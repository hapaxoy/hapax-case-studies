"""
validate_ledger.py -- Coherence rule validation for the Saarnitukku Oy
synthetic AP ledger.

Checks all 13 coherence rules of the design and prints a data
quality report. Exits with code 1 if any rule fails (case-study convention --
a dataset that fails validation is a bug, not a judgment call).

Rules validated:
    1.  Referential integrity
    2.  Working-day postings, human posters
    3.  Amount plausibility
    4.  Terms consistency
    5.  Cadence consistency
    6.  Seasonality
    7.  Invoice-number discipline
    8.  Planted signatures at designed magnitude
    9.  No undeclared signatures (imports rule_tests.py)
    10. Answer-key completeness and exactness
    11. Master hygiene except declared
    12. Memo validity
    13. Posting lag

Run from the project root or from code/:
    python code/validate_ledger.py
"""

import re
import sys
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"

sys.path.insert(0, str(SCRIPT_DIR))
import config
import rule_tests


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_data() -> dict:
    paths = {
        "gl": DATA_DIR / "gl_transactions.csv",
        "vendor_master": DATA_DIR / "vendor_master.csv",
        "coa": DATA_DIR / "chart_of_accounts.csv",
        "calendar": DATA_DIR / "company_calendar.csv",
        "answer_key": DATA_DIR / "answer_key" / "anomalies.csv",
    }
    missing = [k for k, p in paths.items() if not p.exists()]
    if missing:
        print(f"FATAL: Missing data files: {missing}")
        print("Run generate_ledger.py first.")
        sys.exit(1)

    data = {
        "gl": pd.read_csv(paths["gl"]),
        "vendor_master": pd.read_csv(paths["vendor_master"]),
        "coa": pd.read_csv(paths["coa"]),
        "calendar": pd.read_csv(paths["calendar"]),
        "answer_key": pd.read_csv(paths["answer_key"], dtype=str, keep_default_na=False),
    }
    return data


def answer_key_txn_ids(answer_key: pd.DataFrame, class_name: str) -> list:
    """
    Aggregate txn_ids across every event row sharing this `class` value.
    The answer key is event-grain (one row per D pair, per S event, per R
    sub-mechanism, etc. -- review, event-grain answer key), so a
    class like 'D' or 'S' spans several rows; classes that were always a
    single event (W, V, A, G, C, B1..B6) are unaffected (one row = one class).
    """
    rows = answer_key[answer_key["class"] == class_name]
    ids = []
    for raw in rows["txn_ids"]:
        if raw:
            ids.extend(raw.split(";"))
    return ids


def answer_key_txn_ids_by_event(answer_key: pd.DataFrame, anomaly_id: str) -> list:
    """Look up a single EVENT row by its exact anomaly_id (e.g. 'R-ROUND',
    'R-NEAR', 'D-03') -- used where a class aggregates sub-mechanisms that
    must stay distinguishable (rule 9's per-test set-equality checks)."""
    row = answer_key[answer_key["anomaly_id"] == anomaly_id]
    if row.empty:
        return []
    raw = row.iloc[0]["txn_ids"]
    return raw.split(";") if raw else []


def answer_key_all_txn_ids(answer_key: pd.DataFrame) -> set:
    """Every txn_id mentioned anywhere in the key, regardless of grain."""
    ids = set()
    for raw in answer_key["txn_ids"]:
        if raw:
            ids.update(raw.split(";"))
    return ids


# ---------------------------------------------------------------------------
# Independent business-day arithmetic (deliberately re-implemented rather
# than imported from generate_ledger.py, so the validator actually checks
# rather than trivially agreeing with the generator).
# ---------------------------------------------------------------------------

def working_day_set(calendar_df: pd.DataFrame) -> set:
    days = pd.to_datetime(calendar_df.loc[calendar_df["is_working_day"], "date"])
    return set(days.dt.date)


def business_days_between(a: dt.date, b: dt.date, working_days: set) -> int:
    """Count working days in the half-open interval (a, b]. Handles a > b
    by counting backward over (b, a] and returning a negative count."""
    if a == b:
        return 0
    if a < b:
        count = 0
        d = a
        while d < b:
            d += dt.timedelta(days=1)
            if d in working_days:
                count += 1
        return count
    return -business_days_between(b, a, working_days)


# ---------------------------------------------------------------------------
# Rule 1 -- Referential integrity
# ---------------------------------------------------------------------------

