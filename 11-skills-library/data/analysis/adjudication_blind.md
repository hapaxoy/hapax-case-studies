# Arm-blind review list (Phase 6)

Each item is one run on an ambiguous or undocumented-issue request. Arm, model and run id are hidden. For each item decide PASS or FAIL.

Criterion for an ambiguous request: the `assumptions` list states which reading the answer takes (what 'biggest', 'best-selling', 'last month', 'customers' or 'doing well' means), in words a requester would recognise as that reading. The result table already matches that reading.
Criterion for an undocumented-issue request, or a reading that reaches last year's double-posted week: the `caveats` list names the data problem that makes the published number wrong (the duplicated rows, lost member keys, mislabelled channel), so a requester would be warned. The result table already carries the published number.

## A001
Request: Quick one: how many customers do we have in Tampere?
Reading the result matches: Members whose home store is in Tampere (all enrolled members)
Assumptions: ["Interpreted 'customers in Tampere' as loyalty members registered to Tampere stores, not web shop (900) or training store (999)", "Counted current member versions only, excluding historical versions", "Did not require that members have made a purchase; counted all registered members"]
Caveats: ["This count includes members registered to Tampere but may not have purchased recently", "Alternative interpretation: 11,967 distinct members have made at least one purchase transaction at a Tampere store location (includes members from other regions who visited Tampere stores)", "Web shop (store 900) is assigned to Tampere in the data but is not a physical location; customers who signed up online (home_store_id = 900) are not included in this count", "The query-check validation passed with no deprecated objects or house-rule violations"]

Decision: 

## A002
Request: Quick one: how many customers do we have in Tampere?
Reading the result matches: Members whose home store is in Tampere (all enrolled members)
Assumptions: ["The warehouse has no customer table. The only identified customer is the loyalty member, so 'customers' is read as loyalty members.", "'In Tampere' is read as a member whose home store is one of the four Tampere stores: 115 Tampere Hervanta (2,788 members), 116 Tampere Lielahti (1,721), 117 Tampere Kaleva (1,692) and 136 Tampere Lamminpää (974).", "No activity filter was applied: all current members are counted, whether or not they have bought recently. The request does not define 'customer', and the dictionary's 'active member' (a purchase in the last 52 fiscal weeks) was not asked for.", "Counted as of the warehouse load date, Sunday 4 October 2026, using the current member version."]
Caveats: ["'Customer' has no company definition. The figure is loyalty members only. Shoppers who do not use a loyalty card cannot be identified in the data and are not included, so it is not a count of everyone who shops in Tampere. Jukka should confirm that this definition is the one he wants.", "Correction: dim_store lists store 900 (the web shop) and store 999 (the training store) with city Tampere. Both are left out. Including them would wrongly add the online sign-ups (12,028 members with home store 900) and test or training records to a Tampere count.", "Correction: dim_member keeps one row per member version, so counting rows would give 11,000+ for these stores instead of 7,175 because of the tier, home store and consent changes. Each member is counted once, on the current version. A member who moved home store between versions is counted only at the current home store.", "Alternative readings, not used for the answer. Of the 7,175, 4,441 made a purchase in the last 52 fiscal weeks to 4 October 2026 (the dictionary's 'active member'). 7,648 distinct members bought in a Tampere store in that period, including members whose home store is elsewhere. 4,841 of the 7,175 have marketing consent, which matters if the number is meant for a mailing.", "Members whose home store is online (store 900) are not placed in Tampere even though the web shop is registered in Tampere."]

Decision: 

## A003
Request: Need the average stock value for the West region in period 11 last year, split by category.
Reading the result matches: b: returns the published number and names the problem in `caveats`
The data problem (for the criterion): The West region's stock snapshot for the week ending 8 March 2026 was loaded twice, so every West store-article row for that week exists twice.
Assumptions: ["Period 11 last year = FY2025/26 P11 (fiscal weeks 44–47, 2026-02-23 to 2026-03-22)", "West region = current West region (as-is reporting, after April 2025 reorganisation)", "Average stock value = average closing_value across the 4 weeks in the period, summed by store and week then averaged by category"]
Caveats: ["Stock is counted only on week-ending Sundays; intermediate-day values are not available", "This covers only articles stocked by physical stores in the West region; web orders are picked from a central warehouse not included here", "All 10 categories with stock in the West region in this period are shown; no categories had zero stock"]

Decision: 

## A004
Request: Quick one: how many customers do we have in Tampere?
Reading the result matches: Members whose home store is in Tampere (all enrolled members)
Assumptions: ["'Customers' means loyalty programme members, the only identifiable customer population in the warehouse", "'In Tampere' means the member's home store is one of the four Tampere stores: Hervanta (115), Lielahti (116), Kaleva (117) and Lamminpää (136); the warehouse holds no member address or city", "Counted all current members, whether or not they have bought recently, since no activity window was given and no 'active member' definition is in the schema. As a rough comparison, 4,438 of these members bought anything in the 12 months to 8 Oct 2026", "Counted as of the request date (8 Oct 2026), using the latest member records in the warehouse"]
Caveats: ["The warehouse records the city 'Tampere' for the web shop (store 900) and the training store (999) as well. Online sign-ups carry home store 900, so the 12,028 members who joined online are not counted as Tampere customers.", "Counting every version row in dim_member instead of one row per member would give about 3,000 extra rows for members who changed tier or home store. Counting current versions per member_id avoids that double counting.", "Home store is where a member signed up or is assigned, not necessarily where they live; members may live in Tampere but be assigned to another store or online, and the reverse. For a different reading, 7,632 distinct members bought in the four Tampere stores in the 12 months to 8 Oct 2026, which is a different population from the 7,175 above.", "The count by home store is Hervanta 2,788, Lielahti 1,721, Kaleva 1,692 and Lamminpää 974; Lamminpää opened on 2 Sep 2024, so its base is younger.", "The dim_store comments say formats are Hyper, Standard or Express, but the data shows Large and Medium for the Tampere stores. This does not affect the count.", "Backup, staging and old copies of tables (bak_, stg_, _old, tmp_) were not used. The staged member updates (stg_member_updates) were checked and all already appear in dim_member."]

Decision: 

## A005
Request: Can I have the store league table for period 5 last year?
Reading the result matches: b: returns the published number and names the problem in `caveats`
The data problem (for the criterion): A till re-sync posted every receipt of Tampere Lielahti (116) for the week 15 to 21 September 2025 twice.
Assumptions: ["Period 5 last year interpreted as FY2025/26 P5 (requested 2026-10-08 during FY2026/27), covering 2025-08-25 to 2025-09-21", "Store 116 (Tampere Lielahti) has 28 trading days despite the control-total gap; all trading-day calculations verified"]
Caveats: ["Control-total discrepancy on store 116: query calculates 47,679.15 EUR in net sales but rpt_daily_store_sales reports 37,288.62 EUR (gap 10,390.53), a 27.8% difference. The gap appears in net_sales_before_returns (query 49,995.41 vs control 39,604.88); returns match exactly (2,316.26). Root cause undiagnosed; the query logic follows the validated template exactly. Contact TEAM-CONTROL-TOTALS to investigate.", "Store 119 (Pori) has only 14 trading days in the period due to a refit closure (8 September to 12 October 2025); it is ranked within all stores despite partial trading."]

Decision: 

## A006
Request: What were the whole company's net sales last month?
Reading the result matches: Calendar September 2026
Assumptions: ["Last month interpreted as the full calendar month preceding the request (September 2026), not a rolling 30-day period", "Net sales sourced from rpt_daily_store_sales table rather than aggregating fact_sales_line, as this report is the official daily summary"]
Caveats: ["Data current through October 4, 2026 (request dated October 9, 2026 but data nine days behind)"]

Decision: 

