"""The 40 dev requests: past requests with the analyst's accepted query and a one-line note.

These are the library builder's training material, in the way a real team's ticket history is. Each query is written
the way an analyst at Tuomimetsa would write it: correct on the company definitions, pasted from earlier queries
where that is how teams work. The queries cover 10 of the 14 patterns (config.DEV_PATTERNS_COVERED); patterns
9, 10, 13 and 14 are deliberately absent so the test set can hold requests the history has no template for.

Scope discipline: the history must not touch the undocumented incidents. Each request records the
period it covers, the regions and what it uses, and validate_world.py checks these against the incident windows and
also re-runs every query on a repaired copy of the warehouse to prove the answers are unaffected.

`facts_used` names the world facts a reader can learn from the query and note (internal provenance).
"""
from __future__ import annotations

from datetime import date

# ---------------------------------------------------------------------------
# Shared SQL pieces (what an analyst would paste from an earlier query)
# ---------------------------------------------------------------------------

WEB_DISPATCH = """web_dispatch AS (
    SELECT web_order_id,
           CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
)"""

NET_LINES = """net_lines AS (
    -- sales: stores on the sale date, web on the Helsinki dispatch date
    SELECT COALESCE(w.dispatch_date, f.sale_date) AS business_date, s.store_id, p.sku,
           f.net_amount AS net_sales, f.standard_cost AS cost
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
    UNION ALL
    -- returns reduce net sales on the return date
    SELECT r.return_date, s.store_id, p.sku, -r.refund_net, -r.standard_cost_returned
    FROM fact_return_line r
    JOIN dim_store s   ON s.store_key = r.store_key
    JOIN dim_product p ON p.product_key = r.product_key
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
)"""

NET_LINES_WAS = """net_lines AS (
    -- as-was: region and format are the store version valid on the transaction date
    SELECT COALESCE(w.dispatch_date, f.sale_date) AS business_date, s.region, s.format, f.net_amount AS net_sales
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
    UNION ALL
    SELECT r.return_date, s.region, s.format, -r.refund_net
    FROM fact_return_line r
    JOIN dim_store s   ON s.store_key = r.store_key
    JOIN dim_product p ON p.product_key = r.product_key
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
)"""

NET_LINES_STORES = """net_lines AS (
    -- physical stores only, so no web dispatch join is needed
    SELECT f.sale_date AS business_date, s.store_id, f.net_amount AS net_sales
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    WHERE s.store_id < 900 AND p.category <> 'ZZ Test'
    UNION ALL
    SELECT r.return_date, s.store_id, -r.refund_net
    FROM fact_return_line r
    JOIN dim_store s   ON s.store_key = r.store_key
    JOIN dim_product p ON p.product_key = r.product_key
    WHERE s.store_id < 900 AND p.category <> 'ZZ Test'
)"""


def lfl_store_weeks(ty: str, ly: str, week_from: int, week_to: int, period_start: str) -> str:
    """The LFL store-week list: traded in the same fiscal week in both years, open 52+ weeks before the period."""
    return f"""store_weeks AS (
    -- every store x fiscal week in the two years, flagged as trading or not (open, not closed, no refit)
    SELECT st.store_id, d.fiscal_year, d.fiscal_week,
           (st.open_date IS NULL OR st.open_date <= d.fiscal_week_start_date)
           AND (st.close_date IS NULL OR st.close_date >= d.fiscal_week_end_date)
           AND NOT EXISTS (SELECT 1 FROM ref_store_closure c
                           WHERE c.store_id = st.store_id
                             AND c.closure_start_date <= d.fiscal_week_end_date
                             AND c.closure_end_date >= d.fiscal_week_start_date) AS trading
    FROM dim_store st
    CROSS JOIN (SELECT DISTINCT fiscal_year, fiscal_week, fiscal_week_start_date, fiscal_week_end_date
                FROM dim_date
                WHERE fiscal_year IN ('{ly}', '{ty}') AND fiscal_week BETWEEN {week_from} AND {week_to}) d
    WHERE st.is_current AND st.store_id < 900
),
lfl_store_weeks AS (
    SELECT ty.store_id, ty.fiscal_week
    FROM store_weeks ty
    JOIN store_weeks ly ON ly.store_id = ty.store_id AND ly.fiscal_week = ty.fiscal_week AND ly.fiscal_year = '{ly}'
    JOIN dim_store st   ON st.store_id = ty.store_id AND st.is_current
    WHERE ty.fiscal_year = '{ty}' AND ty.trading AND ly.trading
      AND (st.open_date IS NULL OR st.open_date <= DATE '{period_start}' - 364)   -- open 52+ weeks before the period
)"""


def d(text: str) -> date:
    return date.fromisoformat(text)


# ---------------------------------------------------------------------------
# The 40 requests
# ---------------------------------------------------------------------------

DEV_REQUESTS = []


def add(request_id, received, requester, department, pattern, request_text, sql, note, facts_used, period, regions=None, uses=()):
    DEV_REQUESTS.append({
        "id": request_id, "received": d(received), "requester": requester, "department": department, "pattern": pattern,
        "request_text": request_text, "sql": sql.strip() + "\n", "note": note, "facts_used": list(facts_used),
        "period_start": d(period[0]), "period_end": d(period[1]), "regions": regions, "uses": set(uses),
    })


# ---- Pattern 1: weekly net sales by region / format vs last year ------------------------------------------------

add("REQ-D01", "2025-12-02", "Marjatta Salonen", "Finance (FP&A)", 1,
    "Hi, can I get weekly net sales by region for P6, this year against last year? For the board pack, thanks.",
    f"""
WITH {WEB_DISPATCH},
{NET_LINES},
weekly AS (
    SELECT d.fiscal_year, d.fiscal_week, cs.region, SUM(n.net_sales) AS net_sales
    FROM net_lines n
    JOIN dim_date d  ON d.calendar_date = n.business_date
    JOIN dim_store cs ON cs.store_id = n.store_id AND cs.is_current
    WHERE d.fiscal_period = 6 AND d.fiscal_year IN ('FY2025/26', 'FY2024/25')
    GROUP BY 1, 2, 3
)
SELECT ty.fiscal_week, ty.region, ty.net_sales AS this_year, ly.net_sales AS last_year,
       ROUND(100.0 * (ty.net_sales / ly.net_sales - 1), 1) AS growth_pct
FROM weekly ty
JOIN weekly ly ON ly.fiscal_week = ty.fiscal_week AND ly.region = ty.region AND ly.fiscal_year = 'FY2024/25'
WHERE ty.fiscal_year = 'FY2025/26'
ORDER BY ty.fiscal_week, ty.region;
""",
    "As-is regions (current hierarchy restated), Online shown as its own line, weeks lined up by fiscal week number.",
    ["DEF-NET-SALES", "DEF-WEB-RECOGNITION", "DEF-HIERARCHY-ASIS", "CAL-COMPARE", "DEF-NET-SALES-SCOPE"],
    ("2025-09-29", "2025-11-02"), uses=("store_sales", "web"))

