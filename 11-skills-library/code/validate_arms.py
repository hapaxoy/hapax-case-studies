"""Phase 4 checks on the arm materials (rules 16 to 18).

The materials are the shared prompt document and the skills library in arms/, written by an isolated builder that could
read world/ and the warehouse and nothing else. They are never edited by hand; this file only reads them.

  Rule 16  Parity       the doc and the library carry the same set of world fact IDs (and the same source labels), and each
                        carries the content of every fact it tags, not only the tag
  Rule 17  Provenance   every fact ID and source label in either artefact exists in world/; nothing from the four undocumented
                        incidents appears in either (keywords, dates, store, row counts, fiscal-week combinations, phrases);
                        the library's check script is generic (no incident literal in its code, and it flags a double-post
                        planted at a store and week that belong to no incident)
  Rule 18  Leakage      no test request, or near-paraphrase of one, appears in world/, the doc or the library; no reference
                        SQL from the key appears in the doc's or the library's SQL

Called by validate_data.py (run(connection, record)); can also be run alone: python validate_arms.py
Only prompt_doc.md and library/ are what an arm would be given. build_notes.md and tests/ in arms/ are the builder's own
records; they describe the incidents the builder found while querying and must never be handed to an arm. They are not
scanned for rule 17 (a note below says what they contain).
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

import build_requests
import config as cfg
import validate_world

# ---------------------------------------------------------------------------
# Markers, dates and patterns
# ---------------------------------------------------------------------------

FACT_MARKER = re.compile(r"<!--\s*facts:\s*([^>]*?)\s*-->")
SOURCE_MARKER = re.compile(r"<!--\s*source:\s*([^>]*?)\s*-->")
ANY_COMMENT = re.compile(r"<!--.*?-->", re.S)
FACT_ID = re.compile(r"\b(?:CAL|DEF|REG|TEAM)-[A-Z0-9]+(?:-[A-Z0-9]+)*\b")
SQL_FENCE = re.compile(r"```sql\s*\n(.*?)```", re.S | re.I)

MONTHS = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
          "september": 9, "october": 10, "november": 11, "december": 12,
          "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}
MONTH_PATTERN = "(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + ")"
RANGE_DASH = r"(?:-|–|—|to|and)"

# Incident phrasings that would point an assistant at a planted problem without naming a date. Each is a hint the
# builder could only have got from querying. Hits are listed with their context.
INCIDENT_PHRASES = [
    (r"logged[_ -]?in[^.\n]{0,100}(null|missing|lost|without|blank|dropped)[^.\n]{0,40}member", "INC-2 logged-in orders without a member key"),
    (r"member[_ ]key[^.\n]{0,60}(lost|missing|dropped|blank|orphan)", "INC-2 member key lost"),
    (r"\b(lost|lose|loses|losing|dropped)\s+(their\s+|the\s+|its\s+|a\s+)?member[_ ]key", "INC-2 orders lost the member key"),
    (r"(click[-_ ]and[-_ ]collect|click_and_collect)[^.\n]{0,100}(mislabel|mis-label|wrong channel|home[-_ ]delivery (key|channel)|carried the)", "INC-4 click-and-collect carried the delivery key"),
    (r"channel_id[^.\n]{0,80}fulfilment_type[^.\n]{0,60}(disagree|mismatch|differ|inconsist)", "INC-4 channel_id and fulfilment_type disagree"),
    (r"fulfilment_type[^.\n]{0,80}channel_id[^.\n]{0,60}(disagree|mismatch|differ|inconsist)", "INC-4 fulfilment_type and channel_id disagree"),
    (r"west[^.\n]{0,80}(stock|snapshot)[^.\n]{0,80}(twice|duplicate|reload|loaded)", "INC-3 West stock snapshot loaded twice"),
    (r"(till|pos|register)[^.\n]{0,40}(re-?sync|re-?post|replay)", "INC-1 till re-sync"),
    (r"store_id\s*=\s*116|store\s+116|\blielahti\b", "INC-1 store 116"),
    (r"\b(re-?posted|reposted|re-?loaded|reloaded|posted\s+(twice|two times)|loaded\s+(twice|two times)|double[- ]?posted?)\b", "duplicate-load wording"),
]

# Generic words that are allowed even though they sound close to the incidents (they are the defence, not the hint).
ALLOWED_GENERIC = ("duplicate keys", "duplicate key", "duplicate rows", "duplicate receipt", "duplicate stock")


def normalise_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace(" ", " ")).strip()


def words(text: str) -> list[str]:
    return re.findall(r"[\w']+", text.lower())


def ngram_set(tokens: list[str], size: int) -> set:
    return {tuple(tokens[i:i + size]) for i in range(len(tokens) - size + 1)}


def parse_dates(text: str) -> tuple[set, set]:
    """Return (full dates, partial month-day pairs without a year) found in the text, in the formats the artefacts use."""
    full, partial = set(), set()

    def add(year, month, day):
        try:
            full.add(date(int(year), int(month), int(day)))
        except ValueError:
            pass

    lowered = text.lower()
    for year, month, day in re.findall(r"\b(\d{4})-(\d{2})-(\d{2})\b", lowered):
        add(year, month, day)
    for day, month, year in re.findall(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b", lowered):
        add(year, month, day)
    for day, month, year in re.findall(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{MONTH_PATTERN}\.?,?\s+(\d{{4}})\b", lowered):
        add(year, MONTHS[month], day)
    for month, day, year in re.findall(rf"\b{MONTH_PATTERN}\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", lowered):
        add(year, MONTHS[month], day)
    # "15 to 21 September 2025": both days in the same month
    for first, second, month, year in re.findall(rf"\b(\d{{1,2}})\s*{RANGE_DASH}\s*(\d{{1,2}})\s+{MONTH_PATTERN}\.?\s+(\d{{4}})\b", lowered):
        add(year, MONTHS[month], first)
        add(year, MONTHS[month], second)
    # "27 Apr to 3 May 2026": the first date borrows the year
    for first, first_month, second, second_month, year in re.findall(
            rf"\b(\d{{1,2}})\s+{MONTH_PATTERN}\.?\s*{RANGE_DASH}\s*(\d{{1,2}})\s+{MONTH_PATTERN}\.?\s+(\d{{4}})\b", lowered):
        first_year = int(year) - (1 if MONTHS[first_month] > MONTHS[second_month] else 0)
        add(first_year, MONTHS[first_month], first)
        add(year, MONTHS[second_month], second)
    # day and month with no year after them
    for day, month in re.findall(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{MONTH_PATTERN}\b(?!\.?,?\s*\d{{4}})", lowered):
        partial.add((MONTHS[month], int(day)))
    for month, day in re.findall(rf"\b{MONTH_PATTERN}\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?!,?\s*\d{{4}})", lowered):
        partial.add((MONTHS[month], int(day)))
    return full, partial


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def relative(path: Path, base: Path) -> str:
    return str(path.relative_to(base)).replace("\\", "/")


# ---------------------------------------------------------------------------
# Loading the artefacts and the world
# ---------------------------------------------------------------------------

def load_materials() -> dict:
    """Everything the checks read: the exposed artefacts (doc and library), the world, the facts and the incident record."""
    arms_files = {"prompt_doc.md": read_text(cfg.ARMS_DOC_PATH)}
    for path in sorted(cfg.ARMS_LIBRARY_DIR.rglob("*")):
        if path.is_file():
            arms_files["library/" + relative(path, cfg.ARMS_LIBRARY_DIR)] = read_text(path)
    world_files = {relative(path, cfg.WORLD_DIR): read_text(path) for path in sorted(cfg.WORLD_DIR.rglob("*")) if path.is_file()}
    facts = yaml.safe_load(cfg.FACTS_PATH.read_text(encoding="utf-8"))
    incident_manifest = json.loads((cfg.INTERNAL_DIR / "incident_manifest.json").read_text(encoding="utf-8"))
    return {"arms": arms_files, "world": world_files, "facts": {fact["id"]: fact for fact in facts}, "incidents": incident_manifest}


def fact_ids_in_markers(text: str) -> tuple[set, list]:
    """Fact IDs named in `<!-- facts: ... -->` markers, and the tokens that are not well-formed IDs."""
    found, malformed = set(), []
    for match in FACT_MARKER.finditer(text):
        for token in re.split(r"[,\s]+", match.group(1).strip()):
            if not token:
                continue
            (found.add(token) if FACT_ID.fullmatch(token) else malformed.append(token))
    return found, malformed


def source_labels(text: str) -> set:
    labels = set()
    for match in SOURCE_MARKER.finditer(text):
        labels.update(token.strip() for token in match.group(1).split(",") if token.strip())
    return labels


def blocks_by_fact(text: str) -> dict:
    """Text carried under each fact ID: the heading above its marker (a section's name belongs to its facts), then the text
    from the marker to the next marker or heading."""
    carried: dict = {}
    for match in FACT_MARKER.finditer(text):
        following = text[match.end():]
        stops = [m.start() for m in (ANY_COMMENT.search(following), re.search(r"\n#{1,6}\s", following)) if m]
        headings = re.findall(r"^#{1,6}\s+.*$", text[:match.start()], flags=re.M)
        block = (headings[-1] + "\n" if headings else "") + (following[:min(stops)] if stops else following)
        for token in re.split(r"[,\s]+", match.group(1).strip()):
            if FACT_ID.fullmatch(token or ""):
                carried.setdefault(token, []).append(block)
    return carried


def sql_comment_fact_ids(text: str) -> set:
    """Fact IDs cited in comment lines of SQL templates and scripts."""
    cited = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") or stripped.startswith("#") or stripped.startswith('"""') or "# " in stripped:
            cited.update(FACT_ID.findall(line))
    return cited


# ---------------------------------------------------------------------------
# Rule 16: parity
# ---------------------------------------------------------------------------

def check_parity(materials: dict, record) -> dict:
    print("Arms: rule 16, parity between the doc and the library")
    arms, world, facts = materials["arms"], materials["world"], materials["facts"]
    doc_text = arms["prompt_doc.md"]
    library_markdown = {name: text for name, text in arms.items() if name.startswith("library/") and name.endswith(".md")}
    doc_ids, doc_bad = fact_ids_in_markers(doc_text)
    library_ids, library_bad = set(), []
    for text in library_markdown.values():
        ids, bad = fact_ids_in_markers(text)
        library_ids |= ids
        library_bad += bad
    record("R16", "every fact marker in the doc and the library is well-formed", not doc_bad and not library_bad, f"malformed: {doc_bad + library_bad}")
    record("R16", "the doc and the library carry the same set of world fact IDs", doc_ids == library_ids,
           f"doc {len(doc_ids)}, library {len(library_ids)}; only in doc {sorted(doc_ids - library_ids)}, only in library {sorted(library_ids - doc_ids)}")
    required = {fid for fid, fact in facts.items() if fact.get("parity_required")}
    record("R16", "both carry every parity-required fact in facts.yaml", required <= doc_ids and required <= library_ids,
           f"{len(required)} required; missing from doc {sorted(required - doc_ids)}, from library {sorted(required - library_ids)}")
    doc_sources = source_labels(doc_text)
    library_sources = set().union(*[source_labels(text) for text in library_markdown.values()])
    record("R16", "the doc and the library carry the same source labels (schema, request history, dictionary)", doc_sources == library_sources,
           f"doc {len(doc_sources)}, library {len(library_sources)}; difference {sorted(doc_sources ^ library_sources)}")
    # Content, not only the tag: the key values of each fact must sit in the text carried under its marker.
    doc_blocks = blocks_by_fact(doc_text)
    library_blocks: dict = {}
    for text in library_markdown.values():
        for fid, blocks in blocks_by_fact(text).items():
            library_blocks.setdefault(fid, []).extend(blocks)
    gaps = []
    for label, carried in (("doc", doc_blocks), ("library", library_blocks)):
        for fid in sorted(required):
            haystack = normalise_text(" ".join(carried.get(fid, []))).lower()
            for needle in facts[fid].get("must_contain", []):
                if needle.lower() not in haystack:
                    gaps.append(f"{label}:{fid} lacks '{needle}'")
    record("R16", "each artefact carries the key values of every fact it tags (facts.yaml must_contain, in the text under the marker)", not gaps,
           "; ".join(gaps[:6]) if gaps else f"{len(required)} facts x 2 artefacts")
    return {"doc_ids": doc_ids, "library_ids": library_ids, "doc_sources": doc_sources}


# ---------------------------------------------------------------------------
# Rule 17: provenance
# ---------------------------------------------------------------------------

def world_source_names(world: dict) -> set:
    names = {Path(name).name for name in world} | set(world)
    names |= {Path(name).stem for name in world if Path(name).name.startswith("REQ-D")}
    return names


def check_provenance_ids(materials: dict, record) -> None:
    arms, world, facts = materials["arms"], materials["world"], materials["facts"]
    marker_ids_in_world = set()
    for name, text in world.items():
        marker_ids_in_world |= fact_ids_in_markers(text)[0]
    required = {fid for fid, fact in facts.items() if fact.get("parity_required")}
    # facts.yaml also holds the schema-comment facts (not marked in world/ documents); the documents' markers are the curated ones.
    world_ids = marker_ids_in_world
    record("R17", "the fact IDs marked in the world documents are exactly the curated facts in facts.yaml (parity_required)", marker_ids_in_world == required,
           f"world markers {len(marker_ids_in_world)}, curated facts {len(required)}")
    cited, unmarked_comments = {}, []
    for name, text in arms.items():
        ids = fact_ids_in_markers(text)[0] if name.endswith(".md") else sql_comment_fact_ids(text)
        cited[name] = ids
        if name.endswith(".md"):
            for comment in ANY_COMMENT.findall(text):
                if not (FACT_MARKER.fullmatch(comment) or SOURCE_MARKER.fullmatch(comment)):
                    unmarked_comments.append(f"{name}: {comment[:50]}")
    unknown = {name: sorted(ids - world_ids) for name, ids in cited.items() if ids - world_ids}
    record("R17", "every fact ID cited anywhere in the doc or the library (markers, template headers, script comments) exists in world/", not unknown, str(unknown)[:300])
    record("R17", "the doc and the library contain no HTML comment other than a fact or source marker", not unmarked_comments, "; ".join(unmarked_comments[:4]))
    # Every source label must resolve to a file or a request in world/.
    names = world_source_names(world)
    labels = set()
    for text in arms.values():
        labels |= source_labels(text)
    unresolved = sorted(label for label in labels if label not in names)
    record("R17", "every source label in the doc and the library names a file or a request in world/", not unresolved,
           f"{len(labels)} labels; unresolved {unresolved[:6]}")
    # Template header facts must also sit in the library's markdown (a template cannot add a fact of its own).
    markdown_ids = set().union(*[ids for name, ids in cited.items() if name.startswith("library/") and name.endswith(".md")])
    only_in_code = {name: sorted(ids - markdown_ids) for name, ids in cited.items() if not name.endswith(".md") and ids - markdown_ids}
    record("R17", "facts cited in templates and scripts are all stated in the library's markdown", not only_in_code, str(only_in_code)[:300])
    # Reading requests: every REQ-D number the artefacts mention is one of the 40 dev requests.
    mentioned = set()
    for text in arms.values():
        mentioned |= set(re.findall(r"REQ-[A-Z]\d+", text))
    outside = sorted(item for item in mentioned if not re.fullmatch(r"REQ-D(0[1-9]|[1-3]\d|40)", item))
    record("R17", "the only request IDs in the doc and the library are REQ-D01 to REQ-D40", not outside, str(outside[:6]))


def incident_windows() -> list:
    """(id, first day, last day) of each incident's affected span, plus the day it was reloaded where there is one."""
    one, two = cfg.INCIDENT_DOUBLE_POST, cfg.INCIDENT_LOGIN_ORPHANS
    three, four = cfg.INCIDENT_STOCK_RELOAD, cfg.INCIDENT_CNC_MISLABEL
    return [("INC-1", one["week_start"], one["week_end"]), ("INC-2", two["start"], two["end"]),
            ("INC-3", three["week_ending"] - timedelta(days=6), three["week_ending"]), ("INC-4", four["start"], four["end"])]


def boundary_dates() -> set:
    """First and last day of each incident: banned outright (validate_world already proves none is in world/)."""
    one, two, three, four = (cfg.INCIDENT_DOUBLE_POST, cfg.INCIDENT_LOGIN_ORPHANS, cfg.INCIDENT_STOCK_RELOAD, cfg.INCIDENT_CNC_MISLABEL)
    return {one["week_start"], one["week_end"], two["start"], two["end"], three["week_ending"], four["start"], four["end"]}


def reload_dates() -> set:
    """The days the duplicated rows were loaded. An ordinary date elsewhere (a request received that day), so allowed if world/ has it."""
    return {date.fromisoformat(cfg.INCIDENT_DOUBLE_POST["reload_ts"][:10]), date.fromisoformat(cfg.INCIDENT_STOCK_RELOAD["reload_ts"][:10])}


def manifest_number_forms(manifest: dict) -> dict:
    """The counts and amounts the incidents left in the data, in the ways a writer would format them."""
    forms = {}
    for incident, details in manifest.items():
        for key, value in details.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or key == "store_id":
                continue
            candidates = [value, value * 2] if key.startswith("duplicated_lines") else [value]
            for number in candidates:
                shown = {f"{number:,.2f}", f"{number:.2f}"} if isinstance(number, float) else {f"{number:,}", str(number)}
                for text in shown:
                    forms[text] = f"{incident} {key} ({number})"
    forms[str(cfg.INCIDENT_DOUBLE_POST["store_id"])] = "INC-1 store id"
    return forms


def context(text: str, start: int, end: int, width: int = 50) -> str:
    return normalise_text(text[max(0, start - width):end + width])


def check_incident_secrecy(connection, materials: dict, record) -> None:
    print("Arms: rule 17, the four undocumented incidents stay out of both artefacts")
    arms, world, manifest = materials["arms"], materials["world"], materials["incidents"]

    # 1. Keywords, the same list that keeps the incidents out of world/ (validate_world), and ISO / long-form dates in it.
    hits = []
    tokens = validate_world.incident_tokens()
    for name, text in arms.items():
        lowered = text.lower()
        for token in tokens:
            if token in lowered:
                hits.append(f"{name}: '{token}'")
    record("R17", "no incident keyword or incident boundary date from validate_world.incident_tokens() in the doc or the library", not hits, "; ".join(hits[:6]))

    # 2. Specific dates. Boundary dates banned outright (as full dates and as day-month); any other date inside an
    #    incident window must already appear in world/ (a request-history date, say), or the builder got it by querying.
    world_dates = set()
    for text in world.values():
        world_dates |= parse_dates(text)[0]
    banned_full = boundary_dates()
    banned_partial = {(d.month, d.day) for d in banned_full}
    windows = incident_windows()
    date_hits, window_hits = [], []
    for name, text in arms.items():
        full, partial = parse_dates(text)
        for found in sorted(full):
            if found in banned_full:
                date_hits.append(f"{name}: {found.isoformat()}")
            elif (any(first <= found <= last for _, first, last in windows) or found in reload_dates()) and found not in world_dates:
                window_hits.append(f"{name}: {found.isoformat()}")
        for month, day in sorted(partial):
            if (month, day) in banned_partial:
                date_hits.append(f"{name}: day-month {day}/{month}")
    record("R17", "no incident boundary date (full or day-month) appears in the doc or the library", not date_hits, "; ".join(date_hits[:6]))
    record("R17", "no other date inside an incident window, and no reload date, appears unless world/ already carries it", not window_hits, "; ".join(window_hits[:6]))

    # 3. Store, counts and amounts the incidents left behind.
    number_hits = []
    for name, text in arms.items():
        for form, label in manifest_number_forms(manifest).items():
            for match in re.finditer(rf"(?<![\d.,]){re.escape(form)}(?![\d]|,\d|\.\d)", text):
                number_hits.append(f"{name}: '{form}' = {label}: ...{context(text, match.start(), match.end())}...")
    record("R17", "no incident store id, row count or amount (418 / 836 / 7,439 / 10,390.53 and the rest) appears in the doc or the library", not number_hits, "; ".join(number_hits[:4]))

    # 4. Fiscal-week combinations of the windows, for example "FY2025/26 week 21".
    week_hits = []
    for incident, first, last in windows:
        rows = connection.execute("SELECT DISTINCT fiscal_year, fiscal_week FROM dim_date WHERE calendar_date BETWEEN ? AND ?", [first, last]).fetchall()
        for fiscal_year, week in rows:
            short = fiscal_year.replace("FY20", "FY")
            patterns = [rf"({re.escape(fiscal_year)}|{re.escape(short)})\s*[,:]?\s*(fiscal\s+)?(week|wk|w)\s*0?{week}\b",
                        rf"(week|wk|w)\s*0?{week}\s*(of|in)\s*({re.escape(fiscal_year)}|{re.escape(short)})"]
            for name, text in arms.items():
                for pattern in patterns:
                    for match in re.finditer(pattern, text, flags=re.I):
                        week_hits.append(f"{name}: {incident} {fiscal_year} week {week}: ...{context(text, match.start(), match.end(), 30)}...")
    record("R17", "no fiscal-week reference to an incident week (for example FY2025/26 week 21) appears in the doc or the library", not week_hits, "; ".join(week_hits[:4]))

    # 5. Phrasing that would point at a planted problem.
    phrase_hits = []
    for name, text in arms.items():
        for pattern, label in INCIDENT_PHRASES:
            for match in re.finditer(pattern, text, flags=re.I):
                snippet = context(text, match.start(), match.end(), 40)
                if not any(allowed in snippet.lower() for allowed in ALLOWED_GENERIC) or "116" in snippet:
                    phrase_hits.append(f"{name}: {label}: ...{snippet}...")
    record("R17", "no phrasing that points at an incident (till re-sync, orders without a member key, channel key disagreeing with fulfilment type, West stock loaded twice)", not phrase_hits, "; ".join(phrase_hits[:4]))

    note_tokens = [t for t in tokens if t in (materials["notes_text"] or "").lower()]
    print(f"  note: build_notes.md and tests/ in arms/ are outside the arm-facing set and name the incidents the builder found "
          f"({len(note_tokens)} keyword hits there); they are not handed to any arm and are not published as part of the library.")


def check_script_is_generic(connection, materials: dict, record) -> None:
    """The builder says query_check.py catches the incidents through generic checks. Confirm it, statically and by test."""
    print("Arms: rule 17, query_check.py is generic")
    check_script = cfg.ARMS_LIBRARY_DIR / "query-check" / "scripts" / "query_check.py"
    source = read_text(check_script)
    tree = ast.parse(source)
    allowed_numbers = {900, 999}                       # REG-STORE-900 and REG-STORE-999, both in world/
    world_dates = set()
    for text in materials["world"].values():
        world_dates |= parse_dates(text)[0]
    windows = incident_windows()
    suspicious, table_names = [], set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value, int) and not isinstance(value, bool) and abs(value) >= 100 and value not in allowed_numbers:
                suspicious.append(f"number {value} (line {node.lineno})")
            if isinstance(value, str):
                # A date in a message is fine if world/ states it (the migration date, say) and it is not in an incident window.
                for found in parse_dates(value)[0]:
                    inside = any(first <= found <= last for _, first, last in windows) or found in boundary_dates() | reload_dates()
                    if inside or found not in world_dates:
                        suspicious.append(f"date {found} in a string (line {node.lineno}): {value[:50]}")
                table_names |= set(re.findall(r"\b(?:fact|dim|ref|rpt|stg|bak|tmp)_[a-z_]+\b", value))
    ddl = materials["world"]["schema_ddl.sql"].lower()
    not_in_schema = sorted(name for name in table_names if name not in ddl and not name.endswith("_"))
    record("R17", "query_check.py code has no store id, date or count literal beyond store 900 and 999", not suspicious, "; ".join(suspicious[:5]))
    stock_or_campaign = sorted(name for name in table_names if name in ("fact_stock_week", "fact_campaign_exposure", "dim_channel"))
    record("R17", "query_check.py names no table, and no column, tied to one incident (tables it reads: " + ", ".join(sorted(table_names)) + ")",
           not not_in_schema and not stock_or_campaign, f"not in the world schema: {not_in_schema}; incident tables: {stock_or_campaign}")

    # By test: a double-post planted at a store and a week that belong to no incident.
    plant_store, start, end = cfg.ARMS_PLANT_STORE_ID, cfg.ARMS_PLANT_START, cfg.ARMS_PLANT_END
    overlaps_incident = any(first <= end and start <= last for _, first, last in incident_windows()) or plant_store == cfg.INCIDENT_DOUBLE_POST["store_id"]
    record("R17", "the planted test double-post sits at a store and in a week that belong to no incident", not overlaps_incident, f"store {plant_store}, {start} to {end}")
    outcomes = {}
    for label, source_table in (("clean", "fact_sales_line"),
                                ("planted", f"(SELECT * FROM fact_sales_line UNION ALL SELECT * FROM fact_sales_line "
                                            f"WHERE store_key IN (SELECT store_key FROM dim_store WHERE store_id = {plant_store}) "
                                            f"AND sale_date BETWEEN DATE '{start}' AND DATE '{end}')")):
        control_sql = (f"SELECT l.sale_date AS business_date, s.store_id, SUM(l.net_amount) AS net_sales_before_returns FROM {source_table} l "
                       f"JOIN dim_store s ON s.store_key = l.store_key JOIN dim_product p ON p.product_key = l.product_key "
                       f"WHERE s.store_id = {plant_store} AND p.category <> 'ZZ Test' AND l.sale_date BETWEEN DATE '{start}' AND DATE '{end}' GROUP BY 1, 2")
        grain_sql = (f"SELECT l.receipt_id, l.line_no FROM {source_table} l JOIN dim_store s ON s.store_key = l.store_key "
                     f"WHERE s.store_id = {plant_store} AND l.sale_date BETWEEN DATE '{start}' AND DATE '{end}'")
        control = run_check(check_script, ["--sql", control_sql, "--grain", "business_date,store_id", "--start", str(start), "--end", str(end), "--control",
                                           "--control-measure", "net_sales_before_returns", "--value-col", "net_sales_before_returns", "--control-stores", str(plant_store)])
        grain = run_check(check_script, ["--sql", grain_sql, "--grain", "receipt_id,line_no"])
        outcomes[label] = (section_status(control, "Control total"), section_status(grain, "Duplicate keys"))
    record("R17", "query_check.py passes the untouched week at store 118 (control total and source grain)", outcomes["clean"] == ("PASS", "PASS"), str(outcomes["clean"]))
    record("R17", "query_check.py flags a double-post planted at store 118, 1 to 7 June 2026, against the control total and at the source grain", outcomes["planted"] == ("FAIL", "FAIL"), str(outcomes["planted"]))


