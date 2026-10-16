"""
regenerate_a4_briefs.py — Redesigns A4 ("quietly unhappy") tickets as LOW-VOLUME.

Design context (see config.A4_LOW_VOLUME_TICKET_PARAMS,
and data/model/ml_report.md's v1->v3 honesty trail): three generations of
metadata quieting (csat in v2, then resolved/resolution_days in v3 via
fix_a4_ticket_metadata.py) still failed to make A4 invisible to the classical
model. The reason, diagnosed in v3's SHAP breakdown: A4's TICKET VOLUME
itself, independent of sentiment or outcome, was the residual fingerprint
(mean ticket_count_6m 6.65 for A4 vs 1.04 for healthy A1 — see ml_report.md
"A4 before -> after"). The fix: A4 accounts now file
FEW tickets, like a healthy account in volume. Their disengagement shows as
going quiet, not as traffic — each of the small number of tickets they do
file is long, polite, and densely documented (a prose-layer instruction for
the ticket-writer agent, not something this script controls).

What this script does, for A4 accounts ONLY (identified via
data/answer_key.csv):
  1. Backs up the CURRENT data/ticket_briefs.json (the v3 "close-the-tickets"
     high-volume state) to data/ticket_briefs_v3_a4highvolume.json. Skipped,
     with a warning, if that backup already exists (re-running this script
     must never clobber the one true "before" snapshot with an
     already-regenerated state).
  2. For each A4 account, generates a fresh, LOW-VOLUME set of ticket briefs
     (config.A4_LOW_VOLUME_TICKET_PARAMS: Poisson(4.3) clipped to [3, 6]
     tickets total per account across its whole life), keeping the designed
     signal structure:
       - the frustration arc (neutral -> mild_frustration -> frustrated ->
         competitor_mention -> unresolved_complaint) is still present,
         compressed to fit the lower ticket count;
       - at least one competitor mention per account, reusing the SAME
         competitor the account mentioned in the old (high-volume) briefs
         wherever one existed there (persisted forward for narrative
         continuity — checked at run time, see step 4 below);
       - the metadata stays "closed" per the v3 close-the-tickets design:
         resolved = True, resolution_days drawn uniformly from [1, 5];
       - 1-2 consistent contact personas per account (drawn fresh, same
         persona pools as generate_ticket_briefs.py);
       - most of the account's tickets are dated in the trailing 6-month
         feature window (window ends config.A4_LOW_VOLUME_TICKET_PARAMS'
         snapshot_lead_months before churn, spans window_months backward
         from there -- this mirrors build_features.py's SNAPSHOT_LEAD_MONTHS
         / TREND_LONG_MONTHS exactly), with the remainder dated earlier in
         the account's life as the "early neutral" stage of the arc. This is
         deliberate: the goal is trailing-window ticket VOLUME that reads
         like a healthy account (A1/A8), not lifetime volume.
  3. Splices the new A4 brief blocks into data/ticket_briefs.json IN PLACE,
     at the position each account's old block occupied, leaving every other
     archetype's brief dicts untouched (same object references — verified
     byte-identical at the end of this script's run).
  4. Does NOT touch data/tickets_raw/ or data/tickets.csv — the ticket-writer
     prose for the new low-volume briefs is written afterwards. That is
     code/replace_a4_prose.py's job, run later once
     code/make_a4_rewrite_batches.py's batches have been written by the
     ticket-writer agent into data/tickets_raw_a4/.
  5. Also does NOT touch data/answer_key.csv: its planted_signals column for
     A4 is an archetype-level list of signal TYPE names ("competitor_mention;
     unresolved_complaint;frustration_escalation", identical for every A4
     account -- see generate_structured.py), not per-ticket references. All
     three signal types are still genuinely present in the low-volume
     design (guaranteed >=1 competitor mention, an unresolved-complaint
     stage, and a compressed-but-intact frustration arc), so the column
     remains truthful without modification.

Run from the project root:
    python code/regenerate_a4_briefs.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Resolve paths — this script only ever writes to BRIEFS_PATH and
# BRIEFS_BACKUP_PATH, both explicitly named below
# ---------------------------------------------------------------------------

SCRIPT_DIR   = Path(__file__).resolve().parent            # .../code/
PROJECT_ROOT = SCRIPT_DIR.parent                            # .../01 Churn/
DATA_DIR     = PROJECT_ROOT / "data"

sys.path.insert(0, str(SCRIPT_DIR))
import config                          # noqa: E402  (must come after sys.path insert)
import generate_ticket_briefs as gtb   # noqa: E402  (reuse persona/date/module helpers)

ACCOUNTS_PATH      = DATA_DIR / "accounts.csv"
USAGE_PATH         = DATA_DIR / "usage_monthly.csv"
ANSWER_KEY_PATH    = DATA_DIR / "answer_key.csv"
BRIEFS_PATH        = DATA_DIR / "ticket_briefs.json"
BRIEFS_BACKUP_PATH = DATA_DIR / "ticket_briefs_v3_a4highvolume.json"

# Safety: output paths must never collide with any read-only input, and the
# backup must never collide with the file it backs up.
for _input_path in (ACCOUNTS_PATH, USAGE_PATH, ANSWER_KEY_PATH):
    assert _input_path.resolve() != BRIEFS_BACKUP_PATH.resolve(), (
        f"Refusing to run: backup path collides with input file {_input_path}"
    )
    assert _input_path.resolve() != BRIEFS_PATH.resolve(), (
        f"Refusing to run: output path collides with input file {_input_path}"
    )
assert BRIEFS_BACKUP_PATH.resolve() != BRIEFS_PATH.resolve(), (
    "Refusing to run: backup path collides with the file being backed up"
)

# ---------------------------------------------------------------------------
# Config block
# ---------------------------------------------------------------------------

# Fresh seed offset, distinct from TICKET_SEED (generate_ticket_briefs.py,
# config.RANDOM_SEED + 1000), CSAT_SEED (assemble_tickets.py, 42), and
# A4_CLOSE_SEED (fix_a4_ticket_metadata.py, config.RANDOM_SEED + 4000) — so
# this draw never accidentally reuses another script's random stream.
A4_LOWVOL_SEED = config.RANDOM_SEED + 5000

PARAMS       = config.A4_LOW_VOLUME_TICKET_PARAMS
ARC          = config.ARCHETYPE_TICKET_ARCS["A4"]   # chronological, 5 stages
CORE_STAGES  = ARC[1:-1]                              # middle 3 (excludes first/last)
FIRST_STAGE  = ARC[0]                                 # "neutral"
LAST_STAGE   = ARC[-1]                                # "unresolved_complaint"

# Reference figures from ml_report.md's ticket-window diagnostic (v3 run),
# quoted here purely for the printed before/after comparison — not used in
# any computation, just context for the report.
ML_REPORT_A1_MEAN_TICKET_COUNT_6M = 1.04
ML_REPORT_A1_MEDIAN_TICKET_COUNT_6M = 1.0
ML_REPORT_A8_MEAN_TICKET_COUNT_6M = 1.39
ML_REPORT_A8_MEDIAN_TICKET_COUNT_6M = 1.0
ML_REPORT_A4_MEAN_TICKET_COUNT_6M_BEFORE = 6.65


# ---------------------------------------------------------------------------
# Feature-window helper — mirrors build_features.py's SNAPSHOT_LEAD_MONTHS /
# TREND_LONG_MONTHS math exactly (see config.A4_LOW_VOLUME_TICKET_PARAMS'
# comment: these two numbers must stay in sync with build_features.py)
# ---------------------------------------------------------------------------

def compute_feature_window(churn_ts: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    """
    Returns (window_start, window_end): the trailing ticket-count window
    build_features.py will actually use for this account once its churn
    date is known. window_end = last day of (churn_month - lead_months);
    window_start = first day of (churn_month - lead_months - (window_months - 1)).
    """
    lead_months   = PARAMS["snapshot_lead_months"]
    window_months = PARAMS["window_months"]

    snapshot_period = churn_ts.to_period("M") - lead_months
    snapshot_start  = snapshot_period.to_timestamp(how="start")
    window_end      = snapshot_start + pd.offsets.MonthEnd(0)
    window_start    = snapshot_start - pd.DateOffset(months=window_months - 1)
    return window_start, window_end


def in_window_count(account_briefs: list[dict], window_start: pd.Timestamp, window_end: pd.Timestamp) -> int:
    """Counts how many of an account's briefs fall inside [window_start, window_end]."""
    count = 0
    for brief in account_briefs:
        ticket_date = pd.Timestamp(brief["date"])
        if window_start <= ticket_date <= window_end:
            count += 1
    return count


