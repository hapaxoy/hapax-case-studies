"""Collect the full run: the 1,800 final messages, their counters and their usage lines, into one table.

    python code/collect_full.py            # writes data/analysis/collected_runs.jsonl and collection_report.json

For each run in data/agent_runs/full_plan.json this reads, and never writes:
  - the final message: data/agent_runs/scratch/full/final-<run_id>.txt, or recovered-<run_id>.txt where code/recover_final_message.py
    wrote one (a final that was cut off when it was saved; the recovered text is the message in the agent's own transcript);
  - the counter: data/agent_runs/counters/<run_id>.json (queries used, the budget the run was held to, each call);
  - the saved usage line: data/agent_runs/scratch/full/usage-round-NN.jsonl, taken from the round the plan gives the
    run (the re-runs of the 38 runs that hit the old 12-query cap have their usage in rounds 61 and 62; the old line in the first
    round belongs to the superseded answer and is not used).

Parsing is the pilot's: the message is HTML-unescaped (some finals carry &lt; &gt; &amp;, some do not; unescaping is harmless on both),
then read as a bare JSON object, one in a code fence, or one with a sentence around it, and it must carry the five contract keys with
a result table. A final that fails is kept with status "malformed" or "no_answer" and the reason. The superseded cap-12 answers in
data/agent_runs/superseded_cap12/ are NOT collected.
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_agent_answer as pilot_collect      # noqa: E402  (parse_agent_message: unescape, fences, a sentence around the JSON)

CASE_ROOT = Path(__file__).resolve().parent.parent
PLAN_PATH = CASE_ROOT / "data" / "agent_runs" / "full_plan.json"
FINALS_DIR = CASE_ROOT / "data" / "agent_runs" / "scratch" / "full"
COUNTERS_DIR = CASE_ROOT / "data" / "agent_runs" / "counters"
SUPERSEDED_DIR = CASE_ROOT / "data" / "agent_runs" / "superseded_cap12"
OUT_DIR = CASE_ROOT / "data" / "analysis"
INPUT_DIRS = [FINALS_DIR, COUNTERS_DIR, SUPERSEDED_DIR, PLAN_PATH.parent]
ANSWER_KEYS = ("sql", "result", "definitions_applied", "assumptions", "caveats")


def read_usage(finals_dir: Path) -> dict:
    """run_id -> {round: usage record}, from every usage-round-NN.jsonl."""
    usage = collections.defaultdict(dict)
    for path in sorted(finals_dir.glob("usage-round-*.jsonl")):
        round_number = int(re.search(r"usage-round-(\d+)", path.name).group(1))
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                print(f"  warning: {path.name} line {line_number} is not JSON; skipped")
                continue
            usage[record["run_id"]][round_number] = record
    return usage


def final_message(run_id: str, finals_dir: Path) -> tuple:
    """(text, source). source is 'recovered', 'saved' or 'missing'."""
    recovered = finals_dir / f"recovered-{run_id}.txt"
    if recovered.is_file():
        return recovered.read_text(encoding="utf-8"), "recovered"
    saved = finals_dir / f"final-{run_id}.txt"
    if saved.is_file():
        return saved.read_text(encoding="utf-8"), "saved"
    return None, "missing"


def collect_run(entry: dict, usage: dict, finals_dir: Path, counters_dir: Path) -> dict:
    run_id = entry["run_id"]
    text, source = final_message(run_id, finals_dir)
    counter = json.loads((counters_dir / f"{run_id}.json").read_text(encoding="utf-8"))
    status, problem, answer, unescaped = "ok", "", None, False
    if text is None:
        status, problem = "no_answer", "no final message file"
    elif not text.strip():
        status, problem = "no_answer", "empty final message"
    else:
        answer, problem, unescaped = pilot_collect.parse_agent_message(text)
        if answer is None:
            status = "malformed"
    usage_record = usage.get(run_id, {}).get(entry["round"])
    calls = [call for call in counter["calls"] if not call.get("refused")]
    return {
        "run_id": run_id, "model": entry["agent_model"], "arm": entry["arm"], "request_id": entry["request_id"], "repeat": entry["repeat"],
        "plan_round": entry["round"], "first_round": entry.get("first_round"), "rerun_of_cap": bool(entry.get("rerun_of_cap")),
        "told_budget": counter["budget"], "task_instructions_version": counter.get("task_instructions_version"),
        "status": status, "problem": problem, "final_source": source, "entities_unescaped": unescaped, "final_chars": len(text or ""),
        "answer": answer,
        "queries_used": counter["used"], "queries_refused": counter.get("refused", 0), "scripts_run": [c["statement"].split(" ")[0] for c in calls if c["kind"] == "script"],
        "script_calls": sum(1 for c in calls if c["kind"] == "script"), "sql_calls": sum(1 for c in calls if c["kind"] == "sql"),
        "calls_failed": sum(1 for c in calls if not c.get("ok", False)),
        "total_tokens": usage_record.get("tokens") if usage_record else None,
        "tool_calls_reported": usage_record.get("tool_calls") if usage_record else None,
        "duration_s": usage_record.get("duration_s") if usage_record else None,
        "usage_note": usage_record.get("note") if usage_record else None,
        "usage_missing": usage_record is None,
    }


def collect_all(out_dir: Path = OUT_DIR, quiet: bool = False) -> dict:
    say = (lambda *a, **k: None) if quiet else print
    if any(out_dir.resolve() == d.resolve() for d in INPUT_DIRS):
        raise SystemExit(f"Refusing to write into {out_dir}: it is an input folder.")
    out_dir.mkdir(parents=True, exist_ok=True)
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    usage = read_usage(FINALS_DIR)
    say(f"Collecting {len(plan['runs'])} runs ...")
    rows = [collect_run(entry, usage, FINALS_DIR, COUNTERS_DIR) for entry in plan["runs"]]
    (out_dir / "collected_runs.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    failed = [{"run_id": r["run_id"], "status": r["status"], "reason": r["problem"], "chars": r["final_chars"]} for r in rows if r["status"] != "ok"]
    contract_gaps = []
    for row in rows:
        if row["answer"] is not None:
            missing = [key for key in ANSWER_KEYS if key not in row["answer"]]
            if missing:
                contract_gaps.append({"run_id": row["run_id"], "missing": missing})
    report = {
        "runs": len(rows), "parsed_ok": sum(r["status"] == "ok" for r in rows), "failed_to_parse": failed,
        "final_from_recovered_file": [r["run_id"] for r in rows if r["final_source"] == "recovered"],
        "entities_unescaped": sum(r["entities_unescaped"] for r in rows),
        "runs_without_usage_line": [r["run_id"] for r in rows if r["usage_missing"]],
        "usage_notes": [{"run_id": r["run_id"], "note": r["usage_note"]} for r in rows if r["usage_note"]],
        "rerun_of_cap_runs": sum(r["rerun_of_cap"] for r in rows),
        "by_cell": {f"{model}/{arm}": n for (model, arm), n in sorted(collections.Counter((r["model"], r["arm"]) for r in rows).items())},
        "told_budget_by_cell": {f"{model}/{arm}": dict(collections.Counter(r["told_budget"] for r in rows if (r["model"], r["arm"]) == (model, arm)))
                                for (model, arm) in sorted({(r["model"], r["arm"]) for r in rows})},
        "contract_gaps": contract_gaps,
    }
    (out_dir / "collection_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    say(f"  parsed ok: {report['parsed_ok']} of {report['runs']}; failed: {len(failed)}; recovered-file finals: {report['final_from_recovered_file']}")
    return report


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    report = collect_all()
    print(json.dumps({k: v for k, v in report.items() if k not in ("by_cell",)}, indent=1, ensure_ascii=False)[:6000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
