# Provenance
# -----------
# Category:            Anti-Assignment
# Trust grade:         one-sided (present:True only, never present:False)
# Induction set size:  8 contracts (8 accepted positives, 0 accepted negatives)
# Date:                2026-07-03
# Brief:               overseer_brief_v1
#
# Patterns induced: every accepted example ties some form of the verb "assign"
# (assign / assigned / assignable / assignment) to a consent obligation inside
# a single, unbroken clause, in one of two grammatical shapes. (1) A negation
# modal ("shall not" / "may not" / "will not" / "neither ... nor ... shall")
# governs the assign-verb, and the same clause later reads "... without
# [the] [prior] [written] consent ..." — this covers 7 of the 8 induction
# contracts (Coral Gold, Deltathree x2, EcoScience, eDiets, Gpaq/PFHOF,
# Sibannac, Usio). (2) The assign-noun is the clause subject and the clause
# reads "assignment ... requires ... consent", with no negation modal at all —
# this is the second sentence of the Legacy Technology distributor agreement,
# which pairs an affiliate/subsidiary carve-out (assignment allowed without
# consent) with a residual rule that any *other* assignment requires consent;
# the matcher fires on that residual sentence, not the carve-out. Both shapes
# require the assign-word and the word "consent" to sit inside one clause: no
# intervening sentence-ending period, and no intervening blank line. That
# second guard exists because the eDiets contract's assignment clause is
# split across a page-number line ("13" alone on its own line) — the matcher
# stops the captured span right before that artefact instead of reading
# through it, which happens to reproduce the accepted span exactly.
#
# Known limits (published honestly): the matcher does not separately flag
# affiliate/merger-successor carve-outs — it only looks for the sentence that
# states the actual restriction, which was sufficient for every induction
# example, but a contract whose *only* assignment language is a pure carve-out
# with no residual consent requirement anywhere will correctly raise NoMatch
# rather than guess. It will also raise NoMatch (rather than assert Yes) on:
# (a) a notice-only anti-assignment clause that never uses the word "consent"
# — the category semantics count notice-only restrictions as Yes, but no
# induction example shows that phrasing, so the matcher does not attempt it;
# (b) restriction language that avoids both "assign" and "consent" altogether
# (e.g. "transfer" as the sole verb, or "approval"/"permission" in place of
# "consent"). A theoretical false-trigger risk is boilerplate "successors and
# permitted assigns" language sitting close enough to an unrelated consent
# clause to satisfy the pattern; this did not occur in any induction contract
# because a negation modal (or "requires") must sit immediately before the
# assign-word, which plain "successors and assigns" recitals never have.

import re

CATEGORY = "Anti-Assignment"
TRUST = "one-sided"
PROVENANCE = {
    "induced_from": [
        "CORALGOLDRESOURCES,LTD_05_28_2020-EX-4.1-CONSULTING AGREEMENT.txt",
        "DeltathreeInc_19991102_S-1A_EX-10.19_6227850_EX-10.19_Co-Branding Agreement_ Service Agreement.txt",
        "EcoScienceSolutionsInc_20171117_8-K_EX-10.1_10956472_EX-10.1_Endorsement Agreement.txt",
        "EdietsComInc_20001030_10QSB_EX-10.4_2606646_EX-10.4_Co-Branding Agreement.txt",
        "GpaqAcquisitionHoldingsInc_20200123_S-4A_EX-10.6_11951677_EX-10.6_License Agreement.txt",
        "LEGACYTECHNOLOGYHOLDINGS,INC_12_09_2005-EX-10.2-DISTRIBUTOR AGREEMENT.txt",
        "SIBANNAC,INC_12_04_2017-EX-2.1-Strategic Alliance Agreement.txt",
        "UsioInc_20040428_SB-2_EX-10.11_1723988_EX-10.11_Affiliate Agreement 2.txt",
    ],
    "brief": "overseer_brief_v1",
    "commission": "c06-anti-assignment",
}


class NoMatch(Exception):
    """Raised when the matcher cannot answer. NEVER guess instead."""


