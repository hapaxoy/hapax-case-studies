# 10 Talent Screening — project map

Project 10 of the Hapax case studies.
Adjudication summary below; marking scorecard in
`data/analysis/report.md`; writeup in `writeup/talent_screening_case_study.md`.

## The one-line result

240 synthetic applications for one deep-tech role, screened four ways against the
same answer key. The workflow (Sonnet, with a refuse-to-guess gate, verbatim
citations and no verdict) caught 14 of 15 planted credential inflations and
identified 19 of 22 keyword stuffers as unsubstantiated. The disciplined small
model (same contract on Haiku) caught 1 of 15 inflations and 20 of 22 stuffers.
The keyword ATS caught 0 inflations, ranked all 22 stuffers above the pool median,
and put a stuffer at rank 1. 4 of 10 pre-registrations met, 6 not met; nothing
retuned after the numbers appeared.

## What the case demonstrates

A hiring workflow that reads every application against a 12-requirement profile
and produces an evidence dossier per candidate. For each requirement, the dossier
records what the application shows with a verbatim citation, what it claims
without substantiation, what contradicts itself and what is not stated and should
be asked in a screening call. An aggregate coverage table lists per-candidate
evidence counts, unsorted; sorting is the reader's act, and the system emits no
order. The workflow produces no ranking, no shortlist, no reject pile and no
verdict on any candidate. The recruiter decides.

Because every application is synthetic with the qualification truth engineered per
candidate, and every demographic surface feature (name origin, gender-coded name,
graduation-year band, degree country, career-gap status) is assigned orthogonally
to that truth, the case publishes a measurement almost nobody can produce on real
data: whether the evidence layer treats demographically distinct but equally
qualified candidates identically.

A 12-persona, two-arm experiment (unaided vs with-dossier, 48-application
stratified subset, equal time budgets) measured what the dossier changes for a
simulated recruiter. The registered headline (2x hidden-gem identification) was
not met; the measured effects sat elsewhere: stuffers questioned rose 75% to 92%,
inflations spotted rose 56% to 94%, and gem holds fell from 15 to 7 as the
dossier converted hesitation into commitment.

## What lives where

