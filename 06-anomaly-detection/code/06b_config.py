"""
06b_config.py -- All tunable parameters for the Saarnitukku Oy FY2026 purchase
ledger (the 06b "standing vendor-drift review" sequel to 06a).

Everything that controls the shape of the 06b data lives here. Logic lives in
06b_generate.py (generation) and 06b_validate.py (coherence checks). The
detection method itself (drift_report.py) takes its own fixed, pre-registered
parameters -- k, h, minimum invoices/month, minimum baseline months -- which
are declared in drift_report.py, NOT here, because the design requires
them fixed independently of the generator and never tuned against the data.

06b is deliberately much simpler than 06a's generator: there is no rule layer
to dodge (no accidental round-sum/near-threshold/duplicate signatures to
avoid), and the ledger carries exactly five planted items (three drift
anomalies, two benign lookalikes) -- otherwise it is clean, ordinary traffic.

Stated simplification (06b-specific, not present in 06a): every vendor is
domiciled in Finland. 06a's cross-border vendor mix existed to support its
class-V (name-variant / shared VAT id) mechanism; 06b plants no such class, so
the added country/VAT-format/IBAN-length variation would spend generation
effort without buying an exhibit.
"""

import datetime

# ---------------------------------------------------------------------------
# Global settings
# ---------------------------------------------------------------------------

RANDOM_SEED = 2026

COMPANY_NAME = "Saarnitukku Oy"
YEAR = 2026

TOTAL_TRANSACTIONS = 50_000
TOTAL_VENDORS = 200

# Declared invented convention, unchanged from 06a for continuity (the same
# company, its next year).
APPROVAL_TIER_DEPT_HEAD_EUR = 10_000.0
APPROVAL_TIER_CFO_EUR = 50_000.0

# ---------------------------------------------------------------------------
# Company calendar -- Finland, 2026.
# ---------------------------------------------------------------------------
# Computed programmatically (Gregorian Easter algorithm) rather than hand-typed
# -- 06a's dates came from a sourced 2025 calendar; no
# equivalent sourced list exists for 2026, so dates are derived, not guessed,
# and checked against Finland's statutory holiday list (fixed dates + the
# Easter-relative and Midsummer ones).

