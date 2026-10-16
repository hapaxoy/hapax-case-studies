"""
config.py -- Master data, layout parameters, and the class schedule for the
ERP Cleanup synthetic corpus.

Every tunable used by generate_documents.py and validate_data.py lives here.
Nothing about counts, ranges, seeds, or column layouts is buried in the
generator logic -- the generator only implements *how* to render/validate,
never *how many* or *what range*.

Master data (vendors/materials/customers/GL accounts) is generated
deterministically at import time from RANDOM_SEED, using a private
np.random.default_rng instance that is not shared with document generation.
Regenerating this module always produces byte-identical master data.
"""

from pathlib import Path
import numpy as np

# ---------------------------------------------------------------------------
# Paths (never absolute, always relative to this file's location)
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DOCUMENTS_DIR = DATA_DIR / "documents"
ANSWER_KEY_DIR = DATA_DIR / "answer_key"

# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

RANDOM_SEED = 42

# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------

COMPANY_NAME = "Jalavakoski Konepaja Oy"
COMPANY_CODE = "1000"
PURCH_ORG = "1000"
SALES_ORG = "1000"

# ---------------------------------------------------------------------------
# In-world calendar
# ---------------------------------------------------------------------------

MONTHS = [f"2025-{m:02d}" for m in range(1, 13)]
DOCS_PER_TYPE_PER_MONTH = 4
TOTAL_DOCS = len(MONTHS) * DOCS_PER_TYPE_PER_MONTH * 5  # 240

TRANSACTION_TYPES = ["FBL3N", "ME2M", "VA05", "FBL1N", "MB52"]

# Volume shape: line items per document, per type (min, max).
# FBL1N is "per vendor"; the vendor-count range is separate (below).
LINE_ITEM_RANGE = {
    "FBL3N": (20, 120),
    "ME2M": (10, 60),
    "VA05": (15, 80),
    "FBL1N": (5, 40),   # per vendor
    "MB52": (40, 150),
}
FBL1N_VENDORS_PER_DOC_RANGE = (3, 6)

# ---------------------------------------------------------------------------
# SAP users (report header "Benutzer")
# ---------------------------------------------------------------------------

SAP_USERS = ["MHAKALA", "JVIRTA", "SLEHTO", "TKOSKI", "AKORHO", "PNIEMI", "RSALO", "EMAKI"]

# ---------------------------------------------------------------------------
# Finnish VAT (company is Finnish, SAP configuration is German-locale)
# ---------------------------------------------------------------------------

VAT_RATES = [0.255, 0.14, 0.10, 0.0]
VAT_RATE_WEIGHTS = [0.70, 0.10, 0.10, 0.10]

# ---------------------------------------------------------------------------
# Plants / storage locations
# ---------------------------------------------------------------------------

PLANTS = {"1000": "Tampere", "2000": "Turku"}
STORAGE_LOCATIONS = ["0001", "0002", "0088"]

# ---------------------------------------------------------------------------
# Layout: shared rendering conventions (SAP spool format)
# ---------------------------------------------------------------------------

PAGE_HEIGHT_LINES = 65
PAGE_BREAK_DRIFT = 3           # +/- lines, drawn once per document
COLUMN_WIDTH_JITTER_MAX = 3    # +0..3 chars added to "jitter-eligible" columns, once per document
EXTRA_HEADER_LINE_PROBABILITY = 0.15  # chance of one extra metadata header line per document

# ---------------------------------------------------------------------------
# Master-data name pools (defined literally, as an alternative to
# procedural generation; numeric attributes
# (payment terms, ranges, VAT draws, etc.) are still drawn from the seeded
# rng below so the *numbers* are reproducibly random even though the names
# are curated).
# ---------------------------------------------------------------------------

