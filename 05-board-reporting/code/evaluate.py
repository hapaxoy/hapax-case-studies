"""
evaluate.py -- Mechanical evaluation layer for Case Study 5 (Board Reporting
Automation, Paju Consumer Products Oy).

FRAMING -- read this before trusting any single line of the worksheet this
script writes. This script is the MECHANICAL layer only. It runs schema
checks, keyword/structural pattern matching, and CSV-derived arithmetic
against the storyteller agents' findings JSON. It does not read prose for
meaning and it does not hand down a final verdict. Wherever a rule below is
ambiguous -- a finding that half-matches a story, a figure that is "close
but not exact", a severity call that could go either way -- the script says
so explicitly and lists the item for a HUMAN ADJUDICATOR rather than
silently scoring it. The one-line scorecard that goes into
`data/analysis/report.md` is written separately, by hand, after
reading the worksheet this script produces end to end. A dataset -- or an
evaluation script -- that silently guesses is a bug, per the case studies'
coherence-rule discipline; the same discipline applies here.

This script is evaluation-side, not generation-side, so unlike the rest of
code/ it DOES read data/answer_key/stories.csv -- that is by design (the
answer key "stays out of the modelling path entirely"; the
storyteller agents never see it, per the storyteller briefing's hard rule,
but the mechanical grader is exactly the thing the answer key exists for).

It never writes to, or otherwise modifies, anything under
data/analysis/agent_runs/ -- that directory is the storyteller agents' own
output and audit trail; this script only reads it.

Inputs:
    data/answer_key/stories.csv                    (S1-S4, N1-N4 ground truth)
    data/analysis/agent_runs/run_NN_findings.json   (one or more runs, globbed)
    data/pnl_monthly.csv, data/opex_monthly.csv,
    data/working_capital_monthly.csv,
    data/receivables_by_customer_monthly.csv        (figure verification, SSE)

Outputs (data/analysis/):
    evaluation_worksheet.md  -- the human-readable worksheet; the deliverable
                                 a person (the adjudicator) reads end to end
    evaluation_scores.csv    -- the same checks, tidy, one row each, for
                                 filtering/sorting/pivoting by hand

Run from the project root:
    python code/evaluate.py
"""

import json
import re
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
ANALYSIS_DIR = DATA_DIR / "analysis"
AGENT_RUNS_DIR = ANALYSIS_DIR / "agent_runs"
ANSWER_KEY_PATH = DATA_DIR / "answer_key" / "stories.csv"

assert ANALYSIS_DIR != DATA_DIR, "output dir must differ from the source data dir"
assert ANALYSIS_DIR.resolve() != AGENT_RUNS_DIR.resolve(), "must never write into agent_runs/"

# =============================================================================
# CONFIG -- schema, cluster map, keyword patterns, figure definitions
# =============================================================================

# --- A. Findings-schema fields, per the storyteller briefing's JSON schema ---

SCHEMA_TOP_LEVEL_FIELDS = [
    "finding_id", "headline", "cluster", "category", "verdict", "affected",
    "claimed_cause", "evidence", "severity", "confidence", "recommended_action",
]
SCHEMA_AFFECTED_FIELDS = ["bus", "lines", "customers", "months"]
SCHEMA_EVIDENCE_FIELDS = ["table", "what", "figures"]

LEGAL_CATEGORY = {"revenue", "margin", "cost", "working_capital", "cash", "seasonality", "budget", "none"}
LEGAL_VERDICT = {"worry", "stand_down"}
LEGAL_SEVERITY = {"info", "watch", "act"}
LEGAL_CONFIDENCE = {"low", "medium", "high"}

# --- B. Designed verdict per pack flag cluster -----------------------------
# From the design's expected-findings matrix and the S1-S4 write-ups.
# Cluster numbers are the storyteller briefing's six flag clusters (what the
# deterministic pack surfaces); they overlap with, but are not identical to,
# the four story IDs S1-S4 (a cluster can be a story's pack-visible face, a
# noise-ledger item's face, or both at once -- see the per-cluster note).

CLUSTER_DESIGNED_VERDICT = {
    # C1 = January MoM collapse = S4, the trap. The design, S4: "Stand
    # down -- seasonal, in line with budget and prior year, no action."
    1: "stand_down",
    # C2 = Nordics material cost = S1's pack flag. NOT in this map -- S1's
    # failure mode is "right variance, wrong cause", which a
    # single worry/stand_down verdict can't capture; evaluated by its own
    # two-part test, evaluate_cluster_2() below.
    # C3 = Baltics & Poland net revenue = S3's pack flag, a good-news
    # headline. The design, S3: the storyteller must surface that the
    # growth is bought and fading -- a worry on the economics is correct
    # even where the top-line growth finding itself stands down (a split
    # verdict across two C3 findings is accepted, not penalised).
    3: "worry",
    # C4 = reported EBITDA vs budget, concentrated Nordics + Baltics &
    # Poland. The design's expected-findings matrix: a real, worry-worthy
    # variance (S1's margin effect and S3's margin erosion both surface
    # here). N4 (structural budget optimism) is a sub-flag that must be
    # *noted*, not dramatised, and not used to explain away the story-driven
    # part of the gap -- see the N4 check below.
    4: "worry",
    # C5 = Central Europe DSO = S2's one pack-visible thread (the appendix
    # nobody reads, per the design, S2). Worry, with Rheinkauf Gruppe
    # named as the decisive sub-flag.
    5: "worry",
    # C6 = the April EBITDA spike = S2's masking one-off. On its own this is
    # a real, disclosed, non-recurring gain -- the flag itself should stand
    # down. The story is in linking it to what it masks (S2's cash
    # conversion and DSO deterioration), which is the sub-flag below.
    6: "stand_down",
}

# --- C/D. Keyword patterns for structural/keyword matching ------------------
# Every pattern here is quoted verbatim (or near-verbatim) from the
# evaluation rules so the adjudicator can audit the matcher against the
# rules that produced it, not just against this code.

RE_CAUSE_MIX_PROMO_DISCOUNT = re.compile(r"(mix|trade.down|promo|discount)", re.I)
RE_LINE_HOME_SKIN = re.compile(r"(Home Care|Skin & Body)", re.I)
# "unit cost"/"unit material cost" AND its common reversed phrasing "material
# cost per unit"/"cost per unit" -- a real run in development wrote the latter
# ("material cost per unit is flat year-on-year") and the unit-only pattern
# missed it entirely, which would have wrongly failed the S1/C2 unit-cost-flat
# check for a finding that was, in substance, making exactly that claim.
RE_UNIT_COST = re.compile(r"unit (material )?cost|(material )?cost per unit", re.I)
RE_FLAT_STABLE = re.compile(r"\bflat\b|\bstable\b|below[- ]budget", re.I)
RE_COMMODITY_INFLATION = re.compile(r"commodity|input[- ]cost|input price|raw material price|input inflation", re.I)
RE_RHEINKAUF = re.compile(r"rheinkauf", re.I)
RE_TERMS_DSO = re.compile(r"\bterms\b|\bDSO\b|\bdays\b", re.I)
RE_RECEIVABLE_BUILD = re.compile(r"receivable|closing ar\b|\bAR\b", re.I)
RE_MASK = re.compile(r"\bmask(s|ed|ing)?\b|\bflatter(s|ed|ing)?\b|\bunderlying\b|exclude(d|s)?\s+from\s+run.rate", re.I)
RE_DISCOUNT_BOUGHT = re.compile(r"discount|bought", re.I)
RE_ELASTICITY = re.compile(r"elastic|fade|weaker response|diminishing", re.I)
RE_BUDGET_OPTIMISM = re.compile(
    r"optimis(m|tic)|planning bias|budget (runs?|running) hot|budget (is |was )?set high|pre-?dates?", re.I
)
RE_YOY_OR_BUDGET_EVIDENCE = re.compile(r"\byoy\b|year.on.year|vs[. ]?budget|against budget", re.I)

# Negation guard for causal-attribution patterns (RE_COMMODITY_INFLATION above
# all -- "not input-cost inflation" is a finding correctly REJECTING that
# cause, not blaming it; a bare regex.search() cannot tell the difference).
# Applied to every keyword check below that asserts a CAUSE, not just a
# topic's presence (RE_RHEINKAUF, RE_TERMS_DSO etc. stay plain .search() --
# a name or a topic being present is relevant regardless of surrounding
# negation, e.g. "Rheinkauf did not improve" is still a Rheinkauf finding).
NEGATION_RE = re.compile(r"\b(not|isn.t|isnt|no|never|n.t|without|rules? out|ruled out|rather than|instead of)\b", re.I)
NEGATION_WINDOW_CHARS = 40  # roughly 5-8 words of look-back before the match