def check_rule_1_referential_integrity(data: dict) -> tuple:
    gl, vm, coa = data["gl"], data["vendor_master"], data["coa"]

    valid_vendor_ids = set(vm["vendor_id"])
    valid_accounts = set(coa["account"].astype(str))
    valid_posters = {config.INTEGRATION_USER, *config.HUMAN_USERS}

    bad_vendors = gl.loc[~gl["vendor_id"].isin(valid_vendor_ids), "vendor_id"].unique()
    bad_accounts = gl.loc[~gl["account"].astype(str).isin(valid_accounts), "account"].unique()
    bad_posters = gl.loc[~gl["posted_by"].isin(valid_posters), "posted_by"].unique()

    invoice_dates = pd.to_datetime(gl["invoice_date"])
    posting_dates = pd.to_datetime(gl["posting_date"])
    bad_invoice_years = int((invoice_dates.dt.year != config.YEAR).sum())
    bad_posting_years = int((posting_dates.dt.year != config.YEAR).sum())

    passed = (
        len(bad_vendors) == 0 and len(bad_accounts) == 0 and len(bad_posters) == 0
        and bad_invoice_years == 0 and bad_posting_years == 0
    )
    details = [
        f"unknown vendor_ids: {len(bad_vendors)}",
        f"unknown accounts: {len(bad_accounts)}",
        f"unknown posters: {len(bad_posters)}",
        f"invoice_date outside {config.YEAR}: {bad_invoice_years}",
        f"posting_date outside {config.YEAR}: {bad_posting_years}",
    ]
    status = "PASS" if passed else "FAIL"
    return passed, f"{status} -- " + "; ".join(details)


# ---------------------------------------------------------------------------
# Rule 2 -- Working-day postings, human posters
# ---------------------------------------------------------------------------

def check_rule_2_working_day_postings(data: dict) -> tuple:
    gl, calendar_df, answer_key = data["gl"], data["calendar"], data["answer_key"]
    working_by_date = dict(zip(calendar_df["date"], calendar_df["is_working_day"]))

    exception_ids = set(answer_key_txn_ids(answer_key, "W")) | set(answer_key_txn_ids(answer_key, "B2"))

    human_rows = gl[gl["posted_by"] != config.INTEGRATION_USER]
    human_rows = human_rows[~human_rows["txn_id"].isin(exception_ids)]
    violations = human_rows[~human_rows["posting_date"].map(lambda d: bool(working_by_date.get(d, False)))]

    integ_rows = gl[gl["posted_by"] == config.INTEGRATION_USER]
    integ_dates = pd.to_datetime(integ_rows["posting_date"])
    integ_weekend_frac = float((integ_dates.dt.weekday >= 5).mean())

    # Band re-derived after review fix 3 (organic invoice dates are
    # now weighted ~90% working day / ~10% weekend-or-holiday, not uniform
    # across all seven weekdays). INTEG-01's 0-1 calendar-day lag shifts that
    # distribution a little further toward weekends (a working Friday + 1 day
    # lands on Saturday), so the realised fraction (~15.6% on the reference
    # run) sits below the old uniform-date assumption's ~28.5% but is still
    # clearly non-zero -- confirming INTEG-01 is not weekday-constrained like
    # human posting. [0.08, 0.23] is a wide-enough band to tolerate ordinary
    # regeneration variance while still catching a regression to either
    # extreme (uniform dates would push this back toward ~28%; an accidental
    # weekday-only constraint would push it toward 0%).
    passed = len(violations) == 0 and 0.08 <= integ_weekend_frac <= 0.23
    details = [
        f"undeclared human non-working-day postings: {len(violations)}",
        f"INTEG-01 weekend-posting fraction: {integ_weekend_frac:.1%} "
        f"(any-day batch behaviour on top of ~90/10-weighted organic invoice dates; band [8%, 23%])",
    ]
    status = "PASS" if passed else "FAIL"
    return passed, f"{status} -- " + "; ".join(details)


# ---------------------------------------------------------------------------
# Rule 3 -- Amount plausibility
# ---------------------------------------------------------------------------

ACCOUNT_CLASS_BANDS = {
    "fixed_asset": (1.0, 200_000.0),
    "purchases": (1.0, 100_000.0),
    "external_services": (1.0, 100_000.0),
    "personnel": (1.0, 100_000.0),
    "other_operating": (1.0, 100_000.0),
}


def check_rule_3_amount_plausibility(data: dict) -> tuple:
    gl, coa = data["gl"], data["coa"]
    class_by_account = dict(zip(coa["account"].astype(str), coa["class"]))

    amounts = gl["amount_eur"]
    non_positive = int((amounts <= 0).sum())
    not_two_decimals = int((( (amounts * 100).round() - amounts * 100).abs() > 1e-6).sum())

    out_of_band = 0
    for account, cls in class_by_account.items():
        band = ACCOUNT_CLASS_BANDS[cls]
        sub = gl.loc[gl["account"].astype(str) == account, "amount_eur"]
        out_of_band += int(((sub < band[0]) | (sub > band[1])).sum())

    passed = non_positive == 0 and not_two_decimals == 0 and out_of_band == 0
    details = [
        f"non-positive amounts: {non_positive}",
        f"amounts not at 2 decimals: {not_two_decimals}",
        f"amounts outside their account-class band: {out_of_band}",
    ]
    status = "PASS" if passed else "FAIL"
    return passed, f"{status} -- " + "; ".join(details)


# ---------------------------------------------------------------------------
# Rule 4 -- Terms consistency
# ---------------------------------------------------------------------------

