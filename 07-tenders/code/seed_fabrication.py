"""Phase 2b seeded fabrication augmentation for Project 7 (Tenders).

CLOSES A DESIGN GAP found by grep after Phase 2 finished and BEFORE any
Arm A prose existed.
The pre-registration expects "fabricated claims present in >= 25% of Arm A
attempts", but the Phase 2 attempt briefs (`data/attempt_briefs/*.json`)
carried no fabrication signal at all -- grepping "fabricat" across every
attempt brief returned nothing. Left as-is, that would hand fabrication to
the Phase 3 prose agent's improvisation, which violates the pattern
used in every other case study: deterministic Python decides
STRUCTURE and outcomes; LLM agents only dramatise prose consistent with a
brief they may not deviate from. `build_attempt_brief()` in
`generate_structure.py` already does this for requirement engagement
(engaged/skimmed); this script does the equivalent for fabrication and
augments the same attempt-brief files in place.

THE MECHANISM (the realistic one, not "the persona lies"): a chatbot
plausibly drafts an overclaim when asked to summarise Visakoivu's
eligibility, track record, capacity, or capability, and a persona who does
not cross-check the draft against the facts library pastes it in unverified.
Fabrication enters via unverified assistant output, not deliberate lying --
consistent with the "habits, never mockery" register.

Two fields are added to each of the 64 attempt briefs, IN PLACE, preserving
every existing field:

  checks_facts_library : bool
      Whether this persona, on this attempt, cross-checks claims against
      the facts library before submitting. Driven by the persona's
      `eligibility_scrutiny` and `time_pressure_decay` traits (already in
      config.py -- eligibility_scrutiny is literally described there as
      "checking a certification or reference threshold against the facts
      library", the exact cross-reference step this field measures), via
      one seeded coin-flip per attempt. No persona-specific hardcoding.

  fabrication_events : list[dict]
      Empty when `checks_facts_library` is true. Otherwise, a further
      seeded coin-flip decides whether this attempt's draft carries exactly
      one concrete overclaim (kept to one per attempt for markability),
      chosen from four checkable mechanisms: invented_certification,
      inflated_reference, capacity_overclaim, uncited_capability. Every
      event carries `claimed_value`/`true_value` fields alongside its prose
      `instruction`, so `code/mark.py` (Phase 5) can check it mechanically
      against `company_facts.yaml` without parsing prose.

Fresh RNG stream: this script derives its draws from `config.RANDOM_SEED`
(7, unchanged) plus a distinct `FABRICATION_SALT`, folded in before any
tender/persona index -- so this script's coin-flips are statistically
independent of `generate_structure.py`'s engagement-model draws even though
both start from the same global seed, and re-running this script alone is
byte-for-byte deterministic.

This is a deliberate IN-PLACE augmentation of Phase 2 generated artifacts
(not source prose, not tender documents, not the answer key, not clause
maps) -- analogous in kind to the churn project's one-off repair tools, but
run BEFORE any Phase 3 Arm A prose exists, so pre-registration is intact:
nothing about what Phase 3 will write has been observed yet.

Run: python seed_fabrication.py         (after generate_structure.py)
Then: python validate_structure.py      (now also checks these two fields)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import yaml

import config

# ---------------------------------------------------------------------------
# Config block -- every fabrication-specific tunable lives here.
# ---------------------------------------------------------------------------

# A large, distinct salt folded into config.RANDOM_SEED (7) before any
# tender/persona index, so this script's RNG stream never collides with
# generate_structure.py's `deterministic_rng()` stream even on identical
# (tender_num, persona_num) inputs. Arbitrary but fixed -- changing it would
# change every downstream draw, so it is set once and never tuned per-run.
FABRICATION_SALT = 424_242_017

# --- checks_facts_library probability model ---------------------------
# p_check = clip(P_CHECK_INTERCEPT + P_CHECK_ELIGIBILITY_WEIGHT * eligibility_scrutiny
#                - P_CHECK_DECAY_WEIGHT * time_pressure_decay, 0.03, 0.97)
# Calibration note: drafted once
# against the population of 14 personas' already-existing (and already
# twice-recalibrated, see config.py) trait values, checked for directional
# agreement with the design's qualitative buckets (careful reader / sceptic /
# checklist-maker mostly true; paste-everything / deadline-panicker /
# confident generalist / delegator mostly false; the rest mixed), then
# accepted -- no persona-specific tuning, no look at any individual
# attempt's resulting fabrication_events before accepting.
P_CHECK_INTERCEPT = -0.35
P_CHECK_ELIGIBILITY_WEIGHT = 1.6
P_CHECK_DECAY_WEIGHT = 0.4

# --- fabrication-event probability, given checks_facts_library is False ---
# Calibration note: chosen so that, combined with the checks_facts_library
# model above, the POPULATION-level incidence across all 64 attempts lands
# structurally near the middle of the pre-registered >=25% expectation without
# hard-coding an exact count.
# Applied uniformly to every non-checking attempt; not tuned per attempt.
# First pass at 0.8 landed the seeded draw at 32/64 (50%) -- real coin-flip
# variance on a 38-attempt population, not a formula error -- which sits
# above the intended 30-45% band. Rescaled once, population-wide, before
# accepting (the same calibration discipline as config.py's engagement-model
# passes): never looked at any individual attempt's event before rescaling.
EVENT_PROBABILITY_GIVEN_NOT_CHECKING = 0.6

ALLOWED_EVENT_TYPES = (
    "invented_certification", "inflated_reference",
    "capacity_overclaim", "uncited_capability",
)

# Certifications a facilities/technical contractor like Visakoivu could
# plausibly be asked about but does not hold -- NMSB73710 is confirmed absent
# in company_facts.yaml; the other three are simply never mentioned there at
# all, which is equally sufficient grounds for "not held" (validated fresh
# against the facts library every time, never assumed).
CERT_FABRICATION_POOL = [
    {"code": "NMSB73710", "label": "NMSB 73710 information-security certification"},
    {"code": "NMSB78410", "label": "NMSB 78410 energy-management certification"},
    {"code": "NOHS61810", "label": "NOHS 61810 occupational health and safety certification"},
    {"code": "NMSB72230", "label": "NMSB 72230 business-continuity certification"},
]

# Reference-value inflation: multiply the real value_eur by a factor in this
# range (seeded), then round to the nearest 10,000 EUR -- the range keeps a
# comfortable margin above 1.0 so rounding can never accidentally produce a
# claimed value equal to (or below) the true one.
REFERENCE_INFLATION_FACTOR_RANGE = (1.25, 1.6)

# Staff-headcount inflation: same idea, smaller numbers so a coarser margin.
CAPACITY_INFLATION_FACTOR_RANGE = (1.3, 1.7)

# Capabilities with zero basis anywhere in the facts library. `keywords` are
# the substrings checked (case-insensitively) against a flattened dump of
# company_facts.yaml at validation time -- if any keyword is ever found
# there, the event is refused as accidentally true rather than fabricated.
CAPABILITY_POOL = [
    {"target_area": "nationwide_coverage",
     "claim_text": "a 24/7 nationwide emergency-response network, beyond its "
                    "Keski-Suomi service area",
     "keywords": ["nationwide", "valtakunnall", "koko suomess"]},
    {"target_area": "cybersecurity_team",
     "claim_text": "an in-house cybersecurity/OT-security auditing team for "
                    "building-automation systems",
     "keywords": ["cybersecurity", "cyber security", "tietoturva-audit", "security audit"]},
    {"target_area": "cleanroom_experience",
     "claim_text": "prior experience delivering hospital-grade cleanroom "
                    "HVAC installations",
     "keywords": ["cleanroom", "clean room", "puhdastila", "hospital-grade", "sairaalatas"]},
    {"target_area": "software_dev_team",
     "claim_text": "an in-house software development team building custom "
                    "building-automation integrations",
     "keywords": ["software development", "ohjelmistokehit"]},
    {"target_area": "datacenter_specialization",
     "claim_text": "a dedicated data-centre cooling specialisation unit",
     "keywords": ["data-centre", "data centre", "data center", "datakeskus"]},
]

CAPABILITY_BY_AREA = {c["target_area"]: c for c in CAPABILITY_POOL}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def log(message: str) -> None:
    """Progress print, flushed immediately so a long run stays legible."""
    print(f"[seed_fabrication] {message}", flush=True)


def tender_num(tender_id: str) -> int:
    return int(tender_id[1:])


def persona_num(persona_id: str) -> int:
    return int(persona_id[1:])


def deterministic_rng(*parts: int) -> np.random.Generator:
    """A fresh, reproducible RNG keyed off RANDOM_SEED plus FABRICATION_SALT
    plus salt parts -- statistically independent of generate_structure.py's
    `deterministic_rng()` (same global seed, different starting fold), so
    the two augmentation passes never share a coin-flip stream.
    """
    seed = config.RANDOM_SEED * 1_000_003 + FABRICATION_SALT
    for i, part in enumerate(parts):
        seed = seed * 1_000_003 + (i + 1) * 97 + part
    return np.random.default_rng(seed % (2**32 - 1))


def load_facts() -> dict:
    """Read company_facts.yaml fresh from disk -- never trust an in-memory
    dict, per the same discipline validate_structure.py already applies.
    """
    facts_path = config.FACTS_DIR / "company_facts.yaml"
    if not facts_path.exists():
        raise FileNotFoundError(
            f"missing {facts_path} -- run generate_structure.py first")
    with open(facts_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def flatten_facts_text(facts: dict) -> str:
    """One lowercase blob of every prose-bearing field in the facts library,
    for the uncited_capability keyword-absence guard.
    """
    parts = [facts["company"]["description"], facts["company"]["sector"]]
    for cert in facts["certifications"]:
        parts.append(cert["name_fi"])
    for ref in facts["reference_projects"]:
        parts.append(ref["client"])
        parts.append(ref["description"])
    return " ".join(parts).lower()


# ---------------------------------------------------------------------------
# checks_facts_library
# ---------------------------------------------------------------------------

def checks_facts_library_probability(persona: dict) -> float:
    """Seeded-model probability that this persona cross-checks claims
    against the facts library, from already-existing numeric traits.
    """
    traits = persona["traits"]
    p = (P_CHECK_INTERCEPT
         + P_CHECK_ELIGIBILITY_WEIGHT * traits["eligibility_scrutiny"]
         - P_CHECK_DECAY_WEIGHT * traits["time_pressure_decay"])
    return float(np.clip(p, 0.03, 0.97))


# ---------------------------------------------------------------------------
# Fabrication event construction (also used, read-only, by
# validate_structure.py via validate_event()).
# ---------------------------------------------------------------------------

def build_invented_certification_event(rng: np.random.Generator, facts: dict,
                                        persona_name: str) -> dict:
    held_codes = {c["code"] for c in facts["certifications"] if c["held"]}
    pool = [c for c in CERT_FABRICATION_POOL if c["code"] not in held_codes]
    choice = pool[int(rng.integers(0, len(pool)))]
    return {
        "type": "invented_certification",
        "target_area": choice["code"],
        "claimed_value": "held",
        "true_value": "not held",
        "instruction": (
            f"The chatbot draft plausibly asserts that Visakoivu holds a "
            f"valid {choice['label']} when answering an eligibility or "
            f"compliance question; {persona_name} pastes this into the "
            f"response without checking it against the facts library. "
            f"Visakoivu does not hold this certification -- the draft "
            f"claims {choice['code']}, not held (see company_facts.yaml, "
            f"certifications)."),
    }


def build_inflated_reference_event(rng: np.random.Generator, facts: dict,
                                    persona_name: str) -> dict:
    refs = facts["reference_projects"]
    ref = refs[int(rng.integers(0, len(refs)))]
    lo, hi = REFERENCE_INFLATION_FACTOR_RANGE
    factor = float(rng.uniform(lo, hi))
    claimed = int(round(ref["value_eur"] * factor / 10_000) * 10_000)
    assert claimed > ref["value_eur"], (
        f"{ref['id']}: inflated value {claimed} did not exceed actual "
        f"{ref['value_eur']} -- widen REFERENCE_INFLATION_FACTOR_RANGE")
    return {
        "type": "inflated_reference",
        "target_area": ref["id"],
        "claimed_value": claimed,
        "true_value": ref["value_eur"],
        "instruction": (
            f"The chatbot draft plausibly inflates the contract value of "
            f"reference project {ref['id']} ({ref['client']}) to "
            f"{claimed:,} EUR when summarising Visakoivu's track record; "
            f"{persona_name} pastes this into the response without "
            f"checking it against the facts library. The actual contract "
            f"value on file is {ref['value_eur']:,} EUR (see "
            f"company_facts.yaml, reference_projects, {ref['id']})."),
    }


def build_capacity_overclaim_event(rng: np.random.Generator, facts: dict,
                                    persona_name: str) -> dict:
    disciplines = list(facts["staff_by_discipline"].keys())
    discipline = disciplines[int(rng.integers(0, len(disciplines)))]
    actual = facts["staff_by_discipline"][discipline]
    lo, hi = CAPACITY_INFLATION_FACTOR_RANGE
    factor = float(rng.uniform(lo, hi))
    claimed = int(round(actual * factor))
    assert claimed > actual, (
        f"{discipline}: inflated headcount {claimed} did not exceed actual "
        f"{actual} -- widen CAPACITY_INFLATION_FACTOR_RANGE")
    return {
        "type": "capacity_overclaim",
        "target_area": discipline,
        "claimed_value": claimed,
        "true_value": actual,
        "instruction": (
            f"The chatbot draft plausibly overstates Visakoivu's "
            f"{discipline} staff headcount as {claimed} when answering a "
            f"capacity or resourcing question; {persona_name} pastes this "
            f"into the response without checking it against the facts "
            f"library. The actual headcount on file is {actual} "
            f"{discipline} staff (see company_facts.yaml, "
            f"staff_by_discipline)."),
    }


def build_uncited_capability_event(rng: np.random.Generator, facts: dict,
                                    persona_name: str) -> dict:
    choice = CAPABILITY_POOL[int(rng.integers(0, len(CAPABILITY_POOL)))]
    return {
        "type": "uncited_capability",
        "target_area": choice["target_area"],
        "claimed_value": choice["claim_text"],
        "true_value": None,
        "instruction": (
            f"The chatbot draft plausibly asserts that Visakoivu has "
            f"{choice['claim_text']} when answering a capability question; "
            f"{persona_name} pastes this into the response without "
            f"checking it against the facts library. No basis for this "
            f"claim exists anywhere in company_facts.yaml."),
    }


EVENT_BUILDERS = {
    "invented_certification": build_invented_certification_event,
    "inflated_reference": build_inflated_reference_event,
    "capacity_overclaim": build_capacity_overclaim_event,
    "uncited_capability": build_uncited_capability_event,
}


def build_fabrication_event(rng: np.random.Generator, facts: dict,
                             persona_name: str) -> dict:
    event_type = ALLOWED_EVENT_TYPES[int(rng.integers(0, len(ALLOWED_EVENT_TYPES)))]
    event = EVENT_BUILDERS[event_type](rng, facts, persona_name)
    errors = validate_event(event, facts)
    if errors:
        raise ValueError(f"freshly built fabrication event failed its own "
                          f"guard: {errors}")
    return event


# ---------------------------------------------------------------------------
# The no-true-fact guard -- reusable by this script and by
# validate_structure.py (imported from there).
# ---------------------------------------------------------------------------

def validate_event(event: dict, facts: dict) -> list[str]:
    """Return a list of error strings (empty if the event is clean). Checks
    that this fabrication event does NOT accidentally coincide with a true
    fact in `facts` (the company_facts.yaml dict, loaded fresh from disk).
    """
    errors: list[str] = []
    etype = event.get("type")
    if etype not in ALLOWED_EVENT_TYPES:
        return [f"unknown fabrication event type {etype!r}"]

    if etype == "invented_certification":
        held_codes = {c["code"] for c in facts["certifications"] if c["held"]}
        if event["target_area"] in held_codes:
            errors.append(
                f"invented_certification targets {event['target_area']!r}, "
                f"which Visakoivu genuinely holds per company_facts.yaml -- "
                f"this would not be a fabrication")

    elif etype == "inflated_reference":
        ref = next((p for p in facts["reference_projects"]
                    if p["id"] == event["target_area"]), None)
        if ref is None:
            errors.append(f"inflated_reference targets unknown reference "
                          f"project id {event['target_area']!r}")
        else:
            if event.get("true_value") != ref["value_eur"]:
                errors.append(
                    f"inflated_reference true_value={event.get('true_value')} "
                    f"does not match company_facts.yaml's {ref['value_eur']} "
                    f"for {ref['id']}")
            if not (event.get("claimed_value", 0) > ref["value_eur"]):
                errors.append(
                    f"inflated_reference claimed_value="
                    f"{event.get('claimed_value')} does not exceed the "
                    f"actual value {ref['value_eur']} for {ref['id']} -- "
                    f"not an overclaim")

    elif etype == "capacity_overclaim":
        actual = facts["staff_by_discipline"].get(event["target_area"])
        if actual is None:
            errors.append(f"capacity_overclaim targets unknown discipline "
                          f"{event['target_area']!r}")
        else:
            if event.get("true_value") != actual:
                errors.append(
                    f"capacity_overclaim true_value={event.get('true_value')} "
                    f"does not match company_facts.yaml's {actual} for "
                    f"{event['target_area']}")
            if not (event.get("claimed_value", 0) > actual):
                errors.append(
                    f"capacity_overclaim claimed_value="
                    f"{event.get('claimed_value')} does not exceed the "
                    f"actual headcount {actual} for {event['target_area']} "
                    f"-- not an overclaim")

    elif etype == "uncited_capability":
        pool_entry = CAPABILITY_BY_AREA.get(event["target_area"])
        if pool_entry is None:
            errors.append(f"uncited_capability targets unknown target_area "
                          f"{event['target_area']!r}")
        else:
            blob = flatten_facts_text(facts)
            for kw in pool_entry["keywords"]:
                if kw.lower() in blob:
                    errors.append(
                        f"uncited_capability {event['target_area']!r} keyword "
                        f"{kw!r} unexpectedly appears in company_facts.yaml "
                        f"-- this claim would coincide with a true fact")

    return errors


# ---------------------------------------------------------------------------
# Per-attempt augmentation
# ---------------------------------------------------------------------------

def augment_attempt(path: Path, facts: dict) -> tuple[bool, list[dict]]:
    """Load one attempt brief, compute and write its two new fields in
    place, and return (checks_facts_library, fabrication_events) for the
    caller's summary statistics.
    """
    with open(path, "r", encoding="utf-8") as fh:
        attempt = json.load(fh)

    tid, pid = attempt["tender_id"], attempt["persona_id"]
    persona = config.PERSONA_BY_ID[pid]
    persona_name = attempt["persona_name"]

    rng_check = deterministic_rng(tender_num(tid), persona_num(pid), 1)
    rng_event = deterministic_rng(tender_num(tid), persona_num(pid), 2)
    rng_detail = deterministic_rng(tender_num(tid), persona_num(pid), 3)

    p_check = checks_facts_library_probability(persona)
    checks_facts_library = bool(rng_check.random() < p_check)

    fabrication_events: list[dict] = []
    if not checks_facts_library:
        if rng_event.random() < EVENT_PROBABILITY_GIVEN_NOT_CHECKING:
            fabrication_events = [build_fabrication_event(rng_detail, facts, persona_name)]

    attempt["checks_facts_library"] = checks_facts_library
    attempt["fabrication_events"] = fabrication_events

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(attempt, fh, ensure_ascii=False, indent=2)

    return checks_facts_library, fabrication_events


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not config.ATTEMPT_BRIEFS_DIR.exists():
        raise FileNotFoundError(
            f"missing {config.ATTEMPT_BRIEFS_DIR} -- run generate_structure.py "
            f"(and, if needed, build_clause_maps.py / validate_corpus.py) first")

    log(f"loading facts library from {config.FACTS_DIR / 'company_facts.yaml'}")
    facts = load_facts()

    log("loading assignment_matrix.json to iterate attempts in a fixed order")
    with open(config.DATA_DIR / "assignment_matrix.json", "r", encoding="utf-8") as fh:
        assignment = json.load(fh)

    results: list[dict] = []
    n_seen = 0
    for tender in config.TENDERS:
        tid = tender["id"]
        for pid in assignment[tid]:
            path = config.ATTEMPT_BRIEFS_DIR / f"attempt_{tid[1:]}_{pid[1:]}.json"
            if not path.exists():
                raise FileNotFoundError(f"missing attempt brief {path}")
            checks, events = augment_attempt(path, facts)
            results.append({"tender_id": tid, "persona_id": pid,
                             "checks_facts_library": checks,
                             "n_events": len(events),
                             "event_types": [e["type"] for e in events]})
            n_seen += 1
    log(f"augmented {n_seen} attempt briefs in place with "
        f"checks_facts_library + fabrication_events")

    # --- diagnostic summary (visibility only -- validate_structure.py does
    #     the hard schema/guard checks; this mirrors generate_structure.py's
    #     own diagnostic block against the pre-registration) ---------------
    n_checking = sum(1 for r in results if r["checks_facts_library"])
    n_with_events = sum(1 for r in results if r["n_events"] > 0)
    pct_with_events = round(100 * n_with_events / len(results), 1)

    log("--- diagnostic summary vs the pre-registration (>=25% of Arm A attempts) ---")
    log(f"  checks_facts_library=True: {n_checking}/{len(results)} attempts")
    log(f"  attempts with >=1 fabrication event: {n_with_events}/{len(results)} "
        f"({pct_with_events}%)")

    by_persona: dict[str, dict] = {}
    for r in results:
        pid = r["persona_id"]
        slot = by_persona.setdefault(pid, {"checking": 0, "events": 0, "total": 0})
        slot["total"] += 1
        slot["checking"] += int(r["checks_facts_library"])
        slot["events"] += int(r["n_events"] > 0)
    log("  by persona (checks_facts_library count / attempts, events count / attempts):")
    for p in config.PERSONAS:
        pid = p["id"]
        slot = by_persona.get(pid, {"checking": 0, "events": 0, "total": 0})
        log(f"    {pid} {p['tagline']:<42} checks {slot['checking']}/{slot['total']}  "
            f"events {slot['events']}/{slot['total']}")

    type_counts: dict[str, int] = {}
    for r in results:
        for t in r["event_types"]:
            type_counts[t] = type_counts.get(t, 0) + 1
    log(f"  event-type distribution: {type_counts}")
    log("These are diagnostics on the generative model, not a gate: the "
        "actual pre-registered scoring happens at marking time against real Arm A drafts "
        "and is never retuned after the fact.")
    log("done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # graceful, informative failure
        print(f"[seed_fabrication] FAILED: {exc}", file=sys.stderr)
        raise
