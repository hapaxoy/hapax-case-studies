# Provenance
# ----------
# CATEGORY: Expiration Date
# TRUST: one-sided (10 accepted positives, 0 accepted negatives — this matcher
#        may only ever confirm "present", never assert "absent")
# INDUCTION SET SIZE: 10 contracts (commission c05-expiration-date)
# DATE: 2026-07-03
# BRIEF: overseer_brief_v1
#
# Plain-language description of the induced patterns and known limits
# ---------------------------------------------------------------------
# Across the 10 accepted extractions, the model's "Expiration Date" answer was
# produced one of three ways:
#   (1) The contract states the end date of the Term outright ("...ending on
#       January 31, 2025", "...shall terminate on December 31, 2034"). No
#       arithmetic — just extraction.
#   (2) The contract states a base date (usually the contract date in the
#       opening/preamble sentence, sometimes an explicit commencement date
#       inside the Term clause itself) plus a duration in the "word (N) unit"
#       legal-drafting form ("six (6) months", "three (3) years", "twelve
#       (12) months"), with the Term clause referring back to that base date
#       via one of a small set of fixed phrases ("commencing on the Effective
#       Date", "from and after the Effective Date", "from the Effective
#       Date", "from the date hereof", "effective as of the date first
#       stated above", or an embedded "commence[d] upon <date>"). The answer
#       is base date + duration, computed with ordinary calendar arithmetic
#       (month/year rollover, end-of-month clamping for the 30th/31st -> a
#       shorter month).
#   (3) Two of the ten induction contracts have no computable date at all and
#       the accepted answer is the literal string "UNDETERMINED" (still
#       present=True — a termination/expiration concept exists, just not a
#       fixed date): one because the Term's own duration depends on a blank,
#       never-filled-in execution date ("EXECUTED this ________ day of
#       ______________, in the year ____________"); the model in this
#       induction set never showed the sibling pattern this matcher would
#       need (a purely event/condition-triggered Termination clause with NO
#       Term/duration language anywhere in the contract) generalising safely
#       from a single example, so that specific contract
#       (SUNTRONCORP ... MAINTENANCE AGREEMENT) is a deliberate, documented
#       miss: this matcher raises NoMatch on it rather than guess at a
#       pattern seen only once.
#
# What this matcher covers, narrowly:
#   - Six fixed "Term clause" skeletons (T1-T6 below), each requiring the
#     literal anchor phrase from the induction example it was drawn from —
#     NOT a generic "duration near the words Effective Date" search, because
#     that generic search produces false positives (e.g. a "deliver content
#     within fifteen (15) days after the Effective Date" deadline clause that
#     has nothing to do with the contract's own Term, found while drafting
#     this matcher in the Ediets induction contract).
#   - Two fixed "explicit end date" skeletons ("ending on <date>", "shall
#     terminate on <date>"), tried BEFORE the arithmetic path so an explicit
#     stated end date always wins over a naive base+duration computation
#     (needed for CORALGOLD, where 5 years from the Effective Date would
#     compute to Feb 1 2025 but the contract explicitly fixes the end date
#     one day earlier, at Jan 31 2025).
#   - One fixed "blank execution date" skeleton for the UNDETERMINED case
#     that has an unambiguous textual signal (a literal blank fill-in-the-
#     blank date line) rather than an inferred absence.
#
# Known failure modes / what this matcher will silently NOT handle (raises
# NoMatch instead of guessing):
#   - Any Term/duration phrasing not matching one of the six fixed skeletons
#     below (e.g. different connecting verbs, "Initial Term" vs "Term",
#     different reference phrase to the base date). This matcher does not
#     attempt a general-purpose "find the duration nearest the defined term
#     Effective Date" search, specifically because that was tried during
#     induction and produced a wrong answer on unrelated deadline clauses.
#   - Termination-only contracts whose end depends on business conditions
#     (capital thresholds, contingent conversion events) rather than a
#     calendar duration — the "event-triggered, no Term clause" pattern
#     illustrated by SUNTRON is a declared, permanent gap.
#   - Multiple Term-like clauses in tension, superseding amendments, or a
#     Term clause defined by reference to an external, undated instrument.
#   - Non-Gregorian date formats, non-English month names, or numerals
#     spelled out without the parenthetical digit convention.

