-- C10 (pattern 13). Reference query.
SELECT COUNT(DISTINCT member_id) AS new_members FROM dim_member WHERE join_date = DATE '2026-10-03';

-- Sloppy variant 1 (must give the reference result)
SELECT COUNT(*) AS new_members FROM dim_member WHERE join_date = DATE '2026-10-03';
