"""Configuration for the Tuomimetsa Oy warehouse generator (Project 11, Phase 2).

Every tunable lives here: RANDOM_SEED, the fiscal calendar, the 40 stores and
their dated history, the product blueprint (subcategories, prices, margins,
seasonality), member and campaign parameters, web-order behaviour, return and
stock behaviour, the four undocumented incidents, and the time-zone trap days.
generate_warehouse.py reads this module and invents no identity, history or
trap data of its own.

Per the Hapax core generation pattern: this module controls STRUCTURE only.
There is no prose here except short labels (store names, campaign names).
The in-world documents (world/) are written separately under brief
discipline from the facts in facts.yaml, which build_facts.py derives from
this file, so a date or rate changed here changes the facts and the data
together.

Collision check (16 Oct 2026, trade register open data and web search): no registered
company or retail brand is called "Tuomimetsa Oy", and no registered name
contains it. Product brand
names below are invented. "Ruska" (an Arabia tableware line) and "Pihlaja"
(a Fazer confectionery line) were found by the same check and dropped.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Global
# ---------------------------------------------------------------------------

RANDOM_SEED = 42  # every RNG draw is derived from this plus a per-section salt

CASE_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = CASE_ROOT / "data"
WAREHOUSE_DIR = DATA_DIR / "warehouse"
WAREHOUSE_PATH = WAREHOUSE_DIR / "tuomimetsa.duckdb"
MANIFEST_PATH = WAREHOUSE_DIR / "warehouse_manifest.json"
INTERNAL_DIR = DATA_DIR / "internal"          # held out: clean tables, incident manifest
FACTS_PATH = DATA_DIR / "facts.yaml"          # structured facts, one ID per fact
WORLD_DIR = CASE_ROOT / "world"               # the in-world documents (the only builder input)
WORLD_TEMPLATE_DIR = CASE_ROOT / "code" / "world_templates"
VALIDATION_REPORT_PATH = DATA_DIR / "validation_report.json"

# ---------------------------------------------------------------------------
# Window and fiscal calendar
# ---------------------------------------------------------------------------

WINDOW_START = date(2024, 4, 29)     # Monday, first day of FY2024/25
WINDOW_END = date(2026, 10, 4)       # Sunday, end of FY2026/27 week 22

# Fiscal year starts (the Monday nearest 1 May) and week counts.
FISCAL_YEAR_STARTS = {2024: date(2024, 4, 29), 2025: date(2025, 4, 28), 2026: date(2026, 5, 4)}
FISCAL_YEAR_WEEKS = {2024: 52, 2025: 53, 2026: 52}
PERIOD_WEEKS_445 = [4, 4, 5, 4, 4, 5, 4, 4, 5, 4, 4, 5]   # 12 periods, 52 weeks; week 53 joins period 12

REGION_REORG_DATE = date(2025, 4, 28)        # start of FY2025/26
CATEGORY_MOVE_DATE = date(2025, 10, 27)      # FY2025/26 period 7, week 27
MIGRATION_DATE = date(2025, 11, 3)           # web-platform migration
VAT_CHANGE_DATE = date(2024, 9, 1)
VAT_RATES_BP = {"standard_before": 2400, "standard_after": 2550, "reduced14": 1400, "reduced10": 1000}
FIRST_VERSION_VALID_FROM = date(2000, 1, 1)  # earliest valid_from for entities that pre-date the window
OPEN_ENDED_DATE = date(9999, 12, 31)

# Days on which the stores are shut (statutory closing days). Web dispatch also pauses.
STORE_CLOSED_HOLIDAYS = [
    "New Year's Day", "Epiphany", "Good Friday", "Easter Sunday", "May Day",
    "Midsummer Eve", "Midsummer Day", "Independence Day", "Christmas Eve",
    "Christmas Day", "Boxing Day",
]
STORE_OPEN_HOURS_LOCAL = {"weekday": (9, 21), "saturday": (9, 18), "sunday": (12, 18)}  # local hours, start inclusive

# ---------------------------------------------------------------------------
# Locations: store 900 (web shop) and 999 (training store) are pseudo-stores
# ---------------------------------------------------------------------------

WEB_STORE_ID = 900
TRAINING_STORE_ID = 999
TEST_CATEGORY = "ZZ Test"
N_TEST_SKUS = 12

REGIONS_OLD = ["South", "West", "East", "North"]
REGIONS_NEW = ["Capital Region", "South", "West", "East", "North"]

# (store_id, store_name, city, region before 28 Apr 2025, region from 28 Apr 2025, format,
#  open_date or None for "before the window", close_date or None)
STORES = [
    (101, "Helsinki Vuosaari", "Helsinki", "South", "Capital Region", "Medium", None, None),
    (102, "Helsinki Pitäjänmäki", "Helsinki", "South", "Capital Region", "Large", None, None),
    (103, "Espoo Lommila", "Espoo", "South", "Capital Region", "Medium", None, None),
    (104, "Vantaa Tammisto", "Vantaa", "South", "Capital Region", "Large", None, None),
    (105, "Kerava", "Kerava", "South", "Capital Region", "Small", None, None),
    (106, "Porvoo", "Porvoo", "South", "South", "Small", None, None),
    (107, "Hyvinkää", "Hyvinkää", "South", "South", "Medium", None, None),
    (108, "Lahti", "Lahti", "South", "South", "Large", None, None),
    (109, "Hämeenlinna", "Hämeenlinna", "South", "South", "Medium", None, None),
    (110, "Turku Kupittaa", "Turku", "South", "South", "Large", None, None),
    (111, "Turku Härmälä", "Turku", "South", "South", "Medium", None, None),
    (112, "Raisio", "Raisio", "South", "South", "Small", None, None),
    (113, "Salo", "Salo", "South", "South", "Small", None, None),
    (114, "Kouvola", "Kouvola", "East", "South", "Medium", None, None),
    (115, "Tampere Hervanta", "Tampere", "West", "West", "Large", None, None),
    (116, "Tampere Lielahti", "Tampere", "West", "West", "Large", None, None),
    (117, "Tampere Kaleva", "Tampere", "West", "West", "Medium", None, None),
    (118, "Nokia", "Nokia", "West", "West", "Medium", None, None),
    (119, "Pori", "Pori", "West", "West", "Medium", None, None),
    (120, "Rauma", "Rauma", "West", "West", "Small", None, None),
    (121, "Vaasa", "Vaasa", "West", "West", "Medium", None, None),
    (122, "Seinäjoki", "Seinäjoki", "West", "West", "Medium", None, None),
    (123, "Kokkola", "Kokkola", "West", "West", "Small", None, None),
    (124, "Jyväskylä Palokka", "Jyväskylä", "East", "East", "Medium", None, None),
    (125, "Kuopio", "Kuopio", "East", "East", "Large", None, None),
    (126, "Joensuu", "Joensuu", "East", "East", "Medium", None, None),
    (127, "Mikkeli", "Mikkeli", "East", "East", "Medium", None, None),
    (128, "Lappeenranta", "Lappeenranta", "East", "East", "Medium", None, None),
    (129, "Savonlinna", "Savonlinna", "East", "East", "Small", None, date(2026, 1, 25)),   # permanent closure
    (130, "Kotka", "Kotka", "East", "East", "Small", None, None),
    (131, "Oulu Kaakkuri", "Oulu", "North", "North", "Large", None, None),
    (132, "Oulu Linnanmaa", "Oulu", "North", "North", "Medium", None, None),
    (133, "Kemi", "Kemi", "North", "North", "Small", None, None),
    (134, "Rovaniemi", "Rovaniemi", "North", "North", "Medium", None, None),
    (135, "Kajaani", "Kajaani", "North", "North", "Small", None, None),
    (136, "Tampere Lamminpää", "Tampere", "West", "West", "Medium", date(2024, 9, 2), None),   # opening 1
    (137, "Lohja", "Lohja", "South", "South", "Small", date(2024, 11, 4), None),               # opening 2
    (138, "Iisalmi", "Iisalmi", "East", "East", "Small", None, None),
    (139, "Raahe", "Raahe", "North", "North", "Small", None, None),
]
STORE_SQM_BY_FORMAT = {"Large": (6000, 9000), "Medium": (3000, 5000), "Small": (1200, 2500)}

# Refit closures: whole fiscal weeks, Monday to Sunday, 4-6 weeks.
REFITS = [
    (104, date(2024, 7, 8), date(2024, 8, 11)),      # 5 weeks, FY2024/25
    (119, date(2025, 9, 8), date(2025, 10, 12)),     # 5 weeks, FY2025/26
    (125, date(2026, 6, 15), date(2026, 7, 26)),     # 6 weeks, FY2026/27
]
CLOSED_STORE_MEMBER_TRANSFER_TO = 127                # Savonlinna members move to Mikkeli on closure
NEW_STORE_CATCHMENT = {136: (115, 116, 117), 137: (113, 104, 107)}   # stores whose members may move home
NEW_STORE_TRANSFER_SHARE = 0.10

# ---------------------------------------------------------------------------
# Store volume model
# ---------------------------------------------------------------------------

RECEIPTS_PER_DAY_BY_FORMAT = {"Large": 29.0, "Medium": 16.0, "Small": 7.5}
STORE_FACTOR_SIGMA = 0.18                 # lognormal spread of store size within a format
STORE_ANNUAL_GROWTH_MEAN = 0.02           # real volume growth per year, per store
STORE_ANNUAL_GROWTH_SIGMA = 0.025
MONTH_VOLUME_INDEX = [0.86, 0.80, 0.90, 1.05, 1.30, 1.25, 1.10, 1.00, 0.95, 0.96, 1.10, 1.35]
WEEKDAY_VOLUME_INDEX = [0.85, 0.85, 0.92, 1.00, 1.18, 1.45, 0.72]   # Mon..Sun
EVENT_VOLUME_MULTIPLIER = {"black_friday": 1.5, "dec_22": 1.45, "dec_23": 1.7, "day_before_midsummer": 1.0}
NEW_STORE_RAMP_START = 0.55               # share of mature volume in week 1, rising to 1.0 over 52 weeks
CLOSING_STORE_FACTOR = 0.75               # last six weeks before closure
POST_REFIT_UPLIFT = 0.08                  # for 26 weeks after reopening
LINES_PER_RECEIPT_EXTRA_MEAN = 1.3        # lines = 1 + Poisson(this)
STAFF_RECEIPT_SHARE = 0.015
STAFF_DISCOUNT = 0.15
TRAINING_STORE_RECEIPTS_PER_DAY = 3.0
TRAINING_STORE_TEST_SKU_SHARE = 0.30      # rest of store 999 receipts are staff-flagged real SKUs
PRICE_INDEX_BY_FISCAL_YEAR = {2024: 1.00, 2025: 1.00, 2026: 1.00}   # nominal prices held flat
PROMO_LINE_SHARE_BASE = 0.10
PROMO_LINE_SHARE_BLACK_WEEK = 0.45
PROMO_LINE_SHARE_JANUARY = 0.22
PROMO_DISCOUNTS = [0.10, 0.15, 0.20, 0.25, 0.30, 0.40]
BLACK_FRIDAYS = [date(2024, 11, 29), date(2025, 11, 28)]

# ---------------------------------------------------------------------------
# Product blueprint: 4,000 SKUs incl. test SKUs
# (category, subcategory, n_skus, median net unit price EUR, gross margin share,
#  mean units per line, popularity weight, season profile, return rate, vat class, bulky)
# ---------------------------------------------------------------------------

SUBCATEGORIES = [
    ("Garden", "Plants & Flowers", 320, 7.5, 0.45, 1.6, 1.4, "garden_spring", 0.030, "standard", False),
    ("Garden", "Edible Plants & Seeds", 160, 3.2, 0.55, 1.5, 1.2, "garden_spring", 0.010, "reduced14", False),
    ("Garden", "Garden Tools", 180, 22.0, 0.40, 1.1, 0.9, "garden_spring", 0.050, "standard", False),
    ("Garden", "Garden Furniture", 110, 140.0, 0.34, 1.0, 0.5, "summer_outdoor", 0.090, "standard", True),
    ("Garden", "Barbecue & Grills", 90, 95.0, 0.32, 1.0, 0.6, "summer_outdoor", 0.060, "standard", True),
    ("Garden", "Soil & Fertiliser", 110, 8.0, 0.38, 2.2, 1.2, "garden_spring", 0.020, "standard", False),
    ("Garden", "Pots & Planters", 150, 12.0, 0.48, 1.4, 1.0, "garden_spring", 0.040, "standard", False),
    ("Garden", "Outdoor Lighting", 95, 24.0, 0.40, 1.2, 0.7, "lighting_out", 0.070, "standard", False),
    ("Paint & Decorating", "Interior Paint", 160, 28.0, 0.36, 1.3, 1.3, "paint", 0.020, "standard", False),
    ("Paint & Decorating", "Exterior Paint", 110, 42.0, 0.34, 1.2, 0.8, "paint_ext", 0.020, "standard", False),
    ("Paint & Decorating", "Brushes & Rollers", 130, 7.0, 0.52, 1.5, 1.1, "paint", 0.030, "standard", False),
    ("Paint & Decorating", "Wallpaper & Decor Film", 100, 26.0, 0.42, 1.2, 0.5, "paint", 0.050, "standard", False),
    ("Tools & Hardware", "Power Tools", 140, 95.0, 0.28, 1.0, 0.6, "flat", 0.070, "standard", False),
    ("Tools & Hardware", "Hand Tools", 200, 14.0, 0.46, 1.2, 1.0, "flat", 0.040, "standard", False),
    ("Tools & Hardware", "Fixings & Fasteners", 260, 3.5, 0.62, 3.0, 1.8, "flat", 0.010, "standard", False),
    ("Tools & Hardware", "Tool Storage", 70, 38.0, 0.40, 1.0, 0.4, "flat", 0.050, "standard", False),
    ("Electrical", "Indoor Lighting", 190, 18.0, 0.42, 1.4, 1.1, "lighting", 0.060, "standard", False),
    ("Electrical", "Cables & Plugs", 150, 6.5, 0.55, 1.5, 1.0, "flat", 0.030, "standard", False),
    ("Electrical", "Smart Home", 80, 38.0, 0.30, 1.0, 0.5, "flat", 0.090, "standard", False),
    ("Electrical", "Batteries & Bulbs", 110, 5.5, 0.50, 2.2, 1.6, "lighting", 0.020, "standard", False),
    ("Bathroom & Plumbing", "Taps & Showers", 110, 62.0, 0.36, 1.0, 0.5, "flat", 0.060, "standard", False),
    ("Bathroom & Plumbing", "Bathroom Furniture", 80, 120.0, 0.34, 1.0, 0.35, "flat", 0.080, "standard", True),
    ("Bathroom & Plumbing", "Plumbing Parts", 170, 6.0, 0.58, 2.0, 1.2, "flat", 0.020, "standard", False),
    ("Kitchen & Dining", "Cookware", 130, 22.0, 0.44, 1.3, 0.9, "flat", 0.050, "standard", False),
    ("Kitchen & Dining", "Tableware", 170, 8.0, 0.50, 2.0, 1.2, "xmas_mild", 0.040, "standard", False),
    ("Kitchen & Dining", "Small Appliances", 110, 55.0, 0.27, 1.0, 0.7, "xmas_mild", 0.100, "standard", False),
    ("Home Textiles & Decor", "Curtains & Blinds", 110, 24.0, 0.46, 1.2, 0.7, "flat", 0.080, "standard", False),
    ("Home Textiles & Decor", "Rugs", 70, 55.0, 0.42, 1.0, 0.4, "flat", 0.080, "standard", True),
    ("Home Textiles & Decor", "Cushions & Throws", 130, 14.0, 0.52, 1.5, 1.0, "winter_cosy", 0.060, "standard", False),
    ("Home Textiles & Decor", "Candles & Frames", 170, 7.0, 0.56, 2.0, 1.4, "xmas_mild", 0.030, "standard", False),
    ("Furniture", "Storage Furniture", 110, 85.0, 0.36, 1.0, 0.45, "flat", 0.090, "standard", True),
    ("Furniture", "Living Room", 70, 210.0, 0.34, 1.0, 0.25, "flat", 0.100, "standard", True),
    ("Furniture", "Bedroom", 70, 190.0, 0.34, 1.0, 0.25, "flat", 0.100, "standard", True),
    ("Furniture", "Home Office", 60, 110.0, 0.32, 1.0, 0.30, "back_to_school", 0.090, "standard", True),
    ("Cleaning & Household", "Cleaning Products", 170, 4.5, 0.55, 2.0, 1.8, "flat", 0.010, "standard", False),
    ("Cleaning & Household", "Laundry & Ironing", 80, 20.0, 0.40, 1.1, 0.6, "flat", 0.050, "standard", False),
    ("Cleaning & Household", "Storage Boxes", 120, 9.0, 0.48, 1.8, 1.0, "back_to_school", 0.030, "standard", False),
    ("Seasonal", "Christmas Decorations", 200, 11.0, 0.58, 2.0, 1.6, "xmas", 0.020, "standard", False),
    ("Seasonal", "Sauna & Winter", 90, 26.0, 0.40, 1.1, 0.7, "sauna_winter", 0.040, "standard", False),
    ("Seasonal", "Books & Magazines", 40, 22.0, 0.30, 1.0, 0.3, "flat", 0.010, "reduced10", False),
]
N_SKUS_TOTAL = 4000                         # regular SKUs are scaled to N_SKUS_TOTAL - N_TEST_SKUS
SKU_FIRST_NUMBER = 100001
SKU_PRICE_SIGMA = 0.45                      # lognormal spread of price within a subcategory
SKU_POPULARITY_SIGMA = 0.85
SKU_MARGIN_NOISE = 0.05
SKU_INTRODUCED_DURING_WINDOW_SHARE = 0.12   # listed_from inside the window
SKU_DELISTED_DURING_WINDOW_SHARE = 0.07     # delisted_on inside the window
OWN_LABEL_SHARE = 0.25
OWN_LABEL_BRANDS = ["Havu", "Havu Pro"]
BRANDS = ["Norvik", "Kuusela", "Lumiko", "Harmaja", "Vesikko", "Kultala", "Mäntylä", "Kajo", "Nordhem",
          "Peltola", "Selkämaa", "Tuulikki", "Koivuranta", "Ahvenisto", "Raudikko", "Poutaranta Home"]
BRAND_RENAME_SKU_COUNT = 40                 # SKUs given a second dim_product version (brand renamed)
OUTDOOR_LIGHTING_SUBCATEGORY = "Outdoor Lighting"

SEASON_PROFILES = {                          # monthly multipliers, January..December
    "flat":           [1.0] * 12,
    "garden_spring":  [0.2, 0.2, 0.5, 1.8, 3.2, 2.6, 1.6, 1.0, 0.6, 0.4, 0.2, 0.2],
    "summer_outdoor": [0.2, 0.2, 0.4, 1.0, 2.2, 3.0, 2.8, 1.8, 0.7, 0.3, 0.2, 0.2],
    "paint":          [0.7, 0.7, 1.0, 1.4, 1.5, 1.4, 1.3, 1.2, 1.0, 0.9, 0.8, 0.6],
    "paint_ext":      [0.2, 0.2, 0.5, 1.6, 2.4, 2.4, 2.2, 1.6, 0.8, 0.3, 0.2, 0.2],
    "lighting":       [1.4, 1.0, 0.8, 0.6, 0.5, 0.5, 0.6, 0.9, 1.3, 1.6, 1.8, 1.7],
    "lighting_out":   [0.8, 0.6, 0.5, 0.6, 0.9, 1.0, 1.0, 1.3, 1.6, 1.8, 1.7, 1.4],
    "xmas":           [0.5, 0.2, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.3, 1.5, 5.5, 8.0],
    "xmas_mild":      [0.8, 0.7, 0.7, 0.7, 0.7, 0.7, 0.7, 0.7, 0.8, 1.1, 1.8, 2.3],
    "sauna_winter":   [1.4, 1.1, 0.9, 0.7, 0.6, 0.5, 0.5, 0.6, 0.9, 1.3, 1.6, 1.6],
    "winter_cosy":    [1.3, 1.1, 0.9, 0.7, 0.6, 0.5, 0.5, 0.6, 0.9, 1.4, 1.6, 1.6],
    "back_to_school": [0.9, 0.8, 0.8, 0.8, 0.8, 0.8, 0.9, 1.7, 1.8, 1.0, 0.9, 0.8],
}
RANGING_PROBABILITY_BY_FORMAT = {"Large": 0.34, "Medium": 0.19, "Small": 0.10}
RANGING_BULKY_FACTOR_SMALL_STORE = 0.15     # bulky lines are rarely ranged in small stores

# ---------------------------------------------------------------------------
# Members and campaigns
# ---------------------------------------------------------------------------

N_MEMBERS = 60000
MEMBER_PRE_WINDOW_SHARE = 0.40              # joined before the window start
MEMBER_PRE_WINDOW_FIRST_DATE = date(2019, 1, 1)
MEMBER_ONLINE_ENROL_SHARE = 0.20            # home store 900 at enrolment
MEMBER_TIER_SHARES = {"Basic": 0.70, "Silver": 0.22, "Gold": 0.08}
MEMBER_TIER_CHANGE_SHARE = 0.30
MEMBER_HOME_MOVE_SHARE = 0.06
MEMBER_CONSENT_INITIAL_SHARE = 0.72
MEMBER_CONSENT_WITHDRAW_SHARE = 0.12        # of consenting members
MEMBER_CONSENT_OPTIN_SHARE = 0.15           # of non-consenting members
MEMBER_CHURN_SHARE = 0.30
MEMBER_ACTIVITY_GAMMA_SHAPE = 0.7
MEMBER_WEB_TRAIT_SIGMA = 0.8
MEMBER_RECEIPT_SHARE_START = 0.44           # share of store receipts carrying a member
MEMBER_RECEIPT_SHARE_END = 0.58
MEMBER_HOME_STORE_PICK_SHARE = 0.80         # store receipts drawn from members whose home is that store
WEB_LOGGED_IN_SHARE = 0.68

CAMPAIGN_HOLDOUT_SHARE = 0.10
CAMPAIGN_UPLIFT_WINDOW_EXTRA_DAYS = 7
CAMPAIGN_DEFAULT_TARGET_FRACTION = 0.45     # share of eligible members on the mailing list
CAMPAIGN_CONTACTS_PER_MEMBER = {1: 0.30, 2: 0.40, 3: 0.20, 4: 0.10}
# (campaign_id, name, start, end, channels, segment, true uplift, target fraction)
CAMPAIGNS = [
    (1, "Spring Garden Launch 2024", date(2024, 5, 6), date(2024, 5, 26), ("email", "sms"), "all_consenting", 0.22, None),
    (2, "Midsummer Terrace 2024", date(2024, 6, 10), date(2024, 6, 23), ("email",), "silver_gold", 0.18, None),
    (3, "Back to School Home Office 2024", date(2024, 8, 12), date(2024, 9, 1), ("email", "push"), "all_consenting", 0.12, None),
    (4, "Autumn Refresh Paint 2024", date(2024, 9, 16), date(2024, 10, 6), ("email",), "all_consenting", 0.15, None),
    (5, "Black Week 2024", date(2024, 11, 25), date(2024, 12, 1), ("email", "sms", "push"), "all_consenting", 0.30, 0.80),
    (6, "Christmas Last Orders 2024", date(2024, 12, 9), date(2024, 12, 22), ("email", "sms"), "silver_gold", 0.20, None),
    (7, "New Year Storage Sale", date(2025, 1, 6), date(2025, 1, 26), ("email",), "all_consenting", 0.10, None),
    (8, "Sauna and Winter Warmers 2025", date(2025, 2, 3), date(2025, 2, 23), ("email",), "region_north_east", 0.12, None),
    (9, "Spring Garden Launch 2025", date(2025, 5, 5), date(2025, 5, 25), ("email", "sms"), "all_consenting", 0.24, None),
    (10, "Welcome Back 2025", date(2025, 6, 2), date(2025, 6, 29), ("email",), "new_members_12m", 0.28, 0.80),
    (11, "Midsummer Terrace 2025", date(2025, 6, 9), date(2025, 6, 22), ("email",), "silver_gold", 0.17, None),
    (12, "Garden Clearance 2025", date(2025, 8, 18), date(2025, 9, 7), ("email", "push"), "all_consenting", 0.11, None),
    (13, "Autumn Refresh 2025", date(2025, 9, 15), date(2025, 10, 5), ("email",), "all_consenting", 0.14, None),
    (14, "Lighting Season 2025", date(2025, 10, 27), date(2025, 11, 16), ("email",), "region_capital_south", 0.16, None),
    (15, "Black Week 2025", date(2025, 11, 24), date(2025, 11, 30), ("email", "sms", "push"), "all_consenting", 0.31, 0.80),
    (16, "Christmas Last Orders 2025", date(2025, 12, 8), date(2025, 12, 21), ("email", "sms"), "silver_gold", 0.19, None),
    (17, "Winter Sale 2026", date(2026, 1, 5), date(2026, 1, 25), ("email",), "all_consenting", 0.10, None),
    (18, "Sauna and Winter Warmers 2026", date(2026, 2, 2), date(2026, 2, 22), ("email",), "region_north_east", 0.13, None),
    (19, "Spring Garden Launch 2026", date(2026, 5, 4), date(2026, 5, 24), ("email", "sms"), "all_consenting", 0.23, None),
    (20, "Welcome Back 2026", date(2026, 6, 1), date(2026, 6, 28), ("email",), "new_members_12m", 0.27, 0.80),
    (21, "Midsummer Terrace 2026", date(2026, 6, 8), date(2026, 6, 21), ("email",), "silver_gold", 0.18, None),
    (22, "Back to School Home Office 2026", date(2026, 8, 10), date(2026, 8, 30), ("email", "push"), "all_consenting", 0.12, None),
    (23, "Autumn Refresh 2026", date(2026, 9, 14), date(2026, 9, 20), ("email",), "all_consenting", 0.14, None),
]
CAMPAIGN_SEGMENT_DESCRIPTIONS = {
    "all_consenting": "All members with marketing consent at the campaign start",
    "silver_gold": "Silver and Gold tier members with marketing consent at the campaign start",
    "region_north_east": "Members with marketing consent whose home store is in the North or East region at the campaign start",
    "region_capital_south": "Members with marketing consent whose home store is in the Capital Region or South at the campaign start",
    "new_members_12m": "Members who joined in the 12 months before the campaign start and have marketing consent",
}

# ---------------------------------------------------------------------------
# Web orders
# ---------------------------------------------------------------------------

WEB_ORDERS_PER_DAY_START = 70.0             # FY2024/25 average, before seasonality
WEB_ANNUAL_GROWTH = 0.28
WEB_BLACK_FRIDAY_MULTIPLIER = 3.4
WEB_CYBER_MONDAY_MULTIPLIER = 2.2
WEB_EVENT_MULTIPLIER = {                    # extra web demand on named days (trap days need enough orders; see TIMEZONE_TRAP_DAYS)
    date(2024, 12, 16): 1.6, date(2024, 12, 17): 1.6, date(2024, 12, 18): 1.6, date(2024, 12, 19): 1.6,
    date(2024, 12, 20): 1.6, date(2024, 12, 23): 1.8, date(2025, 12, 15): 1.7, date(2025, 12, 16): 1.7,
    date(2025, 12, 17): 1.7, date(2025, 12, 18): 1.7, date(2025, 12, 19): 1.7, date(2025, 12, 22): 1.5,
    date(2025, 12, 23): 1.8, date(2025, 3, 30): 1.5, date(2025, 10, 26): 1.5,
}
WEB_WEEKDAY_INDEX = [1.05, 1.05, 1.0, 1.0, 0.95, 0.9, 1.1]
WEB_LINES_PER_ORDER_EXTRA_MEAN = 1.0
WEB_CANCELLATION_SHARE = 0.04
WEB_CANCELLATION_SHARE_PEAK = 0.065         # on Black Friday and Cyber Monday
WEB_CLICK_COLLECT_SHARE_START = 0.22
WEB_CLICK_COLLECT_SHARE_END = 0.31
# local-hour order profile, hours 0..23; peaks late evening, with a small night shift
WEB_ORDER_HOUR_WEIGHTS = [1.6, 1.0, 0.5, 0.2, 0.2, 0.3, 0.6, 1.1, 1.8, 2.6, 3.2, 3.6,
                          3.5, 3.2, 3.2, 3.4, 3.6, 4.0, 4.6, 5.4, 6.0, 6.4, 5.2, 2.6]
CYBER_MONDAYS = [date(2024, 12, 2), date(2025, 12, 1)]
CLOCK_CHANGE_DAYS = [date(2025, 3, 30), date(2025, 10, 26)]       # Finland changes clocks: 23- and 25-hour days
CHRISTMAS_DEADLINE_DAYS = [date(2024, 12, 23), date(2025, 12, 23)]   # last-orders midnight deadline
WEB_MIDNIGHT_DEAL_DAYS = BLACK_FRIDAYS + CYBER_MONDAYS + CLOCK_CHANGE_DAYS + CHRISTMAS_DEADLINE_DAYS   # a spike of orders in local hour 0
WEB_MIDNIGHT_DEAL_SHARE = 0.12
WEB_DISPATCH_LAG_DAYS_HOME = {0: 0.10, 1: 0.50, 2: 0.28, 3: 0.12}
WEB_DISPATCH_LAG_DAYS_CLICK_COLLECT = {0: 0.25, 1: 0.55, 2: 0.20}
WEB_DISPATCH_NIGHT_SCAN_SHARE = 0.12        # carrier hand-over scans between 21:00 and 24:00 UTC
WEB_DISPATCH_DAY_HOURS_UTC = (6, 17)        # otherwise uniform between these UTC hours
WEB_TEST_ORDERS_PER_YEAR = 8
WEB_BULKY_TILT = 1.5
WEB_PROCESSING_WINDOW_DAYS = 6              # orders newer than this may still be unshipped at the data cut

# Days on which a UTC-vs-Helsinki calendar-day error changes web counts. Validator rule 6.
TIMEZONE_TRAP_DAYS = [
    date(2024, 11, 29), date(2025, 11, 28),         # Black Fridays (midnight deals)
    date(2024, 12, 2), date(2025, 12, 1),           # Cyber Mondays
    date(2024, 12, 23), date(2025, 12, 23),         # last Christmas orders
    date(2025, 3, 30), date(2025, 10, 26),          # clocks change in Finland (23 and 25 hour days)
]
TIMEZONE_TRAP_MIN_BOUNDARY_ORDERS = 12              # orders whose UTC date differs from the Helsinki date
TIMEZONE_TRAP_MIN_BOUNDARY_DISPATCHES = 6

# ---------------------------------------------------------------------------
# Returns (fact_return_line; coherence rule 5)
# ---------------------------------------------------------------------------

RETURN_WINDOW_DAYS = 30
RETURN_WEB_MULTIPLIER = 2.2
RETURN_STORE_LAG_GEOMETRIC_P = 0.18         # lag = 1 + Geometric(p) days
RETURN_WEB_LAG_GEOMETRIC_P = 0.12           # lag = 2 + Geometric(p) days after dispatch
RETURN_WEB_IN_STORE_SHARE = 0.25
RETURN_REASONS = {"changed_mind": 0.34, "not_as_described": 0.18, "defective": 0.20, "damaged_in_transit": 0.08,
                  "wrong_size_or_fit": 0.20}

# ---------------------------------------------------------------------------
# Stock (fact_stock_week; rule 9). Physical stores only.
# ---------------------------------------------------------------------------

STOCK_MIN_FACING_UNITS = 2
STOCK_REORDER_WEEKS = 1.5
STOCK_ORDER_UP_TO_EXTRA_WEEKS = 2.0
STOCK_PACK_SIZE_CHOICES = [2, 3, 4, 6]
STOCK_TRAILING_WEEKS = 4
STOCK_SHRINK_PROBABILITY = 0.015            # chance per store-SKU-week of a stock-take adjustment of -1

# ---------------------------------------------------------------------------
# Undocumented incidents (in the data, in no world/ document). IDs are internal.
# ---------------------------------------------------------------------------

INCIDENT_DOUBLE_POST = {      # I1: a till re-sync re-posted a whole store-week of receipts
    "id": "INC-1", "store_id": 116, "week_start": date(2025, 9, 15), "week_end": date(2025, 9, 21),
    "reload_ts": "2025-09-23 03:12:00",
}
INCIDENT_LOGIN_ORPHANS = {    # I2: logged-in web orders lost their member key on the sales lines
    "id": "INC-2", "start": date(2026, 2, 9), "end": date(2026, 3, 1), "share_of_logged_in_orders": 0.55,
}
INCIDENT_STOCK_RELOAD = {     # I3: the West region's stock snapshot for one week was loaded twice
    "id": "INC-3", "week_ending": date(2026, 3, 8), "region_new": "West", "reload_ts": "2026-03-10 02:45:00",
}
INCIDENT_CNC_MISLABEL = {     # I4: click-and-collect orders carried the home-delivery channel key
    "id": "INC-4", "start": date(2026, 1, 12), "end": date(2026, 2, 8),
}

# ---------------------------------------------------------------------------
# Clutter, retention of dated copies, and load timing
# ---------------------------------------------------------------------------

NIGHTLY_LOAD_HOUR_UTC = 1                   # facts are loaded at 01:00 UTC the next calendar day
STAGING_RETENTION_DAYS = 2                  # stg_* tables hold only the last few days
BAK_STORE_SNAPSHOT_DATE = date(2025, 4, 27)
BAK_PRODUCT_SNAPSHOT_DATE = date(2025, 10, 26)
LEGACY_WEEKLY_REPORT_LAST_DATE = date(2025, 4, 27)   # rpt_weekly_sales_by_region stopped refreshing here

# ---------------------------------------------------------------------------
# Dev requests: which patterns the history covers
# ---------------------------------------------------------------------------

DEV_PATTERNS_COVERED = [1, 2, 3, 4, 5, 6, 7, 8, 11, 12]
DEV_PATTERNS_ABSENT = [9, 10, 13, 14]
N_DEV_REQUESTS = 40
DEV_REQUEST_COUNTS = {1: 5, 2: 4, 3: 4, 4: 3, 5: 5, 6: 3, 7: 4, 8: 4, 11: 4, 12: 4}

# ---------------------------------------------------------------------------
# The shared task text. Identical for every arm; Phase 5's harness reads it from here.
# Placeholders: {received_date} {requester} {department} {request_text} {max_queries}
# It says nothing about any specific incident.
# ---------------------------------------------------------------------------

MAX_QUERY_EXECUTIONS = 30                     # 12 until round 38 of the full run; raised to 30 on 15 Oct 2026 (task text v4, see below)
MAX_SKILL_LOADS = 6
# Version of the shared task text. "1" = as run in the 15 Oct 2026 API pilot. "2" = after the pilot diagnosis, with the
# six output rules added to the "result" key (15 Oct 2026, before any test run).
# "3" = after pilot 2 (agents): two more output rules in the "result" list, a fiscal calendar label never fused into one
# string, and a read-through of the table against the request before replying (15 Oct 2026, before any run of pilot 3). Pilot 2 ran version 2.
# "4" = the query budget raised from 12 to 30 (15 Oct 2026, paused after round 38 of the full run). The wording is
# unchanged: the number reaches the task text, the packets' SQL section and the counters through MAX_QUERY_EXECUTIONS. Rounds 1 to 38
# ran under version 3 (12 queries).
TASK_INSTRUCTIONS_VERSION = "4"
TASK_INSTRUCTIONS = """You are an analyst on the Data & Analytics team at Tuomimetsä Oy. A request has arrived in the team queue. Answer it by querying the company's DuckDB warehouse (read-only) with the SQL tool. You may run up to {max_queries} queries.

