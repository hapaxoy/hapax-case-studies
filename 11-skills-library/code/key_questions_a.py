"""Reference queries, naive variants and pandas recomputations, part A: patterns 1 to 4 (Project 11, Phase 3).

Every question is a function registered with @question(qid). Each gives:
  - the reference SQL, written the way the company's definitions say (see world/),
  - a pandas recomputation from the generator's own tables (key_lib.World), sharing no code with the SQL,
  - one naive variant per planted trap (the plausible wrong query), and
  - the plain-English facts the review sheet needs.
Column names are the key's; the marker matches columns by values, not names.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

import config as cfg
from key_lib import NET_EVENTS, NET_EVENTS_DEDUP, WEB_DISPATCH, hel
from key_types import Interpretation, Naive, Question, col, question, yoy_frame, yoy_sql

NET_WITH_DISPATCH = f"WITH {WEB_DISPATCH},\n{NET_EVENTS}"

GROWTH_WORDS = ["growth", "grew", "year on year", "year-on-year", "against last year", "vs last year", "compared with last year", "compared to last year"]
LFL_WORDS = ["lfl", "like-for-like", "like for like"]
# Readings that reach last year's week 21 (15 to 21 September 2025) meet the double-posted week of Tampere Lielahti. They have two
# accepted outcomes: the corrected figures, or the published figures with a caveat naming the duplicates.
INC1_CAVEAT = {
    "keywords": [["duplicate", "double", "twice", "repeated", "re-posted", "reposted", "posted two", "dupe", "inflat", "overstat", "more than once"],
                 ["116", "lielahti", "week 21", "15 sep", "15-21", "21 sep", "tampere", "west"]],
    "pass": "Store 116 Tampere Lielahti has duplicate receipt lines in the week of 15 to 21 September 2025, so last year's figure for it is overstated.",
    "fail": "Figures were computed from the sales lines and returns, excluding store 999 and test articles.",
}

# Second reading of "today's category": the Outdoor Lighting subcategory as a whole is in Electrical (five delisted articles
# never got a new product version and still show Garden).
MOVED_CATEGORY = "CASE WHEN cp.subcategory = 'Outdoor Lighting' THEN 'Electrical' ELSE cp.category END"
AS_IS_STORE = "JOIN dim_store cs ON cs.store_id = n.store_id AND cs.is_current"
AS_WAS_STORE = "JOIN dim_store cs ON cs.store_key = n.store_key"
AS_IS_PRODUCT = "JOIN dim_product cp ON cp.sku = n.sku AND cp.is_current"
AS_WAS_PRODUCT = "JOIN dim_product cp ON cp.product_key = n.product_key"


# ---------------------------------------------------------------------------
# LFL machinery (SQL and pandas written separately)
# ---------------------------------------------------------------------------

def lfl_sql(ty: str, ly: str, week_from: int, week_to: int, period_start: str, by_region: str | None = None,
            ly_dates: tuple | None = None, per_period: bool = False, events: str = NET_EVENTS) -> str:
    """LFL net sales for the later year `ty` against `ly`, over fiscal weeks week_from..week_to.

    Store-week eligibility: the store traded in that fiscal week in both years (open for the whole week, not closed,
    not in a refit), and it had been open 364 days before the first day of the period. Web and week 53 are out.
    ly_dates replaces the same-fiscal-week comparator with a date range (the fiscal-calendar trap).
    per_period applies the 364-day rule to the first day of each fiscal period inside the range instead of the first day of
    the whole range (an accepted second reading of "for a period"). events chooses the de-duplicated lines for readings that
    reach the double-posted week.
    """
    open_rule = "t.pstart" if per_period else f"DATE '{period_start}'"
    # by_region: None (one total), "asis" (today's region of each store) or "aswas" (the store version on the sale day)
    group_select = "cs.region AS region, " if by_region else ""
    region_join = ""
    if by_region == "asis":
        region_join = "JOIN dim_store cs ON cs.store_id = t.store_id AND cs.is_current"
    elif by_region == "aswas":
        region_join = "JOIN dim_store cs ON cs.store_key = t.store_key"
    ly_filter = (f"(d.fiscal_year = '{ly}' AND d.fiscal_week BETWEEN {week_from} AND {week_to})" if not ly_dates
                 else f"(n.business_date BETWEEN DATE '{ly_dates[0]}' AND DATE '{ly_dates[1]}')")
    ty_filter = f"(d.fiscal_year = '{ty}' AND d.fiscal_week BETWEEN {week_from} AND {week_to})"
    if ly_dates:
        # with a date-aligned comparator the eligible store list is by store only (any eligible week)
        eligible_join = "JOIN (SELECT DISTINCT store_id FROM eligible) el ON el.store_id = n.store_id"
    else:
        eligible_join = "JOIN eligible el ON el.store_id = n.store_id AND el.fiscal_week = d.fiscal_week"
    select_tail = (f"SELECT {group_select}ROUND(SUM(CASE WHEN yr = 'ty' THEN v END), 2) AS net_sales_ty, "
                   f"ROUND(SUM(CASE WHEN yr = 'ly' THEN v END), 2) AS net_sales_ly, "
                   f"ROUND(100.0 * (SUM(CASE WHEN yr = 'ty' THEN v END) / SUM(CASE WHEN yr = 'ly' THEN v END) - 1), 2) AS lfl_growth_pct")
    group_clause = "GROUP BY 1 ORDER BY 1" if by_region else ""
    return f"""WITH {WEB_DISPATCH},
{events},
weeks AS (
    SELECT DISTINCT fiscal_year, fiscal_week, fiscal_week_start_date AS ws, fiscal_week_end_date AS we,
           MIN(fiscal_week_start_date) OVER (PARTITION BY fiscal_year, fiscal_period) AS pstart
    FROM dim_date WHERE fiscal_year IN ('{ty}', '{ly}') AND fiscal_week BETWEEN {week_from} AND {week_to}
),
store_week AS (
    -- trading = open for the whole week, not closed, not in a refit
    SELECT st.store_id, w.fiscal_year, w.fiscal_week, w.pstart,
           (st.open_date IS NULL OR st.open_date <= w.ws) AND (st.close_date IS NULL OR st.close_date >= w.we)
           AND NOT EXISTS (SELECT 1 FROM ref_store_closure c WHERE c.store_id = st.store_id
                           AND c.closure_start_date <= w.we AND c.closure_end_date >= w.ws) AS trading
    FROM dim_store st CROSS JOIN weeks w
    WHERE st.is_current AND st.store_id < 900
),
eligible AS (
    SELECT t.store_id, t.fiscal_week
    FROM store_week t
    JOIN store_week l ON l.store_id = t.store_id AND l.fiscal_week = t.fiscal_week AND l.fiscal_year = '{ly}'
    JOIN dim_store st ON st.store_id = t.store_id AND st.is_current
    WHERE t.fiscal_year = '{ty}' AND t.trading AND l.trading
      AND (st.open_date IS NULL OR st.open_date <= {open_rule} - 364)
),
tagged AS (
    SELECT CASE WHEN {ty_filter} THEN 'ty' ELSE 'ly' END AS yr, n.store_id, n.store_key, n.net_sales AS v, d.fiscal_week
    FROM net_events n
    JOIN dim_date d ON d.calendar_date = n.business_date
    {eligible_join}
    WHERE n.store_id < 900 AND ({ty_filter} OR {ly_filter})
)
{select_tail}
FROM tagged t {region_join}
{group_clause};"""


def lfl_naive_all_stores_sql(ty: str, ly: str, week_from: int, week_to: int, group: str | None = None, group_out: str = "region") -> str:
    """The naive LFL: every physical store, same fiscal weeks, no eligibility rules."""
    group_select = f"{group} AS {group_out}, " if group else ""
    return f"""WITH {WEB_DISPATCH},
{NET_EVENTS},
tagged AS (
    SELECT CASE WHEN d.fiscal_year = '{ty}' THEN 'ty' ELSE 'ly' END AS yr, n.store_id, n.net_sales AS v
    FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date
    WHERE n.store_id < 900 AND d.fiscal_year IN ('{ty}', '{ly}') AND d.fiscal_week BETWEEN {week_from} AND {week_to}
)
SELECT {group_select}ROUND(SUM(CASE WHEN yr = 'ty' THEN v END), 2) AS net_sales_ty, ROUND(SUM(CASE WHEN yr = 'ly' THEN v END), 2) AS net_sales_ly,
       ROUND(100.0 * (SUM(CASE WHEN yr = 'ty' THEN v END) / SUM(CASE WHEN yr = 'ly' THEN v END) - 1), 2) AS lfl_growth_pct
