"""Marking for the pilot only: a returned result table against a dev request's accepted result.

This is NOT the Phase 6 marker (code/mark.py, the only reader of the answer key). It reads no key. The pilot uses dev
requests, whose accepted result is what the analyst's accepted query (world/request_history/REQ-D*.md) returns on the
warehouse. The rules:
  - columns are matched by values, not names (a returned column matches an expected column if its values do);
  - rows are order-insensitive unless the accepted query is a top-N (it has a LIMIT);
  - numbers match within 0.1% relative; columns named like percentages, shares, rates or growth within 0.1 pp;
    a value that is a few cents out from rounding passes (absolute floor 0.005);
  - extra returned columns are tolerated, a missing required column is a fail.

Revised 15 Oct 2026 after the pilot diagnosis. 21 of the pilot's 31 wrong marks
were the marker, not the model. The revision adds four things, each covering answers that carry the same numbers as the
accepted result in a different but legitimate shape:
  1. Total rows. A returned row labelled as a total ("Total", "Total company", "All regions", or a NULL label from a
     ROLLUP) is ignored when the accepted result has no such row. When the accepted result is one figure with no row
     label, a total row carrying that figure is accepted and the breakdown under it is extra detail.
  2. Zero-filled rows. An extra returned row whose required measures are all zero or empty (hour 3 with 0 orders, say)
     is ignored: it says the same as an absent row. This needs to know which columns are row labels, so it applies only
     with an answer spec.
  3. Required columns. Per dev request, PILOT_ANSWER_SPECS names the columns the request actually asks for (the row
     labels and the asked-for measure). The accepted query's supporting columns (the two totals behind a growth rate,
     the sold and returned amounts behind a return rate) may be left out. Without a spec every expected column is
     required, as before.
  4. Accepted alternatives. Per dev request, other readings that answer the request as worded and follow the
     documented rules (world/), computed on the warehouse from the accepted query. They are listed with their reasons
     in PILOT_ANSWER_SPECS; an answer that matches one is correct and the reason names it.
What stays strict: every number within tolerance, every required column present, every expected row present, no extra
row that carries non-zero figures, and the order for a top-N.

Revised 15 Oct 2026 (marker version 4) after the pilot 2 diagnosis. Three more
shapes that carry the accepted numbers, each a judgement that can be reversed:
  5. Rounded columns. When the accepted query rounded a column (every value of a column of five or more is a whole number, or has
     one decimal), the unrounded figure is accepted: the gap may be half a unit of the last kept place. REQ-D40's per-day figures
     are rounded to whole euros, which is more than 0.1% of the small stores' figures.
  6. Wide for long. A spec may list `wide_alternatives`: a dimension with few values (web and stores) given as one column per value
     instead of one row per value. The columns are found by their values, as always.
  7. Label aliases. A spec may map a label the request itself words differently ("Store" for "Stores").
What stays strict, among other things: the trap readings (calendar-date comparisons, units for value, cancelled orders counted, the
sale-date category, Online or Web dropped) and every number outside tolerance.

Revised 15 Oct 2026 (marker version 5), after pilot 2: a fused fiscal label is also accepted, because it is
unambiguous. One more shape:
  8. Fused fiscal labels. A returned column in which every cell is a fiscal year joined to a period, quarter or week
     ("FY2025/26 P07", "FY2024/25 Q1", "FY2025/26 W15") counts as a separate fiscal-year column and a separate whole-number
     column. The fused column is split into two extra columns before matching, so it is equal to the same answer given in
     separate columns: the year must still equal the accepted result's fiscal_year where it has one, and the number must
     still equal the period, quarter or week. A column where only some cells are fused is left alone. The shared output
     rules (task text version 3) ask for separate columns; the marker no longer fails an answer that did not follow them.
"""
from __future__ import annotations

import itertools
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Optional

import duckdb

import config as cfg
from harness import json_safe

MARKER_VERSION = "5"   # 1 = the pilot as run on 15 Oct 2026; 2 = after the pilot diagnosis (totals, zero rows, required columns, alternatives);
                       # 3 = pilot 2 / agent runs: any-of groups in `required` (a name or an ID label), an `ordered` override in the spec;
                       # 4 = after the pilot 2 diagnosis: a column the accepted query rounded may be given unrounded (half a unit of its last
                       #     place), a two-valued dimension may be given as one column per value (wide), label aliases in the spec;
                       # 5 = after pilot 2: a fiscal year fused with its period, quarter or week in one label
                       #     ("FY2025/26 P07") equals a separate fiscal-year column and a separate whole number
PERCENT_COLUMN = re.compile(r"pct|percent|share|rate|growth", re.IGNORECASE)
TOTAL_LABEL = re.compile(r"^\s*(grand\s+)?total\b|^\s*all(\s|$)|\btotal\s*$", re.IGNORECASE)
ABSOLUTE_FLOOR = 0.005
MAX_COLUMN_ASSIGNMENTS = 200


# ---------------------------------------------------------------------------
# Answer specs for the pilot's dev requests
# ---------------------------------------------------------------------------

def _strip_semicolon(sql: str) -> str:
    return sql.strip().rstrip(";").strip()


def _d02_four_week_total(accepted_sql: str) -> str:
    """REQ-D02 as a four-week total per format: the accepted weekly rows summed, growth recomputed from the sums."""
    return (f"SELECT format, SUM(this_year) AS this_year, SUM(last_year) AS last_year, "
            f"ROUND(100.0 * (SUM(this_year) / SUM(last_year) - 1), 1) AS growth_pct "
            f"FROM ({_strip_semicolon(accepted_sql)}) GROUP BY format ORDER BY format")