| Path | What it is |
|---|---|
| `code/config.py` | Every tunable: 12 requirements, displacement table, archetype table (9 archetypes, exact counts), demographic name pools, company, personas, persona subset, time budget |
| `code/generate_structured.py` | Deterministic generator: roster, answer key, briefs, persona subset |
| `code/validate_structured.py` | Every corpus coherence rule; exits 1 on any failure |
| `code/split_briefs.py` | Batches the 240 briefs into 30 files of 8 for the prose-writing agents |
| `code/qa_corpus.py` | Prose QA sweep over the written corpus (keyword, date, degree, letter checks) |
| `code/build_extraction_tasks.py` | Per-candidate extraction tasks + 8-candidate batches; no LLM calls, never reads the key |
| `code/assemble_dossiers.py` | Assembles raw extraction output into per-candidate dossiers + coverage table; verifies every quoted citation verbatim; never reads the key |
| `code/validate_dossiers.py` | Structural + no-verdict-vocabulary checks; exits 1 on failure; never reads the key |
| `code/ats_baseline.py` | Arm 1. Deterministic keyword/synonym ATS, synonyms from requirement text only (never the displacement table); full-text and CV-only variants; the only script in the project that ranks |
| `code/build_naive_tasks.py` | Arm 2. Naive-prompt task batches (plain "which requirements does this candidate meet", no citations, no refuse-to-guess) |
| `code/build_disciplined_tasks.py` | Arm 3. Task batches using arm 4's extraction contract verbatim, differing only in output path |
| `code/validate_baselines.py` | Synonym-leak check, arm 2/3 coverage, ATS rank determinism; exits 1 on failure |
| `code/persona_arm.py` | Task generation for the unaided/assisted human-arm simulation from persona_subset.json |
| `code/mark_results.py` | **The only script permitted to read the answer key.** Scores all 10 pre-registrations across all 4 arms + the persona experiment; outputs `data/analysis/marking.json` and `data/analysis/report.md` |
| `code/fix_duplicate_names.py` | One-off repair script (7 duplicate full names fixed surgically mid-build; kept in the tree for the record) |
| `data/answer_key.csv` | Per candidate x per requirement ground truth (2,880 rows). Held out of the pipeline entirely |
| `data/answer_key_candidates.csv` | Per-candidate summary key (240 rows) |
| `data/briefs/` | One brief per candidate for the prose-writing agents |
| `data/brief_batches/` | 30 batches of 8 briefs, output contract embedded |
| `data/applications_raw/` | 30 batches of 8 written applications (CV + cover letter). **Session data** |
| `data/extraction_tasks/` | One extraction task per candidate (application text + 12 requirements + extraction contract) |
| `data/extraction_batches/` | 30 batches of 8 extraction tasks (arm 4) |
| `data/extraction_raw/` | Raw extraction-agent output (arm 4, Sonnet). **Session data** |
| `data/dossiers/` | Assembled per-candidate evidence dossiers (arm 4 output, 240 files) |
| `data/dossiers/_citation_failures.json` | 19 citation failures in 2,116 quoted lines (0.90%) |
| `data/coverage_table.csv` | Aggregate per-candidate coverage counts, application order, unsorted |
| `data/baselines/` | Arm 1 output: `ats_scores.csv` (full-text) and `ats_scores_cv_only.csv` |
| `data/naive_batches/` | Arm 2 task batches (30 x 8) |
| `data/naive_raw/` | Raw naive-Haiku output (arm 2). **Session data** |
| `data/disciplined_batches/` | Arm 3 task batches (30 x 8, contract byte-identical to arm 4) |
| `data/disciplined_raw/` | Raw disciplined-Haiku output (arm 3). **Session data** |
| `data/persona_subset.json` | 48-application persona-arm subset + 12 recruiter-persona definitions |
| `data/persona_tasks/` | `unaided/` and `assisted/` screening tasks, one file per persona |
| `data/persona_raw/` | `unaided/` and `assisted/` persona screening output, 24 files total. **Session data** |
| `data/analysis/` | `marking.json` + `report.md` (the full marking scorecard) |
| `writeup/talent_screening_case_study.md` | Canonical writeup |

## Pipeline order

```
python code/generate_structured.py       # answer_key.csv, answer_key_candidates.csv, briefs/, persona_subset.json
python code/validate_structured.py       # every corpus coherence rule; exits 1 on any failure
python code/split_briefs.py              # data/brief_batches/batch_NN.json (30 batches of 8)
# prose-writing agents (Claude Opus 4.6) write CV + cover-letter prose per batch
#   -> data/applications_raw/batch_NN.json
python code/qa_corpus.py                 # prose QA sweep (0 FAIL)
python code/build_extraction_tasks.py    # data/extraction_tasks/, data/extraction_batches/
# extraction agents (arm 4, Sonnet) run against extraction_batches
#   -> data/extraction_raw/batch_NN.json
python code/assemble_dossiers.py         # data/dossiers/, coverage_table.csv, _citation_failures.json
python code/validate_dossiers.py         # structural + no-verdict checks (green)

# --- baseline arms (pre-registered addendum) ---
python code/ats_baseline.py              # arm 1: data/baselines/ats_scores.csv + _cv_only.csv
python code/build_naive_tasks.py         # arm 2 task batches
# naive Haiku runs -> data/naive_raw/batch_NN.json
python code/build_disciplined_tasks.py   # arm 3 task batches (contract identical to arm 4)
# disciplined Haiku runs -> data/disciplined_raw/batch_NN.json

# --- persona experiment ---
python code/persona_arm.py               # data/persona_tasks/{unaided,assisted}/
# 12 personas x 2 arms (Sonnet) -> data/persona_raw/{unaided,assisted}/persona_PNN.json

# --- marking (the only key reader) ---
python code/mark_results.py              # data/analysis/marking.json + report.md
```