FROM tagged t {'JOIN dim_store cs ON cs.store_id = t.store_id AND cs.is_current' if group else ''}
{'GROUP BY 1 ORDER BY 1' if group else ''};"""


def lfl_naive_total_company_sql(ty: str, ly: str, week_from: int, week_to: int) -> str:
    """The other naive LFL: growth of total company net sales (stores and web) over the same fiscal weeks."""
    return f"""WITH {WEB_DISPATCH},
{NET_EVENTS},
t AS (
    SELECT CASE WHEN d.fiscal_year = '{ty}' THEN 'ty' ELSE 'ly' END AS yr, SUM(n.net_sales) AS v
    FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date
    WHERE d.fiscal_year IN ('{ty}', '{ly}') AND d.fiscal_week BETWEEN {week_from} AND {week_to}
    GROUP BY 1
)
SELECT ROUND(MAX(CASE WHEN yr = 'ty' THEN v END), 2) AS net_sales_ty, ROUND(MAX(CASE WHEN yr = 'ly' THEN v END), 2) AS net_sales_ly,
       ROUND(100.0 * (MAX(CASE WHEN yr = 'ty' THEN v END) / MAX(CASE WHEN yr = 'ly' THEN v END) - 1), 2) AS lfl_growth_pct
FROM t;"""


def lfl_eligible_pairs(world, ty: str, ly: str, week_from: int, week_to: int, period_start: date, per_period: bool = False) -> set:
    """(store_id, fiscal_week) pairs in the LFL base, from cfg.STORES and cfg.REFITS (not from dim_store)."""
    calendar = world.calendar
    # first day of the fiscal period each week of the later year belongs to
    period_first_day = {int(week): calendar[(calendar.fy == ty) & (calendar.period == period)].date.min().date()
                        for week, period in calendar[calendar.fy == ty][["week", "period"]].drop_duplicates().itertuples(index=False)}
    weeks = calendar[calendar.fy.isin([ty, ly]) & calendar.week.between(week_from, week_to)][["fy", "week", "week_start", "week_end"]].drop_duplicates()
    bounds = {(row.fy, row.week): (row.week_start.date(), row.week_end.date()) for row in weeks.itertuples()}
    refits = {}
    for store_id, start, end in cfg.REFITS:
        refits.setdefault(store_id, []).append((start, end))

    def trading(store_id, opened, closed, fy, week):
        week_start, week_end = bounds[(fy, week)]
        if opened is not None and opened > week_start:
            return False
        if closed is not None and closed < week_end:
            return False
        return not any(start <= week_end and end >= week_start for start, end in refits.get(store_id, []))

    pairs = set()
    for store_id, _, _, _, _, _, opened, closed in cfg.STORES:
        for week in range(week_from, week_to + 1):
            rule_day = period_first_day[week] if per_period else period_start
            if opened is not None and opened > rule_day - timedelta(days=364):
                continue
            if trading(store_id, opened, closed, ty, week) and trading(store_id, opened, closed, ly, week):
                pairs.add((store_id, week))
    return pairs


def lfl_frame(world, ty: str, ly: str, week_from: int, week_to: int, period_start: date, group: str | None = None,
              group_out: str = "region", ly_dates: tuple | None = None, as_was: bool = False, per_period: bool = False) -> pd.DataFrame:
    events = world.events()
    events = events[(events.store_id < 900)]
    pairs = lfl_eligible_pairs(world, ty, ly, week_from, week_to, period_start, per_period)
    in_base = pd.Series(list(zip(events.store_id, events.week)), index=events.index).isin(pairs)
    ty_rows = events[in_base & (events.fy == ty) & events.week.between(week_from, week_to)]
    if ly_dates is None:
        ly_rows = events[in_base & (events.fy == ly) & events.week.between(week_from, week_to)]
    else:
        stores = {s for s, _ in pairs}
        ly_rows = events[events.store_id.isin(stores) & (events.date >= pd.Timestamp(ly_dates[0])) & (events.date <= pd.Timestamp(ly_dates[1]))]
    key = (lambda f: f["region_was"]) if as_was else (lambda f: f["region"])
    if group:
        ty_sum = ty_rows.groupby(key(ty_rows)).net_c.sum()
        ly_sum = ly_rows.groupby(key(ly_rows)).net_c.sum()
        return yoy_frame(ty_sum, ly_sum, group_out, growth="lfl_growth_pct")
    ty_total, ly_total = ty_rows.net_c.sum() / 100.0, ly_rows.net_c.sum() / 100.0
    return pd.DataFrame({"net_sales_ty": [ty_total], "net_sales_ly": [ly_total], "lfl_growth_pct": [100.0 * (ty_total / ly_total - 1)]})


LFL_COLUMNS = [col("net_sales_ty", "measure", "eur"), col("net_sales_ly", "measure", "eur"), col("lfl_growth_pct", "measure", "pct")]
LFL_DOCS = ["Metric dictionary, 'Like-for-like (LFL)'", "Team notes, 'LFL edge cases'", "Data quality register, 'Store openings' and 'Refit closures'"]


# ---------------------------------------------------------------------------
# Pattern 1
# ---------------------------------------------------------------------------

@question("Q01")
def q01() -> Question:
    """Net sales by region, Q3 of last year (FY2025/26) against Q3 the year before, web as its own line, as-is regions."""
    ty = "d.fiscal_year = 'FY2025/26' AND d.fiscal_quarter = 3"
    ly = "d.fiscal_year = 'FY2024/25' AND d.fiscal_quarter = 3"
    names = ("net_sales_ty", "net_sales_ly")
    reference = yoy_sql("cs.region", "region", ty, ly, AS_IS_STORE, names)
    as_was = yoy_sql("cs.region", "region", ty, ly, AS_WAS_STORE, names)
    calendar_q3 = yoy_sql("cs.region", "region", "n.business_date BETWEEN DATE '2025-07-01' AND DATE '2025-09-30'",
                          "n.business_date BETWEEN DATE '2024-07-01' AND DATE '2024-09-30'", AS_IS_STORE, names)

    def pandas_fn(world):
        events = world.events()
        q3 = events[events.quarter == 3]
        return yoy_frame(q3[q3.fy == "FY2025/26"].groupby("region").net_c.sum(), q3[q3.fy == "FY2024/25"].groupby("region").net_c.sum(), "region")

    return Question(
        "Q01", 1, [col("region", "dimension", "text"), col("net_sales_ty", "measure", "eur"), col("net_sales_ly", "measure", "eur"),
                   col("growth_pct", "measure", "pct")],
        reference, pandas_fn,
        {"counts": "Net sales after returns (returns taken off on the day they were booked), web on its dispatch date. Q3 is periods 7 to 9, weeks 27 to 39, in both years. Regions are today's regions applied to both years, with the web shop as its own line, Online.",
         "leaves_out": "Store 999 (the training store) and test articles. Week 53 does not fall in Q3.",
         "docs": ["Metric dictionary, 'Net sales', 'Fiscal calendar' and 'Hierarchies and stores'", "Data quality register, 'History that changes the answer'"],
         "result_note": "One row per region, last year's Q3 against the year before, with growth."},
        naive=[Naive("scd", "as_was_region", as_was, "Uses each store's region as it was on the day of the sale. Last year's Capital Region stores were still in South the year before, so the two years cannot be compared and the Capital Region has no comparator."),
               Naive("fiscal_calendar", "calendar_quarter", calendar_q3, "Reads Q3 as July to September instead of the fiscal Q3 (late October to late January).")])


@question("Q03")
def q03() -> Question:
    """Total company net sales per week for P2 this year against the same weeks last year."""
    ty = "d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 2"
    ly = "d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 2"
    reference = yoy_sql("d.fiscal_week", "fiscal_week", ty, ly)
    shifted = f"""WITH {WEB_DISPATCH},
{NET_EVENTS},
ty AS (SELECT d.fiscal_week, SUM(n.net_sales) AS v FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date
       WHERE d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 2 GROUP BY 1),
