"""
config.py -- All tunable parameters for the Saarnitukku Oy synthetic AP ledger.

Everything that controls the shape of the data lives here. Logic lives in
generate_ledger.py (generation), rule_tests.py (the seven audit rule tests)
and validate_ledger.py (the thirteen coherence checks).

Every planted anomaly class and every declared benign item is specified here
with its exact transaction count and placement parameters, per the design's
catch matrix.
"""

import datetime

# ---------------------------------------------------------------------------
# Global settings
# ---------------------------------------------------------------------------

RANDOM_SEED = 42

COMPANY_NAME = "Saarnitukku Oy"
YEAR = 2025

TOTAL_TRANSACTIONS = 50_000
TOTAL_VENDORS = 200

# Approval tiers (declared invented convention; no authoritative Nordic norm
# exists).
APPROVAL_TIER_DEPT_HEAD_EUR = 10_000.0
APPROVAL_TIER_CFO_EUR = 50_000.0

# ---------------------------------------------------------------------------
# Date helpers used to pin exact calendar dates below (stdlib only).
# ---------------------------------------------------------------------------

def _nth_weekday(year: int, month: int, weekday: int, n: int) -> datetime.date:
    """Return the date of the nth occurrence of `weekday` (Mon=0..Sun=6) in
    the given year/month. Used to pin the W-class Saturday dates deterministically
    rather than hand-typing them."""
    d = datetime.date(year, month, 1)
    count = 0
    while True:
        if d.weekday() == weekday:
            count += 1
            if count == n:
                return d
        d += datetime.timedelta(days=1)


SATURDAY = 5

# ---------------------------------------------------------------------------
# Company calendar -- Finland, 2025 (sourced statutory calendar)
# ---------------------------------------------------------------------------
# Statutory / de-facto non-working weekdays. Weekend dates that already fall
# on statutory holidays (Midsummer Day 21 Jun (Sat), All Saints 1 Nov (Sat),
# Independence Day 6 Dec (Sat)) carry zero incremental signal and are not
# listed separately -- the weekend flag already covers them.

HOLIDAYS_2025 = {
    datetime.date(2025, 1, 1): "Uudenvuodenpäivä (New Year's Day)",
    datetime.date(2025, 1, 6): "Loppiainen (Epiphany)",
    datetime.date(2025, 4, 18): "Pitkäperjantai (Good Friday)",
    datetime.date(2025, 4, 21): "2. pääsiäispäivä (Easter Monday)",
    datetime.date(2025, 5, 1): "Vappu (May Day)",
    datetime.date(2025, 5, 29): "Helatorstai (Ascension Day)",
    datetime.date(2025, 6, 20): "Juhannusaatto (Midsummer Eve, de facto non-working)",
    datetime.date(2025, 12, 24): "Jouluaatto (Christmas Eve, de facto non-working)",
    datetime.date(2025, 12, 25): "Joulupäivä (Christmas Day)",
    datetime.date(2025, 12, 26): "Tapaninpäivä (Boxing Day)",
}

# ---------------------------------------------------------------------------
# Posting roster
# ---------------------------------------------------------------------------

INTEGRATION_USER = "INTEG-01"
INTEGRATION_SHARE = 0.82  # target fraction of all rows posted by the integration (design: 80-85%)

# Six named AP staff. U-117, U-204 and U-031 carry designed plants (W, A, B2
# respectively); the other three are ordinary staff with no planted signal.
HUMAN_USERS = ["U-117", "U-204", "U-031", "U-058", "U-142", "U-176"]

# Posting lag (coherence rule 13). INTEG-01 lag is modelled in plain
# calendar days (0 or 1) because integration batches are not constrained to
# working days at all; human lag is modelled in business days (skips
# weekends/holidays) because human posting happens inside office workflows.
INTEGRATION_LAG_CALENDAR_DAYS = (0, 1)
HUMAN_LAG_BUSINESS_DAYS = (2, 3, 4, 5)

# ---------------------------------------------------------------------------
# Payment terms
# ---------------------------------------------------------------------------

TERMS_DAYS_OPTIONS = [14, 21, 30]
TERMS_DAYS_WEIGHTS = [0.40, 0.30, 0.30]

# ---------------------------------------------------------------------------
# Chart of accounts (~40 rows, anchored to Kirjanpitoasetus expense-by-nature
# ranges).
# ---------------------------------------------------------------------------
# Columns: account, name_fi, name_en, class

