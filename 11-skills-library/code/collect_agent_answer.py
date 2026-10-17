"""Turn one finished agent run into a run log, in the shape the API pilot logs have.

    python code/collect_agent_answer.py --run p2-sonnet-S-d05-r1 --final-message-file final.txt \\
        --tokens 48210 --tool-calls 9 --duration "2m 41s"

The main session pastes what the Agent tool reports (tokens, tool calls, duration) and the agent's final message; this script
adds what the run left behind: its counter file (data/agent_runs/counters/<run_id>.json), which holds the arm, model and request
the run was registered for and every call the SQL and script commands made, with the SQL and a preview of each output.
Nothing the agent says about its own queries is taken on trust: queries_used, the SQL it ran and the scripts it ran come from
the counter.

Output (default data/agent_runs/logs/): <run_id>.jsonl with the events run_start, tool_call / tool_result (one pair per
counted call), message (the final message) and run_end, and one line appended to runs_index.jsonl. The run_end summary has the keys of the
API harness's summary (run_id, arm, model_requested, request_id, status, problem, answer, queries_used, scripts_run, ...) plus
the agent figures (tokens as total_tokens only, tool_calls_reported, elapsed_s, final_sql_was_run). An earlier log of the same
run id is kept as .attemptN.jsonl, never overwritten. Reads the packet and counter; writes nothing else.

Parsing: the final message is HTML-unescaped first (html.unescape), then read as a bare JSON object, one inside a code fence or
one with a sentence before or after it. The log's message event keeps the text as the agent wrote it; the summary's entities_unescaped says
whether unescaping changed anything.

Statuses: ok (a parsed JSON answer in the contract), malformed (a final message that is not), no_answer (empty), agent_error
(--agent-failed REASON: the agent died, was stopped or refused before answering).
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_agent_packets as bp          # noqa: E402
import config as cfg                      # noqa: E402
import harness                            # noqa: E402

LOG_LABEL = "agent"


# ---------------------------------------------------------------------------
# Reading what the Agent tool reports
# ---------------------------------------------------------------------------

def parse_tokens(text) -> int:
    """'48210', '48,210', '48.2k', '1.2m' -> an integer."""
    cleaned = str(text).strip().lower().replace(",", "").replace(" ", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([km]?)", cleaned)
    if not match:
        raise SystemExit(f"Cannot read a token count from {text!r}; give a number such as 48210 or 48.2k.")
    return int(round(float(match.group(1)) * {"": 1, "k": 1_000, "m": 1_000_000}[match.group(2)]))


def parse_duration_seconds(text) -> float:
    """'95', '95s', '2m 41s', '1:35', '1:02:03', '161000ms', '2.5 min' -> seconds. A bare number is seconds."""
    cleaned = str(text).strip().lower()
    clock = re.fullmatch(r"(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)", cleaned)
    if clock:
        hours, minutes, seconds = int(clock.group(1) or 0), int(clock.group(2)), float(clock.group(3))
        return hours * 3600 + minutes * 60 + seconds
    if re.fullmatch(r"\d+(?:\.\d+)?", cleaned):
        return float(cleaned)
    total, found = 0.0, False
    for number, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(ms|milliseconds?|h|hours?|hrs?|m|mins?|minutes?|s|secs?|seconds?)\b", cleaned):
        found = True
        value = float(number)
        if unit.startswith("ms") or unit.startswith("milli"):
            total += value / 1000
        elif unit.startswith("h"):
            total += value * 3600
        elif unit.startswith("m"):
            total += value * 60
        else:
            total += value
    if not found:
        raise SystemExit(f"Cannot read a duration from {text!r}; give seconds (95), a clock (1:35) or words (2m 41s).")
    return total


def unescape_message(text: str) -> tuple:
    """The agent's final message with HTML entities turned back into characters (&lt; &gt; &amp; and the like), and whether any changed.
    Pilot 2's final messages reached the files entity-escaped (the agents' own transcripts hold raw < > &, so the escaping came in
    transit); the answer the agent gave is the unescaped one.
    The log keeps the message exactly as it came; only the parsing sees the unescaped text."""
    unescaped = html.unescape(text or "")
    return unescaped, unescaped != (text or "")


def parse_agent_message(text: str) -> tuple:
    """Parse an agent's final message into the JSON contract: (answer_or_None, problem_text, entities_were_unescaped).
    Accepts a bare JSON object, one wrapped in a code fence, one preceded (or followed) by a sentence, and one whose SQL or
    labels came back with HTML entities. The contract itself is checked by harness.parse_final_answer."""
    unescaped, changed = unescape_message(text)
    answer, problem = harness.parse_final_answer(unescaped)
    if answer is not None:
        return answer, problem, changed
    # A sentence after the object that holds a brace defeats the first-to-last-brace rule: try every opening brace in turn.
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", unescaped):
        try:
            candidate, _ = decoder.raw_decode(unescaped[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and "result" in candidate:
            checked, problem_again = harness.parse_final_answer(json.dumps(candidate))
            if checked is not None:
                return checked, "", changed
            problem = problem_again
            break
    return None, problem, changed


def normalise_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", (sql or "").strip().rstrip(";").strip()).lower()


# ---------------------------------------------------------------------------
# Collecting
# ---------------------------------------------------------------------------

def collect(run_id: str, final_text: str, *, total_tokens: Optional[int], tool_calls: Optional[int], duration_s: Optional[float],
            paths: Optional[bp.AgentPaths] = None, out_dir: Optional[Path] = None, agent_failed: Optional[str] = None,
            label: str = LOG_LABEL) -> dict:
    """Write the run log for one finished run and return its summary."""
    paths = paths or bp.AgentPaths.default()
    counter_file = paths.counters_dir / f"{bp.hx_common.check_run_id(run_id)}.json"
    if not counter_file.is_file():
        raise SystemExit(f"No counter file for run {run_id} ({counter_file}). The run was never registered by build_agent_packets.py.")
    counter = json.loads(counter_file.read_text(encoding="utf-8"))
    request = bp.load_request(counter["request_id"])
    arm, alias = counter["arm"], counter["model"]
    model_id = cfg.AGENT_MODEL_IDS[alias]
    out_dir = Path(out_dir) if out_dir else paths.agent_dir / "logs"
    if out_dir.resolve() in [paths.packets_dir.resolve(), paths.stage_dir.resolve(), paths.counters_dir.resolve()]:
        raise SystemExit(f"Refusing to write logs into {out_dir}: it is an input folder of the runs.")
    import run_pilot
    run_pilot.assert_output_is_safe(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    entities_unescaped = False
    if agent_failed:
        answer, problem, status = None, agent_failed, "agent_error"
    else:
        answer, problem, entities_unescaped = parse_agent_message(final_text)
        status = "ok" if answer is not None else ("no_answer" if not (final_text or "").strip() else "malformed")
    calls = [call for call in counter["calls"] if not call.get("refused")]
    refused = [call for call in counter["calls"] if call.get("refused")]
    scripts_run = [call["statement"].split(" ")[0] for call in calls if call["kind"] == "script"]
    final_sql_ran = None
    if answer is not None:
        ran = {normalise_sql(call["statement"]) for call in calls if call["kind"] == "sql"}
        final_sql_ran = normalise_sql(answer.get("sql", "")) in ran if isinstance(answer.get("sql"), str) else False

    log_path = out_dir / f"{run_id}.jsonl"
    if log_path.exists():
        attempt = 1
        while (out_dir / f"{run_id}.attempt{attempt}.jsonl").exists():
            attempt += 1
        log_path.rename(out_dir / f"{run_id}.attempt{attempt}.jsonl")
    packet_file = paths.packets_dir
    packet_hits = sorted(packet_file.glob(f"*/{run_id}.txt"))
    packet_sha = hashlib.sha256(packet_hits[0].read_bytes()).hexdigest() if packet_hits else None
    events = []

    def event(kind: str, **fields) -> None:
        events.append({"event": kind, "at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), **fields})

    event("run_start", run_id=run_id, label=label, arm=arm, model_requested=model_id, model_alias=alias, repeat=_repeat(run_id), request=request,
          tools=["Bash", "Read", "Glob"], system_sha256=packet_sha, packet_matches_counter=(packet_sha == counter.get("packet_sha256")),
          client_kind="claude-code-agent", budgets={"max_queries": counter["budget"], "max_skill_loads": cfg.MAX_SKILL_LOADS},
          task_instructions_version=counter.get("task_instructions_version"), harness_version="agent-1.0", warehouse=harness.warehouse_fingerprint())
    event("message", role="user", content=[{"type": "text", "text": harness.task_text(request)}])
    for call in calls:
        tool_name = "hx_sql" if call["kind"] == "sql" else "hx_script"
        event("tool_call", name=tool_name, input={"statement": call["statement"]}, call_number=call["n"], called_at=call["at"])
        event("tool_result", name=tool_name, is_error=not call.get("ok", False), content=call.get("output_preview", ""), rows=call.get("rows"),
              queries_used=call["n"])
    for call in refused:
        event("tool_call", name="hx_" + call["kind"], input={"statement": call["statement"]}, refused=True, called_at=call["at"])
    event("message", role="assistant", content=[{"type": "text", "text": final_text or ""}])
    summary = {
        "run_id": run_id, "label": label, "arm": arm, "model_requested": model_id, "model_alias": alias, "model_returned": None,
        "request_id": counter["request_id"], "repeat": _repeat(run_id), "status": status, "problem": problem, "answer": answer,
        "final_text": final_text if status != "ok" else None, "turns": None, "queries_used": counter["used"],
        "skills_opened": None, "files_read": None, "scripts_run": scripts_run, "refused_query_calls": counter.get("refused", 0),
        "tokens": {"total_tokens": total_tokens}, "cost_usd": None, "cost_usd_warm_prefix": None,
        "elapsed_s": round(duration_s, 2) if duration_s is not None else None, "tool_calls_reported": tool_calls,
        "final_sql_was_run": final_sql_ran, "stop_reasons": [], "client_kind": "claude-code-agent", "log_file": log_path.name,
        "packet_sha256": packet_sha, "entities_unescaped": entities_unescaped,
    }
    event("run_end", **summary)
    log_path.write_text("".join(json.dumps(item, ensure_ascii=False, default=str) + "\n" for item in events), encoding="utf-8")
    with open(out_dir / "runs_index.jsonl", "a", encoding="utf-8") as index_file:
        index_file.write(json.dumps({key: value for key, value in summary.items() if key != "answer"} | {"answer_present": answer is not None},
                                    ensure_ascii=False, default=str) + "\n")
    return summary


def _repeat(run_id: str) -> int:
    match = re.search(r"-r(\d+)$", run_id)
    return int(match.group(1)) if match else 1


def main(argv: list = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Write the run log for one finished agent run.")
    parser.add_argument("--run", required=True)
    parser.add_argument("--final-message-file", help="file holding the agent's final message ('-' for standard input)")
    parser.add_argument("--agent-failed", metavar="REASON", help="the agent died or was stopped before answering")
    parser.add_argument("--tokens", help="total tokens the Agent tool reported, e.g. 48210 or 48.2k")
    parser.add_argument("--tool-calls", type=int, help="tool calls the Agent tool reported")
    parser.add_argument("--duration", help="duration the Agent tool reported: seconds, 1:35 or '2m 41s'")
    parser.add_argument("--out-dir", type=Path, help="where to write the log (default data/agent_runs/logs)")
    args = parser.parse_args(argv)
    if args.agent_failed:
        final_text = ""
    elif args.final_message_file == "-":
        final_text = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    elif args.final_message_file:
        final_text = Path(args.final_message_file).read_text(encoding="utf-8")
    else:
        raise SystemExit("Give --final-message-file (or --agent-failed REASON).")
    summary = collect(args.run, final_text, total_tokens=parse_tokens(args.tokens) if args.tokens else None, tool_calls=args.tool_calls,
                      duration_s=parse_duration_seconds(args.duration) if args.duration else None, out_dir=args.out_dir, agent_failed=args.agent_failed)
    print(f"{summary['run_id']}: status {summary['status']}, {summary['queries_used']} counted queries, "
          f"final SQL ran: {summary['final_sql_was_run']}, log {summary['log_file']}" + (f"  ({summary['problem']})" if summary["problem"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
