"""
08 Inbox — Phase 4 deterministic retrieval (pipeline step 2).

Everything in this module is deterministic Python — no model call, no
randomness. It reads exactly three kinds of in-world artefact: the policy
handbook, the customer register, and the prose thread history. It never
opens `data/answer_key/`, `data/threads/` (the structured, ground-truth
version), or `data/email_briefs/` — those carry intent_class/trap_type/
promise fields that would hand the pipeline the answer directly (see
`assemble_emails.py`'s "Design decisions" note). The pipeline is only ever
allowed to know what a human agent opening the real inbox would know.

Functions are split into loaders (I/O, read the data/ tree) and pure
retrieval logic (no I/O, operate on already-loaded structures) so the pure
functions can be unit-tested against hand-built fixtures without touching
disk at all.
"""

from __future__ import annotations

import json

import pandas as pd
import yaml

import config


# ---------------------------------------------------------------------------
# Loaders (I/O). Read-only — never write anywhere under data/.
# ---------------------------------------------------------------------------

def load_all_emails() -> dict[str, dict]:
    """Every inbound customer email, keyed by email_id. Reads
    data/emails/email_*.json only — the assembled, ground-truth-stripped
    corpus (see assemble_emails.py)."""
    if not config.EMAILS_DIR.exists():
        raise SystemExit(
            f"[retrieval] ERROR: {config.EMAILS_DIR} does not exist. "
            "Run assemble_emails.py (Phase 3) first."
        )
    emails: dict[str, dict] = {}
    for path in sorted(config.EMAILS_DIR.glob("email_*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        emails[record["email_id"]] = record
    if not emails:
        raise SystemExit(
            f"[retrieval] ERROR: no email_*.json files found under "
            f"{config.EMAILS_DIR}."
        )
    return emails


def load_all_threads_prose() -> dict[str, dict]:
    """Every thread's prose history, keyed by thread_id. Reads
    data/threads_prose/thread_*.json only — never data/threads/ (which
    carries the structured promise block and per-message trap_type /
    intent_class ground truth)."""
    if not config.THREADS_PROSE_DIR.exists():
        raise SystemExit(
            f"[retrieval] ERROR: {config.THREADS_PROSE_DIR} does not exist. "
            "Run assemble_emails.py (Phase 3) first."
        )
    threads: dict[str, dict] = {}
    for path in sorted(config.THREADS_PROSE_DIR.glob("thread_*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        threads[record["thread_id"]] = record
    if not threads:
        raise SystemExit(
            f"[retrieval] ERROR: no thread_*.json files found under "
            f"{config.THREADS_PROSE_DIR}."
        )
    return threads


def load_policy_handbook() -> list[dict]:
    """The ~30-clause policy handbook, as a list of {id, category, title,
    text} dicts, straight from the single authored source
    data/policy/handbook.yaml."""
    handbook_path = config.POLICY_DIR / "handbook.yaml"
    if not handbook_path.exists():
        raise SystemExit(
            f"[retrieval] ERROR: policy handbook not found at "
            f"{handbook_path}. Run generate_structure.py (Phase 2) first."
        )
    data = yaml.safe_load(handbook_path.read_text(encoding="utf-8"))
    clauses = data.get("clauses", [])
    if not clauses:
        raise SystemExit(
            f"[retrieval] ERROR: {handbook_path} parsed but contains no "
            "clauses — the handbook file may be corrupt."
        )
    return [
        {"id": c["id"], "category": c["category"], "title": c["title"], "text": c["text"]}
        for c in clauses
    ]


def load_customer_register() -> pd.DataFrame:
    """The customer register as a DataFrame, keyed by customer_id."""
    register_path = config.CUSTOMERS_DIR / "register.csv"
    if not register_path.exists():
        raise SystemExit(
            f"[retrieval] ERROR: customer register not found at "
            f"{register_path}. Run generate_structure.py (Phase 2) first."
        )
    return pd.read_csv(register_path)


# ---------------------------------------------------------------------------
# Pure retrieval logic (no I/O). Every function here takes already-loaded
# structures and returns a result with no side effects — this is what the
# throwaway unit tests exercise directly against hand-built fixtures.
# ---------------------------------------------------------------------------

def handbook_clause_ids(handbook_clauses: list[dict]) -> set[str]:
    """The set of real clause ids — what the policy gate checks a cited
    clause_id against ("citations ... are real")."""
    return {c["id"] for c in handbook_clauses}


def thread_messages_before(thread: dict, email_id: str) -> list[dict]:
    """Every message in `thread` (customer and staff) strictly before the
    message with this email_id, in thread order — "the full thread
    history" that step 2 names. Raises a clear, informative error
    if the email is not found in this thread at all (a wiring bug between
    data/emails/ and data/threads_prose/, not a judgment call) rather than
    silently returning an empty history that would hide the bug.
    """
    messages = sorted(thread["messages"], key=lambda m: m["index"])
    target_index = None
    for message in messages:
        if message.get("email_id") == email_id:
            target_index = message["index"]
            break
    if target_index is None:
        raise ValueError(
            f"email_id {email_id!r} was not found among thread "
            f"{thread.get('thread_id')!r}'s messages — check the "
            "email/thread wiring."
        )
    return [m for m in messages if m["index"] < target_index]


def prior_staff_message_count(thread_history: list[dict]) -> int:
    """How many prior staff replies exist in a thread history — the
    consistency gate's completeness check: every one of these must appear,
    reviewed, in the draft's prior_commitments_reviewed list."""
    return sum(1 for m in thread_history if m.get("sender") == "staff")


def customer_record_for(customer_id: str, register: pd.DataFrame) -> dict:
    """The one customer register row for this customer_id, as a plain
    dict. Raises a clear error for an unknown customer_id rather than
    returning an empty/default record."""
    matches = register[register["customer_id"] == customer_id]
    if matches.empty:
        raise ValueError(
            f"customer_id {customer_id!r} was not found in the customer "
            "register."
        )
    return matches.iloc[0].to_dict()
