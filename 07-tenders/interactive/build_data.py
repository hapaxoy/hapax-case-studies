"""build_data.py -- assembles interactive/_data.json for the tender-workflow
interactive page, then inlines it (plus the game's scoring source) into
_template.html to produce tender-workflow.html.

Follows the same pattern as the other cases (01 Churn's interactive/build_data.py
+ _template.html -> churn_explorer.html): a deterministic, re-runnable Python
build step assembles ONE JSON blob from the project's real data directories
under data/, and a hand-written template with an embedded
<script type="application/json" id="hpx-data"> renders it client-side. No
number on the page is invented here -- everything traces to data/analysis/
marks.json, data/arm_b/run_*/*.json, data/arm_a/*.json, data/answer_key/,
data/tenders/, code/config.py or writeup/tender_workflow_case_study.md
(quoted verbatim, never paraphrased).

Run from this directory or the project root:
    python interactive/build_data.py
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
DATA_DIR = PROJECT_ROOT / "data"
CODE_DIR = PROJECT_ROOT / "code"

sys.path.insert(0, str(CODE_DIR))
import config  # noqa: E402  -- the project's own config module (TENDERS, PERSONAS, TRAP_TABLE)

MARKS_PATH = DATA_DIR / "analysis" / "marks.json"
WRITEUP_PATH = PROJECT_ROOT / "writeup" / "tender_workflow_case_study.md"
OUT_JSON = HERE / "_data.json"
TEMPLATE_PATH = HERE / "_template.html"
GAME_JS_PATH = HERE / "quickplay_score.src.js"
OUT_HTML = HERE / "tender-workflow.html"

QUICKPLAY_TENDER_IDS = ["T04", "T08", "T11"]  # the committed quick-play set

# Static company facts (data/facts/company_facts.yaml), hand-transcribed once
# here for the fabrication "claimed vs true" lookups in view 2 -- this file
# never writes to or alters company_facts.yaml itself.
STAFF_BY_DISCIPLINE = {
    "LVI": 62, "sahko": 48, "rakennusautomaatio": 18,
    "kiinteistonhoito": 35, "hallinto": 17,
}
REFERENCE_VALUES_EUR = {
    "REF01": 640000, "REF02": 1650000, "REF03": 310000, "REF04": 890000,
    "REF05": 1120000, "REF06": 275000, "REF07": 520000, "REF08": 415000,
    "REF09": 980000, "REF10": 705000,
}
CERTIFICATIONS_HELD = {
    "NMSB7310": True, "NMSB74210": True, "NMSB75310": True, "LUSA": True,
    "URAKKAVARMENNE": True, "FKAASU": True, "SAHKOURAKOINTI": True,
    "NMSB73710": False,
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


def quote(source_text: str, start_marker: str, end_marker: str, label: str) -> str:
    """Extract an EXACT verbatim substring from source_text, from the start
    of start_marker to the end of end_marker (inclusive). Slicing straight
    out of the source file -- rather than retyping the sentence -- is the
    guarantee that every callout on the page is byte-for-byte what the
    writeup says (typographic apostrophes, en-dashes and all), so no new
    prose is written here."""
    start_idx = source_text.find(start_marker)
    if start_idx == -1:
        raise ValueError(f"quote '{label}': start marker not found: {start_marker!r}")
    end_idx = source_text.find(end_marker, start_idx)
    if end_idx == -1:
        raise ValueError(f"quote '{label}': end marker not found after start: {end_marker!r}")
    return source_text[start_idx:end_idx + len(end_marker)]


def fabrication_true_value(kind: str, target_area: str):
    """The real fact behind a seeded/detected fabrication event, for the
    'claimed vs true' display in view 2. Returns a short descriptive string,
    never a guess -- every branch traces to company_facts.yaml."""
    if kind == "invented_certification":
        held = CERTIFICATIONS_HELD.get(target_area)
        if held is None:
            return "not a certification Visakoivu's facts library lists at all"
        return "held" if held else "listed in the facts library as NOT held"
    if kind == "uncited_capability":
        return "no such capability or record in the facts library"
    if kind == "capacity_overclaim":
        n = STAFF_BY_DISCIPLINE.get(target_area)
        return n if n is not None else "discipline not in the facts library"
    if kind == "inflated_reference":
        v = REFERENCE_VALUES_EUR.get(target_area)
        return v if v is not None else "reference not in the facts library"
    return "unknown fabrication kind"


# ---------------------------------------------------------------------------
# Requirements CSV (per-tender answer-key rows)
# ---------------------------------------------------------------------------

def load_requirements(tender_num: str) -> list[dict]:
    path = DATA_DIR / "answer_key" / f"requirements_{tender_num}.csv"
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Quick-play tender document parsing (T04, T08, T11)
# ---------------------------------------------------------------------------

HEADING_RE = re.compile(r"^(#{2,3})\s+(.*)$")
ANNEX_WORD_RE = re.compile(r"\bLiite\b|\bAnnex\b", re.IGNORECASE)


def parse_quickplay_tender(tender_id: str) -> dict:
    tender_num = tender_id[1:].zfill(2)
    doc_text = load_text(DATA_DIR / "tenders" / f"tender_{tender_num}.md")
    clause_map = load_json(DATA_DIR / "tenders" / f"clause_map_{tender_num}.json")["clauses"]
    requirements = {r["req_id"]: r for r in load_requirements(tender_num)}

    lines = doc_text.splitlines()
    # For every line, record the nearest preceding "##" heading text and
    # whether that heading names an annex (Liite/Annex) -- a "###"
    # sub-heading does not change the annex flag, only the display label.
    line_heading = [None] * len(lines)
    line_subheading = [None] * len(lines)
    line_is_annex = [False] * len(lines)
    current_h2 = None
    current_h3 = None
    current_annex = False
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m:
            level, text = m.group(1), m.group(2).strip()
            if level == "##":
                current_h2 = text
                current_h3 = None
                current_annex = bool(ANNEX_WORD_RE.search(text))
            else:
                current_h3 = text
        line_heading[i] = current_h2
        line_subheading[i] = current_h3
        line_is_annex[i] = current_annex

    sections: list[dict] = []
    section_index: dict[tuple, int] = {}
    pointer = 0

    for entry in clause_map:
        req_id = entry["req_id"]
        label = entry["clause_label"]
        pattern = re.compile(r"^\s*" + re.escape(label) + r"\s+(.*)$")
        found_at = None
        for i in range(pointer, len(lines)):
            m = pattern.match(lines[i])
            if m:
                found_at = i
                clause_text = m.group(1).strip()
                break
        if found_at is None:
            raise ValueError(
                f"quick-play parser: clause {label} ({req_id}) not found in "
                f"tender_{tender_num}.md at or after line {pointer}"
            )
        pointer = found_at + 1

        heading = line_heading[found_at] or "(preamble)"
        subheading = line_subheading[found_at]
        is_annex = line_is_annex[found_at]
        key = (heading, subheading)
        if key not in section_index:
            section_index[key] = len(sections)
            sections.append({
                "heading": heading,
                "subheading": subheading,
                "is_annex": is_annex,
                "clauses": [],
            })
        req_row = requirements.get(req_id, {})
        sections[section_index[key]]["clauses"].append({
            "req_id": req_id,
            "clause_label": label,
            "text": clause_text,
            "type": entry["type"],
            "trap_code": entry["trap_code"],
            "trap_group_id": req_row.get("trap_group_id") or None,
        })

    # Trap metadata, keyed the way quickplay_score.src.js expects it.
    trap_meta: dict = {"format_trap": None, "contradiction": None, "eligibility_fail": None}
    contradiction_ids: list[str] = []
    for req_id, row in requirements.items():
        code = row.get("trap_code")
        if not code:
            continue
        if code == "format_trap":
            trap_meta["format_trap"] = {"req_id": req_id}
        elif code == "eligibility_fail":
            trap_meta["eligibility_fail"] = {"req_id": req_id}
        elif code == "contradiction":
            contradiction_ids.append(req_id)
    if contradiction_ids:
        if len(contradiction_ids) != 2:
            raise ValueError(f"{tender_id}: expected exactly 2 contradiction rows, got {contradiction_ids}")
        trap_meta["contradiction"] = {"req_ids": sorted(contradiction_ids)}

    key_req_ids = [r["req_id"] for r in sorted(requirements.values(), key=lambda r: int(r["req_number"]))]
    expected_call = next(iter(requirements.values()))["tender_bid_no_bid_call"]
    expected_call = "no-bid" if expected_call.upper() == "NO-BID" else "bid"

    return {
        "tender_id": tender_id,
        "sections": sections,
        "trap_meta": trap_meta,
        "key_req_ids": key_req_ids,
        "expected_call": expected_call,
    }


# ---------------------------------------------------------------------------
# Arm A: attempts (transcript + draft + marks summary, no per_requirement --
# kept out to hold the page's size down; per-tender scatter only needs
# coverage_pct, which is carried on the summary already)
# ---------------------------------------------------------------------------

def build_arm_a(marks: dict) -> dict:
    log("assembling Arm A attempts (transcripts, drafts, marks summaries)...")
    attempts_out: dict = {}
    raw_dir = DATA_DIR / "arm_a"
    marks_attempts = marks["arm_a"]["attempts"]

    for raw_path in sorted(raw_dir.glob("attempt_*.json")):
        raw = load_json(raw_path)
        attempt_id = raw["attempt_id"]
        m = marks_attempts[attempt_id]

        fabrication = dict(m["fabrication"])
        for bucket in ("seeded_events", "detected_events"):
            enriched = []
            for ev in fabrication.get(bucket, []):
                ev2 = dict(ev)
                kind = ev.get("type") or ev.get("kind")
                ev2["true_value"] = fabrication_true_value(kind, ev.get("target_area"))
                enriched.append(ev2)
            fabrication[bucket] = enriched

        attempts_out[attempt_id] = {
            "attempt_id": attempt_id,
            "tender_id": raw["tender_id"],
            "persona_id": raw["persona_id"],
            "persona_name": raw["persona_name"],
            "transcript": raw["transcript"],
            "draft": raw["draft"],
            "coverage_pct": m["coverage_pct"],
            "n_requirements": m["n_requirements"],
            "n_addressed": m["n_addressed"],
            "traps": m["traps"],
            "bid_decision": m["bid_decision"],
            "expected_bid_no_bid": m["expected_bid_no_bid"],
            "bid_no_bid_correct": m["bid_no_bid_correct"],
            "fabrication": fabrication,
        }

    by_tender = marks["arm_a"]["by_tender"]
    log(f"  {len(attempts_out)} attempts assembled")
    return {"attempts": attempts_out, "by_tender": by_tender}


# ---------------------------------------------------------------------------
# Arm B: per-tender pipeline artifacts (matrix, final + bounced responses,
# gate reports, sign-off)
# ---------------------------------------------------------------------------

def build_arm_b(marks: dict) -> dict:
    log("assembling Arm B pipeline artifacts (matrix, responses, gates, sign-offs)...")
    runs_out: dict = {}
    marks_runs = marks["arm_b"]["runs"]

    for tender_id, m in sorted(marks_runs.items()):
        run_num = tender_id[1:].zfill(2)
        run_dir = DATA_DIR / "arm_b" / f"run_{run_num}"

        matrix = load_json(run_dir / "matrix.json")
        signoff = load_json(run_dir / "signoff.json")

        iterations = m["iterations"]
        final_response = load_json(run_dir / f"response_v{iterations}.json")
        bounced_response = None
        gate_reports = []
        if m["bounce_count"] > 0:
            # v1 is the version that got bounced at least once; keep it so
            # the "bounced text vs passing text" exhibit (T02) can show both.
            bounced_response = load_json(run_dir / "response_v1.json")
            for gr_path in sorted(run_dir.glob("gate_report_*.json")):
                gate_reports.append(load_json(gr_path))

        runs_out[tender_id] = {
            "tender_id": tender_id,
            "n_key_requirements": m["n_key_requirements"],
            "n_matrix_rows": m["n_matrix_rows"],
            "n_matched": m["n_matched"],
            "extraction_recall_pct": m["extraction_recall_pct"],
            "missed_requirement_ids": m["missed_requirement_ids"],
            "final_coverage_pct": m["final_coverage_pct"],
            "signoff_coverage_pct": m["signoff_coverage_pct"],
            "bid_no_bid": m["bid_no_bid"],
            "status": m["status"],
            "iterations": iterations,
            "bounce_count": m["bounce_count"],
            "per_requirement": m["per_requirement"],
            "matrix": matrix,
            "final_response": final_response,
            "bounced_response": bounced_response,
            "gate_reports": gate_reports,
            "signoff": signoff,
        }

    log(f"  {len(runs_out)} runs assembled")
    return {"runs": runs_out}


# ---------------------------------------------------------------------------
# Personas (code/config.py is the source of truth)
# ---------------------------------------------------------------------------

def build_personas() -> dict:
    out = {}
    for p in config.PERSONAS:
        out[p["id"]] = {
            "id": p["id"],
            "name": p["name"],
            "tagline": p["tagline"],
            "habit_paragraph": p["habit_paragraph"],
        }
    return out


# ---------------------------------------------------------------------------
# Tenders (code/config.py + marks.json's per-tender numbers)
# ---------------------------------------------------------------------------

def build_tenders(marks: dict) -> list[dict]:
    by_tender = marks["arm_a"]["by_tender"]
    runs = marks["arm_b"]["runs"]
    out = []
    for t in config.TENDERS:
        tid = t["id"]
        out.append({
            "id": tid,
            "size_class": t["size_class"],
            "sector": t["sector"],
            "buyer": t["buyer"],
            "traps": t["traps"],
            "n_key_requirements": runs[tid]["n_key_requirements"],
            "arm_a_median_coverage": by_tender[tid]["median_coverage"],
            "arm_a_best_coverage": by_tender[tid]["best_coverage"],
            "arm_a_worst_coverage": by_tender[tid]["worst_coverage"],
            "arm_b_final_coverage": runs[tid]["final_coverage_pct"],
            "arm_b_bid_no_bid": runs[tid]["bid_no_bid"],
        })
    return out


# ---------------------------------------------------------------------------
# Writeup quotes -- every callout sentence on the page is one of these,
# sliced verbatim out of writeup/tender_workflow_case_study.md.
# ---------------------------------------------------------------------------

def build_quotes(writeup_text: str) -> dict:
    log("slicing verbatim callout quotes from the writeup...")
    q = {}
    q["title"] = "Sixteen tenders, answered two ways"
    q["byline"] = quote(
        writeup_text,
        "*Visakoivu Oy, the fourteen people",
        "before either arm saw a document.*",
        "byline",
    ).strip("*")
    q["lede"] = quote(
        writeup_text,
        "Our shapes page claims that a person asking a chatbot",
        "we had not measured it.",
        "lede",
    )
    q["corpus_built"] = quote(
        writeup_text,
        "So we built one. Sixteen invented tenders,",
        "the only code in the project permitted to open the answer key.",
        "corpus_built",
    )
    q["seventy_habits_title_origin"] = quote(
        writeup_text,
        "The section title comes from the exemplum on the shapes page,",
        "Every persona is a working habit, not a deficiency.",
        "seventy_habits_title_origin",
    )
    q["arm_a_is_simulation"] = quote(
        writeup_text,
        "Arm A is a simulation, and how it was built decides what it can show.",
        "Its internal structure is what the case leans on.",
        "arm_a_is_simulation",
    )
    q["sanna_peltola_t08"] = quote(
        writeup_text,
        "**Sanna Peltola on T08**",
        "put an unchecked number into the response.",
        "sanna_peltola_t08",
    )
    q["timo_rautiainen_t11"] = quote(
        writeup_text,
        "**Timo Rautiainen on T11**",
        "He bids, at 73.3% coverage.",
        "timo_rautiainen_t11",
    )
    q["antti_salomaa_t13"] = quote(
        writeup_text,
        "**Antti Salomaa on T13**",
        "His is the single annex-buried disqualifier the human arm missed, out of twelve.",
        "antti_salomaa_t13",
    )
    q["marko_salminen_t15"] = quote(
        writeup_text,
        "**Marko Salminen on T15**",
        "His bid/no-bid call is right.",
        "marko_salminen_t15",
    )
    q["arm_b_five_steps"] = quote(
        writeup_text,
        "Arm B runs the same five steps on every tender, with no operator to be good or bad at it.",
        "every check is draft against matrix against facts library.",
        "arm_b_five_steps",
    )
    q["t11_no_bid_shape"] = quote(
        writeup_text,
        "On T11 the run drafted all 30 rows,",
        "rather than submit a quotation it cannot honour",
        "t11_no_bid_shape",
    ) + "”."
    q["t15_no_bid_shape"] = quote(
        writeup_text,
        "On T15 it stopped at row 7 of 53:",
        "lists all 46 of them by matrix id.",
        "t15_no_bid_shape",
    )
    q["t15_measured_stop"] = quote(
        writeup_text,
        "Measured against the key, that run covers 13.7% of T15’s requirements,",
        "which is what a correct stop looks like when coverage is the metric.",
        "t15_measured_stop",
    )
    q["zero_fabrication_mechanism"] = quote(
        writeup_text,
        "No fabricated claim survived to a terminal response in any of the 16 runs,",
        "the cheapest route through the pipeline is to say only what the facts library supports.",
        "zero_fabrication_mechanism",
    )
    q["t02_bounce_cost"] = quote(
        writeup_text,
        "T02 shows what that costs.",
        "the version that passed tells the buyer less than the version that failed.",
        "t02_bounce_cost",
    )
    q["false_block_pre_registration"] = quote(
        writeup_text,
        "The design pre-registered at least one false block as the bureaucratic cost of process;",
        "ten occurred, and none of them was a genuine catch.",
        "false_block_pre_registration",
    )
    q["speed_unmeasurable"] = quote(
        writeup_text,
        "Two things were not measured at all.",
        "nothing here changes that.",
        "speed_unmeasurable",
    )
    q["prose_quality_admission"] = quote(
        writeup_text,
        "Prose quality was excluded from the measured variables by design and was not scored;",
        "several Arm A drafts read better than the workflow’s matrix-shaped output.",
        "prose_quality_admission",
    )
    q["coverage_95_failed_one"] = quote(
        writeup_text,
        "**Coverage of 95% everywhere failed on exactly one tender**,",
        "and the reason is in the last section of this writeup.",
        "coverage_95_failed_one",
    )
    q["human_arm_beat_prereg"] = quote(
        writeup_text,
        "**The human arm beat its own pre-registration.**",
        "so it is published rather than corrected.",
        "human_arm_beat_prereg",
    )
    q["difficulty_not_size"] = quote(
        writeup_text,
        "**Difficulty does not scale with size.**",
        "What makes a tender hard here is what has been planted in it, not how long it is.",
        "difficulty_not_size",
    )
    q["extraction_better_than_wanted"] = quote(
        writeup_text,
        "**Extraction was better than the design wanted it to be.**",
        "and what the gates demonstrably did is catch fabrications during drafting and enforce cross-row consistency, at the cost described above.",
        "extraction_better_than_wanted",
    )
    q["three_nobody_found"] = quote(
        writeup_text,
        "Across all sixteen runs, the workflow’s extraction step missed three of the corpus’s 510 requirements:",
        "and nothing else was missed anywhere.",
        "three_nobody_found",
    )
    q["hidden_form_examples"] = quote(
        writeup_text,
        "Each is a single sentence, stated once, inside an annex, with no clause number of its own.",
        "so it reads as a recap rather than as a new obligation.",
        "hidden_form_examples",
    )
    q["hidden_form_verdict"] = quote(
        writeup_text,
        "The human arm scored 0 of 12 on that class,",
        "this is also why T03 finished at 92.9% and missed the pre-registered floor.",
        "hidden_form_verdict",
    )
    q["how_marking_checked"] = quote(
        writeup_text,
        "Clause text in T05 to T08 is printed in Finnish verbatim",
        "deliberately left open on the right so suffixed forms still match their stem.",
        "how_marking_checked",
    )
    q["what_transfers"] = quote(
        writeup_text,
        "The architecture transfers, because it does not depend on anything about tenders:",
        "the design has to decide in advance whether the bounce is cheaper than the miss.",
        "what_transfers",
    )
    q["what_doesnt_transfer"] = quote(
        writeup_text,
        "The numbers do not transfer.",
        "which is why they are the finding.",
        "what_doesnt_transfer",
    )
    q["closing_honesty"] = quote(
        writeup_text,
        "A real tender desk also has something this corpus does not.",
        "one run of a method against data built to have a known right answer.",
        "closing_honesty",
    )
    log(f"  {len(q)} verbatim quotes extracted")
    return q


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def build_quickplay(marks: dict) -> dict:
    log("parsing quick-play tender documents (T04, T08, T11)...")
    by_tender = marks["arm_a"]["by_tender"]
    runs = marks["arm_b"]["runs"]
    out = {}
    for tid in QUICKPLAY_TENDER_IDS:
        parsed = parse_quickplay_tender(tid)
        parsed["arm_a_coverages"] = [
            row["coverage_pct"] for row in by_tender[tid]["persona_table"]
        ]
        parsed["arm_b_final_coverage"] = runs[tid]["final_coverage_pct"]
        n_clauses = sum(len(s["clauses"]) for s in parsed["sections"])
        if n_clauses != len(parsed["key_req_ids"]):
            raise ValueError(
                f"{tid}: parsed {n_clauses} clauses but key has "
                f"{len(parsed['key_req_ids'])} requirements -- 1:1 mapping assumption broken"
            )
        out[tid] = parsed
        log(f"  {tid}: {n_clauses} clauses parsed across {len(parsed['sections'])} sections")
    return out


def main() -> int:
    try:
        marks = load_json(MARKS_PATH)
        writeup_text = load_text(WRITEUP_PATH)

        data = {
            "meta": {
                "project": "07 Tenders",
                "n_tenders": marks["meta"]["n_arm_a_attempts"] // 4,
                "n_arm_a_attempts": marks["meta"]["n_arm_a_attempts"],
                "n_arm_b_runs": marks["meta"]["n_arm_b_runs"],
                "n_key_requirements": sum(r["n_key_requirements"] for r in marks["arm_b"]["runs"].values()),
                "quickplay_tenders": QUICKPLAY_TENDER_IDS,
            },
            "tenders": build_tenders(marks),
            "personas": build_personas(),
            "arm_a": build_arm_a(marks),
            "arm_b": build_arm_b(marks),
            "trap_table": marks["trap_table"],
            "expectations": marks["expectations"],
            "quotes": build_quotes(writeup_text),
            "quickplay": build_quickplay(marks),
        }

        log(f"writing {OUT_JSON} ...")
        OUT_JSON.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        size_kb = OUT_JSON.stat().st_size / 1024
        log(f"  wrote {size_kb:.1f} KB")

        log("inlining data + game scoring source into template...")
        template = load_text(TEMPLATE_PATH)
        game_js = load_text(GAME_JS_PATH)
        data_json_text = OUT_JSON.read_text(encoding="utf-8")

        if "/*__HPX_DATA_JSON__*/" not in template:
            raise ValueError("_template.html is missing the /*__HPX_DATA_JSON__*/ placeholder")
        if "/*__HPX_QUICKPLAY_SCORE_JS__*/" not in template:
            raise ValueError("_template.html is missing the /*__HPX_QUICKPLAY_SCORE_JS__*/ placeholder")

        # json.dumps output never contains "</script>", but guard anyway --
        # embedding untrusted-shaped text inside a <script> block is exactly
        # where that bug bites.
        if "</script" in data_json_text.lower():
            data_json_text = data_json_text.replace("</script", "<\\/script")

        html = template.replace("/*__HPX_DATA_JSON__*/", data_json_text)
        html = html.replace("/*__HPX_QUICKPLAY_SCORE_JS__*/", game_js)

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
