"""build_data.py -- assembles interactive/_data.json (and interactive/CANDIDATES.md) for the
case 11 interactive explorer page ("Skills library").

Follows the house pattern (09 Training Outcomes: interactive/build_data.py -> _data.json ->
_template.html).  It builds the data that _template.html reads.

Read-only on everything outside interactive/.  Every number in _data.json is read from, or
counted from, the case's own files:

    data/analysis/marked_runs.jsonl      correct / wrong per run (code/mark.py + adjudication)
    data/analysis/collected_runs.jsonl   each run's answer, assumptions, caveats, SQL, tokens
    data/key/key.json                    reference results, accepted readings, naive variants
    data/key/review_sheet.md             the key's "where this is written down" line per request
    data/requests/test_requests.json     the 60 request texts
    data/analysis/results.json           class counts, tokens (used to cross-check, not to copy)
    data/analysis/report.md              section 2: the twelve predictions' verdicts and numbers
    design/predictions-FROZEN-2026-10-15.md   the twelve bets, as frozen before the runs
    arms/prompt_doc.md, arms/library/    the rules, and where the library holds each one
    world/*.md, data/facts.yaml          section headings and fact ids, to resolve the key's citations

Run (Python 3.10 or later with PyYAML):
    python interactive/build_data.py
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

# ============================================================================================
# CONFIG  (everything tunable lives here)
# ============================================================================================

HERE = Path(__file__).resolve().parent
CASE_ROOT = HERE.parent

PATH_MARKED = CASE_ROOT / "data" / "analysis" / "marked_runs.jsonl"
PATH_COLLECTED = CASE_ROOT / "data" / "analysis" / "collected_runs.jsonl"
PATH_RESULTS = CASE_ROOT / "data" / "analysis" / "results.json"
PATH_REPORT = CASE_ROOT / "data" / "analysis" / "report.md"
PATH_KEY = CASE_ROOT / "data" / "key" / "key.json"
PATH_REVIEW_SHEET = CASE_ROOT / "data" / "key" / "review_sheet.md"
PATH_TEST_REQUESTS = CASE_ROOT / "data" / "requests" / "test_requests.json"
PATH_FACTS = CASE_ROOT / "data" / "facts.yaml"
PATH_PROMPT_DOC = CASE_ROOT / "arms" / "prompt_doc.md"
PATH_LIBRARY = CASE_ROOT / "arms" / "library"
PATH_WORLD = CASE_ROOT / "world"
PATH_PREDICTIONS = CASE_ROOT / "design" / "predictions-FROZEN-2026-10-15.md"   # internal record, not published; only the bets' titles and wording are read

OUT_JSON = HERE / "_data.json"                    # PUBLIC: inlined into the served page; only what the page reads
OUT_JSON_INTERNAL = HERE / "_data_internal.json"  # everything, for the record; stays in the case folder, never published
OUT_CANDIDATES = HERE / "CANDIDATES.md"

SIZE_BUDGET_KB = 300

# What the page uses.  CANDIDATES.md is still written from the full sets.
PAGE_MODULE1_ORDER = ["REQ-T15", "REQ-T25", "REQ-T07", "REQ-T22", "REQ-T21"]
PAGE_MODULE2_ORDER = ["REQ-T24", "REQ-T30", "REQ-T59", "REQ-T31", "REQ-T08", "REQ-T05"]

# The six setups in the order the report uses.  `cell` is the name results.json uses.
SETUPS = [
    {"id": "sonnet_S", "model": "sonnet", "arm": "S", "cell": "Sonnet S", "short": "Sonnet S",
     "label": "Sonnet, database only", "what": "Sees the database and nothing else (schema only)."},
    {"id": "sonnet_D", "model": "sonnet", "arm": "D", "cell": "Sonnet D", "short": "Sonnet D",
     "label": "Sonnet with one shared document", "what": "Same, plus the company's house-knowledge document (arms/prompt_doc.md)."},
    {"id": "sonnet_L", "model": "sonnet", "arm": "L", "cell": "Sonnet L", "short": "Sonnet L",
     "label": "Sonnet with the skills library", "what": "Same 62 facts as the document, as ten skills with SQL templates and two check scripts."},
    {"id": "sonnet_Lm", "model": "sonnet", "arm": "L-", "cell": "Sonnet L-", "short": "Sonnet L−",
     "label": "Sonnet with the library, no scripts", "what": "The skills library with its scripts removed."},
    {"id": "haiku_S", "model": "haiku", "arm": "S", "cell": "Haiku S", "short": "Haiku S",
     "label": "Haiku, database only", "what": "The smaller model, schema only."},
    {"id": "haiku_L", "model": "haiku", "arm": "L", "cell": "Haiku L", "short": "Haiku L",
     "label": "Haiku with the skills library", "what": "The smaller model with the library."},
]
SETUP_BY_KEY = {(s["model"], s["arm"]): s for s in SETUPS}

# Lay-reader groups of the key's trap classes.  A request that carries classes
# from two groups counts in both (the lay groups overlap); `exclusive_priority` also gives each
# request exactly one home so a chart can add up to 60.
LAY_GROUPS = [
    {"id": "simple", "label": "Simple lookups", "classes": ["clean"]},
    {"id": "definitions", "label": "Company definitions", "classes": ["company_definition"]},
    {"id": "calendar_history", "label": "Calendar and history", "classes": ["fiscal_calendar", "scd", "migration", "time_zone"]},
    {"id": "data_handling", "label": "Data handling", "classes": ["fan_out", "semi_additive", "vat", "exclusions"]},
    {"id": "judgement", "label": "Judgement calls", "classes": ["ambiguous", "override"]},
    {"id": "undocumented", "label": "Undocumented problems", "classes": ["undocumented"]},
]
CLASS_LABELS = {
    "clean": "clean", "company_definition": "company definition", "fiscal_calendar": "fiscal calendar", "scd": "history of regions or categories (scd)",
    "migration": "web-platform migration", "time_zone": "time zone", "fan_out": "double counting in joins (fan-out)",
    "semi_additive": "stock (semi-additive)", "vat": "VAT", "exclusions": "exclusions", "ambiguous": "ambiguous request",
    "override": "request overrides a default", "undocumented": "undocumented data problem",
}

# Module 3: how a request is counted as depending on a rule.
RUNS_NAMING_MIN_RUNS = 5          # of the 15 correct Sonnet D/L/L- runs on that request
LIBRARY_HUB_SKILLS = {"metric-dictionary", "warehouse-map", "query-check"}   # generic hubs, never a rule's "home"

# Module 3: free-text phrases in the key's "where this is written down" lines that do not match a
# heading or a fact's wording, mapped to the fact ids they point at (checked by hand against world/).
CITATION_ALIASES = {
    ("data quality register", "outdoor lighting move"): ["REG-OUTDOOR-LIGHTING"],
    ("data quality register", "cancelled web orders"): ["REG-CANCELLED"],
    ("data quality register", "store openings"): ["REG-STORE-EVENTS"],
    ("data quality register", "refit closures"): ["REG-REFITS"],
    ("data quality register", "staff_purchase_flag"): ["REG-STAFF-PURCHASE"],
    ("data quality register", "time"): ["REG-UTC"],
    ("team notes", "explicitly asks"): ["TEAM-EXPLICIT-REQUEST"],
    ("team notes", "lfl edge cases"): ["TEAM-LFL-EDGE"],
    ("team notes", "check the total against rpt_daily_store_sales"): ["TEAM-CONTROL-TOTALS"],
    ("team notes", "always filter out store 999 and category zz test"): ["TEAM-EXCLUSIONS"],
    ("data quality register", "the vat rate rose from 24% to 25.5% on 1 september 2024"): ["REG-VAT-CHANGE"],
    ("data quality register", "guest web orders have no member key. logged-in orders carry the member's key"): ["REG-GUEST-ORDERS"],
    ("data quality register", "fact_campaign_exposure has one row per contact. reduce to one row per member before joining to sales"): ["REG-EXPOSURE-FANOUT"],
    ("data quality register", "holdout members are never contacted"): ["REG-CONSENT"],
}

# Parentheses in the key's pointers ('Metric dictionary, \'Fiscal calendar\' (compare week to week)') that say which part of a
# section the answer leans on, mapped to fact ids (checked by hand against world/metric_dictionary.md).  Parts are lower case.
HINT_ALIASES = {
    "compare week to week": ["CAL-COMPARE"],
    "compare by the same fiscal week, not the same dates": ["CAL-COMPARE"],
    "week-aligned": ["CAL-COMPARE"],
    "relative terms": ["CAL-RELATIVE"],
    "last period": ["CAL-RELATIVE"],
    "ytd": ["CAL-RELATIVE"],
    "closed days": ["CAL-CLOSED-DAYS"],
    "as-is": ["DEF-HIERARCHY-ASIS"],
    "as-is regions": ["DEF-HIERARCHY-ASIS"],
    "as-was": ["DEF-HIERARCHY-ASIS"],
    "store league table": ["DEF-STORE-LEAGUE"],
    "store counts": ["DEF-STORE-SCOPE"],
    "store counts and store-level analyses cover physical stores only": ["DEF-STORE-SCOPE"],
    "helsinki is the default": ["DEF-TIMEZONE"],
    "web orders are counted on the order date in helsinki time": ["DEF-WEB-ORDER-COUNT"],
    "cancelled orders are not counted": ["DEF-WEB-CANCELLED"],
    "dispatch date in helsinki time": ["DEF-WEB-RECOGNITION"],
    "dispatch date": ["DEF-WEB-RECOGNITION"],
    "click-and-collect share": ["DEF-CLICK-COLLECT"],
    "including-vat figures come from gross_amount": ["DEF-VAT-GROSS"],
    "including-vat figures from gross_amount": ["DEF-VAT-GROSS"],
    "figures including vat come from gross_amount": ["DEF-VAT-GROSS"],
    "never one flat rate": ["DEF-VAT-GROSS"],
    "sale-week cohort": ["DEF-RETURN-RATE"],
    "atv": ["DEF-ATV"],
    "atv is a store measure by default": ["DEF-ATV"],
    "active member": ["DEF-ACTIVE-MEMBER"],
    "new member": ["DEF-NEW-MEMBER"],
    "member share of sales": ["DEF-MEMBER-SHARE"],
    "campaign uplift": ["DEF-UPLIFT"],
    "weeks of cover": ["DEF-WEEKS-COVER"],
    "never add across weeks": ["DEF-STOCK-SEMIADD"],
    "add across stores and products": ["DEF-STOCK-SEMIADD"],
    "average the weekly closings": ["DEF-STOCK-SEMIADD"],
    "store 900, not channel_code": ["REG-STORE-900"],
    "channel_code is not filled after 3 november 2025": ["REG-MIGRATION"],
}

# Jargon / internal ids a lay reader would not follow, flagged on every quoted run line.
JARGON_PATTERNS = [
    ("table or column name", re.compile(r"\b(?:fact|dim|rpt|ref|stg|bak|tmp|campaign)_[a-z0-9_]+\b|\brpt\.v_[a-z_]+\b", re.I)),
    ("table or column name", re.compile(r"\b[a-z]+_(?:id|key|date|code|flag|ts_utc|total|state|type)\b|\bis_[a-z_]+\b|\bvalid_(?:from|to)\b", re.I)),
    ("internal id", re.compile(r"\bREQ-[A-Z]\d+\b|\b(?:DEF|CAL|REG|TEAM)-[A-Z0-9-]+\b")),
    ("store or campaign number", re.compile(r"\bstores?\s+(?:9\d\d|1\d\d)\b|\((?:9\d\d|1\d\d)\)|\bstores? \d{3}(?:\s*(?:to|-)\s*\d{3})?\b|\bcampaign\s+(?:id\s+)?\d+\b", re.I)),
    ("fiscal code", re.compile(r"\bP0?\d{1,2}\b|\bFY\d{2,4}/\d{2}\b|\bQ\d\b")),
    ("technical term", re.compile(r"\b(?:SQL|ETL|UTC|DuckDB|CTE|SKU|EET|timestamp|snapshot|grain|fan-out)\b", re.I)),
]

# ============================================================================================
# SMALL HELPERS
# ============================================================================================

def log(message: str) -> None:
    print(f"[build_data] {message}", flush=True)


def fail(message: str) -> None:
    raise SystemExit(f"[build_data] FATAL: {message}")


def load_json(path: Path):
    if not path.exists():
        fail(f"required file missing: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_jsonl(path: Path) -> list:
    if not path.exists():
        fail(f"required file missing: {path}")
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_text(path: Path) -> str:
    if not path.exists():
        fail(f"required file missing: {path}")
    return path.read_text(encoding="utf-8")


def jargon_in(text: str) -> list:
    """Terms in `text` that a lay reader would not follow (table names, ids, codes)."""
    found = []
    for _label, pattern in JARGON_PATTERNS:
        for match in pattern.finditer(text):
            term = match.group(0)
            if term.lower() not in [f.lower() for f in found]:
                found.append(term)
    return found


def quote(text: str) -> dict:
    """A run's own words, verbatim, with a jargon flag list when needed."""
    terms = jargon_in(text)
    return {"t": text, "j": terms} if terms else {"t": text}


def round_number(value, places=2):
    if isinstance(value, float):
        return round(value, places)
    return value


def run_lines(run: dict) -> list:
    """Every sentence a run wrote about its choices: assumptions, caveats, definitions applied."""
    answer = run.get("answer") or {}
    lines = []
    for field in ("assumptions", "caveats", "definitions_applied"):
        for item in answer.get(field) or []:
            if isinstance(item, str):
                lines.append(item)
    return lines


def run_sql(run: dict) -> str:
    return ((run.get("answer") or {}).get("sql")) or ""


def cell_equals(cell, wanted) -> bool:
    if cell is None:
        return False
    if isinstance(wanted, (int, float)) and isinstance(cell, (int, float)):
        return abs(float(cell) - float(wanted)) < 1e-9
    return str(cell).strip().casefold() == str(wanted).strip().casefold()


def extract_headline(result: dict | None, spec: dict):
    """Pick one headline number out of a result table.

    spec: {"row": value-or-None, "row_col_re": regex for the column that holds `row`,
           "col_re": regex for the measure column, "avoid_re": measure columns to skip}
    Returns {"value": number, "column": name, "row": value} or None.
    """
    if not result:
        return None
    columns = result.get("columns") or []
    rows = result.get("rows") or []
    if not rows:
        return None
    chosen_row = None
    if spec.get("row") is None:
        chosen_row = rows[0]
    else:
        row_col_re = re.compile(spec["row_col_re"], re.I) if spec.get("row_col_re") else None
        for row in rows:
            for index, cell in enumerate(row):
                if row_col_re and not row_col_re.search(str(columns[index])):
                    continue
                if cell_equals(cell, spec["row"]):
                    chosen_row = row
                    break
            if chosen_row is not None:
                break
    if chosen_row is None:
        return None
    col_re = re.compile(spec["col_re"], re.I) if spec.get("col_re") else None
    avoid_re = re.compile(spec["avoid_re"], re.I) if spec.get("avoid_re") else None
    numeric_columns = [
        (index, name) for index, (name, cell) in enumerate(zip(columns, chosen_row))
        if isinstance(cell, (int, float)) and not isinstance(cell, bool)
    ]
    hits = [
        (index, name) for index, name in numeric_columns
        if (col_re is None or col_re.search(str(name))) and not (avoid_re and avoid_re.search(str(name)))
    ]
    if spec.get("row") is not None and spec.get("row_col_re"):
        # do not return the very column used to find the row
        row_col_re = re.compile(spec["row_col_re"], re.I)
        hits = [(i, n) for i, n in hits if not row_col_re.search(str(n))]
    if not hits:
        return None
    index, name = hits[0]
    return {"value": chosen_row[index], "column": name, "row": spec.get("row")}


