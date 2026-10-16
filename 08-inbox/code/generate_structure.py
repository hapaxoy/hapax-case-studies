"""
08 Inbox — Phase 2 deterministic structure generator.

Builds, in order:
  1. The policy handbook (data/policy/handbook.yaml + handbook.md) — ~30 numbered
     clauses, internally consistent so the traps genuinely bind.
  2. The customer register (data/customers/register.csv).
  3. Thread skeletons (data/threads/thread_NNN.json) — which customer, how many
     messages, dates, and (for the 6 prior-promise traps) the prior staff
     reply's planted promise.
  4. Email briefs (data/email_briefs/brief_NNN.json) — one per inbound email:
     customer, thread position, intent class, facts, trap mechanics, tone notes.
  5. The answer key (data/answer_key/answer_key.csv) — correct route, binding
     clauses, correct commitments, trap class. Read by nothing but the future
     code/mark.py.

Deterministic Python controls all of the above; nothing here is prose. Later
phases add LLM-written email and staff-reply text on top of this structure —
prose agents dramatise, they never add or remove a planted signal.

Run: python generate_structure.py
Then: python validate_structure.py   (must exit 0)
"""

from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta

import pandas as pd
import yaml

import config

# ---------------------------------------------------------------------------
# Policy handbook content (the single authored source; handbook.yaml and
# handbook.md are both derived from CLAUSE_SPECS below).
# ---------------------------------------------------------------------------

