"""
generate_ledger.py -- Builds the Saarnitukku Oy synthetic AP ledger.

Writes, into data/:
    gl_transactions.csv        (exactly 50,000 rows)
    vendor_master.csv          (200 rows)
    chart_of_accounts.csv      (~40 rows)
    company_calendar.csv       (365 rows)
    answer_key/anomalies.csv   (held out of every analysis path)

Every tunable lives in config.py. This script only implements the mechanics:
identity generation, per-vendor transaction streams, the planted classes and
benign items at their pinned parameters, and the by-construction exclusions
that keep accidental rule-test signatures out of the ordinary traffic
(coherence rule 9).

Determinism: a single seeded numpy Generator is spawned into named child
streams (one per generation concern) via SeedSequence.spawn, consumed in a
fixed order over a fixed vendor list. No wall-clock or OS randomness is used
anywhere. Run twice from a clean data/ directory; SHA-256 of all five output
files must match (checked separately, not by this script).

Run from the project root or from code/:
    python code/generate_ledger.py
"""

import calendar as pycalendar
import datetime as dt
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
ANSWER_KEY_DIR = DATA_DIR / "answer_key"

sys.path.insert(0, str(SCRIPT_DIR))
import config

# Guard: never write anywhere other than the explicitly specified data/
# output folder.
assert DATA_DIR != SCRIPT_DIR, "Output path must not equal the code/ input path"
assert DATA_DIR.name == "data"


# ---------------------------------------------------------------------------
# RNG setup -- one seeded SeedSequence spawned into named child streams.
# ---------------------------------------------------------------------------

def make_rngs() -> dict:
    root = np.random.SeedSequence(config.RANDOM_SEED)
    names = [
        "identity",         # vendor names/addresses/vat/iban/terms/country
        "vendor_params",    # pure-filler category + monthly-rate assignment
        "transactions",     # pure-filler per-transaction draws
        "story",            # story vendors (Teräskontio, Kuormaraitti, Karrenbach, Kaarniala, Neuvantila)
        "plants",           # D/R/S/B1-B5/W reserved-class generation
        "filler",           # the deterministic exact-count adjustment
        "invoice_offsets",  # per-vendor invoice-number starting offset (review fix 2)
        "order_refs",       # per-vendor memo order-ref starting offset (review, memo/invoice decoupling)
    ]
    children = root.spawn(len(names))
    return {name: np.random.default_rng(child) for name, child in zip(names, children)}


# ---------------------------------------------------------------------------
# Calendar and business-day arithmetic
# ---------------------------------------------------------------------------

def build_calendar() -> tuple:
    """Return (calendar_df, working_days set) for config.YEAR."""
    rows = []
    working_days = set()
    d = dt.date(config.YEAR, 1, 1)
    while d.year == config.YEAR:
        is_weekend = d.weekday() >= 5
        holiday_note = config.HOLIDAYS_2025.get(d)
        is_working = (not is_weekend) and (holiday_note is None)
        if holiday_note is not None:
            note = holiday_note
        elif is_weekend:
            note = "Weekend"
        else:
            note = ""
        rows.append({"date": d.isoformat(), "is_working_day": is_working, "note": note})
        if is_working:
            working_days.add(d)
        d += dt.timedelta(days=1)
    calendar_df = pd.DataFrame(rows, columns=["date", "is_working_day", "note"])
    return calendar_df, working_days


def add_business_days(start_date: dt.date, n: int, working_days: set) -> dt.date:
    """Move forward n business days from start_date (n=0 returns start_date
    unchanged). The company calendar only covers config.YEAR, so a start_date
    close enough to 31 Dec that n business days would spill into next year
    would otherwise search forever; the 30-calendar-day safety cap makes that
    case terminate (the caller checks posting_date.year and falls back to
    same-day integration-style posting -- the design's year-boundary
    simplification, never an actual output date)."""
    d = start_date
    remaining = n
    steps = 0
    while remaining > 0 and steps < 30:
        d += dt.timedelta(days=1)
        steps += 1
        if d in working_days:
            remaining -= 1
    return d


def business_days_between(a: dt.date, b: dt.date, working_days: set) -> int:
    """Count working days in the half-open interval (a, b]. Requires a <= b."""
    count = 0
    d = a
    while d < b:
        d += dt.timedelta(days=1)
        if d in working_days:
            count += 1
    return count


def find_invoice_date_for_target_posting(target_posting_date: dt.date, lag_target: int, working_days: set) -> dt.date:
    """
    Inverse of the lag relationship: find the invoice_date such that
    business_days_between(invoice_date, target_posting_date) == lag_target.
    Used for plants where the POSTING date is pinned (W, B2, B4, B5) and the
    invoice_date must be back-derived to respect the human posting-lag rule
    (validator rule 13) even though target_posting_date may itself be a
    non-working day (W's whole mechanism).
    """
    d = target_posting_date
    count = 0
    steps = 0
    while steps < 60:
        if d in working_days:
            count += 1
            if count == lag_target:
                return d - dt.timedelta(days=1)
        d -= dt.timedelta(days=1)
        steps += 1
    raise ValueError(f"Could not find an invoice_date {lag_target} business days before {target_posting_date}")


def choose_posted_by_and_posting_date(rng: np.random.Generator, invoice_date: dt.date, working_days: set) -> tuple:
    """
    Decide poster and posting_date for an ordinary (non-plant) transaction.
    INTEG-01 lag is 0-1 calendar days (integration batches
    land on any calendar day); human lag is 2-5 business days, always
    landing on a working day by construction. If an invoice dated very late
    in December would need a human lag that spills into next year, this
    falls back to same-day integration-style posting rather than violate the
    stated year-boundary simplification -- a rare edge
    case (only the last handful of December calendar days).
    """
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


def nearest_working_day(d: dt.date, working_days: set) -> dt.date:
    """Roll forward to the nearest working day (used for 'mid-month working day' plants)."""
    while d not in working_days:
        d += dt.timedelta(days=1)
    return d


def days_in_month(month: int) -> int:
    return pycalendar.monthrange(config.YEAR, month)[1]


# Target share of ORGANIC invoice dates landing on a working day (review
# fix 3: a uniform draw across all seven weekdays was unrealistic --
# an invoice a vendor issues is far more likely to be dated on a working day
# than a weekend or holiday).
INVOICE_DATE_WORKING_DAY_SHARE = 0.90


def weighted_invoice_day(rng: np.random.Generator, month: int, working_days: set) -> int:
    """
    Draw a day-of-month for an ORGANIC invoice_date, weighted so that
    (in expectation, independently for every month) INVOICE_DATE_WORKING_DAY_SHARE
    of draws land on a working day and the remainder on a weekend or holiday.
    Used for pure-filler vendors and the Karrenbach trio (organic, unplanted
    traffic); planted classes (D/R/S/W/B1-B5/G/A) keep their pinned dates.
    """
    n_days = days_in_month(month)
    is_working = [dt.date(config.YEAR, month, d) in working_days for d in range(1, n_days + 1)]
    n_working = sum(is_working)
    n_nonworking = n_days - n_working

    working_weight = INVOICE_DATE_WORKING_DAY_SHARE / n_working if n_working > 0 else 0.0
    nonworking_weight = (1.0 - INVOICE_DATE_WORKING_DAY_SHARE) / n_nonworking if n_nonworking > 0 else 0.0
    weights = np.array([working_weight if w else nonworking_weight for w in is_working])
    weights = weights / weights.sum()

    day = int(rng.choice(np.arange(1, n_days + 1), p=weights))
    return day


# ---------------------------------------------------------------------------
# Amount helpers -- lognormal draws with the rule-9 exclusion bands enforced
# by construction (round-sum multiples >= EUR2,000 and the near-threshold
# band EUR9,500-9,999.99 are perturbed away unless the caller is generating
# a designed plant, which never calls these helpers on its pinned amounts).
# ---------------------------------------------------------------------------

def lognormal_mu_sigma(mean: float, cv: float) -> tuple:
    sigma2 = math.log(1.0 + cv ** 2)
    sigma = math.sqrt(sigma2)
    mu = math.log(mean) - 0.5 * sigma2
    return mu, sigma


def draw_amount(rng: np.random.Generator, mean: float, cv: float) -> float:
    mu, sigma = lognormal_mu_sigma(mean, cv)
    return float(rng.lognormal(mu, sigma))


def is_round_multiple(amount: float) -> bool:
    if amount < config.RULE_ROUND_SUM_MIN_EUR:
        return False
    cents = round(amount * 100)
    step_cents = int(round(config.RULE_ROUND_SUM_MULTIPLE * 100))
    return cents % step_cents == 0


def is_near_threshold(amount: float) -> bool:
    return config.RULE_NEAR_THRESHOLD_LOW <= amount < config.RULE_NEAR_THRESHOLD_HIGH


def perturb_amount(amount: float, rng: np.random.Generator) -> float:
    """Nudge an amount away from the round-sum and near-threshold exclusion
    bands (coherence rule 9). Called on every non-planted amount."""
    amount = round(amount, 2)
    guard = 0
    while (is_round_multiple(amount) or is_near_threshold(amount)) and guard < 25:
        if is_near_threshold(amount):
            amount = amount - float(rng.uniform(5.0, 90.0))
        if is_round_multiple(amount):
            amount = amount + float(rng.uniform(0.10, 6.0))
        amount = round(amount, 2)
        guard += 1
    return max(amount, 1.00)


