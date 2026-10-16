# Ledger anomalies, marked against ground truth

## Flags are cheap; attention is not

The ledger described in this case study is synthetic, built with a known answer key held out of every layer of analysis. No real company sits behind any figure below.

A mid-size company's purchase ledger runs to about fifty thousand rows a year. Nobody reads it, and nobody could. Reading every row was never the constrained resource. Producing flags is cheap. A handful of rule tests or a statistical model can raise thousands of them from a ledger this size without much effort. What is scarce is a competent person's time to look at each flag and decide whether it means anything: a duplicate submission, a coding error, a habit of staying just under an approval threshold, or nothing at all. Get that triage wrong in either direction and it costs money. Real process issues compound quietly for months if the flags that would have shown them are buried in noise, and good people burn attention on round numbers and Saturday postings that turn out to mean nothing.

This case tests three different ways of turning a ledger into flags worth someone's time, and marks each one against a set of anomalies planted into the data before any of the three layers ever saw it. The framing throughout is controls and process quality (coding errors, duplicate submissions, threshold habits), never accusation.

## Three layers, one answer key

The ledger belongs to a fictional company, Saarnitukku Oy, a technical wholesale and MRO distributor selling fasteners, seals, tools and maintenance supplies to industrial customers. It runs a Vantaa head office with branches in Tampere and Kuopio, turns over roughly €90 million a year with about 180 staff, and posts its purchase ledger through a four-person accounts-payable team. Procurement peaks every November and December, as customers stock up ahead of their own year-end, and troughs every July.

Three layers screen that ledger, each different in kind. The first is a set of seven deterministic rule tests, each traceable to sourced audit practice: duplicate invoices, round sums, amounts sitting just under the company's €10,000 approval tier, purchases split to slip under that same tier, weekend and holiday postings, mis-posted accounts, and exact-match vendor-name duplication. The second is a statistical anomaly detector, an Isolation Forest running over eight engineered features per transaction, built to catch what a fixed rule set cannot specify in advance. The third is three independent AI analyst runs, each working from an identical pinned briefing and the same public data, blinded to each other's output and to the answer key, and required to explain every flag or stand it down with evidence.

Before any of the three layers saw the ledger, 87 anomalous transactions across eight classes were planted into it, alongside 18 transactions designed to be entirely benign yet certain to attract flags: a landlord's rent that happens to fall on a round number, an agreed Saturday stocktake, a genuine coincidence of two equal invoices from the same vendor. All of it is recorded in a held-out answer key, and the results are marked against it.

## What the rules caught

The rule layer found everything it was built to find. Against the 87 planted anomalies, the seven tests raised 64 flags. Forty-eight of those land on a planted anomaly, a 75% first-pass precision rate. Recall on the rule-shaped classes (duplicate invoices, round sums and near-threshold amounts, weekend postings, mis-posted accounts, split purchases) is 100%.

The other 16 flags land precisely on the ledger's designed benign bank: 12 months of a landlord's rent at an exact, contractual €15,000, two agreed Saturday postings for a stocktake with the memo saying so, and one coincidental pair of identical-amount invoices from the same vendor that turn out, once the purchase-order references are checked, to be two genuinely separate deliveries. A rule test that flags round numbers cannot tell a contract from a habit on its own, and a first pass over this ledger does not try to. That quarter of the flag list is the triage burden the rest of the case exists to test. A practitioner's second pass would clear most of it before anyone has to look. Suppressing recurring identical amounts silences the rent flags within a week of use, and a materiality floor removes the smaller round sums that carry no risk regardless of pattern. Those refinements are standard practice.

## What the model caught

The Isolation Forest raised 200 flags. None was a planted anomaly.

Three causes explain the miss. First, the feature measuring how unusual an invoice is for its own vendor is built from that vendor's full-year average, so a vendor whose whole year drifts upward drags its own yardstick up with it. The one vendor engineered to drift, ending the year about 19% above where it started, reads as only mildly unusual against itself, a peak deviation of about 2.1 standard deviations, where a clean baseline would put the same invoices at around 6.5. A slow-moving problem inflates the average it is measured against. Second, two of the largest one-off purchases in the ledger (a €78,400 machine and a €24,600 annual insurance premium, both legitimate but exactly the size a controller would expect a detector to notice) sit on vendors with a single invoice each. With no purchase history to compare against, the detector had almost nothing to work with beyond the raw amount, and both ranked deep in the ledger (9,069th and 6,641st of 50,000), nowhere near the flagged tail. Third, against fifty thousand transactions with naturally wide, heavy-tailed swings in amount, a genuine 19% shift on one vendor barely moves the population-level statistics the detector is actually reading.

