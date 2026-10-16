"""Shared locale rendering — the ONE place number/date formatting lives.

Used by both the HTML templates (code/generate_invoices.py passes these
functions into the Jinja environment) and the validator's re-rendering
checks (code/validate_data.py imports this module directly). Money and
quantities are canonical decimal.Decimal / canonical strings everywhere else
(schemas.py); this module is only ever called at the point of turning a
canonical value into the printed string for one document locale, or in the
validator, turning a canonical value into the printed string it expects to
find in the text layer.

Locale keys used throughout the corpus: "fi" (Finnish), "fi_compact" (s2's
unspaced narrow-table variant), "de" (German), "sv" (Swedish), "en" (English
-- s5 and the English-language one-offs), "en_ie" (English vocabulary,
Irish DD/MM/YYYY dates -- the Ashquill Software one-off only, fix 10).

Grounding: the Finnish and DE/SE/EE national number and date formats.
"""
from __future__ import annotations

from decimal import Decimal


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------

def format_money(value: str | Decimal, locale: str) -> str:
    """Render a canonical money string (e.g. "1841.00", "-52.00") in the
    printed convention for the given locale. Sign is kept as a leading '-'.
    """
    d = Decimal(value)
    negative = d < 0
    d = abs(d)
    whole, frac = f"{d:.2f}".split(".")
    if locale == "de":
        # 1.234,56 -- dot thousands, comma decimal
        grouped = _group(whole, ".")
        out = f"{grouped},{frac}"
    elif locale in ("fi", "sv"):
        # 1 234,56 -- space thousands, comma decimal
        grouped = _group(whole, " ")
        out = f"{grouped},{frac}"
    elif locale == "fi_compact":
        # 1234,56 -- no thousands separator, comma decimal (s2's narrow table)
        out = f"{whole},{frac}"
    elif locale in ("en", "en_ie"):
        # 1,234.56 -- comma thousands, dot decimal
        grouped = _group(whole, ",")
        out = f"{grouped}.{frac}"
    else:
        raise ValueError(f"unknown locale: {locale!r}")
    return f"-{out}" if negative else out


def _group(whole_digits: str, sep: str) -> str:
    """Insert a thousands separator every three digits from the right."""
    rev = whole_digits[::-1]
    chunks = [rev[i:i + 3] for i in range(0, len(rev), 3)]
    return sep.join(chunks)[::-1]


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

def format_date(iso_date: str, locale: str) -> str:
    """Render an ISO YYYY-MM-DD date string in the printed convention."""
    year, month, day = iso_date.split("-")
    if locale == "sv":
        return f"{year}-{month}-{day}"
    if locale in ("fi", "fi_compact", "de", "en"):
        return f"{day}.{month}.{year}"
    if locale == "en_ie":
        # fix 10: Irish convention is DD/MM/YYYY, not the dotted DD.MM.YYYY
        # used by the rest of the "en" family.
        return f"{day}/{month}/{year}"
    raise ValueError(f"unknown locale: {locale!r}")


# ---------------------------------------------------------------------------
# Quantities
# ---------------------------------------------------------------------------

def format_quantity(value: str) -> str:
    """Quantities are canonical integer strings; printed form drops any
    sign convention peculiarities but keeps the minus for credit notes."""
    return str(int(value))


def format_rate(value: str, locale: str) -> str:
    """VAT rate values are canonical decimal strings (e.g. "14.0"); printed
    without a redundant trailing zero/point ("14", "0") and, for a genuine
    fraction, locale-rendered: fi/fi_compact/de/sv use a decimal comma
    ("25,5"); en/en_ie keep the dot ("25.5"). (fix 4)
    """
    stripped = value.rstrip("0").rstrip(".") if "." in value else value
    if locale in ("fi", "fi_compact", "de", "sv"):
        return stripped.replace(".", ",")
    if locale in ("en", "en_ie"):
        return stripped
    raise ValueError(f"unknown locale: {locale!r}")


# ---------------------------------------------------------------------------
# Per-locale vocabulary — presentation labels only (not schema fields)
# ---------------------------------------------------------------------------