add("REQ-D02", "2026-09-01", "Mika Hietala", "Store operations", 1,
    "Sales by store format for the last four weeks vs same time last year please",
    f"""
WITH {WEB_DISPATCH},
{NET_LINES},
weekly AS (
    SELECT d.fiscal_year, d.fiscal_week, cs.format, SUM(n.net_sales) AS net_sales
    FROM net_lines n
    JOIN dim_date d   ON d.calendar_date = n.business_date
    JOIN dim_store cs ON cs.store_id = n.store_id AND cs.is_current
    WHERE d.fiscal_period = 4 AND d.fiscal_year IN ('FY2026/27', 'FY2025/26')
    GROUP BY 1, 2, 3
)
SELECT ty.fiscal_week, ty.format, ty.net_sales AS this_year, ly.net_sales AS last_year,
       ROUND(100.0 * (ty.net_sales / ly.net_sales - 1), 1) AS growth_pct
FROM weekly ty
JOIN weekly ly ON ly.fiscal_week = ty.fiscal_week AND ly.format = ty.format AND ly.fiscal_year = 'FY2025/26'
WHERE ty.fiscal_year = 'FY2026/27'
ORDER BY ty.fiscal_week, ty.format;
""",
    "'Last four weeks' read as the last completed period, FY2026/27 P4, compared with P4 last year by week number; format includes Web.",
    ["CAL-RELATIVE", "CAL-COMPARE", "DEF-NET-SALES", "DEF-WEB-RECOGNITION"],
    ("2026-08-03", "2026-08-30"), uses=("store_sales", "web"))

add("REQ-D03", "2026-04-14", "Antti Rautiainen", "Finance (FP&A)", 1,
    "Total company net sales per week for Q3 with last year alongside. Need it today if possible.",
    f"""
WITH {WEB_DISPATCH},
{NET_LINES},
weekly AS (
    SELECT d.fiscal_year, d.fiscal_week, SUM(n.net_sales) AS net_sales
    FROM net_lines n
    JOIN dim_date d ON d.calendar_date = n.business_date
    WHERE d.fiscal_quarter = 3 AND d.fiscal_year IN ('FY2025/26', 'FY2024/25')
    GROUP BY 1, 2
)
SELECT ty.fiscal_week, ty.net_sales AS this_year, ly.net_sales AS last_year,
       ROUND(100.0 * (ty.net_sales / ly.net_sales - 1), 1) AS growth_pct
FROM weekly ty
JOIN weekly ly ON ly.fiscal_week = ty.fiscal_week AND ly.fiscal_year = 'FY2024/25'
WHERE ty.fiscal_year = 'FY2025/26'
ORDER BY ty.fiscal_week;
""",
    "Q3 = P7-P9 = weeks 27-39; total company so web is in, stores 999 and ZZ Test out.",
    ["CAL-PERIODS", "CAL-COMPARE", "DEF-NET-SALES", "DEF-NET-SALES-SCOPE", "DEF-WEB-RECOGNITION"],
    ("2025-10-27", "2026-01-25"), uses=("store_sales", "web"))

add("REQ-D04", "2026-05-12", "Marjatta Salonen", "Finance (FP&A)", 1,
    "Net sales by region and period for the second half of last year vs the year before.",
    f"""
WITH {WEB_DISPATCH},
{NET_LINES},
by_period AS (
    SELECT d.fiscal_year, d.fiscal_period, cs.region, SUM(n.net_sales) AS net_sales
    FROM net_lines n
    JOIN dim_date d   ON d.calendar_date = n.business_date
    JOIN dim_store cs ON cs.store_id = n.store_id AND cs.is_current
    WHERE d.fiscal_period BETWEEN 7 AND 12
      AND d.fiscal_week <= 52                       -- week 53 has no comparator, so it is left out of both years
      AND d.fiscal_year IN ('FY2025/26', 'FY2024/25')
    GROUP BY 1, 2, 3
)
SELECT ty.fiscal_period, ty.region, ty.net_sales AS fy2526, ly.net_sales AS fy2425,
       ROUND(100.0 * (ty.net_sales / ly.net_sales - 1), 1) AS growth_pct
FROM by_period ty
JOIN by_period ly ON ly.fiscal_period = ty.fiscal_period AND ly.region = ty.region AND ly.fiscal_year = 'FY2024/25'
WHERE ty.fiscal_year = 'FY2025/26'
ORDER BY ty.fiscal_period, ty.region;
""",
    "'Last year' = FY2025/26, 'second half' = P7-P12; week 53 dropped so P12 compares like with like; regions as-is.",
    ["CAL-WEEK53", "CAL-COMPARE", "DEF-HIERARCHY-ASIS", "DEF-NET-SALES"],
    ("2025-10-27", "2026-04-26"), uses=("store_sales", "web"))

add("REQ-D05", "2025-06-18", "Leena Vuorinen", "Store operations", 1,
    "Regional net sales by quarter for last year, but with the regions as they were at the time. We need to match the old reports.",
    f"""
WITH {WEB_DISPATCH},
{NET_LINES_WAS},
by_quarter AS (
    SELECT d.fiscal_quarter, n.region, SUM(n.net_sales) AS net_sales
    FROM net_lines n
    JOIN dim_date d ON d.calendar_date = n.business_date
    WHERE d.fiscal_year = 'FY2024/25'
    GROUP BY 1, 2
)
SELECT fiscal_quarter, region, net_sales
FROM by_quarter
ORDER BY fiscal_quarter, region;
""",
    "As-was requested, so region is taken from the store version valid on each transaction date (four regions plus Online in FY2024/25).",
    ["DEF-HIERARCHY-ASIS", "REG-SCD-KEYS", "REG-REGION-REORG"],
    ("2024-04-29", "2025-04-27"), uses=("store_sales", "web"))

# ---- Pattern 2: like-for-like growth -----------------------------------------------------------------------------

add("REQ-D06", "2025-08-20", "Antti Rautiainen", "Finance (FP&A)", 2,
    "LFL growth for Q1 please, stores only",
    f"""
WITH {lfl_store_weeks('FY2025/26', 'FY2024/25', 1, 13, '2025-04-28')},
{WEB_DISPATCH},
{NET_LINES},
lfl_sales AS (
    SELECT d.fiscal_year, SUM(n.net_sales) AS net_sales
    FROM net_lines n
    JOIN dim_date d ON d.calendar_date = n.business_date
    JOIN lfl_store_weeks l ON l.store_id = n.store_id AND l.fiscal_week = d.fiscal_week
    WHERE d.fiscal_year IN ('FY2025/26', 'FY2024/25') AND d.fiscal_week BETWEEN 1 AND 13
    GROUP BY 1
)
SELECT ty.net_sales AS this_year, ly.net_sales AS last_year,
       ROUND(100.0 * (ty.net_sales / ly.net_sales - 1), 2) AS lfl_growth_pct
FROM lfl_sales ty, lfl_sales ly
WHERE ty.fiscal_year = 'FY2025/26' AND ly.fiscal_year = 'FY2024/25';
""",
    "Company LFL rule: stores open 52+ weeks before the period and trading in the same week both years; Tammisto's FY2024/25 refit weeks drop out.",
    ["DEF-LFL-BASIS", "DEF-LFL-OPEN", "DEF-LFL-BOTH-YEARS", "DEF-LFL-REFIT", "REG-REFITS"],
    ("2025-04-28", "2025-07-27"), uses=("store_sales",))