def trim_table(result: dict | None, keep_rows: int = 6, always_keep=None, key_col: str | None = None) -> dict | None:
    """Keep a result table small: the first rows, plus any row whose first cell(s) match `always_keep`."""
    if not result:
        return None
    columns = result.get("columns") or []
    rows = result.get("rows") or []
    if len(rows) <= keep_rows:
        return {"columns": columns, "rows": rows, "n_rows": len(rows)}
    kept = list(rows[:keep_rows])
    if always_keep is not None:
        for row in rows[keep_rows:]:
            if any(cell_equals(cell, always_keep) for cell in row):
                kept.append(row)
    return {"columns": columns, "rows": kept, "n_rows": len(rows), "trimmed": True}


# ============================================================================================
# LOAD EVERYTHING ONCE
# ============================================================================================

class Case:
    """All source data, loaded once and indexed."""

    def __init__(self) -> None:
        log("loading marked runs, collected runs, key, requests, results ...")
        self.marked = load_jsonl(PATH_MARKED)
        self.collected = load_jsonl(PATH_COLLECTED)
        self.results = load_json(PATH_RESULTS)
        key_file = load_json(PATH_KEY)
        self.key = {entry["request_id"]: entry for entry in key_file["entries"]}
        self.requests = {r["id"]: r for r in load_json(PATH_TEST_REQUESTS)}
        self.facts = {f["id"]: f for f in yaml.safe_load(load_text(PATH_FACTS)) if not f["id"].startswith("SCH-")}
        self.marked_by_run = {m["run_id"]: m for m in self.marked}
        self.run_by_id = {r["run_id"]: r for r in self.collected}
        if len(self.marked) != 1800 or len(self.collected) != 1800:
            fail(f"expected 1,800 marked and collected runs, got {len(self.marked)} and {len(self.collected)}")
        if len(self.key) != 60 or len(self.requests) != 60:
            fail("expected 60 requests in the key and in test_requests.json")
        # runs[request_id][setup_id] -> list of (run, mark) ordered by repeat
        self.runs: dict = defaultdict(lambda: defaultdict(list))
        for run in self.collected:
            mark = self.marked_by_run[run["run_id"]]
            setup = SETUP_BY_KEY[(run["model"], run["arm"])]
            self.runs[run["request_id"]][setup["id"]].append((run, mark))
        for request_id in self.runs:
            for setup_id in self.runs[request_id]:
                self.runs[request_id][setup_id].sort(key=lambda pair: pair[0]["repeat"])
                if len(self.runs[request_id][setup_id]) != 5:
                    fail(f"{request_id} {setup_id} does not have 5 runs")

    def n_correct(self, request_id: str, setup_id: str) -> int:
        return sum(1 for _run, mark in self.runs[request_id][setup_id] if mark["outcome"] == "correct")


# ============================================================================================
# MODULE 3 (built first: modules 1 and 4 quote its lines)  --  THE RULES, WRITTEN DOWN
# ============================================================================================

FACT_ID_RE = re.compile(r"\b((?:DEF|CAL|REG|TEAM)-[A-Z0-9-]*[A-Z0-9])\b")
MARKER_RE = re.compile(r"^<!--\s*(facts|source):\s*(.*?)\s*-->\s*$")
HEADING_RE = re.compile(r"^##\s+(\d+)\.\s+(.*)$")


def parse_prompt_doc(text: str) -> dict:
    """Split arms/prompt_doc.md into sections and tagged blocks (a block = the markers and the text under them)."""
    lines = text.splitlines()
    sections = [{"no": 0, "title": "Opening", "first_line": 1}]
    blocks = []
    current = None
    pending_facts: list = []
    pending_sources: list = []
    pending_marker_line = None
    section_no = 0

    def close_block():
        nonlocal current
        if current is not None:
            current["text"] = "\n".join(current["body"]).strip()
            del current["body"]
            if current["text"] or current["fact_ids"] or current["sources"]:
                blocks.append(current)
        current = None

    for line_number, line in enumerate(lines, start=1):
        heading = HEADING_RE.match(line)
        if heading:
            close_block()
            pending_facts, pending_sources = [], []
            section_no = int(heading.group(1))
            sections.append({"no": section_no, "title": heading.group(2).strip(), "first_line": line_number})
            continue
        marker = MARKER_RE.match(line)
        if marker:
            body_so_far = current is not None and any(part.strip() for part in current["body"])
            if current is None or body_so_far:
                close_block()
                current = {"section_no": section_no, "fact_ids": [], "sources": [], "first_line": line_number, "last_line": line_number, "body": []}
            if marker.group(1) == "facts":
                current["fact_ids"].extend(FACT_ID_RE.findall(marker.group(2)))
            else:
                current["sources"].extend([s.strip() for s in marker.group(2).split(",") if s.strip()])
            continue
        if current is None:
            if line.strip() and not line.startswith("#"):
                current = {"section_no": section_no, "fact_ids": [], "sources": [], "first_line": line_number, "last_line": line_number, "body": [line]}
            continue
        current["body"].append(line)
        if line.strip():
            current["last_line"] = line_number
    close_block()
    return {"sections": sections, "blocks": blocks, "lines": lines}


def library_fact_map() -> dict:
    """fact id -> list of library files (relative) that carry a `facts:` tag for it."""
    mapping: dict = defaultdict(set)
    for path in sorted(PATH_LIBRARY.rglob("*")):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r"facts:\s*([^>\n]*)", text):
            for fact_id in FACT_ID_RE.findall(match.group(1)):
                mapping[fact_id].add(path.relative_to(PATH_LIBRARY).as_posix())
    return {fact_id: sorted(files) for fact_id, files in mapping.items()}


def library_inventory() -> dict:
    files = [p for p in PATH_LIBRARY.rglob("*") if p.is_file()]
    skills = sorted(p.parent.name for p in files if p.name == "SKILL.md")
    return {
        "skills": skills,
        "n_skills": len(skills),
        "n_templates": sum(1 for p in files if p.suffix == ".sql"),
        "n_reference_files": sum(1 for p in files if "references" in p.parts),
        "n_scripts": sum(1 for p in files if p.suffix == ".py"),
        "n_files": len(files),
    }


def skill_descriptions() -> dict:
    """skill name -> (name + description line of its SKILL.md), lower case."""
    out = {}
    for skill_file in sorted(PATH_LIBRARY.glob("*/SKILL.md")):
        text = skill_file.read_text(encoding="utf-8")
        match = re.search(r"^description:\s*(.*)$", text, re.M)
        out[skill_file.parent.name] = (skill_file.parent.name + " " + (match.group(1) if match else "")).lower()
    return out


def home_skill(fact: dict, files: list, descriptions: dict) -> str | None:
    """The one topical skill to show as a rule's home.

    Candidates are the non-hub skills whose SKILL.md carries the fact's tag (hubs only if there is no other).
    Ranked by: how many of the fact's check phrases (facts.yaml must_contain) appear in the skill's name and
    description; then how many library files of that skill carry the tag; then alphabetical.  The full list of
    skills and files is output beside it, so this is a convenience, never the only answer.
    """
    carrying = sorted({f.split("/")[0] for f in files if f.endswith("/SKILL.md")})
    topical = [s for s in carrying if s not in LIBRARY_HUB_SKILLS]
    pool = topical or carrying
    if not pool:
        return None
    files_per_skill = Counter(f.split("/")[0] for f in files)
    phrases = [p.lower() for p in fact["must_contain"]]

    def score(skill: str):
        return (-sum(1 for p in phrases if p in descriptions.get(skill, "")), -files_per_skill[skill], skill)

    return sorted(pool, key=score)[0]


def parse_world_docs() -> dict:
    """world/*.md -> {doc_key: {"headings": {heading_lower: [fact ids]}, "blocks": [(fact_ids, text_lower)]}}."""
    docs = {}
    for doc_key, filename in (("metric dictionary", "metric_dictionary.md"), ("data quality register", "data_quality_register.md"), ("team notes", "team_notes.md")):
        text = load_text(PATH_WORLD / filename)
        headings: dict = defaultdict(list)
        blocks = []
        current_heading = None
        current_facts: list = []
        current_text: list = []

        def flush():
            if current_facts:
                blocks.append((list(current_facts), " ".join(current_text).lower()))

        for line in text.splitlines():
            heading = re.match(r"^##\s+(?:\d+\.\s+)?(.*)$", line)
            marker = MARKER_RE.match(line)
            if heading:
                flush()
                current_facts, current_text = [], []
                current_heading = heading.group(1).strip().lower()
                continue
            if marker and marker.group(1) == "facts":
                flush()
                current_facts = FACT_ID_RE.findall(marker.group(2))
                current_text = []
                for fact_id in current_facts:
                    if current_heading:
                        headings[current_heading].append(fact_id)
                continue
            if current_facts and line.strip():
                current_text.append(line.strip())
        flush()
        docs[doc_key] = {"headings": dict(headings), "blocks": blocks}
    return docs


def split_top_level(text: str, separator: str = ";") -> list:
    """Split on `separator` only outside parentheses."""
    parts, depth, current = [], 0, []
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if char == separator and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def single_quoted_phrases(text: str) -> list:
    """'...' phrases with the parenthesis that follows each, if any: [(phrase, hint-or-None)].

    An apostrophe inside a word (member's) does not close a phrase.
    """
    phrases, index = [], 0
    while index < len(text):
        if text[index] == "'" and (index == 0 or text[index - 1] in " (,"):
            end = index + 1
            while end < len(text):
                if text[end] == "'" and (end + 1 == len(text) or text[end + 1] in " ,;.)"):
                    break
                end += 1
            if end < len(text):
                phrase = text[index + 1:end]
                hint = None
                after = end + 1
                if text[after:after + 2] == " (":
                    depth, scan = 0, after + 2
                    while scan < len(text):
                        if text[scan] == "(":
                            depth += 1
                        elif text[scan] == ")":
                            if depth == 0:
                                break
                            depth -= 1
                        scan += 1
                    hint = text[after + 2:scan]
                    after = scan + 1
                phrases.append((phrase, hint))
                index = after
                continue
        index += 1
    return phrases


def parse_key_citations(review_sheet: str) -> dict:
    """request id -> the verbatim 'Where this is written down' line, plus parsed (doc, phrase) pairs."""
    out = {}
    pieces = re.split(r"\n### (REQ-T\d+):", review_sheet)
    for index in range(1, len(pieces), 2):
        request_id, body = pieces[index], pieces[index + 1]
        match = re.search(r"\*\*Where this is written down:\*\* (.*)", body)
        if not match:
            fail(f"no 'Where this is written down' line for {request_id}")
        line = match.group(1).strip()
        pairs = []
        for segment in split_top_level(line, ";"):
            segment = segment.rstrip(".")
            span_starts = [(m.start(), m.group(1)) for m in re.finditer(r"(Metric dictionary|Data quality register|Team notes|Schema comments)", segment)]
            for position, (start, doc_name) in enumerate(span_starts):
                end = span_starts[position + 1][0] if position + 1 < len(span_starts) else len(segment)
                span = segment[start:end]
                phrases = single_quoted_phrases(span)
                remainder = span[len(doc_name):].lstrip(", ")
                if phrases:
                    for phrase, hint in phrases:
                        pairs.append((doc_name.lower(), phrase.strip().rstrip("."), hint))
                elif remainder and doc_name.lower() != "schema comments":
                    pairs.append((doc_name.lower(), remainder.strip().rstrip("."), None))
                elif doc_name.lower() == "schema comments":
                    pairs.append((doc_name.lower(), "schema comments", None))
        out[request_id] = {"line": line, "pairs": pairs}
    return out


def resolve_citation(doc_name: str, phrase: str, hint: str | None, world: dict, facts: dict) -> tuple[list, str]:
    """-> (fact ids, how).  how: heading | heading+hint | heading(no hint match) | quote | alias | schema | unresolved

    A citation that names a whole section ('Net sales') credits every fact under that heading.  If the key
    adds a parenthesis saying which part ('ATV', 'new member', 'dispatch date'), only the facts that parenthesis
    points at are credited; when it points at none of them the whole section is credited and the case is reported.
    """
    if doc_name == "schema comments":
        return [], "schema"
    lowered = phrase.lower()
    alias = CITATION_ALIASES.get((doc_name, lowered))
    doc = world[doc_name]
    if alias:
        return alias, "alias"
    if lowered in doc["headings"]:
        section_facts = sorted(set(doc["headings"][lowered]))
        if not hint:
            return section_facts, "heading"
        chosen: list = []
        parts = [hint.lower().strip()] if hint.lower().strip() in HINT_ALIASES else re.split(r"\s*;\s*|\s*,\s*|\s+and\s+", hint.lower())
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if part in HINT_ALIASES:
                chosen.extend(HINT_ALIASES[part])
                continue
            for fact_id in section_facts:
                if part in facts[fact_id]["statement"].lower():
                    chosen.append(fact_id)
        if chosen:
            return sorted(set(chosen)), "heading+hint"
        return section_facts, "heading(no hint match)"
    fragments = [f.strip() for f in re.split(r"\s*\.\.\.\s*", lowered) if f.strip()]
    matched: list = []
    for fact_ids, block_text in doc["blocks"]:
        if all(fragment in block_text for fragment in fragments):
            matched.extend(fact_ids)
    if matched:
        return sorted(set(matched)), "quote"
    return [], "unresolved"


