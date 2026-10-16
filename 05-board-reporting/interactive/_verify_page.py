"""QA for interactive/board-reporting.html (site verify-script precedent).

Checks the embeddability constraints and the site's
typography conventions. Exits 1 on any failure.
"""
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

HTML_PATH = Path(__file__).resolve().parent / "board-reporting.html"
ALLOWED_HOSTS = {"fonts.googleapis.com", "fonts.gstatic.com"}
VOID = {"meta", "link", "br", "hr", "img", "input", "wbr", "source"}

failures = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(name)


html = HTML_PATH.read_text(encoding="utf-8")


class Auditor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.errors, self.classes, self.text = [], [], set(), []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append(tag)
        if tag in ("script", "style"):
            self._skip += 1
        for k, v in attrs:
            if k == "class" and v:
                self.classes.update(v.split())

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip -= 1
        if tag in VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"unbalanced </{tag}>")
        else:
            self.stack.pop()

    def handle_data(self, data):
        if self._skip == 0:
            self.text.append(data)


a = Auditor()
a.feed(html)
check("balanced tags", not a.errors and not a.stack, "; ".join(a.errors) or ("open: " + ",".join(a.stack) if a.stack else ""))

unprefixed = sorted(c for c in a.classes if not c.startswith("hpx-"))
check("all classes hpx-prefixed", not unprefixed, ", ".join(unprefixed))

urls = re.findall(r'(?:href|src)="(https?://[^"/]+)', html)
bad_hosts = sorted({u.split("//")[1] for u in urls} - ALLOWED_HOSTS)
check("no external requests beyond fonts", not bad_hosts, ", ".join(bad_hosts))
check("no other absolute URLs in markup",
      not re.findall(r'https?://(?!fonts\.)[^"\s<>]+', re.sub(r"<script.*?</script>", "", html, flags=re.S)))

check("no data placeholder left", "__HPX_DATA__" not in html)
m = re.search(r'<script id="hpx-data" type="application/json">(.*?)</script>', html, re.S)
data_ok = False
if m:
    try:
        d = json.loads(m.group(1))
        data_ok = len(d["months"]) == 24 and abs(d["anchors"]["growth_pct"] - 8.63) < 0.02
    except Exception as e:  # noqa: BLE001
        data_ok = False
check("embedded JSON parses with 24 months and correct growth anchor", bool(m) and data_ok)

visible = "".join(a.text)
check("no straight apostrophes in prose", "'" not in visible)
check("spaced en-dashes, no em-dashes in prose", "—" not in visible and " - " not in visible)
check('lang="en-GB"', 'lang="en-GB"' in html)
check("viewport meta present", 'name="viewport"' in html)
check("responsive svg (width:100%)", ".hpx-chart svg{width:100%" in html)
check("media query present", "@media (max-width" in html)
check("reduced-motion handled", "prefers-reduced-motion" in html)
check("postMessage height reporting", "hpx-height" in html)
fixed_heights = re.findall(r"[^-]height:\s*\d{3,}px", html)
check("no large fixed pixel heights", not fixed_heights, ", ".join(fixed_heights))

print()
if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("ALL CHECKS PASSED")
sys.exit(0)
