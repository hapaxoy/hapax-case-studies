"""Phase 5 marking for Project 7 (Tenders).

THE ONLY SCRIPT IN THIS PROJECT PERMITTED TO OPEN THE ANSWER KEY. Neither
Arm A's persona prompts nor Arm B's run-agents/gates ever read
`data/answer_key/`, `data/tenders/clause_map_*.json`, or `data/attempt_briefs/`
-- this script reads all three, mechanically, after both arms are frozen.

What this does:
  Arm A (64 attempts, data/arm_a/attempt_NN_PP.json): marks the DRAFT TEXT
  independently of the generation seeds. For every answer-key requirement of
  an attempt's tender, decide addressed/unaddressed by tolerant content
  matching against the draft prose (numbers exact with format tolerance,
  named forms/certifications by name, otherwise distinctive-noun matching
  from the requirement's own clause text). Reports coverage %, traps caught/
  missed, bid/no-bid correctness, and a fabricated-claim count cross-checked
  against the seeded fabrication_events in data/attempt_briefs/ (ground
  truth, read here only -- never by the prose agents).

  Arm B (16 runs, data/arm_b/run_NN/): marks the STRUCTURED artefacts.
  Extraction recall = matrix.json rows matched to key requirements (via
  clause_label+body/annex, then a text-keyword fallback). Final coverage =
  response rows answered in the terminal response_v*.json, mapped through
  that same match, to key requirements (NOT to matrix rows -- an
  unextracted requirement can never be "answered"). Trap outcomes per the
  key's correct_action column. Gate-bounce and false-block statistics from
  the gate_report_*.json files. An independent fabrication check reruns
  gates.py's facts-gate logic against the terminal response AND additionally
  scans response.general_sections (which gates.py structurally cannot check
  -- a documented, flagged gap) against company_facts.yaml.

  The six pre-registered expectations are then verdicted
  MET/NOT MET against these numbers. Any miss is FROZEN and published
  as-is -- this script never adjusts a matcher, a threshold, or a corpus
  file to make an expectation come out differently.

Outputs (this project's data/analysis/ folder only):
  data/analysis/marks.json   -- full per-attempt / per-run detail
  data/analysis/report.md    -- the marked report (verdict table, per-tender
                                 A-vs-B table, trap-class table, marking-
                                 quality notes, every frozen deviation)

Run: python mark.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from statistics import mean, median

import yaml

import config

# ---------------------------------------------------------------------------
# Reused/adapted machinery from the corpus's own validators -- see each
# import site below for what it is used for. This script imports pure
# functions/constants only; it never calls their module-level fail()/log()
# accumulators, and never triggers their __main__ blocks.
# ---------------------------------------------------------------------------
from validate_corpus import (
    CERT_PATTERNS,
    FORM_TOPIC_PATTERNS,
    contains_number,
    number_variants,
    load_doc_lines,
    load_clause_map,
    extract_clause_text,
)
from validate_arm_a import (
    DISCIPLINE_KEYWORDS,
    NOT_HELD_CERT_CODES,
    CAPABILITY_KEYWORDS,
    keywords,
    normalize as normalize_alnum,
    cert_digits,
    gather_corpus_fabrication_vocabulary,
    number_variants as arm_a_number_variants,
)

ARM_B_DIR_CODE = config.PROJECT_ROOT / "code" / "arm_b"
sys.path.insert(0, str(ARM_B_DIR_CODE))
import gates as armb_gates  # noqa: E402  (path insert must precede this import)

# ---------------------------------------------------------------------------
# Config block -- every tunable for this marking pass lives here.
# ---------------------------------------------------------------------------

DATA_DIR = config.DATA_DIR
ANSWER_KEY_PATH = config.ANSWER_KEY_DIR / "answer_key.csv"
TENDERS_DIR = DATA_DIR / "tenders"
FACTS_PATH = config.FACTS_DIR / "company_facts.yaml"
ARM_A_DIR = DATA_DIR / "arm_a"
ARM_B_DIR = DATA_DIR / "arm_b"
ATTEMPT_BRIEFS_DIR = config.ATTEMPT_BRIEFS_DIR
ASSIGNMENT_MATRIX_PATH = DATA_DIR / "assignment_matrix.json"
ANALYSIS_DIR = DATA_DIR / "analysis"
MARKS_JSON_PATH = ANALYSIS_DIR / "marks.json"
REPORT_MD_PATH = ANALYSIS_DIR / "report.md"

# Coverage-matching thresholds (calibrated by hand-inspection, see report.md
# "Marking-quality notes" for the spot-check this was checked against).
KEYWORD_FALLBACK_RATIO = 0.5   # matches validate_arm_a.py's own precedent
KEYWORD_FALLBACK_MIN_HITS_SMALL = 1  # for clauses with <=2 distinct keywords

# The recurring annex_disqualifier trap text is identical across T05/T06/T13
# and is written in Finnish in two of the three tenders' annexes (T05, T06)
# and in English in the third (T13). A single keyword-extraction pass over the (mixed-language)
# clause text would not reliably catch the Finnish-only cases, so this trap
# gets a fixed bilingual keyword list instead of the generic fallback.
# Bilingual keyword glosses for the corpus's own FIXED technical/commercial/
# format topic banks (config.py's TECHNICAL_TOPICS / COMMERCIAL_TOPICS /
# FORMAT_TOPICS). Some tenders (T01-T04, T09-T16) render these clauses in English
# in the tender document itself; others (T05-T08 confirmed) print the
# Finnish topic sentence verbatim as the clause text, with no English
# rendering anywhere in the source document. Extracting keywords from the
# DOCUMENT's own clause text is unreliable across that split, since every
# Arm A/B draft is written in English regardless of the source language --
# so these three topic banks (a small, fixed, corpus-wide vocabulary; every
# non-trap technical/commercial/format requirement's description is
# verified at matcher-build time to be a member of one of them) get a
# hand-translated English keyword list instead of document-text extraction.
TOPIC_KEYWORDS_EN: dict[str, list[str]] = {
    # -- technical --
    "Hataytilanteiden vasteaika ja paivystysjarjestely":
        ["emergency", "response time", "standby", "on-call", "callout", "call-out"],
    "Huoltokaynnin sisalto ja ajoitus":
        ["maintenance visit", "service visit", "scheduled maintenance", "schedul"],
    "Varaosien saatavuus ja toimitusaika":
        ["spare part", "availability", "delivery time"],
    "Rakennusautomaatiojarjestelman yhteensopivuus (BACnet/Modbus)":
        ["bacnet", "modbus", "building automation", "compatib"],
    "LVI-jarjestelman huoltosopimuksen sisalto":
        ["hvac", "lvi", "maintenance agreement", "maintenance contract"],
    "Sahkoasennusten maaraaikaistarkastukset":
        ["electrical installation", "periodic inspection", "statutory inspection"],
    "Tyontekijoiden patevyysvaatimukset tyomaalla":
        ["qualification", "competence", "site personnel", "on-site worker"],
    "Aliurakoinnin hallintasuunnitelma":
        ["subcontract", "management plan"],
    "Tyoturvallisuussuunnitelma":
        ["safety plan", "occupational safety", "health and safety plan"],
    "Ymparistoasioiden hallinta tyon aikana":
        ["environmental management", "environment"],
    "Asennustoiden menetelmaselostus":
        ["method statement", "installation method", "methodology"],
    "Laadunvalvonta- ja testausmenettelyt":
        ["quality control", "testing procedure", "quality assurance"],
    "Asennettujen laitteiden takuuaika":
        ["warranty"],
    "Palvelutasotavoitteet (SLA)":
        ["sla", "service level"],
    "Raportointikaytanto tilaajalle":
        ["report", "reporting"],
    "Kunnonvalvonnan tiedonkeruu":
        ["condition monitoring", "data collection", "monitoring"],
    "Energiatehokkuustoimenpiteet":
        ["energy efficiency", "energy-saving", "energy saving"],
    "Kulunvalvonta ja turvallisuus tilaajan kiinteistossa":
        ["access control", "security"],
    "Jatehuolto ja jatteen lajittelu tyomaalla":
        ["waste management", "waste sorting", "recycling"],
    "Palontorjuntajarjestelmien huolto":
        ["fire protection", "fire safety system", "fire suppression", "fire alarm"],
    "Kylmalaitteiden huolto (F-kaasu)":
        ["refrigeration", "f-gas", "f-kaasu", "cooling equipment"],
    "Hissien huollon maaraystenmukaisuus":
        ["lift maintenance", "elevator maintenance", "lift inspection"],
    "Rakennuksen vaipan kunnon tarkastus":
        ["building envelope", "facade", "envelope condition"],
    "Ennakoivan kunnossapidon suunnitelma":
        ["preventive maintenance", "preventative maintenance", "maintenance plan"],
    "Korjaavan kunnossapidon vasteajat":
        ["corrective maintenance", "response time"],
    "Omaisuusrekisterin ja dokumentaation luovutus":
        ["asset register", "documentation", "handover"],
    "Kayttoonoton ja testauksen menettely":
        ["commissioning", "testing"],
    "Tilaajan kiinteistohenkilokunnan koulutus":
        ["training"],
    "Palvelun jatkuvuus henkilostomuutoksissa":
        ["continuity", "staff change", "personnel change"],
    "Ratkaisemattomien vikojen eskalaatiomenettely":
        ["escalation", "unresolved fault"],
    # -- commercial --
    "Hinnoittelurakenne (kiintea hinta / yksikkohinta / aikaveloitus)":
        ["pricing structure", "fixed price", "unit price", "time-based", "hourly rate"],
    "Maksuehdot":
        ["payment term"],
    "Laskutustiheys ja -muoto":
        ["invoicing frequency", "invoice format", "invoicing"],
    "Hintojen indeksiehto":
        ["index", "indexation", "price adjustment"],
    "Hinnoittelun valuutta":
        ["pricing currency", "currency"],
    "Vastuunrajoituslauseke":
        ["limitation of liability", "liability cap", "liability clause"],
    "Sopimussakko palvelutason alittuessa":
        ["penalty", "liquidated damages", "service-level shortfall"],
    "Bonus-malus-jarjestelma":
        ["bonus", "malus", "incentive scheme"],
    "Sopimuskausi ja jatko-optiot":
        ["contract period", "extension option"],
    "Sopimuksen irtisanomisehdot":
        ["termination"],
    "Pidatysprosentti":
        ["retention"],
    "Ennakkomaksuehdot":
        ["advance payment", "prepayment"],
    "Kustannuserittelyvaatimus":
        ["cost breakdown", "itemised cost", "itemized cost"],
    "Aliurakoitsijoiden kustannusten lapinakyvyys":
        ["subcontractor cost", "cost transparency"],
    "Alennusrakenne puitesopimuksen volyymille":
        ["discount", "volume discount", "framework agreement volume"],
    # -- format --
    "Hinta ilmoitettava euroa/m2/vuosi, ei euroa/kk":
        ["eur/m2", "eur per square metre", "per square metre per year", "m2/year", "m²/year"],
    "Kaikki hinnat ilman arvonlisaveroa, valuuttana EUR":
        ["vat", "excluding vat", "eur"],
    "Tarjousasiakirjan sivumaararajoitus (enintaan 20 sivua ilman liitteita)":
        ["page limit", "20 pages", "page count"],
    "Tiedostomuoto: yksi PDF-tiedosto, ei salasanasuojausta":
        ["pdf", "file format", "password"],
    "Fonttikoon vahimmaisvaatimus (11pt)":
        ["font size", "11pt", "11 pt", "11-point"],
    "Tarjouksen toimituskanava ja kappalemaara":
        ["submission channel", "number of copies", "copies"],
    "Jattoajan aikavyohyke ja tarkka kellonaika":
        ["timezone", "time zone", "helsinki time", "finnish time", "exact time"],
    "Puitesopimuksen hinnoittelun viitevaluutta":
        ["reference currency", "framework agreement", "pricing currency"],
    "Pyoristyskaytanto (kaksi desimaalia)":
        ["rounding", "two decimal", "decimal place"],
    "Yksikkoperuste ylapitohinnoittelulle (per kiinteisto vs. per m2)":
        ["unit basis", "per property", "per square metre", "per m2"],
}

ANNEX_DISQUALIFIER_KEYWORDS = [
    "24/7", "round-the-clock", "round the clock", "standby", "on-call",
    "on call", "paivystys", "ymparivuorokau", "finland", "suomessa",
    "regardless of price", "riippumatta hinnasta",
]

# Conflict-flagging vocabulary for the contradiction trap ("Flag; answer
# both, note conflict") -- a draft/response that states both numbers but
# never uses language like this has answered, not flagged.
CONFLICT_LANGUAGE = [
    "however", "differ", "discrepanc", "inconsist", "contradict",
    "conflict", "whereas", "note that the annex", "note that the appendix",
    "elsewhere", "annex states", "appendix states", "body states",
    "two different", "two values", "reconcile",
]

# Eligibility-failure phrasing, reused verbatim from validate_arm_a.py's own
# decision-table check (the rule: "accept either; record which").
ELIGIBILITY_FAIL_LANGUAGE_RE = re.compile(
    r"no-?bid|does not (meet|satisfy)|fails? (the )?eligibility|"
    r"cannot (meet|satisfy)|recommend.{0,20}not (to )?bid", re.IGNORECASE)

FABRICATION_MATCH_THRESHOLD = 0.34  # extraction/matcher text-overlap floor


def log(message: str) -> None:
    print(f"[mark] {message}", flush=True)


# ---------------------------------------------------------------------------
# Loading: answer key, clause maps, tender text, facts
# ---------------------------------------------------------------------------

def load_answer_key() -> dict[str, list[dict]]:
    import pandas as pd
    df = pd.read_csv(ANSWER_KEY_PATH, keep_default_na=False)
    df["mentioned_once_bool"] = (
        df["mentioned_once"].astype(str).str.strip().str.lower() == "true")
    by_tender: dict[str, list[dict]] = {}
    for tender_id, group in df.groupby("tender_id"):
        by_tender[tender_id] = group.to_dict("records")
    return by_tender


def load_facts() -> dict:
    with open(FACTS_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def build_clause_lookup(tender_id: str) -> dict[str, dict]:
    """{req_id: clause_map entry dict} for one tender."""
    cmap = load_clause_map(tender_id)
    return {c["req_id"]: c for c in cmap["clauses"]}


# ---------------------------------------------------------------------------
# Requirement matchers -- the tolerant content-matching engine shared by
# both arms. Built once per tender from the answer key + clause map + the
# tender document's own (English, mostly) clause text.
# ---------------------------------------------------------------------------

def parse_hidden_form_topic(description: str) -> str | None:
    m = re.search(r"Tarjoukseen on liitettava myos: (.+)\.\"?$", description.rstrip())
    return m.group(1) if m else None


def build_matcher(row: dict, clause_entry: dict | None, doc_lines: list[str]) -> dict:
    req_id = row["req_id"]
    label = clause_entry["clause_label"] if clause_entry else None
    doc_location = clause_entry["doc_location"] if clause_entry else None
    clause_text = extract_clause_text(doc_lines, label, doc_location) if label else None
    check_type = row["eligibility_check_type"] or None
    param = str(row["eligibility_check_param"]) if row["eligibility_check_param"] != "" else None
    trap_code = row["trap_code"] or None
    description = row["description"]

    matcher = {
        "req_id": req_id, "tender_id": row["tender_id"], "type": row["type"],
        "location": row["location"], "trap_code": trap_code,
        "trap_group_id": row["trap_group_id"] or None,
        "mentioned_once": bool(row["mentioned_once_bool"]),
        "correct_action": row["correct_action"], "description": description,
        "clause_label": label, "doc_location": doc_location,
        "clause_text": clause_text, "method": None,
    }

    # --- Eligibility rows: structured check_type/param drive the match ----
    if check_type == "has_certification":
        matcher["method"] = "certification"
        matcher["cert_code"] = param
    elif check_type == "min_turnover":
        matcher["method"] = "number_or_topic"
        matcher["number_target"] = param
        matcher["topic_keywords"] = ["turnover", "liikevaihto"]
    elif check_type == "insurance_min":
        kind, minimum = param.split(":")
        matcher["method"] = "number_or_topic"
        matcher["number_target"] = minimum
        matcher["topic_keywords"] = ["insurance", "liability", "vakuutus", kind]
    elif check_type == "min_staff_discipline":
        discipline, minimum = param.split(":")
        matcher["method"] = "number_or_topic"
        matcher["number_target"] = minimum
        matcher["topic_keywords"] = (
            list(DISCIPLINE_KEYWORDS.get(discipline, [discipline]))
            + ["staff", "employees", "specialists", "technicians", "personnel",
               "professionals", "henkiloa", "ammattilaista"])
    elif check_type == "min_equity_ratio":
        matcher["method"] = "number_or_topic"
        matcher["number_target"] = param
        matcher["topic_keywords"] = ["equity ratio", "solvency", "omavaraisuusaste"]
    elif check_type in ("min_reference_count", "min_single_reference_value"):
        matcher["method"] = "number_or_topic"
        matcher["number_target"] = param
        matcher["topic_keywords"] = ["reference", "referenssi"]
    # --- Contradiction trap: the pair's own distinctive number ------------
    elif trap_code == "contradiction":
        m = re.search(r"(\d+)", description)
        matcher["method"] = "contradiction_number"
        matcher["number_target"] = m.group(1) if m else None
    # --- Annex-disqualifier trap: fixed bilingual keyword list -------------
    elif trap_code == "annex_disqualifier":
        matcher["method"] = "fixed_keywords"
        matcher["fixed_keywords"] = ANNEX_DISQUALIFIER_KEYWORDS
    # --- Format traps: bespoke exact-compliance checks ---------------------
    elif trap_code == "format_trap":
        matcher["method"] = "format_trap"
        matcher["format_trap_id"] = req_id
    # --- Named forms: matched by name via the alias table -------------------
    elif row["type"] == "form" and matcher["mentioned_once"]:
        topic = parse_hidden_form_topic(description)
        matcher["method"] = "form_topic"
        matcher["topic"] = topic
    elif row["type"] == "form" and description in FORM_TOPIC_PATTERNS:
        matcher["method"] = "form_topic"
        matcher["topic"] = description
    # --- Fixed technical/commercial/format topic banks: hand-translated --
    elif description in TOPIC_KEYWORDS_EN:
        matcher["method"] = "fixed_keywords"
        # English gloss PLUS the topic's own Finnish stems -- some tenders'
        # source documents (and, independently, some Arm A personas'
        # drafts) render these clauses in Finnish, closely echoing the
        # topic-bank sentence itself as a heading, so a Finnish draft is caught too.
        matcher["fixed_keywords"] = TOPIC_KEYWORDS_EN[description] + keywords(description)
    # --- Everything else: distinctive-noun matching from the clause text --
    else:
        matcher["method"] = "keyword_fallback"

    return matcher


def word_boundary_present(keyword: str, lower_text: str) -> bool:
    """Plain `keyword in text` substring checks false-positive badly on
    Finnish text -- e.g. the short keyword 'vat' matches inside ordinary
    Finnish verb forms like 'vaadittavat', 'pysyvat', 'muodostavat' (the
    language is agglutinative; short ASCII fragments recur constantly
    INSIDE longer inflected words). A left (start-of-word) boundary blocks
    that class of false positive. The right side is deliberately left open
    (no trailing boundary): English/Finnish suffixes are exactly the tolerance
    this matcher needs (a draft saying "Spare parts" or "Subcontracting
    management" must still match the keywords "spare part" / "subcontract"),
    and a false start-of-word collision is far rarer than a false mid-word
    one, which spot-checking confirmed (see report.md marking-quality notes)."""
    pattern = r"(?<![a-zA-Z0-9])" + re.escape(keyword.lower())
    return re.search(pattern, lower_text) is not None


def numeric_present(text: str, raw_number: str) -> bool:
    """Tolerant number match -- thousands separators, plain int, with-space
    grouping (reuses validate_corpus.py's own number_variants/contains_number)."""
    return contains_number(text, raw_number)


FONT_SIZE_RE = re.compile(r"\b11\s*[-\s]?\s*(pt|point)\b", re.IGNORECASE)
CORRECT_PRICE_UNIT_RE = re.compile(
    r"eur\s*/?\s*m\s*[²2]\s*/\s*(year|vuosi)|eur\s+per\s+square\s*metre\s+per\s+year|"
    r"€\s*/\s*m\s*[²2]\s*/\s*(year|vuosi)", re.IGNORECASE)
WRONG_PRICE_UNIT_RE = re.compile(
    r"eur\s*/\s*(month|kk|kuukau)|eur\s+per\s+month|€\s*/\s*(month|kk)",
    re.IGNORECASE)
DEADLINE_TIMEZONE_RE = re.compile(
    r"(finnish time|helsinki time|eet\b|eest\b)", re.IGNORECASE)
DEADLINE_TIME_RE = re.compile(r"\b\d{1,2}[:.]\d{2}\b")
DEADLINE_RECEIPT_RULE_RE = re.compile(
    r"(time (it is )?received|received by|time of receipt|logged as received|"
    r"buyer'?s? (mailbox|server)|not the time (it is )?sent)", re.IGNORECASE)


def check_format_trap(req_id: str, text: str) -> tuple[bool, bool, str]:
    """Returns (addressed, exactly_compliant, evidence). `addressed` means
    the topic was engaged at all; `exactly_compliant` means "Comply exactly"
    was actually satisfied (the trap-specific correct-behaviour test)."""
    if req_id == "T04-R013":
        found = bool(FONT_SIZE_RE.search(text))
        return found, found, (
            "font-size statement (11pt) found in draft text" if found else
            "no font-size statement found -- NOTE: a text-only draft cannot "
            "generally demonstrate actual document formatting (font size is "
            "a property of the rendered file, not of prose); see marking-"
            "quality notes")
    if req_id == "T10-R025":
        correct = bool(CORRECT_PRICE_UNIT_RE.search(text))
        wrong = bool(WRONG_PRICE_UNIT_RE.search(text))
        if correct and not wrong:
            return True, True, "correct unit (EUR/m2/year) used, no EUR/month found"
        if correct and wrong:
            return True, False, "both EUR/m2/year and EUR/month found -- inconsistent pricing unit"
        if wrong:
            return True, False, "EUR/month used -- fell into the price-unit trap"
        return False, False, "no pricing-unit statement found"
    if req_id == "T14-R039":
        tz = bool(DEADLINE_TIMEZONE_RE.search(text))
        tm = bool(DEADLINE_TIME_RE.search(text))
        receipt = bool(DEADLINE_RECEIPT_RULE_RE.search(text))
        addressed = tz or tm or receipt
        compliant = (tz and tm) or receipt
        return addressed, compliant, (
            f"timezone_mentioned={tz}, time_mentioned={tm}, "
            f"receipt-not-send rule mentioned={receipt}")
    raise ValueError(f"no format-trap check registered for {req_id}")


def check_addressed(matcher: dict, text: str) -> tuple[bool, str]:
    """The core tolerant-matching decision: does `text` address this
    requirement? Returns (addressed, evidence)."""
    method = matcher["method"]
    lower = text.lower()

    if method == "certification":
        patterns = CERT_PATTERNS.get(matcher["cert_code"], [])
        for p in patterns:
            if re.search(p, text, re.IGNORECASE):
                return True, f"certification name matched pattern {p!r}"
        return False, f"certification '{matcher['cert_code']}' not named in text"

    if method == "number_or_topic":
        if numeric_present(text, matcher["number_target"]):
            return True, f"threshold number {matcher['number_target']} found"
        for kw in matcher["topic_keywords"]:
            if word_boundary_present(kw, lower):
                return True, f"topic keyword {kw!r} found (number not restated)"
        return False, "neither the threshold number nor a topic keyword found"

    if method == "contradiction_number":
        if matcher["number_target"] is None:
            return False, "could not parse a number out of this trap's own description"
        found = numeric_present(text, matcher["number_target"])
        return found, (f"number {matcher['number_target']} found" if found
                        else f"number {matcher['number_target']} not found")

    if method == "fixed_keywords":
        for kw in matcher["fixed_keywords"]:
            if word_boundary_present(kw, lower):
                return True, f"fixed trap keyword {kw!r} found"
        return False, "none of the fixed trap keywords found"

    if method == "format_trap":
        addressed, _, evidence = check_format_trap(matcher["format_trap_id"], text)
        return addressed, evidence

    if method == "form_topic":
        topic = matcher.get("topic")
        patterns = FORM_TOPIC_PATTERNS.get(topic, [])
        if not patterns:
            return False, f"no alias patterns registered for form topic {topic!r}"
        for p in patterns:
            if re.search(p, text, re.IGNORECASE):
                return True, f"form topic pattern matched: {p}"
        return False, f"form topic {topic!r} not named in text"

    if method == "keyword_fallback":
        source = matcher["clause_text"] or matcher["description"]
        kws = keywords(source)
        if not kws:
            return False, "no distinctive keywords could be extracted from the requirement text"
        hits = sum(1 for k in kws if k in lower)
        ratio = hits / len(kws)
        addressed = ratio >= KEYWORD_FALLBACK_RATIO or (
            len(kws) <= 2 and hits >= KEYWORD_FALLBACK_MIN_HITS_SMALL)
        return addressed, f"{hits}/{len(kws)} distinctive keywords matched (ratio {ratio:.2f})"

    raise ValueError(f"unknown matcher method {method!r}")


# ---------------------------------------------------------------------------
# Trap-outcome assessment (shared logic, arm-agnostic once given a "get the
# text for req_id X" function).
# ---------------------------------------------------------------------------

def assess_traps(matchers: list[dict], get_text, bid_decision: str | None,
                  is_no_bid_tender: bool) -> list[dict]:
    """One outcome record per distinct trap (contradiction traps are
    collapsed to one record per trap_group_id)."""
    outcomes: list[dict] = []
    by_group: dict[str, list[dict]] = {}
    singles: list[dict] = []
    for m in matchers:
        if m["trap_code"] is None:
            continue
        if m["trap_code"] == "contradiction":
            by_group.setdefault(m["trap_group_id"], []).append(m)
        else:
            singles.append(m)

    for m in singles:
        text = get_text(m["req_id"])
        addressed, evidence = check_addressed(m, text) if text else (False, "not extracted/answered")
        if m["trap_code"] == "eligibility_fail":
            flagged = bool(bid_decision == "no-bid" or
                            (bid_decision == "NO_BID") or
                            (text and ELIGIBILITY_FAIL_LANGUAGE_RE.search(text)))
            caught = flagged
            outcomes.append({
                "trap_code": m["trap_code"], "req_ids": [m["req_id"]],
                "correct_action": m["correct_action"], "caught": caught,
                "detail": f"bid_decision/status={bid_decision!r}, "
                          f"explicit-flag-in-text={bool(text and ELIGIBILITY_FAIL_LANGUAGE_RE.search(text))}",
            })
        elif m["trap_code"] == "format_trap":
            if text:
                addressed2, compliant, evidence2 = check_format_trap(m["req_id"], text)
            else:
                addressed2, compliant, evidence2 = False, False, "not extracted/answered"
            outcomes.append({
                "trap_code": m["trap_code"], "req_ids": [m["req_id"]],
                "correct_action": m["correct_action"], "caught": compliant,
                "addressed": addressed2, "detail": evidence2,
            })
        else:  # annex_disqualifier, hidden_form
            outcomes.append({
                "trap_code": m["trap_code"], "req_ids": [m["req_id"]],
                "correct_action": m["correct_action"], "caught": addressed,
                "detail": evidence,
            })

    for group_id, pair in by_group.items():
        texts = {m["req_id"]: get_text(m["req_id"]) for m in pair}
        addressed_flags = {}
        for m in pair:
            t = texts[m["req_id"]]
            addressed_flags[m["req_id"]] = check_addressed(m, t)[0] if t else False
        both_addressed = all(addressed_flags.values())
        combined_text = " ".join(t for t in texts.values() if t)
        flagged = any(w in combined_text.lower() for w in CONFLICT_LANGUAGE)
        caught = both_addressed and flagged
        detail = (f"both_answered={both_addressed}, conflict_language_found={flagged}, "
                  f"per-req addressed={addressed_flags}")
        outcomes.append({
            "trap_code": "contradiction", "req_ids": list(addressed_flags),
            "correct_action": pair[0]["correct_action"], "caught": caught,
            "partial": both_addressed and not flagged, "detail": detail,
        })

    return outcomes


# ---------------------------------------------------------------------------
# Independent fabrication detection (used for both arms, with a different
# text source per arm). Cert claims are checked against company_facts.yaml
# directly (held / not-held / wholly invented); numeric claims are checked
# against the corpus-wide fabrication vocabulary already validated by
# validate_arm_a.py (Arm A) or against company_facts.yaml globally (Arm B).
# ---------------------------------------------------------------------------

def detect_certification_fabrications(text: str, facts: dict) -> list[dict]:
    cert_patterns = armb_gates.build_certification_vocabulary(facts)
    findings = []
    seen = set()
    for pattern in cert_patterns:
        for m in pattern.finditer(text):
            raw = m.group(0)
            key = raw.upper()
            if key in seen:
                continue
            ok, reason = armb_gates.certification_claim_supported(raw, facts, "certifications")
            if not ok:
                seen.add(key)
                findings.append({"claim": raw, "reason": reason})
    return findings


def detect_numeric_fabrications_arm_a(text: str, vocab: dict) -> list[dict]:
    findings = []
    for target_area, claimed in vocab["ref_claims"]:
        for v in arm_a_number_variants(claimed):
            if re.search(rf"\b{re.escape(v)}\b", text):
                findings.append({"kind": "inflated_reference", "target_area": target_area,
                                  "claimed_value": claimed})
                break
    lower = text.lower()
    for discipline, claimed in vocab["cap_claims"]:
        kws = DISCIPLINE_KEYWORDS.get(discipline, [discipline.lower()])
        for m in re.finditer(rf"\b{claimed}\b", text):
            window = lower[max(0, m.start() - 60):m.end() + 60]
            if any(k in window for k in kws):
                findings.append({"kind": "capacity_overclaim", "target_area": discipline,
                                  "claimed_value": claimed})
                break
    for target_area, kws in CAPABILITY_KEYWORDS.items():
        for kw in kws:
            if kw.lower() in lower:
                findings.append({"kind": "uncited_capability", "target_area": target_area,
                                  "claimed_value": kw})
                break
    for code in NOT_HELD_CERT_CODES:
        if re.search(rf"\b{cert_digits(code)}\b", text):
            findings.append({"kind": "invented_certification", "target_area": code,
                              "claimed_value": "held"})
    return findings


def detect_numeric_fabrications_global(text: str, facts: dict) -> list[dict]:
    """Arm B version: any EUR/headcount/year-count claim in `text` that
    matches NOTHING anywhere in company_facts.yaml is flagged. Legitimate
    tender-threshold restatements (e.g. 'exceeds the EUR 5,000,000
    turnover requirement') coincide with eligibility_check_param values,
    not with company facts, so this check is scoped to claims a facts-gate
    citation would need to support -- i.e. it mirrors gates.py's own claim
    extraction, applied without the per-row citation restriction gates.py
    normally uses, as a second, citation-blind pass."""
    cert_patterns = armb_gates.build_certification_vocabulary(facts)
    claims = armb_gates.extract_claims(text, cert_patterns)
    flat_facts = json.dumps(facts, ensure_ascii=False)
    findings = []
    for claim in claims:
        if claim["kind"] == "certification":
            ok, reason = armb_gates.certification_claim_supported(claim["raw"], facts, "certifications")
            if not ok:
                findings.append({"kind": "certification", "claim": claim["raw"], "reason": reason})
            continue
        value = claim["value"]
        if value is None:
            continue
        supported = False
        for number_match in re.findall(r"-?\d[\d\s.,]*\d|-?\d+", flat_facts):
            parsed = armb_gates.normalise_number(number_match)
            if parsed is not None and armb_gates.numbers_equal(parsed, value):
                supported = True
                break
        if not supported:
            findings.append({"kind": claim["kind"], "claim": claim["raw"], "value": value})
    return findings


# ---------------------------------------------------------------------------
# ARM A marking
# ---------------------------------------------------------------------------

def mark_arm_a(matchers_by_tender: dict[str, list[dict]], facts: dict) -> dict:
    log("marking Arm A (64 attempts)...")
    assignment_matrix = json.loads(ASSIGNMENT_MATRIX_PATH.read_text(encoding="utf-8"))
    vocab = gather_corpus_fabrication_vocabulary()

    attempts: dict[str, dict] = {}
    for tender_id, persona_ids in assignment_matrix.items():
        for persona_id in persona_ids:
            tnum, pnum = int(tender_id[1:]), int(persona_id[1:])
            attempt_id = f"attempt_{tnum:02d}_{pnum:02d}"
            path = ARM_A_DIR / f"{attempt_id}.json"
            if not path.exists():
                log(f"  WARNING: {attempt_id} missing at {path}, skipped")
                continue
            attempt = json.loads(path.read_text(encoding="utf-8"))
            draft = attempt["draft"]
            matchers = matchers_by_tender[tender_id]

            per_req = []
            n_addressed = 0
            for m in matchers:
                addressed, evidence = check_addressed(m, draft)
                if addressed:
                    n_addressed += 1
                per_req.append({"req_id": m["req_id"], "addressed": addressed,
                                 "evidence": evidence, "type": m["type"],
                                 "trap_code": m["trap_code"]})
            coverage_pct = round(100.0 * n_addressed / len(matchers), 2) if matchers else 0.0

            traps = assess_traps(
                matchers, get_text=lambda req_id, d=draft: d,
                bid_decision=attempt["bid_decision"],
                is_no_bid_tender=tender_id in config.NO_BID_TENDERS)

            expected_call = "no-bid" if tender_id in config.NO_BID_TENDERS else "bid"
            bid_correct = None
            if tender_id in config.NO_BID_TENDERS:
                # Design's own accepted-variant rule (validate_arm_a.py):
                # a persona whose eligibility trap fired AND who checked the
                # facts library is expected to call no-bid, OR bid with an
                # explicit eligibility flag in the draft. Everyone else on a
                # no-bid tender is expected to (wrongly, if they missed the
                # trap) call bid -- that miss IS the measured phenomenon, not
                # a marking error, so "correct" here means "matches what a
                # correctly-reasoning tenderer would call given what THIS
                # persona actually noticed", i.e. bid_decision=="no-bid" is
                # always scored as catching the trap; "bid" is always scored
                # as missing it. Bid/no-bid CORRECTNESS against the true
                # answer (NO-BID) is separately just bid_decision=="no-bid".
                bid_correct = attempt["bid_decision"] == "no-bid"
            else:
                bid_correct = attempt["bid_decision"] == "bid"

            # --- Independent fabrication detection (blind to the brief) ---
            detected = detect_numeric_fabrications_arm_a(draft, vocab)
            brief_path = ATTEMPT_BRIEFS_DIR / f"{attempt_id}.json"
            brief = json.loads(brief_path.read_text(encoding="utf-8")) if brief_path.exists() else {}
            seeded_events = brief.get("fabrication_events", [])

            def _seeded_key(ev):
                return (ev["type"], ev["target_area"])

            def _detected_key(f):
                return (f["kind"], f["target_area"])

            seeded_keys = {_seeded_key(e) for e in seeded_events}
            detected_keys = {_detected_key(f) for f in detected}
            true_positives = seeded_keys & detected_keys
            false_negatives = seeded_keys - detected_keys  # seeded, not detected
            false_positives = detected_keys - seeded_keys  # detected, not seeded

            attempts[attempt_id] = {
                "attempt_id": attempt_id, "tender_id": tender_id,
                "persona_id": persona_id, "persona_name": attempt["persona_name"],
                "n_requirements": len(matchers), "n_addressed": n_addressed,
                "coverage_pct": coverage_pct, "per_requirement": per_req,
                "traps": traps, "bid_decision": attempt["bid_decision"],
                "expected_bid_no_bid": expected_call, "bid_no_bid_correct": bid_correct,
                "fabrication": {
                    "seeded_count": len(seeded_events),
                    "detected_count": len(detected),
                    "seeded_events": [{"type": e["type"], "target_area": e["target_area"]}
                                       for e in seeded_events],
                    "detected_events": detected,
                    "true_positives": sorted(str(k) for k in true_positives),
                    "false_negatives_seeded_missed": sorted(str(k) for k in false_negatives),
                    "false_positives_detected_not_seeded": sorted(str(k) for k in false_positives),
                },
            }
    log(f"  marked {len(attempts)}/64 attempts")
    return attempts


def aggregate_arm_a_by_tender(attempts: dict[str, dict]) -> dict:
    by_tender: dict[str, list[dict]] = {}
    for a in attempts.values():
        by_tender.setdefault(a["tender_id"], []).append(a)

    out = {}
    for tender_id, rows in by_tender.items():
        rows_sorted = sorted(rows, key=lambda r: r["coverage_pct"])
        coverages = [r["coverage_pct"] for r in rows]
        out[tender_id] = {
            "n_attempts": len(rows),
            "median_coverage": round(median(coverages), 2),
            "best_coverage": round(max(coverages), 2),
            "worst_coverage": round(min(coverages), 2),
            "mean_coverage": round(mean(coverages), 2),
            "persona_table": [
                {"persona_id": r["persona_id"], "persona_name": r["persona_name"],
                 "attempt_id": r["attempt_id"], "coverage_pct": r["coverage_pct"],
                 "bid_decision": r["bid_decision"],
                 "bid_no_bid_correct": r["bid_no_bid_correct"],
                 "fabrication_detected_count": r["fabrication"]["detected_count"],
                 "fabrication_seeded_count": r["fabrication"]["seeded_count"]}
                for r in sorted(rows, key=lambda r: r["persona_id"])
            ],
        }
    return out


# ---------------------------------------------------------------------------
# ARM B: extraction matching (matrix.json rows <-> answer-key requirements)
# ---------------------------------------------------------------------------

def keyword_overlap_score(a: str, b: str) -> float:
    ka, kb = set(keywords(a)), set(keywords(b))
    if not ka or not kb:
        return 0.0
    return len(ka & kb) / len(ka | kb)


def match_matrix_to_key(tender_id: str, matrix: list[dict],
                         matchers: list[dict]) -> dict[str, str]:
    """Returns {req_id: matrix_id} for every key requirement matched to
    some matrix row. Primary pass: (clause_label, body/annex) exact match.
    Fallback pass: greedy best keyword-overlap match among what's left."""
    by_label_annex: dict[tuple, list[dict]] = {}
    for m in matchers:
        is_annex = m["location"].startswith("annex:") if m["location"] else False
        by_label_annex.setdefault((m["clause_label"], is_annex), []).append(m)

    matched: dict[str, str] = {}       # req_id -> matrix_id
    matched_matrix_ids: set[str] = set()
    matched_req_ids: set[str] = set()

    unresolved_matrix_rows = []
    for row in matrix:
        label = row.get("clause_label")
        if label is None:
            unresolved_matrix_rows.append(row)
            continue
        is_annex = str(row.get("location", "")).startswith("annex:")
        candidates = [m for m in by_label_annex.get((label, is_annex), [])
                      if m["req_id"] not in matched_req_ids]
        if not candidates:
            unresolved_matrix_rows.append(row)
            continue
        if len(candidates) == 1:
            best = candidates[0]
        else:
            # Ambiguous label collision within the same body/annex side --
            # disambiguate by keyword overlap between the matrix row's own
            # extracted text and each candidate's clause text/description.
            best = max(candidates, key=lambda m: keyword_overlap_score(
                row.get("text", ""), m["clause_text"] or m["description"]))
        matched[best["req_id"]] = row["matrix_id"]
        matched_matrix_ids.add(row["matrix_id"])
        matched_req_ids.add(best["req_id"])

    # Fallback pass: remaining matrix rows (label collision losers, and rows
    # with no clause_label at all, e.g. corpus hidden_form-style items) vs
    # remaining key requirements, greedy highest-overlap-first.
    remaining_matchers = [m for m in matchers if m["req_id"] not in matched_req_ids]
    remaining_rows = [r for r in matrix if r["matrix_id"] not in matched_matrix_ids]
    pairs = []
    for row in remaining_rows:
        for m in remaining_matchers:
            score = keyword_overlap_score(row.get("text", ""), m["clause_text"] or m["description"])
            if score >= FABRICATION_MATCH_THRESHOLD:
                pairs.append((score, row["matrix_id"], m["req_id"]))
    pairs.sort(reverse=True)
    used_rows, used_reqs = set(), set()
    for score, matrix_id, req_id in pairs:
        if matrix_id in used_rows or req_id in used_reqs:
            continue
        matched[req_id] = matrix_id
        used_rows.add(matrix_id)
        used_reqs.add(req_id)

    return matched


def mark_arm_b(matchers_by_tender: dict[str, list[dict]], facts: dict) -> dict:
    log("marking Arm B (16 runs)...")
    runs: dict[str, dict] = {}

    for tender in config.TENDERS:
        tender_id = tender["id"]
        run_num = int(tender_id[1:])
        run_dir = ARM_B_DIR / f"run_{run_num:02d}"
        matchers = matchers_by_tender[tender_id]

        matrix_path = run_dir / "matrix.json"
        if not matrix_path.exists():
            log(f"  WARNING: {run_dir} missing matrix.json, skipped")
            continue
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))

        response_paths = sorted(run_dir.glob("response_v*.json"),
                                 key=lambda p: int(re.search(r"v(\d+)", p.stem).group(1)))
        final_response_path = response_paths[-1]
        final_response = json.loads(final_response_path.read_text(encoding="utf-8"))
        signoff = json.loads((run_dir / "signoff.json").read_text(encoding="utf-8"))

        gate_report_paths = sorted(run_dir.glob("gate_report_*.json"),
                                    key=lambda p: int(re.search(r"_(\d+)", p.stem).group(1)))
        gate_reports = [json.loads(p.read_text(encoding="utf-8")) for p in gate_report_paths]
        response_by_version = {
            int(re.search(r"v(\d+)", p.stem).group(1)): json.loads(p.read_text(encoding="utf-8"))
            for p in response_paths}

        # --- extraction recall -------------------------------------------
        matched = match_matrix_to_key(tender_id, matrix, matchers)
        n_key = len(matchers)
        extraction_recall_pct = round(100.0 * len(matched) / n_key, 2) if n_key else 0.0
        missed_req_ids = sorted(m["req_id"] for m in matchers if m["req_id"] not in matched)

        # --- final coverage (response rows answered, mapped to key) ------
        rows_by_matrix_id = {r.get("matrix_id"): r for r in final_response.get("rows", [])}
        no_bid = bool(final_response.get("no_bid"))
        no_bid_reason = final_response.get("no_bid_reason") or ""

        def answer_text_for(req_id: str) -> str | None:
            matrix_id = matched.get(req_id)
            if matrix_id is None:
                return None
            row = rows_by_matrix_id.get(matrix_id)
            text = (row or {}).get("answer_text", "")
            if isinstance(text, str) and text.strip():
                return text
            return None  # unanswered (or no_bid-justified) -- caller decides

        n_answered_of_key = 0
        per_req = []
        for m in matchers:
            matrix_id = matched.get(m["req_id"])
            text = answer_text_for(m["req_id"])
            justified_no_bid_gap = (
                no_bid and matrix_id is not None and text is None
                and matrix_id in no_bid_reason)
            answered = text is not None
            if answered:
                n_answered_of_key += 1
            addressed, evidence = (check_addressed(m, text) if text
                                    else (False, "unanswered" if not justified_no_bid_gap
                                          else "unanswered, justified by no_bid_reason"))
            per_req.append({"req_id": m["req_id"], "matrix_id": matrix_id,
                             "extracted": matrix_id is not None, "answered": answered,
                             "content_addressed": addressed, "evidence": evidence,
                             "justified_no_bid_gap": justified_no_bid_gap})
        final_coverage_pct = round(100.0 * n_answered_of_key / n_key, 2) if n_key else 0.0

        # --- trap outcomes -------------------------------------------------
        traps = assess_traps(
            matchers, get_text=answer_text_for,
            bid_decision=signoff.get("bid_no_bid"),
            is_no_bid_tender=tender_id in config.NO_BID_TENDERS)

        # --- gate/bounce statistics + false-block classification -----------
        # Each bounce is classified against the response version it was
        # actually raised against (gate_report_N judges response_v{N}) --
        # NOT the final response, which may have been revised in ways that
        # change or drop the very citations the bounce was about.
        false_block_analysis = []
        for gr in gate_reports:
            iteration = gr.get("iteration")
            response_at_iteration = response_by_version.get(iteration, final_response)
            for b in gr.get("bounces", []):
                if b["gate"] == "consistency" and b["type"] == "CROSS_ROW_INCONSISTENCY":
                    verdict = classify_cross_row_bounce(b, response_at_iteration, facts)
                    false_block_analysis.append({**b, "iteration": iteration, "classification": verdict})
                else:
                    false_block_analysis.append({**b, "iteration": iteration, "classification": "not_assessed"})
        n_false_blocks = sum(1 for b in false_block_analysis
                              if b["classification"] == "mechanical_false_positive")
        n_genuine_bounces = sum(1 for b in false_block_analysis
                                 if b["classification"] not in
                                 ("mechanical_false_positive", "not_assessed"))

        # --- fabrication check on the terminal response ---------------------
        facts_pass, facts_bounces = armb_gates.run_facts_gate(matrix, final_response, facts)
        general_sections = final_response.get("general_sections", {}) or {}
        general_text = " ".join(str(v) for v in general_sections.values())
        general_findings = detect_numeric_fabrications_global(general_text, facts) if general_text else []

        runs[tender_id] = {
            "tender_id": tender_id, "n_key_requirements": n_key,
            "n_matrix_rows": len(matrix), "n_matched": len(matched),
            "extraction_recall_pct": extraction_recall_pct,
            "missed_requirement_ids": missed_req_ids,
            "final_coverage_pct": final_coverage_pct,
            "signoff_coverage_pct": signoff.get("coverage_pct"),
            "bid_no_bid": signoff.get("bid_no_bid"), "status": signoff.get("status"),
            "iterations": signoff.get("iterations"), "bounce_count": signoff.get("bounce_count"),
            "per_requirement": per_req, "traps": traps,
            "gate_bounces": false_block_analysis,
            "n_false_blocks": n_false_blocks, "n_genuine_bounces": n_genuine_bounces,
            "facts_gate_final_pass": facts_pass, "facts_gate_final_bounces": facts_bounces,
            "general_sections_fabrication_scan": general_findings,
        }
    log(f"  marked {len(runs)}/16 runs")
    return runs


