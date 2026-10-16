"""Pipeline tooling — accept one stream batch's extraction agent
output.

For batch N:
  1. For each contract with a non-empty question list, parses the expected
     `out/<stem>.extraction.json`, validates it (schema shape restricted to
     the asked categories, every span verbatim in the contract text). Any
     failure REJECTS that file (listed with reasons) — the whole batch is
     not accepted until every file passes; retries are the caller's call,
     recorded via `--retries K` when re-dispatching.
  2. On full-batch acceptance: non-shadow answers are appended to the
     accepted-extraction store; shadow answers are appended separately and
     compared against the corresponding matcher answer — any disagreement
     demotes that matcher immediately (permanent for the run).
  3. Updates the read count (contracts read + retries) and refuses if this
     would exceed config.READ_CAP.
  4. Prints commissioning candidates: categories crossing the induction
     trigger (no matcher yet, >= N_INDUCTION accepted positives) with their
     positive/negative counts and the trust grade they would qualify for.

Pipeline-facing: never references the derived key or its CSV source
(validate_corpus.py rule 10).

Run: `python accept_batch.py --batch N [--retries K]`. Exits 1 on rejection
or any hard failure; 0 on acceptance.
"""

from __future__ import annotations

import argparse

import pipeline_common as pc
import schemas
import config


def _load_batch_questions(paths: pc.Paths, batch_number: int) -> tuple[dict, dict]:
    batch_dir = paths.batches_dir / f"batch_{batch_number:02d}"
    if not batch_dir.exists():
        pc.fail(f"batch folder not found: {batch_dir} — run prepare_batch.py --batch {batch_number} first.")
    questions_path = batch_dir / "questions.json"
    if not questions_path.exists():
        pc.fail(f"questions.json not found in {batch_dir}")
    return batch_dir, pc.read_json(questions_path)


def _validate_output_file(paths: pc.Paths, batch_dir, contract: str, asked: list[str]) -> tuple[dict | None, list[str]]:
    """Returns (record or None, errors). record is None iff errors is
    non-empty (a rejected file)."""
    stem = contract[:-4] if contract.lower().endswith(".txt") else contract
    out_path = batch_dir / "out" / f"{stem}.extraction.json"
    if not out_path.exists():
        return None, [f"missing output file: {out_path}"]
    try:
        rec = pc.read_json_soft(out_path)
    except Exception as exc:  # pragma: no cover - read_json_soft raises ValueError itself
        return None, [f"could not read/parse {out_path}: {exc}"]
    errors = list(schemas.validate_record(rec, asked))
    text = pc.read_contract_text(paths, contract)
    text_norm = schemas.norm_ws(text)
    for category in asked:
        entry = rec.get("categories", {}).get(category, {})
        for span in entry.get("spans", []) or []:
            if not isinstance(span, str):
                continue
            if schemas.norm_ws(span) not in text_norm:
                errors.append(f"{category}: span not verbatim in contract text: {span!r}")
    return (rec, []) if not errors else (None, errors)


