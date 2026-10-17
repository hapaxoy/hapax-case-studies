# Metric dictionary

Tuomimetsä Oy, Data & Analytics wiki. Owner: head of data, Outi Kallio. This page holds the company definitions we use in every report and request. If you need a number that is not here, ask in the request queue before you invent a definition.

## 1. Fiscal calendar

<!-- facts: CAL-YEAR -->
The fiscal year starts on the Monday nearest 1 May, and fiscal weeks run Monday to Sunday. A year is written like FY2025/26, which is the year that began in April 2025.

<!-- facts: CAL-FY-DATES -->
FY2024/25 runs from 29 April 2024 to 27 April 2025 and has 52 weeks. FY2025/26 runs from 28 April 2025 to 3 May 2026 and has 53 weeks. FY2026/27 starts on 4 May 2026.

<!-- facts: CAL-PERIODS -->
There are 12 periods in a year, built from weeks in a 4-4-5 pattern within each quarter (four weeks, four weeks, five weeks). A quarter is three periods: Q1 is P1 to P3 (weeks 1 to 13), Q2 is P4 to P6, Q3 is P7 to P9 and Q4 is P10 to P12.

<!-- facts: CAL-WEEK53 -->
FY2025/26 has 53 weeks. Week 53 (27 April 2026 to 3 May 2026) is added to period 12, which then runs six weeks. Week 53 has no comparator week in the prior year.

<!-- facts: CAL-COMPARE -->
To compare with last year, line up the same fiscal week or the same period number, so that the comparison is week-aligned. Do not line up calendar dates: the same calendar dates fall in a different fiscal week each year.

<!-- facts: CAL-RELATIVE -->
"Last period" means the last completed fiscal period. "YTD" means the fiscal year to date through the last completed fiscal week. "This year" means the current fiscal year.

<!-- facts: CAL-DATA-THROUGH -->
The warehouse is loaded through Sunday 4 October 2026 (FY2026/27 week 22). Period 6 of FY2026/27 has only its first week so far. The last complete period is FY2026/27 P05, which ended on 27 September 2026.

<!-- facts: CAL-CLOSED-DAYS -->
The stores are shut on New Year's Day, Epiphany, Good Friday, Easter Sunday, May Day, Midsummer Eve, Midsummer Day, Independence Day, Christmas Eve, Christmas Day, Boxing Day. The column dim_date.is_trading_day is false on those days.

## 2. Net sales

<!-- facts: DEF-NET-SALES -->
Net sales is the net amount excluding VAT, after returns. A return reduces net sales on its own return date, not on the date of the original sale.

<!-- facts: DEF-NET-SALES-SCOPE -->
Store 999 (the training store) and test articles (category ZZ Test) are left out of net sales. Staff purchases are included.

<!-- facts: DEF-VAT-GROSS -->
Net sales are always excluding VAT. When a request wants figures including VAT, sum gross_amount from the lines. Every line carries its own VAT rate, so never multiply a net total by one flat rate.

## 3. Web sales and time

<!-- facts: DEF-WEB-RECOGNITION -->
Web sales are recognised on the dispatch date in Helsinki time. On a web line, sale_date is the order date and is not used for web net sales.

<!-- facts: DEF-WEB-CANCELLED -->
Cancelled orders are not web sales and are not counted as web orders.

<!-- facts: DEF-WEB-ORDER-COUNT -->
Web orders are counted on the order date in Helsinki time. An order that is still processing is counted; a cancelled one is not.

<!-- facts: DEF-CLICK-COLLECT -->
Click-and-collect is counted as web. The click-and-collect share is click-and-collect net sales divided by all web net sales.

<!-- facts: DEF-TIMEZONE -->
Timestamps in the warehouse are UTC. Reporting is in Helsinki time, and a day changes at local midnight, not at midnight UTC.

## 4. Like-for-like (LFL)

<!-- facts: DEF-LFL-BASIS -->
Like-for-like (LFL) growth compares net sales in the LFL stores for a period with the same fiscal weeks last year, week by week. It covers physical stores only. The web shop is not part of LFL.

<!-- facts: DEF-LFL-OPEN -->
A store is in the LFL base for a period only if it had been open at least 52 weeks (364 days) before the first day of the period.

<!-- facts: DEF-LFL-BOTH-YEARS -->
A store-week counts only if the store traded in that fiscal week in both years. A week in which the store was shut, whether for a refit or because it had closed, drops out for that store.

<!-- facts: DEF-LFL-REFIT -->
Refit weeks are taken out for the store concerned, in both years, using ref_store_closure. The store stays in the base for its other weeks.

<!-- facts: DEF-LFL-WEEK53 -->
Week 53 is not part of LFL, because it has no comparator week.

## 5. Transactions, members and campaigns

<!-- facts: DEF-ATV -->
ATV (average transaction value) is net sales before returns divided by the number of sales receipts. It is a store measure: staff purchases, store 999 and test articles are left out, and web orders are not included.

<!-- facts: DEF-ACTIVE-MEMBER -->
An active member has made at least one purchase in the trailing 52 fiscal weeks, ending with the as-of week and including it, in any channel. Count distinct member_id.

<!-- facts: DEF-MEMBER-SHARE -->
Member share of sales is net sales before returns on lines linked to a member, divided by all net sales before returns. Receipts without a member, and guest web orders, count as non-member.

<!-- facts: DEF-NEW-MEMBER -->
A new member is counted on their join date, at the home store in their first version in dim_member (the store where they enrolled). Online sign-ups sit under store 900.

<!-- facts: DEF-UPLIFT -->
Campaign uplift is the mean net sales per targeted member minus the mean per holdout member, over the campaign window plus seven days. A targeted member has at least one exposure row in the campaign. Members with no sales count as zero, and net sales are before returns, on lines linked to the member.

## 6. Returns and margin

<!-- facts: DEF-RETURN-RATE -->
Return rate is returned net (refund_net) divided by sold net, grouped by the fiscal week of the original sale. This is the sale-week cohort: a return counts in the week the item was sold, whenever it came back. That is a different date convention from net sales, on purpose.

<!-- facts: DEF-GROSS-MARGIN -->
Gross margin is net sales minus the standard cost of the goods sold, both after returns: returned units are credited back at standard cost. Gross margin percentage is gross margin divided by net sales.

## 7. Stock

<!-- facts: DEF-STOCK-SEMIADD -->
Closing stock is a snapshot at the end of each fiscal week. Add it across stores and products, but never across weeks. For a period, use the average of the weekly closings or the last week's closing, whichever the request asks for.

<!-- facts: DEF-WEEKS-COVER -->
Weeks of cover is the closing stock units at the end of a fiscal week divided by the average weekly units sold over the prior four fiscal weeks, for the same store or grouping. Units sold are the quantity on sales lines, by sale date.

## 8. Hierarchies and stores

<!-- facts: DEF-HIERARCHY-ASIS -->
Management reporting restates history on the current hierarchy of store regions and product categories. This is called as-is. If a request asks for as-was, use the hierarchy as it stood on the date of the transaction.

<!-- facts: DEF-STORE-SCOPE -->
Store counts and store-level analyses cover the physical stores only (store_id below 900). The web shop (store 900) is shown as its own line when a request asks for the total company. Store 999 is never included.

<!-- facts: DEF-STORE-LEAGUE -->
The store league table ranks stores by net sales per trading day. Trading days are the days the store was open: after opening, before closure, outside refit closures and not a closed holiday. A store that traded for only part of the period is still listed, with its own trading days.
