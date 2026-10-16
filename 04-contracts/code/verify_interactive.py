"""QA gate for interactive/contract-review.html. Exits 1 on
any failed check.

Modelled on 03 Invoices' code/verify_interactive.py. Checks: self-containment
(single external request = Google Fonts; the SVG XML namespace string is not
a network request and is exempted, documented below), hpx- class prefix
discipline, no id collisions, balanced structural tags, embedded-JSON (``var
D = {...};``) integrity cross-checked against data/runs/evaluation.json and
data/runs/extract_agent_log.json, typography rules (no em-dashes or
word-internal straight apostrophes in static prose, no "artifact", "license"
flagged as a noun outside its exempt capitalised uses), lang/viewport/
reduced-motion/height-reporting/aria-label/role=img presence, no oversized
fixed pixel heights, viewBox on every SVG, the CUAD attribution string, the
not-legal-advice banner line, the __HPX_DATA__ placeholder being gone (i.e.
the build actually ran), and the answer-key-isolation strings from
validate_corpus.py's rule 10 being absent from the built page.

Run standalone: `python verify_interactive.py`
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# cp1252 console guard (Windows terminals can't print curly quotes/dashes in
# failure detail strings without this -- same guard as validate_corpus.py).
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
PAGE = PROJECT / "interactive" / "contract-review.html"
EVALUATION_PATH = PROJECT / "data" / "runs" / "evaluation.json"
EXTRACT_AGENT_LOG_PATH = PROJECT / "data" / "runs" / "extract_agent_log.json"

MAX_PAGE_BYTES = 200_000
MAX_FIXED_HEIGHT_PX = 600
COVERAGE_TOLERANCE = 1e-3  # 3-decimal tolerance

# The XML namespace URI passed to document.createElementNS -- a fixed
# identifier string, never an HTTP request a browser makes. Excluded from
# the "external request" count for that reason, not because it is missing
# from the http(s):// scan.
EXEMPT_NAMESPACE_URIS = {"http://www.w3.org/2000/svg"}

# Rule 10 in validate_corpus.py: these two strings must never appear outside
# the six whitelisted pipeline-facing scripts. The interactive page is not
# on that whitelist and must reference only data/runs/evaluation.json (a
# scored, aggregate artefact), never the answer-key directory or the CUAD
# clause-annotation spreadsheet by name.
FORBIDDEN_STRINGS = ["answer_key", "master_clauses"]

STRUCTURAL_TAGS = ("div", "section", "header", "footer", "script", "style", "svg")

failures: list[str] = []
total_checks = 0  # incremented by every check() call -- the source of truth
                  # for "how many checks does this gate run", printed in the
                  # summary so a doc citing a check count can be verified
                  # against a live number instead of a hand-counted one going
                  # stale (the "log says 42, source has 43" drift this was
                  # written to close for good).


def check(name: str, ok: bool, detail: str = "") -> None:
    global total_checks
    total_checks += 1
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def fail_all_and_exit(message: str) -> None:
    """A missing required input is a hard stop, not a soft check failure --
    print it plainly and exit 1 rather than cascading into confusing
    downstream failures."""
    print(f"verify_interactive.py: {message}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# 1. File exists, decodes as UTF-8, is under the size budget
# ---------------------------------------------------------------------------

if not PAGE.exists():
    fail_all_and_exit(f"target page not found: {PAGE}")

raw_bytes = PAGE.read_bytes()
try:
    html = raw_bytes.decode("utf-8")
except UnicodeDecodeError as exc:
    fail_all_and_exit(f"{PAGE} is not valid UTF-8: {exc}")
# Normalise CRLF/CR to LF (Windows-authored file) so regexes anchored on a
# bare "\n" -- e.g. the end of the embedded-JSON line -- match regardless of
# the file's line-ending style; byte-size and UTF-8 checks above already ran
# against the untouched raw_bytes.
html = html.replace("\r\n", "\n").replace("\r", "\n")

check("file exists", True)
check("decodes as UTF-8", True)
check(f"size under {MAX_PAGE_BYTES:,} bytes", len(raw_bytes) < MAX_PAGE_BYTES,
      f"{len(raw_bytes):,} bytes")

if not EVALUATION_PATH.exists():
    fail_all_and_exit(f"required cross-check input not found: {EVALUATION_PATH}")
if not EXTRACT_AGENT_LOG_PATH.exists():
    fail_all_and_exit(f"required cross-check input not found: {EXTRACT_AGENT_LOG_PATH}")
try:
    evaluation = json.loads(EVALUATION_PATH.read_text(encoding="utf-8"))
    extract_agent_log = json.loads(EXTRACT_AGENT_LOG_PATH.read_text(encoding="utf-8"))
except json.JSONDecodeError as exc:
    fail_all_and_exit(f"could not parse a required cross-check input: {exc}")


# ---------------------------------------------------------------------------
# 2. Balanced structural tags (open count == close count)
# ---------------------------------------------------------------------------

for tag in STRUCTURAL_TAGS:
    n_open = len(re.findall(rf"<{tag}[\s>]", html))
    n_close = html.count(f"</{tag}>")
    check(f"balanced <{tag}>", n_open == n_close, f"{n_open} open vs {n_close} close")


# ---------------------------------------------------------------------------
# 3. Exactly one external request (Google Fonts), nothing else external
# ---------------------------------------------------------------------------

all_urls = re.findall(r'https?://[^\s"\'<>]+', html)
external_requests = [u for u in all_urls if u not in EXEMPT_NAMESPACE_URIS]
check("exactly one external request",
      len(external_requests) == 1,
      f"found {len(external_requests)}: {external_requests}")
check("the one external request is the Google Fonts stylesheet",
      bool(external_requests) and "fonts.googleapis.com" in external_requests[0],
      str(external_requests))
check("no separate fonts.gstatic.com reference (preconnect-free single link)",
      "fonts.gstatic.com" not in html)
check("no fetch/XMLHttpRequest calls", "fetch(" not in html and "XMLHttpRequest" not in html)


# ---------------------------------------------------------------------------
# 4. Every class="..." token starts with hpx-
# ---------------------------------------------------------------------------

classes: set[str] = set()
for class_attr in re.findall(r'class="([^"]*)"', html):
    classes.update(class_attr.split())
non_prefixed = {c for c in classes if not c.startswith("hpx-")}
check("hpx- prefix on every class token", not non_prefixed, str(sorted(non_prefixed)[:8]))


# ---------------------------------------------------------------------------
# 5. No id collisions
# ---------------------------------------------------------------------------

ids = re.findall(r'id="([^"]*)"', html)
duplicate_ids = sorted({i for i in ids if ids.count(i) > 1})
check("no id collisions", not duplicate_ids, f"{len(ids)} ids total; duplicates: {duplicate_ids}")


# ---------------------------------------------------------------------------
# 6. Embedded JSON (var D = {...};) integrity, cross-checked against the run
#    artefacts
# ---------------------------------------------------------------------------

data_match = re.search(r"var D = (\{.*?\});\n", html, re.S)
check("embedded `var D = {...};` blob found", data_match is not None)

if data_match is not None:
    try:
        data = json.loads(data_match.group(1))
        embedded_json_ok = True
    except json.JSONDecodeError as exc:
        data = None
        embedded_json_ok = False
    check("embedded blob parses as JSON", embedded_json_ok, "" if embedded_json_ok else str(exc))
else:
    data = None

if data is not None:
    headline = data.get("headline", {})
    check("headline.comparisons == 776", headline.get("comparisons") == 776,
          str(headline.get("comparisons")))
    check("headline.predictions_matched == 4", headline.get("predictions_matched") == 4,
          str(headline.get("predictions_matched")))

    # Cross-check predictions_matched is not just hardcoded right but agrees
    # with an independent recount from evaluation.json's own rows.
    eval_pva_by_category = {row["category"]: row for row in evaluation["predicted_vs_actual"]}
    recounted_matches = sum(1 for row in eval_pva_by_category.values() if row["match"])
    check("headline.predictions_matched agrees with evaluation.json recount",
          headline.get("predictions_matched") == recounted_matches,
          f"embedded={headline.get('predictions_matched')} recounted={recounted_matches}")

    embedded_pva = data.get("predicted_vs_actual", [])
    check("embedded predicted_vs_actual has 12 categories", len(embedded_pva) == 12,
          str(len(embedded_pva)))

    embedded_pva_by_category = {row["category"]: row for row in embedded_pva}
    category_set_agrees = set(embedded_pva_by_category) == set(eval_pva_by_category)
    check("predicted_vs_actual category sets agree with evaluation.json",
          category_set_agrees,
          f"embedded only: {set(embedded_pva_by_category) - set(eval_pva_by_category)}; "
          f"evaluation only: {set(eval_pva_by_category) - set(embedded_pva_by_category)}")

    match_mismatches = [
        category for category, eval_row in eval_pva_by_category.items()
        if category in embedded_pva_by_category
        and bool(embedded_pva_by_category[category]["match"]) != bool(eval_row["match"])
    ]
    check("predicted_vs_actual match booleans agree with evaluation.json",
          not match_mismatches, str(match_mismatches))

    # Coverage: every active-category row in D.coverage must agree with
    # evaluation.json's predicted_vs_actual holdout_coverage for the same
    # category, within a 3-decimal tolerance.
    coverage_rows = data.get("coverage", [])
    coverage_mismatches = []
    for row in coverage_rows:
        category = row["category"]
        eval_row = eval_pva_by_category.get(category)
        if eval_row is None:
            coverage_mismatches.append(f"{category}: not found in evaluation.json")
            continue
        expected_coverage = eval_row["holdout_coverage"]
        expected_coverage = 0.0 if expected_coverage is None else expected_coverage
        if abs(row["coverage"] - expected_coverage) > COVERAGE_TOLERANCE:
            coverage_mismatches.append(
                f"{category}: embedded={row['coverage']} evaluation={expected_coverage}"
            )
    check("coverage values agree with evaluation.json (3-decimal tolerance)",
          not coverage_mismatches, str(coverage_mismatches))

    # Costs: total_tokens must agree with extract_agent_log.json's own total,
    # not just be internally consistent.
    embedded_total_tokens = data.get("costs", {}).get("total_tokens")
    log_total_tokens = extract_agent_log.get("total_tokens")
    check("costs.total_tokens == extract_agent_log.json total_tokens",
          embedded_total_tokens == log_total_tokens,
          f"embedded={embedded_total_tokens} log={log_total_tokens}")


# ---------------------------------------------------------------------------
# 7. Typography in static visible prose (script/style stripped, so the JSON
#    blob and every JS string literal are out of scope by construction;
#    blockquote and the hpx-code excerpt are additionally stripped in case a
#    future edit puts static markup there)
# ---------------------------------------------------------------------------

prose = re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.S)
prose = re.sub(r"<style\b[^>]*>.*?</style>", "", prose, flags=re.S)
prose = re.sub(r"<blockquote\b[^>]*>.*?</blockquote>", "", prose, flags=re.S)
prose = re.sub(r'<div class="hpx-code"[^>]*>.*?</div>', "", prose, flags=re.S)
prose_text = re.sub(r"<[^>]+>", " ", prose)

em_dash_context = [
    prose_text[max(0, m.start() - 25): m.start() + 25].strip()
    for m in re.finditer("—", prose_text)
]
check('no em-dash "—" in static prose (spaced en-dashes only)',
      not em_dash_context, f"{len(em_dash_context)} occurrence(s), e.g. {em_dash_context[:4]}")

word_internal_straight_apostrophes = re.findall(r"[A-Za-z]'[A-Za-z]", prose_text)
check("no word-internal straight apostrophes in static prose",
      not word_internal_straight_apostrophes, str(word_internal_straight_apostrophes[:8]))

check('no "artifact" in static prose (British spelling: artefact)',
      "artifact" not in prose_text.lower())

# "license" as a noun is a misspelling of "licence" in British English;
# "licensed"/"licensing" are legitimate verb forms, and the capitalised
# category name "License Grant" / quoted contract text like "MEDIA LICENSE
# AGREEMENT" are exempt (both live inside the stripped JSON blob for this
# page, but the exemption is applied here too in case that ever changes).
license_candidates = re.finditer(r"\blicense(s)?\b", prose_text, re.IGNORECASE)
bad_license_uses = []
for m in license_candidates:
    start, end = m.span()
    window = prose_text[max(0, start - 20): end + 20]
    if "License Grant" in window or "MEDIA LICENSE AGREEMENT" in window.upper().replace(
        "MEDIA LICENSE AGREEMENT".upper(), "MEDIA LICENSE AGREEMENT"
    ):
        continue
    if "MEDIA LICENSE AGREEMENT" in window.upper():
        continue
    bad_license_uses.append(prose_text[max(0, start - 15): end + 15].strip())
check('no "license" used as a noun in static prose (licence is the BrE noun)',
      not bad_license_uses, str(bad_license_uses[:6]))


# ---------------------------------------------------------------------------
# 8. prefers-reduced-motion, postMessage height reporting, aria-label +
#    role=img on both SVGs
# ---------------------------------------------------------------------------

check("prefers-reduced-motion present in CSS", "prefers-reduced-motion" in html)
check("postMessage height reporting present in JS",
      "postMessage" in html and "height" in html)

aria_label_count = len(re.findall(r'setAttribute\(\s*["\']aria-label["\']', html))
role_img_count = len(re.findall(r'setAttribute\(\s*["\']role["\']\s*,\s*["\']img["\']\s*\)', html))
svg_creation_count = len(re.findall(r'svgEl\("svg"\)', html))
# >= rather than ==: the category drill-down's clickable rows also carry
# their own aria-label (a real accessibility improvement, not an SVG), so
# the total can now exceed the SVG count -- it must never fall short of it.
check("aria-label set on at least both SVGs", aria_label_count >= svg_creation_count and svg_creation_count > 0,
      f"aria-label count={aria_label_count}, svg elements created={svg_creation_count}")
check('role="img" set on both SVGs', role_img_count == 2,
      f"role=img count={role_img_count}")


# ---------------------------------------------------------------------------
# 9. No large fixed pixel heights; viewBox on every SVG; no hardcoded
#    width= on svg elements
# ---------------------------------------------------------------------------

fixed_heights_css = [
    int(h) for h in re.findall(r"[^-]height\s*:\s*(\d+)px", html) if int(h) > MAX_FIXED_HEIGHT_PX
]
fixed_heights_attr = [
    int(h) for h in re.findall(r'height="(\d+)"', html) if int(h) > MAX_FIXED_HEIGHT_PX
]
check(f"no fixed heights over {MAX_FIXED_HEIGHT_PX}px",
      not fixed_heights_css and not fixed_heights_attr,
      f"css: {fixed_heights_css}, attr: {fixed_heights_attr}")

viewbox_count = len(re.findall(r'setAttribute\(\s*["\']viewBox["\']', html)) + \
    len(re.findall(r'\bviewBox="', html))
check("viewBox present on all SVGs", viewbox_count == svg_creation_count and svg_creation_count > 0,
      f"viewBox occurrences={viewbox_count}, svg elements created={svg_creation_count}")

hardcoded_svg_width = re.findall(r"<svg[^>]*\swidth=", html) + \
    re.findall(r'svg\.setAttribute\(\s*["\']width["\']', html)
check("no hardcoded width= on svg elements", not hardcoded_svg_width, str(hardcoded_svg_width))


# ---------------------------------------------------------------------------
# 10. CUAD attribution string present
# ---------------------------------------------------------------------------

check('attribution mentions "CUAD"', "CUAD" in html)
check('attribution mentions "CC BY 4.0"', "CC BY 4.0" in html)
check('attribution mentions "Atticus"', "Atticus" in html)
check('attribution mentions "arXiv:2103.06268"', "arXiv:2103.06268" in html)
check('attribution contains a not-legal-advice disclaimer',
      bool(re.search(r"(not legal advice|is not legal advice|"
                     r"Nothing on this (page|report) is legal advice)", html)),
      "no recognised not-legal-advice phrasing found")


# ---------------------------------------------------------------------------
# 11. lang="en-GB" on <html>; meta viewport present
# ---------------------------------------------------------------------------

check('lang="en-GB" on <html>', bool(re.search(r"<html[^>]*\blang=\"en-GB\"", html)))
check("meta viewport present", 'name="viewport"' in html)


# ---------------------------------------------------------------------------
# 12. The not-legal-advice line appears in the visible banner text (not only
#     buried in the embedded JSON)
# ---------------------------------------------------------------------------

banner_match = re.search(r'<div class="hpx-honesty">(.*?)</div>', html, re.S)
banner_text = banner_match.group(1) if banner_match else ""
check("not-legal-advice line appears in the visible honesty box",
      "legal advice" in banner_text.lower())


# ---------------------------------------------------------------------------
# 13. __HPX_DATA__ placeholder absent (i.e. the build actually ran)
# ---------------------------------------------------------------------------

check("__HPX_DATA__ placeholder absent (build ran)", "__HPX_DATA__" not in html)


# ---------------------------------------------------------------------------
# 14. Rule-10 answer-key isolation strings absent from the built page
#     (validate_corpus.py's rule 10: this page must reference only
#     data/runs/evaluation.json, never the answer-key directory or the CUAD
#     clause-annotation spreadsheet by name)
# ---------------------------------------------------------------------------

found_forbidden = [term for term in FORBIDDEN_STRINGS if term in html]
check("no rule-10 forbidden strings (answer-key dir / clause CSV names)",
      not found_forbidden, str(found_forbidden))


# ---------------------------------------------------------------------------
# 15. Typography INSIDE the embedded JSON payload's own display strings.
#     Check 7 above strips <script> before scanning for em-dashes/straight
#     apostrophes, so it never looks at var D = {...} at all -- a real gap
#     that let em-dashes reach the page through the JSON (footer attribution,
#     two exemplar labels, one demotion card, all fixed at the build_data
#     layer, not here). This check closes that blind spot for good: it walks
#     every string value in the parsed embedded blob and re-runs the same
#     two typography rules, but only over fields that are OUR OWN authored
#     or paraphrased display prose -- never over verbatim quoted material
#     (real contract text, matcher source code, worksheet answers), which
#     must stay byte-faithful to its artefact and is expected to contain
#     plain ASCII apostrophes (the SEC-filing plaintext convention) and,
#     rarely, a genuine em-dash from the source itself.
# ---------------------------------------------------------------------------

# Fields holding verbatim quoted material (contract text, matcher code,
# worksheet-derived answers/context) -- excluded from BOTH typography scans.
_JSON_VERBATIM_KEYS = {
    "text", "source", "regex", "contract", "pipeline_answer", "key_answer", "context",
}
# "limits" is also excluded from the apostrophe scan specifically: it is a
# verbatim excerpt of the overseer's own code-comment prose (see
# build_interactive_data.py's _extract_known_limits docstring), house-
# typographed for em-dashes only, never for apostrophes.
_JSON_APOSTROPHE_EXTRA_EXCLUDE = {"limits"}


def _walk_json_strings(node, exclude_keys, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            if k in exclude_keys:
                continue
            yield from _walk_json_strings(v, exclude_keys, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_json_strings(v, exclude_keys, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


if data is not None:
    json_em_dash_hits = [
        (p, s[max(0, s.find("—") - 25): s.find("—") + 25])
        for p, s in _walk_json_strings(data, _JSON_VERBATIM_KEYS)
        if "—" in s
    ]
    check('no em-dash "—" in the embedded JSON\'s display strings',
          not json_em_dash_hits, str(json_em_dash_hits[:4]))

    json_apostrophe_hits = [
        (p, m.group(0))
        for p, s in _walk_json_strings(data, _JSON_VERBATIM_KEYS | _JSON_APOSTROPHE_EXTRA_EXCLUDE)
        for m in re.finditer(r"[A-Za-z]'[A-Za-z]", s)
    ]
    check("no word-internal straight apostrophes in the embedded JSON's display strings",
          not json_apostrophe_hits, str(json_apostrophe_hits[:8]))
else:
    check('no em-dash "—" in the embedded JSON\'s display strings', False, "no embedded JSON to scan")
    check("no word-internal straight apostrophes in the embedded JSON's display strings",
          False, "no embedded JSON to scan")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
if failures:
    print(f"FAILED: {len(failures)} of {total_checks} check(s): {failures}")
    sys.exit(1)
print(f"ALL {total_checks} CHECKS PASS ({PAGE.stat().st_size / 1024:.1f} KB, self-contained)")
