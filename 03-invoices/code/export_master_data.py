"""Export the router's world knowledge to data/master_data.json.

The router validates deterministic parses against "what a real AP system
knows": supplier identities and the PO register — existence/identity facts
only. It must never import config (which also knows the
planted events) — so this script derives a public master-data file once,
at generation time, and the router reads that.

Contents per supplier: identity block (name, country, address, VAT id,
business id, bank details, reference system, payment terms). Plus the PO
register (po_number, supplier_id, date) copied from the manifest.
No classes, no events, no answer-key material.
"""
from __future__ import annotations

import json
from pathlib import Path

import config

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
OUT = DATA / "master_data.json"


def repeat_supplier_entry(sup: dict) -> dict:
    return {
        "id": sup["id"], "name": sup["name"], "country": sup["country"],
        "street": sup["street"], "postcode": sup["postcode"], "city": sup["city"],
        "vat_id": sup["vat_id"], "business_id": sup.get("business_id"),
        "iban": sup.get("iban"), "bic": sup.get("bic"), "bankgiro": sup.get("bankgiro"),
        "reference_type": sup.get("reference_type"), "terms_days": sup.get("terms_days"),
    }


def oneoff_entry(entry: dict) -> dict:
    iban, bic = config.ONE_OFF_BANK[entry["key"]]
    return {
        "id": entry["key"], "name": entry["name"], "country": entry["country"],
        "street": entry["street"], "postcode": entry["postcode"], "city": entry["city"],
        "vat_id": entry["vat_id"], "business_id": entry.get("business_id"),
        "iban": iban, "bic": bic, "bankgiro": None,
        "reference_type": None, "terms_days": 30,
    }


def main() -> None:
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    suppliers = [repeat_supplier_entry(config.SUPPLIERS[sid])
                 for sid in config.REPEAT_SUPPLIER_ORDER]
    seen: set[str] = set()
    for e in config.ONE_OFFS:  # per-document roster; two suppliers invoice twice
        if e["vat_id"] not in seen:  # dedupe by legal identity, not roster key
            seen.add(e["vat_id"])
            suppliers.append(oneoff_entry(e))
    out = {
        "buyer": dict(config.BUYER),
        "suppliers": suppliers,
        "po_register": manifest["po_register"],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"master data written: {len(suppliers)} suppliers, "
          f"{len(out['po_register'])} POs -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
