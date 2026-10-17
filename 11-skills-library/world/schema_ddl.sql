-- Tuomimetsä Oy warehouse (DuckDB). Object definitions as created, with the comments the warehouse carries.

CREATE TABLE dim_date(calendar_date DATE, day_of_week INTEGER, day_name VARCHAR, calendar_year INTEGER, calendar_month INTEGER, fiscal_year VARCHAR, fiscal_year_start_date DATE, fiscal_quarter INTEGER, fiscal_period INTEGER, fiscal_period_label VARCHAR, fiscal_week INTEGER, fiscal_week_start_date DATE, fiscal_week_end_date DATE, weeks_in_fiscal_year INTEGER, is_53_week_year BOOLEAN, is_public_holiday BOOLEAN, holiday_name VARCHAR, is_trading_day BOOLEAN);
COMMENT ON TABLE dim_date IS 'Calendar and fiscal calendar, one row per day';
COMMENT ON COLUMN dim_date.calendar_date IS 'Calendar date';
COMMENT ON COLUMN dim_date.day_of_week IS 'ISO weekday, 1 = Monday';
COMMENT ON COLUMN dim_date.day_name IS 'Weekday name';
COMMENT ON COLUMN dim_date.calendar_year IS 'Calendar year';
COMMENT ON COLUMN dim_date.calendar_month IS 'Calendar month number';
COMMENT ON COLUMN dim_date.fiscal_year IS 'Fiscal year label, e.g. FY2025/26';
COMMENT ON COLUMN dim_date.fiscal_year_start_date IS 'First day of the fiscal year';
COMMENT ON COLUMN dim_date.fiscal_quarter IS 'Fiscal quarter, 1 to 4';
COMMENT ON COLUMN dim_date.fiscal_period IS 'Fiscal period, 1 to 12';
COMMENT ON COLUMN dim_date.fiscal_period_label IS 'Fiscal year and period, e.g. FY2025/26 P05';
COMMENT ON COLUMN dim_date.fiscal_week IS 'Fiscal week number within the fiscal year';
COMMENT ON COLUMN dim_date.fiscal_week_start_date IS 'Monday of the fiscal week';
COMMENT ON COLUMN dim_date.fiscal_week_end_date IS 'Sunday of the fiscal week';
COMMENT ON COLUMN dim_date.weeks_in_fiscal_year IS 'Number of weeks in the fiscal year';
COMMENT ON COLUMN dim_date.is_53_week_year IS 'True for a 53-week fiscal year';
COMMENT ON COLUMN dim_date.is_public_holiday IS 'Finnish public holiday';
COMMENT ON COLUMN dim_date.holiday_name IS 'Holiday name';
COMMENT ON COLUMN dim_date.is_trading_day IS 'False on days the stores are shut by law or company rule';

CREATE TABLE ref_fiscal_calendar(fiscal_year VARCHAR, fiscal_period INTEGER, fiscal_quarter INTEGER, fiscal_period_label VARCHAR, period_start_date DATE, period_end_date DATE, weeks_in_period INTEGER, first_fiscal_week INTEGER, last_fiscal_week INTEGER, fully_loaded BOOLEAN);
COMMENT ON TABLE ref_fiscal_calendar IS 'Fiscal periods with start and end dates';
COMMENT ON COLUMN ref_fiscal_calendar.fiscal_year IS 'Fiscal year label';
COMMENT ON COLUMN ref_fiscal_calendar.fiscal_period IS 'Period number, 1 to 12';
COMMENT ON COLUMN ref_fiscal_calendar.fiscal_quarter IS 'Quarter number, 1 to 4';
COMMENT ON COLUMN ref_fiscal_calendar.fiscal_period_label IS 'Fiscal year and period';
COMMENT ON COLUMN ref_fiscal_calendar.period_start_date IS 'First day of the period';
COMMENT ON COLUMN ref_fiscal_calendar.period_end_date IS 'Last day of the period';
COMMENT ON COLUMN ref_fiscal_calendar.weeks_in_period IS 'Weeks in the period';
COMMENT ON COLUMN ref_fiscal_calendar.first_fiscal_week IS 'First fiscal week number in the period';
COMMENT ON COLUMN ref_fiscal_calendar.last_fiscal_week IS 'Last fiscal week number in the period';
COMMENT ON COLUMN ref_fiscal_calendar.fully_loaded IS 'True when the whole period is in the warehouse';

