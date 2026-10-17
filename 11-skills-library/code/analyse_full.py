"""Phase 6 measures and the twelve frozen predictions, from the marked runs.

    python code/analyse_full.py            # writes data/analysis/results.json and data/analysis/tables.md

Reads (never writes): data/analysis/marked_runs.jsonl (code/mark.py), collected_runs.jsonl (code/collect_full.py), lane_check.jsonl
(code/lane_check.py), the key (through mark.load_specs, for trap classes, twin groups and patterns), and the superseded cap-12 answers
(a side analysis only; they are never scored). Writes only into data/analysis/.

Measures (and the twelve frozen predictions):
  correctness per cell, overall and per trap class, with bootstrap 95% intervals over requests (10,000 resamples, seed 42);
  error attribution against the naive variants; consistency (all five runs agree; paraphrase pairs); adherence to definitions;
  override rigidity; the undocumented class, (a) and (b) apart; tokens per run (agent totals, not API cost); queries per run;
  skills loaded; runs told 12 or 30 queries and correctness by budget within Sonnet S.
Each prediction is scored by its exact stated rule, with the numbers.
"""
from __future__ import annotations

import collections
import json
import statistics
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mark                      # noqa: E402

CASE_ROOT = Path(__file__).resolve().parent.parent
ANALYSIS = CASE_ROOT / "data" / "analysis"
SEED = 42
BOOTSTRAP = 10_000
CELLS = ["sonnet/S", "sonnet/D", "sonnet/L", "sonnet/L-", "haiku/S", "haiku/L"]
CELL_NAME = {c: f"{c.split('/')[0].capitalize()} {c.split('/')[1]}" for c in CELLS}
TRAP_CLASSES = ["company_definition", "fiscal_calendar", "scd", "migration", "time_zone", "exclusions", "fan_out", "semi_additive", "vat",
                "ambiguous", "override", "undocumented", "clean"]
OVERRIDE_DEFAULT_VARIANT = {"REQ-T03": "stores_only_default", "REQ-T27": "as_is_region_default", "REQ-T36": "as_is_category_default", "REQ-T59": "helsinki_day_default"}
NO_TEMPLATE_PATTERNS = {9, 10, 13, 14}
SCRIPT_TARGETED = ["REQ-T22", "REQ-T25", "REQ-T31", "REQ-T45", "REQ-T51", "REQ-T15", "REQ-T39", "REQ-T56", "REQ-T12", "REQ-T28", "REQ-T48", "REQ-T42"]


def load_runs() -> pd.DataFrame:
    specs = mark.load_specs()
    marked = pd.DataFrame([json.loads(l) for l in (ANALYSIS / "marked_runs.jsonl").read_text(encoding="utf-8").splitlines()])
    collected_rows = [json.loads(l) for l in (ANALYSIS / "collected_runs.jsonl").read_text(encoding="utf-8").splitlines()]
    collected = pd.DataFrame([{k: v for k, v in r.items() if k != "answer"} for r in collected_rows]).drop(columns=["model", "arm", "request_id", "repeat"])
    lane = [json.loads(l) for l in (ANALYSIS / "lane_check.jsonl").read_text(encoding="utf-8").splitlines()]
    lane = [r for r in lane if r["role"] in ("only", "effective")]
    lane_df = pd.DataFrame([{
        "run_id": r["run_id"], "skills_opened": r["skills_opened"], "n_skills": len(r["skills_opened"]), "n_library_files": len(r["library_files_read"]),
        "library_files": r["library_files_read"], "transcript_tool_calls": sum(r["tool_counts"].values()), "api_requests": r["api_requests"],
        "api_input": r["api_usage_sum"].get("input_tokens", 0), "api_cache_write": r["api_usage_sum"].get("cache_creation_input_tokens", 0),
        "api_cache_read": r["api_usage_sum"].get("cache_read_input_tokens", 0), "api_output": r["api_usage_sum"].get("output_tokens", 0),
        "lane_flags": r["flags"], "transcripts_for_run": r["transcripts_for_run"]} for r in lane])
    df = marked.merge(collected, on="run_id", how="left").merge(lane_df, on="run_id", how="left")
    df["cell"] = df["model"] + "/" + df["arm"]
    df["answer"] = df["run_id"].map({r["run_id"]: r["answer"] for r in collected_rows})
    df["correct"] = (df["outcome"] == "correct").astype(int)
    df["correct_strict"] = (df["outcome_strict"] == "correct").astype(int)
    df["trap_classes"] = df["request_id"].map(lambda r: specs[r].trap_classes)
    df["pattern"] = df["request_id"].map(lambda r: specs[r].pattern)
    df["twin_group"] = df["request_id"].map(lambda r: specs[r].twin_group)
    return df, specs


def request_matrix(df: pd.DataFrame, column: str = "correct") -> pd.DataFrame:
    """Rows: requests; columns: cells; values: runs correct out of 5."""
    pivot = df.pivot_table(index="request_id", columns="cell", values=column, aggfunc="sum")
    return pivot[CELLS]


def bootstrap_ci(per_request: np.ndarray, rng: np.random.Generator, runs_per_request: int = 5) -> tuple:
    """Run-level correctness with a 95% interval from resampling requests (equal weights, so run-level = mean of request means)."""
    n = len(per_request)
    draws = rng.integers(0, n, size=(BOOTSTRAP, n))
    means = per_request[draws].mean(axis=1) / runs_per_request
    return float(per_request.mean() / runs_per_request), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def paired_bootstrap_diff(a: np.ndarray, b: np.ndarray, rng: np.random.Generator) -> tuple:
    n = len(a)
    draws = rng.integers(0, n, size=(BOOTSTRAP, n))
    diffs = (a[draws].mean(axis=1) - b[draws].mean(axis=1)) / 5
    return float((a.mean() - b.mean()) / 5), float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


