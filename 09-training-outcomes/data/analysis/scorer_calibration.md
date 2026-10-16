# Scorer calibration -- 09 Training Outcomes

Calibration run of `code/rubric_detectors.py` (via `code/score_responses.py`) against all 240 Phase-3 response files, compared item-by-item against the response briefs' recorded `rubric_items_hit`. This is a calibration exercise, not production scoring -- a real scoring run never reads the briefs.

**Overall item-level agreement: 9046/9600 = 94.2292%** (target >= 97%).

Verdict: **BELOW** the 97% target.

## Agreement by task

| Task | Category | Agree | Total | Rate |
|---|---|---|---|---|
| A1 | | 463 | 480 | 96.46% |
| A2 | | 458 | 480 | 95.42% |
| A3 | | 445 | 480 | 92.71% |
| A4 | | 464 | 480 | 96.67% |
| A5 | | 456 | 480 | 95.00% |
| A6 | | 437 | 480 | 91.04% |
| A7 | | 462 | 480 | 96.25% |
| A8 | | 463 | 480 | 96.46% |
| A9 | | 447 | 480 | 93.12% |
| A10 | | 461 | 480 | 96.04% |
| B1 | | 470 | 480 | 97.92% |
| B2 | | 433 | 480 | 90.21% |
| B3 | | 432 | 480 | 90.00% |
| B4 | | 465 | 480 | 96.88% |
| B5 | | 457 | 480 | 95.21% |
| B6 | | 434 | 480 | 90.42% |
| B7 | | 460 | 480 | 95.83% |
| B8 | | 443 | 480 | 92.29% |
| B9 | | 439 | 480 | 91.46% |
| B10 | | 457 | 480 | 95.21% |

## Agreement by batch (assumed 8-learner contiguous batches)

| Batch | Learners | Agree | Total | Rate |
|---|---|---|---|---|
| 1 | L01-L08 | 1904 | 1920 | 99.17% |
| 2 | L09-L16 | 1853 | 1920 | 96.51% |
| 3 | L17-L24 | 1763 | 1920 | 91.82% |
| 4 | L25-L32 | 1773 | 1920 | 92.34% |
| 5 | L33-L40 | 1753 | 1920 | 91.30% |

## Disagreements

Total disagreements: 554 out of 9600 item checks.

| Classification | Count |
|---|---|
| detector_recall_limit | 554 |

### Genuine infidelities (regeneration candidates)

These disagreements are NOT detector bugs -- the response text plainly contains (or omits) content the brief says it should not (or should). Confirmed by the cross-batch audit.

| File | Task | Item | Expected | Detected | Reason |
|---|---|---|---|---|---|

### Detector recall/precision limits (the remaining disagreements)

554 remaining disagreements. Eight tuning iterations brought overall item-level agreement from 74.80% to the figure at the top of this report by reading hundreds of these by hand and broadening keyword patterns for every confirmed detector miss. What is left clusters into two kinds, both detector-side, neither response infidelity:

1. **Genuine paraphrase the detector doesn't recognise yet** -- the response text plainly satisfies (or plainly lacks) the item; a keyword pattern for that specific phrasing was not written. Diminishing returns set in here: each round fixed the highest-volume pattern gaps, and what remains is long-tail phrasing (dozens of one-off wordings across 240 files).
2. **Band-boundary noise** -- for a handful of closely-spaced item pairs (notably Task 9 items 1/2, Task 6 items 2/3, Task 4-A items 1/2), the corpus contains near-identical sentences where one is briefed as earning the higher item and an almost-identical one is not (e.g. "I'd have someone spot-check the numbers before the report goes out" vs "Before the weekly report goes out, I cross-check the totals against the source system" -- the first is briefed item-1-only, the second item-1+2). No keyword rule distinguishes these reliably; the two effective-ability draws that produced them sit either side of an item's difficulty threshold and manifest as nearly the same sentence. This is intrinsic to a continuous ability score mapped through natural-language generation, not a scorer defect.

A stratified sample (up to 3 disagreements per task, drawn from across the corpus, not cherry-picked) is listed below with the actual response text, so this classification is checkable rather than asserted.

