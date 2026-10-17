# Tuomimetsä Oy: house knowledge for data requests

The company definitions, calendar rules, warehouse traps and past answers, from the Data & Analytics wiki. Each block is tagged with the wiki fact it comes from.

<!-- source: metric_dictionary.md -->
If a request needs a number that is not defined here, ask in the request queue before inventing a definition.

## 1. Working rules

<!-- facts: TEAM-EXPLICIT-REQUEST -->
When a request explicitly asks for something that differs from a company default (gross instead of net, as-was instead of as-is, UTC instead of Helsinki time, and so on), follow the request and say that you did.

<!-- facts: TEAM-ASIS, DEF-HIERARCHY-ASIS -->
Report history as-is unless the requester asks for as-was, and say which one you used. Management reporting restates history on the current hierarchy of store regions and product categories (as-is). As-was means the hierarchy as it stood on the date of the transaction.

<!-- facts: TEAM-EXCLUSIONS -->
Always filter out store 999 and category ZZ Test in sales work, and say so when the filter changes a total.

<!-- facts: TEAM-CONTROL-TOTALS, REG-CONTROL-TOTAL -->
Before sending a store-level figure, check the total against rpt_daily_store_sales for the same days. That table holds net sales per store per business day on the company definition (web on its dispatch date, returns on their return date). It has no product, member or channel dimension, so it is a control total, not a source for analysis.

<!-- facts: TEAM-NO-LEGACY-VIEW, REG-LEGACY-VIEW -->
Do not use rpt.v_daily_sales. It is built on channel_code and from 3 November 2025 it silently leaves out web sales. rpt.v_weekly_store_sales is built on it and has the same gap. Some dashboards still use them.

## 2. Fiscal calendar

<!-- facts: CAL-YEAR -->
The fiscal year starts on the Monday nearest 1 May, and fiscal weeks run Monday to Sunday. A year is written like FY2025/26, which is the year that began in April 2025.

<!-- facts: CAL-FY-DATES -->
FY2024/25 runs from 29 April 2024 to 27 April 2025 and has 52 weeks. FY2025/26 runs from 28 April 2025 to 3 May 2026 and has 53 weeks. FY2026/27 starts on 4 May 2026.

<!-- facts: CAL-PERIODS -->
There are 12 periods in a year, built from weeks in a 4-4-5 pattern within each quarter (four weeks, four weeks, five weeks). Q1 is P1 to P3 (weeks 1 to 13), Q2 is P4 to P6, Q3 is P7 to P9 and Q4 is P10 to P12.

<!-- facts: CAL-WEEK53 -->
FY2025/26 has 53 weeks. Week 53 (27 April 2026 to 3 May 2026) is added to period 12, which then runs six weeks. Week 53 has no comparator week in the prior year.

<!-- facts: CAL-COMPARE -->
To compare with last year, line up the same fiscal week or the same period number. Do not line up calendar dates: the same calendar dates fall in a different fiscal week each year.

<!-- facts: CAL-RELATIVE -->
"Last period" means the last completed fiscal period. "YTD" means the fiscal year to date through the last completed fiscal week. "This year" means the current fiscal year.

<!-- facts: CAL-DATA-THROUGH -->
The warehouse is loaded through Sunday 4 October 2026 (FY2026/27 week 22). Period 6 of FY2026/27 has only its first week so far. The last complete period is FY2026/27 P05, which ended on 27 September 2026.

<!-- facts: CAL-CLOSED-DAYS -->
The stores are shut on New Year's Day, Epiphany, Good Friday, Easter Sunday, May Day, Midsummer Eve, Midsummer Day, Independence Day, Christmas Eve, Christmas Day and Boxing Day. dim_date.is_trading_day is false on those days.

<!-- source: schema_comments.csv -->
Calendar tables. dim_date has one row per day with fiscal_year, fiscal_quarter, fiscal_period, fiscal_period_label (e.g. 'FY2025/26 P05'), fiscal_week, fiscal_week_start_date (Monday), fiscal_week_end_date (Sunday), weeks_in_fiscal_year, is_53_week_year, is_public_holiday, holiday_name and is_trading_day. ref_fiscal_calendar has one row per period with period_start_date, period_end_date, weeks_in_period, first_fiscal_week, last_fiscal_week and fully_loaded (true when the whole period is in the warehouse). Filter on these columns rather than on calendar months.

<!-- facts: CAL-RELATIVE -->
<!-- source: REQ-D02, REQ-D03, REQ-D04, REQ-D05, REQ-D06, REQ-D08, REQ-D10, REQ-D11, REQ-D12, REQ-D13, REQ-D14, REQ-D16, REQ-D28, REQ-D29, REQ-D33, REQ-D35 -->
How past requests read relative phrases:

