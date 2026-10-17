-- Weekly net sales by region (as-is), this year against last year, lined up by fiscal week number.
-- facts: DEF-NET-SALES, DEF-NET-SALES-SCOPE, DEF-WEB-RECOGNITION, CAL-COMPARE, CAL-WEEK53, DEF-HIERARCHY-ASIS,
--        TEAM-ASIS, DEF-STORE-SCOPE, REG-STORE-900
-- Pattern from REQ-D01 (by region), REQ-D02 (by format), REQ-D03 (total company), REQ-D04 (by period).
-- Edit params. Week 53 has no comparator: the inner join drops it; say so if the range contains it.
-- To group by format or total company, replace cs.region (format: cs.format; total: drop the column).
-- Grain of the output: fiscal_week x region.
WITH params AS (
    SELECT 'FY2026/27' AS ty_year, 'FY2025/26' AS ly_year,
           18 AS first_week, 21 AS last_week                -- FY2026/27 P05 = weeks 18-21
),
web_dispatch AS (
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
    -- returns reduce net sales on the return date
    SELECT r.return_date, s.store_id, p.sku, -r.refund_net, -r.standard_cost_returned
    FROM fact_return_line r
    JOIN dim_store s   ON s.store_key = r.store_key
    JOIN dim_product p ON p.product_key = r.product_key
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
),
weekly AS (
    -- as-is: region from the current store version (Online = the web shop, its own line)
    SELECT d.fiscal_year, d.fiscal_week, cs.region, SUM(n.net_sales) AS net_sales
    FROM net_lines n
    JOIN dim_date d   ON d.calendar_date = n.business_date
    JOIN dim_store cs ON cs.store_id = n.store_id AND cs.is_current
    CROSS JOIN params
    WHERE d.fiscal_year IN (params.ty_year, params.ly_year)
      AND d.fiscal_week BETWEEN params.first_week AND params.last_week
    GROUP BY 1, 2, 3
)
SELECT ty.fiscal_week, ty.region, ty.net_sales AS this_year, ly.net_sales AS last_year,
       ROUND(100.0 * (ty.net_sales / ly.net_sales - 1), 1) AS growth_pct
FROM weekly ty
CROSS JOIN params
JOIN weekly ly ON ly.fiscal_week = ty.fiscal_week AND ly.region = ty.region AND ly.fiscal_year = params.ly_year
WHERE ty.fiscal_year = params.ty_year
ORDER BY ty.fiscal_week, ty.region;
