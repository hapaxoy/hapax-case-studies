"""Extraction schema for the contract-review pipeline (Project 4).

Design-critical: binds the answer key, the model
path, and the generated matchers.

The schema is deliberately small: per category a record carries
    present : bool
    spans   : list[str]   verbatim quotes (evidence; reported, never scored)
    answer  : str | None  normalised answer (extraction categories only)

Comparison rules (the comparators) live here and ONLY here — the evaluator,
the validator, and the regression gate all import them, so "correct" means
one thing everywhere. Dates compare as parsed dates, never as strings
(the key writes m/d/yy, the README promises mm/dd/yyyy — both occur).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

# --------------------------------------------------------------------------
# Categories (canonical names; csv = column name in master_clauses.csv)
# --------------------------------------------------------------------------

CATEGORIES = [
    {"name": "Document Name",           "kind": "extraction", "csv": "Document Name"},
    {"name": "Parties",                 "kind": "extraction", "csv": "Parties"},
    {"name": "Agreement Date",          "kind": "extraction", "csv": "Agreement Date"},
    {"name": "Governing Law",           "kind": "extraction", "csv": "Governing Law"},
    {"name": "Expiration Date",         "kind": "extraction", "csv": "Expiration Date"},
    {"name": "Anti-Assignment",         "kind": "yesno",      "csv": "Anti-Assignment"},
    {"name": "License Grant",           "kind": "yesno",      "csv": "License Grant"},
    {"name": "Cap on Liability",        "kind": "yesno",      "csv": "Cap On Liability"},
    {"name": "Audit Rights",            "kind": "yesno",      "csv": "Audit Rights"},
    {"name": "Insurance",               "kind": "yesno",      "csv": "Insurance"},
    {"name": "IP Ownership Assignment", "kind": "yesno",      "csv": "Ip Ownership Assignment"},
    {"name": "Non-Compete",             "kind": "yesno",      "csv": "Non-Compete"},
]

CATEGORY_NAMES = [c["name"] for c in CATEGORIES]
KIND = {c["name"]: c["kind"] for c in CATEGORIES}
CSV_COLUMN = {c["name"]: c["csv"] for c in CATEGORIES}

OMITTED_MARKER = "<omitted>"

# --------------------------------------------------------------------------
# Text normalisation
# --------------------------------------------------------------------------

def norm_ws(s: str) -> str:
    """Collapse all whitespace runs to single spaces and strip."""
    return re.sub(r"\s+", " ", s).strip()


def norm_text(s: str) -> str:
    """Casefolded, accent-stripped, punctuation-insensitive form for
    comparing short answers (Document Name and similar)."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.casefold()
    s = re.sub(r"[\"'‘’“”]", "", s)
    s = re.sub(r"[^0-9a-z]+", " ", s)
    return norm_ws(s)


# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------

_REDACTION_RE = re.compile(r"(\*{2,}|_{2,}|\[\s*\]|\[\*+\])")
_DATE_RE = re.compile(r"^\s*(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{2,4})\s*$")

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"])}
_TEXT_DATE_RE = re.compile(
    r"^\s*([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s+(\d{4})\s*$")


def is_redacted(s: str) -> bool:
    return bool(_REDACTION_RE.search(s or ""))


def parse_date_answer(s: str | None):
    """Parse an answer string to (kind, value):
        ("date", datetime.date)  a calendar date
        ("perpetual", None)      an explicit perpetual term
        ("redacted", None)       filer-redacted date
        ("text", norm_text(s))   unparseable — falls back to text comparison
        ("empty", None)          None/blank
    Two-digit years pivot at 50 (99 -> 1999, 00 -> 2000, 19 -> 2019):
    CUAD contracts are filed 1990s-2020s.
    """
    if s is None or not str(s).strip():
        return ("empty", None)
    s = str(s).strip()
    if s.casefold() in ("perpetual", "none", "n/a"):
        return ("perpetual", None) if s.casefold() == "perpetual" else ("text", norm_text(s))
    if is_redacted(s):
        return ("redacted", None)
    m = _DATE_RE.match(s)
    if m:
        mm, dd, yy = (int(g) for g in m.groups())
        if len(m.group(3)) == 2:
            yy = 2000 + yy if yy < 50 else 1900 + yy
        try:
            return ("date", date(yy, mm, dd))
        except ValueError:
            return ("text", norm_text(s))
    m = _TEXT_DATE_RE.match(s)
    if m and m.group(1).casefold() in _MONTHS:
        try:
            return ("date", date(int(m.group(3)), _MONTHS[m.group(1).casefold()],
                                 int(m.group(2))))
        except ValueError:
            return ("text", norm_text(s))
    return ("text", norm_text(s))