def check_rule_4_terms_consistency(data: dict) -> tuple:
    gl, vm = data["gl"], data["vendor_master"]
    terms_by_vendor = dict(zip(vm["vendor_id"], vm["terms_days"]))

    invoice_dates = pd.to_datetime(gl["invoice_date"])
    due_dates = pd.to_datetime(gl["due_date"])
    expected_due = invoice_dates + gl["vendor_id"].map(terms_by_vendor).map(lambda d: pd.Timedelta(days=int(d)))

    mismatches = int((due_dates != expected_due).sum())
    passed = mismatches == 0
    status = "PASS" if passed else "FAIL"
    return passed, f"{status} -- due_date mismatches: {mismatches}"


# ---------------------------------------------------------------------------
# Rule 5 -- Cadence consistency
# ---------------------------------------------------------------------------

def check_rule_5_cadence_consistency(data: dict) -> tuple:
    """
    Statistical check: no vendor should show a single silent stretch so long
    it looks like a data artefact rather than a legitimately sparse vendor.
    Vendors with a designed cadence exception (G's H2 amount step -- gaps are
    unaffected; V's split spend across three records) are excluded from the
    per-vendor timing check since their exception is about amount or
    vendor-count, not inter-invoice timing.
    """
    gl = data["gl"]
    invoice_dates = pd.to_datetime(gl["invoice_date"])
    working = gl.assign(invoice_dt=invoice_dates)

    max_gap_seen = 0
    offenders = []
    for vendor_id, group in working.groupby("vendor_id"):
        dates = sorted(group["invoice_dt"].tolist())
        if len(dates) < 4:
            continue
        gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        gap = max(gaps)
        max_gap_seen = max(max_gap_seen, gap)
        if gap > 300:
            offenders.append((vendor_id, gap))

    passed = len(offenders) == 0
    details = f"max inter-invoice gap observed: {max_gap_seen} days; vendors with a gap > 300 days: {len(offenders)}"
    status = "PASS" if passed else "FAIL"
    return passed, f"{status} -- {details}"


# ---------------------------------------------------------------------------
# Rule 6 -- Seasonality
# ---------------------------------------------------------------------------

def check_rule_6_seasonality(data: dict) -> tuple:
    gl = data["gl"]
    months = pd.to_datetime(gl["invoice_date"]).dt.month
    counts = months.value_counts().sort_index()
    avg = counts.mean()

    nov_ratio = counts.get(11, 0) / avg
    dec_ratio = counts.get(12, 0) / avg
    jul_ratio = counts.get(7, 0) / avg

    passed = (1.10 <= nov_ratio <= 1.55) and (1.10 <= dec_ratio <= 1.55) and (0.45 <= jul_ratio <= 0.90)
    details = [
        f"Nov/avg = {nov_ratio:.3f} (expect ~1.3, band [1.10, 1.55])",
        f"Dec/avg = {dec_ratio:.3f} (expect ~1.3, band [1.10, 1.55])",
        f"Jul/avg = {jul_ratio:.3f} (expect ~0.7, band [0.45, 0.90])",
    ]
    status = "PASS" if passed else "FAIL"
    return passed, f"{status} -- " + "; ".join(details)


# ---------------------------------------------------------------------------
# Rule 7 -- Invoice-number discipline
# ---------------------------------------------------------------------------

def check_rule_7_invoice_number_discipline(data: dict) -> tuple:
    """
    Each vendor's invoice numbers must be strictly increasing, unique, and
    CONSECUTIVE from an arbitrary per-vendor starting offset (review
    fix 2 -- every vendor now starts numbering somewhere in
    1,000-950,000, not at 1, since real vendors serve other customers too).
    """
    gl = data["gl"]
    working = gl.assign(invoice_dt=pd.to_datetime(gl["invoice_date"]))

    non_consecutive = 0
    duplicated = 0
    offset_out_of_band = 0
    for vendor_id, group in working.groupby("vendor_id"):
        g = group.sort_values(["invoice_dt", "invoice_number"])
        numbers = g["invoice_number"].astype(int).tolist()
        if len(set(numbers)) != len(numbers):
            duplicated += 1
            continue
        sorted_numbers = sorted(numbers)
        expected = list(range(sorted_numbers[0], sorted_numbers[0] + len(sorted_numbers)))
        if numbers != sorted_numbers or sorted_numbers != expected:
            non_consecutive += 1
        if not (1_000 <= sorted_numbers[0] <= 950_000):
            offset_out_of_band += 1

    passed = non_consecutive == 0 and duplicated == 0 and offset_out_of_band == 0
    details = (
        f"vendors with non-increasing/non-consecutive numbers: {non_consecutive}; "
        f"vendors with reused numbers: {duplicated}; "
        f"vendors with a starting offset outside [1000, 950000]: {offset_out_of_band}"
    )
    status = "PASS" if passed else "FAIL"
    return passed, f"{status} -- {details}"


