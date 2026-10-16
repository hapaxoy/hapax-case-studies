# 06 Anomaly Detection — adjudicated scorecard

The marking of Case 6's three-layer demonstration against the held-out answer key.
Written by hand from `evaluation_worksheet.md` and the raw `run_0N_findings.json`
files (the worksheet is mechanical and hands down no final verdicts — 05's
convention); everything that went wrong stays in (ml_report precedent).

**Mechanism honesty.** The three storyteller runs are Claude Code subagents
(Opus), mutually blinded, each given the same pinned briefing verbatim,
with only run-number bindings added. All three audit lists are clean: every run
opened exactly the seven whitelisted input files — no answer key, no design
documents, no other run's folder. No cost figures are claimed;
the runs are session artefacts and re-running them would produce different
results — that variance is part of the story, and this document records it.

---

## 1. The detection layers against the key (tier 1, mechanical)

**Rule layer** — exactly as pre-registered, to the flag:

| Test | Flags | On planted anomalies | On declared benign |
|---|---|---|---|
| duplicate | 14 | 12 (D) | 2 (B3) |
| round_sum | 18 | 6 (R) | 12 (B1) |
| near_threshold | 4 | 4 (R) | 0 |
| split | 10 | 10 (S) | 0 |
| calendar | 10 | 8 (W) | 2 (B2) |
| mapping | 8 | 8 (A) | 0 |
| name_hygiene | 0 | 0 | 0 |
| **total** | **64** | **48** | **16** |

First-pass precision vs the anomalous key: **48/64 = 75%**, the designed figure.
Recall on every rule-shaped class: 100%.

**Detector layer — the frozen deviation, confirmed mechanically.** 200 flags of
50,000 (contamination as designed); **zero overlap with any answer-key
transaction**. The three designed catches were missed: G 0/12 (pre-registered
≥6), B4 and B5 unflagged (expected top singletons). The one designed *negative*
held: C 0/12 — nothing flags Neuvantila. Diagnosis recorded at deviation time
(3 Jul 2026): a sustained drift inflates the full-year
baseline it is measured against (Teräskontio's H2 z peaks at +2.13, not the
clean-baseline ~+6.5); the pinned neutral edge-cases make single-invoice vendors
invisible; and against heavy-tailed organic amounts a +19% shift on one tight
vendor is small in population terms. Frozen, not retuned, per the design's own
pre-commitment.

## 2. The catch matrix — designed vs as-run

| Class | Designed catch | As run |
|---|---|---|
| D — duplicates | Rules | **Rules** ✓ (12/12 flagged) |
| R — round/near-tier | Rules | **Rules** ✓ (10/10) |
| W — non-working-day | Rules | **Rules** ✓ (8/8) |
| S — splits | Rules | **Rules** ✓ (10/10) |
| A — mis-posted account | Rules | **Rules** ✓ (8/8) |
| V — name variants | Agents (free hunt) | **Agents, 3/3 runs** ✓ |
| G — the drift *(the exemplum)* | Detector → agents | **Nobody** — detector missed (frozen deviation) and all three free hunts left it unclaimed |
| C — the ceiling | Nobody | **Nobody** ✓ — and no run accused it (0 trap hits) |

