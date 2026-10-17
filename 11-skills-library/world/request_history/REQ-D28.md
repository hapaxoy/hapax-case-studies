# REQ-D28

- Received: 2026-05-27
- From: Mika Hietala, Store operations

## Request

> Pori ATV against the whole chain, by period, second half of last year

## Accepted query

```sql
WITH receipts AS (
    SELECT d.fiscal_period, s.store_id, f.receipt_id, SUM(f.net_amount) AS receipt_net
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    JOIN dim_date d    ON d.calendar_date = f.sale_date
    WHERE s.store_id < 900 AND NOT f.staff_purchase_flag AND p.category <> 'ZZ Test'
      AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period BETWEEN 7 AND 12
    GROUP BY 1, 2, 3
)
SELECT fiscal_period,
       ROUND(SUM(CASE WHEN store_id = 119 THEN receipt_net END) / COUNT(CASE WHEN store_id = 119 THEN 1 END), 2) AS pori_atv,
       ROUND(SUM(receipt_net) / COUNT(*), 2) AS chain_atv
FROM receipts
GROUP BY 1
ORDER BY 1;
```

## Note

Pori is store 119; same ATV rules, store receipts only; second half = P7-P12.
