"""Extraction schema for the invoice-processing case study (Project 3).

One schema binds all three uses:
  - the answer key (ground truth per document),
  - the LLM parse path (subagent output is validated against this),
  - the generated deterministic parsers (their output is validated against this).

"Correctly parsed" has exactly one definition: a record that passes
``validate_record`` and matches the answer key field-for-field.

Conventions
-----------
- Monetary amounts and quantities are canonical decimal STRINGS
  (``"1841.00"``, ``"-52.00"``, ``"24"``): locale rendering (``1 841,00`` /
  ``1.841,00``) is normalised away by whoever extracts.
- Dates are ISO ``YYYY-MM-DD`` regardless of the printed format.
- Free-text fields (names, descriptions, references, identifiers) are the
  verbatim rendered strings from the document.
- The class label (R/O/T/F/S) lives only in the answer key wrapper, never in
  the extraction record: neither path may see it.

Stdlib only. Shared identifier algorithms (IBAN mod-97, viitenumero 7-3-1,
Swedish OCR mod-10, Y-tunnus mod-11) live here so the generator, the
validator and the router use one implementation.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

SCHEMA_VERSION = "1.0"

MONEY_RE = re.compile(r"^-?\d+\.\d{2}$")
QTY_RE = re.compile(r"^-?\d+$")          # quantities are integers by design
RATE_VALUES = {"25.5", "14.0", "10.0", "0.0"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CURRENCIES = {"EUR", "SEK"}
COUNTRIES = {"FI", "DE", "SE", "EE", "IE"}
DOC_TYPES = {"invoice", "credit_note"}
REFERENCE_TYPES = {"viitenumero", "rf", "ocr"}

# ---------------------------------------------------------------------------
# Identifier algorithms (Finnish, German, Swedish and Estonian formats)
# ---------------------------------------------------------------------------

def iban_ok(iban: str) -> bool:
    """ISO 13616 mod-97 check (spaces tolerated)."""
    s = iban.replace(" ", "").upper()
    if not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$", s):
        return False
    rearranged = s[4:] + s[:4]
    digits = "".join(str(int(c, 36)) for c in rearranged)
    return int(digits) % 97 == 1


def viitenumero_ok(ref: str) -> bool:
    """Finnish bank reference: weights 7-3-1 right-to-left, mod 10."""
    s = ref.replace(" ", "")
    if not s.isdigit() or not (4 <= len(s) <= 20):
        return False
    base, check = s[:-1], int(s[-1])
    weights = [7, 3, 1]
    total = sum(int(d) * weights[i % 3] for i, d in enumerate(reversed(base)))
    return (10 - total % 10) % 10 == check


def make_viitenumero(base: str) -> str:
    """Append the 7-3-1 check digit to a digit string."""
    weights = [7, 3, 1]
    total = sum(int(d) * weights[i % 3] for i, d in enumerate(reversed(base)))
    return base + str((10 - total % 10) % 10)


def ocr_ok(ref: str) -> bool:
    """Swedish OCR reference: Luhn (mod-10) check digit, 3-25 digits."""
    s = ref.replace(" ", "")
    if not s.isdigit() or not (3 <= len(s) <= 25):
        return False
    total = 0
    for i, d in enumerate(reversed(s)):
        n = int(d)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def make_ocr(base: str) -> str:
    """Append the Luhn check digit to a digit string."""
    total = 0
    for i, d in enumerate(reversed(base)):
        n = int(d)
        if i % 2 == 0:          # positions counted after the check digit is added
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return base + str((10 - total % 10) % 10)


def y_tunnus_ok(business_id: str) -> bool:
    """Finnish Y-tunnus: NNNNNNN-C, weights 7 9 10 5 8 4 2, mod 11."""
    m = re.match(r"^(\d{7})-(\d)$", business_id)
    if not m:
        return False
    digits, check = m.group(1), int(m.group(2))
    weights = [7, 9, 10, 5, 8, 4, 2]
    total = sum(int(d) * w for d, w in zip(digits, weights))
    rem = total % 11
    if rem == 0:
        return check == 0
    if rem == 1:
        return False            # ids with remainder 1 are never issued
    return check == 11 - rem


def make_y_tunnus(seven_digits: str) -> str | None:
    """Return NNNNNNN-C, or None if the remainder-1 case makes it invalid."""
    weights = [7, 9, 10, 5, 8, 4, 2]
    total = sum(int(d) * w for d, w in zip(seven_digits, weights))
    rem = total % 11
    if rem == 1:
        return None
    return f"{seven_digits}-{0 if rem == 0 else 11 - rem}"


def vat_id_ok(vat_id: str, country: str) -> bool:
    patterns = {
        "FI": r"^FI\d{8}$",
        "DE": r"^DE\d{9}$",
        "SE": r"^SE\d{10}01$",
        "EE": r"^EE\d{9}$",
        "IE": r"^IE\d{7}[A-W][A-I]?$",
    }
    return bool(re.match(patterns[country], vat_id)) if country in patterns else False


# ---------------------------------------------------------------------------
# Record structure
# ---------------------------------------------------------------------------
# party: name, street, postcode, city, country, vat_id (nullable for buyer on
#        domestic docs and for non-VAT contexts), business_id (nullable for
#        non-FI parties where not printed)
# invoice: number, type, issue_date, supply_date?, due_date?, payment_terms?,
#        currency, po_number?, reference_type?, reference_value?,
#        original_invoice_number? (credit notes), reverse_charge_mention?
# bank: iban?, bic?, bankgiro?   (at least one route present)
# lines: [{description, quantity, unit, unit_price, vat_rate, line_total}]
# vat_summary: [{rate, base, amount}]  (>= 1 row; 0.0-row on reverse-charge docs)
# totals: {net, vat, gross}

_PARTY_FIELDS = {"name", "street", "postcode", "city", "country", "vat_id", "business_id"}
_INVOICE_FIELDS = {
    "number", "type", "issue_date", "supply_date", "due_date", "payment_terms",
    "currency", "po_number", "reference_type", "reference_value",
    "original_invoice_number", "reverse_charge_mention",
}
_BANK_FIELDS = {"iban", "bic", "bankgiro"}
_LINE_FIELDS = {"description", "quantity", "unit", "unit_price", "vat_rate", "line_total"}
_VAT_ROW_FIELDS = {"rate", "base", "amount"}
_TOTAL_FIELDS = {"net", "vat", "gross"}


def _d(value: str) -> Decimal:
    return Decimal(value)


def _err(errors: list, path: str, msg: str) -> None:
    errors.append(f"{path}: {msg}")


def _check_fields(obj: dict, allowed: set, required: set, path: str, errors: list) -> None:
    if not isinstance(obj, dict):
        _err(errors, path, "not an object")
        return
    for k in obj:
        if k not in allowed:
            _err(errors, path, f"unexpected field '{k}'")
    for k in required:
        if k not in obj:
            _err(errors, path, f"missing field '{k}'")


def _check_money(value, path: str, errors: list) -> bool:
    if not isinstance(value, str) or not MONEY_RE.match(value):
        _err(errors, path, f"not a canonical money string: {value!r}")
        return False
    return True


def validate_record(rec: dict) -> list[str]:
    """Return a list of validation errors (empty == valid).

    Checks structure, formats, conditional requirements, identifier check
    digits, and internal arithmetic to the cent. Does NOT compare against the
    answer key and does NOT know document classes.
    """
    errors: list[str] = []
    if not isinstance(rec, dict):
        return ["record: not an object"]

    _check_fields(rec, {"schema_version", "doc_id", "supplier", "buyer", "invoice",
                        "bank", "lines", "vat_summary", "totals"},
                  {"supplier", "buyer", "invoice", "bank", "lines", "vat_summary", "totals"},
                  "record", errors)
    if errors:
        return errors

    # --- parties ---
    for role in ("supplier", "buyer"):
        p = rec[role]
        _check_fields(p, _PARTY_FIELDS, {"name", "street", "postcode", "city", "country"},
                      role, errors)
        if isinstance(p, dict):
            if p.get("country") not in COUNTRIES:
                _err(errors, role, f"bad country: {p.get('country')!r}")
            for f in ("name", "street", "postcode", "city"):
                if f in p and (not isinstance(p.get(f), str) or not p[f].strip()):
                    _err(errors, role, f"empty or non-string '{f}'")
            vat = p.get("vat_id")
            if vat is not None and isinstance(p.get("country"), str) and p["country"] in COUNTRIES:
                if not vat_id_ok(vat, p["country"]):
                    _err(errors, role, f"vat_id fails national format: {vat!r}")
            bid = p.get("business_id")
            if bid is not None and p.get("country") == "FI" and not y_tunnus_ok(bid):
                _err(errors, role, f"Y-tunnus check digit fails: {bid!r}")

    # --- invoice block ---
    inv = rec["invoice"]
    _check_fields(inv, _INVOICE_FIELDS, {"number", "type", "issue_date", "currency"},
                  "invoice", errors)
    if isinstance(inv, dict):
        if inv.get("type") not in DOC_TYPES:
            _err(errors, "invoice", f"bad type: {inv.get('type')!r}")
        for f in ("issue_date", "supply_date", "due_date"):
            v = inv.get(f)
            if v is not None and (not isinstance(v, str) or not DATE_RE.match(v)):
                _err(errors, "invoice", f"{f} not ISO: {v!r}")
        if inv.get("currency") not in CURRENCIES:
            _err(errors, "invoice", f"bad currency: {inv.get('currency')!r}")
        rt, rv = inv.get("reference_type"), inv.get("reference_value")
        if (rt is None) != (rv is None):
            _err(errors, "invoice", "reference_type and reference_value must both be set or both null")
        if rt is not None:
            if rt not in REFERENCE_TYPES:
                _err(errors, "invoice", f"bad reference_type: {rt!r}")
            elif rt == "viitenumero" and not viitenumero_ok(rv):
                _err(errors, "invoice", f"viitenumero check digit fails: {rv!r}")
            elif rt == "ocr" and not ocr_ok(rv):
                _err(errors, "invoice", f"OCR check digit fails: {rv!r}")
            elif rt == "rf":
                s = rv.replace(" ", "")
                if not re.match(r"^RF\d{2}\d{1,21}$", s):
                    _err(errors, "invoice", f"RF reference malformed: {rv!r}")
                else:
                    rearranged = s[4:] + s[:4]
                    digits = "".join(str(int(c, 36)) for c in rearranged)
                    if int(digits) % 97 != 1:
                        _err(errors, "invoice", f"RF check digits fail: {rv!r}")
        if inv.get("type") == "credit_note" and not inv.get("original_invoice_number"):
            _err(errors, "invoice", "credit note without original_invoice_number")

    # --- bank block ---
    bank = rec["bank"]
    _check_fields(bank, _BANK_FIELDS, set(), "bank", errors)
    if isinstance(bank, dict):
        if not any(bank.get(f) for f in _BANK_FIELDS):
            _err(errors, "bank", "no payment route (iban or bankgiro) present")
        if bank.get("iban") is not None and not iban_ok(bank["iban"]):
            _err(errors, "bank", f"IBAN mod-97 fails: {bank['iban']!r}")
        if bank.get("bankgiro") is not None and not re.match(r"^\d{3,4}-\d{4}$", bank["bankgiro"]):
            _err(errors, "bank", f"bankgiro malformed: {bank['bankgiro']!r}")

    # --- lines ---
    lines = rec["lines"]
    if not isinstance(lines, list) or not lines:
        _err(errors, "lines", "must be a non-empty array")
        lines = []
    line_sum = Decimal("0")
    rate_bases: dict[str, Decimal] = {}
    for i, line in enumerate(lines):
        path = f"lines[{i}]"
        _check_fields(line, _LINE_FIELDS, _LINE_FIELDS, path, errors)
        if not isinstance(line, dict):
            continue
        ok = True
        if not isinstance(line.get("quantity"), str) or not QTY_RE.match(line.get("quantity", "")):
            _err(errors, path, f"quantity not canonical integer string: {line.get('quantity')!r}")
            ok = False
        ok &= _check_money(line.get("unit_price"), f"{path}.unit_price", errors)
        ok &= _check_money(line.get("line_total"), f"{path}.line_total", errors)
        if line.get("vat_rate") not in RATE_VALUES:
            _err(errors, path, f"vat_rate not in {sorted(RATE_VALUES)}: {line.get('vat_rate')!r}")
            ok = False
        if ok:
            expected = _d(line["quantity"]) * _d(line["unit_price"])
            if expected != _d(line["line_total"]):
                _err(errors, path, f"qty*price != line_total ({expected} != {line['line_total']})")
            line_sum += _d(line["line_total"])
            rate_bases.setdefault(line["vat_rate"], Decimal("0"))
            rate_bases[line["vat_rate"]] += _d(line["line_total"])

    # --- vat summary ---
    summary = rec["vat_summary"]
    if not isinstance(summary, list) or not summary:
        _err(errors, "vat_summary", "must be a non-empty array")
        summary = []
    vat_sum = Decimal("0")
    seen_rates = set()
    for i, row in enumerate(summary):
        path = f"vat_summary[{i}]"
        _check_fields(row, _VAT_ROW_FIELDS, _VAT_ROW_FIELDS, path, errors)
        if not isinstance(row, dict):
            continue
        rate = row.get("rate")
        if rate not in RATE_VALUES:
            _err(errors, path, f"rate not in {sorted(RATE_VALUES)}: {rate!r}")
            continue
        if rate in seen_rates:
            _err(errors, path, f"duplicate rate row: {rate}")
        seen_rates.add(rate)
        if not (_check_money(row.get("base"), f"{path}.base", errors)
                and _check_money(row.get("amount"), f"{path}.amount", errors)):
            continue
        base, amount = _d(row["base"]), _d(row["amount"])
        expected_vat = (base * _d(rate) / 100).quantize(Decimal("0.01"))
        if amount != expected_vat:
            _err(errors, path, f"amount != round(base*rate) ({amount} != {expected_vat})")
        if rate in rate_bases and rate_bases[rate] != base:
            _err(errors, path, f"base != sum of {rate}% lines ({base} != {rate_bases[rate]})")
        vat_sum += amount
    for rate in rate_bases:
        if rate not in seen_rates:
            _err(errors, "vat_summary", f"missing row for rate {rate} present in lines")

    # --- totals ---
    totals = rec["totals"]
    _check_fields(totals, _TOTAL_FIELDS, _TOTAL_FIELDS, "totals", errors)
    if isinstance(totals, dict) and all(
            _check_money(totals.get(f), f"totals.{f}", errors) for f in ("net", "vat", "gross")):
        if _d(totals["net"]) != line_sum:
            _err(errors, "totals", f"net != sum of lines ({totals['net']} != {line_sum})")
        if _d(totals["vat"]) != vat_sum:
            _err(errors, "totals", f"vat != sum of vat_summary ({totals['vat']} != {vat_sum})")
        if _d(totals["gross"]) != _d(totals["net"]) + _d(totals["vat"]):
            _err(errors, "totals", "gross != net + vat")
        if isinstance(inv, dict) and inv.get("type") == "credit_note" and _d(totals["gross"]) >= 0:
            _err(errors, "totals", "credit note with non-negative gross")

    # --- cross-block conditionals ---
    if isinstance(inv, dict) and isinstance(rec.get("supplier"), dict):
        supplier_country = rec["supplier"].get("country")
        buyer = rec.get("buyer", {})
        zero_only = seen_rates == {"0.0"} if seen_rates else False
        if supplier_country in {"DE", "SE", "EE", "IE"}:
            if not zero_only:
                _err(errors, "record", "foreign-supplier document must be 0% (reverse charge / ICS)")
            if not inv.get("reverse_charge_mention"):
                _err(errors, "invoice", "0% cross-border document without its required mention")
            if isinstance(buyer, dict) and not buyer.get("vat_id"):
                _err(errors, "buyer", "reverse-charge/ICS document without buyer vat_id")
        if supplier_country == "SE" and rec["supplier"].get("name", "").startswith("Möbeltyg") \
                and inv.get("currency") != "SEK":
            _err(errors, "invoice", "S4 documents are SEK by design")

    return errors


# ---------------------------------------------------------------------------
# Field flattening — one honest way to count and compare fields
# ---------------------------------------------------------------------------

def flatten_record(rec: dict) -> dict[str, object]:
    """Flatten a record to dotted-path -> value for field-level accuracy.

    Arrays are indexed; None values are kept (a wrongly-null field is an
    error, a rightly-null field is a correct field).
    """
    flat: dict[str, object] = {}

    def walk(obj, prefix: str) -> None:
        if isinstance(obj, dict):
            for k in sorted(obj):
                if k in {"schema_version", "doc_id"}:
                    continue
                walk(obj[k], f"{prefix}.{k}" if prefix else k)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                walk(item, f"{prefix}[{i}]")
        else:
            flat[prefix] = obj

    walk(rec, "")
    return flat


def compare_records(parsed: dict, truth: dict) -> dict:
    """Field-level comparison against the answer key.

    Returns {'total': int, 'wrong': [(path, parsed_value, true_value), ...]}.
    The universe of fields is the answer key's (missing in parse = wrong;
    extra hallucinated fields also counted wrong).
    """
    p, t = flatten_record(parsed), flatten_record(truth)
    wrong = []
    for path, tv in t.items():
        if path not in p:
            wrong.append((path, "<missing>", tv))
        elif p[path] != tv:
            wrong.append((path, p[path], tv))
    for path in p:
        if path not in t:
            wrong.append((path, p[path], "<not a field>"))
    return {"total": len(t), "wrong": wrong}
