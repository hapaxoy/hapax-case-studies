"""mark.py (Phase 6): marks the 1,800 full-run answers against the answer key. The only reader of data/key/.

    python code/mark.py                                   # strict marking; writes data/analysis/marked_runs.jsonl and the adjudication files
    python code/mark.py --adjudication data/analysis/adjudication_decisions.json    # apply the arm-blind adjudication decisions
    python code/mark.py --self-check                      # key against itself: reference correct, accepted results correct, naive variants wrong

Built on the pilot marker (code/pilot_marking.py, marker 5) and its lessons from the pilots. Marker version 6. What it does, in the order a run meets it:

 1. Result correctness. The returned table is compared with the key's reference result and every result the key accepts:
    columns matched by their values, not their names; rows order-insensitive unless the request asks for an order (the key's `ordered`);
    0.1% relative tolerance, 0.1 percentage points on percentages (the key's unit `pct`), an absolute floor of half a cent.
    No answer = status not ok. A table whose rows differ in width from its columns is wrong.
 2. Which columns an answer must carry. The required-flag proposal (data/key/required_flags_proposal.json) is adopted: a request that
    asks for one rate need not carry the sales totals behind it (LFL, return rate, league table); a request that lists figures needs
    all of them. Dimension columns (what each row is) are always required.
 3. Shapes that carry the same numbers (the pilot's lessons, each switchable, see FEATURES, and each measured in the report):
    - total rows are ignored when the key has none; a one-figure answer may sit on a total row, never on a breakdown row;
    - zero-filled padding rows are ignored (a row whose required measures are all zero or empty), only where the table has row labels;
    - IDs or names: a column of store names or product names is read as the store_id or sku it names (any version of the name);
    - long or wide: months in one column with a value column carry the same numbers as one column per month (REQ-T04, REQ-T27);
    - fused fiscal labels: "FY2025/26 P07", "P7", "Q3", "W22" are read as a fiscal year plus a whole number (marker 5, extended to bare labels);
    - rounding: a column the agent rounded to whole numbers or one decimal passes if each value is the key's value correctly rounded.
    What stays strict: every number outside tolerance, a fraction written for a percentage, a missing required column, a missing row,
    an extra non-zero row, the order of a ranked list, and every trap reading (calendar-date comparisons, units for value, cancelled
    orders, the sale-date category, the web shop dropped or ranked as a store, and so on).
 4. The accepted alternatives and interpretations in the key (widened after the 15 Oct review). A result that matches one is correct
    without the answer having to name it, except in the ambiguous class (REQ-T14, T20, T43, T45, T54), where the `assumptions` field must
    also pass the keyword rule of the reading the result matches.
 5. "Fix or flag" for the undocumented class (REQ-T12, T16, T42, T55; decided 15 Oct): (a) the incident-free number, with or
    without a warning; (b) the published number with `caveats` passing the key's keyword rule. The two are reported separately. The
    published number with no warning is wrong. The same published-with-caveat rule applies to the ambiguous readings that reach
    last year's double-posted week (T14 reading 3, T20 readings 3 and 4).
 6. Error attribution. A wrong result is matched against the request's naive variants and labelled by trap; no match = "other".
 7. Arm-blind adjudication. Where a result matches an accepted reading but the keyword rule fails, or the rule passes in a way worth a
    second look, the run goes into data/analysis/adjudication_blind.md with the arm, model and run id hidden (the map is a separate file
    that is not read until the decisions are made). Marking is strict (the keyword rule alone) until a decisions file is applied.

Reads: data/key/key.json, data/key/required_flags_proposal.json, data/analysis/collected_runs.jsonl, the warehouse (read only, for the
store and product names). Writes only into data/analysis/. It calls no model.
"""
from __future__ import annotations

import argparse
import collections
import copy
import itertools
import json
import random
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional

CASE_ROOT = Path(__file__).resolve().parent.parent
KEY_PATH = CASE_ROOT / "data" / "key" / "key.json"
PROPOSAL_PATH = CASE_ROOT / "data" / "key" / "required_flags_proposal.json"
WAREHOUSE_PATH = CASE_ROOT / "data" / "warehouse" / "tuomimetsa.duckdb"
COLLECTED_PATH = CASE_ROOT / "data" / "analysis" / "collected_runs.jsonl"
OUT_DIR = CASE_ROOT / "data" / "analysis"

MARKER_VERSION = "6"
RELATIVE_TOLERANCE = 0.001          # 0.1 %
PERCENT_POINT_TOLERANCE = 0.1       # 0.1 percentage points
ABSOLUTE_FLOOR = 0.005              # half a cent: a value a few cents out from rounding passes
MAX_COLUMN_ASSIGNMENTS = 400
SEED = 42

# Every leniency of item 3 above, so the report can say how many runs each one decided.
FEATURES = frozenset({"supporting_omitted", "totals", "zero_rows", "names_for_ids", "month_long", "fused_label", "agent_rounding", "alternatives"})

TOTAL_LABEL = re.compile(r"^\s*(grand\s+)?total\b|^\s*all(\s|$)|\btotal\s*$", re.IGNORECASE)
FUSED_FISCAL_LABEL = re.compile(r"^\s*(?:FY\s*(\d{4}/\d{2})\s*[-_:,]?\s*)?(?:P|Q|W|Period|Quarter|Week)\s*0*(\d{1,2})\s*$", re.IGNORECASE)
MONTH_PATTERNS = [(8, re.compile(r"\baug(?:ust)?\b|\b2024[-/ ]?0?8\b|^0?8$", re.IGNORECASE)),
                  (9, re.compile(r"\bsep(?:t(?:ember)?)?\b|\b2024[-/ ]?0?9\b|^0?9$", re.IGNORECASE))]


# ---------------------------------------------------------------------------
# Cells
# ---------------------------------------------------------------------------

