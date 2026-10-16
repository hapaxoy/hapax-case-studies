"""
08 Inbox — Phase 4 pipeline, stage 2: draft task-file builder
(pipeline steps 2-3, "Retrieve" + "Draft (model)").

Reads the classify agent's raw output from
`data/pipeline/classify_raw/batch_NN.json` (Phase 5's stage-1 LLM run; this
script makes no LLM calls itself) and, for every email
NOT classified into an escalate-on-classification class, performs
deterministic retrieval (the full policy handbook, the customer's account
record, and the thread history preceding this email) and writes a
self-contained draft task for the stage-2 drafting agent.

Emails classified 'safety' or 'data_request' get NO draft task at all —
The pipeline design is explicit that those classes "never receive a drafted reply
at all". This script instead assembles `data/pipeline/classify_results.csv`
covering every email (escalate-shortcut or not), which is the audit trail
`run_gates_and_router.py` reads back to route those emails directly to
'escalate' without ever looking for a draft.

This script never reads `data/answer_key/`, `data/threads/`, or
`data/email_briefs/` — only `data/pipeline/classify_raw/` (Phase 5 output),
`data/emails/`, `data/threads_prose/`, `data/policy/`, and
`data/customers/` via retrieval.py.

`data/pipeline/classify_raw/` is written by Phase 5's classify run, a
separate LLM step. Run this script with --partial once some
classify batches exist to build draft tasks only for the emails already
classified; without --partial, any missing batch is an informative error,
not a silent partial run (mirrors assemble_emails.py / assemble_dossiers.py
convention).

Run: python build_draft_tasks.py [--partial]

Outputs:
  data/pipeline/classify_results.csv           -- one row per classified
                                                   email (email_id,
                                                   thread_id, customer_id,
                                                   intent_class, rationale,
                                                   escalate_shortcut)
  data/pipeline/draft_tasks/task_EML-NNN.json  -- one per non-escalate
                                                   classified email
  data/pipeline/draft_batches/batch_NN.json    -- fixed-size batches,
                                                   output contract embedded
"""

from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

import config
import retrieval


def log(message: str) -> None:
    print(f"[build_draft_tasks] {message}", flush=True)


FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)
        print(f"[FAIL] {message}", flush=True)
    else:
        print(f"[ok]   {message}", flush=True)


# ---------------------------------------------------------------------------
# The drafting contract — embedded verbatim in every task and batch file.
# ---------------------------------------------------------------------------

