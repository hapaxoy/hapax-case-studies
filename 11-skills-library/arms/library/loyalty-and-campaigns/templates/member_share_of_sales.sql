-- Member share of sales by region (as-is), net sales before returns.
-- facts: DEF-MEMBER-SHARE, REG-GUEST-ORDERS, DEF-WEB-RECOGNITION, DEF-NET-SALES-SCOPE, DEF-HIERARCHY-ASIS, DEF-STORE-SCOPE
-- Pattern from REQ-D31 (by month) and REQ-D32 (by region, Online on its own line).
-- Member share = net sales before returns on lines linked to a member / all net sales before returns.
-- Receipts without a member and guest web orders (no member key) count as non-member.
-- Grain of the output: region.
WITH params AS (
    SELECT 'FY2026/27' AS fiscal_year, 1 AS first_period, 1 AS last_period      -- REQ-D32: P1
),
web_dispatch AS (
    SELECT web_order_id,
           CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
lines AS (
    SELECT COALESCE(w.dispatch_date, f.sale_date) AS business_date, s.store_id, f.member_key, f.net_amount
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
)
SELECT cs.region,
       SUM(l.net_amount) AS net_sales_before_returns,
       SUM(CASE WHEN l.member_key IS NOT NULL THEN l.net_amount ELSE 0 END) AS member_net_sales,
       ROUND(100.0 * SUM(CASE WHEN l.member_key IS NOT NULL THEN l.net_amount ELSE 0 END) / SUM(l.net_amount), 1) AS member_share_pct
FROM lines l
JOIN dim_date d   ON d.calendar_date = l.business_date
JOIN dim_store cs ON cs.store_id = l.store_id AND cs.is_current
CROSS JOIN params
WHERE d.fiscal_year = params.fiscal_year AND d.fiscal_period BETWEEN params.first_period AND params.last_period
GROUP BY 1
ORDER BY 1;