def run_check(script: Path, arguments: list) -> dict:
    command = [sys.executable, "-I", str(script), str(cfg.WAREHOUSE_PATH), "--json"] + arguments
    outcome = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    try:
        return json.loads(outcome.stdout)
    except json.JSONDecodeError:
        return {"checks": [], "error": (outcome.stderr or outcome.stdout)[:200]}


def section_status(report: dict, section_prefix: str) -> str:
    statuses = [c["status"] for c in report.get("checks", []) if c["section"].startswith(section_prefix) and c["status"] in ("PASS", "FAIL")]
    return "FAIL" if "FAIL" in statuses else ("PASS" if statuses else report.get("error", "none"))


# ---------------------------------------------------------------------------
# Rule 18: leakage
# ---------------------------------------------------------------------------

def sql_tokens(text: str) -> list[str]:
    text = re.sub(r"--[^\n]*", " ", text)
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.findall(r"[a-z_][a-z_0-9.]*|\d+(?:\.\d+)?|'[^']*'|[^\s\w]", text.lower())


def token_runs(text: str) -> set:
    return ngram_set(sql_tokens(text), cfg.ARMS_SQL_TOKEN_RUN)


def statements(text: str) -> list[str]:
    parts = [re.sub(r"--[^\n]*", " ", part) for part in re.split(r";\s*\n", text)]
    return [normalise_text(part).rstrip(";").lower() for part in parts if len(normalise_text(part)) > 60]


