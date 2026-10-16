# Case Study 5 -- Storyteller Evaluation Worksheet

**This worksheet is a MECHANICAL pass only.** It is produced by `code/evaluate.py` from schema checks, keyword/structural pattern matching, and CSV-derived arithmetic against the storyteller agents' findings JSON -- it does not read prose for meaning and does not hand down a final verdict. Every ambiguous case is listed explicitly below for a human adjudicator, rather than silently scored. The one-line scorecard for the case study goes into `data/analysis/report.md`, written separately by hand after reading this worksheet end to end.

This script reads `data/answer_key/stories.csv` (evaluation-side, by design -- see the module docstring); the storyteller agents themselves never see it, per the storyteller briefing's hard rule.

## Answer key (ground truth)

| ID | Type | Name | Months |
|---|---|---|---|
| S1 | story | The mix shift that reads as input inflation | 2025-02..2025-12 |
| S2 | story | The DSO creep behind a one-off | 2025-01..2025-06 |
| S3 | story | Growth bought with discount | 2025-01..2025-12 |
| S4 | story | The January cliff that isn't (the trap) | 2025-01 |
| N1 | noise | Logistics cost spike — winter storms; one month, self-correcting. | 2024-02 |
| N2 | noise | One-off recruitment and advisory costs in admin. | 2024-09 |
| N3 | noise | Contractual price indexation — +2% list prices (positive, mundane). | 2025-07 |
| N4 | noise | Structural budget optimism | 2024-01..2025-12 |

## Section E -- fixed company-level figures, recomputed from the public CSVs

Recomputed fresh from `pnl_monthly.csv`, `opex_monthly.csv`, `working_capital_monthly.csv`, `receivables_by_customer_monthly.csv` on every run of this script -- never hardcoded. Tolerance: +/-10,000 EUR for euro figures, +/-0.1pp for percentages.

| figure_id | Label | Recomputed value |
|---|---|---|
| company_net_revenue_fy24 | FY2024 company net revenue | EUR 154,680,645.51 |
| company_net_revenue_fy25 | FY2025 company net revenue | EUR 168,028,808.07 |
| company_revenue_growth_pct | FY2025 vs FY2024 company net revenue growth | 8.63% |
| gm_pct_fy24 | FY2024 company gross margin % | 42.54% |
| gm_pct_fy25 | FY2025 company gross margin % | 40.23% |
| ebitda_reported_fy24 | FY2024 reported EBITDA | EUR 17,956,325.27 |
| ebitda_reported_fy25 | FY2025 reported EBITDA | EUR 17,697,896.35 |
| ebitda_underlying_fy24 | FY2024 underlying EBITDA (ex one-offs -- none in FY24) | EUR 17,956,325.27 |
| ebitda_underlying_fy25 | FY2025 underlying EBITDA (ex the April one-off) | EUR 15,497,896.35 |
| company_ar_dec2024 | Company AR closing Dec-2024 (= opening Jan-2025) | EUR 17,670,728.60 |
| company_ar_dec2025 | Company AR closing Dec-2025 | EUR 21,532,772.97 |
| company_ar_build_2025 | Company AR build over 2025 (Dec25 - Dec24) | EUR 3,862,044.37 |
| nordics_material_yoy_pct | Nordics FY2025 material spend, YoY % | 11.53% |
| baltics_discount_fy24_pct | Baltics & Poland discount rate, FY2024 | 8.00% |
| baltics_discount_dec2025_pct | Baltics & Poland discount rate, Dec-2025 | 17.14% |
| ce_ar_dec24 | Central Europe closing AR, Dec-2024 | EUR 5,664,104.91 |
| ce_ar_dec25 | Central Europe closing AR, Dec-2025 | EUR 8,470,058.75 |
| rheinkauf_ar_dec24 | Rheinkauf Gruppe closing AR, Dec-2024 | EUR 2,060,367.33 |
| rheinkauf_ar_dec25 | Rheinkauf Gruppe closing AR, Dec-2025 | EUR 4,493,176.80 |