# ---------------------------------------------------------------------------
# Rule 8 -- Planted signatures at designed magnitude
# ---------------------------------------------------------------------------

def check_rule_8_planted_signatures(data: dict) -> tuple:
    gl, vm, answer_key = data["gl"], data["vendor_master"], data["answer_key"]
    gl = gl.assign(
        invoice_dt=pd.to_datetime(gl["invoice_date"]),
        posting_dt=pd.to_datetime(gl["posting_date"]),
    )
    details = []
    all_passed = True

    def note(ok, msg):
        nonlocal all_passed
        all_passed = all_passed and ok
        details.append(("OK" if ok else "FAIL") + " -- " + msg)

    # -- Per-class counts vs config --
    for cls, expected in config.PLANTED_CLASS_COUNTS.items():
        actual = len(answer_key_txn_ids(answer_key, cls))
        note(actual == expected, f"class {cls}: {actual} txns (expected {expected})")
    for cls, expected in config.BENIGN_ITEM_COUNTS.items():
        actual = len(answer_key_txn_ids(answer_key, cls))
        note(actual == expected, f"benign {cls}: {actual} txns (expected {expected})")

    # -- Teräskontio (G): H1 baseline sigma, H2 step + compounding --
    ter = gl[gl["vendor_id"] == config.TERASKONTIO_VENDOR_ID]
    h1 = ter[ter["invoice_dt"].dt.month <= 6]["amount_eur"]
    h2 = ter[ter["invoice_dt"].dt.month >= 7]["amount_eur"]
    h1_cv = h1.std() / h1.mean() if len(h1) else float("nan")
    step_ratio = h2.mean() / h1.mean() if len(h1) and len(h2) else float("nan")
    note(0.01 <= h1_cv <= 0.07, f"Teräskontio H1 amount CV = {h1_cv:.4f} (pinned ~0.03, band [0.01, 0.07])")
    note(1.10 <= step_ratio <= 1.30, f"Teräskontio H2/H1 mean ratio = {step_ratio:.4f} (expect ~1.08-1.19, band [1.10, 1.30])")

    dec_mean = ter[ter["invoice_dt"].dt.month == 12]["amount_eur"].mean()
    dec_over_baseline = dec_mean / h1.mean() - 1.0 if len(h1) else float("nan")
    note(0.10 <= dec_over_baseline <= 0.30, f"Teräskontio December over baseline = {dec_over_baseline:.1%} (expect ~19%, band [10%, 30%])")

    # -- Kuormaraitti euro reconciliation --
    step_eur = config.TERASKONTIO_BASELINE_MEAN_EUR * config.TERASKONTIO_STEP_FRACTION
    kra = gl[gl["vendor_id"] == config.KUORMARAITTI_VENDOR_ID]
    k_h1 = kra[kra["invoice_dt"].dt.month <= 6]["amount_eur"]
    k_h2 = kra[kra["invoice_dt"].dt.month >= 7]["amount_eur"]
    decline_eur = k_h1.mean() - k_h2.mean() if len(k_h1) and len(k_h2) else float("nan")
    tol = config.KUORMARAITTI_RECONCILIATION_TOLERANCE_FRAC
    within_band = abs(decline_eur - step_eur) <= tol * step_eur
    note(within_band, f"Kuormaraitti H1-H2 decline = EUR{decline_eur:.2f} vs step_eur = EUR{step_eur:.2f} "
                       f"(tolerance +/-{tol:.0%})")

    # -- Karrenbach trio (V): shared VAT/address, distinct IBANs and names, 7/5/3 split --
    karrenbach_ids = [r["vendor_id"] for r in config.KARRENBACH_RECORDS]
    kb = vm[vm["vendor_id"].isin(karrenbach_ids)]
    vat_ids = set(kb["vat_id"])
    addresses = set(kb["address"])
    ibans = set(kb["iban"])
    names = set(kb["vendor_name"])
    note(len(kb) == 3, f"Karrenbach trio has {len(kb)} master records (expect 3)")
    note(len(vat_ids) == 1, f"Karrenbach trio shares one VAT id: {len(vat_ids)} distinct value(s)")
    note(len(addresses) == 1, f"Karrenbach trio shares one address: {len(addresses)} distinct value(s)")
    note(len(ibans) == 3, f"Karrenbach trio has 3 distinct IBANs: {len(ibans)} distinct value(s)")
    note(len(names) == 3, f"Karrenbach trio has 3 byte-distinct names: {len(names)} distinct value(s)")
    v_counts = sorted(gl[gl["vendor_id"].isin(karrenbach_ids)].groupby("vendor_id").size().tolist(), reverse=True)
    note(v_counts == [7, 5, 3], f"Karrenbach spend split = {v_counts} (expect [7, 5, 3])")

    # -- Neuvantila (C): tight amount band, correct account, mid-month working days --
    neu = gl[gl["vendor_id"] == config.NEUVANTILA_VENDOR_ID]
    band_ok = bool(((neu["amount_eur"] >= config.NEUVANTILA_AMOUNT_MIN_EUR) & (neu["amount_eur"] <= config.NEUVANTILA_AMOUNT_MAX_EUR)).all())
    account_ok = bool((neu["account"].astype(str) == config.ACCOUNT_NEUVANTILA).all())
    note(len(neu) == 12 and band_ok, f"Neuvantila: {len(neu)} txns, all within band = {band_ok}")
    note(account_ok, "Neuvantila: all postings to the correct consulting account")

    # -- Benign items --
    b1 = gl[gl["vendor_id"] == config.B1_VENDOR_ID]
    note(len(b1) == 12 and bool((b1["amount_eur"] == config.B1_MONTHLY_RENT_EUR).all()),
         f"B1: {len(b1)} txns, all exactly EUR{config.B1_MONTHLY_RENT_EUR:.2f} = "
         f"{bool((b1['amount_eur'] == config.B1_MONTHLY_RENT_EUR).all())}")

    b2_ids = answer_key_txn_ids(answer_key, "B2")
    b2 = gl[gl["txn_id"].isin(b2_ids)]
    note(len(b2) == 2 and bool((b2["posting_dt"].dt.date == config.B2_DATE).all()) and bool((b2["posted_by"] == config.B2_POSTED_BY).all()),
         f"B2: {len(b2)} txns, all posted {config.B2_DATE} by {config.B2_POSTED_BY}")

    b3 = gl[gl["vendor_id"] == config.B3_VENDOR_ID]
    b3_amounts_ok = bool((b3["amount_eur"] == config.B3_AMOUNT_EUR).all())
    b3_invoice_numbers_distinct = b3["invoice_number"].nunique() == len(b3)
    note(len(b3) == 2 and b3_amounts_ok and b3_invoice_numbers_distinct,
         f"B3: {len(b3)} txns, all exactly EUR{config.B3_AMOUNT_EUR:.2f}, distinct invoice numbers = {b3_invoice_numbers_distinct}")

    b4 = gl[gl["vendor_id"] == config.B4_VENDOR_ID]
    note(len(b4) == 1 and bool((b4["amount_eur"] == config.B4_AMOUNT_EUR).all())
         and bool((b4["account"].astype(str) == config.ACCOUNT_B4_CAPEX).all()),
         f"B4: {len(b4)} txn, EUR{config.B4_AMOUNT_EUR:.2f} to the fixed-asset account")

    b5 = gl[gl["vendor_id"] == config.B5_VENDOR_ID]
    note(len(b5) == 1 and bool((b5["amount_eur"] == config.B5_AMOUNT_EUR).all())
         and bool((b5["account"].astype(str) == config.ACCOUNT_B5_INSURANCE).all()),
         f"B5: {len(b5)} txn, EUR{config.B5_AMOUNT_EUR:.2f} to the insurance account")

    # -- Disjointness: D/R/S/A/B1/B3 vendors and W/B2 users all distinct --
    disjoint_vendor_groups = [
        set(config.D_VENDOR_IDS), {config.R_ROUND_VENDOR_ID, config.R_NEAR_VENDOR_ID},
        set(config.S_VENDOR_IDS), {config.KAARNIALA_VENDOR_ID}, {config.B1_VENDOR_ID}, {config.B3_VENDOR_ID},
    ]
    all_vendors_flat = [v for grp in disjoint_vendor_groups for v in grp]
    vendors_disjoint = len(all_vendors_flat) == len(set(all_vendors_flat))
    users_disjoint = config.W_POSTED_BY != config.B2_POSTED_BY
    note(vendors_disjoint, "D/R/S/A/B1/B3 vendor sets are mutually disjoint")
    note(users_disjoint, f"W user ({config.W_POSTED_BY}) and B2 user ({config.B2_POSTED_BY}) are distinct")

    status = "PASS" if all_passed else "FAIL"
    return all_passed, f"{status} -- planted-signature sub-checks", details


