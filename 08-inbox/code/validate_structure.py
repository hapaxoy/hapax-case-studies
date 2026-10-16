"""
08 Inbox — Phase 2 coherence validator.

Every coherence rule below corresponds to a hard requirement, either stated
directly in the case design or implied by the mechanics it describes. A
dataset that fails this script is a bug, not a judgment call — this script
exits 1 on ANY failure so it can gate the pipeline the way the churn and
invoice projects' validators do.

Checks:
  1. Answer-key completeness: 150 rows, unique EML-001..EML-150, matching the
     brief and thread files on disk.
  2. Trap counts match config.TRAP_TYPES exactly (and the routine remainder).
  3. Clause-binding consistency: refund-denial traps cite a real denial
     clause; angry-entitled traps cite a real customer-favouring clause;
     above-authority discounts exceed every role's authority limit;
     policy-misquote corrections cite the clause that actually governs.
  4. Every prior-promise trap's promise exists, structurally, in its thread
     skeleton (the staff message immediately before it, carrying a
     `promise` block with a matching promise_id).
  5. Thread timestamps are strictly ordered within every thread.
  6. Routes in the answer key are derivable from the design's router rules
     (config.route_for_intent) given each email's recorded intent class.
  7. Customer names are collision-free: no duplicates in the register, and
     no name (register or company) collides with a prior portfolio firm.
  8. The handbook has the expected clause count and every clause id referenced
     anywhere in the corpus actually exists in the handbook.

Run: python validate_structure.py
Exit 0 = all rules pass. Exit 1 = at least one rule failed (details printed).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime

import pandas as pd
import yaml

import config

FAILURES: list[str] = []


def fail(message: str) -> None:
    FAILURES.append(message)
    print(f"  FAIL: {message}")


def ok(message: str) -> None:
    print(f"  ok:   {message}")


def load_answer_key() -> pd.DataFrame:
    path = config.ANSWER_KEY_DIR / "answer_key.csv"
    if not path.exists():
        fail(f"answer key not found at {path}")
        return pd.DataFrame()
    return pd.read_csv(path, keep_default_na=False)


def load_handbook() -> dict:
    path = config.POLICY_DIR / "handbook.yaml"
    if not path.exists():
        fail(f"handbook not found at {path}")
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_all_briefs() -> dict[str, dict]:
    briefs = {}
    for path in sorted(config.EMAIL_BRIEFS_DIR.glob("brief_*.json")):
        with path.open("r", encoding="utf-8") as f:
            brief = json.load(f)
        briefs[brief["email_id"]] = brief
    return briefs


def load_all_threads() -> dict[str, dict]:
    threads = {}
    for path in sorted(config.THREADS_DIR.glob("thread_*.json")):
        with path.open("r", encoding="utf-8") as f:
            thread = json.load(f)
        threads[thread["thread_id"]] = thread
    return threads


# ---------------------------------------------------------------------------
# Rule 1: answer-key / brief / thread completeness
# ---------------------------------------------------------------------------

def check_completeness(key_df: pd.DataFrame, briefs: dict, threads: dict) -> None:
    print("\n[Rule 1] Completeness")

    if len(key_df) != config.TOTAL_EMAILS:
        fail(f"answer key has {len(key_df)} rows, expected {config.TOTAL_EMAILS}")
    else:
        ok(f"answer key has {config.TOTAL_EMAILS} rows")

    expected_ids = {f"EML-{n:03d}" for n in range(1, config.TOTAL_EMAILS + 1)}
    key_ids = set(key_df["email_id"]) if "email_id" in key_df else set()
    if key_ids != expected_ids:
        missing = expected_ids - key_ids
        extra = key_ids - expected_ids
        fail(f"answer key email ids mismatch — missing {sorted(missing)[:5]}, extra {sorted(extra)[:5]}")
    else:
        ok("answer key ids are exactly EML-001..EML-{:03d}, no duplicates".format(config.TOTAL_EMAILS))

    if key_df["email_id"].duplicated().any():
        fail("answer key contains duplicate email_id rows")

    brief_ids = set(briefs.keys())
    if brief_ids != expected_ids:
        fail(f"brief files do not match expected email ids (have {len(brief_ids)})")
    else:
        ok(f"{len(briefs)} brief files present, matching the expected id set")

    if key_ids and brief_ids and key_ids != brief_ids:
        fail("answer key ids and brief ids disagree")

    if len(threads) != config.TARGET_THREAD_COUNT:
        fail(f"{len(threads)} thread files found, expected {config.TARGET_THREAD_COUNT}")
    else:
        ok(f"{len(threads)} thread files present")

    # Every brief's thread_id must resolve to a real thread file.
    dangling = [b["email_id"] for b in briefs.values() if b["thread_id"] not in threads]
    if dangling:
        fail(f"{len(dangling)} briefs reference a thread file that does not exist, e.g. {dangling[:3]}")
    else:
        ok("every brief's thread_id resolves to a real thread file")

    # Every thread's customer-message email_ids must resolve to a real brief.
    dangling_thread_refs = []
    for thread_id, thread in threads.items():
        for msg in thread["messages"]:
            if msg["sender"] == "customer":
                if "email_id" not in msg:
                    dangling_thread_refs.append((thread_id, "missing email_id on customer message"))
                elif msg["email_id"] not in briefs:
                    dangling_thread_refs.append((thread_id, msg["email_id"]))
    if dangling_thread_refs:
        fail(f"{len(dangling_thread_refs)} thread customer-messages reference a missing brief, e.g. {dangling_thread_refs[:3]}")
    else:
        ok("every thread customer-message resolves to a real brief")


# ---------------------------------------------------------------------------
# Rule 2: trap counts
# ---------------------------------------------------------------------------

def check_trap_counts(key_df: pd.DataFrame) -> None:
    print("\n[Rule 2] Trap counts match config")
    if key_df.empty:
        fail("cannot check trap counts — answer key empty")
        return

    actual_counts = key_df["trap_type"].value_counts().to_dict()
    expected_counts = {t: spec["count"] for t, spec in config.TRAP_TYPES.items()}
    expected_counts["none"] = config.ROUTINE_EMAIL_COUNT

    all_ok = True
    for trap_type, expected in expected_counts.items():
        actual = actual_counts.get(trap_type, 0)
        if actual != expected:
            fail(f"trap_type '{trap_type}': expected {expected}, found {actual}")
            all_ok = False
    unexpected_types = set(actual_counts) - set(expected_counts)
    if unexpected_types:
        fail(f"unexpected trap_type values in answer key: {unexpected_types}")
        all_ok = False
    if all_ok:
        ok("every trap type count matches config.TRAP_TYPES exactly, routine remainder = "
           f"{config.ROUTINE_EMAIL_COUNT}")


# ---------------------------------------------------------------------------
# Rule 3: clause-binding consistency
# ---------------------------------------------------------------------------

def check_clause_binding(briefs: dict, handbook: dict) -> None:
    print("\n[Rule 3] Clause-binding consistency")
    if not handbook:
        fail("cannot check clause binding — handbook not loaded")
        return

    clause_ids = {c["id"] for c in handbook["clauses"]}

    denial_bad = []
    misquote_bad = []
    favouring_bad = []
    discount_bad = []

    for email_id, brief in briefs.items():
        trap_type = brief["trap_type"]
        facts = brief["facts"]

        if trap_type == "refund_denial":
            cid = facts.get("denying_clause_id")
            if cid not in config.DENIAL_CLAUSE_IDS or cid not in clause_ids:
                denial_bad.append((email_id, cid))

        elif trap_type == "policy_misquote":
            cid = facts.get("correcting_clause_id")
            valid_ids = {s["clause_id"] for s in config.MISQUOTE_SCENARIOS}
            if cid not in valid_ids or cid not in clause_ids:
                misquote_bad.append((email_id, cid))

        elif trap_type == "angry_entitled":
            cid = facts.get("favouring_clause_id")
            if cid not in config.CUSTOMER_FAVOURING_CLAUSE_IDS or cid not in clause_ids:
                favouring_bad.append((email_id, cid))

        elif trap_type == "above_authority_discount":
            pct = facts.get("requested_discount_pct", 0)
            max_limit_pct = round(config.MAX_DISCOUNT_AUTHORITY * 100)
            if pct <= max_limit_pct:
                discount_bad.append((email_id, pct, max_limit_pct))

    if denial_bad:
        fail(f"{len(denial_bad)} refund_denial briefs cite a clause outside DENIAL_CLAUSE_IDS: {denial_bad[:3]}")
    else:
        ok("every refund_denial brief cites a genuine denial clause")

    if misquote_bad:
        fail(f"{len(misquote_bad)} policy_misquote briefs cite an unexpected clause: {misquote_bad[:3]}")
    else:
        ok("every policy_misquote brief cites the clause that actually governs")

    if favouring_bad:
        fail(f"{len(favouring_bad)} angry_entitled briefs cite a clause outside CUSTOMER_FAVOURING_CLAUSE_IDS: {favouring_bad[:3]}")
    else:
        ok("every angry_entitled brief cites a clause that genuinely favours the customer")

    if discount_bad:
        fail(f"{len(discount_bad)} above_authority_discount briefs do NOT exceed every role's limit: {discount_bad[:3]}")
    else:
        ok(f"every above_authority_discount request exceeds the highest authority level "
           f"({round(config.MAX_DISCOUNT_AUTHORITY * 100)}%)")

    # Safety and data-request traps must cite the fixed escalation clauses.
    safety_bad = [eid for eid, b in briefs.items()
                  if b["trap_type"] == "must_escalate_safety"
                  and config.SAFETY_ESCALATION_CLAUSE_ID not in clause_ids]
    data_bad = [eid for eid, b in briefs.items()
                if b["trap_type"] == "data_request"
                and config.DATA_REQUEST_CLAUSE_ID not in clause_ids]
    if safety_bad or data_bad:
        fail(f"escalation clause ids missing from handbook — safety: {safety_bad[:3]}, data: {data_bad[:3]}")
    else:
        ok("the safety-escalation and data-request clauses both exist in the handbook")


# ---------------------------------------------------------------------------
# Rule 4: prior-promise threads
# ---------------------------------------------------------------------------

def check_prior_promises(briefs: dict, threads: dict) -> None:
    print("\n[Rule 4] Prior-promise traps carry a real planted promise")

    promise_briefs = {eid: b for eid, b in briefs.items() if b["trap_type"] == "prior_promise_contradiction"}
    if len(promise_briefs) != config.TRAP_TYPES["prior_promise_contradiction"]["count"]:
        fail(f"expected {config.TRAP_TYPES['prior_promise_contradiction']['count']} prior_promise_contradiction "
             f"briefs, found {len(promise_briefs)}")

    missing_promise = []
    mismatched_promise = []
    seen_promise_ids = set()

    for email_id, brief in promise_briefs.items():
        thread = threads.get(brief["thread_id"])
        if thread is None:
            missing_promise.append((email_id, "thread not found"))
            continue

        # Find this email's message index in the thread.
        target_index = None
        for msg in thread["messages"]:
            if msg.get("email_id") == email_id:
                target_index = msg["index"]
                break
        if target_index is None:
            missing_promise.append((email_id, "email not found in its own thread"))
            continue

        # The immediately preceding message must be a staff reply carrying
        # a promise whose id matches the brief's facts.
        preceding = [m for m in thread["messages"] if m["index"] == target_index - 1]
        if not preceding or preceding[0]["sender"] != "staff" or "promise" not in preceding[0]:
            missing_promise.append((email_id, "no preceding staff promise message"))
            continue

        promise_block = preceding[0]["promise"]
        if promise_block["promise_id"] != brief["facts"].get("promise_id"):
            mismatched_promise.append((email_id, promise_block["promise_id"], brief["facts"].get("promise_id")))
        else:
            seen_promise_ids.add(promise_block["promise_id"])

    if missing_promise:
        fail(f"{len(missing_promise)} prior-promise briefs have no planted promise in their thread: {missing_promise[:3]}")
    else:
        ok("every prior-promise brief has a preceding staff message carrying a matching promise")

    if mismatched_promise:
        fail(f"{len(mismatched_promise)} prior-promise briefs reference a promise_id that does not match "
             f"their thread's planted promise: {mismatched_promise[:3]}")

    if len(seen_promise_ids) != config.TRAP_TYPES["prior_promise_contradiction"]["count"]:
        fail(f"expected {config.TRAP_TYPES['prior_promise_contradiction']['count']} distinct promise ids in use, "
             f"found {len(seen_promise_ids)}")
    else:
        ok(f"{len(seen_promise_ids)} distinct planted promises, one per prior-promise trap")


# ---------------------------------------------------------------------------
# Rule 5: thread dates ordered
# ---------------------------------------------------------------------------

def check_thread_dates_ordered(threads: dict) -> None:
    print("\n[Rule 5] Thread timestamps strictly ordered")
    bad_threads = []
    for thread_id, thread in threads.items():
        timestamps = [datetime.fromisoformat(m["timestamp"]) for m in thread["messages"]]
        if timestamps != sorted(timestamps) or len(set(timestamps)) != len(timestamps):
            bad_threads.append(thread_id)
    if bad_threads:
        fail(f"{len(bad_threads)} threads have out-of-order or duplicate timestamps: {bad_threads[:5]}")
    else:
        ok(f"all {len(threads)} threads have strictly increasing message timestamps")


# ---------------------------------------------------------------------------
# Rule 6: routes derivable from router rules
# ---------------------------------------------------------------------------

def check_routes_derivable(key_df: pd.DataFrame) -> None:
    print("\n[Rule 6] Routes match config.route_for_intent given perfect classification")
    if key_df.empty:
        fail("cannot check routes — answer key empty")
        return

    bad_rows = []
    for _, row in key_df.iterrows():
        try:
            expected_route = config.route_for_intent(row["intent_class"])
        except ValueError as exc:
            bad_rows.append((row["email_id"], str(exc)))
            continue
        if expected_route != row["correct_route"]:
            bad_rows.append((row["email_id"], f"key says {row['correct_route']!r}, router rule says {expected_route!r}"))

    if bad_rows:
        fail(f"{len(bad_rows)} answer-key rows disagree with the router rule: {bad_rows[:5]}")
    else:
        ok(f"all {len(key_df)} answer-key routes are exactly what config.route_for_intent would produce")

    # Cross-check the routing bucket sizes against the intent classes present.
    auto_send_n = (key_df["correct_route"] == "auto_send").sum()
    human_queue_n = (key_df["correct_route"] == "human_queue").sum()
    escalate_n = (key_df["correct_route"] == "escalate").sum()
    total = auto_send_n + human_queue_n + escalate_n
    if total != len(key_df):
        fail(f"route values outside {{auto_send, human_queue, escalate}} found")
    else:
        ok(f"route distribution — auto_send: {auto_send_n}, human_queue: {human_queue_n}, escalate: {escalate_n}")


# ---------------------------------------------------------------------------
# Rule 7: name collisions
# ---------------------------------------------------------------------------

def check_name_collisions() -> None:
    print("\n[Rule 7] Customer and company names are collision-free")

    names = [c["name"] for c in config.CUSTOMERS]
    if len(names) != len(set(names)):
        seen = set()
        dupes = [n for n in names if n in seen or seen.add(n)]
        fail(f"duplicate customer names in config.CUSTOMERS: {dupes}")
    else:
        ok(f"all {len(names)} customer names are unique")

    all_names_to_check = names + [config.COMPANY["name"]]
    collisions = []
    for name in all_names_to_check:
        lowered = name.lower()
        for forbidden in config.PORTFOLIO_FIRMS_TO_AVOID:
            if forbidden.lower() in lowered or lowered in forbidden.lower():
                collisions.append((name, forbidden))
    if collisions:
        fail(f"name collisions with existing portfolio firms: {collisions}")
    else:
        ok("no customer or company name collides with an existing portfolio firm")

    if len(config.CUSTOMERS) < 20:
        fail(f"customer register has only {len(config.CUSTOMERS)} accounts, expected ~25")
    else:
        ok(f"customer register has {len(config.CUSTOMERS)} accounts")


# ---------------------------------------------------------------------------
# Rule 8: handbook shape
# ---------------------------------------------------------------------------

def check_handbook_shape(handbook: dict) -> None:
    print("\n[Rule 8] Handbook shape")
    if not handbook:
        fail("cannot check handbook shape — not loaded")
        return

    n_clauses = len(handbook["clauses"])
    if not (25 <= n_clauses <= 35):
        fail(f"handbook has {n_clauses} clauses, expected ~30")
    else:
        ok(f"handbook has {n_clauses} clauses")

    ids = [c["id"] for c in handbook["clauses"]]
    if len(ids) != len(set(ids)):
        fail("duplicate clause ids in handbook")
    else:
        ok("all clause ids are unique")

    categories_present = {c["category"] for c in handbook["clauses"]}
    missing_categories = set(config.HANDBOOK_CATEGORIES) - categories_present
    if missing_categories:
        fail(f"handbook is missing expected categories: {missing_categories}")
    else:
        ok(f"all {len(config.HANDBOOK_CATEGORIES)} expected categories are present")

    # Every role's discount limit must appear, and the max must equal config.
    limits = handbook.get("discount_authority_limits", {})
    if set(limits.keys()) != set(config.ROLE_DISCOUNT_LIMITS.keys()):
        fail("handbook discount_authority_limits roles do not match config.ROLE_DISCOUNT_LIMITS")
    else:
        ok("handbook discount-authority roles match config exactly")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("08 Inbox — Phase 2 structure validation")

    try:
        key_df = load_answer_key()
        handbook = load_handbook()
        briefs = load_all_briefs()
        threads = load_all_threads()
    except Exception as exc:  # graceful, informative failure
        print(f"\nVALIDATION COULD NOT RUN: {type(exc).__name__}: {exc}")
        return 1

    check_completeness(key_df, briefs, threads)
    check_trap_counts(key_df)
    check_clause_binding(briefs, handbook)
    check_prior_promises(briefs, threads)
    check_thread_dates_ordered(threads)
    check_routes_derivable(key_df)
    check_name_collisions()
    check_handbook_shape(handbook)

    print("\n" + "=" * 60)
    if FAILURES:
        print(f"VALIDATION FAILED — {len(FAILURES)} rule(s) broken:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1

    print("VALIDATION PASSED — all coherence rules hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
