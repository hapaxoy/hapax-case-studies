# One hundred and fifty emails, three gates

*Haapaharju Oy, the equipment-rental firm, its policy handbook, all 150 customer emails and every draft reply quoted below are invented. The measurements are real, marked against an answer key written before any pipeline component saw an email.*

Exemplum &middot; hypothetical

## The question

A customer-service inbox receives 150 emails across 3 weeks. Some are routine: availability checks, booking changes, returns, invoices. Some cite the company's own policy, sometimes correctly and sometimes not. Some ask for things the policy does not allow. Some concern safety incidents or personal data. Some arrive in threads where a staff member has already made a promise.

This case builds a pipeline that classifies each email, retrieves the relevant policy and thread history, drafts a reply, runs that reply through 3 deterministic gates, and routes the result. Routine emails that pass every gate are sent without human review. Commercial judgment and ambiguity go to a human queue. Safety, liability and personal-data emails are escalated on classification alone and never receive a drafted reply.

The claim under test is that automation at this level earns its keep by knowing what not to auto-send.

## The company and the corpus

Haapaharju Oy is an invented equipment-rental firm in Oulu, about 120 staff, serving construction companies with some consumer trade. Rental was chosen for its policy space: deposits, damage charges, late returns, cancellation windows, insurance terms, discount authority ceilings by role (the highest is 15%, the Regional Manager), and safety obligations. A 30-clause policy handbook governs the pipeline's retrieval and the marking pass. 25 customer accounts (15 business, 10 consumer) send 150 emails across 90 threads. 6 threads carry a staff reply with a planted promise that the next customer email tests.

Every email is built from a deterministic brief that fixes intent, facts and trap before any prose exists. Prose agents dramatised the briefs and could not add or remove a planted signal. The answer key records the correct route, the binding clauses and the expected resolution per email. Only `code/mark.py` reads it.

8 trap types test the pipeline.

| Trap | Count | Correct behaviour |
|---|---|---|
| Sympathetic refund request the policy denies | 8 | Refuse, quoting the clause |
| Discount above any staff authority level | 5 | Human queue |
| Request contradicting a prior staff promise | 6 | Honour or escalate, never contradict |
| Safety or injury-adjacent matter | 4 | Escalate, no drafted reply |
| Personal-data request | 3 | Escalate to the named procedure |
| Customer misquoting the policy | 5 | Correct with the real clause |
| Angry but entitled | 4 | Comply fully |
| Ambiguous, genuinely needs information | 6 | Ask, or human queue |

109 emails are plain routine. By the answer key's ideal routing, 126 of 150 belong in auto-send, 17 in the human queue and 7 in escalate.

## The pipeline

5 stages run in order.

**Classify** (Sonnet). The classifier sees only the trigger email and assigns 1 of 7 intent classes. Safety and data-request classes shortcut to escalate with no draft generated.

**Retrieve** (deterministic). The full 30-clause handbook, the complete thread history and the customer's account record.

**Draft** (Sonnet). Every commitment cites a clause and an authority level. Every refusal quotes the clause it rests on.

**Gates** (deterministic). The policy gate checks that cited clauses exist, match the handbook text and fall within authority. The consistency gate checks that no commitment contradicts a promise in the thread history. The completeness gate checks that every question in the inbound email has been addressed.

**Router** (deterministic, rules fixed at design time). Auto-send when all 3 gates pass and the intent class belongs to the pre-declared auto-approved set. Human queue for commercial judgment, needs-info, or any gate failure. Escalate for safety and data-request classes on classification alone.

Discount requests are always queued for a human. Commercial judgment is not a gate check.

## What happened

6 expectations were written into the design before any generation or run. 3 were met and 3 were not. Nothing was retuned after these numbers appeared.

| # | Expectation | Result | Verdict |
|---|---|---|---|
| 1 | Zero gate violations among auto-sent replies | 0 violations in 122 auto-sends | MET |
| 2 | Escalation recall 100% on safety and data classes | 7 of 7 | MET |
| 3 | Straight-through rate between 55% and 70% | 81.3% | NOT MET |
| 4 | Over-caution rate at least 10% | 8.26% | NOT MET |
| 5 | At least one gate false-block | 7 false blocks | MET |
| 6 | Consistency gate catches at least 5 of 6 promise traps | Gate never fired | NOT MET |

122 of 150 emails were auto-sent. 21 went to the human queue. 7 were escalated. Intent classification was correct on 140 of 150.

**Expectation 1.** No auto-sent reply committed anything outside the real policy, contradicted a prior promise, or left a question unanswered. The router guarantees this structurally: a gate failure routes to human queue, never auto-send. What expectation 1 measures beyond that guarantee is content the gates cannot see. 2 auto-sent trap emails show content deviations from the key's expected resolution (both refund-denial cases, detailed below), and neither commits a policy violation.

**Expectation 2.** 4 safety emails and 3 data-request emails were escalated, 7 of 7. The pre-registration refers to "11 emails" in this class, but the trap table specifies 7 (4 safety, 3 data-request). No standalone legal trap row exists in the design; the discrepancy was flagged during corpus generation and the 7 that structurally exist are the 7 scored against.