# 39 non-fixed vendor names (vendor #10040 "Lührer GmbH" is fixed
# separately). Suffix implies country: GmbH/AG -> DE, Oy -> FI, AB -> SE,
# AS -> NO, A/S -> DK.
_VENDOR_NAME_POOL = [
    "Schober Stahlbau GmbH",
    "Wagner Präzisionstechnik GmbH & Co. KG",
    "Fruhner Maschinenbau AG",
    "Bauer Metallwerke GmbH",
    "Hollmann Industriebedarf GmbH",
    "Schalz & Söhne GmbH",
    "Becker Normteile GmbH",
    "Krenz Werkzeugbau GmbH",
    "Wolf Federntechnik GmbH",
    "Krüger Schweißtechnik GmbH",
    "Scharff Blechverarbeitung GmbH",
    "Zimmermann Guss GmbH",
    "Braun Antriebstechnik GmbH & Co. KG",
    "Lange Verbindungselemente GmbH",
    "Richter Stahlhandel GmbH",
    "Neumann Komponenten GmbH",
    "Vogel Präzisionsteile GmbH",
    "Frank Hydraulik GmbH",
    "Albrecht Zerspanungstechnik GmbH",
    "Zorn Werkzeuge GmbH",
    "Beck Metallhandel GmbH",
    "Sauer Fertigungstechnik GmbH",
    "Peters Industriewerke GmbH",
    "Virtanen Konepaja Oy",
    "Koskinen Teräs Oy",
    "Aaltonen Metalli Oy",
    "Mäkinen Komponentti Oy",
    "Salminen Konetekniikka Oy",
    "Peltonen Konepaja Oy",
    "Nyström Stål AB",
    "Lindqvist Verktyg AB",
    "Bergström Industri AB",
    "Karlsson Mekaniska AB",
    "Stavnes Maskin AS",
    "Haugen Metallvarer AS",
    "Kristiansen Stål AS",
    "Sørensen Fastgørelse A/S",
    "Andersen Værktøj A/S",
    "Jørgensen Industri A/S",
]
_VENDOR_FIXED_NAME = "Lührer GmbH"  # vendor 10040, fixed

_SUFFIX_TO_COUNTRY = {
    "GmbH": "DE", "AG": "DE", "KG": "DE",
    "Oy": "FI",
    "AB": "SE",
    "AS": "NO",
    "A/S": "DK",
}


def _country_for_name(name):
    """Infer country from the legal-form suffix at the end of a company name."""
    for suffix, country in sorted(_SUFFIX_TO_COUNTRY.items(), key=lambda kv: -len(kv[0])):
        if name.endswith(suffix):
            return country
    return "DE"


def _build_vendors(rng):
    """Build the ~40-vendor master. Deterministic given rng. Vendor 10040 is
    fixed to 'Lührer GmbH'; the remaining 39 numbers 10001-10039
    are assigned to the literal name pool in list order (no shuffle needed --
    order in the pool is already arbitrary)."""
    vendors = []
    for i, name in enumerate(_VENDOR_NAME_POOL):
        number = f"{10001 + i:05d}"
        country = _country_for_name(name)
        # Only Swedish vendors bill in SEK ("a few SEK for the FBL1N F-class");
        # all others (including NO/DK) bill in EUR -- a declared simplification.
        currency = "SEK" if country == "SE" else "EUR"
        payment_terms_days = int(rng.choice([14, 30, 60], p=[0.3, 0.5, 0.2]))
        order_value_min = round(float(rng.uniform(200, 3000)), 2)
        order_value_max = round(order_value_min + float(rng.uniform(2000, 20000)), 2)
        vendors.append({
            "number": number,
            "name": name,
            "country": country,
            "currency": currency,
            "payment_terms_days": payment_terms_days,
            "order_value_min": order_value_min,
            "order_value_max": order_value_max,
        })
    number = "10040"
    vendors.append({
        "number": number,
        "name": _VENDOR_FIXED_NAME,
        "country": "DE",
        "currency": "EUR",
        "payment_terms_days": 30,
        "order_value_min": 500.0,
        "order_value_max": 25000.0,
    })
    return vendors


