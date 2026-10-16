# Forty learners, three instruments

*Kuusiharju Oy, the forty learners, the two-day programme and every answer quoted below are invented. The cohort is simulated, which means nothing here is evidence that training works. What is measured is the ruler, meaning how closely a pre/post assessment recovers learning that was planted in each learner before a single response was written, and where it fails.*

## The question

The evidence the industry offers for training is attendance and applause.

Hapax has trained no commercial cohort, so the case about how much a real cohort learned is not available to write yet. The instrument is. This case builds the assessment that will be attached to every real training engagement (pre/post testing on held-out task sets) and tests it on a simulated cohort whose true learning was planted in advance and recorded in an answer key that only `code/mark.py` opens. The claim it supports is a narrow one. Not that our training works, but that when we train you the effect will be measured with an instrument whose accuracy, and whose failure modes, we have published.

## The cohort

Kuusiharju Oy is an invented technical trade company of about 200 people; 40 of its employees in finance, operations, sales and service administration sit a two-day AI-Augmented Workflows programme, the flagship theme from our own training page. Each simulated learner carries a deterministic profile: a baseline ability, a planted true shift from the training (δ), a confidence trajectory, an assessment-noise level, and a propensity to volunteer.

The confidence trajectory is drawn independently of δ, from its own archetype-conditioned distribution, and never as a function of it. That separation is what the case rests on, so it was given a pre-declared band, not left as an assertion: the cohort-wide correlation between planted shift and confidence gain had to land between 0.20 and 0.65. At seed 9 it is 0.322. Within the confident non-learners alone, a mean planted shift of about 0.03 sits against a mean confidence gain of 1.63 points on a 1–7 scale.

| Archetype | n | Planted truth |
|---|---|---|
| Genuine improver, strong | 8 | δ large; confidence tracks ability |
| Genuine improver, modest | 12 | δ small-positive; confidence tracks |
| Confident non-learner | 7 | δ ≈ 0; confidence rises sharply |
| Non-responder | 7 | δ ≈ 0; confidence flat |
| Ceiling case | 3 | δ ≈ 0 by ceiling; high baseline |
| Fast forgetter | 3 | δ positive at post-test, decays by +8 weeks |

The seven confident non-learners are deliberately the largest problem group, because they are the case a feedback form cannot distinguish from a genuine improver.

## The three instruments

**The honest instrument**, which is the product, is two ten-task forms, A and B, drawn from the programme’s own skill claims and counterbalanced so that no learner answers the same questions twice. Twenty learners sat A first, twenty sat B. Both forms are published in full, because a client should be able to read exactly what would be measured; a real engagement generates fresh forms by the same published method, which is what keeps publication from turning into a rehearsal sheet.

The tasks are ordinary work. A9 reads:

> You now generate the weekly ops report with AI assistance. Describe the specific check you would build into that process – not “I’d read it over” but a named, repeatable step – and say exactly where in the weekly workflow it sits.

A4 gives the learner a drafted paragraph of a weekly ops report – “Deliveries this week: 62, up from 54 last week (a 15% increase). Of these, 3 were late, giving an on-time rate of 97%. Stock of the fast-moving items held steady at 340 units across the two depots, 170 at each.” – and asks them to find both planted errors, say where each sits, and say what they would check to confirm each.

**The feedback sheet** is the industry standard, run honestly as a comparator: post-only self-reported satisfaction and self-assessed improvement, on the same cohort.

**The naive evaluation** is how training is usually measured when anyone tries, assembled from three documented bad practices. It takes volunteers only, gives them the same form before and after, and blends self-report into the score at a weight of 0.5. The practice effect is planted as a flat bonus of 0.07 to effective ability on any form a learner has already seen.

All three run on the same corpus: 240 response files, one per learner per form per occasion, with occasions at pre, post and +8 weeks. Deterministic Python fixed every learner’s ability, shift, noise and rubric hits; prose agents wrote the answers to those briefs and could not add or remove a rubric item. Scoring then reads the answer text, not the briefs, which keeps generation and marking apart.

