"""Reference queries, naive variants and pandas recomputations, part B: patterns 5 to 8 (Project 11, Phase 3)."""
from __future__ import annotations

from datetime import date

import pandas as pd

import config as cfg
from key_lib import NET_EVENTS, WEB_DISPATCH, hel
from key_types import Interpretation, Naive, Question, col, question
from key_questions_a import NET_WITH_DISPATCH

TEST_ORDER_FILTER = ("NOT EXISTS (SELECT 1 FROM fact_sales_line tf JOIN dim_product tp ON tp.product_key = tf.product_key "
                     "WHERE tf.receipt_id = o.web_order_id AND tp.category = 'ZZ Test')")


# ---------------------------------------------------------------------------
# Pattern 5: web orders and web sales
# ---------------------------------------------------------------------------

def web_orders_on(local_date_sql: str, include_cancelled: bool = False, cancel_test: bool = True) -> str:
    cancelled = "" if include_cancelled else "AND o.status <> 'cancelled'"
    test = f"AND {TEST_ORDER_FILTER}" if cancel_test else ""
    return f"SELECT COUNT(*) AS web_orders FROM fact_web_order o WHERE {local_date_sql} {cancelled} {test};"


def web_orders_fn(day: str, utc: bool):
    def fn(world):
        web = world.web
        column = web.order_ts_utc.dt.normalize() if utc else web.order_date
        mask = (column == pd.Timestamp(day)) & (web.status != "cancelled") & (~web.test_order)
        return pd.DataFrame({"web_orders": [int(mask.sum())]})
    return fn


@question("W1")
def w1() -> Question:
    """Web orders placed on Cyber Monday 2025 (1 December), Helsinki day."""
    day = "2025-12-01"
    reference = web_orders_on(f"{hel('o.order_ts_utc')} = DATE '{day}'")
    utc = web_orders_on(f"CAST(o.order_ts_utc AS DATE) = DATE '{day}'")
    return Question(
        "W1", 5, [col("web_orders", "measure", "count")], reference, web_orders_fn(day, utc=False),
        {"counts": "Web orders placed on Monday 1 December 2025 (Cyber Monday) by the Finnish calendar day, so an order placed at 00:30 Finnish time counts on the 1st even though it is still the 30th in UTC. Orders still being processed would count; none were.",
         "leaves_out": "Cancelled orders and the web test orders (test articles).",
         "docs": ["Metric dictionary, 'Web sales and time' (web orders are counted on the order date in Helsinki time; cancelled orders are not counted)", "Data quality register, 'Time' and 'Cancelled web orders'"],
         "result_note": "One number."},
        naive=[Naive("time_zone", "utc_day", utc, "Counts the UTC calendar day. The Cyber Monday midnight offer lands in the last hours of the previous UTC day, so orders are missing from the 1st and extra ones from the 2nd are included.")])


@question("O2")
def o2() -> Question:
    """Web orders placed on Black Friday 2025 (28 November) counted on the UTC day, because the request asks for UTC."""
    day = "2025-11-28"
    reference = web_orders_on(f"CAST(o.order_ts_utc AS DATE) = DATE '{day}'")
    helsinki = web_orders_on(f"{hel('o.order_ts_utc')} = DATE '{day}'")
    return Question(
        "O2", 5, [col("web_orders", "measure", "count")], reference, web_orders_fn(day, utc=True),
        {"counts": "Web orders whose UTC order time falls on Friday 28 November 2025 (Black Friday), because the request asks for the UTC day (for the carrier's report), not the Finnish day the company normally uses.",
         "leaves_out": "Cancelled orders and the web test orders.",
         "docs": ["Team notes, 'explicitly asks' rule", "Metric dictionary, 'Web sales and time' (Helsinki is the default)"],
         "result_note": "One number."},
        naive=[Naive("override", "helsinki_day_default", helsinki, "Counts the Finnish calendar day (the company default) although the request asks for the UTC day. The Black Friday midnight offer moves a few hundred orders from the 27th to the 28th.")])


