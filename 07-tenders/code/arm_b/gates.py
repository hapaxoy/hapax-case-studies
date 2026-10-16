"""Arm B deterministic gates (workflow steps 3-4) -- Project 7.

Runs three checks against a run-agent's drafted response, with NO LLM calls
and NO access to `data/answer_key/` or `data/tenders/clause_map_*.json`:

  1. Coverage gate  -- every matrix row is answered, or the run is a clean
     no-bid that names the unanswered rows in its reason.
  2. Facts gate     -- every citation resolves into `company_facts.yaml`,
     and every specific factual claim in an answer is actually supported by
     one of that row's cited facts (not merely "a citation exists").
  3. Consistency gate -- a bid may not go out with an eligibility row the
     draft itself flags as failing, and the same fact may not be quoted at
     two different values across rows.

This module never edits `matrix.json` or `response_v*.json` -- it only
reads them and writes `gate_report_N.json`. The files in `data/arm_b/run_NN/`
show the schemas; a run-agent reads each gate report and revises its draft.

Usage:
    python gates.py <run_dir> [--facts PATH]

`<run_dir>` must contain `matrix.json` and at least one `response_v*.json`.
The highest-numbered `response_v*.json` present is the one evaluated; the
result is written to `gate_report_{N}.json` in the same directory (N = that
response's own version number), overwriting a prior report for the same N
if `gates.py` is re-run against it.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - environment guard
    raise SystemExit(
        "gates.py requires PyYAML ('pip install pyyaml') to read "
        "company_facts.yaml. Install it and re-run."
    ) from exc

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ARM_B_DIR = Path(__file__).resolve().parent
CODE_DIR = ARM_B_DIR.parent
PROJECT_ROOT = CODE_DIR.parent
DEFAULT_FACTS_PATH = PROJECT_ROOT / "data" / "facts" / "company_facts.yaml"

MAX_ITERATIONS = 5  # the run protocol's hard cap; enforced by the run-agent's loop
                     # and re-stated here so gates.py can warn on approach.

# ---------------------------------------------------------------------------
# Fact-path resolution (facts gate)
# ---------------------------------------------------------------------------

# Aliases for top-level keys, so a run-agent following the documented
# illustrative example ("references.REF02.value_eur") still resolves, even
# though company_facts.yaml's real root key is "reference_projects".
TOP_LEVEL_ALIASES = {
    "references": "reference_projects",
    "reference": "reference_projects",
}

# When a path segment addresses a list-of-dicts, try these identifying
# fields, in order, to find the matching item (case-insensitive match on the
# segment string against the field's own string value).
LIST_ITEM_KEY_FIELDS = ("code", "id", "kind", "year")


class FactPathError(ValueError):
    """Raised (and caught) when a fact_path does not resolve."""


def resolve_fact_path(facts: dict, path: str) -> Any:
    """Resolve a dotted fact_path into `company_facts.yaml`'s loaded dict.

    Raises FactPathError with a human-readable reason if the path does not
    resolve to a real value. This is the single source of truth for what
    "resolves to a real path in company_facts.yaml" means for the facts
    gate -- both the citation-validity check and the claim-support check
    reuse it.
    """
    if not path or not isinstance(path, str):
        raise FactPathError(f"empty or non-string fact_path: {path!r}")

    segments = path.split(".")
    node: Any = facts
    walked: list[str] = []

    for i, raw_segment in enumerate(segments):
        segment = raw_segment
        if i == 0 and segment in TOP_LEVEL_ALIASES:
            segment = TOP_LEVEL_ALIASES[segment]

        if isinstance(node, dict):
            # Case-sensitive first, then a forgiving case-insensitive pass
            # (the documented example uses "certifications.lusa"
            # lower-case against a data file that stores "LUSA").
            if segment in node:
                node = node[segment]
            else:
                match = next(
                    (k for k in node if isinstance(k, str) and k.lower() == segment.lower()),
                    None,
                )
                if match is None:
                    raise FactPathError(
                        f"path {'.'.join(walked + [raw_segment])!r}: "
                        f"no key {segment!r} on dict with keys "
                        f"{sorted(str(k) for k in node)}"
                    )
                node = node[match]
        elif isinstance(node, list):
            found = None
            for item in node:
                if not isinstance(item, dict):
                    continue
                for key_field in LIST_ITEM_KEY_FIELDS:
                    if key_field in item and str(item[key_field]).lower() == segment.lower():
                        found = item
                        break
                if found is not None:
                    break
            if found is None:
                raise FactPathError(
                    f"path {'.'.join(walked + [raw_segment])!r}: "
                    f"no list item matching {segment!r} "
                    f"(tried fields {LIST_ITEM_KEY_FIELDS})"
                )
            node = found
        else:
            raise FactPathError(
                f"path {'.'.join(walked)!r} resolved to a scalar "
                f"({node!r}); cannot descend into {segment!r}"
            )
        walked.append(raw_segment)

    return node


def load_facts(facts_path: Path) -> dict:
    if not facts_path.exists():
        raise SystemExit(f"Facts file not found: {facts_path}")
    with facts_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise SystemExit(f"Facts file did not parse to a mapping: {facts_path}")
    return data


# ---------------------------------------------------------------------------
# Numeric / claim parsing helpers
# ---------------------------------------------------------------------------

def normalise_number(raw: str) -> float | None:
    """Parse a number that may carry spaces, EUR/euro markers, commas, or
    periods as thousands separators. Returns None if unparseable.

    Handles: "2 000 000", "2,000,000", "2.000.000", "2000000", "1,650,000.50".
    Heuristic for the comma/period-as-decimal-vs-thousands ambiguity: a
    trailing group of exactly 1-2 digits after the LAST separator is treated
    as a decimal fraction; anything else is treated as thousands grouping.
    """
    text = raw.strip()
    text = re.sub(r"[€]|EUR|eur|euroa|Euroa", "", text).strip()
    text = text.replace("\xa0", " ")
    # Strip everything except digits, spaces, commas, periods, minus.
    text = re.sub(r"[^0-9\-.,\s]", "", text)
    text = text.strip()
    if not text:
        return None

    # Collapse internal spaces used as thousands separators.
    compact = text.replace(" ", "")
    if not compact:
        return None

    # Decide whether the final , or . is a decimal point.
    last_comma = compact.rfind(",")
    last_period = compact.rfind(".")
    decimal_pos = max(last_comma, last_period)
    if decimal_pos != -1:
        fractional_len = len(compact) - decimal_pos - 1
        if 1 <= fractional_len <= 2 and compact[:decimal_pos].replace(",", "").replace(".", "").isdigit():
            integer_part = re.sub(r"[.,]", "", compact[:decimal_pos])
            fractional_part = compact[decimal_pos + 1:]
            compact = f"{integer_part}.{fractional_part}"
        else:
            compact = re.sub(r"[.,]", "", compact)
    try:
        return float(compact)
    except ValueError:
        return None


def numbers_equal(a: float, b: float, rel_tol: float = 1e-6, abs_tol: float = 0.01) -> bool:
    return abs(a - b) <= max(abs_tol, rel_tol * max(abs(a), abs(b)))


# --- Claim extraction -------------------------------------------------------

EUR_CLAIM_RE = re.compile(
    r"(?:€\s?[\d][\d\s.,]*\d|\d[\d\s.,]*\d\s?€|"
    r"EUR\s?[\d][\d\s.,]*\d|\d[\d\s.,]*\d\s?EUR|"
    r"\d[\d\s.,]*\d\s?euro[a]?)",
    re.IGNORECASE,
)

HEADCOUNT_CLAIM_RE = re.compile(
    r"(\d[\d\s,.]*\d|\d+)\s*"
    r"(employees|staff|personnel|workers|professionals|specialists|"
    r"henkil[oö]a|ammattilaista|ty[oö]ntekij[aä][aä]|asiantuntijaa)",
    re.IGNORECASE,
)

YEAR_COUNT_CLAIM_RE = re.compile(
    r"(\d{1,3})\s*"
    r"(years?|vuotta|vuoden|vuosien)\b",
    re.IGNORECASE,
)

# Certification / standard vocabulary: built from company_facts.yaml's own
# certification codes at runtime (see build_certification_vocabulary) plus
# common generic patterns a run-agent might mention even if Visakoivu does
# not hold that exact item (NMSB ####[:####], NOHS ####, LUSA, F-gas /
# F-kaasu, national scheme names). Matching a pattern here is what makes a
# span of text a "certification claim" that then needs citation support.
GENERIC_CERT_PATTERNS = [
    re.compile(r"NMSB\s?\d{4,5}(?::\d{4})?", re.IGNORECASE),
    re.compile(r"NOHS\s?\d{3,5}", re.IGNORECASE),
    re.compile(r"LUSA(?:-p[aä]tevyys)?", re.IGNORECASE),
    re.compile(r"Urakkavarmenne(?:\s+Varmennettu\s+Toimittaja)?", re.IGNORECASE),
    re.compile(r"F-kaas(?:u|assetuksen)\w*", re.IGNORECASE),
    re.compile(r"S[aä]hk[oö]urakointi(?:oikeu\w+)?", re.IGNORECASE),
]


def build_certification_vocabulary(facts: dict) -> list[re.Pattern]:
    """Certification-name patterns drawn from company_facts.yaml itself, so
    the facts gate recognises any cert Visakoivu actually lists (held or
    not) as a checkable claim, plus the generic patterns above."""
    patterns = list(GENERIC_CERT_PATTERNS)
    for cert in facts.get("certifications", []) or []:
        code = str(cert.get("code", "")).strip()
        if code:
            patterns.append(re.compile(re.escape(code), re.IGNORECASE))
    return patterns


def extract_claims(text: str, cert_patterns: list[re.Pattern]) -> list[dict]:
    """Find every specific factual claim in `text`. Each claim is
    {"kind": ..., "raw": matched substring, "value": parsed value or None}.
    """
    claims: list[dict] = []

    for match in EUR_CLAIM_RE.finditer(text):
        raw = match.group(0)
        claims.append({"kind": "eur_amount", "raw": raw, "value": normalise_number(raw)})

    for match in HEADCOUNT_CLAIM_RE.finditer(text):
        raw = match.group(0)
        claims.append({"kind": "headcount", "raw": raw, "value": normalise_number(match.group(1))})

    for match in YEAR_COUNT_CLAIM_RE.finditer(text):
        raw = match.group(0)
        claims.append({"kind": "year_count", "raw": raw, "value": normalise_number(match.group(1))})

    for pattern in cert_patterns:
        for match in pattern.finditer(text):
            claims.append({"kind": "certification", "raw": match.group(0), "value": None})

    return claims


def flatten_fact_value(value: Any) -> str:
    """Turn a resolved fact (scalar, dict, or list) into one search string
    for substring/equality checks against a claim."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def claim_supported_by_fact(claim: dict, fact_value: Any, fact_path: str) -> bool:
    """Does this one resolved fact actually support this one claim?

    Numeric claims (eur_amount, headcount, year_count): the fact must
    contain a number equal to the claim's parsed value (robust parsing on
    both sides), OR the fact's flattened text must contain the claim's raw
    digit sequence as a plain substring (covers cases like a year count
    quoting a founding year that is itself a plain int fact).
    Certification claims: resolved via the dedicated
    certification_claim_supported() below (needs the "held" flag, not just
    substring containment) -- this function is only used for numeric kinds.
    """
    if claim["kind"] == "certification":
        raise AssertionError("certification claims must use certification_claim_supported()")

    claim_value = claim["value"]
    flat = flatten_fact_value(fact_value)

    if claim_value is not None:
        # Scan every number embedded in the fact's own text.
        for number_match in re.findall(r"-?\d[\d\s.,]*\d|-?\d+", flat):
            parsed = normalise_number(number_match)
            if parsed is not None and numbers_equal(parsed, claim_value):
                return True
        # Fall back: does the raw digit string appear verbatim?
        digits_only = re.sub(r"[^\d]", "", claim["raw"])
        if digits_only and digits_only in re.sub(r"[^\d]", "", flat):
            return True
        return False

    # No parseable numeric value -- fall back to plain substring match.
    return claim["raw"].lower() in flat.lower()


