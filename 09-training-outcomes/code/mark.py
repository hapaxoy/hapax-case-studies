"""
Phase 5, step 2 -- `mark.py`, the SOLE reader of data/answer_key/ in this
project. Everything upstream of this file -- response
generation, prose, instrument administration in run_instruments.py -- is
blind to the planted truth. This script is where that blindness ends: it
joins each instrument's estimate against the planted delta_post, archetype,
and volunteer flag, and renders the six pre-registered
verdicts, frozen whatever the result.

It also runs three things the pre-registration asks for that are naturally marking-
time work rather than instrument administration:
  1. The naive arm's overstatement, decomposed into its three planted flaws
     via one-flaw-off counterfactual re-runs (selection, practice effect,
     self-report weighting), each isolated by calling
     `run_instruments.run_naive` / `instrument_scoring.compute_pre_post_effect`
     directly with one rule changed and the other two held at the naive
     arm's actual settings.
  2. A robustness table the design did not anticipate but the scorer's
     documented 94.23% calibration (data/analysis/scorer_calibration.md)
     makes possible: every verdict computed twice -- once on the realistic,
     noisy scored-text layer (primary), once on the response briefs' own
     "perfect" intended scores (a rater-reliability sensitivity check) --
     reporting whether any verdict flips.
  3. The fast-forgetter demonstration: the standard two-occasion pre/post
     design cannot see the fast forgetters' decay (the
     designed blind spot); the +8-week response data, which no named
     instrument reads as sold, can.

Output: data/analysis/report.md (human-readable) and
data/analysis/marks.json (full detail, everything this script computed).
Deterministic given the existing corpus; re-running produces a
byte-identical marks.json (see `main()`'s ordering discipline).
"""

import csv
import json
import statistics
import sys
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CODE_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
ANSWER_KEY_DIR = DATA_DIR / "answer_key"
INSTRUMENT_RUNS_DIR = DATA_DIR / "analysis" / "instrument_runs"
ANALYSIS_DIR = DATA_DIR / "analysis"

sys.path.insert(0, str(CODE_DIR))
import config  # noqa: E402
import instrument_scoring as scoring  # noqa: E402
import run_instruments  # noqa: E402 -- reused for run_honest/run_naive, mode-parametrised

# Output must never coincide with any input directory (house rule).
assert ANALYSIS_DIR.resolve() != ANSWER_KEY_DIR.resolve()
assert ANALYSIS_DIR.resolve() != INSTRUMENT_RUNS_DIR.resolve()

REPORT_PATH = ANALYSIS_DIR / "report.md"
MARKS_PATH = ANALYSIS_DIR / "marks.json"


# ---------------------------------------------------------------------------
# Loading -- the answer key, and the persisted primary-pass instrument runs
# ---------------------------------------------------------------------------
def load_answer_key():
    path = ANSWER_KEY_DIR / "answer_key.csv"
    if not path.exists():
        raise FileNotFoundError(f"missing answer key: {path} -- run generate_structure.py first.")
    rows = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows[row["learner_id"]] = {
                "learner_id": row["learner_id"],
                "name": row["name"],
                "role": row["role"],
                "archetype": row["archetype"],
                "archetype_label": row["archetype_label"],
                "pre_form": row["pre_form"],
                "post_form": row["post_form"],
                "delta_post": float(row["delta_post"]),
                "retention_factor": float(row["retention_factor"]),
                "ability_pre": float(row["ability_pre"]),
                "ability_post": float(row["ability_post"]),
                "ability_8wk": float(row["ability_8wk"]),
                "confidence_pre": float(row["confidence_pre"]),
                "confidence_post": float(row["confidence_post"]),
                "confidence_8wk": float(row["confidence_8wk"]),
                "confidence_delta_post": float(row["confidence_delta_post"]),
                "volunteer": row["volunteer"].strip().lower() == "true",
                "volunteering_propensity": float(row["volunteering_propensity"]),
            }
    if len(rows) != 40:
        raise ValueError(f"expected 40 learners in the answer key, found {len(rows)}")
    return rows


def load_instrument_run(name):
    path = INSTRUMENT_RUNS_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"missing instrument run: {path} -- run code/run_instruments.py first.")
    return json.loads(path.read_text(encoding="utf-8"))


def pearson_r(xs, ys):
    n = len(xs)
    if n < 2:
        return float("nan")
    mean_x, mean_y = statistics.fmean(xs), statistics.fmean(ys)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x == 0 or var_y == 0:
        return float("nan")
    return cov / (var_x * var_y) ** 0.5


