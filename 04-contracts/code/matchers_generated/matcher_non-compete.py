# Provenance
# ----------
# Category:        Non-Compete
# Trust grade:      one-sided (present:True + verbatim spans, or NoMatch — never present:False)
# Induction set:    8 accepted positives, 0 accepted negatives
# Date:             2026-07-03
# Brief:            overseer_brief_v1 (commission c10-non-compete)
#
# What was induced, in plain language:
#   Non-Compete clauses restrict a party (or its affiliates) from engaging in a
#   COMPETING business, product line, service, or activity — as distinct from
#   Exclusivity clauses, which restrict a party to dealing/purchasing/sourcing
#   only through the counterparty. Across the 8 accepted positives, the actual
#   restriction always takes one of four recognisable shapes:
#
#     1. "<business|enterprise|entity|product(s)|service(s)|activity> ...
#        compet(e/es/ing/itive/ition) with/to ..." sitting inside a sentence
#        that also carries a prohibition cue ("shall not", "will not", "may
#        not", "prohibited from", "restricted from", "without the prior
#        written consent/notice/approval", or a "neither ... shall" negation).
#        Covers the Quaker Chemical, Legacy Technology, Senmiao/Didi,
#        EcoScience and Usio/Network 1 examples.
#     2. "engage in any enterprise/business ... anywhere in the world / world-
#        wide / any jurisdiction / any territory", again under a prohibition
#        cue. Covers the Igene Biotechnology joint-venture field carve-out.
#     3. "shall not: ... any other manufacturer or seller" — the endorsement-
#        contract shape, where the consultant/talent is barred from lending
#        their name, sponsorship or advisory services to any other maker or
#        seller of the same product. Covers Adams Golf.
#     4. "shall not ... be employed, engaged, concerned or interested in any
#        other ... business, organisation, occupation or profession" — the
#        UK-style personal-services shape. Covers Theravance/Haumann.
#
#   All four require the "compet-" root or an explicit "any other
#   business/enterprise anywhere in the world" / "any other manufacturer or
#   seller" / "employed ... in any other business" backbone; a prohibition
#   cue occurring near a purchasing/sourcing/requirements verb (purchase, buy,
#   procure, acquire, source, "requirements contract", "sole source") is
#   treated as Exclusivity-flavoured and rejected, since that is this
#   category's worst failure mode (an exclusive-dealing or requirements
#   commitment misread as Non-Compete).
#
#   Known limits (published honestly): this matcher will miss non-competes
#   that use neither the "compet-" word family nor these specific structural
#   templates — e.g. a bare list of forbidden industries/customers with no
#   "compete" language and no "anywhere in the world" scope phrase, or
#   non-competes drafted only as defined-term cross-references ("the
#   Restricted Activities" defined elsewhere). It will also miss non-competes
#   embedded in clauses longer than the ~1500-character extraction window.
#   Because TRUST is one-sided, every one of these misses correctly raises
#   NoMatch rather than guessing, so nothing is lost except throughput back
#   to the model.

import re

CATEGORY = "Non-Compete"
TRUST = "one-sided"
PROVENANCE = {
    "induced_from": [
        "ADAMSGOLFINC_03_21_2005-EX-10.17-ENDORSEMENT AGREEMENT.txt",
        "EcoScienceSolutionsInc_20171117_8-K_EX-10.1_10956472_EX-10.1_Endorsement Agreement.txt",
        "IGENEBIOTECHNOLOGYINC_05_13_2003-EX-1-JOINT VENTURE AGREEMENT.txt",
        "LEGACYTECHNOLOGYHOLDINGS,INC_12_09_2005-EX-10.2-DISTRIBUTOR AGREEMENT.txt",
        "Quaker Chemical Corporation - NON COMPETITION AND NON SOLICITATION AGREEMENT.txt",
        "SENMIAOTECHNOLOGYLTD_02_19_2019-EX-10.5-Collaboration Agreement.txt",
        "THERAVANCEBIOPHARMA,INC_05_08_2020-EX-10.2-SERVICE AGREEMENT.txt",
        "UsioInc_20040428_SB-2_EX-10.11_1723988_EX-10.11_Affiliate Agreement 2.txt",
    ],
    "brief": "overseer_brief_v1",
    "commission": "c10-non-compete",
}


