# Provenance
# ----------
# Category:        License Grant
# Trust grade:      one-sided (present:True on confident hit; NEVER present:False)
# Induction set:    6 accepted positives, 0 accepted negatives
# Date:             3 July 2026
# Brief version:    overseer_brief_v1
#
# Patterns induced (plain language):
#   The six accepted extractions split into two families of surface language.
#
#   (1) Explicit grant-of-licence clauses ("hereby grants ... a ... licence
#       to use/Exploit ...", "grants ... a ... sub-licence of ...", "Agreement
#       grants ... a ... licence to use the mark ..."). Four of the six
#       contracts (Co-Branding/Services, Co-Branding eDiets x2 clauses,
#       Media Licence, Distributor) use this family. The matcher looks for
#       the word "grant(s)" and a "licen[cs]e" word within the same sentence
#       — a sentence boundary is defined as a period followed by whitespace
#       and a capital letter, so abbreviations/domain names inside the
#       clause (e.g. "Women.com", "Section 2.1") don't falsely end it — which
#       is the invariant across every example regardless of exclusivity/
#       royalty/sublicensability qualifiers, which vary freely and are NOT
#       anchored on.
#
#   (2) Right-to-use clauses that grant a licence in substance without ever
#       using the words "grant" or "licence" — personality/endorsement
#       rights ("shall have the right to use the name, image, likeness ...")
#       and brand-name usage rights ("the use of the [name] is on a
#       non-exclusive basis"). Two of the six contracts (Endorsement,
#       Affiliate Office) are this family, each anchored on the specific
#       term-of-art phrase actually observed.
#
#   A same-sentence negation guard (a "not"/"no"/"never"/"without"/"nor"/
#   "neither" token in the ~40 characters immediately before the "grant"
#   trigger) is applied to every pattern family so that clauses about a
#   party's OBLIGATION NOT to grant a licence (e.g. "Neither party shall
#   grant ... any license", or a right-of-first-refusal carve-out) are not
#   mistaken for the grant itself.
#
# Known limits (published — read before trusting this matcher's silence):
#   - Family (1) only fires when "grant(s)" and a licence word co-occur in
#     one sentence. A licence created by other verbs ("is licensed to",
#     "may exploit", "is authorised to use") without "grant" anywhere near
#     it will be missed (NoMatch, safe by construction for one-sided trust,
#     but under-recall).
#   - Family (2) is anchored on two specific templates ("name, image,
#     likeness" and "use of the <mark> is on a non-exclusive basis"). Any
#     other wording for an implicit (word-free-of-"licence") usage grant —
#     e.g. "may display the Company's logo", "is permitted to reference the
#     Trademark" — is NOT covered and will raise NoMatch.
#   - The negation guard is a blunt ~40-character lookback for a short list
#     of tokens. It will not catch multi-clause or distant negations
#     ("...notwithstanding anything herein, no licence is hereby granted
#     under Section 12 above..." with a long lead-in) and will not
#     misfire on legitimate uses of "non-exclusive" (which starts with
#     "non", not the standalone word "no").
#   - This matcher counts ALL licence types (technology, trademark,
#     content, brand/personality features) per the category definition; it
#     does not attempt to distinguish licence subject-matter.
#   - Never returns present:False — an unhandled phrasing raises NoMatch
#     rather than asserting the category is absent, per one-sided trust.

import re
from typing import Any, Dict, List, Tuple

CATEGORY = "License Grant"
TRUST = "one-sided"
PROVENANCE = {
    "induced_from": [
        "DeltathreeInc_19991102_S-1A_EX-10.19_6227850_EX-10.19_Co-Branding Agreement_ Service Agreement.txt",
        "EcoScienceSolutionsInc_20171117_8-K_EX-10.1_10956472_EX-10.1_Endorsement Agreement.txt",
        "EdietsComInc_20001030_10QSB_EX-10.4_2606646_EX-10.4_Co-Branding Agreement.txt",
        "GpaqAcquisitionHoldingsInc_20200123_S-4A_EX-10.6_11951677_EX-10.6_License Agreement.txt",
        "LEGACYTECHNOLOGYHOLDINGS,INC_12_09_2005-EX-10.2-DISTRIBUTOR AGREEMENT.txt",
        "UsioInc_20040428_SB-2_EX-10.11_1723988_EX-10.11_Affiliate Agreement 2.txt",
    ],
    "brief": "overseer_brief_v1",
    "commission": "c07-license-grant",
}


class NoMatch(Exception):
    """Raised when the matcher cannot answer. NEVER guess instead."""