def matches_positively(pattern: re.Pattern, text: str) -> bool:
    """True if `pattern` matches `text` at least once with no negation word in
    the NEGATION_WINDOW_CHARS immediately before that match. Best-effort, not a
    parser -- it catches the clear case ("not X") that a bare .search() cannot,
    and leaves anything subtler to the worksheet's disagree/adjudicate paths."""
    for m in pattern.finditer(text):
        window_start = max(0, m.start() - NEGATION_WINDOW_CHARS)
        if NEGATION_RE.search(text[window_start:m.start()]):
            continue
        return True
    return False

# --- E. Fixed company-level figures re-derived from the public CSVs --------
# Tolerance defaults per the evaluation rules: +/-0.1pp for percentages, +/-EUR 10,000
# for euro amounts, "unless stated" -- none of these need a wider band.

TOL_EUR_DEFAULT = 10_000.0
TOL_PCT_DEFAULT = 0.1

# Each figure: id -> (label, unit ["eur"|"pct"], tolerance, context rule).
# Context rule = {"all": [required substrings, ALL must appear],
#                  "any_groups": [[group1 alternatives], [group2 alternatives], ...],
#                  each group needs >=1 hit}. Matched against the finding's
# headline + claimed_cause + category + evidence "table"/"what"/"figures"
# text, lower-cased. This determines whether a finding is even "about" a
# given figure; the euro/percentage TOKENS used for the agree/disagree call
# are extracted only from evidence[].figures (Section E), never from "what".
# Company-level figures require the literal word "company" in context, not
# just the driver name (e.g. "net revenue") -- BU-level findings (Baltics
# net revenue, Nordics material cost) use the same driver vocabulary, and
# without this the matcher would compare a BU number against the company
# total and call it a "disagreement" that isn't one. This under-detects some
# true positives phrased without the word "company" (e.g. "FY2024 EBITDA
# EUR X vs budget" with no BU qualifier, which IS the company figure) -- an
# accepted false-negative ("not checked") in favour of not manufacturing
# false "disagree"s, per the evaluation rules' own instruction to lean that way.
FIGURE_CONTEXT_RULES = {
    "company_net_revenue_fy24":     {"all": ["company", "net revenue"], "any_groups": [["2024", "fy24", "fy2024"]]},
    "company_net_revenue_fy25":     {"all": ["company", "net revenue"], "any_groups": [["2025", "fy25", "fy2025"]]},
    "company_revenue_growth_pct":   {"all": ["company", "net revenue"], "any_groups": [["growth", "grew", "grow"]]},
    "gm_pct_fy24":                  {"all": ["company", "gross margin"], "any_groups": [["2024", "fy24", "fy2024"]]},
    "gm_pct_fy25":                  {"all": ["company", "gross margin"], "any_groups": [["2025", "fy25", "fy2025"]]},
    "ebitda_reported_fy24":         {"all": ["company", "ebitda"], "any_groups": [["2024", "fy24", "fy2024"]]},
    "ebitda_reported_fy25":         {"all": ["company", "ebitda"], "any_groups": [["2025", "fy25", "fy2025"]]},
    "ebitda_underlying_fy24":       {"all": ["company", "ebitda", "underlying"], "any_groups": [["2024", "fy24", "fy2024"]]},
    "ebitda_underlying_fy25":       {"all": ["company", "ebitda", "underlying"], "any_groups": [["2025", "fy25", "fy2025"]]},
    "company_ar_dec2024":           {"all": ["company", "receivable"], "any_groups": [["opening", "dec-2024", "december 2024", "dec 2024"]]},
    "company_ar_dec2025":           {"all": ["company", "receivable"], "any_groups": [["closing", "dec-2025", "december 2025", "dec 2025"]]},
    "company_ar_build_2025":        {"all": ["company", "receivable"], "any_groups": [["build", "increase", "rose", "grew", "growth"]]},
    "nordics_material_yoy_pct":     {"all": ["material"], "any_groups": [["nordics"]]},
    "baltics_discount_fy24_pct":    {"all": ["discount", "baltics"], "any_groups": [["2024", "fy24", "fy2024"]]},
    "baltics_discount_dec2025_pct": {"all": ["discount", "baltics"], "any_groups": [["dec", "december"]]},
    "ce_ar_dec24":                  {"all": ["receivable"], "any_groups": [["central europe", "ce closing", "ce total ar"], ["2024", "dec-2024", "december 2024", "dec 2024"]]},
    "ce_ar_dec25":                  {"all": ["receivable"], "any_groups": [["central europe", "ce closing", "ce total ar"], ["2025", "dec-2025", "december 2025", "dec 2025"]]},
    "rheinkauf_ar_dec24":           {"all": ["rheinkauf"], "any_groups": [["2024", "dec-2024", "december 2024", "dec 2024"]]},
    "rheinkauf_ar_dec25":           {"all": ["rheinkauf"], "any_groups": [["2025", "dec-2025", "december 2025", "dec 2025"]]},
}
# Explicit, not inferred from the id string -- a suffix heuristic (e.g. "ends
# with _pct") silently mis-typed gm_pct_fy24/fy25 during development (the
# "pct" sits mid-identifier, not at the end), which would have compared a
# gross-margin PERCENTAGE against the EUR tolerance/extractor. Left explicit
# on purpose so that class of bug cannot recur silently.
FIGURE_UNITS = {
    "company_net_revenue_fy24": "eur",
    "company_net_revenue_fy25": "eur",
    "company_revenue_growth_pct": "pct",
    "gm_pct_fy24": "pct",
    "gm_pct_fy25": "pct",
    "ebitda_reported_fy24": "eur",
    "ebitda_reported_fy25": "eur",
    "ebitda_underlying_fy24": "eur",
    "ebitda_underlying_fy25": "eur",
    "company_ar_dec2024": "eur",
    "company_ar_dec2025": "eur",
    "company_ar_build_2025": "eur",
    "nordics_material_yoy_pct": "pct",
    "baltics_discount_fy24_pct": "pct",
    "baltics_discount_dec2025_pct": "pct",
    "ce_ar_dec24": "eur",
    "ce_ar_dec25": "eur",
    "rheinkauf_ar_dec24": "eur",
    "rheinkauf_ar_dec25": "eur",
}
assert set(FIGURE_UNITS) == set(FIGURE_CONTEXT_RULES), "FIGURE_UNITS must cover exactly the figures in FIGURE_CONTEXT_RULES"
FIGURE_LABELS = {
    "company_net_revenue_fy24": "FY2024 company net revenue",
    "company_net_revenue_fy25": "FY2025 company net revenue",
    "company_revenue_growth_pct": "FY2025 vs FY2024 company net revenue growth",
    "gm_pct_fy24": "FY2024 company gross margin %",
    "gm_pct_fy25": "FY2025 company gross margin %",
    "ebitda_reported_fy24": "FY2024 reported EBITDA",
    "ebitda_reported_fy25": "FY2025 reported EBITDA",
    "ebitda_underlying_fy24": "FY2024 underlying EBITDA (ex one-offs -- none in FY24)",
    "ebitda_underlying_fy25": "FY2025 underlying EBITDA (ex the April one-off)",
    "company_ar_dec2024": "Company AR closing Dec-2024 (= opening Jan-2025)",
    "company_ar_dec2025": "Company AR closing Dec-2025",
    "company_ar_build_2025": "Company AR build over 2025 (Dec25 - Dec24)",
    "nordics_material_yoy_pct": "Nordics FY2025 material spend, YoY %",
    "baltics_discount_fy24_pct": "Baltics & Poland discount rate, FY2024",
    "baltics_discount_dec2025_pct": "Baltics & Poland discount rate, Dec-2025",
    "ce_ar_dec24": "Central Europe closing AR, Dec-2024",
    "ce_ar_dec25": "Central Europe closing AR, Dec-2025",
    "rheinkauf_ar_dec24": "Rheinkauf Gruppe closing AR, Dec-2024",
    "rheinkauf_ar_dec25": "Rheinkauf Gruppe closing AR, Dec-2025",
}

# =============================================================================
# Loading
# =============================================================================

def load_answer_key() -> pd.DataFrame:
    if not ANSWER_KEY_PATH.exists():
        print(f"FATAL: answer key not found at {ANSWER_KEY_PATH}", file=sys.stderr)
        sys.exit(1)
    return pd.read_csv(ANSWER_KEY_PATH)


def parse_semicolon_list(raw: str) -> list:
    """'A; B; C' -> ['A','B','C']; '(none)'/'(all three)'/'(all four)' -> []
    (these are prose placeholders in stories.csv, not entity lists)."""
    if not isinstance(raw, str) or not raw.strip():
        return []
    if raw.strip().startswith("("):
        return []
    return [x.strip() for x in raw.split(";") if x.strip()]


