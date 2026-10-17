"""Propose a `required` flag for every measure of every key entry, for review. Does not touch key.json.

    python code/propose_required_flags.py

Why. The pilot diagnosis found that 6 of the pilot's 21 false fails were an answer that
gave the figure the request asks for and left out the supporting figures behind it (the two totals behind a growth rate, the sold
and returned amounts behind a return rate, the trading days and total behind a league table's per-day figure). 19 of the 60 key
entries carry more than one measure and the key does not say which is the answer. mark.py (Phase 6) needs that flag.

The rule, in the order it is applied to each measure of an entry:
  1. The only measure of an entry is required.
  2. A rate or growth measure (lfl_growth_pct; return_rate_pct) is required: it is the metric the request names.
     growth_pct is required only if the request says "growth" (a request for net sales "against last year" that does not ask for
     growth gets the two sales columns).
  3. The two sales columns of a year-on-year pair (net_sales_ty, net_sales_ly) are required if the request asks for sales set against
     another period ("net sales ... against", "compared with", "alongside", "next to") and not merely for a like-for-like or growth figure.
  4. The amounts behind a rate (sold_net, returned_net) and the trading days and total behind a per-trading-day ranking are
     supporting: not required, but an answer that carries them is fine.
  5. Measures a request lists one by one (the two months of a VAT request, the three figures of an uplift request, "net sales and
     gross margin percentage", the members and the spend) are all required.
Each decision carries the words of the request that decided it. Dimensions keyed on an ID (store_id, sku, campaign_id) are listed
with `accept_name_or_id`: mark.py should accept the name instead of, or beside, the ID (the new task rule asks for names).
Entries whose measures are listed in separate columns by month are listed under `wide_months`: an answer with a month column
and one value column carries the same numbers.

Output: data/key/required_flags_proposal.json and data/key/required_flags_proposal.md (the md is for reading; both are generated).
Both stay in data/key/ so they are locked with the key. Nothing here edits key.json.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as cfg                      # noqa: E402

ID_DIMENSIONS = {"store_id", "sku", "campaign_id", "member_id"}
RATE_MEASURES = {"lfl_growth_pct", "return_rate_pct", "gross_margin_pct"}
AMOUNTS_BEHIND_A_RATE = {"sold_net", "returned_net"}
PER_DAY_MEASURE = "net_sales_per_trading_day"
SUPPORT_FOR_PER_DAY = {"trading_days", "net_sales"}


def decide(entry: dict) -> list:
    """[{name, required, why}] for each measure of one key entry, by the rule in the module docstring."""
    text = entry["request_text"].lower()
    measures = [column["name"] for column in entry["columns"] if column["role"] == "measure"]
    decisions = []
    for name in measures:
        if len(measures) == 1:
            required, why = True, "the only measure"
        elif name == "growth_pct":
            hit = re.search(r"growth", text)
            required = bool(hit)
            why = f"the request says '{hit.group(0)}'" if hit else "the request does not ask for growth"
        elif name in RATE_MEASURES and name != "gross_margin_pct":
            required, why = True, "the rate is the metric the request names"
        elif name in ("net_sales_ty", "net_sales_ly"):
            hit = re.search(r"sales[^.?]*?(against|compared|alongside|next to)|(against|compared|alongside|next to)[^.?]*?sales", text)
            required = bool(hit)
            why = ("the request asks for sales set against another period" if hit
                   else "the request asks for the LFL or growth figure, not for the two sales totals")
        elif name in AMOUNTS_BEHIND_A_RATE:
            required, why = False, "the amount behind the rate; the request asks for the rate"
        elif PER_DAY_MEASURE in measures and name in SUPPORT_FOR_PER_DAY:
            required, why = False, "behind the per-trading-day figure that ranks the table"
        elif name == PER_DAY_MEASURE:
            required, why = True, "the league-table metric"
        else:
            required, why = True, "listed by the request (several measures asked for)"
        decisions.append({"name": name, "required": required, "why": why})
    return decisions


def build_proposal(key: dict) -> dict:
    entries = []
    for entry in key["entries"]:
        decisions = decide(entry)
        dimensions = [column["name"] for column in entry["columns"] if column["role"] == "dimension"]
        wide = [d["name"] for d in decisions if re.search(r"_(aug|sep)_\d{4}$", d["name"])]
        entries.append({
            "request_id": entry["request_id"], "request_text": entry["request_text"], "dimensions": dimensions,
            "accept_name_or_id": [name for name in dimensions if name in ID_DIMENSIONS],
            "wide_months": wide or None, "measures": decisions,
            "supporting": [d["name"] for d in decisions if not d["required"]],
            "multi_measure": len(decisions) > 1,
        })
    multi = [e for e in entries if e["multi_measure"]]
    return {
        "status": "PROPOSAL for review. key.json is unchanged; nothing reads this file yet.",
        "rule": "see the docstring of code/propose_required_flags.py",
        "entries_total": len(entries), "entries_with_more_than_one_measure": len(multi),
        "entries_with_supporting_measures": sum(1 for e in entries if e["supporting"]),
        "entries": entries,
    }


def build_markdown(proposal: dict) -> str:
    lines = ["# Proposed `required` flags for the answer key", "",
             "A proposal, not a change: `key.json` is untouched. For each request that asks for more than one figure, which figures an answer "
             "must carry (**required**) and which are supporting (an answer may leave them out; carrying them is fine). "
             "Read the 'why' column: it quotes what the request says.", "",
             f"{proposal['entries_with_more_than_one_measure']} of {proposal['entries_total']} requests have more than one measure; "
             f"{proposal['entries_with_supporting_measures']} of them have at least one supporting measure.", ""]
    for entry in proposal["entries"]:
        if not entry["multi_measure"]:
            continue
        lines += [f"## {entry['request_id']}", "", f"> {entry['request_text']}", ""]
        lines += ["| Figure | Required | Why |", "|---|---|---|"]
        for measure in entry["measures"]:
            lines.append(f"| `{measure['name']}` | {'yes' if measure['required'] else 'no (supporting)'} | {measure['why']} |")
        extras = []
        if entry["accept_name_or_id"]:
            extras.append("rows keyed on " + ", ".join(f"`{n}`" for n in entry["accept_name_or_id"]) + ": accept the name instead of, or beside, the ID")
        if entry["wide_months"]:
            extras.append("months are separate columns: accept a month column with one value column")
        if extras:
            lines += ["", "; ".join(extras) + "."]
        lines.append("")
    single = [e for e in proposal["entries"] if not e["multi_measure"] and (e["accept_name_or_id"])]
    if single:
        lines += ["## Single-measure requests keyed on an ID", "",
                  "Required is the one measure. mark.py should accept the name instead of, or beside, the ID for: "
                  + ", ".join(e["request_id"] for e in single) + ".", ""]
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    key_path = cfg.KEY_DIR / "key.json"
    if not key_path.is_file():
        print(f"{key_path} not found. If the case is locked, unlock it first (python code/lock_answers.py unlock).")
        return 1
    key = json.loads(key_path.read_text(encoding="utf-8"))
    proposal = build_proposal(key)
    json_path, md_path = cfg.KEY_DIR / "required_flags_proposal.json", cfg.KEY_DIR / "required_flags_proposal.md"
    for target in (json_path, md_path):
        if target.resolve() == key_path.resolve():
            raise SystemExit("Refusing to overwrite key.json.")
    json_path.write_text(json.dumps(proposal, indent=1, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(build_markdown(proposal), encoding="utf-8")
    print(f"{proposal['entries_with_more_than_one_measure']} multi-measure entries of {proposal['entries_total']}; "
          f"{proposal['entries_with_supporting_measures']} with supporting measures.")
    print(f"Written: {json_path}\n         {md_path}\nkey.json was not touched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
