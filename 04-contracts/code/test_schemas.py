"""Sanity suite for schemas.py — run before anything imports it.
Exit 1 on any failure. (03 precedent: code/test_schemas.py, 21 checks.)"""

import sys
from datetime import date

from schemas import (CATEGORY_NAMES, KIND, compare_category, compare_records,
                     norm_jurisdiction, norm_text, parse_date_answer,
                     parties_equal, span_segments, segment_in_text,
                     validate_record, norm_ws)

FAILURES = []
CHECKS = 0


def check(label, cond):
    global CHECKS
    CHECKS += 1
    print(f"{'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        FAILURES.append(label)


# --- structure ---
check("12 categories", len(CATEGORY_NAMES) == 12)
check("5 extraction + 7 yesno",
      sum(1 for n in CATEGORY_NAMES if KIND[n] == "extraction") == 5
      and sum(1 for n in CATEGORY_NAMES if KIND[n] == "yesno") == 7)

# --- date parsing (the spike lesson: key m/d/yy vs README mm/dd/yyyy) ---
check("date m/d/yy pivots 1999", parse_date_answer("6/8/99") == ("date", date(1999, 6, 8)))
check("date mm/dd/yyyy", parse_date_answer("06/08/1999") == ("date", date(1999, 6, 8)))
check("date 12/31/00 pivots 2000", parse_date_answer("12/31/00") == ("date", date(2000, 12, 31)))
check("date equality across formats",
      parse_date_answer("6/8/99") == parse_date_answer("06/08/1999"))
check("textual date", parse_date_answer("June 8, 1999") == ("date", date(1999, 6, 8)))
check("perpetual", parse_date_answer("Perpetual") == ("perpetual", None))
check("redacted 1/[]/2020", parse_date_answer("1/[]/2020") == ("redacted", None))
check("empty", parse_date_answer("") == ("empty", None))
check("invalid calendar date falls to text", parse_date_answer("2/30/1999")[0] == "text")

# --- parties (the spike contract's real values) ---
KEY_P = 'Snap Technologies, Inc. ("Snap"); United Airlines, Inc. ("Sponsor")'
GOT_P = 'Snap Technologies, Inc. ("Snap"); United Airlines, Inc. ("Sponsor")'
check("parties exact", parties_equal(GOT_P, KEY_P))
check("parties reordered", parties_equal(
    'United Airlines, Inc. ("Sponsor"); Snap Technologies, Inc. ("Snap")', KEY_P))
check("parties punctuation-insensitive", parties_equal(
    'Snap Technologies Inc ("Snap"); United Airlines Inc ("Sponsor")', KEY_P))
check("parties short/long split covered", parties_equal(
    'Snap; Snap Technologies, Inc.; United Airlines, Inc.; Sponsor', KEY_P))
check("parties mismatch detected", not parties_equal(
    'Delta Air Lines, Inc. ("Delta"); Snap Technologies, Inc. ("Snap")', KEY_P))
check("parties empty vs nonempty", not parties_equal("", KEY_P))

# --- governing law ---
check("jurisdiction strips State of",
      norm_jurisdiction("the State of California") == norm_jurisdiction("California"))
check("jurisdiction case", norm_jurisdiction("NEW YORK") == norm_jurisdiction("New York"))
check("jurisdiction distinct", norm_jurisdiction("Delaware") != norm_jurisdiction("California"))
check("multi-jurisdiction order-insensitive (Usio case)",
      norm_jurisdiction("Virginia, Texas") == norm_jurisdiction("Texas, Virginia"))
check("multi-jurisdiction 'and' split",
      norm_jurisdiction("England and Wales") == norm_jurisdiction("Wales; England"))
check("multi vs single distinct",
      norm_jurisdiction("Virginia, Texas") != norm_jurisdiction("Texas"))

# --- record validation ---
def entry(present=False, spans=None, answer=None):
    return {"present": present, "spans": spans or [], "answer": answer}

good = {"contract": "x.txt", "categories": {
    "Document Name": entry(True, ["CO-BRANDING AGREEMENT"], "Co-Branding Agreement"),
    "Parties": entry(True, ["by and between ..."], KEY_P),
    "Agreement Date": entry(True, ["dated as of June 8, 1999"], "06/08/1999"),
    "Governing Law": entry(True, ["laws of the State of California"], "California"),
    "Expiration Date": entry(True, ["shall end as of December 31, 2000."], "12/31/2000"),
    "Anti-Assignment": entry(True, ["Neither party may assign ..."]),
    "License Grant": entry(True, ["hereby grants ..."]),
    "Cap on Liability": entry(True, ["NEITHER PARTY WILL HAVE ANY LIABILITY ..."]),
    "Audit Rights": entry(),
    "Insurance": entry(),
    "IP Ownership Assignment": entry(),
    "Non-Compete": entry(),
}}
check("valid record passes", validate_record(good) == [])

bad = {k: (dict(v) if isinstance(v, dict) else v) for k, v in good.items()}
bad["categories"] = dict(good["categories"])
bad["categories"]["Anti-Assignment"] = entry(True, ["x"], "Yes")  # yesno with answer
check("yesno answer rejected", any("Anti-Assignment" in e for e in validate_record(bad)))

bad2 = {"contract": "x", "categories": {k: v for k, v in good["categories"].items()
                                        if k != "Insurance"}}
check("missing category rejected", any("Insurance" in e for e in validate_record(bad2)))

bad3 = dict(good, categories=dict(good["categories"]))
bad3["categories"]["Governing Law"] = entry(True, ["laws of California"], None)
check("present-without-answer rejected", any("Governing Law" in e for e in validate_record(bad3)))

bad4 = dict(good, categories=dict(good["categories"]))
bad4["categories"]["License Grant"] = entry(True, [])
check("present-without-span rejected", any("License Grant" in e for e in validate_record(bad4)))

# --- comparison (spike contract end-to-end: got 12/12 vs key) ---
key = {"contract": "x.txt", "categories": {
    "Document Name": entry(True, ["CO-BRANDING AGREEMENT"], "CO-BRANDING AGREEMENT"),
    "Parties": entry(True, ["..."], KEY_P),
    "Agreement Date": entry(True, ["June 8, 1999"], "6/8/99"),
    "Governing Law": entry(True, ["..."], "California"),
    "Expiration Date": entry(True, ["..."], "12/31/00"),
    "Anti-Assignment": entry(True, ["..."]),
    "License Grant": entry(True, ["..."]),
    "Cap on Liability": entry(True, ["..."]),
    "Audit Rights": entry(),
    "Insurance": entry(),
    "IP Ownership Assignment": entry(),
    "Non-Compete": entry(),
}}
res = compare_records(good, key)
check("spike-style records: 12/12 match", all(r["match"] for r in res.values()))
check("date format difference tolerated", res["Agreement Date"]["match"])
check("document name case tolerated", res["Document Name"]["match"])

flip = dict(good, categories=dict(good["categories"]))
flip["categories"]["Insurance"] = entry(True, ["shall maintain insurance"])
check("presence flip detected", not compare_records(flip, key)["Insurance"]["match"])

wrong_date = dict(good, categories=dict(good["categories"]))
wrong_date["categories"]["Agreement Date"] = entry(True, ["x"], "06/09/1999")
check("wrong date detected", not compare_records(wrong_date, key)["Agreement Date"]["match"])

# --- partial records (narrowed reads) ---
partial = {"contract": "x.txt", "categories": {
    "Audit Rights": entry(True, ["right to audit the books"]),
    "Non-Compete": entry(),
}}
check("partial record passes with subset",
      validate_record(partial, ["Audit Rights", "Non-Compete"]) == [])
check("partial record fails against full set",
      any("Governing Law" in e for e in validate_record(partial)))
check("unasked category rejected in subset mode",
      any("unasked" in e for e in validate_record(partial, ["Audit Rights"])))

# --- span-only presence (pre-registered scoring rule) ---
key_blank = dict(key, categories=dict(key["categories"]))
key_blank["categories"]["Expiration Date"] = entry(True, ["until five (5) years following the Effective Date"], "")
got_dated = dict(good, categories=dict(good["categories"]))
got_dated["categories"]["Expiration Date"] = entry(True, ["..."], "02/10/2019")
r = compare_records(got_dated, key_blank)["Expiration Date"]
check("span-only key row scores presence-only", r["match"] and r["axis"] == "presence-only")
got_absent = dict(good, categories=dict(good["categories"]))
got_absent["categories"]["Expiration Date"] = entry(False)
r2 = compare_records(got_absent, key_blank)["Expiration Date"]
check("span-only key row still detects missed presence", not r2["match"])

# --- spans ---
segs = span_segments("January 1, 2010 <omitted> This Agreement is effective as of the date written above.")
check("<omitted> splits to 2 segments", len(segs) == 2)
check("segment found in normalised text",
      segment_in_text(norm_ws("shall  end as\nof December 31, 2000."),
                      norm_ws("The Term ... shall end as of December 31, 2000. More text")))
check("absent segment not found", not segment_in_text("no such words", "some contract text"))

print(f"\n{len(FAILURES)} failures of {CHECKS} checks")
sys.exit(1 if FAILURES else 0)
