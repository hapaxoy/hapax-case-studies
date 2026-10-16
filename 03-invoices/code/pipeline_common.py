"""Shared, answer-key-free helpers for the pipeline scripts.

Used by ``regression_gate.py`` and ``router.py`` (both forbidden from reading ``data/answer_key/``, and
``router.py`` additionally forbidden from importing ``config.py``).
``evaluate.py`` also reuses the parser-loading and doc-id helpers below for
its own re-scoring pass; that is safe because this module itself never opens
``data/answer_key`` and never imports ``config``.

Contents: doc_id parsing, dynamic parser loading, induction-manifest path
resolution, and the master-data "existence checks" shared verbatim between
the activation-gate dry run and the router replay so the two scripts can
never silently diverge on what "a deterministic parse is good enough to use"
means.

Stdlib + local ``schemas`` only.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import schemas

# Repeat-supplier ids per config.py REPEAT_SUPPLIER_ORDER.
# Duplicated as a small literal here (not imported from config.py) so this
# module -- and anything built on it -- carries no config dependency.
REPEAT_SUPPLIER_IDS = {f"s{i}" for i in range(1, 9)}


class ParserLayoutError(Exception):
    """Fallback sentinel used only when a loaded parser module does not
    define its own ParserLayoutError (defensive; every real generated
    parser is required by the overseer instructions to define one)."""


# ---------------------------------------------------------------------------
# doc_id / filename conventions
# ---------------------------------------------------------------------------

def doc_supplier_slug(doc_id: str) -> str:
    """The supplier slug embedded in a doc_id: ``YYYY-MM_<slug>_NN``.

    For repeat suppliers the slug is the bare supplier id ("s1".."s8"); for
    one-off suppliers it is the hyphenated roster key (e.g.
    "kalibrointi-aho"). The slug is stable across a supplier's whole year
    even when its layout changes (S8's redesign keeps doc_ids on "s8").
    """
    parts = doc_id.split("_")
    if len(parts) < 3:
        raise ValueError(f"doc_id does not match YYYY-MM_<slug>_NN: {doc_id!r}")
    return parts[1]


def is_repeat_supplier(slug: str) -> bool:
    return slug in REPEAT_SUPPLIER_IDS


def supplier_id_for_slug(slug: str) -> str:
    """Map a doc_id slug to its master-data supplier id.

    Repeat suppliers: identity ("s1".."s8"). One-off slugs are hyphenated
    where master-data ids use underscores, and a supplier's second visit
    carries a "-2" roster suffix that is part of the document naming, not of
    the legal identity ("kuriiripalvelu-nopsa-2" -> "kuriiripalvelu_nopsa").
    """
    if slug in REPEAT_SUPPLIER_IDS:
        return slug
    sid = slug.replace("-", "_")
    if sid.endswith("_2"):
        sid = sid[:-2]
    return sid


# ---------------------------------------------------------------------------
# Dynamic parser loading
# ---------------------------------------------------------------------------

def load_parser_module(path: Path, slug: str):
    """Import a generated parser file as a fresh module object.

    A fresh module per call avoids any risk of state leaking between
    documents (the parsers are required to be pure, but this costs nothing
    and removes the need to trust that).
    """
    spec = importlib.util.spec_from_file_location(f"parser_{slug}_{id(path)}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load parser module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_path(raw: str, base_dirs: list[Path]) -> Path:
    """Resolve a path string recorded in an induction manifest.

    The pipeline pins the manifest's *keys* (doc_ids / parse_paths /
    pdf_paths) but not whether the path values are absolute or relative to
    some root, since the manifests are written at dispatch
    time and do not exist yet. This tries, in order: the raw string as an
    absolute or CWD-relative path, then each candidate base directory in
    turn. Raises FileNotFoundError with the full candidate list if none
    resolve, so a bad manifest fails loudly rather than silently.
    """
    p = Path(raw)
    if p.exists():
        return p
    tried = [str(p)]
    for base in base_dirs:
        candidate = base / raw
        tried.append(str(candidate))
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"cannot resolve path {raw!r}; tried: {tried}")


# ---------------------------------------------------------------------------
# Master data
# ---------------------------------------------------------------------------

def load_master_data(path: Path) -> dict:
    """Load data/master_data.json and index suppliers by id.

    Adds a private "_suppliers_by_id" index; does not mutate the file.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"master data not found at {path} -- run export_master_data.py first")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["_suppliers_by_id"] = {s["id"]: s for s in data.get("suppliers", [])}
    return data