def repair_text(value: str) -> str:
    """Strip, normalise Unicode, and undo the one mojibake the hx tools' previews show (UTF-8 read as cp1252)."""
    text = unicodedata.normalize("NFC", str(value)).strip()
    if "Ã" in text or "Â" in text:
        try:
            repaired = text.encode("cp1252").decode("utf-8")
            text = unicodedata.normalize("NFC", repaired)
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return text


def to_number(value: Any) -> Optional[float]:
    """A cell as a float if it is a number or a plain numeric string; None otherwise (booleans are not numbers)."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"[-+]?\d+(\.\d+)?", text):
            return float(text)
    return None


def decimals_of(value: Any) -> Optional[int]:
    """Number of decimal places a numeric cell is written with (29.2 -> 1, 29 -> 0), None if not numeric."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        # normalised, so 2796.0 counts as a whole number and 29.20 as one decimal
        exponent = Decimal(str(value).strip()).normalize().as_tuple().exponent
    except (InvalidOperation, ValueError):
        return None
    return max(0, -exponent) if isinstance(exponent, int) else None


def column_decimals(values: list) -> Optional[int]:
    """The coarsest-to-finest decimals of a column the agent rounded: the maximum decimals over its numeric cells, or None if the
    column is not all numeric. Only 0 or 1 count as 'rounded' (see cells_match)."""
    found = [decimals_of(v) for v in values if v is not None]
    if not found or any(d is None for d in found):
        return None
    return max(found)


@dataclass(frozen=True)
class ColumnRule:
    percent: bool = False          # compare within 0.1 percentage points as well as 0.1 %
    got_decimals: Optional[int] = None   # decimals the agent's column is written with, when it may have rounded it
    allow_rounding: bool = False


def cells_match(expected: Any, got: Any, rule: ColumnRule) -> bool:
    if expected is None or got is None:
        return expected is None and got is None
    if isinstance(expected, bool) or isinstance(got, bool):
        return isinstance(expected, bool) and isinstance(got, bool) and expected == got
    expected_number = to_number(expected) if not isinstance(expected, str) else None
    if expected_number is not None:
        got_number = to_number(got)
        if got_number is None:
            return False
        gap = abs(expected_number - got_number)
        if rule.percent and gap <= PERCENT_POINT_TOLERANCE + 1e-9:
            return True
        if gap <= max(RELATIVE_TOLERANCE * abs(expected_number), ABSOLUTE_FLOOR):
            return True
        if rule.allow_rounding and rule.got_decimals is not None and rule.got_decimals <= 1:
            digits = rule.got_decimals
            return abs(round(expected_number, digits) - got_number) < 1e-9
        return False
    expected_text = repair_text(expected)
    got_text = repair_text(got) if not isinstance(got, (int, float)) else (str(int(got)) if float(got).is_integer() else str(got))
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", expected_text):
        return got_text[:10] == expected_text
    return expected_text.casefold() == got_text.casefold()


def sort_key(value: Any) -> tuple:
    if value is None:
        return (3, 0.0, "")
    number = to_number(value) if not isinstance(value, str) else None
    if number is not None:
        return (1, number, "")
    return (2, 0.0, repair_text(value).casefold())


def column_covers(expected_values: list, got_values: list, rule: ColumnRule) -> bool:
    """Does the returned column hold every expected value (each matched to its own cell)? Extra cells are allowed here; whether extra
    rows are acceptable is decided by the caller."""
    if len(got_values) < len(expected_values):
        return False
    unused = sorted(got_values, key=sort_key)
    for value in sorted(expected_values, key=sort_key):
        for position, candidate in enumerate(unused):
            if cells_match(value, candidate, rule):
                del unused[position]
                break
        else:
            return False
    return True


def is_zero_or_empty(value: Any) -> bool:
    if value is None:
        return True
    number = to_number(value)
    if number is not None:
        return abs(number) <= ABSOLUTE_FLOOR
    return isinstance(value, str) and not value.strip()


# ---------------------------------------------------------------------------
# Total rows
# ---------------------------------------------------------------------------

def text_columns(rows: list) -> set:
    width = len(rows[0]) if rows else 0
    return {index for index in range(width) if any(isinstance(row[index], str) and to_number(row[index]) is None for row in rows)}


def is_total_row(row: list, label_positions: set) -> bool:
    for index in label_positions:
        cell = row[index]
        if cell is None or (isinstance(cell, str) and (not cell.strip() or TOTAL_LABEL.search(cell))):
            return True
    return False


# ---------------------------------------------------------------------------
# Variants: one accepted (or naive) result and how to compare an answer with it
# ---------------------------------------------------------------------------

@dataclass
class Variant:
    kind: str                  # reference | alternative | interpretation | interpretation_published | undocumented_b | naive
    ident: str
    label: str
    table: dict                # {"columns": [...], "rows": [[...]]}
    column_specs: list         # key column dicts {name, role, unit}
    ordered: bool
    swap: bool = False         # tied rows may swap places
    required: list = field(default_factory=list)
    assumption_rule: Optional[dict] = None
    caveat_rule: Optional[dict] = None
    wide_months: Optional[list] = None
    trap: Optional[str] = None

    @property
    def dimension_names(self) -> list:
        return [c["name"] for c in self.column_specs if c["role"] == "dimension"]

    def unit_of(self, name: str) -> str:
        for spec in self.column_specs:
            if spec["name"] == name:
                return spec.get("unit", "")
        return ""


@dataclass
class RequestSpec:
    request_id: str
    question_id: str
    text: str
    trap_classes: list
    twin_group: Optional[str]
    pattern: int
    ordered: bool
    accepted: list            # Variants that make a run correct (reference or interpretations, alternatives, undocumented_b, published)
    naive: list
    is_ambiguous: bool
    undocumented: Optional[dict]