CHART_OF_ACCOUNTS = [
    # Fixed assets (1xxx)
    ("1100", "Rakennukset ja rakennelmat", "Buildings and structures", "fixed_asset"),
    ("1150", "Keskeneräiset hankinnat", "Assets under construction", "fixed_asset"),
    ("1200", "Koneet ja kalusto", "Machinery and equipment", "fixed_asset"),
    ("1300", "Kuljetusvälineet", "Vehicles", "fixed_asset"),
    ("1400", "Muut aineelliset hyödykkeet", "Other tangible assets", "fixed_asset"),
    ("1500", "Aineettomat oikeudet", "Intangible rights", "fixed_asset"),
    # Purchases (4000-4399)
    ("4000", "Ostot kotimaasta", "Domestic purchases", "purchases"),
    ("4010", "Ostot ulkomailta", "Foreign purchases", "purchases"),
    ("4020", "Pakkausmateriaalit", "Packaging materials", "purchases"),
    ("4100", "Teräs- ja metallituotteet", "Steel and metal products", "purchases"),
    ("4110", "Tiivisteet ja komponentit", "Seals and components", "purchases"),
    ("4200", "Työkalut ja tarvikkeet", "Tools and supplies", "purchases"),
    ("4210", "Suojavarusteet", "Protective equipment", "purchases"),
    ("4300", "Kunnossapitotarvikkeet", "Maintenance supplies", "purchases"),
    ("4310", "Varaosat", "Spare parts", "purchases"),
    ("4390", "Muut ostot", "Other purchases", "purchases"),
    # External services (4400-4499)
    ("4410", "Rahtikulut", "Freight costs", "external_services"),
    ("4420", "Alihankinta", "Subcontracting", "external_services"),
    ("4430", "Konsultointipalvelut", "Consulting services", "external_services"),
    ("4440", "Muut ulkopuoliset palvelut", "Other external services", "external_services"),
    # Personnel (5xxx-6xxx) -- not used by the AP vendor ledger; present for
    # chart-of-accounts realism and referential-integrity completeness only.
    ("5100", "Palkat", "Wages", "personnel"),
    ("5200", "Henkilösivukulut", "Payroll overheads", "personnel"),
    ("6100", "Eläkevakuutusmaksut", "Pension insurance contributions", "personnel"),
    ("6200", "Muut henkilöstökulut", "Other personnel costs", "personnel"),
    # Other operating costs (7xxx+)
    ("7000", "Toimitilavuokrat", "Premises rent", "other_operating"),
    ("7100", "Markkinointi", "Marketing", "other_operating"),
    ("7150", "Messut ja näyttelyt", "Trade fairs and exhibitions", "other_operating"),
    ("7200", "IT-palvelut", "IT services", "other_operating"),
    ("7250", "Ohjelmistolisenssit", "Software licences", "other_operating"),
    ("7300", "Vakuutukset", "Insurance", "other_operating"),
    ("7400", "Puhelin- ja tietoliikennekulut", "Telecom costs", "other_operating"),
    ("7450", "Postikulut", "Postal costs", "other_operating"),
    ("7500", "Toimistotarvikkeet", "Office supplies", "other_operating"),
    ("7600", "Matkakulut", "Travel costs", "other_operating"),
    ("7700", "Edustuskulut", "Representation costs", "other_operating"),
    ("7800", "Siivous- ja jätehuoltopalvelut", "Cleaning and waste services", "other_operating"),
    ("7850", "Turvallisuuspalvelut", "Security services", "other_operating"),
    ("7900", "Energia ja vesi", "Energy and water", "other_operating"),
    ("7990", "Muut liiketoiminnan kulut", "Other operating expenses", "other_operating"),
]

# Account pools used when assigning "allowed_accounts" to generic vendors,
# by vendor category (see GENERIC_VENDOR_CATEGORIES below).
ACCOUNTS_GOODS_SMALL = ["4000", "4020", "4200", "4210", "4300"]
ACCOUNTS_GOODS_BULK = ["4010", "4100", "4110", "4310"]
ACCOUNTS_EXTERNAL_SERVICES = ["4410", "4420", "4430", "4440"]
ACCOUNTS_OTHER_OPERATING = [
    "7000", "7100", "7150", "7200", "7250", "7300",
    "7400", "7450", "7500", "7600", "7700", "7800", "7850", "7900", "7990",
]

# Reserved accounts for named story items / benign items
ACCOUNT_TERASKONTIO = "4100"          # steel and metal products
ACCOUNT_KUORMARAITTI = "4410"         # freight costs
ACCOUNT_KARRENBACH = "4110"           # seals and components
ACCOUNT_KAARNIALA_CORRECT = "7100"    # marketing (the account it should use)
ACCOUNT_KAARNIALA_MISPOST = "7200"    # IT services (where it is wrongly posted)
ACCOUNT_NEUVANTILA = "4430"           # consulting services
ACCOUNT_B1_RENT = "7000"              # premises rent
ACCOUNT_B2_INVENTORY = "4420"         # subcontracting (inventory-count labour)
ACCOUNT_B4_CAPEX = "1200"             # machinery and equipment
ACCOUNT_B5_INSURANCE = "7300"         # insurance

