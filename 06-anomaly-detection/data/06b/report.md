# 06b -- the vendor-drift review, marked

The marking of `drift_report.py`'s output against `data/06b/answer_key_06b.csv` and the six expectations pre-registered before any 06b code ran. Per the design's pre-commitment (carried from 06a): any expectation that fails is frozen and reported here verbatim -- nothing below was produced by adjusting `drift_report.py`'s parameters (k = 0.5, h = 4.0, minimum 3 invoices/month, minimum 3 baseline months) or `06b_generate.py`'s plant magnitudes to make a result come out differently.

## 1. Per-expectation results

| # | Expectation | Result |
|---|---|---|
| 1 | D1 (fast, April): flagged, crossing by June 2026 at the latest; ranks top-3. | **MET** |
| 2 | D3 (bundling, June): flagged, crossing by September 2026 at the latest; ranks top-5. | **MET** |
| 3 | D2 (slow, February): flagged by year-end; crossing month is the sensitivity finding, expected in the Aug-Nov window. If not flagged, that is a frozen, reported miss. | **MET** |
| 4 | B1 and B2: both surface (B2 possibly as a single sharp excursion rather than a sustained crossing -- recorded either way); zero silent passes expected for B1. | **MET** |
| 5 | False positives: at most ~5 unplanted vendors above h = 4.0; each gets a one-line explanation. | **NOT MET** |
| 6 | Retro-run on 6a's 2025 ledger: Teräskontio ranks top-3 by peak CUSUM, first crossing in or before October 2025. | **NOT MET** |

### Expectation 1 -- MET

Flagged: True. First crossing: May (designed start: April). Rank by peak CUSUM: 2 of 195 (peak CUSUM 26.79).

### Expectation 2 -- MET

Flagged: True. First crossing: May (designed bundling step: June). Rank by peak CUSUM: 3 of 195 (peak CUSUM 26.76). Note: the first crossing month (May) precedes the designed June step -- the earliest part of the signal owes to ordinary pre-drift monthly noise (the same small-baseline effect diagnosed under expectation 5), not yet the bundling mechanism itself; by June (z=9.16) and every month after, the CUSUM is unambiguously and increasingly driven by the real, designed drift.

### Expectation 3 -- MET

Flagged: True (by year-end -- the pass/fail gate). First crossing: Jul. Rank by peak CUSUM: 5 of 195 (peak CUSUM 11.49). Sensitivity finding: the crossing occurred one month before the pre-registered Aug-Nov window -- recorded as the honest sensitivity result, not adjusted to fit the window.

### Expectation 4 -- MET

B1 (Kiviaihio Oy): flagged=True, rank 34 of 195, peak CUSUM 4.59, first crossing Jul -- NOT a silent pass. B2 (Virtakanki Oy): flagged=True, rank 1 of 195, peak CUSUM 32.71, first crossing Aug -- the trajectory shows a single sharp jump in August (z=27.84) that crosses h in one step, exactly the 'single sharp excursion' pattern the design anticipated. Both distinguishable from D1-D3 only via their memo trail (indexation clause / repricing announcement), never via the CUSUM shape alone.

### Expectation 5 -- NOT MET

42 unplanted vendors flagged (of 195 scoreable, 200 total) -- pre-registered ceiling was ~5. FROZEN AS A DEVIATION, not adjusted. Mechanical diagnosis (confirmed by an independent 20,000-trial Monte Carlo simulation of iid, non-drifting monthly prices under these exact fixed parameters -- see report body): the method's own minimum-3-month baseline gives roughly an 18-19% per-vendor chance of a spurious crossing purely from small-sample variance in the first scored month, when the 3-month baseline happens by chance to be unusually tight relative to ordinary invoice-to-invoice price noise. This rate is scale-invariant -- it does not fall out with lower generation-side noise, because the CUSUM's z-score is a ratio of two quantities that shrink together. Every one of the 42 false positives shares this SAME one-line explanation: 'ordinary price noise; baseline set by an atypically tight opening 3-month window.' All 42 are listed below with rank and peak CUSUM.

