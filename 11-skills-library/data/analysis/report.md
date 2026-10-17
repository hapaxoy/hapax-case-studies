# Case 11 · Skills library · Report

Written after the marking of the 1,800 runs, 15 Oct 2026. The numbers are in `tables.md` and `results.json`, and the commands to reproduce them are in section 9.

## 1. Result

Correct means the returned table matches the key under `code/mark.py` (marker 6), with the keyword rules and the arm-blind adjudication applied. Each cell is 300 runs.

| Cell | Correct | Share | 95% interval (resampling the 60 requests) | Keyword rules only |
|---|---|---|---|---|
| Sonnet S | 149 | 49.7% | 37.7 to 61.7 | 149 |
| Sonnet D | 298 | 99.3% | 98.0 to 100.0 | 298 |
| Sonnet L | 295 | 98.3% | 95.3 to 100.0 | 295 |
| Sonnet L− | 297 | 99.0% | 97.7 to 100.0 | 297 |
| Haiku S | 89 | 29.7% | 19.7 to 40.0 | 89 |
| Haiku L | 237 | 79.0% | 71.0 to 86.3 | 233 |

Paired bootstrap differences over the 60 requests, in percentage points:

| Contrast | pp | Interval |
|---|---|---|
| D − S | +49.7 | 37.7 to 62.0 |
| L − S | +48.7 | 36.0 to 61.3 |
| L − D | −1.0 | −2.7 to 0.0 |
| L − L− | −0.7 | −3.0 to 1.0 |
| Haiku L − Haiku S | +49.3 | 38.3 to 60.3 |
| Haiku L − Sonnet S | +29.3 | 14.7 to 43.7 |
| Sonnet L − Haiku L | +19.3 | 12.0 to 27.3 |

- **Doc, library and library without scripts tie.** All three Sonnet arms score 98 to 99%. On the 14 clean requests all three score 70 of 70. Nothing here shows that skills packaging, or the scripts, adds accuracy over the same 62 facts in one document.
- **Schema-only Sonnet scores 50%.** It fails exactly the traps whose answer is a private company rule and passes the rest.
- **Haiku with the library scores 79%.** Haiku S fails 11 of the 70 clean-request runs; Sonnet S fails none.

## 2. The twelve frozen predictions

Scored by the exact rule in the frozen file, on the marker as built. "Sonnet" unless stated.

| # | Prediction | Verdict | Numbers |
|---|---|---|---|
| 1 | Overall | **NOT MET** | S 149/300 (inside 75–150 by one run); D 298 and L 295 against a band of 195–255 |
| 2 | Where the gain comes from | MET | D − S = 49.7 pp; L − D = −1.0 pp |
| 3 | Clean requests | MET | S 70/70, D 70/70, L 70/70; spread 0 |
| 4 | Same answer every time | **NOT MET** | Requests with five matching runs: S 33 (needed ≤27), D 57, L 54 (needed ≥39) |
| 5 | Two departments, one number | **NOT MET** | Pairs agreeing: S 9 (needed ≤5), D 10, L 10 |
| 6 | Company definitions | **NOT MET** | S 19/60 (needed ≤12), D 60/60, L 60/60 |
| 7 | Rigidity | MET | Default applied against the request: D 0/20, L 0/20 |
| 8 | Problems nobody wrote down | **NOT MET** | L 20/20 (all repaired, none flagged-only); S 5/20 (needed ≤3); L without REQ-T16 15/15 (needed ≤7) |
| 9 | Token use | MET | Median S 71,548 < D 80,897 < L 85,100; L/D = 1.052 |
| 10 | Small model with library | MET | Haiku L − Sonnet S = +29.3 pp; Sonnet L − Haiku L = +19.3 pp |
| 11 | Scripts | MET | L − L− = −0.7 pp overall; on the 12 targeted requests L 56/60, L− 59/60 (L − L− = −3) |
| 12 | Requests the library was not built for | **NOT MET** | L: 64/65 (98.5%) on the 13 no-template requests, 231/235 (98.3%) on the other 47; gap −0.2 pp |

