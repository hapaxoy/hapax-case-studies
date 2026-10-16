# Hapax case studies

The complete pipelines, datasets and held-out answer keys behind the ten case
studies published at [hapax.fi](https://hapax.fi) — an AI advisory and training
boutique in Helsinki. Each folder is one case: the generator that built the
dataset, the code that ran the method, the results, and the analysis, in full.

| Case | What it does | Page |
|---|---|---|
| [`01-churn/`](01-churn/) | A usage-based churn model combined with an agent that reads support tickets | [hapax.fi/case-churn.html](https://hapax.fi/case-churn.html) |
| [`02-erp-cleanup/`](02-erp-cleanup/) | A language model reads legacy ERP spool files; an overseer writes deterministic parsers and keeps the model only for exceptions | [hapax.fi/case-erp-cleanup.html](https://hapax.fi/case-erp-cleanup.html) |
| [`03-invoices/`](03-invoices/) | The same overseer method run on a year of supplier PDF invoices | [hapax.fi/case-invoices.html](https://hapax.fi/case-invoices.html) |
| [`04-contracts/`](04-contracts/) | An overseer learns which CUAD contract-clause categories are boilerplate and writes matchers for them, keeping the model only for the bespoke residue | [hapax.fi/case-contracts.html](https://hapax.fi/case-contracts.html) |
| [`05-board-reporting/`](05-board-reporting/) | A deterministic variance pack says what moved in the numbers; three blinded agent runs say why | [hapax.fi/case-board-reporting.html](https://hapax.fi/case-board-reporting.html) |
| [`06-anomaly-detection/`](06-anomaly-detection/) | Audit rule tests and an Isolation Forest screen a purchase ledger; three blinded agents triage every flag | [hapax.fi/case-anomaly-detection.html](https://hapax.fi/case-anomaly-detection.html) |
| [`07-tenders/`](07-tenders/) | Sixteen invented tenders answered two ways: simulated people with a chatbot, and a gated workflow that extracts the requirements and must cite a facts library for every factual claim | [hapax.fi/case-tenders.html](https://hapax.fi/case-tenders.html) |
| [`08-inbox/`](08-inbox/) | A pipeline classifies 150 customer emails, drafts replies with policy citations, checks each draft against fixed rules and sends it or routes it to a person | [hapax.fi/case-inbox.html](https://hapax.fi/case-inbox.html) |
| [`09-training-outcomes/`](09-training-outcomes/) | A before-and-after assessment of a training programme, tested on a simulated cohort whose true learning was set in advance | [hapax.fi/case-training-outcomes.html](https://hapax.fi/case-training-outcomes.html) |
| [`10-talent-screening/`](10-talent-screening/) | 240 synthetic job applications screened four ways; a workflow returns evidence with verbatim quotes against twelve requirements, with no ranking or verdict | [hapax.fi/case-talent-screening.html](https://hapax.fi/case-talent-screening.html) |

Most case folders have their own `README.md` with the exact commands to run
the pipeline; every case has its code, data, results and writeup. The design
documents, research notes and agent briefs referred to in code comments and in
the recorded agent inputs and logs are internal working documents and are not
published.

## The method, in one paragraph

Each case runs a method end to end on data engineered so that the right answer
is known in advance and held out of the pipeline throughout, which is what lets
every result be marked against ground truth. Company names,
customers and datasets are fictional unless stated otherwise; nothing here
describes or implies a real client. One case, `04-contracts`, runs on real
documents — 150 SEC-filed contracts from CUAD v1, a public dataset released by
The Atticus Project — marked against CUAD's own attorney annotations rather than
an answer key we wrote ourselves. Negative results are kept in: where a method
missed something, the miss is reported next to the catch, not edited out.

## Regenerate vs artefact — read this before re-running anything

Two different kinds of file live in these repos, and they are not interchangeable:

- **Deterministic code and data** — generators, validators, evaluation scripts,
  and the datasets they produce — are seeded (`RANDOM_SEED = 42` throughout) and
  byte-identical on re-run. Safe to regenerate any time. One exception: the churn
  case's `usage_monthly.csv`, which is frozen (see `01-churn/README.md`).
- **LLM-produced artefacts** — the model's reads, the parsers or matchers an
  overseer agent wrote, the blinded analysts' findings — are the output of a
  specific agent session on a specific date. Re-running the agents produces
  *different* output (same task, different words or judgement calls), which
  would silently invalidate every number published in that case's findings
  report, notebook, and interactive page. These are treated as data, not as
  code to refresh, and are checked into each repo alongside the pipeline that
  produced them.

For cases 01 to 04 and 06, the case's own `README.md` says exactly which of
its files fall into the second category; look for the ⚠️ section before
running anything end to end. In the other cases, treat every agent output
under `data/` the same way.

## Licence

Code (`code/`, `notebooks/`, build scripts) is MIT-licensed — see `LICENSE`.

The synthetic datasets, generated prose, and case-study writeups are
© Hapax Oy, released under CC BY 4.0 — see `LICENSE-DATA.md`.

`04-contracts/data/answer_key/` and `04-contracts/data/manifest.json` are
Hapax adaptations of CUAD v1's `master_clauses.csv` (© The Atticus Project),
also under CC BY 4.0; the governing attribution and citation are in
`04-contracts/data/CUAD_LICENCE_ATTRIBUTION.md`. CUAD's raw contract archive
itself is not redistributed here — `04-contracts/data/contracts/` holds the
150-contract sub-corpus this case uses, and `data/manifest.json` carries the
source URL and checksum for the full archive.