import re
from datetime import date, timedelta
from typing import Optional, Tuple

CATEGORY = "Expiration Date"
TRUST = "one-sided"
PROVENANCE = {
    "induced_from": [
        "CENTRACKINTERNATIONALINC_10_29_1999-EX-10.3-WEB SITE HOSTING AGREEMENT.txt",
        "CORALGOLDRESOURCES,LTD_05_28_2020-EX-4.1-CONSULTING AGREEMENT.txt",
        "DeltathreeInc_19991102_S-1A_EX-10.19_6227850_EX-10.19_Co-Branding Agreement_ Service Agreement.txt",
        "EcoScienceSolutionsInc_20171117_8-K_EX-10.1_10956472_EX-10.1_Endorsement Agreement.txt",
        "EdietsComInc_20001030_10QSB_EX-10.4_2606646_EX-10.4_Co-Branding Agreement.txt",
        "GpaqAcquisitionHoldingsInc_20200123_S-4A_EX-10.6_11951677_EX-10.6_License Agreement.txt",
        "LEGACYTECHNOLOGYHOLDINGS,INC_12_09_2005-EX-10.2-DISTRIBUTOR AGREEMENT.txt",
        "SIBANNAC,INC_12_04_2017-EX-2.1-Strategic Alliance Agreement.txt",
        "SUNTRONCORP_05_17_2006-EX-10.22-MAINTENANCE AGREEMENT.txt",
        "UsioInc_20040428_SB-2_EX-10.11_1723988_EX-10.11_Affiliate Agreement 2.txt",
    ],
    "brief": "overseer_brief_v1",
    "commission": "c05-expiration-date",
}


class NoMatch(Exception):
    """Raised when the matcher cannot answer. NEVER guess instead."""


# ---------------------------------------------------------------------------
# Date grammar: "Month D[st/nd/rd/th], YYYY"  and  "Dth day of Month[,] YYYY"
# ---------------------------------------------------------------------------

_MONTH_PATTERN = (
    r"(?:January|Jan\.|Jan|February|Feb\.|Feb|March|Mar\.|Mar|April|Apr\.|Apr|"
    r"May|June|Jun\.|Jun|July|Jul\.|Jul|August|Aug\.|Aug|September|Sept\.|Sept|"
    r"Sep\.|Sep|October|Oct\.|Oct|November|Nov\.|Nov|December|Dec\.|Dec)"
)

_MONTH_NUM = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sept": 9, "sep": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


def _month_num(token: str) -> Optional[int]:
    return _MONTH_NUM.get(token.rstrip(".").lower())


# Two alternative date grammars, sharing the month alternation above but using
# distinct group names for each branch (Python's `re` forbids re-using a group
# name across branches of one pattern).
_DATE_PATTERN = (
    r"(?:"
    rf"(?P<dom_day>\d{{1,2}})(?:st|nd|rd|th)\s+day\s+of\s+(?P<dom_month>{_MONTH_PATTERN}),?\s+(?P<dom_year>\d{{4}})"
    r"|"
    rf"(?P<mdy_month>{_MONTH_PATTERN})\s+(?P<mdy_day>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<mdy_year>\d{{4}})"
    r")"
)

DATE_RE = re.compile(_DATE_PATTERN)


def _parse_date(m: re.Match) -> date:
    if m.group("dom_year"):
        day = int(m.group("dom_day"))
        month = _month_num(m.group("dom_month"))
        year = int(m.group("dom_year"))
    else:
        month = _month_num(m.group("mdy_month"))
        day = int(m.group("mdy_day"))
        year = int(m.group("mdy_year"))
    return date(year, month, day)


def _find_preamble_date(text: str) -> Optional[Tuple[date, int, int]]:
    """The contract's own dating clause is always in the opening sentence(s),
    before the recitals. Search only that window so an unrelated later date
    (e.g. a referenced third-party agreement's date) is never mistaken for
    the contract's own base date."""
    window_end = len(text)
    upper_text = text.upper()
    for marker in ("WHEREAS", "RECITALS", "WITNESSETH", "NOW, THEREFORE", "NOW THEREFORE"):
        idx = upper_text.find(marker)
        if idx != -1:
            window_end = min(window_end, idx)
    window_end = min(window_end, 1200)
    m = DATE_RE.search(text, 0, window_end)
    if not m:
        return None
    return _parse_date(m), m.start(), m.end()