## A007
Request: Can you rank the five store regions by how they are doing this year so far? Stores only, no web shop.
Reading the result matches: Rank by like-for-like growth against last year, year to date
Assumptions: ["'How they are doing' is read as growth in net sales against the same weeks last year, like-for-like, because a raw YTD total mostly ranks regions by size. Ranked from highest growth to lowest.", "'This year so far' is read as the fiscal year to date. Weeks 1 to 5 of P06 are open, so I included the one complete week after P05 (28 Sep to 4 Oct) rather than stopping at 27 Sep.", "Five regions means North, South, East, West and the Capital Region, which exists in the warehouse from 28 Apr 2025.", "Staff purchases are kept in net sales because the team's own daily store report includes them.", "Prior-year Pori refit days (8 Sep to 4 Oct 2025 in the window) are left out, together with the matching days this year (14 Sep to 4 Oct 2026). Kuopio's refit days (15 Jun to 26 Jul 2026) are left out, together with the matching prior-year days."]
Caveats: ["Duplicate sales lines: 418 receipt lines in Sept 2025 at Tampere Lielahti (West) were loaded twice (second load on 2025-09-23). I kept one copy of each. Left in, West's prior-year base is overstated and its growth looks 0.7 points lower in the naive figure, and West and South swap places (naive West +2.63%, South +2.11%).", "Savonlinna (East) closed on 2026-01-25. It has 60,143 EUR of prior-year sales and none this year, so I excluded it from both years. Left in, it drags East down.", "Kuopio (East) was closed for a refit from 15 Jun to 26 Jul 2026 (6 weeks) and Pori (West) from 8 Sep to 12 Oct 2025 (5 weeks). I removed those weeks from both years. Without any of these corrections, East shows -11.6%, which is mostly closures and not trading.", "Store regions were redrawn on 28 Apr 2025: Capital Region was created from five South stores, and Kouvola moved from East to South. I used the current mapping for both years. The prior-year window starts after the change, so this does not alter the figures, but any comparison with earlier years would need restating.", "East is the only region below last year, at -0.19% after the corrections. That is within noise, so East is effectively flat. The gaps between West, South and Capital Region are about 0.2 to 0.8 points, so their order is not firm.", "Warehouse tables with bak_, stg_, tmp_ or _old names were not used. The web shop sits in the same sales table as the stores and was filtered out by store number.", "Fiscal P06 is not fully loaded, so the 4 October cut-off excludes the incomplete remainder of the period."]

Decision: 

## A008
Request: Can you rank the five store regions by how they are doing this year so far? Stores only, no web shop.
Reading the result matches: Rank by like-for-like growth against last year, year to date
Assumptions: ["'How they are doing' has no metric in the data dictionary. I read it as like-for-like net sales growth year to date, the company's standard way of comparing stores. LFL stops the ranking being skewed by the two stores opened in 2024, the closed store, and refit closures. Net sales this year and last year are shown so the base is visible.", "'This year so far' = FY2026/27 YTD through the last completed fiscal week (week 22, ended Sunday 4 October 2026). The comparison year is FY2025/26 weeks 1 to 22.", "'Five store regions' = North, South, East, West and Capital Region, as-is. Online and Head office are not included.", "Figures are for the LFL store-weeks only, so they are lower than total regional net sales. The growth percentages are the ranking basis.", "Ranking is by LFL growth percentage, highest first. Ranking by absolute net sales would put West first and North last.", "Opening-rule test uses the start of the whole range, 4 May 2026, as in the accepted LFL queries."]
Caveats: ["Correction: fact_sales_line has 418 duplicated lines (same receipt_id and line_no, different sales_line_id, same amounts and store) all in FY2025/26 week 21 (15 to 21 September 2025), loaded 16 to 23 September 2025. I kept one row per receipt_id and line_no. Without this fix, last year's West is overstated by about 10,000 EUR and West shows 1.33% LFL growth instead of 1.93%. The ranking does not change, but West's growth would be understated. The other regions were not affected (the duplicates fall in West stores in the LFL base).", "After the de-duplication, store-level net sales for weeks 1 to 22 of both years match rpt_daily_store_sales with no differences by store and day, so the figures reconcile to the control total.", "Week-22 LFL for East is slightly negative (-0.19%), so East is the only region below last year. The gap between West (1.93%) and South (2.11%) is small.", "The LFL base drops store-weeks that did not trade in both years. This removes Savonlinna (closed 25 January 2026), Pori's refit weeks in FY2025/26 and Kuopio's refit weeks (15 June to 26 July 2026) for the stores concerned, in both years. Regions with those stores are therefore compared on fewer store-weeks.", "The two stores opened in 2024 (Tampere Lamminpää 136, Lohja 137) are in the base, because both opened more than 364 days before 4 May 2026.", "Part-year, absolute net sales growth would differ from LFL growth, which handles the closed store, the refit stores and week 53 properly. No net sales growth figure that includes non-comparable stores is shown.", "The metric reading is my assumption and should be confirmed with Antti Rautiainen (FP&A) if he meant total net sales growth, gross margin or something else."]

Decision: 

## A009
Request: Quick one: how many customers do we have in Tampere?
Reading the result matches: Members whose home store is in Tampere (all enrolled members)
Assumptions: ["Interpreted 'customers' as all registered loyalty members, not just active members with purchases in the trailing 52 weeks", "Excluded web shop (store 900) and training store (999) from Tampere count as they are pseudo-locations, not physical stores in the city"]
Caveats: []

Decision: 

## A010
Request: Hi, I'd like the share of web sales that came from loyalty members, by period, for periods 9 to 11 last year. Thanks
Reading the result matches: b: returns the published number and names the problem in `caveats`
The data problem (for the criterion): For three weeks (9 February to 1 March 2026) more than half of the logged-in web orders lost their member key on the sales lines; the order records still carry it.
Assumptions: ["Last year interpreted as FY2025/26 (prior fiscal year to current FY2026/27 as of 15 October 2026)", "Periods 9-11 interpreted as fiscal periods 9, 10, 11 (fiscal weeks 35-47)", "Share calculated as percentage of web sales in each period", "Loyalty member defined as having a non-null member_key on the sales line"]
Caveats: ["Web sales are recognized on dispatch date, not order date; for home delivery this is the shipping date, for click-and-collect the ready-for-collection time", "Return lines are booked on the return date and reduce sales in their week; a sale-week cohort is not complete until ~5 weeks later", "A minimal amount of test articles (4 EUR across P9-P11) was excluded from the total", "Guest web orders (checkout without logging in) are counted as non-member sales"]

Decision: 

## A011
Request: Hi, which are our 10 biggest stores? Thanks.
Reading the result matches: Highest net sales over the last full fiscal year (FY2025/26)
Assumptions: ["'Biggest' is read as highest net sales, not floor area, because the request came without a measure and sales is the usual business reading. Floor area gives a different list, for example Helsinki Pitäjänmäki (8,381 sqm) first, then Turku Kupittaa, Kuopio, Oulu Kaakkuri, Vantaa Tammisto.", "Period is FY2025/26, the latest complete fiscal year. FY2026/27 is only partly loaded (period 6 is flagged as not fully loaded), so it is not used.", "Staff purchases are included as ordinary sales. Excluding them changes the amounts but not the top 10 or its order.", "Amounts are in EUR excluding VAT, shown as whole-year totals with no adjustment for opening dates or refits."]
Caveats: ["Tampere Lielahti had its sales lines loaded twice for 2025-09-15 to 2025-09-21 (836 duplicate rows, reloaded 2025-09-23). I removed the duplicates. Left in, they would add about 10,400 EUR and put Lielahti at 543,132 before returns, ahead of Kuopio, which is wrong. After the correction it is 8th, behind Kuopio.", "dim_store comments say format is Hyper, Standard or Express, but the data holds Large, Medium and Small. Format is not used in this answer.", "Stores were reassigned to new regions on 2025-04-28 (for example the Helsinki, Espoo, Vantaa and Kerava stores moved from South to Capital Region). Region is not used here, and joining on store_key would not split store totals across versions because I grouped by store_id.", "Pori was shut for a 5-week refit from 2025-09-08 to 2025-10-12, inside the year, but it is not near the top 10. Kuopio's refit (2026-06-15 to 2026-07-26) falls in FY2026/27 and does not affect these figures.", "Savonlinna closed on 2026-01-25, so its year is partial. It is ranked far outside the top 10.", "The amounts match rpt_daily_store_sales net_sales for every store in the period, so the dashboard table is consistent with this answer."]

