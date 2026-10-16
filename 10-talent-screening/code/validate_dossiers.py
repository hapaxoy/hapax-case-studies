"""Structural validation for assembled dossiers (Project 10, Phase 3).

Checks `data/dossiers/dossier_CNNN.json` for structural soundness: every
candidate present, every requirement addressed, every status within the
fixed vocabulary, and -- the check that matters most for the design's
standing constraint ("the system assists and never decides") -- NO ranking,
verdict, or recommendation vocabulary anywhere in any dossier text field.
Also reports the citation-failure rate computed by assemble_dossiers.py.

Exits 1 on any structural failure, per the portfolio's rule that a dataset
failing validation is a bug, not a judgment call.

This script never reads data/answer_key.csv or data/answer_key_candidates.csv
-- it checks the dossier's internal structure and vocabulary hygiene, not
whether the dossier is *correct* against ground truth (that is the marking
script's job, Phase 5, the only script permitted to read the key).

If no dossiers have been assembled (Phase 3b's extraction run and
assemble_dossiers.py have not run), this is reported as an informational,
non-failing empty state -- there is nothing to be structurally wrong with
data that does not exist yet. Once any dossier files exist, full structural
validation applies to whatever set is present.

Run: python validate_dossiers.py
"""
from __future__ import annotations

import json
import re
import sys

import config


FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)
        print(f"[FAIL] {message}", flush=True)
    else:
        print(f"[ok]   {message}", flush=True)


def log(message: str) -> None:
    print(f"[validate_dossiers] {message}", flush=True)


REQUIRED_STATUSES = {"evidence_found", "claim_only", "contradiction", "not_stated"}
REQUIRED_REQUIREMENT_IDS = [r["id"] for r in config.REQUIREMENTS]

# ---------------------------------------------------------------------------
# Banned vocabulary -- ranking, verdict, and recommendation language. This is
# the mechanical enforcement of the design's standing constraint: "the
# system helps the recruiter and never takes the final decision." Matched
# case-insensitively as whole phrases (word-boundary aware where the phrase
# is a single word, to avoid flagging incidental substrings like "reject"
# inside "rejected" being fine to flag too -- these ARE all decision verbs we
# want caught in any inflected form via a shared stem check below).
# ---------------------------------------------------------------------------

BANNED_PHRASES = [
    "recommend", "recommendation",
    "reject", "rejection",
    "shortlist",
    "rank", "ranking", "ranked",
    "top candidate", "best candidate", "worst candidate",
    "strong candidate", "weak candidate",
    "good fit", "poor fit", "bad fit",
    "should hire", "should not hire", "do not hire", "don't hire",
    "hire this candidate", "hire them",
    "unsuitable", "not suitable for the role", "suitable for the role",
    "advance to the next round", "advance this candidate",
    "screen out", "pass on this candidate",
    "should be shortlisted", "should be rejected",
    "we recommend", "our recommendation",
]

# Fields within a dossier that carry free text and must be scanned. Field
# names, not values -- walked generically below so a future field addition
# is caught automatically rather than needing this list extended by hand.
TEXT_FIELD_KEYS = {"quote", "note", "question", "name", "reason"}


# The no-verdict rule binds the DOSSIER'S OWN VOICE. Verbatim corpus quotes
# are the candidate's words (an RF corpus legitimately says "interference
# rejection", "clutter rejection", "sidelobe rejection"), so `quote` fields
# are exempt from this scan. In authored fields, the reject/rank stems are
# radar vocabulary too, so those two stems only count when the surrounding
# text is about the candidate/application rather than a signal chain.
CONTEXT_SENSITIVE_STEMS = {"reject", "rejection", "rank", "ranking", "ranked"}
VERDICT_CONTEXT = re.compile(r"candidat|applic|cv\b|résumé|resume|screen")


def scan_for_banned_language(obj, path: str, hits: list[tuple[str, str]]) -> None:
    """Walk a dossier (or any nested JSON structure) and record every banned
    phrase found in any string value, with the JSON path it occurred at, so
    a failure is traceable back to the exact field. Quote fields (verbatim
    corpus text) are exempt -- the rule governs the dossier's voice.
    """
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "quote":
                continue
            scan_for_banned_language(value, f"{path}.{key}", hits)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            scan_for_banned_language(item, f"{path}[{i}]", hits)
    elif isinstance(obj, str):
        lowered = obj.lower()
        for phrase in BANNED_PHRASES:
            for match in re.finditer(r"\b" + re.escape(phrase) + r"\b", lowered):
                if phrase in CONTEXT_SENSITIVE_STEMS:
                    window = lowered[max(0, match.start() - 60):match.end() + 60]
                    if not VERDICT_CONTEXT.search(window):
                        continue
                hits.append((path, phrase))
                break


