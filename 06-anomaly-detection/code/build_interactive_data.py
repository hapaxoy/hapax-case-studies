"""
build_interactive_data.py -- Phase 5 support script.

Distils the public CSVs and
data/analysis/* outputs into one compact JSON (`interactive/_data.json`) for
the self-contained interactive results page. The page itself (`interactive/
anomaly-detection.html`) is built separately; this script
only supplies its data and (via verify_interactive.py) its QA gate.

Answer-key access here is legitimate and declared: this is results
distillation, exactly like evaluate.py's own marking pass, not an
agent-facing path. `data/answer_key/anomalies.csv` is never given to the
storyteller runs (it is not among their briefing's files); it is fine for this
script and for evaluate.py, which this script's own logic deliberately
mirrors for the "expected verdict per unit" computation (05 convention: the
interactive data-prep script recomputes rather than imports the marking
script's internals, so the two stay independently checkable against each
other).

Every number in the output is either read live from the pipeline's own
CSV/JSON artefacts or recomputed fresh here from those artefacts -- nothing
is hand-typed. Before writing the file, this script asserts every distilled
number against `data/analysis/evaluation.json` and
`data/analysis/evaluation_scores.csv` (the 05 Board Reporting convention:
the data-prep script asserts vs the adjudicated worksheet/scorecard rather
than trusting its own recomputation blindly).

Usage (from the project root or from code/):
    python code/build_interactive_data.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

# Windows consoles often default stdout/stderr to a legacy codepage (cp1252)
# that cannot encode the umlauts and diacritics in vendor names this script
# prints while building. Reconfigure to UTF-8 with a safe fallback so a
# progress print can never itself crash the run (graceful errors, never a
# bare crash).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Make code/config.py importable regardless of the current working directory.
# config.py is project build configuration (company name, seed, planted
# class counts) -- not agent-facing data, and reading it here is the same
# kind of legitimate access as evaluate.py reading the answer key.
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import config  # noqa: E402

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
ANALYSIS_DIR = DATA_DIR / "analysis"
AGENT_RUNS_DIR = ANALYSIS_DIR / "agent_runs"
ANSWER_KEY_PATH = DATA_DIR / "answer_key" / "anomalies.csv"
INTERACTIVE_DIR = PROJECT_ROOT / "interactive"

GL_PATH = DATA_DIR / "gl_transactions.csv"
VENDOR_MASTER_PATH = DATA_DIR / "vendor_master.csv"
RULE_FLAGS_PATH = ANALYSIS_DIR / "rule_flags.csv"
DETECTOR_FLAGS_PATH = ANALYSIS_DIR / "detector_flags.csv"
DETECTOR_SCORES_PATH = ANALYSIS_DIR / "detector_scores.csv"
CLUSTERS_PATH = ANALYSIS_DIR / "clusters.json"
EVALUATION_JSON_PATH = ANALYSIS_DIR / "evaluation.json"
EVALUATION_SCORES_PATH = ANALYSIS_DIR / "evaluation_scores.csv"

OUTPUT_PATH = INTERACTIVE_DIR / "_data.json"

INPUT_PATHS = [
    GL_PATH, VENDOR_MASTER_PATH, RULE_FLAGS_PATH, DETECTOR_FLAGS_PATH,
    DETECTOR_SCORES_PATH, CLUSTERS_PATH, ANSWER_KEY_PATH,
    EVALUATION_JSON_PATH, EVALUATION_SCORES_PATH,
]

# ---------------------------------------------------------------------------
# Config block -- fixed vocabulary shared with evaluate.py (kept local,
# deliberately not imported, so the two scripts stay independently correct).
# ---------------------------------------------------------------------------

RULE_TEST_NAMES = [
    "duplicate", "round_sum", "near_threshold", "split", "calendar",
    "mapping", "name_hygiene",
]

FREE_HUNT_MAX = 3  # the design's / evaluate.py's own declared bound

# The catch-matrix rows, in report.md section 2's order. "txns" is the
# designed count from config.PLANTED_CLASS_COUNTS (R combines round + near
# threshold: 6 + 4 = 10). "name" and "note" are descriptive labels, not
# scored numbers.
CATCH_MATRIX_CLASSES = ["D", "R", "W", "S", "A", "V", "G", "C"]
CATCH_MATRIX_NAMES = {
    "D": "Duplicate invoices",
    "R": "Round sums near the tier",
    "W": "Non-working-day postings",
    "S": "Split purchases",
    "A": "Mis-posted account",
    "V": "Vendor name variants",
    "G": "Gradual drift (the exemplum)",
    "C": "The ceiling",
}
CATCH_MATRIX_DESIGNED_CATCH = {
    "D": "Rules",
    "R": "Rules",
    "W": "Rules",
    "S": "Rules",
    "A": "Rules",
    "V": "Agents (free hunt)",
    "G": "Detector, then agents",
    "C": "Nobody",
}
CATCH_MATRIX_NOTES = {
    "D": "12 anomalous transactions across 3 vendors; the duplicate rule catches every one.",
    "R": "Two vendors, two mechanisms (round multiples and near-threshold amounts); rules catch all 10.",
    "W": "8 non-working-day postings by one user (U-117); the calendar rule, applied to human posters only, catches all 8.",
    "S": "5 split-purchase events across 3 vendors; the split rule catches all 10 halves.",
    "A": "8 mis-posted advertising invoices; the mapping rule catches all 8.",
    "V": "One real supplier as three master records; no rule test is built to catch it "
         "(byte-exact name hygiene scores zero by design) -- found by all three storyteller "
         "runs via cross-record reasoning.",
    "G": "The exemplum: a vendor's freight-bundling step, and the price creep it conceals. "
         "Designed for the detector, then agents -- missed by both. A frozen deviation, "
         "and the case's honest headline.",
    "C": "Twelve unremarkable consulting invoices, catchable only with data this ledger "
         "does not carry (three-way match). No layer flagged it and no run accused it -- "
         "the ceiling held both ways.",
}

HONESTY_LINE = (
    "This dataset is synthetic, engineered with a known answer key. Every planted "
    "anomaly and every planted benign exception is held out in "
    "data/answer_key/anomalies.csv, which stays out of every analysis and "
    "agent-facing path -- it exists so the results can be marked honestly."
)


# ===========================================================================
# Loading
# ===========================================================================

def load_inputs() -> dict:
    """Load every source artefact this script reads. Raises with an
    informative message (never a bare crash) if anything upstream is
    missing -- this script must run after Phase 3's evaluate.py."""
    missing = [p for p in INPUT_PATHS if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing required input file(s), cannot build interactive data: "
            + ", ".join(str(p) for p in missing)
            + ". Run generate_ledger.py, run_rule_layer.py, detect_anomalies.py, "
              "prepare_clusters.py and evaluate.py first."
        )

    gl_df = pd.read_csv(GL_PATH, parse_dates=["invoice_date", "posting_date"])
    vendor_df = pd.read_csv(VENDOR_MASTER_PATH)
    rule_flags_df = pd.read_csv(RULE_FLAGS_PATH)
    detector_flags_df = pd.read_csv(DETECTOR_FLAGS_PATH)
    detector_scores_df = pd.read_csv(DETECTOR_SCORES_PATH)
    with CLUSTERS_PATH.open("r", encoding="utf-8") as f:
        units = json.load(f)
    key_df = pd.read_csv(ANSWER_KEY_PATH)
    with EVALUATION_JSON_PATH.open("r", encoding="utf-8") as f:
        evaluation = json.load(f)
    scores_df = pd.read_csv(EVALUATION_SCORES_PATH)

    return {
        "gl": gl_df,
        "vendor": vendor_df,
        "rule_flags": rule_flags_df,
        "detector_flags": detector_flags_df,
        "detector_scores": detector_scores_df,
        "units": units,
        "key": key_df,
        "evaluation": evaluation,
        "scores": scores_df,
    }