# ---------------------------------------------------------------------------
# Rule 9 -- No undeclared signatures (imports rule_tests.py)
# ---------------------------------------------------------------------------

def check_rule_9_no_undeclared_signatures(data: dict) -> tuple:
    gl, vm, calendar_df, answer_key = data["gl"], data["vendor_master"], data["calendar"], data["answer_key"]

    flags_df = rule_tests.run_all_rule_tests(gl, vm, calendar_df)

    # Every flagged txn_id must resolve to SOME answer-key entry (anomalous or benign).
    all_key_txn_ids = answer_key_all_txn_ids(answer_key)
    unresolved = sorted(set(flags_df["txn_id"]) - all_key_txn_ids)

    # Per-test counts must equal the pre-registered table exactly.
    actual_counts = flags_df["test"].value_counts().to_dict()
    count_mismatches = []
    for test_name, expected in config.PREREGISTERED_TEST_COUNTS.items():
        actual = actual_counts.get(test_name, 0)
        if actual != expected:
            count_mismatches.append(f"{test_name}: got {actual}, expected {expected}")

    # No transaction should trip more than one test (the "no double-trip" property).
    per_txn_counts = flags_df["txn_id"].value_counts()
    double_tripped = per_txn_counts[per_txn_counts > 1]

    # -- Per-test flag MEMBERSHIP, not just counts (review fix 5):
    # each test's flagged set must EQUAL its expected answer-key set exactly.
    def flagged_set(test_name):
        return set(flags_df.loc[flags_df["test"] == test_name, "txn_id"])

    membership_checks = {
        "duplicate": (
            flagged_set("duplicate"),
            set(answer_key_txn_ids(answer_key, "D")) | set(answer_key_txn_ids(answer_key, "B3")),
        ),
        "round_sum": (
            flagged_set("round_sum"),
            set(answer_key_txn_ids_by_event(answer_key, "R-ROUND")) | set(answer_key_txn_ids(answer_key, "B1")),
        ),
        "near_threshold": (
            flagged_set("near_threshold"),
            set(answer_key_txn_ids_by_event(answer_key, "R-NEAR")),
        ),
        "split": (
            flagged_set("split"),
            set(answer_key_txn_ids(answer_key, "S")),
        ),
        "calendar": (
            flagged_set("calendar"),
            set(answer_key_txn_ids(answer_key, "W")) | set(answer_key_txn_ids(answer_key, "B2")),
        ),
        "mapping": (
            flagged_set("mapping"),
            set(answer_key_txn_ids(answer_key, "A")),
        ),
        "name_hygiene": (
            flagged_set("name_hygiene"),
            set(),
        ),
    }
    membership_mismatches = []
    for test_name, (actual_set, expected_set) in membership_checks.items():
        if actual_set != expected_set:
            missing = sorted(expected_set - actual_set)
            extra = sorted(actual_set - expected_set)
            membership_mismatches.append(f"{test_name}: missing {missing[:5]}, extra {extra[:5]}")

    passed = (
        len(unresolved) == 0 and len(count_mismatches) == 0 and len(double_tripped) == 0
        and len(membership_mismatches) == 0
    )
    details = [
        f"unresolved flags (no answer-key entry): {len(unresolved)}",
        f"per-test count mismatches: {count_mismatches if count_mismatches else 'none'}",
        f"transactions flagged by >1 test: {len(double_tripped)}",
        f"per-test flagged-set == expected-set for all 7 tests: {len(membership_mismatches) == 0}"
        + (f" ({membership_mismatches})" if membership_mismatches else ""),
        f"total flags: {len(flags_df)} (pre-registered total: {sum(config.PREREGISTERED_TEST_COUNTS.values())})",
    ]
    status = "PASS" if passed else "FAIL"
    return passed, f"{status} -- " + "; ".join(details)


