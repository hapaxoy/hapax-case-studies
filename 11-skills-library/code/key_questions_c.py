"""Reference queries, naive variants and pandas recomputations, part C: patterns 9 to 14 (Project 11, Phase 3)."""
from __future__ import annotations

from datetime import date

import pandas as pd

import config as cfg
from key_lib import DEDUPED_LINES, NET_EVENTS, NET_EVENTS_DEDUP, WEB_DISPATCH, hel
from key_types import Interpretation, Naive, Question, col, question
from key_questions_a import AS_IS_PRODUCT, AS_IS_STORE, AS_WAS_STORE, INC1_CAVEAT, NET_WITH_DISPATCH


# ---------------------------------------------------------------------------
# Pattern 9: campaigns
# ---------------------------------------------------------------------------

def _campaign_window(world, campaign_id: int, extra_days: int):
    campaign = world.dim_campaign.set_index("campaign_id").loc[campaign_id]
    return campaign.start_date, campaign.end_date + pd.Timedelta(days=extra_days)


def _member_spend(world, start, end, web_on_dispatch: bool) -> pd.Series:
    """Net sales before returns on member-linked lines in the window, by loyalty number."""
    keymap = world.dim_member.set_index("member_key").member_id
    lines = world.sales[world.sales.member_key.notna()]
    date_column = lines.business_date if web_on_dispatch else lines.sale_date
    lines = lines[(date_column >= start) & (date_column <= end)]
    return (lines.groupby(lines.member_key.map(keymap)).net_c.sum() / 100.0)


def _targeted_and_holdout(world, campaign_id: int):
    keymap = world.dim_member.set_index("member_key").member_id
    exposure = world.exposure[world.exposure.campaign_id == campaign_id]
    targeted = set(exposure.member_key.map(keymap))
    holdout = set(world.holdout[world.holdout.campaign_id == campaign_id].member_id)
    return targeted, holdout


def uplift_sql(campaign_id: int, extra_days: int, web_on_dispatch: bool = False, fan_out: bool = False, vs_everyone_else: bool = False) -> str:
    date_expr = "COALESCE(w.dispatch_date, f.sale_date)" if web_on_dispatch else "f.sale_date"
    spend = f"""WITH {WEB_DISPATCH},
camp AS (SELECT start_date, end_date + {extra_days} AS window_end FROM dim_campaign WHERE campaign_id = {campaign_id}),
targeted AS (
    SELECT DISTINCT m.member_id FROM fact_campaign_exposure e JOIN dim_member m ON m.member_key = e.member_key WHERE e.campaign_id = {campaign_id}
),
holdout AS (SELECT member_id FROM campaign_holdout WHERE campaign_id = {campaign_id}),
spend AS (
    SELECT m.member_id, SUM(f.net_amount) AS net
    FROM fact_sales_line f JOIN dim_member m ON m.member_key = f.member_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    CROSS JOIN camp
    WHERE {date_expr} BETWEEN camp.start_date AND camp.window_end
    GROUP BY 1
)"""
    holdout_mean = "(SELECT AVG(COALESCE(s.net, 0)) FROM holdout h LEFT JOIN spend s USING (member_id))"
    if vs_everyone_else:
        holdout_mean = ("(SELECT AVG(COALESCE(s.net, 0)) FROM (SELECT DISTINCT member_id FROM dim_member) a LEFT JOIN spend s USING (member_id) "
                        "WHERE a.member_id NOT IN (SELECT member_id FROM targeted))")
    if not fan_out:
        targeted_mean = "(SELECT AVG(COALESCE(s.net, 0)) FROM targeted t LEFT JOIN spend s USING (member_id))"
        return f"""{spend}
SELECT ROUND({targeted_mean}, 2) AS mean_net_targeted, ROUND({holdout_mean}, 2) AS mean_net_holdout,
       ROUND({targeted_mean} - {holdout_mean}, 2) AS uplift_eur;"""
    # naive: join the contact rows straight to the sales lines, so every contact repeats the member's spend
    fanned = f"""(SELECT SUM(f.net_amount) / COUNT(DISTINCT m.member_id)
         FROM fact_campaign_exposure e
         JOIN dim_member m ON m.member_key = e.member_key
         JOIN dim_member v ON v.member_id = m.member_id
         JOIN fact_sales_line f ON f.member_key = v.member_key
         CROSS JOIN camp
         WHERE e.campaign_id = {campaign_id} AND f.sale_date BETWEEN camp.start_date AND camp.window_end)"""
    return f"""{spend}
SELECT ROUND({fanned}, 2) AS mean_net_targeted, ROUND({holdout_mean}, 2) AS mean_net_holdout,
       ROUND({fanned} - {holdout_mean}, 2) AS uplift_eur;"""


def uplift_fn(campaign_id: int, extra_days: int, web_on_dispatch: bool = False):
    def fn(world):
        start, end = _campaign_window(world, campaign_id, extra_days)
        spend = _member_spend(world, start, end, web_on_dispatch)
        targeted, holdout = _targeted_and_holdout(world, campaign_id)
        mean_t = spend.reindex(list(targeted)).fillna(0.0).mean()
        mean_h = spend.reindex(list(holdout)).fillna(0.0).mean()
        return pd.DataFrame({"mean_net_targeted": [mean_t], "mean_net_holdout": [mean_h], "uplift_eur": [mean_t - mean_h]})
    return fn


UPLIFT_COLUMNS = [col("mean_net_targeted", "measure", "eur"), col("mean_net_holdout", "measure", "eur"), col("uplift_eur", "measure", "eur")]


@question("U9a")
def u9a() -> Question:
    return Question(
        # 16 Oct 2026: reference and alternative swapped. The company document dates web sales by dispatch date,
        # so that is the reference; the order-date reading stays accepted as the alternative.
        "U9a", 9, UPLIFT_COLUMNS, uplift_sql(15, 7, web_on_dispatch=True), uplift_fn(15, 7, web_on_dispatch=True),
        {"counts": "Campaign uplift for Black Week 2025 (campaign 15, 24 to 30 November 2025): the average spend per targeted member minus the average spend per held-out member, over the campaign window plus seven days (24 November to 7 December 2025). A targeted member is anyone with at least one contact in the campaign, counted once however many times they were contacted. Members with no spend count as zero. Spend is net sales before returns on the member's sales lines, with web sales on their dispatch date, as in net sales.",
         "leaves_out": "Members who were neither contacted nor held out. Returns.",
         "docs": ["Metric dictionary, 'Transactions, members and campaigns' (campaign uplift)", "Data quality register, 'fact_campaign_exposure has one row per contact' and 'Holdout members are never contacted'"],
         "result_note": "One row: the two averages and their difference."},
        naive=[Naive("fan_out", "contact_rows_joined_to_sales", uplift_sql(15, 7, fan_out=True),
                     "Joins the contact rows straight to the sales lines, so a member contacted three times has their spend counted three times, and members who did not spend vanish from the average."),
               Naive("company_definition", "compared_with_everyone_not_mailed", uplift_sql(15, 7, vs_everyone_else=True),
                     "Compares with every member who was not mailed instead of the holdout group, so members who never consented to marketing are in the comparison.")],
        alternatives=[{"label": "web sales on the order date", "sql": uplift_sql(15, 7),
                       "pandas_fn": uplift_fn(15, 7)}])


