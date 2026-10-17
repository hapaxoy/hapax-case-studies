<!-- table:headline -->
| Cell | Correct runs | Share | 95% interval (resampling the 60 requests) | Same, keyword rules only |
|---|---|---|---|---|
| Sonnet S | 149 of 300 | 49.7% | 37.7% to 61.7% | 149 |
| Sonnet D | 298 of 300 | 99.3% | 98.0% to 100.0% | 298 |
| Sonnet L | 295 of 300 | 98.3% | 95.3% to 100.0% | 295 |
| Sonnet L- | 297 of 300 | 99.0% | 97.7% to 100.0% | 297 |
| Haiku S | 89 of 300 | 29.7% | 19.7% to 40.0% | 89 |
| Haiku L | 237 of 300 | 79.0% | 71.0% to 86.3% | 233 |

<!-- table:by_class -->
| Trap class | Requests | Sonnet S | Sonnet D | Sonnet L | Sonnet L- | Haiku S | Haiku L |
|---|---|---|---|---|---|---|---|
| company definition | 12 | 19/60 (32%; 10%-55%) | 60/60 (100%; 100%-100%) | 60/60 (100%; 100%-100%) | 60/60 (100%; 100%-100%) | 12/60 (20%; 5%-38%) | 52/60 (87%; 73%-97%) |
| fiscal calendar | 11 | 12/55 (22%; 5%-40%) | 55/55 (100%; 100%-100%) | 55/55 (100%; 100%-100%) | 55/55 (100%; 100%-100%) | 12/55 (22%; 5%-42%) | 49/55 (89%; 80%-96%) |
| scd | 6 | 0/30 | 30/30 | 30/30 | 30/30 | 0/30 | 26/30 |
| migration | 4 | 0/20 | 20/20 | 20/20 | 20/20 | 0/20 | 17/20 |
| time zone | 3 | 5/15 | 15/15 | 15/15 | 15/15 | 0/15 | 15/15 |
| exclusions | 5 | 23/25 | 25/25 | 25/25 | 24/25 | 4/25 | 18/25 |
| fan out | 5 | 5/25 | 23/25 | 21/25 | 24/25 | 6/25 | 14/25 |
| semi additive | 3 | 11/15 | 15/15 | 15/15 | 15/15 | 2/15 | 9/15 |
| vat | 4 | 10/20 | 20/20 | 19/20 | 19/20 | 1/20 | 11/20 |
| ambiguous | 5 | 13/25 | 23/25 | 21/25 | 24/25 | 13/25 | 17/25 |
| override | 4 | 3/20 | 20/20 | 20/20 | 20/20 | 0/20 | 15/20 |
| undocumented | 4 | 5/20 | 20/20 | 20/20 | 20/20 | 0/20 | 8/20 |
| clean | 14 | 70/70 (100%; 100%-100%) | 70/70 (100%; 100%-100%) | 70/70 (100%; 100%-100%) | 70/70 (100%; 100%-100%) | 59/70 (84%; 67%-97%) | 60/70 (86%; 67%-100%) |

<!-- table:trapped_vs_clean -->
| Requests | Sonnet S | Sonnet D | Sonnet L | Sonnet L- | Haiku S | Haiku L | Runs per cell |
|---|---|---|---|---|---|---|---|
| trapped (46 requests) | 79 | 228 | 225 | 227 | 30 | 177 | 230 |
| clean (14 requests) | 70 | 70 | 70 | 70 | 59 | 60 | 70 |

<!-- table:attribution -->
| Wrong runs, by the naive variant they match | Sonnet S | Sonnet D | Sonnet L | Sonnet L- | Haiku S | Haiku L |
|---|---|---|---|---|---|---|
| fiscal calendar | 3 | 0 | 0 | 0 | 0 | 0 |
| migration | 0 | 0 | 0 | 0 | 4 | 0 |
| other | 140 | 2 | 4 | 2 | 204 | 54 |
| percent as fraction | 0 | 0 | 1 | 1 | 1 | 0 |
| published without warning | 0 | 0 | 0 | 0 | 0 | 7 |
| scd | 6 | 0 | 0 | 0 | 0 | 2 |
| semi additive | 0 | 0 | 0 | 0 | 2 | 0 |
| time zone | 2 | 0 | 0 | 0 | 0 | 0 |
| total wrong | 151 | 2 | 5 | 3 | 211 | 63 |

