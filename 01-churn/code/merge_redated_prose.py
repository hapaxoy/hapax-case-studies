"""
merge_redated_prose.py — Merge freshly-written re-dated ticket prose back
into the original tickets_raw batch files.

Context: fix_ticket_dates.py re-dated tickets for the five non-churning
archetypes (A1, A2, A6, A7, A8) whose dates were clustered into a 30-day
burst by a bug in generate_ticket_briefs.py. The original ticket PROSE
(subject/body/channel) in data/tickets_raw/batch_*.json was written by the
ticket-writer agents against the OLD (buggy) dates and briefs, so once new
prose is written against the corrected briefs (data/brief_batches_redate/),
it needs to be spliced back into the original tickets_raw files in place —
churned-archetype records (A3/A4/A5) are untouched throughout.

This script does NOT generate prose. It expects the ticket-writer agents to
have already written data/tickets_raw_redate/batch_*.json, in the same
schema as data/tickets_raw/batch_*.json (account_id, ticket_index, date,
module, resolved, resolution_days, channel, subject, body).

For every record in data/tickets_raw_redate/:
  - Find the matching (account_id, ticket_index) record in
    data/tickets_raw/batch_*.json (search across all batch files — batch
    numbering differs between the two directories).
  - Replace that record's subject, body, channel, and date with the
    re-dated version.
  - Error out (no partial write) if any redated record has no match in the
    original tickets_raw files.

Before writing, the original tickets_raw batch files are backed up once to
data/tickets_raw_v1_preredate/ (idempotent — a second run reuses the
existing backup rather than overwriting it with already-merged data).

Run from the project root (after the redated prose exists):
    python code/merge_redated_prose.py

Output:
    data/tickets_raw/batch_*.json — updated in place (only touched batches
    are rewritten)
    data/tickets_raw_v1_preredate/batch_*.json — one-time backup
"""

import json
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR   = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR     = PROJECT_ROOT / "data"

TICKETS_RAW_DIR        = DATA_DIR / "tickets_raw"
TICKETS_RAW_REDATE_DIR = DATA_DIR / "tickets_raw_redate"
TICKETS_RAW_BACKUP_DIR = DATA_DIR / "tickets_raw_v1_preredate"

# Fields copied from the redated record into the original record
FIELDS_TO_MERGE = ["subject", "body", "channel", "date"]

assert TICKETS_RAW_REDATE_DIR.resolve() != TICKETS_RAW_DIR.resolve()


def main() -> None:
    print("=" * 60)
    print("merge_redated_prose.py — splicing re-dated prose into tickets_raw")
    print("=" * 60)

    # -- Step 1: locate the re-dated prose batches ------------------------------
    print(f"\n[1/6] Scanning {TICKETS_RAW_REDATE_DIR} for re-dated batches ...")
    if not TICKETS_RAW_REDATE_DIR.exists():
        print(f"  ERROR: {TICKETS_RAW_REDATE_DIR} does not exist. "
              "Write the re-dated prose there first (ticket-writer agents, "
              "using data/brief_batches_redate/ as the briefs).")
        sys.exit(1)

    redate_paths = sorted(TICKETS_RAW_REDATE_DIR.glob("batch_*.json"))
    if not redate_paths:
        print(f"  ERROR: no batch_*.json files found in {TICKETS_RAW_REDATE_DIR}.")
        sys.exit(1)

    redated_records = {}   # (account_id, ticket_index) -> record dict
    duplicate_keys = []
    for path in redate_paths:
        with open(path, encoding="utf-8") as fh:
            batch = json.load(fh)
        for record in batch:
            key = (record["account_id"], int(record["ticket_index"]))
            if key in redated_records:
                duplicate_keys.append((key, path.name))
            redated_records[key] = record
    print(f"  {len(redate_paths)} redated batch files, "
          f"{len(redated_records)} unique redated records loaded")
    if duplicate_keys:
        print(f"  WARNING: {len(duplicate_keys)} duplicate keys across redated "
              "batches — last occurrence wins.")

    # -- Step 2: load all original tickets_raw batches ---------------------------
    print(f"\n[2/6] Loading original batches from {TICKETS_RAW_DIR} ...")
    if not TICKETS_RAW_DIR.exists():
        print(f"  ERROR: {TICKETS_RAW_DIR} does not exist.")
        sys.exit(1)

    original_paths = sorted(TICKETS_RAW_DIR.glob("batch_*.json"))
    if not original_paths:
        print(f"  ERROR: no batch_*.json files found in {TICKETS_RAW_DIR}.")
        sys.exit(1)

    original_batches = {}   # path -> list of records (loaded fresh, mutated in place)
    key_to_path = {}        # (account_id, ticket_index) -> path
    for path in original_paths:
        with open(path, encoding="utf-8") as fh:
            batch = json.load(fh)
        original_batches[path] = batch
        for record in batch:
            key = (record["account_id"], int(record["ticket_index"]))
            key_to_path[key] = path
    print(f"  {len(original_paths)} original batch files, "
          f"{len(key_to_path)} records indexed")

    # -- Step 3: verify every redated record has a match --------------------------
    print("\n[3/6] Verifying every redated record has a matching original record ...")
    missing = [key for key in redated_records if key not in key_to_path]
    if missing:
        print(f"  ERROR: {len(missing)} redated records have no matching "
              "(account_id, ticket_index) in data/tickets_raw/. First few:")
        for key in missing[:10]:
            print(f"    {key}")
        print("\n  Aborting — no files were modified.")
        sys.exit(1)
    print(f"  All {len(redated_records)} redated records matched. OK to proceed.")

    # -- Step 4: back up the original tickets_raw files (idempotent) --------------
    print(f"\n[4/6] Backing up {TICKETS_RAW_DIR.name} ...")
    if TICKETS_RAW_BACKUP_DIR.exists():
        print(f"  Backup already exists at {TICKETS_RAW_BACKUP_DIR.name} — leaving it as is "
              "(re-run is safe; backup is only taken once).")
    else:
        TICKETS_RAW_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        for path in original_paths:
            shutil.copy2(path, TICKETS_RAW_BACKUP_DIR / path.name)
        print(f"  Backed up {len(original_paths)} batch files to {TICKETS_RAW_BACKUP_DIR}")

    # -- Step 5: splice the redated fields into the original records --------------
    print("\n[5/6] Merging re-dated subject/body/channel/date into original records ...")
    touched_paths = set()
    merged_count = 0

    # Build a fast lookup from path -> {key: record} for in-place updates
    records_by_path_key = {
        path: {(r["account_id"], int(r["ticket_index"])): r for r in batch}
        for path, batch in original_batches.items()
    }

    for key, redated_record in redated_records.items():
        path = key_to_path[key]
        original_record = records_by_path_key[path][key]
        for field in FIELDS_TO_MERGE:
            original_record[field] = redated_record[field]
        touched_paths.add(path)
        merged_count += 1

    print(f"  Merged {merged_count} records across {len(touched_paths)} original batch files")

    # -- Step 6: write back only the touched batch files ---------------------------
    print("\n[6/6] Writing updated batch files ...")
    for path in sorted(touched_paths):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(original_batches[path], fh, indent=1, ensure_ascii=False)
        print(f"  Updated: {path.name}")

    print("\n" + "=" * 60)
    print(f"Done. {merged_count} records merged into {len(touched_paths)} batch files.")
    print("Re-run assemble_tickets.py to rebuild data/tickets.csv with the "
          "re-dated prose (and the updated A4 csat pattern).")
    print("=" * 60)


if __name__ == "__main__":
    main()