def certification_claim_supported(claim_raw: str, facts: dict, fact_path: str) -> tuple[bool, str]:
    """A certification claim is supported by a citation only if that
    citation resolves into a certifications[] entry whose code or Finnish
    name matches the claim AND whose `held` flag is true.

    This is a deliberate strengthening beyond plain substring containment:
    company_facts.yaml lists NMSB73710 with held=false (T11's eligibility
    trap). A run-agent could otherwise "cite" that exact entry while writing
    prose that claims current possession, and a naive substring check would
    wave it through because the certification name IS present in the cited
    fact's text. Returns (supported, reason).
    """
    try:
        resolved = resolve_fact_path(facts, fact_path)
    except FactPathError as exc:
        return False, str(exc)

    candidates: list[dict]
    if isinstance(resolved, dict) and "code" in resolved:
        candidates = [resolved]
    elif isinstance(resolved, list):
        candidates = [item for item in resolved if isinstance(item, dict) and "code" in item]
    else:
        return False, f"fact at {fact_path!r} is not a certification record"

    claim_norm = re.sub(r"[^A-Z0-9]", "", claim_raw.upper())
    for cert in candidates:
        code_norm = re.sub(r"[^A-Z0-9]", "", str(cert.get("code", "")).upper())
        name_norm = re.sub(r"[^A-Z0-9]", "", str(cert.get("name_fi", "")).upper())
        if claim_norm and (claim_norm in code_norm or code_norm in claim_norm or claim_norm in name_norm):
            if cert.get("held") is True:
                return True, "matched and held"
            return False, f"matched certification {cert.get('code')!r} but held=false"
    return False, f"no certification at {fact_path!r} matches {claim_raw!r}"


