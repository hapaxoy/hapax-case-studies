"""Validate the generated invoice-processing corpus against the ten coherence
rules. Exits 1 on any rule failure;
prints per-rule PASS/FAIL with the first few offending examples.

Reads data/answer_key/, data/documents/, data/manifest.json, and the
templates directory. Never used downstream of the answer key in the parsing
path -- this script is the one place answer_key/ is legitimately read back.

Usage: python validate_data.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import pdfplumber

import config
import formatting
import schemas

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
DATA_DIR = PROJECT_ROOT / "data"
ANSWER_KEY_DIR = DATA_DIR / "answer_key"
DOCS_DIR = DATA_DIR / "documents"
MANIFEST_PATH = DATA_DIR / "manifest.json"
TEMPLATES_DIR = HERE / "templates"

# Field leaves that are re-rendered via formatting.py rather than matched
# verbatim (money/date/quantity/rate all transform locale-to-locale).
DATE_FIELDS = {"issue_date", "due_date", "supply_date"}
MONEY_FIELDS = {"unit_price", "line_total", "base", "amount", "net", "vat", "gross"}
RATE_FIELDS = {"vat_rate", "rate"}
# Categorical/structural fields that are never printed as their raw schema
# code (country shows as a name or is omitted domestically; currency shows
# as a symbol; type/reference_type drive which localized word is printed) --
# excluded from the verbatim check by design, not by oversight.
EXCLUDED_FIELDS = {"country", "currency", "type", "reference_type"}

# fix 7: no rendered document may ever contain the literal standalone token
# "None" (a leaked null field) -- word-boundaried so it doesn't false-positive
# on a word that merely contains "none" as a substring.
NONE_TOKEN_RE = re.compile(r"\bNone\b")


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_answer_keys() -> dict[str, dict]:
    wrappers = {}
    for f in sorted(ANSWER_KEY_DIR.glob("*.json")):
        wrappers[f.stem] = json.loads(f.read_text(encoding="utf-8"))
    return wrappers


def build_identity_lookup() -> dict[str, dict]:
    """vat_id -> {'sid': short id or one-off root key, 'locale': ..., 'kind': 'repeat'/'oneoff'}"""
    lookup = {}
    for sid, sup in config.SUPPLIERS.items():
        lookup[sup["vat_id"]] = {"sid": sid, "locale": sup["locale"], "kind": "repeat"}
    for entry in config.ONE_OFFS:
        root = entry.get("same_supplier_as", entry["key"])
        lookup[entry["vat_id"]] = {"sid": root, "locale": entry["number_format"], "kind": "oneoff"}
    return lookup


IDENTITY = build_identity_lookup()


_PDF_CACHE: dict[str, tuple[str, int]] = {}


def pdf_text(doc_id: str) -> tuple[str, int]:
    """Return (concatenated text across all pages, page count). Cached --
    every rule that needs PDF content shares one pdfplumber pass per file."""
    if doc_id not in _PDF_CACHE:
        path = DOCS_DIR / f"{doc_id}.pdf"
        with pdfplumber.open(str(path)) as pdf:
            n_pages = len(pdf.pages)
            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        _PDF_CACHE[doc_id] = (text, n_pages)
    return _PDF_CACHE[doc_id]


# ---------------------------------------------------------------------------
# Rule 1 -- every answer-key record passes schemas.validate_record
# ---------------------------------------------------------------------------

def rule1_schema_validity(wrappers: dict[str, dict]) -> tuple[bool, list[str]]:
    failures = []
    for doc_id, w in wrappers.items():
        errs = schemas.validate_record(w["record"])
        if errs:
            failures.append(f"{doc_id}: {errs[:3]}")
    return not failures, failures


# ---------------------------------------------------------------------------
# Rule 2 -- rendered-text verbatim / re-rendered presence check
# ---------------------------------------------------------------------------

def rule2_rendered_text(wrappers: dict[str, dict]) -> tuple[bool, list[str]]:
    failures = []
    text_cache: dict[str, str] = {}

    for doc_id, w in wrappers.items():
        record = w["record"]
        is_s = bool(w.get("s_exception"))
        vat_id = record["supplier"]["vat_id"]
        ident = IDENTITY.get(vat_id)
        if ident is None:
            failures.append(f"{doc_id}: supplier vat_id {vat_id!r} not found in config identity lookup")
            continue
        locale = ident["locale"]

        text, _ = pdf_text(doc_id)
        text_cache[doc_id] = text

        # fix 7 sub-check: a null field must never leak into rendered text as
        # the literal standalone token "None" -- templates must omit the
        # whole row/line for a null field instead of printing it.
        if NONE_TOKEN_RE.search(text):
            failures.append(f"{doc_id}: literal standalone token 'None' found in rendered text layer")

        s_line_idx = None
        if is_s:
            for i, line in enumerate(record["lines"]):
                if line["description"] == config.S_EVENT_LINE_DESCRIPTION:
                    s_line_idx = i
                    break
            if s_line_idx is None:
                failures.append(f"{doc_id}: s_exception set but no line matches S_EVENT_LINE_DESCRIPTION")

        flat = schemas.flatten_record(record)
        for path, value in flat.items():
            if value is None:
                continue
            leaf = path.rsplit(".", 1)[-1]
            if leaf in EXCLUDED_FIELDS:
                continue
            skip_normal = (is_s and s_line_idx is not None
                            and path in (f"lines[{s_line_idx}].quantity", f"lines[{s_line_idx}].unit_price"))
            if skip_normal:
                continue
            if leaf in DATE_FIELDS:
                expected = formatting.format_date(value, locale)
            elif leaf in MONEY_FIELDS:
                expected = formatting.format_money(value, locale)
            elif leaf == "quantity":
                expected = formatting.format_quantity(value)
            elif leaf in RATE_FIELDS:
                expected = formatting.format_rate(value, locale)
            else:
                expected = str(value)
            if expected not in text:
                failures.append(f"{doc_id}: field {path} expected {expected!r} not found in rendered text")

        if is_s and s_line_idx is not None:
            # exactly the designed transposition must appear: qty 50, price 2.00
            expected_qty = formatting.format_quantity("50")
            expected_price = formatting.format_money("2.00", locale)
            if expected_qty not in text:
                failures.append(f"{doc_id}: S document missing transposed quantity {expected_qty!r}")
            if expected_price not in text:
                failures.append(f"{doc_id}: S document missing transposed unit_price {expected_price!r}")

    return not failures, failures


# ---------------------------------------------------------------------------
# Rule 3 -- class counts, per-supplier/month counts, December total
# ---------------------------------------------------------------------------

def rule3_counts(wrappers: dict[str, dict]) -> tuple[bool, list[str]]:
    failures = []
    class_counts = Counter(w["class"] for w in wrappers.values())
    if dict(class_counts) != config.EXPECTED_CLASS_COUNTS:
        failures.append(f"class_counts mismatch: got {dict(class_counts)}, expected {config.EXPECTED_CLASS_COUNTS}")

    supplier_month_counts: dict[tuple[str, int], int] = defaultdict(int)
    oneoff_month_counts: dict[int, int] = defaultdict(int)
    december_total = 0
    for w in wrappers.values():
        record = w["record"]
        vat_id = record["supplier"]["vat_id"]
        ident = IDENTITY.get(vat_id)
        month = int(record["invoice"]["issue_date"][5:7])
        if month == 12:
            december_total += 1
        if ident and ident["kind"] == "repeat":
            supplier_month_counts[(ident["sid"], month)] += 1
        elif ident and ident["kind"] == "oneoff":
            oneoff_month_counts[month] += 1

    for sid in config.REPEAT_SUPPLIER_ORDER:
        for month in range(1, 13):
            expected = config.MONTHLY_MATRIX[sid][month - 1]
            got = supplier_month_counts.get((sid, month), 0)
            if got != expected:
                failures.append(f"{sid} month {month}: got {got}, expected {expected}")

    expected_oneoff = Counter(e["month"] for e in config.ONE_OFFS)
    for month in range(1, 13):
        got = oneoff_month_counts.get(month, 0)
        expected = expected_oneoff.get(month, 0)
        if got != expected:
            failures.append(f"one-off documents in month {month}: got {got}, expected {expected}")

    if december_total != 17:
        failures.append(f"December total: got {december_total}, expected 17")

    return not failures, failures


# ---------------------------------------------------------------------------
# Rule 4 -- discovery timing: each repeat supplier's 6th document's month
# ---------------------------------------------------------------------------

def rule4_discovery_timing(wrappers: dict[str, dict]) -> tuple[bool, list[str]]:
    failures = []
    by_supplier: dict[str, list[str]] = defaultdict(list)  # sid -> [issue_date, ...]
    for w in wrappers.values():
        record = w["record"]
        vat_id = record["supplier"]["vat_id"]
        ident = IDENTITY.get(vat_id)
        if ident and ident["kind"] == "repeat":
            by_supplier[ident["sid"]].append(record["invoice"]["issue_date"])

    for sid, dates in by_supplier.items():
        dates.sort()
        if len(dates) < 6:
            failures.append(f"{sid}: fewer than 6 documents ({len(dates)})")
            continue
        sixth_month = int(dates[5][5:7])
        expected_month = config.DISCOVERY_MONTH[sid]
        if sixth_month != expected_month:
            failures.append(f"{sid}: 6th document in month {sixth_month}, expected {expected_month}")

    return not failures, failures


# ---------------------------------------------------------------------------
# Rule 5 -- PO register integrity + credit-note reference resolution
# ---------------------------------------------------------------------------

PO_ELIGIBLE_REPEAT = {"s1", "s2", "s3", "s4", "s5", "s8"}
PO_ELIGIBLE_ONEOFF = {"ersatzteile_brandt"}


def rule5_po_and_credit_notes(wrappers: dict[str, dict], manifest: dict) -> tuple[bool, list[str]]:
    failures = []
    po_by_number = {po["po_number"]: po for po in manifest["po_register"]}

    invoice_numbers_by_supplier: dict[str, list[tuple[str, str]]] = defaultdict(list)  # sid -> [(date, number)]
    for w in wrappers.values():
        record = w["record"]
        vat_id = record["supplier"]["vat_id"]
        ident = IDENTITY.get(vat_id)
        if ident:
            invoice_numbers_by_supplier[ident["sid"]].append(
                (record["invoice"]["issue_date"], record["invoice"]["number"]))

    for doc_id, w in wrappers.items():
        record = w["record"]
        inv = record["invoice"]
        vat_id = record["supplier"]["vat_id"]
        ident = IDENTITY.get(vat_id)
        sid = ident["sid"] if ident else None
        po_number = inv.get("po_number")
        is_credit_note = inv["type"] == "credit_note"

        goods_po_eligible = (sid in PO_ELIGIBLE_REPEAT and ident["kind"] == "repeat") or sid in PO_ELIGIBLE_ONEOFF
        if is_credit_note:
            if po_number is not None:
                failures.append(f"{doc_id}: credit note has a po_number ({po_number!r}), expected null")
        elif goods_po_eligible:
            if po_number is None:
                failures.append(f"{doc_id}: goods invoice from PO-eligible supplier has null po_number")
            else:
                po = po_by_number.get(po_number)
                if po is None:
                    failures.append(f"{doc_id}: po_number {po_number!r} not found in PO register")
                else:
                    if po["supplier_id"] != sid:
                        failures.append(f"{doc_id}: PO {po_number} belongs to {po['supplier_id']!r}, not {sid!r}")
                    po_date = date.fromisoformat(po["date"])
                    inv_date = date.fromisoformat(inv["issue_date"])
                    delta = (inv_date - po_date).days
                    if not (0 < delta <= 45):
                        failures.append(f"{doc_id}: PO date {po['date']} to invoice date {inv['issue_date']} "
                                         f"is {delta} days, expected 1-45")
        else:
            if po_number is not None:
                failures.append(f"{doc_id}: service/one-off invoice has a po_number ({po_number!r}), expected null")

        if is_credit_note:
            orig = inv.get("original_invoice_number")
            if not orig:
                failures.append(f"{doc_id}: credit note missing original_invoice_number")
            elif sid:
                candidates = [(d, n) for d, n in invoice_numbers_by_supplier[sid] if n == orig and d < inv["issue_date"]]
                if not candidates:
                    failures.append(f"{doc_id}: original_invoice_number {orig!r} does not resolve to an "
                                     f"earlier {sid} invoice")

    return not failures, failures


# ---------------------------------------------------------------------------
# Rule 6 -- identifier check digits (explicit, via schemas)
# ---------------------------------------------------------------------------

def rule6_identifier_check_digits(wrappers: dict[str, dict]) -> tuple[bool, list[str]]:
    failures = []
    for doc_id, w in wrappers.items():
        record = w["record"]
        for role in ("supplier", "buyer"):
            p = record[role]
            # buyer.vat_id is legitimately null on domestic (non-reverse-charge) documents
            if p.get("vat_id") is not None and not schemas.vat_id_ok(p["vat_id"], p["country"]):
                failures.append(f"{doc_id}: {role} vat_id {p['vat_id']!r} fails national format")
            if p["country"] == "FI" and p.get("business_id") and not schemas.y_tunnus_ok(p["business_id"]):
                failures.append(f"{doc_id}: {role} Y-tunnus {p['business_id']!r} fails check digit")
        bank = record["bank"]
        if bank.get("iban") and not schemas.iban_ok(bank["iban"]):
            failures.append(f"{doc_id}: IBAN {bank['iban']!r} fails mod-97")
        inv = record["invoice"]
        rt, rv = inv.get("reference_type"), inv.get("reference_value")
        if rt == "viitenumero" and not schemas.viitenumero_ok(rv):
            failures.append(f"{doc_id}: viitenumero {rv!r} fails 7-3-1 check digit")
        if rt == "ocr" and not schemas.ocr_ok(rv):
            failures.append(f"{doc_id}: OCR reference {rv!r} fails mod-10 check digit")
        if rt == "rf":
            s = rv.replace(" ", "")
            rearranged = s[4:] + s[:4]
            digits = "".join(str(int(c, 36)) for c in rearranged)
            if int(digits) % 97 != 1:
                failures.append(f"{doc_id}: RF reference {rv!r} fails mod-97 check digit")
    return not failures, failures


# ---------------------------------------------------------------------------
# Rule 7 -- supplier identity stability across the year
# ---------------------------------------------------------------------------

IDENTITY_FIELDS = ("name", "street", "postcode", "city", "country", "vat_id", "business_id")


def rule7_identity_stability(wrappers: dict[str, dict]) -> tuple[bool, list[str]]:
    failures = []
    by_vat: dict[str, list[tuple[str, dict, dict]]] = defaultdict(list)
    for doc_id, w in wrappers.items():
        record = w["record"]
        by_vat[record["supplier"]["vat_id"]].append((doc_id, record["supplier"], record["bank"]))

    for vat_id, entries in by_vat.items():
        first_doc, first_supplier, first_bank = entries[0]
        for doc_id, supplier, bank in entries[1:]:
            for f in IDENTITY_FIELDS:
                if supplier.get(f) != first_supplier.get(f):
                    failures.append(f"{doc_id}: supplier.{f} = {supplier.get(f)!r} differs from "
                                     f"{first_doc}'s {first_supplier.get(f)!r}")
            if bank != first_bank:
                failures.append(f"{doc_id}: bank block {bank!r} differs from {first_doc}'s {first_bank!r}")
    return not failures, failures


# ---------------------------------------------------------------------------
# Rule 8 -- currency / locale discipline
# ---------------------------------------------------------------------------

def rule8_currency_locale(wrappers: dict[str, dict]) -> tuple[bool, list[str]]:
    failures = []
    for doc_id, w in wrappers.items():
        record = w["record"]
        currency = record["invoice"]["currency"]
        name = record["supplier"]["name"]
        is_s4 = name.startswith("Möbeltyg")
        if currency == "SEK" and not is_s4:
            failures.append(f"{doc_id}: currency SEK but supplier is {name!r}, not Möbeltyg Viskan AB")
        if is_s4 and currency != "SEK":
            failures.append(f"{doc_id}: Möbeltyg Viskan AB document not in SEK ({currency!r})")
        if record["supplier"]["vat_id"] not in IDENTITY:
            failures.append(f"{doc_id}: supplier vat_id {record['supplier']['vat_id']!r} has no known locale mapping")
        # one currency per document is structural (schema has a single currency field) -- nothing further to check
    return not failures, failures


# ---------------------------------------------------------------------------
# Rule 9 -- multi-page: >= 10 documents have 2 pages, none exceed 2
# ---------------------------------------------------------------------------

def rule9_multipage(wrappers: dict[str, dict]) -> tuple[bool, list[str]]:
    failures = []
    two_page_count = 0
    for doc_id in wrappers:
        _, n_pages = pdf_text(doc_id)
        if n_pages > 2:
            failures.append(f"{doc_id}: {n_pages} pages, expected <= 2")
        if n_pages == 2:
            two_page_count += 1
    if two_page_count < 10:
        failures.append(f"only {two_page_count} documents have 2 pages, expected >= 10")
    return not failures, failures + [f"(two_page_count={two_page_count})"]


# ---------------------------------------------------------------------------
# Rule 10 -- grounded formatting: every template file is registered
# ---------------------------------------------------------------------------

def rule10_template_registry() -> tuple[bool, list[str]]:
    failures = []
    template_files = sorted(p.stem.replace(".html", "") for p in TEMPLATES_DIR.glob("*.html.j2"))
    for name in template_files:
        sections = config.TEMPLATE_REGISTRY.get(name)
        if not sections:
            failures.append(f"template {name!r} has no non-empty entry in config.TEMPLATE_REGISTRY")
    for name in config.TEMPLATE_REGISTRY:
        if name not in template_files:
            failures.append(f"config.TEMPLATE_REGISTRY has entry {name!r} with no matching template file")
    return not failures, failures


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not ANSWER_KEY_DIR.exists() or not any(ANSWER_KEY_DIR.glob("*.json")):
        print(f"FATAL: no answer keys found in {ANSWER_KEY_DIR}. Run generate_invoices.py first.", flush=True)
        sys.exit(1)
    if not MANIFEST_PATH.exists():
        print(f"FATAL: no manifest at {MANIFEST_PATH}. Run generate_invoices.py first.", flush=True)
        sys.exit(1)

    print("Loading answer keys and manifest...", flush=True)
    wrappers = load_answer_keys()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    print(f"  {len(wrappers)} documents loaded", flush=True)

    rules = [
        ("1. schema validity (schemas.validate_record)", lambda: rule1_schema_validity(wrappers)),
        ("2. rendered-text verbatim/re-render presence", lambda: rule2_rendered_text(wrappers)),
        ("3. class/supplier/month counts, December=17", lambda: rule3_counts(wrappers)),
        ("4. discovery timing (6th document's month)", lambda: rule4_discovery_timing(wrappers)),
        ("5. PO register integrity + credit-note refs", lambda: rule5_po_and_credit_notes(wrappers, manifest)),
        ("6. identifier check digits", lambda: rule6_identifier_check_digits(wrappers)),
        ("7. supplier identity stability", lambda: rule7_identity_stability(wrappers)),
        ("8. currency/locale discipline", lambda: rule8_currency_locale(wrappers)),
        ("9. multi-page (>=10 at 2 pages, none >2)", lambda: rule9_multipage(wrappers)),
        ("10. grounded formatting (template registry)", lambda: rule10_template_registry()),
    ]

    all_passed = True
    for name, fn in rules:
        print(f"Running rule {name}...", flush=True)
        passed, failures = fn()
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}", flush=True)
        if not passed:
            all_passed = False
            for f in failures[:15]:
                print(f"    - {f}", flush=True)
            if len(failures) > 15:
                print(f"    ... and {len(failures) - 15} more", flush=True)

    print("", flush=True)
    if all_passed:
        print("ALL RULES PASSED", flush=True)
        sys.exit(0)
    else:
        print("VALIDATION FAILED", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