CREATE TABLE dim_store(store_key INTEGER, store_id INTEGER, store_name VARCHAR, city VARCHAR, region VARCHAR, format VARCHAR, sqm INTEGER, open_date DATE, close_date DATE, valid_from DATE, valid_to DATE, is_current BOOLEAN);
COMMENT ON TABLE dim_store IS 'Stores and pseudo-locations (slowly changing, one row per version)';
COMMENT ON COLUMN dim_store.store_key IS 'Surrogate key of the store version, used by the fact tables';
COMMENT ON COLUMN dim_store.store_id IS 'Store number, stable across versions';
COMMENT ON COLUMN dim_store.store_name IS 'Store name';
COMMENT ON COLUMN dim_store.city IS 'City';
COMMENT ON COLUMN dim_store.region IS 'Sales region: North, South, East or West';
COMMENT ON COLUMN dim_store.format IS 'Store format: Hyper, Standard or Express';
COMMENT ON COLUMN dim_store.sqm IS 'Sales area in square metres';
COMMENT ON COLUMN dim_store.open_date IS 'Opening date; null for stores open before 2024';
COMMENT ON COLUMN dim_store.close_date IS 'Closing date for closed stores';
COMMENT ON COLUMN dim_store.valid_from IS 'First day this version applies';
COMMENT ON COLUMN dim_store.valid_to IS 'Last day this version applies; 9999-12-31 for the current version';
COMMENT ON COLUMN dim_store.is_current IS 'True for the latest version of the store';

CREATE TABLE ref_store_closure(closure_id INTEGER, store_id INTEGER, closure_type VARCHAR, closure_start_date DATE, closure_end_date DATE, weeks_closed INTEGER);
COMMENT ON TABLE ref_store_closure IS 'Planned store closures for refits';
COMMENT ON COLUMN ref_store_closure.closure_id IS 'Closure number';
COMMENT ON COLUMN ref_store_closure.store_id IS 'Store number';
COMMENT ON COLUMN ref_store_closure.closure_type IS 'Reason for the closure';
COMMENT ON COLUMN ref_store_closure.closure_start_date IS 'First closed day';
COMMENT ON COLUMN ref_store_closure.closure_end_date IS 'Last closed day';
COMMENT ON COLUMN ref_store_closure.weeks_closed IS 'Whole weeks closed';

CREATE TABLE dim_product(product_key INTEGER, sku INTEGER, product_name VARCHAR, category VARCHAR, subcategory VARCHAR, brand VARCHAR, own_label_flag BOOLEAN, vat_class VARCHAR, standard_unit_cost DECIMAL(10,2), listed_from DATE, delisted_on DATE, valid_from DATE, valid_to DATE, is_current BOOLEAN);
COMMENT ON TABLE dim_product IS 'Products (slowly changing, one row per version)';
COMMENT ON COLUMN dim_product.product_key IS 'Surrogate key of the product version, used by the fact tables';
COMMENT ON COLUMN dim_product.sku IS 'Article number, stable across versions';
COMMENT ON COLUMN dim_product.product_name IS 'Article description';
COMMENT ON COLUMN dim_product.category IS 'Product category';
COMMENT ON COLUMN dim_product.subcategory IS 'Product subcategory';
COMMENT ON COLUMN dim_product.brand IS 'Brand';
COMMENT ON COLUMN dim_product.own_label_flag IS 'True for own-label articles';
COMMENT ON COLUMN dim_product.vat_class IS 'VAT class: standard, reduced14 or reduced10';
COMMENT ON COLUMN dim_product.standard_unit_cost IS 'Standard cost per unit, revalued each April';
COMMENT ON COLUMN dim_product.listed_from IS 'Date the article was listed';
COMMENT ON COLUMN dim_product.delisted_on IS 'Date the article was delisted; null if still listed';
COMMENT ON COLUMN dim_product.valid_from IS 'First day this version applies';
COMMENT ON COLUMN dim_product.valid_to IS 'Last day this version applies; 9999-12-31 for the current version';
COMMENT ON COLUMN dim_product.is_current IS 'True for the latest version of the article';