# ---------------------------------------------------------------------------
# Correctness
# ---------------------------------------------------------------------------

def correctness_tables(df: pd.DataFrame, specs: dict) -> dict:
    rng = np.random.default_rng(SEED)
    matrix = request_matrix(df)
    out = {"overall": {}, "by_class": {}, "strict_overall": {}}
    for cell in CELLS:
        per_request = matrix[cell].to_numpy(dtype=float)
        p, lo, hi = bootstrap_ci(per_request, rng)
        out["overall"][CELL_NAME[cell]] = {"correct": int(per_request.sum()), "runs": int(5 * len(per_request)), "share": p, "ci_low": lo, "ci_high": hi}
    strict = request_matrix(df, "correct_strict")
    for cell in CELLS:
        out["strict_overall"][CELL_NAME[cell]] = int(strict[cell].sum())
    class_requests = {cls: sorted(r for r, s in specs.items() if cls in s.trap_classes) for cls in TRAP_CLASSES}
    for cls, requests in class_requests.items():
        row = {"requests": len(requests), "request_ids": requests}
        for cell in CELLS:
            per_request = matrix.loc[requests, cell].to_numpy(dtype=float)
            p, lo, hi = bootstrap_ci(per_request, rng)
            row[CELL_NAME[cell]] = {"correct": int(per_request.sum()), "runs": int(5 * len(requests)), "share": p, "ci_low": lo, "ci_high": hi}
        out["by_class"][cls] = row
    out["trapped_vs_clean"] = {}
    trapped = [r for r, s in specs.items() if "clean" not in s.trap_classes]
    for label, requests in (("trapped (46 requests)", trapped), ("clean (14 requests)", class_requests["clean"])):
        out["trapped_vs_clean"][label] = {CELL_NAME[c]: int(matrix.loc[requests, c].sum()) for c in CELLS} | {"runs": 5 * len(requests)}
    out["per_request"] = {r: {CELL_NAME[c]: int(matrix.loc[r, c]) for c in CELLS} for r in matrix.index}
    return out


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------

def attribution_tables(df: pd.DataFrame) -> dict:
    wrong = df[df["outcome"] != "correct"]
    out = {}
    for cell in CELLS:
        sub = wrong[wrong["cell"] == cell]
        out[CELL_NAME[cell]] = dict(collections.Counter(sub["attribution"].fillna("other")))
    return out


# ---------------------------------------------------------------------------
# Consistency
# ---------------------------------------------------------------------------

def signature(table: dict) -> dict:
    """Drop columns that carry nothing (constant over several rows, or all empty): a fiscal_year column repeated on every row."""
    columns, rows = table["columns"], table["rows"]
    keep = []
    for index in range(len(columns)):
        values = [row[index] for row in rows]
        if all(v is None for v in values):
            continue
        if len(rows) > 1 and len({json.dumps(v) for v in values}) == 1:
            continue
        keep.append(index)
    return {"columns": [columns[i] for i in keep], "rows": [[row[i] for i in keep] for row in rows]}


def covers(narrow: dict, wide: dict, ordered: bool) -> bool:
    """Is every column of `narrow` found, by its values, in `wide`, with the rows lining up? Strict: no totals, no zero rows, no rounding leniency."""
    if not narrow["rows"] or len(narrow["rows"]) != len(wide["rows"]) or not narrow["columns"]:
        return False
    specs = [{"name": name, "role": "dimension" if any(isinstance(r[i], str) for r in narrow["rows"]) else "measure", "unit": ""}
             for i, name in enumerate(narrow["columns"])]
    variant = mark.Variant(kind="naive", ident="x", label="x", table=narrow, column_specs=specs, ordered=ordered, required=list(narrow["columns"]))
    prepared = mark.Prepared(list(wide["columns"]), [list(r) for r in wide["rows"]])
    return mark.match_variant(variant, prepared, frozenset())[0]


def same_result(a: dict, b: dict, ordered: bool) -> bool:
    a, b = signature(a), signature(b)
    if len(a["columns"]) > len(b["columns"]):
        a, b = b, a
    return covers(a, b, ordered)


def cluster_runs(runs: list, spec) -> list:
    """Group the runs of one request in one cell by the result they returned. A run with no answer is its own group (it breaks agreement).
    Correct runs are grouped by the accepted result they matched; wrong runs by table equality."""
    clusters = []     # {"label": ..., "table": ..., "run_ids": [...]}
    for run in runs:
        answer = run["answer"]
        if run["outcome_strict"] == "no_answer" or answer is None:
            clusters.append({"label": f"none:{run['run_id']}", "table": None, "run_ids": [run["run_id"]], "correct": False})
            continue
        table = answer["result"]
        if run["outcome"] == "correct":
            label = run["matched"] or "correct"
            for cluster in clusters:
                if cluster["label"] == label:
                    cluster["run_ids"].append(run["run_id"])
                    break
            else:
                clusters.append({"label": label, "table": table, "run_ids": [run["run_id"]], "correct": True})
            continue
        for cluster in clusters:
            if not cluster["correct"] and cluster["table"] is not None and same_result(cluster["table"], table, spec.ordered):
                cluster["run_ids"].append(run["run_id"])
                break
        else:
            clusters.append({"label": f"wrong:{run['run_id']}", "table": table, "run_ids": [run["run_id"]], "correct": False})
    return clusters


