# 06 Anomaly Detection — "The flags that mattered"

Case 6 of the Hapax case studies (05's bottom-up sibling). A synthetic Finnish purchase
ledger (Saarnitukku Oy, fictional; 50,000 rows, seed 42) is screened by seven
sourced audit rule tests and an Isolation Forest; three blinded agent runs triage
every flag; all three layers are marked against a held-out answer key. The honest
headline: the rules caught everything rule-shaped, the detector caught nothing
planted (a frozen, diagnosed, pre-registered deviation), and the drift story the
case is named for was caught by nobody — which is the case's actual argument.

A follow-on, "06b", builds the standing vendor-drift review the main case
missed and runs it on the company's next year; see the 06b section below.

## Pipeline (run from this folder)

```
python code/generate_ledger.py          # 4 public tables + data/answer_key/anomalies.csv (seed 42)
python code/validate_ledger.py          # 13 coherence rules; exits 1 on any failure
python code/run_rule_layer.py           # -> data/analysis/rule_flags.csv (64 flags, pre-registered)
python code/detect_anomalies.py         # -> detector_flags.csv + detector_scores.csv (200 flags; self-checks determinism)
python code/prepare_clusters.py         # -> data/analysis/clusters.json (39 verdict units)
# 3 blinded Claude Code subagent runs, each given the same pinned briefing
#   -> data/analysis/agent_runs/run_0N_findings.json + run_0N_memo.md
python code/evaluate.py                 # mechanical marking -> evaluation.json + evaluation_worksheet.md + scores CSV
# data/analysis/report.md = the adjudicated scorecard, written by hand from the worksheet
python code/build_interactive_data.py   # distils results -> interactive/_data.json (asserts vs evaluation)
python code/merge_interactive_data.py   # inlines the JSON into the self-contained page
python code/verify_interactive.py       # page QA gate (19 checks); exits 1 on failure
```

Notebook: `python -m nbconvert --to notebook --execute --inplace notebooks/anomaly_detection_analysis.ipynb`
(re-reads every number live; 23 asserts on the headline figures).

## ⚠️ What regenerates and what does not

**Deterministic (safe to re-run, byte-identical on the pinned environment):** the
generator, validator, rule layer, detector (seeded, `n_jobs=1` — pinned
scikit-learn 1.9.0 / scipy 1.18.0 / numpy 2.5.0 / Python 3.12.6; version drift can
change detector output), cluster prep, evaluation, interactive data prep and page QA.

**NOT regenerable — session artefacts, treat as data:**
`data/analysis/agent_runs/` (the three runs' findings JSONs and memos) were produced by blinded Claude Code subagent runs (Opus) on 3 July 2026.
Re-running them means new agent sessions with the pinned briefing, and results
WILL differ — that variance (37/35/38 of 39) is part of the published result.
`data/analysis/report.md` is the hand-adjudicated scorecard of those specific runs.

## Where things live

| Artefact | Location |
|---|---|
| Generation + detection + evaluation code | `code/` |
| Public dataset (4 tables) | `data/*.csv` |
| Answer key — held out of every analysis and agent-facing path | `data/answer_key/anomalies.csv` |
| Flags, clusters, agent runs, worksheet, adjudicated scorecard | `data/analysis/` |
| Executed analysis notebook (incl. the labelled post-hoc detector v2) | `notebooks/` |
| Interactive page (single self-contained HTML) + its data | `interactive/anomaly-detection.html` |
| Canonical long-form writeup | `writeup/anomaly_detection_case_study.md` |
| 06b: generator, validator, drift review, marking | `code/06b_*.py`, `code/config_06b.py`, `code/drift_report.py` |
| 06b: ledger, answer key, drift reports, marked report | `data/06b/` |

## Environment

Python 3.12 with pandas, numpy, scikit-learn 1.9.0 (pinned); the notebook additionally needs matplotlib, nbformat,
nbconvert, ipykernel. No API keys anywhere.

## The one-line result

Rules 48/64 flags on plants at the designed 75% first-pass precision with 100%
recall on every rule-shaped class; detector 0/200 on anything planted (frozen,
diagnosed deviation); agents 37/35/38 of 39 verdicts with all 78 detector-unit
stand-downs correct, the cross-record vendor-trio story found 3/3 — and the
case's namesake drift story caught by nobody, which is why the answer key exists.

## 06b – the standing vendor-drift review

The main case's drift story was caught by nobody. 06b builds the method that
would have found it, a standing review of each vendor's unit prices against its
own history (`code/drift_report.py`, a one-sided CUSUM, deterministic, no ML), and
runs it on Saarnitukku Oy's next financial year: an FY2026 ledger of 50,000 rows
and 200 vendors (seed 2026), with three planted price drifts and two benign
lookalikes held in a separate answer key. The method's four parameters and six
expectations were fixed before any 06b data existed.

```
python code/06b_generate.py   # data/06b/ ledger tables + data/06b/answer_key_06b.csv (seed 2026)
python code/06b_validate.py   # coherence checks; exits 1 on any failure
python code/drift_report.py data/06b/gl_transactions_06b.csv data/06b/drift_report.md --label "Saarnitukku Oy FY2026"
python code/drift_report.py data/gl_transactions.csv data/06b/drift_report_2025_retro.md --label "Saarnitukku Oy FY2025 (6a frozen ledger, retrospective, in-sample)"
python code/06b_mark.py       # marks both reports against the answer key and the six expectations -> data/06b/report.md
```

Four of the six expectations were met, and all five planted items were flagged.
The two misses are frozen and diagnosed in `data/06b/report.md`: 42 unplanted
vendors crossed the threshold against an expected ceiling of about five, and on
the 2025 ledger the original drift vendor cannot be scored at all, because it
bills twice a month and the method needs three invoices in a month.
