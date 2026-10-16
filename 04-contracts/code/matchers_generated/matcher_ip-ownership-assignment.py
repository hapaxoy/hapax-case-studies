"""
CATEGORY: IP Ownership Assignment (yes/no)
TRUST: one-sided (present:True confident hits only; everything else -> NoMatch)
INDUCTION SET: 9 accepted positives (see PROVENANCE below); 0 negatives supplied
BRIEF: overseer_brief_v1, 3 July 2026
DATE INDUCED: 3 July 2026

WHAT THIS MATCHER LOOKS FOR, IN PLAIN LANGUAGE.

The category asks whether IP created by one party becomes the property of the
counterparty, per the contract's terms or upon a triggering event (creation,
delivery, payment). Across the 9 accepted positives the operative language is
genuinely bespoke -- this category sat at the bottom of the published
difficulty figure for a reason -- but five recurring skeletons cover all nine:

  (A) an ASSIGNMENT verb (assign/assigns/assigned/transfer and assign/hereby
      assigns/grant and assign, etc.) governing an IP-shaped object (rights,
      right/title/interest, ownership, "Assigned IP", "Transferred Assets",
      "Developments", copyright, etc.) running "to" a named party -- e.g.
      Armstrong ("Arizona ... hereby assigns its entire right, title and
      interest ... to the Company"), Corio ("hereby assigns all rights in
      and to such Developments to Corio"), Igene ("sufficient to transfer
      Igene's right, title and interest in the Transferred Assets to the
      Operating Company"), Theravance ("hereby assigns all right, title and
      interest in the Company IP to the Company"), Pelican ("hereby assigns
      and transfers to Client all copyright and other intellectual property
      ownership in the Works"), Gpaq ("hereby granted and assigned to
      PFHOF").
  (B) a PROPERTY-OF clause naming a specific party as owner of created work
      -- "sole and absolute/exclusive property of X", "shall be [and
      remain] the property of X" -- e.g. Coral Gold ("will be the sole and
      absolute property of the Company"), EcoScience ("shall be and remain
      the property of ESSI"), Pelican ("shall be the sole and exclusive
      property of the Client").
  (C) an automatic VESTING clause -- "shall automatically ... vest in the
      Company" -- e.g. Theravance.
  (D) an OWN-AND-CONTROL clause -- "shall own and control all right,
      title, interest[,] and copyright in and to" -- e.g. Gpaq.
  (E) a bespoke EXCLUSIVE-RIGHTS-ARISING-FROM-OR-CREATED-BY clause -- e.g.
      Senmiao ("has exclusive rights and interests in all rights,
      ownership, titles, interests and intellectual property rights
      arising from or created by the performance of this Agreement").

KNOWN LIMITS (published honestly).
  - This is five narrow templates, not a semantic understanding of
    "ownership transfer". Any positive phrased differently -- e.g. pure
    "sole and exclusive owner" without "property of"/"assign"/"vest", or an
    ownership transfer buried in a defined-term cross-reference with no
    local anchor phrase -- will raise NoMatch, i.e. a false negative (silent
    under one-sided trust, which is the safe failure direction here).
  - Pattern (A) explicitly excludes clauses containing "retain" nearby,
    because two of the nine induction contracts (Corio, Pelican) contain a
    same-document decoy where the OTHER party retains/keeps ownership
    ("Commerce One shall retain all right, title and interest ...",
    "Developer shall retain full ownership over its Developer Technology")
    a few sentences from the true assignment clause. This exclusion is a
    blunt instrument: a genuine assignment sentence that happens to mention
    "retain" for an unrelated carve-out elsewhere in the same window would
    also be suppressed (false negative, safe direction).
  - Pattern (A) also excludes "assign(s/ed) ... this Agreement", "shall
    not/may not assign", and "non-assignable"/"not assignable" -- these are
    ordinary anti-assignment-of-the-contract boilerplate (present in 3 of
    the 9 induction contracts) and share the verb "assign" but say nothing
    about IP ownership. A contract that assigns IP using only the bare verb
    "assign" pointed at an object this filter doesn't recognise as
    IP-shaped will be missed.
  - Pattern (B) excludes generic role-holders ("the Disclosing Party",
    "the Receiving Party", "either/each/such/the other Party") after "of",
    because Pelican's own contract contains a mutual, symmetric decoy
    ("Confidential Information ... remain the property of the Disclosing
    Party") that is not a one-directional IP assignment. A real positive
    phrased as "property of the Receiving Party" (unusual, but possible)
    would be missed by this exclusion.
  - None of the five patterns attempt to distinguish "IP created under this
    agreement" from "IP already owned pre-existing" -- they trust the local
    anchor phrase. A contract that assigns pre-existing (not newly created)
    IP would still match; that is arguably still an ownership assignment
    per the category definition, so this is treated as in-scope, not a
    limitation.
  - Not evaluated against true negatives: this commission's induction set
    supplied 0 accepted negatives, so precision against genuine "each party
    retains its own IP" contracts rests only on the decoys that happen to
    co-occur in these 9 positive contracts, not on a held-out negative set.
  - Standard library only, no semantic parsing: everything is regex over
    raw text with generous whitespace tolerance (contract text in this
    corpus frequently hard-wraps mid-sentence with runs of spaces).

Expected coverage: reproduces all 9 induction positives. Real-world recall
on the wider corpus is unknown and likely well under 100% given how bespoke
this category's language is -- narrowness was chosen deliberately over
breadth, per the overseer instructions for this category.
"""