class NoMatch(Exception):
    """Raised when the matcher cannot answer. NEVER guess instead."""


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Family 1: "<activity-noun> ... compete(s)/competing/competitive with/to ..."
_COMPETE_PHRASE = re.compile(
    r"\b(?:business|enterprise|entity|product|products|service|services|"
    r"activity|activities)\b[^.]{0,120}?\bcompet(?:e|es|ing|itive|ition)\s+"
    r"(?:with|to)\b",
    re.IGNORECASE,
)

# Prohibition / restriction cue — the clause must be phrased as a bar, not a
# mere description.
_CUE_RE = re.compile(
    r"(?:shall\s+not|will\s+not|may\s+not|is\s+prohibited\s+from|"
    r"are\s+prohibited\s+from|prohibited\s+from|shall\s+be\s+prohibited|"
    r"is\s+restricted\s+from|are\s+restricted\s+from|restricted\s+from|"
    r"without\s+(?:the\s+)?prior\s+written\s+(?:notice|consent|approval)|"
    r"neither\b.{0,60}?\bshall\b)",
    re.IGNORECASE | re.DOTALL,
)

# If a purchasing/sourcing verb governs the restriction nearby, this is very
# likely an Exclusivity / requirements clause wearing "competitive" as an
# adjective, not a Non-Compete — reject it.
_EXCLUDE_NEARBY = re.compile(
    r"\b(?:purchase|purchasing|purchased|buy|buying|procure|procuring|"
    r"acquire|acquiring|source|sourcing|requirements?\s+(?:contract|"
    r"agreement)|sole\s+source|supply\s+solely)\b",
    re.IGNORECASE,
)

# Family 2: "engage in any enterprise/business ... anywhere in the world"
_ENGAGE_PHRASE = re.compile(
    r"engage\s+in\s+any\s+(?:enterprise|business)\b", re.IGNORECASE
)
_BROAD_SCOPE = re.compile(
    r"\b(?:anywhere\s+in\s+the\s+world|world[\s-]?wide|any\s+jurisdiction|"
    r"any\s+territory|globally)\b",
    re.IGNORECASE,
)

# Family 3: endorsement-style "shall not: ... any other manufacturer or seller"
_C1 = re.compile(
    r"shall\s+not\s*:?.{0,300}?\bany\s+other\s+manufacturer\s+or\s+seller\b",
    re.IGNORECASE | re.DOTALL,
)

# Family 4: UK-style "shall not ... employed, engaged, concerned or interested
# in any other ... business/organisation/occupation/profession"
_C2 = re.compile(
    r"shall\s+not\b.{0,260}?\bemployed,\s*engaged,\s*concerned\s+or\s+"
    r"interested\s+in\s+any\s+other\b[^.]{0,120}?\b(?:business|organisation|"
    r"organization|occupation|profession)\b",
    re.IGNORECASE | re.DOTALL,
)


def _context(text, start, end, before=500, after=350):
    return text[max(0, start - before):min(len(text), end + after)]


# Clause/sentence boundary: a period or semicolon followed by whitespace, or
# a blank line. Many of the induction contracts (e.g. numbered breach lists)
# separate clauses with ";" rather than ".", so both must count — otherwise
# the backward scan can run past several unrelated enumerated items before
# finding a bare period, sweeping unrelated clauses into the span.
_BOUNDARY = re.compile(r"[.;]\s+|\n\s*\n")