# ---------------------------------------------------------------------------
# Calendar arithmetic (stdlib only: no `calendar` module on the allow-list)
# ---------------------------------------------------------------------------

def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, month + 1, 1)
    return (nxt - date(year, month, 1)).days


def _add_years(d: date, n: int) -> date:
    year = d.year + n
    day = min(d.day, _days_in_month(year, d.month))
    return date(year, d.month, day)


def _add_months(d: date, n: int) -> date:
    total = d.month - 1 + n
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, _days_in_month(year, month))
    return date(year, month, day)


def _add_duration(base: date, num: int, unit: str) -> date:
    unit = unit.lower()
    if unit.startswith("year"):
        return _add_years(base, num)
    if unit.startswith("month"):
        return _add_months(base, num)
    return base + timedelta(days=num)


def _fmt(d: date) -> str:
    return f"{d.month:02d}/{d.day:02d}/{d.year:04d}"


_SENTENCE_BREAK_RE = re.compile(r"\.\s+")


def _expand_span(text: str, start: int, end: int, max_extra: int = 300) -> str:
    """Widen [start, end) to (approximately) full sentences for readability.
    Sentence breaks are periods followed by whitespace of any kind (space,
    newline, blank line) -- contract text extracted from filings wraps
    lines, so a period is often followed by "\\n\\n" rather than a literal
    space. Falls back to a fixed-size window if no break is found; either
    way [start, end) — the verbatim regex match — is always included."""
    left_bound = max(0, start - max_extra)
    right_bound = min(len(text), end + max_extra)
    left = left_bound
    for sb in _SENTENCE_BREAK_RE.finditer(text, left_bound, start):
        left = sb.end()
    right = right_bound
    m = _SENTENCE_BREAK_RE.search(text, end, right_bound)
    if m:
        right = m.start() + 1
    span = text[left:right].strip()
    return span if span else text[start:end]


# ---------------------------------------------------------------------------
# Step 1 — explicit end date stated directly (no arithmetic, wins outright)
# ---------------------------------------------------------------------------

_DIRECT_END_RE = re.compile(
    r"(?:ending on|shall terminate on|terminates on|terminated on)\s+" + _DATE_PATTERN,
    re.IGNORECASE,
)


def _try_direct_end_date(text: str):
    m = _DIRECT_END_RE.search(text)
    if not m:
        return None
    d = _parse_date(m)
    span = _expand_span(text, m.start(), m.end())
    return {"present": True, "spans": [span], "answer": _fmt(d)}


# ---------------------------------------------------------------------------
# Step 2 — base date + duration, via one of six fixed induced skeletons
# ---------------------------------------------------------------------------

_DURATION = r"[A-Za-z][A-Za-z\- ]*\(\s*(?P<num>\d{1,3})\s*\)\s*(?P<unit>day|month|year)s?"

# T1 — CENTRACK: the base date is embedded in the Term clause itself, no
# preamble reference needed.
_T1_RE = re.compile(
    r"commence[sd]?\s+upon\s+" + _DATE_PATTERN +
    r"\s+and\s+shall\s+continue\s+for\s+a\s+period\s+of\s+" + _DURATION,
    re.IGNORECASE,
)

# T2 — DeltaThree: "effective as of the date first stated above ... continue
# for a term of <duration>".
_T2_RE = re.compile(
    r"effective\s+as\s+of\s+the\s+date\s+first\s+stated\s+above\s+and\s+shall\s+continue\s+for\s+a\s+term\s+of\s+"
    + _DURATION,
    re.IGNORECASE,
)

# T3 — EcoScience: "shall be for <duration> commencing on the Effective Date".
_T3_RE = re.compile(
    r"shall\s+be\s+for\s+" + _DURATION + r"\s+commencing\s+on\s+the\s+Effective\s+Date",
    re.IGNORECASE,
)

# T4 — Ediets: "remain effective for <duration> from and after the Effective Date".
_T4_RE = re.compile(
    r"remain\s+effective\s+for\s+" + _DURATION + r"\s+from\s+and\s+after\s+the\s+Effective\s+Date",
    re.IGNORECASE,
)