def accept_batch(paths: pc.Paths, batch_number: int, retries: int = 0) -> dict:
    manifest = pc.load_manifest(paths)
    state = pc.load_matcher_state(paths)

    if batch_number != state["last_accepted_batch"] + 1:
        pc.fail(
            f"sequential discipline: batch {batch_number} requested but "
            f"last accepted batch is {state['last_accepted_batch']} "
            f"(expected batch {state['last_accepted_batch'] + 1} next)."
        )

    batch_dir, questions_doc = _load_batch_questions(paths, batch_number)
    contracts = pc.batch_contracts(manifest, batch_number)
    doc_contracts = set(questions_doc["contracts"].keys())
    if set(contracts) != doc_contracts:
        pc.fail(
            f"batch {batch_number}: questions.json contracts do not match the "
            f"manifest's batch membership.\n  manifest: {sorted(contracts)}\n  "
            f"questions.json: {sorted(doc_contracts)}"
        )

    shadow_map = questions_doc.get("shadow", {})
    rejects: list[tuple[str, list[str]]] = []
    accepted_records: dict[str, dict] = {}
    llm_read_contracts = []

    for contract in contracts:
        asked = questions_doc["contracts"][contract]["questions"]
        if not asked:
            continue  # no LLM read needed this batch (fully matcher-covered)
        llm_read_contracts.append(contract)
        record, errors = _validate_output_file(paths, batch_dir, contract, asked)
        if errors:
            rejects.append((contract, errors))
        else:
            accepted_records[contract] = record

    if rejects:
        print(f"BATCH {batch_number} NOT ACCEPTED — {len(rejects)} file(s) rejected:")
        for contract, errors in rejects:
            print(f"  REJECTED {contract}:")
            for e in errors:
                print(f"    - {e}")
        pc.fail(
            f"batch {batch_number} has {len(rejects)} rejected file(s); fix/retry the "
            f"extraction and re-run accept_batch.py (use --retries K to record the cost)."
        )

    new_reads = len(llm_read_contracts) + retries
    if pc.read_cap_exceeded(state, new_reads):
        pc.fail(
            f"accepting batch {batch_number} ({new_reads} reads: "
            f"{len(llm_read_contracts)} contracts + {retries} retries) would push the "
            f"total read count from {state['read_count']} past config.READ_CAP = "
            f"{config.READ_CAP}."
        )

    # Split shadow vs non-shadow, write both stores, and run the shadow
    # regression comparison against the matcher's own answer.
    shadow_comparisons = []
    demotions = []
    for contract, record in accepted_records.items():
        shadow_cats = shadow_map.get(contract, [])
        asked = questions_doc["contracts"][contract]["questions"]
        non_shadow_cats = [c for c in asked if c not in shadow_cats]
        non_shadow_subset = {c: record["categories"][c] for c in non_shadow_cats}
        pc.merge_llm_extraction(paths, contract, non_shadow_subset)

        for category in shadow_cats:
            llm_entry = record["categories"][category]
            matcher_record = pc.load_matcher_output(paths, contract)
            matcher_entry = (matcher_record or {}).get("categories", {}).get(category)
            shadow_record = {
                "contract": contract,
                "batch": batch_number,
                "category": category,
                "llm_answer": llm_entry,
                "matcher_answer": matcher_entry,
            }
            if matcher_entry is None:
                # By construction (pipeline_common.assign_shadow_categories
                # only assigns a shadow to a (contract, category) pair where
                # the matcher already recorded a real answer this batch),
                # this is now an impossible state. Fail loud rather than
                # silently comparing the LLM's shadow answer against
                # nothing — silence here would hide a regression of that
                # eligibility fix (the batch-2 prep gap, 3 Jul 2026).
                pc.fail(
                    f"shadow category {category!r} for {contract!r} has no matcher output on "
                    f"record this batch — impossible by construction (shadow assignment must "
                    f"only ever target a (contract, category) pair the matcher already answered "
                    f"this batch); this indicates a bug in prepare_batch.py's shadow assignment."
                )
            comparison = schemas.compare_category(category, llm_entry, matcher_entry)
            shadow_record["agree"] = comparison["match"]
            shadow_record["axis"] = comparison["axis"]
            shadow_record["detail"] = comparison["detail"]
            shadow_comparisons.append(shadow_record)
            if not comparison["match"]:
                reason = (
                    f"shadow regression disagreement on {contract}: "
                    f"matcher={matcher_entry} llm-shadow={llm_entry} ({comparison['detail']})"
                )
                pc.demote_category(state, category, batch_number, reason)
                print(f"DEMOTION (shadow disagreement)  {category}: {reason}")
                demotions.append((category, contract, comparison["detail"]))

    _append_shadow_answers(paths, shadow_comparisons)

    pc.record_reads(state, batch_number, len(llm_read_contracts), retries)
    state["last_accepted_batch"] = batch_number
    pc.save_matcher_state(paths, state)

    candidates = _commissioning_candidates(paths, state)

    return {
        "batch": batch_number,
        "accepted_contracts": sorted(accepted_records.keys()),
        "llm_read_contracts": llm_read_contracts,
        "reads_this_batch": len(llm_read_contracts),
        "retries": retries,
        "total_read_count": state["read_count"],
        "shadow_comparisons": shadow_comparisons,
        "demotions": demotions,
        "commissioning_candidates": candidates,
    }


