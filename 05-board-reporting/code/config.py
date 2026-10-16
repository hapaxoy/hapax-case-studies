"""
config.py — All tunable parameters for the Paju Consumer Products Oy synthetic
board-reporting dataset.

Everything that controls the shape of the data lives here. Logic lives in
generate_financials.py. A handful of values below (BASE_VOLUME_FY2023,
UNIT_*_COST_CENTS_FY2023, monthly trend rates) are *derived* from the more
intuitive target parameters above them via plain arithmetic — this is still
configuration, not simulation: change a target percentage and every derived
number recalculates.

Money is handled in integer cents throughout the generator; the *_EUR
constants below are convenience inputs converted to cents once, here.
"""

# ---------------------------------------------------------------------------
# Global settings
# ---------------------------------------------------------------------------

RANDOM_SEED = 42

# Actual-data observation window (in-world calendar, matches churn's universe)
OBS_START = "2024-01"
OBS_END   = "2025-12"

# Internal driver model runs from FY2023 (the budget base year for FY2024,
# never itself emitted as a table) through FY2025.
DRIVER_MODEL_START = "2023-01"
DRIVER_MODEL_END   = "2025-12"

DAYS_IN_MONTH_APPROX = 30   # declared simplification for DSO / AR roll-forward

# ---------------------------------------------------------------------------
# Company grid — the shared spine every table lives on
# ---------------------------------------------------------------------------

COMPANY_NAME = "Paju Consumer Products Oy"

BUS = ["Nordics", "Central Europe", "Baltics & Poland"]
LINES = ["Hair Care", "Skin & Body", "Home Care", "Professional"]

BU_SHARE = {
    "Nordics":          0.55,
    "Central Europe":   0.25,
    "Baltics & Poland": 0.20,
}

LINE_SHARE = {
    "Hair Care":   0.30,
    "Skin & Body": 0.28,
    "Home Care":   0.22,
    "Professional": 0.20,
}

LINE_MATERIAL_PCT_OF_NET_REVENUE = {
    "Hair Care":    0.30,
    "Skin & Body":  0.28,
    "Home Care":    0.48,   # bulk chemicals, heavy packaging
    "Professional": 0.26,
}

# ---------------------------------------------------------------------------
# Shape targets — used only to derive FY2023 base drivers,
# not validated directly (the validator checks story bands and identities,
# not the absolute revenue level).
# ---------------------------------------------------------------------------

COMPANY_FY2024_NET_REVENUE_TARGET_EUR = 152_000_000
COMPANY_FY2024_GM_TARGET     = 0.42
COMPANY_FY2024_EBITDA_TARGET = 0.11
COMPANY_FY2024_FTE_TARGET    = 480

NORMAL_ANNUAL_GROWTH_BLENDED = 0.03   # rough company-wide growth, base-year back-solve only
COMPANY_FY2023_NET_REVENUE_TARGET_EUR = (
    COMPANY_FY2024_NET_REVENUE_TARGET_EUR / (1 + NORMAL_ANNUAL_GROWTH_BLENDED)
)

# ---------------------------------------------------------------------------
# Base-year (FY2023) unit economics
# ---------------------------------------------------------------------------

LINE_BASE_LIST_PRICE_EUR_FY2023 = {
    "Hair Care":    3.80,
    "Skin & Body":  5.40,
    "Home Care":    2.60,
    "Professional": 11.50,
}
LINE_BASE_LIST_PRICE_CENTS_FY2023 = {
    line: round(price * 100) for line, price in LINE_BASE_LIST_PRICE_EUR_FY2023.items()
}

# Baseline promotional discount rate (fraction of gross revenue), by BU.
# Uniform across lines within a BU except where a story overrides it.
# Baltics & Poland's 8% baseline is deliberately S3's own starting point.
BASELINE_DISCOUNT_RATE_BY_BU = {
    "Nordics":          0.06,
    "Central Europe":   0.04,
    "Baltics & Poland": 0.08,
}

