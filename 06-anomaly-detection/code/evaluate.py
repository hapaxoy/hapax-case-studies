"""
evaluate.py -- Phase 3 evaluation / marking script.

Implements the evaluation design and checks the catch matrix and the
pre-registered run expectations.

This IS the marking script -- reading data/answer_key/anomalies.csv here is
legitimate and required. It must never be referenced by, imported by, or
made available to anything agent-facing: the storyteller runs are given only
the files listed in their briefing, and nothing under
data/answer_key/ is on that list. This script is read-only with respect to
every other artefact in the project; it writes only the three outputs below.

Two tiers (05's load-bearing distinction):

  TIER 1 -- fully mechanical, transaction-id matching only. No prose is read.
    -> data/analysis/evaluation.json
       per-layer recall by answer-key class, per-layer precision vs the
       anomalous kind, per-rule-test precision, the five designed-outcome
       checks, and the flag/unit inventory.

  TIER 2 -- per storyteller run, MECHANICAL ONLY (05's worksheet convention:
    this script does not read prose for meaning and hands down no final
    verdict; it only runs literal keyword/regex tests over the findings
    JSON's own text fields and lists every ambiguous case for a human
    adjudicator). Findings JSON is read; memo.md is checked for presence
    only, never parsed.
    -> data/analysis/evaluation_worksheet.md  (human-readable detail)
    -> data/analysis/evaluation_scores.csv    (one summary row per run)

Runs are discovered dynamically from data/analysis/agent_runs/run_*_findings.json
(top-level only -- any working sub-folders are ignored). The
script runs correctly with only run_01 present and will pick up run_02 and
run_03 automatically once they land, with no code change required.

Implementation choices not fully pinned by the design are noted in the
comments below.

Usage (from the project root or from code/):
    python code/evaluate.py
"""

import json
import re
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
ANALYSIS_DIR = DATA_DIR / "analysis"
AGENT_RUNS_DIR = ANALYSIS_DIR / "agent_runs"
ANSWER_KEY_PATH = DATA_DIR / "answer_key" / "anomalies.csv"

GL_PATH = DATA_DIR / "gl_transactions.csv"
RULE_FLAGS_PATH = ANALYSIS_DIR / "rule_flags.csv"
DETECTOR_FLAGS_PATH = ANALYSIS_DIR / "detector_flags.csv"
CLUSTERS_PATH = ANALYSIS_DIR / "clusters.json"

EVALUATION_JSON_PATH = ANALYSIS_DIR / "evaluation.json"
WORKSHEET_PATH = ANALYSIS_DIR / "evaluation_worksheet.md"
SCORES_CSV_PATH = ANALYSIS_DIR / "evaluation_scores.csv"

INPUT_PATHS = [GL_PATH, RULE_FLAGS_PATH, DETECTOR_FLAGS_PATH, CLUSTERS_PATH, ANSWER_KEY_PATH]
OUTPUT_PATHS = [EVALUATION_JSON_PATH, WORKSHEET_PATH, SCORES_CSV_PATH]

# ---------------------------------------------------------------------------
# Config block
# ---------------------------------------------------------------------------

# The seven rule tests of the design (canonical list, kept
# local to this marking script rather than imported from rule_tests.py /
# config.py -- evaluate.py must stand on its own reading only the CSV/JSON
# outputs, never the generation-side code).
RULE_TEST_NAMES = [
    "duplicate", "round_sum", "near_threshold", "split", "calendar",
    "mapping", "name_hygiene",
]

# Figure-verification tolerances for tier 2 section 5. NOTE: the original
# design states a tighter tolerance (+/-EUR50 absolute or exact for planted
# figures, +/-0.1pp for percentages); this script implements the wider band
# below instead. Recorded as a deliberate deviation.
EXACT_MATCH_TOLERANCE_EUR = 0.005   # float-rounding guard only, not a real band
AGGREGATE_ABS_TOLERANCE_EUR = 100.0
AGGREGATE_REL_TOLERANCE = 0.01

FREE_HUNT_MAX = 3

REQUIRED_FINDING_FIELDS = [
    "finding_id", "headline", "unit_id", "verdict", "mechanism", "affected",
    "evidence", "severity", "confidence", "recommended_action",
]
REQUIRED_AFFECTED_FIELDS = ["vendor_ids", "accounts", "months", "users"]
REQUIRED_EVIDENCE_FIELDS = ["source", "what", "figure"]
ALLOWED_VERDICTS = {"worry", "stand_down"}
ALLOWED_SEVERITIES = {"info", "watch", "act"}
ALLOWED_CONFIDENCES = {"low", "medium", "high"}

# ---------------------------------------------------------------------------
# Mechanism keyword tests -- tier 2 section 3, stated verbatim in the
# worksheet. Each test is a list of clauses that must ALL match (AND) against
# the finding's searchable text (headline + mechanism + recommended_action +
# every evidence entry's source/what/figure), case-insensitively, Unicode-
# aware. Group keys are the answer-key class each test targets; W and A are
# two-clause AND tests exactly as specified; D and B3's second/only clause
# operationalises a descriptive requirement of the evaluation rules -- the
# exact wording of that choice is in the patterns below.
# ---------------------------------------------------------------------------

KEYWORD_TESTS = {
    "D": {
        "description": (
            "text matches (duplicate|double|resubmi|uudelleen|toistuv) and "
            "mentions the shared order reference or invoice-number pair"
        ),
        "clauses": [
            r"duplicate|double|resubmi|uudelleen|toistuv",
            r"order|tilaus|reference|invoice number|invoice ref",
        ],
    },
    "R-ROUND": {
        "description": "(round|tasasumma|multiple|threshold|tier|approval)",
        "clauses": [r"round|tasasumma|multiple|threshold|tier|approval"],
    },
    "R-NEAR": {
        "description": "(threshold|tier|approval|9[.,]?5|just under|alle)",
        "clauses": [r"threshold|tier|approval|9[.,]?5|just under|alle"],
    },
    "S": {
        "description": "(split|osatoimitus|structur|threshold|approval|avoid)",
        "clauses": [r"split|osatoimitus|structur|threshold|approval|avoid"],
    },
    "W": {
        "description": "mentions U-117 AND (weekend|non-working|holiday|lauantai|viikonloppu)",
        "clauses": [r"U-117", r"weekend|non-working|holiday|lauantai|viikonloppu"],
    },
    "A": {
        "description": "(marketing|mainos) AND (IT|7200|mis-cod|wrong account|mapping)",
        "clauses": [r"marketing|mainos", r"\bIT\b|7200|mis-cod|wrong account|mapping"],
    },
    "B1": {
        "description": "(rent|vuokra|contract|recurring)",
        "clauses": [r"rent|vuokra|contract|recurring"],
    },
    "B2": {
        "description": "(inventaario|overtime|ylityö|agreed)",
        "clauses": [r"inventaario|overtime|ylityö|agreed"],
    },
    "B3": {
        "description": "(PO|different (order|purchase)|distinct)",
        "clauses": [r"\bPO\b|different (order|purchase)|distinct"],
    },
}

