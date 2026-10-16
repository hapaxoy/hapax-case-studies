"""
fuse_and_evaluate.py -- Fusion + evaluation stage of the Hybrid Churn Intelligence
case study.

Background: data/model/ml_report.md (the A4 story:
A4 is NOT fully invisible to the classical model -- mean ml_risk_score 0.477,
50% top-100 share, a residual ticket-volume leak. This is documented and
expected, not a bug this script fixes.)

What this script does:
    1. Fuses ml_risk_score + text_risk_score (+ agent-derived features) into
       a single logistic regression "combined_score", produced out-of-fold
       (5-fold StratifiedKFold) so every account is scored by a fold that
       never trained on it -- same discipline as ml_scores.csv.
    2. Head-to-head evaluation of ML-only vs text-only vs combined against
       the true churned label: AUC, average precision, recall@50, recall@100.
    3. Per-archetype top-100 share for each approach.
    4. The 2x2 centrepiece (ml_flag x text_flag) with archetype breakdown,
       and the "A7 verdict" (A7 must never be flagged -- how much does the
       agent layer pollute its own top-100 with A7, and does fusion rescue it?).
    5. The A4 table (the money segment -- how much does text/fusion lift
       A4 recall over ML alone?).
    6. ARR-weighted business translation, including a top-50 "review budget"
       framing.
    7. Segmentation of the combined top-100 into "worth-saving" vs
       "low-leverage".

answer_key.csv is used for evaluation ONLY -- it is never a model input.

Run from the project root:
    python code/fuse_and_evaluate.py

Outputs (data/fusion/ only -- distinct from data/model/, data/agent/, data/):
    data/fusion/combined_scores.csv     (account_id, ml_risk_score, text_risk_score, combined_score)
    data/fusion/evaluation_report.md    (full human-readable report)
    data/fusion/results_summary.json    (machine-readable bundle for the interactive HTML page)
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler

# Explicit, deterministic tie-break for every ranked cut (see code/ranking.py).
import ranking

# ---------------------------------------------------------------------------
# Resolve paths
# ---------------------------------------------------------------------------

SCRIPT_DIR   = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR     = PROJECT_ROOT / "data"

ML_SCORES_PATH   = DATA_DIR / "model" / "ml_scores.csv"
TEXT_SCORES_PATH = DATA_DIR / "agent" / "text_scores.csv"
ACCOUNTS_PATH    = DATA_DIR / "accounts.csv"
ANSWER_KEY_PATH  = DATA_DIR / "answer_key.csv"          # evaluation ONLY -- never a model input
TICKETS_PATH     = DATA_DIR / "tickets.csv"             # read ONLY for each account's most recent ticket date (rank tie-break)

FUSION_DIR = DATA_DIR / "fusion"
FUSION_DIR.mkdir(parents=True, exist_ok=True)

COMBINED_SCORES_PATH   = FUSION_DIR / "combined_scores.csv"
EVALUATION_REPORT_PATH = FUSION_DIR / "evaluation_report.md"
RESULTS_SUMMARY_PATH   = FUSION_DIR / "results_summary.json"

INPUT_PATHS = [ML_SCORES_PATH, TEXT_SCORES_PATH, ACCOUNTS_PATH, ANSWER_KEY_PATH, TICKETS_PATH]
OUTPUT_PATHS = [COMBINED_SCORES_PATH, EVALUATION_REPORT_PATH, RESULTS_SUMMARY_PATH]

# Confirm output paths never collide with input paths -- non-negotiable safety rule.
for out_path in OUTPUT_PATHS:
    for in_path in INPUT_PATHS:
        assert out_path.resolve() != in_path.resolve(), (
            f"Refusing to run: output path {out_path} collides with input path {in_path}"
        )
assert FUSION_DIR.resolve() != DATA_DIR.resolve(), "Output dir must not be the data root"
assert FUSION_DIR.resolve() != (DATA_DIR / "model").resolve(), "Output dir must not be data/model"
assert FUSION_DIR.resolve() != (DATA_DIR / "agent").resolve(), "Output dir must not be data/agent"

# ---------------------------------------------------------------------------
# Config block
# ---------------------------------------------------------------------------

RANDOM_SEED  = 42
N_CV_FOLDS   = 5
TOP_K_LARGE  = 100   # "top-100" used throughout the head-to-head, 2x2, A4 table
TOP_K_SMALL  = 50    # "review budget" framing -- a smaller, more realistic CS review queue

# Known archetype totals from answer_key.csv (used for validation).
EXPECTED_ARCHETYPE_COUNTS = {
    "A1": 176, "A2": 46, "A3": 57, "A4": 46,
    "A5": 30, "A6": 52, "A7": 55, "A8": 38,
}

# Trajectory -> ordinal mapping for the fusion model's feature set.
TRAJECTORY_ORDINAL_MAP = {"improving": -1, "stable": 0, "deteriorating": 1}

FLOAT_ROUND = 4   # decimal places for scores/metrics in the JSON bundle


def log(message):
    """Print a progress message. Centralised so encoding is handled consistently on Windows."""
    print(message, flush=True)


# ---------------------------------------------------------------------------
# Step 0: load and join all inputs
# ---------------------------------------------------------------------------

def load_inputs():
    """Load the four read-only input files and join them on account_id."""
    log("Loading input files (read-only)...")

    try:
        ml_scores = pd.read_csv(ML_SCORES_PATH)
        text_scores = pd.read_csv(TEXT_SCORES_PATH)
        accounts = pd.read_csv(ACCOUNTS_PATH)
        answer_key = pd.read_csv(ANSWER_KEY_PATH)
    except FileNotFoundError as error:
        raise FileNotFoundError(
            f"Could not find an expected input file. Check that generate_structured.py, "
            f"train_models.py and the agent-scoring step have all been run first. Detail: {error}"
        )

    for name, df in [("ml_scores", ml_scores), ("text_scores", text_scores),
                      ("accounts", accounts), ("answer_key", answer_key)]:
        if len(df) != 500:
            raise ValueError(f"{name} has {len(df)} rows, expected exactly 500.")

    # Join everything on account_id. Inner join so a mismatch in account_id sets
    # surfaces as a row-count drop rather than silent NaNs.
    merged = (
        accounts
        .merge(ml_scores, on="account_id", how="inner", validate="one_to_one")
        .merge(text_scores, on="account_id", how="inner", validate="one_to_one")
        .merge(answer_key, on="account_id", how="inner", validate="one_to_one")
    )

    if len(merged) != 500:
        raise ValueError(
            f"Joined dataset has {len(merged)} rows, expected 500 -- account_id sets "
            f"across the four input files do not match exactly."
        )

    log(f"Loaded and joined {len(merged)} accounts across accounts/ml_scores/text_scores/answer_key.")
    # Most recent ticket date per account: the recency tie-break for the text and
    # combined arms (see code/ranking.py). Tickets are text-layer data, so this
    # keeps the text arm independent of the usage arm.
    tickets = pd.read_csv(TICKETS_PATH, usecols=["account_id", "created_at"])
    last_ticket_dates = ranking.last_ticket_date_by_account(tickets)
    merged["last_ticket_date"] = merged["account_id"].map(last_ticket_dates)
    if merged["last_ticket_date"].isna().any():
        n_undated = int(merged["last_ticket_date"].isna().sum())
        log(f"  Note: {n_undated} account(s) have no tickets and sort last at equal score.")

    return merged


# ---------------------------------------------------------------------------
# Step 1: fusion logistic regression
# ---------------------------------------------------------------------------

def build_fusion_features(df):
    """Build the feature matrix for the fusion model from the joined dataframe."""
    features = pd.DataFrame({
        "ml_risk_score": df["ml_risk_score"].astype(float),
        "text_risk_score": df["text_risk_score"].astype(float),
        "trajectory_ordinal": df["frustration_trajectory"].map(TRAJECTORY_ORDINAL_MAP).astype(float),
        "n_serious_competitor_mentions": df["n_serious_competitor_mentions"].astype(float),
        "escalation_pattern": df["escalation_pattern"].astype(int).astype(float),
    })

    if features["trajectory_ordinal"].isna().any():
        bad_values = df.loc[features["trajectory_ordinal"].isna(), "frustration_trajectory"].unique()
        raise ValueError(
            f"frustration_trajectory contains values outside "
            f"{list(TRAJECTORY_ORDINAL_MAP.keys())}: {bad_values}"
        )

    return features


def run_fusion_model(df):
    """
    Fit the fusion logistic regression two ways:
      (a) out-of-fold via 5-fold StratifiedKFold -- produces combined_score for
          all 500 accounts, each scored by a fold that never trained on it.
      (b) once on the full dataset (standardized features) -- purely to report
          final coefficients + intercept for the explainability writeup.
    """
    log("Building fusion feature matrix (ml_risk_score, text_risk_score, "
        "trajectory_ordinal, n_serious_competitor_mentions, escalation_pattern)...")
    features = build_fusion_features(df)
    target = df["churned"].astype(int).values

    # --- (a) out-of-fold combined_score for all 500 accounts ---
    log(f"Running {N_CV_FOLDS}-fold StratifiedKFold out-of-fold scoring (seed {RANDOM_SEED})...")
    combined_score = np.full(len(df), np.nan)
    skf = StratifiedKFold(n_splits=N_CV_FOLDS, shuffle=True, random_state=RANDOM_SEED)

    for fold_index, (train_idx, test_idx) in enumerate(skf.split(features, target), start=1):
        scaler = StandardScaler()
        X_train = scaler.fit_transform(features.iloc[train_idx])
        X_test = scaler.transform(features.iloc[test_idx])

        model = LogisticRegression(random_state=RANDOM_SEED, max_iter=1000)
        model.fit(X_train, target[train_idx])
        combined_score[test_idx] = model.predict_proba(X_test)[:, 1]
        log(f"  Fold {fold_index}/{N_CV_FOLDS}: trained on {len(train_idx)}, scored {len(test_idx)} held-out accounts.")

    if np.isnan(combined_score).any():
        raise ValueError("Out-of-fold scoring left NaN combined_score values -- a fold assignment bug.")

    # --- (b) full-dataset fit, purely for reporting coefficients ---
    log("Fitting fusion model once on the full dataset for coefficient reporting...")
    scaler_full = StandardScaler()
    X_full_raw = features.values
    X_full_scaled = scaler_full.fit_transform(X_full_raw)

    model_raw = LogisticRegression(random_state=RANDOM_SEED, max_iter=1000)
    model_raw.fit(X_full_raw, target)

    model_standardized = LogisticRegression(random_state=RANDOM_SEED, max_iter=1000)
    model_standardized.fit(X_full_scaled, target)

    feature_names = list(features.columns)
    coefficients = {
        "feature_names": feature_names,
        "raw_coefficients": {name: float(c) for name, c in zip(feature_names, model_raw.coef_[0])},
        "raw_intercept": float(model_raw.intercept_[0]),
        "standardized_coefficients": {name: float(c) for name, c in zip(feature_names, model_standardized.coef_[0])},
        "standardized_intercept": float(model_standardized.intercept_[0]),
    }

    log("Fusion model fitting complete.")
    return combined_score, coefficients


# ---------------------------------------------------------------------------
# Step 2: head-to-head evaluation
# ---------------------------------------------------------------------------

# Which tie-break arm each score column belongs to (see code/ranking.py).
ARM_BY_SCORE_COLUMN = {
    "ml_risk_score": ranking.ARM_USAGE,
    "text_risk_score": ranking.ARM_TEXT,
    "combined_score": ranking.ARM_COMBINED,
}


def top_k_flags(df, score_column, k):
    """
    Boolean array flagging the top-k accounts by score_column, cut by the explicit rule
    in code/ranking.py (score desc, then most recent ticket date desc for the text and
    combined arms, then account_id asc). Not by row order: the text arm's score has
    only 33 distinct values, so its top-100 cut falls inside a tie.
    """
    return ranking.top_k_flags_ranked(
        df["account_id"].values, df[score_column].values, k,
        last_ticket_dates=df["last_ticket_date"].values,
        arm=ARM_BY_SCORE_COLUMN[score_column],
    )


def recall_at_k(y_true, df, score_column, k):
    """Fraction of all true churners captured within the top-k accounts by score."""
    flags = top_k_flags(df, score_column, k)
    total_churners = int(np.sum(y_true))
    if total_churners == 0:
        return 0.0
    caught = int(np.sum(y_true[flags]))
    return caught / total_churners


def compute_head_to_head(df):
    """AUC, average precision, recall@50, recall@100 for ML-only, text-only, combined."""
    log("Computing head-to-head metrics (AUC, average precision, recall@50, recall@100)...")
    y_true = df["churned"].astype(int).values

    approaches = {
        "ml_only": "ml_risk_score",
        "text_only": "text_risk_score",
        "combined": "combined_score",
    }

    results = {}
    for name, score_column in approaches.items():
        scores = df[score_column].values
        results[name] = {
            "auc": round(float(roc_auc_score(y_true, scores)), FLOAT_ROUND),
            "average_precision": round(float(average_precision_score(y_true, scores)), FLOAT_ROUND),
            "recall_at_50": round(float(recall_at_k(y_true, df, score_column, TOP_K_SMALL)), FLOAT_ROUND),
            "recall_at_100": round(float(recall_at_k(y_true, df, score_column, TOP_K_LARGE)), FLOAT_ROUND),
        }
        log(f"  {name}: AUC={results[name]['auc']}, AP={results[name]['average_precision']}, "
            f"recall@50={results[name]['recall_at_50']}, recall@100={results[name]['recall_at_100']}")

    return results


def compute_per_archetype_top100_share(df):
    """For each approach, the share of each archetype's accounts landing in that approach's top-100."""
    log("Computing per-archetype top-100 share for each approach...")

    table = {}
    for archetype in sorted(EXPECTED_ARCHETYPE_COUNTS.keys()):
        subset = df[df["archetype"] == archetype]
        n_accounts = len(subset)
        table[archetype] = {
            "n_accounts": n_accounts,
            "ml_top100_share": round(float(subset["ml_flag"].sum() / n_accounts), FLOAT_ROUND) if n_accounts else 0.0,
            "text_top100_share": round(float(subset["text_flag"].sum() / n_accounts), FLOAT_ROUND) if n_accounts else 0.0,
            "combined_top100_share": round(float(subset["combined_flag"].sum() / n_accounts), FLOAT_ROUND) if n_accounts else 0.0,
        }

    return table


# ---------------------------------------------------------------------------
# Step 3: the 2x2 centrepiece + A7 verdict
# ---------------------------------------------------------------------------

def compute_two_by_two(df):
    """ml_flag x text_flag 2x2, with total/churner/archetype breakdown per cell."""
    log("Computing the 2x2 (ml_flag x text_flag) centrepiece...")

    cell_definitions = {
        "both":      (df["ml_flag"] == 1) & (df["text_flag"] == 1),
        "ml_only":   (df["ml_flag"] == 1) & (df["text_flag"] == 0),
        "text_only": (df["ml_flag"] == 0) & (df["text_flag"] == 1),
        "neither":   (df["ml_flag"] == 0) & (df["text_flag"] == 0),
    }

    two_by_two = {}
    for cell_name, mask in cell_definitions.items():
        subset = df[mask]
        archetype_counts = {
            archetype: int((subset["archetype"] == archetype).sum())
            for archetype in sorted(EXPECTED_ARCHETYPE_COUNTS.keys())
        }
        two_by_two[cell_name] = {
            "total_accounts": int(len(subset)),
            "true_churners": int(subset["churned"].sum()),
            "archetype_breakdown": archetype_counts,
        }
        log(f"  {cell_name}: {len(subset)} accounts, {int(subset['churned'].sum())} true churners.")

    return two_by_two


def compute_a7_verdict(df):
    """
    A7 ('loud but loyal') must never be flagged -- the agent must read resolution
    and arc, not tone alone. Quantify how much A7 pollutes the text top-100, and
    whether fusion rescues those accounts out of the combined top-100.
    """
    log("Computing the A7 verdict (does fusion rescue A7 accounts the text layer flags)...")

    a7 = df[df["archetype"] == "A7"]
    n_a7_total = len(a7)
    a7_in_text_top100 = a7[a7["text_flag"] == 1]
    n_a7_in_text_top100 = len(a7_in_text_top100)

    n_rescued = int((a7_in_text_top100["combined_flag"] == 0).sum())
    n_still_flagged = int((a7_in_text_top100["combined_flag"] == 1).sum())

    verdict = {
        "n_a7_total": int(n_a7_total),
        "n_a7_in_text_top100": int(n_a7_in_text_top100),
        "pct_a7_polluting_text_top100": round(n_a7_in_text_top100 / n_a7_total, FLOAT_ROUND) if n_a7_total else 0.0,
        "n_rescued_out_of_combined_top100": n_rescued,
        "n_still_flagged_in_combined_top100": n_still_flagged,
        "mean_text_risk_score_a7": round(float(a7["text_risk_score"].mean()), FLOAT_ROUND),
    }
    log(f"  A7: {n_a7_in_text_top100}/{n_a7_total} in text top-100; "
        f"of those, {n_rescued} rescued out of combined top-100, {n_still_flagged} still flagged.")

    return verdict


def compute_a5_honesty_check(df):
    """A5 ('sudden death') is designed to be undetectable by either layer. Report its
    presence in each top-100 as a low/near-baseline honesty check."""
    log("Computing the A5 honesty check (undetectable-by-design archetype)...")

    a5 = df[df["archetype"] == "A5"]
    n_a5_total = len(a5)
    check = {
        "n_a5_total": int(n_a5_total),
        "n_a5_in_ml_top100": int(a5["ml_flag"].sum()),
        "n_a5_in_text_top100": int(a5["text_flag"].sum()),
        "n_a5_in_combined_top100": int(a5["combined_flag"].sum()),
    }
    log(f"  A5 (undetectable by design): {check['n_a5_in_ml_top100']} in ML top-100, "
        f"{check['n_a5_in_text_top100']} in text top-100, {check['n_a5_in_combined_top100']} in combined top-100 "
        f"(of {n_a5_total} total).")
    return check


# ---------------------------------------------------------------------------
# Step 4: the A4 table
# ---------------------------------------------------------------------------

def compute_a4_table(df):
    """A4 ('quietly unhappy') is the money segment. How many appear in each top-100?"""
    log("Computing the A4 table (the money segment)...")

    a4 = df[df["archetype"] == "A4"]
    n_a4_total = len(a4)
    n_ml = int(a4["ml_flag"].sum())
    n_text = int(a4["text_flag"].sum())
    n_combined = int(a4["combined_flag"].sum())

    table = {
        "n_a4_total": int(n_a4_total),
        "n_in_ml_top100": n_ml,
        "n_in_text_top100": n_text,
        "n_in_combined_top100": n_combined,
        "headline_delta_text_minus_ml": n_text - n_ml,
        "headline_delta_combined_minus_ml": n_combined - n_ml,
    }
    log(f"  A4: {n_ml} in ML top-100, {n_text} in text top-100, {n_combined} in combined top-100 "
        f"(of {n_a4_total} total). Delta (text-ml)={table['headline_delta_text_minus_ml']}, "
        f"(combined-ml)={table['headline_delta_combined_minus_ml']}.")

    return table


# ---------------------------------------------------------------------------
# Step 5: ARR-weighted business translation
# ---------------------------------------------------------------------------

def compute_arr_translation(df):
    """ARR caught / incremental ARR at top-100, plus the top-50 'review budget' framing."""
    log("Computing ARR-weighted business translation...")

    churned = df[df["churned"] == True]
    total_churned_arr = float(churned["arr_eur"].sum())

    def arr_caught(flag_column):
        return float(df.loc[(df["churned"] == True) & (df[flag_column] == 1), "arr_eur"].sum())

    arr_caught_ml_top100 = arr_caught("ml_flag")
    arr_caught_text_top100 = arr_caught("text_flag")
    arr_caught_combined_top100 = arr_caught("combined_flag")

    # Incremental ARR: churned accounts caught by one approach's top-100 but not the other's.
    churned_mask = df["churned"] == True
    text_not_ml = churned_mask & (df["text_flag"] == 1) & (df["ml_flag"] == 0)
    ml_not_text = churned_mask & (df["ml_flag"] == 1) & (df["text_flag"] == 0)

    incremental_arr_text_unique = float(df.loc[text_not_ml, "arr_eur"].sum())
    incremental_arr_ml_unique = float(df.loc[ml_not_text, "arr_eur"].sum())

    # Top-50 "review budget" framing, repeated for all three approaches.
    y_true = df["churned"].astype(int).values
    review_budget = {}
    for approach_name, score_column in [("ml_only", "ml_risk_score"),
                                         ("text_only", "text_risk_score"),
                                         ("combined", "combined_score")]:
        flags_top50 = top_k_flags(df, score_column, TOP_K_SMALL)
        caught_mask = flags_top50 & (y_true == 1)
        review_budget[approach_name] = {
            "n_accounts_caught": int(caught_mask.sum()),
            "arr_caught": float(df.loc[caught_mask, "arr_eur"].sum()),
        }
        log(f"  Top-50 {approach_name}: {review_budget[approach_name]['n_accounts_caught']} churners caught, "
            f"EUR {review_budget[approach_name]['arr_caught']:,.0f} ARR.")

    translation = {
        "total_churned_arr": round(total_churned_arr),
        "arr_caught_top100": {
            "ml_only": round(arr_caught_ml_top100),
            "text_only": round(arr_caught_text_top100),
            "combined": round(arr_caught_combined_top100),
        },
        "incremental_arr_text_uniquely_surfaces": round(incremental_arr_text_unique),
        "incremental_arr_ml_uniquely_surfaces": round(incremental_arr_ml_unique),
        "review_budget_top50": {
            name: {"n_accounts_caught": v["n_accounts_caught"], "arr_caught": round(v["arr_caught"])}
            for name, v in review_budget.items()
        },
    }

    log(f"  Total churned ARR: EUR {total_churned_arr:,.0f}. "
        f"Top-100 caught -- ML: EUR {arr_caught_ml_top100:,.0f}, text: EUR {arr_caught_text_top100:,.0f}, "
        f"combined: EUR {arr_caught_combined_top100:,.0f}.")
    log(f"  Incremental ARR text uniquely surfaces (top-100): EUR {incremental_arr_text_unique:,.0f}. "
        f"Incremental ARR ML uniquely surfaces: EUR {incremental_arr_ml_unique:,.0f}.")

    return translation


# ---------------------------------------------------------------------------
# Step 6: segmentation of combined top-100
# ---------------------------------------------------------------------------

def compute_segmentation(df):
    """
    Segment the combined top-100 into "worth-saving" vs "low-leverage".
    Rule: worth-saving = ARR above the combined top-100's median ARR AND a
    fixable driver present (deteriorating trajectory OR any serious competitor
    mention). Everything else in the combined top-100 is low-leverage.
    """
    log("Segmenting the combined top-100 into worth-saving vs low-leverage...")

    combined_top100 = df[df["combined_flag"] == 1].copy()
    median_arr = float(combined_top100["arr_eur"].median())

    is_high_arr = combined_top100["arr_eur"] > median_arr
    has_fixable_driver = (
        (combined_top100["frustration_trajectory"] == "deteriorating")
        | (combined_top100["n_serious_competitor_mentions"] > 0)
    )
    is_worth_saving = is_high_arr & has_fixable_driver

    worth_saving = combined_top100[is_worth_saving]
    low_leverage = combined_top100[~is_worth_saving]

    segmentation = {
        "rule": (
            f"worth-saving = arr_eur above the combined top-100 median (EUR {median_arr:,.0f}) "
            f"AND (frustration_trajectory == 'deteriorating' OR n_serious_competitor_mentions > 0); "
            f"everything else in the combined top-100 is low-leverage."
        ),
        "median_arr_threshold": round(median_arr),
        "worth_saving": {
            "n_accounts": int(len(worth_saving)),
            "total_arr": round(float(worth_saving["arr_eur"].sum())),
        },
        "low_leverage": {
            "n_accounts": int(len(low_leverage)),
            "total_arr": round(float(low_leverage["arr_eur"].sum())),
        },
    }

    log(f"  Worth-saving: {segmentation['worth_saving']['n_accounts']} accounts, "
        f"EUR {segmentation['worth_saving']['total_arr']:,.0f} ARR.")
    log(f"  Low-leverage: {segmentation['low_leverage']['n_accounts']} accounts, "
        f"EUR {segmentation['low_leverage']['total_arr']:,.0f} ARR.")

    return segmentation


# ---------------------------------------------------------------------------
# Validation pass
# ---------------------------------------------------------------------------

def run_validation(df, two_by_two, arr_translation):
    """
    Every coherence rule this stage must satisfy. A failing check is a bug,
    not a warning to ignore -- raises on first failure after printing all results.
    """
    log("")
    log("=" * 70)
    log("VALIDATION PASS")
    log("=" * 70)

    checks = []

    # 1. All 500 accounts have a combined_score, no NaNs.
    n_missing = df["combined_score"].isna().sum()
    checks.append(("All 500 accounts have a non-NaN combined_score", n_missing == 0 and len(df) == 500))

    # 2. 2x2 cell counts sum to 500.
    two_by_two_total = sum(cell["total_accounts"] for cell in two_by_two.values())
    checks.append((f"2x2 cell counts sum to 500 (got {two_by_two_total})", two_by_two_total == 500))

    # 3. Per-archetype counts across the 2x2 sum to each archetype's known total.
    archetype_sums = {archetype: 0 for archetype in EXPECTED_ARCHETYPE_COUNTS}
    for cell in two_by_two.values():
        for archetype, count in cell["archetype_breakdown"].items():
            archetype_sums[archetype] += count
    archetype_check_passed = all(
        archetype_sums[archetype] == expected_count
        for archetype, expected_count in EXPECTED_ARCHETYPE_COUNTS.items()
    )
    checks.append((
        f"Per-archetype 2x2 counts match known totals ({archetype_sums} vs {EXPECTED_ARCHETYPE_COUNTS})",
        archetype_check_passed
    ))

    # 4. ARR figures are internally consistent (caught ARR <= total churned ARR).
    total_churned_arr = arr_translation["total_churned_arr"]
    arr_consistent = all(
        caught <= total_churned_arr
        for caught in arr_translation["arr_caught_top100"].values()
    )
    checks.append((
        f"ARR caught at top-100 never exceeds total churned ARR (EUR {total_churned_arr:,.0f})",
        arr_consistent
    ))

    # 5. combined_scores.csv account_ids exactly match accounts.csv account_ids.
    accounts_ids = set(pd.read_csv(ACCOUNTS_PATH)["account_id"])
    combined_ids = set(df["account_id"])
    checks.append((
        "combined_scores account_id set exactly matches accounts.csv account_id set",
        accounts_ids == combined_ids
    ))

    # 6. Every top-100 cut is exactly 100 accounts, and the cut is reproducible by rule:
    #    shuffling the row order must not change which accounts are flagged.
    rng = np.random.default_rng(RANDOM_SEED)
    shuffled = df.iloc[rng.permutation(len(df))].reset_index(drop=True)
    for score_column, flag_column in [("ml_risk_score", "ml_flag"), ("text_risk_score", "text_flag"),
                                      ("combined_score", "combined_flag")]:
        flagged_ids = set(df.loc[df[flag_column] == 1, "account_id"])
        shuffled_flags = top_k_flags(shuffled, score_column, TOP_K_LARGE)
        shuffled_ids = set(shuffled.loc[shuffled_flags, "account_id"])
        checks.append((
            f"{flag_column}: exactly {TOP_K_LARGE} accounts flagged, identical under a shuffled row order",
            len(flagged_ids) == TOP_K_LARGE and flagged_ids == shuffled_ids
        ))

    # Print every check's result, then raise if anything failed.
    all_passed = True
    for description, passed in checks:
        status = "PASS" if passed else "FAIL"
        log(f"  [{status}] {description}")
        if not passed:
            all_passed = False

    if not all_passed:
        raise AssertionError(
            "One or more validation checks FAILED. A failing check is a bug in this "
            "pipeline, not a judgment call -- fix the underlying issue before trusting "
            "any output in data/fusion/."
        )

    log("All validation checks PASSED.")
    log("=" * 70)


# ---------------------------------------------------------------------------
# Report writing
# ---------------------------------------------------------------------------

def format_markdown_table(headers, rows):
    """Build a simple markdown table from a header list and list of row lists."""
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def write_evaluation_report(head_to_head, per_archetype, two_by_two, a7_verdict, a5_check,
                            a4_table, coefficients, arr_translation, segmentation):
    """Write the full human-readable evaluation_report.md."""
    log("Writing evaluation_report.md...")

    lines = []
    lines.append("# Hybrid Churn Intelligence -- Fusion & Evaluation Report")
    lines.append("")
    lines.append(
        "Combines the classical ML risk score (`ml_risk_score`, out-of-fold, see "
        "`data/model/ml_report.md`) and the LLM agent's text risk score "
        "(`text_risk_score`, see `data/agent/`) into a single explainable fusion "
        "model, then evaluates all three approaches -- ML-only, text-only, combined "
        "-- against the held-out `answer_key.csv`. The answer key is evaluation-only "
        "and never touches model training."
    )
    lines.append("")

    # --- Head-to-head ---
    lines.append("## 1. Head-to-head evaluation")
    lines.append("")
    rows = []
    for name, label in [("ml_only", "ML-only"), ("text_only", "Text-only"), ("combined", "Combined")]:
        m = head_to_head[name]
        rows.append([label, m["auc"], m["average_precision"], m["recall_at_50"], m["recall_at_100"]])
    lines.append(format_markdown_table(
        ["Approach", "AUC", "Average precision", "Recall@50", "Recall@100"], rows
    ))
    lines.append("")

    # --- Per-archetype top-100 share ---
    lines.append("## 2. Per-archetype top-100 share")
    lines.append("")
    lines.append("Share of each archetype's accounts landing in that approach's top-100.")
    lines.append("")
    rows = []
    for archetype in sorted(EXPECTED_ARCHETYPE_COUNTS.keys()):
        row = per_archetype[archetype]
        rows.append([
            archetype, row["n_accounts"],
            f"{row['ml_top100_share']:.1%}",
            f"{row['text_top100_share']:.1%}",
            f"{row['combined_top100_share']:.1%}",
        ])
    lines.append(format_markdown_table(
        ["Archetype", "N accounts", "ML top-100 share", "Text top-100 share", "Combined top-100 share"], rows
    ))
    lines.append("")

    # --- 2x2 centrepiece ---
    lines.append("## 3. The 2x2 centrepiece")
    lines.append("")
    lines.append("`ml_flag` = 1 if in ML top-100 by `ml_risk_score`; `text_flag` = 1 if in text top-100 by `text_risk_score`.")
    lines.append("")
    lines.append(f"Every top-N cut uses an explicit tie-break rule (`code/ranking.py`): {ranking.RULE_TEXT}. "
                 "The text score has only 33 distinct values, so its top-100 cut falls inside a tie.")
    lines.append("")
    rows = []
    for cell_name, label in [("both", "Both (ml_flag=1, text_flag=1)"), ("ml_only", "ML only (1,0)"),
                              ("text_only", "Text only (0,1)"), ("neither", "Neither (0,0)")]:
        cell = two_by_two[cell_name]
        archetype_str = ", ".join(f"{a}={c}" for a, c in cell["archetype_breakdown"].items() if c > 0)
        rows.append([label, cell["total_accounts"], cell["true_churners"], archetype_str or "--"])
    lines.append(format_markdown_table(
        ["Cell", "Total accounts", "True churners", "Archetype breakdown"], rows
    ))
    lines.append("")

    # --- A7 verdict ---
    lines.append("### The A7 verdict")
    lines.append("")
    lines.append(
        f"A7 ('loud but loyal') is designed to NEVER churn and the agent must NOT flag it -- "
        f"angry tickets that always resolve fast are not a risk signal. Of the {a7_verdict['n_a7_total']} "
        f"A7 accounts (mean text_risk_score {a7_verdict['mean_text_risk_score_a7']:.3f}), "
        f"**{a7_verdict['n_a7_in_text_top100']} ({a7_verdict['pct_a7_polluting_text_top100']:.1%}) land in the "
        f"text top-100** -- the agent layer's honest false-positive rate on this archetype. "
        f"Of those, fusion rescues **{a7_verdict['n_rescued_out_of_combined_top100']}** out of the combined "
        f"top-100 (the ML signal and other fusion features outweigh the text score), while "
        f"**{a7_verdict['n_still_flagged_in_combined_top100']}** still remains flagged in the combined top-100."
        if a7_verdict['n_still_flagged_in_combined_top100'] == 1 else
        f"**{a7_verdict['n_still_flagged_in_combined_top100']}** remain flagged in the combined top-100."
    )
    lines.append("")

    # --- A5 honesty check ---
    lines.append("### The A5 honesty check")
    lines.append("")
    lines.append(
        f"A5 ('sudden death') is designed to be undetectable by either layer -- no usage decline, "
        f"no text signal, the churn driver is exogenous (acquisitions, budget cuts, champion leaves). "
        f"Of {a5_check['n_a5_total']} A5 accounts: **{a5_check['n_a5_in_ml_top100']}** in ML top-100, "
        f"**{a5_check['n_a5_in_text_top100']}** in text top-100, **{a5_check['n_a5_in_combined_top100']}** in "
        f"combined top-100. Low, near-baseline counts here are the expected, honest result -- not a failure "
        f"of either layer."
    )
    lines.append("")

    # --- A4 table ---
    lines.append("## 4. The A4 table (the money segment)")
    lines.append("")
    lines.append(
        f"A4 ('quietly unhappy') is designed to be near-invisible to the classical model and caught by "
        f"the agent reading ticket text. Of {a4_table['n_a4_total']} A4 accounts:"
    )
    lines.append("")
    lines.append(format_markdown_table(
        ["Approach", "N of 46 A4 accounts in top-100"],
        [
            ["ML top-100", a4_table["n_in_ml_top100"]],
            ["Text top-100", a4_table["n_in_text_top100"]],
            ["Combined top-100", a4_table["n_in_combined_top100"]],
        ]
    ))
    lines.append("")
    lines.append(
        f"**Headline delta: text top-100 vs ML top-100 = {a4_table['headline_delta_text_minus_ml']:+d} accounts. "
        f"Combined top-100 vs ML top-100 = {a4_table['headline_delta_combined_minus_ml']:+d} accounts.**"
    )
    lines.append("")

    # --- Fusion coefficients ---
    lines.append("## 5. Fusion model coefficients")
    lines.append("")
    lines.append(
        "Logistic regression fit once on the full 500-account dataset for explainability "
        "(the reported combined_score itself comes from out-of-fold predictions, not this full fit)."
    )
    lines.append("")
    rows = []
    for feature in coefficients["feature_names"]:
        rows.append([
            feature,
            round(coefficients["raw_coefficients"][feature], 4),
            round(coefficients["standardized_coefficients"][feature], 4),
        ])
    rows.append(["intercept", round(coefficients["raw_intercept"], 4), round(coefficients["standardized_intercept"], 4)])
    lines.append(format_markdown_table(["Feature", "Raw coefficient", "Standardized coefficient"], rows))
    lines.append("")
    lines.append(
        "Raw coefficients are on each feature's native scale (not comparable to each other). "
        "Standardized coefficients (features scaled to zero mean / unit variance before fitting) "
        "are comparable in magnitude -- the largest standardized coefficient is the strongest driver "
        "of the fusion model's risk score."
    )
    lines.append("")

    # --- ARR business translation ---
    lines.append("## 6. Business translation (ARR-weighted)")
    lines.append("")
    lines.append(f"Total ARR of all churned accounts: **EUR {arr_translation['total_churned_arr']:,.0f}**.")
    lines.append("")
    lines.append("### ARR caught at top-100")
    lines.append("")
    rows = [
        ["ML-only", f"EUR {arr_translation['arr_caught_top100']['ml_only']:,.0f}"],
        ["Text-only", f"EUR {arr_translation['arr_caught_top100']['text_only']:,.0f}"],
        ["Combined", f"EUR {arr_translation['arr_caught_top100']['combined']:,.0f}"],
    ]
    lines.append(format_markdown_table(["Approach", "ARR caught (churned accounts in top-100)"], rows))
    lines.append("")
    lines.append(
        f"**Incremental ARR text uniquely surfaces (churned, in text top-100 but not ML top-100): "
        f"EUR {arr_translation['incremental_arr_text_uniquely_surfaces']:,.0f}.**"
    )
    lines.append(
        f"Incremental ARR ML uniquely surfaces (churned, in ML top-100 but not text top-100): "
        f"EUR {arr_translation['incremental_arr_ml_uniquely_surfaces']:,.0f}."
    )
    lines.append("")
    lines.append("### Review budget framing (top-50 instead of top-100)")
    lines.append("")
    rows = []
    for name, label in [("ml_only", "ML-only"), ("text_only", "Text-only"), ("combined", "Combined")]:
        v = arr_translation["review_budget_top50"][name]
        rows.append([label, v["n_accounts_caught"], f"EUR {v['arr_caught']:,.0f}"])
    lines.append(format_markdown_table(["Approach", "Churners caught (top-50)", "ARR caught (top-50)"], rows))
    lines.append("")

    # --- Segmentation ---
    lines.append("## 7. Segmentation of the combined top-100")
    lines.append("")
    lines.append(f"**Rule:** {segmentation['rule']}")
    lines.append("")
    rows = [
        ["Worth-saving", segmentation["worth_saving"]["n_accounts"], f"EUR {segmentation['worth_saving']['total_arr']:,.0f}"],
        ["Low-leverage", segmentation["low_leverage"]["n_accounts"], f"EUR {segmentation['low_leverage']['total_arr']:,.0f}"],
    ]
    lines.append(format_markdown_table(["Segment", "N accounts", "Total ARR"], rows))
    lines.append("")

    EVALUATION_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    log(f"  Wrote {EVALUATION_REPORT_PATH}")


def write_results_summary(head_to_head, per_archetype, two_by_two, a7_verdict, a5_check,
                           a4_table, coefficients, arr_translation, segmentation):
    """Write the compact machine-readable results_summary.json for the interactive HTML page."""
    log("Writing results_summary.json...")

    summary = {
        "fusion_coefficients": coefficients,
        "head_to_head": head_to_head,
        "per_archetype_top100_share": per_archetype,
        "two_by_two": two_by_two,
        "a7_verdict": a7_verdict,
        "a5_honesty_check": a5_check,
        "a4_table": a4_table,
        "arr_business_translation": arr_translation,
        "segmentation": segmentation,
        "ranking_rule": ranking.RULE_TEXT,
    }

    with open(RESULTS_SUMMARY_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    log(f"  Wrote {RESULTS_SUMMARY_PATH}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    log("=" * 70)
    log("fuse_and_evaluate.py -- Hybrid Churn Intelligence fusion + evaluation")
    log("=" * 70)

    try:
        df = load_inputs()

        combined_score, coefficients = run_fusion_model(df)
        df["combined_score"] = combined_score

        # Write combined_scores.csv (account_id, ml_risk_score, text_risk_score, combined_score).
        combined_scores_output = df[["account_id", "ml_risk_score", "text_risk_score", "combined_score"]].copy()
        # Explicit 1-based ranks per arm under the tie-break rule (code/ranking.py), so
        # downstream consumers (the explorer) never re-sort scores and re-introduce
        # row-order tie-breaking.
        for score_column, rank_column in [("ml_risk_score", "ml_rank"),
                                           ("text_risk_score", "text_rank"),
                                           ("combined_score", "combined_rank")]:
            combined_scores_output[rank_column] = ranking.rank_numbers(
                df["account_id"].values, df[score_column].values,
                last_ticket_dates=df["last_ticket_date"].values,
                arm=ARM_BY_SCORE_COLUMN[score_column],
            )
        combined_scores_output["combined_score"] = combined_scores_output["combined_score"].round(FLOAT_ROUND)
        combined_scores_output.to_csv(COMBINED_SCORES_PATH, index=False)
        log(f"Wrote {COMBINED_SCORES_PATH} ({len(combined_scores_output)} rows).")

        # Compute top-100 flags once, reused throughout.
        df["ml_flag"] = top_k_flags(df, "ml_risk_score", TOP_K_LARGE).astype(int)
        df["text_flag"] = top_k_flags(df, "text_risk_score", TOP_K_LARGE).astype(int)
        df["combined_flag"] = top_k_flags(df, "combined_score", TOP_K_LARGE).astype(int)

        head_to_head = compute_head_to_head(df)
        per_archetype = compute_per_archetype_top100_share(df)
        two_by_two = compute_two_by_two(df)
        a7_verdict = compute_a7_verdict(df)
        a5_check = compute_a5_honesty_check(df)
        a4_table = compute_a4_table(df)
        arr_translation = compute_arr_translation(df)
        segmentation = compute_segmentation(df)

        run_validation(df, two_by_two, arr_translation)

        write_evaluation_report(
            head_to_head, per_archetype, two_by_two, a7_verdict, a5_check,
            a4_table, coefficients, arr_translation, segmentation
        )
        write_results_summary(
            head_to_head, per_archetype, two_by_two, a7_verdict, a5_check,
            a4_table, coefficients, arr_translation, segmentation
        )

        log("")
        log("Done. See data/fusion/evaluation_report.md and data/fusion/results_summary.json.")

    except Exception as error:
        log("")
        log(f"ERROR: {error}")
        raise


if __name__ == "__main__":
    main()
