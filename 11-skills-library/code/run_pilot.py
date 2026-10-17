"""The Phase 5 pilot: dev requests only, the same requests and arms for each model, with a hard spending stop.

Phase 5, 15 Oct 2026: both a larger and a smaller model, measuring both the cost and the
results, to decide which is worth it for the full run. By default: 5 dev requests x 4 arms (S, D, L, L-) x 2 models
= 40 runs, 20 per model, one run per cell, ordered by model, arm, request so the static prefix of an arm stays cached
from run to run. The requests are config.PILOT_REQUEST_IDS.

    python code/run_pilot.py --cap-usd 20 --yes            # the real pilot (needs ANTHROPIC_API_KEY)
    python code/run_pilot.py --cap-usd 20                  # prints the plan and a prior cost estimate, spends nothing
    python code/run_pilot.py --estimate-only               # same, never touches the key
    python code/run_pilot.py --dry-run                     # the whole pipeline with a scripted fake model, no network
    python code/run_pilot.py --remark data/runs/pilot      # mark finished runs again with the current marker, no API call;
                                                           # writes to data/runs/pilot_remarked (or --out-dir), never to the logs' folder

Real runs refuse to start without ANTHROPIC_API_KEY in the environment, and spend only with --yes.

The hard stop: --cap-usd is a ceiling on total pilot spend across both models. Before every API call the harness bounds
that call's cost from above and does not make it if spend so far plus the bound would pass the cap (harness.SpendLedger).
Spend already logged in the output folder counts, so a restart cannot overspend. Costs are computed from the token counts
the API returns at the published prices in config (MODEL_PRICES_USD_PER_MTOK, with the date they were read).

Output (data/runs/pilot/, or data/runs/dry_run/pilot/ for a dry run): one JSON-lines log per run, runs_index.jsonl,
pilot_results.jsonl (one marked line per run), expected_results.json (the dev requests' accepted results),
pilot_summary.json and pilot_summary.txt. The run is resumable: finished runs are skipped.

Caveat built into the report: the dev requests are the library builder's training material, so the D and L arms hold
their queries (a digest in the doc, templates in the library). Pilot correctness for D, L and L- is therefore inflated
and says nothing about the test set; the pilot's job is plumbing, cost and a first look at the models.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Optional

import config as cfg
import harness
import pilot_marking
from fake_client import ScriptedClient

RETRY_STATUSES = {"cap_stop", "api_error"}
STATUS_ORDER = ("correct", "wrong", "no_answer")


# ---------------------------------------------------------------------------
# Safety: where output may go
# ---------------------------------------------------------------------------

def assert_output_is_safe(out_dir: Path) -> None:
    """Output goes only to the chosen folder, which must not be an input folder (or inside one)."""
    protected = [cfg.WORLD_DIR, cfg.ARMS_DIR, cfg.KEY_DIR, cfg.REQUESTS_DIR, cfg.WAREHOUSE_DIR, cfg.INTERNAL_DIR,
                 cfg.CASE_ROOT / "design", cfg.CASE_ROOT / "code"]
    resolved = Path(out_dir).resolve()
    for folder in protected:
        folder = folder.resolve()
        if resolved == folder or folder in resolved.parents:
            raise SystemExit(f"Refusing to write into {resolved}: it is an input folder or inside one ({folder}).")


# ---------------------------------------------------------------------------
# Plan and prior estimate
# ---------------------------------------------------------------------------

def build_plan(models: list, arms: list, request_ids: list, repeats: int) -> list:
    """Run order: model, arm, request, repeat. Keeps an arm's cached prefix warm from run to run."""
    return [{"model": model, "arm": arm, "request_id": request_id, "repeat": repeat}
            for model in models for arm in arms for request_id in request_ids for repeat in range(1, repeats + 1)]