add("REQ-D07", "2026-08-11", "Marjatta Salonen", "Finance (FP&A)", 2,
    "LFL for P3 this year. I know Kuopio was shut for the refit so please do it the usual way.",
    f"""
WITH {lfl_store_weeks('FY2026/27', 'FY2025/26', 9, 13, '2026-06-29')},
{WEB_DISPATCH},
{NET_LINES},
lfl_sales AS (
    SELECT d.fiscal_year, SUM(n.net_sales) AS net_sales
    FROM net_lines n
    JOIN dim_date d ON d.calendar_date = n.business_date
    JOIN lfl_store_weeks l ON l.store_id = n.store_id AND l.fiscal_week = d.fiscal_week
    WHERE d.fiscal_year IN ('FY2026/27', 'FY2025/26') AND d.fiscal_week BETWEEN 9 AND 13
    GROUP BY 1
)
SELECT ty.net_sales AS this_year, ly.net_sales AS last_year,
       ROUND(100.0 * (ty.net_sales / ly.net_sales - 1), 2) AS lfl_growth_pct
FROM lfl_sales ty, lfl_sales ly
WHERE ty.fiscal_year = 'FY2026/27' AND ly.fiscal_year = 'FY2025/26';
""",
    "P3 = weeks 9-13; Kuopio is in only for week 13 and Savonlinna is out (closed), both from the store-week list.",
    ["DEF-LFL-BASIS", "DEF-LFL-REFIT", "DEF-LFL-BOTH-YEARS", "TEAM-LFL-EDGE", "REG-STORE-EVENTS"],
    ("2026-06-29", "2026-08-02"), uses=("store_sales",))

add("REQ-D08", "2026-05-19", "Antti Rautiainen", "Finance (FP&A)", 2,
    "LFL by region for the back half of last year please (as-is regions are fine)",
    f"""
WITH {lfl_store_weeks('FY2025/26', 'FY2024/25', 27, 52, '2025-10-27')},
{WEB_DISPATCH},
{NET_LINES},
lfl_sales AS (
    SELECT d.fiscal_year, cs.region, SUM(n.net_sales) AS net_sales
    FROM net_lines n
    JOIN dim_date d   ON d.calendar_date = n.business_date
    JOIN dim_store cs ON cs.store_id = n.store_id AND cs.is_current
    JOIN lfl_store_weeks l ON l.store_id = n.store_id AND l.fiscal_week = d.fiscal_week
    WHERE d.fiscal_year IN ('FY2025/26', 'FY2024/25') AND d.fiscal_week BETWEEN 27 AND 52   -- week 53 is never LFL
    GROUP BY 1, 2
)
SELECT ty.region, ty.net_sales AS this_year, ly.net_sales AS last_year,
       ROUND(100.0 * (ty.net_sales / ly.net_sales - 1), 2) AS lfl_growth_pct
FROM lfl_sales ty
JOIN lfl_sales ly ON ly.region = ty.region AND ly.fiscal_year = 'FY2024/25'
WHERE ty.fiscal_year = 'FY2025/26'
ORDER BY ty.region;
""",
    "Weeks 27-52 (back half, week 53 out); Lohja is not yet in the base, and the closed store contributes only the weeks it traded.",
    ["DEF-LFL-WEEK53", "DEF-LFL-OPEN", "DEF-LFL-BOTH-YEARS", "DEF-HIERARCHY-ASIS", "TEAM-LFL-EDGE"],
    ("2025-10-27", "2026-04-26"), uses=("store_sales",))

add("REQ-D09", "2026-09-08", "Marjatta Salonen", "Finance (FP&A)", 2,
    "YTD LFL as of the end of P4, please.",
    f"""
WITH {lfl_store_weeks('FY2026/27', 'FY2025/26', 1, 17, '2026-05-04')},
{WEB_DISPATCH},
{NET_LINES},
lfl_sales AS (
    SELECT d.fiscal_year, SUM(n.net_sales) AS net_sales
    FROM net_lines n
    JOIN dim_date d ON d.calendar_date = n.business_date
    JOIN lfl_store_weeks l ON l.store_id = n.store_id AND l.fiscal_week = d.fiscal_week
    WHERE d.fiscal_year IN ('FY2026/27', 'FY2025/26') AND d.fiscal_week BETWEEN 1 AND 17
    GROUP BY 1
)
SELECT ty.net_sales AS this_year, ly.net_sales AS last_year,
       ROUND(100.0 * (ty.net_sales / ly.net_sales - 1), 2) AS lfl_growth_pct
FROM lfl_sales ty, lfl_sales ly
WHERE ty.fiscal_year = 'FY2026/27' AND ly.fiscal_year = 'FY2025/26';
""",
    "YTD to end of P4 = weeks 1-17 of FY2026/27 against weeks 1-17 of FY2025/26; refit weeks and the closed store drop out via the store-week list.",
    ["CAL-RELATIVE", "DEF-LFL-BASIS", "DEF-LFL-REFIT", "DEF-LFL-OPEN"],
    ("2026-05-04", "2026-08-30"), uses=("store_sales",))

# ---- Pattern 3: category sales and gross margin ------------------------------------------------------------------

add("REQ-D10", "2026-07-07", "Hanna Kivistö", "Commercial (category management)", 3,
    "Net sales and gross margin % by category for P2",
    f"""
WITH {WEB_DISPATCH},
{NET_LINES},
by_category AS (
    SELECT cp.category, SUM(n.net_sales) AS net_sales, SUM(n.net_sales - n.cost) AS gross_margin
    FROM net_lines n
    JOIN dim_date d     ON d.calendar_date = n.business_date
    JOIN dim_product cp ON cp.sku = n.sku AND cp.is_current
    WHERE d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 2
    GROUP BY 1
)
SELECT category, net_sales, gross_margin, ROUND(100.0 * gross_margin / net_sales, 1) AS gross_margin_pct
FROM by_category
ORDER BY net_sales DESC;
""",
    "Current fiscal year's P2 (FY2026/27); margin after returns with returned units credited at standard cost; categories as-is.",
    ["DEF-GROSS-MARGIN", "DEF-HIERARCHY-ASIS", "DEF-NET-SALES", "CAL-RELATIVE"],
    ("2026-06-01", "2026-06-28"), uses=("store_sales", "web"))

add("REQ-D11", "2025-07-02", "Pekka Lindroos", "Commercial (category management)", 3,
    "Garden and Electrical gross margin by period for last year",
    f"""
WITH {WEB_DISPATCH},
{NET_LINES},
by_period AS (
    SELECT d.fiscal_period, cp.category, SUM(n.net_sales) AS net_sales, SUM(n.net_sales - n.cost) AS gross_margin
    FROM net_lines n
    JOIN dim_date d     ON d.calendar_date = n.business_date
    JOIN dim_product cp ON cp.sku = n.sku AND cp.is_current
    WHERE d.fiscal_year = 'FY2024/25' AND cp.category IN ('Garden', 'Electrical')
    GROUP BY 1, 2
)
SELECT fiscal_period, category, net_sales, ROUND(100.0 * gross_margin / net_sales, 1) AS gross_margin_pct
FROM by_period
ORDER BY fiscal_period, category;
""",
    "Categories as-is: outdoor lighting sits in Electrical for the whole of FY2024/25 even though it was Garden then.",
    ["DEF-HIERARCHY-ASIS", "REG-OUTDOOR-LIGHTING", "DEF-GROSS-MARGIN"],
    ("2024-04-29", "2025-04-27"), uses=("store_sales", "web"))