def web_daily_sql(sales_date_expr: str, from_day: str, to_day: str) -> str:
    return f"""WITH {WEB_DISPATCH},
events AS (
    SELECT {sales_date_expr} AS business_date, f.net_amount AS net_sales
    FROM fact_sales_line f
    JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
    JOIN fact_web_order o ON o.web_order_id = f.receipt_id
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id = 900 AND p.category <> 'ZZ Test'
    UNION ALL
    SELECT r.return_date, -r.refund_net
    FROM fact_return_line r JOIN dim_store s ON s.store_key = r.store_key JOIN dim_product p ON p.product_key = r.product_key
    WHERE s.store_id = 900 AND p.category <> 'ZZ Test'
)
SELECT business_date, ROUND(SUM(net_sales), 2) AS web_net_sales FROM events
WHERE business_date BETWEEN DATE '{from_day}' AND DATE '{to_day}'
GROUP BY 1 ORDER BY 1;"""


@question("W2")
def w2() -> Question:
    """Daily web net sales 15 to 23 December 2025."""
    first, last = "2025-12-15", "2025-12-23"
    reference = web_daily_sql("w.dispatch_date", first, last)
    utc_dispatch = web_daily_sql("CAST(o.dispatch_ts_utc AS DATE)", first, last)
    order_day = web_daily_sql("f.sale_date", first, last)

    def pandas_fn(world):
        e = world.events()
        e = e[(e.store_id == 900) & (e.date >= pd.Timestamp(first)) & (e.date <= pd.Timestamp(last))]
        out = (e.groupby("date").net_c.sum() / 100.0).rename("web_net_sales")
        out.index.name = "business_date"
        return out.reset_index()

    return Question(
        "W2", 5, [col("business_date", "dimension", "date"), col("web_net_sales", "measure", "eur")], reference, pandas_fn,
        {"counts": "Web net sales for each day from 15 to 23 December 2025. A web sale counts on the day it was dispatched, by the Finnish calendar day; refunds booked to the web shop come off on the day they were booked.",
         "leaves_out": "Orders not yet dispatched, cancelled orders, the web test orders, and refunds for web goods handed in at a store (booked to that store).",
         "docs": ["Metric dictionary, 'Web sales and time' (dispatch date in Helsinki time)", "Data quality register, 'On web lines, sale_date is the order date'"],
         "result_note": "Nine rows, one per day."},
        naive=[Naive("time_zone", "utc_dispatch_day", utc_dispatch, "Uses the UTC date of the dispatch time. Carrier hand-over scans after 21:00 UTC (midnight in Finland) fall on the next Finnish day and are put on the wrong one."),
               Naive("time_zone", "order_date_not_dispatch", order_day, "Puts each sale on the day the order was placed instead of the day it was dispatched.")])


@question("W4")
def w4() -> Question:
    """Web net sales by period for P5 to P8 of last year (FY2025/26), across the 3 November migration."""
    reference = f"""{NET_WITH_DISPATCH}
SELECT d.fiscal_period, ROUND(SUM(n.net_sales), 2) AS web_net_sales
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date
WHERE n.store_id = 900 AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period BETWEEN 5 AND 8
GROUP BY 1 ORDER BY 1;"""
    legacy_view = """SELECT d.fiscal_period, ROUND(SUM(v.net_sales), 2) AS web_net_sales
FROM rpt.v_daily_sales v JOIN dim_date d ON d.calendar_date = v.sale_date
WHERE v.channel = 'WB' AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period BETWEEN 5 AND 8
GROUP BY 1 ORDER BY 1;"""
    channel_code = f"""SELECT d.fiscal_period, ROUND(SUM(f.net_amount), 2) AS web_net_sales
FROM fact_sales_line f JOIN dim_date d ON d.calendar_date = f.sale_date
WHERE f.channel_code = 'WB' AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period BETWEEN 5 AND 8
GROUP BY 1 ORDER BY 1;"""

    def pandas_fn(world):
        e = world.events()
        e = e[(e.store_id == 900) & (e.fy == "FY2025/26") & e.period.between(5, 8)]
        out = (e.groupby("period").net_c.sum() / 100.0).rename("web_net_sales")
        out.index.name = "fiscal_period"
        return out.reset_index()

    return Question(
        "W4", 5, [col("fiscal_period", "dimension", "count"), col("web_net_sales", "measure", "eur")], reference, pandas_fn,
        {"counts": "Web net sales (dispatch date, after returns booked to the web shop) for periods 5 to 8 of last year, 25 August to 21 December 2025. The web platform migrated on 3 November 2025, inside period 7. The web shop is found by its own store number (900), which works on both sides of the migration.",
         "leaves_out": "Cancelled and unshipped orders, web test orders, refunds for web goods handed in at a store.",
         "docs": ["Data quality register, 'Web platform migration and the legacy view' (store 900, not channel_code)", "Metric dictionary, 'Web sales and time'"],
         "result_note": "Four rows, one per period."},
        naive=[Naive("migration", "legacy_view", legacy_view, "Reads the old reporting view rpt.v_daily_sales, which stops showing web sales on 3 November 2025. Period 7 is short and periods 8 and 9 show nothing."),
               Naive("migration", "channel_code_filter", channel_code, "Filters on channel_code = 'WB', a column that is no longer filled after the migration, so web sales vanish from 3 November.")])


