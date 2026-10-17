-- U9b (pattern 9). Reference query.
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
targeted AS (SELECT DISTINCT m.member_id FROM fact_campaign_exposure e JOIN dim_member m ON m.member_key = e.member_key WHERE e.campaign_id = 19)
SELECT (SELECT COUNT(*) FROM targeted) AS targeted_members, ROUND(SUM(f.net_amount), 2) AS net_sales
FROM fact_sales_line f JOIN dim_member m ON m.member_key = f.member_key LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
WHERE m.member_id IN (SELECT member_id FROM targeted) AND COALESCE(w.dispatch_date, f.sale_date) BETWEEN DATE '2026-05-04' AND DATE '2026-05-24';

-- Also accepted: web sales on the order date
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
targeted AS (SELECT DISTINCT m.member_id FROM fact_campaign_exposure e JOIN dim_member m ON m.member_key = e.member_key WHERE e.campaign_id = 19)
SELECT (SELECT COUNT(*) FROM targeted) AS targeted_members, ROUND(SUM(f.net_amount), 2) AS net_sales
FROM fact_sales_line f JOIN dim_member m ON m.member_key = f.member_key LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
WHERE m.member_id IN (SELECT member_id FROM targeted) AND f.sale_date BETWEEN DATE '2026-05-04' AND DATE '2026-05-24';

-- Naive variant [fan_out] contact_rows_joined_to_sales: Joins the contact rows straight to the sales lines, so each member's spend is repeated once per contact (about twice over).
SELECT COUNT(DISTINCT m.member_id) AS targeted_members, ROUND(SUM(f.net_amount), 2) AS net_sales
FROM fact_campaign_exposure e JOIN dim_member m ON m.member_key = e.member_key
JOIN dim_member v ON v.member_id = m.member_id JOIN fact_sales_line f ON f.member_key = v.member_key
WHERE e.campaign_id = 19 AND f.sale_date BETWEEN DATE '2026-05-04' AND DATE '2026-05-24';