def load_runs() -> dict:
    """Glob run_NN_findings.json under agent_runs/. Returns {run_id: (findings_list_or_None, load_error_or_None)}."""
    paths = sorted(AGENT_RUNS_DIR.glob("run_*_findings.json"))
    runs = {}
    for p in paths:
        run_id = p.stem.replace("_findings", "")
        try:
            text = p.read_text(encoding="utf-8")
            data = json.loads(text)
            if not isinstance(data, list):
                runs[run_id] = (None, f"top-level JSON is not an array (got {type(data).__name__})")
            else:
                runs[run_id] = (data, None)
        except Exception as exc:
            runs[run_id] = (None, f"failed to load/parse: {exc}")
    return runs


def load_public_tables() -> dict:
    paths = {
        "pnl": DATA_DIR / "pnl_monthly.csv",
        "opex": DATA_DIR / "opex_monthly.csv",
        "wc": DATA_DIR / "working_capital_monthly.csv",
        "recv": DATA_DIR / "receivables_by_customer_monthly.csv",
    }
    missing = [k for k, p in paths.items() if not p.exists()]
    if missing:
        print(f"FATAL: missing public data files: {missing}. Run generate_financials.py first.", file=sys.stderr)
        sys.exit(1)
    return {k: pd.read_csv(p) for k, p in paths.items()}


# =============================================================================
# Text helpers -- keyword search over a finding's full text
# =============================================================================

def finding_text(f: dict) -> str:
    """All human-readable text on a finding, concatenated, for keyword search.
    Used everywhere EXCEPT figure-token extraction (SSE), which is scoped to
    evidence[].figures only, by design."""
    parts = [f.get("headline") or "", f.get("claimed_cause") or "", f.get("category") or ""]
    for e in (f.get("evidence") or []):
        if isinstance(e, dict):
            parts.append(e.get("table") or "")
            parts.append(e.get("what") or "")
            parts.append(e.get("figures") or "")
    aff = f.get("affected") or {}
    if isinstance(aff, dict):
        parts.append(" ".join(aff.get("customers") or []))
        parts.append(" ".join(aff.get("lines") or []))
        parts.append(" ".join(aff.get("bus") or []))
    parts.append(f.get("recommended_action") or "")
    return " ".join(str(p) for p in parts)


def run_text(findings: list) -> str:
    """All text across every finding in a run -- for 'anywhere in the run' checks."""
    return " \n ".join(finding_text(f) for f in findings)


def affected_bus(f: dict) -> list:
    aff = f.get("affected") or {}
    return aff.get("bus") or [] if isinstance(aff, dict) else []


def affected_lines(f: dict) -> list:
    aff = f.get("affected") or {}
    return aff.get("lines") or [] if isinstance(aff, dict) else []


def affected_customers(f: dict) -> list:
    aff = f.get("affected") or {}
    return aff.get("customers") or [] if isinstance(aff, dict) else []


def affected_months(f: dict) -> str:
    aff = f.get("affected") or {}
    return aff.get("months") or "" if isinstance(aff, dict) else ""


def parse_month_range(s: str):
    """'2025-02..2025-12' -> ('2025-02','2025-12'); a bare month -> (m, m). None on failure."""
    if not isinstance(s, str) or not s.strip():
        return None
    s = s.strip()
    if ".." in s:
        parts = s.split("..")
        if len(parts) != 2:
            return None
        return (parts[0].strip(), parts[1].strip())
    return (s, s)


def get_cluster_findings(findings: list, cluster_n: int) -> list:
    return [f for f in findings if f.get("cluster") == cluster_n]


# =============================================================================
# A. Schema validation
# =============================================================================

def validate_schema(findings: list) -> tuple:
    """Returns (violations: list[str], cluster_coverage: {1..6: n findings with explicit verdict})."""
    violations = []
    seen_ids = set()
    for i, f in enumerate(findings):
        label = f.get("finding_id") if isinstance(f, dict) else None
        label = label or f"<finding index {i}, no finding_id>"
        if not isinstance(f, dict):
            violations.append(f"{label}: finding is not a JSON object")
            continue

        missing = [k for k in SCHEMA_TOP_LEVEL_FIELDS if k not in f]
        if missing:
            violations.append(f"{label}: missing top-level field(s) {missing}")

        fid = f.get("finding_id")
        if not fid:
            violations.append(f"{label}: missing or empty finding_id")
        elif fid in seen_ids:
            violations.append(f"{fid}: duplicate finding_id")
        else:
            seen_ids.add(fid)

        cluster = f.get("cluster")
        if cluster is not None and cluster not in range(1, 7):
            violations.append(f"{label}: cluster={cluster!r} is not null or an integer 1-6")

        category = f.get("category")
        if category not in LEGAL_CATEGORY:
            violations.append(f"{label}: category={category!r} not in {sorted(LEGAL_CATEGORY)}")

        verdict = f.get("verdict")
        if verdict not in LEGAL_VERDICT:
            violations.append(f"{label}: verdict={verdict!r} not in {sorted(LEGAL_VERDICT)}")

        severity = f.get("severity")
        if severity not in LEGAL_SEVERITY:
            violations.append(f"{label}: severity={severity!r} not in {sorted(LEGAL_SEVERITY)}")

        confidence = f.get("confidence")
        if confidence not in LEGAL_CONFIDENCE:
            violations.append(f"{label}: confidence={confidence!r} not in {sorted(LEGAL_CONFIDENCE)}")

        aff = f.get("affected")
        if not isinstance(aff, dict):
            violations.append(f"{label}: affected is missing or not an object")
        else:
            missing_aff = [k for k in SCHEMA_AFFECTED_FIELDS if k not in aff]
            if missing_aff:
                violations.append(f"{label}: affected missing field(s) {missing_aff}")
            for k in ("bus", "lines", "customers"):
                if k in aff and not isinstance(aff[k], list):
                    violations.append(f"{label}: affected.{k} is not a list")
            if "months" in aff and not isinstance(aff["months"], str):
                violations.append(f"{label}: affected.months is not a string")

        evidence = f.get("evidence")
        if not isinstance(evidence, list) or len(evidence) == 0:
            violations.append(
                f"{label}: evidence is missing or empty (every verdict must carry evidence, "
                f"per the storyteller briefing -- 'stand_down is a first-class answer and must "
                f"carry evidence like any other')"
            )
        else:
            for j, e in enumerate(evidence):
                if not isinstance(e, dict):
                    violations.append(f"{label}: evidence[{j}] is not an object")
                    continue
                missing_e = [k for k in SCHEMA_EVIDENCE_FIELDS if k not in e]
                if missing_e:
                    violations.append(f"{label}: evidence[{j}] missing field(s) {missing_e}")

    coverage = {}
    for c in range(1, 7):
        c_findings = [f for f in findings if isinstance(f, dict) and f.get("cluster") == c and f.get("verdict") in LEGAL_VERDICT]
        coverage[c] = len(c_findings)
        if not c_findings:
            violations.append(
                f"cluster {c}: no finding carries an explicit verdict (worry/stand_down) for this "
                f"cluster -- the storyteller briefing requires every one of the six clusters to have one"
            )

    return violations, coverage


# =============================================================================
# B. Cluster verdicts
# =============================================================================

def evaluate_cluster_standard(findings: list, cluster_n: int, designed_verdict: str) -> dict:
    c_findings = get_cluster_findings(findings, cluster_n)
    verdicts = {f.get("verdict") for f in c_findings}
    finding_ids = [f.get("finding_id") for f in c_findings]
    if not c_findings:
        return {"outcome": "MISSING -- no finding tagged to this cluster", "finding_ids": finding_ids, "verdicts_seen": sorted(verdicts)}
    if designed_verdict == "stand_down":
        if "worry" in verdicts:
            outcome = "CRIED WOLF -- a worry verdict present where the design calls for stand_down"
        elif "stand_down" in verdicts:
            outcome = "correct (stand_down delivered)"
        else:
            outcome = "adjudicate -- no worry/stand_down verdict found on this cluster"
    else:  # worry
        if "worry" in verdicts:
            outcome = "correct (worry delivered)"
        elif "stand_down" in verdicts:
            outcome = "WRONG -- stood down where the design calls for worry"
        else:
            outcome = "adjudicate -- no worry/stand_down verdict found on this cluster"
    return {"outcome": outcome, "finding_ids": finding_ids, "verdicts_seen": sorted(verdicts)}