# ---------------------------------------------------------------------------
# Vendor master -- countries, VAT/IBAN formats, naming scheme
# ---------------------------------------------------------------------------

COUNTRY_WEIGHTS = {"FI": 0.80, "SE": 0.07, "DE": 0.07, "NO": 0.04, "EE": 0.02}

# Combinatorial Finnish naming scheme for the ~193 generic-scheme vendors
# ("common-noun compounds + standard suffixes").
GENERIC_NAME_PREFIXES = [
    "Rauta", "Pultti", "Ruuvi", "Metalli", "Kone", "Tekno", "Varaosa", "Tarvike",
    "Huolto", "Laatu", "Piste", "Verkko", "Pinta", "Kulma", "Runko", "Voima",
    "Kanta", "Pora", "Säiliö", "Vaunu", "Silta", "Portti", "Vasara", "Lanka",
    "Kaapeli", "Putki", "Levy", "Muovi", "Kumi", "Suoja", "Turva", "Palkki",
    "Laakeri", "Hitsi", "Kotelo", "Akseli", "Ratas", "Kisko", "Kaira", "Nosto",
]
GENERIC_NAME_MID = [
    "tukku", "tarvike", "komponentti", "huolto", "varaosa", "palvelu",
    "logistiikka", "tekniikka", "väline", "materiaali", "asennus", "järjestelmä",
]
GENERIC_NAME_SUFFIXES_FI = ["Oy", "Oy Ab", "Ky", "Tmi"]

# Non-Finnish generic vendor naming (kept simple: combinatorial too)
GENERIC_NAME_PREFIXES_INTL = {
    "SE": ["Nord", "Bergs", "Sjo", "Malm", "Stal", "Verktygs"],
    "DE": ["Stahl", "Werk", "Technik", "Metall", "Bau", "Industrie"],
    "NO": ["Fjord", "Stal", "Verktoy", "Nord", "Bergen"],
    "EE": ["Tera", "Metalli", "Tehnika", "Varu"],
}
GENERIC_NAME_MID_INTL = {
    "SE": ["handel", "teknik", "grossist"],
    "DE": ["technik GmbH", "handel GmbH", "vertrieb GmbH"],
    "NO": ["handel AS", "teknikk AS"],
    "EE": ["Grupp", "Tarned"],
}
COUNTRY_SUFFIXES = {"SE": "AB", "DE": "GmbH", "NO": "AS", "EE": "OU"}

# Name policy.
# The bare generic names above ("Felsmark Metalltechnik GmbH", "Skavlund Fjordhandel AS") are the kind of name the
# national registers routinely hold, so every international generic vendor gets a coined stem in
# front. The stem is applied AFTER the pool draw, so the random stream and every draw order are
# unchanged: the dataset is the same dataset with different names.
GENERIC_NAME_STEMS_INTL = {
    "DE": ["Felsmark", "Erlengrund"],
    "NO": ["Skavlund", "Fjellskor"],
    "SE": ["Myrkvarn", "Hällsvik"],
    "EE": ["Kuuseoru", "Pihlakoru"],
}
# Stems pinned by drawn name (the three that appear on the website explorer).
# Keys are the names as drawn from the pool, before the stem is added.
GENERIC_NAME_STEM_PINS_INTL = {
    "Metalltechnik GmbH": "Felsmark",
    "Stahltechnik GmbH": "Erlengrund",
    "Industriehandel GmbH": "Felsmark",
}
# Published names pinned by vendor id, applied after the draw so no random
# draw changes. Keyed by vendor id so the drawn names they replace are not
# repeated here.
GENERIC_NAME_PINS_BY_VENDOR_ID = {
    "V-0043": "Putkiaihio Oy",
    "V-0051": "Kehystukku Oy",
    "V-0120": "Kumivaraosa Tmi",
    "V-0157": "Kumivaraosa Oy Ab",
}
# VAT ids pinned by vendor id (drawn values that happened to be real,
# checksum-valid register entries are replaced after the draw).
VAT_ID_PINS_BY_VENDOR_ID = {
    "V-0031": "SE194848890201",
    "V-0050": "FI30898203",
    "V-0057": "NO522209954MVA",
    "V-0063": "SE654684068501",
    "V-0068": "EE809830673",
    "V-0160": "NO005837236MVA",
    "V-0178": "DE658604423",
}
# Invented bank codes: the start of every drawn BBAN is overwritten with this
# prefix and the IBAN check digits are recomputed (mod 97), so every IBAN is
# checksum-valid but carries a bank code no real bank uses.
FICTIONAL_BANK_PREFIX = {"FI": "999", "SE": "999", "DE": "99999999", "NO": "9999", "EE": "99"}


