"""
evaluate.py -- Official evaluation of the hybrid pipeline.

Scores both paths against the answer key, checks the frozen designed-outcome
table (pre-registered) against what actually happened, and computes the cost
series -- labelled estimates, method B.

Inputs (all produced earlier in the pipeline):
    data/runs/stream_events.json   -- the router replay (router.py)
    data/runs/llm_parses/          -- recorded LLM-path parses (subagents)
    code/parsers_generated/        -- the overseer's parsers
    data/answer_key/               -- ground truth (scoring only)
    data/runs/parse_agent_log.json -- measured subagent usage + pricing ref

Outputs:
    data/runs/evaluation.json      -- per-doc series + summary (feeds the
                                      notebook and the interactive page)
    printed report

Cost labelling (non-negotiable): subagent token totals are undifferentiated
(input+output combined) and include agent overhead, so every cost figure is
an ESTIMATE -- a band from the all-input floor to the all-output ceiling,
with a central estimate at a stated 85/15 input/output split. Accuracy
figures are exact. Local parser runtime is measured on this machine.

Usage: python evaluate.py
"""

import sys
import json
import time
import importlib.util
from pathlib import Path
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from check_llm_parses import compare_doc

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "data" / "documents"
KEYS = ROOT / "data" / "answer_key"
LLM = ROOT / "data" / "runs" / "llm_parses"
GEN = Path(__file__).resolve().parent / "parsers_generated"
RUNS = ROOT / "data" / "runs"

TYPES = ["FBL3N", "ME2M", "VA05", "FBL1N", "MB52"]

DESIGNED_OUTCOME = {  # frozen pre-registration (incl. relocations)
    "R": "deterministic after the type's parser activates (discovery docs LLM by construction)",
    "V": "stays on the LLM path (below the learning threshold)",
    "F": "deterministic parse fails validation -> falls back to the LLM",
    "S": "parses deterministically, passes all checks, silently wrong vs the answer key",
}


