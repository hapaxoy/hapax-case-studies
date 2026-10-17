---
name: query-check
description: Run and check any warehouse query before sending an answer - row count, duplicate keys at a declared grain, date coverage against the requested range (including the UTC/Helsinki day edge), deprecated tables or columns, and the gap to the rpt_daily_store_sales control total.
---

# Query check

Every skill in this library ends with this step. `scripts/query_check.py` runs the query read-only and reports five things. Exit code 0 means nothing failed; 1 means a check failed and the answer should not go out until it is explained.

```
conda run -n <env> python <library>/query-check/scripts/query_check.py PATH_TO/tuomimetsa.duckdb \
    --file my_query.sql --grain business_date,store_id --period "FY2026/27 P05" --control
```

| Option | Use |
|---|---|
| `--file F` or `--sql "..."` | the query (one statement; a trailing semicolon is fine) |
| `--grain a,b` | columns that should be unique in the result |
| `--period "FY2026/27 P05"` or `--start D --end D` | the range the request asked for, in Helsinki business dates |
| `--date-col C` | the result's date column, if it is not business_date, calendar_date, sale_date, return_date, dispatch_date, order_date, week_ending_date or as_of_end |
| `--ts-col C` | a UTC timestamp column in the result, to test it against the Helsinki range |
| `--control` | compare with rpt_daily_store_sales over the range; by store and/or day when the result has store_id and a date column |
| `--value-col C`, `--control-measure M` | the result's figure and the control column (net_sales, net_sales_before_returns, returns_net, receipts, units_sold) |
| `--control-stores all/physical/web/101,102` | which stores the control side covers (physical = below 900) |
| `--json` | machine-readable output |

Get the range from `fiscal-calendar/scripts/fiscal.py` first.

## What it checks, and the house facts behind each check

1. **Row count**, with a preview. Zero rows is a warning.

2. **Duplicate keys at the declared grain.**
<!-- facts: TEAM-CONTROL-TOTALS, REG-CONTROL-TOTAL, REG-SCD-KEYS, REG-STOCK-SNAPSHOT, CAL-DATA-THROUGH, DEF-TIMEZONE, REG-DEPRECATED -->
   Check every answer for:
   1. Grain. The result has one row per the keys you meant. Source grains: fact_sales_line one row per receipt line (receipt_id, line_no), fact_stock_week one row per store_key, product_key, week_ending_date, fact_web_order one row per web_order_id. A join to a versioned dimension on its natural key without is_current or validity dates multiplies rows. Check the source rows for the range you use as well as the output: run the script on a `SELECT` of the source keys with `--grain` set to the source grain.
   2. Dates. The result covers the days asked for and nothing outside them, day boundaries are Helsinki midnight, and the range does not run past 4 October 2026 (or say that it does).
   3. Objects. Nothing from the deprecated list, no channel_code across 3 November 2025.
   4. Control total. Store-level net sales agree with rpt_daily_store_sales over the same days, store by store where you can. If they do not, find out why before sending.
   5. Wording. Say which year you read a relative phrase as, as-is or as-was, and any filter that changed a total.

3. **Date coverage.** The result's dates against the requested range: dates outside it fail; missing days are listed, split into closed days (dim_date.is_trading_day false) and trading days. It warns when the range is not whole fiscal weeks or runs past the load point, and reports how many warehouse rows sit across the requested boundaries with a different UTC date than Helsinki date.
<!-- facts: REG-UTC, DEF-TIMEZONE -->
   Columns ending _ts_utc hold UTC. sale_date is the Helsinki business date of the sale. Reporting is in Helsinki time and a day changes at local midnight, not at midnight UTC. Finland is UTC+2 in winter and UTC+3 in summer; the clocks changed on 30 March 2025 and 26 October 2025, among other dates. The accepted queries convert with `CAST(timezone('Europe/Helsinki', col AT TIME ZONE 'UTC') AS DATE)`, or `hour(...)` for the hour.

4. **Deprecated objects and house-rule lints.** A deprecated table or view is a failure; channel_code is a warning. Lints (warnings) flag sales lines without the store 999 or ZZ Test filter, web lines dated by sale_date without fact_web_order, a `_ts_utc` column cast to a date or hour without conversion, and a versioned dimension joined on its natural key without is_current or validity dates. Full list in `references/deprecated_objects.md`.
<!-- facts: TEAM-EXCLUSIONS -->
   Always filter out store 999 and category ZZ Test in sales work, and say so when the filter changes a total.

   Two lint warnings fire on accepted queries and are expected there: the return-rate cohort (REQ-D16) dates sold lines by sale_date by definition, and the active-member counts (REQ-D29, REQ-D30) count any purchase without the 999 and ZZ Test filter, as accepted.

5. **Control total.**
<!-- facts: TEAM-CONTROL-TOTALS, REG-CONTROL-TOTAL -->
   Before sending a store-level figure, check the total against rpt_daily_store_sales for the same days. That table holds net sales per store per business day on the company definition (web on its dispatch date, returns on their return date). It has no product, member or channel dimension, so it is a control total, not a source for analysis.

   It applies to net sales by store, region, format or total company on the company definition. It does not apply as-is to a category or member subset, gross figures, ATV (staff purchases out) or anything before returns unless you pick the matching control measure (`--control-measure net_sales_before_returns`). A gap with a stated reason (a different definition the request asked for) can go out with that reason; an unexplained gap cannot.

## Reading a failure

- Duplicate keys in the source rows: find which rows repeat (the preview and the examples show the keys) before aggregating; do not send totals built on them.
- Control gap on a few store-days: run the query for those store-days only and compare line counts and amounts with the control.
- Dates outside the range in Helsinki time: the filter was applied to a UTC date.
