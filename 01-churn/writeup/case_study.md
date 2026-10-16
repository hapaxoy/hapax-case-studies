# Hybrid Churn Intelligence

### What a usage-based churn model catches, what a support-ticket reader catches, and what a CFO does with the difference

*This case study runs on synthetic data, engineered by us with a held-out answer key, so every result could be marked against ground truth. "Kataja Analytics", its customers, and its competitors are fictional. No real client is described or implied anywhere in this document.*

---

## 1. The account that looked fine until it wasn't

Kataja Analytics is a Helsinki-based B2B SaaS company selling a dashboards-and-reporting platform to mid-market firms, roughly 500 accounts, Nordic and European, 10 to 200 seats each. Its customer success team runs a standard churn model on usage levels, trends and seat utilisation. It works. It catches the accounts whose logins taper off, whose report volume visibly declines before the cancellation email arrives.

It did not catch Hedbrunn Systems AB.

Hedbrunn, a Swedish construction firm with 31 seats on the Standard plan at €12,426 a year, used the product normally right up until it left in November 2025. Its usage numbers never moved. What moved was the tone of 4 support tickets over 9 months, the last closing with "no need to treat this as urgent." A dashboard reconciliation problem that made 2 colleagues quietly start doing the board pack in Excel again. A report template that kept reverting to default, so the team stopped asking after the fourth time. Nobody escalated, nobody used a harsh word, and the account cancelled anyway.

That is the shape of churn a usage dashboard cannot see. The account behaves normally while trust erodes somewhere a spreadsheet does not reach. The support inbox had the story. Nobody had time to sit down and read months of ticket history for every one of 500 accounts, looking for a pattern like this.

This case study builds a second detector that does exactly that job. An agent reads each account's ticket history in order and produces a risk score and a short explanation, which is then combined with the usage model's score. The only question that matters commercially is whether the combination catches more than either one alone, and what that difference is worth.

## 2. The finding

Two things are true at once. The classical usage model is good on its own terms (AUC 0.899 on a held-out test split, gradient boosting), a fair baseline for anyone selling "an ML churn model" by itself. Read alongside a text layer and evaluated fairly across the whole account book, the combination catches more of the accounts that matter and misses fewer euros.

Scored out-of-fold across all 500 accounts, against the answer key:

| Approach | AUC | Average precision | Recall @ top-100 |
|---|---|---|---|
| Usage model only | 0.867 | 0.777 | 0.594 |
| Ticket-text agent only | 0.795 | 0.705 | 0.586 |
| Combined | 0.890 | 0.845 | 0.662 |

Recall at top-100 is the practical number here. If a CS team can review 100 accounts a cycle (a fifth of the book), this is how many of the truly churning accounts make that list. Usage gets 59.4%; text gets 58.6%, by a different route. Combined gets 66.2%, 9 more genuine churners for the same review effort.

The more useful cut is where each method's hits land. Split the top 100 by which layer flagged the account:

| | Text flags trouble | Text says fine |
|---|---|---|
| **Usage flags trouble** | 59 accounts, 57 churners | 41 accounts, 22 churners |
| **Usage says fine** | 41 accounts, 21 churners | 359 accounts, 33 churners |

Both layers agree in the top-left cell, and they are right almost every time. Bottom-right is the combined miss, covered in section 5. Both cross-cells carry the argument. Usage alone flags 22 churners that the text layer missed; the text layer, in turn, flags 21 churners that usage missed entirely. 18 of that second group are the "quietly unhappy" type, Hedbrunn's type, the commercial case in one number.

**The money segment, counted directly against the answer key:**

| Method | Quietly-unhappy accounts caught, of 46 |
|---|---|
| Usage model | 23 (50%) |
| Text agent | 34 (74%) |
| Combined | 37 (80%) |

Attach revenue. Total ARR inside accounts that actually churned comes to **€6.53M**. Usage alone surfaces €3.71M of that within its top 100; text alone, €4.14M; combined, €4.57M. The figure for a CFO's desk is that delta between the first two. **The text layer surfaces €1.14M of churned ARR that the usage model, alone, does not**, because those accounts looked healthy on every dashboard metric until the invoice stopped renewing. Usage returns the favour in the other direction, adding €716K in accounts the text layer under-weighted. Neither layer subsumes the other, which is why combining them is the finding.

## 3. Three accounts, in their own words

