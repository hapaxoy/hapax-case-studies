"""Pipeline tooling — deterministic replay of the whole stream.

For each of the 50 stream contracts, in order, resolves per category which
path answered it (matcher / llm-discovery / llm-fallback / the llm-shadow
overlay), reading only what prepare_batch.py / accept_batch.py /
regression_gate.py already recorded — this script never re-derives an
answer, it only assembles and cross-checks. Consistency checks enforced:
  - every category of every stream contract is answered EXACTLY ONCE on
    the primary path (matcher XOR llm);
  - a matcher answer's batch falls within that category's active window
    (>= active_from_batch, and before any later demotion);
  - every declared shadow assignment has a recorded shadow answer, and
    targets a category that did have an active matcher on record;
  - the total read count matches `data/runs/extract_agent_log.json` when
    that log exists (it is written by the human orchestrator at run time,
    not by any script in this repo, so its absence during pipeline-tooling
    development is expected and only skips this one check).

Any consistency failure stops the script before writing anything (fail
loud) — `data/runs/stream_events.json` is only ever written once, for a
stream that passed every check. This file is the interactive page's data
source.

Pipeline-facing: never references the derived key (validate_corpus.py rule
10) — every input here is the manifest, run-state, and the stores this
run's own tooling built.

Run: `python router.py`.
"""

from __future__ import annotations

import pipeline_common as pc
import schemas


def build_stream_events(paths: pc.Paths) -> dict:
    manifest = pc.load_manifest(paths)
    stream = pc.stream_contracts(manifest)
    contract_batch = pc.contract_batch_map(manifest)
    state = pc.load_matcher_state(paths)

    errors: list[str] = []

    questions_by_batch: dict[int, dict] = {}
    for batch_number in range(1, len(pc.BATCH_SIZES) + 1):
        qpath = paths.batches_dir / f"batch_{batch_number:02d}" / "questions.json"
        if qpath.exists():
            questions_by_batch[batch_number] = pc.read_json(qpath)

    shadow_doc = pc.read_json(paths.shadow_answers_path) if paths.shadow_answers_path.exists() else {"entries": []}
    shadow_lookup = {(e["contract"], e["category"]): e for e in shadow_doc.get("entries", [])}

    records: dict[str, dict] = {}

    for contract in stream:
        batch_number = contract_batch.get(contract)
        if batch_number is None:
            errors.append(f"{contract}: not found in any batch's stream membership")
            continue
        qdoc = questions_by_batch.get(batch_number)
        if qdoc is None:
            errors.append(f"{contract}: batch {batch_number}'s questions.json not found (has it been prepared?)")
            continue
        contract_q = qdoc["contracts"].get(contract)
        if contract_q is None:
            errors.append(f"{contract}: not present in batch {batch_number}'s questions.json")
            continue
        reasons = contract_q.get("reasons", {})
        shadow_cats = qdoc.get("shadow", {}).get(contract, [])

        matcher_out = pc.load_matcher_output(paths, contract) or {"categories": {}}
        llm_out = pc.load_llm_extraction(paths, contract) or {"categories": {}}

        record_categories: dict[str, dict] = {}
        for category in schemas.CATEGORY_NAMES:
            in_matcher = category in matcher_out.get("categories", {})
            in_llm = category in llm_out.get("categories", {})
            sources = [s for s, present in (("matcher", in_matcher), ("llm", in_llm)) if present]

            if len(sources) == 0:
                errors.append(f"{contract} / {category}: unanswered on the primary path")
                continue
            if len(sources) > 1:
                errors.append(f"{contract} / {category}: answered on multiple primary paths: {sources}")
                continue

            if sources[0] == "matcher":
                entry = dict(matcher_out["categories"][category])
                entry["path"] = "matcher"
                info = state["categories"][category]
                if info.get("active_from_batch") is None or batch_number < info["active_from_batch"]:
                    errors.append(
                        f"{contract} / {category}: matcher answer recorded but batch {batch_number} "
                        f"precedes active_from_batch={info.get('active_from_batch')}"
                    )
                # Demotion happens at batch-N ACCEPT time; matcher answers made
                # at batch-N PREP time legitimately stand (the pinned trust-then-
                # verify semantics: past damage stays visible and counted). Only
                # answers in LATER batches violate the window.
                if info.get("demoted_at_batch") is not None and batch_number > info["demoted_at_batch"]:
                    errors.append(
                        f"{contract} / {category}: matcher answer recorded in batch {batch_number} "
                        f"but the category was demoted at batch {info['demoted_at_batch']}"
                    )
            else:
                entry = dict(llm_out["categories"][category])
                reason = reasons.get(category)
                if reason == "no-match":
                    entry["path"] = "llm-fallback"
                elif reason == "no-matcher":
                    entry["path"] = "llm-discovery"
                else:
                    errors.append(f"{contract} / {category}: LLM answer with unrecognised reason {reason!r}")
                    entry["path"] = "llm-unknown"
            record_categories[category] = entry

        shadow_overlay: dict[str, dict] = {}
        for category in shadow_cats:
            se = shadow_lookup.get((contract, category))
            if se is None:
                errors.append(f"{contract} / {category}: declared shadow in batch {batch_number} but no shadow answer recorded")
                continue
            if category not in matcher_out.get("categories", {}):
                errors.append(
                    f"{contract} / {category}: shadow-assigned but no matcher output on record "
                    f"(shadow must only ever target an active category)"
                )
            shadow_overlay[category] = {
                "llm_answer": se["llm_answer"],
                "matcher_answer": se["matcher_answer"],
                "agree": se["agree"],
                "axis": se["axis"],
                "detail": se["detail"],
            }

        records[contract] = {"batch": batch_number, "categories": record_categories, "shadow": shadow_overlay}

    batches_info = []
    for batch_number in sorted(questions_by_batch.keys()):
        qdoc = questions_by_batch[batch_number]
        contracts_in_batch = sorted(qdoc["contracts"].keys())
        scope_sizes = {c: len(qdoc["contracts"][c]["questions"]) for c in contracts_in_batch}
        reads = sum(1 for c in contracts_in_batch if qdoc["contracts"][c]["questions"])
        batches_info.append({
            "batch": batch_number,
            "contracts": contracts_in_batch,
            "scope_sizes": scope_sizes,
            "reads": reads,
            "shadow": qdoc.get("shadow", {}),
            "dropped_shadows": qdoc.get("dropped_shadows", []),
        })

    # lifecycle keys are written only by the code path that sets them
    # (gate failure writes failed_at_batch, demotion writes demoted_at_batch,
    # ...), so read every optional key defensively.
    lifecycle = {
        category: {
            "status": info["status"],
            "trust": info.get("trust"),
            "matcher_id": info.get("matcher_id"),
            "commissioned_at_batch": info.get("commissioned_at_batch"),
            "active_from_batch": info.get("active_from_batch"),
            "failed_at_batch": info.get("failed_at_batch"),
            "demoted_at_batch": info.get("demoted_at_batch"),
            "demotion_reason": info.get("demotion_reason"),
            "history": info.get("history", []),
        }
        for category, info in state["categories"].items()
    }

    read_count_check = {"checked": False, "note": None, "agent_log_total": None, "state_total": state["read_count"]}
    if paths.extract_agent_log_path.exists():
        try:
            log_doc = pc.read_json_soft(paths.extract_agent_log_path)
        except (ValueError, OSError) as exc:
            read_count_check["note"] = f"extract_agent_log.json present but unreadable: {exc}"
        else:
            log_total = log_doc.get("total_reads")
            if log_total is None and "batches" in log_doc:
                log_total = sum(b.get("reads", 0) + b.get("retries", 0) for b in log_doc["batches"])
            if log_total is None:
                read_count_check["note"] = "extract_agent_log.json present but no recognised total-reads field"
            else:
                read_count_check["checked"] = True
                read_count_check["agent_log_total"] = log_total
                if log_total != state["read_count"]:
                    errors.append(
                        f"read count mismatch: extract_agent_log.json records {log_total}, "
                        f"matcher_state.json records {state['read_count']}"
                    )
    else:
        read_count_check["note"] = "extract_agent_log.json not found — read-count cross-check skipped"

    return {
        "batches": batches_info,
        "records": records,
        "matcher_lifecycle": lifecycle,
        "read_count_check": read_count_check,
        "total_read_count": state["read_count"],
        "consistency_errors": errors,
    }


