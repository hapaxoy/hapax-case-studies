"""Generate the 198-document invoice-processing corpus (Project 3).

Pipeline per document: build a canonical schema record -> assert
schemas.validate_record passes -> render HTML via Jinja2 -> print to PDF via
headless Chrome -> normalise the PDF via pypdf -> write the HTML/PDF/answer
key -> record the document in data/manifest.json.

Determinism: one seeded random.Random(config.RANDOM_SEED) stream, consumed
in a single fixed pass (month-major, then supplier order within month, then
one-offs in roster order). Re-running produces byte-identical HTML/PDF/
answer-key files -- compare the manifest's per-file SHA-256 set across runs.

Usage: python generate_invoices.py
"""
from __future__ import annotations

import calendar
import hashlib
import json
import random
import subprocess
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, ByteStringObject

import config
import formatting
import schemas

# ---------------------------------------------------------------------------
# Paths (relative to this file; never touch anything outside data/)
# ---------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
DATA_DIR = PROJECT_ROOT / "data"
HTML_DIR = DATA_DIR / "html"
DOCS_DIR = DATA_DIR / "documents"
ANSWER_KEY_DIR = DATA_DIR / "answer_key"
MANIFEST_PATH = DATA_DIR / "manifest.json"
TEMPLATES_DIR = HERE / "templates"
assert DATA_DIR != HERE  # output path != input/code path, sanity per house rule

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROME_VERSION = "149.0.7827.201"  # confirmed via file metadata

YEAR = 2025
COUNTRY_NAMES = {"FI": "Finland", "DE": "Germany", "SE": "Sweden", "EE": "Estonia", "IE": "Ireland"}
CURRENCY_SUFFIX = {"EUR": "€", "SEK": "kr"}
PAYMENT_TERMS_PHRASE = {
    "fi": lambda d: f"{d} pv netto", "fi_compact": lambda d: f"{d} pv netto",
    "de": lambda d: f"{d} Tage netto", "sv": lambda d: f"{d} dagar netto",
    "en": lambda d: f"{d} days net", "en_ie": lambda d: f"{d} days net",
}
MONTH_NAMES_FI = ["tammikuu", "helmikuu", "maaliskuu", "huhtikuu", "toukokuu", "kesäkuu",
                  "heinäkuu", "elokuu", "syyskuu", "lokakuu", "marraskuu", "joulukuu"]

S6_ROUTES = [
    ("Runkokuljetus, Lahti-Helsinki", "kpl"), ("Runkokuljetus, Lahti-Tampere", "kpl"),
    ("Runkokuljetus, Lahti-Turku", "kpl"), ("Jakelukuljetus, pääkaupunkiseutu", "kpl"),
    ("Nostopalvelu, purku", "kpl"), ("Lisäkuljetus, kiireellinen toimitus", "kpl"),
]

F4_TERMS_TEXT = (
    "Leverans sker fritt vårt lager (Ex Works). Reklamationer ska anmälas skriftligen "
    "inom åtta dagar efter mottagandet. Vid försenad betalning debiteras dröjsmålsränta "
    "enligt räntelagen samt påminnelseavgift."
)


# ---------------------------------------------------------------------------
# Business-day / date helpers
# ---------------------------------------------------------------------------

def is_business_day(d: date) -> bool:
    # fix 6: no document may be issued on a Finnish public holiday.
    return d.weekday() < 5 and d not in config.HOLIDAYS_2025


def business_days_in_month(year: int, month: int) -> list[date]:
    n_days = calendar.monthrange(year, month)[1]
    return [date(year, month, day) for day in range(1, n_days + 1)
            if is_business_day(date(year, month, day))]


def pick_dates(supplier_id: str, year: int, month: int, n: int, rng: random.Random) -> list[date]:
    """Return n ascending business-day dates for a supplier's documents this month."""
    bdays = business_days_in_month(year, month)
    if supplier_id == "s7":
        return [bdays[-1]] * n
    if supplier_id == "s6":
        last_day = date(year, month, calendar.monthrange(year, month)[1])
        window = 3
        candidates = [d for d in bdays if (last_day - d).days <= window]
        while len(candidates) < n:
            window += 2
            candidates = [d for d in bdays if (last_day - d).days <= window]
        return sorted(rng.sample(candidates, n))
    if n <= len(bdays):
        return sorted(rng.sample(bdays, n))
    return sorted(bdays)  # degenerate fallback, never hit at these volumes