Six met, six not met. Nothing is retuned.

### Diagnosis of the misses

- **1.** The 15 to 20 point discount for the dev requests was too big. The 13 no-template requests (VAT, stock, uplift, new members) scored 64/65 for L, no worse than the rest.
  - D and L cite a past request by id in 58 and 21 of their 300 runs, and all of those are correct. They are also correct in all but 2 and 5 of the runs that do not cite one. So the dev history is used but does not carry the score.
  - It is not the marker. With every leniency off, D is 260 (above the band), and D is out of band under every marking tried.
- **4 and 5.** S is more consistent than predicted, including in its mistakes.
  - It is reliably right on 25 requests and makes the same wrong choice in all five runs on 8 (REQ-T15, T21, T25, T36, T42, T43, T59, T60).
  - It agrees on 9 of 10 paraphrase pairs: three are clean, six repeat the same mistake under both wordings.
  - D and L clear their bars easily.
- **6.** D and L are at 60/60. The miss is S: 10 of its 19 are the two return-rate requests (REQ-T06, T23). S computed the sale-cohort rate from the schema alone and dropped the Web row, which the key accepts as an alternative. Without that alternative S scores 9 and the prediction is met. The other 9 are partial like-for-like runs (REQ-T01 3 of 5, T34 4, T53 2).
- **8.** L passes the first clause (20 ≥ 8) and fails the other two.
  - All 20 of L's right runs are repairs. S's 5 are all REQ-T12: all five S runs found the duplicated West stock snapshot themselves, fixed it and said so. S also found and repaired the other three incidents in all 15 of its runs, but those answers were wrong for other reasons (section 8, item 3), so the clause scores correctness, not detection.
  - The advice to check source rows for duplicates, which was written after two of the problems were already known, is consistent with this. Each run was not traced.
  - D, L and L− repaired and said so in 19, 16 and 17 of 20 runs. The gaps are all REQ-T16, where the template takes the route the incident does not touch and nothing is noticed (D 4 of 5 said so, L 1, L− 2). A correct REQ-T16 answer from D or L is not evidence of care.
- **12.** The one miss in L's 65 is REQ-T29 (the VAT rate written as 0.255). The library did as well on requests it had no template for as on the rest, under every marking. (In the first marking the verdict depended on the key's alternatives, because the key's reference for REQ-T22 and T51 dated web sales by order date while the company document says dispatch date. The key was corrected on 16 Oct 2026; see the note at the end of section 5.)

### Marker sensitivity

| Marking | Cells (S / D / L / L− / Haiku S / Haiku L) | Verdicts that change |
|---|---|---|
| Keyword rules only | 149 / 298 / 295 / 297 / 89 / 233 | none |
| Key's alternatives off | 130 / 290 / 290 / 291 / 86 / 227 | 6 becomes **met** |
| All eight leniencies off | 115 / 270 / 251 / 251 / 79 / 199 | 2 becomes **not met** (L − D = −6.3 pp) |
| Seven double-launched runs left out | 149 / 296 of 298 / 293 of 298 / 297 / 88 of 297 / 237 | none |

Predictions 2 and 6 move with the marker. The prediction file names the built marker, so the verdicts above stand. (Figures after the 16 Oct key correction; before it, the first two rows also flipped prediction 12.)

## 3. Collection

`code/collect_full.py` read all 1,800 final messages, counters and usage lines. All 1,800 parsed, so there is no failure list. 1,124 finals carried HTML entities and 676 did not; each is unescaped before parsing.

Every run has one usage line in the round the plan gives it. The 38 old cap-12 lines are not used. No run reached its query ceiling (most used: 11 of 12, 29 of 30), and no call was refused in any run. Counter-write faults: none.

| Told up to | S | D | L | L− | Haiku S | Haiku L |
|---|---|---|---|---|---|---|
| 12 queries | 152 | 197 | 179 | 190 | 190 | 194 |
| 30 queries | 148 | 103 | 121 | 110 | 110 | 106 |

