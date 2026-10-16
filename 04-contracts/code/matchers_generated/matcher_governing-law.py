# Matcher: Governing Law
# Trust grade: one-sided (confident hit -> present=True; everything else -> NoMatch)
# Induction set: 11 accepted extractions, commission c04-governing-law
# Date: 3 July 2026. Brief: overseer_brief_v1.
#
# Patterns induced: every accepted extraction states the governing jurisdiction
# with the phrase "...laws... of the State/Commonwealth/Province of <NAME>",
# anchored a short distance after a governing-law verb ("governed", "construed",
# "interpreted", "enforced", or "applied [pursuant to]"). This wording is stable
# across very different drafting styles in the induction set (mixed case,
# ALL-CAPS boilerplate, heavy multi-space OCR artefacts, Canadian "Province of"
# phrasing, US "Commonwealth of" phrasing) and reliably distinguishes the real
# governing-law clause from superficially similar text elsewhere in the same
# contracts (corporate-formation clauses such as "a Delaware corporation" or
# "organized under the laws of the State of X" use different verbs and are
# never matched, because "organized"/"incorporated" are not in the trigger
# list). The matcher also reproduces the one induction example whose accepted
# answer is UNDETERMINED: a contract with a "Governing Law" heading that names
# no single governing jurisdiction but instead sends different parties to
# arbitration in two different states (McLean, Virginia vs. San Antonio,
# Texas) -- a genuine conflict, not a matcher failure. Known limits: (1) a
# contract whose real governing-law clause is phrased without any of the five
# trigger verbs, or without the exact "laws ... of the State/Commonwealth/
# Province of <name>" construction, will raise NoMatch rather than guess --
# expected to be the majority of the miss rate; (2) a contract that states two
# genuinely different confident governing-law jurisdictions (e.g. one clause
# for the main agreement, another for an attached schedule) also raises
# NoMatch, since this induction set has no such example to confirm what the
# right call would be; (3) jurisdictions outside the fixed US-state/DC/
# Canadian-province list used here (e.g. "England and Wales", Australian
# states, other countries) are never recognised, because none appeared in the
# induction set -- this is a deliberate narrowing, not an oversight; (4) the
# UNDETERMINED fingerprint is narrow by design (requires an explicit
# "Governing Law[s]" heading plus 2+ distinct arbitration-venue states) and
# will not fire on other kinds of jurisdictional conflict never observed here.

import re

CATEGORY = "Governing Law"
TRUST = "one-sided"
PROVENANCE = {
    "induced_from": [
        "CENTRACKINTERNATIONALINC_10_29_1999-EX-10.3-WEB SITE HOSTING AGREEMENT.txt",
        "CORALGOLDRESOURCES,LTD_05_28_2020-EX-4.1-CONSULTING AGREEMENT.txt",
        "DeltathreeInc_19991102_S-1A_EX-10.19_6227850_EX-10.19_Co-Branding Agreement_ Service Agreement.txt",
        "EcoScienceSolutionsInc_20171117_8-K_EX-10.1_10956472_EX-10.1_Endorsement Agreement.txt",
        "EdietsComInc_20001030_10QSB_EX-10.4_2606646_EX-10.4_Co-Branding Agreement.txt",
        "FEDERATEDGOVERNMENTINCOMESECURITIESINC_04_28_2020-EX-99.SERV AGREE-SERVICES AGREEMENT_SECONDAMENDMENT.txt",
        "GpaqAcquisitionHoldingsInc_20200123_S-4A_EX-10.6_11951677_EX-10.6_License Agreement.txt",
        "LEGACYTECHNOLOGYHOLDINGS,INC_12_09_2005-EX-10.2-DISTRIBUTOR AGREEMENT.txt",
        "SIBANNAC,INC_12_04_2017-EX-2.1-Strategic Alliance Agreement.txt",
        "SUNTRONCORP_05_17_2006-EX-10.22-MAINTENANCE AGREEMENT.txt",
        "UsioInc_20040428_SB-2_EX-10.11_1723988_EX-10.11_Affiliate Agreement 2.txt",
    ],
    "brief": "overseer_brief_v1",
    "commission": "c04-governing-law",
}


class NoMatch(Exception):
    """Raised when the matcher cannot answer. NEVER guess instead."""


