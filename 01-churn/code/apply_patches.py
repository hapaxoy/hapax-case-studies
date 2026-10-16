"""Apply ticket text patches to the raw batch files, then re-run assembly.

Reads data/patch_output.json (produced by the ticket-writer patch agent) and
replaces subject/body for the matching tickets inside data/tickets_raw/batch_NN.json.
The raw batch files remain the single source of prose truth, so assembly can
always be re-run cleanly afterwards.
"""

import json
import subprocess
import sys
from pathlib import Path

# --- Paths -------------------------------------------------------------------
PROJECT_FOLDER = Path(__file__).resolve().parent.parent
DATA_FOLDER = PROJECT_FOLDER / "data"
RAW_FOLDER = DATA_FOLDER / "tickets_raw"
PATCH_OUTPUT_FILE = DATA_FOLDER / "patch_output.json"

# --- Load patches and index them by (account_id, ticket_index) ----------------
print(f"Loading {PATCH_OUTPUT_FILE} ...")
with open(PATCH_OUTPUT_FILE, encoding="utf-8") as patch_file:
    patches = json.load(patch_file)
patch_lookup = {(p["account_id"], p["ticket_index"]): p for p in patches}
print(f"  {len(patch_lookup)} patches loaded")

# --- Walk every batch file and apply matching patches -------------------------
applied_count = 0
for batch_path in sorted(RAW_FOLDER.glob("batch_*.json")):
    with open(batch_path, encoding="utf-8") as batch_file:
        batch_tickets = json.load(batch_file)

    batch_changed = False
    for ticket in batch_tickets:
        key = (ticket["account_id"], ticket["ticket_index"])
        if key in patch_lookup:
            patch = patch_lookup.pop(key)
            ticket["subject"] = patch["subject"]
            ticket["body"] = patch["body"]
            batch_changed = True
            applied_count += 1

    if batch_changed:
        with open(batch_path, "w", encoding="utf-8") as batch_file:
            json.dump(batch_tickets, batch_file, indent=1, ensure_ascii=False)
        print(f"  {batch_path.name}: patched")

print(f"\nApplied {applied_count} patches.")
if patch_lookup:
    print(f"ERROR: {len(patch_lookup)} patches had no matching ticket: {list(patch_lookup)[:5]} ...")
    sys.exit(1)

# --- Re-run assembly so tickets.csv reflects the patched prose -----------------
print("\nRe-running assembly ...")
result = subprocess.run(
    [sys.executable, str(PROJECT_FOLDER / "code" / "assemble_tickets.py")],
    capture_output=True, text=True, encoding="utf-8",
)
print(result.stdout[-600:] if result.stdout else "")
if result.returncode != 0:
    print("Assembly FAILED:")
    print(result.stderr[-1000:] if result.stderr else "")
    sys.exit(1)
print("Done — tickets.csv rebuilt with patched prose.")
