"""
config.py — All tunable parameters for the Kataja Analytics synthetic dataset.

Everything that controls the shape of the data lives here.
Logic lives in generate_structured.py and generate_ticket_briefs.py.
"""

# ---------------------------------------------------------------------------
# Global settings
# ---------------------------------------------------------------------------

RANDOM_SEED = 42
N_ACCOUNTS = 500

# Observation window (in-world calendar)
OBS_START = "2024-01"   # first possible month of data
OBS_END   = "2025-12"   # last possible month of data

# Signup dates roll over the first 12 months (Jan 2024 – Dec 2024)
SIGNUP_WINDOW_START = "2024-01-01"
SIGNUP_WINDOW_END   = "2024-12-31"

# Churn events may not occur before this many months post-signup
MIN_MONTHS_BEFORE_CHURN = 6

# ---------------------------------------------------------------------------
# Product feature map
# ---------------------------------------------------------------------------
# Shared vocabulary used in both structured (column names) and ticket briefs.

FEATURE_MAP = {
    "Dashboards": {
        "metric": "dashboard_views",
        "ticket_themes": ["dashboard slow to load", "can't share dashboard", "dashboard not updating"],
    },
    "Report builder": {
        "metric": "reports_created",
        "ticket_themes": ["report builder crashes", "can't schedule monthly report", "report formatting broken"],
    },
    "Data connectors": {
        "metric": "connector_syncs",
        "ticket_themes": ["SAP connector keeps failing", "sync delayed again", "connector authentication error"],
    },
    "Alerts": {
        "metric": "alerts_configured",
        "ticket_themes": ["alert didn't fire", "too many false alerts", "alert threshold not saving"],
    },
    "API": {
        "metric": "api_calls",
        "ticket_themes": ["API rate limits", "breaking change in v2", "API key rotation help"],
    },
    "Admin & seats": {
        "metric": "active_users",   # secondary metric: licensed_seats
        "ticket_themes": ["can't deactivate user", "SSO setup help", "billing query"],
    },
    "Exports": {
        "metric": "exports_run",
        "ticket_themes": ["Excel export mangles formatting", "PDF export blank", "export queue stuck"],
    },
}

MODULE_NAMES = list(FEATURE_MAP.keys())

# ---------------------------------------------------------------------------
# Plan tiers and ARR ranges (EUR)
# ---------------------------------------------------------------------------

PLAN_TIERS = {
    "Standard":     {"arr_min": 12_000,  "arr_max": 30_000,  "seats_min": 10, "seats_max": 40},
    "Professional": {"arr_min": 30_001,  "arr_max": 80_000,  "seats_min": 30, "seats_max": 100},
    "Enterprise":   {"arr_min": 80_001,  "arr_max": 200_000, "seats_min": 80, "seats_max": 200},
}

# Distribution of plan tiers across all accounts
PLAN_TIER_WEIGHTS = {
    "Standard":     0.50,
    "Professional": 0.35,
    "Enterprise":   0.15,
}

# ---------------------------------------------------------------------------
# Fictional competitor list (for planted text signals)
# ---------------------------------------------------------------------------

COMPETITORS = {
    "Storsund BI": "cheaper, simpler rival — mentioned by price-sensitive accounts",
    "Dashlume": "slicker, better-marketed rival — mentioned by accounts frustrated with UX",
    "Excel":     "going back to spreadsheets — the real competitor, as in life",
}

COMPETITOR_NAMES = list(COMPETITORS.keys())

# ---------------------------------------------------------------------------
# Company name components (Nordic / European mid-market B2B)
# ---------------------------------------------------------------------------
# Used by generate_structured.py to build plausible company names.

