# Category: Cap on Liability (CUAD-operational definition — wider than the naive
#   "there is a liability cap" reading). Covers: (a) maximum recovery amounts,
#   (b) time limitations for bringing claims, (c) waivers/exclusions of whole
#   damage types (e.g. mutual waiver of indirect/consequential/exemplary damages).
# Trust: one-sided — a confident hit is returned as present:True with verbatim
#   spans; every other input raises NoMatch. Absence is never asserted.
# Induction set: 6 contracts, 6 accepted positives, 0 accepted negatives.
# Date: 2026-07-03. Brief: overseer_brief_v1. Commission: c08-cap-on-liability.
#
# Patterns induced (in expected order of real-world coverage):
#   (1) the classic damage-type waiver boilerplate — "IN NO EVENT SHALL/WILL
#       <party> BE LIABLE ... FOR ANY SPECIAL/INCIDENTAL/INDIRECT/CONSEQUENTIAL/
#       EXEMPLARY/PUNITIVE DAMAGES", and its lower-case cousins ("<party> will
#       not be liable ... for any ... consequential damages", "Neither <A> nor
#       <B> shall be liable for any consequential loss ..."). This is standard
#       limitation-of-liability boilerplate and is expected to be by far the
#       highest-recall, highest-precision pattern of the four.
#   (2) an explicit monetary/fee cap — "<party>'s liability ... shall/will be
#       limited to <amount>" or "... is limited to, and will not exceed,
#       <amount>". Also common boilerplate; second highest expected coverage.
#   (3) a liquidated-damages formula stated as the exclusive recovery —
#       "<amount> will be the full, agreed and liquidated damages ...".
#       Induced from a single financing-agreement example; narrow, and likely
#       to miss liquidated-damages clauses phrased any other way (e.g. without
#       the word "full" signalling exclusivity).
#   (4) a conditional non-liability tied to a triggering event — "<party>
#       shall have no liability ... unless and until <condition>". Induced
#       from a single affiliate-agreement payment clause; the narrowest and
#       most idiosyncratic pattern here — it is really a condition-precedent-
#       to-payment clause that this induction set's accepted extractions treat
#       as a liability cap, and it risks both under- and over-firing on
#       similarly worded conditional-liability language that is not really
#       about capping damages.
#
# Known limits (write it down honestly): contract phrasing for this category
# is extremely heterogeneous. This matcher does NOT attempt: standalone time
# limitations for bringing claims (sub-type (b)) — no induction example
# exhibited this sub-type, so no pattern was induced and any such clause will
# raise NoMatch; one-party-only caps phrased without "liable", "limited to" or
# "liquidated damages" (e.g. bare "X's maximum aggregate liability shall not
# exceed ..." without the word "liable" nearby); caps expressed only as a
# defined term ("the Liability Cap") that points elsewhere in the document;
# insurance-style caps; and any synonym this matcher does not recognise
# ("aggregate liability", "total liability", "under no circumstances", "in no
# circumstances"). Best guess: patterns (1)-(2) catch a fair slice of standard
# commercial boilerplate; patterns (3)-(4) are single-contract inductions with
# no claim to generalise. Overall this matcher should be expected to miss a
# sizeable share — plausibly a majority — of real cap-on-liability clauses in
# the wild; it is deliberately narrow so that what it does return is trustworthy.

import re

CATEGORY = "Cap on Liability"
TRUST = "one-sided"
PROVENANCE = {
    "induced_from": [
        "CENTRACKINTERNATIONALINC_10_29_1999-EX-10.3-WEB SITE HOSTING AGREEMENT.txt",
        "CORALGOLDRESOURCES,LTD_05_28_2020-EX-4.1-CONSULTING AGREEMENT.txt",
        "DeltathreeInc_19991102_S-1A_EX-10.19_6227850_EX-10.19_Co-Branding Agreement_ Service Agreement.txt",
        "EdietsComInc_20001030_10QSB_EX-10.4_2606646_EX-10.4_Co-Branding Agreement.txt",
        "SUNTRONCORP_05_17_2006-EX-10.22-MAINTENANCE AGREEMENT.txt",
        "UsioInc_20040428_SB-2_EX-10.11_1723988_EX-10.11_Affiliate Agreement 2.txt",
    ],
    "brief": "overseer_brief_v1",
    "commission": "c08-cap-on-liability",
}


class NoMatch(Exception):
    """Raised when the matcher cannot answer. NEVER guess instead."""


# --- shared, period-safe filler fragments -----------------------------------
# ".{0,N}" bounded filler that will happily cross periods embedded in numbers
# or section refs ("3.01", "$5,000,000.00") but stops before a *true*
# sentence-ending period (one followed by whitespace or end of string), so an
# anchor phrase can never silently bridge into an unrelated later sentence.
_GAP = r"(?:(?!\.(?:\s|$))[\s\S]){0,300}?"
_TAIL = r"(?:(?!\.(?:\s|$))[\s\S]){0,260}\.?"

