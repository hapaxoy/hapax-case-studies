-- ATV (average transaction value) by store for a fiscal range.
-- facts: DEF-ATV, REG-STAFF-PURCHASE, REG-STORE-999, REG-TEST-SKU, DEF-STORE-SCOPE
-- Pattern from REQ-D25 (by store), REQ-D26 (by format), REQ-D27 (by weekday), REQ-D28 (one store vs chain).
-- ATV = net sales before returns / number of sales receipts. Store measure: physical stores only
-- (store_id below 900, so no web and no store 999), staff purchases out, test articles out.
-- Stores are dated by sale_date (no web lines here, so no dispatch join is needed).
-- Grain of the output: store_id.
WITH params AS (
    SELECT 'FY2026/27' AS fiscal_year, 5 AS first_period, 5 AS last_period     -- REQ-D25: last period = P5
)
SELECT cs.store_id, cs.store_name,
       COUNT(DISTINCT f.receipt_id) AS receipts,
       SUM(f.net_amount) AS net_sales_before_returns,
       ROUND(SUM(f.net_amount) / COUNT(DISTINCT f.receipt_id), 2) AS atv
FROM fact_sales_line f
JOIN dim_store s   ON s.store_key = f.store_key
JOIN dim_store cs  ON cs.store_id = s.store_id AND cs.is_current
JOIN dim_product p ON p.product_key = f.product_key
JOIN dim_date d    ON d.calendar_date = f.sale_date
CROSS JOIN params
WHERE s.store_id < 900                         -- stores only: no web, no training store
  AND NOT f.staff_purchase_flag                -- staff purchases are out of ATV
  AND p.category <> 'ZZ Test'
  AND d.fiscal_year = params.fiscal_year
  AND d.fiscal_period BETWEEN params.first_period AND params.last_period
GROUP BY 1, 2
ORDER BY atv DESC;