CLAUSE_SPECS = [
    # -- Deposits --
    ("H-01", "deposits", "Refundable damage deposit",
     "A refundable damage deposit is charged at booking for all machinery and lift "
     "rentals. The deposit is returned in full within five (5) working days of the "
     "equipment being checked in, provided the equipment is undamaged and complete."),
    ("H-02", "deposits", "Deposit forfeiture",
     "The deposit is forfeited in full, with no exceptions, if the equipment is "
     "returned damaged beyond normal wear, missing accessories, or more than seven "
     "(7) calendar days late."),
    ("H-03", "deposits", "Deposit-exempt rentals",
     "Deposits are not required for hand tools and site-consumable rentals under "
     "€150 total value."),
    # -- Damage charges --
    ("H-04", "damage_charges", "Damage assessment",
     "Damage charges are assessed against the standard repair-cost schedule "
     "maintained at each depot and communicated to the customer within five (5) "
     "working days of check-in."),
    ("H-05", "damage_charges", "Pre-existing damage",
     "No damage charge applies where the damage is confirmed, from check-out "
     "photographs or the depot's own pre-rental inspection record, to have existed "
     "before the rental began."),
    ("H-06", "damage_charges", "Damage charges are final",
     "Damage charges assessed under clause H-04 are final once the repair-cost "
     "schedule has been applied and communicated; they are not negotiable or "
     "waivable after the event, including for a first-time or long-standing "
     "customer."),
    ("H-07", "damage_charges", "Cosmetic damage",
     "Cosmetic damage that does not affect the safe or working operation of the "
     "equipment is chargeable at 50% of the relevant repair-cost schedule line, "
     "not waived."),
    ("H-08", "damage_charges", "Total loss or theft",
     "Total loss or theft of rented equipment is charged at full replacement "
     "value, less any deposit held, regardless of insurance status (see "
     "H-15–H-17)."),
    # -- Late returns --
    ("H-09", "late_returns", "Late return fee",
     "A late return fee equal to 100% of the daily rate applies for each calendar "
     "day the equipment is returned after the agreed end date. The fee is not "
     "waived for weather, traffic, or site-schedule delays."),
    ("H-10", "late_returns", "Grace day",
     "Customers who notify the depot before the agreed end date that a return "
     "will be late receive one grace day free of the late fee, once per rolling "
     "12-month period per account."),
    ("H-11", "late_returns", "Verbal extensions",
     "Late fees are calculated from the agreed end date on the rental agreement, "
     "not from any informal extension discussed verbally; verbal extensions must "
     "be confirmed in writing to take effect."),
    # -- Cancellation windows --
    ("H-12", "cancellation_windows", "Cancellation more than 48 hours out",
     "Bookings cancelled more than 48 hours before the scheduled pickup time are "
     "refunded in full."),
    ("H-13", "cancellation_windows", "Late cancellation forfeiture",
     "Bookings cancelled within 48 hours of the scheduled pickup time forfeit 50% "
     "of the booking value; bookings cancelled after pickup has occurred forfeit "
     "the full first rental day, with no exceptions for change of mind or site "
     "delay."),
    ("H-14", "cancellation_windows", "Cancellation by Haapaharju Oy",
     "Where Haapaharju Oy cancels or is unable to fulfil a confirmed booking "
     "(equipment unavailability, breakdown of the reserved unit), the customer "
     "receives a full refund of any sums paid plus a 10% goodwill credit toward "
     "a future rental."),
    # -- Insurance --
    ("H-15", "insurance", "Damage Waiver Cover is optional",
     "Optional Damage Waiver Cover (DWC) may be purchased at booking for a daily "
     "fee shown in the price list; it is not included in the base rental price."),
    ("H-16", "insurance", "DWC exclusions",
     "DWC does not cover loss or damage caused by operating equipment outside "
     "its stated working limits, unauthorised use by a person not named on the "
     "rental agreement, or damage to tyres, tracks, and consumable parts."),
    ("H-17", "insurance", "Equivalent third-party cover",
     "Customers may provide evidence of equivalent third-party plant-insurance "
     "cover in place of purchasing DWC; the depot manager confirms adequacy "
     "before pickup."),
    # -- Discount authority (one clause per role, ceilings from config) --
    ("H-18", "discount_authority", "Rental Coordinator authority",
     "Rental Coordinators may not apply any discretionary discount; list price "
     "and published promotional rates only."),
    ("H-19", "discount_authority", "Senior Coordinator authority",
     "Senior Coordinators may apply a discretionary discount of up to 5% on a "
     "single booking."),
    ("H-20", "discount_authority", "Branch Manager authority",
     "Branch Managers may apply a discretionary discount of up to 10% on a "
     "single booking, or on a standing account arrangement reviewed annually."),
    ("H-21", "discount_authority", "Regional Manager authority",
     "Regional Managers may apply a discretionary discount of up to 15% on a "
     "single booking; this is the highest discount authority held anywhere in "
     "the company. Any request beyond 15% must be referred to the Managing "
     "Director, who is not part of the standard approval chain."),
    # -- Escalation duties --
    ("H-22", "escalation_duties", "Safety and injury escalation",
     "Any report of injury, near-miss, or equipment failure that created a "
     "safety risk during a rental must be escalated immediately to the Safety "
     "& Compliance Lead. No commitment, apology framed as an admission of "
     "fault, or drafted reply is sent to the customer without the Safety & "
     "Compliance Lead's sign-off."),
    ("H-23", "escalation_duties", "Safety recalls",
     "Equipment recalled for a safety defect is withdrawn from the fleet "
     "immediately on notice from the manufacturer or the Safety & Compliance "
     "Lead; affected customers are contacted proactively, not on request."),
    ("H-24", "escalation_duties", "Confirmed equipment fault",
     "Where a confirmed equipment fault caused a rental to be unusable for "
     "part or all of its booked period, the customer is entitled to a "
     "pro-rated refund for the unusable period plus a goodwill credit, "
     "without needing to raise a formal complaint."),
    ("H-25", "escalation_duties", "Financial-loss complaints",
     "Complaints alleging financial loss caused by Haapaharju Oy's error "
     "(beyond the direct rental cost) are escalated to the Branch Manager; "
     "front-line staff do not settle these directly."),
    # -- Data requests --
    ("H-26", "data_requests", "Personal-data requests",
     "Requests to access, correct, or delete personal data held about a "
     "customer are escalated to the Data Protection Contact, who responds "
     "within the statutory period. Front-line staff do not action deletion "
     "or export requests themselves."),
    ("H-27", "data_requests", "Marketing preferences",
     "Marketing communications preferences can be changed by front-line "
     "staff directly and do not require escalation to the Data Protection "
     "Contact."),
    # -- General --
    ("H-28", "general", "Availability is not a guarantee until confirmed",
     "Equipment availability is checked in the live booking system at the "
     "time of enquiry; verbal availability given more than 24 hours before "
     "pickup is indicative, not guaranteed, until the booking is confirmed."),
    ("H-29", "general", "Confirmed price is locked",
     "A confirmed booking's price is locked at the price shown at "
     "confirmation; subsequent price-list changes do not apply retroactively "
     "to an already-confirmed booking."),
    ("H-30", "general", "Invoice queries",
     "Invoice queries must be raised within 30 days of the invoice date; "
     "front-line staff may correct clear invoicing errors (wrong rate "
     "applied, arithmetic mistakes) at any time without escalation."),
]

# ---------------------------------------------------------------------------
# Content used only by the generator (not tunables, so kept out of config.py)
# ---------------------------------------------------------------------------

EQUIPMENT_CATALOGUE = [
    "18m articulated boom lift", "13-tonne excavator", "compact track loader",
    "6m scaffold tower", "20kVA diesel generator", "140L concrete mixer",
    "core drill rig", "diamond floor saw", "pressure washer (petrol)",
    "site cabin (single unit)", "scissor lift (10m)", "mini dumper (1-tonne)",
    "concrete breaker (hydraulic)", "site fencing (per 50m run)",
    "tower light (LED, towable)", "plate compactor", "cement mixer trailer",
]