def majority(clusters: list):
    for cluster in clusters:
        if len(cluster["run_ids"]) >= 3:
            return cluster
    return None


def consistency_tables(df: pd.DataFrame, specs: dict) -> dict:
    out = {"all_five_agree": {}, "correct_in_all_five": {}, "paraphrase_pairs_agree": {}, "paraphrase_detail": {}, "agree_by_class": {}}
    twin_groups = collections.defaultdict(list)
    for request_id, spec in specs.items():
        if spec.twin_group:
            twin_groups[spec.twin_group].append(request_id)
    for cell in CELLS:
        sub = df[df["cell"] == cell]
        by_request = {}
        agree, reliable = [], []
        majorities = {}
        for request_id, group in sub.groupby("request_id"):
            runs = group.sort_values("repeat").to_dict("records")
            clusters = cluster_runs(runs, specs[request_id])
            by_request[request_id] = clusters
            agree.append(request_id) if len(clusters) == 1 and not clusters[0]["label"].startswith("none") else None
            reliable.append(request_id) if all(r["outcome"] == "correct" for r in runs) else None
            majorities[request_id] = majority(clusters)
        out["all_five_agree"][CELL_NAME[cell]] = {"requests": len(agree), "request_ids": sorted(agree)}
        out["correct_in_all_five"][CELL_NAME[cell]] = {"requests": len(reliable), "request_ids": sorted(reliable)}
        pairs_agree, detail = 0, {}
        for group, ids in sorted(twin_groups.items()):
            a, b = ids
            ma, mb = majorities[a], majorities[b]
            if ma is None or mb is None:
                verdict = False
            elif ma["correct"] and mb["correct"]:
                verdict = ma["label"] == mb["label"]
            elif (not ma["correct"]) and (not mb["correct"]):
                verdict = same_result(ma["table"], mb["table"], specs[a].ordered)
            else:
                verdict = False
            pairs_agree += int(verdict)
            detail[group] = {"requests": ids, "agree": verdict, "majority_a": None if ma is None else ("correct" if ma["correct"] else "wrong"),
                             "majority_b": None if mb is None else ("correct" if mb["correct"] else "wrong")}
        out["paraphrase_pairs_agree"][CELL_NAME[cell]] = pairs_agree
        out["paraphrase_detail"][CELL_NAME[cell]] = detail
    return out


# ---------------------------------------------------------------------------
# Definitions, overrides, undocumented
# ---------------------------------------------------------------------------

def definitions_tables(df: pd.DataFrame, specs: dict) -> dict:
    requests = sorted(r for r, s in specs.items() if "company_definition" in s.trap_classes)
    out = {"requests": requests, "cells": {}}
    for cell in CELLS:
        sub = df[(df["cell"] == cell) & (df["request_id"].isin(requests))]
        naive_applied = int(sub["naive_matches"].map(lambda m: len(m) > 0).sum())
        out["cells"][CELL_NAME[cell]] = {"runs": len(sub), "correct": int(sub["correct"].sum()), "naive_variant_applied": naive_applied}
    return out


def override_tables(df: pd.DataFrame) -> dict:
    out = {"requests": OVERRIDE_DEFAULT_VARIANT, "cells": {}}
    for cell in CELLS:
        sub = df[(df["cell"] == cell) & (df["request_id"].isin(OVERRIDE_DEFAULT_VARIANT))]
        detail = {}
        total_default = 0
        for request_id, variant in OVERRIDE_DEFAULT_VARIANT.items():
            group = sub[sub["request_id"] == request_id]
            default_runs = int(group["naive_matches"].map(lambda m: variant in m).sum())
            total_default += default_runs
            detail[request_id] = {"correct": int(group["correct"].sum()), "default_applied_against_request": default_runs}
        out["cells"][CELL_NAME[cell]] = {"runs": len(sub), "correct": int(sub["correct"].sum()), "default_applied": total_default, "by_request": detail}
    return out


def undocumented_tables(df: pd.DataFrame) -> dict:
    requests = ["REQ-T12", "REQ-T16", "REQ-T42", "REQ-T55"]
    out = {"requests": requests, "cells": {}}
    for cell in CELLS:
        sub = df[(df["cell"] == cell) & (df["request_id"].isin(requests))]
        row = {"runs": len(sub), "a_repaired": int((sub["route"] == "undocumented_a").sum()),
               "b_flagged": int(((sub["route"] == "undocumented_b") & (sub["outcome"] == "correct")).sum()),
               "b_flagged_strict_keywords_only": int(((sub["route"] == "undocumented_b") & (sub["outcome_strict"] == "correct")).sum()), "by_request": {}}
        # a run adjudicated from wrong to correct has no route in the strict mark: take it from the matched field
        adjudicated_b = int(((sub["outcome"] == "correct") & (sub["outcome_strict"] != "correct") & (sub["matched"] == "undocumented_b:undocumented_b")).sum())
        row["b_flagged"] = int(((sub["outcome"] == "correct") & (sub["matched"] == "undocumented_b:undocumented_b")).sum())
        row["correct_total"] = int(sub["correct"].sum())
        row["c_published_without_warning"] = int((sub["attribution"] == "published_without_warning").sum() - ((sub["outcome"] == "correct") & (sub["attribution"] == "published_without_warning")).sum())
        for request_id in requests:
            group = sub[sub["request_id"] == request_id]
            row["by_request"][request_id] = {"correct": int(group["correct"].sum()),
                                             "a": int((group["route"] == "undocumented_a").sum()),
                                             "b": int(((group["outcome"] == "correct") & (group["matched"] == "undocumented_b:undocumented_b")).sum()),
                                             "c_published_no_warning": int(((group["outcome"] != "correct") & (group["attribution"] == "published_without_warning")).sum())}
        out["cells"][CELL_NAME[cell]] = row
    return out


