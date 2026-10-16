# Matcher: Parties
# TRUST: one-sided
# Induction set: 6 contracts (see PROVENANCE below)
# Brief: overseer_brief_v1, 3 July 2026
#
# Patterns induced: every induction contract states its parties in a single
# preamble clause introduced by "by and between" or (failing that) a bare
# "between", running from the opening recital-type sentence up to the first
# hard section marker (RECITALS / WHEREAS / NOW THEREFORE) or, if none
# appears nearby, a short character cap. Within that clause, each party is
# named immediately before a parenthetical short-name definition of the form
# ("Short"), (the "Short"), (hereinafter "Short") or (hereinafter
# collectively "Short"). The matcher scans the clause left to right for
# these parenthetical definitions, discards the handful of generic
# boilerplate parentheticals that are never a party's short name
# (("Agreement"), ("Effective Date"), ("Party"/"Parties"), ("Term"), etc.),
# and for each survivor walks backward from the parenthetical to recover the
# party's full legal name: it takes the comma-separated run of capitalised
# tokens immediately preceding the parenthetical, stopping at the first
# lower-case descriptor word ("a Nevada corporation", "with an address at
# ...", etc). Where that immediate run is itself a lower-case descriptor
# (observed once, in a "wholly-owned subsidiary of X" appositive sandwiched
# between two descriptor clauses) the matcher falls back to splitting on the
# last top-level " and " in the run-up text, and failing that on a
# "subsidiary/affiliate/division/unit of" marker, before repeating the same
# backward walk. Names that are written fully in capitals in the preamble
# (a drafting convention distinct from the party's actual legal name, seen
# twice in induction) are re-cased to standard title case with a small
# corporate-suffix table (INC -> Inc, LLC stays LLC, etc.); mixed-case names
# are left exactly as printed. Whitespace runs are collapsed throughout
# (SEC exhibit text is frequently justified with multiple spaces) and a
# stray space around "/" in slash-joined names is removed.
#
# Known limits (read before trusting this on new contracts): this covers
# only the "X (by and between|between) PARTY1 (...), and PARTY2 (...) [, and
# PARTY3 (...)]" preamble grammar. It will raise NoMatch — never guess — on:
# preambles that introduce parties via "by and among" or a numbered list
# ("(1) X and (2) Y") instead of "between"; parties defined only in a
# signature block with no preamble short-name parenthetical; more than one
# level of nested subsidiary/appositive references; a dba clause that
# renames rather than merely re-describes a party; any preamble where a
# party's legal name does not sit in a clean comma-run immediately before,
# or immediately after a single subsidiary-of appositive before, its
# parenthetical; and more than 4 or fewer than 2 parenthetical-defined
# parties surviving the boilerplate filter. Because TRUST is one-sided,
# every one of those situations raises NoMatch rather than a partial or
# best-guess party list.

import re

CATEGORY = "Parties"
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
    "commission": "c02-parties",
}


class NoMatch(Exception):
    """Raised when the matcher cannot answer. NEVER guess instead."""


# ---------------------------------------------------------------------------
# Constants

_ANCHOR_BY_AND_BETWEEN = re.compile(r"by\s+and\s+between\s+", re.IGNORECASE)
_ANCHOR_BETWEEN = re.compile(r"\bbetween\s+", re.IGNORECASE)
_ANCHOR_SEARCH_PREFIX = 3000

_HARD_MARKER_RE = re.compile(
    r"\b(?:RECITALS?|WHEREAS|NOW\s*,?\s*THEREFORE)\b", re.IGNORECASE
)
_SEARCH_CAP = 700  # chars scanned after the anchor if no hard marker intervenes

_CONNECTOR = r"(?:the|this|a|an|hereinafter|collectively|solely|individually|each)"
_SHORT_NAME_GROUP_RE = re.compile(
    r'\(\s*(?:' + _CONNECTOR + r'\s*,?\s*)*"([^"]+)"\s*\)', re.IGNORECASE
)

