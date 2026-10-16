"""
fix_a4_ticket_metadata.py — "Close-the-tickets" design fix for archetype A4.

Design context (see data/model/ml_report.md's
"A4 before -> after" section): A4 ("quietly unhappy") accounts are supposed to
be detectable ONLY from ticket prose, never from structured ticket metadata.
The v2 ML re-run (post ticket-date-fix, post csat-quieting) showed A4's
unresolved-ticket rate and slow resolution_days were still leaking the signal
to the classical model (A4 mean risk score 0.666, 67% of A4 accounts in the
top-100 — see ml_report.md "A4 is still not fully invisible to the classical
model").

The fix: A4 tickets get CLOSED by support
("resolved") even though the underlying fix does not hold — the notorious
real-world support pattern of "ticket marked resolved, problem persists."
Support closes A4 tickets promptly (resolution_days drawn 1-5, same as any
other quickly-handled ticket) but the account's dissatisfaction survives only
in later tickets' prose ("the fix from October did not hold, we've set up a
workaround" — prose already written, untouched by this script). This removes
the ticket OUTCOME leak (unresolved_count_6m, mean_resolution_days_6m)
without touching a single word of ticket text.

What this script does:
  1. Backs up the CURRENT data/ticket_briefs.json (the v2 post-date-fix state)
     to data/ticket_briefs_v2_a4unresolved.json, so the pre-fix state is
     recoverable. Skipped (with a warning) if that backup already exists —
     re-running this script must never overwrite the one true "before" snapshot
     with an already-fixed state.
  2. For every ticket brief belonging to an A4 account (per answer_key.csv)
     that was previously unresolved: sets resolved = True and draws
     resolution_days from a seeded uniform integer in [1, 5] (support closes
     promptly). Already-resolved A4 tickets are left completely alone —
     their existing resolution_days is untouched.
  3. Applies the EXACT SAME (account_id, ticket_index) -> resolution_days
     mapping to the matching records in data/tickets_raw/batch_*.json — only
     the resolved and resolution_days fields, never subject/body/channel/date.
     The mapping is computed once so the brief and the raw ticket always agree.
  4. Prints a before/after per-archetype unresolved-ticket table.

Never touches usage_monthly.csv, accounts.csv, answer_key.csv, or any ticket
prose. Must be followed by re-running assemble_tickets.py, build_features.py,
train_models.py, and make_assessment_batches.py (see the README
pipeline order) to propagate the fix downstream.

Run from the project root:
    python code/fix_a4_ticket_metadata.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Resolve paths — this script only ever writes to files explicitly named below
# ---------------------------------------------------------------------------

SCRIPT_DIR   = Path(__file__).resolve().parent            # .../code/
PROJECT_ROOT = SCRIPT_DIR.parent                            # .../01 Churn/
DATA_DIR     = PROJECT_ROOT / "data"

ANSWER_KEY_PATH   = DATA_DIR / "answer_key.csv"
BRIEFS_PATH       = DATA_DIR / "ticket_briefs.json"
BRIEFS_BACKUP_PATH = DATA_DIR / "ticket_briefs_v2_a4unresolved.json"
TICKETS_RAW_DIR   = DATA_DIR / "tickets_raw"

# Safety: this script overwrites BRIEFS_PATH and files inside TICKETS_RAW_DIR
# in place (they are the designated "source of prose truth" for the metadata
# fields being fixed here — see module docstring), but the backup path must
# never collide with the file it is backing up, and answer_key.csv (the only
# read-only reference input) must never be touched.
assert BRIEFS_BACKUP_PATH.resolve() != BRIEFS_PATH.resolve(), (
    "Refusing to run: backup path collides with the file being backed up"
)
assert ANSWER_KEY_PATH.resolve() != BRIEFS_PATH.resolve(), (
    "Refusing to run: answer_key path collides with briefs path"
)

# ---------------------------------------------------------------------------
# Config block
# ---------------------------------------------------------------------------

sys.path.insert(0, str(SCRIPT_DIR))
import config  # noqa: E402  (must come after sys.path insert)

# Fresh seed offset for this fix — deliberately distinct from TICKET_SEED
# (config.RANDOM_SEED + 1000, used in generate_ticket_briefs.py) and CSAT_SEED
# (42, used in assemble_tickets.py) so this draw never accidentally reuses
# another script's random stream.
A4_CLOSE_SEED = config.RANDOM_SEED + 4000

# Support closes A4 tickets promptly — resolution_days drawn uniformly from
# this inclusive range. The fix not holding is a prose-layer fact, not a
# metadata one; from the metadata's point of view this is just a normal,
# fast resolution.
A4_CLOSE_RESOLUTION_DAYS_MIN = 1
A4_CLOSE_RESOLUTION_DAYS_MAX = 5   # inclusive


# ---------------------------------------------------------------------------
# Step 1: load answer key + ticket briefs
# ---------------------------------------------------------------------------

def load_inputs() -> tuple[dict, list]:
    """Loads answer_key.csv (account_id -> archetype) and ticket_briefs.json."""
    if not ANSWER_KEY_PATH.exists():
        print(f"ERROR: {ANSWER_KEY_PATH} not found.")
        sys.exit(1)
    if not BRIEFS_PATH.exists():
        print(f"ERROR: {BRIEFS_PATH} not found.")
        sys.exit(1)

    answer_key_df = pd.read_csv(ANSWER_KEY_PATH)
    archetype_by_account = dict(zip(answer_key_df["account_id"], answer_key_df["archetype"]))

    with open(BRIEFS_PATH, encoding="utf-8") as fh:
        briefs = json.load(fh)

    return archetype_by_account, briefs


# ---------------------------------------------------------------------------
# Step 2: back up the pre-fix (v2) ticket_briefs.json
# ---------------------------------------------------------------------------

def backup_briefs() -> None:
    """Copies the current ticket_briefs.json to the v2 backup path, unless
    that backup already exists (re-running this script must never clobber
    the one true 'before' snapshot with an already-fixed state)."""
    if BRIEFS_BACKUP_PATH.exists():
        print(f"  Backup already exists at {BRIEFS_BACKUP_PATH.name} — skipping "
              f"(not overwriting a possibly-already-fixed file onto the pre-fix snapshot).")
        return

    with open(BRIEFS_PATH, encoding="utf-8") as fh:
        current_content = fh.read()
    with open(BRIEFS_BACKUP_PATH, "w", encoding="utf-8") as fh:
        fh.write(current_content)
    print(f"  Backed up {BRIEFS_PATH.name} -> {BRIEFS_BACKUP_PATH.name}")


# ---------------------------------------------------------------------------
# Per-archetype unresolved-ticket summary
# ---------------------------------------------------------------------------

def summarize_unresolved(briefs: list, archetype_by_account: dict) -> pd.DataFrame:
    """Returns a per-archetype table of ticket count, unresolved count, and rate."""
    df = pd.DataFrame(briefs)
    df["archetype"] = df["account_id"].map(archetype_by_account)
    summary = (
        df.groupby("archetype")
        .agg(
            n_tickets=("resolved", "size"),
            n_unresolved=("resolved", lambda s: int((~s.astype(bool)).sum())),
        )
        .reset_index()
    )
    summary["unresolved_rate"] = summary["n_unresolved"] / summary["n_tickets"]
    return summary.sort_values("archetype")


# ---------------------------------------------------------------------------
# Step 3: build the (account_id, ticket_index) -> resolution_days mapping for
# previously-unresolved A4 tickets, and apply it to the briefs in place
# ---------------------------------------------------------------------------

def build_and_apply_fix(briefs: list, archetype_by_account: dict) -> dict:
    """
    Identifies every A4 brief that was unresolved, draws a seeded
    resolution_days in [1, 5] for each (in deterministic account_id/
    ticket_index order), and mutates the brief dicts in place: resolved ->
    True, resolution_days -> the drawn value. Already-resolved A4 tickets and
    all non-A4 tickets are left completely untouched.

    Returns the mapping {(account_id, ticket_index): resolution_days} so the
    exact same values can be applied to tickets_raw/batch_*.json.
    """
    # Find every A4 brief that is currently unresolved, in deterministic order
    a4_unresolved_keys = sorted(
        (b["account_id"], b["ticket_index"])
        for b in briefs
        if archetype_by_account.get(b["account_id"]) == "A4" and not b["resolved"]
    )

    rng = np.random.default_rng(A4_CLOSE_SEED)
    mapping = {}
    for key in a4_unresolved_keys:
        days = int(rng.integers(A4_CLOSE_RESOLUTION_DAYS_MIN, A4_CLOSE_RESOLUTION_DAYS_MAX + 1))
        mapping[key] = days

    # Apply to the briefs in place
    applied = 0
    for brief in briefs:
        key = (brief["account_id"], brief["ticket_index"])
        if key in mapping:
            brief["resolved"] = True
            brief["resolution_days"] = mapping[key]
            applied += 1

    assert applied == len(mapping), (
        f"Mismatch applying fix to briefs: {applied} briefs updated vs {len(mapping)} keys in mapping"
    )

    return mapping


# ---------------------------------------------------------------------------
# Step 4: apply the same mapping to tickets_raw/batch_*.json
# ---------------------------------------------------------------------------

def apply_fix_to_raw_batches(mapping: dict) -> None:
    """
    Walks every data/tickets_raw/batch_*.json file and, for any ticket whose
    (account_id, ticket_index) is in the mapping, sets resolved = True and
    resolution_days = mapping[key] — nothing else on that record is touched
    (subject, body, channel, date are left completely alone).
    """
    if not TICKETS_RAW_DIR.exists():
        print(f"  WARNING: {TICKETS_RAW_DIR} not found — no raw batches to fix.")
        return

    batch_paths = sorted(TICKETS_RAW_DIR.glob("batch_*.json"))
    if not batch_paths:
        print(f"  WARNING: no batch_*.json files found under {TICKETS_RAW_DIR}.")
        return

    remaining_keys = set(mapping.keys())
    total_flipped = 0

    for path in batch_paths:
        with open(path, encoding="utf-8") as fh:
            batch = json.load(fh)

        flipped_in_batch = 0
        for ticket in batch:
            key = (ticket["account_id"], ticket["ticket_index"])
            if key in mapping:
                ticket["resolved"] = True
                ticket["resolution_days"] = mapping[key]
                flipped_in_batch += 1
                remaining_keys.discard(key)

        if flipped_in_batch > 0:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(batch, fh, indent=2, ensure_ascii=False)
            print(f"  {path.name}: {flipped_in_batch} ticket(s) flipped to resolved")

        total_flipped += flipped_in_batch

    print(f"  Total tickets flipped across raw batches: {total_flipped} / {len(mapping)} mapped keys")
    if remaining_keys:
        print(f"  WARNING: {len(remaining_keys)} mapped keys were never found in any raw batch file "
              f"(first few: {sorted(remaining_keys)[:5]})")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("fix_a4_ticket_metadata.py — close-the-tickets fix for A4")
    print(f"Seed: {A4_CLOSE_SEED}")
    print("=" * 70)

    print("\n[1/5] Loading answer_key.csv and ticket_briefs.json...")
    archetype_by_account, briefs = load_inputs()
    print(f"  {len(archetype_by_account)} accounts in answer key, {len(briefs):,} ticket briefs loaded")

    print("\n[2/5] Backing up pre-fix ticket_briefs.json...")
    backup_briefs()

    print("\n[3/5] Computing BEFORE per-archetype unresolved-ticket rates...")
    before_summary = summarize_unresolved(briefs, archetype_by_account)
    print(before_summary.round(4).to_string(index=False))

    print("\n[4/5] Applying close-the-tickets fix to A4 briefs...")
    mapping = build_and_apply_fix(briefs, archetype_by_account)
    print(f"  {len(mapping)} previously-unresolved A4 tickets flipped to resolved "
          f"(resolution_days drawn 1-{A4_CLOSE_RESOLUTION_DAYS_MAX})")

    # Write the fixed briefs back to ticket_briefs.json
    with open(BRIEFS_PATH, "w", encoding="utf-8") as fh:
        json.dump(briefs, fh, indent=2, ensure_ascii=False, default=str)
    print(f"  Written: {BRIEFS_PATH}")

    print("\n[5/5] Applying the same fix to data/tickets_raw/batch_*.json...")
    apply_fix_to_raw_batches(mapping)

    print("\nComputing AFTER per-archetype unresolved-ticket rates...")
    after_summary = summarize_unresolved(briefs, archetype_by_account)
    print(after_summary.round(4).to_string(index=False))

    # ------------------------------------------------------------------
    # Before/after comparison table (the number this whole fix exists to move)
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("BEFORE -> AFTER: unresolved-ticket rate by archetype")
    print("=" * 70)
    comparison = before_summary.merge(
        after_summary, on="archetype", suffixes=("_before", "_after")
    )
    comparison["rate_before_pct"] = comparison["unresolved_rate_before"] * 100
    comparison["rate_after_pct"] = comparison["unresolved_rate_after"] * 100
    print(
        comparison[["archetype", "n_tickets_before", "n_unresolved_before", "rate_before_pct",
                    "n_unresolved_after", "rate_after_pct"]]
        .round(2)
        .to_string(index=False)
    )

    a4_before = comparison.loc[comparison["archetype"] == "A4"].iloc[0]
    print(f"\nA4 unresolved rate: {a4_before['rate_before_pct']:.2f}% -> {a4_before['rate_after_pct']:.2f}%")
    other_after_max = comparison.loc[comparison["archetype"] != "A4", "rate_after_pct"].max()
    print(f"Highest unresolved rate among OTHER archetypes (after): {other_after_max:.2f}%")
    if a4_before["rate_after_pct"] <= other_after_max + 1e-9:
        print("OK: A4's post-fix unresolved rate is now at or below every other archetype.")
    else:
        print("WARNING: A4's post-fix unresolved rate is still above at least one other archetype "
              "— investigate before proceeding downstream.")

    print("\nDone. Next: re-run validate_data.py, then assemble_tickets.py, build_features.py, "
          "train_models.py, and make_assessment_batches.py.")
    print("=" * 70)


if __name__ == "__main__":
    main()
