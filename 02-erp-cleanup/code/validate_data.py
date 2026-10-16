"""
validate_data.py -- Checks the seven coherence rules of the corpus design against
the generated corpus in data/, and exits 1 on any failure.

Reuses schemas.py (the single definition of "correctly parsed") and
config.py (master data, class schedule) -- never redefines either.

Rules checked:
    1. Arithmetic            -- totals equal sums of line items, in the
                                 answer key AND (FBL3N, ME2M) in the rendered text.
    2. Cross-transaction      -- master-data existence; ME2M/FBL1N reconciliation.
    3. Amount plausibility    -- amounts within master-data ranges.
    4. Locale                 -- German formatting throughout, no US numbers/ISO dates.
    5. Dates                  -- 2025, within batch month, business-day weighted.
    6. Answer-key completeness-- every doc present, schema-valid, classes match.
    7. Grounded formatting    -- every planted horror is actually present.

Usage: python validate_data.py
"""

import sys
import re
import json
import datetime as dt
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config
import schemas
import generate_documents as gd  # reuse column-layout helpers (no randomness needed below)

MONEY_TOL = schemas.MONEY_TOLERANCE

# ===========================================================================
# Loading
# ===========================================================================

def load_corpus():
    """Loads every answer key and its matching document text. Returns
    (answer_keys: {doc_id: dict}, texts: {doc_id: str})."""
    answer_keys = {}
    texts = {}
    if not config.ANSWER_KEY_DIR.exists():
        raise FileNotFoundError(f"Answer key directory not found: {config.ANSWER_KEY_DIR} -- run generate_documents.py first.")
    for path in sorted(config.ANSWER_KEY_DIR.glob("*.json")):
        with open(path, "r", encoding="utf-8") as f:
            ak = json.load(f)
        answer_keys[ak["doc_id"]] = ak
    for path in sorted(config.DOCUMENTS_DIR.glob("*.txt")):
        with open(path, "r", encoding="utf-8") as f:
            texts[path.stem] = f.read()
    return answer_keys, texts


# ===========================================================================
# Locale parsing helpers (inverse of generate_documents.de_number)
# ===========================================================================

DE_NUMBER_RE = re.compile(r"-?\d{1,3}(?:\.\d{3})*,\d{2}-?")


def parse_de_number(token):
    token = token.strip()
    negative = token.endswith("-")
    if negative:
        token = token[:-1]
    token = token.replace(".", "").replace(",", ".")
    value = float(token)
    return -value if negative else value


def find_last_de_number(line):
    matches = DE_NUMBER_RE.findall(line)
    if not matches:
        return None
    return parse_de_number(matches[-1])


def money_close(a, b, tol=MONEY_TOL):
    return abs(a - b) <= tol


def check_me2m_value_swap(doc_id, ak, text):
    """S-class assertion (the S-class escalation): headers are
    canonical, but each rendered row's Nettopreis cell must carry the
    payload's still_to_deliver_value and vice versa -- the document lies,
    the answer key tells the truth."""
    errors = []
    lines = text.split("\n")
    header_rows = [l for l in lines if l.startswith("|") and "Bestellnr" in l]
    data_rows = [l for l in lines if l.startswith("|") and "Bestellnr" not in l]
    if not header_rows:
        return [f"{doc_id}: S-class ME2M has no column header row"]
    labels = [c.strip() for c in header_rows[0].strip("|").split("|")]
    try:
        idx_price = labels.index("Nettopreis")
        idx_sdv = labels.index("Noch offen Wert")
    except ValueError:
        return [f"{doc_id}: S-class ME2M header labels missing Nettopreis / Noch offen Wert"]
    items = ak["parse"]["line_items"]
    if len(data_rows) != len(items):
        return [f"{doc_id}: S-class row count {len(data_rows)} != payload items {len(items)}"]
    for i, (row, item) in enumerate(zip(data_rows, items)):
        cells = [c.strip() for c in row.strip("|").split("|")]
        want_price_cell = gd.de_money(item["still_to_deliver_value"])
        want_sdv_cell = gd.de_money(item["net_price"])
        if cells[idx_price] != want_price_cell or cells[idx_sdv] != want_sdv_cell:
            errors.append(f"{doc_id}: row {i} value swap not present "
                          f"(Nettopreis cell {cells[idx_price]!r} vs expected {want_price_cell!r})")
            break
    return errors


# ===========================================================================
# Rule 1: Arithmetic
# ===========================================================================

def _fbl3n_columns_for_class(doc_class):
    if doc_class == "V":
        return gd.reorder_columns(config.FBL3N_COLUMNS, config.FBL3N_V_FIELD_ORDER,
                                   extra_columns=[config.FBL3N_V_EXTRA_COLUMN])
    # S never occurs for FBL3N (relocated to ME2M; see config note).
    return config.FBL3N_COLUMNS


def _field_char_offset(columns, field):
    """Character start offset of `field`'s cell within a build_row() line,
    assuming (as is true for every FBL3N layout used -- R, V, S) that no
    column preceding it has width jitter, so the static config widths alone
    determine the offset. Cells are joined by a single space (build_row)."""
    offset = 0
    for c in columns:
        if c["field"] == field:
            return offset, c["width"], c["align"]
        offset += c["width"] + 1
    raise ValueError(f"field {field!r} not found in columns")


