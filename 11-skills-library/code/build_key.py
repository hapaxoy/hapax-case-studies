"""Build the answer key and the review sheet (Project 11, Phase 3).

Run after build_requests.py (briefs and assemble):   python code/build_key.py

Writes only to data/key/ (never under world/):
  key.json                one entry per test request: reference SQL and result, accepted readings, naive variants with
                          results, the two accepted outcomes for undocumented issues, keyword rules, trap classes
  reference_sql/<Q>.sql   the reference query of each distinct question, with its naive variants as commented blocks
  review_sheet.md         the plain-English sheet for a reviewer (no SQL)

Every number in the key has been produced twice (SQL on the warehouse, pandas on the generator's own tables) and the
two agree; key_runner.evaluate_all() stops the build if any check fails.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

import config as cfg
from key_lib import describe_difference, format_value, frame_to_rows
from key_runner import evaluate_all, load_briefs
from wh_common import log

CLASS_LABELS = {
    "company_definition": "company definition", "fiscal_calendar": "fiscal calendar", "scd": "history of regions or categories",
    "migration": "web-platform migration", "time_zone": "time zone", "exclusions": "exclusions", "fan_out": "double counting in joins",
    "semi_additive": "stock (never added across weeks)", "vat": "VAT", "ambiguous": "genuinely ambiguous request",
    "override": "request overrides a company default", "undocumented": "undocumented data problem", "clean": "clean (no trap)",
}


# Requests whose key was widened after the independent review of 15 Oct 2026 (listed in the review sheet's introduction).
# The accepted readings themselves live in key_questions_a/b/c.py; this is only the plain-English summary for a reviewer.
WIDENED_AFTER_REVIEW = [
    ("REQ-T08", "the 364-day rule for a new store applied at the start of each fiscal period, not of the whole quarter (Lohja is then in for P8 and P9)"),
    ("REQ-T14", "'biggest' as net sales over the last full fiscal year, or over the trailing 52 weeks"),
    ("REQ-T20", "'doing well' as year-to-date growth against last year, total or like-for-like"),
    ("REQ-T06 and REQ-T23", "stores only (no Web row), or web sales placed in the cohort by dispatch date"),
    ("REQ-T11 and REQ-T17", "the whole Outdoor Lighting subcategory counted in Electrical, including the five delisted articles"),
    ("REQ-T28", "the four weeks ending at the stock week in the denominator"),
    ("REQ-T43", "units with web sales dated by dispatch date, or units in the stores only"),
    ("REQ-T26 and REQ-T58", "the table ranked by total net sales instead of net sales per trading day"),
]


def safe_write(path: Path, text: str) -> None:
    """Write only inside data/key/, and never over an input or under world/."""
    resolved = path.resolve()
    if cfg.KEY_DIR.resolve() not in resolved.parents:
        raise PermissionError(f"Refusing to write outside data/key/: {resolved}")
    if cfg.WORLD_DIR.resolve() in resolved.parents:
        raise PermissionError(f"The key must never be written under world/: {resolved}")
    if resolved in {cfg.WAREHOUSE_PATH.resolve(), cfg.FACTS_PATH.resolve()}:
        raise PermissionError(f"Output equals an input: {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(text, encoding="utf-8", newline="\n")


def table(frame: pd.DataFrame, columns: list[dict]) -> dict:
    return {"columns": [c["name"] for c in columns], "rows": frame_to_rows(frame[[c["name"] for c in columns]])}


def classes_of(question) -> list[str]:
    found = {n.trap for n in question.naive}
    if question.interpretations:
        found.add("ambiguous")
    if question.undocumented:
        found.add("undocumented")
    if not found:
        found.add("clean")
    return sorted(found)


def build_entry(brief: dict, request: dict, question, evaluation: dict) -> dict:
    from key_lib import keyword_rule_match   # noqa: F401  (kept importable for the validator)
    entry = {
        "request_id": brief["id"], "question_id": question.qid, "pattern": brief["pattern"], "twin_group": brief["twin"],
        "department": brief["department"], "requester": brief["requester"], "received": brief["received"],
        "request_text": request["request_text"], "trap_classes": classes_of(question), "ordered": question.ordered, "top_n": question.top_n,
        "columns": question.columns,
        "marking": {"relative_tolerance": cfg.MARKING_REL_TOLERANCE, "percentage_point_tolerance": cfg.MARKING_PCT_TOLERANCE,
                    "rows_order_insensitive": not question.ordered, "match_columns_by_values": True},
        "reference": {"sql": question.reference_sql.strip(), "result": table(evaluation["reference_frame"], question.columns)},
        "equal_values_may_swap": evaluation.get("ties_inside_list", {}).get("", False),
        "alternatives": [{"label": alt["label"], "sql": alt["sql"].strip(), "result": table(found["frame"], question.columns),
                          "order_by": question.alternatives_ordered_by.get(alt["label"])}
                         for alt, found in zip(question.alternatives, evaluation["alternatives"])],
        "interpretations": [], "naive": [], "undocumented": None,
    }
    for interp, found in zip(question.interpretations, evaluation["interpretations"]):
        record = {
            "id": interp.ident, "label": interp.label, "sql": interp.sql.strip(), "columns": interp.columns,
            "result": table(found["frame"], interp.columns),
            "equal_values_may_swap": evaluation.get("ties_inside_list", {}).get(interp.ident, False),
            "assumption_rule": {"field": "assumptions", "groups": interp.keywords, "example_pass": interp.example_pass, "example_fail": interp.example_fail},
            "published_outcome": None}
        if interp.published_sql:
            record["published_outcome"] = {
                "label": "also accepted: the published figures, if the caveats name the duplicated receipts", "sql": interp.published_sql.strip(),
                "result": table(found["published_frame"], interp.columns), "differs_from_corrected_beyond_10x_tolerance": found["published_differs"],
                "caveat_rule": {"field": "caveats", "groups": interp.caveat_keywords, "example_pass": interp.caveat_pass, "example_fail": interp.caveat_fail}}
        entry["interpretations"].append(record)
    for naive, found in zip(question.naive, evaluation["naive"]):
        entry["naive"].append({
            "trap": naive.trap, "label": naive.label, "sql": naive.sql.strip(), "plain": naive.plain,
            "result": table(found["frame"], question.columns), "differs_from_every_accepted_result": found["bites"],
            "difference": describe_difference(evaluation["reference_frame"], found["frame"], question.columns)})
    if question.undocumented:
        spec = question.undocumented
        published = evaluation["published_frame"]
        entry["undocumented"] = {
            "incident": spec["incident"], "what": spec["what"],
            "outcome_a_incident_free": {"label": "a: repairs the problem and returns the incident-free number", "result": entry["reference"]["result"]},
            "outcome_b_published_with_caveat": {
                "label": "b: returns the published number and names the problem in `caveats`", "sql": spec["published_sql"].strip(),
                "result": table(published, question.columns),
                "caveat_rule": {"field": "caveats", "groups": spec["keywords"], "example_pass": spec["example_pass"], "example_fail": spec["example_fail"]}},
            "outcome_c_published_without_warning": "wrong: the published number with no warning in `caveats`",
        }
        entry["naive"].append({
            "trap": "undocumented", "label": "published_number", "sql": spec["published_sql"].strip(), "plain": "Runs the same question on the published data without noticing the problem.",
            "result": table(published, question.columns), "differs_from_every_accepted_result": True,
            "difference": describe_difference(evaluation["reference_frame"], published, question.columns)})
    return entry


# ---------------------------------------------------------------------------
# The review sheet
# ---------------------------------------------------------------------------

PATTERN_NAMES = {1: "sales by region or week", 2: "like-for-like growth", 3: "category sales and margin", 4: "return rate", 5: "web sales and orders",
                 6: "click-and-collect share", 7: "average transaction value", 8: "members", 9: "campaign uplift", 10: "stock",
                 11: "top products", 12: "store league table", 13: "new members", 14: "figures including VAT"}


def pretty(name: str) -> str:
    """Column name in words for the review sheet (the _ty / _ly suffixes are the later and the earlier year of a comparison)."""
    if name.endswith("_ty"):
        return name[:-3].replace("_", " ") + " (year asked about)"
    if name.endswith("_ly"):
        return name[:-3].replace("_", " ") + " (year before)"
    return name.replace("_", " ")


def long_date(iso: str) -> str:
    year, month, day = (int(part) for part in iso.split("-"))
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    return f"{day} {months[month - 1]} {year}"


def md_table(result: dict, columns: list[dict], limit: int = 14) -> str:
    units = {c["name"]: c["unit"] for c in columns}
    header = "| " + " | ".join(pretty(name) for name in result["columns"]) + " |"
    divider = "|" + "|".join("---" for _ in result["columns"]) + "|"
    lines = [header, divider]
    for row in result["rows"][:limit]:
        lines.append("| " + " | ".join(format_value(v, units[name]) if units[name] not in ("date", "text") else str(v)
                                       for name, v in zip(result["columns"], row)) + " |")
    if len(result["rows"]) > limit:
        lines.append(f"| ... {len(result['rows']) - limit} more rows | " + " | ".join("" for _ in result["columns"][1:]) + " |")
    return "\n".join(lines)


def sheet_entry(entry: dict, question, twin_ids: list) -> str:
    plain = question.plain
    title = "no trap" if entry["trap_classes"] == ["clean"] else ", ".join(CLASS_LABELS[c] for c in entry["trap_classes"])
    lines = [f"### {entry['request_id']}: {PATTERN_NAMES[entry['pattern']]} ({title})", "",
             f"{entry['department']}, {entry['requester']}, received {long_date(entry['received'])}." + (f" Same question as {', '.join(twin_ids)} in different words; the answer is the same." if twin_ids else ""),
             "", f"> {entry['request_text']}", "",
             f"**The reference answer counts:** {plain['counts']}", ""]
    lines += [f"**It leaves out:** {plain['leaves_out']}", "", f"**Where this is written down:** {'; '.join(plain['docs'])}.", ""]
    if entry["interpretations"]:
        lines += ["**Accepted readings** (any one counts if the answer says which it used):", ""]
        for interp in entry["interpretations"]:
            lines += [f"*{interp['label']}*", "", md_table(interp["result"], interp["columns"]), ""]
            if interp["published_outcome"]:
                lines += ["The published figures for this reading are also accepted if the caveats name the duplicated receipts of Tampere Lielahti in September 2025 (that store's week was posted twice):", "",
                          md_table(interp["published_outcome"]["result"], interp["columns"]), ""]
            if interp["equal_values_may_swap"]:
                lines += ["(Some products tie on units inside the list; tied products may come in either order.)", ""]
    elif entry["undocumented"]:
        undocumented = entry["undocumented"]
        lines += [f"**The hidden problem:** {undocumented['what']} It is in no document the analysts have.", "",
                  "**Two answers count as right.** (a) The corrected figures, which are the reference:", "", md_table(entry["reference"]["result"], entry["columns"]), "",
                  "(b) The published figures, if the answer's caveats name the problem:", "",
                  md_table(undocumented["outcome_b_published_with_caveat"]["result"], entry["columns"]), "",
                  "The published figures with no warning are wrong.", ""]
    else:
        lines += ["**Reference result:**", "", md_table(entry["reference"]["result"], entry["columns"]), ""]
        if entry["alternatives"]:
            lines += ["Other readings of the request are also accepted without the answer naming them. Each gives a different table:", ""]
            for alt in entry["alternatives"]:
                lines += [f"*{alt['label']}*", "", md_table(alt["result"], entry["columns"]), ""]
    if entry["naive"] and not entry["undocumented"]:
        lines.append("**The trap, and what a plausible wrong answer does:**")
        lines.append("")
        for naive in entry["naive"]:
            lines.append(f"- {naive['plain']} The result: {naive['difference']}.")
        lines.append("")
    elif not entry["naive"] and "clean" in entry["trap_classes"]:
        lines += ["**The trap:** none. Everyone should get this one right; it is here to check that the extra knowledge does not cost accuracy where there is nothing to know.", ""]
    return "\n".join(lines)


def build_sheet(entries: list[dict], questions: dict) -> str:
    twins = {}
    for e in entries:
        if e["twin_group"]:
            twins.setdefault(e["twin_group"], []).append(e["request_id"])
    order = sorted(entries, key=lambda e: (0 if e["pattern"] == 2 else 1, e["pattern"], e["request_id"]))
    counts = Counter(c for e in entries for c in e["trap_classes"])
    intro = [
        "# Review sheet for the test-request answer key (case 11)", "",
        "One entry per test request: what the reference answer counts and leaves out, why, the trap, and the number. No SQL. "
        "Check each one by common sense: is this really what the question means at Tuomimetsä, and is the number believable?", "",
        "How to read it", "",
        "- The warehouse is synthetic and about a twentieth of the in-world size, so amounts are in the tens or hundreds of thousands of euros for a period, not millions.",
        "- 'Today' is the first week of October 2026. The data runs to Sunday 4 October 2026 (fiscal week 22 of FY2026/27). 'Last period' is therefore P5 (31 August to 27 September 2026), 'last year' is FY2025/26 and 'this year' is FY2026/27, as the dictionary says.",
        "- 'The trap' lines describe the plausible wrong answers the marker will look for, and how far each is off.",
        "- The like-for-like requests come first, because that is where a quiet mistake in the key is most likely. Then the rest, by pattern.",
        "- Three independent reviewer agents re-checked all 60 reference answers on 15 October 2026. None broke a documented definition. Where they found a second defensible reading, the key now also accepts it (shown under the reference answer as 'other readings' or as an accepted reading): " +
        "; ".join(f"{ids}, {text}" for ids, text in WIDENED_AFTER_REVIEW) + ". Every wrong answer below still differs from all of these.", "",
        "Trap classes on this set (a request can carry two; targets in brackets): " +
        ", ".join(f"{CLASS_LABELS[c]} {counts.get(c, 0)} ({cfg.TRAP_CLASS_COUNTS[c]})" for c in cfg.TRAP_CLASS_COUNTS) + ".", "", "---", ""]
    body = []
    for e in order:
        partners = [i for i in twins.get(e["twin_group"], []) if i != e["request_id"]] if e["twin_group"] else []
        body.append(sheet_entry(e, questions[e["question_id"]], partners))
        body.append("---\n")
    return "\n".join(intro + body)


def reference_sql_file(question) -> str:
    parts = [f"-- {question.qid} (pattern {question.pattern}). Reference query.", question.reference_sql.strip(), ""]
    for interp in question.interpretations:
        parts += [f"-- Accepted reading: {interp.label}", interp.sql.strip(), ""]
        if interp.published_sql:
            parts += [f"-- Same reading on the published data (accepted with a caveat naming the duplicated receipts): {interp.ident}", interp.published_sql.strip(), ""]
    for alt in question.alternatives:
        parts += [f"-- Also accepted: {alt['label']}", alt["sql"].strip(), ""]
    if question.undocumented:
        parts += ["-- Published number (same question without the repair; the problem is in no document)", question.undocumented["published_sql"].strip(), ""]
    for naive in question.naive:
        parts += [f"-- Naive variant [{naive.trap}] {naive.label}: {naive.plain}", naive.sql.strip(), ""]
    for index, sql in enumerate(question.invariance_sql, start=1):
        parts += [f"-- Sloppy variant {index} (must give the reference result)", sql.strip(), ""]
    return "\n".join(parts)


def main() -> int:
    briefs = load_briefs()
    requests = {r["id"]: r for r in json.loads((cfg.REQUESTS_DIR / "test_requests.json").read_text(encoding="utf-8"))}
    qids = sorted({b["qid"] for b in briefs})
    questions, results = evaluate_all(qids)
    failed = {qid: [o for o in r["outcomes"] if not o["ok"]] for qid, r in results.items() if not r["ok"]}
    if failed:
        print("KEY CHECKS FAILED:")
        for qid, outcomes in failed.items():
            for outcome in outcomes:
                print(f"  {qid}: {outcome['check']} | {outcome['detail']}")
        return 1
    entries = [build_entry(b, requests[b["id"]], questions[b["qid"]], results[b["qid"]]) for b in briefs]
    counts = Counter(c for e in entries for c in e["trap_classes"])
    log("Trap classes achieved (target): " + ", ".join(f"{c} {counts.get(c, 0)} ({n})" for c, n in cfg.TRAP_CLASS_COUNTS.items()))
    key = {"case": "11 Skills Library", "built_with_seed": cfg.RANDOM_SEED, "n_requests": len(entries), "entries": entries}
    safe_write(cfg.KEY_DIR / "key.json", json.dumps(key, indent=1, ensure_ascii=False, default=str))
    for qid in qids:
        safe_write(cfg.KEY_DIR / "reference_sql" / f"{qid}.sql", reference_sql_file(questions[qid]))
    safe_write(cfg.KEY_DIR / "review_sheet.md", build_sheet(entries, questions))
    log(f"Wrote data/key/key.json ({len(entries)} requests), {len(qids)} reference_sql files and review_sheet.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