# ---------------------------------------------------------------------------
# Stage-sequence builder — compresses the 5-stage A4 arc to fit a low total
# ticket count while guaranteeing the "early neutral -> recurring-issue
# documentation -> resignation" shape and at least one competitor mention
# ---------------------------------------------------------------------------

def build_stage_sequence(n_tickets: int, rng: np.random.Generator) -> list[str]:
    """
    Returns an ordered (chronological) list of n_tickets sentiment stages,
    always starting with FIRST_STAGE ("neutral") and ending with LAST_STAGE
    ("unresolved_complaint"), with the middle slots filled from CORE_STAGES
    ("mild_frustration", "frustrated", "competitor_mention") — guaranteeing
    "competitor_mention" appears somewhere in the sequence.
    """
    if n_tickets <= 1:
        return [LAST_STAGE]

    n_middle = n_tickets - 2
    if n_middle <= 0:
        middle = []
    elif n_middle <= len(CORE_STAGES):
        chosen = set(rng.choice(CORE_STAGES, size=n_middle, replace=False).tolist())
        if "competitor_mention" not in chosen:
            # Guarantee the design requirement: at least one competitor
            # mention among this account's briefs. Swap the chronologically
            # last chosen middle stage for "competitor_mention".
            ordered_chosen = [s for s in CORE_STAGES if s in chosen]
            if ordered_chosen:
                ordered_chosen[-1] = "competitor_mention"
            else:
                ordered_chosen = ["competitor_mention"]
            chosen = set(ordered_chosen)
        middle = [s for s in CORE_STAGES if s in chosen]
    else:
        # More middle slots than core stages (n_tickets == max_total == 6):
        # use the whole core, then pad with extra unresolved-complaint
        # follow-ups — a customer who keeps reporting that the "fix" from
        # last time did not hold (the design's planted-follow-up pattern).
        extra = n_middle - len(CORE_STAGES)
        middle = list(CORE_STAGES) + ["unresolved_complaint"] * extra

    return [FIRST_STAGE] + middle + [LAST_STAGE]


