# REQ-D29

- Received: 2025-05-06
- From: Sanna Ahonen, Marketing and CRM

## Request

> How many active members did we have at the end of last year?

## Accepted query

```sql
WITH as_of AS (
    SELECT fiscal_week_end_date AS as_of_end FROM dim_date WHERE calendar_date = DATE '2025-04-27'
)
SELECT COUNT(DISTINCT m.member_id) AS active_members
FROM fact_sales_line f
JOIN dim_member m ON m.member_key = f.member_key
CROSS JOIN as_of
WHERE f.sale_date > as_of.as_of_end - 364           -- trailing 52 fiscal weeks, as-of week included
  AND f.sale_date <= as_of.as_of_end;
```

## Note

End of FY2024/25 = Sunday 27 April 2025; active = a purchase in the trailing 52 fiscal weeks, counted on distinct member_id (not member_key).