DRAFT_CONTRACT = {
    "task": (
        "You are the drafting step of Haapaharju Oy's customer-email "
        "support pipeline, for the one email given below. You are shown "
        "the email, everything said earlier in its thread, the "
        "customer's account record, the complete policy handbook, and "
        "the discount-authority table. Produce a structured draft reply "
        "that a downstream, separate set of automated checks will "
        "verify — you are not deciding whether this reply gets sent; you "
        "are producing the material those checks verify."
    ),
    "rules": [
        "Every commitment you make of type 'refusal', 'waiver_or_discount', "
        "or 'correction' must cite the real policy clause id it rests on. "
        "Never invent a clause or a policy term that is not in the "
        "handbook given to you.",
        "Never propose a discretionary discount or waiver beyond what the "
        "discount-authority table allows for any role (the highest role's "
        "limit is the absolute ceiling) — if the customer's ask exceeds "
        "every authority level, do not grant it in the reply text; say it "
        "requires management approval instead.",
        "Review EVERY prior staff message in the thread history "
        "individually, even ones that seem unrelated to today's request, "
        "and record in 'prior_commitments_reviewed' how your draft treats "
        "each one: 'not_applicable' (nothing to honour or contradict), "
        "'honoured' (your draft's commitments are consistent with it), "
        "'contradicted' (your draft would go against it — use this "
        "honestly even though it will block the reply; do not hide a real "
        "conflict), or 'escalated_instead' (you are not attempting to "
        "resolve it in this reply because it needs a human decision).",
        "Never silently ignore or reverse something a staff member "
        "already told this customer in this thread. If you cannot honour "
        "a prior commitment, say so explicitly in the reply text as well "
        "as in prior_commitments_reviewed.",
        "List every distinct question or request the customer's email "
        "asks in 'customer_questions', then address each one in "
        "'questions_addressed' with a short answer summary. A request the "
        "customer states as a fact (e.g. 'we're returning it Friday') is "
        "not a question and does not belong in this list.",
        "Write 'reply_body' as the actual customer-facing email you would "
        "send — plain, direct, no internal jargon, no clause ids written "
        "out as bare codes (spell out what the policy says in plain "
        "language; you may still mention it is 'our policy').",
    ],
    "commitment_types": config.COMMITMENT_TYPES,
    "commitment_types_requiring_citation": sorted(config.COMMITMENT_TYPES_REQUIRING_CITATION),
    "prior_commitment_treatments": config.PRIOR_COMMITMENT_TREATMENTS,
    "return_format": {
        "description": (
            "Return a single JSON object for this one email (when "
            "drafting runs in a batch, return a JSON array of such "
            "objects, one per email, in the same order as the batch's "
            "'tasks' list)."
        ),
        "schema": {
            "email_id": "string, must match the task's email_id",
            "reply_body": "string: the full customer-facing reply text",
            "commitments": [
                {
                    "description": "string: plain description of what "
                                    "this commitment does",
                    "type": "one of: " + ", ".join(config.COMMITMENT_TYPES),
                    "clause_id": "string 'H-NN' or null — required for "
                                 "refusal / waiver_or_discount / correction",
                    "discount_pct": "number (0-1) or null — only for "
                                     "waiver_or_discount commitments that "
                                     "grant a percentage discount",
                }
            ],
            "customer_questions": ["string: one entry per distinct "
                                    "question the customer's email asks"],
            "questions_addressed": [
                {
                    "question": "string, matching one customer_questions "
                                 "entry",
                    "answered": "boolean",
                    "answer_summary": "string: short summary of the "
                                       "answer given in reply_body",
                }
            ],
            "prior_commitments_reviewed": [
                {
                    "source_message_index": "integer: the thread "
                                             "history message's index",
                    "staff_name": "string: that message's staff_name",
                    "commitment_summary": "string: what that message "
                                           "committed to, in your own "
                                           "words (or 'no commitment' if "
                                           "it was a routine "
                                           "acknowledgement)",
                    "treatment": "one of: " + ", ".join(config.PRIOR_COMMITMENT_TREATMENTS),
                },
            ],
        },
        "note": (
            "prior_commitments_reviewed must contain exactly one entry "
            "per staff message in the thread_history given to you, in "
            "the same order, covering all of them — this is checked "
            "mechanically downstream."
        ),
    },
}


# ---------------------------------------------------------------------------
# Loading Phase 5 stage-1 output (classify results) — read-only.
# ---------------------------------------------------------------------------

def load_classify_raw(partial: bool) -> dict[str, dict]:
    """Load every classified email's {intent_class, rationale} from
    data/pipeline/classify_raw/batch_NN.json. Returns {email_id: response}.
    """
    raw_dir = config.CLASSIFY_RAW_DIR
    if not raw_dir.exists():
        raise SystemExit(
            f"[build_draft_tasks] ERROR: {raw_dir} does not exist. The "
            "classify agent has not run yet (Phase 5, stage 1) — this is "
            "expected before that separate LLM run happens. "
            "Nothing to build draft tasks from."
        )

    responses: dict[str, dict] = {}
    missing_batches = []
    batch_paths = sorted(raw_dir.glob("batch_*.json"))
    if not batch_paths:
        raise SystemExit(
            f"[build_draft_tasks] ERROR: {raw_dir} exists but contains no "
            "batch_*.json files."
        )

    expected_batch_ids = {p.stem for p in sorted(config.CLASSIFY_BATCHES_DIR.glob("batch_*.json"))}
    found_batch_ids = {p.stem for p in batch_paths}
    for batch_id in sorted(expected_batch_ids - found_batch_ids):
        missing_batches.append(f"{batch_id}.json")

    for path in batch_paths:
        try:
            batch = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(
                f"[build_draft_tasks] ERROR: {path} is not valid JSON "
                f"({exc}). Fix or re-run this batch before continuing."
            ) from exc
        # A batch's raw output may be a bare JSON array (per the contract's
        # return_format) or wrapped in {"results": [...]}; accept both so a
        # agent's natural response shape is not needlessly rejected.
        entries = batch if isinstance(batch, list) else batch.get("results", batch.get("tasks", []))
        for entry in entries:
            responses[entry["email_id"]] = entry

    if missing_batches and not partial:
        raise SystemExit(
            "[build_draft_tasks] ERROR: missing "
            f"{len(missing_batches)} classify batch file(s) under "
            f"data/pipeline/classify_raw/: {missing_batches}. Re-run with "
            "--partial to build draft tasks only for the emails already "
            "classified, or supply the missing batches."
        )
    if missing_batches:
        log(f"--partial: proceeding without {len(missing_batches)} "
            f"missing batch(es): {missing_batches}")

    return responses


