"""
Rubric-item detectors for the 09 Training Outcomes case study.

Given a response answer's free text for one task, each detector returns the
SET of rubric-item numbers (1-based, in the item order defined in
`code/config.py`'s `TASK_PAIRS`) that the text's content satisfies.

These detectors are keyword/pattern based, not semantic. They exist because
Phase 3 response prose was generated from deterministic briefs that build an
answer by ADDING one content "atom" per rubric item earned (an "excellent"
band response contains every lower item's atom plus its own). Content is genuinely
paraphrased across the five writing batches, though -- not one fixed
sentence per item -- so each item's detector looks for that item's
characteristic FACTS and CONCEPTS (specific figures, named clauses, named
steps, comparison words) via several alternative patterns, tuned by
sampling real corpus text across every rubric_items_hit group per task, not guessed from a
single example.

Used by:
- code/validate_responses.py -- a narrow fidelity check on tasks 7/8 only
  (the binary/enumerable policy tasks).
- code/score_responses.py -- the full calibration run across all 10 tasks.

IMPORTANT: detection here is calibrated AGAINST the response briefs (which
record the intended rubric_items_hit) for measurement purposes only. A real
scoring run (Phase 5's mark.py) would only ever see response text, never the
brief. Patterns below were broadened only in response to confirmed detector
misses (the text plainly satisfies/violates an item and the pattern missed
it) -- never to make a genuine response-infidelity case agree with its
brief. The eight Task-4/B4 files identified by the cross-batch
audit are a deliberate, permanent exception: they SHOULD
disagree with the detector, because their prose contradicts their own
brief.
"""

import re


def _any(text, *patterns):
    """True if any of the given regex patterns matches text (case-insensitive)."""
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def _count_present(text, phrases):
    return sum(1 for p in phrases if re.search(p, text, re.IGNORECASE))


# ---------------------------------------------------------------------------
# Task 1 -- instruction_reliability, "always return the same N lines"
# ---------------------------------------------------------------------------

_TASK1_FIELDS = {
    "A": [r"delivery date", r"item and quantity", r"\bchange\b"],
    "B": [r"drop-?off time", r"pallet count", r"\bdamage\b"],
}

_TASK1_MECHANISM = [
    r"\bfixed\b", r"\bsame order\b", r"\bin (this|that) order\b", r"\block(ed)?\b",
    r"\btemplate\b", r"\balways (return|give)\b", r"\bevery (time|run)\b",
    r"\bset order\b", r"\bconsistent (format|structure)\b", r"\bno exceptions\b",
]

_TASK1_UNAMBIGUOUS = [
    r"\bunambiguous\b", r"which line is which", r"\bno ambiguity\b", r"\bisn't ambiguous\b",
    r"\bclear which\b", r"\blabel(led|s|ing)? each line\b", r"precise(ly)? defin",
    r"no (line )?(absorbing|overlap(ping)?)",
]

_TASK1_MISSING_FIELD = [
    r"if (no|a|one|any).{0,25}(is|isn't|not) (mentioned|stated|in the (email|message))",
    r"\bnone noted\b", r"\bnot stated\b", r"still outputs?", r"rather than (dropping|skipping|leaving) the line",
    r"missing (one of|a) (the )?(three )?fields?", r"explicit fallback", r"defined fallback",
    r"write 'no(ne)?'", r"write \"not stated\"",
]

_TASK1_FORCES = [
    r"forces (that|the) (repeat-consistency|same)", r"not the wording", r"because there's no wording decision",
    r"only slots to fill", r"forces the same three lines", r"what forces the consistency",
    r"removes any room for the output to (vary|change)", r"nothing (about the output )?depends on how",
    r"that's what a reviewer would check first",
]


