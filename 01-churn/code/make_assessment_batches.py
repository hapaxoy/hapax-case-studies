"""
make_assessment_batches.py — Builds BLINDED ticket-reading batches for the
LLM assessor agents (the agent layer).

The assessor agents read an account's support ticket history and produce a
structured text-risk assessment. They must never see:
    - usage data (usage_monthly.csv)
    - the churn label (accounts.csv 'churned' / 'churn_date')
    - archetype or planted_signals (answer_key.csv)
    - ARR or plan tier (accounts.csv 'arr_eur' / 'plan_tier')
Each batch file therefore contains ONLY account_id and that account's
tickets (date, channel, subject, body, module, resolved, resolution_days).

Reading window: must match the ML feature window exactly (build_features.py),
so the two layers see the same information horizon. That
script computes, per account:
    snapshot_end  = churn month minus SNAPSHOT_LEAD_MONTHS (churned accounts)
                    or the observation window's last month minus
                    SNAPSHOT_LEAD_MONTHS (retained accounts)
    ticket_cutoff = last calendar day of the snapshot_end month
                    (ticket dates are exact days, usage rows are monthly
                    aggregates keyed to day 1, so the ticket cutoff has to be
                    month-end to include the whole snapshot month's tickets)
This script imports build_features.compute_snapshot_end() directly (rather
than re-deriving the formula) so the two layers are GUARANTEED to agree --
no risk of the cutoff logic drifting apart if build_features.py ever changes.

Accounts with zero tickets in the window are excluded from the batches
entirely (an LLM has nothing to read) and listed instead in
data/agent/no_ticket_accounts.csv; collect_assessments.py gives them a
neutral default score.

Run from the project root:
    python code/make_assessment_batches.py

Output:
    data/agent/assessment_batches/batch_NN.json
    data/agent/no_ticket_accounts.csv
"""

import json
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Resolve paths — output directories are created fresh, never touch source data
# ---------------------------------------------------------------------------

SCRIPT_DIR   = Path(__file__).resolve().parent            # .../code/
PROJECT_ROOT = SCRIPT_DIR.parent                           # .../01 Churn/
DATA_DIR     = PROJECT_ROOT / "data"
AGENT_DIR    = DATA_DIR / "agent"
BATCH_DIR    = AGENT_DIR / "assessment_batches"

ACCOUNTS_PATH            = DATA_DIR / "accounts.csv"
TICKETS_PATH             = DATA_DIR / "tickets.csv"
NO_TICKET_ACCOUNTS_PATH  = AGENT_DIR / "no_ticket_accounts.csv"

# Safety: confirm every output path is outside/different from every input path
for out_path in (NO_TICKET_ACCOUNTS_PATH,):
    for in_path in (ACCOUNTS_PATH, TICKETS_PATH):
        assert out_path.resolve() != in_path.resolve(), (
            f"Refusing to run: output path {out_path} collides with input path {in_path}"
        )
assert BATCH_DIR.resolve() not in (ACCOUNTS_PATH.resolve(), TICKETS_PATH.resolve()), (
    "Refusing to run: batch output directory collides with an input path"
)

sys.path.insert(0, str(SCRIPT_DIR))
import config          # noqa: E402  (must come after sys.path insert)
import build_features as bf  # noqa: E402  -- reused ONLY for its snapshot-date
                              # logic (compute_snapshot_end, SNAPSHOT_LEAD_MONTHS,
                              # RETAINED_CENSOR_MONTH); importing rather than
                              # re-deriving the formula guarantees the agent
                              # layer and the ML layer never see a different
                              # information horizon.

# ---------------------------------------------------------------------------
# Config block — everything tunable about the batch build lives here
# ---------------------------------------------------------------------------

ACCOUNTS_PER_BATCH = 20   # ~20 accounts per batch, whole accounts kept together

# The exact set of fields an assessor agent is allowed to see per ticket.
# Deliberately excludes ticket_id (no operational value to the assessment)
# and anything from accounts.csv / usage_monthly.csv / answer_key.csv.
TICKET_FIELDS = ["date", "channel", "subject", "body", "module", "resolved", "resolution_days"]

