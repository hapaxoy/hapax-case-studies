"""Structured facts for the in-world documents.

One ID per fact. Every date, rate and count that appears in a fact is read
from config.py, so a change there changes the data, the facts and (through
build_world.py) the documents together.

Each fact carries:
  id               e.g. DEF-LFL-OPEN
  kind             definition | calendar | register | team_note | schema | history
  statement        the canonical statement of the fact (internal; the documents phrase it)
  must_contain     phrases that must appear in the document block that carries the fact
  docs             the world documents that must carry it
  trap_class       the trap class it belongs to (internal; never shown in world/)
  parity_required  True if the prompt doc and the library must both carry it (rule 16)

The facts here are what the world documents may say, no more and no fewer. The
four undocumented incidents are deliberately absent.
"""
from __future__ import annotations

from datetime import date, timedelta

import config as cfg
import schema_comments

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]


def fmt_date(value: date) -> str:
    """British long date, e.g. 3 November 2025."""
    return f"{value.day} {MONTHS[value.month - 1]} {value.year}"


def fy_label(start_year: int) -> str:
    return f"FY{start_year}/{str(start_year + 1)[2:]}"


def world_context() -> dict:
    """Every value that world templates and facts take from config, already formatted."""
    stores = {row[0]: row for row in cfg.STORES}
    fy = cfg.FISCAL_YEAR_STARTS
    fy2526_end = fy[2026] - timedelta(days=1)
    fy2425_end = fy[2025] - timedelta(days=1)
    week53_start = fy[2025] + timedelta(days=7 * 52)
    last_period_end = cfg.WINDOW_END - timedelta(days=7)         # P5 FY2026/27 ends the Sunday before the loaded week
    refit_text = []
    for store_id, start, end in cfg.REFITS:
        weeks = ((end - start).days + 1) // 7
        refit_text.append(f"{stores[store_id][1]} ({store_id}), {fmt_date(start)} to {fmt_date(end)} ({weeks} weeks)")
    moved = [(row[0], row[1], row[3], row[4]) for row in cfg.STORES if row[3] != row[4]]
    moved_text = "; ".join(f"{sid} {name} ({old} to {new})" for sid, name, old, new in moved)
    closed_holidays = ", ".join(cfg.STORE_CLOSED_HOLIDAYS)
    new_stores = [(row[0], row[1], row[6]) for row in cfg.STORES if row[6]]
    closed_store = [(row[0], row[1], row[7]) for row in cfg.STORES if row[7]][0]
    return {
        "migration_date": fmt_date(cfg.MIGRATION_DATE),
        "vat_change_date": fmt_date(cfg.VAT_CHANGE_DATE),
        "vat_standard_before": "24%", "vat_standard_after": "25.5%", "vat_reduced_a": "14%", "vat_reduced_b": "10%",
        "reorg_date": fmt_date(cfg.REGION_REORG_DATE),
        "category_move_date": fmt_date(cfg.CATEGORY_MOVE_DATE),
        "fy2425_label": fy_label(2024), "fy2526_label": fy_label(2025), "fy2627_label": fy_label(2026),
        "fy2425_start": fmt_date(fy[2024]), "fy2425_end": fmt_date(fy2425_end),
        "fy2526_start": fmt_date(fy[2025]), "fy2526_end": fmt_date(fy2526_end),
        "fy2627_start": fmt_date(fy[2026]),
        "week53_start": fmt_date(week53_start), "week53_end": fmt_date(fy2526_end),
        "data_end": fmt_date(cfg.WINDOW_END),
        "data_end_week": f"{fy_label(2026)} week {(cfg.WINDOW_END - fy[2026]).days // 7 + 1}",
        "last_period_label": f"{fy_label(2026)} P05", "last_period_end": fmt_date(last_period_end),
        "refits": refit_text,
        "moved_stores": moved_text,
        "n_moved": str(len(moved)),
        "closed_holidays": closed_holidays,
        "new_store_1": f"{new_stores[0][1]} ({new_stores[0][0]}), opened {fmt_date(new_stores[0][2])}",
        "new_store_2": f"{new_stores[1][1]} ({new_stores[1][0]}), opened {fmt_date(new_stores[1][2])}",
        "lfl_ready_136": fmt_date(new_stores[0][2] + timedelta(days=364)),
        "lfl_ready_137": fmt_date(new_stores[1][2] + timedelta(days=364)),
        "closed_store": f"{closed_store[1]} ({closed_store[0]}), closed {fmt_date(closed_store[2])}",
        "closed_store_date": fmt_date(closed_store[2]),
        "closed_store_id": str(closed_store[0]),
        "legacy_report_last": fmt_date(cfg.LEGACY_WEEKLY_REPORT_LAST_DATE),
        "return_window_days": str(cfg.RETURN_WINDOW_DAYS),
        "holdout_pct": f"{int(round(cfg.CAMPAIGN_HOLDOUT_SHARE * 100))}%",
        "uplift_extra_days": "seven",
        "staff_discount": f"{int(round(cfg.STAFF_DISCOUNT * 100))}%",
        "web_store_id": str(cfg.WEB_STORE_ID), "training_store_id": str(cfg.TRAINING_STORE_ID),
        "test_category": cfg.TEST_CATEGORY,
        "first_clock_change": fmt_date(cfg.CLOCK_CHANGE_DAYS[0]), "second_clock_change": fmt_date(cfg.CLOCK_CHANGE_DAYS[1]),
    }


