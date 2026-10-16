# Kuusiharju Oy — AI-Augmented Workflows — Assessment Form B

This form is one half of a matched pair (Form A / Form B) used before and after the two-day AI-Augmented Workflows programme. Each learner sits one form before training and the other after, so that no one answers the identical questions twice. There are 10 tasks. Work through them in order; there is no trick in the ordering. Answer in your own words — there is no single required phrasing, only a fixed set of things a complete answer contains.

---

## B1. (instruction reliability)

Kuusiharju's warehouse team gets a short text message from a driver every time a load is dropped off. Write a single instruction you could hand an AI assistant so that, given any one of these messages, it always returns the same three-line log entry in the same order: drop-off time, pallet count, and any damage noted. Running your instruction twice on the same message must produce the same three lines both times. State the instruction, then explain in one sentence what part of it forces that repeat-consistency.

## B2. (instruction reliability)

Write an instruction for turning a week's worth of call-log entries (time, customer, topic, outcome) into a standard follow-up-call list. Two different colleagues, given the same week's entries and your instruction, should produce lists with the same structure and the same count of calls needing follow-up — even though the wording may differ.

## B3. (error spotting)

An AI assistant drafted this internal note:

"Site visit logged for the 22nd. The client's site contact confirmed access from 8am, and our crew of four will need roughly six hours on site, finishing by early afternoon on the 23rd."

Find the planted error, state exactly where it sits in the text, and say what you would check to confirm it before the note is filed.

## B4. (error spotting)

An AI assistant drafted this section of a monthly finance note:

"Invoices issued this month: 118, compared with 96 last month (a 20% increase). Of these, 9 were paid late, giving an on-time rate of 92%. Outstanding balance across the two regions held steady at €58,000, split evenly at €29,000 each."

Find both planted errors, state exactly where each sits, and say what you would check to confirm each before the note is sent up.

## B5. (checkability judgment)

Two AI outputs answer the same question, "what percentage of support tickets closed within SLA last quarter?":

Output 1: "88% of tickets closed within SLA."
Output 2: "There were 940 tickets last quarter and 827 closed within SLA, so 827 / 940 = 88% closed within SLA."

Which output would you sign off, and why? What exactly makes the other one harder to check?

## B6. (checkability judgment)

Two draft supplier-negotiation emails opening a price discussion:

Email 1 (confident): "Given current volumes, we'd expect a better rate than this — please revise your offer."
Email 2 (hedged): "Our order volume with you rose from 1,200 to 1,650 units over the last two quarters (ref. our PO log); at that volume we'd expect the tier-2 rate rather than tier-1 — could you revise the offer accordingly?"

Which would you send without further checking, and what would you check on the other one first?

## B7. (data handling policy)

You want an AI chat tool's help summarising a vendor quote. Kuusiharju has not vetted this particular tool for data handling. For each item below, say yes or no to pasting it in, with one line of reasoning:
1. The vendor's line-item pricing from the quote
2. This month's total procurement spend (aggregate, no vendor detail)
3. An unsigned draft of next year's budget
4. A datasheet already published on the vendor's own website
5. An employee's home address, copied from an HR record

## B8. (data handling policy)

A client's signed service agreement needs summarising for an internal memo, and you want an AI tool's help drafting the summary. The agreement includes: the client's company name and billing contact, the agreed hourly rates and retainer cap, a non-disclosure clause naming both parties, and the service scope. Decide what you would paste in as-is, what you would redact first, and why.

## B9. (verification habit)

You now generate the monthly stock-reconciliation summary with AI assistance. Describe the specific check you would build into that process — not "I'd read it over" but a named, repeatable step — and say exactly where in the monthly workflow it sits.

## B10. (verification habit)

Here is a multi-step AI-assisted workflow for processing incoming supplier invoices: (1) AI reads the incoming invoice PDF and extracts the line items and totals; (2) AI matches the invoice against the original purchase order; (3) AI drafts a payment approval note; (4) the note is submitted automatically if the match is within tolerance. Identify the step most in need of a verification gate, and specify exactly what the gate should check.