<!-- table:consistency -->
| Measure | Sonnet S | Sonnet D | Sonnet L | Sonnet L- | Haiku S | Haiku L |
|---|---|---|---|---|---|---|
| All five runs return the same result (requests of 60) | 33 | 57 | 54 | 53 | 16 | 29 |
| Correct in all five runs (requests of 60) | 25 | 59 | 58 | 57 | 11 | 32 |
| Paraphrase pairs with the same majority result (of 10) | 9 | 10 | 10 | 10 | 4 | 9 |

<!-- table:definitions -->
| Company-definition requests (12 requests, 60 runs) | Sonnet S | Sonnet D | Sonnet L | Sonnet L- | Haiku S | Haiku L |
|---|---|---|---|---|---|---|
| Correct | 19 | 60 | 60 | 60 | 12 | 52 |
| Result equals a naive variant of the request | 6 | 0 | 0 | 0 | 0 | 1 |

<!-- table:override -->
| Override requests (4 requests, 20 runs) | Sonnet S | Sonnet D | Sonnet L | Sonnet L- | Haiku S | Haiku L |
|---|---|---|---|---|---|---|
| Correct (follows the request) | 3 | 20 | 20 | 20 | 0 | 15 |
| Company default applied against the request | 0 | 0 | 0 | 0 | 0 | 0 |

<!-- table:undocumented -->
| Undocumented-issue requests (4 requests, 20 runs) | Sonnet S | Sonnet D | Sonnet L | Sonnet L- | Haiku S | Haiku L |
|---|---|---|---|---|---|---|
| (a) repaired: the incident-free number | 5 | 20 | 20 | 20 | 0 | 4 |
| (b) published number, problem named in caveats (after adjudication) | 0 | 0 | 0 | 0 | 0 | 4 |
| (b) published number, keyword rule alone | 0 | 0 | 0 | 0 | 0 | 0 |
| (c) published number, no usable warning | 0 | 0 | 0 | 0 | 0 | 7 |
| Right under fix or flag, (a) + (b) | 5 | 20 | 20 | 20 | 0 | 8 |
| REQ-T12: right (of 5) | 5 | 5 | 5 | 5 | 0 | 0 |
| REQ-T16: right (of 5) | 0 | 5 | 5 | 5 | 0 | 4 |
| REQ-T42: right (of 5) | 0 | 5 | 5 | 5 | 0 | 4 |
| REQ-T55: right (of 5) | 0 | 5 | 5 | 5 | 0 | 0 |

<!-- table:tokens -->
| Agent tokens per run | Sonnet S | Sonnet D | Sonnet L | Sonnet L- | Haiku S | Haiku L |
|---|---|---|---|---|---|---|
| Median | 71,548 | 80,897 | 85,100 | 87,236 | 49,451 | 58,982 |
| Quartiles | 67,085 to 77,101 | 78,922 to 83,229 | 80,444 to 90,453 | 82,091 to 91,651 | 47,591 to 51,278 | 54,640 to 62,662 |
| Range | 59,541 to 100,301 | 74,478 to 97,568 | 65,247 to 105,540 | 65,091 to 107,586 | 44,336 to 70,086 | 45,890 to 79,643 |
| Total, 300 runs | 21.9M | 24.4M | 25.5M | 25.9M | 15.0M | 17.7M |
| Total tokens per correct run | 146,656 | 81,775 | 86,333 | 87,264 | 168,117 | 74,551 |
| Median tool calls reported | 11 | 8 | 14 | 15 | 9 | 9 |
| Median seconds | 64 | 49 | 56 | 56 | 54 | 64 |