def check_fbl3n_text_arithmetic(doc_id, ak, text, errors):
    columns = _fbl3n_columns_for_class(ak["doc_class"])
    amt_off, amt_w, amt_align = _field_char_offset(columns, "amount")

    lines = text.split("\n")
    total_from_text = 0.0
    n_rows = 0
    for line in lines:
        if line.startswith("*") or line.startswith("-") or "Seite" in line or not line.strip():
            continue
        if len(line) < amt_off + amt_w:
            continue
        cell = line[amt_off:amt_off + amt_w].strip()
        if not DE_NUMBER_RE.fullmatch(cell):
            continue
        total_from_text += parse_de_number(cell)
        n_rows += 1

    saldo_lines = [l for l in lines if l.strip().startswith("* Saldo")]
    if not saldo_lines:
        errors.append(f"{doc_id}: no '* Saldo' totals line found in text")
        return
    saldo_value = find_last_de_number(saldo_lines[0])
    if saldo_value is None:
        errors.append(f"{doc_id}: could not parse a number from the Saldo line {saldo_lines[0]!r}")
        return
    if n_rows == 0:
        errors.append(f"{doc_id}: text-arithmetic check found zero parsable amount cells (renderer/offset mismatch?)")
        return
    if not money_close(total_from_text, saldo_value, tol=0.02 * max(1, n_rows) ** 0.5):
        # A slightly looser tolerance than MONEY_TOLERANCE is used here because
        # this check sums independently-parsed text cells across a whole
        # (possibly multi-page) document; MONEY_TOLERANCE still governs the
        # JSON-side check below, which is the authoritative one.
        errors.append(f"{doc_id}: rendered-text Betrag column sums to {total_from_text:.2f} "
                       f"but the rendered Saldo line says {saldo_value:.2f}")


def check_me2m_text_arithmetic(doc_id, ak, text, errors):
    lines = text.split("\n")
    data_rows = [l for l in lines if l.startswith("|") and "Bestellnr" not in l]
    total_from_text = 0.0
    n_rows = 0
    for line in data_rows:
        cells = [c.strip() for c in line.strip("|").split("|")]
        for cell in reversed(cells):
            if DE_NUMBER_RE.fullmatch(cell):
                total_from_text += parse_de_number(cell)
                n_rows += 1
                break
    gesamt_lines = [l for l in lines if "Gesamtsumme" in l]
    if not gesamt_lines:
        errors.append(f"{doc_id}: no 'Gesamtsumme' line found in text")
        return
    gesamt_value = find_last_de_number(gesamt_lines[-1])
    if gesamt_value is None:
        errors.append(f"{doc_id}: could not parse a number from the Gesamtsumme line")
        return
    # net_value is not the last numeric-shaped cell on data rows reliably
    # (still-to-deliver value is); instead re-derive the grand total from the
    # vendor subtotal lines, which are unambiguous.
    subtotal_lines = [l for l in lines if l.strip().startswith("Summe ")]
    subtotal_sum = sum(find_last_de_number(l) or 0.0 for l in subtotal_lines)
    if not money_close(subtotal_sum, gesamt_value, tol=0.01 * max(1, len(subtotal_lines))):
        errors.append(f"{doc_id}: rendered-text vendor subtotals sum to {subtotal_sum:.2f} "
                       f"but Gesamtsumme says {gesamt_value:.2f}")


def check_va05_text_arithmetic(doc_id, ak, text, errors):
    """Extends the from-text recheck to VA05 (ground-truth principle, Fix 2): sum the rendered Nettowert
    cells and compare with the rendered Gesamtsumme line. Scans pipe cells
    backwards for the last money-shaped token per row, which is robust to
    the F-class pipe/dash horror names padding out extra "cells" earlier in
    the same row (they never look like a 2-decimal German amount)."""
    lines = text.split("\n")
    data_rows = [l for l in lines if l.startswith("|") and "Verkaufsbeleg" not in l]
    total_from_text = 0.0
    n_rows = 0
    for line in data_rows:
        cells = [c.strip() for c in line.strip("|").split("|")]
        for cell in reversed(cells):
            if DE_NUMBER_RE.fullmatch(cell):
                total_from_text += parse_de_number(cell)
                n_rows += 1
                break
    gesamt_lines = [l for l in lines if "Gesamtsumme" in l]
    if not gesamt_lines:
        errors.append(f"{doc_id}: no 'Gesamtsumme' line found in VA05 text")
        return
    gesamt_value = find_last_de_number(gesamt_lines[-1])
    if gesamt_value is None:
        errors.append(f"{doc_id}: could not parse a number from the VA05 Gesamtsumme line")
        return
    if n_rows == 0:
        errors.append(f"{doc_id}: VA05 text-arithmetic check found zero parsable Nettowert cells")
        return
    if not money_close(total_from_text, gesamt_value, tol=0.01 * max(1, n_rows)):
        errors.append(f"{doc_id}: rendered-text Nettowert cells sum to {total_from_text:.2f} "
                       f"but Gesamtsumme says {gesamt_value:.2f}")


FBL1N_STATUS_TO_NAME = {v: k for k, v in config.FBL1N_STATUS_CODES.items()}


