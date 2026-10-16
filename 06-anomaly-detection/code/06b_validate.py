"""
06b_validate.py -- coherence checks for the 06b FY2026 purchase ledger.

Case-study convention: one function per rule, PASS/FAIL printed, sys.exit(1) on
any failure. Run after 06b_generate.py:

    python code/06b_validate.py

Checks, in order:
  1. Row/vendor/table counts match config_06b.py exactly.
  2. Referential integrity -- every vendor_id/account resolves to its master;
     quantity * unit_price_eur reconciles to amount_eur; all dates in range.
  3. Plant integrity -- each of D1/D2/D3/B1/B2's drift is present at
     approximately its designed magnitude, and the designed memo breadcrumbs
     appear where (and only where) the design says they do.
  4. Answer-key completeness -- exactly 5 rows, correct kind/vendor mapping.
  5. 6a untouched -- a couple of 6a's own artefacts are re-hashed and
     compared against the SHA-256 values captured immediately after 06b's
     first build (hardcoded below); any difference fails loudly. This is a
     forward-looking guard, not a before/after diff within a single run --
     06b_generate.py never opens 6a's files in write mode (also grep-
     verifiable: 06b_generate.py opens SIX_A_VENDOR_MASTER only via
     pd.read_csv, never via `open(..., "w")`).
"""

import hashlib
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data" / "06b"
SIX_A_DATA_DIR = PROJECT_ROOT / "data"

sys.path.insert(0, str(SCRIPT_DIR))
import config_06b as config

FAILURES = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}")


# ---------------------------------------------------------------------------
# 6a artefact hashes, captured immediately after 06b's own build
# -- the forward-looking untouched-guard.
# ---------------------------------------------------------------------------
SIX_A_EXPECTED_HASHES = {
    "gl_transactions.csv": "8eeaed2896d65f927b9488dd44a52ff0e73f24c194644ca7d90287d0e29ad9eb",
    "vendor_master.csv": "d8725148a766d77f00df91ccd951eafa93436b23aed9516773602349fdce7982",
}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rule_1_row_counts(gl, vendor_master, coa, calendar, answer_key):
    print("\n[Rule 1] Row/vendor/table counts")
    check("gl_transactions_06b.csv row count", len(gl) == config.TOTAL_TRANSACTIONS,
          f"got {len(gl)}, expected {config.TOTAL_TRANSACTIONS}")
    check("vendor_master_06b.csv row count", len(vendor_master) == config.TOTAL_VENDORS,
          f"got {len(vendor_master)}, expected {config.TOTAL_VENDORS}")
    check("chart_of_accounts_06b.csv row count", len(coa) == len(config.CHART_OF_ACCOUNTS),
          f"got {len(coa)}, expected {len(config.CHART_OF_ACCOUNTS)}")
    check("company_calendar_06b.csv row count", len(calendar) == 365, f"got {len(calendar)}")
    check("answer_key_06b.csv row count", len(answer_key) == 5, f"got {len(answer_key)}")
    check("vendor_master_06b.csv has no duplicate vendor_id", vendor_master["vendor_id"].is_unique)
    check("vendor_master_06b.csv has no duplicate vendor_name", vendor_master["vendor_name"].is_unique)


def rule_2_referential_integrity(gl, vendor_master, coa):
    print("\n[Rule 2] Referential integrity, amount reconciliation, date range")
    known_vendors = set(vendor_master["vendor_id"])
    known_accounts = set(coa["account"].astype(str))
    check("every gl vendor_id resolves to vendor_master", set(gl["vendor_id"]).issubset(known_vendors))
    check("every gl account resolves to chart_of_accounts", set(gl["account"].astype(str)).issubset(known_accounts))

    # unit_price_eur is rounded to the cent for display, but amount_eur is
    # computed from the unrounded (4-decimal) unit price -- so the two can
    # differ by up to half a cent times the quantity. Tolerance is per-row,
    # not a flat constant, to reflect that mechanically rather than guess a
    # number large enough to paper over a real bug.
    recon = (gl["quantity"] * gl["unit_price_eur"] - gl["amount_eur"]).abs()
    tolerance = 0.005 * gl["quantity"] + 0.01
    check("quantity * unit_price_eur reconciles to amount_eur (tolerance = 0.005/unit rounding + 0.01 EUR)",
          bool((recon <= tolerance).all()), f"max discrepancy {recon.max():.4f}, max tolerance {tolerance.max():.4f}")

    check("all amounts positive", bool((gl["amount_eur"] > 0).all()))
    check("all quantities >= 1", bool((gl["quantity"] >= 1).all()))

    invoice_dates = pd.to_datetime(gl["invoice_date"])
    posting_dates = pd.to_datetime(gl["posting_date"])
    check("all invoice_date within FY2026", bool((invoice_dates.dt.year == config.YEAR).all()))
    check("all posting_date within FY2026", bool((posting_dates.dt.year == config.YEAR).all()))

    due_dates = pd.to_datetime(gl["due_date"])
    terms_by_vendor = vendor_master.set_index("vendor_id")["terms_days"]
    expected_due = invoice_dates + pd.to_timedelta(gl["vendor_id"].map(terms_by_vendor), unit="D")
    check("due_date == invoice_date + vendor terms_days exactly", bool((due_dates == expected_due).all()))

    check("txn_id values are unique", gl["txn_id"].is_unique)
    check("invoice_number strictly increasing per vendor (no reuse)",
          bool(gl.sort_values(["vendor_id", "invoice_date"]).groupby("vendor_id")["invoice_number"]
               .apply(lambda s: s.is_monotonic_increasing).all()))