# ---------------------------------------------------------------------------
# Expectation 1 -- honest instrument recovers the planted cohort mean effect
# ---------------------------------------------------------------------------
def check_expectation_1(honest_run, answer_key):
    planted_deltas = [row["delta_post"] for row in answer_key.values()]
    planted_mean = statistics.fmean(planted_deltas)
    planted_sd = statistics.stdev(planted_deltas)  # sample sd, n=40

    measured_mean = honest_run["summary"]["cohort_mean_delta_hat"]
    tolerance = 0.10 * planted_sd
    gap = measured_mean - planted_mean
    met = abs(gap) <= tolerance

    return {
        "expectation": 1,
        "description": "Honest instrument recovers the planted cohort mean effect within +/-0.10 sigma.",
        "planted_cohort_mean_delta": planted_mean,
        "planted_cohort_sd_delta": planted_sd,
        "tolerance_abs": tolerance,
        "measured_cohort_mean_delta_hat": measured_mean,
        "gap": gap,
        "met": met,
    }


# ---------------------------------------------------------------------------
# Expectation 2 -- confident-non-learner detection
# ---------------------------------------------------------------------------
def check_expectation_2(honest_run, answer_key):
    planted_cnl_ids = {lid for lid, row in answer_key.items() if row["archetype"] == "confident_non_learner"}
    flagged_ids = set(honest_run["summary"]["flagged_learner_ids"])
    caught = planted_cnl_ids & flagged_ids
    missed = planted_cnl_ids - flagged_ids
    false_positives = flagged_ids - planted_cnl_ids

    met = len(caught) >= 6  # pre-registered: ">= 6 of 7"
    return {
        "expectation": 2,
        "description": "Honest instrument flags >= 6 of the 7 confident non-learners.",
        "n_planted_confident_non_learners": len(planted_cnl_ids),
        "planted_confident_non_learner_ids": sorted(planted_cnl_ids, key=lambda x: int(x[1:])),
        "n_flagged_total": len(flagged_ids),
        "n_caught": len(caught),
        "caught_ids": sorted(caught, key=lambda x: int(x[1:])),
        "missed_ids": sorted(missed, key=lambda x: int(x[1:])),
        "false_positive_ids": sorted(false_positives, key=lambda x: int(x[1:])),
        "met": met,
    }


# ---------------------------------------------------------------------------
# Expectation 3 -- feedback sheet correlation with planted delta
# ---------------------------------------------------------------------------
def check_expectation_3(feedback_run, answer_key):
    learner_ids = [r["learner_id"] for r in feedback_run["learners"]]
    confidences = [r["confidence_post"] for r in feedback_run["learners"]]
    satisfactions = [r["satisfaction_post"] for r in feedback_run["learners"]]
    planted_deltas = [answer_key[lid]["delta_post"] for lid in learner_ids]

    r_confidence = pearson_r(confidences, planted_deltas)
    r_satisfaction = pearson_r(satisfactions, planted_deltas)
    met = abs(r_confidence) < 0.30

    return {
        "expectation": 3,
        "description": "Feedback sheet correlates with planted delta at r < 0.30 (near-uninformative).",
        "r_confidence_post_vs_planted_delta": r_confidence,
        "r_satisfaction_post_vs_planted_delta": r_satisfaction,
        "threshold_abs_r": 0.30,
        "met": met,
    }


