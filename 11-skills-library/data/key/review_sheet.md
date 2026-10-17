# Review sheet for the test-request answer key (case 11)

One entry per test request: what the reference answer counts and leaves out, why, the trap, and the number. No SQL. Check each one by common sense: is this really what the question means at Tuomimetsä, and is the number believable?

How to read it

- The warehouse is synthetic and about a twentieth of the in-world size, so amounts are in the tens or hundreds of thousands of euros for a period, not millions.
- 'Today' is the first week of October 2026. The data runs to Sunday 4 October 2026 (fiscal week 22 of FY2026/27). 'Last period' is therefore P5 (31 August to 27 September 2026), 'last year' is FY2025/26 and 'this year' is FY2026/27, as the dictionary says.
- 'The trap' lines describe the plausible wrong answers the marker will look for, and how far each is off.
- The like-for-like requests come first, because that is where a quiet mistake in the key is most likely. Then the rest, by pattern.
- Three independent reviewer agents re-checked all 60 reference answers on 15 October 2026. None broke a documented definition. Where they found a second defensible reading, the key now also accepts it (shown under the reference answer as 'other readings' or as an accepted reading): REQ-T08, the 364-day rule for a new store applied at the start of each fiscal period, not of the whole quarter (Lohja is then in for P8 and P9); REQ-T14, 'biggest' as net sales over the last full fiscal year, or over the trailing 52 weeks; REQ-T20, 'doing well' as year-to-date growth against last year, total or like-for-like; REQ-T06 and REQ-T23, stores only (no Web row), or web sales placed in the cohort by dispatch date; REQ-T11 and REQ-T17, the whole Outdoor Lighting subcategory counted in Electrical, including the five delisted articles; REQ-T28, the four weeks ending at the stock week in the denominator; REQ-T43, units with web sales dated by dispatch date, or units in the stores only; REQ-T26 and REQ-T58, the table ranked by total net sales instead of net sales per trading day. Every wrong answer below still differs from all of these.

Trap classes on this set (a request can carry two; targets in brackets): company definition 12 (14), fiscal calendar 11 (12), history of regions or categories 6 (8), web-platform migration 4 (5), time zone 3 (4), exclusions 5 (6), double counting in joins 5 (5), stock (never added across weeks) 3 (3), VAT 4 (4), genuinely ambiguous request 5 (5), request overrides a company default 4 (4), undocumented data problem 4 (4), clean (no trap) 14 (14).

---

### REQ-T01: like-for-like growth (company definition, fiscal calendar)

Store operations, Leena Vuorinen, received 5 October 2026. Same question as REQ-T34 in different words; the answer is the same.

> How did the stores do like for like in period 4 this year against last year?

**The reference answer counts:** Like-for-like growth for period 4 of this year (weeks 14 to 17, 3 to 30 August 2026) against fiscal weeks 14 to 17 of last year (28 July to 24 August 2025). Kuopio is back from its refit and counts; Savonlinna (closed) does not.

**It leaves out:** The web shop, store 999, week 53, the closed store and any store-week in a refit.

**Where this is written down:** Metric dictionary, 'Like-for-like (LFL)'; Team notes, 'LFL edge cases'; Data quality register, 'Store openings' and 'Refit closures'; Metric dictionary, 'Fiscal calendar' (compare week to week).

**Reference result:**

| net sales (year asked about) | net sales (year before) | lfl growth pct |
|---|---|---|
| 1,010,478.52 | 1,010,743.32 | -0.03 % |

**The trap, and what a plausible wrong answer does:**

- Takes last year's comparator as the same calendar dates (3 to 30 August 2025) instead of the same fiscal weeks, which starts it six days late. The result: lfl growth pct comes out as 1.67 % instead of -0.03 %.
- Reports the growth of total company net sales, web included, which is not like-for-like: the web shop grows much faster than the stores. The result: net sales (year asked about) comes out as 1,195,443.99 instead of 1,010,478.52.

---

### REQ-T08: like-for-like growth (company definition, history of regions or categories)

Finance (FP&A), Marjatta Salonen, received 5 October 2026.

> Like-for-like growth by region for Q3 last year, please.

**The reference answer counts:** Like-for-like growth by region for Q3 of last year (periods 7 to 9, weeks 27 to 39) against Q3 the year before, using today's regions for both years. Lohja (opened 4 November 2024) has not been open 364 days by the start of the period (27 October 2025), so it is not in the base; Savonlinna counts for its weeks of trading.

**It leaves out:** The web shop (so no Online line), store 999, week 53 and any store-week not trading in both years.

**Where this is written down:** Metric dictionary, 'Like-for-like (LFL)'; Team notes, 'LFL edge cases'; Data quality register, 'Store openings' and 'Refit closures'; Metric dictionary, 'Hierarchies and stores' (as-is regions).

**Reference result:**

| region | net sales (year asked about) | net sales (year before) | lfl growth pct |
|---|---|---|---|
| Capital Region | 527,026.01 | 525,151.30 | 0.36 % |
| East | 597,583.01 | 588,069.69 | 1.62 % |
| North | 413,618.24 | 387,519.62 | 6.73 % |
| South | 686,946.66 | 686,791.06 | 0.02 % |
| West | 997,953.07 | 952,479.50 | 4.77 % |

Other readings of the request are also accepted without the answer naming them. Each gives a different table:

*the 364-day rule applied to the first day of each fiscal period (Lohja counts from P8)*

| region | net sales (year asked about) | net sales (year before) | lfl growth pct |
|---|---|---|---|
| Capital Region | 527,026.01 | 525,151.30 | 0.36 % |
| East | 597,583.01 | 588,069.69 | 1.62 % |
| North | 413,618.24 | 387,519.62 | 6.73 % |
| South | 715,066.55 | 703,852.92 | 1.59 % |
| West | 997,953.07 | 952,479.50 | 4.77 % |

**The trap, and what a plausible wrong answer does:**

- Uses each year's own regions. The Capital Region did not exist the year before, so there is nothing to compare it with, and South and East are different sets of stores in the two years. The result: South, net sales (year before) comes out as 1,140,692.73 instead of 686,791.06.
- Compares every physical store with no LFL rules, so Lohja (open less than a year) and Savonlinna's partial year are in the base. The result: South, net sales (year asked about) comes out as 729,021.20 instead of 686,946.66.

---

### REQ-T34: like-for-like growth (company definition, fiscal calendar)

Finance (FP&A), Antti Rautiainen, received 7 October 2026. Same question as REQ-T01 in different words; the answer is the same.

> Like-for-like growth for period 4 this year.

**The reference answer counts:** Like-for-like growth for period 4 of this year (weeks 14 to 17, 3 to 30 August 2026) against fiscal weeks 14 to 17 of last year (28 July to 24 August 2025). Kuopio is back from its refit and counts; Savonlinna (closed) does not.

**It leaves out:** The web shop, store 999, week 53, the closed store and any store-week in a refit.

**Where this is written down:** Metric dictionary, 'Like-for-like (LFL)'; Team notes, 'LFL edge cases'; Data quality register, 'Store openings' and 'Refit closures'; Metric dictionary, 'Fiscal calendar' (compare week to week).

**Reference result:**

| net sales (year asked about) | net sales (year before) | lfl growth pct |
|---|---|---|
| 1,010,478.52 | 1,010,743.32 | -0.03 % |

**The trap, and what a plausible wrong answer does:**

- Takes last year's comparator as the same calendar dates (3 to 30 August 2025) instead of the same fiscal weeks, which starts it six days late. The result: lfl growth pct comes out as 1.67 % instead of -0.03 %.
- Reports the growth of total company net sales, web included, which is not like-for-like: the web shop grows much faster than the stores. The result: net sales (year asked about) comes out as 1,195,443.99 instead of 1,010,478.52.

---

### REQ-T53: like-for-like growth (company definition, fiscal calendar)

Finance (FP&A), Marjatta Salonen, received 9 October 2026.

> Like-for-like growth for period 1 this year, please.

**The reference answer counts:** Like-for-like net sales growth for period 1 of this year (weeks 1 to 4) against the same fiscal weeks last year, in the stores that count. A store-week counts only if the store traded that week in both years and the store had been open at least 364 days before the period began. Savonlinna (closed in January 2026) drops out, so it does not drag this year down against last year.

**It leaves out:** The web shop, store 999, week 53, the closed store and any store-week in a refit.

**Where this is written down:** Metric dictionary, 'Like-for-like (LFL)'; Team notes, 'LFL edge cases'; Data quality register, 'Store openings' and 'Refit closures'.

**Reference result:**

| net sales (year asked about) | net sales (year before) | lfl growth pct |
|---|---|---|
| 1,177,925.94 | 1,103,969.88 | 6.70 % |

**The trap, and what a plausible wrong answer does:**

- Compares all physical stores with no LFL rules, so Savonlinna's sales last year are in the base but it sold nothing this year. The result: lfl growth pct comes out as 5.55 % instead of 6.70 %.
- Takes last year's comparator as the same calendar dates (4 to 31 May 2025) instead of the same fiscal weeks, which starts it six days late. The result: lfl growth pct comes out as 1.47 % instead of 6.70 %.

---

### REQ-T05: sales by region or week (fiscal calendar)

Store operations, Leena Vuorinen, received 5 October 2026. Same question as REQ-T33 in different words; the answer is the same.

> Hi, could you show how total company sales did in each of the four weeks of period 2 this year compared with last year? Growth too, please.

**The reference answer counts:** Total company net sales (stores and web, after returns) for each of the four weeks of period 2 this year (weeks 5 to 8), against the same four fiscal weeks last year.

**It leaves out:** Store 999 and test articles.

**Where this is written down:** Metric dictionary, 'Fiscal calendar' (compare by the same fiscal week, not the same dates) and 'Net sales'.

**Reference result:**

| fiscal week | net sales (year asked about) | net sales (year before) | growth pct |
|---|---|---|---|
| 5 | 341,054.61 | 330,868.04 | 3.08 % |
| 6 | 362,249.20 | 329,334.78 | 9.99 % |
| 7 | 220,623.76 | 325,472.70 | -32.21 % |
| 8 | 370,720.07 | 210,207.18 | 76.36 % |

**The trap, and what a plausible wrong answer does:**

- Compares with the same calendar dates a year earlier (1 to 28 June 2025). Last year's fiscal weeks started six days earlier, so the comparison is shifted by almost a week. The result: 8, growth pct comes out as 3.48 % instead of 76.36 %.

---

### REQ-T19: sales by region or week (fiscal calendar, history of regions or categories)

Finance (FP&A), Antti Rautiainen, received 6 October 2026.

> Net sales by region for Q3 last year against Q3 the year before, with the web shop as its own line. For each region I need last year's figure, the earlier year's figure and the growth percentage.

**The reference answer counts:** Net sales after returns (returns taken off on the day they were booked), web on its dispatch date. Q3 is periods 7 to 9, weeks 27 to 39, in both years. Regions are today's regions applied to both years, with the web shop as its own line, Online.

**It leaves out:** Store 999 (the training store) and test articles. Week 53 does not fall in Q3.

**Where this is written down:** Metric dictionary, 'Net sales', 'Fiscal calendar' and 'Hierarchies and stores'; Data quality register, 'History that changes the answer'.

**Reference result:**