## What happened

Six expectations were written into the design before any generation or run. Four were met and two were not. Nothing was retuned after these numbers appeared.

| # | Expectation | Verdict | Measured |
|---|---|---|---|
| 1 | Recovers the planted cohort mean effect within ±0.10σ | met | planted 0.1338, measured 0.1437, gap 0.0100 against a tolerance of ±0.0124 |
| 2 | Flags at least 6 of the 7 confident non-learners | met | 6 caught, 1 missed, 2 false positives |
| 3 | Feedback sheet correlates with planted δ at r < 0.30 | met | r = 0.101 for confidence, 0.056 for satisfaction |
| 4 | Naive arm overstates the cohort effect by at least 50% | **not met** | overstatement 41.3% (naive 0.1890 against planted 0.1338) |
| 5 | Form equivalence within tolerance | **not met** | pre-score A 0.4400, B 0.3688, difference 0.0713 against ±0.05 |
| 6 | The designed blind spot is demonstrated | met | forgetters 0.2667 against improvers 0.2150 at post; 22% against 88% retention at +8 weeks |

Scores are fractions of the rubric points available on a form, so a δ of 0.13 means the cohort gained about a seventh of the available marks.

**The cohort effect came back.** The instrument measured a mean gain of 0.1437 against a planted 0.1338, a gap of 0.0100 inside a tolerance of 0.0124. That tolerance is a tenth of the planted shifts’ own standard deviation, and the margin is 0.0024 wide, which matters when the same figure is recomputed under a perfect rater below.

**Six of the seven confident non-learners were flagged**, by a single frozen statistic: each learner’s confidence gain and measured gain are z-scored across the cohort’s own forty values, and anyone whose confidence z exceeds their performance z by more than one standard deviation is flagged. The threshold was set before the run and never adjusted. It caught L01, L03, L09, L12, L23 and L31, missed L30, and flagged two genuine modest improvers, L11 and L15, who happened to combine real but small gains with large confidence gains. The rule returns eight names, six of them the intended ones.

Tiina Räsänen (L23) shows the pattern. Her confidence goes from 3.09 to 4.70 and she rates the course at 4.95 out of 7. Her planted shift is 0.0237 and the instrument measures −0.025. Asked before the course how she would build a check into the weekly report, she wrote that she would “spot-check some of the reconciled figures against the warehouse system before the summary goes out, rather than just reading it over”. Asked the equivalent question afterwards, she wrote that she would “spot-check some of the figures against the system before sending the report on, so it’s not just a read-through”. On the first task of the post form she opened with “Same as before really”.

**The feedback sheet correlates with actual learning at r = 0.101.** Satisfaction does slightly worse, at 0.056. Both are computed against the planted shift for all forty learners. On this cohort the standard evidence for training carries almost no information about whether anyone learned anything, and the expectation that it would come in under r = 0.30 was set before the numbers existed.

**The naive arm overstated by 41.3%, and the pre-registration asked for 50%.** That expectation is frozen as a failure. What it got wrong is the size of the distortion, not its direction. The naive design measured 0.1890 where the cohort truth is 0.1338.

The decomposition is the more useful half, and it is messier than the design anticipated. Each row below switches off exactly one of the three flaws and holds the other two at the naive arm’s actual settings.

| Flaw switched off | Counterfactual effect | Share of the overstatement |
|---|---|---|
| Selection (volunteers → full cohort) | 0.1757 | 24.1% |
| Practice effect (repeated form → counterbalanced) | 0.1654 | 42.8% |
| Self-report weighting (blended → performance only) | 0.2211 | −57.9% |
| Interaction, not attributable to one flaw | – | 90.9% |

Two things there were not anticipated. Self-report weighting pulls the estimate down, not up, because the repeated-form performance delta is already inflated (the flat practice bonus pushes several rubric-band thresholds at once) while the confidence gain rescaled to the same units is comparatively modest, so blending the two dilutes the number. And the interaction term is 90.9% of the total, which means the three flaws do not add. The individual shares are marginal effects, not a partition, and a real evaluation carrying two of these flaws cannot have its bias estimated by adding up what each one is worth alone.