ly AS (SELECT d.fiscal_week, SUM(n.net_sales) AS v FROM net_events n
       JOIN dim_date d ON d.calendar_date = CAST(n.business_date + INTERVAL 1 YEAR AS DATE)
       WHERE d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 2 GROUP BY 1)
SELECT ty.fiscal_week, ROUND(ty.v, 2) AS net_sales_ty, ROUND(ly.v, 2) AS net_sales_ly, ROUND(100.0 * (ty.v / ly.v - 1), 2) AS growth_pct
FROM ty JOIN ly USING (fiscal_week) ORDER BY 1;"""

    def pandas_fn(world):
        events = world.events()
        p2 = events[events.period == 2]
        return yoy_frame(p2[p2.fy == "FY2026/27"].groupby("week").net_c.sum(), p2[p2.fy == "FY2025/26"].groupby("week").net_c.sum(), "fiscal_week")

    return Question(
        "Q03", 1, [col("fiscal_week", "dimension", "count"), col("net_sales_ty", "measure", "eur"), col("net_sales_ly", "measure", "eur"),
                   col("growth_pct", "measure", "pct")],
        reference, pandas_fn,
        {"counts": "Total company net sales (stores and web, after returns) for each of the four weeks of period 2 this year (weeks 5 to 8), against the same four fiscal weeks last year.",
         "leaves_out": "Store 999 and test articles.",
         "docs": ["Metric dictionary, 'Fiscal calendar' (compare by the same fiscal week, not the same dates) and 'Net sales'"],
         "result_note": "Four rows, one per week, with growth."},
        naive=[Naive("fiscal_calendar", "date_aligned_last_year", shifted, "Compares with the same calendar dates a year earlier (1 to 28 June 2025). Last year's fiscal weeks started six days earlier, so the comparison is shifted by almost a week.")])


@question("Q06")
def q06() -> Question:
    """Rank the regions by how they are doing this year so far (stores only): net sales or gross margin %."""
    ytd = "d.fiscal_year = 'FY2026/27' AND d.fiscal_week <= 22"
    cols_sales = [col("region", "dimension", "text"), col("metric_value", "measure", "eur")]
    cols_margin = [col("region", "dimension", "text"), col("metric_value", "measure", "pct")]
    sales_sql = f"""{NET_WITH_DISPATCH}
SELECT cs.region, ROUND(SUM(n.net_sales), 2) AS metric_value
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date {AS_IS_STORE}
WHERE n.store_id < 900 AND {ytd}
GROUP BY 1 ORDER BY metric_value DESC;"""
    margin_sql = f"""{NET_WITH_DISPATCH}
SELECT cs.region, ROUND(100.0 * SUM(n.net_sales - n.cost) / SUM(n.net_sales), 2) AS metric_value
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date {AS_IS_STORE}
WHERE n.store_id < 900 AND {ytd}
GROUP BY 1 ORDER BY metric_value DESC;"""
    through_p5 = sales_sql.replace("d.fiscal_week <= 22", "d.fiscal_week <= 21")

    def sales_fn(world):
        e = world.events()
        e = e[(e.store_id < 900) & (e.fy == "FY2026/27") & (e.week <= 22)]
        out = (e.groupby("region").net_c.sum() / 100.0).rename("metric_value").reset_index()
        return out.sort_values("metric_value", ascending=False).reset_index(drop=True)

    def margin_fn(world):
        e = world.events()
        e = e[(e.store_id < 900) & (e.fy == "FY2026/27") & (e.week <= 22)]
        grouped = e.groupby("region")[["net_c", "cost_c"]].sum()
        out = (100.0 * (grouped.net_c - grouped.cost_c) / grouped.net_c).rename("metric_value").reset_index()
        return out.sort_values("metric_value", ascending=False).reset_index(drop=True)

    def growth_rank_sql(events: str) -> str:
        inner = yoy_sql("cs.region", "region", "d.fiscal_year = 'FY2026/27' AND d.fiscal_week <= 22", "d.fiscal_year = 'FY2025/26' AND d.fiscal_week <= 22",
                        AS_IS_STORE, events=events, where_extra="AND n.store_id < 900").rstrip(";")
        return f"SELECT region, growth_pct AS metric_value FROM ({inner}) ORDER BY metric_value DESC, region;"

    def lfl_rank_sql(events: str) -> str:
        inner = lfl_sql("FY2026/27", "FY2025/26", 1, 22, "2026-05-04", by_region="asis", events=events).rstrip(";")
        return f"SELECT region, lfl_growth_pct AS metric_value FROM ({inner}) ORDER BY metric_value DESC, region;"

    def growth_rank_fn(world):
        e = world.events()
        e = e[(e.store_id < 900) & (e.week <= 22)]
        frame = yoy_frame(e[e.fy == "FY2026/27"].groupby("region").net_c.sum(), e[e.fy == "FY2025/26"].groupby("region").net_c.sum(), "region")
        out = frame[["region", "growth_pct"]].rename(columns={"growth_pct": "metric_value"})
        return out.sort_values(["metric_value", "region"], ascending=[False, True]).reset_index(drop=True)

    def lfl_rank_fn(world):
        frame = lfl_frame(world, "FY2026/27", "FY2025/26", 1, 22, date(2026, 5, 4), group="region")
        out = frame[["region", "lfl_growth_pct"]].rename(columns={"lfl_growth_pct": "metric_value"})
        return out.sort_values(["metric_value", "region"], ascending=[False, True]).reset_index(drop=True)

    return Question(
        "Q06", 1, cols_sales, sales_sql, sales_fn,
        {"counts": "The five store regions (Capital Region, South, West, East, North) ranked on the current fiscal year to date, weeks 1 to 22. Reading 1 ranks by net sales; reading 2 by gross margin percentage; reading 3 by net sales growth against the same fiscal weeks last year; reading 4 by like-for-like growth. The request does not say which; any of the four is accepted if the answer says which it used. Readings 3 and 4 use last year's week 21, in which Tampere Lielahti's receipts were posted twice in the published data, so they have two accepted outcomes: the corrected figures, or the published figures with the duplicates named in the caveats.",
         "leaves_out": "The web shop (not a region), store 999 and test articles. Year to date runs to the last completed week, week 22 (ending 4 October 2026).",
         "docs": ["Metric dictionary, 'Net sales', 'Gross margin' and 'Fiscal calendar' (YTD)"],
         "result_note": "Five rows, best first."},
        naive=[Naive("fiscal_calendar", "ytd_to_last_period", through_p5, "Stops the year to date at the end of period 5 (week 21) instead of the last completed week (week 22).")],
        ordered=True,
        interpretations=[
            Interpretation("net_sales", "Rank by net sales, year to date", sales_sql, sales_fn, cols_sales,
                           [["net sales", "sales", "revenue", "turnover"]], "I ranked the regions by net sales year to date.",
                           "I ranked the regions by how they are doing."),
            Interpretation("gross_margin_pct", "Rank by gross margin percentage, year to date", margin_sql, margin_fn, cols_margin,
                           [["margin"]], "I read 'doing well' as gross margin percentage.", "I ranked the regions by how they are doing."),
            Interpretation("growth_total", "Rank by net sales growth against last year, year to date (week for week, weeks 1 to 22 of both years)",
                           growth_rank_sql(NET_EVENTS_DEDUP), growth_rank_fn, cols_margin,
                           [GROWTH_WORDS], "I ranked the regions by net sales growth against last year, year to date.", "I ranked the regions by how they are doing.",
                           published_sql=growth_rank_sql(NET_EVENTS), published_pandas_fn=growth_rank_fn,
                           caveat_keywords=INC1_CAVEAT["keywords"], caveat_pass=INC1_CAVEAT["pass"], caveat_fail=INC1_CAVEAT["fail"]),
            Interpretation("growth_lfl", "Rank by like-for-like growth against last year, year to date",
                           lfl_rank_sql(NET_EVENTS_DEDUP), lfl_rank_fn, cols_margin,
                           [LFL_WORDS], "I ranked the regions by like-for-like growth against last year, year to date.", "I ranked the regions by total net sales growth.",
                           published_sql=lfl_rank_sql(NET_EVENTS), published_pandas_fn=lfl_rank_fn,
                           caveat_keywords=INC1_CAVEAT["keywords"], caveat_pass=INC1_CAVEAT["pass"], caveat_fail=INC1_CAVEAT["fail"])])


@question("A3")
def a3() -> Question:
    """Total company net sales last month: calendar September 2026 or fiscal period 5."""
    cols = [col("net_sales", "measure", "eur")]

    def sql_range(start, end):
        return f"""{NET_WITH_DISPATCH}