def evaluate_cluster_2(findings: list) -> dict:
    """C2 (Nordics material cost, S1's pack flag) -- two-part test:
    (i) some C2 finding asserts unit material cost flat/stable/below-budget;
    (ii) some finding in the RUN (any cluster) attributes Nordics margin
        movement to discount/promo/mix/trade-down.
    Both -> "correct (possibly distributed)". Only (i) -> "half: false-trail
    identified, cause not delivered". A C2 finding blaming commodity/input-
    price inflation -> "wrong cause"."""
    c2 = get_cluster_findings(findings, 2)
    finding_ids = [f.get("finding_id") for f in c2]
    if not c2:
        return {"outcome": "MISSING -- no finding tagged to cluster 2", "finding_ids": [], "part_i": False, "part_ii": False, "wrong_cause": False}

    part_i = any(RE_UNIT_COST.search(finding_text(f)) and RE_FLAT_STABLE.search(finding_text(f)) for f in c2)
    part_ii = any(
        ("Nordics" in affected_bus(f) or re.search(r"nordics", finding_text(f), re.I))
        and matches_positively(RE_CAUSE_MIX_PROMO_DISCOUNT, finding_text(f))
        for f in findings
    )
    wrong_cause = any(matches_positively(RE_COMMODITY_INFLATION, finding_text(f)) for f in c2)

    if wrong_cause and part_i:
        outcome = (
            "MIXED -- adjudicate: unit-cost-flat asserted in cluster 2 AND commodity/input-cost "
            "inflation blamed in (another) cluster-2 finding"
        )
    elif wrong_cause:
        outcome = "wrong cause"
    elif part_i and part_ii:
        outcome = "correct (possibly distributed)"
    elif part_i:
        outcome = "half: false-trail identified, cause not delivered"
    else:
        outcome = "adjudicate -- no unit-cost-flat assertion found in cluster 2"

    return {"outcome": outcome, "finding_ids": finding_ids, "part_i": part_i, "part_ii": part_ii, "wrong_cause": wrong_cause}


def n4_noted(findings: list) -> dict:
    hits = [f.get("finding_id") for f in findings if matches_positively(RE_BUDGET_OPTIMISM, finding_text(f))]
    return {"noted": len(hits) > 0, "finding_ids": hits}


def rheinkauf_named(findings_subset: list) -> bool:
    return any(RE_RHEINKAUF.search(finding_text(f)) or "Rheinkauf Gruppe" in affected_customers(f) for f in findings_subset)


def mask_linkage_present(findings: list) -> dict:
    hits = [f.get("finding_id") for f in findings if matches_positively(RE_MASK, finding_text(f))]
    return {"present": len(hits) > 0, "finding_ids": hits}


def evaluate_clusters(findings: list) -> dict:
    result = {}
    result[1] = evaluate_cluster_standard(findings, 1, CLUSTER_DESIGNED_VERDICT[1])
    result[2] = evaluate_cluster_2(findings)
    result[3] = evaluate_cluster_standard(findings, 3, CLUSTER_DESIGNED_VERDICT[3])
    result[4] = evaluate_cluster_standard(findings, 4, CLUSTER_DESIGNED_VERDICT[4])
    result[4]["n4_sub_flag"] = n4_noted(findings)
    result[5] = evaluate_cluster_standard(findings, 5, CLUSTER_DESIGNED_VERDICT[5])
    result[5]["rheinkauf_sub_flag"] = rheinkauf_named(get_cluster_findings(findings, 5))
    result[6] = evaluate_cluster_standard(findings, 6, CLUSTER_DESIGNED_VERDICT[6])
    result[6]["mask_sub_flag"] = mask_linkage_present(findings)
    return result


# =============================================================================
# C. Story detection matrix
# =============================================================================

def detect_s1(findings: list) -> dict:
    matches = []
    for f in findings:
        if "Nordics" not in affected_bus(f):
            continue
        text = finding_text(f)
        if not matches_positively(RE_CAUSE_MIX_PROMO_DISCOUNT, text):
            continue
        line_hit = any(l in affected_lines(f) for l in ("Home Care", "Skin & Body")) or RE_LINE_HOME_SKIN.search(text)
        if not line_hit:
            continue
        matches.append(f.get("finding_id"))
    detected = len(matches) > 0
    unit_cost_flat_anywhere = any(RE_UNIT_COST.search(finding_text(f)) and RE_FLAT_STABLE.search(finding_text(f)) for f in findings)
    return {
        "detected": detected, "finding_ids": matches,
        "cause_correct_candidate": detected and unit_cost_flat_anywhere,
        "unit_cost_flat_asserted_anywhere": unit_cost_flat_anywhere,
    }


def detect_s2(findings: list) -> dict:
    rheinkauf_findings = [f for f in findings if RE_RHEINKAUF.search(finding_text(f)) or "Rheinkauf Gruppe" in affected_customers(f)]
    detected = len(rheinkauf_findings) > 0
    terms_dso = any(RE_TERMS_DSO.search(finding_text(f)) for f in rheinkauf_findings)
    receivable_build = any(RE_RECEIVABLE_BUILD.search(finding_text(f)) for f in rheinkauf_findings)
    mask = mask_linkage_present(findings)
    return {
        "detected": detected, "finding_ids": [f.get("finding_id") for f in rheinkauf_findings],
        "terms_dso_language": terms_dso, "receivable_build_figures": receivable_build,
        "mask_linkage": mask["present"], "mask_finding_ids": mask["finding_ids"],
    }


def detect_s3(findings: list, concentrated_accounts: list) -> dict:
    matches = []
    for f in findings:
        if "Baltics & Poland" not in affected_bus(f):
            continue
        if not matches_positively(RE_DISCOUNT_BOUGHT, finding_text(f)):
            continue
        matches.append(f.get("finding_id"))
    detected = len(matches) > 0
    account_hit = any(
        any(name in affected_customers(f) or name.lower() in finding_text(f).lower() for name in concentrated_accounts)
        for f in findings
    )
    elasticity_hit = any(RE_ELASTICITY.search(finding_text(f)) for f in findings)
    return {
        "detected": detected, "finding_ids": matches,
        "account_names_evidenced": account_hit, "elasticity_language": elasticity_hit,
    }


def detect_s4(findings: list) -> dict:
    c1 = get_cluster_findings(findings, 1)
    stand_down = [f for f in c1 if f.get("verdict") == "stand_down"]
    passing = [f for f in stand_down if RE_YOY_OR_BUDGET_EVIDENCE.search(finding_text(f))]
    return {"passed": len(passing) > 0, "finding_ids": [f.get("finding_id") for f in passing], "stand_down_finding_ids": [f.get("finding_id") for f in stand_down]}


def noise_references(findings: list, bu: str, month: str) -> list:
    """Findings whose affected months+BU overlap a single-month noise-ledger event."""
    refs = []
    for f in findings:
        rng = parse_month_range(affected_months(f))
        if rng is None:
            continue
        month_hit = rng[0] <= month <= rng[1]
        bu_hit = bu in affected_bus(f) or "Company" in affected_bus(f)
        if month_hit and bu_hit:
            refs.append(f)
    return refs


def classify_noise_ref(f: dict) -> str:
    return "dramatised" if f.get("severity") == "act" else "noted"


# =============================================================================
# D. Unmatched findings
# =============================================================================

def compute_matched_ids(findings: list, s1: dict, s2: dict, s3: dict, s4: dict, noise_ref_lists: list, n4: dict) -> set:
    matched = set()
    for f in findings:
        if isinstance(f.get("cluster"), int) and 1 <= f.get("cluster") <= 6:
            matched.add(f.get("finding_id"))
    matched |= set(s1["finding_ids"]) | set(s2["finding_ids"]) | set(s3["finding_ids"]) | set(s4["finding_ids"])
    for refs in noise_ref_lists:
        matched |= {f.get("finding_id") for f in refs}
    matched |= set(n4["finding_ids"])
    return matched


def unmatched_findings(findings: list, matched_ids: set) -> list:
    return [f for f in findings if f.get("severity") in ("watch", "act") and f.get("finding_id") not in matched_ids]


# =============================================================================
# E. Figure verification
# =============================================================================

_RE_PCT = re.compile(r"([+-]?\d+(?:\.\d+)?)\s?%")
_RE_PP = re.compile(r"([+-]?\d+(?:\.\d+)?)\s?pp\b", re.I)
_RE_DAY = re.compile(r"\d+(?:\.\d+)?\s?d(?:ays)?\b", re.I)
_RE_UNIT_NOISE = re.compile(r"\d+(?:\.\d+)?\s?(?:units|fte|eur/unit)\b", re.I)
_RE_EUR_PREFIXED = re.compile(r"[+-]?\s*(?:EUR|€)\s*[+-]?\s*(\d[\d,]*\.?\d*)\s*(million|mn|thousand|m\b|k\b)?", re.I)
_RE_BARE_COMMA = re.compile(r"(?<![\d.,])([+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?)(?!\s*(?:%|pp\b|d\b|days\b|units\b))")
_RE_BARE_MK = re.compile(r"(?<![\d.])([+-]?\d+\.\d+|\d+)\s?(million|mn|m\b|k\b|thousand)\b(?!\s*units)", re.I)