# ---------------------------------------------------------------------------
# Expectation 4 -- naive overstatement, decomposed
# ---------------------------------------------------------------------------
def check_expectation_4(naive_run, answer_key, admin, responses, naive_config, mode="scored", briefs=None):
    volunteer_ids = naive_config["volunteer_learner_ids"]
    weight = naive_config["self_report_weight"]

    planted_mean_all = statistics.fmean(row["delta_post"] for row in answer_key.values())
    planted_mean_volunteers = statistics.fmean(answer_key[lid]["delta_post"] for lid in volunteer_ids)

    e_naive = naive_run["summary"]["cohort_mean_blended_effect"]
    overstatement_abs = e_naive - planted_mean_all
    overstatement_pct = (overstatement_abs / planted_mean_all) * 100.0 if planted_mean_all else float("nan")
    met = overstatement_pct >= 50.0

    # Three one-flaw-off counterfactuals, each changing exactly one of the
    # naive arm's three planted flaws while holding the other two at the
    # naive arm's actual settings.
    all_learner_ids = sorted(answer_key.keys(), key=lambda lid: int(lid[1:]))

    no_selection = run_instruments.run_naive(
        admin, responses,
        {"volunteer_learner_ids": all_learner_ids, "self_report_weight": weight},
        mode=mode, briefs=briefs, quiet=True,
    )
    e_no_selection = no_selection["summary"]["cohort_mean_blended_effect"]

    no_practice_records = scoring.compute_pre_post_effect(
        volunteer_ids, admin, responses,
        form_assignment="counterbalanced", self_report_weight=weight, mode=mode, briefs=briefs,
    )
    e_no_practice = statistics.fmean(r["blended_effect"] for r in no_practice_records)

    no_selfreport_records = scoring.compute_pre_post_effect(
        volunteer_ids, admin, responses,
        form_assignment="same_form_repeated", self_report_weight=0.0, mode=mode, briefs=briefs,
    )
    e_no_selfreport = statistics.fmean(r["blended_effect"] for r in no_selfreport_records)

    share_selection = e_naive - e_no_selection
    share_practice = e_naive - e_no_practice
    share_selfreport = e_naive - e_no_selfreport
    total_overstatement = e_naive - planted_mean_all
    sum_of_shares = share_selection + share_practice + share_selfreport
    residual = total_overstatement - sum_of_shares

    def pct_of_total(share):
        return (share / total_overstatement) * 100.0 if total_overstatement else float("nan")

    return {
        "expectation": 4,
        "description": "Naive evaluation overstates the cohort effect by >= 50%, decomposed into its three flaws.",
        "planted_cohort_mean_delta_all_40": planted_mean_all,
        "planted_cohort_mean_delta_volunteers_only": planted_mean_volunteers,
        "naive_measured_effect": e_naive,
        "overstatement_abs": overstatement_abs,
        "overstatement_pct": overstatement_pct,
        "met": met,
        "decomposition": {
            "note": (
                "Each counterfactual switches OFF exactly one of the naive arm's "
                "three flaws, holding the other two at the naive arm's actual "
                "settings. 'share' = naive's measured effect minus that "
                "counterfactual's effect -- how much the estimate falls when just "
                "that flaw is fixed. Shares need not sum exactly to the total "
                "overstatement; the residual is the flaws' interaction, reported "
                "rather than hidden."
            ),
            "e_naive_full": e_naive,
            "e_no_selection_full_cohort_n40": e_no_selection,
            "e_no_practice_counterbalanced_forms": e_no_practice,
            "e_no_selfreport_performance_only": e_no_selfreport,
            "share_selection_abs": share_selection,
            "share_practice_effect_abs": share_practice,
            "share_self_report_weighting_abs": share_selfreport,
            "share_selection_pct_of_overstatement": pct_of_total(share_selection),
            "share_practice_effect_pct_of_overstatement": pct_of_total(share_practice),
            "share_self_report_weighting_pct_of_overstatement": pct_of_total(share_selfreport),
            "residual_abs": residual,
            "residual_pct_of_overstatement": pct_of_total(residual),
        },
    }


# ---------------------------------------------------------------------------
# Expectation 5 -- form equivalence (pre-scores across forms)
# ---------------------------------------------------------------------------
def check_expectation_5(honest_run):
    a_pre_scores = [r["performance_pre"] for r in honest_run["learners"] if r["pre_form_used"] == "A"]
    b_pre_scores = [r["performance_pre"] for r in honest_run["learners"] if r["pre_form_used"] == "B"]
    mean_a = statistics.fmean(a_pre_scores)
    mean_b = statistics.fmean(b_pre_scores)
    diff = mean_a - mean_b
    tolerance = config.FORM_DIFFICULTY_TOLERANCE
    met = abs(diff) <= tolerance

    return {
        "expectation": 5,
        "description": "Form equivalence holds: pre-score difference between forms within tolerance.",
        "n_form_a_pre": len(a_pre_scores),
        "n_form_b_pre": len(b_pre_scores),
        "mean_pre_score_form_a": mean_a,
        "mean_pre_score_form_b": mean_b,
        "diff_abs": diff,
        "tolerance": tolerance,
        "met": met,
    }


# ---------------------------------------------------------------------------
# Expectation 6 -- the designed blind spot (fast forgetters)
# ---------------------------------------------------------------------------
FAST_FORGETTER_BLINDNESS_BAND = 1.0  # in units of the comparison group's own sd
FAST_FORGETTER_DECAY_RATIO_THRESHOLD = 0.60  # 8wk delta must retain <= 60% of the post delta to count as "visible decay"


