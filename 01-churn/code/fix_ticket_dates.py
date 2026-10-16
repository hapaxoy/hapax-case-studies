"""
fix_ticket_dates.py — Fixes the ticket-date clustering defect for non-churn accounts.

THE DEFECT (found in generate_ticket_briefs.py, build_account_briefs()):

    churn_ts = pd.Timestamp(account["churn_date"]) if account["churn_date"] else None

For non-churned accounts, ``account["churn_date"]`` is NaN (a float, read from
accounts.csv by pandas). ``if account["churn_date"]`` treats NaN as truthy
(it is a non-zero float), so the branch is taken and ``churn_ts`` becomes
``pd.Timestamp(nan)`` = NaT — instead of the intended ``None``. Downstream,
``end_ts = churn_ts`` (NaT, not None), and the guard
``if pd.isna(end_ts) or end_ts <= signup_ts: end_ts = signup_ts + 30 days``
then collapses every non-churn account's ticket window to a 30-day burst
right after signup. Churned accounts (where churn_date is a real string) are
unaffected — that branch's truthiness works as intended there.

THIS SCRIPT re-dates tickets for the five non-churning archetypes only
(A1, A2, A6, A7, A8). Churned archetypes (A3, A4, A5) are untouched. Only the
``date`` field is changed — ticket count, order, sentiment stages, modules,
personas and signals are preserved exactly as generated.

Per-archetype date strategy:
  A1, A8 — scatter across the account's life with a mild onboarding skew
           (Beta distribution weighted early, long tail).
  A2     — near-uniform scatter across life ("feature requests spread across
           the growth period").
  A7     — recurring anger bursts every 2-4 months, each burst 1-5 tickets
           over a few days, across the whole life.
  A6     — arc aligned to the account's own usage dip (detected from
           usage_monthly.csv: months where total usage across metrics falls
           below ~80% of the account's own median). "frustrated"/"angry"
           land in the pre-dip lead-in (sentiment sours before the usage
           decline becomes visible), "escalation" is tied to the dip window
           itself (+/-1 month, matching validate_data.py Rule 8), resolution
           lands near the end of the dip, and calm/positive tickets land
           after recovery. Accounts with no detectable dip get the arc
           placed mid-life and are flagged in the printed report.

Run from the project root:
    python code/fix_ticket_dates.py
"""

import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Resolve paths — output must never overwrite input except the target file
# itself, which we explicitly back up first.
# ---------------------------------------------------------------------------

SCRIPT_DIR   = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR     = PROJECT_ROOT / "data"

BRIEFS_PATH  = DATA_DIR / "ticket_briefs.json"
BACKUP_PATH  = DATA_DIR / "ticket_briefs_v1_clustered.json"

sys.path.insert(0, str(SCRIPT_DIR))
import config  # noqa: E402
from generate_ticket_briefs import sample_business_day  # reuse the existing helper

# ---------------------------------------------------------------------------
# Config block — every tunable parameter for the fix lives here
# ---------------------------------------------------------------------------

FIX_SEED = 42

# Non-churning archetypes affected by the defect (touched by this script)
NON_CHURN_ARCHETYPES = ["A1", "A2", "A6", "A7", "A8"]
CHURN_ARCHETYPES      = ["A3", "A4", "A5"]

# Allowed re-dating window
LO_BUFFER_DAYS   = 14                             # earliest = signup + 14 days
HI_DATE          = pd.Timestamp("2025-12-15")     # latest re-dated ticket
LIFE_END_DATE    = pd.Timestamp("2025-12-31")     # denominator for position-in-life
                                                    # (matches config.OBS_END month-end,
                                                    # used consistently for before/after
                                                    # reporting and validate_data.py Rule 8)

# A7 — loud-but-loyal recurring anger bursts
A7_BURST_SIZE_MIN   = 1
A7_BURST_SIZE_MAX   = 5      # inclusive
A7_BURST_SPAN_DAYS  = 4      # a burst's tickets land within this many days of the burst start
A7_GAP_MONTHS_MIN   = 2
A7_GAP_MONTHS_MAX   = 4      # inclusive — gap between burst starts

# A6 — saved-account dip alignment
A6_DIP_RATIO            = 0.80   # dip = months below this fraction of the account's own median
A6_ANGER_MARGIN_DAYS    = 30     # frustrated/angry/escalation may land up to this many days
                                  # outside the detected dip window (matches the +/-1 month
                                  # tolerance validate_data.py Rule 8 checks against)
