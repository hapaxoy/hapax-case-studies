"""
verify_interactive_09.py -- QA gate for interactive/training-outcomes.html.

Modelled on 07 Tenders' code/verify_interactive_07.py (structural checks:
single external request, hpx- prefix discipline, balanced tags, embedded-JSON
parity, typography, embeddability), trimmed to this project's own shape --
there is no in-browser scored game here, so there is no JS-vs-Python
agreement check to run; everything else carries over:

  - single external request (Google Fonts only), no other absolute URLs;
  - hpx- prefix discipline on every class and id;
  - balanced tags, page size under the 2 MB budget;
  - embedded <script id="hpx-data"> parses and matches interactive/_data.json
    byte-for-byte;
  - every displayed headline number re-checked against
    data/analysis/marks.json directly (the sole output of code/mark.py, the
    only script permitted to open the answer key) -- not against
    interactive/_data.json, which is itself downstream of marks.json and
    could in principle drift from it if build_data.py had a bug;
  - "nothing stored, nothing transmitted": no localStorage/sessionStorage/
    indexedDB/cookie access and no fetch/XHR/WebSocket/sendBeacon calls
    anywhere in the inline scripts (this page carries no game, but the
    house rule is checked page-wide regardless, per the 07 precedent);
  - every writeup quote used on the page is checked against
    writeup/training_outcomes_case_study.md by the same verbatim-paragraph
    extraction build_data.py itself uses, so a hand-edit that drifted a
    quote from its source paragraph is caught here too.

Exits 1 on any failing check; never crashes bare (graceful errors, portfolio
convention).

Usage (from the project root or from code/):
    python code/verify_interactive_09.py
"""
from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
INTERACTIVE_DIR = PROJECT_ROOT / "interactive"
HTML_PATH = INTERACTIVE_DIR / "training-outcomes.html"
DATA_JSON_PATH = INTERACTIVE_DIR / "_data.json"
MARKS_PATH = PROJECT_ROOT / "data" / "analysis" / "marks.json"
WRITEUP_PATH = PROJECT_ROOT / "writeup" / "training_outcomes_case_study.md"

ALLOWED_EXTERNAL_HOSTS = {"fonts.googleapis.com", "fonts.gstatic.com"}
# XML namespace URIs are literal identifiers required by createElementNS()
# for hand-rolled SVG -- never a network request -- so they are excluded
# from the "no other absolute URLs" scan below.
NAMESPACE_URIS = {"http://www.w3.org/2000/svg", "http://www.w3.org/1999/xhtml", "http://www.w3.org/1998/Math/MathML"}
VOID_TAGS = {"meta", "link", "br", "hr", "img", "input", "wbr", "source"}
MAX_SIZE_BYTES = 2 * 1024 * 1024

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


