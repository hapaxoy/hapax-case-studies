"""Phase 3 checks on the request set and the answer key (rules 12 to 15, plus the Phase 3 brief).

Called by validate_data.py (run(connection, record)). It re-proves the key from scratch rather than trusting data/key/:
every question is evaluated again (reference SQL on the warehouse, pandas recomputation from the generator's own
tables, naive variants), and the stored key must equal the fresh result.

  Rule 12  every reference query runs, returns rows, and equals the independent pandas recomputation
  Rule 13  every trapped request has naive variants that bite (differ by more than 10 x tolerance, or change the rows
           or order of a top-N); clean requests have none and their sloppy variants still give the reference result
  Rule 14  paraphrase twins have identical reference results
  Rule 15  ambiguous requests have at least two accepted readings with different results and a keyword rule
  K        set composition, trap-class counts, wording fidelity, no leak from the dev history, undocumented-issue
           requests with their two accepted outcomes, and the key kept out of world/
"""
from __future__ import annotations

import json
import re
from collections import Counter

import duckdb
import pandas as pd

import build_requests
import config as cfg
import dev_requests
from key_lib import compare_tables, keyword_rule_match
from key_runner import evaluate_all, load_briefs


def frame_from_table(table: dict) -> pd.DataFrame:
    return pd.DataFrame(table["rows"], columns=table["columns"])


def fingerprint(frame: pd.DataFrame) -> tuple:
    values = []
    for column in frame.columns:
        if pd.api.types.is_numeric_dtype(frame[column]):
            values += [round(float(v), 2) for v in frame[column].dropna()]
    return tuple(sorted(values))


