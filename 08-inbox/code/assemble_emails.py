"""
08 Inbox — Phase 3 prose assembly.

Reads `data/emails_raw/batch_NN.json` — the prose agents' filled-in
responses to the tasks `build_prose_tasks.py` wrote, same batch/thread/
message-index conventions — and produces the two canonical, pipeline-facing
corpus shapes that Phase 4 will read:

  data/emails/email_NNN.json      — one flat record per inbound customer
                                     email (EML-001..150), the "current
                                     email" Phase 4's classify/draft steps
                                     read.
  data/threads_prose/thread_NNN.json
                                   — the full thread history with prose,
                                     matching data/threads/thread_NNN.json's
                                     structure and message order, but with
                                     every ground-truth-only field stripped
                                     and every message's subject/body added.
                                     This is what Phase 4's "retrieve: the
                                     full thread history" step reads — the
                                     promise-memory mechanism now lives
                                     ENTIRELY in this prose (the structured
                                     `promise` block is deliberately not
                                     carried over — see "Design decisions"
                                     below), so a pipeline step reading this
                                     file gets no more information than a
                                     human agent opening the real thread
                                     would.
  data/emails/prose_manifest.csv  — one row per assembled email: batch
                                     source, subject/body lengths, thread
                                     position. A build QA aid, not read by
                                     anything downstream.

Design decisions (flagged here, since the pipeline design does not
spell out Phase 3's file shapes):
  - The canonical corpus strips `intent_class`, `trap_type`, `facts`, and
    the staff `promise` block from every message. Carrying these into the
    files Phase 4 reads would hand the pipeline's classify step (and the
    consistency gate) the answer directly — the whole point of Phase 4 is
    that the pipeline must recover intent and prior commitments from the
    prose alone, the way a human agent reading the inbox would. The
    ground-truth fields stay exactly where they already lived
    (data/email_briefs/, data/threads/, data/answer_key/) for marking.
  - Batching unit is the thread (see build_prose_tasks.py), so this script
    also assembles by thread and then explodes into individual email files.

This script makes no LLM calls and never reads data/answer_key/ — content
QA (planted signals locatable, no leaked vocabulary) is a separate, later
script, validate_emails.py.

`data/emails_raw/` is written by the prose agents, a separate LLM step
outside this script. Run this script with
--partial once some batches exist to assemble what's available; without
--partial, any missing batch is an informative error, not a silent partial
corpus (mirrors the churn case's assemble_tickets.py and Case 10's
assemble_dossiers.py conventions).

Run: python assemble_emails.py [--partial]
Then: python validate_emails.py   (must exit 0)
"""

from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

import config


def log(message: str) -> None:
    print(f"[assemble_emails] {message}", flush=True)


FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)
        print(f"[FAIL] {message}", flush=True)
    else:
        print(f"[ok]   {message}", flush=True)


# ---------------------------------------------------------------------------
# Loading raw prose output
# ---------------------------------------------------------------------------

def expected_batch_count() -> int:
    """Number of batch files build_prose_tasks.py wrote, discovered from
    data/prose_batches/ itself rather than re-deriving the packing (the task
    files are the single source of truth for how many batches exist).
    """
    if not config.PROSE_BATCHES_DIR.exists():
        raise SystemExit(
            f"[assemble_emails] ERROR: {config.PROSE_BATCHES_DIR} does not "
            "exist. Run build_prose_tasks.py first."
        )
    return len(list(config.PROSE_BATCHES_DIR.glob("batch_*.json")))


def load_task_batches() -> dict[str, dict]:
    """Load the original task files, keyed by batch_id, so assembly can
    check the writer's response against exactly what was asked for (thread
    set, message set, message order) rather than trusting the response's
    own shape.
    """
    tasks = {}
    for path in sorted(config.PROSE_BATCHES_DIR.glob("batch_*.json")):
        task = json.loads(path.read_text(encoding="utf-8"))
        tasks[task["batch_id"]] = task
    return tasks


