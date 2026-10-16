"""
schemas.py — Per-transaction-type extraction schemas for the ERP Cleanup case study.

One schema per transaction type, binding all three consumers:
  - the answer key emitted by generate_documents.py,
  - the LLM extraction path,
  - the overseer-generated deterministic parsers.
"Correctly parsed" means: conforms to the schema here AND matches the answer
key field-for-field. There is no second definition.

Design-critical file;
implementation scripts import from here and must not redefine field sets.

Conventions:
  - Dates are ISO strings "YYYY-MM-DD" in JSON (documents render them German,
    DD.MM.YYYY — parsing includes the locale conversion).
  - Money and quantities are floats rounded to 2 decimals in JSON (documents
    render them German, 1.234,56 with trailing minus for negatives).
  - MONEY_TOLERANCE is the comparison tolerance for money fields everywhere
    (answer-key validation, parser regression, evaluation).
  - A field spec of the form ("name", "type") is required; ("name", "type?")
    is nullable/optional.

Field type vocabulary: str, date, money, qty, int, and enum:A|B|C.
"""

MONEY_TOLERANCE = 0.005

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
# Structure per type:
#   header:     flat dict of fields
#   line_items: list of dicts (the repeating unit)
#   totals:     dict, possibly with per-group subtotal lists
# FBL1N is nested one level deeper (vendors[] each with line_items and totals)
# because the document itself is one-vendor-per-page; MB52 line items carry
# their plant/storage-location denormalised so field accuracy is scored flat.

SCHEMAS = {
    "FBL3N": {
        "header": [
            ("company_code", "str"),
            ("gl_account", "str"),
            ("gl_account_name", "str"),
            ("period_from", "date"),
            ("period_to", "date"),
            ("report_date", "date"),
            ("user", "str"),
        ],
        "line_items": [
            ("posting_date", "date"),
            ("document_number", "str"),
            ("document_type", "str"),
            ("debit_credit", "enum:S|H"),
            ("amount", "money"),          # signed: H (credit) is negative
            ("tax_amount", "money"),      # Steuerbetrag; 0.0 when no VAT line
            ("clearing_document", "str?"),
            ("reference", "str?"),
            ("text", "str?"),
        ],
        "totals": [
            ("sum_debit", "money"),
            ("sum_credit", "money"),      # negative by the sign convention
            ("balance", "money"),
        ],
    },
    "ME2M": {
        "header": [
            ("purch_org", "str"),
            ("selection_scope", "str"),
            ("report_date", "date"),
            ("user", "str"),
        ],
        "line_items": [
            ("po_number", "str"),
            ("item", "int"),
            ("order_date", "date"),
            ("vendor_number", "str"),
            ("vendor_name", "str"),
            ("material", "str"),
            ("material_text", "str"),
            ("quantity", "qty"),
            ("unit", "str"),
            ("net_price", "money"),
            ("net_value", "money"),
            ("currency", "str"),
            ("still_to_deliver_qty", "qty"),
            ("still_to_deliver_value", "money"),
        ],
        "totals": [
            ("vendor_subtotals", "list"),   # [{vendor_number, total_value}]
            ("grand_total", "money"),
        ],
        "subtotal_item": [
            ("vendor_number", "str"),
            ("total_value", "money"),
        ],
    },
    "VA05": {
        "header": [
            ("sales_org", "str"),
            ("period_from", "date"),
            ("period_to", "date"),
            ("report_date", "date"),
            ("user", "str"),
        ],
        "line_items": [
            ("sales_document", "str"),
            ("doc_date", "date"),
            ("sold_to", "str"),
            ("material", "str"),
            ("order_quantity", "qty"),
            ("unit", "str"),
            ("net_value", "money"),
            ("currency", "str"),
            ("delivery_status", "str"),
        ],
        "totals": [
            ("total_net_value", "money"),
        ],
    },
    "FBL1N": {
        # One document = several vendors, one per page.
        "header": [
            ("company_code", "str"),
            ("key_date", "date"),
            ("report_date", "date"),
            ("user", "str"),
        ],
        "vendors": [
            ("vendor_number", "str"),
            ("vendor_name", "str"),
        ],
        "line_items": [                      # per vendor
            ("status", "enum:open|partial|cleared"),
            ("document_number", "str"),
            ("document_type", "enum:KR|KZ|KA"),
            ("document_date", "date"),
            ("posting_date", "date"),
            ("due_date", "date"),
            ("debit_credit", "enum:S|H"),
            ("amount", "money"),             # signed: H (credit) is negative
            ("currency", "str"),
            ("clearing_document", "str?"),
        ],
        "vendor_totals": [                   # per vendor; one entry per currency
            ("currency", "str"),
            ("open_total", "money"),
            ("cleared_total", "money"),
        ],
        "totals": [],                        # no document-level totals row
    },
    "MB52": {
        "header": [
            ("plants", "list"),              # list of plant codes in selection
            ("report_date", "date"),
            ("user", "str"),
        ],
        "line_items": [                      # flat; hierarchy denormalised
            ("material", "str"),
            ("material_text", "str"),
            ("plant", "str"),
            ("storage_location", "str"),
            ("unit", "str"),
            ("unrestricted", "qty"),
            ("quality_inspection", "qty"),
            ("blocked", "qty"),
            ("value_unrestricted", "money"),
            ("currency", "str"),
        ],
        "totals": [
            ("plant_totals", "list"),        # [{plant, value_total}]
            ("grand_value_total", "money"),
        ],
        "subtotal_item": [
            ("plant", "str"),
            ("value_total", "money"),
        ],
    },
}