CREATE TABLE dim_member(member_key INTEGER, member_id BIGINT, join_date DATE, tier VARCHAR, home_store_id INTEGER, marketing_consent BOOLEAN, valid_from DATE, valid_to DATE, is_current BOOLEAN);
COMMENT ON TABLE dim_member IS 'Loyalty members (slowly changing, one row per version)';
COMMENT ON COLUMN dim_member.member_key IS 'Surrogate key of the member version, used by the fact tables';
COMMENT ON COLUMN dim_member.member_id IS 'Loyalty number, stable across versions';
COMMENT ON COLUMN dim_member.join_date IS 'Date the member joined';
COMMENT ON COLUMN dim_member.tier IS 'Loyalty tier: Basic, Silver or Gold';
COMMENT ON COLUMN dim_member.home_store_id IS 'Member's home store (store_id); 900 for online sign-ups';
COMMENT ON COLUMN dim_member.marketing_consent IS 'True if the member accepts marketing contact';
COMMENT ON COLUMN dim_member.valid_from IS 'First day this version applies';
COMMENT ON COLUMN dim_member.valid_to IS 'Last day this version applies; 9999-12-31 for the current version';
COMMENT ON COLUMN dim_member.is_current IS 'True for the latest version of the member';

CREATE TABLE dim_channel(channel_id INTEGER, channel_name VARCHAR, channel_group VARCHAR, legacy_channel_code VARCHAR);
COMMENT ON TABLE dim_channel IS 'Sales channels';
COMMENT ON COLUMN dim_channel.channel_id IS 'Channel key, used from the web-platform migration';
COMMENT ON COLUMN dim_channel.channel_name IS 'Channel name';
COMMENT ON COLUMN dim_channel.channel_group IS 'store or web';
COMMENT ON COLUMN dim_channel.legacy_channel_code IS 'Old two-letter code, where there was one';

CREATE TABLE dim_campaign(campaign_id INTEGER, campaign_name VARCHAR, start_date DATE, end_date DATE, channels VARCHAR, target_group VARCHAR, holdout_pct DECIMAL(4,3), mailing_list_size INTEGER, holdout_size INTEGER);
COMMENT ON TABLE dim_campaign IS 'Marketing campaigns';
COMMENT ON COLUMN dim_campaign.campaign_id IS 'Campaign number';
COMMENT ON COLUMN dim_campaign.campaign_name IS 'Campaign name';
COMMENT ON COLUMN dim_campaign.start_date IS 'First day of the campaign window';
COMMENT ON COLUMN dim_campaign.end_date IS 'Last day of the campaign window';
COMMENT ON COLUMN dim_campaign.channels IS 'Contact channels used, joined with +';
COMMENT ON COLUMN dim_campaign.target_group IS 'Description of the target group';
COMMENT ON COLUMN dim_campaign.holdout_pct IS 'Share of the mailing list held out';
COMMENT ON COLUMN dim_campaign.mailing_list_size IS 'Members on the mailing list, including the holdout';
COMMENT ON COLUMN dim_campaign.holdout_size IS 'Members held out';

CREATE TABLE campaign_holdout(campaign_id INTEGER, member_id BIGINT);
COMMENT ON TABLE campaign_holdout IS 'Members held out from a campaign';
COMMENT ON COLUMN campaign_holdout.campaign_id IS 'Campaign number';
COMMENT ON COLUMN campaign_holdout.member_id IS 'Loyalty number (member_id, not member_key)';

