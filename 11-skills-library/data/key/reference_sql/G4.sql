-- G4 (pattern 8). Reference query.
SELECT COUNT(DISTINCT member_id) AS gold_members FROM dim_member WHERE is_current AND tier = 'Gold';

-- Sloppy variant 1 (must give the reference result)
SELECT COUNT(DISTINCT member_id) AS gold_members FROM dim_member WHERE tier = 'Gold' AND DATE '2026-10-04' BETWEEN valid_from AND valid_to;
