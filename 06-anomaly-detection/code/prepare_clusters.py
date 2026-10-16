"""
prepare_clusters.py -- Phase 3 cluster preparation.

Implements the pre-registered "Cluster preparation" rule exactly,
reading data/analysis/rule_flags.csv, data/analysis/detector_flags.csv, and
gl_transactions.csv (one of the four public CSVs -- vendor_master.csv and
chart_of_accounts.csv are not needed here). Never reads, imports, or
references anything under data/answer_key/.

The rule:
  (a) rule flags group by vendor into one unit per vendor, EXCEPT
      calendar-test flags, which group by posted_by (the story is the
      user, not the vendor).
  (b) detector flags group by vendor where a vendor has >= 3 flags.
  (c) then by calendar month where a month still holds >= 15 ungrouped
      detector flags.
  (d) the top 10 remaining detector singletons by anomaly score form one
      "notable singles" unit.
  (e) everything left is one "residual tail" unit.

Two independent partitions are produced and each is asserted complete and
disjoint on its own domain:
  - every one of the rule_flags.csv rows (64, pre-registered) lands in
    exactly one RU-* unit (rule_vendor or rule_user).
  - every one of the detector_flags.csv rows (~200) lands in exactly one
    DU-* / SINGLES / RESIDUAL unit.
A transaction that was flagged by BOTH layers legitimately appears in one
unit from each partition (the design: "incidental detector flags on
D/R/S/W/A members are permitted"; the evaluation counts 64 rule + 200 detector
= 264 flags being partitioned, not a deduplicated transaction count).

Writes data/analysis/clusters.json: a single top-level JSON array of unit
objects, in a fixed deterministic order (by type, then by grouping key).

Run from the project root or from code/ -- after run_rule_layer.py and
detect_anomalies.py:
    python code/prepare_clusters.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
ANALYSIS_DIR = DATA_DIR / "analysis"

# ---------------------------------------------------------------------------
# Config block -- the cluster-preparation thresholds, pinned in the
# design.
# ---------------------------------------------------------------------------

CALENDAR_TEST_NAME = "calendar"
DETECTOR_VENDOR_MIN_FLAGS = 3    # (b) vendor grouping threshold
DETECTOR_MONTH_MIN_FLAGS = 15    # (c) month grouping threshold
DETECTOR_SINGLES_TOP_N = 10      # (d) "notable singles" unit size

# Month grouping uses posting_date's month (consistent with detect_anomalies.py's
# month_index feature and with the calendar test's own posting_date basis).


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_inputs() -> tuple:
    """Load gl_transactions.csv plus the two Phase-3 analysis outputs.
    Deliberately never touches data/answer_key/."""
    gl_path = DATA_DIR / "gl_transactions.csv"
    rule_flags_path = ANALYSIS_DIR / "rule_flags.csv"
    detector_flags_path = ANALYSIS_DIR / "detector_flags.csv"

    missing = [p for p in (gl_path, rule_flags_path, detector_flags_path) if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing required input file(s): {[str(p) for p in missing]}. "
            f"Run run_rule_layer.py and detect_anomalies.py first."
        )

    gl_df = pd.read_csv(gl_path)
    rule_flags_df = pd.read_csv(rule_flags_path)
    detector_flags_df = pd.read_csv(detector_flags_path)
    return gl_df, rule_flags_df, detector_flags_df


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stats_block(group: pd.DataFrame, *, tests_involved=None, score_range=None) -> dict:
    """Build the compact stats block shared by every unit type."""
    stats = {
        "n_flags": int(len(group)),
        "months_touched": sorted(int(m) for m in group["month"].unique()),
        "total_eur": round(float(group.drop_duplicates("txn_id")["amount_eur"].sum()), 2),
    }
    if tests_involved is not None:
        stats["tests_involved"] = tests_involved
    if score_range is not None:
        stats["score_range"] = score_range
    return stats


def _score_range(group: pd.DataFrame) -> list:
    if len(group) == 0:
        return [None, None]
    return [round(float(group["anomaly_score"].min()), 6), round(float(group["anomaly_score"].max()), 6)]


# ---------------------------------------------------------------------------
# Rule-side partition -- (a)
# ---------------------------------------------------------------------------

def build_rule_units(rule_flags_df: pd.DataFrame, gl_lookup: pd.DataFrame) -> list:
    rule_joined = rule_flags_df.merge(gl_lookup, on="txn_id", how="left")
    unmatched = rule_joined[rule_joined["vendor_id"].isna()]
    if len(unmatched):
        raise ValueError(
            f"{len(unmatched)} rule-flagged txn_id(s) not found in gl_transactions.csv: "
            f"{unmatched['txn_id'].tolist()[:5]}"
        )

    calendar_rows = rule_joined[rule_joined["test"] == CALENDAR_TEST_NAME]
    non_calendar_rows = rule_joined[rule_joined["test"] != CALENDAR_TEST_NAME]

    rule_vendor_units = []
    for vendor_id, group in non_calendar_rows.groupby("vendor_id", sort=True):
        rule_vendor_units.append({
            "unit_type": "rule_vendor",
            "group_key": vendor_id,
            "txn_ids": sorted(group["txn_id"].unique().tolist()),
            "stats": _stats_block(group, tests_involved=sorted(group["test"].unique().tolist())),
        })

    rule_user_units = []
    for posted_by, group in calendar_rows.groupby("posted_by", sort=True):
        rule_user_units.append({
            "unit_type": "rule_user",
            "group_key": posted_by,
            "txn_ids": sorted(group["txn_id"].unique().tolist()),
            "stats": _stats_block(group, tests_involved=sorted(group["test"].unique().tolist())),
        })

    # Deterministic ordering: by type (rule_vendor before rule_user, mirroring
    # the design's own listing order), then by grouping key ascending.
    units = rule_vendor_units + rule_user_units
    for i, unit in enumerate(units, start=1):
        unit["unit_id"] = f"RU-{i:02d}"
    return units


# ---------------------------------------------------------------------------
# Detector-side partition -- (b), (c), (d), (e)
# ---------------------------------------------------------------------------

def build_detector_units(detector_flags_df: pd.DataFrame, gl_lookup: pd.DataFrame) -> list:
    det_joined = detector_flags_df.merge(gl_lookup, on="txn_id", how="left")
    unmatched = det_joined[det_joined["vendor_id"].isna()]
    if len(unmatched):
        raise ValueError(
            f"{len(unmatched)} detector-flagged txn_id(s) not found in gl_transactions.csv: "
            f"{unmatched['txn_id'].tolist()[:5]}"
        )

    remaining = det_joined.copy()

    # (b) vendor grouping, >= 3 flags
    detector_vendor_units = []
    vendor_flag_counts = remaining.groupby("vendor_id").size()
    qualifying_vendors = sorted(vendor_flag_counts[vendor_flag_counts >= DETECTOR_VENDOR_MIN_FLAGS].index.tolist())
    for vendor_id in qualifying_vendors:
        group = remaining[remaining["vendor_id"] == vendor_id]
        txn_ids = sorted(group["txn_id"].unique().tolist())
        detector_vendor_units.append({
            "unit_type": "detector_vendor",
            "group_key": vendor_id,
            "txn_ids": txn_ids,
            "stats": _stats_block(group, score_range=_score_range(group)),
        })
        remaining = remaining[~remaining["txn_id"].isin(txn_ids)]

    # (c) month grouping on what's left, >= 15 ungrouped flags
    detector_month_units = []
    month_flag_counts = remaining.groupby("month").size()
    qualifying_months = sorted(month_flag_counts[month_flag_counts >= DETECTOR_MONTH_MIN_FLAGS].index.tolist())
    for month in qualifying_months:
        group = remaining[remaining["month"] == month]
        txn_ids = sorted(group["txn_id"].unique().tolist())
        detector_month_units.append({
            "unit_type": "detector_month",
            "group_key": int(month),
            "txn_ids": txn_ids,
            "stats": _stats_block(group, score_range=_score_range(group)),
        })
        remaining = remaining[~remaining["txn_id"].isin(txn_ids)]

    grouped_units = detector_vendor_units + detector_month_units
    for i, unit in enumerate(grouped_units, start=1):
        unit["unit_id"] = f"DU-{i:02d}"

    # (d) top 10 remaining singletons by anomaly score (descending), tie-break
    # on txn_id ascending for a fully deterministic selection.
    remaining_sorted = remaining.sort_values(["anomaly_score", "txn_id"], ascending=[False, True])
    n_singles = min(DETECTOR_SINGLES_TOP_N, len(remaining_sorted))
    if n_singles < DETECTOR_SINGLES_TOP_N:
        print(
            f"  NOTE: only {n_singles} detector flags remained for the notable-singles "
            f"unit (fewer than the designed {DETECTOR_SINGLES_TOP_N})."
        )
    singles_group = remaining_sorted.iloc[:n_singles]
    singles_txn_ids = sorted(singles_group["txn_id"].tolist())
    singles_unit = {
        "unit_id": "SINGLES",
        "unit_type": "detector_singles",
        "group_key": None,
        "txn_ids": singles_txn_ids,
        "stats": _stats_block(singles_group, score_range=_score_range(singles_group)),
    }
    remaining = remaining[~remaining["txn_id"].isin(singles_txn_ids)]

    # (e) everything left -> one residual tail unit
    residual_unit = {
        "unit_id": "RESIDUAL",
        "unit_type": "detector_residual",
        "group_key": None,
        "txn_ids": sorted(remaining["txn_id"].tolist()),
        "stats": _stats_block(remaining, score_range=_score_range(remaining)),
    }

    return grouped_units + [singles_unit, residual_unit]


# ---------------------------------------------------------------------------
# Partition assertions -- every flag belongs to exactly one unit, per layer
# ---------------------------------------------------------------------------

def assert_partition(units: list, expected_txn_ids: set, layer_name: str) -> None:
    covered = set()
    for unit in units:
        overlap = covered & set(unit["txn_ids"])
        if overlap:
            raise AssertionError(
                f"{layer_name}: txn_id(s) {sorted(overlap)[:5]} assigned to more than one unit "
                f"(found while adding unit {unit['unit_id']})."
            )
        covered.update(unit["txn_ids"])
    if covered != expected_txn_ids:
        missing = expected_txn_ids - covered
        extra = covered - expected_txn_ids
        raise AssertionError(
            f"{layer_name}: partition is not complete. "
            f"Missing {len(missing)} (e.g. {sorted(missing)[:5]}), "
            f"extra {len(extra)} (e.g. {sorted(extra)[:5]})."
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("prepare_clusters.py -- Phase 3 cluster preparation")
    print("=" * 70)

    if ANALYSIS_DIR.resolve() == DATA_DIR.resolve():
        raise RuntimeError("Output path must not equal an input path.")
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

    print("\nLoading inputs (gl_transactions.csv, rule_flags.csv, detector_flags.csv)...")
    gl_df, rule_flags_df, detector_flags_df = load_inputs()
    print(f"  gl_transactions:     {len(gl_df):,} rows")
    print(f"  rule_flags:          {len(rule_flags_df)} rows")
    print(f"  detector_flags:      {len(detector_flags_df)} rows")

    gl_df = gl_df.copy()
    gl_df["month"] = pd.to_datetime(gl_df["posting_date"]).dt.month
    gl_lookup = gl_df[["txn_id", "vendor_id", "posted_by", "amount_eur", "month"]]

    print("\nBuilding rule-side units (rule_vendor, except calendar -> rule_user)...")
    rule_units = build_rule_units(rule_flags_df, gl_lookup)
    assert_partition(rule_units, set(rule_flags_df["txn_id"]), "rule-side")
    print(f"  {len(rule_units)} rule-side units built and verified complete/disjoint.")

    print("\nBuilding detector-side units (vendor >=3, then month >=15, then top-10 singles, then residual)...")
    detector_units = build_detector_units(detector_flags_df, gl_lookup)
    assert_partition(detector_units, set(detector_flags_df["txn_id"]), "detector-side")
    print(f"  {len(detector_units)} detector-side units built and verified complete/disjoint.")

    all_units = rule_units + detector_units

    output_path = ANALYSIS_DIR / "clusters.json"
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(all_units, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {len(all_units)} verdict units to {output_path}\n")
    print(f"{'unit_id':<10}{'unit_type':<18}{'key':<12}{'n_flags':>8}{'total_eur':>14}")
    print("-" * 62)
    for unit in all_units:
        key_str = "-" if unit["group_key"] is None else str(unit["group_key"])
        print(
            f"{unit['unit_id']:<10}{unit['unit_type']:<18}{key_str:<12}"
            f"{unit['stats']['n_flags']:>8}{unit['stats']['total_eur']:>14,.2f}"
        )

    total_rule_flags = sum(u["stats"]["n_flags"] for u in rule_units)
    total_detector_flags = sum(u["stats"]["n_flags"] for u in detector_units)
    print("-" * 62)
    print(f"Rule-side total: {total_rule_flags} flags across {len(rule_units)} units")
    print(f"Detector-side total: {total_detector_flags} flags across {len(detector_units)} units")
    print(f"Combined: {total_rule_flags + total_detector_flags} flags across {len(all_units)} units")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nFATAL: {exc}")
        sys.exit(1)
