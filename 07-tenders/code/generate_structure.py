"""Phase 2 deterministic structure generator for Project 7 (Tenders).

Builds, in order:
  1. The requirement inventory for all 16 tenders (data/answer_key/).
  2. The Visakoivu Oy facts library (data/facts/).
  3. Tender briefs for the Phase 3/4 prose agents (data/tender_briefs/).
  4. Persona attempt briefs with seeded engagement lists (data/attempt_briefs/).

Everything here is deterministic given RANDOM_SEED in config.py. No tender
prose, chat transcript, or draft language is generated -- this script
produces only the STRUCTURE (numbered requirements, traps, facts, and who
plausibly noticed what) that Phase 3/4 LLM agents will dramatise into
prose, per the Hapax core generation pattern: Python controls structure,
LLM agents write only prose and may never add or remove a planted signal.

Run: python generate_structure.py
Then: python validate_structure.py   (exits 1 on any coherence failure)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

import config


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def log(message: str) -> None:
    """Progress print, flushed immediately so a long run stays legible."""
    print(f"[generate_structure] {message}", flush=True)


def tender_num(tender_id: str) -> int:
    return int(tender_id[1:])


def persona_num(persona_id: str) -> int:
    return int(persona_id[1:])


def deterministic_rng(*parts: int) -> np.random.Generator:
    """A fresh, reproducible RNG keyed off RANDOM_SEED plus salt parts."""
    seed = config.RANDOM_SEED
    for i, part in enumerate(parts):
        seed = seed * 1_000_003 + (i + 1) * 97 + part
    return np.random.default_rng(seed % (2**32 - 1))


def largest_remainder_split(total: int, proportions: dict[str, float]) -> dict[str, int]:
    """Round `total` into integer buckets matching `proportions` exactly,
    using the largest-remainder method so the counts always sum to `total`.
    """
    raw = {k: total * p for k, p in proportions.items()}
    floors = {k: int(np.floor(v)) for k, v in raw.items()}
    remainder = total - sum(floors.values())
    # Hand out the leftover units to the buckets with the largest fractional
    # remainder, breaking ties by key order for determinism.
    fracs = sorted(raw.keys(), key=lambda k: (-(raw[k] - floors[k]), k))
    for k in fracs[:remainder]:
        floors[k] += 1
    assert sum(floors.values()) == total
    return floors


def cycle_pool(pool: list[str], count: int, rng: np.random.Generator) -> list[str]:
    """Return `count` items drawn from a shuffled copy of `pool`, wrapping
    around (with a fresh shuffle each lap) if `count` exceeds len(pool).
    Deterministic given `rng`.
    """
    out: list[str] = []
    while len(out) < count:
        lap = list(pool)
        rng.shuffle(lap)
        out.extend(lap)
    return out[:count]


# ---------------------------------------------------------------------------
# Step 1: requirement inventory per tender
# ---------------------------------------------------------------------------

def build_requirement_inventory(tender: dict, facts: dict) -> list[dict]:
    """Build the full numbered requirement list for one tender, with every
    trap this tender is designed to carry placed at an explicit slot.
    """
    tid = tender["id"]
    size_class = tender["size_class"]
    profile = config.SIZE_PROFILES[size_class]
    rng = deterministic_rng(tender_num(tid), 1)

    lo, hi = profile["n_range"]
    n_total = int(rng.integers(lo, hi + 1))

    n_annexes = profile["annexes"]
    annex_names = config.ANNEX_NAMES[n_annexes]

    # Reserve slots for this tender's traps before drawing the generic pool,
    # so the exact TRAP_TABLE counts are guaranteed regardless of rounding.
    traps = tender["traps"]
    n_trap_reqs = 0
    for code in traps:
        n_trap_reqs += 2 if code == "contradiction" else 1
    n_generic = n_total - n_trap_reqs
    assert n_generic > 0, f"{tid}: trap requirements exceed tender size"

    counts = largest_remainder_split(n_generic, config.TYPE_PROPORTIONS)
    # An eligibility_fail tender still needs its normal eligibility pool
    # requirements alongside the one designed failure, so no adjustment
    # needed there; the trap is simply an EXTRA eligibility requirement.

    # --- generic requirement text pools -------------------------------
    technical_texts = cycle_pool(config.TECHNICAL_TOPICS, counts["technical"], rng)
    commercial_texts = cycle_pool(config.COMMERCIAL_TOPICS, counts["commercial"], rng)
    form_texts = cycle_pool(config.FORM_TOPICS, counts["form"], rng)
    format_texts = cycle_pool(config.FORMAT_TOPICS, counts["format"], rng)
    eligibility_items = cycle_pool(
        [json.dumps(e, sort_keys=True) for e in config.ELIGIBILITY_POOL],
        counts["eligibility"], rng)
    eligibility_items = [json.loads(e) for e in eligibility_items]

    records: list[dict] = []
    rid = 0

    def add_record(req_type: str, text: str, location: str, *, trap_code: str | None = None,
                    trap_group: str | None = None, mentioned_once: bool = False,
                    eligibility_check: dict | None = None) -> dict:
        nonlocal rid
        rid += 1
        eligibility_pass = ""
        check_type = ""
        check_param = ""
        if eligibility_check is not None:
            check_type = eligibility_check["check_type"]
            check_param = eligibility_check["check_param"]
            eligibility_pass = config.ELIGIBILITY_CHECKS[check_type](facts, check_param)
        rec = {
            "tender_id": tid,
            "req_number": rid,  # temporary; renumbered after full ordering
            "req_id": f"{tid}-R{rid:03d}",
            "type": req_type,
            "location": location,
            "description": text,
            "trap_code": trap_code or "",
            "trap_group_id": trap_group or "",
            "mentioned_once": mentioned_once,
            "eligibility_check_type": check_type,
            "eligibility_check_param": check_param,
            "eligibility_pass": eligibility_pass,
            "correct_action": config.TRAP_CORRECT_ACTION.get(
                trap_code, "Answer normally" if req_type != "eligibility"
                else "Confirm compliance"),
        }
        records.append(rec)
        return rec

    # --- body eligibility requirements (generic pool, always pass) -----
    for item in eligibility_items:
        add_record("eligibility", item["text"], "body", eligibility_check=item)

    # --- body technical / commercial / form / format (generic pool) ----
    for text in technical_texts:
        add_record("technical", text, "body")
    for text in commercial_texts:
        add_record("commercial", text, "body")
    for text in form_texts:
        add_record("form", text, "body")
    for text in format_texts:
        add_record("format", text, "body")

    # --- now relocate a share of the generic body requirements into
    #     annexes, per type, so the document has real annex structure ----
    body_fraction = {"eligibility": 1.0, "technical": 0.70, "commercial": 0.75,
                      "form": 0.60, "format": 0.88}
    preferred_annex_index = {
        1: {"technical": 0, "commercial": 0, "form": 0, "format": 0},
        2: {"technical": 0, "commercial": 1, "form": 1, "format": 0},
        4: {"technical": 0, "commercial": 1, "form": 2, "format": 1},
    }[n_annexes]

    for req_type in ("technical", "commercial", "form", "format"):
        type_records = [r for r in records if r["type"] == req_type and r["location"] == "body"]
        n_keep_body = int(round(len(type_records) * body_fraction[req_type]))
        idx = rng.permutation(len(type_records))
        to_annex = [type_records[i] for i in idx[n_keep_body:]]
        annex_name = annex_names[preferred_annex_index[req_type]]
        for r in to_annex:
            r["location"] = f"annex:{annex_name}"

    # --- planted traps, explicit placement ------------------------------
    for code in traps:
        if code == "eligibility_fail":
            trap_item = config.ELIGIBILITY_TRAP_BY_TENDER[tid]
            add_record("eligibility", trap_item["text"], "body",
                       trap_code=code, eligibility_check=trap_item)
        elif code == "annex_disqualifier":
            annex_name = annex_names[0]  # the technical/most detailed annex
            text = ("Mikali tarjoaja ei pysty osoittamaan ymparivuorokautista "
                    "paivystysta Suomessa, tarjous hylataan riippumatta "
                    "hinnasta (ehdoton vaatimus, ks. liitteen kohta 3.2).")
            add_record("technical", text, f"annex:{annex_name}", trap_code=code)
        elif code == "hidden_form":
            annex_name = annex_names[-1]
            if tid in config.HIDDEN_FORM_TOPIC_OVERRIDE:
                # Explicit override (see config.py comment) -- bypasses the
                # independent RNG draw entirely for this tender, so no other
                # tender's RNG stream is affected.
                form_topic = config.HIDDEN_FORM_TOPIC_OVERRIDE[tid]
            else:
                form_topic = cycle_pool(config.FORM_TOPICS, 1, deterministic_rng(
                    tender_num(tid), 2))[0]
            # Self-defending coherence check: the buried "hidden" form must
            # not duplicate a form this tender already requires elsewhere
            # (body or annex) -- that duplication is exactly the T03 defect
            # this override exists to fix, and this guard stops it from
            # silently recurring for any tender in the future.
            existing_form_topics = {r["description"] for r in records if r["type"] == "form"}
            if form_topic in existing_form_topics:
                raise ValueError(
                    f"{tid}: hidden_form trap topic '{form_topic}' duplicates "
                    f"a form this tender already requires elsewhere -- pick a "
                    f"distinct HIDDEN_FORM_TOPIC_OVERRIDE entry in config.py")
            text = (f"[Mainittu vain kerran, ohimennen liitteen tekstikappaleessa] "
                    f"Tarjoukseen on liitettava myos: {form_topic}.")
            add_record("form", text, f"annex:{annex_name}", trap_code=code,
                       mentioned_once=True)
        elif code == "format_trap":
            format_topic = cycle_pool(config.FORMAT_TOPICS, 1, deterministic_rng(
                tender_num(tid), 3))[0]
            text = f"[Muotovaatimus] {format_topic}."
            add_record("format", text, "body", trap_code=code)
        elif code == "contradiction":
            pass  # handled below, once, after this loop (needs a stable
                  # tender-to-topic index computed across all trap codes)
        else:
            raise ValueError(f"unknown trap code {code}")

    # Contradiction traps need a stable topic-per-tender mapping (there are
    # exactly 3 contradiction tenders and 3 topics -- one each).
    contradiction_tenders = [t["id"] for t in config.TENDERS if "contradiction" in t["traps"]]
    if "contradiction" in traps:
        topic_index = contradiction_tenders.index(tid)
        topic = config.CONTRADICTION_TOPICS[topic_index]
        group_id = f"{tid}-CONTRA"
        req_type = "technical" if topic["topic"] == "response_time" else "commercial"
        annex_name = annex_names[min(1, len(annex_names) - 1)]
        add_record(req_type, topic["body_text"], "body",
                   trap_code="contradiction", trap_group=group_id)
        add_record(req_type, topic["annex_text"], f"annex:{annex_name}",
                   trap_code="contradiction", trap_group=group_id)

    # --- final document-order numbering ---------------------------------
    # Body first (eligibility, technical, commercial, form, format), then
    # each annex in turn (in the same type order within it).
    type_order = {"eligibility": 0, "technical": 1, "commercial": 2, "form": 3, "format": 4}

    def sort_key(r: dict) -> tuple:
        is_annex = r["location"].startswith("annex:")
        annex_rank = 0
        if is_annex:
            annex_rank = annex_names.index(r["location"].split("annex:", 1)[1]) + 1
        return (annex_rank, type_order[r["type"]], r["req_id"])

    records.sort(key=sort_key)
    for i, r in enumerate(records, start=1):
        r["req_number"] = i
        r["req_id"] = f"{tid}-R{i:03d}"

    assert len(records) == n_total, f"{tid}: expected {n_total} requirements, got {len(records)}"
    return records


# ---------------------------------------------------------------------------
# Step 2: facts library
# ---------------------------------------------------------------------------

def build_company_facts() -> dict:
    certifications = list(config.CERTIFICATIONS_HELD)
    for code in config.CERTIFICATIONS_NOT_HELD:
        certifications.append({"code": code, "name_fi": f"{code} (ei hallussa)",
                                "valid_until": None})
    facts = {
        "company": config.COMPANY,
        "certifications": [
            {**c, "held": c["code"] not in config.CERTIFICATIONS_NOT_HELD}
            for c in certifications
        ],
        "staff_by_discipline": config.STAFF_BY_DISCIPLINE,
        "insurances": config.INSURANCES,
        "financials": config.FINANCIALS,
        "reference_projects": config.REFERENCE_PROJECTS,
    }
    return facts


def assert_eligibility_consistency(all_requirements: list[dict], facts: dict) -> None:
    """Every eligibility requirement's stored eligibility_pass must match a
    fresh recomputation against the facts library, AND the aggregate
    bid/no-bid call this implies for each tender must match config's
    NO_BID_TENDERS list exactly (14 PASS-everywhere tenders, T11/T15 with
    a genuine failure). This is the design's load-bearing consistency
    requirement -- checked here at generation time and again, independently,
    in validate_structure.py.
    """
    by_tender: dict[str, list[dict]] = {}
    for r in all_requirements:
        if r["type"] == "eligibility":
            by_tender.setdefault(r["tender_id"], []).append(r)

    failing_tenders = []
    for tid, reqs in by_tender.items():
        for r in reqs:
            recomputed = config.ELIGIBILITY_CHECKS[r["eligibility_check_type"]](
                facts, r["eligibility_check_param"])
            assert recomputed == r["eligibility_pass"], (
                f"{r['req_id']}: stored eligibility_pass={r['eligibility_pass']} "
                f"but recomputation gives {recomputed}")
        if any(not r["eligibility_pass"] for r in reqs):
            failing_tenders.append(tid)

    assert sorted(failing_tenders) == sorted(config.NO_BID_TENDERS), (
        f"eligibility-driven no-bid tenders {sorted(failing_tenders)} do not "
        f"match the designed set {sorted(config.NO_BID_TENDERS)}")
    log(f"eligibility consistency OK -- genuine failures only on "
        f"{sorted(failing_tenders)}, all 14 other tenders pass every "
        f"eligibility requirement")


def render_company_facts_md(facts: dict) -> str:
    c = facts["company"]
    lines = [f"# {c['name']} -- company facts", "",
             "*Synthetic company profile, engineered for the Tender Workflow "
             "case study. In-world data available to both arms; not the "
             "answer key.*", "",
             f"{c['description']}", "",
             f"- Founded: {c['founded_year']}", f"- Employees: {c['employee_count']}",
             f"- Business ID: {c['business_id']}", f"- Sector: {c['sector']}", "",
             "## Certifications", ""]
    for cert in facts["certifications"]:
        status = "held" if cert["held"] else "NOT held"
        until = f", valid until {cert['valid_until']}" if cert["valid_until"] else ""
        lines.append(f"- **{cert['code']}** -- {cert['name_fi']} ({status}{until})")
    lines += ["", "## Staff by discipline", ""]
    for disc, n in facts["staff_by_discipline"].items():
        lines.append(f"- {disc}: {n}")
    lines += ["", "## Insurances", ""]
    for ins in facts["insurances"]:
        cover = f"{ins['cover_eur']:,} EUR" if ins["cover_eur"] else "statutory, uncapped"
        lines.append(f"- {ins['name_fi']} ({ins['kind']}): {cover}")
    lines += ["", "## Financials (three years)", "",
              "| Year | Revenue (EUR) | Operating profit (EUR) | Equity ratio | Balance sheet total (EUR) |",
              "|---|---|---|---|---|"]
    for f in facts["financials"]:
        lines.append(f"| {f['year']} | {f['revenue_eur']:,} | {f['operating_profit_eur']:,} "
                     f"| {f['equity_ratio_pct']}% | {f['balance_sheet_total_eur']:,} |")
    lines += ["", "## Reference projects", "",
              "| ID | Client | Type | Value (EUR) | Period | Description |",
              "|---|---|---|---|---|---|"]
    for p in facts["reference_projects"]:
        lines.append(f"| {p['id']} | {p['client']} | {p['client_type']} | "
                     f"{p['value_eur']:,} | {p['start']} to {p['end']} | {p['description']} |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 3: tender briefs (for Phase 3/4 prose agents)
# ---------------------------------------------------------------------------

def build_tender_brief(tender: dict, requirements: list[dict]) -> dict:
    tid = tender["id"]
    n_annexes = config.SIZE_PROFILES[tender["size_class"]]["annexes"]
    annex_names = config.ANNEX_NAMES[n_annexes]
    tone = ("formal public-procurement register, referencing eligibility and "
            "evaluation criteria in the manner of a Finnish hankintailmoitus "
            "(loosely -- no real portal or authority is named)"
            if tender["sector"] == "public" else
            "brisker private-sector RFQ register, still formal but shorter "
            "on procedural boilerplate")
    placements = []
    for r in requirements:
        if r["trap_code"]:
            placements.append({
                "req_id": r["req_id"], "trap_code": r["trap_code"],
                "trap_group_id": r["trap_group_id"], "location": r["location"],
                "mentioned_once": r["mentioned_once"],
                "instruction": (
                    "Place this exactly where `location` says and word it so "
                    "it reads as unremarkable procurement prose -- do not "
                    "flag it as important. Do not add or remove any "
                    "requirement, and do not soften or relocate this one."),
            })
    return {
        "tender_id": tid,
        "buyer": tender["buyer"],
        "sector": tender["sector"],
        "size_class": tender["size_class"],
        "procurement_style": tone,
        "document_structure": {"body": True, "annexes": annex_names},
        "requirements": requirements,
        "trap_placements": placements,
        "correct_bid_no_bid_call": "NO-BID" if tid in config.NO_BID_TENDERS else "BID",
        "prose_agent_constraints": [
            "May not add or remove any requirement or trap listed here.",
            "May not change which document location (body vs named annex) "
            "carries which requirement.",
            "Dramatises wording, buyer voice, and document layout only.",
            "Must not reveal in the tender text itself which items are "
            "traps -- that information is for the marking key only.",
        ],
    }


# ---------------------------------------------------------------------------
# Step 4: persona attempt briefs (the engagement model)
# ---------------------------------------------------------------------------
#
# THE ENGAGEMENT MODEL (the design's load-bearing structural point):
#
# For persona P on tender T, every requirement r gets one seeded coin-flip
# deciding ENGAGED vs SKIMMED. The coin's bias is:
#
#   type_factor(r)              -- which persona trait governs this
#                                   requirement's type (eligibility ->
#                                   eligibility_scrutiny, technical ->
#                                   thoroughness, commercial -> thoroughness
#                                   at a mild discount, form ->
#                                   form_attentiveness, format ->
#                                   format_precision)
#   x annex_penalty(r)           -- persona's annex_diligence if r sits in
#                                   an annex, 1.0 if it sits in the body
#   x hidden_penalty(r)          -- an extra x0.4 if the requirement is
#                                   flagged mentioned_once (the hidden-form
#                                   trap is specifically designed to be easy
#                                   to miss even for an attentive reader)
#   x decay(r, T)                -- 1 - time_pressure_decay * position, i.e.
#                                   engagement erodes over the numbered list,
#                                   more so for personas who panic and for
#                                   longer (gnarlier) tenders
#
# then clipped to [0.03, 0.97] and compared against one draw from a
# Generator seeded on (RANDOM_SEED, persona_id, tender_id) -- so the whole
# 64-attempt corpus is reproducible bit-for-bit on any machine.
#
# This is deliberately NOT tuned per-attempt to hit the pre-registered
# bands (median 55-80% coverage, >=1 best attempt >=90% on >=3 tenders,
# <=1 of 8 no-bid attempts catching the eligibility trap). The persona
# TRAIT RANGES were calibrated once, at the population level, before any
# attempt was drawn; the per-attempt outcome is
# whatever the seeded draw produces. Where the chips fall is the finding,
# not a target hit by construction.
# ---------------------------------------------------------------------------

TYPE_TRAIT = {
    "eligibility": "eligibility_scrutiny",
    "technical": "thoroughness",
    "commercial": "thoroughness",
    "form": "form_attentiveness",
    "format": "format_precision",
}
COMMERCIAL_DISCOUNT = 0.9  # commercial terms get slightly less scrutiny than technical


def engagement_probability(persona: dict, req: dict, n_total: int) -> float:
    traits = persona["traits"]
    base = traits[TYPE_TRAIT[req["type"]]]
    if req["type"] == "commercial":
        base *= COMMERCIAL_DISCOUNT
    if req["location"].startswith("annex:"):
        base *= traits["annex_diligence"]
    if req["mentioned_once"]:
        base *= 0.4
    position_fraction = req["req_number"] / n_total
    decay = max(0.15, 1 - traits["time_pressure_decay"] * position_fraction)
    base *= decay
    return float(np.clip(base, 0.03, 0.97))


def build_attempt_brief(persona: dict, tender: dict, requirements: list[dict]) -> dict:
    tid, pid = tender["id"], persona["id"]
    rng = deterministic_rng(tender_num(tid), 100 + persona_num(pid))
    n_total = len(requirements)

    engagement_rows = []
    engaged_count = 0
    eligibility_trap_engaged = False
    for r in requirements:
        prob = engagement_probability(persona, r, n_total)
        engaged = bool(rng.random() < prob)
        if engaged:
            engaged_count += 1
        if engaged and r["trap_code"] == "eligibility_fail":
            eligibility_trap_engaged = True
        engagement_rows.append({
            "req_id": r["req_id"], "req_number": r["req_number"],
            "type": r["type"], "location": r["location"],
            "trap_code": r["trap_code"], "engagement": "engaged" if engaged else "skimmed",
            "engagement_probability": round(prob, 4),
        })

    # Contradiction-specific derived flag: flagged only if BOTH halves of a
    # linked pair were engaged with AND the persona's contradiction_alertness
    # clears one more seeded draw (noticing the pair conflicts is a further
    # step beyond having read both halves).
    contradiction_flags = {}
    groups: dict[str, list[dict]] = {}
    for row in engagement_rows:
        gid = next((r["trap_group_id"] for r in requirements if r["req_id"] == row["req_id"]), "")
        if gid:
            groups.setdefault(gid, []).append(row)
    for gid, rows in groups.items():
        both_engaged = all(r["engagement"] == "engaged" for r in rows)
        noticed = bool(both_engaged and rng.random() < persona["traits"]["contradiction_alertness"])
        contradiction_flags[gid] = noticed

    coverage_pct = round(100 * engaged_count / n_total, 1)

    return {
        "tender_id": tid,
        "persona_id": pid,
        "persona_name": persona["name"],
        "persona_tagline": persona["tagline"],
        "habit_paragraph": persona["habit_paragraph"],
        "chatbot_style": persona["chatbot_style"],
        "n_requirements": n_total,
        "engaged_count": engaged_count,
        "coverage_pct": coverage_pct,
        "eligibility_trap_engaged": eligibility_trap_engaged,
        "contradiction_pairs_noticed": contradiction_flags,
        "engagement": engagement_rows,
        "note": (
            "This brief lists which requirements this attempt plausibly "
            "noticed (engaged) versus glossed over (skimmed), derived "
            "deterministically from the persona's habit traits and this "
            "tender's structure. The prose agent dramatises a chat "
            "transcript and a draft response consistent with this list; "
            "it does not decide coverage itself and may not treat a "
            "'skimmed' requirement as noticed, or vice versa."),
    }


def build_assignment_matrix() -> dict[str, list[str]]:
    """Each tender gets 4 distinct personas; each persona gets 4 or 5
    tenders overall (8 personas at 5, 6 at 4, per config.PERSONAS_WITH_FIVE).
    Deterministic seeded greedy balance: for each tender, take the 4
    personas with the most remaining capacity (ties broken by a seeded
    shuffle each round).
    """
    rng = np.random.default_rng(config.RANDOM_SEED * 31 + 1)
    capacity = {p["id"]: (5 if p["id"] in config.PERSONAS_WITH_FIVE else 4)
                for p in config.PERSONAS}
    assert sum(capacity.values()) == len(config.TENDERS) * 4

    assignment: dict[str, list[str]] = {}
    for tender in config.TENDERS:
        order = list(capacity.keys())
        rng.shuffle(order)
        order.sort(key=lambda pid: -capacity[pid])  # stable: shuffle breaks ties
        chosen = order[:4]
        for pid in chosen:
            capacity[pid] -= 1
        assignment[tender["id"]] = chosen

    # Verify exact balance.
    total_per_persona: dict[str, int] = {p["id"]: 0 for p in config.PERSONAS}
    for pids in assignment.values():
        assert len(set(pids)) == 4, "a tender was assigned a duplicate persona"
        for pid in pids:
            total_per_persona[pid] += 1
    for pid, count in total_per_persona.items():
        expected = 5 if pid in config.PERSONAS_WITH_FIVE else 4
        assert count == expected, f"{pid} got {count} assignments, expected {expected}"
    assert sum(total_per_persona.values()) == 64
    return assignment


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    for d in (config.ANSWER_KEY_DIR, config.FACTS_DIR, config.TENDER_BRIEFS_DIR,
              config.ATTEMPT_BRIEFS_DIR):
        d.mkdir(parents=True, exist_ok=True)

    log(f"building facts library (Visakoivu Oy, seed={config.RANDOM_SEED})")
    facts = build_company_facts()

    log("building requirement inventories for all 16 tenders")
    all_requirements: list[dict] = []
    requirements_by_tender: dict[str, list[dict]] = {}
    for tender in config.TENDERS:
        reqs = build_requirement_inventory(tender, facts)
        requirements_by_tender[tender["id"]] = reqs
        all_requirements.extend(reqs)
        n_traps = sum(1 for r in reqs if r["trap_code"])
        log(f"  {tender['id']} ({tender['size_class']:>6}, {tender['sector']:>7}): "
            f"{len(reqs)} requirements, {n_traps} trap-flagged, "
            f"buyer='{tender['buyer']}'")

    log("checking eligibility consistency against the facts library")
    assert_eligibility_consistency(all_requirements, facts)

    # --- write per-tender + combined answer key -------------------------
    log("writing answer_key/requirements_NN.csv and combined answer_key.csv")
    combined_rows = []
    for tender in config.TENDERS:
        tid = tender["id"]
        reqs = requirements_by_tender[tid]
        df = pd.DataFrame(reqs)
        df["tender_bid_no_bid_call"] = "NO-BID" if tid in config.NO_BID_TENDERS else "BID"
        df.to_csv(config.ANSWER_KEY_DIR / f"requirements_{tid[1:]}.csv", index=False)
        combined_rows.append(df)
    combined = pd.concat(combined_rows, ignore_index=True)
    combined.to_csv(config.ANSWER_KEY_DIR / "answer_key.csv", index=False)
    log(f"  {len(combined)} requirement rows across 16 tenders written")

    # --- facts library ----------------------------------------------------
    log("writing facts/company_facts.yaml and company_facts.md")
    with open(config.FACTS_DIR / "company_facts.yaml", "w", encoding="utf-8") as fh:
        yaml.safe_dump(facts, fh, allow_unicode=True, sort_keys=False)
    with open(config.FACTS_DIR / "company_facts.md", "w", encoding="utf-8") as fh:
        fh.write(render_company_facts_md(facts))

    # --- tender briefs ------------------------------------------------------
    log("writing tender_briefs/brief_NN.json")
    for tender in config.TENDERS:
        brief = build_tender_brief(tender, requirements_by_tender[tender["id"]])
        path = config.TENDER_BRIEFS_DIR / f"brief_{tender['id'][1:]}.json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(brief, fh, ensure_ascii=False, indent=2)

    # --- assignment matrix + attempt briefs ---------------------------------
    log("building the 16x4 persona assignment matrix")
    assignment = build_assignment_matrix()
    with open(config.DATA_DIR / "assignment_matrix.json", "w", encoding="utf-8") as fh:
        json.dump(assignment, fh, ensure_ascii=False, indent=2)

    log("writing attempt_briefs/attempt_NN_PP.json (the engagement model)")
    all_attempts = []
    for tender in config.TENDERS:
        tid = tender["id"]
        for pid in assignment[tid]:
            persona = config.PERSONA_BY_ID[pid]
            attempt = build_attempt_brief(persona, tender, requirements_by_tender[tid])
            all_attempts.append(attempt)
            path = config.ATTEMPT_BRIEFS_DIR / f"attempt_{tid[1:]}_{pid[1:]}.json"
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(attempt, fh, ensure_ascii=False, indent=2)
    log(f"  {len(all_attempts)} attempt briefs written")

    # --- diagnostic summary (not a pass/fail gate -- just visibility into
    #     whether the seeded engagement model landed near the pre-registered
    #     bands; validate_structure.py does the hard checks) -------------
    coverages = [a["coverage_pct"] for a in all_attempts]
    median_coverage = float(np.median(coverages))
    by_tender_best = {}
    for tender in config.TENDERS:
        tid = tender["id"]
        best = max(a["coverage_pct"] for a in all_attempts if a["tender_id"] == tid)
        by_tender_best[tid] = best
    n_tenders_best_ge_90 = sum(1 for v in by_tender_best.values() if v >= 90)
    no_bid_attempts = [a for a in all_attempts if a["tender_id"] in config.NO_BID_TENDERS]
    no_bid_caught = sum(1 for a in no_bid_attempts if a["eligibility_trap_engaged"])

    log("--- diagnostic summary vs the pre-registered bands ---")
    log(f"  median Arm-A coverage across 64 attempts: {median_coverage}% "
        f"(band: 55-80%)")
    log(f"  tenders where the best attempt reaches >=90% coverage: "
        f"{n_tenders_best_ge_90} (band: >=3)")
    log(f"  of {len(no_bid_attempts)} attempts on the 2 no-bid tenders, "
        f"{no_bid_caught} engaged with the eligibility-fail requirement "
        f"(band: <=1 recommending NO-BID; engagement is necessary but not "
        f"sufficient for that -- Phase 3 prose determines the actual call)")
    log("These are diagnostics on the generative model, not a gate: the "
        "actual pre-registered scoring happens at marking time against real Arm A/B attempts "
        "and is never retuned after the fact.")
    log("done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # graceful, informative failure
        print(f"[generate_structure] FAILED: {exc}", file=sys.stderr)
        raise
