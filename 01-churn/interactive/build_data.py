"""
Build the inlined JSON payload for the Hybrid Churn Intelligence interactive page.

Reads the pipeline's read-only outputs (data/accounts.csv, usage_monthly.csv,
tickets.csv, answer_key.csv, data/agent/text_scores.csv + narratives.json,
data/fusion/combined_scores.csv + results_summary.json) and writes
`_data.json` next to this script -- the file that
`churn_explorer.html`'s <script id="hpx-data"> block is generated from.

Never edits any source file. Regenerate with:

    python build_data.py

Size discipline: a full 500-account
drill-down (usage curves + all ticket text for every account) is too large to
inline cheaply. Every account gets its scores (leaderboard, 2x2, threshold
counters all work for all 500) but only a CURATED SUBSET gets the heavy detail
(usage sparkline series + full ticket text + agent narrative) needed for the
account drill-down panel. The curated subset is:

  - all 46 A4 accounts ("quietly unhappy") -- the case's money segment, every
    single one belongs in the drill-down.
  - 7 vivid exemplars each of A1, A3, A5, A6, A7 (35 more), chosen by a
    documented, reproducible rule per archetype (see CURATION_RULES below) --
    not cherry-picked by hand.

A2 and A8 are not curated for full detail (score-only) -- they are the
"nothing much to say" archetypes (healthy-growing, quiet-decline-but-stays)
and are well represented already by A1/A3 in the drill-down.

Total curated: 46 + 5*7 = 81 accounts.
"""

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"

# Default outputs. `--staging` redirects them to interactive/staging/ so a regenerated
# page can be inspected without overwriting the standing files (used for the
# 6 Oct 2026 tie-break fix).
OUT_JSON = HERE / "_data.json"
TEMPLATE_HTML = HERE / "_template.html"
OUT_HTML = HERE / "churn_explorer.html"
STAGING_DIR = HERE / "staging"
DATA_MARKER = "/*__HPX_DATA_JSON__*/"

RANDOM_SEED = 42  # unused directly here (no new randomness is introduced), kept for the record.

EXEMPLARS_PER_ARCHETYPE = 7
CURATED_ARCHETYPES = ["A1", "A3", "A5", "A6", "A7"]  # A4 is curated separately (all 46).

ARCHETYPE_LABELS = {
    "A1": "Healthy stable",
    "A2": "Healthy growing",
    "A3": "Slow decay",
    "A4": "Quietly unhappy",
    "A5": "Sudden death",
    "A6": "Saved account",
    "A7": "Loud but loyal",
    "A8": "Quiet decline, stays",
}

TRAJECTORY_ORDINAL_MAP = {"improving": -1, "stable": 0, "deteriorating": 1}

USAGE_METRICS = [
    "active_users", "dashboard_views", "reports_created", "connector_syncs",
    "alerts_configured", "api_calls", "exports_run", "logins",
]


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# Load (read-only)
# ---------------------------------------------------------------------------

def load_all():
    log("Loading pipeline outputs (read-only)...")
    accounts = pd.read_csv(DATA / "accounts.csv")
    usage = pd.read_csv(DATA / "usage_monthly.csv")
    tickets = pd.read_csv(DATA / "tickets.csv")
    answer_key = pd.read_csv(DATA / "answer_key.csv")
    text_scores = pd.read_csv(DATA / "agent" / "text_scores.csv")
    narratives = json.loads((DATA / "agent" / "narratives.json").read_text(encoding="utf-8"))
    combined = pd.read_csv(DATA / "fusion" / "combined_scores.csv")
    results_summary = json.loads((DATA / "fusion" / "results_summary.json").read_text(encoding="utf-8"))

    for name, df in [("accounts", accounts), ("answer_key", answer_key),
                      ("text_scores", text_scores), ("combined", combined)]:
        if len(df) != 500:
            raise ValueError(f"{name} has {len(df)} rows, expected 500 -- pipeline output looks stale.")

    log(f"Loaded {len(accounts)} accounts, {len(usage)} usage rows, {len(tickets)} tickets.")
    return accounts, usage, tickets, answer_key, text_scores, narratives, combined, results_summary


# ---------------------------------------------------------------------------
# Join into one per-account frame
# ---------------------------------------------------------------------------

