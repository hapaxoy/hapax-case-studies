"""build_data.py -- assembles interactive/_data.json for the training-outcomes
interactive page, then inlines it into _template.html to produce
training-outcomes.html.

Follows the established portfolio pattern (07 Tenders' interactive/build_data.py
+ _template.html -> tender-workflow.html): a deterministic, re-runnable Python
build step assembles ONE JSON blob from the project's real data directories
under data/, and a hand-written template with an embedded
<script type="application/json" id="hpx-data"> renders it client-side. No
number on the page is invented here -- every number traces to
data/analysis/marks.json (the sole output of code/mark.py, the only script
permitted to open data/answer_key/), data/cohort/L*.json, data/responses/,
or code/config.py. Every callout sentence traces to
writeup/training_outcomes_case_study.md and is sliced out verbatim, never
paraphrased or retyped by hand (quote_paragraph() below extracts the whole
markdown paragraph containing a chosen ASCII anchor, so the extracted text --
including its curly quotes, en dashes and minus signs -- always matches the
source file byte-for-byte; this script never types a typographic character
into a marker itself).

Run from this directory or the project root:
    python interactive/build_data.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
DATA_DIR = PROJECT_ROOT / "data"
CODE_DIR = PROJECT_ROOT / "code"

sys.path.insert(0, str(CODE_DIR))
import config  # noqa: E402 -- the project's own config module (TASK_PAIRS, ARCHETYPES)

MARKS_PATH = DATA_DIR / "analysis" / "marks.json"
COHORT_DIR = DATA_DIR / "cohort"
RESPONSES_DIR = DATA_DIR / "responses"
WRITEUP_PATH = PROJECT_ROOT / "writeup" / "training_outcomes_case_study.md"
OUT_JSON = HERE / "_data.json"
TEMPLATE_PATH = HERE / "_template.html"
OUT_HTML = HERE / "training-outcomes.html"

# The three illustrative task indices shown per learner in the cohort view
# (2-3 illustrative tasks per learner rather than all ten). Chosen because the canonical writeup itself quotes exactly these
# three exhibits verbatim: task 1 (Markus Hirvonen's fast-forgetter answer),
# task 4 (Tiina Rasanen's error-spotting answer), task 9 (Tiina Rasanen's
# verification-habit answer, the "Same as before really" exhibit) -- so the
# fixed selection is not an arbitrary editorial pick, it is the set the
# writeup already leans on.
ILLUSTRATIVE_TASK_INDICES = [1, 4, 9]

CATEGORY_LABELS = {
    "instruction_reliability": "Instruction reliability",
    "error_spotting": "Error spotting",
    "checkability_judgment": "Checkability judgment",
    "data_handling_policy": "Data handling policy",
    "verification_habit": "Verification habit",
}


def log(message: str) -> None:
    print(f"[build_data] {message}")


def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"required data file missing: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"required data file missing: {path}")
    return path.read_text(encoding="utf-8")


def quote_paragraph(source_text: str, anchor: str, label: str) -> str:
    """Extract the whole markdown paragraph (blank-line to blank-line) that
    contains the ASCII anchor substring, verbatim. This is the guarantee that
    every callout on the page is byte-for-byte what the writeup says
    (typographic apostrophes, en dashes, curly quotes and minus signs all
    included) -- the anchor itself is chosen to be a plain-ASCII, apostrophe-
    free substring so this script never has to retype a special character to
    find its target; the special characters ride along in the slice.
    """
    idx = source_text.find(anchor)
    if idx == -1:
        raise ValueError(f"quote '{label}': anchor not found: {anchor!r}")
    start = source_text.rfind("\n\n", 0, idx)
    start = 0 if start == -1 else start + 2
    end = source_text.find("\n\n", idx)
    end = len(source_text) if end == -1 else end
    para = source_text[start:end].strip()
    # Strip markdown emphasis markers -- displayed as plain text, not
    # rendered markdown, so "**bold**" / "*italic*" markers are noise.
    if para.startswith("*") and para.endswith("*") and not para.startswith("**"):
        para = para[1:-1]
    para = para.replace("**", "")
    return para


def build_quotes(writeup_text: str) -> dict:
    log("slicing verbatim callout paragraphs from the writeup...")
    q = {}
    q["title"] = "Forty learners, three instruments"
    q["byline"] = quote_paragraph(writeup_text, "the forty learners, the two-day programme", "byline")
    q["lede"] = quote_paragraph(writeup_text, "The evidence the industry offers for training", "lede")
    q["cohort_independence"] = quote_paragraph(writeup_text, "cohort-wide correlation between planted shift", "cohort_independence")
    q["confident_group_frame"] = quote_paragraph(writeup_text, "deliberately the largest problem group", "confident_group_frame")
    q["honest_desc"] = quote_paragraph(writeup_text, "counterbalanced so that no learner answers the same questions twice", "honest_desc")
    q["feedback_desc"] = quote_paragraph(writeup_text, "post-only self-reported satisfaction and self-assessed improvement", "feedback_desc")
    q["naive_desc"] = quote_paragraph(writeup_text, "assembled from three documented bad practices", "naive_desc")
    q["corpus_note"] = quote_paragraph(writeup_text, "All three run on the same corpus", "corpus_note")
    q["cohort_recovered"] = quote_paragraph(writeup_text, "gap of 0.0100 inside a tolerance of 0.0124", "cohort_recovered")
    q["six_flagged"] = quote_paragraph(writeup_text, "single frozen statistic", "six_flagged")
    q["l23_exhibit"] = quote_paragraph(writeup_text, "shows the pattern.", "l23_exhibit")
    q["feedback_r_finding"] = quote_paragraph(writeup_text, "carries almost no information about whether anyone learned anything", "feedback_r_finding")
    q["naive_overstate_finding"] = quote_paragraph(writeup_text, "pre-registration asked for 50%", "naive_overstate_finding")
    q["naive_decomp_note"] = quote_paragraph(writeup_text, "Two things there were not anticipated", "naive_decomp_note")
    q["form_equivalence_finding"] = quote_paragraph(writeup_text, "Form equivalence failed", "form_equivalence_finding")
    q["scorer_reliability_intro"] = quote_paragraph(writeup_text, "9,046 of 9,600 item checks", "scorer_reliability_intro")
    q["robustness_flip_finding"] = quote_paragraph(writeup_text, "Two of six verdicts flip, in opposite directions", "robustness_flip_finding")
    q["feedback_immune_dry_remark"] = quote_paragraph(writeup_text, "immunity to rater error bought by measuring nothing", "feedback_immune_dry_remark")
    q["rater_reliability_conclusion"] = quote_paragraph(writeup_text, "Neither pass is the true answer", "rater_reliability_conclusion")
    q["real_engagement_three_things"] = quote_paragraph(writeup_text, "For a real engagement this settles three things", "real_engagement_three_things")
    q["forgetters_intro"] = quote_paragraph(writeup_text, "built to lose most of what they gained within two months", "forgetters_intro")
    q["forgetters_invisible"] = quote_paragraph(writeup_text, "average a measured gain of 0.2667", "forgetters_invisible")
    q["forgetters_8wk"] = quote_paragraph(writeup_text, "no named instrument reads it", "forgetters_8wk")
    q["markus_exhibit"] = quote_paragraph(writeup_text, "show the decay in plain text", "markus_exhibit")
    q["followup_argument"] = quote_paragraph(writeup_text, "published argument for the follow-up", "followup_argument")
    q["what_transfers"] = quote_paragraph(writeup_text, "The instrument transfers, and it is published in full", "what_transfers")
    q["what_doesnt_transfer"] = quote_paragraph(writeup_text, "The numbers do not transfer.", "what_doesnt_transfer")
    q["closing"] = quote_paragraph(writeup_text, "the entire reason for measuring it", "closing")
    log(f"  {len(q)} verbatim quotes extracted")
    return q


# ---------------------------------------------------------------------------
# Illustrative tasks (code/config.py TASK_PAIRS, indices 1, 4, 9)
# ---------------------------------------------------------------------------

def build_illustrative_tasks() -> list[dict]:
    out = []
    by_index = {p["index"]: p for p in config.TASK_PAIRS}
    for i in ILLUSTRATIVE_TASK_INDICES:
        p = by_index[i]
        out.append({
            "index": i,
            "category": p["category"],
            "category_label": CATEGORY_LABELS[p["category"]],
            "prompt_a": p["prompt_a"],
            "prompt_b": p["prompt_b"],
        })
    return out


# ---------------------------------------------------------------------------
# Responses -- load only the three illustrative tasks' text, per (learner,
# form, occasion), to keep the page's embedded data small.
# ---------------------------------------------------------------------------

def load_response_tasks(learner_id: str, form: str, occasion: str) -> dict:
    path = RESPONSES_DIR / f"{learner_id}_form{form}_{occasion}.json"
    resp = load_json(path)
    task_prefix = form
    wanted_ids = {f"{task_prefix}{i}" for i in ILLUSTRATIVE_TASK_INDICES}
    texts = {}
    for ans in resp["answers"]:
        if ans["task_id"] in wanted_ids:
            index = int(ans["task_id"][len(task_prefix):])
            texts[str(index)] = ans["text"]
    if len(texts) != len(ILLUSTRATIVE_TASK_INDICES):
        raise ValueError(f"{path}: expected {ILLUSTRATIVE_TASK_INDICES} tasks, found {sorted(texts.keys())}")
    return {"form": form, "tasks": texts}


# ---------------------------------------------------------------------------
# Cohort -- merge data/cohort/L*.json (planted profile) with marks.json's
# per-learner instrument verdicts (honest / feedback / naive runs).
# ---------------------------------------------------------------------------

def build_cohort(marks: dict) -> list[dict]:
    log("assembling the 40-learner cohort (profile + instrument verdicts + illustrative responses)...")
    primary = marks["primary_pass"]
    honest_by_id = {r["learner_id"]: r for r in primary["honest_run"]["learners"]}
    feedback_by_id = {r["learner_id"]: r for r in primary["feedback_run"]["learners"]}
    naive_by_id = {r["learner_id"]: r for r in primary["naive_run"]["learners"]}

    cohort_files = sorted(COHORT_DIR.glob("L*.json"))
    out = []
    for path in cohort_files:
        profile = load_json(path)
        lid = profile["learner_id"]
        is_fast_forgetter = profile["archetype"] == "fast_forgetter"

        responses = {
            "pre": load_response_tasks(lid, profile["pre_form"], "pre"),
            "post": load_response_tasks(lid, profile["post_form"], "post"),
        }
        if is_fast_forgetter:
            responses["wk8"] = load_response_tasks(lid, profile["post_form"], "follow_up_8wk")

        honest = honest_by_id[lid]
        feedback = feedback_by_id[lid]
        naive = naive_by_id.get(lid)  # None if not a naive-arm volunteer

        out.append({
            "learner_id": lid,
            "name": profile["name"],
            "role": profile["role"],
            "archetype": profile["archetype"],
            "archetype_label": profile["archetype_label"],
            "pre_form": profile["pre_form"],
            "post_form": profile["post_form"],
            "volunteer": profile["volunteer"],
            "planted": {
                "baseline_ability": profile["baseline_ability"],
                "delta_post": profile["delta_post"],
                "retention_factor": profile["retention_factor"],
                "confidence_baseline": profile["confidence_baseline"],
                "confidence_delta_post": profile["confidence_delta_post"],
            },
            "honest": {
                "delta_hat": honest["delta_hat"],
                "performance_pre": honest["performance_pre"],
                "performance_post": honest["performance_post"],
                "divergence_z": honest["divergence_z"],
                "flagged_confident_non_learner": honest["flagged_confident_non_learner"],
            },
            "feedback": {
                "confidence_pre": profile["confidence_pre"],
                "confidence_post": feedback["confidence_post"],
                "satisfaction_post": feedback["satisfaction_post"],
            },
            "naive": None if naive is None else {
                "is_repeat_form": naive["is_repeat_form"],
                "performance_delta": naive["performance_delta"],
                "confidence_delta_scaled": naive["confidence_delta_scaled"],
                "blended_effect": naive["blended_effect"],
            },
            "responses": responses,
        })
    log(f"  {len(out)} learners assembled")
    return out


# ---------------------------------------------------------------------------
# Instrument summaries (view 2)
# ---------------------------------------------------------------------------

INSTRUMENT_LABELS = {
    "honest": "The honest instrument",
    "feedback_sheet": "The feedback sheet",
    "naive": "The naive evaluation",
}


def build_instruments(marks: dict) -> dict:
    primary = marks["primary_pass"]
    exp = primary["expectations"]
    return {
        "honest": {
            "label": INSTRUMENT_LABELS["honest"],
            "description": config.INSTRUMENT_DEFINITIONS["honest"]["description"],
            "summary": primary["honest_run"]["summary"],
        },
        "feedback_sheet": {
            "label": INSTRUMENT_LABELS["feedback_sheet"],
            "description": config.INSTRUMENT_DEFINITIONS["feedback_sheet"]["description"],
            "summary": primary["feedback_run"]["summary"],
            "r_confidence_vs_delta": exp["3"]["r_confidence_post_vs_planted_delta"],
            "r_satisfaction_vs_delta": exp["3"]["r_satisfaction_post_vs_planted_delta"],
        },
        "naive": {
            "label": INSTRUMENT_LABELS["naive"],
            "description": config.INSTRUMENT_DEFINITIONS["naive"]["description"],
            "summary": primary["naive_run"]["summary"],
        },
    }


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        marks = load_json(MARKS_PATH)
        writeup_text = load_text(WRITEUP_PATH)
        primary = marks["primary_pass"]
        perfect = marks["perfect_scoring_robustness_pass"]

        exp2 = primary["expectations"]["2"]
        exp6 = primary["expectations"]["6"]

        data = {
            "meta": {
                "project": "09 Training Outcomes",
                "n_learners": primary["honest_run"]["summary"]["n_learners"],
                "n_confident_non_learners": exp2["n_planted_confident_non_learners"],
                "n_flagged_total": primary["honest_run"]["summary"]["n_flagged_confident_non_learners"],
                "n_fast_forgetters": len(exp6["per_fast_forgetter_detail"]),
                "divergence_flag_threshold_z": primary["honest_run"]["summary"]["divergence_flag_threshold_z"],
            },
            "quotes": build_quotes(writeup_text),
            "illustrative_tasks": build_illustrative_tasks(),
            "cohort": build_cohort(marks),
            "confident_non_learner_ids": exp2["planted_confident_non_learner_ids"],
            "flagged_ids": primary["honest_run"]["summary"]["flagged_learner_ids"],
            "missed_ids": exp2["missed_ids"],
            "false_positive_ids": exp2["false_positive_ids"],
            "fast_forgetter_ids": [d["learner_id"] for d in exp6["per_fast_forgetter_detail"]],
            "instruments": build_instruments(marks),
            "expectations_scored": primary["expectations"],
            "expectations_perfect": perfect["expectations"],
            "robustness_table": marks["robustness_table"],
            "naive_decomposition": primary["expectations"]["4"]["decomposition"],
            "fast_forgetter_detail": exp6,
        }

        log(f"writing {OUT_JSON} ...")
        OUT_JSON.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        size_kb = OUT_JSON.stat().st_size / 1024
        log(f"  wrote {size_kb:.1f} KB")

        log("inlining data into template...")
        template = load_text(TEMPLATE_PATH)
        data_json_text = OUT_JSON.read_text(encoding="utf-8")

        if "/*__HPX_DATA_JSON__*/" not in template:
            raise ValueError("_template.html is missing the /*__HPX_DATA_JSON__*/ placeholder")

        # json.dumps output never contains "</script>", but guard anyway --
        # embedding untrusted-shaped text inside a <script> block is exactly
        # where that bug bites.
        if "</script" in data_json_text.lower():
            data_json_text = data_json_text.replace("</script", "<\\/script")

        html = template.replace("/*__HPX_DATA_JSON__*/", data_json_text)

        if OUT_HTML.resolve() == TEMPLATE_PATH.resolve():
            raise RuntimeError("refusing to write: output path equals template path")

        OUT_HTML.write_text(html, encoding="utf-8")
        out_kb = OUT_HTML.stat().st_size / 1024
        log(f"wrote {OUT_HTML} ({out_kb:.1f} KB)")
        if out_kb > 2048:
            log(f"WARNING: page is {out_kb:.1f} KB, over the 2 MB (2048 KB) budget")
        return 0
    except Exception as exc:  # noqa: BLE001 -- build script must report, never crash bare
        print(f"[build_data] FATAL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