def fix_duplicate_and_split_collisions(raw_txns: list, rng: np.random.Generator) -> list:
    """
    raw_txns: list of [invoice_date, amount] pairs, SORTED by invoice_date.
    Removes accidental duplicate-amount pairs within RULE_DUPLICATE_MAX_GAP_DAYS
    and accidental split-shaped pairs within RULE_SPLIT_MAX_WINDOW_DAYS
    (coherence rule 9's constructive exclusions). Only ever called on
    vendors that carry no designed D/R/S plant, so any fix here is safe.
    """
    n = len(raw_txns)
    if n < 2:
        return raw_txns

    changed = True
    guard = 0
    while changed and guard < 8:
        changed = False
        guard += 1
        for i in range(n):
            date_i, _ = raw_txns[i]
            for j in range(i + 1, n):
                date_j, _ = raw_txns[j]
                gap = (date_j - date_i).days
                if gap > config.RULE_DUPLICATE_MAX_GAP_DAYS:
                    break  # sorted by date -- no further j can be closer
                amt_i, amt_j = raw_txns[i][1], raw_txns[j][1]
                if round(amt_i, 2) == round(amt_j, 2):
                    raw_txns[j][1] = perturb_amount(amt_j + float(rng.uniform(0.50, 12.0)), rng)
                    changed = True
                if gap <= config.RULE_SPLIT_MAX_WINDOW_DAYS:
                    a, b = raw_txns[i][1], raw_txns[j][1]
                    parts_in_band = (
                        config.RULE_SPLIT_MIN_PART_EUR <= a < config.RULE_SPLIT_MAX_PART_EUR
                        and config.RULE_SPLIT_MIN_PART_EUR <= b < config.RULE_SPLIT_MAX_PART_EUR
                    )
                    if parts_in_band and (a + b) >= config.RULE_SPLIT_MIN_SUM_EUR:
                        # Redraw the smaller amount from well below the
                        # EUR4,000 part-minimum -- scaling down proportionally
                        # is not safe here: for amounts already close to the
                        # EUR10,000 ceiling, even a 0.55x cut can still land
                        # back inside the [4000, 10000) band.
                        replacement = perturb_amount(float(rng.uniform(400.0, 3600.0)), rng)
                        if a <= b:
                            raw_txns[i][1] = replacement
                        else:
                            raw_txns[j][1] = replacement
                        changed = True
    return raw_txns


# ---------------------------------------------------------------------------
# Generic vendor identity generation (names, address, VAT id, IBAN, terms)
# ---------------------------------------------------------------------------

IBAN_LENGTH_BY_COUNTRY = {"FI": 18, "DE": 22, "SE": 24, "NO": 15, "EE": 20}


def make_vat_id(rng: np.random.Generator, country: str) -> str:
    def digits(n):
        return "".join(str(int(rng.integers(0, 10))) for _ in range(n))

    if country == "FI":
        return f"FI{digits(8)}"
    if country == "DE":
        return f"DE{digits(9)}"
    if country == "SE":
        return f"SE{digits(10)}01"
    if country == "NO":
        return f"NO{digits(9)}MVA"
    if country == "EE":
        return f"EE{digits(9)}"
    raise ValueError(f"Unknown country {country}")


def iban_check_digits(country: str, bban: str) -> str:
    """ISO 13616 mod-97 check digits for a country code and BBAN."""
    digits = "".join(str(int(c, 36)) for c in bban + country + "00")
    return f"{98 - int(digits) % 97:02d}"


def make_iban(rng: np.random.Generator, country: str, used_ibans: set) -> str:
    """Draw a unique IBAN, then give it an invented bank code.

    The random draw is unchanged (same number of draws, same uniqueness test
    on the drawn value), so every later draw in the stream is unaffected.
    After the draw, the start of the BBAN is overwritten with the country's
    FICTIONAL_BANK_PREFIX and the check digits are recomputed, so the IBAN
    passes the mod-97 check but names no real bank."""
    length = IBAN_LENGTH_BY_COUNTRY[country]
    remaining = length - 4  # after 2-letter country code + 2-digit check
    while True:
        check = f"{int(rng.integers(0, 100)):02d}"
        body = "".join(str(int(rng.integers(0, 10))) for _ in range(remaining))
        iban = f"{country}{check}{body}"
        if iban not in used_ibans:
            used_ibans.add(iban)
            prefix = config.FICTIONAL_BANK_PREFIX[country]
            bban = prefix + body[len(prefix):]
            return f"{country}{iban_check_digits(country, bban)}{bban}"


def make_address(rng: np.random.Generator, country: str) -> str:
    if country == "FI":
        street = str(rng.choice(config.ADDRESS_STREETS_FI))
        number = int(rng.integers(1, 60))
        city = str(rng.choice(config.ADDRESS_CITIES_FI))
        postal = int(rng.integers(1000, 99999))
        return f"{street} {number}, {postal:05d} {city}"
    street = str(rng.choice(config.ADDRESS_STREETS_INTL[country]))
    number = int(rng.integers(1, 60))
    city = str(rng.choice(config.ADDRESS_CITIES_INTL[country]))
    postal = int(rng.integers(10000, 99999))
    return f"{street} {number}, {postal} {city}"


def build_generic_name_pools(rng: np.random.Generator) -> dict:
    """Pre-shuffle a large candidate name list per country so names can be
    drawn without replacement in a fixed, deterministic order."""
    pools = {}

    fi_candidates = [
        f"{p}{m} {s}"
        for p in config.GENERIC_NAME_PREFIXES
        for m in config.GENERIC_NAME_MID
        for s in config.GENERIC_NAME_SUFFIXES_FI
    ]
    order = rng.permutation(len(fi_candidates))
    pools["FI"] = {"candidates": fi_candidates, "order": order.tolist(), "next": 0}

    for country in ["SE", "DE", "NO", "EE"]:
        prefixes = config.GENERIC_NAME_PREFIXES_INTL[country]
        mids = config.GENERIC_NAME_MID_INTL[country]
        candidates = [f"{p}{m}" for p in prefixes for m in mids]
        order = rng.permutation(len(candidates))
        pools[country] = {"candidates": candidates, "order": order.tolist(), "next": 0}

    return pools


def draw_unique_name(rng: np.random.Generator, pools: dict, country: str, used_names: set) -> str:
    pool = pools[country]
    while True:
        if pool["next"] >= len(pool["order"]):
            # Exhausted the pre-shuffled pool (should not happen at our scale) --
            # extend deterministically with a numbered suffix.
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


def generate_generic_identities(rng: np.random.Generator, vendor_ids: list) -> dict:
    """Build vendor_id -> identity dict for every generic-scheme vendor
    (V-0008..V-0200): vendor_name, country, vat_id, iban, address, terms_days.
    Reserved vendor_ids (D/R/S/B1-B5) are forced to country FI so their
    identity fields stay internally consistent with the FI-flavoured names
    pinned in config for B1-B5."""
    countries = list(config.COUNTRY_WEIGHTS.keys())
    probs = list(config.COUNTRY_WEIGHTS.values())
    pools = build_generic_name_pools(rng)
    used_names = set()
    used_ibans = set()
    identities = {}

    for vid in vendor_ids:
        if vid in config.RESERVED_VENDOR_IDS:
            country = "FI"
        else:
            country = str(rng.choice(countries, p=probs))
        name = draw_unique_name(rng, pools, country, used_names)
        if vid in config.RESERVED_VENDOR_NAME_OVERRIDES:
            name = config.RESERVED_VENDOR_NAME_OVERRIDES[vid]
        else:
            # Published-name policy (6 Oct 2026): coined stems on international names, pinned
            # Finnish names. Applied after the draw so no random draw changes.
            name = config.apply_generic_name_policy(name, country)
        # Per-vendor pins (config), applied after every draw for this vendor
        name = config.GENERIC_NAME_PINS_BY_VENDOR_ID.get(vid, name)
        vat_id = make_vat_id(rng, country)
        vat_id = config.VAT_ID_PINS_BY_VENDOR_ID.get(vid, vat_id)
        iban = make_iban(rng, country, used_ibans)
        address = make_address(rng, country)
        terms_days = int(rng.choice(config.TERMS_DAYS_OPTIONS, p=config.TERMS_DAYS_WEIGHTS))
        identities[vid] = {
            "vendor_id": vid,
            "vendor_name": name,
            "country": country,
            "vat_id": vat_id,
            "iban": iban,
            "address": address,
            "terms_days": terms_days,
        }
    return identities


def assign_pure_filler_behavior(rng: np.random.Generator) -> tuple:
    """Draw (category, allowed_accounts) for one pure-filler vendor."""
    categories = list(config.GENERIC_VENDOR_CATEGORIES.keys())
    weights = [config.GENERIC_VENDOR_CATEGORIES[c]["weight"] for c in categories]
    category = str(rng.choice(categories, p=weights))
    pool = config.GENERIC_VENDOR_CATEGORIES[category]["accounts"]
    primary = str(rng.choice(pool))
    accounts = [primary]
    if rng.random() < config.SECOND_ACCOUNT_PROBABILITY:
        remaining = [a for a in pool if a != primary]
        if remaining:
            accounts.append(str(rng.choice(remaining)))
    return category, accounts


# ---------------------------------------------------------------------------
# Generic (pure-filler) vendor transaction generation
# ---------------------------------------------------------------------------

