"""
Category: Audit Rights
Trust grade: one-sided (present:True with spans, or NoMatch — never present:False)
Induction set size: 9 accepted positives, 0 accepted negatives
Date: 3 July 2026
Brief: overseer_brief_v1
Commission: c11-audit-rights

Plain-language description of induced patterns and known limits
-----------------------------------------------------------------
All 9 induction contracts grant one party a contractual right to inspect,
audit, or review the counterparty's books, records, files, premises, or
submitted materials in order to verify compliance with the agreement (or
verify payment amounts). Across the 9 examples the invariant is a rights-
granting verb phrase ("shall have the right to", "is entitled to", "may",
"will permit ... to enter") bound tightly (within a short word window) to
an audit/inspect/review/examine verb AND a compliance-relevant object noun
(books and records, premises, files, submitted information/materials,
qualification certificates/business license, or an explicit "Audit Rights"
/ "Records and Audit Rights" section heading). Ten narrow, hand-anchored
patterns were induced, one or two per induction contract, each modelled
directly on the actual clause language found (not on imagined boilerplate).
Two guard rails were added because the induction contracts themselves
contain the category's classic false friends sitting right next to the
true positives: (1) a blacklist window check that suppresses a hit if
"financial statements", "GAAP", "generally accepted accounting
principles", "neutral auditor", "arbitrat*", "beta", "specifications", or
"manifest" appears near the match (this is exactly the trap the overseer
instructions warn about: audited-financial-statement / external-auditor mentions,
and the IGENEBIOTECHNOLOGY contract's own "Neutral Auditor" tax-dispute
clause sitting a few hundred lines from its real audit-rights clause,
confirms the trap is real even within the accepted set); (2) a negation
guard that suppresses a hit if "not/no/never/except/unless" appears in the
~60 characters immediately before the matched verb phrase (so "shall NOT
have the right to audit" or "no right to inspect" cannot be mistaken for a
grant of the right).

Known limits (false negatives expected, by design): this matcher only
fires on the specific verb+object phrasings actually observed in the
induction set (plus the immediately adjacent "right to audit ... books and
records ... confirm/compliance" variant, since "right to" and "entitled
to" are attested as interchangeable across the set). Any audit-rights
clause phrased materially differently — e.g. "Licensor may commission a
review of Licensee's accounts", passive constructions, or audit rights
described only by cross-reference to a separate exhibit — will raise
NoMatch rather than guess. Because this is a one-sided commission, that is
the intended and safe failure mode: a missed positive costs nothing here,
a wrong positive would be repeated silently on every contract that reuses
this matcher. Government/regulatory inspection rights (a state authority
inspecting a party, not one contract party auditing the other) and
product/service acceptance-testing "inspection" clauses are deliberately
not matched — both appear in this very induction set as non-matches
sitting next to the real clauses (IDREAMSKYTECHNOLOGY's "supervision and
inspection of relevant competent authority", and StampscomInc's beta
Manifest inspection/acceptance clause) and were verified NOT to fire.
"""

import re

CATEGORY = "Audit Rights"
TRUST = "one-sided"
PROVENANCE = {
    "induced_from": [
        "CORIOINC_07_20_2000-EX-10.5-LICENSE AND HOSTING AGREEMENT.txt",
        "HUBEIMINKANGPHARMACEUTICALLTD_09_19_2006-EX-10.1-OUTSOURCING AGREEMENT.txt",
        "IDREAMSKYTECHNOLOGYLTD_07_03_2014-EX-10.39-Cooperation Agreement on Mobile Game Business.txt",
        "IGENEBIOTECHNOLOGYINC_05_13_2003-EX-1-JOINT VENTURE AGREEMENT.txt",
        "REGANHOLDINGCORP_03_31_2008-EX-10-LICENSE AND HOSTING AGREEMENT.txt",
        "SENMIAOTECHNOLOGYLTD_02_19_2019-EX-10.5-Collaboration Agreement.txt",
        "StampscomInc_20001114_10-Q_EX-10.47_2631630_EX-10.47_Co-Branding Agreement.txt",
        "UsioInc_20040428_SB-2_EX-10.11_1723988_EX-10.11_Affiliate Agreement 2.txt",
        "WHITESMOKE,INC_11_08_2011-EX-10.26-PROMOTION AND DISTRIBUTION AGREEMENT.txt",
    ],
    "brief": "overseer_brief_v1",
    "commission": "c11-audit-rights",
}


