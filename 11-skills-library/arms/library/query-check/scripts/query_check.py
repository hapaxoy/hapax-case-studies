"""
query_check.py - run a query against the Tuomimetsä warehouse and check it before the answer goes out.

Usage:
    conda run -n <env> python query_check.py PATH_TO_DUCKDB --file my_query.sql [options]
    conda run -n <env> python query_check.py PATH_TO_DUCKDB --sql "SELECT ..." [options]

What it reports:
    1. Row count (and a preview of the first rows).
    2. Duplicate keys at the grain you declare with --grain col1,col2.
    3. Date coverage: the dates the result actually covers against the range you asked for
       (--start/--end or --period "FY2026/27 P05"), missing days and whether they were trading days,
       the warehouse load point (CAL-DATA-THROUGH), and the UTC/Helsinki edge: how many rows in the
       warehouse sit on the requested boundaries with a different UTC date than Helsinki date
       (DEF-TIMEZONE, REG-UTC). With --ts-col it also checks a UTC timestamp column in your result.
    4. Use of a deprecated table or column (REG-DEPRECATED, REG-LEGACY-VIEW, REG-MIGRATION),
       plus a few lints for the house rules (exclusions, web revenue date, SCD joins, UTC casts).
    5. With --control: the gap between your figures and the control total in rpt_daily_store_sales
       for the same days (REG-CONTROL-TOTAL, TEAM-CONTROL-TOTALS), by store and/or day when your
       result has those columns.

Options:
    --grain COLS            comma-separated columns that should be unique in the result
    --date-col COL          date column in the result (default: first of business_date, calendar_date,
                            sale_date, return_date, dispatch_date, order_date, week_ending_date, as_of_end)
    --start D --end D       requested range, YYYY-MM-DD, Helsinki business dates
    --period LABEL          requested range from ref_fiscal_calendar, e.g. "FY2026/27 P05"
    --ts-col COL            a UTC timestamp column in the result to check against the Helsinki range
    --control               compare with rpt_daily_store_sales over the requested range
    --value-col COL         result column holding the figure (default: net_sales, then net_sales_before_returns)
    --control-measure M     net_sales | net_sales_before_returns | returns_net | receipts | units_sold
                            (default: the value column's name if it is one of these, else net_sales)
    --store-col COL         store_id column in the result (default: store_id if present)
    --control-stores S      all | physical | web | comma-separated store_ids (default: all; physical = below 900)
    --tolerance X           allowed absolute gap per compared cell (default 0.01)
    --show N                rows to preview (default 10)
    --json                  machine-readable report

Exit code 0 when nothing failed, 1 when a check failed (duplicates, deprecated object, control gap,
query error), 2 for bad arguments. Standard library plus duckdb only; the database is opened read-only.
"""

import argparse
import collections
import datetime as dt
import decimal
import json
import re
import sys
import time

try:
    import duckdb
except ImportError:
    sys.exit("query_check.py needs the duckdb package (conda run -n <env> ...).")


# ---------------------------------------------------------------------------
# House knowledge used by the checks (each line names the world fact it comes from)
# ---------------------------------------------------------------------------

# REG-DEPRECATED, REG-LEGACY-VIEW, TEAM-NO-LEGACY-VIEW
DEPRECATED_TABLE_PATTERNS = [
    (r"\bdim_store_old\b", "dim_store_old: flat table from before history was kept (REG-DEPRECATED). Use dim_store."),
    (r"\bdim_product_old\b", "dim_product_old: flat table from before history was kept (REG-DEPRECATED). Use dim_product."),
    (r"\bstg_\w+", "staging table (stg_*) (REG-DEPRECATED)."),
    (r"\bbak_\w+", "dated backup table (bak_*) (REG-DEPRECATED)."),
    (r"\btmp_\w+", "temporary table (tmp_*) (REG-DEPRECATED)."),
    (r"\brpt_weekly_sales_by_region\b", "rpt_weekly_sales_by_region: stopped refreshing on 27 April 2025 and uses the old regions (REG-DEPRECATED)."),
    (r"\bv_daily_sales\b", "rpt.v_daily_sales: built on channel_code, silently loses web sales from 3 November 2025 (REG-LEGACY-VIEW, TEAM-NO-LEGACY-VIEW)."),
    (r"\bv_weekly_store_sales\b", "rpt.v_weekly_store_sales: built on rpt.v_daily_sales, same web gap (REG-LEGACY-VIEW)."),
]