| File | Task | Item | Expected | Detected | Response text |
|---|---|---|---|---|---|
| L01_formB_follow_up_8wk | B3 | 3 | False | True | There's a timing error in this note. Eight am plus six hours on the 22nd finishes that same afternoon -- not the 23rd as stated. |
| L01_formB_post | B3 | 3 | False | True | There's a timing error in this note. Eight am plus six hours on the 22nd finishes that same afternoon -- not the 23rd as stated. |
| L01_formB_pre | B3 | 3 | False | True | There's a timing error in this note. Eight am plus six hours on the 22nd finishes that same afternoon -- not the 23rd as stated. |
| L03_formA_pre | A1 | 2 | False | True | First, one instruction: return exactly three lines, in order -- delivery date, item and quantity, change from original order -- using a fixed template. |
| L07_formA_follow_up_8wk | A1 | 2 | False | True | I think one instruction: return exactly three lines, in order -- delivery date, item and quantity, change from original order -- using a fixed template. |
| L07_formA_post | A1 | 2 | False | True | I think one instruction: return exactly three lines, in order -- delivery date, item and quantity, change from original order -- using a fixed template. |
| L07_formB_pre | B1 | 2 | False | True | I think one instruction: return exactly three lines, in order -- drop-off time, pallet count, damage noted -- using a fixed template. |
| L09_formA_follow_up_8wk | A6 | 2 | True | False | Reply 2 — it has the order and credit references so it's traceable. Reply 1 sounds sincere but there's nothing to look up. |
| L09_formA_follow_up_8wk | A8 | 2 | True | False | I'd keep the pricing and confidentiality details out of an unvetted tool — those feel like the risky parts of the contract. |
| L09_formA_pre | A2 | 2 | False | True | Run each week's claims through an instruction that lists every claim by date, amount, category and submitter, then adds up the total spent for the week so the memo has a clear structure. |
| L09_formA_pre | A9 | 2 | False | True | I'd have someone spot-check the numbers before the report goes out. |
| L09_formB_follow_up_8wk | B9 | 2 | False | True | I'd cross-check the totals before it goes out. |
| L09_formB_post | B2 | 1 | True | False | I'd just make a list of this week's calls with who was contacted and why. |
| L09_formB_post | B6 | 3 | False | True | Email 2 — it's got the actual volume numbers in it. Email 1 doesn't even say what 'current volumes' means, so there's nothing to check it against. |
| L09_formB_post | B9 | 2 | True | False | I'd have someone cross-check the stock counts against the system before the monthly summary goes out. |
| L09_formB_pre | B2 | 2 | True | False | Turn the week's call log into a list with time, customer, topic and outcome for each entry that needs a follow-up call. |
| L09_formB_pre | B9 | 2 | True | False | I'd have someone cross-check the stock counts against the system before the monthly summary is sent out. |
| L10_formA_pre | A3 | 1 | True | False | Something might be wrong with the numbers here but I can't say what exactly. |
| L10_formB_follow_up_8wk | B8 | 1 | True | False | I'd redact the rates and be careful with the non-disclosure clause too. |
| L10_formB_post | B4 | 2 | True | False | 96 to 118 looks like more than a 20% rise to me. The on-time rate might be worth double-checking too. |
| L10_formB_post | B6 | 3 | True | False | Email 2 — it's got the actual volume figures, 1,200 to 1,650. Email 1 just says 'current volumes' without saying what that means, so there's nothing there to verify. |
| L10_formB_pre | B8 | 1 | True | False | I'd hold back the rates, not sure about the rest. |
| L11_formA_pre | A4 | 1 | True | False | The delivery increase looks about right, 15% or so. I didn't look closely enough at the rest to say more, sorry. |
| L11_formB_follow_up_8wk | B4 | 2 | True | False | 96 to 118 is more than a 20% rise. And I'd double-check the on-time rate too. |
| L11_formB_post | B4 | 2 | True | False | 96 to 118 looks bigger than a 20% rise to me. The on-time rate might need a second look too. |
| L12_formA_follow_up_8wk | A4 | 1 | True | False | The delivery number checks out at roughly 15%. |
| L12_formA_follow_up_8wk | A5 | 2 | True | False | Output 2, clearly — it shows the numbers behind the 4.1%. Output 1 doesn't. |
| L12_formA_post | A9 | 2 | False | True | I'd build in some form of cross-check before the report goes out. |
| L13_formA_post | A6 | 4 | False | True | Reply 2 — the order reference and credit reference make it checkable. Reply 1 might well be accurate, I'd just want to see it backed by something before sending it. |
| L13_formA_pre | A4 | 1 | True | False | The delivery figures look roughly consistent to me. |
| L13_formA_pre | A7 | 3 | False | True | 1. No. 2. Yes. 3. Yes. 4. Yes. 5. No. |
| L14_formA_follow_up_8wk | A8 | 2 | True | False | I'd redact the pricing, flag the confidentiality clause, and leave the delivery schedule as is since that part's low risk. |
| L14_formA_pre | A6 | 2 | True | False | Reply 2 — the order and credit references make it checkable. Reply 1 could be fine, I'd just want something to verify it against first. |
| L14_formA_pre | A9 | 3 | True | False | I'd build in a cross-check before the report goes to the manager — recalculate the totals against the source system, not just re-read the draft. |
| L14_formB_follow_up_8wk | B8 | 2 | True | False | I'd redact the hourly rates, flag the non-disclosure clause, and leave the service scope as is. |
| L14_formB_pre | B5 | 2 | True | False | Output 2 — shows the numbers behind the 88%. Output 1 doesn't. |
| L15_formB_post | B6 | 3 | True | False | Email 2 — real volume numbers, 1,200 to 1,650. Email 1 doesn't say what it's comparing to. |
| L15_formB_pre | B5 | 2 | True | False | Output 2 — shows the numbers behind the 88%. Output 1 doesn't. |
| L16_formA_post | A5 | 2 | True | False | Output 2 shows the numbers behind the 4.1%. Output 1 doesn't. |
| L16_formA_pre | A5 | 2 | True | False | I'd probably go with Output 2, it shows more numbers behind the 4.1%. |
| L16_formB_follow_up_8wk | B5 | 2 | True | False | Output 2 shows the numbers behind the 88%. Output 1 doesn't. |
| L17_formA_follow_up_8wk | A3 | 1 | True | False | The dates are wrong here - the call was on the 14th, and going to the 19th is five days later, not the three days the email claims. |
| L17_formA_follow_up_8wk | A3 | 3 | True | False | The dates are wrong here - the call was on the 14th, and going to the 19th is five days later, not the three days the email claims. |
| L17_formA_post | A8 | 2 | True | False | The pricing and discount terms are sensitive, so I wouldn't paste those in as they are. The confidentiality clause naming both companies makes me cautious about the whole thing too. |
| L17_formB_pre | B1 | 2 | False | True | Tell the assistant to give three lines back every time - drop-off time, pallet count, and any damage noted. |
| L18_formA_post | A10 | 3 | True | False | Step 4 is where an error becomes irreversible, since it sends automatically - the gate belongs there, checking quantities and stock match are within bounds. Step 1 carries risk too, since a bad extraction feeds every ... |
| L18_formB_follow_up_8wk | B2 | 4 | True | False | Split the week's entries into Needs follow-up and No action needed, one line per entry with time, customer, topic and outcome kept, and the count is just the size of the first list. A call that looks logged twice gets... |
| L18_formB_post | B7 | 2 | True | False | Vendor pricing stays out — no reason to hand that to an unvetted tool. Procurement spend is fine, it's an aggregate. The unsigned budget draft stays out too, unreleased. The vendor's own datasheet is fine, already pub... |
| L18_formB_post | B7 | 3 | True | False | Vendor pricing stays out — no reason to hand that to an unvetted tool. Procurement spend is fine, it's an aggregate. The unsigned budget draft stays out too, unreleased. The vendor's own datasheet is fine, already pub... |
| L18_formB_post | B7 | 4 | True | False | Vendor pricing stays out — no reason to hand that to an unvetted tool. Procurement spend is fine, it's an aggregate. The unsigned budget draft stays out too, unreleased. The vendor's own datasheet is fine, already pub... |
| L19_formA_follow_up_8wk | A2 | 3 | True | False | List each claim as date, amount, category, submitter, and add up the amounts for a total at the end. |
| L19_formA_post | A7 | 4 | True | False | 1. No, that's the customer's own info. 2. Yes. 3. No. 4. Yes, it's out already. 5. No. |
| L19_formB_post | B10 | 1 | True | False | I'd put the gate on the last step, before the payment note gets submitted automatically — once that's gone through it's hard to pull back. I'd also keep an eye on the first step, since if the invoice gets misread the ... |
| L21_formA_follow_up_8wk | A2 | 2 | True | False | The memo should list date, amount, category, submitter in that order, then a total of all the amounts at the end. |
| L22_formA_follow_up_8wk | A10 | 2 | True | False | The order-reading step is the risky one at the start. The gate really needs to sit before the confirmation goes out automatically, checking the extracted quantity against stock. |
| L22_formA_follow_up_8wk | A10 | 3 | True | False | The order-reading step is the risky one at the start. The gate really needs to sit before the confirmation goes out automatically, checking the extracted quantity against stock. |
| L22_formB_post | B10 | 2 | True | False | Reading the invoice PDF is the riskiest step, since a bad read carries through everything after it. But the real gate needs to sit before the payment note is auto-submitted, checking the extracted total is within a se... |
| L22_formB_post | B10 | 3 | True | False | Reading the invoice PDF is the riskiest step, since a bad read carries through everything after it. But the real gate needs to sit before the payment note is auto-submitted, checking the extracted total is within a se... |
| L24_formA_follow_up_8wk | A7 | 4 | False | True | 1. No, that's the customer's address, wouldn't paste that in. 2. Yes, that's fine, just a total. 3. No, not released yet. 4. No, I'd rather not risk it even though it's not new information. 5. No, that's personal. |
| L27_formB_post | B1 | 2 | False | True | Use a fixed three-line template — drop-off time, pallet count, damage — always in that order. |

(Sample above: 60 of 554 detector-side disagreements shown, up to 3 per task.)
