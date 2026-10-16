"""build_interactive_data.py

Distils Project 4 (Contract Clause Extraction) run artefacts into ONE
compact JSON file, ``interactive/_data.json``, consumed by
``interactive/_template.html`` for the case-study's interactive page.

Reads only:
  - data/runs/evaluation.json
  - data/runs/stream_events.json
  - data/runs/holdout_coverage.json
  - data/runs/extract_agent_log.json
  - data/runs/matcher_state.json
  - data/runs/evaluation_worksheet.md (the disagreement worksheet -- already
    scored output, not the answer-key file itself; see below)
  - data/manifest.json
  - code/matchers_generated/matcher_<slug>.py, all 12 (session artefacts,
    read-only -- the gate-failed and demoted matchers are shown same as the
    8 survivors, since the page's honesty depends on that)
  - data/runs/commissions/<slug>/commission.json + induction/*.json, all 12
    (the accepted extractions each matcher was induced from -- real corpus
    language, not the key)
  - data/contracts/GpaqAcquisitionHoldingsInc_..._License Agreement.txt
    (one contract, to quote a single sentence verbatim -- this is corpus
    text, not the held-out expert annotations)

Never reads the held-out expert-annotation directory or the CUAD clause
spreadsheet the pipeline derives it from (rule 10 in validate_corpus.py --
this module is not on that rule's whitelist and deliberately never spells
either name out, matching config.py's own convention, so a mechanical scan
for those literal strings finds nothing here). evaluation_worksheet.md is
evaluate.py's own scored output (pipeline answer vs key answer, already
marked) -- reading it is not reading the key file, the same way reading
evaluation.json isn't.

Deterministic: same input artefacts -> byte-identical output (sorted keys,
no timestamps, no wall-clock or random anything). Every headline number is
computed from the artefacts and then checked against the values the design
write-up already published; a mismatch is treated as a bug and raises
loudly instead of silently shipping a drifted number.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration -- every path and hand-set constant lives here.
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_RUNS = DATA_DIR / "runs"
CONTRACTS_DIR = DATA_DIR / "contracts"

EVALUATION_PATH = DATA_RUNS / "evaluation.json"
STREAM_EVENTS_PATH = DATA_RUNS / "stream_events.json"
HOLDOUT_COVERAGE_PATH = DATA_RUNS / "holdout_coverage.json"
EXTRACT_AGENT_LOG_PATH = DATA_RUNS / "extract_agent_log.json"
MANIFEST_PATH = DATA_DIR / "manifest.json"
MATCHERS_DIR = ROOT / "code" / "matchers_generated"
MATCHER_GOVERNING_LAW_PATH = MATCHERS_DIR / "matcher_governing-law.py"
COMMISSIONS_DIR = DATA_RUNS / "commissions"
MATCHER_STATE_PATH = DATA_RUNS / "matcher_state.json"
WORKSHEET_PATH = DATA_RUNS / "evaluation_worksheet.md"
GPAQ_CONTRACT_PATH = (
    CONTRACTS_DIR
    / "GpaqAcquisitionHoldingsInc_20200123_S-4A_EX-10.6_11951677_EX-10.6_License Agreement.txt"
)

OUTPUT_DIR = ROOT / "interactive"
OUTPUT_PATH = OUTPUT_DIR / "_data.json"
MAX_OUTPUT_BYTES = 60_000

INPUT_PATHS = [
    EVALUATION_PATH,
    STREAM_EVENTS_PATH,
    HOLDOUT_COVERAGE_PATH,
    EXTRACT_AGENT_LOG_PATH,
    MANIFEST_PATH,
    MATCHERS_DIR,
    COMMISSIONS_DIR,
    MATCHER_STATE_PATH,
    WORKSHEET_PATH,
    GPAQ_CONTRACT_PATH,
]

# Two-letter category short codes -- the same mapping used in
# notebooks/contract_review_analysis.ipynb's CATEGORY_INITIALS, kept
# identical here so the notebook and the interactive page agree.
CATEGORY_CODES = {
    "Agreement Date": "AD",
    "Anti-Assignment": "AA",
    "Audit Rights": "AR",
    "Cap on Liability": "CL",
    "Document Name": "DN",
    "Expiration Date": "ED",
    "Governing Law": "GL",
    "IP Ownership Assignment": "IP",
    "Insurance": "IN",
    "License Grant": "LG",
    "Non-Compete": "NC",
    "Parties": "PT",
}

# The findings report (data/runs/report.md) already pins these headline
# numbers. They are recomputed from the artefacts below and checked against
# this table -- a drift here means the artefacts changed underneath the
# published report, which is a bug in the pipeline, not a judgment call.
EXPECTED_HEADLINE = {
    "stream": 50,
    "holdout": 100,
    "reads": 52,
    "read_cap": 60,
    "comparisons": 776,
    "commissions": 12,
    "gate_failed": 1,
    "demoted": 3,
    "active": 8,
    "predictions_matched": 4,
    "predictions_total": 12,
}

# Hand-adjudicated family breakdown (data/runs/report.md, "The adjudication"
# section) -- a human read all 80 disagreement rows in
# evaluation_worksheet.md by hand; this is not machine-derived from any
# JSON artefact, so (like the notebook's own hand-adjudicated constant) it
# is hardcoded here, labelled as such, and cross-checked below against
# evaluation.json's own count of disagreement rows.
ADJUDICATION_FAMILIES_ROWS = [
    ("Key errors", 15),
    ("Ambiguous", 28),
    ("Comparator strictness", 19),
    ("Model errors", 8),
    ("Matcher errors", 10),
]
ADJUDICATION_TOTAL = 80

# Three demotion stories, paraphrase-tight from report.md's "Matcher
# lifecycle -- the honest arc" bullets (facts verbatim-faithful, wording
# tightened to fit a card).
DEMOTION_STORIES = [
    {
        "category": "Document Name",
        "batch": 3,
        "story": (
            "A bare Schedule A issued under a master agreement: the matcher "
            "named the schedule, the shadow read named the master. The key "
            "itself records both titles."
        ),
    },
    {
        "category": "Parties",
        "batch": 5,
        "story": (
            "Preamble scan overran into a BACKGROUND section and captured "
            "two defined terms as bogus parties — an unambiguous "
            "matcher defect, caught live."
        ),
    },
    {
        "category": "Governing Law",
        "batch": 6,
        "story": (
            "A Texas/Singapore/Belgium contract: the matcher’s closed "
            "US-state whitelist made the foreign clauses invisible, turning "
            "a real conflict into a confident wrong \"Texas\"."
        ),
    },
]

# Two exemplar clauses, hardcoded verbatim (public SEC-filed text, CUAD
# corpus, CC BY 4.0). The first is hardcoded here verbatim;
# the second is extracted from its source contract at build time (see
# _extract_gpaq_exemplar) and checked against this expected fragment so a
# change to the source text fails loudly instead of silently drifting.
EMBARK_CONTRACT = "EmbarkComInc_19991008_S-1A_EX-10.10_6487661_EX-10.10_Co-Branding Agreement.txt"
EMBARK_EXEMPLAR_TEXT = (
    "This Agreement shall be governed by, and construed in accordance with, "
    "the laws of the State of California without reference to its choice of "
    "law rules."
)
GPAQ_SENTENCE_START_MARKER = "Unless otherwise terminated as provided herein"
GPAQ_SENTENCE_END_MARKER = '"Term")'
GPAQ_EXPECTED_FRAGMENT = "shall terminate on December 31, 2034"

MAX_EXEMPLAR_CHARS = 420
MAX_LIMITS_CHARS = 600
MAX_REGEX_CHARS = 500
MAX_STORY_CHARS = 180
MAX_CONTEXT_CHARS = 480

# One failure story (IP Ownership Assignment never reached "active" -- its
# matcher failed the activation gate itself, the mechanism confirming the
# pre-registered prediction). Paraphrase-tight from report.md's "Matcher
# lifecycle" section, cross-checked below against matcher_state.json's own
# failed_at_batch.
FAILURE_STORIES = [
    {
        "category": "IP Ownership Assignment",
        "batch": 4,
        "story": (
            "The overseer’s attempt fired a false positive on a contract the "
            "model had already scored negative, in the gate’s own replay — "
            "frozen, never recommissioned."
        ),
    },
]

# CUAD citation + licence + not-legal-advice line, wording carried over from
# data/runs/report.md's Attribution section (markdown emphasis stripped;
# the clause-annotation spreadsheet is described, not named literally, per
# rule 10 in validate_corpus.py -- this module is not on that rule's
# whitelist).
ATTRIBUTION_TEXT = (
    "Corpus and annotations: CUAD v1 — Hendrycks, Burns, Chen & Ball, "
    "“CUAD: An Expert-Annotated NLP Dataset for Legal Contract "
    "Review,” NeurIPS 2021 Datasets and Benchmarks (arXiv:2103.06268). "
    "Dataset © The Atticus Project, CC BY 4.0. This project adapts "
    "CUAD’s clause-annotation spreadsheet into per-contract key files under "
    "the same licence. Nothing in this report is legal advice; the "
    "pipeline processes documents, it does not practise law."
)

PRICING_NOTE = (
    "Method B: measured Claude Sonnet 5 subagent tokens priced at published "
    "rates. Central estimate assumes an 85/15 input/output split at "
    "introductory pricing ($2/$10 per MTok in/out, in force through "
    "2026-08-31); list pricing ($3/$15 per MTok) is the alternate basis. "
    "All figures are estimates, not invoiced costs."
)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _fail(message: str) -> "None":
    """Raise a graceful, informative error instead of a bare crash."""
    raise SystemExit(f"build_interactive_data.py: {message}")


def _load_json(path: Path) -> dict:
    if not path.exists():
        _fail(f"required input not found: {path}")
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"could not read/parse {path}: {exc}")


def _load_text(path: Path) -> str:
    if not path.exists():
        _fail(f"required input not found: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        _fail(f"could not read {path}: {exc}")


def _round(value, ndigits: int = 3):
    """Round floats for a compact, stable JSON; pass through everything else
    (None, ints, strings, bools) unchanged."""
    if isinstance(value, float):
        return round(value, ndigits)
    return value


def _round_currency(value: float) -> float:
    return round(float(value), 2)


def _endash(text: str) -> str:
    """Convert an em-dash to a spaced en-dash (house typography) for OUR OWN
    display prose -- labels, paraphrased stories, attribution, extracted
    code-comment prose. Never applied to verbatim quoted contract text, key
    values, or matcher source code, which must stay byte-faithful to their
    artefact; callers are responsible for only passing authored prose
    through this function."""
    return re.sub(r"\s*—\s*", " – ", text)


def _slugify(category: str) -> str:
    """Category display name -> matcher/commission slug, e.g. "Cap on
    Liability" -> "cap-on-liability", "IP Ownership Assignment" ->
    "ip-ownership-assignment". Matches the slugs already fixed by
    commission.json / matcher_<slug>.py filenames on disk (checked, not
    assumed, in compute_category_detail)."""
    return category.lower().replace(" ", "-")


def _truncate(text: str, max_chars: int) -> str:
    """Trim verbatim text to at most max_chars, cutting on a word boundary
    and marking the cut with an ellipsis (the ellipsis counts toward the
    limit, so the result is never longer than max_chars)."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    ellipsis = "…"
    budget = max_chars - len(ellipsis)
    cut = text[:budget]
    last_space = cut.rfind(" ")
    if last_space > 0:
        cut = cut[:last_space]
    return cut.rstrip() + ellipsis


