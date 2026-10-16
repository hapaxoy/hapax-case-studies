"""router.py -- Replays the 198-document invoice stream through the hybrid
pipeline in stream order.

The router NEVER reads the answer key and NEVER imports config.py (which
also knows the planted events). Its inputs are exactly what a real deployment would have:
    - the PDFs in data/documents/ (the corpus itself, replayed in date
      order -- see "Determining stream order" below),
    - the recorded LLM parses in data/runs/llm_parses/, standing in for
      live LLM calls already commissioned,
    - the generated parsers in code/parsers_generated/, each with an
      induction manifest that pins exactly which documents its birth was
      conditioned on,
    - data/master_data.json -- "what a real AP system knows": supplier
      identity and the PO register, nothing about classes or events.

Determining stream order: the true issue_date is not encoded in a
document's filename (only its month and a within-month sequence number
are), so it has to be read off a parse of the document itself. For each
doc_id this script takes the issue_date from the accepted LLM parse in
data/runs/llm_parses/ when one exists, or otherwise from running whichever
generated parser can structurally parse that document (regardless of
whether that parser is "live" yet -- liveness only gates which result is
USED for the routing decision, not whether a date can be read off the
page). When both sources exist they are expected to agree (same document,
same field); a mismatch is logged as a warning. A document with NEITHER
source is a consistency failure: the corpus
could not actually have been processed by this pipeline, and the script
exits non-zero rather than guessing an order.

Overseer trigger: a parser
is born immediately after the LAST document (by stream order) listed in its
own induction manifest. This script does not recompute "the 6th accepted
LLM parse of a pair" from first principles -- the induction manifest, written
at dispatch time, already IS that set, for however many
generations of parser a supplier has had (S8's redesign is not a special
case: its v2 parser is simply a second parser file whose induction doc_ids
happen to start after the cutover).

Per document, in stream order: try each LIVE parser for its supplier,
newest (latest birth) first. A parser "succeeds" when parse() returns
without ParserLayoutError AND the record passes schemas.validate_record AND
the master-data existence checks (pipeline_common.existence_checks).
Deliberately NOT checked here: line-level reconciliation of quantities and
prices against the PO's contents (the three-way match is
the production recommendation this case study argues for, not part of this
router). If no live parser succeeds, the document takes the LLM path using
its recorded parse.

Output: data/runs/stream_events.json -- one event per document in stream
order, plus parser-birth events. Class labels (R/O/T/F/S) are deliberately
absent; evaluate.py joins them in from the answer key.

Usage:
    python router.py                 # real run
    python router.py --selftest      # exercises the same replay logic on
                                      # tiny synthetic fixtures in a temp
                                      # dir; no real corpus, parsers, LLM
                                      # parses or master data needed

Exit code: non-zero if the final consistency check fails (the set of
documents ending on an LLM path does not equal the set of parse files that
exist), or if any document could not be dated at all.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pipeline_common as pc

HERE = Path(__file__).resolve().parent
PARSERS_DIR = HERE / "parsers_generated"
PROJECT_ROOT = HERE.parent
DATA_DIR = PROJECT_ROOT / "data"
DOCS_DIR = DATA_DIR / "documents"
LLM_PARSES_DIR = DATA_DIR / "runs" / "llm_parses"
MASTER_DATA_PATH = DATA_DIR / "master_data.json"
OUT_PATH = DATA_DIR / "runs" / "stream_events.json"

EXPECTED_DOCUMENT_COUNT = 198


# ---------------------------------------------------------------------------
# Parser registry: one entry per parser_<slug>.py with a usable manifest.
# ---------------------------------------------------------------------------

def discover_parsers(parsers_dir: Path) -> list[dict]:
    """Load every parser_<slug>.py that has an induction manifest naming a
    single, consistent supplier. Mirrors regression_gate.discover_parsers
    (duplicated rather than imported to keep the two scripts' failure modes
    independent -- a bug in one script's discovery should not silently
    change the other's)."""
    entries = []
    for py_path in sorted(parsers_dir.glob("parser_*.py")):
        slug = py_path.stem[len("parser_"):]
        manifest_path = parsers_dir / f"parser_{slug}.induction.json"
        if not manifest_path.exists():
            print(f"  WARNING: {py_path.name} has no induction manifest; skipping", flush=True)
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"  WARNING: {manifest_path.name} is not readable/valid JSON ({e}); skipping", flush=True)
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
            print(f"  WARNING: {manifest_path.name} spans multiple suppliers; skipping", flush=True)
            continue
        try:
            module = pc.load_parser_module(py_path, slug)
        except Exception as e:
            print(f"  WARNING: {py_path.name} failed to import ({type(e).__name__}: {e}); skipping", flush=True)
            continue
        entries.append({
            "slug": slug, "py_path": py_path, "supplier": next(iter(slugs_seen)),
            "induction_doc_ids": list(doc_ids), "module": module,
        })
    return entries


