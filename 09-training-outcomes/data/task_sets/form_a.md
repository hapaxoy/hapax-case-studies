# Kuusiharju Oy — AI-Augmented Workflows — Assessment Form A

This form is one half of a matched pair (Form A / Form B) used before and after the two-day AI-Augmented Workflows programme. Each learner sits one form before training and the other after, so that no one answers the identical questions twice. There are 10 tasks. Work through them in order; there is no trick in the ordering. Answer in your own words — there is no single required phrasing, only a fixed set of things a complete answer contains.

---

## A1. (instruction reliability)

Kuusiharju's site-supply team gets a short email from a supplier every time a delivery is confirmed. Write a single instruction you could hand an AI assistant so that, given any one of these emails, it always returns the same three-line summary in the same order: delivery date, item and quantity, and any change from the original order. Running your instruction twice on the same email must produce the same three lines both times. State the instruction, then explain in one sentence what part of it forces that repeat-consistency.

## A2. (instruction reliability)

Write an instruction for turning a week's worth of expense-claim lines (date, amount, category, submitter) into a standard approval memo. Two different colleagues, given the same week's claims and your instruction, should produce memos with the same structure and the same total — even though the wording may differ.

## A3. (error spotting)

An AI assistant drafted this email to a client:

"Thanks for your patience. Following our call on the 14th, we can confirm the revised delivery date of the 19th, three days out from today. The unit price stays at €48.50 as quoted, for a total of €4,850 on the 100-unit order."

Find the planted error, state exactly where it sits in the text, and say what you would check to confirm it before the email goes out.

## A4. (error spotting)

An AI assistant drafted this section of a weekly ops report:

"Deliveries this week: 62, up from 54 last week (a 15% increase). Of these, 3 were late, giving an on-time rate of 97%. Stock of the fast-moving items held steady at 340 units across the two depots, 170 at each."

Find both planted errors, state exactly where each sits, and say what you would check to confirm each before the report is sent up.

## A5. (checkability judgment)

Two AI outputs answer the same question, "what were Q2 returns as a percentage of Q2 sales?":

Output 1: "Q2 returns ran at 4.1% of sales."
Output 2: "Q2 sales were €612,000 and returns were €25,100, so returns were 25,100 / 612,000 = 4.1% of sales."

Which output would you sign off, and why? What exactly makes the other one harder to check?

## A6. (checkability judgment)

Two draft customer-service replies to a complaint about a late delivery:

Reply 1 (confident): "We're very sorry — this was entirely our error and it won't happen again. We've applied a 10% credit to your account."
Reply 2 (hedged): "Thanks for flagging this. Our records show the order (ref. 4471) was dispatched two days after the confirmed date; we've applied a 10% credit (ref. CR-1182) to your account and are checking with the depot on the cause."

Which would you send without further checking, and what would you check on the other one first?

## A7. (data handling policy)

You want an AI chat tool's help drafting a customer update. Kuusiharju has not vetted this particular tool for data handling. For each item below, say yes or no to pasting it in, with one line of reasoning:
1. The customer's delivery address
2. This week's total sales figure (aggregate, no customer detail)
3. Next quarter's unreleased pricing plan
4. A product spec sheet already published on the company website
5. A colleague's personal mobile number, copied from an email signature

## A8. (data handling policy)

A supplier contract needs summarising for an internal memo, and you want an AI tool's help drafting the summary. The contract includes: the supplier's company registration details, the agreed unit pricing and volume discounts, a confidentiality clause naming both parties, and the delivery schedule. Decide what you would paste in as-is, what you would redact first, and why.

## A9. (verification habit)

You now generate the weekly ops report with AI assistance. Describe the specific check you would build into that process — not "I'd read it over" but a named, repeatable step — and say exactly where in the weekly workflow it sits.

## A10. (verification habit)

Here is a multi-step AI-assisted workflow for processing incoming customer orders: (1) AI reads the incoming order email and extracts the item list and quantities; (2) AI checks stock availability against the warehouse system; (3) AI drafts a confirmation email with a delivery estimate; (4) the confirmation is sent automatically if stock is available. Identify the step most in need of a verification gate, and specify exactly what the gate should check.