# ---------------------------------------------------------------------------
# Pattern 6: click-and-collect share
# ---------------------------------------------------------------------------

def cnc_share_sql(periods: tuple, fiscal_year: str, cnc_by: str) -> str:
    """Click-and-collect share of web net sales by period. cnc_by: 'fulfilment' (the order's type) or 'channel_id'."""
    flag_sales = "o.fulfilment_type = 'click_and_collect'" if cnc_by == "fulfilment" else "f.channel_id = 3"
    flag_returns = "o.fulfilment_type = 'click_and_collect'" if cnc_by == "fulfilment" else "f.channel_id = 3"
    return f"""WITH {WEB_DISPATCH},
web_events AS (
    SELECT w.dispatch_date AS business_date, ({flag_sales}) AS is_cnc, f.net_amount AS net_sales
    FROM fact_sales_line f
    JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
    JOIN fact_web_order o ON o.web_order_id = f.receipt_id JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id = 900 AND p.category <> 'ZZ Test'
    UNION ALL
    SELECT r.return_date, ({flag_returns}), -r.refund_net
    FROM fact_return_line r
    JOIN dim_store s ON s.store_key = r.store_key
    JOIN fact_sales_line f ON f.sales_line_id = r.sales_line_id
    JOIN dim_product p ON p.product_key = f.product_key
    JOIN fact_web_order o ON o.web_order_id = f.receipt_id
    WHERE s.store_id = 900 AND p.category <> 'ZZ Test'
)
SELECT d.fiscal_period,
       ROUND(100.0 * SUM(CASE WHEN e.is_cnc THEN e.net_sales ELSE 0 END) / SUM(e.net_sales), 2) AS click_collect_share_pct
FROM web_events e JOIN dim_date d ON d.calendar_date = e.business_date
WHERE d.fiscal_year = '{fiscal_year}' AND d.fiscal_period BETWEEN {periods[0]} AND {periods[1]}
GROUP BY 1 ORDER BY 1;"""


def cnc_share_fn(fiscal_year: str, periods: tuple, mode: str, source_world: str = "clean"):
    def fn(world):
        sales = world.sales[world.sales.is_web & (world.sales.category_was != cfg.TEST_CATEGORY)].copy()
        ful = world.web.set_index("web_order_id").fulfilment_type
        if mode == "fulfilment":
            sales["cnc"] = sales.receipt_id.map(ful) == "click_and_collect"
        else:
            sales["cnc"] = sales.channel_id == 3
        sales = world.fiscal(sales[sales.business_date.notna()], "business_date")
        sale_events = pd.DataFrame({"date": sales.business_date, "cnc": sales.cnc, "net_c": sales.net_c})
        lookup = world.sales.set_index("sales_line_id")
        returns = world.returns[(world.returns.store_id == 900) & (world.returns.category_was != cfg.TEST_CATEGORY)].copy()
        returns["receipt_id"] = returns.sales_line_id.map(lookup.receipt_id)
        if mode == "fulfilment":
            returns["cnc"] = returns.receipt_id.map(ful) == "click_and_collect"
        else:
            returns["cnc"] = returns.sales_line_id.map(lookup.channel_id) == 3
        return_events = pd.DataFrame({"date": returns.return_date, "cnc": returns.cnc, "net_c": -returns.refund_net_c})
        events = pd.concat([sale_events, return_events], ignore_index=True)
        events = world.fiscal(events, "date")
        events = events[(events.fy == fiscal_year) & events.period.between(*periods)]
        total = events.groupby("period").net_c.sum()
        cnc = events[events.cnc].groupby("period").net_c.sum().reindex(total.index).fillna(0)
        out = (100.0 * cnc / total).rename("click_collect_share_pct")
        out.index.name = "fiscal_period"
        return out.reset_index()
    return fn