# Materials: short texts by category (German-flavoured, plant/consumables
# flavour).
_MATERIAL_TEXTS = {
    "machined": [
        "Lagerbuchse Stahl 20x30", "Zahnrad Modul 2 Z24", "Antriebswelle gehärtet",
        "Flanschplatte gefräst", "Hydraulikzylinder klein", "Kolbenstange verchromt",
        "Getriebegehäuse Alu", "Passfeder DIN 6885", "Exzenterwelle Stahl",
        "Kupplungsscheibe Stahl", "Führungsbuchse Bronze", "Nockenwelle geschliffen",
        "Distanzhülse Stahl 12x40", "Spannring verzinkt", "Adapterflansch Alu",
        "Lagerdeckel Grauguss", "Ritzelwelle gehärtet", "Spannzange ER32",
        "Führungsschiene Stahl", "Kupplungsnabe Stahl",
    ],
    "fastener": [
        "Sechskantschraube M8x40", "Sechskantschraube M10x60", "Zylinderschraube M6x20",
        "Sechskantmutter M8", "Scheibe DIN 125 M8", "Sicherungsring DIN 471 20mm",
        "Stiftschraube M10x50", "Innensechskantschraube M5x16", "Unterlegscheibe M10",
        "Federring DIN 127 M8", "Blechschraube 4,2x25", "Gewindestift M6x12",
        "Passschraube M12x80", "Kronenmutter M10", "Splint DIN 94 3x25",
    ],
    "raw_steel": [
        "Flachstahl 40x5mm", "Rundstahl Durchmesser 20mm", "Vierkantstahl 25x25mm",
        "Stahlblech 2mm verzinkt", "Rundrohr Stahl 30x2mm", "Winkelstahl 40x40x4",
        "Walzdraht 6mm", "Stahlblech 4mm warmgewalzt", "Sechskantstahl 22mm",
        "T-Profil Stahl 30x30x4", "Vierkantrohr 40x40x3", "Blankstahl rund 16mm",
        "Stahlblech 1mm kaltgewalzt",
    ],
    "consumable": [
        "Schweißdraht 1,0mm", "Reinigungsmittel Industrie", "Schneidöl Fass 20L",
        "Schleifscheibe 125mm", "Handschuhe Arbeitsschutz", "Kühlschmierstoff 5L",
        "Poliertuch Industrie", "Klebstoff Industrie 250ml", "Markierfarbe Metall",
        "Schutzbrille Industrie", "Trennscheibe 230mm", "Gewindeschneidöl 1L",
    ],
}

_MATERIAL_UNIT = {"machined": "ST", "fastener": "ST", "raw_steel": "KG", "consumable": "ST"}
_MATERIAL_PRICE_BAND = {
    "machined": (15.00, 450.00),
    "fastener": (0.05, 8.00),
    "raw_steel": (0.90, 6.50),
    "consumable": (3.00, 60.00),
}


def _build_materials(rng):
    """Build the ~60-material master. Category mix and per-material price
    sub-range are drawn from the seeded rng; short texts are literal pools
    (declared)."""
    materials = []
    idx = 0
    for category, texts in _MATERIAL_TEXTS.items():
        for text in texts:
            number = f"{60000000 + idx * 7:08d}"
            band_lo, band_hi = _MATERIAL_PRICE_BAND[category]
            price_lo = round(float(rng.uniform(band_lo, band_hi * 0.5)), 2)
            price_hi = round(float(rng.uniform(price_lo * 1.3, band_hi)), 2)
            materials.append({
                "number": number,
                "text": text,
                "category": category,
                "unit": _MATERIAL_UNIT[category],
                "price_min": price_lo,
                "price_max": max(price_hi, price_lo + 0.05),
            })
            idx += 1
    return materials