# ---------------------------------------------------------------------------
# Cost-ish: tokens, queries, skills
# ---------------------------------------------------------------------------

def pearson(x: np.ndarray, y: np.ndarray) -> float:
    """Pearson correlation without np.corrcoef (this environment's BLAS library crashes on it)."""
    x, y = x - x.mean(), y - y.mean()
    return float((x * y).sum() / np.sqrt((x * x).sum() * (y * y).sum()))


def token_tables(df: pd.DataFrame) -> dict:
    out = {"note": "Agent totals as the Agent tool reported them for each run. Not API cost: the make-up (input, cache reads, output) is not given and Claude Code's own overhead is inside.", "cells": {}}
    for cell in CELLS:
        sub = df[df["cell"] == cell]
        tokens = sub["total_tokens"].astype(float)
        correct = int(sub["correct"].sum())
        out["cells"][CELL_NAME[cell]] = {"median": float(tokens.median()), "mean": float(tokens.mean()), "p25": float(tokens.quantile(0.25)), "p75": float(tokens.quantile(0.75)),
                                         "min": float(tokens.min()), "max": float(tokens.max()), "total": float(tokens.sum()), "per_correct_answer": float(tokens.sum() / correct) if correct else None,
                                         "median_tool_calls_reported": float(sub["tool_calls_reported"].astype(float).median()), "median_duration_s": float(sub["duration_s"].astype(float).median())}
    sonnet = df[df["model"] == "sonnet"]
    out["by_arm_sonnet_median"] = {arm: float(sonnet[sonnet["arm"] == arm]["total_tokens"].median()) for arm in ("S", "D", "L", "L-")}
    # the make-up from the transcripts' API usage, to say what an agent total is
    comp = df.copy()
    comp["api_sum_in_out_write"] = comp["api_input"] + comp["api_cache_write"] + comp["api_output"]
    comp["api_sum_all"] = comp["api_sum_in_out_write"] + comp["api_cache_read"]
    comp["ratio_total_to_inout_write"] = comp["total_tokens"] / comp["api_sum_in_out_write"]
    comp["ratio_total_to_all"] = comp["total_tokens"] / comp["api_sum_all"]
    out["composition"] = {"median_ratio_reported_to_(input+cache_write+output)": float(comp["ratio_total_to_inout_write"].median()),
                          "median_ratio_reported_to_(input+cache_write+cache_read+output)": float(comp["ratio_total_to_all"].median()),
                          "median_cache_read_tokens_per_run": float(comp["api_cache_read"].median()), "median_output_tokens_per_run": float(comp["api_output"].median()),
                          "median_api_requests_per_run": float(comp["api_requests"].median()),
                          "correlation_reported_vs_(input+cache_write+output)": pearson(comp["total_tokens"].to_numpy(dtype=float), comp["api_sum_in_out_write"].to_numpy(dtype=float))}
    return out


def query_tables(df: pd.DataFrame) -> dict:
    out = {}
    for cell in CELLS:
        sub = df[df["cell"] == cell]
        out[CELL_NAME[cell]] = {"mean": float(sub["queries_used"].mean()), "median": float(sub["queries_used"].median()), "max": int(sub["queries_used"].max()),
                                "ran_all_budget": int((sub["queries_used"] >= sub["told_budget"]).sum()), "mean_scripts_calls": float(sub["script_calls"].mean()),
                                "runs_with_a_script": int((sub["script_calls"] > 0).sum()), "failed_calls_mean": float(sub["calls_failed"].mean())}
    return out


def skill_tables(df: pd.DataFrame) -> dict:
    out = {}
    for cell in ["sonnet/L", "sonnet/L-", "haiku/L"]:
        sub = df[df["cell"] == cell]
        counter = collections.Counter(s for skills in sub["skills_opened"] for s in skills)
        files = collections.Counter(f for fs in sub["library_files"] for f in fs)
        scripts = collections.Counter(sc for sl in sub["scripts_run"] for sc in sl)
        out[CELL_NAME[cell]] = {"mean_skills_opened": float(sub["n_skills"].mean()), "median_skills_opened": float(sub["n_skills"].median()), "max_skills_opened": int(sub["n_skills"].max()),
                                "runs_over_6_skills": int((sub["n_skills"] > 6).sum()), "mean_library_files": float(sub["n_library_files"].mean()), "max_library_files": int(sub["n_library_files"].max()),
                                "skill_open_counts": dict(counter.most_common()), "digest_opened": int(sum(any("request_history_digest" in f for f in fs) for fs in sub["library_files"])),
                                "scripts_run": dict(scripts), "runs_with_script": int((sub["script_calls"] > 0).sum()),
                                "skills_opened_correct_vs_wrong": {"correct": float(sub[sub["correct"] == 1]["n_skills"].mean()), "wrong": float(sub[sub["correct"] == 0]["n_skills"].mean()) if (sub["correct"] == 0).any() else None}}
    return out