# ---------------------------------------------------------------------------
# Per-section builders
# ---------------------------------------------------------------------------

def compute_headline(
    evaluation: dict, stream_events: dict, extract_agent_log: dict, manifest: dict
) -> dict:
    """Every headline number, computed from the artefacts (never hardcoded)."""
    lifecycle = stream_events["matcher_lifecycle"]

    stream_size = evaluation["stream_size"]
    holdout_size = evaluation["holdout_size"]

    reads = extract_agent_log["reads_plus_retries"]
    read_cap = extract_agent_log["read_cap"]

    # 776 marked comparisons = every presence-scored row, stream (matcher +
    # model) plus holdout (matcher only) -- report.md: "776 (600 stream +
    # 176 holdout)".
    stream_presence_total = 0
    for scoring in evaluation["stream_scoring"].values():
        stream_presence_total += scoring["llm"]["presence_total"]
        stream_presence_total += scoring["matcher"]["presence_total"]
    holdout_presence_total = sum(
        scoring["presence_total"] for scoring in evaluation["holdout_scoring"].values()
    )
    comparisons = stream_presence_total + holdout_presence_total

    commissions = len(lifecycle)
    gate_failed = sum(1 for entry in lifecycle.values() if entry["status"] == "failed")
    demoted = sum(1 for entry in lifecycle.values() if entry["status"] == "demoted")
    active = sum(1 for entry in lifecycle.values() if entry["status"] == "active")

    predicted_vs_actual = evaluation["predicted_vs_actual"]
    predictions_matched = sum(1 for row in predicted_vs_actual if row["match"])
    predictions_total = len(predicted_vs_actual)

    headline = {
        "stream": stream_size,
        "holdout": holdout_size,
        "reads": reads,
        "read_cap": read_cap,
        "comparisons": comparisons,
        "commissions": commissions,
        "gate_failed": gate_failed,
        "demoted": demoted,
        "active": active,
        "predictions_matched": predictions_matched,
        "predictions_total": predictions_total,
    }

    # Cross-check against manifest.json's own recorded selection sizes.
    selection = manifest["selection"]
    if len(selection["stream"]) != stream_size:
        _fail(
            f"manifest stream count {len(selection['stream'])} != "
            f"evaluation.json stream_size {stream_size}"
        )
    if len(selection["holdout"]) != holdout_size:
        _fail(
            f"manifest holdout count {len(selection['holdout'])} != "
            f"evaluation.json holdout_size {holdout_size}"
        )

    # Fail loud on drift: the report already published these numbers.
    if headline != EXPECTED_HEADLINE:
        mismatches = {
            key: (headline[key], EXPECTED_HEADLINE[key])
            for key in EXPECTED_HEADLINE
            if headline[key] != EXPECTED_HEADLINE[key]
        }
        _fail(
            "computed headline numbers drifted from the published report "
            f"(computed, expected): {mismatches}"
        )

    return headline