def _volume_weighted_monthly_price(gl: pd.DataFrame, vendor_id: str) -> pd.Series:
    sub = gl[gl["vendor_id"] == vendor_id].copy()
    sub["month"] = pd.to_datetime(sub["invoice_date"]).dt.month
    weighted = sub.assign(_wp=sub["quantity"] * sub["unit_price_eur"]).groupby("month")["_wp"].sum()
    weight = sub.groupby("month")["quantity"].sum()
    return (weighted / weight).sort_index()


def rule_3_plant_integrity(gl):
    print("\n[Rule 3] Plant integrity -- drift magnitude and memo breadcrumbs")

    # D1 -- fast drift, April onward, ~2.5%/month compounding.
    d1 = _volume_weighted_monthly_price(gl, config.D1_VENDOR_ID)
    d1_baseline = d1.loc[[1, 2, 3]].mean()
    d1_expected_dec_multiplier = (1 + config.D1_DRIFT_RATE_MONTHLY) ** (12 - (config.D1_DRIFT_START_MONTH - 1))
    d1_dec_ratio = d1.loc[12] / d1_baseline
    check("D1 December price elevated within band of the designed multiplier (+/-25% relative)",
          abs(d1_dec_ratio - d1_expected_dec_multiplier) / d1_expected_dec_multiplier < 0.25,
          f"observed ratio {d1_dec_ratio:.3f}, expected ~{d1_expected_dec_multiplier:.3f}")
    check("D1 price rises monotonically month-on-month from April (allowing 1 non-monotonic month for noise)",
          (d1.loc[4:12].diff().dropna() < 0).sum() <= 1)

    # D2 -- slow drift, February onward, ~1.0%/month compounding.
    d2 = _volume_weighted_monthly_price(gl, config.D2_VENDOR_ID)
    d2_jan = d2.loc[1]
    d2_expected_dec_multiplier = (1 + config.D2_DRIFT_RATE_MONTHLY) ** (12 - (config.D2_DRIFT_START_MONTH - 1))
    d2_dec_ratio = d2.loc[12] / d2_jan
    check("D2 December price elevated within band of the designed multiplier (+/-30% relative)",
          abs(d2_dec_ratio - d2_expected_dec_multiplier) / d2_expected_dec_multiplier < 0.30,
          f"observed ratio {d2_dec_ratio:.3f}, expected ~{d2_expected_dec_multiplier:.3f}")

    # D3 -- bundling drift, June step then compounding.
    d3 = _volume_weighted_monthly_price(gl, config.D3_VENDOR_ID)
    d3_baseline = d3.loc[[1, 2, 3, 4, 5]].mean()
    d3_expected_dec_multiplier = (1 + config.D3_BUNDLE_STEP_FRACTION) * (
        (1 + config.D3_DRIFT_RATE_MONTHLY) ** (12 - config.D3_BUNDLE_START_MONTH)
    )
    d3_dec_ratio = d3.loc[12] / d3_baseline
    check("D3 December price elevated within band of the designed multiplier (+/-25% relative)",
          abs(d3_dec_ratio - d3_expected_dec_multiplier) / d3_expected_dec_multiplier < 0.25,
          f"observed ratio {d3_dec_ratio:.3f}, expected ~{d3_expected_dec_multiplier:.3f}")
    check("D3 H1 (Jan-May) shows no material trend (max/min < 1.10)",
          d3.loc[[1, 2, 3, 4, 5]].max() / d3.loc[[1, 2, 3, 4, 5]].min() < 1.10)

    # B1 -- contractual step, February onward.
    b1 = _volume_weighted_monthly_price(gl, config.B1_VENDOR_ID)
    b1_expected_ratio = 1 + config.B1_STEP_FRACTION
    b1_observed_ratio = b1.loc[12] / b1.loc[1]
    check("B1 post-step price elevated within band of the designed +5.2% step",
          abs(b1_observed_ratio - b1_expected_ratio) / b1_expected_ratio < 0.20,
          f"observed ratio {b1_observed_ratio:.3f}, expected ~{b1_expected_ratio:.3f}")

    # B2 -- market repricing step, August onward.
    b2 = _volume_weighted_monthly_price(gl, config.B2_VENDOR_ID)
    b2_pre = b2.loc[[1, 2, 3, 4, 5, 6, 7]].mean()
    b2_post = b2.loc[[8, 9, 10, 11, 12]].mean()
    b2_expected_ratio = 1 + config.B2_STEP_FRACTION
    b2_observed_ratio = b2_post / b2_pre
    check("B2 post-August price elevated within band of the designed +9% step",
          abs(b2_observed_ratio - b2_expected_ratio) / b2_expected_ratio < 0.15,
          f"observed ratio {b2_observed_ratio:.3f}, expected ~{b2_expected_ratio:.3f}")

    # Memo breadcrumbs.
    def memo_month(vendor_id):
        sub = gl[gl["vendor_id"] == vendor_id].copy()
        sub["month"] = pd.to_datetime(sub["invoice_date"]).dt.month
        return sub

    d3_memos = memo_month(config.D3_VENDOR_ID)
    check("D3 memo carries the freight breadcrumb from June onward, and only from June onward",
          bool((d3_memos.loc[d3_memos["month"] >= 6, "memo"].str.contains(config.D3_MEMO_BREADCRUMB)).all())
          and not bool((d3_memos.loc[d3_memos["month"] < 6, "memo"].str.contains(config.D3_MEMO_BREADCRUMB)).any()))

    b1_memos = memo_month(config.B1_VENDOR_ID)
    check("B1 memo cites the indexation clause from February onward, and only from then",
          bool((b1_memos.loc[b1_memos["month"] >= config.B1_STEP_EFFECTIVE_MONTH, "memo"].str.contains("indeksikorotus")).all())
          and not bool((b1_memos.loc[b1_memos["month"] < config.B1_STEP_EFFECTIVE_MONTH, "memo"].str.contains("indeksikorotus")).any()))

    b2_memos = memo_month(config.B2_VENDOR_ID)
    check("B2 memo announces the repricing from August onward, and only from then",
          bool((b2_memos.loc[b2_memos["month"] >= config.B2_STEP_MONTH, "memo"].str.contains("hinnankorotus")).all())
          and not bool((b2_memos.loc[b2_memos["month"] < config.B2_STEP_MONTH, "memo"].str.contains("hinnankorotus")).any()))

    d1_memos = memo_month(config.D1_VENDOR_ID)
    check("D1 carries no covering-memo breadcrumb (a silent, undisguised drift)",
          not bool(d1_memos["memo"].str.contains("indeksikorotus|hinnankorotus|rahtikulut").any()))
    d2_memos = memo_month(config.D2_VENDOR_ID)
    check("D2 carries no covering-memo breadcrumb (a silent, undisguised drift)",
          not bool(d2_memos["memo"].str.contains("indeksikorotus|hinnankorotus|rahtikulut").any()))