def load_raw_prose(partial: bool, n_batches: int) -> dict[str, list[dict]]:
    """Load every batch's raw prose response from data/emails_raw/.
    Returns {batch_id: [thread_response, ...]}.
    """
    raw_dir = config.EMAILS_RAW_DIR
    responses: dict[str, list[dict]] = {}
    missing_batches = []

    if not raw_dir.exists():
        raise SystemExit(
            f"[assemble_emails] ERROR: {raw_dir} does not exist. Prose "
            "agents have not run yet — this is expected before Phase 3's "
            "prose batches are run. Nothing to "
            "assemble."
        )

    for batch_num in range(1, n_batches + 1):
        batch_id = f"batch_{batch_num:02d}"
        path = raw_dir / f"{batch_id}.json"
        if not path.exists():
            missing_batches.append(path.name)
            continue
        try:
            responses[batch_id] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(
                f"[assemble_emails] ERROR: {path} is not valid JSON ({exc}). "
                "Fix or re-run this batch before continuing."
            ) from exc

    if missing_batches and not partial:
        raise SystemExit(
            f"[assemble_emails] ERROR: missing {len(missing_batches)} prose "
            f"batch file(s) under {raw_dir}: {missing_batches}. Re-run with "
            "--partial to assemble the corpus only for the threads already "
            "written, or supply the missing batches."
        )
    if missing_batches:
        log(f"--partial: proceeding without {len(missing_batches)} missing "
            f"batch(es): {missing_batches}")

    return responses


# ---------------------------------------------------------------------------
# Structural loading (the read-only Phase 2 outputs, for cross-checks)
# ---------------------------------------------------------------------------