def print_summary(result: dict) -> None:
    pc.announce("Router: stream replay summary")
    for b in result["batches"]:
        print(f"  batch {b['batch']:2d}: {len(b['contracts'])} contracts, {b['reads']} reads, "
              f"shadow on {len(b['shadow'])} contract(s)")
    print(f"\nTotal read count (matcher_state.json): {result['total_read_count']}")
    rc = result["read_count_check"]
    if rc["checked"]:
        print(f"Agent-log cross-check: agent log={rc['agent_log_total']} state={rc['state_total']} "
              f"{'OK' if rc['agent_log_total'] == rc['state_total'] else 'MISMATCH'}")
    else:
        print(f"Agent-log cross-check: {rc['note']}")

    print("\nMatcher lifecycle:")
    for category, info in sorted(result["matcher_lifecycle"].items()):
        print(f"  {category:28s} status={info['status']:12s} trust={info['trust']}")

    agree = sum(1 for r in result["records"].values() for s in r["shadow"].values() if s["agree"])
    disagree = sum(1 for r in result["records"].values() for s in r["shadow"].values() if not s["agree"])
    print(f"\nShadow overlay: {agree} agree, {disagree} disagree (never merged into the scored path)")


def main() -> None:
    paths = pc.default_paths()
    pc.assert_safe_output_paths(paths)

    result = build_stream_events(paths)
    if result["consistency_errors"]:
        pc.announce("Router consistency check FAILED")
        for e in result["consistency_errors"]:
            print(f"  - {e}")
        pc.fail(f"{len(result['consistency_errors'])} consistency error(s) found; stream_events.json NOT written.")

    pc.write_json(paths.stream_events_path, result)
    print_summary(result)
    print(f"\nWrote {paths.stream_events_path}")
    print("router.py completed successfully.")


if __name__ == "__main__":
    main()