### The four irregularities

1. **`full-sonnet-S-t34-r5`, truncated save.**
   - The saved final stopped at 1,748 characters. The real message was recovered from the run's own re-run transcript, the run's agent transcript (5,718 characters, read only).
   - The saved text, unescaped, equals the first 1,736 characters of it.
   - The recovered text is in `data/agent_runs/scratch/full/recovered-full-sonnet-S-t34-r5.txt` with a `.NOTE.md`, written by `code/recover_final_message.py`. The damaged file is untouched.
   - The recovered answer is scored and is correct. It is the only damaged final.
2. **Runs launched twice.** 45 run ids have two sessions.
   - 38 are the planned cap-12 re-runs. Their first sessions ended hours earlier on the old counter, and no timestamps overlap. `full-haiku-S-t22-r1` is one of these 38.
   - Seven are unplanned and share a counter between their two sessions:

| Run | How | Counter | Scored |
|---|---|---|---|
| `full-haiku-S-t37-r3` | Two launches 9 s apart, concurrent | 6 + 4 calls, 10 of 12 | Second-launched session; correct |
| `full-sonnet-L-t03-r3` | 16 min apart, second ran inside the first's 85-minute window | 4 + 5, 9 of 12 | Second session; correct |
| `full-haiku-S-t50-r3` | Round 24, relaunched 25 min later | 3, then 7 | Relaunch; wrong |
| `full-haiku-S-t59-r5` | Same | 3, then 6 | Relaunch; wrong |
| `full-sonnet-D-t10-r4` | Same | 8, then 2 | Relaunch; correct |
| `full-sonnet-D-t24-r1` | Same | 4, then 4 | Relaunch; correct |
| `full-sonnet-L-t14-r2` | Same | 3, then 6 | Relaunch; correct |

   - The five round-24 runs are exactly those whose first sessions finished in 20 to 50 s but were never saved.
   - The saved answer is scored in all seven. Leaving the seven out changes no verdict.
   - **`full-haiku-L-t03-r4` was launched once.** There is one launch record and one transcript, so the earlier suspicion of a double launch does not hold.
3. **`full-sonnet-S-t26-r2`, "background work still running".**
   - Its sixth query finished in the warehouse, but the Bash call passed the 120 s timeout and the harness moved it to a background task. That task's output file stayed empty.
   - The agent never saw that result, ran two more queries and answered correctly. It used 8 of 12 queries on its own counter.
   - 13 other runs also had a command moved to the background after 120 s.
4. **Entities.** Handled by unescaping on collection; no answer was marked down for them.

## 4. Lane check

`code/lane_check.py` matched all 1,845 transcripts (read only) to the 1,800 runs. It classified every Read, Glob, Grep, Bash and PowerShell call, every absolute path in a command, and every Glob and Grep result. It followed variables, one-line shell functions and `cd`. It also searched everything the agents wrote for lock, password, vault, registry, scratch folder, key and held-out-folder terms.

**No run read, listed, searched or ran anything in `world/`, `arms/`, `arms_v1/`, `design/`, `data/key`, `data/requests`, `data/internal`, `code/`, another run's packet, another arm's stage, another counter or the lock archive. No run touched or mentioned the lock, the password or the registry.**

Every Read and Glob was the run's own packet, a file in its own arm's stage, or its own background-task output. Every hx call carried the run's own id except 28 refused probes. 1,797 runs carry no breach or term flag.

**Three runs carry a breach-level flag, each small:**
- `full-haiku-L-t05-r3` tried `import duckdb` on a made-up path inside its stage folder. It failed on its own command-line error, read nothing and then used `hx_sql`. Its answer is correct.
- `full-haiku-S-t46-r2` wrote and read back its own query file in the session scratch folder.
- `full-sonnet-L-t42-r5` ran `cd` into the scratch folder and `echo ok`.

