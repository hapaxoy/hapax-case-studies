"""build_data.py -- assembles interactive/_data.json for the talent-screening
interactive page, then inlines it into _template.html to produce
talent-screening.html.

Follows the same pattern as the other case pages (07 Tenders, 09 Training Outcomes:
interactive/build_data.py + _template.html -> single self-contained HTML
file): a deterministic, re-runnable Python build step assembles ONE JSON
blob from the project's real data directories under data/, and a
hand-written template with an embedded <script type="application/json"
id="hpx-data"> renders it client-side.

Data sources:
  data/applications_raw/batch_*.json  -- cv_markdown + cover_letter_markdown
  data/dossiers/dossier_C*.json       -- arm 4 (the workflow), per candidate
  data/baselines/ats_scores.csv       -- arm 1 (the ATS), rank + score
  data/analysis/marking.json          -- the one marking script's output
  data/answer_key_candidates.csv      -- per-candidate demographics + archetype
  data/answer_key.csv                 -- per-candidate x per-requirement key rows

Reading the answer key here is a deliberate, logged exception to the
"answer key stays out of the modelling path" rule: marking
and adjudication are frozen (18 Sep 2026), so this is display packaging AFTER the fact, not
a leak into any run that produced a result. The site's other explorers
(07 Tenders, 09 Training Outcomes) show their keys the same way, once
results are frozen.

For the four-arm side-by-side exhibit, full per-requirement reads (all 12
requirements, all four arms) are assembled ONLY for the matched pair
(C213, the hidden gem; C228, the keyword stuffer) -- selected by
data/analysis/marking.json's own frozen rule (matched_pair.selection_rule),
never hand-picked here. Every other candidate gets application + dossier +
ATS rank/score + key summary only, to keep the page size down.

The five game-mode candidates are chosen here, deterministically, from the
key: one hidden gem, one keyword stuffer, one credential inflation, one
clear fit, one genuine borderline -- excluding C213/C228 (already used in
the matched-pair exhibit) so the game doesn't repeat it. See
choose_game_candidates() for the exact rule.

Nowhere in this script or the page it feeds does the system rank candidates
or emit a verdict of its own: the coverage table carries
evidence counts only, in application order (candidate_id ascending), and
sorting it is left entirely to the client-side JS the reader clicks.

Run from this directory or the project root:
    python interactive/build_data.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
DATA_DIR = PROJECT_ROOT / "data"
CODE_DIR = PROJECT_ROOT / "code"

sys.path.insert(0, str(CODE_DIR))
import config  # noqa: E402 -- the project's own config module (REQUIREMENTS, ARCHETYPES)

APPLICATIONS_DIR = DATA_DIR / "applications_raw"
DOSSIERS_DIR = DATA_DIR / "dossiers"
NAIVE_DIR = DATA_DIR / "naive_raw"
DISCIPLINED_DIR = DATA_DIR / "disciplined_raw"
ATS_PATH = DATA_DIR / "baselines" / "ats_scores.csv"
MARKING_PATH = DATA_DIR / "analysis" / "marking.json"
ANSWER_KEY_CANDIDATES_PATH = DATA_DIR / "answer_key_candidates.csv"
ANSWER_KEY_PATH = DATA_DIR / "answer_key.csv"

OUT_JSON = HERE / "_data.json"
TEMPLATE_PATH = HERE / "_template.html"
OUT_HTML = HERE / "talent-screening.html"

# The matched pair, selected by marking.json's own frozen rule (largest
# key-verified ATS-rank-vs-truth gap) -- recorded here as a constant only
# because the numbers are already frozen and read back from marking.json
# below as a cross-check, never chosen by this script.
MATCHED_PAIR_GEM_ID = "C213"
MATCHED_PAIR_STUFFER_ID = "C228"

# A candidate "advances" cleanly on an archetype whose must-haves are, by
# design, all genuinely evidenced (the archetype table);
# D and E are must-have claims the key does not back up or that contradict
# themselves, so the defensible unaided read is to hold them for questions
# rather than decide either way; H is engineered so the key itself records
# "defensible either way" and carries no single correct call; B/C/OFFROLE
# fail must-haves outright. Used only for the game's own end-of-round
# self-tally (the reader's calls against the key), never shown as a verdict
# on any candidate elsewhere on the page.
EXPECTED_CALL_BY_ARCHETYPE = {
    "A": "advance", "F": "advance", "G": "advance",
    "D": "hold", "E": "hold",
    "H": None,  # genuinely defensible either way -- no correct answer
    "B": "decline", "C": "decline", "OFFROLE": "decline",
}


def log(message: str) -> None:
    print(f"[build_data] {message}")


def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"required data file missing: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_csv_rows(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"required data file missing: {path}")
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def to_bool(value) -> bool:
    """CSV booleans arrive as the strings 'True'/'False'."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def omit_empty(d: dict) -> dict:
    """Drop keys whose value is None or an empty string -- keeps the
    per-requirement key rows compact (most optional fields are blank for
    most candidates: displaced_phrase, contradiction_code, borderline_code,
    borderline_note)."""
    return {k: v for k, v in d.items() if v not in (None, "")}