# Roster of invented stems. rng.choice picks by index, so the list lengths fix the draw.
# Many stems repeat by design (account_id is the key).
COMPANY_PREFIXES_BY_COUNTRY = {
    "FI": ["Kaarnikko", "Lumikarpalo", "Tuohisalo", "Kaarnikko", "Lumikarpalo", "Tuohisalo", "Kaarnikko", "Lumikarpalo", "Tuohisalo", "Kaarnikko", "Lumikarpalo", "Tuohisalo", "Kaarnikko", "Lumikarpalo", "Tuohisalo"],
    "SE": ["Fjällbris", "Vittmora", "Stensvala", "Granlöja", "Ekbrinken", "Ljungsvala", "Fjällbris", "Vittmora", "Stensvala", "Granlöja", "Ekbrinken", "Ljungsvala"],
    "NO": ["Fonnhaug", "Myrbrekk", "Elvesnø", "Fonnhaug", "Myrbrekk", "Elvesnø", "Fonnhaug", "Myrbrekk", "Elvesnø", "Fonnhaug", "Myrbrekk", "Elvesnø"],
    "DK": ["Klintvæld", "Marskhøj", "Fjordlyng", "Engbakkerup", "Strandkær", "Klintvæld", "Marskhøj", "Fjordlyng", "Engbakkerup", "Strandkær"],
    "DE": ["Weidenhang", "Talbrunn", "Weidenhang", "Talbrunn", "Weidenhang", "Talbrunn", "Weidenhang", "Talbrunn", "Weidenhang", "Talbrunn", "Weidenhang", "Talbrunn"],
    "NL": ["Veenhorst", "Duinwaard", "Kreekdal", "Lindewaal", "Zeggeveld", "Kwelderhof", "Veenhorst", "Duinwaard", "Kreekdal", "Lindewaal"],
    "EE": ["Sammalpere", "Kadakmetsa", "Sammalranna", "Sammalpere", "Kadakmetsa", "Sammalranna", "Sammalpere", "Kadakmetsa", "Sammalranna", "Sammalpere"],
}

# The headline account of the case has a fixed name, applied after the name draw, so no random
# draw changes.
HEADLINE_NAME_OVERRIDES = {"ACC0013": "Hedbrunn Systems AB"}

COMPANY_SUFFIXES_BY_COUNTRY = {
    "FI": ["Oy", "Oy Ab", "Oyj"],
    "SE": ["AB", "AB"],
    "NO": ["AS", "AS"],
    "DK": ["A/S", "ApS"],
    "DE": ["GmbH", "GmbH & Co. KG", "AG"],
    "NL": ["B.V.", "N.V."],
    "EE": ["OÜ", "AS"],
}

INDUSTRIES = [
    "Manufacturing", "Logistics & Supply Chain", "Financial Services", "Retail & E-commerce",
    "Construction", "Healthcare", "Professional Services", "Technology",
    "Energy & Utilities", "Real Estate", "Media & Publishing", "Public Sector",
]

INDUSTRY_MID_COMPONENTS = [
    "Components", "Logistics", "Capital", "Solutions", "Systems", "Services",
    "Industries", "Group", "Partners", "Networks", "Technologies", "Dynamics",
    "Consulting", "Ventures", "Holdings",
]

COUNTRY_WEIGHTS = {
    "FI": 0.25,
    "SE": 0.25,
    "NO": 0.15,
    "DK": 0.10,
    "DE": 0.12,
    "NL": 0.08,
    "EE": 0.05,
}

# ---------------------------------------------------------------------------
# Archetype definitions
# ---------------------------------------------------------------------------
# Each archetype controls both the usage generation and the ticket brief
# generation.  All proportions sum to 1.0.

ARCHETYPE_PROPORTIONS = {
    "A1": 0.35,   # Healthy stable — no churn
    "A2": 0.10,   # Healthy growing — no churn
    "A3": 0.12,   # Slow decay — churns, both ML + agent catch
    "A4": 0.08,   # Quietly unhappy — churns, AGENT ONLY catches
    "A5": 0.05,   # Sudden death — churns, NEITHER catches (honest ceiling)
    "A6": 0.10,   # Saved account — dip then recovery, no churn
    "A7": 0.12,   # Loud but loyal — healthy usage, angry tickets, no churn
    "A8": 0.08,   # Quiet decline stays — usage down, sparse neutral tickets, no churn
}

ARCHETYPE_CHURNS = {
    "A1": False,
    "A2": False,
    "A3": True,
    "A4": True,
    "A5": True,
    "A6": False,
    "A7": False,
    "A8": False,
}

# Per-archetype usage parameters.
# base_*: multiplier on the plan-tier base levels below
# trend_per_month: fractional change per month (+ = growth, - = decay)
# noise_std: std-dev of per-month Gaussian noise (fraction of current level)
# seasonality_amplitude: fraction of annual sinusoidal swing (summer dip)
# decline_start_frac: fraction into account lifetime when decline begins (A3, A4, A8, A6 dip)
# recovery_start_frac: fraction into lifetime when recovery begins (A6 only)
# clamp_min: floor on any metric (avoids negatives)