def generate_filler_stream(rng: np.random.Generator, vendor: dict, working_days: set, n_override: int = None) -> list:
    """
    Generate one vendor's year of ordinary transactions.
    vendor: dict with vendor_id, vendor_name, category, allowed_accounts, terms_days.
    n_override: if given, generate exactly this many transactions total
    (used by the filler-adjustment pass), spread across months by the same
    seasonality weights rather than by the vendor's own drawn base rate.
    """
    cat = config.GENERIC_VENDOR_CATEGORIES[vendor["category"]]

    raw = []
    if n_override is None:
        shape = cat["monthly_rate_gamma_shape"]
        scale = cat["monthly_rate_mean"] / shape
        base_rate = min(float(rng.gamma(shape, scale)), config.MONTHLY_RATE_CLIP_MAX)
        for month in range(1, 13):
            lam = base_rate * config.MONTH_SEASONALITY_WEIGHT[month]
            n_month = int(rng.poisson(lam))
            for _ in range(n_month):
                day = weighted_invoice_day(rng, month, working_days)
                raw.append([dt.date(config.YEAR, month, day), None])
    else:
        weights = np.array([config.MONTH_SEASONALITY_WEIGHT[m] for m in range(1, 13)], dtype=float)
        weights = weights / weights.sum()
        month_counts = rng.multinomial(n_override, weights)
        for month, n_month in zip(range(1, 13), month_counts):
            for _ in range(int(n_month)):
                day = weighted_invoice_day(rng, month, working_days)
                raw.append([dt.date(config.YEAR, month, day), None])

    # Decide account, poster and posting_date BEFORE the collision fix --
    # the duplicate and split rule tests window on posting_date, not invoice_date, and posting lag can move a transaction
    # several calendar days from its invoice_date. Fixing collisions on
    # invoice_date proximity would neither catch nor reliably reproduce what
    # the rule tests actually see.
    accounts = vendor["allowed_accounts"]
    transactions = []
    for invoice_date, _ in raw:
        if len(accounts) > 1 and rng.random() < config.SECOND_ACCOUNT_PROBABILITY:
            account = accounts[1]
        else:
            account = accounts[0]
        amount = draw_amount(rng, cat["amount_mean"], cat["amount_cv"])
        amount = perturb_amount(amount, rng)
        posted_by, posting_date = choose_posted_by_and_posting_date(rng, invoice_date, working_days)
        due_date = invoice_date + dt.timedelta(days=vendor["terms_days"])
        transactions.append({
            "vendor_id": vendor["vendor_id"],
            "vendor_name": vendor["vendor_name"],
            "invoice_date": invoice_date,
            "posting_date": posting_date,
            "due_date": due_date,
            "account": account,
            "amount_eur": round(amount, 2),
            "posted_by": posted_by,
            "memo_category": vendor["category"],
            "_plant_tag": "",
        })

    transactions.sort(key=lambda t: t["posting_date"])
    pairs = [[t["posting_date"], t["amount_eur"]] for t in transactions]
    pairs = fix_duplicate_and_split_collisions(pairs, rng)
    for t, (_, amount_fixed) in zip(transactions, pairs):
        t["amount_eur"] = round(amount_fixed, 2)

    return transactions


# ---------------------------------------------------------------------------
# Story vendors
# ---------------------------------------------------------------------------

def generate_teraskontio(rng: np.random.Generator) -> tuple:
    """Returns (transactions, step_eur)."""
    txns = []
    step_eur = config.TERASKONTIO_BASELINE_MEAN_EUR * config.TERASKONTIO_STEP_FRACTION
    for month in range(1, 13):
        for day in config.TERASKONTIO_INVOICE_DAYS:
            invoice_date = dt.date(config.YEAR, month, day)
            if month <= 6:
                mean = config.TERASKONTIO_BASELINE_MEAN_EUR
                memo_template = config.MEMO_TERASKONTIO_H1
                plant_tag = "G_H1"
            else:
                k = month - 7
                mean = (
                    config.TERASKONTIO_BASELINE_MEAN_EUR
                    * (1 + config.TERASKONTIO_STEP_FRACTION)
                    * ((1 + config.TERASKONTIO_MONTHLY_COMPOUND_FRACTION) ** k)
                )
                memo_template = config.MEMO_TERASKONTIO_H2
                plant_tag = "G"
            noise = float(rng.normal(0.0, config.TERASKONTIO_BASELINE_SIGMA_FRAC))
            amount = round(mean * (1 + noise), 2)
            lag_days = int(rng.choice(config.INTEGRATION_LAG_CALENDAR_DAYS))
            posting_date = invoice_date + dt.timedelta(days=lag_days)
            due_date = invoice_date + dt.timedelta(days=config.TERASKONTIO_TERMS_DAYS)
            txns.append({
                "vendor_id": config.TERASKONTIO_VENDOR_ID,
                "vendor_name": config.TERASKONTIO_NAME,
                "invoice_date": invoice_date,
                "posting_date": posting_date,
                "due_date": due_date,
                "account": config.ACCOUNT_TERASKONTIO,
                "amount_eur": amount,
                "posted_by": config.INTEGRATION_USER,
                "memo_template": memo_template,
                "_plant_tag": plant_tag,
            })
    return txns, step_eur


def generate_kuormaraitti(rng: np.random.Generator, step_eur: float) -> list:
    txns = []
    for month in range(1, 13):
        for day in config.KUORMARAITTI_INVOICE_DAYS:
            invoice_date = dt.date(config.YEAR, month, day)
            if month <= 6:
                mean = config.KUORMARAITTI_BASELINE_MEAN_EUR
                plant_tag = "KUORMARAITTI_H1"
            else:
                mean = config.KUORMARAITTI_BASELINE_MEAN_EUR - step_eur
                plant_tag = "KUORMARAITTI_H2"
            noise = float(rng.normal(0.0, config.KUORMARAITTI_SIGMA_FRAC))
            amount = round(max(mean * (1 + noise), 50.0), 2)
            lag_days = int(rng.choice(config.INTEGRATION_LAG_CALENDAR_DAYS))
            posting_date = invoice_date + dt.timedelta(days=lag_days)
            due_date = invoice_date + dt.timedelta(days=config.KUORMARAITTI_TERMS_DAYS)
            txns.append({
                "vendor_id": config.KUORMARAITTI_VENDOR_ID,
                "vendor_name": config.KUORMARAITTI_NAME,
                "invoice_date": invoice_date,
                "posting_date": posting_date,
                "due_date": due_date,
                "account": config.ACCOUNT_KUORMARAITTI,
                "amount_eur": amount,
                "posted_by": config.INTEGRATION_USER,
                "memo_template": config.MEMO_KUORMARAITTI,
                "_plant_tag": plant_tag,
            })
    return txns


def generate_karrenbach(rng: np.random.Generator, working_days: set) -> list:
    raw_by_record = []
    for rec in config.KARRENBACH_RECORDS:
        months = sorted(rng.choice(np.arange(1, 13), size=rec["n_invoices"], replace=False).tolist())
        for month in months:
            day = weighted_invoice_day(rng, month, working_days)
            invoice_date = dt.date(config.YEAR, month, day)
            amount = draw_amount(rng, config.KARRENBACH_AMOUNT_MEAN_EUR, config.KARRENBACH_AMOUNT_CV)
            amount = perturb_amount(amount, rng)
            posted_by, posting_date = choose_posted_by_and_posting_date(rng, invoice_date, working_days)
            raw_by_record.append({
                "invoice_date": invoice_date, "posting_date": posting_date, "amount_eur": amount,
                "posted_by": posted_by, "vendor_id": rec["vendor_id"], "vendor_name": rec["name"],
            })

    # Collision-fix per vendor record, keyed on posting_date (each record is
    # its own vendor_id, so duplicate/split checks are scoped per record,
    # matching the rule tests, which window on posting_date).
    by_vendor = {}
    for item in raw_by_record:
        by_vendor.setdefault(item["vendor_id"], []).append(item)
    fixed_items = []
    for vid, items in by_vendor.items():
        items.sort(key=lambda t: t["posting_date"])
        pairs = [[t["posting_date"], t["amount_eur"]] for t in items]
        pairs = fix_duplicate_and_split_collisions(pairs, rng)
        for t, (_, amount_fixed) in zip(items, pairs):
            t["amount_eur"] = amount_fixed
        fixed_items.extend(items)

    txns = []
    for item in fixed_items:
        due_date = item["invoice_date"] + dt.timedelta(days=config.KARRENBACH_TERMS_DAYS)
        txns.append({
            "vendor_id": item["vendor_id"],
            "vendor_name": item["vendor_name"],
            "invoice_date": item["invoice_date"],
            "posting_date": item["posting_date"],
            "due_date": due_date,
            "account": config.ACCOUNT_KARRENBACH,
            "amount_eur": round(item["amount_eur"], 2),
            "posted_by": item["posted_by"],
            "memo_template": config.MEMO_KARRENBACH,
            "_plant_tag": "V",
        })
    return txns


def generate_kaarniala(rng: np.random.Generator, working_days: set) -> list:
    txns = []
    day_map = {9: config.KAARNIALA_DAYS_SEP, 10: config.KAARNIALA_DAYS_OCT}
    for month in config.KAARNIALA_MONTHS:
        for day in day_map[month]:
            invoice_date = dt.date(config.YEAR, month, day)
            amount = perturb_amount(
                float(rng.uniform(config.KAARNIALA_AMOUNT_MIN_EUR, config.KAARNIALA_AMOUNT_MAX_EUR)), rng
            )
            lag = int(rng.choice(config.HUMAN_LAG_BUSINESS_DAYS))
            posting_date = add_business_days(invoice_date, lag, working_days)
            due_date = invoice_date + dt.timedelta(days=config.KAARNIALA_TERMS_DAYS)
            txns.append({
                "vendor_id": config.KAARNIALA_VENDOR_ID,
                "vendor_name": config.KAARNIALA_NAME,
                "invoice_date": invoice_date,
                "posting_date": posting_date,
                "due_date": due_date,
                "account": config.ACCOUNT_KAARNIALA_MISPOST,
                "amount_eur": round(amount, 2),
                "posted_by": config.KAARNIALA_POSTED_BY,
                "memo_template": config.MEMO_KAARNIALA,
                "_plant_tag": "A",
            })
    return txns