def _extract_clause(text, start, end, max_back=1500, max_fwd=1500):
    """Expand a raw phrase match outward to the nearest clause boundary so
    the returned span reads as a self-contained clause rather than a bare
    phrase or a runaway multi-clause block. Always returns a contiguous,
    verbatim substring of `text`."""
    back_limit = max(0, start - max_back)
    clause_start = back_limit
    for bm in _BOUNDARY.finditer(text, back_limit, start):
        clause_start = bm.end()

    fwd_limit = min(len(text), end + max_fwd)
    fm = _BOUNDARY.search(text, end, fwd_limit)
    clause_end = fm.end() if fm else fwd_limit

    return text[clause_start:clause_end].strip()


def _try_family_compete(text):
    for m in _COMPETE_PHRASE.finditer(text):
        start, end = m.span()
        ctx = _context(text, start, end)
        if not _CUE_RE.search(ctx):
            continue
        if _EXCLUDE_NEARBY.search(ctx):
            continue
        clause = _extract_clause(text, start, end)
        if clause:
            return clause
    return None


def _try_family_engage_world(text):
    for m in _ENGAGE_PHRASE.finditer(text):
        start, end = m.span()
        ctx = _context(text, start, end)
        if not _BROAD_SCOPE.search(ctx):
            continue
        if not _CUE_RE.search(ctx):
            continue
        if _EXCLUDE_NEARBY.search(ctx):
            continue
        clause = _extract_clause(text, start, end)
        if clause:
            return clause
    return None


def _try_family_manufacturer_or_seller(text):
    for m in _C1.finditer(text):
        start, end = m.span()
        ctx = _context(text, start, end, before=200, after=200)
        if _EXCLUDE_NEARBY.search(ctx):
            continue
        span = m.group(0).strip()
        if span:
            return span
    return None


def _try_family_employed_interested(text):
    for m in _C2.finditer(text):
        start, end = m.span()
        ctx = _context(text, start, end, before=200, after=200)
        if _EXCLUDE_NEARBY.search(ctx):
            continue
        span = m.group(0).strip()
        if span:
            return span
    return None


def match(text: str) -> dict:
    """Answer the Non-Compete question from raw contract text.

    Returns {"present": bool, "spans": [str, ...], "answer": str | None}.
    Raises NoMatch when the text doesn't fit the induced patterns — for this
    one-sided category, NoMatch is the only negative outcome; `present:
    False` is never returned.
    """
    if not isinstance(text, str) or not text.strip():
        raise NoMatch("empty or non-string input")

    span = _try_family_compete(text)
    if span is None:
        span = _try_family_engage_world(text)
    if span is None:
        span = _try_family_manufacturer_or_seller(text)
    if span is None:
        span = _try_family_employed_interested(text)

    if span is None:
        raise NoMatch(
            "no unambiguous competitive-activity restriction pattern found"
        )

    return {"present": True, "spans": [span], "answer": None}


# ---------------------------------------------------------------------------
# Mandatory self-test
# ---------------------------------------------------------------------------