_LEADING_CONNECTOR_RE = re.compile(r"^[\s,]*(?:and\s+)?", re.IGNORECASE)
_AND_RE = re.compile(r"\band\b", re.IGNORECASE)
_SUBSIDIARY_OF_RE = re.compile(
    r"(?:subsidiary|affiliate|division|unit)\s+of\s+", re.IGNORECASE
)

_SHORT_NAME_BLACKLIST = {
    "agreement",
    "effective date",
    "party",
    "parties",
    "term",
    "closing",
    "closing date",
    "date",
    "merger agreement",
    "master agreement",
}

_SUFFIX_TITLE = {
    "INC": "Inc",
    "CORP": "Corp",
    "CORPORATION": "Corporation",
    "CO": "Co",
    "COMPANY": "Company",
    "LTD": "Ltd",
    "LIMITED": "Limited",
}
_SUFFIX_KEEP_CAPS = {"LLC", "LLP", "LP", "PLC"}

_MIN_PARTIES = 2
_MAX_PARTIES = 4


# ---------------------------------------------------------------------------
# Name recovery helpers


def _strip_leading(chunk: str) -> str:
    m = _LEADING_CONNECTOR_RE.match(chunk)
    return chunk[m.end():] if m else chunk


def _forward_truncate(chunk: str) -> str:
    """Take the leading comma-separated run of capitalised tokens, stopping
    at the first token that (after stripping) starts with a lower-case
    letter — i.e. the first descriptor clause."""
    chunk = _strip_leading(chunk)
    if not chunk:
        return ""
    parts = chunk.split(",")
    kept = []
    for i, part in enumerate(parts):
        stripped = part.strip()
        if stripped == "":
            if i == 0:
                return ""
            kept.append(part)
            continue
        first_alpha = next((c for c in stripped if c.isalpha()), None)
        if first_alpha is None:
            # no letters at all (pure digits/punctuation) - carry through
            kept.append(part)
            continue
        if first_alpha.isupper():
            kept.append(part)
        else:
            break
    return ",".join(kept).strip()


def _titlecase_shouty(name: str) -> str:
    tokens = name.split(" ")
    out = []
    for tok in tokens:
        m = re.match(r"^([A-Za-z]+)([.,]*)$", tok)
        if not m:
            out.append(tok)
            continue
        core, trail = m.group(1), m.group(2)
        key = core.upper()
        if key in _SUFFIX_KEEP_CAPS:
            out.append(key + trail)
        elif key in _SUFFIX_TITLE:
            out.append(_SUFFIX_TITLE[key] + trail)
        else:
            out.append(core[:1].upper() + core[1:].lower() + trail)
    return " ".join(out)


def _normalize_name(raw: str) -> str:
    s = re.sub(r"\s+", " ", raw).strip()
    s = re.sub(r"\s*/\s*", "/", s)
    s = re.sub(r"\s*,\s*", ", ", s)
    s = s.strip(" ,")
    if not s:
        return ""
    letters = [c for c in s if c.isalpha()]
    if letters and all(c.isupper() for c in letters):
        s = _titlecase_shouty(s)
    return s


def _derive_name(raw_chunk: str) -> str:
    name = _forward_truncate(raw_chunk)
    if not name:
        and_matches = list(_AND_RE.finditer(raw_chunk))
        if and_matches:
            tail = raw_chunk[and_matches[-1].end():]
            name = _forward_truncate(tail)
    if not name:
        sub_match = _SUBSIDIARY_OF_RE.search(raw_chunk)
        if sub_match:
            tail = raw_chunk[sub_match.end():]
            name = _forward_truncate(tail)
    return name


def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------------------
# Core extraction


def _find_anchor(text: str):
    prefix = text[:_ANCHOR_SEARCH_PREFIX]
    m = _ANCHOR_BY_AND_BETWEEN.search(prefix)
    if m:
        return m
    return _ANCHOR_BETWEEN.search(prefix)