No run listed the session scratch folder or opened anything in it other than its own files.

Not breaches, listed so the count is complete (runs with the flag):

| Flag | Runs |
|---|---|
| Grep inside own library | 55 (all L and L−; 60 calls) |
| `ls`/`cat`/`grep`/`find` inside own stage | 50 |
| Tool called with an unregistered run id (typos, placeholders, usually with `SELECT 1`) | 28 (Sonnet S 25, D 2, L− 1); every call refused, nothing spent |
| Inline Python for arithmetic | 8 |
| PowerShell (failed on the heredoc) | 3, all Haiku S |
| Files under `/tmp` | 3 |

- Transcript against counter: tool-call counts agree in 1,727 runs. 27 transcripts show one or two extra calls (commands that failed before the tool started), and 1 shows one fewer.
- The 6-skill cap is an instruction the harness cannot count: four runs opened 7 skills (Sonnet L 3, L− 1).

## 5. The marker

Marker 6 is built on pilot marker 5. Eighty tests pass, and `mark.py --self-check` passes on all 60 requests: every accepted result marks correct and every naive variant marks wrong and is attributed to itself.

- **Compared as:** columns matched by value; row order only where the key says; 0.1% relative and 0.1 pp tolerance.
- **Required columns:** the required-flag proposal is adopted as written.
- **Shapes accepted, each switchable:** total rows ignored; zero-filled padding rows ignored; store and product names read as IDs; months long or wide; fused fiscal labels (extended to bare "P7"); agent rounding to whole numbers or one decimal when each value is correctly rounded.
- **Stays strict:** a fraction written for a percentage, a missing or extra non-zero row, ranked-list order, and every trap reading.
- **Ambiguous class** (REQ-T14, T20, T43, T45, T54): correct only if the result matches a reading and `assumptions` passes that reading's keyword rule.
- **Undocumented class** (REQ-T12, T16, T42, T55): (a) the incident-free number, (b) the published number with `caveats` passing the keyword rule, (c) published with no warning is wrong. (a) and (b) are reported apart.

Runs that depend on each leniency, switched off alone:

| Leniency | Runs |
|---|---|
| Required-flag proposal (supporting figures omitted) | 137 |
| Key's alternatives | 47 (S 19, D 8, L 5, L− 6, Haiku S 3, Haiku L 6) |
| Agent rounding | 32 |
| Long months (REQ-T04) | 20 |
| Zero rows | 3 |
| Names for IDs | 1 |
| Totals | 1 |
| Fused labels | 0 |

All eight off: 1,165 of 1,800 correct, against 1,361 (keyword rules) or 1,365 (adjudicated).

**Key correction, 16 Oct 2026.** On REQ-T22 and T51 the key's reference dated web sales by order date, while the company document dates them by dispatch date; the document's reading was accepted only as an alternative. Reference and alternative were swapped at source (`code/key_questions_c.py`) and the key rebuilt with `build_key.py`; only those two entries changed (new references 190,687.59 and 9.34 / 7.94 / 1.41). The earlier key is not published. No run's mark changed, since both readings were already accepted; only the leniency counts and the sensitivity rows above moved (the alternatives leniency went from 76 runs to 47, all-off from 1,136 to 1,165).

### Marker choices that can be reversed

- **REQ-T26 / T58 alternative** (ranked by total net sales): the marker asks for the ranking figure, not the per-trading-day one. 8 Sonnet S and 1 Haiku S runs depend on it; without it S has 141.
- **REQ-T29:** a VAT rate written 0.255 in the label column stays wrong. Three runs (Sonnet L, Sonnet L−, Haiku S). Accepting it gives L 296, L− 298.
- **REQ-T45 "customers in Tampere":** seven Sonnet runs (D 2, L 4, L− 1) read it as active members with a Tampere home store (4,441). That is defensible and not in the key, so they stay wrong. Accepting it gives D 300, L 299, L− 298. It changes no verdict.
- **Rounding rule:** 16 of its 32 runs are REQ-T28, weeks of cover to one decimal.