def generate_neuvantila(rng: np.random.Generator, working_days: set) -> list:
    txns = []
    for month in range(1, 13):
        target_day = min(config.NEUVANTILA_DAY_OF_MONTH, days_in_month(month))
        invoice_date = nearest_working_day(dt.date(config.YEAR, month, target_day), working_days)
        amount = float(rng.uniform(config.NEUVANTILA_AMOUNT_MIN_EUR, config.NEUVANTILA_AMOUNT_MAX_EUR))
        amount = perturb_amount(amount, rng)
        lag = int(rng.choice(config.HUMAN_LAG_BUSINESS_DAYS))
        posted_by = str(rng.choice(config.HUMAN_USERS))
        posting_date = add_business_days(invoice_date, lag, working_days)
        due_date = invoice_date + dt.timedelta(days=config.NEUVANTILA_TERMS_DAYS)
        txns.append({
            "vendor_id": config.NEUVANTILA_VENDOR_ID,
            "vendor_name": config.NEUVANTILA_NAME,
            "invoice_date": invoice_date,
            "posting_date": posting_date,
            "due_date": due_date,
            "account": config.ACCOUNT_NEUVANTILA,
            "amount_eur": round(amount, 2),
            "posted_by": posted_by,
            "memo_template": config.MEMO_NEUVANTILA,
            "_plant_tag": "C",
        })
    return txns


# ---------------------------------------------------------------------------
# Reserved plant classes: D, R, S, B1, B2, B3, B4, B5
# ---------------------------------------------------------------------------

def generate_D(identities: dict) -> list:
    """Each of the 6 duplicate-invoice pairs gets its own event-level plant
    tag ('D-01'..'D-06') so the answer key can carry one row per event
    (review, event-grain answer key)."""
    txns = []
    for v_ix, vendor_id in enumerate(config.D_VENDOR_IDS):
        identity = identities[vendor_id]
        # Each vendor carries 2 of the 6 pairs (round-robin assignment).
        my_pairs = [i for i in range(6) if i % 3 == v_ix]
        for local_pair_num, pair_i in enumerate(my_pairs):
            month = config.D_PAIR_MONTHS[pair_i]
            gap = config.D_PAIR_GAP_DAYS[pair_i]
            base_amount = config.D_PAIR_BASE_AMOUNTS_EUR[pair_i]
            day1 = 5 + local_pair_num * 3  # keeps the two pairs within one vendor well apart
            invoice_date_1 = dt.date(config.YEAR, month, day1)
            invoice_date_2 = invoice_date_1 + dt.timedelta(days=gap)
            event_tag = f"D-{pair_i + 1:02d}"
            for k, invoice_date in enumerate([invoice_date_1, invoice_date_2]):
                due_date = invoice_date + dt.timedelta(days=identity["terms_days"])
                txns.append({
                    "vendor_id": vendor_id,
                    "vendor_name": identity["vendor_name"],
                    "invoice_date": invoice_date,
                    "posting_date": invoice_date,  # INTEG-01, lag 0 -- keeps the posting gap exact
                    "due_date": due_date,
                    "account": config.RESERVED_VENDOR_ACCOUNTS[vendor_id][0],
                    "amount_eur": round(base_amount, 2),
                    "posted_by": config.INTEGRATION_USER,
                    "memo_template": config.MEMO_D_GENERIC,
                    "_plant_tag": event_tag,
                })
    return txns


def generate_R(identities: dict) -> list:
    txns = []
    round_identity = identities[config.R_ROUND_VENDOR_ID]
    for month, amount in zip(config.R_ROUND_MONTHS, config.R_ROUND_AMOUNTS_EUR):
        invoice_date = dt.date(config.YEAR, month, 12)
        due_date = invoice_date + dt.timedelta(days=round_identity["terms_days"])
        txns.append({
            "vendor_id": config.R_ROUND_VENDOR_ID,
            "vendor_name": round_identity["vendor_name"],
            "invoice_date": invoice_date,
            "posting_date": invoice_date,
            "due_date": due_date,
            "account": config.RESERVED_VENDOR_ACCOUNTS[config.R_ROUND_VENDOR_ID][0],
            "amount_eur": round(amount, 2),
            "posted_by": config.INTEGRATION_USER,
            "memo_template": config.MEMO_R_GENERIC,
            "_plant_tag": "R-ROUND",
        })
    near_identity = identities[config.R_NEAR_VENDOR_ID]
    for month, amount in zip(config.R_NEAR_THRESHOLD_MONTHS, config.R_NEAR_THRESHOLD_AMOUNTS_EUR):
        invoice_date = dt.date(config.YEAR, month, 18)
        due_date = invoice_date + dt.timedelta(days=near_identity["terms_days"])
        txns.append({
            "vendor_id": config.R_NEAR_VENDOR_ID,
            "vendor_name": near_identity["vendor_name"],
            "invoice_date": invoice_date,
            "posting_date": invoice_date,
            "due_date": due_date,
            "account": config.RESERVED_VENDOR_ACCOUNTS[config.R_NEAR_VENDOR_ID][0],
            "amount_eur": round(amount, 2),
            "posted_by": config.INTEGRATION_USER,
            "memo_template": config.MEMO_R_GENERIC,
            "_plant_tag": "R-NEAR",
        })
    return txns


def generate_S(identities: dict) -> list:
    """Each of the 5 split-purchase events gets its own event-level plant
    tag ('S-01'..'S-05') -- event-grain answer key (review)."""
    txns = []
    for event_ix, event in enumerate(config.S_EVENTS):
        vendor_id = config.S_VENDOR_IDS[event["vendor_ix"]]
        identity = identities[vendor_id]
        invoice_date_a = dt.date(config.YEAR, event["month"], 10)
        invoice_date_b = invoice_date_a + dt.timedelta(days=event["offset_days"])
        event_tag = f"S-{event_ix + 1:02d}"
        for invoice_date, amount in [(invoice_date_a, event["part_a_eur"]), (invoice_date_b, event["part_b_eur"])]:
            due_date = invoice_date + dt.timedelta(days=identity["terms_days"])
            txns.append({
                "vendor_id": vendor_id,
                "vendor_name": identity["vendor_name"],
                "invoice_date": invoice_date,
                "posting_date": invoice_date,  # INTEG-01, lag 0 -- keeps the posting gap exact
                "due_date": due_date,
                "account": config.RESERVED_VENDOR_ACCOUNTS[vendor_id][0],
                "amount_eur": round(amount, 2),
                "posted_by": config.INTEGRATION_USER,
                "memo_template": config.MEMO_S_GENERIC,
                "_plant_tag": event_tag,
            })
    return txns


def generate_B1(identities: dict) -> list:
    identity = identities[config.B1_VENDOR_ID]
    txns = []
    for month in range(1, 13):
        invoice_date = dt.date(config.YEAR, month, 1)
        due_date = invoice_date + dt.timedelta(days=identity["terms_days"])
        txns.append({
            "vendor_id": config.B1_VENDOR_ID,
            "vendor_name": identity["vendor_name"],
            "invoice_date": invoice_date,
            "posting_date": invoice_date,
            "due_date": due_date,
            "account": config.ACCOUNT_B1_RENT,
            "amount_eur": round(config.B1_MONTHLY_RENT_EUR, 2),
            "posted_by": config.INTEGRATION_USER,
            "memo_template": config.MEMO_B1_RENT,
            "_plant_tag": "B1",
        })
    return txns


def generate_B2(identities: dict, working_days: set) -> list:
    identity = identities[config.B2_VENDOR_ID]
    txns = []
    for k, amount in enumerate(config.B2_AMOUNTS_EUR):
        lag = 3 + k  # 3, then 4 business days -- both within the human 2-5 range
        invoice_date = find_invoice_date_for_target_posting(config.B2_DATE, lag, working_days)
        due_date = invoice_date + dt.timedelta(days=identity["terms_days"])
        txns.append({
            "vendor_id": config.B2_VENDOR_ID,
            "vendor_name": identity["vendor_name"],
            "invoice_date": invoice_date,
            "posting_date": config.B2_DATE,
            "due_date": due_date,
            "account": config.ACCOUNT_B2_INVENTORY,
            "amount_eur": round(amount, 2),
            "posted_by": config.B2_POSTED_BY,
            "memo": config.B2_MEMO,  # verbatim breadcrumb, no template substitution
            "_plant_tag": "B2",
        })
    return txns


def generate_B3(identities: dict) -> list:
    identity = identities[config.B3_VENDOR_ID]
    txns = []
    invoice_date_1 = dt.date(config.YEAR, config.B3_MONTH, 10)
    invoice_date_2 = invoice_date_1 + dt.timedelta(days=config.B3_GAP_DAYS)
    for invoice_date, po_ref in zip([invoice_date_1, invoice_date_2], config.B3_PO_REFS):
        due_date = invoice_date + dt.timedelta(days=identity["terms_days"])
        txns.append({
            "vendor_id": config.B3_VENDOR_ID,
            "vendor_name": identity["vendor_name"],
            "invoice_date": invoice_date,
            "posting_date": invoice_date,
            "due_date": due_date,
            "account": config.RESERVED_VENDOR_ACCOUNTS[config.B3_VENDOR_ID][0],
            "amount_eur": round(config.B3_AMOUNT_EUR, 2),
            "posted_by": config.INTEGRATION_USER,
            "memo": config.MEMO_B3_GENERIC.format(po_ref=po_ref),
            "_plant_tag": "B3",
        })
    return txns


