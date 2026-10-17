"""Validate the Tuomimetsa warehouse and world (Project 11, Phase 2).

Run:  python code/validate_data.py            full validation (includes the rebuild for rule 11)
      python code/validate_data.py --fast     skip rule 11 (the rebuild takes about a minute)

Implements warehouse rules 1-11, plus the Phase 2 checks on
scale, the planted incidents, the facts file, the in-world documents and the
40 dev requests, and (Phase 3, validate_key.py) rules 12-15 on the 60 test
requests and the answer key, and (Phase 4, validate_arms.py) rules 16-18 on the
prompt doc and the skills library in arms/. The database is opened read-only. Exits 1 if any check fails; a
dataset that fails validation is a bug, not a judgment call.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, timedelta

import duckdb
import numpy as np
import pandas as pd

import config as cfg
from wh_common import compute_content_hash, log

RESULTS: list[dict] = []


def record(rule: str, name: str, passed: bool, detail: str = "") -> None:
    """Store and print one check result."""
    RESULTS.append({"rule": rule, "check": name, "passed": bool(passed), "detail": detail})
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {rule} {name}" + (f"  ({detail})" if detail else ""), flush=True)


def scalar(connection, sql: str):
    return connection.execute(sql).fetchone()[0]


def expect_zero(connection, rule: str, name: str, sql: str) -> None:
    """A check that passes when the query counts zero offending rows."""
    count = scalar(connection, sql)
    record(rule, name, count == 0, f"{count:,} offending rows" if count else "")


DEDUPED_LINES = ("(SELECT * FROM fact_sales_line QUALIFY row_number() OVER "
                 "(PARTITION BY receipt_id, line_no ORDER BY sales_line_id) = 1)")
HELSINKI = "timezone('Europe/Helsinki', {col} AT TIME ZONE 'UTC')"


def helsinki(column: str) -> str:
    return HELSINKI.format(col=column)


# ---------------------------------------------------------------------------
# Rule 1: referential integrity
# ---------------------------------------------------------------------------

def rule_1(connection) -> None:
    print("Rule 1: referential integrity")
    links = [
        ("fact_sales_line", "store_key", "dim_store", "store_key", False),
        ("fact_sales_line", "product_key", "dim_product", "product_key", False),
        ("fact_sales_line", "member_key", "dim_member", "member_key", True),
        ("fact_sales_line", "channel_id", "dim_channel", "channel_id", True),
        ("fact_sales_line", "sale_date", "dim_date", "calendar_date", False),
        ("fact_return_line", "sales_line_id", "fact_sales_line", "sales_line_id", False),
        ("fact_return_line", "store_key", "dim_store", "store_key", False),
        ("fact_return_line", "product_key", "dim_product", "product_key", False),
        ("fact_return_line", "member_key", "dim_member", "member_key", True),
        ("fact_return_line", "return_date", "dim_date", "calendar_date", False),
        ("fact_web_order", "member_key", "dim_member", "member_key", True),
        ("fact_web_order", "pickup_store_key", "dim_store", "store_key", True),
        ("fact_stock_week", "store_key", "dim_store", "store_key", False),
        ("fact_stock_week", "product_key", "dim_product", "product_key", False),
        ("fact_stock_week", "week_ending_date", "dim_date", "calendar_date", False),
        ("fact_campaign_exposure", "campaign_id", "dim_campaign", "campaign_id", False),
        ("fact_campaign_exposure", "member_key", "dim_member", "member_key", False),
        ("campaign_holdout", "campaign_id", "dim_campaign", "campaign_id", False),
        ("campaign_holdout", "member_id", "dim_member", "member_id", False),
        ("rpt_daily_store_sales", "business_date", "dim_date", "calendar_date", False),
        ("rpt_daily_store_sales", "store_id", "dim_store", "store_id", False),
        ("dim_member", "home_store_id", "dim_store", "store_id", False),
        ("ref_store_closure", "store_id", "dim_store", "store_id", False),
    ]
    for child, child_column, parent, parent_column, nullable in links:
        null_clause = f"c.{child_column} IS NOT NULL AND " if nullable else ""
        expect_zero(connection, "R1", f"{child}.{child_column} -> {parent}.{parent_column}",
                    f"SELECT count(*) FROM {child} c WHERE {null_clause}NOT EXISTS "
                    f"(SELECT 1 FROM {parent} p WHERE p.{parent_column} = c.{child_column})")
    # Web lines and web orders point at each other.
    expect_zero(connection, "R1", "web sales lines -> fact_web_order",
                "SELECT count(*) FROM fact_sales_line f JOIN dim_store s USING (store_key) WHERE s.store_id = 900 AND NOT EXISTS "
                "(SELECT 1 FROM fact_web_order o WHERE o.web_order_id = f.receipt_id)")
    expect_zero(connection, "R1", "shipped web orders have sales lines",
                "SELECT count(*) FROM fact_web_order o WHERE o.status IN ('delivered', 'collected') AND NOT EXISTS "
                "(SELECT 1 FROM fact_sales_line f WHERE f.receipt_id = o.web_order_id)")


# ---------------------------------------------------------------------------
# Rule 2: SCD2 integrity and fact-to-version validity
# ---------------------------------------------------------------------------

def rule_2(connection) -> None:
    print("Rule 2: slowly changing dimensions")
    for table, natural in (("dim_store", "store_id"), ("dim_product", "sku"), ("dim_member", "member_id")):
        base = (f"SELECT {natural} AS nk, valid_from, valid_to, is_current, "
                f"lead(valid_from) OVER (PARTITION BY {natural} ORDER BY valid_from) AS next_from FROM {table}")
        expect_zero(connection, "R2", f"{table}: windows contiguous (next valid_from = valid_to + 1)",
                    f"SELECT count(*) FROM ({base}) WHERE next_from IS NOT NULL AND next_from <> valid_to + 1")
        expect_zero(connection, "R2", f"{table}: valid_to >= valid_from",
                    f"SELECT count(*) FROM {table} WHERE valid_to < valid_from")
        expect_zero(connection, "R2", f"{table}: exactly one current row per key, and it is the open-ended last version",
                    f"SELECT count(*) FROM (SELECT {natural}, sum(CASE WHEN is_current THEN 1 ELSE 0 END) AS c, "
                    f"sum(CASE WHEN valid_to = DATE '9999-12-31' THEN 1 ELSE 0 END) AS o FROM {table} GROUP BY 1) WHERE c <> 1 OR o <> 1")
        expect_zero(connection, "R2", f"{table}: current row is the last version",
                    f"SELECT count(*) FROM ({base}) WHERE is_current AND next_from IS NOT NULL")
    checks = [
        ("sales line store version", "fact_sales_line f JOIN dim_store d ON d.store_key = f.store_key", "f.sale_date"),
        ("sales line product version", "fact_sales_line f JOIN dim_product d ON d.product_key = f.product_key", "f.sale_date"),
        ("sales line member version", "fact_sales_line f JOIN dim_member d ON d.member_key = f.member_key", "f.sale_date"),
        ("return store version", "fact_return_line f JOIN dim_store d ON d.store_key = f.store_key", "f.return_date"),
        ("return product version", "fact_return_line f JOIN dim_product d ON d.product_key = f.product_key", "f.return_date"),
        ("return member version", "fact_return_line f JOIN dim_member d ON d.member_key = f.member_key", "f.return_date"),
        ("stock store version", "fact_stock_week f JOIN dim_store d ON d.store_key = f.store_key", "f.week_ending_date"),
        ("stock product version", "fact_stock_week f JOIN dim_product d ON d.product_key = f.product_key", "f.week_ending_date"),
        ("exposure member version", "fact_campaign_exposure f JOIN dim_member d ON d.member_key = f.member_key",
         f"CAST({helsinki('f.contact_ts_utc')} AS DATE)"),
        ("web order member version", "fact_web_order f JOIN dim_member d ON d.member_key = f.member_key",
         f"CAST({helsinki('f.order_ts_utc')} AS DATE)"),
        ("web pickup store version", "fact_web_order f JOIN dim_store d ON d.store_key = f.pickup_store_key",
         f"CAST({helsinki('coalesce(f.dispatch_ts_utc, f.order_ts_utc)')} AS DATE)"),
    ]
    for name, source, date_expression in checks:
        expect_zero(connection, "R2", f"{name} valid on the transaction date",
                    f"SELECT count(*) FROM {source} WHERE NOT ({date_expression} BETWEEN d.valid_from AND d.valid_to)")
    # Planted history sits in the dimensions.
    reorg = scalar(connection, f"SELECT count(DISTINCT store_id) FROM dim_store WHERE valid_from = DATE '{cfg.REGION_REORG_DATE}'")
    record("R2", "six stores changed region on the reorganisation date", reorg == 6, f"{reorg} stores")
    regions_before = scalar(connection, f"SELECT count(DISTINCT region) FROM dim_store WHERE store_id < 900 AND DATE '{cfg.REGION_REORG_DATE - timedelta(days=1)}' BETWEEN valid_from AND valid_to")
    regions_after = scalar(connection, f"SELECT count(DISTINCT region) FROM dim_store WHERE store_id < 900 AND DATE '{cfg.REGION_REORG_DATE}' BETWEEN valid_from AND valid_to")
    record("R2", "four regions become five", (regions_before, regions_after) == (4, 5), f"{regions_before} -> {regions_after}")
    moved = scalar(connection, f"SELECT count(*) FROM dim_product WHERE subcategory = '{cfg.OUTDOOR_LIGHTING_SUBCATEGORY}' "
                               f"AND valid_from = DATE '{cfg.CATEGORY_MOVE_DATE}' AND category = 'Electrical'")
    record("R2", "outdoor lighting moves to Electrical on the move date", moved > 0, f"{moved} SKUs")


# ---------------------------------------------------------------------------
# Rule 3: arithmetic
# ---------------------------------------------------------------------------

def rule_3(connection) -> None:
    print("Rule 3: arithmetic")
    expect_zero(connection, "R3", "gross = net x (1 + VAT rate) within a cent",
                "SELECT count(*) FROM fact_sales_line WHERE abs(gross_amount - net_amount * (1 + vat_rate)) > 0.0100001")
    expect_zero(connection, "R3", "return refund_gross = refund_net x (1 + VAT rate) within a cent",
                "SELECT count(*) FROM fact_return_line WHERE abs(refund_gross - refund_net * (1 + vat_rate)) > 0.0100001")
    expect_zero(connection, "R3", "VAT rate is the statutory rate for the line's date and VAT class",
                f"SELECT count(*) FROM fact_sales_line f JOIN dim_product p USING (product_key) WHERE f.vat_rate <> CASE "
                f"WHEN p.vat_class = 'standard' AND f.sale_date < DATE '{cfg.VAT_CHANGE_DATE}' THEN 0.2400 "
                f"WHEN p.vat_class = 'standard' THEN 0.2550 WHEN p.vat_class = 'reduced14' THEN 0.1400 ELSE 0.1000 END")
    standard_before = scalar(connection, f"SELECT count(*) FROM fact_sales_line WHERE vat_rate = 0.2400 AND sale_date >= DATE '{cfg.VAT_CHANGE_DATE}'")
    standard_after = scalar(connection, f"SELECT count(*) FROM fact_sales_line WHERE vat_rate = 0.2550 AND sale_date < DATE '{cfg.VAT_CHANGE_DATE}'")
    record("R3", "no 24% line after 1 Sep 2024 and no 25.5% line before", standard_before == 0 and standard_after == 0)
    expect_zero(connection, "R3", "returns carry the VAT rate of the original line",
                "SELECT count(*) FROM fact_return_line r JOIN fact_sales_line f USING (sales_line_id) WHERE r.vat_rate <> f.vat_rate")
    expect_zero(connection, "R3", "standard cost = quantity x standard unit cost",
                "SELECT count(*) FROM fact_sales_line f JOIN dim_product p USING (product_key) "
                "WHERE abs(f.standard_cost - f.quantity * p.standard_unit_cost) > 0.0001")
    expect_zero(connection, "R3", "quantity >= 1 and net > 0",
                "SELECT count(*) FROM fact_sales_line WHERE quantity < 1 OR net_amount <= 0")
    margin = scalar(connection, "SELECT 1 - sum(standard_cost) / sum(net_amount) FROM fact_sales_line")
    record("R3", "overall gross margin is plausible (margin = net - standard cost)", 0.30 <= margin <= 0.55, f"{margin:.1%}")
    # Receipt consistency (after removing the planted double-post, which is exercised under the incident checks).
    expect_zero(connection, "R3", "each receipt has one store, time, member and staff flag across its lines",
                f"SELECT count(*) FROM (SELECT receipt_id FROM {DEDUPED_LINES} GROUP BY receipt_id HAVING count(DISTINCT store_key) > 1 "
                "OR count(DISTINCT sale_ts_utc) > 1 OR count(DISTINCT coalesce(member_key, -1)) > 1 OR count(DISTINCT staff_purchase_flag) > 1)")
    expect_zero(connection, "R3", "line numbers run 1..n within each receipt",
                f"SELECT count(*) FROM (SELECT receipt_id FROM {DEDUPED_LINES} GROUP BY receipt_id HAVING min(line_no) <> 1 OR max(line_no) <> count(*))")
    # Receipt/line totals against the maintained aggregate (control totals), recomputed from the lines.
    sql = f"""
    WITH shipped AS (
        SELECT web_order_id, CAST({helsinki('dispatch_ts_utc')} AS DATE) AS dispatch_date FROM fact_web_order WHERE dispatch_ts_utc IS NOT NULL),
    sold AS (
        SELECT CASE WHEN s.store_id = 900 THEN sh.dispatch_date ELSE f.sale_date END AS business_date, s.store_id,
               count(DISTINCT f.receipt_id) AS receipts, sum(f.quantity) AS units, sum(f.net_amount) AS net
        FROM {DEDUPED_LINES} f JOIN dim_store s USING (store_key) JOIN dim_product p USING (product_key)
        LEFT JOIN shipped sh ON sh.web_order_id = f.receipt_id
        WHERE s.store_id <> 999 AND p.category <> '{cfg.TEST_CATEGORY}' GROUP BY 1, 2),
    returned AS (
        SELECT r.return_date AS business_date, s.store_id, sum(r.refund_net) AS ret
        FROM fact_return_line r JOIN dim_store s USING (store_key) JOIN dim_product p USING (product_key)
        WHERE p.category <> '{cfg.TEST_CATEGORY}' GROUP BY 1, 2),
    recomputed AS (
        SELECT coalesce(a.business_date, b.business_date) AS business_date, coalesce(a.store_id, b.store_id) AS store_id,
               coalesce(a.receipts, 0) AS receipts, coalesce(a.units, 0) AS units, coalesce(a.net, 0) AS net, coalesce(b.ret, 0) AS ret
        FROM sold a FULL OUTER JOIN returned b ON a.business_date = b.business_date AND a.store_id = b.store_id)
    SELECT count(*) FROM recomputed x FULL OUTER JOIN rpt_daily_store_sales r
      ON r.business_date = x.business_date AND r.store_id = x.store_id
    WHERE r.business_date IS NULL OR x.business_date IS NULL OR r.receipts <> x.receipts OR r.units_sold <> x.units
       OR r.net_sales_before_returns <> x.net OR r.returns_net <> x.ret OR r.net_sales <> x.net - x.ret
    """
    expect_zero(connection, "R3", "rpt_daily_store_sales equals the lines (control totals) after removing duplicate postings", sql)


# ---------------------------------------------------------------------------
# Rule 4: calendar
# ---------------------------------------------------------------------------

def rule_4(connection) -> None:
    print("Rule 4: calendar")
    dim_date = connection.execute("SELECT * FROM dim_date ORDER BY calendar_date").df()
    ref = connection.execute("SELECT * FROM ref_fiscal_calendar ORDER BY period_start_date").df()
    dates = pd.to_datetime(dim_date["calendar_date"])
    record("R4", "one row per day, contiguous, covering the window",
           dates.is_unique and (dates.diff().dropna() == pd.Timedelta(days=1)).all() and dates.iloc[0].date() == cfg.WINDOW_START
           and dates.iloc[-1].date() == cfg.WINDOW_END, f"{len(dim_date)} days")
    week_start = pd.to_datetime(dim_date["fiscal_week_start_date"])
    week_end = pd.to_datetime(dim_date["fiscal_week_end_date"])
    record("R4", "weeks run Monday to Sunday", (week_start.dt.weekday == 0).all() and (week_end.dt.weekday == 6).all()
           and ((week_end - week_start) == pd.Timedelta(days=6)).all() and (dates >= week_start).all() and (dates <= week_end).all())
    record("R4", "each fiscal week has exactly seven days",
           (dim_date.groupby(["fiscal_year", "fiscal_week"]).size() == 7).all())
    starts_ok = all(pd.Timestamp(start).weekday() == 0 and abs((pd.Timestamp(start) - pd.Timestamp(start.year, 5, 1)).days) <= 3
                    for start in cfg.FISCAL_YEAR_STARTS.values())
    record("R4", "fiscal years start on the Monday nearest 1 May", starts_ok)
    only_one = dim_date.groupby("calendar_date")[["fiscal_year", "fiscal_quarter", "fiscal_period", "fiscal_week"]].nunique().max().max() == 1
    record("R4", "every date maps to exactly one fiscal year, quarter, period and week", bool(only_one))
    complete_ok = True
    detail = []
    for fiscal_year, group in dim_date.groupby("fiscal_year"):
        start_year = int(fiscal_year[2:6])
        weeks_total = group["fiscal_week"].nunique()
        expected_weeks = cfg.FISCAL_YEAR_WEEKS[start_year]
        loaded_to_end = pd.Timestamp(group["calendar_date"].max()) >= pd.Timestamp(
            cfg.FISCAL_YEAR_STARTS[start_year] + timedelta(days=7 * expected_weeks - 1))
        if loaded_to_end and weeks_total != expected_weeks:
            complete_ok = False
        per_period = group.groupby("fiscal_period")["fiscal_week"].nunique()
        pattern = list(cfg.PERIOD_WEEKS_445)
        if expected_weeks == 53:
            pattern[11] += 1
        for period, weeks in per_period.items():
            if loaded_to_end and weeks != pattern[period - 1]:
                complete_ok = False
            if not loaded_to_end and period < per_period.index.max() and weeks != pattern[period - 1]:
                complete_ok = False
        quarters_ok = (group["fiscal_quarter"] == (group["fiscal_period"] - 1) // 3 + 1).all()
        flag_ok = (group["is_53_week_year"] == (expected_weeks == 53)).all() and (group["weeks_in_fiscal_year"] == expected_weeks).all()
        if not (quarters_ok and flag_ok):
            complete_ok = False
        detail.append(f"{fiscal_year}: {weeks_total} wks")
    record("R4", "4-4-5 pattern holds; 52 weeks per year and 53 in FY2025/26; quarter mapping and 53-week flags consistent",
           complete_ok, "; ".join(detail))
    week_53 = dim_date[dim_date["fiscal_week"] == 53]
    record("R4", "week 53 exists only in FY2025/26 and sits in period 12",
           set(week_53["fiscal_year"]) == {"FY2025/26"} and set(week_53["fiscal_period"]) == {12} and len(week_53) == 7)
    matches = True
    for row in ref.itertuples():
        subset = dim_date[(dim_date["fiscal_year"] == row.fiscal_year) & (dim_date["fiscal_period"] == row.fiscal_period)]
        if row.fully_loaded:
            matches &= (pd.Timestamp(subset["calendar_date"].min()) == pd.Timestamp(row.period_start_date)
                        and pd.Timestamp(subset["calendar_date"].max()) == pd.Timestamp(row.period_end_date)
                        and subset["fiscal_week"].nunique() == row.weeks_in_period)
        else:
            matches &= pd.Timestamp(subset["calendar_date"].min()) == pd.Timestamp(row.period_start_date)
    record("R4", "ref_fiscal_calendar agrees with dim_date", bool(matches), f"{len(ref)} periods")
    holiday_ok = (dim_date.loc[dim_date["holiday_name"] == "Midsummer Eve", "day_of_week"] == 5).all() and \
                 (dim_date.loc[dim_date["holiday_name"] == "Good Friday", "day_of_week"] == 5).all() and \
                 (dim_date.loc[dim_date["holiday_name"] == "Easter Sunday", "day_of_week"] == 7).all()
    record("R4", "holiday dates fall on the right weekdays", bool(holiday_ok))


# ---------------------------------------------------------------------------
# Rule 5: returns
# ---------------------------------------------------------------------------

def rule_5(connection) -> None:
    print("Rule 5: returns")
    base = f"""
    FROM fact_return_line r JOIN fact_sales_line f USING (sales_line_id)
    LEFT JOIN fact_web_order o ON o.web_order_id = f.receipt_id
    """
    base_date = f"coalesce(CAST({helsinki('o.dispatch_ts_utc')} AS DATE), f.sale_date)"
    expect_zero(connection, "R5", "returned quantity <= sold quantity (per return and cumulatively)",
                "SELECT count(*) FROM (SELECT f.sales_line_id FROM fact_return_line r JOIN fact_sales_line f USING (sales_line_id) "
                "GROUP BY f.sales_line_id, f.quantity HAVING sum(r.quantity_returned) > f.quantity)")
    expect_zero(connection, "R5", "returned quantity >= 1", "SELECT count(*) FROM fact_return_line WHERE quantity_returned < 1")
    expect_zero(connection, "R5", "return date >= sale date, and >= dispatch date for web sales",
                f"SELECT count(*) {base} WHERE r.return_date < f.sale_date OR r.return_date < {base_date}")
    expect_zero(connection, "R5", "refund net <= original net (per return and cumulatively)",
                "SELECT count(*) FROM (SELECT f.sales_line_id FROM fact_return_line r JOIN fact_sales_line f USING (sales_line_id) "
                "GROUP BY f.sales_line_id, f.net_amount HAVING sum(r.refund_net) > f.net_amount)")
    # Within the returns window: 30 days from sale (dispatch for web), extended when the return day itself was a closed day.
    expect_zero(connection, "R5", "return within 30 days, extended only over closed days",
                f"""SELECT count(*) {base} JOIN dim_store s ON s.store_key = r.store_key
                    JOIN dim_date d ON d.calendar_date = r.return_date - 1
                    WHERE r.return_date - {base_date} > {cfg.RETURN_WINDOW_DAYS}
                      AND d.is_trading_day AND NOT EXISTS (SELECT 1 FROM ref_store_closure c WHERE c.store_id = s.store_id
                          AND r.return_date - 1 BETWEEN c.closure_start_date AND c.closure_end_date)""")
    stats = connection.execute(
        f"SELECT count(*), sum(quantity_returned), max(return_date - {base_date.replace('o.', 'o.')}) "
        f"{base}").fetchone()
    record("R5", "returns present", stats[0] > 0, f"{stats[0]:,} returns, longest lag {stats[2]} days")
    rate = scalar(connection, "SELECT sum(r.refund_net) / (SELECT sum(net_amount) FROM fact_sales_line) FROM fact_return_line r")
    record("R5", "overall refund share of sales is plausible", 0.02 <= rate <= 0.09, f"{rate:.1%}")


# ---------------------------------------------------------------------------
# Rule 6: web orders and time zones
# ---------------------------------------------------------------------------

def rule_6(connection) -> None:
    print("Rule 6: web orders and time zones")
    expect_zero(connection, "R6", "dispatch >= order time", "SELECT count(*) FROM fact_web_order WHERE dispatch_ts_utc < order_ts_utc")
    expect_zero(connection, "R6", "cancelled orders have no dispatch and no sales lines",
                "SELECT count(*) FROM fact_web_order o WHERE o.status = 'cancelled' AND (o.dispatch_ts_utc IS NOT NULL OR EXISTS "
                "(SELECT 1 FROM fact_sales_line f WHERE f.receipt_id = o.web_order_id))")
    expect_zero(connection, "R6", "processing orders have no dispatch, no lines and are recent",
                f"SELECT count(*) FROM fact_web_order o WHERE o.status = 'processing' AND (o.dispatch_ts_utc IS NOT NULL OR EXISTS "
                f"(SELECT 1 FROM fact_sales_line f WHERE f.receipt_id = o.web_order_id) OR "
                f"CAST({helsinki('o.order_ts_utc')} AS DATE) < DATE '{cfg.WINDOW_END - timedelta(days=cfg.WEB_PROCESSING_WINDOW_DAYS)}')")
    expect_zero(connection, "R6", "delivered/collected orders have a dispatch time",
                "SELECT count(*) FROM fact_web_order WHERE status IN ('delivered', 'collected') AND dispatch_ts_utc IS NULL")
    expect_zero(connection, "R6", "status matches fulfilment type; pickup store only for click-and-collect",
                "SELECT count(*) FROM fact_web_order WHERE (status = 'collected' AND fulfilment_type <> 'click_and_collect') OR "
                "(status = 'delivered' AND fulfilment_type <> 'home_delivery') OR "
                "((fulfilment_type = 'click_and_collect') <> (pickup_store_key IS NOT NULL))")
    expect_zero(connection, "R6", "guest orders have no member; logged-in orders have one",
                "SELECT count(*) FROM fact_web_order WHERE (login_state = 'guest') <> (member_key IS NULL)")
    expect_zero(connection, "R6", "order total = sum of line gross for shipped orders; line count matches",
                f"SELECT count(*) FROM fact_web_order o JOIN (SELECT receipt_id, sum(gross_amount) g, count(*) n FROM {DEDUPED_LINES} "
                "GROUP BY 1) l ON l.receipt_id = o.web_order_id WHERE abs(o.order_total_gross - l.g) > 0.001 OR o.line_count <> l.n")
    expect_zero(connection, "R6", "every line: sale_date = Helsinki date of sale_ts_utc (web: the order time)",
                f"SELECT count(*) FROM fact_sales_line WHERE sale_date <> CAST({helsinki('sale_ts_utc')} AS DATE)")
    expect_zero(connection, "R6", "store timestamps are UTC (Helsinki local time falls in opening hours)",
                f"SELECT count(*) FROM fact_sales_line f JOIN dim_store s USING (store_key) WHERE s.store_id < 900 "
                f"AND (hour({helsinki('sale_ts_utc')}) < 9 OR hour({helsinki('sale_ts_utc')}) > 20)")
    expect_zero(connection, "R6", "no dispatch on Sundays or closed days (UTC date)",
                "SELECT count(*) FROM fact_web_order o JOIN dim_date d ON d.calendar_date = CAST(o.dispatch_ts_utc AS DATE) "
                "WHERE d.day_of_week = 7 OR NOT d.is_trading_day")
    # Time-zone trap days must carry enough boundary orders and dispatches to change the answer.
    for trap_day in cfg.TIMEZONE_TRAP_DAYS:
        row = connection.execute(f"""
            SELECT
              sum(CASE WHEN CAST({helsinki('order_ts_utc')} AS DATE) = DATE '{trap_day}' AND CAST(order_ts_utc AS DATE) <> DATE '{trap_day}' THEN 1 ELSE 0 END)
              + sum(CASE WHEN CAST(order_ts_utc AS DATE) = DATE '{trap_day}' AND CAST({helsinki('order_ts_utc')} AS DATE) <> DATE '{trap_day}' THEN 1 ELSE 0 END),
              sum(CASE WHEN CAST({helsinki('order_ts_utc')} AS DATE) = DATE '{trap_day}' THEN 1 ELSE 0 END),
              sum(CASE WHEN CAST(order_ts_utc AS DATE) = DATE '{trap_day}' THEN 1 ELSE 0 END),
              sum(CASE WHEN CAST({helsinki('dispatch_ts_utc')} AS DATE) = DATE '{trap_day}' AND CAST(dispatch_ts_utc AS DATE) <> DATE '{trap_day}' THEN 1 ELSE 0 END)
              + sum(CASE WHEN CAST(dispatch_ts_utc AS DATE) = DATE '{trap_day}' AND CAST({helsinki('dispatch_ts_utc')} AS DATE) <> DATE '{trap_day}' THEN 1 ELSE 0 END)
            FROM fact_web_order WHERE status <> 'cancelled' OR status = 'cancelled'""").fetchone()
        boundary_orders, helsinki_count, utc_count, boundary_dispatch = [int(v or 0) for v in row]
        passed = (boundary_orders >= cfg.TIMEZONE_TRAP_MIN_BOUNDARY_ORDERS and helsinki_count != utc_count
                  and boundary_dispatch >= cfg.TIMEZONE_TRAP_MIN_BOUNDARY_DISPATCHES)
        record("R6", f"time-zone trap day {trap_day} bites", passed,
               f"boundary orders {boundary_orders}, Helsinki-day count {helsinki_count} vs UTC-day count {utc_count}, boundary dispatches {boundary_dispatch}")
    # Black Friday midnight deals show up as local-midnight orders.
    for bf in cfg.BLACK_FRIDAYS:
        midnight = scalar(connection, f"SELECT count(*) FROM fact_web_order WHERE CAST({helsinki('order_ts_utc')} AS DATE) = DATE '{bf}' "
                                      f"AND hour({helsinki('order_ts_utc')}) = 0")
        record("R6", f"Black Friday {bf} has a midnight order spike", midnight >= 25, f"{midnight} orders in the first local hour")


# ---------------------------------------------------------------------------
# Rule 7: migration and the legacy view
# ---------------------------------------------------------------------------

def rule_7(connection) -> None:
    print("Rule 7: migration")
    migration = cfg.MIGRATION_DATE
    expect_zero(connection, "R7", "channel_code filled only before the migration; channel_id only from it",
                f"SELECT count(*) FROM fact_sales_line WHERE (sale_date < DATE '{migration}' AND (channel_code IS NULL OR channel_id IS NOT NULL)) "
                f"OR (sale_date >= DATE '{migration}' AND (channel_code IS NOT NULL OR channel_id IS NULL))")
    expect_zero(connection, "R7", "click-and-collect key (3) never appears before the migration",
                f"SELECT count(*) FROM fact_sales_line WHERE channel_id = 3 AND sale_date < DATE '{migration}'")
    expect_zero(connection, "R7", "pre-migration channel codes match store/web (ST for stores, WB for web)",
                f"SELECT count(*) FROM fact_sales_line f JOIN dim_store s USING (store_key) WHERE f.sale_date < DATE '{migration}' "
                "AND f.channel_code <> CASE WHEN s.store_id = 900 THEN 'WB' ELSE 'ST' END")
    # Channel id vs fulfilment type: any mismatch must be the planted incident (checked under the incident section).
    inc4 = cfg.INCIDENT_CNC_MISLABEL
    expect_zero(connection, "R7", "channel_id agrees with fulfilment type outside the planted incident window",
                f"SELECT count(*) FROM fact_sales_line f JOIN fact_web_order o ON o.web_order_id = f.receipt_id "
                f"WHERE f.sale_date >= DATE '{migration}' AND NOT (f.sale_date BETWEEN DATE '{inc4['start']}' AND DATE '{inc4['end']}') "
                "AND f.channel_id <> CASE WHEN o.fulfilment_type = 'click_and_collect' THEN 3 ELSE 2 END")
    # Legacy view: matches the canonical tables before, diverges after.
    before = f"""
    SELECT count(*) FROM (
      SELECT v.sale_date, sum(v.net_sales) AS view_net FROM rpt.v_daily_sales v WHERE v.sale_date < DATE '{migration}' GROUP BY 1) a
    FULL OUTER JOIN (
      SELECT f.sale_date, sum(f.net_amount) AS net FROM fact_sales_line f JOIN dim_store s USING (store_key)
      WHERE f.sale_date < DATE '{migration}' AND s.store_id <> 999 GROUP BY 1) b USING (sale_date)
    WHERE a.view_net IS NULL OR b.net IS NULL OR a.view_net <> b.net"""
    expect_zero(connection, "R7", "legacy view equals the canonical tables for every day before the migration", before)
    after = connection.execute(f"""
    SELECT sum(CASE WHEN w.web_net > 0 THEN 1 ELSE 0 END), sum(CASE WHEN w.web_net > 0 AND coalesce(v.view_web, 0) = 0 THEN 1 ELSE 0 END),
           sum(CASE WHEN abs(coalesce(v.view_store, 0) - w.store_net) > 0.001 THEN 1 ELSE 0 END)
    FROM (SELECT f.sale_date, sum(CASE WHEN s.store_id = 900 THEN f.net_amount ELSE 0 END) AS web_net,
                 sum(CASE WHEN s.store_id < 900 THEN f.net_amount ELSE 0 END) AS store_net
          FROM fact_sales_line f JOIN dim_store s USING (store_key) WHERE f.sale_date >= DATE '{migration}' GROUP BY 1) w
    LEFT JOIN (SELECT sale_date, sum(CASE WHEN channel = 'WB' THEN net_sales ELSE 0 END) AS view_web,
                      sum(CASE WHEN channel = 'ST' THEN net_sales ELSE 0 END) AS view_store FROM rpt.v_daily_sales GROUP BY 1) v
      ON v.sale_date = w.sale_date""").fetchone()
    record("R7", "after the migration the legacy view shows no web sales on any day when web sold, and store sales still match",
           after[0] > 0 and after[1] == after[0] and after[2] == 0, f"{after[0]} days with web sales, {after[1]} missing from the view")


# ---------------------------------------------------------------------------
# Rule 8: stores
# ---------------------------------------------------------------------------

def rule_8(connection) -> None:
    print("Rule 8: stores")
    expect_zero(connection, "R8", "no sales before opening or after closure",
                "SELECT count(*) FROM fact_sales_line f JOIN dim_store s USING (store_key) WHERE s.store_id < 900 AND "
                "(f.sale_date < coalesce(s.open_date, DATE '1900-01-01') OR f.sale_date > coalesce(s.close_date, DATE '9999-12-31'))")
    expect_zero(connection, "R8", "no sales during refit closures",
                "SELECT count(*) FROM fact_sales_line f JOIN dim_store s USING (store_key) JOIN ref_store_closure c ON c.store_id = s.store_id "
                "WHERE f.sale_date BETWEEN c.closure_start_date AND c.closure_end_date")
    expect_zero(connection, "R8", "no store sales on closed days",
                "SELECT count(*) FROM fact_sales_line f JOIN dim_store s USING (store_key) JOIN dim_date d ON d.calendar_date = f.sale_date "
                "WHERE s.store_id < 900 AND NOT d.is_trading_day")
    expect_zero(connection, "R8", "no store returns before opening, after closure, in a closure, or on a closed day",
                "SELECT count(*) FROM fact_return_line r JOIN dim_store s USING (store_key) JOIN dim_date d ON d.calendar_date = r.return_date "
                "WHERE s.store_id < 900 AND (r.return_date < coalesce(s.open_date, DATE '1900-01-01') OR r.return_date > coalesce(s.close_date, DATE '9999-12-31') "
                "OR NOT d.is_trading_day OR EXISTS (SELECT 1 FROM ref_store_closure c WHERE c.store_id = s.store_id AND r.return_date BETWEEN c.closure_start_date AND c.closure_end_date))")
    expect_zero(connection, "R8", "store 999 carries only training (test article) and staff-flagged lines, never a member",
                f"SELECT count(*) FROM fact_sales_line f JOIN dim_store s USING (store_key) JOIN dim_product p USING (product_key) "
                f"WHERE s.store_id = 999 AND ((NOT f.staff_purchase_flag AND p.category <> '{cfg.TEST_CATEGORY}') OR f.member_key IS NOT NULL)")
    expect_zero(connection, "R8", "store 999 has no returns and no stock",
                "SELECT (SELECT count(*) FROM fact_return_line r JOIN dim_store s USING (store_key) WHERE s.store_id = 999) + "
                "(SELECT count(*) FROM fact_stock_week w JOIN dim_store s USING (store_key) WHERE s.store_id IN (900, 999))")
    trading_at_end = scalar(connection, "SELECT count(*) FROM dim_store WHERE is_current AND store_id < 900 AND close_date IS NULL")
    record("R8", "38 stores trading at the end of the window", trading_at_end == cfg.EXPECTED_STORES_TRADING_AT_END, f"{trading_at_end}")
    expect_zero(connection, "R8", "refit closures are whole fiscal weeks (Monday to Sunday) of 4-6 weeks",
                "SELECT count(*) FROM ref_store_closure WHERE dayofweek(closure_start_date) <> 1 OR dayofweek(closure_end_date) <> 0 "
                "OR weeks_closed NOT BETWEEN 4 AND 6 OR (closure_end_date - closure_start_date + 1) <> 7 * weeks_closed")
    openings = connection.execute(
        "SELECT s.store_id, min(f.sale_date) - s.open_date FROM fact_sales_line f JOIN dim_store s USING (store_key) "
        "WHERE s.open_date IS NOT NULL GROUP BY s.store_id, s.open_date").fetchall()
    record("R8", "new stores start trading within three days of opening", all(d is not None and d <= 3 for _, d in openings), str(openings))
    closing = connection.execute(
        "SELECT s.store_id, s.close_date - max(f.sale_date) FROM fact_sales_line f JOIN dim_store s USING (store_key) "
        "WHERE s.close_date IS NOT NULL GROUP BY s.store_id, s.close_date").fetchall()
    record("R8", "the closed store trades until its closing date", all(d <= 3 for _, d in closing), str(closing))


# ---------------------------------------------------------------------------
# Rule 9: stock
# ---------------------------------------------------------------------------

def rule_9(connection) -> None:
    print("Rule 9: stock")
    expect_zero(connection, "R9", "closing stock >= 0", "SELECT count(*) FROM fact_stock_week WHERE closing_units < 0")
    expect_zero(connection, "R9", "closing value = closing units x standard unit cost",
                "SELECT count(*) FROM fact_stock_week w JOIN dim_product p USING (product_key) "
                "WHERE abs(w.closing_value - w.closing_units * p.standard_unit_cost) > 0.001")
    connection.execute(f"""
    CREATE TEMP TABLE stock_dedup AS
    SELECT s.store_id, p.sku, w.week_ending_date, w.closing_units, w.receipts_units, w.adjustment_units
    FROM (SELECT * FROM fact_stock_week QUALIFY row_number() OVER (PARTITION BY store_key, product_key, week_ending_date ORDER BY etl_loaded_at) = 1) w
    JOIN dim_store s USING (store_key) JOIN dim_product p USING (product_key)""")
    connection.execute(f"""
    CREATE TEMP TABLE sold_week AS
    SELECT s.store_id, p.sku, d.fiscal_week_end_date AS week_ending_date, sum(f.quantity) AS sold
    FROM {DEDUPED_LINES} f JOIN dim_store s USING (store_key) JOIN dim_product p USING (product_key)
    JOIN dim_date d ON d.calendar_date = f.sale_date WHERE s.store_id < 900 GROUP BY 1, 2, 3""")
    connection.execute("""
    CREATE TEMP TABLE returned_week AS
    SELECT s.store_id, p.sku, d.fiscal_week_end_date AS week_ending_date, sum(r.quantity_returned) AS returned
    FROM fact_return_line r JOIN dim_store s USING (store_key) JOIN dim_product p USING (product_key)
    JOIN dim_date d ON d.calendar_date = r.return_date WHERE s.store_id < 900 GROUP BY 1, 2, 3""")
    expect_zero(connection, "R9", "no duplicate store x SKU x week rows outside the planted reload",
                f"SELECT count(*) FROM (SELECT w.store_key, w.product_key, w.week_ending_date FROM fact_stock_week w GROUP BY ALL HAVING count(*) > 1) x "
                f"JOIN dim_store s ON s.store_key = x.store_key WHERE NOT (x.week_ending_date = DATE '{cfg.INCIDENT_STOCK_RELOAD['week_ending']}' "
                f"AND s.region = '{cfg.INCIDENT_STOCK_RELOAD['region_new']}')")
    expect_zero(connection, "R9", "weekly rows are contiguous for each store x SKU",
                "SELECT count(*) FROM (SELECT store_id, sku, count(*) n, (max(week_ending_date) - min(week_ending_date)) / 7 + 1 span "
                "FROM stock_dedup GROUP BY 1, 2) WHERE n <> span")
    reconcile = """
    SELECT count(*) FROM (
      SELECT w.*, coalesce(lag(w.closing_units) OVER (PARTITION BY w.store_id, w.sku ORDER BY w.week_ending_date), 0) AS opening,
             coalesce(sw.sold, 0) AS sold, coalesce(rw.returned, 0) AS returned
      FROM stock_dedup w
      LEFT JOIN sold_week sw ON sw.store_id = w.store_id AND sw.sku = w.sku AND sw.week_ending_date = w.week_ending_date
      LEFT JOIN returned_week rw ON rw.store_id = w.store_id AND rw.sku = w.sku AND rw.week_ending_date = w.week_ending_date)
    WHERE closing_units <> opening + receipts_units + returned - sold + adjustment_units"""
    expect_zero(connection, "R9", "week-to-week stock reconciles: closing = opening + receipts + returns - sold + adjustments", reconcile)
    expect_zero(connection, "R9", "every store sale has a stock row for that store, SKU and week",
                "SELECT count(*) FROM sold_week sw WHERE NOT EXISTS (SELECT 1 FROM stock_dedup w WHERE w.store_id = sw.store_id "
                "AND w.sku = sw.sku AND w.week_ending_date = sw.week_ending_date)")
    expect_zero(connection, "R9", "every in-store return has a stock row for that store, SKU and week",
                "SELECT count(*) FROM returned_week rw WHERE NOT EXISTS (SELECT 1 FROM stock_dedup w WHERE w.store_id = rw.store_id "
                "AND w.sku = rw.sku AND w.week_ending_date = rw.week_ending_date)")
    connection.execute("DROP TABLE stock_dedup; DROP TABLE sold_week; DROP TABLE returned_week;")


# ---------------------------------------------------------------------------
# Rule 10: campaigns
# ---------------------------------------------------------------------------

def rule_10(connection) -> None:
    print("Rule 10: campaigns")
    expect_zero(connection, "R10", "holdout members are never exposed",
                "SELECT count(*) FROM fact_campaign_exposure e JOIN dim_member m USING (member_key) JOIN campaign_holdout h "
                "ON h.campaign_id = e.campaign_id AND h.member_id = m.member_id")
    expect_zero(connection, "R10", "exposure only to members with consent on the exposure date",
                "SELECT count(*) FROM fact_campaign_exposure e JOIN dim_member m USING (member_key) WHERE NOT m.marketing_consent")
    expect_zero(connection, "R10", "contacts fall inside the campaign window",
                f"SELECT count(*) FROM fact_campaign_exposure e JOIN dim_campaign c USING (campaign_id) "
                f"WHERE CAST({helsinki('e.contact_ts_utc')} AS DATE) NOT BETWEEN c.start_date AND c.end_date")
    expect_zero(connection, "R10", "holdout size matches campaign_holdout rows",
                "SELECT count(*) FROM dim_campaign c WHERE c.holdout_size <> (SELECT count(*) FROM campaign_holdout h WHERE h.campaign_id = c.campaign_id)")
    expect_zero(connection, "R10", "holdout is 8-12% of each mailing list",
                "SELECT count(*) FROM dim_campaign WHERE holdout_size < 0.08 * mailing_list_size OR holdout_size > 0.12 * mailing_list_size")
    expect_zero(connection, "R10", "holdout members consented at the campaign start",
                "SELECT count(*) FROM campaign_holdout h JOIN dim_campaign c USING (campaign_id) WHERE NOT EXISTS "
                "(SELECT 1 FROM dim_member m WHERE m.member_id = h.member_id AND c.start_date BETWEEN m.valid_from AND m.valid_to AND m.marketing_consent)")
    fanout = scalar(connection, "SELECT count(*) FROM (SELECT campaign_id, member_key FROM fact_campaign_exposure GROUP BY 1, 2 HAVING count(*) > 1)")
    record("R10", "contacts fan out (many per member per campaign), so the join trap is live", fanout > 1000, f"{fanout:,} member-campaign pairs with 2+ contacts")
    # The planted effect exists: exposed members out-spend holdouts in the campaign window (sanity, large campaigns).
    row = connection.execute(f"""
    WITH big AS (SELECT campaign_id, start_date, end_date + {cfg.CAMPAIGN_UPLIFT_WINDOW_EXTRA_DAYS} AS end_plus FROM dim_campaign WHERE campaign_id IN (5, 15)),
    exposed AS (SELECT DISTINCT e.campaign_id, m.member_id FROM fact_campaign_exposure e JOIN dim_member m USING (member_key)),
    spend AS (SELECT b.campaign_id, m.member_id, sum(f.net_amount) AS net FROM big b
              JOIN fact_sales_line f ON f.sale_date BETWEEN b.start_date AND b.end_plus
              JOIN dim_member m ON m.member_key = f.member_key GROUP BY 1, 2)
    SELECT b.campaign_id,
      (SELECT sum(coalesce(s.net, 0)) / count(*) FROM exposed x LEFT JOIN spend s ON s.campaign_id = x.campaign_id AND s.member_id = x.member_id WHERE x.campaign_id = b.campaign_id),
      (SELECT sum(coalesce(s.net, 0)) / count(*) FROM campaign_holdout h LEFT JOIN spend s ON s.campaign_id = h.campaign_id AND s.member_id = h.member_id WHERE h.campaign_id = b.campaign_id)
    FROM big b ORDER BY 1""").fetchall()
    ok = all(exposed_mean > holdout_mean for _, exposed_mean, holdout_mean in row)
    record("R10", "exposed members out-spend the holdout in the big campaigns (planted uplift is detectable)", ok,
           "; ".join(f"campaign {c}: {e:.2f} vs {h:.2f}" for c, e, h in row))


# ---------------------------------------------------------------------------
# Rule 11: determinism
# ---------------------------------------------------------------------------

def rule_11(connection, skip: bool) -> None:
    print("Rule 11: determinism")
    manifest = json.loads(cfg.MANIFEST_PATH.read_text(encoding="utf-8"))
    current_hash, _ = compute_content_hash(connection)
    record("R11", "content hash of the database on disk equals the manifest", current_hash == manifest["content_hash"], current_hash[:16])
    if skip:
        record("R11", "rebuild from config gives the same content hash (skipped by --fast)", True, "skipped")
        return
    rebuild_dir = cfg.DATA_DIR / "_rebuild_check"
    rebuild_path = rebuild_dir / "rebuild.duckdb"
    log("Rebuilding from config into a scratch folder (this takes about a minute)")
    command = [sys.executable, str(cfg.CASE_ROOT / "code" / "generate_warehouse.py"), "--out", str(rebuild_path), "--no-internal", "--no-manifest"]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0 or not rebuild_path.exists():
        record("R11", "rebuild from config succeeds", False, result.stderr[-300:])
        return
    rebuilt = duckdb.connect(str(rebuild_path), read_only=True)
    rebuilt_hash, _ = compute_content_hash(rebuilt)
    rebuilt.close()
    from wh_common import file_sha256
    same_bytes = file_sha256(rebuild_path) == manifest["file_sha256"]
    record("R11", "rebuild from config gives the same content hash", rebuilt_hash == current_hash, rebuilt_hash[:16])
    print(f"      (database file bytes {'identical' if same_bytes else 'differ; content hash is the criterion'})")
    rebuild_path.unlink(missing_ok=True)
    rebuild_path.with_suffix(".duckdb.wal").unlink(missing_ok=True)
    try:
        rebuild_dir.rmdir()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Phase 2 checks beyond rules 1-11
# ---------------------------------------------------------------------------

def check_scale_and_incidents(connection) -> None:
    print("Phase 2: scale, mix and the planted incidents")
    lines = scalar(connection, "SELECT count(*) FROM fact_sales_line")
    low, high = cfg.EXPECTED_SALES_LINES_RANGE
    record("X1", "sales lines within the designed order of magnitude", low <= lines <= high, f"{lines:,}")
    skus = scalar(connection, "SELECT count(DISTINCT sku) FROM dim_product")
    record("X1", "about 4,000 SKUs", skus == cfg.N_SKUS_TOTAL, f"{skus:,}")
    members = scalar(connection, "SELECT count(DISTINCT member_id) FROM dim_member")
    record("X1", "about 60,000 loyalty members", members == cfg.EXPECTED_MEMBERS, f"{members:,}")
    web_share = scalar(connection, "SELECT sum(net_sales) FILTER (WHERE store_id = 900) / sum(net_sales) FROM rpt_daily_store_sales")
    record("X1", "web share of net sales is plausible (8-18%)", 0.08 <= web_share <= 0.18, f"{web_share:.1%}")
    member_share = scalar(connection, "SELECT sum(net_amount) FILTER (WHERE member_key IS NOT NULL) / sum(net_amount) FROM fact_sales_line")
    record("X1", "member share of sales is plausible (45-65%)", 0.45 <= member_share <= 0.65, f"{member_share:.1%}")
    objects = scalar(connection, "SELECT count(*) FROM information_schema.tables")
    record("X1", "about 35 objects (15 canonical plus clutter and views)", 30 <= objects <= 40, f"{objects}")

    manifest = json.loads(cfg.MANIFEST_PATH.read_text(encoding="utf-8"))["incidents_planted"]
    inc1 = cfg.INCIDENT_DOUBLE_POST
    duplicated = connection.execute(
        f"SELECT count(DISTINCT (f.receipt_id, f.line_no)), min(s.store_id), max(s.store_id), min(f.sale_date), max(f.sale_date) FROM (SELECT receipt_id, line_no FROM fact_sales_line "
        f"GROUP BY 1, 2 HAVING count(*) > 1) d JOIN fact_sales_line f USING (receipt_id, line_no) JOIN dim_store s USING (store_key)").fetchone()
    record("X2", "INC-1 double-post: duplicated line keys exist only for the planted store-week",
           duplicated[0] == manifest["INC-1"]["duplicated_lines"] and duplicated[1] == duplicated[2] == inc1["store_id"]
           and duplicated[3] >= inc1["week_start"] and duplicated[4] <= inc1["week_end"], f"{duplicated[0]:,} duplicated line keys")
    inc2 = cfg.INCIDENT_LOGIN_ORPHANS
    orphans = connection.execute(
        "SELECT count(*), min(CAST(timezone('Europe/Helsinki', o.order_ts_utc AT TIME ZONE 'UTC') AS DATE)), "
        "max(CAST(timezone('Europe/Helsinki', o.order_ts_utc AT TIME ZONE 'UTC') AS DATE)) FROM fact_web_order o "
        "WHERE o.login_state = 'logged_in' AND o.status IN ('delivered','collected') AND EXISTS (SELECT 1 FROM fact_sales_line f "
        "WHERE f.receipt_id = o.web_order_id AND f.member_key IS NULL)").fetchone()
    record("X2", "INC-2 login orphans: logged-in orders with member-less lines exist only inside the planted window",
           orphans[0] == manifest["INC-2"]["orders_affected"] and orphans[1] >= inc2["start"] and orphans[2] <= inc2["end"], f"{orphans[0]:,} orders")
    inc3 = cfg.INCIDENT_STOCK_RELOAD
    reloaded = connection.execute(
        "SELECT count(*), min(week_ending_date), max(week_ending_date) FROM (SELECT store_key, product_key, week_ending_date FROM fact_stock_week "
        "GROUP BY ALL HAVING count(*) > 1)").fetchone()
    record("X2", "INC-3 stock reload: duplicate stock rows exist only for the planted week",
           reloaded[0] == manifest["INC-3"]["duplicated_rows"] and reloaded[1] == reloaded[2] == inc3["week_ending"], f"{reloaded[0]:,} rows")
    inc4 = cfg.INCIDENT_CNC_MISLABEL
    mislabel = connection.execute(
        f"SELECT count(DISTINCT f.receipt_id), min(f.sale_date), max(f.sale_date) FROM fact_sales_line f JOIN fact_web_order o ON o.web_order_id = f.receipt_id "
        f"WHERE f.channel_id = 2 AND o.fulfilment_type = 'click_and_collect'").fetchone()
    record("X2", "INC-4 click-and-collect mislabel: affected orders sit inside the planted window",
           mislabel[0] == manifest["INC-4"]["orders_affected"] and mislabel[1] >= inc4["start"] and mislabel[2] <= inc4["end"], f"{mislabel[0]:,} orders")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the Tuomimetsa warehouse and world.")
    parser.add_argument("--fast", action="store_true", help="skip the rebuild for rule 11")
    parser.add_argument("--skip-world", action="store_true", help="skip the world / facts / dev-request checks")
    parser.add_argument("--skip-key", action="store_true", help="skip the request-set and answer-key checks (rules 12-15)")
    parser.add_argument("--skip-arms", action="store_true", help="skip the prompt-doc and skills-library checks (rules 16-18)")
    arguments = parser.parse_args()
    if not cfg.WAREHOUSE_PATH.exists():
        print(f"ERROR: {cfg.WAREHOUSE_PATH} not found; run generate_warehouse.py first.")
        return 1
    connection = duckdb.connect(str(cfg.WAREHOUSE_PATH), read_only=True)
    started = pd.Timestamp.now()
    try:
        for step in (rule_1, rule_2, rule_3, rule_4, rule_5, rule_6, rule_7, rule_8, rule_9, rule_10):
            step(connection)
        check_scale_and_incidents(connection)
        rule_11(connection, arguments.fast)
        if not arguments.skip_world:
            import validate_world
            validate_world.run(connection, record)
        if not arguments.skip_key:
            import validate_key
            validate_key.run(connection, record)
        if not arguments.skip_arms:
            import validate_arms
            validate_arms.run(connection, record)
    except Exception as error:
        import traceback
        traceback.print_exc()
        record("ERR", "validator crashed", False, str(error))
    finally:
        connection.close()
    failures = [r for r in RESULTS if not r["passed"]]
    cfg.VALIDATION_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg.VALIDATION_REPORT_PATH.write_text(json.dumps({
        "run_at": started.isoformat(timespec="seconds"), "checks": len(RESULTS), "failed": len(failures), "results": RESULTS},
        indent=2, default=str), encoding="utf-8")
    print(f"\n{len(RESULTS) - len(failures)} of {len(RESULTS)} checks passed; report in {cfg.VALIDATION_REPORT_PATH}")
    if failures:
        print("FAILED CHECKS:")
        for item in failures:
            print(f"  - {item['rule']} {item['check']} {item['detail']}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