SELECT ROUND(SUM(n.net_sales), 2) AS net_sales FROM net_events n WHERE n.business_date BETWEEN DATE '{start}' AND DATE '{end}';"""

    def fn_range(start, end):
        def fn(world):
            e = world.events()
            return pd.DataFrame({"net_sales": [e[(e.date >= pd.Timestamp(start)) & (e.date <= pd.Timestamp(end))].net_c.sum() / 100.0]})
        return fn

    return Question(
        "A3", 1, cols, sql_range("2026-09-01", "2026-09-30"), fn_range("2026-09-01", "2026-09-30"),
        {"counts": "Total company net sales (stores and web, after returns). Reading 1 takes 'last month' as calendar September 2026 (1 to 30 September). Reading 2 takes it as the last completed fiscal period, P5 (31 August to 27 September 2026). The dictionary defines 'last period' but not 'last month', so both are accepted when the answer says which was used.",
         "leaves_out": "Store 999 and test articles.",
         "docs": ["Metric dictionary, 'Fiscal calendar' (relative terms) and 'Net sales'"],
         "result_note": "One number."},
        naive=[Naive("fiscal_calendar", "rolling_28_days", sql_range("2026-09-07", "2026-10-04"),
                     "Takes the last 28 days up to the data cut (7 September to 4 October), a window that is neither calendar September nor a fiscal period.")],
        interpretations=[
            Interpretation("calendar_september", "Calendar September 2026", sql_range("2026-09-01", "2026-09-30"), fn_range("2026-09-01", "2026-09-30"),
                           cols, [["september", "calendar month", "1 sep", "1-30"]], "I took last month as calendar September 2026.", "I assumed the usual definition."),
            Interpretation("fiscal_p5", "Fiscal period 5 (31 August to 27 September)", sql_range("2026-08-31", "2026-09-27"), fn_range("2026-08-31", "2026-09-27"),
                           cols, [["p5", "period 5", "fiscal period", "last period", "31 aug", "27 sep"]], "I used the last completed fiscal period, P5.",
                           "I assumed the usual definition.")])


@question("O1")
def o1() -> Question:
    """Gross sales including VAT by region for August and September 2024, regions as they were then (tax team)."""
    cols = [col("region", "dimension", "text"), col("gross_incl_vat_aug_2024", "measure", "eur"), col("gross_incl_vat_sep_2024", "measure", "eur")]

    def sql(region_join, gross_expr="f.gross_amount"):
        return f"""WITH {WEB_DISPATCH},
lines AS (
    SELECT COALESCE(w.dispatch_date, f.sale_date) AS business_date, {region_join} AS region, {gross_expr} AS gross
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
)
SELECT region,
       ROUND(SUM(CASE WHEN business_date BETWEEN DATE '2024-08-01' AND DATE '2024-08-31' THEN gross ELSE 0 END), 2) AS gross_incl_vat_aug_2024,
       ROUND(SUM(CASE WHEN business_date BETWEEN DATE '2024-09-01' AND DATE '2024-09-30' THEN gross ELSE 0 END), 2) AS gross_incl_vat_sep_2024