# Fields that must NEVER appear anywhere in a batch file — the blinding
# contract. Checked by a hard assertion after batches are built.
FORBIDDEN_FIELDS = {
    "churned", "churn_date", "archetype", "planted_signals", "churn_driver",
    "arr_eur", "plan_tier", "licensed_seats", "active_users", "dashboard_views",
    "reports_created", "connector_syncs", "alerts_configured", "api_calls",
    "exports_run", "logins", "company_name", "industry", "country",
}


# ---------------------------------------------------------------------------
# Load source data (read-only — never written back to)
# ---------------------------------------------------------------------------

def load_source_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Loads accounts and tickets (full tables — the text columns are exactly
    what this layer is allowed to see; the blinding happens at record-build
    time by simply never reading accounts' label/ARR/plan-tier columns into
    the per-account JSON records)."""
    print(f"Loading accounts from {ACCOUNTS_PATH}")
    accounts = pd.read_csv(ACCOUNTS_PATH, parse_dates=["signup_date", "churn_date"])

    print(f"Loading tickets from {TICKETS_PATH}")
    tickets = pd.read_csv(TICKETS_PATH, parse_dates=["created_at"])

    print(f"  accounts: {len(accounts)} rows | tickets: {len(tickets)} rows")
    return accounts, tickets


# ---------------------------------------------------------------------------
# Reading window — identical cutoff logic to build_features.py
# ---------------------------------------------------------------------------

def compute_reading_window(accounts: pd.DataFrame) -> pd.DataFrame:
    """
    Adds 'snapshot_end' and 'ticket_cutoff' columns to a copy of accounts.

    snapshot_end  comes straight from build_features.compute_snapshot_end()
                  (churn month / censoring month minus SNAPSHOT_LEAD_MONTHS).
    ticket_cutoff replicates build_features.py's inline
                  `snapshot_end + pd.offsets.MonthEnd(0)` line exactly (see
                  its build_features() function) — the last calendar day of
                  the snapshot month, so the whole snapshot month's tickets
                  are included even though ticket dates are exact days.
    """
    accounts = accounts.copy()
    accounts["snapshot_end"] = bf.compute_snapshot_end(accounts)
    accounts["ticket_cutoff"] = accounts["snapshot_end"] + pd.offsets.MonthEnd(0)
    return accounts


# ---------------------------------------------------------------------------
# Per-account blinded ticket records
# ---------------------------------------------------------------------------

def build_account_records(accounts: pd.DataFrame, tickets: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """
    For each account, builds a blinded record {account_id, tickets: [...]}
    containing only tickets with created_at <= ticket_cutoff, in chronological
    order. Accounts with zero tickets in the window are returned separately
    (they get no batch record at all).
    """
    records: list[dict] = []
    no_ticket_accounts: list[dict] = []

    print(f"Building blinded ticket windows for {len(accounts)} accounts...")
    for i, account in enumerate(accounts.itertuples(index=False), start=1):
        account_id = account.account_id
        cutoff = account.ticket_cutoff

        account_tickets = tickets[
            (tickets["account_id"] == account_id) & (tickets["created_at"] <= cutoff)
        ].sort_values("created_at")

        # Leakage guard: nothing past the cutoff made it into the window
        if len(account_tickets) > 0:
            assert account_tickets["created_at"].max() <= cutoff, (
                f"{account_id}: ticket leakage past ticket_cutoff={cutoff.date()}"
            )

        if len(account_tickets) == 0:
            no_ticket_accounts.append({"account_id": account_id, "reason": "no_tickets_in_window"})
            continue

        ticket_list = []
        for t in account_tickets.itertuples(index=False):
            ticket_list.append({
                "date": t.created_at.strftime("%Y-%m-%d"),
                "channel": t.channel,
                "subject": t.subject,
                "body": t.body,
                "module": t.module,
                "resolved": bool(t.resolved),
                "resolution_days": None if pd.isna(t.resolution_days) else float(t.resolution_days),
            })

        records.append({"account_id": account_id, "tickets": ticket_list})

        if i % 100 == 0 or i == len(accounts):
            print(f"  ...{i}/{len(accounts)} accounts processed")

    return records, no_ticket_accounts


def pack_batches(records: list[dict], accounts_per_batch: int) -> list[list[dict]]:
    """Packs whole-account records into batches of ~accounts_per_batch accounts
    each. Sorted by account_id first for reproducible, stable batch contents."""
    records = sorted(records, key=lambda r: r["account_id"])
    return [records[i:i + accounts_per_batch] for i in range(0, len(records), accounts_per_batch)]


# ---------------------------------------------------------------------------
# Validation pass — the blinding contract is a hard requirement, not optional
# ---------------------------------------------------------------------------

def validate_batches(batches: list[list[dict]], no_ticket_accounts: list[dict], accounts: pd.DataFrame) -> None:
    """Checks the blinding contract and full account coverage/partition."""
    print("Running validation pass on assessment batches...")

    # 1. Every account is accounted for exactly once: either in a batch or in
    #    the no-ticket list, never both, never neither.
    batched_ids = {rec["account_id"] for batch in batches for rec in batch}
    no_ticket_ids = {row["account_id"] for row in no_ticket_accounts}
    overlap = batched_ids & no_ticket_ids
    assert not overlap, f"Accounts present in both batches and no-ticket list: {overlap}"

    all_covered = batched_ids | no_ticket_ids
    all_accounts = set(accounts["account_id"])
    assert all_covered == all_accounts, (
        f"Coverage mismatch: {len(all_accounts - all_covered)} accounts missing entirely, "
        f"{len(all_covered - all_accounts)} unknown account_ids present"
    )

    # 2. Schema check: every ticket dict has exactly the allowed fields
    for batch in batches:
        for record in batch:
            assert set(record.keys()) == {"account_id", "tickets"}, (
                f"{record.get('account_id')}: unexpected top-level keys {set(record.keys())}"
            )
            for ticket in record["tickets"]:
                assert set(ticket.keys()) == set(TICKET_FIELDS), (
                    f"{record['account_id']}: unexpected ticket keys {set(ticket.keys())}"
                )

    # 3. Blinding check: none of the forbidden fields appear anywhere, and no
    #    numeric ARR-shaped values sneak in under an unexpected key name.
    batches_json = json.dumps(batches)
    for forbidden_key in FORBIDDEN_FIELDS:
        assert f'"{forbidden_key}"' not in batches_json, (
            f"Blinding violation: forbidden field '{forbidden_key}' found in batch output"
        )

    print(f"  Validation passed: {len(batched_ids)} accounts batched, "
          f"{len(no_ticket_ids)} no-ticket accounts, {len(all_accounts)} total — "
          "partition complete, blinding contract intact.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    try:
        AGENT_DIR.mkdir(parents=True, exist_ok=True)
        BATCH_DIR.mkdir(parents=True, exist_ok=True)

        accounts, tickets = load_source_tables()
        accounts = compute_reading_window(accounts)
        records, no_ticket_accounts = build_account_records(accounts, tickets)
        batches = pack_batches(records, ACCOUNTS_PER_BATCH)

        validate_batches(batches, no_ticket_accounts, accounts)

        print(f"\nWriting {len(batches)} batch files to {BATCH_DIR}...")
        for batch_number, batch_records in enumerate(batches, start=1):
            batch_path = BATCH_DIR / f"batch_{batch_number:02d}.json"
            with open(batch_path, "w", encoding="utf-8") as batch_file:
                json.dump(batch_records, batch_file, indent=1, ensure_ascii=False)
            n_tickets = sum(len(rec["tickets"]) for rec in batch_records)
            print(f"  {batch_path.name}: {len(batch_records)} accounts, {n_tickets} tickets")

        no_ticket_df = pd.DataFrame(no_ticket_accounts, columns=["account_id", "reason"])
        no_ticket_df.to_csv(NO_TICKET_ACCOUNTS_PATH, index=False)

        n_batched = sum(len(batch) for batch in batches)
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"  Total accounts             : {len(accounts)}")
        print(f"  Accounts with tickets in window (batched): {n_batched}")
        print(f"  Accounts with zero tickets in window      : {len(no_ticket_accounts)}")
        print(f"  Batch files written        : {len(batches)}  ({BATCH_DIR})")
        print(f"  No-ticket accounts written : {NO_TICKET_ACCOUNTS_PATH}")
        print("=" * 60)

    except FileNotFoundError as e:
        print(f"ERROR: required input file not found — {e}")
        sys.exit(1)
    except AssertionError as e:
        print(f"VALIDATION FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: unexpected failure building assessment batches — {e}")
        raise


if __name__ == "__main__":
    main()