add("REQ-D12", "2026-06-23", "Hanna Kivistö", "Commercial (category management)", 3,
    "Top 10 subcategories by gross margin for Q4",
    f"""
WITH {WEB_DISPATCH},
{NET_LINES},
by_subcategory AS (
    SELECT cp.category, cp.subcategory, SUM(n.net_sales) AS net_sales, SUM(n.net_sales - n.cost) AS gross_margin
    FROM net_lines n
    JOIN dim_date d     ON d.calendar_date = n.business_date
    JOIN dim_product cp ON cp.sku = n.sku AND cp.is_current
    WHERE d.fiscal_year = 'FY2025/26' AND d.fiscal_quarter = 4
    GROUP BY 1, 2
)
SELECT category, subcategory, net_sales, gross_margin, ROUND(100.0 * gross_margin / net_sales, 1) AS gross_margin_pct
FROM by_subcategory
ORDER BY gross_margin DESC
LIMIT 10;
""",
    "Q4 of last year = P10-P12 FY2025/26, including week 53 (no comparison asked, so nothing dropped).",
    ["CAL-PERIODS", "CAL-WEEK53", "DEF-GROSS-MARGIN", "DEF-HIERARCHY-ASIS"],
    ("2026-02-23", "2026-05-03"), uses=("store_sales", "web"))

add("REQ-D13", "2025-11-12", "Pekka Lindroos", "Commercial (category management)", 3,
    "Paint & Decorating: own label vs brands, sales and margin, first half of FY24/25",
    f"""
WITH {WEB_DISPATCH},
{NET_LINES},
by_label AS (
    SELECT cp.own_label_flag, SUM(n.net_sales) AS net_sales, SUM(n.net_sales - n.cost) AS gross_margin
    FROM net_lines n
    JOIN dim_date d     ON d.calendar_date = n.business_date
    JOIN dim_product cp ON cp.sku = n.sku AND cp.is_current
    WHERE d.fiscal_year = 'FY2024/25' AND d.fiscal_period BETWEEN 1 AND 6
      AND cp.category = 'Paint & Decorating'
    GROUP BY 1
)
SELECT CASE WHEN own_label_flag THEN 'Own label' ELSE 'Brands' END AS label_type,
       net_sales, gross_margin, ROUND(100.0 * gross_margin / net_sales, 1) AS gross_margin_pct
FROM by_label
ORDER BY label_type;
""",
    "First half = P1-P6; category and own-label flag from the current product version.",
    ["CAL-PERIODS", "DEF-GROSS-MARGIN", "DEF-HIERARCHY-ASIS"],
    ("2024-04-29", "2024-10-27"), uses=("store_sales", "web"))

# ---- Pattern 4: return rate by category --------------------------------------------------------------------------

RETURN_COHORT_BASE = """
    FROM fact_sales_line f
    JOIN dim_store s     ON s.store_key = f.store_key
    JOIN dim_product p   ON p.product_key = f.product_key
    JOIN dim_product cp  ON cp.sku = p.sku AND cp.is_current
    JOIN dim_date d      ON d.calendar_date = f.sale_date
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'"""

add("REQ-D14", "2026-03-10", "Hanna Kivistö", "Commercial (category management)", 4,
    "Return rate by category for goods sold in the first four periods of last year.",
    f"""
WITH sold AS (
    SELECT cp.category, SUM(f.net_amount) AS sold_net
    {RETURN_COHORT_BASE}
      AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period BETWEEN 1 AND 4
    GROUP BY 1
),
returned AS (
    -- cohort by the original sale, whenever the return happened
    SELECT cp.category, SUM(r.refund_net) AS returned_net
    FROM fact_return_line r
    JOIN fact_sales_line f ON f.sales_line_id = r.sales_line_id
    JOIN dim_store s     ON s.store_key = f.store_key
    JOIN dim_product p   ON p.product_key = f.product_key
    JOIN dim_product cp  ON cp.sku = p.sku AND cp.is_current
    JOIN dim_date d      ON d.calendar_date = f.sale_date
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
      AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period BETWEEN 1 AND 4
    GROUP BY 1
)
SELECT sold.category, sold.sold_net, COALESCE(returned.returned_net, 0) AS returned_net,
       ROUND(100.0 * COALESCE(returned.returned_net, 0) / sold.sold_net, 2) AS return_rate_pct
FROM sold LEFT JOIN returned USING (category)
ORDER BY return_rate_pct DESC;
""",
    "Sale-week cohort: refunds are matched to the week the item was sold, not the week it came back; cohort is old enough to be complete.",
    ["DEF-RETURN-RATE", "REG-RETURN-LAG", "DEF-HIERARCHY-ASIS"],
    ("2025-04-28", "2025-08-31"), uses=("store_sales", "web"))

add("REQ-D15", "2025-09-24", "Pekka Lindroos", "Commercial (category management)", 4,
    "Furniture return rate by subcategory, FY24/25 sales",
    f"""
WITH sold AS (
    SELECT cp.subcategory, SUM(f.net_amount) AS sold_net
    {RETURN_COHORT_BASE}
      AND d.fiscal_year = 'FY2024/25' AND cp.category = 'Furniture'
    GROUP BY 1
),
returned AS (
    SELECT cp.subcategory, SUM(r.refund_net) AS returned_net
    FROM fact_return_line r
    JOIN fact_sales_line f ON f.sales_line_id = r.sales_line_id
    JOIN dim_store s     ON s.store_key = f.store_key
    JOIN dim_product p   ON p.product_key = f.product_key
    JOIN dim_product cp  ON cp.sku = p.sku AND cp.is_current
    JOIN dim_date d      ON d.calendar_date = f.sale_date
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
      AND d.fiscal_year = 'FY2024/25' AND cp.category = 'Furniture'
    GROUP BY 1
)
SELECT sold.subcategory, sold.sold_net, COALESCE(returned.returned_net, 0) AS returned_net,
       ROUND(100.0 * COALESCE(returned.returned_net, 0) / sold.sold_net, 2) AS return_rate_pct
FROM sold LEFT JOIN returned USING (subcategory)
ORDER BY sold.subcategory;
""",
    "Cohort = FY2024/25 sales, all returns attributed back to the sale; Furniture as-is.",
    ["DEF-RETURN-RATE", "DEF-HIERARCHY-ASIS"],
    ("2024-04-29", "2025-04-27"), uses=("store_sales", "web"))

