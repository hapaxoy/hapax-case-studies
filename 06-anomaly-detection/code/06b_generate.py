"""
06b_generate.py -- Builds the Saarnitukku Oy FY2026 purchase ledger (the 06b
"standing vendor-drift review" sequel to 06a's FY2025 case).

Writes, into data/06b/:
    gl_transactions_06b.csv    (exactly 50,000 rows)
    vendor_master_06b.csv      (200 rows)
    chart_of_accounts_06b.csv
    company_calendar_06b.csv
    answer_key_06b.csv         (held out of every analysis path except
                                 06b_mark.py)

Every tunable lives in config_06b.py. Five vendors (V-0001..V-0005) carry the
planted items (D1, D2, D3 drift anomalies; B1, B2 benign lookalikes); the
remaining 195 vendors are ordinary, undifferentiated traffic -- there is no
rule layer in 06b, so (unlike 06a) no accidental-signature avoidance is
needed anywhere in this script.

06a's session artefacts (data/gl_transactions.csv, data/vendor_master.csv,
etc.) are read ONCE here, read-only, purely for the vendor-name collision
check -- never written to, never re-derived from.

Determinism: a single seeded numpy Generator is spawned into named child
streams (SeedSequence.spawn), consumed in a fixed order. No wall-clock or OS
randomness anywhere. Run twice from a clean data/06b/ directory and the
outputs are byte-identical.

Run from the project root or from code/:
    python code/06b_generate.py
"""

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data" / "06b"
SIX_A_VENDOR_MASTER = PROJECT_ROOT / "data" / "vendor_master.csv"

sys.path.insert(0, str(SCRIPT_DIR))
import config_06b as config

# Guard: never write over the code/ input path, and never write anywhere
# other than the explicitly specified data/06b/ output folder. Never touch
# 6a's data/ files (read-only access to the vendor master only, for the
# collision check, is the one exception -- and it is a read, not a write).
assert DATA_DIR != SCRIPT_DIR, "Output path must not equal the code/ input path"
assert DATA_DIR.parts[-2:] == ("data", "06b")


# ---------------------------------------------------------------------------
# RNG setup -- one seeded SeedSequence spawned into named child streams.
# ---------------------------------------------------------------------------

def make_rngs() -> dict:
    root = np.random.SeedSequence(config.RANDOM_SEED)
    names = [
        "identity",       # vendor names/addresses/vat/iban/terms
        "vendor_params",  # generic vendor category + monthly-rate assignment
        "transactions",   # generic vendor per-transaction draws
        "plants",         # the five planted vendors
        "filler",         # the deterministic exact-count adjustment
        "offsets",        # per-vendor invoice-number / order-ref offsets
    ]
    children = root.spawn(len(names))
    return {name: np.random.default_rng(child) for name, child in zip(names, children)}


# ---------------------------------------------------------------------------
# Calendar and business-day arithmetic (same mechanics as 06a's generator,
# reduced to what 06b actually needs -- there is no calendar-anomaly plant).
# ---------------------------------------------------------------------------

def build_calendar() -> tuple:
    rows = []
    working_days = set()
    d = dt.date(config.YEAR, 1, 1)
    while d.year == config.YEAR:
        is_weekend = d.weekday() >= 5
        holiday_note = config.HOLIDAYS_2026.get(d)
        is_working = (not is_weekend) and (holiday_note is None)
        note = holiday_note if holiday_note is not None else ("Weekend" if is_weekend else "")
        rows.append({"date": d.isoformat(), "is_working_day": is_working, "note": note})
        if is_working:
            working_days.add(d)
        d += dt.timedelta(days=1)
    calendar_df = pd.DataFrame(rows, columns=["date", "is_working_day", "note"])
    return calendar_df, working_days


def add_business_days(start_date: dt.date, n: int, working_days: set) -> dt.date:
    d = start_date
    remaining = n
    steps = 0
    while remaining > 0 and steps < 30:
        d += dt.timedelta(days=1)
        steps += 1
        if d in working_days:
            remaining -= 1
    return d


def days_in_month(month: int) -> int:
    import calendar as pycalendar
    return pycalendar.monthrange(config.YEAR, month)[1]


INVOICE_DATE_WORKING_DAY_SHARE = 0.90


def weighted_invoice_day(rng: np.random.Generator, month: int, working_days: set) -> int:
    """Draw a day-of-month weighted so ~90% of organic invoice dates land on
    a working day (mirrors 06a's realism choice -- an issued invoice is far
    more likely dated on a working day than a weekend/holiday)."""
    n_days = days_in_month(month)
    is_working = [dt.date(config.YEAR, month, d) in working_days for d in range(1, n_days + 1)]
    n_working = sum(is_working)
    n_nonworking = n_days - n_working
    working_weight = INVOICE_DATE_WORKING_DAY_SHARE / n_working if n_working > 0 else 0.0
    nonworking_weight = (1.0 - INVOICE_DATE_WORKING_DAY_SHARE) / n_nonworking if n_nonworking > 0 else 0.0
    weights = np.array([working_weight if w else nonworking_weight for w in is_working])
    weights = weights / weights.sum()
    return int(rng.choice(np.arange(1, n_days + 1), p=weights))