def budget_tables(df: pd.DataFrame) -> dict:
    out = {"told_by_cell": {}, "sonnet_S_by_budget": {}}
    for cell in CELLS:
        sub = df[df["cell"] == cell]
        out["told_by_cell"][CELL_NAME[cell]] = {"told_12": int((sub["told_budget"] == 12).sum()), "told_30": int((sub["told_budget"] == 30).sum()),
                                                "reruns_of_capped": int(sub["rerun_of_cap"].sum())}
    s = df[df["cell"] == "sonnet/S"]
    for label, mask in (("told 12", s["told_budget"] == 12), ("told 30 (all)", s["told_budget"] == 30),
                        ("told 30, re-runs of capped runs", (s["told_budget"] == 30) & s["rerun_of_cap"]),
                        ("told 30, first pass (rounds 39-60)", (s["told_budget"] == 30) & ~s["rerun_of_cap"])):
        g = s[mask]
        out["sonnet_S_by_budget"][label] = {"runs": len(g), "correct": int(g["correct"].sum()), "share": float(g["correct"].mean()) if len(g) else None,
                                            "mean_queries": float(g["queries_used"].mean()) if len(g) else None}
    # the same comparison with the request mix held fixed: per request, told-12 share vs told-30 share, averaged over requests that have both
    paired = []
    for request_id, g in s.groupby("request_id"):
        a, b = g[g["told_budget"] == 12], g[g["told_budget"] == 30]
        if len(a) and len(b):
            paired.append((a["correct"].mean(), b["correct"].mean(), len(a), len(b)))
    out["sonnet_S_paired_by_request"] = {"requests_with_both": len(paired), "mean_share_told_12": float(np.mean([p[0] for p in paired])), "mean_share_told_30": float(np.mean([p[1] for p in paired]))}
    for model in ("sonnet", "haiku"):
        for arm in ("S", "D", "L", "L-"):
            g = df[(df["model"] == model) & (df["arm"] == arm)]
            if len(g) == 0:
                continue
            out.setdefault("all_cells_by_budget", {})[CELL_NAME[f"{model}/{arm}"]] = {str(b): {"runs": int((g["told_budget"] == b).sum()), "correct": int(g[g["told_budget"] == b]["correct"].sum())} for b in (12, 30)}
    return out


def route_tables(df: pd.DataFrame) -> dict:
    """Which accepted result each correct run matched (reference, an alternative, a reading, outcome b)."""
    out = {}
    for cell in CELLS:
        sub = df[(df["cell"] == cell) & (df["outcome"] == "correct")]
        out[CELL_NAME[cell]] = dict(collections.Counter(sub["matched"].map(lambda m: (m or "").split(":")[0])))
    alt_by_request = {}
    for cell in CELLS:
        sub = df[(df["cell"] == cell) & (df["outcome"] == "correct") & (df["matched"].fillna("").str.startswith("alternative"))]
        for request_id, n in sub["request_id"].value_counts().items():
            alt_by_request.setdefault(request_id, {})[CELL_NAME[cell]] = int(n)
    out["_alternative_hits_by_request"] = alt_by_request
    return out


# ---------------------------------------------------------------------------
# Predictions
# ---------------------------------------------------------------------------