# ---------------------------------------------------------------------------
# Applications (CV + cover letter markdown), keyed by candidate id
# ---------------------------------------------------------------------------

def load_applications() -> dict:
    log("loading applications (CV + cover letter markdown)...")
    out = {}
    batch_paths = sorted(APPLICATIONS_DIR.glob("batch_*.json"))
    if not batch_paths:
        raise FileNotFoundError(f"no application batches found under {APPLICATIONS_DIR}")
    for path in batch_paths:
        batch = load_json(path)
        for entry in batch:
            out[entry["candidate_id"]] = {
                "cv": entry["cv_markdown"],
                "letter": entry["cover_letter_markdown"],
            }
    log(f"  {len(out)} applications loaded")
    return out


# ---------------------------------------------------------------------------
# Dossiers (arm 4, the workflow), keyed by candidate id
# ---------------------------------------------------------------------------

def compact_dossier_requirements(dossier_requirements: list) -> list:
    """Slim a dossier's 12 requirement reads to the fields the page shows:
    drop citation_verified (a marking-time detail, not a display need) and
    omit a null note."""
    out = []
    for r in dossier_requirements:
        row = {
            "r": r["requirement_id"],
            "cat": r["category"],
            "st": r["status"],
            "ln": [{"q": line["quote"], "s": line["source"]} for line in r["lines"]],
        }
        if r.get("note"):
            row["nt"] = r["note"]
        out.append(row)
    return out


def load_dossiers() -> dict:
    log("loading dossiers (arm 4, the workflow)...")
    out = {}
    paths = sorted(DOSSIERS_DIR.glob("dossier_C*.json"))
    if not paths:
        raise FileNotFoundError(f"no dossiers found under {DOSSIERS_DIR}")
    for path in paths:
        d = load_json(path)
        out[d["candidate_id"]] = d
    log(f"  {len(out)} dossiers loaded")
    return out


# ---------------------------------------------------------------------------
# Answer key -- candidate-level (demographics, archetype) and per-requirement
# ---------------------------------------------------------------------------

def load_key_candidates() -> dict:
    log("loading answer_key_candidates.csv (demographics + archetype)...")
    rows = load_csv_rows(ANSWER_KEY_CANDIDATES_PATH)
    out = {}
    for row in rows:
        out[row["candidate_id"]] = row
    log(f"  {len(out)} candidate key rows loaded")
    return out


def load_key_requirements() -> dict:
    log("loading answer_key.csv (per-requirement key rows)...")
    rows = load_csv_rows(ANSWER_KEY_PATH)
    out = {}
    for row in rows:
        out.setdefault(row["candidate_id"], []).append(row)
    log(f"  {len(out)} candidates' key rows loaded ({len(rows)} rows total)")
    return out


