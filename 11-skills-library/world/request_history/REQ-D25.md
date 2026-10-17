# REQ-D25

- Received: 2026-09-30
- From: Leena Vuorinen, Store operations

## Request

> ATV by store for last period

## Accepted query

```sql
SELECT cs.store_id, cs.store_name,
       COUNT(DISTINCT f.receipt_id) AS receipts,
       ROUND(SUM(f.net_amount) / COUNT(DISTINCT f.receipt_id), 2) AS atv
FROM fact_sales_line f
JOIN dim_store s   ON s.store_key = f.store_key
JOIN dim_store cs  ON cs.store_id = s.store_id AND cs.is_current
JOIN dim_product p ON p.product_key = f.product_key
JOIN dim_date d    ON d.calendar_date = f.sale_date
WHERE s.store_id < 900                         -- stores only: no web, no training store
  AND NOT f.staff_purchase_flag                -- staff purchases are out of ATV
  AND p.category <> 'ZZ Test'
  AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 5
GROUP BY 1, 2
ORDER BY atv DESC;
```

## Note

ATV is net sales before returns over sales receipts, stores only, staff purchases and store 999 out; last period = FY2026/27 P5.