# Story-detection (free-hunt target) regexes -- tier 2 section 4, verbatim.
STORY_V_TEXT_RE = r"Kärrenbach|Kaerrenbach|KARRENBACH|DE199283746"
STORY_V_VENDOR_SET = {"V-0003", "V-0004", "V-0005"}
STORY_V_VENDOR_MIN = 2

STORY_G_VENDOR = "V-0001"
STORY_G_NAME_RE = r"Teräskontio"
STORY_G_MECHANISM_RE = r"rahti|freight|bundl|drift|creep|price increase|step"

STORY_G_MIRROR_VENDOR = "V-0002"
STORY_G_MIRROR_TEXT_RE = r"Kuormaraitti"

C_TRAP_VENDOR = "V-0007"
C_TRAP_TEXT_RE = r"Neuvantila"


# ===========================================================================
# Loading
# ===========================================================================

def load_public_inputs() -> dict:
    """Load the fixed, run-independent inputs shared by tier 1 and tier 2."""
    missing = [p for p in INPUT_PATHS if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing required input file(s), cannot evaluate: "
            + ", ".join(str(p) for p in missing)
            + ". Run run_rule_layer.py, detect_anomalies.py and "
              "prepare_clusters.py first (Phase 2 must already have produced "
              "the answer key)."
        )

    gl_df = pd.read_csv(GL_PATH)
    rule_flags_df = pd.read_csv(RULE_FLAGS_PATH)
    detector_flags_df = pd.read_csv(DETECTOR_FLAGS_PATH)
    with CLUSTERS_PATH.open("r", encoding="utf-8") as f:
        units = json.load(f)
    key_df = pd.read_csv(ANSWER_KEY_PATH)

    return {
        "gl": gl_df,
        "rule_flags": rule_flags_df,
        "detector_flags": detector_flags_df,
        "units": units,
        "key": key_df,
    }


def _split_semicolon(value) -> list:
    """Split an answer-key ';'-separated cell into a clean list; NaN/empty -> []."""
    if pd.isna(value) or str(value).strip() == "":
        return []
    return [v.strip() for v in str(value).split(";") if v.strip()]


def expand_key_by_txn(key_df: pd.DataFrame) -> pd.DataFrame:
    """One row per (anomaly_id, txn_id): class/kind/expected_verdict carried
    through. B6 (no itemised txn_ids) contributes zero rows by design."""
    rows = []
    for _, r in key_df.iterrows():
        for txn_id in _split_semicolon(r["txn_ids"]):
            rows.append({
                "anomaly_id": r["anomaly_id"],
                "class": r["class"],
                "kind": r["kind"],
                "expected_verdict": r["expected_verdict"],
                "txn_id": txn_id,
            })
    return pd.DataFrame(rows, columns=["anomaly_id", "class", "kind", "expected_verdict", "txn_id"])


def build_class_totals(key_df: pd.DataFrame, key_expanded: pd.DataFrame) -> dict:
    """class -> set of txn_ids, for every class in the answer key (including
    B6, which is present with an empty set -- a declared pattern, not an
    itemised transaction list)."""
    all_classes = sorted(key_df["class"].unique().tolist())
    class_totals = {cls: set() for cls in all_classes}
    for cls, grp in key_expanded.groupby("class"):
        class_totals[cls] = set(grp["txn_id"])
    return class_totals


def build_key_vendor_anomalous_worry(key_df: pd.DataFrame) -> set:
    """Vendor ids appearing in a key row that is BOTH kind=anomalous AND
    expected_verdict=worry. This deliberately excludes class C: C's kind is
    'anomalous' but the design declares its expected_verdict
    'stand_down' by design (the false-positive trap) ; the
    two-field rule, not kind alone, is
    the correct mechanical membership test."""
    vendor_ids = set()
    for _, r in key_df.iterrows():
        if r["kind"] == "anomalous" and r["expected_verdict"] == "worry":
            vendor_ids.update(_split_semicolon(r["vendor_id"]))
    return vendor_ids


# ===========================================================================
# TIER 1 -- mechanical, id-matching only
# ===========================================================================

def recall_by_class(flag_ids: set, class_totals: dict) -> dict:
    out = {}
    for cls, txns in class_totals.items():
        if len(txns) == 0:
            out[cls] = {
                "matched": None, "class_total": 0, "recall": None,
                "note": "class has no itemised txn_ids in the answer key (a declared pattern, e.g. B6)",
            }
        else:
            matched = flag_ids & txns
            out[cls] = {
                "matched": len(matched),
                "class_total": len(txns),
                "recall": round(len(matched) / len(txns), 4),
            }
    return out


def precision_vs_anomalous(flag_ids: set, anomalous_txn_ids: set) -> dict:
    total = len(flag_ids)
    on_anomalous = len(flag_ids & anomalous_txn_ids)
    return {
        "flags_on_anomalous_kind": on_anomalous,
        "total_flags": total,
        "precision": round(on_anomalous / total, 4) if total else None,
    }


def precision_by_rule_test(rule_flags_df: pd.DataFrame, anomalous_txn_ids: set) -> dict:
    out = {}
    present = dict(tuple(rule_flags_df.groupby("test")))
    for test_name in RULE_TEST_NAMES:
        grp = present.get(test_name)
        if grp is None or len(grp) == 0:
            out[test_name] = {
                "flags_on_anomalous_kind": 0, "total_flags": 0, "precision": None,
                "note": "test raised zero flags",
            }
            continue
        ids = set(grp["txn_id"])
        on_anom = len(ids & anomalous_txn_ids)
        out[test_name] = {
            "flags_on_anomalous_kind": on_anom,
            "total_flags": len(ids),
            "precision": round(on_anom / len(ids), 4),
        }
    return out


def build_designed_outcome_checks(class_totals: dict, rule_ids: set, detector_ids: set) -> dict:
    """The four designed-outcome checks, computed
    fresh from the flag files and the answer key -- never hardcoded. Every
    'designed_target' string is descriptive context from the design's catch
    matrix; the 'actual_*' fields are what this run of the pipeline produced.
    A mismatch is reported, not corrected (the design's own rule: "any
    miss is a frozen, reported deviation, not a retune")."""

    def class_vs_layer(cls: str, layer_ids: set, target_text: str) -> dict:
        txns = class_totals.get(cls, set())
        matched = txns & layer_ids
        return {
            "class_total": len(txns),
            "actual_count": len(matched),
            "actual_txn_ids": sorted(matched),
            "designed_target": target_text,
        }

    g_check = class_vs_layer(
        "G", detector_ids,
        "Design: >= 6 of G's 12 elevated invoices expected in the detector's flags",
    )
    b4_check = class_vs_layer(
        "B4", detector_ids,
        "Design: B4 expected flagged by the detector as a top singleton",
    )
    b5_check = class_vs_layer(
        "B5", detector_ids,
        "Design: B5 expected flagged by the detector as a top singleton",
    )
    c_any_layer = (class_totals.get("C", set())) & (rule_ids | detector_ids)
    c_check = {
        "class_total": len(class_totals.get("C", set())),
        "actual_count": len(c_any_layer),
        "actual_txn_ids": sorted(c_any_layer),
        "designed_target": "Design: zero flags by either layer, by design (the ceiling class)",
    }

    overlap = {}
    for cls, txns in class_totals.items():
        hit = txns & detector_ids
        if hit:
            overlap[cls] = sorted(hit)

    return {
        "g_txns_in_detector_flags": g_check,
        "b4_flagged_by_detector": b4_check,
        "b5_flagged_by_detector": b5_check,
        "c_txns_flagged_by_any_layer": c_check,
        "detector_flag_overlap_with_any_key_class": {
            "designed_target": "Design: empty except possibly G (and B4/B5, which the detector "
                                "also treats as ordinary top singletons rather than a class)",
            "actual": overlap,
        },
    }