# ---------------------------------------------------------------------------
# Gate 1 -- Coverage
# ---------------------------------------------------------------------------

def run_coverage_gate(matrix: list[dict], response: dict) -> tuple[bool, list[dict], float]:
    """Every matrix row must have a non-empty answer_text, OR the run is
    no_bid with a reason citing the failing (unanswered) row(s)."""
    bounces: list[dict] = []
    rows_by_id = {row.get("matrix_id"): row for row in response.get("rows", [])}

    unanswered_ids: list[str] = []
    for req in matrix:
        mid = req.get("matrix_id")
        row = rows_by_id.get(mid)
        answer = (row or {}).get("answer_text", "")
        if not isinstance(answer, str) or not answer.strip():
            unanswered_ids.append(mid)

    total = len(matrix)
    answered = total - len(unanswered_ids)
    coverage_pct = round(100.0 * answered / total, 2) if total else 100.0

    if not unanswered_ids:
        return True, bounces, coverage_pct

    no_bid = bool(response.get("no_bid"))
    reason = response.get("no_bid_reason") or ""

    if no_bid and all(mid in reason for mid in unanswered_ids if mid):
        # No-bid, and every unanswered row is explicitly named in the
        # reason -- the coverage gate accepts this as a deliberate stop,
        # not a silently dropped requirement.
        return True, bounces, coverage_pct

    for mid in unanswered_ids:
        bounces.append({
            "gate": "coverage",
            "type": "UNANSWERED_ROW",
            "matrix_id": mid,
            "detail": (
                f"matrix row {mid} has no non-empty answer_text, and the run "
                f"is not a no-bid whose no_bid_reason names it."
                if not no_bid else
                f"matrix row {mid} is unanswered but no_bid_reason does not "
                f"name it (reason: {reason!r})."
            ),
        })
    return False, bounces, coverage_pct