def score_predictions(df: pd.DataFrame, specs: dict, correctness: dict, consistency: dict, definitions: dict, override: dict, undocumented: dict, tokens: dict) -> list:
    def c(model, arm, requests=None):
        sub = df[(df["model"] == model) & (df["arm"] == arm)]
        if requests is not None:
            sub = sub[sub["request_id"].isin(requests)]
        return int(sub["correct"].sum()), len(sub)

    results = []
    s, d, l = c("sonnet", "S")[0], c("sonnet", "D")[0], c("sonnet", "L")[0]
    ok = (75 <= s <= 150) and (195 <= d <= 255) and (195 <= l <= 255)
    results.append({"n": 1, "title": "Overall correctness", "rule": "S between 75 and 150 correct runs of 300; D and L each between 195 and 255.", "met": ok,
                    "numbers": f"S {s}/300 ({s/3:.1f}%), D {d}/300 ({d/3:.1f}%), L {l}/300 ({l/3:.1f}%). S in band: {75 <= s <= 150}; D in band: {195 <= d <= 255}; L in band: {195 <= l <= 255}."})
    ok = ((d - s) / 300 * 100 >= 30) and (-5 <= (l - d) / 300 * 100 <= 5)
    results.append({"n": 2, "title": "Where the gain comes from", "rule": "(D - S) >= 30 pp and -5 pp <= (L - D) <= +5 pp.", "met": ok,
                    "numbers": f"D - S = {(d - s) / 3:.1f} pp; L - D = {(l - d) / 3:.1f} pp."})
    clean = sorted(r for r, sp in specs.items() if "clean" in sp.trap_classes)
    cs, cd, cl = c("sonnet", "S", clean)[0], c("sonnet", "D", clean)[0], c("sonnet", "L", clean)[0]
    ok = min(cs, cd, cl) >= 60 and (max(cs, cd, cl) - min(cs, cd, cl)) <= 5
    results.append({"n": 3, "title": "Clean requests", "rule": "S, D and L each >= 60 correct of 70 on the 14 clean requests, and best minus worst <= 5 runs.", "met": ok,
                    "numbers": f"S {cs}/70, D {cd}/70, L {cl}/70; spread {max(cs, cd, cl) - min(cs, cd, cl)} runs."})
    a = consistency["all_five_agree"]
    sa, da, la = a["Sonnet S"]["requests"], a["Sonnet D"]["requests"], a["Sonnet L"]["requests"]
    ok = da >= 39 and la >= 39 and sa <= 27
    results.append({"n": 4, "title": "Same answer every time", "rule": "Requests (of 60) with five matching runs: D >= 39, L >= 39, S <= 27.", "met": ok,
                    "numbers": f"S {sa}, D {da}, L {la} of 60."})
    p = consistency["paraphrase_pairs_agree"]
    ok = p["Sonnet D"] >= 7 and p["Sonnet L"] >= 7 and p["Sonnet S"] <= 5
    results.append({"n": 5, "title": "Two departments, one number", "rule": "Paraphrase pairs (of 10) with the same majority result: D >= 7, L >= 7, S <= 5.", "met": ok,
                    "numbers": f"S {p['Sonnet S']}, D {p['Sonnet D']}, L {p['Sonnet L']} of 10."})
    dcs = definitions["cells"]
    ok = dcs["Sonnet D"]["correct"] >= 45 and dcs["Sonnet L"]["correct"] >= 45 and dcs["Sonnet S"]["correct"] <= 12
    results.append({"n": 6, "title": "Company definitions", "rule": "On the 12 company-definition requests (60 runs per arm): D >= 45 correct, L >= 45, S <= 12.", "met": ok,
                    "numbers": f"S {dcs['Sonnet S']['correct']}/60, D {dcs['Sonnet D']['correct']}/60, L {dcs['Sonnet L']['correct']}/60."})
    oc = override["cells"]
    ok = oc["Sonnet D"]["default_applied"] <= 2 and oc["Sonnet L"]["default_applied"] <= 2
    results.append({"n": 7, "title": "Rigidity", "rule": "On the 4 override requests (20 runs per arm): D and L each have at most 2 runs matching the default-applied naive variant.", "met": ok,
                    "numbers": f"D {oc['Sonnet D']['default_applied']}/20, L {oc['Sonnet L']['default_applied']}/20 (S {oc['Sonnet S']['default_applied']}/20 for reference)."})
    uc = undocumented["cells"]
    l_all = uc["Sonnet L"]["correct_total"]
    l_wo_t16 = l_all - uc["Sonnet L"]["by_request"]["REQ-T16"]["correct"]
    s_all = uc["Sonnet S"]["correct_total"]
    ok = (l_all >= 8) and (s_all <= 3) and (l_wo_t16 <= 7)
    results.append({"n": 8, "title": "Problems nobody wrote down", "rule": "Fix-or-flag scoring: L >= 8 of its 20 undocumented-issue runs right, S <= 3, and without REQ-T16 L <= 7 of the remaining 15.", "met": ok,
                    "numbers": f"L {l_all}/20 (repaired {uc['Sonnet L']['a_repaired']}, flagged {uc['Sonnet L']['b_flagged']}); S {s_all}/20 (repaired {uc['Sonnet S']['a_repaired']}, flagged {uc['Sonnet S']['b_flagged']}); L without T16 {l_wo_t16}/15."})
    t = tokens["cells"]
    ts, td, tl = t["Sonnet S"]["median"], t["Sonnet D"]["median"], t["Sonnet L"]["median"]
    ok = (ts < td < tl) and tl <= 1.15 * td
    results.append({"n": 9, "title": "Token use", "rule": "Median agent tokens per run S < D < L, and L <= 1.15 x D.", "met": ok,
                    "numbers": f"S {ts:,.0f}, D {td:,.0f}, L {tl:,.0f}; L/D = {tl / td:.3f}; S < D: {ts < td}; D < L: {td < tl}."})
    hl, ss, sl = c("haiku", "L")[0], s, l
    ok = ((hl - ss) / 300 * 100 >= 10) and ((sl - hl) / 300 * 100 >= 5)
    results.append({"n": 10, "title": "Small model with the library", "rule": "(Haiku L - Sonnet S) >= 10 pp and (Sonnet L - Haiku L) >= 5 pp.", "met": ok,
                    "numbers": f"Haiku L {hl}/300 ({hl / 3:.1f}%), Sonnet S {ss}/300 ({ss / 3:.1f}%), Sonnet L {sl}/300 ({sl / 3:.1f}%); Haiku L - Sonnet S = {(hl - ss) / 3:.1f} pp; Sonnet L - Haiku L = {(sl - hl) / 3:.1f} pp."})
    lm = c("sonnet", "L-")[0]
    tl_correct, tm_correct = c("sonnet", "L", SCRIPT_TARGETED)[0], c("sonnet", "L-", SCRIPT_TARGETED)[0]
    ok = (abs(l - lm) / 300 * 100 <= 5) and ((tl_correct - tm_correct) < 6)
    results.append({"n": 11, "title": "Scripts", "rule": "|L - L-| <= 5 pp overall, and on the 12 script-targeted requests (60 runs) L has fewer than 6 more correct runs than L-.", "met": ok,
                    "numbers": f"L {l}/300, L- {lm}/300 (gap {(l - lm) / 3:+.1f} pp); on the 12 requests L {tl_correct}/60, L- {tm_correct}/60 (L - L- = {tl_correct - tm_correct:+d})."})
    no_template = sorted(r for r, sp in specs.items() if sp.pattern in NO_TEMPLATE_PATTERNS)
    rest = sorted(r for r in specs if r not in no_template)
    a13, n13 = c("sonnet", "L", no_template)
    a47, n47 = c("sonnet", "L", rest)
    ok = (a47 / n47 - a13 / n13) * 100 >= 10
    results.append({"n": 12, "title": "Requests the library was not built for", "rule": f"L's correct share on the {len(no_template)} no-template requests is at least 10 pp below its share on the other {len(rest)}.", "met": ok,
                    "numbers": f"No-template {a13}/{n13} ({a13 / n13 * 100:.1f}%), other {a47}/{n47} ({a47 / n47 * 100:.1f}%); gap {(a47 / n47 - a13 / n13) * 100:+.1f} pp (no-template requests: {', '.join(no_template)})."})
    return results