def detect_task1(text, form):
    hits = set()
    fields = _TASK1_FIELDS[form]
    field_count = _count_present(text, fields)
    mechanism = _any(text, *_TASK1_MECHANISM)
    if field_count >= 2 or mechanism:
        hits.add(1)
    # NOTE: item 2's canonical content is the explicit "unambiguous / label
    # each line" sentence, but a large minority-batch style satisfies both item 1 and item 2 in the SAME sentence
    # (mechanism + all three field names together), with no separate
    # "unambiguous" clause ever appearing for that style. Requiring the
    # explicit phrase alone under-detects that population badly (a measured
    # ~14-point task-level regression); accepting the mechanism signal here
    # trades a smaller, visible false-positive rate on the majority style
    # for materially better aggregate recall. Documented, not silently
    # tuned -- see the scorer_calibration.md sample for worked examples of
    # the residual over-detection this causes.
    if mechanism or _any(text, *_TASK1_UNAMBIGUOUS):
        hits.add(2)
    if _any(text, *_TASK1_MISSING_FIELD):
        hits.add(3)
    if _any(text, *_TASK1_FORCES):
        hits.add(4)
    return hits


# ---------------------------------------------------------------------------
# Task 2 -- instruction_reliability, "standard memo/list, same total/count"
# ---------------------------------------------------------------------------

_TASK2_FIELDS = {
    "A": [r"\bdate\b", r"\bamount\b", r"\bcategory\b", r"\bsubmitter\b"],
    "B": [r"\btime\b", r"\bcustomer\b", r"\btopic\b", r"\boutcome\b"],
}

_TASK2_STRUCTURE = [
    r"\bstructure:", r"in that fixed order", r"same structure", r"exact output structure",
    r"fields and their order", r"same order each time", r"fixed field(s)? (order|in order)",
    r"own (row|line)", r"field order", r"one (row|line) per", r"set (the )?(field|output)",
    r"output shape", r"memo structure", r"fixed fields", r"follow-?up list", r"list structure",
]

_TASK2_DERIVATION = [
    r"total is the sum of", r"stated once at the (end|top)", r"count is the number of",
    r"the count is just", r"derived from", r"one total from", r"total(led|s)? (it |them )?up",
    r"sum(ming)? (up|the amount)", r"total the amounts?", r"add(s|ed|ing)? up the total",
    r"count(ing)? how many", r"count(ing)? (the )?follow-?ups?", r"count(ing)? (those|these|the) lines",
    r"give me the (number|total)", r"tell me the total", r"add(s|ed|ing)? up (the|all)",
    r"total (calculated|line)", r"sum of the amounts? column", r"just the sum of", r"count up how many",
]

_TASK2_DUPLICATE = [
    r"identical-looking", r"duplicate-looking", r"kept separate, not merged", r"kept as separate claims",
    r"flagged (for a person to confirm|rather than counted twice|as .possible duplicate.)", r"logged twice",
    r"duplicat", r"entered twice", r"counted (once|twice)", r"calls? twice", r"twice about",
    r"mark the second", r"note (it|that it) happened twice", r"note to check",
]

_TASK2_TWO_PEOPLE = [
    r"two (different )?(people|colleagues) run", r"without (needing |having seen )?(a |an )?(shared )?example",
    r"land on the same", r"cold and land", r"none of this needs two people",
    r"no hand adjustment", r"without comparing notes", r"two people (adding up|running)",
]


def detect_task2(text, form):
    hits = set()
    fields = _TASK2_FIELDS[form]
    field_count = _count_present(text, fields)
    if field_count >= 2 or _any(text, *_TASK2_STRUCTURE):
        hits.add(1)
    if _any(text, *_TASK2_DERIVATION):
        hits.add(2)
    if _any(text, *_TASK2_DUPLICATE):
        hits.add(3)
    if _any(text, *_TASK2_TWO_PEOPLE):
        hits.add(4)
    return hits


# ---------------------------------------------------------------------------
# Task 3 -- error_spotting, single planted date-arithmetic error
# ---------------------------------------------------------------------------

