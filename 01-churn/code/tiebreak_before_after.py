"""
tiebreak_before_after.py -- what moved when the top-N cuts went from row-order
tie-breaking to the explicit rule in code/ranking.py (method clarification,
6 Oct 2026).

It reproduces the OLD behaviour (stable sort on accounts.csv row order, as the
pre-fix fuse_and_evaluate.py did), applies the NEW rule, and tabulates every
published figure that depends on a top-100 (or top-50) cut. It also reports how
wide the range of outcomes was under the old behaviour: any 6 of the 23 accounts
tied at 0.55 could have made the list, so the old figure was one arbitrary draw
from a spread. The spread is computed by exact bounds plus a seeded Monte Carlo.

Reads (read-only): accounts, answer_key, tickets, ml_scores, text_scores,
fusion/combined_scores.csv. Writes only: data/fusion/tiebreak_before_after.md.

Run from the project root:
    python code/tiebreak_before_after.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

import ranking

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
OUTPUT_PATH = DATA_DIR / "fusion" / "tiebreak_before_after.md"
INPUT_PATHS = [DATA_DIR / name for name in
               ("accounts.csv", "answer_key.csv", "tickets.csv", "model/ml_scores.csv",
                "agent/text_scores.csv", "fusion/combined_scores.csv")]
assert OUTPUT_PATH.resolve() not in [p.resolve() for p in INPUT_PATHS], "output path collides with an input"

RANDOM_SEED = 42
MONTE_CARLO_DRAWS = 20000
TOP_LARGE, TOP_SMALL = 100, 50

# The figures as published before the fix (from the pre-fix results_summary.json), used
# to prove the old-behaviour reproduction below matches what was actually published.
PUBLISHED_BEFORE = {"text_recall_100": 0.594, "regions": (58, 42, 42, 358),
                    "incremental_text": 1340728, "incremental_ml": 703350}


def log(message):
    print(message, flush=True)


def old_flags(df, score_column, k):
    """Pre-fix behaviour: stable sort on score descending; ties fall back to accounts.csv row order."""
    order = np.argsort(-df[score_column].values, kind="stable")
    flags = np.zeros(len(df), dtype=bool)
    flags[order[:k]] = True
    return flags


def new_flags(df, score_column, k, arm):
    return ranking.top_k_flags_ranked(df["account_id"].values, df[score_column].values, k,
                                      last_ticket_dates=df["last_ticket_date"].values, arm=arm)


def figures(df, flags_by_arm):
    """Every published number that depends on a cut, for one set of flags."""
    churned = df["churned"].astype(bool).values
    total_churners = churned.sum()
    ml, tx, cb = flags_by_arm["ml"], flags_by_arm["text"], flags_by_arm["combined"]
    arr = df["arr_eur"].values
    a4 = (df["archetype"] == "A4").values
    a7 = (df["archetype"] == "A7").values
    out = {}
    out["Recall@100 usage"] = (churned & ml).sum() / total_churners
    out["Recall@100 text"] = (churned & tx).sum() / total_churners
    out["Recall@100 combined"] = (churned & cb).sum() / total_churners
    out["Churners in text top-100"] = int((churned & tx).sum())
    out["Region both"] = int((ml & tx).sum())
    out["Region usage only"] = int((ml & ~tx).sum())
    out["Region tickets only"] = int((~ml & tx).sum())
    out["Region neither"] = int((~ml & ~tx).sum())
    out["Churners: both"] = int((churned & ml & tx).sum())
    out["Churners: usage only"] = int((churned & ml & ~tx).sum())
    out["Churners: tickets only"] = int((churned & ~ml & tx).sum())
    out["Churners: neither"] = int((churned & ~ml & ~tx).sum())
    out["Churned ARR caught, usage top-100"] = int(arr[churned & ml].sum())
    out["Churned ARR caught, text top-100"] = int(arr[churned & tx].sum())
    out["Churned ARR caught, combined top-100"] = int(arr[churned & cb].sum())
    out["Churned ARR text surfaces, usage does not"] = int(arr[churned & tx & ~ml].sum())
    out["Churned ARR usage surfaces, text does not"] = int(arr[churned & ml & ~tx].sum())
    out["A4 in text top-100"] = int((a4 & tx).sum())
    out["A4: text minus usage"] = int((a4 & tx).sum() - (a4 & ml).sum())
    out["A7 in text top-100"] = int((a7 & tx).sum())
    out["A7 rescued out of combined top-100"] = int((a7 & tx & ~cb).sum())
    return out


def main():
    log("Loading inputs (read-only)...")
    df = (pd.read_csv(DATA_DIR / "accounts.csv")
          .merge(pd.read_csv(DATA_DIR / "answer_key.csv")[["account_id", "archetype"]], on="account_id")
          .merge(pd.read_csv(DATA_DIR / "model/ml_scores.csv"), on="account_id")
          .merge(pd.read_csv(DATA_DIR / "agent/text_scores.csv")[["account_id", "text_risk_score"]], on="account_id")
          .merge(pd.read_csv(DATA_DIR / "fusion/combined_scores.csv")[["account_id", "combined_score"]], on="account_id"))
    assert len(df) == 500
    tickets = pd.read_csv(DATA_DIR / "tickets.csv", usecols=["account_id", "created_at"])
    df["last_ticket_date"] = df["account_id"].map(ranking.last_ticket_date_by_account(tickets))

    # Old and new flags at top-100.
    old = {"ml": old_flags(df, "ml_risk_score", TOP_LARGE), "text": old_flags(df, "text_risk_score", TOP_LARGE),
           "combined": old_flags(df, "combined_score", TOP_LARGE)}
    new = {"ml": new_flags(df, "ml_risk_score", TOP_LARGE, ranking.ARM_USAGE),
           "text": new_flags(df, "text_risk_score", TOP_LARGE, ranking.ARM_TEXT),
           "combined": new_flags(df, "combined_score", TOP_LARGE, ranking.ARM_COMBINED)}
    # combined_scores.csv is rounded to 4 dp; the pipeline used unrounded scores. Cuts have no tie
    # either way, but flag a difference loudly rather than assume.
    log("Reproducing the old behaviour and checking it against the published figures...")
    before = figures(df, old)
    after = figures(df, new)
    assert round(before["Recall@100 text"], 3) == PUBLISHED_BEFORE["text_recall_100"], "old reproduction != published"
    assert (before["Region both"], before["Region usage only"], before["Region tickets only"],
            before["Region neither"]) == PUBLISHED_BEFORE["regions"], "old regions != published"
    assert before["Churned ARR text surfaces, usage does not"] == PUBLISHED_BEFORE["incremental_text"]
    assert before["Churned ARR usage surfaces, text does not"] == PUBLISHED_BEFORE["incremental_ml"]
    log("  Old behaviour reproduced exactly (matches the figures published before the fix).")

    # Which accounts changed places on the text list.
    text_cut = df["text_risk_score"].sort_values(ascending=False).iloc[TOP_LARGE - 1]
    tied_mask = df["text_risk_score"] == text_cut
    swapped_in = df[new["text"] & ~old["text"]]
    swapped_out = df[old["text"] & ~new["text"]]
    log(f"  Text score at the cut: {text_cut}; {int(tied_mask.sum())} accounts tied there; "
        f"{len(swapped_in)} swap in, {len(swapped_out)} swap out.")

    # Top-50 text cut also sits in a tie; compare old vs new.
    old50 = old_flags(df, "text_risk_score", TOP_SMALL)
    new50 = new_flags(df, "text_risk_score", TOP_SMALL, ranking.ARM_TEXT)
    churned = df["churned"].astype(bool).values
    top50_note = (f"Top-50 text cut: score at cut {df['text_risk_score'].sort_values(ascending=False).iloc[TOP_SMALL - 1]}, "
                  f"{int((df['text_risk_score'] == df['text_risk_score'].sort_values(ascending=False).iloc[TOP_SMALL - 1]).sum())} accounts tied; "
                  f"old vs new churners caught {int((churned & old50).sum())} vs {int((churned & new50).sum())}, "
                  f"ARR caught EUR {int(df.loc[churned & old50, 'arr_eur'].sum()):,} vs EUR {int(df.loc[churned & new50, 'arr_eur'].sum()):,}; "
                  f"{int((old50 != new50).sum() // 2)} account(s) swap.")
    log("  " + top50_note)

    # Spread of the old behaviour: choose which of the tied accounts fill the open slots.
    log(f"Sampling the spread of outcomes under arbitrary tie order ({MONTE_CARLO_DRAWS} seeded draws)...")
    scores = df["text_risk_score"].values
    strictly_above = scores > text_cut
    tied_positions = np.flatnonzero(scores == text_cut)
    open_slots = TOP_LARGE - int(strictly_above.sum())
    rng = np.random.default_rng(RANDOM_SEED)
    ml_flags = new["ml"]
    arr = df["arr_eur"].values
    recalls, incrementals = [], []
    for _ in range(MONTE_CARLO_DRAWS):
        chosen = rng.choice(tied_positions, size=open_slots, replace=False)
        flags = strictly_above.copy()
        flags[chosen] = True
        recalls.append((churned & flags).sum() / churned.sum())
        incrementals.append(arr[churned & flags & ~ml_flags].sum())
    recalls, incrementals = np.array(recalls), np.array(incrementals)
    spread = {
        "open_slots": open_slots, "tied": len(tied_positions),
        "recall_min": recalls.min(), "recall_max": recalls.max(),
        "inc_min": int(incrementals.min()), "inc_max": int(incrementals.max()),
        "inc_p5": int(np.percentile(incrementals, 5)), "inc_p95": int(np.percentile(incrementals, 95)),
    }
    log(f"  {open_slots} open slots among {len(tied_positions)} tied accounts. Recall@100 text range "
        f"{spread['recall_min']:.3f}-{spread['recall_max']:.3f}; incremental ARR range "
        f"EUR {spread['inc_min']:,}-{spread['inc_max']:,} (5th-95th pct {spread['inc_p5']:,}-{spread['inc_p95']:,}).")

    # Write the report.
    def fmt(label, value):
        if "Recall" in label:
            return f"{value:.1%}"
        if "ARR" in label:
            return f"EUR {value:,}"
        return str(value)

    lines = [
        "# Tie-break fix -- before / after",
        "",
        "Method clarification recorded 6 Oct 2026 (not a retune). Generated by `code/tiebreak_before_after.py`.",
        f"Rule (`code/ranking.py`): {ranking.RULE_TEXT}.",
        "",
        f"Text score at the top-100 cut: {text_cut}; {int(tied_mask.sum())} accounts tied there; "
        f"{open_slots} open slots; {len(swapped_in)} accounts swap in and {len(swapped_out)} out.",
        "",
        "| Figure | Before (row order) | After (explicit rule) | Moved |",
        "|---|---|---|---|",
    ]
    for label in before:
        moved = "yes" if before[label] != after[label] else "no"
        lines.append(f"| {label} | {fmt(label, before[label])} | {fmt(label, after[label])} | {moved} |")
    lines += ["", "## Accounts that swapped on the text top-100", "",
              "| Direction | Account | Archetype | Churned | ARR (EUR) | Last ticket |", "|---|---|---|---|---|---|"]
    for direction, frame in (("in (new rule)", swapped_in), ("out (old row order)", swapped_out)):
        for _, row in frame.iterrows():
            lines.append(f"| {direction} | {row['account_id']} | {row['archetype']} | {bool(row['churned'])} | "
                         f"{int(row['arr_eur']):,} | {str(row['last_ticket_date'])[:10]} |")
    lines += ["", "## How arbitrary the old figure was", "",
              f"Any {open_slots} of the {len(tied_positions)} accounts tied at {text_cut} could have filled the open slots under row-order "
              f"tie-breaking. Across {MONTE_CARLO_DRAWS:,} seeded random draws (seed {RANDOM_SEED}): text recall@100 ranged "
              f"{spread['recall_min']:.1%} to {spread['recall_max']:.1%}; churned ARR the text layer surfaces that usage does not ranged "
              f"EUR {spread['inc_min']:,} to EUR {spread['inc_max']:,} (5th to 95th percentile EUR {spread['inc_p5']:,} to EUR {spread['inc_p95']:,}).",
              "", top50_note, ""]
    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    log(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