def choose_posted_by_and_posting_date(rng: np.random.Generator, invoice_date: dt.date, working_days: set) -> tuple:
    is_integ = rng.random() < config.INTEGRATION_SHARE
    if is_integ:
        posted_by = config.INTEGRATION_USER
        lag_days = int(rng.choice(config.INTEGRATION_LAG_CALENDAR_DAYS))
        posting_date = invoice_date + dt.timedelta(days=lag_days)
        if posting_date.year != config.YEAR:
            posting_date = invoice_date
        return posted_by, posting_date
    posted_by = str(rng.choice(config.HUMAN_USERS))
    lag_biz = int(rng.choice(config.HUMAN_LAG_BUSINESS_DAYS))
    posting_date = add_business_days(invoice_date, lag_biz, working_days)
    if posting_date.year != config.YEAR:
        return config.INTEGRATION_USER, invoice_date
    return posted_by, posting_date


# ---------------------------------------------------------------------------
# Amount / price helpers
# ---------------------------------------------------------------------------

import math


def lognormal_mu_sigma(mean: float, cv: float) -> tuple:
    sigma2 = math.log(1.0 + cv ** 2)
    sigma = math.sqrt(sigma2)
    mu = math.log(mean) - 0.5 * sigma2
    return mu, sigma


def draw_lognormal(rng: np.random.Generator, mean: float, cv: float) -> float:
    mu, sigma = lognormal_mu_sigma(mean, cv)
    return float(rng.lognormal(mu, sigma))


# ---------------------------------------------------------------------------
# Vendor identity generation (Finland-only -- see config_06b.py docstring)
# ---------------------------------------------------------------------------

def make_vat_id(rng: np.random.Generator) -> str:
    digits = "".join(str(int(rng.integers(0, 10))) for _ in range(8))
    return f"FI{digits}"


def iban_check_digits(country: str, bban: str) -> str:
    """ISO 13616 mod-97 check digits for a country code and BBAN."""
    digits = "".join(str(int(c, 36)) for c in bban + country + "00")
    return f"{98 - int(digits) % 97:02d}"


def make_iban(rng: np.random.Generator, used_ibans: set) -> str:
    """Draw a unique IBAN, then give it an invented bank code (the draw is
    unchanged, so later draws are unaffected; the BBAN's start becomes
    FICTIONAL_BANK_PREFIX_FI and the check digits are recomputed)."""
    while True:
        check = f"{int(rng.integers(0, 100)):02d}"
        body = "".join(str(int(rng.integers(0, 10))) for _ in range(14))
        iban = f"FI{check}{body}"
        if iban not in used_ibans:
            used_ibans.add(iban)
            prefix = config.FICTIONAL_BANK_PREFIX_FI
            bban = prefix + body[len(prefix):]
            return f"FI{iban_check_digits('FI', bban)}{bban}"


def make_address(rng: np.random.Generator) -> str:
    street = str(rng.choice(config.ADDRESS_STREETS))
    number = int(rng.integers(1, 60))
    city = str(rng.choice(config.ADDRESS_CITIES))
    postal = int(rng.integers(1000, 99999))
    return f"{street} {number}, {postal:05d} {city}"


def build_name_pool(rng: np.random.Generator) -> dict:
    candidates = [
        f"{p}{m} {s}"
        for p in config.GENERIC_NAME_PREFIXES
        for m in config.GENERIC_NAME_MID
        for s in config.GENERIC_NAME_SUFFIXES
    ]
    order = rng.permutation(len(candidates))
    return {"candidates": candidates, "order": order.tolist(), "next": 0}


def draw_unique_name(rng: np.random.Generator, pool: dict, used_names: set) -> str:
    while True:
        if pool["next"] >= len(pool["order"]):
            extra = f"{pool['candidates'][pool['next'] % len(pool['candidates'])]} {pool['next']}"
            pool["next"] += 1
            if extra not in used_names:
                used_names.add(extra)
                return extra
            continue
        idx = pool["order"][pool["next"]]
        pool["next"] += 1
        name = pool["candidates"][idx]
        if name not in used_names:
            used_names.add(name)
            return name


def check_name_collisions(candidate_names: list) -> None:
    """
    Collision-check every 06b vendor name against 6a's real vendor master
    and the six case-study company names (a design requirement). Raises
    AssertionError with the offending name(s) if anything collides -- this
    generator refuses to write a ledger with a colliding vendor name.
    """
    print("  Checking vendor-name collisions against 6a's vendor master and "
          "the six portfolio company names...")
    assert SIX_A_VENDOR_MASTER.exists(), f"6a vendor master not found for the collision check: {SIX_A_VENDOR_MASTER}"
    six_a_names = set(pd.read_csv(SIX_A_VENDOR_MASTER)["vendor_name"].astype(str).str.strip().str.lower())
    portfolio_names_lower = [n.lower() for n in config.PORTFOLIO_COMPANY_NAMES]

    collisions = []
    for name in candidate_names:
        name_lower = name.strip().lower()
        if name_lower in six_a_names:
            collisions.append((name, "exact match in 6a vendor_master.csv"))
            continue
        for portfolio_name in portfolio_names_lower:
            if portfolio_name in name_lower or name_lower in portfolio_name:
                collisions.append((name, f"collides with portfolio company name '{portfolio_name}'"))
    assert not collisions, f"Vendor name collision(s) found, refusing to generate: {collisions}"
    print(f"  Clear: {len(candidate_names)} vendor names checked, 0 collisions.")


