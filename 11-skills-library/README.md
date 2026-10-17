# 11 Skills Library — project map

Project 11 of the Hapax case studies.
Findings report in `data/analysis/report.md`; writeup in
`writeup/skills_library_case_study.md`.

## The one-line result

Sixty requests to Tuomimetsä Oy, a fictional Finnish retailer with 38 stores and
a web store, backed by a DuckDB warehouse with 32 tables (the 50 reference queries
use 12 of them). Each request was answered in six model-and-setup cells: the main
model (Sonnet) with no rules (S), a single document (D), the full library (L) and
the library without its check programs (L−), plus a cheaper model (Haiku) with no
rules and with the library. Without written rules the main model scored 49.7%. With
the document, 99.3%. With the library, 98.3%. The cheaper model with the library
scored 79.0%, 29 points above the main model without rules. 6 of 12 predictions
met, 6 not met; nothing retuned after the numbers appeared.

## What the case demonstrates

An experiment measuring how much written data definitions change the accuracy of
an AI assistant answering data requests. `data/facts.yaml` records 206 facts about
Tuomimetsä's business, of which 62 carry a trap class (fiscal calendar, metric
definitions, data-quality exclusions, store groupings, naming conventions and
others). The sixty requests are grouped by what kind of company knowledge each one
tests: fourteen need nothing beyond standard SQL, and the rest test fiscal-year
boundaries, metric definitions, known data-quality issues, naming conventions and
trap classes designed to surface specific failure modes.

Each of the four Sonnet arms gave the assistant five independent runs on all sixty
requests (300 runs per arm, 1,200 in total). Two Haiku arms (S and L) added
another 600 runs, for 1,800 in all. Every run had read access to the warehouse
and could execute SQL queries. The answer key was locked in an encrypted archive
(built by `lock_answers.py`) during every run. No tested agent could read it; the marker, the validators
and the page build read it.

## What lives where

| Path | What it is |
|---|---|
| `arms/prompt_doc.md` | Arm D's single document: definitions, fiscal-calendar rules, data-quality exclusions, worked examples |
| `arms/library/` | Arm L: 10 skills, 5 reference files, 24 SQL templates, 2 check programs (`fiscal.py`, `query_check.py`) |
| `arms/tests/` | The builder's library tests and run log |
| `world/` | In-world documents the builder could read: metric dictionary, data-quality register, team notes, schema DDL, column comments, 40 past requests |
| `code/config.py` | Every tunable: seed (42), arm definitions, request classes, trap definitions, warehouse schema, world-document templates |
| `code/generate_warehouse.py` | Builds the DuckDB warehouse and clean tables (about 30 s) |
| `code/build_world.py` | Builds `data/facts.yaml` and the 47 `world/` files |
| `code/build_requests.py` | `briefs` subcommand builds the 60 request briefs; `assemble` checks the frozen wording and writes the final request texts |
| `code/build_key.py` | Builds `data/key/` (reference SQL, keyword rules, accepted readings) |
| `code/validate_data.py` | 408 checks across arms, world, requests and key (about 2 min); reads `data/key/` |
| `code/validate_arms.py` | Arm-specific checks; check A0 requires the builder's notes, which are not published (see below) |
| `code/collect_full.py` | Reads the 1,800 frozen final messages into `data/analysis/collected_runs.jsonl` |
| `code/mark.py` | Marks collected answers against the key; with `--adjudication` applies blind decisions; `--self-check` runs the key against itself |
| `code/analyse_full.py` | Produces `results.json` and the 12 prediction verdicts |
| `code/report_tables.py` | Produces `tables.md` |
| `code/test_mark.py` | 80 tests for the marker |
| `code/lane_check.py` | Isolation check across agent transcripts; needs `--subagent-dir` pointing at the transcripts, which are not published |
| `code/recover_final_message.py` | Recovers one agent's final message from its transcript; same dependency |
| `data/facts.yaml` | 206 facts (62 with a trap class) |
| `data/validation_report.json` | Result of the last validator run |
| `data/warehouse/warehouse_manifest.json` | Content hash, row counts, build metadata. The DuckDB file (~68 MB) is not shipped; `generate_warehouse.py` rebuilds it |
| `data/requests/` | `briefs.json`, `wording_batches/`, `wording_raw/` (session data, 4 batches), `test_requests.json` |
| `data/key/` | The answer key in plaintext: `key.json`, 50 reference queries in `reference_sql/`, `review_sheet.md`, `required_flags_proposal.json` |
| `data/agent_runs/` | Frozen record of the 1,800 runs: `full_plan.json`, `counters/` (1,800 files), `scratch/full/` (final messages, usage logs, one recovered message), `superseded_cap12/` (38 earlier runs before the budget increase) |
| `data/analysis/` | `collected_runs.jsonl`, `marked_runs.jsonl`, `adjudication_decisions.json`, `adjudication_blind.md`, `adjudication_map.json`, `leniency_ledger.json`, `lane_check.jsonl`, `lane_check_summary.json`, `results.json`, `tables.md`, `report.md` |
| `interactive/` | `skills-library.html` (self-contained page), `_data.json`, `_template.html`, `build_data.py` (reads `data/key/key.json`), `build_page.py` |
| `writeup/` | `skills_library_case_study.md` |