@question("U9b")
def u9b() -> Question:
    def sql(web_on_dispatch: bool, fan_out: bool) -> str:
        date_expr = "COALESCE(w.dispatch_date, f.sale_date)" if web_on_dispatch else "f.sale_date"
        if fan_out:
            return f"""SELECT COUNT(DISTINCT m.member_id) AS targeted_members, ROUND(SUM(f.net_amount), 2) AS net_sales
FROM fact_campaign_exposure e JOIN dim_member m ON m.member_key = e.member_key
JOIN dim_member v ON v.member_id = m.member_id JOIN fact_sales_line f ON f.member_key = v.member_key
WHERE e.campaign_id = 19 AND f.sale_date BETWEEN DATE '2026-05-04' AND DATE '2026-05-24';"""
        return f"""WITH {WEB_DISPATCH},
targeted AS (SELECT DISTINCT m.member_id FROM fact_campaign_exposure e JOIN dim_member m ON m.member_key = e.member_key WHERE e.campaign_id = 19)
SELECT (SELECT COUNT(*) FROM targeted) AS targeted_members, ROUND(SUM(f.net_amount), 2) AS net_sales
FROM fact_sales_line f JOIN dim_member m ON m.member_key = f.member_key LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
WHERE m.member_id IN (SELECT member_id FROM targeted) AND {date_expr} BETWEEN DATE '2026-05-04' AND DATE '2026-05-24';"""

    def fn_for(web_on_dispatch: bool):
        def fn(world):
            start, end = pd.Timestamp("2026-05-04"), pd.Timestamp("2026-05-24")
            spend = _member_spend(world, start, end, web_on_dispatch)
            targeted, _ = _targeted_and_holdout(world, 19)
            return pd.DataFrame({"targeted_members": [len(targeted)], "net_sales": [spend.reindex(list(targeted)).fillna(0.0).sum()]})
        return fn

    return Question(
        # 16 Oct 2026: reference and alternative swapped, as for U9a (web sales on the dispatch date, per the document).
        "U9b", 9, [col("targeted_members", "measure", "count"), col("net_sales", "measure", "eur")], sql(True, False), fn_for(True),
        {"counts": "How many members were contacted for the Spring Garden Launch 2026 mailing (campaign 19, counted once each however many contacts), and what those members spent between 4 and 24 May 2026, the campaign dates. Spend is net sales before returns on the members' sales lines, with web sales on their dispatch date, as in net sales.",
         "leaves_out": "Held-out members (never contacted), non-members, returns.",
         "docs": ["Data quality register, 'fact_campaign_exposure has one row per contact. Reduce to one row per member before joining to sales'"],
         "result_note": "One row: the number of members and their total spend."},
        naive=[Naive("fan_out", "contact_rows_joined_to_sales", sql(False, True), "Joins the contact rows straight to the sales lines, so each member's spend is repeated once per contact (about twice over).")],
        alternatives=[{"label": "web sales on the order date", "sql": sql(False, False), "pandas_fn": fn_for(False)}])


@question("C6")
def c6() -> Question:
    sql = "SELECT COUNT(*) AS holdout_members FROM campaign_holdout WHERE campaign_id = 15;"
    sloppy = "SELECT holdout_size AS holdout_members FROM dim_campaign WHERE campaign_name = 'Black Week 2025';"

    def pandas_fn(world):
        return pd.DataFrame({"holdout_members": [int((world.holdout.campaign_id == 15).sum())]})

    return Question(
        "C6", 9, [col("holdout_members", "measure", "count")], sql, pandas_fn,
        {"counts": "The number of members held back from the Black Week 2025 mailing (campaign 15), from the campaign's holdout list.",
         "leaves_out": "Nothing.", "docs": ["Data quality register, 'Holdout members (10% of each mailing list)'"], "result_note": "One number."},
        invariance_sql=[sloppy])


# ---------------------------------------------------------------------------
# Pattern 10: stock
# ---------------------------------------------------------------------------

def _stock_weeks(world, fy: str, period: int):
    stock = world.fiscal(world.stock, "week_ending_date")
    return stock[(stock.fy == fy) & (stock.period == period)]


@question("S1")
def s1() -> Question:
    base = """FROM fact_stock_week w JOIN dim_product p ON p.product_key = w.product_key JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
JOIN dim_date d ON d.calendar_date = w.week_ending_date
WHERE cp.category = 'Paint & Decorating' AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 3"""
    reference = f"""SELECT ROUND(AVG(weekly), 2) AS average_stock_value FROM (SELECT w.week_ending_date, SUM(w.closing_value) AS weekly {base} GROUP BY 1);"""
    summed = f"""SELECT ROUND(SUM(w.closing_value), 2) AS average_stock_value {base};"""
    per_row = f"""SELECT ROUND(AVG(w.closing_value), 2) AS average_stock_value {base};"""

    def pandas_fn(world):
        stock = _stock_weeks(world, "FY2026/27", 3)
        stock = stock[stock.sku.map(world.product_current["category"]) == "Paint & Decorating"]
        return pd.DataFrame({"average_stock_value": [stock.groupby("week_ending_date").closing_value_c.sum().mean() / 100.0]})

    return Question(
        "S1", 10, [col("average_stock_value", "measure", "eur")], reference, pandas_fn,
        {"counts": "The value of Paint & Decorating stock (at standard cost, all stores) at the end of each of the five weeks of period 3 this year (29 June to 2 August 2026), added across stores and products, then averaged over the five weeks.",
         "leaves_out": "The web shop (its stock is held in the central warehouse, which is not in the table).",
         "docs": ["Metric dictionary, 'Stock' (add across stores and products, never across weeks; average the weekly closings)", "Data quality register, 'Stock and returns'"],
         "result_note": "One number, in euros."},
        naive=[Naive("semi_additive", "sum_of_weekly_snapshots", summed, "Adds the five weekly snapshots together, which counts the same stock five times."),
               Naive("semi_additive", "average_of_rows", per_row, "Averages the stock value of each product-store line instead of the total held, which gives the typical value of one line, not the stock.")])