add("REQ-D16", "2026-01-21", "Hanna Kivistö", "Commercial (category management)", 4,
    "Return rate web vs stores by category for Q1 sales last year. Web feels worse.",
    f"""
WITH lines AS (
    SELECT f.sales_line_id, cp.category,
           CASE WHEN s.store_id = 900 THEN 'Web' ELSE 'Stores' END AS channel_group,
           f.net_amount
    FROM fact_sales_line f
    JOIN dim_store s     ON s.store_key = f.store_key
    JOIN dim_product p   ON p.product_key = f.product_key
    JOIN dim_product cp  ON cp.sku = p.sku AND cp.is_current
    JOIN dim_date d      ON d.calendar_date = f.sale_date
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
      AND d.fiscal_year = 'FY2025/26' AND d.fiscal_quarter = 1
),
refunds AS (
    SELECT sales_line_id, SUM(refund_net) AS refund_net FROM fact_return_line GROUP BY 1
)
SELECT l.category, l.channel_group, SUM(l.net_amount) AS sold_net, COALESCE(SUM(r.refund_net), 0) AS returned_net,
       ROUND(100.0 * COALESCE(SUM(r.refund_net), 0) / SUM(l.net_amount), 2) AS return_rate_pct
FROM lines l LEFT JOIN refunds r USING (sales_line_id)
GROUP BY 1, 2
ORDER BY l.category, l.channel_group;
""",
    "Web is told apart by store 900, not by channel_code; refunds follow the original line whichever location booked them.",
    ["DEF-RETURN-RATE", "REG-STORE-900", "REG-RETURN-LAG"],
    ("2025-04-28", "2025-07-27"), uses=("store_sales", "web"))

# ---- Pattern 5: web sales and orders ---------------------------------------------------------------------------

add("REQ-D17", "2025-12-03", "Tiina Mäkelä", "E-commerce", 5,
    "Daily web sales for Black Friday week please",
    f"""
WITH {WEB_DISPATCH},
{NET_LINES}
SELECT n.business_date, SUM(n.net_sales) AS web_net_sales
FROM net_lines n
WHERE n.store_id = 900
  AND n.business_date BETWEEN DATE '2025-11-24' AND DATE '2025-11-30'    -- Mon-Sun of Black Friday week 2025
GROUP BY 1
ORDER BY 1;
""",
    "Web sales on the Helsinki dispatch date (not the order date, not UTC), returns booked to the web shop on their own date.",
    ["DEF-WEB-RECOGNITION", "DEF-TIMEZONE", "REG-WEB-SALE-DATE", "REG-STORE-900"],
    ("2025-11-24", "2025-11-30"), uses=("web",))

add("REQ-D18", "2026-01-13", "Veikko Saarela", "E-commerce", 5,
    "How many web orders per week in P8? Not counting cancelled ones.",
    """
SELECT d.fiscal_week, COUNT(*) AS web_orders
FROM fact_web_order o
JOIN dim_date d ON d.calendar_date = CAST(timezone('Europe/Helsinki', o.order_ts_utc AT TIME ZONE 'UTC') AS DATE)
WHERE d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 8
  AND o.status <> 'cancelled'
GROUP BY 1
ORDER BY 1;
""",
    "Orders counted on the Helsinki order date; processing orders count, cancelled do not.",
    ["DEF-WEB-ORDER-COUNT", "DEF-WEB-CANCELLED", "DEF-TIMEZONE", "REG-CANCELLED"],
    ("2025-11-24", "2025-12-21"), uses=("web",))

add("REQ-D19", "2025-11-18", "Tiina Mäkelä", "E-commerce", 5,
    "Weekly web sales from August to the end of October 2025, I want to see the migration week too.",
    f"""
WITH {WEB_DISPATCH},
{NET_LINES}
SELECT d.fiscal_year, d.fiscal_week, MIN(d.fiscal_week_start_date) AS week_start, SUM(n.net_sales) AS web_net_sales
FROM net_lines n
JOIN dim_date d ON d.calendar_date = n.business_date
WHERE n.store_id = 900
  AND n.business_date BETWEEN DATE '2025-08-04' AND DATE '2025-11-09'      -- whole fiscal weeks, Monday to Sunday
GROUP BY 1, 2
ORDER BY 1, 2;
""",
    "Web identified by store 900 so the series runs straight through the 3 November migration (channel_code would drop out).",
    ["REG-MIGRATION", "REG-STORE-900", "DEF-WEB-RECOGNITION", "REG-LEGACY-VIEW"],
    ("2025-08-04", "2025-11-09"), uses=("web",))

add("REQ-D20", "2024-12-04", "Veikko Saarela", "E-commerce", 5,
    "Web orders by hour on Black Friday, Finnish time. The midnight deal, how big was it?",
    """
SELECT hour(timezone('Europe/Helsinki', o.order_ts_utc AT TIME ZONE 'UTC')) AS hour_helsinki,
       COUNT(*) AS web_orders
FROM fact_web_order o
WHERE CAST(timezone('Europe/Helsinki', o.order_ts_utc AT TIME ZONE 'UTC') AS DATE) = DATE '2024-11-29'
  AND o.status <> 'cancelled'
GROUP BY 1
ORDER BY 1;
""",
    "Black Friday 2024 was 29 November; timestamps are UTC so they are converted to Helsinki time before the day and hour are read.",
    ["DEF-TIMEZONE", "REG-UTC", "DEF-WEB-ORDER-COUNT"],
    ("2024-11-29", "2024-11-29"), uses=("web",))

add("REQ-D21", "2026-09-03", "Tiina Mäkelä", "E-commerce", 5,
    "Web sales by category for P4, plus what share of web each one is",
    f"""
WITH {WEB_DISPATCH},
{NET_LINES},
by_category AS (
    SELECT cp.category, SUM(n.net_sales) AS web_net_sales
    FROM net_lines n
    JOIN dim_date d     ON d.calendar_date = n.business_date
    JOIN dim_product cp ON cp.sku = n.sku AND cp.is_current
    WHERE n.store_id = 900 AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 4
    GROUP BY 1
)
SELECT category, web_net_sales, ROUND(100.0 * web_net_sales / SUM(web_net_sales) OVER (), 1) AS share_of_web_pct
FROM by_category
ORDER BY web_net_sales DESC;
""",
    "P4 = current year's P4; web sales on dispatch date, categories as-is.",
    ["DEF-WEB-RECOGNITION", "DEF-HIERARCHY-ASIS", "CAL-RELATIVE"],
    ("2026-08-03", "2026-08-30"), uses=("web",))

# ---- Pattern 6: click-and-collect share ------------------------------------------------------------------------

add("REQ-D22", "2025-12-09", "Tiina Mäkelä", "E-commerce", 6,
    "Click and collect share of web sales by period, P1 to P4",
    f"""
WITH {WEB_DISPATCH},
web_lines AS (
    SELECT w.dispatch_date AS business_date, o.fulfilment_type, f.net_amount AS net_sales
    FROM fact_sales_line f
    JOIN dim_store s ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    JOIN fact_web_order o ON o.web_order_id = f.receipt_id
    WHERE s.store_id = 900 AND p.category <> 'ZZ Test'
    UNION ALL
    -- refunds booked to the web shop, tied back to the order's fulfilment type
    SELECT r.return_date, o.fulfilment_type, -r.refund_net
    FROM fact_return_line r
    JOIN dim_store s ON s.store_key = r.store_key
    JOIN fact_sales_line f ON f.sales_line_id = r.sales_line_id
    JOIN dim_product p ON p.product_key = f.product_key
    JOIN fact_web_order o ON o.web_order_id = f.receipt_id
    WHERE s.store_id = 900 AND p.category <> 'ZZ Test'
)
SELECT d.fiscal_period,
       SUM(CASE WHEN l.fulfilment_type = 'click_and_collect' THEN l.net_sales ELSE 0 END) AS click_collect_net,
       SUM(l.net_sales) AS web_net,
       ROUND(100.0 * SUM(CASE WHEN l.fulfilment_type = 'click_and_collect' THEN l.net_sales ELSE 0 END) / SUM(l.net_sales), 1) AS click_collect_share_pct
FROM web_lines l
JOIN dim_date d ON d.calendar_date = l.business_date
WHERE d.fiscal_year = 'FY2025/26' AND d.fiscal_period BETWEEN 1 AND 4
GROUP BY 1
ORDER BY 1;
""",
    "Click-and-collect counts as web, so the denominator is all web; fulfilment type from fact_web_order works on both sides of the migration.",
    ["DEF-CLICK-COLLECT", "REG-MIGRATION", "DEF-WEB-RECOGNITION", "REG-STORE-900"],
    ("2025-04-28", "2025-08-31"), uses=("web",))