CREATE TABLE fact_sales_line(sales_line_id BIGINT, receipt_id BIGINT, line_no INTEGER, sale_date DATE, sale_ts_utc TIMESTAMP, store_key INTEGER, product_key INTEGER, member_key INTEGER, channel_code VARCHAR, channel_id INTEGER, quantity INTEGER, net_amount DECIMAL(14,2), vat_rate DECIMAL(5,4), gross_amount DECIMAL(14,2), standard_cost DECIMAL(14,2), staff_purchase_flag BOOLEAN, etl_loaded_at TIMESTAMP);
COMMENT ON TABLE fact_sales_line IS 'One row per receipt line or web order line';
COMMENT ON COLUMN fact_sales_line.sales_line_id IS 'Line number';
COMMENT ON COLUMN fact_sales_line.receipt_id IS 'Receipt number; equals web_order_id for web lines';
COMMENT ON COLUMN fact_sales_line.line_no IS 'Line number within the receipt';
COMMENT ON COLUMN fact_sales_line.sale_date IS 'Date of sale';
COMMENT ON COLUMN fact_sales_line.sale_ts_utc IS 'Time of sale, UTC';
COMMENT ON COLUMN fact_sales_line.store_key IS 'Store version at the sale date (dim_store.store_key)';
COMMENT ON COLUMN fact_sales_line.product_key IS 'Product version at the sale date (dim_product.product_key)';
COMMENT ON COLUMN fact_sales_line.member_key IS 'Member version at the sale date; null for non-members';
COMMENT ON COLUMN fact_sales_line.channel_code IS 'Sales channel: ST = store, WB = web';
COMMENT ON COLUMN fact_sales_line.channel_id IS 'Sales channel key (dim_channel)';
COMMENT ON COLUMN fact_sales_line.quantity IS 'Units sold';
COMMENT ON COLUMN fact_sales_line.net_amount IS 'Line value in EUR excluding VAT, after line discounts';
COMMENT ON COLUMN fact_sales_line.vat_rate IS 'VAT rate applied to the line';
COMMENT ON COLUMN fact_sales_line.gross_amount IS 'Line value in EUR including VAT';
COMMENT ON COLUMN fact_sales_line.standard_cost IS 'Standard cost of the units sold, EUR';
COMMENT ON COLUMN fact_sales_line.staff_purchase_flag IS 'True for staff purchases';

CREATE TABLE fact_return_line(return_line_id BIGINT, sales_line_id BIGINT, return_date DATE, return_ts_utc TIMESTAMP, store_key INTEGER, product_key INTEGER, member_key INTEGER, quantity_returned INTEGER, refund_net DECIMAL(14,2), vat_rate DECIMAL(5,4), refund_gross DECIMAL(14,2), standard_cost_returned DECIMAL(14,2), reason_code VARCHAR);
COMMENT ON TABLE fact_return_line IS 'One row per returned line';
COMMENT ON COLUMN fact_return_line.return_line_id IS 'Return line number';
COMMENT ON COLUMN fact_return_line.sales_line_id IS 'The sales line being returned';
COMMENT ON COLUMN fact_return_line.return_date IS 'Date of return';
COMMENT ON COLUMN fact_return_line.return_ts_utc IS 'Time of return, UTC';
COMMENT ON COLUMN fact_return_line.store_key IS 'Store version at the return date; the web shop for web returns';
COMMENT ON COLUMN fact_return_line.product_key IS 'Product version at the return date';
COMMENT ON COLUMN fact_return_line.member_key IS 'Member version at the return date; null for non-members';
COMMENT ON COLUMN fact_return_line.quantity_returned IS 'Units returned';
COMMENT ON COLUMN fact_return_line.refund_net IS 'Refund in EUR excluding VAT';
COMMENT ON COLUMN fact_return_line.vat_rate IS 'VAT rate of the original line';
COMMENT ON COLUMN fact_return_line.refund_gross IS 'Refund in EUR including VAT';
COMMENT ON COLUMN fact_return_line.standard_cost_returned IS 'Standard cost of the units returned, EUR';
COMMENT ON COLUMN fact_return_line.reason_code IS 'Reason given for the return';

CREATE TABLE fact_web_order(web_order_id BIGINT, member_key INTEGER, login_state VARCHAR, order_ts_utc TIMESTAMP, dispatch_ts_utc TIMESTAMP, status VARCHAR, fulfilment_type VARCHAR, pickup_store_key INTEGER, order_total_gross DECIMAL(14,2), line_count INTEGER);
COMMENT ON TABLE fact_web_order IS 'One row per web order';
COMMENT ON COLUMN fact_web_order.web_order_id IS 'Order number; equals receipt_id on the sales lines';
COMMENT ON COLUMN fact_web_order.member_key IS 'Member version at the order date; null for guest orders';
COMMENT ON COLUMN fact_web_order.login_state IS 'logged_in or guest';
COMMENT ON COLUMN fact_web_order.order_ts_utc IS 'Time the order was placed, UTC';
COMMENT ON COLUMN fact_web_order.dispatch_ts_utc IS 'Time of dispatch, UTC; for click-and-collect, when ready for collection';
COMMENT ON COLUMN fact_web_order.status IS 'delivered, collected, processing or cancelled';
COMMENT ON COLUMN fact_web_order.fulfilment_type IS 'home_delivery or click_and_collect';
COMMENT ON COLUMN fact_web_order.pickup_store_key IS 'Collection store for click-and-collect orders';
COMMENT ON COLUMN fact_web_order.order_total_gross IS 'Order value in EUR including VAT, at order time';
COMMENT ON COLUMN fact_web_order.line_count IS 'Number of lines on the order';