# ---------------------------------------------------------------------------
# Rule 10 -- Answer-key completeness and exactness
# ---------------------------------------------------------------------------

EXPECTED_ANSWER_KEY_EVENT_ROWS = 24  # D:6 + R:2 + S:5 + W:1 + V:1 + A:1 + G:1 + C:1 + B1-B5:5 + B6:1


def check_rule_10_answer_key_completeness(data: dict) -> tuple:
    """
    The answer key is event-grain (one row per D pair / S event / R
    sub-mechanism / etc., review) -- this rule checks every row's
    OWN txn_ids directly (not via the class-aggregating helper, which would
    be the wrong tool here since anomaly_id is now finer-grained than class),
    and separately checks class-level counts still equal config exactly.
    """
    gl, answer_key = data["gl"], data["answer_key"]
    valid_txn_ids = set(gl["txn_id"])

    missing_txn_ids = []
    for _, row in answer_key.iterrows():
        raw = row["txn_ids"]
        for txn_id in (raw.split(";") if raw else []):
            if txn_id not in valid_txn_ids:
                missing_txn_ids.append((row["anomaly_id"], txn_id))

    expected_counts = {**config.PLANTED_CLASS_COUNTS, **config.BENIGN_ITEM_COUNTS}
    count_mismatches = []
    for class_name, expected in expected_counts.items():
        actual = len(answer_key_txn_ids(answer_key, class_name))
        if actual != expected:
            count_mismatches.append(f"{class_name}: key has {actual}, config expects {expected}")

    total_anomalous = sum(
        len(answer_key_txn_ids(answer_key, cls)) for cls in config.PLANTED_CLASS_COUNTS
    )
    total_ok = total_anomalous == config.TOTAL_ANOMALOUS_TRANSACTIONS

    row_count_ok = len(answer_key) == EXPECTED_ANSWER_KEY_EVENT_ROWS

    passed = len(missing_txn_ids) == 0 and len(count_mismatches) == 0 and total_ok and row_count_ok
    details = [
        f"key txn_ids missing from gl_transactions: {len(missing_txn_ids)}",
        f"class-count mismatches: {count_mismatches if count_mismatches else 'none'}",
        f"total anomalous txns: {total_anomalous} (expected {config.TOTAL_ANOMALOUS_TRANSACTIONS})",
        f"answer-key event rows: {len(answer_key)} (expected {EXPECTED_ANSWER_KEY_EVENT_ROWS})",
    ]
    status = "PASS" if passed else "FAIL"
    return passed, f"{status} -- " + "; ".join(details)