def build_module3(case: Case) -> dict:
    log("module 3: parsing the prompt document, the library and the key's citations ...")
    doc_text = load_text(PATH_PROMPT_DOC)
    parsed = parse_prompt_doc(doc_text)
    lib_map = library_fact_map()
    inventory = library_inventory()
    descriptions = skill_descriptions()

    # --- the document's facts, in document order
    doc_fact_ids: list = []
    for block in parsed["blocks"]:
        for fact_id in block["fact_ids"]:
            if fact_id not in doc_fact_ids:
                doc_fact_ids.append(fact_id)
    if len(doc_fact_ids) != 62:
        fail(f"expected 62 fact ids in prompt_doc.md, found {len(doc_fact_ids)}")
    missing = [f for f in doc_fact_ids if f not in lib_map]
    if missing:
        fail(f"facts in the document but in no library file: {missing}")
    if set(lib_map) != set(doc_fact_ids):
        fail("the library and the document do not carry the same fact ids")

    # --- how each request is counted against each rule: (1) the key's own pointers
    world = parse_world_docs()
    citations = parse_key_citations(load_text(PATH_REVIEW_SHEET))
    by_key_docs: dict = defaultdict(set)
    unresolved: list = []
    schema_only: list = []
    no_hint_match: list = []
    for request_id, info in citations.items():
        resolved_any = False
        for doc_name, phrase, hint in info["pairs"]:
            fact_ids, how = resolve_citation(doc_name, phrase, hint, world, case.facts)
            if how == "schema":
                continue
            if how == "unresolved":
                unresolved.append((request_id, doc_name, phrase))
                continue
            if how == "heading(no hint match)":
                no_hint_match.append((request_id, doc_name, phrase, hint))
            resolved_any = True
            for fact_id in fact_ids:
                by_key_docs[fact_id].add(request_id)
        if not resolved_any:
            schema_only.append(request_id)
    if unresolved:
        fail(f"{len(unresolved)} key citations did not resolve to a fact: {unresolved[:6]}")
    if no_hint_match:
        log(f"  note: {len(no_hint_match)} citations carry a parenthesis that matched no fact; their whole section is credited: {no_hint_match}")

    # --- (2) the runs' own words
    by_runs: dict = defaultdict(lambda: defaultdict(int))     # fact -> request -> n correct D/L/L- runs naming it
    for request_id in case.key:
        for setup_id in ("sonnet_D", "sonnet_L", "sonnet_Lm"):
            for run, mark in case.runs[request_id][setup_id]:
                if mark["outcome"] != "correct":
                    continue
                lowered_lines = [l.lower() for l in ((run.get("answer") or {}).get("definitions_applied") or [])]
                for fact_id in doc_fact_ids:
                    phrases = [p.lower() for p in case.facts[fact_id]["must_contain"]]
                    if any(all(p in line for p in phrases) for line in lowered_lines):
                        by_runs[fact_id][request_id] += 1
    runs_naming = {
        fact_id: sorted(r for r, n in by_runs[fact_id].items() if n >= RUNS_NAMING_MIN_RUNS) for fact_id in doc_fact_ids
    }

    # --- per fact
    facts_out = {}
    for fact_id in doc_fact_ids:
        files = lib_map[fact_id]
        fact = case.facts[fact_id]
        docs_requests = sorted(by_key_docs.get(fact_id, set()))
        either = sorted(set(docs_requests) | set(runs_naming[fact_id]))
        facts_out[fact_id] = {
            "id": fact_id,
            "kind": fact["kind"],
            "trap_class": fact["trap_class"],
            "world_doc": fact["docs"][0],
            "home_skill": home_skill(fact, files, descriptions),
            "skills": sorted({f.split("/")[0] for f in files}),
            "n_library_files": len(files),
            "n_key_docs": len(docs_requests),
            "n_named_in_runs": len(runs_naming[fact_id]),
            "n_either": len(either),
            "_key_docs": docs_requests,
            "_named_in_runs": runs_naming[fact_id],
            "_library_files": files,
        }

    # --- sections and blocks
    section_titles = {s["no"]: s["title"] for s in parsed["sections"]}
    word_count_all = len(re.sub(r"<!--.*?-->", "", doc_text).split())
    blocks_out = []
    sections_out = []
    for section in parsed["sections"]:
        section_blocks = [b for b in parsed["blocks"] if b["section_no"] == section["no"]]
        kind = "rules"
        if section["no"] == 11:
            kind = "worked_examples"
        elif section["no"] == 12:
            kind = "request_history_digest"
        elif section["no"] == 0:
            kind = "opening"
        section_words = sum(len(re.sub(r"<!--.*?-->", "", b["text"]).split()) for b in section_blocks)
        sections_out.append({"no": section["no"], "title": section["title"], "kind": kind, "n_blocks": len(section_blocks),
                             "n_rule_blocks": sum(1 for b in section_blocks if b["fact_ids"]), "words": section_words})
    for index, block in enumerate(parsed["blocks"], start=1):
        block["block_id"] = f"B{index:02d}"
        if block["section_no"] in (11, 12):
            continue
        ids = block["fact_ids"]
        union_docs = sorted(set().union(*[set(facts_out[i]["_key_docs"]) for i in ids])) if ids else []
        union_runs = sorted(set().union(*[set(facts_out[i]["_named_in_runs"]) for i in ids])) if ids else []
        union_either = sorted(set(union_docs) | set(union_runs))
        files = sorted(set().union(*[set(facts_out[i]["_library_files"]) for i in ids])) if ids else []
        homes = sorted({facts_out[i]["home_skill"] for i in ids if facts_out[i]["home_skill"]})
        text = block["text"]
        blocks_out.append({
            "block": block["block_id"],
            "section_no": block["section_no"],
            "section_title": section_titles[block["section_no"]],
            "first_line": block["first_line"],
            "fact_ids": ids,
            "sources": block["sources"],
            "text": text,
            "words": len(text.split()),
            "home_skills": homes,
            "library_files": files,
            "requests": union_either,
            "n_requests": len(union_either),
            "n_key_docs": len(union_docs),
            "n_named_in_runs": len(union_runs),
        })
    for fact in facts_out.values():
        del fact["_key_docs"], fact["_named_in_runs"], fact["_library_files"]

    # --- library side: skills and their tagged facts
    skills_out = []
    for skill in inventory["skills"]:
        skill_files = sorted(p.relative_to(PATH_LIBRARY).as_posix() for p in (PATH_LIBRARY / skill).rglob("*") if p.is_file())
        skill_facts = sorted({f for f, files in lib_map.items() if any(x.startswith(skill + "/") for x in files)})
        description = ""
        match = re.search(r"^description:\s*(.*)$", load_text(PATH_LIBRARY / skill / "SKILL.md"), re.M)
        if match:
            description = match.group(1).strip()
        skills_out.append({"skill": skill, "description": description, "files": skill_files, "n_files": len(skill_files),
                           "fact_ids": skill_facts, "home_for": sorted(f for f, v in facts_out.items() if v["home_skill"] == skill)})

    return {
        "how_counted": (
            "A request depends on a rule in two ways, counted separately and then joined. (1) The key's own pointers: the key's review sheet lists, for each of the "
            "60 requests, the wiki sections the answer leans on ('Where this is written down'). Each pointer is matched to the fact ids under that section heading "
            "(narrowed to the part named in the key's parenthesis, for example 'ATV' or 'dispatch date', when there is one) or to the fact whose wording it quotes. "
            "A rule therefore inherits the count of the section it sits in: this is section-level, not line-level, so a section holding several rules gives each the "
            "same count when the key does not say which part. Pointers to 'Schema comments' name no rule and are not counted. (2) Named in runs: the request has at least "
            f"{RUNS_NAMING_MIN_RUNS} of its 15 correct Sonnet D, L and L-minus runs whose own 'definitions_applied' list contains all of the fact's check phrases "
            "(facts.yaml must_contain). This is a floor, because runs paraphrase. 'requests' on a rule is the union of the two."),
        "unresolved_citations": [list(u) for u in unresolved],
        "citations_whose_parenthesis_matched_no_fact": [list(x) for x in no_hint_match],
        "requests_citing_schema_comments_only": schema_only,
        "document": {
            "path": "arms/prompt_doc.md",
            "words_without_markers": word_count_all,
            "n_fact_ids": len(doc_fact_ids),
            "n_rule_blocks": sum(1 for b in blocks_out if b["fact_ids"]),
            "sections": sections_out,
        },
        "library": {
            "path": "arms/library/",
            "n_skills": inventory["n_skills"],
            "n_templates": inventory["n_templates"],
            "n_reference_files": inventory["n_reference_files"],
            "n_scripts": inventory["n_scripts"],
            "n_files": inventory["n_files"],
            "n_fact_ids": len(lib_map),
            "skills": skills_out,
        },
        "blocks": blocks_out,
        "facts": facts_out,
        "_doc_lines": parsed["lines"],
        "_blocks_raw": parsed["blocks"],
    }


def doc_line(module3: dict, anchor: str) -> dict:
    """The exact line of prompt_doc.md containing `anchor`, with the fact ids of the block it sits in."""
    lines = module3["_doc_lines"]
    for index, line in enumerate(lines):
        if anchor in line:
            line_no = index + 1
            fact_ids: list = []
            block_id = None
            for block in module3["_blocks_raw"]:
                if block["first_line"] <= line_no <= block["last_line"]:
                    fact_ids = list(dict.fromkeys(block["fact_ids"]))
                    block_id = block.get("block_id")
                    break
            section_no, section_title = 0, "Opening"
            for scan in range(index, -1, -1):
                heading = HEADING_RE.match(lines[scan])
                if heading:
                    section_no, section_title = int(heading.group(1)), heading.group(2)
                    break
            return {"line": line.strip(), "doc_line_no": line_no, "fact_ids": fact_ids, "block": block_id,
                    "section": f"{section_no}. {section_title}" if section_no else section_title}
    fail(f"anchor not found in prompt_doc.md: {anchor!r}")


# ============================================================================================
# MODULES 1 AND 2  --  CANDIDATE SPECS
# ============================================================================================
# Each spec is hand-written from reading the five Sonnet S runs of the request and the key.  The counts
# in the output are NOT typed here: every `n` is computed by running the regexes below over the runs'
# own assumptions / caveats / definitions (text) or SQL.  `inferred` marks a run whose text is silent but
# whose returned figures are identical to a run that states it.