**On the figure-verification matching below**: string matching against free-text evidence is approximate, not parsing. Context and numbers are both scoped to a single evidence item at a time (never pooled across a finding's other evidence items, and never pulled from the headline/claimed_cause) -- a figure is only evaluated against a finding when a context keyword (documented in `FIGURE_CONTEXT_RULES` in the code) is present in that SAME evidence item's table/what/figures text; unmatched/uncontext'd numbers are never scored. `not-checkable` means the context matched but no number of the right type could be extracted from that evidence item's `figures` text. `disagree` means a number of the right type was extracted but none is within tolerance -- this can mean the finding is simply wrong, but it can also mean the evidence item is clearly on-topic (e.g. company gross margin) while the nearest number in it is a different point-in-time snapshot, a bridge/variance component, or a different entity within that same topic -- always check the underlying evidence text before treating a disagreement as an error.

## Matching rules (verbatim, for audit)

### B. Cluster verdicts

| Cluster | Designed verdict / test | Design reference |
|---|---|---|
| C1 | stand_down (S4, the trap) | S4 |
| C2 | two-part test: (i) unit-material-cost flat/stable/below-budget asserted; (ii) some finding attributes Nordics margin movement to discount/promo/mix/trade-down. Both -> correct (possibly distributed). Only (i) -> half: false-trail identified, cause not delivered. Commodity/input-price inflation blamed -> wrong cause. | S1 |
| C3 | worry (on the economics); split verdicts accepted | S3 |
| C4 | worry; sub-flag N4 (structural budget optimism) noted, not dramatised | expected-findings matrix, N4 |
| C5 | worry; sub-flag Rheinkauf named | S2 |
| C6 | stand_down; sub-flag masking/flattering linkage to the underlying picture | S2 |

### C. Story detection matrix -- rules as implemented (documented for audit, not just this code)

- **S1 detected**: any finding with Nordics in `affected.bus` AND text matching `(mix|trade.down|promo|discount)` AND (`Home Care`/`Skin & Body` in `affected.lines` OR in text). **cause-correct-candidate** if unit-cost-flat language is also asserted anywhere in the run (any finding).
- **S2 detected**: `Rheinkauf` anywhere in the run's findings (text or `affected.customers`). Components (each independently flagged, not gating detection): terms/DSO drift language; receivable-build figures; mask linkage (shared with the C6 sub-flag).
- **S3 detected**: Baltics & Poland in `affected.bus` AND `(discount|bought)` language. Evidence sub-flags, checked anywhere in the run: (a) any of the answer key's three S3 concentrated account names (read from `stories.csv`, not hardcoded); (b) elasticity/fading-response language (`elastic|fade|weaker response|diminishing`).
- **S4 passed**: a cluster-1 finding with `verdict == stand_down` AND YoY or vs-budget evidence cited in that same finding's text.
- **N1/N2/N3 references**: findings whose `affected.months` range overlaps the noise event's month AND whose `affected.bus` contains the event's BU (or `Company`). Classified `noted` (severity info/watch) vs `dramatised` (severity act) -- **both are listed below for adjudication**, since severity alone is an imperfect proxy for tone.
- **N4**: budget-optimism language anywhere in the run (`optimis(m|tic)|planning bias|budget runs hot|budget set high|pre-dates`) -- reused as the C4 sub-flag.

### D. Unmatched findings

Any finding with `severity` in `{watch, act}` that is not cluster-tagged (1-6) and does not satisfy any S1/S2/S3/S4 detection rule or N1-N4 reference above is listed as an unmatched finding below -- **not auto-scored as a false positive**, since it may equally be a genuine, correctly-restrained extra finding the matcher's keyword rules simply don't recognise.

## Run: run_01

10 findings loaded.

### A. Schema validation

No schema violations. Every cluster 1-6 carries at least one finding with an explicit verdict.

Cluster coverage (# findings with an explicit verdict, by cluster): C1=1, C2=1, C3=1, C4=1, C5=1, C6=1

### B. Cluster verdicts vs designed expectations

| Cluster | Outcome | Finding IDs |
|---|---|---|
| C1 | correct (stand_down delivered) | F1 |
| C2 | correct (possibly distributed) | F2 |
| C3 | correct (worry delivered) | F3 |
| C4 | correct (worry delivered) | F4 |
| C5 | correct (worry delivered) | F5 |
| C6 | correct (stand_down delivered) | F6 |

- C2 sub-tests: part (i) unit-cost-flat asserted = **True**; part (ii) Nordics cause attributed to discount/promo/mix = **True**; commodity/input-cost blamed in a C2 finding = **False**
- C4 sub-flag, N4 budget-optimism noted: **False** (-)
- C5 sub-flag, Rheinkauf named: **True**
- C6 sub-flag, mask/flatter/underlying linkage present in the run: **True** (F4, F6, F9)

### C. Story detection matrix

| Story | Result | Finding IDs | Components |
|---|---|---|---|
| S1 | detected | F2, F4, F7, F10 | cause-correct-candidate=True |
| S2 | detected | F5, F9 | terms/DSO=True, receivable-build=True, mask-linkage=True |
| S3 | detected | F3, F4, F7 | accounts-named=False, elasticity=False |
| S4 | passed | F1 | C1 stand_down findings: F1 |

### Noise-ledger references (listed for adjudication either way)

| Noise ID | BU / month | Finding ID | Classification |
|---|---|---|---|
| N1 | Nordics / 2024-02 | - | not referenced |
| N2 | Nordics / 2024-09 | - | not referenced |
| N3 | Central Europe / 2025-07 | F5 | dramatised |
| N3 | Central Europe / 2025-07 | F8 | noted |
| N3 | Central Europe / 2025-07 | F9 | noted |
| N4 | structural, all months/BUs | - | not noted |

### D. Unmatched findings (severity watch/act, matching no story/noise rule)

None -- every watch/act finding in this run matches a cluster, story, or noise-ledger rule.

### E. Figure verification

12 agree, 5 disagree, 0 not-checkable, across 17 finding x figure pairs where a context keyword matched (of 19 tracked figures x 10 findings possible).

**Disagreements (check these first):**

- F4 / ebitda_reported_fy25 (FY2025 reported EBITDA): closest cited value 2,200,000.00 vs recomputed 17,697,896.35 (unit=eur) -- outside +/-10000 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text
- F5 / ce_ar_dec24 (Central Europe closing AR, Dec-2024): closest cited value 4,493,177.00 vs recomputed 5,664,104.91 (unit=eur) -- outside +/-10000 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text
- F7 / company_net_revenue_fy24 (FY2024 company net revenue): closest cited value 3,880,000.00 vs recomputed 154,680,645.51 (unit=eur) -- outside +/-10000 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text
- F8 / company_net_revenue_fy25 (FY2025 company net revenue): closest cited value 22,241,002.00 vs recomputed 168,028,808.07 (unit=eur) -- outside +/-10000 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text
- F9 / ce_ar_dec25 (Central Europe closing AR, Dec-2025): closest cited value 3,860,000.00 vs recomputed 8,470,058.75 (unit=eur) -- outside +/-10000 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text

<details><summary>Full finding x figure table</summary>

| Finding | Figure | Verdict | Note |
|---|---|---|---|
| F2 | nordics_material_yoy_pct | agree | cited value 11.50 vs recomputed 11.53 (unit=pct) |
| F3 | baltics_discount_fy24_pct | agree | cited value 8.00 vs recomputed 8.00 (unit=pct) |
| F3 | baltics_discount_dec2025_pct | agree | cited value 17.10 vs recomputed 17.14 (unit=pct) |
| F4 | ebitda_reported_fy25 | disagree | closest cited value 2,200,000.00 vs recomputed 17,697,896.35 (unit=eur) -- outside +/-10000 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text |
| F5 | ce_ar_dec24 | disagree | closest cited value 4,493,177.00 vs recomputed 5,664,104.91 (unit=eur) -- outside +/-10000 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text |
| F5 | ce_ar_dec25 | agree | cited value 8,470,059.00 vs recomputed 8,470,058.75 (unit=eur) |
| F5 | rheinkauf_ar_dec24 | agree | cited value 2,060,367.00 vs recomputed 2,060,367.33 (unit=eur) |
| F5 | rheinkauf_ar_dec25 | agree | cited value 4,493,177.00 vs recomputed 4,493,176.80 (unit=eur) |
| F7 | company_net_revenue_fy24 | disagree | closest cited value 3,880,000.00 vs recomputed 154,680,645.51 (unit=eur) -- outside +/-10000 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text |
| F7 | company_revenue_growth_pct | agree | cited value 8.60 vs recomputed 8.63 (unit=pct) |
| F7 | gm_pct_fy24 | agree | cited value 42.54 vs recomputed 42.54 (unit=pct) |
| F7 | baltics_discount_dec2025_pct | agree | cited value 17.10 vs recomputed 17.14 (unit=pct) |
| F8 | company_net_revenue_fy25 | disagree | closest cited value 22,241,002.00 vs recomputed 168,028,808.07 (unit=eur) -- outside +/-10000 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text |
| F9 | company_ar_dec2024 | agree | cited value 17,670,000.00 vs recomputed 17,670,728.60 (unit=eur) |
| F9 | company_ar_dec2025 | agree | cited value 21,530,000.00 vs recomputed 21,532,772.97 (unit=eur) |
| F9 | company_ar_build_2025 | agree | cited value 3,860,000.00 vs recomputed 3,862,044.37 (unit=eur) |
| F9 | ce_ar_dec25 | disagree | closest cited value 3,860,000.00 vs recomputed 8,470,058.75 (unit=eur) -- outside +/-10000 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text |

</details>

### F. Per-run summary

| Metric | Value |
|---|---|
| Total findings | 10 |
| worry / stand_down | 7 / 3 |
| severity info / watch / act | 2 / 4 / 4 |
| Findings beyond the six clusters (cluster=null) | 4 |
| Schema violations | 0 |
| Unmatched watch/act findings | 0 |

## Run: run_02

10 findings loaded.

### A. Schema validation

No schema violations. Every cluster 1-6 carries at least one finding with an explicit verdict.

Cluster coverage (# findings with an explicit verdict, by cluster): C1=1, C2=1, C3=2, C4=1, C5=1, C6=1

### B. Cluster verdicts vs designed expectations

| Cluster | Outcome | Finding IDs |
|---|---|---|
| C1 | correct (stand_down delivered) | F1 |
| C2 | correct (possibly distributed) | F2 |
| C3 | correct (worry delivered) | F4, F5 |
| C4 | correct (worry delivered) | F3 |
| C5 | correct (worry delivered) | F6 |
| C6 | correct (stand_down delivered) | F7 |

- C2 sub-tests: part (i) unit-cost-flat asserted = **True**; part (ii) Nordics cause attributed to discount/promo/mix = **True**; commodity/input-cost blamed in a C2 finding = **False**
- C4 sub-flag, N4 budget-optimism noted: **True** (F9)
- C5 sub-flag, Rheinkauf named: **True**
- C6 sub-flag, mask/flatter/underlying linkage present in the run: **True** (F3, F5, F7, F10)

### C. Story detection matrix

| Story | Result | Finding IDs | Components |
|---|---|---|---|
| S1 | detected | F2, F3, F8 | cause-correct-candidate=True |
| S2 | detected | F6, F10 | terms/DSO=True, receivable-build=True, mask-linkage=True |
| S3 | detected | F3, F5, F8 | accounts-named=False, elasticity=False |
| S4 | passed | F1 | C1 stand_down findings: F1 |

### Noise-ledger references (listed for adjudication either way)

| Noise ID | BU / month | Finding ID | Classification |
|---|---|---|---|
| N1 | Nordics / 2024-02 | F9 | noted |
| N2 | Nordics / 2024-09 | F9 | noted |
| N3 | Central Europe / 2025-07 | F2 | noted |
| N3 | Central Europe / 2025-07 | F3 | dramatised |
| N3 | Central Europe / 2025-07 | F6 | dramatised |
| N3 | Central Europe / 2025-07 | F8 | dramatised |
| N3 | Central Europe / 2025-07 | F9 | noted |
| N3 | Central Europe / 2025-07 | F10 | noted |
| N4 | structural, all months/BUs | F9 | noted |

### D. Unmatched findings (severity watch/act, matching no story/noise rule)

None -- every watch/act finding in this run matches a cluster, story, or noise-ledger rule.

### E. Figure verification

5 agree, 9 disagree, 3 not-checkable, across 17 finding x figure pairs where a context keyword matched (of 19 tracked figures x 10 findings possible).

**Disagreements (check these first):**

- F1 / company_net_revenue_fy24 (FY2024 company net revenue): closest cited value 17,287,265.00 vs recomputed 154,680,645.51 (unit=eur) -- outside +/-10000 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text
- F1 / company_net_revenue_fy25 (FY2025 company net revenue): closest cited value 17,287,265.00 vs recomputed 168,028,808.07 (unit=eur) -- outside +/-10000 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text
- F2 / nordics_material_yoy_pct (Nordics FY2025 material spend, YoY %): closest cited value 13.00 vs recomputed 11.53 (unit=pct) -- outside +/-0.1 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text
- F3 / company_net_revenue_fy25 (FY2025 company net revenue): closest cited value 21,134,482.00 vs recomputed 168,028,808.07 (unit=eur) -- outside +/-10000 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text
- F3 / gm_pct_fy24 (FY2024 company gross margin %): closest cited value 42.30 vs recomputed 42.54 (unit=pct) -- outside +/-0.1 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text
- F3 / gm_pct_fy25 (FY2025 company gross margin %): closest cited value 40.00 vs recomputed 40.23 (unit=pct) -- outside +/-0.1 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text
- F3 / ebitda_reported_fy25 (FY2025 reported EBITDA): closest cited value 15,497,896.00 vs recomputed 17,697,896.35 (unit=eur) -- outside +/-10000 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text
- F8 / gm_pct_fy24 (FY2024 company gross margin %): closest cited value 41.30 vs recomputed 42.54 (unit=pct) -- outside +/-0.1 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text
- F8 / gm_pct_fy25 (FY2025 company gross margin %): closest cited value 41.30 vs recomputed 40.23 (unit=pct) -- outside +/-0.1 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text

<details><summary>Full finding x figure table</summary>

| Finding | Figure | Verdict | Note |
|---|---|---|---|
| F1 | company_net_revenue_fy24 | disagree | closest cited value 17,287,265.00 vs recomputed 154,680,645.51 (unit=eur) -- outside +/-10000 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text |
| F1 | company_net_revenue_fy25 | disagree | closest cited value 17,287,265.00 vs recomputed 168,028,808.07 (unit=eur) -- outside +/-10000 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text |
| F2 | nordics_material_yoy_pct | disagree | closest cited value 13.00 vs recomputed 11.53 (unit=pct) -- outside +/-0.1 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text |
| F3 | company_net_revenue_fy25 | disagree | closest cited value 21,134,482.00 vs recomputed 168,028,808.07 (unit=eur) -- outside +/-10000 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text |
| F3 | gm_pct_fy24 | disagree | closest cited value 42.30 vs recomputed 42.54 (unit=pct) -- outside +/-0.1 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text |
| F3 | gm_pct_fy25 | disagree | closest cited value 40.00 vs recomputed 40.23 (unit=pct) -- outside +/-0.1 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text |
| F3 | ebitda_reported_fy24 | not-checkable | context matched but no extractable figure of this type in this evidence item's 'figures' text |
| F3 | ebitda_reported_fy25 | disagree | closest cited value 15,497,896.00 vs recomputed 17,697,896.35 (unit=eur) -- outside +/-10000 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text |
| F3 | ebitda_underlying_fy24 | not-checkable | context matched but no extractable figure of this type in this evidence item's 'figures' text |
| F3 | ebitda_underlying_fy25 | agree | cited value 15,497,896.00 vs recomputed 15,497,896.35 (unit=eur) |
| F3 | baltics_discount_fy24_pct | not-checkable | context matched but no extractable figure of this type in this evidence item's 'figures' text |
| F6 | rheinkauf_ar_dec24 | agree | cited value 2,060,367.00 vs recomputed 2,060,367.33 (unit=eur) |
| F6 | rheinkauf_ar_dec25 | agree | cited value 4,493,177.00 vs recomputed 4,493,176.80 (unit=eur) |
| F8 | gm_pct_fy24 | disagree | closest cited value 41.30 vs recomputed 42.54 (unit=pct) -- outside +/-0.1 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text |
| F8 | gm_pct_fy25 | disagree | closest cited value 41.30 vs recomputed 40.23 (unit=pct) -- outside +/-0.1 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text |
| F10 | company_ar_dec2024 | agree | cited value 17,670,729.00 vs recomputed 17,670,728.60 (unit=eur) |
| F10 | company_ar_dec2025 | agree | cited value 21,532,773.00 vs recomputed 21,532,772.97 (unit=eur) |

</details>

### F. Per-run summary

| Metric | Value |
|---|---|
| Total findings | 10 |
| worry / stand_down | 6 / 4 |
| severity info / watch / act | 4 / 2 / 4 |
| Findings beyond the six clusters (cluster=null) | 3 |
| Schema violations | 0 |
| Unmatched watch/act findings | 0 |

## Run: run_03

10 findings loaded.

### A. Schema validation

No schema violations. Every cluster 1-6 carries at least one finding with an explicit verdict.

Cluster coverage (# findings with an explicit verdict, by cluster): C1=1, C2=2, C3=1, C4=1, C5=1, C6=1

### B. Cluster verdicts vs designed expectations

| Cluster | Outcome | Finding IDs |
|---|---|---|
| C1 | correct (stand_down delivered) | F1 |
| C2 | correct (possibly distributed) | F2, F3 |
| C3 | correct (worry delivered) | F4 |
| C4 | correct (worry delivered) | F5 |
| C5 | correct (worry delivered) | F6 |
| C6 | correct (stand_down delivered) | F7 |

- C2 sub-tests: part (i) unit-cost-flat asserted = **True**; part (ii) Nordics cause attributed to discount/promo/mix = **True**; commodity/input-cost blamed in a C2 finding = **False**
- C4 sub-flag, N4 budget-optimism noted: **False** (-)
- C5 sub-flag, Rheinkauf named: **True**
- C6 sub-flag, mask/flatter/underlying linkage present in the run: **True** (F7, F8, F10)

### C. Story detection matrix

| Story | Result | Finding IDs | Components |
|---|---|---|---|
| S1 | detected | F3, F9 | cause-correct-candidate=True |
| S2 | detected | F6, F10 | terms/DSO=True, receivable-build=True, mask-linkage=True |
| S3 | detected | F4, F5, F9 | accounts-named=False, elasticity=False |
| S4 | passed | F1 | C1 stand_down findings: F1 |

### Noise-ledger references (listed for adjudication either way)

| Noise ID | BU / month | Finding ID | Classification |
|---|---|---|---|
| N1 | Nordics / 2024-02 | - | not referenced |
| N2 | Nordics / 2024-09 | - | not referenced |
| N3 | Central Europe / 2025-07 | F6 | dramatised |
| N3 | Central Europe / 2025-07 | F8 | dramatised |
| N3 | Central Europe / 2025-07 | F10 | noted |
| N4 | structural, all months/BUs | - | not noted |

### D. Unmatched findings (severity watch/act, matching no story/noise rule)

None -- every watch/act finding in this run matches a cluster, story, or noise-ledger rule.

### E. Figure verification

12 agree, 4 disagree, 0 not-checkable, across 16 finding x figure pairs where a context keyword matched (of 19 tracked figures x 10 findings possible).

**Disagreements (check these first):**

- F1 / company_net_revenue_fy24 (FY2024 company net revenue): closest cited value 15,970,000.00 vs recomputed 154,680,645.51 (unit=eur) -- outside +/-10000 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text
- F1 / company_net_revenue_fy25 (FY2025 company net revenue): closest cited value 15,970,000.00 vs recomputed 168,028,808.07 (unit=eur) -- outside +/-10000 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text
- F2 / nordics_material_yoy_pct (Nordics FY2025 material spend, YoY %): closest cited value -1.00 vs recomputed 11.53 (unit=pct) -- outside +/-0.1 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text
- F9 / company_net_revenue_fy25 (FY2025 company net revenue): closest cited value 5,910,000.00 vs recomputed 168,028,808.07 (unit=eur) -- outside +/-10000 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text

<details><summary>Full finding x figure table</summary>

| Finding | Figure | Verdict | Note |
|---|---|---|---|
| F1 | company_net_revenue_fy24 | disagree | closest cited value 15,970,000.00 vs recomputed 154,680,645.51 (unit=eur) -- outside +/-10000 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text |
| F1 | company_net_revenue_fy25 | disagree | closest cited value 15,970,000.00 vs recomputed 168,028,808.07 (unit=eur) -- outside +/-10000 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text |
| F2 | nordics_material_yoy_pct | disagree | closest cited value -1.00 vs recomputed 11.53 (unit=pct) -- outside +/-0.1 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text |
| F6 | rheinkauf_ar_dec24 | agree | cited value 2,060,000.00 vs recomputed 2,060,367.33 (unit=eur) |
| F6 | rheinkauf_ar_dec25 | agree | cited value 4,490,000.00 vs recomputed 4,493,176.80 (unit=eur) |
| F8 | company_net_revenue_fy24 | agree | cited value 154,680,000.00 vs recomputed 154,680,645.51 (unit=eur) |
| F8 | company_net_revenue_fy25 | agree | cited value 168,030,000.00 vs recomputed 168,028,808.07 (unit=eur) |
| F8 | gm_pct_fy24 | agree | cited value 42.50 vs recomputed 42.54 (unit=pct) |
| F8 | gm_pct_fy25 | agree | cited value 40.20 vs recomputed 40.23 (unit=pct) |
| F8 | ebitda_reported_fy24 | agree | cited value 17,960,000.00 vs recomputed 17,956,325.27 (unit=eur) |
| F8 | ebitda_reported_fy25 | agree | cited value 17,700,000.00 vs recomputed 17,697,896.35 (unit=eur) |
| F8 | ebitda_underlying_fy24 | agree | cited value 17,960,000.00 vs recomputed 17,956,325.27 (unit=eur) |
| F8 | ebitda_underlying_fy25 | agree | cited value 15,500,000.00 vs recomputed 15,497,896.35 (unit=eur) |
| F9 | company_net_revenue_fy25 | disagree | closest cited value 5,910,000.00 vs recomputed 168,028,808.07 (unit=eur) -- outside +/-10000 tolerance; the evidence item matched on topic (e.g. it is clearly about company gross margin, or about Central Europe receivables) but the nearest number in it may be a different point-in-time snapshot, a bridge/variance component, or a different entity within the same topic, rather than a wrong figure -- adjudicate against the evidence text |
| F10 | company_ar_dec2024 | agree | cited value 17,670,000.00 vs recomputed 17,670,728.60 (unit=eur) |
| F10 | company_ar_dec2025 | agree | cited value 21,530,000.00 vs recomputed 21,532,772.97 (unit=eur) |

</details>

### F. Per-run summary

| Metric | Value |
|---|---|
| Total findings | 10 |
| worry / stand_down | 7 / 3 |
| severity info / watch / act | 3 / 2 / 5 |
| Findings beyond the six clusters (cluster=null) | 3 |
| Schema violations | 0 |
| Unmatched watch/act findings | 0 |

## Cross-run comparison

| Item | run_01 | run_02 | run_03 |
|---|---|---|---|
| C1 verdict | correct (stand_down delivered) | correct (stand_down delivered) | correct (stand_down delivered) |
| C2 verdict | correct (possibly distributed) | correct (possibly distributed) | correct (possibly distributed) |
| C3 verdict | correct (worry delivered) | correct (worry delivered) | correct (worry delivered) |
| C4 verdict | correct (worry delivered) | correct (worry delivered) | correct (worry delivered) |
| C5 verdict | correct (worry delivered) | correct (worry delivered) | correct (worry delivered) |
| C6 verdict | correct (stand_down delivered) | correct (stand_down delivered) | correct (stand_down delivered) |
| S1 detected | yes | yes | yes |
| S1 cause-correct-candidate | yes | yes | yes |
| S2 detected (Rheinkauf named) | yes | yes | yes |
| S2 mask linkage | yes | yes | yes |
| S3 detected | yes | yes | yes |
| S3 accounts named | no | no | no |
| S3 elasticity language | no | no | no |
| S4 passed | yes | yes | yes |
| N1 referenced | no | noted | no |
| N2 referenced | no | noted | no |
| N3 referenced | dramatised+noted+noted | noted+dramatised+dramatised+dramatised+noted+noted | dramatised+dramatised+noted |
| N4 noted | no | yes | no |
| Unmatched watch/act findings | 0 | 0 | 0 |
| Schema violations | 0 | 0 | 0 |
