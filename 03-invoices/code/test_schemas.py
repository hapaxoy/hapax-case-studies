"""Sanity tests for schemas.py — check-digit algorithms, record validation, comparison.

Run from anywhere: python code/test_schemas.py  (exit 1 on any failure).
First run 3 Jul 2026 (21/21 PASS); kept in the tree as a regression suite.
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import schemas as S  # noqa: E402

fails = []


def check(name, cond):
    print(("OK  " if cond else "FAIL") + " " + name, flush=True)
    if not cond:
        fails.append(name)


check("iban FI21 example valid", S.iban_ok("FI79 9234 5600 0007 85"))
check("iban corrupted invalid", not S.iban_ok("FI21 1234 5600 0007 86"))
check("iban DE example valid", S.iban_ok("DE64 3709 9920 0532 0130 00"))

v = S.make_viitenumero("10432")
check(f"viitenumero round-trip ({v})", S.viitenumero_ok(v))
check("viitenumero tamper fails", not S.viitenumero_ok(v[:-1] + str((int(v[-1]) + 1) % 10)))

o = S.make_ocr("7654321")
check(f"ocr round-trip ({o})", S.ocr_ok(o))
check("ocr tamper fails", not S.ocr_ok(o[:-1] + str((int(o[-1]) + 1) % 10)))
check("ocr canonical luhn valid", S.ocr_ok("79927398713"))

made = [S.make_y_tunnus(f"{n:07d}") for n in (1234567, 2045667, 156)]
made_ok = [m for m in made if m]
check(f"y-tunnus round-trips ({', '.join(made_ok)})", all(S.y_tunnus_ok(m) for m in made_ok))
check("y-tunnus tamper fails", not S.y_tunnus_ok("1234567-0") or not S.y_tunnus_ok("1234567-1"))

check("FI vat", S.vat_id_ok("FI12345678", "FI"))
check("SE vat", S.vat_id_ok("SE556677123401", "SE"))
check("SE vat bad suffix", not S.vat_id_ok("SE556677123402", "SE"))
check("IE vat", S.vat_id_ok("IE1234567T", "IE"))

rec = {
    "supplier": {"name": "Testi Oy", "street": "Katu 1", "postcode": "15100", "city": "Lahti",
                 "country": "FI", "vat_id": "FI12345678", "business_id": made_ok[0]},
    "buyer": {"name": "Pyokkipaja Oy", "street": "Tie 2", "postcode": "15520", "city": "Lahti",
              "country": "FI", "vat_id": None, "business_id": None},
    "invoice": {"number": "2025-1001", "type": "invoice", "issue_date": "2025-03-15",
                "supply_date": None, "due_date": "2025-04-14", "payment_terms": "30 pv netto",
                "currency": "EUR", "po_number": "PO-2025-071",
                "reference_type": "viitenumero", "reference_value": v,
                "original_invoice_number": None, "reverse_charge_mention": None},
    "bank": {"iban": "FI79 9234 5600 0007 85", "bic": "KALTFIHH", "bankgiro": None},
    "lines": [
        {"description": "Koivuvaneri 12 mm", "quantity": "24", "unit": "kpl",
         "unit_price": "38.50", "vat_rate": "25.5", "line_total": "924.00"},
        {"description": "Rahti", "quantity": "1", "unit": "era",
         "unit_price": "85.00", "vat_rate": "25.5", "line_total": "85.00"},
    ],
    "vat_summary": [{"rate": "25.5", "base": "1009.00", "amount": "257.30"}],
    "totals": {"net": "1009.00", "vat": "257.30", "gross": "1266.30"},
}
errs = S.validate_record(rec)
check("valid record passes", errs == [])
if errs:
    print("   " + "\n   ".join(errs), flush=True)

bad = copy.deepcopy(rec)
bad["totals"]["gross"] = "1266.31"
check("broken gross caught", any("gross" in e for e in S.validate_record(bad)))

bad2 = copy.deepcopy(rec)
bad2["vat_summary"][0]["amount"] = "257.31"
check("bad vat amount caught", len(S.validate_record(bad2)) >= 1)

rc = copy.deepcopy(rec)
rc["supplier"].update({"country": "DE", "vat_id": "DE123456789", "business_id": None})
rc["invoice"].update({"reference_type": None, "reference_value": None})
rc["lines"] = [{"description": "Scharnier X", "quantity": "100", "unit": "St",
                "unit_price": "2.40", "vat_rate": "0.0", "line_total": "240.00"}]
rc["vat_summary"] = [{"rate": "0.0", "base": "240.00", "amount": "0.00"}]
rc["totals"] = {"net": "240.00", "vat": "0.00", "gross": "240.00"}
check("RC without mention caught", any("mention" in e for e in S.validate_record(rc)))
rc["invoice"]["reverse_charge_mention"] = "Steuerfreie innergemeinschaftliche Lieferung"
rc["buyer"]["vat_id"] = "FI87654321"
rc["bank"]["iban"] = "DE64 3709 9920 0532 0130 00"
rc["bank"]["bic"] = "NWRKDEFF"
errs_rc = S.validate_record(rc)
check("RC with mention + buyer vat passes", errs_rc == [])
if errs_rc:
    print("   " + "\n   ".join(errs_rc), flush=True)

cmp0 = S.compare_records(copy.deepcopy(rec), rec)
check(f"compare identical ({cmp0['total']} fields)", cmp0["wrong"] == [] and cmp0["total"] > 30)
mut = copy.deepcopy(rec)
mut["lines"][0]["unit_price"] = "38.05"
cmp1 = S.compare_records(mut, rec)
check("compare catches one wrong field", len(cmp1["wrong"]) == 1)

print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}", flush=True)
sys.exit(1 if fails else 0)