def compact_key_row(row: dict) -> dict:
    return omit_empty({
        "r": row["requirement_id"],
        "cat": row["requirement_category"],
        "st": row["status"],
        "loc": row.get("evidence_location") or None,
        "lo": to_bool(row.get("letter_only")) or None,
        "disp": to_bool(row.get("displaced")) or None,
        "dp": row.get("displaced_phrase") or None,
        "cc": row.get("contradiction_code") or None,
        "bc": row.get("borderline_code") or None,
        "bn": row.get("borderline_note") or None,
    })


# ---------------------------------------------------------------------------
# ATS baseline (arm 1), keyed by candidate id
# ---------------------------------------------------------------------------

def load_ats() -> dict:
    log("loading ATS baseline scores (arm 1)...")
    rows = load_csv_rows(ATS_PATH)
    out = {}
    for row in rows:
        out[row["candidate_id"]] = row
    log(f"  {len(out)} ATS rows loaded")
    return out


# ---------------------------------------------------------------------------
# Naive (arm 2) and disciplined (arm 3) small-model runs -- loaded in full
# only for the matched pair (to control page size).
# ---------------------------------------------------------------------------

def find_candidate_in_batches(batch_dir: Path, candidate_id: str) -> dict:
    for path in sorted(batch_dir.glob("batch_*.json")):
        batch = load_json(path)
        for entry in batch:
            if entry["candidate_id"] == candidate_id:
                return entry
    raise ValueError(f"{candidate_id} not found in any batch under {batch_dir}")


# ---------------------------------------------------------------------------
# Candidates -- the 240-row core dataset
# ---------------------------------------------------------------------------

def build_candidates(applications: dict, dossiers: dict, ats: dict,
                      key_candidates: dict, key_requirements: dict) -> list:
    log("assembling the 240-candidate dataset...")
    candidate_ids = sorted(key_candidates.keys(), key=lambda cid: int(cid[1:]))
    out = []
    missing_app, missing_dossier, missing_ats = [], [], []
    for cid in candidate_ids:
        kc = key_candidates[cid]
        app = applications.get(cid)
        dossier = dossiers.get(cid)
        ats_row = ats.get(cid)
        if app is None:
            missing_app.append(cid)
            continue
        if dossier is None:
            missing_dossier.append(cid)
            continue
        if ats_row is None:
            missing_ats.append(cid)
            continue
        key_rows = key_requirements.get(cid, [])
        out.append({
            "id": cid,
            "nm": kc["full_name"],
            "ar": kc["archetype"],
            "dm": {
                "no": kc["name_origin"],
                "gd": kc["gender"],
                "gy": kc["grad_year_band"],
                "dc": kc["degree_country"],
                "cg": to_bool(kc["career_gap"]),
            },
            "ats": {"rk": int(ats_row["rank"]), "sc": int(ats_row["total_score"])},
            "mh": int(float(kc["must_have_pass_count"])),
            "fq": to_bool(kc["fully_qualified"]),
            "cv": app["cv"],
            "lt": app["letter"],
            "ds": compact_dossier_requirements(dossier["requirements"]),
            "key": [compact_key_row(r) for r in key_rows],
        })
    if missing_app or missing_dossier or missing_ats:
        raise ValueError(
            f"data gaps -- missing application: {missing_app}, "
            f"missing dossier: {missing_dossier}, missing ATS row: {missing_ats}"
        )
    log(f"  {len(out)} candidates assembled, no data gaps")
    return out


# ---------------------------------------------------------------------------
# Matched pair -- full 12-requirement, four-arm side-by-side
# ---------------------------------------------------------------------------

