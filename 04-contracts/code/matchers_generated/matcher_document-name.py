# Matcher: Document Name
# Trust grade: one-sided (present:True with spans, or NoMatch -- never present:False)
# Induction set size: 6 contracts (all accepted as positives, no negatives supplied)
# Date: 2026-07-03
# Brief: overseer_brief_v1
#
# Patterns induced (plain language):
#   Every US SEC-exhibit-style contract in the induction set opens with a recital
#   sentence whose first word (case-insensitive) is "this"/"This"/"THIS", very
#   near the top of the document. Two shapes of that recital were observed:
#     (a) "THIS <TITLE IN ALL CAPS> (the/this "Agreement") is/shall be/was ..."
#         -- the title is captured directly out of the recital itself. This
#         covers plain titles (ENDORSEMENT AGREEMENT), inline cover-page titles
#         squashed onto one line with "Exhibit N.N EXECUTION COPY <TITLE> THIS
#         <TITLE> (this "Agreement") is made ..." (MEDIA LICENSE AGREEMENT), and
#         documents that print a short cover title once and then a fuller title
#         right before the recital (DISTRIBUTOR AGREEMENT, then EXCLUSIVE
#         DISTRIBUTOR AGREEMENT immediately before "THIS EXCLUSIVE DISTRIBUTOR
#         AGREEMENT (the "Agreement")..." -- the recital-adjacent one wins).
#     (b) "THIS AGREEMENT is entered into ..." / "This agreement is made and
#         entered into ..." / "This Exhibit B is entered into ..." -- the
#         recital does not restate a distinctive title at all. Here the title
#         is instead the nearest heading-like text immediately BEFORE the
#         recital, once a leading numeric "Exhibit <n>" cover slug (and an
#         "EXECUTION COPY" stamp) are stripped -- but only when something
#         non-boilerplate remains after stripping. When nothing remains (an
#         exhibit whose only "name" is its own letter, e.g. EXHIBIT 'B', which
#         happens when the filed document is itself an exhibit/schedule to a
#         master agreement rather than a freestanding contract) the stripped
#         slug itself, "EXHIBIT 'B'", *is* the document name. When more than
#         one heading-like line remains (e.g. a company name banner sitting
#         above the real title, as in NETWORK 1 FINANCIAL CORPORATION /
#         AFFILIATE OFFICE AGREEMENT), the LAST line before the recital wins.
#
#   Known limits (published honestly):
#     - Assumes the classic SEC-exhibit recital opening ("This/THIS ... is/was/
#       shall be made/dated/effective/entered into ...") appears within roughly
#       the first 3000 characters. Contracts with no such recital at all (short
#       letter agreements, amendments that only ever say "this Amendment",
#       titles that live solely in a running header/footer rather than inline
#       before the recital) will raise NoMatch rather than guess.
#     - Rule (a)'s title capture is deliberately restricted to an unbroken
#       run of upper-case words: this is what stops it from wandering past the
#       true title into a *different* defined "Agreement" mentioned later in
#       the same sentence (seen in the Kubient exhibit, where "(the
#       "Agreement")" actually defines the *master* services agreement, not
#       the exhibit itself) -- but it also means a title that is not fully
#       capitalised in its recital restatement will fall through to rule (b).
#     - Rule (b)'s heading-lookback only recognises blank-line/newline
#       separated segments and only strips "Exhibit <token>" / "EXECUTION
#       COPY" boilerplate; a title page laid out with unusual spacing,
#       multiple stacked boilerplate stamps, or separated from the recital by
#       intervening running text (rather than pure boilerplate lines) could
#       make it pick the wrong line or nothing at all.
#     - No semantic judgement of what "looks like" a contract title is
#       attempted beyond these mechanical rules; a document whose real title
#       cannot be isolated this way is left to the model, not guessed at.

import re

CATEGORY = "Document Name"
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
    "commission": "c01-document-name",
}


class NoMatch(Exception):
    """Raised when the matcher cannot answer. NEVER guess instead."""


# --- Rule (a): title restated inline in the opening recital ----------------
# "this" (any case) + whitespace + an all-caps title + "(the/this "Agreement")"
# The capture class is upper-case only on purpose: it must not be able to
# cross into ordinary lower-case prose later in the same sentence (see the
# Kubient trap in the module docstring above).
_RECITAL_TITLE_RE = re.compile(
    r'\s+([A-Z][A-Z0-9 &\'\-/.]*?)\s*'
    r'\(\s*(?:the|this|The|This|THE|THIS)\s+'
    r'["“‘]\s*[Aa]greement\s*["”’]\s*\)'
)

# Boilerplate lines/segments to discard while scanning backward from the
# recital for a heading (rule b).
_BOILERPLATE_SEGMENT_RE = re.compile(
    r'^(?:exhibit\s+\S+|source\s*:.*|\d+|execution\s+copy)$',
    re.IGNORECASE,
)

_LEADING_EXHIBIT_RE = re.compile(
    r'^exhibit\s+(\S+)\s*(.*)$',
    re.IGNORECASE | re.DOTALL,
)

_LEADING_EXECUTION_COPY_RE = re.compile(
    r'^\s*execution\s+copy\s*',
    re.IGNORECASE,
)

# The recital must appear near the top of the document; beyond this we no
# longer trust "this" to be the opening recital rather than some unrelated
# later sentence.
_MAX_RECITAL_OFFSET = 3000

# A cap on how long a "title" we are willing to accept can be -- guards
# against a rule accidentally swallowing a huge span of running text.
_MAX_TITLE_LEN = 120


def _normalise(s: str) -> str:
    return re.sub(r'\s+', ' ', s).strip()


