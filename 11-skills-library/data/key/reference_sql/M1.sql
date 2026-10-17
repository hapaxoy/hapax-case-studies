-- M1 (pattern 8). Reference query.
WITH active AS (
    SELECT DISTINCT m.member_id
    FROM fact_sales_line f JOIN dim_member m ON m.member_key = f.member_key
    WHERE f.sale_date > DATE '2025-12-21' - 364 AND f.sale_date <= DATE '2025-12-21'
)
SELECT cur.tier, COUNT(*) AS active_members
FROM active a JOIN dim_member cur ON cur.member_id = a.member_id AND DATE '2025-12-21' BETWEEN cur.valid_from AND cur.valid_to
GROUP BY 1 ORDER BY 1;

-- Naive variant [fan_out] count_member_versions: Counts member versions (member_key) instead of members, and uses the tier on the day of each purchase. A member who changed tier or store during the year is counted more than once.
SELECT m.tier, COUNT(DISTINCT f.member_key) AS active_members
FROM fact_sales_line f JOIN dim_member m ON m.member_key = f.member_key
WHERE f.sale_date > DATE '2025-12-21' - 364 AND f.sale_date <= DATE '2025-12-21'
GROUP BY 1 ORDER BY 1;

-- Naive variant [company_definition] bought_in_the_period_only: Counts only members who bought during period 8 itself instead of in the 52 weeks to the end of it.
SELECT cur.tier, COUNT(*) AS active_members
FROM (SELECT DISTINCT m.member_id FROM fact_sales_line f JOIN dim_member m ON m.member_key = f.member_key
      JOIN dim_date d ON d.calendar_date = f.sale_date WHERE d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 8) a
JOIN dim_member cur ON cur.member_id = a.member_id AND DATE '2025-12-21' BETWEEN cur.valid_from AND cur.valid_to
GROUP BY 1 ORDER BY 1;