def build_four_arm_read(candidate_id: str, ats: dict, dossiers: dict,
                         key_requirements: dict) -> list:
    ats_row = ats[candidate_id]
    dossier = dossiers[candidate_id]
    naive_entry = find_candidate_in_batches(NAIVE_DIR, candidate_id)
    disciplined_entry = find_candidate_in_batches(DISCIPLINED_DIR, candidate_id)

    naive_by_req = {r["requirement_id"]: r for r in naive_entry["requirements"]}
    disciplined_by_req = {r["requirement_id"]: r for r in disciplined_entry["requirements"]}
    dossier_by_req = {r["requirement_id"]: r for r in dossier["requirements"]}
    key_by_req = {r["requirement_id"]: r for r in key_requirements[candidate_id]}

    out = []
    for req in config.REQUIREMENTS:
        rid = req["id"]
        key_row = key_by_req[rid]
        naive_row = naive_by_req[rid]
        disc_row = disciplined_by_req[rid]
        dossier_row = dossier_by_req[rid]
        out.append(omit_empty({
            "r": rid,
            "nm": req["name"],
            "cat": req["category"],
            "key_st": key_row["status"],
            "key_note": key_row.get("borderline_note") or key_row.get("contradiction_code") or None,
            "ats_hit": int(ats_row[f"{rid}_hit"]),
            "naive_met": naive_row["met"],
            "naive_reason": naive_row["reason"],
            "arm3_st": disc_row["status"],
            "arm3_lines": [{"q": l["quote"], "s": l["source"]} for l in disc_row["lines"]],
            "arm3_note": disc_row.get("note") or None,
            "arm4_st": dossier_row["status"],
            "arm4_lines": [{"q": l["quote"], "s": l["source"]} for l in dossier_row["lines"]],
            "arm4_note": dossier_row.get("note") or None,
        }))
    return out


def build_matched_pair(marking: dict, ats: dict, dossiers: dict,
                        key_candidates: dict, key_requirements: dict) -> dict:
    log("assembling the matched-pair exhibit (full 12-req, 4-arm reads)...")
    mp = marking["matched_pair"]
    gem_id = mp["missed_star"]["candidate_id"]
    stuffer_id = mp["false_positive"]["candidate_id"]
    if gem_id != MATCHED_PAIR_GEM_ID or stuffer_id != MATCHED_PAIR_STUFFER_ID:
        raise ValueError(
            f"marking.json's matched pair ({gem_id}, {stuffer_id}) does not match "
            f"the constants this script expects ({MATCHED_PAIR_GEM_ID}, {MATCHED_PAIR_STUFFER_ID})"
        )

    def build_side(candidate_id: str, kc: dict) -> dict:
        return {
            "id": candidate_id,
            "nm": kc["full_name"],
            "ar": kc["archetype"],
            "ats_rank": int(ats[candidate_id]["rank"]),
            "ats_score": int(ats[candidate_id]["total_score"]),
            "reads": build_four_arm_read(candidate_id, ats, dossiers, key_requirements),
        }

    return {
        "selection_rule": mp["selection_rule"],
        "gem": build_side(gem_id, key_candidates[gem_id]),
        "stuffer": build_side(stuffer_id, key_candidates[stuffer_id]),
    }


# ---------------------------------------------------------------------------
# Game mode -- five fixed candidates: one gem, one stuffer, one inflation,
# one clear fit, one genuine borderline.
# ---------------------------------------------------------------------------

