# 01 Churn — project map

The first Hapax case study. ML findings in
`data/model/ml_report.md`; fusion/evaluation findings in `data/fusion/evaluation_report.md`.

## The one-line result

Combining the usage model with an agent that reads support tickets lifts AUC from
0.867 to 0.890 and recall@top-100 from 59% to 66%, scored out-of-fold across all
500 accounts against a held-out answer key. The deeper finding sits upstream of
that number: it took four iterations of data design to make the quietly-unhappy
archetype (A4) invisible to the usage-metadata model — the full trail is in
`data/model/ml_report.md`'s "A4 before -> after" table.
The short version: an account noisy enough to read is noisy enough to count.

## What lives where

| Path | What it is |
|---|---|
| `code/` | Generation + validation + ML + fusion pipeline |
| `code/` (eight one-off repair scripts) | `fix_ticket_dates.py`, `make_redate_batches.py`, `merge_redated_prose.py`, `apply_patches.py`, `fix_a4_ticket_metadata.py`, `regenerate_a4_briefs.py`, `replace_a4_prose.py`, `make_a4_rewrite_batches.py` — **archive, not pipeline.** See warning below |
| `data/accounts.csv`, `usage_monthly.csv`, `tickets.csv`, `answer_key.csv` | The structured layer + the held-out ground truth. Deterministic (seed 42) |
| `data/brief_batches/` | Ticket-writer briefs, batched for the prose agents |
| `data/tickets_raw/` | **Session-produced — the 30 ticket-writer batches.** See warning below |
| `data/agent/` | Assessor-agent batches, raw output, and the consolidated text-layer scores |
| `data/fusion/` | Fusion model, head-to-head evaluation, the 2x2, ARR translation |
| `data/model/` | Classical ML results and the full v1-v4 honesty trail (`ml_report.md`) |
| `data/validation_report.md` | Coherence-rule report for the frozen v4 dataset |
| `notebooks/churn_analysis.ipynb` | Analysis notebook (executed in place) |
| `interactive/` | `churn_explorer.html` — the published self-contained page — plus build script, template, data, QA |
| `writeup/` | `case_study.md` — the canonical case study |

## ⚠️ What regenerates and what does not

**Deterministic (safe to re-run; byte-identical at seed 42, with one exception):** `usage_monthly.csv` is not. `generate_structured.py` seeds each account's usage from Python's `hash()` of the account id, which Python randomises in every process, so a re-run gives different usage numbers. The shipped `usage_monthly.csv` is the frozen one, and every feature, model and figure was built from it; do not regenerate it. `accounts.csv` and `answer_key.csv` do reproduce exactly.

```
python code/generate_structured.py     # accounts.csv, usage_monthly.csv, answer_key.csv
python code/generate_ticket_briefs.py  # ticket_briefs.json (needs structured outputs first)
python code/split_briefs.py            # data/brief_batches/batch_NN.json
# ticket-writer agents write prose per batch -> data/tickets_raw/batch_NN.json (SESSION DATA — see below)
python code/assemble_tickets.py        # tickets.csv (--partial to accept missing batches)
python code/validate_data.py           # eight coherence rules; exits 1 on any failure
python code/build_features.py          # snapshot features (deseasonalised, 2-month lead time)
python code/train_models.py            # LR baseline + gradient boosting, writes data/model/
python code/make_assessment_batches.py # data/agent/assessment_batches/batch_NN.json
# assessor agents read tickets, write structured assessments -> data/agent/assessments_raw/batch_NN.json (SESSION DATA — see below)
python code/collect_assessments.py     # data/agent/text_scores.csv, narratives.json (--partial for missing batches)
python code/fuse_and_evaluate.py       # data/fusion/ — fusion model, head-to-head, 2x2, A4 table, ARR translation
python interactive/build_data.py       # distils artefacts -> interactive/_data.json
python code/verify_interactive.py      # page QA gate; exits 1 on failure
```

**NOT regenerable — do not delete or "refresh":**

- `data/tickets_raw/` (30 batches) — the ticket-writer agent's prose, written by Sonnet
  subagents from deterministic briefs. Re-running the agents would produce *different*
  prose (same signals, different words) and invalidate every downstream number that
  depends on the exact text an assessor agent read.
- `data/agent/assessments_raw/` (25 batches) — the assessor agents' structured
  readings of that prose (frustration trajectory, competitor mentions, narrative,
  text risk score). Same reasoning: re-running produces a different judgement call
  per account, not a byte-identical one.
- `data/agent/narratives.json` and `data/agent/text_scores.csv` — `collect_assessments.py`
  is itself a deterministic aggregation script (no LLM call), so re-running it against
  the *same, frozen* `assessments_raw/` batches is harmless. They are listed here
  because they encode what the assessor agents said, not because the script that
  produces them is non-deterministic — treat them as data derived from data, not as
  a build artefact to casually refresh.

Re-running any of the above under new agent sessions would change every published
head-to-head, A4-table, and ARR number in `data/fusion/`, `data/model/ml_report.md`,
the notebook, the interactive page, and the writeup. They are data. Treat them like
the corpus.

The notebook re-executes with
`python -m nbconvert --to notebook --execute --inplace notebooks/churn_analysis.ipynb`;
it reads its numbers from the artefacts above at run time.

### Archive vs canonical — the honesty trail's evidence

The dataset went through several redesigns before freezing at v4 (fixing a ticket-date
clustering bug, then three iterations of quieting the A4 archetype — see
`data/model/ml_report.md`). The intermediate states (three superseded brief
generations, the superseded ticket-writer output and brief batches from the date-fix and
A4 redesign rounds, a pilot batch of assessor output, and the ticket-date repair round's
patch records) are not part of this repository; the current brief set is
`data/ticket_briefs.json`.

The eight one-off repair scripts remain in `code/` (kept, not archived, as the honesty
trail): `fix_ticket_dates.py`, `make_redate_batches.py`, `merge_redated_prose.py`,
`apply_patches.py`, `fix_a4_ticket_metadata.py`, `regenerate_a4_briefs.py`,
`replace_a4_prose.py`, `make_a4_rewrite_batches.py`. Read each one's docstring before
touching it — they are repair tooling for specific past defects, not part of the
standing pipeline. (`split_briefs.py` looks similar but is pipeline, not repair — it
runs every time briefs are split into batches, not just during a fix.)

## Environment

Python 3.12 with `pandas`/`numpy` (pipeline), `scikit-learn` (logistic regression,
fusion, cross-validation), `lightgbm` (gradient boosting backend), `shap` (feature
attribution), `matplotlib` + `nbformat`/`nbconvert`/`ipykernel` (notebook). No API
keys anywhere — the ticket-writer and assessor agents ran as Claude Code subagents.