def run_tier1(inputs: dict) -> dict:
    print("\n" + "=" * 70)
    print("TIER 1 -- mechanical detection-layer scoring")
    print("=" * 70)

    gl_df = inputs["gl"]
    rule_flags_df = inputs["rule_flags"]
    detector_flags_df = inputs["detector_flags"]
    units = inputs["units"]
    key_df = inputs["key"]

    rule_ids = set(rule_flags_df["txn_id"])
    detector_ids = set(detector_flags_df["txn_id"])

    key_expanded = expand_key_by_txn(key_df)
    class_totals = build_class_totals(key_df, key_expanded)
    anomalous_txn_ids = set(key_expanded.loc[key_expanded["kind"] == "anomalous", "txn_id"])

    print(f"  Rule flags:      {len(rule_ids)}")
    print(f"  Detector flags:  {len(detector_ids)}")
    print(f"  Verdict units:   {len(units)}")
    print(f"  Answer-key txn rows (expanded): {len(key_expanded)}")

    layers = {
        "rules": {
            "total_flags": len(rule_ids),
            "recall_by_class": recall_by_class(rule_ids, class_totals),
            "precision_vs_anomalous": precision_vs_anomalous(rule_ids, anomalous_txn_ids),
            "precision_by_rule_test": precision_by_rule_test(rule_flags_df, anomalous_txn_ids),
        },
        "detector": {
            "total_flags": len(detector_ids),
            "recall_by_class": recall_by_class(detector_ids, class_totals),
            "precision_vs_anomalous": precision_vs_anomalous(detector_ids, anomalous_txn_ids),
            "note": "no per-test precision breakdown -- a single Isolation Forest flag "
                    "carries no test identity the way a rule flag does.",
        },
    }

    designed_outcome_checks = build_designed_outcome_checks(class_totals, rule_ids, detector_ids)

    per_unit_flag_counts = {u["unit_id"]: u["stats"]["n_flags"] for u in units}
    inventory = {
        "rule_flags_total": len(rule_flags_df),
        "detector_flags_total": len(detector_flags_df),
        "verdict_units_total": len(units),
        "per_unit_flag_counts": per_unit_flag_counts,
        "note": "the design originally estimated ~20-22 units; the mechanical "
                "cluster-preparation rule as actually run produced 39 (13 rule-side + 26 "
                "detector-side).",
    }

    print(f"  Rule-layer precision vs anomalous kind:     {layers['rules']['precision_vs_anomalous']['precision']}")
    print(f"  Detector-layer precision vs anomalous kind: {layers['detector']['precision_vs_anomalous']['precision']}")
    print(f"  Designed-outcome check -- G txns in detector flags: "
          f"{designed_outcome_checks['g_txns_in_detector_flags']['actual_count']} of "
          f"{designed_outcome_checks['g_txns_in_detector_flags']['class_total']}")
    print(f"  Designed-outcome check -- B4 flagged: {designed_outcome_checks['b4_flagged_by_detector']['actual_count'] > 0}")
    print(f"  Designed-outcome check -- B5 flagged: {designed_outcome_checks['b5_flagged_by_detector']['actual_count'] > 0}")
    print(f"  Designed-outcome check -- C txns flagged by any layer: {designed_outcome_checks['c_txns_flagged_by_any_layer']['actual_count']}")
    print(f"  Designed-outcome check -- detector overlap with any key class: "
          f"{designed_outcome_checks['detector_flag_overlap_with_any_key_class']['actual']}")

    evaluation = {
        "generated_by": "code/evaluate.py",
        "answer_key_access_note": "Legitimate here -- this IS the marking script. Never read by "
                                   "anything agent-facing (it is not among the files the storyteller briefing lists).",
        "inventory": inventory,
        "layers": layers,
        "designed_outcome_checks": designed_outcome_checks,
    }
    return evaluation, class_totals, key_expanded


# ===========================================================================
# TIER 2 -- per-run mechanical worksheet
# ===========================================================================

def discover_runs() -> list:
    """Top-level run_NN_findings.json files only -- any working sub-folders
    are ignored (they are not part of the frozen deliverable)."""
    if not AGENT_RUNS_DIR.exists():
        return []
    runs = []
    for findings_path in sorted(AGENT_RUNS_DIR.glob("run_*_findings.json")):
        m = re.match(r"run_(\d+)_findings\.json$", findings_path.name)
        if not m:
            continue
        run_num = m.group(1)
        memo_path = AGENT_RUNS_DIR / f"run_{run_num}_memo.md"
        runs.append({
            "run_id": f"run_{run_num}",
            "findings_path": findings_path,
            "memo_path": memo_path,
            "memo_present": memo_path.exists(),
        })
    return runs


def load_findings(path: Path):
    """Returns (findings_list_or_None, error_message_or_None). Never raises --
    a malformed run is a reportable schema violation, not a script crash."""
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"could not parse {path.name} as JSON: {exc}"
    if not isinstance(data, list):
        return None, f"{path.name} top level is not a JSON array"
    return data, None