def check_fbl1n_text_arithmetic(doc_id, ak, text, errors):
    """Extends the from-text recheck to FBL1N: per vendor page, re-derive
    per-currency open/cleared totals from the @0x@-coded data rows and
    compare against the printed '* Summe offen/teilweise <WHG>' /
    '* Summe ausgeglichen <WHG>' lines. A data row is identified purely by
    its first token being a known status code -- no column-offset
    assumptions needed, so this is unaffected by width jitter."""
    blocks = text.split("\x0c")
    payload_by_vendor = {v["vendor_number"]: v for v in ak["parse"]["vendors"]}
    seen_vendors = set()

    for block in blocks:
        m = re.search(r"Kreditor:\s*(\S+)", block)
        if not m or m.group(1) not in payload_by_vendor:
            continue
        vendor_number = m.group(1)
        seen_vendors.add(vendor_number)
        block_lines = block.split("\n")

        computed = {}
        for line in block_lines:
            tokens = line.split()
            if not tokens or tokens[0] not in FBL1N_STATUS_TO_NAME:
                continue
            status = FBL1N_STATUS_TO_NAME[tokens[0]]
            amount, currency = None, None
            for tok in tokens:
                if DE_NUMBER_RE.fullmatch(tok):
                    amount = parse_de_number(tok)
                if tok in ("EUR", "SEK"):
                    currency = tok
            if amount is None or currency is None:
                continue
            bucket = computed.setdefault(currency, {"open": 0.0, "cleared": 0.0})
            key = "cleared" if status == "cleared" else "open"
            bucket[key] = round(bucket[key] + amount, 2)

        printed_open, printed_cleared = {}, {}
        for line in block_lines:
            stripped = line.strip()
            m2 = re.match(r"\*\s*Summe offen/teilweise (\S+)", stripped)
            if m2:
                printed_open[m2.group(1)] = find_last_de_number(stripped)
            m3 = re.match(r"\*\s*Summe ausgeglichen (\S+)", stripped)
            if m3:
                printed_cleared[m3.group(1)] = find_last_de_number(stripped)

        for currency, comp in computed.items():
            po = printed_open.get(currency)
            pc = printed_cleared.get(currency)
            if po is None or not money_close(comp["open"], po, tol=0.02 * max(1, len(block_lines)) ** 0.5):
                errors.append(f"{doc_id}: vendor {vendor_number} {currency} rendered-text open total "
                               f"{comp['open']:.2f} does not match the printed line ({po})")
            if pc is None or not money_close(comp["cleared"], pc, tol=0.02 * max(1, len(block_lines)) ** 0.5):
                errors.append(f"{doc_id}: vendor {vendor_number} {currency} rendered-text cleared total "
                               f"{comp['cleared']:.2f} does not match the printed line ({pc})")

    missing = set(payload_by_vendor) - seen_vendors
    for vendor_number in missing:
        errors.append(f"{doc_id}: vendor {vendor_number} page not found in rendered text for the text-arithmetic check")


def check_mb52_text_arithmetic(doc_id, ak, text, errors):
    """Extends the from-text recheck to MB52: re-derive per-plant value
    totals from the indented material rows and compare against the printed
    '* Werk <plant> gesamt' / '* Gesamtwert' lines. Material rows are
    identified by their fixed indent (MB52_MATERIAL_INDENT), and the target
    cell is found by scanning backwards for the last money-shaped token --
    robust to material_text's width jitter shifting value_unrestricted's
    column offset, since no offset is assumed at all."""
    lines = text.split("\n")
    computed_by_plant = {}
    current_plant = None
    grand_from_text = 0.0

    for line in lines:
        werk_match = re.match(r"Werk (\S+)\s", line)
        if werk_match:
            current_plant = werk_match.group(1)
            computed_by_plant.setdefault(current_plant, 0.0)
            continue
        if current_plant is not None and line.startswith(" " * config.MB52_MATERIAL_INDENT) and not line.strip().startswith("*"):
            tokens = line.split()
            value = None
            for tok in reversed(tokens):
                if DE_NUMBER_RE.fullmatch(tok):
                    value = parse_de_number(tok)
                    break
            if value is not None:
                computed_by_plant[current_plant] = round(computed_by_plant[current_plant] + value, 2)
                grand_from_text = round(grand_from_text + value, 2)

    plant_total_lines = {}
    for line in lines:
        m = re.match(r"\*\s*Werk (\S+) gesamt", line.strip())
        if m:
            plant_total_lines[m.group(1)] = find_last_de_number(line)
    gesamtwert_lines = [l for l in lines if l.strip().startswith("* Gesamtwert")]

    for plant, computed in computed_by_plant.items():
        printed = plant_total_lines.get(plant)
        if printed is None or not money_close(computed, printed, tol=0.02 * max(1, len(lines)) ** 0.5):
            errors.append(f"{doc_id}: plant {plant} rendered-text value sum {computed:.2f} "
                           f"does not match the printed '* Werk {plant} gesamt' line ({printed})")

    if not gesamtwert_lines:
        errors.append(f"{doc_id}: no '* Gesamtwert' line found in MB52 text")
    else:
        printed_grand = find_last_de_number(gesamtwert_lines[-1])
        if printed_grand is None or not money_close(grand_from_text, printed_grand, tol=0.02 * max(1, len(lines)) ** 0.5):
            errors.append(f"{doc_id}: rendered-text grand value {grand_from_text:.2f} "
                           f"does not match the printed Gesamtwert line ({printed_grand})")