| region | net sales (year asked about) | net sales (year before) | growth pct |
|---|---|---|---|
| Capital Region | 527,026.01 | 525,151.30 | 0.36 % |
| East | 597,583.01 | 588,069.69 | 1.62 % |
| North | 413,618.24 | 387,519.62 | 6.73 % |
| Online | 580,450.93 | 447,645.43 | 29.67 % |
| South | 729,021.20 | 710,020.17 | 2.68 % |
| West | 997,953.07 | 952,479.50 | 4.77 % |

**The trap, and what a plausible wrong answer does:**

- Uses each store's region as it was on the day of the sale. Last year's Capital Region stores were still in South the year before, so the two years cannot be compared and the Capital Region has no comparator. The result: South, net sales (year before) comes out as 1,163,921.84 instead of 710,020.17.
- Reads Q3 as July to September instead of the fiscal Q3 (late October to late January). The result: Capital Region, growth pct comes out as 17.43 % instead of 0.36 %.

---

### REQ-T20: sales by region or week (genuinely ambiguous request, fiscal calendar)

Finance (FP&A), Antti Rautiainen, received 6 October 2026.

> Can you rank the five store regions by how they are doing this year so far? Stores only, no web shop.

**The reference answer counts:** The five store regions (Capital Region, South, West, East, North) ranked on the current fiscal year to date, weeks 1 to 22. Reading 1 ranks by net sales; reading 2 by gross margin percentage; reading 3 by net sales growth against the same fiscal weeks last year; reading 4 by like-for-like growth. The request does not say which; any of the four is accepted if the answer says which it used. Readings 3 and 4 use last year's week 21, in which Tampere Lielahti's receipts were posted twice in the published data, so they have two accepted outcomes: the corrected figures, or the published figures with the duplicates named in the caveats.

**It leaves out:** The web shop (not a region), store 999 and test articles. Year to date runs to the last completed week, week 22 (ending 4 October 2026).

**Where this is written down:** Metric dictionary, 'Net sales', 'Gross margin' and 'Fiscal calendar' (YTD).

**Accepted readings** (any one counts if the answer says which it used):

*Rank by net sales, year to date*

| region | metric value |
|---|---|
| West | 1,815,139.47 |
| South | 1,309,213.51 |
| East | 959,424.31 |
| Capital Region | 948,667.50 |
| North | 730,386.24 |

*Rank by gross margin percentage, year to date*

| region | metric value |
|---|---|
| North | 40.40 % |
| South | 40.35 % |
| West | 40.21 % |
| Capital Region | 40.20 % |
| East | 39.89 % |

*Rank by net sales growth against last year, year to date (week for week, weeks 1 to 22 of both years)*

| region | metric value |
|---|---|
| North | 3.80 % |
| West | 3.24 % |
| Capital Region | 2.71 % |
| South | 2.11 % |
| East | -11.61 % |

