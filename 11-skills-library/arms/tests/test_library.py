"""
test_library.py - tests for the skills library scripts and templates.

Usage:
    conda run -n <env> python test_library.py PATH_TO_DUCKDB [--world PATH_TO_WORLD_FOLDER]

What it runs:
    1. fiscal.py on phrases whose answers are fixed by the metric dictionary or the request history.
    2. query_check.py on every template in library/*/templates (expected: no failed check).
    3. Templates against the accepted queries in world/request_history that they generalise:
       the two result sets must be identical on the shared columns.
    4. query_check.py on cases built to fail (deprecated view, duplicate grain, control gap, UTC cast ...).
    5. query_check.py lint on all 40 accepted queries (expected: no deprecated object).
Prints one line per test and a summary; exit code 1 if anything failed.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent
LIBRARY = HERE.parent / "library"
FISCAL = LIBRARY / "fiscal-calendar" / "scripts" / "fiscal.py"
QUERY_CHECK = LIBRARY / "query-check" / "scripts" / "query_check.py"

results = []


def record(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{' - ' + detail if detail else ''}")


def run(args):
    proc = subprocess.run([sys.executable] + [str(a) for a in args], capture_output=True, text=True, encoding="utf-8")
    return proc.returncode, proc.stdout, proc.stderr


# ---------------------------------------------------------------------------
# 1. fiscal.py
# ---------------------------------------------------------------------------

FISCAL_CASES = [
    # phrase, as-of, expected start, expected end, source of the expectation
    ("last period", None, "2026-08-31", "2026-09-27", "CAL-DATA-THROUGH: last complete period FY2026/27 P05"),
    ("last period", "2026-10-01", "2026-08-31", "2026-09-27", "REQ-D23 (31 Aug - 27 Sep 2026)"),
    ("last period", "2026-09-30", "2026-08-31", "2026-09-27", "REQ-D25 (FY2026/27 P5)"),
    ("Q3", "2026-04-14", "2025-10-27", "2026-01-25", "REQ-D03 (Q3 = weeks 27-39 FY2025/26)"),
    ("Q4", "2026-06-23", "2026-01-26", "2026-05-03", "REQ-D12 (Q4 FY2025/26 incl. week 53)"),
    ("Q1", "2025-08-20", "2025-04-28", "2025-07-27", "REQ-D06 (Q1 FY2025/26)"),
    ("P2", "2026-07-07", "2026-06-01", "2026-06-28", "REQ-D10 (P2 FY2026/27)"),
    ("P11", "2026-04-07", "2026-02-23", "2026-03-22", "REQ-D27 (weeks 44-47 FY2025/26)"),
    ("P8", "2026-01-13", "2025-11-24", "2025-12-21", "REQ-D18 (P8 FY2025/26)"),
    ("P4", "2025-09-09", "2025-07-28", "2025-08-24", "REQ-D37 (P4 FY2025/26)"),
    ("P4", "2026-09-03", "2026-08-03", "2026-08-30", "REQ-D21 (P4 FY2026/27)"),
    ("P3", "2026-08-19", "2026-06-29", "2026-08-02", "REQ-D40 (P3 FY2026/27)"),
    ("P1-P4 FY2025/26", None, "2025-04-28", "2025-08-24", "REQ-D22"),
    ("H2 FY2025/26", None, "2025-10-27", "2026-05-03", "REQ-D04/D35 (P7-P12)"),
    ("H1 FY2024/25", None, "2024-04-29", "2024-10-27", "REQ-D13 (P1-P6)"),
    ("FY2024/25", None, "2024-04-29", "2025-04-27", "CAL-FY-DATES"),
    ("FY25/26", None, "2025-04-28", "2026-05-03", "CAL-FY-DATES (53 weeks)"),
    ("YTD", None, "2026-05-04", "2026-10-04", "CAL-RELATIVE + CAL-DATA-THROUGH (through week 22)"),
    ("YTD as of the end of P4", "2026-09-08", "2026-05-04", "2026-08-30", "REQ-D09 (weeks 1-17 FY2026/27)"),
    ("YTD to end of P4 FY2025/26", None, "2025-04-28", "2025-08-24", "CAL-PERIODS (weeks 1-17 FY2025/26)"),
    ("this year", None, "2026-05-04", "2027-05-02", "CAL-RELATIVE (52-week year, loaded through 4 Oct 2026)"),
    ("last 4 weeks", "2026-09-01", "2026-08-03", "2026-08-30", "REQ-D02 (= P4 FY2026/27)"),
    ("week 22 FY2026/27", None, "2026-09-28", "2026-10-04", "CAL-DATA-THROUGH (week 22)"),
]


def test_fiscal(db):
    for phrase, as_of, start, end, source in FISCAL_CASES:
        args = [FISCAL, db, phrase, "--json"] + (["--as-of", as_of] if as_of else [])
        code, out, err = run(args)
        try:
            data = json.loads(out)
            ok = code == 0 and data["start_date"] == start and data["end_date"] == end
            detail = f"{data.get('start_date')} to {data.get('end_date')} ({source})"
        except (json.JSONDecodeError, KeyError):
            ok, detail = False, f"exit {code}: {out[:200]} {err[:200]}"
        record(f"fiscal.py '{phrase}'{' as of ' + as_of if as_of else ''}", ok, detail)

    # comparator: week 53 has no comparator, same week numbers last year
    code, out, _ = run([FISCAL, db, "P12 FY2025/26", "--compare", "--json"])
    data = json.loads(out)
    comp = data["comparison"]
    ok = (data["includes_week_53"] and comp["start_date"] == "2025-03-24" and comp["end_date"] == "2025-04-27"
          and comp["weeks_without_comparator"] == ["FY2025/26 week 53"])
    record("fiscal.py P12 FY2025/26 --compare (week 53 without comparator)", ok,
           f"comparator {comp['start_date']} to {comp['end_date']}, unmatched {comp['weeks_without_comparator']}")

    code, out, _ = run([FISCAL, db, "same week last year", "--json"])
    data = json.loads(out)
    comp = data["comparison"]
    ok = data["start_date"] == "2026-09-28" and comp["start_date"] == "2025-09-22" and comp["end_date"] == "2025-09-28"
    record("fiscal.py 'same week last year'", ok, f"{data['start_date']} vs {comp['start_date']} to {comp['end_date']}")

    code, out, _ = run([FISCAL, db, "Q1 FY2024/25", "--compare", "--json"])
    data = json.loads(out)
    ok = data["comparison"]["comparator"] is None
    record("fiscal.py Q1 FY2024/25 --compare (no prior year in warehouse)", ok, data["comparison"].get("note", ""))

    code, out, _ = run([FISCAL, db, "last year", "--json"])
    data = json.loads(out)
    ok = code == 2 and "not defined" in data.get("error", "")
    record("fiscal.py 'last year' is refused (not defined in the dictionary)", ok, f"exit {code}")

    code, out, _ = run([FISCAL, db, "P6", "--as-of", "2026-10-04", "--json"])
    data = json.loads(out)
    ok = data.get("fiscal_periods") == ["FY2025/26 P06"]
    record("fiscal.py bare 'P6' on 4 Oct 2026 -> most recent completed P6", ok, str(data.get("fiscal_periods")))

    code, out, _ = run([FISCAL, db, "P6 FY2026/27", "--json"])
    data = json.loads(out)
    ok = data.get("complete_as_of") is False and data.get("loaded_through") == "2026-10-04"
    record("fiscal.py 'P6 FY2026/27' flagged incomplete (only week 22 loaded)", ok,
           f"complete={data.get('complete_as_of')}, loaded_through={data.get('loaded_through')}")


# ---------------------------------------------------------------------------
# 2. Every template through query_check.py
# ---------------------------------------------------------------------------

TEMPLATE_CHECKS = {
    "sales-reporting/templates/net_sales_by_store_day.sql":
        ["--grain", "business_date,store_id", "--period", "FY2026/27 P05", "--control"],
    "sales-reporting/templates/net_sales_weekly_yoy.sql": ["--grain", "fiscal_week,region"],
    "sales-reporting/templates/gross_margin_by_category.sql": ["--grain", "category"],
    "sales-reporting/templates/gross_sales_incl_vat.sql": ["--grain", "category", "--period", "FY2026/27 P05"],
    "sales-reporting/templates/return_rate_by_category.sql": ["--grain", "category"],
    "sales-reporting/templates/atv_by_store.sql": ["--grain", "store_id"],
    "lfl-and-store-league/templates/lfl.sql": ["--grain", "region"],
    "lfl-and-store-league/templates/lfl_store_weeks.sql": ["--grain", "store_id"],
    "lfl-and-store-league/templates/store_league_table.sql":
        ["--grain", "store_id", "--start", "2026-06-29", "--end", "2026-08-02", "--control", "--control-stores", "physical"],
    "store-and-product-history/templates/net_sales_by_region_as_was.sql":
        ["--grain", "fiscal_quarter,region", "--period", "FY2024/25 P01", "--start", "2024-04-29", "--end", "2025-04-27", "--control"],
    "store-and-product-history/templates/category_as_is_vs_as_was.sql": ["--grain", "category"],
    "store-and-product-history/templates/version_on_date.sql": ["--grain", "kind,natural_key"],
    "web-orders/templates/web_net_sales_daily.sql":
        ["--grain", "business_date", "--start", "2025-11-24", "--end", "2025-11-30", "--control", "--control-stores", "web",
         "--value-col", "web_net_sales"],
    "web-orders/templates/web_orders_by_week.sql": ["--grain", "fiscal_week"],
    "web-orders/templates/web_orders_by_hour_helsinki.sql": ["--grain", "hour_helsinki"],
    "web-orders/templates/click_collect_share_of_web_sales.sql": ["--grain", "fiscal_period"],
    "web-orders/templates/click_collect_orders_by_store.sql": ["--grain", "store_id", "--period", "FY2026/27 P05"],
    "web-orders/templates/click_collect_share_of_orders_by_quarter.sql": ["--grain", "fiscal_year,fiscal_quarter"],
    "loyalty-and-campaigns/templates/active_members.sql": ["--grain", "tier"],
    "loyalty-and-campaigns/templates/member_share_of_sales.sql": ["--grain", "region"],
    "loyalty-and-campaigns/templates/new_members.sql": ["--grain", "fiscal_period,home_store_id"],
    "loyalty-and-campaigns/templates/campaign_uplift.sql": ["--grain", "member_group"],
    "stock/templates/closing_stock_for_period.sql": ["--grain", "store_id"],
    "stock/templates/weeks_of_cover.sql": ["--grain", "store_id,category"],
}


def required_values(db):
    """
    Values for templates' required placeholders, chosen from the warehouse at test time (not written into
    any template): the most recent campaign whose window plus seven days is fully loaded.
    """
    con = duckdb.connect(str(db), read_only=True)
    campaign_id = con.execute(
        "SELECT MAX(campaign_id) FROM dim_campaign WHERE end_date + 7 <= (SELECT MAX(calendar_date) FROM dim_date)"
    ).fetchone()[0]
    con.close()
    return {"{{campaign_id}}": str(campaign_id)}


def fill_template(template, values, scratch):
    """Return a path to run: the template itself, or a filled copy when it has required placeholders."""
    text = (LIBRARY / template).read_text(encoding="utf-8")
    if "{{" not in text:
        return LIBRARY / template
    for placeholder, value in values.items():
        text = text.replace(placeholder, value)
    path = scratch / ("filled_" + template.replace("/", "_"))
    path.write_text(text, encoding="utf-8")
    return path


def test_templates(db, scratch):
    found = sorted(p.relative_to(LIBRARY).as_posix() for p in LIBRARY.glob("*/templates/*.sql"))
    missing = [t for t in found if t not in TEMPLATE_CHECKS]
    record("every template has a test", not missing, f"{len(found)} templates" + (f", untested: {missing}" if missing else ""))
    values = required_values(db)

    # a template with a required placeholder must not run until it is filled in
    code, out, _ = run([QUERY_CHECK, db, "--file", LIBRARY / "loyalty-and-campaigns/templates/campaign_uplift.sql", "--json"])
    report = json.loads(out)
    ok = code == 1 and "FAIL" in statuses(report, "Query")
    record("campaign_uplift.sql without a campaign_id is rejected (required, no default)", ok, f"exit {code}")

    for template, extra in TEMPLATE_CHECKS.items():
        # --period and --start both given above for the as-was case: keep the explicit dates
        if "--start" in extra and "--period" in extra:
            index = extra.index("--period")
            extra = extra[:index] + extra[index + 2:]
        code, out, err = run([QUERY_CHECK, db, "--file", fill_template(template, values, scratch), "--json"] + extra)
        try:
            report = json.loads(out)
        except json.JSONDecodeError:
            record(f"template {template}", False, f"exit {code}: {err[:300]}")
            continue
        rows = next((c["message"] for c in report["checks"] if c["section"] == "Row count"), "")
        warns = [c["message"][:90] for c in report["checks"] if c["status"] in ("WARN", "FAIL")]
        ok = code == 0 and not report["failed"] and not rows.startswith("0 rows")
        record(f"template {template}", ok, rows.split(",")[0] + (f"; warnings: {warns}" if warns else ""))


# ---------------------------------------------------------------------------
# 3. Templates against accepted queries from the request history
# ---------------------------------------------------------------------------

def history_sql(world, request):
    text = (world / "request_history" / f"{request}.md").read_text(encoding="utf-8")
    sql = re.search(r"```sql\n(.*?)```", text, re.DOTALL).group(1)
    return re.sub(r";\s*(--[^\n]*\s*)*$", "", sql.strip())


def template_sql(template, replacements=()):
    sql = re.sub(r";\s*(--[^\n]*\s*)*$", "", (LIBRARY / template).read_text(encoding="utf-8").strip())
    for old, new in replacements:
        if old not in sql:
            raise ValueError(f"{template}: '{old}' not found for replacement")
        sql = sql.replace(old, new)
    return sql


EQUIVALENCE = [
    # request, template, replacements in params, columns compared, filter on template rows, both directions
    ("REQ-D01", "sales-reporting/templates/net_sales_weekly_yoy.sql",
     [("'FY2026/27' AS ty_year, 'FY2025/26' AS ly_year", "'FY2025/26' AS ty_year, 'FY2024/25' AS ly_year"),
      ("18 AS first_week, 21 AS last_week", "22 AS first_week, 26 AS last_week")],
     "fiscal_week, region, this_year, last_year, growth_pct", "TRUE", True),
    ("REQ-D05", "store-and-product-history/templates/net_sales_by_region_as_was.sql", [],
     "fiscal_quarter, region, net_sales", "TRUE", True),
    ("REQ-D06", "lfl-and-store-league/templates/lfl.sql",
     [("'FY2026/27' AS ty_year, 'FY2025/26' AS ly_year, 9 AS first_week, 13 AS last_week",
       "'FY2025/26' AS ty_year, 'FY2024/25' AS ly_year, 1 AS first_week, 13 AS last_week")],
     "this_year, last_year, lfl_growth_pct", "region IS NULL", True),
    ("REQ-D07", "lfl-and-store-league/templates/lfl.sql", [],
     "this_year, last_year, lfl_growth_pct", "region IS NULL", True),
    ("REQ-D08", "lfl-and-store-league/templates/lfl.sql",
     [("'FY2026/27' AS ty_year, 'FY2025/26' AS ly_year, 9 AS first_week, 13 AS last_week",
       "'FY2025/26' AS ty_year, 'FY2024/25' AS ly_year, 27 AS first_week, 53 AS last_week")],
     "region, this_year, last_year, lfl_growth_pct", "region IS NOT NULL", True),
    ("REQ-D09", "lfl-and-store-league/templates/lfl.sql",
     [("9 AS first_week, 13 AS last_week", "1 AS first_week, 17 AS last_week")],
     "this_year, last_year, lfl_growth_pct", "region IS NULL", True),
    ("REQ-D10", "sales-reporting/templates/gross_margin_by_category.sql", [],
     "category, net_sales, gross_margin, gross_margin_pct", "TRUE", True),
    ("REQ-D14", "sales-reporting/templates/return_rate_by_category.sql", [],
     "category, sold_net, returned_net, return_rate_pct", "TRUE", True),
    ("REQ-D17", "web-orders/templates/web_net_sales_daily.sql", [],
     "business_date, web_net_sales", "TRUE", True),
    ("REQ-D18", "web-orders/templates/web_orders_by_week.sql", [],
     "fiscal_week, web_orders", "TRUE", True),
    ("REQ-D20", "web-orders/templates/web_orders_by_hour_helsinki.sql", [],
     "hour_helsinki, web_orders", "TRUE", True),
    ("REQ-D22", "web-orders/templates/click_collect_share_of_web_sales.sql", [],
     "fiscal_period, click_collect_net, web_net, click_collect_share_pct", "TRUE", True),
    ("REQ-D23", "web-orders/templates/click_collect_orders_by_store.sql", [],
     "store_id, store_name, collected_orders, share_of_collected_pct", "TRUE", False),   # history kept the top 15
    ("REQ-D24", "web-orders/templates/click_collect_share_of_orders_by_quarter.sql", [],
     "fiscal_year, fiscal_quarter, web_orders, click_collect_orders, click_collect_share_pct", "TRUE", True),
    ("REQ-D25", "sales-reporting/templates/atv_by_store.sql", [],
     "store_id, store_name, receipts, atv", "TRUE", True),
    ("REQ-D29", "loyalty-and-campaigns/templates/active_members.sql",
     [("DATE '2025-09-28' AS as_of_date", "DATE '2025-04-27' AS as_of_date")],
     "active_members", "tier IS NULL", True),
    ("REQ-D30", "loyalty-and-campaigns/templates/active_members.sql", [],
     "tier, active_members", "tier IS NOT NULL", True),
    ("REQ-D32", "loyalty-and-campaigns/templates/member_share_of_sales.sql", [],
     "region, member_share_pct", "TRUE", True),
    ("REQ-D37", "lfl-and-store-league/templates/store_league_table.sql",
     [("DATE '2026-06-29' AS start_date, DATE '2026-08-02' AS end_date", "DATE '2025-07-28' AS start_date, DATE '2025-08-24' AS end_date")],
     "rank, store_id, store_name, format, trading_days, net_sales, net_sales_per_trading_day", "TRUE", True),
    ("REQ-D38", "lfl-and-store-league/templates/store_league_table.sql",
     [("DATE '2026-06-29' AS start_date, DATE '2026-08-02' AS end_date", "DATE '2025-10-27' AS start_date, DATE '2026-01-25' AS end_date")],
     "rank, store_id, store_name, format, trading_days, net_sales, net_sales_per_trading_day", "TRUE", True),
    ("REQ-D39", "lfl-and-store-league/templates/store_league_table.sql",
     [("DATE '2026-06-29' AS start_date, DATE '2026-08-02' AS end_date", "DATE '2024-10-28' AS start_date, DATE '2025-04-27' AS end_date")],
     "store_id, store_name, format, trading_days, net_sales, net_sales_per_trading_day", "format = 'Large'", True),
    ("REQ-D40", "lfl-and-store-league/templates/store_league_table.sql", [],
     "rank, store_id, store_name, format, trading_days, net_sales, net_sales_per_trading_day", "TRUE", True),
]


def test_equivalence(db, world):
    con = duckdb.connect(str(db), read_only=True)
    for request, template, replacements, columns, where, both in EQUIVALENCE:
        try:
            h = history_sql(world, request)
            t = template_sql(template, replacements)
            count_h = con.execute(f"SELECT COUNT(*) FROM (\n{h}\n)").fetchone()[0]
            only_h = con.execute(f"SELECT COUNT(*) FROM ((SELECT {columns} FROM (\n{h}\n)) EXCEPT ALL "
                                 f"(SELECT {columns} FROM (\n{t}\n) WHERE {where}))").fetchone()[0]
            only_t = con.execute(f"SELECT COUNT(*) FROM ((SELECT {columns} FROM (\n{t}\n) WHERE {where}) EXCEPT ALL "
                                 f"(SELECT {columns} FROM (\n{h}\n)))").fetchone()[0] if both else 0
            ok = only_h == 0 and only_t == 0 and count_h > 0
            record(f"{template.split('/')[-1]} reproduces {request}", ok,
                   f"{count_h} history rows; {only_h} only in history, {only_t if both else 'n/a'} only in template")
        except Exception as error:
            record(f"{template.split('/')[-1]} reproduces {request}", False, str(error)[:300])


# ---------------------------------------------------------------------------
# 4. query_check.py cases built to fail
# ---------------------------------------------------------------------------

def statuses(report, section):
    return [c["status"] for c in report["checks"] if c["section"].startswith(section)]


def test_query_check_negative(db, scratch):
    cases = []
    cases.append(("deprecated legacy view is a FAIL",
                  ["--sql", "SELECT sale_date, channel, net_sales FROM rpt.v_daily_sales WHERE sale_date >= DATE '2025-11-01'"],
                  lambda r: "FAIL" in statuses(r, "Deprecated")))
    cases.append(("stg_/bak_/tmp_ tables are a FAIL",
                  ["--sql", "SELECT s.store_id FROM tmp_lfl_store_list_2025 s JOIN bak_dim_store_2025 b USING (store_id)"],
                  lambda r: statuses(r, "Deprecated").count("FAIL") == 2))
    cases.append(("channel_code and missing exclusions are warnings",
                  ["--sql", "SELECT sale_date, SUM(net_amount) AS net_sales FROM fact_sales_line WHERE channel_code = 'WB' GROUP BY 1"],
                  lambda r: "WARN" in statuses(r, "Deprecated") and statuses(r, "House-rule").count("WARN") >= 2))
    cases.append(("UTC timestamp cast to a date is a warning",
                  ["--sql", "SELECT CAST(order_ts_utc AS DATE) AS order_date, COUNT(*) AS n FROM fact_web_order GROUP BY 1"],
                  lambda r: "WARN" in statuses(r, "House-rule")))
    cases.append(("natural-key join without a version rule is a warning, and the grain check fails",
                  ["--sql", "SELECT c.business_date, c.store_id, s.region FROM rpt_daily_store_sales c "
                            "JOIN dim_store s ON s.store_id = c.store_id WHERE c.business_date = DATE '2026-09-01'",
                   "--grain", "business_date,store_id"],
                  lambda r: "WARN" in statuses(r, "House-rule") and "FAIL" in statuses(r, "Duplicate")))
    cases.append(("duplicate receipt lines found at grain receipt_id,line_no",
                  ["--sql", "SELECT receipt_id, line_no, sale_date FROM fact_sales_line f JOIN dim_store s USING (store_key) "
                            "WHERE f.sale_date BETWEEN DATE '2025-09-15' AND DATE '2025-09-21' AND s.store_id < 900",
                   "--grain", "receipt_id,line_no"],
                  lambda r: "FAIL" in statuses(r, "Duplicate")))
    cases.append(("duplicate stock snapshot rows found at grain store_key,product_key,week_ending_date",
                  ["--sql", "SELECT store_key, product_key, week_ending_date FROM fact_stock_week",
                   "--grain", "store_key,product_key,week_ending_date"],
                  lambda r: "FAIL" in statuses(r, "Duplicate")))
    week21 = template_sql("sales-reporting/templates/net_sales_by_store_day.sql",
                          [("DATE '2026-08-31' AS start_date", "DATE '2025-09-15' AS start_date"),
                           ("DATE '2026-09-27' AS end_date", "DATE '2025-09-21' AS end_date")])
    path = scratch / "net_sales_fy2526_w21.sql"
    path.write_text(week21, encoding="utf-8")
    cases.append(("control-total gap is a FAIL (FY2025/26 week 21)",
                  ["--file", path, "--start", "2025-09-15", "--end", "2025-09-21", "--control", "--grain", "business_date,store_id"],
                  lambda r: "FAIL" in statuses(r, "Control")))
    cases.append(("result dates outside the requested range are a FAIL",
                  ["--file", LIBRARY / "sales-reporting/templates/net_sales_by_store_day.sql", "--period", "FY2026/27 P04"],
                  lambda r: "FAIL" in statuses(r, "Date coverage")))
    cases.append(("UTC-dated filter caught with --ts-col",
                  ["--sql", "SELECT web_order_id, order_ts_utc FROM fact_web_order "
                            "WHERE CAST(order_ts_utc AS DATE) BETWEEN DATE '2026-08-31' AND DATE '2026-09-27'",
                   "--ts-col", "order_ts_utc", "--period", "FY2026/27 P05"],
                  lambda r: "FAIL" in statuses(r, "Date coverage")))
    cases.append(("range past the load point is a warning",
                  ["--sql", "SELECT business_date, store_id, net_sales FROM rpt_daily_store_sales "
                            "WHERE business_date BETWEEN DATE '2026-09-28' AND DATE '2026-11-01'",
                   "--period", "FY2026/27 P06"],
                  lambda r: any("after the last loaded date" in c["message"] for c in r["checks"])))
    for name, extra, predicate in cases:
        code, out, err = run([QUERY_CHECK, db, "--json"] + extra)
        try:
            report = json.loads(out)
            ok = predicate(report)
            flagged = [c["message"][:110] for c in report["checks"] if c["status"] in ("FAIL", "WARN")]
            detail = f"exit {code}; " + " | ".join(flagged[:2])
        except Exception as error:
            ok, detail = False, f"exit {code}: {error} {err[:200]}"
        record(f"query_check: {name}", ok, detail)


# ---------------------------------------------------------------------------
# 5. Lint on the 40 accepted queries
# ---------------------------------------------------------------------------

def test_history_lint(db, world, scratch):
    warnings = {}
    failures = []
    for path in sorted((world / "request_history").glob("REQ-D*.md")):
        sql = history_sql(world, path.stem)
        file = scratch / f"{path.stem}.sql"
        file.write_text(sql, encoding="utf-8")
        code, out, _ = run([QUERY_CHECK, db, "--file", file, "--json"])
        report = json.loads(out)
        if report["failed"]:
            failures.append(path.stem)
        warns = [c["message"][:70] for c in report["checks"] if c["status"] == "WARN" and c["section"] != "Row count"]
        if warns:
            warnings[path.stem] = warns
    record("query_check on the 40 accepted queries: no failed check", not failures,
           f"failed: {failures}" if failures else f"{len(warnings)} with lint warnings")
    for request, warns in warnings.items():
        print(f"       {request}: {warns}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("db")
    parser.add_argument("--world", default=str(HERE.parent.parent / "world"))
    args = parser.parse_args()
    db = Path(args.db).resolve()
    world = Path(args.world).resolve()
    scratch = HERE / "_scratch"
    scratch.mkdir(exist_ok=True)

    print("== 1. fiscal.py ==")
    test_fiscal(db)
    print("\n== 2. templates through query_check.py ==")
    test_templates(db, scratch)
    print("\n== 3. templates against accepted queries ==")
    test_equivalence(db, world)
    print("\n== 4. query_check.py negative cases ==")
    test_query_check_negative(db, scratch)
    print("\n== 5. lint on accepted queries ==")
    test_history_lint(db, world, scratch)

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
