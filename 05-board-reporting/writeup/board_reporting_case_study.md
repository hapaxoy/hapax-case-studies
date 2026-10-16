# Board Reporting Automation

## A pack that is right and still incomplete

A competent finance team's monthly board pack is usually correct. Material costs up 12%, gross margin down 2 points, and the number is right. What the pack rarely carries is the cause. The cause usually sits three drill-downs below the line item, in a table nobody has time to open before the meeting starts. So the obvious explanation goes into the commentary – "input cost inflation", "seasonal", "on plan" – the board moves on, and if it is wrong, the real cause keeps costing money for another two quarters, unremarked.

This case study tests whether an AI layer, working from the same numbers the finance team already has, can close that gap. It has to find the cause behind a flagged variance, or say plainly that a scary-looking number needs no story at all.

## What we built

Everything in this case study is synthetic. Paju Consumer Products Oy is a fictional Nordic personal-care and home-care manufacturer (3 business units, 4 product lines, roughly €155M net revenue and 480 people in the base year) generated in full by a seeded Python model. It is not a real company, and none of the figures below describe a real client's data.

Four scenarios were hidden in the data before a single analysis saw it, each with a designed mechanism, magnitude and answer, held out in a separate answer key file nothing in the pipeline touches. A Nordics margin move that reads as commodity inflation is actually a discount-and-mix shift into a material-heavy product line. In Central Europe, a warehouse sale-and-leaseback keeps reported EBITDA on plan while one customer's payment terms quietly drift out underneath it. Baltics revenue growth turns out to be substantially bought with escalating discounts. And the fourth scenario is a trap. January shows a revenue collapse that is pure seasonality, identical to the prior year and to budget, the kind of number that could easily be narrated into a crisis. The correct answer is to stand down.

## Two layers, not one

The case study runs two layers over the same data.

The first is deterministic (pandas, not an agent). It computes budget-vs-actual and year-on-year variance at company and business-unit grain, decomposes revenue and cost moves into price, volume and mix, tracks the standard KPI set, and flags anything that breaches a threshold. This layer is fast, exact and free to run. Over the full two-year dataset, it raises 327 mechanically correct flags and attributes zero of them. A threshold breach is a fact about a number, not an explanation of one.

The second layer is 3 independent analyses (Claude Code subagents, not a fine-tuned model) each given an identical pinned briefing, the nine public data tables and the deterministic pack, and told to use nothing else. None saw the answer key. The runs were sequential and blinded. Each was barred from the earlier runs' output and ended its transcript with a list of every file it opened, so the audit trail can be checked independently; all three lists contain only permitted files, and none opened the answer key, the design documents, or another run's work. No API costs were metered, so no cost figure is claimed for the agent layer.

Each run had three jobs. For every one of the pack's six recurring flag clusters it had to explain the cause with cited evidence, or say "stand down" and show why. Beyond the clusters, it had to surface anything material the pack missed, and write the whole thing up as a findings file plus a one-page board memo. A wrong cause counts against a run, and so does a false alarm.

## What the analyses found

All three runs, independently, landed on the same three board actions and the same three stand-downs.

All three traced the Nordics cost rise to its cause. Every run reported flat unit material costs – the decisive fact the pack itself cannot see, since it never computes cost per unit – and traced the 11.5% material-cost rise to a promotional discount that jumped in a single month, Nordics Home Care from 6.0% to 18.8% of gross, alongside a volume shift into the material-heavy line. Each filed the material-cost flag itself as "stand down, not a procurement problem" and moved the real finding into a margin flag instead, a sharper split than the design expected.

The Central Europe receivables scenario was designed to be the hardest of the four, since it requires connecting four tables while every headline metric looks fine. All three found it. Each named Rheinkauf Gruppe, the business unit's largest customer, from the per-customer receivables table, and cited the same figures for it – a receivable balance that more than doubled over the year, from about €2.06M to €4.49M. Each linked the April sale-and-leaseback (a €2.2M other-income gain, €5.5M cash) to the flattered headline, and each computed a cash-conversion deterioration once the one-off was stripped out; one run put the underlying operating-cash fall at about €3.4M against a €3.9M build in receivables.

Baltics growth turned out to be bought, and all three runs said so. The pack's headline read as good news – company revenue up 8.6%, ahead of plan – but a disproportionate share of it traces to one business unit, Baltics & Poland, where revenue rose 27% funded by discounting that escalated from around 8% to 17% of gross. One run went further and quantified the combined cost directly. Across Nordics and Baltics together, discounting handed back about €5.9M in FY2025 against holding 2024 rates, split roughly €3.6M and €2.3M between the two, a figure that checked out on verification.

The trap held too. All three runs correctly stood down on the January collapse, a 28.7% month-on-month drop that reads as alarming in isolation, citing the same seasonal pattern present in the prior year and in budget. No run cried wolf anywhere else in the dataset either.

Across all 3 runs (30 findings in total) there were no false positives among those worth acting on, and no cited figure turned out to be wrong. A mechanical check flagged eighteen apparent figure disagreements across the runs; each turned out to be a correct number quoted on a different, clearly labelled basis.

## The evidence nobody pulled

The two sharpest pieces of evidence in the Baltics scenario went unexamined. The dataset was built so that three of the business unit's ten named accounts – Balticum Retail, Polska Handlowa and Sūduvos Prekyba – carry discount rates above 18% by the end of the period, and so that the volume response per euro of discount fell by roughly 38% between the first half of the year and the second, the signal that the growth strategy is running out of road. Every run found that discounting was buying the growth. No run pulled either exhibit. One run checked customer-level revenue concentration, found it broad, and stopped one column short of discount concentration.

A single-pass investigation finds the mechanism behind a flagged variance reliably. It does not reliably go looking for evidence nobody pointed it at.

## What transfers to a real ledger

The mechanics would run the same way against an actual monthly close: a deterministic variance layer first, then independent, blinded analyses each committing to a verdict with evidence for every flag, then a check of what came back.

The answer key does not transfer. A real ledger has none. Running on synthetic data first lets you measure what a single pass catches and what it leaves behind, while an answer exists. Three independent runs agreed on all three board-action findings and all three stand-downs, and still left the sharpest Baltics evidence unexamined. On real data, the same checking has to be built in from the start.

## Appendix

The pipeline runs in five steps from the case folder. `generate_financials.py` builds the nine data tables and the held-out answer key from a seeded driver model (`RANDOM_SEED = 42`, byte-identical on every run); `validate_financials.py` checks all twelve coherence rules and exits with failure on any breach, with every total reconciling to the cent; `variance_analysis.py` produces the deterministic board pack; three blinded Claude Code subagent runs, each given the same pinned briefing, produce the findings files and memos; `evaluate.py` marks all three runs against the answer key into a mechanical worksheet; the adjudicated scorecard this write-up draws from, `data/analysis/report.md`, was then written by hand from that worksheet.

All code, all generated data, the answer key and the full evaluation worksheet are public in the case study folder. The analysis notebook (`notebooks/board_reporting.ipynb`) walks the pipeline end to end. The interactive page (`interactive/board-reporting.html`) lets you step through a month of the pack, see what it flagged, and compare that against what the analyses found.
