# Classical ML pipeline — results

**This is the v4 ("low-volume A4") run — the final dataset.** Three generations of source-data fixes precede it, each a documented iteration in making the quietly-unhappy archetype (A4) invisible to metadata (the full honesty trail is in the "A4 before -> after" section). v1 -> v2 fixed ticket dates for non-churning accounts (which had clustered in the first month after signup) and gave A4 a *polite disengaged* csat pattern (~5% fill rate, never below 3). v2's result was NEGATIVE: A4's mean risk score ROSE (0.591 -> 0.666), because csat was never A4's dominant leak — `unresolved_count_6m` and `mean_resolution_days_6m` were. v2 -> v3 closed that outcome leak at source (`code/fix_a4_ticket_metadata.py`: support closes every A4 ticket promptly even though the fix does not hold — the real-world "marked resolved, problem persists" pattern; the prose already says so). v3's result was ALSO negative: A4 rose marginally again (0.679, 70% top-100) as the model shifted its weight onto ticket VOLUME itself — A4 then generated ~6.65 tickets in the trailing 6 months vs A1's 1.04, and an account noisy enough to read is noisy enough to count. v3 -> v4 (this run) redesigned A4 as genuinely low-volume (`code/regenerate_a4_briefs.py` + rewritten prose: 3–6 tickets per account life, ~2.9 in the feature window, each long, polite, densely documented; the disengagement shows as going quiet). Result: A4 fell to 0.477 mean / 50% top-100. Residual visibility rides on ticket timing (`ticket_count_3m` — the arc crescendos late) and resolution-day patterns; tuning stops here and the four-iteration trail is published as the finding. See "A4 before -> after" and the SHAP breakdown below.

Gradient boosting backend: **lightgbm**

Split: 70/30 stratified by churn label, seed 42. Scoring for all 500 accounts: 5-fold stratified CV, seed 42 (every account scored by a model that never trained on it).

## Holdout test-set metrics (70/30 split)

| Model | AUC | Average precision | Recall@top-50 |
|---|---|---|---|
| Logistic regression | 0.782 | 0.652 | 0.600 |
| Gradient boosting (lightgbm) | 0.899 | 0.818 | 0.800 |

v2 (post-date-fix, pre-close-the-tickets) run for comparison: logistic regression AUC 0.850 / AP 0.775 / recall@50 0.725; gradient boosting AUC 0.925 / AP 0.876 / recall@50 0.850. v1 (pre-date-fix) run: logistic regression AUC 0.817 / AP 0.674 / recall@50 0.675; gradient boosting AUC 0.912 / AP 0.851 / recall@50 0.825.

## Data artefact investigation

Four structural issues have been found and corrected/documented across the v1-v4 history of building the classical model, all originally surfaced because the v1 pass produced suspiciously perfect separation (AUC ~0.98) and an undetectable archetype (A5) scoring almost as high as the designed-to-be-caught archetype (A3). Two (tenure_months, calendar seasonality) are unchanged by any run's source fixes and remain excluded from the trained feature set or handled by deseasonalising; the other two (ticket-date clustering, A4's ticket-outcome leak) have each been fixed at source, in v2 and v3 respectively, and are re-examined below.

**1. `tenure_months` is a mechanical confound, not behavioural signal.** `churn_date` in `generate_structured.py` is drawn uniformly between `signup + 6 months` and the observation window's end, independent of archetype. Retained accounts are always snapshotted at the same fixed calendar date (window end minus 2 months). The combination means every churning archetype -- including A5 ("sudden death", designed to be *undetectable*) -- has systematically shorter tenure-at-snapshot than survivors, purely as an artefact of how the snapshot date is chosen, not because of anything the account did. Feeding `tenure_months` to the model let it separate churners from survivors almost perfectly off remaining runway alone, which would have erased the entire point of this case study. **`tenure_months` remains excluded from the trained feature set** (kept in `features.csv` for transparency). The ablation below quantifies the effect.