The case was designed with one class nothing catches. As run, it has two — and
the second is the exemplum. That is the honest headline: the story this case
was named for (the vendor whose freight consolidation hides a price creep — the
advisory page's "margin that dipped") sits in the data, breadcrumbed in the
memos ("sis. rahtikulut") and mirrored in the freight carrier's decline, and it
was found by neither rules (by design), nor the detector (missed), nor three
independent one-pass analysts. A ~€1,800/month drift on one vendor is invisible
in account-level monthly totals; only a per-vendor H1/H2 movers sweep with a
drill-down would have surfaced it, and no run drilled there.

## 3. The runs — unit verdicts (39 units each; expected verdicts derived from the key)

| | run 01 | run 02 | run 03 |
|---|---|---|---|
| Units correct | **37/39** | **35/39** | **38/39** |
| Anomalous-expectation units (10) | 8/10 | 7/10 | 10/10 |
| Benign-expectation units (29) | 29/29 | 28/29 | 28/29 |
| Missed worries | R-ROUND, W (stood down) | S ×3 (stood down) | — |
| False positives | 0 | 1 (B3) | 1 (B3) |
| Free-hunt findings | 2 | 2 | 1 |

- **All 26 detector units were correctly stood down by all three runs** (78/78
  verdicts), each with recomputed evidence (allowed accounts, within-vendor
  ranges, no rule co-flags). The 200-flag triage burden was carried cleanly —
  the false-positive-discipline exhibit the case was built around.
- **Run 01's misses**: R-ROUND stood down (read the six round-thousand invoices
  as contract-style billing) and W stood down (read U-117's weekend postings as
  flexible-hours data entry). Both defensible-sounding, both wrong against the
  key — exactly the calls the marking exists to catch.
- **Run 02's misses**: all three split units stood down on the "osatoimitus"
  memo reading (partial deliveries). The memos do say that; the designed signal
  is that the parts sum over the tier within days at exactly three vendors.
  Runs 01 and 03 read it correctly.
- **The two false positives are the same item**: B3, the designed coincidental
  equal-amount pair whose distinct PO references are the designed stand-down
  evidence. Runs 02 and 03 saw the differing POs and still hedged to
  worry/watch ("verify against source documents"). Adjudicated as false
  positives — the evidence was present and sufficient — while noting the
  failure mode is cautious hedging, not invention. Run 01 read it correctly,
  explicitly contrasting the distinct POs with the D-class pairs' shared order
  reference.
- **Run 01's second free-hunt finding** (the unmatched worry) accused nobody:
  it observed that the ledger's largest hand-keyed postings — including the
  €78,400 capex — sit outside both detection layers' reach, and recommended a
  value-based review. That is a correct, independently-derived statement of the
  B4/B5 detector blind spot this project logged as part of the frozen
  deviation. Adjudicated as a legitimate control observation, not a false
  positive.

## 4. The stories

- **V (the Kärrenbach trio): found by 3/3 runs**, in every case as the run's
  top-priority action item, in every case with the full mechanism — one legal
  entity as three master records, shared VAT id and Hamburg address, three
  spellings, three different IBANs, and the reason the rule layer missed it
  (byte-identical name matching). The designed agent-only class behaved exactly
  as designed, three times independently.
- **G: 0/3** (and the Kuormaraitti mirror, its second-order evidence: 0/3). See §2.
- **C: clean 3/3.** Twelve unremarkable consulting invoices drew no accusation
  from any run — the false-positive trap side of the ceiling class held.

## 5. Figures

364 evidence figures machine-checked across the three runs: **zero
disagreements** (219 matched exactly or within aggregate tolerance; 102
compound strings not machine-checkable were sampled and hand-verified —
including "51 invoices ≥ €10,000 across 14 vendors", "8 of 1,466 U-117 rows",
and the €10,664.40 recoverable duplicate halves — all exact).
**Two recorded imprecisions**: runs 01 and 03 headline the Kärrenbach trio's
combined spend as €48,001 while their own correct components (23,651.32 +
15,026.40 + 10,323.64) sum to **€49,001.36**; run 02 states it correctly. A
−€1,000 arithmetic slip in the headline figure of two runs, components right,
mechanism right.

## 6. What this adds up to

The layered argument, as evidenced rather than asserted: the deterministic
rules caught **every** rule-shaped plant at the designed 75% first-pass
precision; the generic transaction-grain detector caught **none** of the
designed anomalies and 200 statistically-odd-but-benign rows; and the reasoning
layer triaged all 264 flags with two hedged false positives, found the
cross-record story no other layer could reach three times out of three — and
still left the drift story on the table three times out of three.

Which is the point this case shares with its top-down sibling (05), now with
sharper teeth: agents extend detection meaningfully beyond rules and models,
and their reach still has edges that only marking against ground truth reveals
— for the detector as much as for the storyteller. A dataset with a known
answer key is what makes this paragraph checkable rather than a claim.
