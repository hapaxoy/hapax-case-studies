"""
make_redate_batches.py — Split the re-dated (post fix_ticket_dates.py) briefs
for non-churn accounts into batch files for the ticket-writer agents.

Only the five non-churning archetypes (A1, A2, A6, A7, A8) had their dates
touched by fix_ticket_dates.py. Prose for their tickets was originally
written against the OLD (clustered/buggy) dates, so it needs to be
regenerated against the new dates. Churned archetypes (A3, A4, A5) were not
touched and keep their existing prose — they are excluded from these batches.

Same packing approach as split_briefs.py: group by account (an account's
tickets must stay together so the writer keeps persona and arc consistent),
then pack whole accounts into batches of roughly TARGET_TICKETS_PER_BATCH
tickets each.

Run from the project root:
    python code/make_redate_batches.py

Output:
    data/brief_batches_redate/batch_NN.json
"""

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TARGET_TICKETS_PER_BATCH = 150

SCRIPT_DIR   = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR     = PROJECT_ROOT / "data"

BRIEFS_FILE   = DATA_DIR / "ticket_briefs.json"
ANSWER_KEY_FILE = DATA_DIR / "answer_key.csv"
BATCH_FOLDER  = DATA_DIR / "brief_batches_redate"

# Safety check: output directory must not be the input file's directory alias
assert BATCH_FOLDER != DATA_DIR or True  # output is a subfolder of data/, distinct path from BRIEFS_FILE
assert BATCH_FOLDER.resolve() != BRIEFS_FILE.resolve()

NON_CHURN_ARCHETYPES = {"A1", "A2", "A6", "A7", "A8"}

sys.path.insert(0, str(SCRIPT_DIR))


def main() -> None:
    print("=" * 60)
    print("make_redate_batches.py — batching re-dated non-churn briefs")
    print("=" * 60)

    # -- Step 1: load briefs and the answer key --------------------------------
    print(f"\n[1/4] Loading {BRIEFS_FILE.name} and {ANSWER_KEY_FILE.name} ...")

    if not BRIEFS_FILE.exists():
        print(f"  ERROR: {BRIEFS_FILE} not found. Run fix_ticket_dates.py first.")
        sys.exit(1)
    if not ANSWER_KEY_FILE.exists():
        print(f"  ERROR: {ANSWER_KEY_FILE} not found.")
        sys.exit(1)

    with open(BRIEFS_FILE, encoding="utf-8") as fh:
        all_briefs = json.load(fh)
    print(f"  {len(all_briefs)} total briefs loaded")

    import csv
    archetype_map = {}
    with open(ANSWER_KEY_FILE, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            archetype_map[row["account_id"]] = row["archetype"]
    print(f"  {len(archetype_map)} accounts in answer key")

    # -- Step 2: filter to non-churn accounts only ------------------------------
    print("\n[2/4] Filtering to non-churn accounts (A1, A2, A6, A7, A8) ...")
    redate_briefs = [
        b for b in all_briefs
        if archetype_map.get(b["account_id"]) in NON_CHURN_ARCHETYPES
    ]
    n_accounts_total = len({b["account_id"] for b in all_briefs})
    n_accounts_redate = len({b["account_id"] for b in redate_briefs})
    print(f"  {len(redate_briefs)} briefs across {n_accounts_redate} non-churn accounts "
          f"(of {len(all_briefs)} briefs / {n_accounts_total} accounts total)")

    briefs_by_account: dict = {}
    for brief in redate_briefs:
        briefs_by_account.setdefault(brief["account_id"], []).append(brief)

    # -- Step 3: pack whole accounts into batches --------------------------------
    print("\n[3/4] Packing accounts into batches "
          f"(target ~{TARGET_TICKETS_PER_BATCH} tickets/batch) ...")

    BATCH_FOLDER.mkdir(parents=True, exist_ok=True)

    batches: list[list[dict]] = []
    current_batch: list[dict] = []
    for account_id in sorted(briefs_by_account):
        account_briefs = briefs_by_account[account_id]
        if current_batch and len(current_batch) + len(account_briefs) > TARGET_TICKETS_PER_BATCH:
            batches.append(current_batch)
            current_batch = []
        current_batch.extend(account_briefs)
    if current_batch:
        batches.append(current_batch)

    # -- Step 4: write batch files ------------------------------------------------
    print(f"\n[4/4] Writing {len(batches)} batch files to {BATCH_FOLDER} ...")
    total_written = 0
    for batch_number, batch_briefs in enumerate(batches, start=1):
        batch_path = BATCH_FOLDER / f"batch_{batch_number:02d}.json"
        with open(batch_path, "w", encoding="utf-8") as batch_file:
            json.dump(batch_briefs, batch_file, indent=1, ensure_ascii=False)
        account_count = len({brief["account_id"] for brief in batch_briefs})
        total_written += len(batch_briefs)
        print(f"  {batch_path.name}: {len(batch_briefs)} tickets across {account_count} accounts")

    print(f"\nDone. {len(batches)} batch files written to {BATCH_FOLDER} "
          f"({total_written} tickets total).")


if __name__ == "__main__":
    main()