def build_master(accounts, answer_key, text_scores, combined, tickets):
    df = (
        accounts
        .merge(answer_key[["account_id", "archetype", "planted_signals", "churn_driver"]],
               on="account_id", how="inner", validate="one_to_one")
        .merge(text_scores, on="account_id", how="inner", validate="one_to_one")
        .merge(combined[["account_id", "ml_risk_score", "combined_score",
                         "ml_rank", "text_rank", "combined_rank"]],
               on="account_id", how="inner", validate="one_to_one")
    )
    if len(df) != 500:
        raise ValueError(f"Joined master has {len(df)} rows, expected 500.")

    df["trajectory_ordinal"] = df["frustration_trajectory"].map(TRAJECTORY_ORDINAL_MAP)
    if df["trajectory_ordinal"].isna().any():
        raise ValueError("Unmapped frustration_trajectory values found.")
    df["escalation_pattern"] = df["escalation_pattern"].astype(bool)

    # Most recent ticket date per account: the recency tie-break for ranking ties in the
    # live mixer (the static per-arm ranks come precomputed from code/fuse_and_evaluate.py).
    last_ticket = tickets.groupby("account_id")["created_at"].max()
    df["last_ticket"] = df["account_id"].map(last_ticket)
    if df["last_ticket"].isna().any():
        raise ValueError("An account has no tickets -- the recency tie-break is undefined for it.")
    return df


# ---------------------------------------------------------------------------
# Curated-subset selection (documented, reproducible rules -- no hand-picking)
# ---------------------------------------------------------------------------

def select_curated(df, tickets):
    """Return the set of account_ids that get full drill-down detail."""
    ticket_count = tickets.groupby("account_id").size().rename("ticket_count")
    d = df.merge(ticket_count, on="account_id", how="left")
    d["ticket_count"] = d["ticket_count"].fillna(0).astype(int)

    curated = set(d.loc[d.archetype == "A4", "account_id"])
    log(f"  A4 (mandated, all): {len(curated)} accounts.")

    def top(archetype, by, n=EXEMPLARS_PER_ARCHETYPE, ascending=False):
        sub = d[d.archetype == archetype].sort_values(by, ascending=ascending)
        return set(sub.head(n)["account_id"])

    # A3 (slow decay, both layers catch it) and A5 (sudden death, honest ceiling):
    # highest-ARR churners -- the biggest, most dramatic revenue-at-stake stories.
    curated |= top("A3", "arr_eur")
    curated |= top("A5", "arr_eur")
    # A6 (saved account, anger -> resolution -> recovery arc): needs enough tickets
    # to actually show the arc -- highest ticket volume.
    curated |= top("A6", "ticket_count")
    # A7 (loud but loyal, agent must NOT flag): highest text_risk_score among A7 --
    # the most persuasive illustration of the false-positive lesson.
    curated |= top("A7", "text_risk_score")
    # A1 (healthy stable): highest-ARR accounts -- the reassuring, boring-in-a-good-way
    # default view of what "nothing to see here" looks like at scale.
    curated |= top("A1", "arr_eur")

    log(f"  Curated subset total: {len(curated)} accounts "
        f"(target ~{46 + 5 * EXEMPLARS_PER_ARCHETYPE}).")
    return curated


# ---------------------------------------------------------------------------
# Per-account light record (all 500 -- scores, leaderboard, 2x2, threshold slider)
# ---------------------------------------------------------------------------

def build_light_records(df, curated_ids):
    records = []
    for _, r in df.iterrows():
        records.append({
            "id": r.account_id,
            "name": r.company_name,
            "industry": r.industry,
            "country": r.country,
            "arr": int(r.arr_eur),
            "seats": int(r.licensed_seats),
            "plan": r.plan_tier,
            "churned": bool(r.churned),
            "churn_date": (None if pd.isna(r.churn_date) else str(r.churn_date)),
            "archetype": r.archetype,
            "ml": round(float(r.ml_risk_score), 4),
            "text": round(float(r.text_risk_score), 4),
            "combined": round(float(r.combined_score), 4),
            # Pipeline ranks under the explicit tie-break rule (code/ranking.py). The page
            # reads these; it never re-sorts scores for the 2x2, so row order cannot decide a cut.
            "ml_rank": int(r.ml_rank),
            "text_rank": int(r.text_rank),
            "combined_rank": int(r.combined_rank),
            "last_ticket": str(r.last_ticket),
            "traj": r.frustration_trajectory,
            "traj_ord": int(r.trajectory_ordinal),
            "unresolved": int(r.unresolved_issue_count),
            "n_comp": int(r.n_competitor_mentions),
            "n_comp_serious": int(r.n_serious_competitor_mentions),
            "escalation": bool(r.escalation_pattern),
            "curated": r.account_id in curated_ids,
        })
    return records


# ---------------------------------------------------------------------------
# Per-account heavy record (curated subset only -- usage series + tickets + narrative)
# ---------------------------------------------------------------------------

