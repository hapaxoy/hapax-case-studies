"""Phase-4 marking script (Project 10 -- "Talent screening: the dossier, not
the decision").

**This is the ONLY script in this project permitted to read
`data/answer_key.csv` and `data/answer_key_candidates.csv`.** Every other
script in `code/` (generators, extractors, baselines, validators) is
structurally forbidden from touching the key. This
script reads the key exactly once, computes every pre-registered number
against it, and writes two outputs:

  data/analysis/marking.json  -- every number below, machine-readable
  data/analysis/report.md     -- the same material as plain markdown tables,
                                  for a human reader

It marks four arms against the same 240-candidate corpus and the same key:
  arm 1  -- the ATS keyword baseline           (data/baselines/ats_scores*.csv)
  arm 2  -- the naive local LLM (Haiku)         (data/naive_raw/)
  arm 3  -- the disciplined local LLM (Haiku)   (data/disciplined_raw/) -- MAY
            BE INCOMPLETE while the addendum run is in flight; this script
            marks whatever is present, prints a loud PARTIAL banner, and
            still exits 0 unless run with --require-complete.
  arm 4  -- the full workflow (Sonnet)          (data/dossiers/) -- complete.

Ground rule enforced structurally, not just by convention: the only import
that ever resolves to the two key CSVs is `load_key()` / `load_candidates()`
below. Citation verification for arm 3 reuses `assemble_dossiers.py`'s own
`verify_citation` / `assemble_dossier` functions rather than re-implementing
them, so arm 3 is marked by exactly the same machinery that produced arm 4's
dossiers.

Run (partial arm 3, current data):
    python mark_results.py

Run (final run, once all 30 disciplined_raw batches exist -- fails loudly if
any are still missing):
    python mark_results.py --require-complete
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import config
import assemble_dossiers  # reused: verify_citation(), assemble_dossier(), load_applications()


def log(message: str) -> None:
    print(f"[mark_results] {message}", flush=True)


# ---------------------------------------------------------------------------
# CONFIG BLOCK -- every tunable for this marking pass lives here, not buried
# in the functions below.
# ---------------------------------------------------------------------------

OUTPUT_DIR = config.DATA_DIR / "analysis"
MARKING_JSON_PATH = OUTPUT_DIR / "marking.json"
REPORT_MD_PATH = OUTPUT_DIR / "report.md"

DEMOGRAPHIC_DIMS = ["name_origin", "gender", "grad_year_band", "degree_country", "career_gap"]
PARITY_BAR_PP = 2.0  # percentage points (pre-reg 5)

EVIDENCE_RECALL_BAR = 0.95        # pre-reg 1
INVENTED_EVIDENCE_BAR_PCT = 1.0   # pre-reg 2 (judged on fabrications only)
FABRICATION_SIMILARITY_THRESHOLD = 0.85  # pre-reg 2 classification cutoff
GEMS_BAR = 15         # of 18, pre-reg 3
STUFFERS_BAR = 19     # of 22, pre-reg 4

A1_STUFFERS_ABOVE_MEDIAN_BAR = 15   # of 22
A2_ATS_GEM_HIT_MAX = 3              # of 18
ATS_POOL_MEDIAN_RANK = 120          # "above pool median" == rank <= 120 (n=240)

# Conservative word list for crediting the naive arm with "catching" a
# planted contradiction from free-text `reason` alone (the naive contract has
# no contradiction vocabulary -- the cross-arm comparison requires this to
# be conservative). Deliberately narrow: generic phrases like "does not match"
# fire constantly on ordinary absence judgements ("Python experience does
# not match the requirement") and would inflate naive's credit for a signal
# it was never asked to produce. Kept here, not buried in a function, so a
# future editor sees exactly what counts as "mentions the inconsistency".
CONTRADICTION_INDICATOR_REGEX = re.compile(
    r"\b(inconsist\w*|contradict\w*|discrepan\w*|conflicts?\b)", re.IGNORECASE
)

assert OUTPUT_DIR != config.DATA_DIR, "output path must never equal an input path"
assert OUTPUT_DIR != config.DATA_DIR / "dossiers", "output path must never equal an input path"

# ---------------------------------------------------------------------------
# Persona-experiment config (pre-registration 6, 18 Sep
# 2026) -- 12 recruiter personas x 2 arms (unaided / assisted), each screening
# the same 48-application subset. One output file per (persona, arm) at
# data/persona_raw/<arm>/persona_P<NN>.json; one task file per (persona, arm)
# at data/persona_tasks/<arm>/persona_P<NN>.json (the source of the subset
# and persona traits -- never the answer key).
# ---------------------------------------------------------------------------

PERSONA_IDS = [f"P{n:02d}" for n in range(1, 13)]
PERSONA_ARMS = ["unaided", "assisted"]
PERSONA_TASKS_DIR = config.DATA_DIR / "persona_tasks"
PERSONA_RAW_DIR = config.DATA_DIR / "persona_raw"
N_PERSONA_FILES_EXPECTED = len(PERSONA_IDS) * len(PERSONA_ARMS)  # 24
PERSONA_SUBSET_SIZE = config.PERSONA_SUBSET_SIZE  # 48

# Pre-registration 6 (frozen 18 Sep 2026): total gems
# advanced across all 12 personas in the assisted arm must be >= this
# multiple of the same total in the unaided arm.
GEM_IDENTIFICATION_RATIO_BAR = 2.0

# Mechanical leading-token decision parser (frozen with pre-registration 6):
# case-insensitive, tolerant of punctuation/dash immediately after the token.
# Never fuzzy-matched -- a screening_decision that doesn't match this goes on
# the adjudication list, never guessed.
DECISION_TOKEN_REGEX = re.compile(r"^\s*(advance|hold|decline)\b", re.IGNORECASE)

# Adjudicated decision-vocabulary mapping (18 Sep 2026): the P07-assisted
# output file wrote Yes / No /
# Maybe (and a "want to flag before deciding" variant) instead of the
# contracted advance / hold / decline. The mapping was drafted and logged
# BEFORE any mapped total was computed. Scope is
# STRICTLY (persona P07, assisted arm); it applies only after the mechanical
# parser fails; every mapped decision is published as adjudicated-mapped,
# never silently parsed; and pre-registration 6 is reported both with the
# mapping (primary) and with P07-assisted left unparsed (sensitivity).
ADJUDICATED_MAPPING_SCOPE = ("P07", "assisted")
ADJUDICATED_TOKEN_REGEX = re.compile(r"^\s*(yes|no|maybe)\b", re.IGNORECASE)
ADJUDICATED_TOKEN_MAP = {"yes": "ADVANCE", "no": "DECLINE", "maybe": "HOLD"}
ADJUDICATED_FLAG_REGEX = re.compile(r"\bflag\b[\s\S]{0,40}\bbefore\b[\s\S]{0,20}\bdecid",
                                     re.IGNORECASE)


# ---------------------------------------------------------------------------
# Loaders. Every one of these is read-only against files this script never
# writes to.
# ---------------------------------------------------------------------------

def load_key() -> pd.DataFrame:
    """The only place in the whole project that reads answer_key.csv."""
    path = config.ANSWER_KEY_PATH
    if not path.exists():
        raise SystemExit(f"[mark_results] ERROR: {path} not found -- nothing to mark against.")
    return pd.read_csv(path)


def load_candidates() -> pd.DataFrame:
    """The only place in the whole project that reads answer_key_candidates.csv."""
    path = config.ANSWER_KEY_CANDIDATES_PATH
    if not path.exists():
        raise SystemExit(f"[mark_results] ERROR: {path} not found -- nothing to mark against.")
    return pd.read_csv(path)


def load_arm4_dossiers() -> dict[str, dict]:
    """Arm 4 (full workflow, Sonnet) -- already-assembled dossiers."""
    dossiers_dir = config.DATA_DIR / "dossiers"
    if not dossiers_dir.exists():
        raise SystemExit(f"[mark_results] ERROR: {dossiers_dir} not found.")
    dossiers = {}
    for path in sorted(dossiers_dir.glob("dossier_C*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        dossiers[d["candidate_id"]] = d
    return dossiers


def load_arm4_citation_failures() -> list[dict]:
    path = config.DATA_DIR / "dossiers" / "_citation_failures.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def load_ats() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Arm 1 -- the deterministic ATS keyword baseline (full-text primary
    configuration and the CV-only sensitivity variant)."""
    full_path = config.DATA_DIR / "baselines" / "ats_scores.csv"
    cv_path = config.DATA_DIR / "baselines" / "ats_scores_cv_only.csv"
    if not full_path.exists() or not cv_path.exists():
        raise SystemExit(f"[mark_results] ERROR: ATS baseline files missing under "
                          f"{config.DATA_DIR / 'baselines'} -- run ats_baseline.py first.")
    return pd.read_csv(full_path), pd.read_csv(cv_path)


def load_naive() -> tuple[dict[str, dict], list[str], list[str]]:
    """Arm 2 -- the naive local LLM. Returns (responses, present_batch_names,
    missing_batch_names)."""
    raw_dir = config.DATA_DIR / "naive_raw"
    responses: dict[str, dict] = {}
    present, missing = [], []
    for batch_num in range(1, config.N_BATCHES + 1):
        path = raw_dir / f"batch_{batch_num:02d}.json"
        if not path.exists():
            missing.append(path.name)
            continue
        present.append(path.name)
        batch = json.loads(path.read_text(encoding="utf-8"))
        for response in batch:
            responses[response["candidate_id"]] = response
    return responses, present, missing


def load_disciplined_raw() -> tuple[dict[str, dict], list[str], list[str]]:
    """Arm 3's raw extraction responses (workflow contract, Haiku). May be
    partial -- returns (responses, present_batch_names, missing_batch_names)
    so callers can decide how loudly to complain."""
    raw_dir = config.DATA_DIR / "disciplined_raw"
    responses: dict[str, dict] = {}
    present, missing = [], []
    if not raw_dir.exists():
        return responses, present, [f"batch_{n:02d}.json" for n in range(1, config.N_BATCHES + 1)]
    for batch_num in range(1, config.N_BATCHES + 1):
        path = raw_dir / f"batch_{batch_num:02d}.json"
        if not path.exists():
            missing.append(path.name)
            continue
        try:
            batch = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            log(f"WARNING: {path} is not valid JSON ({exc}) -- treating as missing")
            missing.append(path.name)
            continue
        present.append(path.name)
        for response in batch:
            responses[response["candidate_id"]] = response
    return responses, present, missing


def build_arm3_dossiers(responses: dict[str, dict], applications: dict[str, dict]
                         ) -> tuple[dict[str, dict], list[dict], int]:
    """Assemble arm-3 "dossiers" from raw disciplined-Haiku responses, using
    the SAME assembly + citation-verification function that produced arm 4's
    dossiers (assemble_dossiers.assemble_dossier / verify_citation). Nothing here is a re-implementation --
    it is the identical function called on a different raw-response set.

    Returns (dossiers_by_candidate, citation_failures, total_quoted_lines).
    """
    citation_failures: list[dict] = []
    dossiers: dict[str, dict] = {}
    for candidate_id, response in responses.items():
        application = applications.get(candidate_id)
        if application is None:
            log(f"WARNING: no application text for {candidate_id} -- skipping arm-3 dossier")
            continue
        dossiers[candidate_id] = assemble_dossiers.assemble_dossier(
            candidate_id, response, application, citation_failures)
    total_lines = sum(len(r["lines"]) for d in dossiers.values() for r in d["requirements"])
    return dossiers, citation_failures, total_lines