def check_arithmetic(answer_keys, texts):
    errors = []
    for doc_id, ak in answer_keys.items():
        t = ak["transaction_type"]
        payload = ak["parse"]

        if t == "FBL3N":
            items = payload["line_items"]
            sum_debit = round(sum(li["amount"] for li in items if li["debit_credit"] == "S"), 2)
            sum_credit = round(sum(li["amount"] for li in items if li["debit_credit"] == "H"), 2)
            balance = round(sum_debit + sum_credit, 2)
            tot = payload["totals"]
            if not money_close(sum_debit, tot["sum_debit"]):
                errors.append(f"{doc_id}: sum_debit mismatch: computed {sum_debit} vs stored {tot['sum_debit']}")
            if not money_close(sum_credit, tot["sum_credit"]):
                errors.append(f"{doc_id}: sum_credit mismatch: computed {sum_credit} vs stored {tot['sum_credit']}")
            if not money_close(balance, tot["balance"]):
                errors.append(f"{doc_id}: balance mismatch: computed {balance} vs stored {tot['balance']}")
            check_fbl3n_text_arithmetic(doc_id, ak, texts[doc_id], errors)

        elif t == "ME2M":
            items = payload["line_items"]
            by_vendor = {}
            for li in items:
                by_vendor.setdefault(li["vendor_number"], 0.0)
                by_vendor[li["vendor_number"]] = round(by_vendor[li["vendor_number"]] + li["net_value"], 2)
            stored_subtotals = {s["vendor_number"]: s["total_value"] for s in payload["totals"]["vendor_subtotals"]}
            if set(by_vendor) != set(stored_subtotals):
                errors.append(f"{doc_id}: vendor_subtotals vendor set mismatch")
            for vendor_number, computed in by_vendor.items():
                stored = stored_subtotals.get(vendor_number)
                if stored is None or not money_close(computed, stored):
                    errors.append(f"{doc_id}: vendor {vendor_number} subtotal mismatch: computed {computed} vs stored {stored}")
            grand_total = round(sum(by_vendor.values()), 2)
            if not money_close(grand_total, payload["totals"]["grand_total"]):
                errors.append(f"{doc_id}: grand_total mismatch: computed {grand_total} vs stored {payload['totals']['grand_total']}")
            check_me2m_text_arithmetic(doc_id, ak, texts[doc_id], errors)

        elif t == "VA05":
            computed = round(sum(li["net_value"] for li in payload["line_items"]), 2)
            stored = payload["totals"]["total_net_value"]
            if not money_close(computed, stored):
                errors.append(f"{doc_id}: total_net_value mismatch: computed {computed} vs stored {stored}")
            check_va05_text_arithmetic(doc_id, ak, texts[doc_id], errors)

        elif t == "FBL1N":
            for vendor in payload["vendors"]:
                by_currency = {}
                for li in vendor["line_items"]:
                    bucket = by_currency.setdefault(li["currency"], {"open_total": 0.0, "cleared_total": 0.0})
                    key = "cleared_total" if li["status"] == "cleared" else "open_total"
                    bucket[key] = round(bucket[key] + li["amount"], 2)
                stored = {vt["currency"]: vt for vt in vendor["vendor_totals"]}
                if set(by_currency) != set(stored):
                    errors.append(f"{doc_id}: vendor {vendor['vendor_number']} vendor_totals currency set mismatch")
                for currency, computed in by_currency.items():
                    s = stored.get(currency)
                    if s is None:
                        continue
                    if not money_close(computed["open_total"], s["open_total"]):
                        errors.append(f"{doc_id}: vendor {vendor['vendor_number']} {currency} open_total mismatch: "
                                       f"computed {computed['open_total']} vs stored {s['open_total']}")
                    if not money_close(computed["cleared_total"], s["cleared_total"]):
                        errors.append(f"{doc_id}: vendor {vendor['vendor_number']} {currency} cleared_total mismatch: "
                                       f"computed {computed['cleared_total']} vs stored {s['cleared_total']}")
            check_fbl1n_text_arithmetic(doc_id, ak, texts[doc_id], errors)

        elif t == "MB52":
            by_plant = {}
            for li in payload["line_items"]:
                by_plant.setdefault(li["plant"], 0.0)
                by_plant[li["plant"]] = round(by_plant[li["plant"]] + li["value_unrestricted"], 2)
            stored_plants = {p["plant"]: p["value_total"] for p in payload["totals"]["plant_totals"]}
            if set(by_plant) != set(stored_plants):
                errors.append(f"{doc_id}: plant_totals plant set mismatch")
            for plant, computed in by_plant.items():
                stored = stored_plants.get(plant)
                if stored is None or not money_close(computed, stored):
                    errors.append(f"{doc_id}: plant {plant} total mismatch: computed {computed} vs stored {stored}")
            grand_total = round(sum(by_plant.values()), 2)
            if not money_close(grand_total, payload["totals"]["grand_value_total"]):
                errors.append(f"{doc_id}: grand_value_total mismatch: computed {grand_total} vs stored {payload['totals']['grand_value_total']}")
            check_mb52_text_arithmetic(doc_id, ak, texts[doc_id], errors)

    return errors


# ===========================================================================
# Rule 2: Cross-transaction consistency
# ===========================================================================