def generate_B4(identities: dict, working_days: set) -> list:
    identity = identities[config.B4_VENDOR_ID]
    posting_date = nearest_working_day(dt.date(config.YEAR, config.B4_MONTH, config.B4_DAY_OF_MONTH), working_days)
    invoice_date = find_invoice_date_for_target_posting(posting_date, 3, working_days)
    due_date = invoice_date + dt.timedelta(days=identity["terms_days"])
    return [{
        "vendor_id": config.B4_VENDOR_ID,
        "vendor_name": identity["vendor_name"],
        "invoice_date": invoice_date,
        "posting_date": posting_date,
        "due_date": due_date,
        "account": config.ACCOUNT_B4_CAPEX,
        "amount_eur": round(config.B4_AMOUNT_EUR, 2),
        "posted_by": config.B4_POSTED_BY,
        "memo": config.MEMO_B4_CAPEX,
        "_plant_tag": "B4",
    }]


def generate_B5(identities: dict, working_days: set) -> list:
    identity = identities[config.B5_VENDOR_ID]
    posting_date = nearest_working_day(dt.date(config.YEAR, config.B5_MONTH, config.B5_DAY_OF_MONTH), working_days)
    invoice_date = find_invoice_date_for_target_posting(posting_date, 3, working_days)
    due_date = invoice_date + dt.timedelta(days=identity["terms_days"])
    return [{
        "vendor_id": config.B5_VENDOR_ID,
        "vendor_name": identity["vendor_name"],
        "invoice_date": invoice_date,
        "posting_date": posting_date,
        "due_date": due_date,
        "account": config.ACCOUNT_B5_INSURANCE,
        "amount_eur": round(config.B5_AMOUNT_EUR, 2),
        "posted_by": config.B5_POSTED_BY,
        "memo": config.MEMO_B5_INSURANCE,
        "_plant_tag": "B5",
    }]


def rescrub_amounts(transactions: list, rng: np.random.Generator) -> list:
    """
    Re-run the duplicate/split collision fix across a vendor's FULL
    transaction list. Needed after combining two independently-generated
    batches for the same vendor (organic generation + the filler-adjustment
    top-up) -- fix_duplicate_and_split_collisions only ever sees one batch
    at a time otherwise, so a collision straddling the two batches would
    slip through. W-tagged rows are pinned plants and are excluded.
    """
    non_plant = [t for t in transactions if t["_plant_tag"] == ""]
    plant = [t for t in transactions if t["_plant_tag"] != ""]
    non_plant.sort(key=lambda t: t["posting_date"])
    pairs = [[t["posting_date"], t["amount_eur"]] for t in non_plant]
    pairs = fix_duplicate_and_split_collisions(pairs, rng)
    for t, (_, amount_fixed) in zip(non_plant, pairs):
        t["amount_eur"] = round(amount_fixed, 2)
    return non_plant + plant


def fix_point_against_existing(target_date: dt.date, amount: float, existing: list, rng: np.random.Generator) -> float:
    """
    Adjust a single new (date, amount) point so it does not accidentally
    trip the duplicate or split test against any existing same-vendor
    transaction (used for the one-off W insertions, which are appended
    after the vendor's own stream has already been internally collision-fixed).
    """
    guard = 0
    while guard < 10:
        violation = False
        for date_e, amount_e in existing:
            gap = abs((target_date - date_e).days)
            if gap <= config.RULE_DUPLICATE_MAX_GAP_DAYS and round(amount, 2) == round(amount_e, 2):
                violation = True
                break
            if gap <= config.RULE_SPLIT_MAX_WINDOW_DAYS:
                a, b = amount, amount_e
                parts_in_band = (
                    config.RULE_SPLIT_MIN_PART_EUR <= a < config.RULE_SPLIT_MAX_PART_EUR
                    and config.RULE_SPLIT_MIN_PART_EUR <= b < config.RULE_SPLIT_MAX_PART_EUR
                )
                if parts_in_band and (a + b) >= config.RULE_SPLIT_MIN_SUM_EUR:
                    violation = True
                    break
        if not violation:
            return amount
        amount = perturb_amount(float(rng.uniform(400.0, 3600.0)), rng)
        guard += 1
    return amount


def inject_W(rng: np.random.Generator, filler_by_vendor: dict, vendor_lookup: dict, working_days: set) -> list:
    """Append one plant transaction each to 8 distinct, sufficiently active
    pure-filler vendors, posted by U-117 on the 8 designed non-working dates."""
    eligible = sorted(vid for vid, txns in filler_by_vendor.items() if len(txns) >= 20)
    chosen_positions = rng.choice(len(eligible), size=len(config.W_DATES), replace=False)
    chosen_vendor_ids = [eligible[i] for i in chosen_positions]

    w_txns = []
    for target_date, vendor_id in zip(config.W_DATES, chosen_vendor_ids):
        vendor = vendor_lookup[vendor_id]
        invoice_date = find_invoice_date_for_target_posting(target_date, config.W_LAG_BUSINESS_DAYS, working_days)
        cat = config.GENERIC_VENDOR_CATEGORIES[vendor["category"]]
        amount = perturb_amount(draw_amount(rng, cat["amount_mean"], cat["amount_cv"]), rng)
        existing = [(t["posting_date"], t["amount_eur"]) for t in filler_by_vendor[vendor_id]]
        amount = fix_point_against_existing(target_date, amount, existing, rng)
        account = vendor["allowed_accounts"][0]
        due_date = invoice_date + dt.timedelta(days=vendor["terms_days"])
        txn = {
            "vendor_id": vendor_id,
            "vendor_name": vendor["vendor_name"],
            "invoice_date": invoice_date,
            "posting_date": target_date,
            "due_date": due_date,
            "account": account,
            "amount_eur": round(amount, 2),
            "posted_by": config.W_POSTED_BY,
            "memo_category": vendor["category"],
            "_plant_tag": "W",
        }
        filler_by_vendor[vendor_id].append(txn)
        w_txns.append(txn)
    return w_txns


def assign_order_refs(df: pd.DataFrame, offset_by_vendor: dict) -> list:
    """
    Assign each row a memo order-ref, independent of invoice_number
    (review). Assumes df is already sorted by
    (vendor_id, invoice_date, posting_date) -- i.e. each vendor's rows are
    contiguous and in chronological order -- which is exactly the sort in
    place when invoice_number is assigned in main().

    Ordinary rows get their own consecutive counter value, exactly parallel
    to invoice_number but from a separate offset (so the two numbers never
    coincide). D-class pairs are the one exception: both members of a
    duplicate-invoice pair (same _plant_tag, e.g. 'D-03') share ONE order
    ref and the counter advances only once for the pair -- the shared
    reference is the re-submission signature, discoverable in the memo,
    that distinguishes D (worry) from B3 (stand-down, genuinely distinct
    PO references).
    """
    vendor_ids = df["vendor_id"].tolist()
    plant_tags = df["_plant_tag"].tolist()
    order_refs = [0] * len(df)
    counters = {}
    pair_ref_by_vendor_tag = {}
    for i in range(len(df)):
        vid = vendor_ids[i]
        tag = plant_tags[i]
        if vid not in counters:
            counters[vid] = offset_by_vendor[vid]
        if tag.startswith("D-"):
            key = (vid, tag)
            if key in pair_ref_by_vendor_tag:
                order_refs[i] = pair_ref_by_vendor_tag[key]
                continue
            pair_ref_by_vendor_tag[key] = counters[vid]
        order_refs[i] = counters[vid]
        counters[vid] += 1
    return order_refs


