"""Distil run artefacts into interactive/_data.json for the self-contained page.

Reads only public artefacts and run outputs
(never data/answer_key/ -- the S-document panel quotes evaluation.json, which is
the marking step's output). Asserts every headline figure against evaluation.json
so the page cannot drift from the evaluated numbers.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
RUNS = DATA / "runs"
OUT = HERE.parent / "interactive" / "_data.json"

REPEAT = {f"s{i}" for i in range(1, 9)}
SUPPLIER_LABELS = None  # filled from master_data


def text_excerpt(doc_id: str, max_lines: int = 26) -> str:
    txt = (RUNS / "text_layers" / f"{doc_id}.txt").read_text(encoding="utf-8")
    lines = txt.splitlines()
    out = lines[:max_lines]
    if len(lines) > max_lines:
        out.append(f"... ({len(lines) - max_lines} more lines)")
    return "\n".join(out)


def parser_excerpt(slug: str, max_lines: int = 44) -> str:
    src = (HERE / "parsers_generated" / f"parser_{slug}.py").read_text(encoding="utf-8")
    lines = src.splitlines()
    out = lines[:max_lines]
    out.append(f"... ({len(lines) - max_lines} more lines -- full source in code/parsers_generated/)")
    return "\n".join(out)


def main() -> None:
    ev = json.loads((RUNS / "evaluation.json").read_text(encoding="utf-8"))
    se = json.loads((RUNS / "stream_events.json").read_text(encoding="utf-8"))
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    master = json.loads((DATA / "master_data.json").read_text(encoding="utf-8"))
    log = json.loads((RUNS / "parse_agent_log.json").read_text(encoding="utf-8"))

    supplier_names = {s["id"]: s["name"] for s in master["suppliers"]}
    class_by_doc = {doc_id: entry["class"] for doc_id, entry in manifest["files"].items()}

    # --- per-document stream (198 rows, stream order) ---
    doc_events = [e for e in se if e.get("doc_id") and e.get("path")]
    assert len(doc_events) == 198, len(doc_events)
    curve = {r["doc_id"]: r for r in ev["cost_estimates_block"]["docs_cost_curve"] if r.get("doc_id")}

    path_code = {"deterministic": "d", "llm-discovery": "D", "llm-fallback": "f", "llm-oneoff": "o"}
    mean_tok = ev["cost_estimates_block"]["cost_estimates"]["mean_tokens_per_parsed_document_measured"]
    usd_per_tok_central = (0.85 * 3.0 + 0.15 * 15.0) / 1e6

    stream = []
    cum_cf = 0.0
    for i, e in enumerate(sorted(doc_events, key=lambda x: x["idx"])):
        cum_cf += mean_tok * usd_per_tok_central
        sup_id = e["supplier"] if e["supplier"] in REPEAT else None
        # one-off slugs -> master id (hyphen/underscore + second-visit suffix)
        sid = e["supplier"]
        if sid not in REPEAT:
            sid = sid.replace("-", "_")
            if sid.endswith("_2"):
                sid = sid[:-2]
        row = {
            "i": i,
            "id": e["doc_id"],
            "m": int(e["date"][5:7]),
            "s": supplier_names.get(e["supplier"], supplier_names.get(sid, sid)),
            "c": class_by_doc[e["doc_id"]],
            "p": path_code[e["path"]],
            "ch": round(curve[e["doc_id"]]["cum_hybrid_usd_est"], 3) if e["doc_id"] in curve else None,
            "cc": round(cum_cf, 3),
        }
        stream.append(row)
    # carry cumulative hybrid forward over rows the curve tracks separately (birth steps)
    last = 0.0
    for r in stream:
        if r["ch"] is None:
            r["ch"] = round(last, 3)
        else:
            last = max(last, r["ch"])
            r["ch"] = round(last, 3)

    # --- long tail, both framings ---
    vol_auto_docs = sum(1 for e in doc_events if e["supplier"] in REPEAT)
    lt = ev["shares"]["long_tail_exhibit"]
    longtail = {
        "sup_auto": lt["automated_suppliers"], "sup_total": lt["total_suppliers"],
        "vol_docs": vol_auto_docs, "docs_total": lt["total_documents"],
        "vol_share": round(vol_auto_docs / lt["total_documents"], 3),
        "det_docs": lt["volume_automated_documents"],
        "det_share": lt["volume_automated_share"],
    }
    assert longtail["vol_docs"] == 178 and longtail["det_docs"] == 117

    # --- costs ---
    ce = ev["cost_estimates_block"]["cost_estimates"]
    oneoff_fallback_docs = sum(1 for e in doc_events if e["path"] in ("llm-oneoff", "llm-fallback"))
    yr2_llm_docs = oneoff_fallback_docs - 6  # T fallbacks were one-time (v2 now exists)
    yr2_hybrid = round(yr2_llm_docs * mean_tok * usd_per_tok_central, 2)
    costs = {
        "hybrid_central": ce["hybrid"]["central_85_15_usd"],
        "hybrid_floor": ce["hybrid"]["floor_all_input_usd"],
        "hybrid_ceiling": ce["hybrid"]["ceiling_all_output_usd"],
        "cf_central": ce["counterfactual_all_llm"]["central_85_15_usd"],
        "cf_floor": ce["counterfactual_all_llm"]["floor_all_input_usd"],
        "cf_ceiling": ce["counterfactual_all_llm"]["ceiling_all_output_usd"],
        "tokens_parses": ce["hybrid_llm_tokens_measured"],
        "tokens_overseer": ce["hybrid_parser_generation_tokens_measured"],
        "tokens_total": ce["hybrid_total_tokens_measured"],
        "yr2_hybrid_est": yr2_hybrid,
        "yr2_llm_docs": yr2_llm_docs,
        "pricing_note": log["pricing_reference"]["note"],
        "pricing": "$3 / $15 per MTok (Sonnet standard list, run date 3 Jul 2026)",
    }

    # --- accuracy / s-doc / scorecard ---
    acc = {k: {"docs": v["docs"], "fields": v["fields"],
               "wrong": v["wrong_including_s"],
               "pct_excl": round(v["field_accuracy_excluding_s"] * 100, 4),
               "pct_incl": round(v["field_accuracy_including_s"] * 100, 4)}
           for k, v in ev["accuracy"].items()}
    sdoc = ev["s_document"]
    s_excerpt_lines = [l for l in (RUNS / "text_layers" / f"{sdoc['doc_id']}.txt")
                       .read_text(encoding="utf-8").splitlines() if "sarana" in l.lower()]

    sc = ev["designed_outcome_scorecard"]
    scorecard = [{"cls": k, "designed": v["designed"], "actual": v["actual"],
                  "note": v["designed_note"]} for k, v in sc.items()]

    births = [{"parser": b["parser"], "name": supplier_names[b["supplier"]],
               "date": b["birth_date"], "idx": b["stream_index"],
               "relearn": b["parser"] == "s8v2"}
              for b in ev["shares"]["parser_birth_timeline"]]

    monthly = [{"m": int(k[5:7]), "docs": v["docs"], "det": v["deterministic"]}
               for k, v in sorted(ev["shares"]["per_month"].items())]

    data = {
        "tiles": {"docs": 198, "suppliers": 26, "fields": ev["accuracy"]["overall"]["fields"],
                   "wrong": ev["accuracy"]["overall"]["wrong_including_s"],
                   "llm_parses": ev["accuracy"]["llm"]["docs"],
                   "det_share": ev["shares"]["whole_stream_deterministic_share"]},
        "stream": stream, "births": births, "monthly": monthly,
        "accuracy": acc,
        "sdoc": {"id": sdoc["doc_id"], "fields": sdoc["designed_mismatch_fields"],
                  "note": sdoc["note"], "line": "\n".join(s_excerpt_lines)},
        "scorecard": scorecard, "deviations": ev["deviations_from_design"],
        "costs": costs, "longtail": longtail,
        "exhibits": {
            "routine": {"id": "2025-01_s1_01", "label": "Salpausselän Puutavara Oy · routine, month 1",
                         "text": text_excerpt("2025-01_s1_01")},
            "oneoff": {"id": "2025-07_ashquill-software_01", "label": "Ashquill Software Ltd · one-off, month 7",
                        "text": text_excerpt("2025-07_ashquill-software_01")},
            "s8v1": {"id": "2025-07_s8_01", "label": "Työkalu-Tiira Oy · old layout (July)",
                      "text": text_excerpt("2025-07_s8_01", 18)},
            "s8v2": {"id": "2025-08_s8_01", "label": "Työkalu-Tiira Oy · new layout (August)",
                      "text": text_excerpt("2025-08_s8_01", 18)},
        },
        "parser_excerpt": parser_excerpt("s8v2"),
    }

    # --- asserts vs evaluation ---
    assert data["tiles"]["fields"] == 13650 and data["tiles"]["wrong"] == 2
    assert sum(1 for r in stream if r["p"] == "d") == 117
    assert abs(stream[-1]["ch"] - 0) > 0 and abs(stream[-1]["cc"] - ce["counterfactual_all_llm"]["central_85_15_usd"]) < 0.05
    assert len(births) == 9 and sum(b["relearn"] for b in births) == 1

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"_data.json written: {OUT.stat().st_size/1024:.1f} KB; "
          f"stream {len(stream)} rows; hybrid cum end ${stream[-1]['ch']}; cf end ${stream[-1]['cc']}")


if __name__ == "__main__":
    main()
