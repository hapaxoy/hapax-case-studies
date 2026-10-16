"""
generate_structured.py — Generates accounts.csv, usage_monthly.csv, answer_key.csv.

Fictional company: Kataja Analytics Oy (Helsinki-based B2B SaaS, BI/reporting platform).
Observation window: Jan 2024 – Dec 2025 (24 months).
Accounts: 500, across 8 archetypes, ~25% churn.

Run from the project root:
    python code/generate_structured.py

Outputs (written to data/ folder next to this script's parent):
    data/accounts.csv
    data/usage_monthly.csv
    data/answer_key.csv
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Resolve paths
# ---------------------------------------------------------------------------

SCRIPT_DIR   = Path(__file__).resolve().parent           # .../code/
PROJECT_ROOT = SCRIPT_DIR.parent                          # .../01 Churn/
DATA_DIR     = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Add code dir to path so we can import config
sys.path.insert(0, str(SCRIPT_DIR))
import config

# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------

rng = np.random.default_rng(config.RANDOM_SEED)

# ---------------------------------------------------------------------------
# Helper: draw archetype labels for N_ACCOUNTS
# ---------------------------------------------------------------------------

def assign_archetypes(n_accounts: int, rng: np.random.Generator) -> list[str]:
    """Draw archetype labels respecting the proportions in config."""
    archetypes = list(config.ARCHETYPE_PROPORTIONS.keys())
    weights    = list(config.ARCHETYPE_PROPORTIONS.values())
    labels = rng.choice(archetypes, size=n_accounts, p=weights)
    print(f"  Archetype distribution: {dict(zip(*np.unique(labels, return_counts=True)))}")
    return list(labels)


# ---------------------------------------------------------------------------
# Helper: generate company names
# ---------------------------------------------------------------------------

def make_company_name(country: str, industry: str, rng: np.random.Generator) -> str:
    """Build a plausible Nordic/European B2B company name for the given country."""
    prefix_list = config.COMPANY_PREFIXES_BY_COUNTRY[country]
    suffix_list = config.COMPANY_SUFFIXES_BY_COUNTRY[country]
    mid_list    = config.INDUSTRY_MID_COMPONENTS

    prefix = rng.choice(prefix_list)
    suffix = rng.choice(suffix_list)
    # ~40% of names include an industry mid-component for variety
    if rng.random() < 0.40:
        mid = rng.choice(mid_list)
        return f"{prefix} {mid} {suffix}"
    else:
        return f"{prefix} {suffix}"


# ---------------------------------------------------------------------------
# Helper: generate signup and churn dates
# ---------------------------------------------------------------------------

def make_dates(
    archetype: str,
    n_accounts_per_archetype: dict[str, int],
    archetype_list: list[str],
    rng: np.random.Generator,
) -> tuple[list[pd.Timestamp], list[pd.Timestamp | None]]:
    """
    Generate signup_date and churn_date for every account.
    - Signup dates spread uniformly across the first 12 months.
    - Churn may not happen until MIN_MONTHS_BEFORE_CHURN after signup.
    - Churn dates are within the observation window.
    - Returns parallel lists (same order as archetype_list).
    """
    signup_start = pd.Timestamp(config.SIGNUP_WINDOW_START)
    signup_end   = pd.Timestamp(config.SIGNUP_WINDOW_END)
    obs_end      = pd.Timestamp(config.OBS_END + "-01") + pd.offsets.MonthEnd(0)

    signup_dates = []
    churn_dates  = []

    for arc in archetype_list:
        # Pick a random signup day within the signup window
        days_range  = (signup_end - signup_start).days
        signup_day  = signup_start + pd.Timedelta(days=int(rng.integers(0, days_range + 1)))
        signup_dates.append(signup_day)

        if config.ARCHETYPE_CHURNS[arc]:
            # Earliest possible churn: signup + MIN_MONTHS_BEFORE_CHURN
            earliest_churn = signup_day + pd.DateOffset(months=config.MIN_MONTHS_BEFORE_CHURN)
            if earliest_churn > obs_end:
                # Account signed up too late to churn within window — treat as retained
                churn_dates.append(None)
            else:
                # Churn uniformly between earliest and obs_end
                max_days  = (obs_end - earliest_churn).days
                churn_day = earliest_churn + pd.Timedelta(days=int(rng.integers(0, max(1, max_days + 1))))
                churn_dates.append(churn_day)
        else:
            churn_dates.append(None)

    return signup_dates, churn_dates


# ---------------------------------------------------------------------------
# Helper: compute usage for a single account × single metric
# ---------------------------------------------------------------------------

def generate_metric_series(
    metric: str,
    archetype: str,
    plan_tier: str,
    months: list[pd.Timestamp],   # calendar months this account was active
    signup_date: pd.Timestamp,
    churn_date: pd.Timestamp | None,
    account_rng: np.random.Generator,
) -> list[float]:
    """
    Generate a monthly usage series for one metric and one account.

    The series respects archetype-specific:
    - trend (per-month fractional growth/decline)
    - noise (Gaussian, proportional)
    - annual seasonality (cosine — summer dip)
    - decline/recovery timing (fractions of account lifetime)
    - A4 cliff in the final month only
    - A3 module-specific collapse vs linger
    """
    params   = config.ARCHETYPE_USAGE_PARAMS[archetype]
    base_val = config.PLAN_BASE_USAGE[plan_tier].get(metric, 0)

    # Account-level multiplier: ±30% heterogeneity so accounts of the same archetype differ
    account_multiplier = account_rng.uniform(0.70, 1.30)
    base_val = base_val * account_multiplier

    n_months  = len(months)
    tenure_end = churn_date if churn_date else pd.Timestamp(config.OBS_END + "-01") + pd.offsets.MonthEnd(0)
    total_months = max(1, (tenure_end.year - signup_date.year) * 12 + (tenure_end.month - signup_date.month))

    values = []

    for i, month in enumerate(months):
        # Fractional position through account's total tenure
        frac = i / max(1, total_months - 1) if total_months > 1 else 0.5

        # ---- 1. Base trend ------------------------------------------------
        trend = params["trend_per_month"]

        # A3: module-specific collapse or linger
        if archetype == "A3":
            collapse_mods = params.get("collapse_modules", [])
            linger_mods   = params.get("linger_modules", [])
            if metric in collapse_mods:
                trend = params["trend_per_month"]          # uses the base (negative) trend
            elif metric in linger_mods:
                trend = params.get("logins_trend_per_month", params["trend_per_month"] * 0.35)
            else:
                trend = params["trend_per_month"] * 0.70  # mild decay

        monthly_val = base_val * ((1 + trend) ** i)

        # ---- 2. Seasonality (summer dip — July peak on cosine) ---------------
        month_num  = month.month   # 1–12
        amp        = params["seasonality_amplitude"]
        # cosine with trough in July (month 7) and peak in Jan
        season_factor = 1.0 + amp * np.cos(2 * np.pi * (month_num - 1) / 12.0)
        monthly_val *= season_factor

        # ---- 3. Decline phase (A3, A6 dip, A8) --------------------------------
        decline_frac = params.get("decline_start_frac")
        if decline_frac is not None and frac >= decline_frac:
            # How far into the decline phase are we?
            if archetype == "A6":
                recovery_frac = params.get("recovery_start_frac", 0.55)
                if frac < recovery_frac:
                    # Dip phase
                    dip_depth   = params.get("dip_depth", 0.40)
                    dip_prog    = (frac - decline_frac) / (recovery_frac - decline_frac)
                    decline_mul = 1.0 - dip_prog * dip_depth
                else:
                    # Recovery phase
                    dip_depth        = params.get("dip_depth", 0.40)
                    recovery_strength = params.get("recovery_strength", 0.85)
                    rec_prog = (frac - recovery_frac) / (1.0 - recovery_frac) if recovery_frac < 1.0 else 1.0
                    rec_prog = min(1.0, rec_prog)
                    trough_level = 1.0 - dip_depth
                    decline_mul  = trough_level + rec_prog * (1.0 - trough_level) * recovery_strength
            else:
                # Monotone decline from decline_start_frac onward
                # Rate of additional monthly decline factor on top of trend
                extra_decline_per_step = 0.06 if archetype == "A3" else 0.04
                steps_in_decline = frac - decline_frac
                # Scale steps to months
                steps = steps_in_decline * total_months
                decline_mul = max(params["clamp_min"] / max(base_val, 1),
                                  1.0 - steps * extra_decline_per_step)
                decline_mul = max(0.0, decline_mul)
            monthly_val *= decline_mul

        # ---- 4. A4 cliff: drop ONLY in the final recorded month ---------------
        # Using index-based detection (last item in months list) rather than
        # a fractional threshold, so the cliff fires exactly once.
        if archetype == "A4" and i == n_months - 1:
            monthly_val *= (1.0 - params.get("cliff_drop", 0.45))

        # ---- 5. Gaussian noise ------------------------------------------------
        noise_factor = 1.0 + account_rng.normal(0, params["noise_std"])
        monthly_val  = max(params["clamp_min"], monthly_val * noise_factor)

        # ---- 6. Round to integers (usage counts) -----------------------------
        values.append(max(int(params["clamp_min"]), round(monthly_val)))

    return values


# ---------------------------------------------------------------------------
# Main generation
# ---------------------------------------------------------------------------

def build_accounts_df(
    archetype_list: list[str],
    signup_dates: list[pd.Timestamp],
    churn_dates: list[pd.Timestamp | None],
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    Build the accounts DataFrame from generated archetype/date lists.
    Assigns country, company name, industry, plan tier, ARR, seats.
    """
    countries       = list(config.COUNTRY_WEIGHTS.keys())
    country_weights = list(config.COUNTRY_WEIGHTS.values())

    rows = []
    for idx, (arc, signup, churn) in enumerate(zip(archetype_list, signup_dates, churn_dates)):
        account_id = f"ACC{idx+1:04d}"

        # Country and company name
        country  = rng.choice(countries, p=country_weights)
        industry = rng.choice(config.INDUSTRIES)
        name     = make_company_name(country, industry, rng)
        name     = config.HEADLINE_NAME_OVERRIDES.get(account_id, name)   # headline account keeps its name

        # Plan tier (weighted)
        tiers        = list(config.PLAN_TIER_WEIGHTS.keys())
        tier_weights = list(config.PLAN_TIER_WEIGHTS.values())
        plan_tier    = rng.choice(tiers, p=tier_weights)

        tier_cfg = config.PLAN_TIERS[plan_tier]
        seats    = int(rng.integers(tier_cfg["seats_min"], tier_cfg["seats_max"] + 1))
        arr      = int(rng.integers(tier_cfg["arr_min"], tier_cfg["arr_max"] + 1))

        rows.append({
            "account_id":     account_id,
            "company_name":   name,
            "industry":       industry,
            "country":        country,
            "signup_date":    signup.date(),
            "licensed_seats": seats,
            "plan_tier":      plan_tier,
            "arr_eur":        arr,
            "churn_date":     churn.date() if churn else None,
            "churned":        bool(churn is not None),
            "archetype":      arc,   # kept here for reference; not in final accounts.csv output
        })

    return pd.DataFrame(rows)