@question("S2")
def s2() -> Question:
    def sql(sold_filter: str, stock_where: str, divisor: str = "4.0") -> str:
        return f"""WITH stock AS (
    SELECT cp.category, SUM(w.closing_units) AS closing_units
    FROM fact_stock_week w JOIN dim_product p ON p.product_key = w.product_key JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
    WHERE {stock_where} GROUP BY 1
),
sold AS (
    SELECT cp.category, SUM(f.quantity) / {divisor} AS avg_weekly_units
    FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
    JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
    WHERE f.sale_date BETWEEN DATE '2026-08-24' AND DATE '2026-09-20' {sold_filter}
    GROUP BY 1
)
SELECT stock.category, ROUND(stock.closing_units / sold.avg_weekly_units, 2) AS weeks_of_cover
FROM stock JOIN sold USING (category) ORDER BY 1;"""

    reference = sql("AND s.store_id < 900", "w.week_ending_date = DATE '2026-09-27'")
    with_web = sql("AND s.store_id <> 999", "w.week_ending_date = DATE '2026-09-27'")
    summed = sql("AND s.store_id < 900", "w.week_ending_date BETWEEN DATE '2026-09-06' AND DATE '2026-09-27'")
    with_current_week = reference.replace("BETWEEN DATE '2026-08-24' AND DATE '2026-09-20'", "BETWEEN DATE '2026-08-31' AND DATE '2026-09-27'")
    assert with_current_week != reference

    def make_fn(include_web: bool, window=("2026-08-24", "2026-09-20")):
        def fn(world):
            stock = world.stock[world.stock.week_ending_date == pd.Timestamp("2026-09-27")]
            closing = stock.groupby(stock.sku.map(world.product_current["category"])).closing_units.sum()
            lines = world.sales
            scope = (lines.store_id != cfg.TRAINING_STORE_ID) if include_web else (lines.store_id < 900)
            lines = lines[scope & (lines.sale_date >= pd.Timestamp(window[0])) & (lines.sale_date <= pd.Timestamp(window[1]))]
            sold = lines.groupby(lines.sku.map(world.product_current["category"])).quantity.sum() / 4.0
            out = (closing / sold).dropna().rename("weeks_of_cover").round(10)
            out.index.name = "category"
            return out.reset_index()
        return fn

    return Question(
        "S2", 10, [col("category", "dimension", "text"), col("weeks_of_cover", "measure", "ratio")], reference, make_fn(False),
        {"counts": "For each category, the stock in all stores at the end of period 5 (Sunday 27 September 2026) divided by the average weekly units sold over the four weeks before it (24 August to 20 September 2026), with units counted on the store sales lines by sale date. Categories are today's.",
         "leaves_out": "Stock is the single closing snapshot, not an average. The web shop's stock is not in the table. Two other readings are also accepted without the answer naming them: web units counted in the denominator (the dictionary says only 'units on sales lines'), and the four weeks ending at the stock week (18 to 21) instead of the four before it (17 to 20).",
         "docs": ["Metric dictionary, 'Stock' (weeks of cover; never add across weeks)", "Data quality register, 'fact_stock_week ... only for the articles the store ranges'"],
         "result_note": "One row per category."},
        naive=[Naive("semi_additive", "stock_added_across_weeks", summed, "Adds the closing stock of the last four weeks together before dividing, which counts the same stock four times.")],
        alternatives=[{"label": "web units counted in the denominator", "sql": with_web, "pandas_fn": make_fn(True)},
                      {"label": "the four weeks ending at the stock week (18 to 21) in the denominator", "sql": with_current_week,
                       "pandas_fn": make_fn(False, ("2026-08-31", "2026-09-27"))}])


def west_stock_sql(dedupe: bool) -> str:
    source = ("(SELECT * FROM fact_stock_week QUALIFY row_number() OVER (PARTITION BY store_key, product_key, week_ending_date ORDER BY etl_loaded_at) = 1)"
              if dedupe else "fact_stock_week")
    return f"""WITH weekly AS (
    SELECT cp.category, w.week_ending_date, SUM(w.closing_value) AS v
    FROM {source} w
    JOIN dim_store s ON s.store_key = w.store_key JOIN dim_store cs ON cs.store_id = s.store_id AND cs.is_current
    JOIN dim_product p ON p.product_key = w.product_key JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
    JOIN dim_date d ON d.calendar_date = w.week_ending_date
    WHERE cs.region = 'West' AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 11
    GROUP BY 1, 2
)
SELECT category, ROUND(AVG(v), 2) AS average_stock_value FROM weekly GROUP BY 1 ORDER BY 1;"""


def west_stock_fn(world):
    stock = _stock_weeks(world, "FY2025/26", 11)
    stock = stock[stock.store_id.map(world.store_current["region"]) == "West"]
    weekly = stock.groupby([stock.sku.map(world.product_current["category"]).rename("category"), "week_ending_date"]).closing_value_c.sum()
    out = (weekly.groupby("category").mean() / 100.0).rename("average_stock_value")
    return out.reset_index()


@question("U3")
def u3() -> Question:
    return Question(
        "U3", 10, [col("category", "dimension", "text"), col("average_stock_value", "measure", "eur")], west_stock_sql(True), west_stock_fn,
        {"counts": "For each category, the stock value (standard cost) held in the West region's stores at the end of each of the four weeks of period 11 last year (23 February to 22 March 2026), added across stores and products, then averaged over the four weeks. West is today's West.",
         "leaves_out": "The web shop. In the published stock table the West region's snapshot for the week ending 8 March 2026 appears twice, so a plain total for that week is doubled.",
         "docs": ["Metric dictionary, 'Stock' (average the weekly closings)", "Data quality register, 'fact_stock_week has one row per store and article for each week-ending Sunday'"],
         "result_note": "One row per category."},
        naive=[Naive("semi_additive", "sum_of_weekly_snapshots", west_stock_sql(True).replace("ROUND(AVG(v), 2)", "ROUND(SUM(v), 2)"),
                     "Adds the four weekly snapshots together instead of averaging them, which counts the same stock four times.")],
        undocumented={"incident": "INC-3", "published_sql": west_stock_sql(False), "published_pandas_fn": west_stock_fn,
                      "what": "The West region's stock snapshot for the week ending 8 March 2026 was loaded twice, so every West store-article row for that week exists twice.",
                      "keywords": [["duplicate", "double", "twice", "repeated", "loaded two", "two copies", "dedup", "de-dup", "inflat", "overstat", "more than one row"], ["8 mar", "2026-03-08", "week 45", "p11", "march", "west", "snapshot", "week ending"]],
                      "example_pass": "The stock table has duplicate rows for the West region for the week ending 2026-03-08; the average is overstated unless they are removed.",
                      "example_fail": "Stock was averaged over the four weekly snapshots of period 11."})


@question("C7")
def c7() -> Question:
    sku, store_id = cfg.CLEAN_STOCK_SKU, cfg.CLEAN_STOCK_STORE
    sql = f"""SELECT w.closing_units FROM fact_stock_week w JOIN dim_store s ON s.store_key = w.store_key JOIN dim_product p ON p.product_key = w.product_key
WHERE s.store_id = {store_id} AND p.sku = {sku} AND w.week_ending_date = DATE '2026-10-04';"""
    sloppy = f"""SELECT w.closing_units FROM fact_stock_week w JOIN dim_store s ON s.store_key = w.store_key JOIN dim_product cp ON cp.sku = {sku} AND cp.is_current
JOIN dim_date d ON d.calendar_date = w.week_ending_date WHERE s.store_id = {store_id} AND w.product_key IN (SELECT product_key FROM dim_product WHERE sku = {sku})
AND d.fiscal_year = 'FY2026/27' AND d.fiscal_week = 22;"""

    def pandas_fn(world):
        stock = world.stock
        mask = (stock.store_id == store_id) & (stock.sku == sku) & (stock.week_ending_date == pd.Timestamp("2026-10-04"))
        return pd.DataFrame({"closing_units": [int(stock[mask].closing_units.iloc[0])]})

    return Question(
        "C7", 10, [col("closing_units", "measure", "count")], sql, pandas_fn,
        {"counts": f"The closing stock units of SKU {sku} at one store (store {store_id}) at the end of the last completed week, Sunday 4 October 2026: a single snapshot, so nothing is added up.",
         "leaves_out": "Nothing.", "docs": ["Schema comments (fact_stock_week.closing_units)"], "result_note": "One number."},
        invariance_sql=[sloppy])


# ---------------------------------------------------------------------------
# Pattern 11: top-N
# ---------------------------------------------------------------------------

def top_n_sql(inner_select: str, order_expr: str, n: int, extra_rows: int = 0) -> str:
    return f"{inner_select}\nORDER BY {order_expr}, 1\nLIMIT {n + extra_rows};"