def validate_schema(findings: list, unit_ids: set) -> dict:
    violations = []
    unit_id_counts = {}
    free_hunt_count = 0

    for i, f in enumerate(findings):
        fid = f.get("finding_id", f"<index {i}>") if isinstance(f, dict) else f"<index {i}>"
        if not isinstance(f, dict):
            violations.append(f"finding at index {i} is not a JSON object")
            continue

        missing_top = [k for k in REQUIRED_FINDING_FIELDS if k not in f]
        if missing_top:
            violations.append(f"{fid}: missing required field(s) {missing_top}")

        affected = f.get("affected")
        if isinstance(affected, dict):
            missing_aff = [k for k in REQUIRED_AFFECTED_FIELDS if k not in affected]
            if missing_aff:
                violations.append(f"{fid}: 'affected' missing field(s) {missing_aff}")
        elif "affected" in f:
            violations.append(f"{fid}: 'affected' is present but not an object")

        evidence = f.get("evidence")
        if isinstance(evidence, list):
            if len(evidence) == 0:
                violations.append(f"{fid}: 'evidence' is an empty list")
            for j, ev in enumerate(evidence):
                if not isinstance(ev, dict):
                    violations.append(f"{fid}: evidence[{j}] is not an object")
                    continue
                missing_ev = [k for k in REQUIRED_EVIDENCE_FIELDS if k not in ev]
                if missing_ev:
                    violations.append(f"{fid}: evidence[{j}] missing field(s) {missing_ev}")
        elif "evidence" in f:
            violations.append(f"{fid}: 'evidence' is present but not a list")

        verdict = f.get("verdict")
        if verdict not in ALLOWED_VERDICTS:
            violations.append(f"{fid}: verdict {verdict!r} not in {sorted(ALLOWED_VERDICTS)}")
        severity = f.get("severity")
        if severity not in ALLOWED_SEVERITIES:
            violations.append(f"{fid}: severity {severity!r} not in {sorted(ALLOWED_SEVERITIES)}")
        confidence = f.get("confidence")
        if confidence not in ALLOWED_CONFIDENCES:
            violations.append(f"{fid}: confidence {confidence!r} not in {sorted(ALLOWED_CONFIDENCES)}")

        uid = f.get("unit_id")
        if uid == "free-hunt":
            free_hunt_count += 1
        elif uid in unit_ids:
            unit_id_counts[uid] = unit_id_counts.get(uid, 0) + 1
        else:
            violations.append(f"{fid}: unit_id {uid!r} is neither a known verdict unit nor 'free-hunt'")

    missing_units = sorted(unit_ids - set(unit_id_counts.keys()))
    duplicated_units = sorted(u for u, c in unit_id_counts.items() if c > 1)
    if missing_units:
        violations.append(f"no finding for {len(missing_units)} unit(s): {missing_units}")
    if duplicated_units:
        violations.append(f"more than one finding for unit(s): {duplicated_units}")
    if free_hunt_count > FREE_HUNT_MAX:
        violations.append(f"free-hunt findings = {free_hunt_count}, exceeds the bound of {FREE_HUNT_MAX}")

    return {
        "violations": violations,
        "unit_id_counts": unit_id_counts,
        "free_hunt_count": free_hunt_count,
        "missing_units": missing_units,
        "duplicated_units": duplicated_units,
    }


def build_unit_key_map(units: list, key_expanded: pd.DataFrame) -> dict:
    """unit_id -> list of matched answer-key rows (one dict per anomaly_id),
    found by intersecting the unit's txn_ids against the expanded key."""
    txn_to_rows = {}
    for row in key_expanded.to_dict("records"):
        txn_to_rows.setdefault(row["txn_id"], []).append(row)

    unit_map = {}
    for u in units:
        matched = {}
        for t in u["txn_ids"]:
            for row in txn_to_rows.get(t, []):
                matched[row["anomaly_id"]] = row  # de-dup by anomaly_id
        unit_map[u["unit_id"]] = list(matched.values())
    return unit_map


def expected_verdict_for_unit(matched_rows: list) -> str:
    """Mechanical rule (worksheet section 2): worry iff the unit's flags
    intersect a key row with kind=anomalous AND expected_verdict=worry.
    Using both fields (not kind alone) is what correctly excludes class C:
    C's kind is 'anomalous' but the design declares its
    expected_verdict 'stand_down' by design -- the false-positive trap."""
    for row in matched_rows:
        if row["kind"] == "anomalous" and row["expected_verdict"] == "worry":
            return "worry"
    return "stand_down"


def keyword_group_for_unit(matched_rows: list) -> str:
    classes_present = {row["class"] for row in matched_rows}
    anomaly_ids_present = {row["anomaly_id"] for row in matched_rows}
    if "D" in classes_present:
        return "D"
    if "S" in classes_present:
        return "S"
    if "W" in classes_present:
        return "W"
    if "A" in classes_present:
        return "A"
    if "R" in classes_present:
        if "R-ROUND" in anomaly_ids_present:
            return "R-ROUND"
        if "R-NEAR" in anomaly_ids_present:
            return "R-NEAR"
    for b in ("B1", "B2", "B3"):
        if b in classes_present:
            return b
    return None


def finding_searchable_text(finding: dict) -> str:
    parts = [
        str(finding.get("headline", "") or ""),
        str(finding.get("mechanism", "") or ""),
        str(finding.get("recommended_action", "") or ""),
    ]
    evidence = finding.get("evidence") or []
    if isinstance(evidence, list):
        for ev in evidence:
            if isinstance(ev, dict):
                parts.append(str(ev.get("source", "") or ""))
                parts.append(str(ev.get("what", "") or ""))
                parts.append(str(ev.get("figure", "") or ""))
    return " | ".join(parts)


def vendor_ids_of(finding: dict) -> set:
    affected = finding.get("affected")
    if not isinstance(affected, dict):
        return set()
    return set(affected.get("vendor_ids") or [])


def compare_unit_verdicts(findings: list, unit_expected: dict) -> list:
    finding_by_unit = {f.get("unit_id"): f for f in findings if isinstance(f, dict)}
    rows = []
    for unit_id, expected in unit_expected.items():
        f = finding_by_unit.get(unit_id)
        actual = f.get("verdict") if f else None
        rows.append({
            "unit_id": unit_id,
            "expected": expected,
            "actual": actual,
            "correct": (actual == expected) if f is not None else False,
            "finding_id": f.get("finding_id") if f else None,
        })
    return rows


def run_keyword_tests(findings: list, unit_keyword_group: dict) -> list:
    finding_by_unit = {f.get("unit_id"): f for f in findings if isinstance(f, dict)}
    results = []
    for unit_id, group in unit_keyword_group.items():
        if group is None:
            continue
        test = KEYWORD_TESTS[group]
        f = finding_by_unit.get(unit_id)
        if f is None:
            results.append({
                "unit_id": unit_id, "group": group, "finding_id": None,
                "matched": None, "clause_results": None,
            })
            continue
        text = finding_searchable_text(f)
        clause_results = [bool(re.search(c, text, re.IGNORECASE)) for c in test["clauses"]]
        results.append({
            "unit_id": unit_id, "group": group, "finding_id": f.get("finding_id"),
            "matched": all(clause_results), "clause_results": clause_results,
        })
    return results


def find_story_hits(findings: list, vendor_set, vendor_min, text_re) -> list:
    hits = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        vids = vendor_ids_of(f)
        text = finding_searchable_text(f)
        vendor_hit = vendor_set is not None and len(vids & vendor_set) >= vendor_min
        text_hit = text_re is not None and bool(re.search(text_re, text, re.IGNORECASE))
        if vendor_hit or text_hit:
            hits.append(f.get("finding_id"))
    return hits


def find_story_g(findings: list) -> list:
    hits = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        vids = vendor_ids_of(f)
        text = finding_searchable_text(f)
        vendor_hit = STORY_G_VENDOR in vids
        text_hit = bool(re.search(STORY_G_NAME_RE, text, re.IGNORECASE)) and bool(
            re.search(STORY_G_MECHANISM_RE, text, re.IGNORECASE))
        if vendor_hit or text_hit:
            hits.append(f.get("finding_id"))
    return hits