**Hedbrunn Systems AB** (quietly unhappy, churned). The agent's read: *"a dashboard/export reconciliation mismatch... two of my colleagues have gone back to reconciling manually in Excel before each board pack, just so we're not presenting numbers we can't trust... a report-builder template reverting for the third time since spring... the customer has quietly built workarounds around problems that keep recurring and is asking for less each time, not more."* Text risk score: 0.75. Usage-model risk score: 0.04, near the floor, exactly as designed.

**Lumikarpalo Oy** (loud but loyal, retained, a large Finnish public-sector account, €117,767 ARR). 18 tickets over 13 months, some with real edge: *"Connector's down again, same Salesforce auth issue as before. Feels like we're doing your reauth job for you"* and, 8 months later, *"I feel like I send this exact ticket every quarter."* Every ticket resolved within a day or two, no competitor ever mentioned. On tone alone, the text agent scored this account 0.70, high enough for its own top 100. It is not at risk. It has been complaining and renewing on schedule since signup; if irritation predicted departure, it would have left long before now.

**Zeggeveld Group B.V.** (also loud but loyal, retained, a Dutch healthcare account, €17,421 ARR). 29 tickets in a year, recurring faults, fast fixes, no drop-off. Text score: 0.55. Usage score: 0.006. Combined score: 0.20, well outside the reviewable range. This is fusion doing its job. The text layer's caution gets outweighed by everything else the model knows, and the account drops off the list. Lumikarpalo did not get the same treatment, and stayed near the top of the combined ranking anyway. Section 5 explains why.

## 4. How it works, briefly

Two independent reads of each account, combined by a third, small model:

- **The usage model.** Usage levels, three- and six-month trends, module mix shifts, seat utilisation, fed to a gradient-boosted tree model (a logistic regression baseline runs alongside for comparison, AUC 0.782 against 0.899). Ticket *counts* and resolution times are included as metadata, deliberately, since any CS ops team already has that data whether or not anyone reads a ticket. Ticket *content* is not included here.
- **The text agent.** For each account, an LLM reads every ticket in order and returns a structured read covering frustration trajectory (improving / stable / deteriorating), unresolved-issue count, competitor mentions with context, whether the account has escalated, a one-paragraph narrative, and a risk score. It never sees usage data or the churn label.
- **Fusion.** A single logistic regression over both scores plus 2 agent outputs (frustration trajectory, count of serious competitor mentions). Standardised coefficients: the usage score is the strongest input (1.32), then frustration trajectory (0.68), then the text score (0.53), then competitor mentions (0.34). An escalation flag pulls risk slightly *down* (–0.16), because in this dataset "the customer escalated and it got fixed" is disproportionately the shape of a saved account, not a lost one. One small, inspectable model on top of 2 others, and nothing here is a black box.

## 5. What each layer misses

Each account here has a planted answer kept away from the models. Each miss below is measured against a known correct answer.

**The usage model was never fully blind to the quietly-unhappy pattern.** It took 4 iterations of data design to make these accounts as quiet as real life allows, and 3 times the model found a path back in. First, satisfaction scores. Quietly unhappy customers stopped filling in surveys, or politely ticked "fine", and the model leaned on unresolved-ticket counts instead; mean risk rose from 0.591 to 0.666. Second, ticket outcomes. Support now closes these tickets promptly even though the fix does not hold, the familiar real-world pattern, with the truth surviving only in the next polite ticket's text. The model shifted its weight onto ticket volume itself, rising again to 0.679. These accounts were then generating 6.65 tickets in a trailing 6-month window against 1.04 for a healthy one, and an account that generates enough tickets to read is generating enough to count. The final redesign made the archetype genuinely quiet, producing 3 to 6 long, courteous, meticulously documented tickets across an account's whole life, the disengagement expressed as going silent. The model's read fell to 0.477, with half of these accounts absent from its top 100 altogether. What visibility remains rides on ticket timing and ordinary closure speeds. Making the archetype fully invisible would have meant making it stop being the thing it models. The figures in this document come from that final dataset.

Even so, the usage model returns a weak, ambiguous flag on these accounts (0.48 mean score, against 0.86 for the archetype it is built to catch), with nothing to explain it. The text layer reads the same account and returns a paragraph a CS manager can act on by lunchtime.

**The text layer over-reads loud-but-loyal accounts, and the other layer corrects it.** 19 of the 55 "loud but loyal" accounts here, Lumikarpalo and Zeggeveld's type, accounts that complain often and renew every time, land in the text agent's own top 100, on tone alone. Fusion catches most of this. Of those 19, 18 drop out of the *combined* top 100 once the usage signal and the escalation-then-resolved pattern are folded back in. Lumikarpalo does not. Its ticket-volume metadata is itself unusually high, so it stays flagged even after fusion.