class NoMatch(Exception):
    """Raised when the matcher cannot answer. NEVER guess instead."""


def _ws(phrase):
    """Turn a literal phrase into a regex that tolerates runs of whitespace
    between words (source contract text has irregular multi-space padding
    from line-wrap extraction)."""
    parts = re.split(r"\s+", phrase.strip())
    return r"\s+".join(re.escape(p) for p in parts)


_BLACKLIST_RE = re.compile(
    r"\b(financial\s+statements|generally\s+accepted\s+accounting\s+principles|GAAP|"
    r"neutral\s+auditor|arbitrat\w*|beta\b|specifications\b|manifest\b|warrant\w*)\b",
    re.IGNORECASE,
)

_NEGATION_RE = re.compile(r"\b(not|no|never|except|unless)\b", re.IGNORECASE)

_PATTERNS = (
    # Corio-style royalty/payment audit: books "open for inspection ... for
    # the purpose of verifying [amounts]".
    ("open_for_inspection_verifying", re.compile(
        _ws("open for inspection") + r"[\s\S]{0,250}?" + r"for\s+the\s+purpose\s+of\s+verifying",
        re.IGNORECASE)),
    # Explicit "Audit Rights" / "Records and Audit Rights" section heading
    # followed (within the same clause) by a "may/shall audit" grant tied
    # to compliance confirmation.
    ("heading_audit_rights_may_audit", re.compile(
        _ws("Audit Rights") + r"\.?[\s\S]{0,400}?\b(?:may\s+audit|shall\s+audit|to\s+audit)\b[\s\S]{0,200}?\bcompl(?:y|iance)\b",
        re.IGNORECASE)),
    # "entitled to audit" / "right to audit" ... "confirm/conformance/
    # compliance/verify" nearby.
    ("right_or_entitled_to_audit_confirm", re.compile(
        r"\b(?:entitled\s+to\s+audit|right\s+to\s+audit)\b[\s\S]{0,200}?\b(?:confirm|conformance|compliance|verify)\b",
        re.IGNORECASE)),
    # "permit ... to enter [upon] ... premises ... [for the purpose of]
    # inspecting".
    ("permit_enter_premises_inspect", re.compile(
        _ws("permit") + r"[\s\S]{0,150}?" + _ws("to enter") + r"[\s\S]{0,150}?" + r"premises" + r"[\s\S]{0,150}?" + r"inspect",
        re.IGNORECASE)),
    # "right to inspect [X] ... to insure/ensure compliance".
    ("right_to_inspect_compliance", re.compile(
        _ws("right to inspect") + r"[\s\S]{0,200}?\b(?:compliance|comply|insure\s+compliance)\b",
        re.IGNORECASE)),
    # "right to have [its own internal or external] auditors review the
    # books and records".
    ("right_to_have_auditors_review_books", re.compile(
        r"right\s+to\s+have[\s\S]{0,40}?auditors\s+review\s+the\s+books\s+and\s+records",
        re.IGNORECASE)),
    # "entitled to inspect [any] information/materials/records/documents".
    ("entitled_to_inspect_info", re.compile(
        _ws("entitled to inspect") + r"[\s\S]{0,150}?\b(?:information|materials|records|documents|documentation)\b",
        re.IGNORECASE)),
    # "right to review and retain ... files/records/documentation/data".
    ("right_to_review_and_retain_files", re.compile(
        _ws("right to review and retain") + r"[\s\S]{0,100}?\b(?:files|records|documentation|data)\b",
        re.IGNORECASE)),
    # "right to [know and] review the business license" (qualification/
    # licensing-document review right).
    ("right_review_business_license", re.compile(
        r"right\s+to\s+(?:know\s+and\s+)?review\s+the\s+business\s+license",
        re.IGNORECASE)),
    # "spot checks ... [not in] compliance" — periodic compliance-checking
    # right.
    ("spot_checks_compliance", re.compile(
        _ws("spot checks") + r"[\s\S]{0,200}?\b(?:not\s+in\s+compliance|compliance)\b",
        re.IGNORECASE)),
)