CNC_COLUMNS = [col("fiscal_period", "dimension", "count"), col("click_collect_share_pct", "measure", "pct")]


@question("K1")
def k1() -> Question:
    reference = cnc_share_sql((6, 8), "FY2025/26", "fulfilment")
    return Question(
        "K1", 6, CNC_COLUMNS, reference, cnc_share_fn("FY2025/26", (6, 8), "fulfilment"),
        {"counts": "Click-and-collect net sales as a share of all web net sales, for periods 6 to 8 of last year (22 September to 21 December 2025). Click-and-collect counts as web. The type of each order comes from the order record, which is right on both sides of the 3 November 2025 migration (before it, click-and-collect orders had no channel key of their own).",
         "leaves_out": "Cancelled and unshipped orders, web test orders, refunds for web goods handed in at a store.",
         "docs": ["Metric dictionary, 'Web sales and time' (click-and-collect share)", "Data quality register, 'Web platform migration and the legacy view'"],
         "result_note": "Three rows, one per period."},
        naive=[Naive("migration", "channel_id_only", cnc_share_sql((6, 8), "FY2025/26", "channel_id"),
                     "Finds click-and-collect by the new channel key (3), which only exists from 3 November 2025. Period 6 shows no click-and-collect at all and period 7 only its last three weeks."),
               Naive("company_definition", "share_of_orders_not_sales", f"""WITH {WEB_DISPATCH}
SELECT d.fiscal_period, ROUND(100.0 * SUM(CASE WHEN o.fulfilment_type = 'click_and_collect' THEN 1 ELSE 0 END) / COUNT(*), 2) AS click_collect_share_pct
FROM fact_web_order o JOIN web_dispatch w ON w.web_order_id = o.web_order_id JOIN dim_date d ON d.calendar_date = w.dispatch_date
WHERE d.fiscal_year = 'FY2025/26' AND d.fiscal_period BETWEEN 6 AND 8 GROUP BY 1 ORDER BY 1;""",
                     "Works out the share of orders instead of the share of net sales, which the dictionary defines as click-and-collect net sales over all web net sales.")])


@question("K2")
def k2() -> Question:
    reference = cnc_share_sql((9, 10), "FY2025/26", "fulfilment")
    published = cnc_share_sql((9, 10), "FY2025/26", "channel_id")
    return Question(
        "K2", 6, CNC_COLUMNS, reference, cnc_share_fn("FY2025/26", (9, 10), "fulfilment"),
        {"counts": "Click-and-collect net sales as a share of all web net sales for periods 9 and 10 of last year (22 December 2025 to 22 February 2026). The type of each order comes from the order record.",
         "leaves_out": "Cancelled and unshipped orders, web test orders, refunds for web goods handed in at a store.",
         "docs": ["Metric dictionary, 'Web sales and time' (click-and-collect share)"],
         "result_note": "Two rows, one per period. In the published data the click-and-collect channel key was wrong on lines ordered between 12 January and 8 February 2026, so a share built from the channel key is understated for those weeks."},
        undocumented={"incident": "INC-4", "published_sql": published, "published_pandas_fn": cnc_share_fn("FY2025/26", (9, 10), "channel_id"),
                      "what": "For four weeks (12 January to 8 February 2026) click-and-collect sales lines carried the home-delivery channel key; the order record still shows the right fulfilment type.",
                      "keywords": [["channel", "click", "collect"], ["wrong", "mislabel", "mis-label", "incorrect", "home delivery", "home-delivery", "misclassif", "mismatch", "inconsisten", "understat"]],
                      "example_pass": "The channel_id on click-and-collect lines between 12 Jan and 8 Feb 2026 was set to home delivery, so the share by channel key is too low in those weeks.",
                      "example_fail": "Click-and-collect share was computed from fulfilment_type on the web orders."})


