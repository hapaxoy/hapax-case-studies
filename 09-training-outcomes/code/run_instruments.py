"""
Phase 5, step 1 -- run the three named instruments over the SCORED
responses (the realistic, noisy layer: `rubric_detectors.detect()` applied
to response TEXT in data/responses/, never the response briefs' intended
scores). Reads each instrument's administration rule from
data/instruments/*.yaml, and the pre_form/post_form/volunteer roster from
data/cohort/learners.csv (administrative logistics, never the planted-truth
columns that same file also carries -- see instrument_scoring.py's module
docstring).

This script never opens data/answer_key/. It has no notion of "correct" --
it only applies each instrument's own stated rules and reports what each
instrument, running honestly by its own design, would conclude. Marking
those conclusions against the planted truth is code/mark.py's job alone.

Outputs (data/analysis/instrument_runs/):
    honest.json          -- per-learner delta-hat, confidence divergence,
                             confident-non-learner flag; cohort summary.
    feedback_sheet.json  -- per-learner post-only self-report; cohort summary.
    naive.json           -- per-learner blended effect (volunteers only);
                             cohort summary.
    manifest.json        -- what ran, when, against how many response files.
"""

import json
import statistics
import sys
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CODE_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
INSTRUMENTS_DIR = DATA_DIR / "instruments"
OUT_DIR = DATA_DIR / "analysis" / "instrument_runs"

sys.path.insert(0, str(CODE_DIR))
import instrument_scoring as scoring  # noqa: E402

try:
    import yaml
except ImportError as exc:
    print(f"ERROR: PyYAML is required to read {INSTRUMENTS_DIR} configs: {exc}", file=sys.stderr)
    sys.exit(1)

# Confirm output directory is not the input directory or any source folder
# (house rule: output only to the specified output folder, never touch
# inputs). OUT_DIR is a fresh subfolder of data/analysis/, disjoint from
# every directory this script reads from.
_READ_DIRS = {INSTRUMENTS_DIR.resolve(), scoring.COHORT_DIR.resolve(), scoring.RESPONSES_DIR.resolve()}
assert OUT_DIR.resolve() not in _READ_DIRS, "refusing to write instrument_runs/ over a source directory"


def load_instrument_config(name):
    path = INSTRUMENTS_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"missing instrument config: {path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def zscore(values):
    """Population-relative z-scores (sample mean/sd); returns a list aligned
    with `values`. If sd is (numerically) zero, returns zeros to avoid a
    divide-by-zero -- would only happen with a degenerate, non-varying run."""
    mean = statistics.fmean(values)
    sd = statistics.pstdev(values)
    if sd == 0:
        return [0.0 for _ in values]
    return [(v - mean) / sd for v in values]


# ---------------------------------------------------------------------------
# The honest instrument
# ---------------------------------------------------------------------------
DIVERGENCE_FLAG_THRESHOLD = 1.0  # z-score units


def run_honest(admin, responses, mode="scored", briefs=None, quiet=False):
    """
    `mode`/`briefs` let code/mark.py reuse this exact function for the
    perfect-scoring robustness pass (mode="perfect", briefs=<loaded briefs>)
    -- the same administration logic, the only difference being which
    scoring layer answers "how many rubric items did this response earn".
    """
    if not quiet:
        print("Running THE HONEST INSTRUMENT (A/B counterbalanced pre/post, all 40 learners)...")
    learner_ids = sorted(admin.keys(), key=lambda lid: int(lid[1:]))
    records = scoring.compute_pre_post_effect(
        learner_ids, admin, responses,
        form_assignment="counterbalanced", self_report_weight=0.0, mode=mode, briefs=briefs,
    )

    # Confidence-vs-performance divergence: the confident-non-learner
    # detector. z-scored across this run's own 40 delta-hats and 40
    # confidence gains (not against any known archetype count), then
    # flagged at a single frozen threshold decided before this run. This
    # never reads the answer key: it only compares each learner's
    # self-reported confidence gain to their own measured performance gain,
    # relative to the rest of the cohort.
    delta_hats = [r["performance_delta"] for r in records]
    confidence_gains_scaled = [r["confidence_delta_scaled"] for r in records]
    z_delta = zscore(delta_hats)
    z_confidence = zscore(confidence_gains_scaled)

    for rec, zd, zc in zip(records, z_delta, z_confidence):
        divergence_z = zc - zd
        rec["delta_hat"] = rec.pop("performance_delta")
        rec["z_delta_hat"] = zd
        rec["z_confidence_gain"] = zc
        rec["divergence_z"] = divergence_z
        rec["flagged_confident_non_learner"] = divergence_z > DIVERGENCE_FLAG_THRESHOLD

    flagged = [r for r in records if r["flagged_confident_non_learner"]]
    cohort_mean_delta_hat = statistics.fmean(delta_hats)
    cohort_sd_delta_hat = statistics.stdev(delta_hats)  # sample sd, n=40

    summary = {
        "n_learners": len(records),
        "cohort_mean_delta_hat": cohort_mean_delta_hat,
        "cohort_sd_delta_hat": cohort_sd_delta_hat,
        "divergence_flag_threshold_z": DIVERGENCE_FLAG_THRESHOLD,
        "n_flagged_confident_non_learners": len(flagged),
        "flagged_learner_ids": [r["learner_id"] for r in flagged],
    }
    if not quiet:
        print(f"  cohort mean delta-hat: {cohort_mean_delta_hat:.4f} (sd {cohort_sd_delta_hat:.4f})")
        print(f"  flagged as confident non-learners (divergence z > {DIVERGENCE_FLAG_THRESHOLD}): "
              f"{len(flagged)} of {len(records)} -- {summary['flagged_learner_ids']}")
    return {"instrument": "honest", "summary": summary, "learners": records}