def find_story_g_mirror(findings: list, g_hit_ids: set) -> list:
    hits = []
    for f in findings:
        if not isinstance(f, dict) or f.get("finding_id") not in g_hit_ids:
            continue
        vids = vendor_ids_of(f)
        text = finding_searchable_text(f)
        if STORY_G_MIRROR_VENDOR in vids or re.search(STORY_G_MIRROR_TEXT_RE, text, re.IGNORECASE):
            hits.append(f.get("finding_id"))
    return hits


def find_c_trap(findings: list) -> list:
    hits = []
    for f in findings:
        if not isinstance(f, dict) or f.get("verdict") != "worry":
            continue
        vids = vendor_ids_of(f)
        text = finding_searchable_text(f)
        if C_TRAP_VENDOR in vids or re.search(C_TRAP_TEXT_RE, text, re.IGNORECASE):
            hits.append(f.get("finding_id"))
    return hits


def find_unmatched_worry(findings: list, unit_expected: dict, key_vendor_anomalous_worry: set) -> list:
    """Worry findings not mapped to a kind=anomalous & expected-worry key row
    -- listed for adjudication, by rule NEVER auto-scored as a false
    positive. Unit-based findings use the same expectation as section 2;
    free-hunt findings are matched via affected.vendor_ids overlap with the
    key's anomalous-worry vendor set (free-hunt findings carry no txn_ids of
    their own in the schema)."""
    unmatched = []
    for f in findings:
        if not isinstance(f, dict) or f.get("verdict") != "worry":
            continue
        uid = f.get("unit_id")
        if uid in unit_expected:
            if unit_expected[uid] != "worry":
                unmatched.append({
                    "finding_id": f.get("finding_id"), "unit_id": uid,
                    "reason": "unit's flags do not intersect a kind=anomalous/expected-worry key row",
                })
        elif uid == "free-hunt":
            vids = vendor_ids_of(f)
            if not (vids & key_vendor_anomalous_worry):
                unmatched.append({
                    "finding_id": f.get("finding_id"), "unit_id": "free-hunt",
                    "reason": "affected.vendor_ids do not overlap any kind=anomalous/expected-worry key row",
                })
    return unmatched


# --- figure verification ---------------------------------------------------

FIGURE_NUMBER_RE = re.compile(
    r"(?:EUR\s*|€\s*)?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+\.\d{2})(?!\d)(?!\.\d)(?!\s*%)"
)


def extract_figures(text: str) -> list:
    """Candidate euro-amount numbers from one evidence[].figure string.
    Deliberately conservative: requires either a comma thousands-group or an
    exact 2-decimal fraction, and rejects trailing-digit, trailing-'.digit'
    (so a Finnish DD.MM.YYYY date such as '15.11.2025' is not read as the
    two-decimal amount '15.11'), or trailing-percent continuations (so
    '99.998th percentile' and '19.5%' are not mistaken for currency either).
    Plain integer counts that happen to have a comma thousands group (e.g.
    '1,466') can still slip through as candidates; since this section only
    ever produces 'not-checkable' rather than a hard fail for anything it
    cannot match to an anchor, that is a safe, documented limitation
    rather than a scoring risk."""
    out = []
    for m in FIGURE_NUMBER_RE.finditer(text):
        raw = m.group("num").replace(",", "")
        try:
            out.append(float(raw))
        except ValueError:
            continue
    return out


def build_anchor_pool(finding: dict, unit_by_id: dict, gl_df: pd.DataFrame) -> dict:
    """Anchors recomputed fresh from gl_transactions.csv for this finding's
    scope: individual transaction amounts (checked exactly, for planted
    figures) and aggregate sums -- the full-scope total, every pairwise sum
    (covers duplicate/split-style 'a + b = c' evidence), and, for free-hunt
    findings, each named vendor's own full-year total (checked with
    tolerance, for aggregate figures)."""
    exact = set()
    aggregate = set()
    unit_id = finding.get("unit_id")
    txn_ids = []

    if unit_id in unit_by_id:
        txn_ids = unit_by_id[unit_id]["txn_ids"]
    elif unit_id == "free-hunt":
        vendor_ids = vendor_ids_of(finding)
        if vendor_ids:
            vendor_txns = gl_df[gl_df["vendor_id"].isin(vendor_ids)]
            txn_ids = vendor_txns["txn_id"].tolist()
            for _, grp in vendor_txns.groupby("vendor_id"):
                aggregate.add(round(float(grp["amount_eur"].sum()), 2))

    if txn_ids:
        amounts = gl_df.loc[gl_df["txn_id"].isin(txn_ids), "amount_eur"].tolist()
        for a in amounts:
            exact.add(round(float(a), 2))
        if amounts:
            aggregate.add(round(sum(amounts), 2))
        for i in range(len(amounts)):
            for j in range(i + 1, len(amounts)):
                aggregate.add(round(amounts[i] + amounts[j], 2))

    return {"exact": exact, "aggregate": aggregate}


def classify_figure(value: float, anchors: dict) -> str:
    for a in anchors["exact"]:
        if abs(value - a) <= EXACT_MATCH_TOLERANCE_EUR:
            return "exact-match"
    for a in anchors["aggregate"]:
        tol = max(AGGREGATE_ABS_TOLERANCE_EUR, AGGREGATE_REL_TOLERANCE * abs(a))
        if abs(value - a) <= tol:
            return "aggregate-match"
    return "not-checkable"


def verify_figures(findings: list, unit_by_id: dict, gl_df: pd.DataFrame) -> dict:
    counts = {"exact-match": 0, "aggregate-match": 0, "not-checkable": 0}
    not_checkable_rows = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        anchors = build_anchor_pool(f, unit_by_id, gl_df)
        evidence = f.get("evidence") or []
        if not isinstance(evidence, list):
            continue
        for idx, ev in enumerate(evidence):
            if not isinstance(ev, dict):
                continue
            figure_text = str(ev.get("figure", "") or "")
            for value in extract_figures(figure_text):
                status = classify_figure(value, anchors)
                counts[status] += 1
                if status == "not-checkable":
                    not_checkable_rows.append({
                        "finding_id": f.get("finding_id"),
                        "unit_id": f.get("unit_id"),
                        "evidence_index": idx,
                        "source": ev.get("source"),
                        "figure_text": figure_text,
                        "parsed_value": value,
                    })
    total = sum(counts.values())
    return {"counts": counts, "total": total, "not_checkable_rows": not_checkable_rows}


