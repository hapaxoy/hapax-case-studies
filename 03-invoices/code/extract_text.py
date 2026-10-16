"""Produce text-layer dumps for overseer agents (and anyone else).

For each PDF in data/documents/, writes to data/runs/text_layers/:
  <doc_id>.txt    — pdfplumber extract_text() per page, pages separated by a marker
  <doc_id>.words.json — per page, extract_words() with coordinates (rounded to 0.1pt)

These dumps are derived from the public corpus only — no answer-key access.
Run from anywhere; paths resolve relative to this file.
"""
from __future__ import annotations

import json
from pathlib import Path

import pdfplumber

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent / "data" / "documents"
OUT = HERE.parent / "data" / "runs" / "text_layers"


def dump(pdf_path: Path) -> None:
    doc_id = pdf_path.stem
    pages_text: list[str] = []
    pages_words: list[list[dict]] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            pages_text.append(page.extract_text() or "")
            pages_words.append([
                {"text": w["text"], "x0": round(w["x0"], 1), "x1": round(w["x1"], 1),
                 "top": round(w["top"], 1), "bottom": round(w["bottom"], 1)}
                for w in page.extract_words()
            ])
    (OUT / f"{doc_id}.txt").write_text(
        ("\n\n==== PAGE BREAK ====\n\n").join(pages_text), encoding="utf-8")
    (OUT / f"{doc_id}.words.json").write_text(
        json.dumps(pages_words, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(DOCS.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"no PDFs found in {DOCS}")
    for i, p in enumerate(pdfs, 1):
        dump(p)
        if i % 25 == 0 or i == len(pdfs):
            print(f"{i}/{len(pdfs)} dumped", flush=True)


if __name__ == "__main__":
    main()