def compute_codes() -> dict:
    if len(CATEGORY_CODES) != 12:
        _fail(f"expected 12 category codes, found {len(CATEGORY_CODES)}")
    if len(set(CATEGORY_CODES.values())) != 12:
        _fail("category short codes are not unique")
    return dict(CATEGORY_CODES)


def compute_timeline(stream_events: dict) -> list:
    """One entry per batch (1-8): contracts read, reads incl. per-batch
    retries, mean question-list size, and any matcher births/demotions."""
    lifecycle = stream_events["matcher_lifecycle"]

    births_by_batch: dict = {}
    demotions_by_batch: dict = {}
    for category, info in lifecycle.items():
        code = CATEGORY_CODES.get(category)
        if code is None:
            _fail(f"no short code mapped for category {category!r}")
        if info["active_from_batch"] is not None:
            births_by_batch.setdefault(info["active_from_batch"], []).append(code)
        if info["demoted_at_batch"] is not None:
            demotions_by_batch.setdefault(info["demoted_at_batch"], []).append(code)

    timeline = []
    for batch in stream_events["batches"]:
        batch_number = batch["batch"]
        scope_sizes = list(batch["scope_sizes"].values())
        if not scope_sizes:
            _fail(f"batch {batch_number} has no scope_sizes to average")
        mean_scope = sum(scope_sizes) / len(scope_sizes)
        timeline.append(
            {
                "batch": batch_number,
                "contracts": len(batch["contracts"]),
                "reads": batch["reads"],
                "mean_scope": _round(mean_scope),
                "births": sorted(births_by_batch.get(batch_number, [])),
                "demotions": sorted(demotions_by_batch.get(batch_number, [])),
            }
        )

    if [entry["batch"] for entry in timeline] != list(range(1, 9)):
        _fail(f"expected batches 1..8, found {[e['batch'] for e in timeline]}")

    # Every birth/demotion code must have landed on some batch in the
    # timeline (i.e. no lifecycle event pointing past batch 8).
    all_batches = {entry["batch"] for entry in timeline}
    for batch_number in list(births_by_batch) + list(demotions_by_batch):
        if batch_number not in all_batches:
            _fail(f"lifecycle event references batch {batch_number}, outside 1..8")

    return timeline