# ---------------------------------------------------------------------------
# Pass 1 -- resolve an issue_date (and cache any successful raw parse) for
# every document, so the full stream can be sorted before it is replayed.
# ---------------------------------------------------------------------------

def _resolve_stream_dates_impl(doc_ids: list[str], docs_dir: Path, parsers: list[dict],
                                llm_dir: Path) -> tuple[dict[str, str], dict, list[str]]:
    parsers_by_supplier: dict[str, list[dict]] = {}
    for p in parsers:
        parsers_by_supplier.setdefault(p["supplier"], []).append(p)

    issue_date_by_doc: dict[str, str] = {}
    parse_cache: dict[tuple[str, str], dict] = {}
    unresolved: list[str] = []

    for doc_id in doc_ids:
        slug = pc.doc_supplier_slug(doc_id)
        pdf_path = docs_dir / f"{doc_id}.pdf"
        parser_date = None
        for candidate in parsers_by_supplier.get(slug, []):
            try:
                record = candidate["module"].parse(str(pdf_path))
            except Exception:
                continue
            parse_cache[(doc_id, candidate["slug"])] = record
            date = record.get("invoice", {}).get("issue_date")
            if date:
                parser_date = date
                break  # any structurally-successful parser's date is as good as another's

        llm_date = None
        llm_path = llm_dir / f"{doc_id}.json"
        if llm_path.exists():
            try:
                llm_record = json.loads(llm_path.read_text(encoding="utf-8"))
                llm_date = llm_record.get("invoice", {}).get("issue_date")
            except (OSError, json.JSONDecodeError) as e:
                print(f"  WARNING: cannot read {llm_path}: {e}", flush=True)

        if parser_date and llm_date and parser_date != llm_date:
            print(f"  WARNING: {doc_id}: parser-derived issue_date {parser_date!r} "
                  f"disagrees with recorded LLM parse {llm_date!r}", flush=True)

        date = parser_date or llm_date
        if date is None:
            unresolved.append(doc_id)
        else:
            issue_date_by_doc[doc_id] = date

    return issue_date_by_doc, parse_cache, unresolved


# ---------------------------------------------------------------------------
# Parser birth positions, derived from induction manifests + stream order
# ---------------------------------------------------------------------------

def compute_birth_indices(parsers: list[dict], stream_order: list[str]) -> dict[str, int]:
    """For each parser, the 0-based index in stream_order of the LAST of its
    induction doc_ids. The parser is live for documents at index > this."""
    position = {doc_id: i for i, doc_id in enumerate(stream_order)}
    births = {}
    for p in parsers:
        indices = [position[d] for d in p["induction_doc_ids"] if d in position]
        missing = [d for d in p["induction_doc_ids"] if d not in position]
        if missing:
            print(f"  WARNING: parser_{p['slug']}: induction doc_id(s) not found in the "
                  f"corpus: {missing}", flush=True)
        if not indices:
            births[p["slug"]] = None
            continue
        births[p["slug"]] = max(indices)
    return births


# ---------------------------------------------------------------------------
# Pass 2 -- the actual replay
# ---------------------------------------------------------------------------

