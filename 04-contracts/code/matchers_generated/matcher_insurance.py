# Matcher: Insurance (c12-insurance)
# Trust grade: one-sided (present:True with verbatim spans, or NoMatch — never False)
# Induction set: 6 accepted positives, 0 accepted negatives
# Brief: overseer_brief_v1, 3 July 2026
#
# Patterns induced: the six accepted extractions all state that a named party
# (or "each Party" / "Both Parties") is *obligated* to carry insurance for the
# counterparty's benefit. Two surface grammars recur:
#   (1) "<Party> shall (obtain and) maintain / provide (and maintain) / keep
#        in force ... insurance ..." — an affirmative covenant, sometimes with
#        a long intervening qualifier ("at all times during the currency of
#        this Agreement and for a period of ...") before the verb, or with the
#        object list separated by semicolons rather than periods (Regan's
#        5-line schedule of minimum coverages).
#   (2) "<Party> warrants that it carries ... insurance ..." — a warranty of
#        already-held coverage (Legacy/Sierra-Envision), which the extraction
#        instructions explicitly treat as an Insurance requirement.
# The matcher looks for "shall" followed within ~300 characters (no
# intervening "shall", to keep each candidate local) by one of the verbs
# obtain / procure / maintain / provide / keep in force, or for the fixed
# phrase "warrants that it carries", then confirms the word "insurance"
# appears in the same sentence (no period between the verb and "insurance",
# checked in whichever direction — forward for the active-voice cases above,
# backward for passive constructions such as "insurance ... shall be
# maintained"). Candidates containing "not" in the shall-to-verb span are
# dropped (guards against "shall not be required to maintain insurance" and
# similar disclaimers). The returned span is the verb clause expanded to its
# enclosing sentence(s) using nearby ". "/": "/"; " boundaries.
#
# Known limits (published honestly): the matcher only fires on the "shall
# <verb> ... insurance" / "warrants that it carries ... insurance" grammars.
# It will miss requirements phrased with other verbs (e.g. FuseMedical's
# supplementary "The Supplier shall add the distributor to their current
# insurance certificate.", which uses "add" — not in the verb list — so that
# sentence is not separately captured, though the contract's primary
# requirement sentence is). It will also miss a bare heading ("Insurance")
# with no shall/warrants covenant nearby, and any requirement drafted without
# "shall" (e.g. "will maintain", "agrees to procure") since only "shall" and
# "warrants that it carries" are treated as anchors. It deliberately does not
# fire on casual mentions — insurance as a business/industry noun, insurance
# named merely as a shipping/cost item ("packaging, insurance and carriage"),
# or insurance mentioned only as part of an unrelated indemnity/HR clause
# ("employment insurance premiums") — because those lack a "shall <verb>"
# or "warrants that it carries" anchor in the same sentence as the word
# "insurance". Because TRUST is one-sided, any contract that does not fit
# these two grammars raises NoMatch rather than asserting absence.

import re

CATEGORY = "Insurance"
TRUST = "one-sided"
PROVENANCE = {
    "induced_from": [
        "CARDAX,INC_08_19_2014-EX-10.1-COLLABORATION AGREEMENT.txt",
        "EhaveInc_20190515_20-F_EX-4.44_11678816_EX-4.44_License Agreement_ Reseller Agreement.txt",
        "FuseMedicalInc_20190321_10-K_EX-10.43_11575454_EX-10.43_Distributor Agreement.txt",
        "LEGACYTECHNOLOGYHOLDINGS,INC_12_09_2005-EX-10.2-DISTRIBUTOR AGREEMENT.txt",
        "PROLONGINTERNATIONALCORP_03_23_1998-EX-10.16-SPONSORSHIP AGREEMENT.txt",
        "REGANHOLDINGCORP_03_31_2008-EX-10-LICENSE AND HOSTING AGREEMENT.txt",
    ],
    "brief": "overseer_brief_v1",
    "commission": "c12-insurance",
}


class NoMatch(Exception):
    """Raised when the matcher cannot answer. NEVER guess instead."""


# --- tuning constants -------------------------------------------------

_VERB_GAP = 300          # max chars between "shall" and the obligation verb
_FORWARD_LOOKAHEAD = 400  # max chars scanned forward for "insurance"
_BACKWARD_LOOKAHEAD = 200  # max chars scanned backward for "insurance"
_CLAUSE_BACK = 200        # max chars scanned backward for a sentence boundary
_CLAUSE_FWD = 1600        # max chars scanned forward for the clause's end

# --- patterns -----------------------------------------------------------

_SHALL_VERB = re.compile(
    r"\bshall\b(?:(?!\bshall\b)[\s\S]){0,%d}?"
    r"\b(?:obtain|procure|maintain|provide|keep\s+in\s+force)\b" % _VERB_GAP,
    re.IGNORECASE,
)