PROMISE_TEMPLATES = [
    {
        "promise_id": "PROM-01", "kind": "deposit_waiver",
        "description": "waived the damage deposit on the customer's next rental as a loyalty gesture",
        "naive_denial_clause_id": "H-01",
        "naive_denial_note": "a naive draft would charge the deposit per H-01, contradicting the waiver",
    },
    {
        "promise_id": "PROM-02", "kind": "late_fee_refund",
        "description": "promised to refund a late fee already charged, as a goodwill gesture after a depot mix-up",
        "naive_denial_clause_id": "H-09",
        "naive_denial_note": "a naive draft would cite H-09 (late fees are not waived) and refuse the refund already promised",
    },
    {
        "promise_id": "PROM-03", "kind": "extended_deadline",
        "description": "promised a free 3-day extension on the current rental at no extra charge",
        "naive_denial_clause_id": "H-09",
        "naive_denial_note": "a naive draft would apply the late fee under H-09 for days already covered by the promised extension",
    },
    {
        "promise_id": "PROM-04", "kind": "held_replacement_unit",
        "description": "promised a specific replacement unit would be held at the same rate for the customer's next visit",
        "naive_denial_clause_id": "H-28",
        "naive_denial_note": "a naive draft would treat availability as unconfirmed per H-28, ignoring the specific hold already promised",
    },
    {
        "promise_id": "PROM-05", "kind": "free_delivery",
        "description": "promised free delivery on the customer's next order as an apology for a previous scheduling error",
        "naive_denial_clause_id": None,
        "naive_denial_note": "delivery is normally charged; a naive draft would quote the standard delivery fee, contradicting the promise",
    },
    {
        "promise_id": "PROM-06", "kind": "price_match",
        "description": "promised to match a lower price the customer found elsewhere for their next booking",
        "naive_denial_clause_id": "H-29",
        "naive_denial_note": "H-29 only locks the price of an already-confirmed booking; a naive draft would quote current list price for the new booking, contradicting the match promised",
    },
]

TONE_NOTE_DEFAULT = (
    "Frustrated tone is permitted; cartoonish anger is not. The word 'fraud' "
    "must not appear anywhere in the correspondence."
)
TONE_NOTE_ANGRY_ENTITLED = (
    "Customer is angry and the anger is legitimate — the clause genuinely favours "
    "them. Frustration is allowed; never write the customer as dishonest or as "
    "trying it on. The word 'fraud' must not appear."
)

BUSINESS_ONLY_TRAP_TYPES = {"must_escalate_safety", "above_authority_discount"}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def business_days(start: str, end: str) -> list[date]:
    """All Monday-Friday dates between start and end inclusive."""
    start_d = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    days = []
    current = start_d
    while current <= end_d:
        if current.weekday() < 5:  # 0=Mon .. 4=Fri
            days.append(current)
        current += timedelta(days=1)
    return days


def weekend_days(start: str, end: str) -> list[date]:
    start_d = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    days = []
    current = start_d
    while current <= end_d:
        if current.weekday() >= 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def random_timestamp(rng: random.Random, day: date) -> datetime:
    hour = rng.randint(8, 17)
    minute = rng.randint(0, 59)
    return datetime(day.year, day.month, day.day, hour, minute)


def clause_lookup(clause_specs) -> dict:
    return {c[0]: {"category": c[1], "title": c[2], "text": c[3]} for c in clause_specs}


# ---------------------------------------------------------------------------
# Step 1: policy handbook
# ---------------------------------------------------------------------------

def build_handbook() -> dict:
    """Assemble the handbook document (dict, ready for YAML dump)."""
    clauses = [
        {"id": cid, "category": cat, "title": title, "text": text}
        for cid, cat, title, text in CLAUSE_SPECS
    ]
    handbook = {
        "company": config.COMPANY["name"],
        "document": "Haapaharju Oy customer-service policy handbook",
        "clause_count": len(clauses),
        "discount_authority_limits": {
            role: f"{limit:.0%}" for role, limit in config.ROLE_DISCOUNT_LIMITS.items()
        },
        "escalation_contacts": config.ESCALATION_CONTACTS,
        "clauses": clauses,
    }
    return handbook


def write_handbook(handbook: dict) -> None:
    config.POLICY_DIR.mkdir(parents=True, exist_ok=True)

    yaml_path = config.POLICY_DIR / "handbook.yaml"
    with yaml_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(handbook, f, sort_keys=False, allow_unicode=True, width=100)
    print(f"  wrote {yaml_path.relative_to(config.PROJECT_ROOT)} ({handbook['clause_count']} clauses)")

    md_lines = [
        f"# {handbook['document']}",
        "",
        f"*Generated from `handbook.yaml` — do not hand-edit; regenerate via "
        f"`generate_structure.py`.*",
        "",
        "## Discount authority",
        "",
    ]
    for role, limit in handbook["discount_authority_limits"].items():
        md_lines.append(f"- **{role}**: up to {limit}")
    md_lines += ["", "## Escalation contacts", ""]
    for kind, contact in handbook["escalation_contacts"].items():
        md_lines.append(f"- **{kind}**: {contact}")
    md_lines += ["", "## Clauses", ""]
    current_category = None
    for clause in handbook["clauses"]:
        if clause["category"] != current_category:
            current_category = clause["category"]
            md_lines += ["", f"### {current_category.replace('_', ' ').title()}", ""]
        md_lines.append(f"**{clause['id']} — {clause['title']}**  ")
        md_lines.append(clause["text"])
        md_lines.append("")

    md_path = config.POLICY_DIR / "handbook.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"  wrote {md_path.relative_to(config.PROJECT_ROOT)}")