# REG-MIGRATION, REG-STORE-900
DEPRECATED_COLUMN_PATTERNS = [
    (r"\bchannel_code\b", "channel_code stops being filled from 3 November 2025 (REG-MIGRATION). Tell web lines apart "
                          "by store_id = 900 (REG-STORE-900); for click-and-collect use fact_web_order.fulfilment_type."),
]

CONTROL_MEASURES = ("net_sales", "net_sales_before_returns", "returns_net", "receipts", "units_sold")
DATE_COLUMN_GUESSES = ("business_date", "calendar_date", "sale_date", "return_date", "dispatch_date",
                       "order_date", "week_ending_date", "as_of_end")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def strip_comments(sql):
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", sql)


def strip_literals(sql):
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def to_number(value):
    if value is None:
        return 0.0
    if isinstance(value, decimal.Decimal):
        return float(value)
    return float(value)


def to_date(value):
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def wrap(sql):
    """Use the query as a subquery; the newline protects a trailing -- comment."""
    return f"SELECT * FROM (\n{sql}\n) AS checked_query"


class Report:
    """Collects check results as (section, status, message) and prints them."""

    def __init__(self):
        self.items = []

    def add(self, section, status, message):
        self.items.append({"section": section, "status": status, "message": message})

    def failed(self):
        return any(item["status"] == "FAIL" for item in self.items)

    def print_text(self):
        current = None
        for item in self.items:
            if item["section"] != current:
                current = item["section"]
                print(f"\n== {current} ==")
            print(f"  [{item['status']}] {item['message']}")


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def lint_sql(sql, report):
    """Static checks on the SQL text: deprecated objects and house-rule lints."""
    no_comments = strip_comments(sql)
    code = strip_literals(no_comments)
    lowered = code.lower()

    found = False
    for pattern, message in DEPRECATED_TABLE_PATTERNS:
        hits = sorted(set(re.findall(pattern, lowered)))
        if hits:
            found = True
            report.add("Deprecated objects", "FAIL", f"{', '.join(hits)} -> {message}")
    for pattern, message in DEPRECATED_COLUMN_PATTERNS:
        if re.search(pattern, lowered):
            found = True
            report.add("Deprecated objects", "WARN", message)
    if not found:
        report.add("Deprecated objects", "PASS", "No deprecated table, view or column referenced.")

    # Lints on house rules. These are warnings: a request may ask for something different (TEAM-EXPLICIT-REQUEST).
    text_with_literals = no_comments.lower()
    uses_sales = re.search(r"\bfact_sales_line\b|\bfact_return_line\b", lowered) is not None
    if uses_sales:
        excludes_999 = re.search(r"999|<\s*900|store_id\s*=\s*900|between\s+\d+\s+and\s+8\d\d", text_with_literals)
        excludes_test = "zz test" in text_with_literals
        if not excludes_999:
            report.add("House-rule lints", "WARN", "Sales lines used without a filter on store 999 "
                       "(REG-STORE-999, TEAM-EXCLUSIONS).")
        if not excludes_test:
            report.add("House-rule lints", "WARN", "Sales lines used without a filter on category 'ZZ Test' "
                       "(REG-TEST-SKU, TEAM-EXCLUSIONS).")
        mentions_web = re.search(r"store_id\s*(=|in\s*\()\s*900|\bweb\b", text_with_literals) is not None
        if mentions_web and "fact_web_order" not in lowered and "sale_date" in lowered:
            report.add("House-rule lints", "WARN", "Web lines appear to be dated by sale_date (the order date). "
                       "Web net sales are recognised on the Helsinki dispatch date from fact_web_order "
                       "(DEF-WEB-RECOGNITION, REG-WEB-SALE-DATE).")
    # UTC timestamps turned into dates without a time-zone conversion (DEF-TIMEZONE, REG-UTC)
    for match in re.finditer(r"(cast\s*\(\s*[\w.]*_ts_utc\s+as\s+date\s*\)|[\w.]*_ts_utc\s*::\s*date|"
                             r"date_trunc\s*\(\s*'\w+'\s*,\s*[\w.]*_ts_utc\s*\)|\bhour\s*\(\s*[\w.]*_ts_utc\s*\))", lowered):
        report.add("House-rule lints", "WARN", f"'{match.group(0)}' reads a UTC timestamp without converting to "
                   "Helsinki time; use timezone('Europe/Helsinki', col AT TIME ZONE 'UTC') (DEF-TIMEZONE, REG-UTC).")
    # SCD joins on a natural key without a version rule (REG-SCD-KEYS)
    for match in re.finditer(r"join\s+(dim_store|dim_product|dim_member)\s+(?:as\s+)?(\w+)\s+on\s+(.*?)(?=\bjoin\b|\bwhere\b|\bgroup\b|\border\b|\)|$)",
                             lowered, flags=re.DOTALL):
        table, alias, condition = match.group(1), match.group(2), match.group(3)
        natural = {"dim_store": "store_id", "dim_product": "sku", "dim_member": "member_id"}[table]
        if re.search(rf"\b{alias}\.{natural}\b", condition) and not re.search(r"is_current|valid_from|valid_to", condition):
            report.add("House-rule lints", "WARN", f"{table} {alias} is joined on {natural} without is_current or "
                       "validity dates; one row per version will multiply rows (REG-SCD-KEYS).")
    if not any(item["section"] == "House-rule lints" for item in report.items):
        report.add("House-rule lints", "PASS", "No lint warnings.")