# ---------------------------------------------------------------------------
# Pattern 7: ATV
# ---------------------------------------------------------------------------

@question("AT")
def at() -> Question:
    """ATV by store format for P4 this year (stores only)."""
    def sql(store_filter: str, staff_filter: str) -> str:
        return f"""SELECT s.format, ROUND(SUM(f.net_amount) / COUNT(DISTINCT f.receipt_id), 2) AS atv
FROM fact_sales_line f
JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
JOIN dim_date d ON d.calendar_date = f.sale_date
WHERE {store_filter} {staff_filter} AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 4
GROUP BY 1 ORDER BY 1;"""

    reference = sql("s.store_id < 900", "AND NOT f.staff_purchase_flag")
    no_scope = sql("TRUE", "AND NOT f.staff_purchase_flag")

    def pandas_fn(world):
        s = world.sales
        s = world.fiscal(s, "sale_date")
        s = s[(s.store_id < 900) & ~s.staff & (s.category_was != cfg.TEST_CATEGORY) & (s.fy == "FY2026/27") & (s.period == 4)].copy()
        s["format"] = s.store_key.map(world.store_by_key["format"])
        net = s.groupby("format").net_c.sum() / 100.0
        receipts = s.groupby("format").receipt_id.nunique()
        out = (net / receipts).rename("atv")
        out.index.name = "format"
        return out.reset_index()

    return Question(
        "AT", 7, [col("format", "dimension", "text"), col("atv", "measure", "eur")], reference, pandas_fn,
        {"counts": "Average transaction value by store format (Large, Medium, Small) for period 4 of this year (3 to 30 August 2026): net sales before returns divided by the number of sales receipts.",
         "leaves_out": "Staff purchases, store 999, the web shop (ATV is a store measure) and test articles.",
         "docs": ["Metric dictionary, 'Transactions, members and campaigns' (ATV)", "Data quality register, 'staff_purchase_flag'"],
         "result_note": "Three rows."},
        naive=[Naive("exclusions", "no_store_scope", no_scope, "Does not limit the table to the physical stores, so the web shop shows up as a 'Web' format and the training store as its own line.")])


@question("A2")
def a2() -> Question:
    """ATV for the whole company including web orders, P1-P3 this year (override: web orders included)."""
    def sql(include_web: bool) -> str:
        web_clause = "" if include_web else "AND s.store_id < 900"
        return f"""WITH {WEB_DISPATCH}
SELECT ROUND(SUM(f.net_amount) / COUNT(DISTINCT f.receipt_id), 2) AS atv
FROM fact_sales_line f
JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
JOIN dim_date d ON d.calendar_date = COALESCE(w.dispatch_date, f.sale_date)
WHERE s.store_id <> 999 AND NOT f.staff_purchase_flag AND p.category <> 'ZZ Test' {web_clause}
  AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period BETWEEN 1 AND 3;"""

    def pandas_fn(world):
        s = world.fiscal(world.in_scope_sales(), "business_date")
        s = s[~s.staff & (s.fy == "FY2026/27") & s.period.between(1, 3)]
        return pd.DataFrame({"atv": [s.net_c.sum() / 100.0 / s.receipt_id.nunique()]})

    return Question(
        "A2", 7, [col("atv", "measure", "eur")], sql(True), pandas_fn,
        {"counts": "One ATV figure for the whole company for periods 1 to 3 of this year (4 May to 2 August 2026), with web orders counted as receipts alongside store receipts, because the request asks for web included. Net sales before returns divided by receipts (a web order is one receipt, counted on its dispatch day).",
         "leaves_out": "Staff purchases, store 999 and test articles (the other ATV rules still apply).",
         "docs": ["Team notes, 'explicitly asks' rule", "Metric dictionary, 'Transactions, members and campaigns' (ATV is a store measure by default)"],
         "result_note": "One number."},
        naive=[Naive("override", "stores_only_default", sql(False), "Leaves the web orders out (the company default) although the request asks for them. Web orders are larger than store receipts, so the figure is too low.")])