def build_usage_df(
    accounts_df: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    Build usage_monthly DataFrame.
    One row per (account, month) for months from signup to end of observation
    window (or churn month, exclusive).
    """
    obs_months = pd.period_range(start=config.OBS_START, end=config.OBS_END, freq="M")
    all_timestamps = [m.to_timestamp() for m in obs_months]

    metrics = [
        "active_users", "dashboard_views", "reports_created",
        "connector_syncs", "alerts_configured", "api_calls",
        "exports_run", "logins",
    ]

    usage_rows = []

    for _, acc in accounts_df.iterrows():
        account_id = acc["account_id"]
        archetype  = acc["archetype"]
        plan_tier  = acc["plan_tier"]
        signup_ts  = pd.Timestamp(acc["signup_date"])
        churn_ts   = pd.Timestamp(acc["churn_date"]) if acc["churn_date"] else None

        # Months this account was active (after signup, before or at churn)
        if churn_ts is not None:
            active_months = [
                t for t in all_timestamps
                if t >= signup_ts.to_period("M").to_timestamp()
                and t < churn_ts.to_period("M").to_timestamp()   # no usage rows after churn
            ]
        else:
            active_months = [
                t for t in all_timestamps
                if t >= signup_ts.to_period("M").to_timestamp()
            ]

        if not active_months:
            continue

        # Per-account deterministic RNG derived from global seed + account index
        acc_seed   = config.RANDOM_SEED + hash(account_id) % (2**31)
        acc_rng    = np.random.default_rng(acc_seed)

        # Generate each metric independently
        metric_series = {}
        for metric in metrics:
            metric_series[metric] = generate_metric_series(
                metric=metric,
                archetype=archetype,
                plan_tier=plan_tier,
                months=active_months,
                signup_date=signup_ts,
                churn_date=churn_ts,
                account_rng=acc_rng,
            )

        for i, month_ts in enumerate(active_months):
            row = {
                "account_id":        account_id,
                "month":             month_ts.strftime("%Y-%m"),
            }
            for metric in metrics:
                row[metric] = metric_series[metric][i]
            usage_rows.append(row)

    return pd.DataFrame(usage_rows)


def build_answer_key(accounts_df: pd.DataFrame) -> pd.DataFrame:
    """
    Build answer_key DataFrame with archetype, planted signals, churn driver.
    The planted_signals column is a semicolon-separated list of signal descriptors.
    """
    rows = []
    for _, acc in accounts_df.iterrows():
        arc    = acc["archetype"]
        signal_types = config.PLANTED_SIGNAL_TYPES.get(arc, [])
        signals_str  = ";".join(signal_types) if signal_types else ""
        churn_driver = config.CHURN_DRIVERS.get(arc, "") if acc["churned"] else ""

        rows.append({
            "account_id":      acc["account_id"],
            "archetype":       arc,
            "planted_signals": signals_str,
            "churn_driver":    churn_driver,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Kataja Analytics — Structured Data Generator")
    print(f"Seed: {config.RANDOM_SEED}  |  Accounts: {config.N_ACCOUNTS}")
    print("=" * 60)

    # -- 1. Assign archetypes -------------------------------------------------
    print("\n[1/4] Assigning archetypes...")
    archetype_list = assign_archetypes(config.N_ACCOUNTS, rng)

    # -- 2. Generate dates ----------------------------------------------------
    print("[2/4] Generating signup and churn dates...")
    n_by_arc = {k: archetype_list.count(k) for k in config.ARCHETYPE_PROPORTIONS}
    signup_dates, churn_dates = make_dates(
        archetype="all",   # not used directly — list-level generation
        n_accounts_per_archetype=n_by_arc,
        archetype_list=archetype_list,
        rng=rng,
    )

    # -- 3. Build accounts DataFrame ------------------------------------------
    print("[3/4] Building accounts table...")
    accounts_df = build_accounts_df(archetype_list, signup_dates, churn_dates, rng)

    # Verify churn rate
    churn_rate = accounts_df["churned"].mean()
    print(f"  Total accounts: {len(accounts_df)}")
    print(f"  Churned:        {accounts_df['churned'].sum()}  ({churn_rate:.1%})")
    print(f"  Retained:       {(~accounts_df['churned']).sum()}")

    # Show archetype x churn breakdown
    cross = accounts_df.groupby("archetype")["churned"].agg(["count", "sum"])
    cross.columns = ["total", "churned"]
    print("\n  Archetype distribution:")
    print(cross.to_string())

    # -- 4. Build usage DataFrame ---------------------------------------------
    print("\n[4/4] Building usage_monthly table (this may take a moment)...")
    usage_df = build_usage_df(accounts_df, rng)
    print(f"  Usage rows generated: {len(usage_df):,}")
    print(f"  Months per account (min/median/max): "
          f"{usage_df.groupby('account_id').size().min()} / "
          f"{usage_df.groupby('account_id').size().median()} / "
          f"{usage_df.groupby('account_id').size().max()}")

    # -- 5. Build answer key --------------------------------------------------
    answer_key_df = build_answer_key(accounts_df)

    # -- 6. Write outputs ------------------------------------------------------
    print("\n[Writing outputs to data/ folder...]")

    # accounts.csv — drop the archetype column (it goes in answer_key only)
    accounts_out = accounts_df.drop(columns=["archetype"])
    out_accounts = DATA_DIR / "accounts.csv"
    accounts_out.to_csv(out_accounts, index=False)
    print(f"  Written: {out_accounts}  ({len(accounts_out)} rows)")

    out_usage = DATA_DIR / "usage_monthly.csv"
    usage_df.to_csv(out_usage, index=False)
    print(f"  Written: {out_usage}  ({len(usage_df):,} rows)")

    out_key = DATA_DIR / "answer_key.csv"
    answer_key_df.to_csv(out_key, index=False)
    print(f"  Written: {out_key}  ({len(answer_key_df)} rows)")

    print("\nDone. Run validate_data.py to verify coherence rules.")


if __name__ == "__main__":
    main()
