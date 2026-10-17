-- Store league table: physical stores ranked by net sales per trading day.
-- facts: DEF-STORE-LEAGUE, CAL-CLOSED-DAYS, REG-STORE-EVENTS, REG-REFITS, DEF-STORE-SCOPE, DEF-NET-SALES,
--        DEF-NET-SALES-SCOPE, REG-STAFF-PURCHASE
-- Pattern from REQ-D37 to REQ-D40. Trading days = days the store was open: after opening, before
-- closure, outside refit closures (ref_store_closure) and not a closed holiday (dim_date.is_trading_day).
-- A store that traded for only part of the range stays in the table with its own trading days.
-- Physical stores only, so no web dispatch join is needed. Staff purchases stay in (they are net sales).
-- Grain of the output: store_id.
WITH params AS (
    SELECT DATE '2026-06-29' AS start_date, DATE '2026-08-02' AS end_date     -- REQ-D40: FY2026/27 P03
),
period_days AS (
    SELECT d.calendar_date FROM dim_date d CROSS JOIN params
    WHERE d.calendar_date BETWEEN params.start_date AND params.end_date AND d.is_trading_day
),
trading_days AS (
    SELECT cs.store_id, COUNT(*) AS trading_days
    FROM dim_store cs
    CROSS JOIN period_days pd
    WHERE cs.is_current AND cs.store_id < 900
      AND (cs.open_date IS NULL OR cs.open_date <= pd.calendar_date)
      AND (cs.close_date IS NULL OR cs.close_date >= pd.calendar_date)
      AND NOT EXISTS (SELECT 1 FROM ref_store_closure c
                      WHERE c.store_id = cs.store_id AND pd.calendar_date BETWEEN c.closure_start_date AND c.closure_end_date)
    GROUP BY 1
),
net_lines AS (
    SELECT f.sale_date AS business_date, s.store_id, f.net_amount AS net_sales
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    WHERE s.store_id < 900 AND p.category <> 'ZZ Test'
    UNION ALL
    SELECT r.return_date, s.store_id, -r.refund_net
    FROM fact_return_line r
    JOIN dim_store s   ON s.store_key = r.store_key
    JOIN dim_product p ON p.product_key = r.product_key
    WHERE s.store_id < 900 AND p.category <> 'ZZ Test'
),
store_sales AS (
    SELECT n.store_id, SUM(n.net_sales) AS net_sales
    FROM net_lines n CROSS JOIN params
    WHERE n.business_date BETWEEN params.start_date AND params.end_date
    GROUP BY 1
)
SELECT RANK() OVER (ORDER BY ss.net_sales / td.trading_days DESC) AS rank, cs.store_id, cs.store_name, cs.format,
       td.trading_days, ss.net_sales, ROUND(ss.net_sales / td.trading_days, 0) AS net_sales_per_trading_day
FROM store_sales ss
JOIN trading_days td ON td.store_id = ss.store_id
JOIN dim_store cs    ON cs.store_id = ss.store_id AND cs.is_current
ORDER BY rank;