def check_cross_transaction(answer_keys):
    errors = []

    for doc_id, ak in answer_keys.items():
        t = ak["transaction_type"]
        payload = ak["parse"]

        def check_vendor(v, where):
            if v not in config.VENDORS_BY_NUMBER:
                errors.append(f"{doc_id}: {where} vendor {v!r} not in vendor master")

        def check_material(m, where):
            if m not in config.MATERIALS_BY_NUMBER:
                errors.append(f"{doc_id}: {where} material {m!r} not in material master")

        if t == "ME2M":
            for i, li in enumerate(payload["line_items"]):
                check_vendor(li["vendor_number"], f"line_items[{i}]")
                check_material(li["material"], f"line_items[{i}]")
        elif t == "VA05":
            customer_names = {c["name"] for c in config.CUSTOMERS}
            for i, li in enumerate(payload["line_items"]):
                sold_to = li["sold_to"]
                if sold_to not in customer_names:
                    # VA05 has no customer-number field, so there is nothing
                    # to match by number (ground-truth principle). Since Fix 1 makes
                    # sold_to the truncated *rendered* string, an exact match
                    # can legitimately fail for a long name -- accept it only
                    # if it is an unambiguous prefix of exactly one master
                    # name.
                    prefix_matches = [n for n in customer_names if n.startswith(sold_to)]
                    if len(prefix_matches) != 1:
                        errors.append(f"{doc_id}: line_items[{i}] sold_to {sold_to!r} not in customer master "
                                       f"(no exact match, and {len(prefix_matches)} unambiguous-prefix candidates)")
                check_material(li["material"], f"line_items[{i}]")
        elif t == "FBL1N":
            for v in payload["vendors"]:
                check_vendor(v["vendor_number"], "vendors[]")
        elif t == "MB52":
            for i, li in enumerate(payload["line_items"]):
                check_material(li["material"], f"line_items[{i}]")
                if li["plant"] not in config.PLANTS:
                    errors.append(f"{doc_id}: line_items[{i}] plant {li['plant']!r} not in plant master")
                if li["storage_location"] not in config.STORAGE_LOCATIONS:
                    errors.append(f"{doc_id}: line_items[{i}] storage_location {li['storage_location']!r} not in master")
        elif t == "FBL3N":
            if payload["header"]["gl_account"] not in config.GL_ACCOUNTS_BY_NUMBER:
                errors.append(f"{doc_id}: gl_account {payload['header']['gl_account']!r} not in GL chart")

    # PO <-> invoice reconciliation.
    po_by_vendor = {}
    for doc_id, ak in answer_keys.items():
        if ak["transaction_type"] != "ME2M":
            continue
        for li in ak["parse"]["line_items"]:
            po_by_vendor.setdefault(li["vendor_number"], []).append({
                "order_date": dt.date.fromisoformat(li["order_date"]),
                "net_value": li["net_value"],
            })

    invoices = []
    for doc_id, ak in answer_keys.items():
        if ak["transaction_type"] != "FBL1N":
            continue
        for vendor_block in ak["parse"]["vendors"]:
            for li in vendor_block["line_items"]:
                if li["document_type"] != "KR":
                    continue
                invoices.append({
                    "doc_id": doc_id,
                    "vendor_number": vendor_block["vendor_number"],
                    "document_date": dt.date.fromisoformat(li["document_date"]),
                    "amount": abs(li["amount"]),
                })

    max_lag = dt.timedelta(days=config.FBL1N_INVOICE_LAG_DAYS_MAX)
    for inv in invoices:
        pool = po_by_vendor.get(inv["vendor_number"], [])
        window_match = any(po["order_date"] < inv["document_date"] <= po["order_date"] + max_lag for po in pool)
        if not window_match:
            errors.append(f"{inv['doc_id']}: KR invoice dated {inv['document_date']} for vendor "
                           f"{inv['vendor_number']} has no ME2M PO within the 60-day reconciliation window")

    invoiced_by_vendor = {}
    for inv in invoices:
        invoiced_by_vendor[inv["vendor_number"]] = invoiced_by_vendor.get(inv["vendor_number"], 0.0) + inv["amount"]
    ordered_by_vendor = {}
    for vendor_number, pos in po_by_vendor.items():
        ordered_by_vendor[vendor_number] = sum(po["net_value"] for po in pos)
    for vendor_number, invoiced in invoiced_by_vendor.items():
        ordered = ordered_by_vendor.get(vendor_number, 0.0)
        if invoiced > ordered + MONEY_TOL:
            errors.append(f"vendor {vendor_number}: cumulative KR invoiced {invoiced:.2f} exceeds "
                           f"cumulative ME2M ordered {ordered:.2f}")

    return errors


# ===========================================================================
# Rule 3: Amount plausibility
# ===========================================================================