# ---------------------------------------------------------------------------
# Main assembly
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print(f"{config.COMPANY_NAME} -- synthetic AP ledger generation")
    print("=" * 70)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ANSWER_KEY_DIR.mkdir(parents=True, exist_ok=True)

    rngs = make_rngs()

    print("\n[1/8] Building company calendar and chart of accounts...")
    calendar_df, working_days = build_calendar()
    coa_df = pd.DataFrame(config.CHART_OF_ACCOUNTS, columns=["account", "name_fi", "name_en", "class"])
    print(f"  calendar: {len(calendar_df)} days, {len(working_days)} working days")
    print(f"  chart of accounts: {len(coa_df)} accounts")

    print("\n[2/8] Generating vendor identities (200 vendors)...")
    generic_vendor_ids = [f"V-{i:04d}" for i in range(8, 8 + config.TOTAL_VENDORS - 7)]
    identities = generate_generic_identities(rngs["identity"], generic_vendor_ids)

    # The full, fixed 200-vendor ordering (story vendors first, then the
    # generic-scheme pool) -- used both for the invoice-number offset draw
    # below and again for vendor_master.csv assembly at the end of main().
    all_vendor_ids_ordered = (
        [config.TERASKONTIO_VENDOR_ID, config.KUORMARAITTI_VENDOR_ID]
        + [r["vendor_id"] for r in config.KARRENBACH_RECORDS]
        + [config.KAARNIALA_VENDOR_ID, config.NEUVANTILA_VENDOR_ID]
        + generic_vendor_ids
    )

    # Per-vendor invoice-number starting offset (review fix 2 --
    # every vendor previously started numbering at 1, an obvious artefact;
    # real vendors serve other customers too). Deterministic, one draw per
    # vendor in the fixed order above; invoice numbers for that vendor then
    # run consecutively from its offset.
    INVOICE_OFFSET_MIN = 1_000
    INVOICE_OFFSET_MAX = 950_000
    invoice_number_offset_by_vendor = {
        vid: int(rngs["invoice_offsets"].integers(INVOICE_OFFSET_MIN, INVOICE_OFFSET_MAX + 1))
        for vid in all_vendor_ids_ordered
    }

    # Per-vendor memo order-ref starting offset (review: the memo
    # {ref} token previously just echoed invoice_number everywhere, which
    # (a) undermines the D-class re-submission story -- a re-sent invoice
    # should reference the SAME underlying order on both pair members, not
    # get a fresh order number -- and (b) is a synthetic tell ledger-wide,
    # since a real order-reference sequence and a real invoice-number
    # sequence are independent systems. Drawn from a separate RNG stream in
    # the same fixed vendor order, so it never numerically coincides with
    # invoice_number_offset_by_vendor by construction of the source, and
    # essentially never by chance either.
    order_ref_offset_by_vendor = {
        vid: int(rngs["order_refs"].integers(INVOICE_OFFSET_MIN, INVOICE_OFFSET_MAX + 1))
        for vid in all_vendor_ids_ordered
    }

    # Attach category/allowed_accounts to every generic vendor.
    vendor_lookup = {}
    for vid in generic_vendor_ids:
        identity = identities[vid]
        if vid in config.RESERVED_VENDOR_ACCOUNTS:
            category = None
            allowed_accounts = config.RESERVED_VENDOR_ACCOUNTS[vid]
        else:
            category, allowed_accounts = assign_pure_filler_behavior(rngs["vendor_params"])
        vendor_lookup[vid] = {
            "vendor_id": vid,
            "vendor_name": identity["vendor_name"],
            "country": identity["country"],
            "vat_id": identity["vat_id"],
            "iban": identity["iban"],
            "address": identity["address"],
            "terms_days": identity["terms_days"],
            "category": category,
            "allowed_accounts": allowed_accounts,
        }
    print(f"  {len(generic_vendor_ids)} generic-scheme vendor identities generated")

    print("\n[3/8] Generating story vendors (Teräskontio, Kuormaraitti, Karrenbach trio, Kaarniala, Neuvantila)...")
    teraskontio_txns, step_eur = generate_teraskontio(rngs["story"])
    kuormaraitti_txns = generate_kuormaraitti(rngs["story"], step_eur)
    karrenbach_txns = generate_karrenbach(rngs["story"], working_days)
    kaarniala_txns = generate_kaarniala(rngs["story"], working_days)
    neuvantila_txns = generate_neuvantila(rngs["story"], working_days)
    print(f"  Teräskontio: {len(teraskontio_txns)}, Kuormaraitti: {len(kuormaraitti_txns)}, "
          f"Karrenbach trio: {len(karrenbach_txns)}, Kaarniala: {len(kaarniala_txns)}, "
          f"Neuvantila: {len(neuvantila_txns)}")
    print(f"  Teräskontio step_eur = {step_eur:.2f}")

    print("\n[4/8] Generating reserved plant classes (D, R, S, B1, B2, B3, B4, B5)...")
    d_txns = generate_D(vendor_lookup)
    r_txns = generate_R(vendor_lookup)
    s_txns = generate_S(vendor_lookup)
    b1_txns = generate_B1(vendor_lookup)
    b2_txns = generate_B2(vendor_lookup, working_days)
    b3_txns = generate_B3(vendor_lookup)
    b4_txns = generate_B4(vendor_lookup, working_days)
    b5_txns = generate_B5(vendor_lookup, working_days)
    print(f"  D: {len(d_txns)}, R: {len(r_txns)}, S: {len(s_txns)}, "
          f"B1: {len(b1_txns)}, B2: {len(b2_txns)}, B3: {len(b3_txns)}, "
          f"B4: {len(b4_txns)}, B5: {len(b5_txns)}")

    print("\n[5/8] Generating pure-filler vendor traffic (~180 vendors)...")
    pure_filler_ids = sorted(
        vid for vid in generic_vendor_ids
        if vid not in config.RESERVED_VENDOR_IDS
    )
    filler_by_vendor = {}
    for vid in pure_filler_ids:
        filler_by_vendor[vid] = generate_filler_stream(rngs["transactions"], vendor_lookup[vid], working_days)
    organic_total = sum(len(v) for v in filler_by_vendor.values())
    print(f"  {len(pure_filler_ids)} pure-filler vendors, {organic_total:,} organic transactions")

    print("\n[6/8] Injecting class W (8 non-working-day postings by U-117)...")
    w_txns = inject_W(rngs["plants"], filler_by_vendor, vendor_lookup, working_days)
    print(f"  W: {len(w_txns)} transactions appended to {len(set(t['vendor_id'] for t in w_txns))} host vendors")

    print("\n[7/8] Applying the deterministic filler adjustment to hit exactly "
          f"{config.TOTAL_TRANSACTIONS:,} rows...")
    fixed_total = (
        len(teraskontio_txns) + len(kuormaraitti_txns) + len(karrenbach_txns)
        + len(kaarniala_txns) + len(neuvantila_txns)
        + len(d_txns) + len(r_txns) + len(s_txns)
        + len(b1_txns) + len(b2_txns) + len(b3_txns) + len(b4_txns) + len(b5_txns)
    )
    filler_total_before = sum(len(v) for v in filler_by_vendor.values())
    current_total = fixed_total + filler_total_before
    delta = config.TOTAL_TRANSACTIONS - current_total
    print(f"  fixed/story/plant rows: {fixed_total:,}; filler rows (incl. W): {filler_total_before:,}; "
          f"running total: {current_total:,}; delta needed: {delta:+,}")

    # Spread the adjustment across several of the busiest pure-filler vendors
    # (deterministic choice: the N with the most organic transactions) rather
    # than dumping the whole delta onto one vendor, so no single vendor ends
    # up looking implausibly dominant.
    n_flex_vendors = min(config.N_FLEX_VENDORS, len(pure_filler_ids))
    flex_vendor_ids = sorted(pure_filler_ids, key=lambda v: (-len(filler_by_vendor[v]), v))[:n_flex_vendors]

    if delta > 0:
        base_share, remainder = divmod(delta, n_flex_vendors)
        for i, vid in enumerate(flex_vendor_ids):
            share = base_share + (1 if i < remainder else 0)
            if share == 0:
                continue
            extra = generate_filler_stream(rngs["filler"], vendor_lookup[vid], working_days, n_override=share)
            filler_by_vendor[vid] = rescrub_amounts(filler_by_vendor[vid] + extra, rngs["filler"])
        print(f"  added {delta} filler rows across {n_flex_vendors} flex vendors "
              f"({base_share}-{base_share + 1} rows each)")
    elif delta < 0:
        remove_total = -delta
        base_share, remainder = divmod(remove_total, n_flex_vendors)
        for i, vid in enumerate(flex_vendor_ids):
            remove_n = base_share + (1 if i < remainder else 0)
            if remove_n == 0:
                continue
            current_rows = filler_by_vendor[vid]
            removable = [t for t in current_rows if t["_plant_tag"] != "W"]
            untouchable = [t for t in current_rows if t["_plant_tag"] == "W"]
            removable.sort(key=lambda t: (t["invoice_date"], t["amount_eur"]))
            assert len(removable) > remove_n, f"flex vendor {vid} too small to absorb its share of the negative filler adjustment"
            filler_by_vendor[vid] = removable[:-remove_n] + untouchable
        print(f"  removed {remove_total} filler rows across {n_flex_vendors} flex vendors "
              f"({base_share}-{base_share + 1} rows each)")
    else:
        print("  no adjustment needed -- organic generation hit the target exactly")

    all_txns = (
        teraskontio_txns + kuormaraitti_txns + karrenbach_txns + kaarniala_txns + neuvantila_txns
        + d_txns + r_txns + s_txns + b1_txns + b2_txns + b3_txns + b4_txns + b5_txns
    )
    for vid in pure_filler_ids:
        all_txns.extend(filler_by_vendor[vid])

    total_rows = len(all_txns)
    print(f"  final row count: {total_rows:,}")
    assert total_rows == config.TOTAL_TRANSACTIONS, (
        f"Row count mismatch: got {total_rows}, expected {config.TOTAL_TRANSACTIONS}"
    )

    print("\n[8/8] Assigning invoice numbers and txn_ids, finalising memos, writing CSVs...")
    df = pd.DataFrame(all_txns)

    # Invoice numbers: strictly increasing and consecutive per vendor, in
    # invoice_date order, starting from that vendor's seeded offset rather
    # than 1 (review fix 2). Offsets run 1,000-950,000, so 6 digits
    # comfortably covers offset + up to a few thousand consecutive invoices.
    df = df.sort_values(["vendor_id", "invoice_date", "posting_date"], kind="stable").reset_index(drop=True)
    starting_offset = df["vendor_id"].map(invoice_number_offset_by_vendor)
    seq0 = df.groupby("vendor_id", sort=False).cumcount()
    df["invoice_number"] = (starting_offset + seq0).map(lambda n: f"{n:06d}")

    # Memo order-refs: a separate numbering system from invoice_number (main-
    # loop review). df is still sorted by (vendor_id, invoice_date,
    # posting_date) here, which assign_order_refs relies on.
    order_ref_ints = assign_order_refs(df, order_ref_offset_by_vendor)
    df["order_ref"] = [f"{n:06d}" for n in order_ref_ints]

    # Finalise memo text: rows either carry a literal 'memo' (verbatim
    # breadcrumbs: B2, B3, B4, B5) or a 'memo_template'/'memo_category' to
    # be formatted now that the order_ref is known. The memo's {ref} token
    # is the order_ref, not invoice_number -- an independent numbering
    # system, as in reality (review).
    def finalise_memo(row):
        if isinstance(row.get("memo"), str) and row["memo"]:
            return row["memo"]
        month_fi = config.FINNISH_MONTH_NAMES[row["invoice_date"].month]
        if isinstance(row.get("memo_template"), str) and row["memo_template"]:
            return row["memo_template"].format(ref=row["order_ref"], month_fi=month_fi)
        category = row.get("memo_category")
        template = config.MEMO_TEMPLATES_BY_CATEGORY[category]
        return template.format(ref=row["order_ref"], month_fi=month_fi)

    df["memo"] = df.apply(finalise_memo, axis=1)

    # txn_id: final deterministic sort, then sequential assignment.
    df = df.sort_values(["posting_date", "vendor_id", "invoice_number"], kind="stable").reset_index(drop=True)
    df["txn_id"] = [f"TXN{i + 1:06d}" for i in range(len(df))]

    # Answer key rows use these txn_ids -- build them before dropping the
    # internal-only columns.
    answer_key_rows = build_answer_key(df, vendor_lookup, step_eur)

    df["invoice_date"] = df["invoice_date"].map(lambda d: d.isoformat())
    df["posting_date"] = df["posting_date"].map(lambda d: d.isoformat())
    df["due_date"] = df["due_date"].map(lambda d: d.isoformat())

    gl_df = df[[
        "txn_id", "posting_date", "invoice_date", "due_date", "vendor_id", "vendor_name",
        "account", "amount_eur", "invoice_number", "posted_by", "memo",
    ]].copy()

    # Story vendors need identity fields too -- build them now.
    story_identities = build_story_identities(rngs["story"])
    vendor_master_full = []
    seen = set()
    for vid in all_vendor_ids_ordered:
        if vid in seen:
            continue
        seen.add(vid)
        if vid in story_identities:
            info = story_identities[vid]
        else:
            info = vendor_lookup[vid]
        vendor_master_full.append({
            "vendor_id": vid,
            "vendor_name": info["vendor_name"],
            "country": info["country"],
            "vat_id": info["vat_id"],
            "iban": info["iban"],
            "address": info["address"],
            "terms_days": info["terms_days"],
            "allowed_accounts": ";".join(info["allowed_accounts"]),
            "active_from": f"{config.YEAR}-01-01",
        })
    vendor_master_df = pd.DataFrame(vendor_master_full)

    write_csv(gl_df, DATA_DIR / "gl_transactions.csv")
    write_csv(vendor_master_df, DATA_DIR / "vendor_master.csv")
    write_csv(coa_df, DATA_DIR / "chart_of_accounts.csv")
    write_csv(calendar_df, DATA_DIR / "company_calendar.csv")
    write_csv(pd.DataFrame(answer_key_rows), ANSWER_KEY_DIR / "anomalies.csv")

    print(f"  gl_transactions.csv:   {len(gl_df):,} rows")
    print(f"  vendor_master.csv:     {len(vendor_master_df):,} rows")
    print(f"  chart_of_accounts.csv: {len(coa_df):,} rows")
    print(f"  company_calendar.csv:  {len(calendar_df):,} rows")
    print(f"  answer_key/anomalies.csv: {len(answer_key_rows):,} rows")

    integ_share = (gl_df["posted_by"] == config.INTEGRATION_USER).mean()
    print(f"\n  INTEG-01 share of all rows: {integ_share:.1%}")

    print("\n" + "=" * 70)
    print("Ledger generation complete.")
    print("=" * 70)