FROM lines WHERE business_date BETWEEN DATE '2024-08-01' AND DATE '2024-09-30'
GROUP BY 1 ORDER BY 1;"""

    reference = sql("s.region")
    as_is = sql("(SELECT cs.region FROM dim_store cs WHERE cs.store_id = s.store_id AND cs.is_current)")
    flat = sql("s.region", "f.net_amount * 1.255")

    def pandas_fn(world):
        s = world.in_scope_sales()
        s = s[(s.business_date >= pd.Timestamp("2024-08-01")) & (s.business_date <= pd.Timestamp("2024-09-30"))]
        aug = s[s.business_date <= pd.Timestamp("2024-08-31")].groupby("region_was").gross_c.sum()
        sep = s[s.business_date >= pd.Timestamp("2024-09-01")].groupby("region_was").gross_c.sum()
        frame = pd.DataFrame({"gross_incl_vat_aug_2024": aug / 100.0, "gross_incl_vat_sep_2024": sep / 100.0}).fillna(0.0)
        frame.index.name = "region"
        return frame.reset_index()

    return Question(
        "O1", 1, cols, reference, pandas_fn,
        {"counts": "Gross sales including VAT, summed from the gross amount on each sales line (each line at its own VAT rate), before returns, for August and September 2024 as two columns. Regions are as they were at the time (four regions plus Online), because the request asks for that.",
         "leaves_out": "Store 999 and test articles. Returns are not taken off (the request asks for gross sales). Web on its dispatch date.",
         "docs": ["Team notes, 'explicitly asks' rule (follow the request and say so)", "Metric dictionary, 'Net sales' (including-VAT figures come from gross_amount) and 'Hierarchies and stores' (as-was)",
                  "Data quality register, 'The VAT rate rose from 24% to 25.5% on 1 September 2024'"],
         "result_note": "One row per region, two columns (August, September)."},
        naive=[Naive("override", "as_is_region_default", as_is, "Uses today's regions (the company default) although the request asks for the regions as they were. The Capital Region appears and South is too small."),
               Naive("vat", "flat_vat_rate", flat, "Multiplies net sales by one flat 25.5% VAT rate. August 2024 was at 24%, and reduced-rate goods carry 14% or 10%.")])


# ---------------------------------------------------------------------------
# Pattern 2: like-for-like
# ---------------------------------------------------------------------------

@question("L1")
def l1() -> Question:
    reference = lfl_sql("FY2026/27", "FY2025/26", 1, 4, "2026-05-04")

    def pandas_fn(world):
        return lfl_frame(world, "FY2026/27", "FY2025/26", 1, 4, date(2026, 5, 4))

    return Question(
        "L1", 2, LFL_COLUMNS, reference, pandas_fn,
        {"counts": "Like-for-like net sales growth for period 1 of this year (weeks 1 to 4) against the same fiscal weeks last year, in the stores that count. A store-week counts only if the store traded that week in both years and the store had been open at least 364 days before the period began. Savonlinna (closed in January 2026) drops out, so it does not drag this year down against last year.",
         "leaves_out": "The web shop, store 999, week 53, the closed store and any store-week in a refit.",
         "docs": LFL_DOCS, "result_note": "This year's LFL sales, last year's, and the growth percentage."},
        naive=[Naive("company_definition", "all_stores_no_lfl_rules", lfl_naive_all_stores_sql("FY2026/27", "FY2025/26", 1, 4),
                     "Compares all physical stores with no LFL rules, so Savonlinna's sales last year are in the base but it sold nothing this year."),
               Naive("fiscal_calendar", "date_aligned_last_year", lfl_sql("FY2026/27", "FY2025/26", 1, 4, "2026-05-04", ly_dates=("2025-05-04", "2025-05-31")),
                     "Takes last year's comparator as the same calendar dates (4 to 31 May 2025) instead of the same fiscal weeks, which starts it six days late.")])


@question("L3")
def l3() -> Question:
    reference = lfl_sql("FY2025/26", "FY2024/25", 27, 39, "2025-10-27", by_region="asis")
    as_was = lfl_sql("FY2025/26", "FY2024/25", 27, 39, "2025-10-27", by_region="aswas")

    def pandas_fn(world):
        return lfl_frame(world, "FY2025/26", "FY2024/25", 27, 39, date(2025, 10, 27), group="region")

    return Question(
        "L3", 2, [col("region", "dimension", "text")] + LFL_COLUMNS, reference, pandas_fn,
        {"counts": "Like-for-like growth by region for Q3 of last year (periods 7 to 9, weeks 27 to 39) against Q3 the year before, using today's regions for both years. Lohja (opened 4 November 2024) has not been open 364 days by the start of the period (27 October 2025), so it is not in the base; Savonlinna counts for its weeks of trading.",
         "leaves_out": "The web shop (so no Online line), store 999, week 53 and any store-week not trading in both years.",
         "docs": LFL_DOCS + ["Metric dictionary, 'Hierarchies and stores' (as-is regions)"], "result_note": "One row per store region."},
        naive=[Naive("scd", "as_was_region", as_was, "Uses each year's own regions. The Capital Region did not exist the year before, so there is nothing to compare it with, and South and East are different sets of stores in the two years."),
               Naive("company_definition", "all_stores_no_lfl_rules", lfl_naive_all_stores_sql("FY2025/26", "FY2024/25", 27, 39, group="cs.region"),
                     "Compares every physical store with no LFL rules, so Lohja (open less than a year) and Savonlinna's partial year are in the base.")],
        alternatives=[{"label": "the 364-day rule applied to the first day of each fiscal period (Lohja counts from P8)",
                       "sql": lfl_sql("FY2025/26", "FY2024/25", 27, 39, "2025-10-27", by_region="asis", per_period=True),
                       "pandas_fn": lambda world: lfl_frame(world, "FY2025/26", "FY2024/25", 27, 39, date(2025, 10, 27), group="region", per_period=True)}])


@question("L5")
def l5() -> Question:
    reference = lfl_sql("FY2026/27", "FY2025/26", 14, 17, "2026-08-03")
    shifted = lfl_sql("FY2026/27", "FY2025/26", 14, 17, "2026-08-03", ly_dates=("2025-08-03", "2025-08-30"))

    def pandas_fn(world):
        return lfl_frame(world, "FY2026/27", "FY2025/26", 14, 17, date(2026, 8, 3))

    return Question(
        "L5", 2, LFL_COLUMNS, reference, pandas_fn,
        {"counts": "Like-for-like growth for period 4 of this year (weeks 14 to 17, 3 to 30 August 2026) against fiscal weeks 14 to 17 of last year (28 July to 24 August 2025). Kuopio is back from its refit and counts; Savonlinna (closed) does not.",
         "leaves_out": "The web shop, store 999, week 53, the closed store and any store-week in a refit.",
         "docs": LFL_DOCS + ["Metric dictionary, 'Fiscal calendar' (compare week to week)"], "result_note": "This year's LFL sales, last year's, and the growth percentage."},
        naive=[Naive("fiscal_calendar", "date_aligned_last_year", shifted, "Takes last year's comparator as the same calendar dates (3 to 30 August 2025) instead of the same fiscal weeks, which starts it six days late."),
               Naive("company_definition", "total_company_growth", lfl_naive_total_company_sql("FY2026/27", "FY2025/26", 14, 17),
                     "Reports the growth of total company net sales, web included, which is not like-for-like: the web shop grows much faster than the stores.")])


# ---------------------------------------------------------------------------
# Pattern 3
# ---------------------------------------------------------------------------

@question("C1")
def c1() -> Question:
    """Garden and Electrical net sales and gross margin % for P6 of last year (FY2025/26), categories as-is."""
    cols = [col("category", "dimension", "text"), col("net_sales", "measure", "eur"), col("gross_margin_pct", "measure", "pct")]

    def sql(product_join, events=NET_WITH_DISPATCH):
        return f"""{events}
SELECT cp.category, ROUND(SUM(n.net_sales), 2) AS net_sales, ROUND(100.0 * SUM(n.net_sales - n.cost) / SUM(n.net_sales), 2) AS gross_margin_pct
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date {product_join}
WHERE d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 6 AND cp.category IN ('Garden', 'Electrical')
GROUP BY 1 ORDER BY 1;"""

    reference = sql(AS_IS_PRODUCT)
    as_was = sql(AS_WAS_PRODUCT)
    before_returns = f"""WITH {WEB_DISPATCH}
SELECT cp.category, ROUND(SUM(f.net_amount), 2) AS net_sales, ROUND(100.0 * SUM(f.net_amount - f.standard_cost) / SUM(f.net_amount), 2) AS gross_margin_pct
FROM fact_sales_line f
JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
JOIN dim_date d ON d.calendar_date = COALESCE(w.dispatch_date, f.sale_date)
WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
  AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 6 AND cp.category IN ('Garden', 'Electrical')