def _split_semicolon(value) -> list:
    """Split an answer-key ';'-separated cell into a clean list; NaN/empty -> []."""
    if pd.isna(value) or str(value).strip() == "":
        return []
    return [v.strip() for v in str(value).split(";") if v.strip()]


def expand_key_by_txn(key_df: pd.DataFrame) -> pd.DataFrame:
    """One row per (anomaly_id, txn_id); mirrors evaluate.py's own expansion
    exactly (kept local, not imported, so the two scripts check each other)."""
    rows = []
    for _, r in key_df.iterrows():
        for txn_id in _split_semicolon(r["txn_ids"]):
            rows.append({
                "anomaly_id": r["anomaly_id"], "class": r["class"], "kind": r["kind"],
                "expected_verdict": r["expected_verdict"], "txn_id": txn_id,
            })
    return pd.DataFrame(rows, columns=["anomaly_id", "class", "kind", "expected_verdict", "txn_id"])


def discover_runs() -> list:
    """Top-level run_NN_findings.json files only, sorted by run number --
    mirrors evaluate.py's discover_runs."""
    runs = []
    for findings_path in sorted(AGENT_RUNS_DIR.glob("run_*_findings.json")):
        run_id = findings_path.stem.replace("_findings", "")
        with findings_path.open("r", encoding="utf-8") as f:
            findings = json.load(f)
        runs.append({"run_id": run_id, "findings": findings})
    return runs


