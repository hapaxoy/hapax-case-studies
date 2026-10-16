# 03 Invoices — project map

Case 3 of the Hapax case studies ("the automation that retires itself") runs the same overseer
method as `02 ERP Cleanup`, supplier by supplier, on PDF invoices. Findings in `data/runs/report.md`.

## The one-line result

A year of 198 synthetic PDF invoices from 26 suppliers: the model read 81 documents
(5,427 fields, zero extraction errors), the overseer wrote nine deterministic parsers —
including one re-learned after a mid-year template redesign — and the whole pipeline was
marked against a held-out answer key: 13,650 fields, with the only wrong values being the
two the corpus was built to lie about. Year-one cost roughly breaks even against the
all-model counterfactual (parser generation ≈ the reads it displaced, labelled estimates);
the parsers persist, so year two runs at about a seventh.

## What lives where

| Path | What it is |
|---|---|
| `code/` | Generator + validator, schema, pipeline (gate/router/evaluate), interactive build + QA |
| `code/parsers_generated/` | **The nine parsers the overseer wrote — artefacts, not source.** See warning below |
| `code/templates/` | Per-supplier HTML invoice templates (generation-side) |
| `data/documents/`, `data/html/`, `data/answer_key/` | The 198-document corpus (PDF + HTML) and ground truth. Deterministic (seed 42) |
| `data/master_data.json`, `data/manifest.json` | The router's world knowledge; hashes + PO register |
| `data/runs/` | **Session-produced results — artefacts.** 81 LLM parses, stream events, evaluation, agent-usage log, findings report, text-layer dumps |
| `notebooks/` | Analysis notebook (executed in place) |
| `interactive/` | `invoice-processing.html` — the published self-contained page — plus template, data, QA |
| `writeup/` | `invoice_processing_case_study.md` (canonical) |

## ⚠️ What regenerates and what does not

**Deterministic (safe to re-run; byte-identical at the pinned Chrome version — see
`data/manifest.json` for versions):**

```
python code/generate_invoices.py       # corpus + answer keys (seed 42)
python code/validate_data.py           # ten coherence rules; exit 1 on failure
python code/export_master_data.py      # data/master_data.json
python code/extract_text.py            # text-layer dumps for the overseer inputs
python code/regression_gate.py         # parsers vs their own induction sets + full dry run
python code/router.py                  # stream replay -> data/runs/stream_events.json
python code/evaluate.py                # marking + costs -> data/runs/evaluation.json
python code/build_interactive_data.py  # distils artefacts -> interactive/_data.json
python code/build_interactive.py       # -> interactive/invoice-processing.html
python code/verify_interactive.py      # page QA gate
python code/check_llm_parses.py        # parse validity + accuracy vs key
python code/test_schemas.py            # schema/check-digit sanity suite (21 checks)
python code/replay_pipeline.py         # all of the above in order + byte-identity proof (~15 min)
```

**NOT regenerable — do not delete or "refresh":** `data/runs/llm_parses/` (81 files),
`code/parsers_generated/` (9 parsers + induction manifests), and
`data/runs/parse_agent_log.json`. These were produced by Claude Code subagent runs on
3 July 2026 (method B — Claude Code subagents, no API keys, costs are labelled estimates). Re-running those agents would produce *different* artefacts and
invalidate every published number. They are data. Treat them like the corpus.

The notebook re-executes with
`python -m nbconvert --to notebook --execute --inplace notebooks/invoice_processing_analysis.ipynb`;
it reads all numbers from `data/runs/` at run time and never opens the answer key.

## Identity numbers and names

Every company name, Y-tunnus and VAT number in this corpus is invented. The suppliers' Finnish Y-tunnukset sit in an unassigned range (98xxxxx, with valid check digits); the buyer's business ID, 2417551-8, lies outside that range but is not in the trade register either. Banks, BICs, IBANs, street addresses and registry courts are invented as well: the banks and their BICs do not exist, the IBANs pass the mod-97 check but carry invented bank codes, and every street is a placeholder such as Esimerkkikatu 4 with the town and postcode kept. Treat none of it as a real bank, account or address.

## Environment

Python 3.12 with `pandas`/`numpy` (pipeline), `pdfplumber` + `pypdf` (PDF layer), `jinja2`
(templates), `matplotlib` + `nbformat`/`nbconvert`/`ipykernel` (notebook). Headless Chrome
(version pinned in the manifest) renders the corpus; byte-identity claims are relative to
that version — the HTML sources and answer key are deterministic unconditionally.
No API keys anywhere — LLM-in-pipeline work runs as Claude Code subagents under pinned,
versioned instructions; costs are labelled estimates.