ARCHETYPE_USAGE_PARAMS = {
    "A1": {
        "trend_per_month":      0.005,    # slight natural growth
        "noise_std":            0.08,
        "seasonality_amplitude": 0.10,
        "decline_start_frac":   None,
        "recovery_start_frac":  None,
        "clamp_min":            1,
    },
    "A2": {
        "trend_per_month":      0.025,    # healthy growth
        "noise_std":            0.07,
        "seasonality_amplitude": 0.08,
        "decline_start_frac":   None,
        "recovery_start_frac":  None,
        "clamp_min":            1,
    },
    "A3": {
        "trend_per_month":      -0.055,   # visible multi-month decline across most modules
        "noise_std":            0.09,
        "seasonality_amplitude": 0.10,
        "decline_start_frac":   0.35,     # decline starts ~35% into tenure
        "recovery_start_frac":  None,
        "clamp_min":            0,
        # logins decay more slowly than feature usage (people log in, look, leave)
        "logins_trend_per_month": -0.020,
        # modules that collapse hard vs those that linger
        "collapse_modules": ["reports_created", "connector_syncs", "alerts_configured"],
        "linger_modules":   ["dashboard_views", "logins"],
    },
    "A4": {
        "trend_per_month":      0.004,    # normal — indistinguishable from A1 until cliff
        "noise_std":            0.06,     # tighter noise than A1 so random drift doesn't
                                          # create detectable trends
        "seasonality_amplitude": 0.05,   # deliberately mild — A4 is a feature-rich account
                                          # that uses the product year-round
        "decline_start_frac":   None,     # NO decline until the very last month
        "recovery_start_frac":  None,
        "cliff_frac":           0.95,     # kept for config completeness; logic uses index
        "cliff_drop":           0.45,     # usage drops ~45% in the last recorded month
        "clamp_min":            1,
    },
    "A5": {
        "trend_per_month":      0.004,    # normal throughout
        "noise_std":            0.08,
        "seasonality_amplitude": 0.09,
        "decline_start_frac":   None,
        "recovery_start_frac":  None,
        "clamp_min":            1,
    },
    "A6": {
        "trend_per_month":      0.005,    # baseline healthy, then dip, then recovery
        "noise_std":            0.09,
        "seasonality_amplitude": 0.10,
        "decline_start_frac":   0.30,     # dip starts at ~30% of tenure
        "recovery_start_frac":  0.55,     # recovery starts at ~55% of tenure
        "dip_depth":            0.45,     # maximum decline fraction during dip
        "recovery_strength":    0.85,     # recovery back toward pre-dip levels
        "clamp_min":            1,
    },
    "A7": {
        "trend_per_month":      0.010,    # healthy, steady
        "noise_std":            0.08,
        "seasonality_amplitude": 0.09,
        "decline_start_frac":   None,
        "recovery_start_frac":  None,
        "clamp_min":            2,
    },
    "A8": {
        "trend_per_month":      -0.030,   # quiet usage decline
        "noise_std":            0.08,
        "seasonality_amplitude": 0.12,    # slightly stronger seasonality — suggests seasonal role change
        "decline_start_frac":   0.25,     # decline starts fairly early
        "recovery_start_frac":  None,
        "clamp_min":            0,
    },
}

# Base usage levels per plan tier (absolute values, pre-trend/noise)
PLAN_BASE_USAGE = {
    "Standard": {
        "active_users":       12,
        "dashboard_views":    85,
        "reports_created":    18,
        "connector_syncs":    45,
        "alerts_configured":  8,
        "api_calls":          120,
        "exports_run":        22,
        "logins":             95,
    },
    "Professional": {
        "active_users":       35,
        "dashboard_views":    210,
        "reports_created":    45,
        "connector_syncs":    130,
        "alerts_configured":  22,
        "api_calls":          480,
        "exports_run":        58,
        "logins":             260,
    },
    "Enterprise": {
        "active_users":       90,
        "dashboard_views":    520,
        "reports_created":    110,
        "connector_syncs":    380,
        "alerts_configured":  55,
        "api_calls":          1400,
        "exports_run":        145,
        "logins":             640,
    },
}

# ---------------------------------------------------------------------------
# Ticket brief parameters
# ---------------------------------------------------------------------------

