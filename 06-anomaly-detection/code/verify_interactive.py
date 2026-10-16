"""
verify_interactive.py -- QA gate for interactive/anomaly-detection.html.

Checks the embeddability constraints the page inherits (single self-contained HTML file, hpx- prefix).
Precedent: 05-board-reporting/interactive/_verify_page.py
(read-only reference; extended here with further checks -- id-prefixing, an exact external-resource count, embedded-JSON
byte-for-byte parity with interactive/_data.json, and a British-spellings
spot-check).

The interactive page itself is built separately. This script runs cleanly
*before* the page exists (reporting that plainly and exiting 0 -- there is nothing to fail
yet) and gate it properly once it does (exit 1 on any check failure).

Usage (from the project root or from code/):
    python code/verify_interactive.py
"""

import json
import re
import sys
from pathlib import Path

# Windows consoles often default stdout/stderr to a legacy codepage (cp1252)
# that cannot encode en-dashes, umlauts, or the checkmark-adjacent prose this
# script prints when reporting a typography violation. Reconfigure to UTF-8
# with a safe fallback so a diagnostic print can never itself crash the run
# (graceful errors, never a bare crash).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
INTERACTIVE_DIR = PROJECT_ROOT / "interactive"
HTML_PATH = INTERACTIVE_DIR / "anomaly-detection.html"
DATA_JSON_PATH = INTERACTIVE_DIR / "_data.json"

ALLOWED_EXTERNAL_HOSTS = {"fonts.googleapis.com", "fonts.gstatic.com"}
VOID_TAGS = {"meta", "link", "br", "hr", "img", "input", "wbr", "source"}

# British-spellings spot-list. Not exhaustive -- a spot-check -- chosen
# to avoid words with a legitimate British "-ize"/"-ise" ambiguity (both are
# valid Oxford spelling) so this check does not fail on correct copy.
AMERICAN_SPELLING_SPOTLIST = [
    "color", "colors", "colored", "favorite", "favorites", "organization",
    "organizations", "behavior", "behaviors", "center", "centers", "gray",
    "defense", "modeling", "traveled", "canceled", "fiber", "meter",
    "liter", "labeled", "neighbor",
]

SCRIPT_JSON_RE = re.compile(
    r'<script\b(?=[^>]*\bid=["\']hpx-data["\'])(?=[^>]*\btype=["\']application/json["\'])'
    r'[^>]*>(.*?)</script>',
    re.S,
)

failures = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(name)


class TagAuditor:
    """Minimal HTML structural auditor: balanced tags, class/id inventory,
    and visible text (script/style content excluded). Deliberately simple
    (stdlib html.parser) -- this is a QA gate, not a full HTML validator,
    matching the 05 precedent's own scope."""

    def __init__(self):
        from html.parser import HTMLParser

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
                # self-closing tags (<br/>, <img .../>) never affect self.stack
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