GROUP BY 1 ORDER BY 1;"""

    def pandas_fn(world):
        e = world.events()
        e = e[(e.fy == "FY2025/26") & (e.period == 6) & e.category.isin(["Garden", "Electrical"])]
        g = e.groupby("category")[["net_c", "cost_c"]].sum()
        return pd.DataFrame({"category": g.index, "net_sales": g.net_c.values / 100.0,
                             "gross_margin_pct": 100.0 * (g.net_c.values - g.cost_c.values) / g.net_c.values})

    return Question(
        "C1", 3, cols, reference, pandas_fn,
        {"counts": "Net sales and gross margin percentage for Garden and Electrical in period 6 of last year (22 September to 26 October 2025). Both are after returns, with returned units credited back at standard cost. Categories are today's: the outdoor lighting range, which sat in Garden until 27 October 2025, is counted in Electrical for the whole period.",
         "leaves_out": "Store 999 and test articles. Web on its dispatch date.",
         "docs": ["Metric dictionary, 'Gross margin', 'Net sales' and 'Hierarchies and stores' (as-is)", "Data quality register, 'outdoor lighting subcategory moved from Garden to Electrical'"],
         "result_note": "Two rows, Garden and Electrical."},
        naive=[Naive("scd", "as_was_category", as_was, "Uses the category each article had on the day of sale. In period 6 the outdoor lighting range was still in Garden, so Garden is too big and Electrical too small."),
               Naive("company_definition", "margin_before_returns", before_returns, "Counts sales and margin before returns, instead of after returns with the returned units credited back at standard cost.")])


@question("C2")
def c2() -> Question:
    """Garden and Electrical net sales for P8 of last year against P8 the year before, categories as-is."""
    ty = "d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 8"
    ly = "d.fiscal_year = 'FY2024/25' AND d.fiscal_period = 8"
    extra = "AND cp.category IN ('Garden', 'Electrical')"
    reference = yoy_sql("cp.category", "category", ty, ly, AS_IS_PRODUCT, where_extra=extra)
    as_was = yoy_sql("cp.category", "category", ty, ly, AS_WAS_PRODUCT, where_extra=extra)
    shifted = yoy_sql("cp.category", "category", ty, "n.business_date BETWEEN DATE '2024-11-24' AND DATE '2024-12-21'", AS_IS_PRODUCT, where_extra=extra)

    def pandas_fn(world):
        e = world.events()
        e = e[e.category.isin(["Garden", "Electrical"]) & (e.period == 8)]
        return yoy_frame(e[e.fy == "FY2025/26"].groupby("category").net_c.sum(), e[e.fy == "FY2024/25"].groupby("category").net_c.sum(), "category")

    def c2_moved_fn(world):
        e = world.events().copy()
        e["category"] = e.category.where(e.subcategory != "Outdoor Lighting", "Electrical")
        e = e[e.category.isin(["Garden", "Electrical"]) & (e.period == 8)]
        return yoy_frame(e[e.fy == "FY2025/26"].groupby("category").net_c.sum(), e[e.fy == "FY2024/25"].groupby("category").net_c.sum(), "category")

    return Question(
        "C2", 3, [col("category", "dimension", "text"), col("net_sales_ty", "measure", "eur"), col("net_sales_ly", "measure", "eur"), col("growth_pct", "measure", "pct")],
        reference, pandas_fn,
        {"counts": "Net sales (after returns, web on dispatch date) for Garden and Electrical in period 8 of last year (24 November to 21 December 2025), against period 8 the year before (25 November to 22 December 2024). Categories are today's, so the outdoor lighting range is in Electrical in both years.",
         "leaves_out": "Store 999 and test articles.",
         "docs": ["Metric dictionary, 'Net sales', 'Fiscal calendar' (week-aligned) and 'Hierarchies and stores' (as-is)", "Data quality register, outdoor lighting move"],
         "result_note": "Two rows, with growth."},
        naive=[Naive("scd", "as_was_category", as_was, "Uses the category on the day of sale, so the outdoor lighting range sits in Garden in the year before and in Electrical last year. Both categories then show a false jump or fall."),
               Naive("fiscal_calendar", "date_aligned_last_year", shifted, "Compares with 24 November to 21 December 2024, one day off the fiscal period, which moves the big pre-Christmas days in or out.")],
        alternatives=[{"label": "the whole Outdoor Lighting subcategory counted in Electrical, including the five delisted articles that never got a new version",
                       "sql": yoy_sql(MOVED_CATEGORY, "category", ty, ly, AS_IS_PRODUCT, where_extra=f"AND ({MOVED_CATEGORY}) IN ('Garden', 'Electrical')"),
                       "pandas_fn": c2_moved_fn}])


@question("C4")
def c4() -> Question:
    """Garden net sales per period for FY2024/25 P7-P12, as-was categories (override)."""
    cols = [col("fiscal_period", "dimension", "count"), col("garden_net_sales", "measure", "eur")]

    def sql(product_join):
        return f"""{NET_WITH_DISPATCH}
SELECT d.fiscal_period, ROUND(SUM(n.net_sales), 2) AS garden_net_sales
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date {product_join}
WHERE d.fiscal_year = 'FY2024/25' AND d.fiscal_period BETWEEN 7 AND 12 AND cp.category = 'Garden'
GROUP BY 1 ORDER BY 1;"""

    def pandas_fn(world):
        e = world.events()
        e = e[(e.fy == "FY2024/25") & e.period.between(7, 12) & (e.category_was == "Garden")]
        out = (e.groupby("period").net_c.sum() / 100.0).rename("garden_net_sales")
        out.index.name = "fiscal_period"
        return out.reset_index()

    return Question(
        "C4", 3, cols, sql(AS_WAS_PRODUCT), pandas_fn,
        {"counts": "Garden net sales for each period of the second half of FY2024/25 (periods 7 to 12, late October 2024 to late April 2025), with Garden as it was reported at the time, because the request asks for that. The outdoor lighting range was in Garden throughout that year.",
         "leaves_out": "Store 999 and test articles. Web on its dispatch date.",
         "docs": ["Team notes, 'explicitly asks' rule", "Metric dictionary, 'Hierarchies and stores' (as-was)", "Data quality register, outdoor lighting move"],
         "result_note": "Six rows, one per period."},
        naive=[Naive("override", "as_is_category_default", sql(AS_IS_PRODUCT), "Uses today's categories (the company default) although the request asks for them as they were. The outdoor lighting range, which sold best in autumn, is missing from Garden.")])


@question("C3")
def c3() -> Question:
    """Clean: units of one SKU sold at Oulu Kaakkuri last week (week 22)."""
    return _clean_units_sku()


def _clean_units_sku() -> Question:
    sku, store_id = cfg.CLEAN_SKU_UNITS_SKU, cfg.CLEAN_SKU_UNITS_STORE
    sql = f"""SELECT SUM(f.quantity) AS units_sold
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
WHERE s.store_id = {store_id} AND p.sku = {sku} AND f.sale_date BETWEEN DATE '2026-09-28' AND DATE '2026-10-04';"""
    sloppy = f"""SELECT SUM(f.quantity) AS units_sold
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product cp ON cp.sku = {sku} AND cp.is_current
WHERE s.store_id = {store_id} AND f.product_key IN (SELECT product_key FROM dim_product WHERE sku = {sku})
  AND f.sale_date >= DATE '2026-09-28' AND f.sale_date <= DATE '2026-10-04' AND s.store_id < 999;"""

    def pandas_fn(world):
        s = world.sales
        mask = (s.store_id == store_id) & (s.sku == sku) & (s.sale_date >= pd.Timestamp("2026-09-28")) & (s.sale_date <= pd.Timestamp("2026-10-04"))
        return pd.DataFrame({"units_sold": [int(s[mask].quantity.sum())]})

    return Question(
        "C3", 3, [col("units_sold", "measure", "count")], sql, pandas_fn,
        {"counts": f"Units on the sales lines of SKU {sku} at one store (store {store_id}) in the last completed week, week 22 (28 September to 4 October 2026).",
         "leaves_out": "Nothing: a single store, a single article, and every sale line counts.",
         "docs": ["Schema comments (fact_sales_line.quantity)"], "result_note": "One number."},
        invariance_sql=[sloppy])


@question("C13")
def c13() -> Question:
    """Clean: units of Cleaning Products sold at Hyvinkää in P5 this year."""
    sql = """SELECT SUM(f.quantity) AS units_sold
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
JOIN dim_date d ON d.calendar_date = f.sale_date
WHERE s.store_id = 107 AND p.subcategory = 'Cleaning Products' AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 5;"""
    sloppy = """SELECT SUM(f.quantity) AS units_sold
