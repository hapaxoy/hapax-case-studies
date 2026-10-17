-- M2 (pattern 8). Reference query.
SELECT COUNT(DISTINCT m.member_id) AS customers FROM dim_member m
WHERE m.is_current AND m.home_store_id IN (SELECT store_id FROM dim_store WHERE city = 'Tampere' AND store_id < 900 AND is_current);

-- Accepted reading: Members whose home store is in Tampere (all enrolled members)
SELECT COUNT(DISTINCT m.member_id) AS customers FROM dim_member m
WHERE m.is_current AND m.home_store_id IN (SELECT store_id FROM dim_store WHERE city = 'Tampere' AND store_id < 900 AND is_current);

-- Accepted reading: Members who bought at a Tampere store in the last 52 weeks
SELECT COUNT(DISTINCT m.member_id) AS customers
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_member m ON m.member_key = f.member_key
WHERE s.store_id IN (SELECT store_id FROM dim_store WHERE city = 'Tampere' AND store_id < 900 AND is_current) AND f.sale_date > DATE '2026-10-04' - 364 AND f.sale_date <= DATE '2026-10-04';

-- Naive variant [fan_out] count_member_versions: Counts rows in the member table whose home store is in Tampere, including every earlier version of every member, so people who changed tier or store are counted twice or more.
SELECT COUNT(*) AS customers FROM dim_member m WHERE m.home_store_id IN (SELECT store_id FROM dim_store WHERE city = 'Tampere' AND store_id < 900 AND is_current);