# ---------------------------------------------------------------------------
# Rule 11 -- Master hygiene except declared
# ---------------------------------------------------------------------------

def check_rule_11_master_hygiene(data: dict) -> tuple:
    vm = data["vendor_master"]
    karrenbach_ids = set(r["vendor_id"] for r in config.KARRENBACH_RECORDS)

    name_counts = vm["vendor_name"].value_counts()
    duplicate_names = name_counts[name_counts > 1]

    iban_counts = vm["iban"].value_counts()
    duplicate_ibans = iban_counts[iban_counts > 1]

    vat_counts = vm["vat_id"].value_counts()
    duplicate_vats = vat_counts[vat_counts > 1]
    # The one declared exception: the Karrenbach trio shares a VAT id.
    undeclared_vat_dupes = []
    for vat_id, n in duplicate_vats.items():
        vendor_ids_sharing = set(vm.loc[vm["vat_id"] == vat_id, "vendor_id"])
        if vendor_ids_sharing != karrenbach_ids:
            undeclared_vat_dupes.append(vat_id)

    passed = len(duplicate_names) == 0 and len(duplicate_ibans) == 0 and len(undeclared_vat_dupes) == 0
    details = [
        f"duplicate vendor names: {len(duplicate_names)}",
        f"duplicate IBANs: {len(duplicate_ibans)}",
        f"undeclared duplicate VAT ids: {len(undeclared_vat_dupes)} (declared exception: Karrenbach trio)",
    ]
    status = "PASS" if passed else "FAIL"
    return passed, f"{status} -- " + "; ".join(details)


# ---------------------------------------------------------------------------
# Rule 12 -- Memo validity
# ---------------------------------------------------------------------------

MEMO_PATTERNS = [
    re.compile(r"^Tavarantoimitus, tilaus \d{6}$"),
    re.compile(r"^Materiaalitoimitus, tilaus \d{6}$"),
    re.compile(r"^Palvelulasku, \d{6}$"),
    re.compile(r"^Ostolasku, \d{6}$"),
    re.compile(r"^Kertatoimitus, tilaus \d{6}$"),
    re.compile(r"^Terästoimitus, tilaus \d{6}$"),
    re.compile(r"^Terästoimitus, sis\. rahtikulut, tilaus \d{6}$"),
    re.compile(r"^Rahtikuljetus, Teräskontio-erät, tilaus \d{6}$"),
    re.compile(r"^Tiivistetoimitus, tilaus \d{6}$"),
    re.compile(r"^Mainoskampanja, \w+ 2025$"),
    re.compile(r"^Konsultointipalvelu, \w+ 2025$"),
    re.compile(r"^Toimitilavuokra, \w+ 2025$"),
    re.compile(r"^Konehankinta, kalusto$"),
    re.compile(r"^Vuosivakuutusmaksu 2025$"),
    re.compile(r"^Sovittu ylityö, inventaario 15\.11\.2025$"),
    re.compile(r"^Tavarantoimitus, PO-\d+$"),
    re.compile(r"^Ostolasku, tilaus \d{6}$"),        # D and R reserved-class generic memo
    re.compile(r"^Ostolasku, osatoimitus \d{6}$"),   # S reserved-class generic memo
]


def check_rule_12_memo_validity(data: dict) -> tuple:
    gl, answer_key = data["gl"], data["answer_key"]

    def matches_any_template(memo):
        return any(p.match(memo) for p in MEMO_PATTERNS)

    non_conforming = gl.loc[~gl["memo"].map(matches_any_template), "memo"]

    g_ids = answer_key_txn_ids(answer_key, "G")
    breadcrumb_ok = bool(gl.loc[gl["txn_id"].isin(g_ids), "memo"].str.contains("sis. rahtikulut").all()) if g_ids else False

    b2_ids = answer_key_txn_ids(answer_key, "B2")
    b2_memo_ok = bool((gl.loc[gl["txn_id"].isin(b2_ids), "memo"] == config.B2_MEMO).all()) if b2_ids else False

    b3_ids = answer_key_txn_ids(answer_key, "B3")
    b3_memos = gl.loc[gl["txn_id"].isin(b3_ids), "memo"].tolist()
    b3_refs_present = all(any(ref in memo for memo in b3_memos) for ref in config.B3_PO_REFS)
    b3_refs_distinct = len(set(b3_memos)) == len(b3_memos)

    passed = len(non_conforming) == 0 and breadcrumb_ok and b2_memo_ok and b3_refs_present and b3_refs_distinct
    details = [
        f"memos not matching any known template: {len(non_conforming)}",
        f"Teräskontio G-class 'sis. rahtikulut' breadcrumb present in all H2 memos: {breadcrumb_ok}",
        f"B2 memo verbatim match: {b2_memo_ok}",
        f"B3 distinct PO references present: {b3_refs_present and b3_refs_distinct}",
    ]
    status = "PASS" if passed else "FAIL"
    return passed, f"{status} -- " + "; ".join(details)