A6_RESOLUTION_LEAD_DAYS = 3      # resolution window starts this many days before dip end
A6_RESOLUTION_TAIL_DAYS = 7      # ... and extends this many days after dip end
A6_RECOVERY_GAP_DAYS    = 0      # calm/positive tickets start this many days after dip end
                                  # (right after the resolution window closes) so the
                                  # post-recovery window is as wide as possible
A6_FALLBACK_HALFSPAN_DAYS = 30   # if no dip detected, arc window = mid-life +/- this many days

# A1 / A8 — mild onboarding skew (Beta distribution over the [lo, hi] fraction)
SCATTER_BETA_PARAMS = {
    "A1": (1.3, 2.2),   # skewed early, long tail — "how-tos early, occasional later"
    "A8": (1.3, 2.2),   # same shape — sparse, mildly onboarding-skewed
    "A2": (1.0, 1.0),   # uniform — "feature requests spread across the growth period"
}
SCATTER_BUSINESS_DAY_JITTER = 3   # +/- days around the sampled fraction, business-day weighted

USAGE_METRICS = [
    "active_users", "dashboard_views", "reports_created", "connector_syncs",
    "alerts_configured", "api_calls", "exports_run", "logins",
]

# ---------------------------------------------------------------------------
# Deterministic per-account RNG (built-in hash() is randomised per process —
# not safe for reproducibility, so we derive seeds from a stable md5 digest)
# ---------------------------------------------------------------------------

def account_rng_for(account_id: str) -> np.random.Generator:
    digest = hashlib.md5(f"fix_ticket_dates::{account_id}".encode("utf-8")).hexdigest()
    seed = (FIX_SEED + int(digest[:8], 16)) % (2**32)
    return np.random.default_rng(seed)


# ---------------------------------------------------------------------------
# Position-in-life formula (also mirrored in validate_data.py Rule 8):
#   pos = (ticket_date - signup_date) / (life_end - signup_date)
#   life_end = churn_date for churned accounts, else LIFE_END_DATE (2025-12-31)
# Applied vectorised, per row, inside summarise_positions() below.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Archetype-specific date generators
# ---------------------------------------------------------------------------

def dates_for_a7(n_tickets: int, lo: pd.Timestamp, hi: pd.Timestamp, rng: np.random.Generator) -> list:
    """Recurring anger bursts every 2-4 months, 1-5 tickets per burst, across the whole life."""
    # Draw burst sizes until they cover n_tickets
    burst_sizes = []
    total = 0
    while total < n_tickets:
        size = int(rng.integers(A7_BURST_SIZE_MIN, A7_BURST_SIZE_MAX + 1))
        size = min(size, n_tickets - total)
        burst_sizes.append(size)
        total += size

    n_bursts = len(burst_sizes)

    # Draw raw gaps (in days) between burst starts, then scale to fit the life window
    raw_gaps_months = rng.integers(A7_GAP_MONTHS_MIN, A7_GAP_MONTHS_MAX + 1, size=max(n_bursts - 1, 0))
    raw_gap_days = raw_gaps_months.astype(float) * 30.4375  # average month length
    available_days = max((hi - lo).days, 1)
    if raw_gap_days.sum() > available_days and raw_gap_days.sum() > 0:
        raw_gap_days = raw_gap_days * (available_days / raw_gap_days.sum())

    burst_starts = [lo]
    for gap in raw_gap_days:
        burst_starts.append(min(hi, burst_starts[-1] + pd.Timedelta(days=float(gap))))

    dates = []
    for start, size in zip(burst_starts, burst_sizes):
        burst_end = min(hi, start + pd.Timedelta(days=A7_BURST_SPAN_DAYS))
        burst_dates = sorted(sample_business_day(start, burst_end, rng) for _ in range(size))
        dates.extend(burst_dates)

    dates = sorted(dates)[:n_tickets]
    while len(dates) < n_tickets:
        dates.append(hi)
    return dates


def compute_dip_window(acc_usage: pd.DataFrame) -> tuple:
    """
    Detect the usage-dip window for one account: months where total usage
    across all metrics falls below A6_DIP_RATIO of the account's own median
    total usage. Returns (dip_start, dip_end) timestamps, or (None, None)
    if no dip is detected.
    """
    acc_usage = acc_usage.sort_values("month")
    present_metrics = [m for m in USAGE_METRICS if m in acc_usage.columns]
    total_usage = acc_usage[present_metrics].sum(axis=1)
    if total_usage.empty:
        return None, None

    median_total = total_usage.median()
    threshold = A6_DIP_RATIO * median_total
    dip_mask = total_usage < threshold
    dip_months = acc_usage.loc[dip_mask, "month"].tolist()

    if not dip_months:
        return None, None

    dip_start = pd.Period(min(dip_months), freq="M").start_time
    dip_end   = pd.Period(max(dip_months), freq="M").end_time
    return dip_start, dip_end