def _d14_previous_fiscal_year(accepted_sql: str) -> str:
    """REQ-D14 with 'last year' read as the fiscal year before the current one (FY2024/25 on 10 March 2026)."""
    return accepted_sql.replace("FY2025/26", "FY2024/25")


def _d20_without_test_orders(accepted_sql: str) -> str:
    """REQ-D20 without web orders that hold a ZZ Test article (one such order on Black Friday 2024, in the 15:00 hour)."""
    marker = "AND o.status <> 'cancelled'"
    if marker not in accepted_sql:
        raise ValueError("REQ-D20's accepted query no longer has the cancelled-order filter this alternative extends")
    return accepted_sql.replace(marker, marker + "\n  AND o.web_order_id NOT IN (SELECT f.receipt_id FROM fact_sales_line f "
                                "JOIN dim_product p ON p.product_key = f.product_key WHERE p.category = 'ZZ Test')")


# dimensions: the expected columns that label rows. required: the columns an answer must carry (labels plus the
# measure the request asks for). alternatives: (label, why it is accepted, function of the accepted SQL).
PILOT_ANSWER_SPECS: dict = {
    "REQ-D02": {
        "dimensions": ["fiscal_week", "format"],
        "required": ["fiscal_week", "format", "this_year", "last_year"],
        "alternatives": [
            ("four-week total per format",
             "The request asks for sales by format for the last four weeks against last year; it does not ask for a "
             "weekly split. The accepted query happens to split by week.",
             _d02_four_week_total),
        ],
    },
    "REQ-D06": {
        "dimensions": [],
        "required": ["lfl_growth_pct"],
        "alternatives": [],
    },
    "REQ-D14": {
        "dimensions": ["category"],
        "required": ["category", "return_rate_pct"],
        "alternatives": [
            ("'last year' = FY2024/25",
             "'Last year' is not defined in world/ (the metric dictionary defines 'last period', 'YTD' and 'this "
             "year'); on 10 March 2026 the previous fiscal year is FY2024/25, the reading REQ-D04 and the test set use.",
             _d14_previous_fiscal_year),
        ],
    },
    "REQ-D20": {
        "dimensions": ["hour_helsinki"],
        "required": ["hour_helsinki", "web_orders"],
        "alternatives": [
            ("test web orders left out",
             "world/data_quality_register.md: test articles are sold 'in a few web test orders, and are left out of "
             "all reporting'. The accepted query counts the one test order of the day.",
             _d20_without_test_orders),
        ],
    },
    "REQ-D32": {
        "dimensions": ["region"],
        "required": ["region", "member_share_pct"],
        "alternatives": [],
    },

    # ---- Pilot 2 (agent runs, 15 Oct 2026): ten more dev requests, one per pattern the history covers --------------------
    # required = the row labels plus the figure the request asks for; supporting columns of the accepted query may be left out.
    # A list inside `required` means one of those names is enough to label the row (a store's name or ID, a week's number
    # or its start date). No alternative is listed unless the request as worded allows a second reading that the documented
    # rules (world/) do not rule out; every other trap reading stays wrong on purpose.
    "REQ-D05": {   # pattern 1: regions as they were at the time (SCD), 'last year' received 18 Jun 2025 = FY2024/25
        "dimensions": ["fiscal_quarter", "region"],
        "required": ["fiscal_quarter", "region", "net_sales"],
        "alternatives": [],
    },
    "REQ-D09": {   # pattern 2: year-to-date LFL; one figure, the growth percentage
        "dimensions": [],
        "required": ["lfl_growth_pct"],
        "alternatives": [],
    },
    "REQ-D10": {   # pattern 3: net sales and margin % by category, margin after returns, categories as-is
        "dimensions": ["category"],
        "required": ["category", "net_sales", "gross_margin_pct"],
        "alternatives": [],
    },
    "REQ-D16": {   # pattern 4: return rate web vs stores by category; cohort of Q1 sales
        "dimensions": ["category", "channel_group"],
        "required": ["category", "channel_group", "return_rate_pct"],
        "alternatives": [
            ("'last year' = FY2024/25",
             "'Last year' is not defined in world/. The request was received on 21 Jan 2026, inside FY2025/26, so 'Q1 last year' is "
             "Q1 of FY2024/25 on the reading REQ-D04 and the test set use; the accepted query took Q1 of FY2025/26 (the quarter "
             "that began in calendar 2025). Both are accepted, as for REQ-D14.",
             _d14_previous_fiscal_year),
        ],
        # 'web vs stores by category' invites web and stores side by side: one row per category, one column per channel.
        "wide_alternatives": [
            {"pivot": "channel_group", "measure": "return_rate_pct",
             "why": "The request asks for web against stores by category; one row per category with a web column and a stores column "
                    "carries the same rates as one row per category and channel."},
        ],
        # the request's own words are 'web' and 'stores'; the singular is the same label
        "label_aliases": {"Stores": ["Store", "Physical stores", "Physical store"]},
    },
    "REQ-D19": {   # pattern 5: weekly web sales through the 3 Nov 2025 migration; the week is a number or a start date
        "dimensions": ["fiscal_year", "fiscal_week", "week_start"],
        "required": [["fiscal_week", "week_start"], "web_net_sales"],
        "alternatives": [],
    },
    "REQ-D24": {   # pattern 6: click-and-collect share of web orders by quarter, complete quarters only, cancelled out
        "dimensions": ["fiscal_year", "fiscal_quarter"],
        "required": ["fiscal_year", "fiscal_quarter", "click_collect_share_pct"],
        "alternatives": [],
    },
    "REQ-D28": {   # pattern 7: one store's ATV against the chain by period
        "dimensions": ["fiscal_period"],
        "required": ["fiscal_period", "pori_atv", "chain_atv"],
        "alternatives": [],
    },
    "REQ-D30": {   # pattern 8: active members by tier at a date (tier valid on that date)
        "dimensions": ["tier"],
        "required": ["tier", "active_members"],
        "alternatives": [],
    },
    "REQ-D34": {   # pattern 11: top 10 brands by margin, Capital Region as-is; order matters (the accepted query has a LIMIT)
        "dimensions": ["brand"],
        "required": ["brand", "gross_margin"],
        "alternatives": [],
    },
    "REQ-D40": {   # pattern 12: league table, ranked per trading day; a league table is an ordered list even without a LIMIT
        "dimensions": ["rank", "store_id", "store_name"],
        "required": [["store_name", "store_id"], "net_sales_per_trading_day"],
        "ordered": True,
        "alternatives": [],
    },

    # ---- Pilot 3 (agent runs, 15 Oct 2026): ten more dev requests, one per pattern the history covers ---------------------------
    # Same rules as pilot 2: required = the row labels plus the figure the request asks for, supporting columns may be left out, a
    # list inside `required` means one of those names is enough, and no alternative unless the request as worded allows a second
    # reading that world/ does not rule out. Every trap reading stays wrong on purpose.
    "REQ-D03": {   # pattern 1: total company net sales per week for Q3 with last year alongside; whole fiscal weeks 27-39
        "dimensions": ["fiscal_week"],
        "required": ["fiscal_week", "this_year", "last_year"],
        "alternatives": [],
    },
    "REQ-D08": {   # pattern 2: LFL by region for the back half of last year (weeks 27-52); the growth is the asked-for figure
        "dimensions": ["region"],
        "required": ["region", "lfl_growth_pct"],
        "alternatives": [],
    },
    "REQ-D12": {   # pattern 3: top 10 subcategories by gross margin (amount) for Q4 = last year's Q4 incl. week 53; order matters (LIMIT)
        "dimensions": ["subcategory"],
        "required": ["subcategory", "gross_margin"],
        "alternatives": [],
    },
    "REQ-D15": {   # pattern 4: Furniture return rate by subcategory, FY24/25 sales (sale-week cohort)
        "dimensions": ["subcategory"],
        "required": ["subcategory", "return_rate_pct"],
        "alternatives": [],
    },
    "REQ-D18": {   # pattern 5: web orders per week in P8, cancelled out; whole weeks
        "dimensions": ["fiscal_week"],
        "required": ["fiscal_week", "web_orders"],
        "alternatives": [],
    },
    "REQ-D22": {   # pattern 6: click and collect share of web SALES (value) by period, P1 to P4
        "dimensions": ["fiscal_period"],
        "required": ["fiscal_period", "click_collect_share_pct"],
        "alternatives": [],
    },
    "REQ-D27": {   # pattern 7: ATV by weekday for P11; the weekday is a number or a name
        "dimensions": ["day_of_week", "day_name"],
        "required": [["day_of_week", "day_name"], "atv"],
        "alternatives": [],
    },
    "REQ-D29": {   # pattern 8: one figure, active members at the end of last year (distinct member_id, trailing 52 weeks)
        "dimensions": [],
        "required": ["active_members"],
        "alternatives": [],
    },
    "REQ-D35": {   # pattern 11: top 5 subcategories by margin in the East (as-is), second half of last year; order matters (LIMIT)
        "dimensions": ["subcategory"],
        "required": ["subcategory", "gross_margin"],
        "alternatives": [],
    },
    "REQ-D39": {   # pattern 12: league table of the Large stores, ranked per trading day (closed holidays out); an ordered list
        "dimensions": ["rank", "store_id", "store_name"],
        "required": [["store_name", "store_id"], "net_sales_per_trading_day"],
        "ordered": True,
        "alternatives": [],
    },
}