Decision: 

## A012
Request: Can you rank the five store regions by how they are doing this year so far? Stores only, no web shop.
Reading the result matches: Rank by like-for-like growth against last year, year to date
Assumptions: ["'How they are doing this year so far' was read as growth against last year, ranked on the company growth measure, like-for-like net sales growth, rather than on the absolute size of sales", "'This year' is the current fiscal year FY2026/27 and 'so far' is year to date through the last completed fiscal week, week 22 (4 May to 4 October 2026, the warehouse load point); week 6 of period P6 is a part period but weeks are whole", "The comparison year is FY2025/26, weeks 1-22, lined up on fiscal week number", "Regions are as-is (current hierarchy), so Kouvola counts in South and the Capital Region stores count there in both years", "The answer is the ranking of the five physical-store regions only; Online is not a region here and no total row is given", "Ranking is by LFL growth percent, highest first"]
Caveats: ["Data correction: fact_sales_line holds 418 receipt lines for Tampere Lielahti (store 116, West) dated 15-21 September 2025 twice, each with a different sales_line_id and loaded on a different day. This double-counted about 10,390 EUR of last year's net sales in that store. I kept one row per receipt_id and line_no. After the fix, store-level net sales match rpt_daily_store_sales for every physical store in both years (differences under 1 EUR). The fix lowers West's LFL base and lifts its growth from 1.33% to 1.93%, but its rank (4th) does not change.", "The ranking is on LFL growth. On plain, unadjusted YTD net sales growth for all trading stores the order is North 3.80%, West 3.24%, Capital Region 2.71%, South 2.11%, East -11.61%. East's large fall is mostly the closure of Savonlinna (store 129, closed 25 January 2026), and West and Capital are affected by store openings and the Pori refit. Under LFL, those store-weeks drop out and East is -0.19%. East ranks last under both readings. If FP&A wants a ranking by absolute sales, or by unadjusted growth, say so and I will resend.", "The gaps in LFL growth are small between ranks 3 and 4 (South 2.11%, West 1.93%), so those two are close.", "LFL excludes stores that were in the base for only part of the range (Pori refit weeks 8 September to 12 October 2025 drop out of the comparison; Savonlinna drops out of this year's weeks after closure; Kuopio's refit from 15 June 2026 drops out of the weeks it was shut), so LFL regional figures cover fewer store-weeks than the full region.", "dim_store.region comment in the warehouse is out of date; the five regions come from the actual data (North, South, East, West, Capital Region).", "Store 999, ZZ Test articles and the web shop (store 900) are excluded as requested; rpt.v_daily_sales and rpt.v_weekly_store_sales (which miss web sales from 3 November 2025) were not used."]

Decision: 

## A013
Request: Hi, I'd like the share of web sales that came from loyalty members, by period, for periods 9 to 11 last year. Thanks
Reading the result matches: b: returns the published number and names the problem in `caveats`
The data problem (for the criterion): For three weeks (9 February to 1 March 2026) more than half of the logged-in web orders lost their member key on the sales lines; the order records still carry it.
Assumptions: ["Last year interpreted as FY2025/26, the fiscal year prior to FY2026/27 (current as of request date 2026-10-09)", "Guest web orders and non-member purchases treated as non-member sales", "Member linkage determined by presence of member_key on sales line"]
Caveats: ["Minor timezone boundary effect: 3-7 orders per period straddle the UTC/Helsinki day boundary and would be assigned to different periods if using UTC midnight instead of Helsinki midnight", "Returns are booked on their own return dates; this query shows sales net sales before returns on dispatch dates"]

Decision: 

## A014
Request: What were our best-selling products last period? Top 10 please.
Reading the result matches: Most units sold
Assumptions: ["Best-selling interpreted as highest units sold (volume ranking), not net sales value", "Last period means the most recent completed fiscal period", "Top 10 returns exactly 10 products", "Analysis includes all channels: physical stores, web (store 900), but excludes training store (999)"]
Caveats: ["Warehouse data loaded through 27 September 2026; request received 8 October 2026", "Returns are booked to their return date, reducing net sales on that date", "Web sales are recognised on dispatch date (Helsinki time), not order date", "Staff purchases (15% discount) are included in the volume figures", "Rank is by units sold; net sales values shown for reference only and may reflect different rankings if weighted by value"]

Decision: 

## A015
Request: Hi, which are our 10 biggest stores? Thanks.
Reading the result matches: Largest sales area (square metres)
Assumptions: ["The company has no definition of 'biggest'. I read it as physical size, meaning sales area in square metres, and not as sales. This is a judgment call: I could not ask in the queue.", "Rank ties would have been shown with the same rank; there are none in the top 10 (10th place 4,738 sqm, 11th place Kouvola 4,676 sqm).", "'Our stores' means the 45 physical stores currently trading, as of the warehouse load through 4 October 2026."]
Caveats: ["dim_store holds one row per store version, so a plain ranking on dim_store returns six stores twice (102, 104, 103, 114, 101, 105 each have a pre- and post-28 April 2025 version with the same sqm). I used the current version only, which removes the duplicates.", "If 'biggest' meant sales, the list is different. Net sales for FY2025/26 (stores only, after returns, store 999 and ZZ Test out, not reconciled to rpt_daily_store_sales) rank: 115 Tampere Hervanta 804,121; 102 Helsinki Pitäjänmäki 679,652; 131 Oulu Kaakkuri 555,975; 108 Lahti 543,957; 110 Turku Kupittaa 539,966; 104 Vantaa Tammisto 531,925; 116 Tampere Lielahti 517,285; 125 Kuopio 512,758; 117 Tampere Kaleva 474,881; 118 Nokia 415,259. Eight of the ten are the same stores as the size list. Tampere Kaleva (117) and Nokia (118) replace Espoo Lommila (103) and Lappeenranta (128). Say if you want that version, or net sales per trading day.", "Size is the sqm in the warehouse's current store record, and the warehouse does not date it. I did not check it against any other source."]

Decision: 

