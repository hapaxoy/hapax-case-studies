"""
detect_anomalies.py -- Phase 3 Isolation Forest detector.

Reads ONLY the public CSVs (gl_transactions.csv, company_calendar.csv --
two of the four public tables; vendor_master.csv and chart_of_accounts.csv
are not needed by any of the eight features below). Never reads, imports,
or references anything under data/answer_key/.

Computes the eight pre-registered detector features, with the pinned
edge-case handling, fits a single
IsolationForest, and writes:
    data/analysis/detector_scores.csv  -- txn_id, anomaly_score for all rows
    data/analysis/detector_flags.csv   -- txn_id, anomaly_score, rank for the
                                           flagged tail (contamination-selected)

Determinism is asserted, not just claimed: the whole feature-build-and-fit
pipeline runs twice in this one process, the second run's outputs are
written to temp files, SHA-256 hashes of both runs are compared, and the
temp files are deleted. A prior determinism
spike (scikit-learn 1.9.0, IsolationForest(n_estimators=200,
contamination=0.004, random_state=42, n_jobs=1), PASS across two fresh
processes on a synthetic matrix) -- this script re-verifies it against the
real feature matrix every time it runs.

Run from the project root or from code/:
    python code/detect_anomalies.py
"""

import hashlib
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import IsolationForest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
ANALYSIS_DIR = DATA_DIR / "analysis"

# ---------------------------------------------------------------------------
# Config block -- every tunable for this script lives here (the design pins
# all of these numbers exactly; nothing here is free to retune).
# ---------------------------------------------------------------------------

ISOLATION_FOREST_PARAMS = dict(
    n_estimators=200,
    contamination=0.004,   # -> exactly 200 of 50,000 rows targeted (by design)
    random_state=42,
    n_jobs=1,               # single-threaded on purpose -- determinism spike
)

# Fixed feature order (the pre-registered list 1-8). Row order and
# column order are both held fixed across the two determinism-check fits.
FEATURE_COLUMNS = [
    "log10_amount",
    "vendor_amount_z",
    "cadence_ratio",
    "day_of_week",
    "non_working_flag",
    "account_rarity",
    "month_index",
    "vendor_month_volume_z",
]

# Pinned edge-case thresholds.
VENDOR_AMOUNT_Z_MIN_TXNS = 5
VENDOR_AMOUNT_Z_MIN_STD_EUR = 1.0
CADENCE_MIN_TXNS = 3
CADENCE_NEUTRAL_VALUE = 1.0

# A sanity band around the designed ~200-flag outcome ("contamination
# 0.004 -> exactly 200 flags of 50,000"). This is a reported
# check, not a retune -- per the design, any deviation at Phase 3 is frozen
# and reported, never tuned away.
EXPECTED_FLAG_COUNT = 200
FLAG_COUNT_SANITY_BAND = (190, 210)

# Interpretation choices (not pinned verbatim in the design; recorded
# here):
#   - day_of_week, non_working_flag and month_index use posting_date (the
#     field the company_calendar / rule-9 calendar test itself is keyed on).
#   - cadence_ratio uses invoice_date (the field validator rule 5's own
#     "cadence consistency" concept is keyed on -- inter-invoice timing).
#   - vendor_amount_z is date-independent (amount only).


# ---------------------------------------------------------------------------
# Data loading -- public CSVs only
# ---------------------------------------------------------------------------

def load_public_csvs() -> tuple:
    """Load the two public CSVs the detector needs. Deliberately never
    touches data/answer_key/."""
    paths = {
        "gl": DATA_DIR / "gl_transactions.csv",
        "calendar": DATA_DIR / "company_calendar.csv",
    }
    missing = [name for name, p in paths.items() if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing required input file(s): {missing}. "
            f"Run code/generate_ledger.py (Phase 2) first."
        )
    gl_df = pd.read_csv(paths["gl"])
    calendar_df = pd.read_csv(paths["calendar"])
    return gl_df, calendar_df


# ---------------------------------------------------------------------------
# Feature engineering -- the eight pre-registered features
# ---------------------------------------------------------------------------