def existence_checks(record: dict, doc_slug: str, master_data: dict) -> list[str]:
    """Master-data existence checks: supplier identity fields match the master data;
    po_number, when present, exists in the PO register for that supplier;
    iban/bankgiro belongs to that supplier.

    Deliberately NOT checked: line-level reconciliation of quantities and
    prices against the PO's contents (the three-way match is the production
    recommendation this case study argues for, not part of this router).

    Returns a list of problem strings; empty means all checks pass.
    """
    problems: list[str] = []
    suppliers_by_id = master_data.get("_suppliers_by_id") or {
        s["id"]: s for s in master_data.get("suppliers", [])}
    supplier_id = supplier_id_for_slug(doc_slug)
    master_supplier = suppliers_by_id.get(supplier_id)
    if master_supplier is None:
        return [f"supplier {doc_slug!r} (id {supplier_id!r}) unknown to master data"]

    rec_supplier = record.get("supplier", {}) if isinstance(record, dict) else {}
    for field in ("name", "street", "postcode", "city", "country", "vat_id", "business_id"):
        if rec_supplier.get(field) != master_supplier.get(field):
            problems.append(
                f"supplier.{field} mismatch: parsed={rec_supplier.get(field)!r} "
                f"master={master_supplier.get(field)!r}")

    invoice = record.get("invoice", {}) if isinstance(record, dict) else {}
    po_number = invoice.get("po_number")
    if po_number:
        matches = [po for po in master_data.get("po_register", [])
                   if po.get("po_number") == po_number and po.get("supplier_id") == supplier_id]
        if not matches:
            problems.append(f"po_number {po_number!r} not found in PO register for {supplier_id!r}")

    bank = record.get("bank", {}) if isinstance(record, dict) else {}
    if bank.get("iban") and bank["iban"] != master_supplier.get("iban"):
        problems.append(f"iban {bank['iban']!r} does not belong to {doc_slug!r}")
    if bank.get("bankgiro") and bank["bankgiro"] != master_supplier.get("bankgiro"):
        problems.append(f"bankgiro {bank['bankgiro']!r} does not belong to {doc_slug!r}")

    return problems


# ---------------------------------------------------------------------------
# One shared "run a parser and classify what happened" primitive
# ---------------------------------------------------------------------------

def classify_parse_attempt(parser_module, pdf_path: Path, doc_slug: str, master_data: dict):
    """Run parser_module.parse(pdf_path) and classify the outcome.

    Returns (outcome, detail, record_or_None) where outcome is one of
    "OK", "LAYOUT-ERROR", "VALIDATION-FAIL". Any exception other than the
    parser's own ParserLayoutError is ALSO treated as LAYOUT-ERROR (a parser
    that crashes is not a parser that silently guessed -- both are "does not
    trust this document"), but its real type is reported in the detail
    string.
    """
    layout_error_cls = getattr(parser_module, "ParserLayoutError", ParserLayoutError)
    try:
        record = parser_module.parse(str(pdf_path))
    except layout_error_cls as e:
        return "LAYOUT-ERROR", f"ParserLayoutError: {e}", None
    except Exception as e:  # noqa: BLE001 -- deliberate: fail-loud posture
        return "LAYOUT-ERROR", f"UNEXPECTED {type(e).__name__}: {e}", None

    schema_errors = schemas.validate_record(record)
    if schema_errors:
        return "VALIDATION-FAIL", f"schema: {schema_errors[0]}", record

    problems = existence_checks(record, doc_slug, master_data)
    if problems:
        return "VALIDATION-FAIL", f"existence: {problems[0]}", record

    return "OK", "", record


# ---------------------------------------------------------------------------
# Test-fixture helpers (selftest use only -- NOT part of the production
# pipeline surface). Mirrors config.py's identifier-construction algorithms
# without importing config, so selftest fixtures stay config-free too.
# ---------------------------------------------------------------------------

def make_test_iban(country_code: str, bban: str) -> str:
    rearranged = bban + country_code + "00"
    digits = "".join(str(int(c, 36)) for c in rearranged)
    check = 98 - (int(digits) % 97)
    return f"{country_code}{check:02d}{bban}"