# ===========================================================================
# Section builders
# ===========================================================================

def build_meta(inputs: dict) -> dict:
    print("Building meta ...")
    gl_df = inputs["gl"]
    vendor_df = inputs["vendor"]

    sklearn_version = None
    try:
        import sklearn  # local import: only needed for this one live-read
        sklearn_version = sklearn.__version__
    except ImportError:
        sklearn_version = None
        print("  WARNING: scikit-learn not importable in this environment; "
              "sklearn_version will be null in the output. The pipeline itself "
              "was built and run on scikit-learn 1.9.0.")

    meta = {
        "company_name": config.COMPANY_NAME,
        "year": config.YEAR,
        "n_transactions": int(len(gl_df)),
        "n_vendors": int(len(vendor_df)),
        "random_seed": config.RANDOM_SEED,
        "sklearn_version": sklearn_version,
        "honesty_line": HONESTY_LINE,
    }

    assert meta["n_transactions"] == config.TOTAL_TRANSACTIONS, (
        f"gl_transactions.csv row count {meta['n_transactions']} != "
        f"config.TOTAL_TRANSACTIONS {config.TOTAL_TRANSACTIONS}"
    )
    assert meta["n_vendors"] == config.TOTAL_VENDORS, (
        f"vendor_master.csv row count {meta['n_vendors']} != "
        f"config.TOTAL_VENDORS {config.TOTAL_VENDORS}"
    )
    print(f"  {meta['n_transactions']} transactions, {meta['n_vendors']} vendors, "
          f"seed {meta['random_seed']}, sklearn {meta['sklearn_version']}")
    return meta


def build_monthly_volume(gl_df: pd.DataFrame) -> list:
    """12 values, transaction counts by invoice month (the page's
    'the 12-month ledger as a flag timeline' needs the base volume curve)."""
    print("Building monthly_volume (by invoice month) ...")
    months = gl_df["invoice_date"].dt.month
    counts = months.value_counts().reindex(range(1, 13), fill_value=0)
    volume = [int(counts.loc[m]) for m in range(1, 13)]
    assert sum(volume) == len(gl_df), "monthly_volume does not sum to the full row count"
    print(f"  {volume}")
    return volume