_WARRANT_CARRY = re.compile(
    r"\bwarrants?\s+that\s+it\s+carries\b",
    re.IGNORECASE,
)

_INSURANCE_WORD = re.compile(r"\binsurance\b", re.IGNORECASE)
_NOT_WORD = re.compile(r"\bnot\b", re.IGNORECASE)

_SENT_BOUNDARY_LEFT = re.compile(r"[.:;]\s+(?=[A-Z0-9(])")
_SENT_END = re.compile(r"\.(?:\s|$)")


def _locate_insurance(text, trigger_start, trigger_end):
    """Find the nearest same-sentence 'insurance' occurrence, forward
    (active voice: '<verb> ... insurance') or backward (passive voice:
    'insurance ... shall be <verb>'). Returns (start, end) or None."""
    tail = text[trigger_end:trigger_end + _FORWARD_LOOKAHEAD]
    m = _INSURANCE_WORD.search(tail)
    if m and "." not in tail[: m.start()]:
        return trigger_end + m.start(), trigger_end + m.end()

    head_lo = max(0, trigger_start - _BACKWARD_LOOKAHEAD)
    head = text[head_lo:trigger_start]
    matches = list(_INSURANCE_WORD.finditer(head))
    if matches:
        last = matches[-1]
        between = head[last.end():]
        if "." not in between:
            return head_lo + last.start(), head_lo + last.end()

    return None


def _expand_to_clause(text, start, end):
    """Expand [start, end) to its enclosing sentence(s), bounded so a
    missing boundary never runs away across the whole document."""
    lo = max(0, start - _CLAUSE_BACK)
    left = text[lo:start]
    boundaries = list(_SENT_BOUNDARY_LEFT.finditer(left))
    span_start = lo + boundaries[-1].end() if boundaries else lo

    hi = min(len(text), end + _CLAUSE_FWD)
    right = text[end:hi]
    m = _SENT_END.search(right)
    span_end = end + m.end() if m else hi

    return span_start, span_end


def _find_insurance_clauses(text):
    candidates = list(_SHALL_VERB.finditer(text)) + list(_WARRANT_CARRY.finditer(text))
    candidates.sort(key=lambda m: m.start())

    spans = []
    claimed = []
    for m in candidates:
        if _NOT_WORD.search(m.group(0)):
            continue
        loc = _locate_insurance(text, m.start(), m.end())
        if loc is None:
            continue
        ins_start, ins_end = loc
        clause_start, clause_end = _expand_to_clause(
            text, min(m.start(), ins_start), max(m.end(), ins_end)
        )
        if any(clause_start < c_end and clause_end > c_start for c_start, c_end in claimed):
            continue
        claimed.append((clause_start, clause_end))
        span_text = text[clause_start:clause_end].strip()
        if span_text:
            spans.append(span_text)

    return spans


def match(text: str) -> dict:
    """Answer the Insurance category question from raw contract text.
    Returns {"present": bool, "spans": [str, ...], "answer": str | None}
    Raises NoMatch when the text doesn't fit the patterns trusted here."""
    spans = _find_insurance_clauses(text)
    if not spans:
        raise NoMatch("no confident insurance-requirement clause found")
    return {"present": True, "spans": spans, "answer": None}


# --- mandatory self-test -------------------------------------------------

SELF_TEST = [
    ("CARDAX,INC_08_19_2014-EX-10.1-COLLABORATION AGREEMENT.txt", True),
    (
        "EhaveInc_20190515_20-F_EX-4.44_11678816_EX-4.44_License Agreement_ Reseller Agreement.txt",
        True,
    ),
    (
        "FuseMedicalInc_20190321_10-K_EX-10.43_11575454_EX-10.43_Distributor Agreement.txt",
        True,
    ),
    (
        "LEGACYTECHNOLOGYHOLDINGS,INC_12_09_2005-EX-10.2-DISTRIBUTOR AGREEMENT.txt",
        True,
    ),
    (
        "PROLONGINTERNATIONALCORP_03_23_1998-EX-10.16-SPONSORSHIP AGREEMENT.txt",
        True,
    ),
    (
        "REGANHOLDINGCORP_03_31_2008-EX-10-LICENSE AND HOSTING AGREEMENT.txt",
        True,
    ),
]