<!-- table:queries -->
| Counted queries per run (SQL and script calls) | Sonnet S | Sonnet D | Sonnet L | Sonnet L- | Haiku S | Haiku L |
|---|---|---|---|---|---|---|
| Mean | 11.7 | 7.0 | 5.6 | 5.9 | 7.5 | 4.8 |
| Median | 11 | 7 | 5 | 6 | 8 | 4 |
| Most in one run | 28 | 17 | 15 | 13 | 29 | 20 |
| Runs that ran a library script | 0 | 0 | 209 | 0 | 0 | 265 |
| Failed calls per run | 0.65 | 0.27 | 0.20 | 0.19 | 0.19 | 0.19 |

<!-- table:skills -->
| Library arms | Sonnet L | Sonnet L- | Haiku L |
|---|---|---|---|
| Skills opened per run, mean (median, most) | 4.7 (5, 7) | 4.8 (5, 7) | 2.4 (2, 5) |
| Runs that opened more than 6 skills | 3 | 1 | 0 |
| Library files read per run, mean (most) | 6.1 (10) | 6.7 (12) | 3.1 (7) |
| Runs that opened the request-history digest | 55 | 94 | 1 |
| Runs that ran a script | 209 | 0 | 265 |
| fiscal.py calls / query_check.py calls | 193 / 93 | 0 / 0 | 240 / 349 |

<!-- table:skill_opens -->
| Skill (runs of 300 that opened it) | Sonnet L | Sonnet L- | Haiku L |
|---|---|---|---|
| warehouse-map | 298 | 298 | 67 |
| metric-dictionary | 235 | 245 | 97 |
| fiscal-calendar | 233 | 237 | 207 |
| query-check | 155 | 179 | 35 |
| sales-reporting | 153 | 170 | 124 |
| store-and-product-history | 137 | 136 | 48 |
| web-orders | 70 | 64 | 61 |
| loyalty-and-campaigns | 55 | 55 | 44 |
| lfl-and-store-league | 43 | 44 | 34 |
| stock | 20 | 20 | 16 |

<!-- table:budget -->
| Told up to | Sonnet S | Sonnet D | Sonnet L | Sonnet L- | Haiku S | Haiku L |
|---|---|---|---|---|---|---|
| 12 queries | 152 | 197 | 179 | 190 | 190 | 194 |
| 30 queries | 148 | 103 | 121 | 110 | 110 | 106 |
| of which re-runs of capped runs | 32 | 0 | 0 | 0 | 3 | 3 |

<!-- table:budget_sonnet_s -->
| Sonnet S | Runs | Correct | Share | Mean queries used |
|---|---|---|---|---|
| told 12 | 152 | 82 | 53.9% | 8.4 |
| told 30 (all) | 148 | 67 | 45.3% | 15.0 |
| told 30, re-runs of capped runs | 32 | 13 | 40.6% | 17.2 |
| told 30, first pass (rounds 39-60) | 116 | 54 | 46.6% | 14.4 |

<!-- table:predictions -->
| # | Prediction | Verdict | The numbers |
|---|---|---|---|
| 1 | Overall correctness | NOT MET | S 149/300 (49.7%), D 298/300 (99.3%), L 295/300 (98.3%). S in band: True; D in band: False; L in band: False. |
| 2 | Where the gain comes from | MET | D - S = 49.7 pp; L - D = -1.0 pp. |
| 3 | Clean requests | MET | S 70/70, D 70/70, L 70/70; spread 0 runs. |
| 4 | Same answer every time | NOT MET | S 33, D 57, L 54 of 60. |
| 5 | Two departments, one number | NOT MET | S 9, D 10, L 10 of 10. |
| 6 | Company definitions | NOT MET | S 19/60, D 60/60, L 60/60. |
| 7 | Rigidity | MET | D 0/20, L 0/20 (S 0/20 for reference). |
| 8 | Problems nobody wrote down | NOT MET | L 20/20 (repaired 20, flagged 0); S 5/20 (repaired 5, flagged 0); L without T16 15/15. |
| 9 | Token use | MET | S 71,548, D 80,897, L 85,100; L/D = 1.052; S < D: True; D < L: True. |
| 10 | Small model with the library | MET | Haiku L 237/300 (79.0%), Sonnet S 149/300 (49.7%), Sonnet L 295/300 (98.3%); Haiku L - Sonnet S = 29.3 pp; Sonnet L - Haiku L = 19.3 pp. |
| 11 | Scripts | MET | L 295/300, L- 297/300 (gap -0.7 pp); on the 12 requests L 56/60, L- 59/60 (L - L- = -3). |
| 12 | Requests the library was not built for | NOT MET | No-template 64/65 (98.5%), other 231/235 (98.3%); gap -0.2 pp (no-template requests: REQ-T04, REQ-T12, REQ-T21, REQ-T22, REQ-T24, REQ-T25, REQ-T28, REQ-T29, REQ-T37, REQ-T38, REQ-T41, REQ-T48, REQ-T51). |

