"""
router.py -- Replays the 240-document stream through the hybrid pipeline
and records every routing event.

The router NEVER reads the answer key. Its inputs are exactly what a real
deployment would have:
    - the documents (data/documents/), replayed in date order,
    - the recorded LLM parses (data/runs/llm_parses/) standing in for live
      LLM calls (method B: they were produced by subagents),
    - the generated parsers (code/parsers_generated/), activated per the
      overseer rule: after 8 accepted LLM parses of a type + regression gate,
    - master data (config.py) for existence checks -- in-world, the company
      knows its own vendors, materials, accounts and customers.

Per document: deterministic parser first when active; every deterministic
result is validated (schema + internal arithmetic + master-data lookups);
on parser exception or validation failure the document falls back to the
LLM parse. LLM parses are themselves schema-validated (a schema failure
would mean a retry -- by the time of the replay, retried parses are already
the recorded final ones; retry costs are carried in parse_agent_log.json).

Output: data/runs/stream_events.json -- one event per document, in stream
order, plus parser-activation events. Class labels (R/V/F/S) are added by
evaluate.py, which joins the answer key; they are deliberately absent here.

Usage: python router.py
"""

import sys
import json
import importlib.util
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config
import schemas

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "data" / "documents"
LLM = ROOT / "data" / "runs" / "llm_parses"
GEN = Path(__file__).resolve().parent / "parsers_generated"
OUT = ROOT / "data" / "runs" / "stream_events.json"

ACTIVATION_THRESHOLD = 8   # pre-registered, N = 8

MONEY_TOL_DOC = 0.02       # internal-arithmetic tolerance across a whole document