@question("T1")
def t1() -> Question:
    def sql(store_join: str, time_filter: str, n: int = 10) -> str:
        return top_n_sql(f"""{NET_WITH_DISPATCH}
SELECT n.sku, ROUND(SUM(n.net_sales - n.cost), 2) AS gross_margin
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date {store_join}
WHERE cs.region = 'South' AND {time_filter}
GROUP BY 1""", "2 DESC", n)

    ty = "d.fiscal_year = 'FY2024/25' AND d.fiscal_quarter = 4"
    reference = sql(AS_IS_STORE, ty)

    def pandas_fn(world):
        e = world.events()
        e = e[(e.region == "South") & (e.fy == "FY2024/25") & (e.quarter == 4)]
        grouped = e.groupby("sku")[["net_c", "cost_c"]].sum()
        out = ((grouped.net_c - grouped.cost_c) / 100.0).rename("gross_margin").reset_index()
        return out.sort_values(["gross_margin", "sku"], ascending=[False, True]).head(10).reset_index(drop=True)

    return Question(
        "T1", 11, [col("sku", "dimension", "count"), col("gross_margin", "measure", "eur")], reference, pandas_fn,
        {"counts": "The ten products with the largest gross margin (net sales minus standard cost, both after returns) in the stores of the South region in Q4 of FY2024/25 (27 January to 27 April 2025). South is today's South: it includes Kouvola, which moved from East in April 2025, and not the five Capital Region stores that used to be South.",
         "leaves_out": "The web shop (its own region, Online), store 999, test articles.",
         "docs": ["Metric dictionary, 'Gross margin', 'Hierarchies and stores' (as-is)", "Data quality register, 'On 28 April 2025 the four regions ... became five'"],
         "result_note": "Ten products, largest margin first."},
        naive=[Naive("scd", "as_was_region", sql(AS_WAS_STORE, ty), "Uses the region each store had in early 2025, so the five stores that are now the Capital Region count as South and Kouvola does not."),
               Naive("fiscal_calendar", "calendar_quarter_four", sql(AS_IS_STORE, "n.business_date BETWEEN DATE '2024-10-01' AND DATE '2024-12-31'"),
                     "Reads Q4 as October to December 2024 instead of the fiscal Q4 (late January to late April 2025).")],
        ordered=True, top_n=10, tie_check_sql=sql(AS_IS_STORE, ty, 11))


@question("T2")
def t2() -> Question:
    def units_sql(time_filter: str, n: int = 10) -> str:
        return top_n_sql(f"""SELECT p.sku, SUM(f.quantity) AS metric_value
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
JOIN dim_date d ON d.calendar_date = f.sale_date
WHERE s.store_id <> 999 AND p.category <> 'ZZ Test' AND {time_filter}
GROUP BY 1""", "2 DESC", n)

    def net_sql(n: int = 10) -> str:
        return top_n_sql(f"""{NET_WITH_DISPATCH}
SELECT n.sku, ROUND(SUM(n.net_sales), 2) AS metric_value
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date
WHERE d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 5
GROUP BY 1""", "2 DESC", n)

    p5 = "d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 5"
    units_columns = [col("sku", "dimension", "count"), col("metric_value", "measure", "count")]
    net_columns = [col("sku", "dimension", "count"), col("metric_value", "measure", "eur")]

    def units_fn(world):
        s = world.fiscal(world.in_scope_sales(), "sale_date")
        s = s[(s.fy == "FY2026/27") & (s.period == 5)]
        out = s.groupby("sku").quantity.sum().rename("metric_value").reset_index()
        return out.sort_values(["metric_value", "sku"], ascending=[False, True]).head(10).reset_index(drop=True)

    def net_fn(world):
        e = world.events()
        e = e[(e.fy == "FY2026/27") & (e.period == 5)]
        out = (e.groupby("sku").net_c.sum() / 100.0).rename("metric_value").reset_index()
        return out.sort_values(["metric_value", "sku"], ascending=[False, True]).head(10).reset_index(drop=True)

    def units_dispatch_sql(n: int = 10) -> str:
        return top_n_sql(f"""WITH {WEB_DISPATCH}
SELECT p.sku, SUM(f.quantity) AS metric_value
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id JOIN dim_date d ON d.calendar_date = COALESCE(w.dispatch_date, f.sale_date)
WHERE s.store_id <> 999 AND p.category <> 'ZZ Test' AND {p5}
GROUP BY 1""", "2 DESC", n)

    def units_dispatch_fn(world):
        s = world.fiscal(world.in_scope_sales(), "business_date")
        s = s[(s.fy == "FY2026/27") & (s.period == 5)]
        out = s.groupby("sku").quantity.sum().rename("metric_value").reset_index()
        return out.sort_values(["metric_value", "sku"], ascending=[False, True]).head(10).reset_index(drop=True)

    def units_stores_fn(world):
        s = world.fiscal(world.in_scope_sales(), "sale_date")
        s = s[(s.fy == "FY2026/27") & (s.period == 5) & (s.store_id < 900)]
        out = s.groupby("sku").quantity.sum().rename("metric_value").reset_index()
        return out.sort_values(["metric_value", "sku"], ascending=[False, True]).head(10).reset_index(drop=True)

    unit_words = [["unit", "units", "quantity", "volume", "number sold", "pieces"]]
    return Question(
        "T2", 11, units_columns, units_sql(p5), units_fn,
        {"counts": "The request does not say what 'best-selling' means. Readings are accepted if the answer says which it used. Reading 1: the ten products with the most units sold in the last completed period, P5 (31 August to 27 September 2026), units counted on the sales lines by sale date. Reading 2: the ten products with the highest net sales (after returns, web on dispatch date) in the same period. Two variants of reading 1 are also accepted under the same 'units' wording: web units dated by dispatch date, and stores only.",
         "leaves_out": "Store 999 and test articles. 'Last period' is P5, the last complete period; P6 has only its first week.",
         "docs": ["Metric dictionary, 'Fiscal calendar' (last period) and 'Net sales'", "Team notes, 'Always filter out store 999 and category ZZ Test'"],
         "result_note": "Ten products for each reading."},
        naive=[Naive("fiscal_calendar", "partial_period_6", units_sql("d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 6"),
                     "Takes 'last period' as P6, the period that has only one week loaded so far, instead of the last completed period, P5.")],
        ordered=True, top_n=10, tie_check_sql=units_sql(p5, 11),
        interpretations=[
            Interpretation("units", "Most units sold", units_sql(p5), units_fn, units_columns,
                           [["unit", "units", "quantity", "volume", "number sold", "pieces"]], "I ranked best-sellers by units sold.", "I ranked by sales."),
            Interpretation("net_sales", "Highest net sales", net_sql(), net_fn, net_columns,
                           [["net sales", "revenue", "sales value", "value", "euro", "eur"]], "I ranked best-sellers by net sales value.", "I ranked by units."),
            Interpretation("units_web_on_dispatch_date", "Most units sold, web units dated by dispatch date", units_dispatch_sql(), units_dispatch_fn, units_columns,
                           unit_words, "I ranked best-sellers by units sold, web units on the dispatch date.", "I ranked by sales.", tie_check_sql=units_dispatch_sql(11)),
            Interpretation("units_stores_only", "Most units sold in the stores only", units_sql(p5 + " AND s.store_id < 900"), units_stores_fn, units_columns,
                           unit_words, "I ranked best-sellers by units sold in the stores.", "I ranked by sales.", tie_check_sql=units_sql(p5 + " AND s.store_id < 900", 11))])