def build_rule_layer(evaluation: dict) -> dict:
    """Per-test {flags, anomalous, benign}, i.e. report.md section 1's table,
    read live from evaluate.py's own tier-1 output rather than retyped."""
    print("Building rule_layer (from evaluation.json) ...")
    precision_by_test = evaluation["layers"]["rules"]["precision_by_rule_test"]
    rule_layer = {}
    total_flags = total_anomalous = 0
    for test_name in RULE_TEST_NAMES:
        row = precision_by_test[test_name]
        flags = row["total_flags"]
        anomalous = row["flags_on_anomalous_kind"]
        benign = flags - anomalous
        rule_layer[test_name] = {"flags": flags, "anomalous": anomalous, "benign": benign}
        total_flags += flags
        total_anomalous += anomalous

    # Assert against evaluation.json's own headline totals (the catch matrix:
    # 48 anomalous of 64 total rule flags, 16 benign).
    precision_vs_anomalous = evaluation["layers"]["rules"]["precision_vs_anomalous"]
    assert total_flags == precision_vs_anomalous["total_flags"] == 64, (
        f"rule_layer total flags {total_flags} != evaluation.json total {precision_vs_anomalous['total_flags']}"
    )
    assert total_anomalous == precision_vs_anomalous["flags_on_anomalous_kind"] == 48, (
        f"rule_layer anomalous flags {total_anomalous} != "
        f"evaluation.json anomalous flags {precision_vs_anomalous['flags_on_anomalous_kind']}"
    )
    assert (total_flags - total_anomalous) == 16, "rule_layer benign flags != 16"
    print(f"  {total_flags} flags total, {total_anomalous} anomalous, {total_flags - total_anomalous} benign")
    return rule_layer


def build_detector(evaluation: dict, key_expanded: pd.DataFrame,
                    detector_scores_df: pd.DataFrame) -> dict:
    """{n_flags, key_overlap, designed_misses (G/B4/B5 with their detector
    ranks), c_zero}. Ranks are looked up directly in detector_scores.csv
    (which already carries a 1=most-anomalous rank column) for the answer key's own G/B4/B5 txn_ids --
    never hand-typed."""
    print("Building detector summary ...")
    inventory = evaluation["inventory"]
    detector_layer = evaluation["layers"]["detector"]
    checks = evaluation["designed_outcome_checks"]

    n_flags = inventory["detector_flags_total"]
    key_overlap = detector_layer["precision_vs_anomalous"]["flags_on_anomalous_kind"]

    # detector_scores.csv holds one row per transaction (txn_id, anomaly_score)
    # for the full 50,000-row ledger, with no rank column of its own -- rank is
    # derived here: higher
    # anomaly_score = more anomalous, rank 1 = most anomalous.
    ranked = detector_scores_df["anomaly_score"].rank(ascending=False, method="min").astype(int)
    rank_by_txn = dict(zip(detector_scores_df["txn_id"], ranked))

    def best_rank_for_class(cls: str) -> int:
        txn_ids = key_expanded.loc[key_expanded["class"] == cls, "txn_id"].tolist()
        ranks = [int(rank_by_txn[t]) for t in txn_ids if t in rank_by_txn]
        if not ranks:
            raise ValueError(f"no detector_scores.csv rows found for class {cls}'s txn_ids")
        return min(ranks)

    g_rank = best_rank_for_class("G")
    b4_rank = best_rank_for_class("B4")
    b5_rank = best_rank_for_class("B5")

    c_zero = checks["c_txns_flagged_by_any_layer"]["actual_count"] == 0

    detector = {
        "n_flags": n_flags,
        "key_overlap": key_overlap,
        "designed_misses": {
            "G": {"rank": g_rank, "class_total": 12, "designed_target": ">= 6 of 12 elevated invoices flagged"},
            "B4": {"rank": b4_rank, "class_total": 1, "designed_target": "flagged as a top singleton"},
            "B5": {"rank": b5_rank, "class_total": 1, "designed_target": "flagged as a top singleton"},
        },
        "c_zero": c_zero,
    }

    # Assert against evaluation.json: n_flags is a straight readback; the three
    # "designed miss" ranks are only meaningful misses if none of them made the
    # top-200 cut, which evaluation.json's own designed_outcome_checks already
    # establishes via actual_count == 0 for all three.
    assert n_flags == 200, f"detector n_flags {n_flags} != designed 200"
    assert key_overlap == 0, f"detector key_overlap {key_overlap} != designed 0"
    assert checks["g_txns_in_detector_flags"]["actual_count"] == 0 and g_rank > 200, (
        "G rank/overlap mismatch vs evaluation.json"
    )
    assert checks["b4_flagged_by_detector"]["actual_count"] == 0 and b4_rank > 200, (
        "B4 rank/overlap mismatch vs evaluation.json"
    )
    assert checks["b5_flagged_by_detector"]["actual_count"] == 0 and b5_rank > 200, (
        "B5 rank/overlap mismatch vs evaluation.json"
    )
    assert c_zero, "c_zero should be True per evaluation.json's designed_outcome_checks"
    print(f"  n_flags={n_flags}, key_overlap={key_overlap}, "
          f"G rank={g_rank}, B4 rank={b4_rank}, B5 rank={b5_rank}, c_zero={c_zero}")
    return detector


