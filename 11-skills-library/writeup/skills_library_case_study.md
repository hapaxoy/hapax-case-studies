# Sixty questions, and what happens when you write the rules down

*An invented company, real measurements.*

Exemplum &middot; hypothetical

## A Tuesday

It is Tuesday morning and the data queue has its usual traffic. One request reads: "Like-for-like growth by region for Q3 last year, please."

The analyst who picks it up knows what that means. Like-for-like at this company means stores open for at least a full year, with weeks closed for refitting taken out of both years, the 53rd week excluded from any long fiscal year, and history restated on the current region map. She opens the query she wrote last quarter, changes the dates, checks the result against the store operations report, and sends it back to finance.

Now imagine the company has started using an AI assistant to draft the first version of these queries. The assistant has access to the same database. It can read the fiscal calendar, the region history, the closure records. It can write a like-for-like query that runs and returns a plausible number. But nobody has told it which stores the company counts as comparable, or that week 53 is excluded, or that regions are restated and not reported as they were at the time. The tables hold the data. The rules about how to use it are in the analyst's head, and in a handful of pinned notes in the team wiki, and nowhere else.

The number that comes back will be plausible, and wrong. The person who asked for it will have no easy way to tell, because the answer looks reasonable, the query runs without errors, and the response arrived faster than it ever has.

## One question

Take the like-for-like question. Eight words and a "please," and at least three of the company's private rules are buried in it.

Without the rules, the assistant read the database well enough to get the fiscal calendar, the current regions and the refit closures right. What it got wrong was which stores are comparable. It made its own guess, and the only corroboration in the database was a pair of old tables listing 37 like-for-like stores, left over from earlier years and never cleaned up. One run stated that it was following "the company's LFL store lists." The lists left out the two newest stores, one of which the company's rule already counted as comparable for this quarter. No other table in the database contradicted them.

In four of five runs, it dropped Tampere Lamminpää, a store that opened in September 2024 and that the company counts as comparable by Q3 of the following year. West-region growth came back at 2.0% instead of 4.8%. The fifth run kept that store but dropped another for a different reason, and got the North region wrong. Each run produced a query that ran, a result that looked reasonable, and a number that was wrong. Four of the five gave the same wrong answer. A user who checked by asking twice would get the same figure back.

With the written rules, a single record of the company's definitions, the assistant applied the right like-for-like rule, including which stores qualify and on what basis, and got the right number in all five runs.

## Sixty questions

The like-for-like question is one of sixty. Tuomimetsä Oy is a fictional Finnish retailer, with about 1,100 staff, 38 stores and a nine-person data team. The company, the data and the sixty requests were all engineered with the correct answers written first and held out, so that each setup's errors can be counted exactly. The full design is in the methods section below.

If your company has 100 or 200 people, you probably do not have a data team. You might be the one person who runs the reports. But you have rules, and the problem is the same.

Across all sixty, accuracy without any written rules was 49.7%. With the rules in a single written document, 99.3%. That is a gap of 50 percentage points, and the whole gain came in one step. Whether the rules were in one document or ten packaged handbooks made no measurable difference.

## A cheaper model

We also ran two of the setups, database only and the library, on a smaller model, the kind that is cheaper to run. Without the rules, it scored 29.7%. With the library, 79.0%, which is 29 points above the main model working without rules. These models are billed in tokens, and the smaller model with written rules used about half as many per correct answer as the main model needed without them. Writing the rules down did more for accuracy than paying for the stronger model.

## Problems nobody wrote down

Four of the sixty requests hit a data problem that nobody had documented. One store had a week of till receipts posted twice, pushing it from seventh to third in the league table. Web orders in one period had lost their member links. Two more problems sat quietly in the data, mentioned nowhere.

The assistant without rules found all four in all 20 of its runs and tried to fix each one. It was right on only 5, because the rest of each answer still depended on guessed company rules. The company ranks its store league table per trading day, for instance, and the bare assistant used total sales.

With the rules, all 20 came back right. On three of the four problems, the assistant noticed the issue and repaired it. On the fourth, the standard query takes a route that does not touch the bad data, so a correct answer there does not by itself prove the problem was found.

The written rules advise checking source rows for duplicates. That advice was added after two of these problems had already been found while the rules were being written. The assistant without rules found all four on its own.

## What we got wrong

Before the runs, we wrote twelve predictions and froze them. Six were wrong. The full list is in the methods section.

Our biggest miss was the ceiling. We expected the written rules to take accuracy to somewhere between 65% and 85%, and they reached 98 to 99%. The bare model was also more consistent than predicted, giving the same wrong answer in all five runs on eight of the sixty requests.

## What it means

Your company has rules that determine whether a number is right. They are almost certainly not written down in a form that any tool can read. Write them down. A single document is where to start.

---

## How we tested it