# Assumptions behind the prior estimate (printed with it). Replaced by measured figures once the pilot has run.
PRIOR_TURNS = {"typical": 7, "heavy": 12}
PRIOR_NEW_TOKENS_PER_TURN = {"typical": 1500, "heavy": 2500}          # tool results and the model's own text added each turn
PRIOR_OUTPUT_TOKENS_PER_TURN = {                                       # includes thinking where the model does it by default
    "claude-sonnet-5-5": {"typical": 1200, "heavy": 2500},
    "claude-haiku-4-5-20251001": {"typical": 500, "heavy": 1000},
}
PRIOR_FIRST_PROMPT_TOKENS = 700
PRIOR_CHARS_PER_TOKEN = 3.5


def prior_run_cost_usd(model: str, materials: harness.ArmMaterials, case: str) -> float:
    price = harness.prices_for(model)
    static_tokens = (len(materials.system_text) + len(json.dumps(materials.tools))) / PRIOR_CHARS_PER_TOKEN
    turns, step = PRIOR_TURNS[case], PRIOR_NEW_TOKENS_PER_TURN[case]
    output = PRIOR_OUTPUT_TOKENS_PER_TURN.get(model, PRIOR_OUTPUT_TOKENS_PER_TURN["claude-sonnet-5-5"])[case]
    cost = 0.0
    for turn in range(1, turns + 1):
        cost += static_tokens * price["cache_read"]            # the static prefix is warm in steady state
        conversation_before = PRIOR_FIRST_PROMPT_TOKENS + (turn - 1) * step
        if turn == 1:
            cost += PRIOR_FIRST_PROMPT_TOKENS * price["input"]
        else:
            cost += (conversation_before - step) * price["cache_read"] + step * price["cache_write_5m"]
        cost += output * price["output"]
    return cost / 1_000_000


def print_prior_estimate(plan: list, cap_usd: float) -> float:
    """Print an assumption-based estimate of the pilot and return the suggested cap."""
    materials = {arm: harness.build_arm_materials(arm) for arm in cfg.ARM_LABELS}
    print("\nPrior estimate (assumption-based, before any real run; the measured figures replace it):")
    print(f"  assumptions: typical {PRIOR_TURNS['typical']} model calls per run, heavy {PRIOR_TURNS['heavy']}; "
          f"{PRIOR_NEW_TOKENS_PER_TURN['typical']}/{PRIOR_NEW_TOKENS_PER_TURN['heavy']} new input tokens per call; static prefix cached;")
    print("  output per call (Sonnet incl. its default thinking) "
          f"{PRIOR_OUTPUT_TOKENS_PER_TURN['claude-sonnet-5-5']['typical']}/{PRIOR_OUTPUT_TOKENS_PER_TURN['claude-sonnet-5-5']['heavy']}, "
          f"(Haiku) {PRIOR_OUTPUT_TOKENS_PER_TURN['claude-haiku-4-5-20251001']['typical']}/{PRIOR_OUTPUT_TOKENS_PER_TURN['claude-haiku-4-5-20251001']['heavy']}.")
    totals = {"typical": 0.0, "heavy": 0.0}
    for model in sorted({item["model"] for item in plan}):
        row = []
        for arm in cfg.ARM_LABELS:
            runs = sum(1 for item in plan if item["model"] == model and item["arm"] == arm)
            if not runs:
                continue
            typical = prior_run_cost_usd(model, materials[arm], "typical")
            heavy = prior_run_cost_usd(model, materials[arm], "heavy")
            totals["typical"] += runs * typical
            totals["heavy"] += runs * heavy
            row.append(f"{arm} ${typical:.2f}-{heavy:.2f}")
        print(f"  {model}: per run (typical-heavy)  " + "   ".join(row))
    suggested = math.ceil(max(1.4 * totals["heavy"], 5.0) / 5) * 5
    print(f"  whole pilot ({len(plan)} runs): typical ${totals['typical']:.2f}, heavy ${totals['heavy']:.2f}.")
    print(f"  suggested cap: ${suggested} (the heavy case plus about 40%; the hard stop ends the pilot before it passes the cap you give, "
          "and a stopped pilot resumes where it left off if you raise the cap).")
    if cap_usd and cap_usd < totals["typical"]:
        print(f"  WARNING: the cap ${cap_usd:.2f} is below the typical estimate; the pilot will probably stop early.")
    return suggested