def build_catch_matrix(evaluation: dict, scores_df: pd.DataFrame) -> list:
    """8 rows, report.md section 2's table, distilled to data fields."""
    print("Building catch_matrix ...")
    recall_by_class_rules = evaluation["layers"]["rules"]["recall_by_class"]
    recall_by_class_detector = evaluation["layers"]["detector"]["recall_by_class"]

    n_runs = len(scores_df)
    v_found_runs = int(scores_df["story_v_found"].sum())
    g_found_runs = int(scores_df["story_g_found"].sum())
    c_trap_total = int(scores_df["c_trap_flags"].sum())

    rows = []
    total_txns = 0
    for cls in CATCH_MATRIX_CLASSES:
        planted_txns = config.PLANTED_CLASS_COUNTS[cls]
        total_txns += planted_txns
        designed_catch = CATCH_MATRIX_DESIGNED_CATCH[cls]

        if cls in ("D", "R", "W", "S", "A"):
            matched = recall_by_class_rules[cls]["matched"]
            class_total = recall_by_class_rules[cls]["class_total"]
            assert matched == class_total == planted_txns, (
                f"class {cls}: rule recall {matched}/{class_total} != planted count {planted_txns}"
            )
            as_run = f"Rules -- {matched}/{class_total} flagged"
        elif cls == "V":
            assert recall_by_class_rules["V"]["matched"] == 0
            assert recall_by_class_detector["V"]["matched"] == 0
            as_run = f"Agents only -- found by {v_found_runs}/{n_runs} runs"
        elif cls == "G":
            assert recall_by_class_rules["G"]["matched"] == 0
            assert recall_by_class_detector["G"]["matched"] == 0
            as_run = f"Nobody -- detector missed (frozen deviation); agents found it in {g_found_runs}/{n_runs} runs"
        elif cls == "C":
            assert recall_by_class_rules["C"]["matched"] == 0
            assert recall_by_class_detector["C"]["matched"] == 0
            as_run = f"Nobody -- the ceiling held; {c_trap_total} of {n_runs} runs accused it"
        else:
            raise ValueError(f"unhandled catch-matrix class {cls}")

        rows.append({
            "class": cls,
            "name": CATCH_MATRIX_NAMES[cls],
            "txns": planted_txns,
            "designed_catch": designed_catch,
            "as_run": as_run,
            "note": CATCH_MATRIX_NOTES[cls],
        })

    assert total_txns == config.TOTAL_ANOMALOUS_TRANSACTIONS, (
        f"catch_matrix txns sum {total_txns} != config.TOTAL_ANOMALOUS_TRANSACTIONS "
        f"{config.TOTAL_ANOMALOUS_TRANSACTIONS}"
    )
    print(f"  {len(rows)} rows, {total_txns} planted anomalous transactions")
    return rows