def run(connection, record) -> None:
    print("Key: the request set and the answer key (rules 12 to 15)")
    key_path = cfg.KEY_DIR / "key.json"
    requests_path = cfg.REQUESTS_DIR / "test_requests.json"
    if not (key_path.exists() and requests_path.exists()):
        record("K0", "request set and key exist (run build_requests.py and build_key.py)", False, "missing files")
        return
    briefs = load_briefs()
    requests = {r["id"]: r for r in json.loads(requests_path.read_text(encoding="utf-8"))}
    key = json.loads(key_path.read_text(encoding="utf-8"))
    entries = {e["request_id"]: e for e in key["entries"]}

    # ---- composition -------------------------------------------------------------------------------------
    ids = [b["id"] for b in briefs]
    record("K1", "60 test requests with unique IDs, one brief, one wording and one key entry each",
           len(ids) == cfg.N_TEST_REQUESTS == len(set(ids)) and set(ids) == set(requests) == set(entries), f"{len(ids)} requests")
    patterns = Counter(b["pattern"] for b in briefs)
    record("K1", "all 14 patterns appear, in the planned counts", set(patterns) == set(range(1, 15)) and dict(patterns) == cfg.TEST_PATTERN_COUNTS, str(dict(sorted(patterns.items()))))
    novel = sum(patterns[p] for p in cfg.TEST_NOVEL_PATTERNS)
    record("K1", "patterns 9, 10, 13 and 14 (absent from the dev history) carry the novel requests", novel >= 11 and all(patterns[p] >= 3 for p in cfg.TEST_NOVEL_PATTERNS), f"{novel} novel requests")
    twin_groups = Counter(b["twin"] for b in briefs if b["twin"])
    record("K1", "10 paraphrase pairs (20 requests), each pair from two departments", len(twin_groups) == cfg.N_PARAPHRASE_PAIRS and set(twin_groups.values()) == {2}
           and all(len({b["department"] for b in briefs if b["twin"] == t}) == 2 for t in twin_groups), f"{len(twin_groups)} pairs")
    record("K1", "requests arrive in the week after the data cut", all(requests[i]["received"] in {d.isoformat() for d in cfg.TEST_RECEIVED_DATES} for i in ids))

    # ---- wording fidelity and leaks -------------------------------------------------------------------------
    bad = {b["id"]: build_requests.check_text(b, requests[b["id"]]["request_text"]) for b in briefs}
    bad = {k: v for k, v in bad.items() if v}
    record("K2", "every wording contains what its brief requires and none of the words that would resolve a trap", not bad, str(bad)[:300])
    dev_texts = [r["request_text"] for r in dev_requests.DEV_REQUESTS]
    worst = max(max(build_requests.overlap(requests[i]["request_text"], d) for d in dev_texts) for i in ids)
    record("K2", "no test request repeats a dev request (3-gram overlap under the threshold)", worst <= cfg.DEV_NGRAM_LEAK_THRESHOLD, f"worst {worst:.0%}")
    record("K2", "request texts are all different", len({requests[i]["request_text"].lower() for i in ids}) == len(ids))

    # ---- the key stays out of world/ ----------------------------------------------------------------------------
    world_text = "\n".join(p.read_text(encoding="utf-8") for p in cfg.WORLD_DIR.rglob("*") if p.is_file())
    record("K3", "the key is not under world/", cfg.WORLD_DIR.resolve() not in cfg.KEY_DIR.resolve().parents and not (cfg.WORLD_DIR / "key").exists())
    leaked = [i for i in ids if i in world_text]
    reference_sql = {re.sub(r"\s+", " ", e["reference"]["sql"]).strip().rstrip(";") for e in entries.values()}   # whole queries; shared CTE fragments are house style
    sql_leaked = [s for s in reference_sql if s in re.sub(r"\s+", " ", world_text)]
    record("K3", "no test request ID, text or reference SQL appears anywhere in world/",
           not leaked and not sql_leaked and not any(requests[i]["request_text"] in world_text for i in ids), f"{len(leaked)} ids, {len(sql_leaked)} queries")

    # ---- evaluate every question from scratch ----------------------------------------------------------------------
    qids = sorted({b["qid"] for b in briefs})
    questions, results = evaluate_all(qids, published=connection)

    # ---- dev history: no test question has a dev query's result ------------------------------------------------------
    dev_prints = set()
    for r in dev_requests.DEV_REQUESTS:
        frame = connection.execute(r["sql"]).df()
        dev_prints.add(fingerprint(frame))
    duplicated = [qid for qid, res in results.items() if fingerprint(res["reference_frame"]) in dev_prints and len(fingerprint(res["reference_frame"])) > 1]
    record("K2", "no test question gives the same table of numbers as any of the 40 dev queries", not duplicated, str(duplicated))

    # ---- rule 12 ------------------------------------------------------------------------------------------------------
    for qid in qids:
        outcomes = results[qid]["outcomes"]
        wanted = [o for o in outcomes if ("equals pandas" in o["check"] or "non-empty" in o["check"] or "row order" in o["check"] or "repaired" in o["check"]) and "naive" not in o["check"]]
        failed = [o for o in wanted if not o["ok"]]
        record("R12", f"{qid}: reference SQL, accepted readings and published number all equal the pandas recomputation and are non-empty", not failed,
               "; ".join(f"{o['check']} ({o['detail']})" for o in failed)[:300] if failed else f"{len(wanted)} checks")
    stale = []
    for brief in briefs:
        entry, fresh = entries[brief["id"]], results[brief["qid"]]
        same, why = compare_tables(frame_from_table(entry["reference"]["result"]), fresh["reference_frame"], questions[brief["qid"]].columns)
        if not same:
            stale.append(f"{brief['id']}: {why}")
    record("R12", "the stored key equals the freshly computed reference result for all 60 requests", not stale, "; ".join(stale[:3]))

    # ---- rule 13 ------------------------------------------------------------------------------------------------------
    counts = Counter()
    for brief in briefs:
        entry, question = entries[brief["id"]], questions[brief["qid"]]
        classes = entry["trap_classes"]
        counts.update(classes)
        if "clean" in classes:
            ok = not entry["naive"] and not entry["interpretations"] and not entry["undocumented"] and bool(question.invariance_sql)
            detail = "clean: no naive variant"
        else:
            ok = bool(entry["naive"]) and all(n["differs_from_every_accepted_result"] for n in entry["naive"]) and len(classes) <= 2
            detail = f"{len(entry['naive'])} naive variants, classes {classes}"
        record("R13", f"{brief['id']} ({brief['qid']}): " + ("clean request has no naive variant" if "clean" in classes else "every trap has a naive variant that bites, at most two traps"), ok, detail)
    for qid in qids:
        wanted = [o for o in results[qid]["outcomes"] if "naive" in o["check"] or "top-N" in o["check"] or "sloppy" in o["check"] or "published number differs" in o["check"]]
        failed = [o for o in wanted if not o["ok"]]
        record("R13", f"{qid}: naive variants bite beyond 10 x tolerance, top-N has no tie, clean sloppy variants agree", not failed,
               "; ".join(f"{o['check']} ({o['detail']})" for o in failed)[:300] if failed else f"{len(wanted)} checks")
    out_of_range = {c: (counts.get(c, 0), target) for c, target in cfg.TRAP_CLASS_COUNTS.items() if abs(counts.get(c, 0) - target) > cfg.TRAP_CLASS_TOLERANCE}
    record("R13", "trap-class counts are within tolerance of the targets", not out_of_range,
           ", ".join(f"{c} {counts.get(c, 0)} ({t})" for c, t in cfg.TRAP_CLASS_COUNTS.items()))
    record("R13", "clean requests number 14 and trapped requests 46", counts["clean"] == 14, f"{counts['clean']} clean")

    # ---- rule 14 ------------------------------------------------------------------------------------------------------
    by_twin = {}
    for brief in briefs:
        if brief["twin"]:
            by_twin.setdefault(brief["twin"], []).append(brief)
    for twin, pair in sorted(by_twin.items()):
        a, b = (entries[p["id"]] for p in pair)
        same_ref, why = compare_tables(frame_from_table(a["reference"]["result"]), frame_from_table(b["reference"]["result"]), a["columns"])
        same_all = (same_ref and a["question_id"] == b["question_id"] and a["interpretations"] == b["interpretations"] and a["naive"] == b["naive"]
                    and a["undocumented"] == b["undocumented"])
        record("R14", f"twins {pair[0]['id']} and {pair[1]['id']} ({twin}) have identical reference results and variants", same_all, why)

    # ---- rule 15 ------------------------------------------------------------------------------------------------------
    ambiguous = [e for e in entries.values() if "ambiguous" in e["trap_classes"]]
    record("R15", "five ambiguous requests", len(ambiguous) == cfg.TRAP_CLASS_COUNTS["ambiguous"], f"{len(ambiguous)}")
    for entry in ambiguous:
        interps = entry["interpretations"]
        distinct = next((o for o in results[entry["question_id"]]["outcomes"] if "every accepted reading gives a different result" in o["check"]), {"ok": False})
        rule_tests = all(i["assumption_rule"]["groups"] and keyword_rule_match(i["assumption_rule"]["groups"], i["assumption_rule"]["example_pass"])
                         and not keyword_rule_match(i["assumption_rule"]["groups"], i["assumption_rule"]["example_fail"]) for i in interps)
        # readings that reach the double-posted week carry a second accepted outcome with its own caveat rule
        for i in interps:
            published = i["published_outcome"]
            if published:
                caveat = published["caveat_rule"]
                rule_tests = rule_tests and keyword_rule_match(caveat["groups"], caveat["example_pass"]) and not keyword_rule_match(caveat["groups"], caveat["example_fail"])
        record("R15", f"{entry['request_id']} ({entry['question_id']}): at least two accepted readings with different results, each with a keyword rule that passes and fails its examples",
               len(interps) >= 2 and distinct["ok"] and rule_tests, f"{len(interps)} readings")

    # ---- undocumented-issue requests -----------------------------------------------------------------------
    undocumented = [e for e in entries.values() if e["undocumented"]]
    incidents = sorted(e["undocumented"]["incident"] for e in undocumented if e["twin_group"] is None)
    record("K4", "four undocumented-issue requests, one per planted incident", len(undocumented) == 4 and incidents == ["INC-1", "INC-2", "INC-3", "INC-4"], str(incidents))
    for entry in undocumented:
        spec = entry["undocumented"]
        rule = spec["outcome_b_published_with_caveat"]["caveat_rule"]
        a = frame_from_table(spec["outcome_a_incident_free"]["result"])
        b = frame_from_table(spec["outcome_b_published_with_caveat"]["result"])
        differs = not compare_tables(a, b, entry["columns"], factor=cfg.TRAP_BITE_FACTOR)[0]
        passes = keyword_rule_match(rule["groups"], rule["example_pass"]) and not keyword_rule_match(rule["groups"], rule["example_fail"])
        record("K4", f"{entry['request_id']} ({spec['incident']}): outcome (a) incident-free and outcome (b) published differ, and the caveat rule passes and fails its examples", differs and passes)
    clean_incident = [i for i in ids if not entries[i]["undocumented"] and not any(
        o["ok"] is False for o in results[entries[i]["question_id"]]["outcomes"] if "repaired" in o["check"])]
    record("K4", "every request that is not an undocumented-issue request gives the same answer on the published and the repaired warehouse", len(clean_incident) == 56, f"{len(clean_incident)} requests")