# ---------------------------------------------------------------------------
# Identifier helpers (per-document; identity-level identifiers live in config)
# ---------------------------------------------------------------------------

def make_reference(reference_type: str | None, rng: random.Random) -> tuple[str | None, str | None]:
    if reference_type is None:
        return None, None
    if reference_type == "viitenumero":
        base = str(rng.randint(100000, 9999999))
        return "viitenumero", schemas.make_viitenumero(base)
    if reference_type == "ocr":
        base = str(rng.randint(1000000, 99999999))
        return "ocr", schemas.make_ocr(base)
    if reference_type == "rf":
        base = str(rng.randint(100000, 999999999))
        return "rf", config.make_rf(base)
    raise ValueError(f"unknown reference_type {reference_type!r}")


# ---------------------------------------------------------------------------
# Line generation
# ---------------------------------------------------------------------------

def generate_goods_lines(catalog: list[tuple], target_net: Decimal, n_lines: int,
                          rng: random.Random, vat_rate: str) -> list[dict]:
    # fix 5: no duplicate catalogue items within one invoice -- sample
    # without replacement and cap the line count at the catalogue size
    # (rather than padding with repeated random.choice() items).
    catalog_list = list(catalog)
    n_lines = min(n_lines, len(catalog_list))
    items = rng.sample(catalog_list, n_lines)
    weights = [rng.random() + 0.25 for _ in range(n_lines)]
    wsum = sum(weights)
    target_f = float(target_net)
    lines = []
    for item, w in zip(items, weights):
        desc, unit, pmin, pmax = item
        line_target = target_f * (w / wsum)
        unit_price = round(rng.uniform(float(pmin), float(pmax)), 2)
        if unit_price <= 0:
            unit_price = 0.5
        qty = max(1, round(line_target / unit_price))
        unit_price_d = Decimal(str(unit_price)).quantize(Decimal("0.01"))
        line_total_d = (Decimal(qty) * unit_price_d).quantize(Decimal("0.01"))
        lines.append({
            "description": desc, "quantity": str(qty), "unit": unit,
            "unit_price": f"{unit_price_d:.2f}", "vat_rate": vat_rate,
            "line_total": f"{line_total_d:.2f}", "catalog_item": item,
        })
    return lines


def generate_service_lines(desc_unit_pairs: list[tuple[str, str]], target_net: Decimal,
                            rng: random.Random, vat_rate: str) -> list[dict]:
    n = len(desc_unit_pairs)
    weights = [rng.random() + 0.25 for _ in range(n)]
    wsum = sum(weights)
    target_f = float(target_net)
    single_unit_kinds = {"erä", "kk", "vrk", "licence", "kpl"}
    lines = []
    for (desc, unit), w in zip(desc_unit_pairs, weights):
        line_target = target_f * (w / wsum)
        qty = 1 if unit in single_unit_kinds else rng.randint(1, 4)
        unit_price = round(line_target / qty, 2)
        if unit_price <= 0:
            unit_price = 1.0
        unit_price_d = Decimal(str(unit_price)).quantize(Decimal("0.01"))
        line_total_d = (Decimal(qty) * unit_price_d).quantize(Decimal("0.01"))
        lines.append({
            "description": desc, "quantity": str(qty), "unit": unit,
            "unit_price": f"{unit_price_d:.2f}", "vat_rate": vat_rate,
            "line_total": f"{line_total_d:.2f}", "catalog_item": None,
        })
    return lines


def to_schema_lines(working_lines: list[dict]) -> list[dict]:
    return [{"description": l["description"], "quantity": l["quantity"], "unit": l["unit"],
             "unit_price": l["unit_price"], "vat_rate": l["vat_rate"], "line_total": l["line_total"]}
            for l in working_lines]


def assemble_vat_and_totals(schema_lines: list[dict]) -> tuple[list[dict], dict]:
    rate = schema_lines[0]["vat_rate"]
    base = sum((Decimal(l["line_total"]) for l in schema_lines), Decimal("0"))
    amount = (base * Decimal(rate) / 100).quantize(Decimal("0.01"))
    if amount == 0:
        # Decimal signed zero: a credit note's 0% VAT computes to -0.00, but the
        # document prints 0,00 and the key is the ideal reading of the document
        # (D1/F-wave ground-truth principle; found by the F2 parse, 3 Jul 2026).
        amount = Decimal("0.00")
    vat_summary = [{"rate": rate, "base": f"{base:.2f}", "amount": f"{amount:.2f}"}]
    totals = {"net": f"{base:.2f}", "vat": f"{amount:.2f}", "gross": f"{(base + amount):.2f}"}
    return vat_summary, totals