FROM fact_sales_line f JOIN dim_store cs ON cs.store_key = f.store_key AND cs.store_id = 107
JOIN dim_product p ON p.product_key = f.product_key JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
WHERE cp.subcategory = 'Cleaning Products' AND f.sale_date BETWEEN DATE '2026-08-31' AND DATE '2026-09-27';"""

    def pandas_fn(world):
        s = world.sales
        sub = s.sku.map(world.product_current["subcategory"])
        mask = (s.store_id == 107) & (sub == "Cleaning Products") & (s.sale_date >= pd.Timestamp("2026-08-31")) & (s.sale_date <= pd.Timestamp("2026-09-27"))
        return pd.DataFrame({"units_sold": [int(s[mask].quantity.sum())]})

    return Question(
        "C13", 3, [col("units_sold", "measure", "count")], sql, pandas_fn,
        {"counts": "Units on the sales lines of the Cleaning Products subcategory at Hyvinkää (store 107) in period 5 of this year (31 August to 27 September 2026).",
         "leaves_out": "Nothing: one store, so no web, no training store and no test articles.", "docs": ["Schema comments"], "result_note": "One number."},
        invariance_sql=[sloppy])


@question("C1X")
def c1x() -> Question:
    """Clean twin pair: units of Interior Paint sold at Lahti in P3 this year."""
    sql = """SELECT SUM(f.quantity) AS units_sold
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
JOIN dim_date d ON d.calendar_date = f.sale_date
WHERE s.store_id = 108 AND p.subcategory = 'Interior Paint' AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 3;"""
    sloppy = """SELECT SUM(f.quantity) AS units_sold
FROM fact_sales_line f JOIN dim_store cs ON cs.store_key = f.store_key AND cs.store_id = 108
JOIN dim_product p ON p.product_key = f.product_key JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
WHERE cp.subcategory = 'Interior Paint' AND f.sale_date BETWEEN DATE '2026-06-29' AND DATE '2026-08-02';"""

    def pandas_fn(world):
        s = world.sales
        sub = s.sku.map(world.product_current["subcategory"])
        mask = (s.store_id == 108) & (sub == "Interior Paint") & (s.sale_date >= pd.Timestamp("2026-06-29")) & (s.sale_date <= pd.Timestamp("2026-08-02"))
        return pd.DataFrame({"units_sold": [int(s[mask].quantity.sum())]})

    return Question(
        "C1X", 3, [col("units_sold", "measure", "count")], sql, pandas_fn,
        {"counts": "Units on the sales lines of the Interior Paint subcategory at Lahti (store 108) in period 3 of this year (29 June to 2 August 2026).",
         "leaves_out": "Nothing: one store, so no web, no training store and no test articles.", "docs": ["Schema comments"], "result_note": "One number."},
        invariance_sql=[sloppy])


# ---------------------------------------------------------------------------
# Pattern 4: returns
# ---------------------------------------------------------------------------

def return_rate_sql(group_expr: str, group_name: str, fiscal_cond: str, extra_where: str, product_join: str, cohort: bool = True,
                    format_join: str = "") -> str:
    """Return rate on the sale-week cohort (cohort=True) or, for the naive variant, by the return date."""
    if cohort:
        returned = f"""returned AS (
    SELECT {group_expr} AS grp, SUM(r.refund_net) AS returned_net
    FROM fact_return_line r
    JOIN fact_sales_line f ON f.sales_line_id = r.sales_line_id
    JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key {product_join} {format_join}
    JOIN dim_date d ON d.calendar_date = f.sale_date
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test' AND {fiscal_cond} {extra_where}
    GROUP BY 1
)"""
    else:
        returned = f"""returned AS (
    -- returns counted in the period they were booked
    SELECT {group_expr} AS grp, SUM(r.refund_net) AS returned_net
    FROM fact_return_line r
    JOIN fact_sales_line f ON f.sales_line_id = r.sales_line_id
    JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key {product_join} {format_join}
    JOIN dim_date d ON d.calendar_date = r.return_date
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test' AND {fiscal_cond} {extra_where}
    GROUP BY 1
)"""
    return f"""WITH sold AS (
    SELECT {group_expr} AS grp, SUM(f.net_amount) AS sold_net
    FROM fact_sales_line f
    JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key {product_join} {format_join}
    JOIN dim_date d ON d.calendar_date = f.sale_date
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test' AND {fiscal_cond} {extra_where}
    GROUP BY 1
),
{returned}
SELECT sold.grp AS {group_name}, ROUND(sold.sold_net, 2) AS sold_net, ROUND(COALESCE(returned.returned_net, 0), 2) AS returned_net,
       ROUND(100.0 * COALESCE(returned.returned_net, 0) / sold.sold_net, 2) AS return_rate_pct
