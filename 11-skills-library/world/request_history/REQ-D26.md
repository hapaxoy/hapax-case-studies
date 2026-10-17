# REQ-D26

- Received: 2025-05-20
- From: Mika Hietala, Store operations

## Request

> ATV by store format, each quarter of FY24/25

## Accepted query

```sql
SELECT d.fiscal_quarter, s.format,
       COUNT(DISTINCT f.receipt_id) AS receipts,
       ROUND(SUM(f.net_amount) / COUNT(DISTINCT f.receipt_id), 2) AS atv
FROM fact_sales_line f
JOIN dim_store s   ON s.store_key = f.store_key
JOIN dim_product p ON p.product_key = f.product_key
JOIN dim_date d    ON d.calendar_date = f.sale_date
WHERE s.store_id < 900
  AND NOT f.staff_purchase_flag
  AND p.category <> 'ZZ Test'
  AND d.fiscal_year = 'FY2024/25'
GROUP BY 1, 2
ORDER BY 1, 2;
```

## Note

Format is the same in every store version, so the version valid on the sale date is fine here.
