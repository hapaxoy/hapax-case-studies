-- Return rate by category (as-is) on the sale-week cohort.
-- facts: DEF-RETURN-RATE, REG-RETURN-LAG, DEF-NET-SALES-SCOPE, REG-STORE-900, CAL-DATA-THROUGH
-- Pattern from REQ-D14, REQ-D15 (subcategory) and REQ-D16 (web vs stores: CASE WHEN s.store_id = 900).
-- Refunds are matched to the line that was sold (sales_line_id), so a return counts in the week the item
-- was sold, whenever it came back. Returns arrive up to 30 days after a sale: the cohort_complete column
-- is false when the last sale date is less than 30 days before the last loaded date.
-- Grain of the output: category.
WITH params AS (
    SELECT 'FY2025/26' AS fiscal_year, 1 AS first_period, 4 AS last_period     -- REQ-D14
),
sold_lines AS (
    SELECT f.sales_line_id, f.sale_date, cp.category, f.net_amount
    FROM fact_sales_line f
    JOIN dim_store s     ON s.store_key = f.store_key
    JOIN dim_product p   ON p.product_key = f.product_key
    JOIN dim_product cp  ON cp.sku = p.sku AND cp.is_current
    JOIN dim_date d      ON d.calendar_date = f.sale_date
    CROSS JOIN params
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
      AND d.fiscal_year = params.fiscal_year
      AND d.fiscal_period BETWEEN params.first_period AND params.last_period
),
refunds AS (
    SELECT sales_line_id, SUM(refund_net) AS refund_net FROM fact_return_line GROUP BY 1
)
SELECT l.category,
       SUM(l.net_amount) AS sold_net,
       COALESCE(SUM(r.refund_net), 0) AS returned_net,
       ROUND(100.0 * COALESCE(SUM(r.refund_net), 0) / SUM(l.net_amount), 2) AS return_rate_pct,
       MAX(l.sale_date) + 30 <= (SELECT MAX(calendar_date) FROM dim_date) AS cohort_complete
FROM sold_lines l
LEFT JOIN refunds r USING (sales_line_id)
GROUP BY 1
ORDER BY return_rate_pct DESC;