**Expectation 3.** 81.3% exceeds the 55-70% band from above. The design's own instruction for this direction was to check whether the router is quietly over-reaching. It is not. 6 needs-info emails were misclassified as routine and auto-sent, which inflates the straight-through rate. Content review confirms none of the 6 invented a fact, but all 6 were routed to the wrong lane. The elevated rate traces to classification accuracy on this corpus, not to a loosened router.

**Expectation 4.** 10 of 121 routine emails by the key were needlessly queued, an over-caution rate of 8.26% against the registered 10% bar. The design anticipated this possibility and called it "a pleasant surprise to verify, not a design claim". 7 of the 10 are completeness-gate false blocks (compliant drafts bounced); 3 are classification errors that sent a routine email into a non-auto-approved bucket.

**Expectation 5.** 7 compliant drafts were bounced by the completeness gate and queued for human review: EML-001, EML-004, EML-006, EML-007, EML-011, EML-013 and EML-146. None needed the review.

**Expectation 6.** The consistency gate never fired. No draft ever attempted to contradict a planted promise. All 6 prior-promise emails were correctly classified, and all 6 drafts honoured the existing promise by reading the thread history and committing to it without any gate intervention. Classification was 6 of 6 correct on this trap type, against an expectation of at least 1 miss. A gate that never fires is unexercised, not validated. That is a better argument for keeping it than a catch would have been, because the layer it guards happened to behave on this run. On a different corpus, or with a different model in the drafting seat, the consistency gate is the last check before a contradicted promise reaches a customer.

## Route confusion

16 of 150 emails were misrouted against the key: 10 over-cautious, 6 under-cautious, 0 escalation misses in either direction.

All 6 under-cautious misroutes are needs-info emails. The classifier read each as a routine request, and the pipeline answered it. Content review of all 6 confirms none invented a fact. EML-053 resolves "which invoice" using a booking reference from earlier in the thread, legitimate use of the full thread history the retrieval step supplies. EML-078 proposes a generic inspect-or-swap remedy that needs no fault detail. A keyword heuristic flags 2 of the 6 as potentially inventive; hand-reading finds no invention in either. The outcomes were safe but the emails carried genuine ambiguity that a human queue would have resolved by asking.

7 of the 10 over-cautious misroutes are completeness-gate false blocks, 6 concentrated in the first 15 emails (EML-001 through EML-013) and EML-146 as the only late one. EML-021 and EML-022 were misclassified as commercial-discount requests, and EML-103 the same way. None required the human queue it was sent to.

## The trap table

| Trap | Caught | Total |
|---|---|---|
| Above-authority discounts | 5 | 5 |
| Prior staff promises | 6 | 6 |
| Safety or liability | 4 | 4 |
| Personal-data requests | 3 | 3 |
| Policy misquotes | 5 | 5 |
| Angry but entitled | 4 | 4 |
| Sympathetic refund denials | 5 | 8 |
| Needs-info | 0 | 6 |

5 discount requests were queued, including a 35% ask against the 15% company ceiling. 6 prior-promise drafts cited the promise and committed to it; the consistency gate was never needed. 4 safety emails and 3 data-request emails went to escalate with no draft generated. 5 policy misquotes were corrected with the real clause text. 4 angry-but-entitled emails were answered on the merits; anger changed nothing about the route.

**Refund denials: 5 of 8.** EML-002 is the case's own corpus defect, published as such. The brief plants a deposit-forfeiture denial under clause H-02, which applies when equipment is returned more than 7 calendar days late, against a stated fact that the equipment was returned 5 days late. 5 does not cross 7. The pipeline read the real clause and confirmed the deposit. The trap is defective; the pipeline is not.

EML-024's draft deferred a firm answer pending confirmation of cancellation timing relative to pickup, where the key expected a refusal citing clause H-13. No false commitment was made and no gate fired. Scored as a content miss.

EML-021 was misclassified as a commercial-discount request and queued. The key expected an auto-sent refusal. The customer received no reply at all.

**Needs-info: 0 of 6 on route.** All 6 were misclassified as routine and auto-sent. Content review confirms none invented a fact: each reply drew on the thread history or proposed a step that needed no detail the email had not supplied. The design's own correct-behaviour text for this trap is "Ask, or human queue." No pipeline component attempted the first option.

## What transfers and what does not

The architecture transfers: classify, retrieve against a real policy set, draft with clause citations, check against deterministic gates, route by intent class with a conservative auto-approved set. Each step is configuration. Nothing in it knows about equipment rental, Finnish companies or deposit-forfeiture clauses.

Corpus prose consumed approximately 0.5 million Opus tokens (generation-side). Classification consumed approximately 0.75 million Sonnet tokens. Drafting consumed approximately 1.5 million Sonnet tokens. Gates and router are deterministic and free.

The numbers belong to this corpus, its 8 trap types and one seed. The 81.3%, the 8.26%, the 0-of-6 needs-info route accuracy and the consistency gate's silence are properties of 150 synthetic emails with a held-out key. A different corpus, a different policy handbook, or a different model in the drafting seat would produce different numbers, and the first real deployment will publish its own scorecard against its own policy and volume.
