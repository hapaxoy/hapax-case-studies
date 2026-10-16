"""
08 Inbox — Phase 4 pipeline, stage 3: gates + router
(pipeline steps 4-5, and the "artefacts logged per email").

Reads `data/pipeline/classify_results.csv` (built by build_draft_tasks.py
from Phase 5's stage-1 classify run) and, for every email that got a draft
task, the draft agent's raw output from `data/pipeline/draft_raw/batch_NN.json`
(Phase 5's stage-2 LLM run; this script makes no LLM
calls itself). It re-derives the same deterministic retrieval facts
build_draft_tasks.py used (the real handbook clause ids, the count of prior
staff messages in each thread) and runs the three gates and the router from
`gates.py` — pure, judgment-free functions — against every draft.

For every one of the 150 emails this produces exactly one decision-trace
artefact and one row in the aggregate summary, whether it was escalated on
classification alone, blocked by a gate, or sent straight through — this is
the per-email logging that marking requires.

This script never reads `data/answer_key/` — marking against the key is a
separate, later, key-reading script (`mark.py`, Phase 6).

`data/pipeline/draft_raw/` is written by Phase 5's draft run, a
separate LLM step. Run this script with --partial once some draft
batches exist to route only the emails already drafted (plus every
escalate-shortcut email, which needs no draft); without --partial, any
missing non-escalate email is an informative error, not a silent partial
run.

Run: python run_gates_and_router.py [--partial]

Outputs:
  data/pipeline/decisions/decision_EML-NNN.json  -- one per email (150):
      intent_class, classification rationale, the draft (or null),
      each gate's verdict (or null), the route, and why.
  data/pipeline/routing_summary.csv              -- one row per email,
      email_id order — the aggregate table Phase 6's marking pass and the
      interactive page's River/Scoreboard views read.
"""

from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

import config
import gates
import retrieval


def log(message: str) -> None:
    print(f"[run_gates_and_router] {message}", flush=True)


FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)
        print(f"[FAIL] {message}", flush=True)
    else:
        print(f"[ok]   {message}", flush=True)


# ---------------------------------------------------------------------------
# Loading upstream artefacts.
# ---------------------------------------------------------------------------

def load_classify_results() -> pd.DataFrame:
    if not config.CLASSIFY_RESULTS_CSV.exists():
        raise SystemExit(
            f"[run_gates_and_router] ERROR: {config.CLASSIFY_RESULTS_CSV} "
            "does not exist. Run build_draft_tasks.py first — it produces "
            "this file from the classify agent's output."
        )
    return pd.read_csv(config.CLASSIFY_RESULTS_CSV)


def load_draft_raw(partial: bool, expected_email_ids: set[str]) -> dict[str, dict]:
    """Load every drafted email's structured response from
    data/pipeline/draft_raw/batch_NN.json. Returns {email_id: draft}."""
    raw_dir = config.DRAFT_RAW_DIR
    if not expected_email_ids:
        return {}
    if not raw_dir.exists():
        raise SystemExit(
            f"[run_gates_and_router] ERROR: {raw_dir} does not exist. The "
            "draft agent has not run yet (Phase 5, stage 2) — this is "
            "expected before that separate LLM run happens. "
            "Nothing to route."
        )

    drafts: dict[str, dict] = {}
    for path in sorted(raw_dir.glob("batch_*.json")):
        try:
            batch = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(
                f"[run_gates_and_router] ERROR: {path} is not valid JSON "
                f"({exc}). Fix or re-run this batch before continuing."
            ) from exc
        entries = batch if isinstance(batch, list) else batch.get("results", batch.get("tasks", []))
        for entry in entries:
            drafts[entry["email_id"]] = entry

    missing = sorted(expected_email_ids - drafts.keys(),
                      key=lambda e: int(e.split("-")[1]))
    if missing and not partial:
        raise SystemExit(
            "[run_gates_and_router] ERROR: missing draft output for "
            f"{len(missing)} email(s) under data/pipeline/draft_raw/: "
            f"{missing}. Re-run with --partial to route only the emails "
            "already drafted, or supply the missing batches."
        )
    if missing:
        log(f"--partial: proceeding without {len(missing)} missing "
            f"drafted email(s): {missing}")

    return drafts


# ---------------------------------------------------------------------------
# Per-email decision assembly.
# ---------------------------------------------------------------------------

def decide_escalate_shortcut(row: pd.Series) -> dict:
    route, reason = gates.route_email(row["intent_class"], gate_results=None)
    return {
        "email_id": row["email_id"],
        "thread_id": row["thread_id"],
        "customer_id": row["customer_id"],
        "intent_class": row["intent_class"],
        "classification_rationale": row["rationale"],
        "draft": None,
        "gate_results": None,
        "route": route,
        "route_reason": reason,
    }