import re

CATEGORY = "IP Ownership Assignment"
TRUST = "one-sided"
PROVENANCE = {
    "induced_from": [
        "ARMSTRONGFLOORING,INC_01_07_2019-EX-10.2-INTELLECTUAL PROPERTY AGREEMENT.txt",
        "CORALGOLDRESOURCES,LTD_05_28_2020-EX-4.1-CONSULTING AGREEMENT.txt",
        "CORIOINC_07_20_2000-EX-10.5-LICENSE AND HOSTING AGREEMENT.txt",
        "EcoScienceSolutionsInc_20171117_8-K_EX-10.1_10956472_EX-10.1_Endorsement Agreement.txt",
        "GpaqAcquisitionHoldingsInc_20200123_S-4A_EX-10.6_11951677_EX-10.6_License Agreement.txt",
        "IGENEBIOTECHNOLOGYINC_05_13_2003-EX-1-JOINT VENTURE AGREEMENT.txt",
        "PelicanDeliversInc_20200211_S-1_EX-10.3_11975895_EX-10.3_Development Agreement2.txt",
        "SENMIAOTECHNOLOGYLTD_02_19_2019-EX-10.5-Collaboration Agreement.txt",
        "THERAVANCEBIOPHARMA,INC_05_08_2020-EX-10.2-SERVICE AGREEMENT.txt",
    ],
    "brief": "overseer_brief_v1",
    "commission": "c09-ip-ownership-assignment",
}


class NoMatch(Exception):
    """Raised when the matcher cannot answer. NEVER guess instead."""


# --- shared building blocks ---------------------------------------------
# Gaps between anchor phrases are written inline as [\s\S]{0,N}? rather than
# with '.' + re.DOTALL, since contract text in this corpus frequently
# hard-wraps mid-sentence with runs of embedded whitespace/newlines.

_ROLE_HOLDERS = (
    r"(?:the\s+)?(?:disclosing|receiving|other|applicable|respective|relevant|"
    r"transferring|sending|originating|providing|developing|creating|"
    r"contributing|non-disclosing|owning|original)\s+part(?:y|ies)|"
    r"either\s+part(?:y|ies)|"
    r"each\s+part(?:y|ies)|"
    r"such\s+part(?:y|ies)|"
    r"both\s+part(?:ies|y)|"
    r"the\s+part(?:y|ies)|"
    r"that\s+part(?:y|ies)"
)

_NEGATION_NEAR_ASSIGN = re.compile(
    r"\b(?:shall\s+not|will\s+not|may\s+not|cannot|not\s+be|without\s+the\s+prior)\b[\s\S]{0,60}?assign",
    re.IGNORECASE,
)

_SENT_BOUNDARY = re.compile(r"(?<=[.;:])\s+(?=[A-Z0-9])")

_AGREEMENT_OBJECT = re.compile(
    r"assign(?:s|ed|able)?\s*(?:,)?\s*(?:this\s+Agreement|the\s+Agreement|hereof)",
    re.IGNORECASE,
)