def compute_predicted_vs_actual(evaluation: dict) -> list:
    rows = []
    for row in evaluation["predicted_vs_actual"]:
        rows.append(
            {
                "category": row["category"],
                "predicted": row["predicted"],
                "actual": row["actual"],
                "match": bool(row["match"]),
                "status": row["status"],
                "holdout_coverage": _round(row["holdout_coverage"]),
                "holdout_accuracy": _round(row["holdout_accuracy"]),
                "holdout_n": row["holdout_n"],
                "stream_llm_accuracy": _round(row["stream_llm_accuracy"]),
            }
        )
    if len(rows) != 12:
        _fail(f"expected 12 predicted-vs-actual rows, found {len(rows)}")
    return rows


def compute_coverage(evaluation: dict, holdout_coverage: dict) -> list:
    """Active categories only, sorted by holdout coverage descending."""
    active_rows = [
        row for row in evaluation["predicted_vs_actual"] if row["status"] == "active"
    ]
    if len(active_rows) != 8:
        _fail(f"expected 8 active categories, found {len(active_rows)}")

    # Cross-check evaluation.json's per-category holdout coverage against
    # holdout_coverage.json's independently recorded answered/total counts.
    coverage_source = holdout_coverage["coverage"]
    active_from_holdout_file = set(holdout_coverage["active_categories"])
    active_from_eval = {row["category"] for row in active_rows}
    if active_from_holdout_file != active_from_eval:
        _fail(
            "active-category sets disagree between evaluation.json and "
            f"holdout_coverage.json: {active_from_eval} vs {active_from_holdout_file}"
        )
    for row in active_rows:
        record = coverage_source.get(row["category"])
        if record is None:
            _fail(f"holdout_coverage.json has no entry for {row['category']!r}")
        recomputed_coverage = record["answered"] / record["total"]
        if abs(recomputed_coverage - row["holdout_coverage"]) > 1e-9:
            _fail(
                f"{row['category']}: holdout_coverage.json coverage "
                f"{recomputed_coverage} disagrees with evaluation.json "
                f"{row['holdout_coverage']}"
            )

    coverage_rows = [
        {
            "category": row["category"],
            "coverage": _round(row["holdout_coverage"]),
            "accuracy": _round(row["holdout_accuracy"]),
            "n": row["holdout_n"],
        }
        for row in active_rows
    ]
    coverage_rows.sort(key=lambda entry: entry["coverage"], reverse=True)
    return coverage_rows


def _sum_scoring_path(scoring_by_category: dict, path_key: str | None) -> dict:
    """Sum presence/answer correctness across every category's scoring
    table. path_key selects the "matcher"/"llm" sub-table for stream
    scoring; pass None for holdout scoring, which has no sub-table."""
    presence_correct = presence_total = 0
    answer_correct = answer_total = 0
    for scoring in scoring_by_category.values():
        table = scoring[path_key] if path_key is not None else scoring
        presence_correct += table["presence_correct"]
        presence_total += table["presence_total"]
        answer_correct += table["answer_correct"]
        answer_total += table["answer_total"]
    presence_pct = round(100 * presence_correct / presence_total, 1) if presence_total else 0.0
    return {
        "n": presence_total,
        "presence_pct": presence_pct,
        "answers_correct": answer_correct,
        "answers_total": answer_total,
    }


def compute_accuracy_totals(evaluation: dict) -> dict:
    stream_scoring = evaluation["stream_scoring"]
    holdout_scoring = evaluation["holdout_scoring"]
    return {
        "stream_matcher": _sum_scoring_path(stream_scoring, "matcher"),
        "stream_llm": _sum_scoring_path(stream_scoring, "llm"),
        "holdout_matcher": _sum_scoring_path(holdout_scoring, None),
    }


def _matcher_header_text(source_text: str, tree: ast.AST) -> str:
    """The matcher's header, as prose: its module docstring if it has one
    (audit-rights, ip-ownership-assignment), else its leading `#`-comment
    block (the other ten). Whitespace-collapsed to a single line so a
    "Known limits" search doesn't have to cross line wraps."""
    docstring = ast.get_docstring(tree)
    if docstring:
        return re.sub(r"\s+", " ", docstring).strip()
    comment_lines = []
    for line in source_text.splitlines():
        if line.startswith("#"):
            stripped = line[1:]
            if stripped.startswith(" "):
                stripped = stripped[1:]
            comment_lines.append(stripped)
        elif comment_lines:
            break
    return re.sub(r"\s+", " ", " ".join(comment_lines)).strip()