def decide_drafted(
    row: pd.Series,
    draft: dict,
    handbook_ids: set[str],
    prior_staff_count: int,
) -> dict:
    gate_results = gates.run_all_gates(draft, handbook_ids, prior_staff_count)
    route, reason = gates.route_email(row["intent_class"], gate_results=gate_results)
    return {
        "email_id": row["email_id"],
        "thread_id": row["thread_id"],
        "customer_id": row["customer_id"],
        "intent_class": row["intent_class"],
        "classification_rationale": row["rationale"],
        "draft": draft,
        "gate_results": {name: g.to_dict() for name, g in gate_results.items()},
        "route": route,
        "route_reason": reason,
    }


def summary_row(decision: dict) -> dict:
    gate_results = decision["gate_results"] or {}
    return {
        "email_id": decision["email_id"],
        "thread_id": decision["thread_id"],
        "customer_id": decision["customer_id"],
        "intent_class": decision["intent_class"],
        "route": decision["route"],
        "policy_gate_passed": gate_results.get("policy_gate", {}).get("passed"),
        "consistency_gate_passed": gate_results.get("consistency_gate", {}).get("passed"),
        "completeness_gate_passed": gate_results.get("completeness_gate", {}).get("passed"),
        "route_reason": decision["route_reason"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--partial", action="store_true",
        help="route only the emails whose draft output is present (plus "
             "every escalate-shortcut email), instead of erroring on any "
             "missing draft",
    )
    args = parser.parse_args()

    log("08 Inbox — Phase 4 pipeline, stage 3: gates + router")

    log("loading classify results")
    classify_results = load_classify_results()
    check(
        set(classify_results["intent_class"]) <= config.ALL_INTENT_CLASSES,
        "every row in classify_results.csv names a recognised intent class",
    )

    escalate_rows = classify_results[classify_results["escalate_shortcut"]]
    draft_rows = classify_results[~classify_results["escalate_shortcut"]]
    expected_draft_ids = set(draft_rows["email_id"])

    log(f"{len(escalate_rows)} escalate-shortcut email(s), "
        f"{len(draft_rows)} email(s) expecting a draft")

    log("loading draft outputs from data/pipeline/draft_raw/")
    drafts = load_draft_raw(args.partial, expected_draft_ids)

    log("loading policy handbook and thread prose for gate inputs")
    handbook_clauses = retrieval.load_policy_handbook()
    handbook_ids = retrieval.handbook_clause_ids(handbook_clauses)
    threads = retrieval.load_all_threads_prose()
    emails = retrieval.load_all_emails()

    config.DECISIONS_DIR.mkdir(parents=True, exist_ok=True)

    decisions: list[dict] = []

    for _, row in escalate_rows.iterrows():
        decision = decide_escalate_shortcut(row)
        decisions.append(decision)

    for _, row in draft_rows.iterrows():
        email_id = row["email_id"]
        draft = drafts.get(email_id)
        if draft is None:
            continue  # --partial: not yet drafted, skip for this run
        email = emails[email_id]
        thread = threads[email["thread_id"]]
        thread_history = retrieval.thread_messages_before(thread, email_id)
        prior_staff_count = retrieval.prior_staff_message_count(thread_history)
        decision = decide_drafted(row, draft, handbook_ids, prior_staff_count)
        decisions.append(decision)

    decisions.sort(key=lambda d: int(d["email_id"].split("-")[1]))

    for decision in decisions:
        out_path = config.DECISIONS_DIR / f"decision_{decision['email_id']}.json"
        out_path.write_text(json.dumps(decision, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"wrote {len(decisions)} decision file(s) to {config.DECISIONS_DIR}")

    summary_rows = [summary_row(d) for d in decisions]
    pd.DataFrame(summary_rows).to_csv(config.ROUTING_SUMMARY_CSV, index=False)
    log(f"wrote {len(summary_rows)} row(s) to {config.ROUTING_SUMMARY_CSV}")

    route_counts = pd.Series([d["route"] for d in decisions]).value_counts().to_dict()
    log(f"route counts: {route_counts}")

    if not args.partial:
        check(
            len(decisions) == config.TOTAL_EMAILS,
            f"every one of {config.TOTAL_EMAILS} emails has a decision "
            f"(got {len(decisions)})",
        )

    if FAILURES:
        log(f"FAILED: {len(FAILURES)} check(s) did not pass — see [FAIL] lines above")
        sys.exit(1)

    log("done")


if __name__ == "__main__":
    main()