def build_story_identities(rng: np.random.Generator) -> dict:
    """Identity fields (country/vat/iban/address) for the 7 story vendors."""
    used_ibans = set()
    identities = {}

    identities[config.TERASKONTIO_VENDOR_ID] = {
        "vendor_name": config.TERASKONTIO_NAME, "country": "FI",
        "vat_id": make_vat_id(rng, "FI"), "iban": make_iban(rng, "FI", used_ibans),
        "address": make_address(rng, "FI"), "terms_days": config.TERASKONTIO_TERMS_DAYS,
        "allowed_accounts": [config.ACCOUNT_TERASKONTIO],
    }
    identities[config.KUORMARAITTI_VENDOR_ID] = {
        "vendor_name": config.KUORMARAITTI_NAME, "country": "FI",
        "vat_id": make_vat_id(rng, "FI"), "iban": make_iban(rng, "FI", used_ibans),
        "address": make_address(rng, "FI"), "terms_days": config.KUORMARAITTI_TERMS_DAYS,
        "allowed_accounts": [config.ACCOUNT_KUORMARAITTI],
    }
    for rec in config.KARRENBACH_RECORDS:
        identities[rec["vendor_id"]] = {
            "vendor_name": rec["name"], "country": "DE",
            "vat_id": config.KARRENBACH_SHARED_VAT_ID,
            "iban": make_iban(rng, "DE", used_ibans),
            "address": config.KARRENBACH_SHARED_ADDRESS,
            "terms_days": config.KARRENBACH_TERMS_DAYS,
            "allowed_accounts": [config.ACCOUNT_KARRENBACH],
        }
    identities[config.KAARNIALA_VENDOR_ID] = {
        "vendor_name": config.KAARNIALA_NAME, "country": "FI",
        "vat_id": make_vat_id(rng, "FI"), "iban": make_iban(rng, "FI", used_ibans),
        "address": make_address(rng, "FI"), "terms_days": config.KAARNIALA_TERMS_DAYS,
        "allowed_accounts": [config.ACCOUNT_KAARNIALA_CORRECT],
    }
    identities[config.NEUVANTILA_VENDOR_ID] = {
        "vendor_name": config.NEUVANTILA_NAME, "country": "FI",
        "vat_id": make_vat_id(rng, "FI"), "iban": make_iban(rng, "FI", used_ibans),
        "address": make_address(rng, "FI"), "terms_days": config.NEUVANTILA_TERMS_DAYS,
        "allowed_accounts": [config.ACCOUNT_NEUVANTILA],
    }
    return identities