# ---------------------------------------------------------------------------
# Rendering pipeline
# ---------------------------------------------------------------------------

def render_pdf(html_path: Path, pdf_path: Path) -> None:
    url = html_path.resolve().as_uri()
    cmd = [CHROME_PATH, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
           f"--print-to-pdf={pdf_path.resolve()}", url]
    result = subprocess.run(cmd, capture_output=True, timeout=60)
    if result.returncode != 0 or not pdf_path.exists():
        raise RuntimeError(f"chrome failed for {html_path.name}: {result.stderr!r}")


def normalise_pdf(pdf_path: Path) -> None:
    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.add_metadata({"/Producer": "Hapax invoice generator", "/Creator": "Hapax"})
    writer._ID = ArrayObject([ByteStringObject(b"\x00" * 16)] * 2)
    if "/Metadata" in writer._root_object:
        del writer._root_object["/Metadata"]
    with open(pdf_path, "wb") as f:
        writer.write(f)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# View (Jinja context) builder -- the only place canonical values are
# transformed into printed strings, via formatting.py exclusively.
# ---------------------------------------------------------------------------

def build_view(record: dict, locale: str, template_name: str, extra: dict) -> dict:
    inv = record["invoice"]
    supplier = record["supplier"]
    buyer = record["buyer"]
    bank = record["bank"]
    currency = inv["currency"]
    labels = formatting.LABELS[locale]
    doc_type_label = labels["document_invoice"] if inv["type"] == "invoice" else labels["document_credit_note"]

    def fmt_money(v):
        return formatting.format_money(v, locale)

    def fmt_date(v):
        return formatting.format_date(v, locale) if v else None

    lines_view = []
    for l in extra["working_lines"]:
        line_ctx = {
            "description": l["description"], "quantity": formatting.format_quantity(l["quantity"]),
            "unit": l["unit"], "unit_price": fmt_money(l["unit_price"]),
            "vat_rate": formatting.format_rate(l["vat_rate"], locale),
            "line_total": fmt_money(l["line_total"]),
        }
        if template_name == "s8_v2" and l.get("catalog_item") is not None:
            idx = config.CATALOG_S8.index(l["catalog_item"])
            line_ctx["product_code"] = f"TK-{idx + 1:04d}"
        lines_view.append(line_ctx)

    vat_summary_view = [{"rate": formatting.format_rate(row["rate"], locale),
                          "base": fmt_money(row["base"]), "amount": fmt_money(row["amount"])}
                         for row in record["vat_summary"]]
    totals_view = {k: fmt_money(v) for k, v in record["totals"].items()}

    # deterministic 2-page overflow: when overflow_split is set, the last few
    # lines render in a second table on a forced new page, thead repeated --
    # format pattern H8, guarantees exactly 2 pages (never 3).
    split = extra.get("overflow_split")
    if split is not None:
        page1_lines, page2_lines = lines_view[:split], lines_view[split:]
    else:
        page1_lines, page2_lines = lines_view, []

    return {
        "lang": locale, "locale": locale, "labels": labels,
        "doc_type_label": doc_type_label,
        "number": inv["number"],
        "issue_date": fmt_date(inv["issue_date"]),
        "due_date": fmt_date(inv.get("due_date")),
        "supply_date": fmt_date(inv.get("supply_date")),
        # the record stores the verbatim printed phrase (answer-key ideal-reading
        # principle, D1 finding); the view passes it straight through
        "payment_terms_label": inv.get("payment_terms"),
        "reference_value": inv.get("reference_value"),
        "po_number": inv.get("po_number"),
        "original_invoice_number": inv.get("original_invoice_number"),
        "reverse_charge_mention": inv.get("reverse_charge_mention"),
        "currency": currency, "currency_suffix": CURRENCY_SUFFIX[currency],
        "supplier": {**supplier, **bank,
                      "country_name": COUNTRY_NAMES.get(supplier["country"], supplier["country"]),
                      # display form of the registration id (e.g. German court suffix);
                      # the record/key keep the crisp identifier (D1 finding)
                      "business_id": (supplier["business_id"] + extra["registration_suffix"])
                      if extra.get("registration_suffix") else supplier["business_id"]},
        "buyer": {**buyer},
        "lines": lines_view, "page1_lines": page1_lines, "page2_lines": page2_lines,
        "vat_summary": vat_summary_view, "totals": totals_view,
        "font_family": extra["font_family"],
        "terms_block_text": extra.get("terms_block_text"),
    }