def check_expectation_6(honest_run, answer_key, admin, responses, mode="scored", briefs=None):
    fast_forgetter_ids = sorted(
        (lid for lid, row in answer_key.items() if row["archetype"] == "fast_forgetter"),
        key=lambda x: int(x[1:]),
    )
    genuine_improver_ids = sorted(
        (lid for lid, row in answer_key.items() if row["archetype"] in ("strong_improver", "modest_improver")),
        key=lambda x: int(x[1:]),
    )

    by_learner = {r["learner_id"]: r for r in honest_run["learners"]}
    ff_post_deltas = [by_learner[lid]["delta_hat"] for lid in fast_forgetter_ids]
    gi_post_deltas = [by_learner[lid]["delta_hat"] for lid in genuine_improver_ids]
    gi_mean = statistics.fmean(gi_post_deltas)
    gi_sd = statistics.stdev(gi_post_deltas)
    ff_mean_post = statistics.fmean(ff_post_deltas)

    # Sub-check A: at the standard post occasion, are fast forgetters
    # indistinguishable from genuine improvers (within one improver-group sd
    # of the improver mean)? This is the claimed blindness.
    blind_at_post = abs(ff_mean_post - gi_mean) <= FAST_FORGETTER_BLINDNESS_BAND * gi_sd

    # Sub-check B: using the +8-week response data (no named instrument
    # reads this as sold), recompute delta using post_occasion="follow_up_8wk"
    # with the SAME counterbalanced, no-practice-effect administration logic
    # the honest instrument uses -- this reuses run_honest's exact
    # arithmetic via compute_pre_post_effect, just pointed at the later
    # occasion.
    all_ids = sorted(answer_key.keys(), key=lambda lid: int(lid[1:]))
    records_8wk = scoring.compute_pre_post_effect(
        all_ids, admin, responses,
        form_assignment="counterbalanced", self_report_weight=0.0, mode=mode, briefs=briefs,
        post_occasion="follow_up_8wk",
    )
    by_learner_8wk = {r["learner_id"]: r for r in records_8wk}

    ff_8wk_deltas = [by_learner_8wk[lid]["performance_delta"] for lid in fast_forgetter_ids]
    gi_8wk_deltas = [by_learner_8wk[lid]["performance_delta"] for lid in genuine_improver_ids]
    ff_mean_8wk = statistics.fmean(ff_8wk_deltas)
    gi_mean_8wk = statistics.fmean(gi_8wk_deltas)

    ff_retention_ratio = ff_mean_8wk / ff_mean_post if ff_mean_post else float("nan")
    gi_retention_ratio = gi_mean_8wk / gi_mean if gi_mean else float("nan")
    visible_decay_at_8wk = ff_retention_ratio <= FAST_FORGETTER_DECAY_RATIO_THRESHOLD

    met = blind_at_post and visible_decay_at_8wk

    per_learner_detail = []
    for lid in fast_forgetter_ids:
        per_learner_detail.append({
            "learner_id": lid,
            "name": answer_key[lid]["name"],
            "delta_hat_post": by_learner[lid]["delta_hat"],
            "delta_hat_8wk": by_learner_8wk[lid]["performance_delta"],
            "planted_delta_post": answer_key[lid]["delta_post"],
            "planted_retention_factor": answer_key[lid]["retention_factor"],
        })

    return {
        "expectation": 6,
        "description": (
            "The designed blind spot: standard pre/post cannot see the fast "
            "forgetters' decay; the +8-week data (not read by any named "
            "instrument as sold) reveals it."
        ),
        "fast_forgetter_ids": fast_forgetter_ids,
        "genuine_improver_ids_n": len(genuine_improver_ids),
        "mean_delta_hat_post_fast_forgetters": ff_mean_post,
        "mean_delta_hat_post_genuine_improvers": gi_mean,
        "sd_delta_hat_post_genuine_improvers": gi_sd,
        "blind_at_post": blind_at_post,
        "blindness_band_sd_multiple": FAST_FORGETTER_BLINDNESS_BAND,
        "mean_delta_hat_8wk_fast_forgetters": ff_mean_8wk,
        "mean_delta_hat_8wk_genuine_improvers": gi_mean_8wk,
        "fast_forgetter_8wk_retention_ratio": ff_retention_ratio,
        "genuine_improver_8wk_retention_ratio": gi_retention_ratio,
        "decay_ratio_threshold": FAST_FORGETTER_DECAY_RATIO_THRESHOLD,
        "visible_decay_at_8wk": visible_decay_at_8wk,
        "met": met,
        "per_fast_forgetter_detail": per_learner_detail,
    }


# ---------------------------------------------------------------------------
# Running all six checks under a given scoring mode -- used once for the
# primary pass (mode="scored") and once for the robustness pass
# (mode="perfect"), so the two are guaranteed to be computed by identical
# code, differing only in which scoring layer feeds them.
# ---------------------------------------------------------------------------
def run_all_expectations(mode, admin, responses, briefs, answer_key, naive_config, honest_run=None, feedback_run=None, naive_run=None):
    """
    If honest_run/feedback_run/naive_run are given (the primary pass,
    already persisted by run_instruments.py), reuse them rather than
    recomputing -- guarantees the report's primary-pass numbers are
    literally the same objects run_instruments.py wrote to disk. Otherwise
    (the robustness pass) compute all three fresh in the given mode.
    """
    if honest_run is None:
        honest_run = run_instruments.run_honest(admin, responses, mode=mode, briefs=briefs, quiet=True)
    if feedback_run is None:
        feedback_run = run_instruments.run_feedback_sheet(admin, responses)  # scoring-mode invariant
    if naive_run is None:
        naive_run = run_instruments.run_naive(admin, responses, naive_config, mode=mode, briefs=briefs, quiet=True)

    exp1 = check_expectation_1(honest_run, answer_key)
    exp2 = check_expectation_2(honest_run, answer_key)
    exp3 = check_expectation_3(feedback_run, answer_key)
    exp4 = check_expectation_4(naive_run, answer_key, admin, responses, naive_config, mode=mode, briefs=briefs)
    exp5 = check_expectation_5(honest_run)
    exp6 = check_expectation_6(honest_run, answer_key, admin, responses, mode=mode, briefs=briefs)

    return {
        "mode": mode,
        "honest_run": honest_run,
        "feedback_run": feedback_run,
        "naive_run": naive_run,
        "expectations": {1: exp1, 2: exp2, 3: exp3, 4: exp4, 5: exp5, 6: exp6},
    }