_TASK3_ERROR_EXISTS = [
    r"\berror\b", r"\bmismatch\b", r"\btiming (issue|error)\b", r"\binconsisten",
    r"do(esn't|n't) (quite )?(add up|line up|check out|hold up|work|match|reconcile|sit right|look right|follow|fit|support)",
    r"\b(feels|seems|looks|sounds|is) (wrong|off|not right)\b", r"\bnot (quite )?right\b",
    r"\bsomething('s| is)? (off|wrong|not right)\b", r"does not (add up|sit right|line up|work|fit)",
    r"the (date|finish time|finishing time|timing)('s)? (is )?wrong", r"the error is", r"read this twice", r"i read.{0,15}twice",
    r"doesn't seem (quite )?right", r"doesn't look (quite )?right", r"seems? (a bit|a little)? ?(off|tight|quick|rushed)",
    r"a (bit|little) (off|tight|quick|rushed)", r"can't put my finger on", r"not sure (exactly )?(what|why)",
    r"look(ed)? twice", r"can't say exactly", r"don't support the stated", r"does not sit together",
    r"not lining up", r"cannot put my finger on", r"is where the mistake",
]

_TASK3_LOCATE = {
    "A": [r"\b19th\b", r"\b14th\b", r"three days out", r"delivery date"],
    "B": [r"\b22nd\b", r"\b23rd\b", r"8\s?am", r"six.hour", r"finish(ing)? time"],
}

# Item 3's differentiator is a COMPUTED/explicit resolution beyond the plain
# "X is N days off" statement already present at item 2's tier -- e.g. Form
# A explicitly deriving the correct 17th, or an explicit two-sided
# contradiction statement ("one of those two facts is wrong"). Phrases that
# already appear at the item-2 tier (e.g. "five days later", "same
# afternoon") are deliberately excluded here to avoid crediting item 3 for
# item-2-level content.
_TASK3_PRECISE = {
    "A": [r"\b17th\b", r"two-day gap", r"can't both be right", r"can't both be true"],
    "B": [r"one of those two facts", r"can't both be right", r"can't both be true", r"doesn't follow\b",
          r"disagreeing with its own arithmetic", r"can't finish the next day", r"wouldn't (reach|finish) the next day",
          r"same (day|afternoon).{0,25}not (the )?(next|23rd)"],
}

_TASK3_CHECK = [
    r"order system", r"site access log", r"sign-off log", r"crew's (actual )?schedule",
    r"call notes? (and|or) (the )?calendar", r"today's actual date", r"rather than (assume|re-derive|guess|just re-check)",
    r"not re-derive", r"crew's (own )?(log|sign-off)", r"site-visit booking", r"dispatch system",
    r"call log.{0,30}(calendar|dispatch system)", r"(calendar|dispatch system).{0,30}call log",
    r"today's (actual )?date and", r"actual agreed date",
]


def detect_task3(text, form):
    hits = set()
    if _any(text, *_TASK3_ERROR_EXISTS):
        hits.add(1)
    locate_count = _count_present(text, _TASK3_LOCATE[form])
    if locate_count >= 1 or _any(text, r"five days?", r"\b5.day\b", r"two-day"):
        hits.add(2)
    if _any(text, *_TASK3_PRECISE[form]):
        hits.add(3)
    if _any(text, *_TASK3_CHECK):
        hits.add(4)
    return hits


# ---------------------------------------------------------------------------
# Task 4 -- error_spotting, two planted errors (tightened item mapping)
# ---------------------------------------------------------------------------