def _mask_non_eur_tokens(text: str) -> str:
    text = _RE_PCT.sub(" ", text)
    text = _RE_PP.sub(" ", text)
    text = _RE_DAY.sub(" ", text)
    text = _RE_UNIT_NOISE.sub(" ", text)
    return text


def _to_value(num_str: str, suffix) -> float:
    v = float(num_str.replace(",", ""))
    if suffix:
        s = suffix.lower()
        if s in ("million", "mn", "m"):
            v *= 1_000_000
        elif s in ("thousand", "k"):
            v *= 1_000
    return v


def extract_eur_tokens(text: str) -> list:
    """Approximate euro-value extraction from evidence 'figures' strings. Deliberately
    permissive (catches EUR-prefixed AND bare comma/million/thousand-suffixed numbers,
    since evidence text often drops the currency prefix on the second of a pair, e.g.
    'EUR 2,060,367 -> 4,493,177') -- this is why the evaluation rules call the whole exercise
    approximate string matching, not parsing, and why unmatched tokens are 'not
    checked' rather than 'wrong' throughout this module."""
    masked = _mask_non_eur_tokens(text)
    vals = []
    for m in _RE_EUR_PREFIXED.finditer(masked):
        vals.append(_to_value(m.group(1), m.group(2)))
    for m in _RE_BARE_COMMA.finditer(masked):
        vals.append(_to_value(m.group(1), None))
    for m in _RE_BARE_MK.finditer(masked):
        vals.append(_to_value(m.group(1), m.group(2)))
    return vals


def extract_pct_tokens(text: str) -> list:
    return [float(m.group(1)) for m in _RE_PCT.finditer(text)]


def context_hit(text_lower: str, rule: dict) -> bool:
    for kw in rule.get("all", []):
        if kw.lower() not in text_lower:
            return False
    for group in rule.get("any_groups", []):
        if not any(kw.lower() in text_lower for kw in group):
            return False
    return True


def compute_public_figures(tables: dict) -> dict:
    """Recomputes the fixed set of company-level figures from the public CSVs only
    (Section E) -- independent of, and a cross-check against, both surface_report.md
    and validate_financials.py's rule 8 bands (which check story SIGNATURES, not
    these specific headline numbers)."""
    pnl, opex, wc, recv = tables["pnl"], tables["opex"], tables["wc"], tables["recv"]

    def fy(df, year):
        return df[df["month"].str.startswith(year)]

    def company_ebitda(year):
        gp = fy(pnl, year)["gross_profit"].sum()
        o = fy(opex, year)
        reported = gp - o["sales_marketing"].sum() - o["admin_general"].sum() + o["other_income"].sum()
        underlying = reported - o["other_income"].sum()
        return reported, underlying

    nr24 = fy(pnl, "2024")["net_revenue"].sum()
    nr25 = fy(pnl, "2025")["net_revenue"].sum()
    gp24 = fy(pnl, "2024")["gross_profit"].sum()
    gp25 = fy(pnl, "2025")["gross_profit"].sum()
    ebitda_rep24, ebitda_und24 = company_ebitda("2024")
    ebitda_rep25, ebitda_und25 = company_ebitda("2025")

    wc_co = wc.groupby("month")[["receivables_opening", "receivables_closing"]].sum()
    ar_dec24 = wc_co.loc["2024-12", "receivables_closing"]
    ar_dec25 = wc_co.loc["2025-12", "receivables_closing"]

    nordics = pnl[pnl["bu"] == "Nordics"]
    mat24 = fy(nordics, "2024")["material_cost"].sum()
    mat25 = fy(nordics, "2025")["material_cost"].sum()

    baltics = pnl[pnl["bu"] == "Baltics & Poland"]
    baltics_disc_fy24 = fy(baltics, "2024")["promo_discounts"].sum() / fy(baltics, "2024")["gross_revenue"].sum() * 100
    baltics_dec25 = baltics[baltics["month"] == "2025-12"]
    baltics_disc_dec25 = baltics_dec25["promo_discounts"].sum() / baltics_dec25["gross_revenue"].sum() * 100

    ce_wc = wc[wc["bu"] == "Central Europe"].set_index("month")
    rhein = recv[recv["customer"] == "Rheinkauf Gruppe"].set_index("month")

    values = {
        "company_net_revenue_fy24": nr24,
        "company_net_revenue_fy25": nr25,
        "company_revenue_growth_pct": (nr25 / nr24 - 1) * 100,
        "gm_pct_fy24": gp24 / nr24 * 100,
        "gm_pct_fy25": gp25 / nr25 * 100,
        "ebitda_reported_fy24": ebitda_rep24,
        "ebitda_reported_fy25": ebitda_rep25,
        "ebitda_underlying_fy24": ebitda_und24,
        "ebitda_underlying_fy25": ebitda_und25,
        "company_ar_dec2024": ar_dec24,
        "company_ar_dec2025": ar_dec25,
        "company_ar_build_2025": ar_dec25 - ar_dec24,
        "nordics_material_yoy_pct": (mat25 / mat24 - 1) * 100,
        "baltics_discount_fy24_pct": baltics_disc_fy24,
        "baltics_discount_dec2025_pct": baltics_disc_dec25,
        "ce_ar_dec24": ce_wc.loc["2024-12", "receivables_closing"],
        "ce_ar_dec25": ce_wc.loc["2025-12", "receivables_closing"],
        "rheinkauf_ar_dec24": rhein.loc["2024-12", "receivables_closing"],
        "rheinkauf_ar_dec25": rhein.loc["2025-12", "receivables_closing"],
    }
    return values


_VERDICT_RANK = {"agree": 0, "disagree": 1, "not-checkable": 2}  # best-first, for aggregating across evidence items


def evaluate_finding_figures(f: dict, public_figures: dict) -> list:
    """For one finding, for every fixed figure, scan EACH evidence item separately
    (not the finding's evidence pooled together, and not the finding's headline/
    claimed_cause either) for a context match, and -- only within that same item --
    extract euro/pct tokens from its 'figures' text and compare to tolerance.
    Scoping this tightly matters: an earlier version of this function pooled every
    evidence item's text together, so a mention of "EBITDA" in one evidence item
    caused UNRELATED numbers from a different evidence item (e.g. a receivables
    figure) on the same finding to be checked against the EBITDA target. Folding
    the finding's headline/claimed_cause into every item's context had the same
    failure mode one level up -- a one-line summary that mentions several BUs
    ("Central Europe +EUR 2.81m, Baltics +EUR 1.16m...") gave every evidence item
    on that finding a false "Central Europe" context hit, regardless of which
    item's numbers actually related to Central Europe. So context AND numbers are
    both scoped to a single evidence item's own table/what/figures text, nothing
    broader -- narrower than the evaluation rules' letter, deliberately, to avoid manufacturing
    disagreements the finding never actually asserted. Returns one row per figure
    that had a context hit in at least one evidence item (figures never mentioned
    in any item are not reported at all, by design: they were never 'scanned', as
    distinct from 'not-checkable' below). Where multiple evidence items match the
    same figure, the best result wins (agree > disagree > not-checkable)."""
    evidence = [e for e in (f.get("evidence") or []) if isinstance(e, dict)]

    results = {}  # fig_id -> (verdict, note)
    for fig_id, rule in FIGURE_CONTEXT_RULES.items():
        unit = FIGURE_UNITS[fig_id]
        target = public_figures[fig_id]
        tol = TOL_PCT_DEFAULT if unit == "pct" else TOL_EUR_DEFAULT

        for e in evidence:
            item_context = " ".join([e.get("table") or "", e.get("what") or "", e.get("figures") or ""]).lower()
            if not context_hit(item_context, rule):
                continue
            number_text = e.get("figures") or ""
            tokens = extract_pct_tokens(number_text) if unit == "pct" else extract_eur_tokens(number_text)
            if not tokens:
                verdict = "not-checkable"
                note = "context matched but no extractable figure of this type in this evidence item's 'figures' text"
            elif any(abs(t - target) <= tol for t in tokens):
                verdict = "agree"
                closest = min(tokens, key=lambda t: abs(t - target))
                note = f"cited value {closest:,.2f} vs recomputed {target:,.2f} (unit={unit})"
            else:
                verdict = "disagree"
                closest = min(tokens, key=lambda t: abs(t - target))
                note = (
                    f"closest cited value {closest:,.2f} vs recomputed {target:,.2f} (unit={unit}) -- "
                    f"outside +/-{tol:g} tolerance; the evidence item matched on topic (e.g. it is "
                    f"clearly about company gross margin, or about Central Europe receivables) but the "
                    f"nearest number in it may be a different point-in-time snapshot, a bridge/variance "
                    f"component, or a different entity within the same topic, rather than a wrong figure "
                    f"-- adjudicate against the evidence text"
                )
            if fig_id not in results or _VERDICT_RANK[verdict] < _VERDICT_RANK[results[fig_id][0]]:
                results[fig_id] = (verdict, note)

    return [
        {"figure_id": fig_id, "label": FIGURE_LABELS[fig_id], "verdict": v, "note": n}
        for fig_id, (v, n) in results.items()
    ]