_NON_ASSIGNABLE = re.compile(r"non-assignable|not\s+assignable", re.IGNORECASE)

_SUCCESSORS_ASSIGNS = re.compile(r"successors\s+and\s*$", re.IGNORECASE)

_RETAIN_NEARBY = re.compile(r"\bretain(?:s|ed|ing)?\b", re.IGNORECASE)

_IP_OBJECT_ANCHOR = re.compile(
    r"right,?\s*title\b|"
    r"\ball\s+rights?\b|"
    r"\bownership\b|"
    r"\bcopyright\b|"
    r"\bAssigned\s+IP\b|"
    r"\bTransferred\s+Assets\b|"
    r"\bDevelopments\b|"
    r"\bintellectual\s+property\b|"
    r"\binvention",
    re.IGNORECASE,
)

_PARTY_TAIL = re.compile(
    r"\bto\s+(?:the\s+)?([A-Z][A-Za-z0-9&.,'/-]*(?:\s+[A-Z][A-Za-z0-9&.,'/-]*){0,4})"
)


def _sentence_spans(text):
    """Split text into sentence-like (start, end) spans on '.'/';'/':'
    followed by whitespace and a capital letter or digit. Deliberately does
    not split mid-clause on decimal section numbers (e.g. '3.2') because
    those have no whitespace immediately after the inner period."""
    starts = [0]
    ends = []
    for m in _SENT_BOUNDARY.finditer(text):
        ends.append(m.start())
        starts.append(m.end())
    ends.append(len(text))
    return list(zip(starts, ends))


def _sentence_containing(spans, pos):
    for start, end in spans:
        if start <= pos < end:
            return start, end
    return 0, len(spans[-1]) if spans else 0


def _pattern_a_assignment(text):
    """Assignment verb governing an IP-shaped object, running 'to <Party>',
    scoped to the single sentence containing the verb (never a fixed-size
    character window) so an unrelated anchor phrase or party name in a
    neighbouring sentence cannot be swept in."""
    spans = _sentence_spans(text)
    # Case-sensitive on purpose: a lower-case leading 'a' is how every true
    # assignment verb appears in the induction set ("agrees to assign",
    # "hereby assigns"). A capitalised "Assign(ed)" is, in every induction
    # contract, part of a Title-Case defined term ("Arizona Assigned IP",
    # "Assigned Copyrights") rather than a verb, and matching those produces
    # false hits inside definitions sections. Narrow trade-off: a genuine
    # assignment verb capitalised at the very start of a sentence would be
    # missed (none of the 9 positives do this).
    for m in re.finditer(r"\bassign(?:s|ed)?\b", text):
        verb_start = m.start()
        w_start, w_end = _sentence_containing(spans, verb_start)
        # skip anti-assignment-of-contract boilerplate
        local = text[max(w_start, verb_start - 60):verb_start + 20]
        if _NEGATION_NEAR_ASSIGN.search(local):
            continue
        if _AGREEMENT_OBJECT.search(text[verb_start:verb_start + 60]):
            continue
        # skip "successors and assigns" (indemnitee-class boilerplate,
        # noun not verb)
        if _SUCCESSORS_ASSIGNS.search(text[max(w_start, verb_start - 25):verb_start]):
            continue
        if _NON_ASSIGNABLE.search(text[max(w_start, verb_start - 20):min(w_end, verb_start + 20)]):
            continue
        if _RETAIN_NEARBY.search(text[w_start:w_end]):
            continue
        if not _IP_OBJECT_ANCHOR.search(text[verb_start:w_end]):
            continue
        tail_match = _PARTY_TAIL.search(text, verb_start, w_end)
        if not tail_match:
            continue
        party = tail_match.group(1)
        if re.match(r"this\s+Agreement|the\s+Agreement", party, re.IGNORECASE):
            continue
        span_start = max(w_start, verb_start - 80)
        span_end = min(w_end, tail_match.end())
        span = text[span_start:span_end].strip()
        if span:
            return span
    return None


_PROPERTY_OF = re.compile(
    r"(?:shall\s+be(?:\s+and\s+remain)?|will\s+be|shall\s+remain|remain)\s+the\s+sole\s+(?:and\s+(?:absolute|exclusive)\s+)?property\s+of\s+([A-Z][A-Za-z0-9&.,'/ -]{0,60}?)(?=[.;])"
    r"|"
    r"(?:shall\s+be(?:\s+and\s+remain)?|will\s+be(?:\s+and\s+remain)?|shall\s+remain)\s+the\s+property\s+of\s+([A-Z][A-Za-z0-9&.,'/ -]{0,60}?)(?=[.;])",
    re.IGNORECASE,
)