@question("T5")
def t5() -> Question:
    reference = top_n_sql(f"""{NET_WITH_DISPATCH}
SELECT n.sku, ROUND(SUM(n.net_sales), 2) AS web_net_sales
FROM net_events n
WHERE n.store_id = 900 AND n.business_date >= DATE '2025-11-03'
GROUP BY 1""", "2 DESC", 10)
    tie = reference.replace("LIMIT 10", "LIMIT 11")
    channel_code = top_n_sql("""SELECT p.sku, ROUND(SUM(f.net_amount), 2) AS web_net_sales
FROM fact_sales_line f JOIN dim_product p ON p.product_key = f.product_key
WHERE f.channel_code = 'WB' AND f.sale_date >= DATE '2025-11-03'
GROUP BY 1""", "2 DESC", 10)

    def pandas_fn(world):
        e = world.events()
        e = e[(e.store_id == 900) & (e.date >= pd.Timestamp("2025-11-03"))]
        out = (e.groupby("sku").net_c.sum() / 100.0).rename("web_net_sales").reset_index()
        return out.sort_values(["web_net_sales", "sku"], ascending=[False, True]).head(10).reset_index(drop=True)

    return Question(
        "T5", 11, [col("sku", "dimension", "count"), col("web_net_sales", "measure", "eur")], reference, pandas_fn,
        {"counts": "The ten products with the highest web net sales (dispatch date, after returns booked to the web shop) from the platform migration on 3 November 2025 to the end of the data (4 October 2026). The web shop is found by its store number, 900.",
         "leaves_out": "Cancelled and unshipped orders, web test orders, refunds for web goods handed in at a store.",
         "docs": ["Data quality register, 'Web platform migration and the legacy view' (channel_code is not filled after 3 November 2025)"],
         "result_note": "Ten products, largest first."},
        naive=[Naive("migration", "channel_code_filter", channel_code, "Filters on channel_code = 'WB', which is empty from the migration date, so the result is empty.")],
        ordered=True, top_n=10, tie_check_sql=tie)


@question("C8")
def c8() -> Question:
    """Clean twin pair: top 3 products by units sold at Helsinki Pitäjänmäki (102) in P5 this year."""
    sql = top_n_sql("""SELECT p.sku, SUM(f.quantity) AS units_sold
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
JOIN dim_date d ON d.calendar_date = f.sale_date
WHERE s.store_id = 102 AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 5
GROUP BY 1""", "2 DESC", 3)
    tie = sql.replace("LIMIT 3", "LIMIT 4")
    sloppy = top_n_sql("""SELECT p.sku, SUM(f.quantity) AS units_sold
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key AND s.store_id = 102 JOIN dim_product p ON p.product_key = f.product_key
WHERE f.sale_date BETWEEN DATE '2026-08-31' AND DATE '2026-09-27'
GROUP BY 1""", "2 DESC", 3)

    def pandas_fn(world):
        s = world.sales
        s = s[(s.store_id == 102) & (s.sale_date >= pd.Timestamp("2026-08-31")) & (s.sale_date <= pd.Timestamp("2026-09-27"))]
        out = s.groupby("sku").quantity.sum().rename("units_sold").reset_index()
        return out.sort_values(["units_sold", "sku"], ascending=[False, True]).head(3).reset_index(drop=True)

    return Question(
        "C8", 11, [col("sku", "dimension", "count"), col("units_sold", "measure", "count")], sql, pandas_fn,
        {"counts": "The three products with the most units on the sales lines at Helsinki Pitäjänmäki (store 102) in period 5 of this year (31 August to 27 September 2026).",
         "leaves_out": "Nothing: one store, so no web, no training store and no test articles.", "docs": ["Schema comments"], "result_note": "Three products, best first."},
        invariance_sql=[sloppy], ordered=True, top_n=3, tie_check_sql=tie)


@question("C14")
def c14() -> Question:
    sql = top_n_sql("""SELECT cp.subcategory, SUM(f.quantity) AS units_sold
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current JOIN dim_date d ON d.calendar_date = f.sale_date
WHERE s.store_id = 118 AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 5
GROUP BY 1""", "2 DESC", 3)
    tie = sql.replace("LIMIT 3", "LIMIT 4")
    sloppy = top_n_sql("""SELECT p.subcategory, SUM(f.quantity) AS units_sold
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key AND s.store_id = 118 JOIN dim_product p ON p.product_key = f.product_key
WHERE f.sale_date BETWEEN DATE '2026-08-31' AND DATE '2026-09-27'
GROUP BY 1""", "2 DESC", 3)

    def pandas_fn(world):
        s = world.sales
        s = s[(s.store_id == 118) & (s.sale_date >= pd.Timestamp("2026-08-31")) & (s.sale_date <= pd.Timestamp("2026-09-27"))]
        out = s.groupby("current_subcategory").quantity.sum().rename("units_sold")
        out.index.name = "subcategory"
        return out.reset_index().sort_values(["units_sold", "subcategory"], ascending=[False, True]).head(3).reset_index(drop=True)

    return Question(
        "C14", 11, [col("subcategory", "dimension", "text"), col("units_sold", "measure", "count")], sql, pandas_fn,
        {"counts": "The three subcategories with the most units on the sales lines at Nokia (store 118) in period 5 of this year (31 August to 27 September 2026).",
         "leaves_out": "Nothing: one store, so no web, no training store and no test articles.", "docs": ["Schema comments"], "result_note": "Three subcategories, best first."},
        invariance_sql=[sloppy], ordered=True, top_n=3, tie_check_sql=tie)


# ---------------------------------------------------------------------------
# Pattern 12: league tables and biggest stores
# ---------------------------------------------------------------------------

def league_sql(fiscal_cond: str, events: str, scope_stores: bool = True, per: str = "trading") -> str:
    store_filter = "AND cs.store_id < 900" if scope_stores else ""
    day_filter = "AND pd.is_trading_day" if per == "trading" else ""
    event_filter = "n.store_id < 900 AND " if scope_stores else ""
    return f"""WITH {WEB_DISPATCH},
{events},
period_days AS (SELECT d.calendar_date, d.is_trading_day FROM dim_date d WHERE {fiscal_cond}),
trading AS (
    SELECT cs.store_id, COUNT(*) AS trading_days
    FROM dim_store cs CROSS JOIN period_days pd
    WHERE cs.is_current {store_filter} {day_filter}
      AND (cs.open_date IS NULL OR cs.open_date <= pd.calendar_date) AND (cs.close_date IS NULL OR cs.close_date >= pd.calendar_date)
      AND NOT EXISTS (SELECT 1 FROM ref_store_closure c WHERE c.store_id = cs.store_id AND pd.calendar_date BETWEEN c.closure_start_date AND c.closure_end_date)
    GROUP BY 1
),
sales AS (
    SELECT n.store_id, SUM(n.net_sales) AS net_sales
    FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date
    WHERE {event_filter}{fiscal_cond}
    GROUP BY 1
)
SELECT t.store_id, t.trading_days, ROUND(s.net_sales, 2) AS net_sales, ROUND(s.net_sales / t.trading_days, 2) AS net_sales_per_trading_day
FROM trading t JOIN sales s USING (store_id)
ORDER BY 4 DESC, 1;"""