**Tuomimetsä Oy** is a fictional Finnish home-and-garden retailer with about 1,100 staff, 38 stores, a web shop with click-and-collect, and a nine-person data team. Its database has 15 main tables and about 20 objects of clutter (staging tables, dated backups, stale views), including a fiscal calendar that starts on the Monday nearest 1 May, stores that open, close and close for renovation, a web-platform migration, category and region reorganisations, and stock snapshots that are semi-additive. The company was invented so that every rule and every data problem would be known in advance and recorded in an answer key.

**Sixty requests** were written from the kinds of questions the data team receives. The correct answer to each was worked out and locked away before any assistant saw the requests. Ten paraphrase pairs (the same question asked two ways) test whether two departments would get the same number.

**Four setups,** each differing only in what the assistant was told about the company's rules.

*Database only.* Table and column descriptions, realistically annotated, but no company definitions or conventions. This is roughly what happens when a company gives an AI assistant access to its database and starts asking questions.

*Shared document.* The same database, plus a single written document of the company's metric definitions, fiscal-calendar rules, known data-quality issues, and worked examples from past requests. Written with the same care as the library, so that any difference measures the format, not the quality of the writing.

*Library of handbooks.* The same knowledge in ten small handbooks the assistant opens on demand. A like-for-like question opened the like-for-like and fiscal-calendar handbooks in every run; across the sixty requests the median was five handbooks per run.

*Library without check programs.* The same handbooks, minus the small programs that verify date ranges, flag duplicates, or reconcile against a control total. Separates what the assistant knows from what it can run.

The rules (both the document and the library) were written by a separate AI agent working in isolation from the answer key.

**Runs.** 60 requests &times; 5 runs &times; 4 setups = 1,200 on the main model. The database-only and library setups were also run on a smaller, cheaper model (600 runs). 1,800 in all.

**Isolation.** Each run was restricted to its own materials and its activity was logged. The isolation is a checked log, not an operating-system sandbox. All 1,800 logs were reviewed afterwards, and none showed a run reading anything it should not have.

**Marking.** Automatic against the held-out key, with 0.1% numeric tolerance. Borderline cases were judged blind to which setup produced them.

**Twelve predictions** were written and frozen before the runs. Six were met and six were not.

| # | Prediction | Verdict | Numbers |
|---|---|---|---|
| 1 | Written-rules setups land between 65% and 85% | NOT MET | 98&ndash;99% |
| 2 | Writing rules down does most of the work; packaging adds nothing measurable | MET | D &minus; S = 49.7pp; L &minus; D = &minus;1.0pp |
| 3 | All setups above 85% on the 14 clean requests, within 5 runs of each other | MET | All 70/70 |
| 4 | Bare model gives different wrong answers on different runs (&le; 27 of 60 with same answer all 5) | NOT MET | 33 |
| 5 | Bare model agrees on &le; 5 of 10 paraphrase pairs | NOT MET | 9 |
| 6 | Bare model gets &le; 12/60 right on the 12 company-definition requests | NOT MET | 19 |
| 7 | Written rules cause &le; 2 overrides of explicit requests | MET | 0 in every setup |
| 8 | Library &ge; 8/20 right on undocumented problems; bare &le; 3 | NOT MET | L 20/20; S 5/20 |
| 9 | Library uses more tokens per run than the document | MET | 5% more |
| 10 | Cheaper model with rules beats main model without | MET | +29 points |
| 11 | Check programs add nothing measurable | MET | L&minus; slightly higher on correctness |
| 12 | Library scores &ge; 10pp lower on requests without a worked template | NOT MET | 98.5% vs 98.3% |

**Selected findings.**

*Clean requests.* The 14 requests designed with no company rule scored 70 of 70 in every setup on the main model, every run. The assistant writes competent queries; its failures sit entirely in the company rules.

*Company-defined metrics.* Twelve requests ask directly for a company-defined metric. Without rules, 19 of 60 runs right; ten of those were two return-rate requests where the assistant's own reading matched an alternative the answer key accepts. With written rules, 60 of 60.

*Consistency.* Without rules, the assistant gave the same answer in all five runs on 33 of 60 requests and made the same wrong choice on 8 of them. It agreed on 9 of 10 paraphrase pairs, including 6 where both wordings gave the same wrong answer.

*Rigidity.* No setup, including the bare assistant, ever applied a company default against an explicit request.

*Scripts.* The library without check programs scored slightly higher on correctness than the full library, both overall (297 vs 295 of 300) and on the twelve requests the programs were aimed at (59 vs 56 of 60).

*No-template requests.* The library scored 98.5% on the 13 requests where it had definitions but no worked example, against 98.3% on the rest.

*Tokens.* The library used about 5% more tokens per run than the document (median 85,100 against 80,897). The cheaper model with the library used about half the tokens per correct answer as the main model without rules (74,551 against 146,656). These are the totals each run reported; they are not a measured cost.

**Limits.** The written-rules setups hit the ceiling, and this case cannot separate whether that is because the rules were well written, because the requests were easy for an assistant that has them, or both. Tuomimetsä's database has 15 main tables; a real database at this size of company has hundreds. The requests are synthetic, and the margins on individual trap classes are wide. The document, the library, the sixty requests and the answer key are published in this repository.
