---
name: warehouse-map
description: Start here for any Tuomimetsä data request - house rules, which warehouse tables to use, the grain and join keys of each, the web shop (900) and training store (999), versioned dimensions, deprecated objects and UTC timestamps.
---

# Warehouse map

The Tuomimetsä warehouse is a DuckDB file. This skill says which tables to use, what one row means in each, how they join, and the rules the team applies to every request. The other skills hold the definitions and validated SQL for each subject:

| Request is about | Skill |
|---|---|
| Dates, periods, "last period", YTD, comparisons with last year | fiscal-calendar |
| What a metric means | metric-dictionary |
| Net sales, gross/VAT, margin, return rate, ATV | sales-reporting |
| LFL, store league table | lfl-and-store-league |
| As-is or as-was, region and category changes, store openings, closures, refits | store-and-product-history |
| Web sales, web orders, click-and-collect, time zones | web-orders |
| Members, member share, campaigns | loyalty-and-campaigns |
| Closing stock, weeks of cover | stock |
| Checking a query before sending | query-check |

Every skill uses `query-check/scripts/query_check.py` before an answer goes out. Scripts run as `conda run -n <env> python <library>/<skill>/scripts/<script>.py PATH_TO/tuomimetsa.duckdb ...`.

## House rules

<!-- source: metric_dictionary.md -->
If a request needs a number that is not defined in the metric dictionary, ask in the request queue before inventing a definition.

<!-- facts: TEAM-EXPLICIT-REQUEST -->
When a request explicitly asks for something that differs from a company default (gross instead of net, as-was instead of as-is, UTC instead of Helsinki time, and so on), follow the request and say that you did.

<!-- facts: TEAM-ASIS, DEF-HIERARCHY-ASIS -->
Report history as-is unless the requester asks for as-was, and say which one you used. Management reporting restates history on the current hierarchy of store regions and product categories (as-is). As-was means the hierarchy as it stood on the date of the transaction.

<!-- facts: TEAM-EXCLUSIONS -->
Always filter out store 999 and category ZZ Test in sales work, and say so when the filter changes a total.

<!-- facts: TEAM-CONTROL-TOTALS, REG-CONTROL-TOTAL -->
Before sending a store-level figure, check the total against rpt_daily_store_sales for the same days. That table holds net sales per store per business day on the company definition (web on its dispatch date, returns on their return date). It has no product, member or channel dimension, so it is a control total, not a source for analysis. `query_check.py --control` does the comparison.

<!-- facts: TEAM-NO-LEGACY-VIEW, REG-LEGACY-VIEW -->
Do not use rpt.v_daily_sales. It is built on channel_code and from 3 November 2025 it silently leaves out web sales. rpt.v_weekly_store_sales is built on it and has the same gap. Some dashboards still use them.

## Canonical tables

<!-- source: schema_ddl.sql, schema_comments.csv -->
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
| dim_date, ref_fiscal_calendar | day; fiscal period | see the fiscal-calendar skill |

Column-by-column notes are in `references/tables.md`.

<!-- source: schema_comments.csv, REQ-D39 -->
Two column comments in the schema are out of date. dim_store.region says "North, South, East or West"; there are five regions since 28 April 2025, plus Online (store-and-product-history). dim_store.format says "Hyper, Standard or Express", but REQ-D39 filters format = 'Large' and the web shop's format is Web. Look at the distinct values before filtering on either column.

## Versioned dimensions

<!-- facts: REG-SCD-KEYS -->
dim_store, dim_product and dim_member keep one row per version. The fact tables carry the version key (store_key, product_key, member_key) that was valid on the transaction date. The natural keys store_id, sku and member_id are stable across versions. Count distinct natural keys, and join between versions only on the validity dates, or rows multiply. In practice: join the fact's store_key to dim_store for as-was; for as-is, go from there to dim_store again on store_id AND is_current (same for sku and dim_product). valid_to is 9999-12-31 on the current version.

## Web shop, training store, test articles, channels

<!-- facts: REG-STORE-900, REG-STORE-999, REG-TEST-SKU -->
The web shop is a pseudo-store, store_id 900 (region Online, format Web), so that web lines and web returns have a store key. Web lines are told apart by store_id, not by channel_code. Store 999 is the training store: it holds test-article and staff-training transactions only and is left out of all sales reporting. Test articles sit in category ZZ Test; they are sold in store 999 and in a few web test orders, and are left out of all reporting.

<!-- facts: REG-MIGRATION -->
The web platform migrated on 3 November 2025. channel_code stops being filled from that date and channel_id is used instead. Click-and-collect gets its own key (3). Before the migration, click-and-collect orders carry channel_code WB and no channel_id. So neither channel column works across the migration: use store_id 900 for web and fact_web_order.fulfilment_type for click-and-collect.

## Do not use

<!-- facts: REG-DEPRECATED -->
Do not use: dim_store_old and dim_product_old (flat tables from before the history was kept), every stg_ table (staging), every bak_ table (dated backups), every tmp_ table, rpt_weekly_sales_by_region (it stopped refreshing on 27 April 2025 and uses the old regions), rpt.v_daily_sales and rpt.v_weekly_store_sales. `query_check.py` fails any query that touches them.

## Time

<!-- facts: REG-UTC, DEF-TIMEZONE -->
Columns ending _ts_utc hold UTC. sale_date is the Helsinki business date of the sale. Reporting is in Helsinki time and a day changes at local midnight, not at midnight UTC. Finland is UTC+2 in winter and UTC+3 in summer; the clocks changed on 30 March 2025 and 26 October 2025, among other dates. The accepted queries convert with `CAST(timezone('Europe/Helsinki', col AT TIME ZONE 'UTC') AS DATE)`, or `hour(...)` for the hour.

## Past requests

`references/request_history_digest.md` lists the 40 accepted requests with the reading each requester accepted. Look there for a request like the one in hand.
