"""build_page.py -- inlines _data.json into _template.html to produce skills-library.html.

Follows the house pattern (09 Training Outcomes: build_data.py builds the JSON,
a second step inlines it into the template).

Run from this directory (Python 3.10 or later, standard library only):
    python build_page.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "_template.html"
DATA_JSON = HERE / "_data.json"
OUTPUT = HERE / "skills-library.html"

PLACEHOLDER = "/*__HPX_DATA_JSON__*/"
SIZE_BUDGET_KB = 2048  # 2 MB budget for the self-contained page


def main() -> int:
    if not TEMPLATE.exists():
        print(f"[build_page] FATAL: {TEMPLATE} not found", file=sys.stderr)
        return 1
    if not DATA_JSON.exists():
        print(f"[build_page] FATAL: {DATA_JSON} not found", file=sys.stderr)
        return 1

    template = TEMPLATE.read_text(encoding="utf-8")
    data = DATA_JSON.read_text(encoding="utf-8")

    if PLACEHOLDER not in template:
        print(f"[build_page] FATAL: template is missing the {PLACEHOLDER} placeholder",
              file=sys.stderr)
        return 1

    # Guard against script injection in the inlined JSON
    if "</script" in data.lower():
        data = data.replace("</script", r"<\/script")

    html = template.replace(PLACEHOLDER, data)

    # Safety: never overwrite the template
    if OUTPUT.resolve() == TEMPLATE.resolve():
        print("[build_page] FATAL: output path equals template path", file=sys.stderr)
        return 1

    OUTPUT.write_text(html, encoding="utf-8")
    size_kb = OUTPUT.stat().st_size / 1024
    print(f"[build_page] wrote {OUTPUT.name} ({size_kb:.1f} KB)")
    if size_kb > SIZE_BUDGET_KB:
        print(f"[build_page] WARNING: page is {size_kb:.1f} KB, over the {SIZE_BUDGET_KB} KB budget")
    return 0


if __name__ == "__main__":
    sys.exit(main())