def _pattern_b_property_of(text):
    for m in re.finditer(_PROPERTY_OF, text):
        party = m.group(1) or m.group(2)
        if party and re.fullmatch(_ROLE_HOLDERS, party.strip(), re.IGNORECASE):
            continue
        return m.group(0).strip()
    return None


_VEST = re.compile(
    r"\bshall\s+automatically[\s\S]{0,40}?\bvest\s+in\s+the\s+[A-Z][A-Za-z0-9&.,'/ -]{0,40}?(?=[.;])"
    r"|\bshall\s+vest\s+in\s+the\s+[A-Z][A-Za-z0-9&.,'/ -]{0,40}?(?=[.;])",
    re.IGNORECASE,
)


def _pattern_c_vest(text):
    m = _VEST.search(text)
    return m.group(0).strip() if m else None


_OWN_AND_CONTROL = re.compile(
    r"\b(?:shall\s+)?own\s+and\s+control\s+all\s+right,?\s*title,?\s*interest,?\s*(?:and\s+)?copyright\s+in\s+and\s+to[\s\S]{0,700}?(?=[.;])",
    re.IGNORECASE,
)


def _pattern_d_own_and_control(text):
    m = _OWN_AND_CONTROL.search(text)
    return m.group(0).strip() if m else None


_EXCLUSIVE_ARISING = re.compile(
    r"(?:exclusive\s+)?rights?\s+and\s+interests?\s+in\s+all\s+rights,?\s*ownership,?\s*titles?,?\s*interests?\s+and\s+intellectual\s+property\s+rights\s+arising\s+from\s+or\s+created\s+by[\s\S]{0,80}?(?=[.;])",
    re.IGNORECASE,
)


def _pattern_e_exclusive_arising(text):
    m = _EXCLUSIVE_ARISING.search(text)
    return m.group(0).strip() if m else None


_DETECTORS = (
    _pattern_a_assignment,
    _pattern_b_property_of,
    _pattern_c_vest,
    _pattern_d_own_and_control,
    _pattern_e_exclusive_arising,
)


def match(text: str) -> dict:
    """Answer the category question from raw contract text.
    Returns {"present": bool, "spans": [str, ...], "answer": str | None}
    — same shape as the model's answers for this category.
    Raises NoMatch when the text doesn't fit the patterns you trust."""
    if not isinstance(text, str) or not text.strip():
        raise NoMatch("empty input")

    spans = []
    for detector in _DETECTORS:
        try:
            hit = detector(text)
        except re.error:
            hit = None
        if hit:
            spans.append(hit)

    if not spans:
        raise NoMatch("no trusted IP-ownership-assignment pattern found")

    return {"present": True, "spans": spans, "answer": None}


# --- mandatory self-test -------------------------------------------------

SELF_TEST = [
    ("ARMSTRONGFLOORING,INC_01_07_2019-EX-10.2-INTELLECTUAL PROPERTY AGREEMENT.txt", True),
    ("CORALGOLDRESOURCES,LTD_05_28_2020-EX-4.1-CONSULTING AGREEMENT.txt", True),
    ("CORIOINC_07_20_2000-EX-10.5-LICENSE AND HOSTING AGREEMENT.txt", True),
    ("EcoScienceSolutionsInc_20171117_8-K_EX-10.1_10956472_EX-10.1_Endorsement Agreement.txt", True),
    ("GpaqAcquisitionHoldingsInc_20200123_S-4A_EX-10.6_11951677_EX-10.6_License Agreement.txt", True),
    ("IGENEBIOTECHNOLOGYINC_05_13_2003-EX-1-JOINT VENTURE AGREEMENT.txt", True),
    ("PelicanDeliversInc_20200211_S-1_EX-10.3_11975895_EX-10.3_Development Agreement2.txt", True),
    ("SENMIAOTECHNOLOGYLTD_02_19_2019-EX-10.5-Collaboration Agreement.txt", True),
    ("THERAVANCEBIOPHARMA,INC_05_08_2020-EX-10.2-SERVICE AGREEMENT.txt", True),
]