# ---------------------------------------------------------------------------
# Pattern 8: members
# ---------------------------------------------------------------------------

@question("M1")
def m1() -> Question:
    """Active members by tier at the end of P8 last year (21 December 2025), tier as it was on that date."""
    as_of = "2025-12-21"

    def sql(count_expr: str, tier_join: str) -> str:
        return f"""WITH active AS (
    SELECT f.member_key, m.member_id
    FROM fact_sales_line f JOIN dim_member m ON m.member_key = f.member_key
    WHERE f.sale_date > DATE '{as_of}' - 364 AND f.sale_date <= DATE '{as_of}'
)
SELECT t.tier, {count_expr} AS active_members
FROM (SELECT DISTINCT member_id, member_key FROM active) a
{tier_join}
GROUP BY 1 ORDER BY 1;"""

    reference = f"""WITH active AS (
    SELECT DISTINCT m.member_id
    FROM fact_sales_line f JOIN dim_member m ON m.member_key = f.member_key
    WHERE f.sale_date > DATE '{as_of}' - 364 AND f.sale_date <= DATE '{as_of}'
)
SELECT cur.tier, COUNT(*) AS active_members
FROM active a JOIN dim_member cur ON cur.member_id = a.member_id AND DATE '{as_of}' BETWEEN cur.valid_from AND cur.valid_to
GROUP BY 1 ORDER BY 1;"""
    in_period = f"""SELECT cur.tier, COUNT(*) AS active_members
FROM (SELECT DISTINCT m.member_id FROM fact_sales_line f JOIN dim_member m ON m.member_key = f.member_key
      JOIN dim_date d ON d.calendar_date = f.sale_date WHERE d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 8) a
JOIN dim_member cur ON cur.member_id = a.member_id AND DATE '{as_of}' BETWEEN cur.valid_from AND cur.valid_to
GROUP BY 1 ORDER BY 1;"""
    fan_out = f"""SELECT m.tier, COUNT(DISTINCT f.member_key) AS active_members
FROM fact_sales_line f JOIN dim_member m ON m.member_key = f.member_key
WHERE f.sale_date > DATE '{as_of}' - 364 AND f.sale_date <= DATE '{as_of}'
GROUP BY 1 ORDER BY 1;"""

    def pandas_fn(world):
        s = world.sales
        keymap = world.dim_member.set_index("member_key").member_id
        window = s[(s.sale_date > pd.Timestamp(as_of) - pd.Timedelta(days=364)) & (s.sale_date <= pd.Timestamp(as_of)) & s.member_key.notna()]
        members = set(window.member_key.map(keymap).astype("int64"))
        versions = world.dim_member
        at_date = versions[(versions.valid_from <= pd.Timestamp(as_of)) & (versions.valid_to >= pd.Timestamp(as_of)) & versions.member_id.isin(members)]
        out = at_date.groupby("tier").member_id.nunique().rename("active_members")
        return out.reset_index()

    return Question(
        "M1", 8, [col("tier", "dimension", "text"), col("active_members", "measure", "count")], reference, pandas_fn,
        {"counts": "Members who bought anything (any channel) in the 52 fiscal weeks ending with the week that ends on Sunday 21 December 2025 (the end of period 8 last year), counted once each by loyalty number, split by the tier each had on that date.",
         "leaves_out": "Anyone with no purchase in those 52 weeks, whatever their tier.",
         "docs": ["Metric dictionary, 'Transactions, members and campaigns' (active member)", "Data quality register, 'dim_member gets a new version when a member's tier, home store or marketing consent changes'"],
         "result_note": "Three rows: Basic, Silver, Gold."},
        naive=[Naive("fan_out", "count_member_versions", fan_out, "Counts member versions (member_key) instead of members, and uses the tier on the day of each purchase. A member who changed tier or store during the year is counted more than once."),
               Naive("company_definition", "bought_in_the_period_only", in_period, "Counts only members who bought during period 8 itself instead of in the 52 weeks to the end of it.")])


