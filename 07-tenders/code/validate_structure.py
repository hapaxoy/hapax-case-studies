"""Phase 2 coherence validator for Project 7 (Tenders).

Independently re-reads every file generate_structure.py wrote (never trusts
its in-memory state) and checks every coherence rule implied by the corpus
design:

  1. Key completeness -- per-tender CSVs + combined answer_key.csv agree,
     requirement numbering is a gapless 1..N sequence per tender, tender
     sizes fall inside their size-class band.
  2. Trap placement matches config.TRAP_TABLE exactly (counts, and the
     eligibility_fail trap lands only on the two designed no-bid tenders).
  3. Facts-library eligibility consistency -- every eligibility requirement
     is RE-CHECKED against the written company_facts.yaml (not against
     generate_structure.py's in-memory facts dict), and the tender-level
     bid/no-bid call implied by those checks matches config.NO_BID_TENDERS.
  4. Assignment matrix validity -- 16 tenders x 4 distinct personas, each
     persona assigned 4 or 5 times overall, matching
     config.PERSONAS_WITH_FIVE, total 64.
  5. Attempt-brief engagement lists reference only real requirement ids for
     their tender, with no duplicate or missing requirement.
  6. No persona duplicated on a single tender (belt-and-braces on top of
     the filename-uniqueness already implied by one file per tender/persona
     pair).
  7. Fabrication seeding (`code/seed_fabrication.py`'s two added fields) --
     presence and schema of `checks_facts_library` / `fabrication_events`,
     the checks_facts_library=true-implies-zero-events consistency rule,
     and the no-true-fact guard: every event is RE-CHECKED against the
     written `company_facts.yaml` (not against any in-memory dict) via
     `seed_fabrication.validate_event()`.

Exits 1 on any failure, printing every failure found (not just the first).
Exits 0 only if every rule passes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import yaml

import config
import seed_fabrication

FAILURES: list[str] = []


def fail(message: str) -> None:
    FAILURES.append(message)
    print(f"[validate_structure] FAIL: {message}", flush=True)


def ok(message: str) -> None:
    print(f"[validate_structure] OK: {message}", flush=True)


# ---------------------------------------------------------------------------
# Rule 1: key completeness
# ---------------------------------------------------------------------------

def check_key_completeness() -> pd.DataFrame | None:
    combined_path = config.ANSWER_KEY_DIR / "answer_key.csv"
    if not combined_path.exists():
        fail(f"missing {combined_path}")
        return None
    combined = pd.read_csv(combined_path, keep_default_na=False)

    for tender in config.TENDERS:
        tid = tender["id"]
        per_tender_path = config.ANSWER_KEY_DIR / f"requirements_{tid[1:]}.csv"
        if not per_tender_path.exists():
            fail(f"missing {per_tender_path}")
            continue
        per_tender = pd.read_csv(per_tender_path, keep_default_na=False)
        combined_slice = combined[combined["tender_id"] == tid]
        if len(per_tender) != len(combined_slice):
            fail(f"{tid}: requirements_{tid[1:]}.csv has {len(per_tender)} rows "
                 f"but answer_key.csv has {len(combined_slice)} rows for this tender")
            continue

        lo, hi = config.SIZE_PROFILES[tender["size_class"]]["n_range"]
        n = len(per_tender)
        if not (lo <= n <= hi):
            fail(f"{tid} ({tender['size_class']}): {n} requirements outside "
                 f"the designed band [{lo}, {hi}]")

        numbers = sorted(per_tender["req_number"].tolist())
        if numbers != list(range(1, n + 1)):
            fail(f"{tid}: req_number is not a gapless 1..{n} sequence: {numbers}")

        if per_tender["req_id"].duplicated().any():
            fail(f"{tid}: duplicate req_id values in requirements_{tid[1:]}.csv")

    if combined["req_id"].duplicated().any():
        fail("answer_key.csv: duplicate req_id values across the whole corpus")

    n_simple = sum(1 for t in config.TENDERS if t["size_class"] == "simple")
    n_medium = sum(1 for t in config.TENDERS if t["size_class"] == "medium")
    n_gnarly = sum(1 for t in config.TENDERS if t["size_class"] == "gnarly")
    if (n_simple, n_medium, n_gnarly) != (4, 8, 4):
        fail(f"tender size-class mix is {(n_simple, n_medium, n_gnarly)}, expected (4, 8, 4)")

    if not FAILURES:
        ok(f"key completeness -- {len(combined)} requirement rows, 16 tenders, "
           f"sizes within band, gapless numbering, no duplicate req_ids")
    return combined


# ---------------------------------------------------------------------------
# Rule 2: trap placement matches config exactly
# ---------------------------------------------------------------------------

def check_trap_placement(combined: pd.DataFrame) -> None:
    # A trap TYPE is counted once per instance, not once per row: a
    # contradiction trap plants two linked rows (body + annex) sharing one
    # trap_group_id, so it counts as one instance; every other trap type is
    # single-row and counts row-for-row.
    trapped = combined[combined["trap_code"] != ""]
    trap_counts: dict[str, int] = {}
    for code, group in trapped.groupby("trap_code"):
        if code == "contradiction":
            trap_counts[code] = group["trap_group_id"].nunique()
        else:
            trap_counts[code] = len(group)
    clean_tenders = combined.groupby("tender_id")["trap_code"].apply(
        lambda s: not any(s.astype(str).str.len() > 0))
    trap_counts["clean"] = int(clean_tenders.sum())

    for row in config.TRAP_TABLE:
        found = trap_counts.get(row["code"], 0)
        if found != row["count"]:
            fail(f"trap '{row['code']}': answer_key.csv has {found}, "
                 f"config.TRAP_TABLE says {row['count']}")

    elig_fail_tenders = sorted(
        combined.loc[combined["trap_code"] == "eligibility_fail", "tender_id"].unique().tolist())
    if elig_fail_tenders != sorted(config.NO_BID_TENDERS):
        fail(f"eligibility_fail trap sits on {elig_fail_tenders}, "
             f"expected {sorted(config.NO_BID_TENDERS)}")

    if not FAILURES:
        ok("trap placement matches config.TRAP_TABLE exactly "
           f"({dict(sorted(trap_counts.items()))})")


# ---------------------------------------------------------------------------
# Rule 3: facts-library eligibility consistency (re-derived from disk)
# ---------------------------------------------------------------------------

def check_eligibility_consistency(combined: pd.DataFrame) -> None:
    facts_path = config.FACTS_DIR / "company_facts.yaml"
    if not facts_path.exists():
        fail(f"missing {facts_path}")
        return
    with open(facts_path, "r", encoding="utf-8") as fh:
        facts = yaml.safe_load(fh)

    elig_rows = combined[combined["type"] == "eligibility"]
    failing_tenders = set()
    for _, row in elig_rows.iterrows():
        check_type = row["eligibility_check_type"]
        check_param = str(row["eligibility_check_param"])
        stored = str(row["eligibility_pass"]).strip().lower() in ("true", "1")
        checker = config.ELIGIBILITY_CHECKS.get(check_type)
        if checker is None:
            fail(f"{row['req_id']}: unknown eligibility check_type '{check_type}'")
            continue
        recomputed = checker(facts, check_param)
        if recomputed != stored:
            fail(f"{row['req_id']}: answer_key says eligibility_pass={stored}, "
                 f"but recomputing against company_facts.yaml gives {recomputed}")
        if not recomputed:
            failing_tenders.add(row["tender_id"])

    if sorted(failing_tenders) != sorted(config.NO_BID_TENDERS):
        fail(f"tenders failing eligibility on disk are {sorted(failing_tenders)}, "
             f"expected exactly {sorted(config.NO_BID_TENDERS)}")

    # bid/no-bid call column sanity
    for tid, group in combined.groupby("tender_id"):
        calls = group["tender_bid_no_bid_call"].unique().tolist()
        if len(calls) != 1:
            fail(f"{tid}: inconsistent tender_bid_no_bid_call values {calls}")
            continue
        expected = "NO-BID" if tid in config.NO_BID_TENDERS else "BID"
        if calls[0] != expected:
            fail(f"{tid}: tender_bid_no_bid_call={calls[0]!r}, expected {expected!r}")

    if not FAILURES:
        ok(f"facts-library eligibility consistency -- recomputed against "
           f"company_facts.yaml on disk, genuine failures only on "
           f"{sorted(failing_tenders)}")


# ---------------------------------------------------------------------------
# Rule 4/6: assignment matrix validity, no persona twice on one tender
# ---------------------------------------------------------------------------

def check_assignment_matrix() -> dict[str, list[str]] | None:
    path = config.DATA_DIR / "assignment_matrix.json"
    if not path.exists():
        fail(f"missing {path}")
        return None
    with open(path, "r", encoding="utf-8") as fh:
        assignment = json.load(fh)

    if sorted(assignment.keys()) != sorted(t["id"] for t in config.TENDERS):
        fail(f"assignment_matrix.json does not cover exactly the 16 tender ids")

    per_persona_count: dict[str, int] = {p["id"]: 0 for p in config.PERSONAS}
    for tid, pids in assignment.items():
        if len(pids) != 4:
            fail(f"{tid}: assignment matrix lists {len(pids)} personas, expected 4")
        if len(set(pids)) != len(pids):
            fail(f"{tid}: a persona is assigned to this tender more than once ({pids})")
        for pid in pids:
            if pid not in per_persona_count:
                fail(f"{tid}: unknown persona id '{pid}' in assignment matrix")
                continue
            per_persona_count[pid] += 1

    total = sum(per_persona_count.values())
    if total != 64:
        fail(f"assignment matrix totals {total} attempts, expected 64")

    for pid, count in per_persona_count.items():
        expected = 5 if pid in config.PERSONAS_WITH_FIVE else 4
        if count != expected:
            fail(f"{pid}: assigned {count} tenders, expected {expected} "
                 f"(config.PERSONAS_WITH_FIVE)")

    if not FAILURES:
        ok(f"assignment matrix -- 16 tenders x 4 distinct personas, "
           f"64 total attempts, split 8x5 + 6x4 across personas as designed")
    return assignment


# ---------------------------------------------------------------------------
# Rule 5: attempt-brief engagement lists reference only real requirement ids
# ---------------------------------------------------------------------------

def check_attempt_briefs(assignment: dict[str, list[str]] | None) -> None:
    n_briefs = 0
    for tender in config.TENDERS:
        tid = tender["id"]
        req_path = config.ANSWER_KEY_DIR / f"requirements_{tid[1:]}.csv"
        if not req_path.exists():
            continue  # already reported by check_key_completeness
        real_ids = set(pd.read_csv(req_path, keep_default_na=False)["req_id"])

        expected_personas = assignment.get(tid, []) if assignment else []
        for pid in expected_personas:
            path = config.ATTEMPT_BRIEFS_DIR / f"attempt_{tid[1:]}_{pid[1:]}.json"
            if not path.exists():
                fail(f"missing attempt brief {path.name} implied by the assignment matrix")
                continue
            with open(path, "r", encoding="utf-8") as fh:
                attempt = json.load(fh)
            n_briefs += 1

            engaged_ids = [row["req_id"] for row in attempt["engagement"]]
            if set(engaged_ids) != real_ids:
                missing = real_ids - set(engaged_ids)
                extra = set(engaged_ids) - real_ids
                fail(f"{path.name}: engagement list mismatch vs {tid}'s real "
                     f"requirement ids (missing={missing or None}, extra={extra or None})")
            if len(engaged_ids) != len(set(engaged_ids)):
                fail(f"{path.name}: duplicate req_id entries in the engagement list")

            recomputed_engaged = sum(1 for row in attempt["engagement"]
                                     if row["engagement"] == "engaged")
            if recomputed_engaged != attempt["engaged_count"]:
                fail(f"{path.name}: engaged_count={attempt['engaged_count']} does not "
                     f"match {recomputed_engaged} rows marked engaged")

    if not FAILURES:
        ok(f"attempt briefs -- {n_briefs} briefs checked, every engagement list "
           f"references exactly its tender's real requirement ids, no duplicates")


# ---------------------------------------------------------------------------
# Rule 7: fabrication seeding (checks_facts_library / fabrication_events)
# ---------------------------------------------------------------------------

def check_fabrication_seeding(assignment: dict[str, list[str]] | None) -> None:
    facts_path = config.FACTS_DIR / "company_facts.yaml"
    if not facts_path.exists():
        fail(f"missing {facts_path}")
        return
    with open(facts_path, "r", encoding="utf-8") as fh:
        facts = yaml.safe_load(fh)

    n_checked = 0
    n_checking = 0
    n_with_events = 0
    event_type_counts: dict[str, int] = {}

    for tender in config.TENDERS:
        tid = tender["id"]
        expected_personas = assignment.get(tid, []) if assignment else []
        for pid in expected_personas:
            path = config.ATTEMPT_BRIEFS_DIR / f"attempt_{tid[1:]}_{pid[1:]}.json"
            if not path.exists():
                continue  # already reported by check_attempt_briefs
            with open(path, "r", encoding="utf-8") as fh:
                attempt = json.load(fh)
            n_checked += 1

            if "checks_facts_library" not in attempt:
                fail(f"{path.name}: missing 'checks_facts_library' field")
                continue
            if "fabrication_events" not in attempt:
                fail(f"{path.name}: missing 'fabrication_events' field")
                continue

            checks = attempt["checks_facts_library"]
            events = attempt["fabrication_events"]
            if not isinstance(checks, bool):
                fail(f"{path.name}: checks_facts_library={checks!r} is not a bool")
                continue
            if not isinstance(events, list):
                fail(f"{path.name}: fabrication_events={events!r} is not a list")
                continue

            if checks:
                n_checking += 1
                if events:
                    fail(f"{path.name}: checks_facts_library=true but "
                         f"fabrication_events is non-empty ({len(events)} "
                         f"events) -- an attempt that checks the facts "
                         f"library may not carry an uncaught fabrication")
                continue

            if events:
                n_with_events += 1

            for event in events:
                if not isinstance(event, dict):
                    fail(f"{path.name}: a fabrication_events entry is not "
                         f"an object: {event!r}")
                    continue
                for required_key in ("type", "target_area", "instruction"):
                    if required_key not in event or not event[required_key]:
                        fail(f"{path.name}: fabrication event missing or "
                             f"empty required field '{required_key}': {event}")
                if event.get("type") not in seed_fabrication.ALLOWED_EVENT_TYPES:
                    fail(f"{path.name}: fabrication event has unknown "
                         f"type {event.get('type')!r}, expected one of "
                         f"{seed_fabrication.ALLOWED_EVENT_TYPES}")
                    continue
                event_type_counts[event["type"]] = event_type_counts.get(event["type"], 0) + 1

                # The no-true-fact guard, re-derived from the facts library
                # on disk (never trusting anything generate_structure.py or
                # seed_fabrication.py held in memory).
                errors = seed_fabrication.validate_event(event, facts)
                for err in errors:
                    fail(f"{path.name}: fabrication event coincides with a "
                         f"true fact -- {err}")

    if n_checked == 0:
        fail("no attempt briefs were checked for fabrication seeding "
             "(assignment matrix missing or empty)")

    if not FAILURES:
        pct = round(100 * n_with_events / n_checked, 1) if n_checked else 0.0
        ok(f"fabrication seeding -- {n_checked} attempts checked, "
           f"{n_checking} checks_facts_library=true (zero events each, "
           f"verified), {n_with_events} carry >=1 fabrication event "
           f"({pct}%), no event coincides with a true fact "
           f"(types: {event_type_counts})")


# ---------------------------------------------------------------------------
# Extra: tender briefs exist and their trap_placements agree with the key
# ---------------------------------------------------------------------------

def check_tender_briefs(combined: pd.DataFrame) -> None:
    for tender in config.TENDERS:
        tid = tender["id"]
        path = config.TENDER_BRIEFS_DIR / f"brief_{tid[1:]}.json"
        if not path.exists():
            fail(f"missing {path}")
            continue
        with open(path, "r", encoding="utf-8") as fh:
            brief = json.load(fh)
        key_traps = combined[(combined["tender_id"] == tid) & (combined["trap_code"] != "")]
        brief_trap_ids = {p["req_id"] for p in brief["trap_placements"]}
        key_trap_ids = set(key_traps["req_id"])
        if brief_trap_ids != key_trap_ids:
            fail(f"{path.name}: trap_placements do not match answer_key.csv for {tid}")
        expected_call = "NO-BID" if tid in config.NO_BID_TENDERS else "BID"
        if brief["correct_bid_no_bid_call"] != expected_call:
            fail(f"{path.name}: correct_bid_no_bid_call={brief['correct_bid_no_bid_call']!r}, "
                 f"expected {expected_call!r}")

    if not FAILURES:
        ok("tender briefs -- 16 present, trap placements and bid/no-bid calls "
           "match the answer key")


def main() -> int:
    print("[validate_structure] Project 7 Tenders -- Phase 2 coherence checks", flush=True)
    combined = check_key_completeness()
    if combined is not None:
        check_trap_placement(combined)
        check_eligibility_consistency(combined)
        check_tender_briefs(combined)
    assignment = check_assignment_matrix()
    check_attempt_briefs(assignment)
    check_fabrication_seeding(assignment)

    print("", flush=True)
    if FAILURES:
        print(f"[validate_structure] {len(FAILURES)} FAILURE(S) -- dataset is not valid.",
              file=sys.stderr)
        return 1
    print("[validate_structure] ALL CHECKS PASSED.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # graceful, informative failure
        print(f"[validate_structure] CRASHED: {exc}", file=sys.stderr)
        raise