def compute_features(gl_df: pd.DataFrame, calendar_df: pd.DataFrame) -> pd.DataFrame:
    """Compute all eight detector features for every transaction, with the
    pinned edge-case handling. Returns a DataFrame sorted by txn_id (a fixed,
    deterministic row order that both determinism-check fits share)."""

    gl = gl_df.sort_values("txn_id").reset_index(drop=True).copy()
    gl["invoice_dt"] = pd.to_datetime(gl["invoice_date"])
    gl["posting_dt"] = pd.to_datetime(gl["posting_date"])

    # -- 1. log10_amount --
    if (gl["amount_eur"] <= 0).any():
        raise ValueError(
            "amount_eur must be strictly positive for every row -- found "
            f"{(gl['amount_eur'] <= 0).sum()} non-positive amount(s)."
        )
    gl["log10_amount"] = np.log10(gl["amount_eur"])

    # -- 4. day_of_week (posting_date basis; Mon=0..Sun=6) --
    gl["day_of_week"] = gl["posting_dt"].dt.weekday

    # -- 7. month_index (posting_date basis; 1-12) --
    gl["month_index"] = gl["posting_dt"].dt.month

    # -- 5. non_working_flag (posting_date basis; 0/1 per company_calendar) --
    # String-keyed lookup mirrors rule_tests.py's own calendar-test style
    # (both posting_date and calendar's date column are ISO 'YYYY-MM-DD'
    # strings already, so no date-parsing round trip is needed here).
    working_by_date = dict(zip(calendar_df["date"], calendar_df["is_working_day"]))
    gl["non_working_flag"] = (
        ~gl["posting_date"].map(working_by_date).astype(bool)
    ).astype(int)

    # -- 2. vendor_amount_z --
    # (amount - vendor's full-year mean) / vendor's full-year std;
    # vendors with < 5 transactions or std < EUR1 -> 0.
    vendor_amount_stats = (
        gl.groupby("vendor_id")["amount_eur"]
        .agg(vendor_amount_mean="mean", vendor_amount_std="std", vendor_amount_n="count")
        .reset_index()
    )
    gl = gl.merge(vendor_amount_stats, on="vendor_id", how="left")
    amount_z_invalid = (
        (gl["vendor_amount_n"] < VENDOR_AMOUNT_Z_MIN_TXNS)
        | gl["vendor_amount_std"].isna()
        | (gl["vendor_amount_std"] < VENDOR_AMOUNT_Z_MIN_STD_EUR)
    )
    gl["vendor_amount_z"] = np.where(
        amount_z_invalid,
        0.0,
        (gl["amount_eur"] - gl["vendor_amount_mean"]) / gl["vendor_amount_std"],
    )

    # -- 6. account_rarity --
    # 1 - (count of this account among the vendor's transactions / the
    # vendor's transaction count); single-transaction vendors -> 0 (the
    # formula already yields 0 in that case: 1 - (1/1) = 0).
    account_counts = (
        gl.groupby(["vendor_id", "account"]).size().rename("vendor_account_count").reset_index()
    )
    vendor_totals = gl.groupby("vendor_id").size().rename("vendor_total_txns").reset_index()
    gl = gl.merge(account_counts, on=["vendor_id", "account"], how="left")
    gl = gl.merge(vendor_totals, on="vendor_id", how="left")
    gl["account_rarity"] = 1.0 - (gl["vendor_account_count"] / gl["vendor_total_txns"])

    # -- 8. vendor_month_volume_z --
    # (vendor's txn count in this transaction's month - vendor's mean monthly
    # count) / std of the vendor's 12 monthly counts; std = 0 -> 0. All 12
    # calendar months are represented per vendor (missing months count as 0)
    # so a vendor's "typical month" genuinely reflects its full-year rhythm.
    monthly_counts = (
        gl.groupby(["vendor_id", "month_index"]).size().rename("txn_count").reset_index()
    )
    all_vendor_ids = gl["vendor_id"].unique()
    full_month_index = pd.MultiIndex.from_product(
        [all_vendor_ids, range(1, 13)], names=["vendor_id", "month_index"]
    )
    monthly_full = (
        monthly_counts.set_index(["vendor_id", "month_index"])
        .reindex(full_month_index, fill_value=0)
        .reset_index()
    )
    monthly_vol_stats = (
        monthly_full.groupby("vendor_id")["txn_count"]
        .agg(vol_mean="mean", vol_std="std")
        .reset_index()
    )
    monthly_full = monthly_full.merge(monthly_vol_stats, on="vendor_id", how="left")
    monthly_full["vendor_month_volume_z"] = np.where(
        (monthly_full["vol_std"] == 0) | monthly_full["vol_std"].isna(),
        0.0,
        (monthly_full["txn_count"] - monthly_full["vol_mean"]) / monthly_full["vol_std"],
    )
    gl = gl.merge(
        monthly_full[["vendor_id", "month_index", "vendor_month_volume_z"]],
        on=["vendor_id", "month_index"],
        how="left",
    )

    # -- 3. cadence_ratio --
    # days since the vendor's previous invoice / the vendor's median
    # inter-invoice gap; a vendor's first transaction, or vendors with < 3
    # transactions, -> 1 (neutral). Sorted by (vendor_id, invoice_dt, txn_id)
    # so same-day ties resolve deterministically.
    cadence = gl[["txn_id", "vendor_id", "invoice_dt"]].sort_values(
        ["vendor_id", "invoice_dt", "txn_id"]
    ).copy()
    cadence["prev_invoice_dt"] = cadence.groupby("vendor_id")["invoice_dt"].shift(1)
    cadence["days_since_prev"] = (cadence["invoice_dt"] - cadence["prev_invoice_dt"]).dt.days
    cadence["vendor_n_txns"] = cadence.groupby("vendor_id")["txn_id"].transform("count")

    gap_medians = (
        cadence.dropna(subset=["days_since_prev"])
        .groupby("vendor_id")["days_since_prev"]
        .median()
        .rename("median_gap")
        .reset_index()
    )
    cadence = cadence.merge(gap_medians, on="vendor_id", how="left")

    def _cadence_ratio(row) -> float:
        if row["vendor_n_txns"] < CADENCE_MIN_TXNS:
            return CADENCE_NEUTRAL_VALUE
        if pd.isna(row["days_since_prev"]):  # this vendor's first transaction
            return CADENCE_NEUTRAL_VALUE
        median_gap = row["median_gap"]
        # Defensive edge case beyond the design's pinned list: a vendor
        # whose median inter-invoice gap is exactly 0 (repeated same-day
        # invoices) would otherwise divide by zero. Treated as neutral.
        if pd.isna(median_gap) or median_gap == 0:
            return CADENCE_NEUTRAL_VALUE
        return row["days_since_prev"] / median_gap

    cadence["cadence_ratio"] = cadence.apply(_cadence_ratio, axis=1)
    gl = gl.merge(cadence[["txn_id", "cadence_ratio"]], on="txn_id", how="left")

    # Re-assert the fixed row order before returning (merges above are all
    # many-to-one on gl's own txn_id/vendor_id, which preserves order, but
    # this makes the determinism guarantee explicit rather than incidental).
    gl = gl.sort_values("txn_id").reset_index(drop=True)

    missing_features = gl[FEATURE_COLUMNS].isna().any()
    if missing_features.any():
        raise ValueError(
            f"Unexpected missing feature values after computation: "
            f"{missing_features[missing_features].index.tolist()}"
        )

    return gl


