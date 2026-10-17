# REQ-D16

- Received: 2026-01-21
- From: Hanna Kivistö, Commercial (category management)

## Request

> Return rate web vs stores by category for Q1 sales last year. Web feels worse.

## Accepted query

```sql
WITH lines AS (
    SELECT f.sales_line_id, cp.category,
           CASE WHEN s.store_id = 900 THEN 'Web' ELSE 'Stores' END AS channel_group,
           f.net_amount
    FROM fact_sales_line f
    JOIN dim_store s     ON s.store_key = f.store_key
    JOIN dim_product p   ON p.product_key = f.product_key
    JOIN dim_product cp  ON cp.sku = p.sku AND cp.is_current
    JOIN dim_date d      ON d.calendar_date = f.sale_date
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
      AND d.fiscal_year = 'FY2025/26' AND d.fiscal_quarter = 1
),
refunds AS (
    SELECT sales_line_id, SUM(refund_net) AS refund_net FROM fact_return_line GROUP BY 1
)
SELECT l.category, l.channel_group, SUM(l.net_amount) AS sold_net, COALESCE(SUM(r.refund_net), 0) AS returned_net,
       ROUND(100.0 * COALESCE(SUM(r.refund_net), 0) / SUM(l.net_amount), 2) AS return_rate_pct
FROM lines l LEFT JOIN refunds r USING (sales_line_id)
GROUP BY 1, 2
ORDER BY l.category, l.channel_group;
```

## Note

Web is told apart by store 900, not by channel_code; refunds follow the original line whichever location booked them.