_LIMITS_MARKERS = [
    # 11 of the 12 headers phrase the real passage as "Known limits (..." or
    # "Known limits: (...)"; requiring the "[:(]" tail excludes audit-rights'
    # bare-phrase section TITLE ("... and known limits\n----------"), which
    # a plain "known limits" search would otherwise match first.
    re.compile(r"known\s+limits\s*[:(]", re.IGNORECASE),
    # expiration-date is the one exception: its header never uses the phrase
    # "known limits" followed by ":" or "(" at all -- its limits passage is
    # headed "Known failure modes / what this matcher will silently NOT
    # handle" instead.
    re.compile(r"known\s+failure\s+modes", re.IGNORECASE),
]


def _extract_known_limits(source_text: str, tree: ast.AST, matcher_path: Path) -> str:
    """Pull the "Known limits" (or equivalent) passage out of the matcher's
    header (docstring or comment block, see _matcher_header_text), verbatim,
    trimmed to MAX_LIMITS_CHARS. This is the overseer's own explanatory
    prose, not a contract quotation, so house typography (_endash) is
    applied for display -- the code the matcher actually runs is never
    touched."""
    header_text = _matcher_header_text(source_text, tree)
    for marker in _LIMITS_MARKERS:
        match = marker.search(header_text)
        if match is not None:
            return _endash(_truncate(header_text[match.start():], MAX_LIMITS_CHARS))
    _fail(f"{matcher_path}: no 'known limits' passage found in header (tried {len(_LIMITS_MARKERS)} markers)")


def _extract_first_regex(tree: ast.AST, source_text: str, matcher_path: Path) -> str:
    """Pull the first `NAME = re.compile(...)` assignment out of the matcher
    source, in file order, regardless of the variable's name or whether it
    sits at module level or inside match() -- this generalises the old
    governing-law-only `_PRIMARY_RE` lookup to all twelve matcher files,
    which don't share a naming convention. Verbatim source code, trimmed to
    MAX_REGEX_CHARS; never passed through _endash (read-only code, shown
    exactly as the overseer wrote it)."""
    candidates = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr == "compile"
            and isinstance(value.func.value, ast.Name)
            and value.func.value.id == "re"
        ):
            candidates.append(node)
    if not candidates:
        _fail(f"{matcher_path}: no `re.compile(...)` assignment found")
    candidates.sort(key=lambda n: n.lineno)
    snippet = ast.get_source_segment(source_text, candidates[0])
    if not snippet:
        _fail(f"{matcher_path}: could not recover source for its first re.compile(...)")
    return _truncate(snippet, MAX_REGEX_CHARS)


def _load_category_exemplar(slug: str, category: str) -> dict:
    """One real accepted extraction -- the longest positive span among the
    category's induction set, i.e. the actual corpus language the model's
    accepted answer was built from and the overseer induced its matcher
    from. Real SEC-filed contract text (CUAD, CC BY 4.0), never the
    held-out key. Deterministic: ties broken by contract filename."""
    commission = _load_json(COMMISSIONS_DIR / slug / "commission.json")
    if commission["category"] != category:
        _fail(
            f"{slug}: commission.json category {commission['category']!r} != "
            f"expected {category!r}"
        )
    positives = commission["induction"]["positives"]
    if not positives:
        _fail(f"{slug}: commission.json has no induction positives")
    best_text = ""
    best_source = None
    for contract in sorted(positives):
        induction_path = COMMISSIONS_DIR / slug / "induction" / (contract[:-4] + ".json")
        record = _load_json(induction_path)
        spans = record.get("spans") or []
        if not spans:
            continue
        span_text = " ".join(spans[0].split())  # normalise internal whitespace
        if len(span_text) > len(best_text):
            best_text, best_source = span_text, contract
    if best_source is None:
        _fail(f"{slug}: no induction positive carries a non-empty span")
    return {"text": _truncate(best_text, MAX_EXEMPLAR_CHARS), "source": best_source}


def _load_matcher_pattern(category: str, slug: str) -> dict:
    """The matcher's own regex (verbatim code) and its author's "known
    limits" passage (prose, house-typography display copy), for every one
    of the 12 categories -- including the gate-failed and demoted ones,
    which still wrote real matcher files that are read-only session
    artefacts here, same as the 8 survivors."""
    matcher_path = MATCHERS_DIR / f"matcher_{slug}.py"
    source_text = _load_text(matcher_path)
    tree = ast.parse(source_text, filename=str(matcher_path))
    return {
        "regex": _extract_first_regex(tree, source_text, matcher_path),
        "limits": _extract_known_limits(source_text, tree, matcher_path),
    }


# ---------------------------------------------------------------------------
# evaluation_worksheet.md parsing -- one representative pipeline-vs-key
# disagreement per category, for the drill-down's third panel. Restricted to
# the "Mismatches" section only (not the presence-only or seeded-R-sample
# sections further down the same file, which use the same heading shape but
# a different population).
# ---------------------------------------------------------------------------

_WORKSHEET_HEADING_RE = re.compile(
    r"^### (?P<category>[A-Za-z][A-Za-z \-]*) / `(?P<contract>[^`]+)` "
    r"\(path: (?P<path>[a-z-]+), axis: (?P<axis>[a-z]+)\)$",
    re.MULTILINE,
)
_WORKSHEET_PATH_PRIORITY = {"matcher": 0, "llm-fallback": 1, "llm-discovery": 2}
_WORKSHEET_AXIS_PRIORITY = {"answer": 0, "presence": 1}