@question("M2")
def m2() -> Question:
    """How many customers do we have in Tampere? Two accepted readings."""
    tampere = "SELECT store_id FROM dim_store WHERE city = 'Tampere' AND store_id < 900 AND is_current"
    cols = [col("customers", "measure", "count")]
    homed = f"""SELECT COUNT(DISTINCT m.member_id) AS customers FROM dim_member m
WHERE m.is_current AND m.home_store_id IN ({tampere});"""
    shopped = f"""SELECT COUNT(DISTINCT m.member_id) AS customers
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_member m ON m.member_key = f.member_key
WHERE s.store_id IN ({tampere}) AND f.sale_date > DATE '2026-10-04' - 364 AND f.sale_date <= DATE '2026-10-04';"""
    fan_out = f"""SELECT COUNT(*) AS customers FROM dim_member m WHERE m.home_store_id IN ({tampere});"""
    tampere_ids = {row[0] for row in cfg.STORES if row[2] == "Tampere"}

    def homed_fn(world):
        current = world.dim_member[world.dim_member.is_current]
        return pd.DataFrame({"customers": [current[current.home_store_id.isin(tampere_ids)].member_id.nunique()]})

    def shopped_fn(world):
        s = world.sales
        window = s[s.store_id.isin(tampere_ids) & (s.sale_date > pd.Timestamp("2026-10-04") - pd.Timedelta(days=364)) & s.member_key.notna()]
        keymap = world.dim_member.set_index("member_key").member_id
        return pd.DataFrame({"customers": [window.member_key.map(keymap).nunique()]})

    return Question(
        "M2", 8, cols, homed, homed_fn,
        {"counts": "The request does not say what a customer is, and the dictionary does not define it. Two readings are accepted if the answer says which it used. Reading 1: loyalty members whose home store is one of the four Tampere stores (Hervanta, Lielahti, Kaleva, Lamminpää), counted once each by loyalty number. Reading 2: members who bought at one of those stores in the 52 weeks to 4 October 2026.",
         "leaves_out": "Reading 1 leaves out members who live in Tampere but have another home store; reading 2 leaves out members who have not shopped there for a year. Non-members cannot be counted at all.",
         "docs": ["Metric dictionary, 'Transactions, members and campaigns' (new member, active member) and 'Hierarchies and stores' (store counts)", "Data quality register, 'Count members by distinct member_id'"],
         "result_note": "One number per reading."},
        naive=[Naive("fan_out", "count_member_versions", fan_out, "Counts rows in the member table whose home store is in Tampere, including every earlier version of every member, so people who changed tier or store are counted twice or more.")],
        interpretations=[
            Interpretation("home_store", "Members whose home store is in Tampere (all enrolled members)", homed, homed_fn, cols,
                           [["home store", "home-store", "enrolled", "registered", "member"], ["tampere"]],
                           "I took customers to mean loyalty members whose home store is in Tampere.", "I counted customers in Tampere."),
            Interpretation("shopped_52_weeks", "Members who bought at a Tampere store in the last 52 weeks", shopped, shopped_fn, cols,
                           [["bought", "shopped", "purchase", "purchased", "transaction", "active"], ["52", "year", "twelve months", "12 months"]],
                           "I counted members who bought at a Tampere store in the last 52 weeks.", "I counted customers in Tampere.")])


def member_share_web_sql(periods: tuple, repair: bool) -> str:
    member_expr = "COALESCE(f.member_key, o.member_key)" if repair else "f.member_key"
    return f"""WITH {WEB_DISPATCH}
SELECT d.fiscal_period,
       ROUND(100.0 * SUM(CASE WHEN {member_expr} IS NOT NULL THEN f.net_amount ELSE 0 END) / SUM(f.net_amount), 2) AS member_share_pct
FROM fact_sales_line f
JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
JOIN fact_web_order o ON o.web_order_id = f.receipt_id JOIN web_dispatch w ON w.web_order_id = f.receipt_id
JOIN dim_date d ON d.calendar_date = w.dispatch_date
WHERE s.store_id = 900 AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period BETWEEN {periods[0]} AND {periods[1]}
GROUP BY 1 ORDER BY 1;"""