def run_tier2(inputs: dict, class_totals: dict, key_expanded: pd.DataFrame) -> dict:
    print("\n" + "=" * 70)
    print("TIER 2 -- per-run mechanical worksheet")
    print("=" * 70)

    units = inputs["units"]
    key_df = inputs["key"]
    gl_df = inputs["gl"]
    unit_ids = {u["unit_id"] for u in units}
    unit_by_id = {u["unit_id"]: u for u in units}

    unit_key_map = build_unit_key_map(units, key_expanded)
    unit_expected = {uid: expected_verdict_for_unit(rows) for uid, rows in unit_key_map.items()}
    unit_keyword_group = {uid: keyword_group_for_unit(rows) for uid, rows in unit_key_map.items()}
    unit_matched_classes = {
        uid: sorted({row["anomaly_id"] for row in rows}) for uid, rows in unit_key_map.items()
    }
    key_vendor_anomalous_worry = build_key_vendor_anomalous_worry(key_df)

    run_infos = discover_runs()
    print(f"  Runs discovered: {[r['run_id'] for r in run_infos] if run_infos else '(none yet)'}")

    run_results = {}
    for run_info in run_infos:
        run_id = run_info["run_id"]
        print(f"\n  Processing {run_id} ({run_info['findings_path'].name})...")
        findings, load_error = load_findings(run_info["findings_path"])

        if load_error is not None:
            print(f"    FATAL for this run: {load_error}")
            run_results[run_id] = {"load_error": load_error, "memo_present": run_info["memo_present"]}
            continue

        schema = validate_schema(findings, unit_ids)
        verdict_rows = compare_unit_verdicts(findings, unit_expected)
        keyword_results = run_keyword_tests(findings, unit_keyword_group)
        story_v = find_story_hits(findings, STORY_V_VENDOR_SET, STORY_V_VENDOR_MIN, STORY_V_TEXT_RE)
        story_g = find_story_g(findings)
        story_g_mirror = find_story_g_mirror(findings, set(story_g))
        c_trap = find_c_trap(findings)
        unmatched = find_unmatched_worry(findings, unit_expected, key_vendor_anomalous_worry)
        figures = verify_figures(findings, unit_by_id, gl_df)

        units_correct = sum(1 for r in verdict_rows if r["correct"])
        units_total = len(verdict_rows)

        print(f"    Schema violations: {len(schema['violations'])}")
        print(f"    Unit verdicts correct: {units_correct}/{units_total}")
        print(f"    Story V found: {bool(story_v)}  G found: {bool(story_g)}  "
              f"G-mirror found: {bool(story_g_mirror)}  C-trap flags: {len(c_trap)}")
        print(f"    Unmatched worry findings (candidate FPs, for adjudication): {len(unmatched)}")
        print(f"    Figures: {figures['counts']} (total {figures['total']})")

        run_results[run_id] = {
            "findings_count": len(findings),
            "memo_present": run_info["memo_present"],
            "schema": schema,
            "verdict_rows": verdict_rows,
            "units_correct": units_correct,
            "units_total": units_total,
            "keyword_results": keyword_results,
            "story_v": story_v,
            "story_g": story_g,
            "story_g_mirror": story_g_mirror,
            "c_trap": c_trap,
            "unmatched_worry": unmatched,
            "figures": figures,
        }

    return {
        "unit_expected": unit_expected,
        "unit_keyword_group": unit_keyword_group,
        "unit_matched_classes": unit_matched_classes,
        "run_infos": run_infos,
        "run_results": run_results,
    }


# ===========================================================================
# Worksheet + scores rendering
# ===========================================================================

