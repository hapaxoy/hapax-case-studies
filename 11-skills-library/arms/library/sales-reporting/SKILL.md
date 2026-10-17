---
name: sales-reporting
description: Net sales on the company definition (exclusions, return timing, web on dispatch date), figures including VAT, gross margin, return rate on the sale-week cohort, and ATV - with validated SQL templates and the control-total check against rpt_daily_store_sales.
---

# Sales reporting

## Steps

1. Resolve the dates with `fiscal-calendar/scripts/fiscal.py` (add `--compare` for a year-on-year request).
2. Start from a template below; edit only its `params` CTE and the grouping column.
3. Run `query-check/scripts/query_check.py` with `--grain`, the range, and `--control` for store-level net sales.
4. In the answer, say as-is or as-was, which year a relative phrase meant, and any exclusion that changed a total.

## Templates (all run against the warehouse; see build notes)

| Template | Gives | Reproduces |
|---|---|---|
| `templates/net_sales_by_store_day.sql` | net sales per store per business day; the base for anything else | matches rpt_daily_store_sales exactly for FY2026/27 P05 |
| `templates/net_sales_weekly_yoy.sql` | weekly net sales by region against the same fiscal weeks last year | REQ-D01 |
| `templates/gross_margin_by_category.sql` | net sales, gross margin and margin % by category, as-is | REQ-D10 |
| `templates/gross_sales_incl_vat.sql` | sales including VAT by category, refunds including VAT alongside | - |
| `templates/return_rate_by_category.sql` | return rate on the sale-week cohort, with a cohort-complete flag | REQ-D14 |
| `templates/atv_by_store.sql` | ATV by store | REQ-D25 |

`references/net_sales_pattern.md` explains the `net_lines` CTE every sales query is built on, with REQ-D01 in full.

## Net sales

<!-- facts: DEF-NET-SALES, DEF-NET-SALES-SCOPE -->
Net sales is the net amount excluding VAT, after returns. A return reduces net sales on its own return date, not on the date of the original sale. Store 999 and test articles (category ZZ Test) are left out of net sales. Staff purchases are included.

<!-- facts: TEAM-EXCLUSIONS -->
Always filter out store 999 and category ZZ Test in sales work, and say so when the filter changes a total.

<!-- facts: REG-STAFF-PURCHASE -->
staff_purchase_flag is set on every line of a staff receipt (staff get 15% off). Staff purchases count in net sales and are excluded from ATV.

<!-- facts: DEF-WEB-RECOGNITION, REG-WEB-SALE-DATE -->
Web sales are recognised on the dispatch date in Helsinki time. On a web line, sale_date is the order date and is not used for web net sales. Get the dispatch date by joining fact_web_order on receipt_id = web_order_id.

<!-- facts: REG-RETURN-LAG -->
Returns can arrive up to 30 days after a sale, so a sale-week cohort is not complete until about five weeks later. Return lines are booked where they are processed: web returns sent by post are booked to the web shop.

<!-- facts: DEF-STORE-SCOPE -->
Store counts and store-level analyses cover the physical stores only (store_id below 900). The web shop (store 900) is shown as its own line when a request asks for the total company. Store 999 is never included.

<!-- facts: TEAM-CONTROL-TOTALS, REG-CONTROL-TOTAL -->
Before sending a store-level figure, check the total against rpt_daily_store_sales for the same days. That table holds net sales per store per business day on the company definition (web on its dispatch date, returns on their return date). It has no product, member or channel dimension, so it is a control total, not a source for analysis. Run `query_check.py --control` with the result at store or store-day level; for a regional or total figure the script compares the totals.

## Including VAT

<!-- facts: DEF-VAT-GROSS, REG-VAT-CHANGE -->
Net sales are always excluding VAT. When a request wants figures including VAT, sum gross_amount from the lines. Every line carries its own VAT rate, so never multiply a net total by one flat rate. The general VAT rate rose from 24% to 25.5% on 1 September 2024; the reduced rates (14% and 10%) did not change. dim_product.vat_class says which rate applies to an article. The dictionary does not say how returns enter a figure including VAT; fact_return_line carries refund_gross, so show refunds as their own column and say what you sent.

<!-- facts: TEAM-EXPLICIT-REQUEST -->
When a request explicitly asks for something that differs from a company default (gross instead of net, as-was instead of as-is, UTC instead of Helsinki time, and so on), follow the request and say that you did.

## Gross margin

<!-- facts: DEF-GROSS-MARGIN -->
Gross margin is net sales minus the standard cost of the goods sold, both after returns: returned units are credited back at standard cost (standard_cost_returned). Gross margin percentage is gross margin divided by net sales.

<!-- source: REQ-D10, REQ-D11, REQ-D12, REQ-D13, REQ-D05 -->
For margin, group `SUM(n.net_sales - n.cost)` by the current product version (`JOIN dim_product cp ON cp.sku = n.sku AND cp.is_current`), as REQ-D10 to REQ-D13 did. For as-was, take region or category from `s` and `p` (the version on the date), as REQ-D05 did.