def _blacklisted(text, start, end, window=250):
    lo = max(0, start - window)
    hi = min(len(text), end + window)
    return bool(_BLACKLIST_RE.search(text[lo:hi]))


def _negated(text, start, window=60):
    lo = max(0, start - window)
    return bool(_NEGATION_RE.search(text[lo:start]))


def match(text: str) -> dict:
    """Answer the Audit Rights question from raw contract text.

    Returns {"present": True, "spans": [...], "answer": None} on a
    confident, guarded hit. Raises NoMatch for everything else — per the
    one-sided trust grade for this category, present:False is never
    returned.
    """
    if not text:
        raise NoMatch("empty text")

    spans = []
    seen = set()
    for _name, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            if _blacklisted(text, m.start(), m.end()):
                continue
            if _negated(text, m.start()):
                continue
            span_text = m.group(0)
            if span_text not in seen:
                seen.add(span_text)
                spans.append(span_text)

    if not spans:
        raise NoMatch("no trusted audit-rights pattern matched")

    return {"present": True, "spans": spans, "answer": None}


# ---------------------------------------------------------------------------
# Mandatory self-test
# ---------------------------------------------------------------------------
# Each entry is (induction filename, expected present, evidence snippet).
# The evidence snippet is a whitespace-normalised excerpt drawn from the
# text this matcher itself is expected to capture for that file (verified
# during induction to overlap the accepted extraction's spans). The
# self-test normalises whitespace on both sides before checking overlap,
# because the source contract text has irregular line-wrap spacing that
# is not worth reproducing character-for-character in this table.
SELF_TEST = [
    ("CORIOINC_07_20_2000-EX-10.5-LICENSE AND HOSTING AGREEMENT.txt", True,
     "open for inspection by an independent certified public accountant"),
    ("HUBEIMINKANGPHARMACEUTICALLTD_09_19_2006-EX-10.1-OUTSOURCING AGREEMENT.txt", True,
     "permit any duly authorized representative of DGT"),
    ("IDREAMSKYTECHNOLOGYLTD_07_03_2014-EX-10.39-Cooperation Agreement on Mobile Game Business.txt", True,
     "right to know and review the business license"),
    ("IGENEBIOTECHNOLOGYINC_05_13_2003-EX-1-JOINT VENTURE AGREEMENT.txt", True,
     "right to have its own internal or external auditors review the books and records"),
    ("REGANHOLDINGCORP_03_31_2008-EX-10-LICENSE AND HOSTING AGREEMENT.txt", True,
     "right to review and retain the entirety of, all computer or other files"),
    ("SENMIAOTECHNOLOGYLTD_02_19_2019-EX-10.5-Collaboration Agreement.txt", True,
     "entitled to inspect any information"),
    ("StampscomInc_20001114_10-Q_EX-10.47_2631630_EX-10.47_Co-Branding Agreement.txt", True,
     "entitled to audit all such records"),
    ("UsioInc_20040428_SB-2_EX-10.11_1723988_EX-10.11_Affiliate Agreement 2.txt", True,
     "right to inspect the Local Offices during normal business hours to insure compliance"),
    ("WHITESMOKE,INC_11_08_2011-EX-10.26-PROMOTION AND DISTRIBUTION AGREEMENT.txt", True,
     "Audit Rights. Distributor will keep and maintain complete and accurate books"),
]


def _normalise(s):
    return re.sub(r"\s+", " ", s).strip()


def self_test(load_text):
    """Replay the matcher over the full induction set. `load_text` is a
    caller-supplied function: filename -> contract text. Raises
    AssertionError on any reproduction failure."""
    for filename, expected_present, snippet in SELF_TEST:
        text = load_text(filename)
        try:
            result = match(text)
        except NoMatch:
            assert not expected_present, (
                f"{filename}: expected present={expected_present} but matcher raised NoMatch"
            )
            continue

        assert result["present"] == expected_present, (
            f"{filename}: expected present={expected_present}, got {result['present']}"
        )

        norm_snippet = _normalise(snippet)
        norm_spans = [_normalise(s) for s in result["spans"]]
        overlap = any(norm_snippet in s or s in norm_snippet for s in norm_spans)
        assert overlap, (
            f"{filename}: no returned span overlaps expected evidence snippet {snippet!r}; "
            f"got spans {result['spans']!r}"
        )
    return True