# ---------------------------------------------------------------------------
# Draft task construction.
# ---------------------------------------------------------------------------

def render_thread_history_message(message: dict) -> dict:
    if message["sender"] == "customer":
        return {
            "index": message["index"],
            "sender": "customer",
            "date": message["date"],
            "subject": message["subject"],
            "body": message["body"],
        }
    return {
        "index": message["index"],
        "sender": "staff",
        "staff_name": message["staff_name"],
        "staff_role": message["staff_role"],
        "date": message["date"],
        "subject": message["subject"],
        "body": message["body"],
    }


def build_task(
    email: dict,
    intent_class: str,
    thread_history: list[dict],
    handbook_clauses: list[dict],
    customer_record: dict,
) -> dict:
    return {
        "email_id": email["email_id"],
        "thread_id": email["thread_id"],
        "customer_id": email["customer_id"],
        "intent_class": intent_class,
        "trigger_email": {
            "date": email["date"],
            "subject": email["subject"],
            "body": email["body"],
        },
        "thread_history": [render_thread_history_message(m) for m in thread_history],
        "customer_record": {
            "name": customer_record["name"],
            "type": customer_record["type"],
            "city": customer_record["city"],
            "repeat_customer": bool(customer_record["repeat_customer"]),
            "account_since_year": int(customer_record["account_since_year"]),
            "open_rentals": int(customer_record["open_rentals"]),
            "history_summary": customer_record["history_summary"],
        },
        "policy_handbook": handbook_clauses,
        "discount_authority_table": config.ROLE_DISCOUNT_LIMITS,
        "draft_contract": DRAFT_CONTRACT,
    }


# ---------------------------------------------------------------------------
# Self-validation.
# ---------------------------------------------------------------------------