# =============================================================================
# Worksheet + scores assembly
# =============================================================================

def md_table(headers: list, rows: list) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(lines)


def eval_run(run_id: str, findings, load_error, answer_key: pd.DataFrame, public_figures: dict) -> dict:
    """Runs every mechanical check (A-E) for one run. Returns a dict the worksheet
    and scores builders both consume, so the two outputs never drift apart."""
    out = {"run_id": run_id, "load_error": load_error, "findings": findings or []}
    if load_error:
        return out

    out["schema_violations"], out["cluster_coverage"] = validate_schema(findings)
    out["clusters"] = evaluate_clusters(findings)

    s1_row = answer_key[answer_key["story_id"] == "S1"].iloc[0]
    s3_row = answer_key[answer_key["story_id"] == "S3"].iloc[0]
    s3_accounts = parse_semicolon_list(s3_row["affected_customers"])

    out["s1"] = detect_s1(findings)
    out["s2"] = detect_s2(findings)
    out["s3"] = detect_s3(findings, s3_accounts)
    out["s3_accounts"] = s3_accounts
    out["s4"] = detect_s4(findings)

    noise_rows = {row["story_id"]: row for _, row in answer_key[answer_key["type"] == "noise"].iterrows()}
    noise_ref_lists = []
    out["noise_refs"] = {}
    for nid in ("N1", "N2", "N3"):
        row = noise_rows[nid]
        refs = noise_references(findings, row["affected_bus"], row["months"])
        noise_ref_lists.append(refs)
        out["noise_refs"][nid] = {
            "bu": row["affected_bus"], "month": row["months"],
            "refs": [(f.get("finding_id"), classify_noise_ref(f)) for f in refs],
        }
    out["n4"] = n4_noted(findings)

    matched_ids = compute_matched_ids(findings, out["s1"], out["s2"], out["s3"], out["s4"], noise_ref_lists, out["n4"])
    out["unmatched"] = unmatched_findings(findings, matched_ids)

    out["figures"] = {f.get("finding_id"): evaluate_finding_figures(f, public_figures) for f in findings}

    return out


def build_scores_rows(run_result: dict) -> list:
    run_id = run_result["run_id"]
    rows = []
    if run_result["load_error"]:
        rows.append([run_id, "load", "-", "FATAL", run_result["load_error"]])
        return rows

    for v in run_result["schema_violations"]:
        rows.append([run_id, "schema", "-", "VIOLATION", v])
    if not run_result["schema_violations"]:
        rows.append([run_id, "schema", "-", "OK", "no schema violations found"])

    for c in range(1, 7):
        info = run_result["clusters"][c]
        rows.append([run_id, "cluster", f"C{c}", info["outcome"], "; ".join(str(x) for x in info.get("finding_ids", []))])
    rows.append([run_id, "cluster_subflag", "C4/N4 budget-optimism noted", run_result["clusters"][4]["n4_sub_flag"]["noted"], "; ".join(run_result["clusters"][4]["n4_sub_flag"]["finding_ids"])])
    rows.append([run_id, "cluster_subflag", "C5/Rheinkauf named", run_result["clusters"][5]["rheinkauf_sub_flag"], ""])
    rows.append([run_id, "cluster_subflag", "C6/mask linkage", run_result["clusters"][6]["mask_sub_flag"]["present"], "; ".join(run_result["clusters"][6]["mask_sub_flag"]["finding_ids"])])

    rows.append([run_id, "story", "S1", "detected" if run_result["s1"]["detected"] else "not detected", "; ".join(run_result["s1"]["finding_ids"])])
    rows.append([run_id, "story_subflag", "S1 cause-correct-candidate (unit cost flat asserted anywhere)", run_result["s1"]["cause_correct_candidate"], ""])
    rows.append([run_id, "story", "S2", "detected" if run_result["s2"]["detected"] else "not detected", "; ".join(run_result["s2"]["finding_ids"])])
    rows.append([run_id, "story_subflag", "S2 terms/DSO drift language", run_result["s2"]["terms_dso_language"], ""])
    rows.append([run_id, "story_subflag", "S2 receivable-build figures", run_result["s2"]["receivable_build_figures"], ""])
    rows.append([run_id, "story_subflag", "S2 mask linkage", run_result["s2"]["mask_linkage"], ""])
    rows.append([run_id, "story", "S3", "detected" if run_result["s3"]["detected"] else "not detected", "; ".join(run_result["s3"]["finding_ids"])])
    rows.append([run_id, "story_subflag", "S3 concentrated-account names evidenced", run_result["s3"]["account_names_evidenced"], "; ".join(run_result["s3_accounts"])])
    rows.append([run_id, "story_subflag", "S3 elasticity/fading language", run_result["s3"]["elasticity_language"], ""])
    rows.append([run_id, "story", "S4", "passed" if run_result["s4"]["passed"] else "not passed", "; ".join(run_result["s4"]["finding_ids"])])

    for nid, info in run_result["noise_refs"].items():
        if info["refs"]:
            for fid, cls in info["refs"]:
                rows.append([run_id, "noise", nid, f"referenced ({cls})", fid])
        else:
            rows.append([run_id, "noise", nid, "not referenced", ""])
    rows.append([run_id, "noise", "N4", "noted" if run_result["n4"]["noted"] else "not noted", "; ".join(run_result["n4"]["finding_ids"])])

    for f in run_result["unmatched"]:
        rows.append([run_id, "unmatched", f.get("finding_id"), "adjudicate: potential false positive OR unmatched composite", f.get("headline", "")])

    for fid, figs in run_result["figures"].items():
        for fig in figs:
            rows.append([run_id, "figure", f"{fid}/{fig['figure_id']}", fig["verdict"], fig["note"]])

    return rows


