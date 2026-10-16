"""
Shared scoring / administration library for Phase 5 (09 Training Outcomes).

Used by both `run_instruments.py` (the three named instrument runs) and
`mark.py` (the perfect-scoring robustness pass and the naive-arm flaw
decomposition counterfactuals). Keeping this arithmetic in one place means
every consumer of "what does instrument X estimate for learner Y" goes
through the exact same code path -- there is no second, drifted copy of the
scoring or blending logic anywhere in Phase 5.

Two scoring MODES for a single (learner, form, occasion) task-performance
administration:
  - "scored"  -- the realistic, noisy layer: rubric_detectors.detect() run
    against the actual response TEXT in data/responses/. This is what a
    real deployment would use, and it inherits the scorer's measured
    94.23% item-level calibration (data/analysis/scorer_calibration.md).
  - "perfect" -- reads data/response_briefs/'s own points_earned/max_points
    directly (the intended, noise-free quality band Phase 2 planted before
    any prose was written). Used ONLY for the Phase 5 robustness check
    ("would any verdict flip under a perfect rater") -- never for the
    primary marking pass, and never by run_instruments.py.

Self-report values (confidence, satisfaction) are never touched by either
scoring mode: they are plain recorded numbers in every response file,
identical between "scored" and "perfect" runs by construction (Phase 2
wrote them once; Phase 3 prose never altered them -- validate_responses.py
already checked byte-identity against the brief). This is itself a finding
worth keeping visible in the robustness table: the feedback sheet
instrument cannot be affected by the scorer's reliability at all, because
it never scores response text.

Administrative fields read here (learner_id -> pre_form / post_form /
volunteer, from data/cohort/learners.csv) are logistics -- which form a
learner sat and when -- not the planted-truth columns (delta_post,
ability_*, confidence_baseline/delta/retention). Only those planted-truth
columns are "the answer key" in the sense of the rule that mark.py is the
sole reader of the key; this module never reads data/answer_key/, and neither does
run_instruments.py. Only mark.py opens that directory.
"""

import csv
import json
import sys
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CODE_DIR.parent
DATA_DIR = PROJECT_DIR / "data"

COHORT_DIR = DATA_DIR / "cohort"
RESPONSES_DIR = DATA_DIR / "responses"
BRIEFS_DIR = DATA_DIR / "response_briefs"

sys.path.insert(0, str(CODE_DIR))
import config  # noqa: E402
import rubric_detectors  # noqa: E402

OCCASIONS = config.COMPANY["occasions"]  # ["pre", "post", "follow_up_8wk"]
FORMS = ("A", "B")

# Max points per task index, read once from config.py (currently a flat 4
# for every one of the 10 tasks, but derived generically rather than
# hard-coded so a future change to TASK_PAIRS is honoured automatically).
MAX_POINTS_BY_INDEX = {pair["index"]: len(pair["rubric_items"]) for pair in config.TASK_PAIRS}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_admin():
    """
    Administrative roster only: learner_id -> {pre_form, post_form,
    volunteer}. Read from data/cohort/learners.csv, deliberately ignoring
    every planted-truth column that file also carries (delta_post,
    ability_*, confidence_*) -- this function never returns them, so a
    caller cannot accidentally leak them into an instrument run.
    """
    path = COHORT_DIR / "learners.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"Cohort roster not found at {path} -- run code/generate_structure.py first."
        )
    admin = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            admin[row["learner_id"]] = {
                "pre_form": row["pre_form"],
                "post_form": row["post_form"],
                "volunteer": row["volunteer"].strip().lower() == "true",
            }
    return admin


def load_responses():
    """(learner_id, form, occasion) -> response dict, from data/responses/."""
    responses = {}
    if not RESPONSES_DIR.exists():
        raise FileNotFoundError(f"Responses directory not found: {RESPONSES_DIR}")
    for path in sorted(RESPONSES_DIR.glob("*.json")):
        resp = json.loads(path.read_text(encoding="utf-8"))
        key = (resp["learner_id"], resp["form"], resp["occasion"])
        responses[key] = resp
    return responses


def load_briefs():
    """(learner_id, form, occasion) -> brief dict, from data/response_briefs/.
    Used ONLY for the perfect-scoring robustness pass."""
    briefs = {}
    if not BRIEFS_DIR.exists():
        raise FileNotFoundError(f"Response briefs directory not found: {BRIEFS_DIR}")
    for path in sorted(BRIEFS_DIR.glob("*.json")):
        if path.name == "manifest.csv":
            continue
        brief = json.loads(path.read_text(encoding="utf-8"))
        key = (brief["learner_id"], brief["form"], brief["occasion"])
        briefs[key] = brief
    return briefs