def league_fn(fy: str, period: int):
    def fn(world):
        calendar = world.calendar
        days = calendar[(calendar.fy == fy) & (calendar.period == period)].date
        trading_flag = world.dim_date.set_index("calendar_date").is_trading_day
        open_days = [d for d in days if bool(trading_flag[d])]
        refits = {}
        for store_id, start, end in cfg.REFITS:
            refits.setdefault(store_id, []).append((pd.Timestamp(start), pd.Timestamp(end)))
        rows = []
        events = world.events()
        events = events[(events.store_id < 900) & (events.fy == fy) & (events.period == period)]
        net = events.groupby("store_id").net_c.sum() / 100.0
        for store_id, _, _, _, _, _, opened, closed in cfg.STORES:
            count = 0
            for day in open_days:
                if opened is not None and day < pd.Timestamp(opened):
                    continue
                if closed is not None and day > pd.Timestamp(closed):
                    continue
                if any(start <= day <= end for start, end in refits.get(store_id, [])):
                    continue
                count += 1
            if count and store_id in net.index:
                rows.append((store_id, count, net[store_id], net[store_id] / count))
        out = pd.DataFrame(rows, columns=["store_id", "trading_days", "net_sales", "net_sales_per_trading_day"])
        return out.sort_values(["net_sales_per_trading_day", "store_id"], ascending=[False, True]).reset_index(drop=True)
    return fn


LEAGUE_COLUMNS = [col("store_id", "dimension", "count"), col("trading_days", "measure", "count"), col("net_sales", "measure", "eur"),
                  col("net_sales_per_trading_day", "measure", "eur")]


@question("G1")
def g1() -> Question:
    cond = "d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 5"
    return Question(
        "G1", 12, LEAGUE_COLUMNS, league_sql(cond, NET_EVENTS_DEDUP), league_fn("FY2025/26", 5),
        {"counts": "The store league table for period 5 of last year (25 August to 21 September 2025): each physical store's net sales (after returns) divided by its trading days, best first. Trading days are the days the store was open: after opening, before closure, outside a refit and not a closed holiday. Pori was in a refit from 8 September 2025, so it is listed on its first 14 days only.",
         "leaves_out": "The web shop, store 999, test articles. One store (Tampere Lielahti, 116) had a week of receipts posted twice in the published data; the table here counts each receipt once.",
         "docs": ["Metric dictionary, 'Hierarchies and stores' (store league table)", "Data quality register, 'Refit closures' and Team notes ('check the total against rpt_daily_store_sales')"],
         "result_note": "One row per store, ranked."},
        undocumented={"incident": "INC-1", "published_sql": league_sql(cond, NET_EVENTS), "published_pandas_fn": league_fn("FY2025/26", 5),
                      "what": "A till re-sync posted every receipt of Tampere Lielahti (116) for the week 15 to 21 September 2025 twice.",
                      "keywords": [["duplicate", "double", "twice", "repeated", "re-posted", "reposted", "posted two", "dupe", "inflat", "overstat", "more than once"], ["116", "lielahti", "week 21", "15 sep", "15-21", "21 sep", "tampere"]],
                      "example_pass": "Store 116 Tampere Lielahti has duplicate receipt lines in the week of 15 to 21 September 2025; its figure is overstated unless the duplicates are removed.",
                      "example_fail": "Net sales per trading day were computed from the sales lines and returns, excluding store 999."},
        ordered=True)


@question("G3")
def g3() -> Question:
    """League table for P2 of this year (twin pair)."""
    cond = "d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 2"
    return Question(
        "G3", 12, LEAGUE_COLUMNS, league_sql(cond, NET_EVENTS), league_fn("FY2026/27", 2),
        {"counts": "The store league table for period 2 of this year (1 to 28 June 2026): each physical store's net sales (after returns) divided by its trading days, best first. Midsummer Eve and Midsummer Day (19 and 20 June) are closed holidays and do not count as trading days, and Kuopio is listed on its first 14 days only because its refit started on 15 June.",
         "leaves_out": "The web shop, store 999, test articles, Savonlinna (closed since January 2026).",
         "docs": ["Metric dictionary, 'Hierarchies and stores' (store league table) and 'Fiscal calendar' (closed days)", "Data quality register, 'Refit closures'"],
         "result_note": "One row per store, ranked."},
        naive=[Naive("exclusions", "calendar_days_not_trading_days", league_sql(cond, NET_EVENTS, per="calendar"),
                     "Divides by calendar days instead of trading days, so closed holidays and (for Kuopio) the refit days are counted as days the store could sell."),
               Naive("exclusions", "no_store_scope", league_sql(cond, NET_EVENTS, scope_stores=False),
                     "Does not limit the table to physical stores, so the web shop is ranked as if it were a store.")],
        ordered=True,
        alternatives=[{"label": "the same table ranked by total net sales instead of net sales per trading day ('store ranking' is not the defined league table)",
                       "sql": league_sql(cond, NET_EVENTS).replace("ORDER BY 4 DESC, 1;", "ORDER BY 3 DESC, 1;"),
                       "pandas_fn": lambda world: league_fn("FY2026/27", 2)(world).sort_values(["net_sales", "store_id"], ascending=[False, True]).reset_index(drop=True)}],
        alternatives_ordered_by={"the same table ranked by total net sales instead of net sales per trading day ('store ranking' is not the defined league table)": "net_sales desc"})


