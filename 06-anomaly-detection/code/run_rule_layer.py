"""
run_rule_layer.py -- Phase 3 rule-layer runner.

Runs the seven frozen audit rule tests (code/rule_tests.py, built in Phase 2)
over the public ledger and writes the flagged transactions to
data/analysis/rule_flags.csv.

This script reads ONLY the frozen public CSVs (gl_transactions.csv,
vendor_master.csv, company_calendar.csv). It never reads, imports, or
references anything under data/answer_key/ -- the answer-key comparison
happens separately, outside this codebase.

The pre-registered catch matrix is config.PREREGISTERED_TEST_COUNTS.

Run from the project root or from code/:
    python code/run_rule_layer.py
"""

import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Paths (pathlib, relative to this script's own location -- never absolute,
# never touching anything outside data/analysis/ for output).
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
ANALYSIS_DIR = DATA_DIR / "analysis"

# Phase 2 modules are frozen -- imported here, never modified.
sys.path.insert(0, str(SCRIPT_DIR))
import config       # noqa: E402  (frozen Phase 2 module)
import rule_tests   # noqa: E402  (frozen Phase 2 module)


# ---------------------------------------------------------------------------
# Data loading -- public CSVs only
# ---------------------------------------------------------------------------

def load_public_csvs() -> tuple:
    """Load the three public CSVs the rule engine needs. Deliberately never
    touches data/answer_key/ -- that folder is out of scope for this script
    and for every script in Phase 3."""
    paths = {
        "gl": DATA_DIR / "gl_transactions.csv",
        "vendor_master": DATA_DIR / "vendor_master.csv",
        "calendar": DATA_DIR / "company_calendar.csv",
    }
    missing = [name for name, p in paths.items() if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing required input file(s): {missing}. "
            f"Run code/generate_ledger.py (Phase 2) first."
        )

    gl_df = pd.read_csv(paths["gl"])
    vendor_master_df = pd.read_csv(paths["vendor_master"])
    calendar_df = pd.read_csv(paths["calendar"])
    return gl_df, vendor_master_df, calendar_df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("run_rule_layer.py -- Phase 3 rule-layer runner")
    print("=" * 70)

    # Guard: output folder must never coincide with an input folder.
    if ANALYSIS_DIR.resolve() == DATA_DIR.resolve():
        raise RuntimeError("Output path must not equal an input path.")
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

    print("\nLoading public CSVs...")
    gl_df, vendor_master_df, calendar_df = load_public_csvs()
    print(f"  gl_transactions:   {len(gl_df):,} rows")
    print(f"  vendor_master:     {len(vendor_master_df)} rows")
    print(f"  company_calendar:  {len(calendar_df)} rows")

    print("\nRunning the seven rule tests (code/rule_tests.py, frozen Phase 2)...")
    flags_df = rule_tests.run_all_rule_tests(gl_df, vendor_master_df, calendar_df)

    # Stable, deterministic row order for a byte-reproducible output file.
    flags_df = flags_df.sort_values(["txn_id", "test"]).reset_index(drop=True)

    # Per-test counts must equal the pre-registered totals exactly
    # (config.PREREGISTERED_TEST_COUNTS: 14/18/4/10/10/8/0). This is a hard
    # requirement, not a judgment call -- a mismatch here means either the
    # frozen rule engine or the frozen ledger has drifted since Phase 2's
    # validator last passed.
    print(f"\n{'Test':<16}{'Flags':>8}{'Expected':>10}")
    print("-" * 34)
    all_match = True
    for test_name, expected in config.PREREGISTERED_TEST_COUNTS.items():
        actual = int((flags_df["test"] == test_name).sum())
        match = actual == expected
        all_match = all_match and match
        marker = "" if match else "  <-- MISMATCH"
        print(f"{test_name:<16}{actual:>8}{expected:>10}{marker}")
    print("-" * 34)
    total_actual = len(flags_df)
    total_expected = sum(config.PREREGISTERED_TEST_COUNTS.values())
    print(f"{'TOTAL':<16}{total_actual:>8}{total_expected:>10}")

    if not all_match:
        raise AssertionError(
            "Rule-layer flag counts do not match the pre-registered totals "
            "in config.PREREGISTERED_TEST_COUNTS (expected 14/18/4/10/10/8/0)."
        )

    output_path = ANALYSIS_DIR / "rule_flags.csv"
    flags_df.to_csv(output_path, index=False, encoding="utf-8")
    print(f"\nWrote {len(flags_df)} rule flags to {output_path}")
    print("All per-test counts match the pre-registered totals (14/18/4/10/10/8/0).")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nFATAL: {exc}")
        sys.exit(1)
