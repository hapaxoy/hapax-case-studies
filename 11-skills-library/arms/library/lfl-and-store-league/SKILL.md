---
name: lfl-and-store-league
description: Like-for-like (LFL) growth and the store league table - which store-weeks or trading days count around openings, the Savonlinna closure, refits and week 53 - with validated SQL that reproduces the accepted LFL and league-table requests.
---

# LFL and the store league table

## Steps

1. Get the fiscal weeks with `fiscal-calendar/scripts/fiscal.py ... --compare`. LFL runs on fiscal week numbers in two years; week 53 never counts.
2. Edit the `params` CTE of `templates/lfl.sql` (two years, first and last fiscal week) or `templates/store_league_table.sql` (first and last date).
3. To explain an LFL figure, run `templates/lfl_store_weeks.sql` with the same params: it lists each store's LFL weeks and the weeks that dropped out.
4. Check with `query-check/scripts/query_check.py`; for the league table add `--control --control-stores physical --start ... --end ...`.

| Template | Reproduces exactly |
|---|---|
| `templates/lfl.sql` (total row with region NULL, then one row per region as-is) | REQ-D06, REQ-D07, REQ-D08, REQ-D09 |
| `templates/lfl_store_weeks.sql` | - (diagnostic) |
| `templates/store_league_table.sql` | REQ-D37, REQ-D38, REQ-D39 (add `WHERE cs.format = 'Large'` before ranking), REQ-D40 |

## LFL definition

<!-- facts: DEF-LFL-BASIS, DEF-LFL-OPEN, DEF-LFL-BOTH-YEARS -->
LFL growth compares net sales in the LFL stores for a period with the same fiscal weeks last year, week by week. It covers physical stores only; the web shop is not part of LFL. A store is in the LFL base for a period only if it had been open at least 52 weeks (364 days) before the first day of the period. A store-week counts only if the store traded in that fiscal week in both years: a week in which the store was shut, for a refit or because it had closed, drops out for that store.

<!-- facts: DEF-LFL-REFIT, DEF-LFL-WEEK53 -->
Refit weeks are taken out for the store concerned, in both years, using ref_store_closure. The store stays in the base for its other weeks. Week 53 is not part of LFL, because it has no comparator week.

<!-- facts: TEAM-LFL-EDGE -->
LFL edge cases. A store back from a refit is excluded for the refit weeks only. The two new stores enter the LFL base on 1 September 2025 (136) and 3 November 2025 (137). The closed store (129) drops out from its closure. Week 53 is never LFL. The web shop is never LFL.