def load_structural_threads() -> dict[str, dict]:
    threads = {}
    for path in sorted(config.THREADS_DIR.glob("thread_*.json")):
        thread = json.loads(path.read_text(encoding="utf-8"))
        threads[thread["thread_id"]] = thread
    return threads


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def assemble_batch(
    batch_id: str,
    task: dict,
    response_threads: list[dict],
    structural_threads: dict[str, dict],
    manifest_rows: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Returns (email_records, thread_prose_records) for every thread this
    batch's response actually covers.
    """
    email_records = []
    thread_prose_records = []

    response_by_thread_id = {r["thread_id"]: r for r in response_threads}

    for task_thread in task["threads"]:
        thread_id = task_thread["thread_id"]
        response_thread = response_by_thread_id.get(thread_id)
        if response_thread is None:
            check(False, f"{batch_id}: no response for thread {thread_id}")
            continue

        response_msgs_by_index = {m["message_index"]: m for m in response_thread.get("messages", [])}
        structural_thread = structural_threads.get(thread_id)
        if structural_thread is None:
            check(False, f"{batch_id}: thread {thread_id} not found in data/threads/")
            continue

        prose_messages = []
        thread_ok = True
        for task_msg in task_thread["messages"]:
            idx = task_msg["message_index"]
            response_msg = response_msgs_by_index.get(idx)
            if response_msg is None:
                check(False, f"{batch_id}/{thread_id}: no response for message_index {idx}")
                thread_ok = False
                continue
            if response_msg.get("sender") != task_msg["sender"]:
                check(False, f"{batch_id}/{thread_id} msg {idx}: sender mismatch "
                              f"(task {task_msg['sender']!r}, response {response_msg.get('sender')!r})")
                thread_ok = False

            subject = (response_msg.get("subject") or "").strip()
            body = (response_msg.get("body") or "").strip()
            if not subject or not body:
                check(False, f"{batch_id}/{thread_id} msg {idx}: empty subject or body")
                thread_ok = False

            prose_msg = {
                "index": idx,
                "sender": task_msg["sender"],
                "date": task_msg["date"],
                "timestamp": task_msg["timestamp"],
                "subject": subject,
                "body": body,
            }
            if task_msg["sender"] == "staff":
                prose_msg["staff_id"] = task_msg["staff_id"]
                prose_msg["staff_name"] = task_msg["staff_name"]
                prose_msg["staff_role"] = task_msg["staff_role"]
            else:
                prose_msg["email_id"] = task_msg["email_id"]
            prose_messages.append(prose_msg)

            manifest_rows.append({
                "batch_id": batch_id,
                "thread_id": thread_id,
                "message_index": idx,
                "sender": task_msg["sender"],
                "email_id": task_msg.get("email_id", ""),
                "subject_chars": len(subject),
                "body_chars": len(body),
                "body_words": len(body.split()),
            })

            if task_msg["sender"] == "customer":
                email_records.append({
                    "email_id": task_msg["email_id"],
                    "thread_id": thread_id,
                    "customer_id": task_thread["customer"]["customer_id"],
                    "customer_name": task_thread["customer"]["name"],
                    "position_in_thread": task_msg["position_in_thread"],
                    "thread_customer_message_count": task_msg["thread_customer_message_count"],
                    "date": task_msg["date"],
                    "timestamp": task_msg["timestamp"],
                    "subject": subject,
                    "body": body,
                })

        if not thread_ok:
            continue

        thread_prose_records.append({
            "thread_id": thread_id,
            "customer_id": task_thread["customer"]["customer_id"],
            "customer_name": task_thread["customer"]["name"],
            "is_promise_thread": task_thread["is_promise_thread"],
            "messages": prose_messages,
        })

    return email_records, thread_prose_records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partial", action="store_true",
                         help="assemble the corpus only for threads whose "
                              "prose batch is present, instead of erroring "
                              "on any missing batch")
    args = parser.parse_args()

    log("08 Inbox — Phase 3 prose assembly")

    n_batches = expected_batch_count()
    log(f"found {n_batches} prose task batch file(s)")

    tasks = load_task_batches()
    structural_threads = load_structural_threads()

    log("loading raw prose responses from data/emails_raw/")
    raw = load_raw_prose(args.partial, n_batches)
    log(f"loaded {len(raw)} of {n_batches} batch response(s)")

    config.EMAILS_DIR.mkdir(parents=True, exist_ok=True)
    config.THREADS_PROSE_DIR.mkdir(parents=True, exist_ok=True)

    all_email_records: list[dict] = []
    all_thread_records: list[dict] = []
    manifest_rows: list[dict] = []

    for batch_id in sorted(raw.keys()):
        task = tasks.get(batch_id)
        if task is None:
            check(False, f"{batch_id}: no matching task file in data/prose_batches/")
            continue
        email_records, thread_records = assemble_batch(
            batch_id, task, raw[batch_id], structural_threads, manifest_rows,
        )
        all_email_records.extend(email_records)
        all_thread_records.extend(thread_records)

    for record in all_email_records:
        num = int(record["email_id"].split("-")[1])
        path = config.EMAILS_DIR / f"email_{num:03d}.json"
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"wrote {len(all_email_records)} email file(s) to {config.EMAILS_DIR}")

    for record in all_thread_records:
        num = int(record["thread_id"].split("-")[1])
        path = config.THREADS_PROSE_DIR / f"thread_{num:03d}.json"
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"wrote {len(all_thread_records)} thread-with-prose file(s) to {config.THREADS_PROSE_DIR}")

    manifest_path = config.EMAILS_DIR / "prose_manifest.csv"
    pd.DataFrame(manifest_rows).to_csv(manifest_path, index=False)
    log(f"wrote prose manifest ({len(manifest_rows)} rows) to {manifest_path}")

    if not args.partial and len(all_email_records) != config.TOTAL_EMAILS:
        check(False, f"assembled {len(all_email_records)} emails, expected "
                      f"{config.TOTAL_EMAILS} (run without --partial only "
                      "once every batch is present)")

    if FAILURES:
        print(f"\n{len(FAILURES)} assembly problem(s) found — see [FAIL] lines above.")
        sys.exit(1)

    log("assembly complete with no structural problems. Run validate_emails.py next.")


if __name__ == "__main__":
    main()