`mark_results.py` is the only script in the project permitted to read
`data/answer_key.csv` or `data/answer_key_candidates.csv`. Everything upstream of
it is blind to the key.

Everything through `split_briefs.py` is deterministic at `RANDOM_SEED = 42` in
`code/config.py`. `build_extraction_tasks.py`, `ats_baseline.py`,
`build_naive_tasks.py`, `build_disciplined_tasks.py`, `assemble_dossiers.py`, and
the task-generation side of `persona_arm.py` are also deterministic given the
session-produced application prose. `mark_results.py` is deterministic given the
session-produced arm outputs.

## Warning: what regenerates and what does not

**Session data (not regenerable, do not delete or re-run):**

- `data/applications_raw/` (30 batches, 240 applications). Written by Claude
  Opus 4.6 agents from the deterministic briefs. Re-running would
  produce different prose (same signals, different words) and invalidate every
  downstream number.
- `data/extraction_raw/` (30 batches, arm 4, Sonnet). The extraction agents'
  actual output against the written applications.
- `data/naive_raw/` (30 batches, arm 2, Haiku). The naive arm's actual output.
- `data/disciplined_raw/` (30 batches, arm 3, Haiku). The disciplined arm's
  actual output.
- `data/persona_raw/` (24 files, 12 personas x 2 arms, Sonnet). The persona
  experiment's actual screening decisions.

**Everything else regenerates from config + seed**, given the session-produced
inputs it depends on: briefs, batches, the answer key, extraction/naive/disciplined
task batches, persona tasks, dossiers (derived deterministically from
`extraction_raw/` by `assemble_dossiers.py`), the ATS baseline under
`data/baselines/`, and the marking outputs under `data/analysis/`.

## The honest scorecard

10 expectations written into the design before any generation or run.

### Original pre-registrations

| # | Registration | Result | Verdict |
|---|---|---|---|
| 1 | Evidence recall >= 95% | 96.71% (618/639) | **MET** |
| 2 | Invented evidence < 1% | 0.09% (2 fabrications, 17 transcription slippage, in 2,116 lines) | **MET** |
| 3 | Hidden gems >= 15/18 | 12/18 | **NOT MET** |
| 4 | Stuffers >= 19/22 | 19/22 | **MET** |
| 5 | Parity <= 2pp between strata | grad_year_band 2.88pp, degree_country 2.48pp; other 3 dimensions within 2pp | **NOT MET** |
| 6 | With-dossier >= 2x unaided on gems | 1.32x (41 vs 31 of 48); sensitivity with P07 excluded 1.19x | **NOT MET** |

### Addendum pre-registrations

| # | Registration | Result | Verdict |
|---|---|---|---|
| A1 | ATS ranks >= 15/22 stuffers above median | 22/22 (rank 1 is a stuffer) | **MET** |
| A2 | ATS surfaces <= 3/18 gems' displaced skill | 15/18 keyword hits | **NOT MET** |
| A3 | Naive fabrication rate > disciplined citation-failure rate | Inverted: disciplined 16.53% vs naive 2.59% | **NOT MET** |
| A4 | Disciplined beats ATS on both gems AND stuffers | Stuffers yes (20/22 vs 0/22); gems no (13/18 vs ATS keyword artefact) | **NOT MET** |

### One-line diagnoses of failures

**3 (gems 12/18).** Letter-only plantings are where the workflow lost its gems.
When the CV describes a role in one vocabulary and the cover letter describes
related work in another, the workflow chose the harsher reading, calling a
contradiction and consuming evidence it would otherwise have surfaced.

**5 (parity 2.88pp, 2.48pp).** Recall parity failed on 2 of 5 dimensions at the
boundary. Flag-rate parity held on every dimension (all spreads below 0.52pp).
Arm 3 (disciplined Haiku) shows the tightest parity of the four arms: largest
recall spread 1.75pp, every dimension inside 2pp.

