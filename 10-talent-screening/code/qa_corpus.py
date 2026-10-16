"""Phase-2-close corpus QA for case 10 (Talent Screening).

Runs the mechanical QA checklist built up while the corpus was written
(including the degree-ambiguity rules) against the *current* state of `data/applications_raw/`. This script never edits
corpus content -- it only reads `data/briefs/`, `data/applications_raw/`,
`data/answer_key.csv` and `data/answer_key_candidates.csv`, and writes a
report to `data/qa_corpus_report.txt` plus a summary to stdout.

Seven checks, each producing zero or more Finding records (PASS is implicit;
only WARN/FAIL are recorded as findings):

  1. Completeness       -- hard FAIL: missing batch files, missing/duplicate
                            candidate ids, empty document fields, stray
                            *.part files.
  2. No future dates     -- hard FAIL: a real year later than 2026 anywhere
                            in cv_markdown / cover_letter_markdown.
  3. Name integrity      -- hard FAIL: own full name missing from own CV,
                            duplicate full names, another candidate's full
                            name leaking into a candidate's documents.
  4. Displacement (F)    -- hard FAIL: the canonical requirement term is
                            present, or no recognisable stem of the
                            assigned displaced phrase is present.
  5. Degree-field rule   -- hard FAIL on a relevant-field term inside the
                            education section of an R05-absent/not-stated/
                            claimed-only candidate; WARN on an
                            ambiguous-relevance term (per the C148/C198/C218
                            precedent).
  6. Cover-letter-only    -- FAIL if a CV contains a strong/specific keyword
     placement               for a requirement whose key entry is located
                            in the cover letter; WARN on a generic keyword
                            (human review).
  7. Not-to-mention scan -- WARN only: any keyword hit for a requirement the
                            brief marks not_to_mention, anywhere in either
                            document, with context (keyword matches can be
                            innocent -- e.g. an employer name).

Run: `python code/qa_corpus.py` from the project root or from `code/`.
Exit code 1 if any hard FAIL is found anywhere (including an incomplete
corpus); 0 otherwise. A dataset failing this script is a bug in the
generator/writer flow to fix upstream -- this script never patches corpus
content itself.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

# Make `code/config.py` importable regardless of the current working
# directory the script is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402  (must follow the sys.path fix-up)

# ---------------------------------------------------------------------------
# Config block -- every QA-specific tunable lives here, not buried in logic.
# Structural facts (paths, requirement ids, N_CANDIDATES, N_BATCHES, the
# displacement table) come from code/config.py; the keyword lists below are
# QA-script-specific heuristics for scanning already-written prose and are
# NOT part of the corpus generation config.
# ---------------------------------------------------------------------------

PROJECT_ROOT = config.PROJECT_ROOT
DATA_DIR = config.DATA_DIR
BRIEFS_DIR = config.BRIEFS_DIR
APPLICATIONS_RAW_DIR = DATA_DIR / "applications_raw"
ANSWER_KEY_PATH = config.ANSWER_KEY_PATH
ANSWER_KEY_CANDIDATES_PATH = config.ANSWER_KEY_CANDIDATES_PATH
REPORT_PATH = DATA_DIR / "qa_corpus_report.txt"

N_CANDIDATES = config.N_CANDIDATES
N_BATCHES = config.N_BATCHES
BATCH_SIZE = config.BRIEF_BATCH_SIZE
CORPUS_NOW_YEAR = config.CORPUS_NOW_YEAR  # 2026

# --- Check 5: degree-field rule ---------------------------------------------
# Word-tuples: ALL words in a tuple must appear (as whole words, order-
# independent) on the SAME line of the education section for a hit. Matching
# whole words on one line (rather than a raw substring) is what lets
# "electronic engineering" catch "Electronic and Information Engineering"
# (C218's case) without also matching unrelated text elsewhere in the CV.
HARD_RELEVANT_DEGREE_TERMS = [
    ("electrical", "engineering"),
    ("physics",),
    ("applied", "mathematics"),
    ("electronics", "engineering"),
]
# The three known ambiguity cases (C148 Software
# Engineering, C198 Information Processing Science, C218 Electronic and
# Information Engineering) -- flagged WARN, never FAIL, by design.
AMBIGUOUS_RELEVANCE_DEGREE_TERMS = [
    ("software", "engineering"),
    ("information", "processing"),
    ("electronic", "engineering"),
    ("computer", "engineering"),
    ("telecommunications",),
]

# --- Check 4: displacement integrity (F archetype) --------------------------
# Canonical terms that must NEVER appear anywhere in an F candidate's
# documents for the requirement that candidate has displaced (contiguous
# phrases; hyphen/space variants are handled by normalize() at match time).
CANONICAL_EXCLUSIVE_TERMS = {
    "R01": ["phased array"],
    "R02": ["embedded dsp"],
    "R03": ["production python"],
}
# Per displaced phrase (matched positionally against config.DISPLACEMENT_TABLE
# for the same requirement id), a short list of "stem" keywords likely to
# survive paraphrase by the prose-writing agent. ANY one match counts as
# the displaced phrase being present ("a recognisable stem of it").
DISPLACEMENT_STEM_KEYWORDS = {
    "R01": [
        ["automotive", "fmcw"],
        ["5g", "massive mimo", "base station"],
        ["sonar", "towed"],
        ["hearing aid", "acoustic", "microphone array"],
    ],
    "R02": [
        ["sensor fusion", "drone", "flight controller"],
        ["audio dsp", "hearing aid"],
        ["engine control", "ecu"],
        ["ecg", "eeg", "medical"],
    ],
    "R03": [
        ["physics phd", "side project"],
        ["research institute", "data pipeline"],
        ["open source", "numpy", "scipy"],
        ["particle physics", "detector collaboration"],
    ],
}
for _rid in config.DISPLACEMENT_REQUIREMENT_IDS:
    assert len(DISPLACEMENT_STEM_KEYWORDS[_rid]) == len(config.DISPLACEMENT_TABLE[_rid])

# --- Checks 6/7: per-requirement canonical keyword lists ---------------------
# "strong" keywords are specific enough that a hit is a real signal (FAIL if
# found where it shouldn't be); "generic" keywords are common enough that a
# hit alone is not conclusive (WARN / human review only). This is a QA-script
# heuristic, not part of the corpus generation config -- it is deliberately
# conservative (favours WARN over FAIL) because these lists cannot capture
# every paraphrase the writer used.
REQUIREMENT_KEYWORDS = {
    "R01": {"strong": ["phased array", "phased-array", "beamforming"],
            "generic": ["array processing", "radar"]},
    "R02": {"strong": ["embedded dsp", "embedded c", "embedded c++", "embedded software"],
            "generic": ["dsp", "c/c++", "firmware"]},
    "R03": {"strong": ["production python"],
            "generic": ["python"]},
    "R04": {"strong": ["rf measurement", "network analyser", "network analyzer",
                        "anechoic chamber", "spectrum analyser", "spectrum analyzer",
                        "vector network analyser", "vna"],
            "generic": ["rf test", "calibration", "test bench"]},
    "R05": {"strong": ["electrical engineering", "applied mathematics", "demonstrated equivalent"],
            "generic": ["physics", "degree", "engineering degree"]},
    "R06": {"strong": ["kalman filter", "kalman filtering", "state estimation", "extended kalman"],
            "generic": ["estimation theory", "filtering"]},
    "R07": {"strong": ["satellite platform", "airborne platform", "spaceborne",
                        "cubesat", "satellite instrument", "satellite payload"],
            "generic": ["satellite", "airborne", "aircraft"]},
    "R08": {"strong": ["team lead", "technical lead", "led a team", "head of"],
            "generic": ["leadership", "managed a team", "supervised"]},
    "R09": {"strong": ["peer-reviewed", "peer reviewed", "open-source contribution",
                        "open source contribution", "published a paper", "github.example"],
            "generic": ["publication", "open source", "open-source"]},
    "R10": {"strong": ["eu work authorisation", "eu work authorization",
                        "right to work in the eu", "eu citizen"],
            "generic": ["work authorisation", "work authorization", "work permit"]},
    "R11": {"strong": ["professional working fluency", "professional working proficiency",
                        "native english", "fluent in english"],
            "generic": ["english"]},
    "R12": {"strong": ["willing to relocate", "relocate to oulu", "based in oulu",
                        "relocated to oulu"],
            "generic": ["relocation", "onsite", "relocate"]},
}
assert set(REQUIREMENT_KEYWORDS) == set(config.REQUIREMENT_BY_ID)

# Future-date scan: real years shaped like \b20[2-9][0-9]\b, filtered to those
# strictly after CORPUS_NOW_YEAR.
FUTURE_YEAR_PATTERN = re.compile(r"\b20[2-9][0-9]\b")

# --- Check 2 refinement (triage, "Corpus QA triage", 18 Sep 2026) ----------
# The corpus is written as applications submitted in September 2026: a future
# year is only a real defect when it is attached to a PAST/COMPLETED event
# (a career-history date range, "since"/"joined"/"graduated"/"completed" --
# something that already happened). A future year in a PROSPECTIVE statement
# (planned relocation, permit validity, availability date) is legitimate and
# expected. Phone numbers matching the year-shaped regex are a known false
# positive of the literal \b20[2-9][0-9]\b approach. Classification order:
# phone-number artifact -> forward-looking/prospective -> past/completed
# (FAIL) -> unclear (WARN, conservative default now that FAIL is the narrow
# case).
PHONE_NUMBER_CONTEXT_PATTERN = re.compile(r"\+\d[\d\s]{3,20}$")
FORWARD_LOOKING_KEYWORDS = [
    "plan", "relocat", "start", "available", "avail", "valid through",
    "valid until", "notice period", "intend", "expect to", "target start",
    "can join", "able to join", "can start",
    "from january", "from february", "from march", "from april",
    "from may", "from june", "from july", "from august", "from september",
    "from october", "from november", "from december",
]
PAST_COMPLETED_KEYWORDS = [
    "since", "joined", "graduated", "completed", "finished", "delivered",
    "shipped", "obtained", "conferred", "employed",
]
YEAR_RANGE_PATTERN = re.compile(r"\b((?:19|20)\d{2})\s*[-–—]\s*((?:19|20)\d{2})\b")

CONTEXT_CHARS = 20  # characters of context either side of a hit


def classify_future_year(text: str, match: re.Match) -> tuple[str, str]:
    """Classify a FUTURE_YEAR_PATTERN hit as ("FAIL", reason) or ("WARN",
    reason), per the check-2 triage refinement above."""
    start, end = match.start(), match.end()
    pre = text[max(0, start - 60):start]
    post = text[end:end + 30]
    window = (pre + " " + post).lower()

    if PHONE_NUMBER_CONTEXT_PATTERN.search(pre):
        return "WARN", "phone-number digits, not a date"

    if any(kw in window for kw in FORWARD_LOOKING_KEYWORDS):
        return "WARN", "forward-looking / prospective statement (legitimate in a September-2026 application)"

    for rm in YEAR_RANGE_PATTERN.finditer(text):
        if rm.start() <= start < rm.end() or rm.start() < end <= rm.end():
            return "FAIL", f"future year is part of a date range {rm.group(0)!r} (career-history span)"

    if any(kw in window for kw in PAST_COMPLETED_KEYWORDS):
        return "FAIL", "past/completed-event context nearby (since/joined/graduated/completed)"

    return "WARN", "no clear past/completed or forward-looking cue nearby -- review context"

# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    check: str          # e.g. "1. Completeness"
    severity: str        # "FAIL", "WARN", or "INFO"
    candidate_id: str
    message: str
    context: str = ""


@dataclass
class CheckResult:
    name: str
    findings: list = field(default_factory=list)
    n_evaluated: int = 0  # denominator for the summary table (candidates/items checked)

    def fail(self, candidate_id, message, context=""):
        self.findings.append(Finding(self.name, "FAIL", candidate_id, message, context))

    def warn(self, candidate_id, message, context=""):
        self.findings.append(Finding(self.name, "WARN", candidate_id, message, context))

    def info(self, candidate_id, message, context=""):
        # Informational only: a pattern that looked worth flagging but was
        # triaged as a frozen design interpretation, not a defect. Never affects the exit
        # code and is reported separately from WARN.
        self.findings.append(Finding(self.name, "INFO", candidate_id, message, context))

    @property
    def n_fail(self):
        return sum(1 for f in self.findings if f.severity == "FAIL")

    @property
    def n_warn(self):
        return sum(1 for f in self.findings if f.severity == "WARN")

    @property
    def n_info(self):
        return sum(1 for f in self.findings if f.severity == "INFO")

    @property
    def n_pass(self):
        return max(self.n_evaluated - len({f.candidate_id for f in self.findings}), 0)


# ---------------------------------------------------------------------------
# Small text helpers
# ---------------------------------------------------------------------------


def normalize(text: str) -> str:
    """Lowercase, fold hyphens/slashes/underscores to spaces, strip stray
    punctuation, collapse whitespace. Applied to both corpus text and
    keyword/term lists before every substring match in this script, so
    "phased-array" and "phased array" are the same match target."""
    text = text.lower()
    text = re.sub(r"[-_/]", " ", text)
    text = re.sub(r"[^a-z0-9%.\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def context_snippet(text: str, start: int, end: int, pad: int = CONTEXT_CHARS) -> str:
    """A single-line context window around a match span, for report readability."""
    lo = max(0, start - pad)
    hi = min(len(text), end + pad)
    snippet = text[lo:hi].replace("\n", " ").replace("\r", " ")
    snippet = re.sub(r"\s+", " ", snippet).strip()
    prefix = "..." if lo > 0 else ""
    suffix = "..." if hi < len(text) else ""
    return f"{prefix}{snippet}{suffix}"


def find_full_name(full_name: str, text: str):
    """Return the match object for `full_name` inside `text`, case-insensitive,
    with flexible whitespace between name parts and word boundaries at each
    end -- or None. Used for both the own-name check and the cross-candidate
    leakage check (full-name matches only; shared surnames are allowed)."""
    parts = [re.escape(p) for p in full_name.split()]
    if not parts:
        return None
    pattern = re.compile(r"\b" + r"\s+".join(parts) + r"\b", re.IGNORECASE)
    return pattern.search(text)


def extract_section(text: str, heading_name: str) -> tuple[str | None, bool]:
    """Extract the block of `text` under a heading matching `heading_name`
    (e.g. "education"), tolerant of markdown (#/##/###), plain, or all-caps
    heading styles observed across the corpus's writer-generated CVs. Returns
    (section_text_or_None, used_fallback). used_fallback is True when the
    heading could not be located and the caller should scan the whole
    document instead (reported transparently in the QA output)."""
    lines = text.split("\n")
    heading_re = re.compile(rf"^(#{{1,6}}\s*)?{re.escape(heading_name)}\s*:?\s*$", re.IGNORECASE)
    generic_heading_re = re.compile(r"^#{1,6}\s+\S|^[A-Z][A-Z0-9 /&\-]{2,50}$")

    start = None
    for i, line in enumerate(lines):
        if heading_re.match(line.strip()):
            start = i + 1
            break
    if start is None:
        return None, True

    end = len(lines)
    for j in range(start, len(lines)):
        stripped = lines[j].strip()
        if stripped and generic_heading_re.match(stripped) and stripped.lower() != heading_name.lower():
            end = j
            break
    return "\n".join(lines[start:end]), False


def line_word_hits(section_text: str, term_tuples: list[tuple]) -> list[tuple]:
    """For each line of `section_text`, tokenise to whole words and report any
    term-tuple whose words are ALL present (order-independent) on that line.
    Returns a list of (" ".join(term_tuple), line_text) hits."""
    hits = []
    for raw_line in section_text.split("\n"):
        if not raw_line.strip():
            continue
        tokens = set(re.findall(r"[a-z0-9]+", raw_line.lower()))
        for term_tuple in term_tuples:
            if all(word in tokens for word in term_tuple):
                hits.append((" ".join(term_tuple), raw_line.strip()))
    return hits


def keyword_hits(text: str, keywords: list[str]) -> list[tuple]:
    """Substring-search `keywords` (already meant to be normalized phrases)
    against normalize(text). Returns (keyword, context_snippet) pairs. Because
    normalize() collapses whitespace, spans are computed on the normalized
    string; context is taken from the normalized string too (readable, if not
    byte-identical to the source formatting)."""
    norm = normalize(text)
    hits = []
    for kw in keywords:
        kw_norm = normalize(kw)
        idx = norm.find(kw_norm)
        while idx != -1:
            hits.append((kw, context_snippet(norm, idx, idx + len(kw_norm))))
            idx = norm.find(kw_norm, idx + 1)
    return hits


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_applications() -> tuple[dict, list, list]:
    """Load every existing data/applications_raw/batch_NN.json. Returns
    (applications_by_candidate_id, missing_batch_numbers, stray_part_files).
    Never raises on a missing batch file -- that is check 1's job to report."""
    applications = {}
    missing_batches = []
    for batch_num in range(1, N_BATCHES + 1):
        batch_path = APPLICATIONS_RAW_DIR / f"batch_{batch_num:02d}.json"
        if not batch_path.exists():
            missing_batches.append(batch_num)
            continue
        try:
            with open(batch_path, encoding="utf-8") as fh:
                entries = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  [ERROR] could not read {batch_path.name}: {exc}")
            missing_batches.append(batch_num)
            continue
        for entry in entries:
            cid = entry.get("candidate_id")
            if cid in applications:
                print(f"  [ERROR] duplicate candidate_id {cid} "
                      f"(already loaded, also present in {batch_path.name})")
            applications[cid] = {**entry, "_source_batch": batch_path.name}

    stray_part_files = sorted(str(p.relative_to(DATA_DIR))
                               for p in APPLICATIONS_RAW_DIR.glob("*.part"))
    return applications, missing_batches, stray_part_files


def load_briefs() -> dict:
    """Load every data/briefs/brief_NNN.json into a dict keyed by candidate_id.
    Briefs are Phase-1 artefacts and are expected to all exist regardless of
    how many prose batches have landed."""
    briefs = {}
    for path in sorted(BRIEFS_DIR.glob("brief_*.json")):
        try:
            with open(path, encoding="utf-8") as fh:
                brief = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  [ERROR] could not read {path.name}: {exc}")
            continue
        briefs[brief.get("candidate_id", path.stem)] = brief
    return briefs


# ---------------------------------------------------------------------------
# Check 1: completeness
# ---------------------------------------------------------------------------


def check_completeness(applications, missing_batches, stray_part_files,
                        expected_ids: set) -> CheckResult:
    result = CheckResult("1. Completeness")
    result.n_evaluated = N_BATCHES

    for batch_num in missing_batches:
        result.fail("(corpus)", f"batch_{batch_num:02d}.json is missing from "
                    f"{APPLICATIONS_RAW_DIR.name}/")

    found_ids = set(applications.keys())
    missing_ids = expected_ids - found_ids
    extra_ids = found_ids - expected_ids
    if missing_ids:
        result.fail("(corpus)", f"{len(missing_ids)} candidate id(s) present in "
                    f"the key but absent from applications_raw: "
                    f"{', '.join(sorted(missing_ids)[:10])}"
                    + (" ..." if len(missing_ids) > 10 else ""))
    if extra_ids:
        result.fail("(corpus)", f"{len(extra_ids)} candidate id(s) present in "
                    f"applications_raw but absent from the key: "
                    f"{', '.join(sorted(extra_ids))}")

    for cid, app in applications.items():
        cv = app.get("cv_markdown", "")
        letter = app.get("cover_letter_markdown", "")
        if not cv or not cv.strip():
            result.fail(cid, f"cv_markdown is empty (batch {app.get('_source_batch')})")
        if not letter or not letter.strip():
            result.fail(cid, f"cover_letter_markdown is empty (batch {app.get('_source_batch')})")

    for stray in stray_part_files:
        result.fail("(corpus)", f"stray .part file left behind: {stray}")

    if not missing_batches and not missing_ids and not extra_ids and not stray_part_files:
        print(f"  [ok] all {N_BATCHES} batch files present, "
              f"{len(found_ids)} candidate ids match the key exactly, "
              f"every cv_markdown/cover_letter_markdown non-empty, "
              f"no stray .part files")
    else:
        print(f"  found {len(found_ids)}/{len(expected_ids)} candidates across "
              f"{N_BATCHES - len(missing_batches)}/{N_BATCHES} batch files")
    return result


# ---------------------------------------------------------------------------
# Check 2: no future dates
# ---------------------------------------------------------------------------


def check_future_dates(applications) -> CheckResult:
    result = CheckResult("2. No future dates")
    result.n_evaluated = len(applications)
    for cid, app in sorted(applications.items()):
        for field_name in ("cv_markdown", "cover_letter_markdown"):
            text = app.get(field_name, "") or ""
            for match in FUTURE_YEAR_PATTERN.finditer(text):
                year = int(match.group(0))
                if year > CORPUS_NOW_YEAR:
                    snippet = context_snippet(text, match.start(), match.end())
                    severity, reason = classify_future_year(text, match)
                    message = f"year {year} (> {CORPUS_NOW_YEAR}) found in {field_name} -- {reason}"
                    if severity == "FAIL":
                        result.fail(cid, message, snippet)
                    else:
                        result.warn(cid, message, snippet)
    if result.n_fail == 0:
        print(f"  [ok] no year later than {CORPUS_NOW_YEAR} attached to a "
              f"past/completed event across {len(applications)} candidates' "
              f"documents (forward-looking mentions and phone-number "
              f"false positives reported as WARN)")
    return result


# ---------------------------------------------------------------------------
# Check 3: name integrity
# ---------------------------------------------------------------------------


def check_name_integrity(applications, candidates_df: pd.DataFrame) -> CheckResult:
    result = CheckResult("3. Name integrity")
    result.n_evaluated = len(applications)

    full_name_by_id = dict(zip(candidates_df["candidate_id"], candidates_df["full_name"]))

    # (b) global uniqueness, from the answer key (the authoritative source).
    name_counts = candidates_df["full_name"].value_counts()
    duplicated = name_counts[name_counts > 1]
    if len(duplicated) > 0:
        for name, count in duplicated.items():
            holders = candidates_df.loc[candidates_df["full_name"] == name, "candidate_id"].tolist()
            result.fail("(corpus)", f"full name {name!r} is used by {count} "
                        f"candidates: {', '.join(holders)}")
    else:
        print(f"  [ok] all {len(candidates_df)} candidate full names in the key are unique")

    # (a) own name appears in own cv_markdown.
    own_name_ok = 0
    for cid, app in applications.items():
        full_name = full_name_by_id.get(cid)
        if full_name is None:
            result.fail(cid, "candidate_id not found in answer_key_candidates.csv "
                        "-- cannot check name integrity")
            continue
        cv = app.get("cv_markdown", "") or ""
        if find_full_name(full_name, cv) is None:
            result.fail(cid, f"own full name {full_name!r} not found in cv_markdown")
        else:
            own_name_ok += 1
    print(f"  [ok] own full name found in cv_markdown for {own_name_ok}/{len(applications)} candidates")

    # (c) no other candidate's full name leaks into this candidate's documents.
    combined_text = {
        cid: (app.get("cv_markdown", "") or "") + "\n" + (app.get("cover_letter_markdown", "") or "")
        for cid, app in applications.items()
    }
    name_patterns = {}
    for cid, full_name in full_name_by_id.items():
        if cid in applications:
            parts = [re.escape(p) for p in full_name.split()]
            name_patterns[cid] = re.compile(r"\b" + r"\s+".join(parts) + r"\b", re.IGNORECASE)

    leakage_hits = 0
    for cid, text in combined_text.items():
        own_name = full_name_by_id.get(cid)
        for other_cid, pattern in name_patterns.items():
            if other_cid == cid:
                continue
            match = pattern.search(text)
            if match:
                leakage_hits += 1
                result.fail(cid, f"contains {full_name_by_id[other_cid]!r} "
                            f"(candidate {other_cid})'s full name",
                            context_snippet(text, match.start(), match.end()))
    if leakage_hits == 0:
        print(f"  [ok] no candidate's documents contain another candidate's full name")
    return result


# ---------------------------------------------------------------------------
# Check 4: displacement integrity (F archetype)
# ---------------------------------------------------------------------------


def check_displacement(applications, key_df: pd.DataFrame) -> CheckResult:
    result = CheckResult("4. Displacement integrity (F)")
    displaced_rows = key_df[key_df["displaced"] == True]  # noqa: E712
    result.n_evaluated = displaced_rows["candidate_id"].nunique()

    for _, row in displaced_rows.iterrows():
        cid = row["candidate_id"]
        rid = row["requirement_id"]
        phrase = row["displaced_phrase"]
        app = applications.get(cid)
        if app is None:
            continue  # already reported as missing by check 1
        text = (app.get("cv_markdown", "") or "") + "\n" + (app.get("cover_letter_markdown", "") or "")

        # (i) the canonical term must appear nowhere.
        canonical_terms = CANONICAL_EXCLUSIVE_TERMS.get(rid, [])
        hits = keyword_hits(text, canonical_terms)
        for term, snippet in hits:
            result.fail(cid, f"canonical term {term!r} for displaced requirement "
                        f"{rid} found in documents", snippet)

        # (ii) a recognisable stem of the assigned displaced phrase must appear.
        table_phrases = config.DISPLACEMENT_TABLE.get(rid, [])
        stem_lists = DISPLACEMENT_STEM_KEYWORDS.get(rid, [])
        try:
            phrase_index = table_phrases.index(phrase)
            stems = stem_lists[phrase_index]
        except ValueError:
            result.fail(cid, f"displaced_phrase {phrase!r} for {rid} does not "
                        f"exactly match any entry in config.DISPLACEMENT_TABLE "
                        f"-- QA script cannot verify the stem (fix the table or "
                        f"the mismatch)")
            continue
        norm_text = normalize(text)
        if not any(normalize(stem) in norm_text for stem in stems):
            result.fail(cid, f"no recognisable stem of the displaced phrase "
                        f"{phrase!r} (requirement {rid}) found anywhere in "
                        f"documents -- looked for: {stems}")

    if result.n_fail == 0:
        print(f"  [ok] all {result.n_evaluated} F candidates: canonical term absent, "
              f"displaced-phrase stem present")
    return result


# ---------------------------------------------------------------------------
# Check 5: degree-field rule
# ---------------------------------------------------------------------------


def check_degree_field(applications, key_df: pd.DataFrame) -> CheckResult:
    result = CheckResult("5. Degree-field rule")
    r05 = key_df[key_df["requirement_id"] == "R05"]
    not_evidenced = r05[r05["status"].isin(["absent", "not_stated", "claimed_only"])]
    result.n_evaluated = len(not_evidenced)

    fallback_count = 0
    for _, row in not_evidenced.iterrows():
        cid = row["candidate_id"]
        app = applications.get(cid)
        if app is None:
            continue  # already reported by check 1
        cv = app.get("cv_markdown", "") or ""
        section, used_fallback = extract_section(cv, "education")
        if used_fallback:
            fallback_count += 1
            section = cv  # scan the whole CV rather than skip the candidate

        hard_hits = line_word_hits(section, HARD_RELEVANT_DEGREE_TERMS)
        if hard_hits:
            for term, line in hard_hits:
                note = " (education heading not found; scanned whole CV)" if used_fallback else ""
                result.fail(cid, f"relevant-field term {term!r} found in "
                            f"education section for R05-{row['status']} "
                            f"candidate{note}", line)
            continue  # a FAIL takes priority; don't also WARN the same candidate

        ambiguous_hits = line_word_hits(section, AMBIGUOUS_RELEVANCE_DEGREE_TERMS)
        for term, line in ambiguous_hits:
            note = " (education heading not found; scanned whole CV)" if used_fallback else ""
            result.warn(cid, f"ambiguous-relevance term {term!r} found in "
                        f"education section for R05-{row['status']} "
                        f"candidate -- human review{note}", line)

    if fallback_count:
        print(f"  [note] education heading not found for {fallback_count} candidate(s); "
              f"scanned whole CV as fallback")
    if result.n_fail == 0 and result.n_warn == 0:
        print(f"  [ok] no relevant or ambiguous degree-field terms found for "
              f"{result.n_evaluated} R05-absent/not-stated/claimed-only candidates")
    return result


# ---------------------------------------------------------------------------
# Check 6: cover-letter-only placement
# ---------------------------------------------------------------------------


def check_letter_only_placement(applications, key_df: pd.DataFrame) -> CheckResult:
    result = CheckResult("6. Cover-letter-only placement")
    # Use the corpus's own `letter_only` flag, not just evidence_location ==
    # "cover_letter": the credential-inflation (E) contradiction templates
    # also place a claim in the cover letter with evidence_location ==
    # "cover_letter", but BY DESIGN also require a plain, contradicting
    # mention in the CV work-history entry (config.CONTRADICTION_TEMPLATES) --
    # that is the whole mechanism, not a leak. `letter_only` (True only for
    # status == "evidenced") is the corpus's actual "present nowhere else"
    # commitment (config.py's LETTER_ONLY_* discussion), so it is the correct
    # filter for this check.
    letter_rows = key_df[key_df["letter_only"] == True]  # noqa: E712
    result.n_evaluated = len(letter_rows)

    for _, row in letter_rows.iterrows():
        cid = row["candidate_id"]
        rid = row["requirement_id"]
        app = applications.get(cid)
        if app is None:
            continue
        cv = app.get("cv_markdown", "") or ""
        kws = REQUIREMENT_KEYWORDS.get(rid, {"strong": [], "generic": []})

        # R05 design clarification (triage, "Corpus QA triage", 18 Sep 2026):
        # a genuinely qualified candidate's CV shows a bare degree line in
        # the education section regardless of where the brief placed the
        # SUBSTANTIVE R05 write-up -- the key's letter_only location refers
        # to that write-up, not to the baseline biographical fact of what
        # degree the candidate holds. Frozen as a design interpretation, not
        # a corpus defect. Detected as: the strong-term hit falls inside the
        # CV's education section. Applies to R05 only -- every other
        # requirement's letter-only check is unchanged.
        education_section = None
        if rid == "R05":
            education_section, _ = extract_section(cv, "education")

        strong_hits = keyword_hits(cv, kws["strong"])
        leaked_strong_hits = []
        for term, snippet in strong_hits:
            if rid == "R05" and education_section is not None \
                    and normalize(term) in normalize(education_section):
                result.info(cid, f"requirement R05 (letter_only): bare degree "
                            f"line naming {term!r} in the CV education "
                            f"section is baseline biography, not a "
                            f"letter-only-placement violation -- the key's "
                            f"location refers to the substantive R05 "
                            f"write-up, which remains letter-only", snippet)
            else:
                leaked_strong_hits.append((term, snippet))

        for term, snippet in leaked_strong_hits:
            result.fail(cid, f"requirement {rid} ({row['status']}, cover-letter-"
                        f"located) leaks into CV via strong term {term!r}", snippet)
        if leaked_strong_hits:
            continue

        generic_hits = keyword_hits(cv, kws["generic"])
        for term, snippet in generic_hits:
            result.warn(cid, f"requirement {rid} ({row['status']}, cover-letter-"
                        f"located): generic term {term!r} found in CV -- human "
                        f"review", snippet)

    if result.n_fail == 0 and result.n_warn == 0:
        print(f"  [ok] no cover-letter-only requirement leaked into a CV, "
              f"across {result.n_evaluated} cover-letter-located key rows")
    return result


# ---------------------------------------------------------------------------
# Check 7: not-to-mention scan
# ---------------------------------------------------------------------------


def check_not_to_mention(applications, briefs) -> CheckResult:
    result = CheckResult("7. Not-to-mention scan")
    n_items = 0
    for cid, app in applications.items():
        brief = briefs.get(cid)
        if brief is None:
            result.fail(cid, "no matching brief found in data/briefs/ -- cannot "
                        "run the not-to-mention scan")
            continue
        text = (app.get("cv_markdown", "") or "") + "\n" + (app.get("cover_letter_markdown", "") or "")
        for item in brief.get("not_to_mention", []):
            n_items += 1
            rid = item["requirement_id"]
            kws = REQUIREMENT_KEYWORDS.get(rid, {"strong": [], "generic": []})
            all_kws = kws["strong"] + kws["generic"]
            for term, snippet in keyword_hits(text, all_kws):
                result.warn(cid, f"not_to_mention requirement {rid} "
                            f"({item['canonical_name']}): keyword {term!r} found "
                            f"-- review for innocent mention", snippet)
    result.n_evaluated = n_items
    if result.n_warn == 0 and result.n_fail == 0:
        print(f"  [ok] no keyword hits across {n_items} not_to_mention items "
              f"({len(applications)} candidates)")
    return result


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def render_summary_table(results: list) -> str:
    header = f"{'Check':<38}{'PASS':>8}{'WARN':>8}{'FAIL':>8}{'INFO':>8}{'N':>8}"
    lines = [header, "-" * len(header)]
    for r in results:
        lines.append(f"{r.name:<38}{r.n_pass:>8}{r.n_warn:>8}{r.n_fail:>8}{r.n_info:>8}{r.n_evaluated:>8}")
    return "\n".join(lines)


def render_details(results: list) -> str:
    lines = []
    for r in results:
        if not r.findings:
            continue
        lines.append(f"\n=== {r.name} ===")
        # FAIL and WARN first (actionable), INFO last (frozen design
        # interpretation, never affects the exit code).
        severity_order = {"FAIL": 0, "WARN": 1, "INFO": 2}
        for f in sorted(r.findings, key=lambda f: severity_order.get(f.severity, 3)):
            ctx = f"  | {f.context}" if f.context else ""
            lines.append(f"  [{f.severity}] {f.candidate_id}: {f.message}{ctx}")
    return "\n".join(lines) if lines else "\n(no WARN/FAIL/INFO findings in any check)"


def main() -> int:
    print("=== Case 10 Talent Screening: Phase-2-close corpus QA ===")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Applications: {APPLICATIONS_RAW_DIR}")
    print()

    if not ANSWER_KEY_PATH.exists() or not ANSWER_KEY_CANDIDATES_PATH.exists():
        print(f"[FATAL] answer key files not found under {DATA_DIR} -- cannot run QA.")
        return 1

    key_df = pd.read_csv(ANSWER_KEY_PATH)
    candidates_df = pd.read_csv(ANSWER_KEY_CANDIDATES_PATH)
    expected_ids = set(candidates_df["candidate_id"])
    if len(expected_ids) != N_CANDIDATES:
        print(f"[WARNING] answer_key_candidates.csv has {len(expected_ids)} "
              f"candidates, expected {N_CANDIDATES} (config.N_CANDIDATES)")

    print("Loading applications_raw batches...")
    applications, missing_batches, stray_part_files = load_applications()
    print(f"  loaded {len(applications)} candidates from "
          f"{N_BATCHES - len(missing_batches)}/{N_BATCHES} batch files")
    if missing_batches:
        print(f"  missing batch numbers: {missing_batches}")

    print("Loading briefs...")
    briefs = load_briefs()
    print(f"  loaded {len(briefs)} brief files")
    print()

    results = []

    print("--- Check 1: Completeness ---")
    results.append(check_completeness(applications, missing_batches, stray_part_files, expected_ids))
    print()

    print("--- Check 2: No future dates ---")
    results.append(check_future_dates(applications))
    print()

    print("--- Check 3: Name integrity ---")
    results.append(check_name_integrity(applications, candidates_df))
    print()

    print("--- Check 4: Displacement integrity (F archetype) ---")
    results.append(check_displacement(applications, key_df))
    print()

    print("--- Check 5: Degree-field rule ---")
    results.append(check_degree_field(applications, key_df))
    print()

    print("--- Check 6: Cover-letter-only placement ---")
    results.append(check_letter_only_placement(applications, key_df))
    print()

    print("--- Check 7: Not-to-mention scan ---")
    results.append(check_not_to_mention(applications, briefs))
    print()

    summary = render_summary_table(results)
    details = render_details(results)

    total_fail = sum(r.n_fail for r in results)
    total_warn = sum(r.n_warn for r in results)
    total_info = sum(r.n_info for r in results)
    info_suffix = f" ({total_info} INFO finding(s), frozen design interpretations, no action needed)" if total_info else ""
    if total_fail == 0 and total_warn == 0:
        verdict = f"PASS -- no FAIL or WARN findings in any check.{info_suffix}"
    elif total_fail == 0:
        verdict = f"PASS WITH WARNINGS -- 0 FAIL, {total_warn} WARN finding(s) for human review.{info_suffix}"
    else:
        verdict = f"FAIL -- {total_fail} FAIL finding(s), {total_warn} WARN finding(s). See details above.{info_suffix}"

    print("=== Summary ===")
    print(summary)
    print()
    print("=== Verdict ===")
    print(verdict)

    report_text = (
        "Case 10 Talent Screening -- Phase-2-close corpus QA report\n"
        f"Run against: {APPLICATIONS_RAW_DIR}\n"
        f"Batches loaded: {N_BATCHES - len(missing_batches)}/{N_BATCHES} "
        f"(missing: {missing_batches if missing_batches else 'none'})\n"
        f"Candidates loaded: {len(applications)}/{N_CANDIDATES}\n\n"
        "=== Summary ===\n" + summary + "\n\n"
        "=== Details ===" + details + "\n\n"
        "=== Verdict ===\n" + verdict + "\n"
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write(report_text)
    print(f"\nFull report written to {REPORT_PATH}")

    return 1 if total_fail > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