def generate_generic_identities(rng: np.random.Generator, vendor_ids: list) -> dict:
    pool = build_name_pool(rng)
    used_names = set()
    used_ibans = set()
    identities = {}
    for vid in vendor_ids:
        name = draw_unique_name(rng, pool, used_names)
        # Per-vendor pins (config), applied after every draw for this vendor
        name = config.GENERIC_NAME_PINS_BY_VENDOR_ID.get(vid, name)
        vat_id = make_vat_id(rng)
        vat_id = config.VAT_ID_PINS_BY_VENDOR_ID.get(vid, vat_id)
        iban = make_iban(rng, used_ibans)
        address = make_address(rng)
        terms_days = int(rng.choice(config.TERMS_DAYS_OPTIONS, p=config.TERMS_DAYS_WEIGHTS))
        identities[vid] = {
            "vendor_id": vid, "vendor_name": name, "country": "FI",
            "vat_id": vat_id, "iban": iban, "address": address, "terms_days": terms_days,
        }
    return identities


def assign_category_and_accounts(rng: np.random.Generator) -> tuple:
    categories = list(config.GENERIC_VENDOR_CATEGORIES.keys())
    weights = [config.GENERIC_VENDOR_CATEGORIES[c]["weight"] for c in categories]
    category = str(rng.choice(categories, p=weights))
    pool = config.GENERIC_VENDOR_CATEGORIES[category]["accounts"]
    return category, [str(rng.choice(pool))]


# ---------------------------------------------------------------------------
# Generic (ordinary) vendor transaction generation
# ---------------------------------------------------------------------------

def generate_generic_stream(rng: np.random.Generator, vendor: dict, working_days: set, n_override: int = None) -> list:
    cat = config.GENERIC_VENDOR_CATEGORIES[vendor["category"]]
    raw_dates = []
    if n_override is None:
        shape = cat["monthly_rate_gamma_shape"]
        scale = cat["monthly_rate_mean"] / shape
        base_rate = min(float(rng.gamma(shape, scale)), config.MONTHLY_RATE_CLIP_MAX)
        for month in range(1, 13):
            lam = base_rate * config.MONTH_SEASONALITY_WEIGHT[month]
            n_month = int(rng.poisson(lam))
            for _ in range(n_month):
                raw_dates.append((month, weighted_invoice_day(rng, month, working_days)))
    else:
        weights = np.array([config.MONTH_SEASONALITY_WEIGHT[m] for m in range(1, 13)], dtype=float)
        weights = weights / weights.sum()
        month_counts = rng.multinomial(n_override, weights)
        for month, n_month in zip(range(1, 13), month_counts):
            for _ in range(int(n_month)):
                raw_dates.append((month, weighted_invoice_day(rng, month, working_days)))

    account = vendor["allowed_accounts"][0]
    transactions = []
    for month, day in raw_dates:
        invoice_date = dt.date(config.YEAR, month, day)
        if cat["has_unit_price"]:
            qty_lo, qty_hi = cat["quantity_range"]
            quantity = int(rng.integers(qty_lo, qty_hi + 1))
            unit_price = draw_lognormal(rng, cat["unit_price_mean"], cat["unit_price_cv"])
            unit_price = round(unit_price, 4)
            amount = round(quantity * unit_price, 2)
        else:
            quantity = 1
            amount = round(draw_lognormal(rng, cat["amount_mean"], cat["amount_cv"]), 2)
            unit_price = amount
        posted_by, posting_date = choose_posted_by_and_posting_date(rng, invoice_date, working_days)
        due_date = invoice_date + dt.timedelta(days=vendor["terms_days"])
        transactions.append({
            "vendor_id": vendor["vendor_id"], "vendor_name": vendor["vendor_name"],
            "invoice_date": invoice_date, "posting_date": posting_date, "due_date": due_date,
            "account": account, "quantity": quantity, "unit_price_eur": round(unit_price, 2),
            "amount_eur": amount, "posted_by": posted_by, "memo_category": vendor["category"],
            "_plant_tag": "",
        })
    return transactions


# ---------------------------------------------------------------------------
# The five planted vendors
# ---------------------------------------------------------------------------