def validate_outputs(draft_email_ids: list[str]) -> None:
    log("=== self-validation: draft tasks ===")

    tasks_dir = config.DRAFT_TASKS_DIR
    task_files = sorted(tasks_dir.glob("task_EML-*.json"))
    check(
        len(task_files) == len(draft_email_ids),
        f"draft_tasks has exactly {len(draft_email_ids)} task files "
        f"(got {len(task_files)})",
    )

    bad_email_id = 0
    missing_review_note = 0
    for email_id in draft_email_ids:
        path = tasks_dir / f"task_{email_id}.json"
        if not path.exists():
            bad_email_id += 1
            continue
        task = json.loads(path.read_text(encoding="utf-8"))
        if task.get("email_id") != email_id:
            bad_email_id += 1
        if "note" not in task.get("draft_contract", {}).get("return_format", {}):
            missing_review_note += 1

    check(bad_email_id == 0,
          f"every draft task file's email_id matches its filename and "
          f"exists (got {bad_email_id} mismatched/missing)")
    check(missing_review_note == 0,
          "every draft task carries the prior_commitments_reviewed "
          f"completeness note (got {missing_review_note} missing it)")

    batches_dir = config.DRAFT_BATCHES_DIR
    batch_files = sorted(batches_dir.glob("batch_*.json"))
    expected_batch_count = -(-len(draft_email_ids) // config.DRAFT_BATCH_SIZE) if draft_email_ids else 0
    check(
        len(batch_files) == expected_batch_count,
        f"draft_batches has exactly {expected_batch_count} batch files "
        f"(got {len(batch_files)})",
    )

    seen_in_batches: list[str] = []
    for batch_path in batch_files:
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        seen_in_batches += [t["email_id"] for t in batch["tasks"]]
    check(
        sorted(seen_in_batches) == sorted(draft_email_ids),
        "every non-escalate classified email appears exactly once across "
        "all draft batches, and no others do",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--partial", action="store_true",
        help="build draft tasks only for emails whose classify batch is "
             "present, instead of erroring on any missing batch",
    )
    args = parser.parse_args()

    log("08 Inbox — Phase 4 pipeline, stage 2: draft task builder")

    log("loading classify results from data/pipeline/classify_raw/")
    classify_responses = load_classify_raw(args.partial)
    log(f"loaded {len(classify_responses)} classify result(s)")

    log("loading emails, thread prose, policy handbook, customer register")
    emails = retrieval.load_all_emails()
    threads = retrieval.load_all_threads_prose()
    handbook_clauses = retrieval.load_policy_handbook()
    register = retrieval.load_customer_register()

    bad_intent_class = 0
    for email_id, response in classify_responses.items():
        if response.get("email_id", email_id) != email_id:
            bad_intent_class += 1
        if response.get("intent_class") not in config.ALL_INTENT_CLASSES:
            bad_intent_class += 1
    check(
        bad_intent_class == 0,
        f"every classify response names a valid, recognised intent class "
        f"(got {bad_intent_class} invalid)",
    )

    # classify_results.csv: every classified email, in email_id order,
    # whether or not it goes on to get a draft task.
    classify_rows = []
    for email_id in sorted(classify_responses, key=lambda e: int(e.split("-")[1])):
        response = classify_responses[email_id]
        email = emails[email_id]
        intent_class = response["intent_class"]
        classify_rows.append({
            "email_id": email_id,
            "thread_id": email["thread_id"],
            "customer_id": email["customer_id"],
            "intent_class": intent_class,
            "rationale": response.get("rationale", ""),
            "escalate_shortcut": intent_class in config.ESCALATE_INTENT_CLASSES,
        })
    config.PIPELINE_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(classify_rows).to_csv(config.CLASSIFY_RESULTS_CSV, index=False)
    log(f"wrote {len(classify_rows)} row(s) to {config.CLASSIFY_RESULTS_CSV}")

    draft_email_ids = [
        row["email_id"] for row in classify_rows if not row["escalate_shortcut"]
    ]
    escalate_count = len(classify_rows) - len(draft_email_ids)
    log(f"{escalate_count} email(s) shortcut straight to escalate (no draft "
        f"task); {len(draft_email_ids)} proceed to drafting")

    config.DRAFT_TASKS_DIR.mkdir(parents=True, exist_ok=True)
    config.DRAFT_BATCHES_DIR.mkdir(parents=True, exist_ok=True)

    tasks_by_id: dict[str, dict] = {}
    for email_id in draft_email_ids:
        email = emails[email_id]
        thread = threads.get(email["thread_id"])
        if thread is None:
            raise SystemExit(
                f"[build_draft_tasks] ERROR: no thread_prose record found "
                f"for {email['thread_id']} (email {email_id}). "
                "data/threads_prose/ and data/emails/ have drifted apart."
            )
        thread_history = retrieval.thread_messages_before(thread, email_id)
        customer_record = retrieval.customer_record_for(email["customer_id"], register)
        intent_class = classify_responses[email_id]["intent_class"]

        task = build_task(email, intent_class, thread_history, handbook_clauses, customer_record)
        tasks_by_id[email_id] = task
        out_path = config.DRAFT_TASKS_DIR / f"task_{email_id}.json"
        out_path.write_text(json.dumps(task, indent=2, ensure_ascii=False), encoding="utf-8")

    log(f"wrote {len(tasks_by_id)} draft tasks to {config.DRAFT_TASKS_DIR}")

    batch_size = config.DRAFT_BATCH_SIZE
    n_batches = -(-len(draft_email_ids) // batch_size) if draft_email_ids else 0
    for batch_num in range(n_batches):
        start = batch_num * batch_size
        end = start + batch_size
        chunk_ids = draft_email_ids[start:end]
        batch = {
            "batch_id": f"batch_{batch_num + 1:02d}",
            "company": {
                "name": config.COMPANY["name"],
                "sector": config.COMPANY["sector"],
                "support_address": config.COMPANY["support_address"],
            },
            "draft_contract": DRAFT_CONTRACT,
            "tasks": [tasks_by_id[eid] for eid in chunk_ids],
        }
        out_path = config.DRAFT_BATCHES_DIR / f"batch_{batch_num + 1:02d}.json"
        out_path.write_text(json.dumps(batch, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"wrote {n_batches} batches to {config.DRAFT_BATCHES_DIR}")

    validate_outputs(draft_email_ids)

    if FAILURES:
        log(f"FAILED: {len(FAILURES)} check(s) did not pass — see [FAIL] lines above")
        sys.exit(1)

    log(f"done: {len(draft_email_ids)} draft tasks, {n_batches} batches, "
        "all self-validation checks passed")


if __name__ == "__main__":
    main()