<!-- source: REQ-D06, REQ-D07, REQ-D08, REQ-D09 -->
How the accepted LFL queries apply this: build every physical store x fiscal week for both years, flag each as trading (open_date on or before the week's Monday, close_date on or after its Sunday, no overlap with ref_store_closure), keep store-weeks trading in both years, and test the opening rule as open_date <= first day of the requested range - 364. For a multi-period range that first day is the start of the whole range: REQ-D08 (weeks 27 to 52 of FY2025/26) left Lohja out entirely. Open and close dates come from the current dim_store version.

<!-- facts: DEF-LFL-BASIS, DEF-LFL-OPEN, DEF-LFL-BOTH-YEARS -->
<!-- source: REQ-D06, REQ-D07, REQ-D08, REQ-D09 -->
An LFL answer is one total (this year, last year, growth) unless the request asks for a breakdown. REQ-D06 (Q1), REQ-D07 (P3) and REQ-D09 (YTD to the end of P4) each returned one row; REQ-D08 asked "by region" and got one row per region, as-is.

`lfl.sql` returns the total row (region NULL) first and the regions after it: send the total row alone unless the request asks for a breakdown.

## The stores and dates that move LFL and the league table

<!-- facts: REG-STORE-EVENTS -->
Store openings: Tampere Lamminpää (136) opened 2 September 2024; Lohja (137) opened 4 November 2024. Store closure: Savonlinna (129) closed 25 January 2026.

<!-- facts: REG-REFITS -->
Refit closures, each a run of whole fiscal weeks with no sales: Vantaa Tammisto (104), 8 July 2024 to 11 August 2024 (5 weeks); Pori (119), 8 September 2025 to 12 October 2025 (5 weeks); Kuopio (125), 15 June 2026 to 26 July 2026 (6 weeks). They are listed in ref_store_closure.

<!-- source: REQ-D06, REQ-D07, REQ-D38 -->
In the history: Tammisto's FY2024/25 refit weeks dropped out of Q1 FY2025/26 LFL (REQ-D06); Kuopio counted only for week 13 of P3 FY2026/27 and Savonlinna was out (REQ-D07); Savonlinna closed in week 39, so it had fewer trading days in the Q3 FY2025/26 league table (REQ-D38).

## Store league table

<!-- facts: DEF-STORE-LEAGUE -->
The store league table ranks stores by net sales per trading day. Trading days are the days the store was open: after opening, before closure, outside refit closures and not a closed holiday. A store that traded for only part of the period is still listed, with its own trading days.

<!-- facts: CAL-CLOSED-DAYS -->
The stores are shut on New Year's Day, Epiphany, Good Friday, Easter Sunday, May Day, Midsummer Eve, Midsummer Day, Independence Day, Christmas Eve, Christmas Day and Boxing Day. dim_date.is_trading_day is false on those days.

<!-- facts: DEF-STORE-SCOPE -->
Store counts and store-level analyses cover the physical stores only (store_id below 900). The web shop (store 900) is shown as its own line when a request asks for the total company. Store 999 is never included.

<!-- facts: DEF-NET-SALES, DEF-NET-SALES-SCOPE -->
Net sales is the net amount excluding VAT, after returns. A return reduces net sales on its own return date, not on the date of the original sale. Store 999 and test articles (category ZZ Test) are left out of net sales. Staff purchases are included.

<!-- source: REQ-D39, schema_comments.csv -->
The league table for "Large stores" (REQ-D39) filtered `format = 'Large'` and ranked within that format. The dim_store.format comment ("Hyper, Standard or Express") is out of date; list the distinct values before filtering.

## Past requests for this skill

Copied from `warehouse-map/references/request_history_digest.md`. Date asked in brackets; the reading the requester accepted after the colon.

<!-- source: REQ-D06, REQ-D07, REQ-D08, REQ-D09, REQ-D37, REQ-D38, REQ-D39, REQ-D40 -->
- D06 (20 Aug 2025) LFL for Q1: FY2025/26 weeks 1-13; Tammisto's FY2024/25 refit weeks drop out. -> lfl-and-store-league/templates/lfl.sql
- D07 (11 Aug 2026) LFL for P3 this year: weeks 9-13; Kuopio in for week 13 only; Savonlinna out. -> lfl.sql
- D08 (19 May 2026) LFL by region, back half of last year: weeks 27-52; Lohja not yet in the base; the closed store only for weeks it traded. -> lfl.sql
- D09 (8 Sep 2026) YTD LFL as of the end of P4: weeks 1-17, FY2026/27 vs FY2025/26. -> lfl.sql
- D37 (9 Sep 2025) store league table, P4: FY2025/26 P4; net sales per trading day; stores only. -> lfl-and-store-league/templates/store_league_table.sql
- D38 (3 Feb 2026) league table for Q3, new and closed stores marked: every store that traded kept; Savonlinna closed in week 39. -> store_league_table.sql
- D39 (3 Jun 2025) league table for the Large stores, second half of FY24/25: format = 'Large'; closed holidays are not trading days. -> store_league_table.sql
- D40 (19 Aug 2026) league table for P3 with Kuopio's refit: Kuopio ranked on the days it traded. -> store_league_table.sql