def load_parser(ttype):
    path = GEN / f"parser_{ttype.lower()}.py"
    spec = importlib.util.spec_from_file_location(f"gen_{ttype.lower()}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Router-side validation (schema + internal arithmetic + master data).
# Works on the parse payload ONLY -- no answer key anywhere.
# ---------------------------------------------------------------------------

def _close(a, b, tol=MONEY_TOL_DOC):
    return abs(a - b) <= tol


def internal_arithmetic_ok(ttype, p, reasons):
    ok = True
    if ttype == "FBL3N":
        sd = sum(li["amount"] for li in p["line_items"] if li["debit_credit"] == "S")
        sc = sum(li["amount"] for li in p["line_items"] if li["debit_credit"] == "H")
        if not _close(sd, p["totals"]["sum_debit"]):
            reasons.append(f"sum_debit {sd:.2f} != {p['totals']['sum_debit']:.2f}"); ok = False
        if not _close(sc, p["totals"]["sum_credit"]):
            reasons.append(f"sum_credit {sc:.2f} != {p['totals']['sum_credit']:.2f}"); ok = False
        if not _close(p["totals"]["sum_debit"] + p["totals"]["sum_credit"], p["totals"]["balance"]):
            reasons.append("balance != debit+credit"); ok = False
    elif ttype == "ME2M":
        by_vendor = {}
        for li in p["line_items"]:
            by_vendor[li["vendor_number"]] = by_vendor.get(li["vendor_number"], 0.0) + li["net_value"]
        for sub in p["totals"]["vendor_subtotals"]:
            got = by_vendor.get(sub["vendor_number"])
            if got is None or not _close(got, sub["total_value"]):
                reasons.append(f"vendor {sub['vendor_number']} subtotal mismatch"); ok = False
        if not _close(sum(s["total_value"] for s in p["totals"]["vendor_subtotals"]),
                      p["totals"]["grand_total"]):
            reasons.append("grand_total != sum of subtotals"); ok = False
    elif ttype == "VA05":
        if not _close(sum(li["net_value"] for li in p["line_items"]),
                      p["totals"]["total_net_value"]):
            reasons.append("total_net_value != sum of lines"); ok = False
    elif ttype == "FBL1N":
        for v in p["vendors"]:
            per_curr = {}
            for li in v["line_items"]:
                bucket = per_curr.setdefault(li["currency"], {"open": 0.0, "cleared": 0.0})
                bucket["cleared" if li["status"] == "cleared" else "open"] += li["amount"]
            for vt in v["vendor_totals"]:
                b = per_curr.get(vt["currency"])
                if b is None or not _close(b["open"], vt["open_total"]) \
                        or not _close(b["cleared"], vt["cleared_total"]):
                    reasons.append(f"vendor {v['vendor_number']} {vt['currency']} totals mismatch"); ok = False
    elif ttype == "MB52":
        by_plant = {}
        for li in p["line_items"]:
            by_plant[li["plant"]] = by_plant.get(li["plant"], 0.0) + li["value_unrestricted"]
        for pt in p["totals"]["plant_totals"]:
            got = by_plant.get(pt["plant"])
            if got is None or not _close(got, pt["value_total"], tol=0.05):
                reasons.append(f"plant {pt['plant']} total mismatch"); ok = False
        if not _close(sum(t["value_total"] for t in p["totals"]["plant_totals"]),
                      p["totals"]["grand_value_total"], tol=0.05):
            reasons.append("grand_value_total != sum of plant totals"); ok = False
    return ok


def master_data_ok(ttype, p, reasons):
    ok = True
    vendors = set(config.VENDORS_BY_NUMBER)
    materials = {m["number"] for m in config.MATERIALS}
    accounts = {a["number"] for a in config.GL_ACCOUNTS}
    if ttype == "FBL3N":
        if p["header"]["gl_account"] not in accounts:
            reasons.append(f"unknown G/L account {p['header']['gl_account']}"); ok = False
    elif ttype == "ME2M":
        for li in p["line_items"]:
            if li["vendor_number"] not in vendors:
                reasons.append(f"unknown vendor {li['vendor_number']}"); ok = False; break
            if li["material"] not in materials:
                reasons.append(f"unknown material {li['material']}"); ok = False; break
    elif ttype == "FBL1N":
        for v in p["vendors"]:
            if v["vendor_number"] not in vendors:
                reasons.append(f"unknown vendor {v['vendor_number']}"); ok = False; break
    elif ttype == "MB52":
        for li in p["line_items"]:
            if li["material"] not in materials:
                reasons.append(f"unknown material {li['material']}"); ok = False; break
    # VA05: sold_to names may be truncated; customers carry no number in the
    # document, so the router does not master-check VA05 names (a real CS
    # team would match against CRM -- out of scope here, noted honestly).
    return ok


def validate_payload(ttype, payload):
    reasons = list(schemas.validate_parse(ttype, payload))
    if reasons:
        return False, ["schema: " + reasons[0]]
    reasons = []
    a = internal_arithmetic_ok(ttype, payload, reasons)
    m = master_data_ok(ttype, payload, reasons)
    return a and m, reasons


def main():
    parsers = {}          # type -> module, once activated
    accepted_llm = {t: 0 for t in config.TRANSACTION_TYPES}
    events = []

    doc_ids = sorted(p.stem for p in DOCS.glob("*.txt"))   # YYYY-MM_TYPE_NN => date order
    print(f"Replaying {len(doc_ids)} documents in stream order...")

    for doc_id in doc_ids:
        month, ttype, _ = doc_id.split("_")
        text = (DOCS / f"{doc_id}.txt").read_text(encoding="utf-8")
        event = {"doc_id": doc_id, "month": month, "type": ttype}

        det_payload = None
        if ttype in parsers:
            try:
                det_payload = parsers[ttype].parse(text)
            except Exception as e:
                event["parser_error"] = f"{type(e).__name__}: {str(e)[:120]}"

        if det_payload is not None:
            ok, reasons = validate_payload(ttype, det_payload)
            if ok:
                event["path"] = "deterministic"
                event["validation"] = "pass"
                events.append(event)
                continue
            event["det_validation_failed"] = reasons[:3]

        # LLM path (recorded parse stands in for the live call)
        llm_file = LLM / f"{doc_id}.json"
        if not llm_file.exists():
            event["path"] = "MISSING_LLM_PARSE"
            events.append(event)
            continue
        payload = json.loads(llm_file.read_text(encoding="utf-8"))
        ok, reasons = validate_payload(ttype, payload)
        event["path"] = "llm_fallback" if ttype in parsers else "llm_discovery"
        event["validation"] = "pass" if ok else f"FAIL: {reasons[:2]}"
        if ok:
            accepted_llm[ttype] += 1
            if ttype not in parsers and accepted_llm[ttype] >= ACTIVATION_THRESHOLD:
                parsers[ttype] = load_parser(ttype)
                events.append(event)
                events.append({"event": "parser_activated", "type": ttype,
                               "after_doc": doc_id,
                               "note": "8 accepted LLM parses + regression gate (regression_gate.py)"})
                continue
        events.append(event)

    OUT.write_text(json.dumps(events, indent=1, ensure_ascii=False), encoding="utf-8")

    # Summary
    from collections import Counter
    paths = Counter(e.get("path") for e in events if "doc_id" in e)
    print("Path counts:", dict(paths))
    missing = [e["doc_id"] for e in events if e.get("path") == "MISSING_LLM_PARSE"]
    fails = [e for e in events if "doc_id" in e and str(e.get("validation", "")).startswith("FAIL")]
    print("Missing LLM parses:", missing or "none")
    print("Validation failures on accepted path:", [e["doc_id"] for e in fails] or "none")
    print(f"Events written to {OUT}")
    return 1 if missing or fails else 0


if __name__ == "__main__":
    sys.exit(main())
