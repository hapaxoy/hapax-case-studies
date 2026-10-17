-- Sales including VAT by category (as-is), for requests that ask for gross figures.
-- facts: DEF-VAT-GROSS, REG-VAT-CHANGE, DEF-NET-SALES, DEF-NET-SALES-SCOPE, DEF-WEB-RECOGNITION, TEAM-EXPLICIT-REQUEST
-- Sum gross_amount from the lines: every line carries its own VAT rate (24% general rate before
-- 1 September 2024, 25.5% after; 14% and 10% unchanged), so never multiply a net total by one rate.
-- The dictionary defines gross as the sum of gross_amount on the lines. It does not say how returns are
-- treated in a gross figure, so this template shows refunds including VAT (refund_gross) as a separate
-- column; state in the answer which figure you sent.
-- Dates follow net sales: store lines on the sale date, web lines on the Helsinki dispatch date,
-- refunds on the return date.
-- Grain of the output: category.
WITH params AS (
    SELECT DATE '2026-08-31' AS start_date, DATE '2026-09-27' AS end_date      -- FY2026/27 P05
),
web_dispatch AS (
    SELECT web_order_id,
           CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
lines AS (
    SELECT COALESCE(w.dispatch_date, f.sale_date) AS business_date, p.sku,
           f.gross_amount AS gross_sales, 0 AS refund_gross, f.net_amount AS net_sales
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
    UNION ALL
    SELECT r.return_date, p.sku, 0, r.refund_gross, -r.refund_net
    FROM fact_return_line r
    JOIN dim_store s   ON s.store_key = r.store_key
    JOIN dim_product p ON p.product_key = r.product_key
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
)
SELECT cp.category,
       SUM(l.gross_sales)  AS gross_sales_incl_vat,         -- sum of gross_amount on the sales lines
       SUM(l.refund_gross) AS refunds_incl_vat,             -- refund_gross on return lines, shown separately
       SUM(l.net_sales)    AS net_sales_excl_vat            -- company net sales, for reference
FROM lines l
JOIN dim_product cp ON cp.sku = l.sku AND cp.is_current
CROSS JOIN params
WHERE l.business_date BETWEEN params.start_date AND params.end_date
GROUP BY 1
ORDER BY gross_sales_incl_vat DESC;