CREATE TABLE fact_stock_week(store_key INTEGER, product_key INTEGER, week_ending_date DATE, closing_units INTEGER, closing_value DECIMAL(14,2), receipts_units INTEGER, adjustment_units INTEGER, etl_loaded_at TIMESTAMP);
COMMENT ON TABLE fact_stock_week IS 'Closing stock per store and SKU at the end of each fiscal week';
COMMENT ON COLUMN fact_stock_week.store_key IS 'Store version at the week-ending date';
COMMENT ON COLUMN fact_stock_week.product_key IS 'Product version at the week-ending date';
COMMENT ON COLUMN fact_stock_week.week_ending_date IS 'Sunday on which the stock was counted';
COMMENT ON COLUMN fact_stock_week.closing_units IS 'Units in stock at the end of the week';
COMMENT ON COLUMN fact_stock_week.closing_value IS 'Closing stock at standard cost, EUR';
COMMENT ON COLUMN fact_stock_week.receipts_units IS 'Units received into the store during the week';
COMMENT ON COLUMN fact_stock_week.adjustment_units IS 'Stock-take and write-off adjustments during the week';

CREATE TABLE fact_campaign_exposure(exposure_id BIGINT, campaign_id INTEGER, member_key INTEGER, contact_ts_utc TIMESTAMP, contact_channel VARCHAR, delivered BOOLEAN, opened BOOLEAN);
COMMENT ON TABLE fact_campaign_exposure IS 'One row per contact made to a member in a campaign';
COMMENT ON COLUMN fact_campaign_exposure.exposure_id IS 'Contact number';
COMMENT ON COLUMN fact_campaign_exposure.campaign_id IS 'Campaign number';
COMMENT ON COLUMN fact_campaign_exposure.member_key IS 'Member version at the contact date';
COMMENT ON COLUMN fact_campaign_exposure.contact_ts_utc IS 'Time of contact, UTC';
COMMENT ON COLUMN fact_campaign_exposure.contact_channel IS 'email, sms or push';
COMMENT ON COLUMN fact_campaign_exposure.delivered IS 'Contact was delivered';
COMMENT ON COLUMN fact_campaign_exposure.opened IS 'Contact was opened';

CREATE TABLE rpt_daily_store_sales(business_date DATE, store_id INTEGER, receipts INTEGER, units_sold BIGINT, net_sales_before_returns DECIMAL(14,2), returns_net DECIMAL(14,2), net_sales DECIMAL(14,2));
COMMENT ON TABLE rpt_daily_store_sales IS 'Daily net sales per store, maintained by Data & Analytics';
COMMENT ON COLUMN rpt_daily_store_sales.business_date IS 'Business date';
COMMENT ON COLUMN rpt_daily_store_sales.store_id IS 'Store number';
COMMENT ON COLUMN rpt_daily_store_sales.receipts IS 'Receipts with sales on the day';
COMMENT ON COLUMN rpt_daily_store_sales.units_sold IS 'Units sold on the day';
COMMENT ON COLUMN rpt_daily_store_sales.net_sales_before_returns IS 'Net sales before returns, EUR excluding VAT';
COMMENT ON COLUMN rpt_daily_store_sales.returns_net IS 'Refunds booked on the day, EUR excluding VAT';
COMMENT ON COLUMN rpt_daily_store_sales.net_sales IS 'Net sales, EUR excluding VAT';

CREATE TABLE bak_dim_campaign_2025(campaign_id INTEGER, campaign_name VARCHAR, start_date DATE, end_date DATE, channels VARCHAR, target_group VARCHAR, holdout_pct DECIMAL(4,3), mailing_list_size INTEGER, holdout_size INTEGER);

CREATE TABLE bak_dim_product_20251026(product_key INTEGER, sku INTEGER, product_name VARCHAR, category VARCHAR, subcategory VARCHAR, brand VARCHAR, own_label_flag BOOLEAN, vat_class VARCHAR, standard_unit_cost DECIMAL(10,2), listed_from DATE, delisted_on DATE, valid_from DATE, valid_to DATE, is_current BOOLEAN);