class TagAuditor:
    """Minimal HTML structural auditor: balanced tags, class/id inventory,
    visible text. Deliberately simple (stdlib html.parser), matching the
    07 Tenders precedent's own scope."""

    def __init__(self):
        class _Parser(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.stack = []
                self.errors = []
                self.classes = set()
                self.ids = set()
                self._skip = 0

            def handle_starttag(self, tag, attrs):
                if tag not in VOID_TAGS:
                    self.stack.append(tag)
                if tag in ("script", "style"):
                    self._skip += 1
                for k, v in attrs:
                    if k == "class" and v:
                        self.classes.update(v.split())
                    if k == "id" and v:
                        self.ids.add(v)

            def handle_startendtag(self, tag, attrs):
                for k, v in attrs:
                    if k == "class" and v:
                        self.classes.update(v.split())
                    if k == "id" and v:
                        self.ids.add(v)

            def handle_endtag(self, tag):
                if tag in ("script", "style"):
                    self._skip -= 1
                if tag in VOID_TAGS:
                    return
                if not self.stack or self.stack[-1] != tag:
                    self.errors.append(f"unbalanced </{tag}>")
                else:
                    self.stack.pop()

        self._parser = _Parser()

    def feed(self, html: str):
        self._parser.feed(html)
        return self._parser


def quote_paragraph(source_text: str, anchor: str, label: str) -> str:
    """Identical extraction logic to interactive/build_data.py's own
    quote_paragraph() -- re-implemented here (not imported) so this QA gate
    verifies the page's quotes independently of build_data.py's own code
    path, catching a drift in either file."""
    idx = source_text.find(anchor)
    if idx == -1:
        raise ValueError(f"quote '{label}': anchor not found: {anchor!r}")
    start = source_text.rfind("\n\n", 0, idx)
    start = 0 if start == -1 else start + 2
    end = source_text.find("\n\n", idx)
    end = len(source_text) if end == -1 else end
    para = source_text[start:end].strip()
    if para.startswith("*") and para.endswith("*") and not para.startswith("**"):
        para = para[1:-1]
    return para.replace("**", "")


# Anchors identical to build_data.py's build_quotes() -- kept as a separate
# list here (not imported) so a divergence between the two is visible rather
# than silently sharing a single point of failure.
QUOTE_ANCHORS = {
    "byline": "the forty learners, the two-day programme",
    "lede": "The evidence the industry offers for training",
    "cohort_independence": "cohort-wide correlation between planted shift",
    "confident_group_frame": "deliberately the largest problem group",
    "honest_desc": "counterbalanced so that no learner answers the same questions twice",
    "feedback_desc": "post-only self-reported satisfaction and self-assessed improvement",
    "naive_desc": "assembled from three documented bad practices",
    "corpus_note": "All three run on the same corpus",
    "cohort_recovered": "gap of 0.0100 inside a tolerance of 0.0124",
    "six_flagged": "single frozen statistic",
    "l23_exhibit": "shows the pattern.",
    "feedback_r_finding": "carries almost no information about whether anyone learned anything",
    "naive_overstate_finding": "pre-registration asked for 50%",
    "naive_decomp_note": "Two things there were not anticipated",
    "form_equivalence_finding": "Form equivalence failed",
    "scorer_reliability_intro": "9,046 of 9,600 item checks",
    "robustness_flip_finding": "Two of six verdicts flip, in opposite directions",
    "feedback_immune_dry_remark": "immunity to rater error bought by measuring nothing",
    "rater_reliability_conclusion": "Neither pass is the true answer",
    "real_engagement_three_things": "For a real engagement this settles three things",
    "forgetters_intro": "built to lose most of what they gained within two months",
    "forgetters_invisible": "average a measured gain of 0.2667",
    "forgetters_8wk": "no named instrument reads it",
    "markus_exhibit": "show the decay in plain text",
    "followup_argument": "published argument for the follow-up",
    "what_transfers": "The instrument transfers, and it is published in full",
    "what_doesnt_transfer": "The numbers do not transfer.",
    "closing": "the entire reason for measuring it",
}


def main() -> int:
    print("=" * 74)
    print("verify_interactive_09.py -- QA gate for interactive/training-outcomes.html")
    print("=" * 74)

    if not HTML_PATH.exists():
        print(f"\ninteractive/training-outcomes.html not present yet at {HTML_PATH}.")
        print("Nothing to verify. Run interactive/build_data.py first.")
        return 0

    if not DATA_JSON_PATH.exists() or not MARKS_PATH.exists():
        print(f"\nFATAL: {HTML_PATH.name} exists but a required data file does not "
              f"({DATA_JSON_PATH.name} or {MARKS_PATH}). Run interactive/build_data.py first.")
        return 1

    html = HTML_PATH.read_text(encoding="utf-8")
    with DATA_JSON_PATH.open("r", encoding="utf-8") as f:
        expected_data = json.load(f)
    with MARKS_PATH.open("r", encoding="utf-8") as f:
        marks = json.load(f)
    writeup_text = WRITEUP_PATH.read_text(encoding="utf-8")

    size_bytes = HTML_PATH.stat().st_size
    print(f"\nChecking {HTML_PATH} ({size_bytes / 1024:.1f} KB) ...\n")

    print("Structure")
    parser = TagAuditor().feed(html)
    check("balanced tags", not parser.errors and not parser.stack,
          "; ".join(parser.errors) or (f"still open: {','.join(parser.stack)}" if parser.stack else ""))
    unprefixed_classes = sorted(c for c in parser.classes if not c.startswith("hpx-"))
    check("every class hpx-prefixed", not unprefixed_classes, ", ".join(unprefixed_classes))
    unprefixed_ids = sorted(i for i in parser.ids if not i.startswith("hpx-"))
    check("every id hpx-prefixed", not unprefixed_ids, ", ".join(unprefixed_ids))
    check("page under 2 MB", size_bytes < MAX_SIZE_BYTES, f"{size_bytes/1024:.1f} KB")

    print("\nExternal requests")
    external_urls = re.findall(r'(?:href|src)\s*=\s*["\'](https?://[^"\']+)["\']', html)
    bad_hosts = sorted({u.split("/")[2] for u in external_urls} - ALLOWED_EXTERNAL_HOSTS)
    check("no external requests beyond Google Fonts", not bad_hosts, ", ".join(bad_hosts))
    font_links = [u for u in external_urls if u.startswith("https://fonts.googleapis.com")]
    check("exactly one Google Fonts stylesheet link", len(font_links) == 1, f"found {len(font_links)}")
    all_absolute_urls = re.findall(r'https?://[^\s"\'<>)]+', html)
    non_font_urls = [
        u for u in all_absolute_urls
        if not u.startswith(tuple(f"https://{h}" for h in ALLOWED_EXTERNAL_HOSTS))
        and u not in NAMESPACE_URIS
    ]
    check("no other absolute URLs anywhere in the file (SVG namespace URI excepted)", not non_font_urls, ", ".join(non_font_urls[:10]))

    print("\nNothing stored, nothing transmitted")
    script_blocks = re.findall(r"<script\b[^>]*>(.*?)</script>", html, re.S)
    js_text = "\n".join(script_blocks)
    storage_tokens = re.findall(r"\b(localStorage|sessionStorage|indexedDB|document\.cookie|openDatabase)\b", js_text)
    check("no browser storage APIs referenced", not storage_tokens, ", ".join(sorted(set(storage_tokens))))
    network_tokens = re.findall(r"\b(fetch\s*\(|XMLHttpRequest|\.ajax\s*\(|sendBeacon|new\s+WebSocket|EventSource)\b", js_text)
    check("no network-call APIs referenced (fetch/XHR/WebSocket/sendBeacon)", not network_tokens, ", ".join(sorted(set(network_tokens))))
    src_values = re.findall(r'\bsrc\s*=\s*["\']([^"\']+)["\']', html)
    external_src = [s for s in src_values if s.startswith(("http://", "https://")) and not s.startswith("data:")]
    check("no src= attribute points outside the file", not external_src, ", ".join(external_src))

    print("\nEmbedded data integrity")
    m = re.search(r'<script type="application/json" id="hpx-data">(.*?)</script>', html, re.S)
    embedded_ok = False
    embedded_matches = False
    if m:
        try:
            embedded_data = json.loads(m.group(1))
            embedded_ok = True
            embedded_matches = embedded_data == expected_data
        except json.JSONDecodeError as exc:
            check("embedded <script id=hpx-data> parses", False, str(exc))
    check('embedded <script id="hpx-data"> present and parses', bool(m) and embedded_ok)
    check("embedded JSON matches interactive/_data.json exactly", embedded_ok and embedded_matches)

    print("\nHeadline numbers re-checked against data/analysis/marks.json directly")
    primary = marks["primary_pass"]
    perfect = marks["perfect_scoring_robustness_pass"]
    check("n_learners == 40", expected_data["meta"]["n_learners"] == 40 == primary["honest_run"]["summary"]["n_learners"])
    check("n_confident_non_learners == 7",
          expected_data["meta"]["n_confident_non_learners"] == 7 == primary["expectations"]["2"]["n_planted_confident_non_learners"])
    check("n_flagged_total == 8",
          expected_data["meta"]["n_flagged_total"] == 8 == primary["honest_run"]["summary"]["n_flagged_confident_non_learners"])
    check("n_fast_forgetters == 3", expected_data["meta"]["n_fast_forgetters"] == 3)
    check("confident_non_learner_ids matches marks.json",
          expected_data["confident_non_learner_ids"] == primary["expectations"]["2"]["planted_confident_non_learner_ids"])
    check("flagged_ids matches marks.json",
          sorted(expected_data["flagged_ids"]) == sorted(primary["honest_run"]["summary"]["flagged_learner_ids"]))
    check("missed_ids / false_positive_ids match marks.json",
          expected_data["missed_ids"] == primary["expectations"]["2"]["missed_ids"] and
          expected_data["false_positive_ids"] == primary["expectations"]["2"]["false_positive_ids"])
    check("fast_forgetter_ids matches marks.json",
          expected_data["fast_forgetter_ids"] == [d["learner_id"] for d in primary["expectations"]["6"]["per_fast_forgetter_detail"]])
    check("expectations_scored matches marks.json's primary_pass.expectations exactly",
          expected_data["expectations_scored"] == primary["expectations"])
    check("expectations_perfect matches marks.json's perfect_scoring_robustness_pass.expectations exactly",
          expected_data["expectations_perfect"] == perfect["expectations"])
    check("robustness_table matches marks.json exactly",
          expected_data["robustness_table"] == marks["robustness_table"])
    check("naive_decomposition matches marks.json's expectation 4 decomposition",
          expected_data["naive_decomposition"] == primary["expectations"]["4"]["decomposition"])
    check("fast_forgetter_detail matches marks.json's expectation 6",
          expected_data["fast_forgetter_detail"] == primary["expectations"]["6"])

    # Spot-check the headline numbers the page states.
    check("cohort mean delta-hat == 0.1437 (rounded)", round(primary["honest_run"]["summary"]["cohort_mean_delta_hat"], 4) == 0.1437)
    check("feedback-sheet r(confidence) == 0.101 (rounded)", round(primary["expectations"]["3"]["r_confidence_post_vs_planted_delta"], 3) == 0.101)
    check("naive overstatement == 41.3% (rounded)", round(primary["expectations"]["4"]["overstatement_pct"], 1) == 41.3)
    check("naive interaction/residual == 90.9% (rounded)",
          round(primary["expectations"]["4"]["decomposition"]["residual_pct_of_overstatement"], 1) == 90.9)
    check("fast-forgetter +8wk retention == 21.9% (rounded)",
          round(primary["expectations"]["6"]["fast_forgetter_8wk_retention_ratio"] * 100, 1) == 21.9)
    check("genuine-improver +8wk retention == 87.8% (rounded)",
          round(primary["expectations"]["6"]["genuine_improver_8wk_retention_ratio"] * 100, 1) == 87.8)
    check("expectation 1 flips MET -> NOT MET under perfect scoring",
          primary["expectations"]["1"]["met"] is True and perfect["expectations"]["1"]["met"] is False)
    check("expectation 4 flips NOT MET -> MET under perfect scoring",
          primary["expectations"]["4"]["met"] is False and perfect["expectations"]["4"]["met"] is True)

    print("\nCohort records (interactive/_data.json vs data/cohort/ + marks.json)")
    honest_by_id = {r["learner_id"]: r for r in primary["honest_run"]["learners"]}
    feedback_by_id = {r["learner_id"]: r for r in primary["feedback_run"]["learners"]}
    naive_by_id = {r["learner_id"]: r for r in primary["naive_run"]["learners"]}
    cohort_mismatches = []
    for c in expected_data["cohort"]:
        lid = c["learner_id"]
        h = honest_by_id.get(lid)
        f = feedback_by_id.get(lid)
        n = naive_by_id.get(lid)
        if h is None or c["honest"]["delta_hat"] != h["delta_hat"] or c["honest"]["divergence_z"] != h["divergence_z"] \
                or c["honest"]["flagged_confident_non_learner"] != h["flagged_confident_non_learner"]:
            cohort_mismatches.append(f"{lid}: honest mismatch")
        if f is None or c["feedback"]["confidence_post"] != f["confidence_post"] or c["feedback"]["satisfaction_post"] != f["satisfaction_post"]:
            cohort_mismatches.append(f"{lid}: feedback mismatch")
        if (n is None) != (c["naive"] is None):
            cohort_mismatches.append(f"{lid}: naive presence mismatch")
        elif n is not None and c["naive"]["blended_effect"] != n["blended_effect"]:
            cohort_mismatches.append(f"{lid}: naive value mismatch")
    check(f"all {len(expected_data['cohort'])} learners' instrument numbers match marks.json exactly",
          not cohort_mismatches, "; ".join(cohort_mismatches[:10]))
    check("cohort has exactly 40 learners", len(expected_data["cohort"]) == 40, str(len(expected_data["cohort"])))

    print("\nWriteup quotes -- re-extracted independently and compared to interactive/_data.json")
    quote_mismatches = []
    for key, anchor in QUOTE_ANCHORS.items():
        try:
            expected_quote = quote_paragraph(writeup_text, anchor, key)
        except ValueError as exc:
            quote_mismatches.append(f"{key}: {exc}")
            continue
        got = expected_data["quotes"].get(key)
        if got != expected_quote:
            quote_mismatches.append(f"{key}: page text does not match writeup paragraph verbatim")
    check(f"all {len(QUOTE_ANCHORS)} writeup quotes verified verbatim against the source paragraph",
          not quote_mismatches, "; ".join(quote_mismatches[:5]))
    for key in QUOTE_ANCHORS:
        check(f"quote text present on page: {key}", expected_data["quotes"].get(key, "") in html)

    print("\nEmbeddability")
    check("postMessage height reporting present (hpx-height shape)",
          '"hpx-height"' in html and "postMessage" in html)
    check("prefers-reduced-motion media query present", "prefers-reduced-motion" in html)
    check('viewport meta present', 'name="viewport"' in html)
    small_bp = re.search(r"@media[^{]*max-width\s*:\s*(\d+)px", html)
    check("at least one responsive media query at <=600px", bool(small_bp) and int(small_bp.group(1)) <= 600,
          f"tightest max-width: {small_bp.group(1)}px" if small_bp else "none found")

    print()
    if failures:
        print(f"FAILED ({len(failures)}): {failures}")
        return 1
    print(f"ALL CHECKS PASSED ({size_bytes/1024:.1f} KB, self-contained)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 -- QA gate must report, never crash bare
        print(f"\nFATAL: {exc}")
        sys.exit(1)