**2. `tickets.csv`'s date-clustering defect was FIXED at source in v2 (unchanged this run).** Previously, tickets for non-churning archetypes (A1, A2, A6, A7, A8) clustered within roughly the first two months after signup regardless of total tenure (median `days-since-signup / total-lifetime-days` ~0.03), which made any trailing-window ticket feature a disguised churn proxy: a long-tenured survivor's trailing window saw almost no tickets purely because of when its tickets happened to have been generated, not because it was quiet. The `*_lifetime` ticket features (signup-to-snapshot) were introduced as a workaround, immune to that clustering. Ticket dates are now spread realistically across every account's life for every archetype (median lifetime-position by archetype now ranges ~0.36-0.71, not ~0.03). The diagnostic below re-checks the failure mode directly on the fixed data.

**Ticket-window diagnostic (trailing 6-month ticket features by archetype, post-fix -- these are the actual features fed to the model):**

| Archetype | N accounts | Mean ticket_count_6m | Median ticket_count_6m | % accounts with 0 tickets in window | Mean ticket_count_lifetime | Mean unresolved_count_6m | Mean resolved_rate_6m | Mean resolution_days_6m |
|---|---|---|---|---|---|---|---|---|
| A1 | 176 | 1.04 | 1.0 | 43% | 4.29 | 0.09 | 92.4% | 4.02 |
| A2 | 46 | 2.24 | 2.0 | 15% | 5.57 | 0.20 | 92.0% | 4.21 |
| A3 | 57 | 5.91 | 6.0 | 0% | 8.70 | 1.30 | 75.9% | 5.99 |
| A4 | 46 | 2.93 | 3.0 | 0% | 4.15 | 0.00 | 100.0% | 3.03 |
| A5 | 30 | 1.87 | 1.5 | 10% | 2.43 | 0.03 | 99.3% | 4.39 |
| A6 | 52 | 7.02 | 7.0 | 0% | 13.23 | 0.73 | 89.9% | 5.37 |
| A7 | 55 | 4.71 | 4.0 | 16% | 16.07 | 0.00 | 100.0% | 1.49 |
| A8 | 38 | 1.39 | 1.0 | 32% | 4.66 | 0.11 | 90.4% | 4.17 |

**Note for the A4 discussion below (v3, post-close-the-tickets):** in v3, within the trailing 6-month window the model actually saw, A4 had a mean unresolved-ticket count of 0.00 per account -- literally 0 for every single A4 account, same for `resolved_rate_6m` (exactly 1.0 for every A4 account) -- vs A3's 1.30. In the v2 run, before `code/fix_a4_ticket_metadata.py` closed A4's tickets at source, this same figure was 1.61 per account, the highest of all eight archetypes, and `mean_resolution_days_6m` / `unresolved_count_6m` were the two largest SHAP drivers of A4's risk score. That specific leak was closed in v3: `unresolved_count_6m` and `resolved_rate_6m` became constants for A4 and could no longer discriminate between A4 accounts. In the shipped v4 data the picture has moved again -- see item 3 below and the SHAP breakdown further down for what the model leans on instead.

Non-churning archetype A6 now shows *higher* mean trailing-window ticket volume than either churning archetype A3 or A4 (7.02 vs 5.91 and 2.93), and A7 sits well above the healthy archetypes (4.71, close to A3/A4) despite never churning -- both archetypes' designed arcs (A6's escalation-then-recovery, A7's steady stream of angry-but-resolved tickets) genuinely generate more support contact, they just don't churn over it. A1 (healthy-stable) no longer reads as uniformly zero either. This is the opposite of the old mechanical-separation failure mode, where non-churning archetypes read as near-zero purely because of when their tickets happened to be dated. **Trailing-window ticket features (`ticket_count_3m`, `ticket_count_6m`, `has_tickets_6m`, `tickets_per_month_trend`, `unresolved_count_6m`, `resolved_rate_6m`, `mean_resolution_days_6m`, `mean_csat_6m`, `csat_response_count_6m`) are therefore re-admitted to the trained model.** The `*_lifetime` ticket features, no longer needed as a workaround, are excluded instead (same transparency treatment as `tenure_months` -- kept in `features.csv`, not fed to the model, to avoid two redundant views of the same underlying signal).

