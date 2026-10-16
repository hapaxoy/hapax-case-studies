# ERP Output Cleanup — project map

The second Hapax case study ("the automation that retires itself").

## What lives where

| Path | What it is |
|---|---|
| `code/` | Generator, validator, schemas, regression gate, router, evaluation, page builder + QA |
| `code/parsers_generated/` | **The five parsers the overseer wrote — artefacts, not source.** See warning below |
| `data/documents/`, `data/answer_key/` | The 240-document corpus + ground truth. Deterministic (seed 42) |
| `data/runs/` | **Session-produced results — artefacts.** LLM parses (56), stream events, evaluation, usage log, findings report |
| `notebooks/` | Analysis notebook (executed in place) |
| `interactive/` | `erp-cleanup.html` (the published self-contained page) + its template |
| `writeup/` | `case_study.md` (canonical) |

## ⚠️ What regenerates and what does not

**Deterministic (safe to re-run, byte-identical):**

```
python code/generate_documents.py    # corpus + answer keys (seed 42)
python code/validate_data.py         # seven coherence rules, exit 1 on failure
python code/regression_gate.py       # parsers vs LLM parses + full-corpus dry run
python code/router.py                # stream replay -> data/runs/stream_events.json
python code/evaluate.py              # scoring + costs -> data/runs/evaluation.json
python code/build_interactive.py     # evaluation.json -> interactive/erp-cleanup.html
python code/verify_interactive.py    # page QA gate
```

**NOT regenerable — do not delete or "refresh":** `data/runs/llm_parses/` (56 files),
`code/parsers_generated/` (5 files), and `data/runs/parse_agent_log.json`. These were
produced by Claude Code subagent runs on 2–3 July 2026 (method B). Re-running those agents would produce *different* artefacts
and invalidate every published number. They are data. Treat them like the corpus.

The notebook re-executes with `python -m nbconvert --to notebook --execute --inplace
notebooks/erp_cleanup_analysis.ipynb`; it reads all numbers from `data/runs/` at run time.

## Environment

Python 3.12 with `pandas`, `numpy` for the pipeline; the notebook additionally needs
`matplotlib`, `nbformat`, `nbconvert`, `ipykernel` (`pip install matplotlib nbformat
nbconvert ipykernel`). No API keys anywhere — LLM-in-pipeline work runs as Claude Code
subagents, never API keys; costs are labelled estimates.