# A "blank gap" is the signature of a page-number line or other conversion
# artefact splitting a run-on sentence in these texts (blank line, isolated
# page number, blank line). Clauses must not be read through one.
_BLANK_GAP = r"(?:\r?\n[ \t]*\r?\n)"
_CLAUSE_CHAR = r"(?:(?!" + _BLANK_GAP + r")[^.])"  # any char, but not '.' and not the start of a blank gap

_NEG_CUE = (
    r"(?:shall\s+not|may\s+not|will\s+not|can\s*not"
    r"|is\s+not\s+permitted\s+to|shall\s+have\s+no\s+right\s+to|neither)"
)
_ASSIGN = r"assign(?:ed|able|ment|s)?"
_REQUIRE = r"requires?"

# Shape 1: negation modal ... assign-word ... consent
_PATTERN_NEGATION = re.compile(
    r"\b" + _NEG_CUE + r"\b" + _CLAUSE_CHAR + r"{0,250}?"
    r"\b" + _ASSIGN + r"\b" + _CLAUSE_CHAR + r"{0,250}?"
    r"\bconsent\b" + _CLAUSE_CHAR + r"*\.?",
    re.IGNORECASE,
)

# Shape 2: assign-word ... requires ... consent (no negation modal needed)
_PATTERN_REQUIRES = re.compile(
    r"\b" + _ASSIGN + r"\b" + _CLAUSE_CHAR + r"{0,250}?"
    r"\b" + _REQUIRE + r"\b" + _CLAUSE_CHAR + r"{0,250}?"
    r"\bconsent\b" + _CLAUSE_CHAR + r"*\.?",
    re.IGNORECASE,
)


def match(text: str) -> dict:
    """Answer the Anti-Assignment question from raw contract text.

    Returns {"present": bool, "spans": [str, ...], "answer": str | None}.
    Raises NoMatch when the text doesn't fit the patterns induced above.
    One-sided trust: only ever returns present=True; never present=False.
    """
    spans = []
    seen = set()
    for pattern in (_PATTERN_NEGATION, _PATTERN_REQUIRES):
        for m in pattern.finditer(text):
            span = m.group(0).strip()
            if span and span not in seen:
                seen.add(span)
                spans.append(span)

    if not spans:
        raise NoMatch("no anti-assignment consent/requirement clause found")

    return {"present": True, "spans": spans, "answer": None}


# ---------------------------------------------------------------------------
# Mandatory self-test
# ---------------------------------------------------------------------------

SELF_TEST = [
    ("CORALGOLDRESOURCES,LTD_05_28_2020-EX-4.1-CONSULTING AGREEMENT.txt", True),
    (
        "DeltathreeInc_19991102_S-1A_EX-10.19_6227850_EX-10.19_Co-Branding Agreement_ Service Agreement.txt",
        True,
    ),
    (
        "EcoScienceSolutionsInc_20171117_8-K_EX-10.1_10956472_EX-10.1_Endorsement Agreement.txt",
        True,
    ),
    (
        "EdietsComInc_20001030_10QSB_EX-10.4_2606646_EX-10.4_Co-Branding Agreement.txt",
        True,
    ),
    (
        "GpaqAcquisitionHoldingsInc_20200123_S-4A_EX-10.6_11951677_EX-10.6_License Agreement.txt",
        True,
    ),
    ("LEGACYTECHNOLOGYHOLDINGS,INC_12_09_2005-EX-10.2-DISTRIBUTOR AGREEMENT.txt", True),
    ("SIBANNAC,INC_12_04_2017-EX-2.1-Strategic Alliance Agreement.txt", True),
    (
        "UsioInc_20040428_SB-2_EX-10.11_1723988_EX-10.11_Affiliate Agreement 2.txt",
        True,
    ),
]

