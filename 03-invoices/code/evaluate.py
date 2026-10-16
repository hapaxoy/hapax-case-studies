"""evaluate.py -- The marking step for the invoice-processing pipeline.

THIS IS THE ONLY SCRIPT IN THE PIPELINE ALLOWED TO READ data/answer_key/.
regression_gate.py and router.py never touch it;
evaluate.py exists precisely to be the one place that does, so
the marking can be done honestly against ground truth while the rest of the
pipeline runs blind to it, exactly as a production system would.

Inputs:
    data/runs/stream_events.json    -- the router replay (router.py)
    data/runs/llm_parses/           -- recorded LLM-path parses
    code/parsers_generated/         -- the overseer's parsers (re-run here
                                        to reconstruct deterministic-path
                                        payloads; router.py does not persist
                                        them, only which parser succeeded)
    data/answer_key/                -- ground truth (scoring only)
    data/runs/parse_agent_log.json  -- measured subagent usage + pricing
                                        reference (see "parse_agent_log.json
                                        interface" below)

Output:
    data/runs/evaluation.json       -- page- and notebook-ready: accuracy,
                                        scorecard, shares, costs, latency.
                                        Every cost figure carries an explicit
                                        "estimate": true.
    printed report

parse_agent_log.json interface (ASSUMED -- this script was written before
the log existed, so the reader documents the interface it expects):

    {
      "pricing_reference": {
        "source": "...", "model_class": "...", "as_of": "YYYY-MM-DD",
        "usd_per_mtok_input": <num>, "usd_per_mtok_output": <num>, "note": "..."
      },
      "waves": [
        {"wave": "discovery_wave", "date": "...", "model": "claude-sonnet-5",
         "batches": [{"batch": "...", "doc_ids": [...], "subagent_tokens": <num>, "wall_ms": <num>}]},
        {"wave": "fallback_wave", ...},
        {"wave": "retry_wave", ...},                    # schema-failure retries; a doc_id
                                                          # appearing here ADDS to its tokens
        {"wave": "overseer_generation_wave", "date": "...", "model": "...",
         "batches": [{"batch": "parser_s1", "parser": "s1", "subagent_tokens": <num>, "wall_ms": <num>}]}
      ]
    }

Cost labelling (non-negotiable, method B):
subagent token totals are undifferentiated (input+output combined) and
include agent overhead, so every cost figure is an ESTIMATE -- a band from
the all-input floor to the all-output ceiling, with a central estimate at a
stated 85/15 input/output split. Accuracy figures are exact. Every leaf of
"cost_estimates" in the output JSON carries "estimate": true.

Usage:
    python evaluate.py                 # real run
    python evaluate.py --selftest      # exercises the same scoring/cost
                                        # logic on tiny synthetic fixtures in
                                        # a temp dir; no real corpus, answer
                                        # key, parsers or log needed
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pipeline_common as pc
import schemas

HERE = Path(__file__).resolve().parent
PARSERS_DIR = HERE / "parsers_generated"
PROJECT_ROOT = HERE.parent
DATA_DIR = PROJECT_ROOT / "data"
DOCS_DIR = DATA_DIR / "documents"
LLM_PARSES_DIR = DATA_DIR / "runs" / "llm_parses"
ANSWER_KEY_DIR = DATA_DIR / "answer_key"
STREAM_EVENTS_PATH = DATA_DIR / "runs" / "stream_events.json"
PARSE_AGENT_LOG_PATH = DATA_DIR / "runs" / "parse_agent_log.json"
OUT_PATH = DATA_DIR / "runs" / "evaluation.json"

EXPECTED_TOTAL_DOCUMENTS = 198

# Pre-registered designed-outcome table (frozen; deviations
# from this are listed, never silently absorbed -- Case 2 precedent).
DESIGNED_OUTCOME_COUNTS: dict[str, dict[str, int]] = {
    "R": {"llm-discovery": 48, "deterministic": 117},
    "O": {"llm-oneoff": 20},
    "T": {"llm-fallback": 6, "deterministic": 2},
    "F": {"llm-fallback": 4},
    "S": {"deterministic": 1},
}
DESIGNED_OUTCOME_NOTE = {
    "R": "LLM path for each supplier's first 6 (discovery); deterministic thereafter",
    "O": "stays on the LLM path permanently (below any learning threshold)",
    "T": "parser v1 fails validation loudly -> LLM fallback -> overseer re-learns -> parser v2 -> deterministic again",
    "F": "deterministic parse fails validation -> falls back to the LLM -> correct result",
    "S": "parses deterministically, passes all checks, silently wrong vs the answer key (the document lies)",
}

# Fallback pricing reference, used only if parse_agent_log.json does not
# carry its own pricing_reference block. Reuses the figures Case 2's
# evaluate.py recorded the same day (02 ERP Cleanup/data/runs/
# evaluation.json), checked 2026-07-03 against Anthropic's published price
# list -- not invented, and not re-verified independently here.
FALLBACK_PRICING_REFERENCE = {
    "source": "Anthropic published list prices, as recorded by Case 2's evaluate.py "
               "(02 ERP Cleanup), checked 2026-07-03 against the published price list",
    "model_class": "Claude Sonnet tier (claude-sonnet-5)",
    "as_of": "2026-07-03",
    "usd_per_mtok_input": 3.0,
    "usd_per_mtok_output": 15.0,
    "note": "FALLBACK VALUE: parse_agent_log.json did not carry its own pricing_reference. "
            "Introductory pricing ($2/$10) runs through 2026-08-31; this uses standard list "
            "prices. subagent_tokens are undifferentiated totals, so costs are a BAND "
            "(all-input floor to all-output ceiling) plus a central estimate at a stated "
            "85/15 input/output split. All figures are estimates.",
}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_stream_events(path: Path) -> tuple[list[dict], list[dict]]:
    events = json.loads(path.read_text(encoding="utf-8"))
    doc_events = [e for e in events if "doc_id" in e]
    birth_events = [e for e in events if e.get("event") == "parser_born"]
    return doc_events, birth_events


def load_answer_key(key_dir: Path, doc_id: str) -> dict:
    path = key_dir / f"{doc_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"no answer key for {doc_id} at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def path_group(path: str) -> str:
    """Collapse the four routing paths to the two accuracy buckets the
    case reports: 'deterministic' vs 'llm' (discovery+oneoff+fallback)."""
    return "deterministic" if path == "deterministic" else "llm"


def compute_payload(event: dict, docs_dir: Path, parsers_dir: Path, llm_dir: Path,
                     parser_cache: dict) -> dict:
    """Reconstruct the record that the accepted path actually produced.
    Mirrors Case 2's evaluate.py: the router does not persist payloads, only
    which path/parser won, so this re-derives them (deterministic parses are
    pure re-runs of the same parser on the same PDF; LLM parses are loaded
    from the recorded file)."""
    doc_id = event["doc_id"]
    if event["path"] == "deterministic":
        slug = event["parser_used"]
        if slug is None:
            raise ValueError(f"{doc_id}: path is 'deterministic' but parser_used is null")
        if slug not in parser_cache:
            py_path = parsers_dir / f"parser_{slug}.py"
            parser_cache[slug] = pc.load_parser_module(py_path, slug)
        return parser_cache[slug].parse(str(docs_dir / f"{doc_id}.pdf"))
    llm_path = llm_dir / f"{doc_id}.json"
    if not llm_path.exists():
        raise FileNotFoundError(f"{doc_id}: path is {event['path']!r} but {llm_path} is missing")
    return json.loads(llm_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Accuracy
# ---------------------------------------------------------------------------

def score_document(payload: dict, truth: dict, is_s_exception: bool) -> dict:
    """schemas.compare_records against the answer key, with the S-document's
    two designed mismatches (one line's quantity and unit_price) split out
    -- same heuristic as check_llm_parses.py: any wrong field whose path
    contains 'quantity' or 'unit_price' on the s_exception document is a
    DESIGNED mismatch, not an extraction error."""
    cmp = schemas.compare_records(payload, truth)
    designed, extraction_errors = [], []
    for path, got, want in cmp["wrong"]:
        if is_s_exception and ("quantity" in path or "unit_price" in path):
            designed.append({"field": path, "parsed": got, "truth": want})
        else:
            extraction_errors.append({"field": path, "parsed": got, "truth": want})
    return {"total_fields": cmp["total"], "extraction_errors": extraction_errors,
            "designed_mismatches": designed}


def build_accuracy(scored: list[dict]) -> dict:
    """Per-path (deterministic/llm) and overall field accuracy, both
    excluding and including the S-document's designed mismatches (Case 2
    convention: report the corrected figure AND the naive one side by side)."""
    buckets = defaultdict(lambda: {"docs": 0, "fields": 0, "extraction_wrong": 0, "designed_wrong": 0})
    for s in scored:
        b = buckets[s["path_group"]]
        b["docs"] += 1
        b["fields"] += s["total_fields"]
        b["extraction_wrong"] += len(s["extraction_errors"])
        b["designed_wrong"] += len(s["designed_mismatches"])
        o = buckets["overall"]
        o["docs"] += 1
        o["fields"] += s["total_fields"]
        o["extraction_wrong"] += len(s["extraction_errors"])
        o["designed_wrong"] += len(s["designed_mismatches"])

    out = {}
    for bucket, v in buckets.items():
        fields = v["fields"] or 1
        excl = v["extraction_wrong"]
        incl = v["extraction_wrong"] + v["designed_wrong"]
        out[bucket] = {
            "docs": v["docs"], "fields": v["fields"],
            "wrong_excluding_s": v["extraction_wrong"],
            "wrong_including_s": incl,
            "field_accuracy_excluding_s": round((fields - excl) / fields, 6),
            "field_accuracy_including_s": round((fields - incl) / fields, 6),
        }
    return out


# ---------------------------------------------------------------------------
# Scorecard (designed vs actual)
# ---------------------------------------------------------------------------

def build_scorecard(scored: list[dict]) -> tuple[dict, list[str]]:
    actual: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for s in scored:
        actual[s["class"]][s["path"]] += 1

    deviations = []
    all_classes = sorted(set(DESIGNED_OUTCOME_COUNTS) | set(actual))
    for cls in all_classes:
        designed = DESIGNED_OUTCOME_COUNTS.get(cls, {})
        got = dict(actual.get(cls, {}))
        all_paths = sorted(set(designed) | set(got))
        for path in all_paths:
            d, a = designed.get(path, 0), got.get(path, 0)
            if d != a:
                deviations.append(
                    f"class {cls}, path {path}: designed {d}, actual {a}")

    scorecard = {
        cls: {"designed": DESIGNED_OUTCOME_COUNTS.get(cls, {}),
              "designed_note": DESIGNED_OUTCOME_NOTE.get(cls, ""),
              "actual": dict(actual.get(cls, {})),
              "actual_total": sum(actual.get(cls, {}).values())}
        for cls in all_classes
    }
    return scorecard, deviations


# ---------------------------------------------------------------------------
# Shares
# ---------------------------------------------------------------------------

def canonical_supplier_id(truth_record: dict) -> str:
    """The same "who is this really" key export_master_data.py dedupes
    one-off suppliers by (vat_id first, business_id, then name) -- so a
    supplier that invoices twice under two doc_ids still counts once."""
    supplier = truth_record.get("supplier", {})
    return supplier.get("vat_id") or supplier.get("business_id") or supplier.get("name") or "?"


def build_shares(scored: list[dict], birth_events: list[dict], doc_events_by_id: dict) -> dict:
    total = len(scored)
    det = sum(1 for s in scored if s["path"] == "deterministic")
    whole_stream_share = round(det / total, 4) if total else 0.0

    by_month: dict[str, dict[str, int]] = defaultdict(lambda: {"docs": 0, "deterministic": 0})
    for s in scored:
        m = by_month[s["month"]]
        m["docs"] += 1
        if s["path"] == "deterministic":
            m["deterministic"] += 1
    per_month = {m: {**v, "deterministic_share": round(v["deterministic"] / v["docs"], 4) if v["docs"] else 0.0}
                 for m, v in sorted(by_month.items())}

    timeline = []
    for b in sorted(birth_events, key=lambda e: e["stream_index"]):
        after = doc_events_by_id.get(b["after_doc_id"], {})
        timeline.append({
            "parser": b["parser"], "supplier": b["supplier"],
            "birth_date": after.get("date"), "after_doc_id": b["after_doc_id"],
            "stream_index": b["stream_index"],
            "documents_seen_before_birth": b["induction_doc_count"],
        })

    all_supplier_ids = {canonical_supplier_id(s["truth"]) for s in scored}
    automated_supplier_slugs = {b["supplier"] for b in birth_events}
    total_suppliers = len(all_supplier_ids)
    automated_suppliers = len(automated_supplier_slugs)
    long_tail = {
        "total_suppliers": total_suppliers,
        "automated_suppliers": automated_suppliers,
        "automated_supplier_share": round(automated_suppliers / total_suppliers, 4) if total_suppliers else 0.0,
        "total_documents": total,
        "volume_automated_documents": det,
        "volume_automated_share": whole_stream_share,
        "note": "suppliers automated vs volume automated -- the automation ceiling is a "
                "property of the supplier base, not of parser quality",
    }

    return {
        "whole_stream_deterministic_share": whole_stream_share,
        "per_month": per_month,
        "parser_birth_timeline": timeline,
        "long_tail_exhibit": long_tail,
    }


# ---------------------------------------------------------------------------
# Costs
# ---------------------------------------------------------------------------

def load_parse_agent_log(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"parse_agent_log.json not found at {path} -- see this script's docstring "
            f"for the assumed interface")
    return json.loads(path.read_text(encoding="utf-8"))


def allocate_tokens(log: dict) -> tuple[dict, dict, dict, dict, list[dict]]:
    """Batch totals allocated evenly across their doc_ids (Case 2 method).
    A doc_id appearing in more than one batch (e.g. an original wave plus a
    retry_wave batch) accumulates -- retries are costed like any parse.
    Overseer-generation batches (no doc_ids; a "parser" slug instead) are
    kept separate: one-time parser-birth cost, not a per-document cost."""
    doc_tokens: dict[str, float] = defaultdict(float)
    doc_wall: dict[str, float] = defaultdict(float)
    overseer_tokens: dict[str, float] = defaultdict(float)
    overseer_wall: dict[str, float] = defaultdict(float)
    batch_log: list[dict] = []

    for wave in log.get("waves", []):
        wave_name = wave.get("wave", "?")
        for batch in wave.get("batches", []):
            wall_ms = batch.get("wall_ms", 0)
            tokens = batch.get("subagent_tokens", 0)
            doc_ids = batch.get("doc_ids")
            batch_log.append({"wave": wave_name, "batch": batch.get("batch", "?"),
                               "model": batch.get("model", wave.get("model")),
                               "n_docs": len(doc_ids) if doc_ids else 0,
                               "subagent_tokens": tokens, "wall_ms": wall_ms})
            if doc_ids:
                n = len(doc_ids)
                per_tok, per_wall = tokens / n, wall_ms / n
                for d in doc_ids:
                    doc_tokens[d] += per_tok
                    doc_wall[d] += per_wall
            else:
                slug = batch.get("parser") or batch.get("batch", "").removeprefix("parser_")
                overseer_tokens[slug] += tokens
                overseer_wall[slug] += wall_ms

    return doc_tokens, doc_wall, overseer_tokens, overseer_wall, batch_log


def build_costs(events: list[dict], log: dict, total_documents: int) -> dict:
    pricing = log.get("pricing_reference")
    pricing_is_fallback = pricing is None
    if pricing_is_fallback:
        pricing = FALLBACK_PRICING_REFERENCE

    rate_in = pricing["usd_per_mtok_input"] / 1e6
    rate_out = pricing["usd_per_mtok_output"] / 1e6
    rate_central = 0.85 * rate_in + 0.15 * rate_out

    doc_tokens, doc_wall, overseer_tokens, overseer_wall, batch_log = allocate_tokens(log)

    def band(tokens: float) -> dict:
        return {"estimate": True,
                "floor_all_input_usd": round(tokens * rate_in, 2),
                "central_85_15_usd": round(tokens * rate_central, 2),
                "ceiling_all_output_usd": round(tokens * rate_out, 2)}

    # per-document + cumulative curve, walking events in stream order so
    # parser-birth one-time costs land at the right position (page-ready
    # for the interactive "press play" cost curve)
    docs_curve = []
    cum_hybrid = 0.0
    for e in events:
        if e.get("event") == "parser_born":
            slug = e["parser"]
            tok = overseer_tokens.get(slug, 0.0)
            cost = tok * rate_central
            cum_hybrid += cost
            docs_curve.append({
                "event": "parser_born", "parser": slug, "after_doc_id": e["after_doc_id"],
                "stream_index": e["stream_index"], "one_time_tokens_measured": round(tok),
                "cost_central_usd_est": round(cost, 4), "cum_hybrid_usd_est": round(cum_hybrid, 4),
                "estimate": True,
            })
            continue
        doc_id = e["doc_id"]
        tok = doc_tokens.get(doc_id, 0.0) if e["path"] != "deterministic" else 0.0
        cost = tok * rate_central
        cum_hybrid += cost
        docs_curve.append({
            "doc_id": doc_id, "idx": e.get("idx"), "date": e.get("date"), "path": e["path"],
            "tokens_measured": round(tok), "cost_central_usd_est": round(cost, 4),
            "cum_hybrid_usd_est": round(cum_hybrid, 4), "estimate": True,
        })

    hybrid_total_tokens = sum(doc_tokens.values()) + sum(overseer_tokens.values())
    mean_tokens_per_parsed_doc = (sum(doc_tokens.values()) / len(doc_tokens)) if doc_tokens else 0.0
    counterfactual_total_tokens = mean_tokens_per_parsed_doc * total_documents

    total_wall_ms = sum(b["wall_ms"] for b in batch_log)

    return {
        "labels": "All figures under cost_estimates and latency are ESTIMATES (method B): "
                   "published Sonnet-tier list prices applied to measured, undifferentiated "
                   "subagent token totals (a band, all-input floor to all-output ceiling, "
                   "central at a stated 85/15 input/output split). PDF reading is a vision "
                   "task, so tokens/document run materially higher than a plain-text parse. "
                   "Accuracy figures elsewhere in this file are exact.",
        "pricing_reference": {**pricing, "used_as_fallback": pricing_is_fallback},
        "cost_estimates": {
            "estimate": True,
            "hybrid_llm_tokens_measured": round(sum(doc_tokens.values())),
            "hybrid_parser_generation_tokens_measured": round(sum(overseer_tokens.values())),
            "hybrid_total_tokens_measured": round(hybrid_total_tokens),
            "hybrid": band(hybrid_total_tokens),
            "mean_tokens_per_parsed_document_measured": round(mean_tokens_per_parsed_doc),
            "counterfactual_all_llm_tokens_est": round(counterfactual_total_tokens),
            "counterfactual_all_llm": band(counterfactual_total_tokens),
            "saving_central_usd_est": round((counterfactual_total_tokens - hybrid_total_tokens) * rate_central, 2),
            "saving_share_of_cf_est": round(
                1 - hybrid_total_tokens / counterfactual_total_tokens, 4
            ) if counterfactual_total_tokens else None,
        },
        "latency": {
            "estimate": True, "label": "harness-inclusive wall-clock (subagent session time, "
                                        "not pure model inference)",
            "total_wall_ms_measured": total_wall_ms,
            "per_batch": batch_log,
        },
        "docs_cost_curve": docs_curve,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_evaluation(docs_dir: Path, parsers_dir: Path, llm_dir: Path, key_dir: Path,
                    stream_events_path: Path, parse_agent_log_path: Path, out_path: Path) -> int:
    if not stream_events_path.exists():
        print(f"FATAL: {stream_events_path} does not exist -- run router.py first "
              f"(evaluate.py scores its replay, it does not produce one).", flush=True)
        return 1
    if not key_dir.exists():
        print(f"FATAL: answer-key directory {key_dir} does not exist.", flush=True)
        return 1

    try:
        doc_events, birth_events = load_stream_events(stream_events_path)
    except (OSError, json.JSONDecodeError) as e:
        print(f"FATAL: cannot read {stream_events_path}: {e}", flush=True)
        return 1
    doc_events_by_id = {e["doc_id"]: e for e in doc_events}
    print(f"Loaded {len(doc_events)} document events, {len(birth_events)} parser-birth events "
          f"from {stream_events_path}"
          + ("" if len(doc_events) == EXPECTED_TOTAL_DOCUMENTS else
             f"  (WARNING: expected {EXPECTED_TOTAL_DOCUMENTS})"), flush=True)

    parser_cache: dict = {}
    scored = []
    s_document = None
    for e in doc_events:
        try:
            ak = load_answer_key(key_dir, e["doc_id"])
            truth = ak["record"]
            is_s = bool(ak.get("s_exception"))
            payload = compute_payload(e, docs_dir, parsers_dir, llm_dir, parser_cache)
        except (FileNotFoundError, OSError, json.JSONDecodeError, KeyError) as exc:
            print(f"FATAL: cannot score {e['doc_id']!r}: {type(exc).__name__}: {exc}", flush=True)
            return 1
        result = score_document(payload, truth, is_s)
        row = {"doc_id": e["doc_id"], "class": ak["class"], "path": e["path"],
               "path_group": path_group(e["path"]), "month": e.get("date", "?")[:7],
               "truth": truth, **result}
        scored.append(row)
        if is_s:
            s_document = {
                "doc_id": e["doc_id"], "path": e["path"],
                "designed_mismatch_fields": result["designed_mismatches"],
                "extraction_errors_beyond_design": result["extraction_errors"],
                "note": "The S document's quantity/unit_price are transposed at the source "
                        "(printed 50 x EUR2.00 where the order was 2 x EUR50.00); neither path "
                        "can catch it from the document alone. Excluded from the error counts "
                        "and reported here separately.",
            }

    if s_document is None:
        print("  WARNING: no s_exception document found among the scored documents", flush=True)
    elif len(s_document["designed_mismatch_fields"]) != 2:
        print(f"  WARNING: S document {s_document['doc_id']} has "
              f"{len(s_document['designed_mismatch_fields'])} designed mismatch field(s), "
              f"expected 2", flush=True)

    accuracy = build_accuracy(scored)
    scorecard, deviations = build_scorecard(scored)
    shares = build_shares(scored, birth_events, doc_events_by_id)

    try:
        log = load_parse_agent_log(parse_agent_log_path)
        costs = build_costs(json.loads(stream_events_path.read_text(encoding="utf-8")), log,
                             len(doc_events))
        costs_error = None
    except FileNotFoundError as e:
        costs = None
        costs_error = str(e)

    out = {
        "meta": {"generated_by": "evaluate.py",
                 "note": "The only pipeline script that reads data/answer_key/ -- the marking "
                         "step. See its module docstring for the parse_agent_log.json interface "
                         "this script assumes."},
        "accuracy": accuracy,
        "s_document": s_document,
        "designed_outcome_scorecard": scorecard,
        "deviations_from_design": deviations,
        "shares": shares,
        "cost_estimates_block": costs,
        "cost_estimates_error": costs_error,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nEvaluation written to {out_path}", flush=True)

    print("\n=== Accuracy (per path) ===", flush=True)
    for bucket, a in accuracy.items():
        print(f"  {bucket:14} docs {a['docs']:>4}  fields {a['fields']:>6}  "
              f"excl-S accuracy {a['field_accuracy_excluding_s']:.4%}  "
              f"incl-S accuracy {a['field_accuracy_including_s']:.4%}", flush=True)

    print("\n=== Designed-outcome scorecard ===", flush=True)
    for cls, row in scorecard.items():
        print(f"  {cls}: designed {row['designed']}  actual {row['actual']}", flush=True)
    print(f"\nDeviations from design ({len(deviations)}):", flush=True)
    for d in deviations:
        print(f"  [DEVIATION] {d}", flush=True)
    if not deviations:
        print("  none -- every class matched the pre-registered table exactly", flush=True)

    print(f"\n=== Shares ===\nwhole-stream deterministic share: "
          f"{shares['whole_stream_deterministic_share']:.2%}", flush=True)
    lt = shares["long_tail_exhibit"]
    print(f"long-tail: {lt['automated_suppliers']}/{lt['total_suppliers']} suppliers automated "
          f"({lt['automated_supplier_share']:.1%}), carrying {lt['volume_automated_documents']}/"
          f"{lt['total_documents']} documents ({lt['volume_automated_share']:.1%} of volume)", flush=True)

    if costs:
        ce = costs["cost_estimates"]
        print("\n=== Cost estimates (labelled; central = 85/15 split) ===", flush=True)
        print(f"  hybrid:         {ce['hybrid_total_tokens_measured']:>9} tok  "
              f"${ce['hybrid']['floor_all_input_usd']}-${ce['hybrid']['ceiling_all_output_usd']} "
              f"(central ${ce['hybrid']['central_85_15_usd']})", flush=True)
        print(f"  counterfactual: {ce['counterfactual_all_llm_tokens_est']:>9} tok  "
              f"${ce['counterfactual_all_llm']['floor_all_input_usd']}-"
              f"${ce['counterfactual_all_llm']['ceiling_all_output_usd']} "
              f"(central ${ce['counterfactual_all_llm']['central_85_15_usd']})", flush=True)
        if costs["pricing_reference"]["used_as_fallback"]:
            print("  NOTE: parse_agent_log.json had no pricing_reference; used the fallback "
                  "recorded in this script (see docstring).", flush=True)
    else:
        print(f"\nCost estimates skipped: {costs_error}", flush=True)

    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true",
                     help="run the self-test on synthetic fixtures instead of the real corpus")
    args = ap.parse_args()

    if args.selftest:
        return run_selftest()

    return run_evaluation(DOCS_DIR, PARSERS_DIR, LLM_PARSES_DIR, ANSWER_KEY_DIR,
                           STREAM_EVENTS_PATH, PARSE_AGENT_LOG_PATH, OUT_PATH)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _fixture_record(number: str, issue_date: str, iban: str, qty="10", price="5.00") -> dict:
    line_total = f"{float(qty) * float(price):.2f}"
    net = line_total
    vat = f"{float(net) * 0.255:.2f}"
    gross = f"{float(net) + float(vat):.2f}"
    return {
        "schema_version": "1.0", "doc_id": "fixture",
        "supplier": {"name": "Selftest Supplier Oy", "street": "Testikatu 1",
                      "postcode": "00100", "city": "Helsinki", "country": "FI",
                      "vat_id": "FI22334455", "business_id": "9811228-8"},
        "buyer": {"name": "Pyökkipaja Oy", "street": "Esimerkkikatu 11",
                   "postcode": "15520", "city": "Lahti", "country": "FI",
                   "vat_id": None, "business_id": schemas.make_y_tunnus("2417551")},
        "invoice": {"number": number, "type": "invoice", "issue_date": issue_date,
                     "supply_date": None, "due_date": "2025-04-09", "payment_terms": 30,
                     "currency": "EUR", "po_number": None,
                     "reference_type": "viitenumero", "reference_value": schemas.make_viitenumero("10150001"),
                     "original_invoice_number": None, "reverse_charge_mention": None},
        "bank": {"iban": iban, "bic": "KALTFIHH"},
        "lines": [{"description": "Widget", "quantity": qty, "unit": "kpl",
                    "unit_price": price, "vat_rate": "25.5", "line_total": line_total}],
        "vat_summary": [{"rate": "25.5", "base": net, "amount": vat}],
        "totals": {"net": net, "vat": vat, "gross": gross},
    }


def run_selftest() -> int:
    print("=== evaluate.py --selftest ===", flush=True)
    ok_all = True

    with tempfile.TemporaryDirectory(prefix="hapax_evaluate_selftest_") as tmp:
        tmp_path = Path(tmp)
        docs_dir = tmp_path / "data" / "documents"
        parsers_dir = tmp_path / "code" / "parsers_generated"
        llm_dir = tmp_path / "data" / "runs" / "llm_parses"
        key_dir = tmp_path / "data" / "answer_key"
        for d in (docs_dir, parsers_dir, llm_dir, key_dir):
            d.mkdir(parents=True)

        iban = pc.make_test_iban("FI", "95783022011184")

        # -- a fake deterministic parser (reads its "PDF" as JSON, like the
        # other two scripts' fixtures) --
        (parsers_dir / "parser_s1.py").write_text('''
import json
def parse(pdf_path):
    return json.loads(open(pdf_path, encoding="utf-8").read())["record"]
''', encoding="utf-8")

        # doc 1: R-class, discovery (llm-discovery), perfect
        d1 = _fixture_record("1001", "2025-01-05", iban)
        (llm_dir / "2025-01_s1_01.json").write_text(json.dumps(d1), encoding="utf-8")
        (key_dir / "2025-01_s1_01.json").write_text(
            json.dumps({"schema_version": "1.0", "doc_id": "2025-01_s1_01", "class": "R", "record": d1}),
            encoding="utf-8")

        # doc 2: R-class, deterministic, perfect
        d2 = _fixture_record("1002", "2025-04-05", iban)
        (docs_dir / "2025-04_s1_01.pdf").write_text(json.dumps({"record": d2}), encoding="utf-8")
        (key_dir / "2025-04_s1_01.json").write_text(
            json.dumps({"schema_version": "1.0", "doc_id": "2025-04_s1_01", "class": "R", "record": d2}),
            encoding="utf-8")

        # doc 3: F-class, llm-fallback, perfect (deterministic parse would
        # have failed validation -- not exercised here, only the LLM result)
        d3 = _fixture_record("1003", "2025-09-05", iban)
        (llm_dir / "2025-09_s1_01.json").write_text(json.dumps(d3), encoding="utf-8")
        (key_dir / "2025-09_s1_01.json").write_text(
            json.dumps({"schema_version": "1.0", "doc_id": "2025-09_s1_01", "class": "F", "record": d3}),
            encoding="utf-8")

        # doc 4: S-class, deterministic, with the designed transposition --
        # payload (what the parser reads off the document) has qty=50/price=2.00;
        # truth (answer key) has the real transaction qty=2/price=50.00.
        s_truth = _fixture_record("1004", "2025-11-05", iban, qty="2", price="50.00")
        s_payload = _fixture_record("1004", "2025-11-05", iban, qty="50", price="2.00")
        (docs_dir / "2025-11_s1_02.pdf").write_text(json.dumps({"record": s_payload}), encoding="utf-8")
        (key_dir / "2025-11_s1_02.json").write_text(
            json.dumps({"schema_version": "1.0", "doc_id": "2025-11_s1_02", "class": "S",
                        "s_exception": True, "record": s_truth}), encoding="utf-8")

        # doc 5: R-class, deterministic, with a genuine extraction error
        # (wrong postcode) -- must show up as an extraction_error, not a
        # designed mismatch
        d5_truth = _fixture_record("1005", "2025-05-05", iban)
        d5_payload = json.loads(json.dumps(d5_truth))
        d5_payload["supplier"]["postcode"] = "99999"
        (docs_dir / "2025-05_s1_01.pdf").write_text(json.dumps({"record": d5_payload}), encoding="utf-8")
        (key_dir / "2025-05_s1_01.json").write_text(
            json.dumps({"schema_version": "1.0", "doc_id": "2025-05_s1_01", "class": "R", "record": d5_truth}),
            encoding="utf-8")

        stream_events = [
            {"idx": 0, "doc_id": "2025-01_s1_01", "date": "2025-01-05", "supplier": "s1",
             "path": "llm-discovery", "parser_used": None, "attempts": []},
            {"event": "parser_born", "parser": "s1", "supplier": "s1", "after_doc_id": "2025-01_s1_01",
             "stream_index": 0, "induction_doc_count": 1,
             "note": "born immediately after the last document in its induction manifest"},
            {"idx": 1, "doc_id": "2025-04_s1_01", "date": "2025-04-05", "supplier": "s1",
             "path": "deterministic", "parser_used": "s1", "attempts": []},
            {"idx": 2, "doc_id": "2025-05_s1_01", "date": "2025-05-05", "supplier": "s1",
             "path": "deterministic", "parser_used": "s1", "attempts": []},
            {"idx": 3, "doc_id": "2025-09_s1_01", "date": "2025-09-05", "supplier": "s1",
             "path": "llm-fallback", "parser_used": None, "attempts": []},
            {"idx": 4, "doc_id": "2025-11_s1_02", "date": "2025-11-05", "supplier": "s1",
             "path": "deterministic", "parser_used": "s1", "attempts": []},
        ]
        stream_events_path = tmp_path / "data" / "runs" / "stream_events.json"
        stream_events_path.parent.mkdir(parents=True, exist_ok=True)
        stream_events_path.write_text(json.dumps(stream_events), encoding="utf-8")

        log = {
            "pricing_reference": {"source": "test", "model_class": "test",
                                    "usd_per_mtok_input": 3.0, "usd_per_mtok_output": 15.0,
                                    "note": "fixture"},
            "waves": [
                {"wave": "discovery_wave", "date": "2025-01-06", "model": "claude-sonnet-5",
                 "batches": [{"batch": "s1_2025-01", "doc_ids": ["2025-01_s1_01"],
                               "subagent_tokens": 20000, "wall_ms": 90000}]},
                {"wave": "fallback_wave", "date": "2025-09-06", "model": "claude-sonnet-5",
                 "batches": [{"batch": "s1_fallback", "doc_ids": ["2025-09_s1_01"],
                               "subagent_tokens": 22000, "wall_ms": 95000}]},
                {"wave": "overseer_generation_wave", "date": "2025-01-07", "model": "claude-sonnet-5",
                 "batches": [{"batch": "parser_s1", "parser": "s1", "subagent_tokens": 150000, "wall_ms": 280000}]},
            ],
        }
        log_path = tmp_path / "data" / "runs" / "parse_agent_log.json"
        log_path.write_text(json.dumps(log), encoding="utf-8")

        out_path = tmp_path / "data" / "runs" / "evaluation.json"
        rc = run_evaluation(docs_dir, parsers_dir, llm_dir, key_dir, stream_events_path, log_path, out_path)
        print(f"  [A] run_evaluation exit code: {rc} (expect 0)", flush=True)
        ok_all &= (rc == 0)

        out = json.loads(out_path.read_text(encoding="utf-8"))

        # -- accuracy: deterministic bucket has 1 genuine extraction error
        # (doc 5's postcode) out of 3 deterministic docs; S-doc's 2 designed
        # mismatches must NOT appear in wrong_excluding_s --
        det = out["accuracy"]["deterministic"]
        check_acc = (det["docs"] == 3 and det["wrong_excluding_s"] == 1
                     and det["wrong_including_s"] == 3)
        print(f"  [B] deterministic accuracy: docs={det['docs']} wrong_excl_s={det['wrong_excluding_s']} "
              f"wrong_incl_s={det['wrong_including_s']} (expect 3/1/3): {'PASS' if check_acc else 'FAIL'}",
              flush=True)
        ok_all &= check_acc

        # -- S document reported separately with exactly 2 designed mismatches --
        s_doc = out["s_document"]
        check_s = s_doc is not None and s_doc["doc_id"] == "2025-11_s1_02" \
            and len(s_doc["designed_mismatch_fields"]) == 2
        print(f"  [C] s_document reported separately with 2 designed mismatches: "
              f"{'PASS' if check_s else 'FAIL'} ({s_doc})", flush=True)
        ok_all &= check_s

        # -- scorecard: R has both llm-discovery(1) and deterministic(2) in
        # this fixture, vs designed 48/117 -> both should be flagged as
        # deviations (a tiny fixture necessarily deviates from the full-scale
        # design numbers; the point is that build_scorecard DETECTS it) --
        deviations = out["deviations_from_design"]
        check_dev = any("class R" in d for d in deviations) and any("class F" in d for d in deviations)
        print(f"  [D] scorecard deviations detected for undersized fixture classes: "
              f"{'PASS' if check_dev else 'FAIL'} ({len(deviations)} deviations)", flush=True)
        ok_all &= check_dev

        # -- shares: 3 of 5 fixture documents (d2, d5, s) are deterministic --
        share = out["shares"]["whole_stream_deterministic_share"]
        check_share = abs(share - 0.6) < 1e-9
        print(f"  [E] whole-stream deterministic share: {share} (expect 0.6): "
              f"{'PASS' if check_share else 'FAIL'}", flush=True)
        ok_all &= check_share

        timeline = out["shares"]["parser_birth_timeline"]
        check_timeline = len(timeline) == 1 and timeline[0]["parser"] == "s1" \
            and timeline[0]["birth_date"] == "2025-01-05"
        print(f"  [F] parser-birth timeline: {timeline} (expect 1 entry, s1, 2025-01-05): "
              f"{'PASS' if check_timeline else 'FAIL'}", flush=True)
        ok_all &= check_timeline

        # -- costs: every leaf under cost_estimates carries estimate: true --
        ce = out["cost_estimates_block"]["cost_estimates"]
        check_estimate_flags = (ce.get("estimate") is True and ce["hybrid"].get("estimate") is True
                                  and ce["counterfactual_all_llm"].get("estimate") is True)
        print(f"  [G] every cost_estimates leaf carries estimate=true: "
              f"{'PASS' if check_estimate_flags else 'FAIL'}", flush=True)
        ok_all &= check_estimate_flags

        # hybrid tokens = discovery batch (20000, doc 1) + fallback batch
        # (22000, doc 3) + overseer batch (150000, one-time at birth) = 192000
        # (doc 2/4/5 are deterministic, cost 0 marginal)
        check_hybrid_tok = ce["hybrid_total_tokens_measured"] == 192000
        print(f"  [H] hybrid_total_tokens_measured: {ce['hybrid_total_tokens_measured']} "
              f"(expect 192000): {'PASS' if check_hybrid_tok else 'FAIL'}", flush=True)
        ok_all &= check_hybrid_tok

        # mean tokens per parsed doc = (20000+22000)/2 = 21000; counterfactual
        # over the fixture's 5 documents = 105000
        check_cf = ce["counterfactual_all_llm_tokens_est"] == 105000
        print(f"  [I] counterfactual_all_llm_tokens_est: {ce['counterfactual_all_llm_tokens_est']} "
              f"(expect 105000): {'PASS' if check_cf else 'FAIL'}", flush=True)
        ok_all &= check_cf

        check_not_fallback = out["cost_estimates_block"]["pricing_reference"]["used_as_fallback"] is False
        print(f"  [J] pricing_reference taken from the log, not the fallback: "
              f"{'PASS' if check_not_fallback else 'FAIL'}", flush=True)
        ok_all &= check_not_fallback

        # -- scenario K: missing parse_agent_log.json -> costs skipped
        # gracefully, rest of the evaluation still succeeds --
        out_path_k = tmp_path / "data" / "runs" / "evaluation_k.json"
        rc_k = run_evaluation(docs_dir, parsers_dir, llm_dir, key_dir, stream_events_path,
                               tmp_path / "data" / "runs" / "does_not_exist.json", out_path_k)
        out_k = json.loads(out_path_k.read_text(encoding="utf-8"))
        check_k = (rc_k == 0 and out_k["cost_estimates_block"] is None
                   and out_k["cost_estimates_error"] is not None)
        print(f"  [K] missing parse_agent_log.json degrades gracefully: "
              f"{'PASS' if check_k else 'FAIL'}", flush=True)
        ok_all &= check_k

    print(f"\nSelftest overall: {'PASS' if ok_all else 'FAIL'}", flush=True)
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
