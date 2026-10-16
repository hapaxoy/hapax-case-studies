"""
build_features.py — Builds the snapshot feature table for the classical ML pipeline.


Snapshot design (the whole point of this script):
    For each account, the feature window ends TWO MONTHS BEFORE its churn month
    (churned accounts) or two months before its last observed month (retained
    accounts). This gives the model actionable lead time — it is never allowed
    to read usage data from the month immediately preceding churn (where the
    A4 "quietly unhappy" archetype's cliff drop lives) or any data after the
    snapshot date at all.

Feature families (per account, computed only from usage_monthly.csv rows with
month <= snapshot_end and tickets.csv rows with created_at <= snapshot_end):
    - Usage levels: last-3-month mean per metric
    - Usage trends: 3-month and 6-month fractional slopes per metric
    - Module mix shift: change in each module's share of total activity
      between the recent 3 months and the prior 3 months
    - Seat utilisation (active_users / licensed_seats): level and trend
    - Tenure, plan tier, ARR
    - Ticket metadata ONLY (counts, resolution days, resolved rate, csat) —
      NEVER subject/body text. That boundary belongs to the agent layer.

Run from the project root:
    python code/build_features.py

Output:
    data/model/features.csv
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Resolve paths — output directory is created fresh, never touches source data
# ---------------------------------------------------------------------------

SCRIPT_DIR   = Path(__file__).resolve().parent            # .../code/
PROJECT_ROOT = SCRIPT_DIR.parent                           # .../01 Churn/
DATA_DIR     = PROJECT_ROOT / "data"
MODEL_DIR    = DATA_DIR / "model"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

ACCOUNTS_PATH = DATA_DIR / "accounts.csv"
USAGE_PATH    = DATA_DIR / "usage_monthly.csv"
TICKETS_PATH  = DATA_DIR / "tickets.csv"
OUTPUT_PATH   = MODEL_DIR / "features.csv"

# Safety: confirm every output path is outside/different from every input path
for out_path in (OUTPUT_PATH,):
    for in_path in (ACCOUNTS_PATH, USAGE_PATH, TICKETS_PATH):
        assert out_path.resolve() != in_path.resolve(), (
            f"Refusing to run: output path {out_path} collides with input path {in_path}"
        )

sys.path.insert(0, str(SCRIPT_DIR))
import config  # noqa: E402  (must come after sys.path insert)

# ---------------------------------------------------------------------------
# Config block — everything tunable about the feature build lives here
# ---------------------------------------------------------------------------

SNAPSHOT_LEAD_MONTHS = 2          # feature window ends this many months before churn/censoring
LEVEL_WINDOW_MONTHS  = 3          # "recent" window for level means and mix-shift numerator
TREND_SHORT_MONTHS   = 3          # short trend window
TREND_LONG_MONTHS    = 6          # long trend window, also mix-shift denominator period
MIN_POINTS_FOR_SLOPE = 2          # minimum months required to fit a slope at all

USAGE_METRICS = [
    "active_users", "dashboard_views", "reports_created", "connector_syncs",
    "alerts_configured", "api_calls", "exports_run", "logins",
]

# The 6 core "module" metrics used for module-mix-shift features (active_users
# and logins are engagement metrics, not a specific product module, so they
# are excluded from the mix calculation but still get their own level/trend
# features above).
MODULE_METRICS = [
    "dashboard_views", "reports_created", "connector_syncs",
    "alerts_configured", "api_calls", "exports_run",
]

RETAINED_CENSOR_MONTH = pd.Timestamp(config.OBS_END + "-01")  # 2025-12-01: last month in the observation window

# Ticket metadata columns we are permitted to touch. subject/body must never
# appear anywhere below this line.
ALLOWED_TICKET_COLUMNS = ["ticket_id", "account_id", "created_at", "resolved", "resolution_days", "csat"]
FORBIDDEN_TICKET_COLUMNS = ["subject", "body", "channel", "module"]


# ---------------------------------------------------------------------------
# Load source data (read-only — never written back to)
# ---------------------------------------------------------------------------

def load_source_tables():
    """Loads accounts, usage, and tickets, parsing dates and dropping forbidden columns early."""
    print(f"Loading accounts from {ACCOUNTS_PATH}")
    accounts = pd.read_csv(ACCOUNTS_PATH, parse_dates=["signup_date", "churn_date"])

    print(f"Loading usage from {USAGE_PATH}")
    usage = pd.read_csv(USAGE_PATH)
    usage["month"] = pd.to_datetime(usage["month"], format="%Y-%m")

    print(f"Loading tickets from {TICKETS_PATH} (metadata columns only — text columns dropped immediately)")
    tickets_raw = pd.read_csv(TICKETS_PATH, parse_dates=["created_at"])
    # Hard guard: drop subject/body/channel/module the moment the file is read,
    # so no downstream code path can accidentally touch ticket text.
    tickets = tickets_raw[ALLOWED_TICKET_COLUMNS].copy()
    for forbidden_col in FORBIDDEN_TICKET_COLUMNS:
        assert forbidden_col not in tickets.columns, f"Forbidden ticket column leaked into working frame: {forbidden_col}"

    print(f"  accounts: {len(accounts)} rows | usage: {len(usage)} rows | tickets (metadata only): {len(tickets)} rows")
    return accounts, usage, tickets


# ---------------------------------------------------------------------------
# Snapshot date logic
# ---------------------------------------------------------------------------

def compute_snapshot_end(accounts: pd.DataFrame) -> pd.Series:
    """
    Computes each account's snapshot_end date: the last month of data the
    model is allowed to see.

    Churned accounts:  churn month minus SNAPSHOT_LEAD_MONTHS.
    Retained accounts: the observation window's last month minus SNAPSHOT_LEAD_MONTHS.
    """
    churn_month = accounts["churn_date"].dt.to_period("M")
    snapshot_if_churned = (churn_month - SNAPSHOT_LEAD_MONTHS).dt.to_timestamp()

    retained_month = RETAINED_CENSOR_MONTH.to_period("M")
    snapshot_if_retained = (retained_month - SNAPSHOT_LEAD_MONTHS).to_timestamp()

    snapshot_end = np.where(accounts["churned"], snapshot_if_churned, snapshot_if_retained)
    return pd.to_datetime(snapshot_end)


# ---------------------------------------------------------------------------
# Per-account windowed usage helpers
# ---------------------------------------------------------------------------

def slope_per_month(values: np.ndarray) -> float:
    """
    Fits a simple linear trend (ordinary least squares) to a short series and
    returns the fractional (relative) slope: raw slope divided by the mean
    level in the window, so a metric's trend is comparable across accounts of
    very different size (Standard vs Enterprise). Returns NaN when there are
    not enough points, or when the mean level is ~0 (division guard).
    """
    n = len(values)
    if n < MIN_POINTS_FOR_SLOPE:
        return np.nan
    mean_level = np.mean(values)
    if abs(mean_level) < 1e-6:
        return np.nan
    month_index = np.arange(n)
    raw_slope = np.polyfit(month_index, values, 1)[0]
    return raw_slope / mean_level


def compute_seasonal_index(usage: pd.DataFrame) -> dict:
    """
    Empirically estimates a per-metric, per-calendar-month seasonal index from
    the full usage panel (portfolio-wide, not per-account or per-label -- this
    uses no churn outcome and is the same kind of "day-of-week"/"month-of-year"
    fixed effect a real BI vendor would maintain from aggregate telemetry).

    Why this is necessary: the product has a real built-in "summer dip"
    seasonal pattern. Retained accounts in this dataset are ALWAYS snapshotted
    at the same fixed calendar window (Aug-Oct, two months before the
    observation window's end), while churned accounts are snapshotted at
    scattered calendar months tied to their individual churn dates. That
    means the seasonal cycle's phase at snapshot time is systematically
    different between survivors and churners as a GROUP, purely as a
    calendar artefact -- e.g. Aug-Oct sits on the recovering half of the
    cosine (post-July-trough), so every retained account's raw 3-month trend
    gets a deterministic upward nudge that has nothing to do with its actual
    behaviour. Deseasonalising before computing level/trend features removes
    this artefact the same way a competent analyst would deseasonalise
    monthly revenue before reading a trend off it.
    """
    usage = usage.copy()
    usage["calendar_month"] = usage["month"].dt.month
    seasonal_index = {}
    for metric in USAGE_METRICS:
        account_mean = usage.groupby("account_id")[metric].transform("mean")
        ratio = usage[metric] / account_mean.replace(0, np.nan)
        monthly_index = ratio.groupby(usage["calendar_month"]).median()
        monthly_index = monthly_index.reindex(range(1, 13))
        monthly_index = monthly_index.fillna(1.0)
        monthly_index = monthly_index / monthly_index.mean()  # normalise so the 12 indices average to 1.0
        seasonal_index[metric] = monthly_index.to_dict()
    return seasonal_index


def deseasonalize(values: np.ndarray, calendar_months: np.ndarray, metric: str, seasonal_index: dict) -> np.ndarray:
    """Divides each monthly value by the empirically estimated seasonal index for its calendar month."""
    factors = np.array([seasonal_index[metric].get(m, 1.0) for m in calendar_months], dtype=float)
    factors = np.where(factors <= 0, 1.0, factors)
    return values / factors


def compute_usage_features_for_account(account_usage: pd.DataFrame, seasonal_index: dict) -> dict:
    """
    Computes level/trend features for one account from its already-windowed
    usage rows (must already be filtered to month <= snapshot_end and sorted
    ascending by month before this is called). All values are deseasonalised
    first (see compute_seasonal_index) so trends reflect genuine behaviour,
    not the calendar phase the snapshot happens to land on.
    """
    features = {}
    n_available = len(account_usage)
    calendar_months = account_usage["month"].dt.month.to_numpy()

    recent_3m = account_usage.tail(LEVEL_WINDOW_MONTHS)
    recent_6m = account_usage.tail(TREND_LONG_MONTHS)
    recent_3m_cal = calendar_months[-LEVEL_WINDOW_MONTHS:]
    recent_6m_cal = calendar_months[-TREND_LONG_MONTHS:]

    deseason_3m_by_metric = {}
    deseason_6m_by_metric = {}
    for metric in USAGE_METRICS:
        deseason_3m = deseasonalize(recent_3m[metric].to_numpy(dtype=float), recent_3m_cal, metric, seasonal_index)
        deseason_6m = deseasonalize(recent_6m[metric].to_numpy(dtype=float), recent_6m_cal, metric, seasonal_index)
        deseason_3m_by_metric[metric] = deseason_3m
        deseason_6m_by_metric[metric] = deseason_6m

        features[f"{metric}_level_3m_mean"] = deseason_3m.mean()
        features[f"{metric}_trend_pct_3m"] = slope_per_month(deseason_3m)
        features[f"{metric}_trend_pct_6m"] = slope_per_month(deseason_6m)

    # Seat utilisation: active_users / licensed_seats is computed later once
    # licensed_seats is merged in (kept out of this per-account usage-only
    # helper to avoid duplicating the accounts join here).

    # Module mix shift: share of total (deseasonalised) module activity,
    # recent 3m vs the 3m immediately prior to that (months 4-6 back).
    module_totals_recent = pd.Series({m: deseason_3m_by_metric[m].sum() for m in MODULE_METRICS})
    recent_sum = module_totals_recent.sum()
    recent_share = (module_totals_recent / recent_sum) if recent_sum > 0 else pd.Series(np.nan, index=MODULE_METRICS)

    prior_3m = account_usage.iloc[max(0, n_available - TREND_LONG_MONTHS): max(0, n_available - LEVEL_WINDOW_MONTHS)]
    if len(prior_3m) >= 2:  # require at least 2 months for a meaningful "prior" share
        prior_cal = prior_3m["month"].dt.month.to_numpy()
        module_totals_prior = pd.Series({
            m: deseasonalize(prior_3m[m].to_numpy(dtype=float), prior_cal, m, seasonal_index).sum()
            for m in MODULE_METRICS
        })
        prior_sum = module_totals_prior.sum()
        prior_share = (module_totals_prior / prior_sum) if prior_sum > 0 else pd.Series(np.nan, index=MODULE_METRICS)
    else:
        prior_share = pd.Series(np.nan, index=MODULE_METRICS)

    for module_metric in MODULE_METRICS:
        features[f"mix_share_shift_{module_metric}"] = recent_share[module_metric] - prior_share[module_metric]

    features["n_usage_months_available"] = n_available  # diagnostic only, dropped before modelling
    return features


# ---------------------------------------------------------------------------
# Per-account windowed ticket helpers
# ---------------------------------------------------------------------------

def compute_ticket_features_for_account(account_tickets: pd.DataFrame, snapshot_end: pd.Timestamp) -> dict:
    """
    Computes ticket METADATA features only (counts, resolution days, resolved
    rate, csat) from tickets already filtered to created_at <= snapshot_end
    (both bounds are the CALENDAR MONTH cutoff -- see ticket_cutoff below --
    not just the first day of the snapshot month, since usage rows are
    monthly aggregates but ticket dates are exact days within a month).
    Handles sparsity explicitly: csat is rarely filled in, so we report both
    the mean (NaN when no responses exist) and a response-count column so the
    model can see how much csat evidence backs the mean.

    Also reports LIFETIME (signup-to-snapshot) ticket metadata alongside the
    trailing-window figures, for transparency and comparison.

    Historical note: an earlier data-generation defect clustered most tickets
    for non-churning archetypes within roughly the first two months after
    signup, which made trailing-window ticket features a disguised churn
    proxy (a long-tenured survivor's trailing window saw almost no tickets
    purely because of when its tickets happened to have been generated, not
    because it was quiet) -- the *_lifetime columns were introduced as a
    workaround, immune to that clustering. The defect has since been fixed
    at source: ticket dates are now spread realistically across each
    account's life for every archetype. train_models.py verifies this
    empirically (trailing-window ticket counts by archetype no longer show
    mechanical churn/non-churn separation) before re-admitting the
    trailing-window features to the trained model. Both families are kept
    here so that check, and any future one, has something to check against.
    """
    features = {}

    window_6m_start = snapshot_end - pd.DateOffset(months=TREND_LONG_MONTHS - 1)
    window_3m_start = snapshot_end - pd.DateOffset(months=LEVEL_WINDOW_MONTHS - 1)

    tickets_6m = account_tickets[account_tickets["created_at"] >= window_6m_start]
    tickets_3m = account_tickets[account_tickets["created_at"] >= window_3m_start]

    # Lifetime (signup through snapshot_end) ticket metadata -- robust to the
    # windowing/clustering issue described above.
    features["ticket_count_lifetime"] = len(account_tickets)
    features["unresolved_count_lifetime"] = int((~account_tickets["resolved"]).sum()) if len(account_tickets) > 0 else 0
    features["resolved_rate_lifetime"] = account_tickets["resolved"].mean() if len(account_tickets) > 0 else np.nan
    features["mean_resolution_days_lifetime"] = account_tickets["resolution_days"].mean()
    features["mean_csat_lifetime"] = account_tickets["csat"].mean()
    features["csat_response_count_lifetime"] = int(account_tickets["csat"].notna().sum())

    features["ticket_count_3m"] = len(tickets_3m)
    features["ticket_count_6m"] = len(tickets_6m)
    features["has_tickets_6m"] = int(len(tickets_6m) > 0)

    # Tickets-per-month trend: bucket the 6m window into calendar months and
    # fit a slope on monthly counts (raw slope, not fractional — count-based
    # series routinely include zero months, which breaks the fractional
    # normalisation used for usage metrics).
    if len(tickets_6m) > 0:
        monthly_counts = (
            tickets_6m.assign(month=tickets_6m["created_at"].dt.to_period("M"))
            .groupby("month").size()
        )
        full_month_range = pd.period_range(end=snapshot_end.to_period("M"), periods=TREND_LONG_MONTHS, freq="M")
        monthly_counts = monthly_counts.reindex(full_month_range, fill_value=0)
        if len(monthly_counts) >= MIN_POINTS_FOR_SLOPE:
            features["tickets_per_month_trend"] = np.polyfit(np.arange(len(monthly_counts)), monthly_counts.to_numpy(dtype=float), 1)[0]
        else:
            features["tickets_per_month_trend"] = np.nan
    else:
        features["tickets_per_month_trend"] = 0.0  # no tickets at all -> flat zero trend, not missing

    features["unresolved_count_6m"] = int((~tickets_6m["resolved"]).sum()) if len(tickets_6m) > 0 else 0
    features["resolved_rate_6m"] = tickets_6m["resolved"].mean() if len(tickets_6m) > 0 else np.nan
    features["mean_resolution_days_6m"] = tickets_6m["resolution_days"].mean()  # NaN if no resolved tickets have a value
    features["mean_csat_6m"] = tickets_6m["csat"].mean()  # NaN when nobody filled it in — sparsity is expected
    features["csat_response_count_6m"] = int(tickets_6m["csat"].notna().sum())

    return features


# ---------------------------------------------------------------------------
# Main feature build
# ---------------------------------------------------------------------------

def build_features(accounts: pd.DataFrame, usage: pd.DataFrame, tickets: pd.DataFrame) -> pd.DataFrame:
    """Builds the full snapshot feature table, one row per account."""
    accounts = accounts.copy()
    accounts["snapshot_end"] = compute_snapshot_end(accounts)

    print("Estimating portfolio-wide seasonal index per metric (for deseasonalising trend features)...")
    seasonal_index = compute_seasonal_index(usage)

    rows = []
    print(f"Building features for {len(accounts)} accounts...")

    for i, account in enumerate(accounts.itertuples(index=False), start=1):
        account_id = account.account_id
        snapshot_end = account.snapshot_end

        # Usage rows are monthly aggregates keyed to the first of the month, so
        # "month <= snapshot_end" already includes the whole snapshot month.
        # Ticket dates are exact days within a month, so the equivalent cutoff
        # is the LAST calendar day of the snapshot month -- comparing against
        # the first-of-month snapshot_end would silently drop all but day 1 of
        # the snapshot month's tickets.
        ticket_cutoff = snapshot_end + pd.offsets.MonthEnd(0)

        # --- Leakage guard: filter usage/tickets strictly to <= snapshot cutoff ---
        account_usage = usage[(usage["account_id"] == account_id) & (usage["month"] <= snapshot_end)].sort_values("month")
        account_tickets = tickets[(tickets["account_id"] == account_id) & (tickets["created_at"] <= ticket_cutoff)].sort_values("created_at")

        # Hard assertions: nothing past the snapshot date made it into the window
        if len(account_usage) > 0:
            assert account_usage["month"].max() <= snapshot_end, f"{account_id}: usage leakage past snapshot_end"
        if len(account_tickets) > 0:
            assert account_tickets["created_at"].max() <= ticket_cutoff, f"{account_id}: ticket leakage past snapshot_end"

        row = {
            "account_id": account_id,
            "snapshot_end": snapshot_end,
            "tenure_months": (snapshot_end.to_period("M") - account.signup_date.to_period("M")).n,
            "plan_tier": account.plan_tier,
            "arr_eur": account.arr_eur,
            "licensed_seats": account.licensed_seats,
            "churned": bool(account.churned),
        }

        if len(account_usage) == 0:
            # Should not happen given >=5 months available for every account
            # in this dataset, but fail loudly rather than silently zero-fill.
            raise ValueError(f"{account_id}: no usage rows available at or before snapshot_end={snapshot_end.date()}")

        row.update(compute_usage_features_for_account(account_usage, seasonal_index))

        # Seat utilisation, computed here since it needs licensed_seats from
        # accounts. active_users is deseasonalised first for the same reason
        # every other usage trend feature is (see compute_seasonal_index).
        calendar_months = account_usage["month"].dt.month.to_numpy()
        deseason_active_users = deseasonalize(
            account_usage["active_users"].to_numpy(dtype=float), calendar_months, "active_users", seasonal_index
        )
        seat_util_series = deseason_active_users / account.licensed_seats
        recent_3m_util = seat_util_series[-LEVEL_WINDOW_MONTHS:]
        recent_6m_util = seat_util_series[-TREND_LONG_MONTHS:]
        row["seat_utilisation_level_3m_mean"] = recent_3m_util.mean()
        row["seat_utilisation_trend_pct_3m"] = slope_per_month(recent_3m_util)
        row["seat_utilisation_trend_pct_6m"] = slope_per_month(recent_6m_util)

        row.update(compute_ticket_features_for_account(account_tickets, snapshot_end))

        rows.append(row)

        if i % 100 == 0 or i == len(accounts):
            print(f"  ...{i}/{len(accounts)} accounts featurised")

    features_df = pd.DataFrame(rows)

    # One-hot encode plan tier (small, fixed cardinality — safe to do here
    # rather than leaving it to the training script)
    plan_dummies = pd.get_dummies(features_df["plan_tier"], prefix="plan_tier")
    features_df = pd.concat([features_df, plan_dummies], axis=1)

    return features_df


# ---------------------------------------------------------------------------
# Validation pass — a features table that fails these checks is a bug
# ---------------------------------------------------------------------------

def validate_features(features_df: pd.DataFrame, accounts: pd.DataFrame) -> None:
    """Runs the coherence/leakage assertions this build is required to satisfy."""
    print("Running validation pass on features.csv...")

    assert len(features_df) == len(accounts), (
        f"Row count mismatch: {len(features_df)} feature rows vs {len(accounts)} accounts"
    )
    assert set(features_df["account_id"]) == set(accounts["account_id"]), "account_id sets do not match"

    # No forbidden identity/label/text columns anywhere in the output
    forbidden_columns = {
        "archetype", "planted_signals", "churn_driver", "company_name",
        "subject", "body", "channel", "module", "churn_date", "industry", "country",
    }
    leaked = forbidden_columns & set(features_df.columns)
    assert not leaked, f"Forbidden columns present in features.csv: {leaked}"

    # Label integrity: churned flag in features must match accounts.csv exactly
    merged = features_df.merge(accounts[["account_id", "churned"]], on="account_id", suffixes=("_features", "_accounts"))
    assert (merged["churned_features"] == merged["churned_accounts"]).all(), "churned label mismatch vs accounts.csv"

    # Snapshot date sanity: retained accounts snapshot_end is fixed; churned
    # accounts snapshot_end must sit exactly SNAPSHOT_LEAD_MONTHS before churn month
    acc = accounts.set_index("account_id")
    feat = features_df.set_index("account_id")
    for account_id in feat.index:
        row_churned = bool(acc.loc[account_id, "churned"])
        snapshot_end = feat.loc[account_id, "snapshot_end"]
        if row_churned:
            expected = (acc.loc[account_id, "churn_date"].to_period("M") - SNAPSHOT_LEAD_MONTHS).to_timestamp()
        else:
            expected = (RETAINED_CENSOR_MONTH.to_period("M") - SNAPSHOT_LEAD_MONTHS).to_timestamp()
        assert snapshot_end == expected, f"{account_id}: snapshot_end mismatch (got {snapshot_end}, expected {expected})"

    assert (feat["tenure_months"] > 0).all(), "Found accounts with non-positive tenure_months at snapshot"

    # Sanity ranges (soft checks reported, not fatal, since real distributions vary)
    seat_util = feat["seat_utilisation_level_3m_mean"]
    out_of_range = seat_util[(seat_util < 0) | (seat_util > 3)]  # >100% seat utilisation is plausible (shared logins) but >300% is suspicious
    if len(out_of_range) > 0:
        print(f"  WARNING: {len(out_of_range)} accounts have seat utilisation > 300% or < 0 — investigate: {list(out_of_range.index)}")

    print(f"  Validation passed: {len(features_df)} accounts, {features_df.shape[1]} columns, no leakage detected.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    try:
        accounts, usage, tickets = load_source_tables()
        features_df = build_features(accounts, usage, tickets)
        validate_features(features_df, accounts)

        # Drop the diagnostic-only column before writing (not a modelling feature)
        features_df = features_df.drop(columns=["n_usage_months_available"])

        features_df.to_csv(OUTPUT_PATH, index=False)
        print(f"\nWrote {len(features_df)} rows x {features_df.shape[1]} columns to {OUTPUT_PATH}")
        print(f"Churn rate in feature table: {features_df['churned'].mean():.1%}")

    except FileNotFoundError as e:
        print(f"ERROR: required input file not found — {e}")
        sys.exit(1)
    except AssertionError as e:
        print(f"VALIDATION FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: unexpected failure building features — {e}")
        raise


if __name__ == "__main__":
    main()