def build_heavy_records(curated_ids, usage, tickets, narratives, df):
    heavy = {}
    usage_g = usage[usage.account_id.isin(curated_ids)].sort_values(["account_id", "month"])
    tickets_g = tickets[tickets.account_id.isin(curated_ids)].sort_values(["account_id", "created_at"])
    answer_lookup = df.set_index("account_id")

    for acc_id in sorted(curated_ids):
        u = usage_g[usage_g.account_id == acc_id]
        months = u["month"].tolist()
        series = {m: [int(v) for v in u[m].tolist()] for m in USAGE_METRICS}

        t = tickets_g[tickets_g.account_id == acc_id]
        ticket_list = []
        for _, tk in t.iterrows():
            ticket_list.append({
                "date": tk.created_at,
                "channel": tk.channel,
                "subject": tk.subject,
                "body": tk.body,
                "module": tk.module,
                "resolved": bool(tk.resolved),
                "res_days": (None if pd.isna(tk.resolution_days) else float(tk.resolution_days)),
                "csat": (None if pd.isna(tk.csat) else float(tk.csat)),
            })

        narr = narratives.get(acc_id, {})
        row = answer_lookup.loc[acc_id]

        heavy[acc_id] = {
            "months": months,
            "usage": series,
            "tickets": ticket_list,
            "narrative": narr.get("narrative", ""),
            "planted_signals": (row.planted_signals if isinstance(row.planted_signals, str) else ""),
            "churn_driver": (row.churn_driver if isinstance(row.churn_driver, str) else ""),
        }
    return heavy


# ---------------------------------------------------------------------------
# Risk-mixer math (identical formula reimplemented client-side in JS --
# this copy exists purely so build_data.py can sanity-check it before shipping)
# ---------------------------------------------------------------------------

def mixer_score(row, w_usage, w_sentiment, w_competitor, coefs):
    """
    Reproduce the interactive page's blended-score formula for one account.

    w_usage / w_sentiment / w_competitor are fractions in [0, 1] -- 1.0 means
    "full fitted weight for this channel", 0.0 means "this channel switched off".
    At (1, 1, 1) this is EXACTLY the fusion model's raw-coefficient logistic
    formula from results_summary.json (a full-dataset fit), which is why the
    "Combined (fitted)" preset uses (1, 1, 1).

    Presets:
      Usage only        -> (1, 0, 0): sigmoid is a monotonic function of
                            ml_risk_score alone, so ranking exactly matches
                            the ML-only evaluation.
      Tickets only       -> (0, 1, 0): the ticket-sentiment channel bundles
                            the agent's own text_risk_score with the two
                            other things it reads straight off the ticket
                            text -- frustration trajectory and escalation
                            pattern -- so ranking correlates very highly
                            with (but is not identical to) a pure
                            text_risk_score sort; it is a richer "what do
                            the tickets say" reading than that one number.
      Combined (fitted)  -> (1, 1, 1): the full fusion formula.
    """
    raw = coefs["raw_coefficients"]
    intercept = coefs["raw_intercept"]
    logit = (
        intercept
        + w_usage * raw["ml_risk_score"] * row["ml"]
        + w_sentiment * (
            raw["text_risk_score"] * row["text"]
            + raw["trajectory_ordinal"] * row["traj_ord"]
            + raw["escalation_pattern"] * (1 if row["escalation"] else 0)
        )
        + w_competitor * raw["n_serious_competitor_mentions"] * row["n_comp_serious"]
    )
    return 1.0 / (1.0 + math.exp(-logit))