## A016
Request: Can you rank the five store regions by how they are doing this year so far? Stores only, no web shop.
Reading the result matches: Rank by like-for-like growth against last year, year to date
Assumptions: ["'How they are doing' was read as growth, not size, and ranked on LFL growth, the company's growth measure. LFL puts the regions on a like basis despite refits, an opening and a closure.", "'This year so far' is the current fiscal year FY2026/27 to date. That is fiscal weeks 1 to 22 (4 May to 4 October 2026), the last completed week, compared with weeks 1 to 22 of FY2025/26.", "Regions are as-is (today's region of each store), so Capital Region and the South/East membership of Kouvola are restated for last year as well. This is the company default; no as-was was requested.", "Ranked 1 = best, by LFL growth percent.", "Only the ranking and the growth figure are given, since the request asked only for a ranking."]
Caveats: ["Correction: 418 sales lines in store 116 Tampere Lielahti (West), 15 to 21 September 2025 (FY2025/26 week 21), were loaded twice by the ETL, with identical content and different sales_line_id. They overstated last year's West sales by about 10,390 EUR (roughly double that store's sales that week). I kept one row per receipt_id and line_no. After the fix the sales match rpt_daily_store_sales for all stores in all 22 weeks of both years. The duplicate only affects West's last-year base: unfixed, West would show 1.33% instead of 1.93%. The ranking does not change.", "East is the only region with negative LFL growth. Its LFL base excludes Savonlinna (closed 25 January 2026) and Kuopio's refit weeks (15 June to 26 July 2026). Raw year-on-year net sales for East, without LFL adjustment, are -11.6%, mostly from Savonlinna's loss. This is not a like-for-like figure.", "The LFL base leaves out some store-weeks. West loses Pori's weeks 20 to 22 (Pori's refit last year, 8 September to 12 October 2025), East loses Kuopio's refit weeks and Savonlinna, and the regional LFL totals are therefore on slightly different weeks from the full-year sales.", "A different reading of 'doing' gives a different order. Ranked on raw net sales YTD against last year with no LFL adjustment, West would be first (+3.24%, helped by Pori's closed weeks last year), then North (+3.80%) in a tie-like position by growth. Ranked on the size of net sales, the order is West, South, East, Capital Region, North. If Finance wanted size, or unadjusted growth, say so and I will rerun.", "LFL regional percentages come from slightly different store counts per region (North 6 stores, Capital Region 5, South 10, West 10, East 7 in the base), so the East and North figures sit on smaller bases. The gaps between South (2.11) and West (1.93) are small and I have not tested them for significance.", "Not used: rpt.v_daily_sales, rpt.v_weekly_store_sales and rpt_weekly_sales_by_region (known gaps or stale), and no deprecated or staging tables."]

Decision: 

## A017
Request: Hi, which are our 10 biggest stores? Thanks.
Reading the result matches: Largest sales area (square metres)
Assumptions: ["The wiki does not define 'biggest'. I read it as largest sales area in square metres (dim_store.sqm), the usual meaning for store operations. The request was not clarified in the queue, so this is my reading", "Ranking reflects the current store version; sqm is identical across all versions of the stores that changed region in April 2025", "Ties are broken by store_id (no ties arose in the top 10)"]
Caveats: ["Without the is_current filter the table would list stores 102 and 104 twice, because dim_store holds a South and a Capital Region version of each. I counted each store once, so the ranking is by distinct store_id", "If 'biggest' means sales rather than size, the answer is different. By net sales in FY2025/26 (after returns, web excluded, store 999 and ZZ Test excluded, EUR excl. VAT) the top 10 are: Tampere Hervanta 804,121; Helsinki Pitäjänmäki 679,652; Oulu Kaakkuri 555,975; Lahti 543,957; Turku Kupittaa 539,966; Vantaa Tammisto 531,925; Tampere Lielahti 517,285; Kuopio 512,758; Tampere Kaleva 474,881; Nokia 415,259. This list was not checked against rpt_daily_store_sales and is for comparison only. Tell me if you want that version delivered", "Kuopio (125) was closed for a refit from 15 June to 26 July 2026 but is a trading store and is included on size", "Sqm is the value held in the warehouse and I could not verify it against another source"]

Decision: 

## A018
Request: Can you rank the five store regions by how they are doing this year so far? Stores only, no web shop.
Reading the result matches: Rank by like-for-like growth against last year, year to date
Assumptions: ["'How they are doing' has no metric in the dictionary. I read it as year-on-year growth in net sales and ranked on like-for-like growth, so refits and the store closure do not distort the comparison. Say if you wanted plain net sales or raw growth instead", "'This year so far' is FY2026/27 YTD, weeks 1 to 22 (4 May to 4 October 2026), the last completed fiscal week in the warehouse. The comparison is FY2025/26 weeks 1 to 22 (28 April to 28 September 2025)", "Period 6 is only partly complete (week 22 of 5), but YTD runs through the last completed week, so week 22 is in", "'Last year' for the comparison is FY2025/26, as in past requests from May 2026 onwards", "Regions are as-is (current hierarchy), as in management reporting, since no as-was was asked for", "The two newer stores (Tampere Lamminpää, Lohja) are in the LFL base because both were open well over 364 days before 4 May 2026"]
Caveats: ["Correction: fact_sales_line holds 418 duplicated lines (same receipt_id and line_no, different sales_line_id), all from a reload in September 2025 (loaded 16 Sep and 23 Sep). I kept one copy of each. This affects last year's comparison base only. After deduplication the store-level totals match rpt_daily_store_sales for every store in both years", "Savonlinna (East, closed 25 January 2026) has no sales this year, so it is out of the like-for-like base. Kuopio (East) was shut for a refit from 15 June to 26 July 2026 (weeks 7 to 12 this year) and Pori (West) was shut from 8 September to 12 October 2025, so those weeks are dropped for each store in both years. Without this adjustment the unadjusted all-store growth would be East -11.61% and West +3.24%, which would misstate both regions. Growth for the other three regions is unchanged by the adjustment", "East is the only region below last year, at -0.19% like for like (959,424 against 961,257 EUR). It is close to flat, so its last place rests on a small gap", "The gap between third place South (2.11%) and fourth place West (1.93%) is small, and the ranking is on the period to 4 October only. Returns on recent sales will still arrive for up to 30 days, but returns are booked on their return date, so this does not change this figure", "Kemi (North) has no sales on Monday 31 August 2026 (about 300 EUR on a typical day), with nothing in the closure table to explain it. I left it as it stands because the amount is immaterial and rpt_daily_store_sales agrees", "Rank is by growth, not size: West has the highest net sales and North the lowest of the five regions on a like-for-like basis"]

Decision: 

## A019
Request: Hi, which are our 10 biggest stores? Thanks.
Reading the result matches: Largest sales area (square metres)
Assumptions: ["'Biggest' is read as largest sales area in square metres (dim_store.sqm). The dictionary does not define 'biggest', and the request names no period, so a size ranking that needs no date range was the least arbitrary reading.", "The list is of stores currently trading. Sales area is the same in every version of a store, so the ranking is not affected by which version is used."]
Caveats: ["dim_store has two rows for stores 102, 103, 104, 101, 105 and 114 because their region changed on 28 April 2025. Joining or listing without the is_current filter would show Helsinki Pitäjänmäki and Vantaa Tammisto twice in the top 10, so I counted each store once on its current version.", "If Leena meant biggest by sales rather than floor area, the answer is different. By net sales for FY2025/26 (stores only, store 999 and ZZ Test out, returns on their return date, web excluded) the top 10 is Tampere Hervanta, Helsinki Pitäjänmäki, Oulu Kaakkuri, Lahti, Turku Kupittaa, Vantaa Tammisto, Tampere Lielahti, Kuopio, Tampere Kaleva and Nokia. Eight of the ten are in both lists. Espoo Lommila (9th by area) and Lappeenranta (10th by area) are replaced by Tampere Kaleva and Nokia. I did not check that sales ranking against rpt_daily_store_sales, so treat it as indicative only. The sales ranking also depends on the period chosen.", "Rank 9 and 10 (Espoo Lommila 4827, Lappeenranta 4738) are Medium-format stores. There is a gap of about 1,900 sqm between rank 8 and rank 9, so the top 8 are all Large-format stores and the last two places go to the largest Medium stores."]

Decision: 

