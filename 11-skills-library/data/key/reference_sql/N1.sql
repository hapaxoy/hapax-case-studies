-- N1 (pattern 13). Reference query.
SELECT m.home_store_id AS store_id, COUNT(*) AS new_members
FROM dim_member m
WHERE m.join_date BETWEEN DATE '2025-04-28' AND DATE '2026-05-03' AND m.valid_from = (SELECT MIN(x.valid_from) FROM dim_member x WHERE x.member_id = m.member_id)
GROUP BY 1 ORDER BY 1;

-- Naive variant [company_definition] current_home_store: Uses the member's home store today, so a member who enrolled at Savonlinna and was moved to Mikkeli when it closed counts as a Mikkeli sign-up.
SELECT m.home_store_id AS store_id, COUNT(DISTINCT m.member_id) AS new_members
FROM dim_member m WHERE m.join_date BETWEEN DATE '2025-04-28' AND DATE '2026-05-03' AND m.is_current GROUP BY 1 ORDER BY 1;

-- Naive variant [fan_out] count_member_versions: Counts rows in the member table instead of members, so anyone with more than one version (a tier or consent change) is counted more than once.
SELECT m.home_store_id AS store_id, COUNT(*) AS new_members FROM dim_member m WHERE m.join_date BETWEEN DATE '2025-04-28' AND DATE '2026-05-03' GROUP BY 1 ORDER BY 1;