def _is_boilerplate(segment: str) -> bool:
    if not segment:
        return True
    return bool(_BOILERPLATE_SEGMENT_RE.match(segment))


def _heading_lookback(context: str):
    """Given the raw text before the recital anchor, find the nearest
    non-boilerplate heading-like segment. Returns a verbatim substring of
    `context` (hence of the original text), or None."""
    ctx = context.strip()
    if not ctx:
        return None

    m = _LEADING_EXHIBIT_RE.match(ctx)
    if m and m.group(2).strip():
        remainder = _LEADING_EXECUTION_COPY_RE.sub('', m.group(2))
        ctx2 = remainder
    else:
        ctx2 = ctx

    segments = [seg.strip() for seg in re.split(r'\n+', ctx2)]
    segments = [seg for seg in segments if seg and not _is_boilerplate(seg)]

    if segments:
        return segments[-1]

    # Nothing survived the boilerplate filter -- fall back to whatever raw
    # context we have (covers e.g. "EXHIBIT 'B'" which *is* the name because
    # this filed document is itself an exhibit with no fuller title of its
    # own -- see module docstring).
    ctx2_stripped = ctx2.strip()
    if ctx2_stripped:
        return ctx2_stripped
    return ctx if ctx else None


def match(text: str) -> dict:
    """Answer the "Document Name" question from raw contract text.
    Returns {"present": bool, "spans": [str, ...], "answer": str | None}.
    Raises NoMatch when the text doesn't fit the patterns this matcher
    trusts."""
    if not isinstance(text, str) or not text:
        raise NoMatch("empty or non-string input")

    anchor = re.search(r'\bthis\b', text, re.IGNORECASE)
    if not anchor:
        raise NoMatch("no opening recital ('this'/'This'/'THIS') found")

    this_pos = anchor.start()
    if this_pos > _MAX_RECITAL_OFFSET:
        raise NoMatch("first 'this' too far into the document to trust as the opening recital")

    # "this"/"This"/"THIS" is always exactly 4 characters.
    after = text[this_pos + 4: this_pos + 4 + 400]

    span_text = None

    m = _RECITAL_TITLE_RE.match(after)
    if m:
        raw_title = m.group(1)
        normalised = _normalise(raw_title)
        if normalised and normalised.upper() != "AGREEMENT":
            start = this_pos + 4 + m.start(1)
            end = this_pos + 4 + m.end(1)
            span_text = text[start:end]

    if span_text is None:
        # Rule (a) didn't fire (or produced a degenerate bare "AGREEMENT") --
        # fall back to the heading immediately preceding the recital.
        context = text[:this_pos]
        candidate = _heading_lookback(context)
        if candidate:
            span_text = candidate

    if span_text is None:
        raise NoMatch("no title captured by either the recital-inline rule or the heading lookback")

    answer = _normalise(span_text)
    if not answer or len(answer) > _MAX_TITLE_LEN or not re.search(r'[A-Za-z]', answer):
        raise NoMatch("captured title failed sanity checks (empty, too long, or no letters)")

    return {
        "present": True,
        "spans": [span_text],
        "answer": answer,
    }


# --- Mandatory self-test -----------------------------------------------------

SELF_TEST = [
    ("EcoScienceSolutionsInc_20171117_8-K_EX-10.1_10956472_EX-10.1_Endorsement Agreement.txt",
     {"present": True, "answer": "ENDORSEMENT AGREEMENT"}),
    ("GpaqAcquisitionHoldingsInc_20200123_S-4A_EX-10.6_11951677_EX-10.6_License Agreement.txt",
     {"present": True, "answer": "MEDIA LICENSE AGREEMENT"}),
    ("KUBIENT,INC_07_02_2020-EX-10.14-MASTER SERVICES AGREEMENT_Part2.txt",
     {"present": True, "answer": "EXHIBIT 'B'"}),
    ("LEGACYTECHNOLOGYHOLDINGS,INC_12_09_2005-EX-10.2-DISTRIBUTOR AGREEMENT.txt",
     {"present": True, "answer": "EXCLUSIVE DISTRIBUTOR AGREEMENT"}),
    ("SIBANNAC,INC_12_04_2017-EX-2.1-Strategic Alliance Agreement.txt",
     {"present": True, "answer": "Strategic Alliance Agreement"}),
    ("UsioInc_20040428_SB-2_EX-10.11_1723988_EX-10.11_Affiliate Agreement 2.txt",
     {"present": True, "answer": "AFFILIATE OFFICE AGREEMENT"}),
]


def self_test(load_text):
    """Replay this matcher over the full induction set and assert it
    reproduces every accepted extraction (answer/presence level; spans may
    differ in extent from the accepted evidence but must overlap it)."""
    for fname, expected in SELF_TEST:
        text = load_text(fname)
        try:
            result = match(text)
        except NoMatch as exc:
            raise AssertionError(f"{fname}: expected a match but got NoMatch({exc!r})")

        assert result["present"] == expected["present"], (
            f"{fname}: present mismatch: got {result['present']!r}, expected {expected['present']!r}"
        )

        got_answer = (result["answer"] or "").strip().lower()
        exp_answer = expected["answer"].strip().lower()
        assert got_answer == exp_answer, (
            f"{fname}: answer mismatch: got {result['answer']!r}, expected {expected['answer']!r}"
        )

        exp_norm = exp_answer
        overlap = any(
            exp_norm in re.sub(r'\s+', ' ', s).strip().lower()
            or re.sub(r'\s+', ' ', s).strip().lower() in exp_norm
            for s in result["spans"]
        )
        assert overlap, (
            f"{fname}: no span overlaps the accepted answer: spans={result['spans']!r}"
        )

    return True
