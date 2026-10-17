---
name: fiscal-calendar
description: Turn any date phrase in a request ("last period", "Q2", "YTD", "this year", "same week last year", "second half") into fiscal dates from dim_date, with week-aligned prior-year comparators, week 53 handling and the warehouse load point.
---

# Fiscal calendar

Resolve the dates before writing any SQL. `scripts/fiscal.py` reads dim_date and prints the range, the fiscal weeks and periods it covers, whether it is complete, a ready dim_date filter, and with `--compare` the prior-year weeks lined up by fiscal week number.

```
conda run -n <env> python <library>/fiscal-calendar/scripts/fiscal.py PATH_TO/tuomimetsa.duckdb "last period"
conda run -n <env> python <library>/fiscal-calendar/scripts/fiscal.py PATH_TO/tuomimetsa.duckdb "Q4" --as-of 2026-06-23
conda run -n <env> python <library>/fiscal-calendar/scripts/fiscal.py PATH_TO/tuomimetsa.duckdb "P12 FY2025/26" --compare
conda run -n <env> python <library>/fiscal-calendar/scripts/fiscal.py PATH_TO/tuomimetsa.duckdb "same week last year" --json
```

Phrases: `last period`, `YTD`, `YTD as of the end of P4`, `this year`, `last completed week`, `same week last year`, `same period last year`, `last N weeks`, `current period`, `current week`, `FY2025/26` or `FY25/26`, `P5`, `P1-P3`, `Q2`, `H1`/`H2`/`first half`/`second half`/`back half`, `week 22`, each with an optional fiscal year. `--as-of` is the date the request was received (default: the last loaded date). The script refuses "last year" on its own: see below.

## Calendar rules

<!-- facts: CAL-YEAR -->
The fiscal year starts on the Monday nearest 1 May, and fiscal weeks run Monday to Sunday. A year is written like FY2025/26, which is the year that began in April 2025.

<!-- facts: CAL-FY-DATES -->
FY2024/25 runs from 29 April 2024 to 27 April 2025 and has 52 weeks. FY2025/26 runs from 28 April 2025 to 3 May 2026 and has 53 weeks. FY2026/27 starts on 4 May 2026.

<!-- facts: CAL-PERIODS -->
There are 12 periods in a year, built from weeks in a 4-4-5 pattern within each quarter (four weeks, four weeks, five weeks). Q1 is P1 to P3 (weeks 1 to 13), Q2 is P4 to P6, Q3 is P7 to P9 and Q4 is P10 to P12.

<!-- facts: CAL-WEEK53 -->
FY2025/26 has 53 weeks. Week 53 (27 April 2026 to 3 May 2026) is added to period 12, which then runs six weeks. Week 53 has no comparator week in the prior year.

<!-- facts: CAL-COMPARE -->
To compare with last year, line up the same fiscal week or the same period number. Do not line up calendar dates: the same calendar dates fall in a different fiscal week each year.

<!-- facts: CAL-RELATIVE -->
"Last period" means the last completed fiscal period. "YTD" means the fiscal year to date through the last completed fiscal week. "This year" means the current fiscal year.

<!-- facts: CAL-DATA-THROUGH -->
The warehouse is loaded through Sunday 4 October 2026 (FY2026/27 week 22). Period 6 of FY2026/27 has only its first week so far. The last complete period is FY2026/27 P05, which ended on 27 September 2026.

<!-- facts: CAL-CLOSED-DAYS -->
The stores are shut on New Year's Day, Epiphany, Good Friday, Easter Sunday, May Day, Midsummer Eve, Midsummer Day, Independence Day, Christmas Eve, Christmas Day and Boxing Day. dim_date.is_trading_day is false on those days.

## Calendar tables

<!-- source: schema_comments.csv -->
Calendar tables. dim_date has one row per day with fiscal_year, fiscal_quarter, fiscal_period, fiscal_period_label (e.g. 'FY2025/26 P05'), fiscal_week, fiscal_week_start_date (Monday), fiscal_week_end_date (Sunday), weeks_in_fiscal_year, is_53_week_year, is_public_holiday, holiday_name and is_trading_day. ref_fiscal_calendar has one row per period with period_start_date, period_end_date, weeks_in_period, first_fiscal_week, last_fiscal_week and fully_loaded (true when the whole period is in the warehouse). Filter on these columns rather than on calendar months.

## Relative phrases in past requests

The metric dictionary defines only "last period", "YTD" and "this year". The rest below is what accepted requests did. Read it whenever a request names a period without a year or says "last year".

<!-- facts: CAL-RELATIVE -->
<!-- source: REQ-D02, REQ-D03, REQ-D04, REQ-D05, REQ-D06, REQ-D08, REQ-D10, REQ-D11, REQ-D12, REQ-D13, REQ-D14, REQ-D16, REQ-D28, REQ-D29, REQ-D33, REQ-D35 -->
How past requests read relative phrases:

- A period or quarter named without a year was read as the most recent completed one: "Q3" on 14 April 2026 was FY2025/26 Q3 (REQ-D03), "Q1" on 20 August 2025 was FY2025/26 Q1 (REQ-D06), "P2" on 7 July 2026 was FY2026/27 P2 (REQ-D10), "Q4" on 23 June 2026 was FY2025/26 Q4 (REQ-D12).
- "First half" is P1 to P6 (REQ-D13); "second half" and "back half" are P7 to P12 (REQ-D04, REQ-D35). For an LFL request REQ-D08 took weeks 27 to 52, because week 53 is never LFL.
- "Last four weeks" asked on 1 September 2026 was read as the last completed period, FY2026/27 P4 (REQ-D02), which was those same four weeks.
- "Last year" is not defined in the metric dictionary. Name the fiscal year you used in the answer. Past readings, by date asked (fiscal year current at the time in brackets): 6 May 2025 (FY2025/26) took FY2024/25 (REQ-D29); 18 June 2025 (FY2025/26) took FY2024/25 (REQ-D05); 2 July 2025 (FY2025/26) took FY2024/25 (REQ-D11); 21 January 2026 (FY2025/26) took FY2025/26 (REQ-D16); 10 February 2026 (FY2025/26) took FY2025/26 (REQ-D33); 10 March 2026 (FY2025/26) took FY2025/26 (REQ-D14); 12 to 27 May 2026 (FY2026/27) took FY2025/26 (REQ-D04, REQ-D08, REQ-D28, REQ-D35).
- With a comparison, week 53 was dropped from both years (REQ-D04). Without one, it stays in (REQ-D12, REQ-D35).

`fiscal.py` reads a bare period, quarter or half as the most recent completed one and says which year it took. It refuses "last year" on its own; run it again with the fiscal year named, e.g. `"H2 FY2025/26"`.

<!-- facts: CAL-RELATIVE, CAL-PERIODS -->
<!-- source: REQ-D09 -->
"YTD as of the end of Pn" runs from week 1 of the fiscal year to the last week of Pn. REQ-D09, asked on 8 September 2026 for YTD LFL as of the end of P4, used weeks 1 to 17 of FY2026/27 against weeks 1 to 17 of FY2025/26: P4 ends with week 17.

`fiscal.py "YTD as of the end of P4"` gives that range (add `--compare` for the prior-year weeks).

<!-- facts: CAL-YEAR, CAL-PERIODS -->
<!-- source: REQ-D19 -->
Weekly series use whole fiscal weeks only, Monday to Sunday, with no part week at either end. REQ-D19 (weekly web sales from August to the end of October 2025, with the migration week) ran from Monday 4 August to Sunday 9 November 2025: it started on the first Monday in August rather than with 1 to 3 August as a part week, and ended on the Sunday of the migration week the requester asked for.

<!-- facts: CAL-RELATIVE, CAL-DATA-THROUGH -->
<!-- source: REQ-D24 -->
A series by quarter or by period stops at the last quarter or period complete as of the date of the request; a part quarter or period is not shown. REQ-D24, asked on 24 March 2026 for the click-and-collect share of web orders by quarter since the start of FY24/25, stopped at FY2025/26 Q3 (ended 25 January 2026), because Q4 was still running. With the warehouse loaded through 4 October 2026, the last complete period is FY2026/27 P05 and the last complete quarter is FY2026/27 Q1.

The by-quarter example (REQ-D24 in full) is in the web-orders skill.

## Week 53 and comparisons

`fiscal.py --compare` lists week 53 under `weeks_without_comparator` and gives a this-year filter without it. With a comparison, drop week 53 from both years (REQ-D04); without one, keep it (REQ-D12). LFL never includes it (lfl-and-store-league).

Then check the query with `query-check/scripts/query_check.py --period "FY.. P.."` or `--start/--end`.

## Past requests for this skill

Copied from `warehouse-map/references/request_history_digest.md`. Date asked in brackets; the reading the requester accepted after the colon.

<!-- source: REQ-D02, REQ-D03, REQ-D04, REQ-D06, REQ-D09, REQ-D12, REQ-D13, REQ-D19, REQ-D24, REQ-D27, REQ-D29 -->
- D02 (1 Sep 2026) sales by format, last four weeks vs last year: FY2026/27 P4 vs P4 by week; format includes Web.
- D03 (14 Apr 2026) total company weekly net sales, Q3 with last year: weeks 27-39; web in; 999 and ZZ Test out.
- D04 (12 May 2026) net sales by region and period, second half of last year vs the year before: FY2025/26 P7-P12 vs FY2024/25; week 53 dropped; as-is.
- D06 (20 Aug 2025) LFL for Q1: FY2025/26 weeks 1-13; Tammisto's FY2024/25 refit weeks drop out. -> lfl-and-store-league/templates/lfl.sql
- D09 (8 Sep 2026) YTD LFL as of the end of P4: weeks 1-17, FY2026/27 vs FY2025/26. -> lfl.sql
- D12 (23 Jun 2026) top 10 subcategories by gross margin, Q4: FY2025/26 P10-P12 including week 53.
- D13 (12 Nov 2025) Paint & Decorating own label vs brands, first half of FY24/25: P1-P6; current product version.
- D19 (18 Nov 2025) weekly web sales Aug to end Oct 2025 with the migration week: 4 Aug-9 Nov 2025, whole weeks; web by store 900.
- D24 (24 Mar 2026) click-and-collect share of web orders by quarter since FY24/25: Helsinki order date; cancelled out; quarters complete when asked (to 25 Jan 2026).
- D27 (7 Apr 2026) ATV by weekday, P11: FY2025/26 weeks 44-47.
- D29 (6 May 2025) active members at the end of last year: as of Sunday 27 Apr 2025; distinct member_id. -> loyalty-and-campaigns/templates/active_members.sql