def _plant_invoice_dates(rng: np.random.Generator, working_days: set, monthly_rate_mean: float) -> list:
    """Steady monthly invoice count (Poisson around monthly_rate_mean,
    seasonality-weighted like the rest of the ledger) for a planted vendor.
    Every month must clear the drift review's own minimum of 3 invoices/month
    (step 1 of the method) -- monthly_rate_mean is chosen well above that
    floor so this holds in practice; re-drawing on the rare short month keeps
    it true by construction rather than by luck."""
    dates = []
    for month in range(1, 13):
        lam = monthly_rate_mean * config.MONTH_SEASONALITY_WEIGHT[month]
        n_month = int(rng.poisson(lam))
        guard = 0
        while n_month < 4 and guard < 20:
            n_month = int(rng.poisson(lam))
            guard += 1
        for _ in range(n_month):
            dates.append((month, weighted_invoice_day(rng, month, working_days)))
    return dates


def _make_plant_transaction(rng, vendor_id, vendor_name, account, terms_days, invoice_date,
                             quantity_range, unit_price_mean, sigma_frac, memo_template,
                             working_days, plant_tag):
    qty_lo, qty_hi = quantity_range
    quantity = int(rng.integers(qty_lo, qty_hi + 1))
    noise = float(rng.normal(0.0, sigma_frac))
    unit_price = round(max(unit_price_mean * (1 + noise), 0.50), 4)
    amount = round(quantity * unit_price, 2)
    posted_by, posting_date = choose_posted_by_and_posting_date(rng, invoice_date, working_days)
    due_date = invoice_date + dt.timedelta(days=terms_days)
    return {
        "vendor_id": vendor_id, "vendor_name": vendor_name,
        "invoice_date": invoice_date, "posting_date": posting_date, "due_date": due_date,
        "account": account, "quantity": quantity, "unit_price_eur": round(unit_price, 2),
        "amount_eur": amount, "posted_by": posted_by, "memo": memo_template,
        "_plant_tag": plant_tag,
    }


def generate_D1(rng, working_days, terms_days) -> list:
    """Fast drift: ~2.5%/month compounding from April onward."""
    txns = []
    for month, day in _plant_invoice_dates(rng, working_days, config.D1_MONTHLY_RATE_MEAN):
        invoice_date = dt.date(config.YEAR, month, day)
        if month >= config.D1_DRIFT_START_MONTH:
            k = month - (config.D1_DRIFT_START_MONTH - 1)
            multiplier = (1 + config.D1_DRIFT_RATE_MONTHLY) ** k
        else:
            multiplier = 1.0
        mean_price = config.D1_BASE_UNIT_PRICE_EUR * multiplier
        memo = config.MEMO_TEMPLATES_BY_CATEGORY["goods_bulk"]
        txn = _make_plant_transaction(
            rng, config.D1_VENDOR_ID, config.D1_VENDOR_NAME, config.D1_ACCOUNT, terms_days,
            invoice_date, config.D1_QUANTITY_RANGE, mean_price, config.D1_SIGMA_FRAC, memo,
            working_days, "D1",
        )
        txns.append(txn)
    return txns


def generate_D2(rng, working_days, terms_days) -> list:
    """Slow drift: ~1.0%/month compounding from February onward -- the
    sensitivity test (the drift begins inside the baseline-only window)."""
    txns = []
    for month, day in _plant_invoice_dates(rng, working_days, config.D2_MONTHLY_RATE_MEAN):
        invoice_date = dt.date(config.YEAR, month, day)
        if month >= config.D2_DRIFT_START_MONTH:
            k = month - (config.D2_DRIFT_START_MONTH - 1)
            multiplier = (1 + config.D2_DRIFT_RATE_MONTHLY) ** k
        else:
            multiplier = 1.0
        mean_price = config.D2_BASE_UNIT_PRICE_EUR * multiplier
        memo = config.MEMO_TEMPLATES_BY_CATEGORY["goods_bulk"]
        txn = _make_plant_transaction(
            rng, config.D2_VENDOR_ID, config.D2_VENDOR_NAME, config.D2_ACCOUNT, terms_days,
            invoice_date, config.D2_QUANTITY_RANGE, mean_price, config.D2_SIGMA_FRAC, memo,
            working_days, "D2",
        )
        txns.append(txn)
    return txns


def generate_D3(rng, working_days, terms_days) -> list:
    """Bundling drift, the G re-run: freight folded into goods lines from
    June (one-off step), then ~1.8%/month compounding inside the bundle --
    with the Finnish memo breadcrumb from June onward, as in 06a."""
    txns = []
    for month, day in _plant_invoice_dates(rng, working_days, config.D3_MONTHLY_RATE_MEAN):
        invoice_date = dt.date(config.YEAR, month, day)
        if month >= config.D3_BUNDLE_START_MONTH:
            k = month - config.D3_BUNDLE_START_MONTH
            multiplier = (1 + config.D3_BUNDLE_STEP_FRACTION) * ((1 + config.D3_DRIFT_RATE_MONTHLY) ** k)
            memo = f"Materiaalitoimitus, {config.D3_MEMO_BREADCRUMB}, tilaus {{ref}}"
        else:
            multiplier = 1.0
            memo = config.MEMO_TEMPLATES_BY_CATEGORY["goods_bulk"]
        mean_price = config.D3_BASE_UNIT_PRICE_EUR * multiplier
        txn = _make_plant_transaction(
            rng, config.D3_VENDOR_ID, config.D3_VENDOR_NAME, config.D3_ACCOUNT, terms_days,
            invoice_date, config.D3_QUANTITY_RANGE, mean_price, config.D3_SIGMA_FRAC, memo,
            working_days, "D3",
        )
        txns.append(txn)
    return txns