def _append_shadow_answers(paths: pc.Paths, shadow_comparisons: list[dict]) -> None:
    if not shadow_comparisons:
        return
    existing = pc.read_json(paths.shadow_answers_path) if paths.shadow_answers_path.exists() else {"entries": []}
    existing.setdefault("entries", []).extend(shadow_comparisons)
    pc.write_json(paths.shadow_answers_path, existing)


def _commissioning_candidates(paths: pc.Paths, state: dict) -> list[dict]:
    """Categories with no matcher yet (status == 'none') that have crossed
    the induction trigger, with the trust grade they would qualify for."""
    candidates = []
    for category in schemas.CATEGORY_NAMES:
        info = state["categories"][category]
        if info["status"] != "none":
            continue
        positives, negatives = pc.category_accept_counts(paths, category)
        if positives >= config.N_INDUCTION:
            kind = schemas.KIND[category]
            trust = pc.trust_grade_for_commissioning(kind, negatives if kind == "extraction" else 0)
            candidates.append({
                "category": category,
                "positives": positives,
                "negatives": negatives,
                "trust_grade": trust,
            })
    return candidates


def print_summary(summary: dict) -> None:
    pc.announce(f"Batch {summary['batch']} accepted")
    print(f"Contracts read by the LLM this batch: {summary['reads_this_batch']} "
          f"(+ {summary['retries']} retries) -> total read count {summary['total_read_count']} "
          f"/ {config.READ_CAP}")
    print(f"Accepted contracts: {summary['accepted_contracts']}")

    if summary["shadow_comparisons"]:
        print(f"\nShadow comparisons this batch: {len(summary['shadow_comparisons'])}")
        for sc in summary["shadow_comparisons"]:
            flag = "AGREE" if sc["agree"] else "DISAGREE"
            print(f"  {flag}  {sc['category']} / {sc['contract']}: {sc['detail']}")
    else:
        print("\nShadow comparisons this batch: none")

    if summary["demotions"]:
        print(f"\nDemotions (shadow disagreement): {len(summary['demotions'])}")
        for category, contract, detail in summary["demotions"]:
            print(f"  {category} (triggered by {contract}): {detail}")
    else:
        print("\nDemotions (shadow disagreement): none")

    if summary["commissioning_candidates"]:
        print(f"\nCommissioning candidates ({len(summary['commissioning_candidates'])}):")
        for c in summary["commissioning_candidates"]:
            print(f"  {c['category']:28s} positives={c['positives']:3d} "
                  f"negatives={c['negatives']:3d} trust_grade={c['trust_grade']}")
    else:
        print("\nCommissioning candidates: none")


def main() -> None:
    parser = argparse.ArgumentParser(description="Accept one stream batch's extraction agent output.")
    parser.add_argument("--batch", type=int, required=True, help="1-indexed batch number (1-8)")
    parser.add_argument("--retries", type=int, default=0, help="extra reads spent on rejected/re-dispatched files")
    args = parser.parse_args()

    paths = pc.default_paths()
    pc.assert_safe_output_paths(paths)

    summary = accept_batch(paths, args.batch, retries=args.retries)
    print_summary(summary)
    print("\naccept_batch.py completed successfully.")


if __name__ == "__main__":
    main()
