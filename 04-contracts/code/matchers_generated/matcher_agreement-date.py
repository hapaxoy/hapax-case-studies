# Category: Agreement Date
# Trust grade: one-sided
# Induction set size: 6 (all 6 also used as the "positives" list; no negatives supplied)
# Date: 2026-07-03
# Overseer brief: overseer_brief_v1
#
# What this matcher does, in plain language:
# It looks for the sentence that establishes THIS contract's own agreement
# date -- the opening clause of the shape "THIS <TYPE> AGREEMENT/EXHIBIT/
# SCHEDULE ... is dated as of / is made and effective as of / is entered
# into as of / shall be effective as of / is made and entered into this
# ...". The search for that anchor phrase is restricted to the first ~3000
# characters of the document, so that dates belonging to some *other*,
# merely-referenced agreement (e.g. "the Merger Agreement, dated September
# 16, 2019") are not picked up in preference to the contract's own date.
# Within the text immediately following the anchor it looks for one of four
# shapes, tried in this order:
#   1. An ordinal day-of-month construction ("14th day of November 2017",
#      "26th day of March 2020", "30th day of November, 2017"), normalised
#      via datetime.date() to mm/dd/yyyy.
#   2. A "Month Day, Year" construction, including abbreviated months with
#      a trailing period ("Dec. 8, 2005").
#   3. A blank/redacted date built from runs of underscores around "day of"
#      and "year" (e.g. "EXECUTED this ____ day of ____, in the year
#      ____."), answered as the literal string "[]/[]/[]".
#   4. A reference to an external, undated triggering event -- specifically
#      "the date of the Closing" / "the Closing Date" -- answered as
#      "UNDETERMINED" since no calendar date is recoverable from the text.
# If no anchor is found, or an anchor is found but none of the four shapes
# follow it, the matcher falls back to looking anywhere in the document for
# a bare blank EXECUTED-style signature clause (shape 3) before giving up.
#
# Known limits (published honestly): the five anchor phrasings and the
# "Closing" idiom are exactly the phrasings seen in the six induction
# contracts. A contract that dates itself with different wording (e.g.
# "IN WITNESS WHEREOF ... as of the date first written above", "made as
# of", a numeric date like "3/26/2020" in the preamble, or a contingent-
# event idiom other than "Closing") will not be recognised and will raise
# NoMatch even though a human reader would find the date easily. The
# 3000-character front-of-document cutoff will also miss a genuine
# agreement-date clause sitting after unusually long cover matter. Where a
# document mentions more than one candidate date (as Kubient does: the
# Exhibit's own "26th day of March 2020" versus the Master Services
# Agreement's separately parenthesised "Effective Date: February 5, 2020"),
# the matcher has no general adjudication rule beyond preferring whichever
# clause is the one that dates the document/exhibit at hand -- it does not
# reason about which of several referenced dates should win in general.

import re
import datetime

CATEGORY = "Agreement Date"
TRUST = "one-sided"
PROVENANCE = {
    "induced_from": [
        "EcoScienceSolutionsInc_20171117_8-K_EX-10.1_10956472_EX-10.1_Endorsement Agreement.txt",
        "GpaqAcquisitionHoldingsInc_20200123_S-4A_EX-10.6_11951677_EX-10.6_License Agreement.txt",
        "KUBIENT,INC_07_02_2020-EX-10.14-MASTER SERVICES AGREEMENT_Part2.txt",
        "LEGACYTECHNOLOGYHOLDINGS,INC_12_09_2005-EX-10.2-DISTRIBUTOR AGREEMENT.txt",
        "SIBANNAC,INC_12_04_2017-EX-2.1-Strategic Alliance Agreement.txt",
        "UsioInc_20040428_SB-2_EX-10.11_1723988_EX-10.11_Affiliate Agreement 2.txt",
    ],
    "brief": "overseer_brief_v1",
    "commission": "c03-agreement-date",
}


class NoMatch(Exception):
    """Raised when the matcher cannot answer. NEVER guess instead."""


# --- month name lookup -------------------------------------------------

_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def _month_num(name):
    key = name.strip().lower().rstrip(".")
    return _MONTHS.get(key)


def _to_answer(year, month, day):
    """Validate via datetime.date and normalise to mm/dd/yyyy, or None if invalid."""
    try:
        d = datetime.date(year, month, day)
    except ValueError:
        return None
    return "{:02d}/{:02d}/{:04d}".format(d.month, d.day, d.year)


# --- date-shape sub-patterns, searched within the anchor's lookahead window