# ---------------------------------------------------------------------------
# Step 2: customer register
# ---------------------------------------------------------------------------

def build_customer_register(rng: random.Random) -> pd.DataFrame:
    rows = []
    for c in config.CUSTOMERS:
        open_rentals = rng.randint(1, 3) if c["repeat"] else rng.randint(0, 1)
        account_since_year = 2024 if not c["repeat"] else rng.choice([2016, 2018, 2019, 2020, 2021, 2022, 2023])
        rows.append({
            "customer_id": c["customer_id"],
            "name": c["name"],
            "type": c["type"],
            "city": c["city"],
            "repeat_customer": c["repeat"],
            "account_since_year": account_since_year,
            "open_rentals": open_rentals,
            "history_summary": c["history_summary"],
        })
    return pd.DataFrame(rows)


def write_customer_register(df: pd.DataFrame) -> None:
    config.CUSTOMERS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = config.CUSTOMERS_DIR / "register.csv"
    df.to_csv(out_path, index=False)
    print(f"  wrote {out_path.relative_to(config.PROJECT_ROOT)} ({len(df)} customers)")


# ---------------------------------------------------------------------------
# Step 3+4+5: threads, briefs, answer key
# ---------------------------------------------------------------------------

def build_trap_slot_pool(rng: random.Random) -> tuple[list[str], list[str]]:
    """
    Returns (promise_trap_slots, other_slots) where other_slots mixes the
    remaining trap types with plain routine emails, already shuffled.
    """
    promise_trap_slots = ["prior_promise_contradiction"] * config.TRAP_TYPES[
        "prior_promise_contradiction"]["count"]

    other_trap_slots = []
    for trap_type, spec in config.TRAP_TYPES.items():
        if trap_type == "prior_promise_contradiction":
            continue
        other_trap_slots += [trap_type] * spec["count"]

    plain_routine_count = config.ROUTINE_EMAIL_COUNT - config.PROMISE_SETUP_COUNT
    other_slots = other_trap_slots + ["none"] * plain_routine_count
    rng.shuffle(other_slots)

    assert len(promise_trap_slots) == config.PROMISE_SETUP_COUNT
    assert len(other_slots) == config.TOTAL_EMAILS - 2 * config.PROMISE_SETUP_COUNT
    return promise_trap_slots, other_slots


def partition_into_threads(rng: random.Random, slots: list[str], thread_count: int) -> list[list[str]]:
    """Split `slots` (already shuffled) into `thread_count` chunks, sizes 1..MAX."""
    sizes = [1] * thread_count
    extra = len(slots) - thread_count
    if extra < 0:
        raise ValueError("Not enough threads for at least one message each.")
    guard = 0
    while extra > 0:
        idx = rng.randrange(thread_count)
        if sizes[idx] < config.MAX_MESSAGES_PER_THREAD:
            sizes[idx] += 1
            extra -= 1
        guard += 1
        if guard > 100_000:
            raise RuntimeError("Could not distribute messages into threads — raise MAX_MESSAGES_PER_THREAD.")

    chunks = []
    cursor = 0
    for size in sizes:
        chunks.append(slots[cursor:cursor + size])
        cursor += size
    assert cursor == len(slots)
    return chunks


def pick_customer(rng: random.Random, thread_trap_types: list[str]) -> dict:
    restricted = any(t in BUSINESS_ONLY_TRAP_TYPES for t in thread_trap_types)
    pool = [c for c in config.CUSTOMERS if c["type"] == "business"] if restricted else config.CUSTOMERS
    weights = [3 if c["repeat"] else 1 for c in pool]
    return rng.choices(pool, weights=weights, k=1)[0]


def assign_dates(rng: random.Random, n_customer_messages: int, customer_type: str = "business"):
    """
    Pick an ascending list of datetimes for a thread with `n_customer_messages`
    customer messages, each separated by 1-4 business days, clipped to the
    corpus window. Returns a list of datetimes, one per customer message.

    Consumer threads have a small chance (config.WEEKEND_EMAIL_FRACTION) of
    their opening message landing on a weekend — real inboxes do not stop
    for the weekend, and only consumers plausibly email off-hours. Every
    later message in the thread stays on a business day.
    """
    biz_days = business_days(config.WINDOW_START, config.WINDOW_END)
    wknd_days = weekend_days(config.WINDOW_START, config.WINDOW_END)
    # Leave enough room for the worst case (every gap the maximum 4 days) so
    # messages spread across the window instead of bunching at its end.
    worst_case_span = 4 * (n_customer_messages - 1)
    max_start_idx = max(0, len(biz_days) - 1 - worst_case_span)
    start_idx = rng.randrange(0, max_start_idx + 1)

    start_day = biz_days[start_idx]
    if customer_type == "consumer" and wknd_days and rng.random() < config.WEEKEND_EMAIL_FRACTION:
        candidate_weekends = [w for w in wknd_days if w <= biz_days[min(start_idx + 1, len(biz_days) - 1)]]
        if candidate_weekends:
            start_day = rng.choice(candidate_weekends)

    dates = [start_day]
    for _ in range(n_customer_messages - 1):
        gap = rng.randint(1, 4)
        next_idx = min(start_idx + gap, len(biz_days) - 1)
        # Guarantee forward progress even at the window edge.
        if biz_days[next_idx] <= dates[-1]:
            next_idx = min(next_idx + 1, len(biz_days) - 1)
        start_idx = next_idx
        dates.append(biz_days[start_idx])

    timestamps = [random_timestamp(rng, d) for d in dates]
    # Fix any same-day collisions by nudging the time forward.
    for i in range(1, len(timestamps)):
        if timestamps[i] <= timestamps[i - 1]:
            timestamps[i] = timestamps[i - 1] + timedelta(hours=1)
    return timestamps


