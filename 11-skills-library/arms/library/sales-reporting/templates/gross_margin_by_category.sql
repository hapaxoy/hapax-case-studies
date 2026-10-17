-- Net sales, gross margin and gross margin % by category (as-is) for a fiscal range.
-- facts: DEF-GROSS-MARGIN, DEF-NET-SALES, DEF-NET-SALES-SCOPE, DEF-WEB-RECOGNITION, DEF-HIERARCHY-ASIS,
--        TEAM-ASIS, REG-OUTDOOR-LIGHTING
-- Pattern from REQ-D10 (category), REQ-D11 (by period), REQ-D12 (subcategory top 10), REQ-D13 (own label).
-- Margin is after returns: returned units are credited back at standard cost (standard_cost_returned).
-- Categories come from the current product version (as-is); for as-was use p.category instead of cp.category.
-- Grain of the output: category.
WITH params AS (
    SELECT 'FY2026/27' AS fiscal_year, 2 AS first_period, 2 AS last_period     -- REQ-D10: P2 FY2026/27
),
web_dispatch AS (
    SELECT web_order_id,
           CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
net_lines AS (
    SELECT COALESCE(w.dispatch_date, f.sale_date) AS business_date, s.store_id, p.sku,
           f.net_amount AS net_sales, f.standard_cost AS cost
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
    UNION ALL
    SELECT r.return_date, s.store_id, p.sku, -r.refund_net, -r.standard_cost_returned
    FROM fact_return_line r
    JOIN dim_store s   ON s.store_key = r.store_key
    JOIN dim_product p ON p.product_key = r.product_key
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
),
by_category AS (
    SELECT cp.category, SUM(n.net_sales) AS net_sales, SUM(n.net_sales - n.cost) AS gross_margin
    FROM net_lines n
    JOIN dim_date d     ON d.calendar_date = n.business_date
    JOIN dim_product cp ON cp.sku = n.sku AND cp.is_current
    CROSS JOIN params
    WHERE d.fiscal_year = params.fiscal_year
      AND d.fiscal_period BETWEEN params.first_period AND params.last_period
    GROUP BY 1
)
SELECT category, net_sales, gross_margin, ROUND(100.0 * gross_margin / net_sales, 1) AS gross_margin_pct
FROM by_category
ORDER BY net_sales DESC;