def build_worksheet(run_results: list, answer_key: pd.DataFrame, public_figures: dict) -> str:
    lines = []
    lines.append("# Case Study 5 -- Storyteller Evaluation Worksheet")
    lines.append("")
    lines.append(
        "**This worksheet is a MECHANICAL pass only.** It is produced by "
        "`code/evaluate.py` from schema checks, keyword/structural pattern matching, "
        "and CSV-derived arithmetic against the storyteller agents' findings JSON -- "
        "it does not read prose for meaning and does not hand down a final verdict. "
        "Every ambiguous case is listed explicitly below for a human adjudicator, "
        "rather than silently scored. The one-line scorecard for the case study goes "
        "into `data/analysis/report.md`, written separately by hand after "
        "reading this worksheet end to end."
    )
    lines.append("")
    lines.append(
        "This script reads `data/answer_key/stories.csv` (evaluation-side, by design "
        "-- see the module docstring); the storyteller agents themselves never see "
        "it, per the storyteller briefing's hard rule."
    )
    lines.append("")

    # --- Answer key summary -------------------------------------------------
    lines.append("## Answer key (ground truth)")
    lines.append("")
    ak_rows = [[r["story_id"], r["type"], r["name"], r["months"]] for _, r in answer_key.iterrows()]
    lines.append(md_table(["ID", "Type", "Name", "Months"], ak_rows))
    lines.append("")

    # --- Fixed public figures ------------------------------------------------
    lines.append("## Section E -- fixed company-level figures, recomputed from the public CSVs")
    lines.append("")
    lines.append(
        f"Recomputed fresh from `pnl_monthly.csv`, `opex_monthly.csv`, "
        f"`working_capital_monthly.csv`, `receivables_by_customer_monthly.csv` on every "
        f"run of this script -- never hardcoded. Tolerance: +/-{TOL_EUR_DEFAULT:,.0f} EUR "
        f"for euro figures, +/-{TOL_PCT_DEFAULT:g}pp for percentages."
    )
    lines.append("")
    fig_rows = []
    for fig_id, label in FIGURE_LABELS.items():
        unit = FIGURE_UNITS[fig_id]
        v = public_figures[fig_id]
        vtxt = f"{v:,.2f}%" if unit == "pct" else f"EUR {v:,.2f}"
        fig_rows.append([fig_id, label, vtxt])
    lines.append(md_table(["figure_id", "Label", "Recomputed value"], fig_rows))
    lines.append("")
    lines.append(
        "**On the figure-verification matching below**: string matching against free-text "
        "evidence is approximate, not parsing. Context and numbers are both scoped to a single "
        "evidence item at a time (never pooled across a finding's other evidence items, and never "
        "pulled from the headline/claimed_cause) -- a figure is only evaluated against a finding "
        "when a context keyword (documented in `FIGURE_CONTEXT_RULES` in the code) is present in "
        "that SAME evidence item's table/what/figures text; unmatched/uncontext'd numbers are never "
        "scored. `not-checkable` means the context matched but no number of the right type could be "
        "extracted from that evidence item's `figures` text. `disagree` means a number of the right "
        "type was extracted but none is within tolerance -- this can mean the finding is simply "
        "wrong, but it can also mean the evidence item is clearly on-topic (e.g. company gross "
        "margin) while the nearest number in it is a different point-in-time snapshot, a bridge/"
        "variance component, or a different entity within that same topic -- always check the "
        "underlying evidence text before treating a disagreement as an error."
    )
    lines.append("")

    # --- Matching rules, verbatim --------------------------------------------
    lines.append("## Matching rules (verbatim, for audit)")
    lines.append("")
    lines.append("### B. Cluster verdicts")
    lines.append("")
    lines.append(md_table(
        ["Cluster", "Designed verdict / test", "Design reference"],
        [
            ["C1", "stand_down (S4, the trap)", "S4"],
            ["C2", "two-part test: (i) unit-material-cost flat/stable/below-budget asserted; "
                   "(ii) some finding attributes Nordics margin movement to discount/promo/mix/trade-down. "
                   "Both -> correct (possibly distributed). Only (i) -> half: false-trail identified, cause "
                   "not delivered. Commodity/input-price inflation blamed -> wrong cause.", "S1"],
            ["C3", "worry (on the economics); split verdicts accepted", "S3"],
            ["C4", "worry; sub-flag N4 (structural budget optimism) noted, not dramatised", "expected-findings matrix, N4"],
            ["C5", "worry; sub-flag Rheinkauf named", "S2"],
            ["C6", "stand_down; sub-flag masking/flattering linkage to the underlying picture", "S2"],
        ],
    ))
    lines.append("")
    lines.append("### C. Story detection matrix -- rules as implemented (documented for audit, not just this code)")
    lines.append("")
    lines.append("- **S1 detected**: any finding with Nordics in `affected.bus` AND text matching "
                  "`(mix|trade.down|promo|discount)` AND (`Home Care`/`Skin & Body` in `affected.lines` "
                  "OR in text). **cause-correct-candidate** if unit-cost-flat language is also asserted "
                  "anywhere in the run (any finding).")
    lines.append("- **S2 detected**: `Rheinkauf` anywhere in the run's findings (text or `affected.customers`). "
                  "Components (each independently flagged, not gating detection): terms/DSO drift language; "
                  "receivable-build figures; mask linkage (shared with the C6 sub-flag).")
    lines.append("- **S3 detected**: Baltics & Poland in `affected.bus` AND `(discount|bought)` language. "
                  "Evidence sub-flags, checked anywhere in the run: (a) any of the answer key's three S3 "
                  "concentrated account names (read from `stories.csv`, not hardcoded); (b) elasticity/"
                  "fading-response language (`elastic|fade|weaker response|diminishing`).")
    lines.append("- **S4 passed**: a cluster-1 finding with `verdict == stand_down` AND YoY or vs-budget "
                  "evidence cited in that same finding's text.")
    lines.append("- **N1/N2/N3 references**: findings whose `affected.months` range overlaps the noise "
                  "event's month AND whose `affected.bus` contains the event's BU (or `Company`). Classified "
                  "`noted` (severity info/watch) vs `dramatised` (severity act) -- **both are listed below for "
                  "adjudication**, since severity alone is an imperfect proxy for tone.")
    lines.append("- **N4**: budget-optimism language anywhere in the run (`optimis(m|tic)|planning bias|"
                  "budget runs hot|budget set high|pre-dates`) -- reused as the C4 sub-flag.")
    lines.append("")
    lines.append("### D. Unmatched findings")
    lines.append("")
    lines.append("Any finding with `severity` in `{watch, act}` that is not cluster-tagged (1-6) and does not "
                  "satisfy any S1/S2/S3/S4 detection rule or N1-N4 reference above is listed as an unmatched "
                  "finding below -- **not auto-scored as a false positive**, since it may equally be a genuine, "
                  "correctly-restrained extra finding the matcher's keyword rules simply don't recognise.")
    lines.append("")

    # --- Per-run sections ------------------------------------------------------
    for r in run_results:
        run_id = r["run_id"]
        lines.append(f"## Run: {run_id}")
        lines.append("")
        if r["load_error"]:
            lines.append(f"**FATAL -- could not load this run's findings file: {r['load_error']}**")
            lines.append("")
            continue

        findings = r["findings"]
        lines.append(f"{len(findings)} findings loaded.")
        lines.append("")

        # A. Schema
        lines.append("### A. Schema validation")
        lines.append("")
        if r["schema_violations"]:
            lines.append(f"{len(r['schema_violations'])} violation(s):")
            lines.append("")
            for v in r["schema_violations"]:
                lines.append(f"- {v}")
        else:
            lines.append("No schema violations. Every cluster 1-6 carries at least one finding with an explicit verdict.")
        lines.append("")
        lines.append("Cluster coverage (# findings with an explicit verdict, by cluster): " +
                      ", ".join(f"C{c}={n}" for c, n in r["cluster_coverage"].items()))
        lines.append("")

        # B. Cluster verdicts
        lines.append("### B. Cluster verdicts vs designed expectations")
        lines.append("")
        c_rows = []
        for c in range(1, 7):
            info = r["clusters"][c]
            c_rows.append([f"C{c}", info["outcome"], ", ".join(str(x) for x in info.get("finding_ids", [])) or "-"])
        lines.append(md_table(["Cluster", "Outcome", "Finding IDs"], c_rows))
        lines.append("")
        lines.append(f"- C2 sub-tests: part (i) unit-cost-flat asserted = **{r['clusters'][2].get('part_i')}**; "
                      f"part (ii) Nordics cause attributed to discount/promo/mix = **{r['clusters'][2].get('part_ii')}**; "
                      f"commodity/input-cost blamed in a C2 finding = **{r['clusters'][2].get('wrong_cause')}**")
        lines.append(f"- C4 sub-flag, N4 budget-optimism noted: **{r['clusters'][4]['n4_sub_flag']['noted']}** "
                      f"({', '.join(r['clusters'][4]['n4_sub_flag']['finding_ids']) or '-'})")
        lines.append(f"- C5 sub-flag, Rheinkauf named: **{r['clusters'][5]['rheinkauf_sub_flag']}**")
        lines.append(f"- C6 sub-flag, mask/flatter/underlying linkage present in the run: "
                      f"**{r['clusters'][6]['mask_sub_flag']['present']}** "
                      f"({', '.join(r['clusters'][6]['mask_sub_flag']['finding_ids']) or '-'})")
        lines.append("")

        # C. Story detection matrix
        lines.append("### C. Story detection matrix")
        lines.append("")
        s_rows = [
            ["S1", "detected" if r["s1"]["detected"] else "MISSED", ", ".join(r["s1"]["finding_ids"]) or "-",
             f"cause-correct-candidate={r['s1']['cause_correct_candidate']}"],
            ["S2", "detected" if r["s2"]["detected"] else "MISSED", ", ".join(r["s2"]["finding_ids"]) or "-",
             f"terms/DSO={r['s2']['terms_dso_language']}, receivable-build={r['s2']['receivable_build_figures']}, mask-linkage={r['s2']['mask_linkage']}"],
            ["S3", "detected" if r["s3"]["detected"] else "MISSED", ", ".join(r["s3"]["finding_ids"]) or "-",
             f"accounts-named={r['s3']['account_names_evidenced']}, elasticity={r['s3']['elasticity_language']}"],
            ["S4", "passed" if r["s4"]["passed"] else "FAILED/adjudicate", ", ".join(r["s4"]["finding_ids"]) or "-",
             f"C1 stand_down findings: {', '.join(r['s4']['stand_down_finding_ids']) or 'none'}"],
        ]
        lines.append(md_table(["Story", "Result", "Finding IDs", "Components"], s_rows))
        lines.append("")

        # Noise references
        lines.append("### Noise-ledger references (listed for adjudication either way)")
        lines.append("")
        n_rows = []
        for nid, info in r["noise_refs"].items():
            if info["refs"]:
                for fid, cls in info["refs"]:
                    n_rows.append([nid, f"{info['bu']} / {info['month']}", fid, cls])
            else:
                n_rows.append([nid, f"{info['bu']} / {info['month']}", "-", "not referenced"])
        n_rows.append(["N4", "structural, all months/BUs", ", ".join(r["n4"]["finding_ids"]) or "-",
                       "noted" if r["n4"]["noted"] else "not noted"])
        lines.append(md_table(["Noise ID", "BU / month", "Finding ID", "Classification"], n_rows))
        lines.append("")

        # D. Unmatched
        lines.append("### D. Unmatched findings (severity watch/act, matching no story/noise rule)")
        lines.append("")
        if r["unmatched"]:
            for f in r["unmatched"]:
                lines.append(f"- **{f.get('finding_id')}** [{f.get('severity')}] adjudicate: potential false "
                              f"positive OR unmatched composite -- \"{f.get('headline','')}\"")
        else:
            lines.append("None -- every watch/act finding in this run matches a cluster, story, or noise-ledger rule.")
        lines.append("")

        # E. Figure verification
        lines.append("### E. Figure verification")
        lines.append("")
        agree_n = disagree_n = notcheck_n = 0
        disagreements = []
        fig_rows = []
        for f in findings:
            fid = f.get("finding_id")
            for fig in r["figures"].get(fid, []):
                fig_rows.append([fid, fig["figure_id"], fig["verdict"], fig["note"]])
                if fig["verdict"] == "agree":
                    agree_n += 1
                elif fig["verdict"] == "disagree":
                    disagree_n += 1
                    disagreements.append((fid, fig))
                else:
                    notcheck_n += 1
        lines.append(f"{agree_n} agree, {disagree_n} disagree, {notcheck_n} not-checkable, across "
                      f"{len(fig_rows)} finding x figure pairs where a context keyword matched "
                      f"(of {len(FIGURE_LABELS)} tracked figures x {len(findings)} findings possible).")
        lines.append("")
        if disagreements:
            lines.append("**Disagreements (check these first):**")
            lines.append("")
            for fid, fig in disagreements:
                lines.append(f"- {fid} / {fig['figure_id']} ({fig['label']}): {fig['note']}")
            lines.append("")
        if fig_rows:
            lines.append("<details><summary>Full finding x figure table</summary>")
            lines.append("")
            lines.append(md_table(["Finding", "Figure", "Verdict", "Note"], fig_rows))
            lines.append("")
            lines.append("</details>")
        else:
            lines.append("No finding in this run matched the context keywords for any tracked figure.")
        lines.append("")

        # F. Per-run summary
        lines.append("### F. Per-run summary")
        lines.append("")
        n_total = len(findings)
        n_worry = sum(1 for f in findings if f.get("verdict") == "worry")
        n_stand = sum(1 for f in findings if f.get("verdict") == "stand_down")
        sev_counts = {s: sum(1 for f in findings if f.get("severity") == s) for s in ("info", "watch", "act")}
        n_null_cluster = sum(1 for f in findings if f.get("cluster") is None)
        lines.append(md_table(
            ["Metric", "Value"],
            [
                ["Total findings", n_total],
                ["worry / stand_down", f"{n_worry} / {n_stand}"],
                ["severity info / watch / act", f"{sev_counts['info']} / {sev_counts['watch']} / {sev_counts['act']}"],
                ["Findings beyond the six clusters (cluster=null)", n_null_cluster],
                ["Schema violations", len(r["schema_violations"])],
                ["Unmatched watch/act findings", len(r["unmatched"])],
            ],
        ))
        lines.append("")

    # --- Cross-run comparison ------------------------------------------------
    lines.append("## Cross-run comparison")
    lines.append("")
    ok_runs = [r for r in run_results if not r["load_error"]]
    if ok_runs:
        header = ["Item"] + [r["run_id"] for r in ok_runs]
        rows = []
        for c in range(1, 7):
            rows.append([f"C{c} verdict"] + [ok_runs[i]["clusters"][c]["outcome"] for i in range(len(ok_runs))])
        rows.append(["S1 detected"] + ["yes" if r["s1"]["detected"] else "no" for r in ok_runs])
        rows.append(["S1 cause-correct-candidate"] + ["yes" if r["s1"]["cause_correct_candidate"] else "no" for r in ok_runs])
        rows.append(["S2 detected (Rheinkauf named)"] + ["yes" if r["s2"]["detected"] else "no" for r in ok_runs])
        rows.append(["S2 mask linkage"] + ["yes" if r["s2"]["mask_linkage"] else "no" for r in ok_runs])
        rows.append(["S3 detected"] + ["yes" if r["s3"]["detected"] else "no" for r in ok_runs])
        rows.append(["S3 accounts named"] + ["yes" if r["s3"]["account_names_evidenced"] else "no" for r in ok_runs])
        rows.append(["S3 elasticity language"] + ["yes" if r["s3"]["elasticity_language"] else "no" for r in ok_runs])
        rows.append(["S4 passed"] + ["yes" if r["s4"]["passed"] else "no" for r in ok_runs])
        for nid in ("N1", "N2", "N3"):
            rows.append([f"{nid} referenced"] + [
                ("+".join(cls for _, cls in r["noise_refs"][nid]["refs"]) or "no") for r in ok_runs
            ])
        rows.append(["N4 noted"] + ["yes" if r["n4"]["noted"] else "no" for r in ok_runs])
        rows.append(["Unmatched watch/act findings"] + [str(len(r["unmatched"])) for r in ok_runs])
        rows.append(["Schema violations"] + [str(len(r["schema_violations"])) for r in ok_runs])
        lines.append(md_table(header, rows))
    else:
        lines.append("No runs loaded successfully.")
    lines.append("")

    return "\n".join(lines)