# ---------------------------------------------------------------------------
# The feedback sheet
# ---------------------------------------------------------------------------
def run_feedback_sheet(admin, responses):
    print("Running THE FEEDBACK SHEET (post-only self-report, all 40 learners)...")
    learner_ids = sorted(admin.keys(), key=lambda lid: int(lid[1:]))
    records = scoring.compute_feedback_sheet(learner_ids, admin, responses)

    confidences = [r["confidence_post"] for r in records]
    satisfactions = [r["satisfaction_post"] for r in records]
    summary = {
        "n_learners": len(records),
        "mean_confidence_post": statistics.fmean(confidences),
        "mean_satisfaction_post": statistics.fmean(satisfactions),
    }
    print(f"  mean post-training self-reported confidence: {summary['mean_confidence_post']:.3f} (1-7 scale)")
    print(f"  mean post-training satisfaction: {summary['mean_satisfaction_post']:.3f} (1-7 scale)")
    return {"instrument": "feedback_sheet", "summary": summary, "learners": records}


# ---------------------------------------------------------------------------
# The naive evaluation
# ---------------------------------------------------------------------------
def run_naive(admin, responses, naive_config, mode="scored", briefs=None, quiet=False):
    volunteer_ids = naive_config["volunteer_learner_ids"]
    weight = naive_config["self_report_weight"]
    if not quiet:
        print(f"Running THE NAIVE EVALUATION (volunteers only, n={len(volunteer_ids)}; "
              f"same form repeated; self-report weight {weight})...")
    records = scoring.compute_pre_post_effect(
        volunteer_ids, admin, responses,
        form_assignment="same_form_repeated", self_report_weight=weight, mode=mode, briefs=briefs,
    )
    blended = [r["blended_effect"] for r in records]
    summary = {
        "n_learners": len(records),
        "self_report_weight": weight,
        "cohort_mean_blended_effect": statistics.fmean(blended),
        "cohort_sd_blended_effect": statistics.stdev(blended) if len(blended) > 1 else 0.0,
    }
    if not quiet:
        print(f"  volunteer-subset mean blended effect: {summary['cohort_mean_blended_effect']:.4f}")
    return {"instrument": "naive", "summary": summary, "learners": records}


def main():
    print("09 Training Outcomes -- Phase 5, step 1: instrument runs")
    print(f"Reading responses from {scoring.RESPONSES_DIR}")
    print(f"Reading cohort roster (admin fields only) from {scoring.COHORT_DIR / 'learners.csv'}")
    print(f"Reading instrument configs from {INSTRUMENTS_DIR}")

    try:
        admin = scoring.load_admin()
        responses = scoring.load_responses()
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    expected_files = len(admin) * 2 * 3  # learners x forms x occasions
    if len(responses) != expected_files:
        print(f"ERROR: expected {expected_files} response files, found {len(responses)}. "
              f"Run code/validate_responses.py to diagnose before marking.", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(admin)} learners, {len(responses)} response files -- complete.\n")

    try:
        honest_config = load_instrument_config("honest")
        feedback_config = load_instrument_config("feedback_sheet")
        naive_config = load_instrument_config("naive")
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    # Sanity-check the configs are what the code below assumes, rather than
    # silently drifting from data/instruments/*.yaml if it is ever hand-edited.
    assert honest_config["form_assignment"] == "counterbalanced"
    assert honest_config["self_report_weight"] == 0.0
    assert feedback_config["occasions_used"] == ["post"]
    assert naive_config["form_assignment"] == "same_form_repeated"
    assert naive_config["population"] == "volunteers"

    honest_result = run_honest(admin, responses)
    feedback_result = run_feedback_sheet(admin, responses)
    naive_result = run_naive(admin, responses, naive_config)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, result in (
        ("honest", honest_result),
        ("feedback_sheet", feedback_result),
        ("naive", naive_result),
    ):
        out_path = OUT_DIR / f"{name}.json"
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  wrote {out_path}")

    manifest = {
        "n_learners_total": len(admin),
        "n_response_files": len(responses),
        "instruments_run": ["honest", "feedback_sheet", "naive"],
        "scoring_mode": "scored",
        "note": (
            "This is the primary, realistic run: task performance scored by "
            "code/rubric_detectors.py against response TEXT, not the "
            "response briefs' intended scores. See data/analysis/"
            "scorer_calibration.md for the scorer's measured 94.23% "
            "item-level agreement against the briefs. code/mark.py runs a "
            "separate perfect-scoring sensitivity pass for comparison; it "
            "is not written here."
        ),
    }
    manifest_path = OUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  wrote {manifest_path}")

    print("\nDone. Run code/mark.py next.")


if __name__ == "__main__":
    main()