- A period or quarter named without a year was read as the most recent completed one: "Q3" on 14 April 2026 was FY2025/26 Q3 (REQ-D03), "Q1" on 20 August 2025 was FY2025/26 Q1 (REQ-D06), "P2" on 7 July 2026 was FY2026/27 P2 (REQ-D10), "Q4" on 23 June 2026 was FY2025/26 Q4 (REQ-D12).
- "First half" is P1 to P6 (REQ-D13); "second half" and "back half" are P7 to P12 (REQ-D04, REQ-D35). For an LFL request REQ-D08 took weeks 27 to 52, because week 53 is never LFL.
- "Last four weeks" asked on 1 September 2026 was read as the last completed period, FY2026/27 P4 (REQ-D02), which was those same four weeks.
- "Last year" is not defined in the metric dictionary. Name the fiscal year you used in the answer. Past readings, by date asked (fiscal year current at the time in brackets): 6 May 2025 (FY2025/26) took FY2024/25 (REQ-D29); 18 June 2025 (FY2025/26) took FY2024/25 (REQ-D05); 2 July 2025 (FY2025/26) took FY2024/25 (REQ-D11); 21 January 2026 (FY2025/26) took FY2025/26 (REQ-D16); 10 February 2026 (FY2025/26) took FY2025/26 (REQ-D33); 10 March 2026 (FY2025/26) took FY2025/26 (REQ-D14); 12 to 27 May 2026 (FY2026/27) took FY2025/26 (REQ-D04, REQ-D08, REQ-D28, REQ-D35).
- With a comparison, week 53 was dropped from both years (REQ-D04). Without one, it stays in (REQ-D12, REQ-D35).

<!-- facts: CAL-RELATIVE, CAL-PERIODS -->
<!-- source: REQ-D09 -->
"YTD as of the end of Pn" runs from week 1 of the fiscal year to the last week of Pn. REQ-D09, asked on 8 September 2026 for YTD LFL as of the end of P4, used weeks 1 to 17 of FY2026/27 against weeks 1 to 17 of FY2025/26: P4 ends with week 17.

<!-- facts: CAL-YEAR, CAL-PERIODS -->
<!-- source: REQ-D19 -->
Weekly series use whole fiscal weeks only, Monday to Sunday, with no part week at either end. REQ-D19 (weekly web sales from August to the end of October 2025, with the migration week) ran from Monday 4 August to Sunday 9 November 2025: it started on the first Monday in August rather than with 1 to 3 August as a part week, and ended on the Sunday of the migration week the requester asked for.

<!-- facts: CAL-RELATIVE, CAL-DATA-THROUGH -->
<!-- source: REQ-D24 -->
A series by quarter or by period stops at the last quarter or period complete as of the date of the request; a part quarter or period is not shown. REQ-D24, asked on 24 March 2026 for the click-and-collect share of web orders by quarter since the start of FY24/25, stopped at FY2025/26 Q3 (ended 25 January 2026), because Q4 was still running. With the warehouse loaded through 4 October 2026, the last complete period is FY2026/27 P05 and the last complete quarter is FY2026/27 Q1.

## 3. Warehouse map

<!-- source: schema_ddl.sql, schema_comments.csv -->
Canonical tables, their grain and their keys:

| Table | One row per | Keys and notes |
|---|---|---|
| fact_sales_line | receipt line or web order line | sales_line_id; receipt_id + line_no (receipt_id equals web_order_id on web lines); sale_date (Helsinki date; the order date on web lines), sale_ts_utc; store_key, product_key, member_key (null for non-members); channel_code (ST store, WB web), channel_id; quantity; net_amount (excluding VAT, after line discounts); vat_rate; gross_amount (including VAT); standard_cost; staff_purchase_flag |
| fact_return_line | returned line | return_line_id; sales_line_id (the line being returned); return_date, return_ts_utc; store_key (where the return was processed; the web shop for web returns), product_key, member_key at the return date; quantity_returned; refund_net; vat_rate (of the original line); refund_gross; standard_cost_returned; reason_code |
| fact_web_order | web order | web_order_id; member_key (null for guests); login_state (logged_in, guest); order_ts_utc; dispatch_ts_utc (for click-and-collect, when ready for collection); status (delivered, collected, processing, cancelled); fulfilment_type (home_delivery, click_and_collect); pickup_store_key; order_total_gross (including VAT, at order time); line_count |
| fact_stock_week | store x article x week-ending Sunday | store_key, product_key, week_ending_date; closing_units, closing_value (at standard cost), receipts_units, adjustment_units (stock-take and write-offs) |
| fact_campaign_exposure | contact made to a member | exposure_id; campaign_id; member_key (version at the contact date); contact_ts_utc; contact_channel (email, sms, push); delivered; opened |
| rpt_daily_store_sales | store x business day | business_date, store_id; receipts; units_sold; net_sales_before_returns; returns_net (refunds booked that day); net_sales; all excluding VAT |
| dim_store | store version | store_key (version), store_id (stable); store_name, city, region, format, sqm; open_date (null for stores open before 2024), close_date; valid_from, valid_to, is_current |
| dim_product | article version | product_key (version), sku (stable); product_name, category, subcategory, brand, own_label_flag; vat_class (standard, reduced14, reduced10); standard_unit_cost (revalued each April); listed_from, delisted_on; valid_from, valid_to, is_current |
| dim_member | member version | member_key (version), member_id (stable); join_date, tier (Basic, Silver, Gold), home_store_id (900 for online sign-ups), marketing_consent; valid_from, valid_to, is_current |
| dim_channel | channel | channel_id (used from the web-platform migration), channel_name, channel_group (store or web), legacy_channel_code |
| dim_campaign | campaign | campaign_id, campaign_name; start_date, end_date (the campaign window); channels (joined with +); target_group; holdout_pct; mailing_list_size (including the holdout); holdout_size |
| campaign_holdout | campaign x held-out member | campaign_id, member_id (not member_key) |
| ref_store_closure | refit closure | store_id; closure_type; closure_start_date, closure_end_date (first and last closed day); weeks_closed |
| dim_date, ref_fiscal_calendar | day; fiscal period | see section 2 |

<!-- source: schema_comments.csv, REQ-D39 -->
Two column comments in the schema are out of date. dim_store.region says "North, South, East or West"; there are five regions since 28 April 2025, plus Online (section 6). dim_store.format says "Hyper, Standard or Express", but REQ-D39 filters format = 'Large' and the web shop's format is Web. Look at the distinct values before filtering on either column.

<!-- facts: REG-SCD-KEYS -->
dim_store, dim_product and dim_member keep one row per version. The fact tables carry the version key (store_key, product_key, member_key) that was valid on the transaction date. The natural keys store_id, sku and member_id are stable across versions. Count distinct natural keys, and join between versions only on the validity dates, or rows multiply. In practice: join the fact's store_key to dim_store for as-was; for as-is, go from there to dim_store again on store_id AND is_current (same for sku and dim_product). valid_to is 9999-12-31 on the current version.

<!-- facts: REG-STORE-900, REG-STORE-999, REG-TEST-SKU -->
The web shop is a pseudo-store, store_id 900 (region Online, format Web), so that web lines and web returns have a store key. Web lines are told apart by store_id, not by channel_code. Store 999 is the training store: it holds test-article and staff-training transactions only and is left out of all sales reporting. Test articles sit in category ZZ Test; they are sold in store 999 and in a few web test orders, and are left out of all reporting.

<!-- facts: REG-MIGRATION -->
The web platform migrated on 3 November 2025. channel_code stops being filled from that date and channel_id is used instead. Click-and-collect gets its own key (3). Before the migration, click-and-collect orders carry channel_code WB and no channel_id. So neither channel column works across the migration: use store_id 900 for web and fact_web_order.fulfilment_type for click-and-collect.

<!-- facts: REG-DEPRECATED -->
Do not use: dim_store_old and dim_product_old (flat tables from before the history was kept), every stg_ table (staging), every bak_ table (dated backups), every tmp_ table, rpt_weekly_sales_by_region (it stopped refreshing on 27 April 2025 and uses the old regions), rpt.v_daily_sales and rpt.v_weekly_store_sales.

<!-- source: schema_ddl.sql -->
In this warehouse that covers dim_store_old, dim_product_old, stg_campaign_contact_load, stg_member_updates, stg_product_feed, stg_return_line_load, stg_sales_line_load, stg_stock_snapshot, stg_web_order_load, bak_dim_campaign_2025, bak_dim_product_20251026, bak_dim_store_2025, tmp_lfl_store_list_2024, tmp_lfl_store_list_2025, tmp_outdoor_lighting_skus, tmp_region_map, rpt_weekly_sales_by_region, rpt.v_daily_sales and rpt.v_weekly_store_sales. channel_code is correct before 3 November 2025 and silently empty after.