add("REQ-D23", "2026-10-01", "Mika Hietala", "Store operations", 6,
    "Which stores handled the most click and collect orders last period, and what share of all collected orders is that",
    """
WITH collected AS (
    SELECT ps.store_id, ps.store_name
    FROM fact_web_order o
    JOIN dim_store ps ON ps.store_key = o.pickup_store_key
    WHERE o.status = 'collected'
      AND CAST(timezone('Europe/Helsinki', o.dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE)
          BETWEEN DATE '2026-08-31' AND DATE '2026-09-27'                       -- FY2026/27 P5
)
SELECT store_id, store_name, COUNT(*) AS collected_orders,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS share_of_collected_pct
FROM collected
GROUP BY 1, 2
ORDER BY collected_orders DESC
LIMIT 15;
""",
    "Last completed period is P5 (31 Aug - 27 Sep 2026); an order counts on its dispatch (ready-for-collection) date in Helsinki time.",
    ["CAL-RELATIVE", "CAL-DATA-THROUGH", "DEF-CLICK-COLLECT", "DEF-TIMEZONE"],
    ("2026-08-31", "2026-09-27"), uses=("web",))

add("REQ-D24", "2026-03-24", "Veikko Saarela", "E-commerce", 6,
    "Is click and collect growing? Share of web orders by quarter since the start of FY24/25.",
    """
SELECT d.fiscal_year, d.fiscal_quarter,
       COUNT(*) AS web_orders,
       SUM(CASE WHEN o.fulfilment_type = 'click_and_collect' THEN 1 ELSE 0 END) AS click_collect_orders,
       ROUND(100.0 * SUM(CASE WHEN o.fulfilment_type = 'click_and_collect' THEN 1 ELSE 0 END) / COUNT(*), 1) AS click_collect_share_pct
FROM fact_web_order o
JOIN dim_date d ON d.calendar_date = CAST(timezone('Europe/Helsinki', o.order_ts_utc AT TIME ZONE 'UTC') AS DATE)
WHERE o.status <> 'cancelled'
  AND d.calendar_date <= DATE '2026-01-25'          -- last complete quarter when asked (Q3 FY2025/26)
GROUP BY 1, 2
ORDER BY 1, 2;
""",
    "Orders, not sales, so fulfilment type from fact_web_order and Helsinki order date; cancelled excluded; only quarters that were complete when asked.",
    ["DEF-CLICK-COLLECT", "DEF-WEB-ORDER-COUNT", "DEF-WEB-CANCELLED", "CAL-PERIODS"],
    ("2024-04-29", "2026-01-25"), uses=("web",))

# ---- Pattern 7: average transaction value ------------------------------------------------------------------------

add("REQ-D25", "2026-09-30", "Leena Vuorinen", "Store operations", 7,
    "ATV by store for last period",
    """
SELECT cs.store_id, cs.store_name,
       COUNT(DISTINCT f.receipt_id) AS receipts,
       ROUND(SUM(f.net_amount) / COUNT(DISTINCT f.receipt_id), 2) AS atv
FROM fact_sales_line f
JOIN dim_store s   ON s.store_key = f.store_key
JOIN dim_store cs  ON cs.store_id = s.store_id AND cs.is_current
JOIN dim_product p ON p.product_key = f.product_key
JOIN dim_date d    ON d.calendar_date = f.sale_date
WHERE s.store_id < 900                         -- stores only: no web, no training store
  AND NOT f.staff_purchase_flag                -- staff purchases are out of ATV
  AND p.category <> 'ZZ Test'
  AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 5
GROUP BY 1, 2
ORDER BY atv DESC;
""",
    "ATV is net sales before returns over sales receipts, stores only, staff purchases and store 999 out; last period = FY2026/27 P5.",
    ["DEF-ATV", "CAL-RELATIVE", "REG-STAFF-PURCHASE", "REG-STORE-999"],
    ("2026-08-31", "2026-09-27"), uses=("store_sales",))

add("REQ-D26", "2025-05-20", "Mika Hietala", "Store operations", 7,
    "ATV by store format, each quarter of FY24/25",
    """
SELECT d.fiscal_quarter, s.format,
       COUNT(DISTINCT f.receipt_id) AS receipts,
       ROUND(SUM(f.net_amount) / COUNT(DISTINCT f.receipt_id), 2) AS atv
FROM fact_sales_line f
JOIN dim_store s   ON s.store_key = f.store_key
JOIN dim_product p ON p.product_key = f.product_key
JOIN dim_date d    ON d.calendar_date = f.sale_date
WHERE s.store_id < 900
  AND NOT f.staff_purchase_flag
  AND p.category <> 'ZZ Test'
  AND d.fiscal_year = 'FY2024/25'
GROUP BY 1, 2
ORDER BY 1, 2;
""",
    "Format is the same in every store version, so the version valid on the sale date is fine here.",
    ["DEF-ATV", "REG-SCD-KEYS", "REG-STAFF-PURCHASE"],
    ("2024-04-29", "2025-04-27"), uses=("store_sales",))

add("REQ-D27", "2026-04-07", "Leena Vuorinen", "Store operations", 7,
    "ATV by weekday for P11",
    """
SELECT d.day_of_week, d.day_name,
       COUNT(DISTINCT f.receipt_id) AS receipts,
       ROUND(SUM(f.net_amount) / COUNT(DISTINCT f.receipt_id), 2) AS atv
FROM fact_sales_line f
JOIN dim_store s   ON s.store_key = f.store_key
JOIN dim_product p ON p.product_key = f.product_key
JOIN dim_date d    ON d.calendar_date = f.sale_date
WHERE s.store_id < 900
  AND NOT f.staff_purchase_flag
  AND p.category <> 'ZZ Test'
  AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 11
GROUP BY 1, 2
ORDER BY 1;
""",
    "P11 of last year (FY2025/26, weeks 44-47); same ATV rules.",
    ["DEF-ATV", "CAL-PERIODS"],
    ("2026-02-23", "2026-03-22"), uses=("store_sales",))

