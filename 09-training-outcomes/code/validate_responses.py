"""
09 Training Outcomes -- Phase 3 closure: corpus-wide response validation.

Validates all 240 Phase-3 response files (`data/responses/*.json`, written
by five parallel batch agents from the deterministic response briefs in
`data/response_briefs/`) against the manifest and against each file's own
brief. Every check below is a coherence rule for the response corpus; per
house convention, a dataset that fails validation is a bug, not a judgment
call. Exits 1 on any hard violation.

Checks, in order:
  1. Manifest completeness -- every `data/response_briefs/manifest.csv` row
     has a matching response file; no orphan response files.
  2. Schema -- required keys and types on every response file.
  3. Task-id order -- the 10 answers appear in task-index order for the
     file's form (A1..A10 or B1..B10), no gaps or duplicates.
  4. self_report byte-identity -- confidence/satisfaction in the response
     must exactly match the brief's self_report (Phase 3 prose generation
     must never touch these deterministic Phase-2 numbers).
  5. Banned-term scan -- meta/mechanism vocabulary that describes the
     SIMULATION'S internal machinery (rubric, archetype, band, practice
     effect, ...) should never appear in a learner's own answer text. This
     is a judgment call (no earlier rule defines
     the list); see the BANNED_TERMS block below for the reasoning per
     term, and note the deliberate "planted error" exclusion.
  6. Rubric-fidelity check on the binary/enumerable policy tasks (A7/B7,
     A8/B8 only -- a deliberately narrow check,
     distinct from the full 10-task calibration run in score_responses.py):
     detect which of a task's rubric items the response text satisfies and
     compare against the brief's rubric_items_hit.

This script never modifies data/responses/ or data/response_briefs/ --
violations are reported for targeted regeneration, never hand-fixed here.
"""

import json
import re
import sys
from pathlib import Path
from collections import defaultdict

CODE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CODE_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
RESPONSES_DIR = DATA_DIR / "responses"
BRIEFS_DIR = DATA_DIR / "response_briefs"
MANIFEST_PATH = BRIEFS_DIR / "manifest.csv"

sys.path.insert(0, str(CODE_DIR))
import rubric_detectors  # noqa: E402

EXPECTED_FILE_COUNT = 240
EXPECTED_TASKS_PER_FORM = 10

# ---------------------------------------------------------------------------
# Banned-term scan -- meta/mechanism vocabulary a real learner would never
# write, because it names the SIMULATION's internal scoring machinery
# rather than the training content itself. Grouped by what it would leak:
# ---------------------------------------------------------------------------
BANNED_TERMS = [
    # The scoring/rubric mechanism itself
    "rubric", "rubric item", "rubric band", "band label", "item_difficulty",
    "item difficulty", "characteristic mistake", "points_earned", "max_points",
    "answer key", "cohort truth", "planted truth",
    # The generation model's internal variables
    "effective ability", "effective_ability", "assessment_noise",
    "assessment noise", "delta_post", "confidence_delta",
    # The naive arm's planted flaw -- must stay invisible to the learner
    "practice effect", "practice_bonus", "volunteering propensity",
    # Archetype labels -- a learner cannot know their own archetype
    "confident non-learner", "non-responder", "fast forgetter", "ceiling case",
    # Instrument names -- a learner would not refer to instruments by these
    # marketing/analysis labels while answering a task
    "the honest instrument", "the naive evaluation", "the feedback sheet",
]

# EXCLUSION, deliberate: "planted error" / "planted errors" is NOT banned.
# It is quoted verbatim from the Task 3 and Task 4 prompts themselves
# ("Find the planted error...", "Find both planted errors...") -- the
# in-world exercise frames the exercise that way, so a learner echoing the
# prompt's own wording is expected, legitimate response language, not a
# simulation leak. Do not add "planted error" back to BANNED_TERMS.

# Practice-effect self-awareness: a repeat-form response should never notice
# it has seen the form before (the naive arm's flaw must stay implicit).
PRACTICE_AWARENESS_PATTERNS = [
    r"same form as (before|last time)", r"i remember this from",
    r"saw this (question|form) (already|before)", r"last time i answered this",
    r"answered this (before|already)", r"seen this (one |question )?before",
]

# A learner should never refer to their own internal learner id in prose.
LEARNER_ID_PATTERN = re.compile(r"\bL\d{2}\b")


def load_manifest():
    rows = []
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        header = f.readline().strip().split(",")
        for line in f:
            line = line.strip()
            if not line:
                continue
            values = line.split(",")
            rows.append(dict(zip(header, values)))
    return rows