def apply_generic_name_policy(name: str, country: str) -> str:
    """Return the published name for a drawn generic-scheme name (see the block above).

    International names get a coined stem in front; the stem is the pinned one if the name is
    pinned, otherwise chosen by a stable checksum of the drawn name. Finnish names are kept as
    drawn here; per-vendor pins (GENERIC_NAME_PINS_BY_VENDOR_ID) are applied by the caller."""
    import zlib
    if country == "FI":
        return name
    stems = GENERIC_NAME_STEMS_INTL[country]
    stem = GENERIC_NAME_STEM_PINS_INTL.get(name)
    if stem is None:
        stem = stems[zlib.crc32(name.encode("utf-8")) % len(stems)]
    return f"{stem} {name}"

# Street/city components for deterministic address generation
ADDRESS_STREETS_FI = [
    "Esimerkkikatu", "Esimerkkikatu", "Esimerkkikatu", "Esimerkkikatu", "Esimerkkikatu",
    "Esimerkkikatu", "Esimerkkikatu", "Esimerkkikatu", "Esimerkkikatu", "Esimerkkikatu",
]
ADDRESS_CITIES_FI = ["Vantaa", "Helsinki", "Tampere", "Turku", "Kuopio", "Lahti", "Oulu", "Jyväskylä"]
ADDRESS_STREETS_INTL = {
    "SE": ["Exempelgatan", "Exempelgatan", "Exempelgatan"],
    "DE": ["Beispielstraße", "Beispielstraße", "Beispielstraße"],
    "NO": ["Eksempelveien", "Eksempelveien"],
    "EE": ["Näidise tn", "Näidise tn"],
}
ADDRESS_CITIES_INTL = {
    "SE": ["Göteborg", "Malmö", "Norrköping"],
    "DE": ["Hamburg", "Bremen", "Dortmund"],
    "NO": ["Bergen", "Drammen"],
    "EE": ["Tallinn", "Tartu"],
}

# ---------------------------------------------------------------------------
# Generic vendor archetype categories (pure-filler + plant-host vendors)
# ---------------------------------------------------------------------------
# amount_mean / amount_cv parameterise a lognormal draw (cv = coefficient of
# variation). monthly_rate_mean parameterises a per-vendor Gamma-distributed
# base rate (right-skewed: a handful of vendors carry most of the volume,
# "concentrated in core suppliers").

GENERIC_VENDOR_CATEGORIES = {
    "goods_small": {
        "weight": 0.35,
        "accounts": ACCOUNTS_GOODS_SMALL,
        "amount_mean": 650.0,
        "amount_cv": 0.55,
        "monthly_rate_mean": 32.0,
        "monthly_rate_gamma_shape": 1.4,
    },
    "goods_bulk": {
        "weight": 0.12,
        "accounts": ACCOUNTS_GOODS_BULK,
        "amount_mean": 3300.0,
        "amount_cv": 0.35,
        "monthly_rate_mean": 18.0,
        "monthly_rate_gamma_shape": 1.4,
    },
    "external_services": {
        "weight": 0.20,
        "accounts": ACCOUNTS_EXTERNAL_SERVICES,
        "amount_mean": 1900.0,
        "amount_cv": 0.50,
        "monthly_rate_mean": 23.0,
        "monthly_rate_gamma_shape": 1.3,
    },
    "other_operating": {
        "weight": 0.23,
        "accounts": ACCOUNTS_OTHER_OPERATING,
        "amount_mean": 950.0,
        "amount_cv": 0.60,
        "monthly_rate_mean": 20.0,
        "monthly_rate_gamma_shape": 1.3,
    },
    "sparse_rare": {
        "weight": 0.10,
        "accounts": ACCOUNTS_GOODS_SMALL + ACCOUNTS_EXTERNAL_SERVICES + ACCOUNTS_OTHER_OPERATING,
        "amount_mean": 2600.0,
        "amount_cv": 0.65,
        "monthly_rate_mean": 4.0,
        "monthly_rate_gamma_shape": 1.2,
    },
}

# Probability a generic vendor gets a second allowed account (realism only)
SECOND_ACCOUNT_PROBABILITY = 0.15