## 6. Arm-blind adjudication

There were 41 items: 11 borderline and 30 audits of keyword-rule passes. Arm, model and run id were hidden. They were decided before the map was opened (`adjudication_decisions.json`, with a hash of the blind list so labels cannot drift).

- **Audit:** 30 of 30 keyword-rule passes confirmed.
- **Borderline:** 4 pass and 7 fail.
  - The 4 passes are REQ-T42 caveats that flag the 10,390.53 EUR control-total gap at store 116 without diagnosing the duplicate. All are Haiku L (233 to 237).
  - The 7 fails are REQ-T12 (2), REQ-T55 (4), and one REQ-T42 caveat that blames the control table and says the league table is correct.
- **Who decided:** the marking model. The five items a second reader might dispute (A005, A020, A027, A028, A038, all REQ-T42) were read a second time on 16 Oct 2026 and all five decisions stood.

## 7. Measures

**Correctness by trap class** (runs correct; percentages only where the class has 10 or more requests):

| Class (requests) | S | D | L | L− | Haiku S | Haiku L |
|---|---|---|---|---|---|---|
| company definition (12) | 19/60 (32%) | 60/60 | 60/60 | 60/60 | 12/60 (20%) | 52/60 (87%) |
| fiscal calendar (11) | 12/55 (22%) | 55/55 | 55/55 | 55/55 | 12/55 | 49/55 |
| scd (6) | 0/30 | 30/30 | 30/30 | 30/30 | 0/30 | 26/30 |
| migration (4) | 0/20 | 20/20 | 20/20 | 20/20 | 0/20 | 17/20 |
| time zone (3) | 5/15 | 15/15 | 15/15 | 15/15 | 0/15 | 15/15 |
| exclusions (5) | 23/25 | 25/25 | 25/25 | 24/25 | 4/25 | 18/25 |
| fan-out (5) | 5/25 | 23/25 | 21/25 | 24/25 | 6/25 | 14/25 |
| semi-additive (3) | 11/15 | 15/15 | 15/15 | 15/15 | 2/15 | 9/15 |
| VAT (4) | 10/20 | 20/20 | 19/20 | 19/20 | 1/20 | 11/20 |
| ambiguous (5) | 13/25 | 23/25 | 21/25 | 24/25 | 13/25 | 17/25 |
| override (4) | 3/20 | 20/20 | 20/20 | 20/20 | 0/20 | 15/20 |
| undocumented (4) | 5/20 | 20/20 | 20/20 | 20/20 | 0/20 | 8/20 |
| clean (14) | 70/70 | 70/70 | 70/70 | 70/70 | 59/70 (84%) | 60/70 (86%) |

The per-request table (runs correct of 5) is the last table in `tables.md`.

**Error attribution.** Wrong runs matching a naive variant:

| Variant | S | D | L | L− | Haiku S | Haiku L |
|---|---|---|---|---|---|---|
| fiscal calendar | 3 | 0 | 0 | 0 | 0 | 0 |
| scd | 6 | 0 | 0 | 0 | 0 | 2 |
| time zone | 2 | 0 | 0 | 0 | 0 | 0 |
| migration | 0 | 0 | 0 | 0 | 4 | 0 |
| semi-additive | 0 | 0 | 0 | 0 | 2 | 0 |
| published without warning | 0 | 0 | 0 | 0 | 0 | 7 |
| percent as fraction | 0 | 0 | 1 | 1 | 1 | 0 |
| other | 140 | 2 | 4 | 2 | 204 | 54 |
| total wrong | 151 | 2 | 5 | 3 | 211 | 63 |

Most wrong answers match no naive variant. A naive variant is one trap taken alone, and the wrong answers are several departures at once. Samples were read by hand: 33 Sonnet S runs (one each for 33 of the 36 requests it gets wrong), 22 Haiku L, 6 Haiku S clean requests, and all 10 Sonnet D, L and L− misses.