# Customers: Nordic/German mid-market names, plus the F-class VA05 "horror"
# names (pipe/dash sequences that break naive pipe-splitting). The horror
# names are part of the master data so cross-transaction checks pass.
_CUSTOMER_NAME_POOL = [
    "Nordfeld Bygg AB", "Rantanen Teollisuus Oy", "Havneberg Industri AS",
    "Lehmann Anlagenbau GmbH", "Storaas Mekanisk AS", "Petersen Metallteknik A/S",
    "Grunwald Maschinenhandel GmbH", "Toivonen Konepaja Oy", "Dahlgren Verkstad AB",
    "Reinholt Fertigung GmbH", "Kallio Teknologia Oy", "Bruhn Industriebau GmbH",
    "Solheim Produksjon AS", "Wennberg Industri AB", "Laaksonen Metalliteollisuus Oy",
    "Bjerregaard Produktion A/S", "Frenn Systemtechnik GmbH", "Ahonen Konepaja Oy",
    "Skarström Verkstads AB", "Berglund Industriteknik AB", "Möller Anlagentechnik GmbH",
    "Skjold Mekaniske AS", "Kettunen Tuotanto Oy", "Vogt Industriebedarf GmbH",
    "Östberg Teknik AB",
]
VA05_HORROR_CUSTOMER_NAMES = [
    "Nord | Bygg Sverige AB",
    "K-M--Teknik A/S",
    "Møller | Søn A/S",
    "Bygg-Partner | Öst AB",
    "H-P--Industri AS",
]


def _build_customers(rng):
    customers = []
    all_names = _CUSTOMER_NAME_POOL + VA05_HORROR_CUSTOMER_NAMES
    for i, name in enumerate(all_names):
        number = f"{20001 + i:05d}"
        country = _country_for_name(name)
        customers.append({
            "number": number,
            "name": name,
            "country": country,
            "currency": "EUR",
            "is_horror_name": name in VA05_HORROR_CUSTOMER_NAMES,
        })
    return customers


# G/L chart of accounts: (number, German name, amount_min, amount_max, vat_relevant)
_GL_ACCOUNTS_RAW = [
    ("400000", "Materialaufwand", 500, 50000, True),
    ("416000", "Fremdinstandhaltung", 200, 15000, True),
    ("476000", "Werkzeuge und Kleingeräte", 100, 8000, True),
    ("480000", "Bürobedarf", 20, 2000, True),
    ("620000", "Fertigungslöhne", 1000, 40000, False),
    ("635000", "Energiekosten", 500, 20000, True),
    ("650000", "Instandhaltung Maschinen", 300, 25000, True),
    ("660000", "Fuhrpark", 200, 10000, True),
    ("680000", "Versicherungen", 100, 15000, False),
    ("700000", "Miete und Pacht", 1000, 30000, False),
    ("730000", "Beratungskosten", 500, 25000, True),
    ("160000", "Verbindlichkeiten aus Lieferungen und Leistungen", 100, 100000, False),
    ("154000", "Forderungen aus Lieferungen und Leistungen", 100, 80000, False),
    ("399000", "Sonstige betriebliche Aufwendungen", 50, 10000, True),
    ("480500", "Reisekosten", 50, 5000, True),
    ("490000", "Abschreibungen", 500, 40000, False),
    ("510000", "Fremdleistungen", 300, 30000, True),
    ("440000", "Verpackungsmaterial", 50, 6000, True),
    ("455000", "Hilfs- und Betriebsstoffe", 100, 9000, True),
    ("670000", "Telekommunikation", 50, 3000, True),
]


def _build_gl_accounts():
    return [
        {"number": n, "name": name, "amount_min": float(lo), "amount_max": float(hi), "vat_relevant": vat}
        for (n, name, lo, hi, vat) in _GL_ACCOUNTS_RAW
    ]


# ---------------------------------------------------------------------------
# Build master data at import time (deterministic, private rng)
# ---------------------------------------------------------------------------

_master_rng = np.random.default_rng(RANDOM_SEED)
VENDORS = _build_vendors(_master_rng)
MATERIALS = _build_materials(_master_rng)
CUSTOMERS = _build_customers(_master_rng)
GL_ACCOUNTS = _build_gl_accounts()

VENDORS_BY_NUMBER = {v["number"]: v for v in VENDORS}
MATERIALS_BY_NUMBER = {m["number"]: m for m in MATERIALS}
CUSTOMERS_BY_NUMBER = {c["number"]: c for c in CUSTOMERS}
GL_ACCOUNTS_BY_NUMBER = {a["number"]: a for a in GL_ACCOUNTS}

