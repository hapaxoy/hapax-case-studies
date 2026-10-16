"""
08 Inbox — Phase 3 prose task builder.

Packs the 90 threads (150 email briefs, 53 in-thread staff replies) into
batch task files under data/prose_batches/, one file per batch, for a prose
agent to dramatise into real email language. Deterministic Python decides
every batching and grouping decision; the agent writes only prose text
(subject + body per message) — it may never add or remove a planted signal,
per the core generation pattern (also stated, verbatim, inside
every task file itself, so a batch is fully self-contained).

Batching unit is the THREAD, not the individual email. A thread's messages
(customer AND staff) are always written together, in one task, so that:
  - the writer sees a promise-carrying staff message and the customer's
    later redemption email in the same task, and can make the promise
    genuinely locatable in the staff reply's prose (the only place it will
    live once the corpus is assembled — see assemble_emails.py);
  - no staff reply is ever independently authored twice by two different
    batches (it would land in exactly one batch, since its thread lands in
    exactly one batch).
Threads are packed greedily, in thread_id order (THR-001..090, i.e. the
order generate_structure.py wrote them in — deterministic, not re-sorted by
date), accumulating customer-email count until adding the next thread would
push the running total past config.EMAILS_PER_BATCH_TARGET; the batch is
then closed and a new one started. A batch always gets at least one thread
even if that thread alone exceeds the target (this only happens for the one
4-customer-message thread in this corpus).

Each batch task file carries:
  - the standing corpus-prose rules (verbatim, so nothing depends on the
    agent having read this docstring);
  - the output contract / response schema (what data/emails_raw/batch_NN.json
    must contain);
  - one entry per thread in the batch: customer info, and every message in
    thread order, each carrying whatever the writer needs to dramatise it
    (a customer message's brief fields: intent_class, trap_type, facts,
    tone_notes; a staff message's identity, and — if this is the message
    immediately after a customer's "setup" ask in one of the six
    prior-promise threads — the full planted `promise` block plus an
    explicit instruction to dramatise it into a plain, unambiguous promise
    in that staff member's own voice; every other staff message gets a
    generic non-committal-acknowledgement instruction instead, so the agent
    never invents an unplanted commitment).

This script makes no LLM calls and writes only to data/prose_batches/ — it
never touches data/threads/, data/email_briefs/, or data/answer_key/ (all
read-only inputs here) and never creates data/emails_raw/ (that directory is
the future prose agents' output, not this script's).

Run: python build_prose_tasks.py
"""

from __future__ import annotations

import json

import config


def log(message: str) -> None:
    print(f"[build_prose_tasks] {message}", flush=True)


# ---------------------------------------------------------------------------
# Standing corpus-prose rules — stated here verbatim so every task file is
# self-contained; a prose agent processing one batch never needs to read
# config.py or any other batch to know the rules.
# ---------------------------------------------------------------------------