Request received {received_date}
From: {requester}, {department}

> {request_text}

If you find a problem in the data, correct for it in your answer and list every correction in `caveats`.

When you are done, reply with a single JSON object and nothing else, with these keys:
- "sql": the final SQL query that produces your result (one string).
- "result": the final table that answers the request, as {{"columns": [...], "rows": [[...], ...]}}. Give the answer table only, not intermediate checks. A single number is one row with one column. Use plain numbers (no currency symbols or thousands separators). Percentages are numbers in percent units (12.5 means 12.5%, never 0.125). The table follows these rules:
  - Return exactly the columns the request asks for, plus label columns that say what each row is. Leave out working columns and intermediate figures nobody asked for.
  - One row per natural grain of the question (per store, per region, per week, and so on). Give a breakdown only if the request asks for one.
  - No total or subtotal rows unless the request asks for a total.
  - No padding rows: do not add a row of zeros for something that has no sales or no events.
  - Name things as well as giving their IDs: where a row is a store, a product, a campaign or a member tier, include its name beside the ID.
  - Fiscal calendar labels go in separate columns: `fiscal_year` as the warehouse writes it (FY2025/26), and the quarter, period or week as a plain whole number (3, 7, 22). Never join them into one label such as "FY2025/26 P07", "FY2024/25 Q1" or "FY2025/26 W15".
  - Before you reply, read the table against the wording of the request. If the request asks for one figure, the table is one row; if your query returned a total row, a breakdown or helper columns the request did not ask for, take them out.