def generate_B1(rng, working_days, terms_days) -> list:
    """Contractual indexation: +5.2% step, effective for invoices dated from
    February onward (January invoices still reflect December-negotiated
    deliveries at the outgoing rate -- see config_06b.py's B1 comment).
    Memo cites the index clause from the effective month onward."""
    txns = []
    for month, day in _plant_invoice_dates(rng, working_days, config.B1_MONTHLY_RATE_MEAN):
        invoice_date = dt.date(config.YEAR, month, day)
        if month >= config.B1_STEP_EFFECTIVE_MONTH:
            mean_price = config.B1_BASE_UNIT_PRICE_EUR * (1 + config.B1_STEP_FRACTION)
            memo = "Materiaalitoimitus, sopimuksen indeksikorotus 1.1.2026, tilaus {ref}"
        else:
            mean_price = config.B1_BASE_UNIT_PRICE_EUR
            memo = config.MEMO_TEMPLATES_BY_CATEGORY["goods_bulk"]
        txn = _make_plant_transaction(
            rng, config.B1_VENDOR_ID, config.B1_VENDOR_NAME, config.B1_ACCOUNT, terms_days,
            invoice_date, config.B1_QUANTITY_RANGE, mean_price, config.B1_SIGMA_FRAC, memo,
            working_days, "B1",
        )
        txns.append(txn)
    return txns


def generate_B2(rng, working_days, terms_days) -> list:
    """Market repricing: ~9% step in August, announced in a memo from that
    month onward."""
    txns = []
    for month, day in _plant_invoice_dates(rng, working_days, config.B2_MONTHLY_RATE_MEAN):
        invoice_date = dt.date(config.YEAR, month, day)
        if month >= config.B2_STEP_MONTH:
            mean_price = config.B2_BASE_UNIT_PRICE_EUR * (1 + config.B2_STEP_FRACTION)
            memo = "Tavarantoimitus, toimittajan hinnankorotus 1.8.2026, tilaus {ref}"
        else:
            mean_price = config.B2_BASE_UNIT_PRICE_EUR
            memo = config.MEMO_TEMPLATES_BY_CATEGORY["goods_small"]
        txn = _make_plant_transaction(
            rng, config.B2_VENDOR_ID, config.B2_VENDOR_NAME, config.B2_ACCOUNT, terms_days,
            invoice_date, config.B2_QUANTITY_RANGE, mean_price, config.B2_SIGMA_FRAC, memo,
            working_days, "B2",
        )
        txns.append(txn)
    return txns


# ---------------------------------------------------------------------------
# Answer key
# ---------------------------------------------------------------------------

