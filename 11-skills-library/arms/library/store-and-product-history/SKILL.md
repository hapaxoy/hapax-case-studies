---
name: store-and-product-history
description: As-is versus as-was reporting on versioned stores, products and members - the April 2025 region reorganisation (Capital Region), the outdoor lighting move to Electrical, store openings, the Savonlinna closure, refits and other dated events that change an answer.
---

# Store and product history

## As-is or as-was

<!-- facts: TEAM-ASIS, DEF-HIERARCHY-ASIS -->
Report history as-is unless the requester asks for as-was, and say which one you used. Management reporting restates history on the current hierarchy of store regions and product categories (as-is). As-was means the hierarchy as it stood on the date of the transaction.

<!-- facts: TEAM-EXPLICIT-REQUEST -->
When a request explicitly asks for something that differs from a company default (gross instead of net, as-was instead of as-is, UTC instead of Helsinki time, and so on), follow the request and say that you did.

<!-- source: REQ-D05 -->
"As they were at the time" and "to match the old reports" (REQ-D05) are as-was requests.

## How versions are stored

<!-- facts: REG-SCD-KEYS -->
dim_store, dim_product and dim_member keep one row per version. The fact tables carry the version key (store_key, product_key, member_key) that was valid on the transaction date. The natural keys store_id, sku and member_id are stable across versions. Count distinct natural keys, and join between versions only on the validity dates, or rows multiply. In practice: join the fact's store_key to dim_store for as-was; for as-is, go from there to dim_store again on store_id AND is_current (same for sku and dim_product). valid_to is 9999-12-31 on the current version.

<!-- facts: REG-MEMBER-VERSIONS -->
dim_member gets a new version when a member's tier, home store or marketing consent changes. Count members by distinct member_id. The member_key on a line is the version at that date.

```sql
-- as-is: current region and category, whatever they were on the day
JOIN dim_store s     ON s.store_key = f.store_key
JOIN dim_store cs    ON cs.store_id = s.store_id AND cs.is_current
JOIN dim_product p   ON p.product_key = f.product_key
JOIN dim_product cp  ON cp.sku = p.sku AND cp.is_current
-- as-was: s.region, p.category straight from the version keys on the fact
-- a version on a given date: d BETWEEN valid_from AND valid_to
```

| Template | Gives | Reproduces |
|---|---|---|
| `templates/net_sales_by_region_as_was.sql` | net sales by quarter and as-was region | REQ-D05 |
| `templates/category_as_is_vs_as_was.sql` | net sales by category both ways, with the restatement | - |
| `templates/version_on_date.sql` | the store, article and member version valid on a date | - |

Check with `query-check/scripts/query_check.py`; it warns when a versioned dimension is joined on its natural key without is_current or validity dates.

## Changes that move an answer

<!-- facts: REG-REGION-REORG -->
On 28 April 2025 the four regions (South, West, East, North) became five, with the new Capital Region. Six stores changed region: 101 Helsinki Vuosaari, 102 Helsinki Pitäjänmäki, 103 Espoo Lommila, 104 Vantaa Tammisto and 105 Kerava (South to Capital Region), and 114 Kouvola (East to South). As-is, the Capital Region covers those stores in every year; as-was, it does not exist before 28 April 2025.

<!-- facts: REG-OUTDOOR-LIGHTING -->
From 27 October 2025 (FY2025/26 period 7) the outdoor lighting subcategory moved from Garden to Electrical. Each affected article has a new dim_product version from that date. As-is, outdoor lighting is in Electrical for all history.

<!-- facts: REG-STORE-EVENTS -->
Store openings: Tampere Lamminpää (136) opened 2 September 2024; Lohja (137) opened 4 November 2024. Store closure: Savonlinna (129) closed 25 January 2026.

<!-- facts: REG-REFITS -->
Refit closures, each a run of whole fiscal weeks with no sales: Vantaa Tammisto (104), 8 July 2024 to 11 August 2024 (5 weeks); Pori (119), 8 September 2025 to 12 October 2025 (5 weeks); Kuopio (125), 15 June 2026 to 26 July 2026 (6 weeks). They are listed in ref_store_closure.

<!-- source: REQ-D11, REQ-D26, REQ-D33, REQ-D34, REQ-D35, schema_comments.csv -->
In the history: Garden and Electrical margin for FY2024/25 as-is put outdoor lighting in Electrical for the whole year (REQ-D11); the East as-is no longer has Kouvola (REQ-D35); the Capital Region as-is also covers last year's South stores (REQ-D34); Online is its own region, so web is in no physical region (REQ-D33); format is the same in every store version (REQ-D26). The dim_store.region column comment still says "North, South, East or West".

All dated events in one timeline: `references/dated_events.md`. The LFL and league-table treatment of openings, closures and refits is in lfl-and-store-league.

## Past requests for this skill

Copied from `warehouse-map/references/request_history_digest.md`. Date asked in brackets; the reading the requester accepted after the colon.

<!-- source: REQ-D05, REQ-D11, REQ-D26, REQ-D33, REQ-D34, REQ-D35 -->
- D05 (18 Jun 2025) regional net sales by quarter, last year, regions as they were: FY2024/25 as-was (four regions plus Online). -> store-and-product-history/templates/net_sales_by_region_as_was.sql
- D11 (2 Jul 2025) Garden and Electrical gross margin by period, last year: FY2024/25 as-is, outdoor lighting in Electrical all year.
- D26 (20 May 2025) ATV by format, each quarter of FY24/25: format is the same in every store version.
- D33 (10 Feb 2026) top 10 products by margin in the North, first half of last year: FY2025/26 P1-P6; North as-is; web not in the North.
- D34 (18 Aug 2026) top 10 brands by gross margin in the Capital Region, P1-P3 this year: FY2026/27; as-is.
- D35 (26 May 2026) top 5 subcategories by margin in the East, second half of last year: FY2025/26 P7-P12 with week 53; East as-is (no Kouvola).