# Cap on per-vendor monthly rate draw (avoids pathological single-vendor volume)
MONTHLY_RATE_CLIP_MAX = 110.0

# Number of the busiest pure-filler vendors that share the deterministic
# exact-count adjustment (spreads the delta rather than dumping it on one).
N_FLEX_VENDORS = 8

# ---------------------------------------------------------------------------
# Seasonality -- monthly volume multipliers (Nov-Dec peak
# ~x1.3, Jul trough ~x0.7).
# ---------------------------------------------------------------------------

MONTH_SEASONALITY_WEIGHT = {
    1: 0.95, 2: 0.95, 3: 1.00, 4: 1.00, 5: 1.00, 6: 0.95,
    7: 0.70, 8: 0.90, 9: 1.00, 10: 1.05, 11: 1.30, 12: 1.30,
}

FINNISH_MONTH_NAMES = {
    1: "tammikuu", 2: "helmikuu", 3: "maaliskuu", 4: "huhtikuu",
    5: "toukokuu", 6: "kesäkuu", 7: "heinäkuu", 8: "elokuu",
    9: "syyskuu", 10: "lokakuu", 11: "marraskuu", 12: "joulukuu",
}

# ---------------------------------------------------------------------------
# Rule-test parameters -- pinned here so generate_ledger.py
# and rule_tests.py share one source of truth for the numeric thresholds.
# ---------------------------------------------------------------------------

RULE_DUPLICATE_MAX_GAP_DAYS = 7
RULE_ROUND_SUM_MULTIPLE = 1000.0
RULE_ROUND_SUM_MIN_EUR = 2000.0
RULE_NEAR_THRESHOLD_LOW = 9500.0
RULE_NEAR_THRESHOLD_HIGH = 10000.0  # exclusive
RULE_SPLIT_MAX_WINDOW_DAYS = 3
RULE_SPLIT_MIN_PART_EUR = 4000.0
RULE_SPLIT_MAX_PART_EUR = 10000.0  # exclusive
RULE_SPLIT_MIN_SUM_EUR = 10000.0

# Pre-registered per-test flag counts (the design's catch matrix).
# validate_ledger.py rule 9 asserts the rule engine reproduces this exactly.
PREREGISTERED_TEST_COUNTS = {
    "duplicate": 14,
    "round_sum": 18,
    "near_threshold": 4,
    "split": 10,
    "calendar": 10,
    "mapping": 8,
    "name_hygiene": 0,
}

# ---------------------------------------------------------------------------
# Planted anomaly classes -- per-class transaction counts (the catch matrix)
# ---------------------------------------------------------------------------

PLANTED_CLASS_COUNTS = {
    "D": 12,   # duplicate invoices
    "R": 10,   # round sums near the tier
    "W": 8,    # non-working-day postings
    "V": 15,   # vendor name variants
    "A": 8,    # mis-posted account
    "G": 12,   # gradual drift (elevated H2 invoices only)
    "S": 10,   # split purchases
    "C": 12,   # the ceiling
}
TOTAL_ANOMALOUS_TRANSACTIONS = 87  # sum of the above -- checked in validate_ledger.py

BENIGN_ITEM_COUNTS = {
    "B1": 12,  # landlord rent, monthly
    "B2": 2,   # inventory-count Saturday overtime
    "B3": 2,   # coincidental equal-amount pair
    "B4": 1,   # one-off capex
    "B5": 1,   # annual insurance premium
    # B6 (December procurement peak) is a declared pattern, not itemised --
    # it rides on MONTH_SEASONALITY_WEIGHT and carries no dedicated txn_ids.
}
TOTAL_BENIGN_ITEMISED_TRANSACTIONS = 18

# ---------------------------------------------------------------------------
# Story vendor: Teräskontio Oy -- the gradual-drift exemplum (class G)
# ---------------------------------------------------------------------------
# 2 invoices/month, 24 for the year. H1 (Jan-Jun) is the clean baseline with
# tight variance; H2 (Jul-Dec) carries the +8% step (freight bundled in) and
# a further +2%/month compounding creep -- December ~= +19% over baseline.

TERASKONTIO_VENDOR_ID = "V-0001"
TERASKONTIO_NAME = "Teräskontio Oy"
TERASKONTIO_TERMS_DAYS = 30
TERASKONTIO_INVOICE_DAYS = [8, 22]  # two fixed invoice days per month
TERASKONTIO_INVOICES_PER_MONTH = 2
TERASKONTIO_BASELINE_MEAN_EUR = 11_000.0
TERASKONTIO_BASELINE_SIGMA_FRAC = 0.03      # sigma as a fraction of the mean (pinned tight by design)
TERASKONTIO_STEP_FRACTION = 0.08            # +8% step from July
TERASKONTIO_MONTHLY_COMPOUND_FRACTION = 0.02  # further +2%/month compounding on top of the step
TERASKONTIO_MEMO_BREADCRUMB = "sis. rahtikulut"