CREATE TABLE bak_dim_store_2025(store_key INTEGER, store_id INTEGER, store_name VARCHAR, city VARCHAR, region VARCHAR, format VARCHAR, sqm INTEGER, open_date DATE, close_date DATE, valid_from DATE, valid_to DATE, is_current BOOLEAN);

CREATE TABLE dim_product_old(sku INTEGER, product_name VARCHAR, category VARCHAR, subcategory VARCHAR, brand VARCHAR);

CREATE TABLE dim_store_old(store_id INTEGER, store_name VARCHAR, region VARCHAR, format VARCHAR, open_date DATE);

CREATE TABLE rpt_weekly_sales_by_region(week_start_date DATE, region VARCHAR, net_sales DECIMAL(38,2));

CREATE TABLE stg_campaign_contact_load(exposure_id BIGINT, campaign_id INTEGER, member_key INTEGER, contact_ts_utc TIMESTAMP, contact_channel VARCHAR, delivered BOOLEAN, opened BOOLEAN);

CREATE TABLE stg_member_updates(member_key INTEGER, member_id BIGINT, join_date DATE, tier VARCHAR, home_store_id INTEGER, marketing_consent BOOLEAN, valid_from DATE, valid_to DATE, is_current BOOLEAN);

CREATE TABLE stg_product_feed(sku INTEGER, product_name VARCHAR, supplier_price DECIMAL(10,2), feed_date DATE);

CREATE TABLE stg_return_line_load(return_line_id BIGINT, sales_line_id BIGINT, return_date DATE, return_ts_utc TIMESTAMP, store_key INTEGER, product_key INTEGER, member_key INTEGER, quantity_returned INTEGER, refund_net DECIMAL(14,2), vat_rate DECIMAL(5,4), refund_gross DECIMAL(14,2), standard_cost_returned DECIMAL(14,2), reason_code VARCHAR);

CREATE TABLE stg_sales_line_load(sales_line_id BIGINT, receipt_id BIGINT, line_no INTEGER, sale_date DATE, sale_ts_utc TIMESTAMP, store_key INTEGER, product_key INTEGER, member_key INTEGER, channel_code VARCHAR, channel_id INTEGER, quantity INTEGER, net_amount DECIMAL(14,2), vat_rate DECIMAL(5,4), gross_amount DECIMAL(14,2), standard_cost DECIMAL(14,2), staff_purchase_flag BOOLEAN, etl_loaded_at TIMESTAMP);

CREATE TABLE stg_stock_snapshot(store_key INTEGER, product_key INTEGER, week_ending_date DATE, closing_units INTEGER, closing_value DECIMAL(14,2), receipts_units INTEGER, adjustment_units INTEGER, etl_loaded_at TIMESTAMP);

CREATE TABLE stg_web_order_load(web_order_id BIGINT, member_key INTEGER, login_state VARCHAR, order_ts_utc TIMESTAMP, dispatch_ts_utc TIMESTAMP, status VARCHAR, fulfilment_type VARCHAR, pickup_store_key INTEGER, order_total_gross DECIMAL(14,2), line_count INTEGER);

CREATE TABLE tmp_lfl_store_list_2024(store_id INTEGER, store_name VARCHAR);

CREATE TABLE tmp_lfl_store_list_2025(store_id INTEGER, store_name VARCHAR);

CREATE TABLE tmp_outdoor_lighting_skus(sku INTEGER);

CREATE TABLE tmp_region_map(store_id INTEGER, region VARCHAR);

CREATE VIEW rpt.v_daily_sales AS SELECT sale_date, channel, sum(net_amount) AS net_sales, count(DISTINCT receipt_id) AS receipts FROM ((SELECT f.sale_date, 'ST' AS channel, f.net_amount, f.receipt_id FROM fact_sales_line AS f INNER JOIN dim_store AS s ON ((s.store_key = f.store_key)) WHERE (s.store_id < 900)) UNION ALL (SELECT f.sale_date, 'WB' AS channel, f.net_amount, f.receipt_id FROM fact_sales_line AS f WHERE (f.channel_code = 'WB'))) AS u GROUP BY sale_date, channel;

CREATE VIEW rpt.v_weekly_store_sales AS SELECT d.fiscal_year, d.fiscal_week, v.channel, sum(v.net_sales) AS net_sales FROM rpt.v_daily_sales AS v INNER JOIN dim_date AS d ON ((d.calendar_date = v.sale_date)) GROUP BY 1, 2, 3;