def render_worksheet(tier2: dict) -> str:
    run_infos = tier2["run_infos"]
    run_results = tier2["run_results"]
    unit_expected = tier2["unit_expected"]
    unit_keyword_group = tier2["unit_keyword_group"]
    unit_matched_classes = tier2["unit_matched_classes"]
    run_ids = [r["run_id"] for r in run_infos]

    lines = []
    a = lines.append

    a("# Evaluation worksheet -- tier 2 (mechanical, per storyteller run)")
    a("")
    a("Generated by `code/evaluate.py`. This worksheet does not read prose for")
    a("meaning and hands down no final verdict (05's convention). Every check")
    a("below is a literal regex, id-intersection, or numeric-tolerance test")
    a("against the run's `run_0N_findings.json` -- never an interpretation of")
    a("what the memo means. Every ambiguous or unmatched case is listed for a")
    a("human adjudicator; nothing here is auto-scored as a final pass or fail")
    a("except the mechanical unit-verdict comparison in section 2, which is")
    a("pure id-matching against the answer key.")
    a("")
    a("Answer-key access in this script is legitimate -- it is the marking")
    a("script. The storyteller runs themselves never see it (it is not")
    a("among the files listed in their briefing).")
    a("")

    a("## 0. Runs discovered")
    a("")
    if not run_infos:
        a("No `run_0N_findings.json` files found under `data/analysis/agent_runs/` yet. "
          "This worksheet will populate once run_02 and run_03 land -- re-run "
          "`python code/evaluate.py` at that point; no code change is needed.")
        a("")
    else:
        a("| run | findings.json | memo.md present | findings count | load error |")
        a("|---|---|---|---|---|")
        for r in run_infos:
            res = run_results.get(r["run_id"], {})
            load_err = res.get("load_error", "")
            a(f"| {r['run_id']} | `{r['findings_path'].name}` | "
              f"{'yes' if r['memo_present'] else 'NO'} | "
              f"{res.get('findings_count', '-')} | {load_err} |")
        a("")

    valid_run_ids = [rid for rid in run_ids if "load_error" not in run_results.get(rid, {"load_error": None})]

    # --- Section 1: schema validation --------------------------------------
    a("## 1. Schema validation")
    a("")
    a("Checked per run: every finding object carries the required top-level")
    a("fields, `affected` and every `evidence[]` entry carry their required")
    a("sub-fields, `verdict`/`severity`/`confidence` are in their allowed")
    a("value sets, exactly one finding exists per unit_id for all 39 units,")
    a("and free-hunt findings number at most 3.")
    a("")
    for run_id in valid_run_ids:
        res = run_results[run_id]
        schema = res["schema"]
        a(f"### {run_id}")
        a("")
        a(f"- Findings: {res['findings_count']} (39 unit findings expected + up to 3 free-hunt)")
        a(f"- Free-hunt findings: {schema['free_hunt_count']} (bound: {FREE_HUNT_MAX})")
        a(f"- Units missing a finding: {schema['missing_units'] or 'none'}")
        a(f"- Units with more than one finding: {schema['duplicated_units'] or 'none'}")
        if schema["violations"]:
            a(f"- **{len(schema['violations'])} schema violation(s):**")
            for v in schema["violations"]:
                a(f"  - {v}")
        else:
            a("- No schema violations found.")
        a("")

    # --- Section 2: unit-verdict matrix -------------------------------------
    a("## 2. Unit-verdict matrix")
    a("")
    a("Mechanical rule: a unit expects **worry** iff its")
    a("flags' txn_ids intersect an answer-key row with `kind=anomalous` AND")
    a("`expected_verdict=worry`; otherwise **stand_down**. Using both fields")
    a("(not `kind` alone) is what correctly excludes class C: C's `kind` is")
    a("`anomalous` but the design declares C's own")
    a("`expected_verdict` `stand_down` by design -- the false-positive trap.")
    a("Units are mapped to key rows by txn_id intersection, recomputed fresh")
    a("from `clusters.json` and `data/answer_key/anomalies.csv` on every run")
    a("of this script.")
    a("")
    header = "| unit_id | matched key row(s) | expected | " + " | ".join(
        f"{rid} actual | {rid} correct" for rid in valid_run_ids) + " |"
    sep = "|---|---|---|" + "|".join(["---|---"] * len(valid_run_ids)) + "|"
    a(header)
    a(sep)
    for uid in sorted(unit_expected.keys(), key=lambda x: (len(x), x)):
        matched = ", ".join(unit_matched_classes.get(uid, [])) or "-"
        expected = unit_expected[uid]
        row_cells = []
        for rid in valid_run_ids:
            vr = {r["unit_id"]: r for r in run_results[rid]["verdict_rows"]}.get(uid)
            actual = vr["actual"] if vr else "MISSING"
            correct = "yes" if (vr and vr["correct"]) else "no"
            row_cells.append(f"{actual} | {correct}")
        a(f"| {uid} | {matched} | {expected} | " + " | ".join(row_cells) + " |")
    a("")
    for run_id in valid_run_ids:
        res = run_results[run_id]
        a(f"**{run_id}: {res['units_correct']} / {res['units_total']} units correctly verdicted.**")
        a("")

    # --- Section 3: mechanism keyword tests ---------------------------------
    a("## 3. Mechanism keyword tests")
    a("")
    a("Results are listed for adjudication and are **not** auto-scored as a")
    a("final pass/fail on the run's mechanism reasoning -- a unit can have")
    a("the right verdict for a different (or better) reason than the keyword")
    a("test anticipates. Test text is quoted verbatim from the evaluation")
    a("rules; the two-part 'mentions the shared order reference or")
    a("invoice-number pair' clause for D and the bracketed clause for B3 are")
    a("operationalised as literal regexes below.")
    a("All matching is case-insensitive and")
    a("Unicode-aware (ä/ö match regardless of case).")
    a("")
    for group, test in KEYWORD_TESTS.items():
        a(f"- **{group}** -- {test['description']}")
    a("")
    if valid_run_ids:
        header = "| unit_id | group | " + " | ".join(f"{rid}" for rid in valid_run_ids) + " |"
        sep = "|---|---|" + "|".join(["---"] * len(valid_run_ids)) + "|"
        a(header)
        a(sep)
        groups_by_unit = {uid: g for uid, g in unit_keyword_group.items() if g is not None}
        for uid in sorted(groups_by_unit.keys(), key=lambda x: (len(x), x)):
            group = groups_by_unit[uid]
            cells = []
            for rid in valid_run_ids:
                kw = {r["unit_id"]: r for r in run_results[rid]["keyword_results"]}.get(uid)
                cells.append("matched" if (kw and kw["matched"]) else ("no match" if kw else "-"))
            a(f"| {uid} | {group} | " + " | ".join(cells) + " |")
        a("")

    # --- Section 4: story detection ------------------------------------------
    a("## 4. Story detection (free-hunt targets)")
    a("")
    a("Searched across every finding in the run (unit-based and free-hunt),")
    a("not only findings tagged `free-hunt` -- a story could in principle")
    a("surface inside a unit's own explanation.")
    a("")
    a("- **V** -- any finding whose `affected.vendor_ids` contains >= 2 of "
      "{V-0003, V-0004, V-0005} or text matches `(Kärrenbach|Kaerrenbach|KARRENBACH|DE199283746)`")
    a("- **G** -- any finding whose `affected.vendor_ids` contains V-0001, or text "
      "matches `Teräskontio` AND `(rahti|freight|bundl|drift|creep|price increase|step)`")
    a("- **G-mirror** -- (of the findings matching G) additionally matches "
      "`(Kuormaraitti|V-0002)`")
    a("- **C-trap** -- any WORRY finding whose `affected.vendor_ids` contains V-0007 "
      "or text matches `Neuvantila` -- flagged as a candidate false positive for adjudication")
    a("")
    if valid_run_ids:
        a("| run | V found | G found | G-mirror found | C-trap flags |")
        a("|---|---|---|---|---|")
        for rid in valid_run_ids:
            res = run_results[rid]
            a(f"| {rid} | {res['story_v'] or 'no'} | {res['story_g'] or 'no'} | "
              f"{res['story_g_mirror'] or 'no'} | {res['c_trap'] or 'none'} |")
        a("")

    # --- Section 5: figure verification --------------------------------------
    a("## 5. Figure verification")
    a("")
    a("Every euro-shaped number in every `evidence[].figure` string is parsed")
    a("and checked against anchors recomputed fresh from `gl_transactions.csv`")
    a("for that finding's scope (the mapped unit's txn_ids, or -- for")
    a("free-hunt findings -- the transactions of the vendors named in")
    a("`affected.vendor_ids`). Individual transaction amounts are exact")
    a("anchors (tolerance €0.005, a float-rounding guard only); the scope")
    a("total, every pairwise sum within the scope, and (for free-hunt)")
    a("each named vendor's own full-year total are aggregate anchors")
    a(f"(tolerance ±€{AGGREGATE_ABS_TOLERANCE_EUR:.0f} or ±{AGGREGATE_REL_TOLERANCE:.0%}, "
      "whichever is larger). NOTE: this tolerance is wider than the "
      "±€50/±0.1pp band stated in the original design, a deliberate, recorded "
      "deviation. Anything that")
    a("matches neither pool is listed below as **not-checkable** -- this is")
    a("never treated as a failure.")
    a("")
    for rid in valid_run_ids:
        res = run_results[rid]
        figs = res["figures"]
        a(f"### {rid}")
        a("")
        a(f"- Figures parsed: {figs['total']}")
        a(f"- Exact match: {figs['counts']['exact-match']}")
        a(f"- Aggregate match (within tolerance): {figs['counts']['aggregate-match']}")
        a(f"- Not-checkable (listed below for adjudication): {figs['counts']['not-checkable']}")
        if figs["not_checkable_rows"]:
            a("")
            a("| finding_id | unit_id | evidence source | figure text | parsed value |")
            a("|---|---|---|---|---|")
            for row in figs["not_checkable_rows"]:
                figure_text_escaped = str(row["figure_text"]).replace("|", "\\|")
                a(f"| {row['finding_id']} | {row['unit_id']} | {row['source']} | "
                  f"{figure_text_escaped} | {row['parsed_value']:,.2f} |")
        a("")

    # --- Section 6: unmatched findings ---------------------------------------
    a("## 6. Unmatched findings (candidate false positives -- for adjudication)")
    a("")
    a("Any WORRY finding not mapped to a `kind=anomalous`/`expected_verdict=worry`")
    a("key row. Explicitly **not** auto-scored as a false positive -- a run")
    a("can be right to worry about something the design did not plant (or, as")
    a("with the C-trap and this dataset's B4/B5 detector-blind-spot deviation,")
    a("can be raising a legitimate control point about a benign item).")
    a("")
    for rid in valid_run_ids:
        res = run_results[rid]
        a(f"### {rid}")
        a("")
        if res["unmatched_worry"]:
            a("| finding_id | unit_id | reason |")
            a("|---|---|---|")
            for row in res["unmatched_worry"]:
                a(f"| {row['finding_id']} | {row['unit_id']} | {row['reason']} |")
        else:
            a("None.")
        a("")

    # --- Section 7: summary ---------------------------------------------------
    a("## 7. Per-run summary")
    a("")
    a("Mirrors `data/analysis/evaluation_scores.csv`.")
    a("")
    a("| run | schema violations | units correct | stories found (V/G/G-mirror) | "
      "C-trap flags | unmatched worry (candidate FPs) | figures matched/total |")
    a("|---|---|---|---|---|---|---|")
    for rid in valid_run_ids:
        res = run_results[rid]
        stories = "/".join([
            "V" if res["story_v"] else "-",
            "G" if res["story_g"] else "-",
            "G-mirror" if res["story_g_mirror"] else "-",
        ])
        figs = res["figures"]
        matched = figs["counts"]["exact-match"] + figs["counts"]["aggregate-match"]
        a(f"| {rid} | {len(res['schema']['violations'])} | "
          f"{res['units_correct']}/{res['units_total']} | {stories} | "
          f"{len(res['c_trap'])} | {len(res['unmatched_worry'])} | "
          f"{matched}/{figs['total']} |")
    a("")

    a("## Notes on this worksheet's own methodology")
    a("")
    a("- Figure parsing occasionally treats a plain transaction count that")
    a("  happens to have a comma thousands-group (e.g. `1,466`) as a currency")
    a("  candidate. This is harmless by construction: such a number will not")
    a("  match any euro anchor and simply ends up in the not-checkable list")
    a("  above, which is always for adjudication, never a failure.")
    a("- The D and B3 keyword tests' descriptive clauses ('mentions the")
    a("  shared order reference or invoice-number pair'; '(PO|different")
    a("  (order|purchase)|distinct)') are operationalised as literal regexes")
    a("  in `code/evaluate.py`'s `KEYWORD_TESTS` config block; `PO` and `IT`")
    a("  are matched with word boundaries to avoid trivial substring")
    a("  collisions (e.g. 'IT' inside 'unit').")
    a("- This dataset's own build")
    a("  already recorded that the detector overlaps the answer key on zero")
    a("  transactions in any class (G realised 0 of 12, not the pre-registered")
    a("  >=6; B4 and B5 were not flagged). Section 2's mechanical rule (all")
    a("  detector units, SINGLES, and RESIDUAL expect stand_down) reflects")
    a("  that reality automatically, because it is recomputed fresh from the")
    a("  actual `detector_flags.csv` rather than from the design's")
    a("  pre-registered target.")
    a("")

    return "\n".join(lines)


