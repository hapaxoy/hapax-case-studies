# Two hundred and forty applications, screened four ways

*Kaikuvaara Oy, the twelve-requirement role, all 240 applicants and every CV and cover letter quoted below are invented. The measurements are real, marked against an answer key written before any screening arm saw a document.*

Exemplum &middot; hypothetical

## The question

A hiring team receives 240 applications for a senior signal-processing engineer at a remote-sensing instruments maker in Oulu. Every application carries a CV and a substantive cover letter. Reading all of them carefully against all 12 requirements takes more time than the team has.

This case builds a workflow that reads every application against the requirement profile and produces, per candidate, an evidence dossier. For each requirement, the dossier records what the application shows with a verbatim citation, what it claims without substantiation, what contradicts itself and what is not stated and should be asked in a screening call. An aggregate coverage table lists per-candidate evidence counts, unsorted; sorting is the reader's act, and the system emits no order. The workflow produces no ranking, no shortlist, no reject pile and no verdict on any candidate. The recruiter decides.

That is the assistive shape on purpose. Recruitment sits in Annex III of the EU AI Act as a high-risk category, and Article 14's human-oversight requirement points at a system that surfaces evidence under human decision-making. It is also the only honest shape for a case on synthetic data: an engineered corpus can prove what evidence a system surfaces, and cannot prove who should have been hired.

Because every application is synthetic with the qualification truth engineered per candidate, the case can measure something almost nobody can measure on real data: whether the evidence layer treats demographically distinct but equally qualified candidates identically. No real applicant pool could serve this test. The answer key would not exist.

## The corpus

Kaikuvaara Oy is a fictional remote-sensing instruments maker in Oulu. Twelve requirements are frozen in the configuration: 5 must-have technical (phased-array/beamforming signal processing, embedded DSP in C/C++, production Python, RF measurement experience, relevant degree or demonstrated equivalent), 4 desirable (Kalman/estimation theory, satellite/airborne platforms, team-lead experience, publications or open-source record), 3 constraints (EU work authorisation, working English, onsite in Oulu or relocation). The domain is deliberately deep-tech: rare skills, a small talent pool, applications from career-changers and adjacent fields.

| Archetype | n | What it plants |
|---|---|---|
| Clear fit | 21 | Every must-have evidenced plainly |
| Clear miss | 87 | Fails 3 or more must-haves, no disguise |
| Near miss | 36 | Exactly 1 must-have genuinely absent |
| Keyword stuffer | 22 | Claims everything; evidence thin or circular |
| Credential inflation | 15 | 8 degree-date clashes, 7 leadership-title clashes |
| Hidden gem | 18 | Fully qualified, one must-have under displaced vocabulary |
| Nonlinear path | 15 | Career gaps, competence intact |
| Genuine borderline | 12 | Engineered "defensible either way" in the key |
| Off-role | 14 | Realistic noise floor |

22 keyword stuffers use the right vocabulary with little substance behind it. C228 sits at keyword rank 1. 15 applicants carry a planted credential inflation, 8 where a degree conferral date is contradicted by a job that required the degree already finished, and 7 where a claimed leadership title is contradicted by the plain title and short tenure in the same role.

18 hidden gems meet every requirement but each with one must-have worded in unfamiliar terms: acoustic beamforming described as hearing-aid array processing, embedded DSP as engine-control-unit firmware, production Python as particle-physics analysis scripts. C213, the clearest example, evidences all five must-haves and ranked 144th by keyword matching. One of the five, production Python, appears only in the cover letter as automation and analysis scripts for a particle-physics detector collaboration, and the word "Python" is nowhere in the application. 9 of the 18 carry their displaced evidence only in the cover letter.

Every candidate carries surface demographic correlates (name origin, gender, graduation-year band, degree country, career-gap status), assigned orthogonally to qualification truth by construction. Any difference the evidence layer shows between strata belongs to the system, not the data.

## Four arms

The same 240 applications were screened four ways, all marked against the same key.

**Arm 1, the ATS.** A deterministic keyword matcher: requirement terms and plain synonyms, scored across the full text, weighted by must-have/desirable/constraint. Its output is a ranked list. The synonym list was built from the requirement text, never from the displacement table.

**Arm 2, the naive local model.** One prompt per candidate on Haiku: application plus the 12 requirements, no citations, no refuse-to-guess gate.

**Arm 3, the disciplined local model.** The full workflow's extraction contract on the same Haiku, isolating discipline from parameter count.