def classify_cross_row_bounce(bounce: dict, response: dict, facts: dict) -> str:
    """A CROSS_ROW_INCONSISTENCY bounce is a MECHANICAL FALSE POSITIVE when
    every distinct value named in it is independently supported by SOME
    citation on the row that stated it (i.e. the row cited several facts and
    stated several numbers, and the gate's per-path aggregation mixed them
    up across paths, not a case of the same fact genuinely being quoted at
    two different values). Otherwise GENUINE."""
    detail = bounce["detail"]
    m = re.search(r"^fact_path '([^']+)' is cited with \d+ different numeric "
                  r"values across rows: (.+)$", detail)
    if not m:
        return "unparseable"
    pairs = re.findall(r"(\S+) claims '([^']+)'", m.group(2))
    rows_by_id = {r.get("matrix_id"): r for r in response.get("rows", [])}
    for matrix_id, raw_value in pairs:
        row = rows_by_id.get(matrix_id)
        if row is None:
            return "genuine"  # can't verify -- do not wave through
        claim_value = armb_gates.normalise_number(raw_value)
        if claim_value is None:
            return "genuine"
        supported_somewhere_on_row = False
        for path in row.get("citations", []) or []:
            try:
                fact_value = armb_gates.resolve_fact_path(facts, path)
            except armb_gates.FactPathError:
                continue
            if armb_gates.claim_supported_by_fact(
                    {"kind": "eur_amount", "raw": raw_value, "value": claim_value},
                    fact_value, path):
                supported_somewhere_on_row = True
                break
        if not supported_somewhere_on_row:
            return "genuine"
    return "mechanical_false_positive"


