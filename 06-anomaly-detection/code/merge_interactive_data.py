"""merge_interactive_data.py -- inline interactive/_data.json into the page.

Replaces the __HPX_DATA__ placeholder in interactive/anomaly-detection.html
with the verbatim contents of interactive/_data.json (the 05 convention:
build_interactive_data.py distils and asserts; this script only injects).
Idempotent: if the placeholder is absent, it re-injects between the
<script type="application/json" id="hpx-data"> tags.
"""
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
INTERACTIVE = SCRIPT_DIR.parent / "interactive"
PAGE = INTERACTIVE / "anomaly-detection.html"
DATA = INTERACTIVE / "_data.json"

def main():
    data_text = DATA.read_text(encoding="utf-8").strip()
    json.loads(data_text)  # must parse
    html = PAGE.read_text(encoding="utf-8")

    if "__HPX_DATA__" in html:
        html = html.replace("__HPX_DATA__", data_text)
    else:
        pattern = re.compile(
            r'(<script type="application/json" id="hpx-data">).*?(</script>)',
            re.DOTALL,
        )
        if not pattern.search(html):
            print("FATAL: no hpx-data block found in the page")
            sys.exit(1)
        html = pattern.sub(lambda m: m.group(1) + data_text + m.group(2), html, count=1)

    PAGE.write_text(html, encoding="utf-8", newline="\n")
    embedded = json.loads(re.search(
        r'<script type="application/json" id="hpx-data">(.*?)</script>',
        PAGE.read_text(encoding="utf-8"), re.DOTALL).group(1))
    assert embedded == json.loads(data_text), "embedded JSON does not match _data.json"
    print(f"Injected {DATA.name} ({len(data_text):,} bytes) into {PAGE.name}; parity verified.")

if __name__ == "__main__":
    main()