_DAMAGE_TYPES = r"(?:special|incidental|indirect|consequential|exemplary|punitive)\s+(?:damages?|loss(?:es)?)"

# (1) "IN NO EVENT SHALL/WILL ... BE LIABLE ... FOR ANY <TYPE> DAMAGES", and the
#     lower-case "will not be liable" / "neither ... shall be liable" cousins.
WAIVER_RE = re.compile(
    r"(?:"
    r"in\s+no\s+event\s+(?:shall|will)\s+" + _GAP + r"be\s+liable"
    r"|(?:shall|will)\s+not\s+be\s+liable"
    r"|neither\s+" + _GAP + r"shall\s+be\s+liable"
    r")" + _GAP + _DAMAGE_TYPES + _TAIL,
    re.IGNORECASE,
)

# (2) an explicit monetary/fee cap: "<party>'s liability ... shall be limited
#     to <amount>" / "... is limited to, and will not exceed, <amount>".
CAP_AMOUNT_RE = re.compile(
    r"liabilit(?:y|ies)\b" + _GAP +
    r"(?:is|are|shall\s+be|will\s+be|shall\s+not\s+exceed|will\s+not\s+exceed)\s+"
    r"(?:limited\s+to|capped\s+at)\b" + _TAIL,
    re.IGNORECASE,
)

# (3) a liquidated-damages formula stated as the exclusive/full recovery.
LIQUIDATED_RE = re.compile(
    r"(?:shall|will)\s+be\s+the\s+(?:full,?\s+)?(?:sole\s+and\s+exclusive\s+)?"
    r"(?:agreed(?:\s+and)?\s+)?liquidated\s+damages\b" + _TAIL,
    re.IGNORECASE,
)

# (4) a conditional non-liability tied to a triggering event.
NO_LIAB_UNTIL_RE = re.compile(
    r"shall\s+have\s+no\s+liability\b" + _GAP + r"unless\s+and\s+until\b" + _TAIL,
    re.IGNORECASE,
)

_PATTERNS = (WAIVER_RE, CAP_AMOUNT_RE, LIQUIDATED_RE, NO_LIAB_UNTIL_RE)


def _merge_span(spans: list, candidate: str) -> None:
    """Add candidate unless it is already covered by (or covers) an existing span."""
    candidate = candidate.strip()
    if not candidate:
        return
    for i, existing in enumerate(spans):
        if candidate in existing:
            return
        if existing in candidate:
            spans[i] = candidate
            return
    spans.append(candidate)


def match(text: str) -> dict:
    """Answer the category question from raw contract text.
    Returns {"present": bool, "spans": [str, ...], "answer": str | None}
    — same shape as the model's answers for this category.
    Raises NoMatch when the text doesn't fit the patterns you trust."""
    if not isinstance(text, str) or not text.strip():
        raise NoMatch("empty or non-string input")

    spans: list = []
    for pattern in _PATTERNS:
        for m in pattern.finditer(text):
            _merge_span(spans, m.group(0))

    if not spans:
        raise NoMatch("no confident cap-on-liability pattern matched")

    for span in spans:
        if span not in text:
            raise NoMatch("internal error: span not verbatim in text")

    return {"present": True, "spans": spans, "answer": None}


# --- mandatory self-test -----------------------------------------------------
# Expected results are the accepted extractions themselves (this commission's
# induction set has no accepted negatives — all six are positives). self_test
# checks presence and that every accepted span overlaps at least one span this
# matcher returns; matched spans need not equal the accepted span verbatim.