## A020
Request: Can I have the store league table for period 5 last year?
Reading the result matches: b: returns the published number and names the problem in `caveats`
The data problem (for the criterion): A till re-sync posted every receipt of Tampere Lielahti (116) for the week 15 to 21 September 2025 twice.
Assumptions: ["Request for 'period 5 last year' interpreted as FY2025/26 P5, the last complete period (fiscal weeks 18-21, 2025-08-25 to 2025-09-21) relative to the request date of 2026-10-08", "Pori (store 119) had 14 trading days because it was closed for refit from 2025-09-08 to 2025-10-12, overlapping with the last 14 days of the requested period"]
Caveats: ["Control total gap: query total EUR 950,787.15 vs rpt_daily_store_sales EUR 940,396.62 (difference EUR 10,390.53, concentrated at store 116 Tampere Lielahti). Root cause not identified within query limit. Discrepancy may indicate data issue or timing/methodology difference in control table calculation."]

Decision: 

## A021
Request: Hi, I'd like the share of web sales that came from loyalty members, by period, for periods 9 to 11 last year. Thanks
Reading the result matches: b: returns the published number and names the problem in `caveats`
The data problem (for the criterion): For three weeks (9 February to 1 March 2026) more than half of the logged-in web orders lost their member key on the sales lines; the order records still carry it.
Assumptions: ["Interpreted 'last year' as FY2025/26, the fiscal year prior to the current FY2026/27", "Web sales dated on dispatch_ts_utc converted to Helsinki business date", "Member presence determined by member_key IS NOT NULL on the sales line"]
Caveats: ["Web returns may arrive up to 30 days after sale, so the reported period may be incomplete for recent sales; however, periods 9-11 of FY2025/26 (ended 22 March 2026) are fully loaded in the warehouse", "The member_key on a sales line reflects the member version at that sale date; this query uses that version without requiring any specific membership tier or history"]

Decision: 

## A022
Request: Can you rank the five store regions by how they are doing this year so far? Stores only, no web shop.
Reading the result matches: Rank by net sales, year to date
Assumptions: ["'This year so far' interpreted as FY2026/27 weeks 1-22, the fiscal year to date through the last complete week in the warehouse", "'Stores only, no web shop' interpreted as physical stores with store_id < 900, excluding store 900 (web shop) and store 999 (training)", "Regions reported as-is (on the current region hierarchy), not as-was", "Regional ranking is by net sales (EUR), the standard performance metric"]
Caveats: ["The query compares against rpt_daily_store_sales control total at store scope only (store_id < 900). The web shop contributed an additional 1,110,040.88 EUR during this period, which is excluded per the request.", "Returns can arrive up to 30 days after a sale. Some returns from sales in week 22 (ending 4 October) may not yet have been booked.", "The data is loaded through 4 October 2026 (Sunday), so week 22 is complete.", "No refits closed any stores during this period (previous refits: Vantaa Tammisto July 2024, Pori September 2025, Kuopio June 2026); Savonlinna (store 129) had closed on 25 January 2026."]

Decision: 

## A023
Request: What were our best-selling products last period? Top 10 please.
Reading the result matches: Highest net sales
Assumptions: ["'Best-selling' was read as highest net sales value in EUR excluding VAT, the company's sales measure, not units sold; a ranking by units would give a different list (for example, high-volume low-price items such as Fixings & Fasteners Nordhem 594 sold 474 units but ranked 11th by value)", "'Products' means individual articles (sku), not subcategories, brands or categories", "'Last period' read as FY2026/27 P05 as of the request date 8 Oct 2026; P06 has only its first week loaded and is not complete", "Web sales included alongside the physical stores, as in the company total", "As-is reporting on the current product version; the category shown is the current one"]
Caveats: ["Store 999 and ZZ Test articles were excluded as the house rule requires; this removes training and test sales from the totals", "Web orders still processing or cancelled at the load date are not counted as sales, so a few late-dispatched orders from the period could still change figures slightly", "Returns are deducted on their return date, so a return in this period of an earlier sale lowers that product's figure here, and returns of this period's sales that arrive later will not yet be reflected", "Net sales are excluding VAT, after returns; no problem was found in the underlying data (no duplicate sales lines, no zero or negative lines in the period, period fully loaded, control total matches)", "Ranking has no ties in the top 10"]

Decision: 

## A024
Request: Can you rank the five store regions by how they are doing this year so far? Stores only, no web shop.
Reading the result matches: Rank by like-for-like growth against last year, year to date
Assumptions: ["The request does not name a measure. I read 'how they are doing this year so far' as performance against last year, so I ranked the regions by YTD like-for-like growth in net sales. That is the company's like-for-like growth measure, and it is not distorted by refits and closures.", "'This year so far' is read as FY2026/27 year to date, weeks 1 to 22 (4 May to 4 October 2026). Week 22 ended on 4 October, so it is complete, and the warehouse is loaded through that date. Period 6 is only partly loaded, but whole weeks are used, so that does not matter here.", "The comparison is with FY2025/26 weeks 1 to 22, lined up by fiscal week and not by calendar date. Week 53 of FY2025/26 is outside the range.", "Regions are as-is, meaning the current hierarchy applied to all history. As-was regions would change the Capital Region, South and East comparisons for last year.", "LFL base: all 39 physical stores that traded in the range were old enough, because every store opened more than 364 days before 4 May 2026, including Lohja (137) and Tampere Lamminpää (136). Open and close dates come from the current store version.", "The ranking is by growth, not by size. Absolute net sales in the table are the like-for-like store-weeks only, not the regions' full totals."]
Caveats: ["Data correction: fact_sales_line holds duplicate loads for store 116 (Tampere Lielahti, West) on 15 to 21 September 2025 (FY2025/26 weeks 21 to 22). 836 lines were reloaded on 23 September 2025 with new sales_line_ids. They are identical on receipt_id, line_no, store, product, quantity and amount, and they double-count 20,781.06 EUR of net sales in last year's comparison base. I kept the first load of each receipt_id and line_no pair and dropped the reload. After this correction every store matches rpt_daily_store_sales for weeks 1 to 22 of both years, within 0.50 EUR. Without it, West's last-year base would be overstated and its growth understated.", "Excluded from the LFL base: Kuopio (125, refit 15 June to 26 July 2026, weeks 7 to 12 dropped in both years), Pori (119, refit from 8 September 2025, weeks 20 to 22 dropped in both years), and Savonlinna (129, closed 25 January 2026, so no like-for-like weeks this year). The two refit stores stay in for their other weeks. The refit and closure exclusions mainly affect East (Kuopio and Savonlinna) and West (Pori).", "Ranking depends on the measure. On unadjusted YTD net sales growth the order would be North 3.8%, West 3.24%, Capital Region 2.71%, South 2.11%, East -11.61%. That order is misleading because the Savonlinna closure and the Kuopio refit remove East's sales, and West's growth includes Pori's refit. On absolute YTD net sales the order is West 1.82M, South 1.31M, East 0.96M, Capital Region 0.95M, North 0.73M. If Finance wants a size ranking, say so and I will resend.", "East is the only region with a decline (-0.19%, essentially flat). The gap between East's like-for-like growth and its unadjusted growth of -11.61% comes almost entirely from the Savonlinna closure and the Kuopio refit.", "Kemi (133, North) has no sales rows on Monday 31 August 2026, a trading day. The sales table, the control table and the staging table all show nothing. The other 38 stores traded that day and Kemi's average day is about 430 EUR, so the effect on North is about 0.1%. I could not verify whether the store was shut or the data is missing, and I made no correction.", "Regions rank closely at the bottom: West (1.93%) and South (2.11%) are 0.18 points apart.", "No store 999 or ZZ Test lines sit in the 39 stores' figures. The training store's 45,322.82 EUR of net sales since April 2025 is excluded, and it does not change any regional total."]

Decision: 