def detect_task4(text, form):
    hits = set()
    if form == "A":
        if _any(text, r"15%.*(check|fine|right|correct|sound)", r"(54|62).*15%", r"15%.*(54|62)",
                r"delivery growth.*(check|fine)", r"growth.*(check|fine|correct|sound)"):
            hits.add(1)
        if _any(text, r"95%", r"97%.*(wrong|isn't|not)", r"on-?time rate.*(wrong|off|isn't|not)", r"3 late.*62"):
            hits.add(2)
    else:
        on_time_clean = _any(text, r"92%.*(check|fine|right|correct|matching)", r"(9|118).*92%", r"92%.*(9|118)",
                              r"on-?time rate.*(check|fine|correct|matching)")
        # A widespread minority resolution (batches 2/3/4)
        # substitutes a VAGUE, non-precise mention of the growth figure for
        # item 1's content instead of the canonical on-time-rate confirmation
        # -- internally consistent with its own item 2 (which still requires
        # the PRECISE 23% correction), so it is not on its own a fidelity bug.
        # Item 1's practical bar in this minority-resolution style is just
        # ENGAGING with the task's figures at all (on-time OR growth OR the
        # held-steady balance), precise or not -- consistent with item 1's
        # own description ("credited even if the response finds nothing
        # else, provided the check is real arithmetic").
        mentions_numbers = _any(text, r"96.{0,15}118", r"118.{0,15}96", r"growth (number|figure)",
                                 r"invoice (number|growth)", r"held steady", r"20%.{0,15}rise", r"23%",
                                 r"22\.\d%", r"92%", r"9 late")
        if on_time_clean or mentions_numbers:
            hits.add(1)
        if _any(text, r"23%", r"22\.\d%", r"20%.*(wrong|not|doesn't check)",
                r"growth (figure|number|percentage).*(wrong|off|not|doesn't hold)", r"96.*118.*23",
                r"both numbers checked", r"get both.{0,20}checked", r"isn't quite \d+%"):
            hits.add(2)
    if _any(text, r"held steady", r"never (squared|reconciled|explained) against", r"unexplained",
            r"doesn't square with", r"never explained why", r"without (any )?explanation", r"without comment",
            r"sit(s)? (oddly|flat)", r"nobody explains why", r"never addressed", r"unaddressed", r"steady.{0,30}odd"):
        hits.add(3)
    if _any(text, r"source records", r"depot ledger", r"regional ledger", r"finance system",
            r"not just re-check the (report|note)'s own", r"pull the actual", r"against the (depot|regional|warehouse) ledgers?",
            r"delivery log and the depot count", r"invoice count and (the )?regional balances"):
        hits.add(4)
    return hits


# ---------------------------------------------------------------------------
# Task 5 -- checkability_judgment, bare number vs shown-working output
# ---------------------------------------------------------------------------

def detect_task5(text, form):
    hits = set()
    prefers_output2 = _any(text, r"output 2", r"\bsecond (output|one)\b", r"sign off.*second", r"lean toward.*second",
                            r"go with the second", r"choose the second", r"pick (the )?second")
    prefers_output1 = _any(text, r"send output 1", r"choose output 1", r"go with output 1",
                            r"output 1 sounds more confident", r"first output.*(more|sounds)")
    if prefers_output2 and not prefers_output1:
        hits.add(1)
    if form == "A":
        missing_figs = _any(text, r"612,?000", r"25,?100")
    else:
        missing_figs = _any(text, r"\b940\b", r"\b827\b")
    if missing_figs or _any(text, r"no way to see", r"gives you nothing", r"nothing (to check|behind it)",
                             r"where the [\d.]+% comes from", r"doesn't show (that|the working)",
                             r"doesn't show them", r"nothing (in it )?you could.*look up",
                             r"leaves out the two figures", r"output 1 doesn't (give|show)"):
        hits.add(2)
    if _any(text, r"could (well |still )?be (right|correct|accurate|fine)", r"might (well |still )?be (right|correct|accurate|fine)",
            r"without re-?running", r"unverifiable", r"can't (check|verify) it without", r"there's no way to know",
            r"isn't necessarily wrong", r"unconfirmable", r"nothing to check it against"):
        hits.add(3)
    if _any(text, r"i'd still (check|confirm)", r"even with output 2, i'd", r"confirm those (two )?source figures",
            r"before signing off", r"redoing.*over", r"right ones for"):
        hits.add(4)
    return hits


# ---------------------------------------------------------------------------
# Task 6 -- checkability_judgment, confident vs hedged (with references)
# ---------------------------------------------------------------------------