EXPECTATION_SHORT_LABELS = {
    1: "Honest instrument recovers cohort mean effect (+/-0.10 sigma)",
    2: "Honest instrument flags >=6/7 confident non-learners",
    3: "Feedback sheet r < 0.30 vs planted delta",
    4: "Naive evaluation overstates cohort effect by >=50%",
    5: "Form equivalence (pre-score diff within tolerance)",
    6: "Designed blind spot: blind at post, visible at +8wk",
}


def build_robustness_table(primary_pass, perfect_pass):
    rows = []
    for exp_num in range(1, 7):
        p = primary_pass["expectations"][exp_num]
        q = perfect_pass["expectations"][exp_num]
        rows.append({
            "expectation": exp_num,
            "label": EXPECTATION_SHORT_LABELS[exp_num],
            "met_scored_primary": p["met"],
            "met_perfect_sensitivity": q["met"],
            "flipped": p["met"] != q["met"],
        })
    return rows


# ---------------------------------------------------------------------------
# Report writing
# ---------------------------------------------------------------------------
def fmt(x, nd=4):
    if isinstance(x, bool):
        return str(x)
    if isinstance(x, float):
        if x != x:  # NaN
            return "n/a"
        return f"{x:.{nd}f}"
    return str(x)


def verdict_word(met):
    return "MET" if met else "NOT MET"