# ---------------------------------------------------------------------------
# Story vendor: Kuormaraitti Oy -- the freight mirror (supports class G;
# not itself a separate anomalous class -- its decline is recorded as
# corroborating evidence in the G answer-key row).
# ---------------------------------------------------------------------------
# Kuormaraitti is modelled as a single-purpose freight carrier for the
# Teräskontio lane in this ledger (smallest reasonable choice -- the design
# gives it no other role). Its H2 billing declines by
# approximately Teräskontio's step portion in euros, held within a tolerance
# band the validator checks (coherence rule 8).

KUORMARAITTI_VENDOR_ID = "V-0002"
KUORMARAITTI_NAME = "Kuormaraitti Oy"
KUORMARAITTI_TERMS_DAYS = 14
KUORMARAITTI_INVOICE_DAYS = [5, 19]  # offset from Teräskontio's dates so the two look independent
KUORMARAITTI_INVOICES_PER_MONTH = 2
KUORMARAITTI_BASELINE_MEAN_EUR = 2_400.0
KUORMARAITTI_SIGMA_FRAC = 0.07
# Step-euro amount is derived at generation time as
# TERASKONTIO_BASELINE_MEAN_EUR * TERASKONTIO_STEP_FRACTION so the two
# vendors' figures are mechanically linked, not independently typed in twice.
KUORMARAITTI_RECONCILIATION_TOLERANCE_FRAC = 0.15  # +/-15% band, coherence rule 8

# ---------------------------------------------------------------------------
# Story vendor trio: Kaerrenbach/Karrenbach Dichtungstechnik -- class V
# ---------------------------------------------------------------------------
# Three master records for one real supplier: shared VAT id and address,
# distinct IBANs, byte-distinct spellings (so the exact-name-hygiene test
# scores zero on purpose, by design).

KARRENBACH_RECORDS = [
    {"vendor_id": "V-0003", "name": "Kärrenbach Dichtungstechnik GmbH", "n_invoices": 7, "iban_seed": 1},
    {"vendor_id": "V-0004", "name": "Kaerrenbach Dichtungstechnik GmbH", "n_invoices": 5, "iban_seed": 2},
    {"vendor_id": "V-0005", "name": "KARRENBACH DICHTUNGSTECHNIK GMBH", "n_invoices": 3, "iban_seed": 3},
]
KARRENBACH_SHARED_VAT_ID = "DE199283746"
KARRENBACH_SHARED_ADDRESS = "Beispielstraße 14, 22525 Hamburg, Germany"
KARRENBACH_AMOUNT_MEAN_EUR = 3_100.0
KARRENBACH_AMOUNT_CV = 0.35
KARRENBACH_TERMS_DAYS = 30

# ---------------------------------------------------------------------------
# Story vendor: Mainostoimisto Kaarniala Oy -- mis-posted account (class A)
# ---------------------------------------------------------------------------
# Smallest reasonable choice: Kaarniala's entire annual invoice history IS
# the 8 planted transactions (no undeclared "normal" baseline invented
# beyond what the design states). All 8 are posted to the IT-services
# account instead of the marketing account, Sep-Oct, by U-204.

KAARNIALA_VENDOR_ID = "V-0006"
KAARNIALA_NAME = "Mainostoimisto Kaarniala Oy"
KAARNIALA_N_INVOICES = 8
KAARNIALA_AMOUNT_MIN_EUR = 2_000.0
KAARNIALA_AMOUNT_MAX_EUR = 6_000.0
KAARNIALA_POSTED_BY = "U-204"
KAARNIALA_MONTHS = [9, 10]
KAARNIALA_TERMS_DAYS = 21
KAARNIALA_DAYS_SEP = [3, 10, 17, 24]
KAARNIALA_DAYS_OCT = [1, 8, 15, 22]

# ---------------------------------------------------------------------------
# Story vendor: Neuvantila Oy -- the ceiling class (class C)
# ---------------------------------------------------------------------------

NEUVANTILA_VENDOR_ID = "V-0007"
NEUVANTILA_NAME = "Neuvantila Oy"
NEUVANTILA_N_INVOICES = 12  # one per month
NEUVANTILA_AMOUNT_MIN_EUR = 3_800.0
NEUVANTILA_AMOUNT_MAX_EUR = 5_600.0
NEUVANTILA_TERMS_DAYS = 14
NEUVANTILA_DAY_OF_MONTH = 15  # snapped to the nearest working day per month

