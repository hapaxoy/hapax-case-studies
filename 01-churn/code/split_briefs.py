"""Split ticket_briefs.json into batch files for the ticket-writer agents.

Groups briefs by account (an account's tickets must stay together so the
writer can keep persona and arc consistent), then packs whole accounts into
batches of roughly TARGET_TICKETS_PER_BATCH tickets each.

Output: data/brief_batches/batch_NN.json
"""

import json
from pathlib import Path

# --- Configuration ---------------------------------------------------------
TARGET_TICKETS_PER_BATCH = 150

DATA_FOLDER = Path(__file__).resolve().parent.parent / "data"
BRIEFS_FILE = DATA_FOLDER / "ticket_briefs.json"
BATCH_FOLDER = DATA_FOLDER / "brief_batches"

# --- Load briefs and group by account ---------------------------------------
print(f"Loading {BRIEFS_FILE} ...")
with open(BRIEFS_FILE, encoding="utf-8") as briefs_file:
    all_briefs = json.load(briefs_file)
print(f"  {len(all_briefs)} briefs loaded")

briefs_by_account: dict[str, list[dict]] = {}
for brief in all_briefs:
    briefs_by_account.setdefault(brief["account_id"], []).append(brief)
print(f"  {len(briefs_by_account)} accounts with tickets")

# --- Pack whole accounts into batches ---------------------------------------
BATCH_FOLDER.mkdir(parents=True, exist_ok=True)

batches: list[list[dict]] = []
current_batch: list[dict] = []
for account_id in sorted(briefs_by_account):
    account_briefs = briefs_by_account[account_id]
    # Start a new batch if adding this account would overshoot the target
    # (unless the current batch is empty — oversized accounts still get a batch)
    if current_batch and len(current_batch) + len(account_briefs) > TARGET_TICKETS_PER_BATCH:
        batches.append(current_batch)
        current_batch = []
    current_batch.extend(account_briefs)
if current_batch:
    batches.append(current_batch)

# --- Write batch files -------------------------------------------------------
for batch_number, batch_briefs in enumerate(batches, start=1):
    batch_path = BATCH_FOLDER / f"batch_{batch_number:02d}.json"
    with open(batch_path, "w", encoding="utf-8") as batch_file:
        json.dump(batch_briefs, batch_file, indent=1, ensure_ascii=False)
    account_count = len({brief["account_id"] for brief in batch_briefs})
    print(f"  {batch_path.name}: {len(batch_briefs)} tickets across {account_count} accounts")

print(f"\nDone. {len(batches)} batch files written to {BATCH_FOLDER}")