def choose_game_candidates(marking: dict, key_candidates: dict) -> list:
    """Deterministic selection, excluding the matched pair (already shown
    above). Each pick is the lowest-numbered candidate id of its archetype
    that also has a clean, self-contained story to tell in 90 seconds:
      - gem: from marking.json's gems_arm3.per_gem, a candidate the
        disciplined arm actually caught (so the reveal has a real "the
        evidence was there, under different words" moment)
      - stuffer: the archetype-D candidate with the best (lowest) ATS rank
        after C228, so the game shows a second, distinct stuffer story
      - inflation: the first archetype-E candidate on marking.json's
        contradiction_table (a title-inflation case with a citable quote)
      - fit: the lowest-numbered archetype-A candidate, fully qualified
      - borderline: the lowest-numbered archetype-H candidate
    All rules are mechanical over already-frozen data; nothing here is
    hand-picked outside these deterministic tie-break rules.
    """
    log("choosing the five fixed game-mode candidates...")

    gem_id = None
    for g in marking["gems_arm3"]["per_gem"]:
        if g["candidate_id"] != MATCHED_PAIR_GEM_ID and g["caught"]:
            gem_id = g["candidate_id"]
            break
    if gem_id is None:
        raise ValueError("no eligible gem candidate found for game mode")

    stuffer_id = None
    for s in sorted(marking["addenda"]["A1"]["detail"], key=lambda row: row["rank"]):
        if s["candidate_id"] != MATCHED_PAIR_STUFFER_ID:
            stuffer_id = s["candidate_id"]
            break
    if stuffer_id is None:
        raise ValueError("no eligible stuffer candidate found for game mode")

    inflation_id = None
    for row in marking["contradiction_table"]["rows"]:
        if key_candidates[row["candidate_id"]]["archetype"] == "E":
            inflation_id = row["candidate_id"]
            break
    if inflation_id is None:
        raise ValueError("no eligible inflation candidate found for game mode")

    fit_candidates = sorted(
        (cid for cid, row in key_candidates.items()
         if row["archetype"] == "A" and to_bool(row["fully_qualified"])),
        key=lambda cid: int(cid[1:]),
    )
    if not fit_candidates:
        raise ValueError("no eligible clear-fit candidate found for game mode")
    fit_id = fit_candidates[0]

    borderline_candidates = sorted(
        (cid for cid, row in key_candidates.items() if row["archetype"] == "H"),
        key=lambda cid: int(cid[1:]),
    )
    if not borderline_candidates:
        raise ValueError("no eligible borderline candidate found for game mode")
    borderline_id = borderline_candidates[0]

    picks = [
        {"id": fit_id, "role": "fit", "role_label": "Clear fit"},
        {"id": stuffer_id, "role": "stuffer", "role_label": "Keyword stuffer"},
        {"id": gem_id, "role": "gem", "role_label": "Hidden gem"},
        {"id": borderline_id, "role": "borderline", "role_label": "Genuine borderline"},
        {"id": inflation_id, "role": "inflation", "role_label": "Credential inflation"},
    ]
    for pick in picks:
        archetype = key_candidates[pick["id"]]["archetype"]
        pick["expected_call"] = EXPECTED_CALL_BY_ARCHETYPE[archetype]
    log(f"  game candidates: {[p['id'] + '(' + p['role'] + ')' for p in picks]}")
    return picks


# ---------------------------------------------------------------------------
# Pre-registrations and addenda -- headline numbers only (no per-candidate
# lists; those live on the coverage table / matched pair / game already).
# ---------------------------------------------------------------------------