def build_answer_key(df: pd.DataFrame) -> list:
    rows = []

    def txn_ids_for_tag(tag):
        return df.loc[df["_plant_tag"] == tag, "txn_id"].tolist()

    def months_for_tag(tag):
        return sorted(set(df.loc[df["_plant_tag"] == tag, "invoice_date"].map(lambda d: d.month)))

    rows.append({
        "anomaly_id": "D1", "class": "D1", "kind": "anomalous",
        "vendor_id": config.D1_VENDOR_ID, "vendor_name": config.D1_VENDOR_NAME,
        "txn_ids": ";".join(txn_ids_for_tag("D1")), "months": ";".join(str(m) for m in months_for_tag("D1")),
        "mechanism": f"Fast drift: unit price rises ~{config.D1_DRIFT_RATE_MONTHLY*100:.1f}%/month, "
                     f"compounding, from month {config.D1_DRIFT_START_MONTH} (April) onward. No covering memo.",
        "designed_catch": "drift_report", "expected_verdict": "worry",
        "expected_finding": "Sustained per-vendor unit-price drift with no memo explanation.",
        "notes": f"drift_start_month={config.D1_DRIFT_START_MONTH};drift_rate_monthly={config.D1_DRIFT_RATE_MONTHLY};"
                 f"base_unit_price_eur={config.D1_BASE_UNIT_PRICE_EUR};sigma_frac={config.D1_SIGMA_FRAC}",
    })
    rows.append({
        "anomaly_id": "D2", "class": "D2", "kind": "anomalous",
        "vendor_id": config.D2_VENDOR_ID, "vendor_name": config.D2_VENDOR_NAME,
        "txn_ids": ";".join(txn_ids_for_tag("D2")), "months": ";".join(str(m) for m in months_for_tag("D2")),
        "mechanism": f"Slow drift: unit price rises ~{config.D2_DRIFT_RATE_MONTHLY*100:.1f}%/month, "
                     f"compounding, from month {config.D2_DRIFT_START_MONTH} (February) onward -- starts inside "
                     "the baseline-only window (months 1-3), the sensitivity test. No covering memo.",
        "designed_catch": "drift_report", "expected_verdict": "worry",
        "expected_finding": "Sustained per-vendor unit-price drift with no memo explanation (harder catch: "
                             "the drift partially contaminates its own early baseline).",
        "notes": f"drift_start_month={config.D2_DRIFT_START_MONTH};drift_rate_monthly={config.D2_DRIFT_RATE_MONTHLY};"
                 f"base_unit_price_eur={config.D2_BASE_UNIT_PRICE_EUR};sigma_frac={config.D2_SIGMA_FRAC}",
    })
    rows.append({
        "anomaly_id": "D3", "class": "D3", "kind": "anomalous",
        "vendor_id": config.D3_VENDOR_ID, "vendor_name": config.D3_VENDOR_NAME,
        "txn_ids": ";".join(txn_ids_for_tag("D3")), "months": ";".join(str(m) for m in months_for_tag("D3")),
        "mechanism": f"Bundling drift (the G re-run): freight folded into goods lines from month "
                     f"{config.D3_BUNDLE_START_MONTH} (June) onward (+{config.D3_BUNDLE_STEP_FRACTION*100:.0f}% "
                     f"step), then ~{config.D3_DRIFT_RATE_MONTHLY*100:.1f}%/month compounding inside the bundle. "
                     f"Memo gains the breadcrumb '{config.D3_MEMO_BREADCRUMB}' from June onward.",
        "designed_catch": "drift_report", "expected_verdict": "worry",
        "expected_finding": "Vendor price drift concealed by a billing-structure change (freight bundled into "
                             "the goods price); the memo breadcrumb is discoverable but does not explain away "
                             "the ongoing rate of rise once the bundle is accounted for.",
        "notes": f"bundle_start_month={config.D3_BUNDLE_START_MONTH};bundle_step_fraction={config.D3_BUNDLE_STEP_FRACTION};"
                 f"drift_rate_monthly={config.D3_DRIFT_RATE_MONTHLY};base_unit_price_eur={config.D3_BASE_UNIT_PRICE_EUR};"
                 f"sigma_frac={config.D3_SIGMA_FRAC}",
    })
    rows.append({
        "anomaly_id": "B1", "class": "B1", "kind": "benign",
        "vendor_id": config.B1_VENDOR_ID, "vendor_name": config.B1_VENDOR_NAME,
        "txn_ids": ";".join(txn_ids_for_tag("B1")), "months": ";".join(str(m) for m in months_for_tag("B1")),
        "mechanism": f"Contractual indexation: +{config.B1_STEP_FRACTION*100:.1f}% step, effective for invoices "
                     f"dated from month {config.B1_STEP_EFFECTIVE_MONTH} (February) onward (January invoices "
                     "still reflect December-negotiated deliveries at the outgoing rate). Memo cites the index "
                     "clause from the effective month onward.",
        "designed_catch": "drift_report", "expected_verdict": "stand_down",
        "expected_finding": "A step, not organic drift -- distinguishable from D1-D3 only via the memo trail. "
                             "The step lands at the edge of the method's own no-baseline scope limit, "
                             "so whether it crosses the flag threshold is itself part of "
                             "the pre-registered test.",
        "notes": f"step_fraction={config.B1_STEP_FRACTION};step_effective_month={config.B1_STEP_EFFECTIVE_MONTH};"
                 f"base_unit_price_eur={config.B1_BASE_UNIT_PRICE_EUR};sigma_frac={config.B1_SIGMA_FRAC}",
    })
    rows.append({
        "anomaly_id": "B2", "class": "B2", "kind": "benign",
        "vendor_id": config.B2_VENDOR_ID, "vendor_name": config.B2_VENDOR_NAME,
        "txn_ids": ";".join(txn_ids_for_tag("B2")), "months": ";".join(str(m) for m in months_for_tag("B2")),
        "mechanism": f"Market repricing: +{config.B2_STEP_FRACTION*100:.0f}% step in month {config.B2_STEP_MONTH} "
                     "(August), announced in a memo from that month onward.",
        "designed_catch": "drift_report", "expected_verdict": "stand_down",
        "expected_finding": "A single sharp price excursion with a covering memo -- distinguishable from "
                             "D1-D3 only via the memo trail.",
        "notes": f"step_fraction={config.B2_STEP_FRACTION};step_month={config.B2_STEP_MONTH};"
                 f"base_unit_price_eur={config.B2_BASE_UNIT_PRICE_EUR};sigma_frac={config.B2_SIGMA_FRAC}",
    })
    return rows


# ---------------------------------------------------------------------------
# Main assembly
# ---------------------------------------------------------------------------

def write_csv(df: pd.DataFrame, path: Path) -> None:
    assert path.parent == DATA_DIR, f"Refusing to write outside data/06b/: {path}"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        df.to_csv(fh, index=False, lineterminator="\n")