# ---------------------------------------------------------------------------
# Persona-experiment loaders. Task files (never the key) give the frozen
# 48-application subset and each persona's traits; raw output files (may be
# partial -- other agents are still writing some of the 24) give the
# screening responses. Independent agents wrote the 24 output files with
# three different top-level wrapper key names (screenings / results /
# responses) and one plain array -- extract_persona_records() below is
# schema-tolerant of the wrapper only, never of the per-record fields, which
# are consistent across every file inspected (candidate_id, persona_id, arm,
# requirement_judgments, flags, screening_decision, time_budget_seconds).
# ---------------------------------------------------------------------------

def extract_persona_records(data) -> list[dict]:
    """Returns the list of 48 per-candidate records from a parsed persona
    output file, regardless of which top-level wrapper key (or none) the
    writing agent used. Raises ValueError if no such list can be found."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("screenings", "results", "responses", "records"):
            candidate_list = data.get(key)
            if (isinstance(candidate_list, list) and candidate_list
                    and isinstance(candidate_list[0], dict) and "candidate_id" in candidate_list[0]):
                return candidate_list
        # Fallback: scan every value for the first list-of-records shape.
        for value in data.values():
            if (isinstance(value, list) and value
                    and isinstance(value[0], dict) and "candidate_id" in value[0]):
                return value
    raise ValueError("no list of per-candidate records found (expected a bare array or one "
                      "of screenings/results/responses/records)")


def load_persona_task_files() -> tuple[list[str], dict]:
    """Reads all 24 persona task files to derive the frozen 48-application
    subset and confirm it is identical across every persona and both arms.
    Task files are inputs (never the answer key)."""
    subset_by_file: dict[tuple[str, str], list[str]] = {}
    errors: list[str] = []
    for persona_id in PERSONA_IDS:
        for arm in PERSONA_ARMS:
            path = PERSONA_TASKS_DIR / arm / f"persona_{persona_id}.json"
            label = f"{arm}/persona_{persona_id}.json"
            if not path.exists():
                errors.append(f"task file {label} missing")
                continue
            try:
                task = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                errors.append(f"task file {label}: unreadable ({exc})")
                continue
            candidate_ids = sorted(c["candidate_id"] for c in task.get("candidates", []))
            subset_by_file[(persona_id, arm)] = candidate_ids

    if not subset_by_file:
        raise SystemExit(f"[mark_results] ERROR: no persona task files found under "
                          f"{PERSONA_TASKS_DIR} -- cannot derive the 48-application subset.")

    reference_key, reference_ids = next(iter(subset_by_file.items()))
    mismatched = [f"{p}/{a}" for (p, a), ids in subset_by_file.items() if ids != reference_ids]
    if len(reference_ids) != PERSONA_SUBSET_SIZE:
        errors.append(f"reference subset (from {reference_key}) has {len(reference_ids)} "
                       f"candidates, expected {PERSONA_SUBSET_SIZE}")

    return reference_ids, {
        "n_task_files_found": len(subset_by_file),
        "n_task_files_expected": N_PERSONA_FILES_EXPECTED,
        "mismatched_files": mismatched,
        "errors": errors,
    }


def load_persona_output_file(persona_id: str, arm: str) -> dict:
    """Loads one of the 24 raw persona-screening output files. Never raises
    on a missing/malformed file -- returns a status so the caller can decide
    how loudly to complain (see build_persona_section)."""
    path = PERSONA_RAW_DIR / arm / f"persona_{persona_id}.json"
    if not path.exists():
        return {"persona_id": persona_id, "arm": arm, "path": path,
                "status": "missing", "records": None, "error": None}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return {"persona_id": persona_id, "arm": arm, "path": path,
                "status": "unreadable", "records": None, "error": str(exc)}
    try:
        records = extract_persona_records(raw)
    except ValueError as exc:
        return {"persona_id": persona_id, "arm": arm, "path": path,
                "status": "unrecognised_schema", "records": None, "error": str(exc)}
    return {"persona_id": persona_id, "arm": arm, "path": path,
            "status": "ok", "records": records, "error": None}


def validate_persona_output(entry: dict, subset_ids: list[str]) -> list[str]:
    """Item 5's completeness contract for one loaded persona file: exactly 48
    unique candidate_ids matching the subset, and 12 requirement_judgments
    per candidate. Returns a list of problem strings (empty if clean)."""
    label = f"{entry['arm']}/persona_{entry['persona_id']}.json"
    if entry["status"] != "ok":
        return [f"{label}: {entry['status']}" +
                (f" ({entry['error']})" if entry["error"] else "")]

    problems = []
    records = entry["records"]
    ids = [r.get("candidate_id") for r in records]
    if len(ids) != len(set(ids)):
        dupes = sorted({cid for cid in ids if ids.count(cid) > 1})
        problems.append(f"{label}: duplicate candidate_id(s) {dupes}")
    id_set = set(ids)
    subset_set = set(subset_ids)
    if id_set != subset_set:
        problems.append(f"{label}: candidate_id set does not match the subset "
                         f"(missing {sorted(subset_set - id_set) or 'none'}, "
                         f"unexpected {sorted(id_set - subset_set) or 'none'})")
    if len(ids) != PERSONA_SUBSET_SIZE:
        problems.append(f"{label}: {len(ids)} records, expected {PERSONA_SUBSET_SIZE}")
    bad_count_ids = [r.get("candidate_id") for r in records
                     if len(r.get("requirement_judgments") or []) != 12]
    if bad_count_ids:
        problems.append(f"{label}: candidate(s) without exactly 12 "
                         f"requirement_judgments: {bad_count_ids}")
    return problems


def parse_screening_decision(text) -> str | None:
    """Mechanical leading-token parse frozen 18 Sep 2026: returns
    'ADVANCE' / 'HOLD' / 'DECLINE', or None if the text doesn't start with
    one of those tokens. Never guessed and never fuzzy-matched -- a None
    here belongs on the adjudication list, not a best-effort classification."""
    if not text:
        return None
    match = DECISION_TOKEN_REGEX.match(text)
    return match.group(1).upper() if match else None


def adjudicated_decision_mapping(persona_id: str, arm: str, text) -> str | None:
    """The adjudicated mapping (18 Sep 2026) for the P07-assisted
    vocabulary drift: Yes -> ADVANCE, No -> DECLINE, Maybe / any
    flag-before-deciding variant -> HOLD. Returns None outside that single
    file's scope, or when the text matches none of the mapped forms -- a None
    here still lands on the adjudication list."""
    if (persona_id, arm) != ADJUDICATED_MAPPING_SCOPE or not text:
        return None
    match = ADJUDICATED_TOKEN_REGEX.match(text)
    if match:
        return ADJUDICATED_TOKEN_MAP[match.group(1).lower()]
    if ADJUDICATED_FLAG_REGEX.search(text):
        return "HOLD"
    return None


# ---------------------------------------------------------------------------
# JSON-safety helper -- numpy/pandas scalar types are not natively
# json.dumps-able, and NaN must become null, not the invalid literal `NaN`.
# ---------------------------------------------------------------------------

def to_jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        f = float(obj)
        return None if f != f else f  # NaN != NaN
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, float) and obj != obj:
        return None
    return obj


# ---------------------------------------------------------------------------
# Pre-registration 1 -- evidence recall >= 95%.
# ---------------------------------------------------------------------------

def preregistration_1(key_df: pd.DataFrame, arm4_dossiers: dict[str, dict]) -> dict:
    """Of key rows where status == evidenced on a must-have, the fraction the
    arm-4 dossier marks evidence_found with at least one verified citation.
    The R05 either-location rule needs no special-case code here: assemble_
    dossiers.verify_citation() already checks a quote against whichever
    document (cv / cover_letter) the extractor tagged as its source, never
    against a required location, so a CV bare-degree-line citation and a
    cover-letter write-up citation are verified identically."""
    rows = key_df[(key_df["requirement_category"] == "must_have") & (key_df["status"] == "evidenced")]
    per_requirement: dict[str, dict] = {rid: {"total": 0, "found": 0} for rid in config.MUST_HAVE_IDS}
    found_count = 0
    failures = []

    for row in rows.itertuples():
        cid, rid = row.candidate_id, row.requirement_id
        dossier = arm4_dossiers.get(cid)
        if dossier is None:
            failures.append({"candidate_id": cid, "requirement_id": rid, "reason": "arm-4 dossier missing"})
            continue
        entry = next((r for r in dossier["requirements"] if r["requirement_id"] == rid), None)
        is_found = bool(entry) and entry["status"] == "evidence_found" and any(
            line.get("citation_verified") for line in entry.get("lines", []))
        per_requirement[rid]["total"] += 1
        if is_found:
            per_requirement[rid]["found"] += 1
            found_count += 1
        else:
            failures.append({
                "candidate_id": cid, "requirement_id": rid,
                "dossier_status": entry["status"] if entry else None,
                "reason": "not marked evidence_found with a verified citation",
            })

    total = len(rows)
    recall = found_count / total if total else None
    for rid, d in per_requirement.items():
        d["recall"] = round(d["found"] / d["total"], 4) if d["total"] else None

    return {
        "definition": "fraction of key must-have rows with status=evidenced that "
                       "arm 4's dossier marks evidence_found with >=1 verified citation "
                       "(R05's either-CV-education-line-or-letter-write-up rule holds "
                       "structurally, via assemble_dossiers.verify_citation's own "
                       "location-agnostic check)",
        "bar": EVIDENCE_RECALL_BAR,
        "evidenced_must_have_rows": total,
        "found": found_count,
        "recall": round(recall, 4) if recall is not None else None,
        "met": recall is not None and recall >= EVIDENCE_RECALL_BAR,
        "recall_by_requirement": per_requirement,
        "n_failures": len(failures),
        "failures": failures,
    }


# ---------------------------------------------------------------------------
# Pre-registration 2 -- < 1% invented evidence, classified transcription vs
# fabrication.
# ---------------------------------------------------------------------------

def normalise_for_fuzzy(text: str) -> str:
    """Whitespace/quote/dash normalisation for the fuzzy re-check -- broader
    than assemble_dossiers.normalise_whitespace(), which only handles
    whitespace, because a citation failure might be nothing more than a
    curly-quote or en-dash transcription slip that the original verbatim
    check (correctly) still flagged as a failure."""
    text = text.replace("‘", "'").replace("’", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-").replace("−", "-")
    return re.sub(r"\s+", " ", text).strip()


def best_fuzzy_ratio(quote: str, document: str) -> float:
    """Best similarity ratio between `quote` and any equal-length window of
    `document`, after normalisation. 1.0 if the quote is found as an exact
    (normalised) substring. Used only to CLASSIFY an already-confirmed
    citation failure (transcription slip vs fabrication) -- never used in
    place of the original verbatim check that produced the failure list."""
    q = normalise_for_fuzzy(quote)
    d = normalise_for_fuzzy(document)
    if not q:
        return 0.0
    if q in d:
        return 1.0
    n = len(q)
    step = max(1, n // 6)
    best = 0.0
    limit = max(1, len(d))
    for start in range(0, limit, step):
        window = d[start:start + n]
        if not window:
            continue
        ratio = difflib.SequenceMatcher(None, q, window, autojunk=False).ratio()
        if ratio > best:
            best = ratio
            if best >= 0.999:
                break
    return best


def preregistration_2(arm4_citation_failures: list[dict], arm4_dossiers: dict[str, dict],
                       applications: dict[str, dict]) -> dict:
    """Classify every citation failure as TRANSCRIPTION (fuzzy-matches a real
    passage at >=0.85 similarity -- a paraphrase or quote/dash/whitespace
    slip) or FABRICATION (no matching passage -- invented text). The
    registration is judged on fabrications only."""
    total_lines = sum(len(r["lines"]) for d in arm4_dossiers.values() for r in d["requirements"])
    classified = []
    for failure in arm4_citation_failures:
        cid, source, quote = failure["candidate_id"], failure["source"], failure["quote"]
        application = applications.get(cid, {})
        document = application.get(f"{source}_markdown", "") if source in ("cv", "cover_letter") else ""
        ratio = best_fuzzy_ratio(quote, document) if document else 0.0
        classification = "TRANSCRIPTION" if ratio >= FABRICATION_SIMILARITY_THRESHOLD else "FABRICATION"
        classified.append({
            "candidate_id": cid, "requirement_id": failure["requirement_id"],
            "source": source, "quote": quote, "similarity": round(ratio, 4),
            "classification": classification,
        })

    n_transcription = sum(1 for c in classified if c["classification"] == "TRANSCRIPTION")
    n_fabrication = sum(1 for c in classified if c["classification"] == "FABRICATION")
    fabrication_rate_pct = (n_fabrication / total_lines * 100) if total_lines else None
    overall_failure_rate_pct = (len(classified) / total_lines * 100) if total_lines else None

    return {
        "definition": "each of arm 4's citation failures re-checked against its "
                       "candidate's actual application text with normalised "
                       "whitespace/quotes/dashes; classified TRANSCRIPTION if the best "
                       f"fuzzy match anywhere in the source document is >= "
                       f"{FABRICATION_SIMILARITY_THRESHOLD} similarity (difflib "
                       "SequenceMatcher ratio over a sliding window), else FABRICATION. "
                       "The pre-registration is judged on the fabrication rate only.",
        "total_quoted_lines": total_lines,
        "total_citation_failures": len(classified),
        "overall_failure_rate_pct": round(overall_failure_rate_pct, 4) if overall_failure_rate_pct is not None else None,
        "n_transcription": n_transcription,
        "n_fabrication": n_fabrication,
        "fabrication_rate_pct": round(fabrication_rate_pct, 4) if fabrication_rate_pct is not None else None,
        "bar_pct": INVENTED_EVIDENCE_BAR_PCT,
        "met": fabrication_rate_pct is not None and fabrication_rate_pct < INVENTED_EVIDENCE_BAR_PCT,
        "classified": classified,
    }


# ---------------------------------------------------------------------------
# Pre-registration 3 -- hidden gems (generic: reused for arm 3 in A4).
# ---------------------------------------------------------------------------

def gems_surfaced(key_df: pd.DataFrame, dossiers: dict[str, dict], arm_label: str) -> dict:
    """For each F (hidden-gem) candidate, does the given arm's dossier mark
    the DISPLACED requirement evidence_found? `dossiers` may be a partial set
    (arm 3 mid-run) -- candidates without a dossier are recorded with
    caught=None and excluded from the count, loudly."""
    f_rows = key_df[(key_df["archetype"] == "F") & (key_df["displaced"] == True)]  # noqa: E712
    per_gem = []
    for row in f_rows.itertuples():
        cid, rid = row.candidate_id, row.requirement_id
        dossier = dossiers.get(cid)
        if dossier is None:
            per_gem.append({"candidate_id": cid, "requirement_id": rid,
                             "displaced_phrase": row.displaced_phrase,
                             "status": None, "caught": None,
                             "note": f"{arm_label} not yet extracted for this candidate"})
            continue
        entry = next(r for r in dossier["requirements"] if r["requirement_id"] == rid)
        caught = entry["status"] == "evidence_found"
        per_gem.append({"candidate_id": cid, "requirement_id": rid,
                         "displaced_phrase": row.displaced_phrase,
                         "status": entry["status"], "caught": caught, "note": None})

    evaluated = [g for g in per_gem if g["caught"] is not None]
    caught_count = sum(1 for g in evaluated if g["caught"])
    return {
        "arm": arm_label,
        "total_gems": len(f_rows),
        "evaluated": len(evaluated),
        "caught": caught_count,
        "rate": round(caught_count / len(evaluated), 4) if evaluated else None,
        "bar": GEMS_BAR,
        "met": caught_count >= GEMS_BAR if len(evaluated) == len(f_rows) else None,
        "met_provisional_on_available": caught_count >= GEMS_BAR,
        "per_gem": per_gem,
    }


# ---------------------------------------------------------------------------
# Pre-registration 4 -- stuffers (generic: reused for arm 3 in A4).
# ---------------------------------------------------------------------------

def stuffers_flagged(key_df: pd.DataFrame, dossiers: dict[str, dict], arm_label: str) -> dict:
    """For each D (keyword-stuffer) candidate, are >= half their claimed
    must-haves marked claim_only (not evidence_found) in the given arm's
    dossier?"""
    d_ids = key_df.loc[key_df["archetype"] == "D", "candidate_id"].unique().tolist()
    per_stuffer = []
    for cid in d_ids:
        claimed_rows = key_df[(key_df["candidate_id"] == cid) &
                               (key_df["requirement_category"] == "must_have") &
                               (key_df["status"] == "claimed_only")]
        claimed_ids = claimed_rows["requirement_id"].tolist()
        dossier = dossiers.get(cid)
        if dossier is None:
            per_stuffer.append({"candidate_id": cid, "claimed_must_haves": len(claimed_ids),
                                 "marked_claim_only": None, "fraction": None, "success": None,
                                 "note": f"{arm_label} not yet extracted for this candidate"})
            continue
        by_id = {r["requirement_id"]: r for r in dossier["requirements"]}
        marked = sum(1 for rid in claimed_ids if by_id[rid]["status"] == "claim_only")
        fraction = marked / len(claimed_ids) if claimed_ids else None
        success = fraction is not None and fraction >= 0.5
        per_stuffer.append({"candidate_id": cid, "claimed_must_haves": len(claimed_ids),
                             "marked_claim_only": marked, "fraction": round(fraction, 4) if fraction is not None else None,
                             "success": success, "note": None})

    evaluated = [s for s in per_stuffer if s["success"] is not None]
    success_count = sum(1 for s in evaluated if s["success"])
    return {
        "arm": arm_label,
        "total_stuffers": len(d_ids),
        "evaluated": len(evaluated),
        "success": success_count,
        "rate": round(success_count / len(evaluated), 4) if evaluated else None,
        "bar": STUFFERS_BAR,
        "met": success_count >= STUFFERS_BAR if len(evaluated) == len(d_ids) else None,
        "met_provisional_on_available": success_count >= STUFFERS_BAR,
        "per_stuffer": per_stuffer,
    }


# ---------------------------------------------------------------------------
# Pre-registration 5 / item 14 -- stratum parity, all four arms.
# ---------------------------------------------------------------------------

def marks_from_dossiers(dossiers: dict[str, dict]) -> pd.DataFrame:
    records = []
    for cid, dossier in dossiers.items():
        for entry in dossier["requirements"]:
            records.append({
                "candidate_id": cid, "requirement_id": entry["requirement_id"],
                "found": entry["status"] == "evidence_found",
                "flag": entry["status"] == "contradiction",
            })
    return pd.DataFrame.from_records(records, columns=["candidate_id", "requirement_id", "found", "flag"])


def marks_from_ats(ats_df: pd.DataFrame) -> pd.DataFrame:
    hit_cols = [c for c in ats_df.columns if c.endswith("_hit")]
    long = ats_df.melt(id_vars=["candidate_id"], value_vars=hit_cols,
                        var_name="requirement_id", value_name="hit")
    long["requirement_id"] = long["requirement_id"].str.replace("_hit", "", regex=False)
    long["found"] = long["hit"] == 1
    long["flag"] = np.nan  # the ATS has no flag/contradiction concept at all
    return long[["candidate_id", "requirement_id", "found", "flag"]]


def marks_from_naive(naive_responses: dict[str, dict]) -> pd.DataFrame:
    records = []
    for cid, response in naive_responses.items():
        for r in response.get("requirements", []):
            reason = r.get("reason", "") or ""
            records.append({
                "candidate_id": cid, "requirement_id": r["requirement_id"],
                "found": r.get("met") == "yes",
                "flag": bool(CONTRADICTION_INDICATOR_REGEX.search(reason)),
            })
    return pd.DataFrame.from_records(records, columns=["candidate_id", "requirement_id", "found", "flag"])


def parity_report(marks: pd.DataFrame, key_df: pd.DataFrame, candidates_df: pd.DataFrame,
                   arm_label: str, compute_flag: bool, flag_method_note: str) -> dict:
    """Evidence-recall parity (on key-evidenced must-have rows) and
    contradiction-flag-rate parity (on all 12 requirement rows), per
    demographic dimension, for one arm. Recall is computed identically
    across arms so the four are comparable; flag rate is arm-appropriate
    (see flag_method_note -- arm 1 has no flag concept at all, arm 2's flag
    is the same conservative regex used in the cross-arm contradiction
    table, not a real status)."""
    merged = marks.merge(
        key_df[["candidate_id", "requirement_id", "requirement_category", "status"]],
        on=["candidate_id", "requirement_id"], how="left")
    merged = merged.merge(candidates_df[["candidate_id"] + DEMOGRAPHIC_DIMS],
                           on="candidate_id", how="left")

    recall_rows = merged[(merged["requirement_category"] == "must_have") & (merged["status"] == "evidenced")]

    dims_out = {}
    for dim in DEMOGRAPHIC_DIMS:
        recall_by_cat = (recall_rows.groupby(dim)["found"].mean() * 100).round(2)
        recall_by_cat.index = recall_by_cat.index.map(str)
        recall_spread = float(recall_by_cat.max() - recall_by_cat.min()) if len(recall_by_cat) > 1 else 0.0
        entry = {
            "recall_by_category_pct": recall_by_cat.to_dict(),
            "recall_spread_pp": round(recall_spread, 2),
            "recall_parity_met": recall_spread <= PARITY_BAR_PP,
        }
        if compute_flag:
            flag_by_cat = (merged.groupby(dim)["flag"].mean() * 100).round(2)
            flag_by_cat.index = flag_by_cat.index.map(str)
            flag_spread = float(flag_by_cat.max() - flag_by_cat.min()) if len(flag_by_cat) > 1 else 0.0
            entry.update({
                "flag_rate_by_category_pct": flag_by_cat.to_dict(),
                "flag_spread_pp": round(flag_spread, 2),
                "flag_parity_met": flag_spread <= PARITY_BAR_PP,
            })
        else:
            entry.update({"flag_rate_by_category_pct": None, "flag_spread_pp": None, "flag_parity_met": None})
        dims_out[dim] = entry

    return {"arm": arm_label, "flag_method_note": flag_method_note, "bar_pp": PARITY_BAR_PP,
            "n_candidates_covered": marks["candidate_id"].nunique(), "dimensions": dims_out}


# ---------------------------------------------------------------------------
# Pre-registration 6 -- the persona experiment (frozen
# operationalisation 18 Sep 2026). 12 recruiter personas
# each screen the same 48-application subset twice (unaided, then with an
# evidence dossier); this is the only section of the script that reads
# data/persona_raw and data/persona_tasks.
# ---------------------------------------------------------------------------

def diagnostic_summary(counts_by_persona: dict[str, int], n_candidates: int) -> dict:
    """total / personas_evaluated / rate for one secondary diagnostic in one
    arm. rate = total hits / (n_candidates * personas_evaluated), i.e. the
    fraction of (persona, candidate) pairs where the diagnostic fired."""
    n_evaluated = len(counts_by_persona)
    total = sum(counts_by_persona.values())
    denominator = n_candidates * n_evaluated
    return {
        "total": total, "personas_evaluated": n_evaluated,
        "max_possible_per_persona": n_candidates,
        "rate": round(total / denominator, 4) if denominator else None,
    }


def persona_experiment(candidates_df: pd.DataFrame, subset_ids: list[str],
                        clean_outputs: dict[tuple[str, str], dict]) -> dict:
    """Computes pre-registration 6 and its secondary diagnostics over
    whatever (persona, arm) output files passed validation (clean_outputs --
    see build_persona_section). Archetypes come from the key-derived
    candidates_df (loaded once in main(), never re-read here)."""
    subset_archetype = (candidates_df[candidates_df["candidate_id"].isin(subset_ids)]
                         .set_index("candidate_id")["archetype"].to_dict())
    gem_ids = sorted(cid for cid, a in subset_archetype.items() if a == "F")
    stuffer_ids = sorted(cid for cid, a in subset_archetype.items() if a == "D")
    inflation_ids = sorted(cid for cid, a in subset_archetype.items() if a == "E")
    borderline_ids = sorted(cid for cid, a in subset_archetype.items() if a == "H")

    decision_totals = {arm: {"ADVANCE": 0, "HOLD": 0, "DECLINE": 0, "unparsed": 0,
                              "adjudicated_mapped": 0,
                              "personas_evaluated": 0} for arm in PERSONA_ARMS}
    adjudication = []
    adjudicated_mapped = []
    gems_advanced = {arm: {} for arm in PERSONA_ARMS}
    # Mechanical-parse-only gem counts: the sensitivity variant of pre-reg 6
    # (P07-assisted left unparsed) sums these instead of gems_advanced.
    gems_advanced_mechanical = {arm: {} for arm in PERSONA_ARMS}
    gems_held = {arm: {} for arm in PERSONA_ARMS}
    stuffers_questioned = {arm: {} for arm in PERSONA_ARMS}
    inflations_spotted = {arm: {} for arm in PERSONA_ARMS}
    borderlines_flagged = {arm: {} for arm in PERSONA_ARMS}

    for (persona_id, arm), entry in clean_outputs.items():
        decision_totals[arm]["personas_evaluated"] += 1
        gem_advance = gem_advance_mech = gem_hold = 0
        stuffer_q = inflation = borderline = 0
        for record in entry["records"]:
            cid = record["candidate_id"]
            token = parse_screening_decision(record.get("screening_decision"))
            mechanically_parsed = token is not None
            if token is None:
                # 18 Sep 2026 adjudicated mapping -- scoped to
                # P07/assisted only, and published, never silently parsed.
                token = adjudicated_decision_mapping(
                    persona_id, arm, record.get("screening_decision"))
                if token is not None:
                    decision_totals[arm]["adjudicated_mapped"] += 1
                    adjudicated_mapped.append(
                        {"candidate_id": cid, "persona_id": persona_id, "arm": arm,
                         "raw_text": record.get("screening_decision"),
                         "mapped_to": token})
            if token is None:
                decision_totals[arm]["unparsed"] += 1
                adjudication.append({"candidate_id": cid, "persona_id": persona_id, "arm": arm,
                                      "raw_text": record.get("screening_decision")})
            else:
                decision_totals[arm][token] += 1

            flags = record.get("flags") or {}
            if cid in gem_ids:
                if token == "ADVANCE":
                    gem_advance += 1
                    if mechanically_parsed:
                        gem_advance_mech += 1
                elif token == "HOLD":
                    gem_hold += 1
            if cid in stuffer_ids:
                if token in ("DECLINE", "HOLD") or len(flags.get("claims_questioned") or []) > 0:
                    stuffer_q += 1
            if cid in inflation_ids and len(flags.get("inconsistencies_noted") or []) > 0:
                inflation += 1
            if cid in borderline_ids and len(flags.get("borderline_calls") or []) > 0:
                borderline += 1

        gems_advanced[arm][persona_id] = gem_advance
        gems_advanced_mechanical[arm][persona_id] = gem_advance_mech
        gems_held[arm][persona_id] = gem_hold
        stuffers_questioned[arm][persona_id] = stuffer_q
        inflations_spotted[arm][persona_id] = inflation
        borderlines_flagged[arm][persona_id] = borderline

    unaided_total = sum(gems_advanced["unaided"].values())
    assisted_total = sum(gems_advanced["assisted"].values())
    n_unaided_eval = len(gems_advanced["unaided"])
    n_assisted_eval = len(gems_advanced["assisted"])
    fully_evaluated = n_unaided_eval == len(PERSONA_IDS) and n_assisted_eval == len(PERSONA_IDS)
    ratio = (assisted_total / unaided_total) if unaided_total > 0 else None
    met_provisional = assisted_total >= GEM_IDENTIFICATION_RATIO_BAR * unaided_total

    # Sensitivity variant: P07-assisted's decisions
    # left unparsed -- only mechanically parsed tokens count. Identical to the
    # primary numbers everywhere the adjudicated mapping never fired.
    unaided_total_mech = sum(gems_advanced_mechanical["unaided"].values())
    assisted_total_mech = sum(gems_advanced_mechanical["assisted"].values())
    ratio_mech = (assisted_total_mech / unaided_total_mech) if unaided_total_mech > 0 else None
    met_mech = assisted_total_mech >= GEM_IDENTIFICATION_RATIO_BAR * unaided_total_mech

    pre_reg_6 = {
        "definition": "a persona 'identifies' a hidden gem (archetype F) when its "
                       "screening_decision for that candidate parses as ADVANCE. Test: total "
                       "gems advanced across all 12 personas in the assisted arm >= "
                       f"{GEM_IDENTIFICATION_RATIO_BAR:g}x the same total in the unaided arm, "
                       "over the archetype-F candidates present in the 48-application subset "
                       "per the key (frozen 18 Sep 2026).",
        "gem_candidate_ids": gem_ids, "n_gem_candidates": len(gem_ids),
        "bar_multiplier": GEM_IDENTIFICATION_RATIO_BAR,
        "personas_expected": len(PERSONA_IDS),
        "personas_evaluated_unaided": n_unaided_eval, "personas_evaluated_assisted": n_assisted_eval,
        "unaided_gems_advanced_total": unaided_total, "assisted_gems_advanced_total": assisted_total,
        "ratio": round(ratio, 4) if ratio is not None else None,
        "met": met_provisional if fully_evaluated else None,
        "met_provisional_on_available": met_provisional,
        "adjudicated_mapping": {
            "scope": "/".join(ADJUDICATED_MAPPING_SCOPE),
            "mapping": "Yes -> ADVANCE; No -> DECLINE; Maybe / any "
                        "flag-before-deciding variant -> HOLD",
            "source": "mapping drafted before mapped "
                       "totals were computed",
            "n_mapped_decisions": len(adjudicated_mapped),
        },
        "sensitivity_p07_assisted_unparsed": {
            "definition": "the same test with P07-assisted's decisions left "
                           "unparsed (mechanically parsed tokens only), so the "
                           "verdict cannot hinge silently on the mapping.",
            "unaided_gems_advanced_total": unaided_total_mech,
            "assisted_gems_advanced_total": assisted_total_mech,
            "ratio": round(ratio_mech, 4) if ratio_mech is not None else None,
            "met": met_mech if fully_evaluated else None,
        },
    }

    gem_holds_by_arm = {
        arm: {"total": sum(gems_held[arm].values()), "personas_evaluated": len(gems_held[arm])}
        for arm in PERSONA_ARMS
    }

    secondary_diagnostics = {
        "stuffers_questioned": {
            "definition": "archetype-D (keyword-stuffer) candidates in the subset where the "
                           "persona declined or held, OR flagged a non-empty "
                           "flags.claims_questioned for that candidate.",
            "candidate_ids": stuffer_ids,
            "by_arm": {arm: diagnostic_summary(stuffers_questioned[arm], len(stuffer_ids))
                       for arm in PERSONA_ARMS},
        },
        "inflations_spotted": {
            "definition": "archetype-E (credential-inflation) candidates in the subset where "
                           "the persona's flags.inconsistencies_noted is non-empty.",
            "candidate_ids": inflation_ids,
            "by_arm": {arm: diagnostic_summary(inflations_spotted[arm], len(inflation_ids))
                       for arm in PERSONA_ARMS},
        },
        "borderlines_flagged": {
            "definition": "archetype-H (genuine-borderline) candidates in the subset where "
                           "the persona's flags.borderline_calls is non-empty.",
            "candidate_ids": borderline_ids,
            "by_arm": {arm: diagnostic_summary(borderlines_flagged[arm], len(borderline_ids))
                       for arm in PERSONA_ARMS},
        },
    }

    per_persona_table = []
    for persona_id in PERSONA_IDS:
        persona_cfg = config.PERSONA_BY_ID[persona_id]
        per_persona_table.append({
            "persona_id": persona_id, "name": persona_cfg["name"], "tagline": persona_cfg["tagline"],
            "traits": persona_cfg["traits"],
            "gems_advanced_unaided": gems_advanced["unaided"].get(persona_id),
            "gems_advanced_assisted": gems_advanced["assisted"].get(persona_id),
            "stuffers_questioned_unaided": stuffers_questioned["unaided"].get(persona_id),
            "stuffers_questioned_assisted": stuffers_questioned["assisted"].get(persona_id),
        })

    return {
        "pre_registration_6": pre_reg_6,
        "gem_holds_by_arm": gem_holds_by_arm,
        "secondary_diagnostics": secondary_diagnostics,
        "decision_totals_by_arm": decision_totals,
        "per_persona_table": per_persona_table,
        "decision_parse_adjudication": adjudication,
        "adjudicated_mapped_decisions": adjudicated_mapped,
    }


def build_persona_section(candidates_df: pd.DataFrame) -> tuple[dict, bool, list[str]]:
    """Loads and validates all 24 persona files, computes pre-registration 6
    and its diagnostics over whichever pass validation, and reports its own
    completeness independently of the rest of the run. Returns
    (result_dict, is_complete, problems) -- `problems` is empty iff
    is_complete."""
    subset_ids, subset_report = load_persona_task_files()

    outputs = {(p, a): load_persona_output_file(p, a) for p in PERSONA_IDS for a in PERSONA_ARMS}
    missing_files = [f"{a}/persona_{p}.json" for (p, a), e in outputs.items() if e["status"] == "missing"]

    validation_problems: list[str] = []
    clean_outputs: dict[tuple[str, str], dict] = {}
    for key, entry in outputs.items():
        problems = validate_persona_output(entry, subset_ids)
        if problems:
            validation_problems.extend(problems)
        else:
            clean_outputs[key] = entry

    all_problems = subset_report["errors"] + subset_report["mismatched_files"] + validation_problems
    is_complete = (len(missing_files) == 0 and not all_problems
                   and subset_report["n_task_files_found"] == N_PERSONA_FILES_EXPECTED)
    n_present = N_PERSONA_FILES_EXPECTED - len(missing_files)

    experiment = persona_experiment(candidates_df, subset_ids, clean_outputs)

    result = {
        "data_completeness": {
            "banner": "COMPLETE" if is_complete else ("PARTIAL" if n_present > 0 else "PENDING"),
            "n_files_present": n_present, "n_files_expected": N_PERSONA_FILES_EXPECTED,
            "missing_files": missing_files, "validation_problems": validation_problems,
            "subset_derivation": subset_report,
        },
        "subset_size": len(subset_ids), "subset_candidate_ids": subset_ids,
        **experiment,
    }
    # all_problems already includes a formatted "<path>: missing" entry per
    # missing file (via validate_persona_output), so it alone is a complete,
    # non-duplicated problem list for logging/exit purposes.
    return result, is_complete, all_problems


# ---------------------------------------------------------------------------
# Addendum A1 -- ATS rank of the 22 keyword stuffers.
# ---------------------------------------------------------------------------

def addendum_1(key_df: pd.DataFrame, ats_df: pd.DataFrame) -> dict:
    d_ids = key_df.loc[key_df["archetype"] == "D", "candidate_id"].unique().tolist()
    ranks = ats_df.set_index("candidate_id").loc[d_ids, ["rank", "total_score"]]
    above_median = ranks[ranks["rank"] <= ATS_POOL_MEDIAN_RANK]
    return {
        "definition": f"count of D (keyword-stuffer) candidates the ATS ranks at or "
                       f"above the pool median (rank <= {ATS_POOL_MEDIAN_RANK} of 240)",
        "total_stuffers": len(d_ids), "above_median": int(len(above_median)),
        "bar": A1_STUFFERS_ABOVE_MEDIAN_BAR, "met": len(above_median) >= A1_STUFFERS_ABOVE_MEDIAN_BAR,
        "detail": [{"candidate_id": cid, "rank": int(r["rank"]), "score": int(r["total_score"])}
                   for cid, r in ranks.sort_values("rank").iterrows()],
    }


# ---------------------------------------------------------------------------
# Addendum A2 -- ATS hits on the 18 hidden gems' displaced requirement.
# ---------------------------------------------------------------------------

def addendum_2(key_df: pd.DataFrame, ats_df: pd.DataFrame) -> dict:
    f_rows = key_df[(key_df["archetype"] == "F") & (key_df["displaced"] == True)]  # noqa: E712
    ats_by_id = ats_df.set_index("candidate_id")
    detail = []
    hit_count = 0
    for row in f_rows.itertuples():
        hit = int(ats_by_id.loc[row.candidate_id, f"{row.requirement_id}_hit"])
        hit_count += hit
        detail.append({"candidate_id": row.candidate_id, "requirement_id": row.requirement_id,
                        "displaced_phrase": row.displaced_phrase, "ats_hit": hit})
    return {
        "definition": "count of F (hidden-gem) candidates where the ATS's own keyword "
                       "hit flag fires for the displaced requirement, despite the "
                       "evidence being written under displaced vocabulary",
        "total_gems": len(f_rows), "ats_hits": hit_count,
        "bar": A2_ATS_GEM_HIT_MAX, "met": hit_count <= A2_ATS_GEM_HIT_MAX,
        "detail": detail,
    }


# ---------------------------------------------------------------------------
# Addendum A3 -- naive invented-evidence rate vs disciplined citation-failure
# rate, same model, same pool.
# ---------------------------------------------------------------------------

def addendum_3(key_df: pd.DataFrame, naive_responses: dict[str, dict],
               arm3_citation_failures: list[dict], arm3_total_lines: int) -> dict:
    key_by_pair = key_df.set_index(["candidate_id", "requirement_id"])["status"]
    yes_calls = 0
    unsupported = 0
    detail = []
    for cid, response in naive_responses.items():
        for r in response.get("requirements", []):
            rid = r["requirement_id"]
            if rid not in config.MUST_HAVE_IDS:
                continue
            if r.get("met") != "yes":
                continue
            yes_calls += 1
            key_status = key_by_pair.get((cid, rid))
            if key_status in ("absent", "not_stated"):
                unsupported += 1
                detail.append({"candidate_id": cid, "requirement_id": rid,
                                "key_status": key_status, "naive_reason": r.get("reason")})

    naive_rate_pct = (unsupported / yes_calls * 100) if yes_calls else None
    disciplined_rate_pct = (len(arm3_citation_failures) / arm3_total_lines * 100) if arm3_total_lines else None

    return {
        "definition": "naive: fraction of the naive arm's must-have 'yes' calls where "
                       "the key records the requirement absent/not_stated (an "
                       "unsupported assertion -- no refuse-to-guess gate exists in the "
                       "naive contract to catch it). disciplined: arm-3 citation-failure "
                       "rate computed by the identical assemble_dossiers verbatim-quote "
                       "verification used for arm 4, over whatever arm-3 batches are "
                       "currently available.",
        "naive_must_have_yes_calls": yes_calls, "naive_unsupported_yes_calls": unsupported,
        "naive_unsupported_rate_pct": round(naive_rate_pct, 4) if naive_rate_pct is not None else None,
        "disciplined_citation_failures": len(arm3_citation_failures),
        "disciplined_total_quoted_lines": arm3_total_lines,
        "disciplined_citation_failure_rate_pct": round(disciplined_rate_pct, 4) if disciplined_rate_pct is not None else None,
        "met": (naive_rate_pct is not None and disciplined_rate_pct is not None
                and naive_rate_pct > disciplined_rate_pct),
        "sample_unsupported_calls": detail[:25],
        "n_unsupported_calls_total": len(detail),
    }


# ---------------------------------------------------------------------------
# Addendum A4 -- the hero claim.
# ---------------------------------------------------------------------------

def addendum_4(gems3: dict, addendum2: dict, stuffers3: dict, addendum1: dict) -> dict:
    """Compares arm 3 (disciplined small model) against arm 1 (ATS) on both
    A4 counts at once. The ATS side of each comparison has no direct
    equivalent to "surfaced" / "flagged as unsubstantiated" -- it only ranks
    -- so the ATS-side numbers here are DERIVED, and the derivation is
    printed rather than assumed:
      - gems: A2's own count (ATS keyword-hit fires on the displaced
        requirement) is already exactly "does the ATS surface the displaced
        skill" -- used as-is.
      - stuffers: the ATS has no "identified as unsubstantiated" signal, so
        its analogue is "ranked at or below the pool median" -- i.e. NOT
        promoted above the median the way A1 measures -- which is
        (22 - A1's above-median count). This is a judgment call, flagged
        here rather than silently assumed.
    Both sides are compared as RATES (caught / evaluated) rather than raw
    counts, so a partial arm-3 run is still a fair, if provisional,
    comparison; the raw counts are also reported.
    """
    gems3_rate = gems3["rate"]
    ats_gems_rate = addendum2["ats_hits"] / addendum2["total_gems"]
    beats_gems = gems3_rate is not None and gems3_rate > ats_gems_rate

    stuffers3_rate = stuffers3["rate"]
    ats_stuffers_correctly_deprioritised = addendum1["total_stuffers"] - addendum1["above_median"]
    ats_stuffers_rate = ats_stuffers_correctly_deprioritised / addendum1["total_stuffers"]
    beats_stuffers = stuffers3_rate is not None and stuffers3_rate > ats_stuffers_rate

    return {
        "definition": "the falsifiable hero claim: the disciplined small-model arm "
                       "(arm 3) beats the ATS (arm 1) on BOTH counts at once.",
        "judgment_call": "ATS 'stuffers correctly identified' has no direct analogue "
                          "(the ATS only ranks); derived here as "
                          "(22 - A1's above-median count), i.e. stuffers the ATS did "
                          "NOT promote above the pool median.",
        "gems": {
            "arm3_caught": gems3["caught"], "arm3_evaluated": gems3["evaluated"],
            "arm3_rate": round(gems3_rate, 4) if gems3_rate is not None else None,
            "ats_hits": addendum2["ats_hits"], "ats_total": addendum2["total_gems"],
            "ats_rate": round(ats_gems_rate, 4), "arm3_beats_ats": beats_gems,
        },
        "stuffers": {
            "arm3_success": stuffers3["success"], "arm3_evaluated": stuffers3["evaluated"],
            "arm3_rate": round(stuffers3_rate, 4) if stuffers3_rate is not None else None,
            "ats_correctly_deprioritised": ats_stuffers_correctly_deprioritised,
            "ats_total": addendum1["total_stuffers"], "ats_rate": round(ats_stuffers_rate, 4),
            "arm3_beats_ats": beats_stuffers,
        },
        "met": bool(beats_gems and beats_stuffers),
        "provisional": gems3["evaluated"] < gems3["total_gems"] or stuffers3["evaluated"] < stuffers3["total_stuffers"],
    }


# ---------------------------------------------------------------------------
# Item 11 -- cross-arm contradiction table (the 15 planted E-contradictions).
# ---------------------------------------------------------------------------

def contradiction_table(key_df: pd.DataFrame, arm4_dossiers: dict[str, dict],
                         arm3_dossiers: dict[str, dict], naive_responses: dict[str, dict]) -> dict:
    e_rows = key_df[key_df["contradiction_code"].notna()]
    rows_out = []
    for row in e_rows.itertuples():
        cid, rid = row.candidate_id, row.requirement_id

        d4 = arm4_dossiers.get(cid)
        e4 = next((r for r in d4["requirements"] if r["requirement_id"] == rid), None) if d4 else None
        caught4 = e4["status"] == "contradiction" if e4 else None

        d3 = arm3_dossiers.get(cid)
        e3 = next((r for r in d3["requirements"] if r["requirement_id"] == rid), None) if d3 else None
        caught3 = (e3["status"] == "contradiction") if e3 else None

        naive_resp = naive_responses.get(cid)
        naive_entry = next((r for r in naive_resp["requirements"] if r["requirement_id"] == rid), None) if naive_resp else None
        naive_reason = naive_entry.get("reason", "") if naive_entry else ""
        caught_naive = bool(CONTRADICTION_INDICATOR_REGEX.search(naive_reason)) if naive_entry else None

        rows_out.append({
            "candidate_id": cid, "requirement_id": rid, "contradiction_code": row.contradiction_code,
            "caught_arm4": caught4, "caught_arm3": caught3, "caught_naive": caught_naive,
            "arm4_note": (e4.get("note") if e4 else None),
        })

    def rate(key):
        vals = [r[key] for r in rows_out if r[key] is not None]
        return {"caught": sum(vals), "evaluated": len(vals)} if vals else {"caught": 0, "evaluated": 0}

    return {
        "definition": "the 15 candidates whose key row carries a planted contradiction_code "
                       "(E archetype, R05 degree-date or R08 title-inflation). 'caught_naive' "
                       "is conservative: True only if the naive arm's free-text reason for "
                       "that requirement matches the regex "
                       f"{CONTRADICTION_INDICATOR_REGEX.pattern!r} -- the naive contract has "
                       "no contradiction status of its own, so this likely undercounts rather "
                       "than overcounts.",
        "n_planted": len(e_rows),
        "summary": {"arm4": rate("caught_arm4"), "arm3": rate("caught_arm3"), "naive": rate("caught_naive")},
        "rows": rows_out,
    }


# ---------------------------------------------------------------------------
# Item 13 -- adjudication list: arm-4 contradiction calls NOT matching a
# planted E-contradiction. Never auto-resolved.
# ---------------------------------------------------------------------------

def adjudication_list(key_df: pd.DataFrame, arm4_dossiers: dict[str, dict]) -> dict:
    planted = set(zip(key_df.loc[key_df["contradiction_code"].notna(), "candidate_id"],
                       key_df.loc[key_df["contradiction_code"].notna(), "requirement_id"]))
    key_status_by_pair = key_df.set_index(["candidate_id", "requirement_id"])["status"]

    items = []
    for cid, dossier in arm4_dossiers.items():
        for entry in dossier["requirements"]:
            if entry["status"] != "contradiction":
                continue
            rid = entry["requirement_id"]
            if (cid, rid) in planted:
                continue  # correctly caught a planted contradiction -- not an adjudication item
            items.append({
                "candidate_id": cid, "requirement_id": rid,
                "key_status": key_status_by_pair.get((cid, rid)),
                "dossier_note": entry.get("note"),
                "quotes": [line["quote"] for line in entry.get("lines", [])],
                "pre_logged": cid == "C079",
            })

    items.sort(key=lambda x: x["candidate_id"])
    return {
        "definition": "every arm-4 requirement marked 'contradiction' whose (candidate, "
                       "requirement) pair is NOT one of the 15 planted E-contradiction rows. "
                       "This includes true extractor errors (hallucinated or misread "
                       "contradictions -- see C022, C039) and genuine "
                       "corpus inconsistencies found after the extraction run (C079, "
                       "pre-logged as frozen for adjudication). NONE of "
                       "these are auto-resolved here -- this is a list for a human to read, "
                       "not a verdict.",
        "n_items": len(items),
        "items": items,
    }


# ---------------------------------------------------------------------------
# Item 12 -- the matched pair for the interactive page.
# ---------------------------------------------------------------------------

def four_arm_snapshot(cid: str, key_df: pd.DataFrame, ats_df: pd.DataFrame,
                       naive_responses: dict, arm3_dossiers: dict, arm4_dossiers: dict) -> dict:
    key_rows = key_df[(key_df["candidate_id"] == cid) & (key_df["requirement_id"].isin(config.MUST_HAVE_IDS))]
    ats_row = ats_df.set_index("candidate_id").loc[cid] if cid in ats_df["candidate_id"].values else None
    naive_resp = naive_responses.get(cid)
    naive_by_id = {r["requirement_id"]: r for r in naive_resp["requirements"]} if naive_resp else {}
    d3 = arm3_dossiers.get(cid)
    d3_by_id = {r["requirement_id"]: r for r in d3["requirements"]} if d3 else {}
    d4 = arm4_dossiers.get(cid)
    d4_by_id = {r["requirement_id"]: r for r in d4["requirements"]} if d4 else {}

    per_requirement = {}
    for row in key_rows.itertuples():
        rid = row.requirement_id
        per_requirement[rid] = {
            "key_status": row.status,
            "ats_hit": (int(ats_row[f"{rid}_hit"]) if ats_row is not None else None),
            "naive_met": naive_by_id.get(rid, {}).get("met"),
            "arm3_status": d3_by_id.get(rid, {}).get("status") if d3 else "not yet extracted",
            "arm4_status": d4_by_id.get(rid, {}).get("status"),
        }
    return {
        "candidate_id": cid,
        "ats_rank": int(ats_row["rank"]) if ats_row is not None else None,
        "ats_score": int(ats_row["total_score"]) if ats_row is not None else None,
        "must_have_reads": per_requirement,
    }


def matched_pair(key_df: pd.DataFrame, candidates_df: pd.DataFrame, ats_df: pd.DataFrame,
                  naive_responses: dict, arm3_dossiers: dict, arm4_dossiers: dict) -> dict:
    ats_by_id = ats_df.set_index("candidate_id")["rank"]

    # Gem: F candidate with the largest (ATS rank - qualification) gap, where
    # qualification is must_have_pass_count from the candidate summary (5 for
    # every F candidate in this corpus, since F is defined as fully
    # qualified -- flagged here rather than assumed, since the formula is
    # applied generically).
    f_candidates = candidates_df[candidates_df["archetype"] == "F"].copy()
    f_candidates["ats_rank"] = f_candidates["candidate_id"].map(ats_by_id)
    f_candidates["gap"] = f_candidates["ats_rank"] - f_candidates["must_have_pass_count"]
    gem_row = f_candidates.sort_values(["gap", "candidate_id"], ascending=[False, True]).iloc[0]

    # Stuffer: D candidate with the smallest ATS rank (ranked best despite
    # unsubstantiated must-have claims).
    d_candidates = candidates_df[candidates_df["archetype"] == "D"].copy()
    d_candidates["ats_rank"] = d_candidates["candidate_id"].map(ats_by_id)
    stuffer_row = d_candidates.sort_values(["ats_rank", "candidate_id"], ascending=[True, True]).iloc[0]

    return {
        "selection_rule": "Frozen rule: the gem with the largest (ATS rank - "
                           "qualification) gap [qualification = must_have_pass_count, "
                           "5 for every F candidate here, so this reduces to the "
                           "worst-ATS-ranked fully-qualified candidate] and the stuffer "
                           "with the smallest ATS rank. Selected from marked results, "
                           "never hand-picked.",
        "missed_star": {
            "candidate_id": gem_row["candidate_id"], "archetype": "F",
            "must_have_pass_count": int(gem_row["must_have_pass_count"]),
            "ats_rank": int(gem_row["ats_rank"]), "gap": float(gem_row["gap"]),
            "four_arm_read": four_arm_snapshot(gem_row["candidate_id"], key_df, ats_df,
                                                naive_responses, arm3_dossiers, arm4_dossiers),
        },
        "false_positive": {
            "candidate_id": stuffer_row["candidate_id"], "archetype": "D",
            "ats_rank": int(stuffer_row["ats_rank"]),
            "four_arm_read": four_arm_snapshot(stuffer_row["candidate_id"], key_df, ats_df,
                                                naive_responses, arm3_dossiers, arm4_dossiers),
        },
    }


# ---------------------------------------------------------------------------
# Report writer -- plain markdown tables, no styling.
# ---------------------------------------------------------------------------

def fmt(x, suffix=""):
    if x is None:
        return "n/a"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, float):
        return f"{x:.2f}{suffix}"
    return f"{x}{suffix}"


def verdict_str(met) -> str:
    if met is None:
        return "PARTIAL (see detail)"
    return "MET" if met else "NOT MET"


def write_report(results: dict, path: Path) -> None:
    r = results
    lines = []
    lines.append("# Case 10 -- marking scorecard\n")
    lines.append(f"Generated by `code/mark_results.py`. Data-completeness banner: "
                 f"**{r['data_status']['banner']}**\n")

    lines.append("## Data completeness\n")
    dc = r["data_status"]
    lines.append(f"- Arm 1 (ATS): {dc['arm1_candidates']} candidates.")
    lines.append(f"- Arm 2 (naive): {dc['arm2_candidates']} candidates, "
                 f"{len(dc['arm2_missing_batches'])} batch(es) missing.")
    lines.append(f"- Arm 3 (disciplined): {dc['arm3_candidates']} candidates "
                 f"across {dc['arm3_present_batches']} of {dc['arm3_total_batches']} batches. "
                 f"Missing: {dc['arm3_missing_batches'] or 'none'}.")
    lines.append(f"- Arm 4 (workflow): {dc['arm4_candidates']} candidates.")
    dc6 = r["personas"]["data_completeness"]
    lines.append(f"- Persona experiment (pre-reg 6): {dc6['n_files_present']}/"
                 f"{dc6['n_files_expected']} output files present ({dc6['banner']}).\n")

    lines.append("## Pre-registrations\n")
    lines.append("| # | Registration | Result | Verdict |")
    lines.append("|---|---|---|---|")
    p1, p2, p3, p4, p5 = r["pre_registrations"]["1"], r["pre_registrations"]["2"], r["pre_registrations"]["3"], r["pre_registrations"]["4"], r["pre_registrations"]["5"]
    p6 = r["pre_registrations"]["6"]
    lines.append(f"| 1 | Evidence recall >= {p1['bar']*100:.0f}% | {fmt(p1['recall'])} "
                 f"({p1['found']}/{p1['evidenced_must_have_rows']}) | {verdict_str(p1['met'])} |")
    lines.append(f"| 2 | Invented evidence < {p2['bar_pct']}% (fabrications) | "
                 f"{fmt(p2['fabrication_rate_pct'], '%')} ({p2['n_fabrication']} fabrication, "
                 f"{p2['n_transcription']} transcription, of {p2['total_citation_failures']} failures / "
                 f"{p2['total_quoted_lines']} lines) | {verdict_str(p2['met'])} |")
    lines.append(f"| 3 | Hidden gems >= {p3['bar']}/{p3['total_gems']} | "
                 f"{p3['caught']}/{p3['evaluated']} evaluated | {verdict_str(p3['met'])} |")
    lines.append(f"| 4 | Stuffers >= {p4['bar']}/{p4['total_stuffers']} | "
                 f"{p4['success']}/{p4['evaluated']} evaluated | {verdict_str(p4['met'])} |")
    lines.append(f"| 5 | Parity <= {p5['bar_pp']}pp | see stratum tables below | "
                 f"{verdict_str(all(d['recall_parity_met'] and (d['flag_parity_met'] in (True, None)) for d in p5['dimensions'].values()))} |")
    sens = p6["sensitivity_p07_assisted_unparsed"]
    lines.append(f"| 6 | With-dossier >= {p6['bar_multiplier']:g}x unaided (hidden gems) | "
                 f"assisted {p6['assisted_gems_advanced_total']} vs unaided "
                 f"{p6['unaided_gems_advanced_total']} (ratio {fmt(p6['ratio'])}, "
                 f"{p6['personas_evaluated_unaided']}/{p6['personas_expected']} unaided + "
                 f"{p6['personas_evaluated_assisted']}/{p6['personas_expected']} assisted personas "
                 f"evaluated; sensitivity with P07-assisted unparsed: "
                 f"{sens['assisted_gems_advanced_total']} vs "
                 f"{sens['unaided_gems_advanced_total']}, ratio {fmt(sens['ratio'])}, "
                 f"{verdict_str(sens['met'])}) | {verdict_str(p6['met'])} |\n")

    lines.append("## Addendum arms\n")
    a1, a2, a3, a4 = r["addenda"]["A1"], r["addenda"]["A2"], r["addenda"]["A3"], r["addenda"]["A4"]
    lines.append("| # | Registration | Result | Verdict |")
    lines.append("|---|---|---|---|")
    lines.append(f"| A1 | ATS ranks >= {a1['bar']}/22 stuffers above median | "
                 f"{a1['above_median']}/22 | {verdict_str(a1['met'])} |")
    lines.append(f"| A2 | ATS surfaces displaced skill for <= {a2['bar']}/18 gems | "
                 f"{a2['ats_hits']}/18 | {verdict_str(a2['met'])} |")
    lines.append(f"| A3 | naive invented-evidence rate > disciplined citation-failure rate | "
                 f"naive {fmt(a3['naive_unsupported_rate_pct'], '%')} vs disciplined "
                 f"{fmt(a3['disciplined_citation_failure_rate_pct'], '%')} | {verdict_str(a3['met'])} |")
    lines.append(f"| A4 | hero: disciplined beats ATS on both gems AND stuffers | "
                 f"gems {a4['gems']['arm3_beats_ats']}, stuffers {a4['stuffers']['arm3_beats_ats']} "
                 f"({'PROVISIONAL -- arm 3 incomplete' if a4['provisional'] else 'final'}) | "
                 f"{verdict_str(a4['met'])} |\n")

    lines.append("## Pre-reg 3 detail -- hidden gems (arm 4)\n")
    lines.append("| candidate | requirement | displaced phrase | dossier status | caught |")
    lines.append("|---|---|---|---|---|")
    for g in p3["per_gem"]:
        lines.append(f"| {g['candidate_id']} | {g['requirement_id']} | {g['displaced_phrase']} | "
                     f"{g['status']} | {fmt(g['caught'])} |")
    lines.append("")

    lines.append("## Pre-reg 4 detail -- stuffers (arm 4)\n")
    lines.append("| candidate | claimed must-haves | marked claim_only | fraction | success |")
    lines.append("|---|---|---|---|---|")
    for s in p4["per_stuffer"]:
        lines.append(f"| {s['candidate_id']} | {s['claimed_must_haves']} | {fmt(s['marked_claim_only'])} | "
                     f"{fmt(s['fraction'])} | {fmt(s['success'])} |")
    lines.append("")

    lines.append("## Stratum parity, all four arms (pre-reg 5 + item 14)\n")
    for arm_key, arm_result in r["parity"].items():
        lines.append(f"### {arm_result['arm']}\n")
        lines.append(f"_{arm_result['flag_method_note']}_\n")
        lines.append("| dimension | recall spread (pp) | recall parity | flag spread (pp) | flag parity |")
        lines.append("|---|---|---|---|---|")
        for dim, d in arm_result["dimensions"].items():
            lines.append(f"| {dim} | {fmt(d['recall_spread_pp'])} | {fmt(d['recall_parity_met'])} | "
                         f"{fmt(d['flag_spread_pp'])} | {fmt(d['flag_parity_met'])} |")
        lines.append("")

    lines.append("## Cross-arm contradiction table (item 11) -- 15 planted E-contradictions\n")
    ct = r["contradiction_table"]
    lines.append(f"_{ct['definition']}_\n")
    lines.append("| candidate | requirement | code | arm4 caught | arm3 caught | naive caught |")
    lines.append("|---|---|---|---|---|---|")
    for row in ct["rows"]:
        lines.append(f"| {row['candidate_id']} | {row['requirement_id']} | {row['contradiction_code']} | "
                     f"{fmt(row['caught_arm4'])} | {fmt(row['caught_arm3'])} | {fmt(row['caught_naive'])} |")
    s = ct["summary"]
    lines.append(f"\nSummary: arm4 {s['arm4']['caught']}/{s['arm4']['evaluated']}, "
                 f"arm3 {s['arm3']['caught']}/{s['arm3']['evaluated']}, "
                 f"naive {s['naive']['caught']}/{s['naive']['evaluated']}.\n")

    lines.append("## Matched pair (item 12)\n")
    mp = r["matched_pair"]
    lines.append(f"_{mp['selection_rule']}_\n")
    for label, key in [("Missed star (hidden gem)", "missed_star"), ("False positive (stuffer)", "false_positive")]:
        ex = mp[key]
        lines.append(f"### {label}: {ex['candidate_id']} (ATS rank {ex['ats_rank']})\n")
        lines.append("| requirement | key status | ATS hit | naive met | arm3 status | arm4 status |")
        lines.append("|---|---|---|---|---|---|")
        for rid, d in ex["four_arm_read"]["must_have_reads"].items():
            lines.append(f"| {rid} | {d['key_status']} | {fmt(d['ats_hit'])} | {fmt(d['naive_met'])} | "
                         f"{d['arm3_status']} | {d['arm4_status']} |")
        lines.append("")

    lines.append("## Adjudication list (item 13) -- arm-4 contradiction calls NOT matching a "
                 "planted E-contradiction\n")
    lines.append("**Not auto-resolved.** For a human to read and adjudicate.\n")
    adj = r["adjudication_list"]
    for item in adj["items"]:
        flag = " **[pre-logged]**" if item["pre_logged"] else ""
        lines.append(f"- **{item['candidate_id']} / {item['requirement_id']}**{flag} -- key status: "
                     f"`{item['key_status']}`. Dossier note: {item['dossier_note'] or '(none)'}")
        for q in item["quotes"]:
            lines.append(f"    - quote: \"{q}\"")
    lines.append("")

    lines.append("## Citation-failure classification (pre-reg 2 detail)\n")
    lines.append("| candidate | requirement | source | similarity | classification |")
    lines.append("|---|---|---|---|---|")
    for c in p2["classified"]:
        lines.append(f"| {c['candidate_id']} | {c['requirement_id']} | {c['source']} | "
                     f"{c['similarity']:.3f} | {c['classification']} |")
    lines.append("")

    lines.append("## Persona experiment detail (pre-registration 6, 18 Sep 2026)\n")
    pr = r["personas"]
    lines.append(f"Data completeness: {dc6['n_files_present']}/{dc6['n_files_expected']} persona "
                 f"output files present ({dc6['banner']}). Missing: {dc6['missing_files'] or 'none'}.\n")
    if dc6["validation_problems"]:
        lines.append(f"Validation problems ({len(dc6['validation_problems'])}):")
        for problem in dc6["validation_problems"]:
            lines.append(f"- {problem}")
        lines.append("")

    lines.append(f"_{p6['definition']}_\n")
    lines.append("| metric | unaided | assisted |")
    lines.append("|---|---|---|")
    lines.append(f"| gems advanced (total) | {p6['unaided_gems_advanced_total']} | "
                 f"{p6['assisted_gems_advanced_total']} |")
    lines.append(f"| personas evaluated | {p6['personas_evaluated_unaided']}/{p6['personas_expected']} | "
                 f"{p6['personas_evaluated_assisted']}/{p6['personas_expected']} |")
    gh = pr["gem_holds_by_arm"]
    lines.append(f"| gems held (not counted as identified) | {gh['unaided']['total']} | "
                 f"{gh['assisted']['total']} |")
    lines.append(f"\nRatio (assisted/unaided): {fmt(p6['ratio'])}, bar {p6['bar_multiplier']:g}x "
                 f"-> {verdict_str(p6['met'])}\n")

    am = p6["adjudicated_mapping"]
    lines.append(f"**Adjudicated mapping in effect** (scope {am['scope']}, "
                 f"{am['n_mapped_decisions']} decision(s) mapped): {am['mapping']}. "
                 f"Source: {am['source']}.\n")
    lines.append(f"**Sensitivity variant -- P07-assisted left unparsed**: assisted "
                 f"{sens['assisted_gems_advanced_total']} vs unaided "
                 f"{sens['unaided_gems_advanced_total']}, ratio {fmt(sens['ratio'])}, "
                 f"bar {p6['bar_multiplier']:g}x -> {verdict_str(sens['met'])}. "
                 f"{sens['definition']}\n")

    lines.append("### Secondary diagnostics (reported, not pre-registered)\n")
    lines.append("| diagnostic | unaided total | unaided rate | assisted total | assisted rate |")
    lines.append("|---|---|---|---|---|")
    for key, label in [("stuffers_questioned", "stuffers questioned (D)"),
                        ("inflations_spotted", "inflations spotted (E)"),
                        ("borderlines_flagged", "borderlines flagged (H)")]:
        d = pr["secondary_diagnostics"][key]
        u, a = d["by_arm"]["unaided"], d["by_arm"]["assisted"]
        lines.append(f"| {label} | {u['total']} | {fmt(u['rate'])} | {a['total']} | {fmt(a['rate'])} |")
    lines.append("")

    lines.append("### Per-arm decision totals\n")
    lines.append("| arm | advance | hold | decline | unparsed | adjudicated-mapped | personas evaluated |")
    lines.append("|---|---|---|---|---|---|---|")
    for arm in ("unaided", "assisted"):
        dt = pr["decision_totals_by_arm"][arm]
        lines.append(f"| {arm} | {dt['ADVANCE']} | {dt['HOLD']} | {dt['DECLINE']} | "
                     f"{dt['unparsed']} | {dt['adjudicated_mapped']} | {dt['personas_evaluated']} |")
    lines.append("\n(adjudicated-mapped decisions are included in the advance/hold/decline "
                 "columns; the count shows how many of them arrived via the logged "
                 "P07-assisted mapping rather than the mechanical parser.)\n")

    lines.append("### Per-persona table\n")
    lines.append("| persona | name | tagline | strictness | keyword_reliance | time_discipline | "
                 "gems adv. unaided | gems adv. assisted | stuffers q. unaided | stuffers q. assisted |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for row in pr["per_persona_table"]:
        t = row["traits"]
        lines.append(f"| {row['persona_id']} | {row['name']} | {row['tagline']} | "
                     f"{fmt(t['strictness'])} | {fmt(t['keyword_reliance'])} | "
                     f"{fmt(t['time_discipline'])} | {fmt(row['gems_advanced_unaided'])} | "
                     f"{fmt(row['gems_advanced_assisted'])} | {fmt(row['stuffers_questioned_unaided'])} | "
                     f"{fmt(row['stuffers_questioned_assisted'])} |")
    lines.append("")

    lines.append("### Adjudicated-mapped decisions (logged mapping, not the mechanical parser)\n")
    mapped_p = pr["adjudicated_mapped_decisions"]
    if not mapped_p:
        lines.append("None -- the P07-assisted mapping never fired.\n")
    else:
        lines.append(f"**{len(mapped_p)} decision(s) mapped** under the "
                     "logged mapping. Compact listing "
                     "(candidate -> mapped token):\n")
        compact = ", ".join(f"{m['candidate_id']}->{m['mapped_to']}" for m in mapped_p)
        lines.append(compact + "\n")

    lines.append("### Decision-parse adjudication -- never guessed\n")
    adj_p = pr["decision_parse_adjudication"]
    if not adj_p:
        lines.append("None -- every screening_decision parsed mechanically or via "
                     "the logged adjudicated mapping above.\n")
    else:
        lines.append(f"**{len(adj_p)} screening_decision(s) did not parse.** Not guessed, not "
                     "counted as advance/hold/decline anywhere above.\n")
        for item in adj_p:
            lines.append(f"- **{item['candidate_id']} / {item['persona_id']} / {item['arm']}** -- "
                         f"raw text: \"{item['raw_text']}\"")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-complete", action="store_true",
                         help="exit 1 if arm 3 (disciplined_raw) is missing any batch, "
                              "instead of marking whatever is available and exiting 0")
    args = parser.parse_args()

    log("loading the answer key -- the only script permitted to do this")
    key_df = load_key()
    candidates_df = load_candidates()
    check_shape = key_df.shape
    log(f"answer_key.csv: {check_shape[0]} rows; answer_key_candidates.csv: {len(candidates_df)} rows")

    log("loading applications (for citation verification, arm 3 + pre-reg 2)")
    applications = assemble_dossiers.load_applications()

    log("loading arm 4 (full workflow, Sonnet) dossiers")
    arm4_dossiers = load_arm4_dossiers()
    arm4_citation_failures = load_arm4_citation_failures()
    log(f"arm 4: {len(arm4_dossiers)} dossiers, {len(arm4_citation_failures)} citation failures")

    log("loading arm 1 (ATS baseline)")
    ats_df, ats_cv_only_df = load_ats()

    log("loading arm 2 (naive local LLM)")
    naive_responses, naive_present, naive_missing = load_naive()
    log(f"arm 2: {len(naive_responses)} candidates across {len(naive_present)} batches "
        f"({len(naive_missing)} missing)")

    log("loading arm 3 (disciplined local LLM) -- may be partial")
    disciplined_responses, disc_present, disc_missing = load_disciplined_raw()
    log(f"arm 3: {len(disciplined_responses)} candidates across {len(disc_present)} of "
        f"{config.N_BATCHES} batches ({len(disc_missing)} missing: {disc_missing})")
    arm3_dossiers, arm3_citation_failures, arm3_total_lines = build_arm3_dossiers(
        disciplined_responses, applications)
    log(f"arm 3: assembled {len(arm3_dossiers)} dossiers, {len(arm3_citation_failures)} "
        f"citation failures out of {arm3_total_lines} quoted lines")

    arm3_complete = len(disc_missing) == 0
    if not arm3_complete:
        log("=" * 70)
        log("PARTIAL RUN: arm 3 (disciplined_raw) is missing "
            f"{len(disc_missing)}/{config.N_BATCHES} batches: {disc_missing}")
        log("Every A3/A4/pre-reg-3/pre-reg-4/pre-reg-5/item-11 number touching arm 3 is "
            "computed over the AVAILABLE candidates only and is marked provisional below.")
        log("=" * 70)

    data_status = {
        "banner": "PARTIAL -- arm 3 incomplete" if not arm3_complete else "COMPLETE",
        "arm1_candidates": len(ats_df),
        "arm2_candidates": len(naive_responses), "arm2_missing_batches": naive_missing,
        "arm3_candidates": len(disciplined_responses),
        "arm3_present_batches": len(disc_present), "arm3_total_batches": config.N_BATCHES,
        "arm3_missing_batches": disc_missing,
        "arm4_candidates": len(arm4_dossiers),
    }

    log("pre-registration 1 -- evidence recall")
    pr1 = preregistration_1(key_df, arm4_dossiers)
    log(f"  recall = {pr1['recall']} (bar {pr1['bar']}) -> {verdict_str(pr1['met'])}")

    log("pre-registration 2 -- invented evidence classification")
    pr2 = preregistration_2(arm4_citation_failures, arm4_dossiers, applications)
    log(f"  fabrication rate = {pr2['fabrication_rate_pct']}% (bar {pr2['bar_pct']}%) -> {verdict_str(pr2['met'])}")

    log("pre-registration 3 -- hidden gems (arm 4)")
    pr3 = gems_surfaced(key_df, arm4_dossiers, "arm4_workflow")
    log(f"  {pr3['caught']}/{pr3['evaluated']} -> {verdict_str(pr3['met'])}")

    log("pre-registration 4 -- stuffers (arm 4)")
    pr4 = stuffers_flagged(key_df, arm4_dossiers, "arm4_workflow")
    log(f"  {pr4['success']}/{pr4['evaluated']} -> {verdict_str(pr4['met'])}")

    log("pre-registration 5 -- stratum parity, all four arms")
    marks4 = marks_from_dossiers(arm4_dossiers)
    marks3 = marks_from_dossiers(arm3_dossiers)
    marks1 = marks_from_ats(ats_df)
    marks2 = marks_from_naive(naive_responses)
    parity = {
        "arm1_ats": parity_report(marks1, key_df, candidates_df, "arm1_ats", compute_flag=False,
                                   flag_method_note="The ATS has no flag/contradiction concept -- "
                                                     "flag-rate parity is not applicable for this arm."),
        "arm2_naive": parity_report(marks2, key_df, candidates_df, "arm2_naive", compute_flag=True,
                                     flag_method_note="Flag = the same conservative contradiction-"
                                                       "indicator regex used in the cross-arm table, "
                                                       "applied to every requirement's free-text reason "
                                                       "-- a proxy, not a real status; this is the "
                                                       "design-flagged headline candidate for a real "
                                                       "parity gap, since the naive contract has no "
                                                       "refuse-to-guess gate."),
        "arm3_disciplined": parity_report(marks3, key_df, candidates_df, "arm3_disciplined", compute_flag=True,
                                           flag_method_note="Flag = dossier status == contradiction. "
                                                             "PARTIAL: computed over available arm-3 "
                                                             "candidates only." if not arm3_complete else
                                                             "Flag = dossier status == contradiction."),
        "arm4_workflow": parity_report(marks4, key_df, candidates_df, "arm4_workflow", compute_flag=True,
                                        flag_method_note="Flag = dossier status == contradiction."),
    }
    pr5 = parity["arm4_workflow"]
    log(f"  arm4 max recall spread across dims: "
        f"{max(d['recall_spread_pp'] for d in pr5['dimensions'].values())}pp")

    log("pre-registration 6 -- persona experiment (unaided vs assisted hidden-gem identification)")
    persona_section, personas_complete, persona_problems = build_persona_section(candidates_df)
    pr6 = persona_section["pre_registration_6"]
    dc6 = persona_section["data_completeness"]
    log(f"  {dc6['n_files_present']}/{dc6['n_files_expected']} persona files present "
        f"({dc6['banner']}); gems advanced unaided={pr6['unaided_gems_advanced_total']} "
        f"({pr6['personas_evaluated_unaided']} personas), "
        f"assisted={pr6['assisted_gems_advanced_total']} ({pr6['personas_evaluated_assisted']} "
        f"personas) -> {verdict_str(pr6['met'])}")
    sens6 = pr6["sensitivity_p07_assisted_unparsed"]
    log(f"  adjudicated mapping ({pr6['adjudicated_mapping']['scope']}): "
        f"{pr6['adjudicated_mapping']['n_mapped_decisions']} decision(s) mapped; "
        f"sensitivity with P07-assisted unparsed: assisted="
        f"{sens6['assisted_gems_advanced_total']} vs unaided="
        f"{sens6['unaided_gems_advanced_total']} -> {verdict_str(sens6['met'])}")

    log("addendum A1 -- ATS rank of stuffers")
    a1 = addendum_1(key_df, ats_df)
    log(f"  {a1['above_median']}/22 above median -> {verdict_str(a1['met'])}")

    log("addendum A2 -- ATS hits on hidden gems")
    a2 = addendum_2(key_df, ats_df)
    log(f"  {a2['ats_hits']}/18 -> {verdict_str(a2['met'])}")

    log("addendum A3 -- naive invented-evidence vs disciplined citation-failure rate")
    a3 = addendum_3(key_df, naive_responses, arm3_citation_failures, arm3_total_lines)
    log(f"  naive {a3['naive_unsupported_rate_pct']}% vs disciplined "
        f"{a3['disciplined_citation_failure_rate_pct']}% -> {verdict_str(a3['met'])}")

    log("addendum A4 -- the hero claim (arm 3 vs arm 1, same method as pre-regs 3/4)")
    gems3 = gems_surfaced(key_df, arm3_dossiers, "arm3_disciplined")
    stuffers3 = stuffers_flagged(key_df, arm3_dossiers, "arm3_disciplined")
    a4 = addendum_4(gems3, a2, stuffers3, a1)
    log(f"  gems beats ATS: {a4['gems']['arm3_beats_ats']}; stuffers beats ATS: "
        f"{a4['stuffers']['arm3_beats_ats']} -> {verdict_str(a4['met'])} "
        f"({'PROVISIONAL' if a4['provisional'] else 'final'})")

    log("item 11 -- cross-arm contradiction table")
    ct = contradiction_table(key_df, arm4_dossiers, arm3_dossiers, naive_responses)

    log("item 12 -- matched pair for the interactive page")
    mp = matched_pair(key_df, candidates_df, ats_df, naive_responses, arm3_dossiers, arm4_dossiers)
    log(f"  missed star: {mp['missed_star']['candidate_id']} (ATS rank {mp['missed_star']['ats_rank']}); "
        f"false positive: {mp['false_positive']['candidate_id']} (ATS rank {mp['false_positive']['ats_rank']})")

    log("item 13 -- adjudication list (arm-4 contradictions not matching a planted E-row)")
    adj = adjudication_list(key_df, arm4_dossiers)
    log(f"  {adj['n_items']} item(s) for human adjudication")

    results = {
        "data_status": data_status,
        "pre_registrations": {
            "1": pr1, "2": pr2, "3": pr3, "4": pr4, "5": pr5, "6": pr6,
        },
        "addenda": {"A1": a1, "A2": a2, "A3": a3, "A4": a4},
        "gems_arm3": gems3, "stuffers_arm3": stuffers3,
        "parity": parity,
        "contradiction_table": ct,
        "matched_pair": mp,
        "adjudication_list": adj,
        "personas": persona_section,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    MARKING_JSON_PATH.write_text(json.dumps(to_jsonable(results), indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"wrote {MARKING_JSON_PATH}")
    write_report(to_jsonable(results), REPORT_MD_PATH)
    log(f"wrote {REPORT_MD_PATH}")

    if not arm3_complete:
        log("=" * 70)
        log(f"PARTIAL RUN COMPLETE: {len(disc_missing)}/{config.N_BATCHES} arm-3 batches "
            "still missing -- re-run once complete for final numbers.")
        log(f"Final-run command: python mark_results.py --require-complete")
        log("=" * 70)
        if args.require_complete:
            sys.exit(1)

    if not personas_complete:
        log("=" * 70)
        log(f"PARTIAL RUN: persona experiment (pre-registration 6) is missing/invalid data -- "
            f"{dc6['n_files_present']}/{dc6['n_files_expected']} files present, "
            f"{len(persona_problems)} problem(s). See marking.json 'personas' section.")
        for problem in persona_problems[:20]:
            log(f"  - {problem}")
        log(f"Final-run command: python mark_results.py --require-complete")
        log("=" * 70)
        if args.require_complete:
            sys.exit("[mark_results] ERROR: --require-complete requires all 24 persona files "
                      "present and valid (48 unique candidate_ids matching the subset, 12 "
                      "requirement_judgments per candidate). See problems logged above.")

    log("done.")


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as exc:
        sys.exit(f"[mark_results] ERROR: missing input file -- {exc}")
