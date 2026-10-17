-- Daily web net sales on the Helsinki dispatch date, returns booked to the web shop on their own date.
-- facts: DEF-WEB-RECOGNITION, DEF-WEB-CANCELLED, DEF-TIMEZONE, REG-WEB-SALE-DATE, REG-STORE-900, REG-CANCELLED,
--        REG-RETURN-LAG, REG-MIGRATION, DEF-CLICK-COLLECT, DEF-NET-SALES, REG-TEST-SKU
-- Pattern from REQ-D17 (Black Friday week) and REQ-D19 (weekly, across the 3 November 2025 migration).
-- Web = store_id 900, never channel_code (empty from the migration). Click-and-collect is web.
-- Grain of the output: business_date.
WITH params AS (
    SELECT DATE '2025-11-24' AS start_date, DATE '2025-11-30' AS end_date      -- Black Friday week 2025
),
web_dispatch AS (
    SELECT web_order_id,
           CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
net_lines AS (
    SELECT COALESCE(w.dispatch_date, f.sale_date) AS business_date, s.store_id, f.net_amount AS net_sales
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
    UNION ALL
    SELECT r.return_date, s.store_id, -r.refund_net
    FROM fact_return_line r
    JOIN dim_store s   ON s.store_key = r.store_key
    JOIN dim_product p ON p.product_key = r.product_key
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
)
SELECT n.business_date, n.store_id, SUM(n.net_sales) AS web_net_sales
FROM net_lines n CROSS JOIN params
WHERE n.store_id = 900
  AND n.business_date BETWEEN params.start_date AND params.end_date
GROUP BY 1, 2
ORDER BY 1;