# ---------------------------------------------------------------------------
# Gate 2 -- Facts
# ---------------------------------------------------------------------------

def run_facts_gate(matrix: list[dict], response: dict, facts: dict) -> tuple[bool, list[dict]]:
    bounces: list[dict] = []
    cert_patterns = build_certification_vocabulary(facts)
    valid_matrix_ids = {req.get("matrix_id") for req in matrix}

    for row in response.get("rows", []):
        mid = row.get("matrix_id")
        answer_text = row.get("answer_text", "") or ""
        citations = row.get("citations", []) or []

        if mid not in valid_matrix_ids:
            bounces.append({
                "gate": "facts", "type": "UNKNOWN_MATRIX_ID", "matrix_id": mid,
                "detail": f"response row references matrix_id {mid!r}, not present in matrix.json",
            })
            continue

        # Citation validity: every citation must resolve.
        resolved_citations: list[tuple[str, Any]] = []
        for path in citations:
            try:
                value = resolve_fact_path(facts, path)
                resolved_citations.append((path, value))
            except FactPathError as exc:
                bounces.append({
                    "gate": "facts", "type": "BAD_CITATION", "matrix_id": mid,
                    "detail": f"citation {path!r} does not resolve: {exc}",
                })

        if not answer_text.strip():
            continue  # coverage gate already reports this row

        claims = extract_claims(answer_text, cert_patterns)
        for claim in claims:
            supported = False
            support_reasons: list[str] = []
            if claim["kind"] == "certification":
                for path, _value in resolved_citations:
                    ok, reason = certification_claim_supported(claim["raw"], facts, path)
                    support_reasons.append(f"{path}: {reason}")
                    if ok:
                        supported = True
                        break
            else:
                for path, value in resolved_citations:
                    if claim_supported_by_fact(claim, value, path):
                        supported = True
                        break
                    support_reasons.append(f"{path}: value {value!r} does not support {claim['raw']!r}")

            if not supported:
                bounces.append({
                    "gate": "facts", "type": "FABRICATION", "matrix_id": mid,
                    "detail": (
                        f"claim {claim['raw']!r} ({claim['kind']}) in answer_text is not "
                        f"supported by any cited fact (citations: {citations!r})."
                        + (f" Detail: {'; '.join(support_reasons)}" if support_reasons else "")
                    ),
                })

    passed = not bounces
    return passed, bounces


