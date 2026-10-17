"""Markdown tables for data/analysis/report.md, built from data/analysis/results.json (written by analyse_full.py).

    python code/report_tables.py        # writes data/analysis/tables.md

Kept apart from analyse_full.py so that the report's tables can be rebuilt from results.json alone. Each table is written under a
`<!-- table:name -->` marker line.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

CASE_ROOT = Path(__file__).resolve().parent.parent
ANALYSIS = CASE_ROOT / "data" / "analysis"
CELLS = ["sonnet/S", "sonnet/D", "sonnet/L", "sonnet/L-", "haiku/S", "haiku/L"]
CELL_NAME = {c: f"{c.split('/')[0].capitalize()} {c.split('/')[1]}" for c in CELLS}


def md(headers: list, rows: list) -> str:
    lines = ["| " + " | ".join(str(h) for h in headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def pct(value: float, digits: int = 1) -> str:
    return f"{value * 100:.{digits}f}%"


def markdown_tables(results: dict, per_request: dict, specs_info: dict) -> dict:
    """per_request: {request_id: {cell name: runs correct}}; specs_info: {request_id: (trap classes, pattern)}."""
    out = {}
    names = [CELL_NAME[c] for c in CELLS]
    cor = results["correctness"]
    out["headline"] = md(["Cell", "Correct runs", "Share", "95% interval (resampling the 60 requests)", "Same, keyword rules only"],
                         [[n, f"{cor['overall'][n]['correct']} of {cor['overall'][n]['runs']}", pct(cor['overall'][n]['share']),
                           f"{pct(cor['overall'][n]['ci_low'])} to {pct(cor['overall'][n]['ci_high'])}", cor["strict_overall"][n]] for n in names])
    rows = []
    for cls, row in cor["by_class"].items():
        cells = []
        for n in names:
            e = row[n]
            text = f"{e['correct']}/{e['runs']}"
            if row["requests"] >= 10:
                text += f" ({pct(e['share'], 0)}; {pct(e['ci_low'], 0)}-{pct(e['ci_high'], 0)})"
            cells.append(text)
        rows.append([cls.replace("_", " "), row["requests"]] + cells)
    out["by_class"] = md(["Trap class", "Requests"] + names, rows)
    tv = cor["trapped_vs_clean"]
    out["trapped_vs_clean"] = md(["Requests"] + names + ["Runs per cell"], [[k] + [f"{v[n]}" for n in names] + [v["runs"]] for k, v in tv.items()])
    att = results["attribution"]
    labels = sorted({l for v in att.values() for l in v})
    out["attribution"] = md(["Wrong runs, by the naive variant they match"] + names,
                            [[l.replace("_", " ")] + [att[n].get(l, 0) for n in names] for l in labels] + [["total wrong"] + [sum(att[n].values()) for n in names]])
    con = results["consistency"]
    out["consistency"] = md(["Measure"] + names, [
        ["All five runs return the same result (requests of 60)"] + [con["all_five_agree"][n]["requests"] for n in names],
        ["Correct in all five runs (requests of 60)"] + [con["correct_in_all_five"][n]["requests"] for n in names],
        ["Paraphrase pairs with the same majority result (of 10)"] + [con["paraphrase_pairs_agree"][n] for n in names]])
    d = results["definitions"]["cells"]
    out["definitions"] = md(["Company-definition requests (12 requests, 60 runs)"] + names,
                            [["Correct"] + [d[n]["correct"] for n in names], ["Result equals a naive variant of the request"] + [d[n]["naive_variant_applied"] for n in names]])
    o = results["override"]["cells"]
    out["override"] = md(["Override requests (4 requests, 20 runs)"] + names,
                         [["Correct (follows the request)"] + [o[n]["correct"] for n in names], ["Company default applied against the request"] + [o[n]["default_applied"] for n in names]])
    u = results["undocumented"]["cells"]
    rows = [["(a) repaired: the incident-free number"] + [u[n]["a_repaired"] for n in names],
            ["(b) published number, problem named in caveats (after adjudication)"] + [u[n]["b_flagged"] for n in names],
            ["(b) published number, keyword rule alone"] + [u[n]["b_flagged_strict_keywords_only"] for n in names],
            ["(c) published number, no usable warning"] + [u[n]["c_published_without_warning"] for n in names],
            ["Right under fix or flag, (a) + (b)"] + [u[n]["correct_total"] for n in names]]
    for rq in results["undocumented"]["requests"]:
        rows.append([f"{rq}: right (of 5)"] + [u[n]["by_request"][rq]["correct"] for n in names])
    out["undocumented"] = md(["Undocumented-issue requests (4 requests, 20 runs)"] + names, rows)
    t = results["tokens"]["cells"]
    out["tokens"] = md(["Agent tokens per run"] + names, [
        ["Median"] + [f"{t[n]['median']:,.0f}" for n in names], ["Quartiles"] + [f"{t[n]['p25']:,.0f} to {t[n]['p75']:,.0f}" for n in names],
        ["Range"] + [f"{t[n]['min']:,.0f} to {t[n]['max']:,.0f}" for n in names], ["Total, 300 runs"] + [f"{t[n]['total'] / 1e6:.1f}M" for n in names],
        ["Total tokens per correct run"] + [f"{t[n]['per_correct_answer']:,.0f}" for n in names],
        ["Median tool calls reported"] + [f"{t[n]['median_tool_calls_reported']:.0f}" for n in names], ["Median seconds"] + [f"{t[n]['median_duration_s']:.0f}" for n in names]])
    q = results["queries"]
    out["queries"] = md(["Counted queries per run (SQL and script calls)"] + names, [
        ["Mean"] + [f"{q[n]['mean']:.1f}" for n in names], ["Median"] + [f"{q[n]['median']:.0f}" for n in names], ["Most in one run"] + [q[n]["max"] for n in names],
        ["Runs that ran a library script"] + [q[n]["runs_with_a_script"] for n in names], ["Failed calls per run"] + [f"{q[n]['failed_calls_mean']:.2f}" for n in names]])
    s = results["skills"]
    lib = ["Sonnet L", "Sonnet L-", "Haiku L"]
    out["skills"] = md(["Library arms"] + lib, [
        ["Skills opened per run, mean (median, most)"] + [f"{s[n]['mean_skills_opened']:.1f} ({s[n]['median_skills_opened']:.0f}, {s[n]['max_skills_opened']})" for n in lib],
        ["Runs that opened more than 6 skills"] + [s[n]["runs_over_6_skills"] for n in lib],
        ["Library files read per run, mean (most)"] + [f"{s[n]['mean_library_files']:.1f} ({s[n]['max_library_files']})" for n in lib],
        ["Runs that opened the request-history digest"] + [s[n]["digest_opened"] for n in lib],
        ["Runs that ran a script"] + [s[n]["runs_with_script"] for n in lib],
        ["fiscal.py calls / query_check.py calls"] + [f"{s[n]['scripts_run'].get('fiscal-calendar/scripts/fiscal.py', 0)} / {s[n]['scripts_run'].get('query-check/scripts/query_check.py', 0)}" for n in lib]])
    skill_names = sorted({k for n in lib for k in s[n]["skill_open_counts"]}, key=lambda k: -s["Sonnet L"]["skill_open_counts"].get(k, 0))
    out["skill_opens"] = md(["Skill (runs of 300 that opened it)"] + lib, [[k] + [s[n]["skill_open_counts"].get(k, 0) for n in lib] for k in skill_names])
    b = results["budget"]
    out["budget"] = md(["Told up to"] + names, [["12 queries"] + [b["told_by_cell"][n]["told_12"] for n in names], ["30 queries"] + [b["told_by_cell"][n]["told_30"] for n in names],
                                              ["of which re-runs of capped runs"] + [b["told_by_cell"][n]["reruns_of_capped"] for n in names]])
    out["budget_sonnet_s"] = md(["Sonnet S", "Runs", "Correct", "Share", "Mean queries used"],
                                [[k, v["runs"], v["correct"], pct(v["share"]) if v["share"] is not None else "-", f"{v['mean_queries']:.1f}"] for k, v in b["sonnet_S_by_budget"].items()])
    pr = results["predictions"]
    out["predictions"] = md(["#", "Prediction", "Verdict", "The numbers"], [[p["n"], p["title"], "MET" if p["met"] else "NOT MET", p["numbers"]] for p in pr])
    rows = []
    for request_id in sorted(per_request):
        classes, pattern = specs_info[request_id]
        rows.append([request_id, ", ".join(classes), pattern] + [per_request[request_id][n] for n in names])
    out["per_request"] = md(["Request", "Trap classes", "Pattern"] + names, rows)
    led = json.loads((ANALYSIS / "leniency_ledger.json").read_text(encoding="utf-8"))
    desc = {"supporting_omitted": "Answer leaves out supporting measures the key does not require (the required-flag proposal)",
            "alternatives": "Result matches an alternative the key accepts (widened after the 15 Oct review)",
            "agent_rounding": "Column rounded to whole numbers or one decimal, each value correctly rounded",
            "month_long": "Months given in one column with a value column (REQ-T04)",
            "zero_rows": "Zero-filled padding row ignored", "totals": "Total row ignored", "names_for_ids": "Store or product name given instead of the ID",
            "fused_label": "Fiscal year fused with period, quarter or week in one label"}
    rows = [[desc[k], led[k]["correct_without"], led[k]["correct_with"] - led[k]["correct_without"]] for k in desc]
    rows.append(["All eight switched off", led["_all_off"]["correct_without"], led["_all_off"]["correct_with"] - led["_all_off"]["correct_without"]])
    out["ledger"] = md(["Leniency (switched off alone)", "Correct runs of 1,800 without it", "Runs that depend on it"], rows)
    return out


def main() -> int:
    results = json.loads((ANALYSIS / "results.json").read_text(encoding="utf-8"))
    import mark
    specs = mark.load_specs()
    specs_info = {r: (s.trap_classes, s.pattern) for r, s in specs.items()}
    tables = markdown_tables(results, results["correctness"]["per_request"], specs_info)
    (ANALYSIS / "tables.md").write_text("".join(f"<!-- table:{k} -->\n{v}\n\n" for k, v in tables.items()), encoding="utf-8")
    print(f"wrote {ANALYSIS / 'tables.md'} with {len(tables)} tables")
    return 0


if __name__ == "__main__":
    sys.exit(main())