def run_query(con, sql, report):
    started = time.time()
    try:
        result = con.execute(sql)
    except Exception as error:
        report.add("Query", "FAIL", f"Query failed: {error}")
        return None, None
    columns = [d[0] for d in result.description]
    rows = result.fetchall()
    report.add("Query", "PASS", f"Ran in {time.time() - started:.1f} s.")
    return columns, rows


def check_rows(columns, rows, report, show):
    status = "PASS" if rows else "WARN"
    report.add("Row count", status, f"{len(rows)} rows, {len(columns)} columns: {', '.join(columns)}")
    preview = []
    for row in rows[:show]:
        preview.append(" | ".join("" if v is None else str(v) for v in row))
    return preview


def check_grain(columns, rows, grain, report):
    if not grain:
        report.add("Duplicate keys", "INFO", "No grain declared (use --grain col1,col2).")
        return
    missing = [g for g in grain if g not in columns]
    if missing:
        report.add("Duplicate keys", "FAIL", f"Grain column(s) not in the result: {', '.join(missing)}.")
        return
    index = [columns.index(g) for g in grain]
    counts = collections.Counter(tuple(row[i] for i in index) for row in rows)
    duplicated = [(key, n) for key, n in counts.items() if n > 1]
    if not duplicated:
        report.add("Duplicate keys", "PASS", f"Unique at grain ({', '.join(grain)}): {len(counts)} keys.")
        return
    extra_rows = sum(n - 1 for _, n in duplicated)
    sample = "; ".join(f"{key} x{n}" for key, n in sorted(duplicated, key=lambda kv: -kv[1])[:5])
    report.add("Duplicate keys", "FAIL", f"{len(duplicated)} keys appear more than once at grain "
               f"({', '.join(grain)}), {extra_rows} surplus rows. Examples: {sample}")


def requested_range(con, args):
    if args.period:
        row = con.execute(
            "SELECT period_start_date, period_end_date FROM ref_fiscal_calendar WHERE fiscal_period_label = ?",
            [args.period.strip()],
        ).fetchone()
        if row is None:
            sys.exit(f"--period {args.period!r} not found in ref_fiscal_calendar (format: 'FY2026/27 P05').")
        return row[0], row[1]
    if args.start and args.end:
        try:
            return dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.end)
        except ValueError:
            sys.exit("--start and --end must be YYYY-MM-DD.")
    if args.start or args.end:
        sys.exit("Give both --start and --end, or --period.")
    return None, None