**3. A4's ticket-OUTCOME leak (unresolved count, slow resolution) was FIXED at source in v3 (superseded by the v4 volume redesign below).** The v2 run's negative result (A4 mean risk score rose from 0.591 to 0.666 despite csat being quieted -- see "Previous runs" appendix below) traced to `unresolved_count_6m` and `mean_resolution_days_6m`: A4's designed ticket arc includes a genuinely unresolved complaint stage, and that OUTCOME was legible from ticket metadata even though its sentiment was not. `code/fix_a4_ticket_metadata.py` closed the loop for v3: A4 tickets got marked resolved by support (resolution_days drawn 1-5, support closes tickets promptly) even though the underlying fix does not hold -- the real-world "marked resolved, problem persists" pattern. Only the `resolved` and `resolution_days` fields were changed, in both `ticket_briefs.json` and the corresponding `tickets_raw/batch_*.json` records; not one word of ticket prose was touched (the later tickets already say the fix did not hold). A4's unresolved-ticket rate in `tickets.csv` became 0.0% (was 23.1%), at or below every other archetype's rate. **This did NOT make A4 invisible to the classical model** -- see "A4 before -> after" below: the model's weight simply shifted from ticket OUTCOME features onto ticket VOLUME features (`ticket_count_6m` / `ticket_count_3m`), because in v3, A4's designed arc still generated far more tickets than a healthy account (mean 6.65 in the trailing 6 months vs A1's 1.04) -- that volume, independent of how the tickets resolved, remained a residual metadata fingerprint. In the shipped v4 data the figure is 2.93 (see the ticket-window diagnostic table above and "A4 before -> after" below) -- the volume redesign that finally addresses this leak.

**4. Calendar seasonality is a fourth, subtler confound, unaffected by any run's fixes.** SHAP showed usage TREND features (`logins_trend_pct_3m`, `exports_run_trend_pct_3m`, etc.) as dominant drivers, contributing *positively* to A5's risk score while contributing *negatively* to A1's -- for two archetypes whose usage is generated with nearly identical parameters (`trend_per_month` 0.004 vs 0.005). Root cause: the product has a real seasonal "summer dip" (cosine, trough in July) baked into usage generation. Retained accounts are ALWAYS snapshotted in the same fixed calendar window (Aug-Oct 2025, since censoring is fixed at the observation window's end), which sits on the RISING half of that cosine -- giving every survivor's raw 3-month trend a deterministic upward nudge that has nothing to do with behaviour. Churned accounts are snapshotted at scattered calendar months (tied to their individual, uniformly-drawn churn dates), so this bias averages out for them. **Fix (unchanged from the previous run):** `build_features.py` estimates a portfolio-wide seasonal index per metric per calendar month (`compute_seasonal_index`, a population-level statistic computed with no churn label involved) and deseasonalises every usage value before computing level, trend, module-mix-shift, and seat-utilisation features.

**Tenure ablation (gradient boosting, same holdout split):**

| Feature set | AUC | Average precision | Recall@top-50 |
|---|---|---|---|
| Official (tenure_months excluded) | 0.899 | 0.818 | 0.800 |
| With tenure_months added back | 0.955 | 0.930 | 0.900 |

## Per-archetype risk table (out-of-fold scores, vs answer_key.csv, evaluation only)

Top-100 = the 100 highest ml_risk_score accounts across all 500.