# T5 — Legacy: "term of this Agreement shall be <duration> from the Effective Date".
_T5_RE = re.compile(
    r"term\s+of\s+this\s+Agreement\s+shall\s+be\s+" + _DURATION + r"\s+from\s+the\s+Effective\s+Date",
    re.IGNORECASE,
)

# T6 — Sibannac: "term of this Agreement is <duration> from the date hereof".
_T6_RE = re.compile(
    r"term\s+of\s+this\s+Agreement\s+is\s+" + _DURATION + r"\s+from\s+the\s+date\s+hereof",
    re.IGNORECASE,
)

_PREAMBLE_REFERENCE_PATTERNS = (_T2_RE, _T3_RE, _T4_RE, _T5_RE, _T6_RE)


def _try_computed_date(text: str):
    # T1 first: its base date is self-contained (no preamble lookup, so it
    # cannot be thrown off by an unrelated earlier date in the text).
    m = _T1_RE.search(text)
    if m:
        base = _parse_date(m)
        num = int(m.group("num"))
        unit = m.group("unit")
        end = _add_duration(base, num, unit)
        span = _expand_span(text, m.start(), m.end())
        return {"present": True, "spans": [span], "answer": _fmt(end)}

    for pattern in _PREAMBLE_REFERENCE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        preamble = _find_preamble_date(text)
        if preamble is None:
            continue
        base, p_start, p_end = preamble
        num = int(m.group("num"))
        unit = m.group("unit")
        end = _add_duration(base, num, unit)
        preamble_span = _expand_span(text, p_start, p_end)
        term_span = _expand_span(text, m.start(), m.end())
        spans = [preamble_span] if preamble_span == term_span else [preamble_span, term_span]
        return {"present": True, "spans": spans, "answer": _fmt(end)}

    return None


# ---------------------------------------------------------------------------
# Step 3 — blank, never-filled-in execution date -> the model's "UNDETERMINED"
# ---------------------------------------------------------------------------

_BLANK_DATE_RE = re.compile(
    r"_{3,}\s*day\s+of\s+_{3,}.{0,40}?year\s+_{3,}",
    re.IGNORECASE | re.DOTALL,
)

_DEFERRED_DATE_REFERENCE_RE = re.compile(
    r"the\s+date\s+set\s+forth\s+below",
    re.IGNORECASE,
)


def _try_undetermined_blank_date(text: str):
    if not _DEFERRED_DATE_REFERENCE_RE.search(text):
        return None
    blank = _BLANK_DATE_RE.search(text)
    if not blank:
        return None
    ref = _DEFERRED_DATE_REFERENCE_RE.search(text)
    ref_span = _expand_span(text, ref.start(), ref.end())
    blank_span = text[blank.start():blank.end()]
    spans = [ref_span] if ref_span == blank_span or blank_span in ref_span else [ref_span, blank_span]
    return {"present": True, "spans": spans, "answer": "UNDETERMINED"}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def match(text: str) -> dict:
    """Answer the "Expiration Date" question from raw contract text.
    Returns {"present": bool, "spans": [str, ...], "answer": str | None}.
    Raises NoMatch when the text doesn't fit the induced, narrow patterns.
    """
    result = _try_direct_end_date(text)
    if result is not None:
        return result

    result = _try_computed_date(text)
    if result is not None:
        return result

    result = _try_undetermined_blank_date(text)
    if result is not None:
        return result

    raise NoMatch("No induced Expiration Date pattern (explicit end date, "
                   "base-date-plus-duration, or blank execution date) matched this text.")


# ---------------------------------------------------------------------------
# Mandatory self-test
# ---------------------------------------------------------------------------