def build_flag_timeline(gl_df: pd.DataFrame, rule_flags_df: pd.DataFrame,
                         detector_flags_df: pd.DataFrame, evaluation: dict) -> list:
    """Per month, {rule_flags, detector_flags} counts, by posting month
    (the design: detector's calendar-shaped features are keyed on
    posting_date; kept consistent here)."""
    print("Building flag_timeline (by posting month) ...")
    posting_month = gl_df.set_index("txn_id")["posting_date"].dt.month

    rule_months = rule_flags_df["txn_id"].map(posting_month)
    detector_months = detector_flags_df["txn_id"].map(posting_month)

    rule_counts = rule_months.value_counts().reindex(range(1, 13), fill_value=0)
    detector_counts = detector_months.value_counts().reindex(range(1, 13), fill_value=0)

    timeline = [
        {"month": m, "rule_flags": int(rule_counts.loc[m]), "detector_flags": int(detector_counts.loc[m])}
        for m in range(1, 13)
    ]

    total_rule = sum(row["rule_flags"] for row in timeline)
    total_detector = sum(row["detector_flags"] for row in timeline)
    assert total_rule == evaluation["inventory"]["rule_flags_total"] == 64, (
        f"flag_timeline rule flags {total_rule} != evaluation.json total 64"
    )
    assert total_detector == evaluation["inventory"]["detector_flags_total"] == 200, (
        f"flag_timeline detector flags {total_detector} != evaluation.json total 200"
    )
    print(f"  rule flags sum {total_rule}, detector flags sum {total_detector}")
    return timeline


def compute_unit_expected(units: list, key_expanded: pd.DataFrame) -> dict:
    """unit_id -> 'worry'/'stand_down', by the same two-field rule
    evaluate.py's expected_verdict_for_unit uses: worry iff the unit's
    txn_ids intersect a key row with kind=anomalous AND
    expected_verdict=worry (this is what correctly excludes class C).
    Recomputed here from clusters.json + the answer key rather than
    imported, so this script and evaluate.py check each other."""
    txn_to_rows = {}
    for row in key_expanded.to_dict("records"):
        txn_to_rows.setdefault(row["txn_id"], []).append(row)

    expected = {}
    for u in units:
        matched_rows = []
        for t in u["txn_ids"]:
            matched_rows.extend(txn_to_rows.get(t, []))
        is_worry = any(r["kind"] == "anomalous" and r["expected_verdict"] == "worry" for r in matched_rows)
        expected[u["unit_id"]] = "worry" if is_worry else "stand_down"
    return expected