# --- Family (1): explicit "grant(s) ... licen[cs]e" clauses -----------------
# Bounded so the match cannot cross a sentence boundary; the window is
# generous (long qualifier lists are common in these clauses). A naive
# "no literal period" class breaks on abbreviations/domain names inside the
# clause itself (e.g. "Women.com"), so a sentence boundary is instead defined
# as "a period followed by whitespace and a capital letter" (a period
# followed directly by a digit, lower-case letter, or no whitespace, as in
# "Women.com" or "2.1", is not treated as ending the sentence).
#
# The trigger word "grant(s)" is matched case-sensitively as [Gg]rant(s),
# deliberately excluding the all-caps form GRANT(S). Section headings such
# as "GRANT OF RIGHTS" are frequently run on directly into the operative
# clause with no punctuation at all between heading and text, so an
# all-caps "GRANT" would otherwise anchor the match at the heading instead
# of at the real "PFHOF hereby grants ..." sentence and pull in the
# (harmless but wrong) heading text as part of the span. The licence word
# on the far side stays case-insensitive via a scoped inline flag, since
# "License"/"LICENSE" appearing later in the same clause is not a heading
# problem in any induction example.
_SENT_GAP = r"(?:(?!\.\s+[A-Z])[\s\S])"
_GRANT_LICENSE_RE = re.compile(
    r"\b[Gg]rants?\b" + _SENT_GAP + r"{0,500}?(?i:\blicen[cs]es?\b)"
)

# --- Family (2a): personality / endorsement "name, image, likeness" grant --
_NAME_IMAGE_LIKENESS_RE = re.compile(
    r"right\s+to\s+use\s+the\s+name,?\s*image,?\s*(?:and\s+)?likeness", re.IGNORECASE
)

# --- Family (2b): brand-name usage right phrased as a non-exclusive basis --
_NAME_NONEXCLUSIVE_RE = re.compile(
    r"use\s+of\s+the\s+" + _SENT_GAP + r"{0,60}?name\s+is\s+on\s+a\s+non-exclusive\s+basis",
    re.IGNORECASE,
)

_NEGATION_RE = re.compile(r"\b(not|no|never|without|nor|neither)\b", re.IGNORECASE)

_LOOKBACK = 40


def _is_negated(text: str, match_start: int) -> bool:
    window_start = max(0, match_start - _LOOKBACK)
    return bool(_NEGATION_RE.search(text[window_start:match_start]))


def _collect(pattern: "re.Pattern[str]", text: str, apply_negation_guard: bool) -> List[str]:
    spans: List[str] = []
    for m in pattern.finditer(text):
        if apply_negation_guard and _is_negated(text, m.start()):
            continue
        span = m.group(0)
        if span not in spans:
            spans.append(span)
    return spans


def match(text: str) -> dict:
    """Answer the category question from raw contract text.
    Returns {"present": bool, "spans": [str, ...], "answer": str | None}
    — same shape as the model's answers for this category.
    Raises NoMatch when the text doesn't fit the patterns you trust."""
    spans: List[str] = []
    spans.extend(_collect(_GRANT_LICENSE_RE, text, apply_negation_guard=True))
    spans.extend(_collect(_NAME_IMAGE_LIKENESS_RE, text, apply_negation_guard=True))
    spans.extend(_collect(_NAME_NONEXCLUSIVE_RE, text, apply_negation_guard=True))

    if not spans:
        raise NoMatch("No confident license-grant pattern found in text.")

    return {"present": True, "spans": spans, "answer": None}