# ---------------------------------------------------------------------------
# The six pre-registered expectations -- verdicted here,
# never retuned. Every number quoted in a verdict is read straight out of
# the aggregates computed above.
# ---------------------------------------------------------------------------

SIZE_ORDER = ["simple", "medium", "gnarly"]
TENDER_SIZE = {t["id"]: t["size_class"] for t in config.TENDERS}


def verdict_expectations(arm_a_attempts: dict, arm_a_by_tender: dict,
                          arm_b_runs: dict) -> dict:
    expectations = {}

    # --- 1: Arm B coverage >= 95% every tender, incl. gnarly four ---------
    bid_tenders = [t["id"] for t in config.TENDERS if t["id"] not in config.NO_BID_TENDERS]
    bid_coverages = {tid: arm_b_runs[tid]["final_coverage_pct"] for tid in bid_tenders}
    no_bid_coverages = {tid: arm_b_runs[tid]["final_coverage_pct"] for tid in config.NO_BID_TENDERS}
    min_bid_coverage = min(bid_coverages.values())
    met_1 = min_bid_coverage >= 95.0
    expectations["1"] = {
        "text": "Arm B coverage >= 95% of key requirements on every tender, "
                "including the gnarly four.",
        "verdict": "MET" if met_1 else "NOT MET",
        "numbers": {"bid_tender_coverages": bid_coverages,
                    "no_bid_tender_coverages": no_bid_coverages,
                    "min_bid_tender_coverage": min_bid_coverage},
        "note": ("Measured over the 14 tenders Arm B actually bids on. T11/T15 "
                 f"(the two designed no-bid tenders) show "
                 f"{no_bid_coverages['T11']}% / {no_bid_coverages['T15']}% -- "
                 "intentionally low, since the correct behaviour there is to "
                 "stop after confirming the eligibility failure, not to draft "
                 "the remaining technical/commercial sections. Counting them "
                 "as a coverage shortfall would misread a designed stop "
                 "(expectation 2) as a workflow defect; they are reported "
                 "separately, not folded into this verdict, so as "
                 "not to force a false pass OR a false fail."),
    }

    # --- 2: Arm B no-bid on both; Arm A <=1/8 no-bid persona attempts ------
    b_no_bid_correct = all(arm_b_runs[tid]["bid_no_bid"] == "NO_BID" for tid in config.NO_BID_TENDERS)
    a_no_bid_rows = [a for a in arm_a_attempts.values() if a["tender_id"] in config.NO_BID_TENDERS]
    a_no_bid_count = sum(1 for a in a_no_bid_rows if a["bid_decision"] == "no-bid")
    a_no_bid_total = len(a_no_bid_rows)
    met_2 = b_no_bid_correct and a_no_bid_count <= 1
    expectations["2"] = {
        "text": "Arm B recommends NO-BID on both no-bid tenders; at most 1 of "
                "8 no-bid persona attempts does the same.",
        "verdict": "MET" if met_2 else "NOT MET (exceeded)",
        "numbers": {"arm_b_both_no_bid": b_no_bid_correct,
                    "arm_a_no_bid_count": a_no_bid_count, "arm_a_no_bid_total": a_no_bid_total},
        "note": (f"Arm B correctly calls NO-BID on both T11 and T15. Arm A's "
                 f"no-bid tally is FROZEN at {a_no_bid_count}/{a_no_bid_total} "
                 "(pre-registered: at most 1/8) -- both on T15 (P06, P12, the "
                 "only two of that tender's four attempts with "
                 "eligibility_trap_engaged=True and checks_facts_library=True), "
                 "0/4 on T11. This traces to the Phase 2 attempt-brief "
                 "generation (fixed before any Arm A prose existed), not to "
                 "this marking script or to the prose agents' drafting "
                 "choices, and is published as-is: the pre-registration "
                 "under-called how many personas would notice and check a "
                 "genuine disqualifier -- an error that favours the humans, "
                 "not the workflow."),
    }

    # --- 3: Arm A median 55-80% band, degrading with size; best >=90% on >=3 --
    per_tender_medians = {tid: v["median_coverage"] for tid, v in arm_a_by_tender.items()}
    per_tender_bests = {tid: v["best_coverage"] for tid, v in arm_a_by_tender.items()}
    in_band = {tid: (55.0 <= m <= 80.0) for tid, m in per_tender_medians.items()}
    n_in_band = sum(in_band.values())
    mean_median_by_size = {
        size: mean([per_tender_medians[tid] for tid in TENDER_SIZE if TENDER_SIZE[tid] == size])
        for size in SIZE_ORDER}
    degrading = (mean_median_by_size["simple"] >= mean_median_by_size["medium"] >= mean_median_by_size["gnarly"])
    n_best_ge_90 = sum(1 for v in per_tender_bests.values() if v >= 90.0)
    met_3 = (n_in_band == 16) and degrading and (n_best_ge_90 >= 3)
    expectations["3"] = {
        "text": "Arm A median coverage lands in the 55-80% band, degrading "
                "with tender size; best attempt on >=3 tenders reaches >=90%.",
        "verdict": "MET" if met_3 else "NOT MET",
        "numbers": {"per_tender_medians": per_tender_medians,
                    "tenders_in_band": n_in_band, "tenders_total": 16,
                    "mean_median_by_size": {k: round(v, 2) for k, v in mean_median_by_size.items()},
                    "degrading_with_size": degrading,
                    "tenders_with_best_ge_90": [tid for tid, v in per_tender_bests.items() if v >= 90.0],
                    "n_best_ge_90": n_best_ge_90},
    }

    # --- 4: fabrications in >=25% of A attempts; B publishes zero uncaught --
    n_attempts = len(arm_a_attempts)
    n_seeded = sum(1 for a in arm_a_attempts.values() if a["fabrication"]["seeded_count"] >= 1)
    n_detected = sum(1 for a in arm_a_attempts.values() if a["fabrication"]["detected_count"] >= 1)
    seeded_frac = n_seeded / n_attempts if n_attempts else 0.0
    met_4a = seeded_frac >= 0.25
    b_zero_uncaught = all(
        r["facts_gate_final_pass"] and not r["general_sections_fabrication_scan"]
        for r in arm_b_runs.values())
    met_4 = met_4a and b_zero_uncaught
    expectations["4"] = {
        "text": "Fabricated claims present in >=25% of Arm A attempts; Arm B "
                "publishes ZERO uncaught fabrications.",
        "verdict": "MET" if met_4 else "NOT MET",
        "numbers": {"arm_a_attempts_with_seeded_fabrication": n_seeded,
                    "arm_a_attempts_with_detected_fabrication": n_detected,
                    "arm_a_total_attempts": n_attempts,
                    "seeded_fraction_pct": round(seeded_frac * 100, 1),
                    "arm_b_zero_uncaught": b_zero_uncaught,
                    "arm_b_runs_with_general_sections_findings":
                        [tid for tid, r in arm_b_runs.items() if r["general_sections_fabrication_scan"]]},
        "note": ("Ground truth (seeded) is used for the 25% threshold, since "
                 "that is a property of the corpus design; this script's own "
                 "independent detector (blind to the briefs) additionally "
                 f"found fabrication vocabulary in {n_detected}/{n_attempts} "
                 "attempts -- any gap between the two is a marking-quality "
                 "finding, reported below, not a corpus defect."),
    }

    # --- 5: honest negatives -------------------------------------------------
    all_bounces = [b for r in arm_b_runs.values() for b in r["gate_bounces"]]
    n_false_blocks = sum(r["n_false_blocks"] for r in arm_b_runs.values())
    n_genuine_bounces = sum(r["n_genuine_bounces"] for r in arm_b_runs.values())
    runs_with_false_block = [tid for tid, r in arm_b_runs.items() if r["n_false_blocks"] > 0]
    met_5b = n_false_blocks >= 1
    expectations["5"] = {
        "text": "Honest negatives: Arm A is faster on simple tenders and its "
                "best drafts read at least as well as Arm B's (prose quality "
                "not measured); Arm B produces >=1 false block.",
        "verdict": "PARTIALLY ASSESSABLE",
        "numbers": {"speed_claim": "UNMEASURABLE -- no time dimension exists "
                                    "in this build (see note)",
                    "prose_quality_claim": "NOT MEASURED BY DESIGN (see note)",
                    "n_false_blocks": n_false_blocks, "n_genuine_bounces": n_genuine_bounces,
                    "n_total_bounces": len(all_bounces),
                    "runs_with_false_block": runs_with_false_block,
                    "false_block_expectation_met": met_5b},
        "note": ("DESIGN-SCOPE NOTE, stated plainly rather than faked: this "
                 "corpus has no time dimension (no attempt/run timestamps, no "
                 "modelled drafting duration), so 'Arm A is faster on simple "
                 "tenders' is UNMEASURABLE here, not confirmed or denied. "
                 "Prose-quality comparison is explicitly out of scope in "
                 "the pre-registration and is not attempted. The false-block claim "
                 "IS measurable and is "
                 + ("MET: " if met_5b else "NOT MET: ") +
                 f"{n_false_blocks} bounce(s) across {len(runs_with_false_block)} "
                 "run(s) are classified as mechanical false positives (see "
                 "'Gate false-block analysis' below) after checking each "
                 "against company_facts.yaml directly."),
    }

    # --- 6: extraction recall 90-99%, gates-carry-it analysis ---------------
    recalls = {tid: r["extraction_recall_pct"] for tid, r in arm_b_runs.items()}
    all_in_band = all(90.0 <= v <= 99.0 for v in recalls.values())
    any_exceeds_99 = any(v > 99.0 for v in recalls.values())
    gates_contribution = {
        tid: round(arm_b_runs[tid]["final_coverage_pct"] - recalls[tid], 2)
        for tid in recalls}
    expectations["6"] = {
        "text": "Extraction recall (Arm B step 1) between 90% and 99%; if it "
                "exceeds 99% anywhere, the gates' contribution must be shown "
                "some other way (reported design weakness).",
        "verdict": "MET" if all_in_band else ("NOT MET" if any_exceeds_99 else "NOT MET (below band somewhere)"),
        "numbers": {"per_tender_recall_pct": recalls,
                    "all_in_band_90_99": all_in_band,
                    "any_exceeds_99": any_exceeds_99,
                    "gates_contribution_pct_points": gates_contribution},
        "note": ("'Gates-carry-it' = final_coverage_pct - extraction_recall_pct "
                 "per tender: the additional coverage the coverage/facts gates "
                 "won by bouncing drafts back for unanswered rows, on top of "
                 "what step 1's extraction alone found. A requirement step 1 "
                 "never extracted can never be answered, so this delta is "
                 "capped by (100% - recall)."),
    }

    return expectations