def check_amount_plausibility(answer_keys):
    errors = []
    for doc_id, ak in answer_keys.items():
        t = ak["transaction_type"]
        payload = ak["parse"]

        if t == "FBL3N":
            account = config.GL_ACCOUNTS_BY_NUMBER.get(payload["header"]["gl_account"])
            if account is None:
                continue
            for i, li in enumerate(payload["line_items"]):
                mag = abs(li["amount"])
                if not (account["amount_min"] - MONEY_TOL <= mag <= account["amount_max"] + MONEY_TOL):
                    errors.append(f"{doc_id}: line_items[{i}] amount {li['amount']} outside account "
                                   f"{account['number']} range [{account['amount_min']}, {account['amount_max']}]")

        elif t == "ME2M":
            for i, li in enumerate(payload["line_items"]):
                vendor = config.VENDORS_BY_NUMBER.get(li["vendor_number"])
                if vendor is None:
                    continue
                if not (vendor["order_value_min"] - MONEY_TOL <= li["net_value"] <= vendor["order_value_max"] + MONEY_TOL):
                    errors.append(f"{doc_id}: line_items[{i}] net_value {li['net_value']} outside vendor "
                                   f"{vendor['number']} order-value range [{vendor['order_value_min']}, {vendor['order_value_max']}]")

        elif t == "VA05":
            lo_mult, hi_mult = config.SALES_MARKUP_RANGE
            for i, li in enumerate(payload["line_items"]):
                material = config.MATERIALS_BY_NUMBER.get(li["material"])
                if material is None or li["order_quantity"] == 0:
                    continue
                unit_price = li["net_value"] / li["order_quantity"]
                band_lo = material["price_min"] * lo_mult * 0.9
                band_hi = material["price_max"] * hi_mult * 1.1
                if not (band_lo <= unit_price <= band_hi):
                    errors.append(f"{doc_id}: line_items[{i}] implied unit price {unit_price:.2f} outside plausible "
                                   f"band [{band_lo:.2f}, {band_hi:.2f}] for material {material['number']}")

        elif t == "MB52":
            for i, li in enumerate(payload["line_items"]):
                material = config.MATERIALS_BY_NUMBER.get(li["material"])
                if material is None or li["unrestricted"] == 0:
                    continue
                unit_price = li["value_unrestricted"] / li["unrestricted"]
                if not (material["price_min"] * 0.9 <= unit_price <= material["price_max"] * 1.1):
                    errors.append(f"{doc_id}: line_items[{i}] implied unit price {unit_price:.2f} outside "
                                   f"material {material['number']} band")

        elif t == "FBL1N":
            for v in payload["vendors"]:
                vendor = config.VENDORS_BY_NUMBER.get(v["vendor_number"])
                if vendor is None:
                    continue
                ceiling = vendor["order_value_max"] * 1.5
                for i, li in enumerate(v["line_items"]):
                    mag = abs(li["amount"])
                    if mag <= 0 or mag > ceiling:
                        errors.append(f"{doc_id}: vendor {v['vendor_number']} line_items[{i}] amount {li['amount']} "
                                       f"implausible (ceiling {ceiling:.2f})")
    return errors


# ===========================================================================
# Rule 4: Locale
# ===========================================================================

US_NUMBER_RE = re.compile(r"\d,\d{3}\.\d{2}\b")
ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

EXPECTED_HEADINGS = {
    "FBL3N": ["Betrag", "Belegnr", "Buch.datum"],
    "ME2M": ["Bestellnr", "Lieferant", "Nettowert"],
    "VA05": ["Auftraggeber", "Nettowert", "Menge"],
    "FBL1N": ["Kreditor", "Belegnr", "Fälligkeit"],
    "MB52": ["Materialkurztext", "Frei verwendbar", "Gesperrt"],
}


def check_locale(answer_keys, texts):
    errors = []
    for doc_id, ak in answer_keys.items():
        text = texts.get(doc_id)
        if text is None:
            continue
        if US_NUMBER_RE.search(text):
            errors.append(f"{doc_id}: text contains a US-format number")
        if ISO_DATE_RE.search(text):
            errors.append(f"{doc_id}: text contains an ISO-format date")
        for heading in EXPECTED_HEADINGS[ak["transaction_type"]]:
            if heading not in text:
                errors.append(f"{doc_id}: expected German heading {heading!r} not found in text")
    return errors


# ===========================================================================
# Rule 5: Dates
# ===========================================================================

def extract_dates(transaction_type, payload):
    """Generic date extraction driven by schemas.py's own type annotations
    -- no per-type special-casing needed beyond FBL1N's extra nesting."""
    schema = schemas.SCHEMAS[transaction_type]

    def date_field_names(spec):
        return [name for name, t in spec if t.rstrip("?") == "date"]

    dates = []
    for f in date_field_names(schema["header"]):
        v = payload["header"].get(f)
        if v:
            dates.append((f"header.{f}", v))

    li_fields = date_field_names(schema["line_items"])
    if transaction_type == "FBL1N":
        for vi, vendor in enumerate(payload.get("vendors", [])):
            for li in vendor.get("line_items", []):
                for f in li_fields:
                    v = li.get(f)
                    if v:
                        dates.append((f"vendors[{vi}].{f}", v))
    else:
        for li in payload.get("line_items", []):
            for f in li_fields:
                v = li.get(f)
                if v:
                    dates.append((f"line_items.{f}", v))
    return dates


def check_dates(answer_keys):
    errors = []
    all_dates = []

    for doc_id, ak in answer_keys.items():
        payload = ak["parse"]
        report_date_str = payload["header"].get("report_date") or payload["header"].get("key_date")
        report_date = dt.date.fromisoformat(report_date_str)
        if report_date.year != 2025:
            errors.append(f"{doc_id}: report_date {report_date} not in 2025")
        if report_date.isoformat()[:7] != ak["month"]:
            errors.append(f"{doc_id}: report_date {report_date} not within batch month {ak['month']}")

        for field, value in extract_dates(ak["transaction_type"], payload):
            d = dt.date.fromisoformat(value)
            all_dates.append(d)
            if d.year != 2025:
                errors.append(f"{doc_id}: {field}={value} not in 2025")
            # "posting/doc dates <= report_date" (coherence rule) means the
            # posting-date/document-date family specifically (BUDAT/BLDAT).
            # Two field families are intentionally exempted from this
            # comparison (still checked for year==2025 above, and still
            # counted in the business-day sanity check below):
            #   - due_date (Faelligkeit): forward-looking by definition -- an
            #     open item's due date is routinely after the report's key
            #     date, that's what makes it "open".
            #   - period_from/period_to: a selection-range label (the
            #     calendar month being reported on), not a posting/document
            #     date -- a report run a day or two before month-end can
            #     still legitimately select "the whole month" as its range.
            exempt = field.endswith("due_date") or field.endswith("period_from") or field.endswith("period_to")
            if not exempt and d > report_date:
                errors.append(f"{doc_id}: {field}={value} is after report_date {report_date}")

    if all_dates:
        business_day_count = sum(1 for d in all_dates if d.weekday() < 5)
        fraction = business_day_count / len(all_dates)
        if fraction < 0.80:
            errors.append(f"business-day weighting sanity failed: only {fraction:.1%} of "
                           f"{len(all_dates)} dates are Mon-Fri (need >= 80%)")

    return errors


