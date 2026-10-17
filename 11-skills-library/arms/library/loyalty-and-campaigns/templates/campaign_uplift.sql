-- Campaign uplift: mean net sales per targeted member minus mean per holdout member.
-- facts: DEF-UPLIFT, REG-EXPOSURE-FANOUT, REG-CONSENT, REG-MEMBER-VERSIONS, DEF-NET-SALES-SCOPE,
--        DEF-WEB-RECOGNITION, REG-GUEST-ORDERS
-- Window: the campaign window plus seven days (start_date to end_date + 7).
-- Targeted = at least one exposure row in the campaign; exposure has one row per contact, so reduce to
-- distinct member_id first (via dim_member, because exposure carries member_key).
-- Holdout = campaign_holdout, which holds member_id, not member_key. Holdout members are never contacted.
-- Net sales before returns, on lines linked to the member; members with no sales count as zero.
-- Lines are dated as in net sales (web on the Helsinki dispatch date); store 999 and ZZ Test are out.
-- REQUIRED parameter: replace {{campaign_id}} with the campaign_id from dim_campaign that the request
-- names. There is no default; the query does not parse until it is filled in.
-- Grain of the output: one row per group, plus the uplift row.
WITH params AS (
    SELECT {{campaign_id}} AS campaign_id                  -- required, no default
),
campaign AS (
    SELECT c.campaign_id, c.campaign_name, c.start_date, c.end_date + 7 AS window_end
    FROM dim_campaign c JOIN params ON params.campaign_id = c.campaign_id
),
targeted AS (
    SELECT DISTINCT m.member_id
    FROM fact_campaign_exposure e
    JOIN dim_member m ON m.member_key = e.member_key
    JOIN params ON params.campaign_id = e.campaign_id
),
holdout AS (
    SELECT DISTINCT h.member_id
    FROM campaign_holdout h
    JOIN params ON params.campaign_id = h.campaign_id
),
members AS (
    SELECT member_id, 'targeted' AS member_group FROM targeted
    UNION ALL
    SELECT member_id, 'holdout' FROM holdout
),
web_dispatch AS (
    SELECT web_order_id,
           CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
member_sales AS (
    SELECT m.member_id, SUM(f.net_amount) AS net_sales
    FROM fact_sales_line f
    JOIN dim_member m  ON m.member_key = f.member_key
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    CROSS JOIN campaign
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
      AND COALESCE(w.dispatch_date, f.sale_date) BETWEEN campaign.start_date AND campaign.window_end
    GROUP BY 1
),
by_group AS (
    SELECT mb.member_group, COUNT(*) AS members, AVG(COALESCE(ms.net_sales, 0)) AS mean_net_sales
    FROM members mb
    LEFT JOIN member_sales ms ON ms.member_id = mb.member_id
    GROUP BY 1
)
SELECT member_group, members, ROUND(mean_net_sales, 2) AS mean_net_sales_per_member
FROM by_group
UNION ALL
SELECT 'uplift (targeted - holdout)', NULL,
       ROUND(MAX(CASE WHEN member_group = 'targeted' THEN mean_net_sales END)
           - MAX(CASE WHEN member_group = 'holdout' THEN mean_net_sales END), 2)
FROM by_group
UNION ALL
SELECT 'check: members in both groups', (SELECT COUNT(*) FROM targeted JOIN holdout USING (member_id)), NULL;