_ORDINAL_DATE_RE = re.compile(
    r"(?P<day>\d{1,2})(?:st|nd|rd|th)\s+day\s+of\s+(?P<month>[A-Za-z]+)\.?,?\s+(?P<year>\d{4})",
    re.IGNORECASE,
)

_MONTHDAY_DATE_RE = re.compile(
    r"(?P<month>[A-Za-z]+)\.?\s+(?P<day>\d{1,2}),\s+(?P<year>\d{4})",
    re.IGNORECASE,
)

_BLANK_DATE_RE = re.compile(
    r"_{2,}\s*day\s+of\s+_{2,}\s*,?\s*(?:in\s+the\s+year\s+)?_{2,}",
    re.IGNORECASE,
)

_UNDETERMINED_RE = re.compile(
    r"the\s+date\s+of\s+(?:the\s+)?Closing\b|the\s+Closing\s+Date\b",
    re.IGNORECASE,
)

# --- preamble anchor phrases (each establishes THIS document's own date) --

_PREAMBLE_ANCHORS = [
    re.compile(r"is\s+dated\s+as\s+of", re.IGNORECASE),
    re.compile(r"is\s+made\s+and\s+effective\s+as\s+of", re.IGNORECASE),
    re.compile(r"is\s+entered\s+into\s+as\s+of", re.IGNORECASE),
    re.compile(r"shall\s+be\s+effective\s+as\s+of", re.IGNORECASE),
    re.compile(r"is\s+made\s+and\s+entered\s+into", re.IGNORECASE),
]

_PREAMBLE_WINDOW_CHARS = 3000
_DATE_LOOKAHEAD_CHARS = 160


def _extract_from_window(window):
    """Return (answer, matched_fragment) or (None, None)."""
    m = _ORDINAL_DATE_RE.search(window)
    if m:
        month_num = _month_num(m.group("month"))
        if month_num:
            answer = _to_answer(int(m.group("year")), month_num, int(m.group("day")))
            if answer:
                return answer, m.group(0)
    m = _MONTHDAY_DATE_RE.search(window)
    if m:
        month_num = _month_num(m.group("month"))
        if month_num:
            answer = _to_answer(int(m.group("year")), month_num, int(m.group("day")))
            if answer:
                return answer, m.group(0)
    m = _BLANK_DATE_RE.search(window)
    if m:
        return "[]/[]/[]", m.group(0)
    m = _UNDETERMINED_RE.search(window)
    if m:
        return "UNDETERMINED", m.group(0)
    return None, None


def _expand_span(text, anchor_start, frag_start, frag_end):
    """Build a readable, verbatim span covering the anchor and the date fragment."""
    left = max(0, anchor_start - 150)
    sp = text.find(" ", left)
    if 0 <= sp < anchor_start:
        left = sp + 1
    right = min(len(text), frag_end + 40)
    period = text.find(".", frag_end, right + 100)
    if period != -1:
        right = period + 1
    else:
        sp2 = text.rfind(" ", frag_end, right)
        if sp2 != -1:
            right = sp2
    return text[left:right].strip()


def match(text: str) -> dict:
    """Answer the Agreement Date question from raw contract text.
    Returns {"present": bool, "spans": [str, ...], "answer": str | None}
    Raises NoMatch when the text doesn't fit the patterns trusted here."""
    for anchor_re in _PREAMBLE_ANCHORS:
        for m in anchor_re.finditer(text):
            if m.start() > _PREAMBLE_WINDOW_CHARS:
                break
            window_start = m.end()
            window = text[window_start:window_start + _DATE_LOOKAHEAD_CHARS]
            answer, frag = _extract_from_window(window)
            if answer is None:
                continue
            frag_pos = window.find(frag)
            frag_start = window_start + frag_pos
            frag_end = frag_start + len(frag)
            span = _expand_span(text, m.start(), frag_start, frag_end)
            if span:
                return {"present": True, "spans": [span], "answer": answer}

    # Fall back: a bare blank EXECUTED-style signature clause anywhere in the text.
    m = _BLANK_DATE_RE.search(text)
    if m:
        start = m.start()
        prefix_window = text[max(0, start - 40):start]
        pm = re.search(r"EXECUTED\s+this\s*$", prefix_window, re.IGNORECASE)
        if pm:
            start = max(0, start - 40) + pm.start()
        end = m.end()
        if end < len(text) and text[end] == ".":
            end += 1
        span = text[start:end]
        return {"present": True, "spans": [span], "answer": "[]/[]/[]"}

    raise NoMatch()


def _spans_overlap(text, span_a, span_b):
    ia = text.find(span_a)
    ib = text.find(span_b)
    if ia == -1 or ib == -1:
        return False
    return max(ia, ib) < min(ia + len(span_a), ib + len(span_b))