def answer_spec(request_id: str) -> Optional[dict]:
    """The pilot answer spec of a dev request, or None (then every expected column is required and nothing else is accepted)."""
    return PILOT_ANSWER_SPECS.get(request_id)


# ---------------------------------------------------------------------------
# Expected results
# ---------------------------------------------------------------------------

def compute_expected(warehouse_path: Path, accepted_sql: str) -> dict:
    """Run a dev request's accepted query read-only and return {"columns": [...], "rows": [[...]]}."""
    connection = duckdb.connect(str(warehouse_path), read_only=True)
    try:
        cursor = connection.execute(accepted_sql)
        columns = [item[0] for item in cursor.description]
        rows = [[json_safe(cell) for cell in row] for row in cursor.fetchall()]
    finally:
        connection.close()
    return {"columns": columns, "rows": rows}


def compute_expected_set(warehouse_path: Path, request_id: str, accepted_sql: str) -> dict:
    """The accepted result of a dev request, whether it is ordered, and the results of its accepted alternatives."""
    spec = answer_spec(request_id) or {"alternatives": []}
    alternatives = []
    for label, why, build in spec["alternatives"]:
        sql = build(accepted_sql)
        alternatives.append({"label": label, "why": why, "sql": sql, "table": compute_expected(warehouse_path, sql)})
    accepted_table = compute_expected(warehouse_path, accepted_sql)
    # Wide readings of the accepted result and of every other alternative (a dimension with few values as one column per value).
    for wide in spec.get("wide_alternatives", []):
        wide_label = f"{wide['pivot']} as columns"
        for base_label, base_table, base_why in [(None, accepted_table, None)] + [(a["label"], a["table"], a["why"]) for a in list(alternatives)
                                                                                  if "wide_spec" not in a]:
            widened = widen_table(base_table, wide["pivot"], wide["measure"], (spec.get("dimensions") or []))
            alternatives.append({"label": wide_label if base_label is None else f"{base_label}; {wide_label}",
                                 "why": wide["why"] if base_why is None else f"{base_why} {wide['why']}",
                                 "sql": None, "table": widened["table"], "wide_spec": widened["spec"]})
    ordered = spec["ordered"] if "ordered" in spec else is_ordered(accepted_sql)
    return {"table": accepted_table, "ordered": ordered,
            "alternatives": alternatives, "marker_version": MARKER_VERSION}