TRANSACTION_TYPES = list(SCHEMAS.keys())

# ---------------------------------------------------------------------------
# Answer-key envelope
# ---------------------------------------------------------------------------
# The answer key wraps the parse payload with generator-side metadata that a
# parser never sees and never produces. Evaluation joins on doc_id.

ANSWER_KEY_METADATA = [
    ("doc_id", "str"),            # e.g. "2025-03_FBL3N_02"
    ("transaction_type", "str"),
    ("month", "str"),             # "2025-03"
    ("doc_class", "enum:R|V|F|S"),
    ("planted_mechanism", "str?"),  # e.g. "column_swap:amount<->tax_amount"
]


# ---------------------------------------------------------------------------
# Validation helpers (dependency-free)
# ---------------------------------------------------------------------------

def _check_value(name, spec_type, value, errors, where):
    optional = spec_type.endswith("?")
    base = spec_type.rstrip("?")
    if value is None:
        if not optional:
            errors.append(f"{where}: '{name}' is null but required")
        return
    if base == "str":
        if not isinstance(value, str) or value == "":
            errors.append(f"{where}: '{name}' should be a non-empty string, got {value!r}")
    elif base == "date":
        if not isinstance(value, str) or len(value) != 10 or value[4] != "-" or value[7] != "-":
            errors.append(f"{where}: '{name}' should be ISO date YYYY-MM-DD, got {value!r}")
    elif base in ("money", "qty"):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            errors.append(f"{where}: '{name}' should be a number, got {value!r}")
    elif base == "int":
        if not isinstance(value, int) or isinstance(value, bool):
            errors.append(f"{where}: '{name}' should be an integer, got {value!r}")
    elif base == "list":
        if not isinstance(value, list):
            errors.append(f"{where}: '{name}' should be a list, got {type(value).__name__}")
    elif base.startswith("enum:"):
        allowed = base.split(":", 1)[1].split("|")
        if value not in allowed:
            errors.append(f"{where}: '{name}' should be one of {allowed}, got {value!r}")
    else:
        errors.append(f"{where}: unknown spec type '{spec_type}' for '{name}'")


def _check_fields(spec, record, errors, where):
    spec_names = {name for name, _ in spec}
    for name, spec_type in spec:
        if name not in record:
            errors.append(f"{where}: missing field '{name}'")
        else:
            _check_value(name, spec_type, record[name], errors, where)
    for name in record:
        if name not in spec_names:
            errors.append(f"{where}: unexpected field '{name}'")


def validate_parse(transaction_type, payload):
    """Validate a parse payload (or the parse portion of an answer key)
    against its schema. Returns a list of error strings; empty means valid.
    Structural conformance only — value correctness is the answer key's job."""
    errors = []
    schema = SCHEMAS.get(transaction_type)
    if schema is None:
        return [f"unknown transaction type {transaction_type!r}"]

    _check_fields(schema["header"], payload.get("header", {}), errors, "header")

    if transaction_type == "FBL1N":
        vendors = payload.get("vendors", [])
        if not isinstance(vendors, list) or not vendors:
            errors.append("vendors: should be a non-empty list")
            return errors
        for vi, vendor in enumerate(vendors):
            where = f"vendors[{vi}]"
            _check_fields(schema["vendors"],
                          {k: v for k, v in vendor.items()
                           if k not in ("line_items", "vendor_totals")},
                          errors, where)
            for li, item in enumerate(vendor.get("line_items", [])):
                _check_fields(schema["line_items"], item, errors, f"{where}.line_items[{li}]")
            for ti, tot in enumerate(vendor.get("vendor_totals", [])):
                _check_fields(schema["vendor_totals"], tot, errors, f"{where}.vendor_totals[{ti}]")
            if not vendor.get("line_items"):
                errors.append(f"{where}: no line items")
    else:
        items = payload.get("line_items", [])
        if not isinstance(items, list) or not items:
            errors.append("line_items: should be a non-empty list")
        else:
            for li, item in enumerate(items):
                _check_fields(schema["line_items"], item, errors, f"line_items[{li}]")
        _check_fields(schema["totals"], payload.get("totals", {}), errors, "totals")
        sub_spec = schema.get("subtotal_item")
        if sub_spec:
            list_field = schema["totals"][0][0]   # vendor_subtotals / plant_totals
            for si, sub in enumerate(payload.get("totals", {}).get(list_field, []) or []):
                _check_fields(sub_spec, sub, errors, f"totals.{list_field}[{si}]")

    return errors


def money_equal(a, b, tolerance=MONEY_TOLERANCE):
    """The one definition of money equality used everywhere."""
    return abs(float(a) - float(b)) <= tolerance
