"""
generate_ticket_briefs.py — Generates ticket_briefs.json.

Produces a structured list of ticket briefs for every account.
Each brief is a JSON object describing a single ticket's metadata and
planted signals.  Actual ticket prose is generated later by an LLM agent
that reads these briefs; the structure and signals are deterministic here.

Requires accounts.csv, usage_monthly.csv, and answer_key.csv to already exist
(run generate_structured.py first).

Run from the project root:
    python code/generate_ticket_briefs.py

Output:
    data/ticket_briefs.json
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Resolve paths
# ---------------------------------------------------------------------------

SCRIPT_DIR   = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR     = PROJECT_ROOT / "data"

sys.path.insert(0, str(SCRIPT_DIR))
import config

# ---------------------------------------------------------------------------
# Global RNG (separate seed offset so briefs are reproducible independently)
# ---------------------------------------------------------------------------

TICKET_SEED = config.RANDOM_SEED + 1000
rng_global  = np.random.default_rng(TICKET_SEED)

# ---------------------------------------------------------------------------
# Persona name pools (1–2 consistent contact personas per account)
# ---------------------------------------------------------------------------

FIRST_NAMES_NORDIC = [
    "Aino", "Mikael", "Sanna", "Erik", "Liisa", "Oskar", "Maria", "Jens",
    "Tuomas", "Kristina", "Lars", "Hanna", "Nils", "Emma", "Pekka", "Ingrid",
    "Ville", "Astrid", "Matti", "Sigrid", "Risto", "Marit", "Eero", "Britta",
    "Timo", "Helena", "Juha", "Maja", "Tero", "Anna",
]

LAST_NAMES_NORDIC = [
    "Korhonen", "Lindqvist", "Halvorsen", "Eriksen", "Mäkinen", "Bergström",
    "Virtanen", "Hansen", "Leinonen", "Nordgren", "Heikkinen", "Larsson",
    "Nieminen", "Holm", "Peltonen", "Strand", "Jokinen", "Bäck", "Koskinen",
    "Dahl", "Salminen", "Lund", "Harjula", "Møller", "Lehtinen", "Johansson",
]

JOB_TITLES = [
    "Finance Manager", "Head of Operations", "BI Analyst", "Data Engineer",
    "Financial Controller", "IT Manager", "Head of Reporting",
    "Senior Analyst", "VP Finance", "Operations Lead",
]

def sample_personas(n_personas: int, account_rng: np.random.Generator) -> list[dict]:
    """Draw n_personas contact personas (name, job title) for one account."""
    personas = []
    for _ in range(n_personas):
        first = account_rng.choice(FIRST_NAMES_NORDIC)
        last  = account_rng.choice(LAST_NAMES_NORDIC)
        title = account_rng.choice(JOB_TITLES)
        personas.append({"name": f"{first} {last}", "title": title})
    return personas


# ---------------------------------------------------------------------------
# Business-day weighted date sampling
# ---------------------------------------------------------------------------

def sample_business_day(
    start: pd.Timestamp,
    end: pd.Timestamp,
    account_rng: np.random.Generator,
) -> pd.Timestamp:
    """
    Sample a single date between start and end (inclusive) with business-day
    weighting (weekdays 3× more likely than weekends).
    """
    if start > end:
        return start

    date_range = pd.date_range(start=start, end=end, freq="D")
    if len(date_range) == 0:
        return start

    weights = np.where(date_range.weekday < 5, 3.0, 1.0)
    weights = weights / weights.sum()
    idx = account_rng.choice(len(date_range), p=weights)
    return date_range[idx]


# ---------------------------------------------------------------------------
# Module selection logic — correlate with usage story
# ---------------------------------------------------------------------------

def pick_module_for_ticket(
    archetype: str,
    sentiment_stage: str,
    usage_row: pd.Series | None,
    account_rng: np.random.Generator,
    declining_modules: list[str] | None = None,
) -> str:
    """
    Select a module for this ticket.

    Coherence rule 1: if usage is declining, tickets in that period must
    reference the declining modules with higher probability.
    """
    modules = config.MODULE_NAMES

    if declining_modules and sentiment_stage in (
        "frustrated", "angry", "escalation", "unresolved_complaint",
        "competitor_mention", "mild_frustration", "resigned",
    ):
        # Weight declining modules 4× more
        weights = np.array([
            4.0 if config.FEATURE_MAP[m]["metric"] in declining_modules else 1.0
            for m in modules
        ], dtype=float)
    else:
        weights = np.ones(len(modules), dtype=float)

    weights /= weights.sum()
    return account_rng.choice(modules, p=weights)


# ---------------------------------------------------------------------------
# Determine which metrics are declining in a given month window
# ---------------------------------------------------------------------------

def find_declining_metrics(
    account_usage: pd.DataFrame,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> list[str]:
    """
    Return a list of metric column names that show a negative trend
    in the given window for this account's usage data.
    """
    metrics = [
        "dashboard_views", "reports_created", "connector_syncs",
        "alerts_configured", "api_calls", "exports_run", "logins",
    ]

    window_data = account_usage[
        (account_usage["month"] >= window_start.strftime("%Y-%m")) &
        (account_usage["month"] <= window_end.strftime("%Y-%m"))
    ]

    if len(window_data) < 2:
        return []

    declining = []
    for metric in metrics:
        if metric not in window_data.columns:
            continue
        series = window_data[metric].values
        if len(series) < 2:
            continue
        # Simple linear trend: negative slope = declining
        x = np.arange(len(series))
        slope = np.polyfit(x, series, 1)[0]
        if slope < -0.5:  # threshold: must be meaningfully declining
            declining.append(metric)

    return declining


# ---------------------------------------------------------------------------
# Arc stage allocation: spread ticket sentiment stages across the timeline
# ---------------------------------------------------------------------------

def allocate_arc_stages(
    archetype: str,
    n_tickets: int,
    account_rng: np.random.Generator,
) -> list[str]:
    """
    Allocate sentiment stage labels to n_tickets in chronological order,
    respecting the archetype's arc progression.
    """
    arc_template = config.ARCHETYPE_TICKET_ARCS[archetype]

    if n_tickets <= 0:
        return []

    if n_tickets <= len(arc_template):
        # Sample n_tickets stages from the arc in order
        indices = sorted(account_rng.choice(len(arc_template), size=n_tickets, replace=False))
        return [arc_template[i] for i in indices]

    # More tickets than arc stages — pad by repeating the dominant middle stages
    stages = []
    # Distribute tickets across arc segments
    seg_size = n_tickets / len(arc_template)
    for stage in arc_template:
        count = max(1, round(seg_size))
        stages.extend([stage] * count)
    # Trim or extend to exactly n_tickets
    while len(stages) < n_tickets:
        stages.append(arc_template[-1])
    return stages[:n_tickets]


# ---------------------------------------------------------------------------
# Planted signal injection
# ---------------------------------------------------------------------------

def should_inject_competitor_mention(
    archetype: str,
    stage: str,
    account_rng: np.random.Generator,
    is_noise_account: bool = False,
) -> str | None:
    """
    Return a competitor name to mention, or None.

    Rules:
    - A4: inject competitor mentions in mid-to-late frustration stages
    - A7: NEVER inject competitor mentions (hard rule)
    - Healthy accounts (A1, A2, A7): optional noise at noise rate
    - A6: never during anger phase, can appear once post-resolution as noise
    """
    if archetype == "A7":
        return None

    if archetype == "A4" and stage in ("competitor_mention", "unresolved_complaint", "frustrated"):
        if account_rng.random() < 0.65:
            return account_rng.choice(config.COMPETITOR_NAMES)

    if is_noise_account and archetype in ("A1", "A2") and stage in ("neutral", "routine", "positive"):
        if account_rng.random() < 0.30:
            # Noise: benign context (asking for comparison, not defecting)
            return account_rng.choice(config.COMPETITOR_NAMES)

    return None


def is_unresolved(
    archetype: str,
    stage: str,
    account_rng: np.random.Generator,
) -> bool:
    """
    Decide whether a ticket is unresolved.

    A4 unresolved_complaint stage: high probability of unresolved.
    A7: always resolved.
    All others: low baseline.
    """
    if archetype == "A7":
        return False
    if archetype == "A4" and stage == "unresolved_complaint":
        return account_rng.random() < 0.70
    if stage in ("frustrated", "angry", "escalation"):
        return account_rng.random() < 0.25
    return account_rng.random() < 0.07


def resolution_days(
    archetype: str,
    resolved: bool,
    stage: str,
    account_rng: np.random.Generator,
) -> int | None:
    """
    Draw resolution_days.

    A7: always ≤2 days (coherence rule 4).
    Unresolved: None.
    Others: log-normal distribution, higher for escalation stages.
    """
    if not resolved:
        return None
    if archetype == "A7":
        return int(account_rng.integers(1, 3))   # 1 or 2 days
    if stage in ("escalation", "unresolved_complaint", "angry"):
        days = int(np.ceil(account_rng.lognormal(mean=2.0, sigma=0.7)))
        return min(days, 30)
    days = int(np.ceil(account_rng.lognormal(mean=1.2, sigma=0.6)))
    return min(days, 21)


# ---------------------------------------------------------------------------
# Build briefs for a single account
# ---------------------------------------------------------------------------

def build_account_briefs(
    account: pd.Series,
    usage_df: pd.DataFrame,
    answer_key: pd.Series,
    noise_competitor: bool,
    account_rng: np.random.Generator,
) -> list[dict]:
    """
    Generate all ticket briefs for one account.
    Returns a list of brief dicts ready for JSON serialisation.
    """
    archetype  = answer_key["archetype"]
    arc_params = config.ARCHETYPE_TICKET_PARAMS[archetype]

    # ---- Draw number of tickets via negative-binomial-ish (Poisson for simplicity) --
    median  = arc_params["median"]
    max_t   = arc_params["max"]
    # Use a Gamma-Poisson approximation: draw Poisson with lambda ~ median
    # and apply a fat tail via the dispersion
    lam     = float(median) * 1.1
    n_raw   = account_rng.poisson(lam=lam)
    n_tickets = int(np.clip(n_raw, 1, max_t))

    signup_ts = pd.Timestamp(account["signup_date"])
    churn_ts  = pd.Timestamp(account["churn_date"]) if account["churn_date"] else None
    obs_end   = pd.Timestamp(config.OBS_END + "-01") + pd.offsets.MonthEnd(0)
    end_ts    = churn_ts if churn_ts is not None else obs_end

    # ---- Personas: 1–2 per account ------------------------------------------
    n_personas = int(account_rng.choice([1, 1, 2], p=[0.5, 0.3, 0.2]))
    personas   = sample_personas(n_personas, account_rng)

    # ---- Build the stage arc for this account -------------------------------
    stages = allocate_arc_stages(archetype, n_tickets, account_rng)

    # ---- Spread ticket dates across the active period -----------------------
    # Sort dates so arc stages run chronologically
    # Guard: ensure end_ts is after signup_ts to avoid zero/negative span
    if pd.isna(end_ts) or end_ts <= signup_ts:
        end_ts = signup_ts + pd.Timedelta(days=30)

    total_days = (end_ts - signup_ts).days
    if total_days < 2:
        ticket_dates = [signup_ts] * n_tickets
    else:
        raw_offsets = np.sort(account_rng.uniform(0, 1, n_tickets))
        ticket_dates = []
        for off in raw_offsets:
            day_offset = int(off * total_days)
            date_start = signup_ts + pd.Timedelta(days=day_offset)
            date_end   = min(
                signup_ts + pd.Timedelta(days=day_offset + 7),
                end_ts - pd.Timedelta(days=1),
            )
            # Ensure date_end >= date_start
            if date_end < date_start:
                date_end = date_start
            ticket_dates.append(
                sample_business_day(date_start, date_end, account_rng)
            )

    # ---- Account usage for declining-module detection -----------------------
    acc_usage = usage_df[usage_df["account_id"] == account["account_id"]].copy()
    acc_usage = acc_usage.sort_values("month")

    briefs = []
    for i, (stage, ticket_date) in enumerate(zip(stages, ticket_dates)):
        # Which metrics are declining in the 3 months around this ticket?
        window_start = ticket_date - pd.DateOffset(months=2)
        window_end   = ticket_date + pd.DateOffset(months=1)
        declining    = find_declining_metrics(acc_usage, window_start, window_end)

        module = pick_module_for_ticket(
            archetype=archetype,
            sentiment_stage=stage,
            usage_row=None,
            account_rng=account_rng,
            declining_modules=declining if declining else None,
        )

        resolved       = not is_unresolved(archetype, stage, account_rng)
        res_days       = resolution_days(archetype, resolved, stage, account_rng)
        competitor_mention = should_inject_competitor_mention(
            archetype, stage, account_rng, is_noise_account=noise_competitor
        )

        # Persona: cycle through account's personas (for consistency)
        persona = personas[i % len(personas)]

        brief = {
            "account_id":          account["account_id"],
            "ticket_index":        i + 1,
            "date":                ticket_date.strftime("%Y-%m-%d"),
            "module":              module,
            "sentiment_stage":     stage,
            "resolved":            resolved,
            "resolution_days":     res_days,
            "competitor_mention":  competitor_mention,
            "contact_name":        persona["name"],
            "contact_title":       persona["title"],
            # Planted signal flag for answer key traceability
            "planted_signal":      _planted_signal_label(archetype, stage, competitor_mention),
            # Context clues for the LLM prose generation step
            "archetype_hint":      archetype,
            "declining_metrics":   declining,
            "account_arr_eur":     int(account["arr_eur"]),
            "plan_tier":           account["plan_tier"],
        }
        briefs.append(brief)

    return briefs


def _planted_signal_label(
    archetype: str,
    stage: str,
    competitor_mention: str | None,
) -> str | None:
    """Tag briefs that carry planted signals for traceability."""
    if competitor_mention:
        return f"competitor_mention:{competitor_mention}"
    if archetype == "A4" and stage == "unresolved_complaint":
        return "unresolved_complaint"
    if archetype == "A4" and stage == "competitor_mention":
        return "competitor_mention_stage"
    if archetype == "A6" and stage in ("escalation", "resolution"):
        return f"arc_signal:{stage}"
    if archetype == "A7" and stage == "angry_resolved":
        return "fast_resolution"
    return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Kataja Analytics — Ticket Brief Generator")
    print(f"Seed: {TICKET_SEED}")
    print("=" * 60)

    # -- Load structured data -------------------------------------------------
    print("\n[1/3] Loading structured data...")
    accounts_path = DATA_DIR / "accounts.csv"
    usage_path    = DATA_DIR / "usage_monthly.csv"
    key_path      = DATA_DIR / "answer_key.csv"

    for p in [accounts_path, usage_path, key_path]:
        if not p.exists():
            print(f"ERROR: {p} not found. Run generate_structured.py first.")
            sys.exit(1)

    accounts_df  = pd.read_csv(accounts_path)
    usage_df     = pd.read_csv(usage_path)
    answer_key   = pd.read_csv(key_path).set_index("account_id")

    print(f"  Accounts loaded:   {len(accounts_df)}")
    print(f"  Usage rows loaded: {len(usage_df):,}")

    # -- Decide which healthy accounts get noise competitor mentions ----------
    healthy_mask = answer_key["archetype"].isin(["A1", "A2", "A7"])
    healthy_ids  = answer_key[healthy_mask].index.tolist()
    n_noise      = max(1, int(len(healthy_ids) * config.NOISE_COMPETITOR_MENTION_RATE))
    noise_ids    = set(
        rng_global.choice(healthy_ids, size=n_noise, replace=False).tolist()
    )
    print(f"  Healthy accounts with noise competitor mentions: {len(noise_ids)}")

    # -- Generate briefs per account ------------------------------------------
    print("\n[2/3] Generating ticket briefs for all accounts...")
    all_briefs = []
    for idx, account in accounts_df.iterrows():
        acc_id     = account["account_id"]
        arc        = answer_key.loc[acc_id, "archetype"]
        noise_flag = acc_id in noise_ids

        # Per-account deterministic RNG
        acc_seed = TICKET_SEED + hash(acc_id) % (2**31)
        acc_rng  = np.random.default_rng(acc_seed)

        briefs = build_account_briefs(
            account=account,
            usage_df=usage_df,
            answer_key=answer_key.loc[acc_id],
            noise_competitor=noise_flag,
            account_rng=acc_rng,
        )
        all_briefs.extend(briefs)

        if (idx + 1) % 100 == 0:
            print(f"  Processed {idx + 1}/{len(accounts_df)} accounts "
                  f"({len(all_briefs):,} briefs so far)...")

    print(f"  Total briefs generated: {len(all_briefs):,}")

    # -- Summary statistics ---------------------------------------------------
    briefs_df = pd.DataFrame(all_briefs)
    arc_col   = answer_key["archetype"].reset_index()
    arc_col.columns = ["account_id", "archetype"]
    briefs_with_arc = briefs_df.merge(arc_col, on="account_id", how="left")

    print("\n  Tickets per archetype:")
    arc_counts = briefs_with_arc.groupby("archetype").size()
    per_account = briefs_with_arc.groupby("account_id").size()
    print(arc_counts.to_string())
    print(f"\n  Tickets per account (min/median/max): "
          f"{per_account.min()} / {per_account.median():.1f} / {per_account.max()}")

    competitor_count = briefs_df["competitor_mention"].notna().sum()
    unresolved_count = (~briefs_df["resolved"]).sum()
    print(f"\n  Competitor mentions:   {competitor_count}")
    print(f"  Unresolved tickets:    {unresolved_count}")

    # -- Write output ---------------------------------------------------------
    print("\n[3/3] Writing ticket_briefs.json...")
    out_path = DATA_DIR / "ticket_briefs.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(all_briefs, fh, indent=2, ensure_ascii=False, default=str)
    print(f"  Written: {out_path}  ({len(all_briefs):,} briefs)")

    print("\nDone. Run validate_data.py to verify coherence rules.")


if __name__ == "__main__":
    main()