SEK_VENDOR_NUMBERS = [v["number"] for v in VENDORS if v["currency"] == "SEK"]

# ---------------------------------------------------------------------------
# Column layouts: field, German header, width,
# alignment ("L"/"R"), and whether the column participates in the
# per-document width-jitter axis.
# ---------------------------------------------------------------------------

FBL3N_COLUMNS = [
    {"field": "posting_date", "header": "Buch.datum", "width": 10, "align": "L", "jitter": False},
    {"field": "document_number", "header": "Belegnr", "width": 10, "align": "L", "jitter": False},
    {"field": "document_type", "header": "BelArt", "width": 6, "align": "L", "jitter": False},
    {"field": "debit_credit", "header": "S/H", "width": 3, "align": "L", "jitter": False},
    {"field": "amount", "header": "Betrag", "width": 15, "align": "R", "jitter": False},
    {"field": "tax_amount", "header": "Steuerbetr.", "width": 13, "align": "R", "jitter": False},
    {"field": "clearing_document", "header": "AusglBeleg", "width": 10, "align": "L", "jitter": False},
    {"field": "reference", "header": "Referenz", "width": 15, "align": "L", "jitter": True},
    {"field": "text", "header": "Text", "width": 20, "align": "L", "jitter": True},
]
# V-class: reordered + one added rendered-only column (Zuordnung). Extra
# column data never enters the schema payload.
FBL3N_V_EXTRA_COLUMN = {"field": "assignment_extra", "header": "Zuordnung", "width": 12, "align": "L", "jitter": False}
FBL3N_V_FIELD_ORDER = [
    "posting_date", "document_type", "document_number", "debit_credit",
    "amount", "tax_amount", "assignment_extra", "clearing_document", "text",
]
# NOTE: the S-class silent error originally lived in FBL3N (amount<->tax
# swap) but was relocated to ME2M during review: FBL3N's
# S/H-split, label-matched totals make any amount-column swap arithmetically
# LOUD (the router would catch it, falsifying the pre-registered "silent"
# outcome).

ME2M_COLUMNS = [
    {"field": "po_number", "header": "Bestellnr", "width": 10, "align": "L", "jitter": False},
    {"field": "item", "header": "Pos", "width": 4, "align": "R", "jitter": False},
    {"field": "order_date", "header": "Bestelldat.", "width": 11, "align": "L", "jitter": False},
    {"field": "vendor_number", "header": "Lieferant", "width": 9, "align": "L", "jitter": False},
    {"field": "vendor_name", "header": "Kreditorenname", "width": 22, "align": "L", "jitter": True},
    {"field": "material", "header": "Material", "width": 10, "align": "L", "jitter": False},
    {"field": "material_text", "header": "Kurztext", "width": 20, "align": "L", "jitter": True},
    {"field": "quantity", "header": "Menge", "width": 12, "align": "R", "jitter": False},
    {"field": "net_price", "header": "Nettopreis", "width": 12, "align": "R", "jitter": False},
    {"field": "net_value", "header": "Nettowert", "width": 14, "align": "R", "jitter": False},
    {"field": "currency", "header": "Whg", "width": 4, "align": "L", "jitter": False},
    {"field": "still_to_deliver_qty", "header": "Noch offen Mge", "width": 14, "align": "R", "jitter": False},
    {"field": "still_to_deliver_value", "header": "Noch offen Wert", "width": 15, "align": "R", "jitter": False},
]
# F-class: inserted goods-receipt-date column ("system patch"), shifts
# everything after it. Rendered-only field, not in the schema.
ME2M_F_EXTRA_COLUMN = {"field": "goods_receipt_date", "header": "WE-Datum", "width": 10, "align": "L", "jitter": False}
ME2M_F_INSERT_AFTER = "order_date"
ME2M_F_PLANTED_MECHANISM = "inserted_column:we_datum"
# S-class (iteration 3): headers stay
# CANONICAL; the VALUES of Nettopreis and "Noch offen Wert" are written into
# each other's columns. Upstream corruption -- the document lies. Any
# text-only reader (LLM or generated parser, positional or label-driven)
# extracts the printed values; totals still reconcile because Nettowert is
# untouched; schema and master-data checks pass. Only reconciliation against
# an independent truth (the answer key; in production, the source system)
# reveals it. A line-level price*quantity cross-check would also catch it;
# the router does not run one, by design.
ME2M_S_VALUE_SWAP = ("net_price", "still_to_deliver_value")
ME2M_S_PLANTED_MECHANISM = "value_swap:net_price<->still_to_deliver_value"

