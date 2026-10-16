"""
verify_interactive.py -- QA gate for the interactive page, checking the
page's embeddability constraints.

Checks: balanced tags, single external request (Google Fonts only), hpx- class
prefix discipline, no control characters or straight apostrophes in prose, the
data payload injected, responsive viewport meta, no fixed pixel heights on
layout containers, and that key page numbers match evaluation.json.

Usage: python verify_interactive.py    (exit 1 on any failure)
"""

import sys
import re
import json
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "interactive" / "erp-cleanup.html"
issues = []

t = PAGE.read_text(encoding="utf-8")
head, _, body_js = t.partition("<script>")

# 1. control characters (the corpus text legitimately contains no control chars
#    besides \n; form feeds were stripped by taking page 1 only)
if re.search("[\x00-\x08\x0b\x0c\x0e-\x1f]", t):
    issues.append("control characters present")

# 2. straight apostrophes in prose (markup/JS excluded: check only text between
#    > and < in the pre-script part, skipping attribute values)
for m in re.finditer(r">([^<>]+)<", head):
    if re.search(r"[A-Za-z]'[A-Za-z]", m.group(1)):
        issues.append(f"straight apostrophe in prose: {m.group(1)[:60]!r}")

# 3. balanced tags (prose part only; SVG elements are created in JS)
for tag in ["div", "section", "p", "header", "footer", "span", "table", "thead",
            "tbody", "tr", "th", "button", "h1", "h2", "svg", "style", "script"]:
    o = len(re.findall(f"<{tag}[ >]", t))
    c = t.count(f"</{tag}>")
    if o != c:
        issues.append(f"<{tag}> open={o} close={c}")

# 4. external requests: exactly one, the Google Fonts stylesheet
ext = re.findall(r'(?:href|src)="(https?://[^"]+)"', t)
if ext != ["https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,400;1,500&family=Geist+Mono:wght@400;500&display=swap"]:
    issues.append(f"external requests: {ext}")
if re.search(r"\b(fetch|XMLHttpRequest|WebSocket)\s*\(", body_js):
    issues.append("network call in page JS")

# 5. class prefix discipline: every class attribute token starts with hpx-
for m in re.finditer(r'class="([^"]+)"', t):
    for cls in m.group(1).split():
        if not cls.startswith("hpx-"):
            issues.append(f"unprefixed class: {cls}")

# 6. data payload injected
if "/*__DATA__*/null" in t:
    issues.append("data payload NOT injected (template marker still present)")
m = re.search(r"const HPX = (\{.*?\});\n", t, re.S)
data = None
if not m:
    issues.append("could not locate injected HPX data")
else:
    data = json.loads(m.group(1))
    if len(data["docs"]) != 240:
        issues.append(f"docs in payload: {len(data['docs'])} != 240")
    if len(data["activations"]) != 5:
        issues.append(f"activations in payload: {len(data['activations'])} != 5")

# 7. page numbers match evaluation.json
ev = json.loads((ROOT / "data" / "runs" / "evaluation.json").read_text(encoding="utf-8"))
if data:
    want_share = f"{ev['summary']['deterministic_share'] * 100:.1f}%"
    if data["summary"]["det_share_pct"] != want_share:
        issues.append(f"det share mismatch: page {data['summary']['det_share_pct']} vs eval {want_share}")
    last = ev["docs"][-1]
    if abs(data["docs"][-1]["cf"] - round(last["cum_cf_usd_est"], 2)) > 0.01:
        issues.append("final counterfactual cumulative differs from evaluation.json")

# 8. responsiveness basics
if '<meta name="viewport"' not in t:
    issues.append("viewport meta missing")
if "max-width:960px" not in t:
    issues.append("wrap max-width missing")
for bad in re.findall(r"(?<!max-)(?<!-)height\s*:\s*\d{3,}px", t):
    issues.append(f"fixed large height: {bad}")

# 9. estimate labelling present near cost content
if t.count("estimate") < 3:
    issues.append("estimate labels look missing")

print("\n".join(issues) if issues else f"ALL CHECKS PASSED ({PAGE.stat().st_size / 1024:.0f} KB)")
sys.exit(1 if issues else 0)