**Arm 4, the full workflow.** Extraction on Sonnet, with the refuse-to-guess gate, verbatim citations, consistency checks and the no-verdict constraint.

## What happened, in numbers

Ten predictions were set before marking began. Four were met, including the evidence recall at 96.71% against a 95% bar. Six were not. Nothing was retuned after the numbers appeared.

| # | Registration | Result | Verdict |
|---|---|---|---|
| 1 | Evidence recall &ge; 95% | 96.71% (618 of 639) | MET |
| 2 | Invented evidence < 1% | 0.09% (2 fabrications; 17 of 19 failures transcription) | MET |
| 3 | Hidden gems &ge; 15 of 18 | 12 of 18 | NOT MET |
| 4 | Stuffers &ge; 19 of 22 | 19 of 22 | MET |
| 5 | Parity &le; 2pp between strata | grad_year_band 2.88pp, degree_country 2.48pp | NOT MET |
| 6 | With-dossier &ge; 2&times; unaided on gems | 1.32&times; (41 vs 31 of 48) | NOT MET |
| A1 | ATS ranks &ge; 15/22 stuffers above median | 22 of 22 | MET |
| A2 | ATS surfaces &le; 3/18 gems' displaced skill | 15 of 18 keyword hits (mis-registered) | NOT MET |
| A3 | Naive fabrication > disciplined citation failure | Inverted: 16.53% vs 2.59% | NOT MET |
| A4 | Disciplined beats ATS on gems and stuffers | Stuffers yes; gems no | NOT MET |

Across 240 applications the workflow extracted 2,116 evidence lines with verbatim citations. 618 of 639 key-recorded must-have evidence items appeared in the dossiers. Of the 19 citations that failed verification, 17 were minor transcription differences and 2 were fabricated, quotes the candidate's application does not contain. Both fabrications are hallucinated contradictions, detailed in the adjudication below.

## Where the gems hid

12 of 18 hidden gems had their displaced skill surfaced as evidence against the right requirement. The misses concentrated in the cover letter: 5 of the 9 gems whose displaced skill appeared only there were missed, against 1 of the 9 whose evidence was elsewhere. Where the CV describes a role in one vocabulary and the cover letter describes related work in another, the workflow chose the harsher reading, calling a contradiction and consuming evidence it would otherwise have surfaced.

C232 shows the sharpest case of this. His CV describes a January &ndash; August 2020 role as signal conditioning and filter implementation. His cover letter describes the same role as designing phased-array beamforming algorithms and a 12-element receive array processor, in the same sentence that carries the planted title inflation ("Head of Signal Processing &hellip; directed a team of six"). The genuine R01 evidence and the fabricated R08 claim share a sentence, so distrust of the lie swallowed the truth beside it. No careful reader can separate the two, and that is the argument for asking in screening.

The interactive page leads with a matched pair selected from the marked results. C213 ranked 144th by keyword matching and evidences every must-have per the key. C228, the stuffer the ATS pushed to rank 1, has 4 of 5 must-haves recorded as claims without substantiation. Arm 4 itself over-credited C228 on R05, returning evidence_found where the key holds claimed_only; that over-credit is published in the exhibit.

## What the discipline carries

The ATS ranked all 22 keyword stuffers above the pool median. Rank 1 is a stuffer. A keyword matcher cannot distinguish a claim from evidence; a workflow with a refuse-to-guess gate can, regardless of model size, and the disciplined Haiku flagged claims as unsubstantiated on 20 of 22 stuffers against the ATS's 0 of 22.

15 planted credential inflations (8 degree-date, 7 leadership-title) separate the arms. Arm 4 caught 14 of 15. Arm 3 caught 1. The naive arm caught 0.

The workflow's refuse-to-guess discipline transferred to the smaller model; verbatim citation quality did not. The disciplined Haiku's citation-failure rate was 16.53%, against the naive Haiku's 2.59% and Sonnet's 0.90%. Haiku merges adjacent lines into non-verbatim quotes. The assembly layer's verification step caught every one of those failures. The workflow's safety net works even when the model inside it does not quote accurately.

C213 carries 3 of 5 must-have keyword hits and still sits in the bottom half. A keyword match that fires without changing the ranking tells the recruiter nothing useful.

## How the marking was checked

12 arm-4 contradiction calls do not match a planted credential inflation. Each was adjudicated by reading the candidate's application text against the dossier entry and the answer-key row.