CANDIDATE_SPECS = [
    {
        "request_id": "REQ-T15",
        "short_title": "A cancelled order is not a web order",
        "rule_anchors": ["Web orders are counted on the order date in Helsinki time.", "Cancelled orders are not web sales and are not counted as web orders."],
        "one_rule": "Cancelled web orders are not counted as web orders.",
        "headline": {"row": None, "col_re": r"order"},
        "headline_label": "web orders on Cyber Monday 2025",
        "web_dating_applies": False,
        "main": {"id": "counted_cancelled", "text": "Counted the cancelled orders as 'placed'", "text_re": r"cancel"},
        "also": [
            {"id": "helsinki_day", "right": True, "text": "Took the day as a Helsinki calendar day (the company's way)", "text_re": r"finnish|helsinki|utc\+2|local time"},
        ],
        "gap_hint_re": r"\b(\d+)\s+(?:later\s+)?cancel|cancel\w*\s+\w*\s*(\d+)\b",
        "d_quote_re": r"cancel",
        "readings": [
            {"id": "placed", "value_from": 's_typical', "label": "Every order placed, whatever happened to it afterwards", "who": "S", "plain": "A customer pressed 'order' on the day, so it counts, even if it was cancelled later."},
            {"id": "company", "value_from": 'correct', "label": "Only orders that were not cancelled", "who": "company rule", "plain": "Cancelled orders are not web orders."},
        ],
        "twin": {"request_id": "REQ-T39", "note": "The same question asked as 'web shop orders'.", "quote_re": r"cancel"},
        "family": "web orders",
    },
    {
        "request_id": "REQ-T59",
        "short_title": "Same rule, with the day counted in UTC on request",
        "rule_anchors": ["Cancelled orders are not web sales and are not counted as web orders.", "When a request explicitly asks for something that differs from a company default"],
        "one_rule": "Cancelled web orders are not counted as web orders (the UTC day the requester asked for was followed by every run).",
        "headline": {"row": None, "col_re": r"order"},
        "headline_label": "web orders on Black Friday 2025, by UTC day",
        "web_dating_applies": False,
        "main": {"id": "counted_cancelled", "text": "Counted the cancelled orders as 'placed'", "text_re": r"cancel"},
        "also": [],
        "gap_hint_re": r"\b(\d+)\s+(?:of the \d+\s+)?(?:are\s+|later\s+)?cancel|\b(\d+) orders later cancelled",
        "d_quote_re": r"cancel|utc",
        "readings": [
            {"id": "placed", "value_from": 's_typical', "label": "Every order placed, whatever happened to it afterwards", "who": "S", "plain": "Counts the order even if it was cancelled later."},
            {"id": "company", "value_from": 'correct', "label": "Only orders that were not cancelled", "who": "company rule", "plain": "Cancelled orders are not web orders."},
        ],
        "family": "web orders",
    },
    {
        "request_id": "REQ-T07",
        "short_title": "South as it is now, or as it was",
        "rule_anchors": ["Report history as-is unless the requester asks for as-was", "On 28 April 2025 the four regions"],
        "one_rule": "History is reported as-is, on today's regions, unless the requester asks for as-was.",
        "headline": {"row": None, "col_re": r"margin"},
        "headline_label": "gross margin of the top product (EUR)",
        "web_dating_applies": False,
        "main": {"id": "as_was_region", "text": "Read 'South' as the region as it stood at the time (the old South, without the five stores that later joined the Capital Region, and with Kouvola in the East)",
                 "text_re": r"as it stood|as it was during|in force during|were in south during|as recorded at the time|stood during"},
        "also": [
            {"id": "staff_out", "right": False, "text": "Also left staff purchases out of the margin", "text_re": r"excluded staff purchases|left them out"},
        ],
        "naive_variant": "as_was_region",
        "d_quote_re": r"as-is|as is|current hierarchy|current region",
        "readings": [
            {"id": "as_was", "value_from": 's_typical', "label": "South as it was in Q4 of FY24/25", "who": "S", "plain": "Stores that were in the South at the time."},
            {"id": "as_is", "value_from": 'correct', "label": "South as it is today", "who": "company rule", "plain": "Today's regions, applied to all history."},
        ],
        "family": "history",
    },
    {
        "request_id": "REQ-T25",
        "short_title": "'Last year' is the fiscal year, not the calendar year",
        "rule_anchors": ["\"Last year\" is not defined in the metric dictionary.", "The fiscal year starts on the Monday nearest 1 May"],
        "one_rule": "'Last year' is read as the last fiscal year (FY2025/26), not calendar 2025.",
        "headline": {"row": 101, "row_col_re": r"store", "col_re": r"new_members|members"},
        "headline_label": "new members signed up at store 101 last year",
        "web_dating_applies": False,
        "main": {"id": "calendar_year", "text": "Read 'last year' as calendar 2025", "text_re": r"calendar year 2025"},
        "also": [
            {"id": "named_alternative", "right": True, "text": "Named the fiscal-year reading as a possible alternative in its own notes", "text_re": r"fiscal.year reading|fiscal year \(fy|if a fiscal|if marketing meant|figures will differ|would give different|would differ|count differ"},
        ],
        "d_quote_re": r"fy2025/26|fiscal year|last year",
        "readings": [
            {"id": "calendar", "value_from": 's_typical', "label": "Calendar year 2025 (1 January to 31 December)", "who": "S", "plain": "Last year as an ordinary calendar year."},
            {"id": "fiscal", "value_from": 'correct', "label": "Fiscal year FY2025/26 (28 April 2025 to 3 May 2026)", "who": "company rule", "plain": "The company's year, which is what past requests took 'last year' to mean."},
        ],
        "family": "calendar",
    },
    {
        "request_id": "REQ-T56",
        "short_title": "A web sale is dated when it is dispatched, not when it is ordered",
        "rule_anchors": ["Web sales are recognised on the dispatch date in Helsinki time."],
        "one_rule": "Web sales are dated by the dispatch date (Helsinki time); sale_date on a web line is the order date.",
        "headline": {"row": "2025-12-21", "row_col_re": r"date", "col_re": r"net|sales"},
        "headline_label": "web net sales on 21 December 2025 (EUR)",
        "web_dating_applies": True,
        "main": {"id": "order_date", "text": "Dated web sales by the day the order was placed", "sql_lacks": "dispatch"},
        "also": [
            {"id": "refunds_to_web", "right": False, "text": "Also charged web items returned in a physical store against the web shop", "text_re": r"wherever|including the few handed back|even when the return was made in a store|handed in"},
        ],
        "naive_variant": "order_date_not_dispatch",
        "d_quote_re": r"dispatch",
        "readings": [
            {"id": "order_date", "value_from": ('naive', 'order_date_not_dispatch'), "label": "The day the order was placed", "who": "S", "plain": "The date on the sales line."},
            {"id": "dispatch_date", "value_from": 'correct', "label": "The day the order was dispatched (Helsinki time)", "who": "company rule", "plain": "When the revenue is recognised."},
            {"id": "utc_dispatch", "value_from": ('naive', 'utc_dispatch_day'), "label": "The UTC date of the dispatch time", "who": "key variant (no run chose it)", "plain": "A carrier scan after 21:00 UTC lands on the next Finnish day."},
        ],
        "family": "web dating",
    },
    {
        "request_id": "REQ-T31",
        "short_title": "Active member: 52 weeks, not 'the last 12 months'",
        "rule_anchors": ["An active member has made at least one purchase in the trailing 52 fiscal weeks"],
        "one_rule": "An active member has bought in the trailing 52 fiscal weeks (364 days), counted to the as-of week.",
        "headline": {"row": "Silver", "row_col_re": r"tier", "col_re": r"active|members"},
        "headline_label": "active Silver members at the end of period 8 last year",
        "web_dating_applies": False,
        "main": {"id": "twelve_months", "text": "Counted purchases in the last 12 months (365 days) because no definition of 'active' was available to it", "text_re": r"12 months"},
        "also": [
            {"id": "staff_out", "right": False, "text": "Also did not count staff purchases as activity", "text_re": r"staff purchases made on a loyalty card do not count|(?<!if )staff purchases (?:are )?(?:excluded|left out)"},
        ],
        "d_quote_re": r"52",
        "readings": [
            {"id": "twelve_months", "value_from": 's_typical', "label": "At least one purchase in the 12 months to the as-of date", "who": "S", "plain": "The usual loyalty-programme reading."},
            {"id": "fiscal_52", "value_from": 'correct', "label": "At least one purchase in the trailing 52 fiscal weeks", "who": "company rule", "plain": "364 days to the end of the as-of week."},
            {"id": "period_only", "value_from": ('naive', 'bought_in_the_period_only'), "label": "Bought during period 8 itself", "who": "key variant (no run chose it)", "plain": "Counts only members who bought in the period."},
        ],
        "family": "definitions",
    },
    {
        "request_id": "REQ-T05",
        "short_title": "Weekly company sales: web revenue lands in the dispatch week",
        "rule_anchors": ["Web sales are recognised on the dispatch date in Helsinki time."],
        "one_rule": "Web sales are dated by the dispatch date, so web revenue can fall in a different week from the order.",
        "headline": {"row": 8, "row_col_re": r"week", "col_re": r"growth"},
        "headline_label": "growth in fiscal week 8 of period 2, this year against last (%)",
        "web_dating_applies": True,
        "main": {"id": "order_date", "text": "Dated web sales by the day the order was placed", "sql_lacks": "dispatch"},
        "also": [
            {"id": "fiscal_week_alignment", "right": True, "text": "Lined the weeks up by fiscal week number (the company's way)", "text_re": r"fiscal week number|same fiscal week|by fiscal week|fiscal-week alignment"},
        ],
        "d_quote_re": r"dispatch",
        "twin": {"request_id": "REQ-T33", "note": "The same question in different words."},
        "readings": [
            {"id": "order_date", "value_from": 's_typical', "label": "Web sales on the order date", "who": "S", "plain": "The date on the sales line."},
            {"id": "dispatch_date", "value_from": 'correct', "label": "Web sales on the dispatch date", "who": "company rule", "plain": "When the revenue is recognised."},
            {"id": "date_aligned", "value_from": ('naive', 'date_aligned_last_year'), "label": "Last year's weeks taken from the same calendar dates", "who": "key variant (no run chose it)", "plain": "Shifts the comparison by almost a week."},
        ],
        "family": "web dating",
    },
    {
        "request_id": "REQ-T21",
        "short_title": "Web sales including VAT, dated by dispatch",
        "rule_anchors": ["Web sales are recognised on the dispatch date in Helsinki time.", "Net sales are always excluding VAT."],
        "one_rule": "Web sales are dated by the dispatch date (the VAT part was handled correctly by every S run).",
        "headline": {"row": 4, "row_col_re": r"period", "col_re": r"vat|gross|web|sales"},
        "headline_label": "web sales including VAT, period 4 of FY24/25 (EUR)",
        "web_dating_applies": True,
        "main": {"id": "order_date", "text": "Dated web sales by the day the order was placed", "sql_lacks": "dispatch"},
        "also": [
            {"id": "vat_line_by_line", "right": True, "text": "Took VAT line by line: summed the gross amount of each sales line in its final query", "sql_has": "sum(f.gross_amount)"},
            {"id": "no_flat_multiplier", "right": True, "text": "Applied no flat VAT multiplier (no 1.24, 1.255 or 25.5% factor in its final query)", "sql_lacks_all": ["1.255", "1.24", "1.2550", "25.5", "* 0.2", "*0.2", "1.25"]},
            {"id": "vat_stated", "right": True, "text": "Said in its notes that VAT is each line's own gross amount at the rate in force", "text_re": r"gross_amount as recorded on each line|own vat rate|gross_amount on each line"},
        ],
        "d_quote_re": r"dispatch",
        "readings": [
            {"id": "order_date", "value_from": 's_typical', "label": "Web sales on the order date", "who": "S", "plain": "The date on the sales line."},
            {"id": "dispatch_date", "value_from": 'correct', "label": "Web sales on the dispatch date", "who": "company rule", "plain": "When the revenue is recognised."},
            {"id": "flat_vat", "value_from": ('naive', 'flat_25_5'), "label": "Net sales times one flat VAT rate", "who": "key variant (no run chose it)", "plain": "Wrong in the months the rate changed."},
        ],
        "family": "web dating",
    },
    {
        "request_id": "REQ-T22",
        "short_title": "Campaign spend is counted before returns",
        "rule_anchors": ["Campaign uplift is the mean net sales per targeted member"],
        "one_rule": "For the campaign figures, net sales are before returns (and web sales are dated by dispatch).",
        "headline": {"row": None, "col_re": r"net|spend|sales", "avoid_re": r"avg|member"},
        "headline_label": "spend by the contacted members, 4 to 24 May 2026 (EUR)",
        "web_dating_applies": True,
        "main": {"id": "net_of_refunds", "text": "Deducted refunds from the members' spend", "text_re": r"net of (?:refunds|returns)|after refunds|net of vat and net of refunds"},
        "also": [
            {"id": "order_date", "right": False, "marker_accepts": True, "text": "Dated web sales by the day the order was placed (the key accepts this reading for this request)", "sql_lacks": "dispatch"},
        ],
        "d_quote_re": r"before returns|dispatch",
        "alt_value_hint": True,
        "readings": [
            {"id": "after_refunds", "value_from": 's_typical', "label": "Spend after refunds", "who": "S", "plain": "What the members kept."},
            {"id": "before_returns", "value_from": 'correct', "label": "Net sales before returns (web by dispatch date)", "who": "company rule", "plain": "How the company measures campaign uplift."},
            {"id": "before_returns_order_date", "value_from": ('alt', 0), "label": "Net sales before returns (web by order date)", "who": "key alternative (accepted)", "plain": "Also accepted by the key."},
        ],
        "family": "web dating",
    },
    {
        "request_id": "REQ-T44",
        "short_title": "Garden and Electrical: categories as they are now",
        "rule_anchors": ["Report history as-is unless the requester asks for as-was", "From 27 October 2025 (FY2025/26 period 7) the outdoor lighting subcategory"],
        "one_rule": "History is reported as-is, on today's categories, unless the requester asks for as-was.",
        "headline": {"row": "Garden", "row_col_re": r"category", "col_re": r"net"},
        "headline_label": "Garden net sales, period 6 last year (EUR)",
        "web_dating_applies": True,
        "main": {"id": "as_was_category", "text": "Kept the categories as they stood at the time (outdoor lighting still in Garden)", "text_re": r"as they stood|stood at the time|classified at the time"},
        "also": [
            {"id": "order_date", "right": False, "text": "Dated web sales by the day the order was placed", "sql_lacks": "dispatch"},
            {"id": "as_is_categories", "right": True, "text": "Used today's categories (the company's way) and was still wrong, on the web dating", "text_re": r"restated the history to the current category"},
        ],
        "naive_variant": "as_was_category",
        "d_quote_re": r"as-is|as is|current categor|restate",
        "readings": [
            {"id": "as_was", "value_from": 's_typical', "label": "Categories as they were at the time", "who": "S", "plain": "Outdoor lighting still counted as Garden."},
            {"id": "as_is", "value_from": 'correct', "label": "Categories as they are today", "who": "company rule", "plain": "Outdoor lighting counted in Electrical for all history."},
        ],
        "family": "history",
    },
    {
        "request_id": "REQ-T08",
        "short_title": "Like-for-like by region: which stores are in the base",
        "rule_anchors": ["LFL growth compares net sales in the LFL stores", "LFL edge cases."],
        "one_rule": "A store is in the LFL base only if it had been open at least 52 weeks (364 days) before the first day of the period; the two 2024 openings enter on set dates.",
        "headline": {"row": "West", "row_col_re": r"region", "col_re": r"growth|lfl"},
        "headline_label": "West region like-for-like growth, Q3 last year (%)",
        "web_dating_applies": False,
        "main": {"id": "dropped_136", "text": "Left Tampere Lamminpää (store 136) out of the like-for-like base as 'still ramping up'",
                 "text_re": r"lamminp\S* \(?(?:tampere, )?(?:store )?136[^)]*\)? (?:is treated as non-comparable|was still ramping|opened[^.]*non-like)|excluded tampere lamminp|treated as non-comparable|new stores excluded", "infer_from_headline_value": 2.04},
        "also": [
            {"id": "dropped_raahe", "right": False, "text": "Left Raahe (store 139) out because of one trading day with no sales (a rule of its own)", "text_re": r"excluded as not comparable: raahe"},
            {"id": "no_written_definition", "right": False, "info_only": True, "text": "Said it could find no written like-for-like definition", "text_re": r"no written|could not find a written|no company like-for-like"},
            {"id": "mentions_tmp_lists", "right": False, "info_only": True, "text": "Mentioned the leftover tmp_lfl_store_list tables or 'the company's LFL store lists' in its notes", "text_re": r"tmp_lfl|company's lfl store lists"},
            {"id": "final_sql_reads_tmp_lists", "right": False, "info_only": True, "text": "Read the tmp_lfl_store_list tables in its final query", "sql_has": "tmp_lfl"},
        ],
        "d_quote_re": r"52 weeks|364|lfl|opening rule",
        "readings": [
            {"id": "s_own_cut", "value_from": 's_typical', "label": "Its own 12-month store cut (drops store 136)", "who": "S", "plain": "Stores must have traded for a full year; store 136 was judged still ramping up."},
            {"id": "company", "value_from": 'correct', "label": "Open at least 364 days before the period starts", "who": "company rule", "plain": "Store 136 is in; Lohja (137) is out."},
            {"id": "per_period", "value_from": ('alt', 0), "label": "364-day test at the start of each fiscal period (Lohja counts from P8)", "who": "key alternative (accepted)", "plain": "Accepted by the key."},
        ],
        "family": "definitions",
    },
    {
        "request_id": "REQ-T51",
        "short_title": "Campaign uplift: window plus seven days, before returns",
        "rule_anchors": ["Campaign uplift is the mean net sales per targeted member"],
        "one_rule": "Uplift runs over the campaign window plus seven days, on net sales before returns.",
        "headline": {"row": None, "col_re": r"spend.*targeted|mean_net_targeted"},
        "headline_label": "average spend per targeted member (EUR)",
        "web_dating_applies": True,
        "main": {"id": "window_only", "text": "Counted spend only inside the campaign week, with no seven-day tail", "text_re": r"campaign week only|window only|no post-campaign|tail|24-30 nov|only inside the campaign window", "infer_from_identical_result": True},
        "also": [
            {"id": "net_of_refunds", "right": False, "text": "Deducted refunds", "text_re": r"net of (?:refunds|returns)|after returns|refunds? (?:are|were) (?:netted|attributed)|refunds are netted|net of vat and net of returns|sales net of refunds"},
            {"id": "order_date", "right": False, "marker_accepts": True, "text": "Dated web sales by the day the order was placed (the key accepts this reading for this request)", "sql_lacks": "dispatch"},
            {"id": "staff_out", "right": False, "text": "Left staff purchases out", "text_re": r"staff purchases are (?:not customer spend and are )?excluded|excluded because they are not driven"},
        ],
        "d_quote_re": r"seven|7 days|plus 7|tail|window",
        "readings": [
            {"id": "window_only", "value_from": 's_typical', "label": "Spend during the campaign week only", "who": "S", "plain": "Nothing after 30 November."},
            {"id": "window_plus_seven", "value_from": 'correct', "label": "The campaign window plus seven days", "who": "company rule", "plain": "How the company measures uplift."},
            {"id": "vs_everyone_not_mailed", "label": "Compared with everyone not mailed, not the holdout group", "who": "key variant (no run chose it)", "plain": "Brings in members who never consented."},
        ],
        "family": "web dating",
    },
]

# Module 2: requests shown side by side (Sonnet S, D and L, five runs each).  `focus` picks the line
# of each run's own assumptions to show (first match; else the first line).
MODULE2_SPECS = [
    {"request_id": "REQ-T24", "kind": "clean", "headline": {"row": None, "col_re": r"member"}, "label": "new members who signed up on 25 September 2026", "focus_re": r"join|sign"},
    {"request_id": "REQ-T30", "kind": "clean", "headline": {"row": None, "col_re": r"gold|member|count"}, "label": "Gold-tier members now", "focus_re": r"moment|current|tier"},
    {"request_id": "REQ-T15", "kind": "company rule", "headline": {"row": None, "col_re": r"order"}, "label": "web orders on Cyber Monday 2025", "focus_re": r"cancel"},
    {"request_id": "REQ-T59", "kind": "company rule", "headline": {"row": None, "col_re": r"order"}, "label": "web orders on Black Friday 2025 (UTC day)", "focus_re": r"cancel"},
    {"request_id": "REQ-T31", "kind": "company rule", "headline": {"row": "Silver", "row_col_re": r"tier", "col_re": r"active|members"}, "label": "active Silver members, end of period 8 last year", "focus_re": r"52 (?:fiscal )?weeks|trailing|12 months|active member"},
    {"request_id": "REQ-T08", "kind": "company rule", "headline": {"row": "West", "row_col_re": r"region", "col_re": r"growth|lfl"}, "label": "West like-for-like growth, Q3 last year (%)", "focus_re": r"opening rule|52 weeks|364|lamminp|136|ramping|new stores"},
    {"request_id": "REQ-T22", "kind": "company rule", "headline": {"row": None, "col_re": r"net|spend|sales", "avoid_re": r"avg|member"}, "label": "spend by the contacted members, 4 to 24 May 2026 (EUR)", "focus_re": r"refund|before returns|returns|dispatch"},
    {"request_id": "REQ-T05", "kind": "fiscal", "headline": {"row": 8, "row_col_re": r"week", "col_re": r"growth"}, "label": "growth in fiscal week 8 of period 2 (%)", "focus_re": r"dispatch|order date|sale.date"},
    {"request_id": "REQ-T25", "kind": "fiscal", "headline": {"row": 101, "row_col_re": r"store", "col_re": r"new_members|members"}, "label": "new members at store 101 last year", "focus_re": r"last year|calendar year|fiscal year"},
    {"request_id": "REQ-T54", "kind": "fiscal", "headline": {"row": None, "col_re": r"net_sales"}, "label": "the whole company's net sales last month (EUR)", "focus_re": r"last month|last period|calendar month|fiscal period"},
    {"request_id": "REQ-T21", "kind": "company rule", "headline": {"row": 4, "row_col_re": r"period", "col_re": r"vat|gross|web|sales"}, "label": "web sales including VAT, period 4 of FY24/25 (EUR)", "focus_re": r"dispatch|sale.date|order date"},
]
MODULE2_SETUP_IDS = ["sonnet_S", "sonnet_D", "sonnet_L"]