# ---------------------------------------------------------------------------
# Results store (resumable)
# ---------------------------------------------------------------------------

def read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def spent_so_far(out_dir: Path) -> float:
    """Everything logged in this folder counts toward the cap, including stopped and failed attempts."""
    return sum(entry.get("cost_usd", 0.0) for entry in read_jsonl(out_dir / "runs_index.jsonl"))


def latest_by_run_id(results: list) -> dict:
    return {entry["run_id"]: entry for entry in results}


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def mean(values: list) -> float:
    return sum(values) / len(values) if values else float("nan")


def standard_error(values: list) -> float:
    return statistics.stdev(values) / math.sqrt(len(values)) if len(values) > 1 else 0.0


def cell_stats(entries: list) -> dict:
    """Statistics for one model x arm cell (or a whole model when entries span arms)."""
    n = len(entries)
    correct = sum(1 for e in entries if e["outcome"] == "correct")
    cost_total = sum(e["cost_usd"] for e in entries)
    warm = [e["cost_usd_warm_prefix"] for e in entries]
    return {
        "runs": n, "correct": correct, "wrong": sum(1 for e in entries if e["outcome"] == "wrong"),
        "no_answer": sum(1 for e in entries if e["outcome"] == "no_answer"),
        "cost_total_usd": cost_total, "cost_per_run_usd": cost_total / n if n else float("nan"),
        "cost_per_correct_usd": cost_total / correct if correct else None,
        "cost_warm_per_run_usd": mean(warm), "cost_warm_se": standard_error(warm),
        "tokens_fresh_input": mean([e["tokens"]["input_tokens"] for e in entries]),
        "tokens_cache_read": mean([e["tokens"]["cache_read_input_tokens"] for e in entries]),
        "tokens_cache_write": mean([e["tokens"]["cache_creation_input_tokens"] for e in entries]),
        "tokens_output": mean([e["tokens"]["output_tokens"] for e in entries]),
        "seconds_per_run": mean([e["elapsed_s"] for e in entries]),
        "queries_per_run": mean([e["queries_used"] for e in entries]),
        "skills_opened_per_run": mean([len(e["skills_opened"]) for e in entries]),
        "model_ids_returned": sorted({e.get("model_returned") or "?" for e in entries}),
    }


def full_plan_estimate(stats_by_arm: dict) -> dict:
    """Cost of the full plan for one model from the pilot's warm-prefix cost per run: as the main model (all four arms,
    60 requests x 5 runs each) and as the replication model (S and L only). Band = mean +/- 2 standard errors."""
    runs_per_arm = cfg.FULL_PLAN_REQUESTS * cfg.FULL_PLAN_RUNS_PER_REQUEST

    def scenario(arms: tuple) -> dict:
        if any(arm not in stats_by_arm for arm in arms):
            return {"usd": None, "low": None, "high": None, "runs": None}
        point = sum(stats_by_arm[arm]["cost_warm_per_run_usd"] * runs_per_arm for arm in arms)
        spread = 2 * sum(stats_by_arm[arm]["cost_warm_se"] * runs_per_arm for arm in arms)
        return {"usd": point, "low": max(0.0, point - spread), "high": point + spread, "runs": runs_per_arm * len(arms)}
    return {"as_main_model": scenario(cfg.ARM_LABELS), "as_replication_model": scenario(cfg.SMALL_MODEL_REPLICATION_ARMS)}


def money(value) -> str:
    return "n/a" if value is None or value != value else f"${value:,.3f}" if value < 1 else f"${value:,.2f}"


def build_summary(results: list, models: list, arms: list, dry_run: bool) -> dict:
    latest = list(latest_by_run_id(results).values())
    summary = {"dry_run": dry_run, "prices_read_on": cfg.PRICES_READ_ON, "models": {}}
    for model in models:
        mine = [e for e in latest if e["model"] == model]
        by_arm = {arm: cell_stats([e for e in mine if e["arm"] == arm]) for arm in arms if any(e["arm"] == arm for e in mine)}
        summary["models"][model] = {"overall": cell_stats(mine) if mine else None, "by_arm": by_arm,
                                    "full_plan": full_plan_estimate(by_arm) if by_arm else None}
    summary["spent_usd"] = sum(e["cost_usd"] for e in latest)
    return summary