## Pipeline order

Run from anywhere; paths are resolved from `code/config.py`.

```
python code/generate_warehouse.py            # DuckDB warehouse + clean tables + manifest (~30 s)
python code/build_world.py                   # data/facts.yaml and world/ (~2 s)
python code/build_requests.py briefs         # briefs and wording batches
python code/build_requests.py assemble       # checks frozen wording, writes test_requests.json
python code/build_key.py                     # data/key/ (~1 min)
python code/validate_data.py                 # 408 checks (~2 min)
python code/collect_full.py                  # reads 1,800 frozen finals -> collected_runs.jsonl
python code/mark.py --adjudication data/analysis/adjudication_decisions.json
python code/analyse_full.py                  # results.json and 12 predictions
python code/report_tables.py                 # tables.md
python code/mark.py --self-check             # key against itself (0 failures)
python code/test_mark.py                     # 80 tests
python interactive/build_data.py             # _data.json (needs one private file; see below)
python interactive/build_page.py             # _data.json + _template.html -> skills-library.html
```

No step calls a model. The experiment itself (1,800 agent runs across six cells)
was run as Claude Code subagents, one per run, and only its record is published.

The answer key in `data/key/` is read by `mark.py`, `validate_data.py`,
`validate_arms.py`, and `interactive/build_data.py`. The upstream generation of
requests, world documents and arm materials is blind to it.

Everything through `validate_data.py` is deterministic at `RANDOM_SEED = 42` in
`code/config.py`. `collect_full.py`, `mark.py`, `analyse_full.py` and
`report_tables.py` are also deterministic given the frozen agent outputs.

## Warning: what regenerates and what does not

**Session data (not regenerable, do not delete or re-run):**