# Reference discount rate used only to derive line-level unit costs from a
# BU-invariant physical unit economics view (a bottle costs the same to make
# wherever it is sold) — the revenue-share-weighted average baseline discount.
REFERENCE_DISCOUNT_RATE = sum(
    BU_SHARE[bu] * BASELINE_DISCOUNT_RATE_BY_BU[bu] for bu in BUS
)

# Cost structure as % of net revenue-per-unit (reference basis), uniform
# across lines — material intensity is the variable that matters (see
# LINE_MATERIAL_PCT_OF_NET_REVENUE above); labour and logistics intensity are
# assumed roughly uniform across product lines.
LABOUR_PCT_OF_NET_REVENUE    = 0.150
LOGISTICS_PCT_OF_NET_REVENUE = 0.104

def _unit_net_price_cents(line: str) -> float:
    """Reference net price per unit (cents) used to derive unit costs."""
    return LINE_BASE_LIST_PRICE_CENTS_FY2023[line] * (1 - REFERENCE_DISCOUNT_RATE)

UNIT_MATERIAL_COST_CENTS_FY2023 = {
    line: round(LINE_MATERIAL_PCT_OF_NET_REVENUE[line] * _unit_net_price_cents(line))
    for line in LINES
}
UNIT_LABOUR_COST_CENTS_FY2023 = {
    line: round(LABOUR_PCT_OF_NET_REVENUE * _unit_net_price_cents(line))
    for line in LINES
}
UNIT_LOGISTICS_COST_CENTS_FY2023 = {
    line: round(LOGISTICS_PCT_OF_NET_REVENUE * _unit_net_price_cents(line))
    for line in LINES
}

# FY2023 base annual net revenue target per BU x line, and the base volume
# this implies given the base list price and BU baseline discount rate.
FY2023_NET_REVENUE_TARGET_BY_BU_LINE = {
    bu: {
        line: COMPANY_FY2023_NET_REVENUE_TARGET_EUR * BU_SHARE[bu] * LINE_SHARE[line]
        for line in LINES
    }
    for bu in BUS
}

# BASE_VOLUME_FY2023 is a *monthly* base level (the trend/seasonal formula in
# generate_financials.py multiplies it out across all 12 calendar months, and
# the seasonal index averages to 1.0 over a year) — so the annual revenue
# target is divided by 12 here before deriving volume from price and discount.
BASE_VOLUME_FY2023 = {
    bu: {
        line: round(
            (FY2023_NET_REVENUE_TARGET_BY_BU_LINE[bu][line] / 12)
            / (
                LINE_BASE_LIST_PRICE_EUR_FY2023[line]
                * (1 - BASELINE_DISCOUNT_RATE_BY_BU[bu])
            )
        )
        for line in LINES
    }
    for bu in BUS
}

# ---------------------------------------------------------------------------
# Trends (annual, compounded monthly) — the "normal" world, no stories
# ---------------------------------------------------------------------------

LINE_VOLUME_TREND_ANNUAL = {
    "Hair Care":    0.018,
    "Skin & Body":  0.018,
    "Home Care":    0.015,
    "Professional": 0.020,
}
LINE_PRICE_TREND_ANNUAL = {line: 0.015 for line in LINES}   # modest list-price inflation

MATERIAL_COST_TREND_ANNUAL  = 0.000   # deliberately flat — S1's decisive fact
LABOUR_COST_TREND_ANNUAL    = 0.020
LOGISTICS_COST_TREND_ANNUAL = 0.020

def annual_to_monthly(rate_annual: float) -> float:
    """Convert an annual growth rate to the monthly rate that compounds to it."""
    return (1 + rate_annual) ** (1 / 12) - 1

# ---------------------------------------------------------------------------
# Seasonality — identical shape every year and in the budget (rule 10)
# ---------------------------------------------------------------------------
# Hair Care and Skin & Body carry the Q4 gifting peak / Q1 trough (S4's
# mechanism); Home Care and Professional are flat. Indices average to 1.0
# across the 12 calendar months by construction.

