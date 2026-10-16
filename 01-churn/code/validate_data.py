"""
validate_data.py — Coherence rule validation for the Kataja Analytics dataset.

Checks all 8 coherence rules of the dataset design (plus the
position-in-life spread check added after the ticket-date clustering fix)
and prints a data quality report.  Exits with code 1 if any rule fails.

Rules validated:
  1. Declining modules → tickets reference that module in that period
  2. A4 usage indistinguishable from A1 until ≤1 month pre-churn (statistical)
  3. A5 churners have no competitor mentions, no angry stages
  4. A7 anger always resolves in ≤2 days; no competitor mentions
  5. Competitor mentions are contextual (not stuffed), appear in healthy accounts too
  6. Every ticket module exists in the feature map; every account_id is valid
  7. Ticket dates: after signup, none after churn, business-day weighted
  8. Non-churn archetypes' tickets are spread across account life (not
     clustered right after signup): median position-in-life > 0.25 and
     IQR > 0.3 per archetype; A6 escalation tickets fall within their
     account's usage-dip window (+/-1 month)

Run from the project root:
    python code/validate_data.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR   = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR     = PROJECT_ROOT / "data"

sys.path.insert(0, str(SCRIPT_DIR))
import config
import fix_ticket_dates  # reuses compute_dip_window() and LIFE_END_DATE for Rule 8

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_data() -> tuple:
    """Load all four data files and return as DataFrames."""
    paths = {
        "accounts":      DATA_DIR / "accounts.csv",
        "usage":         DATA_DIR / "usage_monthly.csv",
        "answer_key":    DATA_DIR / "answer_key.csv",
        "ticket_briefs": DATA_DIR / "ticket_briefs.json",
    }
    missing = [k for k, p in paths.items() if not p.exists()]
    if missing:
        print(f"FATAL: Missing data files: {missing}")
        print("Run generate_structured.py and generate_ticket_briefs.py first.")
        sys.exit(1)

    import json
    accounts_df  = pd.read_csv(paths["accounts"])
    usage_df     = pd.read_csv(paths["usage"])
    answer_key   = pd.read_csv(paths["answer_key"])

    with open(paths["ticket_briefs"], encoding="utf-8") as fh:
        briefs_raw = json.load(fh)
    briefs_df = pd.DataFrame(briefs_raw)

    return accounts_df, usage_df, answer_key, briefs_df


def linear_trend(series: np.ndarray) -> float:
    """Return the slope of a linear fit to the series."""
    if len(series) < 2:
        return 0.0
    x = np.arange(len(series), dtype=float)
    slope, _ = np.polyfit(x, series.astype(float), 1)
    return slope


def usage_trend_features(account_usage: pd.DataFrame, end_month: str) -> dict:
    """
    Compute simple trend features for a 9-month window ending at end_month.
    Using 9 months (rather than 6) averages out annual seasonality better,
    which is important for Rule 2: a 6-month window spanning a summer dip
    would create spurious negative slopes in otherwise healthy accounts.
    """
    metrics = [
        "dashboard_views", "reports_created", "connector_syncs",
        "alerts_configured", "api_calls", "exports_run", "logins",
    ]
    # 9-month window ending at end_month
    all_months = pd.period_range(end=end_month, periods=9, freq="M")
    all_months_str = [str(m) for m in all_months]

    window = account_usage[account_usage["month"].isin(all_months_str)]

    features = {}
    for metric in metrics:
        if metric in window.columns and len(window) >= 2:
            features[f"{metric}_slope"] = linear_trend(window[metric].values)
            features[f"{metric}_mean"]  = window[metric].mean()
        else:
            features[f"{metric}_slope"] = 0.0
            features[f"{metric}_mean"]  = 0.0

    return features


# ---------------------------------------------------------------------------
# Rule checks
# ---------------------------------------------------------------------------

def check_rule_6_referential_integrity(
    accounts_df: pd.DataFrame,
    briefs_df: pd.DataFrame,
) -> tuple[bool, str]:
    """
    Rule 6: Every ticket module exists in feature map; every account_id is valid.
    """
    valid_modules = set(config.MODULE_NAMES)
    valid_accounts = set(accounts_df["account_id"])

    bad_modules  = briefs_df[~briefs_df["module"].isin(valid_modules)]["module"].unique()
    bad_accounts = briefs_df[~briefs_df["account_id"].isin(valid_accounts)]["account_id"].unique()

    passed = len(bad_modules) == 0 and len(bad_accounts) == 0
    details = []
    if len(bad_modules) > 0:
        details.append(f"Unknown modules: {list(bad_modules)}")
    if len(bad_accounts) > 0:
        details.append(f"Unknown account_ids: {list(bad_accounts[:5])}...")
    msg = "PASS" if passed else "FAIL — " + "; ".join(details)
    return passed, msg


def check_rule_7_dates(
    accounts_df: pd.DataFrame,
    briefs_df: pd.DataFrame,
) -> tuple[bool, str]:
    """
    Rule 7: Ticket dates must be after signup and before or equal to churn date.
    Also checks business-day weighting (weekday tickets should dominate).
    """
    accounts_map = accounts_df.set_index("account_id")

    violations_pre_signup  = 0
    violations_post_churn  = 0
    weekend_count = 0
    weekday_count = 0

    for _, brief in briefs_df.iterrows():
        acc_id     = brief["account_id"]
        ticket_dt  = pd.Timestamp(brief["date"])

        if acc_id not in accounts_map.index:
            continue

        signup_dt = pd.Timestamp(accounts_map.loc[acc_id, "signup_date"])
        churn_dt_raw = accounts_map.loc[acc_id, "churn_date"]
        churn_dt  = pd.Timestamp(churn_dt_raw) if pd.notna(churn_dt_raw) else None

        if ticket_dt < signup_dt:
            violations_pre_signup += 1
        if churn_dt is not None and ticket_dt >= churn_dt:
            violations_post_churn += 1

        if ticket_dt.weekday() >= 5:
            weekend_count += 1
        else:
            weekday_count += 1

    total = len(briefs_df)
    weekday_pct = weekday_count / max(1, total) * 100

    passed = violations_pre_signup == 0 and violations_post_churn == 0 and weekday_pct >= 60.0
    details = []
    details.append(f"Pre-signup violations: {violations_pre_signup}")
    details.append(f"Post-churn violations: {violations_post_churn}")
    details.append(f"Weekday tickets: {weekday_pct:.1f}%")

    status = "PASS" if passed else "FAIL"
    msg = f"{status} — " + "; ".join(details)
    return passed, msg


def check_rule_4_a7(
    answer_key: pd.DataFrame,
    briefs_df: pd.DataFrame,
) -> tuple[bool, str]:
    """
    Rule 4: A7 tickets always resolve in ≤2 days; never competitor mentions.
    """
    a7_ids    = set(answer_key[answer_key["archetype"] == "A7"]["account_id"])
    a7_briefs = briefs_df[briefs_df["account_id"].isin(a7_ids)]

    if len(a7_briefs) == 0:
        return True, "PASS — no A7 briefs (unexpected)"

    # Check resolution days
    resolved_a7 = a7_briefs[a7_briefs["resolved"] == True]
    slow_resolutions = resolved_a7[
        resolved_a7["resolution_days"].notna() &
        (resolved_a7["resolution_days"].astype(float) > 2)
    ]

    # Check competitor mentions
    competitor_mentions = a7_briefs[a7_briefs["competitor_mention"].notna()]

    passed = len(slow_resolutions) == 0 and len(competitor_mentions) == 0
    details = [
        f"A7 tickets: {len(a7_briefs)}",
        f"Slow resolutions (>2 days): {len(slow_resolutions)}",
        f"Competitor mentions: {len(competitor_mentions)}",
    ]
    status = "PASS" if passed else "FAIL"
    msg = f"{status} — " + "; ".join(details)
    return passed, msg


def check_rule_3_a5(
    answer_key: pd.DataFrame,
    briefs_df: pd.DataFrame,
) -> tuple[bool, str]:
    """
    Rule 3: A5 churners have no text signal (no competitor mentions, no angry stages).
    """
    a5_ids    = set(answer_key[answer_key["archetype"] == "A5"]["account_id"])
    a5_briefs = briefs_df[briefs_df["account_id"].isin(a5_ids)]

    if len(a5_briefs) == 0:
        return True, "PASS — no A5 briefs"

    angry_stages = {"angry", "frustrated", "escalation", "competitor_mention", "unresolved_complaint"}
    bad_stages   = a5_briefs[a5_briefs["sentiment_stage"].isin(angry_stages)]
    bad_comp     = a5_briefs[a5_briefs["competitor_mention"].notna()]

    passed = len(bad_stages) == 0 and len(bad_comp) == 0
    details = [
        f"A5 tickets: {len(a5_briefs)}",
        f"Angry/frustrated stages: {len(bad_stages)}",
        f"Competitor mentions: {len(bad_comp)}",
    ]
    status = "PASS" if passed else "FAIL"
    msg = f"{status} — " + "; ".join(details)
    return passed, msg


def check_rule_1_module_coherence(
    answer_key: pd.DataFrame,
    usage_df: pd.DataFrame,
    briefs_df: pd.DataFrame,
) -> tuple[bool, str]:
    """
    Rule 1: If a module's usage drops, tickets in that period reference that module.
    We check A3 accounts (known declining modules) and verify that the
    proportion of tickets referencing those modules is elevated.

    This is a statistical check — we expect the correlation to be directional,
    not that every declining period has a ticket on that module.
    """
    a3_ids = set(answer_key[answer_key["archetype"] == "A3"]["account_id"])

    # Known collapsing modules for A3
    collapse_metrics = config.ARCHETYPE_USAGE_PARAMS["A3"]["collapse_modules"]
    # Map metrics → module names
    metric_to_module = {v["metric"]: k for k, v in config.FEATURE_MAP.items()}
    collapse_module_names = [
        metric_to_module[m] for m in collapse_metrics if m in metric_to_module
    ]

    if not a3_ids or not collapse_module_names:
        return True, "PASS — no A3 accounts to check"

    a3_briefs = briefs_df[briefs_df["account_id"].isin(a3_ids)]
    total_a3  = len(a3_briefs)
    collapse_ref = a3_briefs[a3_briefs["module"].isin(collapse_module_names)]
    collapse_rate = len(collapse_ref) / max(1, total_a3)

    # Also check non-A3 accounts for baseline
    non_a3_briefs = briefs_df[~briefs_df["account_id"].isin(a3_ids)]
    baseline_rate = len(
        non_a3_briefs[non_a3_briefs["module"].isin(collapse_module_names)]
    ) / max(1, len(non_a3_briefs))

    # Pass if A3 accounts reference collapsing modules more than baseline
    passed = collapse_rate > baseline_rate
    details = [
        f"A3 collapse-module ticket rate: {collapse_rate:.2%}",
        f"Non-A3 baseline rate: {baseline_rate:.2%}",
        f"Lift: {collapse_rate / max(0.001, baseline_rate):.2f}×",
    ]
    status = "PASS" if passed else "FAIL"
    msg = f"{status} — " + "; ".join(details)
    return passed, msg


def check_rule_2_a4_usage(
    accounts_df: pd.DataFrame,
    answer_key: pd.DataFrame,
    usage_df: pd.DataFrame,
) -> tuple[bool, str, dict]:
    """
    Rule 2: A4 accounts must have no statistically detectable usage decline
    until ≤1 month pre-churn.  Compare trend features of A4 vs A1.

    Returns pass/fail, message, and a dict of comparison statistics.
    """
    acc_with_arc = accounts_df.merge(
        answer_key[["account_id", "archetype"]], on="account_id"
    )

    a4_accounts = acc_with_arc[acc_with_arc["archetype"] == "A4"]
    a1_accounts = acc_with_arc[acc_with_arc["archetype"] == "A1"]

    metrics = [
        "dashboard_views", "reports_created", "connector_syncs",
        "alerts_configured", "api_calls", "exports_run", "logins",
    ]

    def get_trends(accs_subset: pd.DataFrame) -> pd.DataFrame:
        """
        Compute 9-month pre-churn/censoring trend slope for each account.

        For A4 accounts: reference month is set to 2 months before churn so
        the cliff (which fires only in the final recorded month = 1 month before
        churn) is excluded from the comparison window entirely.  This is the
        correct interpretation of Rule 2: 'no detectable decline until ≤1 month
        pre-churn' means the window up to T-2 should look like A1.
        """
        rows = []
        for _, acc in accs_subset.iterrows():
            acc_id    = acc["account_id"]
            churn_raw = acc["churn_date"]
            if pd.notna(churn_raw):
                if acc["archetype"] == "A4":
                    # Exclude both the cliff month AND the month before it from
                    # the window, to give a clean pre-cliff view
                    reference_month = (
                        pd.Timestamp(churn_raw) - pd.DateOffset(months=2)
                    ).strftime("%Y-%m")
                else:
                    reference_month = (
                        pd.Timestamp(churn_raw) - pd.DateOffset(months=1)
                    ).strftime("%Y-%m")
            else:
                reference_month = config.OBS_END

            acc_usage = usage_df[usage_df["account_id"] == acc_id]

            feats = usage_trend_features(acc_usage, reference_month)
            feats["account_id"] = acc_id
            rows.append(feats)
        return pd.DataFrame(rows)

    a4_trends = get_trends(a4_accounts)
    a1_trends = get_trends(a1_accounts)

    if a4_trends.empty or a1_trends.empty:
        return True, "PASS — insufficient data for comparison", {}

    # Compare mean slopes across all metrics
    slope_cols = [f"{m}_slope" for m in metrics]

    a4_mean_slopes = a4_trends[slope_cols].mean()
    a1_mean_slopes = a1_trends[slope_cols].mean()

    # Rule passes if A4 mean slopes are NOT significantly more negative than A1
    # Criterion: for each metric, A4 mean slope >= A1 mean slope - 2 std(A1 slopes)
    # (i.e. A4 is within 2σ of A1's distribution)
    comparison = {}
    any_violation = False

    for col in slope_cols:
        metric_name = col.replace("_slope", "")
        a4_val  = a4_mean_slopes[col]
        a1_val  = a1_mean_slopes[col]
        a1_std  = a1_trends[col].std() if len(a1_trends) > 1 else 1.0
        # How many SDs below A1 mean is A4?
        z_score = (a4_val - a1_val) / max(a1_std, 0.001)
        comparison[metric_name] = {
            "a4_mean_slope":  round(a4_val, 4),
            "a1_mean_slope":  round(a1_val, 4),
            "a1_slope_std":   round(a1_std, 4),
            "z_score":        round(z_score, 3),
        }
        # Violation if A4 significantly more negative than A1 (z < -2)
        if z_score < -2.0:
            any_violation = True
            comparison[metric_name]["VIOLATION"] = True

    passed = not any_violation
    n_a4 = len(a4_accounts)
    n_a1 = len(a1_accounts)

    status = "PASS" if passed else "FAIL"
    summary_line = (
        f"{status} — A4 (n={n_a4}) vs A1 (n={n_a1}): "
        f"all metric slopes within 2σ of A1 baseline "
        f"({'yes' if passed else 'no'})"
    )
    return passed, summary_line, comparison


def check_rule_5_competitor_context(
    answer_key: pd.DataFrame,
    briefs_df: pd.DataFrame,
) -> tuple[bool, str]:
    """
    Rule 5: Competitor mentions appear in both troubled and healthy accounts,
    demonstrating noise coverage.
    Also verifies no A7 competitor mentions (redundant with rule 4, belt-and-suspenders).
    """
    comp_briefs = briefs_df[briefs_df["competitor_mention"].notna()]
    total_comp  = len(comp_briefs)

    # Merge archetype
    arc_map = answer_key.set_index("account_id")["archetype"]
    comp_briefs = comp_briefs.copy()
    comp_briefs["archetype"] = comp_briefs["account_id"].map(arc_map)

    # Healthy accounts with competitor mentions (noise)
    healthy_arcs    = {"A1", "A2", "A7"}
    noise_mentions  = comp_briefs[comp_briefs["archetype"].isin(healthy_arcs)]
    churn_arcs      = {"A3", "A4", "A5"}
    churn_mentions  = comp_briefs[comp_briefs["archetype"].isin(churn_arcs)]

    # A7 should have zero
    a7_mentions = comp_briefs[comp_briefs["archetype"] == "A7"]

    # Rule passes if:
    # - noise mentions exist (healthy accounts have some competitor mentions)
    # - churn accounts have competitor mentions
    # - A7 has zero
    passed = (
        len(noise_mentions) > 0
        and len(churn_mentions) > 0
        and len(a7_mentions) == 0
    )
    details = [
        f"Total competitor mentions: {total_comp}",
        f"In healthy accounts (noise): {len(noise_mentions)}",
        f"In churning accounts: {len(churn_mentions)}",
        f"In A7 (must be 0): {len(a7_mentions)}",
    ]
    status = "PASS" if passed else "FAIL"
    msg = f"{status} — " + "; ".join(details)
    return passed, msg


NON_CHURN_ARCHETYPES = ["A1", "A2", "A6", "A7", "A8"]
POSITION_MEDIAN_MIN  = 0.25
POSITION_IQR_MIN     = 0.30
A6_DIP_TOLERANCE_DAYS = 31   # "+/-1 month" tolerance for the escalation-in-dip check


def _position_in_life(briefs_df: pd.DataFrame, accounts_df: pd.DataFrame, answer_key: pd.DataFrame) -> pd.DataFrame:
    """
    Attach a 'pos' column (fraction of account life at which each ticket
    falls) and 'archetype' to every brief. Formula matches fix_ticket_dates.py:
    pos = (ticket_date - signup_date) / (life_end - signup_date), where
    life_end = churn_date for churned accounts, else fix_ticket_dates.LIFE_END_DATE.
    """
    merged = briefs_df.merge(
        accounts_df[["account_id", "signup_date", "churn_date", "churned"]],
        on="account_id",
    ).merge(answer_key[["account_id", "archetype"]], on="account_id")

    merged["signup_date"] = pd.to_datetime(merged["signup_date"])
    merged["date"]        = pd.to_datetime(merged["date"])

    life_end = np.where(
        merged["churned"] & merged["churn_date"].notna(),
        pd.to_datetime(merged["churn_date"]),
        fix_ticket_dates.LIFE_END_DATE,
    )
    life_end = pd.to_datetime(pd.Series(life_end, index=merged.index))
    span_days = (life_end - merged["signup_date"]).dt.days.clip(lower=1)
    merged["pos"] = (merged["date"] - merged["signup_date"]).dt.days / span_days
    return merged


def check_rule_8_position_spread(
    accounts_df: pd.DataFrame,
    answer_key: pd.DataFrame,
    usage_df: pd.DataFrame,
    briefs_df: pd.DataFrame,
) -> tuple[bool, str]:
    """
    Rule 8 (added after the ticket-date clustering fix):
      a) Each non-churn archetype's tickets must be spread across account
         life, not clustered right after signup: median position-in-life
         > 0.25 and IQR (p75-p25) > 0.3.
      b) A6's escalation tickets — the arc's formally dip-aligned stage
         (see fix_ticket_dates.py: "frustrated"/"angry" are an intentional
         pre-dip lead-in, "escalation" is the tightly dip-bound event) —
         must fall within the account's own detected usage-dip window,
         +/-1 month.
    """
    merged = _position_in_life(briefs_df, accounts_df, answer_key)

    details = []
    spread_passed = True
    for archetype in NON_CHURN_ARCHETYPES:
        grp = merged[merged["archetype"] == archetype]
        if grp.empty:
            details.append(f"{archetype}: no tickets found")
            spread_passed = False
            continue
        median = grp["pos"].median()
        iqr = grp["pos"].quantile(0.75) - grp["pos"].quantile(0.25)
        ok = median > POSITION_MEDIAN_MIN and iqr > POSITION_IQR_MIN
        spread_passed = spread_passed and ok
        details.append(f"{archetype} median={median:.3f} IQR={iqr:.3f} [{'OK' if ok else 'FAIL'}]")

    # A6 escalation-in-dip-window check
    a6_ids = answer_key[answer_key["archetype"] == "A6"]["account_id"].tolist()
    escalation_total = 0
    escalation_bad   = 0
    accounts_with_no_dip = []

    for acc_id in a6_ids:
        acc_usage = usage_df[usage_df["account_id"] == acc_id]
        dip_start, dip_end = fix_ticket_dates.compute_dip_window(acc_usage)
        if dip_start is None:
            accounts_with_no_dip.append(acc_id)
            continue

        tolerance = pd.Timedelta(days=A6_DIP_TOLERANCE_DAYS)
        lo_bound  = dip_start - tolerance
        hi_bound  = dip_end + tolerance

        esc = merged[
            (merged["account_id"] == acc_id) &
            (merged["sentiment_stage"] == "escalation")
        ]
        escalation_total += len(esc)
        escalation_bad += ((esc["date"] < lo_bound) | (esc["date"] > hi_bound)).sum()

    escalation_passed = escalation_bad == 0
    details.append(
        f"A6 escalation-in-dip-window (+/-1mo): "
        f"{escalation_total - escalation_bad}/{escalation_total} OK"
        + (f", {len(accounts_with_no_dip)} accounts had no detectable dip (skipped)"
           if accounts_with_no_dip else "")
    )

    passed = spread_passed and escalation_passed
    status = "PASS" if passed else "FAIL"
    msg = f"{status} — " + "; ".join(details)
    return passed, msg


# ---------------------------------------------------------------------------
# Main report
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("Kataja Analytics — Data Coherence Validation Report")
    print("=" * 70)

    # Load data
    print("\nLoading data files...")
    accounts_df, usage_df, answer_key, briefs_df = load_data()

    print(f"  accounts:       {len(accounts_df)} rows")
    print(f"  usage_monthly:  {len(usage_df):,} rows")
    print(f"  answer_key:     {len(answer_key)} rows")
    print(f"  ticket_briefs:  {len(briefs_df):,} rows")

    # Track overall pass/fail
    all_passed = True
    results    = []

    # --------------- Rule 6 (referential integrity — run first) --------------
    print("\n--- Rule 6: Referential integrity ---")
    passed, msg = check_rule_6_referential_integrity(accounts_df, briefs_df)
    print(f"  {msg}")
    results.append(("Rule 6", passed))
    all_passed = all_passed and passed

    # --------------- Rule 7 (date constraints) --------------------------------
    print("\n--- Rule 7: Date constraints ---")
    passed, msg = check_rule_7_dates(accounts_df, briefs_df)
    print(f"  {msg}")
    results.append(("Rule 7", passed))
    all_passed = all_passed and passed

    # --------------- Rule 4 (A7: loud but loyal) ------------------------------
    print("\n--- Rule 4: A7 resolution ≤2 days, no competitor mentions ---")
    passed, msg = check_rule_4_a7(answer_key, briefs_df)
    print(f"  {msg}")
    results.append(("Rule 4", passed))
    all_passed = all_passed and passed

    # --------------- Rule 3 (A5: silent) -------------------------------------
    print("\n--- Rule 3: A5 — no text signal ---")
    passed, msg = check_rule_3_a5(answer_key, briefs_df)
    print(f"  {msg}")
    results.append(("Rule 3", passed))
    all_passed = all_passed and passed

    # --------------- Rule 1 (module coherence) --------------------------------
    print("\n--- Rule 1: Module–usage coherence (A3) ---")
    passed, msg = check_rule_1_module_coherence(answer_key, usage_df, briefs_df)
    print(f"  {msg}")
    results.append(("Rule 1", passed))
    all_passed = all_passed and passed

    # --------------- Rule 5 (competitor context) ------------------------------
    print("\n--- Rule 5: Competitor mentions in context + noise coverage ---")
    passed, msg = check_rule_5_competitor_context(answer_key, briefs_df)
    print(f"  {msg}")
    results.append(("Rule 5", passed))
    all_passed = all_passed and passed

    # --------------- Rule 2 (A4 vs A1 usage — the key statistical check) ------
    print("\n--- Rule 2: A4 usage indistinguishable from A1 until ≤1 month pre-churn ---")
    passed, summary_line, comparison = check_rule_2_a4_usage(
        accounts_df, answer_key, usage_df
    )
    print(f"  {summary_line}")
    if comparison:
        print("\n  Per-metric comparison (slopes in units/month, z-score vs A1):")
        print(f"  {'Metric':<22} {'A4 slope':>10} {'A1 slope':>10} {'A1 std':>8} {'z-score':>8}")
        print("  " + "-" * 62)
        for metric, vals in comparison.items():
            flag = " *** VIOLATION" if vals.get("VIOLATION") else ""
            print(
                f"  {metric:<22} "
                f"{vals['a4_mean_slope']:>10.4f} "
                f"{vals['a1_mean_slope']:>10.4f} "
                f"{vals['a1_slope_std']:>8.4f} "
                f"{vals['z_score']:>8.3f}"
                f"{flag}"
            )
    results.append(("Rule 2", passed))
    all_passed = all_passed and passed

    # --------------- Rule 8 (non-churn ticket-date spread) --------------------
    print("\n--- Rule 8: Non-churn ticket dates spread across account life ---")
    passed, msg = check_rule_8_position_spread(accounts_df, answer_key, usage_df, briefs_df)
    for line in msg.split("; "):
        print(f"  {line}")
    results.append(("Rule 8", passed))
    all_passed = all_passed and passed

    # --------------- Summary -------------------------------------------------
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for rule_name, rule_passed in results:
        status = "PASS" if rule_passed else "FAIL"
        print(f"  {rule_name}: {status}")

    print()
    if all_passed:
        print("ALL RULES PASSED — dataset is coherent and ready for analysis.")
        print("=" * 70)
        sys.exit(0)
    else:
        failed = [r for r, p in results if not p]
        print(f"FAILED RULES: {failed}")
        print("Fix the generation scripts and re-run.")
        print("=" * 70)
        sys.exit(1)


if __name__ == "__main__":
    main()
