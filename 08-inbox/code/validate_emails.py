"""
08 Inbox — Phase 3 prose coherence validator.

Every coherence rule below corresponds to a hard requirement, either stated
directly in the case design, carried over from validate_structure.py's
Phase 2 rules (which this script does not re-check — those already passed),
or implied by the prose-agent contract in build_prose_tasks.py ("may never
add or remove a planted signal"; no leaked pipeline vocabulary). A corpus
that fails this script is a bug, not a judgment call — it exits 1 on ANY
failure, the same convention as validate_structure.py.

Checks:
  1. Completeness: every EML-001..150 has an assembled email file; every
     thread has an assembled thread-with-prose file whose message set
     (index, sender, date, timestamp) matches data/threads/ exactly.
  2. Non-trivial prose: every subject and body is non-empty and above a
     minimum length (catches a degenerate or truncated writer response).
  3. Planted signals are locatable: for every trap type, the facts the
     brief planted (an amount, a percentage, a rental reference, a
     scenario) are actually findable — verbatim for numeric/code facts,
     keyword-matched for descriptive facts — in the corresponding email or
     staff-reply body. This is the corpus-level version of "the writer may
     never add or remove a planted signal."
  4. Prior-promise integrity in prose: for each of the 6 prior-promise
     threads, the staff reply immediately preceding the trap email
     genuinely carries the planted promise in its prose (keyword-matched by
     promise kind) — this is now the ONLY place the promise lives, since
     assemble_emails.py deliberately drops the structured `promise` block
     from the pipeline-facing corpus.
  5. No leaked answer-key vocabulary: no trap-type or intent-class machine
     token, no route-label token, no internal clause-id code (H-NN), no
     promise-id code (PROM-0N), no literal reference to "the answer key" or
     "the trap", and never the word "fraud" (the design's own rule),
     anywhere in the assembled prose.
  6. Thread chronology is coherent: message dates/timestamps strictly
     increase within a thread (re-checked independently on the assembled
     prose files, not assumed from Phase 2's validation).
  7. Name consistency with structure: every assembled thread's customer_id/
     name and every staff message's staff_id/name/role match the customer
     register / config.STAFF exactly — no drift introduced during assembly.

Run: python validate_emails.py
Exit 0 = all rules pass. Exit 1 = at least one rule failed (details printed).
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime

import config

FAILURES: list[str] = []


def fail(message: str) -> None:
    FAILURES.append(message)
    print(f"  FAIL: {message}")


def ok(message: str) -> None:
    print(f"  ok:   {message}")


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_emails() -> dict[str, dict]:
    emails = {}
    if not config.EMAILS_DIR.exists():
        return emails
    for path in sorted(config.EMAILS_DIR.glob("email_*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        emails[record["email_id"]] = record
    return emails


def load_threads_prose() -> dict[str, dict]:
    threads = {}
    if not config.THREADS_PROSE_DIR.exists():
        return threads
    for path in sorted(config.THREADS_PROSE_DIR.glob("thread_*.json")):
        thread = json.loads(path.read_text(encoding="utf-8"))
        threads[thread["thread_id"]] = thread
    return threads


def load_structural_threads() -> dict[str, dict]:
    threads = {}
    for path in sorted(config.THREADS_DIR.glob("thread_*.json")):
        thread = json.loads(path.read_text(encoding="utf-8"))
        threads[thread["thread_id"]] = thread
    return threads


def load_briefs() -> dict[str, dict]:
    briefs = {}
    for path in sorted(config.EMAIL_BRIEFS_DIR.glob("brief_*.json")):
        brief = json.loads(path.read_text(encoding="utf-8"))
        briefs[brief["email_id"]] = brief
    return briefs


# ---------------------------------------------------------------------------
# Rule 1: completeness
# ---------------------------------------------------------------------------

def check_completeness(emails: dict, threads_prose: dict, structural_threads: dict) -> None:
    print("\n[Rule 1] Completeness")

    expected_email_ids = {f"EML-{n:03d}" for n in range(1, config.TOTAL_EMAILS + 1)}
    if set(emails.keys()) != expected_email_ids:
        missing = expected_email_ids - set(emails.keys())
        fail(f"{len(missing)} email file(s) missing from data/emails/, e.g. {sorted(missing)[:5]}")
    else:
        ok(f"all {config.TOTAL_EMAILS} email files present in data/emails/")

    if set(threads_prose.keys()) != set(structural_threads.keys()):
        missing = set(structural_threads.keys()) - set(threads_prose.keys())
        extra = set(threads_prose.keys()) - set(structural_threads.keys())
        fail(f"thread-with-prose set does not match data/threads/ — missing {sorted(missing)[:5]}, "
             f"extra {sorted(extra)[:5]}")
    else:
        ok(f"all {len(structural_threads)} threads have a matching thread-with-prose file")

    message_set_bad = []
    for thread_id, structural in structural_threads.items():
        prose = threads_prose.get(thread_id)
        if prose is None:
            continue
        structural_keys = {(m["index"], m["sender"], m["date"], m["timestamp"]) for m in structural["messages"]}
        prose_keys = {(m["index"], m["sender"], m["date"], m["timestamp"]) for m in prose["messages"]}
        if structural_keys != prose_keys:
            message_set_bad.append(thread_id)
    if message_set_bad:
        fail(f"{len(message_set_bad)} thread(s) have a prose message set (index/sender/date/timestamp) "
             f"that does not match data/threads/ exactly: {message_set_bad[:5]}")
    else:
        ok("every thread-with-prose file's message set matches its structural thread exactly")


# ---------------------------------------------------------------------------
# Rule 2: non-trivial prose
# ---------------------------------------------------------------------------

# One-word subjects ("Discount", "Invoice") are inbox realism, not defects
# (relaxed from 2, 20 Sep 2026). Empty stays a fail.
MIN_SUBJECT_WORDS = 1
MIN_CUSTOMER_BODY_WORDS = 10
MIN_STAFF_BODY_WORDS = 5


def check_nontrivial_prose(threads_prose: dict) -> None:
    print("\n[Rule 2] Non-trivial prose")
    short_subjects = []
    short_bodies = []

    for thread_id, thread in threads_prose.items():
        for msg in thread["messages"]:
            subject_words = len(msg.get("subject", "").split())
            body_words = len(msg.get("body", "").split())
            if subject_words < MIN_SUBJECT_WORDS:
                short_subjects.append((thread_id, msg["index"], subject_words))
            min_body = MIN_CUSTOMER_BODY_WORDS if msg["sender"] == "customer" else MIN_STAFF_BODY_WORDS
            if body_words < min_body:
                short_bodies.append((thread_id, msg["index"], msg["sender"], body_words))

    if short_subjects:
        fail(f"{len(short_subjects)} message(s) with a subject under {MIN_SUBJECT_WORDS} words: {short_subjects[:5]}")
    else:
        ok(f"every subject line has at least {MIN_SUBJECT_WORDS} words")

    if short_bodies:
        fail(f"{len(short_bodies)} message(s) with a suspiciously short body: {short_bodies[:5]}")
    else:
        ok(f"every body meets its minimum word count (customer >= {MIN_CUSTOMER_BODY_WORDS}, "
           f"staff >= {MIN_STAFF_BODY_WORDS})")


# ---------------------------------------------------------------------------
# Rule 3: planted signals locatable
# ---------------------------------------------------------------------------
# Keyword maps below are hand-built against the exact closed sets of
# scenario/reason strings in generate_structure.py's rng.choice lists (and
# config.py's fixed scenario tables) — finite, enumerable, and the right
# thing to check against here: not "does the structure match config" (that
# is validate_structure.py's job) but "does the WRITTEN PROSE still carry
# the signal the structure planted." Falls back to a generic word-overlap
# check for any fact string not found in a map, so a future generator edit
# degrades to a looser check rather than silently skipping the rule.

def _any_keyword_hit(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(kw.lower() in lowered for kw in keywords)


def _generic_fallback_hit(text: str, fact_phrase: str) -> bool:
    """Loose fallback: at least one content word (4+ letters, not a common
    stopword) from the fact phrase appears in the text.
    """
    stopwords = {"with", "that", "this", "from", "their", "about", "which", "there", "would"}
    words = [w.strip(".,'\"()") for w in fact_phrase.lower().split()]
    candidates = [w for w in words if len(w) >= 4 and w not in stopwords]
    lowered = text.lower()
    return any(w in lowered for w in candidates)


PROMISE_KEYWORD_GROUPS = {
    "deposit_waiver": [["deposit"], ["waiv", "no deposit", "skip the deposit", "won't charge", "will not charge", "not charge", "not need"]],
    "late_fee_refund": [["late fee", "late-fee", "late return fee", "late charge"], ["refund", "credit", "reimburse", "waive", "waiv"]],
    "extended_deadline": [["extension", "extend", "extra day", "extra days", "few more days", "couple more days"]],
    "held_replacement_unit": [["hold", "reserve", "set aside", "keep it for you", "keep one for you"]],
    "free_delivery": [["delivery", "deliver"], ["free", "no charge", "waive", "waiv", "on us", "complimentary"]],
    "price_match": [["price"], ["match", "same rate", "honour", "honor"]],
}

REASON_KEYWORDS = {
    "a three-month standing hire of an excavator": ["standing hire", "three-month", "three month", "3-month"],
    "referring another company as a new account": ["referr", "new account"],
    "matching a competitor's advertised rate": ["competitor"],
    "loyalty after years as an account customer": ["loyal"],
    "a large multi-site framework booking": ["framework", "multi-site", "multi site"],
}

SAFETY_KEYWORDS = {
    "the guardrail latch on a hired scissor lift failed during use; the operator reports a fall": ["guardrail", "fall"],
    "a hired generator gave the operator an electric shock on contact with the casing": ["shock"],
    "an excavator's hydraulic hose burst under pressure, spraying fluid near the operator": ["hydraulic", "hose", "burst", "fluid"],
    "a site cabin heater is reported as a fire risk after a burning smell was noticed overnight": ["fire", "burning", "smell", "smoke"],
}

DATA_REQUEST_KEYWORDS = {
    "asks for a full export of all personal data Haapaharju holds on their account": ["export", "copy of", "all the data", "all my data", "all our data"],
    "asks for their account and personal data to be deleted entirely": ["delet", "remov", "erase"],
    "asks who has accessed their account data and for what purpose": ["access", "who has", "who's been"],
}

MISQUOTE_KEYWORDS = {
    "H-01": ["deposit", "refund"],
    "H-07": ["cosmetic", "scratch", "damage"],
    "H-10": ["late", "day", "grace"],
    "H-15": ["insurance", "damage waiver", "dwc", "cover"],
    "H-30": ["invoice", "dispute", "quer"],
}

ANGRY_KEYWORDS = {
    "H-05": ["damage", "photo", "pre-exist", "before the rental", "already there"],
    "H-14": ["cancel", "breakdown", "refund"],
    "H-24": ["fault", "unusable", "broke", "broken"],
    "H-29": ["invoice", "price"],
}

NEEDS_INFO_KEYWORDS = {
    "wants to extend 'the lift' but has two active rentals and does not say which one": ["lift", "extend"],
    "asks for 'the usual discount' without stating an amount or which booking it applies to": ["discount"],
    "reports equipment 'not working properly' with no symptom or fault detail": ["not working", "working properly", "fault", "broken"],
    "asks to move pickup to 'sometime next week' without naming a date": ["next week", "pickup", "move"],
    "requests an invoice copy without saying which invoice or period": ["invoice"],
    "asks whether 'that quote from before' is still valid without a quote reference": ["quote"],
}

ROUTINE_KEYWORDS = {
    # Widened because the prose agents legitimately dramatise these two routine
    # kinds without the literal keyword ("wondering if you've got a site
    # cabin I could rent?"), and the trap/promise/numeric checks carry the
    # signal weight for everything non-routine.
    "checking availability for a booking": [
        "availab", "in stock", "you have", "have you got", "you've got",
        "got any", "got a", "any chance", "free", "rent", "hire", "book"],
    "changing the dates on an existing booking": ["date", "reschedul", "change"],
    "asking a question about an invoice already received": ["invoice"],
    "arranging the return of equipment at the end of a rental": [
        "return", "bring", "brought", "drop", "hand back", "give back",
        "take back", "back to you", "collect"],
    "asking about delivery options for a new booking": ["deliver"],
    "requesting a repeat of a previous booking": ["repeat", "again", "same as", "previous", "before"],
}


def _equipment_hit(text: str, equipment: str) -> bool:
    lowered = text.lower()
    words = [w.strip(".,'\"()") for w in equipment.lower().split() if len(w) >= 4]
    return any(w in lowered for w in words)


def check_planted_signals(emails: dict, threads_prose: dict, briefs: dict) -> None:
    print("\n[Rule 3] Planted signals are locatable in the assembled prose")

    problems: list[tuple[str, str]] = []

    for email_id, brief in briefs.items():
        email = emails.get(email_id)
        if email is None:
            continue  # already reported by Rule 1
        # The subject line is part of the message a reader (and the pipeline)
        # sees, so a signal carried there counts as locatable ("Returning the
        # tower light" over a body that says "bring back" is dramatisation,
        # not omission). Adjusted 20 Sep 2026 after triage of the first full
        # validation run.
        body = f"{email.get('subject', '')}\n{email.get('body', '')}"
        facts = brief["facts"]
        trap_type = brief["trap_type"]

        if trap_type == "refund_denial":
            ref = facts.get("rental_reference", "")
            if ref and ref.lower() not in body.lower():
                problems.append((email_id, f"rental_reference {ref!r} not found verbatim in body"))
            amount = str(facts.get("amount_eur", ""))
            if amount and amount not in body:
                problems.append((email_id, f"amount_eur {amount!r} not found in body"))
            if not _equipment_hit(body, facts.get("equipment", "")):
                problems.append((email_id, f"equipment {facts.get('equipment')!r} not locatable in body"))

        elif trap_type == "above_authority_discount":
            pct = facts.get("requested_discount_pct")
            if pct is not None and (str(pct) not in body or "%" not in body):
                problems.append((email_id, f"requested_discount_pct {pct} not found as a percentage in body"))
            reason = facts.get("reason_given", "")
            keywords = REASON_KEYWORDS.get(reason)
            hit = _any_keyword_hit(body, keywords) if keywords else _generic_fallback_hit(body, reason)
            if not hit:
                problems.append((email_id, f"discount reason {reason!r} not locatable in body"))

        elif trap_type == "must_escalate_safety":
            scenario = facts.get("safety_scenario", "")
            keywords = SAFETY_KEYWORDS.get(scenario)
            hit = _any_keyword_hit(body, keywords) if keywords else _generic_fallback_hit(body, scenario)
            if not hit:
                problems.append((email_id, f"safety_scenario {scenario!r} not locatable in body"))

        elif trap_type == "data_request":
            kind = facts.get("data_request_kind", "")
            keywords = DATA_REQUEST_KEYWORDS.get(kind)
            hit = _any_keyword_hit(body, keywords) if keywords else _generic_fallback_hit(body, kind)
            if not hit:
                problems.append((email_id, f"data_request_kind {kind!r} not locatable in body"))

        elif trap_type == "policy_misquote":
            cid = facts.get("correcting_clause_id", "")
            keywords = MISQUOTE_KEYWORDS.get(cid)
            hit = _any_keyword_hit(body, keywords) if keywords else _generic_fallback_hit(body, facts.get("false_claim", ""))
            if not hit:
                problems.append((email_id, f"misquote for {cid} not locatable in body"))

        elif trap_type == "angry_entitled":
            cid = facts.get("favouring_clause_id", "")
            keywords = ANGRY_KEYWORDS.get(cid)
            hit = _any_keyword_hit(body, keywords) if keywords else _generic_fallback_hit(body, facts.get("grievance", ""))
            if not hit:
                problems.append((email_id, f"grievance for {cid} not locatable in body"))

        elif trap_type == "needs_info":
            ambiguity = facts.get("ambiguity", "")
            keywords = NEEDS_INFO_KEYWORDS.get(ambiguity)
            hit = _any_keyword_hit(body, keywords) if keywords else _generic_fallback_hit(body, ambiguity)
            if not hit:
                problems.append((email_id, f"ambiguity {ambiguity!r} not locatable in body"))

        elif trap_type == "none":
            # Plain routine or a promise-thread setup message.
            if "request_kind" in facts:
                kind = facts.get("request_kind", "")
                keywords = ROUTINE_KEYWORDS.get(kind)
                hit = _any_keyword_hit(body, keywords) if keywords else _generic_fallback_hit(body, kind)
                if not hit:
                    problems.append((email_id, f"request_kind {kind!r} not locatable in body"))
            # promise-thread setup messages ("setup_context") are deliberately
            # not checked here — they are a loose narrative lead-in, not a
            # numeric/code planted fact, and their real payload is the staff
            # promise checked in Rule 4.

        # prior_promise_contradiction emails' own planted fact is the
        # redemption ask referencing the promise — checked together with the
        # promise itself in Rule 4, since both live in the same thread.

    if problems:
        fail(f"{len(problems)} planted-signal(s) not locatable in the assembled prose: {problems[:8]}")
    else:
        ok(f"planted facts for all {len(briefs)} briefs are locatable in their assembled email body")


# ---------------------------------------------------------------------------
# Rule 4: prior-promise integrity in prose
# ---------------------------------------------------------------------------

def check_prior_promises_in_prose(threads_prose: dict, structural_threads: dict, briefs: dict) -> None:
    print("\n[Rule 4] Prior-promise traps carry a locatable promise in the prose")

    promise_briefs = {eid: b for eid, b in briefs.items() if b["trap_type"] == "prior_promise_contradiction"}
    problems = []
    checked = 0

    for email_id, brief in promise_briefs.items():
        thread_id = brief["thread_id"]
        structural = structural_threads.get(thread_id)
        prose = threads_prose.get(thread_id)
        if structural is None or prose is None:
            continue  # already reported by Rule 1

        # Find the planted promise's kind from the structural thread (the
        # only place `kind` still lives — assemble_emails.py strips it).
        staff_promise_msg = next(
            (m for m in structural["messages"] if m.get("sender") == "staff" and "promise" in m), None,
        )
        if staff_promise_msg is None:
            problems.append((email_id, "no planted promise found in structural thread"))
            continue
        kind = staff_promise_msg["promise"]["kind"]
        staff_index = staff_promise_msg["index"]

        prose_staff_msg = next((m for m in prose["messages"] if m["index"] == staff_index), None)
        if prose_staff_msg is None or prose_staff_msg["sender"] != "staff":
            problems.append((email_id, f"prose message at index {staff_index} is missing or not a staff message"))
            continue

        keyword_groups = PROMISE_KEYWORD_GROUPS.get(kind)
        body = prose_staff_msg.get("body", "")
        if keyword_groups is None:
            hit = _generic_fallback_hit(body, staff_promise_msg["promise"]["description"])
        else:
            hit = all(_any_keyword_hit(body, group) for group in keyword_groups)
        if not hit:
            problems.append((email_id, f"promise kind {kind!r} not locatable in the preceding staff reply's body"))
        else:
            checked += 1

    if problems:
        fail(f"{len(problems)} prior-promise trap(s) have no locatable promise in the assembled prose: {problems[:5]}")
    else:
        ok(f"all {checked} planted promises are locatable in their staff reply's prose")


# ---------------------------------------------------------------------------
# Rule 5: no leaked answer-key vocabulary
# ---------------------------------------------------------------------------

FORBIDDEN_LITERAL_TOKENS = sorted(
    set(config.TRAP_TYPES.keys())
    # "routine" and "safety" are ordinary English (a customer reporting an
    # electric shock says "safety" naturally); banning them flags realism as
    # leakage. Snake_case class tokens like must_escalate stay banned.
    | (config.ALL_INTENT_CLASSES - {"routine", "safety"})
    | {"auto_send", "human_queue", "answer_key", "answer key", "the trap", "fraud"}
)
CLAUSE_ID_PATTERN = re.compile(r"\bH-\d{2}\b")
PROMISE_ID_PATTERN = re.compile(r"\bPROM-\d{2}\b")


def check_no_leaked_vocabulary(threads_prose: dict) -> None:
    print("\n[Rule 5] No leaked answer-key vocabulary")

    literal_hits = []
    clause_hits = []
    promise_hits = []

    for thread_id, thread in threads_prose.items():
        for msg in thread["messages"]:
            text = f"{msg.get('subject', '')} {msg.get('body', '')}"
            lowered = text.lower()
            for token in FORBIDDEN_LITERAL_TOKENS:
                if token.lower() in lowered:
                    literal_hits.append((thread_id, msg["index"], token))
            if CLAUSE_ID_PATTERN.search(text):
                clause_hits.append((thread_id, msg["index"]))
            if PROMISE_ID_PATTERN.search(text):
                promise_hits.append((thread_id, msg["index"]))

    if literal_hits:
        fail(f"{len(literal_hits)} message(s) contain forbidden internal vocabulary: {literal_hits[:8]}")
    else:
        ok("no message contains a trap-type, intent-class, route-label, or 'fraud' literal")

    if clause_hits:
        fail(f"{len(clause_hits)} message(s) cite an internal handbook clause code (H-NN) verbatim: {clause_hits[:8]}")
    else:
        ok("no message cites an internal clause code (H-NN) verbatim")

    if promise_hits:
        fail(f"{len(promise_hits)} message(s) cite an internal promise code (PROM-NN) verbatim: {promise_hits[:8]}")
    else:
        ok("no message cites an internal promise code (PROM-NN) verbatim")


# ---------------------------------------------------------------------------
# Rule 6: thread chronology
# ---------------------------------------------------------------------------

def check_thread_chronology(threads_prose: dict) -> None:
    print("\n[Rule 6] Thread timestamps strictly ordered (re-checked on assembled prose)")
    bad_threads = []
    for thread_id, thread in threads_prose.items():
        timestamps = [datetime.fromisoformat(m["timestamp"]) for m in thread["messages"]]
        if timestamps != sorted(timestamps) or len(set(timestamps)) != len(timestamps):
            bad_threads.append(thread_id)
    if bad_threads:
        fail(f"{len(bad_threads)} assembled thread(s) have out-of-order or duplicate timestamps: {bad_threads[:5]}")
    else:
        ok(f"all {len(threads_prose)} assembled threads have strictly increasing timestamps")


# ---------------------------------------------------------------------------
# Rule 7: name consistency with structure
# ---------------------------------------------------------------------------

def check_name_consistency(threads_prose: dict, structural_threads: dict) -> None:
    print("\n[Rule 7] Name/identity consistency with structure")

    customer_bad = []
    staff_bad = []
    staff_by_id = {s["staff_id"]: s for s in config.STAFF}

    for thread_id, prose in threads_prose.items():
        structural = structural_threads.get(thread_id)
        if structural is None:
            continue
        if (prose["customer_id"] != structural["customer_id"]
                or prose["customer_name"] != structural["customer_name"]):
            customer_bad.append(thread_id)

        for msg in prose["messages"]:
            if msg["sender"] != "staff":
                continue
            reference = staff_by_id.get(msg.get("staff_id"))
            if reference is None:
                staff_bad.append((thread_id, msg["index"], "unknown staff_id"))
            elif (msg.get("staff_name") != reference["name"]
                    or msg.get("staff_role") != reference["role"]):
                staff_bad.append((thread_id, msg["index"], "name/role mismatch"))

    if customer_bad:
        fail(f"{len(customer_bad)} thread(s) have a customer_id/name mismatch vs data/threads/: {customer_bad[:5]}")
    else:
        ok("every thread's customer_id/name matches its structural thread")

    if staff_bad:
        fail(f"{len(staff_bad)} staff message(s) have an unknown or mismatched staff identity: {staff_bad[:5]}")
    else:
        ok("every staff message's id/name/role matches config.STAFF exactly")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("08 Inbox — Phase 3 prose validation")

    if not config.EMAILS_DIR.exists() and not config.THREADS_PROSE_DIR.exists():
        print(
            "\nVALIDATION COULD NOT RUN: neither data/emails/ nor "
            "data/threads_prose/ exists yet. Run build_prose_tasks.py, get "
            "the prose-agent batches written to data/emails_raw/, then "
            "assemble_emails.py, before running this script."
        )
        return 1

    try:
        emails = load_emails()
        threads_prose = load_threads_prose()
        structural_threads = load_structural_threads()
        briefs = load_briefs()
    except Exception as exc:  # graceful, informative failure
        print(f"\nVALIDATION COULD NOT RUN: {type(exc).__name__}: {exc}")
        return 1

    check_completeness(emails, threads_prose, structural_threads)
    check_nontrivial_prose(threads_prose)
    check_planted_signals(emails, threads_prose, briefs)
    check_prior_promises_in_prose(threads_prose, structural_threads, briefs)
    check_no_leaked_vocabulary(threads_prose)
    check_thread_chronology(threads_prose)
    check_name_consistency(threads_prose, structural_threads)

    print("\n" + "=" * 60)
    if FAILURES:
        print(f"VALIDATION FAILED — {len(FAILURES)} rule(s) broken:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1

    print("VALIDATION PASSED — all prose coherence rules hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