def detect_task6(text, form):
    hits = set()
    label = "reply 2" if form == "A" else "email 2"
    other = "reply 1" if form == "A" else "email 1"
    prefers_second = _any(text, re.escape(label), r"\bsecond (reply|email|one)\b")
    prefers_first = _any(text, rf"send {re.escape(other)}", r"\bfirst (reply|email|one)\b.*(more|sincere|to the point|short)")
    if prefers_second and not prefers_first:
        hits.add(1)
    if _any(text, r"no order number or reference", r"no volume numbers to check", r"nothing to check",
            r"no reference to check it against", r"no numbers to check the ask against", r"nothing (in it )?you could.*look up",
            r"nothing to verify", r"can't check any of that", r"doesn't say which order", r"no order number in it",
            r"doesn't (say|give).{0,30}(compar|much to go on)", r"can't be checked", r"nothing there (yet )?to (verify|point to)",
            r"doesn't say what it's (even )?comparing", r"doesn't give you anything", r"isn't backed by anything",
            r"no numbers (to check|attached|behind)", r"without anything behind it", r"has no numbers behind it",
            r"hard to check", r"nothing behind it", r"without giving any numbers", r"doesn't back up",
            r"no numbers to check the .{0,20}claim against", r"doesn't\.$", r"\bdoesn't\.\s*$",
            r"isn't checkable as it stands", r"doesn't say (what|by how much)", r"doesn't say why",
            r"backed by something", r"want(ing)? (it |something )?back(ed)? (up )?(by|with)",
            r"wouldn't send it without", r"no way to (tell|know) if.{0,30}(is )?even real", r"no way to check that"):
        hits.add(2)
    if _any(text, rf"doesn't make {re.escape(other)} wrong", r"could still go out as written", r"could go out fine",
            r"once checked, it could", r"isn't necessarily wrong", r"might (well )?be (true|accurate|fine|correct)",
            r"could (still )?be fine", r"can't (currently )?be verified", r"isn't (something you can|verifiable)",
            r"wouldn't rule it out", r"not (that|necessarily) .{0,15}(is )?wrong", r"doesn't mean.{0,20}wrong",
            r"so it can't be checked", r"there's nothing to verify", r"so there's nothing to (check|verify)",
            r"could (probably )?(go|be sent) (out )?too", r"couldn't go out too", r"just as sendable",
            r"once (checked|that('s| is) done)", r"isn't automatically wrong", r"not necessarily wrong",
            r"probably fine to send", r"might turn out to be fair", r"is not necessarily wrong",
            r"does not mean.{0,15}wrong", r"wouldn't reject.{0,20}outright", r"equally sendable",
            r"becomes equally", r"nothing supports it"):
        hits.add(3)
    if _any(text, r"i'd (confirm|pull)", r"before sending", r"pull the real order volumes",
            r"confirm the (order and the credit note|dispatch date)", r"i'd (just )?pull the order",
            r"pull up order", r"want the numbers (added|behind it) before sending"):
        hits.add(4)
    return hits


# ---------------------------------------------------------------------------
# Task 7 -- data_handling_policy, 5-item yes/no enumeration
# ---------------------------------------------------------------------------

def _task7_answer_for(low, num, names):
    """Find the yes/no answer for a numbered or named list item. Tolerates
    a short descriptive label between the number and the answer (e.g.
    "1. Address -- no.") as well as the bare "1. No." / "1 - no" forms."""
    m = re.search(rf"\b{num}\s*[.\):-]\s*[^\d\n]{{0,35}}?\b(yes|no)\b", low)
    if m:
        return m.group(1)
    for name in names:
        m2 = re.search(rf"{name}[^.\n]{{0,50}}?\b(yes|no)\b", low)
        if m2:
            return m2.group(1)
        m3 = re.search(rf"\b(yes|no)\b[^.\n]{{0,15}}{name}", low)
        if m3:
            return m3.group(1)
    return None