def check_request_leakage(materials: dict, record) -> None:
    print("Arms: rule 18, no test request in world/, the doc or the library")
    requests = json.loads((cfg.REQUESTS_DIR / "test_requests.json").read_text(encoding="utf-8"))
    pools = {"world/" + name: text for name, text in materials["world"].items()}
    pools.update({("doc" if name == "prompt_doc.md" else name): text for name, text in materials["arms"].items()})
    id_hits = [f"{name}: {found}" for name, text in pools.items() for found in set(re.findall(r"REQ-T\d+", text))]
    record("R18", "no test request ID appears in world/, the doc or the library", not id_hits, "; ".join(id_hits[:5]))
    prepared = {name: (normalise_text(re.sub(r"[^\w\s']", " ", text.lower())), ngram_set(words(text), 5)) for name, text in pools.items()}
    segments = []
    for name, text in pools.items():
        for line in text.splitlines():
            for piece in [line] + re.split(r"(?<=[.?!])\s+", line):
                if len(words(piece)) >= cfg.ARMS_LEAK_SEGMENT_MIN_WORDS:
                    segments.append((name, piece))
    segment_grams = [(name, build_requests.trigrams(piece)) for name, piece in segments]
    # worst[group][measure] = (share, request id, file or segment), where group is "world" or "arms"
    worst = {group: {"five": (0.0, "", ""), "segment": (0.0, "", "")} for group in ("world", "arms")}
    exact = []
    for request in requests:
        text = request["request_text"]
        wanted = normalise_text(re.sub(r"[^\w\s']", " ", text.lower()))
        request_five = ngram_set(words(text), 5)
        for name, (flat, five) in prepared.items():
            group = "world" if name.startswith("world/") else "arms"
            if wanted in flat:
                exact.append(f"{request['id']} in {name}")
            if request_five:
                share = len(request_five & five) / len(request_five)
                if share > worst[group]["five"][0]:
                    worst[group]["five"] = (share, request["id"], name)
        request_three = build_requests.trigrams(text)
        for name, piece_three in segment_grams:
            group = "world" if name.startswith("world/") else "arms"
            share = len(request_three & piece_three) / max(1, min(len(request_three), len(piece_three)))    # build_requests.overlap, with the grams computed once
            if share > worst[group]["segment"][0]:
                worst[group]["segment"] = (share, request["id"], name)

    def describe(found: tuple) -> str:
        return f"worst {found[0]:.0%} ({found[1]} in {found[2][:70]})"

    record("R18", "no test request appears word for word in world/, the doc or the library", not exact, "; ".join(exact[:5]))
    for group, label in (("arms", "the doc or the library"), ("world", "world/")):
        record("R18", f"no test request shares more than {cfg.ARMS_LEAK_FILE_FIVEGRAM_THRESHOLD:.0%} of its word 5-grams with any one file of {label}",
               worst[group]["five"][0] <= cfg.ARMS_LEAK_FILE_FIVEGRAM_THRESHOLD, describe(worst[group]["five"]))
        record("R18", f"no line or sentence of {cfg.ARMS_LEAK_SEGMENT_MIN_WORDS} words or more in {label} overlaps a test request by more than {cfg.DEV_NGRAM_LEAK_THRESHOLD:.0%} (word 3-grams, as in the dev-history check)",
               worst[group]["segment"][0] <= cfg.DEV_NGRAM_LEAK_THRESHOLD, describe(worst[group]["segment"]))


