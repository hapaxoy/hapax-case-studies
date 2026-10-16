"""Corpus step 2 — derive the answer key for Project 4 (Contract Clause
Extraction), bound to the schema in schemas.py.

For each of the 150 contracts selected by prepare_corpus.py, this script
reads the corresponding row of data/master_clauses.csv and derives one
JSON record per contract under data/answer_key/, using schemas.CATEGORIES
as the single definition of which columns matter and how "present" is
decided.

This is the ONLY script (besides validate_corpus.py's determinism check,
which re-runs it) that touches master_clauses.csv's clause/answer columns.
The pipeline's model-facing agents and generated matchers are never given
this file's path — that is the isolation rule validate_corpus.py checks.

Run standalone: `python derive_answer_key.py` (needs prepare_corpus.py's
outputs already in data/). Exits 0 on success, 1 on any hard failure.
"""

from __future__ import annotations

import ast
import json
import sys
from collections import defaultdict
from pathlib import Path

import schemas

CODE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CODE_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
ANSWER_KEY_DIR = DATA_DIR / "answer_key"
MANIFEST_PATH = DATA_DIR / "manifest.json"


def fail(message: str) -> None:
    print(f"\nERROR: {message}", file=sys.stderr)
    sys.exit(1)


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        fail(f"{MANIFEST_PATH} not found — run prepare_corpus.py first.")
    with open(MANIFEST_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def load_master_clauses_rows(csv_path: Path) -> dict[str, dict]:
    """Filename -> row dict, using the stdlib csv module (no pandas needed
    for a flat lookup by key)."""
    import csv
    if not csv_path.exists():
        fail(f"{csv_path} not found — run prepare_corpus.py first.")
    with open(csv_path, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    by_filename = {row["Filename"]: row for row in rows}
    if len(by_filename) != len(rows):
        fail("master_clauses.csv has duplicate Filename values — cannot key by filename safely")
    return by_filename


def parse_span_list(raw: str | None, *, source_row: str, column: str) -> list[str]:
    """Parse a CUAD clause column (a Python-list-like string of verbatim
    quotes) via ast.literal_eval, guarded. Never eval(). Fails loud, naming
    the offending row/column, on any parse failure — this is a key-quality
    problem worth stopping for, not a silent skip."""
    text = raw if raw is not None else ""
    if not text.strip():
        return []
    try:
        value = ast.literal_eval(text)
    except (ValueError, SyntaxError) as exc:
        fail(f"could not parse clause column as a Python literal.\n"
             f"  row (Filename)={source_row!r}\n  column={column!r}\n"
             f"  raw value={text!r}\n  error={exc}")
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        fail(f"clause column did not parse to a list of strings.\n"
             f"  row (Filename)={source_row!r}\n  column={column!r}\n"
             f"  parsed value={value!r}")
    return value


def derive_yesno_entry(spans: list[str], answer_raw: str | None) -> dict:
    """present = answer strip-casefold == 'yes'; empty/No both -> False.
    answer stays None (yes/no categories carry no normalised answer).
    If spans exist despite a non-Yes answer, flag it for a
    sanity check (the validator watches this count too)."""
    normalised_answer = (answer_raw or "").strip().casefold()
    present = normalised_answer == "yes"
    entry = {"present": present, "spans": spans, "answer": None}
    if spans and not present:
        entry["key_note"] = "spans-without-yes"
    return entry


def derive_extraction_entry(spans: list[str], answer_raw: str | None) -> dict:
    """present = non-blank answer OR non-empty spans. answer is stored
    verbatim (comparison normalisation is schemas' job, at compare time —
    this file stores exactly what CUAD wrote, including a blank string
    when the answer column itself was blank but a span was annotated)."""
    answer_text = answer_raw if answer_raw is not None else ""
    present = bool(answer_text.strip()) or bool(spans)
    return {"present": present, "spans": spans, "answer": answer_text}


def derive_record(contract_txt_name: str, source_row_filename: str, csv_row: dict) -> dict:
    categories: dict[str, dict] = {}
    for cat in schemas.CATEGORIES:
        name = cat["name"]
        csv_column = cat["csv"]
        answer_column = f"{csv_column}-Answer"
        if csv_column not in csv_row or answer_column not in csv_row:
            fail(f"expected columns not found in master_clauses.csv: "
                 f"{csv_column!r} / {answer_column!r} (contract {contract_txt_name!r})")
        spans = parse_span_list(csv_row[csv_column], source_row=source_row_filename, column=csv_column)
        answer_raw = csv_row[answer_column]
        if cat["kind"] == "yesno":
            categories[name] = derive_yesno_entry(spans, answer_raw)
        else:
            categories[name] = derive_extraction_entry(spans, answer_raw)
    return {
        "contract": contract_txt_name,
        "source_row": source_row_filename,
        "categories": categories,
    }


def write_record(record: dict, *, output_dir: Path = ANSWER_KEY_DIR) -> Path:
    stem = record["contract"]
    if stem.lower().endswith(".txt"):
        stem = stem[: -len(".txt")]
    out_path = output_dir / f"{stem}.json"
    text = json.dumps(record, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
    out_path.write_text(text, encoding="utf-8")
    return out_path


def derive_all(output_dir: Path, *, manifest: dict | None = None,
               csv_rows_by_filename: dict[str, dict] | None = None) -> dict:
    """Core derivation loop, factored out so validate_corpus.py's
    determinism check (rule 9) can re-run exactly this logic into a
    scratch directory and byte-compare the result against data/answer_key/
    without re-invoking this file as a subprocess. Returns a stats dict;
    writes one JSON record per selected contract into output_dir.
    """
    if manifest is None:
        manifest = load_manifest()
    if csv_rows_by_filename is None:
        csv_filename = manifest["selection"]["csv_filename"]
        csv_rows_by_filename = load_master_clauses_rows(DATA_DIR / csv_filename)

    stream_entries = manifest["selection"]["stream"]
    holdout_entries = manifest["selection"]["holdout"]

    output_dir.mkdir(parents=True, exist_ok=True)

    presence_counts = {"stream": defaultdict(int), "holdout": defaultdict(int)}
    spans_without_yes_counts: dict[str, int] = defaultdict(int)
    soft_validation_notes: list[str] = []
    written_paths: list[Path] = []

    for split_name, entries in (("stream", stream_entries), ("holdout", holdout_entries)):
        for entry in entries:
            contract = entry["contract"]
            source_row_filename = entry["source_row"]
            csv_row = csv_rows_by_filename.get(source_row_filename)
            if csv_row is None:
                fail(f"selected contract {contract!r} (source_row {source_row_filename!r}) "
                     f"not found in the clause-annotation CSV by Filename")

            record = derive_record(contract, source_row_filename, csv_row)

            # Structural self-check. Missing categories are a hard fail;
            # anything else is printed, not failed (by design —
            # key records may legitimately carry an unparseable/blank
            # verbatim answer, since they ARE the key).
            errors = schemas.validate_record(record)
            hard_errors = [e for e in errors if e.startswith("missing category")]
            soft_errors = [e for e in errors if not e.startswith("missing category")]
            if hard_errors:
                fail(f"{contract}: missing categories in the derived record: {hard_errors}")
            for e in soft_errors:
                soft_validation_notes.append(f"{contract}: {e}")

            for name, cat_entry in record["categories"].items():
                if cat_entry["present"]:
                    presence_counts[split_name][name] += 1
                if cat_entry.get("key_note") == "spans-without-yes":
                    spans_without_yes_counts[name] += 1

            written_paths.append(write_record(record, output_dir=output_dir))

    return {
        "presence_counts": presence_counts,
        "spans_without_yes_counts": spans_without_yes_counts,
        "soft_validation_notes": soft_validation_notes,
        "written_paths": written_paths,
    }


def main() -> None:
    # House rule: this script never touches the CUAD cache at all (it reads
    # only the already-copied data/ outputs), so there is no read/write
    # path collision to guard against beyond the obvious.
    assert ANSWER_KEY_DIR.resolve() != DATA_DIR.resolve()

    print("=== Loading manifest and clause-annotation CSV ===")
    manifest = load_manifest()
    csv_filename = manifest["selection"]["csv_filename"]
    csv_rows_by_filename = load_master_clauses_rows(DATA_DIR / csv_filename)
    print(f"CSV rows indexed by Filename: {len(csv_rows_by_filename)}")
    print(f"Stream: {len(manifest['selection']['stream'])}   "
          f"Holdout: {len(manifest['selection']['holdout'])}")

    stats = derive_all(ANSWER_KEY_DIR, manifest=manifest, csv_rows_by_filename=csv_rows_by_filename)

    print(f"\nWrote {len(stats['written_paths'])} answer-key records to {ANSWER_KEY_DIR}")

    soft_validation_notes = stats["soft_validation_notes"]
    if soft_validation_notes:
        print(f"\n=== validate_record structural notes (printed, not failed): {len(soft_validation_notes)} ===")
        for note in soft_validation_notes:
            print(f"  {note}")
    else:
        print("\nvalidate_record: no structural notes on any of the 150 records.")

    presence_counts = stats["presence_counts"]
    print("\n=== Per-category presence counts (stream / holdout, out of 50 / 100) ===")
    for cat in schemas.CATEGORIES:
        name = cat["name"]
        s = presence_counts["stream"][name]
        h = presence_counts["holdout"][name]
        print(f"  {name:28s} kind={cat['kind']:10s} stream={s:3d}/50   holdout={h:4d}/100")

    spans_without_yes_counts = stats["spans_without_yes_counts"]
    total_spans_without_yes = sum(spans_without_yes_counts.values())
    print(f"\n=== 'spans-without-yes' counts (yes/no categories, span present but answer not Yes): "
          f"{total_spans_without_yes} total ===")
    if spans_without_yes_counts:
        for name, count in sorted(spans_without_yes_counts.items()):
            print(f"  {name:28s} {count}")
    else:
        print("  none")

    print("\nderive_answer_key.py completed successfully.")


if __name__ == "__main__":
    # cp1252 console guard (corpus filenames contain combining marks)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    main()