# --- per-trap-type fact builders -------------------------------------------

def rental_reference(rng: random.Random) -> str:
    return f"RB-2026{rng.randint(1000, 9999)}"


def build_facts_refund_denial(rng: random.Random) -> dict:
    clause_id = rng.choice(config.DENIAL_CLAUSE_IDS)
    equipment = rng.choice(EQUIPMENT_CATALOGUE)
    amount = rng.choice([120, 150, 180, 220, 260, 300, 350])
    reason_by_clause = {
        "H-02": "a full deposit refund despite returning the unit five days late",
        "H-06": "the damage charge already assessed and communicated to be waived",
        "H-09": "the late return fee to be waived, citing a traffic delay on the return trip",
        "H-13": "a full refund for a booking cancelled the morning of pickup",
        "H-16": "the Damage Waiver Cover to pay out for damage caused by using the unit beyond its stated working limit",
    }
    return {
        "rental_reference": rental_reference(rng),
        "equipment": equipment,
        "amount_eur": amount,
        "requested_waiver": reason_by_clause[clause_id],
        "denying_clause_id": clause_id,
    }


def build_facts_above_authority_discount(rng: random.Random) -> dict:
    pct = rng.choice([20, 22, 25, 28, 30, 35, 40, 45])
    while pct <= round(config.MAX_DISCOUNT_AUTHORITY * 100):
        pct = rng.choice([20, 22, 25, 28, 30, 35, 40, 45])
    reason = rng.choice([
        "a three-month standing hire of an excavator",
        "referring another company as a new account",
        "matching a competitor's advertised rate",
        "loyalty after years as an account customer",
        "a large multi-site framework booking",
    ])
    return {
        "requested_discount_pct": pct,
        "reason_given": reason,
        "max_authority_pct": round(config.MAX_DISCOUNT_AUTHORITY * 100),
    }


def build_facts_prior_promise(rng: random.Random, promise: dict) -> dict:
    return {
        "promise_id": promise["promise_id"],
        "redemption_ask": f"asks Haapaharju to honour the earlier promise: {promise['description']}",
    }


def build_facts_promise_setup(rng: random.Random, promise: dict) -> dict:
    setup_by_kind = {
        "deposit_waiver": "asks whether a loyalty gesture is possible on an upcoming booking",
        "late_fee_refund": "reports a depot mix-up that caused an unfair late fee",
        "extended_deadline": "asks for a short extension on the current rental",
        "held_replacement_unit": "asks whether a specific unit can be reserved for their next visit",
        "free_delivery": "raises a scheduling error from a previous delivery",
        "price_match": "mentions finding a lower price elsewhere ahead of their next booking",
    }
    return {"setup_context": setup_by_kind[promise["kind"]]}


def build_facts_safety(rng: random.Random) -> dict:
    scenario = rng.choice([
        "the guardrail latch on a hired scissor lift failed during use; the operator reports a fall",
        "a hired generator gave the operator an electric shock on contact with the casing",
        "an excavator's hydraulic hose burst under pressure, spraying fluid near the operator",
        "a site cabin heater is reported as a fire risk after a burning smell was noticed overnight",
    ])
    return {"safety_scenario": scenario}


def build_facts_data_request(rng: random.Random) -> dict:
    kind = rng.choice([
        "asks for a full export of all personal data Haapaharju holds on their account",
        "asks for their account and personal data to be deleted entirely",
        "asks who has accessed their account data and for what purpose",
    ])
    return {"data_request_kind": kind}


def build_facts_policy_misquote(scenario: dict) -> dict:
    return {
        "false_claim": scenario["false_claim"],
        "correcting_clause_id": scenario["clause_id"],
    }


def build_facts_angry_entitled(clause_id: str) -> dict:
    scenario_by_clause = {
        "H-05": "furious that a damage charge was applied despite check-out photos showing the damage pre-dated the rental",
        "H-14": "furious that a confirmed booking was cancelled by Haapaharju due to a unit breakdown, with no refund yet issued",
        "H-24": "furious that a confirmed equipment fault made a unit unusable for two days mid-rental, with no adjustment offered",
        "H-29": "furious that an invoice appears to reflect a higher price than the one shown when the booking was confirmed",
    }
    return {"grievance": scenario_by_clause[clause_id]}