**Thirty accounts churn for reasons invisible in the product**, such as an acquisition, a budget cut, or a champion leaving. Usage looks normal, tickets are routine. 5 of the 30 land in the usage model's top 100, closer to noise than signal; none land in the text layer's; 2 survive into the combined top 100. There is no signal in the product for either method to find.

## 6. What a CS or finance team does with the list

The combined top 100 splits usefully by ARR and by whether the driver looks fixable.

| Segment | Accounts | Total ARR |
|---|---|---|
| Worth actively saving | 46 | €3.83M |
| Low-leverage (flagged, little to act on) | 54 | €1.30M |

Under a tighter budget (top 50, a tenth of the book), the ranking by euros does not quite match the ranking by headcount. Combined catches the most churners (49), but text-only edges it slightly on ARR (€2.74M against €2.59M), because its unique catches happen to be larger accounts that fall just outside the tighter combined cut. The distinction matters if the actual constraint is reviewer-hours, not a fixed top-100 line.

## 7. What transfers and what does not

The method needs three things from an account base: a written trail held against named accounts, usage or finance metadata of the sort a CS ops team already collects, and a definition of the outcome, meaning which accounts left and when. Support tickets are the written trail here; account emails, CRM notes or call summaries hold the same kind of signal. Most firms selling on subscription already have all three, and the written trail is being paid for whether or not anyone reads it.

The structure carries over. A classical model where the numbers are strong, a reading layer where they are silent, both marked against a holdout, and one small explainable model combining the two. So do the checks that make the marking mean anything: misses counted per archetype, not in aggregate, and scores taken out-of-fold, not from the fit.

What does not carry over is the answer key. Ours was planted before any model ran, which is what makes the figures above markable at all; a real account book offers historical outcomes instead, noisier and arriving later. The figures (0.890 combined AUC, 66.2% recall at the top 100, €1.14M of churned ARR visible only to the text layer) are properties of this dataset and of the archetype mix we chose for it. The narrower claim we would carry to other data is that the 2 layers catch different accounts, and that the overlap between them is partial enough for the second layer to pay for itself.

## 8. Technical appendix

- **Data**: 500 accounts, 24-month window, churn from month 6 onward, 133 churners (26.6%). 3,777 tickets, generated in 2 layers. Deterministic Python controls every structural signal; an LLM writes only the prose, briefed on structure it may not add to or remove from. `answer_key.csv` never touches training or fusion; it exists solely for the evaluation numbers above.
- **Eight archetypes**, from healthy-stable (35%) through slow-decay (12%, both layers catch it), quietly-unhappy (8%, the money segment), sudden-death (5%, the designed ceiling), to loud-but-loyal (12%, the credibility check) and saved-account arcs (10%, the false-positive test).
- **Known artefacts, found and handled**: `tenure_months` is excluded from the trained model because it is a near-perfect churn proxy purely from how the observation window's end date is fixed, confirmed by ablation (including it lifts AUC to 0.955 for the wrong reason). Usage trends are deseasonalised against a portfolio-wide seasonal index, since retained accounts are always snapshotted in the same calendar window and a raw trend feature would otherwise mistake a summer usage dip for churn risk.
- **Models**: logistic regression (AUC 0.782, holdout) as a transparent baseline; gradient boosting via LightGBM (AUC 0.899, holdout) as the production candidate, explained with SHAP. Every `ml_risk_score` in the tables above is out-of-fold (5-fold stratified CV, seed 42), so no account is scored by a model that trained on it. That is a stricter check than the holdout figure, hence 0.867 and not 0.899 in section 2. Top SHAP drivers overall: `ticket_count_3m`, `mean_resolution_days_6m`, `ticket_count_6m`, followed by usage trend and mix-shift features across dashboards, connectors, and alerts.
- **Fusion**: one logistic regression, five inputs (`ml_risk_score`, `text_risk_score`, `trajectory_ordinal`, `n_serious_competitor_mentions`, `escalation_pattern`), fit once on the full 500-account set for explainability; the scores reported above come from an out-of-fold pass, not this illustrative fit.
- **Reproducibility**: one seed (42) throughout, account generation to model scoring. Full pipeline in `code/`; every generated table and the answer key in `data/`. `notebooks/churn_analysis.ipynb` walks the feature build, the model comparison and the fusion evaluation in the order this document reports them. `interactive/churn_explorer.html` carries the same evidence as a browsable page, with per-account scores, the archetype breakdowns behind the tables above, and the ticket history behind each agent read.
