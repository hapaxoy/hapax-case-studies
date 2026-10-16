"""Build the self-contained interactive page: inject interactive/_data.json
into interactive/_template.html at the __HPX_DATA__ placeholder.

Deterministic; the output is
interactive/contract-review.html — one file, all CSS/JS/data inlined,
Google Fonts the only external request.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
TEMPLATE = PROJECT / "interactive" / "_template.html"
DATA = PROJECT / "interactive" / "_data.json"
OUT = PROJECT / "interactive" / "contract-review.html"


def main() -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    data = json.loads(DATA.read_text(encoding="utf-8"))
    blob = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    # </script> inside a JS string would close the script tag mid-page
    blob = blob.replace("</", "<\\/")
    if template.count("__HPX_DATA__") != 1:
        raise SystemExit("template must contain exactly one __HPX_DATA__ placeholder")
    OUT.write_text(template.replace("__HPX_DATA__", blob), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size/1024:.1f} KB)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