def check_reference_leakage(materials: dict, record) -> None:
    print("Arms: rule 18, no reference SQL or key figure in the doc or the library")
    reference_files = {path.stem: read_text(path) for path in sorted((cfg.KEY_DIR / "reference_sql").glob("*.sql"))}
    arm_sql = {}
    for name, text in materials["arms"].items():
        if name.endswith(".sql"):
            arm_sql[name] = text
        elif name.endswith(".md"):
            for number, block in enumerate(SQL_FENCE.findall(text), 1):
                arm_sql[f"{name} [sql block {number}]"] = block
    dev_sql = [block for name, text in materials["world"].items() if name.startswith("request_history/REQ-D") for block in SQL_FENCE.findall(text)]
    dev_runs = set().union(*[token_runs(block) for block in dev_sql])
    arm_runs = {name: token_runs(text) for name, text in arm_sql.items()}
    arm_statements = {name: normalise_text(re.sub(r"--[^\n]*", " ", text)).lower() for name, text in arm_sql.items()}

    whole, share_hits, unexplained_hits = [], [], []
    worst_share, worst_unexplained, worst_dev = (0.0, "", ""), (0.0, "", ""), (0.0, "")
    for question, text in reference_files.items():
        reference_runs = token_runs(text)
        if not reference_runs:
            continue
        for statement in statements(text):
            for name, flat in arm_statements.items():
                if statement in flat:
                    whole.append(f"{question} in {name}")
        dev_share = len(reference_runs & dev_runs) / len(reference_runs)
        if dev_share > worst_dev[0]:
            worst_dev = (dev_share, question)
        for name, runs_found in arm_runs.items():
            shared = reference_runs & runs_found
            share = len(shared) / len(reference_runs)
            unexplained = len(shared - dev_runs) / len(reference_runs)
            if share > worst_share[0]:
                worst_share = (share, question, name)
            if unexplained > worst_unexplained[0]:
                worst_unexplained = (unexplained, question, name)
            if share > cfg.ARMS_SQL_LEAK_THRESHOLD:
                share_hits.append(f"{question} in {name} ({share:.0%})")
            if unexplained > cfg.ARMS_SQL_UNEXPLAINED_LIMIT:
                unexplained_hits.append(f"{question} in {name} ({unexplained:.0%})")
    record("R18", f"no whole reference statement (reference, accepted alternative or naive variant, {len(reference_files)} key files) appears in the doc's or the library's SQL", not whole, "; ".join(whole[:5]))
    record("R18", f"no template or SQL block reproduces more than {cfg.ARMS_SQL_LEAK_THRESHOLD:.0%} of a reference query's {cfg.ARMS_SQL_TOKEN_RUN}-token runs",
           not share_hits, f"worst {worst_share[0]:.0%} ({worst_share[1]} in {worst_share[2]}); the dev history alone reaches {worst_dev[0]:.0%} ({worst_dev[1]})")
    record("R18", f"what a template shares with a reference query and no dev query explains stays under {cfg.ARMS_SQL_UNEXPLAINED_LIMIT:.0%} of its token runs",
           not unexplained_hits, f"worst {worst_unexplained[0]:.0%} ({worst_unexplained[1]} in {worst_unexplained[2]}); {len(arm_sql)} SQL texts checked")
    # The key's own figures: a number the key holds to the cent must not be printed in either artefact.
    key = json.loads((cfg.KEY_DIR / "key.json").read_text(encoding="utf-8"))
    figures = set()

    def collect(node):
        if isinstance(node, dict):
            for item_key, item in node.items():
                if item_key == "rows":
                    for row in item:
                        for value in row:
                            if isinstance(value, (int, float)) and not isinstance(value, bool) and abs(value) >= 100 and round(value, 2) != int(round(value, 2)):
                                figures.add(round(float(value), 2))
                else:
                    collect(item)
        elif isinstance(node, list):
            for item in node:
                collect(item)

    collect(key)
    found = []
    for name, text in materials["arms"].items():
        for token in re.findall(r"\d[\d,]*\.\d+", text):
            try:
                number = round(float(token.replace(",", "")), 2)
            except ValueError:
                continue
            if number in figures:
                found.append(f"{name}: {token}")
    record("R18", "no figure with decimals from the key's results appears in the doc or the library", not found, f"{len(figures)} key figures; hits {found[:5]}")


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def run(connection, record) -> None:
    print("Arms: the prompt doc and the skills library (rules 16 to 18)")
    if not (cfg.ARMS_DOC_PATH.exists() and cfg.ARMS_LIBRARY_DIR.exists()):
        record("A0", "arm materials exist in arms/ (prompt_doc.md and library/)", False, f"missing under {cfg.ARMS_DIR}")
        return
    materials = load_materials()
    notes_path, tests_dir = cfg.ARMS_DIR / "build_notes.md", cfg.ARMS_DIR / "tests"
    materials["notes_text"] = "\n".join([read_text(notes_path)] + [read_text(p) for p in sorted(tests_dir.rglob("*")) if p.is_file() and p.suffix in (".py", ".txt", ".md")]) if notes_path.exists() else ""
    record("A0", "arms/ holds the doc, a library of skills with SKILL.md files, build_notes.md and tests/",
           len([n for n in materials["arms"] if n.endswith("/SKILL.md")]) >= 8 and notes_path.exists() and tests_dir.exists(),
           f"{len([n for n in materials['arms'] if n.endswith('/SKILL.md')])} skills, {len(materials['arms'])} files")
    check_parity(materials, record)
    check_provenance_ids(materials, record)
    check_incident_secrecy(connection, materials, record)
    check_script_is_generic(connection, materials, record)
    check_request_leakage(materials, record)
    check_reference_leakage(materials, record)