add("REQ-D28", "2026-05-27", "Mika Hietala", "Store operations", 7,
    "Pori ATV against the whole chain, by period, second half of last year",
    """
WITH receipts AS (
    SELECT d.fiscal_period, s.store_id, f.receipt_id, SUM(f.net_amount) AS receipt_net
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    JOIN dim_date d    ON d.calendar_date = f.sale_date
    WHERE s.store_id < 900 AND NOT f.staff_purchase_flag AND p.category <> 'ZZ Test'
      AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period BETWEEN 7 AND 12
    GROUP BY 1, 2, 3
)
SELECT fiscal_period,
       ROUND(SUM(CASE WHEN store_id = 119 THEN receipt_net END) / COUNT(CASE WHEN store_id = 119 THEN 1 END), 2) AS pori_atv,
       ROUND(SUM(receipt_net) / COUNT(*), 2) AS chain_atv
FROM receipts
GROUP BY 1
ORDER BY 1;
""",
    "Pori is store 119; same ATV rules, store receipts only; second half = P7-P12.",
    ["DEF-ATV", "CAL-PERIODS"],
    ("2025-10-27", "2026-05-03"), uses=("store_sales",))

# ---- Pattern 8: active loyalty members, member share of sales ----------------------------------------------------

add("REQ-D29", "2025-05-06", "Sanna Ahonen", "Marketing and CRM", 8,
    "How many active members did we have at the end of last year?",
    """
WITH as_of AS (
    SELECT fiscal_week_end_date AS as_of_end FROM dim_date WHERE calendar_date = DATE '2025-04-27'
)
SELECT COUNT(DISTINCT m.member_id) AS active_members
FROM fact_sales_line f
JOIN dim_member m ON m.member_key = f.member_key
CROSS JOIN as_of
WHERE f.sale_date > as_of.as_of_end - 364           -- trailing 52 fiscal weeks, as-of week included
  AND f.sale_date <= as_of.as_of_end;
""",
    "End of FY2024/25 = Sunday 27 April 2025; active = a purchase in the trailing 52 fiscal weeks, counted on distinct member_id (not member_key).",
    ["DEF-ACTIVE-MEMBER", "REG-MEMBER-VERSIONS", "CAL-FY-DATES"],
    ("2024-04-29", "2025-04-27"), uses=("member_web",))

add("REQ-D30", "2025-10-08", "Jukka Ylönen", "Marketing and CRM", 8,
    "Active members by tier as of the last Sunday of September, split Basic/Silver/Gold",
    """
WITH as_of AS (
    SELECT DATE '2025-09-28' AS as_of_end
),
active AS (
    SELECT DISTINCT m.member_id
    FROM fact_sales_line f
    JOIN dim_member m ON m.member_key = f.member_key
    CROSS JOIN as_of
    WHERE f.sale_date > as_of.as_of_end - 364 AND f.sale_date <= as_of.as_of_end
)
SELECT cur.tier, COUNT(*) AS active_members
FROM active a
CROSS JOIN as_of
JOIN dim_member cur ON cur.member_id = a.member_id
                   AND as_of.as_of_end BETWEEN cur.valid_from AND cur.valid_to      -- tier as it was on the as-of date
GROUP BY 1
ORDER BY 1;
""",
    "Active on distinct member_id; tier is the member version valid on the as-of date, otherwise members would be counted once per version.",
    ["DEF-ACTIVE-MEMBER", "REG-MEMBER-VERSIONS", "REG-SCD-KEYS"],
    ("2024-09-30", "2025-09-28"), uses=("member_web",))

add("REQ-D31", "2025-05-14", "Sanna Ahonen", "Marketing and CRM", 8,
    "Member share of sales by month, November to April just gone",
    f"""
WITH {WEB_DISPATCH},
lines AS (
    SELECT COALESCE(w.dispatch_date, f.sale_date) AS business_date, f.member_key, f.net_amount
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
)
SELECT date_trunc('month', business_date) AS month,
       SUM(net_amount) AS net_sales,
       SUM(CASE WHEN member_key IS NOT NULL THEN net_amount ELSE 0 END) AS member_net_sales,
       ROUND(100.0 * SUM(CASE WHEN member_key IS NOT NULL THEN net_amount ELSE 0 END) / SUM(net_amount), 1) AS member_share_pct
FROM lines
WHERE business_date BETWEEN DATE '2024-11-01' AND DATE '2025-04-27'
GROUP BY 1
ORDER BY 1;
""",
    "Net sales before returns; guest web orders and non-member receipts are the non-member part; web on dispatch date; window ends at the fiscal year end.",
    ["DEF-MEMBER-SHARE", "REG-GUEST-ORDERS", "DEF-WEB-RECOGNITION"],
    ("2024-11-01", "2025-04-27"), uses=("member_web",))

add("REQ-D32", "2026-06-09", "Jukka Ylönen", "Marketing and CRM", 8,
    "Member share of sales by region for P1 this year",
    f"""
WITH {WEB_DISPATCH},
lines AS (
    SELECT COALESCE(w.dispatch_date, f.sale_date) AS business_date, s.store_id, f.member_key, f.net_amount
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
)
SELECT cs.region,
       SUM(l.net_amount) AS net_sales,
       ROUND(100.0 * SUM(CASE WHEN l.member_key IS NOT NULL THEN l.net_amount ELSE 0 END) / SUM(l.net_amount), 1) AS member_share_pct
FROM lines l
JOIN dim_date d   ON d.calendar_date = l.business_date
JOIN dim_store cs ON cs.store_id = l.store_id AND cs.is_current
WHERE d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 1
GROUP BY 1
ORDER BY 1;
""",
    "Regions as-is with Online on its own line; net sales before returns.",
    ["DEF-MEMBER-SHARE", "DEF-HIERARCHY-ASIS", "REG-GUEST-ORDERS"],
    ("2026-05-04", "2026-05-31"), uses=("member_web",))

# ---- Pattern 11: top-N products by margin in a region ------------------------------------------------------------

add("REQ-D33", "2026-02-10", "Hanna Kivistö", "Commercial (category management)", 11,
    "Top 10 products by margin in the North, first half of last year",
    f"""
WITH {WEB_DISPATCH},
{NET_LINES}
SELECT cp.sku, cp.product_name, cp.category, SUM(n.net_sales) AS net_sales, SUM(n.net_sales - n.cost) AS gross_margin
FROM net_lines n
JOIN dim_date d     ON d.calendar_date = n.business_date
JOIN dim_store cs   ON cs.store_id = n.store_id AND cs.is_current
JOIN dim_product cp ON cp.sku = n.sku AND cp.is_current
WHERE cs.region = 'North'
  AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period BETWEEN 1 AND 6
GROUP BY 1, 2, 3
ORDER BY gross_margin DESC
LIMIT 10;
""",
    "North as it is now (as-is); first half = P1-P6; margin after returns; Online is its own region so web is not in the North.",
    ["DEF-GROSS-MARGIN", "DEF-HIERARCHY-ASIS", "REG-STORE-900"],
    ("2025-04-28", "2025-11-02"), regions=["North"], uses=("store_sales",))

add("REQ-D34", "2026-08-18", "Pekka Lindroos", "Commercial (category management)", 11,
    "Top 10 brands by gross margin in the Capital Region, P1-P3 this year",
    f"""
WITH {WEB_DISPATCH},
{NET_LINES}
SELECT cp.brand, SUM(n.net_sales) AS net_sales, SUM(n.net_sales - n.cost) AS gross_margin
FROM net_lines n
JOIN dim_date d     ON d.calendar_date = n.business_date
JOIN dim_store cs   ON cs.store_id = n.store_id AND cs.is_current
JOIN dim_product cp ON cp.sku = n.sku AND cp.is_current
WHERE cs.region = 'Capital Region'
  AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period BETWEEN 1 AND 3
GROUP BY 1
ORDER BY gross_margin DESC
LIMIT 10;
""",
    "Capital Region only exists as a region from the reorganisation; as-is it also covers last year's South stores, but this request is current-year only.",
    ["DEF-HIERARCHY-ASIS", "REG-REGION-REORG", "DEF-GROSS-MARGIN"],
    ("2026-05-04", "2026-08-02"), regions=["Capital Region"], uses=("store_sales",))