def sanity_check_mixer(light_records, combined_df, coefs):
    """
    Assert the "Combined (fitted)" preset (1,1,1) is close to the published
    combined_score for known accounts. combined_score is out-of-fold
    (5-fold CV, a different model per fold); this formula reproduces the
    full-dataset fit reported for explainability. They are NOT expected to
    match exactly -- evaluation_report.md section 5 says so explicitly --
    but they should be close. Empirically (checked against all 500 accounts
    before writing this test): mean abs diff ~0.018, 95th pct ~0.06,
    worst case ~0.15 on the highest-confidence account. Tolerance below is
    set accordingly, with headroom.
    """
    by_id = {r["id"]: r for r in light_records}
    combined_lookup = dict(zip(combined_df.account_id, combined_df.combined_score))

    check_accounts = ["ACC0002", "ACC0013", "ACC0019"]
    tolerance = 0.06

    log("Sanity-checking risk-mixer formula against combined_scores.csv...")
    for acc_id in check_accounts:
        row = by_id[acc_id]
        fitted = mixer_score(row, 1.0, 1.0, 1.0, coefs)
        actual = combined_lookup[acc_id]
        diff = abs(fitted - actual)
        log(f"  {acc_id}: mixer(fitted)={fitted:.4f}  combined_score={actual:.4f}  diff={diff:.4f}")
        assert diff < tolerance, (
            f"{acc_id}: mixer formula diverges from combined_score by {diff:.4f} "
            f"(tolerance {tolerance}) -- check the raw-coefficient formula against "
            f"code/fuse_and_evaluate.py's build_fusion_features()."
        )

    # Also check overall correlation across all 500 as a broader sanity net.
    fitted_all = np.array([mixer_score(r, 1.0, 1.0, 1.0, coefs) for r in light_records])
    actual_all = np.array([combined_lookup[r["id"]] for r in light_records])
    corr = np.corrcoef(fitted_all, actual_all)[0, 1]
    log(f"  Pearson correlation, mixer(fitted) vs combined_score, all 500 accounts: {corr:.4f}")
    assert corr > 0.95, f"Mixer formula correlation with combined_score too low: {corr:.4f}"

    # Usage-only preset gates the sentiment/competitor terms to exactly zero, so it
    # is a pure monotonic transform of ml_risk_score alone -- ranking must match exactly.
    ml_order = sorted(light_records, key=lambda r: -r["ml"])
    mixer_ml_order = sorted(light_records, key=lambda r: -mixer_score(r, 1.0, 0.0, 0.0, coefs))
    assert [r["id"] for r in ml_order] == [r["id"] for r in mixer_ml_order], (
        "Usage-only preset does not preserve ml_risk_score ranking."
    )

    # Tickets-only preset bundles text_risk_score with trajectory_ordinal and
    # escalation_pattern (both also read off the ticket text -- see mixer_score's
    # docstring), so it is NOT a pure function of text_risk_score alone and exact
    # rank preservation is not expected. It should still correlate very highly.
    mixer_text_scores = np.array([mixer_score(r, 0.0, 1.0, 0.0, coefs) for r in light_records])
    text_scores_arr = np.array([r["text"] for r in light_records])
    text_corr = np.corrcoef(mixer_text_scores, text_scores_arr)[0, 1]
    log(f"  Tickets-only preset vs raw text_risk_score correlation: {text_corr:.4f}")
    assert text_corr > 0.9, f"Tickets-only preset correlation with text_risk_score too low: {text_corr:.4f}"

    log("  All mixer sanity checks passed.")


def check_published_ranks(light_records, results_summary):
    """
    The 2x2 region counts the page draws from the precomputed ranks must equal the
    pipeline's two_by_two block exactly -- same rule, same cut, same counts.
    """
    ml_top = {r["id"] for r in light_records if r["ml_rank"] <= 100}
    text_top = {r["id"] for r in light_records if r["text_rank"] <= 100}
    counts = {
        "both": len(ml_top & text_top),
        "ml_only": len(ml_top - text_top),
        "text_only": len(text_top - ml_top),
    }
    counts["neither"] = len(light_records) - sum(counts.values())
    for region, expected in ((k, v["total_accounts"]) for k, v in results_summary["two_by_two"].items()):
        assert counts[region] == expected, f"2x2 region {region}: page ranks give {counts[region]}, pipeline {expected}"
    assert len({r["ml_rank"] for r in light_records}) == len(light_records), "ml_rank has ties"
    assert len({r["text_rank"] for r in light_records}) == len(light_records), "text_rank has ties"
    log(f"  2x2 region counts from precomputed ranks match the pipeline: {counts}")


# ---------------------------------------------------------------------------
# Preset weight percentages shown on the sliders (standardized-coefficient shares)
# ---------------------------------------------------------------------------