def build_specs(key: dict, proposal: dict) -> dict:
    required_by_request = {}
    wide_by_request = {}
    for entry in proposal["entries"]:
        required_by_request[entry["request_id"]] = {m["name"] for m in entry["measures"] if m["required"]}
        wide_by_request[entry["request_id"]] = entry.get("wide_months")
    specs = {}
    for entry in key["entries"]:
        request_id = entry["request_id"]
        required_measures = required_by_request[request_id]
        wide = wide_by_request[request_id]

        def make(kind, ident, label, table, column_specs, **extra) -> Variant:
            names = list(table["columns"])
            spec_by_name = {c["name"]: c for c in column_specs}
            specs_present = [spec_by_name.get(n, {"name": n, "role": "measure", "unit": ""}) for n in names]
            if kind in ("interpretation", "interpretation_published"):
                required = names                                  # an interpretation's own columns: all required
            elif kind == "alternative" and extra.get("ranked_by") in names:
                # an alternative that ranks by another measure (REQ-T26, T58: the same table ranked by total net sales) is asked for
                # that measure, not for the per-trading-day figure the reference ranks by
                required = [n for n in names if spec_by_name.get(n, {}).get("role") == "dimension" or n == extra["ranked_by"]]
            else:
                required = [n for n in names if spec_by_name.get(n, {}).get("role") == "dimension" or n in required_measures]
            extra = {k: v for k, v in extra.items() if k != "ranked_by"}
            return Variant(kind=kind, ident=ident, label=label, table=table, column_specs=specs_present, ordered=entry["ordered"],
                           required=required, wide_months=wide if (wide and all(w in names for w in wide)) else None, **extra)

        is_ambiguous = bool(entry["interpretations"])
        accepted = []
        if not is_ambiguous:
            accepted.append(make("reference", "reference", "reference", entry["reference"]["result"], entry["columns"], swap=entry["equal_values_may_swap"]))
            for index, alt in enumerate(entry["alternatives"]):
                ranked_by = (alt.get("order_by") or "").split()[0] if alt.get("order_by") else None
                accepted.append(make("alternative", f"alt{index + 1}", alt["label"], alt["result"], entry["columns"], swap=entry["equal_values_may_swap"],
                                     ranked_by=ranked_by))
        else:
            for interp in entry["interpretations"]:
                accepted.append(make("interpretation", interp["id"], interp["label"], interp["result"], interp["columns"],
                                     swap=interp.get("equal_values_may_swap", False), assumption_rule=interp["assumption_rule"]))
                published = interp.get("published_outcome")
                if published:
                    accepted.append(make("interpretation_published", interp["id"] + ":published", published["label"], published["result"], interp["columns"],
                                         swap=interp.get("equal_values_may_swap", False), assumption_rule=interp["assumption_rule"],
                                         caveat_rule=published["caveat_rule"]))
        undocumented = entry["undocumented"]
        if undocumented:
            b = undocumented["outcome_b_published_with_caveat"]
            accepted.append(make("undocumented_b", "undocumented_b", b["label"], b["result"], entry["columns"], caveat_rule=b["caveat_rule"]))
        naive = [make("naive", n["label"], n["plain"], n["result"], entry["columns"], trap=n["trap"]) for n in entry["naive"]]
        specs[request_id] = RequestSpec(request_id=request_id, question_id=entry["question_id"], text=entry["request_text"],
                                        trap_classes=entry["trap_classes"], twin_group=entry["twin_group"], pattern=entry["pattern"],
                                        ordered=entry["ordered"], accepted=accepted, naive=naive, is_ambiguous=is_ambiguous, undocumented=undocumented)
    return specs


class NameMaps:
    """Store and product names (every version of each) read from the warehouse, to turn a column of names into the IDs they name."""

    def __init__(self, store_names: dict | None = None, product_names: dict | None = None):
        self.store_names = store_names or {}      # casefolded name -> {store_id}
        self.product_names = product_names or {}  # casefolded name -> {sku}

    @classmethod
    def from_warehouse(cls, path: Path = WAREHOUSE_PATH) -> "NameMaps":
        try:
            import duckdb
        except ImportError:
            print("warning: duckdb is not available; names will not be read as IDs")
            return cls()
        if not Path(path).is_file():
            print(f"warning: warehouse not found at {path}; names will not be read as IDs")
            return cls()
        connection = duckdb.connect(str(path), read_only=True)
        try:
            stores, products = {}, {}
            for store_id, name in connection.execute("SELECT store_id, store_name FROM dim_store").fetchall():
                stores.setdefault(repair_text(name).casefold(), set()).add(int(store_id))
            for sku, name in connection.execute("SELECT sku, product_name FROM dim_product").fetchall():
                products.setdefault(repair_text(name).casefold(), set()).add(int(sku))
        finally:
            connection.close()
        return cls(stores, products)


# ---------------------------------------------------------------------------
# Preparing a returned table
# ---------------------------------------------------------------------------

def fused_label_columns(columns: list, rows: list) -> tuple:
    """Marker 5, extended. A column in which EVERY cell is a fiscal label ("FY2025/26 P07", "FY2024/25 Q1", "P7", "W22") gets a derived
    whole-number column (and a derived fiscal-year column when every cell carries a year). A column where only some cells are labels
    is left alone."""
    extra_columns, extra_values = [], []
    if not rows:
        return extra_columns, extra_values
    for index, name in enumerate(columns):
        cells = [row[index] for row in rows]
        if all(isinstance(c, str) and FUSED_FISCAL_LABEL.match(c) for c in cells):
            matches = [FUSED_FISCAL_LABEL.match(c) for c in cells]
            extra_columns.append(f"{name} (number)")
            extra_values.append([int(m.group(2)) for m in matches])
            if all(m.group(1) for m in matches):
                extra_columns.append(f"{name} (fiscal year)")
                extra_values.append([f"FY{m.group(1)}" for m in matches])
    return extra_columns, extra_values