_ACCEPTED_SPANS = {
    "ARMSTRONGFLOORING,INC_01_07_2019-EX-10.2-INTELLECTUAL PROPERTY AGREEMENT.txt": [
        "2.1 Assignment. Arizona agrees to assign and hereby assigns its entire right, title and interest in and to the Arizona Assigned IP to the Company.",
    ],
    "CORALGOLDRESOURCES,LTD_05_28_2020-EX-4.1-CONSULTING AGREEMENT.txt": [
        "will be the sole and absolute property of the Company",
    ],
    "CORIOINC_07_20_2000-EX-10.5-LICENSE AND HOSTING AGREEMENT.txt": [
        "Commerce One hereby assigns all rights in and to such         Developments to Corio",
    ],
    "EcoScienceSolutionsInc_20171117_8-K_EX-10.1_10956472_EX-10.1_Endorsement Agreement.txt": [
        "shall be and remain the property of ESSI",
    ],
    "GpaqAcquisitionHoldingsInc_20200123_S-4A_EX-10.6_11951677_EX-10.6_License Agreement.txt": [
        "PFHOF shall own and control all right, title, interest, and copyright in and to the PFHOF Works",
        "hereby granted and assigned to PFHOF",
    ],
    "IGENEBIOTECHNOLOGYINC_05_13_2003-EX-1-JOINT VENTURE AGREEMENT.txt": [
        "3.2. Subject to the terms and conditions of this Agreement, Igene shall transfer and assign, or cause to be transferred and assigned,",
        "to the Operating Company the Transferred Assets described in Appendix 3.2.",
        "this Agreement and each document contemplated hereby is sufficient to transfer Igene's right, title and interest in the Transferred Assets to the Operating Company",
    ],
    "PelicanDeliversInc_20200211_S-1_EX-10.3_11975895_EX-10.3_Development Agreement2.txt": [
        "Developer hereby assigns and transfers to Client all copyright and other intellectual property ownership in the Works",
        "sole and exclusive property of the Client",
    ],
    "SENMIAOTECHNOLOGYLTD_02_19_2019-EX-10.5-Collaboration Agreement.txt": [
        "exclusive rights and interests in all rights, ownership, titles, interests and intellectual property rights arising from or created by the performance of this Agreement",
    ],
    "THERAVANCEBIOPHARMA,INC_05_08_2020-EX-10.2-SERVICE AGREEMENT.txt": [
        "shall automatically, on creation, vest in the Company absolutely",
        "hereby assigns all right, title and interest in the Company IP to the Company",
    ],
}


def _normalise(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def _ngram_overlap(a, b, n=5):
    """True if a contiguous n-word run from a's normalised form appears in
    b's normalised form (in either direction). Tolerant of the fact that
    this matcher's spans need not extent-match the accepted evidence."""
    aw = _normalise(a).split()
    bn = _normalise(b)
    if len(aw) < n:
        return _normalise(a) in bn or bn in _normalise(a)
    for i in range(len(aw) - n + 1):
        gram = " ".join(aw[i:i + n])
        if gram in bn:
            return True
    return False


def _overlaps_accepted(returned_spans, accepted_spans):
    for r in returned_spans:
        for acc in accepted_spans:
            if _ngram_overlap(r, acc) or _ngram_overlap(acc, r):
                return True
    return False


def self_test(load_text):
    """Replays the matcher over the full induction set. `load_text` is a
    callable: filename -> contract text. Asserts presence is reproduced for
    every accepted extraction and that at least one returned span overlaps
    the accepted evidence."""
    for filename, expected_present in SELF_TEST:
        text = load_text(filename)
        try:
            result = match(text)
        except NoMatch:
            if expected_present:
                raise AssertionError(f"{filename}: expected present=True, got NoMatch")
            continue
        assert result["present"] == expected_present, (
            f"{filename}: expected present={expected_present}, got {result['present']}"
        )
        accepted = _ACCEPTED_SPANS.get(filename, [])
        if accepted:
            assert _overlaps_accepted(result["spans"], accepted), (
                f"{filename}: returned spans {result['spans']!r} do not overlap "
                f"accepted evidence {accepted!r}"
            )
    return True
