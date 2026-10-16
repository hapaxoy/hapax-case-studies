"""Inline interactive/_data.json into interactive/board-reporting.html.

Replaces the __HPX_DATA__ placeholder (or, on re-runs, the previously inlined
JSON between the data-script markers) so the page stays a single self-contained
file.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "interactive" / "board-reporting.html"
DATA = ROOT / "interactive" / "_data.json"

payload = json.dumps(json.loads(DATA.read_text(encoding="utf-8")),
                     separators=(",", ":"), ensure_ascii=False)
# guard: the payload lives inside a <script> block — forbid a closing tag inside it
assert "</script" not in payload.lower()

html = HTML.read_text(encoding="utf-8")
pattern = re.compile(
    r'(<script id="hpx-data" type="application/json">).*?(</script>)', re.S)
new_html, n = pattern.subn(lambda m: m.group(1) + payload + m.group(2), html)
assert n == 1, f"expected exactly one data script block, found {n}"
HTML.write_text(new_html, encoding="utf-8")
print(f"inlined {len(payload):,} bytes of JSON into {HTML.name}")
