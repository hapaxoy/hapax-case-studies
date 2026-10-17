# REQ-D30

- Received: 2025-10-08
- From: Jukka Ylönen, Marketing and CRM

## Request

> Active members by tier as of the last Sunday of September, split Basic/Silver/Gold

## Accepted query

```sql
WITH as_of AS (
    SELECT DATE '2025-09-28' AS as_of_end
),
active AS (
    SELECT DISTINCT m.member_id
    FROM fact_sales_line f
    JOIN dim_member m ON m.member_key = f.member_key
    CROSS JOIN as_of
    WHERE f.sale_date > as_of.as_of_end - 364 AND f.sale_date <= as_of.as_of_end
)
SELECT cur.tier, COUNT(*) AS active_members
FROM active a
CROSS JOIN as_of
JOIN dim_member cur ON cur.member_id = a.member_id
                   AND as_of.as_of_end BETWEEN cur.valid_from AND cur.valid_to      -- tier as it was on the as-of date
GROUP BY 1
ORDER BY 1;
```

## Note

Active on distinct member_id; tier is the member version valid on the as-of date, otherwise members would be counted once per version.