VA05_COLUMNS = [
    {"field": "sales_document", "header": "Verkaufsbeleg", "width": 13, "align": "L", "jitter": False},
    {"field": "doc_date", "header": "Belegdatum", "width": 10, "align": "L", "jitter": False},
    {"field": "sold_to", "header": "Auftraggeber", "width": 25, "align": "L", "jitter": True},
    {"field": "material", "header": "Material", "width": 10, "align": "L", "jitter": False},
    {"field": "order_quantity", "header": "Menge", "width": 12, "align": "R", "jitter": False},
    {"field": "net_value", "header": "Nettowert", "width": 14, "align": "R", "jitter": False},
    {"field": "currency", "header": "Whg", "width": 4, "align": "L", "jitter": False},
    {"field": "delivery_status", "header": "Lieferstatus", "width": 14, "align": "L", "jitter": False},
]
VA05_V_EXTRA_COLUMN = {"field": "wbs_element", "header": "PSP-Element", "width": 12, "align": "L", "jitter": False}
VA05_V_FIELD_ORDER = [
    "doc_date", "sales_document", "sold_to", "wbs_element", "material",
    "order_quantity", "currency", "net_value", "delivery_status",
]
VA05_F_PLANTED_MECHANISM = "delimiter_collision:pipe_dash_in_sold_to"

FBL1N_COLUMNS = [
    {"field": "status", "header": "St", "width": 5, "align": "L", "jitter": False},
    {"field": "document_number", "header": "Belegnr", "width": 10, "align": "L", "jitter": False},
    {"field": "document_type", "header": "BelArt", "width": 6, "align": "L", "jitter": False},
    {"field": "document_date", "header": "Belegdatum", "width": 10, "align": "L", "jitter": False},
    {"field": "posting_date", "header": "Buchungsdatum", "width": 13, "align": "L", "jitter": False},
    {"field": "due_date", "header": "Fälligkeit", "width": 10, "align": "L", "jitter": False},
    {"field": "debit_credit", "header": "S/H", "width": 3, "align": "L", "jitter": False},
    {"field": "amount", "header": "Betrag", "width": 15, "align": "R", "jitter": False},
    {"field": "currency", "header": "Whg", "width": 4, "align": "L", "jitter": False},
    {"field": "clearing_document", "header": "AusglBeleg", "width": 10, "align": "L", "jitter": False},
]
FBL1N_F_PLANTED_MECHANISM = "currency_change:mid_table_sek"
FBL1N_STATUS_CODES = {"open": "@0A@", "partial": "@09@", "cleared": "@08@"}

MB52_COLUMNS = [
    {"field": "material", "header": "Material", "width": 10, "align": "L", "jitter": False},
    {"field": "material_text", "header": "Materialkurztext", "width": 24, "align": "L", "jitter": True},
    {"field": "unit", "header": "Einh", "width": 4, "align": "L", "jitter": False},
    {"field": "unrestricted", "header": "Frei verwendbar", "width": 15, "align": "R", "jitter": False},
    {"field": "quality_inspection", "header": "In Qual.-prüf.", "width": 14, "align": "R", "jitter": False},
    {"field": "blocked", "header": "Gesperrt", "width": 12, "align": "R", "jitter": False},
    {"field": "value_unrestricted", "header": "Wert frei verw.", "width": 15, "align": "R", "jitter": False},
    {"field": "currency", "header": "Whg", "width": 4, "align": "L", "jitter": False},
]
MB52_PLANT_INDENT = 0
MB52_STORLOC_INDENT = 2
MB52_MATERIAL_INDENT = 4