SELF_TEST = [
    (
        "CENTRACKINTERNATIONALINC_10_29_1999-EX-10.3-WEB SITE HOSTING AGREEMENT.txt",
        {"present": True, "answer": "10/01/1999",
         "evidence": "The term of this Agreement for the Hosted Site shall commence upon April 1, 1999 and shall continue for a period of six (6) months, unless earlier terminated in accordance with provisions hereof."},
    ),
    (
        "CORALGOLDRESOURCES,LTD_05_28_2020-EX-4.1-CONSULTING AGREEMENT.txt",
        {"present": True, "answer": "01/31/2025",
         "evidence": "The term of this Agreement is for a period of five (5) years (the \"Term\") commencing on the Effective Date and, unless terminated earlier in accordance with the termination provisions of this Agreement, ending on January 31, 2025."},
    ),
    (
        "DeltathreeInc_19991102_S-1A_EX-10.19_6227850_EX-10.19_Co-Branding Agreement_ Service Agreement.txt",
        {"present": True, "answer": "10/01/2002",
         "evidence": "Section 1.01. Term. The term of this Agreement shall be effective as of the date first stated above and shall continue for a term of three (3) years, unless terminated earlier in accordance with the provisions of this Agreement (the \"Term\")"},
    ),
    (
        "EcoScienceSolutionsInc_20171117_8-K_EX-10.1_10956472_EX-10.1_Endorsement Agreement.txt",
        {"present": True, "answer": "11/14/2018",
         "evidence": "2. Term of Agreement. The term of this Agreement shall be for one (1) year commencing on the Effective Date and automatically renewing annually thereafter"},
    ),
    (
        "EdietsComInc_20001030_10QSB_EX-10.4_2606646_EX-10.4_Co-Branding Agreement.txt",
        {"present": True, "answer": "05/22/2002",
         "evidence": "10.1 Initial Term. This Agreement will become effective as of the Effective Date and, unless sooner terminated pursuant to Sections 3.1  [Advertising and Promotion] or 10.2  [Termination for Breach], shall remain effective for two (2) years from and after the Effective Date (the \"Initial Term\")."},
    ),
    (
        "GpaqAcquisitionHoldingsInc_20200123_S-4A_EX-10.6_11951677_EX-10.6_License Agreement.txt",
        {"present": True, "answer": "12/31/2034",
         "evidence": "Unless otherwise terminated as provided herein, the term of this Agreement shall commence on the Effective Date and shall terminate on December 31, 2034"},
    ),
    (
        "LEGACYTECHNOLOGYHOLDINGS,INC_12_09_2005-EX-10.2-DISTRIBUTOR AGREEMENT.txt",
        {"present": True, "answer": "12/08/2007",
         "evidence": "7.       Term.  The  term of this  Agreement  shall  be two (2)  years  from the          Effective  Date with  automatic  annual  renewals  thereafter"},
    ),
    (
        "SIBANNAC,INC_12_04_2017-EX-2.1-Strategic Alliance Agreement.txt",
        {"present": True, "answer": "11/30/2018",
         "evidence": "The term of this Agreement is twelve (12) months from the date hereof, and will be automatically renewed for one (1) additional twelve month period"},
    ),
    (
        "SUNTRONCORP_05_17_2006-EX-10.22-MAINTENANCE AGREEMENT.txt",
        "NoMatch",
    ),
    (
        "UsioInc_20040428_SB-2_EX-10.11_1723988_EX-10.11_Affiliate Agreement 2.txt",
        {"present": True, "answer": "UNDETERMINED",
         "evidence": "EXECUTED  this ________ day of ______________________, in the year ____________."},
    ),
]


def _spans_overlap(text: str, span_a: str, span_b: str) -> bool:
    ia = text.find(span_a)
    ib = text.find(span_b)
    if ia == -1 or ib == -1:
        return False
    return ia < ib + len(span_b) and ib < ia + len(span_a)


def self_test(load_text) -> bool:
    """Replay the matcher over the full induction set.
    `load_text(filename)` -> raw contract text.
    Asserts every accepted extraction is reproduced at the answer/presence
    level (spans may differ in extent but must overlap the accepted
    evidence). Raises AssertionError on any mismatch."""
    for filename, expected in SELF_TEST:
        text = load_text(filename)
        if expected == "NoMatch":
            try:
                match(text)
            except NoMatch:
                continue
            else:
                raise AssertionError(f"{filename}: expected NoMatch (documented gap), matcher returned a result")
        try:
            result = match(text)
        except NoMatch:
            raise AssertionError(f"{filename}: expected a confident match, matcher raised NoMatch")
        assert result["present"] == expected["present"], (
            f"{filename}: present mismatch, got {result['present']!r}"
        )
        assert result["answer"] == expected["answer"], (
            f"{filename}: answer mismatch, expected {expected['answer']!r}, got {result['answer']!r}"
        )
        evidence = expected["evidence"]
        assert any(_spans_overlap(text, s, evidence) for s in result["spans"]), (
            f"{filename}: returned spans {result['spans']!r} do not overlap accepted evidence {evidence!r}"
        )
    return True