# ---------------------------------------------------------------------------
# Gate 3 -- Consistency
# ---------------------------------------------------------------------------

# Vocabulary of self-declared-failure phrasing for eligibility rows. This is
# a deliberate, documented heuristic: the
# gates never consult the answer key, so they cannot independently know
# whether Visakoivu truly meets an eligibility clause. What they CAN check
# is internal consistency -- if the draft's own words concede failure on an
# eligibility row, a bid may not go out anyway.
ELIGIBILITY_FAILURE_PHRASES = [
    "does not meet", "does not currently meet", "does not satisfy",
    "does not currently hold", "does not hold", "cannot confirm compliance",
    "cannot demonstrate compliance", "unable to meet", "unable to satisfy",
    "fails to meet", "not compliant", "non-compliant", "not currently held",
    "no current certification", "not held", "falls short of",
    "ei tayta", "ei ole voimassa", "ei tallä hetkellä täytä",
]


def run_consistency_gate(matrix: list[dict], response: dict) -> tuple[bool, list[dict]]:
    bounces: list[dict] = []
    matrix_by_id = {req.get("matrix_id"): req for req in matrix}
    rows_by_id = {row.get("matrix_id"): row for row in response.get("rows", [])}
    no_bid = bool(response.get("no_bid"))

    # (a) no_bid=false requires no eligibility-kind row the draft itself
    # flags as failing.
    if not no_bid:
        for mid, req in matrix_by_id.items():
            if req.get("kind") != "eligibility":
                continue
            row = rows_by_id.get(mid)
            answer_text = ((row or {}).get("answer_text") or "").lower()
            if not answer_text:
                continue
            hit = next((p for p in ELIGIBILITY_FAILURE_PHRASES if p in answer_text), None)
            if hit:
                bounces.append({
                    "gate": "consistency", "type": "ELIGIBILITY_FLAGGED_FAILING", "matrix_id": mid,
                    "detail": (
                        f"row {mid} is an eligibility requirement whose own answer_text "
                        f"concedes failure (matched phrase {hit!r}), but no_bid is false."
                    ),
                })

    # (b) cross-row numeric consistency: the same cited fact_path must not
    # be quoted at two different numeric values across rows.
    claimed_values_by_path: dict[str, list[tuple[str, float, str]]] = {}
    cert_patterns_cache: list[re.Pattern] = []  # unused here; numeric only
    for row in response.get("rows", []):
        mid = row.get("matrix_id")
        answer_text = row.get("answer_text", "") or ""
        citations = row.get("citations", []) or []
        if not answer_text.strip() or not citations:
            continue
        claims = extract_claims(answer_text, [])  # numeric claims only (no cert patterns)
        numeric_claims = [c for c in claims if c["kind"] in ("eur_amount", "headcount", "year_count") and c["value"] is not None]
        for path in citations:
            for claim in numeric_claims:
                claimed_values_by_path.setdefault(path, []).append((mid, claim["value"], claim["raw"]))

    for path, entries in claimed_values_by_path.items():
        distinct_values: list[float] = []
        for _mid, value, _raw in entries:
            if not any(numbers_equal(value, existing) for existing in distinct_values):
                distinct_values.append(value)
        if len(distinct_values) > 1:
            offenders = ", ".join(f"{mid} claims {raw!r}" for mid, _v, raw in entries)
            bounces.append({
                "gate": "consistency", "type": "CROSS_ROW_INCONSISTENCY", "matrix_id": None,
                "detail": (
                    f"fact_path {path!r} is cited with {len(distinct_values)} different "
                    f"numeric values across rows: {offenders}"
                ),
            })

    passed = not bounces
    return passed, bounces


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def find_latest_response(run_dir: Path) -> tuple[Path, int]:
    candidates = sorted(run_dir.glob("response_v*.json"))
    if not candidates:
        raise SystemExit(f"No response_v*.json found in {run_dir}")

    def version_of(p: Path) -> int:
        match = re.match(r"response_v(\d+)\.json$", p.name)
        return int(match.group(1)) if match else -1

    latest = max(candidates, key=version_of)
    version = version_of(latest)
    if version < 1:
        raise SystemExit(f"Could not parse a version number from {latest.name}")
    return latest, version