def id_columns_from_names(columns: list, rows: list, maps: NameMaps) -> tuple:
    """A text column in which every cell names a store (or a product) of the warehouse is read as the store_id (or sku) column."""
    extra_columns, extra_values = [], []
    if not rows:
        return extra_columns, extra_values
    for index, name in enumerate(columns):
        cells = [row[index] for row in rows]
        if not all(isinstance(c, str) and c.strip() for c in cells):
            continue
        for table, label in ((maps.store_names, "store_id"), (maps.product_names, "sku")):
            ids = []
            for cell in cells:
                found = table.get(repair_text(cell).casefold())
                if not found or len(found) != 1:
                    ids = None
                    break
                ids.append(next(iter(found)))
            if ids is not None:
                extra_columns.append(f"{name} (as {label})")
                extra_values.append(ids)
    return extra_columns, extra_values


def month_of(cell: Any) -> Optional[int]:
    if isinstance(cell, (int, float)) and not isinstance(cell, bool):
        text = str(int(cell)) if float(cell).is_integer() else str(cell)
    elif isinstance(cell, str):
        text = cell.strip()
    else:
        return None
    hits = [month for month, pattern in MONTH_PATTERNS if pattern.search(text)]
    return hits[0] if len(hits) == 1 else None


def wide_from_long(columns: list, rows: list, wanted_months: tuple = (8, 9)) -> tuple:
    """Months in one column, values in the others: pivot to one derived column per month and numeric column. Returns the derived
    columns and rows, one per distinct combination of the remaining label columns."""
    if not rows:
        return [], []
    month_positions = []
    for index in range(len(columns)):
        months = [month_of(row[index]) for row in rows]
        if all(m is not None for m in months) and set(months) <= set(wanted_months) and len(set(months)) >= 1:
            # a bare 8 or 9 counts as a month only when the column is called something month-like
            name_is_month = bool(re.search(r"month|period|mon", str(columns[index]), re.IGNORECASE))
            all_bare_numbers = all(isinstance(row[index], (int, float)) or re.fullmatch(r"0?\d", str(row[index]).strip()) for row in rows)
            if name_is_month or not all_bare_numbers:
                month_positions.append(index)
    if not month_positions:
        return [], []
    month_position = month_positions[0]
    numeric_positions = [i for i in range(len(columns)) if i != month_position and all(to_number(r[i]) is not None for r in rows)]
    label_positions = [i for i in range(len(columns)) if i != month_position and i not in numeric_positions]
    groups = collections.OrderedDict()
    for row in rows:
        key = tuple(row[i] for i in label_positions)
        groups.setdefault(key, {})[month_of(row[month_position])] = row
    derived_columns = [f"{columns[i]}@{m}" for i in numeric_positions for m in wanted_months]
    derived_rows = []
    for key, by_month in groups.items():
        values = []
        for i in numeric_positions:
            for m in wanted_months:
                values.append(by_month[m][i] if m in by_month else None)
        derived_rows.append(list(key) + values)
    return [columns[i] for i in label_positions] + derived_columns, derived_rows


@dataclass
class Prepared:
    columns: list
    rows: list
    problem: str = ""
    wide_columns: Optional[list] = None
    wide_rows: Optional[list] = None


def prepare_returned(result: Any, maps: NameMaps, features: frozenset, wants_wide: bool) -> Prepared:
    if not isinstance(result, dict) or not isinstance(result.get("rows"), list) or not isinstance(result.get("columns"), list):
        return Prepared([], [], "result is not a table")
    columns = [str(c) for c in result["columns"]]
    rows = result["rows"]
    if any(not isinstance(row, list) for row in rows):
        return Prepared([], [], "rows are not lists")
    if any(len(row) != len(columns) for row in rows):
        return Prepared([], [], "rows differ in width from the columns")
    rows = [list(row) for row in rows]
    extra_columns, extra_values = [], []
    if "fused_label" in features:
        c, v = fused_label_columns(columns, rows)
        extra_columns += c
        extra_values += v
    if "names_for_ids" in features:
        c, v = id_columns_from_names(columns, rows, maps)
        extra_columns += c
        extra_values += v
    if extra_columns:
        columns = columns + extra_columns
        rows = [row + [values[i] for values in extra_values] for i, row in enumerate(rows)]
    prepared = Prepared(columns, rows)
    if wants_wide and "month_long" in features:
        wide_columns, wide_rows = wide_from_long(columns, rows)
        if wide_columns:
            prepared.wide_columns, prepared.wide_rows = wide_columns, wide_rows
    return prepared


# ---------------------------------------------------------------------------
# Comparing a prepared table with a variant
# ---------------------------------------------------------------------------

def tie_groups_match(expected_rows: list, got_rows: list, rules: list, measure_slots: list) -> bool:
    """Ordered comparison where rows with equal values in the ranking measure (the first measure column) may swap places."""
    if not measure_slots:
        return False
    slot = measure_slots[0]
    index = 0
    while index < len(expected_rows):
        end = index + 1
        while end < len(expected_rows) and cells_match(expected_rows[index][slot], expected_rows[end][slot], rules[slot]) \
                and cells_match(expected_rows[end][slot], expected_rows[index][slot], rules[slot]):
            end += 1
        expected_block, got_block = expected_rows[index:end], got_rows[index:end]
        if len(got_block) < len(expected_block):
            return False
        remaining = list(range(len(got_block)))
        for expected_row in expected_block:
            for position in remaining:
                if all(cells_match(e, g, r) for e, g, r in zip(expected_row, got_block[position], rules)):
                    remaining.remove(position)
                    break
            else:
                return False
        index = end
    return True


