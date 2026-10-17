# Data quality register

Tuomimetsä Oy, Data & Analytics wiki. The team's known-issues log: things about the warehouse that are not obvious from the tables and have caught people out. Add an entry when you find another one.

## Web platform migration and the legacy view

<!-- facts: REG-MIGRATION -->
The web platform migrated on 3 November 2025. The column channel_code stops being filled from that date and channel_id is used instead. Click-and-collect gets its own key (3). Before the migration, click-and-collect orders carry channel_code WB and no channel_id.

<!-- facts: REG-LEGACY-VIEW -->
The view rpt.v_daily_sales is built on channel_code. From 3 November 2025 it silently leaves out web sales, and rpt.v_weekly_store_sales, which is built on it, has the same gap. Do not use either of them. Some dashboards still do.

<!-- facts: REG-STORE-900 -->
The web shop is a pseudo-store, store_id 900 (region Online, format Web), so that web lines and web returns have a store key. Web lines are told apart by store_id, not by channel_code.

<!-- facts: REG-WEB-SALE-DATE -->
On web lines, sale_date is the order date. The revenue date is the dispatch date, which you get by joining fact_web_order on receipt_id = web_order_id.

## Exclusions

<!-- facts: REG-STORE-999 -->
Store 999 is the training store. It holds test-article and staff-training transactions only and is left out of all sales reporting.

<!-- facts: REG-TEST-SKU -->
Test articles sit in category ZZ Test. They are sold in store 999 and in a few web test orders, and are left out of all reporting.

<!-- facts: REG-STAFF-PURCHASE -->
The column staff_purchase_flag is set on every line of a staff receipt (staff get 15% off). Staff purchases count in net sales and are excluded from ATV.

<!-- facts: REG-CANCELLED -->
Cancelled web orders stay in fact_web_order with status cancelled, no dispatch time and no sales lines. Orders not yet dispatched have status processing, and also have no sales lines until they are dispatched.

<!-- facts: REG-GUEST-ORDERS -->
Guest web orders (checkout without logging in) have no member key. Logged-in orders carry the member's key.

## Time

<!-- facts: REG-UTC -->
Columns ending _ts_utc hold UTC. The column sale_date is the Helsinki business date of the sale. Finland is UTC+2 in winter and UTC+3 in summer. The clocks changed on 30 March 2025 and 26 October 2025, among other dates.

## History that changes the answer

<!-- facts: REG-SCD-KEYS -->
dim_store, dim_product and dim_member keep one row per version. The fact tables carry the version key (store_key, product_key, member_key) that was valid on the transaction date. The natural keys store_id, sku and member_id are stable across versions. Count distinct natural keys, and join between versions only on the validity dates, or rows multiply.

<!-- facts: REG-REGION-REORG -->
On 28 April 2025 the four regions (South, West, East, North) became five, with the new Capital Region. 6 stores changed region: 101 Helsinki Vuosaari (South to Capital Region); 102 Helsinki Pitäjänmäki (South to Capital Region); 103 Espoo Lommila (South to Capital Region); 104 Vantaa Tammisto (South to Capital Region); 105 Kerava (South to Capital Region); 114 Kouvola (East to South).

<!-- facts: REG-OUTDOOR-LIGHTING -->
From 27 October 2025 (FY2025/26 period 7) the outdoor lighting subcategory moved from Garden to Electrical. Each affected article has a new dim_product version from that date.

<!-- facts: REG-STORE-EVENTS -->
Store openings: Tampere Lamminpää (136), opened 2 September 2024; Lohja (137), opened 4 November 2024. Store closure: Savonlinna (129), closed 25 January 2026.

<!-- facts: REG-REFITS -->
Refit closures, each a run of whole fiscal weeks with no sales: Vantaa Tammisto (104), 8 July 2024 to 11 August 2024 (5 weeks); Pori (119), 8 September 2025 to 12 October 2025 (5 weeks); Kuopio (125), 15 June 2026 to 26 July 2026 (6 weeks). They are listed in ref_store_closure.

<!-- facts: REG-VAT-CHANGE -->
The general VAT rate rose from 24% to 25.5% on 1 September 2024. The reduced rates (14% and 10%) did not change. The rate is stored on each line, and dim_product.vat_class says which rate applies to an article.

## Members and campaigns

<!-- facts: REG-MEMBER-VERSIONS -->
dim_member gets a new version when a member's tier, home store or marketing consent changes. Count members by distinct member_id. The member_key on a line is the version at that date.

<!-- facts: REG-EXPOSURE-FANOUT -->
fact_campaign_exposure has one row per contact, so a member can appear several times in one campaign. Reduce to one row per member (distinct member_id) before joining to sales.

<!-- facts: REG-CONSENT -->
Members are contacted only if they have marketing consent on the contact date. Holdout members (10% of each mailing list) are never contacted. The table campaign_holdout holds member_id, not member_key.

## Stock and returns

<!-- facts: REG-STOCK-SNAPSHOT -->
fact_stock_week has one row per store and article for each week-ending Sunday, and only for the articles the store ranges (carries). Web orders are picked from the central warehouse, which is not in this table.

<!-- facts: REG-RETURN-LAG -->
Returns can arrive up to 30 days after a sale, so a sale-week cohort is not complete until about five weeks later. Return lines are booked where they are processed: web returns sent by post are booked to the web shop.

## Reporting objects

<!-- facts: REG-CONTROL-TOTAL -->
The table rpt_daily_store_sales holds net sales per store per business day on the company definition (web on its dispatch date, returns on their return date). It has no product, member or channel dimension. Use it as a control total for store-level figures.

<!-- facts: REG-DEPRECATED -->
Do not use: dim_store_old and dim_product_old (flat tables from before the history was kept), every stg_ table (staging), every bak_ table (dated backups), every tmp_ table, rpt_weekly_sales_by_region (it stopped refreshing on 27 April 2025 and uses the old regions), rpt.v_daily_sales and rpt.v_weekly_store_sales.
