"""
generate_documents.py -- Renders the 240-document synthetic corpus for the
ERP Cleanup case study: plain-text SAP-style spool documents plus
their JSON answer keys. Every rendering convention below follows documented
SAP spool-output conventions.

No LLM anywhere in this file. Determinism: every document's random draws
come from a per-document rng seeded from sha256(RANDOM_SEED : doc_id), so
regenerating the corpus is byte-identical (validated by validate_data.py's
determinism check, not by this script).

Outputs:
    data/documents/<doc_id>.txt   -- the rendered spool document
    data/answer_key/<doc_id>.json -- {metadata per schemas.ANSWER_KEY_METADATA,
                                       "parse": <payload per schemas.SCHEMAS[type]>}
"""

import sys
import json
import hashlib
import datetime as dt
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config
import schemas

# ===========================================================================
# Determinism helpers
# ===========================================================================

def doc_seed(doc_id):
    """Stable (non-randomized) integer seed derived from doc_id, independent
    of Python's salted hash(). Same doc_id -> same seed, every run."""
    digest = hashlib.sha256(f"{config.RANDOM_SEED}:{doc_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def doc_rng(doc_id):
    return np.random.default_rng(doc_seed(doc_id))


# The whole in-world corpus lives in 2025. Every date derived by adding an offset to another date (due dates,
# fallback KA postings, ...) must be clamped to this range.
YEAR_START = dt.date(2025, 1, 1)
YEAR_END = dt.date(2025, 12, 31)

# ===========================================================================
# Locale rendering helpers (German locale)
# ===========================================================================

def de_number(value, decimals=2):
    """Format a number German-locale: thousands '.', decimals ',', trailing
    '-' for negatives (H3 horror). E.g. -1234.5 -> '1.234,50-'."""
    negative = value < -1e-9
    magnitude = abs(value)
    us_formatted = f"{magnitude:,.{decimals}f}"          # "1,234.50"
    de_formatted = us_formatted.replace(",", "§").replace(".", ",").replace("§", ".")
    return de_formatted + "-" if negative else de_formatted


def de_money(value):
    return de_number(value, decimals=2)


def de_qty(value, unit):
    """Quantities: integer with thousands separator for ST (piece units);
    3 decimals for KG/M. Matches the documented '1.000 ST' convention."""
    if unit == "ST":
        return de_number(round(value), decimals=0)
    return de_number(value, decimals=3)


def de_date(iso_date):
    """ISO 'YYYY-MM-DD' -> German 'DD.MM.YYYY'."""
    if isinstance(iso_date, dt.date):
        d = iso_date
    else:
        d = dt.date.fromisoformat(iso_date)
    return d.strftime("%d.%m.%Y")


# ===========================================================================
# Date sampling (business-day weighting, month-end
# clustering, no dates after report_date)
# ===========================================================================

def _is_business_day(d):
    return d.weekday() < 5


def sample_business_weighted_date(rng, earliest, latest, business_weight=0.85):
    """Uniform pick over [earliest, latest] inclusive, resampled up to a few
    times to prefer (not force) a business day -- gives the ~80%+ business-day
    mix the coherence rules require without ever excluding weekends outright."""
    span = (latest - earliest).days
    if span <= 0:
        return earliest
    for _ in range(6):
        candidate = earliest + dt.timedelta(days=int(rng.integers(0, span + 1)))
        if _is_business_day(candidate) or rng.random() > business_weight:
            return candidate
    return candidate


def last_business_day_of_month(year, month):
    if month == 12:
        next_month_first = dt.date(year + 1, 1, 1)
    else:
        next_month_first = dt.date(year, month + 1, 1)
    d = next_month_first - dt.timedelta(days=1)
    while not _is_business_day(d):
        d -= dt.timedelta(days=1)
    return d


def report_date_for_month(month_str, rng):
    """Report/key date for a batch month: a business day near month-end,
    with a small per-document drift so not every doc in a month shares the
    exact same date."""
    year, month = int(month_str[:4]), int(month_str[5:7])
    anchor = last_business_day_of_month(year, month)
    drift = int(rng.integers(-2, 1))  # 0, -1 or -2 business-ish days
    candidate = anchor + dt.timedelta(days=drift)
    month_start = dt.date(year, month, 1)
    if candidate < month_start:
        candidate = anchor
    return candidate


# ===========================================================================
# Fixed-width / framed rendering primitives
# ===========================================================================

def truncate_cell(value, width):
    """The exact truncation a rendered cell undergoes (H7 horror, for
    left-aligned free-text columns). This is the single definition of
    "what actually got rendered" -- pad_cell() below uses it for on-page
    rendering, and every renderer's answer-key payload for a truncatable
    string field uses it too (ground-truth principle): the answer key stores
    the truncated rendered string, never the pre-truncation master-data
    value, so scoring a parser against it never measures clairvoyance."""
    text = "" if value is None else str(value)
    return text[:width] if len(text) > width else text


def pad_cell(text, width, align, field=None):
    """Fixed-width cell, truncated at width if too long (H7 horror -- long
    vendor/material names truncated at the column boundary, deliberately).
    Right-aligned cells are always numeric (money/qty/int) in this
    generator's column layouts -- truncating one would silently corrupt a
    total, so that case is a hard error rather than a horror."""
    raw = "" if text is None else str(text)
    if align == "R" and len(raw) > width:
        raise ValueError(
            f"numeric cell {field!r} value {raw!r} (length {len(raw)}) exceeds column width {width} -- "
            f"a right-aligned column must never truncate (it would silently corrupt arithmetic)"
        )
    truncated = truncate_cell(raw, width)
    return truncated.rjust(width) if align == "R" else truncated.ljust(width)


def jittered_width(column, rng):
    base = column["width"]
    if column.get("jitter"):
        return base + int(rng.integers(0, config.COLUMN_WIDTH_JITTER_MAX + 1))
    return base


def build_row(values_by_field, columns, widths, sep=" "):
    cells = [pad_cell(values_by_field.get(c["field"], ""), widths[c["field"]], c["align"], field=c["field"]) for c in columns]
    return sep.join(cells).rstrip() if sep == " " else sep + sep.join(cells) + sep


def header_line(columns, widths, sep=" "):
    cells = [pad_cell(c["header"], widths[c["field"]], c["align"] if c["align"] == "L" else "R", field=c["field"]) for c in columns]
    return sep.join(cells).rstrip() if sep == " " else sep + sep.join(cells) + sep


def frame_rule(columns, widths):
    """FRAMES ON style rule line: ----+----+---- (ME2M)."""
    return "+".join("-" * (widths[c["field"]] + 2) for c in columns)


def pipe_row(values_by_field, columns, widths):
    cells = [f" {pad_cell(values_by_field.get(c['field'], ''), widths[c['field']], c['align'], field=c['field'])} " for c in columns]
    return "|" + "|".join(cells) + "|"


def resolve_widths(columns, rng):
    return {c["field"]: jittered_width(c, rng) for c in columns}


def reorder_columns(base_columns, field_order, extra_columns=None):
    """Returns column defs in a new order (V-class layout variants).
    extra_columns supplies rendered-only columns (e.g. Zuordnung) not present
    in base_columns; their data never enters the schema payload."""
    by_field = {c["field"]: c for c in base_columns}
    if extra_columns:
        for c in extra_columns:
            by_field[c["field"]] = c
    return [by_field[f] for f in field_order]


def insert_column(base_columns, new_column, after_field):
    """Inserts a rendered-only column after a given field (F-class ME2M
    'system patch' -- shifts every subsequent column)."""
    result = []
    for c in base_columns:
        result.append(c)
        if c["field"] == after_field:
            result.append(new_column)
    return result


# ===========================================================================
# Pagination engine (repeated headers, page counter, form feed; metadata
# block only on the first "logical" header)
# ===========================================================================

def render_paginated(report_title, meta_lines, colheader_lines, item_lines, footer_lines,
                      effective_page_height, extra_header_line=None, rule_width=132):
    """Builds one paginated section (report header repeats every page; the
    metadata/selection block appears once, at the top). Returns the full
    text with '\\f' page breaks."""
    fixed_lines_per_page = 2  # title line + dash rule, repeated every page
    capacity = max(effective_page_height - fixed_lines_per_page, 10)

    page1_prefix = list(meta_lines)
    if extra_header_line:
        page1_prefix.append(extra_header_line)
    page1_prefix.append("")
    page1_prefix.extend(colheader_lines)

    pages = [page1_prefix[:]]
    remaining = capacity - len(pages[0])

    def new_page():
        nonlocal remaining
        pages.append(list(colheader_lines))
        remaining = capacity - len(pages[-1])

    for line in item_lines:
        if remaining <= 0:
            new_page()
        pages[-1].append(line)
        remaining -= 1

    if remaining < len(footer_lines):
        new_page()
    pages[-1].extend(footer_lines)

    rendered_pages = []
    for i, body in enumerate(pages, start=1):
        title = f"{report_title}" + " " * max(rule_width - len(report_title) - 14, 2) + f"Seite {i:>5}"
        rule = "-" * rule_width
        rendered_pages.append("\n".join([title, rule] + body))
    # The form feed sits alone on its own line between pages (not glued to
    # the previous page's last line or the next page's title) so that naive
    # line-based text processing -- ours in validate_data.py, and any
    # downstream parser -- never silently merges two lines across a page
    # break.
    return "\n\f\n".join(rendered_pages) + "\n"


# ===========================================================================
# Master-data sampling helpers
# ===========================================================================

def sample_in_band(rng, lo, hi, margin_fraction=config.BAND_SAMPLING_MARGIN_FRACTION):
    """Sample inside [lo, hi] with an inset margin so downstream rounding
    (e.g. quantity rounding) can never push the recomputed amount outside
    the declared band (amount-plausibility rule)."""
    span = hi - lo
    margin = max(span * margin_fraction, 1.0)
    if hi - margin <= lo + margin:
        return (lo + hi) / 2.0
    return float(rng.uniform(lo + margin, hi - margin))


def pick_vat_rate(rng):
    return float(rng.choice(config.VAT_RATES, p=config.VAT_RATE_WEIGHTS))


# ===========================================================================
# Sequential document/business-object numbering (deterministic counters --
# generation order is fixed by month/seq iteration, so this is reproducible)
# ===========================================================================

class Counters:
    def __init__(self):
        self.fbl3n_doc = 1900000000
        self.po = 4500010000
        self.sales_doc = 5000010000
        self.kr_doc = 1700000000
        self.kz_doc = 1500000000
        self.ka_doc = 1600000000
        self.clearing_doc = 1400000000

    def next_fbl3n_doc(self):
        self.fbl3n_doc += 1
        return str(self.fbl3n_doc)

    def next_po(self):
        self.po += 10
        return str(self.po)

    def next_sales_doc(self):
        self.sales_doc += 1
        return str(self.sales_doc)

    def next_kr(self):
        self.kr_doc += 1
        return str(self.kr_doc)

    def next_kz(self):
        self.kz_doc += 1
        return str(self.kz_doc)

    def next_ka(self):
        self.ka_doc += 1
        return str(self.ka_doc)

    def next_clearing(self):
        self.clearing_doc += 1
        return str(self.clearing_doc)


COUNTERS = Counters()

# ===========================================================================
# doc_id / answer-key helpers
# ===========================================================================

def make_doc_id(month, txn_type, seq):
    return f"{month}_{txn_type}_{seq:02d}"


def money2(value):
    return round(float(value), 2)


def write_document(doc_id, txn_type, month, doc_class, planted_mechanism, text, parse_payload):
    """Writes the .txt and .json answer-key pair for one document. Confirms
    output paths never collide with any source/input path (there is no
    input corpus here, but the check is cheap insurance for the convention)."""
    config.DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    config.ANSWER_KEY_DIR.mkdir(parents=True, exist_ok=True)

    txt_path = config.DOCUMENTS_DIR / f"{doc_id}.txt"
    json_path = config.ANSWER_KEY_DIR / f"{doc_id}.json"
    assert txt_path.resolve() != json_path.resolve()

    with open(txt_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    errors = schemas.validate_parse(txn_type, parse_payload)
    if errors:
        raise ValueError(f"{doc_id}: answer-key payload fails schema validation: {errors}")

    answer_key = {
        "doc_id": doc_id,
        "transaction_type": txn_type,
        "month": month,
        "doc_class": doc_class,
        "planted_mechanism": planted_mechanism,
        "parse": parse_payload,
    }
    with open(json_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(answer_key, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ===========================================================================
# PO ledger (the shared economic activity that ME2M and
# FBL1N must reconcile against). Built once, up front, for the whole year;
# ME2M documents render directly from it, FBL1N invoices (KR items) are
# matched against it below by select_po_for_invoice().
# ===========================================================================

def build_po_ledger():
    """One ME2M line item = one single-item PO ledger entry (declared
    simplification -- see report). Returns:
      ledger_by_doc:    {(month, seq): [entry, ...]}   -- for ME2M rendering
      ledger_by_vendor: {vendor_number: [entry, ...]}  -- for FBL1N reconciliation
    Entries are dicts; 'remaining' is mutated downstream as FBL1N invoices
    consume PO value."""
    ledger_by_doc = {}
    ledger_by_vendor = {v["number"]: [] for v in config.VENDORS}

    for month in config.MONTHS:
        year, mo = int(month[:4]), int(month[5:7])
        month_start = dt.date(year, mo, 1)
        month_end = (dt.date(year + 1, 1, 1) if mo == 12 else dt.date(year, mo + 1, 1)) - dt.timedelta(days=1)
        for seq in range(1, config.DOCS_PER_TYPE_PER_MONTH + 1):
            doc_id = make_doc_id(month, "ME2M", seq)
            rng = doc_rng(doc_id)
            # report_date_for_month must be the FIRST draw from this rng, to
            # stay in lockstep with render_me2m_document()'s own fresh
            # doc_rng(doc_id) instance (same seed, same first operation ->
            # same value). Coherence rule: order_date must never be
            # after the document's own report_date.
            report_date = report_date_for_month(month, rng)
            n_lines = int(rng.integers(*config.LINE_ITEM_RANGE["ME2M"]))
            entries = []
            for _ in range(n_lines):
                vendor = config.VENDORS[rng.integers(0, len(config.VENDORS))]
                material = config.MATERIALS[rng.integers(0, len(config.MATERIALS))]
                order_date = sample_business_weighted_date(rng, month_start, min(month_end, report_date))
                unit_price = round(sample_in_band(rng, material["price_min"], material["price_max"]), 2)
                target_value = sample_in_band(rng, vendor["order_value_min"], vendor["order_value_max"])
                qty_lo, qty_hi = config.MATERIAL_QUANTITY_RANGE[material["category"]]
                raw_qty = target_value / max(unit_price, 0.01)
                raw_qty = min(max(raw_qty, qty_lo), qty_hi)
                quantity = round(raw_qty) if material["unit"] == "ST" else round(raw_qty, 3)
                quantity = max(quantity, 1 if material["unit"] == "ST" else 0.5)
                net_value = money2(quantity * unit_price)

                still_open = rng.random() >= 0.6
                fraction = float(rng.uniform(0.05, 1.0)) if still_open else 0.0
                still_qty = round(quantity * fraction, 3) if material["unit"] != "ST" else round(quantity * fraction)
                still_value = money2(net_value * fraction)

                entry = {
                    "po_number": COUNTERS.next_po(),
                    "item": 1,
                    "order_date": order_date,
                    "vendor_number": vendor["number"],
                    "material_number": material["number"],
                    "quantity": quantity,
                    "unit": material["unit"],
                    "net_price": unit_price,
                    "net_value": net_value,
                    # ME2M / PO ledger reporting currency is always EUR (purchasing-org
                    # reporting currency) even for SEK-home vendors -- SEK only ever
                    # surfaces on the FBL1N side (the vendor's invoicing currency),
                    # which is the one place the design plants a currency-change
                    # horror. Keeps ME2M's single grand_total meaningful (no mixing
                    # EUR and SEK into one sum).
                    "currency": "EUR",
                    "still_to_deliver_qty": still_qty,
                    "still_to_deliver_value": still_value,
                    "remaining": net_value,
                }
                entries.append(entry)
                ledger_by_vendor[vendor["number"]].append(entry)

            ledger_by_doc[(month, seq)] = entries

    for vendor_number in ledger_by_vendor:
        ledger_by_vendor[vendor_number].sort(key=lambda e: e["order_date"])

    return ledger_by_doc, ledger_by_vendor


def select_po_for_invoice(po_pool_for_vendor, report_date, max_lag_days=config.FBL1N_INVOICE_LAG_DAYS_MAX):
    """FIFO reconciliation rule: among a vendor's PO ledger
    entries with remaining capacity and order_date < report_date, return the
    OLDEST eligible one, or None. This exact rule is reused (independently
    re-derived from answer-key data only) by validate_data.py's rule-2 check,
    so generation and validation can never disagree about feasibility."""
    eligible = [po for po in po_pool_for_vendor
                if po["remaining"] > 0.01 and (report_date - po["order_date"]).days >= 1]
    if not eligible:
        return None
    eligible.sort(key=lambda po: po["order_date"])
    return eligible[0]


# ===========================================================================
# FBL3N -- G/L account line items
# ===========================================================================

def render_fbl3n_document(month, seq, doc_class):
    doc_id = make_doc_id(month, "FBL3N", seq)
    rng = doc_rng(doc_id)
    year, mo = int(month[:4]), int(month[5:7])
    period_from = dt.date(year, mo, 1)
    period_to = (dt.date(year + 1, 1, 1) if mo == 12 else dt.date(year, mo + 1, 1)) - dt.timedelta(days=1)
    report_date = report_date_for_month(month, rng)

    global_index = config.MONTHS.index(month) * config.DOCS_PER_TYPE_PER_MONTH + (seq - 1)
    account = config.GL_ACCOUNTS[global_index % len(config.GL_ACCOUNTS)]
    user = str(rng.choice(config.SAP_USERS))

    planted_mechanism = None
    if doc_class == "V":
        columns = reorder_columns(config.FBL3N_COLUMNS, config.FBL3N_V_FIELD_ORDER,
                                   extra_columns=[config.FBL3N_V_EXTRA_COLUMN])
        planted_mechanism = "layout_variant:reordered_columns+zuordnung"
    else:
        # S never occurs for FBL3N (relocated to ME2M; see config note).
        columns = config.FBL3N_COLUMNS

    widths = resolve_widths(columns, rng)
    n_lines = int(rng.integers(*config.LINE_ITEM_RANGE["FBL3N"]))

    line_items_payload = []
    item_lines = []
    sum_debit = 0.0
    sum_credit = 0.0
    sum_tax = 0.0

    for i in range(n_lines):
        posting_date = sample_business_weighted_date(rng, period_from, min(period_to, report_date))
        document_number = COUNTERS.next_fbl3n_doc()
        document_type = str(rng.choice(config.FBL3N_DOCUMENT_TYPES, p=config.FBL3N_DOCUMENT_TYPE_WEIGHTS))
        debit_credit = str(rng.choice(["S", "H"], p=[config.FBL3N_DEBIT_CREDIT_WEIGHTS["S"],
                                                       config.FBL3N_DEBIT_CREDIT_WEIGHTS["H"]]))
        magnitude = sample_in_band(rng, account["amount_min"], account["amount_max"])
        signed_amount = money2(magnitude if debit_credit == "S" else -magnitude)
        vat_rate = pick_vat_rate(rng) if account["vat_relevant"] else 0.0
        signed_tax = money2(signed_amount * vat_rate)
        clearing_document = COUNTERS.next_clearing() if rng.random() < 0.3 else None
        reference = f"RE{int(rng.integers(100000, 999999))}" if rng.random() < 0.6 else None
        text = str(rng.choice(config.FBL3N_TEXT_OPTIONS))

        # Ground-truth principle: FBL3N_V_FIELD_ORDER deliberately drops the
        # Referenz column from the V-layout (not merely reorders it), so a
        # V-class document never prints a reference value at all -- storing
        # the internally-generated one anyway would be answer-key
        # information absent from the page, the same clairvoyance problem
        # the ground-truth principle rules out for truncated cells. The rng
        # draw above still always happens (determinism, byte-identical
        # non-V-class output); only the payload value is suppressed.
        reference_payload_value = None if doc_class == "V" else reference

        line_items_payload.append({
            "posting_date": posting_date.isoformat(),
            "document_number": document_number,
            "document_type": document_type,
            "debit_credit": debit_credit,
            "amount": signed_amount,
            "tax_amount": signed_tax,
            "clearing_document": clearing_document,
            "reference": reference_payload_value,
            "text": text,
        })
        if debit_credit == "S":
            sum_debit = money2(sum_debit + signed_amount)
        else:
            sum_credit = money2(sum_credit + signed_amount)
        sum_tax = money2(sum_tax + signed_tax)

        row_values = {
            "posting_date": de_date(posting_date),
            "document_number": document_number,
            "document_type": document_type,
            "debit_credit": debit_credit,
            "amount": de_money(signed_amount),
            "tax_amount": de_money(signed_tax),
            "clearing_document": clearing_document or "",
            "reference": reference or "",
            "text": text,
        }
        if doc_class == "V":
            row_values["assignment_extra"] = f"KST-{int(rng.integers(1000, 9999))}"
        item_lines.append(build_row(row_values, columns, widths))

    balance = money2(sum_debit + sum_credit)

    meta_lines = [
        f"Buchungskreis: {config.COMPANY_CODE}   {config.COMPANY_NAME}",
        f"Sachkonto: {account['number']}   {account['name']}",
        f"Zeitraum: {de_date(period_from)} - {de_date(period_to)}",
        f"Datum: {de_date(report_date)}   Benutzer: {user}",
    ]
    extra_header_line = "Selektionsvariante: Z_MONATSABSCHLUSS" if rng.random() < config.EXTRA_HEADER_LINE_PROBABILITY else None

    colheader_lines = [header_line(columns, widths), "-" * len(header_line(columns, widths))]

    totals_rows = []
    tax_line = f"* {'Summe Steuerbetrag':<30}{de_money(sum_tax):>15}"
    debit_credit_lines = [
        f"* {'Summe Soll':<30}{de_money(sum_debit):>15}",
        f"* {'Summe Haben':<30}{de_money(sum_credit):>15}",
        f"* {'Saldo':<30}{de_money(balance):>15}",
    ]
    totals_rows = debit_credit_lines + [tax_line]

    rule_width = max(len(header_line(columns, widths)), 100)
    text_out = render_paginated(
        config.REPORT_TITLES["FBL3N"], meta_lines, colheader_lines, item_lines, totals_rows,
        config.PAGE_HEIGHT_LINES + int(rng.integers(-config.PAGE_BREAK_DRIFT, config.PAGE_BREAK_DRIFT + 1)),
        extra_header_line=extra_header_line, rule_width=rule_width,
    )

    parse_payload = {
        "header": {
            "company_code": config.COMPANY_CODE,
            "gl_account": account["number"],
            "gl_account_name": account["name"],
            "period_from": period_from.isoformat(),
            "period_to": period_to.isoformat(),
            "report_date": report_date.isoformat(),
            "user": user,
        },
        "line_items": line_items_payload,
        "totals": {
            "sum_debit": sum_debit,
            "sum_credit": sum_credit,
            "balance": balance,
        },
    }
    return doc_id, text_out, parse_payload, planted_mechanism


# ===========================================================================
# ME2M -- Purchase orders by material
# ===========================================================================

def me2m_summary_line(label, value, currency):
    return f"  {label:<55}{de_money(value):>15} {currency}"


def render_me2m_document(month, seq, doc_class, entries):
    doc_id = make_doc_id(month, "ME2M", seq)
    rng = doc_rng(doc_id)
    year, mo = int(month[:4]), int(month[5:7])
    month_start = dt.date(year, mo, 1)
    month_end = (dt.date(year + 1, 1, 1) if mo == 12 else dt.date(year, mo + 1, 1)) - dt.timedelta(days=1)
    report_date = report_date_for_month(month, rng)
    user = str(rng.choice(config.SAP_USERS))

    planted_mechanism = None
    if doc_class == "F":
        columns = insert_column(config.ME2M_COLUMNS, config.ME2M_F_EXTRA_COLUMN, config.ME2M_F_INSERT_AFTER)
        planted_mechanism = config.ME2M_F_PLANTED_MECHANISM
    elif doc_class == "S":
        # Silent error (iteration 3): layout stays canonical; the VALUES of
        # net_price and still_to_deliver_value are rendered into each other's
        # columns (see the row loop below). The payload keeps the true values.
        columns = config.ME2M_COLUMNS
        planted_mechanism = config.ME2M_S_PLANTED_MECHANISM
    else:
        columns = config.ME2M_COLUMNS
    widths = resolve_widths(columns, rng)

    # Group this document's ledger entries by vendor for the subtotal rows.
    by_vendor = {}
    for e in entries:
        by_vendor.setdefault(e["vendor_number"], []).append(e)

    item_lines = []
    line_items_payload = []
    vendor_subtotals = []
    grand_total = 0.0
    for vendor_number in sorted(by_vendor):
        vendor = config.VENDORS_BY_NUMBER[vendor_number]
        vendor_total = 0.0
        for e in by_vendor[vendor_number]:
            material = config.MATERIALS_BY_NUMBER[e["material_number"]]
            # Ground-truth principle: the answer key stores the string as it
            # actually appears on the page, not the master-data original.
            # Computed from the same per-document widths used for rendering,
            # so this never changes what gets rendered (see truncate_cell).
            rendered_vendor_name = truncate_cell(vendor["name"], widths["vendor_name"]).strip()
            rendered_material_text = truncate_cell(material["text"], widths["material_text"]).strip()
            row_values = {
                "po_number": e["po_number"],
                "item": e["item"],
                "order_date": de_date(e["order_date"]),
                "vendor_number": vendor_number,
                "vendor_name": vendor["name"],
                "material": e["material_number"],
                "material_text": material["text"],
                "quantity": f"{de_qty(e['quantity'], e['unit'])} {e['unit']}",
                "net_price": de_money(e["net_price"]),
                "net_value": de_money(e["net_value"]),
                "currency": e["currency"],
                "still_to_deliver_qty": f"{de_qty(e['still_to_deliver_qty'], e['unit'])} {e['unit']}",
                "still_to_deliver_value": de_money(e["still_to_deliver_value"]),
            }
            if doc_class == "F":
                gr_date = e["order_date"] + dt.timedelta(days=int(rng.integers(3, 21)))
                row_values["goods_receipt_date"] = de_date(min(gr_date, report_date))
            elif doc_class == "S":
                # The document lies: swap the RENDERED values of the two money
                # columns; headers and the answer-key payload stay truthful.
                fa, fb = config.ME2M_S_VALUE_SWAP
                row_values[fa], row_values[fb] = row_values[fb], row_values[fa]
            item_lines.append(pipe_row(row_values, columns, widths))

            line_items_payload.append({
                "po_number": e["po_number"],
                "item": e["item"],
                "order_date": e["order_date"].isoformat(),
                "vendor_number": vendor_number,
                "vendor_name": rendered_vendor_name,
                "material": e["material_number"],
                "material_text": rendered_material_text,
                "quantity": e["quantity"],
                "unit": e["unit"],
                "net_price": e["net_price"],
                "net_value": e["net_value"],
                "currency": e["currency"],
                "still_to_deliver_qty": e["still_to_deliver_qty"],
                "still_to_deliver_value": e["still_to_deliver_value"],
            })
            vendor_total = money2(vendor_total + e["net_value"])
        item_lines.append(frame_rule(columns, widths))
        item_lines.append(me2m_summary_line(f"Summe {vendor['name']}", vendor_total, by_vendor[vendor_number][0]["currency"]))
        item_lines.append(frame_rule(columns, widths))
        vendor_subtotals.append({"vendor_number": vendor_number, "total_value": vendor_total})
        grand_total = money2(grand_total + vendor_total)

    meta_lines = [
        f"Einkaufsorganisation: {config.PURCH_ORG}   {config.COMPANY_NAME}",
        f"Selektionszeitraum: {de_date(month_start)} - {de_date(month_end)}",
        f"Datum: {de_date(report_date)}   Benutzer: {user}",
    ]
    extra_header_line = "Selektionsvariante: Z_EINKAUF_MONAT" if rng.random() < config.EXTRA_HEADER_LINE_PROBABILITY else None
    colheader_lines = [frame_rule(columns, widths), pipe_row({c["field"]: c["header"] for c in columns}, columns, widths), frame_rule(columns, widths)]
    footer_lines = [me2m_summary_line("Gesamtsumme", grand_total, "EUR")]

    rule_width = max(len(frame_rule(columns, widths)), 100)
    text_out = render_paginated(
        config.REPORT_TITLES["ME2M"], meta_lines, colheader_lines, item_lines, footer_lines,
        config.PAGE_HEIGHT_LINES + int(rng.integers(-config.PAGE_BREAK_DRIFT, config.PAGE_BREAK_DRIFT + 1)),
        extra_header_line=extra_header_line, rule_width=rule_width,
    )

    parse_payload = {
        "header": {
            "purch_org": config.PURCH_ORG,
            "selection_scope": f"{de_date(month_start)} - {de_date(month_end)}",
            "report_date": report_date.isoformat(),
            "user": user,
        },
        "line_items": line_items_payload,
        "totals": {
            "vendor_subtotals": vendor_subtotals,
            "grand_total": grand_total,
        },
    }
    return doc_id, text_out, parse_payload, planted_mechanism


# ===========================================================================
# VA05 -- List of sales orders
# ===========================================================================

def render_va05_document(month, seq, doc_class):
    doc_id = make_doc_id(month, "VA05", seq)
    rng = doc_rng(doc_id)
    year, mo = int(month[:4]), int(month[5:7])
    period_from = dt.date(year, mo, 1)
    period_to = (dt.date(year + 1, 1, 1) if mo == 12 else dt.date(year, mo + 1, 1)) - dt.timedelta(days=1)
    report_date = report_date_for_month(month, rng)
    user = str(rng.choice(config.SAP_USERS))

    planted_mechanism = None
    if doc_class == "V":
        columns = reorder_columns(config.VA05_COLUMNS, config.VA05_V_FIELD_ORDER,
                                   extra_columns=[config.VA05_V_EXTRA_COLUMN])
        planted_mechanism = "layout_variant:reordered_columns+projekt"
    else:
        columns = config.VA05_COLUMNS
        if doc_class == "F":
            planted_mechanism = config.VA05_F_PLANTED_MECHANISM
    widths = resolve_widths(columns, rng)

    regular_customers = [c for c in config.CUSTOMERS if not c["is_horror_name"]]
    horror_customers = [c for c in config.CUSTOMERS if c["is_horror_name"]]

    n_lines = int(rng.integers(*config.LINE_ITEM_RANGE["VA05"]))
    item_lines = [header_line(columns, widths, sep="|"), "-" * (sum(widths.values()) + len(columns) * 3 + 1)]
    line_items_payload = []
    total_net_value = 0.0

    for _ in range(n_lines):
        if doc_class == "F" and rng.random() < 0.4:
            customer = horror_customers[rng.integers(0, len(horror_customers))]
        else:
            customer = regular_customers[rng.integers(0, len(regular_customers))]
        material = config.MATERIALS[rng.integers(0, len(config.MATERIALS))]
        doc_date = sample_business_weighted_date(rng, period_from, min(period_to, report_date))
        base_price = sample_in_band(rng, material["price_min"], material["price_max"])
        markup = float(rng.uniform(*config.SALES_MARKUP_RANGE))
        sales_price = base_price * markup
        qty_lo, qty_hi = config.MATERIAL_QUANTITY_RANGE[material["category"]]
        quantity = int(rng.integers(qty_lo, qty_hi + 1)) if material["unit"] == "ST" else round(float(rng.uniform(qty_lo, qty_hi)), 3)
        net_value = money2(quantity * sales_price)
        delivery_status = str(rng.choice(config.DELIVERY_STATUS_OPTIONS))
        sales_document = COUNTERS.next_sales_doc()

        # Ground-truth principle: store what the cell actually
        # shows, not the master-data original -- see truncate_cell.
        rendered_sold_to = truncate_cell(customer["name"], widths["sold_to"]).strip()
        rendered_delivery_status = truncate_cell(delivery_status, widths["delivery_status"]).strip()

        row_values = {
            "sales_document": sales_document,
            "doc_date": de_date(doc_date),
            "sold_to": customer["name"],
            "material": material["number"],
            "order_quantity": f"{de_qty(quantity, material['unit'])} {material['unit']}",
            "net_value": de_money(net_value),
            "currency": "EUR",
            "delivery_status": delivery_status,
        }
        if doc_class == "V":
            row_values["wbs_element"] = f"P-{int(rng.integers(1000, 9999))}"
        item_lines.append(pipe_row(row_values, columns, widths))

        line_items_payload.append({
            "sales_document": sales_document,
            "doc_date": doc_date.isoformat(),
            "sold_to": rendered_sold_to,
            "material": material["number"],
            "order_quantity": quantity,
            "unit": material["unit"],
            "net_value": net_value,
            "currency": "EUR",
            "delivery_status": rendered_delivery_status,
        })
        total_net_value = money2(total_net_value + net_value)

    meta_lines = [
        f"Verkaufsorganisation: {config.SALES_ORG}   {config.COMPANY_NAME}",
        f"Zeitraum: {de_date(period_from)} - {de_date(period_to)}",
        f"Datum: {de_date(report_date)}   Benutzer: {user}",
    ]
    extra_header_line = "Selektionsvariante: Z_VERTRIEB_MONAT" if rng.random() < config.EXTRA_HEADER_LINE_PROBABILITY else None
    # "Gesamtsumme" (ME2M convention) rather than a bespoke label (ground-truth principle, Fix 2).
    footer_lines = [f"  {'Gesamtsumme':<55}{de_money(total_net_value):>15} EUR"]

    rule_width = max(len(item_lines[0]), 100)
    text_out = render_paginated(
        config.REPORT_TITLES["VA05"], meta_lines, item_lines[:2], item_lines[2:], footer_lines,
        config.PAGE_HEIGHT_LINES + int(rng.integers(-config.PAGE_BREAK_DRIFT, config.PAGE_BREAK_DRIFT + 1)),
        extra_header_line=extra_header_line, rule_width=rule_width,
    )

    parse_payload = {
        "header": {
            "sales_org": config.SALES_ORG,
            "period_from": period_from.isoformat(),
            "period_to": period_to.isoformat(),
            "report_date": report_date.isoformat(),
            "user": user,
        },
        "line_items": line_items_payload,
        "totals": {"total_net_value": total_net_value},
    }
    return doc_id, text_out, parse_payload, planted_mechanism


# ===========================================================================
# FBL1N -- Vendor line items (one vendor per page; the PO
# reconciliation is enforced here via select_po_for_invoice against the
# ME2M ledger built earlier in the same run)
# ===========================================================================

def _fbl1n_build_vendor_items(vendor, rng, report_date, ledger_by_vendor, force_currency_split):
    """Builds one vendor's line items (KR reconciled against the PO ledger,
    KZ clearing some of them, KA for the rest) and returns that list. Each
    item's 'currency' is the vendor's home currency, except when
    force_currency_split is set (F-class FBL1N): then a contiguous tail
    slice of the vendor's items is relabelled to the other currency,
    planting the mid-table currency-change horror."""
    n_total = int(rng.integers(*config.LINE_ITEM_RANGE["FBL1N"]))
    n_ka = max(1, round(n_total * config.FBL1N_KA_SHARE))
    n_kr_attempts = n_total - n_ka

    items = []
    po_pool = ledger_by_vendor[vendor["number"]]

    for _ in range(n_kr_attempts):
        po = select_po_for_invoice(po_pool, report_date)
        if po is not None:
            full_clear = rng.random() < config.FBL1N_KR_CLEARED_FRACTION
            partial_clear = (not full_clear) and (rng.random() < (config.FBL1N_KR_PARTIAL_FRACTION /
                                                                    (1 - config.FBL1N_KR_CLEARED_FRACTION)))
            consume_fraction = 1.0 if (full_clear or rng.random() < 0.7) else float(rng.uniform(0.3, 0.8))
            invoice_amount = money2(po["remaining"] * consume_fraction)
            if invoice_amount <= 0.01:
                continue
            po["remaining"] = money2(po["remaining"] - invoice_amount)

            max_offset = min(config.FBL1N_INVOICE_LAG_DAYS_MAX, (report_date - po["order_date"]).days)
            invoice_date = po["order_date"] + dt.timedelta(days=int(rng.integers(1, max(max_offset, 1) + 1)))
            invoice_date = min(invoice_date, report_date)
            posting_date = min(invoice_date + dt.timedelta(days=int(rng.integers(0, 3))), report_date)
            due_date = min(posting_date + dt.timedelta(days=vendor["payment_terms_days"]), YEAR_END)

            kr_doc = COUNTERS.next_kr()
            status = "open"
            clearing_document = None
            if full_clear or partial_clear:
                status = "cleared" if full_clear else "partial"
                clearing_document = COUNTERS.next_clearing()
                kz_fraction = 1.0 if full_clear else float(rng.uniform(0.3, 0.8))
                kz_amount = money2(invoice_amount * kz_fraction)
                kz_posting = min(posting_date + dt.timedelta(days=int(rng.integers(1, max(vendor["payment_terms_days"], 2)))), report_date)
                kz_doc_number = COUNTERS.next_kz()
                items.append({
                    "status": status, "document_number": kz_doc_number, "document_type": "KZ",
                    "document_date": kz_posting, "posting_date": kz_posting, "due_date": kz_posting,
                    "debit_credit": "S", "amount": kz_amount, "currency": vendor["currency"],
                    "clearing_document": clearing_document,
                })
            items.append({
                "status": status, "document_number": kr_doc, "document_type": "KR",
                "document_date": invoice_date, "posting_date": posting_date, "due_date": due_date,
                "debit_credit": "H", "amount": money2(-invoice_amount), "currency": vendor["currency"],
                "clearing_document": clearing_document,
            })
            continue
        n_ka += 1  # no eligible PO -- add one more KA below instead

    for _ in range(n_ka):
        magnitude = sample_in_band(rng, vendor["order_value_min"] * 0.1, vendor["order_value_max"] * 0.3)
        posting_date = sample_business_weighted_date(rng, max(YEAR_START, report_date - dt.timedelta(days=180)), report_date)
        items.append({
            "status": "open", "document_number": COUNTERS.next_ka(), "document_type": "KA",
            "document_date": posting_date, "posting_date": posting_date, "due_date": posting_date,
            "debit_credit": "H", "amount": money2(-magnitude), "currency": vendor["currency"],
            "clearing_document": None,
        })

    if not items:
        # Guaranteed fallback so every vendor page has at least one line.
        posting_date = report_date
        items.append({
            "status": "open", "document_number": COUNTERS.next_ka(), "document_type": "KA",
            "document_date": posting_date, "posting_date": posting_date, "due_date": posting_date,
            "debit_credit": "H", "amount": -100.0, "currency": vendor["currency"],
            "clearing_document": None,
        })

    if force_currency_split and len(items) >= 2:
        split_point = max(1, int(len(items) * 0.6))
        alt_currency = "EUR" if vendor["currency"] != "EUR" else "SEK"
        for item in items[split_point:]:
            item["currency"] = alt_currency
    else:
        items.sort(key=lambda it: it["posting_date"])

    return items


def render_fbl1n_document(month, seq, doc_class, ledger_by_vendor):
    doc_id = make_doc_id(month, "FBL1N", seq)
    rng = doc_rng(doc_id)
    report_date = report_date_for_month(month, rng)
    user = str(rng.choice(config.SAP_USERS))

    n_vendors = int(rng.integers(*config.FBL1N_VENDORS_PER_DOC_RANGE))
    planted_mechanism = config.FBL1N_F_PLANTED_MECHANISM if doc_class == "F" else None

    all_numbers = [v["number"] for v in config.VENDORS]
    forced_vendor = None
    if doc_class == "F":
        forced_vendor = str(rng.choice(config.SEK_VENDOR_NUMBERS))
        remaining_pool = [n for n in all_numbers if n != forced_vendor]
        chosen = list(rng.choice(remaining_pool, size=n_vendors - 1, replace=False)) + [forced_vendor]
    else:
        chosen = list(rng.choice(all_numbers, size=n_vendors, replace=False))
    rng.shuffle(chosen)

    columns = config.FBL1N_COLUMNS
    widths = resolve_widths(columns, rng)

    vendor_pages_text = []
    vendors_payload = []

    for vendor_number in chosen:
        vendor = config.VENDORS_BY_NUMBER[vendor_number]
        force_split = (doc_class == "F" and vendor_number == forced_vendor)
        items = _fbl1n_build_vendor_items(vendor, rng, report_date, ledger_by_vendor, force_split)

        item_lines = []
        line_items_payload = []
        totals_by_currency = {}
        for it in items:
            row_values = {
                "status": config.FBL1N_STATUS_CODES[it["status"]],
                "document_number": it["document_number"],
                "document_type": it["document_type"],
                "document_date": de_date(it["document_date"]),
                "posting_date": de_date(it["posting_date"]),
                "due_date": de_date(it["due_date"]),
                "debit_credit": it["debit_credit"],
                "amount": de_money(it["amount"]),
                "currency": it["currency"],
                "clearing_document": it["clearing_document"] or "",
            }
            item_lines.append(build_row(row_values, columns, widths))

            line_items_payload.append({
                "status": it["status"],
                "document_number": it["document_number"],
                "document_type": it["document_type"],
                "document_date": it["document_date"].isoformat(),
                "posting_date": it["posting_date"].isoformat(),
                "due_date": it["due_date"].isoformat(),
                "debit_credit": it["debit_credit"],
                "amount": it["amount"],
                "currency": it["currency"],
                "clearing_document": it["clearing_document"],
            })
            bucket = totals_by_currency.setdefault(it["currency"], {"open_total": 0.0, "cleared_total": 0.0})
            if it["status"] == "cleared":
                bucket["cleared_total"] = money2(bucket["cleared_total"] + it["amount"])
            else:
                bucket["open_total"] = money2(bucket["open_total"] + it["amount"])

        vendor_totals_payload = [
            {"currency": cur, "open_total": tot["open_total"], "cleared_total": tot["cleared_total"]}
            for cur, tot in sorted(totals_by_currency.items())
        ]

        meta_lines = [
            f"Kreditor: {vendor_number}   {vendor['name']}",
            f"Buchungskreis: {config.COMPANY_CODE}   {config.COMPANY_NAME}",
            f"Stichtag: {de_date(report_date)}   Benutzer: {user}",
        ]
        colheader_lines = [header_line(columns, widths), "-" * len(header_line(columns, widths))]
        footer_lines = [
            f"* {'Summe offen/teilweise ' + cur:<30}{de_money(tot['open_total']):>15}"
            for cur, tot in sorted(totals_by_currency.items())
        ] + [
            f"* {'Summe ausgeglichen ' + cur:<30}{de_money(tot['cleared_total']):>15}"
            for cur, tot in sorted(totals_by_currency.items())
        ]

        rule_width = max(len(header_line(columns, widths)), 100)
        vendor_text = render_paginated(
            config.REPORT_TITLES["FBL1N"], meta_lines, colheader_lines, item_lines, footer_lines,
            config.PAGE_HEIGHT_LINES + int(rng.integers(-config.PAGE_BREAK_DRIFT, config.PAGE_BREAK_DRIFT + 1)),
            rule_width=rule_width,
        )
        vendor_pages_text.append(vendor_text.rstrip("\n"))

        vendors_payload.append({
            "vendor_number": vendor_number,
            "vendor_name": vendor["name"],
            "line_items": line_items_payload,
            "vendor_totals": vendor_totals_payload,
        })

    text_out = "\n\f\n".join(vendor_pages_text) + "\n"

    parse_payload = {
        "header": {
            "company_code": config.COMPANY_CODE,
            "key_date": report_date.isoformat(),
            "report_date": report_date.isoformat(),
            "user": user,
        },
        "vendors": vendors_payload,
        "totals": {},
    }
    return doc_id, text_out, parse_payload, planted_mechanism


# ===========================================================================
# MB52 -- Warehouse stock (hierarchical: plant -> storage location -> material)
# ===========================================================================

def render_mb52_document(month, seq, doc_class):
    doc_id = make_doc_id(month, "MB52", seq)
    rng = doc_rng(doc_id)
    report_date = report_date_for_month(month, rng)
    user = str(rng.choice(config.SAP_USERS))

    columns = config.MB52_COLUMNS
    widths = resolve_widths(columns, rng)

    plant_codes = list(config.PLANTS.keys())
    n_plants = int(rng.integers(1, len(plant_codes) + 1))
    chosen_plants = sorted(rng.choice(plant_codes, size=n_plants, replace=False))

    n_total = int(rng.integers(*config.LINE_ITEM_RANGE["MB52"]))
    groups = []  # (plant, storloc)
    for plant in chosen_plants:
        n_storlocs = int(rng.integers(2, len(config.STORAGE_LOCATIONS) + 1))
        for storloc in sorted(rng.choice(config.STORAGE_LOCATIONS, size=n_storlocs, replace=False)):
            groups.append((plant, storloc))
    lines_per_group = max(1, n_total // max(len(groups), 1))

    item_lines = []
    line_items_payload = []
    plant_totals = {p: 0.0 for p in chosen_plants}
    grand_total = 0.0

    for plant in chosen_plants:
        item_lines.append(f"Werk {plant}  {config.PLANTS[plant]}")
        plant_groups = [g for g in groups if g[0] == plant]
        for (p, storloc) in plant_groups:
            item_lines.append(" " * config.MB52_STORLOC_INDENT + f"Lagerort {storloc}")
            chosen_materials = [config.MATERIALS[int(i)] for i in rng.integers(0, len(config.MATERIALS), size=lines_per_group)]
            for material in chosen_materials:
                unit = material["unit"]
                lo, hi = config.MB52_STOCK_QTY_RANGE["unrestricted"]
                unrestricted = round(float(rng.uniform(lo, hi)), 3 if unit != "ST" else 0)
                lo, hi = config.MB52_STOCK_QTY_RANGE["quality_inspection"]
                quality = round(float(rng.uniform(lo, hi)), 3 if unit != "ST" else 0)
                lo, hi = config.MB52_STOCK_QTY_RANGE["blocked"]
                blocked = round(float(rng.uniform(lo, hi)), 3 if unit != "ST" else 0)
                unit_price = sample_in_band(rng, material["price_min"], material["price_max"])
                value_unrestricted = money2(unrestricted * unit_price)

                # Ground-truth principle: store what the cell
                # actually shows, not the master-data original -- see truncate_cell.
                rendered_material_text = truncate_cell(material["text"], widths["material_text"]).strip()

                row_values = {
                    "material": material["number"],
                    "material_text": material["text"],
                    "unit": unit,
                    "unrestricted": de_qty(unrestricted, unit),
                    "quality_inspection": de_qty(quality, unit),
                    "blocked": de_qty(blocked, unit),
                    "value_unrestricted": de_money(value_unrestricted),
                    "currency": "EUR",
                }
                item_lines.append(" " * config.MB52_MATERIAL_INDENT + build_row(row_values, columns, widths))

                line_items_payload.append({
                    "material": material["number"],
                    "material_text": rendered_material_text,
                    "plant": plant,
                    "storage_location": storloc,
                    "unit": unit,
                    "unrestricted": unrestricted,
                    "quality_inspection": quality,
                    "blocked": blocked,
                    "value_unrestricted": value_unrestricted,
                    "currency": "EUR",
                })
                plant_totals[plant] = money2(plant_totals[plant] + value_unrestricted)
                grand_total = money2(grand_total + value_unrestricted)
        item_lines.append(f"* Werk {plant} gesamt{' ' * 40}{de_money(plant_totals[plant]):>15} EUR")

    meta_lines = [
        f"Werke: {', '.join(chosen_plants)}   {config.COMPANY_NAME}",
        f"Datum: {de_date(report_date)}   Benutzer: {user}",
    ]
    extra_header_line = "Selektionsvariante: Z_LAGER_MONAT" if rng.random() < config.EXTRA_HEADER_LINE_PROBABILITY else None
    colheader_lines = [header_line(columns, widths), "-" * len(header_line(columns, widths))]
    footer_lines = [f"* {'Gesamtwert':<30}{de_money(grand_total):>15} EUR"]

    rule_width = max(len(header_line(columns, widths)), 100)
    text_out = render_paginated(
        config.REPORT_TITLES["MB52"], meta_lines, colheader_lines, item_lines, footer_lines,
        config.PAGE_HEIGHT_LINES + int(rng.integers(-config.PAGE_BREAK_DRIFT, config.PAGE_BREAK_DRIFT + 1)),
        extra_header_line=extra_header_line, rule_width=rule_width,
    )

    parse_payload = {
        "header": {
            "plants": chosen_plants,
            "report_date": report_date.isoformat(),
            "user": user,
        },
        "line_items": line_items_payload,
        "totals": {
            "plant_totals": [{"plant": p, "value_total": plant_totals[p]} for p in chosen_plants],
            "grand_value_total": grand_total,
        },
    }
    return doc_id, text_out, parse_payload, None


# ===========================================================================
# Orchestration
# ===========================================================================

def generate_all():
    print("ERP Cleanup Phase 2 -- document generation")
    print(f"Output: {config.DOCUMENTS_DIR}")
    print(f"Seed: {config.RANDOM_SEED}\n")

    print("Building the ME2M purchase-order ledger (shared with FBL1N reconciliation)...")
    ledger_by_doc, ledger_by_vendor = build_po_ledger()
    total_po_lines = sum(len(v) for v in ledger_by_doc.values())
    print(f"  {total_po_lines} PO ledger lines across {len(ledger_by_doc)} ME2M documents.\n")

    written = {t: 0 for t in config.TRANSACTION_TYPES}
    class_tally = {t: {"R": 0, "V": 0, "F": 0, "S": 0} for t in config.TRANSACTION_TYPES}

    print("Rendering ME2M documents...")
    for month in config.MONTHS:
        for seq in range(1, config.DOCS_PER_TYPE_PER_MONTH + 1):
            doc_class = config.CLASS_SCHEDULE["ME2M"][month][seq - 1]
            entries = ledger_by_doc[(month, seq)]
            doc_id, text, payload, mechanism = render_me2m_document(month, seq, doc_class, entries)
            write_document(doc_id, "ME2M", month, doc_class, mechanism, text, payload)
            written["ME2M"] += 1
            class_tally["ME2M"][doc_class] += 1
        print(f"  {month} done ({written['ME2M']}/48)")

    print("\nRendering FBL1N documents (consumes PO ledger remaining capacity, chronologically)...")
    for month in config.MONTHS:
        for seq in range(1, config.DOCS_PER_TYPE_PER_MONTH + 1):
            doc_class = config.CLASS_SCHEDULE["FBL1N"][month][seq - 1]
            doc_id, text, payload, mechanism = render_fbl1n_document(month, seq, doc_class, ledger_by_vendor)
            write_document(doc_id, "FBL1N", month, doc_class, mechanism, text, payload)
            written["FBL1N"] += 1
            class_tally["FBL1N"][doc_class] += 1
        print(f"  {month} done ({written['FBL1N']}/48)")

    print("\nRendering FBL3N documents...")
    for month in config.MONTHS:
        for seq in range(1, config.DOCS_PER_TYPE_PER_MONTH + 1):
            doc_class = config.CLASS_SCHEDULE["FBL3N"][month][seq - 1]
            doc_id, text, payload, mechanism = render_fbl3n_document(month, seq, doc_class)
            write_document(doc_id, "FBL3N", month, doc_class, mechanism, text, payload)
            written["FBL3N"] += 1
            class_tally["FBL3N"][doc_class] += 1
    print(f"  {written['FBL3N']}/48 done")

    print("\nRendering VA05 documents...")
    for month in config.MONTHS:
        for seq in range(1, config.DOCS_PER_TYPE_PER_MONTH + 1):
            doc_class = config.CLASS_SCHEDULE["VA05"][month][seq - 1]
            doc_id, text, payload, mechanism = render_va05_document(month, seq, doc_class)
            write_document(doc_id, "VA05", month, doc_class, mechanism, text, payload)
            written["VA05"] += 1
            class_tally["VA05"][doc_class] += 1
    print(f"  {written['VA05']}/48 done")

    print("\nRendering MB52 documents...")
    for month in config.MONTHS:
        for seq in range(1, config.DOCS_PER_TYPE_PER_MONTH + 1):
            doc_class = config.CLASS_SCHEDULE["MB52"][month][seq - 1]
            doc_id, text, payload, mechanism = render_mb52_document(month, seq, doc_class)
            write_document(doc_id, "MB52", month, doc_class, mechanism, text, payload)
            written["MB52"] += 1
            class_tally["MB52"][doc_class] += 1
    print(f"  {written['MB52']}/48 done")

    total = sum(written.values())
    print(f"\nTotal documents written: {total} (expected {config.TOTAL_DOCS})")
    ok = True
    for t in config.TRANSACTION_TYPES:
        expected = config.EXPECTED_CLASS_COUNTS[t]
        actual = class_tally[t]
        status = "OK" if actual == expected else "MISMATCH"
        if status != "OK":
            ok = False
        print(f"  {t}: {actual} expected {expected} [{status}]")

    if total != config.TOTAL_DOCS or not ok:
        raise RuntimeError("Generation finished but counts do not match the pre-registered class plan -- see printout above.")

    print("\nDone. Run validate_data.py next.")


if __name__ == "__main__":
    try:
        generate_all()
    except Exception as exc:
        print(f"\nGENERATION FAILED: {exc}", file=sys.stderr)
        raise