def _parse_worksheet_mismatches(worksheet_text: str) -> dict:
    """Returns {category: [(contract, path, axis, block_text), ...]} for
    every row in the "Mismatches" section."""
    start_marker = re.search(r"^## Mismatches", worksheet_text, re.MULTILINE)
    end_marker = re.search(r"^## Presence-only rows", worksheet_text, re.MULTILINE)
    if start_marker is None or end_marker is None:
        _fail(f"{WORKSHEET_PATH}: could not locate the Mismatches section boundaries")
    section = worksheet_text[start_marker.start(): end_marker.start()]

    headings = list(_WORKSHEET_HEADING_RE.finditer(section))
    if not headings:
        _fail(f"{WORKSHEET_PATH}: no disagreement rows found in the Mismatches section")

    by_category: dict = {}
    for i, m in enumerate(headings):
        block_start = m.end()
        block_end = headings[i + 1].start() if i + 1 < len(headings) else len(section)
        block_text = section[block_start:block_end]
        by_category.setdefault(m.group("category"), []).append(
            (m.group("contract"), m.group("path"), m.group("axis"), block_text)
        )
    return by_category


def _format_worksheet_answer(record: dict) -> str:
    """A short display string for one side (pipeline or key) of a worksheet
    row: the normalised answer if there is one, else present/absent."""
    answer = record.get("answer")
    if answer not in (None, ""):
        return str(answer)
    return "present (no answer recorded)" if record.get("present") else "absent"


def _extract_worksheet_context(block_text: str) -> str:
    context_match = re.search(
        r"context \(\+/-300 chars around the best-matching span\):\s*\n\n"
        r"((?:  > .*\n?)+)",
        block_text,
    )
    if context_match is None:
        _fail("worksheet block has no recognisable context quote")
    lines = [
        line[len("  > "):] if line.startswith("  > ") else line
        for line in context_match.group(1).splitlines()
    ]
    context_text = " ".join(" ".join(lines).split())  # normalise whitespace/newlines
    return _truncate(context_text, MAX_CONTEXT_CHARS)


def compute_worked_examples(worksheet_text: str, categories: list) -> dict:
    """One pipeline-vs-key disagreement example per category (None for a
    category with zero recorded disagreements, e.g. Insurance). Prefers a
    `path: matcher` row (shows the matcher's own wrong answer) over an
    `path: llm-*` row (shows the model's), and prefers axis `answer` over
    `presence` as the more informative tie-break -- both real, quoted,
    verbatim rows from the pipeline's own disagreement worksheet, never
    the answer-key file itself."""
    by_category = _parse_worksheet_mismatches(worksheet_text)
    examples: dict = {}
    for category in categories:
        rows = by_category.get(category)
        if not rows:
            examples[category] = None
            continue
        contract, path, axis, block_text = min(
            rows,
            key=lambda r: (
                _WORKSHEET_PATH_PRIORITY.get(r[1], 9),
                _WORKSHEET_AXIS_PRIORITY.get(r[2], 9),
            ),
        )
        pipeline_match = re.search(r"^- pipeline: (.+)$", block_text, re.MULTILINE)
        key_match = re.search(r"^- key:\s*(.+)$", block_text, re.MULTILINE)
        if pipeline_match is None or key_match is None:
            _fail(f"{category}/{contract}: worksheet block missing pipeline/key lines")
        try:
            pipeline_record = ast.literal_eval(pipeline_match.group(1))
            key_record = ast.literal_eval(key_match.group(1))
        except (ValueError, SyntaxError) as exc:
            _fail(f"{category}/{contract}: could not parse pipeline/key literal: {exc}")
        examples[category] = {
            "contract": contract,
            "path": path,
            "axis": axis,
            "pipeline_answer": _format_worksheet_answer(pipeline_record),
            "key_answer": _format_worksheet_answer(key_record),
            "context": _extract_worksheet_context(block_text),
        }
    if len(examples) != len(categories):
        _fail(f"expected {len(categories)} worked-example entries, built {len(examples)}")
    return examples


def _validated_lifecycle_stories(
    stories: list, state_by_category: dict, expected_count: int, batch_field: str
) -> list:
    """Cross-check a hardcoded (category, batch, story) list against
    matcher_state.json's own recorded batch number for that event, and
    house-typography the prose for display. Shared by the demotion stories
    (batch_field="demoted_at_batch") and the one failure story
    (batch_field="failed_at_batch")."""
    validated = []
    for story in stories:
        category = story["category"]
        if len(story["story"]) > MAX_STORY_CHARS:
            _fail(
                f"lifecycle story for {category!r} is {len(story['story'])} chars, "
                f"over the {MAX_STORY_CHARS}-char budget"
            )
        recorded_batch = state_by_category.get(category, {}).get(batch_field)
        if recorded_batch != story["batch"]:
            _fail(
                f"{category}: hardcoded {batch_field} {story['batch']} disagrees "
                f"with matcher_state.json's {recorded_batch}"
            )
        validated.append({**story, "story": _endash(story["story"])})
    if len(validated) != expected_count:
        _fail(f"expected {expected_count} lifecycle stories for {batch_field}, found {len(validated)}")
    return validated