SELF_TEST = [
    (
        "ADAMSGOLFINC_03_21_2005-EX-10.17-ENDORSEMENT AGREEMENT.txt",
        True,
        [
            "During the term of this Agreement, unless otherwise authorized "
            "at the sole discretion of ADAMS GOLF in writing, CONSULTANT "
            "shall not:",
            "A.give the right to use or permit the use of CONSULTANT'S "
            "name, facsimile signature, nickname, voice or likeness to any "
            "other manufacturer or seller of PRODUCT;",
        ],
    ),
    (
        "EcoScienceSolutionsInc_20171117_8-K_EX-10.1_10956472_EX-10.1_"
        "Endorsement Agreement.txt",
        True,
        [
            "Talent represents and warrants that during the Term and in "
            "the Territories, Talent will not endorse or make any "
            "appearances or advertisements on behalf of any other product "
            "which is directly competitive to ESSI's products."
        ],
    ),
    (
        "IGENEBIOTECHNOLOGYINC_05_13_2003-EX-1-JOINT VENTURE AGREEMENT.txt",
        True,
        [
            "After the Effective Date and as long as Igene and T&L "
            "continue to own an interest in the Operating Company, neither "
            "of the Parties shall, or shall cause or permit any of their "
            "Affiliates to, directly or indirectly, as stockholders, "
            "consultants, members, partners or in any other capacity, "
            "engage in any enterprise or business anywhere in the world, "
            "which (a) manufactures Astaxanthin or (b) develops, markets, "
            "or sells products falling within the Field of Agreement."
        ],
    ),
    (
        "LEGACYTECHNOLOGYHOLDINGS,INC_12_09_2005-EX-10.2-DISTRIBUTOR "
        "AGREEMENT.txt",
        True,
        [
            "Neither party may use the proprietary information except in "
            "furtherance of the goals of this Agreement and is further "
            "prohibited from utilizing the Proprietary Information "
            "directly nor indirectly to engage in any business activity "
            "which is competitive with the other."
        ],
    ),
    (
        "Quaker Chemical Corporation - NON COMPETITION AND NON "
        "SOLICITATION AGREEMENT.txt",
        True,
        [
            "Each Seller agrees that for a period commencing on the "
            "Effective Date and ending two years after the Closing Date "
            '(the "Non- Compete Period"), it shall not, other than solely '
            "through its direct or indirect ownership of Buyer's capital "
            "stock or any other interests in Buyer, directly, or "
            "indirectly, including through or on behalf of a subsidiary, "
            "anywhere in the world, excluding India: (i) own, manage, "
            "operate or control any business which competes with any "
            "Combined Business"
        ],
    ),
    (
        "SENMIAOTECHNOLOGYLTD_02_19_2019-EX-10.5-Collaboration Agreement.txt",
        True,
        [
            "In consideration of the fact that Party B may have access to "
            "the relevant trade secrets of Didi during the cooperation, "
            "Party B or Party B's any affiliate cooperates with any entity "
            "competitive with Didi (including but not limited to Meituan, "
            "CAR, Yongche, izu, Caocao, Dida) in any form without prior "
            "written notice to and confirmation by Didi;"
        ],
    ),
    (
        "THERAVANCEBIOPHARMA,INC_05_08_2020-EX-10.2-SERVICE AGREEMENT.txt",
        True,
        [
            "The Executive shall not during the employment except as a "
            "representative of the Company or with the Company's prior "
            "written consent (whether directly or indirectly, paid or "
            "unpaid) be employed, engaged, concerned or interested in any "
            "other actual or prospective business, organisation, "
            "occupation or profession."
        ],
    ),
    (
        "UsioInc_20040428_SB-2_EX-10.11_1723988_EX-10.11_Affiliate "
        "Agreement 2.txt",
        True,
        [
            "the  providing  of  vendor services or merchant services  by  "
            "Affiliate  or  Contractor(s)  located  by  Affiliate  which  "
            "are competitive  with  Network  1 or without the prior "
            "written consent of Network 1"
        ],
    ),
]


def _overlaps(a, b):
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    n = min(25, len(shorter))
    if n < 8:
        return shorter in longer
    for i in range(0, len(shorter) - n + 1, 5):
        if shorter[i:i + n] in longer:
            return True
    return False


def self_test(load_text):
    """Replay the matcher over the full induction set. `load_text(filename)`
    must return the raw contract text for the given induction filename.
    Raises AssertionError on the first mismatch; returns True if every
    accepted extraction is reproduced."""
    for filename, expected_present, expected_spans in SELF_TEST:
        text = load_text(filename)
        try:
            result = match(text)
        except NoMatch:
            result = None

        if expected_present:
            assert result is not None, (
                f"{filename}: expected present=True, matcher raised NoMatch"
            )
            assert result["present"] is True, (
                f"{filename}: expected present=True, got {result}"
            )
            overlap = any(
                _overlaps(exp, got)
                for exp in expected_spans
                for got in result["spans"]
            )
            assert overlap, (
                f"{filename}: no returned span overlaps accepted evidence\n"
                f"  got: {result['spans']}\n"
                f"  expected (any of): {expected_spans}"
            )
        else:
            assert result is None, (
                f"{filename}: expected NoMatch, matcher returned {result}"
            )
    return True