def load_json(path: Path) -> Any:
    if not path.exists():
        raise SystemExit(f"Required file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} is not valid JSON: {exc}") from exc


def run_gates(run_dir: Path, facts_path: Path) -> dict:
    """Run all three gates against the latest response in run_dir. Returns
    the gate_report dict (does not write it -- see main())."""
    matrix_path = run_dir / "matrix.json"
    matrix = load_json(matrix_path)
    if not isinstance(matrix, list):
        raise SystemExit(f"{matrix_path} must be a JSON array of matrix rows")

    response_path, version = find_latest_response(run_dir)
    response = load_json(response_path)
    if not isinstance(response, dict):
        raise SystemExit(f"{response_path} must be a JSON object")

    facts = load_facts(facts_path)

    print(f"[gates] evaluating {response_path.name} against {matrix_path.name} "
          f"({len(matrix)} requirements) and {facts_path.name}")

    coverage_pass, coverage_bounces, coverage_pct = run_coverage_gate(matrix, response)
    print(f"[gates] coverage gate: {'PASS' if coverage_pass else 'FAIL'} ({coverage_pct}% answered)")

    facts_pass, facts_bounces = run_facts_gate(matrix, response, facts)
    print(f"[gates] facts gate:    {'PASS' if facts_pass else 'FAIL'} ({len(facts_bounces)} bounce(s))")

    consistency_pass, consistency_bounces = run_consistency_gate(matrix, response)
    print(f"[gates] consistency gate: {'PASS' if consistency_pass else 'FAIL'} ({len(consistency_bounces)} bounce(s))")

    all_bounces = coverage_bounces + facts_bounces + consistency_bounces
    overall_pass = coverage_pass and facts_pass and consistency_pass

    if version >= MAX_ITERATIONS and not overall_pass:
        print(f"[gates] WARNING: iteration {version} has reached MAX_ITERATIONS "
              f"({MAX_ITERATIONS}) without a pass. The run protocol says stop here.")

    return {
        "pass": overall_pass,
        "iteration": version,
        "gates": {
            "coverage": coverage_pass,
            "facts": facts_pass,
            "consistency": consistency_pass,
        },
        "coverage_pct": coverage_pct,
        "bounces": all_bounces,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="Directory containing matrix.json and response_v*.json")
    parser.add_argument("--facts", type=Path, default=DEFAULT_FACTS_PATH,
                         help="Path to company_facts.yaml (default: the project's real facts file)")
    args = parser.parse_args()

    run_dir: Path = args.run_dir
    if not run_dir.is_dir():
        raise SystemExit(f"Not a directory: {run_dir}")

    try:
        report = run_gates(run_dir, args.facts)
    except SystemExit:
        raise
    except Exception as exc:  # graceful error, never a bare crash
        print(f"[gates] ERROR: {exc}", file=sys.stderr)
        return 2

    out_path = run_dir / f"gate_report_{report['iteration']}.json"
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(f"[gates] wrote {out_path}")
    print(f"[gates] OVERALL: {'PASS' if report['pass'] else 'FAIL'}")

    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