def hits_in_run(run: dict, item: dict) -> tuple[bool, str | None, str | None]:
    """Does this run show `item`?  -> (hit, how, verbatim line or None)."""
    if item.get("text_re"):
        pattern = re.compile(item["text_re"], re.I)
        for line in run_lines(run):
            if pattern.search(line):
                return True, "text", line
    if item.get("sql_lacks"):
        sql = run_sql(run)
        if sql and item["sql_lacks"] not in sql.lower():
            return True, "sql", None
    if item.get("sql_has"):
        if item["sql_has"] in run_sql(run).lower():
            return True, "sql", None
    if item.get("sql_lacks_all"):
        sql = run_sql(run).lower()
        if sql and not any(s in sql for s in item["sql_lacks_all"]):
            return True, "sql", None
    return False, None, None


def evaluate_item(runs_s: list, item: dict, headline_spec: dict) -> dict:
    """Count how many of the five S runs show an item; fill gaps by identical returned figures where asked."""
    per_run = []
    for run, _mark in runs_s:
        hit, how, line = hits_in_run(run, item)
        per_run.append({"repeat": run["repeat"], "run_id": run["run_id"], "hit": hit, "how": how, "line": line})
    if item.get("infer_from_headline_value") is not None:
        for entry, (run, _mark) in zip(per_run, runs_s):
            headline = extract_headline((run.get("answer") or {}).get("result"), headline_spec)
            if not entry["hit"] and headline and abs(float(headline["value"]) - item["infer_from_headline_value"]) < 1e-9:
                entry["hit"], entry["how"] = True, "inferred"
    if item.get("infer_from_identical_result"):
        values = [extract_headline((run.get("answer") or {}).get("result"), headline_spec) for run, _m in runs_s]
        stated = {round(v["value"], 6) for e, v in zip(per_run, values) if e["hit"] and v}
        for entry, value in zip(per_run, values):
            if not entry["hit"] and value and round(value["value"], 6) in stated:
                entry["hit"], entry["how"] = True, "inferred"
    n_explicit = sum(1 for e in per_run if e["hit"] and e["how"] in ("text", "sql"))
    n_inferred = sum(1 for e in per_run if e["hit"] and e["how"] == "inferred")
    runs_out = []
    for entry in per_run:
        if entry["hit"]:
            record = {"repeat": entry["repeat"], "run_id": entry["run_id"], "how": entry["how"]}
            if entry["line"]:
                record["quote"] = quote(entry["line"])
            runs_out.append(record)
    return {"id": item["id"], "text": item["text"], "right_per_company": bool(item.get("right")),
            "accepted_by_key": bool(item.get("marker_accepts")),
            "info_only": bool(item.get("info_only")),
            "n": n_explicit + n_inferred, "of": len(runs_s), "n_stated": n_explicit, "n_inferred": n_inferred, "runs": runs_out}


def value_signature(headline: dict | None):
    return None if headline is None else round(float(headline["value"]), 4)


def number_patterns(value) -> list:
    """Regexes that find `value` written out in a sentence (with or without thousands commas), not as part of a longer number."""
    if isinstance(value, float) and value == int(value):
        value = int(value)
    forms = set()
    if isinstance(value, int):
        forms.add(str(value))
        forms.add(f"{value:,}")
    else:
        forms.add(f"{value:.2f}")
        forms.add(f"{value:,.2f}")
        forms.add(repr(value))
    return [re.compile(r"(?<![\d.,])" + re.escape(form) + r"(?![\d]|[.,]\d)") for form in forms]


def twin_summary(case: Case, twin: dict) -> dict:
    """How the twin wording fared: right-out-of-5 for S and D, and one S line on the rule."""
    request_id = twin["request_id"]
    out = {"request_id": request_id, "text": case.key[request_id]["request_text"], "note": twin["note"],
           "s_correct": case.n_correct(request_id, "sonnet_S"), "d_correct": case.n_correct(request_id, "sonnet_D"),
           "l_correct": case.n_correct(request_id, "sonnet_L")}
    if twin.get("quote_re"):
        pattern = re.compile(twin["quote_re"], re.I)
        for run, _m in case.runs[request_id]["sonnet_S"]:
            for line in run_lines(run):
                if pattern.search(line):
                    out["s_quote"] = {"run_id": run["run_id"], **quote(line)}
                    return out
    return out


def build_candidate(case: Case, module3: dict, spec: dict) -> dict:
    request_id = spec["request_id"]
    entry = case.key[request_id]
    runs_s = case.runs[request_id]["sonnet_S"]
    runs_d = case.runs[request_id]["sonnet_D"]
    runs_l = case.runs[request_id]["sonnet_L"]
    headline_spec = spec["headline"]
    # --- headline numbers per setup, S in detail
    reference_headline = extract_headline(entry["reference"]["result"], headline_spec)
    if reference_headline is None:
        fail(f"{request_id}: cannot extract the headline from the key's reference result")
    s_headlines = [extract_headline((run.get("answer") or {}).get("result"), headline_spec) for run, _m in runs_s]
    d_headlines = [extract_headline((run.get("answer") or {}).get("result"), headline_spec) for run, _m in runs_d]
    s_counter = Counter(value_signature(h) for h in s_headlines)
    s_typical_signature, s_typical_n = s_counter.most_common(1)[0]
    s_typical_value = next(h["value"] for h in s_headlines if h and value_signature(h) == s_typical_signature)
    # --- what S did
    main_eval = evaluate_item(runs_s, spec["main"], headline_spec)
    also_eval = [evaluate_item(runs_s, item, headline_spec) for item in spec.get("also", [])]
    # --- rules, with the exact document lines and where the library holds them
    rules = []
    for anchor in spec["rule_anchors"]:
        found = doc_line(module3, anchor)
        homes = sorted({module3["facts"][f]["home_skill"] for f in found["fact_ids"] if f in module3["facts"] and module3["facts"][f]["home_skill"]})
        rules.append({"fact_ids": found["fact_ids"], "section": found["section"], "doc_line_no": found["doc_line_no"],
                      "line": found["line"], "library_skills": homes})
    # --- readings: copy the spec's labels and attach the headline value where one exists
    readings = []
    for reading in spec["readings"]:
        reading = dict(reading)
        source = reading.pop("value_from", None)
        value = None
        if source == "s_typical":
            value = round_number(s_typical_value)
        elif source == "correct":
            value = round_number(reference_headline["value"])
        elif isinstance(source, tuple) and source[0] == "naive":
            naive_entry = next((n for n in entry["naive"] if n["label"] == source[1]), None)
            found = extract_headline(naive_entry["result"], headline_spec) if naive_entry else None
            value = round_number(found["value"]) if found else None
            reading["value_source"] = "key variant " + source[1]
        elif isinstance(source, tuple) and source[0] == "alt":
            found = extract_headline(entry["alternatives"][source[1]]["result"], headline_spec) if len(entry["alternatives"]) > source[1] else None
            value = round_number(found["value"]) if found else None
            reading["value_source"] = "key accepted alternative"
        if value is not None:
            reading["value"] = value
        readings.append(reading)
    # --- key variants and alternatives, verbatim from the key
    key_variants = [{"kind": "naive variant", "label": n["label"], "plain": n["plain"], "difference": n["difference"],
                     "chosen_by_s_runs": sum(1 for _r, m in runs_s if n["label"] in (m.get("naive_matches") or []))} for n in entry["naive"]]
    key_alternatives = [{"kind": "accepted alternative", "label": a["label"]} for a in entry["alternatives"]]
    key_alternatives += [{"kind": "accepted reading", "label": i.get("label")} for i in entry["interpretations"]]
    # --- does the gap reconcile to something S states itself?
    gap = None
    explained_by = None
    if isinstance(reference_headline["value"], (int, float)):
        gap = round_number(float(s_typical_value) - float(reference_headline["value"]), 4)
        if gap == int(gap):
            gap = int(gap)
        if spec.get("gap_hint_re"):
            pattern = re.compile(spec["gap_hint_re"], re.I)
            for run, _m in runs_s:
                for line in run_lines(run):
                    for match in pattern.finditer(line):
                        numbers = [int(g) for g in match.groups() if g and g.isdigit()]
                        if any(abs(abs(gap) - number) < 1e-9 for number in numbers):
                            explained_by = {"run_id": run["run_id"], "quote": quote(line)}
                            break
                    if explained_by:
                        break
                if explained_by:
                    break
    reproduces_variant = None
    if spec.get("naive_variant"):
        label = spec["naive_variant"]
        reproduces_variant = {"label": label, "n": sum(1 for _r, m in runs_s if label in (m.get("naive_matches") or [])), "of": 5}
    # --- the alternative figure S states itself (REQ-T22)
    states_accepted_alternative = None
    if spec.get("alt_value_hint") and entry["alternatives"]:
        alt_headline = extract_headline(entry["alternatives"][0]["result"], headline_spec)
        if alt_headline:
            needle_a = f"{alt_headline['value']:,.2f}"
            needle_b = f"{alt_headline['value']:.2f}"
            for run, _m in runs_s:
                for line in run_lines(run):
                    if needle_a in line or needle_b in line:
                        states_accepted_alternative = {"run_id": run["run_id"], "value": alt_headline["value"], "quote": quote(line)}
                        break
                if states_accepted_alternative:
                    break
    # --- does S's own text contain the correct figure?
    patterns = number_patterns(reference_headline["value"]) if isinstance(reference_headline["value"], (int, float)) and abs(reference_headline["value"]) >= 3 else []
    states_correct = []
    for run, _m in runs_s:
        for line in run_lines(run):
            if any(pat.search(line) for pat in patterns):
                states_correct.append({"run_id": run["run_id"], "quote": quote(line)})
                break
    twin = twin_summary(case, spec["twin"]) if spec.get("twin") else None
    # --- D's words
    d_quote = None
    if spec.get("d_quote_re"):
        pattern = re.compile(spec["d_quote_re"], re.I)
        for run, _m in runs_d:
            for line in run_lines(run):
                if pattern.search(line):
                    d_quote = {"run_id": run["run_id"], **quote(line)}
                    break
            if d_quote:
                break
    # --- the correct result (key reference), trimmed
    correct_result = trim_table(entry["reference"]["result"], keep_rows=8, always_keep=headline_spec.get("row"))
    s_typical_result = None
    for (run, _m), headline in zip(runs_s, s_headlines):
        if value_signature(headline) == s_typical_signature:
            s_typical_result = {"run_id": run["run_id"], **(trim_table((run.get("answer") or {}).get("result"), keep_rows=8, always_keep=headline_spec.get("row")) or {})}
            break
    # --- per-setup counts
    counts = {s["id"]: {"correct": case.n_correct(request_id, s["id"]), "of": 5} for s in SETUPS}
    s_wrong = 5 - counts["sonnet_S"]["correct"]
    s_runs_out = []
    for (run, mark), headline in zip(runs_s, s_headlines):
        s_runs_out.append({"repeat": run["repeat"], "run_id": run["run_id"], "outcome": mark["outcome"],
                           "headline": round_number(headline["value"]) if headline else None,
                           "naive_matches": mark.get("naive_matches") or []})
    d_runs_out = [{"repeat": run["repeat"], "run_id": run["run_id"], "outcome": mark["outcome"],
                   "headline": round_number(h["value"]) if h else None}
                  for (run, mark), h in zip(runs_d, d_headlines)]
    # --- cleanliness (computed, then used to rank)
    other_departures = sum(1 for e in also_eval if not e["right_per_company"] and not e["accepted_by_key"] and not e["info_only"] and e["n"] > 0)
    clean = {
        "s_wrong_of_5": s_wrong,
        "main_departure_runs": main_eval["n"],
        "main_departure_stated_runs": main_eval["n_stated"],
        "other_departures": other_departures,
        "gap_explained_by_s_own_words": bool(explained_by),
        "states_accepted_alternative": bool(states_accepted_alternative),
        "reproduces_key_variant_runs": reproduces_variant["n"] if reproduces_variant else 0,
        "s_runs_stating_the_correct_figure_in_text": len(states_correct),
    }
    return {
        "request_id": request_id,
        "text": entry["request_text"],
        "department": entry["department"],
        "requester": entry["requester"],
        "received": entry["received"],
        "trap_classes": entry["trap_classes"],
        "twin_group": entry["twin_group"],
        "short_title": spec["short_title"],
        "one_rule": spec["one_rule"],
        "family": spec["family"],
        "key_docs_line": None,   # filled by caller
        "rules": rules,
        "counts": counts,
        "headline": {
            "label": spec["headline_label"],
            "column": reference_headline["column"],
            "row": reference_headline["row"],
            "correct": round_number(reference_headline["value"]),
            "s_typical": round_number(s_typical_value),
            "s_typical_n": s_typical_n,
            "s_values": [h and round_number(h["value"]) for h in s_headlines],
            "d_values": [h and round_number(h["value"]) for h in d_headlines],
            "gap": gap,
            "gap_explained_by": explained_by,
        },
        "correct_result": correct_result,
        "s_typical_result": s_typical_result,
        "s_did": {"main": main_eval, "also": also_eval},
        "d_words": d_quote,
        "states_accepted_alternative": states_accepted_alternative,
        "s_text_states_correct_figure": states_correct,
        "s_runs": s_runs_out,
        "d_runs": d_runs_out,
        "readings": readings,
        "key_variants": key_variants,
        "key_alternatives": key_alternatives,
        "reproduces_key_variant": reproduces_variant,
        "twin": twin,
        "cleanliness": clean,
    }


def rank_candidates(candidates: list) -> list:
    """Cleaner single-rule stories first.  Order of keys: S wrong in 5 of 5; the figures reconcile to the
    run's own words or reproduce a key variant exactly; main departure in all five S runs; fewest other departures."""
    def sort_key(c):
        k = c["cleanliness"]
        return (
            -k["s_wrong_of_5"],
            0 if (k["gap_explained_by_s_own_words"] or k["states_accepted_alternative"] or k["reproduces_key_variant_runs"] > 0) else 1,
            -k["main_departure_runs"],
            k["other_departures"],
            -k["reproduces_key_variant_runs"],
            c["request_id"],
        )
    ordered = sorted(candidates, key=sort_key)
    for position, candidate in enumerate(ordered, start=1):
        candidate["rank"] = position
    return ordered