# --- Closed jurisdiction vocabulary (US states + DC, Canadian provinces/territories) ---
# Using a closed whitelist (rather than a generic "capitalised word(s)" capture)
# means the state-name group can never over-run into neighbouring clause text,
# and IGNORECASE can safely be used for the whole pattern (needed for the
# ALL-CAPS boilerplate seen in the induction set) without that over-run risk.
_US_STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine",
    "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi",
    "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey",
    "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio",
    "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina",
    "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", "Virginia",
    "Washington", "West Virginia", "Wisconsin", "Wyoming",
    "District of Columbia",
]

_CA_PROVINCES = [
    "Alberta", "British Columbia", "Manitoba", "New Brunswick",
    "Newfoundland and Labrador", "Nova Scotia", "Ontario",
    "Prince Edward Island", "Quebec", "Saskatchewan",
    "Northwest Territories", "Nunavut", "Yukon",
]

_JURISDICTIONS = _US_STATES + _CA_PROVINCES
_CANON = {name.lower(): name for name in _JURISDICTIONS}
_JUR_ALT = "|".join(re.escape(name) for name in sorted(_JURISDICTIONS, key=len, reverse=True))

# Governing-law verb vocabulary. Deliberately excludes "organized"/"incorporated"
# so corporate-formation clauses ("a Delaware corporation", "organized under
# the laws of the State of Colorado") never trigger a match.
_TRIGGER = r"(?:govern|constru|interpret|enforc|appl)\w*"

# "<trigger> ... laws ... of the State/Commonwealth/Province of <jurisdiction>"
# within a single sentence ([^.] keeps the two gaps from crossing a period).
_PRIMARY_RE = re.compile(
    _TRIGGER
    + r"[^.]{0,200}?\blaws\b[^.]{0,80}?\bof\s+the\s+(?:state|commonwealth|province)\s+of\s+("
    + _JUR_ALT
    + r")\b",
    re.IGNORECASE,
)

# Fingerprint for the one accepted UNDETERMINED case: a "Governing Law[s]"
# heading with no single resolvable jurisdiction (_PRIMARY_RE found nothing),
# but two or more distinct arbitration-venue states.
_HEADING_RE = re.compile(r"governing\s+laws?\b", re.IGNORECASE)
_ARB_RE = re.compile(
    r"arbitrat\w*\s+in\s+[^,\n]{2,60}?,\s*(" + _JUR_ALT + r")\b",
    re.IGNORECASE,
)


def _sentence_span(text: str, start: int, end: int) -> str:
    """Expand a match's (start, end) to the enclosing sentence, verbatim."""
    prev_period = text.rfind(".", 0, start)
    seg_start = prev_period + 1 if prev_period != -1 else 0
    next_period = text.find(".", end)
    seg_end = next_period + 1 if next_period != -1 else len(text)
    return text[seg_start:seg_end].strip()


def _dedup_spans(text: str, matches, limit: int) -> list:
    spans = []
    seen = set()
    for m in matches:
        span = _sentence_span(text, m.start(), m.end())
        if span and span not in seen:
            seen.add(span)
            spans.append(span)
        if len(spans) >= limit:
            break
    return spans


def match(text: str) -> dict:
    """Answer the Governing Law question from raw contract text.
    Returns {"present": bool, "spans": [str, ...], "answer": str | None}
    Raises NoMatch when the text doesn't fit the patterns this matcher trusts.
    """
    primary_matches = list(_PRIMARY_RE.finditer(text))
    if primary_matches:
        found = {}
        for m in primary_matches:
            canon = _CANON[m.group(1).lower()]
            found.setdefault(canon, []).append(m)
        if len(found) == 1:
            canon = next(iter(found))
            spans = _dedup_spans(text, found[canon], limit=3)
            return {"present": True, "spans": spans, "answer": canon}
        # Two+ distinct confident jurisdictions: a real possibility (e.g. a
        # multi-jurisdiction answer, or a schedule with its own governing law)
        # but not one this induction set establishes evidence for. Don't guess.
        raise NoMatch("multiple distinct governing-law jurisdictions found; ambiguous")

    # No confident single-jurisdiction governing-law clause. Check the narrow
    # conflicting-arbitration-venue fingerprint before giving up.
    if _HEADING_RE.search(text):
        arb_matches = list(_ARB_RE.finditer(text))
        distinct = {}
        for m in arb_matches:
            canon = _CANON[m.group(1).lower()]
            distinct.setdefault(canon, []).append(m)
        if len(distinct) >= 2:
            spans = _dedup_spans(text, arb_matches, limit=4)
            return {"present": True, "spans": spans, "answer": "UNDETERMINED"}

    raise NoMatch("no confident governing-law pattern found")