def check_dates(con, columns, rows, args, start, end, report):
    section = "Date coverage"
    loaded_to = con.execute("SELECT MAX(calendar_date) FROM dim_date").fetchone()[0]

    # the requested range itself
    if start:
        days = (end - start).days + 1
        cal = con.execute(
            "SELECT MIN(fiscal_week_start_date), MAX(fiscal_week_end_date), "
            "string_agg(DISTINCT fiscal_period_label, ', ') FROM dim_date WHERE calendar_date BETWEEN ? AND ?",
            [start, end]).fetchone()
        report.add(section, "INFO", f"Requested {start} to {end} ({days} days; fiscal: {cal[2]}).")
        if start.isoweekday() != 1 or end.isoweekday() != 7:
            report.add(section, "WARN", "Requested range is not whole fiscal weeks (Monday to Sunday) "
                       "(CAL-YEAR). Fine for daily requests; check it for weekly or period figures.")
        if end > loaded_to:
            report.add(section, "WARN", f"Requested range ends after the last loaded date {loaded_to} "
                       "(CAL-DATA-THROUGH). The figures are incomplete.")
        edge_report(con, start, end, report)

    # what the result covers
    date_col = args.date_col
    if not date_col:
        date_col = next((c for c in DATE_COLUMN_GUESSES if c in columns), None)
    if date_col and date_col not in columns:
        report.add(section, "FAIL", f"--date-col {date_col} is not in the result.")
        return
    if date_col and rows:
        index = columns.index(date_col)
        dates = sorted({d for d in (to_date(row[index]) for row in rows) if d is not None})
        if not dates:
            report.add(section, "WARN", f"{date_col} holds no dates.")
        else:
            report.add(section, "INFO", f"Result covers {dates[0]} to {dates[-1]} on {date_col} "
                       f"({len(dates)} distinct dates).")
            if start:
                outside = [d for d in dates if d < start or d > end]
                if outside:
                    report.add(section, "FAIL", f"{len(outside)} dates outside the requested range, e.g. "
                               f"{', '.join(map(str, outside[:5]))}.")
                inside = set(dates)
                missing = []
                cursor = start
                while cursor <= min(end, loaded_to):
                    if cursor not in inside:
                        missing.append(cursor)
                    cursor += dt.timedelta(days=1)
                if missing and len(dates) > 1:
                    flags = dict(con.execute(
                        "SELECT calendar_date, is_trading_day FROM dim_date WHERE calendar_date BETWEEN ? AND ?",
                        [start, end]).fetchall())
                    trading_missing = [d for d in missing if flags.get(d, True)]
                    closed_missing = [d for d in missing if not flags.get(d, True)]
                    if closed_missing:
                        report.add(section, "INFO", f"{len(closed_missing)} missing dates are closed days "
                                   f"(is_trading_day false, CAL-CLOSED-DAYS): {', '.join(map(str, closed_missing[:8]))}.")
                    if trading_missing:
                        report.add(section, "WARN", f"{len(trading_missing)} trading days in the range have no rows: "
                                   f"{', '.join(map(str, trading_missing[:8]))}{' ...' if len(trading_missing) > 8 else ''}.")
                if not outside and not missing:
                    report.add(section, "PASS", "Every day of the requested range is present, none outside it.")
    elif start:
        report.add(section, "INFO", "No date column in the result; coverage judged from the SQL only. "
                   "Use --date-col, or add the date to the output while checking.")

    # a UTC timestamp column in the result, read against the Helsinki range
    if args.ts_col:
        if args.ts_col not in columns:
            report.add(section, "FAIL", f"--ts-col {args.ts_col} is not in the result.")
            return
        sql = (f"SELECT CAST(timezone('Europe/Helsinki', q.{args.ts_col} AT TIME ZONE 'UTC') AS DATE) AS helsinki_date, "
               f"CAST(q.{args.ts_col} AS DATE) AS utc_date, COUNT(*) FROM ({args.sql_text}\n) AS q GROUP BY ALL")
        pairs = con.execute(sql).fetchall()
        shifted = sum(n for h, u, n in pairs if h != u)
        report.add(section, "INFO", f"{shifted} result rows have a different Helsinki date than UTC date on {args.ts_col}.")
        if start:
            outside = sum(n for h, u, n in pairs if h is not None and (h < start or h > end))
            if outside:
                report.add(section, "FAIL", f"{outside} rows fall outside the requested range in Helsinki time: "
                           "the range was probably applied to the UTC date (DEF-TIMEZONE).")