def web_dating_family(case: Case) -> dict:
    """Across all 60 requests: where S never used the dispatch date and D always did, while S was wrong >= 4 of 5."""
    members = []
    for request_id in sorted(case.key):
        s_runs = case.runs[request_id]["sonnet_S"]
        d_runs = case.runs[request_id]["sonnet_D"]
        s_wrong = 5 - case.n_correct(request_id, "sonnet_S")
        s_lacks = sum(1 for run, _m in s_runs if run_sql(run) and "dispatch" not in run_sql(run).lower())
        d_has = sum(1 for run, _m in d_runs if "dispatch" in run_sql(run).lower())
        if s_wrong >= 4 and s_lacks == 5 and d_has >= 4 and "dispatch" in case.key[request_id]["reference"]["sql"].lower():
            members.append({"request_id": request_id, "s_wrong": s_wrong, "s_runs_without_dispatch_in_sql": s_lacks, "d_runs_with_dispatch_in_sql": d_has,
                            "trap_classes": case.key[request_id]["trap_classes"]})
    return {
        "definition": "Requests where Sonnet S was wrong in at least 4 of 5 runs, none of its five final queries mentions the dispatch date, at least 4 of Sonnet D's do, and the key's reference query dates web sales by dispatch. It shows where the web-dating rule is present, not that it alone made S wrong: on the web-orders and as-was requests above the cause is another rule.",
        "members": members,
    }


# ============================================================================================
# MODULE 2  --  SAME QUESTION, TWO ASSISTANTS
# ============================================================================================

def pick_focus_line(run: dict, pattern: re.Pattern) -> tuple[str | None, bool, str | None]:
    """The run's own sentence on the topic: assumptions first, then caveats, then definitions applied.

    Returns (line, on_topic, field).  If the run wrote nothing on the topic, its first assumption is returned
    with on_topic False, so the page can show that the run was silent on the rule.
    """
    answer = run.get("answer") or {}
    for field in ("assumptions", "caveats", "definitions_applied"):
        for line in answer.get(field) or []:
            if isinstance(line, str) and pattern.search(line):
                return line, True, field
    lines = [l for l in (answer.get("assumptions") or []) if isinstance(l, str)]
    return (lines[0] if lines else None), False, ("assumptions" if lines else None)


def trim_line(line: str, limit: int = 300) -> tuple[str, bool]:
    """Light trim: if a line is long, cut at the end of a sentence under the limit."""
    if len(line) <= limit:
        return line, False
    cut = line[:limit]
    last_stop = max(cut.rfind(". "), cut.rfind("; "))
    if last_stop > 80:
        return line[:last_stop + 1], True
    return cut.rstrip() + " ...", True


def build_module2(case: Case) -> dict:
    log("module 2: same question, three setups ...")
    out = []
    for spec in MODULE2_SPECS:
        request_id = spec["request_id"]
        entry = case.key[request_id]
        headline_spec = spec["headline"]
        reference = extract_headline(entry["reference"]["result"], headline_spec)
        if reference is None:
            fail(f"module 2 {request_id}: no reference headline")
        accepted = [{"label": "key reference", "value": round_number(reference["value"])}]
        for alt in entry["alternatives"]:
            hl = extract_headline(alt["result"], headline_spec)
            if hl:
                accepted.append({"label": alt["label"], "value": round_number(hl["value"])})
        for interp in entry["interpretations"]:
            hl = extract_headline(interp["result"], headline_spec)
            if hl:
                accepted.append({"label": interp.get("label"), "value": round_number(hl["value"])})
        focus = re.compile(spec["focus_re"], re.I)
        setups_out = {}
        for setup_id in MODULE2_SETUP_IDS:
            runs_out = []
            for run, mark in case.runs[request_id][setup_id]:
                headline = extract_headline((run.get("answer") or {}).get("result"), headline_spec)
                line, on_topic, field = pick_focus_line(run, focus)
                text, trimmed = trim_line(line) if line else (None, False)
                record = {
                    "repeat": run["repeat"], "run_id": run["run_id"], "outcome": mark["outcome"],
                    "headline": round_number(headline["value"]) if headline else None,
                    "matched": mark.get("matched"),
                    "on_topic": on_topic, "field": field,
                    "line": ({**quote(text), "trimmed": True} if trimmed else quote(text)) if text else None,
                }
                runs_out.append(record)
            setups_out[setup_id] = {"correct": sum(1 for r in runs_out if r["outcome"] == "correct"), "runs": runs_out}
        out.append({
            "request_id": request_id,
            "text": entry["request_text"],
            "kind": spec["kind"],
            "trap_classes": entry["trap_classes"],
            "headline_label": spec["label"],
            "reference": round_number(reference["value"]),
            "accepted_values": accepted,
            "setups": setups_out,
        })
    return {"setups": MODULE2_SETUP_IDS, "requests": out}


# ============================================================================================
# MODULE 4  --  THE PROBLEM NOBODY WROTE DOWN (REQ-T42)
# ============================================================================================

def store_names(case: Case) -> dict:
    """store_id -> store name, read from the runs' own result tables; refuses on a clash."""
    names: dict = {}
    clashes = []
    for run in case.collected:
        result = (run.get("answer") or {}).get("result") or {}
        columns = result.get("columns") or []
        if "store_id" in columns and "store_name" in columns:
            i_id, i_name = columns.index("store_id"), columns.index("store_name")
            for row in result.get("rows") or []:
                store_id, name = row[i_id], row[i_name]
                if isinstance(store_id, int) and isinstance(name, str):
                    if store_id in names and names[store_id] != name and store_id < 900:
                        clashes.append((store_id, names[store_id], name))
                    names.setdefault(store_id, name)
    if clashes:
        log(f"  WARNING: store name clashes across runs: {clashes[:3]}")
    return names


def rank_table(result: dict, names: dict) -> list:
    columns = result["columns"]
    i_store, i_trading, i_sales, i_metric = (columns.index(c) for c in ("store_id", "trading_days", "net_sales", "net_sales_per_trading_day"))
    rows = sorted(result["rows"], key=lambda r: -r[i_metric])
    out, previous, rank = [], None, 0
    for position, row in enumerate(rows, start=1):
        if row[i_metric] != previous:
            rank = position
            previous = row[i_metric]
        out.append({"rank": rank, "store_id": row[i_store], "store": names.get(row[i_store]), "trading_days": row[i_trading],
                    "net_sales": row[i_sales], "per_trading_day": row[i_metric]})
    return out


NOTICE_RE = re.compile(r"duplicat|loaded twice|twice|double[- ]post|posted twice|re-?load|10,?390\.53|control total|rpt_daily_store_sales.{0,80}(?:gap|differ|mismatch)", re.I)
DIAGNOSED_RE = re.compile(r"duplicat|loaded twice|twice|double[- ]post|posted twice|re-?load", re.I)
REPAIRED_RE = re.compile(r"removed|kept one|one copy|one line per|kept each|kept the (?:first|earliest)|counted each|de-?duplicat|once|excluded the dup", re.I)


def build_module4(case: Case, module3: dict) -> dict:
    log("module 4: REQ-T42 ...")
    request_id = "REQ-T42"
    entry = case.key[request_id]
    undocumented = entry["undocumented"]
    names = store_names(case)
    corrected_result = undocumented["outcome_a_incident_free"]["result"]
    published_naive = next(n for n in entry["naive"] if n["label"] == "published_number")
    published_result = published_naive["result"]
    if undocumented["outcome_b_published_with_caveat"]["result"] != published_result:
        log("  NOTE: outcome (b) result differs from the naive 'published_number' result; using the naive one for 'as published'")
    corrected = rank_table(corrected_result, names)
    published = rank_table(published_result, names)
    if {r["store_id"] for r in corrected} != {r["store_id"] for r in published}:
        fail("T42: published and corrected tables list different stores")
    missing_names = [r["store_id"] for r in corrected if not r["store"]]
    if missing_names:
        log(f"  WARNING: no store name found for {missing_names}")
    rank_before = {r["store_id"]: r["rank"] for r in published}
    rank_after = {r["store_id"]: r["rank"] for r in corrected}
    moved = [{"store_id": s, "store": names.get(s), "rank_published": rank_before[s], "rank_corrected": rank_after[s]}
             for s in rank_before if rank_before[s] != rank_after[s]]
    moved.sort(key=lambda m: m["rank_corrected"])
    store_116_published = next(r for r in published if r["store_id"] == 116)
    store_116_corrected = next(r for r in corrected if r["store_id"] == 116)

    # --- per setup: noticed or repaired, right or wrong
    per_setup = []
    for setup in SETUPS:
        cells = {"noticed_right": 0, "noticed_wrong": 0, "not_noticed_right": 0, "not_noticed_wrong": 0}
        repaired_right = flagged_right = diagnosed = said_repaired_count = 0
        run_rows = []
        for run, mark in case.runs[request_id][setup["id"]]:
            lines = run_lines(run)
            noticed_text = any(NOTICE_RE.search(l) for l in lines)
            diagnosed_text = any(DIAGNOSED_RE.search(l) for l in lines)
            said_repaired = any(DIAGNOSED_RE.search(l) and REPAIRED_RE.search(l) for l in lines)
            route = mark.get("route")
            repaired = route == "undocumented_a"
            noticed = noticed_text or repaired and noticed_text
            right = mark["outcome"] == "correct"
            if repaired and right:
                repaired_right += 1
            if route == "undocumented_b" and right:
                flagged_right += 1
            diagnosed += 1 if diagnosed_text else 0
            said_repaired_count += 1 if said_repaired else 0
            key_name = ("noticed" if noticed else "not_noticed") + ("_right" if right else "_wrong")
            cells[key_name] += 1
            run_rows.append({"repeat": run["repeat"], "run_id": run["run_id"], "outcome": mark["outcome"], "route": route,
                             "noticed": noticed, "diagnosed_duplicate": diagnosed_text, "said_it_removed_the_duplicate": said_repaired})
        per_setup.append({"setup": setup["id"], "right": sum(1 for r in run_rows if r["outcome"] == "correct"), "wrong": sum(1 for r in run_rows if r["outcome"] == "wrong"),
                          "repaired_and_right": repaired_right, "flagged_only_and_right": flagged_right, "named_the_duplicate": diagnosed,
                          "said_it_removed_the_duplicate": said_repaired_count,
                          **cells, "runs": run_rows})
    # --- a Sonnet S example (quote), and the wrong reason: ranked by total, not per trading day
    s_example = None
    for run, mark in case.runs[request_id]["sonnet_S"]:
        for line in (run.get("answer") or {}).get("caveats") or []:
            if re.search(r"duplicat", line, re.I):
                s_example = {"run_id": run["run_id"], **quote(line)}
                break
        if s_example:
            break
    s_without_per_day_column = 0
    for run, _m in case.runs[request_id]["sonnet_S"]:
        columns = ((run.get("answer") or {}).get("result") or {}).get("columns") or []
        if not any(re.search(r"per.?(?:trading.?)?day|trading", str(c), re.I) for c in columns):
            s_without_per_day_column += 1
    def first_caveat(setup_id: str, pattern: re.Pattern):
        for run, _m in case.runs[request_id][setup_id]:
            for line in (run.get("answer") or {}).get("caveats") or []:
                if pattern.search(line):
                    return {"run_id": run["run_id"], **quote(line)}
        return None

    d_example = first_caveat("sonnet_D", re.compile(r"duplicat", re.I))
    haiku_l_example = first_caveat("haiku_L", re.compile(r"10,?390\.53|control total|gap", re.I))
    advice = doc_line(module3, "Check the source rows for the range you use as well as the output.")
    return {
        "request_id": request_id,
        "text": entry["request_text"],
        "incident": undocumented["what"],
        "period": "FY2025/26 period 5 (25 August to 21 September 2025)",
        "store_116": {"published": store_116_published, "corrected": store_116_corrected},
        "published": published,
        "corrected": corrected,
        "moved": moved,
        "per_setup": per_setup,
        "s_example": s_example,
        "d_example": d_example,
        "haiku_l_example": haiku_l_example,
        "outcomes": {
            "a": undocumented["outcome_a_incident_free"]["label"],
            "b": undocumented["outcome_b_published_with_caveat"]["label"],
            "c": undocumented["outcome_c_published_without_warning"],
        },
        "advice_line_in_document": {"line": advice["line"], "section": advice["section"], "fact_ids": advice["fact_ids"]},
        "report_notes": {
            "s_found_all_four_incidents": "Sonnet S finds all four undocumented incidents by itself, and is right on one. On REQ-T42 it names and repairs the duplicated lines (418 at store 116) in all five runs and is marked wrong for another reason: it ranks by total net sales instead of per trading day.",
            "advice_hindsight": "The advice to check source rows for duplicates, which was written after two of the problems were already known, is consistent with this. Each run was not traced.",
            "haiku_flags": "The 4 passes are REQ-T42 caveats that flag the 10,390.53 EUR control-total gap at store 116 without diagnosing the duplicate. All are Haiku L.",
        },
        "s_runs_without_a_per_trading_day_column": s_without_per_day_column,
    }


# ============================================================================================
# MODULE 5  --  SCOREBOARD
# ============================================================================================

def build_module5(case: Case) -> dict:
    log("module 5: scoreboard ...")
    # --- overall correct by setup, recomputed from the marks and checked against results.json
    overall = {}
    for setup in SETUPS:
        correct = sum(1 for m in case.marked if (m["model"], m["arm"]) == (setup["model"], setup["arm"]) and m["outcome"] == "correct")
        reported = case.results["correctness"]["overall"][setup["cell"]]
        if correct != reported["correct"]:
            fail(f"overall correct for {setup['cell']}: recomputed {correct}, results.json says {reported['correct']}")
        overall[setup["id"]] = {"correct": correct, "runs": 300, "share": round(correct / 300, 4),
                                "ci_low": reported["ci_low"], "ci_high": reported["ci_high"]}
    # --- per class
    classes = list(CLASS_LABELS)
    per_class = {}
    for cls in classes:
        request_ids = sorted(r for r, e in case.key.items() if cls in e["trap_classes"])
        row = {"label": CLASS_LABELS[cls], "n_requests": len(request_ids), "request_ids": request_ids, "setups": {}}
        for setup in SETUPS:
            correct = sum(case.n_correct(r, setup["id"]) for r in request_ids)
            reported = case.results["correctness"]["by_class"][cls][setup["cell"]]
            if correct != reported["correct"] or len(request_ids) * 5 != reported["runs"]:
                fail(f"class {cls} {setup['cell']}: recomputed {correct}/{len(request_ids) * 5}, results.json {reported['correct']}/{reported['runs']}")
            row["setups"][setup["id"]] = {"correct": correct, "runs": len(request_ids) * 5}
        per_class[cls] = row
    # --- lay groups (a request touching two groups counts in both) and an exclusive version
    groups = []
    for group in LAY_GROUPS:
        request_ids = sorted(r for r, e in case.key.items() if any(c in group["classes"] for c in e["trap_classes"]))
        row = {"id": group["id"], "label": group["label"], "classes": group["classes"], "n_requests": len(request_ids),
               "request_ids": request_ids, "setups": {}}
        for setup in SETUPS:
            row["setups"][setup["id"]] = {"correct": sum(case.n_correct(r, setup["id"]) for r in request_ids), "runs": len(request_ids) * 5}
        groups.append(row)
    overlapping = sorted(r for r, e in case.key.items()
                         if sum(1 for g in LAY_GROUPS if any(c in g["classes"] for c in e["trap_classes"])) > 1)
    # --- tokens
    tokens = {}
    for setup in SETUPS:
        values = [run["total_tokens"] for run in case.collected if (run["model"], run["arm"]) == (setup["model"], setup["arm"])]
        if any(v is None for v in values):
            fail(f"missing total_tokens in {setup['cell']}")
        median = statistics.median(values)
        total = sum(values)
        correct = overall[setup["id"]]["correct"]
        per_correct = total / correct
        reported = case.results["tokens"]["cells"][setup["cell"]]
        if abs(median - reported["median"]) > 0.5 or abs(per_correct - reported["per_correct_answer"]) > 0.5:
            fail(f"tokens for {setup['cell']}: recomputed median {median}, per correct {per_correct}; results.json {reported['median']}, {reported['per_correct_answer']}")
        tokens[setup["id"]] = {"median_per_run": median, "total_tokens": total, "correct_runs": correct,
                               "tokens_per_correct_run": round(per_correct, 1)}
    return {
        "setups": [{k: s[k] for k in ("id", "short", "label", "what")} for s in SETUPS],
        "overall": overall,
        "per_class": per_class,
        "lay_groups_overlapping": groups,
        "lay_groups_note": "A request that carries classes from two groups appears in both, so the group request counts add to more than 60 (n_distinct_requests_across_groups). Per class the same holds.",
        "n_distinct_requests_across_groups": len({r for g in groups for r in g["request_ids"]}),
        "requests_in_more_than_one_lay_group": overlapping,
        "tokens": tokens,
        "tokens_note": case.results["tokens"]["note"],
        "tokens_per_correct_run_definition": "Total tokens over all 300 runs of the setup, divided by its correct runs.",
    }


