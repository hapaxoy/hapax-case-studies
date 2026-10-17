-- New members by fiscal period and enrolling store.
-- facts: DEF-NEW-MEMBER, REG-MEMBER-VERSIONS, REG-SCD-KEYS, DEF-HIERARCHY-ASIS
-- A new member is counted on their join date, at the home store in their FIRST version in dim_member
-- (the store where they enrolled). Online sign-ups sit under store 900. Later versions may carry another
-- home store, so never take the current version for this.
-- Store name and region are shown as-is (current store version).
-- Grain of the output: fiscal_period x home_store_id.
WITH params AS (
    SELECT 'FY2026/27' AS fiscal_year, 1 AS first_period, 5 AS last_period
),
first_version AS (
    SELECT member_id, join_date, home_store_id,
           ROW_NUMBER() OVER (PARTITION BY member_id ORDER BY valid_from) AS version_no
    FROM dim_member
)
SELECT d.fiscal_period, fv.home_store_id, cs.store_name, cs.region, COUNT(*) AS new_members
FROM first_version fv
JOIN dim_date d ON d.calendar_date = fv.join_date
LEFT JOIN dim_store cs ON cs.store_id = fv.home_store_id AND cs.is_current
CROSS JOIN params
WHERE fv.version_no = 1
  AND d.fiscal_year = params.fiscal_year
  AND d.fiscal_period BETWEEN params.first_period AND params.last_period
GROUP BY 1, 2, 3, 4
ORDER BY 1, 2;
