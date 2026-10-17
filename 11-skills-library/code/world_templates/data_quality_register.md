# Data quality register

Tuomimetsä Oy, Data & Analytics wiki. The team's known-issues log: things about the warehouse that are not obvious from the tables and have caught people out. Add an entry when you find another one.

## Web platform migration and the legacy view

<!-- facts: REG-MIGRATION -->
The web platform migrated on {{migration_date}}. The column channel_code stops being filled from that date and channel_id is used instead. Click-and-collect gets its own key (3). Before the migration, click-and-collect orders carry channel_code WB and no channel_id.

<!-- facts: REG-LEGACY-VIEW -->
The view rpt.v_daily_sales is built on channel_code. From {{migration_date}} it silently leaves out web sales, and rpt.v_weekly_store_sales, which is built on it, has the same gap. Do not use either of them. Some dashboards still do.

<!-- facts: REG-STORE-900 -->
The web shop is a pseudo-store, store_id {{web_store_id}} (region Online, format Web), so that web lines and web returns have a store key. Web lines are told apart by store_id, not by channel_code.

<!-- facts: REG-WEB-SALE-DATE -->
On web lines, sale_date is the order date. The revenue date is the dispatch date, which you get by joining fact_web_order on receipt_id = web_order_id.

## Exclusions

<!-- facts: REG-STORE-999 -->
Store {{training_store_id}} is the training store. It holds test-article and staff-training transactions only and is left out of all sales reporting.

<!-- facts: REG-TEST-SKU -->
Test articles sit in category {{test_category}}. They are sold in store {{training_store_id}} and in a few web test orders, and are left out of all reporting.

<!-- facts: REG-STAFF-PURCHASE -->
The column staff_purchase_flag is set on every line of a staff receipt (staff get {{staff_discount}} off). Staff purchases count in net sales and are excluded from ATV.

<!-- facts: REG-CANCELLED -->
Cancelled web orders stay in fact_web_order with status cancelled, no dispatch time and no sales lines. Orders not yet dispatched have status processing, and also have no sales lines until they are dispatched.

<!-- facts: REG-GUEST-ORDERS -->
Guest web orders (checkout without logging in) have no member key. Logged-in orders carry the member's key.

## Time

<!-- facts: REG-UTC -->
Columns ending _ts_utc hold UTC. The column sale_date is the Helsinki business date of the sale. Finland is UTC+2 in winter and UTC+3 in summer. The clocks changed on {{first_clock_change}} and {{second_clock_change}}, among other dates.

## History that changes the answer

<!-- facts: REG-SCD-KEYS -->
dim_store, dim_product and dim_member keep one row per version. The fact tables carry the version key (store_key, product_key, member_key) that was valid on the transaction date. The natural keys store_id, sku and member_id are stable across versions. Count distinct natural keys, and join between versions only on the validity dates, or rows multiply.

<!-- facts: REG-REGION-REORG -->
On {{reorg_date}} the four regions (South, West, East, North) became five, with the new Capital Region. {{n_moved}} stores changed region: {{moved_stores}}.

<!-- facts: REG-OUTDOOR-LIGHTING -->
From {{category_move_date}} (FY2025/26 period 7) the outdoor lighting subcategory moved from Garden to Electrical. Each affected article has a new dim_product version from that date.

<!-- facts: REG-STORE-EVENTS -->
Store openings: {{new_store_1}}; {{new_store_2}}. Store closure: {{closed_store}}.

<!-- facts: REG-REFITS -->
Refit closures, each a run of whole fiscal weeks with no sales: {{refits_text}}. They are listed in ref_store_closure.

<!-- facts: REG-VAT-CHANGE -->
The general VAT rate rose from {{vat_standard_before}} to {{vat_standard_after}} on {{vat_change_date}}. The reduced rates ({{vat_reduced_a}} and {{vat_reduced_b}}) did not change. The rate is stored on each line, and dim_product.vat_class says which rate applies to an article.

## Members and campaigns

<!-- facts: REG-MEMBER-VERSIONS -->
dim_member gets a new version when a member's tier, home store or marketing consent changes. Count members by distinct member_id. The member_key on a line is the version at that date.

<!-- facts: REG-EXPOSURE-FANOUT -->
fact_campaign_exposure has one row per contact, so a member can appear several times in one campaign. Reduce to one row per member (distinct member_id) before joining to sales.

<!-- facts: REG-CONSENT -->
Members are contacted only if they have marketing consent on the contact date. Holdout members ({{holdout_pct}} of each mailing list) are never contacted. The table campaign_holdout holds member_id, not member_key.

## Stock and returns

<!-- facts: REG-STOCK-SNAPSHOT -->
fact_stock_week has one row per store and article for each week-ending Sunday, and only for the articles the store ranges (carries). Web orders are picked from the central warehouse, which is not in this table.

<!-- facts: REG-RETURN-LAG -->
Returns can arrive up to {{return_window_days}} days after a sale, so a sale-week cohort is not complete until about five weeks later. Return lines are booked where they are processed: web returns sent by post are booked to the web shop.

## Reporting objects

<!-- facts: REG-CONTROL-TOTAL -->
The table rpt_daily_store_sales holds net sales per store per business day on the company definition (web on its dispatch date, returns on their return date). It has no product, member or channel dimension. Use it as a control total for store-level figures.

<!-- facts: REG-DEPRECATED -->
Do not use: dim_store_old and dim_product_old (flat tables from before the history was kept), every stg_ table (staging), every bak_ table (dated backups), every tmp_ table, rpt_weekly_sales_by_region (it stopped refreshing on {{legacy_report_last}} and uses the old regions), rpt.v_daily_sales and rpt.v_weekly_store_sales.