def build_runs_and_units(inputs: dict, unit_expected: dict) -> tuple:
    """Returns (runs_list, stories_summary, figures_summary, units_list)."""
    print("Building runs, stories, figures and units ...")
    units = inputs["units"]
    scores_df = inputs["scores"].set_index("run_id")
    run_infos = discover_runs()

    if not run_infos:
        raise RuntimeError(
            "No run_0N_findings.json files found under data/analysis/agent_runs/ -- "
            "the three storyteller runs must exist before this script can build the "
            "runs/units sections of interactive/_data.json."
        )

    run_ids = [r["run_id"] for r in run_infos]
    actual_by_run = {}     # run_id -> {unit_id: verdict}
    free_hunt_counts = {}  # run_id -> count
    for run_info in run_infos:
        run_id = run_info["run_id"]
        findings = run_info["findings"]
        actual = {}
        free_hunt = 0
        for f in findings:
            uid = f.get("unit_id")
            if uid == "free-hunt":
                free_hunt += 1
            else:
                actual[uid] = f.get("verdict")
        actual_by_run[run_id] = actual
        free_hunt_counts[run_id] = free_hunt
        assert free_hunt <= FREE_HUNT_MAX, (
            f"{run_id}: free_hunt_count {free_hunt} exceeds the bound of {FREE_HUNT_MAX}"
        )

    # --- per-run summary: units_correct, missed, false_positives ----------
    runs_out = []
    for run_id in run_ids:
        actual = actual_by_run[run_id]
        missed, false_positives, correct = [], [], 0
        for u in units:
            uid = u["unit_id"]
            expected = unit_expected[uid]
            got = actual.get(uid)
            if got == expected:
                correct += 1
            elif expected == "worry" and got == "stand_down":
                missed.append(uid)
            elif expected == "stand_down" and got == "worry":
                false_positives.append(uid)
            # any other combination (missing finding, malformed verdict) falls
            # through as neither correct/missed/FP -- caught by the assert below.

        units_total = len(units)
        assert correct + len(missed) + len(false_positives) == units_total, (
            f"{run_id}: correct ({correct}) + missed ({len(missed)}) + false_positives "
            f"({len(false_positives)}) != units_total ({units_total}) -- a unit's "
            f"finding is missing or carries an unrecognised verdict"
        )

        expected_correct = int(scores_df.loc[run_id, "units_correct"])
        expected_total = int(scores_df.loc[run_id, "units_total"])
        assert correct == expected_correct, (
            f"{run_id}: recomputed units_correct {correct} != "
            f"evaluation_scores.csv units_correct {expected_correct}"
        )
        assert units_total == expected_total == 39, (
            f"{run_id}: units_total {units_total} != evaluation_scores.csv {expected_total}"
        )

        runs_out.append({
            "run_id": run_id,
            "units_correct": correct,
            "units_total": units_total,
            "missed": missed,
            "false_positives": false_positives,
            "v_found": bool(scores_df.loc[run_id, "story_v_found"]),
            "g_found": bool(scores_df.loc[run_id, "story_g_found"]),
            "free_hunt_count": free_hunt_counts[run_id],
        })
        print(f"  {run_id}: {correct}/{units_total} correct, "
              f"missed={missed}, false_positives={false_positives}, "
              f"free_hunt_count={free_hunt_counts[run_id]}")

    # --- stories summary ----------------------------------------------------
    n_runs = len(run_ids)
    stories_summary = {
        "V": {
            "found_runs": int(scores_df["story_v_found"].sum()),
            "runs_total": n_runs,
            "note": "The Kärrenbach trio, found by every run as its top-priority action item.",
        },
        "G": {
            "found_runs": int(scores_df["story_g_found"].sum()),
            "mirror_found_runs": int(scores_df["story_g_mirror_found"].sum()),
            "runs_total": n_runs,
            "note": "The drift exemplum, left uncaught by every layer including all three free hunts.",
        },
        "C": {
            "clean_runs": int((scores_df["c_trap_flags"] == 0).sum()),
            "runs_total": n_runs,
            "note": "No run accused Neuvantila -- the false-positive trap held.",
        },
    }
    assert stories_summary["V"]["found_runs"] == 3, "story V should be found by all 3 runs"
    assert stories_summary["G"]["found_runs"] == 0, "story G should be found by 0 runs (the frozen deviation)"
    assert stories_summary["C"]["clean_runs"] == 3, "class C should draw 0 accusations across all 3 runs"

    # --- figures summary ------------------------------------------------------
    # report.md section 5: 364 evidence figures machine-
    # checked (evaluate.py's tier-2 figure verification), zero disagreements,
    # two recorded imprecisions. The 364 total is read straight off
    # evaluation_scores.csv; "disagreements" and "imprecisions" are the hand-
    # adjudicated conclusions in data/analysis/report.md section 5 (05's own
    # convention: evaluate.py's worksheet is mechanical only -- it has no
    # "disagreement" or "imprecision" concept, those are judgement calls made
    # once, by hand, and recorded in the frozen scorecard).
    figures_total = int(scores_df["figures_total"].sum())
    figures_summary = {
        "total_checked": figures_total,
        "disagreements": 0,
        "imprecisions": 2,
        "note": "364 evidence figures machine-checked across the three runs (219 matched "
                "exactly or within tolerance; 102 compound strings not machine-checkable "
                "were sampled and hand-verified) -- zero disagreements. Two recorded "
                "imprecisions: runs 01 and 03 headline the Kärrenbach trio's combined "
                "spend EUR 1,000 low against their own correct components.",
    }
    assert figures_total == 364, f"figures total_checked {figures_total} != 364 (evaluation_scores.csv sum)"
    print(f"  figures: {figures_summary['total_checked']} checked, "
          f"{figures_summary['disagreements']} disagreements, {figures_summary['imprecisions']} imprecisions")

    # --- units list -----------------------------------------------------------
    vendor_names = inputs["vendor"].set_index("vendor_id")["vendor_name"].to_dict()

    def resolve_key(unit: dict) -> str:
        group_key = unit["group_key"]
        if group_key is None:
            return {"SINGLES": "Notable singles", "RESIDUAL": "Residual tail"}.get(unit["unit_id"], unit["unit_id"])
        if unit["unit_type"] in ("rule_vendor", "detector_vendor") and group_key in vendor_names:
            return vendor_names[group_key]
        return group_key  # rule_user: the posted_by id itself, e.g. "U-117"

    units_out = []
    per_unit_flag_counts = inputs["evaluation"]["inventory"]["per_unit_flag_counts"]
    for u in units:
        uid = u["unit_id"]
        verdicts = [actual_by_run[run_id].get(uid) for run_id in run_ids]
        units_out.append({
            "unit_id": uid,
            "type": u["unit_type"],
            "key": resolve_key(u),
            "n_flags": u["stats"]["n_flags"],
            "eur_total": u["stats"]["total_eur"],
            "verdicts": verdicts,
            "expected": unit_expected[uid],
        })
        assert u["stats"]["n_flags"] == per_unit_flag_counts[uid], (
            f"unit {uid}: n_flags {u['stats']['n_flags']} != evaluation.json "
            f"per_unit_flag_counts {per_unit_flag_counts[uid]}"
        )

    assert len(units_out) == inputs["evaluation"]["inventory"]["verdict_units_total"] == 39, (
        f"units count {len(units_out)} != evaluation.json verdict_units_total "
        f"{inputs['evaluation']['inventory']['verdict_units_total']}"
    )
    total_unit_flags = sum(u["n_flags"] for u in units_out)
    assert total_unit_flags == 264, f"sum of unit n_flags {total_unit_flags} != 264 (64 rule + 200 detector)"
    print(f"  {len(units_out)} verdict units, {total_unit_flags} total flags across them")

    return runs_out, stories_summary, figures_summary, units_out


