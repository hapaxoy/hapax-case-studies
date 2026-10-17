# REQ-D27

- Received: 2026-04-07
- From: Leena Vuorinen, Store operations

## Request

> ATV by weekday for P11

## Accepted query

```sql
SELECT d.day_of_week, d.day_name,
       COUNT(DISTINCT f.receipt_id) AS receipts,
       ROUND(SUM(f.net_amount) / COUNT(DISTINCT f.receipt_id), 2) AS atv
FROM fact_sales_line f
JOIN dim_store s   ON s.store_key = f.store_key
JOIN dim_product p ON p.product_key = f.product_key
JOIN dim_date d    ON d.calendar_date = f.sale_date
WHERE s.store_id < 900
  AND NOT f.staff_purchase_flag
  AND p.category <> 'ZZ Test'
  AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 11
GROUP BY 1, 2
ORDER BY 1;
```

## Note

P11 of last year (FY2025/26, weeks 44-47); same ATV rules.