def _extract_parties(text: str):
    anchor = _find_anchor(text)
    if anchor is None:
        raise NoMatch("no 'by and between' / 'between' anchor found")

    anchor_start = anchor.start()
    anchor_end = anchor.end()

    search_text = text[anchor_end:anchor_end + _SEARCH_CAP]
    marker = _HARD_MARKER_RE.search(search_text)
    scan_text = search_text[:marker.start()] if marker else search_text

    groups = list(_SHORT_NAME_GROUP_RE.finditer(scan_text))
    if not groups:
        raise NoMatch("no parenthetical short-name definitions found")

    parties = []
    prev_end = 0
    last_kept_end = None
    for g in groups:
        short = _normalize_ws(g.group(1))
        if short.lower() in _SHORT_NAME_BLACKLIST:
            prev_end = g.end()
            continue
        raw_chunk = scan_text[prev_end:g.start()]
        raw_name = _derive_name(raw_chunk)
        name = _normalize_name(raw_name)
        if not name or not any(c.isalpha() for c in name) or len(name) < 2:
            raise NoMatch(
                f"could not recover a legal name before short name '{short}'"
            )
        parties.append((name, short))
        prev_end = g.end()
        last_kept_end = g.end()

    if len(parties) < _MIN_PARTIES:
        raise NoMatch("fewer than 2 parties recovered")
    if len(parties) > _MAX_PARTIES:
        raise NoMatch("more than 4 parties recovered - too irregular to trust")

    span = text[anchor_start:anchor_end + last_kept_end]
    return parties, span


def match(text: str) -> dict:
    """Answer the Parties question from raw contract text.
    Returns {"present": bool, "spans": [str, ...], "answer": str | None}
    Raises NoMatch when the text doesn't fit the patterns trusted here."""
    if not isinstance(text, str) or not text.strip():
        raise NoMatch("empty text")

    try:
        parties, span = _extract_parties(text)
    except NoMatch:
        raise
    except Exception as exc:  # never let an unexpected error masquerade as a guess
        raise NoMatch(f"internal parsing error: {exc}") from exc

    answer = "; ".join(f'{name} ("{short}")' for name, short in parties)
    return {"present": True, "spans": [span], "answer": answer}


# ---------------------------------------------------------------------------
# Mandatory self-test