def build_facts() -> list[dict]:
    """All facts, in document order."""
    c = world_context()
    facts: list[dict] = []

    def add(fact_id, kind, statement, must_contain, docs, trap_class, parity_required=True):
        facts.append({"id": fact_id, "kind": kind, "statement": statement, "must_contain": must_contain, "docs": docs,
                      "trap_class": trap_class, "parity_required": parity_required})

    D, R, T = "metric_dictionary", "data_quality_register", "team_notes"

    # ---- Definitions (metric dictionary) -----------------------------------------------------------
    add("DEF-NET-SALES", "definition",
        "Net sales is the net amount excluding VAT, after returns; a return reduces net sales on its own return date, not on the original sale date.",
        ["excluding VAT", "return date"], [D], "company_definition")
    add("DEF-NET-SALES-SCOPE", "definition",
        f"Net sales exclude store {c['training_store_id']} and test articles (category {c['test_category']}); they include staff purchases.",
        [c["training_store_id"], c["test_category"], "staff purchases"], [D], "exclusions")
    add("DEF-WEB-RECOGNITION", "definition",
        "Web sales are recognised on the dispatch date in Helsinki time; sale_date on a web line is the order date and is not used for web net sales.",
        ["dispatch date", "Helsinki time"], [D], "time_zone")
    add("DEF-WEB-CANCELLED", "definition",
        "Cancelled web orders are excluded from web sales and from web order counts.",
        ["cancelled"], [D], "exclusions")
    add("DEF-WEB-ORDER-COUNT", "definition",
        "Web orders are counted on the order date in Helsinki time; orders still processing are counted, cancelled orders are not.",
        ["order date", "processing"], [D], "time_zone")
    add("DEF-CLICK-COLLECT", "definition",
        "Click-and-collect counts as web. The click-and-collect share is click-and-collect net sales divided by all web net sales.",
        ["counted as web", "click-and-collect share"], [D], "migration")
    add("DEF-TIMEZONE", "definition",
        "Timestamps in the warehouse are UTC. Business reporting uses Helsinki time, with the day changing at local midnight.",
        ["UTC", "local midnight"], [D], "time_zone")
    add("DEF-LFL-BASIS", "definition",
        "Like-for-like (LFL) growth compares net sales in the LFL stores for a period with the same fiscal weeks last year, week by week. Physical stores only; the web shop is not part of LFL.",
        ["like-for-like", "same fiscal weeks last year", "web shop is not part of"], [D], "company_definition")
    add("DEF-LFL-OPEN", "definition",
        "A store is in the LFL base for a period only if it had been open at least 52 weeks (364 days) before the first day of the period.",
        ["52 weeks", "first day of the period"], [D], "company_definition")
    add("DEF-LFL-BOTH-YEARS", "definition",
        "A store-week counts only if the store traded in that fiscal week in both years; a week in which the store was shut (refit or closure) in either year drops out for that store.",
        ["both years", "traded"], [D], "company_definition")
    add("DEF-LFL-REFIT", "definition",
        "Refit weeks are excluded for the store concerned, in both years, using ref_store_closure; the store stays in the base for its other weeks.",
        ["refit weeks", "ref_store_closure"], [D], "company_definition")
    add("DEF-LFL-WEEK53", "definition",
        "Week 53 is excluded from LFL because it has no comparator week.",
        ["week 53"], [D], "fiscal_calendar")
    add("DEF-ATV", "definition",
        "Average transaction value (ATV) is net sales before returns divided by the number of sales receipts. It is a store measure: staff purchases, store 999 and test articles are excluded, and web orders are not included.",
        ["before returns", "sales receipts", "staff purchases", "store 999"], [D], "company_definition")
    add("DEF-ACTIVE-MEMBER", "definition",
        "An active member has made at least one purchase in the trailing 52 fiscal weeks, ending with the as-of week and including it, through any channel. Count distinct member_id.",
        ["52 fiscal weeks", "member_id"], [D], "company_definition")
    add("DEF-MEMBER-SHARE", "definition",
        "Member share of sales is net sales before returns on lines linked to a member divided by all net sales before returns; receipts without a member and guest web orders count as non-member.",
        ["member share of sales", "guest"], [D], "company_definition")
    add("DEF-RETURN-RATE", "definition",
        "Return rate is returned net (refund_net) divided by sold net, grouped by the fiscal week of the original sale (the sale-week cohort), whenever the return happened. This is deliberately a different date convention from net sales.",
        ["sale-week cohort", "original sale"], [D], "company_definition")
    add("DEF-GROSS-MARGIN", "definition",
        "Gross margin is net sales minus the standard cost of the goods sold, both after returns: returned units are credited back at standard cost. Margin percentage is gross margin divided by net sales.",
        ["standard cost", "credited"], [D], "company_definition")
    add("DEF-WEEKS-COVER", "definition",
        "Weeks of cover is closing stock units at the end of a fiscal week divided by the average weekly units sold over the prior four fiscal weeks, at the same store or grouping. Units sold are the quantity on sales lines, by sale date.",
        ["prior four fiscal weeks", "closing stock"], [D], "semi_additive")
    add("DEF-STOCK-SEMIADD", "definition",
        "Closing stock is a snapshot taken at the end of each fiscal week. Add it across stores and products but never across weeks; for a period, average the weekly closings or take the last week's, as the request asks.",
        ["never across weeks", "snapshot"], [D], "semi_additive")
    add("DEF-UPLIFT", "definition",
        f"Campaign uplift is the mean net sales per targeted member minus the mean per holdout member over the campaign window plus {c['uplift_extra_days']} days. A targeted member has at least one exposure row in the campaign; members with no sales count as zero; net sales are before returns on lines linked to the member.",
        ["plus seven days", "holdout"], [D], "company_definition")
    add("DEF-HIERARCHY-ASIS", "definition",
        "Management reporting restates history on the current hierarchy (store region, product category), called as-is, unless the request asks for as-was, which is the hierarchy at the date of the transaction.",
        ["as-is", "as-was"], [D], "scd")
    add("DEF-VAT-GROSS", "definition",
        "Net sales are always excluding VAT. Figures including VAT are summed from gross_amount on the lines, each at its own VAT rate; a flat rate is never applied to a net total.",
        ["gross_amount", "own VAT rate"], [D], "vat")
    add("DEF-NEW-MEMBER", "definition",
        f"A new member is counted on their join date, at the home store in their first dim_member version (the home store at enrolment). Online sign-ups sit under store {c['web_store_id']}.",
        ["join date", "first version"], [D], "company_definition")
    add("DEF-STORE-LEAGUE", "definition",
        "The store league table ranks stores by net sales per trading day. Trading days are the days the store was open: after opening, before closure, outside refit closures and not a closed holiday. A store that traded for only part of the period is still listed, with its own trading days.",
        ["per trading day", "closed holiday"], [D], "exclusions")
    add("DEF-STORE-SCOPE", "definition",
        f"Store counts and store-level analyses cover the physical stores only (store_id below 900). The web shop (store {c['web_store_id']}) is shown as its own line when a request asks for the total company; store {c['training_store_id']} is never included.",
        ["below 900", "total company"], [D], "exclusions")

    # ---- Calendar ----------------------------------------------------------------------------------
    add("CAL-YEAR", "calendar",
        "The fiscal year starts on the Monday nearest 1 May. Weeks run Monday to Sunday. Years are labelled like FY2025/26.",
        ["Monday nearest 1 May", "FY2025/26"], [D], "fiscal_calendar")
    add("CAL-FY-DATES", "calendar",
        f"{c['fy2425_label']} runs {c['fy2425_start']} to {c['fy2425_end']} (52 weeks); {c['fy2526_label']} runs {c['fy2526_start']} to {c['fy2526_end']} (53 weeks); {c['fy2627_label']} starts {c['fy2627_start']}.",
        [c["fy2425_start"], c["fy2425_end"], c["fy2526_start"], c["fy2526_end"], c["fy2627_start"]], [D], "fiscal_calendar")
    add("CAL-PERIODS", "calendar",
        "A fiscal year has 12 periods in a 4-4-5 week pattern within each quarter. A quarter is three periods: Q1 is P1 to P3 (weeks 1 to 13), Q2 is P4 to P6, Q3 is P7 to P9, Q4 is P10 to P12.",
        ["4-4-5", "P1 to P3"], [D], "fiscal_calendar")
    add("CAL-WEEK53", "calendar",
        f"{c['fy2526_label']} has 53 weeks. Week 53 ({c['week53_start']} to {c['week53_end']}) is added to period 12, which then has six weeks. Week 53 has no comparator week in the prior year.",
        ["week 53", "period 12", c["week53_start"]], [D], "fiscal_calendar")
    add("CAL-COMPARE", "calendar",
        "Compare with last year by the same fiscal week or period number (week-aligned), not by the same calendar dates.",
        ["same fiscal week", "calendar dates"], [D], "fiscal_calendar")
    add("CAL-RELATIVE", "calendar",
        "Relative terms: last period means the last completed fiscal period; year to date (YTD) means the fiscal year to date through the last completed fiscal week; this year means the current fiscal year.",
        ["last completed", "year to date"], [D], "fiscal_calendar")
    add("CAL-DATA-THROUGH", "calendar",
        f"The warehouse is loaded through Sunday {c['data_end']} ({c['data_end_week']}). Period 6 of {c['fy2627_label']} has only its first week; the last complete period is {c['last_period_label']}, ending {c['last_period_end']}.",
        [c["data_end"], c["last_period_label"], c["last_period_end"]], [D], "fiscal_calendar")
    add("CAL-CLOSED-DAYS", "calendar",
        f"The stores are shut on: {c['closed_holidays']}. dim_date.is_trading_day is false on those days.",
        ["is_trading_day", "Midsummer Eve", "Good Friday"], [D], "exclusions")

    # ---- Data quality register ---------------------------------------------------------------------
    add("REG-MIGRATION", "register",
        f"The web platform migrated on {c['migration_date']}. channel_code stops being filled from that date and channel_id is used instead; click-and-collect gets its own key (3). Before the migration click-and-collect orders carry channel_code WB and no channel_id.",
        [c["migration_date"], "channel_id", "channel_code"], [R], "migration")
    add("REG-LEGACY-VIEW", "register",
        f"rpt.v_daily_sales is built on channel_code. From {c['migration_date']} it silently omits web sales. rpt.v_weekly_store_sales is built on it and has the same gap. Do not use either.",
        ["rpt.v_daily_sales", "web sales", "rpt.v_weekly_store_sales"], [R], "migration")
    add("REG-STORE-999", "register",
        f"Store {c['training_store_id']} is the training store. It holds test-article and staff-training transactions only and is excluded from all sales reporting.",
        [c["training_store_id"], "training store"], [R], "exclusions")
    add("REG-STORE-900", "register",
        f"The web shop is a pseudo-store, store_id {c['web_store_id']} (region Online, format Web), so that web lines and web returns have a store key. Web lines are told apart by store_id, not by channel_code.",
        [c["web_store_id"], "Online", "pseudo-store"], [R], "migration")
    add("REG-STAFF-PURCHASE", "register",
        f"staff_purchase_flag is set on every line of a staff receipt (staff get {c['staff_discount']} off). Staff purchases count in net sales and are excluded from ATV.",
        ["staff_purchase_flag"], [R], "exclusions")
    add("REG-UTC", "register",
        f"Columns ending _ts_utc hold UTC. sale_date is the Helsinki business date of the sale. Finland is UTC+2 in winter and UTC+3 in summer; the clocks changed on {c['first_clock_change']} and {c['second_clock_change']}, among other dates.",
        ["_ts_utc", "UTC+2", "UTC+3"], [R], "time_zone")
    add("REG-CANCELLED", "register",
        "Cancelled web orders stay in fact_web_order with status cancelled, no dispatch time and no sales lines. Orders not yet dispatched have status processing and no sales lines until they are.",
        ["cancelled", "processing", "no sales lines"], [R], "exclusions")
    add("REG-TEST-SKU", "register",
        f"Test articles sit in category {c['test_category']}. They are sold in store {c['training_store_id']} and in a few web test orders, and are excluded from all reporting.",
        [c["test_category"]], [R], "exclusions")
    add("REG-WEB-SALE-DATE", "register",
        "On web lines sale_date is the order date. The revenue date is the dispatch date, found by joining fact_web_order on receipt_id = web_order_id.",
        ["order date", "dispatch date", "web_order_id"], [R], "time_zone")
    add("REG-REGION-REORG", "register",
        f"On {c['reorg_date']} the four regions (South, West, East, North) became five, with the new Capital Region. {c['n_moved']} stores changed region: {c['moved_stores']}.",
        [c["reorg_date"], "Capital Region", "114"], [R], "scd")
    add("REG-OUTDOOR-LIGHTING", "register",
        f"From {c['category_move_date']} (FY2025/26 period 7) the outdoor lighting subcategory moved from Garden to Electrical. Each affected article has a new dim_product version from that date.",
        [c["category_move_date"], "outdoor lighting"], [R], "scd")
    add("REG-SCD-KEYS", "register",
        "dim_store, dim_product and dim_member keep one row per version. The fact tables carry the version key (store_key, product_key, member_key) valid on the transaction date. store_id, sku and member_id are stable across versions; count distinct natural keys, and join between versions only on the validity dates, or rows multiply.",
        ["store_id", "member_id", "validity"], [R], "scd")
    add("REG-STORE-EVENTS", "register",
        f"Store openings: {c['new_store_1']}; {c['new_store_2']}. Store closure: {c['closed_store']}.",
        ["136", "137", c["closed_store_date"]], [R], "company_definition")
    add("REG-REFITS", "register",
        "Refit closures, whole fiscal weeks with no sales: " + "; ".join(c["refits"]) + ". They are listed in ref_store_closure.",
        ["ref_store_closure", "104", "119", "125"], [R], "company_definition")
    add("REG-DEPRECATED", "register",
        f"Do not use: dim_store_old and dim_product_old (flat, pre-history), every stg_ table (staging), every bak_ table (dated backups), every tmp_ table, rpt_weekly_sales_by_region (stopped refreshing {c['legacy_report_last']}, old regions), rpt.v_daily_sales and rpt.v_weekly_store_sales.",
        ["dim_store_old", "stg_", "bak_", "tmp_", "rpt_weekly_sales_by_region"], [R], "migration")
    add("REG-CONTROL-TOTAL", "register",
        "rpt_daily_store_sales holds net sales per store per business day on the company definition (web on its dispatch date, returns on their return date). It has no product, member or channel dimension. Use it as a control total for store-level figures.",
        ["rpt_daily_store_sales", "control total"], [R], "company_definition")
    add("REG-MEMBER-VERSIONS", "register",
        "dim_member gets a new version when a member's tier, home store or marketing consent changes. Count members by distinct member_id; the member_key on a line is the version at that date.",
        ["marketing consent", "tier", "distinct member_id"], [R], "fan_out")
    add("REG-EXPOSURE-FANOUT", "register",
        "fact_campaign_exposure has one row per contact, so a member can appear several times in one campaign. Reduce to one row per member (distinct member_id) before joining to sales.",
        ["one row per contact", "distinct member_id"], [R], "fan_out")
    add("REG-CONSENT", "register",
        f"Members are contacted only if they have marketing consent on the contact date. Holdout members ({c['holdout_pct']} of each mailing list) are never contacted. campaign_holdout holds member_id, not member_key.",
        ["campaign_holdout", "member_id, not member_key"], [R], "fan_out")
    add("REG-GUEST-ORDERS", "register",
        "Guest web orders (checkout without logging in) have no member key. Logged-in orders carry the member's key.",
        ["guest", "logged-in"], [R], "company_definition")
    add("REG-STOCK-SNAPSHOT", "register",
        "fact_stock_week has one row per store and article for each week-ending Sunday, only for the articles the store ranges (carries). Web orders are picked from the central warehouse, which is not in this table.",
        ["ranges", "central warehouse"], [R], "semi_additive")
    add("REG-RETURN-LAG", "register",
        f"Returns can arrive up to {c['return_window_days']} days after a sale, so a sale-week cohort is not complete until about five weeks later. Return lines are booked where they are processed: web returns sent by post are booked to the web shop.",
        [f"{c['return_window_days']} days", "booked"], [R], "company_definition")
    add("REG-VAT-CHANGE", "register",
        f"The general VAT rate rose from {c['vat_standard_before']} to {c['vat_standard_after']} on {c['vat_change_date']}. The reduced rates ({c['vat_reduced_a']} and {c['vat_reduced_b']}) did not change. The rate is stored on each line; dim_product.vat_class says which rate applies.",
        [c["vat_standard_after"], c["vat_change_date"], c["vat_reduced_a"], c["vat_reduced_b"]], [R], "vat")

    # ---- Team notes --------------------------------------------------------------------------------
    add("TEAM-ASIS", "team_note",
        "Report history as-is (current regions and categories restated back) unless the requester asks for as-was. Say which one you used.",
        ["as-is", "as-was"], [T], "scd")
    add("TEAM-EXPLICIT-REQUEST", "team_note",
        "When a request explicitly asks for something that differs from a company default (gross instead of net, as-was instead of as-is, UTC instead of Helsinki time, and so on), follow the request and say that you did.",
        ["explicitly asks", "follow the request"], [T], "override")
    add("TEAM-NO-LEGACY-VIEW", "team_note",
        "Do not use rpt.v_daily_sales. It loses web sales after the migration.",
        ["rpt.v_daily_sales"], [T], "migration")
    add("TEAM-LFL-EDGE", "team_note",
        f"LFL edge cases: a store back from a refit is excluded for the refit weeks only; the two new stores enter the LFL base on {c['lfl_ready_136']} (136) and {c['lfl_ready_137']} (137); the closed store ({c['closed_store_id']}) drops out from its closure; week 53 is never LFL; the web shop is never LFL.",
        [c["lfl_ready_136"], c["lfl_ready_137"], "week 53"], [T], "company_definition")
    add("TEAM-EXCLUSIONS", "team_note",
        f"Always filter out store {c['training_store_id']} and category {c['test_category']} in sales work, and say so when the filter changes a total.",
        [c["training_store_id"], c["test_category"]], [T], "exclusions")
    add("TEAM-CONTROL-TOTALS", "team_note",
        "Before sending a store-level figure, check the total against rpt_daily_store_sales for the same days.",
        ["rpt_daily_store_sales"], [T], "company_definition")

    # ---- Schema comments (shared by every arm; not required in the prompt doc or library) ------------
    for (table, column), (comment, stale) in schema_comments.COLUMN_COMMENTS.items():
        facts.append({"id": f"SCH-{table}.{column}", "kind": "schema", "statement": comment, "must_contain": [],
                      "docs": ["schema_comments"], "trap_class": "none", "parity_required": False, "stale": stale})
    return facts
