---
name: stock
description: Closing stock and weeks of cover from the weekly stock snapshot - semi-additive (add across stores and products, never across weeks), ranged articles only, no web stock - with validated SQL for period averages, last-week closing and cover.
---

# Stock

## Steps

1. Fix the weeks with `fiscal-calendar/scripts/fiscal.py`; stock is counted on week-ending Sundays.
2. Before aggregating, check the snapshot rows for your weeks at their grain:
   `query_check.py DB --sql "SELECT store_key, product_key, week_ending_date FROM fact_stock_week WHERE week_ending_date BETWEEN ... AND ..." --grain store_key,product_key,week_ending_date`.
   Do not aggregate over rows that fail it until the repeats are explained.
3. Start from a template; edit `params`.
4. Check the output with `query-check/scripts/query_check.py --grain ...`.

| Template | Gives |
|---|---|
| `templates/closing_stock_for_period.sql` | per store: average of the weekly closings and the last week's closing, units and value |
| `templates/weeks_of_cover.sql` | per store and category (as-is): closing units, average weekly units sold, weeks of cover |

No past request covers stock, so neither template reproduces an accepted query; both were run against the warehouse.

## Definitions

<!-- facts: DEF-STOCK-SEMIADD -->
Closing stock is a snapshot at the end of each fiscal week. Add it across stores and products, but never across weeks. For a period, use the average of the weekly closings or the last week's closing, whichever the request asks for. Sum within each week first, then average or take the last week.

<!-- facts: REG-STOCK-SNAPSHOT -->
fact_stock_week has one row per store and article for each week-ending Sunday, and only for the articles the store ranges (carries). Web orders are picked from the central warehouse, which is not in this table.

<!-- facts: DEF-WEEKS-COVER -->
Weeks of cover is the closing stock units at the end of a fiscal week divided by the average weekly units sold over the prior four fiscal weeks, for the same store or grouping. Units sold are the quantity on sales lines, by sale date. Read literally, the prior four weeks are the four weeks before the snapshot week; say so in the answer.

## Scope

<!-- facts: DEF-STORE-SCOPE, REG-TEST-SKU -->
Store counts and store-level analyses cover the physical stores only (store_id below 900). Store 999 is never included. Test articles sit in category ZZ Test and are left out of all reporting. Both templates filter `s.store_id < 900` and `p.category <> 'ZZ Test'` on stock and on units sold.

<!-- source: schema_comments.csv -->
closing_value is at standard cost. receipts_units are units received into the store during the week; adjustment_units are stock-take and write-off adjustments during the week. dim_product.standard_unit_cost is revalued each April.
