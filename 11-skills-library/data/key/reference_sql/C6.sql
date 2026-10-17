-- C6 (pattern 9). Reference query.
SELECT COUNT(*) AS holdout_members FROM campaign_holdout WHERE campaign_id = 15;

-- Sloppy variant 1 (must give the reference result)
SELECT holdout_size AS holdout_members FROM dim_campaign WHERE campaign_name = 'Black Week 2025';
