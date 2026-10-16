"""
rule_tests.py -- The seven deterministic audit rule tests.

Every test traces to sourced audit practice. This module is deliberately dependency-light: pandas and the
Python standard library only -- no numpy, no config.py, no answer-key
access anywhere. It is meant to read like a standalone audit script that
could be handed to someone with only the four public CSVs.

The numeric thresholds below mirror config.py's RULE_* constants and
the design exactly; they are restated here (rather than imported)
so this module has no project-internal dependency at all.

Public entry point:
    run_all_rule_tests(gl_df, vendor_master_df, calendar_df) -> DataFrame
        columns: txn_id, test
        One row per (transaction, test) flag. By design, no
        transaction should ever appear under more than one test -- that
        "no double-trip" property is asserted by validate_ledger.py, not
        by this module.

Each individual test is also usable standalone; all take pandas DataFrames
matching the public CSV schemas and return a plain list of flagged txn_ids.

Run directly to print per-test flag counts:
    python code/rule_tests.py
"""

from datetime import datetime
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Rule parameters
# ---------------------------------------------------------------------------

DUPLICATE_MAX_GAP_DAYS = 7
ROUND_SUM_MULTIPLE_EUR = 1000.0
ROUND_SUM_MIN_EUR = 2000.0
NEAR_THRESHOLD_LOW_EUR = 9500.0
NEAR_THRESHOLD_HIGH_EUR = 10000.0  # exclusive
SPLIT_MAX_WINDOW_DAYS = 3
SPLIT_MIN_PART_EUR = 4000.0
SPLIT_MAX_PART_EUR = 10000.0  # exclusive
SPLIT_MIN_SUM_EUR = 10000.0

INTEGRATION_USER = "INTEG-01"


# ---------------------------------------------------------------------------
# Shared helper: enumerate same-vendor row pairs within a day window
# ---------------------------------------------------------------------------

def _same_vendor_pairs_within_window(gl_df: pd.DataFrame, max_gap_days: int):
    """
    Yield (row_i, row_j) as pandas Series pairs for every two transactions of
    the same vendor whose posting_date is within max_gap_days of each other
    (posting_date gap, not invoice_date -- the design's duplicate test
    definition, applied consistently to the split test too).
    """
    dates = pd.to_datetime(gl_df["posting_date"])
    working = gl_df.assign(posting_dt=dates)
    for vendor_id, group in working.groupby("vendor_id", sort=False):
        g = group.sort_values("posting_dt")
        rows = list(g.itertuples())
        n = len(rows)
        for i in range(n):
            for j in range(i + 1, n):
                gap = (rows[j].posting_dt - rows[i].posting_dt).days
                if gap > max_gap_days:
                    break
                yield rows[i], rows[j]


# ---------------------------------------------------------------------------
# 1. Duplicate invoices
# ---------------------------------------------------------------------------

def test_duplicate(gl_df: pd.DataFrame) -> list:
    """Same vendor_id, same amount_eur (exact), posting_date gap <= 7 days,
    different invoice_number."""
    flagged = set()
    for row_i, row_j in _same_vendor_pairs_within_window(gl_df, DUPLICATE_MAX_GAP_DAYS):
        if (
            round(row_i.amount_eur, 2) == round(row_j.amount_eur, 2)
            and row_i.invoice_number != row_j.invoice_number
        ):
            flagged.add(row_i.txn_id)
            flagged.add(row_j.txn_id)
    return sorted(flagged)


# ---------------------------------------------------------------------------
# 2. Round-sum
# ---------------------------------------------------------------------------

def test_round_sum(gl_df: pd.DataFrame) -> list:
    """amount_eur an exact multiple of EUR1,000 and >= EUR2,000."""
    def is_round(amount):
        if amount < ROUND_SUM_MIN_EUR:
            return False
        cents = round(amount * 100)
        step_cents = round(ROUND_SUM_MULTIPLE_EUR * 100)
        return cents % step_cents == 0

    mask = gl_df["amount_eur"].map(is_round)
    return sorted(gl_df.loc[mask, "txn_id"].tolist())


# ---------------------------------------------------------------------------
# 3. Near-threshold
# ---------------------------------------------------------------------------

def test_near_threshold(gl_df: pd.DataFrame) -> list:
    """EUR9,500.00 <= amount_eur < EUR10,000.00 (within 5% below the EUR10,000 tier)."""
    mask = (gl_df["amount_eur"] >= NEAR_THRESHOLD_LOW_EUR) & (gl_df["amount_eur"] < NEAR_THRESHOLD_HIGH_EUR)
    return sorted(gl_df.loc[mask, "txn_id"].tolist())


# ---------------------------------------------------------------------------
# 4. Split
# ---------------------------------------------------------------------------

def test_split(gl_df: pd.DataFrame) -> list:
    """Same vendor_id, window <= 3 days, >= 2 invoices each < EUR10,000 and
    >= EUR4,000, sum >= EUR10,000."""
    flagged = set()
    for row_i, row_j in _same_vendor_pairs_within_window(gl_df, SPLIT_MAX_WINDOW_DAYS):
        a, b = row_i.amount_eur, row_j.amount_eur
        parts_in_band = (
            SPLIT_MIN_PART_EUR <= a < SPLIT_MAX_PART_EUR
            and SPLIT_MIN_PART_EUR <= b < SPLIT_MAX_PART_EUR
        )
        if parts_in_band and (a + b) >= SPLIT_MIN_SUM_EUR:
            flagged.add(row_i.txn_id)
            flagged.add(row_j.txn_id)
    return sorted(flagged)


