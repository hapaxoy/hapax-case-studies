"""
collect_assessments.py — Collects, validates and consolidates the LLM
assessor agents' outputs into the text-layer scoring table (the agent
layer).

Runs AFTER the assessor agents have read data/agent/assessment_batches/
batch_NN.json and written their structured assessments to
data/agent/assessments_raw/batch_NN.json (one JSON array per batch, one
object per account in that batch).

Expected per-account assessment schema:
    account_id                (str)
    frustration_trajectory    "improving" | "stable" | "deteriorating"
    unresolved_issue_count    int >= 0
    competitor_mentions       [{competitor, quote, seriousness: "casual"|"serious"}, ...]
    escalation_pattern        bool
    narrative                 non-empty str
    text_risk_score           float in [0, 1]

A dataset that fails schema validation is a bug, not a judgment call — this
script reports every bad record it finds and exits non-zero rather than
silently coercing or dropping data.

Usage:
    python collect_assessments.py            # requires all expected batches present
    python collect_assessments.py --partial  # proceed with whatever batches exist

Output:
    data/agent/text_scores.csv   — all 500 accounts (assessed + no-ticket defaults)
    data/agent/narratives.json   — account_id -> full assessment object
    plus an evaluation section printed to stdout (joins answer_key.csv for
    evaluation purposes ONLY — the join never touches text_scores.csv itself)
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Resolve paths — output files are created fresh, never touch source data
# ---------------------------------------------------------------------------

SCRIPT_DIR    = Path(__file__).resolve().parent
PROJECT_ROOT  = SCRIPT_DIR.parent
DATA_DIR      = PROJECT_ROOT / "data"
AGENT_DIR     = DATA_DIR / "agent"

ASSESSMENT_BATCHES_DIR = AGENT_DIR / "assessment_batches"   # input: what was sent out
ASSESSMENTS_RAW_DIR     = AGENT_DIR / "assessments_raw"      # input: agents' written output
NO_TICKET_ACCOUNTS_PATH = AGENT_DIR / "no_ticket_accounts.csv"
ANSWER_KEY_PATH          = DATA_DIR / "answer_key.csv"       # evaluation only, never modelling

TEXT_SCORES_PATH = AGENT_DIR / "text_scores.csv"
NARRATIVES_PATH  = AGENT_DIR / "narratives.json"

# Safety: confirm every output path is outside/different from every input path
_INPUT_PATHS = [ASSESSMENT_BATCHES_DIR, ASSESSMENTS_RAW_DIR, NO_TICKET_ACCOUNTS_PATH, ANSWER_KEY_PATH]
for out_path in (TEXT_SCORES_PATH, NARRATIVES_PATH):
    for in_path in _INPUT_PATHS:
        assert out_path.resolve() != in_path.resolve(), (
            f"Refusing to run: output path {out_path} collides with input path {in_path}"
        )

# ---------------------------------------------------------------------------
# Config block
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {
    "account_id", "frustration_trajectory", "unresolved_issue_count",
    "competitor_mentions", "escalation_pattern", "narrative", "text_risk_score",
}
VALID_TRAJECTORIES = {"improving", "stable", "deteriorating"}
VALID_SERIOUSNESS  = {"casual", "serious"}

# No-ticket accounts get a neutral default rather than a missing row
NO_TICKET_DEFAULT = {
    "text_risk_score": 0.1,
    "frustration_trajectory": "stable",
    "narrative": "No support contact in window.",
    "unresolved_issue_count": 0,
    "competitor_mentions": [],
    "escalation_pattern": False,
}


# ---------------------------------------------------------------------------
# Step 1: discover expected coverage from assessment_batches (what was sent out)
# ---------------------------------------------------------------------------

def load_expected_batches() -> dict[int, list[str]]:
    """Returns {batch_number: [account_id, ...]} for every assessment_batches
    file — this is the ground truth of which accounts were sent to the
    assessor agents and therefore must come back covered."""
    if not ASSESSMENT_BATCHES_DIR.exists():
        print(f"ERROR: {ASSESSMENT_BATCHES_DIR} not found — run make_assessment_batches.py first.")
        sys.exit(1)

    expected: dict[int, list[str]] = {}
    for path in sorted(ASSESSMENT_BATCHES_DIR.glob("batch_*.json")):
        batch_num = _parse_batch_number(path)
        if batch_num is None:
            print(f"  WARNING: unexpected filename {path.name} in assessment_batches, skipping.")
            continue
        with open(path, encoding="utf-8") as f:
            batch = json.load(f)
        expected[batch_num] = [rec["account_id"] for rec in batch]
    return expected


def _parse_batch_number(path: Path) -> int | None:
    """Extracts the integer batch number from a 'batch_NN.json' filename."""
    stem = path.stem  # "batch_07"
    parts = stem.split("_")
    if len(parts) != 2:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Step 2: load whatever assessments_raw batches are present
# ---------------------------------------------------------------------------

def load_raw_assessment_batches() -> dict[int, list[dict]]:
    """Returns {batch_number: [assessment_dict, ...]} for every present
    assessments_raw batch file."""
    if not ASSESSMENTS_RAW_DIR.exists():
        return {}

    raw: dict[int, list[dict]] = {}
    for path in sorted(ASSESSMENTS_RAW_DIR.glob("batch_*.json")):
        batch_num = _parse_batch_number(path)
        if batch_num is None:
            print(f"  WARNING: unexpected filename {path.name} in assessments_raw, skipping.")
            continue
        try:
            with open(path, encoding="utf-8") as f:
                batch = json.load(f)
        except json.JSONDecodeError as e:
            print(f"  ERROR parsing {path.name}: {e}")
            sys.exit(1)
        if not isinstance(batch, list):
            print(f"  ERROR: {path.name} does not contain a JSON array at the top level.")
            sys.exit(1)
        raw[batch_num] = batch
    return raw


# ---------------------------------------------------------------------------
# Step 3: schema validation — a bad record is a bug, not a judgment call
# ---------------------------------------------------------------------------

def validate_record(record: dict, batch_num: int, errors: list[str]) -> None:
    """Appends a clear, specific error string to `errors` for every problem
    found in a single assessment record. Does not raise — callers collect
    all errors across all records before deciding whether to exit."""
    label = f"batch_{batch_num:02d} / {record.get('account_id', '<missing account_id>')}"

    if not isinstance(record, dict):
        errors.append(f"{label}: record is not a JSON object")
        return

    missing_fields = REQUIRED_FIELDS - record.keys()
    if missing_fields:
        errors.append(f"{label}: missing required field(s) {sorted(missing_fields)}")
        return  # further checks would just be noise once fields are missing

    if not isinstance(record["account_id"], str) or not record["account_id"].strip():
        errors.append(f"{label}: account_id must be a non-empty string")

    if record["frustration_trajectory"] not in VALID_TRAJECTORIES:
        errors.append(
            f"{label}: frustration_trajectory={record['frustration_trajectory']!r} "
            f"not in {sorted(VALID_TRAJECTORIES)}"
        )

    unresolved = record["unresolved_issue_count"]
    if not isinstance(unresolved, int) or isinstance(unresolved, bool) or unresolved < 0:
        errors.append(f"{label}: unresolved_issue_count={unresolved!r} must be a non-negative int")

    mentions = record["competitor_mentions"]
    if not isinstance(mentions, list):
        errors.append(f"{label}: competitor_mentions must be a list, got {type(mentions).__name__}")
    else:
        for j, mention in enumerate(mentions):
            if not isinstance(mention, dict):
                errors.append(f"{label}: competitor_mentions[{j}] is not an object")
                continue
            mention_missing = {"competitor", "quote", "seriousness"} - mention.keys()
            if mention_missing:
                errors.append(f"{label}: competitor_mentions[{j}] missing field(s) {sorted(mention_missing)}")
                continue
            if mention["seriousness"] not in VALID_SERIOUSNESS:
                errors.append(
                    f"{label}: competitor_mentions[{j}].seriousness={mention['seriousness']!r} "
                    f"not in {sorted(VALID_SERIOUSNESS)}"
                )
            if not isinstance(mention["competitor"], str) or not mention["competitor"].strip():
                errors.append(f"{label}: competitor_mentions[{j}].competitor must be a non-empty string")
            if not isinstance(mention["quote"], str) or not mention["quote"].strip():
                errors.append(f"{label}: competitor_mentions[{j}].quote must be a non-empty string")

    if not isinstance(record["escalation_pattern"], bool):
        errors.append(f"{label}: escalation_pattern must be a bool, got {type(record['escalation_pattern']).__name__}")

    if not isinstance(record["narrative"], str) or not record["narrative"].strip():
        errors.append(f"{label}: narrative must be a non-empty string")

    score = record["text_risk_score"]
    if not isinstance(score, (int, float)) or isinstance(score, bool) or not (0.0 <= float(score) <= 1.0):
        errors.append(f"{label}: text_risk_score={score!r} must be a float in [0, 1]")


def validate_all_records(raw_batches: dict[int, list[dict]]) -> list[str]:
    """Runs validate_record over every record in every present raw batch and
    also checks for duplicate account_ids across the whole collected set."""
    errors: list[str] = []
    seen_account_ids: dict[str, int] = {}   # account_id -> batch_num first seen in

    for batch_num, records in sorted(raw_batches.items()):
        for record in records:
            validate_record(record, batch_num, errors)
            account_id = record.get("account_id") if isinstance(record, dict) else None
            if account_id:
                if account_id in seen_account_ids:
                    errors.append(
                        f"batch_{batch_num:02d} / {account_id}: duplicate assessment "
                        f"(already seen in batch_{seen_account_ids[account_id]:02d})"
                    )
                else:
                    seen_account_ids[account_id] = batch_num

    return errors


# ---------------------------------------------------------------------------
# Step 4: coverage check — every batched account must come back assessed
# ---------------------------------------------------------------------------

def check_coverage(expected_batches: dict[int, list[str]], raw_batches: dict[int, list[dict]], partial: bool) -> None:
    """Verifies every account sent out in assessment_batches has a matching
    record in assessments_raw. Missing whole batches are tolerated under
    --partial (agents haven't finished yet); missing individual accounts
    WITHIN a present batch are always an error (a bug in that agent's run,
    not a work-in-progress state)."""
    expected_batch_nums = set(expected_batches.keys())
    present_batch_nums  = set(raw_batches.keys())
    missing_batch_nums  = sorted(expected_batch_nums - present_batch_nums)

    print(f"  Expected batches: {len(expected_batch_nums)} | present: {len(present_batch_nums)}")
    if missing_batch_nums:
        print(f"  Batches not yet collected: {[f'batch_{n:02d}' for n in missing_batch_nums]}")
        if not partial:
            print("\n  Run with --partial to proceed with the batches that exist.")
            sys.exit(1)
        print("  --partial flag set: continuing with available batches.")
    else:
        print("  All expected batches are present.")

    # Within PRESENT batches, every expected account_id must have a record —
    # this always holds regardless of --partial, since a present batch that
    # is missing an account is a defect in that agent's output, not a
    # not-yet-run batch.
    incomplete_errors = []
    for batch_num in sorted(present_batch_nums & expected_batch_nums):
        expected_ids = set(expected_batches[batch_num])
        got_ids = {rec.get("account_id") for rec in raw_batches[batch_num] if isinstance(rec, dict)}
        missing_ids = expected_ids - got_ids
        if missing_ids:
            incomplete_errors.append(
                f"batch_{batch_num:02d}: {len(missing_ids)} account(s) sent for assessment but "
                f"never returned: {sorted(missing_ids)}"
            )
        extra_ids = got_ids - expected_ids
        if extra_ids:
            print(f"  WARNING: batch_{batch_num:02d} contains {len(extra_ids)} unexpected "
                  f"account_id(s) not in the batch it was sent: {sorted(extra_ids)}")

    if incomplete_errors:
        print("\nCOVERAGE FAILED — present batches missing accounts they were sent:")
        for err in incomplete_errors:
            print(f"  - {err}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Step 5: merge assessed accounts with no-ticket defaults
# ---------------------------------------------------------------------------

def load_no_ticket_accounts() -> list[str]:
    if not NO_TICKET_ACCOUNTS_PATH.exists():
        print(f"  WARNING: {NO_TICKET_ACCOUNTS_PATH} not found — assuming zero no-ticket accounts.")
        return []
    df = pd.read_csv(NO_TICKET_ACCOUNTS_PATH)
    return df["account_id"].tolist()


def build_consolidated_records(raw_batches: dict[int, list[dict]], no_ticket_ids: list[str]) -> dict[str, dict]:
    """Builds {account_id: assessment_dict} for every assessed account plus a
    neutral default record for every no-ticket account."""
    consolidated: dict[str, dict] = {}
    for records in raw_batches.values():
        for record in records:
            if isinstance(record, dict) and "account_id" in record:
                consolidated[record["account_id"]] = record

    overlap = set(no_ticket_ids) & consolidated.keys()
    assert not overlap, f"Accounts appear both as assessed and no-ticket: {overlap}"

    for account_id in no_ticket_ids:
        consolidated[account_id] = {"account_id": account_id, **NO_TICKET_DEFAULT}

    return consolidated


# ---------------------------------------------------------------------------
# Step 6: write outputs
# ---------------------------------------------------------------------------

def write_outputs(consolidated: dict[str, dict]) -> pd.DataFrame:
    rows = []
    for account_id, record in consolidated.items():
        mentions = record["competitor_mentions"]
        n_serious = sum(1 for m in mentions if isinstance(m, dict) and m.get("seriousness") == "serious")
        rows.append({
            "account_id": account_id,
            "text_risk_score": float(record["text_risk_score"]),
            "frustration_trajectory": record["frustration_trajectory"],
            "unresolved_issue_count": int(record["unresolved_issue_count"]),
            "n_competitor_mentions": len(mentions),
            "n_serious_competitor_mentions": n_serious,
            "escalation_pattern": bool(record["escalation_pattern"]),
        })

    text_scores_df = pd.DataFrame(rows).sort_values("account_id").reset_index(drop=True)
    text_scores_df.to_csv(TEXT_SCORES_PATH, index=False)
    print(f"  Wrote {len(text_scores_df)} rows to {TEXT_SCORES_PATH}")

    with open(NARRATIVES_PATH, "w", encoding="utf-8") as f:
        json.dump(consolidated, f, indent=1, ensure_ascii=False)
    print(f"  Wrote {len(consolidated)} narratives to {NARRATIVES_PATH}")

    return text_scores_df


# ---------------------------------------------------------------------------
# Step 7: evaluation against the answer key (evaluation only — never feeds
# back into text_scores.csv or any modelling path)
# ---------------------------------------------------------------------------

def run_evaluation(text_scores_df: pd.DataFrame) -> None:
    if not ANSWER_KEY_PATH.exists():
        print(f"  NOTE: {ANSWER_KEY_PATH} not found — skipping evaluation section.")
        return

    answer_key = pd.read_csv(ANSWER_KEY_PATH)
    joined = text_scores_df.merge(answer_key[["account_id", "archetype"]], on="account_id", how="left")

    unmatched = joined["archetype"].isna().sum()
    if unmatched:
        print(f"  WARNING: {unmatched} accounts in text_scores.csv have no matching answer_key row.")

    joined["is_deteriorating"] = joined["frustration_trajectory"] == "deteriorating"

    summary = (
        joined.groupby("archetype")
        .agg(
            n_accounts=("account_id", "count"),
            mean_text_risk_score=("text_risk_score", "mean"),
            share_deteriorating=("is_deteriorating", "mean"),
        )
        .sort_index()
    )

    print("\n" + "=" * 60)
    print("EVALUATION AGAINST answer_key.csv (evaluation only — not used in modelling)")
    print("=" * 60)
    print("  Expected pattern: A4/A3 high mean_text_risk_score; A7 LOW despite angry")
    print("  tickets (resolution speed matters, not tone alone); A5/A1 low.\n")
    print(summary.round(3).to_string())
    print("=" * 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(partial: bool) -> None:
    print("=" * 60)
    print("collect_assessments.py — collecting agent text-risk assessments")
    print("=" * 60)

    print("\n[1/6] Loading expected coverage from assessment_batches...")
    expected_batches = load_expected_batches()
    n_expected_accounts = sum(len(ids) for ids in expected_batches.values())
    print(f"  {len(expected_batches)} batches sent out, {n_expected_accounts} accounts expected.")

    print("\n[2/6] Loading assessments_raw batch files...")
    raw_batches = load_raw_assessment_batches()
    if not raw_batches:
        print(f"  ERROR: no batch files found in {ASSESSMENTS_RAW_DIR}.")
        print("  Assessor agents need to write their output there first.")
        sys.exit(1)
    for batch_num, records in sorted(raw_batches.items()):
        print(f"  batch_{batch_num:02d}.json -> {len(records)} assessments")

    print("\n[3/6] Validating assessment schema...")
    errors = validate_all_records(raw_batches)
    if errors:
        print(f"\nSCHEMA VALIDATION FAILED — {len(errors)} bad record(s):")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    print(f"  All {sum(len(r) for r in raw_batches.values())} records passed schema validation.")

    print("\n[4/6] Checking coverage against assessment_batches...")
    check_coverage(expected_batches, raw_batches, partial)

    print("\n[5/6] Merging with no-ticket accounts...")
    no_ticket_ids = load_no_ticket_accounts()
    print(f"  {len(no_ticket_ids)} no-ticket accounts will get the neutral default score.")
    consolidated = build_consolidated_records(raw_batches, no_ticket_ids)
    print(f"  {len(consolidated)} accounts consolidated in total.")

    print("\n[6/6] Writing text_scores.csv and narratives.json...")
    text_scores_df = write_outputs(consolidated)

    run_evaluation(text_scores_df)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Accounts assessed by agents : {len(consolidated) - len(no_ticket_ids)}")
    print(f"  Accounts with default score : {len(no_ticket_ids)}")
    print(f"  Total accounts written      : {len(consolidated)}")
    if len(expected_batches) != len(raw_batches):
        missing = sorted(set(expected_batches) - set(raw_batches))
        print(f"  REMINDER: batches still missing: {[f'batch_{n:02d}' for n in missing]}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Collect and validate LLM assessor agent outputs into text_scores.csv."
    )
    parser.add_argument(
        "--partial",
        action="store_true",
        help="Proceed even if some assessment batches have not been collected yet.",
    )
    args = parser.parse_args()
    main(partial=args.partial)