def dates_for_a6(
    stages: list,
    lo: pd.Timestamp,
    hi: pd.Timestamp,
    rng: np.random.Generator,
    dip_start,
    dip_end,
) -> tuple:
    """
    Align the anger -> escalation -> resolution -> calm arc to the account's
    usage dip. Returns (dates, no_dip_detected_flag).
    """
    no_dip_detected = dip_start is None

    if no_dip_detected:
        mid = lo + (hi - lo) / 2
        dip_start = max(lo, mid - pd.Timedelta(days=A6_FALLBACK_HALFSPAN_DAYS))
        dip_end   = min(hi, mid + pd.Timedelta(days=A6_FALLBACK_HALFSPAN_DAYS))
    else:
        dip_start = max(lo, pd.Timestamp(dip_start))
        dip_end   = min(hi, pd.Timestamp(dip_end))
        if dip_end <= dip_start:
            dip_end = min(hi, dip_start + pd.Timedelta(days=14))

    # "frustrated"/"angry" are the arc's early warning signs — sentiment sours
    # in the pre-dip period, before the usage decline becomes visible in the
    # metrics (a realistic lead: people get frustrated before they visibly
    # disengage). "escalation" is the arc's formal anger event — Rule 8
    # checks it against the detected dip window with a +/-1 month tolerance,
    # so it gets the tighter, tolerance-matched window.
    lead_window = (lo, dip_start if dip_start > lo else min(hi, lo + pd.Timedelta(days=7)))
    anger_window = (
        max(lo, dip_start - pd.Timedelta(days=A6_ANGER_MARGIN_DAYS)),
        min(hi, dip_end + pd.Timedelta(days=A6_ANGER_MARGIN_DAYS)),
    )
    res_window  = (
        max(lo, dip_end - pd.Timedelta(days=A6_RESOLUTION_LEAD_DAYS)),
        min(hi, dip_end + pd.Timedelta(days=A6_RESOLUTION_TAIL_DAYS)),
    )
    recovery_start = min(hi, dip_end + pd.Timedelta(days=A6_RECOVERY_GAP_DAYS))
    post_window = (recovery_start, hi) if recovery_start < hi else (hi, hi)

    # Sample each ticket's date independently within its stage's window (no
    # running floor) so tickets fill the whole window instead of ratcheting
    # toward its upper edge. The windows are constructed in chronological
    # order (pre < dip < resolution < post) so a single final sort restores
    # strict chronological order without distorting the spread.
    raw_dates = []
    for stage in stages:
        if stage in ("frustrated", "angry"):
            w0, w1 = lead_window
        elif stage == "escalation":
            w0, w1 = anger_window
        elif stage == "resolution":
            w0, w1 = res_window
        elif stage in ("positive", "calm"):
            w0, w1 = post_window
        else:
            w0, w1 = lead_window  # unexpected stage label — fall back to the pre-dip window

        d = sample_business_day(w0, w1, rng)
        raw_dates.append(d)

    dates = sorted(raw_dates)
    return dates, no_dip_detected


def dates_for_scatter(
    n_tickets: int,
    lo: pd.Timestamp,
    hi: pd.Timestamp,
    rng: np.random.Generator,
    beta_a: float,
    beta_b: float,
) -> list:
    """Scatter n_tickets across [lo, hi] with a Beta-shaped skew, business-day nudged."""
    span_days = max((hi - lo).days, 1)
    fracs = rng.beta(beta_a, beta_b, size=n_tickets)  # order doesn't matter — sorted below

    # Sample each ticket independently around its own fractional position (no
    # running floor), then sort once at the end — avoids ratcheting later
    # draws toward the upper edge of the window.
    raw_dates = []
    for frac in fracs:
        raw = lo + pd.Timedelta(days=int(frac * span_days))
        w0 = max(lo, raw - pd.Timedelta(days=SCATTER_BUSINESS_DAY_JITTER))
        w1 = min(hi, raw + pd.Timedelta(days=SCATTER_BUSINESS_DAY_JITTER))
        d = sample_business_day(w0, w1, rng)
        raw_dates.append(d)

    return sorted(raw_dates)


# ---------------------------------------------------------------------------
# Reporting helper
# ---------------------------------------------------------------------------