# ---------------------------------------------------------------------------
# Model fit + scoring
# ---------------------------------------------------------------------------

def fit_and_score(features_df: pd.DataFrame) -> tuple:
    """Fit a fresh IsolationForest and return (anomaly_score, is_flagged),
    both aligned to features_df's row order. anomaly_score is defined so
    that HIGHER means MORE anomalous (the negative of sklearn's
    decision_function, which is higher for inliers)."""
    X = features_df[FEATURE_COLUMNS].to_numpy(dtype=np.float64)

    model = IsolationForest(**ISOLATION_FOREST_PARAMS)
    model.fit(X)

    anomaly_score = -model.decision_function(X)
    is_flagged = model.predict(X) == -1  # sklearn's contamination-based outlier label
    return anomaly_score, is_flagged


def build_scores_df(features_df: pd.DataFrame, anomaly_score: np.ndarray) -> pd.DataFrame:
    scores_df = features_df[["txn_id"]].copy()
    scores_df["anomaly_score"] = anomaly_score
    return scores_df.sort_values("txn_id").reset_index(drop=True)


def build_flags_df(features_df: pd.DataFrame, anomaly_score: np.ndarray, is_flagged: np.ndarray) -> pd.DataFrame:
    flagged = features_df.loc[is_flagged, ["txn_id"]].copy()
    flagged["anomaly_score"] = anomaly_score[is_flagged]
    # Rank 1 = most anomalous. Tie-break on txn_id for a fully deterministic
    # order (ties in anomaly_score are possible in principle, if rare).
    flagged = flagged.sort_values(["anomaly_score", "txn_id"], ascending=[False, True]).reset_index(drop=True)
    flagged["rank"] = flagged.index + 1
    return flagged


# ---------------------------------------------------------------------------
# Determinism check -- SHA-256 over a second, independent fit
# ---------------------------------------------------------------------------