<!-- facts: REG-UTC, DEF-TIMEZONE -->
Columns ending _ts_utc hold UTC. sale_date is the Helsinki business date of the sale. Reporting is in Helsinki time and a day changes at local midnight, not at midnight UTC. Finland is UTC+2 in winter and UTC+3 in summer; the clocks changed on 30 March 2025 and 26 October 2025, among other dates. The accepted queries convert with `CAST(timezone('Europe/Helsinki', col AT TIME ZONE 'UTC') AS DATE)`, or `hour(...)` for the hour.

## 4. Sales definitions

<!-- facts: DEF-NET-SALES, DEF-NET-SALES-SCOPE -->
Net sales is the net amount excluding VAT, after returns. A return reduces net sales on its own return date, not on the date of the original sale. Store 999 and test articles (category ZZ Test) are left out of net sales. Staff purchases are included.

<!-- facts: REG-STAFF-PURCHASE -->
staff_purchase_flag is set on every line of a staff receipt (staff get 15% off). Staff purchases count in net sales and are excluded from ATV.

<!-- facts: DEF-VAT-GROSS, REG-VAT-CHANGE -->
Net sales are always excluding VAT. When a request wants figures including VAT, sum gross_amount from the lines. Every line carries its own VAT rate, so never multiply a net total by one flat rate. The general VAT rate rose from 24% to 25.5% on 1 September 2024; the reduced rates (14% and 10%) did not change. dim_product.vat_class says which rate applies to an article. The dictionary does not say how returns enter a figure including VAT; fact_return_line carries refund_gross, so show refunds as their own column and say what you sent.

<!-- facts: REG-RETURN-LAG -->
Returns can arrive up to 30 days after a sale, so a sale-week cohort is not complete until about five weeks later. Return lines are booked where they are processed: web returns sent by post are booked to the web shop.

<!-- facts: DEF-GROSS-MARGIN -->
Gross margin is net sales minus the standard cost of the goods sold, both after returns: returned units are credited back at standard cost (standard_cost_returned). Gross margin percentage is gross margin divided by net sales.

<!-- facts: DEF-RETURN-RATE -->
Return rate is returned net (refund_net) divided by sold net, grouped by the fiscal week of the original sale. This is the sale-week cohort: a return counts in the week the item was sold, whenever it came back. That is a different date convention from net sales, on purpose. The accepted queries (REQ-D14 to REQ-D16) select the sold lines by the fiscal period of fact_sales_line.sale_date, then add the refunds matched through sales_line_id, wherever and whenever they were booked; web against stores is `CASE WHEN s.store_id = 900`.

<!-- facts: DEF-ATV -->
ATV (average transaction value) is net sales before returns divided by the number of sales receipts. It is a store measure: staff purchases, store 999 and test articles are left out, and web orders are not included. The accepted queries use store_id below 900 and NOT staff_purchase_flag, dated by sale_date.

<!-- facts: DEF-STORE-SCOPE -->
Store counts and store-level analyses cover the physical stores only (store_id below 900). The web shop (store 900) is shown as its own line when a request asks for the total company. Store 999 is never included.

<!-- facts: DEF-STORE-LEAGUE -->
The store league table ranks stores by net sales per trading day. Trading days are the days the store was open: after opening, before closure, outside refit closures and not a closed holiday. A store that traded for only part of the period is still listed, with its own trading days.

## 5. Web sales and orders

<!-- facts: DEF-WEB-RECOGNITION, REG-WEB-SALE-DATE -->
Web sales are recognised on the dispatch date in Helsinki time. On a web line, sale_date is the order date and is not used for web net sales. Get the dispatch date by joining fact_web_order on receipt_id = web_order_id.

<!-- facts: DEF-WEB-CANCELLED, REG-CANCELLED -->
Cancelled orders are not web sales and are not counted as web orders. Cancelled orders stay in fact_web_order with status cancelled, no dispatch time and no sales lines. Orders not yet dispatched have status processing and also have no sales lines until they are dispatched.

<!-- facts: DEF-WEB-ORDER-COUNT -->
Web orders are counted on the order date in Helsinki time. An order that is still processing is counted; a cancelled one is not. Count from fact_web_order, not from sales lines, or processing orders go missing.

<!-- facts: DEF-CLICK-COLLECT -->
Click-and-collect is counted as web. The click-and-collect share is click-and-collect net sales divided by all web net sales. For click-and-collect, dispatch_ts_utc is the time the order was ready for collection, and pickup_store_key is the collection store.

<!-- facts: REG-GUEST-ORDERS -->
Guest web orders (checkout without logging in) have no member key. Logged-in orders carry the member's key.

## 6. History that changes the answer