CORPUS_PROSE_RULES = [
    "You may never add or remove a planted signal. Every fact given in a "
    "message's 'facts' block (an amount, a percentage, an equipment name, a "
    "clause reference id, a promise) must be dramatised into the prose "
    "somewhere findable; you may not invent additional facts, numbers, "
    "dates, promises, or commitments beyond what is given.",
    "Email language must read like real Finnish B2B (and, for consumer "
    "accounts, plain Finnish consumer) correspondence written in English — "
    "direct, plainly worded, occasionally slightly non-native in a "
    "realistic way (a mildly unusual preposition, a slightly formal "
    "register), never a caricature of Finnish English. It must never read "
    "as LLM-flavoured: no 'I hope this email finds you well', no bullet-"
    "point recaps of the customer's own message, no over-apologising, no "
    "corporate throat-clearing before the actual content.",
    "Human quirks are fine — a typo-free but slightly brusque tone, a short "
    "one-line email, a customer who forgets to say which booking they mean "
    "(when the brief says so). Mannered, over-polished, or greeting-card "
    "prose is never fine.",
    "Follow the register and persona hints given exactly: a business "
    "customer's email reads like it was dictated between site tasks; a "
    "consumer customer's email can be a little more casual. Follow each "
    "message's 'tone_notes' field exactly, including its instruction that "
    "the word 'fraud' must never appear anywhere in the correspondence.",
    "Never write any of the pipeline's own internal vocabulary into a "
    "message: no clause ids in the internal 'H-NN' handbook-code format, no "
    "trap-type or intent-class names (e.g. 'prior_promise_contradiction', "
    "'above_authority_discount', 'auto_send', 'human_queue', 'escalate' as "
    "a routing verdict, 'PROM-0N' promise ids), and no reference to "
    "'the answer key', 'the trap', or this being a test or synthetic "
    "scenario. Customers and staff talk about their actual rental "
    "business, in plain language, never about the pipeline that will "
    "later read their email.",
    "A staff message's 'promise' block, when present, is dramatisation "
    "guidance only — it must never appear as structured text or be quoted "
    "verbatim as a label. Turn its 'description' into a plain, "
    "unambiguous promise in the named staff member's own voice. Do not "
    "hedge it, qualify it away, or resolve the tension in 'naive_denial_note' "
    "— that field is there so you understand why the promise matters, not "
    "so you write about it.",
    "A staff message with no 'promise' block is a routine acknowledgement: "
    "confirm receipt, give a short routine update, or ask one clarifying "
    "question if natural — never invent a new commitment, discount, "
    "waiver, or exception of your own.",
    "Every message needs a short, plausible subject line consistent with "
    "its position in the thread (the first message in a thread sets the "
    "subject; later messages in the same thread normally keep it, "
    "optionally with a 'Re:' prefix, unless the brief clearly changes the "
    "topic).",
    "Dates and timestamps are already fixed by the structural data and are "
    "given for your reference only — never invent, restate as prose, or "
    "alter them; do not put a date inside the email body unless a real "
    "person would naturally write one in that context (e.g. citing a "
    "booking's own start date, not the date the email itself was sent).",
    "Customer emails are signed with the customer's own name (or a "
    "first-name/informal sign-off, whichever reads naturally for that "
    "account); staff emails are signed with the given staff member's name "
    "and, optionally, their role.",
]

OUTPUT_CONTRACT = {
    "instructions": (
        "For every thread in this batch's 'threads' list, write prose for "
        "every message in its 'messages' list, in order. A message with "
        "sender 'customer' is an inbound email from that thread's customer; "
        "dramatise its 'facts', 'intent_class'/'trap_type' framing (for "
        "your understanding of what must be true of the email, never to be "
        "named in the prose itself), and 'tone_notes'. A message with "
        "sender 'staff' is Haapaharju Oy's prior reply, already sent, that "
        "the customer would have received before writing their next "
        "message in the thread — write it as that prior reply, following "
        "its 'writer_note' (either dramatise the given 'promise' plainly, "
        "or write a routine, non-committal acknowledgement if there is no "
        "'promise' block). Follow the standing 'corpus_prose_rules' in this "
        "file exactly for every message you write."
    ),
    "return_format": {
        "description": (
            "Return a single JSON array, one object per thread in this "
            "batch's 'threads' list, in the same order, each with the "
            "thread's messages written out in the same order given."
        ),
        "schema": {
            "thread_id": "string, must match the task thread's thread_id",
            "messages": [
                {
                    "message_index": "integer, must match the task "
                                      "message's message_index",
                    "sender": "'customer' or 'staff', must match the task "
                              "message's sender",
                    "email_id": "string: the task message's email_id if it "
                                 "has one (customer messages only), "
                                 "otherwise omit this key",
                    "subject": "string: the email's subject line",
                    "body": "string: the full email body text, plain "
                            "prose, no markdown formatting, no placeholder "
                            "brackets",
                }
            ],
        },
    },
}


