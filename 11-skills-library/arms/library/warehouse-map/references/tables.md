# Table and column notes

From the warehouse schema and its column comments. Only the canonical tables are listed; the deprecated ones are in `query-check/references/deprecated_objects.md`.

<!-- source: schema_comments.csv -->
## Facts

**fact_sales_line** - one row per receipt line or web order line.
- sales_line_id: line number. receipt_id: receipt number, equals web_order_id for web lines. line_no: line number within the receipt.
- sale_date: date of sale (the Helsinki business date; on web lines, the order date). sale_ts_utc: time of sale, UTC.
- store_key, product_key, member_key: the dimension versions at the sale date; member_key is null for non-members.
- channel_code: ST = store, WB = web (empty from 3 November 2025). channel_id: sales channel key (dim_channel), filled from the migration.
- quantity: units sold. net_amount: line value in EUR excluding VAT, after line discounts. vat_rate: VAT rate applied to the line. gross_amount: line value in EUR including VAT. standard_cost: standard cost of the units sold, EUR. staff_purchase_flag: true for staff purchases.

**fact_return_line** - one row per returned line.
- return_line_id; sales_line_id: the sales line being returned. return_date, return_ts_utc (UTC).
- store_key: store version at the return date; the web shop for web returns. product_key, member_key: versions at the return date.
- quantity_returned; refund_net (EUR excluding VAT); vat_rate (of the original line); refund_gross (EUR including VAT); standard_cost_returned; reason_code.

**fact_web_order** - one row per web order.
- web_order_id: equals receipt_id on the sales lines. member_key: member version at the order date; null for guest orders. login_state: logged_in or guest.
- order_ts_utc: time the order was placed, UTC. dispatch_ts_utc: time of dispatch, UTC; for click-and-collect, when ready for collection.
- status: delivered, collected, processing or cancelled. fulfilment_type: home_delivery or click_and_collect. pickup_store_key: collection store for click-and-collect orders.
- order_total_gross: order value in EUR including VAT, at order time. line_count: number of lines on the order.

**fact_stock_week** - closing stock per store and SKU at the end of each fiscal week.
- store_key, product_key: versions at the week-ending date. week_ending_date: the Sunday on which stock was counted.
- closing_units; closing_value (at standard cost, EUR); receipts_units (received during the week); adjustment_units (stock-take and write-off adjustments during the week).

**fact_campaign_exposure** - one row per contact made to a member in a campaign.
- exposure_id; campaign_id; member_key (version at the contact date); contact_ts_utc (UTC); contact_channel (email, sms or push); delivered; opened.

**rpt_daily_store_sales** - daily net sales per store, maintained by Data & Analytics.
- business_date; store_id; receipts (with sales on the day); units_sold; net_sales_before_returns; returns_net (refunds booked on the day); net_sales. All EUR excluding VAT.

## Dimensions

**dim_store** - stores and pseudo-locations, one row per version.
- store_key (used by the facts), store_id (stable), store_name, city, region, format, sqm (sales area).
- open_date: null for stores open before 2024. close_date: for closed stores.
- valid_from, valid_to (9999-12-31 for the current version), is_current.

**dim_product** - one row per version.
- product_key (used by the facts), sku (stable), product_name, category, subcategory, brand, own_label_flag.
- vat_class: standard, reduced14 or reduced10. standard_unit_cost: revalued each April.
- listed_from, delisted_on (null if still listed), valid_from, valid_to, is_current.

**dim_member** - loyalty members, one row per version.
- member_key (used by the facts), member_id (loyalty number, stable), join_date, tier (Basic, Silver or Gold), home_store_id (store_id; 900 for online sign-ups), marketing_consent, valid_from, valid_to, is_current.

**dim_channel** - channel_id (used from the web-platform migration), channel_name, channel_group (store or web), legacy_channel_code (the old two-letter code, where there was one).

**dim_campaign** - campaign_id, campaign_name, start_date and end_date (the campaign window), channels (joined with +), target_group, holdout_pct, mailing_list_size (including the holdout), holdout_size.

**campaign_holdout** - campaign_id, member_id (the loyalty number, not member_key).

**ref_store_closure** - planned closures for refits: closure_id, store_id, closure_type, closure_start_date (first closed day), closure_end_date (last closed day), weeks_closed.

**dim_date**, **ref_fiscal_calendar** - see `fiscal-calendar/SKILL.md`.