def load_dossiers() -> dict[str, dict]:
    dossiers_dir = config.DATA_DIR / "dossiers"
    dossiers: dict[str, dict] = {}
    if not dossiers_dir.exists():
        return dossiers
    for path in sorted(dossiers_dir.glob("dossier_C*.json")):
        dossiers[path.stem.replace("dossier_", "")] = json.loads(
            path.read_text(encoding="utf-8"))
    return dossiers


def check_structure(dossiers: dict[str, dict]) -> None:
    log("=== structural checks ===")

    expected_ids = {f"C{i:03d}" for i in range(1, config.N_CANDIDATES + 1)}
    present_ids = set(dossiers.keys())
    missing = sorted(expected_ids - present_ids)
    unexpected = sorted(present_ids - expected_ids)

    if len(present_ids) < config.N_CANDIDATES:
        log(f"note: {len(present_ids)}/{config.N_CANDIDATES} candidates "
            "have an assembled dossier -- full 240-candidate coverage is "
            "only expected once the extraction run and assemble_dossiers.py "
            "have both completed for the whole corpus.")
    check(len(unexpected) == 0,
          f"no dossier carries an unrecognised candidate_id "
          f"(got {len(unexpected)}: {unexpected[:10]})")

    bad_requirement_sets = 0
    bad_statuses = 0
    bad_status_examples: list[str] = []
    missing_contradiction_notes = 0
    total_lines = 0
    all_banned_hits: list[tuple[str, str, str]] = []  # (candidate_id, path, phrase)

    for candidate_id, dossier in dossiers.items():
        check_local = check  # no-op alias for readability below

        if dossier.get("candidate_id") != candidate_id:
            bad_requirement_sets += 1  # reuse counter path; filename/content mismatch is structural too

        req_ids = [r["requirement_id"] for r in dossier.get("requirements", [])]
        if req_ids != REQUIRED_REQUIREMENT_IDS:
            bad_requirement_sets += 1

        for req in dossier.get("requirements", []):
            status = req.get("status")
            if status not in REQUIRED_STATUSES:
                bad_statuses += 1
                bad_status_examples.append(
                    f"{candidate_id}/{req.get('requirement_id')}={status!r}")
            if status == "contradiction" and not req.get("note"):
                missing_contradiction_notes += 1
            total_lines += len(req.get("lines", []))

        hits: list[tuple[str, str]] = []
        scan_for_banned_language(dossier, candidate_id, hits)
        for path, phrase in hits:
            all_banned_hits.append((candidate_id, path, phrase))

    check(bad_requirement_sets == 0,
          "every dossier's candidate_id matches its filename and its "
          f"requirements cover exactly the 12 requirement ids in config "
          f"order (got {bad_requirement_sets} mismatches)")
    check(bad_statuses == 0,
          f"every requirement status is one of {sorted(REQUIRED_STATUSES)} "
          f"(got {bad_statuses} violation(s): {bad_status_examples[:10]})")
    check(missing_contradiction_notes == 0,
          "every 'contradiction' status carries an explanatory note "
          f"(got {missing_contradiction_notes} missing)")
    check(len(all_banned_hits) == 0,
          "no ranking/verdict/recommendation vocabulary appears anywhere "
          f"in any dossier (got {len(all_banned_hits)} hit(s): "
          f"{all_banned_hits[:10]})")

    log(f"total cited lines across all loaded dossiers: {total_lines}")


def report_citation_failure_rate() -> None:
    log("=== citation-failure rate (pre-registration 2 input) ===")
    failures_path = config.DATA_DIR / "dossiers" / "_citation_failures.json"
    if not failures_path.exists():
        log("no _citation_failures.json found -- assemble_dossiers.py has "
            "not run yet.")
        return
    failures = json.loads(failures_path.read_text(encoding="utf-8"))
    log(f"{len(failures)} recorded citation failure(s) in "
        f"{failures_path.name}")


def main() -> None:
    dossiers = load_dossiers()

    if not dossiers:
        log("no dossiers found under data/dossiers/ -- Phase 3b's "
            "extraction run and assemble_dossiers.py have not run yet. "
            "This is an expected empty state, not a validation failure; "
            "this script activates fully once dossiers are assembled.")
        sys.exit(0)

    check_structure(dossiers)
    report_citation_failure_rate()

    if FAILURES:
        log(f"FAILED: {len(FAILURES)} check(s) did not pass -- see [FAIL] "
            "lines above")
        sys.exit(1)

    log(f"all structural checks passed for {len(dossiers)} dossier(s)")


if __name__ == "__main__":
    main()
