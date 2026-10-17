---
name: web-orders
description: Web sales and web orders - revenue on the Helsinki dispatch date, order counts on the Helsinki order date, cancelled and processing orders, click-and-collect share, guest orders, UTC timestamps and the November 2025 platform migration that broke channel_code.
---

# Web sales and orders

Two different things, counted differently: **web sales** (money, from sales and return lines, on the dispatch date) and **web orders** (counts, from fact_web_order, on the order date).

## Steps

1. Dates from `fiscal-calendar/scripts/fiscal.py`.
2. Start from a template; edit `params`.
3. Check with `query-check/scripts/query_check.py`. For web net sales add `--control --control-stores web --value-col web_net_sales` (store 900 is in rpt_daily_store_sales). For anything filtered on a timestamp, add `--ts-col` with the UTC column to catch a filter applied to the UTC date.

| Template | Gives | Reproduces |
|---|---|---|
| `templates/web_net_sales_daily.sql` | web net sales per Helsinki business day | REQ-D17 |
| `templates/web_orders_by_week.sql` | web orders per fiscal week, with the click-and-collect share of orders | REQ-D18 |
| `templates/web_orders_by_hour_helsinki.sql` | web orders per Helsinki hour of one day | REQ-D20 |
| `templates/click_collect_share_of_web_sales.sql` | click-and-collect share of web net sales by period | REQ-D22 |
| `templates/click_collect_orders_by_store.sql` | collected orders by collection store, with share | REQ-D23 (all stores, not the top 15) |
| `templates/click_collect_share_of_orders_by_quarter.sql` | click-and-collect share of web orders by quarter, up to the last quarter complete on the request date | REQ-D24 |

## Web sales

<!-- facts: DEF-WEB-RECOGNITION, REG-WEB-SALE-DATE -->
Web sales are recognised on the dispatch date in Helsinki time. On a web line, sale_date is the order date and is not used for web net sales. Get the dispatch date by joining fact_web_order on receipt_id = web_order_id.

<!-- facts: REG-STORE-900 -->
The web shop is a pseudo-store, store_id 900 (region Online, format Web), so that web lines and web returns have a store key. Web lines are told apart by store_id, not by channel_code.

<!-- facts: REG-RETURN-LAG -->
Returns can arrive up to 30 days after a sale, so a sale-week cohort is not complete until about five weeks later. Return lines are booked where they are processed: web returns sent by post are booked to the web shop.

<!-- facts: DEF-NET-SALES, DEF-NET-SALES-SCOPE -->
Net sales is the net amount excluding VAT, after returns. A return reduces net sales on its own return date, not on the date of the original sale. Store 999 and test articles (category ZZ Test) are left out of net sales. Staff purchases are included.

<!-- facts: REG-TEST-SKU -->
Test articles sit in category ZZ Test. They are sold in store 999 and in a few web test orders, and are left out of all reporting.

## Web orders

<!-- facts: DEF-WEB-ORDER-COUNT -->
Web orders are counted on the order date in Helsinki time. An order that is still processing is counted; a cancelled one is not. Count from fact_web_order, not from sales lines, or processing orders go missing.

<!-- facts: DEF-WEB-CANCELLED, REG-CANCELLED -->
Cancelled orders are not web sales and are not counted as web orders. Cancelled orders stay in fact_web_order with status cancelled, no dispatch time and no sales lines. Orders not yet dispatched have status processing and also have no sales lines until they are dispatched.

<!-- facts: REG-GUEST-ORDERS -->
Guest web orders (checkout without logging in) have no member key. Logged-in orders carry the member's key.

## Click-and-collect

<!-- facts: DEF-CLICK-COLLECT -->
Click-and-collect is counted as web. The click-and-collect share is click-and-collect net sales divided by all web net sales. For click-and-collect, dispatch_ts_utc is the time the order was ready for collection, and pickup_store_key is the collection store.

<!-- source: REQ-D22, REQ-D23, REQ-D24 -->
A share of web *sales* uses net sales by fulfilment type (REQ-D22); a share of web *orders* counts orders on the order date (REQ-D24). Stores handling collections count collected orders on the ready-for-collection date (REQ-D23).

<!-- facts: CAL-RELATIVE, CAL-DATA-THROUGH -->
<!-- source: REQ-D24 -->
A series by quarter or by period stops at the last quarter or period complete as of the date of the request; a part quarter or period is not shown. REQ-D24, asked on 24 March 2026 for the click-and-collect share of web orders by quarter since the start of FY24/25, stopped at FY2025/26 Q3 (ended 25 January 2026), because Q4 was still running. With the warehouse loaded through 4 October 2026, the last complete period is FY2026/27 P05 and the last complete quarter is FY2026/27 Q1.