# =============================================================================
# Main
# =============================================================================

def main():
    print("=" * 70, flush=True)
    print("evaluate.py -- Case Study 5 mechanical evaluation layer", flush=True)
    print("=" * 70, flush=True)

    print("Loading answer key...", flush=True)
    answer_key = load_answer_key()
    print(f"  {len(answer_key)} rows (stories + noise events)", flush=True)

    print("Loading public data tables for figure verification...", flush=True)
    tables = load_public_tables()
    for name, df in tables.items():
        print(f"  {name}: {len(df)} rows", flush=True)

    print("Recomputing fixed company-level figures from the public CSVs...", flush=True)
    public_figures = compute_public_figures(tables)
    for fig_id, v in public_figures.items():
        unit = FIGURE_UNITS[fig_id]
        print(f"  {fig_id}: {v:,.2f}{'%' if unit == 'pct' else ' EUR'}", flush=True)

    print(f"Globbing run_*_findings.json under {AGENT_RUNS_DIR} ...", flush=True)
    runs = load_runs()
    if not runs:
        print("No run_*_findings.json files found -- nothing to evaluate.", flush=True)
        sys.exit(0)
    print(f"  {len(runs)} run(s) found: {sorted(runs.keys())}", flush=True)

    run_results = []
    for run_id in sorted(runs.keys()):
        findings, load_error = runs[run_id]
        print(f"Evaluating {run_id} ({'FAILED TO LOAD: ' + load_error if load_error else str(len(findings)) + ' findings'})...", flush=True)
        run_results.append(eval_run(run_id, findings, load_error, answer_key, public_figures))

    print("Building worksheet...", flush=True)
    worksheet_text = build_worksheet(run_results, answer_key, public_figures)

    print("Building scores table...", flush=True)
    scores_rows = []
    for r in run_results:
        scores_rows.extend(build_scores_rows(r))
    scores_df = pd.DataFrame(scores_rows, columns=["run", "section", "item", "result", "detail"])

    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    worksheet_path = ANALYSIS_DIR / "evaluation_worksheet.md"
    scores_path = ANALYSIS_DIR / "evaluation_scores.csv"

    worksheet_path.write_text(worksheet_text, encoding="utf-8")
    print(f"Wrote {worksheet_path} ({len(worksheet_text.splitlines())} lines)", flush=True)

    scores_df.to_csv(scores_path, index=False, encoding="utf-8")
    print(f"Wrote {scores_path} ({len(scores_df)} rows)", flush=True)

    print("=" * 70, flush=True)
    print("Done. This is a mechanical worksheet -- read it end to end before writing report.md.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"evaluate.py failed: {exc}", file=sys.stderr, flush=True)
        raise
