"""
assemble_tickets.py — Assemble ticket_batches into a clean tickets.csv.

Usage:
    python assemble_tickets.py            # requires all 30 batches present
    python assemble_tickets.py --partial  # proceed with whatever batches exist

Output:
    data/tickets.csv   — one row per ticket, UTF-8, no answer-key fields

Design notes:
  - Joins raw tickets to ticket_briefs on (account_id, ticket_index) to get
    sentiment_stage (used only to derive csat, then dropped).
  - csat is derived for ~25 % of resolved tickets using seeded randomness
    (seed 42). Score is correlated with sentiment_stage.
  - A4 (quietly unhappy) accounts get a "polite disengaged" csat pattern
    instead: an ~8 % fill rate (vs 25 % standard) and scores drawn mostly
    from {3, 4}, occasionally 5, never 1-2. Quietly unhappy customers skip
    surveys or answer politely rather than flag a problem — their
    dissatisfaction has to live in the ticket prose, not the metadata, which
    is exactly why the text layer is the one that catches them.
  - Nothing from the answer key (sentiment_stage, archetype_hint, planted_signal,
    competitor_mention, declining_metrics, contact fields, account_arr_eur,
    plan_tier) leaks into the output CSV.
"""

# ---------------------------------------------------------------------------
# Standard library / third-party imports
# ---------------------------------------------------------------------------

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Config — all paths and tunable values in one place
# ---------------------------------------------------------------------------

# Resolve project root relative to this script's location
PROJECT_ROOT = Path(__file__).resolve().parent.parent   # …/01 Churn/
DATA_DIR     = PROJECT_ROOT / "data"
TICKETS_RAW  = DATA_DIR / "tickets_raw"
BRIEFS_FILE  = DATA_DIR / "ticket_briefs.json"
OUTPUT_FILE  = DATA_DIR / "tickets.csv"

# Safety check: output path must not be inside tickets_raw
assert OUTPUT_FILE.parent != TICKETS_RAW, "Output path collision with input directory!"

TOTAL_BATCHES = 30                  # expected batch_01 … batch_30
CSAT_SEED     = 42                  # seeded RNG for reproducibility
CSAT_RATE     = 0.25                # fraction of resolved tickets that get a csat score

# A4 (quietly unhappy) — "polite disengaged" csat pattern: they mostly don't
# answer the survey at all, and when they do, they answer politely rather
# than flag the problem. Never 1-2: their dissatisfaction never shows up as
# a bad score, only as prose the ML-only model can't see.
A4_CSAT_RATE    = 0.08                    # much lower fill rate than the standard 25%
A4_CSAT_SCORES  = [3, 4, 5]
A4_CSAT_WEIGHTS = [0.45, 0.45, 0.10]      # mostly 3/4, occasional 5

# Mapping from sentiment_stage → (low, high) inclusive range for csat draw
# Uniform draw within range, plus small Gaussian noise that gets clipped to 1-5
CSAT_RANGES = {
    "positive":             (4, 5),
    "calm":                 (4, 5),
    "routine":              (3, 5),
    "neutral":              (3, 5),
    "feature_request":      (3, 5),
    "resolution":           (4, 5),
    "mild_frustration":     (2, 4),
    "frustrated":           (2, 4),
    "angry":                (1, 3),
    "angry_resolved":       (2, 4),
    "escalation":           (1, 3),
    "resigned":             (1, 3),
    "competitor_mention":   (1, 3),
    "unresolved_complaint": (1, 2),
}
CSAT_DEFAULT_RANGE = (2, 4)         # fallback for any unlisted stage

# ---------------------------------------------------------------------------
# Helper: derive csat scores
# ---------------------------------------------------------------------------