The published figures for this reading are also accepted if the caveats name the duplicated receipts of Tampere Lielahti in September 2025 (that store's week was posted twice):

| region | metric value |
|---|---|
| North | 3.80 % |
| Capital Region | 2.71 % |
| West | 2.63 % |
| South | 2.11 % |
| East | -11.61 % |

*Rank by like-for-like growth against last year, year to date*

| region | metric value |
|---|---|
| North | 3.80 % |
| Capital Region | 2.71 % |
| South | 2.11 % |
| West | 1.93 % |
| East | -0.19 % |

The published figures for this reading are also accepted if the caveats name the duplicated receipts of Tampere Lielahti in September 2025 (that store's week was posted twice):

| region | metric value |
|---|---|
| North | 3.80 % |
| Capital Region | 2.71 % |
| South | 2.11 % |
| West | 1.33 % |
| East | -0.19 % |

**The trap, and what a plausible wrong answer does:**

- Stops the year to date at the end of period 5 (week 21) instead of the last completed week (week 22). The result: East, metric value comes out as 917,435.89 instead of 959,424.31.

---

### REQ-T27: sales by region or week (request overrides a company default, VAT)

Finance (FP&A), Marjatta Salonen, received 7 October 2026.

> For the VAT filing I need gross sales including VAT, before returns, by region for August and September 2024, one column for each month. Regions as they were at the time, as in the old reports.

**The reference answer counts:** Gross sales including VAT, summed from the gross amount on each sales line (each line at its own VAT rate), before returns, for August and September 2024 as two columns. Regions are as they were at the time (four regions plus Online), because the request asks for that.

**It leaves out:** Store 999 and test articles. Returns are not taken off (the request asks for gross sales). Web on its dispatch date.

**Where this is written down:** Team notes, 'explicitly asks' rule (follow the request and say so); Metric dictionary, 'Net sales' (including-VAT figures come from gross_amount) and 'Hierarchies and stores' (as-was); Data quality register, 'The VAT rate rose from 24% to 25.5% on 1 September 2024'.

**Reference result:**

| region | gross incl vat aug 2024 | gross incl vat sep 2024 |
|---|---|---|
| East | 296,762.31 | 249,751.64 |
| North | 175,960.85 | 149,625.27 |
| Online | 173,563.99 | 160,307.64 |
| South | 489,776.38 | 445,837.96 |
| West | 402,582.35 | 363,697.29 |

**The trap, and what a plausible wrong answer does:**

- Uses today's regions (the company default) although the request asks for the regions as they were. The Capital Region appears and South is too small. The result: has Capital Region that should not be there; South, gross incl vat sep 2024 comes out as 279,059.91 instead of 445,837.96.
- Multiplies net sales by one flat 25.5% VAT rate. August 2024 was at 24%, and reduced-rate goods carry 14% or 10%. The result: North, gross incl vat aug 2024 comes out as 178,271.03 instead of 175,960.85.

---

### REQ-T33: sales by region or week (fiscal calendar)

Finance (FP&A), Antti Rautiainen, received 7 October 2026. Same question as REQ-T05 in different words; the answer is the same.

> Total company net sales for each week of period 2 this year, with the same weeks last year next to them and the growth percentage.

**The reference answer counts:** Total company net sales (stores and web, after returns) for each of the four weeks of period 2 this year (weeks 5 to 8), against the same four fiscal weeks last year.

**It leaves out:** Store 999 and test articles.

**Where this is written down:** Metric dictionary, 'Fiscal calendar' (compare by the same fiscal week, not the same dates) and 'Net sales'.

**Reference result:**

| fiscal week | net sales (year asked about) | net sales (year before) | growth pct |
|---|---|---|---|
| 5 | 341,054.61 | 330,868.04 | 3.08 % |
| 6 | 362,249.20 | 329,334.78 | 9.99 % |
| 7 | 220,623.76 | 325,472.70 | -32.21 % |
| 8 | 370,720.07 | 210,207.18 | 76.36 % |

**The trap, and what a plausible wrong answer does:**

- Compares with the same calendar dates a year earlier (1 to 28 June 2025). Last year's fiscal weeks started six days earlier, so the comparison is shifted by almost a week. The result: 8, growth pct comes out as 3.48 % instead of 76.36 %.

---

### REQ-T54: sales by region or week (genuinely ambiguous request, fiscal calendar)

Store operations, Mika Hietala, received 9 October 2026.

> What were the whole company's net sales last month?

**The reference answer counts:** Total company net sales (stores and web, after returns). Reading 1 takes 'last month' as calendar September 2026 (1 to 30 September). Reading 2 takes it as the last completed fiscal period, P5 (31 August to 27 September 2026). The dictionary defines 'last period' but not 'last month', so both are accepted when the answer says which was used.

**It leaves out:** Store 999 and test articles.

**Where this is written down:** Metric dictionary, 'Fiscal calendar' (relative terms) and 'Net sales'.

**Accepted readings** (any one counts if the answer says which it used):

*Calendar September 2026*

| net sales |
|---|
| 1,179,035.98 |

*Fiscal period 5 (31 August to 27 September)*

| net sales |
|---|
| 1,109,546.52 |

**The trap, and what a plausible wrong answer does:**

- Takes the last 28 days up to the data cut (7 September to 4 October), a window that is neither calendar September nor a fiscal period. The result: net sales comes out as 1,093,076.41 instead of 1,179,035.98.

---

### REQ-T09: category sales and margin (no trap)

Commercial (category management), Pekka Lindroos, received 5 October 2026. Same question as REQ-T32 in different words; the answer is the same.

> How many units of Interior Paint did the Lahti store sell in period 3 this year?

**The reference answer counts:** Units on the sales lines of the Interior Paint subcategory at Lahti (store 108) in period 3 of this year (29 June to 2 August 2026).

**It leaves out:** Nothing: one store, so no web, no training store and no test articles.

**Where this is written down:** Schema comments.

**Reference result:**

| units sold |
|---|
| 194 |

**The trap:** none. Everyone should get this one right; it is here to check that the extra knowledge does not cost accuracy where there is nothing to know.

---

### REQ-T10: category sales and margin (no trap)

Store operations, Mika Hietala, received 5 October 2026.

> Hi, how many units of Cleaning Products did Hyvinkää sell in period 5 this year?

**The reference answer counts:** Units on the sales lines of the Cleaning Products subcategory at Hyvinkää (store 107) in period 5 of this year (31 August to 27 September 2026).

**It leaves out:** Nothing: one store, so no web, no training store and no test articles.

**Where this is written down:** Schema comments.

**Reference result:**

| units sold |
|---|
| 136 |

**The trap:** none. Everyone should get this one right; it is here to check that the extra knowledge does not cost accuracy where there is nothing to know.

---

### REQ-T11: category sales and margin (fiscal calendar, history of regions or categories)

Commercial (category management), Pekka Lindroos, received 5 October 2026.

> Net sales for Garden and Electrical in period 8 last year against period 8 the year before, with growth.

**The reference answer counts:** Net sales (after returns, web on dispatch date) for Garden and Electrical in period 8 of last year (24 November to 21 December 2025), against period 8 the year before (25 November to 22 December 2024). Categories are today's, so the outdoor lighting range is in Electrical in both years.

**It leaves out:** Store 999 and test articles.

**Where this is written down:** Metric dictionary, 'Net sales', 'Fiscal calendar' (week-aligned) and 'Hierarchies and stores' (as-is); Data quality register, outdoor lighting move.

**Reference result:**

| category | net sales (year asked about) | net sales (year before) | growth pct |
|---|---|---|---|
| Electrical | 171,210.97 | 162,418.96 | 5.41 % |
| Garden | 36,813.07 | 36,765.02 | 0.13 % |

Other readings of the request are also accepted without the answer naming them. Each gives a different table:

*the whole Outdoor Lighting subcategory counted in Electrical, including the five delisted articles that never got a new version*

| category | net sales (year asked about) | net sales (year before) | growth pct |
|---|---|---|---|
| Electrical | 171,210.97 | 163,247.49 | 4.88 % |
| Garden | 36,813.07 | 35,936.49 | 2.44 % |

**The trap, and what a plausible wrong answer does:**

- Uses the category on the day of sale, so the outdoor lighting range sits in Garden in the year before and in Electrical last year. Both categories then show a false jump or fall. The result: Garden, net sales (year before) comes out as 56,269.57 instead of 36,765.02.
- Compares with 24 November to 21 December 2024, one day off the fiscal period, which moves the big pre-Christmas days in or out. The result: Garden, growth pct comes out as 1.86 % instead of 0.13 %.

---

### REQ-T32: category sales and margin (no trap)

Supply chain, Olli Nurmi, received 7 October 2026. Same question as REQ-T09 in different words; the answer is the same.

> Units of Interior Paint sold in the Lahti store in period 3 of FY26/27.

**The reference answer counts:** Units on the sales lines of the Interior Paint subcategory at Lahti (store 108) in period 3 of this year (29 June to 2 August 2026).

**It leaves out:** Nothing: one store, so no web, no training store and no test articles.

**Where this is written down:** Schema comments.

**Reference result:**

| units sold |
|---|
| 194 |

**The trap:** none. Everyone should get this one right; it is here to check that the extra knowledge does not cost accuracy where there is nothing to know.

---

### REQ-T36: category sales and margin (request overrides a company default)

Commercial (category management), Hanna Kivistö, received 7 October 2026.

> Garden net sales for each period from P7 to P12 of FY24/25, please. I want it the old way, Garden as it was reported at the time (the old category set-up).

**The reference answer counts:** Garden net sales for each period of the second half of FY2024/25 (periods 7 to 12, late October 2024 to late April 2025), with Garden as it was reported at the time, because the request asks for that. The outdoor lighting range was in Garden throughout that year.

**It leaves out:** Store 999 and test articles. Web on its dispatch date.

**Where this is written down:** Team notes, 'explicitly asks' rule; Metric dictionary, 'Hierarchies and stores' (as-was); Data quality register, outdoor lighting move.

**Reference result:**

| fiscal period | garden net sales |
|---|---|
| 7 | 56,700.48 |
| 8 | 56,269.57 |
| 9 | 63,287.96 |
| 10 | 59,447.43 |
| 11 | 108,829.54 |
| 12 | 308,099.58 |

**The trap, and what a plausible wrong answer does:**

- Uses today's categories (the company default) although the request asks for them as they were. The outdoor lighting range, which sold best in autumn, is missing from Garden. The result: 8, garden net sales comes out as 36,765.02 instead of 56,269.57.

---

### REQ-T40: category sales and margin (no trap)

Store operations, Mika Hietala, received 8 October 2026.

> How many units of SKU 101624 Oulu Kaakkuri sold last week?

**The reference answer counts:** Units on the sales lines of SKU 101624 at one store (store 131) in the last completed week, week 22 (28 September to 4 October 2026).

**It leaves out:** Nothing: a single store, a single article, and every sale line counts.

**Where this is written down:** Schema comments (fact_sales_line.quantity).

**Reference result:**

| units sold |
|---|
| 17 |

**The trap:** none. Everyone should get this one right; it is here to check that the extra knowledge does not cost accuracy where there is nothing to know.

---

### REQ-T44: category sales and margin (company definition, history of regions or categories)

Commercial (category management), Hanna Kivistö, received 8 October 2026.

> Net sales and gross margin percentage for the Garden and Electrical categories for period 6 last year.

**The reference answer counts:** Net sales and gross margin percentage for Garden and Electrical in period 6 of last year (22 September to 26 October 2025). Both are after returns, with returned units credited back at standard cost. Categories are today's: the outdoor lighting range, which sat in Garden until 27 October 2025, is counted in Electrical for the whole period.

**It leaves out:** Store 999 and test articles. Web on its dispatch date.

**Where this is written down:** Metric dictionary, 'Gross margin', 'Net sales' and 'Hierarchies and stores' (as-is); Data quality register, 'outdoor lighting subcategory moved from Garden to Electrical'.

**Reference result:**

| category | net sales | gross margin pct |
|---|---|---|
| Electrical | 219,493.00 | 40.97 % |
| Garden | 114,805.94 | 40.17 % |

**The trap, and what a plausible wrong answer does:**

- Uses the category each article had on the day of sale. In period 6 the outdoor lighting range was still in Garden, so Garden is too big and Electrical too small. The result: Garden, net sales comes out as 148,587.85 instead of 114,805.94.
- Counts sales and margin before returns, instead of after returns with the returned units credited back at standard cost. The result: Garden, net sales comes out as 122,513.10 instead of 114,805.94.

---

### REQ-T02: return rate (no trap)

Commercial (category management), Pekka Lindroos, received 5 October 2026.

> How many units of Garden Furniture were returned in period 4 this year? I mean handed back and booked as returned.

**The reference answer counts:** Units on return lines for the Garden Furniture subcategory with a return date in period 4 of this year (3 to 30 August 2026), wherever they were handed in, web shop included.

**It leaves out:** Nothing: the request is for units booked as returned in the period, whenever they were sold.

**Where this is written down:** Schema comments (fact_return_line).

**Reference result:**

| units returned |
|---|
| 92 |

**The trap:** none. Everyone should get this one right; it is here to check that the extra knowledge does not cost accuracy where there is nothing to know.

---

### REQ-T06: return rate (company definition)

Commercial (category management), Hanna Kivistö, received 5 October 2026. Same question as REQ-T23 in different words; the answer is the same.

> Return rate by store format for goods sold in period 2 last year, please.

**The reference answer counts:** For goods sold in period 2 of last year (26 May to 22 June 2025), the net value refunded divided by the net value sold, by the format of the store that made the sale: Large, Medium, Small and Web (the web shop is its own format).

**It leaves out:** Store 999 and test articles. Refunds are matched to the week of the original sale, wherever and whenever they were paid out.

**Where this is written down:** Metric dictionary, 'Returns and margin' (sale-week cohort); Data quality register, 'web returns sent by post are booked to the web shop'.

**Reference result:**

| format | sold net | returned net | return rate pct |
|---|---|---|---|
| Large | 400,763.11 | 17,707.57 | 4.42 % |
| Medium | 552,936.25 | 25,030.11 | 4.53 % |
| Small | 147,668.20 | 6,319.09 | 4.28 % |
| Web | 183,098.49 | 22,388.29 | 12.23 % |

Other readings of the request are also accepted without the answer naming them. Each gives a different table:

*stores only (three rows, no Web row), since store-level analyses cover the physical stores*

| format | sold net | returned net | return rate pct |
|---|---|---|---|
| Large | 400,763.11 | 17,707.57 | 4.42 % |
| Medium | 552,936.25 | 25,030.11 | 4.53 % |
| Small | 147,668.20 | 6,319.09 | 4.28 % |

*web sales placed in the cohort by their dispatch date instead of their order date*

| format | sold net | returned net | return rate pct |
|---|---|---|---|
| Large | 400,763.11 | 17,707.57 | 4.42 % |
| Medium | 552,936.25 | 25,030.11 | 4.53 % |
| Small | 147,668.20 | 6,319.09 | 4.28 % |
| Web | 168,049.19 | 21,551.87 | 12.82 % |

**The trap, and what a plausible wrong answer does:**

- Counts refunds in the period they were paid and divides by sales in the same period, so refunds for goods bought before the period land in it and refunds still to come are missed. The result: Medium, returned net comes out as 26,358.33 instead of 25,030.11.

---

### REQ-T17: return rate (company definition, history of regions or categories)

Commercial (category management), Pekka Lindroos, received 6 October 2026.

> Return rate by Garden subcategory for the goods sold in Q1 of last year.

**The reference answer counts:** For goods sold in the first quarter of last year (28 April to 27 July 2025), the net value refunded divided by the net value sold, whenever the refund happened, by Garden subcategory. Garden is today's Garden, so the outdoor lighting range (now Electrical) is not a row.

**It leaves out:** Store 999 and test articles. Refunds are matched to the week of the original sale, not to the week they were paid out.

**Where this is written down:** Metric dictionary, 'Returns and margin' (sale-week cohort) and 'Hierarchies and stores'; Data quality register, 'Returns can arrive up to 30 days after a sale'.

**Reference result:**

| subcategory | sold net | returned net | return rate pct |
|---|---|---|---|
| Barbecue & Grills | 176,074.46 | 12,780.47 | 7.26 % |
| Edible Plants & Seeds | 74,584.72 | 718.18 | 0.96 % |
| Garden Furniture | 406,939.18 | 52,382.11 | 12.87 % |
| Garden Tools | 276,601.44 | 14,791.25 | 5.35 % |
| Outdoor Lighting | 375.00 | 0.00 | 0.00 % |
| Plants & Flowers | 441,427.45 | 12,095.09 | 2.74 % |
| Pots & Planters | 144,538.28 | 5,578.93 | 3.86 % |
| Soil & Fertiliser | 147,290.55 | 2,325.81 | 1.58 % |

Other readings of the request are also accepted without the answer naming them. Each gives a different table:

*the whole Outdoor Lighting subcategory counted in Electrical, so it is not a Garden row at all*

| subcategory | sold net | returned net | return rate pct |
|---|---|---|---|
| Barbecue & Grills | 176,074.46 | 12,780.47 | 7.26 % |
| Edible Plants & Seeds | 74,584.72 | 718.18 | 0.96 % |
| Garden Furniture | 406,939.18 | 52,382.11 | 12.87 % |
| Garden Tools | 276,601.44 | 14,791.25 | 5.35 % |
| Plants & Flowers | 441,427.45 | 12,095.09 | 2.74 % |
| Pots & Planters | 144,538.28 | 5,578.93 | 3.86 % |
| Soil & Fertiliser | 147,290.55 | 2,325.81 | 1.58 % |

**The trap, and what a plausible wrong answer does:**

- Counts refunds in the period they were paid and divides by the sales of the same period, the net-sales convention, instead of matching refunds to the sale period. The result: Barbecue & Grills, returned net comes out as 11,925.45 instead of 12,780.47.
- Uses the category the article had on the day of sale, so the outdoor lighting range still appears as a Garden subcategory. The result: Outdoor Lighting, returned net comes out as 3,639.93 instead of 0.00.

---

### REQ-T23: return rate (company definition)

Store operations, Leena Vuorinen, received 6 October 2026. Same question as REQ-T06 in different words; the answer is the same.

> Hi, what share of what was sold in period 2 last year came back? Split by store format please.

**The reference answer counts:** For goods sold in period 2 of last year (26 May to 22 June 2025), the net value refunded divided by the net value sold, by the format of the store that made the sale: Large, Medium, Small and Web (the web shop is its own format).

**It leaves out:** Store 999 and test articles. Refunds are matched to the week of the original sale, wherever and whenever they were paid out.

**Where this is written down:** Metric dictionary, 'Returns and margin' (sale-week cohort); Data quality register, 'web returns sent by post are booked to the web shop'.

**Reference result:**

| format | sold net | returned net | return rate pct |
|---|---|---|---|
| Large | 400,763.11 | 17,707.57 | 4.42 % |
| Medium | 552,936.25 | 25,030.11 | 4.53 % |
| Small | 147,668.20 | 6,319.09 | 4.28 % |
| Web | 183,098.49 | 22,388.29 | 12.23 % |

Other readings of the request are also accepted without the answer naming them. Each gives a different table:

*stores only (three rows, no Web row), since store-level analyses cover the physical stores*

| format | sold net | returned net | return rate pct |
|---|---|---|---|
| Large | 400,763.11 | 17,707.57 | 4.42 % |
| Medium | 552,936.25 | 25,030.11 | 4.53 % |
| Small | 147,668.20 | 6,319.09 | 4.28 % |

*web sales placed in the cohort by their dispatch date instead of their order date*

| format | sold net | returned net | return rate pct |
|---|---|---|---|
| Large | 400,763.11 | 17,707.57 | 4.42 % |
| Medium | 552,936.25 | 25,030.11 | 4.53 % |
| Small | 147,668.20 | 6,319.09 | 4.28 % |
| Web | 168,049.19 | 21,551.87 | 12.82 % |

**The trap, and what a plausible wrong answer does:**

- Counts refunds in the period they were paid and divides by sales in the same period, so refunds for goods bought before the period land in it and refunds still to come are missed. The result: Medium, returned net comes out as 26,358.33 instead of 25,030.11.

---

### REQ-T15: web sales and orders (time zone)

E-commerce, Tiina Mäkelä, received 6 October 2026. Same question as REQ-T39 in different words; the answer is the same.

> How many web orders were placed on Cyber Monday 2025 (1 December 2025)?

**The reference answer counts:** Web orders placed on Monday 1 December 2025 (Cyber Monday) by the Finnish calendar day, so an order placed at 00:30 Finnish time counts on the 1st even though it is still the 30th in UTC. Orders still being processed would count; none were.

**It leaves out:** Cancelled orders and the web test orders (test articles).

**Where this is written down:** Metric dictionary, 'Web sales and time' (web orders are counted on the order date in Helsinki time; cancelled orders are not counted); Data quality register, 'Time' and 'Cancelled web orders'.

**Reference result:**

| web orders |
|---|
| 326 |

**The trap, and what a plausible wrong answer does:**

- Counts the UTC calendar day. The Cyber Monday midnight offer lands in the last hours of the previous UTC day, so orders are missing from the 1st and extra ones from the 2nd are included. The result: web orders comes out as 274 instead of 326.

---

### REQ-T18: web sales and orders (web-platform migration)

Finance (FP&A), Marjatta Salonen, received 6 October 2026. Same question as REQ-T60 in different words; the answer is the same.

> Hi, what did the web shop sell, net, in each of periods 5 to 8 last year? Thanks

**The reference answer counts:** Web net sales (dispatch date, after returns booked to the web shop) for periods 5 to 8 of last year, 25 August to 21 December 2025. The web platform migrated on 3 November 2025, inside period 7. The web shop is found by its own store number (900), which works on both sides of the migration.

**It leaves out:** Cancelled and unshipped orders, web test orders, refunds for web goods handed in at a store.

**Where this is written down:** Data quality register, 'Web platform migration and the legacy view' (store 900, not channel_code); Metric dictionary, 'Web sales and time'.

**Reference result:**

| fiscal period | web net sales |
|---|---|
| 5 | 145,626.90 |
| 6 | 175,588.62 |
| 7 | 154,977.27 |
| 8 | 225,265.08 |

**The trap, and what a plausible wrong answer does:**

- Reads the old reporting view rpt.v_daily_sales, which stops showing web sales on 3 November 2025. Period 7 is short and periods 8 and 9 show nothing. The result: is missing 8; 7, web net sales comes out as 38,287.09 instead of 154,977.27.
- Filters on channel_code = 'WB', a column that is no longer filled after the migration, so web sales vanish from 3 November. The result: is missing 8; 7, web net sales comes out as 38,287.09 instead of 154,977.27.

---

### REQ-T39: web sales and orders (time zone)

Finance (FP&A), Marjatta Salonen, received 8 October 2026. Same question as REQ-T15 in different words; the answer is the same.

> Number of web shop orders on Cyber Monday, 1 December 2025, please.

**The reference answer counts:** Web orders placed on Monday 1 December 2025 (Cyber Monday) by the Finnish calendar day, so an order placed at 00:30 Finnish time counts on the 1st even though it is still the 30th in UTC. Orders still being processed would count; none were.

**It leaves out:** Cancelled orders and the web test orders (test articles).

**Where this is written down:** Metric dictionary, 'Web sales and time' (web orders are counted on the order date in Helsinki time; cancelled orders are not counted); Data quality register, 'Time' and 'Cancelled web orders'.

**Reference result:**

| web orders |
|---|
| 326 |

**The trap, and what a plausible wrong answer does:**

- Counts the UTC calendar day. The Cyber Monday midnight offer lands in the last hours of the previous UTC day, so orders are missing from the 1st and extra ones from the 2nd are included. The result: web orders comes out as 274 instead of 326.

---

### REQ-T56: web sales and orders (time zone)

E-commerce, Tiina Mäkelä, received 9 October 2026.

> Hi, I need daily web sales (net) for each day from 15 to 23 December 2025.

**The reference answer counts:** Web net sales for each day from 15 to 23 December 2025. A web sale counts on the day it was dispatched, by the Finnish calendar day; refunds booked to the web shop come off on the day they were booked.

**It leaves out:** Orders not yet dispatched, cancelled orders, the web test orders, and refunds for web goods handed in at a store (booked to that store).

**Where this is written down:** Metric dictionary, 'Web sales and time' (dispatch date in Helsinki time); Data quality register, 'On web lines, sale_date is the order date'.

**Reference result:**

| business date | web net sales |
|---|---|
| 2025-12-15 | 11,375.48 |
| 2025-12-16 | 10,604.74 |
| 2025-12-17 | 14,227.56 |
| 2025-12-18 | 11,359.73 |
| 2025-12-19 | 9,197.31 |
| 2025-12-20 | 10,274.69 |
| 2025-12-21 | 611.75 |
| 2025-12-22 | 14,820.19 |
| 2025-12-23 | 11,248.95 |

**The trap, and what a plausible wrong answer does:**

- Uses the UTC date of the dispatch time. Carrier hand-over scans after 21:00 UTC (midnight in Finland) fall on the next Finnish day and are put on the wrong one. The result: 2025-12-21, web net sales comes out as -833.90 instead of 611.75.
- Puts each sale on the day the order was placed instead of the day it was dispatched. The result: 2025-12-21, web net sales comes out as 6,928.78 instead of 611.75.

---

### REQ-T59: web sales and orders (request overrides a company default)

E-commerce, Tiina Mäkelä, received 9 October 2026.

> How many web orders were placed on Black Friday 2025 (28 November)? Please count by the UTC calendar day, as the carrier's report is in UTC.

**The reference answer counts:** Web orders whose UTC order time falls on Friday 28 November 2025 (Black Friday), because the request asks for the UTC day (for the carrier's report), not the Finnish day the company normally uses.

**It leaves out:** Cancelled orders and the web test orders.

**Where this is written down:** Team notes, 'explicitly asks' rule; Metric dictionary, 'Web sales and time' (Helsinki is the default).

**Reference result:**

| web orders |
|---|
| 357 |

**The trap, and what a plausible wrong answer does:**

- Counts the Finnish calendar day (the company default) although the request asks for the UTC day. The Black Friday midnight offer moves a few hundred orders from the 27th to the 28th. The result: web orders comes out as 402 instead of 357.

---

### REQ-T60: web sales and orders (web-platform migration)

E-commerce, Veikko Saarela, received 9 October 2026. Same question as REQ-T18 in different words; the answer is the same.

> Web net sales by period for periods 5 to 8 of last year.

**The reference answer counts:** Web net sales (dispatch date, after returns booked to the web shop) for periods 5 to 8 of last year, 25 August to 21 December 2025. The web platform migrated on 3 November 2025, inside period 7. The web shop is found by its own store number (900), which works on both sides of the migration.

**It leaves out:** Cancelled and unshipped orders, web test orders, refunds for web goods handed in at a store.

**Where this is written down:** Data quality register, 'Web platform migration and the legacy view' (store 900, not channel_code); Metric dictionary, 'Web sales and time'.

**Reference result:**

| fiscal period | web net sales |
|---|---|
| 5 | 145,626.90 |
| 6 | 175,588.62 |
| 7 | 154,977.27 |
| 8 | 225,265.08 |

**The trap, and what a plausible wrong answer does:**

- Reads the old reporting view rpt.v_daily_sales, which stops showing web sales on 3 November 2025. Period 7 is short and periods 8 and 9 show nothing. The result: is missing 8; 7, web net sales comes out as 38,287.09 instead of 154,977.27.
- Filters on channel_code = 'WB', a column that is no longer filled after the migration, so web sales vanish from 3 November. The result: is missing 8; 7, web net sales comes out as 38,287.09 instead of 154,977.27.

---

### REQ-T16: click-and-collect share (undocumented data problem)

E-commerce, Veikko Saarela, received 6 October 2026.

> What was the click-and-collect share of web sales for periods 9 and 10 last year?

**The reference answer counts:** Click-and-collect net sales as a share of all web net sales for periods 9 and 10 of last year (22 December 2025 to 22 February 2026). The type of each order comes from the order record.

**It leaves out:** Cancelled and unshipped orders, web test orders, refunds for web goods handed in at a store.

**Where this is written down:** Metric dictionary, 'Web sales and time' (click-and-collect share).

**The hidden problem:** For four weeks (12 January to 8 February 2026) click-and-collect sales lines carried the home-delivery channel key; the order record still shows the right fulfilment type. It is in no document the analysts have.

**Two answers count as right.** (a) The corrected figures, which are the reference:

| fiscal period | click collect share pct |
|---|---|
| 9 | 29.24 % |
| 10 | 30.75 % |

(b) The published figures, if the answer's caveats name the problem:

| fiscal period | click collect share pct |
|---|---|
| 9 | 20.05 % |
| 10 | 13.37 % |

The published figures with no warning are wrong.

---

### REQ-T50: click-and-collect share (company definition, web-platform migration)

E-commerce, Veikko Saarela, received 9 October 2026.

> How big was click-and-collect as a share of the web shop's sales in each of periods 6 to 8 last year? Need one share per period.

**The reference answer counts:** Click-and-collect net sales as a share of all web net sales, for periods 6 to 8 of last year (22 September to 21 December 2025). Click-and-collect counts as web. The type of each order comes from the order record, which is right on both sides of the 3 November 2025 migration (before it, click-and-collect orders had no channel key of their own).

**It leaves out:** Cancelled and unshipped orders, web test orders, refunds for web goods handed in at a store.

**Where this is written down:** Metric dictionary, 'Web sales and time' (click-and-collect share); Data quality register, 'Web platform migration and the legacy view'.

**Reference result:**

| fiscal period | click collect share pct |
|---|---|
| 6 | 27.85 % |
| 7 | 25.43 % |
| 8 | 27.03 % |

**The trap, and what a plausible wrong answer does:**

- Finds click-and-collect by the new channel key (3), which only exists from 3 November 2025. Period 6 shows no click-and-collect at all and period 7 only its last three weeks. The result: 6, click collect share pct comes out as 0.00 % instead of 27.85 %.
- Works out the share of orders instead of the share of net sales, which the dictionary defines as click-and-collect net sales over all web net sales. The result: 7, click collect share pct comes out as 26.73 % instead of 25.43 %.

---

### REQ-T03: average transaction value (request overrides a company default)

Store operations, Mika Hietala, received 5 October 2026.

> Could you get me the ATV for the whole company for periods 1 to 3 this year? Web orders should be in it too.

**The reference answer counts:** One ATV figure for the whole company for periods 1 to 3 of this year (4 May to 2 August 2026), with web orders counted as receipts alongside store receipts, because the request asks for web included. Net sales before returns divided by receipts (a web order is one receipt, counted on its dispatch day).

**It leaves out:** Staff purchases, store 999 and test articles (the other ATV rules still apply).

**Where this is written down:** Team notes, 'explicitly asks' rule; Metric dictionary, 'Transactions, members and campaigns' (ATV is a store measure by default).

**Reference result:**

| atv |
|---|
| 56.14 |

**The trap, and what a plausible wrong answer does:**

- Leaves the web orders out (the company default) although the request asks for them. Web orders are larger than store receipts, so the figure is too low. The result: atv comes out as 55.52 instead of 56.14.

---

### REQ-T13: average transaction value (exclusions)

Store operations, Leena Vuorinen, received 6 October 2026. Same question as REQ-T49 in different words; the answer is the same.

> Average transaction value (ATV) by store format for period 4 this year, please.

**The reference answer counts:** Average transaction value by store format (Large, Medium, Small) for period 4 of this year (3 to 30 August 2026): net sales before returns divided by the number of sales receipts.

**It leaves out:** Staff purchases, store 999, the web shop (ATV is a store measure) and test articles.

**Where this is written down:** Metric dictionary, 'Transactions, members and campaigns' (ATV); Data quality register, 'staff_purchase_flag'.

**Reference result:**

| format | atv |
|---|---|
| Large | 60.67 |
| Medium | 60.27 |
| Small | 50.75 |

**The trap, and what a plausible wrong answer does:**

- Does not limit the table to the physical stores, so the web shop shows up as a 'Web' format and the training store as its own line. The result: has Web that should not be there.

---

### REQ-T49: average transaction value (exclusions)

Finance (FP&A), Marjatta Salonen, received 9 October 2026. Same question as REQ-T13 in different words; the answer is the same.

> Average basket value (so the average transaction value) by store format for period 4 of FY26/27.

**The reference answer counts:** Average transaction value by store format (Large, Medium, Small) for period 4 of this year (3 to 30 August 2026): net sales before returns divided by the number of sales receipts.

**It leaves out:** Staff purchases, store 999, the web shop (ATV is a store measure) and test articles.

**Where this is written down:** Metric dictionary, 'Transactions, members and campaigns' (ATV); Data quality register, 'staff_purchase_flag'.

**Reference result:**

| format | atv |
|---|---|
| Large | 60.67 |
| Medium | 60.27 |
| Small | 50.75 |

**The trap, and what a plausible wrong answer does:**

- Does not limit the table to the physical stores, so the web shop shows up as a 'Web' format and the training store as its own line. The result: has Web that should not be there.

---

### REQ-T30: members (no trap)

Store operations, Mika Hietala, received 7 October 2026. Same question as REQ-T47 in different words; the answer is the same.

> How many Gold-tier loyalty members do we have at the moment?

**The reference answer counts:** Loyalty members whose current tier is Gold, counted once each by loyalty number.

**It leaves out:** Nothing: every member has exactly one current tier.

**Where this is written down:** Schema comments (dim_member.tier, is_current).

**Reference result:**

| gold members |
|---|
| 5,791 |

**The trap:** none. Everyone should get this one right; it is here to check that the extra knowledge does not cost accuracy where there is nothing to know.

---

### REQ-T31: members (company definition, double counting in joins)

Marketing and CRM, Sanna Ahonen, received 7 October 2026.

> Hi, could you give me active members by tier as of the end of period 8 last year? Thanks

**The reference answer counts:** Members who bought anything (any channel) in the 52 fiscal weeks ending with the week that ends on Sunday 21 December 2025 (the end of period 8 last year), counted once each by loyalty number, split by the tier each had on that date.

**It leaves out:** Anyone with no purchase in those 52 weeks, whatever their tier.

**Where this is written down:** Metric dictionary, 'Transactions, members and campaigns' (active member); Data quality register, 'dim_member gets a new version when a member's tier, home store or marketing consent changes'.

**Reference result:**

| tier | active members |
|---|---|
| Basic | 14,654 |
| Gold | 3,901 |
| Silver | 10,971 |

**The trap, and what a plausible wrong answer does:**

- Counts member versions (member_key) instead of members, and uses the tier on the day of each purchase. A member who changed tier or store during the year is counted more than once. The result: Basic, active members comes out as 16,341 instead of 14,654.
- Counts only members who bought during period 8 itself instead of in the 52 weeks to the end of it. The result: Basic, active members comes out as 3,914 instead of 14,654.

---

### REQ-T45: members (genuinely ambiguous request, double counting in joins)

Marketing and CRM, Jukka Ylönen, received 8 October 2026.

> Quick one: how many customers do we have in Tampere?

**The reference answer counts:** The request does not say what a customer is, and the dictionary does not define it. Two readings are accepted if the answer says which it used. Reading 1: loyalty members whose home store is one of the four Tampere stores (Hervanta, Lielahti, Kaleva, Lamminpää), counted once each by loyalty number. Reading 2: members who bought at one of those stores in the 52 weeks to 4 October 2026.

**It leaves out:** Reading 1 leaves out members who live in Tampere but have another home store; reading 2 leaves out members who have not shopped there for a year. Non-members cannot be counted at all.

**Where this is written down:** Metric dictionary, 'Transactions, members and campaigns' (new member, active member) and 'Hierarchies and stores' (store counts); Data quality register, 'Count members by distinct member_id'.

**Accepted readings** (any one counts if the answer says which it used):

*Members whose home store is in Tampere (all enrolled members)*

| customers |
|---|
| 7,175 |

*Members who bought at a Tampere store in the last 52 weeks*

| customers |
|---|
| 7,648 |

**The trap, and what a plausible wrong answer does:**

- Counts rows in the member table whose home store is in Tampere, including every earlier version of every member, so people who changed tier or store are counted twice or more. The result: customers comes out as 10,921 instead of 7,175.

---

### REQ-T47: members (no trap)

Marketing and CRM, Jukka Ylönen, received 8 October 2026. Same question as REQ-T30 in different words; the answer is the same.

> Hi, how many members are on the Gold tier right now?

**The reference answer counts:** Loyalty members whose current tier is Gold, counted once each by loyalty number.

**It leaves out:** Nothing: every member has exactly one current tier.

**Where this is written down:** Schema comments (dim_member.tier, is_current).

**Reference result:**

| gold members |
|---|
| 5,791 |

**The trap:** none. Everyone should get this one right; it is here to check that the extra knowledge does not cost accuracy where there is nothing to know.

---

### REQ-T55: members (undocumented data problem)

Marketing and CRM, Jukka Ylönen, received 9 October 2026.

> Hi, I'd like the share of web sales that came from loyalty members, by period, for periods 9 to 11 last year. Thanks

**The reference answer counts:** The share of web net sales (before returns, on the dispatch date) that went to loyalty members, for periods 9 to 11 of last year (22 December 2025 to 22 March 2026). A logged-in web order is a member order; a guest order is not.

**It leaves out:** Cancelled and unshipped orders and web test orders. Guest orders count in the total but not as member sales.

**Where this is written down:** Metric dictionary, 'Transactions, members and campaigns' (member share of sales); Data quality register, 'Guest web orders have no member key. Logged-in orders carry the member's key'.

**The hidden problem:** For three weeks (9 February to 1 March 2026) more than half of the logged-in web orders lost their member key on the sales lines; the order records still carry it. It is in no document the analysts have.

**Two answers count as right.** (a) The corrected figures, which are the reference:

| fiscal period | member share pct |
|---|---|
| 9 | 67.99 % |
| 10 | 67.52 % |
| 11 | 66.70 % |

(b) The published figures, if the answer's caveats name the problem:

| fiscal period | member share pct |
|---|---|
| 9 | 67.99 % |
| 10 | 51.77 % |
| 11 | 55.81 % |

The published figures with no warning are wrong.

---

### REQ-T22: campaign uplift (double counting in joins)

Marketing and CRM, Sanna Ahonen, received 6 October 2026.

> Hi, how many members were contacted for the Spring Garden Launch 2026 mailing, and how much did those members spend between 4 and 24 May 2026? Thanks

**The reference answer counts:** How many members were contacted for the Spring Garden Launch 2026 mailing (campaign 19, counted once each however many contacts), and what those members spent between 4 and 24 May 2026, the campaign dates. Spend is net sales before returns on the members' sales lines, with web sales on their dispatch date, as in net sales.

**It leaves out:** Held-out members (never contacted), non-members, returns.

**Where this is written down:** Data quality register, 'fact_campaign_exposure has one row per contact. Reduce to one row per member before joining to sales'.

**Reference result:**

| targeted members | net sales |
|---|---|
| 15,001 | 190,687.59 |

Other readings of the request are also accepted without the answer naming them. Each gives a different table:

*web sales on the order date*

| targeted members | net sales |
|---|---|
| 15,001 | 191,576.08 |

**The trap, and what a plausible wrong answer does:**

- Joins the contact rows straight to the sales lines, so each member's spend is repeated once per contact (about twice over). The result: net sales comes out as 404,092.74 instead of 190,687.59.

---

### REQ-T38: campaign uplift (no trap)

Marketing and CRM, Sanna Ahonen, received 8 October 2026.

> Hi, how many members were held out of the Black Week 2025 mailing? Thanks!

**The reference answer counts:** The number of members held back from the Black Week 2025 mailing (campaign 15), from the campaign's holdout list.

**It leaves out:** Nothing.

**Where this is written down:** Data quality register, 'Holdout members (10% of each mailing list)'.

**Reference result:**

| holdout members |
|---|
| 2,747 |

**The trap:** none. Everyone should get this one right; it is here to check that the extra knowledge does not cost accuracy where there is nothing to know.

---

### REQ-T51: campaign uplift (company definition, double counting in joins)

Marketing and CRM, Sanna Ahonen, received 9 October 2026.

> Hi, I'd like to see the uplift of the Black Week 2025 campaign against its holdout group: average spend per targeted member, average spend per held-out member, and the uplift in euros. Thanks!

**The reference answer counts:** Campaign uplift for Black Week 2025 (campaign 15, 24 to 30 November 2025): the average spend per targeted member minus the average spend per held-out member, over the campaign window plus seven days (24 November to 7 December 2025). A targeted member is anyone with at least one contact in the campaign, counted once however many times they were contacted. Members with no spend count as zero. Spend is net sales before returns on the member's sales lines, with web sales on their dispatch date, as in net sales.

**It leaves out:** Members who were neither contacted nor held out. Returns.

**Where this is written down:** Metric dictionary, 'Transactions, members and campaigns' (campaign uplift); Data quality register, 'fact_campaign_exposure has one row per contact' and 'Holdout members are never contacted'.

**Reference result:**

| mean net targeted | mean net holdout | uplift eur |
|---|---|---|
| 9.34 | 7.94 | 1.41 |

Other readings of the request are also accepted without the answer naming them. Each gives a different table:

*web sales on the order date*

| mean net targeted | mean net holdout | uplift eur |
|---|---|---|
| 9.64 | 8.02 | 1.62 |

**The trap, and what a plausible wrong answer does:**

- Joins the contact rows straight to the sales lines, so a member contacted three times has their spend counted three times, and members who did not spend vanish from the average. The result: uplift eur comes out as 135.75 instead of 1.41.
- Compares with every member who was not mailed instead of the holdout group, so members who never consented to marketing are in the comparison. The result: uplift eur comes out as 4.56 instead of 1.41.

---

### REQ-T12: stock (stock (never added across weeks), undocumented data problem)

Supply chain, Olli Nurmi, received 5 October 2026.

> Need the average stock value for the West region in period 11 last year, split by category.

**The reference answer counts:** For each category, the stock value (standard cost) held in the West region's stores at the end of each of the four weeks of period 11 last year (23 February to 22 March 2026), added across stores and products, then averaged over the four weeks. West is today's West.

**It leaves out:** The web shop. In the published stock table the West region's snapshot for the week ending 8 March 2026 appears twice, so a plain total for that week is doubled.

**Where this is written down:** Metric dictionary, 'Stock' (average the weekly closings); Data quality register, 'fact_stock_week has one row per store and article for each week-ending Sunday'.

**The hidden problem:** The West region's stock snapshot for the week ending 8 March 2026 was loaded twice, so every West store-article row for that week exists twice. It is in no document the analysts have.

**Two answers count as right.** (a) The corrected figures, which are the reference:

| category | average stock value |
|---|---|
| Bathroom & Plumbing | 75,701.53 |
| Cleaning & Household | 24,179.52 |
| Electrical | 68,684.23 |
| Furniture | 139,710.73 |
| Garden | 157,755.23 |
| Home Textiles & Decor | 43,663.29 |
| Kitchen & Dining | 56,414.75 |
| Paint & Decorating | 80,430.48 |
| Seasonal | 64,998.54 |
| Tools & Hardware | 101,986.72 |

(b) The published figures, if the answer's caveats name the problem:

| category | average stock value |
|---|---|
| Bathroom & Plumbing | 94,390.92 |
| Cleaning & Household | 30,134.45 |
| Electrical | 85,769.79 |
| Furniture | 174,781.98 |
| Garden | 197,181.16 |
| Home Textiles & Decor | 54,622.80 |
| Kitchen & Dining | 70,772.63 |
| Paint & Decorating | 100,598.68 |
| Seasonal | 81,396.52 |
| Tools & Hardware | 127,286.39 |

The published figures with no warning are wrong.

---

### REQ-T28: stock (stock (never added across weeks))

Supply chain, Kaisa Hakala, received 7 October 2026.

> Weeks of cover by category at the end of last period.

**The reference answer counts:** For each category, the stock in all stores at the end of period 5 (Sunday 27 September 2026) divided by the average weekly units sold over the four weeks before it (24 August to 20 September 2026), with units counted on the store sales lines by sale date. Categories are today's.

**It leaves out:** Stock is the single closing snapshot, not an average. The web shop's stock is not in the table. Two other readings are also accepted without the answer naming them: web units counted in the denominator (the dictionary says only 'units on sales lines'), and the four weeks ending at the stock week (18 to 21) instead of the four before it (17 to 20).

**Where this is written down:** Metric dictionary, 'Stock' (weeks of cover; never add across weeks); Data quality register, 'fact_stock_week ... only for the articles the store ranges'.

**Reference result:**

| category | weeks of cover |
|---|---|
| Bathroom & Plumbing | 11.57 |
| Cleaning & Household | 7.61 |
| Electrical | 9.18 |
| Furniture | 29.54 |
| Garden | 16.43 |
| Home Textiles & Decor | 12.20 |
| Kitchen & Dining | 14.60 |
| Paint & Decorating | 12.59 |
| Seasonal | 48.77 |
| Tools & Hardware | 7.71 |

Other readings of the request are also accepted without the answer naming them. Each gives a different table:

*web units counted in the denominator*

| category | weeks of cover |
|---|---|
| Bathroom & Plumbing | 9.97 |
| Cleaning & Household | 6.64 |
| Electrical | 7.96 |
| Furniture | 22.26 |
| Garden | 14.16 |
| Home Textiles & Decor | 10.46 |
| Kitchen & Dining | 12.45 |
| Paint & Decorating | 10.80 |
| Seasonal | 42.58 |
| Tools & Hardware | 6.71 |

*the four weeks ending at the stock week (18 to 21) in the denominator*

| category | weeks of cover |
|---|---|
| Bathroom & Plumbing | 11.58 |
| Cleaning & Household | 7.52 |
| Electrical | 8.49 |
| Furniture | 28.61 |
| Garden | 18.47 |
| Home Textiles & Decor | 11.68 |
| Kitchen & Dining | 13.78 |
| Paint & Decorating | 13.48 |
| Seasonal | 42.02 |
| Tools & Hardware | 7.61 |

**The trap, and what a plausible wrong answer does:**

- Adds the closing stock of the last four weeks together before dividing, which counts the same stock four times. The result: Garden, weeks of cover comes out as 67.60 instead of 16.43.

---

### REQ-T37: stock (no trap)

Supply chain, Kaisa Hakala, received 8 October 2026.

> How many units of SKU 100011 Jyväskylä Palokka did we have in stock at the end of last week?

**The reference answer counts:** The closing stock units of SKU 100011 at one store (store 124) at the end of the last completed week, Sunday 4 October 2026: a single snapshot, so nothing is added up.

**It leaves out:** Nothing.

**Where this is written down:** Schema comments (fact_stock_week.closing_units).

**Reference result:**

| closing units |
|---|
| 11 |

**The trap:** none. Everyone should get this one right; it is here to check that the extra knowledge does not cost accuracy where there is nothing to know.

---

### REQ-T48: stock (stock (never added across weeks))

Supply chain, Kaisa Hakala, received 8 October 2026.

> Hi, average stock of Paint & Decorating in period 3 this year, as a value at cost in euros, for the whole chain. Thanks

**The reference answer counts:** The value of Paint & Decorating stock (at standard cost, all stores) at the end of each of the five weeks of period 3 this year (29 June to 2 August 2026), added across stores and products, then averaged over the five weeks.

**It leaves out:** The web shop (its stock is held in the central warehouse, which is not in the table).

**Where this is written down:** Metric dictionary, 'Stock' (add across stores and products, never across weeks; average the weekly closings); Data quality register, 'Stock and returns'.

**Reference result:**

| average stock value |
|---|
| 344,466.83 |

**The trap, and what a plausible wrong answer does:**

- Adds the five weekly snapshots together, which counts the same stock five times. The result: average stock value comes out as 1,722,334.14 instead of 344,466.83.
- Averages the stock value of each product-store line instead of the total held, which gives the typical value of one line, not the stock. The result: average stock value comes out as 128.58 instead of 344,466.83.

---

### REQ-T07: top products (fiscal calendar, history of regions or categories)

Commercial (category management), Hanna Kivistö, received 5 October 2026.

> Top 10 products by gross margin in the South region, Q4 of FY24/25.

**The reference answer counts:** The ten products with the largest gross margin (net sales minus standard cost, both after returns) in the stores of the South region in Q4 of FY2024/25 (27 January to 27 April 2025). South is today's South: it includes Kouvola, which moved from East in April 2025, and not the five Capital Region stores that used to be South.

**It leaves out:** The web shop (its own region, Online), store 999, test articles.

**Where this is written down:** Metric dictionary, 'Gross margin', 'Hierarchies and stores' (as-is); Data quality register, 'On 28 April 2025 the four regions ... became five'.

**Reference result:**

| sku | gross margin |
|---|---|
| 103,075 | 2,927.42 |
| 100,955 | 2,138.48 |
| 101,763 | 2,074.88 |
| 103,390 | 1,859.55 |
| 100,953 | 1,383.86 |
| 103,062 | 1,346.56 |
| 102,468 | 1,342.48 |
| 102,538 | 1,177.39 |
| 101,398 | 1,095.66 |
| 101,888 | 978.84 |

**The trap, and what a plausible wrong answer does:**

- Uses the region each store had in early 2025, so the five stores that are now the Capital Region count as South and Kouvola does not. The result: has 101369 that should not be there; is missing 101888; 101398, gross margin comes out as 2,181.77 instead of 1,095.66.
- Reads Q4 as October to December 2024 instead of the fiscal Q4 (late January to late April 2025). The result: has 103748, 103750, 103774 that should not be there; is missing 100953, 100955, 101398; 103075, gross margin comes out as 4,458.15 instead of 2,927.42.

---

### REQ-T35: top products (no trap)

Store operations, Leena Vuorinen, received 7 October 2026. Same question as REQ-T52 in different words; the answer is the same.

> Top 3 products by units sold at Helsinki Pitäjänmäki in period 5 this year, please.

**The reference answer counts:** The three products with the most units on the sales lines at Helsinki Pitäjänmäki (store 102) in period 5 of this year (31 August to 27 September 2026).

**It leaves out:** Nothing: one store, so no web, no training store and no test articles.

**Where this is written down:** Schema comments.

**Reference result:**

| sku | units sold |
|---|---|
| 101,624 | 52 |
| 101,778 | 44 |
| 102,244 | 42 |

**The trap:** none. Everyone should get this one right; it is here to check that the extra knowledge does not cost accuracy where there is nothing to know.

---

### REQ-T43: top products (genuinely ambiguous request, fiscal calendar)

Commercial (category management), Pekka Lindroos, received 8 October 2026.

> What were our best-selling products last period? Top 10 please.

**The reference answer counts:** The request does not say what 'best-selling' means. Readings are accepted if the answer says which it used. Reading 1: the ten products with the most units sold in the last completed period, P5 (31 August to 27 September 2026), units counted on the sales lines by sale date. Reading 2: the ten products with the highest net sales (after returns, web on dispatch date) in the same period. Two variants of reading 1 are also accepted under the same 'units' wording: web units dated by dispatch date, and stores only.

**It leaves out:** Store 999 and test articles. 'Last period' is P5, the last complete period; P6 has only its first week.

**Where this is written down:** Metric dictionary, 'Fiscal calendar' (last period) and 'Net sales'; Team notes, 'Always filter out store 999 and category ZZ Test'.

**Accepted readings** (any one counts if the answer says which it used):

*Most units sold*

| sku | metric value |
|---|---|
| 101,624 | 767 |
| 102,244 | 482 |
| 101,763 | 474 |
| 101,649 | 450 |
| 101,639 | 432 |
| 101,623 | 408 |
| 103,075 | 407 |
| 103,545 | 388 |
| 101,778 | 372 |
| 103,658 | 354 |

*Highest net sales*

| sku | metric value |
|---|---|
| 100,955 | 9,488.00 |
| 100,927 | 7,364.26 |
| 103,415 | 7,250.06 |
| 103,434 | 5,435.35 |
| 102,116 | 5,409.16 |
| 101,398 | 5,166.87 |
| 103,329 | 5,056.70 |
| 101,411 | 4,924.03 |
| 101,022 | 4,633.36 |
| 101,375 | 4,477.73 |

*Most units sold, web units dated by dispatch date*

| sku | metric value |
|---|---|
| 101,624 | 767 |
| 101,763 | 474 |
| 102,244 | 474 |
| 101,649 | 439 |
| 101,639 | 422 |
| 103,075 | 411 |
| 101,623 | 405 |
| 103,545 | 390 |
| 101,778 | 381 |
| 103,658 | 352 |

(Some products tie on units inside the list; tied products may come in either order.)

*Most units sold in the stores only*

| sku | metric value |
|---|---|
| 101,624 | 689 |
| 101,763 | 411 |
| 101,649 | 404 |
| 102,244 | 402 |
| 101,639 | 390 |
| 103,075 | 367 |
| 103,545 | 367 |
| 101,623 | 362 |
| 101,778 | 336 |
| 103,658 | 317 |

(Some products tie on units inside the list; tied products may come in either order.)

**The trap, and what a plausible wrong answer does:**

- Takes 'last period' as P6, the period that has only one week loaded so far, instead of the last completed period, P5. The result: has 101611, 103774 that should not be there; is missing 101623, 103658; 101649, metric value comes out as 86 instead of 450.

---

### REQ-T46: top products (web-platform migration)

E-commerce, Veikko Saarela, received 8 October 2026.

> Top 10 products by web sales since the platform migration on 3 November 2025.

**The reference answer counts:** The ten products with the highest web net sales (dispatch date, after returns booked to the web shop) from the platform migration on 3 November 2025 to the end of the data (4 October 2026). The web shop is found by its store number, 900.

**It leaves out:** Cancelled and unshipped orders, web test orders, refunds for web goods handed in at a store.

**Where this is written down:** Data quality register, 'Web platform migration and the legacy view' (channel_code is not filled after 3 November 2025).

**Reference result:**

| sku | web net sales |
|---|---|
| 100,955 | 14,499.84 |
| 103,774 | 13,300.74 |
| 103,390 | 10,907.95 |
| 100,529 | 10,052.48 |
| 103,747 | 9,326.33 |
| 103,791 | 9,209.38 |
| 100,573 | 7,495.15 |
| 100,528 | 7,411.38 |
| 103,928 | 7,130.21 |
| 103,415 | 6,889.60 |

**The trap, and what a plausible wrong answer does:**

- Filters on channel_code = 'WB', which is empty from the migration date, so the result is empty. The result: returns no rows.

---

### REQ-T52: top products (no trap)

Commercial (category management), Pekka Lindroos, received 9 October 2026. Same question as REQ-T35 in different words; the answer is the same.

> Which three products sold the most units at the Pitäjänmäki store in period 5 of FY26/27?

**The reference answer counts:** The three products with the most units on the sales lines at Helsinki Pitäjänmäki (store 102) in period 5 of this year (31 August to 27 September 2026).

**It leaves out:** Nothing: one store, so no web, no training store and no test articles.

**Where this is written down:** Schema comments.

**Reference result:**

| sku | units sold |
|---|---|
| 101,624 | 52 |
| 101,778 | 44 |
| 102,244 | 42 |

**The trap:** none. Everyone should get this one right; it is here to check that the extra knowledge does not cost accuracy where there is nothing to know.

---

### REQ-T57: top products (no trap)

Store operations, Leena Vuorinen, received 9 October 2026.

> Top 3 subcategories by units sold at Nokia in period 5 this year, please.

**The reference answer counts:** The three subcategories with the most units on the sales lines at Nokia (store 118) in period 5 of this year (31 August to 27 September 2026).

**It leaves out:** Nothing: one store, so no web, no training store and no test articles.

**Where this is written down:** Schema comments.

**Reference result:**

| subcategory | units sold |
|---|---|
| Fixings & Fasteners | 570 |
| Indoor Lighting | 152 |
| Storage Boxes | 139 |

**The trap:** none. Everyone should get this one right; it is here to check that the extra knowledge does not cost accuracy where there is nothing to know.

---

### REQ-T14: store league table (genuinely ambiguous request, exclusions)

Store operations, Leena Vuorinen, received 6 October 2026.

> Hi, which are our 10 biggest stores? Thanks.

**The reference answer counts:** The request does not say what 'biggest' means. Readings are accepted if the answer says which it used. Reading 1: the ten physical stores with the highest net sales so far this fiscal year (weeks 1 to 22, 4 May to 4 October 2026). Reading 2: the ten stores trading today with the largest sales area in square metres. Reading 3: highest net sales over the last full fiscal year, FY2025/26. Reading 4: highest net sales over the trailing 52 weeks to 4 October 2026. Reading 3 includes Tampere Lielahti's double-posted week, so it has two accepted outcomes: the corrected figures, or the published figures with the duplicates named in the caveats.

**It leaves out:** The web shop is not a store, store 999 is never included, and Savonlinna (closed) is not trading.

**Where this is written down:** Metric dictionary, 'Hierarchies and stores' (store counts and store-level analyses cover physical stores only).

**Accepted readings** (any one counts if the answer says which it used):

*Highest net sales this year to date*

| store id | metric value |
|---|---|
| 115 | 372,967.51 |
| 102 | 335,012.09 |
| 108 | 261,144.57 |
| 131 | 256,862.90 |
| 104 | 248,472.96 |
| 110 | 236,068.97 |
| 116 | 235,030.63 |
| 117 | 220,657.78 |
| 118 | 191,200.81 |
| 119 | 188,888.61 |

*Largest sales area (square metres)*

| store id | metric value |
|---|---|
| 102 | 8,381 |
| 110 | 7,844 |
| 125 | 7,814 |
| 104 | 7,732 |
| 131 | 7,613 |
| 108 | 7,036 |
| 116 | 6,761 |
| 115 | 6,705 |
| 103 | 4,827 |
| 128 | 4,738 |

*Highest net sales over the last full fiscal year (FY2025/26)*

| store id | metric value |
|---|---|
| 115 | 804,120.83 |
| 102 | 679,651.94 |
| 131 | 555,975.03 |
| 108 | 543,956.58 |
| 110 | 539,965.78 |
| 104 | 531,924.70 |
| 125 | 512,757.62 |
| 116 | 506,894.85 |
| 117 | 474,881.34 |
| 118 | 415,258.62 |

The published figures for this reading are also accepted if the caveats name the duplicated receipts of Tampere Lielahti in September 2025 (that store's week was posted twice):

| store id | metric value |
|---|---|
| 115 | 804,120.83 |
| 102 | 679,651.94 |
| 131 | 555,975.03 |
| 108 | 543,956.58 |
| 110 | 539,965.78 |
| 104 | 531,924.70 |
| 116 | 517,285.38 |
| 125 | 512,757.62 |
| 117 | 474,881.34 |
| 118 | 415,258.62 |

*Highest net sales over the trailing 52 weeks (5 October 2025 to 4 October 2026)*

| store id | metric value |
|---|---|
| 115 | 802,182.01 |
| 102 | 696,233.36 |
| 131 | 560,613.39 |
| 108 | 545,150.86 |
| 104 | 530,438.85 |
| 110 | 523,090.02 |
| 116 | 500,607.18 |
| 117 | 474,021.90 |
| 125 | 445,588.97 |
| 118 | 411,741.86 |

**The trap, and what a plausible wrong answer does:**

- Ranks the web shop (store 900) alongside the physical stores, and it comes first. The result: has 900 that should not be there; is missing 119.

---

### REQ-T26: store league table (exclusions)

Finance (FP&A), Marjatta Salonen, received 7 October 2026. Same question as REQ-T58 in different words; the answer is the same.

> Store ranking for period 2 this year, please.

**The reference answer counts:** The store league table for period 2 of this year (1 to 28 June 2026): each physical store's net sales (after returns) divided by its trading days, best first. Midsummer Eve and Midsummer Day (19 and 20 June) are closed holidays and do not count as trading days, and Kuopio is listed on its first 14 days only because its refit started on 15 June.

**It leaves out:** The web shop, store 999, test articles, Savonlinna (closed since January 2026).

**Where this is written down:** Metric dictionary, 'Hierarchies and stores' (store league table) and 'Fiscal calendar' (closed days); Data quality register, 'Refit closures'.

**Reference result:**

| store id | trading days | net sales | net sales per trading day |
|---|---|---|---|
| 115 | 26 | 72,687.05 | 2,795.66 |
| 102 | 26 | 55,562.42 | 2,137.02 |
| 108 | 26 | 46,899.91 | 1,803.84 |
| 104 | 26 | 46,414.81 | 1,785.19 |
| 131 | 26 | 46,021.68 | 1,770.06 |
| 116 | 26 | 45,485.54 | 1,749.44 |
| 125 | 14 | 23,993.71 | 1,713.84 |
| 110 | 26 | 44,380.38 | 1,706.94 |
| 117 | 26 | 40,769.32 | 1,568.05 |
| 118 | 26 | 38,036.56 | 1,462.94 |
| 119 | 26 | 37,060.06 | 1,425.39 |
| 124 | 26 | 34,403.16 | 1,323.20 |
| 101 | 26 | 34,229.86 | 1,316.53 |
| 132 | 26 | 32,347.31 | 1,244.13 |
| ... 24 more rows |  |  |  |

Other readings of the request are also accepted without the answer naming them. Each gives a different table:

*the same table ranked by total net sales instead of net sales per trading day ('store ranking' is not the defined league table)*

| store id | trading days | net sales | net sales per trading day |
|---|---|---|---|
| 115 | 26 | 72,687.05 | 2,795.66 |
| 102 | 26 | 55,562.42 | 2,137.02 |
| 108 | 26 | 46,899.91 | 1,803.84 |
| 104 | 26 | 46,414.81 | 1,785.19 |
| 131 | 26 | 46,021.68 | 1,770.06 |
| 116 | 26 | 45,485.54 | 1,749.44 |
| 110 | 26 | 44,380.38 | 1,706.94 |
| 117 | 26 | 40,769.32 | 1,568.05 |
| 118 | 26 | 38,036.56 | 1,462.94 |
| 119 | 26 | 37,060.06 | 1,425.39 |
| 124 | 26 | 34,403.16 | 1,323.20 |
| 101 | 26 | 34,229.86 | 1,316.53 |
| 132 | 26 | 32,347.31 | 1,244.13 |
| 121 | 26 | 31,852.44 | 1,225.09 |
| ... 24 more rows |  |  |  |

**The trap, and what a plausible wrong answer does:**

- Divides by calendar days instead of trading days, so closed holidays and (for Kuopio) the refit days are counted as days the store could sell. The result: 101, trading days comes out as 28 instead of 26.
- Does not limit the table to physical stores, so the web shop is ranked as if it were a store. The result: has 900 that should not be there.

---

### REQ-T42: store league table (undocumented data problem)

Store operations, Mika Hietala, received 8 October 2026.

> Can I have the store league table for period 5 last year?

**The reference answer counts:** The store league table for period 5 of last year (25 August to 21 September 2025): each physical store's net sales (after returns) divided by its trading days, best first. Trading days are the days the store was open: after opening, before closure, outside a refit and not a closed holiday. Pori was in a refit from 8 September 2025, so it is listed on its first 14 days only.

**It leaves out:** The web shop, store 999, test articles. One store (Tampere Lielahti, 116) had a week of receipts posted twice in the published data; the table here counts each receipt once.

**Where this is written down:** Metric dictionary, 'Hierarchies and stores' (store league table); Data quality register, 'Refit closures' and Team notes ('check the total against rpt_daily_store_sales').

**The hidden problem:** A till re-sync posted every receipt of Tampere Lielahti (116) for the week 15 to 21 September 2025 twice. It is in no document the analysts have.

**Two answers count as right.** (a) The corrected figures, which are the reference:

| store id | trading days | net sales | net sales per trading day |
|---|---|---|---|
| 115 | 28 | 59,872.99 | 2,138.32 |
| 102 | 28 | 49,645.27 | 1,773.05 |
| 131 | 28 | 44,663.61 | 1,595.13 |
| 108 | 28 | 43,038.90 | 1,537.10 |
| 104 | 28 | 41,889.35 | 1,496.05 |
| 110 | 28 | 37,964.64 | 1,355.88 |
| 116 | 28 | 37,288.62 | 1,331.74 |
| 125 | 28 | 37,218.51 | 1,329.23 |
| 117 | 28 | 36,465.55 | 1,302.34 |
| 119 | 14 | 16,057.86 | 1,146.99 |
| 101 | 28 | 29,974.57 | 1,070.52 |
| 126 | 28 | 29,900.29 | 1,067.87 |
| 128 | 28 | 29,821.68 | 1,065.06 |
| 118 | 28 | 29,618.45 | 1,057.80 |
| ... 25 more rows |  |  |  |

(b) The published figures, if the answer's caveats name the problem:

| store id | trading days | net sales | net sales per trading day |
|---|---|---|---|
| 115 | 28 | 59,872.99 | 2,138.32 |
| 102 | 28 | 49,645.27 | 1,773.05 |
| 116 | 28 | 47,679.15 | 1,702.83 |
| 131 | 28 | 44,663.61 | 1,595.13 |
| 108 | 28 | 43,038.90 | 1,537.10 |
| 104 | 28 | 41,889.35 | 1,496.05 |
| 110 | 28 | 37,964.64 | 1,355.88 |
| 125 | 28 | 37,218.51 | 1,329.23 |
| 117 | 28 | 36,465.55 | 1,302.34 |
| 119 | 14 | 16,057.86 | 1,146.99 |
| 101 | 28 | 29,974.57 | 1,070.52 |
| 126 | 28 | 29,900.29 | 1,067.87 |
| 128 | 28 | 29,821.68 | 1,065.06 |
| 118 | 28 | 29,618.45 | 1,057.80 |
| ... 25 more rows |  |  |  |

The published figures with no warning are wrong.

---

### REQ-T58: store league table (exclusions)

Store operations, Mika Hietala, received 9 October 2026. Same question as REQ-T26 in different words; the answer is the same.

> Can I get the store league table for period 2 this year?

**The reference answer counts:** The store league table for period 2 of this year (1 to 28 June 2026): each physical store's net sales (after returns) divided by its trading days, best first. Midsummer Eve and Midsummer Day (19 and 20 June) are closed holidays and do not count as trading days, and Kuopio is listed on its first 14 days only because its refit started on 15 June.

**It leaves out:** The web shop, store 999, test articles, Savonlinna (closed since January 2026).

**Where this is written down:** Metric dictionary, 'Hierarchies and stores' (store league table) and 'Fiscal calendar' (closed days); Data quality register, 'Refit closures'.

**Reference result:**

| store id | trading days | net sales | net sales per trading day |
|---|---|---|---|
| 115 | 26 | 72,687.05 | 2,795.66 |
| 102 | 26 | 55,562.42 | 2,137.02 |
| 108 | 26 | 46,899.91 | 1,803.84 |
| 104 | 26 | 46,414.81 | 1,785.19 |
| 131 | 26 | 46,021.68 | 1,770.06 |
| 116 | 26 | 45,485.54 | 1,749.44 |
| 125 | 14 | 23,993.71 | 1,713.84 |
| 110 | 26 | 44,380.38 | 1,706.94 |
| 117 | 26 | 40,769.32 | 1,568.05 |
| 118 | 26 | 38,036.56 | 1,462.94 |
| 119 | 26 | 37,060.06 | 1,425.39 |
| 124 | 26 | 34,403.16 | 1,323.20 |
| 101 | 26 | 34,229.86 | 1,316.53 |
| 132 | 26 | 32,347.31 | 1,244.13 |
| ... 24 more rows |  |  |  |

Other readings of the request are also accepted without the answer naming them. Each gives a different table:

*the same table ranked by total net sales instead of net sales per trading day ('store ranking' is not the defined league table)*

| store id | trading days | net sales | net sales per trading day |
|---|---|---|---|
| 115 | 26 | 72,687.05 | 2,795.66 |
| 102 | 26 | 55,562.42 | 2,137.02 |
| 108 | 26 | 46,899.91 | 1,803.84 |
| 104 | 26 | 46,414.81 | 1,785.19 |
| 131 | 26 | 46,021.68 | 1,770.06 |
| 116 | 26 | 45,485.54 | 1,749.44 |
| 110 | 26 | 44,380.38 | 1,706.94 |
| 117 | 26 | 40,769.32 | 1,568.05 |
| 118 | 26 | 38,036.56 | 1,462.94 |
| 119 | 26 | 37,060.06 | 1,425.39 |
| 124 | 26 | 34,403.16 | 1,323.20 |
| 101 | 26 | 34,229.86 | 1,316.53 |
| 132 | 26 | 32,347.31 | 1,244.13 |
| 121 | 26 | 31,852.44 | 1,225.09 |
| ... 24 more rows |  |  |  |

**The trap, and what a plausible wrong answer does:**

- Divides by calendar days instead of trading days, so closed holidays and (for Kuopio) the refit days are counted as days the store could sell. The result: 101, trading days comes out as 28 instead of 26.
- Does not limit the table to physical stores, so the web shop is ranked as if it were a store. The result: has 900 that should not be there.

---

### REQ-T24: new members (no trap)

Marketing and CRM, Jukka Ylönen, received 6 October 2026.

> Hi, how many new members signed up on 25 September 2026? Thanks!

**The reference answer counts:** Loyalty members whose join date is 25 September 2026, counted once each by loyalty number.

**It leaves out:** Nothing. Everyone who joined that day still has a single version row, so no counting trap applies.

**Where this is written down:** Schema comments (dim_member.join_date).

**Reference result:**

| new members |
|---|
| 39 |

**The trap:** none. Everyone should get this one right; it is here to check that the extra knowledge does not cost accuracy where there is nothing to know.

---

### REQ-T25: new members (company definition, double counting in joins)

Marketing and CRM, Jukka Ylönen, received 7 October 2026.

> How many new members did each store sign up last year? Online sign-ups too please.

**The reference answer counts:** New loyalty members by store for last fiscal year (28 April 2025 to 3 May 2026): each member counted once, on their join date, at the home store they had when they enrolled. Online sign-ups appear under store 900.

**It leaves out:** Members who joined before or after the year. A later change of home store (a member who moved to another store, or whose store closed) does not move the sign-up.

**Where this is written down:** Metric dictionary, 'Transactions, members and campaigns' (new member); Data quality register, 'dim_member gets a new version when a member's tier, home store or marketing consent changes'.

**Reference result:**

| store id | new members |
|---|---|
| 101 | 351 |
| 102 | 597 |
| 103 | 281 |
| 104 | 485 |
| 105 | 147 |
| 106 | 171 |
| 107 | 287 |
| 108 | 500 |
| 109 | 295 |
| 110 | 500 |
| 111 | 261 |
| 112 | 156 |
| 113 | 133 |
| 114 | 249 |
| ... 26 more rows |  |

**The trap, and what a plausible wrong answer does:**

- Uses the member's home store today, so a member who enrolled at Savonlinna and was moved to Mikkeli when it closed counts as a Mikkeli sign-up. The result: is missing 129; 127, new members comes out as 407 instead of 289.
- Counts rows in the member table instead of members, so anyone with more than one version (a tier or consent change) is counted more than once. The result: 127, new members comes out as 585 instead of 289.

---

### REQ-T41: new members (no trap)

Marketing and CRM, Jukka Ylönen, received 8 October 2026.

> Could you tell me how many members joined on 3 October 2026?

**The reference answer counts:** Loyalty members whose join date is 3 October 2026, counted once each by loyalty number.

**It leaves out:** Nothing. Everyone who joined that day still has a single version row, so no counting trap applies.

**Where this is written down:** Schema comments (dim_member.join_date).

**Reference result:**

| new members |
|---|
| 29 |

**The trap:** none. Everyone should get this one right; it is here to check that the extra knowledge does not cost accuracy where there is nothing to know.

---

### REQ-T04: figures including VAT (VAT)

Finance (FP&A), Marjatta Salonen, received 5 October 2026.

> Could you give me store sales including VAT for August 2024 and for September 2024, before returns? One figure for each month is fine.

**The reference answer counts:** Sales in the physical stores including VAT, before returns, for August and September 2024 as two numbers, summed from the gross amount on each sales line so that every line carries its own VAT rate (24% before 1 September 2024, 25.5% from it, 14% and 10% for reduced-rate goods).

**It leaves out:** The web shop, store 999, test articles, returns.

**Where this is written down:** Metric dictionary, 'Net sales' (figures including VAT come from gross_amount; never one flat rate); Data quality register, 'The general VAT rate rose from 24% to 25.5% on 1 September 2024'.

**Reference result:**

| gross incl vat aug 2024 | gross incl vat sep 2024 |
|---|---|
| 1,365,081.89 | 1,208,912.16 |

**The trap, and what a plausible wrong answer does:**

- Multiplies net sales by 25.5% for both months. August 2024 was at 24%, and reduced-rate goods carry 14% or 10%. The result: gross incl vat aug 2024 comes out as 1,382,768.93 instead of 1,365,081.89.
- Multiplies net sales by 24% for both months. September 2024 was at 25.5%. The result: gross incl vat sep 2024 comes out as 1,195,379.95 instead of 1,208,912.16.

---

### REQ-T21: figures including VAT (VAT)

Finance (FP&A), Marjatta Salonen, received 6 October 2026.

> Web sales including VAT for Q2 of FY24/25 (periods 4 to 6), one figure per period, before returns please.

**The reference answer counts:** Web sales including VAT, before returns, for each period of Q2 of FY2024/25 (periods 4 to 6, 29 July to 27 October 2024): the gross amount on each web line, by the Finnish dispatch date. A line keeps the VAT rate of the day the order was placed, so orders placed before 1 September 2024 and dispatched after it are still at 24%.

**It leaves out:** Cancelled and unshipped orders, web test orders, returns.

**Where this is written down:** Metric dictionary, 'Net sales' and 'Web sales and time' (dispatch date); Data quality register, 'The general VAT rate rose from 24% to 25.5% on 1 September 2024'.

**Reference result:**

| fiscal period | web gross incl vat |
|---|---|
| 4 | 156,427.22 |
| 5 | 153,246.24 |
| 6 | 192,906.29 |

**The trap, and what a plausible wrong answer does:**

- Multiplies web net sales by 25.5% for every period, but period 4 was entirely at 24% and period 5 was part 24%, part 25.5%. The result: 4, web gross incl vat comes out as 158,434.53 instead of 156,427.22.

---

### REQ-T29: figures including VAT (VAT)

Finance (FP&A), Marjatta Salonen, received 7 October 2026.

> How much VAT did we charge in the stores in period 5 of FY24/25? Split by VAT rate.

**The reference answer counts:** The VAT charged on sales in the physical stores in period 5 of FY2024/25 (26 August to 22 September 2024), split by VAT rate: the amount on each line is its gross amount minus its net amount. The period straddles the 1 September 2024 change, so 24% applies to the first six days and 25.5% afterwards, alongside the 14% and 10% reduced rates.

**It leaves out:** The web shop, store 999, test articles, returns (the request is for VAT charged on sales).

**Where this is written down:** Metric dictionary, 'Net sales' (including-VAT figures from gross_amount); Data quality register, 'The general VAT rate rose from 24% to 25.5% on 1 September 2024 ... The rate is stored on each line'.

**Reference result:**

| vat rate pct | vat amount |
|---|---|
| 10.00 % | 150.67 |
| 14.00 % | 817.62 |
| 24.00 % | 54,105.20 |
| 25.50 % | 180,017.23 |

**The trap, and what a plausible wrong answer does:**

- Applies 25.5% to all net sales, one row instead of four. It ignores the 24% days and the reduced-rate goods. The result: is missing 10.0, 14.0, 24.0; 25.5, vat amount comes out as 239,375.96 instead of 180,017.23.

---
