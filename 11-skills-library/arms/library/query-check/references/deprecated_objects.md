# Deprecated objects

The list `query_check.py` scans for.

<!-- facts: REG-DEPRECATED -->
Do not use: dim_store_old and dim_product_old (flat tables from before the history was kept), every stg_ table (staging), every bak_ table (dated backups), every tmp_ table, rpt_weekly_sales_by_region (it stopped refreshing on 27 April 2025 and uses the old regions), rpt.v_daily_sales and rpt.v_weekly_store_sales.

<!-- facts: TEAM-NO-LEGACY-VIEW, REG-LEGACY-VIEW -->
Do not use rpt.v_daily_sales. It is built on channel_code and from 3 November 2025 it silently leaves out web sales. rpt.v_weekly_store_sales is built on it and has the same gap. Some dashboards still use them.

<!-- facts: REG-MIGRATION -->
The web platform migrated on 3 November 2025. channel_code stops being filled from that date and channel_id is used instead. Click-and-collect gets its own key (3). Before the migration, click-and-collect orders carry channel_code WB and no channel_id. So neither channel column works across the migration: use store_id 900 for web and fact_web_order.fulfilment_type for click-and-collect.

<!-- source: schema_ddl.sql -->
In this warehouse those rules cover: dim_store_old, dim_product_old, stg_campaign_contact_load, stg_member_updates, stg_product_feed, stg_return_line_load, stg_sales_line_load, stg_stock_snapshot, stg_web_order_load, bak_dim_campaign_2025, bak_dim_product_20251026, bak_dim_store_2025, tmp_lfl_store_list_2024, tmp_lfl_store_list_2025, tmp_outdoor_lighting_skus, tmp_region_map, rpt_weekly_sales_by_region, rpt.v_daily_sales, rpt.v_weekly_store_sales. A query that names any of them fails the check; channel_code is a warning, because it is correct before 3 November 2025 and silently empty after.