# --- Mandatory self-test -----------------------------------------------------
# (induction filename, expected present, expected answer, a verbatim fragment
# that must appear inside at least one returned span)
SELF_TEST = [
    (
        "CENTRACKINTERNATIONALINC_10_29_1999-EX-10.3-WEB SITE HOSTING AGREEMENT.txt",
        True, "Florida",
        "shall be governed by the laws and judicial decisions of the State of Florida",
    ),
    (
        "CORALGOLDRESOURCES,LTD_05_28_2020-EX-4.1-CONSULTING AGREEMENT.txt",
        True, "British Columbia",
        "governed by and construed in accordance with the laws of the Province of British Columbia",
    ),
    (
        "DeltathreeInc_19991102_S-1A_EX-10.19_6227850_EX-10.19_Co-Branding Agreement_ Service Agreement.txt",
        True, "New York",
        "the laws of the State of New York",
    ),
    (
        "EcoScienceSolutionsInc_20171117_8-K_EX-10.1_10956472_EX-10.1_Endorsement Agreement.txt",
        True, "Michigan",
        "the laws and decisions of the State of Michigan",
    ),
    (
        "EdietsComInc_20001030_10QSB_EX-10.4_2606646_EX-10.4_Co-Branding Agreement.txt",
        True, "California",
        "the laws of the State of California",
    ),
    (
        "FEDERATEDGOVERNMENTINCOMESECURITIESINC_04_28_2020-EX-99.SERV AGREE-SERVICES AGREEMENT_SECONDAMENDMENT.txt",
        True, "Pennsylvania",
        "the laws of the Commonwealth of Pennsylvania",
    ),
    (
        "GpaqAcquisitionHoldingsInc_20200123_S-4A_EX-10.6_11951677_EX-10.6_License Agreement.txt",
        True, "Ohio",
        "the laws of the State of Ohio",
    ),
    (
        "LEGACYTECHNOLOGYHOLDINGS,INC_12_09_2005-EX-10.2-DISTRIBUTOR AGREEMENT.txt",
        True, "Colorado",
        "the laws of the State of Colorado",
    ),
    (
        "SIBANNAC,INC_12_04_2017-EX-2.1-Strategic Alliance Agreement.txt",
        True, "Texas",
        "interpreted according to the laws of the State of Texas",
    ),
    (
        "SUNTRONCORP_05_17_2006-EX-10.22-MAINTENANCE AGREEMENT.txt",
        True, "Minnesota",
        "THE LAWS OF THE STATE OF MINNESOTA",
    ),
    (
        "UsioInc_20040428_SB-2_EX-10.11_1723988_EX-10.11_Affiliate Agreement 2.txt",
        True, "UNDETERMINED",
        "arbitration in McLean, Virginia",
    ),
]


def self_test(load_text) -> bool:
    """Replay the matcher over the full induction set. `load_text(filename)`
    is supplied by the caller (the activation gate); this module performs no
    file I/O of its own. Raises AssertionError listing every mismatch."""
    failures = []
    for filename, expected_present, expected_answer, expected_fragment in SELF_TEST:
        text = load_text(filename)
        try:
            result = match(text)
        except NoMatch as exc:
            failures.append((filename, "raised NoMatch: %s" % exc))
            continue
        if result["present"] != expected_present:
            failures.append(
                (filename, "present mismatch: got %r want %r" % (result["present"], expected_present))
            )
            continue
        if result["answer"] != expected_answer:
            failures.append(
                (filename, "answer mismatch: got %r want %r" % (result["answer"], expected_answer))
            )
            continue
        if not any(expected_fragment in span for span in result["spans"]):
            failures.append((filename, "no returned span overlaps the accepted evidence"))
    assert not failures, "self-test failures: %r" % (failures,)
    return True