# Median tickets per account per archetype (actual counts drawn from negative-binomial)
#
# A4 ("quietly unhappy") — REDESIGNED LOW-VOLUME (see
# ml_report.md's v1->v3 trail and code/regenerate_a4_briefs.py). Three
# generations of metadata quieting (csat, then resolved/resolution_days)
# failed to make A4 invisible to the classical model because A4's TICKET
# VOLUME itself (~6.7 tickets in the trailing 6-month feature window vs
# A1's ~1.0) was the residual fingerprint — see ml_report.md "A4 before ->
# after". Fix: A4 accounts now file FEW tickets, like a healthy
# account in volume (median/max below dropped from 11/28 to ~4/6). This
# entry is kept for reference/consistency with the other archetypes' shape,
# but A4 briefs are no longer generated by generate_ticket_briefs.py's
# generic Poisson draw — see A4_LOW_VOLUME_TICKET_PARAMS below, which is
# what code/regenerate_a4_briefs.py actually uses (a hand-built arc/window
# scheme, not this median/dispersion/max shape, because the low-volume
# design needs explicit control over how many tickets fall inside vs.
# outside the 6-month feature window, not just a total count).
ARCHETYPE_TICKET_PARAMS = {
    "A1": {"median": 4,  "dispersion": 1.5, "max": 14},
    "A2": {"median": 5,  "dispersion": 1.5, "max": 16},
    "A3": {"median": 9,  "dispersion": 1.5, "max": 24},
    "A4": {"median": 4,  "dispersion": 1.3, "max": 6},
    "A5": {"median": 3,  "dispersion": 2.0, "max": 10},
    "A6": {"median": 14, "dispersion": 1.2, "max": 35},
    "A7": {"median": 16, "dispersion": 1.2, "max": 40},
    "A8": {"median": 4,  "dispersion": 1.5, "max": 12},
}

# A4 low-volume brief generation parameters (code/regenerate_a4_briefs.py).
# Total tickets per A4 account across its whole life: Poisson(lambda),
# clipped to [min_total, max_total] -- targets ~4-5 tickets per account.
# Of those, most fall inside the trailing 6-month feature window (window
# ends SNAPSHOT_LEAD_MONTHS before churn, spans WINDOW_MONTHS backward from
# there) -- the design goal is ~2-3 in-window tickets, matching A1/A8
# levels, with the remainder dated earlier in the account's life (the
# "early neutral" stage of the frustration arc). snapshot_lead_months and
# window_months MUST mirror build_features.py's SNAPSHOT_LEAD_MONTHS and
# TREND_LONG_MONTHS -- if those change, update here too.
A4_LOW_VOLUME_TICKET_PARAMS = {
    "poisson_lambda":       4.3,
    "min_total":            3,
    "max_total":            6,
    "early_count_low_n":    1,    # tickets dated before the window, when total <= 4
    "early_count_high_n":   2,    # tickets dated before the window, when total >= 5
    "early_high_n_threshold": 5,  # total tickets at/above this uses early_count_high_n
    "snapshot_lead_months": 2,    # mirrors build_features.py SNAPSHOT_LEAD_MONTHS
    "window_months":        6,    # mirrors build_features.py TREND_LONG_MONTHS
}

# Sentiment stage definitions (used in ticket brief arc fields)
# The arc encodes progression of sentiment over the account's lifetime.
ARCHETYPE_TICKET_ARCS = {
    "A1": ["neutral", "neutral", "routine"],
    "A2": ["positive", "feature_request", "positive"],
    "A3": ["neutral", "frustrated", "angry", "resigned"],
    "A4": ["neutral", "mild_frustration", "frustrated", "competitor_mention", "unresolved_complaint"],
    "A5": ["neutral", "routine"],                    # no signal
    "A6": ["frustrated", "angry", "escalation", "resolution", "positive", "calm"],
    "A7": ["angry_resolved", "angry_resolved", "angry_resolved"],   # always fast-resolved
    "A8": ["neutral", "routine", "neutral"],
}

# Planted signal types (appear in answer_key.csv planted_signals column)
PLANTED_SIGNAL_TYPES = {
    "A4": ["competitor_mention", "unresolved_complaint", "frustration_escalation"],
    "A6": ["escalation", "resolution", "recovery"],
    "A7": ["fast_resolution"],
    "A3": ["frustration_escalation", "module_specific_decline"],
    "A5": [],
}

# Noise competitor mentions in healthy accounts so agent can't just grep
# Fraction of healthy accounts (A1, A2, A7) that get 1 benign competitor mention
NOISE_COMPETITOR_MENTION_RATE = 0.15

# Churn driver labels for the answer key
CHURN_DRIVERS = {
    "A3": "usage_decay",
    "A4": "relationship_breakdown",
    "A5": "external_event",       # acquisition, budget cut, champion leaves
}

# ---------------------------------------------------------------------------
# Output paths (relative to the project root — resolved in each script)
# ---------------------------------------------------------------------------

OUTPUT_DATA_DIR  = "data"
OUTPUT_CODE_DIR  = "code"