def planted_signal_label(stage: str, competitor_mention: str | None) -> str | None:
    """Tags briefs that carry planted signals for traceability (mirrors
    generate_ticket_briefs.py's _planted_signal_label for the A4 case)."""
    if competitor_mention:
        return f"competitor_mention:{competitor_mention}"
    if stage == "unresolved_complaint":
        return "unresolved_complaint"
    if stage == "competitor_mention":
        return "competitor_mention_stage"
    return None


# ---------------------------------------------------------------------------
# Date sampling — most tickets land inside the trailing feature window, the
# rest ("early neutral") land earlier in the account's life
# ---------------------------------------------------------------------------

def spread_dates(start: pd.Timestamp, end: pd.Timestamp, n: int, rng: np.random.Generator) -> list[pd.Timestamp]:
    """Spreads n business-day-weighted dates across [start, end], sorted."""
    if n <= 0:
        return []
    if end <= start:
        return sorted([gtb.sample_business_day(start, start, rng) for _ in range(n)])

    total_days = (end - start).days
    offsets = np.sort(rng.uniform(0, 1, n))
    dates = []
    for off in offsets:
        day_offset = int(off * total_days)
        d_start = start + pd.Timedelta(days=day_offset)
        d_end   = min(start + pd.Timedelta(days=day_offset + 5), end)
        if d_end < d_start:
            d_end = d_start
        dates.append(gtb.sample_business_day(d_start, d_end, rng))
    return sorted(dates)


