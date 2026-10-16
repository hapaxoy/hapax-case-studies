"""QA gate for interactive/invoice-processing.html. Exits 1 on failure.

Checks: self-containment (single external request = Google Fonts), hpx- class
prefix discipline, balanced key tags, embedded-JSON integrity, numbers match
evaluation.json, estimate labels present, typography rules (no em-dashes or
straight apostrophes in prose), lang/viewport/reduced-motion/height-reporting,
no large fixed pixel heights.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGE = HERE.parent / "interactive" / "invoice-processing.html"
EVAL = HERE.parent / "data" / "runs" / "evaluation.json"

html = PAGE.read_text(encoding="utf-8")
ev = json.loads(EVAL.read_text(encoding="utf-8"))
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)


# 1. single external request (fonts), nothing else external
externals = re.findall(r'(?:href|src)="(https?://[^"]+)"', html)
check("single external request (Google Fonts only)",
      len(externals) == 1 and "fonts.googleapis.com" in externals[0], str(externals))
check("no external fetch/XHR", "fetch(" not in html and "XMLHttpRequest" not in html)

# 2. class prefix discipline
classes = set()
for m in re.findall(r'class="([^"]+)"', html):
    classes.update(m.split())
bad = {c for c in classes if not c.startswith("hpx-")}
check("hpx- prefix on every class", not bad, str(sorted(bad)[:8]))

# 3. balanced tags (structural)
for tag in ("div", "section", "table", "svg", "script", "style"):
    n_open = len(re.findall(rf"<{tag}[\s>]", html))
    n_close = html.count(f"</{tag}>")
    check(f"balanced <{tag}>", n_open == n_close, f"{n_open} open vs {n_close} close")

# 4. embedded JSON parses and matches evaluation
m = re.search(r"var DATA = (\{.*?\});\n", html, re.S)
check("embedded DATA found", m is not None)
if m:
    data = json.loads(m.group(1))
    acc = ev["accuracy"]
    check("fields match evaluation", data["tiles"]["fields"] == acc["overall"]["fields"])
    check("wrong-value count matches", data["tiles"]["wrong"] == acc["overall"]["wrong_including_s"])
    check("llm parse count matches", data["tiles"]["llm_parses"] == acc["llm"]["docs"])
    ce = ev["cost_estimates_block"]["cost_estimates"]
    check("hybrid central matches", data["costs"]["hybrid_central"] == ce["hybrid"]["central_85_15_usd"])
    check("counterfactual central matches", data["costs"]["cf_central"] == ce["counterfactual_all_llm"]["central_85_15_usd"])
    check("stream length 198", len(data["stream"]) == 198)
    check("deterministic docs 117", sum(1 for r in data["stream"] if r["p"] == "d") == 117)
    check("nine parser births, one re-learn",
          len(data["births"]) == 9 and sum(b["relearn"] for b in data["births"]) == 1)

# 5. estimate labelling near costs
check("estimate labels present", html.count("hpx-est") >= 3 and "ESTIMATES" in html)

# 6. typography in prose (exclude script/style bodies)
prose = re.sub(r"<script>.*?</script>", "", html, flags=re.S)
prose = re.sub(r"<style>.*?</style>", "", prose, flags=re.S)
text_only = re.sub(r"<[^>]+>", " ", prose)
check("no em-dashes in prose (house en-dash rule)", "—" not in text_only)
words = re.findall(r"[A-Za-z]'[A-Za-z]", text_only)
check("no straight apostrophes in prose", not words, str(words[:6]))

# 7. head / a11y / embedding
check("lang=en-GB", 'lang="en-GB"' in html)
check("viewport meta", 'name="viewport"' in html)
check("reduced-motion respected", "prefers-reduced-motion" in html)
check("iframe height reporting", "postMessage" in html and "hpxHeight" in html)
check("aria labels on charts", html.count("aria-label") >= 4)

# 8. no large fixed pixel heights (breaks iframe embedding); max-height is fine
fixed = [h for h in re.findall(r"[^-]height\s*:\s*(\d+)px", html) if int(h) > 60]
check("no large fixed heights", not fixed, str(fixed[:6]))

print()
if failures:
    print(f"FAILED: {len(failures)} check(s): {failures}")
    sys.exit(1)
print(f"ALL CHECKS PASS ({PAGE.stat().st_size/1024:.1f} KB, self-contained)")