# ============================================================================================
# MODULE 6  --  THE TWELVE PREDICTIONS
# ============================================================================================

def build_module6() -> dict:
    log("module 6: predictions ...")
    frozen = load_text(PATH_PREDICTIONS)
    report = load_text(PATH_REPORT)
    # --- the frozen file: "**N. Title.** bet" then "- MET if ...", "- Why: ..."
    bets = {}
    section = re.split(r"\n## ", frozen.split("## The predictions", 1)[1], maxsplit=1)[0]   # up to the next heading
    for match in re.finditer(r"\*\*(\d+)\. ([^*]+?)\.\*\* (.*?)\n((?:- .*\n?)+)", section):
        number = int(match.group(1))
        bullets = [b[2:].strip() for b in match.group(4).strip().splitlines()]
        met_rule = next((b for b in bullets if b.startswith("MET if")), None)
        why = next((b[len("Why: "):] for b in bullets if b.startswith("Why:")), None)
        bets[number] = {"title": match.group(2).strip(), "bet": match.group(3).strip(), "met_rule": met_rule, "why": why}
    if sorted(bets) != list(range(1, 13)):
        fail(f"predictions parsed from the frozen file: {sorted(bets)}")
    # --- report section 2 table
    table_text = report.split("## 2. The twelve frozen predictions", 1)[1].split("### Diagnosis of the misses", 1)[0]
    verdicts = {}
    for line in table_text.splitlines():
        match = re.match(r"^\|\s*(\d+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$", line)
        if match:
            number = int(match.group(1))
            verdict_text = match.group(3).replace("**", "").strip()
            verdicts[number] = {"report_title": match.group(2).strip(), "verdict": verdict_text,
                                "met": verdict_text.upper() == "MET", "numbers": match.group(4).replace("**", "").strip()}
    if sorted(verdicts) != list(range(1, 13)):
        fail(f"predictions parsed from report section 2: {sorted(verdicts)}")
    # --- diagnosis bullets, verbatim (the key-correction parenthetical in item 12 is left out by instruction)
    diag_text = report.split("### Diagnosis of the misses", 1)[1].split("### Marker sensitivity", 1)[0]
    diagnosis = {}
    current = None
    for line in diag_text.splitlines():
        top = re.match(r"^- \*\*([\d. and]+)\*\*\s*(.*)$", line)
        if top:
            numbers = [int(n) for n in re.findall(r"\d+", top.group(1))]
            current = numbers
            for number in numbers:
                diagnosis[number] = [top.group(2).strip()] if top.group(2).strip() else []
            continue
        if current and line.strip().startswith("- "):
            for number in current:
                diagnosis[number].append(line.strip()[2:].strip())
        elif current and line.strip() and line.startswith("  "):
            for number in current:
                diagnosis[number].append(line.strip())
    cleaned = {}
    for number, parts in diagnosis.items():
        kept = []
        for part in parts:
            part = re.sub(r"\s*\(In the first marking.*?\)\s*$", "", part).strip()
            if part:
                kept.append(part.replace("**", ""))
        cleaned[number] = kept
    predictions = []
    for number in range(1, 13):
        predictions.append({
            "n": number,
            "title": bets[number]["title"],
            "report_title": verdicts[number]["report_title"],
            "bet": bets[number]["bet"],
            "met_rule": bets[number]["met_rule"],
            "why": bets[number]["why"],
            "met": verdicts[number]["met"],
            "verdict": verdicts[number]["verdict"],
            "numbers": verdicts[number]["numbers"],
            "diagnosis": cleaned.get(number, []),
        })
    met_count = sum(1 for p in predictions if p["met"])
    marker_note = "Predictions 2 and 6 move with the marker. The prediction file names the built marker, so the verdicts above stand."
    if marker_note not in report:
        fail("marker sensitivity sentence not found in report.md")
    return {
        "source_notes": "Titles, bets and rules are verbatim from the frozen predictions file; verdicts and numbers are verbatim from data/analysis/report.md section 2.",
        "n_met": met_count,
        "n_not_met": 12 - met_count,
        "summary_line": "Six met, six not met. Nothing is retuned.",
        "marker_note": marker_note,
        "predictions": predictions,
    }


# ============================================================================================
# CANDIDATES.md
# ============================================================================================

def fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def write_candidates_md(module1: dict, module2: dict, module1_extra: dict, case: Case | None = None) -> None:
    out = []
    out.append("# Case 11 explorer: candidates for module 1 (Play the analyst) and module 2 (Same question, two assistants)\n")
    out.append("Generated by `interactive/build_data.py` from the case files. Every number below comes from the files; nothing is estimated. "
               "S = Sonnet with the database only, D = Sonnet with the shared document, L = Sonnet with the skills library. "
               "Quotes are the runs' own words. `[jargon: ...]` marks terms a lay reader would not follow.\n")
    out.append("## Module 1: twelve candidates, cleanest single-rule story first\n")
    out.append("Ranked by: S wrong in 5 of 5 runs; the gap reconciles to something S states itself or S reproduces a key variant exactly; the main departure shows in all five S runs; fewest other departures.\n")
    out.append("| # | Request | Rule (one line) | S right | D right | L right | Correct | S typical | Main departure (S runs) | Other departures |")
    out.append("|---|---|---|---|---|---|---|---|---|---|")
    for c in module1["candidates"]:
        others = ", ".join(f"{e['text'].split(' (')[0].lower()} ({e['n']}/5)" for e in c["s_did"]["also"] if not e["right_per_company"] and not e["info_only"] and not e["accepted_by_key"] and e["n"]) or "none"
        out.append(f"| {c['rank']} | {c['request_id']} | {c['short_title']} | {c['counts']['sonnet_S']['correct']}/5 | {c['counts']['sonnet_D']['correct']}/5 | "
                   f"{c['counts']['sonnet_L']['correct']}/5 | {fmt(c['headline']['correct'])} | {fmt(c['headline']['s_typical'])} (x{c['headline']['s_typical_n']}) | "
                   f"{c['s_did']['main']['n']}/5 | {others} |")
    out.append("")
    for c in module1["candidates"]:
        out.append(f"### {c['rank']}. {c['request_id']}: {c['short_title']}\n")
        out.append(f"> {c['text']}\n")
        out.append(f"{c['department']}, {c['requester']}, received {c['received']}. Trap classes: {', '.join(c['trap_classes'])}.\n")
        out.append(f"**The one rule:** {c['one_rule']}\n")
        out.append("**Where it is written down (exact lines from `arms/prompt_doc.md`):**\n")
        for rule in c["rules"]:
            skills = ", ".join(rule["library_skills"]) or "-"
            out.append(f"- `{', '.join(rule['fact_ids'])}` (section {rule['section']}, line {rule['doc_line_no']}; library skill: {skills})")
            out.append(f"  > {rule['line']}")
        if c.get("key_docs_line"):
            out.append(f"- The key's own pointer: {c['key_docs_line']}")
        out.append("")
        h = c["headline"]
        out.append(f"**Result ({h['label']}):** correct = {fmt(h['correct'])}; S's typical = {fmt(h['s_typical'])} in {h['s_typical_n']} of 5 runs "
                   f"(S's five: {', '.join(fmt(v) for v in h['s_values'])}); D's five: {', '.join(fmt(v) for v in h['d_values'])}. "
                   f"Right out of 5: S {c['counts']['sonnet_S']['correct']}, D {c['counts']['sonnet_D']['correct']}, L {c['counts']['sonnet_L']['correct']}, "
                   f"L− {c['counts']['sonnet_Lm']['correct']}, Haiku S {c['counts']['haiku_S']['correct']}, Haiku L {c['counts']['haiku_L']['correct']}.\n")
        if h.get("gap_explained_by"):
            q = h["gap_explained_by"]["quote"]
            out.append(f"The gap ({fmt(h['gap'])}) is stated by S itself ({h['gap_explained_by']['run_id']}): \"{q['t']}\"\n")
        out.append("**What S did, from its own assumptions (count of its 5 runs):**\n")
        m = c["s_did"]["main"]
        inferred = f", {m['n_inferred']} inferred from identical figures" if m["n_inferred"] else ""
        out.append(f"- MAIN: {m['text']}: **{m['n']} of 5** ({m['n_stated']} stated{inferred})")
        for run in m["runs"][:2]:
            if run.get("quote"):
                jar = f" [jargon: {', '.join(run['quote']['j'])}]" if run["quote"].get("j") else ""
                out.append(f"  - {run['run_id']}: \"{run['quote']['t']}\"{jar}")
        for e in c["s_did"]["also"]:
            tag = "also (S got this right)" if e["right_per_company"] else ("also (accepted by the key, so not why S is marked wrong)" if e["accepted_by_key"] else ("for the record" if e["info_only"] else "also (a second departure)"))
            out.append(f"- {tag}: {e['text']}: {e['n']} of 5")
        if c["reproduces_key_variant"]:
            rv = c["reproduces_key_variant"]
            out.append(f"- S's figures match the key's naive variant `{rv['label']}` exactly in {rv['n']} of 5 runs.")
        if c.get("states_accepted_alternative"):
            sa = c["states_accepted_alternative"]
            out.append(f"- S ({sa['run_id']}) states the figure the key accepts as an alternative ({fmt(sa['value'])}): \"{sa['quote']['t']}\"")
        out.append("")
        if c.get("d_words"):
            jar = f" [jargon: {', '.join(c['d_words']['j'])}]" if c["d_words"].get("j") else ""
            out.append(f"**D, in its own words** ({c['d_words']['run_id']}): \"{c['d_words']['t']}\"{jar}\n")
        if c["s_text_states_correct_figure"]:
            hits = c["s_text_states_correct_figure"]
            out.append(f"**S wrote the correct figure in its own notes** in {len(hits)} of 5 runs but returned another one in its table. For example ({hits[0]['run_id']}): \"{hits[0]['quote']['t']}\"\n")
        out.append("**Plausible readings:**\n")
        for r in c["readings"]:
            shown = f" -> {fmt(r['value'])}" if r.get("value") is not None else ""
            out.append(f"- {r['label']} ({r['who']}){shown}: {r['plain']}")
        if c["key_variants"]:
            out.append("- Key variants, verbatim: " + " | ".join(f"`{v['label']}`: {v['plain']} ({v['difference']})" for v in c["key_variants"]))
        if c["key_alternatives"]:
            out.append("- Accepted by the key: " + " | ".join(a["label"] for a in c["key_alternatives"]))
        if c.get("twin"):
            tw = c["twin"]
            out.append(f"- Twin {tw['request_id']} ({tw['note']}): right out of 5 - S {tw['s_correct']}, D {tw['d_correct']}, L {tw['l_correct']}.")
            if tw.get("s_quote"):
                jar = f" [jargon: {', '.join(tw['s_quote']['j'])}]" if tw["s_quote"].get("j") else ""
                out.append(f"  - S on the twin ({tw['s_quote']['run_id']}): \"{tw['s_quote']['t']}\"{jar}")
        out.append("")
    if case is not None:
        family_ids = {m["request_id"] for m in module1_extra["web_dating_family"]["members"]}
        out.append("## Also qualify (Sonnet S right in at most 1 of 5, Sonnet D right in 5 of 5), not developed above\n")
        out.append("| Request | Classes | Request text | S | D | L | Haiku S | Haiku L | In the web-dating family |")
        out.append("|---|---|---|---|---|---|---|---|---|")
        for item in module1["all_eligible_requests"]:
            if item["in_candidates"]:
                continue
            r = item["request_id"]
            out.append(f"| {r} | {', '.join(item['trap_classes'])} | {case.key[r]['request_text'].replace('|', '/')} | {case.n_correct(r, 'sonnet_S')}/5 | {case.n_correct(r, 'sonnet_D')}/5 | "
                       f"{case.n_correct(r, 'sonnet_L')}/5 | {case.n_correct(r, 'haiku_S')}/5 | {case.n_correct(r, 'haiku_L')}/5 | {'yes' if r in family_ids else 'no'} |")
        out.append("")
    fam = module1_extra["web_dating_family"]
    out.append("## Same rule, other requests (the web-dating family)\n")
    out.append(fam["definition"] + "\n")
    out.append("| Request | Classes | S wrong | S runs without dispatch in SQL | D runs with dispatch in SQL |")
    out.append("|---|---|---|---|---|")
    for member in fam["members"]:
        out.append(f"| {member['request_id']} | {', '.join(member['trap_classes'])} | {member['s_wrong']}/5 | {member['s_runs_without_dispatch_in_sql']}/5 | {member['d_runs_with_dispatch_in_sql']}/5 |")
    out.append("")
    out.append("## Module 2: eleven requests, five runs each of S, D and L\n")
    out.append("Headline numbers are pulled from each run's returned table (see `headline_label`). Marked correct (✓) or wrong (x) by the marker (code/mark.py). "
               "Assumption line = the run's own words (first line matching the topic; trimmed at a sentence if long). \n")
    for req in module2["requests"]:
        out.append(f"### {req['request_id']} ({req['kind']}): {req['text']}\n")
        acc = "; ".join(f"{a['label']}: {fmt(a['value'])}" for a in req["accepted_values"])
        out.append(f"{req['headline_label']}. Key: {acc}.\n")
        out.append("| Setup | Run | Headline | Marked | Assumption (own words) |")
        out.append("|---|---|---|---|---|")
        for setup_id in module2["setups"]:
            for run in req["setups"][setup_id]["runs"]:
                line = run["line"]["t"] if run["line"] else "-"
                jar = f" [jargon: {', '.join(run['line']['j'])}]" if run["line"] and run["line"].get("j") else ""
                mark = "✓" if run["outcome"] == "correct" else "x"
                out.append(f"| {setup_id.split('_')[1]} | {run['repeat']} | {fmt(run['headline'])} | {mark} | {line.replace('|', '/')}{jar} |")
        out.append("")
    OUT_CANDIDATES.write_text("\n".join(out) + "\n", encoding="utf-8")


# ============================================================================================
# THE PUBLIC FILE
# ============================================================================================
# Rule: nothing private goes into the published page, data blobs embedded in it
# included.  _data.json is inlined into the public page, so it holds ONLY the keys the page's JavaScript reads
# (checked against _template.html), and none of the build metadata, file paths, run ids, notes or flags.

