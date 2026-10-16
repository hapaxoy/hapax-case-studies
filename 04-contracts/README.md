# 04 Contracts — contract review

The one **real-data** case in the series: 150 real SEC-filed contracts from **CUAD v1**
(The Atticus Project, CC BY 4.0), marked against the dataset's own attorney annotations —
an answer key we didn't write, held out from the pipeline throughout and read exactly once,
after the stream closed. A model read 50 contracts (12 review questions each); an overseer
induced deterministic matchers from its accepted answers; an activation gate killed one,
shadow checks demoted three in flight; the eight survivors answered 176 questions on a
100-contract holdout the model never saw. Pre-registered predictions went 4/12, misses in
both directions, kept in print.

## Read these first

- `data/runs/report.md` — the findings report (lifecycle, predicted-vs-actual, adjudication, costs)
- `writeup/contract_review_case_study.md` — the canonical case study

## Folder map

```
code/            corpus prep + validation, pipeline tools, evaluation, page build/QA
code/matchers_generated/   ⚠️ the 12 overseer-written matchers (session artefacts)
data/contracts/  150 selected contract texts (the sub-corpus; source of truth)
data/answer_key/ 150 per-contract key files derived from CUAD's master_clauses.csv
                 — NEVER opened by any agent; evaluate.py is the only reader
data/runs/       ⚠️ run artefacts: 50 LLM extractions, matcher outputs (stream+holdout),
                 shadow answers, gate results, commissions, batches, stream events,
                 evaluation.json, evaluation_worksheet.md, extract_agent_log.json, report.md
notebooks/       contract_review_analysis.ipynb (executed; every number read at run time)
interactive/     contract-review.html (self-contained page) + _template.html + _data.json
writeup/         canonical case study
```

## ⚠️ Regenerate vs artefact — do not re-run the LLM side

Same split as 02/03. **Session artefacts** (products of specific July 2026 agent sessions;
re-running would produce different results and cost real tokens — never regenerate):

- `data/runs/llm_extractions/` (50 contract reads), `data/runs/shadow_answers.json`
- `code/matchers_generated/` (12 matchers incl. the gate-failed and demoted ones)
- `data/runs/commissions/`, `gate_results/`, `matcher_state.json`, `stream_events.json`
- `data/runs/extract_agent_log.json` (measured tokens; the batch-7 gap is a connection drop, documented inside)
- the hand adjudication embedded in `report.md`

**Regenerable** (deterministic from the frozen download + this folder, `RANDOM_SEED = 42`):

- corpus prep: `prepare_corpus.py` → `derive_answer_key.py` → `validate_corpus.py`
  (needs a local copy of the CUAD archive, see `data/manifest.json` for URL + SHA-256;
  tree hash BF804D4E… byte-identical across two independent runs)
- `router.py` (replays the stream deterministically from the artefacts above)
- `evaluate.py` (the only key-reading file) → evaluation.json + worksheet
- the notebook (nbconvert re-execution; live asserts guard the headline numbers)
- the page: `build_interactive_data.py` → `build_interactive.py` → `verify_interactive.py`

## Pipeline order (for reference, from this folder)

```
python code/prepare_corpus.py        # selects 150 from a local copy of the CUAD archive
python code/derive_answer_key.py     # per-contract key JSONs from master_clauses.csv
python code/validate_corpus.py       # 10 rules; rule 10 = answer-key isolation scan
# --- the stream (SESSION DATA, do not re-run): 8 extraction batches + overseer runs ---
python code/router.py                # deterministic replay of the stream
python code/evaluate.py              # the ONE key-read; writes evaluation.json
python code/build_interactive_data.py && python code/build_interactive.py
python code/verify_interactive.py    # QA gate (self-counting; 49 checks)
python -m nbconvert --to notebook --execute --inplace notebooks/contract_review_analysis.ipynb
```

Note: `data/master_clauses.csv` (CUAD's full raw metadata file for all 510 contracts) is
not included here. Only this project's derived answer-key files (`data/answer_key/`) and
`data/manifest.json` are published; the raw CUAD archive itself is not redistributed and
is recoverable from `data/manifest.json`'s URL and SHA-256.

## House rules that bind here

- The answer key stays out of every agent's reach (validator-enforced whitelist; every agent transcript's file-audit list was checked by hand). An overseer that saw the key would launder it into "deterministic" code and void the marking.
- The key is never edited — as-marked scores stand; the adjudication is published beside them.
- Costs are method-B estimates (measured subagent tokens × published prices, banded); intro-vs-list pricing disclosed.
- Nothing here is legal advice; the pipeline processes documents, it does not practise law.

## Attribution

CUAD v1 — Hendrycks, Burns, Chen & Ball, *CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review*, NeurIPS 2021 Datasets and Benchmarks (arXiv:2103.06268). Dataset © The Atticus Project, CC BY 4.0. `data/CUAD_LICENCE_ATTRIBUTION.md` carries the full notice; this project's per-contract key files adapt `master_clauses.csv` under the same licence.