**Form equivalence failed.** Mean pre-score was 0.4400 on Form A and 0.3688 on Form B, a gap of 0.0713 against a tolerance of ±0.05, so Form B is the harder paper by about seven percentage points of rubric coverage. The forms’ structural item difficulties were matched at design time and passed their structural check; what diverged is the realised difficulty once the same rubric items were written out as prose and scored from text. The gap is not a scoring artefact either, since it widens to 0.0900 under the perfect-scoring pass described below. The finding is frozen as the pre-registration said it would be: equivalent forms are genuinely hard to write, and a real engagement pilots both forms on a non-client group before either is relied on. Counterbalancing limits the damage. With 20 learners starting on each form, the cohort mean is protected even when an individual’s pre/post pair is not.

## The scorer, and what a 94%-reliable rater costs

Every number above was produced by scoring response text with `code/rubric_detectors.py`. That scorer’s item-level agreement with the briefs’ intended scores is 94.23%, or 9,046 of 9,600 item checks, against a design target of 97%, and it is the closest analogue this case has to a human marker’s reliability. Someone reading free text against a rubric disagrees with a co-marker, or with themselves on a second pass, some fraction of the time, and this scorer’s fraction is measured and published rather than assumed.

So every verdict was computed a second time on the briefs’ own intended scores, which is what a perfectly reliable rater would produce, and the two passes were compared.

| # | Expectation | Scored text | Perfect scoring | Flipped |
|---|---|---|---|---|
| 1 | Recovers cohort mean effect | met | not met | **yes** |
| 2 | Flags ≥ 6/7 confident non-learners | met | met | no |
| 3 | Feedback sheet r < 0.30 | met | met | no |
| 4 | Naive overstates by ≥ 50% | not met | met | **yes** |
| 5 | Form equivalence | not met | not met | no |
| 6 | Designed blind spot | met | met | no |

Two of six verdicts flip, in opposite directions. Expectation 1 goes from met to not met, because the perfect-scoring gap between planted and measured cohort effect is 0.0212 against the same ±0.0124 tolerance. Expectation 4 goes from not met to met, because the perfect-scoring overstatement is 57.5% and clears the 50% bar the scored pass missed at 41.3%. Under the noisy scorer the instrument looks more accurate than it is, and the naive arm looks less distorted than it is.

The two passes differ in composition elsewhere without changing a verdict. Expectation 2 catches all seven confident non-learners under perfect scoring (all 7, not 6), with two false positives either way, but L28 replaces L15 among them.

Neither pass is the true answer. The scored pass is what a real marking programme produces and the perfect pass is what it is trying to approximate, and the distance between them is what this case has to report. Rater reliability in the region where human markers sit is enough to change what you conclude about a training programme, on a cohort of forty whose true answer is known.

The feedback sheet is identical across both passes. It never reads an answer, so no marker can be wrong about it, which is immunity to rater error bought by measuring nothing.

For a real engagement this settles three things. Forms are piloted before they are relied on. Marking uses two raters, or one calibrated rubric with its agreement rate measured and published. And a conclusion about a cohort is stated with the reliability of the scoring layer attached to it, since two of the six verdicts here turned on exactly that.

## The forgetters the instrument cannot see

The design named this failure in advance. A pre/post instrument measures the day the course ends, and three of the forty learners were built to lose most of what they gained within two months.

At post they are invisible. The three fast forgetters average a measured gain of 0.2667 against 0.2150 for the twenty genuine improvers, whose own standard deviation is 0.1204. They are inside a single standard deviation, and if anything they look slightly better than the people who actually kept the skill.

The +8-week occasion exists in the corpus and no named instrument reads it. Against it, the fast forgetters retain 21.9% of their post-training gain and the genuine improvers retain 87.8%.

| Learner | Measured gain at post | At +8 weeks |
|---|---|---|
| L19, Anne Kiviranta | 0.1750 | 0.0250 |
| L22, Markus Hirvonen | 0.3000 | 0.0750 |
| L25, Katri Vuorinen | 0.3250 | 0.0750 |