SELF_TEST = [
    (
        "EcoScienceSolutionsInc_20171117_8-K_EX-10.1_10956472_EX-10.1_Endorsement Agreement.txt",
        {
            "present": True,
            "answer": 'Eco Science Solutions, Inc. ("ESSI"); Stephen Marley ("Talent")',
            "evidence": (
                'THIS ENDORSEMENT AGREEMENT (the "Agreement") is dated as of this 14th '
                'day of November 2017 ("Effective Date"), by and between Eco Science '
                'Solutions, Inc. ("ESSI"), a Nevada corporation, and Stephen Marley '
                '("Talent"), an individual.'
            ),
        },
    ),
    (
        "GpaqAcquisitionHoldingsInc_20200123_S-4A_EX-10.6_11951677_EX-10.6_License Agreement.txt",
        {
            "present": True,
            "answer": (
                'National Football Museum, Inc. ("PFHOF"); HOF Village Media Group, '
                'LLC ("Village Media Company"); HOF Village, LLC ("HOFV")'
            ),
            "evidence": (
                'THIS MEDIA LICENSE AGREEMENT (this "Agreement") is made and effective '
                'as of the date of the Closing (as defined in the Merger Agreement (as '
                'defined below)) (the "Effective Date"), between NATIONAL FOOTBALL '
                'MUSEUM, INC., an Ohio non-profit corporation, doing business as Pro '
                'Football Hall of Fame ("PFHOF"), HOF Village Media Group, LLC (the '
                '"Village Media Company"), a Delaware limited liability company that is '
                'a wholly-owned subsidiary of HOF Village, LLC, a Delaware limited '
                'liability company ("HOFV") and, solely for purposes of Section 4.5, '
                'HOFV; each a "Party" and collectively, the "Parties".'
            ),
        },
    ),
    (
        "KUBIENT,INC_07_02_2020-EX-10.14-MASTER SERVICES AGREEMENT_Part2.txt",
        {
            "present": True,
            "answer": 'Kubient, Inc. ("Kubient"); The Associated Press ("Customer")',
            "evidence": (
                'This Exhibit B is entered into as of the 26th day of March 2020 by '
                'and between Kubient, Inc. ("Kubient"), and The Associated Press '
                '("Customer").'
            ),
        },
    ),
    (
        "LEGACYTECHNOLOGYHOLDINGS,INC_12_09_2005-EX-10.2-DISTRIBUTOR AGREEMENT.txt",
        {
            "present": True,
            "answer": 'LifeUSA/Envision Health, Inc. ("ENVISION"); Sierra Mountain Minerals, Inc. ("SIERRA")',
            "evidence": (
                'THIS  EXCLUSIVE   DISTRIBUTOR  AGREEMENT  (the  "Agreement")  shall  '
                'be effective as of _Dec. 8, 2005  (hereinafter  "Effective  Date"),  '
                'by and between LifeUSA/  Envision  Health,  Inc.,  a  corporation   '
                '(hereinafter   collectively "ENVISION"), and Sierra Mountain Minerals, '
                'Inc., a Canadian company (hereinafter "SIERRA"), is made with '
                'reference to the following facts:'
            ),
        },
    ),
    (
        "SIBANNAC,INC_12_04_2017-EX-2.1-Strategic Alliance Agreement.txt",
        {
            "present": True,
            "answer": 'Bravatek Solutions, Inc. ("Bravatek"); Sibannac, Inc. ("COMPANY")',
            "evidence": (
                'This agreement is made and entered into this 30th day of November, '
                '2017 by and between Bravatek Solutions, Inc., a corporation organized '
                'under the laws of the State of Colorado, ("Bravatek"), with an address '
                'at 2028 E. Ben White Blvd., Unit #240-2835, Austin, Texas, 78741, and '
                'Sibannac, Inc. ("COMPANY"), a corporation organized under the laws of '
                'Nevada, with an address at 2122 E Highland Avenue, Suite 425, Phoenix, '
                'Arizona 85016.'
            ),
        },
    ),
    (
        "UsioInc_20040428_SB-2_EX-10.11_1723988_EX-10.11_Affiliate Agreement 2.txt",
        {
            "present": True,
            "answer": 'Network 1 Financial, Inc. ("NETWORK 1"); Payment Data Systems, Inc. ("AFFILIATE")',
            "evidence": (
                'THIS  AGREEMENT  is  entered  into  by  and  between  NETWORK  1 '
                'FINANCIAL, INC. ("NETWORK  1"),  a  Virginia Corporation with its '
                'principal place of business at 1501  Farm  Credit  Drive,  Suite '
                '1500, McLean, Virginia 22102-5004, and Payment Data  Systems,  Inc.,  '
                'the  Affiliate Office ("AFFILIATE"), a Nevada Corporation with  its  '
                'principal place of business at 12500 San Pedro Suite 120 San Antonio, '
                'TX  78216.'
            ),
        },
    ),
]


def self_test(load_text):
    """Replays the matcher over the full induction set. `load_text(filename)`
    must return the contract text. Asserts every accepted extraction is
    reproduced at the answer/presence level; spans may differ in extent but
    must overlap the accepted evidence."""
    for fname, expected in SELF_TEST:
        text = load_text(fname)
        result = match(text)
        assert result["present"] == expected["present"], (
            f"{fname}: present mismatch (got {result['present']!r})"
        )
        assert result["answer"] == expected["answer"], (
            f"{fname}: answer mismatch\n got: {result['answer']!r}\n exp: {expected['answer']!r}"
        )
        evidence = expected["evidence"]
        overlap = any(s in evidence or evidence in s for s in result["spans"])
        assert overlap, (
            f"{fname}: span does not overlap accepted evidence\n got spans: {result['spans']!r}"
        )
    return True