Reaching the design's own bar (flagging at least 6 of the drift's 12 elevated invoices) would need a flag list reaching rank 14,667 of 50,000, which is 29% of the ledger. A follow-up analysis recomputed the vendor baseline using only prior invoices instead of the full year. That single change moved the drift's best-ranked invoice from 818th to 98th, roughly an eightfold improvement, and for the first time put one of the twelve elevated invoices inside the top 200.

## What the analysts did

All 264 flags from both automated layers were grouped mechanically into 39 assessed groups, 13 on the rule side (one per vendor or user carrying a rule flag) and 26 on the detector side, covering the 200 model flags across vendor-level clusters, a top-ten list of the highest individual scores, and one catch-all for everything left over, including the ledger's December procurement peak. Each of the three blinded runs had to call every group a genuine problem or a false alarm, with evidence, and the three runs called 37, 35 and 38 of the 39 correctly.

All 26 detector-side groups were correctly cleared by all three runs, each backed by recomputed evidence: allowed accounts, within-vendor ranges, no supporting rule flag. None of the 200 statistically unusual but genuine transactions was misidentified as a problem.

The handful of misses were plausible readings, not careless ones. One run took round-thousand-euro invoices as contract-style billing and weekend postings as flexible working; another accepted partial-delivery wording at face value and stood down three split-purchase events. Each sounds defensible against the memo text and each is wrong against the key.

The standout finding, reached independently by all three runs, is a supplier that exists in the vendor master as three separate records under three near-identical spellings, sharing one VAT number and one address, paid into three different bank accounts, with spend split roughly 7:5:3 across them. No rule test in this design was built to catch it (matching vendor names byte for byte gives it a clean pass), so it surfaced only because each analyst, unprompted, compared vendor records against each other instead of reading the ledger row by row. All three runs made it their top-priority action, and all three gave the same complete mechanism.

## The story nobody caught

This case was built around one story in particular, and no layer found it.

From July, one vendor's invoices begin folding freight charges into the price of the goods themselves (the memos say so, in Finnish, "sis. rahtikulut", "incl. freight costs"), an 8% step up in the invoiced amount. But once freight sits inside the bundled price, a further price rise hides inside the same line, another 2% a month, compounding, so that by December the vendor is billing about 19% above where the year started. The evidence for this sits in the ledger twice over. It is there in the memo text itself, and again in the freight carrier's own billing on that route, which drops by about €924 per invoice once the delivery portion moves elsewhere, close to the €880 that shifted into the bundled goods price. That mirrored fall would confirm the mechanism to anyone who set the two vendors' invoices side by side.

Nothing caught it. The rule tests were never built to look for a slow price drift, by design. The detector's best-ranked invoice among the twelve affected sat 818th of 50,000, nowhere near its 200-flag cut-off. And each of the three analysts had room in their brief for a bounded, self-directed look at anything in the ledger, and used it elsewhere. A shift of roughly €1,800 a month on one vendor is easy to miss inside account-level monthly totals; it only shows up when someone compares a vendor's trend against its own history, which is a different exercise from screening a ledger for outliers.

The design also planted one anomaly deliberately built to be uncatchable with this data. Twelve unremarkable monthly invoices from a consulting firm, ordinary in every visible respect, are distinguishable from a real problem only with data this purchase-ledger extract does not carry (contracts, deliverables, a match against goods received). Nothing flagged it, and none of the three analysts accused it without evidence. The case set out with one class nothing could catch and finished with two, because the vendor whose invoicing quietly changed went unclaimed by rules, model and analysts alike.

## What a production system adds

These are places where a real engagement adds a data source this purchase-ledger extract deliberately leaves out, so the result shows what each layer can and cannot see on its own.

Three-way matching (invoice against purchase order against goods receipt) would have caught the ceiling class outright, since an invoice for nothing delivered has nothing to match against; this ledger carries no purchase orders or receipts by design, because that data is exactly what makes the match possible. Vendor-master hygiene keyed on VAT number and IBAN, with fuzzy name matching, would have turned the vendor-variant finding into a routine data-quality check. Recurring-identical suppression and a materiality floor on the rule layer would clear most of the designed benign flags, the contractual rent chiefly, before anyone has to look at them. And a standing per-vendor review, comparing each vendor's spend trend against its own history, not against the ledger as a whole, is the one method in this case that would have surfaced the freight-and-price story, and it is a report, not a model.

