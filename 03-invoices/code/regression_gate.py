"""regression_gate.py -- Activation gate + full-corpus dry run for the
generated deterministic invoice parsers.

Part 1 (the activation gate): each parser in code/parsers_generated/ must
exactly reproduce the accepted LLM parse on every document listed in its own
induction manifest (parser_<slug>.induction.json) -- regression against the
pipeline's OWN history, nothing else. A parser that fails to reproduce even
one of its induction documents is not fit to activate.

Part 2 (full-corpus dry run): each parser that has a manifest is then run
over every document belonging to its supplier (all layouts, all months) and
every outcome is classified OK / LAYOUT-ERROR / VALIDATION-FAIL. This is a
structural probe of parser robustness, not a scoring exercise: it never
compares to the answer key, and it never asks whether the OUTPUT is right,
only whether the parser is willing to hand it over.

No answer-key access anywhere in this script: it never opens
data/answer_key/ and imports nothing that does (schemas.py and
pipeline_common.py are both answer-key-free).

Usage:
    python regression_gate.py                 # real run over
                                                # code/parsers_generated/
    python regression_gate.py --selftest       # exercises the same logic on
                                                # tiny synthetic fixtures in a
                                                # temp dir; no real corpus,
                                                # parsers or master data
                                                # needed

Exit code: non-zero if any parser fails the Part 1 activation gate (or, in
--selftest mode, if the self-test assertions fail).
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pipeline_common as pc
import schemas

HERE = Path(__file__).resolve().parent
PARSERS_DIR = HERE / "parsers_generated"
PROJECT_ROOT = HERE.parent
DATA_DIR = PROJECT_ROOT / "data"
DOCS_DIR = DATA_DIR / "documents"
MASTER_DATA_PATH = DATA_DIR / "master_data.json"

OUTCOME_CLASSES = ("OK", "LAYOUT-ERROR", "VALIDATION-FAIL")


# ---------------------------------------------------------------------------
# Parser discovery
# ---------------------------------------------------------------------------

def discover_parsers(parsers_dir: Path) -> list[dict]:
    """Find every parser_<slug>.py with a matching induction manifest.

    Returns a list of {"slug", "py_path", "manifest_path", "manifest",
    "supplier"} dicts, sorted by slug. Parsers without a usable manifest are
    skipped with a printed warning rather than crashing the whole gate --
    a missing manifest is a dispatch-process bug worth surfacing, but it
    should not hide the state of every OTHER parser.
    """
    entries = []
    for py_path in sorted(parsers_dir.glob("parser_*.py")):
        slug = py_path.stem[len("parser_"):]
        manifest_path = parsers_dir / f"parser_{slug}.induction.json"
        if not manifest_path.exists():
            print(f"  WARNING: {py_path.name} has no induction manifest "
                  f"({manifest_path.name}); skipping", flush=True)
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"  WARNING: {manifest_path.name} is not valid JSON ({e}); skipping", flush=True)
            continue
        doc_ids = manifest.get("doc_ids") or []
        if not doc_ids:
            print(f"  WARNING: {manifest_path.name} has no doc_ids; skipping", flush=True)
            continue
        try:
            slugs_seen = {pc.doc_supplier_slug(d) for d in doc_ids}
        except ValueError as e:
            print(f"  WARNING: {manifest_path.name}: {e}; skipping", flush=True)
            continue
        if len(slugs_seen) != 1:
            print(f"  WARNING: {manifest_path.name} induction doc_ids span "
                  f"multiple suppliers {sorted(slugs_seen)}; skipping", flush=True)
            continue
        entries.append({
            "slug": slug, "py_path": py_path, "manifest_path": manifest_path,
            "manifest": manifest, "supplier": next(iter(slugs_seen)),
        })
    return entries


# ---------------------------------------------------------------------------
# Part 1 -- activation gate
# ---------------------------------------------------------------------------

def run_activation_gate(entry: dict, module, parsers_dir: Path, project_root: Path) -> tuple[bool, list[str]]:
    """Reproduce the accepted parse on every induction document, exactly.

    "Exactly" means dict equality of the whole record -- not
    schemas.compare_records' field-tolerant diff (this is a regression gate
    against the pipeline's own prior output, not a scoring pass).
    """
    manifest = entry["manifest"]
    doc_ids = manifest["doc_ids"]
    pdf_paths = manifest.get("pdf_paths") or [None] * len(doc_ids)
    parse_paths = manifest.get("parse_paths") or [None] * len(doc_ids)
    if len(pdf_paths) != len(doc_ids) or len(parse_paths) != len(doc_ids):
        return False, [f"manifest doc_ids/pdf_paths/parse_paths length mismatch "
                        f"({len(doc_ids)}/{len(pdf_paths)}/{len(parse_paths)})"]

    base_dirs = [parsers_dir, project_root, DATA_DIR]
    failures: list[str] = []

    for doc_id, raw_pdf, raw_parse in zip(doc_ids, pdf_paths, parse_paths):
        try:
            pdf_path = pc.resolve_path(raw_pdf, base_dirs) if raw_pdf else \
                pc.resolve_path(f"data/documents/{doc_id}.pdf", [project_root])
            parse_path = pc.resolve_path(raw_parse, base_dirs) if raw_parse else \
                pc.resolve_path(f"data/runs/llm_parses/{doc_id}.json", [project_root])
        except FileNotFoundError as e:
            failures.append(f"{doc_id}: {e}")
            continue

        try:
            accepted = json.loads(parse_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            failures.append(f"{doc_id}: cannot read accepted parse {parse_path}: {e}")
            continue

        try:
            got = module.parse(str(pdf_path))
        except Exception as e:
            failures.append(f"{doc_id}: raised {type(e).__name__}: {e}")
            continue

        if got != accepted:
            keys = set(got) | set(accepted) if isinstance(got, dict) and isinstance(accepted, dict) else set()
            diffs = sorted(k for k in keys if got.get(k) != accepted.get(k)) if keys else ["<non-dict output>"]
            failures.append(f"{doc_id}: mismatch in top-level field(s) {diffs}")

    return (not failures), failures


# ---------------------------------------------------------------------------
# Part 2 -- full-corpus dry run
# ---------------------------------------------------------------------------

def run_full_corpus_dry_run(entry: dict, module, docs_dir: Path, master_data: dict) -> dict:
    """Run the parser over every PDF belonging to its supplier and tabulate
    OK / LAYOUT-ERROR / VALIDATION-FAIL. No answer-key comparison."""
    supplier = entry["supplier"]
    outcomes: dict[str, list[str]] = {c: [] for c in OUTCOME_CLASSES}
    details = []
    pdfs = sorted(p for p in docs_dir.glob("*.pdf") if pc.doc_supplier_slug(p.stem) == supplier)
    for pdf_path in pdfs:
        outcome, detail, _record = pc.classify_parse_attempt(module, pdf_path, supplier, master_data)
        outcomes[outcome].append(pdf_path.stem)
        details.append({"doc_id": pdf_path.stem, "outcome": outcome, "detail": detail})
    return {"supplier": supplier, "total": len(pdfs), "outcomes": outcomes, "details": details}


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_report(gate_results: dict, dry_run_results: dict) -> bool:
    """Print the per-parser and per-class outcome tables. Returns True if
    any activation gate failed."""
    print("\n=== Part 1: activation gate (parser vs its own induction set) ===", flush=True)
    any_gate_failed = False
    for slug, (passed, failures) in gate_results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  parser_{slug}: {status}", flush=True)
        for f in failures:
            print(f"      {f}", flush=True)
        any_gate_failed |= not passed

    print("\n=== Part 2: full-corpus dry run -- per-parser outcome table ===", flush=True)
    print(f"  {'parser':<12} {'supplier':<10} {'docs':>5} {'OK':>5} "
          f"{'LAYOUT-ERROR':>13} {'VALIDATION-FAIL':>16}", flush=True)
    for slug, result in dry_run_results.items():
        o = result["outcomes"]
        print(f"  {('parser_' + slug):<12} {result['supplier']:<10} {result['total']:>5} "
              f"{len(o['OK']):>5} {len(o['LAYOUT-ERROR']):>13} {len(o['VALIDATION-FAIL']):>16}", flush=True)

    print("\n=== Part 2: full-corpus dry run -- per-class detail ===", flush=True)
    for slug, result in dry_run_results.items():
        for outcome_class in OUTCOME_CLASSES:
            docs = result["outcomes"][outcome_class]
            if docs:
                print(f"  parser_{slug} {outcome_class}: {docs}", flush=True)

    print(f"\nActivation gate overall: {'FAIL' if any_gate_failed else 'PASS'}", flush=True)
    return any_gate_failed


# ---------------------------------------------------------------------------
# Real run
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true",
                     help="run the self-test on synthetic fixtures instead of the real corpus")
    args = ap.parse_args()

    if args.selftest:
        return run_selftest()

    if not PARSERS_DIR.exists():
        print(f"no parser directory at {PARSERS_DIR}; nothing to gate (exit 0).", flush=True)
        return 0

    entries = discover_parsers(PARSERS_DIR)
    if not entries:
        print("no generated parsers with usable induction manifests found; nothing to gate (exit 0).", flush=True)
        return 0

    try:
        master_data = pc.load_master_data(MASTER_DATA_PATH)
    except (FileNotFoundError, OSError, json.JSONDecodeError) as e:
        print(f"FATAL: cannot load master data: {e}", flush=True)
        return 1
    print(f"Found {len(entries)} generated parser(s): {[e['slug'] for e in entries]}", flush=True)

    gate_results, dry_run_results = {}, {}
    for entry in entries:
        module = pc.load_parser_module(entry["py_path"], entry["slug"])
        gate_results[entry["slug"]] = run_activation_gate(entry, module, PARSERS_DIR, PROJECT_ROOT)
        dry_run_results[entry["slug"]] = run_full_corpus_dry_run(entry, module, DOCS_DIR, master_data)

    any_gate_failed = print_report(gate_results, dry_run_results)
    return 1 if any_gate_failed else 0


# ---------------------------------------------------------------------------
# Self-test: synthetic fixtures, no real corpus / parsers / master data
# ---------------------------------------------------------------------------

def _write_fake_parser(path: Path) -> None:
    """A tiny fake parser whose 'pdf' input is actually a JSON file (so the
    self-test needs neither pdfplumber nor a real PDF). Its behaviour is
    driven entirely by a "trigger" key in that JSON, so the self-test can
    force every outcome class deterministically."""
    path.write_text(
        '''"""Fake generated parser for regression_gate.py --selftest."""
import json


class ParserLayoutError(Exception):
    pass


def parse(pdf_path):
    data = json.loads(open(pdf_path, encoding="utf-8").read())
    trigger = data.get("trigger")
    if trigger == "layout_error":
        raise ParserLayoutError("landmark 'Rechnung' not found")
    if trigger == "boom":
        raise RuntimeError("unexpected crash")
    record = data["record"]
    if trigger == "bad_math":
        record = json.loads(json.dumps(record))
        record["totals"]["gross"] = "999999.99"
    if trigger == "bad_supplier":
        record = json.loads(json.dumps(record))
        record["supplier"]["vat_id"] = "FI99999999"
    return record
''', encoding="utf-8")


def _fixture_record(iban: str) -> dict:
    return {
        "schema_version": "1.0", "doc_id": "fixture",
        "supplier": {"name": "Selftest Supplier Oy", "street": "Testikatu 1",
                      "postcode": "00100", "city": "Helsinki", "country": "FI",
                      "vat_id": "FI22334455", "business_id": "9811228-8"},
        "buyer": {"name": "Pyökkipaja Oy", "street": "Esimerkkikatu 11",
                   "postcode": "15520", "city": "Lahti", "country": "FI",
                   "vat_id": None, "business_id": schemas.make_y_tunnus("2417551")},
        "invoice": {"number": "1001", "type": "invoice", "issue_date": "2025-03-10",
                     "supply_date": None, "due_date": "2025-04-09", "payment_terms": 30,
                     "currency": "EUR", "po_number": "PO-2025-001",
                     "reference_type": "viitenumero", "reference_value": schemas.make_viitenumero("10150001"),
                     "original_invoice_number": None, "reverse_charge_mention": None},
        "bank": {"iban": iban, "bic": "KALTFIHH"},
        "lines": [{"description": "Widget", "quantity": "10", "unit": "kpl",
                    "unit_price": "5.00", "vat_rate": "25.5", "line_total": "50.00"}],
        "vat_summary": [{"rate": "25.5", "base": "50.00", "amount": "12.75"}],
        "totals": {"net": "50.00", "vat": "12.75", "gross": "62.75"},
    }


def run_selftest() -> int:
    print("=== regression_gate.py --selftest ===", flush=True)
    ok_all = True

    with tempfile.TemporaryDirectory(prefix="hapax_regression_gate_selftest_") as tmp:
        tmp_path = Path(tmp)
        project_root = tmp_path
        data_dir = project_root / "data"
        docs_dir = data_dir / "documents"
        parsers_dir = project_root / "code" / "parsers_generated"
        docs_dir.mkdir(parents=True)
        parsers_dir.mkdir(parents=True)

        iban = pc.make_test_iban("FI", "95783022011184")
        assert schemas.iban_ok(iban)

        # -- fake parser + induction manifest, supplier slug "s1" --
        parser_path = parsers_dir / "parser_s1.py"
        _write_fake_parser(parser_path)

        good_record = _fixture_record(iban)
        induction_doc_ids = [f"2025-{i:02d}_s1_01" for i in range(1, 7)]

        # Six induction "documents" (JSON standing in for a PDF) + their
        # accepted parses. Doc 6 is the one the activation gate must catch
        # if the parser diverges -- exercised in the mismatch scenario below.
        for i, doc_id in enumerate(induction_doc_ids, start=1):
            (docs_dir / f"{doc_id}.pdf").write_text(
                json.dumps({"trigger": None, "record": {**good_record, "doc_id": doc_id}}),
                encoding="utf-8")
            (parsers_dir / f"{doc_id}.accepted.json").write_text(
                json.dumps({**good_record, "doc_id": doc_id}), encoding="utf-8")

        manifest = {
            "doc_ids": induction_doc_ids,
            "pdf_paths": [f"data/documents/{d}.pdf" for d in induction_doc_ids],
            "parse_paths": [f"code/parsers_generated/{d}.accepted.json" for d in induction_doc_ids],
        }
        (parsers_dir / "parser_s1.induction.json").write_text(json.dumps(manifest), encoding="utf-8")

        # -- extra full-corpus documents for the dry run (not in induction) --
        extra_docs = {
            "2025-07_s1_01": {"trigger": None},          # -> OK
            "2025-08_s1_01": {"trigger": "layout_error"},  # -> LAYOUT-ERROR
            "2025-08_s1_02": {"trigger": "boom"},          # -> LAYOUT-ERROR (unexpected type)
            "2025-09_s1_01": {"trigger": "bad_math"},      # -> VALIDATION-FAIL (schema)
            "2025-09_s1_02": {"trigger": "bad_supplier"},  # -> VALIDATION-FAIL (existence)
        }
        for doc_id, spec in extra_docs.items():
            payload = {**spec, "record": {**good_record, "doc_id": doc_id}}
            (docs_dir / f"{doc_id}.pdf").write_text(json.dumps(payload), encoding="utf-8")

        master_data = {
            "suppliers": [{"id": "s1", "name": "Selftest Supplier Oy", "street": "Testikatu 1",
                            "postcode": "00100", "city": "Helsinki", "country": "FI",
                            "vat_id": "FI22334455", "business_id": "9811228-8",
                            "iban": iban, "bic": "KALTFIHH", "bankgiro": None}],
            "po_register": [{"po_number": "PO-2025-001", "date": "2025-02-01", "supplier_id": "s1"}],
        }
        master_data["_suppliers_by_id"] = {s["id"]: s for s in master_data["suppliers"]}

        # ---- scenario A: parser reproduces induction set exactly -> PASS ----
        entries = discover_parsers(parsers_dir)
        assert len(entries) == 1, f"expected 1 discovered parser, got {len(entries)}"
        entry = entries[0]
        assert entry["supplier"] == "s1"

        module = pc.load_parser_module(entry["py_path"], entry["slug"])
        passed, failures = run_activation_gate(entry, module, parsers_dir, project_root)
        print(f"  [A] activation gate on matching parser: {'PASS' if passed else 'FAIL'} {failures}", flush=True)
        ok_all &= passed and not failures

        dry_run = run_full_corpus_dry_run(entry, module, docs_dir, master_data)
        o = dry_run["outcomes"]
        expected_ok = 6 + 1          # 6 induction docs + the one clean extra doc
        expected_layout_error = 2    # explicit ParserLayoutError + unexpected exception
        expected_validation_fail = 2  # bad_math + bad_supplier
        check = (len(o["OK"]) == expected_ok and len(o["LAYOUT-ERROR"]) == expected_layout_error
                 and len(o["VALIDATION-FAIL"]) == expected_validation_fail)
        print(f"  [A] dry run counts OK={len(o['OK'])} LAYOUT-ERROR={len(o['LAYOUT-ERROR'])} "
              f"VALIDATION-FAIL={len(o['VALIDATION-FAIL'])}: {'PASS' if check else 'FAIL'}", flush=True)
        ok_all &= check

        # ---- scenario B: parser diverges on one induction doc -> gate FAILs ----
        divergent_parser_path = parsers_dir / "parser_s1_divergent.py"
        divergent_parser_path.write_text(
            _write_divergent_source(), encoding="utf-8")
        divergent_module = pc.load_parser_module(divergent_parser_path, "s1_divergent")
        divergent_entry = {**entry, "py_path": divergent_parser_path, "slug": "s1_divergent"}
        passed2, failures2 = run_activation_gate(divergent_entry, divergent_module, parsers_dir, project_root)
        print(f"  [B] activation gate on divergent parser: {'PASS' if passed2 else 'FAIL'} "
              f"({len(failures2)} failing doc(s))", flush=True)
        ok_all &= (not passed2) and len(failures2) >= 1

        # ---- scenario C: missing induction manifest is skipped, not fatal ----
        (parsers_dir / "parser_orphan.py").write_text("def parse(pdf_path): return {}\n", encoding="utf-8")
        entries_with_orphan = discover_parsers(parsers_dir)
        slugs = {e["slug"] for e in entries_with_orphan}
        check_c = "orphan" not in slugs and "s1" in slugs
        print(f"  [C] orphan parser (no manifest) skipped cleanly: {'PASS' if check_c else 'FAIL'}", flush=True)
        ok_all &= check_c

    print(f"\nSelftest overall: {'PASS' if ok_all else 'FAIL'}", flush=True)
    return 0 if ok_all else 1


def _write_divergent_source() -> str:
    return '''"""Fake parser that returns a record differing from the accepted parse."""
import json


class ParserLayoutError(Exception):
    pass


def parse(pdf_path):
    data = json.loads(open(pdf_path, encoding="utf-8").read())
    record = json.loads(json.dumps(data["record"]))
    record["invoice"]["number"] = "WRONG-NUMBER"
    return record
'''


if __name__ == "__main__":
    sys.exit(main())
