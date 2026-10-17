-- The version of a store, article or member that was valid on a given date.
-- facts: REG-SCD-KEYS, REG-MEMBER-VERSIONS, REG-REGION-REORG, REG-OUTDOOR-LIGHTING
-- dim_store, dim_product and dim_member keep one row per version. Join between versions only on the
-- validity dates (valid_from <= date <= valid_to), or rows multiply. valid_to is 9999-12-31 for the
-- current version. Change the date and the natural keys; the three parts of the UNION are independent.
-- Grain of the output: one row per kind x natural key.
WITH params AS (
    SELECT DATE '2025-01-15' AS on_date
)
-- stores 101 and 114 changed region on 28 April 2025
SELECT 'store' AS kind, CAST(s.store_id AS VARCHAR) AS natural_key, s.store_key AS version_key,
       s.store_name AS name, s.region AS attribute_1, s.format AS attribute_2, s.valid_from, s.valid_to
FROM dim_store s CROSS JOIN params
WHERE s.store_id IN (101, 114) AND params.on_date BETWEEN s.valid_from AND s.valid_to
UNION ALL
-- an outdoor lighting article (moved from Garden to Electrical on 27 October 2025)
SELECT 'product', CAST(p.sku AS VARCHAR), p.product_key, p.product_name, p.category, p.subcategory, p.valid_from, p.valid_to
FROM dim_product p CROSS JOIN params
WHERE p.sku = (SELECT MIN(sku) FROM dim_product WHERE subcategory ILIKE '%outdoor lighting%')
  AND params.on_date BETWEEN p.valid_from AND p.valid_to
UNION ALL
-- a member with more than one version (tier, home store or consent changed)
SELECT 'member', CAST(m.member_id AS VARCHAR), m.member_key, m.tier, CAST(m.home_store_id AS VARCHAR),
       CAST(m.marketing_consent AS VARCHAR), m.valid_from, m.valid_to
FROM dim_member m CROSS JOIN params
WHERE m.member_id = (SELECT MIN(member_id) FROM (SELECT member_id FROM dim_member GROUP BY 1 HAVING COUNT(*) > 1))
  AND params.on_date BETWEEN m.valid_from AND m.valid_to
ORDER BY kind, natural_key;