# ---------------------------------------------------------------------------
# 5. Calendar (human-posted rows only)
# ---------------------------------------------------------------------------

def test_calendar(gl_df: pd.DataFrame, calendar_df: pd.DataFrame) -> list:
    """posting_date is not a working day, applied to human-posted rows only
    (INTEG-01 batch rows are exempt)."""
    working_day_by_date = dict(zip(calendar_df["date"], calendar_df["is_working_day"]))
    human_rows = gl_df[gl_df["posted_by"] != INTEGRATION_USER]
    mask = human_rows["posting_date"].map(lambda d: not bool(working_day_by_date.get(d, True)))
    return sorted(human_rows.loc[mask, "txn_id"].tolist())


# ---------------------------------------------------------------------------
# 6. Mapping
# ---------------------------------------------------------------------------

def test_mapping(gl_df: pd.DataFrame, vendor_master_df: pd.DataFrame) -> list:
    """account not in the vendor's allowed_accounts."""
    allowed_by_vendor = {
        row.vendor_id: set(str(row.allowed_accounts).split(";"))
        for row in vendor_master_df.itertuples()
    }

    def is_mismapped(row):
        allowed = allowed_by_vendor.get(row.vendor_id)
        if allowed is None:
            return False
        return str(row.account) not in allowed

    mask = gl_df.apply(is_mismapped, axis=1)
    return sorted(gl_df.loc[mask, "txn_id"].tolist())


# ---------------------------------------------------------------------------
# 7. Exact-name hygiene
# ---------------------------------------------------------------------------

def test_name_hygiene(gl_df: pd.DataFrame, vendor_master_df: pd.DataFrame) -> list:
    """Byte-identical vendor_name across distinct vendor_ids. Flags every
    transaction belonging to a vendor_id involved in such a collision."""
    name_to_vendor_ids = {}
    for row in vendor_master_df.itertuples():
        name_to_vendor_ids.setdefault(row.vendor_name, set()).add(row.vendor_id)

    colliding_vendor_ids = set()
    for name, vendor_ids in name_to_vendor_ids.items():
        if len(vendor_ids) > 1:
            colliding_vendor_ids.update(vendor_ids)

    if not colliding_vendor_ids:
        return []
    mask = gl_df["vendor_id"].isin(colliding_vendor_ids)
    return sorted(gl_df.loc[mask, "txn_id"].tolist())


# ---------------------------------------------------------------------------
# Combined runner
# ---------------------------------------------------------------------------

TEST_FUNCTIONS = {
    "duplicate": lambda gl, vm, cal: test_duplicate(gl),
    "round_sum": lambda gl, vm, cal: test_round_sum(gl),
    "near_threshold": lambda gl, vm, cal: test_near_threshold(gl),
    "split": lambda gl, vm, cal: test_split(gl),
    "calendar": lambda gl, vm, cal: test_calendar(gl, cal),
    "mapping": lambda gl, vm, cal: test_mapping(gl, vm),
    "name_hygiene": lambda gl, vm, cal: test_name_hygiene(gl, vm),
}


def run_all_rule_tests(gl_df: pd.DataFrame, vendor_master_df: pd.DataFrame, calendar_df: pd.DataFrame) -> pd.DataFrame:
    """Run all seven tests and return a long-format DataFrame(txn_id, test)."""
    records = []
    for test_name, fn in TEST_FUNCTIONS.items():
        for txn_id in fn(gl_df, vendor_master_df, calendar_df):
            records.append({"txn_id": txn_id, "test": test_name})
    return pd.DataFrame(records, columns=["txn_id", "test"])


# ---------------------------------------------------------------------------
# Standalone execution -- prints per-test flag counts
# ---------------------------------------------------------------------------

def _load_public_csvs(data_dir: Path) -> tuple:
    gl_df = pd.read_csv(data_dir / "gl_transactions.csv")
    vendor_master_df = pd.read_csv(data_dir / "vendor_master.csv")
    calendar_df = pd.read_csv(data_dir / "company_calendar.csv")
    return gl_df, vendor_master_df, calendar_df


def main():
    script_dir = Path(__file__).resolve().parent
    data_dir = script_dir.parent / "data"

    print("=" * 70)
    print("rule_tests.py -- standalone run")
    print("=" * 70)
    gl_df, vendor_master_df, calendar_df = _load_public_csvs(data_dir)
    print(f"Loaded {len(gl_df):,} transactions, {len(vendor_master_df)} vendors, "
          f"{len(calendar_df)} calendar days.\n")

    flags_df = run_all_rule_tests(gl_df, vendor_master_df, calendar_df)

    print(f"{'Test':<16}{'Flags':>8}")
    print("-" * 24)
    total = 0
    for test_name in TEST_FUNCTIONS:
        n = int((flags_df["test"] == test_name).sum())
        total += n
        print(f"{test_name:<16}{n:>8}")
    print("-" * 24)
    print(f"{'TOTAL':<16}{total:>8}")

    dup_txns = flags_df["txn_id"].value_counts()
    double_tripped = dup_txns[dup_txns > 1]
    print(f"\nTransactions flagged by more than one test: {len(double_tripped)}")


if __name__ == "__main__":
    main()