add("REQ-D35", "2026-05-26", "Hanna Kivistö", "Commercial (category management)", 11,
    "Which 5 subcategories made the most margin in the East in the second half of last year?",
    f"""
WITH {WEB_DISPATCH},
{NET_LINES}
SELECT cp.category, cp.subcategory, SUM(n.net_sales - n.cost) AS gross_margin, SUM(n.net_sales) AS net_sales
FROM net_lines n
JOIN dim_date d     ON d.calendar_date = n.business_date
JOIN dim_store cs   ON cs.store_id = n.store_id AND cs.is_current
JOIN dim_product cp ON cp.sku = n.sku AND cp.is_current
WHERE cs.region = 'East'
  AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period BETWEEN 7 AND 12
GROUP BY 1, 2
ORDER BY gross_margin DESC
LIMIT 5;
""",
    "East as-is (Kouvola is no longer in it); second half = P7-P12 including week 53.",
    ["DEF-HIERARCHY-ASIS", "REG-REGION-REORG", "DEF-GROSS-MARGIN"],
    ("2025-10-27", "2026-05-03"), regions=["East"], uses=("store_sales",))

add("REQ-D36", "2025-07-09", "Pekka Lindroos", "Commercial (category management)", 11,
    "Top 10 own-label products by margin in the West, Q4 of FY24/25",
    f"""
WITH {WEB_DISPATCH},
{NET_LINES}
SELECT cp.sku, cp.product_name, SUM(n.net_sales - n.cost) AS gross_margin, SUM(n.net_sales) AS net_sales
FROM net_lines n
JOIN dim_date d     ON d.calendar_date = n.business_date
JOIN dim_store cs   ON cs.store_id = n.store_id AND cs.is_current
JOIN dim_product cp ON cp.sku = n.sku AND cp.is_current
WHERE cs.region = 'West'
  AND cp.own_label_flag
  AND d.fiscal_year = 'FY2024/25' AND d.fiscal_quarter = 4
GROUP BY 1, 2
ORDER BY gross_margin DESC
LIMIT 10;
""",
    "Q4 = P10-P12 FY2024/25; West as-is; product attributes from the current version.",
    ["DEF-HIERARCHY-ASIS", "CAL-PERIODS", "DEF-GROSS-MARGIN"],
    ("2025-01-27", "2025-04-27"), regions=["West"], uses=("store_sales",))

# ---- Pattern 12: store league table -----------------------------------------------------------------------------

TRADING_DAYS = """trading_days AS (
    -- days the store was open: after opening, before closure, outside refit closures, not a closed holiday
    SELECT cs.store_id, COUNT(*) AS trading_days
    FROM dim_store cs
    CROSS JOIN period_days pd
    WHERE cs.is_current AND cs.store_id < 900
      AND (cs.open_date IS NULL OR cs.open_date <= pd.calendar_date)
      AND (cs.close_date IS NULL OR cs.close_date >= pd.calendar_date)
      AND NOT EXISTS (SELECT 1 FROM ref_store_closure c
                      WHERE c.store_id = cs.store_id AND pd.calendar_date BETWEEN c.closure_start_date AND c.closure_end_date)
    GROUP BY 1
)"""


def league_sql(where_dates: str, extra_store_filter: str = "") -> str:
    return f"""
WITH period_days AS (
    SELECT calendar_date FROM dim_date
    WHERE {where_dates} AND is_trading_day
),
{TRADING_DAYS},
{NET_LINES_STORES},
store_sales AS (
    SELECT n.store_id, SUM(n.net_sales) AS net_sales
    FROM net_lines n
    JOIN dim_date d ON d.calendar_date = n.business_date
    WHERE {where_dates.replace('calendar_date', 'd.calendar_date').replace('fiscal_year', 'd.fiscal_year').replace('fiscal_period', 'd.fiscal_period').replace('fiscal_quarter', 'd.fiscal_quarter')}
    GROUP BY 1
)
SELECT RANK() OVER (ORDER BY ss.net_sales / td.trading_days DESC) AS rank, cs.store_id, cs.store_name, cs.format,
       td.trading_days, ss.net_sales, ROUND(ss.net_sales / td.trading_days, 0) AS net_sales_per_trading_day
FROM store_sales ss
JOIN trading_days td ON td.store_id = ss.store_id
JOIN dim_store cs    ON cs.store_id = ss.store_id AND cs.is_current
{extra_store_filter}
ORDER BY rank;
"""


add("REQ-D37", "2025-09-09", "Leena Vuorinen", "Store operations", 12,
    "League table of the stores for P4, please",
    league_sql("fiscal_year = 'FY2025/26' AND fiscal_period = 4"),
    "Ranked on net sales per trading day, stores only (web and the training store are not stores for this).",
    ["DEF-STORE-LEAGUE", "DEF-STORE-SCOPE", "CAL-CLOSED-DAYS"],
    ("2025-08-04", "2025-08-31"), uses=("store_sales",))

add("REQ-D38", "2026-02-03", "Mika Hietala", "Store operations", 12,
    "Store league table for Q3, and mark the new stores and the one that closed",
    league_sql("fiscal_year = 'FY2025/26' AND fiscal_quarter = 3").replace(
        "ORDER BY rank;",
        "ORDER BY rank;\n-- store_id 136 and 137 are the 2024 openings, 129 the closure: read their trading_days column"),
    "Kept every store that traded; Savonlinna shows fewer trading days because it closed in week 39.",
    ["DEF-STORE-LEAGUE", "REG-STORE-EVENTS", "CAL-PERIODS"],
    ("2025-10-27", "2026-01-25"), uses=("store_sales",))

add("REQ-D39", "2025-06-03", "Leena Vuorinen", "Store operations", 12,
    "League table for the Large stores, second half of FY24/25",
    league_sql("fiscal_year = 'FY2024/25' AND fiscal_period BETWEEN 7 AND 12", "WHERE cs.format = 'Large'"),
    "Large format only; second half = P7-P12; trading days exclude the closed holidays (Christmas, New Year, Easter).",
    ["DEF-STORE-LEAGUE", "CAL-CLOSED-DAYS", "CAL-PERIODS"],
    ("2024-10-28", "2025-04-27"), uses=("store_sales",))

add("REQ-D40", "2026-08-19", "Mika Hietala", "Store operations", 12,
    "League table for P3. Kuopio was closed for the refit, don't let that sink it.",
    league_sql("fiscal_year = 'FY2026/27' AND fiscal_period = 3"),
    "Kuopio's refit weeks are out of its trading days, so it is ranked on the days it did trade.",
    ["DEF-STORE-LEAGUE", "REG-REFITS", "TEAM-LFL-EDGE"],
    ("2026-06-29", "2026-08-02"), uses=("store_sales",))

assert len(DEV_REQUESTS) == 40, len(DEV_REQUESTS)
