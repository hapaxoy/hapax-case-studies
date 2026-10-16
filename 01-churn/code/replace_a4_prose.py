"""
replace_a4_prose.py — Splices newly-written A4 low-volume ticket prose into
data/tickets_raw/, replacing the OLD high-volume A4 prose in place.

Design context: code/regenerate_a4_briefs.py rewrote data/ticket_briefs.json
with a new, low-volume brief set for A4 accounts (see that script's
docstring). code/make_a4_rewrite_batches.py then split those new briefs into
data/brief_batches_a4/batch_NN.json for a ticket-writer agent to turn into
prose. THIS script is the final step: once the agent has written that prose
into data/tickets_raw_a4/batch_NN.json (the same raw schema as any other
batch — account_id, ticket_index, date, module, resolved, resolution_days,
channel, subject, body), this script:

  1. Reads every data/tickets_raw_a4/batch_NN.json file (the new A4 prose).
  2. Validates the new prose's (account_id, ticket_index) keys against the
     CURRENT data/ticket_briefs.json A4 entries exactly — no missing, no
     extra, no duplicates. Refuses to touch anything if validation fails.
  3. For every A4 account, finds which data/tickets_raw/batch_NN.json file
     currently holds its OLD (high-volume) records, so the new records can
     be inserted into that SAME file, preserving each account's original
     batch placement.
  4. Rewrites each affected data/tickets_raw/batch_NN.json file: strips out
     every OLD record belonging to an A4 account and inserts the account's
     NEW records at the position the old block occupied (accounts stay
     grouped together). Non-A4 records in every batch file are left
     completely untouched (same objects, same order).
  5. Prints a before/after record-count summary (old A4 ~559 records once,
     ~191 now — the exact numbers are read from the data, not hardcoded).

The script was tested against a throwaway fixture before it was run on
data/tickets_raw/ (never hand-edit or dry-run against real project data
folders when a scratch fixture will do).

Run from the project root, once data/tickets_raw_a4/ is populated:
    python code/replace_a4_prose.py
"""

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Config block — paths are parameterised so this script can be pointed at a
# scratch fixture for testing without touching real project data
# ---------------------------------------------------------------------------

SCRIPT_DIR   = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"

RAW_SCHEMA_FIELDS = {
    "account_id", "ticket_index", "date", "module",
    "resolved", "resolution_days", "channel", "subject", "body",
}


def resolve_paths(data_dir: Path) -> dict[str, Path]:
    """Builds the set of paths this script reads/writes, all under data_dir."""
    return {
        "answer_key":        data_dir / "answer_key.csv",
        "briefs":            data_dir / "ticket_briefs.json",
        "tickets_raw":       data_dir / "tickets_raw",
        "tickets_raw_a4":    data_dir / "tickets_raw_a4",
    }


# ---------------------------------------------------------------------------
# Step 1: identify A4 accounts
# ---------------------------------------------------------------------------