<!-- facts: DEF-CLICK-COLLECT, DEF-WEB-ORDER-COUNT, DEF-WEB-CANCELLED, DEF-TIMEZONE, CAL-RELATIVE -->
<!-- source: REQ-D24 -->
The by-quarter example. REQ-D24, asked 24 March 2026: click-and-collect share of web orders by quarter since the start of FY24/25. Orders on the Helsinki order date, cancelled out, and only the quarters complete when asked:

```sql
SELECT d.fiscal_year, d.fiscal_quarter,
       COUNT(*) AS web_orders,
       SUM(CASE WHEN o.fulfilment_type = 'click_and_collect' THEN 1 ELSE 0 END) AS click_collect_orders,
       ROUND(100.0 * SUM(CASE WHEN o.fulfilment_type = 'click_and_collect' THEN 1 ELSE 0 END) / COUNT(*), 1) AS click_collect_share_pct
FROM fact_web_order o
JOIN dim_date d ON d.calendar_date = CAST(timezone('Europe/Helsinki', o.order_ts_utc AT TIME ZONE 'UTC') AS DATE)
WHERE o.status <> 'cancelled'
  AND d.calendar_date <= DATE '2026-01-25'          -- last complete quarter when asked (Q3 FY2025/26)
GROUP BY 1, 2
ORDER BY 1, 2;
```

`templates/click_collect_share_of_orders_by_quarter.sql` does the same with the cut-off worked out from the request date.

## The migration and the legacy view

<!-- facts: REG-MIGRATION -->
The web platform migrated on 3 November 2025. channel_code stops being filled from that date and channel_id is used instead. Click-and-collect gets its own key (3). Before the migration, click-and-collect orders carry channel_code WB and no channel_id. So neither channel column works across the migration: use store_id 900 for web and fact_web_order.fulfilment_type for click-and-collect.

<!-- facts: TEAM-NO-LEGACY-VIEW, REG-LEGACY-VIEW -->
Do not use rpt.v_daily_sales. It is built on channel_code and from 3 November 2025 it silently leaves out web sales. rpt.v_weekly_store_sales is built on it and has the same gap. Some dashboards still use them.

<!-- source: REQ-D19 -->
A weekly web series across the migration (REQ-D19, 4 August to 9 November 2025) runs straight through when web is identified by store 900.

## Time zone

<!-- facts: REG-UTC, DEF-TIMEZONE -->
Columns ending _ts_utc hold UTC. sale_date is the Helsinki business date of the sale. Reporting is in Helsinki time and a day changes at local midnight, not at midnight UTC. Finland is UTC+2 in winter and UTC+3 in summer; the clocks changed on 30 March 2025 and 26 October 2025, among other dates. The accepted queries convert with `CAST(timezone('Europe/Helsinki', col AT TIME ZONE 'UTC') AS DATE)`, or `hour(...)` for the hour.

<!-- source: REQ-D17, REQ-D20 -->
Black Friday 2024 was 29 November (REQ-D20); Black Friday week 2025 ran 24 to 30 November (REQ-D17).

## Past requests for this skill

Copied from `warehouse-map/references/request_history_digest.md`. Date asked in brackets; the reading the requester accepted after the colon.

<!-- source: REQ-D16, REQ-D17, REQ-D18, REQ-D19, REQ-D20, REQ-D21, REQ-D22, REQ-D23, REQ-D24 -->
- D16 (21 Jan 2026) return rate web vs stores by category, Q1 sales last year: FY2025/26 Q1; web by store 900; refunds follow the line.
- D17 (3 Dec 2025) daily web sales, Black Friday week: 24-30 Nov 2025 on the Helsinki dispatch date; returns on their own date. -> web-orders/templates/web_net_sales_daily.sql
- D18 (13 Jan 2026) web orders per week in P8, not cancelled: FY2025/26; Helsinki order date; processing counts. -> web-orders/templates/web_orders_by_week.sql
- D19 (18 Nov 2025) weekly web sales Aug to end Oct 2025 with the migration week: 4 Aug-9 Nov 2025, whole weeks; web by store 900.
- D20 (4 Dec 2024) web orders by hour on Black Friday, Finnish time: 29 Nov 2024, Helsinki hours. -> web-orders/templates/web_orders_by_hour_helsinki.sql
- D21 (3 Sep 2026) web sales by category for P4, with share of web: FY2026/27 P4; dispatch date; as-is.
- D22 (9 Dec 2025) click-and-collect share of web sales, P1-P4: FY2025/26; denominator all web; fulfilment type from fact_web_order. -> web-orders/templates/click_collect_share_of_web_sales.sql
- D23 (1 Oct 2026) stores with the most click-and-collect orders last period, and share: P5 (31 Aug-27 Sep 2026); collected; ready-for-collection date, Helsinki. -> web-orders/templates/click_collect_orders_by_store.sql
- D24 (24 Mar 2026) click-and-collect share of web orders by quarter since FY24/25: Helsinki order date; cancelled out; quarters complete when asked (to 25 Jan 2026).
