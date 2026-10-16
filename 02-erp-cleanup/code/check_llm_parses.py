"""
check_llm_parses.py -- Validation gate for LLM parse outputs
(method B): structural conformance via schemas.validate_parse,
then field-level accuracy against the answer keys.

This comparison logic is the seed of evaluate.py: one definition of field
equality, used for the LLM path now and the generated parsers later.

Usage: python check_llm_parses.py            # checks whatever is in llm_parses/
Exit 1 if any parse is structurally invalid; accuracy mismatches are
reported, not fatal (they are findings, not bugs).
"""

import sys
import json
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import schemas

ROOT = Path(__file__).resolve().parent.parent
PARSE_DIR = ROOT / "data" / "runs" / "llm_parses"
KEY_DIR = ROOT / "data" / "answer_key"


def field_equal(spec_type, got, want):
    base = spec_type.rstrip("?")
    if got is None or want is None:
        return got is None and want is None
    if base in ("money", "qty"):
        return schemas.money_equal(got, want)
    if base == "int":
        return int(got) == int(want)
    return str(got) == str(want)


def compare_records(spec, got, want, where, mismatches):
    """Compare one record against the answer key per the field spec.
    Returns number of fields compared."""
    n = 0
    for name, spec_type in spec:
        if spec_type == "list":
            continue  # subtotal lists handled explicitly by the caller
        n += 1
        g = got.get(name) if isinstance(got, dict) else None
        w = want.get(name)
        if not field_equal(spec_type, g, w):
            mismatches.append(f"{where}.{name}: got {g!r} want {w!r}")
    return n


def compare_list(spec, got_list, want_list, where, mismatches):
    n = 0
    if len(got_list or []) != len(want_list or []):
        mismatches.append(f"{where}: length {len(got_list or [])} vs {len(want_list or [])}")
    for i, want in enumerate(want_list or []):
        got = (got_list or [])[i] if i < len(got_list or []) else {}
        n += compare_records(spec, got, want, f"{where}[{i}]", mismatches)
    return n


def compare_doc(ttype, got, want, mismatches):
    schema = schemas.SCHEMAS[ttype]
    n = compare_records(schema["header"], got.get("header", {}), want["header"], "header", mismatches)
    # plants is a list of plain strings in the MB52 header
    if ttype == "MB52":
        n += 1
        if list(got.get("header", {}).get("plants", [])) != list(want["header"]["plants"]):
            mismatches.append(f"header.plants: got {got.get('header', {}).get('plants')!r} "
                              f"want {want['header']['plants']!r}")
    if ttype == "FBL1N":
        gv, wv = got.get("vendors", []), want["vendors"]
        if len(gv) != len(wv):
            mismatches.append(f"vendors: length {len(gv)} vs {len(wv)}")
        for i, w in enumerate(wv):
            g = gv[i] if i < len(gv) else {}
            n += compare_records(schema["vendors"], g, w, f"vendors[{i}]", mismatches)
            n += compare_list(schema["line_items"], g.get("line_items", []),
                              w["line_items"], f"vendors[{i}].items", mismatches)
            n += compare_list(schema["vendor_totals"], g.get("vendor_totals", []),
                              w["vendor_totals"], f"vendors[{i}].totals", mismatches)
    else:
        n += compare_list(schema["line_items"], got.get("line_items", []),
                          want["line_items"], "items", mismatches)
        n += compare_records(schema["totals"], got.get("totals", {}), want["totals"],
                             "totals", mismatches)
        sub_spec = schema.get("subtotal_item")
        if sub_spec:
            list_field = schema["totals"][0][0]
            n += compare_list(sub_spec, (got.get("totals", {}) or {}).get(list_field, []),
                              want["totals"][list_field], f"totals.{list_field}", mismatches)
    return n


def main():
    parse_files = sorted(PARSE_DIR.glob("*.json"))
    if not parse_files:
        print(f"No parses found in {PARSE_DIR}")
        return 1
    structural_failures = 0
    by_type = {}
    all_mismatch_lines = []
    for pf in parse_files:
        doc_id = pf.stem
        got = json.loads(pf.read_text(encoding="utf-8"))
        ak = json.loads((KEY_DIR / f"{doc_id}.json").read_text(encoding="utf-8"))
        ttype, want = ak["transaction_type"], ak["parse"]

        errs = schemas.validate_parse(ttype, got)
        if errs:
            structural_failures += 1
            print(f"[STRUCT FAIL] {doc_id}: {len(errs)} schema errors, first: {errs[0]}")
            continue

        mismatches = []
        n = compare_doc(ttype, got, want, mismatches)
        stats = by_type.setdefault(ttype, {"docs": 0, "fields": 0, "wrong": 0, "perfect_docs": 0})
        stats["docs"] += 1
        stats["fields"] += n
        stats["wrong"] += len(mismatches)
        stats["perfect_docs"] += (not mismatches)
        for m in mismatches[:10]:
            all_mismatch_lines.append(f"{doc_id}: {m}")
        if len(mismatches) > 10:
            all_mismatch_lines.append(f"{doc_id}: ... {len(mismatches) - 10} more")

    print(f"\nLLM parse check over {len(parse_files)} documents:")
    print(f"{'type':7} {'docs':>4} {'perfect':>7} {'fields':>7} {'wrong':>5}  {'field acc':>9}")
    tot_f = tot_w = 0
    for t in sorted(by_type):
        s = by_type[t]
        acc = 100.0 * (s["fields"] - s["wrong"]) / max(1, s["fields"])
        print(f"{t:7} {s['docs']:>4} {s['perfect_docs']:>7} {s['fields']:>7} {s['wrong']:>5}  {acc:>8.3f}%")
        tot_f += s["fields"]; tot_w += s["wrong"]
    print(f"{'ALL':7} {sum(s['docs'] for s in by_type.values()):>4} "
          f"{sum(s['perfect_docs'] for s in by_type.values()):>7} {tot_f:>7} {tot_w:>5}  "
          f"{100.0 * (tot_f - tot_w) / max(1, tot_f):>8.3f}%")
    if all_mismatch_lines:
        print("\nMismatches:")
        for line in all_mismatch_lines:
            print(" ", line)
    return 1 if structural_failures else 0


if __name__ == "__main__":
    sys.exit(main())