The lesson across all three layers is to test a detector and an analyst against something known before trusting either. The rule layer's 75% precision, the detector's zero overlap with the planted anomalies, and the analysts' 37, 35 and 38 out of 39 are only knowable because a held-out answer key existed. A real ledger has no such key. What transfers is the habit of checking a system's output against a reconciled control total, a known incident, or a manual sample, before deciding any of it can be trusted unattended.

## Method note

Every figure in this case study comes from a seeded model (`RANDOM_SEED = 42`), fully regenerable from the published code, with the 87 planted anomalies and 18 benign exceptions recorded in an answer key that stays out of the rule tests, the detector's features, and every file the analysts were allowed to open.

The three analyst runs are Claude Code subagents (Opus), run sequentially and mutually blinded to each other's output and to the answer key, each given an identical pinned briefing and the same seven data files. Each run recorded the full list of files it opened before finishing, and all three lists came back clean: the seven whitelisted inputs, and nothing else. No cost figures are claimed for this layer.

Where 05 Board Reporting works top-down (the variance analysis names the story before anyone goes looking) this case works bottom-up, letting rule tests and a statistical detector surface candidates and reasoning agents explain the ones that need explaining; together the two bracket what "the data storyteller" theme means in practice.

The pipeline itself runs in order from the case study's `code/` folder. `generate_ledger.py` builds the ledger, vendor master, chart of accounts and calendar from the seeded model, alongside the held-out answer key; `validate_ledger.py` checks thirteen coherence rules and exits on any failure; `rule_tests.py` implements the seven audit tests; `detect_anomalies.py` runs the Isolation Forest (200 trees, contamination fixed at 0.4%, 8 features per transaction: log amount, a vendor-relative amount z-score, invoice cadence against the vendor's own rhythm, day of week, a non-working-day flag, account rarity within the vendor, month, and a vendor's monthly-volume z-score, seeded for exact reproducibility and verified deterministic by hash comparison across independent runs); `prepare_clusters.py` groups all 264 flags into the 39 assessed groups; the three analyst runs, each given the same pinned briefing, produce the findings files and memos; `evaluate.py` marks all three runs against the answer key mechanically; the adjudicated scorecard at `data/analysis/report.md` was then written by hand from that worksheet. The analysis notebook (`notebooks/anomaly_detection_analysis.ipynb`) walks every headline number live from the underlying files, including the contamination ablation and the post-hoc detector variant described above; the interactive page (`interactive/anomaly-detection.html`) steps through the catch matrix and all 39 assessed groups, run by run.

The numbers above come from this synthetic ledger and its held-out answer key. No real company, named or composited from real clients, sits behind any of it.

## 6b – the standing vendor-drift review

The initial screening missed the drift. The method that would have found it is a standing review of each vendor against its own history, which is a report, not a model. What follows builds that review, sets expectations for what it should catch, and runs it on a year of ledger it has never seen.

### The data and the method

The ledger is Saarnitukku Oy's next financial year, generated from the same code family under a fresh seed. It runs to about 50,000 posting lines for calendar 2026 across roughly 200 vendors, net of VAT, on the same approval tiers as the first year. Three sustained price drifts were planted in it: one fast, about 2.5% a month from April; one slow, about 1.0% a month from February, which is the sensitivity test; and one repeating the mechanism the first year was built around, freight folded into goods prices from June with a further 1.8% a month compounding inside the bundle. Two benign lookalikes were planted alongside them, a contractual indexation step of 5.2% on 1 January with the index clause cited in the memo, and a market repricing of about 9% announced in August. The ledger is otherwise clean of the eight anomaly classes the first year carried, because this exercise tests one claim only.

The method is arithmetic. For each vendor and each month it takes a volume-weighted mean unit price, builds a baseline from the expanding mean and standard deviation of every prior month, standardises the current month against that baseline, and accumulates those deviations into a one-sided CUSUM. A month is scored only if the vendor billed at least three invoices in it, and scoring begins only once three months of baseline exist. A vendor is reported when its CUSUM passes 4.0. The output is one ranked table plus a trajectory for each reported vendor (months, prices, baseline, deviations, the month of first crossing). There is no model to train and no agent layer.