| Archetype | N accounts | Mean risk score | N in top-100 | % of archetype in top-100 | % of top-100 that is this archetype |
|---|---|---|---|---|---|
| A3 | 57 | 0.861 | 51 | 89.5% | 51.0% |
| A4 | 46 | 0.477 | 23 | 50.0% | 23.0% |
| A5 | 30 | 0.219 | 5 | 16.7% | 5.0% |
| A8 | 38 | 0.191 | 4 | 10.5% | 4.0% |
| A2 | 46 | 0.164 | 5 | 10.9% | 5.0% |
| A1 | 176 | 0.092 | 10 | 5.7% | 10.0% |
| A7 | 55 | 0.090 | 2 | 3.6% | 2.0% |
| A6 | 52 | 0.008 | 0 | 0.0% | 0.0% |

## Design-expectation check

- **A3 (slow decay — designed to be caught by ML)**: mean score 0.861 (+0.770 vs A1 healthy-stable baseline of 0.092), 89% of its accounts in the top-100.

- **A4 (quietly unhappy — designed to be INVISIBLE to ML)**: mean score 0.477 (+0.386 vs A1 healthy-stable baseline of 0.092), 50% of its accounts in the top-100.

- **A8 (quiet decline, stays — designed as the main ML false-positive source)**: mean score 0.191 (+0.099 vs A1 healthy-stable baseline of 0.092), 11% of its accounts in the top-100.

- **A5 (sudden death — designed as an honest, undetectable miss)**: mean score 0.219 (+0.128 vs A1 healthy-stable baseline of 0.092), 17% of its accounts in the top-100.


## A4 before -> after: the number that matters most

| Run | A4 mean risk score | A4 % in top-100 |
|---|---|---|
| v1 (pre-date-fix, visible csat) | 0.591 | 63% |
| v2 (post-date-fix, quieted csat, unresolved tickets still live) | 0.666 | 67% |
| v3 (post-close-the-tickets: A4 tickets marked resolved, outcome leak closed) | 0.679 | 70% |
| **v4 (this run — A4 redesigned as low-volume: 2–3 tickets in window, each long and polite)** | **0.477** | **50%** |

The v3 result was the pivotal negative: with csat and resolution outcomes silenced, the model shifted its weight onto ticket VOLUME itself (A4 then generated ~6.65 tickets in the trailing 6 months vs A1's 1.04 — an account noisy enough to read is noisy enough to count). The v4 redesign made A4 genuinely quiet: 3–6 tickets per account life, ~2.9 in the feature window (healthy-comparable), each long, courteous and densely documented, with the disengagement expressed as going silent rather than as traffic. That dropped A4 from 0.679 to 0.477.

**A4 is still not fully invisible to the classical model, and we stop tuning here and publish the trail as the finding.** Per the SHAP tables below, A4's residual visibility now rides on `ticket_count_3m` (its few tickets concentrate in the last three months before the window closes — the arc crescendos late) and `mean_resolution_days_6m` (its tickets close in 1–5 days vs the fast-fix norm elsewhere). Removing those traces would mean re-dating the arc away from the churn event or making support close A4 tickets implausibly fast — at which point the archetype stops being the thing we set out to model. The honest summary: after four iterations of making quiet unhappiness quieter, a competent classical model still half-sees it (50% of A4 in the top-100, mean 0.477 vs A3's 0.861 / 89%) but cannot say why, and misses the other half entirely. The agent layer's job is both the missed half and the explanation for the found half.

## SHAP global feature importance (mean |SHAP|, out-of-fold)

| Rank | Feature | Mean |SHAP value| |
|---|---|---|
| 1 | ticket_count_3m | 0.9483 |
| 2 | mean_resolution_days_6m | 0.8389 |
| 3 | ticket_count_6m | 0.4489 |
| 4 | dashboard_views_trend_pct_6m | 0.4070 |
| 5 | connector_syncs_trend_pct_6m | 0.3292 |
| 6 | logins_trend_pct_3m | 0.3039 |
| 7 | mix_share_shift_dashboard_views | 0.3009 |
| 8 | reports_created_trend_pct_3m | 0.2760 |
| 9 | alerts_configured_trend_pct_6m | 0.2617 |
| 10 | connector_syncs_trend_pct_3m | 0.2574 |
| 11 | alerts_configured_trend_pct_3m | 0.2527 |
| 12 | seat_utilisation_level_3m_mean | 0.2365 |
| 13 | mix_share_shift_alerts_configured | 0.2329 |
| 14 | active_users_trend_pct_6m | 0.2314 |
| 15 | mix_share_shift_connector_syncs | 0.2285 |