def load_a4_ids(answer_key_path: Path) -> set[str]:
    """Reads answer_key.csv (no pandas dependency — keeps this script light
    and easy to point at a minimal scratch fixture) and returns the set of
    A4 account_ids."""
    import csv

    if not answer_key_path.exists():
        print(f"ERROR: {answer_key_path} not found.")
        sys.exit(1)

    a4_ids = set()
    with open(answer_key_path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["archetype"] == "A4":
                a4_ids.add(row["account_id"])
    return a4_ids


# ---------------------------------------------------------------------------
# Step 2: load current A4 briefs (the expected key set) and new prose
# ---------------------------------------------------------------------------

def load_current_a4_brief_keys(briefs_path: Path, a4_ids: set[str]) -> set[tuple]:
    """Returns the set of (account_id, ticket_index) keys the current
    ticket_briefs.json expects for A4 accounts — the ground truth the new
    prose must match exactly."""
    if not briefs_path.exists():
        print(f"ERROR: {briefs_path} not found.")
        sys.exit(1)
    with open(briefs_path, encoding="utf-8") as fh:
        briefs = json.load(fh)
    return {
        (b["account_id"], int(b["ticket_index"]))
        for b in briefs
        if b["account_id"] in a4_ids
    }


def load_new_a4_prose(tickets_raw_a4_dir: Path) -> list[dict]:
    """Loads every batch_*.json file under data/tickets_raw_a4/."""
    if not tickets_raw_a4_dir.exists():
        print(f"ERROR: {tickets_raw_a4_dir} not found. No new A4 prose to apply — "
              f"run make_a4_rewrite_batches.py and have a ticket-writer agent "
              f"populate this folder first.")
        sys.exit(1)

    batch_paths = sorted(tickets_raw_a4_dir.glob("batch_*.json"))
    if not batch_paths:
        print(f"ERROR: no batch_*.json files found under {tickets_raw_a4_dir}.")
        sys.exit(1)

    records = []
    for path in batch_paths:
        with open(path, encoding="utf-8") as fh:
            batch = json.load(fh)
        records.extend(batch)
    return records


def validate_new_prose(new_records: list[dict], expected_keys: set[tuple]) -> None:
    """
    Checks the new prose's schema and (account_id, ticket_index) coverage
    against the expected key set. Exits with an informative error on any
    mismatch — never proceeds with a partial or malformed splice.
    """
    # Schema check
    for record in new_records:
        missing_fields = RAW_SCHEMA_FIELDS - set(record.keys())
        if missing_fields:
            print(f"ERROR: record for {record.get('account_id', '?')} / "
                  f"ticket_index {record.get('ticket_index', '?')} is missing "
                  f"required field(s): {missing_fields}")
            sys.exit(1)

    # Duplicate check
    seen_keys = set()
    for record in new_records:
        key = (record["account_id"], int(record["ticket_index"]))
        if key in seen_keys:
            print(f"ERROR: duplicate (account_id, ticket_index) in new A4 prose: {key}")
            sys.exit(1)
        seen_keys.add(key)

    # Coverage check: exact match, no missing, no extra
    missing_keys = expected_keys - seen_keys
    extra_keys   = seen_keys - expected_keys
    if missing_keys:
        print(f"ERROR: {len(missing_keys)} A4 briefs have no matching new prose record. "
              f"First few: {sorted(missing_keys)[:5]}")
        sys.exit(1)
    if extra_keys:
        print(f"ERROR: {len(extra_keys)} new prose records don't match any current A4 brief "
              f"(stale batch file? regenerate_a4_briefs.py re-run since prose was written?). "
              f"First few: {sorted(extra_keys)[:5]}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Step 3: find each A4 account's current batch file, then splice
# ---------------------------------------------------------------------------

def find_account_batch_assignment(tickets_raw_dir: Path, a4_ids: set[str]) -> dict[str, Path]:
    """
    Scans data/tickets_raw/batch_*.json (the current, OLD-A4-prose files) and
    returns {account_id: batch_path} for every A4 account found — i.e. "the
    batch file where each account previously lived."
    """
    if not tickets_raw_dir.exists():
        print(f"ERROR: {tickets_raw_dir} not found.")
        sys.exit(1)

    batch_paths = sorted(tickets_raw_dir.glob("batch_*.json"))
    if not batch_paths:
        print(f"ERROR: no batch_*.json files found under {tickets_raw_dir}.")
        sys.exit(1)

    assignment: dict[str, Path] = {}
    for path in batch_paths:
        with open(path, encoding="utf-8") as fh:
            batch = json.load(fh)
        for record in batch:
            acc_id = record["account_id"]
            if acc_id in a4_ids and acc_id not in assignment:
                assignment[acc_id] = path

    missing = a4_ids - set(assignment.keys())
    if missing:
        print(f"ERROR: {len(missing)} A4 accounts have no OLD records in any "
              f"tickets_raw batch file (nothing to replace): {sorted(missing)[:5]}")
        sys.exit(1)

    return assignment


def splice_batch_file(
    path: Path,
    a4_ids: set[str],
    new_records_by_account: dict[str, list[dict]],
) -> tuple[int, int]:
    """
    Rewrites a single tickets_raw batch file: removes every A4 record and
    inserts that account's new records at the position the old block
    occupied. Non-A4 records are untouched (same objects, same order).

    Returns (old_a4_record_count, new_a4_record_count) for this file.
    """
    with open(path, encoding="utf-8") as fh:
        old_batch = json.load(fh)

    new_batch = []
    replaced_ids: set[str] = set()
    old_a4_count = 0
    new_a4_count = 0

    for record in old_batch:
        acc_id = record["account_id"]
        if acc_id in a4_ids:
            old_a4_count += 1
            if acc_id not in replaced_ids:
                account_new_records = sorted(
                    new_records_by_account[acc_id], key=lambda r: int(r["ticket_index"])
                )
                new_batch.extend(account_new_records)
                new_a4_count += len(account_new_records)
                replaced_ids.add(acc_id)
            # else: subsequent old record for an already-spliced account — drop it
        else:
            new_batch.append(record)   # untouched

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(new_batch, fh, indent=2, ensure_ascii=False)

    return old_a4_count, new_a4_count


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(data_dir: Path = DEFAULT_DATA_DIR):
    print("=" * 70)
    print("replace_a4_prose.py — splicing new low-volume A4 prose into tickets_raw")
    print(f"Data directory: {data_dir}")
    print("=" * 70)

    paths = resolve_paths(data_dir)

    # Safety: tickets_raw_a4 (input) must never be the same path as tickets_raw (output)
    assert paths["tickets_raw_a4"].resolve() != paths["tickets_raw"].resolve(), (
        "Refusing to run: tickets_raw_a4 and tickets_raw resolve to the same path"
    )

    print("\n[1/5] Identifying A4 accounts...")
    a4_ids = load_a4_ids(paths["answer_key"])
    print(f"  {len(a4_ids)} A4 accounts.")

    print("\n[2/5] Loading current ticket_briefs.json A4 key set and new prose...")
    expected_keys = load_current_a4_brief_keys(paths["briefs"], a4_ids)
    new_records = load_new_a4_prose(paths["tickets_raw_a4"])
    print(f"  Expecting {len(expected_keys)} A4 brief keys; found {len(new_records)} new prose records.")

    print("\n[3/5] Validating new prose (schema, duplicates, exact key coverage)...")
    validate_new_prose(new_records, expected_keys)
    print("  OK: new prose matches the current A4 briefs exactly.")

    new_records_by_account: dict[str, list[dict]] = {}
    for record in new_records:
        new_records_by_account.setdefault(record["account_id"], []).append(record)

    print("\n[4/5] Finding each A4 account's current batch file...")
    assignment = find_account_batch_assignment(paths["tickets_raw"], a4_ids)
    affected_paths = sorted(set(assignment.values()))
    print(f"  A4 accounts found across {len(affected_paths)} batch file(s): "
          f"{[p.name for p in affected_paths]}")

    print("\n[5/5] Splicing new prose into each affected batch file...")
    total_old = 0
    total_new = 0
    for path in affected_paths:
        old_count, new_count = splice_batch_file(path, a4_ids, new_records_by_account)
        total_old += old_count
        total_new += new_count
        print(f"  {path.name}: {old_count} old A4 records removed, {new_count} new records inserted")

    print("\n" + "=" * 70)
    print(f"DONE. A4 records across tickets_raw: {total_old} -> {total_new}")
    print("Next: re-run assemble_tickets.py, build_features.py, train_models.py, "
          "and make_assessment_batches.py to propagate the low-volume redesign downstream.")
    print("=" * 70)


if __name__ == "__main__":
    main()