def format_report(summary: dict, models: list, arms: list) -> str:
    """Side by side, one block per measure, rows = arms plus an overall row, columns = models."""
    lines = []
    if summary["dry_run"]:
        lines.append("DRY RUN: scripted fake model, simulated tokens and costs. Nothing here is a real result.\n")
    rows = list(arms) + ["ALL"]

    def pick(model: str, row: str):
        data = summary["models"].get(model)
        if not data:
            return None
        return data["overall"] if row == "ALL" else data["by_arm"].get(row)

    def block(title: str, cell: "callable") -> None:
        lines.append(title)
        width = 34
        lines.append("  " + "arm".ljust(5) + "".join(model.ljust(width) for model in models))
        for row in rows:
            texts = []
            for model in models:
                stats = pick(model, row)
                texts.append((cell(stats) if stats else "-").ljust(width))
            lines.append("  " + row.ljust(5) + "".join(texts))
        lines.append("")

    block("Correct, out of runs (wrong / no answer in brackets):",
          lambda s: f"{s['correct']} of {s['runs']}  ({s['wrong']} wrong, {s['no_answer']} none)")
    block("Cost per run (all calls, as run) / with the static prefix already cached:",
          lambda s: f"{money(s['cost_per_run_usd'])} / {money(s['cost_warm_per_run_usd'])}")
    block("Cost per correct answer (total cost / correct):",
          lambda s: money(s["cost_per_correct_usd"]))
    block("Tokens per run, mean: fresh input / cache read / cache write / output:",
          lambda s: f"{s['tokens_fresh_input']:,.0f} / {s['tokens_cache_read']:,.0f} / {s['tokens_cache_write']:,.0f} / {s['tokens_output']:,.0f}")
    block("Seconds per run, mean:", lambda s: f"{s['seconds_per_run']:.1f}")
    block("Query executions / skills opened per run, mean:",
          lambda s: f"{s['queries_per_run']:.1f} / {s['skills_opened_per_run']:.1f}")
    lines.append("Model IDs returned by the API: " + "; ".join(
        f"{model}: {', '.join(summary['models'][model]['overall']['model_ids_returned'])}"
        for model in models if summary["models"].get(model) and summary["models"][model]["overall"]))
    lines.append("")
    runs_per_arm = cfg.FULL_PLAN_REQUESTS * cfg.FULL_PLAN_RUNS_PER_REQUEST
    lines.append(f"Full plan estimate (prices read {summary['prices_read_on']}; per-run cost taken with the static prefix cached; "
                 f"band is mean +/- 2 standard errors of the pilot runs, n is small):")
    lines.append(f"  main model: {cfg.FULL_PLAN_REQUESTS} requests x {cfg.FULL_PLAN_RUNS_PER_REQUEST} runs x {len(cfg.ARM_LABELS)} arms = "
                 f"{runs_per_arm * len(cfg.ARM_LABELS)} runs.  Replication model: S and L only = {runs_per_arm * 2} runs.")
    for model in models:
        data = summary["models"].get(model)
        if not data or not data["full_plan"]:
            continue
        main, replication = data["full_plan"]["as_main_model"], data["full_plan"]["as_replication_model"]
        fmt = lambda s: "n/a (arms missing from the pilot)" if s["usd"] is None else f"{money(s['usd'])}  (band {money(s['low'])} to {money(s['high'])})"
        lines.append(f"  {model}\n      as the main model:        {fmt(main)}\n      as the replication model: {fmt(replication)}")
    if len(models) == 2:
        first, second = models
        for main_model, replication_model in ((first, second), (second, first)):
            a = (summary["models"].get(main_model) or {}).get("full_plan")
            b = (summary["models"].get(replication_model) or {}).get("full_plan")
            if a and b and a["as_main_model"]["usd"] is not None and b["as_replication_model"]["usd"] is not None:
                lines.append(f"  main {main_model} + replication {replication_model}: "
                             f"{money(a['as_main_model']['usd'] + b['as_replication_model']['usd'])}")
    lines.append("\nRead with care: the pilot uses dev requests, which are the material the doc and the library were built from, "
                 "so D, L and L- correctness is inflated and says nothing about the test set. The test requests include 13 in patterns "
                 "the history lacks and will probably need more calls per run than these, so the cost estimate is more likely low than high. "
                 "One run per cell: differences of one or two answers are noise.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Dry-run policy schedule
# ---------------------------------------------------------------------------

def dry_run_policy(run_id: str) -> str:
    """Deterministic spread of scripted behaviours so a dry run exercises wrong, malformed and thinking cases too."""
    bucket = int(hashlib.sha256(run_id.encode()).hexdigest(), 16) % 10
    if bucket == 0:
        return "wrong"
    if bucket == 1 and "haiku" in run_id:
        return "malformed"
    if bucket == 2:
        return "thinking"
    if bucket == 3:
        return "parallel"
    return "correct"


# ---------------------------------------------------------------------------
# Expected results and marking (shared by a live pilot and a re-mark)
# ---------------------------------------------------------------------------

def load_or_compute_expected(out_dir: Path, request_ids: list, dev: dict, warehouse_path: Path, say) -> dict:
    """Each dev request's accepted result and accepted alternatives, cached in out_dir/expected_results.json. An entry
    written by an older marker version (without alternatives) is computed again."""
    expected_path = out_dir / "expected_results.json"
    expected = json.loads(expected_path.read_text(encoding="utf-8")) if expected_path.exists() else {}
    for request_id in request_ids:
        if expected.get(request_id, {}).get("marker_version") != pilot_marking.MARKER_VERSION:
            say(f"Computing the accepted result of {request_id} and its accepted alternatives ...")
            expected[request_id] = pilot_marking.compute_expected_set(warehouse_path, request_id, dev[request_id]["accepted_sql"])
    expected_path.write_text(json.dumps(expected, indent=1, ensure_ascii=False), encoding="utf-8")
    return expected


def mark_against(summary: dict, expected_entry: dict, request_id: str) -> dict:
    """Mark one run summary against a request's accepted result, its answer spec and its accepted alternatives."""
    return pilot_marking.mark_run(summary, expected_entry["table"], expected_entry["ordered"],
                                  spec=pilot_marking.answer_spec(request_id),
                                  alternatives=expected_entry.get("alternatives", []))


def result_entry(item: dict, summary: dict, mark: dict) -> dict:
    """One line of pilot_results.jsonl."""
    run_id = harness.make_run_id(item["model"], item["arm"], item["request_id"], item["repeat"])
    return {"run_id": run_id, "model": item["model"], "arm": item["arm"], "request_id": item["request_id"],
            "repeat": item["repeat"], "status": summary["status"], "outcome": mark["outcome"], "reason": mark["reason"],
            "marker_version": pilot_marking.MARKER_VERSION,
            "cost_usd": summary["cost_usd"], "cost_usd_warm_prefix": summary["cost_usd_warm_prefix"],
            "tokens": summary["tokens"], "elapsed_s": summary["elapsed_s"], "queries_used": summary["queries_used"],
            "skills_opened": summary["skills_opened"], "scripts_run": summary["scripts_run"], "turns": summary["turns"],
            "model_returned": summary["model_returned"], "problem": summary["problem"], "client_kind": summary["client_kind"]}


def read_run_summary(log_path: Path) -> Optional[dict]:
    """The run_end summary of one run log, or None if the run never finished."""
    ends = [event for event in read_jsonl(log_path) if event.get("event") == "run_end"]
    return ends[-1] if ends else None


def remark_pilot(*, from_dir: Path, out_dir: Path, models: list, arms: list, request_ids: list, repeats: int,
                 dry_run: bool = False, warehouse_path: Path = cfg.WAREHOUSE_PATH, quiet: bool = False) -> dict:
    """Mark the finished runs of an earlier pilot again with the current marker. Reads the run logs in from_dir and
    writes nothing there; the new pilot_results.jsonl, expected_results.json and summary go to out_dir. No API call."""
    from_dir, out_dir = Path(from_dir), Path(out_dir)
    if from_dir.resolve() == out_dir.resolve():
        raise SystemExit("A re-mark writes to a new folder: --out-dir must differ from the folder holding the run logs.")
    assert_output_is_safe(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    say = (lambda *a, **k: None) if quiet else print
    dev = harness.load_dev_requests()
    expected = load_or_compute_expected(out_dir, request_ids, dev, warehouse_path, say)
    earlier = latest_by_run_id(read_jsonl(from_dir / "pilot_results.jsonl"))
    results, changes = [], []
    for item in build_plan(models, arms, request_ids, repeats):
        run_id = harness.make_run_id(item["model"], item["arm"], item["request_id"], item["repeat"])
        log_path = from_dir / f"{run_id}.jsonl"
        summary = read_run_summary(log_path) if log_path.exists() else None
        if summary is None:
            say(f"  {run_id}: no finished log in {from_dir}, skipped")
            continue
        mark = mark_against(summary, expected[item["request_id"]], item["request_id"])
        entry = result_entry(item, summary, mark)
        before = earlier.get(run_id, {})
        entry["outcome_before"], entry["reason_before"] = before.get("outcome"), before.get("reason")
        results.append(entry)
        if before and before.get("outcome") != mark["outcome"]:
            changes.append(entry)
    (out_dir / "pilot_results.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in results), encoding="utf-8")
    summary_dict = build_summary(results, models, arms, dry_run)
    summary_dict.update({"remarked_from": str(from_dir), "marker_version": pilot_marking.MARKER_VERSION, "plan_runs": len(results)})
    text = (f"RE-MARK of the runs in {from_dir} with marker version {pilot_marking.MARKER_VERSION}. No model was called; "
            "the model outputs, tokens and costs are those of the original runs.\n\n") + format_report(summary_dict, models, arms)
    (out_dir / "pilot_summary.json").write_text(json.dumps(summary_dict, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    (out_dir / "pilot_summary.txt").write_text(text, encoding="utf-8")
    say("\n" + text)
    say(f"\n{len(changes)} run(s) changed outcome:")
    for entry in changes:
        say(f"  {entry['run_id']}: {entry['outcome_before']} -> {entry['outcome']}  ({entry['reason']})")
    still_wrong = [e for e in results if e["outcome"] != "correct"]
    if still_wrong:
        say("\nRuns still not marked correct:")
        for entry in still_wrong:
            say(f"  {entry['run_id']}: {entry['outcome']} - {entry['reason']}")
    say(f"\nRe-marked results and summary are in {out_dir}")
    return summary_dict


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_pilot(*, models: list, arms: list, request_ids: list, repeats: int, cap_usd: float, out_dir: Path,
              client, dry_run: bool, warehouse_path: Path = cfg.WAREHOUSE_PATH, quiet: bool = False) -> dict:
    """Run (or resume) the pilot. Returns the summary dict."""
    assert_output_is_safe(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    say = (lambda *a, **k: None) if quiet else print
    dev = harness.load_dev_requests()
    unknown = [r for r in request_ids if r not in dev]
    if unknown:
        raise SystemExit(f"Not dev requests: {unknown}. The pilot uses REQ-D01..REQ-D40 only.")

    # Expected results: each dev request's accepted query and its accepted alternatives, run once on the warehouse.
    expected = load_or_compute_expected(out_dir, request_ids, dev, warehouse_path, say)

    plan = build_plan(models, arms, request_ids, repeats)
    results_path = out_dir / "pilot_results.jsonl"
    results = read_jsonl(results_path)
    finished = {run_id for run_id, entry in latest_by_run_id(results).items() if entry["status"] not in RETRY_STATUSES}
    ledger = harness.SpendLedger(cap_usd, spent_so_far(out_dir))
    say(f"\nPilot: {len(plan)} runs planned, {len([p for p in plan if harness.make_run_id(p['model'], p['arm'], p['request_id'], p['repeat']) in finished])} "
        f"already done. Spent so far ${ledger.spent_usd:.4f} of the ${cap_usd:.2f} cap.")
    materials_cache = {arm: harness.build_arm_materials(arm) for arm in arms}
    consecutive_api_errors = 0
    stopped_by = None
    for position, item in enumerate(plan, start=1):
        run_id = harness.make_run_id(item["model"], item["arm"], item["request_id"], item["repeat"])
        if run_id in finished:
            continue
        if dry_run and isinstance(client, ScriptedClient):
            client.policy = dry_run_policy(run_id)
            client.accepted_sql_by_text[dev[item["request_id"]]["request"]["request_text"].strip()] = dev[item["request_id"]]["accepted_sql"]
        summary = harness.run_one(request=dev[item["request_id"]]["request"], arm=item["arm"], model=item["model"],
                                  repeat=item["repeat"], client=client, out_dir=out_dir, warehouse_path=warehouse_path,
                                  materials=materials_cache[item["arm"]], ledger=ledger, run_id=run_id, log_label="pilot")
        mark = mark_against(summary, expected[item["request_id"]], item["request_id"])
        entry = result_entry(item, summary, mark)
        with open(results_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        results.append(entry)
        tokens = summary["tokens"]
        say(f"[{position}/{len(plan)}] {item['model'].split('-20')[0]:<18} {item['arm']:<2} {item['request_id']}  {mark['outcome']:<10}"
            f"${summary['cost_usd']:.4f}  in {tokens['input_tokens']:,} / read {tokens['cache_read_input_tokens']:,} / write "
            f"{tokens['cache_creation_input_tokens']:,} / out {tokens['output_tokens']:,}  {summary['elapsed_s']:.0f}s  "
            f"{summary['queries_used']}q  [{summary['status']}]  total ${ledger.spent_usd:.3f} / ${cap_usd:.2f}")
        consecutive_api_errors = consecutive_api_errors + 1 if summary["status"] == "api_error" else 0
        if summary["status"] == "cap_stop":
            stopped_by = f"spending cap reached ({summary['problem']})"
            break
        if consecutive_api_errors >= cfg.PILOT_CONSECUTIVE_API_ERRORS_ABORT:
            stopped_by = f"{consecutive_api_errors} API errors in a row (last: {summary['problem']})"
            break
    if stopped_by:
        say(f"\nPILOT STOPPED EARLY: {stopped_by}. Finished runs are kept; run the same command again to resume "
            f"(raise --cap-usd if the cap was the reason).")

    summary_dict = build_summary(results, models, arms, dry_run)
    summary_dict["stopped_early"] = stopped_by
    summary_dict["plan_runs"] = len(plan)
    summary_dict["cap_usd"] = cap_usd
    text = format_report(summary_dict, models, arms)
    (out_dir / "pilot_summary.json").write_text(json.dumps(summary_dict, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    (out_dir / "pilot_summary.txt").write_text(text, encoding="utf-8")
    say("\n" + text)
    wrong = [e for e in latest_by_run_id(results).values() if e["outcome"] != "correct"]
    if wrong:
        say("\nRuns not marked correct:")
        for e in wrong:
            say(f"  {e['run_id']}: {e['outcome']} - {e['reason']}")
    say(f"\nLogs and summary are in {out_dir}")
    return summary_dict


def main(argv: list = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Phase 5 pilot: dev requests, both models, hard spending cap.")
    parser.add_argument("--cap-usd", type=float, help="hard ceiling on total pilot spend in USD, across all models (required for a real run)")
    parser.add_argument("--models", default=",".join(cfg.PILOT_MODELS), help="comma-separated model IDs")
    parser.add_argument("--arms", default=",".join(cfg.PILOT_ARMS), help="comma-separated arms (S,D,L,L-)")
    parser.add_argument("--requests", default=",".join(cfg.PILOT_REQUEST_IDS), help="comma-separated dev request IDs")
    parser.add_argument("--repeats", type=int, default=cfg.PILOT_REPEATS, help="runs per model x arm x request")
    parser.add_argument("--out-dir", type=Path, help="output folder (default data/runs/pilot, or data/runs/dry_run/pilot)")
    parser.add_argument("--yes", action="store_true", help="really spend: without it the script prints the plan and exits")
    parser.add_argument("--dry-run", action="store_true", help="scripted fake model, no network, no key, simulated costs")
    parser.add_argument("--estimate-only", action="store_true", help="print the plan and the prior estimate, then exit")
    parser.add_argument("--remark", type=Path, metavar="FROM_DIR",
                        help="re-mark the finished run logs in FROM_DIR with the current marker (no API call); "
                             "output to --out-dir, default data/runs/pilot_remarked")
    args = parser.parse_args(argv)

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    request_ids = [r.strip() for r in args.requests.split(",") if r.strip()]
    bad_arms = [a for a in arms if a not in cfg.ARM_LABELS]
    if bad_arms:
        print(f"Unknown arms {bad_arms}; arms are {cfg.ARM_LABELS}.")
        return 2
    for model in models:
        harness.prices_for(model)
    if args.remark:
        # Re-mark only: reads finished logs, calls no model, never writes into the logs' folder.
        remark_pilot(from_dir=args.remark, out_dir=args.out_dir or (cfg.RUNS_DIR / f"{cfg.PILOT_DIRNAME}_remarked"),
                     models=models, arms=arms, request_ids=request_ids, repeats=args.repeats)
        return 0
    plan = build_plan(models, arms, request_ids, args.repeats)

    print(f"Pilot plan: {len(plan)} runs = {len(models)} models x {len(arms)} arms x {len(request_ids)} requests x {args.repeats} repeat(s).")
    print(f"Models: {', '.join(models)}.  Arms: {', '.join(arms)}.  Requests: {', '.join(request_ids)}.")
    print(f"Prices (USD per million tokens, read {cfg.PRICES_READ_ON} from {cfg.PRICES_SOURCE}):")
    for model in models:
        p = cfg.MODEL_PRICES_USD_PER_MTOK[model]
        print(f"  {model}: input {p['input']}, cache write {p['cache_write_5m']}, cache read {p['cache_read']}, output {p['output']}")
    suggested = print_prior_estimate(plan, args.cap_usd or 0.0)
    if args.estimate_only:
        return 0

    out_dir = args.out_dir or (cfg.RUNS_DIR / "dry_run" / cfg.PILOT_DIRNAME if args.dry_run else cfg.RUNS_DIR / cfg.PILOT_DIRNAME)
    if args.dry_run:
        dev = harness.load_dev_requests()
        client = ScriptedClient({entry["request"]["request_text"]: entry["accepted_sql"] for entry in dev.values()})
        cap = args.cap_usd if args.cap_usd else 1_000.0
        print("\nDRY RUN: scripted fake model; no key is read and no network is used.")
    else:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            print("\nANTHROPIC_API_KEY is not set in the environment. Refusing to start: a real pilot needs the key. "
                  "(Use --dry-run to exercise the pipeline without one.)")
            return 2
        if not args.cap_usd or args.cap_usd <= 0:
            print(f"\n--cap-usd is required for a real run (the hard spending stop). Suggested: --cap-usd {suggested}.")
            return 2
        if not args.yes:
            print(f"\nNothing has been spent. To start: add --yes (cap ${args.cap_usd:.2f}).")
            return 0
        client = harness.AnthropicClient(key)
        cap = args.cap_usd
    started = time.monotonic()
    run_pilot(models=models, arms=arms, request_ids=request_ids, repeats=args.repeats, cap_usd=cap, out_dir=out_dir,
              client=client, dry_run=args.dry_run)
    print(f"Done in {time.monotonic() - started:.0f}s.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