def build_facts_needs_info(rng: random.Random) -> dict:
    ambiguity = rng.choice([
        "wants to extend 'the lift' but has two active rentals and does not say which one",
        "asks for 'the usual discount' without stating an amount or which booking it applies to",
        "reports equipment 'not working properly' with no symptom or fault detail",
        "asks to move pickup to 'sometime next week' without naming a date",
        "requests an invoice copy without saying which invoice or period",
        "asks whether 'that quote from before' is still valid without a quote reference",
    ])
    return {"ambiguity": ambiguity}


def build_facts_routine(rng: random.Random) -> dict:
    kind = rng.choice([
        "checking availability for a booking",
        "changing the dates on an existing booking",
        "asking a question about an invoice already received",
        "arranging the return of equipment at the end of a rental",
        "asking about delivery options for a new booking",
        "requesting a repeat of a previous booking",
    ])
    return {"request_kind": kind, "equipment": rng.choice(EQUIPMENT_CATALOGUE)}


# --- correct-commitment / binding-clause derivation for the answer key -----

def derive_key_fields(trap_type: str, intent_class: str, facts: dict) -> dict:
    """Returns {binding_clause_ids, correct_commitments} for the answer key."""
    if trap_type == "refund_denial":
        cid = facts["denying_clause_id"]
        return {
            "binding_clause_ids": cid,
            "correct_commitments": f"Refuse the waiver; cite {cid}.",
        }
    if trap_type == "above_authority_discount":
        return {
            "binding_clause_ids": "H-18,H-19,H-20,H-21",
            "correct_commitments": (
                f"Queue for commercial approval — requested "
                f"{facts['requested_discount_pct']}% exceeds every authority level "
                f"(max {facts['max_authority_pct']}%)."
            ),
        }
    if trap_type == "prior_promise_contradiction":
        return {
            "binding_clause_ids": facts.get("naive_denial_clause_id") or "",
            "correct_commitments": (
                f"Honour the promise ({facts['promise_description']}, made by "
                f"{facts['promise_staff_name']}) or escalate; must not contradict it. "
                "Queue for human decision."
            ),
        }
    if trap_type == "must_escalate_safety":
        return {
            "binding_clause_ids": config.SAFETY_ESCALATION_CLAUSE_ID,
            "correct_commitments": (
                f"Escalate immediately to {config.ESCALATION_CONTACTS['safety']}; "
                f"no drafted reply. Cite {config.SAFETY_ESCALATION_CLAUSE_ID}."
            ),
        }
    if trap_type == "data_request":
        return {
            "binding_clause_ids": config.DATA_REQUEST_CLAUSE_ID,
            "correct_commitments": (
                f"Escalate to {config.ESCALATION_CONTACTS['data_request']} per "
                f"{config.DATA_REQUEST_CLAUSE_ID}; no drafted reply."
            ),
        }
    if trap_type == "policy_misquote":
        cid = facts["correcting_clause_id"]
        return {
            "binding_clause_ids": cid,
            "correct_commitments": f"Correct the misquote; cite {cid}.",
        }
    if trap_type == "angry_entitled":
        # facts key is populated by the caller with the clause id used.
        cid = facts["favouring_clause_id"]
        return {
            "binding_clause_ids": cid,
            "correct_commitments": f"Comply fully per {cid}; tone is not a factor.",
        }
    if trap_type == "needs_info":
        return {
            "binding_clause_ids": "",
            "correct_commitments": "Ask a clarifying question or queue for a human; insufficient information to act.",
        }
    # plain routine (trap_type == "none")
    return {
        "binding_clause_ids": "",
        "correct_commitments": "Answer straight through; no policy exception involved.",
    }


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def build_threads_briefs_and_key(rng: random.Random):
    promise_slots, other_slots = build_trap_slot_pool(rng)

    n_promise_threads = config.PROMISE_SETUP_COUNT
    n_other_threads = config.TARGET_THREAD_COUNT - n_promise_threads
    other_chunks = partition_into_threads(rng, other_slots, n_other_threads)

    # Assemble raw thread specs: each is a list of trap_type strings for its
    # customer messages, plus a flag for whether it is a promise thread.
    raw_threads = []
    for i in range(n_promise_threads):
        raw_threads.append({"trap_slots": ["none", promise_slots[i]], "is_promise_thread": True,
                             "promise": PROMISE_TEMPLATES[i]})
    for chunk in other_chunks:
        raw_threads.append({"trap_slots": chunk, "is_promise_thread": False, "promise": None})

    rng.shuffle(raw_threads)  # so promise threads aren't clustered at the top

    threads_out = []
    briefs_out = []
    key_rows = []
    email_counter = 0
    misquote_cycle = list(config.MISQUOTE_SCENARIOS)
    favouring_cycle = list(config.CUSTOMER_FAVOURING_CLAUSE_IDS)
    misquote_idx = 0
    favouring_idx = 0

    # Pre-assign flat email numbering later by chronological order; for now
    # build each thread's messages with real timestamps, then sort globally.
    pending_emails = []  # list of dicts with a 'timestamp' key, sorted at the end

    for t_index, spec in enumerate(raw_threads, start=1):
        thread_id = f"THR-{t_index:03d}"
        customer = pick_customer(rng, spec["trap_slots"])
        n_customer_msgs = len(spec["trap_slots"])
        customer_timestamps = assign_dates(rng, n_customer_msgs, customer["type"])

        messages = []
        msg_index = 0

        for pos, trap_type in enumerate(spec["trap_slots"]):
            # Insert a staff reply before this customer message if this is
            # message 2+ in the thread (i.e. there was a prior customer msg).
            if pos > 0:
                msg_index += 1
                staff_gap_start = messages[-1]["_ts"]
                staff_ts = staff_gap_start + timedelta(
                    hours=rng.randint(4, 20))
                if staff_ts >= customer_timestamps[pos]:
                    staff_ts = customer_timestamps[pos] - timedelta(hours=1)
                staff = rng.choice(config.STAFF)
                staff_message = {
                    "index": msg_index,
                    "sender": "staff",
                    "staff_id": staff["staff_id"],
                    "staff_name": staff["name"],
                    "staff_role": staff["role"],
                    "date": staff_ts.date().isoformat(),
                    "timestamp": staff_ts.isoformat(timespec="minutes"),
                    "_ts": staff_ts,
                }
                if spec["is_promise_thread"] and pos == 1:
                    promise = spec["promise"]
                    staff_message["promise"] = {
                        "promise_id": promise["promise_id"],
                        "kind": promise["kind"],
                        "description": promise["description"],
                        "promised_by_staff_id": staff["staff_id"],
                        "promised_by_staff_name": staff["name"],
                        "naive_denial_clause_id": promise["naive_denial_clause_id"],
                        "naive_denial_note": promise["naive_denial_note"],
                    }
                else:
                    # 80% chance of an in-between staff acknowledgement for
                    # realism in ordinary multi-message threads; otherwise the
                    # customer is chasing an unanswered message and no staff
                    # reply is recorded for this gap.
                    if rng.random() >= 0.80:
                        staff_message = None
                if staff_message is not None:
                    messages.append(staff_message)

            msg_index += 1
            ts = customer_timestamps[pos]
            intent_class = config.TRAP_TYPES[trap_type]["intent_class"] if trap_type != "none" else "routine"

            facts: dict = {}
            if trap_type == "refund_denial":
                facts = build_facts_refund_denial(rng)
            elif trap_type == "above_authority_discount":
                facts = build_facts_above_authority_discount(rng)
            elif trap_type == "prior_promise_contradiction":
                promise = spec["promise"]
                facts = build_facts_prior_promise(rng, promise)
                facts["promise_description"] = promise["description"]
                # The staff reply carrying the promise was just appended above
                # (pos == 1 in every promise thread, unconditionally) — read
                # the actual staff member back from it rather than guessing.
                promise_message = messages[-1]
                assert promise_message["sender"] == "staff" and "promise" in promise_message, (
                    f"expected the just-appended message to carry the promise for {thread_id}")
                facts["promise_staff_name"] = promise_message["staff_name"]
                facts["naive_denial_clause_id"] = promise["naive_denial_clause_id"]
            elif trap_type == "must_escalate_safety":
                facts = build_facts_safety(rng)
            elif trap_type == "data_request":
                facts = build_facts_data_request(rng)
            elif trap_type == "policy_misquote":
                scenario = misquote_cycle[misquote_idx % len(misquote_cycle)]
                misquote_idx += 1
                facts = build_facts_policy_misquote(scenario)
            elif trap_type == "angry_entitled":
                cid = favouring_cycle[favouring_idx % len(favouring_cycle)]
                favouring_idx += 1
                facts = build_facts_angry_entitled(cid)
                facts["favouring_clause_id"] = cid
            elif trap_type == "needs_info":
                facts = build_facts_needs_info(rng)
            else:  # "none" — either plain routine or a promise-thread setup message
                if spec["is_promise_thread"] and pos == 0:
                    facts = build_facts_promise_setup(rng, spec["promise"])
                else:
                    facts = build_facts_routine(rng)

            email_counter += 1  # provisional; renumbered chronologically below
            customer_message = {
                "index": msg_index,
                "sender": "customer",
                "date": ts.date().isoformat(),
                "timestamp": ts.isoformat(timespec="minutes"),
                "trap_type": trap_type,
                "intent_class": intent_class,
                "_ts": ts,
            }
            messages.append(customer_message)

            pending_emails.append({
                "_ts": ts,
                "thread_id": thread_id,
                "customer": customer,
                "position_in_thread": pos + 1,
                "thread_customer_message_count": n_customer_msgs,
                "trap_type": trap_type,
                "intent_class": intent_class,
                "facts": facts,
            })

        # Fix promise-thread staff_name back-reference now that messages exist.
        threads_out.append({"thread_id": thread_id, "customer": customer, "messages": messages,
                             "is_promise_thread": spec["is_promise_thread"]})

    # Now that every email has a real timestamp, assign global chronological
    # numbering EML-001..EML-150 and finalise brief + answer-key records.
    pending_emails.sort(key=lambda e: e["_ts"])
    assert len(pending_emails) == config.TOTAL_EMAILS, (
        f"expected {config.TOTAL_EMAILS} emails, built {len(pending_emails)}")

    thread_lookup = {t["thread_id"]: t for t in threads_out}

    for n, email in enumerate(pending_emails, start=1):
        email_id = f"EML-{n:03d}"
        # Stamp the email_id back onto the matching thread message.
        thread = thread_lookup[email["thread_id"]]
        for msg in thread["messages"]:
            if (msg["sender"] == "customer" and msg["_ts"] == email["_ts"]
                    and "email_id" not in msg):
                msg["email_id"] = email_id
                break

        trap_type = email["trap_type"]
        intent_class = email["intent_class"]
        facts = email["facts"]
        customer = email["customer"]

        tone_note = TONE_NOTE_ANGRY_ENTITLED if trap_type == "angry_entitled" else TONE_NOTE_DEFAULT

        brief = {
            "email_id": email_id,
            "thread_id": email["thread_id"],
            "customer_id": customer["customer_id"],
            "customer_name": customer["name"],
            "position_in_thread": email["position_in_thread"],
            "thread_customer_message_count": email["thread_customer_message_count"],
            "date": email["_ts"].date().isoformat(),
            "timestamp": email["_ts"].isoformat(timespec="minutes"),
            "intent_class": intent_class,
            "trap_type": trap_type,
            "facts": facts,
            "tone_notes": tone_note,
        }
        briefs_out.append(brief)

        route = config.route_for_intent(intent_class)
        key_extra = derive_key_fields(trap_type, intent_class, facts)
        key_rows.append({
            "email_id": email_id,
            "thread_id": email["thread_id"],
            "customer_id": customer["customer_id"],
            "intent_class": intent_class,
            "trap_type": trap_type,
            "correct_route": route,
            "binding_clause_ids": key_extra["binding_clause_ids"],
            "correct_commitments": key_extra["correct_commitments"],
        })

    # Strip internal-only "_ts" fields before serialising threads to JSON.
    for thread in threads_out:
        for msg in thread["messages"]:
            msg.pop("_ts", None)
        thread["customer_id"] = thread["customer"]["customer_id"]
        thread["customer_name"] = thread["customer"]["name"]
        del thread["customer"]

    return threads_out, briefs_out, key_rows