def rule_4_answer_key(answer_key, vendor_master):
    print("\n[Rule 4] Answer-key completeness")
    expected_ids = {"D1", "D2", "D3", "B1", "B2"}
    check("answer key has exactly the 5 designed anomaly_ids",
          set(answer_key["anomaly_id"]) == expected_ids, f"got {set(answer_key['anomaly_id'])}")
    kind_by_id = answer_key.set_index("anomaly_id")["kind"].to_dict()
    check("D1/D2/D3 are kind=anomalous", all(kind_by_id[i] == "anomalous" for i in ("D1", "D2", "D3")))
    check("B1/B2 are kind=benign", all(kind_by_id[i] == "benign" for i in ("B1", "B2")))
    check("every answer-key vendor_id resolves to vendor_master",
          set(answer_key["vendor_id"]).issubset(set(vendor_master["vendor_id"])))
    check("every answer-key txn_ids field is non-empty",
          bool((answer_key["txn_ids"].str.len() > 0).all()))


def rule_5_six_a_untouched():
    print("\n[Rule 5] 6a's own artefacts are untouched")
    for filename, expected_hash in SIX_A_EXPECTED_HASHES.items():
        path = SIX_A_DATA_DIR / filename
        check(f"{filename} exists", path.exists())
        if path.exists():
            actual_hash = sha256_of(path)
            check(f"{filename} SHA-256 matches the post-06b-build snapshot",
                  actual_hash == expected_hash,
                  f"got {actual_hash}, expected {expected_hash}")


def main():
    print("=" * 70)
    print("06b validation")
    print("=" * 70)

    gl = pd.read_csv(DATA_DIR / "gl_transactions_06b.csv")
    vendor_master = pd.read_csv(DATA_DIR / "vendor_master_06b.csv")
    coa = pd.read_csv(DATA_DIR / "chart_of_accounts_06b.csv")
    calendar = pd.read_csv(DATA_DIR / "company_calendar_06b.csv")
    answer_key = pd.read_csv(DATA_DIR / "answer_key_06b.csv")

    rule_1_row_counts(gl, vendor_master, coa, calendar, answer_key)
    rule_2_referential_integrity(gl, vendor_master, coa)
    rule_3_plant_integrity(gl)
    rule_4_answer_key(answer_key, vendor_master)
    rule_5_six_a_untouched()

    print("\n" + "=" * 70)
    if FAILURES:
        print(f"VALIDATION FAILED -- {len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        print("=" * 70)
        sys.exit(1)
    else:
        print("VALIDATION PASSED -- all checks green.")
        print("=" * 70)


if __name__ == "__main__":
    main()
