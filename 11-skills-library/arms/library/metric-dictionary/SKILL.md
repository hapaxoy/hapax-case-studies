---
name: metric-dictionary
description: The company definition of every Tuomimetsä metric in one place - net sales, gross/VAT, web sales and orders, click-and-collect share, LFL, ATV, active members, member share, new members, campaign uplift, return rate, gross margin, closing stock, weeks of cover, store scope, league table, as-is/as-was.
---

# Metric dictionary

The definitions the company uses in every report, as written by the head of data. The skill named after each block has the SQL and the traps; every answer is checked with `query-check/scripts/query_check.py` before it goes out.

<!-- source: metric_dictionary.md -->
If a request needs a number that is not defined here, ask in the request queue before inventing a definition.

## Sales (sales-reporting)

<!-- facts: DEF-NET-SALES, DEF-NET-SALES-SCOPE -->
Net sales is the net amount excluding VAT, after returns. A return reduces net sales on its own return date, not on the date of the original sale. Store 999 and test articles (category ZZ Test) are left out of net sales. Staff purchases are included.

<!-- facts: DEF-VAT-GROSS -->
Net sales are always excluding VAT. When a request wants figures including VAT, sum gross_amount from the lines. Every line carries its own VAT rate, so never multiply a net total by one flat rate.

<!-- facts: DEF-GROSS-MARGIN -->
Gross margin is net sales minus the standard cost of the goods sold, both after returns: returned units are credited back at standard cost (standard_cost_returned). Gross margin percentage is gross margin divided by net sales.

<!-- facts: DEF-RETURN-RATE -->
Return rate is returned net (refund_net) divided by sold net, grouped by the fiscal week of the original sale. This is the sale-week cohort: a return counts in the week the item was sold, whenever it came back. That is a different date convention from net sales, on purpose.

<!-- facts: DEF-ATV -->
ATV (average transaction value) is net sales before returns divided by the number of sales receipts. It is a store measure: staff purchases, store 999 and test articles are left out, and web orders are not included.

## Web (web-orders)

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

## Like-for-like and stores (lfl-and-store-league)

<!-- facts: DEF-LFL-BASIS, DEF-LFL-OPEN, DEF-LFL-BOTH-YEARS -->
LFL growth compares net sales in the LFL stores for a period with the same fiscal weeks last year, week by week. It covers physical stores only; the web shop is not part of LFL. A store is in the LFL base for a period only if it had been open at least 52 weeks (364 days) before the first day of the period. A store-week counts only if the store traded in that fiscal week in both years: a week in which the store was shut, for a refit or because it had closed, drops out for that store.

<!-- facts: DEF-LFL-REFIT, DEF-LFL-WEEK53 -->
Refit weeks are taken out for the store concerned, in both years, using ref_store_closure. The store stays in the base for its other weeks. Week 53 is not part of LFL, because it has no comparator week.

<!-- facts: DEF-STORE-SCOPE -->
Store counts and store-level analyses cover the physical stores only (store_id below 900). The web shop (store 900) is shown as its own line when a request asks for the total company. Store 999 is never included.

<!-- facts: DEF-STORE-LEAGUE -->
The store league table ranks stores by net sales per trading day. Trading days are the days the store was open: after opening, before closure, outside refit closures and not a closed holiday. A store that traded for only part of the period is still listed, with its own trading days.

## Members and campaigns (loyalty-and-campaigns)

<!-- facts: DEF-ACTIVE-MEMBER -->
An active member has made at least one purchase in the trailing 52 fiscal weeks, ending with the as-of week and including it, in any channel. Count distinct member_id.

<!-- facts: DEF-MEMBER-SHARE -->
Member share of sales is net sales before returns on lines linked to a member, divided by all net sales before returns. Receipts without a member, and guest web orders, count as non-member.

<!-- facts: DEF-NEW-MEMBER -->
A new member is counted on their join date, at the home store in their first version in dim_member (the store where they enrolled). Online sign-ups sit under store 900.

<!-- facts: DEF-UPLIFT -->
Campaign uplift is the mean net sales per targeted member minus the mean per holdout member, over the campaign window plus seven days. A targeted member has at least one exposure row in the campaign. Members with no sales count as zero, and net sales are before returns, on lines linked to the member.

## Stock (stock)

<!-- facts: DEF-STOCK-SEMIADD -->
Closing stock is a snapshot at the end of each fiscal week. Add it across stores and products, but never across weeks. For a period, use the average of the weekly closings or the last week's closing, whichever the request asks for.

<!-- facts: DEF-WEEKS-COVER -->
Weeks of cover is the closing stock units at the end of a fiscal week divided by the average weekly units sold over the prior four fiscal weeks, for the same store or grouping. Units sold are the quantity on sales lines, by sale date.

## Hierarchies (store-and-product-history)

<!-- facts: DEF-HIERARCHY-ASIS -->
Management reporting restates history on the current hierarchy of store regions and product categories. This is called as-is. If a request asks for as-was, use the hierarchy as it stood on the date of the transaction.

## Calendar (fiscal-calendar)

Fiscal years, periods, quarters, week 53, "last period", "YTD" and "this year" are defined in the fiscal-calendar skill.