**6 (dossier assistance 1.32x).** A ceiling effect the registration did not
anticipate. Personas found gems unaided at 65%, so doubling required more
advances than the pool could supply.

**A2 (ATS gem hits 15/18).** Mis-registered. The test measured keyword hits, where
the harm is ranking. Generic keywords like "beamforming" appear inside some
displacement phrases and fire without lifting the candidate. C213 carries 3 of 5
must-have keyword hits and still sits at rank 144 of 240.

**A3 (naive vs disciplined, inverted).** Haiku merges adjacent lines into
non-verbatim quotes. Status discipline (refuse-to-guess, the four-status
vocabulary) transferred to the small model; verbatim citation did not. The
assembly layer's verification step caught every failure.

**A4 (hero claim, gem half failed).** The stuffer win is emphatic (20/22 vs 0/22);
13/18 gems do not beat the ATS keyword artefact.

## Adjudication

13 items were adjudicated. Summary:

- 2 extractor fabrications stand as measurement (C022, C039; both already counted
  by pre-registration 2's machinery).
- 6 over-reads at the claimed_only/contradiction boundary, key stands (C076,
  C114, C198, C234, C235, C236).
- 3 corpus prose defects found after the run, published as ours (C079: one
  publication with two identities; C196, C197: minor date-phrase slips).
- C232 published as a design-level entanglement finding: the genuine R01 evidence
  and the planted R08 title inflation share a sentence, so distrust of the lie
  swallowed the truth beside it.
- P07-assisted Yes/No/Maybe vocabulary mapping applied (Yes -> advance, No ->
  decline, Maybe -> hold).

Aggregate observation: every disputed call errs toward over-suspicion, never
credulity. The cost concentrates on letter-only plantings.

## Mid-run incidents

**P05-assisted digest-run quarantine.** The first P05-assisted agent spawned
summariser subagents to compress the applications into digests instead of reading
them directly. A digest layer between the material and the persona would make the
run non-comparable. The summarisers were stopped before any screening output
existed, the invalid output was moved out of the tree, and the run was relaunched
cleanly with an explicit no-delegation rule added to every remaining persona
launch. A pre-output procedural restart, not a fix-and-rerun.

**P07-assisted vocabulary mapping.** The P07-assisted output used Yes/No/Maybe for
screening_decision instead of the contracted advance/hold/decline. The mapping
was drafted before any mapped totals were computed.
Pre-registration 6 is reported both with the mapping applied (1.32x) and with
P07-assisted excluded (1.19x); NOT MET either way, so the verdict does not hinge
on the mapping.

## The corpus at a glance

240 applications for a senior signal-processing engineer at **Kaikuvaara Oy**, a
fictional remote-sensing instruments maker in Oulu. Each carries a CV and a
substantive one-page cover letter (Finnish application convention).

| Archetype | n | What it plants |
|---|---|---|
| A. Clear fit | 21 | Every must-have evidenced plainly |
| B. Clear miss | 87 | Fails >= 3 must-haves, no disguise |
| C. Near miss | 36 | Exactly 1 must-have genuinely absent |
| D. Keyword stuffer | 22 | Claims everything; evidence thin or circular |
| E. Credential inflation | 15 | Title or degree claims contradicted by dates or internal details |
| F. Hidden gem | 18 | Fully qualified, skill under displaced vocabulary |
| G. Nonlinear path | 15 | Career gaps, competence intact |
| H. Genuine borderline | 12 | Engineered "defensible either way" in the key |
| Off-role | 14 | Realistic noise floor |

12 requirements (5 must-have technical, 4 desirable, 3 constraints). Demographic
correlates (name origin, gender, graduation-year band, degree country, career gap)
assigned orthogonally to qualification truth by construction.

The matched pair selected from marked results by the frozen rule: **C213** (hidden
gem, ATS rank 144, all 5 must-haves per key) and **C228** (stuffer, ATS rank 1,
4 of 5 must-haves recorded as claims without substantiation).