def extract_strings(transaction_type, payload):
    """Generic string-field extraction driven by schemas.py's own type
    annotations (fields whose declared type is exactly 'str' or 'str?').
    Mirrors extract_dates above. Used by the verbatim-presence check (rule
    7, ground-truth principle, Fix 1):
    every payload string must appear literally in the rendered text, since
    the payload is now required to store the rendered (possibly truncated)
    cell content rather than the pre-truncation master-data value."""
    schema = schemas.SCHEMAS[transaction_type]

    def str_field_names(spec):
        return [name for name, t in spec if t.rstrip("?") == "str"]

    strings = []
    for f in str_field_names(schema["header"]):
        v = payload["header"].get(f)
        if v:
            strings.append((f"header.{f}", v))

    li_fields = str_field_names(schema["line_items"])
    if transaction_type == "FBL1N":
        vendor_fields = str_field_names(schema["vendors"])
        for vi, vendor in enumerate(payload.get("vendors", [])):
            for f in vendor_fields:
                v = vendor.get(f)
                if v:
                    strings.append((f"vendors[{vi}].{f}", v))
            for li in vendor.get("line_items", []):
                for f in li_fields:
                    v = li.get(f)
                    if v:
                        strings.append((f"vendors[{vi}].line_items.{f}", v))
    else:
        for li in payload.get("line_items", []):
            for f in li_fields:
                v = li.get(f)
                if v:
                    strings.append((f"line_items.{f}", v))
    return strings


# ===========================================================================
# Rule 6: Answer-key completeness
# ===========================================================================

def check_completeness(answer_keys):
    errors = []

    expected_doc_ids = set()
    for t in config.TRANSACTION_TYPES:
        for month in config.MONTHS:
            for seq in range(1, config.DOCS_PER_TYPE_PER_MONTH + 1):
                expected_doc_ids.add(gd.make_doc_id(month, t, seq))

    actual_doc_ids = set(answer_keys)
    missing = expected_doc_ids - actual_doc_ids
    extra = actual_doc_ids - expected_doc_ids
    for doc_id in sorted(missing):
        errors.append(f"missing answer key for expected document {doc_id}")
    for doc_id in sorted(extra):
        errors.append(f"unexpected answer key {doc_id} not in the class plan")
    for doc_id in sorted(expected_doc_ids):
        if not (config.DOCUMENTS_DIR / f"{doc_id}.txt").exists():
            errors.append(f"missing rendered document for {doc_id}")

    for doc_id, ak in answer_keys.items():
        schema_errors = schemas.validate_parse(ak["transaction_type"], ak["parse"])
        for e in schema_errors:
            errors.append(f"{doc_id}: schema violation: {e}")

    class_tally = {t: {"R": 0, "V": 0, "F": 0, "S": 0} for t in config.TRANSACTION_TYPES}
    for doc_id, ak in answer_keys.items():
        t = ak["transaction_type"]
        c = ak["doc_class"]
        if t in class_tally and c in class_tally[t]:
            class_tally[t][c] += 1
    for t in config.TRANSACTION_TYPES:
        expected = config.EXPECTED_CLASS_COUNTS[t]
        if class_tally[t] != expected:
            errors.append(f"{t}: class counts {class_tally[t]} do not match the pre-registered plan {expected}")

    for doc_id, ak in answer_keys.items():
        if ak["doc_class"] in ("V", "F", "S") and not ak.get("planted_mechanism"):
            errors.append(f"{doc_id}: class {ak['doc_class']} but planted_mechanism is not set")
        if ak["doc_class"] == "R" and ak.get("planted_mechanism"):
            errors.append(f"{doc_id}: class R but planted_mechanism is set ({ak['planted_mechanism']!r})")

    return errors


# ===========================================================================
# Rule 7: Grounded formatting
# ===========================================================================

TRAILING_MINUS_RE = re.compile(r"\d,\d{2}-")