def main():
    print("=" * 70)
    print(f"{config.COMPANY_NAME} -- FY{config.YEAR} purchase ledger generation (06b)")
    print("=" * 70)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rngs = make_rngs()

    print("\n[1/7] Building company calendar and chart of accounts...")
    calendar_df, working_days = build_calendar()
    coa_df = pd.DataFrame(config.CHART_OF_ACCOUNTS, columns=["account", "name_fi", "name_en", "class"])
    print(f"  calendar: {len(calendar_df)} days, {len(working_days)} working days")
    print(f"  chart of accounts: {len(coa_df)} accounts")

    print("\n[2/7] Generating vendor identities (200 vendors) and checking name collisions...")
    n_generic = config.TOTAL_VENDORS - len(config.RESERVED_VENDOR_IDS)
    generic_vendor_ids = [f"V-{i:04d}" for i in range(6, 6 + n_generic)]
    identities = generate_generic_identities(rngs["identity"], generic_vendor_ids)

    all_names = [identities[vid]["vendor_name"] for vid in generic_vendor_ids] + list(config.RESERVED_VENDOR_NAMES.values())
    check_name_collisions(all_names)

    print("\n[3/7] Assigning vendor categories/accounts and generating ordinary traffic...")
    vendor_lookup = {}
    filler_by_vendor = {}
    for vid in generic_vendor_ids:
        identity = identities[vid]
        category, allowed_accounts = assign_category_and_accounts(rngs["vendor_params"])
        vendor_lookup[vid] = {**identity, "category": category, "allowed_accounts": allowed_accounts}
        filler_by_vendor[vid] = generate_generic_stream(rngs["transactions"], vendor_lookup[vid], working_days)
    organic_total = sum(len(v) for v in filler_by_vendor.values())
    print(f"  {len(generic_vendor_ids)} generic vendors, {organic_total:,} ordinary transactions")

    print("\n[4/7] Generating the five planted vendors (D1, D2, D3, B1, B2)...")
    # Reserved vendors draw a fixed terms_days (30, the most common tier) --
    # simpler than routing them through generate_generic_identities, and
    # their identity fields are attached directly below.
    reserved_terms_days = 30
    d1_txns = generate_D1(rngs["plants"], working_days, reserved_terms_days)
    d2_txns = generate_D2(rngs["plants"], working_days, reserved_terms_days)
    d3_txns = generate_D3(rngs["plants"], working_days, reserved_terms_days)
    b1_txns = generate_B1(rngs["plants"], working_days, reserved_terms_days)
    b2_txns = generate_B2(rngs["plants"], working_days, reserved_terms_days)
    print(f"  D1: {len(d1_txns)}, D2: {len(d2_txns)}, D3: {len(d3_txns)}, "
          f"B1: {len(b1_txns)}, B2: {len(b2_txns)}")

    reserved_identities = {}
    used_ibans_reserved = set()
    for vid in config.RESERVED_VENDOR_IDS:
        reserved_identities[vid] = {
            "vendor_id": vid, "vendor_name": config.RESERVED_VENDOR_NAMES[vid], "country": "FI",
            "vat_id": make_vat_id(rngs["identity"]), "iban": make_iban(rngs["identity"], used_ibans_reserved),
            "address": make_address(rngs["identity"]), "terms_days": reserved_terms_days,
            "allowed_accounts": config.RESERVED_VENDOR_ACCOUNTS[vid],
        }

    print("\n[5/7] Applying the deterministic filler adjustment to hit exactly "
          f"{config.TOTAL_TRANSACTIONS:,} rows...")
    fixed_total = len(d1_txns) + len(d2_txns) + len(d3_txns) + len(b1_txns) + len(b2_txns)
    filler_total_before = sum(len(v) for v in filler_by_vendor.values())
    current_total = fixed_total + filler_total_before
    delta = config.TOTAL_TRANSACTIONS - current_total
    print(f"  planted rows: {fixed_total:,}; ordinary rows: {filler_total_before:,}; "
          f"running total: {current_total:,}; delta needed: {delta:+,}")

    n_flex = min(config.N_FLEX_VENDORS, len(generic_vendor_ids))
    flex_vendor_ids = sorted(generic_vendor_ids, key=lambda v: (-len(filler_by_vendor[v]), v))[:n_flex]
    if delta > 0:
        base_share, remainder = divmod(delta, n_flex)
        for i, vid in enumerate(flex_vendor_ids):
            share = base_share + (1 if i < remainder else 0)
            if share == 0:
                continue
            extra = generate_generic_stream(rngs["filler"], vendor_lookup[vid], working_days, n_override=share)
            filler_by_vendor[vid] = filler_by_vendor[vid] + extra
        print(f"  added {delta} rows across {n_flex} flex vendors")
    elif delta < 0:
        remove_total = -delta
        base_share, remainder = divmod(remove_total, n_flex)
        for i, vid in enumerate(flex_vendor_ids):
            remove_n = base_share + (1 if i < remainder else 0)
            if remove_n == 0:
                continue
            rows = sorted(filler_by_vendor[vid], key=lambda t: (t["invoice_date"], t["amount_eur"]))
            assert len(rows) > remove_n, f"flex vendor {vid} too small to absorb its share"
            filler_by_vendor[vid] = rows[:-remove_n]
        print(f"  removed {remove_total} rows across {n_flex} flex vendors")
    else:
        print("  no adjustment needed -- organic generation hit the target exactly")

    all_txns = d1_txns + d2_txns + d3_txns + b1_txns + b2_txns
    for vid in generic_vendor_ids:
        all_txns.extend(filler_by_vendor[vid])

    total_rows = len(all_txns)
    print(f"  final row count: {total_rows:,}")
    assert total_rows == config.TOTAL_TRANSACTIONS, f"Row count mismatch: got {total_rows}, expected {config.TOTAL_TRANSACTIONS}"

    print("\n[6/7] Assigning invoice numbers, order refs, txn_ids, finalising memos...")
    df = pd.DataFrame(all_txns)
    df = df.sort_values(["vendor_id", "invoice_date", "posting_date"], kind="stable").reset_index(drop=True)

    all_vendor_ids_ordered = config.RESERVED_VENDOR_IDS + generic_vendor_ids
    OFFSET_MIN, OFFSET_MAX = 1_000, 950_000
    invoice_offset_by_vendor = {vid: int(rngs["offsets"].integers(OFFSET_MIN, OFFSET_MAX + 1)) for vid in all_vendor_ids_ordered}
    order_ref_offset_by_vendor = {vid: int(rngs["offsets"].integers(OFFSET_MIN, OFFSET_MAX + 1)) for vid in all_vendor_ids_ordered}

    starting_offset = df["vendor_id"].map(invoice_offset_by_vendor)
    seq0 = df.groupby("vendor_id", sort=False).cumcount()
    df["invoice_number"] = (starting_offset + seq0).map(lambda n: f"{n:06d}")
    order_ref_start = df["vendor_id"].map(order_ref_offset_by_vendor)
    df["order_ref"] = (order_ref_start + seq0).map(lambda n: f"{n:06d}")

    def finalise_memo(row):
        month_fi = config.FINNISH_MONTH_NAMES[row["invoice_date"].month]
        if isinstance(row.get("memo"), str) and row["memo"]:
            return row["memo"].format(ref=row["order_ref"], month_fi=month_fi)
        template = config.MEMO_TEMPLATES_BY_CATEGORY[row["memo_category"]]
        return template.format(ref=row["order_ref"], month_fi=month_fi)

    df["memo"] = df.apply(finalise_memo, axis=1)

    df = df.sort_values(["posting_date", "vendor_id", "invoice_number"], kind="stable").reset_index(drop=True)
    df["txn_id"] = [f"TXN{i + 1:06d}" for i in range(len(df))]

    answer_key_rows = build_answer_key(df)

    df["invoice_date"] = df["invoice_date"].map(lambda d: d.isoformat())
    df["posting_date"] = df["posting_date"].map(lambda d: d.isoformat())
    df["due_date"] = df["due_date"].map(lambda d: d.isoformat())

    gl_df = df[[
        "txn_id", "posting_date", "invoice_date", "due_date", "vendor_id", "vendor_name",
        "account", "quantity", "unit_price_eur", "amount_eur", "invoice_number", "posted_by", "memo",
    ]].copy()

    vendor_master_rows = []
    for vid in all_vendor_ids_ordered:
        info = reserved_identities[vid] if vid in reserved_identities else vendor_lookup[vid]
        vendor_master_rows.append({
            "vendor_id": vid, "vendor_name": info["vendor_name"], "country": info["country"],
            "vat_id": info["vat_id"], "iban": info["iban"], "address": info["address"],
            "terms_days": info["terms_days"], "allowed_accounts": ";".join(info["allowed_accounts"]),
            "active_from": f"{config.YEAR}-01-01",
        })
    vendor_master_df = pd.DataFrame(vendor_master_rows)

    print("\n[7/7] Writing CSVs to data/06b/...")
    write_csv(gl_df, DATA_DIR / "gl_transactions_06b.csv")
    write_csv(vendor_master_df, DATA_DIR / "vendor_master_06b.csv")
    write_csv(coa_df, DATA_DIR / "chart_of_accounts_06b.csv")
    write_csv(calendar_df, DATA_DIR / "company_calendar_06b.csv")
    write_csv(pd.DataFrame(answer_key_rows), DATA_DIR / "answer_key_06b.csv")

    print(f"  gl_transactions_06b.csv:   {len(gl_df):,} rows")
    print(f"  vendor_master_06b.csv:     {len(vendor_master_df):,} rows")
    print(f"  chart_of_accounts_06b.csv: {len(coa_df):,} rows")
    print(f"  company_calendar_06b.csv:  {len(calendar_df):,} rows")
    print(f"  answer_key_06b.csv:        {len(answer_key_rows):,} rows")

    integ_share = (gl_df["posted_by"] == config.INTEGRATION_USER).mean()
    print(f"\n  INTEG-01 share of all rows: {integ_share:.1%}")

    print("\n" + "=" * 70)
    print("06b ledger generation complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