def rows_match(expected_rows: list, got_rows: list, rules: list, ordered: bool, ignorable: set, swap: bool, measure_slots: list) -> bool:
    """Every expected row matched to its own returned row; the returned rows left over must all be ignorable (zero-filled)."""
    def same(expected_row: list, got_row: list) -> bool:
        return all(cells_match(e, g, r) for e, g, r in zip(expected_row, got_row, rules))
    if ordered:
        kept = [row for i, row in enumerate(got_rows) if i not in ignorable]
        if len(kept) != len(expected_rows):
            return False
        if swap:
            return tie_groups_match(expected_rows, kept, rules, measure_slots)
        return all(same(e, g) for e, g in zip(expected_rows, kept))
    unmatched = sorted(range(len(got_rows)), key=lambda i: i in ignorable)    # real rows first, so a zero row never stands in for a real one
    for expected_row in expected_rows:
        for position in unmatched:
            if same(expected_row, got_rows[position]):
                unmatched.remove(position)
                break
        else:
            return False
    return all(position in ignorable for position in unmatched)


def match_view(variant: Variant, table: dict, columns: list, view_rows: list, features: frozenset) -> tuple:
    expected_columns, expected_rows = table["columns"], table["rows"]
    required = variant.required if "supporting_omitted" in features else list(expected_columns)
    required = [name for name in required if name in expected_columns]
    dimensions = [name for name in variant.dimension_names if name in required]
    measure_names = [name for name in required if name not in dimensions]
    if len(view_rows) < len(expected_rows):
        return False, f"{len(view_rows)} rows returned, {len(expected_rows)} expected"
    extra_rows = len(view_rows) - len(expected_rows)
    if extra_rows and (not dimensions or not measure_names or "zero_rows" not in features):
        return False, f"{len(view_rows)} rows returned, {len(expected_rows)} expected"
    width = len(columns)
    positions = [expected_columns.index(name) for name in required]
    candidates = []
    for name, position in zip(required, positions):
        expected_values = [row[position] for row in expected_rows]
        percent = variant.unit_of(name) == "pct"
        found = []
        for index in range(width):
            got_values = [row[index] for row in view_rows]
            rule = ColumnRule(percent=percent, got_decimals=column_decimals(got_values), allow_rounding="agent_rounding" in features)
            if column_covers(expected_values, got_values, rule):
                found.append((index, rule))
        if not found:
            return False, f"no returned column holds the values of expected column '{name}'"
        candidates.append(found)
    measure_slots = [slot for slot, name in enumerate(required) if name not in dimensions]
    projected_expected = [[row[position] for position in positions] for row in expected_rows]
    for assignment in itertools.islice(itertools.product(*candidates), MAX_COLUMN_ASSIGNMENTS):
        used = [index for index, _ in assignment]
        if len(set(used)) < len(used):
            continue
        rules = [rule for _, rule in assignment]
        projected = [[row[index] for index in used] for row in view_rows]
        ignorable = {i for i, row in enumerate(projected) if extra_rows and all(is_zero_or_empty(row[slot]) for slot in measure_slots)} if extra_rows else set()
        if rows_match(projected_expected, projected, rules, variant.ordered, ignorable, variant.swap, measure_slots):
            return True, "match"
    return False, "columns found but the rows do not line up" + (" in order" if variant.ordered else "")


def match_variant(variant: Variant, prepared: Prepared, features: frozenset) -> tuple:
    """(matches, reason) for one prepared returned table against one variant."""
    if prepared.problem:
        return False, prepared.problem
    expected = variant.table
    if not expected["rows"]:
        return (True, "both empty") if not prepared.rows else (False, f"{len(prepared.rows)} rows returned, 0 expected")
    sources = [(prepared.columns, prepared.rows, "")]
    if variant.wide_months and prepared.wide_columns:
        sources.append((prepared.wide_columns, prepared.wide_rows, "months given long, read as wide"))
    first_reason = None
    for columns, rows, source_note in sources:
        views = [("", rows)]
        labels = text_columns(rows)
        totals = [i for i, row in enumerate(rows) if is_total_row(row, labels)] if labels else []
        has_total_in_expected = any(is_total_row(row, text_columns(expected["rows"])) for row in expected["rows"])
        if "totals" in features and totals and not has_total_in_expected:
            if len(expected["rows"]) == 1 and not variant.dimension_names:
                views += [("figure taken from the total row", [rows[i]]) for i in totals]
            else:
                views.append(("total row ignored", [row for i, row in enumerate(rows) if i not in totals]))
        for note, view_rows in views:
            ok, reason = match_view(variant, expected, columns, view_rows, features)
            if ok:
                notes = [n for n in (source_note, note) if n]
                return True, "match" + (f" ({'; '.join(notes)})" if notes else "")
            first_reason = first_reason or reason
    return False, first_reason


# ---------------------------------------------------------------------------
# Keyword rules
# ---------------------------------------------------------------------------

