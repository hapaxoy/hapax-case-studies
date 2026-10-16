"""Configuration for the invoice-processing corpus generator (Project 3).

Every tunable lives here: RANDOM_SEED, the buyer and supplier identity
blocks, product catalogues, the monthly document matrix, the one-off roster,
planted-event placements, and the template registry. `generate_invoices.py`
reads this module and does not invent identity/matrix data of its own.

BBANs (bank account digit strings) are literal, hardcoded
below so the identity block is plainly visible and diffable; `make_iban` and
`make_rf` compute the check digits from those literals (both pure, seed-free
functions -- no randomness enters identity construction). Y-tunnus values for
suppliers are hardcoded resulting literals (computed once via
`schemas.make_y_tunnus`, pasted in below); the buyer's is computed inline
from its base digits.

TEMPLATE_REGISTRY below records, per template, the format conventions each
layout/vocabulary choice draws on (EU VAT Directive articles, national
formats, layout and header patterns), as section labels of the format
research compiled before the build.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import schemas

RANDOM_SEED = 42

# ---------------------------------------------------------------------------
# Identifier construction helpers (pure, deterministic, no RNG)
# ---------------------------------------------------------------------------

def make_iban(country_code: str, bban: str) -> str:
    """ISO 13616 mod-97 IBAN check-digit construction."""
    rearranged = bban + country_code + "00"
    digits = "".join(str(int(c, 36)) for c in rearranged)
    check = 98 - (int(digits) % 97)
    return f"{country_code}{check:02d}{bban}"


def make_rf(base_digits: str) -> str:
    """ISO 11649 RF creditor reference, same mod-97 algorithm as IBAN."""
    rearranged = base_digits + "RF" + "00"
    digits = "".join(str(int(c, 36)) for c in rearranged)
    check = 98 - (int(digits) % 97)
    return f"RF{check:02d}{base_digits}"


assert schemas.iban_ok(make_iban("FI", "90012345670001"))  # self-check at import time
assert schemas.iban_ok(make_iban("DE", "500999100123456789"))

# ---------------------------------------------------------------------------
# Buyer identity (printed on every document)
# ---------------------------------------------------------------------------

_BUYER_YTUNNUS = schemas.make_y_tunnus("2417551")
assert _BUYER_YTUNNUS is not None and schemas.y_tunnus_ok(_BUYER_YTUNNUS)

BUYER = {
    "name": "Pyökkipaja Oy",
    "street": "Esimerkkikatu 11",
    "postcode": "15520",
    "city": "Lahti",
    "country": "FI",
    "business_id": _BUYER_YTUNNUS,
    "vat_id": "FI" + _BUYER_YTUNNUS.replace("-", ""),
}

# ---------------------------------------------------------------------------
# Product catalogues (goods suppliers only; Decimal price ranges)
# ---------------------------------------------------------------------------
# Each entry: (description, unit, price_min, price_max)

CATALOG_S1 = [  # Salpausselän Puutavara Oy -- board, plywood, timber
    ("Koivuvaneri 15 mm, 1250x2500", "kpl", "38.00", "52.00"),
    ("Koivuvaneri 18 mm, 1250x2500", "kpl", "44.00", "58.00"),
    ("Havuvaneri 12 mm, 1250x2500", "kpl", "26.00", "34.00"),
    ("MDF-levy 16 mm, 2070x2800", "kpl", "48.00", "62.00"),
    ("Lastulevy 22 mm, 2070x2800", "kpl", "22.00", "30.00"),
    ("Höylätty lauta 22x100", "jm", "1.80", "2.60"),
    ("Höylätty lauta 22x125", "jm", "2.10", "2.90"),
    ("Sahatavara 50x100", "jm", "2.40", "3.20"),
    ("Sahatavara 50x150", "jm", "3.10", "4.10"),
    ("Liimapuupalkki 90x225", "jm", "14.00", "19.00"),
    ("Vaneriviilu, koristepinta", "m2", "9.50", "13.50"),
    ("Kovalevy 3.2 mm", "kpl", "6.50", "9.50"),
    ("Reunalista, koivu", "jm", "1.20", "1.80"),
    ("Työlevy, laminoitu", "m2", "16.00", "22.00"),
]

CATALOG_S2 = [  # Päijät-Pakkaus Oy -- packaging
    ("Aaltopahvilaatikko, S", "kpl", "0.65", "0.95"),
    ("Aaltopahvilaatikko, M", "kpl", "0.95", "1.35"),
    ("Aaltopahvilaatikko, L", "kpl", "1.40", "1.95"),
    ("Kuormalava, EUR-lava", "kpl", "9.50", "13.50"),
    ("Kutistekalvo, rulla", "kpl", "18.00", "26.00"),
    ("Pakkausteippi, rulla", "kpl", "1.10", "1.60"),
    ("Suojapehmuste, ilmatyyny, rulla", "kpl", "22.00", "30.00"),
    ("Sidontanauha, muovi, rulla", "kpl", "14.00", "19.00"),
    ("Reunasuoja, pahvi", "kpl", "0.30", "0.45"),
    ("Kuormalavan kulmasuoja", "kpl", "0.55", "0.80"),
    ("Hylsykartonki", "kpl", "3.20", "4.50"),
]
# The S-document line (planted event, see EVENT_TABLE / generate_invoices.py):
# a crate hinge -- packaging hardware for reusable wooden shipping crates,
# plausible both at ~EUR 50/unit (a heavy hinge set) and ~EUR 2/unit (a small
# one), which is exactly the ambiguity the S event needs on its face.
S_EVENT_LINE_DESCRIPTION = "Laatikon sarana, kuljetuslaatikkoon"
S_EVENT_LINE_UNIT = "kpl"

CATALOG_S3 = [  # Falkenrath Beschläge GmbH -- fittings, slides, hinges
    ("Möbelscharnier, verdeckt", "ST", "3.20", "4.80"),
    ("Vollauszug 500mm", "ST", "12.50", "17.50"),
    ("Teilauszug 400mm", "ST", "8.00", "11.00"),
    ("Türdämpfer", "ST", "2.10", "3.10"),
    ("Griffleiste Aluminium", "ST", "6.50", "9.50"),
    ("Schubkastensystem", "ST", "24.00", "34.00"),
    ("Regalbodenträger", "ST", "0.80", "1.20"),
    ("Möbelfuß, höhenverstellbar", "ST", "2.60", "3.80"),
    ("Klappenhalter", "ST", "9.00", "13.00"),
    ("Exzenterverbinder", "ST", "0.45", "0.70"),
    ("Scharnierbohrschablone", "ST", "45.00", "60.00"),
    ("Schrankaufhänger", "ST", "4.20", "6.20"),
]

CATALOG_S4 = [  # Möbeltyg Viskan AB -- upholstery fabric (SEK)
    # 14 items (>= OVERFLOW_LINE_THRESHOLD=12, within the designed 12-25 items):
    # fix 5 requires sampling without replacement and capping at catalogue size,
    # and the F4 planted event forces exactly 12 lines
    # for one s4 document, so the catalogue must offer at least 12 unique items.
    ("Möbeltyg, ylle, standard", "m", "180", "260"),
    ("Möbeltyg, bomull", "m", "120", "180"),
    ("Möbeltyg, konstläder", "m", "220", "320"),
    ("Möbeltyg, flamskyddat kontor", "m", "260", "360"),
    ("Stoppningsfilt", "m", "45", "70"),
    ("Kantband, tyg", "m", "8", "14"),
    ("Möbeltyg, mönstrat", "m", "200", "300"),
    ("Dragkedja, möbel", "st", "12", "20"),
    ("Möbeltyg, linne", "m", "190", "280"),
    ("Möbeltyg, sammet", "m", "240", "340"),
    ("Skumgummi, stoppning", "m", "60", "90"),
    ("Klädsel, konstskinn premium", "m", "260", "380"),
    ("Sytråd, industri, rulle", "st", "15", "25"),
    ("Möbeltyg, utomhus", "m", "210", "300"),
]

CATALOG_S5 = [  # Plekivalu OÜ -- steel legs, frames (EN labels)
    ("Steel table leg, adjustable", "pcs", "14.00", "19.00"),
    ("Steel table leg, fixed", "pcs", "9.00", "13.00"),
    ("Steel frame, chair base", "pcs", "22.00", "30.00"),
    ("Steel bracket, wall-mount", "pcs", "4.50", "6.50"),
    ("Steel castor set", "pcs", "11.00", "15.00"),
    ("Steel corner reinforcement", "pcs", "2.80", "4.00"),
    ("Powder-coated frame, large", "pcs", "38.00", "52.00"),
    ("Steel tube section 40x40", "pcs", "6.00", "8.50"),
]

CATALOG_S8 = [  # Työkalu-Tiira Oy -- tools, consumables (MRO)
    ("Poranterä, HSS 8mm", "kpl", "3.50", "5.50"),
    ("Poranterä, HSS 10mm", "kpl", "4.50", "6.50"),
    ("Katkaisulaikka 125mm", "kpl", "1.80", "2.60"),
    ("Hiomapaperi P120, arkki", "kpl", "0.40", "0.60"),
    ("Työkäsineet, pari", "kpl", "3.20", "4.80"),
    ("Kuulokesuojain", "kpl", "14.00", "19.00"),
    ("Ruuvipuristin 150mm", "kpl", "16.00", "22.00"),
    ("Vasara 500g", "kpl", "12.00", "16.00"),
    ("Mittanauha 5m", "kpl", "6.50", "9.00"),
    ("Suojalasit", "kpl", "4.00", "6.00"),
    ("Teollisuusliima, tuubi", "kpl", "5.50", "7.50"),
    ("Työvalo, LED", "kpl", "22.00", "30.00"),
]

CATALOG_BRANDT = [  # Ersatzteile Brandt GmbH -- spare parts (one-off, DE)
    ("Ersatzmotor, Klein", "ST", "180.00", "260.00"),
    ("Antriebsriemen", "ST", "18.00", "28.00"),
    ("Lagerbuchse", "ST", "6.00", "9.00"),
    ("Steuerplatine", "ST", "220.00", "340.00"),
]

# S6 freight and S7 canteen are service invoices, described directly per
# document in generate_invoices.py (no per-item catalogue needed).

# ---------------------------------------------------------------------------
# Repeat suppliers (s1..s8)
# ---------------------------------------------------------------------------

SUPPLIERS = {
    "s1": {
        "id": "s1", "name": "Salpausselän Puutavara Oy", "country": "FI",
        "street": "Esimerkkikatu 4", "postcode": "15150", "city": "Lahti",
        "business_id": "9811228-8", "vat_id": "FI98112288",
        "iban": make_iban("FI", "95783022011184"), "bic": "KALTFIHH",
        "currency": "EUR", "terms_days": 30, "reference_type": "viitenumero",
        "language": "fi", "locale": "fi", "vat_rate": "25.5",
        "reverse_charge_mention": None, "font_family": "Arial, Helvetica, sans-serif",
        "is_goods": True, "catalog": CATALOG_S1,
        "amount_range": ("500", "6000"),
        "invoice_format": lambda n: f"Lasku 2025-{n:04d}", "invoice_start": 1842,
        "template": "s1",
    },
    "s2": {
        "id": "s2", "name": "Päijät-Pakkaus Oy", "country": "FI",
        "street": "Esimerkkikatu 8", "postcode": "15870", "city": "Hollola",
        "business_id": "9811229-6", "vat_id": "FI98112296",
        "iban": make_iban("FI", "46687211170035"), "bic": "SUVAFIHH",
        "currency": "EUR", "terms_days": 21, "reference_type": "viitenumero",
        "language": "fi", "locale": "fi_compact", "vat_rate": "25.5",
        "reverse_charge_mention": None, "font_family": "'Courier New', Courier, monospace",
        "is_goods": True, "catalog": CATALOG_S2,
        "amount_range": ("300", "2500"),
        "invoice_format": lambda n: f"{n:05d}", "invoice_start": 30512,
        "template": "s2",
    },
    "s3": {
        "id": "s3", "name": "Falkenrath Beschläge GmbH", "country": "DE",
        "street": "Beispielstraße 22", "postcode": "42285", "city": "Wuppertal",
        "business_id": "HRB 24187", "registration_suffix": ", Amtsgericht Beispielstadt",
        "vat_id": "DE187654321",
        "iban": make_iban("DE", "500999100123456789"), "bic": "RHHADEFF",
        "currency": "EUR", "terms_days": 30, "reference_type": None,
        "language": "de", "locale": "de", "vat_rate": "0.0",
        "reverse_charge_mention": "Steuerfreie innergemeinschaftliche Lieferung",
        "font_family": "Georgia, 'Times New Roman', serif",
        "is_goods": True, "catalog": CATALOG_S3,
        "amount_range": ("800", "7000"),
        "invoice_format": lambda n: f"RE-2025-{n:04d}", "invoice_start": 3011,
        "template": "s3",
    },
    "s4": {
        "id": "s4", "name": "Möbeltyg Viskan AB", "country": "SE",
        "street": "Exempelgatan 14", "postcode": "504 62", "city": "Borås",
        "business_id": "556123-4567", "vat_id": "SE556123456701",
        "iban": None, "bic": None, "bankgiro": "5123-4567",
        "currency": "SEK", "terms_days": 30, "reference_type": "ocr",
        "language": "sv", "locale": "sv", "vat_rate": "0.0",
        "reverse_charge_mention": "Undantag från skatteplikt – unionsintern leverans (Intra-EU supply, Art. 138)",
        "font_family": "Tahoma, Geneva, sans-serif",
        "is_goods": True, "catalog": CATALOG_S4,
        "amount_range": ("5000", "40000"),
        "invoice_format": lambda n: f"F{n:05d}", "invoice_start": 8420,
        "template": "s4",
    },
    "s5": {
        "id": "s5", "name": "Plekivalu OÜ", "country": "EE",
        "street": "Näite tn 9", "postcode": "11415", "city": "Tallinn",
        "business_id": "12457896", "vat_id": "EE100786532",
        "iban": make_iban("EE", "7300221054450012"), "bic": "KULDEE22",
        "currency": "EUR", "terms_days": 14, "reference_type": "rf",
        "language": "en", "locale": "en", "vat_rate": "0.0",
        "reverse_charge_mention": "Reverse charge (Article 196, Council Directive 2006/112/EC)",
        "font_family": "'Trebuchet MS', Verdana, sans-serif",
        "is_goods": True, "catalog": CATALOG_S5,
        "amount_range": ("600", "5000"),
        "invoice_format": lambda n: f"A25-{n:03d}", "invoice_start": 214,
        "template": "s5",
    },
    "s6": {
        "id": "s6", "name": "Vesijärven Rahtilinja Oy", "country": "FI",
        "street": "Esimerkkikatu 6", "postcode": "15140", "city": "Lahti",
        "business_id": "9811220-2", "vat_id": "FI98112202",
        "iban": make_iban("FI", "48101470683126"), "bic": "HARMFIHH",
        "currency": "EUR", "terms_days": 14, "reference_type": "viitenumero",
        "language": "fi", "locale": "fi", "vat_rate": "25.5",
        "reverse_charge_mention": None, "font_family": "Verdana, Geneva, sans-serif",
        "is_goods": False, "catalog": None,
        "amount_range": ("180", "900"),
        "invoice_format": lambda n: f"2025{n:05d}", "invoice_start": 41230,
        "template": "s6",
    },
    "s7": {
        "id": "s7", "name": "Lounastupa Helmi Oy", "country": "FI",
        "street": "Esimerkkikatu 12", "postcode": "15110", "city": "Lahti",
        "business_id": "9811230-9", "vat_id": "FI98112309",
        "iban": make_iban("FI", "46600941077314"), "bic": "SUVAFIHH",
        "currency": "EUR", "terms_days": 14, "reference_type": "viitenumero",
        "language": "fi", "locale": "fi", "vat_rate": "14.0",
        "reverse_charge_mention": None, "font_family": "Arial, Helvetica, sans-serif",
        "is_goods": False, "catalog": None,
        "amount_range": ("480", "780"),
        "invoice_format": lambda n: f"{n:04d}", "invoice_start": 512,
        "template": "s7",
    },
    "s8": {
        "id": "s8", "name": "Työkalu-Tiira Oy", "country": "FI",
        "street": "Esimerkkikatu 19", "postcode": "15170", "city": "Lahti",
        "business_id": "9811231-7", "vat_id": "FI98112317",
        "iban": make_iban("FI", "92791800130472"), "bic": "KALTFIHH",
        "currency": "EUR", "terms_days": 30, "reference_type": "viitenumero",
        "language": "fi", "locale": "fi", "vat_rate": "25.5",
        "reverse_charge_mention": None,
        "font_family": "Arial Narrow, Arial, sans-serif",  # v1; v2 overridden below
        "is_goods": True, "catalog": CATALOG_S8,
        "amount_range": ("150", "1800"),
        "invoice_format": lambda n: f"T-{n:04d}", "invoice_start": 118,
        "template": "s8_v1",
        # -- redesign (event T): documents dated >= T_CUTOVER_DATE use v2 --
        "v2_font_family": "'Century Gothic', Verdana, sans-serif",
        "v2_invoice_format": lambda n: f"2025-{n:04d}", "v2_invoice_start": 1,
        "v2_template": "s8_v2",
    },
}

T_CUTOVER_DATE = date(2025, 8, 1)

# Finnish public holidays 2025 (fix 6) -- excluded from every supplier's
# business-day pool; no document may be issued on one of these dates.
HOLIDAYS_2025 = {
    date(2025, 1, 1),   # Uudenvuodenpäivä
    date(2025, 1, 6),   # Loppiainen
    date(2025, 4, 18),  # Pitkäperjantai
    date(2025, 4, 21),  # 2. pääsiäispäivä
    date(2025, 5, 1),   # Vappu
    date(2025, 5, 29),  # Helatorstai
    date(2025, 6, 20),  # Juhannusaatto
    date(2025, 12, 6),  # Itsenäisyyspäivä
    date(2025, 12, 24), # Jouluaatto
    date(2025, 12, 25), # Joulupäivä
    date(2025, 12, 26), # Tapaninpäivä
    date(2025, 12, 31), # Uudenvuodenaatto
}

# ---------------------------------------------------------------------------
# Monthly document matrix -- rows sum to 178
# ---------------------------------------------------------------------------
# index 0 = January .. 11 = December

MONTHLY_MATRIX = {
    "s1": [3, 3, 3, 3, 3, 3, 2, 2, 2, 3, 2, 3],
    "s2": [3, 2, 2, 2, 2, 2, 2, 2, 2, 2, 3, 2],
    "s3": [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2],
    "s4": [2, 2, 2, 2, 1, 2, 1, 2, 2, 2, 1, 1],
    "s5": [2, 2, 2, 2, 1, 2, 1, 2, 1, 2, 1, 2],
    "s6": [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 1, 3],
    "s7": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
    "s8": [2, 2, 2, 2, 1, 2, 1, 2, 2, 2, 1, 1],
}
assert {sid: sum(v) for sid, v in MONTHLY_MATRIX.items()} == {
    "s1": 32, "s2": 26, "s3": 24, "s4": 20, "s5": 20, "s6": 24, "s7": 12, "s8": 20,
}
REPEAT_SUPPLIER_ORDER = ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8"]

# ---------------------------------------------------------------------------
# One-off suppliers (18 suppliers, 20 documents)
# ---------------------------------------------------------------------------
# month is 1-based. net_range in the invoice's own currency (EUR unless noted).
# reverse_charge is None for domestic-rate documents, else the printed mention.

ONE_OFFS = [
    {"key": "kalibrointi_aho", "month": 1, "name": "Kalibrointi Aho Oy",
     "country": "FI", "street": "Esimerkkikatu 3", "postcode": "15230", "city": "Lahti",
     "business_id": "9811221-0", "vat_id": "FI98112210", "vat_rate": "25.5",
     "reverse_charge_mention": None, "currency": "EUR", "net_range": ("300", "900"),
     "service_lines": [("Mittalaitteen kalibrointi", "kpl"), ("Kalibrointitodistus", "kpl")],
     "po_eligible": False, "toiminimi": False, "number_format": "fi"},
    {"key": "painotalo_vesala", "month": 1, "name": "Painotalo Vesala Oy",
     "country": "FI", "street": "Esimerkkikatu 7", "postcode": "40320", "city": "Jyväskylä",
     "business_id": "9811232-5", "vat_id": "FI98112325", "vat_rate": "25.5",
     "reverse_charge_mention": None, "currency": "EUR", "net_range": ("600", "2200"),
     "service_lines": [("Tuotekatalogi, painotyö", "kpl"), ("Taitto ja esivalmistelu", "kpl")],
     "po_eligible": False, "toiminimi": False, "number_format": "fi"},
    {"key": "kuriiripalvelu_nopsa", "month": 2, "name": "Kuriiripalvelu Nopsa Oy",
     "country": "FI", "street": "Esimerkkikatu 2", "postcode": "00880", "city": "Helsinki",
     "business_id": "9811233-3", "vat_id": "FI98112333", "vat_rate": "25.5",
     "reverse_charge_mention": None, "currency": "EUR", "net_range": ("150", "450"),
     "service_lines": [("Pikakuljetus, Lahti-Helsinki", "kpl"), ("Nouto ja toimitus", "kpl")],
     "po_eligible": False, "toiminimi": False, "number_format": "fi"},
    {"key": "kaannostoimisto_lind", "month": 2, "name": "Käännöstoimisto Lind & Co",
     "country": "FI", "street": "Esimerkkikatu 5", "postcode": "33100", "city": "Tampere",
     "business_id": "9811222-9", "vat_id": "FI98112229", "vat_rate": "25.5",
     "reverse_charge_mention": None, "currency": "EUR", "net_range": ("250", "800"),
     "service_lines": [("Tekninen käännös, EN-FI", "sivu"), ("Oikoluku", "sivu")],
     "po_eligible": False, "toiminimi": False, "number_format": "fi"},
    {"key": "konehuolto_alisalo", "month": 3, "name": "Konehuolto Alisalo Oy",
     "country": "FI", "street": "Esimerkkikatu 11", "postcode": "15200", "city": "Lahti",
     "business_id": "9811234-1", "vat_id": "FI98112341", "vat_rate": "25.5",
     "reverse_charge_mention": None, "currency": "EUR", "net_range": ("400", "1200"),
     "service_lines": [("Reunalistakoneen huoltokäynti", "h"), ("Varaosat, huolto", "kpl")],
     "po_eligible": False, "toiminimi": False, "number_format": "fi"},
    {"key": "kustannus_hoyla", "month": 3, "name": "Kustannus Höylä Oy",
     "country": "FI", "street": "Esimerkkikatu 9", "postcode": "00100", "city": "Helsinki",
     "business_id": "9811223-7", "vat_id": "FI98112237", "vat_rate": "10.0",
     "reverse_charge_mention": None, "currency": "EUR", "net_range": ("90", "250"),
     "service_lines": [("Puuteollisuus-ammattilehti, vuosikerta", "kk")],
     "po_eligible": False, "toiminimi": False, "number_format": "fi"},
    {"key": "sahkoasennus_rautio", "month": 4, "name": "Sähköasennus Rautio Oy",
     "country": "FI", "street": "Esimerkkikatu 4", "postcode": "15140", "city": "Lahti",
     "business_id": "9811224-5", "vat_id": "FI98112245", "vat_rate": "25.5",
     "reverse_charge_mention": None, "currency": "EUR", "net_range": ("500", "1800"),
     "service_lines": [("Sähköasennustyö, tuotantotila", "h"), ("Asennustarvikkeet", "kpl")],
     "po_eligible": False, "toiminimi": False, "number_format": "fi"},
    {"key": "messurakenne_nyman", "month": 5, "name": "Messurakenne Nyman Oy",
     "country": "FI", "street": "Esimerkkikatu 14", "postcode": "33900", "city": "Tampere",
     "business_id": "9811236-8", "vat_id": "FI98112368", "vat_rate": "25.5",
     "reverse_charge_mention": None, "currency": "EUR", "net_range": ("2500", "4500"),
     "service_lines": [("Messuosaston suunnittelu ja rakennus", "erä"), ("Kuljetus ja pystytys", "erä")],
     "po_eligible": False, "toiminimi": False, "number_format": "fi"},
    {"key": "ersatzteile_brandt", "month": 5, "name": "Ersatzteile Brandt GmbH",
     "country": "DE", "street": "Beispielstraße 8", "postcode": "33602", "city": "Bielefeld",
     "business_id": "HRB 19442", "registration_suffix": ", Amtsgericht Musterhausen",
     "vat_id": "DE281937465",
     "vat_rate": "0.0",
     "reverse_charge_mention": "Steuerfreie innergemeinschaftliche Lieferung",
     "currency": "EUR", "net_range": ("600", "2000"),
     "service_lines": None, "catalog": CATALOG_BRANDT,
     "po_eligible": True, "toiminimi": False, "number_format": "de"},
    {"key": "hotelli_ilvesranta", "month": 6, "name": "Hotelli Ilvesranta Oy",
     "country": "FI", "street": "Esimerkkikatu 22", "postcode": "15100", "city": "Lahti",
     "business_id": "9811225-3", "vat_id": "FI98112253", "vat_rate": "14.0",
     "reverse_charge_mention": None, "currency": "EUR", "net_range": ("90", "300"),
     # fix 9: two fixed nights at a per-night rate (built directly in
     # generate_invoices.py's build_oneoff_document, not via the generic
     # target-net service-line scaler); service_lines kept here for
     # documentation only and is not read for this supplier.
     "service_lines": [("Majoitus, myyntimatka", "vrk")],
     "po_eligible": False, "toiminimi": False, "number_format": "fi"},
    {"key": "asianajotoimisto_ketomaki", "month": 7, "name": "Asianajotoimisto Keto & Mäki Oy",
     "country": "FI", "street": "Esimerkkikatu 3", "postcode": "00170", "city": "Helsinki",
     "business_id": "9811237-6", "vat_id": "FI98112376", "vat_rate": "25.5",
     "reverse_charge_mention": None, "currency": "EUR", "net_range": ("800", "2500"),
     "service_lines": [("Sopimuskatselmus, toimitussopimus", "h"), ("Neuvottelu, asiakastapaaminen", "h")],
     "po_eligible": False, "toiminimi": False, "number_format": "fi"},
    {"key": "ashquill_software", "month": 7, "name": "Ashquill Software Ltd",
     "name_fallback": "Loughware Ltd",
     "country": "IE", "street": "14 Example Street", "postcode": "D02 X000", "city": "Dublin",
     "business_id": "Company no. 999214", "vat_id": "IE6423178H", "vat_rate": "0.0",
     "reverse_charge_mention": "Reverse charge (Article 196, Council Directive 2006/112/EC)",
     "currency": "EUR", "net_range": ("1200", "3500"),
     "service_lines": [("CAD plugin licence, annual seat", "licence")],
     # fix 10: "en_ie" is the English vocabulary with Irish DD/MM/YYYY dates
     # (distinct from s5/Tõlkebüroo Laine's plain "en", which keeps DD.MM.YYYY)
     "po_eligible": False, "toiminimi": False, "number_format": "en_ie"},
    {"key": "teroituspalvelu_karhinen", "month": 8, "name": "Teroituspalvelu Karhinen",
     "country": "FI", "street": "Esimerkkikatu 6", "postcode": "15230", "city": "Lahti",
     "business_id": "9811238-4", "vat_id": "FI98112384", "vat_rate": "25.5",
     "reverse_charge_mention": None, "currency": "EUR", "net_range": ("120", "400"),
     "service_lines": [("Terien teroitus, sarja", "erä")],
     "po_eligible": False, "toiminimi": True, "number_format": "fi"},
    {"key": "kuriiripalvelu_nopsa_2", "month": 9, "name": "Kuriiripalvelu Nopsa Oy",
     "same_supplier_as": "kuriiripalvelu_nopsa",
     "country": "FI", "street": "Esimerkkikatu 2", "postcode": "00880", "city": "Helsinki",
     "business_id": "9811233-3", "vat_id": "FI98112333", "vat_rate": "25.5",
     "reverse_charge_mention": None, "currency": "EUR", "net_range": ("150", "450"),
     "service_lines": [("Pikakuljetus, Lahti-Helsinki", "kpl"), ("Nouto ja toimitus", "kpl")],
     "po_eligible": False, "toiminimi": False, "number_format": "fi"},
    {"key": "frakt_nordkap", "month": 9, "name": "Frakt Nordkap AB",
     "country": "SE", "street": "Exempelgatan 3", "postcode": "411 04", "city": "Göteborg",
     "business_id": "556789-1234", "vat_id": "SE556789123401", "vat_rate": "0.0",
     "reverse_charge_mention": "Omvänd betalningsskyldighet – Reverse charge (Artikel 196)",
     "currency": "EUR",  # rule 7: SEK is s4-only
     "net_range": ("300", "900"),
     "service_lines": [("Fraktuppdrag, engångstransport", "st")],
     "po_eligible": False, "toiminimi": False, "number_format": "sv"},
    {"key": "konehuolto_alisalo_2", "month": 10, "name": "Konehuolto Alisalo Oy",
     "same_supplier_as": "konehuolto_alisalo",
     "country": "FI", "street": "Esimerkkikatu 11", "postcode": "15200", "city": "Lahti",
     "business_id": "9811234-1", "vat_id": "FI98112341", "vat_rate": "25.5",
     "reverse_charge_mention": None, "currency": "EUR", "net_range": ("400", "1200"),
     "service_lines": [("Karan korjaus, reunalistakone", "h"), ("Varaosat, korjaus", "kpl")],
     "po_eligible": False, "toiminimi": False, "number_format": "fi"},
    {"key": "jatehuolto_routasuo", "month": 11, "name": "Jätehuolto Routasuo Oy",
     "country": "FI", "street": "Esimerkkikatu 18", "postcode": "15230", "city": "Lahti",
     "business_id": "9811239-2", "vat_id": "FI98112392", "vat_rate": "25.5",
     "reverse_charge_mention": None, "currency": "EUR", "net_range": ("200", "700"),
     "service_lines": [("Jätelavan vuokraus ja tyhjennys", "kpl"), ("Kuljetusmaksu", "kpl")],
     "po_eligible": False, "toiminimi": False, "number_format": "fi"},
    {"key": "tolkeburoo_laine", "month": 11, "name": "Tõlkebüroo Laine OÜ",
     "country": "EE", "street": "Näite tn 4", "postcode": "10111", "city": "Tallinn",
     "business_id": "14257689", "vat_id": "EE100457821", "vat_rate": "0.0",
     "reverse_charge_mention": "Käibemaksu pöördmaksustamine – Reverse charge (Article 196)",
     "currency": "EUR", "net_range": ("300", "900"),
     "service_lines": [("Manual translation, technical, EN-FI", "page")],
     "po_eligible": False, "toiminimi": False, "number_format": "en"},
    {"key": "henkilostopalvelu_kiertola", "month": 12, "name": "Henkilöstöpalvelu Kiertola Oy",
     "country": "FI", "street": "Esimerkkikatu 2", "postcode": "15140", "city": "Lahti",
     "business_id": "9811226-1", "vat_id": "FI98112261", "vat_rate": "25.5",
     "reverse_charge_mention": None, "currency": "EUR", "net_range": ("2000", "4500"),
     "service_lines": [("Vuokratyövoima, joulusesonki", "h"), ("Rekrytointi- ja välityspalkkio", "erä")],
     "po_eligible": False, "toiminimi": False, "number_format": "fi"},
    {"key": "pitopalvelu_sinikello", "month": 12, "name": "Pitopalvelu Sinikello Oy",
     "country": "FI", "street": "Esimerkkikatu 5", "postcode": "15200", "city": "Lahti",
     "business_id": "9811240-5", "vat_id": "FI98112405", "vat_rate": "14.0",
     "reverse_charge_mention": None, "currency": "EUR", "net_range": ("90", "350"),
     "service_lines": [("Pikkujoulutarjoilu, henkilömäärän mukaan", "hlö")],
     "po_eligible": False, "toiminimi": False, "number_format": "fi"},
]
assert len(ONE_OFFS) == 20
_ONEOFF_MONTH_COUNTS = [0] * 12
for _o in ONE_OFFS:
    _ONEOFF_MONTH_COUNTS[_o["month"] - 1] += 1
assert _ONEOFF_MONTH_COUNTS == [2, 2, 2, 1, 2, 1, 2, 1, 2, 1, 2, 2], _ONEOFF_MONTH_COUNTS

# One-off IBAN/BIC master (literal BBANs; make_iban computes check digits)
ONE_OFF_BANK = {
    "kalibrointi_aho": (make_iban("FI", "90403500318264"), "KALTFIHH"),
    "painotalo_vesala": (make_iban("FI", "46635621908417"), "SUVAFIHH"),
    "kuriiripalvelu_nopsa": (make_iban("FI", "48163900217859"), "HARMFIHH"),
    "kaannostoimisto_lind": (make_iban("FI", "90661800459321"), "KALTFIHH"),
    "konehuolto_alisalo": (make_iban("FI", "46631700284069"), "SUVAFIHH"),
    "kustannus_hoyla": (make_iban("FI", "93723100850647"), "KALTFIHH"),
    "sahkoasennus_rautio": (make_iban("FI", "48103600574112"), "HARMFIHH"),
    "messurakenne_nyman": (make_iban("FI", "46650700163928"), "SUVAFIHH"),
    "ersatzteile_brandt": (make_iban("DE", "370999200532013000"), "NWRKDEFF"),
    "hotelli_ilvesranta": (make_iban("FI", "96893200741205"), "KALTFIHH"),
    "asianajotoimisto_ketomaki": (make_iban("FI", "46624800690153"), "SUVAFIHH"),
    "ashquill_software": (make_iban("IE", "SLNY99021712345678"), "SLNYIE2D"),
    "teroituspalvelu_karhinen": (make_iban("FI", "48151400328596"), "HARMFIHH"),
    "frakt_nordkap": (make_iban("SE", "77000000058398257466"), "MLVKSESS"),
    "jatehuolto_routasuo": (make_iban("FI", "93368100517483"), "KALTFIHH"),
    "tolkeburoo_laine": (make_iban("EE", "7300221054450099"), "KULDEE22"),
    "henkilostopalvelu_kiertola": (make_iban("FI", "46696300872641"), "SUVAFIHH"),
    "pitopalvelu_sinikello": (make_iban("FI", "91540200693758"), "KALTFIHH"),
}
# the two suppliers who invoice twice reuse their own bank identity
ONE_OFF_BANK["kuriiripalvelu_nopsa_2"] = ONE_OFF_BANK["kuriiripalvelu_nopsa"]
ONE_OFF_BANK["konehuolto_alisalo_2"] = ONE_OFF_BANK["konehuolto_alisalo"]

# ---------------------------------------------------------------------------
# Planted-event placements
# ---------------------------------------------------------------------------
# (supplier_id, month, local_seq_within_month) -> event code.
# local_seq is 1-based position among that supplier's documents THAT MONTH.

EVENT_TABLE: dict[tuple[str, int, int], str] = {
    ("s6", 9, 2): "F1",   # fuel-surcharge line, no product code
    ("s3", 10, 2): "F2",  # Gutschrift (credit note), references Sept invoice
    ("s1", 11, 2): "F3",  # hyvityslasku (credit note), references Oct delivery
    ("s4", 12, 1): "F4",  # two-page overflow + Leveransvillkor block
    ("s2", 11, 3): "S",   # transposed quantity/unit price
}

# Discovery-timing check (validator rule 4): each supplier's 6th document
# (cumulative count across the year) must land in the stated month.
DISCOVERY_MONTH = {
    "s1": 2, "s2": 3, "s3": 3, "s4": 3, "s5": 3, "s6": 3, "s7": 6, "s8": 3,
}

# Line-count overflow threshold: goods invoices with this many lines are
# long enough that the table + totals naturally spill to page 2 (spike-
# verified against the shared header/meta/totals block sizing used by every
# template).
OVERFLOW_LINE_THRESHOLD = 12

# Expected class counts (validator rule 3)
EXPECTED_CLASS_COUNTS = {"R": 165, "O": 20, "T": 8, "F": 4, "S": 1}

# ---------------------------------------------------------------------------
# Template registry -- validator rule 10: every template must be registered
# with the format features it draws from. The section labels below refer to
# the case's internal format notes, which are not published.
# ---------------------------------------------------------------------------

TEMPLATE_REGISTRY: dict[str, list[str]] = {
    "s1": ["§2 Finnish specifics", "§5 L1", "§5 L2", "§5 L3", "§5 L4", "§5 L5",
           "§5 L6", "§6 H2", "§6 H3", "§6 H7"],
    "s2": ["§2 Finnish specifics", "§5 L3", "§5 L5", "§6 H2 (unspaced variant)",
           "§6 H6", "§6 H7"],
    "s3": ["§1 Art. 226", "§1 Art. 138", "§4 Germany", "§5 L1", "§5 L4",
           "§5 L6", "§6 H2", "§6 H3", "§6 H9 (Gutschrift)"],
    "s4": ["§1 Art. 230", "§4 Sweden", "§5 L7", "§6 H2", "§6 H3", "§6 H8",
           "§6 H10 (Leveransvillkor block)"],
    "s5": ["§1 Art. 226(11a)", "§2 RF reference", "§4 Estonia", "§5 L1",
           "§5 L4", "§6 H1", "§6 H7"],
    "s6": ["§2 Finnish specifics", "§5 L3", "§6 H10 (fuel surcharge, F1)"],
    "s7": ["§2 Finnish specifics", "§5 L5 (minimal)"],
    "s8_v1": ["§2 Finnish specifics", "§5 L1", "§5 L6"],
    "s8_v2": ["§2 Finnish specifics", "§5 L1 (redesigned band layout)",
              "§5 L3 (Nimikekoodi column)", "§5 L5 (totals moved left)"],
    "oneoff_fi_a": ["§2 Finnish specifics", "§5 L1", "§5 L5"],
    "oneoff_fi_b": ["§2 Finnish specifics", "§5 L2", "§5 L5"],
    "oneoff_de": ["§1 Art. 226", "§4 Germany", "§5 L1"],
    "oneoff_sv": ["§4 Sweden", "§5 L1", "§6 H2", "§6 H3"],
    "oneoff_en": ["§1 Art. 226(11a)", "§4 Estonia", "§5 L1", "§6 H1"],
}

# One-off suppliers are assigned one of 5 templates deterministically by
# locale; FI one-offs (14 of the 18) alternate between two FI templates for
# visual variety, split by their fixed roster position (even/odd index).

def oneoff_template_for(entry: dict, index_in_roster: int) -> str:
    lang = entry["number_format"]  # reuses the same locale code as formatting
    if lang == "de":
        return "oneoff_de"
    if lang == "sv":
        return "oneoff_sv"
    if lang in ("en", "en_ie"):
        return "oneoff_en"
    return "oneoff_fi_a" if index_in_roster % 2 == 0 else "oneoff_fi_b"