def build_scores_dataframe(tier2: dict) -> pd.DataFrame:
    rows = []
    for run_info in tier2["run_infos"]:
        run_id = run_info["run_id"]
        res = tier2["run_results"].get(run_id, {})
        if "load_error" in res:
            rows.append({
                "run_id": run_id, "load_error": res["load_error"],
                "schema_violations": None, "units_correct": None, "units_total": None,
                "story_v_found": None, "story_g_found": None, "story_g_mirror_found": None,
                "c_trap_flags": None, "unmatched_worry_count": None,
                "figures_matched": None, "figures_total": None,
            })
            continue
        figs = res["figures"]
        rows.append({
            "run_id": run_id,
            "load_error": "",
            "schema_violations": len(res["schema"]["violations"]),
            "units_correct": res["units_correct"],
            "units_total": res["units_total"],
            "story_v_found": bool(res["story_v"]),
            "story_g_found": bool(res["story_g"]),
            "story_g_mirror_found": bool(res["story_g_mirror"]),
            "c_trap_flags": len(res["c_trap"]),
            "unmatched_worry_count": len(res["unmatched_worry"]),
            "figures_matched": figs["counts"]["exact-match"] + figs["counts"]["aggregate-match"],
            "figures_total": figs["total"],
        })
    columns = [
        "run_id", "load_error", "schema_violations", "units_correct", "units_total",
        "story_v_found", "story_g_found", "story_g_mirror_found", "c_trap_flags",
        "unmatched_worry_count", "figures_matched", "figures_total",
    ]
    return pd.DataFrame(rows, columns=columns)


# ===========================================================================
# JSON-safety helper (numpy/pandas scalars -> native Python)
# ===========================================================================

def to_jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]
    if hasattr(obj, "item"):  # numpy scalar
        return obj.item()
    return obj


# ===========================================================================
# Main
# ===========================================================================

def main():
    print("=" * 70)
    print("evaluate.py -- Phase 3 evaluation / marking script")
    print("=" * 70)

    for out_path in OUTPUT_PATHS:
        for in_path in INPUT_PATHS:
            if out_path.resolve() == in_path.resolve():
                raise RuntimeError(f"Output path {out_path} must not equal an input path.")
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

    print("\nLoading public inputs (gl, rule_flags, detector_flags, clusters, answer_key)...")
    inputs = load_public_inputs()

    evaluation, class_totals, key_expanded = run_tier1(inputs)

    print(f"\nWriting {EVALUATION_JSON_PATH} ...")
    with EVALUATION_JSON_PATH.open("w", encoding="utf-8") as f:
        json.dump(to_jsonable(evaluation), f, indent=2, ensure_ascii=False)
    print("  Done.")

    tier2 = run_tier2(inputs, class_totals, key_expanded)

    print(f"\nWriting {WORKSHEET_PATH} ...")
    worksheet_text = render_worksheet(tier2)
    with WORKSHEET_PATH.open("w", encoding="utf-8") as f:
        f.write(worksheet_text)
    print("  Done.")

    print(f"\nWriting {SCORES_CSV_PATH} ...")
    scores_df = build_scores_dataframe(tier2)
    scores_df.to_csv(SCORES_CSV_PATH, index=False, encoding="utf-8")
    print("  Done.")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Rule flags: {evaluation['inventory']['rule_flags_total']}  "
          f"Detector flags: {evaluation['inventory']['detector_flags_total']}  "
          f"Verdict units: {evaluation['inventory']['verdict_units_total']}")
    print(f"Rule-layer precision vs anomalous kind:     "
          f"{evaluation['layers']['rules']['precision_vs_anomalous']['precision']}")
    print(f"Detector-layer precision vs anomalous kind: "
          f"{evaluation['layers']['detector']['precision_vs_anomalous']['precision']}")
    if scores_df.empty:
        print("No storyteller runs found yet -- tier 2 worksheet is a placeholder. "
              "Re-run this script once run_02/run_03 land.")
    else:
        print(scores_df.to_string(index=False))
    print()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nFATAL: {exc}")
        sys.exit(1)
