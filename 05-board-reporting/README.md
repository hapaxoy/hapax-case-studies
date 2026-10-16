# 05 Board Reporting — "The board pack that answers back"

Case 5 of the Hapax case studies. A deterministic variance pack says what moved;
three blinded agent runs say why, or say stand down; everything is marked against a held-out
answer key. The dataset is synthetic (Paju Consumer Products Oy, fictional), seeded,
and byte-identical on regeneration.

## Pipeline (run from this folder)

```
python code/generate_financials.py      # 9 public tables + data/answer_key/stories.csv (seed 42)
python code/validate_financials.py      # 12 coherence rules; exits 1 on any failure
python code/variance_analysis.py        # the deterministic pack -> data/analysis/surface_report.md + 3 CSVs
# 3 blinded Claude Code subagent runs, each given the same pinned briefing
#   -> data/analysis/agent_runs/run_0N_findings.json + run_0N_memo.md
python code/evaluate.py                 # mechanical worksheet -> evaluation_worksheet.md + scores CSV
# data/analysis/report.md = the adjudicated scorecard, written by hand from the worksheet
python code/build_interactive_data.py   # distils public CSVs -> interactive/_data.json (asserts vs worksheet)
python code/merge_interactive_data.py   # inlines the JSON into the self-contained page
python interactive/_verify_page.py      # page QA (embeddability + typography); exits 1 on failure
```

## Where things live

| Artefact | Location |
|---|---|
| Generation + analysis + evaluation code | `code/` |
| Public dataset (9 tables) | `data/*.csv` |
| Answer key — held out of the analysis path | `data/answer_key/stories.csv` |
| The pack, the agent runs, the marking | `data/analysis/` |
| Adjudicated scorecard (honest misses kept in) | `data/analysis/report.md` |
| Executed analysis notebook | `notebooks/board_reporting.ipynb` |
| Interactive page (single self-contained HTML) | `interactive/board-reporting.html` |
| Canonical long-form writeup | `writeup/board_reporting_case_study.md` |

## Environment notes

- Python with pandas/numpy/matplotlib runs the whole pipeline. Re-executing the
  notebook additionally needs `nbformat`, `nbconvert`, `ipykernel` (pip; invoke as
  `python -m nbconvert --to notebook --execute --inplace notebooks/board_reporting.ipynb`
  — the `jupyter` launcher may not be on PATH).
- The interactive page was visually QA'd via headless Chrome
  (`chrome --headless --screenshot=... --window-size=1240,4600 <file:// URL>`);
  the `#agents-open` deep link renders every evidence drill for a single capture.
- The three storyteller runs are session artefacts of the agent mechanism (Claude
  Code subagents, 2 Jul). Their outputs and audits are durable in
  `data/analysis/agent_runs/`; re-running them means new agent sessions with the
  pinned briefing, and results will vary — that variance is part of the story.

## The one-line result

All four planted stories were found or correctly stood down by 3/3 independent runs
(zero false positives, zero wrong figures across 30 findings) — and the two sharpest
pieces of designed evidence went unclaimed by every run, which is the case study's
actual argument: check agents against ground truth before believing them.
