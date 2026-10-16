"""
regression_gate.py -- The overseer's activation gate plus a full-corpus
dry run of the generated parsers.

Part 1 (the formal gate): each generated parser must
reproduce the LLM path's ACCEPTED output on the 8 discovery documents of
its type -- regression against its own history, no answer-key peeking.
A parser that fails the gate is not activated.

Part 2 (empirical designed-outcome check): run every parser over all 240
documents and tabulate outcomes per designed class (R/V/F/S) against the
answer key. This is evaluation tooling (the answer key is used for SCORING
only -- it is never given to a parser); its purpose is to confirm, before
the router is built, that the planted classes behave as designed:
    R -> parses and matches
    V/F -> raises (the router would fall back to the LLM)
    S -> parses, passes internal checks, but MISmatches the answer key
         (silently wrong -- the honest ceiling)

Usage: python regression_gate.py    (exit 1 if the formal gate fails)
"""

import sys
import json
import importlib.util
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import schemas
from check_llm_parses import compare_doc

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "data" / "documents"
KEYS = ROOT / "data" / "answer_key"
LLM = ROOT / "data" / "runs" / "llm_parses"
GEN = Path(__file__).resolve().parent / "parsers_generated"

TYPES = ["FBL3N", "ME2M", "VA05", "FBL1N", "MB52"]


def load_parser(ttype):
    path = GEN / f"parser_{ttype.lower()}.py"
    spec = importlib.util.spec_from_file_location(f"parser_{ttype.lower()}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    parsers = {t: load_parser(t) for t in TYPES}

    # ---- Part 1: formal regression gate (vs accepted LLM parses) ----------
    print("PART 1 -- regression gate (parser vs accepted LLM parses, 8 discovery docs/type)")
    gate_failed = False
    for t in TYPES:
        failures = []
        for llm_file in sorted(LLM.glob(f"*_{t}_*.json")):
            doc_id = llm_file.stem
            text = (DOCS / f"{doc_id}.txt").read_text(encoding="utf-8")
            accepted = json.loads(llm_file.read_text(encoding="utf-8"))
            try:
                got = parsers[t].parse(text)
            except Exception as e:
                failures.append(f"{doc_id}: raised {type(e).__name__}: {e}")
                continue
            mism = []
            compare_doc(t, got, accepted, mism)
            if mism:
                failures.append(f"{doc_id}: {len(mism)} mismatches, first: {mism[0]}")
        status = "PASS" if not failures else "FAIL"
        print(f"  {t}: {status}" + ("" if not failures else f" -- {failures[0]}"))
        gate_failed |= bool(failures)

    # ---- Part 2: full-corpus dry run vs answer keys ------------------------
    print("\nPART 2 -- full-corpus dry run (parser vs answer key, all 240 docs)")
    print(f"{'type':6} {'class':5} {'docs':>4} {'ok':>3} {'raised':>6} {'match':>5} {'silent-wrong':>12}")
    deviations = []
    for t in TYPES:
        tally = {}
        for key_file in sorted(KEYS.glob(f"*_{t}_*.json")):
            ak = json.loads(key_file.read_text(encoding="utf-8"))
            doc_id, cls = ak["doc_id"], ak["doc_class"]
            text = (DOCS / f"{doc_id}.txt").read_text(encoding="utf-8")
            row = tally.setdefault(cls, {"docs": 0, "ok": 0, "raised": 0, "match": 0, "wrong": 0})
            row["docs"] += 1
            try:
                got = parsers[t].parse(text)
            except Exception:
                row["raised"] += 1
                if cls == "R":
                    deviations.append(f"{doc_id}: R-class raised (should parse cleanly)")
                if cls == "S":
                    deviations.append(f"{doc_id}: S-class raised (should be silently wrong, not loud)")
                continue
            row["ok"] += 1
            if cls in ("V", "F"):
                deviations.append(f"{doc_id}: {cls}-class parsed without raising (designed to fall back)")
            mism = []
            compare_doc(t, got, ak["parse"], mism)
            if mism:
                row["wrong"] += 1
                if cls == "R":
                    deviations.append(f"{doc_id}: R-class mismatch: {mism[0]}")
            else:
                row["match"] += 1
                if cls == "S":
                    deviations.append(f"{doc_id}: S-class matched the answer key (the lie failed?)")
        for cls in "RVFS":
            if cls in tally:
                r = tally[cls]
                print(f"{t:6} {cls:5} {r['docs']:>4} {r['ok']:>3} {r['raised']:>6} {r['match']:>5} {r['wrong']:>12}")

    print("\nDesign deviations (empirical vs designed-outcome table):")
    if deviations:
        for d in deviations:
            print("  [DEVIATION]", d)
    else:
        print("  none -- every class behaved exactly as designed")

    return 1 if gate_failed else 0


if __name__ == "__main__":
    sys.exit(main())