def contrast_tables(df: pd.DataFrame) -> dict:
    """Differences between cells in percentage points, with a paired bootstrap interval over requests."""
    rng = np.random.default_rng(SEED + 1)
    matrix = request_matrix(df)
    pairs = [("sonnet/D", "sonnet/S"), ("sonnet/L", "sonnet/S"), ("sonnet/L-", "sonnet/S"), ("sonnet/L", "sonnet/D"), ("sonnet/L", "sonnet/L-"), ("sonnet/D", "sonnet/L-"),
             ("haiku/L", "haiku/S"), ("haiku/L", "sonnet/S"), ("sonnet/L", "haiku/L"), ("sonnet/S", "haiku/S")]
    out = {}
    for a, b in pairs:
        diff, lo, hi = paired_bootstrap_diff(matrix[a].to_numpy(dtype=float), matrix[b].to_numpy(dtype=float), rng)
        out[f"{CELL_NAME[a]} minus {CELL_NAME[b]}"] = {"pp": diff * 100, "ci_low_pp": lo * 100, "ci_high_pp": hi * 100}
    return out


DOUBLE_LAUNCHED = ["full-haiku-S-t37-r3", "full-sonnet-L-t03-r3", "full-haiku-S-t50-r3", "full-haiku-S-t59-r5", "full-sonnet-D-t10-r4", "full-sonnet-D-t24-r1", "full-sonnet-L-t14-r2"]


def remark(df: pd.DataFrame, specs: dict, maps: "mark.NameMaps", features: frozenset) -> pd.DataFrame:
    """The same runs marked again with some leniencies switched off (keyword rules only, no adjudication)."""
    rows = mark.load_collected()
    marks = mark.mark_all(rows, specs, maps, features)
    out = df.copy()
    for column, getter in (("outcome", lambda m: m.outcome), ("matched", lambda m: m.matched), ("route", lambda m: m.route),
                           ("naive_matches", lambda m: m.naive_matches), ("attribution", lambda m: m.attribution)):
        out[column] = out["run_id"].map(lambda r: getter(marks[r]))
    out["outcome_strict"] = out["outcome"]
    out["correct"] = (out["outcome"] == "correct").astype(int)
    return out


def prediction_sensitivity(df: pd.DataFrame, specs: dict, maps: "mark.NameMaps", tokens: dict) -> dict:
    """Do the verdicts change if the contestable marker choices go the other way, or the seven double-launched runs are left out?"""
    variants = {}
    keyword_only = df.copy()
    keyword_only["outcome"] = keyword_only["outcome_strict"]
    keyword_only["correct"] = keyword_only["correct_strict"]
    variants["keyword rules only (no adjudication)"] = keyword_only
    variants["alternatives off (reference result only)"] = remark(df, specs, maps, mark.FEATURES - {"alternatives"})
    variants["all eight leniencies off"] = remark(df, specs, maps, frozenset())
    variants["without the seven double-launched runs"] = df[~df["run_id"].isin(DOUBLE_LAUNCHED)]
    out = {}
    for label, frame in variants.items():
        consistency = consistency_tables(frame, specs)
        definitions = definitions_tables(frame, specs)
        override = override_tables(frame)
        undocumented = undocumented_tables(frame)
        scored = score_predictions(frame, specs, {}, consistency, definitions, override, undocumented, tokens)
        out[label] = {"cells": {CELL_NAME[c]: [int(frame[frame["cell"] == c]["correct"].sum()), int((frame["cell"] == c).sum())] for c in CELLS},
                      "verdicts": {p["n"]: ("MET" if p["met"] else "NOT MET") for p in scored}, "numbers": {p["n"]: p["numbers"] for p in scored}}
    return out



# ---------------------------------------------------------------------------
# Extras: what the numbers lean on
# ---------------------------------------------------------------------------

def answer_text(answer: dict) -> str:
    return "\n".join(mark.text_of(answer.get(key)) for key in ("definitions_applied", "assumptions", "caveats")) if answer else ""