All 12 erred toward over-suspicion, never credulity. 2 are extractor errors resting on fabricated quotes (C022 and C039, both counted in the fabrication rate). C039's dossier quotes a beamformer having "met its performance specification on the first flight" when every flight-adjacent line in the application says ground-based; C022's dossier quotes a site opening date that appears nowhere in the CV. 5 sit at the claimed_only/contradiction boundary, read harshly on stuffer-style claims but substantively aligned with the key every time. 3 are genuine corpus prose defects found after the run (C079's one-publication-two-identities, two minor date-phrase slips), published as the case's own errors. C232's entanglement is described above. C114, a letter-only R01 planting, was misread as cross-document conflict when the CV's project and the letter's project were two distinct pieces of work with similar names.

The cost of the over-suspicion concentrates on the letter-only plantings, which for a screening aid is the less harmful direction.

## Parity

Pre-registration 5 asked that evidence recall and flag rates differ by at most 2 percentage points between any two demographic strata. On 3 of 5 dimensions (name origin, gender, career gap) the workflow meets the bar. Graduation-year band (2.88pp) and degree country (2.48pp) exceed it on recall; flag-rate parity holds on every dimension, all spreads below 0.52pp.

Arm 3 shows the tightest parity of the four arms: largest recall spread 1.75pp, every dimension inside 2pp. Arm 2, the naive Haiku, shows the widest: career-gap spread 3.79pp, every dimension outside. Discipline narrows the parity gap; the full workflow's remaining failures sit at the boundary and are concentrated in 2 of the 5 dimensions.

## The persona experiment

12 simulated recruiter personas screened a stratified 48-application subset two ways: unaided and with the dossier beside the application, at an equal time budget of 240 seconds per application. The subset holds 4 hidden gems, which gives the 12 personas 48 gem readings per arm. Unaided, they advanced the gem on 31 of 48; with the dossier, on 41.

| Diagnostic | Unaided | Assisted |
|---|---|---|
| Gem holds | 15 | 7 |
| Stuffers questioned | 75% | 92% |
| Inflations spotted | 56% | 94% |
| Borderlines flagged as borderline | 33% | 8% |

The larger effects were elsewhere. Inflations spotted rose from 56% to 94%, the largest lift, concentrated on cross-document title inflation where the dossier makes the contradiction visible. Stuffers questioned rose from 75% to 92%. Gem holds fell from 15 to 7: the dossier converted hesitation into commitment.

The subset also holds two candidates built to be defensible either way. Personas marked them as borderline on 33% of unaided readings and 8% of assisted ones. The dossier turned a genuinely open call into a firm decision, the one measured place where it made the personas less careful, not more.

P12 overrode a false citation flag on C062 and confirmed the fabricated C039 contradiction, correcting the tool in both directions. P11 read every dossier flag on the title-inflators and advanced them regardless. P01 advanced C210 unaided, then held him once the dossier showed the title contradiction.

The pattern was not uniform. The two least strict personas went from questioning none of the four stuffers to questioning all four, while the most keyword-reliant persona questioned none in either arm and the strictest was unchanged on gems. One persona advanced fewer gems with the dossier than without.

## What transfers and what does not

The architecture transfers: extraction against a requirement profile with verbatim citations, a refuse-to-guess gate, consistency checks, an aggregate table the recruiter sorts. Each step is configuration; nothing in it knows about remote sensing, keyword stuffing or Finnish cover letters. What was demonstrated is that this workflow can be set up and customised for a role, and that the discipline it imposes carries measurable value: 14 of 15 planted credential inflations caught, 19 of 22 stuffers identified, evidence recall at 96.71%, and a directional bias toward over-suspicion.

Extraction consumed approximately 4.4 million Sonnet tokens. The two Haiku arms consumed approximately 4 million between them, and the 24 persona runs approximately 7 million Sonnet tokens. The ATS is deterministic and free. Corpus authorship is generation-side, measured separately.

The numbers belong to this corpus, its archetype mix and one seed.

Recruitment is the domain where the rules bind hardest. Applications are personal data end to end, and the AI Act's high-risk regime and GDPR keep a human at the helm of the decision. The natural deployment is a small model on the client's own hardware, processing applications that never leave the organisation's infrastructure. The workflow discipline transfers to a small model (arm 3's parity, arm 3's stuffer identification) and verbatim citation quality does not (arm 3's 16.53% citation-failure rate against arm 4's 0.90%). Fine-tuning a local model on the client's own historical screening material, under the client's own lawful basis, is the genuine next step.