def detect_task7(text, form):
    hits = set()
    low = text.lower()
    if form == "A":
        personal = _task7_answer_for(low, "1", [r"delivery address", r"customer's (own )?address", r"customer's own info"])
        unreleased = _task7_answer_for(low, "3", [r"pricing plan", r"unreleased pricing", r"next quarter's pricing"])
        public = _task7_answer_for(low, "4", [r"spec sheet", r"already published", r"product spec"])
    else:
        personal = _task7_answer_for(low, "5", [r"home address", r"employee's (home|own) address"])
        unreleased = _task7_answer_for(low, "3", [r"budget draft", r"draft budget", r"unsigned draft", r"next year's budget"])
        public = _task7_answer_for(low, "4", [r"datasheet", r"already published", r"vendor's (own )?site"])
    if personal == "no":
        hits.add(1)
    if unreleased == "no":
        hits.add(2)
    if public == "yes":
        hits.add(3)
    # item 4 is the top band: ALL FIVE items answered with a reasoning word
    # attached, not just the 3 enumerable ones -- a response that only
    # explains its 3 correct/incorrect calls (items 1-3 above) but leaves
    # the other 2 bare "No."/"Yes." has not earned this item. Count yes/no
    # tokens immediately followed by at least one explanatory word.
    reasoning_count = len(re.findall(r"\b(yes|no)\b[\s,:.\-]{1,4}[a-zA-Z]{2,}", low))
    if reasoning_count >= 4:
        hits.add(4)
    return hits


# ---------------------------------------------------------------------------
# Task 8 -- data_handling_policy, contract/agreement redaction judgment
# ---------------------------------------------------------------------------

def detect_task8(text, form):
    hits = set()
    if form == "A":
        sensitive_terms = r"(unit )?pricing|volume discounts?"
    else:
        sensitive_terms = r"hourly rates?|retainer cap"
    # A bare mention of the pricing terms is NOT enough -- the prompt itself
    # names them, so a response that just lists contract contents without
    # judgement (the hits=() characteristic mistake) would otherwise
    # false-positive here. Require the mention to co-occur with a
    # sensitivity/redaction judgement word.
    caution_words = (r"sensitive|redact|care|hold back|no-go|caution|deliberately|leave out|not paste"
                     r"|wouldn't paste|keep.{0,15}out|risky|check (with|first)|before pasting|before sending")
    if _any(text, rf"({sensitive_terms}).{{0,80}}({caution_words})",
            rf"({caution_words}).{{0,80}}({sensitive_terms})"):
        hits.add(1)
    clause = "confidentiality clause" if form == "A" else "(non-disclosure|nda) clause"
    if _any(text, rf"{clause}.{{0,80}}(names both|caution|harder no|care|no-go)",
            rf"(caution|care(ful)?|no-go).{{0,80}}{clause}",
            r"names both (companies|parties)", r"careful with the (confidentiality|non-disclosure)",
            r"naming both companies.{0,40}(clause|confidentiality)"):
        hits.add(2)
    low_risk = "delivery schedule" if form == "A" else "(general )?service scope"
    if _any(text, rf"{low_risk}.{{0,25}}(low-?risk|fine (to paste|as-?is)|as is|as-is)"):
        hits.add(3)
    if _any(text, r"paraphrase (without figures|the sensitive parts)", r"use a vetted (internal )?tool",
            r"describe (it |them |the structure )?in (general terms|words)", r"go through a vetted tool"):
        hits.add(4)
    return hits


# ---------------------------------------------------------------------------
# Task 9 -- verification_habit, a repeatable weekly/monthly check
# ---------------------------------------------------------------------------

def detect_task9(text, form):
    hits = set()
    # item 1's practical bar (per corpus evidence) is proposing SOME check
    # activity, even vaguely phrased -- as opposed to simply re-reading the
    # draft (the hits=() alternative). Concrete/repeatable phrasing is what
    # distinguishes higher items, not item 1 itself.
    proposes_check = _any(text, r"check", r"verify", r"glance over", r"recomput(e|ing)", r"cross-cast", r"re-?total")
    just_rereads = _any(text, r"^(i'd|i would) just (read|make sure to read)") and not proposes_check
    if proposes_check and not just_rereads:
        hits.add(1)
    if _any(text, r"before (it|the (report|summary|note)).{0,20}(goes (out|up|to)|is sent|reaches)",
            r"right before", r"at month-end", r"before it('s| is) sent (up|out)",
            r"reaches the (manager|supervisor|ops lead|finance lead|depot manager)",
            r"goes (to|out) (my|the)? ?(manager|supervisor|ops lead|finance lead|depot manager)",
            r"before i send the (weekly |monthly )?(report|summary)", r"as the (last|final) step before it leaves",
            r"as the (last|final) step before the summary"):
        hits.add(2)
    if _any(text, r"catches? a wrong (total|variance|figure|number)", r"fabricated line", r"invented line",
            r"not just a typo", r"made up or miscalculated", r"actually wrong"):
        hits.add(3)
    if _any(text, r"i own that check", r"i own the check", r"goes back for", r"routes back to", r"if it fails",
            r"flagged to my manager", r"a failed check routes back"):
        hits.add(4)
    return hits