def compute_category_detail(
    evaluation: dict, matcher_state: dict, worksheet_text: str, codes: dict
) -> list:
    """The drill-down's data: for each of the 12 categories, its predicted
    vs actual fate, its real corpus exemplar, its matcher's actual pattern
    (code + author's known limits), and -- where the worksheet recorded one
    -- a real pipeline-vs-key disagreement on a named contract."""
    pva_by_category = {row["category"]: row for row in evaluation["predicted_vs_actual"]}
    state_by_category = matcher_state["categories"]

    categories = sorted(codes)  # fixed, alphabetical order -- deterministic
    if set(categories) != set(pva_by_category):
        _fail("category set mismatch between codes and evaluation.json predicted_vs_actual")
    if set(categories) != set(state_by_category):
        _fail("category set mismatch between codes and matcher_state.json")

    demotion_stories = _validated_lifecycle_stories(
        DEMOTION_STORIES, state_by_category, 3, "demoted_at_batch"
    )
    failure_stories = _validated_lifecycle_stories(
        FAILURE_STORIES, state_by_category, 1, "failed_at_batch"
    )
    lifecycle_stories = {
        s["category"]: s["story"] for s in demotion_stories + failure_stories
    }
    worked_examples = compute_worked_examples(worksheet_text, categories)

    detail = []
    for category in categories:
        slug = _slugify(category)
        pva = pva_by_category[category]
        state = state_by_category[category]
        if state["status"] != pva["status"]:
            _fail(
                f"{category}: matcher_state.json status {state['status']!r} != "
                f"evaluation.json status {pva['status']!r}"
            )
        detail.append(
            {
                "category": category,
                "code": codes[category],
                "predicted": pva["predicted"],
                "actual": pva["actual"],
                "match": bool(pva["match"]),
                "status": pva["status"],
                "trust": state["trust"],
                # .get(..., None): Parties' record omits "failed_at_batch"
                # entirely (never reached "failed" status -- its one "failed"
                # history event was the protocol-failure recommission, not a
                # gate failure) -- the same lifecycle-key omission
                # router.py already reads defensively.
                "lifecycle": {
                    "commissioned_at_batch": state.get("commissioned_at_batch"),
                    "active_from_batch": state.get("active_from_batch"),
                    "demoted_at_batch": state.get("demoted_at_batch"),
                    "failed_at_batch": state.get("failed_at_batch"),
                },
                "lifecycle_story": lifecycle_stories.get(category),
                "exemplar": _load_category_exemplar(slug, category),
                "matcher": _load_matcher_pattern(category, slug),
                "worked_example": worked_examples[category],
            }
        )
    if len(detail) != 12:
        _fail(f"expected 12 category_detail entries, built {len(detail)}")
    return detail


def compute_demotion_stories(stream_events: dict) -> list:
    """Hardcoded (see DEMOTION_STORIES above), cross-checked against the
    batch numbers stream_events.json actually recorded for each demotion."""
    lifecycle = stream_events["matcher_lifecycle"]
    stories = []
    for story in DEMOTION_STORIES:
        category = story["category"]
        if len(story["story"]) > MAX_STORY_CHARS:
            _fail(
                f"demotion story for {category!r} is {len(story['story'])} chars, "
                f"over the {MAX_STORY_CHARS}-char budget"
            )
        recorded_batch = lifecycle.get(category, {}).get("demoted_at_batch")
        if recorded_batch != story["batch"]:
            _fail(
                f"{category}: hardcoded demotion batch {story['batch']} disagrees "
                f"with stream_events.json's demoted_at_batch {recorded_batch}"
            )
        stories.append({**story, "story": _endash(story["story"])})
    if len(stories) != 3:
        _fail(f"expected 3 demotion stories, found {len(stories)}")
    return stories


def compute_adjudication(evaluation: dict) -> dict:
    total_rows = sum(rows for _, rows in ADJUDICATION_FAMILIES_ROWS)
    if total_rows != ADJUDICATION_TOTAL:
        _fail(f"adjudication family rows sum to {total_rows}, expected {ADJUDICATION_TOTAL}")
    recorded_mismatches = evaluation["worksheet_counts"]["mismatches"]
    if recorded_mismatches != ADJUDICATION_TOTAL:
        _fail(
            f"evaluation.json records {recorded_mismatches} disagreement rows, "
            f"expected {ADJUDICATION_TOTAL} (hand-adjudication total)"
        )
    families = [
        {
            "name": name,
            "rows": rows,
            "share_pct": round(100 * rows / ADJUDICATION_TOTAL, 1),
        }
        for name, rows in ADJUDICATION_FAMILIES_ROWS
    ]
    return {
        "families": families,
        "total": ADJUDICATION_TOTAL,
        "note": "hand-adjudicated; see data/runs/report.md",
    }


def compute_costs(evaluation: dict, extract_agent_log: dict) -> dict:
    costs = evaluation["costs"]
    total_tokens = costs["total_measured_subagent_tokens"]
    if total_tokens != extract_agent_log["total_tokens"]:
        _fail(
            "total token count disagrees between evaluation.json "
            f"({total_tokens}) and extract_agent_log.json "
            f"({extract_agent_log['total_tokens']})"
        )
    return {
        "total_tokens": total_tokens,
        "run_central_intro_usd": _round_currency(
            costs["run_cost_bands_total"]["introductory"]["central_usd"]
        ),
        "run_central_list_usd": _round_currency(
            costs["run_cost_bands_total"]["list"]["central_usd"]
        ),
        "counterfactual_central_intro_usd": _round_currency(
            costs["holdout_counterfactual_cost_bands"]["introductory"]["central_usd"]
        ),
        "mean_tokens_per_read": round(costs["mean_tokens_per_read"]),
        "estimate": True,
        "pricing_note": _endash(PRICING_NOTE),
    }