def member_share_web_fn(periods: tuple, repair: bool):
    def fn(world):
        s = world.sales[world.sales.is_web & (world.sales.category_was != cfg.TEST_CATEGORY) & world.sales.business_date.notna()].copy()
        s = world.fiscal(s, "business_date")
        s = s[(s.fy == "FY2025/26") & s.period.between(*periods)]
        if repair:
            order_member = world.web.set_index("web_order_id").member_key
            has_member = s.member_key.notna() | s.receipt_id.map(order_member).notna()
        else:
            has_member = s.member_key.notna()
        total = s.groupby("period").net_c.sum()
        members = s[has_member].groupby("period").net_c.sum().reindex(total.index).fillna(0)
        out = (100.0 * members / total).rename("member_share_pct")
        out.index.name = "fiscal_period"
        return out.reset_index()
    return fn


@question("U2")
def u2() -> Question:
    return Question(
        "U2", 8, [col("fiscal_period", "dimension", "count"), col("member_share_pct", "measure", "pct")],
        member_share_web_sql((9, 11), repair=True), member_share_web_fn((9, 11), repair=True),
        {"counts": "The share of web net sales (before returns, on the dispatch date) that went to loyalty members, for periods 9 to 11 of last year (22 December 2025 to 22 March 2026). A logged-in web order is a member order; a guest order is not.",
         "leaves_out": "Cancelled and unshipped orders and web test orders. Guest orders count in the total but not as member sales.",
         "docs": ["Metric dictionary, 'Transactions, members and campaigns' (member share of sales)", "Data quality register, 'Guest web orders have no member key. Logged-in orders carry the member's key'"],
         "result_note": "Three rows. In the published data logged-in orders ordered between 9 February and 1 March 2026 lost the member key on their sales lines, so a share built from the sales lines alone dips in periods 10 and 11."},
        undocumented={"incident": "INC-2", "published_sql": member_share_web_sql((9, 11), repair=False),
                      "published_pandas_fn": member_share_web_fn((9, 11), repair=False),
                      "what": "For three weeks (9 February to 1 March 2026) more than half of the logged-in web orders lost their member key on the sales lines; the order records still carry it.",
                      "keywords": [["member"], ["missing", "null", "lost", "drop", "dip", "gap", "orphan", "not linked", "unlinked", "blank", "no member", "understat", "lower than"], ["feb", "march", "mar ", "p10", "p11", "period 10", "period 11", "week"]],
                      "example_pass": "Member share of web sales is understated for P10 and P11: many logged-in web orders in Feb to early March 2026 have a null member_key on the sales lines.",
                      "example_fail": "Member share was computed as member lines over all web lines, before returns."})


@question("G4")
def g4() -> Question:
    """Clean: how many members are on the Gold tier now."""
    sql = "SELECT COUNT(DISTINCT member_id) AS gold_members FROM dim_member WHERE is_current AND tier = 'Gold';"
    sloppy = "SELECT COUNT(DISTINCT member_id) AS gold_members FROM dim_member WHERE tier = 'Gold' AND DATE '2026-10-04' BETWEEN valid_from AND valid_to;"

    def pandas_fn(world):
        m = world.dim_member
        current = m[(m.valid_from <= pd.Timestamp("2026-10-04")) & (m.valid_to >= pd.Timestamp("2026-10-04"))]
        return pd.DataFrame({"gold_members": [int(current[current.tier == "Gold"].member_id.nunique())]})

    return Question(
        "G4", 8, [col("gold_members", "measure", "count")], sql, pandas_fn,
        {"counts": "Loyalty members whose current tier is Gold, counted once each by loyalty number.",
         "leaves_out": "Nothing: every member has exactly one current tier.", "docs": ["Schema comments (dim_member.tier, is_current)"],
         "result_note": "One number."},
        invariance_sql=[sloppy])