def extras_tables(df: pd.DataFrame, specs: dict, maps: "mark.NameMaps") -> dict:
    import re
    out = {}
    # 1. How often an answer cites a past (dev) request by its id: the dev history was in the material of D and L.
    out["cites_a_dev_request"] = {}
    for cell in CELLS:
        sub = df[df["cell"] == cell]
        cites = sub["answer"].map(lambda a: bool(re.search(r"req-d\d+", answer_text(a))))
        out["cites_a_dev_request"][CELL_NAME[cell]] = {"runs": int(cites.sum()), "of": len(sub),
                                                      "correct_when_citing": int(sub[cites]["correct"].sum()), "correct_when_not": int(sub[~cites]["correct"].sum()),
                                                      "not_citing": int((~cites).sum())}
    # 1b. Of the runs that repaired an undocumented incident (outcome a), how many also said so in caveats (the key's keyword rule for outcome b)
    out["repaired_and_said_so"] = {}
    for cell in CELLS:
        per_request = {}
        for request_id in ("REQ-T12", "REQ-T16", "REQ-T42", "REQ-T55"):
            rule = next(v.caveat_rule for v in specs[request_id].accepted if v.kind == "undocumented_b")
            sub = df[(df["cell"] == cell) & (df["request_id"] == request_id) & (df["route"] == "undocumented_a")]
            said = sum(mark.rule_passes(rule, mark.text_of(a.get("caveats"))) for a in sub["answer"] if a)
            per_request[request_id] = [int(said), len(sub)]
        out["repaired_and_said_so"][CELL_NAME[cell]] = per_request
    # 2. query_check.py flags in the L arms, from the counter previews, and what the run then did
    out["query_check"] = {}
    for cell in ["sonnet/L", "haiku/L"]:
        sub = df[df["cell"] == cell]
        flagged, flagged_correct, ran = 0, 0, 0
        flagged_by_request = collections.Counter()
        for _, row in sub.iterrows():
            counter = json.loads((CASE_ROOT / "data" / "agent_runs" / "counters" / f"{row['run_id']}.json").read_text(encoding="utf-8"))
            outputs = [c.get("output_preview", "") for c in counter["calls"] if c["kind"] == "script" and "query_check" in c["statement"]]
            if outputs:
                ran += 1
            if any("[FAIL]" in o for o in outputs):
                flagged += 1
                flagged_correct += int(row["correct"])
                flagged_by_request[row["request_id"]] += 1
        out["query_check"][CELL_NAME[cell]] = {"runs_that_ran_query_check": ran, "runs_with_a_FAIL_line": flagged, "of_those_correct": flagged_correct,
                                               "FAIL_runs_by_request": dict(flagged_by_request.most_common())}
    # 3. Marker choices that could be reversed, and what each is worth
    t45 = df[(df["request_id"] == "REQ-T45")]
    def has_value_near(answer):
        try:
            return any(isinstance(v, (int, float)) and 4400 <= v <= 4480 for row in answer["result"]["rows"] for v in row)
        except Exception:
            return False
    third = t45[t45["answer"].map(has_value_near)]
    out["t45_active_members_in_tampere_reading"] = {"reading": "active members (purchase in trailing 52 weeks) whose home store is in Tampere, about 4,441; not in the key", "runs": {CELL_NAME[c]: int((third["cell"] == c).sum()) for c in CELLS}}
    t29 = df[(df["request_id"] == "REQ-T29") & (df["attribution"] == "percent_as_fraction")]
    out["t29_vat_rate_written_as_fraction"] = {"runs": {CELL_NAME[c]: int((t29["cell"] == c).sum()) for c in CELLS}}
    return out


def cap12_side_analysis(df: pd.DataFrame, specs: dict, maps: "mark.NameMaps") -> dict:
    """The 38 runs that used all 12 queries under the old ceiling were run again under 30. The old answers are not scored. This marks them
    for comparison only: did the ceiling decide the answer?"""
    import collect_agent_answer as pilot_collect
    folder = CASE_ROOT / "data" / "agent_runs" / "superseded_cap12"
    index = json.loads((folder / "INDEX.json").read_text(encoding="utf-8"))
    rows = []
    for entry in index["runs"]:
        run_id = entry["run_id"]
        text = (folder / "finals" / f"final-{run_id}.txt").read_text(encoding="utf-8")
        answer, problem, _ = pilot_collect.parse_agent_message(text)
        status = "ok" if answer is not None else "malformed"
        old = mark.mark_answer(specs[entry["request_id"]], answer, status, maps)
        new_row = df[df["run_id"] == run_id].iloc[0]
        rows.append({"run_id": run_id, "cell": f"{entry['agent_model']}/{entry['arm']}", "old_outcome": old.outcome, "old_status": status, "new_outcome": new_row["outcome"]})
    frame = pd.DataFrame(rows)
    out = {"runs": len(frame), "by_cell": {}}
    for cell, g in frame.groupby("cell"):
        out["by_cell"][CELL_NAME[cell]] = {"runs": len(g), "old_correct": int((g["old_outcome"] == "correct").sum()), "old_no_usable_answer": int((g["old_status"] != "ok").sum()),
                                          "new_correct": int((g["new_outcome"] == "correct").sum())}
    out["transitions"] = dict(collections.Counter(zip(frame["old_outcome"], frame["new_outcome"])).most_common())
    out["transitions"] = {f"{a} -> {b}": n for (a, b), n in collections.Counter(zip(frame["old_outcome"], frame["new_outcome"])).items()}
    return out


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    df, specs = load_runs()
    print(f"{len(df)} runs loaded")
    correctness = correctness_tables(df, specs)
    attribution = attribution_tables(df)
    contrasts = contrast_tables(df)
    consistency = consistency_tables(df, specs)
    definitions = definitions_tables(df, specs)
    override = override_tables(df)
    undocumented = undocumented_tables(df)
    tokens = token_tables(df)
    queries = query_tables(df)
    skills = skill_tables(df)
    budget = budget_tables(df)
    routes = route_tables(df)
    maps = mark.NameMaps.from_warehouse()
    extras = extras_tables(df, specs, maps)
    cap12 = cap12_side_analysis(df, specs, maps)
    predictions = score_predictions(df, specs, correctness, consistency, definitions, override, undocumented, tokens)
    sensitivity = prediction_sensitivity(df, specs, maps, tokens)
    results = {"correctness": correctness, "attribution": attribution, "consistency": consistency, "definitions": definitions, "override": override,
               "undocumented": undocumented, "tokens": tokens, "queries": queries, "skills": skills, "budget": budget, "routes": routes,
               "predictions": predictions, "sensitivity": sensitivity, "extras": extras, "cap12": cap12, "contrasts": contrasts}
    (ANALYSIS / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    for p in predictions:
        print(f"P{p['n']:>2} {'MET    ' if p['met'] else 'NOT MET'} {p['title']}: {p['numbers']}")
    base = {p["n"]: ("MET" if p["met"] else "NOT MET") for p in predictions}
    for label, info in sensitivity.items():
        flips = {n: v for n, v in info["verdicts"].items() if v != base[n]}
        print(f"  sensitivity, {label}: cells {info['cells']}; verdicts that change: {flips if flips else 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