def widen_table(table: dict, pivot: str, measure: str, dimensions: list) -> dict:
    """A long table (one row per other-dimensions x pivot value) as a wide one: one row per other-dimensions, one column per pivot
    value, holding the measure. Returns the table and the answer spec to use against it (its columns are named <value>_<measure>)."""
    columns, rows = table["columns"], table["rows"]
    pivot_position, measure_position = columns.index(pivot), columns.index(measure)
    other_positions = [i for i, name in enumerate(columns) if name in dimensions and name != pivot]
    pivot_values = []
    for row in rows:
        if row[pivot_position] not in pivot_values:
            pivot_values.append(row[pivot_position])
    cells = {}
    for row in rows:
        cells.setdefault(tuple(row[i] for i in other_positions), {})[row[pivot_position]] = row[measure_position]
    value_columns = [f"{value}_{measure}" for value in pivot_values]
    wide_rows = [list(key) + [by_value.get(value) for value in pivot_values] for key, by_value in cells.items()]
    other_names = [columns[i] for i in other_positions]
    return {"table": {"columns": other_names + value_columns, "rows": wide_rows},
            "spec": {"dimensions": other_names, "required": other_names + value_columns}}


def is_ordered(accepted_sql: str) -> bool:
    """A top-N (LIMIT) result is compared in order; everything else as a set of rows."""
    return re.search(r"\blimit\s+\d+", accepted_sql, re.IGNORECASE) is not None


# ---------------------------------------------------------------------------
# Cells and columns
# ---------------------------------------------------------------------------

