"""
verify_interactive_07.py -- QA gate for interactive/tender-workflow.html.

Modelled on 06 Anomaly Detection's code/verify_interactive.py (structural
checks: single external request, hpx- prefix discipline, balanced tags,
embedded-JSON parity, typography, embeddability) and extended for this
project with:

  - headline numbers on the page re-checked against data/analysis/marks.json
    (the sole output of code/mark.py, the only script permitted to open the
    answer key);
  - the JS-vs-Python marking agreement check required for view
    4's game: interactive/quickplay_score.src.js (the exact source inlined
    into the page) is run under Node, via code/quickplay_agreement_check.js,
    over fixtures built from mark.py's own recorded per-requirement
    "addressed" flags for the twelve real Arm A attempts on T04/T08/T11, and
    its coverage_pct / trap "caught" outputs must agree with mark.py's own;
  - "nothing stored, nothing transmitted" for the whole page (not only the
    game): no localStorage/sessionStorage/indexedDB/cookie access and no
    fetch/XHR/WebSocket/sendBeacon calls anywhere in the inline scripts.

Exits 1 on any failing check; never crashes bare (graceful errors, as in the
other cases). Requires Node.js on PATH for the JS-vs-Python check only -- if
Node is unavailable that one check is reported FAIL with a clear reason
rather than silently skipped.

Usage (from the project root or from code/):
    python code/verify_interactive_07.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
INTERACTIVE_DIR = PROJECT_ROOT / "interactive"
HTML_PATH = INTERACTIVE_DIR / "tender-workflow.html"
DATA_JSON_PATH = INTERACTIVE_DIR / "_data.json"
GAME_JS_PATH = INTERACTIVE_DIR / "quickplay_score.src.js"
MARKS_PATH = PROJECT_ROOT / "data" / "analysis" / "marks.json"
AGREEMENT_RUNNER = SCRIPT_DIR / "quickplay_agreement_check.js"

ALLOWED_EXTERNAL_HOSTS = {"fonts.googleapis.com", "fonts.gstatic.com"}
# XML namespace URIs are literal identifiers required by createElementNS()
# for hand-rolled SVG -- never a network request -- so they are excluded
# from the "no other absolute URLs" scan below.
NAMESPACE_URIS = {"http://www.w3.org/2000/svg", "http://www.w3.org/1999/xhtml", "http://www.w3.org/1998/Math/MathML"}
VOID_TAGS = {"meta", "link", "br", "hr", "img", "input", "wbr", "source"}
MAX_SIZE_BYTES = 2 * 1024 * 1024

QUICKPLAY_TENDER_IDS = ["T04", "T08", "T11"]

# The three quick-play tenders' trap structure -- hardcoded here (not read
# from interactive/_data.json) so this script also cross-checks that
# build_data.py's own parsing produced the same thing, independently.
EXPECTED_TRAP_META = {
    "T04": {"format_trap": {"req_id": "T04-R013"}, "contradiction": None, "eligibility_fail": None},
    "T08": {"format_trap": None, "contradiction": {"req_ids": ["T08-R014", "T08-R029"]}, "eligibility_fail": None},
    "T11": {"format_trap": None, "contradiction": None, "eligibility_fail": {"req_id": "T11-R005"}},
}

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


class TagAuditor:
    """Minimal HTML structural auditor: balanced tags, class/id inventory,
    visible text. Deliberately simple (stdlib html.parser), matching the
    06 Anomaly Detection precedent's own scope."""

    def __init__(self):
        outer = self

        class _Parser(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.stack = []
                self.errors = []
                self.classes = set()
                self.ids = set()
                self.text = []
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

            def handle_data(self, data):
                if self._skip == 0:
                    self.text.append(data)

        self._parser = _Parser()

    def feed(self, html: str):
        self._parser.feed(html)
        return self._parser


def build_agreement_fixtures(marks: dict) -> list[dict]:
    """One fixture per real Arm A attempt on T04/T08/T11, feeding mark.py's
    own per-requirement 'addressed' flags into the game's scoring logic as
    if they were the visitor's ticks -- the honest spot-check the page's
    game needs (see quickplay_score.src.js's own docstring for why this is a
    legitimate port rather than a re-implementation)."""
    fixtures = []
    attempts = marks["arm_a"]["attempts"]
    for attempt_id, a in sorted(attempts.items()):
        if a["tender_id"] not in QUICKPLAY_TENDER_IDS:
            continue
        tender_id = a["tender_id"]
        key_req_ids = [row["req_id"] for row in a["per_requirement"]]
        ticked_req_ids = [row["req_id"] for row in a["per_requirement"] if row["addressed"]]
        bid_call = "no-bid" if a["bid_decision"] == "no-bid" else "bid"

        flag_conflict = False
        for tr in a["traps"]:
            if tr["trap_code"] == "contradiction":
                m = re.search(r"conflict_language_found=(True|False)", tr.get("detail", ""))
                if not m:
                    raise ValueError(f"{attempt_id}: could not parse conflict_language_found from trap detail")
                flag_conflict = m.group(1) == "True"

        fixtures.append({
            "attempt_id": attempt_id,
            "tender_id": tender_id,
            "key_req_ids": key_req_ids,
            "ticked_req_ids": ticked_req_ids,
            "bid_call": bid_call,
            "flag_conflict": flag_conflict,
            "trap_meta": EXPECTED_TRAP_META[tender_id],
            # mark.py's own recorded verdicts, to compare against:
            "expected_coverage_pct": a["coverage_pct"],
            "expected_traps": {tr["trap_code"]: tr["caught"] for tr in a["traps"]},
        })
    return fixtures


def run_agreement_check(marks: dict) -> None:
    print("\nJS-vs-Python marking agreement (spot-check) ...")
    if not GAME_JS_PATH.exists():
        check("quickplay_score.src.js present", False, str(GAME_JS_PATH))
        return
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
    except Exception as exc:  # noqa: BLE001
        check("Node.js available to run the agreement check", False, str(exc))
        return

    try:
        fixtures = build_agreement_fixtures(marks)
    except Exception as exc:  # noqa: BLE001
        check("fixtures built from marks.json", False, str(exc))
        return
    check("fixtures built from marks.json", len(fixtures) == 12, f"{len(fixtures)} fixtures (expected 12: 4 attempts x 3 tenders)")

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(fixtures, f)
        fixtures_path = f.name

    try:
        proc = subprocess.run(
            ["node", str(AGREEMENT_RUNNER), fixtures_path, str(GAME_JS_PATH)],
            capture_output=True, text=True, timeout=30,
        )
    except Exception as exc:  # noqa: BLE001
        check("Node agreement runner executed", False, str(exc))
        return
    finally:
        try:
            Path(fixtures_path).unlink()
        except OSError:
            pass

    if proc.returncode != 0:
        check("Node agreement runner executed", False, proc.stderr.strip()[:400])
        return
    check("Node agreement runner executed", True)

    try:
        results = {r["attempt_id"]: r["result"] for r in json.loads(proc.stdout)}
    except Exception as exc:  # noqa: BLE001
        check("agreement runner output parses as JSON", False, f"{exc}: {proc.stdout[:300]!r}")
        return

    coverage_mismatches = []
    trap_mismatches = []
    for fx in fixtures:
        r = results.get(fx["attempt_id"])
        if r is None:
            coverage_mismatches.append(f"{fx['attempt_id']}: no result returned")
            continue
        if abs(r["coverage_pct"] - fx["expected_coverage_pct"]) > 1e-6:
            coverage_mismatches.append(
                f"{fx['attempt_id']}: JS={r['coverage_pct']} mark.py={fx['expected_coverage_pct']}"
            )
        js_traps = {t["trap_code"]: t["caught"] for t in r["traps"]}
        for code, expected_caught in fx["expected_traps"].items():
            got = js_traps.get(code)
            if got != expected_caught:
                trap_mismatches.append(
                    f"{fx['attempt_id']} [{code}]: JS caught={got} mark.py caught={expected_caught}"
                )

    check(
        f"coverage_pct agreement across {len(fixtures)} attempts (T04/T08/T11)",
        not coverage_mismatches, "; ".join(coverage_mismatches),
    )
    check(
        "trap 'caught' agreement (format_trap, contradiction, eligibility_fail)",
        not trap_mismatches, "; ".join(trap_mismatches),
    )
    if not coverage_mismatches and not trap_mismatches:
        print(f"    -> {len(fixtures)}/{len(fixtures)} attempts: exact coverage_pct and trap-caught agreement")


def main() -> int:
    print("=" * 74)
    print("verify_interactive_07.py -- QA gate for interactive/tender-workflow.html")
    print("=" * 74)

    if not HTML_PATH.exists():
        print(f"\ninteractive/tender-workflow.html not present yet at {HTML_PATH}.")
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

    print("\nNothing stored, nothing transmitted (the game's rule, applied page-wide)")
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

    print("\nHeadline numbers re-checked against data/analysis/marks.json")
    check("n_arm_a_attempts == 64", expected_data["meta"]["n_arm_a_attempts"] == 64 == marks["meta"]["n_arm_a_attempts"])
    check("n_arm_b_runs == 16", expected_data["meta"]["n_arm_b_runs"] == 16 == marks["meta"]["n_arm_b_runs"])
    total_key_reqs = sum(r["n_key_requirements"] for r in marks["arm_b"]["runs"].values())
    check("n_key_requirements matches sum of marks.json's per-tender key counts",
          expected_data["meta"]["n_key_requirements"] == total_key_reqs, f"{expected_data['meta']['n_key_requirements']} vs {total_key_reqs}")

    tender_mismatches = []
    for t in expected_data["tenders"]:
        tid = t["id"]
        run = marks["arm_b"]["runs"][tid]
        by_t = marks["arm_a"]["by_tender"][tid]
        if t["arm_b_final_coverage"] != run["final_coverage_pct"] or t["arm_b_bid_no_bid"] != run["bid_no_bid"]:
            tender_mismatches.append(f"{tid}: Arm B mismatch")
        if (t["arm_a_median_coverage"] != by_t["median_coverage"] or
                t["arm_a_best_coverage"] != by_t["best_coverage"] or
                t["arm_a_worst_coverage"] != by_t["worst_coverage"]):
            tender_mismatches.append(f"{tid}: Arm A mismatch")
    check("all 16 tenders' displayed numbers match marks.json exactly", not tender_mismatches, "; ".join(tender_mismatches))

    check("expectations block matches marks.json's 6 verdicts",
          expected_data["expectations"] == marks["expectations"])
    check("trap_table matches marks.json exactly",
          expected_data["trap_table"] == marks["trap_table"])

    print("\nQuick-play game data (view 4)")
    trap_meta_mismatches = []
    for tid in QUICKPLAY_TENDER_IDS:
        got = expected_data["quickplay"][tid]["trap_meta"]
        want = EXPECTED_TRAP_META[tid]
        if got != want:
            trap_meta_mismatches.append(f"{tid}: got {got} want {want}")
    check("quick-play trap metadata matches the hand-verified answer key for T04/T08/T11",
          not trap_meta_mismatches, "; ".join(trap_meta_mismatches))
    clause_count_mismatches = []
    for tid, expected_n in (("T04", 16), ("T08", 32), ("T11", 30)):
        qp = expected_data["quickplay"][tid]
        n_clauses = sum(len(s["clauses"]) for s in qp["sections"])
        if n_clauses != expected_n or len(qp["key_req_ids"]) != expected_n:
            clause_count_mismatches.append(f"{tid}: {n_clauses} clauses, {len(qp['key_req_ids'])} key reqs (want {expected_n})")
    check("quick-play clause counts match the answer key 1:1 for all three tenders",
          not clause_count_mismatches, "; ".join(clause_count_mismatches))

    run_agreement_check(marks)

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