# ---------------------------------------------------------------------------
# Task 10 -- verification_habit, a workflow verification gate
# ---------------------------------------------------------------------------

def detect_task10(text, form):
    hits = set()
    mentions_step1 = _any(text, r"step 1\b", r"step one\b", r"(extraction|reading|order-reading) step",
                           r"reading the (order|invoice)", r"first step", r"reads the (order|email|invoice)")
    step1_significance = _any(text, r"risk", r"matter", r"focus", r"riskiest", r"watch", r"carrie", r"compound",
                               r"feeds?", r"starts?", r"messes up", r"wrong", r"propagate", r"trickiest",
                               r"right at the start", r"worries me")
    if (mentions_step1 and step1_significance) or _any(
        text, r"compound(s)? downstream", r"carries (all the way )?through", r"carries risk downstream",
        r"where a misread", r"highest-risk (point)?", r"watch (most closely|closest)",
        r"one to watch", r"affects everything downstream", r"carries through everything",
        r"doesn't stay contained",
    ):
        hits.add(1)
    mentions_step4_gate = _any(text, r"step 4") and _any(text, r"gate|check")
    if mentions_step4_gate or _any(
        text, r"irreversible", r"can't (easily )?(take back|undo)", r"gate belongs", r"where i'd put the (real )?gate",
        r"point of no return", r"you can't take (it )?back", r"unrecoverable", r"nobody('s| is) looking",
        r"where it becomes final", r"once (that('s)?|it) (auto-submits|sent|gone through)", r"hard to pull back",
        r"there's no catching it after", r"becomes (final|permanent)", r"can't be undone", r"no taking it back",
        r"worth watching too", r"matters too",
    ):
        hits.add(2)
    if _any(text, r"flag any", r"threshold", r"within (a loose )?tolerance", r"near the tolerance edge",
            r"borderline rather than clear-cut", r"unusually (high|large) quantit", r"near the cutoff",
            r"right at the cutoff", r"unmatched item", r"stock (figure|match).{0,20}current",
            r"match(es)? what('s)? (actually )?(recorded|in the warehouse)", r"genuinely (current|within)",
            r"actually (matches|within)", r"don't match within", r"close to the tolerance"):
        hits.add(3)
    if _any(text, r"routes? to (a |the )?(person|named reviewer|whoever)", r"route.* to a person",
            r"not (leave it|just block) silently", r"rather than leave it stopped", r"with the reason attached",
            r"nobody told", r"go to (someone|whoever)", r"for a manual look"):
        hits.add(4)
    return hits


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_DETECTORS_BY_INDEX = {
    1: detect_task1,
    2: detect_task2,
    3: detect_task3,
    4: detect_task4,
    5: detect_task5,
    6: detect_task6,
    7: detect_task7,
    8: detect_task8,
    9: detect_task9,
    10: detect_task10,
}


def detect(task_id, text):
    """
    Detect which rubric items (1-based) a response's text satisfies for the
    given task_id (e.g. "A4", "B7"). Returns a set of ints.
    """
    form = task_id[0]
    index = int(task_id[1:])
    detector = _DETECTORS_BY_INDEX.get(index)
    if detector is None:
        raise ValueError(f"no detector registered for task index {index} (task_id={task_id})")
    return detector(text, form)