- **Sonnet S:** private company rules guessed.
  - Its own 12-month like-for-like cut, which drops the two 2024 openings (REQ-T01, T34, T53, and West in T08).
  - Web sales dated by order date, as-was categories and regions, the web shop dropped from a regional table, return rate on units, ATV with returns netted, `channel_code` for web.
  - None of these is a marker problem.
- **Haiku S and Haiku L:** the same rule errors plus slips.
  - A store read as part of a product name (REQ-T40: all 10 Haiku runs returned the chain-wide 176 or 183 against 17).
  - A guessed category (REQ-T10: 221 against 136), a one-figure request answered per store, and a web-inclusive figure (REQ-T04).
  - A fan-out join (REQ-T22), the web shop ranked as a store, and a stock average taken across rows.
  - Seven Haiku L runs published duplicated numbers with no warning.
- **Sonnet D, L, L−:** seven of the ten are REQ-T45's third reading, two are REQ-T29's label format, and one is a typing slip. In `full-sonnet-Lminus-t58-r5` the agent typed 360.00 where its query said 362.67. None is a missed company rule.

**Consistency:**

| Measure | S | D | L | L− | Haiku S | Haiku L |
|---|---|---|---|---|---|---|
| All five runs agree (requests of 60) | 33 | 57 | 54 | 53 | 16 | 29 |
| Correct in all five (requests of 60) | 25 | 59 | 58 | 57 | 11 | 32 |
| Paraphrase pairs agreeing (of 10) | 9 | 10 | 10 | 10 | 4 | 9 |

"Same result" means the same accepted result for correct runs (reference and alternative differ beyond tolerance) and table equality for wrong runs. D and L miss 60 of 60 only where two accepted results split the runs (REQ-T11, T17, T23, T29, and the ambiguous T14, T45, T54, T20).

**Adherence to definitions.** D, L and L− are correct on all 60 runs of each of the 12 company-definition requests. None applied a naive variant. `definitions_applied` was not checked against the SQL for every run. A crude automated check on all 180 correct D, L and L− runs found the definition named and the matching SQL feature present in every one, and four were read by hand.

**Rigidity never showed.** D, L and L− followed the explicit request in all 20 runs on each of the four override requests and never applied the default. The team-notes line "an explicit request beats the default" is the likely reason. S got 3 of 20 right and also never applied the default. Haiku L got 15 of 20 right.

**Undocumented class, (a) and (b) apart:**

| | S | D | L | L− | Haiku S | Haiku L |
|---|---|---|---|---|---|---|
| (a) repaired | 5 | 20 | 20 | 20 | 0 | 4 |
| (b) flagged, after adjudication (keyword rule alone: 0) | 0 | 0 | 0 | 0 | 0 | 4 |
| (c) published, no warning | 0 | 0 | 0 | 0 | 0 | 7 |

Haiku L's four (a) runs are REQ-T16, and its four (b) runs are REQ-T42.

**Tokens** (agent totals as the Agent tool reported them; not API cost, and the make-up is unknown):

| | S | D | L | L− | Haiku S | Haiku L |
|---|---|---|---|---|---|---|
| Median per run | 71,548 | 80,897 | 85,100 | 87,236 | 49,451 | 58,982 |
| Total per correct run | 146,656 | 81,775 | 86,333 | 87,264 | 168,117 | 74,551 |
| Counted queries per run (mean) | 11.7 | 7.0 | 5.6 | 5.9 | 7.5 | 4.8 |

- **Composition:** the transcripts show a median of about 507,000 cache-read tokens and 6,200 output tokens per run. The reported total is about 1.3 times input plus cache-write plus output (correlation 0.98), and about 0.13 of the sum that includes cache reads. There is no euro figure.
- **Skills:** Sonnet L opens 4.7 skills and 6.1 library files per run; Haiku L opens 2.4 and 3.1. Sonnet L runs a script in 209 of 300 runs (193 `fiscal.py` and 93 `query_check.py` calls); Haiku L in 265.
- **Request-history digest:** opened in 55 Sonnet L runs, 94 L− runs and 1 Haiku L run.
- **`query_check.py`:** printed a FAIL line in 14 of the 84 Sonnet L runs that used it (all 14 correct) and in 58 of 244 Haiku L runs (48 correct). The counter previews do not show whether a run changed its answer afterwards.
- **Skills the key says a request needed:** the key has no such field, so this cannot be reported.

