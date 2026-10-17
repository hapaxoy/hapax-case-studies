-- Click-and-collect share of web net sales by fiscal period.
-- facts: DEF-CLICK-COLLECT, DEF-WEB-RECOGNITION, REG-MIGRATION, REG-STORE-900, REG-RETURN-LAG, DEF-NET-SALES
-- Pattern from REQ-D22. Click-and-collect counts as web, so the denominator is all web net sales.
-- fulfilment_type from fact_web_order works on both sides of the 3 November 2025 migration (before it,
-- click-and-collect lines carry channel_code WB and no channel_id). Refunds booked to the web shop are
-- tied back to the order's fulfilment type.
-- Grain of the output: fiscal_period.
WITH params AS (
    SELECT 'FY2025/26' AS fiscal_year, 1 AS first_period, 4 AS last_period
),
web_dispatch AS (
    SELECT web_order_id,
           CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
web_lines AS (
    SELECT w.dispatch_date AS business_date, o.fulfilment_type, f.net_amount AS net_sales
    FROM fact_sales_line f
    JOIN dim_store s ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    JOIN fact_web_order o ON o.web_order_id = f.receipt_id
    WHERE s.store_id = 900 AND p.category <> 'ZZ Test'
    UNION ALL
    SELECT r.return_date, o.fulfilment_type, -r.refund_net
    FROM fact_return_line r
    JOIN dim_store s ON s.store_key = r.store_key
    JOIN fact_sales_line f ON f.sales_line_id = r.sales_line_id
    JOIN dim_product p ON p.product_key = f.product_key
    JOIN fact_web_order o ON o.web_order_id = f.receipt_id
    WHERE s.store_id = 900 AND p.category <> 'ZZ Test'
)
SELECT d.fiscal_period,
       SUM(CASE WHEN l.fulfilment_type = 'click_and_collect' THEN l.net_sales ELSE 0 END) AS click_collect_net,
       SUM(l.net_sales) AS web_net,
       ROUND(100.0 * SUM(CASE WHEN l.fulfilment_type = 'click_and_collect' THEN l.net_sales ELSE 0 END) / SUM(l.net_sales), 1) AS click_collect_share_pct
FROM web_lines l
JOIN dim_date d ON d.calendar_date = l.business_date
CROSS JOIN params
WHERE d.fiscal_year = params.fiscal_year AND d.fiscal_period BETWEEN params.first_period AND params.last_period
GROUP BY 1
ORDER BY 1;