def derive_csat(df: pd.DataFrame, rng: np.random.Generator) -> pd.Series:
    """
    For roughly CSAT_RATE of resolved tickets, assign a 1-5 csat score
    correlated with the brief's sentiment_stage. All others are NaN.

    A4 accounts (archetype_hint == 'A4') are the exception: a much lower
    fill rate (A4_CSAT_RATE) and scores drawn from the "polite disengaged"
    distribution (A4_CSAT_SCORES / A4_CSAT_WEIGHTS) instead of the
    stage-correlated range — see module docstring for the rationale.

    Parameters
    ----------
    df : DataFrame containing 'resolved' (bool), 'sentiment_stage' (str),
         and 'archetype_hint' (str)
    rng : seeded numpy Generator for reproducibility

    Returns
    -------
    pd.Series of float (NaN for no-response, 1.0-5.0 for responses)
    """
    n = len(df)
    csat = pd.Series([pd.NA] * n, dtype="Int64", index=df.index)

    # Identify resolved tickets eligible for a csat response
    resolved_mask = df["resolved"].fillna(False).astype(bool)
    resolved_idx  = df.index[resolved_mask].tolist()

    if not resolved_idx:
        return csat

    is_a4 = df["archetype_hint"] == "A4"

    # Bernoulli draw: which resolved tickets get a csat response? A4 accounts
    # use their own (much lower) fill rate.
    fill_rates = np.where(is_a4.loc[resolved_idx].to_numpy(), A4_CSAT_RATE, CSAT_RATE)
    gets_response = rng.random(len(resolved_idx)) < fill_rates
    responding_idx = [idx for idx, flag in zip(resolved_idx, gets_response) if flag]

    # For each responding ticket, draw a score
    for idx in responding_idx:
        if is_a4.at[idx]:
            # Polite disengagement: mostly 3/4, occasionally 5, never 1-2
            score = int(rng.choice(A4_CSAT_SCORES, p=A4_CSAT_WEIGHTS))
        else:
            stage = df.at[idx, "sentiment_stage"]
            lo, hi = CSAT_RANGES.get(stage, CSAT_DEFAULT_RANGE)
            # uniform integer draw within [lo, hi]
            score = int(rng.integers(lo, hi + 1))
        csat.at[idx] = score

    return csat

# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def main(partial: bool) -> None:
    print("=" * 60)
    print("assemble_tickets.py — assembling tickets.csv")
    print("=" * 60)

    # ------------------------------------------------------------------
    # Step 1: discover which batch files are present
    # ------------------------------------------------------------------
    print("\n[1/5] Scanning tickets_raw for batch files…")

    present_nums = set()
    for path in sorted(TICKETS_RAW.glob("batch_*.json")):
        # Extract number from filename e.g. "batch_07.json" → 7
        stem = path.stem           # "batch_07"
        num_str = stem.split("_")[1]
        try:
            present_nums.add(int(num_str))
        except ValueError:
            print(f"  WARNING: unexpected filename {path.name}, skipping.")

    all_nums     = set(range(1, TOTAL_BATCHES + 1))
    missing_nums = sorted(all_nums - present_nums)
    present_nums = sorted(present_nums)

    print(f"  Found {len(present_nums)}/{TOTAL_BATCHES} batches: "
          f"{[f'batch_{n:02d}' for n in present_nums]}")
    if missing_nums:
        print(f"  MISSING batches: {[f'batch_{n:02d}' for n in missing_nums]}")
    else:
        print("  All 30 batches are present.")

    # ------------------------------------------------------------------
    # Step 2: load ticket_briefs and compute expected coverage
    # ------------------------------------------------------------------
    print("\n[2/5] Loading ticket_briefs.json…")

    if not BRIEFS_FILE.exists():
        print(f"  ERROR: briefs file not found at {BRIEFS_FILE}")
        sys.exit(1)

    with open(BRIEFS_FILE, encoding="utf-8") as f:
        briefs_raw = json.load(f)

    briefs_df = pd.DataFrame(briefs_raw)
    n_briefs  = len(briefs_df)
    print(f"  Loaded {n_briefs} brief records.")

    # Compute which brief batch numbers cover which accounts
    # Each batch file name corresponds to a slice of accounts; we track which
    # briefs belong to batches that are missing.
    # Since batches are account-ordered, we need to know how briefs map to batches.
    # We can infer this by reading each present brief_batch file to find account coverage.
    brief_batches_dir = DATA_DIR / "brief_batches"
    brief_to_batch: dict[tuple, int] = {}  # (account_id, ticket_index) → batch number

    if brief_batches_dir.exists():
        for path in sorted(brief_batches_dir.glob("batch_*.json")):
            num_str = path.stem.split("_")[1]
            try:
                batch_num = int(num_str)
            except ValueError:
                continue
            with open(path, encoding="utf-8") as f:
                batch_briefs = json.load(f)
            for b in batch_briefs:
                key = (b["account_id"], b["ticket_index"])
                brief_to_batch[key] = batch_num

    # ------------------------------------------------------------------
    # Step 3: load all present ticket batch files
    # ------------------------------------------------------------------
    print("\n[3/5] Loading ticket batch files…")

    all_tickets = []
    for num in present_nums:
        path = TICKETS_RAW / f"batch_{num:02d}.json"
        try:
            with open(path, encoding="utf-8") as f:
                batch = json.load(f)
            print(f"  batch_{num:02d}.json  →  {len(batch)} tickets")
            all_tickets.extend(batch)
        except json.JSONDecodeError as e:
            print(f"  ERROR parsing batch_{num:02d}.json: {e}")
            sys.exit(1)

    n_loaded = len(all_tickets)
    print(f"\n  Total tickets loaded: {n_loaded} / {n_briefs} briefs")

    # ------------------------------------------------------------------
    # Step 4: check completeness; exit non-zero if briefs lack tickets
    # ------------------------------------------------------------------
    print("\n[4/5] Checking coverage…")

    tickets_df = pd.DataFrame(all_tickets)

    # Build set of (account_id, ticket_index) keys from loaded tickets
    if "ticket_index" in tickets_df.columns:
        tickets_df["ticket_index"] = tickets_df["ticket_index"].astype(int)
    else:
        print("  ERROR: 'ticket_index' column missing from ticket data.")
        sys.exit(1)

    loaded_keys = set(zip(tickets_df["account_id"], tickets_df["ticket_index"]))

    # Build the same key set from briefs
    briefs_df["ticket_index"] = briefs_df["ticket_index"].astype(int)
    brief_keys = set(zip(briefs_df["account_id"], briefs_df["ticket_index"]))

    missing_keys  = brief_keys - loaded_keys
    orphan_keys   = loaded_keys - brief_keys   # tickets with no matching brief (unusual)

    if missing_keys:
        # Find which batch numbers are responsible for the missing briefs
        missing_batches = sorted({
            brief_to_batch[k] for k in missing_keys if k in brief_to_batch
        })
        untracked = [k for k in missing_keys if k not in brief_to_batch]

        print(f"  {len(missing_keys)} briefs have no written ticket yet.")
        if missing_batches:
            print(f"  Affected batch numbers: {[f'batch_{n:02d}' for n in missing_batches]}")
        if untracked:
            print(f"  {len(untracked)} missing briefs could not be mapped to a batch.")

        if not partial:
            print("\n  Run with --partial to proceed with existing tickets.")
            print("  Exiting with code 1.")
            sys.exit(1)
        else:
            print("  --partial flag set: continuing with available tickets.")
    else:
        print(f"  All {n_briefs} briefs have a corresponding ticket. Coverage complete.")

    if orphan_keys:
        print(f"  WARNING: {len(orphan_keys)} tickets have no matching brief — "
              "these will be dropped from the join.")

    # Check for duplicate (account_id, ticket_index) pairs in loaded tickets
    dup_mask = tickets_df.duplicated(subset=["account_id", "ticket_index"], keep=False)
    if dup_mask.any():
        n_dups = dup_mask.sum()
        print(f"  ERROR: {n_dups} duplicate (account_id, ticket_index) rows found "
              "in raw tickets. Cannot build a clean table.")
        print(tickets_df[dup_mask][["account_id", "ticket_index"]].head(10).to_string())
        sys.exit(1)
    else:
        print("  No duplicate keys in raw tickets.")

    # ------------------------------------------------------------------
    # Step 5: join tickets to briefs on (account_id, ticket_index)
    # ------------------------------------------------------------------
    print("\n[5/5] Joining tickets to briefs and building final table…")

    # Keep only the fields we need from briefs (sentiment_stage + archetype_hint
    # for csat derivation — A4 gets a different csat pattern, see derive_csat())
    briefs_slim = briefs_df[["account_id", "ticket_index", "sentiment_stage", "archetype_hint"]].copy()

    merged = tickets_df.merge(
        briefs_slim,
        on=["account_id", "ticket_index"],
        how="inner",        # inner join: drops tickets with no brief (orphans)
        validate="1:1",     # raises if duplicates survive
    )

    n_after_join = len(merged)
    n_dropped    = n_loaded - n_after_join
    if n_dropped > 0:
        print(f"  {n_dropped} tickets dropped (no matching brief — likely orphans).")
    print(f"  {n_after_join} tickets retained after join.")

    # ------------------------------------------------------------------
    # Step 6: derive csat scores (seeded, correlated with sentiment_stage)
    # ------------------------------------------------------------------
    rng = np.random.default_rng(CSAT_SEED)
    merged["csat"] = derive_csat(merged, rng)

    n_with_csat = merged["csat"].notna().sum()
    csat_fill_rate = n_with_csat / n_after_join if n_after_join else 0
    print(f"  csat assigned to {n_with_csat} tickets ({csat_fill_rate:.1%} fill rate).")

    a4_mask = merged["archetype_hint"] == "A4"
    if a4_mask.any():
        a4_fill_rate = merged.loc[a4_mask, "csat"].notna().mean()
        other_fill_rate = merged.loc[~a4_mask, "csat"].notna().mean()
        print(f"    A4 ('polite disengaged'): {a4_fill_rate:.1%} fill rate "
              f"({a4_mask.sum()} tickets)")
        print(f"    All other archetypes:    {other_fill_rate:.1%} fill rate")

    # ------------------------------------------------------------------
    # Step 7: build final clean table — no answer-key columns
    # ------------------------------------------------------------------
    # Sort by account then ticket index before assigning sequential ticket_id
    merged = merged.sort_values(
        ["account_id", "ticket_index"],
        ascending=[True, True],
    ).reset_index(drop=True)

    # Assign sequential ticket_id TKT00001 … TKTnnnnn
    merged["ticket_id"] = [f"TKT{i+1:05d}" for i in range(len(merged))]

    # Rename date → created_at
    merged = merged.rename(columns={"date": "created_at"})

    # Select and order output columns — deliberately excludes any answer-key fields
    output_cols = [
        "ticket_id",
        "account_id",
        "created_at",
        "channel",
        "subject",
        "body",
        "module",
        "resolved",
        "resolution_days",
        "csat",
    ]

    # Validate that no answer-key columns are accidentally present
    forbidden_cols = {"sentiment_stage", "archetype_hint", "planted_signal",
                      "competitor_mention", "declining_metrics", "contact_name",
                      "contact_title", "account_arr_eur", "plan_tier"}
    leaked = forbidden_cols & set(output_cols)
    assert not leaked, f"Answer-key columns would leak into output: {leaked}"

    final_df = merged[output_cols].copy()

    # ------------------------------------------------------------------
    # Step 8: write output CSV
    # ------------------------------------------------------------------
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    final_df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")
    print(f"\n  Written: {OUTPUT_FILE}")

    # ------------------------------------------------------------------
    # Summary report
    # ------------------------------------------------------------------
    n_accounts = final_df["account_id"].nunique()
    mean_body_words = final_df["body"].dropna().apply(
        lambda x: len(str(x).split())
    ).mean()

    channel_split = (
        final_df["channel"]
        .value_counts(normalize=True)
        .mul(100)
        .round(1)
        .to_dict()
    )
    channel_str = "  ".join(f"{ch}: {pct}%" for ch, pct in sorted(channel_split.items()))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Ticket count   : {len(final_df):,}")
    print(f"  Accounts covered: {n_accounts:,}")
    print(f"  csat fill rate : {csat_fill_rate:.1%}  ({n_with_csat} tickets)")
    print(f"  Mean body length: {mean_body_words:.0f} words")
    print(f"  Channel split  : {channel_str}")
    if missing_nums:
        print(f"\n  REMINDER: batches still missing: "
              f"{[f'batch_{n:02d}' for n in missing_nums]}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Assemble ticket batch files into a clean tickets.csv."
    )
    parser.add_argument(
        "--partial",
        action="store_true",
        help="Proceed even if some ticket batches are missing.",
    )
    args = parser.parse_args()
    main(partial=args.partial)