def build_answer_key(df: pd.DataFrame, vendor_lookup: dict, step_eur: float) -> list:
    """Build the held-out answer key rows from the finalised, txn_id-bearing
    dataframe. df must still carry the internal _plant_tag column."""
    rows = []

    def txn_ids_for_tag(tag):
        return df.loc[df["_plant_tag"] == tag, "txn_id"].tolist()

    def months_for_tag(tag):
        return sorted(set(df.loc[df["_plant_tag"] == tag, "invoice_date"].map(lambda d: d.month)))

    # D -- duplicate invoices, one row per pair (event grain, review).
    # Both members of a pair share one memo order-ref (assign_order_refs) --
    # the discoverable evidence of a re-submission, recorded here verbatim.
    for pair_i in range(6):
        event_tag = f"D-{pair_i + 1:02d}"
        vendor_id = config.D_VENDOR_IDS[pair_i % 3]
        ids = txn_ids_for_tag(event_tag)
        pair_rows = df.loc[df["_plant_tag"] == event_tag]
        shared_order_ref = pair_rows["order_ref"].iloc[0] if len(pair_rows) else ""
        rows.append({
            "anomaly_id": event_tag, "class": "D", "kind": "anomalous",
            "vendor_id": vendor_id, "txn_ids": ";".join(ids),
            "months": ";".join(str(m) for m in months_for_tag(event_tag)),
            "mechanism": "Vendor re-submits an unpaid invoice under a new invoice number but the SAME memo order "
                         f"reference (tilaus {shared_order_ref}); same amount to the cent, "
                         f"{config.D_PAIR_GAP_DAYS[pair_i]} days apart.",
            "designed_catch": "rules", "expected_verdict": "worry",
            "expected_finding": "Duplicate-payment risk: same-vendor, same-amount pair with distinct invoice numbers "
                                 "but a shared order reference in the memo.",
            "notes": f"One of 6 duplicate pairs across 3 vendors (2 pairs each); posting_date gap always >3 days so "
                     f"the split test cannot also fire. The shared order reference tilaus {shared_order_ref} in "
                     "both invoices' memos is the discoverable evidence that they are one re-submitted order, not "
                     "two genuine deliveries -- contrast B3, whose memos cite two distinct PO references.",
        })

    # R -- round sums near the tier, one row per sub-mechanism (event grain)
    r_round_ids = txn_ids_for_tag("R-ROUND")
    rows.append({
        "anomaly_id": "R-ROUND", "class": "R", "kind": "anomalous",
        "vendor_id": config.R_ROUND_VENDOR_ID, "txn_ids": ";".join(r_round_ids),
        "months": ";".join(str(m) for m in months_for_tag("R-ROUND")),
        "mechanism": "6 invoices at exact EUR1,000 multiples (EUR5,000-9,000).",
        "designed_catch": "rules", "expected_verdict": "worry",
        "expected_finding": "Round-sum habit: 6 exact-multiple invoices from one vendor.",
        "notes": "Half of class R (the other half is R-NEAR, a distinct vendor and mechanism).",
    })
    r_near_ids = txn_ids_for_tag("R-NEAR")
    rows.append({
        "anomaly_id": "R-NEAR", "class": "R", "kind": "anomalous",
        "vendor_id": config.R_NEAR_VENDOR_ID, "txn_ids": ";".join(r_near_ids),
        "months": ";".join(str(m) for m in months_for_tag("R-NEAR")),
        "mechanism": "4 invoices sitting just under the EUR10,000 approval tier (EUR9,500-9,999.99, non-round).",
        "designed_catch": "rules", "expected_verdict": "worry",
        "expected_finding": "Near-threshold habit: 4 invoices from a different vendor, just below the department-head approval tier.",
        "notes": "Half of class R (the other half is R-ROUND, a distinct vendor and mechanism).",
    })

    # W -- non-working-day postings
    w_ids = txn_ids_for_tag("W")
    rows.append({
        "anomaly_id": "W-01", "class": "W", "kind": "anomalous",
        "vendor_id": ";".join(sorted(set(df.loc[df["_plant_tag"] == "W", "vendor_id"]))), "txn_ids": ";".join(w_ids),
        "months": ";".join(str(m) for m in months_for_tag("W")),
        "mechanism": "8 postings by U-117 on non-working days: five Saturdays (Feb-Jun) plus Easter Monday, Ascension and Midsummer Eve.",
        "designed_catch": "rules", "expected_verdict": "worry",
        "expected_finding": "One user habitually posts on non-working days -- a controls/process question about U-117, not the vendors.",
        "notes": "Cluster by posted_by, not by vendor -- the story is the user.",
    })

    # V -- vendor name variants
    v_ids = txn_ids_for_tag("V")
    rows.append({
        "anomaly_id": "V-01", "class": "V", "kind": "anomalous",
        "vendor_id": ";".join(r["vendor_id"] for r in config.KARRENBACH_RECORDS), "txn_ids": ";".join(v_ids),
        "months": ";".join(str(m) for m in months_for_tag("V")),
        "mechanism": "One real supplier exists as three master records (Kärrenbach/Kaerrenbach/KARRENBACH DICHTUNGSTECHNIK GMBH), "
                     "sharing VAT id and address but with distinct IBANs; spend split 7/5/3 invoices.",
        "designed_catch": "agent", "expected_verdict": "worry",
        "expected_finding": "Split-vendor spend concentration, found only by cross-record reasoning (shared VAT id/address) -- "
                             "no rule test catches it by design (byte-exact name hygiene scores zero here).",
        "notes": "Production catch: fuzzy-name and duplicate-VAT-ID/IBAN hygiene tests (declared out of the implemented rule set).",
    })

    # A -- mis-posted account
    a_ids = txn_ids_for_tag("A")
    rows.append({
        "anomaly_id": "A-01", "class": "A", "kind": "anomalous",
        "vendor_id": config.KAARNIALA_VENDOR_ID, "txn_ids": ";".join(a_ids),
        "months": ";".join(str(m) for m in months_for_tag("A")),
        "mechanism": "All 8 Kaarniala invoices (Sep-Oct) posted to the IT-services account instead of the marketing account, by U-204.",
        "designed_catch": "rules", "expected_verdict": "worry",
        "expected_finding": "Vendor-to-account mapping violation: an advertising agency's invoices sitting in IT-services costs.",
        "notes": f"Vendor's allowed_accounts = {config.ACCOUNT_KAARNIALA_CORRECT} (marketing); actual postings = {config.ACCOUNT_KAARNIALA_MISPOST} (IT services).",
    })

    # G -- gradual drift (Teräskontio elevated H2 + Kuormaraitti mirror as corroborating evidence)
    g_ids = txn_ids_for_tag("G")
    kuormaraitti_h1_ids = txn_ids_for_tag("KUORMARAITTI_H1")
    kuormaraitti_h2_ids = txn_ids_for_tag("KUORMARAITTI_H2")
    rows.append({
        "anomaly_id": "G-01", "class": "G", "kind": "anomalous",
        "vendor_id": config.TERASKONTIO_VENDOR_ID, "txn_ids": ";".join(g_ids),
        "months": ";".join(str(m) for m in months_for_tag("G")),
        "mechanism": "From July, Teräskontio bundles freight into goods invoices (+8% step, memo gains 'sis. rahtikulut'), "
                     "then a further +2%/month compounding rise hidden inside the bundle (Dec ~= +19% over baseline).",
        "designed_catch": "detector", "expected_verdict": "worry",
        "expected_finding": "Vendor price drift concealed by a billing-structure change; elevated vendor_amount_z pushes the H2 "
                             "invoices into the detector's flagged tail.",
        "notes": (
            f"kuormaraitti_vendor_id={config.KUORMARAITTI_VENDOR_ID};"
            f"kuormaraitti_h1_txn_ids={'|'.join(kuormaraitti_h1_ids)};"
            f"kuormaraitti_h2_txn_ids={'|'.join(kuormaraitti_h2_ids)};"
            f"step_eur={step_eur:.2f};"
            f"reconciliation_tolerance_frac={config.KUORMARAITTI_RECONCILIATION_TOLERANCE_FRAC};"
            "mechanism_note=Kuormaraitti's Teräskontio-lane freight billing declines by ~=step_eur from July, "
            "corroborating that the step is a bundling reclassification, not a real cost increase."
        ),
    })

    # S -- split purchases, one row per event (event grain, review)
    for event_ix, event in enumerate(config.S_EVENTS):
        event_tag = f"S-{event_ix + 1:02d}"
        vendor_id = config.S_VENDOR_IDS[event["vendor_ix"]]
        ids = txn_ids_for_tag(event_tag)
        part_sum = event["part_a_eur"] + event["part_b_eur"]
        rows.append({
            "anomaly_id": event_tag, "class": "S", "kind": "anomalous",
            "vendor_id": vendor_id, "txn_ids": ";".join(ids),
            "months": ";".join(str(m) for m in months_for_tag(event_tag)),
            "mechanism": f"One purchase split into 2 same-vendor invoices {event['offset_days']} day(s) apart, "
                         f"parts EUR{event['part_a_eur']:.2f} and EUR{event['part_b_eur']:.2f} "
                         f"(sum EUR{part_sum:.2f}) vs the EUR10,000 approval tier.",
            "designed_catch": "rules", "expected_verdict": "worry",
            "expected_finding": "Threshold-structuring pattern: a purchase split to stay clear of single-invoice approval review.",
            "notes": "One of 5 split-purchase events across 3 vendors; parts differ in amount within the pair so the "
                     "duplicate test cannot also fire.",
        })

    # C -- the ceiling
    c_ids = txn_ids_for_tag("C")
    rows.append({
        "anomaly_id": "C-01", "class": "C", "kind": "anomalous",
        "vendor_id": config.NEUVANTILA_VENDOR_ID, "txn_ids": ";".join(c_ids),
        "months": ";".join(str(m) for m in months_for_tag("C")),
        "mechanism": "12 unremarkable monthly consulting invoices, correct account, correct cadence, mid-month working days, "
                     "tight amount band -- catchable only with data this ledger does not carry (contracts, deliverables, three-way match).",
        "designed_catch": "nobody", "expected_verdict": "stand_down",
        "expected_finding": "No finding expected. Any run that accuses Neuvantila without evidence is scored as a false positive.",
        "notes": "The honesty centrepiece: production catch is PO/goods-receipt three-way matching, out of scope for this ledger.",
    })

    # Benign items
    def benign_row(anomaly_id, cls, vendor_id, tag, mechanism, expected_finding, notes):
        ids = txn_ids_for_tag(tag)
        rows.append({
            "anomaly_id": anomaly_id, "class": cls, "kind": "benign",
            "vendor_id": vendor_id, "txn_ids": ";".join(ids),
            "months": ";".join(str(m) for m in months_for_tag(tag)),
            "mechanism": mechanism, "designed_catch": "rules" if cls in ("B1", "B2", "B3") else "detector",
            "expected_verdict": "stand_down", "expected_finding": expected_finding, "notes": notes,
        })

    benign_row(
        "B1", "B1", config.B1_VENDOR_ID, "B1",
        "Landlord rent, EUR15,000.00 exactly, monthly by contract.",
        "Round-sum test fires on all 12 rent postings; correct stand-down is a contracted, recurring, identical-vendor rent.",
        "Second-pass recurring-identical suppression would silence this in week one of real practice.",
    )
    benign_row(
        "B2", "B2", config.B2_VENDOR_ID, "B2",
        "Agreed Saturday overtime for a stock count, 15 Nov 2025, posted by U-031; memo states the justification.",
        "Calendar test fires; memo evidences a genuine, agreed exception.",
        "",
    )
    benign_row(
        "B3", "B3", config.B3_VENDOR_ID, "B3",
        "Coincidental equal-amount pair (EUR7,420.00 twice, 4 days apart) -- genuinely distinct deliveries, different invoice numbers and PO references.",
        "Duplicate test fires; memos show two different PO references, evidencing two real, separate deliveries.",
        "",
    )
    benign_row(
        "B4", "B4", config.B4_VENDOR_ID, "B4",
        "One-off capex: a machine at EUR78,400, correctly posted to the fixed-asset account.",
        "Detector flags it as a top singleton; correct stand-down is a legitimate, correctly coded one-off purchase.",
        "",
    )
    benign_row(
        "B5", "B5", config.B5_VENDOR_ID, "B5",
        "Annual insurance premium, EUR24,600, January, correctly posted to the insurance account.",
        "Detector flags it as a top singleton; correct stand-down is a legitimate annual premium.",
        "",
    )

    # B6 -- declared pattern, not itemised.
    rows.append({
        "anomaly_id": "B6", "class": "B6", "kind": "benign",
        "vendor_id": "", "txn_ids": "", "months": "11;12",
        "mechanism": "November-December procurement peak (customer year-end stocking), designed into MONTH_SEASONALITY_WEIGHT.",
        "designed_catch": "detector", "expected_verdict": "stand_down",
        "expected_finding": "Detector month-clustering surfaces a December/November volume cluster; correct stand-down is ordinary seasonality.",
        "notes": "Declared pattern, not itemised -- no dedicated txn_ids; identified by the seasonal volume profile itself.",
    })

    return rows


def write_csv(df: pd.DataFrame, path: Path) -> None:
    assert path.parent == DATA_DIR or path.parent == ANSWER_KEY_DIR, f"Refusing to write outside data/: {path}"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        df.to_csv(fh, index=False, lineterminator="\n", float_format="%.2f")


if __name__ == "__main__":
    main()