# ---------------------------------------------------------------------------
# Reserved generic-scheme vendors carrying plants: D, R, S, B1, B2, B3, B4, B5
# ---------------------------------------------------------------------------
# These draw their names from the same generic combinatorial scheme as the
# pure-filler vendors (only story-carrying vendors named in
# prose get individually checked names). vendor_id values are reserved next
# in sequence after the seven story vendors above.

# Duplicate invoices (class D): 6 pairs, 3 vendors (2 pairs each).
D_VENDOR_IDS = ["V-0008", "V-0009", "V-0010"]
D_PAIR_GAP_DAYS = [4, 5, 6, 7, 5, 6]  # posting_date gap per pair, cycling within the 4-7 day band
D_PAIR_MONTHS = [2, 4, 6, 8, 10, 12]  # one pair every other month
D_PAIR_BASE_AMOUNTS_EUR = [842.50, 1_365.00, 2_940.75, 615.20, 3_780.60, 1_120.35]

# Round sums near the tier (class R): 2 vendors.
R_ROUND_VENDOR_ID = "V-0011"     # carries the 6 round-multiple invoices
R_NEAR_VENDOR_ID = "V-0012"      # carries the 4 near-threshold invoices
R_ROUND_AMOUNTS_EUR = [5_000.0, 6_000.0, 7_000.0, 8_000.0, 9_000.0, 6_000.0]
R_ROUND_MONTHS = [1, 3, 5, 7, 9, 11]
R_NEAR_THRESHOLD_AMOUNTS_EUR = [9_712.45, 9_580.10, 9_899.99, 9_650.75]
R_NEAR_THRESHOLD_MONTHS = [2, 5, 8, 11]

# Split purchases (class S): 5 events, 3 vendors (2, 2, 1 events).
S_VENDOR_IDS = ["V-0013", "V-0014", "V-0015"]
S_EVENTS = [
    # (vendor_id index into S_VENDOR_IDS, month, day-offset between the two parts, part_a_eur, part_b_eur)
    {"vendor_ix": 0, "month": 1, "offset_days": 2, "part_a_eur": 5_820.40, "part_b_eur": 5_495.10},
    {"vendor_ix": 0, "month": 7, "offset_days": 1, "part_a_eur": 6_340.25, "part_b_eur": 6_910.80},
    {"vendor_ix": 1, "month": 4, "offset_days": 3, "part_a_eur": 4_780.60, "part_b_eur": 6_255.90},
    {"vendor_ix": 1, "month": 10, "offset_days": 2, "part_a_eur": 7_120.15, "part_b_eur": 4_610.35},
    {"vendor_ix": 2, "month": 9, "offset_days": 1, "part_a_eur": 5_990.00 + 0.55, "part_b_eur": 7_340.20},
]

# Benign B1 -- landlord rent, exact, monthly. Name is hand-picked (rather than
# drawn from the generic pool) so it reads as a property company, per the
# design's "generic-scheme name" requirement -- still an ordinary combinatorial
# construction, just chosen rather than randomised.
B1_VENDOR_ID = "V-0016"
B1_VENDOR_NAME = "Kiinteistö Oy Vantaan Teollisuustalo"
B1_MONTHLY_RENT_EUR = 15_000.00

# Benign B2 -- inventory-count Saturday overtime (a staffing/labour vendor).
B2_VENDOR_ID = "V-0017"
B2_VENDOR_NAME = "Varastopalvelu Toivanen Ky"
B2_DATE = datetime.date(2025, 11, 15)
B2_POSTED_BY = "U-031"
B2_AMOUNTS_EUR = [1_840.00 + 0.35, 1_260.00 + 0.80]
B2_MEMO = "Sovittu ylityö, inventaario 15.11.2025"

# Benign B3 -- coincidental equal-amount pair, genuinely distinct deliveries.
B3_VENDOR_ID = "V-0018"
B3_VENDOR_NAME = "Ruuvitukku Halonen Oy"
B3_AMOUNT_EUR = 7_420.00
B3_GAP_DAYS = 4
B3_MONTH = 6
B3_PO_REFS = ["PO-48213", "PO-48297"]

# Benign B4 -- one-off capex (a machinery supplier).
B4_VENDOR_ID = "V-0019"
B4_VENDOR_NAME = "Konepaja Ristimäki Oy"
B4_AMOUNT_EUR = 78_400.00
B4_MONTH = 10
B4_DAY_OF_MONTH = 15  # snapped to the nearest working day
B4_TERMS_DAYS = 30
B4_POSTED_BY = "U-058"