def load_parser(ttype):
    path = GEN / f"parser_{ttype.lower()}.py"
    spec = importlib.util.spec_from_file_location(f"eval_{ttype.lower()}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    log = json.loads((RUNS / "parse_agent_log.json").read_text(encoding="utf-8"))
    pricing = log["pricing_reference"]
    rate_in = pricing["usd_per_mtok_input"] / 1e6
    rate_out = pricing["usd_per_mtok_output"] / 1e6
    rate_central = 0.85 * rate_in + 0.15 * rate_out   # stated split assumption

    # ---- measured tokens / wall per doc (batch totals allocated evenly) ----
    doc_tokens, doc_wall = defaultdict(float), defaultdict(float)
    for wave in ("discovery_wave", "fallback_wave", "retry_wave"):
        for b in log[wave]["batches"]:
            per_tok = b["subagent_tokens"] / len(b["docs"])
            per_wall = b["wall_ms"] / len(b["docs"])
            for d in b["docs"]:
                doc_tokens[d] += per_tok   # retry adds on top: true cost of those docs
                doc_wall[d] += per_wall

    overseer = log["overseer_generation_wave"]
    overseer_tokens = {b["batch"].split("_")[1]: b["subagent_tokens"] for b in overseer["batches"]}

    # per-type mean measured tokens/doc -> counterfactual model for unparsed docs
    type_tokens = defaultdict(list)
    for d, t in doc_tokens.items():
        type_tokens[d.split("_")[1]].append(t)
    type_mean = {t: sum(v) / len(v) for t, v in type_tokens.items()}

    events = json.loads((RUNS / "stream_events.json").read_text(encoding="utf-8"))
    parsers = {t: load_parser(t) for t in TYPES}

    docs_out, activation_events = [], []
    cum_hybrid = cum_cf = 0.0
    acc = defaultdict(lambda: {"docs": 0, "fields": 0, "wrong": 0})
    scorecard = defaultdict(lambda: defaultdict(int))
    idx = 0

    for ev in events:
        if ev.get("event") == "parser_activated":
            tok = overseer_tokens[ev["type"]]
            cost = tok * rate_central
            cum_hybrid += cost
            activation_events.append({
                "after_idx": idx - 1, "type": ev["type"],
                "one_time_tokens_measured": tok,
                "cost_central_usd_est": round(cost, 4),
            })
            continue

        doc_id = ev["doc_id"]
        ak = json.loads((KEYS / f"{doc_id}.json").read_text(encoding="utf-8"))
        cls, ttype = ak["doc_class"], ak["transaction_type"]
        path = ev["path"]

        # accuracy: score whatever payload the accepted path produced
        parse_ms = 0.0
        if path == "deterministic":
            text = (DOCS / f"{doc_id}.txt").read_text(encoding="utf-8")
            t0 = time.perf_counter()
            payload = parsers[ttype].parse(text)
            parse_ms = (time.perf_counter() - t0) * 1000
        else:
            payload = json.loads((LLM / f"{doc_id}.json").read_text(encoding="utf-8"))
        mism = []
        n = compare_doc(ttype, payload, ak["parse"], mism)

        bucket = "deterministic" if path == "deterministic" else "llm"
        acc[bucket]["docs"] += 1
        acc[bucket]["fields"] += n
        acc[bucket]["wrong"] += len(mism)
        scorecard[cls][path] += 1
        if cls == "S" and mism:
            scorecard[cls]["silently_wrong_fields"] += len(mism)

        tok_hybrid = doc_tokens.get(doc_id, 0.0) if bucket == "llm" else 0.0
        tok_cf = doc_tokens.get(doc_id, type_mean[ttype])
        cost_h, cost_cf = tok_hybrid * rate_central, tok_cf * rate_central
        cum_hybrid += cost_h
        cum_cf += cost_cf

        docs_out.append({
            "idx": idx, "doc_id": doc_id, "month": ev["month"], "type": ttype,
            "class": cls, "path": path,
            "fields": n, "wrong_fields": len(mism),
            "mismatches": mism[:4],
            "tokens_hybrid_measured": round(tok_hybrid),
            "tokens_counterfactual_est": round(tok_cf),
            "cost_hybrid_central_usd_est": round(cost_h, 4),
            "cost_cf_central_usd_est": round(cost_cf, 4),
            "cum_hybrid_usd_est": round(cum_hybrid, 4),
            "cum_cf_usd_est": round(cum_cf, 4),
            "parse_ms_local": round(parse_ms, 2),
            "wall_ms_llm_alloc": round(doc_wall.get(doc_id, 0.0)) if bucket == "llm" else 0,
        })
        idx += 1

    # ---- summary -----------------------------------------------------------
    tot_tok_hybrid = sum(d["tokens_hybrid_measured"] for d in docs_out) \
        + sum(e["one_time_tokens_measured"] for e in activation_events)
    tot_tok_cf = sum(d["tokens_counterfactual_est"] for d in docs_out)
    band = lambda tok: {"floor_all_input_usd": round(tok * rate_in, 2),
                        "central_85_15_usd": round(tok * rate_central, 2),
                        "ceiling_all_output_usd": round(tok * rate_out, 2)}

    det_docs = acc["deterministic"]["docs"]
    summary = {
        "labels": "All costs are ESTIMATES (method B): published Sonnet-tier list prices applied to measured, undifferentiated subagent token totals (upper bound incl. agent overhead). Accuracy is exact vs the answer key.",
        "paths": {"deterministic": det_docs, "llm_discovery+fallback": acc["llm"]["docs"]},
        "deterministic_share": round(det_docs / len(docs_out), 4),
        "accuracy": {
            b: {"docs": a["docs"], "fields": a["fields"], "wrong": a["wrong"],
                "field_accuracy": round((a["fields"] - a["wrong"]) / a["fields"], 6)}
            for b, a in acc.items()
        },
        "designed_outcome_scorecard": {
            cls: {"designed": DESIGNED_OUTCOME[cls], "actual": dict(paths)}
            for cls, paths in sorted(scorecard.items())
        },
        "deviations_from_design": [
            "FBL1N F-class (5 docs): designed to fall back; actually parsed correctly on the deterministic path (currency-general parser). Accepted and frozen.",
        ],
        "cost_estimates": {
            "hybrid_total_tokens_measured": round(tot_tok_hybrid),
            "hybrid": band(tot_tok_hybrid),
            "counterfactual_all_llm_tokens_est": round(tot_tok_cf),
            "counterfactual_all_llm": band(tot_tok_cf),
            "saving_central_usd_est": round((tot_tok_cf - tot_tok_hybrid) * rate_central, 2),
            "saving_share_of_cf": round(1 - tot_tok_hybrid / tot_tok_cf, 4),
        },
        "pricing_reference": pricing,
    }

    out = {"meta": {"generated_by": "evaluate.py", "labels": summary["labels"]},
           "docs": docs_out, "activation_events": activation_events, "summary": summary}
    (RUNS / "evaluation.json").write_text(json.dumps(out, indent=1, ensure_ascii=False),
                                          encoding="utf-8")

    print("=== Paths ===")
    print(f"deterministic: {det_docs}/{len(docs_out)} ({summary['deterministic_share']:.1%})  "
          f"llm: {acc['llm']['docs']}")
    print("\n=== Field accuracy (exact, vs answer key) ===")
    for b, a in summary["accuracy"].items():
        print(f"{b:14} docs {a['docs']:>3}  fields {a['fields']:>6}  wrong {a['wrong']:>3}  "
              f"accuracy {a['field_accuracy']:.4%}")
    print("\n=== Designed-outcome scorecard ===")
    for cls, row in summary["designed_outcome_scorecard"].items():
        print(f"{cls}: actual {row['actual']}")
    print("\n=== Cost estimates (labelled; central = 85/15 split) ===")
    ce = summary["cost_estimates"]
    print(f"hybrid:         {ce['hybrid_total_tokens_measured']:>9} tok  "
          f"${ce['hybrid']['floor_all_input_usd']}-${ce['hybrid']['ceiling_all_output_usd']} "
          f"(central ${ce['hybrid']['central_85_15_usd']})")
    print(f"counterfactual: {ce['counterfactual_all_llm_tokens_est']:>9} tok  "
          f"${ce['counterfactual_all_llm']['floor_all_input_usd']}-"
          f"${ce['counterfactual_all_llm']['ceiling_all_output_usd']} "
          f"(central ${ce['counterfactual_all_llm']['central_85_15_usd']})")
    print(f"central saving: ${ce['saving_central_usd_est']} ({ce['saving_share_of_cf']:.1%} of counterfactual)")
    print(f"\nEvaluation written to {RUNS / 'evaluation.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