- "definitions_applied": a list of the company definitions and rules you applied, each named in a few words.
- "assumptions": a list of the choices you made where the request left something open, including how you read any relative or ambiguous term.
- "caveats": a list of the problems, limits and corrections the requester should know about."""

# ---------------------------------------------------------------------------
# Phase 3: request set and answer key
# ---------------------------------------------------------------------------

REQUESTS_DIR = DATA_DIR / "requests"          # HELD OUT of world/: briefs (carry the traps) and the request texts
KEY_DIR = DATA_DIR / "key"                    # HELD OUT of world/: the answer key. Read by code/mark.py and nothing else.
N_TEST_REQUESTS = 60
N_PARAPHRASE_PAIRS = 10
TEST_RECEIVED_DATES = [date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 9)]
# Requests arrive in the week after the data cut, so "last period" = FY2026/27 P05, "last week" = week 22, "this year" = FY2026/27.
MARKING_REL_TOLERANCE = 0.001                 # 0.1% relative
MARKING_PCT_TOLERANCE = 0.1                   # 0.1 percentage points
TRAP_BITE_FACTOR = 10                         # rule 13: a naive variant must differ by more than 10 x tolerance
# Trap-class counts across the 60 requests (counts overlap; a request carries at most two traps).
TRAP_CLASS_COUNTS = {   # targets; the key reports the achieved counts and the validator allows +/- TRAP_CLASS_TOLERANCE
    "company_definition": 14, "fiscal_calendar": 12, "scd": 8, "migration": 5, "time_zone": 4, "exclusions": 6,
    "fan_out": 5, "semi_additive": 3, "vat": 4, "ambiguous": 5, "override": 4, "undocumented": 4, "clean": 14,
}
TRAP_CLASS_TOLERANCE = 3
TEST_NOVEL_PATTERNS = [9, 10, 13, 14]
# Requests per pattern (sums to 60). The four novel patterns carry 3 each = 12.
TEST_PATTERN_COUNTS = {1: 6, 2: 4, 3: 7, 4: 4, 5: 6, 6: 2, 7: 3, 8: 5, 9: 3, 10: 4, 11: 6, 12: 4, 13: 3, 14: 3}   # 13 novel (patterns 9, 10, 13, 14)
DEPARTMENT_REQUESTERS = {
    "Finance (FP&A)": ["Marjatta Salonen", "Antti Rautiainen"],
    "Commercial (category management)": ["Hanna Kivistö", "Pekka Lindroos"],
    "Marketing and CRM": ["Sanna Ahonen", "Jukka Ylönen"],
    "Store operations": ["Mika Hietala", "Leena Vuorinen"],
    "E-commerce": ["Tiina Mäkelä", "Veikko Saarela"],
    "Supply chain": ["Kaisa Hakala", "Olli Nurmi"],
}
CLEAN_SKU_UNITS_SKU = 101624                  # clean request: units of this SKU (Fixings & Fasteners, one product version) ...
CLEAN_SKU_UNITS_STORE = 131                   # ... at Oulu Kaakkuri in the last completed week
CLEAN_STOCK_SKU = 100011                      # clean request: closing stock of this SKU (Plants & Flowers, one product version) ...
CLEAN_STOCK_STORE = 124                       # ... at Jyväskylä Palokka at the end of the last completed week
CLEAN_JOIN_DATES = [date(2026, 10, 3), date(2026, 9, 25)]   # days on which every new member still has a single dim_member version
DEV_NGRAM_LEAK_THRESHOLD = 0.5              # max share of a test request's word 3-grams found in any one dev request

# ---------------------------------------------------------------------------
# Phase 4: arm materials (the prompt doc and the skills library), validated by validate_arms.py (rules 16 to 18)
# ---------------------------------------------------------------------------

ARMS_DIR = CASE_ROOT / "arms"                 # prompt_doc.md and library/ as delivered by the isolated builder (never hand-edited)
ARMS_DOC_PATH = ARMS_DIR / "prompt_doc.md"
ARMS_LIBRARY_DIR = ARMS_DIR / "library"
# Rule 18, request leakage. A test request leaks if a text in the world, the doc or the library repeats it. Two tests:
#   (a) 5-gram containment: share of the request's word 5-grams found anywhere in one file. A copy scores 1.0, a
#       paraphrase that keeps half the phrasing scores about 0.5. The worst honest pair (a test request against the
#       dev history, which the builder may read) scores 0.29, so 0.5 leaves a wide margin on both sides.
#   (b) segment overlap: the Phase 3 trigram overlap (build_requests.overlap, the same function as the dev-history
#       check, same threshold DEV_NGRAM_LEAK_THRESHOLD) against every line or sentence of at least 8 words. Shorter
#       segments are skipped: a 4-word heading such as "League table for P3" would score 1.0 against a request that
#       only shares those words.
ARMS_LEAK_FILE_FIVEGRAM_THRESHOLD = 0.5
ARMS_LEAK_SEGMENT_MIN_WORDS = 8
# Rule 18, reference SQL leakage. A template leaks a reference query if it contains the whole query (after whitespace
# normalisation), or if it reproduces more than this share of the query's 12-token runs. Templates are built from the
# dev history, and reference queries share its house CTEs, so the honest baseline is measured, not assumed: the same
# score of the reference queries against the 40 dev queries is reported beside it, and the limit sits above that.
ARMS_SQL_TOKEN_RUN = 12
ARMS_SQL_LEAK_THRESHOLD = 0.9
# The second SQL test is the one that matters: the share of a reference query's token runs that a template reproduces
# and that appear in no dev query. The dev history is what the builder legitimately saw, so overlap it explains is not a
# leak. What is left comes from the definitions (for example "select distinct member_id via dim_member" follows from
# REG-EXPOSURE-FANOUT) and is small. A copied query would put most of its runs here.
ARMS_SQL_UNEXPLAINED_LIMIT = 0.25
# Rule 17, is query_check.py generic? It is run on a double-post planted at a store and week that belong to no incident
# (a copy of one week of store 118's lines, 1 to 7 June 2026) and must flag it twice: at the source grain and against the
# control total. The same query on the untouched warehouse must pass.
ARMS_PLANT_STORE_ID = 118
ARMS_PLANT_START = date(2026, 6, 1)
ARMS_PLANT_END = date(2026, 6, 7)

# ---------------------------------------------------------------------------
# Validation expectations (scale and mix; the rules themselves are in validate_data.py)
# ---------------------------------------------------------------------------

EXPECTED_SALES_LINES_RANGE = (1_000_000, 2_200_000)
EXPECTED_MEMBERS = N_MEMBERS
EXPECTED_STORES_TRADING_AT_END = 38
HASH_TABLE_SAMPLE_NOTE = "content hash over every table, rows sorted, SHA-256"

# ---------------------------------------------------------------------------
# Phase 5: harness and pilot (harness.py, run_pilot.py, pilot_marking.py, fake_client.py)
#
# NO MODEL IS PINNED HERE. The model is a parameter of every run (harness.run_one(model=...), --models on the pilot),
# because the main model is chosen after the pilot (15 Oct 2026). The two pilot candidates and their prices are below.
# ---------------------------------------------------------------------------

RUNS_DIR = DATA_DIR / "runs"                  # run logs (JSON lines), one file per run, plus runs_index.jsonl
ARM_LABELS = ("S", "D", "L", "L-")            # schema only / + prompt doc / + skills library / library without scripts
SMALL_MODEL_REPLICATION_ARMS = ("S", "L")     # the small-model replication reruns S and L only

# Pilot candidates: one larger and one smaller model, to decide which is worth it for the full run.
PILOT_MODELS = ("claude-sonnet-5-5", "claude-haiku-4-5-20251001")

# Published prices, USD per million tokens. Read on 15 Oct 2026 from the Anthropic pricing page
# (platform.claude.com/docs/en/about-claude/pricing). The Claude API skill reference carries an older cached table
# (25 Sep 2026) that lists Sonnet 5.5 cache hits at $0.20; the pricing page says 0.05x base ($0.10), and the page is used.
# Cost of a call = input*p_in + cache_write*p_cache_write + cache_read*p_cache_read + output*p_out. Cache writes are the
# 5-minute kind (the default ttl). Check the page again on the day the full runs start; prices are the one input here
# that moves. Costs are reported in USD, the currency of the published prices; a euro band is
# computed in Phase 6 with the rate on the run date (no rate is guessed here).
PRICES_READ_ON = "2026-10-15"
PRICES_SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing"
MODEL_PRICES_USD_PER_MTOK = {
    "claude-sonnet-5-5":         {"input": 2.00, "cache_write_5m": 2.50, "cache_read": 0.10, "output": 10.00},
    "claude-haiku-4-5-20251001": {"input": 1.00, "cache_write_5m": 1.25, "cache_read": 0.10, "output": 5.00},
}
MODEL_REQUEST_EXTRAS = {}                     # per-model extra request fields (for example an effort setting). Empty = API defaults,
                                              # the same defaults a deployment would get. Anything put here applies to every run of that model.

# Per-run limits and tool behaviour. The budgets (MAX_QUERY_EXECUTIONS, MAX_SKILL_LOADS) are above, in the task section.
HARNESS_VERSION = "1.0"
MAX_OUTPUT_TOKENS = 16000                     # per API call; thinking tokens (Sonnet) count inside it
MAX_TURNS = 40                                # API calls per run, a safety stop well above the tool budgets
MAX_SKILL_FILE_READS = 30                     # files read through load_skill in one run (the budget counts distinct skills opened)
MAX_REFUSED_CALLS_AFTER_BUDGET = 3            # tool calls tried after a budget is used up before the run is ended as no answer
SCRIPT_CALLS_COUNT_AS_QUERIES = True          # run_script executes SQL, so each call uses one of the run's query executions
SQL_RESULT_ROW_LIMIT = 200                    # rows returned to the model by run_sql
SQL_CELL_CHAR_LIMIT = 200                     # characters per text cell returned to the model
SQL_TIMEOUT_SECONDS = 120
SQL_MEMORY_LIMIT = "4GB"
SCRIPT_TIMEOUT_SECONDS = 180
SCRIPT_OUTPUT_CHAR_LIMIT = 20000
SKILL_FILE_CHAR_LIMIT = 200000
STRIP_PROVENANCE_MARKERS = True               # remove the <!-- facts: --> and <!-- source: --> lines from doc and library text (same for both arms)
API_TIMEOUT_SECONDS = 600
API_MAX_RETRIES = 4                           # SDK-level retries on 429 / 5xx / connection errors

# Spending guard. Before every API call the harness bounds that call's cost from above (the input estimated at
# PESSIMISTIC_CHARS_PER_TOKEN characters per token and priced as a cache write, plus MAX_OUTPUT_TOKENS of output) and
# does not make the call if spend so far plus the bound would pass the cap.
PESSIMISTIC_CHARS_PER_TOKEN = 2.5

# The pilot (Phase 5, 14-15 Oct 2026): dev requests only, the same requests and arms for each model.
# Chosen to need different house knowledge, and to be absent from the prompt doc's three full queries (D01, D07, D25),
# which would make the D arm trivial: D02 fiscal calendar and format comparison, D06 LFL, D14 return-rate cohort,
# D20 time zone, D32 member share by region. All four arms see each request once per model: 5 x 4 = 20 runs per model.
PILOT_REQUEST_IDS = ("REQ-D02", "REQ-D06", "REQ-D14", "REQ-D20", "REQ-D32")
PILOT_ARMS = ARM_LABELS
PILOT_REPEATS = 1
PILOT_DIRNAME = "pilot"                       # under RUNS_DIR
PILOT_CONSECUTIVE_API_ERRORS_ABORT = 3

# The full plan, for the cost estimate: 60 requests x 5 runs x 4 arms, plus the small-model replication on S and L.
FULL_PLAN_REQUESTS = N_TEST_REQUESTS
FULL_PLAN_RUNS_PER_REQUEST = 5

# ---------------------------------------------------------------------------
# Agent runs (15 Oct 2026): the runs are done by Claude Code subagents instead of the paid API.
# No paid API for the full run: agents in batches. A run = one fresh subagent (model "sonnet" = Sonnet 5.5 or
# "haiku" = Haiku 4.5), one request, one arm, with Bash, Read and Glob. The packet is the exact prompt text; the stage
# folder holds only what the arm may read; the SQL and script commands count queries per run (code/hx_*.py).
# ---------------------------------------------------------------------------

AGENT_RUNS_DIR = DATA_DIR / "agent_runs"
AGENT_PACKETS_DIR = AGENT_RUNS_DIR / "packets"
AGENT_STAGE_DIR = AGENT_RUNS_DIR / "stage"
AGENT_COUNTERS_DIR = AGENT_RUNS_DIR / "counters"      # one JSON file per run id: the query budget and an audit of each call
AGENT_SCRATCH_DIR = AGENT_RUNS_DIR / "scratch"        # per-run scratch folders for library scripts
AGENT_LOGS_DIR = AGENT_RUNS_DIR / "logs"              # run logs written by collect_agent_answer.py
AGENT_MARKED_DIR = AGENT_RUNS_DIR / "marked"          # marking output
AGENT_VAULT_DIR = AGENT_RUNS_DIR / "vault"            # the encrypted archive written by lock_answers.py
AGENT_MODEL_IDS = {"sonnet": "claude-sonnet-5-5", "haiku": "claude-haiku-4-5-20251001"}   # Agent tool "model" -> model ID
AGENT_ARMS = ("S", "D", "L", "L-")

# Pilot 2 (15 Oct 2026): another pilot on a variety of questions. Ten dev requests not used in pilot 1 and not among the three queries the
# prompt doc carries in full (D01, D07, D25), one per pattern the dev history covers (1-8, 11, 12), chosen so that the
# traps differ: as-was regions (D05), LFL on a year-to-date range (D09), margin after returns (D10), web against stores
# in a return cohort (D16), the 3 November migration (D19), complete quarters only and cancelled orders (D24), a named
# store against the chain (D28), tier at a date (D30), as-is region in a top-N (D34), trading days in a league table (D40).
PILOT2_REQUEST_IDS = ("REQ-D05", "REQ-D09", "REQ-D10", "REQ-D16", "REQ-D19", "REQ-D24", "REQ-D28", "REQ-D30", "REQ-D34", "REQ-D40")
PILOT2_CELLS = (("sonnet", "S"), ("sonnet", "D"), ("sonnet", "L"), ("haiku", "L"))   # (agent model, arm); 4 x 10 = 40 runs
PILOT2_NAME = "pilot2"

# Pilot 3 (15 Oct 2026, after pilot 2): the same four cells on ten new dev requests, run after the shared task text (version 3), the
# marker (version 5), the counter retry and the revised prompt doc and library. Not used in pilot 1 or 2, and not D01, D07 or D25 (the three
# queries the prompt doc carries in full). One per pattern the history covers (1-8, 11, 12), chosen to exercise the material fixes where the
# unused dev requests allow: whole fiscal weeks (D03, D18), a series that must stay inside complete periods (D22), "last year" and bare
# quarter or period phrases resolved against the received date (D08, D12, D27, D29, D35, D39), LFL asked by region (D08). The fifth fix, YTD to
# the end of a period, has no unused dev request: REQ-D09 is the only one and ran in pilot 2.
PILOT3_REQUEST_IDS = ("REQ-D03", "REQ-D08", "REQ-D12", "REQ-D15", "REQ-D18", "REQ-D22", "REQ-D27", "REQ-D29", "REQ-D35", "REQ-D39")
PILOT3_CELLS = (("sonnet", "S"), ("sonnet", "D"), ("sonnet", "L"), ("haiku", "L"))   # (agent model, arm); 4 x 10 = 40 runs
PILOT3_NAME = "pilot3"