# --- Mandatory self-test -----------------------------------------------------
# (induction filename, expected result) pairs. Expected result mirrors the
# shape of the accepted extraction (present + spans used only for overlap
# checking, not exact-match — the matcher's spans may be tighter fragments
# of the accepted sentence).
SELF_TEST: List[Tuple[str, Dict[str, Any]]] = [
    (
        "DeltathreeInc_19991102_S-1A_EX-10.19_6227850_EX-10.19_Co-Branding Agreement_ Service Agreement.txt",
        {
            "present": True,
            "spans": [
                "Throughout the Term of this Agreement, the parties hereby agree to grant to each other a limited license to use each other's proprietary marks solely in connection with the sale, distribution, marketing and promotion of each party's calling cards by the other party."
            ],
        },
    ),
    (
        "EcoScienceSolutionsInc_20171117_8-K_EX-10.1_10956472_EX-10.1_Endorsement Agreement.txt",
        {
            "present": True,
            "spans": [
                "During the Term and subject to the limitations set forth in Paragraphs 9 and 10, ESSI shall have the right to use the name, image, likeness, characterization, visual and audio representation of Talent (\"Talent Attributes\") in connection with the ESSI product suite, in the venue(s) as follows:"
            ],
        },
    ),
    (
        "EdietsComInc_20001030_10QSB_EX-10.4_2606646_EX-10.4_Co-Branding Agreement.txt",
        {
            "present": True,
            "spans": [
                "2.1 Content License. eDiets hereby grants to Women.com, subject to the terms and conditions of this Agreement, a non-exclusive, nontransferable, worldwide, royalty-free license to use, copy, reproduce and display the editorial content and other data, branding and other identification provided by eDiets to Women.com in connection with this Agreement (the \"eDiets Content\") on the Women.com Sites: (i) for publication in the Diet Center and elsewhere throughout the Women.com Sites; (ii) for the promotion of eDiets and the Diet Center on the Women.com Sites and in collateral advertising materials; and (iii) for such other purposes as are consistent with or otherwise authorized under this Agreement.",
                "9.1 Women.com Marks. Women.com hereby grants eDiets a non-exclusive, non-transferable, royalty-free worldwide right and license without the right to sublicense to use the Women.com Marks during the Term solely in connection with (i) the fulfillment of eDiets' obligations under this Agreement, and (ii) in advertising and marketing collateral related to this Agreement.",
                "9.2 eDiets Marks. eDiets hereby grants Women.com a non-exclusive, non-transferable, royalty-free worldwide right and license without the right to sublicense to use the eDiets Marks during the Term solely in connection with (i) the fulfillment of Women.com's obligations under this Agreement, and (ii) in advertising and marketing collateral related to this Agreement.",
            ],
        },
    ),
    (
        "GpaqAcquisitionHoldingsInc_20200123_S-4A_EX-10.6_11951677_EX-10.6_License Agreement.txt",
        {
            "present": True,
            "spans": [
                "Subject to the terms of this Agreement (including, without limitation, Sections 2.3, 2.4, 2.6 and 5 below), PFHOF hereby grants to the Village Media Company a worldwide, non-exclusive, limited, non-sublicenseable and non-assignable (except to the extent set forth in this Agreement) right and license to (a) Exploit the PFHOF Works and (b) edit, supplement or otherwise adapt, incorporate or otherwise utilize, the PFHOF Works to create, produce and Exploit new, original work(s) (each such work in this clause (b), a \"HOFV Work\")."
            ],
        },
    ),
    (
        "LEGACYTECHNOLOGYHOLDINGS,INC_12_09_2005-EX-10.2-DISTRIBUTOR AGREEMENT.txt",
        {
            "present": True,
            "spans": [
                "SIERRA  hereby  grants  ENVISION an          exclusive,  royalty-free  sub-license of  the Product's future patents,          and patent  applications  to distribute,  sell  and market the Finished          Product.",
                "This          Agreement  grants  ENVISION a  non-exclusive  and  non-royalty  bearing          license to use the mark  \"SierraSil\".",
            ],
        },
    ),
    (
        "UsioInc_20040428_SB-2_EX-10.11_1723988_EX-10.11_Affiliate Agreement 2.txt",
        {
            "present": True,
            "spans": [
                "Affiliate  shall  use  the  Network 1 name in Relationship to all Bankcard marketing activity as required by the rules of VISA USA,  International  and  MasterCard International.",
                "Affiliate acknowledges that the  use of the Network 1 name is on a non-exclusive basis and further agrees to cease using Network 1 name, including but not limited to logo(s) and insignia(s) at  the written request of Network 1.",
            ],
        },
    ),
]


def _char_overlap(text: str, candidate: str, accepted: str) -> bool:
    """True if candidate and accepted occupy overlapping character ranges
    in text (both are verbatim substrings of text, by construction of the
    matcher and of the induction data), or one literally contains the
    other (fallback, in case either string appears more than once and
    `str.find` locates a non-corresponding occurrence)."""
    if candidate in accepted or accepted in candidate:
        return True
    c_start = text.find(candidate)
    a_start = text.find(accepted)
    if c_start == -1 or a_start == -1:
        return False
    c_end = c_start + len(candidate)
    a_end = a_start + len(accepted)
    return c_start < a_end and a_start < c_end


def self_test(load_text) -> None:
    """Replay the matcher over the full induction set and assert it
    reproduces every accepted extraction (one extraction per induction file):
    same present/answer, and at least one returned span overlapping at least
    one accepted span (an accepted extraction may bundle several spans, e.g.
    a mutual-grant clause with one span per direction; the matcher is not
    required to independently rediscover every one of them to have
    reproduced the extraction, only to have found genuine, overlapping
    evidence for it)."""
    for filename, expected in SELF_TEST:
        text = load_text(filename)
        result = match(text)
        assert result["present"] == expected["present"], (
            f"{filename}: expected present={expected['present']}, got {result['present']}"
        )
        found = any(
            _char_overlap(text, got_span, accepted_span)
            for got_span in result["spans"]
            for accepted_span in expected["spans"]
        )
        assert found, (
            f"{filename}: no returned span overlaps any accepted span: {expected['spans']!r}"
        )
    print(f"self_test: all {len(SELF_TEST)} induction examples reproduced OK")