<!-- facts: REG-REGION-REORG -->
On 28 April 2025 the four regions (South, West, East, North) became five, with the new Capital Region. Six stores changed region: 101 Helsinki Vuosaari, 102 Helsinki Pitäjänmäki, 103 Espoo Lommila, 104 Vantaa Tammisto and 105 Kerava (South to Capital Region), and 114 Kouvola (East to South). As-is, the Capital Region covers those stores in every year; as-was, it does not exist before 28 April 2025.

<!-- facts: REG-OUTDOOR-LIGHTING -->
From 27 October 2025 (FY2025/26 period 7) the outdoor lighting subcategory moved from Garden to Electrical. Each affected article has a new dim_product version from that date. As-is, outdoor lighting is in Electrical for all history.

<!-- facts: REG-STORE-EVENTS -->
Store openings: Tampere Lamminpää (136) opened 2 September 2024; Lohja (137) opened 4 November 2024. Store closure: Savonlinna (129) closed 25 January 2026.

<!-- facts: REG-REFITS -->
Refit closures, each a run of whole fiscal weeks with no sales: Vantaa Tammisto (104), 8 July 2024 to 11 August 2024 (5 weeks); Pori (119), 8 September 2025 to 12 October 2025 (5 weeks); Kuopio (125), 15 June 2026 to 26 July 2026 (6 weeks). They are listed in ref_store_closure.

<!-- facts: REG-MEMBER-VERSIONS -->
dim_member gets a new version when a member's tier, home store or marketing consent changes. Count members by distinct member_id. The member_key on a line is the version at that date.

## 7. Like-for-like (LFL)

<!-- facts: DEF-LFL-BASIS, DEF-LFL-OPEN, DEF-LFL-BOTH-YEARS -->
LFL growth compares net sales in the LFL stores for a period with the same fiscal weeks last year, week by week. It covers physical stores only; the web shop is not part of LFL. A store is in the LFL base for a period only if it had been open at least 52 weeks (364 days) before the first day of the period. A store-week counts only if the store traded in that fiscal week in both years: a week in which the store was shut, for a refit or because it had closed, drops out for that store.

<!-- facts: DEF-LFL-REFIT, DEF-LFL-WEEK53 -->
Refit weeks are taken out for the store concerned, in both years, using ref_store_closure. The store stays in the base for its other weeks. Week 53 is not part of LFL, because it has no comparator week.

<!-- facts: TEAM-LFL-EDGE -->
LFL edge cases. A store back from a refit is excluded for the refit weeks only. The two new stores enter the LFL base on 1 September 2025 (136) and 3 November 2025 (137). The closed store (129) drops out from its closure. Week 53 is never LFL. The web shop is never LFL.