<!-- table:per_request -->
| Request | Trap classes | Pattern | Sonnet S | Sonnet D | Sonnet L | Sonnet L- | Haiku S | Haiku L |
|---|---|---|---|---|---|---|---|---|
| REQ-T01 | company_definition, fiscal_calendar | 2 | 3 | 5 | 5 | 5 | 1 | 4 |
| REQ-T02 | clean | 4 | 5 | 5 | 5 | 5 | 5 | 5 |
| REQ-T03 | override | 7 | 3 | 5 | 5 | 5 | 0 | 4 |
| REQ-T04 | vat | 14 | 5 | 5 | 5 | 5 | 0 | 0 |
| REQ-T05 | fiscal_calendar | 1 | 0 | 5 | 5 | 5 | 0 | 5 |
| REQ-T06 | company_definition | 4 | 5 | 5 | 5 | 5 | 0 | 5 |
| REQ-T07 | fiscal_calendar, scd | 11 | 0 | 5 | 5 | 5 | 0 | 4 |
| REQ-T08 | company_definition, scd | 2 | 0 | 5 | 5 | 5 | 0 | 5 |
| REQ-T09 | clean | 3 | 5 | 5 | 5 | 5 | 4 | 5 |
| REQ-T10 | clean | 3 | 5 | 5 | 5 | 5 | 2 | 1 |
| REQ-T11 | fiscal_calendar, scd | 3 | 0 | 5 | 5 | 5 | 0 | 3 |
| REQ-T12 | semi_additive, undocumented | 10 | 5 | 5 | 5 | 5 | 0 | 0 |
| REQ-T13 | exclusions | 7 | 5 | 5 | 5 | 5 | 0 | 5 |
| REQ-T14 | ambiguous, exclusions | 12 | 5 | 5 | 5 | 5 | 3 | 1 |
| REQ-T15 | time_zone | 5 | 0 | 5 | 5 | 5 | 0 | 5 |
| REQ-T16 | undocumented | 6 | 0 | 5 | 5 | 5 | 0 | 4 |
| REQ-T17 | company_definition, scd | 4 | 0 | 5 | 5 | 5 | 0 | 4 |
| REQ-T18 | migration | 5 | 0 | 5 | 5 | 5 | 0 | 5 |
| REQ-T19 | fiscal_calendar, scd | 1 | 0 | 5 | 5 | 5 | 0 | 5 |
| REQ-T20 | ambiguous, fiscal_calendar | 1 | 3 | 5 | 5 | 5 | 1 | 5 |
| REQ-T21 | vat | 14 | 0 | 5 | 5 | 5 | 0 | 5 |
| REQ-T22 | fan_out | 9 | 0 | 5 | 5 | 5 | 0 | 2 |
| REQ-T23 | company_definition | 4 | 5 | 5 | 5 | 5 | 5 | 5 |
| REQ-T24 | clean | 13 | 5 | 5 | 5 | 5 | 5 | 5 |
| REQ-T25 | company_definition, fan_out | 13 | 0 | 5 | 5 | 5 | 2 | 4 |
| REQ-T26 | exclusions | 12 | 4 | 5 | 5 | 5 | 0 | 4 |
| REQ-T27 | override, vat | 1 | 0 | 5 | 5 | 5 | 0 | 3 |
| REQ-T28 | semi_additive | 10 | 1 | 5 | 5 | 5 | 0 | 5 |
| REQ-T29 | vat | 14 | 5 | 5 | 4 | 4 | 1 | 3 |
| REQ-T30 | clean | 8 | 5 | 5 | 5 | 5 | 5 | 5 |
| REQ-T31 | company_definition, fan_out | 8 | 0 | 5 | 5 | 5 | 0 | 5 |
| REQ-T32 | clean | 3 | 5 | 5 | 5 | 5 | 4 | 4 |
| REQ-T33 | fiscal_calendar | 1 | 0 | 5 | 5 | 5 | 1 | 5 |
| REQ-T34 | company_definition, fiscal_calendar | 2 | 4 | 5 | 5 | 5 | 3 | 5 |
| REQ-T35 | clean | 11 | 5 | 5 | 5 | 5 | 5 | 5 |
| REQ-T36 | override | 3 | 0 | 5 | 5 | 5 | 0 | 3 |
| REQ-T37 | clean | 10 | 5 | 5 | 5 | 5 | 5 | 5 |
| REQ-T38 | clean | 9 | 5 | 5 | 5 | 5 | 5 | 5 |
| REQ-T39 | time_zone | 5 | 5 | 5 | 5 | 5 | 0 | 5 |
| REQ-T40 | clean | 3 | 5 | 5 | 5 | 5 | 0 | 0 |
| REQ-T41 | clean | 13 | 5 | 5 | 5 | 5 | 5 | 5 |
| REQ-T42 | undocumented | 12 | 0 | 5 | 5 | 5 | 0 | 4 |
| REQ-T43 | ambiguous, fiscal_calendar | 11 | 0 | 5 | 5 | 5 | 0 | 4 |
| REQ-T44 | company_definition, scd | 3 | 0 | 5 | 5 | 5 | 0 | 5 |
| REQ-T45 | ambiguous, fan_out | 8 | 5 | 3 | 1 | 4 | 4 | 2 |
| REQ-T46 | migration | 11 | 0 | 5 | 5 | 5 | 0 | 2 |
| REQ-T47 | clean | 8 | 5 | 5 | 5 | 5 | 5 | 5 |
| REQ-T48 | semi_additive | 10 | 5 | 5 | 5 | 5 | 2 | 4 |
| REQ-T49 | exclusions | 7 | 4 | 5 | 5 | 5 | 0 | 4 |
| REQ-T50 | company_definition, migration | 6 | 0 | 5 | 5 | 5 | 0 | 5 |
| REQ-T51 | company_definition, fan_out | 9 | 0 | 5 | 5 | 5 | 0 | 1 |
| REQ-T52 | clean | 11 | 5 | 5 | 5 | 5 | 5 | 5 |
| REQ-T53 | company_definition, fiscal_calendar | 2 | 2 | 5 | 5 | 5 | 1 | 4 |
| REQ-T54 | ambiguous, fiscal_calendar | 1 | 0 | 5 | 5 | 5 | 5 | 5 |
| REQ-T55 | undocumented | 8 | 0 | 5 | 5 | 5 | 0 | 0 |
| REQ-T56 | time_zone | 5 | 0 | 5 | 5 | 5 | 0 | 5 |
| REQ-T57 | clean | 11 | 5 | 5 | 5 | 5 | 4 | 5 |
| REQ-T58 | exclusions | 12 | 5 | 5 | 5 | 4 | 1 | 4 |
| REQ-T59 | override | 5 | 0 | 5 | 5 | 5 | 0 | 5 |
| REQ-T60 | migration | 5 | 0 | 5 | 5 | 5 | 0 | 5 |

<!-- table:ledger -->
| Leniency (switched off alone) | Correct runs of 1,800 without it | Runs that depend on it |
|---|---|---|
| Answer leaves out supporting measures the key does not require (the required-flag proposal) | 1224 | 137 |
| Result matches an alternative the key accepts (widened after the 15 Oct review) | 1314 | 47 |
| Column rounded to whole numbers or one decimal, each value correctly rounded | 1329 | 32 |
| Months given in one column with a value column (REQ-T04) | 1341 | 20 |
| Zero-filled padding row ignored | 1358 | 3 |
| Total row ignored | 1360 | 1 |
| Store or product name given instead of the ID | 1360 | 1 |
| Fiscal year fused with period, quarter or week in one label | 1361 | 0 |
| All eight switched off | 1165 | 196 |