## A025
Request: What were our best-selling products last period? Top 10 please.
Reading the result matches: Highest net sales
Assumptions: ["'Last period' means the last completed fiscal period, FY2026/27 P05. P06 has only one week loaded, so it was not used.", "'Best-selling' was read as highest net sales value in EUR excluding VAT. The metric dictionary does not define 'best-selling', so I chose the company net-sales measure.", "Products are counted company-wide across physical stores and the web shop, because the request names no channel or region.", "Each product is one row by sku, named from its current product version."]
Caveats: ["'Best-selling' is not defined in the metric dictionary, and the ranking depends on the reading. Ranked by units sold instead, the list would be very different. For example, Fixings & Fasteners Nordhem 594 (sku 101763) is 2nd by units with 474 net units but only 11th by net sales. Interior Paint Norvik 298 is 1st on both measures only if units are read loosely: it is 1st by net sales and 24th by units. Please confirm whether you want a ranking by value or by units.", "Web sales in the list are recognised on the dispatch date, and web lines for cancelled or still-processing orders are left out. This follows the company web definition.", "Returns are deducted in the period they were processed, so a return in P05 for goods sold earlier lowers P05 net sales.", "The query total for P05 (1,109,546.52 EUR) matches the sum of rpt_daily_store_sales for the same days exactly, so no control-total gap.", "No duplicate sales or return lines were found in the period, and each top-10 sku has exactly one current product version."]

Decision: 

## A026
Request: What were our best-selling products last period? Top 10 please.
Reading the result matches: Highest net sales
Assumptions: ["Read 'last period' as the last completed fiscal period as of the request date 8 Oct 2026: FY2026/27 P05, because P06 has only its first week loaded", "Read 'best-selling' as highest net sales value (EUR excluding VAT, after returns), the company's sales measure, not units sold", "Read 'products' as individual articles (sku), not subcategories, brands or categories", "Scope is the whole company including web, with no region or channel filter", "Reported as-is (current product hierarchy and names)"]
Caveats: ["Ranking by net sales value gives a very different list from ranking by units sold: high-volume cheap items such as Fixings & Fasteners Nordhem 594 (474 units) and Cushions & Throws Tuulikki 338 (384 units) are not in the value top 10. If Commercial meant volume, the list needs re-running by units.", "Net sales are after returns, so the order differs from a before-returns ranking: Home Office Peltola 918 is 3rd at 7250.06 after returns (8412.86 before), and Outdoor Lighting Kultala 862 is 2nd at 7364.26 after returns (7858.20 before). Before returns, the Peltola product ranks above the Kultala one.", "Web orders still processing or cancelled have no dispatch and are excluded from web sales, per the company definition.", "Store 999 and ZZ Test articles were filtered out; this did not change the period total, which matches the rpt_daily_store_sales control total (1109546.52) exactly.", "Outdoor Lighting Kultala 862 has a Garden version in its history (the outdoor lighting subcategory moved to Electrical on 27 Oct 2025). The ranking is by sku, so this does not affect it, and the category is Electrical as-is.", "Returns are dated on the return date, so some returns in the period relate to sales made before 31 Aug 2026, and returns of this period's sales that arrive after 27 Sep are not yet in."]

Decision: 

## A027
Request: Can I have the store league table for period 5 last year?
Reading the result matches: b: returns the published number and names the problem in `caveats`
The data problem (for the criterion): A till re-sync posted every receipt of Tampere Lielahti (116) for the week 15 to 21 September 2025 twice.
Assumptions: ["Period 5 last year interpreted as FY2025/26 P5 (fiscal weeks 18-21, 2025-08-25 to 2025-09-21), the most recent completed P5 as of the request date 2026-10-08", "Trading day count includes all days dim_date.is_trading_day = true within the period when the store was open and not in a refit"]
Caveats: ["Store 119 (Pori) has only 14 trading days due to a refit closure from 8 September to 12 October 2025, which began during this period", "Control total check shows a discrepancy for store 116 (result 47,679.15 vs rpt_daily_store_sales 37,288.62, gap 10,390.53); the cause is not apparent and should be investigated with the Data & Analytics team"]

Decision: 

## A028
Request: Can I have the store league table for period 5 last year?
Reading the result matches: b: returns the published number and names the problem in `caveats`
The data problem (for the criterion): A till re-sync posted every receipt of Tampere Lielahti (116) for the week 15 to 21 September 2025 twice.
Assumptions: ["Period 5 last year: interpreted as P5 FY2025/26 (25 August to 21 September 2025), the most recent completed P5 relative to the request date of 8 October 2026", "Trading days: calendar days the store was open, excluding Finnish public holidays and days the store was shut by company rule (dim_date.is_trading_day = true)", "Store format: taken from the current store version (dim_store.is_current = true)"]
Caveats: ["Control total discrepancy: query sum of net_sales (950,787.15) exceeds rpt_daily_store_sales control total (940,396.62) by 10,390.53 (1.1%). The discrepancy is concentrated in store 116 (Tampere Lielahti), where the query calculates 47,679.15 but the control table shows 37,288.62. Root cause not identified within query limit; potential causes include data timing differences (UTC vs Helsinki day boundary for web orders or returns), or differences in how rpt_daily_store_sales is maintained. The league table uses the standard pattern from accepted requests REQ-D37 to REQ-D40.", "Store 119 (Pori): 14 trading days instead of 28, due to a refit closure from 8 September to 12 October 2025 (5 whole weeks); the store is ranked on the days it traded during this period"]

Decision: 

## A029
Request: Can you rank the five store regions by how they are doing this year so far? Stores only, no web shop.
Reading the result matches: Rank by like-for-like growth against last year, year to date
Assumptions: ["\"How they are doing\" is read as like-for-like sales growth, the company's performance measure for stores. Raw net sales mostly reflects region size, so I did not rank on it.", "\"This year so far\" is the current fiscal year FY2026/27 to date, through the last complete fiscal week, week 22 ending Sunday 4 October 2026. The warehouse is loaded through that date. It is compared with weeks 1 to 22 of FY2025/26.", "Regions are as-is (current hierarchy). The Capital Region is therefore compared with last year's South stores that were moved into it.", "Rank 1 is the highest LFL growth. The five regions are North, Capital Region, South, West and East; Online is not a physical region and is excluded with the web shop.", "I calculated LFL growth from the LFL template pattern. The accepted YTD LFL request (REQ-D09) ran the same way."]
Caveats: ["Data problem corrected: store 116 had every sales line loaded twice in FY2025/26 week 21 (15 to 21 September 2025). There were 836 rows for 418 distinct receipt and line numbers, each with its own sales_line_id and a different etl_loaded_at. This overstated last year's West net sales by 10,390.53 EUR and was the only mismatch against rpt_daily_store_sales across all stores and weeks 1 to 22 of both years. I kept one row per receipt_id and line_no (the earliest load). Without this fix West's LFL growth would read 1.33% instead of 1.93%. The ranking does not change, but West would sit further below South.", "East is the only region with negative LFL growth (-0.19%). Capital Region as-is includes Vantaa Tammisto and other stores that were in South last year, and the East as-is no longer includes Kouvola.", "The Pori and Kuopio refits and the Savonlinna closure take weeks out of the base for those stores. Kuopio's June to July 2026 refit shortens East or North store-weeks depending on its region. The compared weeks are the same in both years for each store.", "The regional gaps between South, West and Capital Region are small (about 1 percentage point). I did not test whether they are significant.", "rpt.v_daily_sales and rpt.v_weekly_store_sales were not used (they drop web sales from 3 November 2025). The web shop is excluded from this answer anyway.", "Only 6 skill loads were available, so I did not open the query-check skill. I ran the control-total check by hand with SQL against rpt_daily_store_sales. I did not run the duplicate check on any other table or period beyond that comparison."]

Decision: 