# ---------------------------------------------------------------------------
# Generation parameters (amount/quantity bands, business logic knobs).
# Kept here, not in generate_documents.py, per the "config not buried in
# logic" convention.
# ---------------------------------------------------------------------------

# Quantity ranges per material category, used to derive PO/sales-order
# quantities once a target monetary amount has been sampled.
MATERIAL_QUANTITY_RANGE = {
    "machined": (5, 200),
    "fastener": (100, 5000),
    "raw_steel": (50, 2000),
    "consumable": (10, 500),
}

# When sampling a monetary amount from a [min, max] band (vendor order value,
# GL account range, ...), inset the sampling range by this fraction so that
# quantity-rounding drift can never push the recomputed amount outside the
# declared band (amount-plausibility rule).
BAND_SAMPLING_MARGIN_FRACTION = 0.08

# VA05 sales price = material purchase price band x markup (no separate
# customer-level price range exists in the master data).
SALES_MARKUP_RANGE = (1.2, 2.0)

DELIVERY_STATUS_OPTIONS = [
    "Vollständig ausgeliefert", "Teillieferung", "Nicht ausgeliefert", "In Bearbeitung",
]

# MB52 stock-quantity bands by column.
MB52_STOCK_QTY_RANGE = {
    "unrestricted": (0, 5000),
    "quality_inspection": (0, 200),
    "blocked": (0, 100),
}

# FBL3N debit/credit mix: expense accounts post mostly Soll (debit).
FBL3N_DEBIT_CREDIT_WEIGHTS = {"S": 0.8, "H": 0.2}

# FBL3N document types and short posting texts (SGTXT-style).
FBL3N_DOCUMENT_TYPES = ["SA", "KR", "RE", "AB"]
FBL3N_DOCUMENT_TYPE_WEIGHTS = [0.5, 0.2, 0.2, 0.1]
FBL3N_TEXT_OPTIONS = [
    "Materialentnahme", "Rechnung Lieferant", "Korrekturbuchung", "Periodenabgrenzung",
    "Wareneingang", "Kostenumlage", "Abschreibung", "Zahlungsausgang",
]

# FBL1N vendor-page composition.
FBL1N_KR_CLEARED_FRACTION = 0.35   # share of KR items fully cleared by a matching KZ
FBL1N_KR_PARTIAL_FRACTION = 0.15   # share of KR items partially cleared (remainder stays open)
# (remaining KR items stay 'open', no KZ)
FBL1N_KA_SHARE = 0.10              # share of a vendor's line items that are KA (not PO-tied)
FBL1N_INVOICE_LAG_DAYS_MAX = 60    # reconciliation lag cap

# ---------------------------------------------------------------------------
# Report titles (German; inferred where no verbatim sample of the SAP
# report title was found)
# ---------------------------------------------------------------------------

REPORT_TITLES = {
    "FBL3N": "Sachkonten Einzelpostenliste",
    "ME2M": "Bestellungen nach Material",
    "VA05": "Liste Verkaufsbelege",
    "FBL1N": "Kreditoren Einzelpostenliste",
    "MB52": "Lagerbestandsübersicht",
}

# ---------------------------------------------------------------------------
# Class plan (pre-registered): explicit, deterministic,
# not sampled. Every doc's class is looked up here so the answer key can
# label every document without ambiguity.
#
# FBL3N: 45 R + 3 V         | V from month 8
# VA05:  40 R + 3 V + 5 F   | V from month 8, F in months 9-12
# ME2M:  42 R + 5 F + 1 S   | F in months 9-12, S in month 11 only
# FBL1N: 43 R + 5 F         | F in months 9-12
# MB52:  48 R               | pure routine
# (S relocated FBL3N -> ME2M in review.)
# ---------------------------------------------------------------------------