# --------------------------------------------------------------------------
# Parties
# --------------------------------------------------------------------------

_PAREN_SHORT_RE = re.compile(r"\(\s*[\"'“‘]?(.*?)[\"'”’]?\s*\)")


def parse_parties_answer(s: str | None) -> frozenset:
    """Key/pipeline Parties answers are semicolon-separated entries like
    'Snap Technologies, Inc. ("Snap")'. Compare as a set of normalised
    entity tokens: for each entry, the long name and any parenthesised
    short name each become one token (so ordering, and whether the short
    name rides with the long one or stands alone, cannot cause a mismatch).
    """
    if not s or not str(s).strip():
        return frozenset()
    tokens: set[str] = set()
    for entry in str(s).split(";"):
        entry = entry.strip()
        if not entry:
            continue
        for m in _PAREN_SHORT_RE.finditer(entry):
            short = norm_text(m.group(1))
            if short:
                tokens.add(short)
        long_part = norm_text(_PAREN_SHORT_RE.sub(" ", entry))
        if long_part:
            tokens.add(long_part)
    return frozenset(tokens)


def parties_equal(a: str | None, b: str | None) -> bool:
    """Symmetric containment: every token on each side must be matched on
    the other side either exactly or as a superstring (covers 'Snap' vs
    'Snap Technologies Inc' style long/short splits)."""
    ta, tb = parse_parties_answer(a), parse_parties_answer(b)
    if not ta and not tb:
        return True
    if not ta or not tb:
        return False

    def covered(t: str, other: frozenset) -> bool:
        return any(t == o or t in o or o in t for o in other)

    return all(covered(t, tb) for t in ta) and all(covered(t, ta) for t in tb)


# --------------------------------------------------------------------------
# Governing law
# --------------------------------------------------------------------------

_JURIS_STRIP_RE = re.compile(
    r"^(the\s+)?(state\s+of\s+|commonwealth\s+of\s+|province\s+of\s+|"
    r"country\s+of\s+|republic\s+of\s+)?", re.IGNORECASE)


def norm_jurisdiction(s: str | None) -> frozenset:
    """Normalised set of jurisdictions. CUAD answers can be multi-valued
    ('Virginia, Texas' — observed in the corpus spot-read, 3 Jul 2026), so
    comparison is set-based and order-insensitive. Splits on comma/semicolon/
    ' and '."""
    if not s:
        return frozenset()
    parts = re.split(r"[,;]|\band\b", str(s))
    out = set()
    for p in parts:
        p = norm_text(_JURIS_STRIP_RE.sub("", p.strip()))
        if p:
            out.add(p)
    return frozenset(out)


# --------------------------------------------------------------------------
# Record structure
# --------------------------------------------------------------------------

def validate_record(rec: dict, categories: list[str] | None = None) -> list[str]:
    """Structural validation of one pipeline/key record. Returns error list
    (empty = valid). A record is {contract: str, categories: {name: entry}}.
    `categories` restricts the expected set (narrowed reads carry only the
    asked categories); default is all twelve."""
    expected = CATEGORY_NAMES if categories is None else list(categories)
    errors: list[str] = []
    if not isinstance(rec, dict):
        return ["record is not an object"]
    if "categories" not in rec or not isinstance(rec["categories"], dict):
        return ["missing/invalid 'categories'"]
    cats = rec["categories"]
    for name in expected:
        if name not in cats:
            errors.append(f"missing category: {name}")
            continue
        e = cats[name]
        if not isinstance(e, dict):
            errors.append(f"{name}: entry not an object")
            continue
        if not isinstance(e.get("present"), bool):
            errors.append(f"{name}: 'present' must be bool")
        spans = e.get("spans")
        if not isinstance(spans, list) or not all(isinstance(x, str) for x in spans):
            errors.append(f"{name}: 'spans' must be a list of strings")
        ans = e.get("answer")
        if KIND[name] == "yesno":
            if ans is not None:
                errors.append(f"{name}: yes/no category must have answer null")
        else:
            if ans is not None and not isinstance(ans, str):
                errors.append(f"{name}: answer must be string or null")
            if e.get("present") and ans is None:
                # extraction categories must attempt an answer when present;
                # an explicit redaction marker is an acceptable answer
                errors.append(f"{name}: present but no answer")
        if e.get("present") and not spans:
            errors.append(f"{name}: present but no supporting span")
    unknown = set(cats) - set(expected)
    if unknown:
        errors.append(f"unknown/unasked categories: {sorted(unknown)}")
    return errors


