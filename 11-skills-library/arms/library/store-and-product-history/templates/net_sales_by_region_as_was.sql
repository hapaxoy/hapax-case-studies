-- Net sales by region AS-WAS (the region the store belonged to on the transaction date), by quarter.
-- facts: DEF-HIERARCHY-ASIS, TEAM-ASIS, TEAM-EXPLICIT-REQUEST, REG-SCD-KEYS, REG-REGION-REORG, DEF-NET-SALES
-- Pattern from REQ-D05. Use only when the request asks for as-was ("as they were at the time",
-- "to match the old reports"); the default is as-is (join dim_store on store_id AND is_current).
-- The fact tables carry the store version valid on the transaction date, so joining on store_key
-- gives the as-was region directly.
-- Grain of the output: fiscal_quarter x region.
WITH params AS (
    SELECT 'FY2024/25' AS fiscal_year
),
web_dispatch AS (
    SELECT web_order_id,
           CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
net_lines AS (
    -- as-was: region is the store version valid on the transaction date
    SELECT COALESCE(w.dispatch_date, f.sale_date) AS business_date, s.region, f.net_amount AS net_sales
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
    UNION ALL
    SELECT r.return_date, s.region, -r.refund_net
    FROM fact_return_line r
    JOIN dim_store s   ON s.store_key = r.store_key
    JOIN dim_product p ON p.product_key = r.product_key
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
)
SELECT d.fiscal_quarter, n.region, SUM(n.net_sales) AS net_sales
FROM net_lines n
JOIN dim_date d ON d.calendar_date = n.business_date
CROSS JOIN params
WHERE d.fiscal_year = params.fiscal_year
GROUP BY 1, 2
ORDER BY 1, 2;