def normalise(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time().isoformat() == "00:00:00" else value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


class ColumnRule:
    """How a column of the accepted result is compared: as a percentage (0.1 pp) or not, and the extra slack a rounded column gets
    (half a unit of its last kept place; 0 when the column is not rounded). Anywhere a bool `percent_column` is taken, this is too."""

    def __init__(self, percent: bool, half_unit: float = 0.0):
        self.percent, self.half_unit = bool(percent), half_unit

    def __bool__(self) -> bool:
        return self.percent


def rounding_half_unit(expected_values: list) -> float:
    """Half a unit of the last place the accepted query kept, for a column it rounded; else 0. A column counts as rounded when it has
    five or more values, all floats, and every one is a whole number (0.5) or has at most one decimal (0.05). Integers (counts) never do."""
    present = [v for v in expected_values if v is not None]
    if len(present) < 5 or not all(isinstance(v, (float, Decimal)) and not isinstance(v, bool) for v in present):
        return 0.0
    for decimals in (0, 1):
        if all(abs(float(v) - round(float(v), decimals)) < 1e-9 for v in present):
            return 0.5 * 10 ** -decimals
    return 0.0


def cells_match(expected: Any, got: Any, percent_column: Any) -> bool:
    half_unit = percent_column.half_unit if isinstance(percent_column, ColumnRule) else 0.0
    percent_column = bool(percent_column)
    expected, got = normalise(expected), normalise(got)
    if expected is None or got is None:
        return expected is None and got is None
    if isinstance(expected, bool) or isinstance(got, bool):
        return expected == got
    if isinstance(expected, float):
        if isinstance(got, str):
            try:
                got = float(got)
            except ValueError:
                return False
        if not isinstance(got, float):
            return False
        gap = abs(expected - got)
        if percent_column and gap <= cfg.MARKING_PCT_TOLERANCE:
            return True
        return gap <= max(cfg.MARKING_REL_TOLERANCE * abs(expected), ABSOLUTE_FLOOR, half_unit + 1e-9 if half_unit else 0.0)
    if isinstance(got, float):
        try:
            return abs(float(expected) - got) <= max(cfg.MARKING_REL_TOLERANCE * abs(got), ABSOLUTE_FLOOR)
        except ValueError:
            return False
    if len(expected) == 10 and re.match(r"\d{4}-\d{2}-\d{2}$", expected):
        return got[:10] == expected  # a date written with a time of day
    return expected.casefold() == got.casefold()


def sort_key(value: Any) -> tuple:
    value = normalise(value)
    if value is None:
        return (3, 0.0, "")
    if isinstance(value, bool):
        return (0, float(value), "")
    if isinstance(value, float):
        return (1, value, "")
    return (2, 0.0, value.casefold())


def columns_match(expected_values: list, got_values: list, percent_column: bool) -> bool:
    """Do two columns hold the same values, whatever the row order?"""
    if len(expected_values) != len(got_values):
        return False
    pairs = zip(sorted(expected_values, key=sort_key), sorted(got_values, key=sort_key))
    return all(cells_match(e, g, percent_column) for e, g in pairs)


def column_covers(expected_values: list, got_values: list, percent_column: bool) -> bool:
    """Does the returned column hold every expected value (each matched to its own cell), with room for extra cells?
    With equal lengths this is the same test as columns_match."""
    if len(got_values) < len(expected_values):
        return False
    if len(got_values) == len(expected_values):
        return columns_match(expected_values, got_values, percent_column)
    unused = sorted(got_values, key=sort_key)
    for value in sorted(expected_values, key=sort_key):
        for position, candidate in enumerate(unused):
            if cells_match(value, candidate, percent_column):
                del unused[position]
                break
        else:
            return False
    return True


def is_zero_or_empty(value: Any) -> bool:
    value = normalise(value)
    if value is None:
        return True
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return False
    return isinstance(value, float) and abs(value) <= ABSOLUTE_FLOOR


# ---------------------------------------------------------------------------
# Total rows
# ---------------------------------------------------------------------------

def text_columns(rows: list) -> set:
    """Positions of columns that hold text in at least one row (label columns)."""
    width = len(rows[0]) if rows else 0
    return {index for index in range(width) if any(isinstance(row[index], str) for row in rows)}


def is_total_row(row: list, label_positions: set) -> bool:
    """A row labelled as a total: a label cell that reads like a total, or is empty where other rows carry labels."""
    for index in label_positions:
        cell = row[index]
        if cell is None or (isinstance(cell, str) and (not cell.strip() or TOTAL_LABEL.search(cell))):
            return True
    return False


def expected_has_total_row(expected_rows: list) -> bool:
    return any(is_total_row(row, text_columns(expected_rows)) for row in expected_rows)


# ---------------------------------------------------------------------------
# Comparing tables
# ---------------------------------------------------------------------------

def _match_view(expected: dict, view_rows: list, width: int, required: list, dimensions: list, ordered: bool) -> tuple:
    """Match the expected table (restricted to its required columns) against one view of the returned rows.
    Extra returned rows are allowed only when every required measure in them is zero or empty."""
    expected_columns, expected_rows = expected["columns"], expected["rows"]
    if len(view_rows) < len(expected_rows):
        return False, f"{len(view_rows)} rows returned, {len(expected_rows)} expected"
    extra_rows = len(view_rows) - len(expected_rows)
    measure_names = [name for name in required if name not in dimensions]
    if extra_rows and (not dimensions or not measure_names):
        # Without row labels a zero-filled row cannot be told from a real one, so extra rows fail.
        return False, f"{len(view_rows)} rows returned, {len(expected_rows)} expected"
    positions = [expected_columns.index(name) for name in required]
    percent_flags = [ColumnRule(bool(PERCENT_COLUMN.search(name)), rounding_half_unit([row[position] for row in expected_rows]))
                     for name, position in zip(required, positions)]
    candidates = []
    for name, position, flag in zip(required, positions, percent_flags):
        expected_values = [row[position] for row in expected_rows]
        found = [index for index in range(width) if column_covers(expected_values, [row[index] for row in view_rows], flag)]
        if not found:
            return False, f"no returned column holds the values of expected column '{name}'"
        candidates.append(found)
    measure_slots = [slot for slot, name in enumerate(required) if name not in dimensions]
    projected_expected = [[row[position] for position in positions] for row in expected_rows]
    for assignment in itertools.islice(itertools.product(*candidates), MAX_COLUMN_ASSIGNMENTS):
        if len(set(assignment)) < len(assignment):
            continue
        projected = [[row[index] for index in assignment] for row in view_rows]
        zero_rows = {i for i, row in enumerate(projected) if all(is_zero_or_empty(row[slot]) for slot in measure_slots)}
        if rows_match_with_extras(projected_expected, projected, percent_flags, ordered, zero_rows, extra_rows):
            return True, "match"
    return False, "columns found but the rows do not line up" + (" in order" if ordered else "")


def rows_match_with_extras(expected_rows: list, got_rows: list, percent_flags: list, ordered: bool,
                           ignorable: set, extra_rows: int) -> bool:
    """Every expected row matched to its own returned row; the returned rows left over must all be ignorable (zero-filled)."""
    if extra_rows == 0:
        return rows_match(expected_rows, got_rows, percent_flags, ordered)
    if ordered:
        kept = [row for i, row in enumerate(got_rows) if i not in ignorable]
        return len(kept) == len(expected_rows) and rows_match(expected_rows, kept, percent_flags, True)

    def same(expected_row: list, got_row: list) -> bool:
        return all(cells_match(e, g, flag) for e, g, flag in zip(expected_row, got_row, percent_flags))
    unmatched = list(range(len(got_rows)))
    # Match against non-ignorable rows first, so a zero row is never used in place of a real one.
    unmatched.sort(key=lambda i: i in ignorable)
    for expected_row in expected_rows:
        for position in unmatched:
            if same(expected_row, got_rows[position]):
                unmatched.remove(position)
                break
        else:
            return False
    return all(position in ignorable for position in unmatched)


FUSED_FISCAL_LABEL = re.compile(r"^\s*FY\s*(\d{4}/\d{2})\s*[-_:,]?\s*([PQW])\s*0*(\d{1,2})\s*$", re.IGNORECASE)


def split_fused_fiscal_columns(columns: list, rows: list) -> tuple:
    """Marker version 5. A column in which EVERY cell is a fiscal year joined to a period, quarter or week ("FY2025/26 P07") is
    split into two more columns appended on the right: the year as the warehouse writes it ("FY2025/26") and the number as an
    integer. The fused column stays where it was (an extra column is tolerated); the new columns are then matched by their values
    like any other. Returns (columns, rows, number of fused columns split)."""
    if not rows:
        return columns, rows, 0
    fused_positions = []
    for index in range(len(columns)):
        cells = [row[index] for row in rows]
        if all(isinstance(cell, str) and FUSED_FISCAL_LABEL.match(cell) for cell in cells):
            fused_positions.append(index)
    if not fused_positions:
        return columns, rows, 0
    new_columns, new_rows = list(columns), [list(row) for row in rows]
    for index in fused_positions:
        new_columns += [f"{columns[index]} (fiscal year)", f"{columns[index]} (number)"]
        for row, original in zip(new_rows, rows):
            parts = FUSED_FISCAL_LABEL.match(original[index])
            row += [f"FY{parts.group(1)}", int(parts.group(3))]
    return new_columns, new_rows, len(fused_positions)


def compare_tables(expected: dict, got: Any, ordered: bool, spec: Optional[dict] = None) -> tuple:
    """Returns (matches, reason). `got` is the model's `result` object. `spec` is a pilot answer spec (see
    PILOT_ANSWER_SPECS); without one every expected column is required and zero-filled rows are not recognised."""
    if not isinstance(got, dict) or not isinstance(got.get("rows"), list) or not isinstance(got.get("columns"), list):
        return False, "result is not a table"
    expected_columns, expected_rows = expected["columns"], expected["rows"]
    got_rows = got["rows"]
    if any(not isinstance(row, list) for row in got_rows):
        return False, "rows are not lists"
    width = len(got["columns"])
    if any(len(row) != width for row in got_rows):
        return False, "rows differ in width from the columns"
    aliases = (spec or {}).get("label_aliases")
    if aliases:
        # a label the request words differently ("Store" for "Stores") is read as the canonical one, in every cell
        canonical = {alias.casefold(): label for label, names in aliases.items() for alias in names}
        got_rows = [[canonical.get(cell.strip().casefold(), cell) if isinstance(cell, str) else cell for cell in row] for row in got_rows]
    if not expected_rows:
        return (True, "both empty") if not got_rows else (False, f"{len(got_rows)} rows returned, 0 expected")
    # a fiscal year joined to its period, quarter or week in one label is read as the two separate columns (marker version 5)
    split_columns, got_rows, fused_count = split_fused_fiscal_columns(list(got["columns"]), got_rows)
    width = len(split_columns)
    first_reason = None
    for required in required_variants((spec or {}).get("required", expected_columns), expected_columns):
        dimensions = [name for name in (spec or {}).get("dimensions", []) if name in required]
        matches, reason = _compare_with(expected, got_rows, width, required, dimensions, ordered)
        if matches:
            if fused_count:
                reason += " [fused fiscal label read as separate year and number]"
            return True, reason
        first_reason = first_reason or reason
    return False, first_reason


def required_variants(required_spec: list, expected_columns: list) -> list:
    """The lists of expected columns an answer may be asked to carry. An item is a column name, or a list of names of which ONE
    is enough (a store's name or its ID, a week's number or its start date). Names the accepted result does not have are dropped.
    Returns every combination, so an answer passes if it passes with any of them."""
    choices = []
    for item in required_spec:
        options = [name for name in (item if isinstance(item, (list, tuple)) else [item]) if name in expected_columns]
        if options:
            choices.append(options)
    variants = []
    for combination in itertools.product(*choices):
        if len(set(combination)) == len(combination) and list(combination) not in variants:
            variants.append(list(combination))
    return variants or [list(expected_columns)]


def _compare_with(expected: dict, got_rows: list, width: int, required: list, dimensions: list, ordered: bool) -> tuple:
    """compare_tables for one choice of required columns: try the returned table as it is, then with total rows ignored."""
    expected_rows = expected["rows"]
    # The views of the returned table to try, most literal first.
    views = [("", got_rows)]
    labels = text_columns(got_rows)
    totals = [i for i, row in enumerate(got_rows) if is_total_row(row, labels)] if labels else []
    if totals and not expected_has_total_row(expected_rows):
        if len(expected_rows) == 1 and not dimensions:
            # One figure for the whole scope: it may sit on the total row, never on a breakdown row.
            views += [("figure taken from the total row", [got_rows[i]]) for i in totals]
        else:
            views.append(("total row ignored", [row for i, row in enumerate(got_rows) if i not in totals]))

    first_reason = None
    for note, view_rows in views:
        ok, reason = _match_view(expected, view_rows, width, required, dimensions, ordered)
        if ok:
            details = [note] if note else []
            if len(view_rows) > len(expected_rows):
                details.append(f"{len(view_rows) - len(expected_rows)} zero-filled row(s) ignored")
            extra_columns = width - len(required)
            if extra_columns:
                details.append(f"{extra_columns} extra column{'s' if extra_columns != 1 else ''}")
            return True, "match" + (f" ({'; '.join(details)})" if details else "")
        first_reason = first_reason or reason
    return False, first_reason


def rows_match(expected_rows: list, got_rows: list, percent_flags: list, ordered: bool) -> bool:
    def same(expected_row: list, got_row: list) -> bool:
        return all(cells_match(e, g, flag) for e, g, flag in zip(expected_row, got_row, percent_flags))
    if ordered:
        return all(same(e, g) for e, g in zip(expected_rows, got_rows))
    unmatched = list(range(len(got_rows)))
    for expected_row in expected_rows:
        for position in unmatched:
            if same(expected_row, got_rows[position]):
                unmatched.remove(position)
                break
        else:
            return False
    return True


# ---------------------------------------------------------------------------
# Marking one run
# ---------------------------------------------------------------------------

def mark_run(summary: dict, expected: dict, ordered: bool, spec: Optional[dict] = None,
             alternatives: Optional[list] = None) -> dict:
    """Mark one run summary from the harness. Outcomes: correct, wrong, no_answer. `expected` is the accepted table;
    `alternatives` the accepted alternatives ({"label", "table"}) from compute_expected_set."""
    answer = summary.get("answer")
    if summary["status"] != "ok" or answer is None:
        return {"outcome": "no_answer", "reason": f"{summary['status']}: {summary.get('problem') or 'no answer'}"}
    matches, reason = compare_tables(expected, answer["result"], ordered, spec)
    if matches:
        return {"outcome": "correct", "reason": reason}
    alternative_reasons = []
    for alternative in alternatives or []:
        # a wide alternative has its own columns, so its own spec; the label aliases still apply
        alternative_spec = dict(alternative["wide_spec"], **({"label_aliases": spec["label_aliases"]} if spec and "label_aliases" in spec else {})) \
            if alternative.get("wide_spec") else spec
        alt_matches, alt_reason = compare_tables(alternative["table"], answer["result"], ordered, alternative_spec)
        if alt_matches:
            return {"outcome": "correct", "reason": f"{alt_reason}; accepted alternative: {alternative['label']}"}
        alternative_reasons.append(f"{alternative['label']}: {alt_reason}")
    if alternative_reasons:
        reason += " (against the alternatives: " + "; ".join(alternative_reasons) + ")"
    return {"outcome": "wrong", "reason": reason}


# ---------------------------------------------------------------------------
# Agent runs (15 Oct 2026): mark the run logs written by collect_agent_answer.py
# ---------------------------------------------------------------------------

def failure_kind(reason: str) -> str:
    """A short label for a failed mark, so the wrong runs can be grouped (the reason strings come from compare_tables)."""
    if reason.startswith("no_answer") or reason.startswith("agent_error") or "malformed" in reason[:40]:
        return "no usable answer"
    if reason.startswith("result is not a table") or reason.startswith("rows"):
        return "table shape"
    if "no returned column holds the values" in reason:
        return "a required column's values differ or are missing"
    if "rows returned" in reason:
        return "row count"
    if "do not line up" in reason:
        return "values or order differ"
    return "other"


def read_agent_log_summary(log_path: Path) -> Optional[dict]:
    """The run_end summary of an agent run log, or None if the log has none."""
    import json
    summary = None
    for line in Path(log_path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            event = json.loads(line)
            if event.get("event") == "run_end":
                summary = event
    return summary


def agent_log_files(logs_dir: Path) -> list:
    """The run logs in a folder: <run_id>.jsonl, not the earlier attempts and not the index."""
    return sorted(path for path in Path(logs_dir).glob("*.jsonl")
                  if path.name != "runs_index.jsonl" and ".attempt" not in path.name)


def mark_agent_runs(logs_dir: Path, out_dir: Path, warehouse_path: Path = cfg.WAREHOUSE_PATH, quiet: bool = False,
                    run_prefix: Optional[str] = None) -> dict:
    """Mark every finished agent run in logs_dir against its dev request's accepted result, answer spec and alternatives.
    Writes agent_results.jsonl, expected_results.json, agent_summary.json and agent_summary.txt to out_dir (never into logs_dir)
    and returns the summary. Test requests (REQ-T) are not marked here: they wait for the Phase 6 marker."""
    import json
    from harness import load_dev_requests
    logs_dir, out_dir = Path(logs_dir), Path(out_dir)
    if logs_dir.resolve() == out_dir.resolve():
        raise SystemExit("Marking writes to a new folder: --out-dir must differ from the folder holding the run logs.")
    import run_pilot
    run_pilot.assert_output_is_safe(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    say = (lambda *a, **k: None) if quiet else print
    dev = load_dev_requests()
    expected_path = out_dir / "expected_results.json"
    expected = json.loads(expected_path.read_text(encoding="utf-8")) if expected_path.exists() else {}
    results, skipped = [], []
    for log_path in agent_log_files(logs_dir):
        if run_prefix and not log_path.name.startswith(run_prefix):
            continue         # another set's log in the same folder (pilot 2's logs sit beside pilot 3's)
        summary = read_agent_log_summary(log_path)
        if summary is None:
            skipped.append(f"{log_path.name}: no run_end event (unfinished log)")
            continue
        request_id = summary["request_id"]
        if request_id not in dev:
            skipped.append(f"{log_path.name}: {request_id} is not a dev request; test requests wait for the Phase 6 marker")
            continue
        if expected.get(request_id, {}).get("marker_version") != MARKER_VERSION:
            say(f"Computing the accepted result of {request_id} and its accepted alternatives ...")
            expected[request_id] = compute_expected_set(warehouse_path, request_id, dev[request_id]["accepted_sql"])
        entry_expected = expected[request_id]
        mark = mark_run(summary, entry_expected["table"], entry_expected["ordered"], spec=answer_spec(request_id),
                        alternatives=entry_expected.get("alternatives", []))
        returned = (summary.get("answer") or {}).get("result") or {}
        results.append({
            "run_id": summary["run_id"], "model": summary["model_alias"], "arm": summary["arm"], "request_id": request_id,
            "status": summary["status"], "outcome": mark["outcome"], "reason": mark["reason"],
            "failure_kind": None if mark["outcome"] == "correct" else failure_kind(mark["reason"]),
            "marker_version": MARKER_VERSION, "queries_used": summary["queries_used"], "scripts_run": summary["scripts_run"],
            "refused_query_calls": summary.get("refused_query_calls", 0), "total_tokens": (summary.get("tokens") or {}).get("total_tokens"),
            "tool_calls_reported": summary.get("tool_calls_reported"), "elapsed_s": summary.get("elapsed_s"),
            "final_sql_was_run": summary.get("final_sql_was_run"),
            "returned_columns": returned.get("columns"), "returned_rows_head": (returned.get("rows") or [])[:6],
            "returned_row_count": len(returned.get("rows") or []),
            "expected_columns": entry_expected["table"]["columns"], "expected_rows_head": entry_expected["table"]["rows"][:6],
            "expected_row_count": len(entry_expected["table"]["rows"]),
            "caveats": (summary.get("answer") or {}).get("caveats"), "assumptions": (summary.get("answer") or {}).get("assumptions"),
        })
    expected_path.write_text(json.dumps(expected, indent=1, ensure_ascii=False), encoding="utf-8")
    (out_dir / "agent_results.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in results), encoding="utf-8")
    summary_dict = build_agent_summary(results, skipped)
    (out_dir / "agent_summary.json").write_text(json.dumps(summary_dict, indent=1, ensure_ascii=False), encoding="utf-8")
    text = format_agent_summary(summary_dict, results)
    (out_dir / "agent_summary.txt").write_text(text, encoding="utf-8")
    say(text)
    say(f"\nMarked results and summary are in {out_dir}")
    return summary_dict


def build_agent_summary(results: list, skipped: list) -> dict:
    def mean(values: list):
        values = [v for v in values if v is not None]
        return sum(values) / len(values) if values else None
    cells = {}
    for entry in results:
        cells.setdefault((entry["model"], entry["arm"]), []).append(entry)
    by_cell = {}
    for (model, arm), entries in sorted(cells.items()):
        by_cell[f"{model}/{arm}"] = {
            "runs": len(entries), "correct": sum(e["outcome"] == "correct" for e in entries),
            "wrong": sum(e["outcome"] == "wrong" for e in entries), "no_answer": sum(e["outcome"] == "no_answer" for e in entries),
            "mean_queries": mean([e["queries_used"] for e in entries]), "mean_total_tokens": mean([e["total_tokens"] for e in entries]),
            "mean_tool_calls": mean([e["tool_calls_reported"] for e in entries]), "mean_seconds": mean([e["elapsed_s"] for e in entries]),
            "final_sql_never_ran": sum(e["final_sql_was_run"] is False for e in entries),
        }
    kinds = {}
    for entry in results:
        if entry["failure_kind"]:
            kinds[entry["failure_kind"]] = kinds.get(entry["failure_kind"], 0) + 1
    return {"marker_version": MARKER_VERSION, "runs_marked": len(results), "by_cell": by_cell, "failure_kinds": kinds, "skipped": skipped,
            "correct_total": sum(e["outcome"] == "correct" for e in results)}


def format_agent_summary(summary: dict, results: list) -> str:
    lines = [f"Agent runs marked with marker version {summary['marker_version']}: {summary['correct_total']} correct of {summary['runs_marked']}.", ""]
    lines.append("By model and arm:")
    lines.append("  cell             correct  wrong  none   queries  tool calls  tokens      seconds")

    def num(value, fmt="{:.1f}"):
        return "-" if value is None else fmt.format(value)
    for cell, data in summary["by_cell"].items():
        lines.append(f"  {cell:<16} {data['correct']:>2} of {data['runs']:<2}  {data['wrong']:>5}  {data['no_answer']:>4}   {num(data['mean_queries']):>7}  "
                     f"{num(data['mean_tool_calls']):>10}  {num(data['mean_total_tokens'], '{:,.0f}'):>10}  {num(data['mean_seconds'], '{:.0f}'):>7}")
    requests = sorted({r["request_id"] for r in results})
    cell_names = list(summary["by_cell"])
    lines += ["", "By request (c = correct, x = wrong, - = no answer):", "  request   " + "  ".join(f"{name:<14}" for name in cell_names)]
    for request_id in requests:
        marks = []
        for name in cell_names:
            model, arm = name.split("/")
            hit = [r for r in results if r["request_id"] == request_id and r["model"] == model and r["arm"] == arm]
            marks.append(("c" if hit[0]["outcome"] == "correct" else "x" if hit[0]["outcome"] == "wrong" else "-") if hit else " ")
        lines.append(f"  {request_id:<9} " + "  ".join(f"{mark:<14}" for mark in marks))
    if summary["failure_kinds"]:
        lines += ["", "Why the others failed: " + "; ".join(f"{kind} {count}" for kind, count in sorted(summary["failure_kinds"].items()))]
    wrong = [r for r in results if r["outcome"] != "correct"]
    if wrong:
        lines += ["", "Runs not marked correct (returned table against the accepted one, first rows):"]
        for entry in wrong:
            lines.append(f"  {entry['run_id']}: {entry['outcome']} - {entry['reason']}")
            lines.append(f"      returned {entry['returned_columns']} ({entry['returned_row_count']} rows) {entry['returned_rows_head'][:3]}")
            lines.append(f"      expected {entry['expected_columns']} ({entry['expected_row_count']} rows) {entry['expected_rows_head'][:3]}")
    for note in summary["skipped"]:
        lines.append(f"  skipped {note}")
    return "\n".join(lines)


def main(argv: list = None) -> int:
    import argparse
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Mark agent-run logs against the dev requests' accepted results (pilot marker).")
    commands = parser.add_subparsers(dest="command", required=True)
    agent = commands.add_parser("agent", help="mark the run logs in a folder")
    agent.add_argument("--logs", type=Path, default=cfg.AGENT_LOGS_DIR, help="folder of run logs (default data/agent_runs/logs)")
    agent.add_argument("--set", dest="set_name", default=cfg.PILOT2_NAME,
                       help="which set of runs to mark: the logs whose run id starts with '<set>-' (default pilot2; pilot3 for pilot 3)")
    agent.add_argument("--out-dir", type=Path, default=None,
                       help="where the marked results go (default data/agent_runs/marked/<set>)")
    args = parser.parse_args(argv)
    out_dir = args.out_dir or (cfg.AGENT_MARKED_DIR / args.set_name)
    mark_agent_runs(args.logs, out_dir, run_prefix=f"{args.set_name}-")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
