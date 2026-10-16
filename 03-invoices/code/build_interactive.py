"""Inject interactive/_data.json into the template -> interactive/invoice-processing.html.

Deterministic: same data + template -> same page bytes.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
INTER = HERE.parent / "interactive"

template = (INTER / "_template.html").read_text(encoding="utf-8")
data = (INTER / "_data.json").read_text(encoding="utf-8")
assert template.count("__DATA__") == 1, "template must contain exactly one __DATA__ placeholder"
page = template.replace("__DATA__", data)
out = INTER / "invoice-processing.html"
out.write_text(page, encoding="utf-8")
print(f"built {out.name}: {out.stat().st_size/1024:.1f} KB")