# Benign B5 -- annual insurance premium.
B5_VENDOR_ID = "V-0020"
B5_VENDOR_NAME = "Varpuniemen Vakuutuspalvelu Oy"
B5_AMOUNT_EUR = 24_600.00
B5_MONTH = 1
B5_DAY_OF_MONTH = 15  # snapped to the nearest working day
B5_TERMS_DAYS = 30
B5_POSTED_BY = "U-058"

# W-class (non-working-day postings): 8 postings by U-117, Feb-Jun.
W_POSTED_BY = "U-117"
W_DATES = (
    [_nth_weekday(YEAR, m, SATURDAY, 2) for m in (2, 3, 4, 5, 6)]
    + [datetime.date(2025, 4, 21), datetime.date(2025, 5, 29), datetime.date(2025, 6, 20)]
)
W_LAG_BUSINESS_DAYS = 3  # within the human 2-5 range, used to back-derive invoice_date

# First reserved vendor id available to the generic vendor pool (pure fillers
# start numbering after all of the above reservations).
FIRST_GENERIC_POOL_VENDOR_INDEX = 21  # V-0021 .. V-0200

# Fixed allowed_accounts for the 13 reserved generic-scheme vendors (V-0008..
# V-0020). These are pinned directly rather than drawn from a category pool
# because each carries a specific plant with its own generation path.
RESERVED_VENDOR_ACCOUNTS = {
    "V-0008": ["4000"],   # D vendor 1
    "V-0009": ["4200"],   # D vendor 2
    "V-0010": ["4300"],   # D vendor 3
    "V-0011": ["4100"],   # R round-sum vendor
    "V-0012": ["4410"],   # R near-threshold vendor
    "V-0013": ["4110"],   # S vendor 1
    "V-0014": ["4310"],   # S vendor 2
    "V-0015": ["4420"],   # S vendor 3
    "V-0016": [ACCOUNT_B1_RENT],
    "V-0017": [ACCOUNT_B2_INVENTORY],
    "V-0018": ["4200"],   # B3
    "V-0019": [ACCOUNT_B4_CAPEX],
    "V-0020": [ACCOUNT_B5_INSURANCE],
}
RESERVED_VENDOR_IDS = list(RESERVED_VENDOR_ACCOUNTS.keys())
RESERVED_VENDOR_NAME_OVERRIDES = {
    "V-0016": B1_VENDOR_NAME,
    "V-0017": B2_VENDOR_NAME,
    "V-0018": B3_VENDOR_NAME,
    "V-0019": B4_VENDOR_NAME,
    "V-0020": B5_VENDOR_NAME,
}

# ---------------------------------------------------------------------------
# Memo templates (deterministic, Finnish)
# ---------------------------------------------------------------------------

MEMO_TEMPLATES_BY_CATEGORY = {
    "goods_small": "Tavarantoimitus, tilaus {ref}",
    "goods_bulk": "Materiaalitoimitus, tilaus {ref}",
    "external_services": "Palvelulasku, {ref}",
    "other_operating": "Ostolasku, {ref}",
    "sparse_rare": "Kertatoimitus, tilaus {ref}",
}
MEMO_TERASKONTIO_H1 = "Terästoimitus, tilaus {ref}"
MEMO_TERASKONTIO_H2 = "Terästoimitus, sis. rahtikulut, tilaus {ref}"
MEMO_KUORMARAITTI = "Rahtikuljetus, Teräskontio-erät, tilaus {ref}"
MEMO_KARRENBACH = "Tiivistetoimitus, tilaus {ref}"
MEMO_KAARNIALA = "Mainoskampanja, {month_fi} 2025"
MEMO_NEUVANTILA = "Konsultointipalvelu, {month_fi} 2025"
MEMO_B1_RENT = "Toimitilavuokra, {month_fi} 2025"
MEMO_B4_CAPEX = "Konehankinta, kalusto"
MEMO_B5_INSURANCE = "Vuosivakuutusmaksu 2025"
MEMO_D_GENERIC = "Ostolasku, tilaus {ref}"
MEMO_R_GENERIC = "Ostolasku, tilaus {ref}"
MEMO_S_GENERIC = "Ostolasku, osatoimitus {ref}"
MEMO_B3_GENERIC = "Tavarantoimitus, {po_ref}"

# ---------------------------------------------------------------------------
# Output paths (relative to the project root -- resolved in each script)
# ---------------------------------------------------------------------------

OUTPUT_DATA_DIR = "data"
OUTPUT_ANSWER_KEY_DIR = "data/answer_key"