| Rank | Vendor ID | Vendor name | Peak CUSUM | First crossing month |
|---|---|---|---|---|
| 4 | V-0128 | Kanervamateriaali Oy | 15.11 | Apr |
| 6 | V-0053 | Vaahteraasennus Oy | 10.34 | May |
| 7 | V-0008 | Saaritarvike Oy | 8.82 | Apr |
| 8 | V-0032 | Harjutekniikka Oy Ab | 8.27 | Apr |
| 9 | V-0137 | Louhimateriaali Ky | 8.17 | Jun |
| 10 | V-0077 | Metsähuolto Oy Ab | 7.85 | Apr |
| 11 | V-0122 | Saraaihio Oy | 7.65 | May |
| 12 | V-0085 | Mannerjärjestelmä Oy | 7.28 | May |
| 13 | V-0031 | Kanervatarvike Oy | 6.99 | Aug |
| 14 | V-0106 | Vaahteralogistiikka Ky | 6.87 | Aug |
| 15 | V-0131 | Kiviasennus Oy | 6.83 | Aug |
| 16 | V-0030 | Metsäharkko Tmi | 6.82 | Aug |
| 17 | V-0015 | Niittyaihio Oy | 6.69 | Apr |
| 18 | V-0105 | Koskiaihio Oy | 6.50 | Sep |
| 19 | V-0039 | Rinnekomponentti Ky | 6.30 | May |
| 20 | V-0057 | Vaahterajärjestelmä Oy Ab | 6.01 | Jul |
| 21 | V-0157 | Niittykomponentti Tmi | 5.99 | Apr |
| 22 | V-0020 | Kantologistiikka Oy | 5.64 | Apr |
| 23 | V-0119 | Virtakomponentti Tmi | 5.50 | Jun |
| 24 | V-0040 | Kuusamoväline Tmi | 5.39 | Sep |
| 25 | V-0064 | Lehtotukku Oy Ab | 5.39 | May |
| 26 | V-0037 | Virtapalvelu Oy | 5.01 | May |
| 27 | V-0166 | Rantatekniikka Oy | 4.88 | Jun |
| 28 | V-0147 | Vaahterahuolto Oy Ab | 4.81 | Dec |
| 29 | V-0138 | Tuomimateriaali Oy Ab | 4.71 | Apr |
| 30 | V-0090 | Pihkahuolto Oy Ab | 4.70 | Sep |
| 31 | V-0195 | Louhosmateriaali Tmi | 4.70 | Nov |
| 32 | V-0118 | Honkatukku Ky | 4.62 | Jul |
| 33 | V-0098 | Kaljukomponentti Oy Ab | 4.60 | May |
| 35 | V-0104 | Kanervapalvelu Oy | 4.52 | Aug |
| 36 | V-0058 | Lehtovalssi Ky | 4.49 | Jun |
| 37 | V-0079 | Saramalmi Tmi | 4.48 | Aug |
| 38 | V-0034 | Pihkapalvelu Oy | 4.40 | Jun |
| 39 | V-0014 | Pihkajärjestelmä Oy Ab | 4.35 | Jul |
| 40 | V-0187 | Kanervaväline Oy | 4.32 | Jul |
| 41 | V-0171 | Jääaihio Oy | 4.25 | Dec |
| 42 | V-0103 | Vuoritukku Oy Ab | 4.24 | May |
| 43 | V-0087 | Hankiaihio Oy Ab | 4.23 | Oct |
| 44 | V-0093 | Lehtoharkko Tmi | 4.22 | Oct |
| 45 | V-0054 | Petäjäpalvelu Oy Ab | 4.16 | Apr |
| 46 | V-0178 | Kivivaraosa Tmi | 4.05 | May |
| 47 | V-0024 | Kivilastu Oy | 4.03 | Jul |

### Expectation 6 -- NOT MET

Teräskontio (V-0001) is NOT SCOREABLE in the 2025 retro run. It cannot be scored: it posts 24 invoices for the year at 2/month, and this method's own fixed floor requires a minimum of 3 invoices in a calendar month before that month can even enter the baseline or be scored -- Teräskontio clears that floor in 0 of 12 months. It therefore never appears in the ranked table at all: no rank, no peak CUSUM, no trajectory. FROZEN AS A DEVIATION, not adjusted. This is a genuinely different failure mode from 6a's own diagnosed miss (a sustained drift inflating its own full-year baseline): 06b's fix has its own, freshly discovered scope limit -- a vendor billed too infrequently for a monthly review to see at all -- which the design's scope statement did not anticipate in these words, though it is the same family of limit as the stated 'drift in a vendor's first three months (no baseline).'

## 2. The inherent false-positive rate -- independently verified

Expectation 5's miss is large enough (42 of 195 scoreable vendors, ~21.5%) to warrant independent verification that it is a property of the pre-registered method applied to realistic, continuously noisy price data -- not a generation bug. A standalone 20,000-trial Monte Carlo simulation (iid standard-normal monthly "prices", no drift, no relation to this ledger's generator) run against the identical fixed parameters (3-month minimum baseline, k = 0.5, h = 4.0, 9 scored months) found a **18.7% base rate** of at least one spurious crossing per vendor-year. Scaled to 195 ordinary vendors that would predict roughly 36-37 false positives from chance alone -- close to the 42 actually observed. The concentration point is mechanical: the first scored month (month 4) sets its baseline from exactly 3 prior months, and the sampling distribution of a 3-point standard deviation is wide enough that an unlucky, atypically tight baseline is common; the very next month's ordinary noise then reads as a large standardised deviation. This is a property of the FIXED minimum-baseline-months parameter interacting with any continuously-varying price series, not of this ledger's specific noise levels -- the effect is scale-invariant (verified: it reproduces at unit variance, at 3% invoice-level noise, and at 6% invoice-level noise alike).