@question("G2")
def g2() -> Question:
    """Which are our biggest stores? Two accepted readings."""
    ytd = "d.fiscal_year = 'FY2026/27' AND d.fiscal_week <= 22"

    fy_last = "d.fiscal_year = 'FY2025/26'"
    trailing_52 = "n.business_date BETWEEN DATE '2025-10-05' AND DATE '2026-10-04'"   # the 52 weeks ending Sunday 4 October 2026

    def sales_sql(scope: str, n: int = 10, condition: str = ytd, events: str = NET_EVENTS) -> str:
        return top_n_sql(f"""WITH {WEB_DISPATCH},
{events}
SELECT n.store_id, ROUND(SUM(n.net_sales), 2) AS metric_value
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date
WHERE {scope}{condition}
GROUP BY 1""", "2 DESC", n)

    def sqm_sql(n: int = 10) -> str:
        return top_n_sql("""SELECT store_id, sqm AS metric_value FROM dim_store WHERE is_current AND store_id < 900 AND close_date IS NULL""", "2 DESC", n).replace(
            "\nORDER BY 2 DESC, 1", "\nORDER BY 2 DESC, 1")

    sales_cols = [col("store_id", "dimension", "count"), col("metric_value", "measure", "eur")]
    sqm_cols = [col("store_id", "dimension", "count"), col("metric_value", "measure", "count")]

    def sales_fn(world):
        e = world.events()
        e = e[(e.store_id < 900) & (e.fy == "FY2026/27") & (e.week <= 22)]
        out = (e.groupby("store_id").net_c.sum() / 100.0).rename("metric_value").reset_index()
        return out.sort_values(["metric_value", "store_id"], ascending=[False, True]).head(10).reset_index(drop=True)

    def fy_last_fn(world):
        e = world.events()
        e = e[(e.store_id < 900) & (e.fy == "FY2025/26")]
        out = (e.groupby("store_id").net_c.sum() / 100.0).rename("metric_value").reset_index()
        return out.sort_values(["metric_value", "store_id"], ascending=[False, True]).head(10).reset_index(drop=True)

    def trailing_fn(world):
        e = world.events()
        e = e[(e.store_id < 900) & (e.date >= pd.Timestamp("2025-10-05")) & (e.date <= pd.Timestamp("2026-10-04"))]
        out = (e.groupby("store_id").net_c.sum() / 100.0).rename("metric_value").reset_index()
        return out.sort_values(["metric_value", "store_id"], ascending=[False, True]).head(10).reset_index(drop=True)

    def sqm_fn(world):
        current = world.dim_store[world.dim_store.is_current & (world.dim_store.store_id < 900) & world.dim_store.close_date.isna()]
        out = current[["store_id", "sqm"]].rename(columns={"sqm": "metric_value"})
        return out.sort_values(["metric_value", "store_id"], ascending=[False, True]).head(10).reset_index(drop=True)

    return Question(
        "G2", 12, sales_cols, sales_sql("n.store_id < 900 AND "), sales_fn,
        {"counts": "The request does not say what 'biggest' means. Readings are accepted if the answer says which it used. Reading 1: the ten physical stores with the highest net sales so far this fiscal year (weeks 1 to 22, 4 May to 4 October 2026). Reading 2: the ten stores trading today with the largest sales area in square metres. Reading 3: highest net sales over the last full fiscal year, FY2025/26. Reading 4: highest net sales over the trailing 52 weeks to 4 October 2026. Reading 3 includes Tampere Lielahti's double-posted week, so it has two accepted outcomes: the corrected figures, or the published figures with the duplicates named in the caveats.",
         "leaves_out": "The web shop is not a store, store 999 is never included, and Savonlinna (closed) is not trading.",
         "docs": ["Metric dictionary, 'Hierarchies and stores' (store counts and store-level analyses cover physical stores only)"],
         "result_note": "Ten stores for each reading."},
        naive=[Naive("exclusions", "web_shop_ranked_as_store", sales_sql(""), "Ranks the web shop (store 900) alongside the physical stores, and it comes first.")],
        ordered=True, top_n=10, tie_check_sql=sales_sql("n.store_id < 900 AND ", 11),
        interpretations=[
            Interpretation("net_sales", "Highest net sales this year to date", sales_sql("n.store_id < 900 AND "), sales_fn, sales_cols,
                           [["net sales", "sales", "revenue", "turnover"]], "I ranked stores by net sales so far this year.", "I took biggest to mean the best-known stores."),
            Interpretation("sales_area", "Largest sales area (square metres)", sqm_sql(), sqm_fn, sqm_cols,
                           [["sqm", "square", "area", "m2", "floor space", "size"]], "I took biggest to mean sales area in square metres.", "I took biggest to mean the best-known stores."),
            Interpretation("net_sales_last_fiscal_year", "Highest net sales over the last full fiscal year (FY2025/26)",
                           sales_sql("n.store_id < 900 AND ", condition=fy_last, events=NET_EVENTS_DEDUP), fy_last_fn, sales_cols,
                           [["net sales", "sales", "revenue", "turnover"], ["last year", "fy2025/26", "fy25/26", "2025/26", "last fiscal year", "last full"]],
                           "I ranked stores by net sales over last fiscal year, FY2025/26.", "I took biggest to mean the best-known stores.",
                           published_sql=sales_sql("n.store_id < 900 AND ", condition=fy_last), published_pandas_fn=fy_last_fn,
                           caveat_keywords=INC1_CAVEAT["keywords"], caveat_pass=INC1_CAVEAT["pass"], caveat_fail=INC1_CAVEAT["fail"],
                           tie_check_sql=sales_sql("n.store_id < 900 AND ", 11, fy_last, NET_EVENTS_DEDUP)),
            Interpretation("net_sales_trailing_52_weeks", "Highest net sales over the trailing 52 weeks (5 October 2025 to 4 October 2026)",
                           sales_sql("n.store_id < 900 AND ", condition=trailing_52), trailing_fn, sales_cols,
                           [["net sales", "sales", "revenue", "turnover"], ["52 weeks", "trailing", "rolling", "12 months", "twelve months", "past year", "last 12"]],
                           "I ranked stores by net sales over the trailing 52 weeks.", "I took biggest to mean the best-known stores.",
                           tie_check_sql=sales_sql("n.store_id < 900 AND ", 11, trailing_52))])


# ---------------------------------------------------------------------------
# Pattern 13: new members
# ---------------------------------------------------------------------------

@question("N1")
def n1() -> Question:
    window = "m.join_date BETWEEN DATE '2025-04-28' AND DATE '2026-05-03'"
    reference = f"""SELECT m.home_store_id AS store_id, COUNT(*) AS new_members
FROM dim_member m
WHERE {window} AND m.valid_from = (SELECT MIN(x.valid_from) FROM dim_member x WHERE x.member_id = m.member_id)
GROUP BY 1 ORDER BY 1;"""
    current_home = f"""SELECT m.home_store_id AS store_id, COUNT(DISTINCT m.member_id) AS new_members
FROM dim_member m WHERE {window} AND m.is_current GROUP BY 1 ORDER BY 1;"""
    all_versions = f"""SELECT m.home_store_id AS store_id, COUNT(*) AS new_members FROM dim_member m WHERE {window} GROUP BY 1 ORDER BY 1;"""

    def pandas_fn(world):
        first = world.dim_member.sort_values(["member_id", "valid_from"]).drop_duplicates("member_id", keep="first")
        first = first[(first.join_date >= pd.Timestamp("2025-04-28")) & (first.join_date <= pd.Timestamp("2026-05-03"))]
        out = first.groupby("home_store_id").member_id.nunique().rename("new_members")
        out.index.name = "store_id"
        return out.reset_index()

    return Question(
        "N1", 13, [col("store_id", "dimension", "count"), col("new_members", "measure", "count")], reference, pandas_fn,
        {"counts": "New loyalty members by store for last fiscal year (28 April 2025 to 3 May 2026): each member counted once, on their join date, at the home store they had when they enrolled. Online sign-ups appear under store 900.",
         "leaves_out": "Members who joined before or after the year. A later change of home store (a member who moved to another store, or whose store closed) does not move the sign-up.",
         "docs": ["Metric dictionary, 'Transactions, members and campaigns' (new member)", "Data quality register, 'dim_member gets a new version when a member's tier, home store or marketing consent changes'"],
         "result_note": "One row per store (and one for online sign-ups)."},
        naive=[Naive("company_definition", "current_home_store", current_home, "Uses the member's home store today, so a member who enrolled at Savonlinna and was moved to Mikkeli when it closed counts as a Mikkeli sign-up."),
               Naive("fan_out", "count_member_versions", all_versions, "Counts rows in the member table instead of members, so anyone with more than one version (a tier or consent change) is counted more than once.")])


def _join_date_question(qid: str, join_date: date) -> Question:
    day = join_date.isoformat()
    sql = f"SELECT COUNT(DISTINCT member_id) AS new_members FROM dim_member WHERE join_date = DATE '{day}';"
    sloppy = f"SELECT COUNT(*) AS new_members FROM dim_member WHERE join_date = DATE '{day}';"

    def pandas_fn(world):
        return pd.DataFrame({"new_members": [int(world.dim_member[world.dim_member.join_date == pd.Timestamp(day)].member_id.nunique())]})

    return Question(
        qid, 13, [col("new_members", "measure", "count")], sql, pandas_fn,
        {"counts": f"Loyalty members whose join date is {join_date.day} {join_date.strftime('%B %Y')}, counted once each by loyalty number.",
         "leaves_out": "Nothing. Everyone who joined that day still has a single version row, so no counting trap applies.",
         "docs": ["Schema comments (dim_member.join_date)"], "result_note": "One number."},
        invariance_sql=[sloppy])