def edge_report(con, start, end, report):
    """Rows near the requested boundaries whose UTC date differs from their Helsinki date."""
    sources = [
        ("fact_web_order.order_ts_utc", "fact_web_order", "order_ts_utc"),
        ("fact_web_order.dispatch_ts_utc", "fact_web_order", "dispatch_ts_utc"),
        ("fact_sales_line.sale_ts_utc", "fact_sales_line", "sale_ts_utc"),
        ("fact_return_line.return_ts_utc", "fact_return_line", "return_ts_utc"),
    ]
    lines = []
    for label, table, column in sources:
        sql = f"""
            WITH t AS (
                SELECT CAST(timezone('Europe/Helsinki', {column} AT TIME ZONE 'UTC') AS DATE) AS h,
                       CAST({column} AS DATE) AS u
                FROM {table}
                WHERE {column} BETWEEN CAST(? AS TIMESTAMP) - INTERVAL 1 DAY AND CAST(? AS TIMESTAMP) + INTERVAL 2 DAY
                   OR {column} BETWEEN CAST(? AS TIMESTAMP) - INTERVAL 1 DAY AND CAST(? AS TIMESTAMP) + INTERVAL 2 DAY
            )
            SELECT SUM(CASE WHEN h BETWEEN ? AND ? AND NOT (u BETWEEN ? AND ?) THEN 1 ELSE 0 END),
                   SUM(CASE WHEN u BETWEEN ? AND ? AND NOT (h BETWEEN ? AND ?) THEN 1 ELSE 0 END)
            FROM t"""
        params = [start, start, end, end] + [start, end] * 4
        inside_helsinki_only, inside_utc_only = con.execute(sql, params).fetchone()
        inside_helsinki_only = inside_helsinki_only or 0
        inside_utc_only = inside_utc_only or 0
        if inside_helsinki_only or inside_utc_only:
            lines.append(f"{label}: {inside_helsinki_only} rows in the range only in Helsinki time, "
                         f"{inside_utc_only} only in UTC")
    if lines:
        report.add("Date coverage", "INFO", "UTC/Helsinki edge (rows that move if the day boundary is taken at "
                   "UTC midnight instead of Helsinki midnight, DEF-TIMEZONE): " + "; ".join(lines) + ".")
    else:
        report.add("Date coverage", "INFO", "UTC/Helsinki edge: no rows sit across the requested boundaries.")


