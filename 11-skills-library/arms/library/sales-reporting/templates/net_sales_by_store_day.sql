-- Net sales by store and business day, on the company definition.
-- facts: DEF-NET-SALES, DEF-NET-SALES-SCOPE, DEF-WEB-RECOGNITION, DEF-WEB-CANCELLED, DEF-TIMEZONE,
--        REG-WEB-SALE-DATE, REG-STORE-999, REG-TEST-SKU, REG-STAFF-PURCHASE, REG-CONTROL-TOTAL
-- Pattern from the accepted queries REQ-D01 to REQ-D04 (the net_lines CTE).
-- Edit the params CTE. Grain of the output: one row per business_date x store_id.
-- Check with: query_check.py DB --file this.sql --grain business_date,store_id --start ... --end ... --control
WITH params AS (
    SELECT DATE '2026-08-31' AS start_date,      -- FY2026/27 P05
           DATE '2026-09-27' AS end_date
),
web_dispatch AS (
    -- web revenue date = dispatch date in Helsinki time; cancelled and processing orders have none
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
    -- returns reduce net sales on the return date, at the location that booked them
    SELECT r.return_date, s.store_id, p.sku, -r.refund_net, -r.standard_cost_returned
    FROM fact_return_line r
    JOIN dim_store s   ON s.store_key = r.store_key
    JOIN dim_product p ON p.product_key = r.product_key
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
)
SELECT n.business_date, n.store_id, SUM(n.net_sales) AS net_sales
FROM net_lines n
CROSS JOIN params
WHERE n.business_date BETWEEN params.start_date AND params.end_date
GROUP BY 1, 2
ORDER BY 1, 2;