LABELS: dict[str, dict[str, str]] = {
    "fi": {
        "document_invoice": "Lasku", "document_credit_note": "Hyvityslasku",
        "invoice_number": "Laskun numero", "issue_date": "Laskun päivä",
        "due_date": "Eräpäivä", "supply_date": "Toimituspäivä",
        "payment_terms": "Maksuehto", "reference": "Viitenumero",
        "po_number": "Tilausnumero", "original_invoice": "Viittaus laskuun",
        "seller": "Myyjä", "buyer": "Ostaja", "business_id": "Y-tunnus",
        "vat_id": "ALV-tunnus", "description": "Nimike", "quantity": "Määrä",
        "unit": "Yksikkö", "unit_price": "A-hinta", "line_total": "Yhteensä",
        "net": "Veroton yhteensä", "vat": "ALV", "gross": "Maksettava",
        "vat_rate": "ALV %", "bank": "Pankkiyhteys", "iban": "IBAN",
        "bic": "BIC", "days_net": "netto", "page": "Sivu",
        "continued": "jatkuu",
    },
    "de": {
        "document_invoice": "Rechnung", "document_credit_note": "Gutschrift",
        "invoice_number": "Rechnungsnummer", "issue_date": "Rechnungsdatum",
        "due_date": "Fälligkeitsdatum", "supply_date": "Leistungsdatum",
        "payment_terms": "Zahlungsbedingungen", "reference": "Verwendungszweck",
        "po_number": "Bestellnummer", "original_invoice": "Bezug Rechnung",
        "seller": "Verkäufer", "buyer": "Käufer", "business_id": "Registernummer",
        "vat_id": "USt-IdNr.", "description": "Bezeichnung", "quantity": "Menge",
        "unit": "Einheit", "unit_price": "Einzelpreis", "line_total": "Gesamt",
        "net": "Netto", "vat": "Umsatzsteuer", "gross": "Brutto",
        "vat_rate": "USt %", "bank": "Bankverbindung", "iban": "IBAN",
        "bic": "BIC", "days_net": "netto", "page": "Seite",
        "continued": "Fortsetzung",
    },
    "sv": {
        "document_invoice": "Faktura", "document_credit_note": "Kreditfaktura",
        "invoice_number": "Fakturanummer", "issue_date": "Fakturadatum",
        "due_date": "Förfallodatum", "supply_date": "Leveransdatum",
        "payment_terms": "Betalningsvillkor", "reference": "OCR",
        "po_number": "Ordernummer", "original_invoice": "Referens faktura",
        "seller": "Säljare", "buyer": "Köpare", "business_id": "Org.nr",
        "vat_id": "Momsreg.nr", "description": "Benämning", "quantity": "Antal",
        "unit": "Enhet", "unit_price": "À-pris", "line_total": "Summa",
        "net": "Netto", "vat": "Moms", "gross": "Att betala",
        "vat_rate": "Moms %", "bank": "Bankgiro", "iban": "IBAN",
        "bic": "BIC", "days_net": "netto", "page": "Sida",
        "continued": "forts.", "terms_heading": "Leveransvillkor",
    },
    "en": {
        "document_invoice": "Invoice", "document_credit_note": "Credit note",
        "invoice_number": "Invoice number", "issue_date": "Issue date",
        "due_date": "Due date", "supply_date": "Supply date",
        "payment_terms": "Payment terms", "reference": "Reference",
        "po_number": "PO number", "original_invoice": "Reference invoice",
        "seller": "Seller", "buyer": "Buyer", "business_id": "Business ID",
        "vat_id": "VAT ID", "description": "Description", "quantity": "Qty",
        "unit": "Unit", "unit_price": "Unit price", "line_total": "Line total",
        "net": "Net total", "vat": "VAT", "gross": "Total due",
        "vat_rate": "VAT %", "bank": "Bank details", "iban": "IBAN",
        "bic": "BIC", "days_net": "net", "page": "Page",
        "continued": "continued",
    },
}
# fi_compact (s2) reuses the Finnish vocabulary; only the number/date grain differs.
LABELS["fi_compact"] = LABELS["fi"]
# en_ie (Ashquill Software, fix 10) reuses the English vocabulary; only the
# date grain (DD/MM/YYYY) differs.
LABELS["en_ie"] = LABELS["en"]