def _easter_sunday(year: int) -> datetime.date:
    """Anonymous Gregorian algorithm (Meeus/Jones/Butcher)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return datetime.date(year, month, day)


def _midsummer_eve(year: int) -> datetime.date:
    """Finnish law: Juhannusaatto is the Friday falling between 19-25 June."""
    for d in range(19, 26):
        candidate = datetime.date(year, 6, d)
        if candidate.weekday() == 4:
            return candidate
    raise ValueError("No Friday found in 19-25 June -- should not happen")


_EASTER_2026 = _easter_sunday(YEAR)

HOLIDAYS_2026 = {
    datetime.date(YEAR, 1, 1): "Uudenvuodenpaiva (New Year's Day)",
    datetime.date(YEAR, 1, 6): "Loppiainen (Epiphany)",
    _EASTER_2026 - datetime.timedelta(days=2): "Pitkaperjantai (Good Friday)",
    _EASTER_2026 + datetime.timedelta(days=1): "2. paasiaispaiva (Easter Monday)",
    datetime.date(YEAR, 5, 1): "Vappu (May Day)",
    _EASTER_2026 + datetime.timedelta(days=39): "Helatorstai (Ascension Day)",
    _midsummer_eve(YEAR): "Juhannusaatto (Midsummer Eve, de facto non-working)",
    datetime.date(YEAR, 12, 24): "Jouluaatto (Christmas Eve, de facto non-working)",
    datetime.date(YEAR, 12, 25): "Joulupaiva (Christmas Day)",
    datetime.date(YEAR, 12, 26): "Tapaninpaiva (Boxing Day)",
}

# ---------------------------------------------------------------------------
# Posting roster (same conventions as 06a: an integration user carries most
# rows; a small human roster carries the rest). No calendar-anomaly plant
# exists in 06b, so this exists for realism only, not for a rule test.
# ---------------------------------------------------------------------------

INTEGRATION_USER = "INTEG-01"
INTEGRATION_SHARE = 0.82

HUMAN_USERS = ["U-211", "U-238", "U-054", "U-179"]

INTEGRATION_LAG_CALENDAR_DAYS = (0, 1)
HUMAN_LAG_BUSINESS_DAYS = (2, 3, 4, 5)

TERMS_DAYS_OPTIONS = [14, 21, 30]
TERMS_DAYS_WEIGHTS = [0.40, 0.30, 0.30]

# ---------------------------------------------------------------------------
# Chart of accounts (reduced from 06a's ~40 rows -- 06b needs enough accounts
# for realistic goods/services/other-operating spread, not a full statutory
# sweep; same numbering ranges/conventions).
# ---------------------------------------------------------------------------

CHART_OF_ACCOUNTS = [
    ("1200", "Koneet ja kalusto", "Machinery and equipment", "fixed_asset"),
    ("4000", "Ostot kotimaasta", "Domestic purchases", "purchases"),
    ("4010", "Ostot ulkomailta", "Foreign purchases", "purchases"),
    ("4100", "Teras- ja metallituotteet", "Steel and metal products", "purchases"),
    ("4110", "Tiivisteet ja komponentit", "Seals and components", "purchases"),
    ("4200", "Tyokalut ja tarvikkeet", "Tools and supplies", "purchases"),
    ("4300", "Kunnossapitotarvikkeet", "Maintenance supplies", "purchases"),
    ("4310", "Varaosat", "Spare parts", "purchases"),
    ("4410", "Rahtikulut", "Freight costs", "external_services"),
    ("4420", "Alihankinta", "Subcontracting", "external_services"),
    ("4430", "Konsultointipalvelut", "Consulting services", "external_services"),
    ("7000", "Toimitilavuokrat", "Premises rent", "other_operating"),
    ("7100", "Markkinointi", "Marketing", "other_operating"),
    ("7200", "IT-palvelut", "IT services", "other_operating"),
    ("7300", "Vakuutukset", "Insurance", "other_operating"),
    ("7500", "Toimistotarvikkeet", "Office supplies", "other_operating"),
    ("7600", "Matkakulut", "Travel costs", "other_operating"),
    ("7900", "Energia ja vesi", "Energy and water", "other_operating"),
]

ACCOUNTS_GOODS_SMALL = ["4000", "4200", "4300"]
ACCOUNTS_GOODS_BULK = ["4010", "4100", "4110", "4310"]
ACCOUNTS_EXTERNAL_SERVICES = ["4410", "4420", "4430"]
ACCOUNTS_OTHER_OPERATING = ["7000", "7100", "7200", "7300", "7500", "7600", "7900"]

# ---------------------------------------------------------------------------
# Vendor master -- naming scheme (Finland-only, see module docstring)
# ---------------------------------------------------------------------------
# Fresh combinatorial roots, deliberately disjoint from 06a's prefix/mid
# vocabulary (checked by eye against 06a's code/config.py word lists, then
# collision-checked programmatically at generation time against the actual
# 06a vendor_master.csv and the six case-study company names).

GENERIC_NAME_PREFIXES = [
    "Louhi", "Aho", "Kivi", "Harju", "Rinne", "Vuori", "Saari", "Koski",
    "Salo", "Manner", "Niitty", "Kanerva", "Metsa", "Virta", "Ranta",
    "Honka", "Petaja", "Vaahtera", "Pihka", "Sara", "Kanto", "Tuomi",
    "Lehto", "Kuusama", "Hanki", "Jaa", "Kalju", "Louhos",
]
GENERIC_NAME_MID = [
    "malmi", "harkko", "valssi", "aihio", "kanki", "lastu",
    "tukku", "tarvike", "komponentti", "huolto", "varaosa", "palvelu",
    "logistiikka", "tekniikka", "valine", "materiaali", "asennus", "jarjestelma",
]
GENERIC_NAME_SUFFIXES = ["Oy", "Oy Ab", "Ky", "Tmi"]

ADDRESS_STREETS = [
    "Esimerkkikatu", "Esimerkkikatu", "Esimerkkikatu", "Esimerkkikatu", "Esimerkkikatu",
    "Esimerkkikatu", "Esimerkkikatu", "Esimerkkikatu", "Esimerkkikatu", "Esimerkkikatu",
]
ADDRESS_CITIES = ["Vantaa", "Helsinki", "Tampere", "Turku", "Kuopio", "Lahti", "Oulu", "Jyvaskyla"]

# ---------------------------------------------------------------------------
# Generic vendor archetype categories.
# ---------------------------------------------------------------------------
# has_unit_price = True categories carry per-invoice quantity + unit_price_eur
# columns (amount_eur = quantity * unit_price_eur) -- goods invoices in
# practice itemise quantity and unit price. has_unit_price = False categories
# carry only amount_eur (quantity = 1, unit_price_eur = amount_eur) -- service
# invoices in practice are billed as a lump sum. This split is what makes the
# design's "falling back to invoice-level totals where item granularity
# is absent" clause concrete, and it is also exactly the shape of 06a's own
# ledger (amount_eur only, no quantity/unit_price at all) -- so drift_report.py
# runs unmodified against both files.

GENERIC_VENDOR_CATEGORIES = {
    "goods_small": {
        "weight": 0.30,
        "accounts": ACCOUNTS_GOODS_SMALL,
        "has_unit_price": True,
        "unit_price_mean": 25.0,
        "unit_price_cv": 0.06,
        "quantity_range": (5, 60),
        "monthly_rate_mean": 26.0,
        "monthly_rate_gamma_shape": 1.4,
    },
    "goods_bulk": {
        "weight": 0.15,
        "accounts": ACCOUNTS_GOODS_BULK,
        "has_unit_price": True,
        "unit_price_mean": 110.0,
        "unit_price_cv": 0.06,
        "quantity_range": (3, 40),
        "monthly_rate_mean": 14.0,
        "monthly_rate_gamma_shape": 1.4,
    },
    "external_services": {
        "weight": 0.20,
        "accounts": ACCOUNTS_EXTERNAL_SERVICES,
        "has_unit_price": False,
        "amount_mean": 1_900.0,
        "amount_cv": 0.50,
        "monthly_rate_mean": 22.0,
        "monthly_rate_gamma_shape": 1.3,
    },
    "other_operating": {
        "weight": 0.25,
        "accounts": ACCOUNTS_OTHER_OPERATING,
        "has_unit_price": False,
        "amount_mean": 950.0,
        "amount_cv": 0.60,
        "monthly_rate_mean": 19.0,
        "monthly_rate_gamma_shape": 1.3,
    },
    "sparse_rare": {
        "weight": 0.10,
        "accounts": ACCOUNTS_GOODS_SMALL + ACCOUNTS_EXTERNAL_SERVICES + ACCOUNTS_OTHER_OPERATING,
        "has_unit_price": False,
        "amount_mean": 2_400.0,
        "amount_cv": 0.65,
        "monthly_rate_mean": 4.0,
        "monthly_rate_gamma_shape": 1.2,
    },
}

MONTHLY_RATE_CLIP_MAX = 110.0
N_FLEX_VENDORS = 8

# ---------------------------------------------------------------------------
# Seasonality -- same profile as 06a (Nov-Dec peak, Jul trough).
# ---------------------------------------------------------------------------

MONTH_SEASONALITY_WEIGHT = {
    1: 0.95, 2: 0.95, 3: 1.00, 4: 1.00, 5: 1.00, 6: 0.95,
    7: 0.70, 8: 0.90, 9: 1.00, 10: 1.05, 11: 1.30, 12: 1.30,
}

FINNISH_MONTH_NAMES = {
    1: "tammikuu", 2: "helmikuu", 3: "maaliskuu", 4: "huhtikuu",
    5: "toukokuu", 6: "kesakuu", 7: "heinakuu", 8: "elokuu",
    9: "syyskuu", 10: "lokakuu", 11: "marraskuu", 12: "joulukuu",
}

MEMO_TEMPLATES_BY_CATEGORY = {
    "goods_small": "Tavarantoimitus, tilaus {ref}",
    "goods_bulk": "Materiaalitoimitus, tilaus {ref}",
    "external_services": "Palvelulasku, {ref}",
    "other_operating": "Ostolasku, {ref}",
    "sparse_rare": "Kertatoimitus, tilaus {ref}",
}

# ---------------------------------------------------------------------------
# The five planted items -- reserved vendors V-0001..V-0005.
# ---------------------------------------------------------------------------
# All five are "goods_bulk"-shaped (unit-priced) so a per-vendor monthly
# volume-weighted unit price is a natural, defensible signal for each -- a
# distributor's steel/fastener/tooling suppliers are exactly where a
# controller would expect to track unit prices over time.
#
# Rates and start months are pinned to the pre-registered design; per-invoice noise levels (sigma_frac), monthly
# invoice volume and the precise mechanics of each step are this script's
# generation-side choices -- never touched to retune the OUTPUT of
# drift_report.py, only chosen up front to realise the described real-world
# mechanism plausibly.

D1_VENDOR_ID = "V-0001"
D1_VENDOR_NAME = "Louhimalmi Oy"
D1_ACCOUNT = "4100"
D1_BASE_UNIT_PRICE_EUR = 80.0
D1_SIGMA_FRAC = 0.03
D1_MONTHLY_RATE_MEAN = 12.0
D1_QUANTITY_RANGE = (8, 30)
D1_DRIFT_START_MONTH = 4          # April
D1_DRIFT_RATE_MONTHLY = 0.025     # ~2.5%/month, compounding

D2_VENDOR_ID = "V-0002"
D2_VENDOR_NAME = "Ahoharkko Oy"
D2_ACCOUNT = "4110"
D2_BASE_UNIT_PRICE_EUR = 60.0
D2_SIGMA_FRAC = 0.045              # noisier than D1/D3 -- the sensitivity test
D2_MONTHLY_RATE_MEAN = 12.0
D2_QUANTITY_RANGE = (8, 30)
D2_DRIFT_START_MONTH = 2          # February
D2_DRIFT_RATE_MONTHLY = 0.010     # ~1.0%/month, compounding

D3_VENDOR_ID = "V-0003"
D3_VENDOR_NAME = "Rantavalssi Oy"
D3_ACCOUNT = "4100"
D3_BASE_UNIT_PRICE_EUR = 150.0
D3_SIGMA_FRAC = 0.03
D3_MONTHLY_RATE_MEAN = 10.0
D3_QUANTITY_RANGE = (5, 25)
D3_BUNDLE_START_MONTH = 6         # June
D3_BUNDLE_STEP_FRACTION = 0.06    # freight folded in -- one-off step
D3_DRIFT_RATE_MONTHLY = 0.018     # ~1.8%/month thereafter, compounding
D3_MEMO_BREADCRUMB = "sis. rahtikulut"

B1_VENDOR_ID = "V-0004"
B1_VENDOR_NAME = "Kiviaihio Oy"
B1_ACCOUNT = "4100"
B1_BASE_UNIT_PRICE_EUR = 50.0
B1_SIGMA_FRAC = 0.03
B1_MONTHLY_RATE_MEAN = 12.0
B1_QUANTITY_RANGE = (8, 30)
B1_STEP_FRACTION = 0.052          # +5.2% contractual indexation
# January invoices reflect December-negotiated deliveries still billed at the
# outgoing rate (ordinary processing lag); the indexed rate is live for every
# invoice dated February onward. This is the smallest realistic mechanism
# consistent with "step on 1 January" -- and it is also what gives the
# drift review's own within-year, expanding-baseline method any chance of
# seeing a step that (by the design's own scope note) lands
# right at the edge of "a vendor's first three months (no baseline)".
B1_STEP_EFFECTIVE_MONTH = 2       # February onward at the new rate

B2_VENDOR_ID = "V-0005"
B2_VENDOR_NAME = "Virtakanki Oy"
B2_ACCOUNT = "4200"
B2_BASE_UNIT_PRICE_EUR = 100.0
B2_SIGMA_FRAC = 0.03
B2_MONTHLY_RATE_MEAN = 12.0
B2_QUANTITY_RANGE = (8, 30)
B2_STEP_FRACTION = 0.09           # ~9% market repricing
B2_STEP_MONTH = 8                 # August

RESERVED_VENDOR_IDS = [D1_VENDOR_ID, D2_VENDOR_ID, D3_VENDOR_ID, B1_VENDOR_ID, B2_VENDOR_ID]
RESERVED_VENDOR_NAMES = {
    D1_VENDOR_ID: D1_VENDOR_NAME,
    D2_VENDOR_ID: D2_VENDOR_NAME,
    D3_VENDOR_ID: D3_VENDOR_NAME,
    B1_VENDOR_ID: B1_VENDOR_NAME,
    B2_VENDOR_ID: B2_VENDOR_NAME,
}
RESERVED_VENDOR_ACCOUNTS = {
    D1_VENDOR_ID: [D1_ACCOUNT],
    D2_VENDOR_ID: [D2_ACCOUNT],
    D3_VENDOR_ID: [D3_ACCOUNT],
    B1_VENDOR_ID: [B1_ACCOUNT],
    B2_VENDOR_ID: [B2_ACCOUNT],
}

# ---------------------------------------------------------------------------
# Collision guards: every 06b vendor name is checked against
# 6a's vendor master and the six case-study company names.
# ---------------------------------------------------------------------------

PORTFOLIO_COMPANY_NAMES = [
    "Jalavakoski Konepaja",
    "Pyokkipaja",
    "Saarnitukku",
    "Paju Consumer Products",
    "Kataja Analytics",
    "Sammalkoski",
]

# ---------------------------------------------------------------------------
# Output paths (relative to the project root -- resolved in each script)
# ---------------------------------------------------------------------------

OUTPUT_DATA_DIR = "data/06b"