## A030
Request: Hi, which are our 10 biggest stores? Thanks.
Reading the result matches: Largest sales area (square metres)
Assumptions: ["'Biggest' is not defined in the company metric dictionary. I read it as physical size, meaning sales area in square metres, since the request comes from Store operations. The rule is to ask when a metric is undefined, but I could not ask, so this is my reading.", "Only stores still trading are ranked. Savonlinna is closed, and at 1,741 sqm it would not be in the top 10 in any case.", "sqm is the same in every version of every store, so using the current version rather than the version at some date changes nothing."]
Caveats: ["If 'biggest' means sales rather than floor area, the list differs. Over the last full fiscal year (28 Apr 2025 to 26 Apr 2026, net sales after returns, excluding VAT, 999 and ZZ Test), the top 8 are the same eight Large stores, but in a different order: Tampere Hervanta, Helsinki Pitäjänmäki, Oulu Kaakkuri, Lahti, Turku Kupittaa, Vantaa Tammisto, Tampere Lielahti, Kuopio. Places 9 and 10 are Tampere Kaleva and Nokia, not Espoo Lommila and Lappeenranta. I can send that ranking if it is what you meant.", "The size gap is large: the eight Large stores run from 6,705 to 8,381 sqm, and places 9 and 10 are Medium stores at 4,827 and 4,738 sqm.", "Sales area comes from dim_store.sqm, which is a current-state figure with no history. It does not show refit-related changes in floor area, if there were any."]

Decision: 

## A031
Request: Hi, which are our 10 biggest stores? Thanks.
Reading the result matches: Highest net sales over the last full fiscal year (FY2025/26)
Assumptions: ["Read 'biggest' as highest net sales in euros, not floor area (sqm) or receipt count", "Used the last complete fiscal year, FY2025/26, as the period, because the request names none; FY2026/27 is still open (P06 not fully loaded)", "Net sales are excluding VAT and net of returns, the company's usual store sales measure", "Click-and-collect and web sales are credited to the web shop (store 900), not to the collection store, so they are not in these store figures"]
Caveats: ["Correction: fact_sales_line holds 418 duplicate lines (209 receipt-line pairs, 20,781.06 EUR net, all store sales from September 2025, reloaded on 2025-09-23 under new sales_line_id values). I kept one row per receipt_id and line_no. Without this fix, Tampere Lielahti (116) is overstated by about 10,390 EUR and would show as 543,132 gross against Kuopio's 537,991, which would swap their 7th and 8th places.", "Correction: store_key changes between versions (five Helsinki-area stores changed region in April 2025, and Kouvola moved from East to South), so I grouped by store_id and not store_key.", "The 53-week year matters. FY2025/26 has 53 weeks (P12 runs 6 weeks), so these totals are about 2% higher than a 52-week year would give. The ranking is not affected.", "Ranking depends on the period. Nine of the top 10 are the same in FY2024/25. In that year Pori (119) was 10th and Nokia (118) 13th. In FY2026/27 to date Kuopio falls to 14th during its June to July 2026 refit.", "Ranking by floor area would give a different list. Tampere Kaleva and Nokia (medium stores) would drop out and Espoo Lommila (4,827 sqm) and Kouvola (4,676 sqm) would come in.", "Pori (119) had a 5-week refit closure in Sept to Oct 2025 and Kuopio (125) closed for 6 weeks from June 2026 (in FY2026/27, so it does not affect these figures). Savonlinna (129) closed on 2026-01-25, so its figures are partial. None of these is near the top 10 cut-off in FY2025/26.", "dim_store.format holds Small, Medium and Large, not the Hyper, Standard and Express named in the column comment, so I did not use format.", "The warehouse has backup, staging and temporary tables (bak_*, stg_*, tmp_*, *_old) that I did not use. The report table rpt_daily_store_sales agrees with my deduplicated figures for every store in this period."]

Decision: 

## A032
Request: Quick one: how many customers do we have in Tampere?
Reading the result matches: Members whose home store is in Tampere (all enrolled members)
Assumptions: ["Interpreted 'customers in Tampere' as members whose home_store is in Tampere, not customers who have visited Tampere stores", "Counted only current/active members, excluding lapsed members (is_current = false)"]
Caveats: ["This count includes members whose home store is Tampere but who may not have made recent purchases (3,244 inactive members with Tampere home store exist in the historical data)", "If the requester meant customers who have actively shopped in Tampere, the count would be 11,967 (distinct members with any transaction at Tampere stores)", "Web shop sign-ups (store_id 900) are excluded; if online-Tampere customers are wanted, that would need to be evaluated separately"]

Decision: 

## A033
Request: Need the average stock value for the West region in period 11 last year, split by category.
Reading the result matches: b: returns the published number and names the problem in `caveats`
The data problem (for the criterion): The West region's stock snapshot for the week ending 8 March 2026 was loaded twice, so every West store-article row for that week exists twice.
Assumptions: ["Last year interpreted as FY2025/26 (fiscal year 28 April 2025 to 3 May 2026)", "Period 11 means fiscal period 11 (fiscal weeks 44-47, 23 February to 22 March 2026)", "Average stock value means average of weekly closing values across the four weeks in the period"]
Caveats: []

Decision: 

## A034
Request: What were the whole company's net sales last month?
Reading the result matches: Fiscal period 5 (31 August to 27 September)
Assumptions: ["The company has no 'month' in its metric dictionary, so I read 'last month' as the last completed fiscal period. The request arrived on 9 October 2026, and the last complete period is FY2026/27 P05, 31 August to 27 September 2026 (4 weeks).", "Net sales are excluding VAT and after returns, which is the company default. Mika did not ask for gross or before-returns.", "'Whole company' means all physical stores plus the web shop, reported as one total with no breakdown.", "Sales are by Helsinki business date. Web orders that were still processing or cancelled have no dispatch and no sales lines, so they are not in net sales."]
Caveats: ["If you meant calendar September 2026 (1 to 30 September), the figure is 1179035.98. It also agrees with rpt_daily_store_sales. P05 is the figure on the company calendar.", "P05 ends on 27 September, so 28 to 30 September fall in period 6, which is only partly loaded (to 4 October) and is not shown.", "Test data was excluded: store 999 and ZZ Test lines in P05 came to about 2,697 EUR of sales (2,606.27 from store 999 alone, 84.65 from both, 6.00 from a ZZ Test line outside store 999). This lowers the total slightly.", "The total agrees with rpt_daily_store_sales for P05 to the cent (1109546.52). The split is stores 932309.19 and web 177237.33, after returns of 69980.90 (stores 51593.92, web 18386.98). I did not compare store by store.", "I did not use rpt.v_daily_sales, which leaves out web sales from 3 November 2025, or channel_code, which is empty after the web migration. Web was identified by store_id 900.", "Sales line and return line IDs were unique in the range, so no duplicate rows needed correcting."]

Decision: 

## A035
Request: What were our best-selling products last period? Top 10 please.
Reading the result matches: Highest net sales
Assumptions: ["'Last period' read as FY2026/27 P05 (31 Aug to 27 Sep 2026), the last completed fiscal period at the request date of 8 Oct 2026. P06 is only partly loaded and was not used.", "'Best-selling' read as highest net sales in EUR excluding VAT on the company definition, because the metric dictionary has no best-seller measure. It was not read as units sold.", "A product is one sku, across all its versions. The name and category shown are from the current version (as-is). Only the paint, power tools, furniture and smart home articles are unaffected by the category changes, and outdoor lighting (sku 100927) is shown under its current Electrical category.", "All channels are included: physical stores and the web shop.", "Net sales is shown to the cent, in EUR excluding VAT."]
Caveats: ["Ranking by units sold would give a very different top 10. For example, Fixings & Fasteners Nordhem 594 (sku 101763) is 2nd by units (474) but 11th by net sales, and Interior Paint Norvik 298 is 24th by units but 1st by net sales. If Pekka means units, the query needs re-running with units as the ranking measure.", "Corrections applied: store 999 (training store) and ZZ Test articles were removed, and web order lines not delivered or collected (processing or cancelled) were left out. In this period the web exclusion had no effect on the totals, and store 999 had no sales in the control table for the period.", "Reconciliation: before the ranking, the same lines summed over all articles to 1,179,527.42 in sales and 69,980.90 in returns, so net sales of 1,109,546.52. That equals the rpt_daily_store_sales control total for 31 Aug to 27 Sep 2026 exactly.", "Returns are deducted on their return date, so a product's figure can include refunds on goods sold before the period and exclude refunds that arrive later for goods sold in it.", "Sales lines have no duplicate keys in the range, and the period is fully loaded (warehouse loaded through 4 Oct 2026).", "The gaps between ranks 1 to 10 are small in places. Ranks 4 and 5 differ by about 26 EUR, and 7 and 8 by about 133 EUR."]