Every parameter (the 3-invoice monthly floor, the 3-month minimum baseline, the CUSUM slack of k = 0.5, the threshold of h = 4.0) was fixed before the second ledger existed, and none was changed afterwards. Six expectations were written down at the same time, covering where each planted drift should rank, when its CUSUM should cross, how the benign pair should behave, how many unplanted vendors should cross, and what the same report should do run backwards over the first year's frozen ledger. Four were met and two were not.

### What the report caught

Of the 200 vendors, 195 cleared the three-invoice floor in enough months to be scoreable at all. All five planted items were flagged.

The fast drift (Louhimalmi Oy) ranks 2 of 195 at a peak CUSUM of 26.79 and first crosses in May, against a designed start in April and an expected crossing by June at the latest. The bundling drift (Rantavalssi Oy) ranks 3 at 26.76 and also crosses in May, ahead of its designed June step; the earliest part of that signal is ordinary pre-drift monthly noise, not the bundling mechanism, and from June onward (a standardised deviation of 9.16 that month, and a rise every month after) the crossing is driven by the drift itself. The slow drift (Ahoharkko Oy), the sensitivity test, ranks 5 at 11.49 and crosses in July.

Both benign lookalikes surfaced, as the design said they should. The August repricing (Virtakanki Oy) ranks 1 of 195 at 32.71, crossing the threshold in a single step in August on a standardised deviation of 27.84, the sharp one-month excursion the design anticipated. The January indexation (Kiviaihio Oy) ranks 34 at 4.59, crossing in July, which is well down the list but not a silent pass. Neither is distinguishable from the three real drifts by the shape of its trajectory. They separate only on the memo trail, the index clause and the announcement, and a drift report cannot read a contract. Four of the top five ranks in the report are planted items.

### The flag count floods

Forty-seven vendors crossed the threshold, 42 of them unplanted, against an expected ceiling of about five. The cause is mechanical and sits in the method's own parameters. The first scored month builds its baseline from exactly three prior months, and the sampling distribution of a three-point standard deviation is wide enough that an unusually tight opening baseline is common; the next month's ordinary noise then reads as a large standardised deviation.

What survives is the ranking. Most of the 42 sit well below the planted items by peak CUSUM; a controller reading the top ten rows of the ranked table sees every planted item and almost none of the chance flags. The usable instruction is to read the top of the ranked list, not the full set of 47.

### The blind spot

The same report, unmodified, was also run backwards over the first year's frozen ledger. That run is in-sample by definition, since the fix was designed from that year's diagnosed failure, so a clean catch there would have demonstrated the diagnosis, not the method's power.

It was not a clean catch. Teräskontio Oy, the vendor whose quiet drift the first year's story was built around, is not scoreable. It posts 24 invoices across the year, two a month, every month, and the method's own floor requires three invoices in a calendar month before that month can be scored or even enter a baseline. It clears the floor in 0 of 12 months. It has no rank, no peak CUSUM and no trajectory; it does not appear in the ranked table at all, where 177 of that ledger's 200 vendors do. The expectation was a top-three rank with a first crossing by October.

This is a different failure from the one diagnosed in the first year. There, a sustained drift inflated the full-year baseline it was measured against and erased its own signal. Here the arithmetic never runs. The two design choices that collided (a story vendor invoicing twice a month, fixed for reasons of its own, and a 3-invoice monthly floor, fixed months later for the follow-on review) were made independently and neither was written with the other in view.

### What it adds up to

The review works on its own terms and on data it had not seen. All three planted drifts and both benign lookalikes were flagged, at ranks 1, 2, 3, 5 and 34 of 195, with the slow 1%-a-month drift caught by July. The method is a page of arithmetic a controller can read in ten minutes and check by hand.

It also has two limits. Its flag count is not usable as a count, for a reason that belongs to the parameter, not to the data, while the ranked list that same run produces is. And it cannot see a vendor that bills too rarely to build a monthly baseline, which is the vendor that prompted it. A method for sparse vendors (longer windows, invoice-level baselines, or a different statistic altogether) is a separate build, and it is not in this case.

The figures in this section come from the same discipline as the rest of the case study. The FY2026 ledger is synthetic, seeded (`RANDOM_SEED = 2026`) and fully regenerable; its five planted items are recorded in an answer key that the report script never opens, read only by the marking script; and the first year's files were hashed before and after every run of this second exercise and are byte-identical throughout.