def build_prereg_headline(marking: dict) -> dict:
    log("summarising pre-registrations and addenda (headline numbers only)...")
    p = marking["pre_registrations"]
    a = marking["addenda"]
    return {
        "1": {"definition": p["1"]["definition"], "bar": p["1"]["bar"], "recall": p["1"]["recall"], "met": p["1"]["met"]},
        "2": {"definition": p["2"]["definition"], "bar_pct": p["2"]["bar_pct"], "fabrication_rate_pct": p["2"]["fabrication_rate_pct"], "met": p["2"]["met"]},
        "3": {"arm": p["3"]["arm"], "caught": p["3"]["caught"], "total": p["3"]["total_gems"], "bar": p["3"]["bar"], "met": p["3"]["met"]},
        "4": {"arm": p["4"]["arm"], "success": p["4"]["success"], "total": p["4"]["total_stuffers"], "bar": p["4"]["bar"], "met": p["4"]["met"]},
        "5": {"bar_pp": p["5"]["bar_pp"], "met": False, "note": "grad-year-band and degree-country spreads exceed the 2pp bar; see marking.json parity for the full per-stratum table"},
        "6": {"definition": p["6"]["definition"], "ratio": p["6"]["ratio"], "bar_multiplier": p["6"]["bar_multiplier"], "met": p["6"]["met"]},
        "A1": {"definition": a["A1"]["definition"], "above_median": a["A1"]["above_median"], "total": a["A1"]["total_stuffers"], "bar": a["A1"]["bar"], "met": a["A1"]["met"]},
        "A2": {"definition": a["A2"]["definition"], "ats_hits": a["A2"]["ats_hits"], "total": a["A2"]["total_gems"], "bar": a["A2"]["bar"], "met": a["A2"]["met"]},
        "A3": {"definition": a["A3"]["definition"], "met": a["A3"]["met"]},
        "A4": {"definition": a["A4"]["definition"], "met": a["A4"]["met"]},
    }


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        applications = load_applications()
        dossiers = load_dossiers()
        ats = load_ats()
        key_candidates = load_key_candidates()
        key_requirements = load_key_requirements()
        marking = load_json(MARKING_PATH)

        candidates = build_candidates(applications, dossiers, ats, key_candidates, key_requirements)
        matched_pair = build_matched_pair(marking, ats, dossiers, key_candidates, key_requirements)
        game_candidates = choose_game_candidates(marking, key_candidates)
        prereg = build_prereg_headline(marking)

        status_labels_key = {
            "evidenced": "Evidenced",
            "claimed_only": "Claimed, not substantiated",
            "contradicted": "Contradicted",
            "absent": "Absent",
            "not_stated": "Not stated",
        }
        status_labels_dossier = {
            "evidence_found": "Evidence found",
            "claim_only": "Claimed, not substantiated",
            "contradiction": "Contradiction flagged",
            "not_stated": "Not stated",
        }
        naive_met_labels = {"yes": "Met", "no": "Not met", "partial": "Partially met"}

        data = {
            "meta": {
                "project": "10 Talent Screening",
                "company": "Kaikuvaara Oy",
                "role_title": "Senior Signal Processing Engineer",
                "location": "Oulu",
                "n_candidates": len(candidates),
                "seed": config.RANDOM_SEED,
                "requirements": [
                    {"id": r["id"], "nm": r["name"], "cat": r["category"], "desc": r["description"]}
                    for r in config.REQUIREMENTS
                ],
                "archetype_labels": {a["id"]: a["label"] for a in config.ARCHETYPES},
                "status_labels_key": status_labels_key,
                "status_labels_dossier": status_labels_dossier,
                "naive_met_labels": naive_met_labels,
                "matched_pair_ids": {"gem": MATCHED_PAIR_GEM_ID, "stuffer": MATCHED_PAIR_STUFFER_ID},
            },
            "candidates": candidates,
            "matched_pair": matched_pair,
            "game": game_candidates,
            "prereg": prereg,
        }

        log(f"writing {OUT_JSON} ...")
        OUT_JSON.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        size_mb = OUT_JSON.stat().st_size / (1024 * 1024)
        log(f"  wrote {size_mb:.2f} MB")

        log("inlining data into template...")
        if not TEMPLATE_PATH.exists():
            raise FileNotFoundError(f"required template missing: {TEMPLATE_PATH}")
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
        data_json_text = OUT_JSON.read_text(encoding="utf-8")

        if "/*__HPX_DATA_JSON__*/" not in template:
            raise ValueError("_template.html is missing the /*__HPX_DATA_JSON__*/ placeholder")

        # json.dumps output never contains "</script>", but guard anyway --
        # embedding untrusted-shaped text inside a <script> block is exactly
        # where that bug bites.
        if "</script" in data_json_text.lower():
            data_json_text = data_json_text.replace("</script", "<\\/script")

        html = template.replace("/*__HPX_DATA_JSON__*/", data_json_text)

        # Safety: output path must never equal an input path (project rule).
        if OUT_HTML.resolve() == TEMPLATE_PATH.resolve():
            raise RuntimeError("refusing to write: output path equals template path")
        for input_path in (APPLICATIONS_DIR, DOSSIERS_DIR, ATS_PATH, MARKING_PATH,
                           ANSWER_KEY_CANDIDATES_PATH, ANSWER_KEY_PATH):
            if OUT_HTML.resolve() == input_path.resolve():
                raise RuntimeError(f"refusing to write: output path equals input path {input_path}")

        OUT_HTML.write_text(html, encoding="utf-8")
        out_mb = OUT_HTML.stat().st_size / (1024 * 1024)
        log(f"wrote {OUT_HTML} ({out_mb:.2f} MB)")
        if out_mb > 4.0:
            log(f"WARNING: page is {out_mb:.2f} MB, over the 4 MB budget")
        return 0
    except Exception as exc:  # noqa: BLE001 -- build script must report, never crash bare
        print(f"[build_data] FATAL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