SEASONAL_INDEX_GIFTING = {
    1: 0.78, 2: 0.88, 3: 0.92, 4: 0.95, 5: 0.98, 6: 1.01,
    7: 0.98, 8: 0.95, 9: 1.00, 10: 1.05, 11: 1.15, 12: 1.35,
}
SEASONAL_INDEX_FLAT = {m: 1.00 for m in range(1, 13)}

SEASONAL_INDEX_BY_LINE = {
    "Hair Care":    SEASONAL_INDEX_GIFTING,
    "Skin & Body":  SEASONAL_INDEX_GIFTING,
    "Home Care":    SEASONAL_INDEX_FLAT,
    "Professional": SEASONAL_INDEX_FLAT,
}

# ---------------------------------------------------------------------------
# Background month-to-month noise (±1-3% per driver)
# ---------------------------------------------------------------------------

NOISE_SIGMA_VOLUME       = 0.020
NOISE_SIGMA_PRICE        = 0.004
NOISE_SIGMA_DISCOUNT_ABS = 0.004   # absolute, in discount-rate points, clipped >= 0
NOISE_SIGMA_UNIT_COST    = 0.008
NOISE_SIGMA_OPEX         = 0.015
NOISE_SIGMA_TERMS_DAYS   = 2.0     # days, applied to effective payment terms

# ---------------------------------------------------------------------------
# Opex, headcount, tax
# ---------------------------------------------------------------------------

SM_PCT_OF_NET_REVENUE    = 0.180
ADMIN_PCT_OF_NET_REVENUE = 0.130

TOTAL_FTE_FY2023 = 470
HEADCOUNT_GROWTH_ANNUAL = 0.020   # smooth, company-wide; split across BUs by BU_SHARE

SIMPLIFIED_TAX_RATE = 0.20   # applied to positive EBITDA only — declared simplification

CASH_OPENING_EUR = 8_000_000   # company cash balance at the start of Jan 2024

# ---------------------------------------------------------------------------
# Budget assumptions — prior-year normal drivers + growth (already embedded
# in the trend model) + a small, mundane optimism bias.
# ---------------------------------------------------------------------------

BUDGET_OPTIMISM_VOLUME    = 0.006    # budget assumes slightly more volume
BUDGET_OPTIMISM_PRICE     = 0.003    # ...slightly higher price realisation
BUDGET_OPTIMISM_UNIT_COST = -0.005   # ...slightly lower unit costs
BUDGET_OPTIMISM_DISCOUNT  = -0.02    # relative reduction versus normal discount rate
BUDGET_OPTIMISM_OPEX      = -0.010   # opex assumed slightly lower than normal trend

# ---------------------------------------------------------------------------
# S1 — the mix shift that reads as input inflation (Nordics, Feb 2025 on)
# ---------------------------------------------------------------------------

S1_PARAMS = {
    "bu": "Nordics",
    "start_month": "2025-02",
    "end_month":   "2025-12",
    "home_care_volume_multiplier":  1.44,
    "skin_body_volume_multiplier":  0.85,
    "home_care_promo_discount_rate": 0.195,   # deep promo vs the 6% baseline
}

# ---------------------------------------------------------------------------
# S2 — the DSO creep behind a one-off (Central Europe, Jan-Oct 2025 drift;
# the warehouse sale-leaseback lands company-wide in April 2025)
# ---------------------------------------------------------------------------

S2_PARAMS = {
    "bu": "Central Europe",
    "primary_account": "Rheinkauf Gruppe",
    "primary_drift_start_month": "2025-01",
    "primary_drift_end_month":   "2025-06",
    "primary_terms_start_days":  45,
    "primary_terms_end_days":    105,
    "secondary_accounts": ["Delta Benelux B.V.", "Nieuwmarkt Wholesale B.V."],
    "secondary_drift_start_month": "2025-02",
    "secondary_drift_end_month":   "2025-06",
    "secondary_terms_start_days":  45,
    "secondary_terms_end_days":    65,
    "warehouse_month":          "2025-04",
    "warehouse_bu":             "Nordics",   # Tampere is a Nordics/Finnish asset
    "warehouse_proceeds_eur":   5_500_000,
    "warehouse_gain_eur":       2_200_000,
}