def text_of(value: Any) -> str:
    """A list of strings (or one string, or nested lists) as one lower-case text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.lower()
    if isinstance(value, (list, tuple)):
        return "\n".join(text_of(v) for v in value)
    if isinstance(value, dict):
        return "\n".join(text_of(v) for v in value.values())
    return str(value).lower()


def rule_passes(rule: Optional[dict], text: str) -> bool:
    """Every group of the rule has at least one of its words in the text."""
    if rule is None:
        return True
    text = text.lower()
    return all(any(word.lower() in text for word in group) for group in rule["groups"])


# ---------------------------------------------------------------------------
# Marking one answer
# ---------------------------------------------------------------------------

@dataclass
class Mark:
    outcome: str                         # correct | wrong | no_answer
    reason: str = ""
    matched: Optional[str] = None        # kind:ident of the accepted result the answer matched
    route: Optional[str] = None          # reference | alternative | interpretation | undocumented_a | undocumented_b | interpretation_published
    rule_status: Optional[str] = None    # pass | fail | None (no keyword rule involved)
    borderline: Optional[str] = None     # why the run goes to the arm-blind adjudication, if it does
    borderline_reading: Optional[str] = None
    audit_candidate: bool = False        # passed by keyword rule; may be sampled for a false-pass audit
    naive_matches: list = field(default_factory=list)
    attribution: Optional[str] = None
    other_notes: list = field(default_factory=list)


def wants_wide(spec: RequestSpec) -> bool:
    return any(v.wide_months for v in spec.accepted)


def naive_attribution(spec: RequestSpec, prepared: Prepared, features: frozenset) -> list:
    return [(v.ident, v.trap) for v in spec.naive if match_variant(v, prepared, features)[0]]


def percent_as_fraction(spec: RequestSpec, result: dict, maps: NameMaps, features: frozenset) -> bool:
    """Diagnostic for wrong answers: does the answer match an accepted result once its percentage-like columns are multiplied by 100?"""
    try:
        columns, rows = result["columns"], result["rows"]
        scaled = [[(round(cell * 100, 6) if isinstance(cell, (int, float)) and not isinstance(cell, bool) and abs(cell) <= 1.5 else cell) for cell in row] for row in rows]
        prepared = prepare_returned({"columns": columns, "rows": scaled}, maps, features, wants_wide(spec))
        return any(v.kind != "naive" and match_variant(v, prepared, features)[0] for v in spec.accepted if v.kind in ("reference", "alternative"))
    except Exception:
        return False


def mark_answer(spec: RequestSpec, answer: Optional[dict], status: str, maps: NameMaps, features: frozenset = FEATURES) -> Mark:
    if status != "ok" or answer is None:
        return Mark(outcome="no_answer", reason=f"{status}", attribution="no_answer")
    prepared = prepare_returned(answer.get("result"), maps, features, wants_wide(spec))
    assumptions = text_of(answer.get("assumptions"))
    caveats = text_of(answer.get("caveats"))
    everything = "\n".join([assumptions, caveats, text_of(answer.get("definitions_applied"))])
    accepted_variants = [v for v in spec.accepted if "alternatives" in features or v.kind != "alternative"]
    matches = []
    first_reason = prepared.problem
    for variant in accepted_variants:
        ok, reason = match_variant(variant, prepared, features)
        if ok:
            matches.append((variant, reason))
        elif not first_reason:
            first_reason = reason
    if not matches:
        mark = Mark(outcome="wrong", reason=first_reason or "no accepted result matched")
        naive = naive_attribution(spec, prepared, features) if not prepared.problem else []
        mark.naive_matches = [ident for ident, _ in naive]
        if prepared.problem:
            mark.attribution = "malformed_table"
        elif naive:
            mark.attribution = naive[0][1]
        elif percent_as_fraction(spec, answer.get("result") or {}, maps, features):
            mark.attribution = "percent_as_fraction"
        else:
            mark.attribution = "other"
        return mark

    # --- ambiguous class: the result matches a reading; the assumptions must name it
    if spec.is_ambiguous:
        passing, failing = [], []
        for variant, reason in matches:
            assumption_ok = rule_passes(variant.assumption_rule, assumptions)
            published = variant.kind == "interpretation_published"
            caveat_ok = rule_passes(variant.caveat_rule, caveats) if published else True
            (passing if assumption_ok and caveat_ok else failing).append((variant, assumption_ok, caveat_ok))
        if passing:
            # a corrected result that also matches beats a published one: prefer a variant needing no caveat
            passing.sort(key=lambda item: item[0].kind == "interpretation_published")
            variant = passing[0][0]
            return Mark(outcome="correct", reason="match; assumptions name the reading" + ("; caveats name the duplicates" if variant.kind == "interpretation_published" else ""),
                        matched=f"{variant.kind}:{variant.ident}", route="interpretation_published" if variant.kind == "interpretation_published" else "interpretation",
                        rule_status="pass", audit_candidate=True, borderline_reading=variant.label)
        variant, assumption_ok, caveat_ok = failing[0]
        lenient_ok = rule_passes(variant.assumption_rule, everything) and (variant.kind != "interpretation_published" or rule_passes(variant.caveat_rule, everything))
        kind = "named_outside_assumptions" if lenient_ok else "reading_not_named_by_keywords"
        if variant.kind == "interpretation_published" and assumption_ok and not caveat_ok:
            kind = "published_number_caveat_not_matched" if not lenient_ok else "published_number_caveat_outside_caveats"
        return Mark(outcome="wrong", reason=f"result matches '{variant.label}' but the keyword rule fails ({kind})", matched=f"{variant.kind}:{variant.ident}",
                    rule_status="fail", borderline=kind, borderline_reading=variant.label, attribution="assumption_not_named")

    # --- the undocumented class: (a) the incident-free number, (b) the published number with the problem named in caveats
    if spec.undocumented:
        for variant, reason in matches:
            if variant.kind in ("reference", "alternative"):
                return Mark(outcome="correct", reason="match (incident-free number)", matched=f"{variant.kind}:{variant.ident}", route="undocumented_a")
        variant = next(v for v, _ in matches if v.kind == "undocumented_b")
        if rule_passes(variant.caveat_rule, caveats):
            return Mark(outcome="correct", reason="published number; caveats name the problem", matched="undocumented_b:undocumented_b", route="undocumented_b",
                        rule_status="pass", audit_candidate=True, borderline_reading=variant.label)
        lenient_ok = rule_passes(variant.caveat_rule, everything)
        kind = "named_outside_caveats" if lenient_ok else "caveat_keywords_fail"
        mark = Mark(outcome="wrong", reason=f"published number; caveat keyword rule fails ({kind})", matched="undocumented_b:undocumented_b", rule_status="fail",
                    borderline=kind, borderline_reading=variant.label, attribution="published_without_warning")
        mark.naive_matches = [ident for ident, _ in naive_attribution(spec, prepared, features)]
        return mark

    variant, reason = matches[0]
    return Mark(outcome="correct", reason=reason, matched=f"{variant.kind}:{variant.ident}", route=variant.kind if variant.kind != "reference" else "reference")


# ---------------------------------------------------------------------------
# Marking the whole run
# ---------------------------------------------------------------------------

def load_specs(key_path: Path = KEY_PATH, proposal_path: Path = PROPOSAL_PATH) -> dict:
    key = json.loads(Path(key_path).read_text(encoding="utf-8"))
    proposal = json.loads(Path(proposal_path).read_text(encoding="utf-8"))
    return build_specs(key, proposal)


def load_collected(path: Path = COLLECTED_PATH) -> list:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def mark_row(row: dict, specs: dict, maps: NameMaps, features: frozenset = FEATURES) -> Mark:
    return mark_answer(specs[row["request_id"]], row["answer"], row["status"], maps, features)


def blind_label(counter: int) -> str:
    return f"A{counter:03d}"


def write_adjudication_files(rows: list, marks: dict, specs: dict, out_dir: Path) -> dict:
    """The arm-blind review list: every borderline run, plus a seeded sample of keyword-rule passes (to audit false passes). Items are
    shuffled and carry no arm, model or run id; the map from item to run is a separate file."""
    items = [(row, marks[row["run_id"]]) for row in rows if marks[row["run_id"]].borderline]
    audit_pool = [(row, marks[row["run_id"]]) for row in rows if marks[row["run_id"]].audit_candidate and not marks[row["run_id"]].borderline]
    rng = random.Random(SEED)
    sample_size = min(len(audit_pool), max(30, len(audit_pool) // 4))
    audit = rng.sample(audit_pool, sample_size) if audit_pool else []
    chosen = [(row, mark, "borderline") for row, mark in items] + [(row, mark, "audit_of_rule_pass") for row, mark in audit]
    rng.shuffle(chosen)
    mapping, lines = {}, ["# Arm-blind review list (Phase 6)", "",
                          "Each item is one run on an ambiguous or undocumented-issue request. Arm, model and run id are hidden. For each item decide PASS or FAIL.",
                          "",
                          "Criterion for an ambiguous request: the `assumptions` list states which reading the answer takes (what 'biggest', 'best-selling', 'last month', 'customers' or 'doing well' means), in words a requester would recognise as that reading. The result table already matches that reading.",
                          "Criterion for an undocumented-issue request, or a reading that reaches last year's double-posted week: the `caveats` list names the data problem that makes the published number wrong (the duplicated rows, lost member keys, mislabelled channel), so a requester would be warned. The result table already carries the published number.",
                          ""]
    for number, (row, mark, why) in enumerate(chosen, start=1):
        label = blind_label(number)
        spec = specs[row["request_id"]]
        answer = row["answer"] or {}
        mapping[label] = {"run_id": row["run_id"], "why_listed": why, "keyword_rule_status": mark.rule_status, "borderline_kind": mark.borderline,
                          "reading": mark.borderline_reading, "request_id": row["request_id"]}
        lines += [f"## {label}", f"Request: {spec.text}", f"Reading the result matches: {mark.borderline_reading}"]
        if spec.undocumented:
            lines.append(f"The data problem (for the criterion): {spec.undocumented['what']}")
        lines.append("Assumptions: " + json.dumps(answer.get("assumptions"), ensure_ascii=False))
        lines.append("Caveats: " + json.dumps(answer.get("caveats"), ensure_ascii=False))
        lines += ["", "Decision: ", ""]
    (out_dir / "adjudication_blind.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "adjudication_map.json").write_text(json.dumps(mapping, indent=1, ensure_ascii=False), encoding="utf-8")
    return mapping


def apply_adjudication(marks: dict, decisions: dict, mapping: dict) -> dict:
    """Decisions are {item label: "PASS" | "FAIL"}. A borderline run decided PASS becomes correct; FAIL stays wrong; an audited rule-pass
    decided FAIL becomes wrong. Returns {run_id: (outcome, item label)} for the runs the decisions changed or confirmed."""
    changed = {}
    for label, verdict in decisions.items():
        info = mapping.get(label)
        if info is None:
            continue
        run_id = info["run_id"]
        if isinstance(verdict, dict):
            verdict = verdict.get("verdict", "")
        passed = str(verdict).strip().upper().startswith("PASS")
        changed[run_id] = ("correct" if passed else "wrong", label, info["why_listed"])
    return changed


def mark_all(rows: list, specs: dict, maps: NameMaps, features: frozenset = FEATURES) -> dict:
    return {row["run_id"]: mark_row(row, specs, maps, features) for row in rows}


def ledger(rows: list, specs: dict, maps: NameMaps, base_marks: dict) -> dict:
    """How many runs each leniency decides: correct under the full marker, wrong without it."""
    result = {}
    base_correct = sum(m.outcome == "correct" for m in base_marks.values())
    for feature in sorted(FEATURES):
        marks = mark_all(rows, specs, maps, FEATURES - {feature})
        lost = [run_id for run_id, m in marks.items() if m.outcome != "correct" and base_marks[run_id].outcome == "correct"]
        gained = [run_id for run_id, m in marks.items() if m.outcome == "correct" and base_marks[run_id].outcome != "correct"]
        result[feature] = {"correct_with": base_correct, "correct_without": sum(m.outcome == "correct" for m in marks.values()),
                           "runs_that_depend_on_it": lost, "runs_that_gain_without_it": gained}
    marks = mark_all(rows, specs, maps, frozenset())
    result["_all_off"] = {"correct_with": base_correct, "correct_without": sum(m.outcome == "correct" for m in marks.values())}
    return result


def mark_record(row: dict, mark: Mark, spec: RequestSpec, adjudicated: Optional[tuple]) -> dict:
    outcome = mark.outcome
    adjudication = None
    if adjudicated:
        outcome, label, why = adjudicated
        adjudication = {"item": label, "why_listed": why, "decision": outcome}
    return {
        "run_id": row["run_id"], "model": row["model"], "arm": row["arm"], "request_id": row["request_id"], "repeat": row["repeat"],
        "outcome_strict": mark.outcome, "outcome": outcome, "reason": mark.reason, "matched": mark.matched, "route": mark.route,
        "rule_status": mark.rule_status, "borderline": mark.borderline, "naive_matches": mark.naive_matches, "attribution": mark.attribution,
        "adjudication": adjudication, "marker_version": MARKER_VERSION,
        "returned_columns": (row["answer"] or {}).get("result", {}).get("columns") if row["answer"] else None,
        "returned_row_count": len(((row["answer"] or {}).get("result") or {}).get("rows") or []) if row["answer"] else None,
    }


def run(adjudication_path: Optional[Path], out_dir: Path = OUT_DIR, with_ledger: bool = True) -> dict:
    say = print
    if out_dir.resolve() in (KEY_PATH.parent.resolve(), CASE_ROOT / "data" / "agent_runs"):
        raise SystemExit(f"Refusing to write into {out_dir}: it is an input folder.")
    out_dir.mkdir(parents=True, exist_ok=True)
    specs = load_specs()
    maps = NameMaps.from_warehouse()
    rows = load_collected()
    say(f"Marking {len(rows)} runs with marker {MARKER_VERSION} ({len(specs)} requests, {len(maps.store_names)} store names, {len(maps.product_names)} product names) ...")
    marks = mark_all(rows, specs, maps)
    mapping = write_adjudication_files(rows, marks, specs, out_dir)
    decisions_applied = {}
    if adjudication_path:
        payload = json.loads(Path(adjudication_path).read_text(encoding="utf-8"))
        decisions = payload.get("decisions", payload)
        expected_hash = payload.get("blind_file_sha256")
        if expected_hash:
            import hashlib
            actual_hash = hashlib.sha256((out_dir / "adjudication_blind.md").read_bytes()).hexdigest()
            if actual_hash != expected_hash:
                raise SystemExit("The decisions were made on a different blind list than the one this marking produced (the hash differs). "
                                 "Item labels would point at the wrong runs; redo the adjudication on the current adjudication_blind.md.")
        decisions_applied = apply_adjudication(marks, decisions, mapping)
        say(f"Applied {len(decisions_applied)} adjudication decisions from {adjudication_path}")
    records = [mark_record(row, marks[row["run_id"]], specs[row["request_id"]], decisions_applied.get(row["run_id"])) for row in rows]
    (out_dir / "marked_runs.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    strict = sum(r["outcome_strict"] == "correct" for r in records)
    final = sum(r["outcome"] == "correct" for r in records)
    say(f"  correct (strict keyword rules): {strict} of {len(records)}; after adjudication: {final}; listed for adjudication: {len(mapping)}")
    if with_ledger:
        say("Measuring how many runs each leniency decides ...")
        led = ledger(rows, specs, maps, marks)
        (out_dir / "leniency_ledger.json").write_text(json.dumps(led, indent=1), encoding="utf-8")
        for feature, info in led.items():
            say(f"  {feature}: {info['correct_with']} correct with, {info['correct_without']} without" + (f" ({len(info['runs_that_depend_on_it'])} runs depend on it)" if "runs_that_depend_on_it" in info else ""))
    return {"strict_correct": strict, "correct": final, "listed": len(mapping)}


def self_check() -> int:
    """The key against itself, through the same engine. Returns the number of failures."""
    specs = load_specs()
    maps = NameMaps.from_warehouse()
    failures = 0
    for request_id, spec in specs.items():
        for variant in spec.accepted:
            if variant.kind == "undocumented_b":
                answer = {"result": variant.table, "assumptions": [], "caveats": ["Duplicate rows twice 116 lielahti week 21 15 sep west snapshot channel click collect wrong member missing feb march p10 p11 week week ending"], "definitions_applied": []}
            elif variant.kind in ("interpretation", "interpretation_published"):
                words = " ".join(w for g in variant.assumption_rule["groups"] for w in g[:1])
                cave = " ".join(w for g in (variant.caveat_rule or {"groups": []})["groups"] for w in g[:1])
                answer = {"result": variant.table, "assumptions": [words], "caveats": [cave], "definitions_applied": []}
            else:
                answer = {"result": variant.table, "assumptions": [], "caveats": [], "definitions_applied": []}
            mark = mark_answer(spec, answer, "ok", maps)
            if mark.outcome != "correct":
                failures += 1
                print(f"FAIL {request_id} accepted result '{variant.kind}:{variant.ident}' marks {mark.outcome}: {mark.reason}")
        for variant in spec.naive:
            answer = {"result": variant.table, "assumptions": [], "caveats": [], "definitions_applied": []}
            mark = mark_answer(spec, answer, "ok", maps)
            if mark.outcome == "correct":
                failures += 1
                print(f"FAIL {request_id} naive variant '{variant.ident}' marks correct ({mark.matched})")
            elif variant.ident not in mark.naive_matches:
                failures += 1
                print(f"FAIL {request_id} naive variant '{variant.ident}' is not attributed to itself ({mark.naive_matches})")
    print(f"self-check: {failures} failures over {len(specs)} requests")
    return failures


def main(argv: list | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Mark the full run against the answer key.")
    parser.add_argument("--adjudication", type=Path, help="decisions file {item: PASS|FAIL} from the arm-blind review")
    parser.add_argument("--self-check", action="store_true", help="check the key against itself and exit")
    parser.add_argument("--no-ledger", action="store_true", help="skip the leniency ledger (it re-marks the run once per feature)")
    args = parser.parse_args(argv)
    if args.self_check:
        return 1 if self_check() else 0
    run(args.adjudication, with_ledger=not args.no_ledger)
    return 0


if __name__ == "__main__":
    sys.exit(main())