# Verbatim accepted spans (from the induction JSONs), used only to check
# that our spans overlap the accepted evidence — not re-read from disk.
_ACCEPTED_SPANS = {
    "CARDAX,INC_08_19_2014-EX-10.1-COLLABORATION AGREEMENT.txt": [
        "8.5 Insurance. During the Term and for a period of two (2) years after "
        "the termination of the Agreement or the expiry date of the last batch "
        "manufactured whichever is later, thereafter, each Party shall obtain "
        "and maintain, at its sole expense adequate product liability insurance "
        "for the Product as it reasonably deems necessary and appropriate. "
        "Evidence of coverage, in the form of certificates of insurance, shall "
        "be provided promptly upon registration of the Product in given "
        "countries and as reasonably requested thereafter.",
    ],
    "EhaveInc_20190515_20-F_EX-4.44_11678816_EX-4.44_License Agreement_ Reseller Agreement.txt": [
        "(a) Required Insurance: Both Parties shall, at all times during the "
        "currency of this Agreement and for a period of one (1) year after the "
        "termination or expiration of this Agreement, maintain the following "
        "policies of insurance in effect: (i) a comprehensive general liability "
        "insurance policy, with minimum coverage of $1,000,000 per occurrence "
        "and in the annual aggregate for product liability and completed "
        "operations, covering bodily and personal injury, including death, and "
        "property damage, including loss of use; and (ii) an information and "
        "network technology blended liability insurance policy with an insured "
        "limit of at least $1,000,000 in the aggregate.",
    ],
    "FuseMedicalInc_20190321_10-K_EX-10.43_11575454_EX-10.43_Distributor Agreement.txt": [
        "10.3 During the Term, the Supplier shall maintain product liability "
        "insurance with a reputable insurer of no less than AU$10 million for "
        "any one occurrence for any and all liability (however arising) for a "
        "claim that the Products are faulty or defective. The Supplier shall "
        "provide a copy of the insurance policy to the Distributor on request.",
        "The Supplier shall add the distributor to their current insurance "
        "certificate.",
    ],
    "LEGACYTECHNOLOGYHOLDINGS,INC_12_09_2005-EX-10.2-DISTRIBUTOR AGREEMENT.txt": [
        "SIERRA  warrants  that it carries  general  liability  insurance of not "
        "less than $2 million  per occurrence and product liability insurance of "
        "not less than $5 million  per occurrence  and that,  upon the execution "
        "of this Agreement,  it  will name ENVISION as an additional  insured on "
        "such policies.",
        "ENVISION  warrants  that it "
        "carries  general  liability  insurance of $1 million per occurrence and "
        "product liability  insurance of not less than $2 million per occurrence "
        "and that, upon execution of this  Agreement,  it will name SIERRA as an "
        "additional insured on such policies.",
    ],
    "PROLONGINTERNATIONALCORP_03_23_1998-EX-10.16-SPONSORSHIP AGREEMENT.txt": [
        "11.  Insurance.  Sabco shall provide at its expense and maintain "
        "throughout           --------- the term of this Agreement and any "
        "option period spectator liability insurance  in an amount not less "
        "than $1 million single limit coverage with respect to any  liability "
        "relating to the activities of Sabco in the performance of this  "
        "Agreement.  Sabco shall, within 90 days of the execution of this "
        "Agreement,  supply Prolong with a copy of such policy of insurance or "
        "a certificate thereof, and such policies shall be cancelable only upon "
        "10 days written notice to  Prolong.",
    ],
    "REGANHOLDINGCORP_03_31_2008-EX-10-LICENSE AND HOSTING AGREEMENT.txt": [
        "During the Term of the Agreement, LMG shall maintain and keep in "
        "force, at its own expense, the following minimum insurance coverages "
        "and minimum limits:",
        "commercial general liability insurance, covering claims for bodily "
        "injury, death and property damage, including premises and "
        "operations, LMG's vicarious liability for acts of independent "
        "contractors, products, services and completed operations (as "
        "applicable to the Services), personal injury, contractual, and "
        "broad-form property damage liability coverages, with combined single "
        "limit of $1,000,000 per occurrence, and a general aggregate limit of "
        "$2,000,000, for bodily injury, death and property damage;",
        "TAG shall be named as an additional insured on the commercial general "
        "liability insurance policies described above.",
    ],
}


def _normalize(s):
    return re.sub(r"\s+", " ", s).strip()


def _overlaps(a, b, min_len=20):
    a = _normalize(a)
    b = _normalize(b)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) < min_len:
        return shorter in longer
    step = max(1, min_len // 2)
    for i in range(0, len(shorter) - min_len + 1, step):
        if shorter[i:i + min_len] in longer:
            return True
    return False


def self_test(load_text):
    """Replays the matcher over the full induction set. Asserts every
    accepted extraction (present=True) is reproduced and that at least one
    returned span overlaps the accepted evidence for that contract."""
    for filename, expected_present in SELF_TEST:
        text = load_text(filename)
        try:
            result = match(text)
        except NoMatch:
            if expected_present:
                raise AssertionError(
                    "expected present=True for %s, got NoMatch" % filename
                )
            continue

        assert result["present"] == expected_present, (
            "present mismatch for %s" % filename
        )

        accepted = _ACCEPTED_SPANS.get(filename, [])
        if accepted:
            ok = any(
                _overlaps(got, acc) for got in result["spans"] for acc in accepted
            )
            assert ok, "no overlap with accepted evidence for %s" % filename

    return True