# ---------------------------------------------------------------------------
# Loading structural inputs (read-only)
# ---------------------------------------------------------------------------

def load_threads() -> list[dict]:
    threads = []
    for path in sorted(
        config.THREADS_DIR.glob("thread_*.json"),
        key=lambda p: int(p.stem.split("_")[1]),
    ):
        threads.append(json.loads(path.read_text(encoding="utf-8")))
    return threads


def load_briefs() -> dict[str, dict]:
    briefs = {}
    for path in sorted(config.EMAIL_BRIEFS_DIR.glob("brief_*.json")):
        brief = json.loads(path.read_text(encoding="utf-8"))
        briefs[brief["email_id"]] = brief
    return briefs


# ---------------------------------------------------------------------------
# Per-thread task message construction
# ---------------------------------------------------------------------------

def build_task_message(msg: dict, briefs: dict[str, dict]) -> dict:
    """Build one message's task entry — everything a writer needs to
    dramatise it, without any pipeline-internal labels beyond what the
    corpus_prose_rules explicitly tell the writer never to reproduce.
    """
    if msg["sender"] == "customer":
        brief = briefs[msg["email_id"]]
        return {
            "message_index": msg["index"],
            "sender": "customer",
            "email_id": msg["email_id"],
            "date": msg["date"],
            "timestamp": msg["timestamp"],
            "position_in_thread": brief["position_in_thread"],
            "thread_customer_message_count": brief["thread_customer_message_count"],
            "intent_class": brief["intent_class"],
            "trap_type": brief["trap_type"],
            "facts": brief["facts"],
            "tone_notes": brief["tone_notes"],
        }

    # Staff message.
    task_message = {
        "message_index": msg["index"],
        "sender": "staff",
        "staff_id": msg["staff_id"],
        "staff_name": msg["staff_name"],
        "staff_role": msg["staff_role"],
        "date": msg["date"],
        "timestamp": msg["timestamp"],
    }
    if "promise" in msg:
        task_message["promise"] = msg["promise"]
        task_message["writer_note"] = (
            f"This is the planted staff promise for the thread's later "
            f"prior-promise trap. Dramatise it plainly in {msg['staff_name']}'s "
            "own voice, as a genuine commitment the customer can rely on — "
            "not hedged, not walked back. Do not name the promise_id or "
            "quote any field of this block as a label."
        )
    else:
        task_message["writer_note"] = (
            "Routine staff acknowledgement — confirm receipt or give a "
            "short routine update. Do not invent a new commitment, "
            "discount, waiver, or exception; this message plants no signal "
            "of its own."
        )
    return task_message


def build_task_thread(thread: dict, briefs: dict[str, dict]) -> dict:
    customer_msg = next(m for m in thread["messages"] if m["sender"] == "customer")
    return {
        "thread_id": thread["thread_id"],
        "customer": {
            "customer_id": thread["customer_id"],
            "name": thread["customer_name"],
            # type/history are on config.CUSTOMERS, not the thread file —
            # look them up so the task is self-contained without requiring
            # the writer to cross-reference the customer register.
            **_customer_context(thread["customer_id"]),
        },
        "is_promise_thread": thread["is_promise_thread"],
        "messages": [build_task_message(m, briefs) for m in thread["messages"]],
    }


_CUSTOMER_LOOKUP = {c["customer_id"]: c for c in config.CUSTOMERS}


def _customer_context(customer_id: str) -> dict:
    c = _CUSTOMER_LOOKUP[customer_id]
    return {
        "type": c["type"],
        "city": c["city"],
        "repeat_customer": c["repeat"],
        "history_summary": c["history_summary"],
    }


# ---------------------------------------------------------------------------
# Batching — whole threads, greedy pack to ~EMAILS_PER_BATCH_TARGET customer
# emails per batch, thread_id order, never splitting a thread.
# ---------------------------------------------------------------------------