# ---------------------------------------------------------------------------
# Scoring a single (learner, form, occasion) administration
# ---------------------------------------------------------------------------
def normalized_score(learner_id, form, occasion, mode, responses, briefs=None):
    """
    Return the normalised rubric-point fraction (0-1) for one administration,
    in the given mode ("scored" = detector-on-text, "perfect" = brief's own
    points_earned/max_points).
    """
    key = (learner_id, form, occasion)
    if mode == "scored":
        resp = responses.get(key)
        if resp is None:
            raise KeyError(f"no response for {key}")
        total_points, total_max = 0, 0
        for answer in resp["answers"]:
            task_id = answer["task_id"]
            index = int(task_id[1:])
            max_points = MAX_POINTS_BY_INDEX[index]
            hits = rubric_detectors.detect(task_id, answer["text"])
            total_points += len(hits)
            total_max += max_points
        return total_points / total_max
    elif mode == "perfect":
        if briefs is None:
            raise ValueError("perfect mode requires briefs")
        brief = briefs.get(key)
        if brief is None:
            raise KeyError(f"no brief for {key}")
        total_points = sum(t["points_earned"] for t in brief["tasks"])
        total_max = sum(t["max_points"] for t in brief["tasks"])
        return total_points / total_max
    else:
        raise ValueError(f"unknown scoring mode: {mode!r}")


def self_report_of(learner_id, form, occasion, responses):
    """Self-report block for one administration -- identical between scoring
    modes and between the two forms at the same occasion (Phase 2 duplicated
    it deliberately; validate_responses.py already checked byte-identity)."""
    resp = responses[(learner_id, form, occasion)]
    return resp["self_report"]


# ---------------------------------------------------------------------------
# The one generic pre/post administration-effect function.
#
# Every named instrument (honest, naive) and every naive-arm decomposition
# counterfactual is one call to this function with a different
# (population, form_assignment, self_report_weight) triple. The feedback
# sheet is structurally different (post-only, no delta) and is handled by
# its own function below.
# ---------------------------------------------------------------------------
def compute_pre_post_effect(
    learner_ids, admin, responses, form_assignment, self_report_weight,
    mode="scored", briefs=None, post_occasion="post",
):
    """
    For each learner_id, compute:
      - pre_form / post_form actually administered (depends on
        form_assignment: "counterbalanced" uses the learner's own
        pre_form/post_form; "same_form_repeated" uses the learner's
        pre_form for BOTH occasions, which is what plants the naive arm's
        practice effect since that administration is a repeat).
      - performance_pre, performance_post, performance_delta (normalised
        rubric-point fraction, via `normalized_score`).
      - confidence_pre, confidence_post, confidence_delta_scaled (the 1-7
        confidence gain rescaled to a 0-1-ish unit by dividing by 6, the
        scale's full width, so it is roughly comparable to performance_delta
        before blending -- a documented Phase 5 build choice).
      - blended_effect = (1 - self_report_weight) * performance_delta
                         + self_report_weight * confidence_delta_scaled
        (self_report_weight = 0.0 reduces this exactly to performance_delta,
        which is the honest instrument's definition).

    `post_occasion` lets the fast-forgetter demonstration reuse this same
    function with post_occasion="follow_up_8wk" to compute an 8-week delta
    on the same form-assignment logic, without duplicating the arithmetic.

    Returns a list of per-learner dicts, in the order of learner_ids given.
    """
    if form_assignment not in ("counterbalanced", "same_form_repeated"):
        raise ValueError(f"unknown form_assignment: {form_assignment!r}")

    records = []
    for learner_id in learner_ids:
        roster = admin[learner_id]
        pre_form = roster["pre_form"]
        if form_assignment == "counterbalanced":
            post_form = roster["post_form"]
        else:  # same_form_repeated -- the naive arm's practice-effect flaw
            post_form = pre_form

        performance_pre = normalized_score(learner_id, pre_form, "pre", mode, responses, briefs)
        performance_post = normalized_score(learner_id, post_form, post_occasion, mode, responses, briefs)
        performance_delta = performance_post - performance_pre

        confidence_pre = self_report_of(learner_id, pre_form, "pre", responses)["confidence"]
        confidence_post = self_report_of(learner_id, post_form, post_occasion, responses)["confidence"]
        confidence_delta_scaled = (confidence_post - confidence_pre) / 6.0  # 1-7 scale, width 6

        if self_report_weight > 0:
            blended_effect = (
                (1.0 - self_report_weight) * performance_delta
                + self_report_weight * confidence_delta_scaled
            )
        else:
            blended_effect = performance_delta

        records.append({
            "learner_id": learner_id,
            "pre_form_used": pre_form,
            "post_form_used": post_form,
            "is_repeat_form": form_assignment == "same_form_repeated",
            "performance_pre": performance_pre,
            "performance_post": performance_post,
            "performance_delta": performance_delta,
            "confidence_pre": confidence_pre,
            "confidence_post": confidence_post,
            "confidence_delta_scaled": confidence_delta_scaled,
            "self_report_weight": self_report_weight,
            "blended_effect": blended_effect,
        })
    return records


def compute_feedback_sheet(learner_ids, admin, responses):
    """
    The feedback sheet: post-only self-report, no task performance at all.
    Per learner: confidence_post (self-assessed post-training skill, the
    closest available proxy for "self-assessed improvement" since the sheet
    -- by design, matching real feedback forms -- never asks a pre-training
    baseline question) and satisfaction_post (the plain happy-sheet number).
    """
    records = []
    for learner_id in learner_ids:
        roster = admin[learner_id]
        post_form = roster["post_form"]
        self_report = self_report_of(learner_id, post_form, "post", responses)
        records.append({
            "learner_id": learner_id,
            "form_used_for_lookup": post_form,
            "confidence_post": self_report["confidence"],
            "satisfaction_post": self_report["satisfaction"],
        })
    return records
