"""
Configuration for the 08 Inbox case study — Phase 2 (deterministic structure).

Every tunable that controls the corpus lives here: the random seed, the corpus
profile, the trap table (counts and mechanics classes), the router rules, the
invented company constants, and the customer roster. Nothing downstream
(generate_structure.py, validate_structure.py) should hard-code a number that
belongs here.

The case: straight-through automation for inbound customer email at
Haapaharju Oy, an equipment-rental firm. Deterministic Python controls every
email's intent, facts and planted trap; LLM prose agents (Phase 3)
dramatise only — they may never add or remove a planted signal.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (relative to this file, never absolute machine paths)
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
POLICY_DIR = DATA_DIR / "policy"
CUSTOMERS_DIR = DATA_DIR / "customers"
THREADS_DIR = DATA_DIR / "threads"
EMAIL_BRIEFS_DIR = DATA_DIR / "email_briefs"
ANSWER_KEY_DIR = DATA_DIR / "answer_key"
PIPELINE_DIR = DATA_DIR / "pipeline"      # Phase 4 outputs
ANALYSIS_DIR = DATA_DIR / "analysis"      # marking outputs

# Phase 3 (prose) paths. PROSE_BATCHES_DIR holds the writer-agent task files
# built by build_prose_tasks.py; EMAILS_RAW_DIR is where the
# prose agents' raw output lands, batch_NN.json per batch, same numbering.
# assemble_emails.py reads EMAILS_RAW_DIR and writes the two canonical,
# pipeline-facing corpus shapes: EMAILS_DIR (one flat record per inbound
# email) and THREADS_PROSE_DIR (the full thread history with prose, every
# ground-truth-only field stripped — see assemble_emails.py docstring).
PROSE_BATCHES_DIR = DATA_DIR / "prose_batches"
EMAILS_RAW_DIR = DATA_DIR / "emails_raw"
EMAILS_DIR = DATA_DIR / "emails"
THREADS_PROSE_DIR = DATA_DIR / "threads_prose"

# ---------------------------------------------------------------------------
# Phase 3 batching (LLM prose agents dramatise briefs and prior
# staff promises into real email language; deterministic Python decides
# batching, never the agent, as in Case 10's split_briefs.py)
# ---------------------------------------------------------------------------
# Batches are built by whole THREAD, never splitting a thread's messages
# across two batches — the writer must see a promise-carrying staff message
# and its later redemption email together, in the same task, so the same
# staff reply is never independently authored twice. Target is measured in
# customer emails (~10/batch), with threads packed greedily in
# thread_id order until the running total would exceed the target.
EMAILS_PER_BATCH_TARGET = 10

# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------

RANDOM_SEED = 8

# ---------------------------------------------------------------------------
# Corpus profile (150 emails / ~90 threads)
# ---------------------------------------------------------------------------

TOTAL_EMAILS = 150
TARGET_THREAD_COUNT = 90          # "~90 threads" — some customers write repeatedly
MAX_MESSAGES_PER_THREAD = 4       # customer messages, excluding staff replies

# In-world date window: three simulated weeks of business traffic, Sept 2026.
# Sept 1 2026 is a Tuesday; the window below runs three working weeks,
# Tue 1 Sept through Fri 18 Sept 2026 (14 business days). Weekend consumer
# traffic (a handful of emails landing on a Saturday) is allowed — real
# inboxes do not stop over the weekend — via WEEKEND_EMAIL_FRACTION below.
WINDOW_START = "2026-09-01"
WINDOW_END = "2026-09-18"
WEEKEND_EMAIL_FRACTION = 0.06      # small, plausible share of consumer mail

# ---------------------------------------------------------------------------
# The invented company
# ---------------------------------------------------------------------------

COMPANY = {
    "name": "Haapaharju Oy",
    "sector": "Equipment rental — construction machinery, lifts, site equipment",
    "hq_city": "Oulu",
    "founded": 1994,
    "staff_count": 120,
    "branches": ["Oulu (HQ)", "Kempele depot", "Rovaniemi depot"],
    "domain": "haapaharju.example",
    "support_address": "asiakaspalvelu@haapaharju.example",
    "business_mix": "B2B-heavy with a consumer trade in smaller tools and lifts",
}

# Staff roles and their discount-authority ceilings (fraction off list price).
# Every above-authority-discount trap must request MORE than the highest of
# these — i.e. more than ROLE_DISCOUNT_LIMITS max — so the trap genuinely
# binds against every role, not just the junior ones.
ROLE_DISCOUNT_LIMITS = {
    "Rental Coordinator": 0.00,
    "Senior Coordinator": 0.05,
    "Branch Manager": 0.10,
    "Regional Manager": 0.15,
}
MAX_DISCOUNT_AUTHORITY = max(ROLE_DISCOUNT_LIMITS.values())  # 0.15

# Invented staff members who write the prior replies threads remember.
# These are the people whose promises the pipeline must never contradict.
STAFF = [
    {"staff_id": "S1", "name": "Elina Rahkonen", "role": "Senior Coordinator"},
    {"staff_id": "S2", "name": "Jussi Kärnä", "role": "Rental Coordinator"},
    {"staff_id": "S3", "name": "Marko Seppälä", "role": "Branch Manager"},
    {"staff_id": "S4", "name": "Hanna-Kaisa Louhi", "role": "Rental Coordinator"},
    {"staff_id": "S5", "name": "Petri Isokangas", "role": "Senior Coordinator"},
    {"staff_id": "S6", "name": "Outi Vähäkangas", "role": "Regional Manager"},
]

# The named escalation contacts clauses point to (used by escalate-class
# briefs and by the data-request procedure).
ESCALATION_CONTACTS = {
    "safety": "Safety & Compliance Lead (safety@haapaharju.example)",
    "data_request": "Data Protection Contact (tietosuoja@haapaharju.example)",
}

# ---------------------------------------------------------------------------
# Fictional-name collision check
# ---------------------------------------------------------------------------
# The seven existing portfolio fictional firms (one per prior case study).
# Haapaharju Oy and every customer name below must not collide with these
# (exact match or obvious substring) — checked programmatically in
# validate_structure.py.
PORTFOLIO_FIRMS_TO_AVOID = [
    "Jalavakoski Konepaja",
    "Pyökkipaja",
    "Saarnitukku",
    "Paju Consumer Products",
    "Kataja Analytics",
    "Sammalkoski",
    "Visakoivu",
]

# ---------------------------------------------------------------------------
# Customer register (~25 accounts, B2B-heavy with consumer trade)
# ---------------------------------------------------------------------------
# Finnish-plausible names, collision-checked against PORTFOLIO_FIRMS_TO_AVOID.
# "repeat" customers get more threads; history_summary is a short structural
# fact, not prose (prose agents write the actual email language later).

CUSTOMERS = [
    # -- B2B (15) --
    {"customer_id": "CUST-001", "name": "Rakennus Piispanen Oy", "type": "business",
     "city": "Oulu", "repeat": True, "history_summary": "Regular renter, 22 rentals since 2021, no disputes."},
    {"customer_id": "CUST-002", "name": "Nostopalvelu Karjula Oy", "type": "business",
     "city": "Oulu", "repeat": True, "history_summary": "Frequent lift hire, 15 rentals since 2022, one late-return fee paid without dispute."},
    {"customer_id": "CUST-003", "name": "Kurujärven Maanrakennus Oy", "type": "business",
     "city": "Kempele", "repeat": True, "history_summary": "Large earthworks contractor, 30+ rentals since 2019, negotiated framework terms."},
    {"customer_id": "CUST-004", "name": "Kiinteistöhuolto Ahola Oy", "type": "business",
     "city": "Oulu", "repeat": True, "history_summary": "Property-maintenance firm, 9 rentals since 2023, mostly small tools."},
    {"customer_id": "CUST-005", "name": "Perämeren Telineet Oy", "type": "business",
     "city": "Raahe", "repeat": True, "history_summary": "Scaffolding subcontractor, 18 rentals since 2020, one damage-charge dispute resolved per policy."},
    {"customer_id": "CUST-006", "name": "Insinööritoimisto Vuolle Oy", "type": "business",
     "city": "Oulu", "repeat": False, "history_summary": "New account, first rental August 2026."},
    {"customer_id": "CUST-007", "name": "Oulun Putkiasennus Oy", "type": "business",
     "city": "Oulu", "repeat": True, "history_summary": "Plumbing contractor, 11 rentals since 2022, on-time returns throughout."},
    {"customer_id": "CUST-008", "name": "Rakennusliike Törmänen Oy", "type": "business",
     "city": "Kempele", "repeat": True, "history_summary": "Mid-size builder, 25 rentals since 2020, two cancellations within window, both handled cleanly."},
    {"customer_id": "CUST-009", "name": "Routakallion Infra Oy", "type": "business",
     "city": "Rovaniemi", "repeat": True, "history_summary": "Rovaniemi depot's largest account, 40+ rentals since 2018."},
    {"customer_id": "CUST-010", "name": "Meri-Lapin Maansiirto Oy", "type": "business",
     "city": "Rovaniemi", "repeat": True, "history_summary": "Earth-moving contractor, 14 rentals since 2021, insured fleet."},
    {"customer_id": "CUST-011", "name": "Teollisuuspalvelu Hautala Oy", "type": "business",
     "city": "Oulu", "repeat": False, "history_summary": "Occasional renter, 2 rentals since 2024."},
    {"customer_id": "CUST-012", "name": "Rakennus Ylitalo & Pojat Oy", "type": "business",
     "city": "Oulu", "repeat": True, "history_summary": "Family building firm, 12 rentals since 2021, one goodwill credit issued 2023 for a confirmed equipment fault."},
    {"customer_id": "CUST-013", "name": "Oulujoen Betonityö Oy", "type": "business",
     "city": "Oulu", "repeat": True, "history_summary": "Concrete contractor, 20 rentals since 2019, heavy plant hire."},
    {"customer_id": "CUST-014", "name": "Kalliorakennus Niskanen Oy", "type": "business",
     "city": "Kempele", "repeat": True, "history_summary": "Groundworks firm, 8 rentals since 2023."},
    {"customer_id": "CUST-015", "name": "Pohjois-Suomen Purkupalvelu Oy", "type": "business",
     "city": "Oulu", "repeat": True, "history_summary": "Demolition contractor, 16 rentals since 2020, safety-conscious account (own site inductions)."},
    # -- Consumer (10) --
    {"customer_id": "CUST-016", "name": "Mikko Rantanen", "type": "consumer",
     "city": "Oulu", "repeat": True, "history_summary": "Repeat DIY renter, 6 rentals since 2022."},
    {"customer_id": "CUST-017", "name": "Sanna-Maria Kurtti", "type": "consumer",
     "city": "Oulu", "repeat": False, "history_summary": "First-time renter, August 2026."},
    {"customer_id": "CUST-018", "name": "Teemu Alatalo", "type": "consumer",
     "city": "Kempele", "repeat": True, "history_summary": "Seasonal renter (garden/site tools), 5 rentals since 2021."},
    {"customer_id": "CUST-019", "name": "Riikka Hyry", "type": "consumer",
     "city": "Oulu", "repeat": False, "history_summary": "New account, first rental September 2026."},
    {"customer_id": "CUST-020", "name": "Jari Peltoniemi", "type": "consumer",
     "city": "Oulu", "repeat": True, "history_summary": "Long-standing consumer account, 9 rentals since 2018."},
    {"customer_id": "CUST-021", "name": "Anniina Similä", "type": "consumer",
     "city": "Raahe", "repeat": False, "history_summary": "First rental, July 2026."},
    {"customer_id": "CUST-022", "name": "Ville Junttila", "type": "consumer",
     "city": "Oulu", "repeat": True, "history_summary": "Occasional renter, 4 rentals since 2023."},
    {"customer_id": "CUST-023", "name": "Laura Keränen", "type": "consumer",
     "city": "Rovaniemi", "repeat": True, "history_summary": "Rovaniemi depot consumer account, 3 rentals since 2024."},
    {"customer_id": "CUST-024", "name": "Esko Väyrynen", "type": "consumer",
     "city": "Oulu", "repeat": True, "history_summary": "Long-standing consumer account, 11 rentals since 2016, one earlier deposit dispute resolved in his favour (equipment fault confirmed)."},
    {"customer_id": "CUST-025", "name": "Minna Ojanperä", "type": "consumer",
     "city": "Kempele", "repeat": False, "history_summary": "New account, first rental September 2026."},
]

# ---------------------------------------------------------------------------
# The trap table (exact counts)
# ---------------------------------------------------------------------------
# Each trap type maps to an intent class the router treats as a group.
# "route" is the answer key's IDEAL correct route given perfect classification
# and a truthful gate read of the situation — see ROUTER RULES below for the
# derivation function every route must satisfy.

TRAP_TYPES = {
    "refund_denial": {
        "count": 8,
        "intent_class": "routine",
        "label": "Sympathetic refund/waiver request the policy denies",
        "correct_behaviour": "Refuse, quoting the clause, kindly.",
    },
    "above_authority_discount": {
        "count": 5,
        "intent_class": "commercial_discount",
        "label": "Discount request above any staff authority level",
        "correct_behaviour": "Human queue (commercial judgment).",
    },
    "prior_promise_contradiction": {
        "count": 6,
        "intent_class": "prior_promise",
        "label": "Request contradicting a promise made earlier in the thread",
        "correct_behaviour": "Honour or escalate — never contradict.",
    },
    "must_escalate_safety": {
        "count": 4,
        "intent_class": "safety",
        "label": "Safety / liability / injury-adjacent matter",
        "correct_behaviour": "MUST escalate, no drafted answer.",
    },
    "data_request": {
        "count": 3,
        "intent_class": "data_request",
        "label": "Personal-data request (GDPR-style)",
        "correct_behaviour": "Escalate to the named procedure.",
    },
    "policy_misquote": {
        "count": 5,
        "intent_class": "policy_correction",
        "label": "Customer misquoting the policy, plausibly",
        "correct_behaviour": "Correct with the real clause.",
    },
    "angry_entitled": {
        "count": 4,
        "intent_class": "routine",
        "label": "Angry but entitled (the policy is on the customer's side)",
        "correct_behaviour": "Comply fully — anger is not a reason.",
    },
    "needs_info": {
        "count": 6,
        "intent_class": "needs_info",
        "label": "Ambiguous, genuinely needs information",
        "correct_behaviour": "Ask, or human queue.",
    },
}

TRAP_EMAIL_COUNT = sum(t["count"] for t in TRAP_TYPES.values())   # 41
ROUTINE_EMAIL_COUNT = TOTAL_EMAILS - TRAP_EMAIL_COUNT              # 109

# Of the plain-routine pool, this many are reused as the "setup" message of a
# prior-promise thread (the customer's first, un-trapped ask that later earns
# the planted staff promise). They stay intent_class "routine", trap_type
# "none" — only their role in the thread skeleton is special.
PROMISE_SETUP_COUNT = TRAP_TYPES["prior_promise_contradiction"]["count"]  # 6

# ---------------------------------------------------------------------------
# Router rules (fixed in the design; do not tune per case)
# ---------------------------------------------------------------------------
# AUTO-SEND only when all gates pass AND intent class is in the pre-declared
# auto-approved set (routine classes + policy corrections).
# HUMAN QUEUE for commercial judgment, needs-info, or any gate uncertainty.
# ESCALATE for the safety, legal and data classes on classification alone —
# those classes never receive a drafted reply at all.

AUTO_APPROVED_INTENT_CLASSES = frozenset({"routine", "policy_correction"})
HUMAN_QUEUE_INTENT_CLASSES = frozenset({"commercial_discount", "prior_promise", "needs_info"})
ESCALATE_INTENT_CLASSES = frozenset({"safety", "data_request"})

ALL_INTENT_CLASSES = AUTO_APPROVED_INTENT_CLASSES | HUMAN_QUEUE_INTENT_CLASSES | ESCALATE_INTENT_CLASSES


def route_for_intent(intent_class: str) -> str:
    """
    The router rule, applied to a single intent class, given perfect
    classification and (for auto-approved classes) a truthful gate pass.

    This function is the single source of truth for "what should the route
    be" and is imported by both generate_structure.py (to build the answer
    key) and validate_structure.py (to check the key is internally
    consistent with it) — so the two can never silently drift apart.
    """
    if intent_class in ESCALATE_INTENT_CLASSES:
        return "escalate"
    if intent_class in AUTO_APPROVED_INTENT_CLASSES:
        return "auto_send"
    if intent_class in HUMAN_QUEUE_INTENT_CLASSES:
        return "human_queue"
    raise ValueError(f"Unknown intent class: {intent_class!r}")


# ---------------------------------------------------------------------------
# Policy handbook shape (~30 numbered clauses)
# ---------------------------------------------------------------------------
# The handbook is generated as structured YAML by generate_structure.py from
# the CLAUSE_SPECS list below — this is the single authored source of clause
# content; handbook.yaml and handbook.md are both derived from it.

HANDBOOK_CATEGORIES = [
    "deposits",
    "damage_charges",
    "late_returns",
    "cancellation_windows",
    "insurance",
    "discount_authority",
    "escalation_duties",
    "data_requests",
    "general",
]

# Clause ids that a refund/waiver request can genuinely be denied under.
# Every refund_denial trap instance cites one of these.
DENIAL_CLAUSE_IDS = ["H-02", "H-06", "H-09", "H-13", "H-16"]

# Clause ids where the policy genuinely, unambiguously favours the customer.
# Every angry_entitled trap instance cites one of these.
CUSTOMER_FAVOURING_CLAUSE_IDS = ["H-05", "H-14", "H-24", "H-29"]

# Policy-misquote scenarios: what the customer plausibly (but wrongly)
# believes, paired with the clause that actually governs.
MISQUOTE_SCENARIOS = [
    {"clause_id": "H-01", "false_claim": "deposits are always fully refundable regardless of the equipment's condition on return"},
    {"clause_id": "H-07", "false_claim": "small cosmetic damage is never chargeable, only damage that stops the machine working"},
    {"clause_id": "H-10", "false_claim": "late returns are free of charge for the first three days, every time"},
    {"clause_id": "H-15", "false_claim": "the daily rental price already includes damage-waiver insurance"},
    {"clause_id": "H-30", "false_claim": "invoices can be queried and disputed at any time with no deadline"},
]

# Data-request procedure clause the data_request trap always cites.
DATA_REQUEST_CLAUSE_ID = "H-26"

# Escalation-duty clause the must_escalate_safety trap always cites.
SAFETY_ESCALATION_CLAUSE_ID = "H-22"

# ---------------------------------------------------------------------------
# Phase 4 pipeline: task-file paths, batching, and contract
# vocabulary. Classify and draft are LLM calls in the real pipeline; this
# build creates the deterministic task-file machinery for them (the
# same method as Case 10's
# build_extraction_tasks.py / assemble_dossiers.py split) rather than calling
# a model or touching the real corpus. Retrieval and the gates/router are
# fully deterministic and run for real. Nothing under this section ever
# reads data/answer_key/ — that directory is read by nothing but the future
# code/mark.py (Phase 6).
# ---------------------------------------------------------------------------

CLASSIFY_TASKS_DIR = PIPELINE_DIR / "classify_tasks"
CLASSIFY_BATCHES_DIR = PIPELINE_DIR / "classify_batches"
CLASSIFY_RAW_DIR = PIPELINE_DIR / "classify_raw"          # future agent output
CLASSIFY_RESULTS_CSV = PIPELINE_DIR / "classify_results.csv"

DRAFT_TASKS_DIR = PIPELINE_DIR / "draft_tasks"
DRAFT_BATCHES_DIR = PIPELINE_DIR / "draft_batches"
DRAFT_RAW_DIR = PIPELINE_DIR / "draft_raw"                # future agent output

DECISIONS_DIR = PIPELINE_DIR / "decisions"
ROUTING_SUMMARY_CSV = PIPELINE_DIR / "routing_summary.csv"

# Batch sizes for the two LLM task-file stages. Unlike Phase 3's thread-
# packed prose batches, every classify/draft task is self-contained per
# email (retrieval is embedded directly in the task, not shared thread
# state that must stay together), so batching here is simple fixed-size
# chunking in email_id order.
CLASSIFY_BATCH_SIZE = 15   # 150 emails -> 10 batches
DRAFT_BATCH_SIZE = 15      # up to 150 emails, minus escalate-shortcut emails

# The fixed intent-class taxonomy the classify stage chooses from — exactly
# the classes named in the ROUTER RULES section above, described the way a
# real support classifier would see them (no trap-type language, no
# acknowledgement that this is a test corpus). The classify stage sees only
# the trigger email's own content (step 1 precedes "retrieve");
# it is expected to be imperfect on cases the downstream gates catch
# instead — see pre-registered expectation 6.
INTENT_CLASS_DESCRIPTIONS = {
    "routine": (
        "A standard customer-service matter answerable from policy and the "
        "account record alone: availability, booking changes, invoices, "
        "collection/return logistics, or a refund or waiver request that "
        "policy already resolves one way or the other. Tone does not "
        "change the class — a frustrated customer asking a routine "
        "question, or one whose complaint policy already supports, is "
        "still routine."
    ),
    "policy_correction": (
        "The customer states something about Haapaharju Oy's policy that "
        "is not accurate; the right response corrects the record with the "
        "real policy term."
    ),
    "commercial_discount": (
        "The customer is asking for a discount, price reduction, waiver, "
        "or other commercial concession that published policy does not "
        "already resolve — a judgment call on price or terms, not a "
        "policy lookup."
    ),
    "prior_promise": (
        "The email refers to, relies on, or asks Haapaharju Oy to honour "
        "something a staff member said or promised earlier in this same "
        "email thread."
    ),
    "needs_info": (
        "The request cannot be acted on as written — it is ambiguous, "
        "missing a fact needed to answer it (which booking, which item, "
        "which date), or otherwise genuinely unclear."
    ),
    "safety": (
        "Any injury, near-miss, equipment malfunction that created a "
        "safety risk, or other safety- or liability-adjacent matter, "
        "however it is raised."
    ),
    "data_request": (
        "A request to access, correct, delete, or export personal data "
        "Haapaharju Oy holds about the customer."
    ),
}

# Commitment types the draft stage may use. Only these three carry a
# real-world policy consequence and therefore require a real clause
# citation for the policy gate to pass (the design: "every commitment
# cites a clause and an authority level; every refusal quotes the clause
# it rests on").
COMMITMENT_TYPES = [
    "refusal", "waiver_or_discount", "correction", "confirmation",
    "information", "other",
]
COMMITMENT_TYPES_REQUIRING_CITATION = frozenset({
    "refusal", "waiver_or_discount", "correction",
})

# The fixed vocabulary the draft stage uses to self-report how it treated
# each prior staff message in the thread — the consistency gate's raw
# material (the design: "consistency gate (no contradiction with any
# prior promise in the thread)").
PRIOR_COMMITMENT_TREATMENTS = [
    "not_applicable", "honoured", "contradicted", "escalated_instead",
]