<!-- source: REQ-D06, REQ-D07, REQ-D08, REQ-D09 -->
How the accepted LFL queries apply this: build every physical store x fiscal week for both years, flag each as trading (open_date on or before the week's Monday, close_date on or after its Sunday, no overlap with ref_store_closure), keep store-weeks trading in both years, and test the opening rule as open_date <= first day of the requested range - 364. For a multi-period range that first day is the start of the whole range: REQ-D08 (weeks 27 to 52 of FY2025/26) left Lohja out entirely. Open and close dates come from the current dim_store version.

<!-- facts: DEF-LFL-BASIS, DEF-LFL-OPEN, DEF-LFL-BOTH-YEARS -->
<!-- source: REQ-D06, REQ-D07, REQ-D08, REQ-D09 -->
An LFL answer is one total (this year, last year, growth) unless the request asks for a breakdown. REQ-D06 (Q1), REQ-D07 (P3) and REQ-D09 (YTD to the end of P4) each returned one row; REQ-D08 asked "by region" and got one row per region, as-is.

## 8. Members and campaigns

<!-- facts: DEF-ACTIVE-MEMBER -->
An active member has made at least one purchase in the trailing 52 fiscal weeks, ending with the as-of week and including it, in any channel. Count distinct member_id. The accepted queries (REQ-D29, REQ-D30) take sale_date > as-of Sunday - 364 and <= as-of Sunday, and read the tier from the member version valid on the as-of Sunday.

<!-- facts: DEF-MEMBER-SHARE -->
Member share of sales is net sales before returns on lines linked to a member, divided by all net sales before returns. Receipts without a member, and guest web orders, count as non-member. The accepted member-share queries date web lines on the dispatch date, keep store 999 and ZZ Test out, and show Online as its own region (REQ-D31, REQ-D32).

<!-- facts: DEF-NEW-MEMBER -->
A new member is counted on their join date, at the home store in their first version in dim_member (the store where they enrolled). Online sign-ups sit under store 900.

<!-- facts: DEF-UPLIFT -->
Campaign uplift is the mean net sales per targeted member minus the mean per holdout member, over the campaign window plus seven days. A targeted member has at least one exposure row in the campaign. Members with no sales count as zero, and net sales are before returns, on lines linked to the member.

<!-- facts: REG-EXPOSURE-FANOUT, REG-CONSENT, DEF-NET-SALES-SCOPE, DEF-WEB-RECOGNITION -->
fact_campaign_exposure has one row per contact, so a member can appear several times in one campaign: reduce to one row per member (distinct member_id, through dim_member) before joining to sales. Members are contacted only if they have marketing consent on the contact date. Holdout members (10% of each mailing list) are never contacted. campaign_holdout holds member_id, not member_key. Apply the net-sales dating and exclusions to the members' lines (web on the dispatch date, store 999 and ZZ Test out), and check that no member is in both groups.

## 9. Stock

<!-- facts: DEF-STOCK-SEMIADD -->
Closing stock is a snapshot at the end of each fiscal week. Add it across stores and products, but never across weeks. For a period, use the average of the weekly closings or the last week's closing, whichever the request asks for. Sum within each week first, then average or take the last week.

<!-- facts: REG-STOCK-SNAPSHOT, DEF-STORE-SCOPE, REG-TEST-SKU -->
fact_stock_week has one row per store and article for each week-ending Sunday, and only for the articles the store ranges (carries). Web orders are picked from the central warehouse, which is not in this table. Stock by store covers the physical stores (store_id below 900, DEF-STORE-SCOPE) and leaves test articles out (REG-TEST-SKU), on stock and on units sold alike. Check the snapshot rows for your weeks at their grain before you aggregate them.

<!-- facts: DEF-WEEKS-COVER -->
Weeks of cover is the closing stock units at the end of a fiscal week divided by the average weekly units sold over the prior four fiscal weeks, for the same store or grouping. Units sold are the quantity on sales lines, by sale date. Read literally, the prior four weeks are the four weeks before the snapshot week; say so in the answer.

## 10. Before you send

<!-- facts: TEAM-CONTROL-TOTALS, REG-CONTROL-TOTAL, REG-SCD-KEYS, REG-STOCK-SNAPSHOT, CAL-DATA-THROUGH, DEF-TIMEZONE, REG-DEPRECATED -->
Check every answer for:

1. Grain. The result has one row per the keys you meant. Source grains: fact_sales_line one row per receipt line (receipt_id, line_no), fact_stock_week one row per store_key, product_key, week_ending_date, fact_web_order one row per web_order_id. A join to a versioned dimension on its natural key without is_current or validity dates multiplies rows. Check the source rows for the range you use as well as the output.
2. Dates. The result covers the days asked for and nothing outside them, day boundaries are Helsinki midnight, and the range does not run past 4 October 2026 (or say that it does).
3. Objects. Nothing from the deprecated list, no channel_code across 3 November 2025.
4. Control total. Store-level net sales agree with rpt_daily_store_sales over the same days, store by store where you can; if not, find out why before sending. For figures before returns compare with net_sales_before_returns. The check does not apply to a category or member subset, gross figures or ATV (staff purchases out). An unexplained gap cannot go out.
5. Wording. Say which year you read a relative phrase as, as-is or as-was, and any filter that changed a total.

## 11. Example queries from the request history

<!-- facts: DEF-NET-SALES, DEF-WEB-RECOGNITION, CAL-COMPARE, DEF-HIERARCHY-ASIS -->
<!-- source: REQ-D01 -->
The net-sales pattern every sales query starts from. REQ-D01, weekly net sales by region for P6 FY2025/26 against FY2024/25, regions as-is, Online as its own line:

```sql
WITH web_dispatch AS (
    SELECT web_order_id,
           CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
net_lines AS (
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
),
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
```

For margin, group `SUM(n.net_sales - n.cost)` by the current product version (`JOIN dim_product cp ON cp.sku = n.sku AND cp.is_current`), as REQ-D10 to REQ-D13 did. For as-was, take region or category from `s` and `p` (the version on the date), as REQ-D05 did.

<!-- source: REQ-D02, REQ-D03, REQ-D04, REQ-D17, REQ-D19, REQ-D21, REQ-D26, REQ-D27, REQ-D28, REQ-D33, REQ-D34, REQ-D35, REQ-D36, REQ-D37 -->
Other variations in the history: by format, `cs.format` (REQ-D02); total company, drop the region (REQ-D03); by period with week 53 out of the comparison, add `d.fiscal_week <= 52` (REQ-D04); web only, `n.store_id = 900` (REQ-D17, REQ-D19, REQ-D21); one region's products, brands or subcategories, filter `cs.region` and group by the current product version (REQ-D33 to REQ-D36); league tables, `s.store_id < 900` on both halves and no dispatch join (REQ-D37 to REQ-D40). For ATV by format the version on the sale date is fine, since format is the same in every store version (REQ-D26); by weekday, group by dim_date.day_of_week (REQ-D27); one store against the chain, sum per receipt first, then average (REQ-D28).

<!-- facts: DEF-LFL-BASIS, DEF-LFL-OPEN, DEF-LFL-BOTH-YEARS, DEF-LFL-REFIT, TEAM-LFL-EDGE -->
<!-- source: REQ-D07 -->
REQ-D07, LFL for P3 FY2026/27 (weeks 9 to 13): Kuopio counts only for week 13, Savonlinna is out. The `net_lines` CTE is the one above, minus the sku and cost columns.

```sql
WITH store_weeks AS (
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
                WHERE fiscal_year IN ('FY2025/26', 'FY2026/27') AND fiscal_week BETWEEN 9 AND 13) d
    WHERE st.is_current AND st.store_id < 900
),
lfl_store_weeks AS (
    SELECT ty.store_id, ty.fiscal_week
    FROM store_weeks ty
    JOIN store_weeks ly ON ly.store_id = ty.store_id AND ly.fiscal_week = ty.fiscal_week AND ly.fiscal_year = 'FY2025/26'
    JOIN dim_store st   ON st.store_id = ty.store_id AND st.is_current
    WHERE ty.fiscal_year = 'FY2026/27' AND ty.trading AND ly.trading
      AND (st.open_date IS NULL OR st.open_date <= DATE '2026-06-29' - 364)
),
-- web_dispatch and net_lines as in REQ-D01
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
```

<!-- facts: DEF-ATV, REG-STAFF-PURCHASE -->
<!-- source: REQ-D25 -->
REQ-D25, ATV by store for the last period (FY2026/27 P5):

```sql
SELECT cs.store_id, cs.store_name,
       COUNT(DISTINCT f.receipt_id) AS receipts,
       ROUND(SUM(f.net_amount) / COUNT(DISTINCT f.receipt_id), 2) AS atv
FROM fact_sales_line f
JOIN dim_store s   ON s.store_key = f.store_key
JOIN dim_store cs  ON cs.store_id = s.store_id AND cs.is_current
JOIN dim_product p ON p.product_key = f.product_key
JOIN dim_date d    ON d.calendar_date = f.sale_date
WHERE s.store_id < 900
  AND NOT f.staff_purchase_flag
  AND p.category <> 'ZZ Test'
  AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 5
GROUP BY 1, 2
ORDER BY atv DESC;
```

<!-- facts: DEF-CLICK-COLLECT, DEF-WEB-ORDER-COUNT, DEF-WEB-CANCELLED, DEF-TIMEZONE, CAL-RELATIVE -->
<!-- source: REQ-D24 -->
The by-quarter example. REQ-D24, asked 24 March 2026: click-and-collect share of web orders by quarter since the start of FY24/25. Orders on the Helsinki order date, cancelled out, and only the quarters complete when asked:

```sql
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
```

## 12. Request history digest

<!-- source: REQ-D01, REQ-D02, REQ-D03, REQ-D04, REQ-D05, REQ-D06, REQ-D07, REQ-D08, REQ-D09, REQ-D10, REQ-D11, REQ-D12, REQ-D13, REQ-D14, REQ-D15, REQ-D16, REQ-D17, REQ-D18, REQ-D19, REQ-D20, REQ-D21, REQ-D22, REQ-D23, REQ-D24, REQ-D25, REQ-D26, REQ-D27, REQ-D28, REQ-D29, REQ-D30, REQ-D31, REQ-D32, REQ-D33, REQ-D34, REQ-D35, REQ-D36, REQ-D37, REQ-D38, REQ-D39, REQ-D40 -->
The 40 accepted requests, with the reading the requester accepted. Date asked in brackets.

- D01 (2 Dec 2025) weekly net sales by region, P6 this year vs last: FY2025/26 vs FY2024/25 by fiscal week; as-is; Online its own line.
- D02 (1 Sep 2026) sales by format, last four weeks vs last year: FY2026/27 P4 vs P4 by week; format includes Web.
- D03 (14 Apr 2026) total company weekly net sales, Q3 with last year: weeks 27-39; web in; 999 and ZZ Test out.
- D04 (12 May 2026) net sales by region and period, second half of last year vs the year before: FY2025/26 P7-P12 vs FY2024/25; week 53 dropped; as-is.
- D05 (18 Jun 2025) regional net sales by quarter, last year, regions as they were: FY2024/25 as-was (four regions plus Online).
- D06 (20 Aug 2025) LFL for Q1: FY2025/26 weeks 1-13; Tammisto's FY2024/25 refit weeks drop out.
- D07 (11 Aug 2026) LFL for P3 this year: weeks 9-13; Kuopio in for week 13 only; Savonlinna out.
- D08 (19 May 2026) LFL by region, back half of last year: weeks 27-52; Lohja not yet in the base; the closed store only for weeks it traded.
- D09 (8 Sep 2026) YTD LFL as of the end of P4: weeks 1-17, FY2026/27 vs FY2025/26.
- D10 (7 Jul 2026) net sales and gross margin % by category, P2: FY2026/27 P2; margin after returns; as-is.
- D11 (2 Jul 2025) Garden and Electrical gross margin by period, last year: FY2024/25 as-is, outdoor lighting in Electrical all year.
- D12 (23 Jun 2026) top 10 subcategories by gross margin, Q4: FY2025/26 P10-P12 including week 53.
- D13 (12 Nov 2025) Paint & Decorating own label vs brands, first half of FY24/25: P1-P6; current product version.
- D14 (10 Mar 2026) return rate by category, goods sold in the first four periods of last year: FY2025/26 P1-P4; sale-week cohort, complete.
- D15 (24 Sep 2025) Furniture return rate by subcategory, FY24/25 sales: returns attributed back to the sale.
- D16 (21 Jan 2026) return rate web vs stores by category, Q1 sales last year: FY2025/26 Q1; web by store 900; refunds follow the line.
- D17 (3 Dec 2025) daily web sales, Black Friday week: 24-30 Nov 2025 on the Helsinki dispatch date; returns on their own date.
- D18 (13 Jan 2026) web orders per week in P8, not cancelled: FY2025/26; Helsinki order date; processing counts.
- D19 (18 Nov 2025) weekly web sales Aug to end Oct 2025 with the migration week: 4 Aug-9 Nov 2025, whole weeks; web by store 900.
- D20 (4 Dec 2024) web orders by hour on Black Friday, Finnish time: 29 Nov 2024, Helsinki hours.
- D21 (3 Sep 2026) web sales by category for P4, with share of web: FY2026/27 P4; dispatch date; as-is.
- D22 (9 Dec 2025) click-and-collect share of web sales, P1-P4: FY2025/26; denominator all web; fulfilment type from fact_web_order.
- D23 (1 Oct 2026) stores with the most click-and-collect orders last period, and share: P5 (31 Aug-27 Sep 2026); collected; ready-for-collection date, Helsinki.
- D24 (24 Mar 2026) click-and-collect share of web orders by quarter since FY24/25: Helsinki order date; cancelled out; quarters complete when asked (to 25 Jan 2026).
- D25 (30 Sep 2026) ATV by store, last period: FY2026/27 P5.
- D26 (20 May 2025) ATV by format, each quarter of FY24/25: format is the same in every store version.
- D27 (7 Apr 2026) ATV by weekday, P11: FY2025/26 weeks 44-47.
- D28 (27 May 2026) Pori ATV vs the chain by period, second half of last year: Pori is store 119; FY2025/26 P7-P12.
- D29 (6 May 2025) active members at the end of last year: as of Sunday 27 Apr 2025; distinct member_id.
- D30 (8 Oct 2025) active members by tier, last Sunday of September: 28 Sep 2025; tier from the version valid that day.
- D31 (14 May 2025) member share by month, November to April: 1 Nov 2024-27 Apr 2025; before returns; web on dispatch date.
- D32 (9 Jun 2026) member share by region, P1 this year: FY2026/27 P1; as-is with Online.
- D33 (10 Feb 2026) top 10 products by margin in the North, first half of last year: FY2025/26 P1-P6; North as-is; web not in the North.
- D34 (18 Aug 2026) top 10 brands by gross margin in the Capital Region, P1-P3 this year: FY2026/27; as-is.
- D35 (26 May 2026) top 5 subcategories by margin in the East, second half of last year: FY2025/26 P7-P12 with week 53; East as-is (no Kouvola).
- D36 (9 Jul 2025) top 10 own-label products by margin in the West, Q4 FY24/25: P10-P12; current product version.
- D37 (9 Sep 2025) store league table, P4: FY2025/26 P4; net sales per trading day; stores only.
- D38 (3 Feb 2026) league table for Q3, new and closed stores marked: every store that traded kept; Savonlinna closed in week 39.
- D39 (3 Jun 2025) league table for the Large stores, second half of FY24/25: format = 'Large'; closed holidays are not trading days.
- D40 (19 Aug 2026) league table for P3 with Kuopio's refit: Kuopio ranked on the days it traded.