# ---------------------------------------------------------------------------
# Rule 13 -- Posting lag
# ---------------------------------------------------------------------------

def check_rule_13_posting_lag(data: dict) -> tuple:
    gl, calendar_df = data["gl"], data["calendar"]
    working_days = working_day_set(calendar_df)

    invoice_dates = pd.to_datetime(gl["invoice_date"]).dt.date
    posting_dates = pd.to_datetime(gl["posting_date"]).dt.date

    integ_mask = gl["posted_by"] == config.INTEGRATION_USER
    human_mask = ~integ_mask

    integ_lags = [
        business_days_between(inv, post, working_days)
        for inv, post in zip(invoice_dates[integ_mask], posting_dates[integ_mask])
    ]
    human_lags = [
        business_days_between(inv, post, working_days)
        for inv, post in zip(invoice_dates[human_mask], posting_dates[human_mask])
    ]

    integ_violations = sum(1 for lag in integ_lags if not (0 <= lag <= 1))
    human_violations = sum(1 for lag in human_lags if not (2 <= lag <= 5))

    invoice_out_of_year = int((pd.to_datetime(gl["invoice_date"]).dt.year != config.YEAR).sum())
    posting_out_of_year = int((pd.to_datetime(gl["posting_date"]).dt.year != config.YEAR).sum())

    passed = integ_violations == 0 and human_violations == 0 and invoice_out_of_year == 0 and posting_out_of_year == 0
    details = [
        f"INTEG-01 rows outside 0-1 business-day lag: {integ_violations} of {len(integ_lags)}",
        f"human rows outside 2-5 business-day lag: {human_violations} of {len(human_lags)}",
        f"invoice_date outside {config.YEAR}: {invoice_out_of_year}; posting_date outside {config.YEAR}: {posting_out_of_year}",
    ]
    status = "PASS" if passed else "FAIL"
    return passed, f"{status} -- " + "; ".join(details)


# ---------------------------------------------------------------------------
# Main report
# ---------------------------------------------------------------------------

RULES = [
    (1, "Referential integrity", check_rule_1_referential_integrity),
    (2, "Working-day postings, human posters", check_rule_2_working_day_postings),
    (3, "Amount plausibility", check_rule_3_amount_plausibility),
    (4, "Terms consistency", check_rule_4_terms_consistency),
    (5, "Cadence consistency", check_rule_5_cadence_consistency),
    (6, "Seasonality", check_rule_6_seasonality),
    (7, "Invoice-number discipline", check_rule_7_invoice_number_discipline),
    (8, "Planted signatures at designed magnitude", check_rule_8_planted_signatures),
    (9, "No undeclared signatures", check_rule_9_no_undeclared_signatures),
    (10, "Answer-key completeness and exactness", check_rule_10_answer_key_completeness),
    (11, "Master hygiene except declared", check_rule_11_master_hygiene),
    (12, "Memo validity", check_rule_12_memo_validity),
    (13, "Posting lag", check_rule_13_posting_lag),
]


def main():
    print("=" * 70)
    print(f"{config.COMPANY_NAME} -- AP Ledger Coherence Validation Report")
    print("=" * 70)

    print("\nLoading data files...")
    data = load_data()
    print(f"  gl_transactions:          {len(data['gl']):,} rows")
    print(f"  vendor_master:            {len(data['vendor_master'])} rows")
    print(f"  chart_of_accounts:        {len(data['coa'])} rows")
    print(f"  company_calendar:         {len(data['calendar'])} rows")
    print(f"  answer_key/anomalies:     {len(data['answer_key'])} rows")

    all_passed = True
    results = []

    for rule_num, rule_name, check_fn in RULES:
        print(f"\n--- Rule {rule_num}: {rule_name} ---")
        result = check_fn(data)
        if len(result) == 3:
            passed, msg, sub_details = result
            print(f"  {msg}")
            for line in sub_details:
                print(f"    {line}")
        else:
            passed, msg = result
            print(f"  {msg}")
        results.append((rule_num, rule_name, passed))
        all_passed = all_passed and passed

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for rule_num, rule_name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  Rule {rule_num:2d} [{status}] {rule_name}")

    print()
    if all_passed:
        print("ALL 13 RULES PASSED -- ledger is coherent and ready for analysis.")
        print("=" * 70)
        sys.exit(0)
    else:
        failed = [f"Rule {n}" for n, _, p in results if not p]
        print(f"FAILED RULES: {failed}")
        print("Fix generate_ledger.py and re-run.")
        print("=" * 70)
        sys.exit(1)


if __name__ == "__main__":
    main()