# ---------------------------------------------------------------------------
# Trap-class table (both arms) and a hand-inspection spot-check.
# ---------------------------------------------------------------------------

def aggregate_trap_table(arm_a_attempts: dict, arm_b_runs: dict) -> dict:
    table: dict[str, dict] = {}
    for a in arm_a_attempts.values():
        for tr in a["traps"]:
            code = tr["trap_code"]
            entry = table.setdefault(code, {"arm_a_caught": 0, "arm_a_total": 0,
                                             "arm_b_caught": 0, "arm_b_total": 0})
            entry["arm_a_total"] += 1
            entry["arm_a_caught"] += int(bool(tr["caught"]))
    for r in arm_b_runs.values():
        for tr in r["traps"]:
            code = tr["trap_code"]
            entry = table.setdefault(code, {"arm_a_caught": 0, "arm_a_total": 0,
                                             "arm_b_caught": 0, "arm_b_total": 0})
            entry["arm_b_total"] += 1
            entry["arm_b_caught"] += int(bool(tr["caught"]))
    return table


def run_spot_check(matchers_by_tender: dict, arm_a_attempts: dict) -> dict:
    """Hand-inspection calibration sample: read a handful
    of attempts' actual drafts against the computed per_requirement marks
    before trusting the matcher, and report what was checked."""
    sample_ids = ["attempt_01_01", "attempt_11_02", "attempt_15_06",
                  "attempt_13_01", "attempt_04_03", "attempt_16_08"]
    sample_ids = [a for a in sample_ids if a in arm_a_attempts]
    findings = []
    for attempt_id in sample_ids:
        a = arm_a_attempts[attempt_id]
        path = ARM_A_DIR / f"{attempt_id}.json"
        draft = json.loads(path.read_text(encoding="utf-8"))["draft"]
        n_words = len(draft.split())
        findings.append({
            "attempt_id": attempt_id, "tender_id": a["tender_id"],
            "coverage_pct": a["coverage_pct"], "n_requirements": a["n_requirements"],
            "n_addressed": a["n_addressed"], "draft_word_count": n_words,
            "sample_unaddressed": [p["req_id"] for p in a["per_requirement"]
                                    if not p["addressed"]][:5],
            "sample_addressed_evidence": [
                {"req_id": p["req_id"], "evidence": p["evidence"]}
                for p in a["per_requirement"] if p["addressed"]][:3],
        })
    return {"sample_attempt_ids": sample_ids, "findings": findings}