FROM sold LEFT JOIN returned USING (grp) ORDER BY 1;"""


def _without_outdoor_lighting(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame.subcategory != "Outdoor Lighting"].reset_index(drop=True)


@question("R4b")
def r4b() -> Question:
    """Return rate by Garden subcategory for goods sold in Q1 of last year (FY2025/26), categories as-is."""
    cond = "d.fiscal_year = 'FY2025/26' AND d.fiscal_quarter = 1"
    reference = return_rate_sql("cp.subcategory", "subcategory", cond, "AND cp.category = 'Garden'", "JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current")
    as_was = return_rate_sql("p.subcategory", "subcategory", cond, "AND p.category = 'Garden'", "")
    by_return_date = return_rate_sql("cp.subcategory", "subcategory", cond, "AND cp.category = 'Garden'",
                                     "JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current", cohort=False)

    def pandas_fn(world):
        sales = world.in_scope_sales()
        sales = world.fiscal(sales, "sale_date")
        sales = sales[(sales.fy == "FY2025/26") & (sales.quarter == 1) & (sales.current_category == "Garden")]
        returns = world.returns.merge(sales[["sales_line_id"]], on="sales_line_id")
        sold = sales.groupby("current_subcategory").net_c.sum()
        returned = returns.groupby("current_subcategory").refund_net_c.sum()
        frame = pd.DataFrame({"sold_net": sold / 100.0, "returned_net": (returned / 100.0).reindex(sold.index).fillna(0.0)})
        frame["return_rate_pct"] = 100.0 * frame.returned_net / frame.sold_net
        frame.index.name = "subcategory"
        return frame.reset_index()

    return Question(
        "R4b", 4, [col("subcategory", "dimension", "text"), col("sold_net", "measure", "eur"), col("returned_net", "measure", "eur"), col("return_rate_pct", "measure", "pct")],
        reference, pandas_fn,
        {"counts": "For goods sold in the first quarter of last year (28 April to 27 July 2025), the net value refunded divided by the net value sold, whenever the refund happened, by Garden subcategory. Garden is today's Garden, so the outdoor lighting range (now Electrical) is not a row.",
         "leaves_out": "Store 999 and test articles. Refunds are matched to the week of the original sale, not to the week they were paid out.",
         "docs": ["Metric dictionary, 'Returns and margin' (sale-week cohort) and 'Hierarchies and stores'", "Data quality register, 'Returns can arrive up to 30 days after a sale'"],
         "result_note": "One row per Garden subcategory."},
        naive=[Naive("company_definition", "return_date_convention", by_return_date, "Counts refunds in the period they were paid and divides by the sales of the same period, the net-sales convention, instead of matching refunds to the sale period."),
               Naive("scd", "as_was_category", as_was, "Uses the category the article had on the day of sale, so the outdoor lighting range still appears as a Garden subcategory.")],
        alternatives=[{"label": "the whole Outdoor Lighting subcategory counted in Electrical, so it is not a Garden row at all",
                       "sql": return_rate_sql("cp.subcategory", "subcategory", cond, "AND cp.category = 'Garden' AND cp.subcategory <> 'Outdoor Lighting'",
                                              "JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current"),
                       "pandas_fn": lambda world: _without_outdoor_lighting(pandas_fn(world))}])


@question("R4c")
def r4c() -> Question:
    """Return rate by store format for goods sold in P2 of last year (FY2025/26)."""
    cond = "d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 2"
    reference = return_rate_sql("s.format", "format", cond, "", "")
    by_return_date = return_rate_sql("s.format", "format", cond, "", "", cohort=False)
    stores_only = return_rate_sql("s.format", "format", cond, "AND s.store_id < 900", "")
    dispatch_cohort = f"""WITH {WEB_DISPATCH},
lines AS (
    SELECT f.sales_line_id, s.format, f.net_amount, COALESCE(w.dispatch_date, f.sale_date) AS cohort_date
    FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
),
in_cohort AS (SELECT l.* FROM lines l JOIN dim_date d ON d.calendar_date = l.cohort_date WHERE {cond}),
sold AS (SELECT format, SUM(net_amount) AS sold_net FROM in_cohort GROUP BY 1),
returned AS (SELECT c.format, SUM(r.refund_net) AS returned_net FROM fact_return_line r JOIN in_cohort c ON c.sales_line_id = r.sales_line_id GROUP BY 1)
SELECT sold.format, ROUND(sold.sold_net, 2) AS sold_net, ROUND(COALESCE(returned.returned_net, 0), 2) AS returned_net,
       ROUND(100.0 * COALESCE(returned.returned_net, 0) / sold.sold_net, 2) AS return_rate_pct
FROM sold LEFT JOIN returned USING (format) ORDER BY 1;"""

    def dispatch_fn(world):
        sales = world.fiscal(world.in_scope_sales(), "business_date")
        sales = sales[(sales.fy == "FY2025/26") & (sales.period == 2)].copy()
        sales["format"] = sales.store_key.map(world.store_by_key["format"])
        returns = world.returns.merge(sales[["sales_line_id", "format"]], on="sales_line_id")
        sold = sales.groupby("format").net_c.sum()
        returned = returns.groupby("format").refund_net_c.sum()
        frame = pd.DataFrame({"sold_net": sold / 100.0, "returned_net": (returned / 100.0).reindex(sold.index).fillna(0.0)})
        frame["return_rate_pct"] = 100.0 * frame.returned_net / frame.sold_net
        frame.index.name = "format"
        return frame.reset_index()

    def pandas_fn(world):
        sales = world.fiscal(world.in_scope_sales(), "sale_date")
        sales = sales[(sales.fy == "FY2025/26") & (sales.period == 2)].copy()
        sales["format"] = sales.store_key.map(world.store_by_key["format"])
        returns = world.returns.merge(sales[["sales_line_id", "format"]], on="sales_line_id")
        sold = sales.groupby("format").net_c.sum()
        returned = returns.groupby("format").refund_net_c.sum()
        frame = pd.DataFrame({"sold_net": sold / 100.0, "returned_net": (returned / 100.0).reindex(sold.index).fillna(0.0)})
        frame["return_rate_pct"] = 100.0 * frame.returned_net / frame.sold_net
        frame.index.name = "format"
        return frame.reset_index()

    return Question(
        "R4c", 4, [col("format", "dimension", "text"), col("sold_net", "measure", "eur"), col("returned_net", "measure", "eur"), col("return_rate_pct", "measure", "pct")],
        reference, pandas_fn,
        {"counts": "For goods sold in period 2 of last year (26 May to 22 June 2025), the net value refunded divided by the net value sold, by the format of the store that made the sale: Large, Medium, Small and Web (the web shop is its own format).",
         "leaves_out": "Store 999 and test articles. Refunds are matched to the week of the original sale, wherever and whenever they were paid out.",
         "docs": ["Metric dictionary, 'Returns and margin' (sale-week cohort)", "Data quality register, 'web returns sent by post are booked to the web shop'"],
         "result_note": "One row per format."},
        naive=[Naive("company_definition", "return_date_convention", by_return_date, "Counts refunds in the period they were paid and divides by sales in the same period, so refunds for goods bought before the period land in it and refunds still to come are missed.")],
        alternatives=[{"label": "stores only (three rows, no Web row), since store-level analyses cover the physical stores", "sql": stores_only,
                       "pandas_fn": lambda world: pandas_fn(world).query("format != 'Web'").reset_index(drop=True)},
                      {"label": "web sales placed in the cohort by their dispatch date instead of their order date", "sql": dispatch_cohort, "pandas_fn": dispatch_fn}])


@question("C12")
def c12() -> Question:
    """Clean: units of Garden Furniture returned (booked) during P4 this year."""
    sql = """SELECT SUM(r.quantity_returned) AS units_returned
FROM fact_return_line r JOIN dim_product p ON p.product_key = r.product_key
JOIN dim_date d ON d.calendar_date = r.return_date
WHERE p.subcategory = 'Garden Furniture' AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 4;"""
    sloppy = """SELECT SUM(r.quantity_returned) AS units_returned
FROM fact_return_line r JOIN dim_product p ON p.product_key = r.product_key JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
WHERE cp.subcategory = 'Garden Furniture' AND r.return_date BETWEEN DATE '2026-08-03' AND DATE '2026-08-30' AND r.store_key NOT IN (SELECT store_key FROM dim_store WHERE store_id = 999);"""

    def pandas_fn(world):
        r = world.returns
        mask = (r.current_subcategory == "Garden Furniture") & (r.return_date >= pd.Timestamp("2026-08-03")) & (r.return_date <= pd.Timestamp("2026-08-30"))
        return pd.DataFrame({"units_returned": [int(r[mask].qty.sum())]})

    return Question(
        "C12", 4, [col("units_returned", "measure", "count")], sql, pandas_fn,
        {"counts": "Units on return lines for the Garden Furniture subcategory with a return date in period 4 of this year (3 to 30 August 2026), wherever they were handed in, web shop included.",
         "leaves_out": "Nothing: the request is for units booked as returned in the period, whenever they were sold.",
         "docs": ["Schema comments (fact_return_line)"], "result_note": "One number."},
        invariance_sql=[sloppy])