- `arms/` (the builder agent's output: document, library, tests). Hash-frozen
  before the full run. Nine of the 45 files here were byte-patched afterwards by
  two literal swaps: the retailer's name (seven files) and a local environment
  name in usage lines, now `<env>` (seven files, five of them the same).
  Otherwise untouched. Re-running the
  builder would produce different materials and change every downstream number.
- `data/requests/wording_raw/` (four batches from the wording agents). Re-running
  would change the request texts the agents saw.
- Everything under `data/agent_runs/` (1,800 final messages, counters, usage
  lines, the 38 superseded cap-12 runs, the recovered message) and
  `full_plan.json`. These are the agents' actual answers.
- `data/analysis/adjudication_decisions.json` (hand decisions taken blind to arm).

**Everything else regenerates from config + seed**, given the frozen
session-produced inputs: world documents, facts, briefs, request texts, the
answer key, collection, marking, analysis, tables, and the interactive page.

**Reproducing the deterministic steps** from this published copy:

Byte-identical to the committed files: `facts.yaml`, all 47 `world/` files, all
10 `data/requests/` files, all 53 `data/key/` files (including `review_sheet.md`),
`collected_runs.jsonl`, `collection_report.json`, `marked_runs.jsonl`,
`leniency_ledger.json`, `adjudication_blind.md`, `adjudication_map.json`,
`results.json`, `tables.md`, `skills-library.html` (from `_data.json` +
template), and `_data.json` (when the private predictions file is supplied).

Marker self-check: 0 failures over 60 requests. `test_mark.py`: 80 tests pass.

Not byte-identical, with reasons:

- The DuckDB file differs between builds (database internals); the content hash
  in the manifest is identical. `warehouse_manifest.json` differs only in
  `built_at`, `run_seconds` and `file_sha256`.
- `data/validation_report.json`: 407 of 408 checks pass. Check A0 requires the
  builder's notes file (`arms/build_notes.md`), which is not published, so it
  reports one failure. The shipped validation report was produced from the full
  record and shows 408 of 408.

## What is not shipped and why

The DuckDB warehouse file (~68 MB) and the held-out parquet tables under
`data/internal/` regenerate from `generate_warehouse.py` and are not shipped for
size. The content hash is in `data/warehouse/warehouse_manifest.json`.

The agent packets (the prompt text each agent received) and staging folders are
working artefacts rebuilt by `build_agent_packets.py` and are not shipped. The
encrypted lock archive (built by `lock_answers.py`) is also not shipped.

`interactive/build_data.py` reads one file that is not published: the frozen
predictions file, from the internal design folder. Without it the script stops. The predictions' titles, verdicts and numbers
are quoted verbatim in `data/analysis/report.md` section 2, and each prediction's
rule is in `data/analysis/results.json` (key `predictions`). The built `_data.json`
and the page are included.

`lane_check.py` and `recover_final_message.py` read the agents' session
transcripts, which are not published. Their outputs are:
`data/analysis/lane_check.jsonl` and `lane_check_summary.json`.

The design documents and decision log are internal working documents.

## The honest scorecard

12 predictions written before the run. The table below reproduces report.md
section 2 (which quotes the titles and verdicts from the frozen predictions
file verbatim) and `results.json`.

| # | Prediction | Verdict | Numbers |
|---|---|---|---|
| 1 | Overall correctness | **NOT MET** | S 149/300 (49.7%), D 298/300 (99.3%), L 295/300 (98.3%). S in band but D and L above it. |
| 2 | Where the gain comes from | MET | D − S = 49.7 pp; L − D = −1.0 pp |
| 3 | Clean requests | MET | S 70/70, D 70/70, L 70/70; spread 0 |
| 4 | Same answer every time | **NOT MET** | Requests with five matching runs: S 33 (needed ≤27), D 57, L 54 (needed ≥39) |
| 5 | Two departments, one number | **NOT MET** | Paraphrase pairs agreeing: S 9 (needed ≤5), D 10, L 10 |
| 6 | Company definitions | **NOT MET** | S 19/60 (needed ≤12), D 60/60, L 60/60 |
| 7 | Rigidity | MET | Default applied against the request: D 0/20, L 0/20 |
| 8 | Problems nobody wrote down | **NOT MET** | L 20/20 (all repaired, none flagged-only); S 5/20 (needed ≤3); L without REQ-T16 15/15 (needed ≤7) |
| 9 | Token use | MET | Median S 71,548 < D 80,897 < L 85,100; L/D = 1.052 |
| 10 | Small model with the library | MET | Haiku L 237/300 (79.0%), Sonnet S 149/300 (49.7%), Sonnet L 295/300 (98.3%); Haiku L − Sonnet S = 29.3 pp; Sonnet L − Haiku L = 19.3 pp |
| 11 | Scripts | MET | L 295/300, L− 297/300 (gap −0.7 pp); on the 12 targeted requests L 56/60, L− 59/60 (L − L− = −3) |
| 12 | Requests the library was not built for | **NOT MET** | No-template 64/65 (98.5%), other 231/235 (98.3%); gap −0.2 pp |

Six met, six not met. Nothing retuned.

Prediction 6 was registered on runs, not requests. By majority vote over the five
runs per request, Sonnet S gets 4 of the 12 company-definition requests right.
The run count is in report.md section 2 and the request-level count in
`data/analysis/tables.md`; on the registered terms it is NOT MET.

## Environment

Python 3.10.19 (conda), duckdb 1.5.6, pandas 2.3.3, numpy 2.2.6,
pyarrow 24.0.0, pyyaml 6.0.3, scipy 1.15.2. `httpx` and `anthropic` are
imported only by the test harness and pilot scripts (not used for the full run).
`pyzipper` is imported by `lock_answers.py` and `test_agent_runs.py`. The DuckDB
build and the full run were done on Windows.