# Internal test-request ids (REQ-T..) are not shown to readers.  Sentences in the public copy that carry them are
# rewritten as little as possible: a parenthetical id is dropped, a list that matters becomes a count or a description.
# Every pair is (original text, public text); the build fails if an original is not found, and the pairs are written to
# _data_internal.json ("public_edits") so each change can be checked.
PUBLIC_REWRITES = [
    ("makes the same wrong choice in all five runs on 8 (REQ-T15, T21, T25, T36, T42, T43, T59, T60).",
     "makes the same wrong choice in all five runs on 8."),
    ("10 of its 19 are the two return-rate requests (REQ-T06, T23).",
     "10 of its 19 are the two return-rate requests."),
    ("The other 9 are partial like-for-like runs (REQ-T01 3 of 5, T34 4, T53 2).",
     "The other 9 are partial like-for-like runs, on three requests where it was right in 3, 4 and 2 of 5 runs."),
    ("L without REQ-T16 15/15 (needed \u22647)",
     "L without the click-and-collect request 15/15 (needed \u22647)"),
    ("S's 5 are all REQ-T12:",
     "S's 5 are all on the West stock request:"),
    ("The gaps are all REQ-T16, where the template",
     "The gaps are all on the click-and-collect request, where the template"),
    ("A correct REQ-T16 answer from D or L",
     "A correct click-and-collect answer from D or L"),
    ("wrong for other reasons (section 8, item 3), so the clause",
     "wrong for other reasons, so the clause"),
    ("The one miss in L's 65 is REQ-T29 (the VAT rate written as 0.255).",
     "The one miss in L's 65 is a VAT answer (the VAT rate written as 0.255)."),
]


def rewrite_public_text(text: str, edits: list) -> str:
    """Apply PUBLIC_REWRITES to one string, noting each change once (original sentence, new sentence)."""
    original = text
    for old, new in PUBLIC_REWRITES:
        text = text.replace(old, new)
    if text != original:
        edits.append({"before": original, "after": text})
    return text


def make_public(data: dict, edits: list | None = None) -> dict:
    """Whitelist copy of the full data: every key listed here is read by _template.html, nothing else."""
    edits = edits if edits is not None else []
    meta = data["meta"]
    m1 = data["m1_play_the_analyst"]["candidates"]
    m2 = data["m2_same_question"]["requests"]
    m3 = data["m3_rules_written_down"]
    m4 = data["m4_undocumented_t42"]
    m5 = data["m5_scoreboard"]
    m6 = data["m6_predictions"]["predictions"]

    def public_run(run: dict) -> dict:
        record = {"outcome": run["outcome"], "headline": run["headline"]}
        if run.get("line") and run["line"].get("t"):
            record["line"] = {"t": run["line"]["t"]}      # the run's own words; jargon flags stay internal
        return record

    return {
        "meta": {k: meta[k] for k in ("n_requests", "runs_per_request_per_setup", "n_runs")},
        "setups": [{"id": s["id"], "short": s["short"]} for s in data["setups"]],
        "m1_play_the_analyst": {"candidates": [
            {"request_id": c["request_id"],
             "headline": {"s_typical": c["headline"]["s_typical"], "correct": c["headline"]["correct"]},
             "s_runs": [{"outcome": r["outcome"]} for r in c["s_runs"]],
             "d_runs": [{"outcome": r["outcome"]} for r in c["d_runs"]]}
            for c in m1]},
        "m2_same_question": {"requests": [
            {"request_id": r["request_id"], "text": r["text"], "reference": r["reference"],
             "setups": {sid: {"runs": [public_run(run) for run in r["setups"][sid]["runs"]]} for sid in ("sonnet_S", "sonnet_D")}}
            for r in m2]},
        "m3_rules_written_down": {
            "document": {
                "n_fact_ids": m3["document"]["n_fact_ids"],
                "words_without_markers": m3["document"]["words_without_markers"],
                "sections": [{"no": s["no"], "title": s["title"], "kind": s["kind"]} for s in m3["document"]["sections"]]},
            "library": {k: m3["library"][k] for k in ("n_skills", "n_files", "n_fact_ids")},
            "blocks": [{"section_no": b["section_no"], "section_title": b["section_title"], "n_requests": b["n_requests"],
                        "text": b["text"], "home_skills": b["home_skills"]} for b in m3["blocks"]]},
        "m4_undocumented_t42": {
            "published": [{k: r[k] for k in ("rank", "store_id", "store", "trading_days", "net_sales", "per_trading_day")} for r in m4["published"]],
            "corrected": [{k: r[k] for k in ("rank", "store_id", "store", "trading_days", "net_sales", "per_trading_day")} for r in m4["corrected"]],
            "moved": [{"store_id": m["store_id"]} for m in m4["moved"]]},
        "m5_scoreboard": {
            "overall": {sid: {"share": v["share"]} for sid, v in m5["overall"].items()},
            "lay_groups_overlapping": [{"label": g["label"], "n_requests": g["n_requests"], "setups": g["setups"]} for g in m5["lay_groups_overlapping"]],
            "tokens": {sid: {k: v[k] for k in ("median_per_run", "correct_runs", "tokens_per_correct_run")} for sid, v in m5["tokens"].items()}},
        "m6_predictions": {"predictions": [
            {"n": p["n"], "title": p["title"], "met": p["met"], "bet": rewrite_public_text(p["bet"], edits),
             "numbers": rewrite_public_text(p["numbers"], edits), "diagnosis": [rewrite_public_text(d, edits) for d in p["diagnosis"]]}
            for p in m6]},
    }


# Terms that must not appear in the public file at all (paths, run ids, people, internal file types).
PUBLIC_HARD_BLOCK = re.compile(r"C:\\|/Users/|Dropbox|\.jsonl|\.py\b|full-(?:sonnet|haiku)|\bEva\b|\bLuigi\b|built_by|authoring_note|how_counted|working_rank|\bsources\b|code/mark")
# Terms reported (not blocked) so every hit can be checked against the page text and the verbatim rule text.
PUBLIC_REPORT_TERMS = ["C:\\", "/Users/", "Dropbox", ".md", ".py", ".jsonl", "full-", "REQ-", "agent", "Eva", "Luigi", "marker", "built", "note"]


def scan_public(payload: str) -> dict:
    hits = {}
    lowered = payload.lower()
    for term in PUBLIC_REPORT_TERMS:
        needle = term.lower()
        positions = [m.start() for m in re.finditer(re.escape(needle), lowered)]
        if positions:
            hits[term] = [payload[max(0, i - 40):i + len(term) + 40].replace("\n", " ") for i in positions]
    return hits


# ============================================================================================
# MAIN
# ============================================================================================

def main() -> int:
    try:
        if OUT_JSON.resolve() in (PATH_MARKED, PATH_KEY, PATH_COLLECTED):
            fail("output path equals an input path")
        HERE.mkdir(parents=True, exist_ok=True)
        case = Case()
        module3 = build_module3(case)

        log("module 1: candidates ...")
        citations = parse_key_citations(load_text(PATH_REVIEW_SHEET))
        candidates = []
        for spec in CANDIDATE_SPECS:
            candidate = build_candidate(case, module3, spec)
            candidate["key_docs_line"] = citations[spec["request_id"]]["line"]
            candidates.append(candidate)
            log(f"  {spec['request_id']}: S {candidate['counts']['sonnet_S']['correct']}/5, D {candidate['counts']['sonnet_D']['correct']}/5, "
                f"main departure {candidate['s_did']['main']['n']}/5, S typical {candidate['headline']['s_typical']} vs correct {candidate['headline']['correct']}")
        # selection rule: S wrong in at least 4 of 5 runs and D right in all 5
        for c in candidates:
            if c["counts"]["sonnet_S"]["correct"] > 1 or c["counts"]["sonnet_D"]["correct"] != 5:
                fail(f"{c['request_id']} does not meet the S-wrong->=4 / D-right-5 condition")
        candidates = rank_candidates(candidates)
        module1 = {"candidates": candidates}
        module1_extra = {"web_dating_family": web_dating_family(case)}
        module1["web_dating_family"] = module1_extra["web_dating_family"]
        module1["selection_rule"] = "Requests where Sonnet S was right in at most 1 of 5 runs (wrong in at least 4) and Sonnet D was right in 5 of 5."
        # every request meeting the rule, so the page (or a reviewer) can see what was left out
        eligible = [r for r in sorted(case.key) if case.n_correct(r, "sonnet_S") <= 1 and case.n_correct(r, "sonnet_D") == 5]
        module1["all_eligible_requests"] = [
            {"request_id": r, "trap_classes": case.key[r]["trap_classes"], "s_right": case.n_correct(r, "sonnet_S"),
             "in_candidates": r in {c["request_id"] for c in candidates}} for r in eligible]

        family_ids = [m["request_id"] for m in module1_extra["web_dating_family"]["members"]]
        recognition = module3["facts"]["DEF-WEB-RECOGNITION"]
        recognition["note"] = (f"Under-counted by both signals. Beyond the {recognition['n_either']} requests counted here, Sonnet S used order dates and Sonnet D "
                               f"dispatch dates in the final queries of {len(family_ids)} requests where S was wrong in at least 4 of 5 runs ({', '.join(family_ids)}); "
                               "see m1_play_the_analyst.web_dating_family.")
        for block in module3["blocks"]:
            if "DEF-WEB-RECOGNITION" in block["fact_ids"]:
                block["note"] = recognition["note"]

        module2 = build_module2(case)
        module4 = build_module4(case, module3)
        module5 = build_module5(case)
        module6 = build_module6()

        module3_public = {k: v for k, v in module3.items() if not k.startswith("_")}

        # --- the page's selection: only the chosen requests, in the chosen order
        by_id1 = {c["request_id"]: c for c in module1["candidates"]}
        by_id2 = {r["request_id"]: r for r in module2["requests"]}
        for wanted, available, label in ((PAGE_MODULE1_ORDER, by_id1, "module 1"), (PAGE_MODULE2_ORDER, by_id2, "module 2")):
            absent = [r for r in wanted if r not in available]
            if absent:
                fail(f"{label}: chosen requests not built: {absent}")
        page_candidates = []
        for position, request_id in enumerate(PAGE_MODULE1_ORDER, start=1):
            candidate = dict(by_id1[request_id])
            candidate["working_rank"] = candidate.pop("rank")   # the cleanliness rank used in CANDIDATES.md
            candidate["order"] = position
            page_candidates.append(candidate)
        page_module1 = {"candidates": page_candidates, "web_dating_family": module1["web_dating_family"]}
        page_module2 = {**module2, "requests": [by_id2[r] for r in PAGE_MODULE2_ORDER]}
        data = {
            "meta": {
                "project": "11 Skills Library",
                "built_by": "interactive/build_data.py",
                "n_requests": 60, "runs_per_cell": 300, "runs_per_request_per_setup": 5, "n_runs": 1800,
                "marker": "code/mark.py, marker 6, with arm-blind adjudication (data/analysis/marked_runs.jsonl, field 'outcome')",
                "synthetic_note": "The company, warehouse and requests are synthetic and engineered with a known answer key.",
                "authoring_note": "Titles, one-line rules, reading labels and 'what S did' labels in m1 are working text written for the build, not page copy; every count, number and quotation beside them is read from the files. Quotes (field 't') are the runs' own words, verbatim; 'j' lists jargon or internal ids in them.",
                "sources": ["data/analysis/marked_runs.jsonl", "data/analysis/collected_runs.jsonl", "data/key/key.json", "data/key/review_sheet.md",
                            "data/requests/test_requests.json", "data/analysis/results.json", "data/analysis/report.md", "arms/prompt_doc.md",
                            "arms/library/", "design/predictions-FROZEN-2026-10-15.md", "world/", "data/facts.yaml"],
            },
            "setups": [{k: s[k] for k in ("id", "short", "label", "what", "model", "arm")} for s in SETUPS],
            "m1_play_the_analyst": page_module1,
            "m2_same_question": page_module2,
            "m3_rules_written_down": module3_public,
            "m4_undocumented_t42": module4,
            "m5_scoreboard": module5,
            "m6_predictions": module6,
        }

        if OUT_JSON.resolve() == PATH_KEY.resolve():
            fail("refusing to write: output path equals an input path")
        public_edits: list = []
        public = make_public(data, public_edits)
        public_payload = json.dumps(public, ensure_ascii=False, separators=(",", ":"))
        # every rewrite must have fired, and no internal test id may remain in reader-facing text
        used = {(e["before"], e["after"]) for e in public_edits}
        for old, new in PUBLIC_REWRITES:
            if not any(old in before for before, _after in used):
                fail(f"public rewrite did not apply (source text changed?): {old[:60]!r}")
        leftover_ids = re.findall(r"REQ-T\d+", re.sub(r'"request_id":"REQ-T\d+"', "", public_payload))
        if leftover_ids:
            fail(f"internal test ids remain in reader-facing public text: {sorted(set(leftover_ids))}")
        log(f"  public copy: {len(public_edits)} sentences rewritten to remove internal test ids")
        data["public_edits"] = public_edits
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        # Guard: these topics belong in the report, not in the page data.
        forbidden = re.compile(r"query.budget|\bre-?runs?\b|double.?launch|launched twice|key correction|16 oct|cap.?12|told (?:12|30)|30.quer|12.quer|swapped at source|superseded", re.I)
        leaks = sorted({m.group(0) for m in forbidden.finditer(payload)})
        if leaks:
            fail(f"_data.json mentions topics that were to be left out: {leaks}")
        blocked = sorted({m.group(0) for m in PUBLIC_HARD_BLOCK.finditer(public_payload)})
        if blocked:
            fail(f"the public data file contains blocked terms: {blocked}")
        if "</script" in public_payload.lower():
            fail("the public data file contains a closing script tag")
        if OUT_JSON_INTERNAL.resolve() == OUT_JSON.resolve():
            fail("internal and public output paths are the same")
        OUT_JSON_INTERNAL.write_text(payload, encoding="utf-8")
        OUT_JSON.write_text(public_payload, encoding="utf-8")
        log(f"wrote {OUT_JSON_INTERNAL.name} (everything, never published): {OUT_JSON_INTERNAL.stat().st_size / 1024:.1f} KB")
        size_kb = OUT_JSON.stat().st_size / 1024
        log(f"wrote {OUT_JSON.name} (public, what the page reads): {size_kb:.1f} KB")
        if size_kb > SIZE_BUDGET_KB:
            log(f"WARNING: over the {SIZE_BUDGET_KB} KB budget")
        for term, contexts in scan_public(public_payload).items():
            log(f"  public scan: '{term}' x{len(contexts)}")
        for module_key in ("m1_play_the_analyst", "m2_same_question", "m3_rules_written_down", "m4_undocumented_t42", "m5_scoreboard", "m6_predictions"):
            log(f"  {module_key}: {len(json.dumps(data[module_key], ensure_ascii=False, separators=(',', ':'))) / 1024:.1f} KB")

        write_candidates_md(module1, module2, module1_extra, case)
        log(f"wrote {OUT_CANDIDATES} ({OUT_CANDIDATES.stat().st_size / 1024:.1f} KB)")
        return 0
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 -- report, never crash bare
        import traceback
        traceback.print_exc()
        print(f"[build_data] FATAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
