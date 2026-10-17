# Request history digest

<!-- source: REQ-D01, REQ-D02, REQ-D03, REQ-D04, REQ-D05, REQ-D06, REQ-D07, REQ-D08, REQ-D09, REQ-D10, REQ-D11, REQ-D12, REQ-D13, REQ-D14, REQ-D15, REQ-D16, REQ-D17, REQ-D18, REQ-D19, REQ-D20, REQ-D21, REQ-D22, REQ-D23, REQ-D24, REQ-D25, REQ-D26, REQ-D27, REQ-D28, REQ-D29, REQ-D30, REQ-D31, REQ-D32, REQ-D33, REQ-D34, REQ-D35, REQ-D36, REQ-D37, REQ-D38, REQ-D39, REQ-D40 -->
The 40 accepted requests, with the reading the requester accepted. Date asked in brackets. The template that reproduces a request, where there is one, is named after the arrow.

- D01 (2 Dec 2025) weekly net sales by region, P6 this year vs last: FY2025/26 vs FY2024/25 by fiscal week; as-is; Online its own line. -> sales-reporting/templates/net_sales_weekly_yoy.sql
- D02 (1 Sep 2026) sales by format, last four weeks vs last year: FY2026/27 P4 vs P4 by week; format includes Web.
- D03 (14 Apr 2026) total company weekly net sales, Q3 with last year: weeks 27-39; web in; 999 and ZZ Test out.
- D04 (12 May 2026) net sales by region and period, second half of last year vs the year before: FY2025/26 P7-P12 vs FY2024/25; week 53 dropped; as-is.
- D05 (18 Jun 2025) regional net sales by quarter, last year, regions as they were: FY2024/25 as-was (four regions plus Online). -> store-and-product-history/templates/net_sales_by_region_as_was.sql
- D06 (20 Aug 2025) LFL for Q1: FY2025/26 weeks 1-13; Tammisto's FY2024/25 refit weeks drop out. -> lfl-and-store-league/templates/lfl.sql
- D07 (11 Aug 2026) LFL for P3 this year: weeks 9-13; Kuopio in for week 13 only; Savonlinna out. -> lfl.sql
- D08 (19 May 2026) LFL by region, back half of last year: weeks 27-52; Lohja not yet in the base; the closed store only for weeks it traded. -> lfl.sql
- D09 (8 Sep 2026) YTD LFL as of the end of P4: weeks 1-17, FY2026/27 vs FY2025/26. -> lfl.sql
- D10 (7 Jul 2026) net sales and gross margin % by category, P2: FY2026/27 P2; margin after returns; as-is. -> sales-reporting/templates/gross_margin_by_category.sql
- D11 (2 Jul 2025) Garden and Electrical gross margin by period, last year: FY2024/25 as-is, outdoor lighting in Electrical all year.
- D12 (23 Jun 2026) top 10 subcategories by gross margin, Q4: FY2025/26 P10-P12 including week 53.
- D13 (12 Nov 2025) Paint & Decorating own label vs brands, first half of FY24/25: P1-P6; current product version.
- D14 (10 Mar 2026) return rate by category, goods sold in the first four periods of last year: FY2025/26 P1-P4; sale-week cohort, complete. -> sales-reporting/templates/return_rate_by_category.sql
- D15 (24 Sep 2025) Furniture return rate by subcategory, FY24/25 sales: returns attributed back to the sale.
- D16 (21 Jan 2026) return rate web vs stores by category, Q1 sales last year: FY2025/26 Q1; web by store 900; refunds follow the line.
- D17 (3 Dec 2025) daily web sales, Black Friday week: 24-30 Nov 2025 on the Helsinki dispatch date; returns on their own date. -> web-orders/templates/web_net_sales_daily.sql
- D18 (13 Jan 2026) web orders per week in P8, not cancelled: FY2025/26; Helsinki order date; processing counts. -> web-orders/templates/web_orders_by_week.sql
- D19 (18 Nov 2025) weekly web sales Aug to end Oct 2025 with the migration week: 4 Aug-9 Nov 2025, whole weeks; web by store 900.
- D20 (4 Dec 2024) web orders by hour on Black Friday, Finnish time: 29 Nov 2024, Helsinki hours. -> web-orders/templates/web_orders_by_hour_helsinki.sql
- D21 (3 Sep 2026) web sales by category for P4, with share of web: FY2026/27 P4; dispatch date; as-is.
- D22 (9 Dec 2025) click-and-collect share of web sales, P1-P4: FY2025/26; denominator all web; fulfilment type from fact_web_order. -> web-orders/templates/click_collect_share_of_web_sales.sql
- D23 (1 Oct 2026) stores with the most click-and-collect orders last period, and share: P5 (31 Aug-27 Sep 2026); collected; ready-for-collection date, Helsinki. -> web-orders/templates/click_collect_orders_by_store.sql
- D24 (24 Mar 2026) click-and-collect share of web orders by quarter since FY24/25: Helsinki order date; cancelled out; quarters complete when asked (to 25 Jan 2026).
- D25 (30 Sep 2026) ATV by store, last period: FY2026/27 P5. -> sales-reporting/templates/atv_by_store.sql
- D26 (20 May 2025) ATV by format, each quarter of FY24/25: format is the same in every store version.
- D27 (7 Apr 2026) ATV by weekday, P11: FY2025/26 weeks 44-47.
- D28 (27 May 2026) Pori ATV vs the chain by period, second half of last year: Pori is store 119; FY2025/26 P7-P12.
- D29 (6 May 2025) active members at the end of last year: as of Sunday 27 Apr 2025; distinct member_id. -> loyalty-and-campaigns/templates/active_members.sql
- D30 (8 Oct 2025) active members by tier, last Sunday of September: 28 Sep 2025; tier from the version valid that day. -> active_members.sql
- D31 (14 May 2025) member share by month, November to April: 1 Nov 2024-27 Apr 2025; before returns; web on dispatch date.
- D32 (9 Jun 2026) member share by region, P1 this year: FY2026/27 P1; as-is with Online. -> loyalty-and-campaigns/templates/member_share_of_sales.sql
- D33 (10 Feb 2026) top 10 products by margin in the North, first half of last year: FY2025/26 P1-P6; North as-is; web not in the North.
- D34 (18 Aug 2026) top 10 brands by gross margin in the Capital Region, P1-P3 this year: FY2026/27; as-is.
- D35 (26 May 2026) top 5 subcategories by margin in the East, second half of last year: FY2025/26 P7-P12 with week 53; East as-is (no Kouvola).
- D36 (9 Jul 2025) top 10 own-label products by margin in the West, Q4 FY24/25: P10-P12; current product version.
- D37 (9 Sep 2025) store league table, P4: FY2025/26 P4; net sales per trading day; stores only. -> lfl-and-store-league/templates/store_league_table.sql
- D38 (3 Feb 2026) league table for Q3, new and closed stores marked: every store that traded kept; Savonlinna closed in week 39. -> store_league_table.sql
- D39 (3 Jun 2025) league table for the Large stores, second half of FY24/25: format = 'Large'; closed holidays are not trading days. -> store_league_table.sql
- D40 (19 Aug 2026) league table for P3 with Kuopio's refit: Kuopio ranked on the days it traded. -> store_league_table.sql