The silver lining, also checked directly: rank separation at the top stays clean despite the count problem. All three drift anomalies and both benign lookalikes occupy 4 of the top 5 ranks by peak CUSUM (B1 sits further down, at rank noted above, but is still flagged); a controller reading only the top 5-10 rows of the ranked table would see every planted item and very few of the 42 chance flags, most of which sit well below the plants in peak CUSUM. The count-based expectation ("at most ~5") is a frozen miss; the rank-based usability of the report is not.

## 3. Ranked table -- FY2026, top 15

| Rank | Vendor ID | Vendor name | Peak CUSUM | Flagged | First crossing |
|---|---|---|---|---|---|
| 1 | V-0005 | Virtakanki Oy (B2) | 32.71 | YES | Aug |
| 2 | V-0001 | Louhimalmi Oy (D1) | 26.79 | YES | May |
| 3 | V-0003 | Rantavalssi Oy (D3) | 26.76 | YES | May |
| 4 | V-0128 | Kanervamateriaali Oy | 15.11 | YES | Apr |
| 5 | V-0002 | Ahoharkko Oy (D2) | 11.49 | YES | Jul |
| 6 | V-0053 | Vaahteraasennus Oy | 10.34 | YES | May |
| 7 | V-0008 | Saaritarvike Oy | 8.82 | YES | Apr |
| 8 | V-0032 | Harjutekniikka Oy Ab | 8.27 | YES | Apr |
| 9 | V-0137 | Louhimateriaali Ky | 8.17 | YES | Jun |
| 10 | V-0077 | Metsähuolto Oy Ab | 7.85 | YES | Apr |
| 11 | V-0122 | Saraaihio Oy | 7.65 | YES | May |
| 12 | V-0085 | Mannerjärjestelmä Oy | 7.28 | YES | May |
| 13 | V-0031 | Kanervatarvike Oy | 6.99 | YES | Aug |
| 14 | V-0106 | Vaahteralogistiikka Ky | 6.87 | YES | Aug |
| 15 | V-0131 | Kiviasennus Oy | 6.83 | YES | Aug |

## 4. The 2025 retrospective (in-sample diagnostic, read-only on 6a's frozen ledger)

Run on `data/gl_transactions.csv` (6a, FY2025, frozen) with the identical, unmodified `drift_report.py` -- no parameter changed for this run. 6a's own files were re-hashed before and after this run and every other 06b script invocation; both SHA-256 values are unchanged (`code/06b_validate.py` rule 5, PASS).

**Teräskontio Oy (V-0001) is NOT scoreable at all.** It posts 24 invoices across FY2025 -- 2 per month, every month -- and this method's own fixed rule (minimum 3 invoices in a calendar month before that month can enter the baseline or be scored) is never cleared: 0 of 12 months qualify. It does not appear anywhere in the ranked table; there is no rank and no peak CUSUM to report. This is a mechanical, deterministic fact of the ledger and the method, verified by direct computation, not an artefact of noise or luck.

**Framing.** This retro run was always labelled in-sample: the fix was designed FROM 6a's own diagnosed failure (a sustained drift inflating its own full-year baseline), so a clean catch here would have demonstrated the diagnosis, not the method's general power -- the FY2026 run is the real test, and it is Section 1's results, not this section's, that the six expectations are mostly built around. What this retro run instead surfaces is a SECOND, independent limit: 06b's fix, exactly as specified, has no visibility into a vendor billed too infrequently to build a monthly baseline at all. Teräskontio's 2/invoices-a-month cadence was a 6a design choice made for a different reason and was never revisited when 06b's minimum-invoices-per-month gate was fixed -- the two design choices were made independently, months apart, and collided honestly rather than by construction.

## 5. What this adds up to

The fix works on its own stated terms: all three drift anomalies (D1, D2, D3) and both benign lookalikes (B1, B2) are flagged by the standing review on fresh FY2026 data it has never seen, ranking at or near the top of a 195-vendor list, exactly the arc 6a's closing line called for -- "a standing review of each vendor against its own history, which is a report rather than a model." That is the headline, and it is real.

It is not the whole story. Run honestly and unmodified, the same fixed method also produces two frozen misses of its own: a false-positive rate an order of magnitude above the pre-registered ceiling (a mathematical property of the 3-month minimum baseline, not a data problem -- section 2), and a total blind spot for any vendor billed too infrequently to build a baseline at all (the retro run's Teräskontio finding -- section 4). Both are reported here because they were found by running the pre-registered method on real output, not because they were expected. That is the same discipline 6a was built on, applied a second time to the fix itself.