def summarise_positions(label: str, briefs_df: pd.DataFrame, accounts_df: pd.DataFrame, answer_key: pd.DataFrame) -> pd.DataFrame:
    merged = briefs_df.merge(
        accounts_df[["account_id", "signup_date", "churn_date", "churned"]],
        on="account_id",
    ).merge(answer_key[["account_id", "archetype"]], on="account_id")

    merged["signup_date"] = pd.to_datetime(merged["signup_date"])
    merged["date"]        = pd.to_datetime(merged["date"])

    # Per-row position (life_end differs per row depending on churn status)
    life_end = np.where(
        merged["churned"] & merged["churn_date"].notna(),
        pd.to_datetime(merged["churn_date"]),
        LIFE_END_DATE,
    )
    life_end = pd.to_datetime(pd.Series(life_end, index=merged.index))
    span_days = (life_end - merged["signup_date"]).dt.days.clip(lower=1)
    merged["pos"] = (merged["date"] - merged["signup_date"]).dt.days / span_days

    rows = []
    for archetype, grp in merged.groupby("archetype"):
        rows.append({
            "archetype": archetype,
            "n_tickets": len(grp),
            "median_pos": grp["pos"].median(),
            "p25": grp["pos"].quantile(0.25),
            "p75": grp["pos"].quantile(0.75),
        })
    result = pd.DataFrame(rows).set_index("archetype").sort_index()
    result["iqr"] = result["p75"] - result["p25"]
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("fix_ticket_dates.py — repairing non-churn ticket date clustering")
    print("=" * 70)

    assert BRIEFS_PATH.resolve() != BACKUP_PATH.resolve()  # output != a different input path

    # -- Step 1: back up the clustered file (idempotent — never overwrite a
    #    real backup with an already-partially-fixed file) --------------------
    print("\n[1/6] Backing up data/ticket_briefs.json ...")
    if BACKUP_PATH.exists():
        print(f"  Backup already exists at {BACKUP_PATH.name} — using it as the source of truth "
              "(re-run is idempotent).")
        with open(BACKUP_PATH, encoding="utf-8") as fh:
            source_briefs = json.load(fh)
    else:
        if not BRIEFS_PATH.exists():
            print(f"  ERROR: {BRIEFS_PATH} not found.")
            sys.exit(1)
        shutil.copy2(BRIEFS_PATH, BACKUP_PATH)
        print(f"  Backed up {BRIEFS_PATH.name} -> {BACKUP_PATH.name}")
        with open(BACKUP_PATH, encoding="utf-8") as fh:
            source_briefs = json.load(fh)

    # -- Step 2: load supporting structured data -------------------------------
    print("\n[2/6] Loading accounts, answer key, and usage data ...")
    accounts_df = pd.read_csv(DATA_DIR / "accounts.csv")
    answer_key  = pd.read_csv(DATA_DIR / "answer_key.csv")
    usage_df    = pd.read_csv(DATA_DIR / "usage_monthly.csv")
    print(f"  Accounts: {len(accounts_df)}  |  Answer key rows: {len(answer_key)}  "
          f"|  Usage rows: {len(usage_df):,}")

    archetype_map = answer_key.set_index("account_id")["archetype"].to_dict()
    accounts_map  = accounts_df.set_index("account_id")

    # -- Step 3: before-report (from the untouched backup) --------------------
    print("\n[3/6] Computing BEFORE position-in-life summary ...")
    before_df = pd.DataFrame(source_briefs)
    before_summary = summarise_positions("before", before_df, accounts_df, answer_key)

    # -- Step 4: group briefs by account, in original ticket_index order ------
    print("\n[4/6] Re-dating non-churn accounts (A1, A2, A6, A7, A8) ...")
    briefs_by_account: dict = {}
    for brief in source_briefs:
        briefs_by_account.setdefault(brief["account_id"], []).append(brief)
    for acc_id in briefs_by_account:
        briefs_by_account[acc_id].sort(key=lambda b: b["ticket_index"])

    n_accounts_fixed = 0
    n_tickets_fixed  = 0
    a6_no_dip_accounts = []

    usage_by_account = {acc_id: grp for acc_id, grp in usage_df.groupby("account_id")}

    for account_id, briefs in briefs_by_account.items():
        archetype = archetype_map.get(account_id)
        if archetype not in NON_CHURN_ARCHETYPES:
            continue  # leave churned archetypes (A3/A4/A5) completely untouched

        acc_row = accounts_map.loc[account_id]
        signup  = pd.Timestamp(acc_row["signup_date"])
        lo = signup + pd.Timedelta(days=LO_BUFFER_DAYS)
        hi = HI_DATE
        if hi <= lo:
            hi = lo + pd.Timedelta(days=7)  # defensive guard, not expected to trigger

        stages = [b["sentiment_stage"] for b in briefs]
        n_tickets = len(briefs)
        rng = account_rng_for(account_id)

        if archetype == "A7":
            new_dates = dates_for_a7(n_tickets, lo, hi, rng)
        elif archetype == "A6":
            acc_usage = usage_by_account.get(account_id, pd.DataFrame(columns=usage_df.columns))
            dip_start, dip_end = compute_dip_window(acc_usage)
            new_dates, no_dip = dates_for_a6(stages, lo, hi, rng, dip_start, dip_end)
            if no_dip:
                a6_no_dip_accounts.append(account_id)
        else:  # A1, A2, A8
            beta_a, beta_b = SCATTER_BETA_PARAMS[archetype]
            new_dates = dates_for_scatter(n_tickets, lo, hi, rng, beta_a, beta_b)

        # Enforce strictly non-decreasing order defensively (belt-and-suspenders)
        fixed_dates = []
        last = lo
        for d in new_dates:
            d = max(pd.Timestamp(d), last)
            d = min(d, hi)
            fixed_dates.append(d)
            last = d

        for brief, new_date in zip(briefs, fixed_dates):
            brief["date"] = new_date.strftime("%Y-%m-%d")

        n_accounts_fixed += 1
        n_tickets_fixed  += n_tickets

    print(f"  Accounts re-dated: {n_accounts_fixed}")
    print(f"  Tickets re-dated:  {n_tickets_fixed}")
    if a6_no_dip_accounts:
        print(f"  A6 accounts with NO detectable usage dip (arc placed mid-life): "
              f"{len(a6_no_dip_accounts)} -> {a6_no_dip_accounts}")
    else:
        print("  All A6 accounts had a detectable usage dip.")

    # -- Step 5: reassemble in original list order and write output -----------
    print("\n[5/6] Writing updated data/ticket_briefs.json ...")
    updated_lookup = {}
    for acc_id, briefs in briefs_by_account.items():
        for b in briefs:
            updated_lookup[(b["account_id"], b["ticket_index"])] = b

    final_briefs = [
        updated_lookup[(b["account_id"], b["ticket_index"])]
        for b in source_briefs
    ]

    assert BRIEFS_PATH.resolve() != BACKUP_PATH.resolve()  # re-confirm before write
    with open(BRIEFS_PATH, "w", encoding="utf-8") as fh:
        json.dump(final_briefs, fh, indent=2, ensure_ascii=False, default=str)
    print(f"  Written: {BRIEFS_PATH}  ({len(final_briefs):,} briefs)")

    # -- Step 6: after-report ---------------------------------------------------
    print("\n[6/6] Computing AFTER position-in-life summary ...")
    after_df = pd.DataFrame(final_briefs)
    after_summary = summarise_positions("after", after_df, accounts_df, answer_key)

    print("\n" + "=" * 70)
    print("PER-ARCHETYPE POSITION-IN-LIFE: BEFORE vs AFTER")
    print("(position = (ticket_date - signup) / (life_end - signup); "
          "life_end = churn_date for churners, else 2025-12-31)")
    print("=" * 70)
    header = f"{'Arc':<5}{'Churns?':<9}{'n':>6}   {'BEFORE med':>11} {'p25':>7} {'p75':>7} {'IQR':>7}   ->   {'AFTER med':>10} {'p25':>7} {'p75':>7} {'IQR':>7}"
    print(header)
    print("-" * len(header))
    for archetype in sorted(set(before_summary.index) | set(after_summary.index)):
        churns = config.ARCHETYPE_CHURNS.get(archetype, "?")
        b = before_summary.loc[archetype]
        a = after_summary.loc[archetype]
        print(
            f"{archetype:<5}{str(churns):<9}{int(a['n_tickets']):>6}   "
            f"{b['median_pos']:>11.3f} {b['p25']:>7.3f} {b['p75']:>7.3f} {b['iqr']:>7.3f}   ->   "
            f"{a['median_pos']:>10.3f} {a['p25']:>7.3f} {a['p75']:>7.3f} {a['iqr']:>7.3f}"
        )

    print("\nDone. Run validate_data.py to verify all coherence rules including Rule 8.")


if __name__ == "__main__":
    main()