@question("C10")
def c10() -> Question:
    return _join_date_question("C10", cfg.CLEAN_JOIN_DATES[0])


@question("C11")
def c11() -> Question:
    return _join_date_question("C11", cfg.CLEAN_JOIN_DATES[1])


# ---------------------------------------------------------------------------
# Pattern 14: VAT-inclusive figures
# ---------------------------------------------------------------------------

STORE_LINES = """FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
WHERE s.store_id < 900 AND p.category <> 'ZZ Test'"""


@question("V1")
def v1() -> Question:
    def sql(expr: str) -> str:
        return f"""SELECT ROUND(SUM(CASE WHEN f.sale_date BETWEEN DATE '2024-08-01' AND DATE '2024-08-31' THEN {expr} ELSE 0 END), 2) AS gross_incl_vat_aug_2024,
       ROUND(SUM(CASE WHEN f.sale_date BETWEEN DATE '2024-09-01' AND DATE '2024-09-30' THEN {expr} ELSE 0 END), 2) AS gross_incl_vat_sep_2024
{STORE_LINES} AND f.sale_date BETWEEN DATE '2024-08-01' AND DATE '2024-09-30';"""

    def pandas_fn(world):
        s = world.in_scope_sales()
        s = s[(s.store_id < 900) & (s.sale_date >= pd.Timestamp("2024-08-01")) & (s.sale_date <= pd.Timestamp("2024-09-30"))]
        return pd.DataFrame({"gross_incl_vat_aug_2024": [s[s.sale_date <= pd.Timestamp("2024-08-31")].gross_c.sum() / 100.0],
                             "gross_incl_vat_sep_2024": [s[s.sale_date >= pd.Timestamp("2024-09-01")].gross_c.sum() / 100.0]})

    return Question(
        "V1", 14, [col("gross_incl_vat_aug_2024", "measure", "eur"), col("gross_incl_vat_sep_2024", "measure", "eur")], sql("f.gross_amount"), pandas_fn,
        {"counts": "Sales in the physical stores including VAT, before returns, for August and September 2024 as two numbers, summed from the gross amount on each sales line so that every line carries its own VAT rate (24% before 1 September 2024, 25.5% from it, 14% and 10% for reduced-rate goods).",
         "leaves_out": "The web shop, store 999, test articles, returns.",
         "docs": ["Metric dictionary, 'Net sales' (figures including VAT come from gross_amount; never one flat rate)", "Data quality register, 'The general VAT rate rose from 24% to 25.5% on 1 September 2024'"],
         "result_note": "Two numbers."},
        naive=[Naive("vat", "flat_25_5", sql("f.net_amount * 1.255"), "Multiplies net sales by 25.5% for both months. August 2024 was at 24%, and reduced-rate goods carry 14% or 10%."),
               Naive("vat", "flat_24", sql("f.net_amount * 1.24"), "Multiplies net sales by 24% for both months. September 2024 was at 25.5%.")])


@question("V2")
def v2() -> Question:
    reference = f"""SELECT ROUND(f.vat_rate * 100, 1) AS vat_rate_pct, ROUND(SUM(f.gross_amount - f.net_amount), 2) AS vat_amount
{STORE_LINES} AND f.sale_date BETWEEN DATE '2024-08-26' AND DATE '2024-09-22'
GROUP BY 1 ORDER BY 1;"""
    flat = f"""SELECT 25.5 AS vat_rate_pct, ROUND(SUM(f.net_amount) * 0.255, 2) AS vat_amount
{STORE_LINES} AND f.sale_date BETWEEN DATE '2024-08-26' AND DATE '2024-09-22';"""

    def pandas_fn(world):
        s = world.in_scope_sales()
        s = s[(s.store_id < 900) & (s.sale_date >= pd.Timestamp("2024-08-26")) & (s.sale_date <= pd.Timestamp("2024-09-22"))].copy()
        s["vat_c"] = s.gross_c - s.net_c
        out = s.groupby("vat_bp").vat_c.sum() / 100.0
        frame = pd.DataFrame({"vat_rate_pct": out.index / 100.0, "vat_amount": out.values})
        return frame.sort_values("vat_rate_pct").reset_index(drop=True)

    return Question(
        "V2", 14, [col("vat_rate_pct", "dimension", "pct"), col("vat_amount", "measure", "eur")], reference, pandas_fn,
        {"counts": "The VAT charged on sales in the physical stores in period 5 of FY2024/25 (26 August to 22 September 2024), split by VAT rate: the amount on each line is its gross amount minus its net amount. The period straddles the 1 September 2024 change, so 24% applies to the first six days and 25.5% afterwards, alongside the 14% and 10% reduced rates.",
         "leaves_out": "The web shop, store 999, test articles, returns (the request is for VAT charged on sales).",
         "docs": ["Metric dictionary, 'Net sales' (including-VAT figures from gross_amount)", "Data quality register, 'The general VAT rate rose from 24% to 25.5% on 1 September 2024 ... The rate is stored on each line'"],
         "result_note": "One row per VAT rate (24, 25.5, 14, 10)."},
        naive=[Naive("vat", "flat_25_5", flat, "Applies 25.5% to all net sales, one row instead of four. It ignores the 24% days and the reduced-rate goods.")])


@question("V3")
def v3() -> Question:
    def sql(expr: str) -> str:
        return f"""WITH {WEB_DISPATCH}
SELECT d.fiscal_period, ROUND(SUM({expr}), 2) AS web_gross_incl_vat
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
JOIN web_dispatch w ON w.web_order_id = f.receipt_id JOIN dim_date d ON d.calendar_date = w.dispatch_date
WHERE s.store_id = 900 AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2024/25' AND d.fiscal_period BETWEEN 4 AND 6
GROUP BY 1 ORDER BY 1;"""

    def pandas_fn(world):
        s = world.sales[world.sales.is_web & (world.sales.category_was != cfg.TEST_CATEGORY) & world.sales.business_date.notna()]
        s = world.fiscal(s, "business_date")
        s = s[(s.fy == "FY2024/25") & s.period.between(4, 6)]
        out = (s.groupby("period").gross_c.sum() / 100.0).rename("web_gross_incl_vat")
        out.index.name = "fiscal_period"
        return out.reset_index()

    return Question(
        "V3", 14, [col("fiscal_period", "dimension", "count"), col("web_gross_incl_vat", "measure", "eur")], sql("f.gross_amount"), pandas_fn,
        {"counts": "Web sales including VAT, before returns, for each period of Q2 of FY2024/25 (periods 4 to 6, 29 July to 27 October 2024): the gross amount on each web line, by the Finnish dispatch date. A line keeps the VAT rate of the day the order was placed, so orders placed before 1 September 2024 and dispatched after it are still at 24%.",
         "leaves_out": "Cancelled and unshipped orders, web test orders, returns.",
         "docs": ["Metric dictionary, 'Net sales' and 'Web sales and time' (dispatch date)", "Data quality register, 'The general VAT rate rose from 24% to 25.5% on 1 September 2024'"],
         "result_note": "Three rows, one per period."},
        naive=[Naive("vat", "flat_25_5", sql("f.net_amount * 1.255"), "Multiplies web net sales by 25.5% for every period, but period 4 was entirely at 24% and period 5 was part 24%, part 25.5%.")])