# ---------------------------------------------------------------------------
# S3 — growth bought with discount (Baltics & Poland, Jan 2025 on)
# ---------------------------------------------------------------------------

S3_PARAMS = {
    "bu": "Baltics & Poland",
    "start_month": "2025-01",
    "end_month":   "2025-12",
    "discount_start_rate": 0.08,
    "discount_end_rate":   0.17,
    "discount_ramp_end_month": "2025-12",   # plain linear Jan->Dec (see s3_discount_rate)
    "elasticity_h1": 10.0,        # volume multiplier lift per 1.0 of incremental discount rate
    "elasticity_h2_ratio": 0.55,  # H2 elasticity = ratio x H1 (>=30-40% weaker response)
    "concentrated_accounts": ["Balticum Retail", "Polska Handlowa Sp. z o.o.", "Sūduvos Prekyba"],
    "concentrated_discount_multiplier": 1.55,   # relative to the BU-average discount rate
}

# ---------------------------------------------------------------------------
# S4 — the January cliff that isn't (every January, by design; test case
# is January 2025). Purely structural: SEASONAL_INDEX_BY_LINE above, applied
# identically to actuals and budget. No separate overlay needed.
# ---------------------------------------------------------------------------

S4_PARAMS = {
    "test_month": "2025-01",
}

STORY_PARAMS = {
    "S1": S1_PARAMS,
    "S2": S2_PARAMS,
    "S3": S3_PARAMS,
    "S4": S4_PARAMS,
}

# ---------------------------------------------------------------------------
# Noise ledger — mundane, self-explaining, never dramatised
# ---------------------------------------------------------------------------

NOISE_EVENTS = {
    "N1": {
        # The design suggested "~EUR 150k"; reduced to keep rule 9's noise ceiling
        # (60% of the smallest story's smallest/median monthly gross-profit impact)
        # comfortably clear given S3 is a slow ramp whose first month or two is, by
        # design, a near-zero signal (see validate_financials.py rule 9 docstring).
        "bu": "Nordics",
        "month": "2024-02",
        "amount_eur": 80_000,
        "field": "logistics_cost",
        "description": "Logistics cost spike — winter storms; one month, self-correcting.",
    },
    "N2": {
        "bu": "Nordics",
        "month": "2024-09",
        "amount_eur": 90_000,
        "field": "admin_general",
        "description": "One-off recruitment and advisory costs in admin.",
    },
    "N3": {
        "bu": "Central Europe",
        "month": "2025-07",
        "list_price_multiplier": 1.02,
        "description": "Contractual price indexation — +2% list prices (positive, mundane).",
    },
}

# ---------------------------------------------------------------------------
# Customer rosters — top-10 named per BU + "Other". Fictional retailer
# names only.
# ---------------------------------------------------------------------------