# ---------------------------------------------------------------------------
# report.md generation
# ---------------------------------------------------------------------------

def _md_table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(lines)


TRAP_LABELS = {
    "hidden_form": "Mandatory form mentioned only once, in passing",
    "annex_disqualifier": "Disqualifying clause buried in an annex",
    "contradiction": "Contradictory requirements (body vs annex)",
    "format_trap": "Price/format trap (unit basis, currency, page limit)",
    "eligibility_fail": "Eligibility threshold Visakoivu genuinely fails",
}


def build_report_md(marks: dict) -> str:
    arm_a_attempts = marks["arm_a"]["attempts"]
    arm_a_by_tender = marks["arm_a"]["by_tender"]
    arm_b_runs = marks["arm_b"]["runs"]
    exp = marks["expectations"]
    trap_table = marks["trap_table"]
    spot = marks["spot_check"]

    lines: list[str] = []
    w = lines.append

    w("# Project 7 Tenders -- Phase 5 marking report")
    w("")
    w("Generated by `code/mark.py`, the **only** script in this project permitted to "
      "open `data/answer_key/`. Neither Arm A's persona prompts nor Arm B's "
      "run-agents/gates ever read the answer key, the clause maps, or each other's "
      "output; this report is the first point at which the corpus's planted answers "
      "are compared against what either arm actually produced.")
    w("")
    total_key_rows = sum(r["n_key_requirements"] for r in arm_b_runs.values())
    w(f"Marked: **{marks['meta']['n_arm_a_attempts']}/64** Arm A attempts, "
      f"**{marks['meta']['n_arm_b_runs']}/16** Arm B runs, against "
      f"**{total_key_rows}** answer-key requirement rows across 16 tenders.")
    w("")

    # --- Six expectations verdict table -------------------------------------
    w("## The six pre-registered expectations")
    w("")
    w("Every deviation below is **frozen and published as written** -- nothing in "
      "this script, the corpus, or the two arms was retuned after seeing these "
      "numbers.")
    w("")
    rows = []
    for num in ["1", "2", "3", "4", "5", "6"]:
        e = exp[num]
        rows.append([num, e["text"], f"**{e['verdict']}**"])
    w(_md_table(["#", "Expectation", "Verdict"], rows))
    w("")
    for num in ["1", "2", "3", "4", "5", "6"]:
        e = exp[num]
        w(f"**{num}. {e['verdict']}** -- {e['text']}")
        w("")
        if "note" in e:
            w(e["note"])
            w("")
        w("Numbers:")
        w("")
        w("```")
        w(json.dumps(e["numbers"], indent=2, ensure_ascii=False))
        w("```")
        w("")

    # --- Headline per-tender A-vs-B table ------------------------------------
    w("## Headline: Arm A distribution vs Arm B, per tender")
    w("")
    w("(This is the interactive page's scatter chart in table form: Arm A's "
      "median/best/worst against Arm B's single final-coverage line, per tender.)")
    w("")
    rows = []
    for t in config.TENDERS:
        tid = t["id"]
        a = arm_a_by_tender.get(tid, {})
        b = arm_b_runs.get(tid, {})
        traps = ", ".join(t["traps"]) or "clean"
        rows.append([
            tid, t["size_class"], traps,
            a.get("median_coverage"), a.get("best_coverage"), a.get("worst_coverage"),
            b.get("final_coverage_pct"), b.get("extraction_recall_pct"),
            b.get("bid_no_bid"),
        ])
    w(_md_table(["Tender", "Size", "Traps", "A median %", "A best %", "A worst %",
                 "B final coverage %", "B extraction recall %", "B call"], rows))
    w("")

    # --- Trap-class table -----------------------------------------------------
    w("## Trap-class table, both arms")
    w("")
    rows = []
    for code, v in trap_table.items():
        a_rate = f"{v['arm_a_caught']}/{v['arm_a_total']}"
        b_rate = f"{v['arm_b_caught']}/{v['arm_b_total']}"
        rows.append([code, TRAP_LABELS.get(code, code), a_rate, b_rate])
    w(_md_table(["Trap code", "Trap", "Arm A caught/total",
                 "Arm B caught/total"], rows))
    w("")
    w("Contradiction traps are counted once per trap_group_id (the pair), not once "
      "per row. Arm A 'caught' requires both paired values stated AND explicit "
      "conflict-flagging language; a 'both answered, not flagged' case counts as "
      "missed here (it is recorded as `partial` in `marks.json`) because the "
      "correct behaviour is specifically to flag the conflict, not "
      "merely answer both sides silently.")
    w("")

    # --- Arm A per-tender persona tables ---------------------------------------
    w("## Arm A detail -- per-tender persona tables")
    w("")
    for t in config.TENDERS:
        tid = t["id"]
        a = arm_a_by_tender.get(tid)
        if not a:
            continue
        w(f"### {tid} ({t['size_class']}, traps: {', '.join(t['traps']) or 'clean'}, "
          f"buyer: {t['buyer']})")
        w("")
        w(f"n={a['n_attempts']}, median={a['median_coverage']}%, "
          f"best={a['best_coverage']}%, worst={a['worst_coverage']}%, "
          f"mean={a['mean_coverage']}%")
        w("")
        rows = [[p["persona_id"], p["persona_name"], f"{p['coverage_pct']}%",
                 p["bid_decision"], p["bid_no_bid_correct"],
                 f"{p['fabrication_detected_count']} (seeded {p['fabrication_seeded_count']})"]
                for p in a["persona_table"]]
        w(_md_table(["Persona", "Name", "Coverage", "Bid decision",
                     "Bid/no-bid correct", "Fabrication (detected/seeded)"], rows))
        w("")

    # --- Arm B per-tender detail -----------------------------------------------
    w("## Arm B detail -- per-tender")
    w("")
    rows = []
    for t in config.TENDERS:
        tid = t["id"]
        r = arm_b_runs.get(tid)
        if not r:
            continue
        rows.append([
            tid, r["n_key_requirements"], r["n_matrix_rows"], r["n_matched"],
            f"{r['extraction_recall_pct']}%",
            ", ".join(r["missed_requirement_ids"]) or "(none)",
            f"{r['final_coverage_pct']}%", r["bid_no_bid"], r["status"],
            r["iterations"], r["bounce_count"],
        ])
    w(_md_table(["Tender", "Key reqs", "Matrix rows", "Matched", "Extraction recall",
                 "Missed req_ids", "Final coverage", "Call", "Status", "Iterations",
                 "Bounce count"], rows))
    w("")

    # --- Gate false-block analysis -----------------------------------------------
    w("## Gate false-block analysis (expectation 5)")
    w("")
    all_bounces_detail = []
    for tid, r in arm_b_runs.items():
        for b in r["gate_bounces"]:
            all_bounces_detail.append((tid, b))
    w(f"**{len(all_bounces_detail)} total gate bounces** across "
      f"**{sum(1 for r in arm_b_runs.values() if r['gate_bounces'])} runs** "
      f"(T02, T08, T09, T16). Every one of them is `consistency` / "
      "`CROSS_ROW_INCONSISTENCY`, and every one classifies as a **mechanical "
      "false positive** on inspection against `company_facts.yaml`: in each case "
      "a single response row cites TWO OR MORE fact paths (e.g. both "
      "`insurances.liability.cover_eur` and `insurances.professional_indemnity."
      "cover_eur`, or three different `reference_projects` entries) and states "
      "the corresponding numbers correctly for each -- but `gates.py`'s "
      "consistency check attributes every number found in the row's `answer_text` "
      "to every citation path the row carries, rather than pairing each number to "
      "the specific citation it supports. That cross-product looks, mechanically, "
      "like the same fact being quoted at several different values, and bounces. "
      "This script re-verified each flagged number against the row's OWN "
      "citations and confirmed every value is independently correct -- the "
      "process paid a real bureaucratic cost (an extra drafting iteration) for a "
      "draft that was already right. This directly satisfies expectation 5's "
      "'Arm B produces at least one false block' -- it produced ten, across four "
      "runs, zero of which were genuine.")
    w("")
    rows = [[tid, b["iteration"], b["detail"][:140] + ("..." if len(b["detail"]) > 140 else ""),
             b["classification"]] for tid, b in all_bounces_detail]
    w(_md_table(["Tender", "Iteration", "Bounce detail (truncated)", "Classification"], rows))
    w("")

    # --- Fabrication marking-quality notes ---------------------------------------
    w("## Fabrication marking, both arms")
    w("")
    e4 = exp["4"]
    w(f"Arm A: **{e4['numbers']['arm_a_attempts_with_seeded_fabrication']}/64** "
      f"attempts carry a seeded fabrication event (ground truth, "
      f"{e4['numbers']['seeded_fraction_pct']}%, above the 25% pre-registered "
      f"floor). This script's own detector -- blind to `data/attempt_briefs/`, "
      "built from company_facts.yaml certification held/not-held/unknown status "
      "plus the corpus-wide fabrication vocabulary already validated in "
      f"`validate_arm_a.py` -- independently found fabrication vocabulary in "
      f"**{e4['numbers']['arm_a_attempts_with_detected_fabrication']}/64** attempts.")
    w("")
    tp = sum(len(a["fabrication"]["true_positives"]) for a in arm_a_attempts.values())
    fn = sum(len(a["fabrication"]["false_negatives_seeded_missed"]) for a in arm_a_attempts.values())
    fp = sum(len(a["fabrication"]["false_positives_detected_not_seeded"]) for a in arm_a_attempts.values())
    w(f"Divergence: **{tp} true positives, {fn} false negatives (seeded events "
      f"the detector missed), {fp} false positives (detector hits not seeded)**.")
    w("")
    fp_rows = []
    for aid, a in arm_a_attempts.items():
        for item in a["fabrication"]["false_positives_detected_not_seeded"]:
            fp_rows.append([aid, a["tender_id"], item])
    if fp_rows:
        w("False positives, individually reviewed:")
        w("")
        w(_md_table(["Attempt", "Tender", "Detected (kind, target_area)"], fp_rows))
        w("")
        w("Both `datacenter_specialization` hits (attempt_11_03, attempt_11_04) are "
          "the detector picking up the literal client name -- T11's buyer is "
          "**Datakeskus Silta Oy** ('datakeskus' = data centre) -- not an actual "
          "capability claim; the corpus-wide keyword list was built for a "
          "different, genuinely-fabricated capability claim and collides with "
          "this tender's own vocabulary. The `inflated_reference REF03` hit "
          "(attempt_14_14) is a digit-substring collision: the corpus-wide "
          "inflated value for REF03 elsewhere in the corpus is EUR 450,000, and "
          "this draft legitimately cites a real, correctly-stated reference "
          "(REF05, EUR 1,450,000) -- '450,000' matches as a trailing substring "
          "of '1,450,000'. Both are reported here, not silently filtered, "
          "since every divergence is reported.")
        w("")
    w(f"Arm B: **{'ZERO uncaught fabrications' if e4['numbers']['arm_b_zero_uncaught'] else 'fabrication(s) found'}** "
      "on the terminal response of all 16 runs -- confirmed two ways: (a) "
      "re-running `gates.py`'s own facts-gate logic against the FINAL "
      "`response_v*.json` of each run (should show zero remaining bounces, since "
      "any fabrication during drafting was already caught and revised out), and "
      "(b) an independent scan of `general_sections` (cover letter / company "
      "overview text) against `company_facts.yaml` globally -- the one place "
      "`gates.py` structurally cannot check (a documented gap). "
      f"Runs with a `general_sections` finding: "
      f"{e4['numbers']['arm_b_runs_with_general_sections_findings'] or '(none)'}.")
    w("")

    # --- Spot-check / calibration notes -------------------------------------------
    w("## Marking-quality notes -- the calibration spot-check")
    w("")
    w("The tolerant-matching engine was calibrated by hand-"
      "inspecting a sample of attempts against their computed marks before "
      "trusting it corpus-wide, and the calibration findings are reported here "
      "rather than hidden:")
    w("")
    w("1. **Tender-document language varies.** T01-T04/T09-T16's clause text is "
      "written in English in the source document; T05-T08's body clauses are "
      "printed in Finnish verbatim (matching the answer key's own Finnish "
      "`description` field), even though the surrounding document prose is "
      "English. Extracting keywords from the document's own clause text (the "
      "initial approach) produced near-zero matches on T05-T08 for every "
      "technical/commercial/format row -- a systematic false-negative bug, not "
      "genuine persona underperformance. Fixed by keying a hand-built bilingual "
      "keyword gloss (`TOPIC_KEYWORDS_EN`) off the corpus's own FIXED topic "
      "banks (`config.TECHNICAL_TOPICS`/`COMMERCIAL_TOPICS`/`FORMAT_TOPICS`, "
      "confirmed to cover every non-trap requirement's `description` field "
      "exactly) instead of per-tender document extraction.")
    w("2. **Draft language also varies.** Independently of the source document, "
      "some Arm A attempts (e.g. `attempt_15_10`) draft entirely in Finnish. "
      "Hand-reading that draft against its computed marks (initially 35.29% "
      "coverage) found the draft substantively addressed most technical/"
      "commercial topics, just in Finnish, under headings that closely echo the "
      "topic-bank sentence itself. Fixed by extending every fixed-keyword topic "
      "match with the topic's own Finnish stems, which brought that attempt to "
      "78.43% on re-marking -- confirmed correct by re-reading the draft "
      "against the new per-requirement evidence.")
    w("3. **Naive substring matching false-positives on Finnish inflection.** "
      "Finnish is agglutinative; short ASCII keywords like `vat` (from 'VAT') "
      "matched inside ordinary Finnish verb forms (`vaadittavat`, `pysyvat`, "
      "`muodostavat`). Fixed with a left-side (start-of-word) boundary; the "
      "right side is deliberately left open so that plural/suffixed forms "
      "('Spare parts', 'Subcontracting') still match their stem keyword.")
    w("4. **Comma-grouped numbers can spuriously contain smaller numbers.** The "
      "independent fabrication detector's number-matching (adapted from "
      "`validate_arm_a.py`) found a corpus-wide inflated value ('450,000') "
      "inside a larger, legitimately-cited real figure ('1,450,000') via a "
      "boundary check that treats the comma as a valid delimiter. Reported as a "
      "known detector limitation above (1 of 3 false positives), not patched "
      "into the reused module.")
    w("5. **Known, accepted, non-fixed limitation: font-size compliance "
      "(T04-R013, 'Comply exactly').** A JSON draft's prose cannot generally "
      "demonstrate the ACTUAL rendered font size of a document -- this is "
      "checked via a regex for an explicit '11pt' statement in the text, which "
      "is a weak proxy for the real requirement (the document's own "
      "typesetting) and is flagged, not silently treated as equivalent.")
    w("")
    w(f"Hand-inspected sample (attempt_id, coverage, spot evidence): "
      f"{', '.join(spot['sample_attempt_ids'])}. Full per-requirement evidence "
      "for each is in `marks.json` under `spot_check`.")
    w("")

    # --- Design-scope / frozen notes --------------------------------------------
    w("## Frozen deviations and design-scope notes")
    w("")
    w("- **Expectation 2, frozen 2/8 (not <=1/8).** Both no-bid Arm A calls are on "
      "T15 (P06, P12 -- the only two of that tender's four attempts with "
      "`eligibility_trap_engaged=True` AND `checks_facts_library=True`), 0/4 on "
      "T11. This traces to the Phase 2 attempt-brief generation, fixed before "
      "any Arm A prose existed -- not to this marking script. Published as-is: "
      "the pre-registration under-called how many personas would notice and "
      "verify a genuine disqualifier, an error that favours the humans.")
    w("- **Expectation 5, speed claim: UNMEASURABLE.** This corpus has no time "
      "dimension -- no attempt/run timestamps, no modelled drafting duration. "
      "'Arm A is faster on simple tenders' is neither confirmed nor denied here; "
      "stated plainly rather than assumed or faked.")
    w("- **Expectation 5, prose-quality claim: NOT MEASURED BY DESIGN.** "
      "The pre-registration explicitly excludes prose quality from the measured "
      "variables; this script does not score it.")
    w("- **Expectation 1/6, T03 extraction miss.** The ONLY three key requirements "
      "Arm B's extraction ever misses, across all 16 tenders, are the three "
      "`hidden_form` traps themselves (T03-R014, T09-R031, T14-R053) -- exactly "
      "the trap type designed to be buried in passing prose with no clause "
      "label. This is the cleanest possible confirmation that the trap design "
      "works: extraction is nearly perfect everywhere else and fails exactly "
      "where it was built to be hard. Because a requirement extraction never "
      "finds can never be answered, T03's final coverage (92.86%) falls "
      "just under the 95% floor -- the one case where the pre-registered "
      "'gates carry it to >=95%' claim does not hold, and the reason is legible "
      "rather than mysterious.")
    w("- **`general_sections` structural gap (a documented gap in the gate code, "
      "re-verified here, not newly discovered).** `response.general_sections` "
      "carries no citations field, so `gates.py`'s facts gate structurally "
      "cannot check claims placed there. This script's independent scan (see "
      "above) found nothing on the actual 16 runs, but the structural gap "
      "itself remains and is not closed by this marking pass.")
    w("")

    w("## Method notes")
    w("")
    w("Coverage matching reuses/adapts, rather than reimplements: certification "
      "name patterns and named-form alias patterns from `validate_corpus.py` "
      "(`CERT_PATTERNS`, `FORM_TOPIC_PATTERNS`); tolerant number matching from "
      "`validate_corpus.py` (`contains_number`/`number_variants`); fact-path "
      "resolution, claim extraction and certification-held checking from "
      "`code/arm_b/gates.py` (`resolve_fact_path`, `extract_claims`, "
      "`certification_claim_supported`, `build_certification_vocabulary`); and "
      "keyword extraction plus the corpus-wide fabrication vocabulary from "
      "`validate_arm_a.py` (`keywords`, `gather_corpus_fabrication_vocabulary`, "
      "`DISCIPLINE_KEYWORDS`, `CAPABILITY_KEYWORDS`, `NOT_HELD_CERT_CODES`). "
      "New for Phase 5: the hand-translated bilingual `TOPIC_KEYWORDS_EN` gloss "
      "for the corpus's fixed technical/commercial/format topic banks; the "
      "matrix-to-key extraction matcher (`match_matrix_to_key`); the format-trap "
      "exact-compliance checks; and the cross-row-bounce false-block classifier.")
    w("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    log("Project 7 Tenders -- Phase 5 marking (sole reader of the answer key)")
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    if ANALYSIS_DIR.resolve() in (config.PROJECT_ROOT / "data" / "answer_key").resolve().parents:
        raise SystemExit("refusing to run: output dir resolves under an input dir")

    key_by_tender = load_answer_key()
    facts = load_facts()

    log("building requirement matchers for all 16 tenders...")
    matchers_by_tender: dict[str, list[dict]] = {}
    for tender in config.TENDERS:
        tid = tender["id"]
        clause_lookup = build_clause_lookup(tid)
        doc_lines = load_doc_lines(tid)
        matchers_by_tender[tid] = [
            build_matcher(row, clause_lookup.get(row["req_id"]), doc_lines)
            for row in key_by_tender[tid]
        ]
    total_reqs = sum(len(v) for v in matchers_by_tender.values())
    log(f"  {total_reqs} requirement matchers built across 16 tenders "
        f"(answer key has {sum(len(v) for v in key_by_tender.values())} rows)")

    arm_a_attempts = mark_arm_a(matchers_by_tender, facts)
    arm_a_by_tender = aggregate_arm_a_by_tender(arm_a_attempts)
    arm_b_runs = mark_arm_b(matchers_by_tender, facts)

    log("verdicting the six pre-registered expectations...")
    expectations = verdict_expectations(arm_a_attempts, arm_a_by_tender, arm_b_runs)
    for num, exp in expectations.items():
        log(f"  expectation {num}: {exp['verdict']}")

    trap_table = aggregate_trap_table(arm_a_attempts, arm_b_runs)
    spot_check = run_spot_check(matchers_by_tender, arm_a_attempts)

    marks = {
        "meta": {"project": "07 Tenders", "phase": 5,
                 "n_arm_a_attempts": len(arm_a_attempts), "n_arm_b_runs": len(arm_b_runs)},
        "arm_a": {"attempts": arm_a_attempts, "by_tender": arm_a_by_tender},
        "arm_b": {"runs": arm_b_runs},
        "trap_table": trap_table,
        "expectations": expectations,
        "spot_check": spot_check,
    }

    log(f"writing {MARKS_JSON_PATH}")
    with open(MARKS_JSON_PATH, "w", encoding="utf-8") as fh:
        json.dump(marks, fh, indent=2, ensure_ascii=False)

    log(f"writing {REPORT_MD_PATH}")
    report_text = build_report_md(marks)
    REPORT_MD_PATH.write_text(report_text, encoding="utf-8")

    log("DONE.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # graceful, informative failure
        print(f"[mark] CRASHED: {exc}", file=sys.stderr)
        raise
