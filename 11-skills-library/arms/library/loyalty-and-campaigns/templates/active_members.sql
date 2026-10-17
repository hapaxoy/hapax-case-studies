-- Active members as of a fiscal week, by tier on the as-of date.
-- facts: DEF-ACTIVE-MEMBER, REG-MEMBER-VERSIONS, REG-SCD-KEYS, REG-GUEST-ORDERS
-- Pattern from REQ-D29 (total) and REQ-D30 (by tier). Active = at least one purchase in the trailing
-- 52 fiscal weeks, ending with the as-of week and including it, in any channel. Count distinct
-- member_id, never member_key (one key per version). Tier is the version valid on the as-of date.
-- Grain of the output: tier (plus a total row with tier NULL).
WITH params AS (
    SELECT DATE '2025-09-28' AS as_of_date            -- any date in the as-of week
),
as_of AS (
    SELECT d.fiscal_week_end_date AS as_of_end
    FROM dim_date d CROSS JOIN params
    WHERE d.calendar_date = params.as_of_date
),
active AS (
    SELECT DISTINCT m.member_id
    FROM fact_sales_line f
    JOIN dim_member m ON m.member_key = f.member_key
    CROSS JOIN as_of
    WHERE f.sale_date > as_of.as_of_end - 364          -- trailing 52 fiscal weeks, as-of week included
      AND f.sale_date <= as_of.as_of_end
)
SELECT cur.tier, COUNT(*) AS active_members
FROM active a
CROSS JOIN as_of
JOIN dim_member cur ON cur.member_id = a.member_id
                   AND as_of.as_of_end BETWEEN cur.valid_from AND cur.valid_to      -- tier as it was on the as-of date
GROUP BY GROUPING SETS ((cur.tier), ())
ORDER BY cur.tier NULLS LAST;