Markus Hirvonen’s answers show the decay in plain text. At post, asked for an instruction that returns the same three-line summary every time, he specified the field order, the exact output template and a rule for missing data, then explained that the format and the missing-data rule together are what make the output independent of the email’s wording. Eight weeks later, on the same task, he wrote: “Give it a fixed structure – date, item and quantity, then the change, in that order. Keeps the three lines the same each time.” The answer keeps the topic and loses the mechanism that earned the marks.

This is the published argument for the follow-up a month later that the training page already promises. A pre/post pair measures whether the room learned. A third measurement some weeks out measures whether the workplace kept it, and on this cohort the two questions have different answers for three of the forty people.

## How the marking was checked

The scorer began at 74.80% item-level agreement and was taken to 94.23% across eight rounds of reading disagreements by hand and broadening keyword patterns only where the detector had demonstrably missed text that matched its brief. 3 findings from that work matter.

A numbered-list parser required the yes/no answer to sit directly after the digit, so it read “1. No” and missed “1. Address – no” and “1 – no” entirely. That is a real bug in the marking layer, found only by reading the disagreements, and fixed once in the shared detector, not per file.

Broadening a pattern to catch a false negative can collapse two distinct items into one trigger. Task 1’s item-2 pattern was widened to also fire on item 1’s keyword, and the strict alternative that keeps them apart costs about 14 percentage points of agreement on tasks A1 and B1 specifically. The trade-off was measured, the widening kept, and the cost of the strict rule documented in the code comment.

The residual 554 disagreements are detector-side, and a stratified sample of 60 of them is published with the response text so the classification is checkable. Most are long-tail paraphrase. A smaller group is not fixable by any keyword rule, and it is the more interesting kind. On several closely spaced item pairs the corpus contains near-identical sentences where one earns the higher item and the other does not, because the two ability draws behind them sit either side of a difficulty threshold. “I’d have someone spot-check the numbers before the report goes out” is briefed as item 1 only; “Before the weekly report goes out, I cross-check the totals against the source system” is briefed as items 1 and 2. Both are reasonable answers and the difference between them is one of degree; no keyword rule recovers a continuous ability through free paraphrase without overfitting to this corpus.

One genuine content problem was found and fixed before the marking run. Task 4 plants 2 errors that trade positions between forms (Form A’s error sits in the on-time rate while its growth figure is correct, Form B’s the other way round) and the rubric text described item 2 by a fixed figure name with an aside for Form B, which left it ambiguous which figure items 1 and 2 track once the form is B. A cross-batch audit of all 240 files found the ambiguity resolved differently by different batches of prose agents. Most wrote the canonical resolution; one batch and one outlier stated the item-2-level correction with full precision in eight files whose briefs credit only item 1. The rubric text was tightened to name each form’s fact explicitly, and the B4 answer alone was regenerated in those eight files. Hashes of all 240 response files before and after confirm that exactly those eight differ. Overall agreement moved from 94.15% to 94.23%, which is what that fix contributed in aggregate.

## What transfers and what does not

The instrument transfers, and it is published in full: both forms, the rubric, the cohort, all 240 responses, the marking script and the answer key. A real engagement generates fresh forms by the same method, pilots them for equivalence before relying on them, counterbalances them across the group, measures the scorer’s agreement rate and publishes it, and adds a third measurement some weeks after the room empties. So does the discipline around it: expectations written before the data exists, failures frozen, not retuned, and every verdict recomputed under a perfect rater to see whether it survives.

The numbers do not transfer. They belong to this cohort, its archetype mix and one seed. The 41.3%, the r of 0.101, the 0.0713 form gap and the two flips are properties of forty simulated learners built to have a known answer, not properties of training in general. The seven confident non-learners are there because we put them there, and a real cohort has whatever mix it has.

What a real cohort learns is unknown before it is measured, which is the entire reason for measuring it. The first real engagement’s outcomes will be published with the client’s permission or described without identification, whatever they show.