def sample_dates_for_account(
    n_early: int,
    n_window: int,
    signup_ts: pd.Timestamp,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    rng: np.random.Generator,
) -> list[pd.Timestamp]:
    """
    Returns n_early + n_window chronologically sorted dates: n_early dates
    before window_start (the "early neutral" period) and n_window dates
    inside [window_start, window_end]. Degenerate case (short-tenure
    account where window_start sits right on top of signup_ts, leaving no
    distinct "before window" period): spreads all dates across
    [signup_ts, window_end] in one pass instead.
    """
    if window_start - signup_ts > pd.Timedelta(days=3):
        early_end   = window_start - pd.Timedelta(days=1)
        early_dates = spread_dates(signup_ts, early_end, n_early, rng)
        window_dates = spread_dates(window_start, window_end, n_window, rng)
        return early_dates + window_dates
    return spread_dates(signup_ts, window_end, n_early + n_window, rng)


# ---------------------------------------------------------------------------
# Build the new low-volume brief set for one A4 account
# ---------------------------------------------------------------------------

def build_low_volume_briefs(
    account: pd.Series,
    acc_usage: pd.DataFrame,
    preferred_competitor: str,
    acc_rng: np.random.Generator,
) -> list[dict]:
    """Generates the new, low-volume ticket brief list for one A4 account."""
    signup_ts = pd.Timestamp(account["signup_date"])
    churn_ts  = pd.Timestamp(account["churn_date"])

    # ---- Total ticket count: Poisson, clipped to [min_total, max_total] ----
    n_raw     = acc_rng.poisson(PARAMS["poisson_lambda"])
    n_tickets = int(np.clip(n_raw, PARAMS["min_total"], PARAMS["max_total"]))

    # ---- Split into "early" (before the feature window) vs "in-window" ----
    if n_tickets >= PARAMS["early_high_n_threshold"]:
        n_early = PARAMS["early_count_high_n"]
    else:
        n_early = PARAMS["early_count_low_n"]
    n_early  = min(n_early, n_tickets - 1)   # always leave >=1 in-window ticket
    n_window = n_tickets - n_early

    # ---- Feature window (mirrors build_features.py exactly) ----------------
    window_start, window_end = compute_feature_window(churn_ts)
    window_start = max(window_start, signup_ts)
    if window_end <= signup_ts:
        window_end = signup_ts + pd.Timedelta(days=30)   # guard, shouldn't trigger
    if window_start > window_end:
        window_start = window_end

    # ---- Stage sequence + dates, zipped in chronological order -------------
    stage_sequence = build_stage_sequence(n_tickets, acc_rng)
    dates = sample_dates_for_account(n_early, n_window, signup_ts, window_start, window_end, acc_rng)

    # ---- Personas: 1-2 per account, same pools as generate_ticket_briefs.py
    n_personas = int(acc_rng.choice([1, 1, 2], p=[0.5, 0.3, 0.2]))
    personas   = gtb.sample_personas(n_personas, acc_rng)

    briefs = []
    for i, (stage, ticket_date) in enumerate(zip(stage_sequence, dates)):
        # Declining-module detection (Rule 1 mechanism) — reused verbatim
        # from generate_ticket_briefs.py; A4 has no detectable decline this
        # far from churn (Rule 2), so this is expected to come back empty
        # for nearly every ticket.
        win_lo = ticket_date - pd.DateOffset(months=2)
        win_hi = ticket_date + pd.DateOffset(months=1)
        declining = gtb.find_declining_metrics(acc_usage, win_lo, win_hi)

        module = gtb.pick_module_for_ticket(
            archetype="A4",
            sentiment_stage=stage,
            usage_row=None,
            account_rng=acc_rng,
            declining_modules=declining if declining else None,
        )

        # Competitor mention: guaranteed on the "competitor_mention" stage
        # (reusing the SAME competitor the account mentioned before, where
        # one existed), with a chance of a second, natural-feeling mention
        # on a later frustrated/unresolved-complaint ticket (mirrors
        # generate_ticket_briefs.py's should_inject_competitor_mention rate).
        competitor_mention = None
        if stage == "competitor_mention":
            competitor_mention = preferred_competitor
        elif stage in ("frustrated", "unresolved_complaint") and acc_rng.random() < 0.65:
            competitor_mention = preferred_competitor

        # Metadata stays "closed" per the v3 close-the-tickets design: every
        # A4 ticket is resolved, resolution_days drawn uniformly 1-5.
        resolved        = True
        resolution_days = int(acc_rng.integers(1, 6))   # inclusive 1-5

        persona = personas[i % len(personas)]

        briefs.append({
            "account_id":          account["account_id"],
            "ticket_index":        i + 1,
            "date":                ticket_date.strftime("%Y-%m-%d"),
            "module":              module,
            "sentiment_stage":     stage,
            "resolved":            resolved,
            "resolution_days":     resolution_days,
            "competitor_mention":  competitor_mention,
            "contact_name":        persona["name"],
            "contact_title":       persona["title"],
            "planted_signal":      planted_signal_label(stage, competitor_mention),
            "archetype_hint":      "A4",
            "declining_metrics":   declining,
            "account_arr_eur":     int(account["arr_eur"]),
            "plan_tier":           account["plan_tier"],
        })

    return briefs


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("regenerate_a4_briefs.py — A4 redesigned as LOW-VOLUME")
    print(f"Seed: {A4_LOWVOL_SEED}")
    print("=" * 70)

    # ---- Step 1: load inputs -------------------------------------------
    print("\n[1/6] Loading accounts.csv, usage_monthly.csv, answer_key.csv, ticket_briefs.json...")
    for p in (ACCOUNTS_PATH, USAGE_PATH, ANSWER_KEY_PATH, BRIEFS_PATH):
        if not p.exists():
            print(f"ERROR: {p} not found.")
            sys.exit(1)

    accounts_df = pd.read_csv(ACCOUNTS_PATH)
    usage_df    = pd.read_csv(USAGE_PATH)
    answer_key  = pd.read_csv(ANSWER_KEY_PATH)

    with open(BRIEFS_PATH, encoding="utf-8") as fh:
        current_briefs = json.load(fh)
    print(f"  {len(accounts_df)} accounts, {len(usage_df):,} usage rows, "
          f"{len(current_briefs):,} current ticket briefs loaded")

    a4_ids = set(answer_key.loc[answer_key["archetype"] == "A4", "account_id"])
    print(f"  A4 accounts identified: {len(a4_ids)}")

    # ---- Step 2: back up the current (v3 high-volume) briefs file -------
    print("\n[2/6] Backing up current ticket_briefs.json...")
    if BRIEFS_BACKUP_PATH.exists():
        print(f"  Backup already exists at {BRIEFS_BACKUP_PATH.name} — skipping "
              f"(not overwriting a possibly-already-regenerated file onto the pre-fix snapshot).")
    else:
        with open(BRIEFS_PATH, encoding="utf-8") as fh:
            raw_text = fh.read()
        with open(BRIEFS_BACKUP_PATH, "w", encoding="utf-8") as fh:
            fh.write(raw_text)
        print(f"  Backed up {BRIEFS_PATH.name} -> {BRIEFS_BACKUP_PATH.name}")

    # ---- Step 3: find each A4 account's preferred (previously mentioned)
    #      competitor, so the new low-volume briefs keep continuity --------
    print("\n[3/6] Finding each A4 account's previously-mentioned competitor...")
    preferred_competitor_by_account: dict[str, str] = {}
    for brief in current_briefs:
        acc_id = brief["account_id"]
        if acc_id in a4_ids and brief.get("competitor_mention"):
            preferred_competitor_by_account.setdefault(acc_id, brief["competitor_mention"])
    n_preserved = len(preferred_competitor_by_account)
    print(f"  {n_preserved}/{len(a4_ids)} A4 accounts had a competitor mention in the "
          f"current briefs — carrying it forward.")
    n_fresh_assignment = len(a4_ids) - n_preserved
    if n_fresh_assignment:
        print(f"  {n_fresh_assignment} A4 accounts had none — will be assigned a fresh "
              f"competitor (seeded, deterministic).")

    # ---- Step 4: group current briefs by account (for old stats + splice) -
    old_briefs_by_account: dict[str, list[dict]] = {}
    for brief in current_briefs:
        old_briefs_by_account.setdefault(brief["account_id"], []).append(brief)

    # ---- Step 5: build new low-volume briefs for every A4 account ---------
    print("\n[4/6] Generating new low-volume briefs for every A4 account...")
    accounts_by_id = accounts_df.set_index("account_id")
    new_briefs_by_account: dict[str, list[dict]] = {}
    before_after_rows = []

    for acc_id in sorted(a4_ids):
        account   = accounts_by_id.loc[acc_id]
        account_s = pd.Series({**account.to_dict(), "account_id": acc_id})
        acc_usage = usage_df[usage_df["account_id"] == acc_id].sort_values("month")

        acc_seed = A4_LOWVOL_SEED + hash(acc_id) % (2**31)
        acc_rng  = np.random.default_rng(acc_seed)

        preferred = preferred_competitor_by_account.get(acc_id)
        if preferred is None:
            preferred = str(acc_rng.choice(config.COMPETITOR_NAMES))

        new_briefs = build_low_volume_briefs(account_s, acc_usage, preferred, acc_rng)
        new_briefs_by_account[acc_id] = new_briefs

        # Before/after stats using the SAME window definition for both
        churn_ts = pd.Timestamp(account["churn_date"])
        window_start, window_end = compute_feature_window(churn_ts)

        old_briefs = old_briefs_by_account.get(acc_id, [])
        before_after_rows.append({
            "account_id":       acc_id,
            "old_total":        len(old_briefs),
            "new_total":        len(new_briefs),
            "old_in_window":    in_window_count(old_briefs, window_start, window_end),
            "new_in_window":    in_window_count(new_briefs, window_start, window_end),
        })

    stats_df = pd.DataFrame(before_after_rows)
    print(f"  Regenerated briefs for {len(new_briefs_by_account)} A4 accounts.")

    # ---- Step 6: splice new A4 blocks into the full briefs list -----------
    print("\n[5/6] Splicing new A4 brief blocks into the full ticket_briefs.json list...")
    new_full_briefs = []
    replaced_ids: set[str] = set()
    for brief in current_briefs:
        acc_id = brief["account_id"]
        if acc_id in a4_ids:
            if acc_id not in replaced_ids:
                new_full_briefs.extend(new_briefs_by_account[acc_id])
                replaced_ids.add(acc_id)
            # else: subsequent old A4 brief for an already-spliced account — drop it
        else:
            new_full_briefs.append(brief)   # same object, byte-identical

    missing_splice = a4_ids - replaced_ids
    if missing_splice:
        print(f"  ERROR: {len(missing_splice)} A4 accounts were never spliced in "
              f"(no briefs found in current_briefs for them): {sorted(missing_splice)[:5]}")
        sys.exit(1)

    with open(BRIEFS_PATH, "w", encoding="utf-8") as fh:
        json.dump(new_full_briefs, fh, indent=2, ensure_ascii=False, default=str)
    print(f"  Written: {BRIEFS_PATH}  ({len(new_full_briefs):,} briefs total, "
          f"was {len(current_briefs):,})")

    # ---- Step 7: byte-level verification that non-A4 briefs are untouched -
    print("\n[6/6] Verifying non-A4 briefs are byte-identical...")
    with open(BRIEFS_PATH, encoding="utf-8") as fh:
        reloaded_briefs = json.load(fh)

    old_non_a4 = [b for b in current_briefs if b["account_id"] not in a4_ids]
    new_non_a4 = [b for b in reloaded_briefs if b["account_id"] not in a4_ids]

    mismatches = 0
    if len(old_non_a4) != len(new_non_a4):
        print(f"  ERROR: non-A4 brief COUNT changed: {len(old_non_a4)} -> {len(new_non_a4)}")
        mismatches += 1
    else:
        for old_b, new_b in zip(old_non_a4, new_non_a4):
            old_str = json.dumps(old_b, ensure_ascii=False, sort_keys=True)
            new_str = json.dumps(new_b, ensure_ascii=False, sort_keys=True)
            if old_str != new_str:
                mismatches += 1

    if mismatches == 0:
        print(f"  OK: all {len(old_non_a4):,} non-A4 briefs are byte-identical "
              f"before and after regeneration.")
    else:
        print(f"  WARNING: {mismatches} non-A4 brief mismatches found — investigate before proceeding.")

    # ---- Summary report -----------------------------------------------
    print("\n" + "=" * 70)
    print("A4 VOLUME: BEFORE -> AFTER")
    print("=" * 70)
    print(f"  Accounts: {len(stats_df)}")
    print(f"  Total tickets (lifetime):     "
          f"before mean {stats_df['old_total'].mean():.2f} (sum {stats_df['old_total'].sum()})  ->  "
          f"after mean {stats_df['new_total'].mean():.2f} (sum {stats_df['new_total'].sum()})")
    print(f"  Trailing 6-month window count: "
          f"before mean {stats_df['old_in_window'].mean():.2f} (median {stats_df['old_in_window'].median():.1f})  ->  "
          f"after mean {stats_df['new_in_window'].mean():.2f} (median {stats_df['new_in_window'].median():.1f})")
    print(f"\n  Reference (from ml_report.md v3 ticket-window diagnostic):")
    print(f"    A1 (healthy stable):  mean ticket_count_6m {ML_REPORT_A1_MEAN_TICKET_COUNT_6M} "
          f"(median {ML_REPORT_A1_MEDIAN_TICKET_COUNT_6M})")
    print(f"    A8 (quiet decline):   mean ticket_count_6m {ML_REPORT_A8_MEAN_TICKET_COUNT_6M} "
          f"(median {ML_REPORT_A8_MEDIAN_TICKET_COUNT_6M})")
    print(f"    A4 (before this run): mean ticket_count_6m {ML_REPORT_A4_MEAN_TICKET_COUNT_6M_BEFORE}")
    print(f"    A4 (after this run):  mean ticket_count_6m {stats_df['new_in_window'].mean():.2f}")

    print(f"\n  New total-ticket distribution: "
          f"min {stats_df['new_total'].min()}, median {stats_df['new_total'].median():.1f}, "
          f"max {stats_df['new_total'].max()}")
    print(f"  New in-window distribution:    "
          f"min {stats_df['new_in_window'].min()}, median {stats_df['new_in_window'].median():.1f}, "
          f"max {stats_df['new_in_window'].max()}")

    print("\nDone. Next: python code/make_a4_rewrite_batches.py, then hand the batches to a "
          "ticket-writer agent, then (once prose exists) code/replace_a4_prose.py.")
    print("Do NOT run assemble_tickets.py / build_features.py / train_models.py yet — "
          "data/tickets_raw/ still holds the OLD high-volume A4 prose.")
    print("=" * 70)


if __name__ == "__main__":
    main()