**Runs told 12 or 30, and Sonnet S correctness by budget:**

| Sonnet S | Runs | Correct | Share |
|---|---|---|---|
| told 12 | 152 | 82 | 53.9% |
| told 30 (all) | 148 | 67 | 45.3% |
| told 30, re-runs of capped runs | 32 | 13 | 40.6% |
| told 30, first pass (rounds 39–60) | 116 | 54 | 46.6% |

This comparison is confounded. The told-12 runs are the ones that finished within 12 queries, so they are the easier ones. On the 52 requests that have runs under both budgets, S is 50.0% told 12 against 53.2% told 30. The 32 capped Sonnet S runs scored 9 correct on their old answers (all parsed) and 13 on the re-run. For the other six capped runs: Haiku L went from 1 to 3 correct of 3, Haiku S stayed 0 of 3. Whether "up to 12" against "up to 30" changes behaviour beyond lifting the ceiling cannot be said.

## 8. Anything odd

1. **D and L are at the ceiling, which the pilots did not predict.** Their five misses are a key gap (REQ-T45) and a label format (REQ-T29). Either the facts are very well written for this set, or the set is easy for an agent that has them, or both. This case cannot separate those.
2. **The key's reference disagreed with the company document on web dates for REQ-T22 and T51.** All 30 D, L and L− runs followed the document. Corrected on 16 Oct 2026 (section 5).
3. **Sonnet S finds all four undocumented incidents by itself, and is right on one.** It is correct on the stock incident (5 of 5 on REQ-T12). On the other three it names and repairs the incident in all 15 runs (the 418 duplicated lines at store 116 on T42, the missing member keys on T55, the 758 mislabelled click-and-collect orders on T16) and is marked wrong for other reasons: ranking by total net sales instead of per trading day (T42), percentages off by 0.2–0.6 pp (T55), shape or value (T16). (Corrected 16 Oct 2026 on a second reading of the runs; the first version said it found none of the three, which described correctness, not detection.)
4. **28 runs called the SQL tool with an unregistered run id,** 25 of them Sonnet S. It reads like a probe of whether an unregistered call is counted. Each was refused.
5. **"Clean" requests are not fully convention-free.** Haiku S and L excluded staff purchases on REQ-T09 and T32 and got 190 units against the key's 194.
6. **P1's S clause passes by one run** (149 against a ceiling of 150).

## 9. What is where

All paths are under the case folder.

| Item | Path |
|---|---|
| Collection | `code/collect_full.py` → `data/analysis/collected_runs.jsonl`, `collection_report.json` |
| Recovery | `code/recover_final_message.py` → `data/agent_runs/scratch/full/recovered-full-sonnet-S-t34-r5.txt` and `.NOTE.md` |
| Lane check | `code/lane_check.py` → `data/analysis/lane_check.jsonl`, `lane_check_summary.json` |
| Marker | `code/mark.py` → `data/analysis/marked_runs.jsonl`, `leniency_ledger.json`, `adjudication_blind.md`, `adjudication_map.json`; `--self-check`; `--adjudication` |
| Adjudication decisions | `data/analysis/adjudication_decisions.json` |
| Measures and predictions | `code/analyse_full.py`, `code/report_tables.py` → `results.json`, `tables.md` |
| Tests | `code/test_mark.py` (80 tests, all pass) |

To rerun in order (about two minutes; the whole chain was run twice and reproduced the same numbers): `collect_full.py`, `lane_check.py`, `mark.py --adjudication data/analysis/adjudication_decisions.json`, `analyse_full.py`, `report_tables.py`.