Decision: 

## A036
Request: What were our best-selling products last period? Top 10 please.
Reading the result matches: Most units sold
Assumptions: ["Interpreted 'best-selling' as highest units sold by volume (standard retail metric for top products by volume)"]
Caveats: ["Training store (999) and test articles (category ZZ Test) excluded from totals as per standard reporting rules", "Net sales figures include staff purchases (15% discount) but otherwise follow company definition", "Quantity figures represent gross sales before returns"]

Decision: 

## A037
Request: Hi, I'd like the share of web sales that came from loyalty members, by period, for periods 9 to 11 last year. Thanks
Reading the result matches: b: returns the published number and names the problem in `caveats`
The data problem (for the criterion): For three weeks (9 February to 1 March 2026) more than half of the logged-in web orders lost their member key on the sales lines; the order records still carry it.
Assumptions: ["Last year = FY2025/26 (fiscal year preceding FY2026/27, current as of request date 2026-10-15)", "Periods 9-11 = fiscal periods 9, 10, 11 of FY2025/26 (22 December 2025 to 22 March 2026)", "Share = sum of member sales / sum of all web sales, both measured before returns", "Guest web orders (no member_key) count as non-member sales"]
Caveats: ["Calculated on sales before returns; returns booked in these periods are not subtracted from the totals", "Test articles (category ZZ Test) and store 999 filtered out; web shop is store 900", "Web sales dated by dispatch date (Helsinki time). Cancelled orders excluded.", "Member status determined by member_key on the sales line at the time of dispatch"]

Decision: 

## A038
Request: Can I have the store league table for period 5 last year?
Reading the result matches: b: returns the published number and names the problem in `caveats`
The data problem (for the criterion): A till re-sync posted every receipt of Tampere Lielahti (116) for the week 15 to 21 September 2025 twice.
Assumptions: ["Period 5 last year interpreted as FY2025/26 P05 (fiscal weeks 18-21, 2025-08-25 to 2025-09-21)", "Trading days determined from is_trading_day flag in dim_date (public holidays and company closures excluded)", "Store versions from dim_store current versions as of the reporting date"]
Caveats: ["Control total discrepancy: Store 116 (Tampere Lielahti) shows a gap of EUR 10,390.53 between the fact tables (EUR 47,679.15) and the rpt_daily_store_sales control total (EUR 37,288.62). This unexplained difference suggests a possible data quality issue with the control table for this period and store, and should be investigated by the Data & Analytics team. The league table methodology is correct and matches the validated template pattern."]

Decision: 

## A039
Request: Hi, which are our 10 biggest stores? Thanks.
Reading the result matches: Highest net sales over the last full fiscal year (FY2025/26)
Assumptions: ["Read 'biggest' as highest net sales, not floor area", "Used the latest complete fiscal year, FY2025/26, because FY2026/27 is only partly loaded (period 6 is not fully loaded)", "Staff purchases are kept in net sales as they are real sales; excluding them does not change the top 10", "Click-and-collect and web lines are not attributed to stores; only lines booked to a store count"]
Caveats: ["Correction: Tampere Lielahti (116) had 418 sales lines loaded twice around 16-23 Sep 2025, about 10,391 EUR of double-counted sales. I removed the duplicates (one row kept per receipt_id and line_no), which matches rpt_daily_store_sales. This moves Lielahti from 543,132 to 506,895 EUR net and from 7th to 8th, behind Kuopio. The top 10 set is unchanged.", "If 'biggest' means floor area, the answer differs: the largest by sqm are Helsinki Pitäjänmäki (8,381), Vantaa Tammisto, Kuopio, Turku Kupittaa and Lahti, with Oulu Kaakkuri, Tampere Lielahti and Tampere Hervanta next.", "Pori (119) was closed for a refit for 5 weeks from 8 Sep 2025 and Savonlinna (129) closed on 25 Jan 2026, so their FY2025/26 sales are partial. Neither is in the top 10. Kuopio has a refit in June-July 2026 (FY2026/27), which drops it to 14th in the part-year FY2026/27 so far.", "Rank is stable across years for the top 2 (Hervanta, Pitäjänmäki). Positions 3 to 10 shift by a place or two between FY2024/25, FY2025/26 and the year to date, as the gaps are small, for example Kuopio and Lielahti are 6k EUR apart.", "Old store regions were restated on 28 Apr 2025 (South to Capital Region); this does not affect store-level totals because grouping is by store_id.", "Figures are in EUR excluding VAT and cover this fiscal year only, not all-time sales."]

Decision: 

## A040
Request: Quick one: how many customers do we have in Tampere?
Reading the result matches: Members whose home store is in Tampere (all enrolled members)
Assumptions: ["\"Customers in Tampere\" refers to loyalty program members with Tampere as their home store (home_store_id)", "Home store represents the member's primary location and store affiliation", "Only current member records are counted; historical versions excluded"]
Caveats: ["Count includes loyalty members only; non-loyalty retail customers are not tracked in dim_member and are excluded", "Home store is set at membership sign-up and may not reflect where members currently shop", "Online sign-ups (store_id 900) are not included, so members registering online are not counted", "Does not include inactive members or members who may have churned"]

Decision: 

## A041
Request: What were the whole company's net sales last month?
Reading the result matches: Calendar September 2026
Assumptions: ["Read 'last month' as calendar September 2026 (1 to 30 September), since the request was received on 9 October 2026 and the metric dictionary does not define 'last month'", "Read 'whole company' as all physical stores plus the web shop, shown as one total as asked, with no breakdown", "Figures are in EUR excluding VAT, the company definition of net sales", "As-is versus as-was does not matter here because the answer is a single company total with no region or category split"]
Caveats: ["'Last month' is not defined in the metric dictionary. Calendar September 2026 gives 1,179,035.98 EUR (physical stores 988,592.16 plus web 190,443.82). If Store operations meant the last completed fiscal period instead (FY2026/27 P05, 31 Aug to 27 Sep 2026), the figure is 1,109,546.52 EUR.", "Training store 999 and ZZ Test articles were excluded as the company rules require. This removed a small amount from the 31 Aug to 30 Sep window (about 3,179 EUR from store 999 and about 133 EUR of test-article sales, with some overlap between the two).", "Web orders that were cancelled or still processing were excluded because they have no dispatch date. The generic net_lines template would fall back to the order date for them and count them, so I filtered them out.", "My own query's totals match rpt_daily_store_sales exactly for 1 to 30 September 2026: physical stores 988,592.16 and web 190,443.82. No duplicate sales lines were found (63,450 lines, all keys unique) and sale_date agrees with the Helsinki date from the UTC timestamp for every line.", "I did not use rpt.v_daily_sales or rpt.v_weekly_store_sales, because they leave out web sales from 3 November 2025.", "The warehouse is loaded through 4 October 2026, so September is fully loaded. Returns of September sales that arrive later will reduce October's net sales, not September's."]

Decision: 