_R4 = ["R", "R", "R", "R"]

CLASS_SCHEDULE = {
    "FBL3N": {
        "2025-01": list(_R4), "2025-02": list(_R4), "2025-03": list(_R4),
        "2025-04": list(_R4), "2025-05": list(_R4), "2025-06": list(_R4),
        "2025-07": list(_R4),
        "2025-08": ["R", "R", "R", "V"],
        "2025-09": list(_R4),
        "2025-10": ["R", "R", "R", "V"],
        "2025-11": ["R", "R", "V", "R"],
        "2025-12": list(_R4),
    },
    "ME2M": {
        "2025-01": list(_R4), "2025-02": list(_R4), "2025-03": list(_R4),
        "2025-04": list(_R4), "2025-05": list(_R4), "2025-06": list(_R4),
        "2025-07": list(_R4), "2025-08": list(_R4),
        "2025-09": ["R", "R", "R", "F"],
        "2025-10": ["R", "R", "R", "F"],
        "2025-11": ["R", "S", "F", "F"],
        "2025-12": ["R", "R", "R", "F"],
    },
    "VA05": {
        "2025-01": list(_R4), "2025-02": list(_R4), "2025-03": list(_R4),
        "2025-04": list(_R4), "2025-05": list(_R4), "2025-06": list(_R4),
        "2025-07": list(_R4),
        "2025-08": ["R", "R", "R", "V"],
        "2025-09": ["R", "R", "V", "F"],
        "2025-10": ["R", "R", "V", "F"],
        "2025-11": ["R", "R", "F", "F"],
        "2025-12": ["R", "R", "R", "F"],
    },
    "FBL1N": {
        "2025-01": list(_R4), "2025-02": list(_R4), "2025-03": list(_R4),
        "2025-04": list(_R4), "2025-05": list(_R4), "2025-06": list(_R4),
        "2025-07": list(_R4), "2025-08": list(_R4),
        "2025-09": ["R", "R", "R", "F"],
        "2025-10": ["R", "R", "R", "F"],
        "2025-11": ["R", "R", "F", "F"],
        "2025-12": ["R", "R", "R", "F"],
    },
    "MB52": {m: list(_R4) for m in MONTHS},
}


def class_counts(transaction_type):
    """Tally R/V/F/S counts for a type from CLASS_SCHEDULE (sanity helper,
    used by both the generator's self-check and validate_data.py)."""
    counts = {"R": 0, "V": 0, "F": 0, "S": 0}
    for month_classes in CLASS_SCHEDULE[transaction_type].values():
        for c in month_classes:
            counts[c] += 1
    return counts


# Pre-registered expected counts per type.
EXPECTED_CLASS_COUNTS = {
    "FBL3N": {"R": 45, "V": 3, "F": 0, "S": 0},
    "ME2M": {"R": 42, "V": 0, "F": 5, "S": 1},
    "VA05": {"R": 40, "V": 3, "F": 5, "S": 0},
    "FBL1N": {"R": 43, "V": 0, "F": 5, "S": 0},
    "MB52": {"R": 48, "V": 0, "F": 0, "S": 0},
}

if __name__ == "__main__":
    # Smoke-check: run this module directly to print master-data summary
    # and confirm the class schedule matches the pre-registered counts exactly.
    print(f"Vendors: {len(VENDORS)} (vendor 10040 = {VENDORS_BY_NUMBER['10040']['name']!r})")
    print(f"Materials: {len(MATERIALS)}")
    print(f"Customers: {len(CUSTOMERS)} (incl. {len(VA05_HORROR_CUSTOMER_NAMES)} horror names)")
    print(f"GL accounts: {len(GL_ACCOUNTS)}")
    print(f"SEK vendors: {SEK_VENDOR_NUMBERS}")
    for t in TRANSACTION_TYPES:
        counts = class_counts(t)
        expected = EXPECTED_CLASS_COUNTS[t]
        status = "OK" if counts == expected else "MISMATCH"
        print(f"{t}: {counts} expected {expected} [{status}]")