def _extract_gpaq_exemplar() -> str:
    text = _load_text(GPAQ_CONTRACT_PATH)
    start = text.find(GPAQ_SENTENCE_START_MARKER)
    if start == -1:
        _fail(f"{GPAQ_CONTRACT_PATH}: exemplar sentence start marker not found")
    end = text.find(GPAQ_SENTENCE_END_MARKER, start)
    if end == -1:
        _fail(f"{GPAQ_CONTRACT_PATH}: exemplar sentence end marker not found")
    end += len(GPAQ_SENTENCE_END_MARKER)
    if end < len(text) and text[end] == ".":
        end += 1
    span = " ".join(text[start:end].split())  # normalise internal whitespace
    if GPAQ_EXPECTED_FRAGMENT not in span:
        _fail(
            f"{GPAQ_CONTRACT_PATH}: extracted span does not contain the "
            f"expected fragment {GPAQ_EXPECTED_FRAGMENT!r}: {span!r}"
        )
    if len(span) > MAX_EXEMPLAR_CHARS:
        _fail(
            f"{GPAQ_CONTRACT_PATH}: exemplar span is {len(span)} chars, "
            f"over the {MAX_EXEMPLAR_CHARS}-char budget"
        )
    return span


def compute_exemplars() -> list:
    if len(EMBARK_EXEMPLAR_TEXT) > MAX_EXEMPLAR_CHARS:
        _fail("Embark exemplar text exceeds the character budget")
    gpaq_text = _extract_gpaq_exemplar()
    return [
        {
            "label": _endash("Governing Law — the formulaic end"),
            "text": EMBARK_EXEMPLAR_TEXT,
            "source": EMBARK_CONTRACT,
        },
        {
            "label": _endash("a negotiated term — the bespoke end"),
            "text": gpaq_text,
            "source": GPAQ_CONTRACT_PATH.name,
        },
    ]


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def build_data() -> dict:
    print("Loading run artefacts...", flush=True)
    evaluation = _load_json(EVALUATION_PATH)
    stream_events = _load_json(STREAM_EVENTS_PATH)
    holdout_coverage = _load_json(HOLDOUT_COVERAGE_PATH)
    extract_agent_log = _load_json(EXTRACT_AGENT_LOG_PATH)
    manifest = _load_json(MANIFEST_PATH)
    matcher_state = _load_json(MATCHER_STATE_PATH)
    worksheet_text = _load_text(WORKSHEET_PATH)

    print("Computing headline numbers (asserting against the published report)...", flush=True)
    headline = compute_headline(evaluation, stream_events, extract_agent_log, manifest)

    print("Deriving category short codes...", flush=True)
    codes = compute_codes()

    print("Building the eight-batch timeline (births, demotions, mean scope)...", flush=True)
    timeline = compute_timeline(stream_events)

    print("Assembling predicted-vs-actual (12 categories)...", flush=True)
    predicted_vs_actual = compute_predicted_vs_actual(evaluation)

    print("Computing holdout coverage for active categories...", flush=True)
    coverage = compute_coverage(evaluation, holdout_coverage)

    print("Recomputing stream/holdout accuracy totals...", flush=True)
    accuracy_totals = compute_accuracy_totals(evaluation)

    print(
        "Building the category drill-down (12x: real exemplar, matcher pattern, "
        "worked disagreement example)...",
        flush=True,
    )
    category_detail = compute_category_detail(evaluation, matcher_state, worksheet_text, codes)

    print("Checking the three hardcoded demotion stories against the lifecycle log...", flush=True)
    demotion_stories = compute_demotion_stories(stream_events)

    print("Checking the hardcoded adjudication family breakdown...", flush=True)
    adjudication = compute_adjudication(evaluation)

    print("Computing cost figures...", flush=True)
    costs = compute_costs(evaluation, extract_agent_log)

    print("Extracting the two exemplar clauses (one hardcoded, one read from source)...", flush=True)
    exemplars = compute_exemplars()

    data = {
        "headline": headline,
        "codes": codes,
        "timeline": timeline,
        "predicted_vs_actual": predicted_vs_actual,
        "coverage": coverage,
        "accuracy_totals": accuracy_totals,
        "category_detail": category_detail,
        "demotion_stories": demotion_stories,
        "adjudication": adjudication,
        "costs": costs,
        "exemplars": exemplars,
        "attribution": _endash(ATTRIBUTION_TEXT),
    }
    return data


def main() -> None:
    # Guard rail from the house rules: never write where we read from.
    for input_path in INPUT_PATHS:
        if input_path.resolve() == OUTPUT_PATH.resolve():
            _fail(f"output path {OUTPUT_PATH} collides with an input path")

    data = build_data()

    print(f"Writing {OUTPUT_PATH}...", flush=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    serialised = json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    OUTPUT_PATH.write_text(serialised, encoding="utf-8")

    size_bytes = OUTPUT_PATH.stat().st_size
    print(f"Wrote {size_bytes:,} bytes.", flush=True)
    if size_bytes >= MAX_OUTPUT_BYTES:
        _fail(f"output is {size_bytes} bytes, at or over the {MAX_OUTPUT_BYTES}-byte budget")

    # Parse-back sanity check.
    with OUTPUT_PATH.open(encoding="utf-8") as handle:
        reloaded = json.load(handle)
    if reloaded != data:
        _fail("round-tripped JSON does not equal the in-memory data (encoding bug)")

    print("Done: interactive/_data.json parses, round-trips, and is under the size budget.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        raise