def check_grounded_formatting(answer_keys, texts):
    errors = []

    for doc_id, ak in answer_keys.items():
        t = ak["transaction_type"]
        text = texts.get(doc_id, "")
        payload = ak["parse"]

        # Verbatim-presence check (ground-truth principle, Fix 1): every payload string field must
        # appear literally in the rendered text. Catches any answer-key
        # field left as the pre-truncation master-data value by mistake.
        for field, value in extract_strings(t, payload):
            if value not in text:
                errors.append(f"{doc_id}: {field}={value!r} does not appear verbatim in the rendered text")

        if t == "FBL1N":
            if "@0A@" not in text and "@09@" not in text and "@08@" not in text:
                errors.append(f"{doc_id}: no @0x@ status codes found in FBL1N text")
            if "\f" not in text:
                errors.append(f"{doc_id}: FBL1N document has no form feed between vendor pages")
            any_negative = any(li["amount"] < 0 for v in payload["vendors"] for li in v["line_items"])
            if any_negative and not TRAILING_MINUS_RE.search(text):
                errors.append(f"{doc_id}: answer key has negative amounts but no trailing-minus found in text")

        if t == "FBL3N":
            any_negative = any(li["amount"] < 0 for li in payload["line_items"])
            if any_negative and not TRAILING_MINUS_RE.search(text):
                errors.append(f"{doc_id}: answer key has negative amounts but no trailing-minus found in text")

        if t == "ME2M":
            if "----+----" not in text.replace("-" * 20, "-" * 10):  # normalize long rules, keep '+' junctions
                if "+" not in text:
                    errors.append(f"{doc_id}: no FRAMES-ON '+' rule intersections found in ME2M text")

        if t == "VA05" and ak["doc_class"] == "F":
            horror_present = any("|" in li["sold_to"] or "--" in li["sold_to"] for li in payload["line_items"])
            if not horror_present:
                errors.append(f"{doc_id}: F-class VA05 has no pipe/dash horror name in its answer key")
            else:
                horror_names_here = {li["sold_to"] for li in payload["line_items"] if "|" in li["sold_to"] or "--" in li["sold_to"]}
                if not any(name in text for name in horror_names_here):
                    errors.append(f"{doc_id}: horror customer name not found verbatim in rendered text")

        if t == "ME2M" and ak["doc_class"] == "F":
            if "WE-Datum" not in text:
                errors.append(f"{doc_id}: F-class ME2M missing the inserted WE-Datum column")

        if t == "FBL1N" and ak["doc_class"] == "F":
            currencies_here = {li["currency"] for v in payload["vendors"] for li in v["line_items"]}
            if len(currencies_here) < 2:
                errors.append(f"{doc_id}: F-class FBL1N has only one currency across all vendors")

        if t == "FBL3N" and ak["doc_class"] == "V":
            if "Zuordnung" not in text:
                errors.append(f"{doc_id}: V-class FBL3N missing the Zuordnung column")

        if t == "VA05" and ak["doc_class"] == "V":
            if "PSP-Element" not in text:
                errors.append(f"{doc_id}: V-class VA05 missing the PSP-Element column")

        if t == "FBL3N":
            header_lines = [l for l in text.split("\n") if "Betrag" in l and "Steuerbetr." in l]
            if not header_lines:
                errors.append(f"{doc_id}: could not find the FBL3N column header line")
            else:
                header_line = header_lines[0]
                if not (header_line.find("Betrag") < header_line.find("Steuerbetr.")):
                    errors.append(f"{doc_id}: FBL3N header order unexpectedly swapped (S no longer lives in FBL3N)")

        if t == "ME2M":
            header_lines = [l for l in text.split("\n") if "Nettopreis" in l and "Nettowert" in l]
            if not header_lines:
                errors.append(f"{doc_id}: could not find the ME2M column header line")
            else:
                header_line = header_lines[0]
                price_pos = header_line.find("Nettopreis")
                value_pos = header_line.find("Nettowert")
                if not (price_pos < value_pos):
                    errors.append(f"{doc_id}: ME2M header order is not canonical "
                                   f"(S is a value swap now, never a layout swap)")
            if ak["doc_class"] == "S":
                errors.extend(check_me2m_value_swap(doc_id, ak, text))

    # At least one multi-page document per paginated type (proves H1 actually fires somewhere).
    for t in ["FBL3N", "ME2M", "VA05", "MB52"]:
        any_ff = any("\f" in texts.get(doc_id, "") for doc_id, ak in answer_keys.items() if ak["transaction_type"] == t)
        if not any_ff:
            errors.append(f"{t}: no document in the corpus triggered a page break (H1 never observed)")

    return errors


# ===========================================================================
# Report
# ===========================================================================

RULES = [
    ("1. Arithmetic", check_arithmetic, "answer_keys_texts"),
    ("2. Cross-transaction consistency", check_cross_transaction, "answer_keys"),
    ("3. Amount plausibility", check_amount_plausibility, "answer_keys"),
    ("4. Locale", check_locale, "answer_keys_texts"),
    ("5. Dates", check_dates, "answer_keys"),
    ("6. Answer-key completeness", check_completeness, "answer_keys"),
    ("7. Grounded formatting", check_grounded_formatting, "answer_keys_texts"),
]


def main():
    print("ERP Cleanup Phase 2 -- data validation")
    print(f"Reading: {config.ANSWER_KEY_DIR} / {config.DOCUMENTS_DIR}\n")

    try:
        answer_keys, texts = load_corpus()
    except FileNotFoundError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded {len(answer_keys)} answer keys and {len(texts)} documents.\n")

    all_ok = True
    total_errors = 0
    for name, fn, arity in RULES:
        if arity == "answer_keys":
            errs = fn(answer_keys)
        else:
            errs = fn(answer_keys, texts)
        status = "PASS" if not errs else f"FAIL ({len(errs)} issue(s))"
        print(f"[{status}] {name}")
        for e in errs[:12]:
            print(f"    - {e}")
        if len(errs) > 12:
            print(f"    ... and {len(errs) - 12} more")
        if errs:
            all_ok = False
            total_errors += len(errs)

    print()
    if all_ok:
        print("ALL SEVEN COHERENCE RULES PASS.")
        sys.exit(0)
    else:
        print(f"VALIDATION FAILED: {total_errors} issue(s) across the rules above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