## What drives A4 accounts' risk scores (mean SHAP contribution, signed)

Positive = pushes risk score up. This is where to look if A4 is scoring higher than designed.

| Rank | Feature | Mean SHAP contribution (signed) |
|---|---|---|
| 1 | ticket_count_3m | +0.8570 |
| 2 | mean_resolution_days_6m | +0.5783 |
| 3 | ticket_count_6m | +0.4536 |
| 4 | dashboard_views_trend_pct_6m | +0.2435 |
| 5 | mix_share_shift_dashboard_views | +0.1670 |
| 6 | resolved_rate_6m | +0.1625 |
| 7 | seat_utilisation_level_3m_mean | +0.1551 |
| 8 | connector_syncs_trend_pct_6m | -0.1351 |
| 9 | logins_trend_pct_6m | +0.1145 |
| 10 | active_users_level_3m_mean | +0.1059 |

## Previous runs (v1 and v2), for the honesty trail

Kept here, condensed, so the movement above is checkable rather than asserted. Neither prior run's full per-archetype table or SHAP breakdown is reproduced; the headline numbers below are transcribed once, by hand, from each run's own report into `PREVIOUS_RUN_V1` / `PREVIOUS_RUN_V2` at the top of `train_models.py`, and are all that is carried forward.

**v1 (pre-date-fix, pre-close-the-tickets).** Ticket dates for non-churning archetypes still clustered in the first two months after signup, and A4's csat pattern was ordinary (visible) dissatisfaction rather than the "polite disengaged" pattern introduced in v2. Under those conditions, trailing-window ticket features were a disguised churn proxy and had to be excluded in favour of `*_lifetime` ticket features; the model still partially recovered A4's unhappiness through `mean_csat_lifetime`, `unresolved_count_lifetime`, and `mean_resolution_days_lifetime`.

| Model | AUC | Average precision | Recall@top-50 |
|---|---|---|---|
| Logistic regression | 0.817 | 0.674 | 0.675 |
| Gradient boosting (lightgbm) | 0.912 | 0.851 | 0.825 |

| Archetype | Mean risk score | % of archetype in top-100 |
|---|---|---|
| A3 (slow decay) | 0.816 | 86% |
| A4 (quietly unhappy) | 0.591 | 63% |
| A1 (healthy-stable, baseline) | 0.069 | -- |

**v2 (post-date-fix, pre-close-the-tickets).** Ticket dates were spread realistically across every account's life (see item 2 above), and A4's csat pattern was quieted to "polite disengaged" (~5% fill rate, never below 3). Trailing-window ticket features were re-admitted to the trained model on that basis. The result was a NEGATIVE one for the design intent, reported honestly at the time: A4's mean risk score ROSE (0.591 -> 0.666) instead of falling, because csat was never A4's dominant structured leak -- `mean_resolution_days_6m` and `unresolved_count_6m` (A4's designed unresolved-complaint stage) were, and quieting csat left them untouched. That is the specific leak `fix_a4_ticket_metadata.py` closes for this (v3) run.

| Model | AUC | Average precision | Recall@top-50 |
|---|---|---|---|
| Logistic regression | 0.850 | 0.775 | 0.725 |
| Gradient boosting (lightgbm) | 0.925 | 0.876 | 0.850 |

| Archetype | Mean risk score | % of archetype in top-100 |
|---|---|---|
| A3 (slow decay) | 0.887 | 93% |
| A4 (quietly unhappy) | 0.666 | 67% |
| A1 (healthy-stable, baseline) | 0.063 | -- |