def check_control(con, columns, rows, args, start, end, report):
    section = "Control total (rpt_daily_store_sales)"
    if not args.control:
        report.add(section, "INFO", "Not requested. For store-level net sales use --control (TEAM-CONTROL-TOTALS).")
        return
    if not start:
        report.add(section, "FAIL", "--control needs the requested range (--start/--end or --period).")
        return
    value_col = args.value_col or next((c for c in ("net_sales", "net_sales_before_returns") if c in columns), None)
    if value_col is None or value_col not in columns:
        report.add(section, "FAIL", f"Value column not found; give --value-col (columns: {', '.join(columns)}).")
        return
    measure = args.control_measure or (value_col if value_col in CONTROL_MEASURES else "net_sales")
    if measure not in CONTROL_MEASURES:
        report.add(section, "FAIL", f"--control-measure must be one of {', '.join(CONTROL_MEASURES)}.")
        return
    store_col = args.store_col or ("store_id" if "store_id" in columns else None)
    date_col = args.date_col or next((c for c in DATE_COLUMN_GUESSES if c in columns), None)

    # store filter for the control side
    stores = args.control_stores.strip().lower()
    if stores == "all":
        store_sql, store_params = "", []
    elif stores == "physical":
        store_sql, store_params = " AND store_id < 900", []
    elif stores == "web":
        store_sql, store_params = " AND store_id = 900", []
    else:
        try:
            ids = [int(s) for s in stores.split(",")]
        except ValueError:
            report.add(section, "FAIL", "--control-stores must be all, physical, web or a list of store_ids.")
            return
        store_sql = f" AND store_id IN ({', '.join('?' for _ in ids)})"
        store_params = ids

    group_cols = []
    if date_col and date_col in columns:
        group_cols.append(("business_date", columns.index(date_col)))
    if store_col and store_col in columns:
        group_cols.append(("store_id", columns.index(store_col)))
    select_keys = ", ".join(name for name, _ in group_cols)
    sql = (f"SELECT {select_keys + ', ' if select_keys else ''}SUM({measure}) FROM rpt_daily_store_sales "
           f"WHERE business_date BETWEEN ? AND ?{store_sql}"
           f"{' GROUP BY ' + select_keys if select_keys else ''}")
    control_rows = con.execute(sql, [start, end] + store_params).fetchall()

    # aggregate the result to the same keys
    value_index = columns.index(value_col)
    mine = collections.defaultdict(float)
    for row in rows:
        key = tuple((to_date(row[i]) if name == "business_date" else row[i]) for name, i in group_cols)
        mine[key] += to_number(row[value_index])
    control = {tuple(r[:-1]): to_number(r[-1]) for r in control_rows}

    keys = set(mine) | set(control)
    gaps = []
    for key in keys:
        gap = mine.get(key, 0.0) - control.get(key, 0.0)
        if abs(gap) > args.tolerance:
            gaps.append((key, mine.get(key, 0.0), control.get(key, 0.0), gap))
    total_mine = sum(mine.values())
    total_control = sum(control.values())
    level = " x ".join(name for name, _ in group_cols) or "total"
    report.add(section, "INFO", f"Compared {value_col} with rpt_daily_store_sales.{measure}, "
               f"{start} to {end}, stores: {args.control_stores}, at level: {level}.")
    report.add(section, "INFO", f"Result total {total_mine:,.2f}; control total {total_control:,.2f}; "
               f"gap {total_mine - total_control:,.2f}.")
    if not gaps:
        report.add(section, "PASS", f"No gap above {args.tolerance} at level {level}.")
        return
    gaps.sort(key=lambda g: -abs(g[3]))
    sample = "; ".join(f"{dict(zip([n for n, _ in group_cols], key)) or 'total'}: result {m:,.2f} vs control "
                       f"{c:,.2f} (gap {g:,.2f})" for key, m, c, g in gaps[:8])
    report.add(section, "FAIL", f"{len(gaps)} cells differ by more than {args.tolerance}. Largest: {sample}. "
               "Find the cause before sending (TEAM-CONTROL-TOTALS); a stated difference in definition "
               "(e.g. gross, as-was, a store subset) is a reason, an unexplained gap is not.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Run and check a warehouse query.")
    parser.add_argument("db", help="path to tuomimetsa.duckdb")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--sql", help="SQL text")
    source.add_argument("--file", help="file holding one SQL query")
    parser.add_argument("--grain")
    parser.add_argument("--date-col")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--period")
    parser.add_argument("--ts-col")
    parser.add_argument("--control", action="store_true")
    parser.add_argument("--value-col")
    parser.add_argument("--control-measure")
    parser.add_argument("--store-col")
    parser.add_argument("--control-stores", default="all")
    parser.add_argument("--tolerance", type=float, default=0.01)
    parser.add_argument("--show", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.file:
        try:
            with open(args.file, encoding="utf-8") as handle:
                sql = handle.read()
        except OSError as error:
            sys.exit(f"Could not read {args.file}: {error}")
    else:
        sql = args.sql
    # drop a final semicolon, also when comment lines follow it, so the query can be used as a subquery
    sql = re.sub(r";\s*(--[^\n]*\s*)*$", "", sql.strip()).strip()
    args.sql_text = sql

    try:
        con = duckdb.connect(args.db, read_only=True)
    except Exception as error:
        sys.exit(f"Could not open {args.db}: {error}")

    report = Report()
    lint_sql(sql, report)
    columns, rows = run_query(con, sql, report)
    preview = []
    if columns is not None:
        start, end = requested_range(con, args)
        preview = check_rows(columns, rows, report, args.show)
        grain = [g.strip() for g in args.grain.split(",")] if args.grain else []
        check_grain(columns, rows, grain, report)
        check_dates(con, columns, rows, args, start, end, report)
        check_control(con, columns, rows, args, start, end, report)

    if args.json:
        print(json.dumps({"failed": report.failed(), "checks": report.items, "preview": preview}, indent=2, default=str))
    else:
        report.print_text()
        if preview:
            print(f"\n== Preview (first {len(preview)} rows) ==")
            if columns:
                print("  " + " | ".join(columns))
            for line in preview:
                print("  " + line)
        print(f"\nResult: {'FAILED - fix before sending' if report.failed() else 'no failed checks'}")
    sys.exit(1 if report.failed() else 0)


if __name__ == "__main__":
    main()