# --------------------------------------------------------------------------
# Comparison (the single definition of "correct")
# --------------------------------------------------------------------------

def compare_category(name: str, got: dict, key: dict) -> dict:
    """Compare one pipeline entry against the key entry.
    Returns {"match": bool, "axis": str, "detail": str}.
    yes/no categories score on presence; extraction categories score on
    presence AND answer equality under the category's comparator."""
    kind = KIND[name]
    if kind == "yesno":
        ok = bool(got.get("present")) == bool(key.get("present"))
        return {"match": ok, "axis": "presence",
                "detail": f"got={got.get('present')} key={key.get('present')}"}

    if bool(got.get("present")) != bool(key.get("present")):
        return {"match": False, "axis": "presence",
                "detail": f"got present={got.get('present')} key={key.get('present')}"}
    if not key.get("present"):
        return {"match": True, "axis": "presence", "detail": "both absent"}

    ga, ka = got.get("answer"), key.get("answer")
    # Pre-registered rule (3 Jul 2026, before any pipeline run): where CUAD
    # records spans but no normalised answer (span-only presence — e.g. 86 of
    # 510 Expiration Dates), the row is scored on presence only and the answer
    # pair is routed to the adjudication lane by construction. Answer accuracy
    # is computed over key-answerable rows; evaluate.py splits on this axis.
    if ka is None or not str(ka).strip():
        return {"match": True, "axis": "presence-only",
                "detail": f"key answer blank (span-only presence); got {ga!r} "
                          f"— answer adjudicated, not scored"}
    if name in ("Agreement Date", "Expiration Date"):
        gk, gv = parse_date_answer(ga)
        kk, kv = parse_date_answer(ka)
        if gk == kk and (gv == kv):
            return {"match": True, "axis": "answer", "detail": f"{gk}"}
        return {"match": False, "axis": "answer",
                "detail": f"got {gk}:{gv} key {kk}:{kv} (raw {ga!r} vs {ka!r})"}
    if name == "Parties":
        ok = parties_equal(ga, ka)
        return {"match": ok, "axis": "answer", "detail": f"{ga!r} vs {ka!r}"}
    if name == "Governing Law":
        ok = norm_jurisdiction(ga) == norm_jurisdiction(ka) != frozenset()
        return {"match": ok, "axis": "answer", "detail": f"{ga!r} vs {ka!r}"}
    # Document Name and any other plain-text answer
    ok = norm_text(ga or "") == norm_text(ka or "") != ""
    return {"match": ok, "axis": "answer", "detail": f"{ga!r} vs {ka!r}"}


def compare_records(got: dict, key: dict) -> dict:
    """Per-category comparison of a full record pair."""
    return {name: compare_category(name,
                                   got["categories"].get(name, {}),
                                   key["categories"].get(name, {}))
            for name in CATEGORY_NAMES}


# --------------------------------------------------------------------------
# Span evidence (descriptive tier — never scored)
# --------------------------------------------------------------------------

def span_segments(span: str) -> list[str]:
    """Split a key span on the <omitted> splice marker; returns non-empty
    normalised segments."""
    return [norm_ws(seg) for seg in span.split(OMITTED_MARKER) if norm_ws(seg)]


def segment_in_text(segment: str, text_norm: str) -> bool:
    """Is the whitespace-normalised segment present verbatim in the
    whitespace-normalised contract text?"""
    return segment in text_norm