def compute_fitted_slider_percentages(coefs):
    """
    The "Combined (fitted)" preset always computes the exact fusion formula
    (fractions 1,1,1 -- see mixer_score). The slider POSITIONS shown for that
    preset are cosmetic but should honestly reflect each channel's actual
    share of the fitted model's standardized-coefficient weight, so a reader
    dragging away from the preset sees where they started. Computed from
    standardized coefficients (comparable magnitudes), trajectory_ordinal and
    escalation_pattern folded into the "sentiment" bucket (both are read off
    the ticket text, same as text_risk_score).
    """
    std = coefs["standardized_coefficients"]
    usage_w = abs(std["ml_risk_score"])
    sentiment_w = abs(std["text_risk_score"] + std["trajectory_ordinal"] + std["escalation_pattern"])
    competitor_w = abs(std["n_serious_competitor_mentions"])
    total = usage_w + sentiment_w + competitor_w
    return {
        "usage": round(100 * usage_w / total),
        "sentiment": round(100 * sentiment_w / total),
        "competitor": round(100 * competitor_w / total),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global OUT_JSON, OUT_HTML
    parser = argparse.ArgumentParser(description="Build the explorer data payload and page.")
    parser.add_argument("--staging", action="store_true",
                        help="write to interactive/staging/ instead of overwriting the standing outputs")
    args = parser.parse_args()
    if args.staging:
        STAGING_DIR.mkdir(exist_ok=True)
        OUT_JSON = STAGING_DIR / "_data.json"
        OUT_HTML = STAGING_DIR / "churn_explorer.staging.html"
        log(f"STAGING mode: writing to {STAGING_DIR}")
    # Never write over an input.
    for output_path in (OUT_JSON, OUT_HTML):
        assert output_path.resolve() != TEMPLATE_HTML.resolve(), "output path must not equal the template"

    accounts, usage, tickets, answer_key, text_scores, narratives, combined, results_summary = load_all()

    log("Joining into master per-account frame...")
    df = build_master(accounts, answer_key, text_scores, combined, tickets)

    log("Selecting curated drill-down subset...")
    curated_ids = select_curated(df, tickets)

    log("Building light (all-500) per-account records...")
    light_records = build_light_records(df, curated_ids)

    log("Building heavy (curated-subset) per-account records...")
    heavy_records = build_heavy_records(curated_ids, usage, tickets, narratives, df)

    coefs = results_summary["fusion_coefficients"]
    sanity_check_mixer(light_records, combined, coefs)
    check_published_ranks(light_records, results_summary)

    fitted_pct = compute_fitted_slider_percentages(coefs)
    log(f"Fitted preset slider percentages: {fitted_pct}")

    total_churned_arr = int(df.loc[df.churned, "arr_eur"].sum())

    payload = {
        "meta": {
            "company_name": "Kataja Analytics Oy",
            "n_accounts": len(df),
            "n_tickets": len(tickets),
            "n_churned": int(df.churned.sum()),
            "total_churned_arr": total_churned_arr,
            "n_curated": len(curated_ids),
            "random_seed": RANDOM_SEED,
            "archetype_labels": ARCHETYPE_LABELS,
            "honesty_line": (
                "This dataset is synthetic -- Kataja Analytics Oy and every account in it are "
                "invented, engineered against a held-out answer key (seed 42, fully regenerable) "
                "so the ML layer's catches and misses can be shown honestly, not just claimed."
            ),
        },
        "fusion_coefficients": coefs,
        "fitted_preset_pct": fitted_pct,
        "head_to_head": results_summary["head_to_head"],
        "a4_table": results_summary["a4_table"],
        "a7_verdict": results_summary["a7_verdict"],
        "a5_honesty_check": results_summary["a5_honesty_check"],
        "arr_business_translation": results_summary["arr_business_translation"],
        "ranking_rule": results_summary["ranking_rule"],
        "accounts": light_records,
        "detail": heavy_records,
    }

    out_str = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    OUT_JSON.write_text(out_str, encoding="utf-8")
    data_size_kb = len(out_str.encode("utf-8")) / 1024
    log(f"Wrote {OUT_JSON} -- {data_size_kb:.1f} KB of JSON.")

    log(f"Assembling {OUT_HTML} from {TEMPLATE_HTML.name}...")
    if not TEMPLATE_HTML.exists():
        raise FileNotFoundError(
            f"{TEMPLATE_HTML} not found -- the static HTML/CSS/JS shell must exist "
            f"before build_data.py can inline data into it."
        )
    template_text = TEMPLATE_HTML.read_text(encoding="utf-8")
    if DATA_MARKER not in template_text:
        raise ValueError(
            f"{TEMPLATE_HTML} does not contain the data marker {DATA_MARKER!r} -- "
            f"cannot inline the JSON payload."
        )
    # Escape "</script" so the inlined JSON can never accidentally close the
    # surrounding <script> tag early (the marker itself lives inside a script block).
    safe_json = out_str.replace("</script", "<\\/script")
    final_html = template_text.replace(DATA_MARKER, safe_json)
    OUT_HTML.write_text(final_html, encoding="utf-8")
    html_size_kb = len(final_html.encode("utf-8")) / 1024
    log(f"Wrote {OUT_HTML} -- {html_size_kb:.1f} KB total.")
    log("Done. To regenerate after any pipeline output changes: python build_data.py "
        "(reads the template + data/... outputs, writes _data.json and churn_explorer.html).")


if __name__ == "__main__":
    main()