def self_test(connection) -> int:
    """Do the checks have teeth? Plant a known fault in a scratch copy of arms/ and require the matching check to fail.

    Nothing in arms/ is touched: each fault goes into a fresh copy in the system temp folder, which is removed afterwards.
    """
    import contextlib
    import io
    import shutil
    import tempfile

    requests = json.loads((cfg.REQUESTS_DIR / "test_requests.json").read_text(encoding="utf-8"))
    request_words = requests[0]["request_text"].split()
    middle = len(request_words) // 2
    near_copy = " ".join(request_words[:middle] + ["somewhat"] + request_words[middle + 1:])
    reference_text = read_text(sorted((cfg.KEY_DIR / "reference_sql").glob("*.sql"))[0])
    reference_statement = re.sub(r"--[^\n]*\n", "", reference_text).split(";")[0].strip() + ";"
    key = json.loads((cfg.KEY_DIR / "key.json").read_text(encoding="utf-8"))
    figure = next(value for entry in key["entries"] for row in entry["reference"]["result"]["rows"] for value in row
                  if isinstance(value, float) and value > 1000 and round(value, 2) != int(value))

    def append(relative_path, addition):
        def mutate(root):
            path = root / relative_path
            path.write_text(read_text(path) + "\n" + addition + "\n", encoding="utf-8")
        return mutate

    def replace(relative_path, old, new, everywhere=False):
        def mutate(root):
            path = root / relative_path
            text = read_text(path)
            assert old in text, f"{old!r} not found in {relative_path}"
            path.write_text(text.replace(old, new) if everywhere else text.replace(old, new, 1), encoding="utf-8")
        return mutate

    def scrub_content(fact_id):
        """Keep the fact's tag in the doc but blank its longest key phrase wherever it sits under that tag."""
        needle = max(materials_for_test["facts"][fact_id]["must_contain"], key=len)

        def mutate(root):
            path = root / "prompt_doc.md"
            text = read_text(path)
            for match in reversed(list(FACT_MARKER.finditer(text))):
                if fact_id in re.split(r"[,\s]+", match.group(1)):
                    following = text[match.end():]
                    stops = [m.start() for m in (ANY_COMMENT.search(following), re.search(r"\n#{1,6}\s", following)) if m]
                    end = match.end() + (min(stops) if stops else len(following))
                    text = text[:match.end()] + re.sub(re.escape(needle), "xxxx", text[match.end():end], flags=re.I) + text[end:]
            path.write_text(text, encoding="utf-8")
        return mutate

    materials_for_test = load_materials()
    known_dates = set()
    for text in materials_for_test["world"].values():
        known_dates |= parse_dates(text)[0]
    window_day = next(first + timedelta(days=offset) for _, first, last in incident_windows() for offset in range((last - first).days + 1)
                      if first + timedelta(days=offset) not in known_dates and first + timedelta(days=offset) not in boundary_dates())
    window_text = f"{window_day.day} {window_day.strftime('%B %Y')}"
    script ="library/query-check/scripts/query_check.py"
    faults = [
        ("a fact dropped from the doc only", replace("prompt_doc.md", "DEF-UPLIFT", "DEF-NET-SALES", everywhere=True), "same set of world fact IDs"),
        ("an invented fact ID in the library", append("library/stock/SKILL.md", "<!-- facts: DEF-INVENTED -->\nA made-up rule."), "exists in world/"),
        ("a fact tag kept but its key phrase removed from the doc", scrub_content("DEF-UPLIFT"), "carries the key values"),
        ("store 116 posted twice, in words", append("prompt_doc.md", "Store 116 had its receipts posted twice."), "phrasing that points at an incident"),
        ("an incident week named by date", append("library/warehouse-map/SKILL.md", "Look at 15 September 2025 and 21 September 2025."), "incident boundary date"),
        ("a date inside an incident window that world/ never mentions", append("library/warehouse-map/SKILL.md", f"Check the figures for {window_text}."), "inside an incident window"),
        ("orders that lost their member key, in words only", append("prompt_doc.md", "Some web orders lost their member key, so check member share."), "phrasing that points at an incident"),
        ("an incident row count", append("library/stock/SKILL.md", "7,439 rows were repeated."), "row count"),
        ("an incident fiscal week", append("prompt_doc.md", "Check FY2025/26 week 21 first."), "fiscal-week reference"),
        ("a test request copied into the library", append("library/stock/SKILL.md", requests[0]["request_text"]), "word for word"),
        ("a test request lightly reworded in the doc", append("prompt_doc.md", near_copy), "5-grams"),
        ("a reference query pasted into a template", append("library/stock/templates/weeks_of_cover.sql", reference_statement), "whole reference statement"),
        ("a key figure printed in the doc", append("prompt_doc.md", f"The answer is {figure:,.2f}."), "figure with decimals"),
        ("store 116 hard-coded in the check script", replace(script, "CONTROL_MEASURES =", "SPECIAL_STORE = 116\nCONTROL_MEASURES ="), "no store id, date or count literal"),
        ("the duplicate-key check disabled", replace(script, "    if not duplicated:\n", "    if True:\n"), "flags a double-post"),
    ]
    missed = []
    original = (cfg.ARMS_DIR, cfg.ARMS_DOC_PATH, cfg.ARMS_LIBRARY_DIR)
    for label, mutate, expected in faults:
        with tempfile.TemporaryDirectory(prefix="arms_selftest_") as scratch:
            root = Path(scratch) / "arms"
            shutil.copytree(original[0], root)
            mutate(root)
            cfg.ARMS_DIR, cfg.ARMS_DOC_PATH, cfg.ARMS_LIBRARY_DIR = root, root / "prompt_doc.md", root / "library"
            outcomes = []
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    run(connection, lambda rule, name, passed, detail="": outcomes.append((rule, name, passed, detail)))
            finally:
                cfg.ARMS_DIR, cfg.ARMS_DOC_PATH, cfg.ARMS_LIBRARY_DIR = original
        failed = [name for _, name, passed, _ in outcomes if not passed]
        caught = bool(failed) if expected is None else any(expected in name for name in failed)
        print(f"  [{'CAUGHT' if caught else 'MISSED'}] {label}" + (f"  -> {failed[0][:90]}" if failed else ""), flush=True)
        if not caught:
            missed.append(label)
    print(f"\n{len(faults) - len(missed)} of {len(faults)} planted faults caught")
    return 0 if not missed else 1


def main() -> int:
    import duckdb
    if "--self-test" in sys.argv:
        if not cfg.WAREHOUSE_PATH.exists():
            print(f"ERROR: {cfg.WAREHOUSE_PATH} not found; run generate_warehouse.py first.")
            return 1
        connection = duckdb.connect(str(cfg.WAREHOUSE_PATH), read_only=True)
        try:
            print("Arms: self-test, planting faults in a scratch copy of arms/")
            return self_test(connection)
        finally:
            connection.close()
    results = []

    def record(rule: str, name: str, passed: bool, detail: str = "") -> None:
        results.append(passed)
        print(f"  [{'PASS' if passed else 'FAIL'}] {rule} {name}" + (f"  ({detail})" if detail else ""), flush=True)

    if not cfg.WAREHOUSE_PATH.exists():
        print(f"ERROR: {cfg.WAREHOUSE_PATH} not found; run generate_warehouse.py first.")
        return 1
    connection = duckdb.connect(str(cfg.WAREHOUSE_PATH), read_only=True)
    try:
        run(connection, record)
    finally:
        connection.close()
    print(f"\n{sum(results)} of {len(results)} arm checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
