"""Phase 2 corpus INTEGRITY checker for Project 7 (Tenders) -- Job 3 of the
pre-arm normalisation pass.

Distinct from validate_structure.py (which checks the STRUCTURED data --
CSVs, JSON briefs, the facts library -- against config.py). This script
checks the other side of the corpus: does the PROSE in data/tenders/*.md
actually say what the answer key claims it says, in the place the answer
key claims it says it?

Checks performed:
  1. Substance traceability. For every requirement in the answer key that
     carries a checkable numeric threshold or a named certification, the
     number/certification is looked up (via clause_map_NN.json, itself
     re-verified for completeness against the answer key) in the EXACT
     clause the map says it lives at, tolerant of thousands-separator and
     phrasing differences (numbers exact, certification names via a small
     bilingual alias table).
  2. Named forms. Every form-type requirement's topic (e.g. "Referenssilomake
     (Liite 2)") is looked up via the same alias table.
  3. Hidden-form traps appear EXACTLY ONCE in their tender's document (this
     is the general form of the T03 defect fixed in Job 1 -- re-checked
     corpus-wide as a regression guard).
  4. Contradiction traps: both linked values (body and annex) are present,
     in their distinct locations.
  5. Eligibility-fail traps are unsoftened: no hedging word from a small
     blacklist appears in the few lines around the trap clause.
  6. Invented dates: every tender's submission deadline is on/after its own
     publication/issue date, and no tender requires a certification whose
     company_facts.yaml valid_until falls before that tender's deadline.

Exits 1 on any FAIL. AMBIGUOUS findings are reported but do not fail the
run: anything ambiguous is reported rather than forced.

Run: python validate_corpus.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd
import yaml

import config

FAILURES: list[str] = []
AMBIGUOUS: list[str] = []
FIXES_LOGGED: list[str] = []

TENDERS_DIR = config.DATA_DIR / "tenders"

MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11,
    "December": 12,
}


def log(message: str) -> None:
    print(f"[validate_corpus] {message}", flush=True)


def fail(message: str) -> None:
    FAILURES.append(message)
    print(f"[validate_corpus] FAIL: {message}", flush=True)


def ambiguous(message: str) -> None:
    AMBIGUOUS.append(message)
    print(f"[validate_corpus] AMBIGUOUS: {message}", flush=True)


def ok(message: str) -> None:
    print(f"[validate_corpus] OK: {message}", flush=True)


# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------

def load_doc_lines(tender_id: str) -> list[str]:
    path = TENDERS_DIR / f"tender_{tender_id[1:]}.md"
    return path.read_text(encoding="utf-8").split("\n")


def load_clause_map(tender_id: str) -> dict:
    path = TENDERS_DIR / f"clause_map_{tender_id[1:]}.json"
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_requirements(tender_id: str) -> pd.DataFrame:
    path = config.ANSWER_KEY_DIR / f"requirements_{tender_id[1:]}.csv"
    df = pd.read_csv(path, keep_default_na=False)
    df["mentioned_once_bool"] = (
        df["mentioned_once"].astype(str).str.strip().str.lower() == "true")
    return df


BODY_HEADER_RE = re.compile(r"^##\s+(\d+)\.\s")
ANNEX_HEADER_RE = re.compile(r"^#{1,2}\s*(?:Liite|Annex)\s+([A-Z])\b")
SUBSECTION_RE = re.compile(r"^###\s+(\d+)\.\s")


def annotate_context(lines: list[str]) -> list[str]:
    """Tag every line with the SAME doc_location string build_clause_maps.py
    uses ("body section N" / "Liite X, subsection N" / "Liite X"), so a
    clause label like "2.1" -- which is NOT globally unique, it recurs once
    per body section and once per annex subsection -- can be looked up in
    the right place instead of matching the first occurrence anywhere in
    the file."""
    context = []
    mode, body_section, annex_letter, subsection = None, None, None, None
    for line in lines:
        m_body = BODY_HEADER_RE.match(line)
        m_annex = ANNEX_HEADER_RE.match(line)
        m_sub = SUBSECTION_RE.match(line)
        if m_body:
            mode, body_section, subsection = "body", m_body.group(1), None
        elif m_annex:
            mode, annex_letter, subsection = "annex", m_annex.group(1), None
        elif m_sub and mode == "annex":
            subsection = m_sub.group(1)
        if mode == "body":
            context.append(f"body section {body_section}")
        elif mode == "annex" and subsection is not None:
            context.append(f"Liite {annex_letter}, subsection {subsection}")
        elif mode == "annex":
            context.append(f"Liite {annex_letter}")
        else:
            context.append(None)
    return context


def extract_clause_text(lines: list[str], label: str | None,
                         doc_location: str | None = None) -> str | None:
    """Pull the actual sentence printed at a given clause label, handling
    both the ordinary "LABEL text..." line and T13's nested-bold-title case
    (a "**LABEL Title**" line immediately followed, on the next non-blank
    line, by the real requirement sentence with no leading number). Scoped
    to `doc_location` when given, since labels repeat across sections."""
    if label is None:
        return None
    plain_re = re.compile(rf"^{re.escape(label)}\s+(.*)$")
    nested_re = re.compile(rf"^\*\*{re.escape(label)}\s+.*\*\*$")
    contexts = annotate_context(lines) if doc_location is not None else None
    for i, line in enumerate(lines):
        if contexts is not None and contexts[i] != doc_location:
            continue
        m = plain_re.match(line)
        if m:
            return m.group(1)
        if nested_re.match(line):
            for j in range(i + 1, len(lines)):
                if lines[j].strip():
                    return lines[j]
    return None


# ---------------------------------------------------------------------------
# Rule 0: re-verify clause map completeness against the answer key (never
# trust build_clause_maps.py's own claim -- recompute independently).
# ---------------------------------------------------------------------------

def check_clause_map_completeness() -> dict[str, dict]:
    """Returns {tender_id: {req_id: (clause_label_or_None, doc_location)}}."""
    result: dict[str, dict] = {}
    for tender in config.TENDERS:
        tid = tender["id"]
        requirements = load_requirements(tid)
        cmap = load_clause_map(tid)
        clause_ids = {c["req_id"]: (c["clause_label"], c["doc_location"])
                      for c in cmap["clauses"]}
        real_ids = set(requirements["req_id"])
        if set(clause_ids) != real_ids:
            missing = real_ids - set(clause_ids)
            extra = set(clause_ids) - real_ids
            fail(f"{tid}: clause_map_{tid[1:]}.json does not cover exactly "
                 f"the answer key's requirements (missing={missing or None}, "
                 f"extra={extra or None})")
        for req_id in requirements.loc[requirements["mentioned_once_bool"], "req_id"]:
            label = clause_ids.get(req_id, (None, None))[0]
            if label is not None:
                fail(f"{tid}: {req_id} is flagged mentioned_once but "
                     f"clause_map gives it a visible label {label!r}")
        result[tid] = clause_ids
    if not FAILURES:
        ok("clause maps re-verified complete and consistent against the "
           "answer key for all 16 tenders")
    return result


# ---------------------------------------------------------------------------
# Rule 1/2: substance traceability -- numbers, certifications, named forms.
# ---------------------------------------------------------------------------

CERT_PATTERNS = {
    "NMSB7310": [r"NMSB\s*7310"],
    "NMSB74210": [r"NMSB\s*74210"],
    "NMSB73710": [r"NMSB[\s/]*(?:IEC\s*)?73710"],
    "LUSA": [r"LUSA"],
    "URAKKAVARMENNE": [r"Urakkavarmenne"],
    "FKAASU": [r"F-gas", r"F-kaasu"],
    "SAHKOURAKOINTI": [r"[Ee]lectrical contracting", r"[Ss]ahkourakointi", r"[Ss]ähköurakointi"],
}

FORM_TOPIC_PATTERNS = {
    "Tarjouslomake (Liite 1)": [r"Tarjouslomake", r"[Tt]ender [Ff]orm"],
    "Referenssilomake (Liite 2)": [r"Referenssilomake", r"[Rr]eference [Ff]orm"],
    "Alihankkijaluettelo (Liite 3)": [r"Alihankkijaluettelo", r"subcontractor list",
                                       r"list of subcontractors"],
    "Todistus verojen maksusta": [r"verojen maks", r"tax payment", r"payment of.{0,20}taxes", r"[Cc]ertificate of tax"],
    "Todistus elakevakuutusmaksuista": [r"elakevakuutusmaksu", r"pension insurance"],
    "Vakuutustodistus": [r"[Vv]akuutustodistus", r"[Ii]nsurance certificate", r"certificate of insurance"],
    "Avainhenkiloiden CV:t": [r"\bCV", r"[Cc]urricul"],
    "Laatujarjestelman kuvaus": [r"[Ll]aatujarjestelm", r"quality (management )?system"],
    "Ymparistojarjestelman kuvaus": [r"[Yy]mparistojarjestelm", r"environmental management system"],
    "Salassapitositoumus": [r"[Ss]alassapitositoumus", r"[Cc]onfidentiality undertaking"],
    "Kaupparekisteriote": [r"[Kk]aupparekisteriote", r"[Tt]rade register extract"],
    "Valtakirja allekirjoittajalle": [r"[Vv]altakirja", r"[Pp]ower of attorney"],
}


def number_variants(raw: str) -> list[str]:
    try:
        n = int(float(raw))
    except ValueError:
        return [raw]
    return [str(n), f"{n:,}", f"{n:,}".replace(",", " ")]


def contains_number(text: str, raw: str) -> bool:
    return any(v in text for v in number_variants(raw))


def check_eligibility_substance(clause_ids_by_tender: dict[str, dict]) -> None:
    checked = 0
    for tender in config.TENDERS:
        tid = tender["id"]
        lines = load_doc_lines(tid)
        requirements = load_requirements(tid)
        for _, row in requirements[requirements["type"] == "eligibility"].iterrows():
            label, doc_location = clause_ids_by_tender[tid].get(row["req_id"], (None, None))
            text = extract_clause_text(lines, label, doc_location)
            if text is None:
                fail(f"{tid}/{row['req_id']}: clause label {label!r} not "
                     f"found in the document text (expected in {doc_location!r})")
                continue
            check_type = row["eligibility_check_type"]
            param = str(row["eligibility_check_param"])
            checked += 1
            if check_type == "has_certification":
                patterns = CERT_PATTERNS.get(param, [])
                if not any(re.search(p, text, re.IGNORECASE) for p in patterns):
                    fail(f"{tid}/{row['req_id']} (clause {label}): expected "
                         f"certification '{param}' not found in clause text: "
                         f"{text!r}")
            elif check_type == "min_staff_discipline":
                discipline, minimum = param.split(":")
                if not contains_number(text, minimum):
                    fail(f"{tid}/{row['req_id']} (clause {label}): expected "
                         f"staff threshold '{minimum}' not found in: {text!r}")
            elif check_type == "insurance_min":
                kind, minimum = param.split(":")
                if not contains_number(text, minimum):
                    fail(f"{tid}/{row['req_id']} (clause {label}): expected "
                         f"insurance amount '{minimum}' not found in: {text!r}")
            elif check_type in ("min_turnover", "min_reference_count",
                                 "min_single_reference_value", "min_equity_ratio"):
                if not contains_number(text, param):
                    fail(f"{tid}/{row['req_id']} (clause {label}): expected "
                         f"number '{param}' not found in: {text!r}")
            else:
                ambiguous(f"{tid}/{row['req_id']}: unrecognised eligibility "
                          f"check_type '{check_type}' -- not checked")
    if not FAILURES:
        ok(f"eligibility substance traceability -- {checked} eligibility "
           f"requirements checked, every threshold/certification found at "
           f"its mapped clause")


def check_form_substance(clause_ids_by_tender: dict[str, dict]) -> None:
    checked, unmatched = 0, []
    for tender in config.TENDERS:
        tid = tender["id"]
        lines = load_doc_lines(tid)
        requirements = load_requirements(tid)
        for _, row in requirements[requirements["type"] == "form"].iterrows():
            if row["mentioned_once_bool"]:
                continue  # hidden-form traps checked separately (Rule 3)
            label, doc_location = clause_ids_by_tender[tid].get(row["req_id"], (None, None))
            text = extract_clause_text(lines, label, doc_location)
            if text is None:
                fail(f"{tid}/{row['req_id']}: clause label {label!r} not "
                     f"found in the document text (expected in {doc_location!r})")
                continue
            checked += 1
            topic = row["description"]
            patterns = FORM_TOPIC_PATTERNS.get(topic)
            if patterns is None:
                ambiguous(f"{tid}/{row['req_id']}: no alias patterns "
                          f"registered for form topic {topic!r} -- not checked")
                continue
            if not any(re.search(p, text, re.IGNORECASE) for p in patterns):
                unmatched.append(f"{tid}/{row['req_id']} (clause {label}, "
                                  f"topic {topic!r}): not found in: {text!r}")
    for m in unmatched:
        fail(m)
    if not FAILURES:
        ok(f"named-form traceability -- {checked} form requirements checked "
           f"against their alias patterns")


# ---------------------------------------------------------------------------
# Rule 3: hidden-form traps appear EXACTLY ONCE (regression guard for the
# T03 defect class fixed in Job 1).
# ---------------------------------------------------------------------------

def check_hidden_form_uniqueness() -> None:
    checked = 0
    for tender in config.TENDERS:
        tid = tender["id"]
        requirements = load_requirements(tid)
        hidden = requirements[requirements["trap_code"] == "hidden_form"]
        if hidden.empty:
            continue
        full_text = "\n".join(load_doc_lines(tid))
        for _, row in hidden.iterrows():
            m = re.search(r"Tarjoukseen on liitettava myos: (.+)\.\"?$",
                           row["description"].rstrip())
            topic = m.group(1) if m else None
            if topic is None:
                ambiguous(f"{tid}/{row['req_id']}: could not parse the "
                          f"hidden-form topic out of its own description")
                continue
            patterns = FORM_TOPIC_PATTERNS.get(topic)
            if patterns is None:
                ambiguous(f"{tid}/{row['req_id']}: no alias patterns for "
                          f"hidden-form topic {topic!r} -- uniqueness not checked")
                continue
            checked += 1
            n_occurrences = 0
            for p in patterns:
                n_occurrences += len(re.findall(p, full_text))
            # A topic can legitimately be named by more than one alias
            # pattern matching the SAME sentence (e.g. both a Finnish and
            # an English pattern hitting the one buried mention), so count
            # distinct LINES that match any pattern, not raw pattern hits.
            matching_lines = [ln for ln in full_text.split("\n")
                               if any(re.search(p, ln) for p in patterns)]
            if len(matching_lines) != 1:
                fail(f"{tid}/{row['req_id']}: hidden-form topic {topic!r} "
                     f"appears on {len(matching_lines)} line(s) in the "
                     f"document, expected exactly 1 -- {matching_lines}")
    if not FAILURES:
        ok(f"hidden-form uniqueness -- {checked} hidden-form traps checked, "
           f"each appears exactly once in its tender's document")


# ---------------------------------------------------------------------------
# Rule 4: contradiction traps -- both linked values present, distinct
# locations.
# ---------------------------------------------------------------------------

def check_contradictions(clause_ids_by_tender: dict[str, dict]) -> None:
    checked = 0
    for tender in config.TENDERS:
        tid = tender["id"]
        if "contradiction" not in tender["traps"]:
            continue
        requirements = load_requirements(tid)
        contra = requirements[requirements["trap_code"] == "contradiction"]
        for group_id, rows in contra.groupby("trap_group_id"):
            if len(rows) != 2:
                fail(f"{tid}: contradiction group {group_id} has {len(rows)} "
                     f"rows, expected 2")
                continue
            lines = load_doc_lines(tid)
            checked += 1
            for _, row in rows.iterrows():
                label, doc_location = clause_ids_by_tender[tid].get(row["req_id"], (None, None))
                text = extract_clause_text(lines, label, doc_location)
                if text is None:
                    fail(f"{tid}/{row['req_id']}: clause label {label!r} "
                         f"not found in the document text (expected in "
                         f"{doc_location!r})")
                    continue
                m = re.search(r"(\d+)", row["description"])
                if m and not contains_number(text, m.group(1)):
                    fail(f"{tid}/{row['req_id']} (clause {label}): expected "
                         f"contradiction value '{m.group(1)}' not found in: "
                         f"{text!r}")
    if not FAILURES:
        ok(f"contradiction traps -- {checked} pairs checked, both values "
           f"present in their distinct locations")


# ---------------------------------------------------------------------------
# Rule 5: eligibility-fail traps unsoftened (no hedging nearby).
# ---------------------------------------------------------------------------

HEDGE_BLACKLIST = ["note that", "please note", "important", "please ensure",
                   "huomioi", "tarkeaa", "muista tarkistaa", "kindly"]


def check_eligibility_traps_unsoftened() -> None:
    checked = 0
    for tid in config.NO_BID_TENDERS:
        lines = load_doc_lines(tid)
        requirements = load_requirements(tid)
        trap = requirements[requirements["trap_code"] == "eligibility_fail"]
        if trap.empty:
            fail(f"{tid}: no eligibility_fail row found in the answer key "
                 f"(expected exactly one, this is a designed no-bid tender)")
            continue
        row = trap.iloc[0]
        cmap = load_clause_map(tid)
        clause_entry = next((c for c in cmap["clauses"]
                             if c["req_id"] == row["req_id"]), None)
        label = clause_entry["clause_label"] if clause_entry else None
        doc_location = clause_entry["doc_location"] if clause_entry else None
        text = extract_clause_text(lines, label, doc_location)
        if text is None:
            fail(f"{tid}/{row['req_id']}: eligibility-fail trap clause "
                 f"{label!r} not found in the document")
            continue
        # Look at a small window around the clause (previous + next
        # non-blank line) for hedging language, not just the clause itself.
        idx = next(i for i, l in enumerate(lines) if text in l)
        window = "\n".join(lines[max(0, idx - 2):idx + 3]).lower()
        checked += 1
        hits = [w for w in HEDGE_BLACKLIST if w in window]
        if hits:
            fail(f"{tid}/{row['req_id']} (clause {label}): hedging "
                 f"language {hits} found near the eligibility-fail trap "
                 f"-- it should read as an ordinary, unsoftened requirement")
    if not FAILURES:
        ok(f"eligibility-fail traps unsoftened -- {checked} checked, no "
           f"hedging language found nearby")


# ---------------------------------------------------------------------------
# Rule 6: invented dates.
# ---------------------------------------------------------------------------

def parse_date_from_line(line: str) -> tuple | None:
    m = re.search(r"(\d{1,2})\s+(January|February|March|April|May|June|July|"
                  r"August|September|October|November|December)\s+(\d{4})", line)
    if m:
        return (int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", line)
    if m:
        return (int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


ISSUE_LABELS = ["Issued:", "Notice published:", "Published:", "Date of issue:"]
DEADLINE_LABELS = ["Tender deadline:", "Quotation deadline:", "Submission deadline:",
                    "Closing date and time for tenders:",
                    "Closing date and time for quotations:"]
DEADLINE_EXCLUDE = ["clarifying questions", "for questions"]


def find_issue_and_deadline(tender_id: str, lines: list[str]) -> tuple:
    issue_date = None
    for line in lines:
        if any(lbl in line for lbl in ISSUE_LABELS):
            d = parse_date_from_line(line)
            if d:
                issue_date = d
                break

    deadline_date = None
    for line in lines:
        if any(lbl in line for lbl in DEADLINE_LABELS) and not any(
                ex in line for ex in DEADLINE_EXCLUDE):
            d = parse_date_from_line(line)
            if d:
                deadline_date = d
                break
    if deadline_date is None:
        # T01-T04-style deadline given as bold prose within a submission
        # sentence rather than a labelled metadata line, e.g. "no later
        # than **14 April 2026, 12:00**" or "submitted ... by **15 May
        # 2026, 12:00**".
        for line in lines:
            lower = line.lower()
            if "no later than" in lower or (
                    "must be submitted" in lower and " by " in lower):
                d = parse_date_from_line(line)
                if d:
                    deadline_date = d
                    break
    return issue_date, deadline_date


def check_dates() -> None:
    facts_path = config.FACTS_DIR / "company_facts.yaml"
    with open(facts_path, "r", encoding="utf-8") as fh:
        facts = yaml.safe_load(fh)
    cert_expiry = {c["code"]: c["valid_until"] for c in facts["certifications"] if c["held"]}

    n_checked = 0
    for tender in config.TENDERS:
        tid = tender["id"]
        lines = load_doc_lines(tid)
        issue_date, deadline_date = find_issue_and_deadline(tid, lines)
        if issue_date is None or deadline_date is None:
            ambiguous(f"{tid}: could not confidently parse both an issue "
                      f"date and a deadline date from the document text "
                      f"(issue={issue_date}, deadline={deadline_date}) -- "
                      f"skipped, not failed")
            continue
        n_checked += 1
        if deadline_date < issue_date:
            fail(f"{tid}: deadline {deadline_date} predates its own "
                 f"publication/issue date {issue_date}")

        requirements = load_requirements(tid)
        cert_rows = requirements[requirements["eligibility_check_type"] == "has_certification"]
        for _, row in cert_rows.iterrows():
            code = row["eligibility_check_param"]
            valid_until = cert_expiry.get(code)
            if valid_until is None:
                continue  # not held / no expiry -- eligibility_pass already covers this
            y, m, d = (int(x) for x in valid_until.split("-"))
            if (y, m, d) < deadline_date:
                fail(f"{tid}/{row['req_id']}: requires certification "
                     f"'{code}' valid until {valid_until}, which is BEFORE "
                     f"this tender's deadline {deadline_date} -- Visakoivu "
                     f"would not hold a valid certificate at submission time")
    if not FAILURES:
        ok(f"invented dates -- {n_checked}/16 tenders had both dates "
           f"parsed and checked; no deadline predates its issue date; no "
           f"required certification would have lapsed by its deadline")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("[validate_corpus] Project 7 Tenders -- Job 3 corpus integrity checks", flush=True)
    clause_ids_by_tender = check_clause_map_completeness()
    check_eligibility_substance(clause_ids_by_tender)
    check_form_substance(clause_ids_by_tender)
    check_hidden_form_uniqueness()
    check_contradictions(clause_ids_by_tender)
    check_eligibility_traps_unsoftened()
    check_dates()

    print("", flush=True)
    if AMBIGUOUS:
        print(f"[validate_corpus] {len(AMBIGUOUS)} AMBIGUOUS finding(s) -- "
              f"reported above, not treated as failures.", flush=True)
    if FAILURES:
        print(f"[validate_corpus] {len(FAILURES)} FAILURE(S) -- corpus is not valid.",
              file=sys.stderr)
        return 1
    print("[validate_corpus] ALL CHECKS PASSED.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # graceful, informative failure
        print(f"[validate_corpus] CRASHED: {exc}", file=sys.stderr)
        raise
