"""
Configuration for the 09 Training Outcomes case study — Phase 2 (deterministic
structure).

Every tunable that controls the shape of the dataset lives in this file:
the random seed, the cohort archetype table, the Finnish learner-name pool
(collision-checked against the rest of the portfolio at import time), the
Kuusiharju Oy constants, and the task-set content for Forms A and B (the
published measurement instrument itself).

`code/generate_structure.py` reads this file and writes files; it does not
invent new parameters of its own. `code/validate_structure.py` re-derives
every coherence rule from the files on disk and checks them against the
values recorded here.

The comments below give the reasoning behind the numeric choices (the
ability-to-band mapping and the δ/confidence independence tolerance in
particular).
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# Everything is relative to this file's location, never to the caller's
# working directory.
CODE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CODE_DIR.parent
DATA_DIR = PROJECT_DIR / "data"

COHORT_DIR = DATA_DIR / "cohort"
TASK_SETS_DIR = DATA_DIR / "task_sets"
ANSWER_KEY_DIR = DATA_DIR / "answer_key"
RESPONSE_BRIEFS_DIR = DATA_DIR / "response_briefs"
INSTRUMENTS_DIR = DATA_DIR / "instruments"
ANALYSIS_DIR = DATA_DIR / "analysis"

# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------
RANDOM_SEED = 9  # fresh seed for this project, per portfolio convention

# ---------------------------------------------------------------------------
# The invented company and programme
# ---------------------------------------------------------------------------
COMPANY = {
    "name": "Kuusiharju Oy",
    "sector": "technical trade — building-materials wholesale and site logistics",
    "employees_total": 200,
    "city": "Jyväskylä",
    "cohort_size": 40,
    "programme_name": "AI-Augmented Workflows",
    "programme_length_days": 2,
    "programme_description": (
        "The training page's flagship one-day theme, run here as a two-day "
        "in-house programme for Kuusiharju Oy: everyone brings a task they "
        "do every week and rebuilds it with AI in the tools the organisation "
        "already has, with a full day given over to verification habits."
    ),
    # Occasion labels and their nominal offsets from the programme end date.
    # The +8-week occasion exists for every learner even though none of the
    # three named instruments uses it as sold — it exists
    # solely to make the fast-forgetter blind spot demonstrable in Phase 5.
    "occasions": ["pre", "post", "follow_up_8wk"],
    "occasion_offset_days": {"pre": -3, "post": 3, "follow_up_8wk": 59},
}

# ---------------------------------------------------------------------------
# Name-collision check
# ---------------------------------------------------------------------------
# Every fictional name used anywhere else in the portfolio, gathered by hand
# from: the eight fictional protagonist firms (02, 03, 05, 06, 07, 08 company
# names, plus 01 Churn's Koivu Oy / Koivu Ventures Oy), 07 Tenders' 14
# persona names, and 08 Inbox's customer register (person names only —
# business names are covered by the firms list). Checked once at import time
# (see `check_name_collisions` below) and again independently by
# `validate_structure.py`.
EXISTING_PORTFOLIO_FIRM_NAMES = {
    "Jalavakoski Konepaja Oy",   # 02 ERP Cleanup
    "Pyökkipaja Oy",             # 03 Invoices
    "Paju Consumer Products Oy", # 05 Board Reporting
    "Saarnitukku Oy",            # 06 Anomaly Detection
    "Visakoivu Oy",              # 07 Tenders
    "Haapaharju Oy",             # 08 Inbox
    "Koivu Oy",                  # 01 Churn roster
    "Koivu Ventures Oy",         # 01 Churn roster
}

EXISTING_PORTFOLIO_PERSON_NAMES = {
    # 07 Tenders — 14 personas
    "Mervi Aaltonen", "Jussi Karkkainen", "Sanna Peltola", "Timo Rautiainen",
    "Elina Vainio", "Antti Salomaa", "Riikka Hamalainen", "Pekka Ylonen",
    "Laura Mattinen", "Ville Korhonen", "Outi Leskinen", "Marko Salminen",
    "Johanna Niemela", "Heikki Toivanen",
    # 08 Inbox — customer register, person accounts only
    "Mikko Rantanen", "Sanna-Maria Kurtti", "Teemu Alatalo", "Riikka Hyry",
    "Jari Peltoniemi", "Anniina Similä", "Ville Junttila", "Laura Keränen",
    "Esko Väyrynen", "Minna Ojanperä",
}

# ---------------------------------------------------------------------------
# The 40-learner cohort — archetypes fixed before generation
# ---------------------------------------------------------------------------
# Every distribution below is a (mean, sd) pair for a normal draw, clipped
# to a sane range at generation time. Two independence rules the generator
# must honour (enforced by validate_structure.py):
#   1. confidence_delta_post is drawn from its OWN distribution per
#      archetype, never computed as a function of delta_post. The two are
#      correlated only through which archetype a learner belongs to — never
#      within an archetype. This is what makes the confident non-learner
#      and non-responder archetypes possible at all.
#   2. assessment_noise is drawn independently of both.
#
# Ability, delta and confidence all live on continuous scales:
#   - ability / delta: 0-1, where 1 is a flawless response on every rubric
#     item across the instrument (see "Ability-to-band mapping" below).
#   - confidence: 1-7 Likert-style continuous scale (self-report survey).
ARCHETYPES = {
    "strong_improver": {
        "label": "Genuine improver, strong",
        "n": 8,
        "baseline_ability": (0.35, 0.07),
        "delta_post": (0.32, 0.05),
        "retention_factor": (0.90, 0.05),   # fraction of delta kept at +8wk
        "confidence_baseline": (3.2, 0.6),
        "confidence_delta_post": (1.3, 0.3),
        "confidence_retention": (0.85, 0.08),
        "assessment_noise": (0.08, 0.02),
        "volunteering_propensity": (0.60, 0.12),
    },
    "modest_improver": {
        "label": "Genuine improver, modest",
        "n": 12,
        "baseline_ability": (0.45, 0.08),
        "delta_post": (0.13, 0.04),
        "retention_factor": (0.88, 0.06),
        "confidence_baseline": (3.4, 0.6),
        "confidence_delta_post": (0.7, 0.3),
        "confidence_retention": (0.80, 0.10),
        "assessment_noise": (0.09, 0.02),
        "volunteering_propensity": (0.42, 0.14),
    },
    "confident_non_learner": {
        "label": "Confident non-learner (the star)",
        "n": 7,
        "baseline_ability": (0.45, 0.08),
        "delta_post": (0.02, 0.02),          # ~= 0, the planted null
        "retention_factor": (0.85, 0.10),
        "confidence_baseline": (3.6, 0.6),
        "confidence_delta_post": (1.6, 0.3), # sharp rise despite delta ~= 0
        "confidence_retention": (0.90, 0.08),# and it STAYS up — the trap
        "assessment_noise": (0.09, 0.02),
        "volunteering_propensity": (0.75, 0.10),  # feedback-form gold
    },
    "non_responder": {
        "label": "Non-responder",
        "n": 7,
        "baseline_ability": (0.45, 0.08),
        "delta_post": (0.01, 0.02),           # ~= 0
        "retention_factor": (0.85, 0.10),
        "confidence_baseline": (3.3, 0.6),
        "confidence_delta_post": (0.1, 0.3),  # flat
        "confidence_retention": (0.80, 0.15),
        "assessment_noise": (0.11, 0.02),
        "volunteering_propensity": (0.18, 0.10),
    },
    "ceiling_case": {
        "label": "Ceiling case (already skilled)",
        "n": 3,
        "baseline_ability": (0.80, 0.06),     # high baseline
        "delta_post": (0.03, 0.02),           # ~= 0 by ceiling
        "retention_factor": (0.85, 0.10),
        "confidence_baseline": (5.5, 0.5),    # already confident too
        "confidence_delta_post": (0.2, 0.3),
        "confidence_retention": (0.85, 0.10),
        "assessment_noise": (0.05, 0.015),    # consistent expert
        "volunteering_propensity": (0.35, 0.14),
    },
    "fast_forgetter": {
        "label": "Fast forgetter",
        "n": 3,
        "baseline_ability": (0.40, 0.07),
        "delta_post": (0.28, 0.05),           # positive at post-test
        "retention_factor": (0.20, 0.08),     # THE designed decay by +8wk
        "confidence_baseline": (3.3, 0.6),
        "confidence_delta_post": (1.0, 0.3),
        "confidence_retention": (0.75, 0.10), # confidence decays SLOWER
        "assessment_noise": (0.09, 0.02),     # than ability — the real trap
        "volunteering_propensity": (0.45, 0.14),
    },
}
COHORT_SIZE = sum(a["n"] for a in ARCHETYPES.values())
assert COHORT_SIZE == 40, f"archetype counts must sum to 40, got {COHORT_SIZE}"

# ---------------------------------------------------------------------------
# Roles — finance / ops / sales / service-admin, evenly split 10/10/10/10,
# assigned independently of archetype (seeded shuffle in generate_structure)
# ---------------------------------------------------------------------------
ROLES = ["finance", "ops", "sales", "service_admin"]
ROLE_COUNT_PER_ROLE = COHORT_SIZE // len(ROLES)  # 10 each
assert ROLE_COUNT_PER_ROLE * len(ROLES) == COHORT_SIZE

# ---------------------------------------------------------------------------
# 40 Finnish learner names — collision-checked below at import time.
# Deliberately distinct first names AND surnames from every name in
# EXISTING_PORTFOLIO_PERSON_NAMES; common Finnish first names inevitably
# recur across a portfolio this size, so the check that matters is on the
# FULL name, not on name components in isolation.
# ---------------------------------------------------------------------------
LEARNER_NAMES = [
    "Anni Hakkarainen", "Joonas Virtanen", "Kirsi Lehtonen", "Mikael Koskinen",
    "Satu Manninen", "Petri Heikkinen", "Noora Järvinen", "Ari Kinnunen",
    "Tuula Laaksonen", "Sami Hyvärinen", "Marja Ahonen", "Juha Pesonen",
    "Elisa Kokkonen", "Tero Turunen", "Hanna Rissanen", "Vesa Kettunen",
    "Paula Lampinen", "Risto Väänänen", "Anne Kiviranta", "Olli Kuisma",
    "Sini Halonen", "Markus Hirvonen", "Tiina Räsänen", "Jarkko Nyholm",
    "Katri Vuorinen", "Esa Karjalainen", "Leena Multanen", "Hannu Seppä",
    "Riitta Ollikainen", "Kimmo Palo", "Merja Aalto", "Janne Wirén",
    "Päivi Sirola", "Toni Männistö", "Anu Räikkönen", "Mika Ryhänen",
    "Sirpa Kortesalmi", "Jouni Lassila", "Heli Pärnänen", "Kalle Ahtiainen",
]
assert len(LEARNER_NAMES) == 40
assert len(set(LEARNER_NAMES)) == 40, "learner names must be unique"


def check_name_collisions():
    """
    Verify none of this project's fictional names collide with a name
    already used elsewhere in the portfolio. Raises AssertionError with an
    informative message on any collision. Called by generate_structure.py
    at the start of a run and independently re-run by validate_structure.py.
    """
    collisions = []

    if COMPANY["name"] in EXISTING_PORTFOLIO_FIRM_NAMES:
        collisions.append(f"company name collides: {COMPANY['name']}")

    for name in LEARNER_NAMES:
        if name in EXISTING_PORTFOLIO_PERSON_NAMES:
            collisions.append(f"learner name collides: {name}")
        if name in EXISTING_PORTFOLIO_FIRM_NAMES:
            collisions.append(f"learner name collides with a firm name: {name}")

    if collisions:
        raise AssertionError(
            "Name collision(s) against the existing portfolio:\n  "
            + "\n  ".join(collisions)
        )
    return True


# ---------------------------------------------------------------------------
# Ability-to-rubric-band mapping (the load-bearing generation rule)
# ---------------------------------------------------------------------------
# A learner's EFFECTIVE ABILITY on a given (task, occasion) is:
#     effective_ability = clip(occasion_ability + practice_bonus + noise, 0, 1)
# where occasion_ability is the learner's ability at that occasion (baseline,
# baseline+delta, or baseline+delta*retention — see generate_structure.py),
# practice_bonus applies only when the SAME form is being re-administered
# (the naive arm's practice effect, see PRACTICE_EFFECT_BONUS below), and
# noise is a fresh N(0, assessment_noise) draw per (learner, form, occasion).
#
# Each task's rubric is a list of items, each carrying an item_difficulty in
# [0, 1]. A response at a given effective_ability is scored deterministically
# by a THRESHOLD RULE: the learner earns a rubric item if and only if
# item_difficulty <= effective_ability. Item difficulties within a task are
# spread across the full 0-1 range, so a learner's raw fraction of items
# earned tracks their effective_ability directly and a fixed set of bands
# can be read off the same scale that produced it. This is the single
# mapping every downstream artefact (response briefs, and later mark.py)
# must agree on — it lives here, once, not re-derived anywhere else.
#
# The four QUALITY BANDS a response is written to (Phase 3 prose target):
RUBRIC_BANDS = [
    # (band_id, label, lower_bound_inclusive, upper_bound_exclusive, characteristic mistake bank)
    ("minimal", "Minimal", 0.00, 0.35, [
        "does not attempt the harder half of the task",
        "answers a different, easier question than the one asked",
        "misses the instruction's edge case entirely",
    ]),
    ("partial", "Partial", 0.35, 0.60, [
        "gets the main point but skips the verification step",
        "catches the obvious planted error but misses a subtler second one",
        "picks a defensible answer without stating why it is checkable",
    ]),
    ("solid", "Solid", 0.60, 0.85, [
        "complete and correct, but the explanation is thinner than the answer",
        "handles the edge case but does not name the general rule behind it",
    ]),
    ("excellent", "Excellent", 0.85, 1.01, [
        "complete, correct, and explains the reasoning a reviewer would check first",
    ]),
]


def ability_to_band(effective_ability: float) -> str:
    """Deterministic threshold mapping from an effective-ability score to a
    rubric band id. Single source of truth for both generate_structure.py
    (writing response briefs) and validate_structure.py (checking them)."""
    for band_id, _label, lower, upper, _mistakes in RUBRIC_BANDS:
        if lower <= effective_ability < upper:
            return band_id
    raise ValueError(f"effective_ability {effective_ability} outside [0, 1]")


# ---------------------------------------------------------------------------
# Practice effect (naive arm's flaw #2) — small familiarity bonus applied
# whenever a learner sees the SAME form at a later occasion than their first
# exposure to it. This is what makes the naive arm's "same form pre and
# post" design overstate the cohort effect: part of the observed gain is
# just familiarity with the instrument, not the training.
# ---------------------------------------------------------------------------
PRACTICE_EFFECT_BONUS = 0.07  # flat addition to effective_ability, pre-clip

# ---------------------------------------------------------------------------
# δ/confidence independence — validation tolerance
# ---------------------------------------------------------------------------
# The design's load-bearing claim is that confidence trajectories are drawn
# independently of delta WITHIN each archetype. Across the full cohort some
# positive correlation is expected anyway, because two archetypes (strong
# and modest improvers) have both high delta and high confidence-delta by
# construction — that is a real, honest pattern, not a bug. What must NOT
# happen is near-perfect tracking (which would silently defeat the
# confident-non-learner and non-responder archetypes' purpose). The band
# below is the documented target.
DELTA_CONFIDENCE_CORRELATION_TARGET = (0.20, 0.65)  # (min, max) Pearson r

# ---------------------------------------------------------------------------
# Form equivalence tolerance (pre-registered) — pre-score difference between
# forms A and B, measured on mean rubric-item difficulty per matched pair,
# must be within this tolerance for the forms to count as equivalent.
# ---------------------------------------------------------------------------
FORM_DIFFICULTY_TOLERANCE = 0.05  # max |mean difficulty A - mean difficulty B|

# ---------------------------------------------------------------------------
# Task-set content — Forms A and B
# ---------------------------------------------------------------------------
# Five task categories drawn directly from the AI-Augmented Workflows
# syllabus on the training page (hapax.fi/training.html, §iii): writing an instruction that returns the same answer twice;
# spotting a planted error in a model's output; judging which of two
# outputs is checkable; deciding what may be pasted where; and building a
# verification habit into a workflow instead of leaving it to memory.
#
# Two tasks per category per form (5 x 2 = 10), matched pairwise by index:
# form_a[i] and form_b[i] share a category and an item_difficulty spread,
# differing only in surface scenario. Each task's rubric items carry their
# own item_difficulty (spread across the 0-1 scale so ability_to_band's
# threshold rule produces a sensible score), a point value of 1 each, and
# max_points = number of items.
TASK_CATEGORIES = [
    "instruction_reliability",
    "error_spotting",
    "checkability_judgment",
    "data_handling_policy",
    "verification_habit",
]

# Each entry: (task_index 1-10, category, difficulty_band_label, prompt_a,
# prompt_b, rubric_items -- shared structure, item text differs per form
# only where the surface scenario requires it).
TASK_PAIRS = [
    {
        "index": 1,
        "category": "instruction_reliability",
        "prompt_a": (
            "Kuusiharju's site-supply team gets a short email from a "
            "supplier every time a delivery is confirmed. Write a single "
            "instruction you could hand an AI assistant so that, given any "
            "one of these emails, it always returns the same three-line "
            "summary in the same order: delivery date, item and quantity, "
            "and any change from the original order. Running your "
            "instruction twice on the same email must produce the same "
            "three lines both times. State the instruction, then explain "
            "in one sentence what part of it forces that repeat-consistency."
        ),
        "prompt_b": (
            "Kuusiharju's warehouse team gets a short text message from a "
            "driver every time a load is dropped off. Write a single "
            "instruction you could hand an AI assistant so that, given any "
            "one of these messages, it always returns the same three-line "
            "log entry in the same order: drop-off time, pallet count, and "
            "any damage noted. Running your instruction twice on the same "
            "message must produce the same three lines both times. State "
            "the instruction, then explain in one sentence what part of it "
            "forces that repeat-consistency."
        ),
        "rubric_items": [
            ("names a concrete consistency mechanism (fixed line count, a template, a stated field order — not just 'be consistent')", 0.15),
            ("the instruction is unambiguous about what counts as one of the three lines", 0.35),
            ("the instruction specifies what to do when the input is missing one of the three fields", 0.60),
            ("the one-sentence explanation correctly names why the instruction constrains the output, not just what a good summary looks like", 0.85),
        ],
    },
    {
        "index": 2,
        "category": "instruction_reliability",
        "prompt_a": (
            "Write an instruction for turning a week's worth of expense-"
            "claim lines (date, amount, category, submitter) into a "
            "standard approval memo. Two different colleagues, given the "
            "same week's claims and your instruction, should produce "
            "memos with the same structure and the same total — even "
            "though the wording may differ."
        ),
        "prompt_b": (
            "Write an instruction for turning a week's worth of call-log "
            "entries (time, customer, topic, outcome) into a standard "
            "follow-up-call list. Two different colleagues, given the same "
            "week's entries and your instruction, should produce lists "
            "with the same structure and the same count of calls needing "
            "follow-up — even though the wording may differ."
        ),
        "rubric_items": [
            ("specifies the exact output structure (fields and their order), not just 'a memo'/'a list'", 0.20),
            ("specifies how the total or count is derived, not just that it should appear", 0.45),
            ("addresses at least one ambiguous or duplicate-looking input line explicitly", 0.65),
            ("the instruction would genuinely survive being run by two different people without a shared example in front of them", 0.90),
        ],
    },
    {
        "index": 3,
        "category": "error_spotting",
        "prompt_a": (
            "An AI assistant drafted this email to a client:\n\n"
            "\"Thanks for your patience. Following our call on the 14th, "
            "we can confirm the revised delivery date of the 19th, three "
            "days out from today. The unit price stays at €48.50 as "
            "quoted, for a total of €4,850 on the 100-unit order.\"\n\n"
            "Find the planted error, state exactly where it sits in the "
            "text, and say what you would check to confirm it before the "
            "email goes out."
        ),
        "prompt_b": (
            "An AI assistant drafted this internal note:\n\n"
            "\"Site visit logged for the 22nd. The client's site contact "
            "confirmed access from 8am, and our crew of four will need "
            "roughly six hours on site, finishing by early afternoon on "
            "the 23rd.\"\n\n"
            "Find the planted error, state exactly where it sits in the "
            "text, and say what you would check to confirm it before the "
            "note is filed."
        ),
        "rubric_items": [
            ("identifies that an error exists at all rather than accepting the text at face value", 0.15),
            ("locates the specific error correctly — a date-arithmetic mismatch between two figures both stated in the SAME form's own text (Form A: '19th' is 5 days from the 14th, not the stated 'three days out'; Form B: an 8am start plus a 'roughly six hours' job finishes the same day, the 22nd, not the stated '23rd') — a response should name only its own form's mismatch, never the other form's numbers", 0.40),
            ("states the error precisely (which two figures disagree) rather than a vague sense something is off", 0.60),
            ("names a concrete check against a source system rather than 'I would double-check it'", 0.80),
        ],
    },
    {
        "index": 4,
        "category": "error_spotting",
        "prompt_a": (
            "An AI assistant drafted this section of a weekly ops report:\n\n"
            "\"Deliveries this week: 62, up from 54 last week (a 15% "
            "increase). Of these, 3 were late, giving an on-time rate of "
            "97%. Stock of the fast-moving items held steady at 340 units "
            "across the two depots, 170 at each.\"\n\n"
            "Find both planted errors, state exactly where each sits, and "
            "say what you would check to confirm each before the report "
            "is sent up."
        ),
        "prompt_b": (
            "An AI assistant drafted this section of a monthly finance "
            "note:\n\n"
            "\"Invoices issued this month: 118, compared with 96 last "
            "month (a 20% increase). Of these, 9 were paid late, giving an "
            "on-time rate of 92%. Outstanding balance across the two "
            "regions held steady at €58,000, split evenly at €29,000 "
            "each.\"\n\n"
            "Find both planted errors, state exactly where each sits, and "
            "say what you would check to confirm each before the note is "
            "sent up."
        ),
        # Explicit per-form item mapping (tightened Phase 3). The two
        # planted errors trade places between forms: Form A's error sits in
        # the on-time-rate figure while its growth figure is clean; Form B's
        # error sits in the growth figure while its on-time-rate figure is
        # clean. Item 1 and item 2 below are defined by ROLE (the clean
        # figure vs the erroneous figure), never by a fixed figure name, so
        # the same item index means the same thing in both forms:
        #   Form A: item 1 = the delivery-growth figure (54->62, ~15%,
        #            CORRECT as stated); item 2 = the on-time-rate figure
        #            (3/62 late, stated 97%, actually ~95% — the error).
        #   Form B: item 1 = the on-time-rate figure (9/118 late, stated
        #            92%, CORRECT as stated); item 2 = the invoice-growth
        #            figure (96->118, stated 20%, actually ~23% — the error).
        "rubric_items": [
            ("engages seriously with the arithmetic on the form's CLEAN figure — the one that checks out as stated (Form A: the 15% delivery-growth figure, 54 to 62; Form B: the 92% on-time-rate figure, 9 late of 118) — credited even if the response finds nothing else, provided the check is real arithmetic and not just restating the figure", 0.20),
            ("finds the form's headline numeric error, which requires recomputing a stated percentage from its own two source figures (Form A: the on-time rate is stated as 97% but 3 late of 62 is ~95%; Form B: the growth rate is stated as 20% but 96 to 118 is ~23%) — a response should name only its own form's error, never the other form's figures", 0.45),
            ("finds the shared structural error: the summary claims a total 'held steady' (170+170=340 in A, 29,000+29,000=58,000 in B — the addition itself is correct in both) while the same paragraph reports the underlying activity rising sharply, an unexplained contradiction the internally-consistent sum does not excuse", 0.70),
            ("proposes checking against the underlying source records (the depot/regional ledgers) rather than re-deriving from the same summary text", 0.85),
        ],
    },
    {
        "index": 5,
        "category": "checkability_judgment",
        "prompt_a": (
            "Two AI outputs answer the same question, \"what were Q2 "
            "returns as a percentage of Q2 sales?\":\n\n"
            "Output 1: \"Q2 returns ran at 4.1% of sales.\"\n"
            "Output 2: \"Q2 sales were €612,000 and returns were €25,100, "
            "so returns were 25,100 / 612,000 = 4.1% of sales.\"\n\n"
            "Which output would you sign off, and why? What exactly makes "
            "the other one harder to check?"
        ),
        "prompt_b": (
            "Two AI outputs answer the same question, \"what percentage "
            "of support tickets closed within SLA last quarter?\":\n\n"
            "Output 1: \"88% of tickets closed within SLA.\"\n"
            "Output 2: \"There were 940 tickets last quarter and 827 "
            "closed within SLA, so 827 / 940 = 88% closed within SLA.\"\n\n"
            "Which output would you sign off, and why? What exactly makes "
            "the other one harder to check?"
        ),
        "rubric_items": [
            ("correctly prefers the output that shows the source numbers and the calculation", 0.15),
            ("names specifically what is missing from the bare-number output (the two source figures), not just 'less detail'", 0.35),
            ("notes that the bare number could still be right but cannot be verified without re-running the query", 0.55),
            ("states what they would still want to check even on the fuller output (that the source figures themselves are correct)", 0.80),
        ],
    },
    {
        "index": 6,
        "category": "checkability_judgment",
        "prompt_a": (
            "Two draft customer-service replies to a complaint about a "
            "late delivery:\n\n"
            "Reply 1 (confident): \"We're very sorry — this was entirely "
            "our error and it won't happen again. We've applied a 10% "
            "credit to your account.\"\n"
            "Reply 2 (hedged): \"Thanks for flagging this. Our records "
            "show the order (ref. 4471) was dispatched two days after the "
            "confirmed date; we've applied a 10% credit (ref. CR-1182) to "
            "your account and are checking with the depot on the cause.\"\n\n"
            "Which would you send without further checking, and what "
            "would you check on the other one first?"
        ),
        "prompt_b": (
            "Two draft supplier-negotiation emails opening a price "
            "discussion:\n\n"
            "Email 1 (confident): \"Given current volumes, we'd expect a "
            "better rate than this — please revise your offer.\"\n"
            "Email 2 (hedged): \"Our order volume with you rose from "
            "1,200 to 1,650 units over the last two quarters (ref. our "
            "PO log); at that volume we'd expect the tier-2 rate rather "
            "than tier-1 — could you revise the offer accordingly?\"\n\n"
            "Which would you send without further checking, and what "
            "would you check on the other one first?"
        ),
        "rubric_items": [
            ("prefers the reply/email that cites a checkable reference (order number, ticket, PO log) over the confident-but-unsourced one", 0.20),
            ("names exactly what claim in the unsourced version cannot currently be checked", 0.40),
            ("does not simply reject the confident version outright — recognises it might be checked and then sent", 0.60),
            ("identifies a specific verification step to run before sending the unsourced version, not a general 'be careful'", 0.80),
        ],
    },
    {
        "index": 7,
        "category": "data_handling_policy",
        "prompt_a": (
            "You want an AI chat tool's help drafting a customer update. "
            "Kuusiharju has not vetted this particular tool for data "
            "handling. For each item below, say yes or no to pasting it "
            "in, with one line of reasoning:\n"
            "1. The customer's delivery address\n"
            "2. This week's total sales figure (aggregate, no customer detail)\n"
            "3. Next quarter's unreleased pricing plan\n"
            "4. A product spec sheet already published on the company website\n"
            "5. A colleague's personal mobile number, copied from an email signature"
        ),
        "prompt_b": (
            "You want an AI chat tool's help summarising a vendor quote. "
            "Kuusiharju has not vetted this particular tool for data "
            "handling. For each item below, say yes or no to pasting it "
            "in, with one line of reasoning:\n"
            "1. The vendor's line-item pricing from the quote\n"
            "2. This month's total procurement spend (aggregate, no vendor detail)\n"
            "3. An unsigned draft of next year's budget\n"
            "4. A datasheet already published on the vendor's own website\n"
            "5. An employee's home address, copied from an HR record"
        ),
        "rubric_items": [
            ("correctly says no to the item containing identifiable personal data (item 1 in A, item 5 in B)", 0.15),
            ("correctly says no to the not-yet-released internal figure (item 3 in both forms)", 0.35),
            ("correctly says yes to the already-public item (item 4 in both forms), not over-cautiously refusing it", 0.55),
            ("gives a reasoning line that names WHY (public already, personal data, competitively sensitive) rather than a bare yes/no", 0.75),
        ],
    },
    {
        "index": 8,
        "category": "data_handling_policy",
        "prompt_a": (
            "A supplier contract needs summarising for an internal memo, "
            "and you want an AI tool's help drafting the summary. The "
            "contract includes: the supplier's company registration "
            "details, the agreed unit pricing and volume discounts, a "
            "confidentiality clause naming both parties, and the delivery "
            "schedule. Decide what you would paste in as-is, what you "
            "would redact first, and why."
        ),
        "prompt_b": (
            "A client's signed service agreement needs summarising for an "
            "internal memo, and you want an AI tool's help drafting the "
            "summary. The agreement includes: the client's company name "
            "and billing contact, the agreed hourly rates and retainer "
            "cap, a non-disclosure clause naming both parties, and the "
            "service scope. Decide what you would paste in as-is, what "
            "you would redact first, and why."
        ),
        "rubric_items": [
            ("recognises the pricing/rate terms as sensitive and treats them deliberately (redact or confirm tool is vetted first), not pasted without thought", 0.20),
            ("recognises the confidentiality/NDA clause as a reason for particular caution given it names both parties", 0.45),
            ("identifies at least one part of the document that is low-risk to paste as-is (e.g. the general service scope) rather than over-redacting everything", 0.65),
            ("proposes a concrete alternative to pasting the sensitive parts (e.g. paraphrase without figures, or use a vetted internal tool) rather than just declining", 0.85),
        ],
    },
    {
        "index": 9,
        "category": "verification_habit",
        "prompt_a": (
            "You now generate the weekly ops report with AI assistance. "
            "Describe the specific check you would build into that "
            "process — not \"I'd read it over\" but a named, repeatable "
            "step — and say exactly where in the weekly workflow it sits."
        ),
        "prompt_b": (
            "You now generate the monthly stock-reconciliation summary "
            "with AI assistance. Describe the specific check you would "
            "build into that process — not \"I'd read it over\" but a "
            "named, repeatable step — and say exactly where in the "
            "monthly workflow it sits."
        ),
        "rubric_items": [
            ("names a concrete, repeatable check (e.g. cross-cast the total against the source system, spot-check N random lines) rather than a vague intention", 0.20),
            ("the check is placed at a specific point in the workflow (before it reaches a named recipient, not just 'at some point')", 0.40),
            ("the check would actually catch a wrong total or a fabricated line, not just a typo", 0.65),
            ("names who is responsible for the check and what happens if it fails (a route back, not a dead end)", 0.85),
        ],
    },
    {
        "index": 10,
        "category": "verification_habit",
        "prompt_a": (
            "Here is a multi-step AI-assisted workflow for processing "
            "incoming customer orders: (1) AI reads the incoming order "
            "email and extracts the item list and quantities; (2) AI "
            "checks stock availability against the warehouse system; (3) "
            "AI drafts a confirmation email with a delivery estimate; (4) "
            "the confirmation is sent automatically if stock is "
            "available. Identify the step most in need of a verification "
            "gate, and specify exactly what the gate should check."
        ),
        "prompt_b": (
            "Here is a multi-step AI-assisted workflow for processing "
            "incoming supplier invoices: (1) AI reads the incoming "
            "invoice PDF and extracts the line items and totals; (2) AI "
            "matches the invoice against the original purchase order; (3) "
            "AI drafts a payment approval note; (4) the note is submitted "
            "automatically if the match is within tolerance. Identify the "
            "step most in need of a verification gate, and specify "
            "exactly what the gate should check."
        ),
        "rubric_items": [
            ("identifies the extraction step (1) as carrying risk that compounds downstream, not just the automatic-send step", 0.20),
            ("identifies the automatic-action step (4) as the point where an error becomes irreversible, and argues for a gate there specifically", 0.45),
            ("specifies a concrete check content (e.g. flag any extracted quantity/total above a threshold, or any stock/match level near the cutoff) rather than 'add a review step'", 0.65),
            ("addresses what happens on a gate failure (routes to a person, does not just block silently)", 0.85),
        ],
    },
]

for pair in TASK_PAIRS:
    assert pair["category"] in TASK_CATEGORIES
    assert len(pair["rubric_items"]) >= 3
assert len(TASK_PAIRS) == 10
assert len({p["category"] for p in TASK_PAIRS}) == 5

# ---------------------------------------------------------------------------
# Instrument definitions — consumed by the Phase 5 mark.py.
# Written here as the single source of the three instruments' selection,
# form-assignment and weighting rules; generate_structure.py renders them to
# data/instruments/*.yaml so the scoring run applies them mechanically.
# ---------------------------------------------------------------------------
INSTRUMENT_DEFINITIONS = {
    "honest": {
        "label": "The honest instrument",
        "description": (
            "A/B counterbalanced pre/post on all 40 learners. Half the "
            "cohort sees Form A pre and Form B post; the other half sees "
            "Form B pre and Form A post. Scored on task performance only "
            "(the rubric); self-report is recorded but never blended in."
        ),
        "population": "all",
        "occasions_used": ["pre", "post"],
        "form_assignment": "counterbalanced",  # see generate_structure.py
        "uses_self_report": False,
        "self_report_weight": 0.0,
        "practice_effect_present": False,  # each learner sees each form once
    },
    "feedback_sheet": {
        "label": "The feedback sheet",
        "description": (
            "Post-only self-report: satisfaction and self-assessed "
            "improvement. No task performance measured at all — this is "
            "the industry-standard instrument, run honestly as a "
            "comparator."
        ),
        "population": "all",
        "occasions_used": ["post"],
        "form_assignment": None,
        "uses_self_report": True,
        "self_report_weight": 1.0,
        "practice_effect_present": False,
    },
    "naive": {
        "label": "The naive evaluation",
        "description": (
            "Volunteers only (selected by volunteering_propensity, biasing "
            "the sample toward high-confidence archetypes). Same form pre "
            "and post (planting a practice effect on the post score). "
            "Self-report blended into the estimated effect at the stated "
            "weight — assembled deliberately from real-world bad practice; "
            "each flaw is documented, not accidental."
        ),
        "population": "volunteers",
        "occasions_used": ["pre", "post"],
        "form_assignment": "same_form_repeated",
        "uses_self_report": True,
        "self_report_weight": 0.5,
        "practice_effect_present": True,
    },
}

# ---------------------------------------------------------------------------
# Volunteer selection for the naive arm — deterministic Bernoulli draw per
# learner against their volunteering_propensity, seeded once during
# generation (see generate_structure.py). Recorded in the answer key so
# Phase 5 marking can decompose the naive arm's selection bias honestly.
# ---------------------------------------------------------------------------