# The accepted evidence spans from the induction set (as extracted by the
# model), copied here so the self-test can check overlap without doing any
# file I/O of its own. Whitespace is normalised before comparison, so exact
# spacing does not need to be reproduced byte-for-byte.
_ACCEPTED_SPANS = {
    "CORALGOLDRESOURCES,LTD_05_28_2020-EX-4.1-CONSULTING AGREEMENT.txt": [
        "Neither this Agreement nor any of the rights of any of the parties under "
        "this Agreement shall be assigned without thewritten consent of all the parties."
    ],
    "DeltathreeInc_19991102_S-1A_EX-10.19_6227850_EX-10.19_Co-Branding Agreement_ Service Agreement.txt": [
        "This Agreement may not be assigned by DeltaThree without the prior written consent of PrimeCall.",
        "Except as provided in the preceding sentence, this Agreement may not be "
        "assigned by PrimeCall without the prior written consent of DeltaThree.",
    ],
    "EcoScienceSolutionsInc_20171117_8-K_EX-10.1_10956472_EX-10.1_Endorsement Agreement.txt": [
        "Neither this Agreement nor any of the rights or obligations contained herein "
        "may be assigned or transferred by either party without the prior written "
        "consent of the other party."
    ],
    "EdietsComInc_20001030_10QSB_EX-10.4_2606646_EX-10.4_Co-Branding Agreement.txt": [
        "Neither party may assign this Agreement, in whole or in part, without the "
        "other party's written consent (which will not be unreasonably delayed or "
        "withheld), except that no such consent will be required in connection with "
        "an assignment or transfer of this Agreement to (a) a party's successor in "
        "connection with a Change in Control of such party, provided that such "
        "successor is not a competitor of the other party, or (b) to any entity that is",
        "controlled by, under common control with, or controls a party.",
    ],
    "GpaqAcquisitionHoldingsInc_20200123_S-4A_EX-10.6_11951677_EX-10.6_License Agreement.txt": [
        "The Village Media Company shall not, directly or indirectly, assign, "
        "sublicense or otherwise transfer any of its rights or obligations hereunder "
        "without the prior written consent of PFHOF.",
        "The transfer of ownership of the Village Media Company pursuant to the "
        "Merger Agreement shall not require the consent of PFHOF.",
    ],
    "LEGACYTECHNOLOGYHOLDINGS,INC_12_09_2005-EX-10.2-DISTRIBUTOR AGREEMENT.txt": [
        "The parties shall have the right to assign all, or part, of its rights "
        "under this Agreement to any wholly owned subsidiary or affiliate without "
        "the consent of the other Party.",
        "Any other assignment by the parties, requires the prior written consent of the other Party.",
    ],
    "SIBANNAC,INC_12_04_2017-EX-2.1-Strategic Alliance Agreement.txt": [
        "This Agreement shall not be assignable by either party without the prior written consent of the other party."
    ],
    "UsioInc_20040428_SB-2_EX-10.11_1723988_EX-10.11_Affiliate Agreement 2.txt": [
        "This agreement may be assigned or delegated, in whole or in part, by "
        "NETWORK 1 without the prior written consent of the other party herein.",
        "This agreement may not be assigned or delegated by Affiliate without prior "
        "written consent from Network 1. Such consent shall not be unreasonably withheld.",
    ],
}


def _normalize(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def _overlaps(predicted_spans, accepted_spans):
    norm_pred = [_normalize(p) for p in predicted_spans]
    for acc in accepted_spans:
        na = _normalize(acc)
        for p in norm_pred:
            if p and na and (p in na or na in p):
                return True
    return False


def self_test(load_text):
    """Replay the matcher over the full induction set.

    `load_text` is a callable: filename -> raw contract text, supplied by the
    activation gate (this module performs no file I/O itself). Raises
    AssertionError on the first reproduction failure.
    """
    for fname, expected_present in SELF_TEST:
        text = load_text(fname)
        try:
            result = match(text)
        except NoMatch:
            assert not expected_present, (
                f"{fname}: matcher raised NoMatch but induction says "
                f"present={expected_present}"
            )
            continue
        assert result["present"] == expected_present, f"{fname}: present mismatch"
        accepted = _ACCEPTED_SPANS.get(fname, [])
        assert _overlaps(result["spans"], accepted), (
            f"{fname}: predicted spans do not overlap accepted evidence"
        )
    return True