def replay(doc_ids_sorted: list[str], docs_dir: Path, parsers: list[dict], birth_index: dict[str, int],
           parse_cache: dict, llm_dir: Path, master_data: dict) -> list[dict]:
    parsers_by_supplier: dict[str, list[dict]] = {}
    for p in parsers:
        parsers_by_supplier.setdefault(p["supplier"], []).append(p)

    events: list[dict] = []
    births_emitted: set[str] = set()

    for idx, doc_id in enumerate(doc_ids_sorted):
        slug = pc.doc_supplier_slug(doc_id)
        pdf_path = docs_dir / f"{doc_id}.pdf"

        candidates = [p for p in parsers_by_supplier.get(slug, [])
                      if birth_index.get(p["slug"]) is not None and idx > birth_index[p["slug"]]]
        candidates.sort(key=lambda p: birth_index[p["slug"]], reverse=True)  # newest-first

        attempts = []
        parser_used = None
        for cand in candidates:
            if (doc_id, cand["slug"]) in parse_cache:
                record = parse_cache[(doc_id, cand["slug"])]
                outcome, detail = _classify_cached(record)
            else:
                outcome, detail, record = pc.classify_parse_attempt(
                    cand["module"], pdf_path, slug, master_data)
            attempts.append({"parser": cand["slug"], "outcome": outcome, "detail": detail})
            if outcome == "OK":
                parser_used = cand["slug"]
                break

        event = {"idx": idx, "doc_id": doc_id, "date": None, "supplier": slug, "attempts": attempts}
        # date is filled in by the caller (it already has issue_date_by_doc);
        # kept as a separate dict update to avoid threading one more param
        # through this function's signature.

        if parser_used is not None:
            event["path"] = "deterministic"
            event["parser_used"] = parser_used
        elif candidates:
            event["path"] = "llm-fallback"
            event["parser_used"] = None
        elif pc.is_repeat_supplier(slug):
            event["path"] = "llm-discovery"
            event["parser_used"] = None
        else:
            event["path"] = "llm-oneoff"
            event["parser_used"] = None

        if event["path"] != "deterministic":
            llm_path = llm_dir / f"{doc_id}.json"
            event["llm_parse_missing"] = not llm_path.exists()

        events.append(event)

        for p in parsers_by_supplier.get(slug, []):
            if p["slug"] in births_emitted:
                continue
            bi = birth_index.get(p["slug"])
            if bi is not None and bi == idx:
                births_emitted.add(p["slug"])
                events.append({
                    "event": "parser_born", "parser": p["slug"], "supplier": p["supplier"],
                    "after_doc_id": doc_id, "stream_index": idx,
                    "induction_doc_count": len(p["induction_doc_ids"]),
                    "note": "born immediately after the last document in its induction manifest",
                })

    return events


def _classify_cached(record: dict) -> tuple[str, str]:
    """Re-validate a record already computed in Pass 1 without re-parsing."""
    errors = schemas_module().validate_record(record)
    if errors:
        return "VALIDATION-FAIL", f"schema: {errors[0]}"
    return "OK", ""


_schemas_module = None


def schemas_module():
    global _schemas_module
    if _schemas_module is None:
        import schemas as s
        _schemas_module = s
    return _schemas_module


# ---------------------------------------------------------------------------
# Consistency check
# ---------------------------------------------------------------------------

def check_consistency(events: list[dict], llm_dir: Path) -> list[str]:
    """The set of documents that end on an LLM path must equal the set of
    parse files that exist. Returns a list of problem strings (empty ==
    consistent)."""
    problems = []
    doc_events = [e for e in events if "doc_id" in e]
    llm_path_docs = {e["doc_id"] for e in doc_events if e["path"].startswith("llm")}
    existing_files = {p.stem for p in llm_dir.glob("*.json")} if llm_dir.exists() else set()

    missing = sorted(llm_path_docs - existing_files)
    extra = sorted(existing_files - llm_path_docs)
    if missing:
        problems.append(f"{len(missing)} document(s) need an LLM parse that does not exist: {missing}")
    if extra:
        problems.append(f"{len(extra)} LLM parse file(s) exist for documents that did not "
                         f"need the LLM path: {extra}")
    return problems


# ---------------------------------------------------------------------------
# Real run
# ---------------------------------------------------------------------------

