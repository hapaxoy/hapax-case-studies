-- U9a (pattern 9). Reference query.
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
camp AS (SELECT start_date, end_date + 7 AS window_end FROM dim_campaign WHERE campaign_id = 15),
targeted AS (
    SELECT DISTINCT m.member_id FROM fact_campaign_exposure e JOIN dim_member m ON m.member_key = e.member_key WHERE e.campaign_id = 15
),
holdout AS (SELECT member_id FROM campaign_holdout WHERE campaign_id = 15),
spend AS (
    SELECT m.member_id, SUM(f.net_amount) AS net
    FROM fact_sales_line f JOIN dim_member m ON m.member_key = f.member_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    CROSS JOIN camp
    WHERE COALESCE(w.dispatch_date, f.sale_date) BETWEEN camp.start_date AND camp.window_end
    GROUP BY 1
)
SELECT ROUND((SELECT AVG(COALESCE(s.net, 0)) FROM targeted t LEFT JOIN spend s USING (member_id)), 2) AS mean_net_targeted, ROUND((SELECT AVG(COALESCE(s.net, 0)) FROM holdout h LEFT JOIN spend s USING (member_id)), 2) AS mean_net_holdout,
       ROUND((SELECT AVG(COALESCE(s.net, 0)) FROM targeted t LEFT JOIN spend s USING (member_id)) - (SELECT AVG(COALESCE(s.net, 0)) FROM holdout h LEFT JOIN spend s USING (member_id)), 2) AS uplift_eur;

-- Also accepted: web sales on the order date
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
camp AS (SELECT start_date, end_date + 7 AS window_end FROM dim_campaign WHERE campaign_id = 15),
targeted AS (
    SELECT DISTINCT m.member_id FROM fact_campaign_exposure e JOIN dim_member m ON m.member_key = e.member_key WHERE e.campaign_id = 15
),
holdout AS (SELECT member_id FROM campaign_holdout WHERE campaign_id = 15),
spend AS (
    SELECT m.member_id, SUM(f.net_amount) AS net
    FROM fact_sales_line f JOIN dim_member m ON m.member_key = f.member_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    CROSS JOIN camp
    WHERE f.sale_date BETWEEN camp.start_date AND camp.window_end
    GROUP BY 1
)
SELECT ROUND((SELECT AVG(COALESCE(s.net, 0)) FROM targeted t LEFT JOIN spend s USING (member_id)), 2) AS mean_net_targeted, ROUND((SELECT AVG(COALESCE(s.net, 0)) FROM holdout h LEFT JOIN spend s USING (member_id)), 2) AS mean_net_holdout,
       ROUND((SELECT AVG(COALESCE(s.net, 0)) FROM targeted t LEFT JOIN spend s USING (member_id)) - (SELECT AVG(COALESCE(s.net, 0)) FROM holdout h LEFT JOIN spend s USING (member_id)), 2) AS uplift_eur;

-- Naive variant [fan_out] contact_rows_joined_to_sales: Joins the contact rows straight to the sales lines, so a member contacted three times has their spend counted three times, and members who did not spend vanish from the average.
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
camp AS (SELECT start_date, end_date + 7 AS window_end FROM dim_campaign WHERE campaign_id = 15),
targeted AS (
    SELECT DISTINCT m.member_id FROM fact_campaign_exposure e JOIN dim_member m ON m.member_key = e.member_key WHERE e.campaign_id = 15
),
holdout AS (SELECT member_id FROM campaign_holdout WHERE campaign_id = 15),
spend AS (
    SELECT m.member_id, SUM(f.net_amount) AS net
    FROM fact_sales_line f JOIN dim_member m ON m.member_key = f.member_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    CROSS JOIN camp
    WHERE f.sale_date BETWEEN camp.start_date AND camp.window_end
    GROUP BY 1
)
SELECT ROUND((SELECT SUM(f.net_amount) / COUNT(DISTINCT m.member_id)
         FROM fact_campaign_exposure e
         JOIN dim_member m ON m.member_key = e.member_key
         JOIN dim_member v ON v.member_id = m.member_id
         JOIN fact_sales_line f ON f.member_key = v.member_key
         CROSS JOIN camp
         WHERE e.campaign_id = 15 AND f.sale_date BETWEEN camp.start_date AND camp.window_end), 2) AS mean_net_targeted, ROUND((SELECT AVG(COALESCE(s.net, 0)) FROM holdout h LEFT JOIN spend s USING (member_id)), 2) AS mean_net_holdout,
       ROUND((SELECT SUM(f.net_amount) / COUNT(DISTINCT m.member_id)
         FROM fact_campaign_exposure e
         JOIN dim_member m ON m.member_key = e.member_key
         JOIN dim_member v ON v.member_id = m.member_id
         JOIN fact_sales_line f ON f.member_key = v.member_key
         CROSS JOIN camp
         WHERE e.campaign_id = 15 AND f.sale_date BETWEEN camp.start_date AND camp.window_end) - (SELECT AVG(COALESCE(s.net, 0)) FROM holdout h LEFT JOIN spend s USING (member_id)), 2) AS uplift_eur;

-- Naive variant [company_definition] compared_with_everyone_not_mailed: Compares with every member who was not mailed instead of the holdout group, so members who never consented to marketing are in the comparison.
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
camp AS (SELECT start_date, end_date + 7 AS window_end FROM dim_campaign WHERE campaign_id = 15),
targeted AS (
    SELECT DISTINCT m.member_id FROM fact_campaign_exposure e JOIN dim_member m ON m.member_key = e.member_key WHERE e.campaign_id = 15
),
holdout AS (SELECT member_id FROM campaign_holdout WHERE campaign_id = 15),
spend AS (
    SELECT m.member_id, SUM(f.net_amount) AS net
    FROM fact_sales_line f JOIN dim_member m ON m.member_key = f.member_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    CROSS JOIN camp
    WHERE f.sale_date BETWEEN camp.start_date AND camp.window_end
    GROUP BY 1
)
SELECT ROUND((SELECT AVG(COALESCE(s.net, 0)) FROM targeted t LEFT JOIN spend s USING (member_id)), 2) AS mean_net_targeted, ROUND((SELECT AVG(COALESCE(s.net, 0)) FROM (SELECT DISTINCT member_id FROM dim_member) a LEFT JOIN spend s USING (member_id) WHERE a.member_id NOT IN (SELECT member_id FROM targeted)), 2) AS mean_net_holdout,
       ROUND((SELECT AVG(COALESCE(s.net, 0)) FROM targeted t LEFT JOIN spend s USING (member_id)) - (SELECT AVG(COALESCE(s.net, 0)) FROM (SELECT DISTINCT member_id FROM dim_member) a LEFT JOIN spend s USING (member_id) WHERE a.member_id NOT IN (SELECT member_id FROM targeted)), 2) AS uplift_eur;