def main() -> int:
    print("=" * 70)
    print("verify_interactive.py -- QA gate for interactive/anomaly-detection.html")
    print("=" * 70)

    if not HTML_PATH.exists():
        print(f"\ninteractive/anomaly-detection.html not present yet at {HTML_PATH}.")
        print("Nothing to verify -- this is expected before Phase 5's page is built.")
        print("Re-run this script once the page exists; every check")
        print("below will then run and gate it (exit 1 on any failure).")
        return 0

    if not DATA_JSON_PATH.exists():
        print(f"\nFATAL: {HTML_PATH.name} exists but {DATA_JSON_PATH} does not. "
              "Run code/build_interactive_data.py first -- the page's embedded JSON "
              "is checked against it.")
        return 1

    html = HTML_PATH.read_text(encoding="utf-8")
    with DATA_JSON_PATH.open("r", encoding="utf-8") as f:
        expected_data = json.load(f)

    print(f"\nChecking {HTML_PATH} ({len(html):,} characters) ...\n")

    # --- structure -----------------------------------------------------------
    parser = TagAuditor().feed(html)
    check(
        "balanced tags",
        not parser.errors and not parser.stack,
        "; ".join(parser.errors) or (f"still open: {','.join(parser.stack)}" if parser.stack else ""),
    )

    unprefixed_classes = sorted(c for c in parser.classes if not c.startswith("hpx-"))
    check("every class hpx-prefixed", not unprefixed_classes, ", ".join(unprefixed_classes))

    unprefixed_ids = sorted(i for i in parser.ids if not i.startswith("hpx-"))
    check("every id hpx-prefixed", not unprefixed_ids, ", ".join(unprefixed_ids))

    # --- external requests -----------------------------------------------------
    external_urls = re.findall(r'(?:href|src)\s*=\s*["\'](https?://[^"\']+)["\']', html)
    bad_hosts = sorted({u.split("/")[2] for u in external_urls} - ALLOWED_EXTERNAL_HOSTS)
    check("no external requests beyond Google Fonts", not bad_hosts, ", ".join(bad_hosts))

    font_stylesheet_links = [
        u for u in external_urls
        if u.startswith("https://fonts.googleapis.com")
    ]
    check(
        "exactly one Google Fonts stylesheet link",
        len(font_stylesheet_links) == 1,
        f"found {len(font_stylesheet_links)}: {font_stylesheet_links}",
    )

    all_absolute_urls = re.findall(r'https?://[^\s"\'<>)]+', html)
    non_font_urls = [u for u in all_absolute_urls if not u.startswith(tuple(f"https://{h}" for h in ALLOWED_EXTERNAL_HOSTS))]
    check("no other absolute URLs anywhere in the file", not non_font_urls, ", ".join(non_font_urls[:10]))

    # --- everything else inlined (no fetch/XHR, no external src=) -----------
    script_blocks = re.findall(r"<script\b[^>]*>(.*?)</script>", html, re.S)
    js_text = "\n".join(script_blocks)
    network_calls = re.findall(r"\b(fetch\s*\(|XMLHttpRequest|\.ajax\s*\()", js_text)
    check("no fetch/XHR network calls in inline script", not network_calls, ", ".join(sorted(set(network_calls))))

    src_values = re.findall(r'\bsrc\s*=\s*["\']([^"\']+)["\']', html)
    external_src = [s for s in src_values if s.startswith(("http://", "https://")) and not s.startswith("data:")]
    check("no src= attribute points outside the file (data: URIs only)", not external_src, ", ".join(external_src))

    # --- embedded JSON integrity -----------------------------------------------
    m = SCRIPT_JSON_RE.search(html)
    embedded_ok = False
    embedded_matches = False
    presence_detail = ""
    match_detail = ""
    if m:
        try:
            embedded_data = json.loads(m.group(1))
            embedded_ok = True
            embedded_matches = embedded_data == expected_data
            if not embedded_matches:
                match_detail = "parsed but does not match interactive/_data.json exactly"
        except json.JSONDecodeError as exc:
            presence_detail = f"could not parse as JSON: {exc}"
    else:
        presence_detail = 'no <script type="application/json" id="hpx-data"> block found'
    check('embedded <script id="hpx-data"> present and parses', bool(m) and embedded_ok, presence_detail)
    check("embedded JSON matches interactive/_data.json exactly", embedded_ok and embedded_matches, match_detail)

    # --- typography -------------------------------------------------------------
    visible_text = "".join(parser.text)
    check("typographic apostrophes in prose (no straight ')", "'" not in visible_text)
    check("spaced en-dashes, no em-dashes in prose", "—" not in visible_text)
    # Numeric ranges (9,500–9,999.99) keep the unspaced en-dash -- standard
    # British typography; only a LETTER run against an en-dash is a violation.
    unspaced_en_dash = re.search(r"[^\W\d_]–|–[^\W\d_]", visible_text)
    check("en-dashes are spaced ( – ), not run against adjoining letters (digit ranges allowed)", unspaced_en_dash is None,
          f"found near: ...{visible_text[max(0, (unspaced_en_dash.start() if unspaced_en_dash else 0) - 15):(unspaced_en_dash.end() if unspaced_en_dash else 0) + 15]}..." if unspaced_en_dash else "")

    found_american = sorted({
        w for w in AMERICAN_SPELLING_SPOTLIST
        if re.search(rf"\b{re.escape(w)}\b", visible_text, re.IGNORECASE)
    })
    check("British-spellings spot-check (no American forms from the spot-list)",
          not found_american, ", ".join(found_american))

    # --- honesty line -------------------------------------------------------------
    honesty_present = (
        re.search(r"synthetic", visible_text, re.IGNORECASE) is not None
        and re.search(r"answer key", visible_text, re.IGNORECASE) is not None
    )
    check('honesty line present ("synthetic" + "answer key" in visible text)', honesty_present)

    # --- embeddability: postMessage height, reduced motion, responsive -----------
    check("postMessage height reporting present", "postMessage" in html and "hpx-height" in html)
    check("prefers-reduced-motion media query present", "prefers-reduced-motion" in html)
    check('viewport meta present', 'name="viewport"' in html)
    small_screen_media_query = re.search(r"@media[^{]*max-width\s*:\s*(\d+)px", html)
    has_small_breakpoint = bool(small_screen_media_query) and int(small_screen_media_query.group(1)) <= 420
    check("at least one responsive media query at <=420px", has_small_breakpoint,
          f"tightest max-width found: {small_screen_media_query.group(1)}px" if small_screen_media_query else "none found")

    print()
    if failures:
        print(f"FAILED ({len(failures)}): {failures}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 -- QA gate must report, never crash bare
        print(f"\nFATAL: {exc}")
        sys.exit(1)