SELF_TEST = [
    (
        "CENTRACKINTERNATIONALINC_10_29_1999-EX-10.3-WEB SITE HOSTING AGREEMENT.txt",
        {
            "present": True,
            "spans": [
                "i-on will not be liable under any circumstances for any lost profits or other consequential damages, even if i-on has been advised as to the possibility of such damages.",
                "i-on's liability for damages to the Customer for any cause whatsoever, regardless of the form of action, and whether in contract or in tort, including negligence, shall be limited to one (1) month's fees and the remaining portion of any prepaid fees.",
            ],
        },
    ),
    (
        "CORALGOLDRESOURCES,LTD_05_28_2020-EX-4.1-CONSULTING AGREEMENT.txt",
        {
            "present": True,
            "spans": [
                "Neither the Company nor the Consultant shall be liable for any consequential loss, including but not limited to, claims for loss of profit, revenue or capital, loss of use of utilities, equipment or facilities, down-time cost, service interruption, cost of money, injury or damage of any character whatsoever.",
            ],
        },
    ),
    (
        "DeltathreeInc_19991102_S-1A_EX-10.19_6227850_EX-10.19_Co-Branding Agreement_ Service Agreement.txt",
        {
            "present": True,
            "spans": [
                "IN NO EVENT SHALL PRIMECALL BE LIABLE TO DELTATHREE FOR ANY SPECIAL, INCIDENTIAL OR CONSEQUENTIAL DAMAGES, INCLUDING, WITHOUT LIMITATION, LOSS OF PROFITS, REVENUES OR DATA WHETHER BASED ON BREACH OF CONTRACT, TORT OR OTHERWISE, WHETHER OR NOT DELTATHREE HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH DAMAGE. THE LIABILITY OF PRIMECALL FOR DAMAGES OR ALLEGED DAMAGES HEREUNDER, WHETHER IN CONTRACT, TORT OR ANY OTHER LEGAL THEORY, IS LIMITED TO, AND WILL NOT EXCEED, DELTATHREE'S DIRECT DAMAGES.",
                "IN NO EVENT SHALL DELTATHREE BE LIABLE TO PRIMECALL FOR ANY SPECIAL, INCIDENTIAL OR CONSEQUENTIAL DAMAGES, INCLUDING, WITHOUT LIMITATION, LOSS OF PROFITS, REVENUES OR DATA WHETHER BASED ON BREACH OF CONTRACT, TORT OR OTHERWISE, WHETHER OR NOT PRIMECALL HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH DAMAGE. THE LIABILITY OF DELTATHREE FOR DAMAGES OR ALLEGED DAMAGES HEREUNDER, WHETHER IN CONTRACT, TORT OR ANY OTHER LEGAL THEORY, IS LIMITED TO, AND WILL NOT EXCEED, PRIMECALL'S DIRECT DAMAGES.",
            ],
        },
    ),
    (
        "EdietsComInc_20001030_10QSB_EX-10.4_2606646_EX-10.4_Co-Branding Agreement.txt",
        {
            "present": True,
            "spans": [
                "EXCEPT FOR BREACHES OF SECTION 11 OR BREACHES OF ANY LICENSE GRANT SET FORTH IN THIS AGREEMENT, IN NO EVENT WILL EITHER PARTY BE LIABLE TO THE OTHER FOR ANY SPECIAL, INCIDENTAL, INDIRECT OR CONSEQUENTIAL DAMAGES, WHETHER BASED ON BREACH OF CONTRACT, TORT (INCLUDING NEGLIGENCE) OR OTHERWISE, WHETHER OR NOT THAT PARTY HAS BEEN ADVISED OF, KNEW, OR SHOULD HAVE KNOWN OF, THE POSSIBILITY OF SUCH DAMAGE AND NOTWITHSTANDING THE FAILURE OF ESSENTIAL PURPOSE OF ANY LIMITED REMEDY.",
            ],
        },
    ),
    (
        "SUNTRONCORP_05_17_2006-EX-10.22-MAINTENANCE AGREEMENT.txt",
        {
            "present": True,
            "spans": [
                "The Investor, the Agent and the Lenders hereby acknowledge and agree that (a) an amount equal to the lesser of (i) the full amount of each Required Capital Contribution that has not been made by the Investor and (ii) the then-outstanding balance of the Obligations, represents a reasonable estimate of the damages which the Agent and the Lenders will sustain upon the occurrence of an Maintenance Event of Default hereunder, and (b) such lesser amount will be the full, agreed and liquidated damages resulting from the occurrence of any Maintenance Event of Default hereunder.",
            ],
        },
    ),
    (
        "UsioInc_20040428_SB-2_EX-10.11_1723988_EX-10.11_Affiliate Agreement 2.txt",
        {
            "present": True,
            "spans": [
                "Network 1 shall have no  liability  with  respect  to  the  payment  of such Affiliate's Fee (for any specific  Merchant)  under  Section 3.01  [AMOUNT] unless and until Network 1 receives the above  referenced  payment for Merchant.",
            ],
        },
    ),
]


def self_test(load_text) -> bool:
    """Replay the matcher over the induction set via an injected loader
    (filename -> text). Asserts presence matches and every accepted span
    overlaps at least one span the matcher returns."""
    for filename, expected in SELF_TEST:
        text = load_text(filename)
        try:
            result = match(text)
        except NoMatch:
            assert expected["present"] is False, f"{filename}: unexpected NoMatch"
            continue
        assert result["present"] == expected["present"], f"{filename}: present mismatch"
        for exp_span in expected["spans"]:
            assert any(
                exp_span in got or got in exp_span for got in result["spans"]
            ), f"{filename}: no matcher span overlaps expected span {exp_span!r}"
    return True
