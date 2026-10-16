# Storyteller evaluation — adjudicated results

Everything that went wrong stays in. Written by hand after reading
`evaluation_worksheet.md` end to end and
adjudicating every ambiguous case against the raw findings JSON. The worksheet
(`code/evaluate.py`) is the mechanical layer; this document is the scorecard.

## Method

Three independent storyteller runs (run_01–run_03), each a Claude Code subagent
(model: Claude Opus) given the identical pinned briefing
and nothing else: nine public data CSVs plus the
deterministic board pack and its three companion CSVs. Runs were sequential and
blinded — each was barred from the earlier runs' outputs and scratch folders, and
each ended its transcript with a list of every file it opened. All three audit lists
contain only permitted files; none opened anything under `data/answer_key/`, any
design or code file, or another run's work. The answer key entered the process only
here, at evaluation time.

Mechanism honesty: no API token counts were measured; no cost figures are claimed.

## Scorecard

| Designed item | run_01 | run_02 | run_03 |
|---|---|---|---|
| S1 mix-shift-as-inflation — detected, cause correct | ✓ | ✓ | ✓ |
| S2 DSO creep — detected, customer named, mask linked | ✓ | ✓ | ✓ |
| S3 bought growth — detected, cause correct | ✓ | ✓ | ✓ |
| S3 evidence bar: concentrated accounts named | ✗ | ✗ | ✗ |
| S3 evidence bar: fading elasticity cited | ✗ | ✗ | ✗ |
| S4 January trap — de-escalated | ✓ | ✓ | ✓ |
| N4 budget optimism — noted (bonus) | ✗ | ✓ | ✗ |
| False positives (severity ≥ watch, post-adjudication) | 0 | 0 | 0 |
| Incorrect cited figures (post-adjudication) | 0 | 0 | 0 |

All six briefed flag clusters received the designed verdict in all three runs —
including both stand-downs. The designed 2×2 played out exactly: the pack-visible
alarm with a real story (S1) was explained rather than parroted; the two stories the
pack stays calm about (S2, S3) were surfaced; the alarm with no story (S4) was stood
down with evidence; and no run narrated noise.

## Per-story adjudication

**S1 — found by all three, and more precisely than designed.** Every run asserted
flat per-line unit material costs (the answer key's decisive fact) and attributed the
Nordics margin move to promotional pricing and mix. Two runs identified the February
step-change explicitly (Nordics Home Care discount 6.0% → 18.8% in a single month —
which is how the generator plants it); run_03 added the check that list prices held
vs budget, isolating the leak to promotional discount specifically. Notably, all
three filed the material-cost flag itself as "stand down on procurement" and
delivered the real cause under margin findings — a sharper framing than the designed
expected finding, scored as correct-distributed.

**S2 — the designed "hard" story was found intact by all three.** Each named
*Rheinkauf Gruppe* from the per-customer receivables table with the same core figures
(balance €2.06M → €4.49M; ~87% of the Central Europe build), each connected the
April one-off (€2.2M other income, €5.5M investing inflow) to the flattered reported
EBITDA and cash headline, and each computed a cash-conversion deterioration. run_03
added the discriminating check that Rheinkauf's revenue was flat (+4.4%) — slow
payment, not growth. The per-customer AR table exists in the dataset precisely
because without it this attribution would have been an inference; including it
paid off three for three.

**S3 — found by all three; the designed evidence bar only half-met.** Every run
identified Baltics growth as bought (discount 8% → 17%, margin eroding, opex
outrunning budget) and run_02 quantified the counterfactual give-away (€5.9M vs
holding 2024 discount rates — verified correct). But two designed evidence paths
were taken by **zero of three runs**: nobody examined per-customer discount rates
(three accounts sit above 18% in December 2025 — validator-proven present in
`customer_revenue_monthly.csv`), and nobody tested whether the volume response per
promotional euro was fading (H2 is ~38% weaker than H1 by design). run_03 even
checked customer-level *revenue* concentration, found none (true — revenue shares
are broad), and stopped one column short of the discount concentration. This is the
honest ceiling of a one-pass investigation: the attention path to AR-by-customer was
suggested by the pack's DSO flags; nothing pointed at discounts-by-customer, and no
run generated that hypothesis unprompted.

**S4 — the credibility trap: three clean passes.** All three runs said "stand down"
with the right evidence (YoY positive, vs-budget within 2%, identical seasonal build
both years; run_03 added that the budget itself assumes the same December-January
step). No run cried wolf anywhere else either — the restraint the noise policy is
designed to score held.

## Noise ledger

- **N1, N2** (the 2024 one-offs): referenced only by run_02, correctly as context,
  not dramatised. Acceptable in all runs ("may be noted").
- **N3** (CE +2% contractual price indexation, July 2025): referenced by no run —
  below every run's materiality bar. The worksheet's "N3 dramatised" rows are
  matcher artefacts (its month/BU-overlap rule catches S2 findings that span July in
  Central Europe); adjudicated: no run discussed the indexation at all.
- **N4** (structural budget optimism, added to the answer key after the deterministic
  layer exposed it): found by run_02 only, correctly framed ("~8% EBITDA miss in
  2024 too, before any discounting — a third of the vs-budget gap is standing
  planning bias"). run_01 and run_03 attributed the 2025 budget miss to real 2025
  drivers — defensible (underlying EBITDA genuinely fell 13.7% YoY) but incomplete.

## Figure discipline

The worksheet's figure verification produced 18 mechanical "disagreements" across the
three runs. Every one was adjudicated against the raw evidence text: all are
different-basis or different-quantity citations that are correct in their own labelled
context (monthly vs FY snapshots, PVM components, volume shares, an explicitly
labelled underlying figure matched against a reported target). **Zero incorrect
figures survived adjudication in any run.** One imprecision worth recording:
run_03's F4 headline compresses "December EBITDA −39.5% YoY" into "down ~40% YoY",
which reads as a full-year claim (the full-year figure is −8.1%); the finding body is
correct and specific. Headline compression is a real failure mode even in strong
runs, and packs of agent findings should be read past their headlines.

## What went wrong / limitations

1. **S3's designed evidence went unclaimed three times.** The dataset contains the
   concentration and elasticity evidence; no run looked. A follow-up prompt would
   elicit it, but that becomes leading; the honest result is that one-pass
   investigation finds the mechanism and misses the two sharpest exhibits.
2. **N4 recall was 1/3.** The structural optimism insight — arguably the most
   consultant-grade observation available — was found once.
3. **The mechanical evaluation layer is fragile on causal language.** Four matcher
   bugs were found and fixed during its build (unit-typing, evidence-scoping,
   negation-blindness, phrase-order), two of which would have mis-scored cluster C2
   for two runs. The final scorecard therefore rests on manual adjudication against
   the raw JSON, with the worksheet as the audit trail — by design, but worth
   stating: keyword matching alone would have got the C2 verdicts wrong.
4. **Runs were not cost-metered.** No token counts were measured, so the case
   study claims no cost figures for the agent layer.

## Reading of the result

The deterministic pack did its job: 327 mechanically correct flags, zero causes. The
storyteller layer turned those flags into three correct board actions (discount
policy, Baltics cost-to-grow, the Rheinkauf receivable) and three correct
stand-downs (January, procurement, April) — per run, independently, with every cited
figure surviving verification. The delta over the pack is not more alarms; it is
attribution, de-escalation, and a named customer. The delta the runs did *not*
deliver — discount concentration, fading elasticity — is the honest measure of where
one-pass agent investigation stops, and it is kept in this report for exactly the
reason the answer key exists: so the case study can be marked, not asserted.