def run_real(docs_dir: Path, parsers_dir: Path, llm_dir: Path, master_data_path: Path,
             out_path: Path) -> int:
    doc_ids = sorted(p.stem for p in docs_dir.glob("*.pdf"))
    if not doc_ids:
        print(f"FATAL: no documents found in {docs_dir}", flush=True)
        return 1
    print(f"Found {len(doc_ids)} document(s) in {docs_dir}"
          + ("" if len(doc_ids) == EXPECTED_DOCUMENT_COUNT else
             f"  (WARNING: expected {EXPECTED_DOCUMENT_COUNT})"), flush=True)

    try:
        master_data = pc.load_master_data(master_data_path)
    except (FileNotFoundError, OSError, json.JSONDecodeError) as e:
        print(f"FATAL: cannot load master data: {e}", flush=True)
        return 1

    parsers = discover_parsers(parsers_dir) if parsers_dir.exists() else []
    print(f"Found {len(parsers)} generated parser(s): {[p['slug'] for p in parsers]}", flush=True)

    print("Pass 1 -- resolving stream order (issue_date per document)...", flush=True)
    issue_date_by_doc, parse_cache, unresolved = _resolve_stream_dates_impl(
        doc_ids, docs_dir, parsers, llm_dir)
    if unresolved:
        print(f"FATAL: {len(unresolved)} document(s) have neither a recorded LLM parse nor a "
              f"successful deterministic parse -- cannot determine stream order (consistency "
              f"failure): {unresolved}", flush=True)
        return 1

    stream_order = sorted(doc_ids, key=lambda d: (issue_date_by_doc[d], d))
    birth_index = compute_birth_indices(parsers, stream_order)
    for p in parsers:
        if birth_index.get(p["slug"]) is None:
            print(f"  WARNING: parser_{p['slug']} never becomes live (no resolvable "
                  f"induction doc_ids in this stream)", flush=True)

    print("Pass 2 -- replaying the stream...", flush=True)
    events = replay(stream_order, docs_dir, parsers, birth_index, parse_cache, llm_dir, master_data)
    for e in events:
        if "doc_id" in e:
            e["date"] = issue_date_by_doc[e["doc_id"]]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(events, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Events written to {out_path}", flush=True)

    doc_events = [e for e in events if "doc_id" in e]
    from collections import Counter
    path_counts = Counter(e["path"] for e in doc_events)
    print("\nPath counts:", flush=True)
    for path, n in sorted(path_counts.items()):
        print(f"  {path:16} {n:>4}", flush=True)
    births = [e for e in events if e.get("event") == "parser_born"]
    print(f"\nParser births: {len(births)}", flush=True)
    for b in births:
        print(f"  parser_{b['parser']} (supplier {b['supplier']}) born after {b['after_doc_id']} "
              f"(stream index {b['stream_index']}, {b['induction_doc_count']} induction docs)", flush=True)

    missing_llm = [e["doc_id"] for e in doc_events if e.get("llm_parse_missing")]
    problems = check_consistency(events, llm_dir)
    if missing_llm:
        print(f"\nDocuments missing a required LLM parse: {missing_llm}", flush=True)
    if problems:
        print("\nCONSISTENCY CHECK FAILED:", flush=True)
        for pr in problems:
            print(f"  {pr}", flush=True)
        return 1

    print("\nConsistency check: PASS (LLM-path documents == existing LLM parse files)", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true",
                     help="run the self-test on synthetic fixtures instead of the real corpus")
    args = ap.parse_args()

    if args.selftest:
        return run_selftest()

    return run_real(DOCS_DIR, PARSERS_DIR, LLM_PARSES_DIR, MASTER_DATA_PATH, OUT_PATH)


# ---------------------------------------------------------------------------
# Self-test: a tiny synthetic supplier population exercising discovery,
# deterministic routing, template-redesign fallback + re-learning, a
# one-off, and both flavours of the consistency-check failure.
# ---------------------------------------------------------------------------

def _write_fake_parser(path: Path, accepts_prefix: str) -> None:
    """A fake parser that succeeds only on pdf 'documents' (really JSON
    fixtures) whose declared layout == accepts_prefix; raises
    ParserLayoutError otherwise. Values are read straight from the fixture
    JSON, so no pdfplumber or real PDF is needed."""
    path.write_text(f'''"""Fake generated parser for router.py --selftest (layout={accepts_prefix!r})."""
import json


class ParserLayoutError(Exception):
    pass


def parse(pdf_path):
    data = json.loads(open(pdf_path, encoding="utf-8").read())
    if data.get("layout") != {accepts_prefix!r}:
        raise ParserLayoutError("layout landmark mismatch")
    return data["record"]
''', encoding="utf-8")


def _selftest_record(supplier_id: str, iban: str, doc_id: str, issue_date: str, number: str) -> dict:
    import schemas
    return {
        "schema_version": "1.0", "doc_id": doc_id,
        "supplier": {"name": f"Selftest {supplier_id} Oy", "street": "Testikatu 1",
                      "postcode": "00100", "city": "Helsinki", "country": "FI",
                      "vat_id": "FI22334455", "business_id": "9811228-8"},
        "buyer": {"name": "Pyökkipaja Oy", "street": "Esimerkkikatu 11",
                   "postcode": "15520", "city": "Lahti", "country": "FI",
                   "vat_id": None, "business_id": schemas.make_y_tunnus("2417551")},
        "invoice": {"number": number, "type": "invoice", "issue_date": issue_date,
                     "supply_date": None, "due_date": "2025-04-09", "payment_terms": 30,
                     "currency": "EUR", "po_number": None,
                     "reference_type": "viitenumero", "reference_value": schemas.make_viitenumero("10150001"),
                     "original_invoice_number": None, "reverse_charge_mention": None},
        "bank": {"iban": iban, "bic": "KALTFIHH"},
        "lines": [{"description": "Widget", "quantity": "10", "unit": "kpl",
                    "unit_price": "5.00", "vat_rate": "25.5", "line_total": "50.00"}],
        "vat_summary": [{"rate": "25.5", "base": "50.00", "amount": "12.75"}],
        "totals": {"net": "50.00", "vat": "12.75", "gross": "62.75"},
    }


def run_selftest() -> int:
    print("=== router.py --selftest ===", flush=True)
    ok_all = True

    with tempfile.TemporaryDirectory(prefix="hapax_router_selftest_") as tmp:
        tmp_path = Path(tmp)
        docs_dir = tmp_path / "data" / "documents"
        parsers_dir = tmp_path / "code" / "parsers_generated"
        llm_dir = tmp_path / "data" / "runs" / "llm_parses"
        for d in (docs_dir, parsers_dir, llm_dir):
            d.mkdir(parents=True)

        iban = pc.make_test_iban("FI", "95783022011184")
        master_data = {
            "suppliers": [
                {"id": "s1", "name": "Selftest s1 Oy", "street": "Testikatu 1",
                 "postcode": "00100", "city": "Helsinki", "country": "FI",
                 "vat_id": "FI22334455", "business_id": "9811228-8",
                 "iban": iban, "bic": "KALTFIHH", "bankgiro": None},
            ],
            "po_register": [],
        }
        master_data["_suppliers_by_id"] = {s["id"]: s for s in master_data["suppliers"]}
        (tmp_path / "data" / "master_data.json").parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "data" / "master_data.json").write_text(json.dumps(master_data), encoding="utf-8")

        # -- build a small s1 stream: 6 discovery docs (v1 layout), then 2
        # deterministic v1 docs, then 6 "redesign" fallback docs (v2 layout,
        # v1 parser fails), then 2 deterministic v2 docs. Plus one one-off
        # document that never gets a parser. 17 documents total.
        doc_specs = []  # (doc_id, date, layout, number)
        n = 0
        for i in range(6):
            n += 1
            doc_specs.append((f"2025-{1 + i:02d}_s1_01", f"2025-{1 + i:02d}-10", "v1", f"{1000 + n}"))
        for i in range(2):
            n += 1
            doc_specs.append((f"2025-{7 + i:02d}_s1_01", f"2025-{7 + i:02d}-10", "v1", f"{1000 + n}"))
        for i in range(6):
            n += 1
            doc_specs.append((f"2025-09_s1_{i + 2:02d}", f"2025-09-{11 + i:02d}", "v2", f"{2000 + n}"))
        for i in range(2):
            n += 1
            doc_specs.append((f"2025-10_s1_{i + 2:02d}", f"2025-10-{11 + i:02d}", "v2", f"{2000 + n}"))
        oneoff_doc = ("2025-01_acme-oneoff_01", "2025-01-05", "oneoff", "ONE-1")

        for doc_id, date, layout, number in doc_specs:
            record = _selftest_record("s1", iban, doc_id, date, number)
            (docs_dir / f"{doc_id}.pdf").write_text(
                json.dumps({"layout": layout, "record": record}), encoding="utf-8")
        record = _selftest_record("acme-oneoff", iban, oneoff_doc[0], oneoff_doc[1], oneoff_doc[3])
        (docs_dir / f"{oneoff_doc[0]}.pdf").write_text(
            json.dumps({"layout": oneoff_doc[2], "record": record}), encoding="utf-8")

        # -- parsers: v1 (induced from the first 6), v2 (induced from the
        # 6 post-redesign fallback docs) --
        v1_induction = [d[0] for d in doc_specs[:6]]
        v2_induction = [d[0] for d in doc_specs[8:14]]
        _write_fake_parser(parsers_dir / "parser_s1.py", "v1")
        (parsers_dir / "parser_s1.induction.json").write_text(
            json.dumps({"doc_ids": v1_induction}), encoding="utf-8")
        _write_fake_parser(parsers_dir / "parser_s1v2.py", "v2")
        (parsers_dir / "parser_s1v2.induction.json").write_text(
            json.dumps({"doc_ids": v2_induction}), encoding="utf-8")

        # -- recorded LLM parses: discovery (6) + redesign-fallback (6) +
        # the one-off (1) = 13 files, matching what the replay should need --
        needs_llm = v1_induction + v2_induction + [oneoff_doc[0]]
        by_doc_id = {d[0]: d for d in doc_specs}
        by_doc_id[oneoff_doc[0]] = oneoff_doc
        for doc_id in needs_llm:
            d = by_doc_id[doc_id]
            record = _selftest_record(pc.doc_supplier_slug(doc_id), iban, d[0], d[1], d[3])
            (llm_dir / f"{doc_id}.json").write_text(json.dumps(record), encoding="utf-8")

        out_path = tmp_path / "data" / "runs" / "stream_events.json"
        rc = run_real(docs_dir, parsers_dir, llm_dir, tmp_path / "data" / "master_data.json", out_path)
        print(f"  [A] full replay exit code: {rc} (expect 0)", flush=True)
        ok_all &= (rc == 0)

        events = json.loads(out_path.read_text(encoding="utf-8"))
        doc_events = [e for e in events if "doc_id" in e]
        path_counts = {}
        for e in doc_events:
            path_counts[e["path"]] = path_counts.get(e["path"], 0) + 1
        expected = {"llm-discovery": 6, "deterministic": 4, "llm-fallback": 6, "llm-oneoff": 1}
        check = path_counts == expected
        print(f"  [A] path counts: {path_counts} (expect {expected}): {'PASS' if check else 'FAIL'}", flush=True)
        ok_all &= check

        births = [e for e in events if e.get("event") == "parser_born"]
        check_births = (len(births) == 2 and {b["parser"] for b in births} == {"s1", "s1v2"})
        print(f"  [A] parser births: {[b['parser'] for b in births]} "
              f"(expect s1 then s1v2): {'PASS' if check_births else 'FAIL'}", flush=True)
        ok_all &= check_births
        ordered_correctly = births and births[0]["parser"] == "s1" and births[-1]["parser"] == "s1v2"
        ok_all &= bool(ordered_correctly)

        # -- scenario B: delete one required LLM parse -> consistency failure --
        missing_target = llm_dir / f"{v1_induction[0]}.json"
        saved = missing_target.read_text(encoding="utf-8")
        missing_target.unlink()
        out_path_b = tmp_path / "data" / "runs" / "stream_events_b.json"
        rc_b = run_real(docs_dir, parsers_dir, llm_dir, tmp_path / "data" / "master_data.json", out_path_b)
        print(f"  [B] replay with a missing required LLM parse, exit code: {rc_b} (expect 1)", flush=True)
        ok_all &= (rc_b == 1)
        missing_target.write_text(saved, encoding="utf-8")

        # -- scenario C: an orphan LLM parse file for a doc that ends up
        # deterministic -> consistency failure the other direction --
        orphan_doc = doc_specs[6][0]  # a post-discovery, pre-redesign deterministic v1 doc
        orphan_record = _selftest_record("s1", iban, orphan_doc, doc_specs[6][1], doc_specs[6][3])
        (llm_dir / f"{orphan_doc}.json").write_text(json.dumps(orphan_record), encoding="utf-8")
        out_path_c = tmp_path / "data" / "runs" / "stream_events_c.json"
        rc_c = run_real(docs_dir, parsers_dir, llm_dir, tmp_path / "data" / "master_data.json", out_path_c)
        print(f"  [C] replay with an orphan LLM parse file, exit code: {rc_c} (expect 1)", flush=True)
        ok_all &= (rc_c == 1)
        (llm_dir / f"{orphan_doc}.json").unlink()

        # -- scenario D: a document with neither a parser nor an LLM parse
        # -> unresolved stream order -> exit 1 before any replay --
        ghost_doc = "2025-01_s1_99"
        (docs_dir / f"{ghost_doc}.pdf").write_text(json.dumps({"layout": "unknown", "record": {}}), encoding="utf-8")
        out_path_d = tmp_path / "data" / "runs" / "stream_events_d.json"
        rc_d = run_real(docs_dir, parsers_dir, llm_dir, tmp_path / "data" / "master_data.json", out_path_d)
        print(f"  [D] replay with an undatable document, exit code: {rc_d} (expect 1)", flush=True)
        ok_all &= (rc_d == 1)
        (docs_dir / f"{ghost_doc}.pdf").unlink()

    print(f"\nSelftest overall: {'PASS' if ok_all else 'FAIL'}", flush=True)
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