def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def delete_with_retry(path: Path, attempts: int = 8, delay_seconds: float = 0.5) -> None:
    """Delete a temp file, retrying briefly on WinError 32 (file locked by
    another process). A file-sync agent can hold a
    transient read lock on a just-written file; a
    short retry loop is the standard, non-destructive fix rather than
    failing the whole determinism check over a filesystem race."""
    last_error = None
    for _ in range(attempts):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(delay_seconds)
    raise RuntimeError(
        f"Could not delete temp file {path} after {attempts} attempts "
        f"(likely a transient file lock): {last_error}"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("detect_anomalies.py -- Phase 3 Isolation Forest detector")
    print("=" * 70)
    print(f"\nscikit-learn version: {sklearn.__version__}")

    if ANALYSIS_DIR.resolve() == DATA_DIR.resolve():
        raise RuntimeError("Output path must not equal an input path.")
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

    print("\nLoading public CSVs...")
    gl_df, calendar_df = load_public_csvs()
    print(f"  gl_transactions:   {len(gl_df):,} rows")
    print(f"  company_calendar:  {len(calendar_df)} rows")

    print("\nComputing the eight detector features...")
    features_df = compute_features(gl_df, calendar_df)
    print(f"  Feature matrix: {len(features_df):,} rows x {len(FEATURE_COLUMNS)} columns")
    print(f"  Columns: {FEATURE_COLUMNS}")

    # -- Run 1: the real, written outputs --
    print(f"\nFitting IsolationForest (run 1 of 2 -- params: {ISOLATION_FOREST_PARAMS})...")
    score_1, flagged_1 = fit_and_score(features_df)
    scores_df_1 = build_scores_df(features_df, score_1)
    flags_df_1 = build_flags_df(features_df, score_1, flagged_1)

    scores_path = ANALYSIS_DIR / "detector_scores.csv"
    flags_path = ANALYSIS_DIR / "detector_flags.csv"
    scores_df_1.to_csv(scores_path, index=False, encoding="utf-8")
    flags_df_1.to_csv(flags_path, index=False, encoding="utf-8")
    print(f"  Wrote {len(scores_df_1):,} rows to {scores_path}")
    print(f"  Wrote {len(flags_df_1):,} rows to {flags_path}")

    n_flagged = len(flags_df_1)
    print(f"\nFlagged transactions: {n_flagged} of {len(scores_df_1):,} "
          f"(designed outcome: {EXPECTED_FLAG_COUNT})")
    if not (FLAG_COUNT_SANITY_BAND[0] <= n_flagged <= FLAG_COUNT_SANITY_BAND[1]):
        print(
            f"  NOTE: flag count {n_flagged} falls outside the sanity band "
            f"{FLAG_COUNT_SANITY_BAND} around the designed {EXPECTED_FLAG_COUNT}. "
            f"Per the design, this is a frozen, reported deviation -- "
            f"not something this script retunes."
        )

    # -- Run 2: an independent fit, written to temp files, for the
    # determinism check. Deleted immediately after hashing. --
    print("\nFitting IsolationForest again (run 2 of 2 -- determinism check)...")
    score_2, flagged_2 = fit_and_score(features_df)
    scores_df_2 = build_scores_df(features_df, score_2)
    flags_df_2 = build_flags_df(features_df, score_2, flagged_2)

    tmp_scores_path = ANALYSIS_DIR / "_tmp_detector_scores_run2.csv"
    tmp_flags_path = ANALYSIS_DIR / "_tmp_detector_flags_run2.csv"
    scores_df_2.to_csv(tmp_scores_path, index=False, encoding="utf-8")
    flags_df_2.to_csv(tmp_flags_path, index=False, encoding="utf-8")

    try:
        hash_scores_1 = sha256_of_file(scores_path)
        hash_scores_2 = sha256_of_file(tmp_scores_path)
        hash_flags_1 = sha256_of_file(flags_path)
        hash_flags_2 = sha256_of_file(tmp_flags_path)
    finally:
        delete_with_retry(tmp_scores_path)
        delete_with_retry(tmp_flags_path)

    print(f"\ndetector_scores.csv SHA-256 (run 1): {hash_scores_1}")
    print(f"detector_scores.csv SHA-256 (run 2): {hash_scores_2}")
    print(f"detector_flags.csv  SHA-256 (run 1): {hash_flags_1}")
    print(f"detector_flags.csv  SHA-256 (run 2): {hash_flags_2}")

    scores_match = hash_scores_1 == hash_scores_2
    flags_match = hash_flags_1 == hash_flags_2
    if not (scores_match and flags_match):
        raise AssertionError(
            "Detector outputs are NOT deterministic across two independent "
            f"fits in this process (scores_match={scores_match}, "
            f"flags_match={flags_match}). Check the scikit-learn version "
            f"against the pinned environment (1.9.0)."
        )

    print("\nDeterminism check PASSED -- identical SHA-256 across two independent fits.")
    print(f"scikit-learn version: {sklearn.__version__}")
    print(f"Flagged transactions: {n_flagged} of {len(scores_df_1):,}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nFATAL: {exc}")
        sys.exit(1)