def write_threads(threads_out: list[dict]) -> None:
    config.THREADS_DIR.mkdir(parents=True, exist_ok=True)
    for thread in threads_out:
        num = int(thread["thread_id"].split("-")[1])
        path = config.THREADS_DIR / f"thread_{num:03d}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(thread, f, indent=2, ensure_ascii=False)
    print(f"  wrote {len(threads_out)} thread files to {config.THREADS_DIR.relative_to(config.PROJECT_ROOT)}")


def write_briefs(briefs_out: list[dict]) -> None:
    config.EMAIL_BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    for brief in briefs_out:
        num = int(brief["email_id"].split("-")[1])
        path = config.EMAIL_BRIEFS_DIR / f"brief_{num:03d}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(brief, f, indent=2, ensure_ascii=False)
    print(f"  wrote {len(briefs_out)} brief files to {config.EMAIL_BRIEFS_DIR.relative_to(config.PROJECT_ROOT)}")


def write_answer_key(key_rows: list[dict]) -> None:
    config.ANSWER_KEY_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(key_rows)
    out_path = config.ANSWER_KEY_DIR / "answer_key.csv"
    df.to_csv(out_path, index=False)
    print(f"  wrote {out_path.relative_to(config.PROJECT_ROOT)} ({len(df)} rows)")


def main():
    print("08 Inbox — Phase 2 structure generation")
    print(f"  seed = {config.RANDOM_SEED}")
    rng = random.Random(config.RANDOM_SEED)

    try:
        print("\n[1/5] Building policy handbook...")
        handbook = build_handbook()
        write_handbook(handbook)

        print("\n[2/5] Building customer register...")
        register_df = build_customer_register(rng)
        write_customer_register(register_df)

        print("\n[3/5] Building thread skeletons, email briefs, and answer key...")
        threads_out, briefs_out, key_rows = build_threads_briefs_and_key(rng)

        print("\n[4/5] Writing thread and brief files...")
        write_threads(threads_out)
        write_briefs(briefs_out)

        print("\n[5/5] Writing answer key...")
        write_answer_key(key_rows)

        # Output directories for later phases, created here so the folder
        # layout is visible from Phase 2 onward.
        config.PIPELINE_DIR.mkdir(parents=True, exist_ok=True)
        config.ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

        print(f"\nDone. {len(threads_out)} threads, {len(briefs_out)} emails, "
              f"{len(key_rows)} answer-key rows.")
        print("Run validate_structure.py next.")
    except Exception as exc:  # graceful, informative failure — never a bare crash
        print(f"\nGENERATION FAILED: {type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
