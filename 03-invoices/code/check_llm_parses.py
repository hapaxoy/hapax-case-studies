"""Validation of LLM parse batches.

For every parse JSON in data/runs/llm_parses/:
  1. structural validity via schemas.validate_record (schema failures are
     pipeline events: the document would be re-queued with a logged retry);
  2. field-level accuracy vs the answer key via schemas.compare_records.

The S document is scored like any other: both paths are EXPECTED to read the
printed (transposed) values and therefore to be 'wrong' against the true
transaction on exactly two fields — that expected mismatch is reported
separately, not hidden in the accuracy total.

Usage:  python check_llm_parses.py [--json OUT]   (exit 1 on schema failure)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import schemas

HERE = Path(__file__).resolve().parent
PARSES = HERE.parent / "data" / "runs" / "llm_parses"
KEYS = HERE.parent / "data" / "answer_key"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="also write a machine-readable summary here")
    args = ap.parse_args()

    parse_files = sorted(PARSES.glob("*.json"))
    if not parse_files:
        raise SystemExit(f"no parses found in {PARSES}")

    total_fields = 0
    wrong_fields: list[dict] = []
    schema_failures: list[dict] = []
    s_expected_mismatches: list[dict] = []
    docs_perfect = 0

    for pf in parse_files:
        doc_id = pf.stem
        parsed = json.loads(pf.read_text(encoding="utf-8"))
        key_path = KEYS / f"{doc_id}.json"
        if not key_path.exists():
            print(f"FATAL: no answer key for {doc_id}", flush=True)
            sys.exit(1)
        wrapper = json.loads(key_path.read_text(encoding="utf-8"))
        truth = wrapper["record"]
        is_s = bool(wrapper.get("s_exception"))

        errs = schemas.validate_record(parsed)
        if errs:
            schema_failures.append({"doc_id": doc_id, "errors": errs})

        cmp = schemas.compare_records(parsed, truth)
        total_fields += cmp["total"]
        doc_wrong = []
        for path, got, want in cmp["wrong"]:
            item = {"doc_id": doc_id, "field": path, "parsed": got, "truth": want}
            if is_s and ("quantity" in path or "unit_price" in path):
                s_expected_mismatches.append(item)
            else:
                doc_wrong.append(item)
        wrong_fields.extend(doc_wrong)
        if not doc_wrong and not errs:
            docs_perfect += 1

    n = len(parse_files)
    acc = (total_fields - len(wrong_fields) - len(s_expected_mismatches)) / total_fields
    print(f"documents checked      : {n}", flush=True)
    print(f"schema-valid           : {n - len(schema_failures)}/{n}", flush=True)
    print(f"fields compared        : {total_fields}", flush=True)
    print(f"wrong fields (true err): {len(wrong_fields)}", flush=True)
    print(f"S-doc expected mismatch: {len(s_expected_mismatches)} (by design; not an extraction error)", flush=True)
    print(f"documents fully correct: {docs_perfect}/{n}", flush=True)
    print(f"field accuracy (excl. designed S mismatch): {acc:.6%}", flush=True)
    for w in wrong_fields:
        print(f"  WRONG {w['doc_id']} {w['field']}: parsed={w['parsed']!r} truth={w['truth']!r}", flush=True)
    for f in schema_failures:
        print(f"  SCHEMA-FAIL {f['doc_id']}: {f['errors'][:4]}", flush=True)

    if args.json:
        Path(args.json).write_text(json.dumps({
            "documents": n, "schema_failures": schema_failures,
            "fields_compared": total_fields, "wrong_fields": wrong_fields,
            "s_expected_mismatches": s_expected_mismatches,
            "documents_fully_correct": docs_perfect,
        }, ensure_ascii=False, indent=1), encoding="utf-8")

    sys.exit(1 if schema_failures else 0)


if __name__ == "__main__":
    main()