CUSTOMER_ROSTER = {
    "Nordics": [
        {"name": "Norrhandel",           "share": 0.120, "channel": "Grocery retail",    "contractual_terms_days": 30},
        {"name": "Praktik Apotek",       "share": 0.090, "channel": "Pharmacy retail",   "contractual_terms_days": 30},
        {"name": "Berghav AS",           "share": 0.080, "channel": "Grocery retail",    "contractual_terms_days": 30},
        {"name": "Björkgrossisten AB",   "share": 0.070, "channel": "Grocery wholesale", "contractual_terms_days": 30},
        {"name": "Havneby Detalj A/S",   "share": 0.060, "channel": "Grocery retail",    "contractual_terms_days": 30},
        {"name": "Puolukkatori Oy",         "share": 0.050, "channel": "Grocery retail",    "contractual_terms_days": 30},
        {"name": "Solvik Dagligvaror AB","share": 0.045, "channel": "Grocery retail",    "contractual_terms_days": 30},
        {"name": "Kystvare AS",          "share": 0.040, "channel": "Grocery retail",    "contractual_terms_days": 30},
        {"name": "Nordkedjan AB",        "share": 0.035, "channel": "Grocery retail",    "contractual_terms_days": 30},
        {"name": "Kruunutukku Oy",       "share": 0.030, "channel": "Grocery wholesale", "contractual_terms_days": 30},
    ],
    "Central Europe": [
        {"name": "Rheinkauf Gruppe",           "share": 0.350, "channel": "Wholesale distributor", "contractual_terms_days": 45},
        {"name": "Vantoria Handel GmbH",       "share": 0.090, "channel": "Wholesale distributor", "contractual_terms_days": 45},
        {"name": "Bergmühle Grosshandel",      "share": 0.070, "channel": "Wholesale distributor", "contractual_terms_days": 45},
        {"name": "Delta Benelux B.V.",         "share": 0.060, "channel": "Wholesale distributor", "contractual_terms_days": 40},
        {"name": "Kronberg Drogerie GmbH",     "share": 0.050, "channel": "Drugstore retail",      "contractual_terms_days": 40},
        {"name": "Nieuwmarkt Wholesale B.V.",  "share": 0.045, "channel": "Wholesale distributor", "contractual_terms_days": 40},
        {"name": "Alpenweg Vertrieb GmbH",     "share": 0.040, "channel": "Wholesale distributor", "contractual_terms_days": 45},
        {"name": "Rheinberg Fachhandel",       "share": 0.035, "channel": "Specialist retail",     "contractual_terms_days": 40},
        {"name": "Van Lierwijk Groothandel B.V.", "share": 0.030, "channel": "Wholesale distributor", "contractual_terms_days": 40},
        {"name": "Feldkirch Distribution GmbH","share": 0.025, "channel": "Wholesale distributor", "contractual_terms_days": 45},
    ],
    "Baltics & Poland": [
        {"name": "Balticum Retail",              "share": 0.130, "channel": "Grocery retail",  "contractual_terms_days": 30},
        {"name": "Polska Handlowa Sp. z o.o.",   "share": 0.110, "channel": "Grocery retail",  "contractual_terms_days": 35},
        {"name": "Sūduvos Prekyba",               "share": 0.090, "channel": "Grocery retail",  "contractual_terms_days": 30},
        {"name": "Poznańska Grupa Detaliczna",   "share": 0.070, "channel": "Discount retail", "contractual_terms_days": 35},
        {"name": "Rīgas Mazumtirdzniecība",      "share": 0.060, "channel": "Grocery retail",  "contractual_terms_days": 30},
        {"name": "Läänemere Kaubad",             "share": 0.050, "channel": "Grocery retail",  "contractual_terms_days": 30},
        {"name": "Gdańska Sieć Detaliczna",      "share": 0.045, "channel": "Discount retail", "contractual_terms_days": 35},
        {"name": "Kauno Diskontas",              "share": 0.040, "channel": "Discount retail", "contractual_terms_days": 30},
        {"name": "Pärnu Kaubad",                 "share": 0.035, "channel": "Grocery retail",  "contractual_terms_days": 30},
        {"name": "Klaipėda Market",              "share": 0.030, "channel": "Grocery retail",  "contractual_terms_days": 30},
    ],
}

OTHER_BUCKET = {
    "Nordics":          {"channel": "Other accounts (long tail)", "contractual_terms_days": 30},
    "Central Europe":   {"channel": "Other accounts (long tail)", "contractual_terms_days": 45},
    "Baltics & Poland":  {"channel": "Other accounts (long tail)", "contractual_terms_days": 32},
}

def other_share(bu: str) -> float:
    """Residual revenue share for the "Other" bucket of a BU."""
    return 1.0 - sum(c["share"] for c in CUSTOMER_ROSTER[bu])

# ---------------------------------------------------------------------------
# Output paths (relative to the project root — resolved in each script)
# ---------------------------------------------------------------------------

OUTPUT_DATA_DIR = "data"
OUTPUT_CODE_DIR = "code"
