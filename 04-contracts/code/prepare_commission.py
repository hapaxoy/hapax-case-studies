"""Pipeline tooling — build one category's overseer commission
folder.

Builds `data/runs/commissions/<slug>/`:
  induction/    one JSON per induction contract: that category's accepted
                extraction alone (present/spans/answer) plus the contract
                name — never the full 12-category record, and never
                anything from the derived key.
  contracts/    the corresponding TXT copies (accepted positives; for a
                two-sided commission, also the accepted negatives).
  commission.json   category, slug, trust grade, target matcher path,
                     induction contract lists, commission id.

Refuses if a matcher file already exists for the category or if the category has not crossed the
induction trigger (config.N_INDUCTION accepted positives).

Pipeline-facing: reads only the accepted-extraction store this run has
built up (data/runs/llm_extractions/) and contract texts — never the
derived key or its CSV source (validate_corpus.py rule 10).

Run: `python prepare_commission.py --category "Governing Law"`.
"""

from __future__ import annotations

import argparse
import shutil

import config
import pipeline_common as pc
import schemas


def prepare_commission(paths: pc.Paths, category: str) -> dict:
    if category not in schemas.CATEGORY_NAMES:
        pc.fail(f"unknown category: {category!r}. Must be one of {schemas.CATEGORY_NAMES}")

    matcher_path = pc.matcher_path_for(paths, category)
    if matcher_path.exists():
        pc.fail(f"a matcher already exists for {category!r}: {matcher_path} "
                f"— prepare_commission.py refuses to overwrite an existing commission.")

    state = pc.load_matcher_state(paths)
    kind = schemas.KIND[category]

    all_records = pc.load_all_llm_extractions(paths)
    positives, negatives = [], []
    for contract, record in all_records.items():
        entry = record.get("categories", {}).get(category)
        if entry is None:
            continue
        (positives if entry.get("present") else negatives).append(contract)
    positives.sort()
    negatives.sort()

    if len(positives) < config.N_INDUCTION:
        pc.fail(
            f"category {category!r} has {len(positives)} accepted positives; needs "
            f">= config.N_INDUCTION = {config.N_INDUCTION} before it can be commissioned."
        )

    trust = pc.trust_grade_for_commissioning(kind, len(negatives) if kind == "extraction" else 0)
    induction_negatives = negatives if trust == "two-sided" else []
    induction_all = sorted(positives + induction_negatives)

    slug = pc.slugify(category)
    commission_id = pc.next_commission_id(paths, category)
    commission_dir = paths.commissions_dir / slug
    induction_dir = commission_dir / "induction"
    contracts_out_dir = commission_dir / "contracts"
    induction_dir.mkdir(parents=True, exist_ok=True)
    contracts_out_dir.mkdir(parents=True, exist_ok=True)

    for contract in induction_all:
        entry = all_records[contract]["categories"][category]
        stem = contract[:-4] if contract.lower().endswith(".txt") else contract
        pc.write_json(induction_dir / f"{stem}.json", {
            "contract": contract,
            "category": category,
            "present": entry["present"],
            "spans": entry["spans"],
            "answer": entry.get("answer"),
        })
        shutil.copyfile(paths.contracts_dir / contract, contracts_out_dir / contract)

    target_matcher_relpath = f"code/matchers_generated/matcher_{slug}.py"
    commission_doc = {
        "id": commission_id,
        "category": category,
        "slug": slug,
        "trust": trust,
        "target_matcher_path": target_matcher_relpath,
        "induction": {
            "positives": positives,
            "negatives": induction_negatives,
            "all": induction_all,
        },
    }
    pc.write_json(commission_dir / "commission.json", commission_doc)

    info = state["categories"][category]
    info["status"] = "commissioned"
    info["trust"] = trust
    info["matcher_id"] = commission_id
    info["matcher_path"] = target_matcher_relpath
    info["commissioned_at_batch"] = state["last_accepted_batch"]
    pc.record_history(
        state, category, state["last_accepted_batch"], "commissioned",
        f"{commission_id}: {len(positives)} positives, {len(induction_negatives)} "
        f"negatives, trust={trust}",
    )
    pc.save_matcher_state(paths, state)

    return {
        "category": category,
        "slug": slug,
        "commission_id": commission_id,
        "trust": trust,
        "positives": positives,
        "negatives": negatives,
        "induction_negatives_included": induction_negatives,
        "commission_dir": str(commission_dir),
        "target_matcher_path": target_matcher_relpath,
    }


def print_summary(summary: dict) -> None:
    pc.announce(f"Commission built: {summary['commission_id']}")
    print(f"Category:            {summary['category']}")
    print(f"Trust grade:         {summary['trust']}")
    print(f"Accepted positives:  {len(summary['positives'])}")
    print(f"Accepted negatives:  {len(summary['negatives'])} "
          f"(included in induction: {len(summary['induction_negatives_included'])})")
    print(f"Commission folder:   {summary['commission_dir']}")
    print(f"Target matcher path: {summary['target_matcher_path']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build one category's overseer commission folder.")
    parser.add_argument("--category", required=True, help="exact category name, e.g. 'Governing Law'")
    args = parser.parse_args()

    paths = pc.default_paths()
    pc.assert_safe_output_paths(paths)

    summary = prepare_commission(paths, args.category)
    print_summary(summary)
    print("\nprepare_commission.py completed successfully.")


if __name__ == "__main__":
    main()