def write_report(primary_pass, perfect_pass, robustness_rows, answer_key, naive_config, out_path):
    lines = []
    lines.append("# 09 Training Outcomes -- Phase 5 marking report")
    lines.append("")
    lines.append(
        "Generated by `code/mark.py`, the sole reader of `data/answer_key/` in this "
        "project. Deterministic given the existing corpus; a re-run produces a "
        "byte-identical `marks.json`. Every number below is frozen as it ran -- no "
        "expectation is retuned after seeing its result."
    )
    lines.append("")
    lines.append(
        "**Primary pass** scores response TEXT with `code/rubric_detectors.py` "
        "(the realistic, noisy layer), whose item-level agreement against the "
        "response briefs' intended scores is measured at **94.23%** "
        "(`data/analysis/scorer_calibration.md`) -- the closest analogue this case "
        "has to a human rater's reliability. **Robustness pass** repeats every "
        "check on the response briefs' own \"perfect\" intended scores instead, as "
        "a sensitivity check: would any verdict flip under a perfectly reliable "
        "rater? See the robustness table below."
    )
    lines.append("")

    # -------------------------------------------------------------------
    # Verdict table
    # -------------------------------------------------------------------
    lines.append("## The six pre-registered verdicts")
    lines.append("")
    lines.append("| # | Expectation | Verdict | Key numbers |")
    lines.append("|---|---|---|---|")

    e1 = primary_pass["expectations"][1]
    lines.append(
        f"| 1 | Recovers cohort mean effect within +/-0.10 sigma | **{verdict_word(e1['met'])}** | "
        f"planted mean delta {fmt(e1['planted_cohort_mean_delta'])}, measured delta-hat "
        f"{fmt(e1['measured_cohort_mean_delta_hat'])}, gap {fmt(e1['gap'])}, "
        f"tolerance +/-{fmt(e1['tolerance_abs'])} (0.10 x sigma={fmt(e1['planted_cohort_sd_delta'])}) |"
    )
    e2 = primary_pass["expectations"][2]
    lines.append(
        f"| 2 | Flags >= 6/7 confident non-learners | **{verdict_word(e2['met'])}** | "
        f"caught {e2['n_caught']}/{e2['n_planted_confident_non_learners']} "
        f"({', '.join(e2['caught_ids'])}); missed {e2['missed_ids'] or 'none'}; "
        f"{len(e2['false_positive_ids'])} false positive(s) ({', '.join(e2['false_positive_ids']) or 'none'}) |"
    )
    e3 = primary_pass["expectations"][3]
    lines.append(
        f"| 3 | Feedback sheet r < 0.30 vs planted delta | **{verdict_word(e3['met'])}** | "
        f"r(confidence_post, delta) = {fmt(e3['r_confidence_post_vs_planted_delta'])}; "
        f"r(satisfaction_post, delta) = {fmt(e3['r_satisfaction_post_vs_planted_delta'])} |"
    )
    e4 = primary_pass["expectations"][4]
    lines.append(
        f"| 4 | Naive overstates cohort effect by >= 50% | **{verdict_word(e4['met'])}** | "
        f"naive effect {fmt(e4['naive_measured_effect'])} vs planted mean "
        f"{fmt(e4['planted_cohort_mean_delta_all_40'])} -- overstatement "
        f"{fmt(e4['overstatement_pct'], 1)}% |"
    )
    e5 = primary_pass["expectations"][5]
    lines.append(
        f"| 5 | Form equivalence within tolerance | **{verdict_word(e5['met'])}** | "
        f"mean pre-score A {fmt(e5['mean_pre_score_form_a'])} (n={e5['n_form_a_pre']}), "
        f"B {fmt(e5['mean_pre_score_form_b'])} (n={e5['n_form_b_pre']}), diff "
        f"{fmt(e5['diff_abs'])}, tolerance +/-{fmt(e5['tolerance'])} |"
    )
    e6 = primary_pass["expectations"][6]
    lines.append(
        f"| 6 | Designed blind spot demonstrated | **{verdict_word(e6['met'])}** | "
        f"post delta-hat: forgetters {fmt(e6['mean_delta_hat_post_fast_forgetters'])} vs "
        f"improvers {fmt(e6['mean_delta_hat_post_genuine_improvers'])} (blind={e6['blind_at_post']}); "
        f"8wk retention ratio: forgetters {fmt(e6['fast_forgetter_8wk_retention_ratio'], 2)} vs "
        f"improvers {fmt(e6['genuine_improver_8wk_retention_ratio'], 2)} (visible decay={e6['visible_decay_at_8wk']}) |"
    )
    lines.append("")

    # -------------------------------------------------------------------
    # Per-instrument tables
    # -------------------------------------------------------------------
    lines.append("## The honest instrument -- per-learner delta-hat and divergence")
    lines.append("")
    lines.append("| Learner | Archetype | Planted delta | delta-hat | Confidence gain (1-7) | Divergence z | Flagged |")
    lines.append("|---|---|---|---|---|---|---|")
    honest_by_id = {r["learner_id"]: r for r in primary_pass["honest_run"]["learners"]}
    for lid in sorted(answer_key, key=lambda x: int(x[1:])):
        r = honest_by_id[lid]
        ak = answer_key[lid]
        conf_gain = r["confidence_post"] - r["confidence_pre"]
        lines.append(
            f"| {lid} | {ak['archetype_label']} | {fmt(ak['delta_post'])} | {fmt(r['delta_hat'])} | "
            f"{fmt(conf_gain, 2)} | {fmt(r['divergence_z'], 2)} | {'YES' if r['flagged_confident_non_learner'] else ''} |"
        )
    lines.append("")

    lines.append("## The feedback sheet -- per-learner self-report vs planted delta")
    lines.append("")
    lines.append("| Learner | Archetype | Planted delta | Confidence post (1-7) | Satisfaction post (1-7) |")
    lines.append("|---|---|---|---|---|")
    feedback_by_id = {r["learner_id"]: r for r in primary_pass["feedback_run"]["learners"]}
    for lid in sorted(answer_key, key=lambda x: int(x[1:])):
        r = feedback_by_id[lid]
        ak = answer_key[lid]
        lines.append(
            f"| {lid} | {ak['archetype_label']} | {fmt(ak['delta_post'])} | {fmt(r['confidence_post'], 2)} | "
            f"{fmt(r['satisfaction_post'], 2)} |"
        )
    lines.append("")

    lines.append("## The naive evaluation -- volunteer subset, blended effect")
    lines.append("")
    lines.append("| Learner | Archetype | Planted delta | Performance delta (repeated form) | Confidence delta (scaled) | Blended effect |")
    lines.append("|---|---|---|---|---|---|")
    naive_by_id = {r["learner_id"]: r for r in primary_pass["naive_run"]["learners"]}
    for lid in naive_config["volunteer_learner_ids"]:
        r = naive_by_id[lid]
        ak = answer_key[lid]
        lines.append(
            f"| {lid} | {ak['archetype_label']} | {fmt(ak['delta_post'])} | {fmt(r['performance_delta'])} | "
            f"{fmt(r['confidence_delta_scaled'])} | {fmt(r['blended_effect'])} |"
        )
    lines.append("")

    # -------------------------------------------------------------------
    # Decomposition
    # -------------------------------------------------------------------
    lines.append("## The naive arm's overstatement, decomposed")
    lines.append("")
    d = e4["decomposition"]
    lines.append(
        f"Naive measured effect (volunteers, repeated form, self-report weight "
        f"{naive_config['self_report_weight']}): **{fmt(d['e_naive_full'])}**. "
        f"Planted truth, full cohort: **{fmt(e4['planted_cohort_mean_delta_all_40'])}**. "
        f"Planted truth, volunteers only: {fmt(e4['planted_cohort_mean_delta_volunteers_only'])}. "
        f"Total overstatement: **{fmt(e4['overstatement_pct'], 1)}%**."
    )
    lines.append("")
    lines.append("| Flaw switched off | Counterfactual effect | Share of overstatement (abs) | Share (% of total) |")
    lines.append("|---|---|---|---|")
    lines.append(
        f"| Selection (volunteers -> full cohort, n=40) | {fmt(d['e_no_selection_full_cohort_n40'])} | "
        f"{fmt(d['share_selection_abs'])} | {fmt(d['share_selection_pct_of_overstatement'], 1)}% |"
    )
    lines.append(
        f"| Practice effect (repeated form -> counterbalanced) | {fmt(d['e_no_practice_counterbalanced_forms'])} | "
        f"{fmt(d['share_practice_effect_abs'])} | {fmt(d['share_practice_effect_pct_of_overstatement'], 1)}% |"
    )
    lines.append(
        f"| Self-report weighting (blended -> performance only) | {fmt(d['e_no_selfreport_performance_only'])} | "
        f"{fmt(d['share_self_report_weighting_abs'])} | {fmt(d['share_self_report_weighting_pct_of_overstatement'], 1)}% |"
    )
    lines.append(
        f"| *(interaction / residual, not attributable to a single flaw)* | -- | {fmt(d['residual_abs'])} | "
        f"{fmt(d['residual_pct_of_overstatement'], 1)}% |"
    )
    lines.append("")
    lines.append(d["note"])
    lines.append("")

    # -------------------------------------------------------------------
    # Fast forgetter detail
    # -------------------------------------------------------------------
    lines.append("## The fast-forgetter demonstration")
    lines.append("")
    lines.append(
        f"At the standard post occasion, the 3 fast forgetters' mean delta-hat "
        f"({fmt(e6['mean_delta_hat_post_fast_forgetters'])}) sits "
        f"{'within' if e6['blind_at_post'] else 'OUTSIDE'} "
        f"{e6['blindness_band_sd_multiple']} sd of the genuine improvers' mean "
        f"({fmt(e6['mean_delta_hat_post_genuine_improvers'])}, sd {fmt(e6['sd_delta_hat_post_genuine_improvers'])}) "
        f"-- the standard instrument, as sold, {'cannot' if e6['blind_at_post'] else 'CAN'} tell them apart from genuine learning."
    )
    lines.append("")
    lines.append(
        f"At +8 weeks (not read by any named instrument as sold), the fast forgetters retain "
        f"{fmt(e6['fast_forgetter_8wk_retention_ratio'] * 100, 1)}% of their post-training gain, "
        f"against {fmt(e6['genuine_improver_8wk_retention_ratio'] * 100, 1)}% for genuine improvers -- "
        f"{'a visible, decisive gap' if e6['visible_decay_at_8wk'] else 'NOT a clearly visible gap (reported as-is)'}."
    )
    lines.append("")
    lines.append("| Learner | delta-hat (post) | delta-hat (+8wk) | Planted delta_post | Planted retention factor |")
    lines.append("|---|---|---|---|---|")
    for row in e6["per_fast_forgetter_detail"]:
        lines.append(
            f"| {row['learner_id']} ({row['name']}) | {fmt(row['delta_hat_post'])} | {fmt(row['delta_hat_8wk'])} | "
            f"{fmt(row['planted_delta_post'])} | {fmt(row['planted_retention_factor'])} |"
        )
    lines.append("")

    # -------------------------------------------------------------------
    # Robustness table
    # -------------------------------------------------------------------
    lines.append("## Robustness: primary (scored) vs perfect-scoring sensitivity pass")
    lines.append("")
    lines.append(
        "Every verdict above, recomputed on the response briefs' own \"perfect\" "
        "intended scores instead of `rubric_detectors.py`'s text-based scoring -- "
        "the sensitivity check for whether the scorer's measured 94.23% item-level "
        "reliability (`data/analysis/scorer_calibration.md`) is good enough to trust "
        "any of the six verdicts above. The feedback sheet never scores response "
        "text at all (it is pure self-report), so expectation 3 cannot flip by "
        "construction -- included for completeness, not because it was at risk."
    )
    lines.append("")
    lines.append("| # | Expectation | Primary (scored) | Perfect-scoring | Flipped? |")
    lines.append("|---|---|---|---|---|")
    any_flip = False
    for row in robustness_rows:
        if row["flipped"]:
            any_flip = True
        lines.append(
            f"| {row['expectation']} | {row['label']} | {verdict_word(row['met_scored_primary'])} | "
            f"{verdict_word(row['met_perfect_sensitivity'])} | {'**YES**' if row['flipped'] else 'no'} |"
        )
    lines.append("")
    lines.append(
        f"**{'One or more verdicts flip' if any_flip else 'No verdict flips'} between the primary "
        f"scored-text pass and the perfect-scoring sensitivity pass.**"
    )
    lines.append("")

    # -------------------------------------------------------------------
    # Marking-quality notes
    # -------------------------------------------------------------------
    lines.append("## Marking-quality notes")
    lines.append("")
    lines.append(
        "- The primary pass's scorer (`code/rubric_detectors.py`) is calibrated at "
        "94.23% item-level agreement against the response briefs' intended scores "
        "(9,046/9,600 items; see `data/analysis/scorer_calibration.md`), below the "
        "97% design target and reported honestly rather than tuned to clear it. "
        "The residual disagreement is overwhelmingly detector recall/precision "
        "limits on paraphrase, not response infidelity (the 8 confirmed genuine "
        "content/brief contradictions from the cross-batch audit were already "
        "regenerated before this marking run)."
    )
    lines.append(
        "- This is the closest analogue this case has to a human rater's "
        "reliability: a real marker reading free text would also disagree with "
        "themselves or a co-marker some fraction of the time. Treat the primary "
        "pass's numbers as measured through that noise, not as ground truth -- "
        "the robustness table above is exactly the check for whether that noise "
        "matters to the conclusions."
    )
    lines.append(
        "- The confident-non-learner detector (expectation 2) is a single frozen "
        "z-score threshold (divergence z > 1.0) decided before this run and never "
        "adjusted afterward, per the pre-registration's no-retuning rule."
    )
    lines.append(
        "- The naive-arm decomposition's three shares are computed by one-flaw-off "
        "counterfactuals and do not require summing to exactly 100% of the total "
        "overstatement; the residual row above is the flaws' interaction, reported "
        "rather than absorbed into any single flaw's share."
    )
    lines.append("")

    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("09 Training Outcomes -- Phase 5, step 2: marking (code/mark.py)")
    print(f"Reading the answer key from {ANSWER_KEY_DIR} (sole reader in this project)...")

    try:
        answer_key = load_answer_key()
        admin = scoring.load_admin()
        responses = scoring.load_responses()
        briefs = scoring.load_briefs()
        naive_config = run_instruments.load_instrument_config("naive")

        honest_run = load_instrument_run("honest")
        feedback_run = load_instrument_run("feedback_sheet")
        naive_run = load_instrument_run("naive")
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"  {len(answer_key)} learners in the answer key, "
          f"{len(responses)} response files, {len(briefs)} response briefs.")

    print("\nRunning the primary pass (scored text, mode='scored')...")
    primary_pass = run_all_expectations(
        "scored", admin, responses, None, answer_key, naive_config,
        honest_run=honest_run, feedback_run=feedback_run, naive_run=naive_run,
    )

    print("Running the robustness pass (perfect intended scores, mode='perfect')...")
    perfect_pass = run_all_expectations(
        "perfect", admin, responses, briefs, answer_key, naive_config,
    )

    robustness_rows = build_robustness_table(primary_pass, perfect_pass)

    print("\n--- The six pre-registered verdicts (primary pass) ---")
    for exp_num in range(1, 7):
        e = primary_pass["expectations"][exp_num]
        print(f"  {exp_num}. {EXPECTATION_SHORT_LABELS[exp_num]}: {verdict_word(e['met'])}")

    print("\n--- Robustness (perfect-scoring sensitivity) ---")
    for row in robustness_rows:
        flag = " <-- FLIPPED" if row["flipped"] else ""
        print(f"  {row['expectation']}. {row['label']}: scored={verdict_word(row['met_scored_primary'])} "
              f"perfect={verdict_word(row['met_perfect_sensitivity'])}{flag}")

    print(f"\nWriting {REPORT_PATH}...")
    write_report(primary_pass, perfect_pass, robustness_rows, answer_key, naive_config, REPORT_PATH)
    print(f"  wrote {REPORT_PATH}")

    print(f"Writing {MARKS_PATH}...")
    marks = {
        "primary_pass": primary_pass,
        "perfect_scoring_robustness_pass": perfect_pass,
        "robustness_table": robustness_rows,
    }
    MARKS_PATH.write_text(json.dumps(marks, indent=2, ensure_ascii=False, sort_keys=False), encoding="utf-8")
    print(f"  wrote {MARKS_PATH}")

    print("\nDone.")


if __name__ == "__main__":
    main()