## Return rate

<!-- facts: DEF-RETURN-RATE -->
Return rate is returned net (refund_net) divided by sold net, grouped by the fiscal week of the original sale. This is the sale-week cohort: a return counts in the week the item was sold, whenever it came back. That is a different date convention from net sales, on purpose. The accepted queries (REQ-D14 to REQ-D16) select the sold lines by the fiscal period of fact_sales_line.sale_date, then add the refunds matched through sales_line_id, wherever and whenever they were booked; web against stores is `CASE WHEN s.store_id = 900`.

The template's `cohort_complete` column is false when the last sale in the cohort is less than 30 days before the last loaded date.

## ATV

<!-- facts: DEF-ATV -->
ATV (average transaction value) is net sales before returns divided by the number of sales receipts. It is a store measure: staff purchases, store 999 and test articles are left out, and web orders are not included. The accepted queries use store_id below 900 and NOT staff_purchase_flag, dated by sale_date.

<!-- source: REQ-D26, REQ-D27, REQ-D28 -->
By format (REQ-D26), the format on the sale date is fine because format is the same in every store version. By weekday (REQ-D27), group by dim_date.day_of_week and day_name. One store against the chain (REQ-D28, Pori = store 119): sum per receipt first, then average.

## Hierarchy

<!-- facts: TEAM-ASIS, DEF-HIERARCHY-ASIS -->
Report history as-is unless the requester asks for as-was, and say which one you used. Management reporting restates history on the current hierarchy of store regions and product categories (as-is). As-was means the hierarchy as it stood on the date of the transaction.

Region and category changes are in store-and-product-history.

## Past requests for this skill

Copied from `warehouse-map/references/request_history_digest.md`. Date asked in brackets; the reading the requester accepted after the colon.

<!-- source: REQ-D01, REQ-D02, REQ-D03, REQ-D04, REQ-D10, REQ-D11, REQ-D12, REQ-D13, REQ-D14, REQ-D15, REQ-D16, REQ-D21, REQ-D25, REQ-D26, REQ-D27, REQ-D28, REQ-D33, REQ-D34, REQ-D35, REQ-D36 -->
- D01 (2 Dec 2025) weekly net sales by region, P6 this year vs last: FY2025/26 vs FY2024/25 by fiscal week; as-is; Online its own line. -> sales-reporting/templates/net_sales_weekly_yoy.sql
- D02 (1 Sep 2026) sales by format, last four weeks vs last year: FY2026/27 P4 vs P4 by week; format includes Web.
- D03 (14 Apr 2026) total company weekly net sales, Q3 with last year: weeks 27-39; web in; 999 and ZZ Test out.
- D04 (12 May 2026) net sales by region and period, second half of last year vs the year before: FY2025/26 P7-P12 vs FY2024/25; week 53 dropped; as-is.
- D10 (7 Jul 2026) net sales and gross margin % by category, P2: FY2026/27 P2; margin after returns; as-is. -> sales-reporting/templates/gross_margin_by_category.sql
- D11 (2 Jul 2025) Garden and Electrical gross margin by period, last year: FY2024/25 as-is, outdoor lighting in Electrical all year.
- D12 (23 Jun 2026) top 10 subcategories by gross margin, Q4: FY2025/26 P10-P12 including week 53.
- D13 (12 Nov 2025) Paint & Decorating own label vs brands, first half of FY24/25: P1-P6; current product version.
- D14 (10 Mar 2026) return rate by category, goods sold in the first four periods of last year: FY2025/26 P1-P4; sale-week cohort, complete. -> sales-reporting/templates/return_rate_by_category.sql
- D15 (24 Sep 2025) Furniture return rate by subcategory, FY24/25 sales: returns attributed back to the sale.
- D16 (21 Jan 2026) return rate web vs stores by category, Q1 sales last year: FY2025/26 Q1; web by store 900; refunds follow the line.
- D21 (3 Sep 2026) web sales by category for P4, with share of web: FY2026/27 P4; dispatch date; as-is.
- D25 (30 Sep 2026) ATV by store, last period: FY2026/27 P5. -> sales-reporting/templates/atv_by_store.sql
- D26 (20 May 2025) ATV by format, each quarter of FY24/25: format is the same in every store version.
- D27 (7 Apr 2026) ATV by weekday, P11: FY2025/26 weeks 44-47.
- D28 (27 May 2026) Pori ATV vs the chain by period, second half of last year: Pori is store 119; FY2025/26 P7-P12.
- D33 (10 Feb 2026) top 10 products by margin in the North, first half of last year: FY2025/26 P1-P6; North as-is; web not in the North.
- D34 (18 Aug 2026) top 10 brands by gross margin in the Capital Region, P1-P3 this year: FY2026/27; as-is.
- D35 (26 May 2026) top 5 subcategories by margin in the East, second half of last year: FY2025/26 P7-P12 with week 53; East as-is (no Kouvola).
- D36 (9 Jul 2025) top 10 own-label products by margin in the West, Q4 FY24/25: P10-P12; current product version.