def check_manifest_completeness(manifest_rows, violations):
    print("Step 1/6: manifest completeness...")
    response_files = {p.name for p in RESPONSES_DIR.glob("*.json")}
    manifest_files = {row["filename"] for row in manifest_rows}

    missing = manifest_files - response_files
    for fname in sorted(missing):
        violations["manifest"].append(f"manifest row {fname} has no response file")

    orphans = response_files - manifest_files
    for fname in sorted(orphans):
        violations["manifest"].append(f"response file {fname} has no manifest row")

    if len(response_files) != EXPECTED_FILE_COUNT:
        violations["manifest"].append(
            f"expected {EXPECTED_FILE_COUNT} response files, found {len(response_files)}"
        )
    print(f"  {len(response_files)} response files, {len(manifest_rows)} manifest rows, "
          f"{len(missing)} missing, {len(orphans)} orphaned")


def check_schema(resp, fname, violations):
    required_top = ["response_id", "learner_id", "form", "occasion", "answers", "self_report"]
    for key in required_top:
        if key not in resp:
            violations["schema"].append(f"{fname}: missing top-level key '{key}'")
            return  # further checks would KeyError

    if resp["response_id"] != fname.replace(".json", ""):
        violations["schema"].append(
            f"{fname}: response_id '{resp['response_id']}' does not match filename"
        )

    expected_learner, expected_form_part, *rest = fname.replace(".json", "").split("_")
    expected_form = expected_form_part.replace("form", "")
    expected_occasion = "_".join(rest)
    if resp["learner_id"] != expected_learner:
        violations["schema"].append(
            f"{fname}: learner_id '{resp['learner_id']}' does not match filename"
        )
    if resp["form"] != expected_form:
        violations["schema"].append(f"{fname}: form '{resp['form']}' does not match filename")
    if resp["occasion"] != expected_occasion:
        violations["schema"].append(
            f"{fname}: occasion '{resp['occasion']}' does not match filename"
        )

    answers = resp["answers"]
    if not isinstance(answers, list) or len(answers) != EXPECTED_TASKS_PER_FORM:
        violations["schema"].append(
            f"{fname}: answers must be a list of {EXPECTED_TASKS_PER_FORM}, "
            f"got {len(answers) if isinstance(answers, list) else type(answers)}"
        )
    else:
        for i, ans in enumerate(answers):
            if "task_id" not in ans or "text" not in ans:
                violations["schema"].append(f"{fname}: answers[{i}] missing task_id or text")
                continue
            if not isinstance(ans["text"], str) or not ans["text"].strip():
                violations["schema"].append(f"{fname}: answers[{i}] ({ans['task_id']}) has empty text")

    sr = resp["self_report"]
    if not isinstance(sr, dict) or "confidence" not in sr or "satisfaction" not in sr:
        violations["schema"].append(f"{fname}: self_report missing confidence/satisfaction")
    else:
        if not isinstance(sr["confidence"], (int, float)):
            violations["schema"].append(f"{fname}: self_report.confidence is not numeric")
        if sr["satisfaction"] is not None and not isinstance(sr["satisfaction"], (int, float)):
            violations["schema"].append(f"{fname}: self_report.satisfaction is not numeric or null")


def check_task_order(resp, fname, violations):
    answers = resp.get("answers")
    if not isinstance(answers, list):
        return  # already flagged by schema check
    form = resp.get("form", "")
    expected_ids = [f"{form}{i}" for i in range(1, EXPECTED_TASKS_PER_FORM + 1)]
    actual_ids = [a.get("task_id") for a in answers]
    if actual_ids != expected_ids:
        violations["task_order"].append(
            f"{fname}: task_id order {actual_ids} does not match expected {expected_ids}"
        )


def check_self_report_identity(resp, brief, fname, violations):
    resp_sr = resp.get("self_report", {})
    brief_sr = brief.get("self_report", {})
    for field in ("confidence", "satisfaction"):
        r_val = resp_sr.get(field)
        b_val = brief_sr.get(field)
        if r_val != b_val:
            violations["self_report"].append(
                f"{fname}: self_report.{field} = {r_val!r} in response but {b_val!r} in brief"
            )


def check_banned_terms(resp, fname, violations):
    for ans in resp.get("answers", []):
        text = ans.get("text", "")
        low = text.lower()
        for term in BANNED_TERMS:
            if term in low:
                violations["banned_terms"].append(
                    f"{fname} / {ans.get('task_id')}: banned term '{term}' found in response text"
                )
        for pattern in PRACTICE_AWARENESS_PATTERNS:
            if re.search(pattern, low):
                violations["banned_terms"].append(
                    f"{fname} / {ans.get('task_id')}: practice-effect self-awareness "
                    f"matched pattern '{pattern}'"
                )
        for m in LEARNER_ID_PATTERN.finditer(text):
            violations["banned_terms"].append(
                f"{fname} / {ans.get('task_id')}: learner-id-shaped token '{m.group(0)}' "
                f"found in response text"
            )