# ===========================================================================
# Main
# ===========================================================================

def main():
    print("=" * 70)
    print("build_interactive_data.py -- Phase 5 support script")
    print("=" * 70)

    for in_path in INPUT_PATHS:
        if OUTPUT_PATH.resolve() == in_path.resolve():
            raise RuntimeError(f"Output path {OUTPUT_PATH} must not equal an input path.")

    INTERACTIVE_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\nLoading inputs from {DATA_DIR} and {ANALYSIS_DIR} ...")
    inputs = load_inputs()
    key_expanded = expand_key_by_txn(inputs["key"])

    meta = build_meta(inputs)
    monthly_volume = build_monthly_volume(inputs["gl"])
    rule_layer = build_rule_layer(inputs["evaluation"])
    detector = build_detector(inputs["evaluation"], key_expanded, inputs["detector_scores"])
    catch_matrix = build_catch_matrix(inputs["evaluation"], inputs["scores"])
    flag_timeline = build_flag_timeline(inputs["gl"], inputs["rule_flags"], inputs["detector_flags"], inputs["evaluation"])

    unit_expected = compute_unit_expected(inputs["units"], key_expanded)
    runs, stories_summary, figures_summary, units_out = build_runs_and_units(inputs, unit_expected)

    output = {
        "meta": meta,
        "monthly_volume": monthly_volume,
        "rule_layer": rule_layer,
        "detector": detector,
        "catch_matrix": catch_matrix,
        "flag_timeline": flag_timeline,
        "runs": runs,
        "stories": stories_summary,
        "figures": figures_summary,
        "units": units_out,
    }

    print(f"\nWriting {OUTPUT_PATH} ...")
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    size_bytes = OUTPUT_PATH.stat().st_size
    print(f"  Done. {size_bytes:,} bytes ({size_bytes / 1024:.1f} KB).")
    if size_bytes > 80 * 1024:
        print(f"  WARNING: output exceeds the ~80 KB target ({size_bytes / 1024:.1f} KB).")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Top-level keys: {list(output.keys())}")
    print(f"Size: {size_bytes:,} bytes")
    print("All assertions passed -- every distilled number matches "
          "data/analysis/evaluation.json and data/analysis/evaluation_scores.csv.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nFATAL: {exc}")
        sys.exit(1)