def pack_threads_into_batches(threads: list[dict]) -> list[list[dict]]:
    batches: list[list[dict]] = []
    current_batch: list[dict] = []
    current_email_count = 0

    for thread in threads:
        thread_email_count = sum(1 for m in thread["messages"] if m["sender"] == "customer")
        if current_batch and current_email_count + thread_email_count > config.EMAILS_PER_BATCH_TARGET:
            batches.append(current_batch)
            current_batch = []
            current_email_count = 0
        current_batch.append(thread)
        current_email_count += thread_email_count

    if current_batch:
        batches.append(current_batch)

    return batches


def main() -> None:
    log("08 Inbox — Phase 3 prose task builder")

    log("loading thread skeletons and email briefs")
    threads = load_threads()
    briefs = load_briefs()

    if len(threads) != config.TARGET_THREAD_COUNT:
        raise SystemExit(
            f"[build_prose_tasks] ERROR: found {len(threads)} thread files, "
            f"expected {config.TARGET_THREAD_COUNT}. Run generate_structure.py "
            "and validate_structure.py first."
        )
    if len(briefs) != config.TOTAL_EMAILS:
        raise SystemExit(
            f"[build_prose_tasks] ERROR: found {len(briefs)} brief files, "
            f"expected {config.TOTAL_EMAILS}. Run generate_structure.py and "
            "validate_structure.py first."
        )

    log("packing threads into batches (whole threads only, "
        f"target {config.EMAILS_PER_BATCH_TARGET} customer emails/batch)")
    batches = pack_threads_into_batches(threads)

    config.PROSE_BATCHES_DIR.mkdir(parents=True, exist_ok=True)

    total_emails_written = 0
    total_staff_messages_written = 0
    for batch_num, batch_threads in enumerate(batches, start=1):
        task_threads = [build_task_thread(t, briefs) for t in batch_threads]
        n_emails = sum(
            1 for th in task_threads for m in th["messages"] if m["sender"] == "customer"
        )
        n_staff = sum(
            1 for th in task_threads for m in th["messages"] if m["sender"] == "staff"
        )
        n_promises = sum(
            1 for th in task_threads for m in th["messages"]
            if m["sender"] == "staff" and "promise" in m
        )
        total_emails_written += n_emails
        total_staff_messages_written += n_staff

        batch = {
            "batch_id": f"batch_{batch_num:02d}",
            "company": {
                "name": config.COMPANY["name"],
                "sector": config.COMPANY["sector"],
                "hq_city": config.COMPANY["hq_city"],
                "branches": config.COMPANY["branches"],
                "domain": config.COMPANY["domain"],
                "support_address": config.COMPANY["support_address"],
                "business_mix": config.COMPANY["business_mix"],
            },
            "corpus_prose_rules": CORPUS_PROSE_RULES,
            "output_contract": OUTPUT_CONTRACT,
            "thread_count": len(task_threads),
            "customer_email_count": n_emails,
            "staff_message_count": n_staff,
            "planted_promise_count": n_promises,
            "threads": task_threads,
        }
        out_path = config.PROSE_BATCHES_DIR / f"batch_{batch_num:02d}.json"
        out_path.write_text(json.dumps(batch, indent=2, ensure_ascii=False), encoding="utf-8")
        log(f"wrote {out_path.name}: {len(task_threads)} threads, {n_emails} customer "
            f"emails, {n_staff} staff messages ({n_promises} planted promises)")

    log(f"done: {len(batches)} batch files, {total_emails_written} customer emails, "
        f"{total_staff_messages_written} staff messages "
        f"({total_emails_written + total_staff_messages_written} messages total) "
        f"written to {config.PROSE_BATCHES_DIR}")

    if total_emails_written != config.TOTAL_EMAILS:
        raise SystemExit(
            f"[build_prose_tasks] ERROR: batches carry {total_emails_written} customer "
            f"emails, expected {config.TOTAL_EMAILS} — a thread was dropped or double-"
            "counted. This is a bug in pack_threads_into_batches, not a judgment call."
        )


if __name__ == "__main__":
    main()