# Tasks 7 and 8 are the binary/enumerable policy tasks chosen
# for a focused fidelity check (distinct from the full 10-task
# calibration run in score_responses.py).
FIDELITY_CHECK_TASK_INDICES = {7, 8}


def check_rubric_fidelity(resp, brief, fname, violations):
    for ans in resp.get("answers", []):
        task_id = ans.get("task_id", "")
        if not task_id or int(task_id[1:]) not in FIDELITY_CHECK_TASK_INDICES:
            continue
        btask = next((t for t in brief.get("tasks", []) if t["task_id"] == task_id), None)
        if btask is None:
            continue
        briefed_hits = set(btask["rubric_items_hit"])
        try:
            detected_hits = rubric_detectors.detect(task_id, ans["text"])
        except Exception as exc:
            violations["rubric_fidelity"].append(
                f"{fname} / {task_id}: detector error: {exc}"
            )
            continue
        max_points = btask["max_points"]
        for item_num in range(1, max_points + 1):
            expected = item_num in briefed_hits
            detected = item_num in detected_hits
            if expected != detected:
                violations["rubric_fidelity"].append(
                    f"{fname} / {task_id} item {item_num}: brief says hit={expected}, "
                    f"text content suggests hit={detected}"
                )


def main():
    print("09 Training Outcomes -- Phase 3 response validation")
    print(f"Responses: {RESPONSES_DIR}")
    print(f"Briefs: {BRIEFS_DIR}")

    if not RESPONSES_DIR.exists():
        print(f"ERROR: {RESPONSES_DIR} does not exist", file=sys.stderr)
        sys.exit(1)
    if not MANIFEST_PATH.exists():
        print(f"ERROR: {MANIFEST_PATH} does not exist", file=sys.stderr)
        sys.exit(1)

    violations = defaultdict(list)

    manifest_rows = load_manifest()
    check_manifest_completeness(manifest_rows, violations)

    print("Step 2-6/6: per-file schema, order, self-report identity, banned terms, "
          "rubric fidelity (tasks 7/8)...")
    response_files = sorted(RESPONSES_DIR.glob("*.json"))
    checked = 0
    for resp_path in response_files:
        fname = resp_path.name
        try:
            resp = json.loads(resp_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            violations["schema"].append(f"{fname}: invalid JSON ({exc})")
            continue

        check_schema(resp, fname, violations)
        check_task_order(resp, fname, violations)

        brief_path = BRIEFS_DIR / fname
        if not brief_path.exists():
            violations["manifest"].append(f"{fname}: no matching brief file")
            continue
        brief = json.loads(brief_path.read_text(encoding="utf-8"))

        check_self_report_identity(resp, brief, fname, violations)
        check_banned_terms(resp, fname, violations)
        check_rubric_fidelity(resp, brief, fname, violations)
        checked += 1

    print(f"  checked {checked} response files against their briefs")
    print()

    # ---------------------------------------------------------------------
    # Report
    # ---------------------------------------------------------------------
    total_violations = sum(len(v) for v in violations.values())
    section_order = ["manifest", "schema", "task_order", "self_report", "banned_terms", "rubric_fidelity"]
    section_labels = {
        "manifest": "Manifest completeness",
        "schema": "Schema",
        "task_order": "Task-id order",
        "self_report": "self_report byte-identity",
        "banned_terms": "Banned-term scan",
        "rubric_fidelity": "Rubric-fidelity check (tasks 7/8)",
    }

    print("=" * 70)
    print("VALIDATION REPORT")
    print("=" * 70)
    for section in section_order:
        items = violations.get(section, [])
        status = "PASS" if not items else f"FAIL ({len(items)} violation(s))"
        print(f"\n[{section_labels[section]}] {status}")
        for item in items:
            print(f"  - {item}")
        if section == "rubric_fidelity" and items:
            print(
                "  NOTE: this check uses the same keyword-based rubric_detectors.py "
                "used for the full 10-task calibration run in score_responses.py, "
                "which measured ~94% item-level agreement against the briefs (see "
                "data/analysis/scorer_calibration.md). Most of the candidates above "
                "are therefore expected to be detector recall/precision limits on "
                "paraphrase, not genuine Phase-3 defects -- cross-reference against "
                "scorer_calibration.md's disagreement classification before treating "
                "any of these as a regeneration candidate. The cross-batch "
                "audit is the source of truth for CONFIRMED fidelity "
                "bugs; this section's job is to surface new candidates for the same "
                "kind of hand investigation, not to assert bugs on its own."
            )

    print()
    print("=" * 70)
    if total_violations == 0:
        print("ALL CHECKS PASSED")
        print("=" * 70)
        sys.exit(0)
    else:
        print(f"FAILED: {total_violations} total violation(s) across "
              f"{sum(1 for s in section_order if violations.get(s))} section(s)")
        print("=" * 70)
        sys.exit(1)


if __name__ == "__main__":
    main()