SELF_TEST = [
    (
        "EcoScienceSolutionsInc_20171117_8-K_EX-10.1_10956472_EX-10.1_Endorsement Agreement.txt",
        {
            "present": True,
            "answer": "11/14/2017",
            "spans": [
                "THIS ENDORSEMENT AGREEMENT (the \"Agreement\") is dated as of this 14th day of November 2017 (\"Effective Date\"), by and between Eco Science Solutions, Inc. (\"ESSI\"), a Nevada corporation, and Stephen Marley (\"Talent\"), an individual."
            ],
        },
    ),
    (
        "GpaqAcquisitionHoldingsInc_20200123_S-4A_EX-10.6_11951677_EX-10.6_License Agreement.txt",
        {
            "present": True,
            "answer": "UNDETERMINED",
            "spans": [
                "THIS MEDIA LICENSE AGREEMENT (this \"Agreement\") is made and effective as of the date of the Closing (as defined in the Merger Agreement (as defined below)) (the \"Effective Date\"), between NATIONAL FOOTBALL MUSEUM, INC., an Ohio non-profit corporation, doing business as Pro Football Hall of Fame (\"PFHOF\"), HOF Village Media Group, LLC (the \"Village Media Company\"), a Delaware limited liability company that is a wholly-owned subsidiary of HOF Village, LLC, a Delaware limited liability company (\"HOFV\") and, solely for purposes of Section 4.5, HOFV; each a \"Party\" and collectively, the \"Parties\"."
            ],
        },
    ),
    (
        "KUBIENT,INC_07_02_2020-EX-10.14-MASTER SERVICES AGREEMENT_Part2.txt",
        {
            "present": True,
            "answer": "03/26/2020",
            "spans": [
                "This Exhibit B is entered into as of the 26th day of March 2020 by and between Kubient, Inc. (\"Kubient\"), and The Associated Press (\"Customer\").",
                "This Exhibit is hereby incorporated into and made a part of the Master Services Agreement (the \"Agreement\") between the Parties (Effective Date: February 5, 2020).",
            ],
        },
    ),
    (
        "LEGACYTECHNOLOGYHOLDINGS,INC_12_09_2005-EX-10.2-DISTRIBUTOR AGREEMENT.txt",
        {
            "present": True,
            "answer": "12/08/2005",
            "spans": [
                "THIS  EXCLUSIVE   DISTRIBUTOR  AGREEMENT  (the  \"Agreement\")  shall  be effective as of _Dec. 8, 2005  (hereinafter  \"Effective  Date\"),  by and between LifeUSA/  Envision  Health,  Inc.,  a  corporation   (hereinafter   collectively \"ENVISION\"), and Sierra Mountain Minerals, Inc., a Canadian company (hereinafter \"SIERRA\"), is made with reference to the following facts:"
            ],
        },
    ),
    (
        "SIBANNAC,INC_12_04_2017-EX-2.1-Strategic Alliance Agreement.txt",
        {
            "present": True,
            "answer": "11/30/2017",
            "spans": [
                "This agreement is made and entered into this 30th day of November, 2017 by and between Bravatek Solutions, Inc., a corporation organized under the laws of the State of Colorado, (\"Bravatek\"), with an address at 2028 E. Ben White Blvd., Unit #240-2835, Austin, Texas, 78741, and Sibannac, Inc. (\"COMPANY\"), a corporation organized under the laws of Nevada, with an address at 2122 E Highland Avenue, Suite 425, Phoenix, Arizona 85016."
            ],
        },
    ),
    (
        "UsioInc_20040428_SB-2_EX-10.11_1723988_EX-10.11_Affiliate Agreement 2.txt",
        {
            "present": True,
            "answer": "[]/[]/[]",
            "spans": [
                "EXECUTED  this ________ day of ______________________, in the year ____________."
            ],
        },
    ),
]


def self_test(load_text):
    """Replay the matcher over the full induction set and check it reproduces
    every accepted extraction (answer/presence level; spans need only overlap)."""
    for filename, expected in SELF_TEST:
        text = load_text(filename)
        result = match(text)
        assert result["present"] == expected["present"], (
            "{}: present mismatch: got {!r}, expected {!r}".format(
                filename, result["present"], expected["present"]
            )
        )
        assert result["answer"] == expected["answer"], (
            "{}: answer mismatch: got {!r}, expected {!r}".format(
                filename, result["answer"], expected["answer"]
            )
        )
        overlap = any(
            _spans_overlap(text, got_span, exp_span)
            for got_span in result["spans"]
            for exp_span in expected["spans"]
        )
        assert overlap, "{}: no span overlap with accepted evidence".format(filename)
    return True