# ---------------------------------------------------------------------------
# Main generation
# ---------------------------------------------------------------------------

class Generator:
    def __init__(self) -> None:
        self.rng = random.Random(config.RANDOM_SEED)
        self.env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=False)
        self.invoice_counters: dict[str, int | None] = {}
        self.po_counter = 0
        self.po_register: list[dict] = []
        self.month_invoice_numbers: dict[tuple[str, int], list[str]] = {}
        self.docs: list[dict] = []  # per-document manifest entries
        self.class_counts: dict[str, int] = {}
        self.supplier_counts: dict[str, int] = {}
        self.month_counts: dict[str, int] = {}
        self.oneoff_root_counter = 0

    # -- invoice numbering -------------------------------------------------
    def next_number(self, series_key: str, start: int, fmt) -> str:
        if series_key not in self.invoice_counters or self.invoice_counters[series_key] is None:
            n = start
        else:
            n = self.invoice_counters[series_key] + self.rng.randint(1, 19)
        self.invoice_counters[series_key] = n
        return fmt(n)

    def next_oneoff_start(self) -> int:
        start = 300 + 137 * self.oneoff_root_counter
        self.oneoff_root_counter += 1
        return start

    # -- PO register ---------------------------------------------------
    def issue_po(self, supplier_id: str, invoice_date: date) -> str:
        self.po_counter += 1
        po_number = f"PO-2025-{self.po_counter:03d}"
        po_date = invoice_date - timedelta(days=self.rng.randint(3, 45))
        self.po_register.append({"po_number": po_number, "date": po_date.isoformat(),
                                  "supplier_id": supplier_id})
        return po_number

    # -- record building for a repeat-supplier document ---------------
    def build_repeat_document(self, sid: str, month: int, local_seq: int, n_this_month: int,
                               issue_date: date) -> tuple[dict, dict | None, str, str, dict]:
        """Return (true_record, rendered_record_or_None, class_label, template_name, extra)."""
        sup = config.SUPPLIERS[sid]
        event = config.EVENT_TABLE.get((sid, month, local_seq))
        is_t = sid == "s8" and issue_date >= config.T_CUTOVER_DATE
        # answer-key class labels are the single letters R/O/T/F/S;
        # F1-F4 are internal event codes collapsed to "F" for the class field.
        if event in ("F1", "F2", "F3", "F4"):
            class_label = "F"
        elif event == "S":
            class_label = "S"
        elif is_t:
            class_label = "T"
        else:
            class_label = "R"

        # -- template / numbering / font selection (s8 redesign) --
        if sid == "s8":
            if is_t:
                template_name = sup["v2_template"]
                font_family = sup["v2_font_family"]
                number = self.next_number("s8_v2", sup["v2_invoice_start"], sup["v2_invoice_format"])
            else:
                template_name = sup["template"]
                font_family = sup["font_family"]
                number = self.next_number("s8_v1", sup["invoice_start"], sup["invoice_format"])
        else:
            template_name = sup["template"]
            font_family = sup["font_family"]
            number = self.next_number(sid, sup["invoice_start"], sup["invoice_format"])

        self.month_invoice_numbers.setdefault((sid, month), []).append(number)

        is_credit_note = event in ("F2", "F3")
        doc_type = "credit_note" if is_credit_note else "invoice"
        currency = sup["currency"]
        vat_rate = sup["vat_rate"]
        locale = sup["locale"]

        # -- reference --
        ref_type, ref_value = make_reference(sup["reference_type"], self.rng)

        # -- lines --
        lo, hi = sup["amount_range"]
        target_net = Decimal(str(round(self.rng.uniform(float(lo), float(hi)), 2)))
        po_number = None
        original_invoice_number = None
        terms_block_text = None
        s_exception = False
        rendered_working_lines = None

        if event in ("F2", "F3"):
            # Credit note (F2: s3 Gutschrift referencing September; F3: s1
            # hyvityslasku referencing October). A formal cross-border credit
            # note over pocket change would read as absurd, so the returned
            # value is floored at ~EUR 25 (spot-read finding):
            # only meaningfully-priced items qualify, and the quantity is
            # scaled up until the credit clears the floor.
            pool = [it for it in sup["catalog"] if float(it[3]) >= 6.0]
            item = self.rng.choice(pool)
            desc, unit, pmin, pmax = item
            unit_price = round(self.rng.uniform(float(pmin), float(pmax)), 2)
            qty_floor = max(1, -(-25 // int(max(unit_price, 1))))  # ceil(25/price)
            qty = -self.rng.randint(qty_floor, qty_floor + 5)
            unit_price_d = Decimal(str(unit_price)).quantize(Decimal("0.01"))
            line_total_d = (Decimal(qty) * unit_price_d).quantize(Decimal("0.01"))
            working_lines = [{"description": desc, "quantity": str(qty), "unit": unit,
                               "unit_price": f"{unit_price_d:.2f}", "vat_rate": vat_rate,
                               "line_total": f"{line_total_d:.2f}", "catalog_item": item}]
            ref_month = 9 if event == "F2" else 10
            ref_numbers = self.month_invoice_numbers.get((sid, ref_month), [])
            original_invoice_number = (ref_numbers[0] if event == "F2" else ref_numbers[-1]) \
                if ref_numbers else None
        elif sup["is_goods"]:
            n_lines = config.OVERFLOW_LINE_THRESHOLD if event == "F4" else self.rng.randint(3, 12)
            # the S document's planted hinge line takes one of the n_lines slots,
            # not an extra one -- keeps the invoice inside the 3-12 goods-line rule
            n_regular = n_lines - 1 if event == "S" else n_lines
            working_lines = generate_goods_lines(sup["catalog"], target_net, n_regular, self.rng, vat_rate)
            po_number = self.issue_po(sid, issue_date)
            if event == "F4":
                terms_block_text = F4_TERMS_TEXT
            if event == "S":
                s_exception = True
                # insert the fixed hinge line (true: qty 2 / price 50.00)
                s_line = {"description": config.S_EVENT_LINE_DESCRIPTION,
                          "quantity": "2", "unit": config.S_EVENT_LINE_UNIT,
                          "unit_price": "50.00", "vat_rate": vat_rate,
                          "line_total": "100.00", "catalog_item": None}
                pos = self.rng.randrange(len(working_lines) + 1)
                working_lines.insert(pos, s_line)
                rendered_working_lines = [dict(l) for l in working_lines]
                rendered_working_lines[pos] = {**s_line, "quantity": "50", "unit_price": "2.00"}
        else:  # service supplier: s6, s7
            if sid == "s7":
                # fix 8: a monthly staff-canteen invoice is a per-meal count
                # (52-88 meals at a plausible per-meal price), not a
                # target-net-scaled single line -- the old target-net scaler
                # produced absurd results like "3 ateria a 162,37". Quantity
                # and unit price are drawn directly; target_net is unused
                # here (kept computed above only for RNG-stream uniformity).
                month_name = MONTH_NAMES_FI[month - 1]
                qty = self.rng.randint(52, 88)
                unit_price = round(self.rng.uniform(7.90, 9.60), 2)
                unit_price_d = Decimal(str(unit_price)).quantize(Decimal("0.01"))
                line_total_d = (Decimal(qty) * unit_price_d).quantize(Decimal("0.01"))
                working_lines = [{
                    "description": f"Henkilöstöruokailu, {month_name} 2025", "quantity": str(qty),
                    "unit": "ateria", "unit_price": f"{unit_price_d:.2f}", "vat_rate": vat_rate,
                    "line_total": f"{line_total_d:.2f}", "catalog_item": None,
                }]
            else:  # s6
                n_lines = self.rng.randint(1, 3)
                pairs = self.rng.sample(S6_ROUTES, n_lines)
                working_lines = generate_service_lines(pairs, target_net, self.rng, vat_rate)
                if event == "F1":
                    surcharge_price = round(self.rng.uniform(15.0, 45.0), 2)
                    surcharge_d = Decimal(str(surcharge_price)).quantize(Decimal("0.01"))
                    working_lines.append({"description": "Polttoainelisä", "quantity": "1", "unit": "erä",
                                           "unit_price": f"{surcharge_d:.2f}", "vat_rate": vat_rate,
                                           "line_total": f"{surcharge_d:.2f}", "catalog_item": None})

        schema_lines = to_schema_lines(working_lines)
        vat_summary, totals = assemble_vat_and_totals(schema_lines)

        due_date = None if is_credit_note else (issue_date + timedelta(days=sup["terms_days"])).isoformat()
        # only s3 (Leistungsdatum) and s5 print supply_date; null for everyone else
        supply_date = issue_date.isoformat() if sid in ("s3", "s5") else None

        buyer_vat_id = config.BUYER["vat_id"] if sup["country"] != "FI" else None

        record = {
            "supplier": {"name": sup["name"], "street": sup["street"], "postcode": sup["postcode"],
                         "city": sup["city"], "country": sup["country"], "vat_id": sup["vat_id"],
                         "business_id": sup["business_id"]},
            "buyer": {"name": config.BUYER["name"], "street": config.BUYER["street"],
                      "postcode": config.BUYER["postcode"], "city": config.BUYER["city"],
                      "country": config.BUYER["country"], "vat_id": buyer_vat_id,
                      "business_id": config.BUYER["business_id"]},
            "invoice": {
                "number": number, "type": doc_type, "issue_date": issue_date.isoformat(),
                "supply_date": supply_date, "due_date": due_date,
                "payment_terms": None if is_credit_note else PAYMENT_TERMS_PHRASE[locale](sup["terms_days"]),
                "currency": currency, "po_number": po_number,
                "reference_type": ref_type, "reference_value": ref_value,
                "original_invoice_number": original_invoice_number,
                "reverse_charge_mention": sup["reverse_charge_mention"],
            },
            "bank": {"iban": sup.get("iban"), "bic": sup.get("bic"),
                     "bankgiro": sup.get("bankgiro")},
            "lines": schema_lines, "vat_summary": vat_summary, "totals": totals,
        }

        # documents with a full-length (>= threshold) line table get a forced
        # 2-page split (last 2 lines + totals on page 2) -- H8, guaranteed 2 pages
        overflow_split = (len(working_lines) - 2
                           if len(working_lines) >= config.OVERFLOW_LINE_THRESHOLD else None)

        extra = {"working_lines": rendered_working_lines if rendered_working_lines is not None else working_lines,
                 "font_family": font_family, "terms_block_text": terms_block_text,
                 "locale": locale, "template_name": template_name, "s_exception": s_exception,
                 "overflow_split": overflow_split,
                 "registration_suffix": sup.get("registration_suffix")}

        rendered_record = None
        if rendered_working_lines is not None:
            rendered_record = json.loads(json.dumps(record))
            rendered_record["lines"] = to_schema_lines(rendered_working_lines)
            # vat_summary/totals are identical by construction (line_total unchanged)

        return record, rendered_record, class_label, template_name, extra

    # -- record building for a one-off document ------------------------
    def build_oneoff_document(self, entry: dict, index_in_roster: int, issue_date: date) -> tuple[dict, str, dict]:
        root_key = entry.get("same_supplier_as", entry["key"])
        locale = entry["number_format"]
        currency = entry["currency"]
        vat_rate = entry["vat_rate"]

        if root_key not in self.invoice_counters:
            start = self.next_oneoff_start()
            self.invoice_counters[root_key] = start
            number = self._format_oneoff_number(locale, start)
        else:
            n = self.invoice_counters[root_key] + self.rng.randint(1, 19)
            self.invoice_counters[root_key] = n
            number = self._format_oneoff_number(locale, n)

        ref_type, ref_value = None, None  # one-offs carry no structured reference (decision)

        lo, hi = entry["net_range"]
        target_net = Decimal(str(round(self.rng.uniform(float(lo), float(hi)), 2)))

        po_number = None
        if entry.get("catalog"):  # Brandt: goods
            n_lines = self.rng.randint(3, 6)
            working_lines = generate_goods_lines(entry["catalog"], target_net, n_lines, self.rng, vat_rate)
            if entry["po_eligible"]:
                po_number = self.issue_po(root_key, issue_date)
        elif entry["key"] == "hotelli_ilvesranta":
            # fix 9: two fixed nights at a per-night rate, not a target-net
            # scaled single line -- the old target-net scaler forced
            # quantity=1 for the "vrk" unit (generate_service_lines' single-
            # unit-kind rule) while the description text still said "2 vrk".
            qty = 2
            unit_price = round(self.rng.uniform(120.0, 160.0), 2)
            unit_price_d = Decimal(str(unit_price)).quantize(Decimal("0.01"))
            line_total_d = (Decimal(qty) * unit_price_d).quantize(Decimal("0.01"))
            working_lines = [{
                "description": "Majoitus, myyntimatka", "quantity": str(qty), "unit": "vrk",
                "unit_price": f"{unit_price_d:.2f}", "vat_rate": vat_rate,
                "line_total": f"{line_total_d:.2f}", "catalog_item": None,
            }]
        else:
            working_lines = generate_service_lines(entry["service_lines"], target_net, self.rng, vat_rate)

        schema_lines = to_schema_lines(working_lines)
        vat_summary, totals = assemble_vat_and_totals(schema_lines)

        terms_days = 30  # one-offs: standard 30-day net term
        due_date = (issue_date + timedelta(days=terms_days)).isoformat()

        buyer_vat_id = config.BUYER["vat_id"] if entry["country"] != "FI" else None
        bank_iban, bank_bic = config.ONE_OFF_BANK[entry["key"]]

        record = {
            "supplier": {"name": entry["name"], "street": entry["street"], "postcode": entry["postcode"],
                         "city": entry["city"], "country": entry["country"], "vat_id": entry["vat_id"],
                         "business_id": entry["business_id"]},
            "buyer": {"name": config.BUYER["name"], "street": config.BUYER["street"],
                      "postcode": config.BUYER["postcode"], "city": config.BUYER["city"],
                      "country": config.BUYER["country"], "vat_id": buyer_vat_id,
                      "business_id": config.BUYER["business_id"]},
            "invoice": {
                "number": number, "type": "invoice", "issue_date": issue_date.isoformat(),
                "supply_date": None, "due_date": due_date,
                "payment_terms": PAYMENT_TERMS_PHRASE[locale](terms_days),
                "currency": currency, "po_number": po_number,
                "reference_type": ref_type, "reference_value": ref_value,
                "original_invoice_number": None,
                "reverse_charge_mention": entry["reverse_charge_mention"],
            },
            "bank": {"iban": bank_iban, "bic": bank_bic, "bankgiro": None},
            "lines": schema_lines, "vat_summary": vat_summary, "totals": totals,
        }
        template_name = config.oneoff_template_for(entry, index_in_roster)
        font_family = {
            "oneoff_fi_a": "Georgia, 'Times New Roman', serif",
            "oneoff_fi_b": "Verdana, Geneva, sans-serif",
            "oneoff_de": "Georgia, 'Times New Roman', serif",
            "oneoff_sv": "Tahoma, Geneva, sans-serif",
            "oneoff_en": "'Trebuchet MS', Verdana, sans-serif",
        }[template_name]
        extra = {"working_lines": working_lines, "font_family": font_family,
                 "terms_block_text": None, "locale": locale, "template_name": template_name,
                 "s_exception": False, "registration_suffix": entry.get("registration_suffix")}
        return record, template_name, extra

    @staticmethod
    def _format_oneoff_number(locale: str, n: int) -> str:
        if locale == "de":
            return f"RE-2025-{n:04d}"
        if locale == "sv":
            return f"F{n:05d}"
        if locale in ("en", "en_ie"):
            return f"INV-2025-{n:03d}"
        return f"{n:04d}"

    # -- rendering + writing one document -------------------------------
    def emit(self, doc_id: str, record: dict, class_label: str, template_name: str, extra: dict) -> None:
        errors = schemas.validate_record(record)
        assert not errors, f"{doc_id}: schema validation failed: {errors}"

        rendered_record = extra.pop("_rendered_record", None)
        if rendered_record is not None:
            render_errors = schemas.validate_record(rendered_record)
            assert not render_errors, f"{doc_id}: rendered-record validation failed: {render_errors}"
        render_record = rendered_record if rendered_record is not None else record
        view = build_view(render_record, extra["locale"], template_name, extra)
        template = self.env.get_template(f"{template_name}.html.j2")
        html = template.render(**view)

        html_path = HTML_DIR / f"{doc_id}.html"
        pdf_path = DOCS_DIR / f"{doc_id}.pdf"
        html_path.write_text(html, encoding="utf-8")
        render_pdf(html_path, pdf_path)
        normalise_pdf(pdf_path)

        wrapper = {"schema_version": schemas.SCHEMA_VERSION, "doc_id": doc_id,
                   "class": class_label, "record": record}
        if extra.get("s_exception"):
            wrapper["s_exception"] = True
        (ANSWER_KEY_DIR / f"{doc_id}.json").write_text(
            json.dumps(wrapper, ensure_ascii=False, indent=1), encoding="utf-8")

        self.docs.append({
            "doc_id": doc_id, "class": class_label, "supplier": record["supplier"]["name"],
            "month": record["invoice"]["issue_date"][:7],
            "html_sha256": sha256_of(html_path), "pdf_sha256": sha256_of(pdf_path),
        })
        self.class_counts[class_label] = self.class_counts.get(class_label, 0) + 1

    # -- generation loop --------------------------------------------------------
    def run(self) -> None:
        for month in range(1, 13):
            for sid in config.REPEAT_SUPPLIER_ORDER:
                n = config.MONTHLY_MATRIX[sid][month - 1]
                if n == 0:
                    continue
                dates = pick_dates(sid, YEAR, month, n, self.rng)
                for local_seq, issue_date in enumerate(dates, start=1):
                    record, rendered_record, class_label, template_name, extra = \
                        self.build_repeat_document(sid, month, local_seq, n, issue_date)
                    doc_id = f"{YEAR}-{month:02d}_{sid}_{local_seq:02d}"
                    extra["_rendered_record"] = rendered_record
                    self.emit(doc_id, record, class_label, template_name, extra)
                    self.supplier_counts[sid] = self.supplier_counts.get(sid, 0) + 1
                    mk = f"{YEAR}-{month:02d}"
                    self.month_counts[mk] = self.month_counts.get(mk, 0) + 1
                    if len(self.docs) % 20 == 0:
                        print(f"  {len(self.docs)}/198 documents rendered...", flush=True)

            for idx, entry in enumerate(config.ONE_OFFS):
                if entry["month"] != month:
                    continue
                dates = pick_dates("_oneoff", YEAR, month, 1, self.rng)
                issue_date = dates[0]
                record, template_name, extra = self.build_oneoff_document(entry, idx, issue_date)
                slug = entry["key"].replace("_", "-")
                doc_id = f"{YEAR}-{month:02d}_{slug}_01"
                self.emit(doc_id, record, "O", template_name, extra)
                root_key = entry.get("same_supplier_as", entry["key"])
                self.supplier_counts[root_key] = self.supplier_counts.get(root_key, 0) + 1
                mk = f"{YEAR}-{month:02d}"
                self.month_counts[mk] = self.month_counts.get(mk, 0) + 1
                if len(self.docs) % 20 == 0:
                    print(f"  {len(self.docs)}/198 documents rendered...", flush=True)

        print(f"  {len(self.docs)}/198 documents rendered (done)", flush=True)

    def write_manifest(self) -> None:
        manifest = {
            "chrome_version": CHROME_VERSION,
            "pypdf_version": __import__("pypdf").__version__,
            "random_seed": config.RANDOM_SEED,
            "document_count": len(self.docs),
            "class_counts": self.class_counts,
            "supplier_counts": self.supplier_counts,
            "month_counts": self.month_counts,
            "po_register": self.po_register,
            "files": {d["doc_id"]: {"class": d["class"], "supplier": d["supplier"], "month": d["month"],
                                     "html_sha256": d["html_sha256"], "pdf_sha256": d["pdf_sha256"]}
                       for d in self.docs},
        }
        MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> None:
    for d in (HTML_DIR, DOCS_DIR, ANSWER_KEY_DIR):
        d.mkdir(parents=True, exist_ok=True)
    print("Generating invoice-processing corpus (198 documents)...", flush=True)
    gen = Generator()
    gen.run()
    gen.write_manifest()
    print(f"Done. class_counts={gen.class_counts}", flush=True)
    print(f"Manifest written to {MANIFEST_PATH}", flush=True)


if __name__ == "__main__":
    main()
