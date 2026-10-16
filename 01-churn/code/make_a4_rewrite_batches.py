"""
make_a4_rewrite_batches.py — Splits the NEW low-volume A4 briefs into batch
files for the ticket-writer agents.

Run this AFTER code/regenerate_a4_briefs.py has rewritten data/ticket_briefs.json
with the low-volume A4 design (see that script's docstring for the full
context). Only A4 accounts' briefs are extracted here — every other
archetype already has its prose written and is left alone.

Mirrors code/split_briefs.py's packing logic (whole accounts stay together
so the writer can keep persona and arc consistent) but scoped to A4 only,
with a smaller per-batch target since there are only ~46 accounts and
~190-200 briefs in total (vs. ~4,000+ for the full dataset).

Output: data/brief_batches_a4/batch_NN.json

Downstream: a ticket-writer agent turns each batch into prose in
data/tickets_raw_a4/batch_NN.json (standard raw schema — see
code/replace_a4_prose.py's docstring), which code/replace_a4_prose.py then
splices into data/tickets_raw/.
"""

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Config block
# ---------------------------------------------------------------------------

TARGET_TICKETS_PER_BATCH_A4 = 80   # smaller than split_briefs.py's 150 — A4
                                   # is a small slice (~190-200 briefs total)

SCRIPT_DIR   = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR     = PROJECT_ROOT / "data"

BRIEFS_FILE      = DATA_DIR / "ticket_briefs.json"
ANSWER_KEY_FILE  = DATA_DIR / "answer_key.csv"
BATCH_FOLDER     = DATA_DIR / "brief_batches_a4"

sys.path.insert(0, str(SCRIPT_DIR))

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("make_a4_rewrite_batches.py — batching the new low-volume A4 briefs")
    print("=" * 60)

    import pandas as pd  # local import: only needed for answer_key.csv

    # ---- Step 1: identify A4 accounts --------------------------------------
    print("\n[1/4] Loading answer_key.csv to identify A4 accounts...")
    if not ANSWER_KEY_FILE.exists():
        print(f"ERROR: {ANSWER_KEY_FILE} not found.")
        sys.exit(1)
    answer_key = pd.read_csv(ANSWER_KEY_FILE)
    a4_ids = set(answer_key.loc[answer_key["archetype"] == "A4", "account_id"])
    print(f"  {len(a4_ids)} A4 accounts identified.")

    # ---- Step 2: load briefs and keep only A4 ------------------------------
    print(f"\n[2/4] Loading {BRIEFS_FILE} and filtering to A4 accounts...")
    if not BRIEFS_FILE.exists():
        print(f"ERROR: {BRIEFS_FILE} not found. Run regenerate_a4_briefs.py first.")
        sys.exit(1)
    with open(BRIEFS_FILE, encoding="utf-8") as fh:
        all_briefs = json.load(fh)

    a4_briefs = [b for b in all_briefs if b["account_id"] in a4_ids]
    print(f"  {len(all_briefs):,} briefs total, {len(a4_briefs):,} belong to A4 accounts.")

    briefs_by_account: dict[str, list[dict]] = {}
    for brief in a4_briefs:
        briefs_by_account.setdefault(brief["account_id"], []).append(brief)

    missing_accounts = a4_ids - set(briefs_by_account.keys())
    if missing_accounts:
        print(f"  WARNING: {len(missing_accounts)} A4 accounts have no briefs at all: "
              f"{sorted(missing_accounts)}")

    print(f"  {len(briefs_by_account)} A4 accounts with briefs to batch.")

    # ---- Step 3: pack whole accounts into batches --------------------------
    print(f"\n[3/4] Packing whole accounts into batches (target "
          f"{TARGET_TICKETS_PER_BATCH_A4} tickets/batch)...")
    BATCH_FOLDER.mkdir(parents=True, exist_ok=True)

    batches: list[list[dict]] = []
    current_batch: list[dict] = []
    for account_id in sorted(briefs_by_account):
        account_briefs = briefs_by_account[account_id]
        if current_batch and len(current_batch) + len(account_briefs) > TARGET_TICKETS_PER_BATCH_A4:
            batches.append(current_batch)
            current_batch = []
        current_batch.extend(account_briefs)
    if current_batch:
        batches.append(current_batch)

    # ---- Step 4: write batch files ------------------------------------------
    print(f"\n[4/4] Writing {len(batches)} batch file(s) to {BATCH_FOLDER}...")
    for batch_number, batch_briefs in enumerate(batches, start=1):
        batch_path = BATCH_FOLDER / f"batch_{batch_number:02d}.json"
        with open(batch_path, "w", encoding="utf-8") as batch_file:
            json.dump(batch_briefs, batch_file, indent=1, ensure_ascii=False)
        account_count = len({brief["account_id"] for brief in batch_briefs})
        print(f"  {batch_path.name}: {len(batch_briefs)} tickets across {account_count} accounts")

    total_tickets = sum(len(b) for b in batches)
    total_accounts = len(briefs_by_account)
    print(f"\nDone. {len(batches)} batch file(s) written to {BATCH_FOLDER} "
          f"({total_tickets} tickets, {total_accounts} accounts).")


if __name__ == "__main__":
    main()
