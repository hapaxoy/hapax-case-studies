"""
build_interactive_data.py -- Prepares the compact JSON data payload for the
Case Study 5 interactive page ("the board pack that answers back").

Reads only public tables: data/*.csv and data/analysis/kpi_monthly.csv,
variances_monthly.csv, evaluation_worksheet.md. data/answer_key/ is never
opened, per the case's honesty framing -- the interactive page works
from the same nine public CSVs any reader has. Two figures (S2's cash
conversion, S3's fading volume response) need the data generator's driver
model rather than a public CSV, exactly as notebooks/board_reporting.ipynb
Section 6(b) documents; code/generate_financials.py is imported read-only
for those two figures only (no data is written, no answer key opened).

Every number here is either read directly from the deterministic analysis
outputs (kpi_monthly.csv, variances_monthly.csv) or recomputed from the
underlying public tables with the same formulas as code/variance_analysis.py
and the notebook, so the interactive page, the notebook and the worksheet
can never silently disagree -- the script asserts that agreement rather
than hoping for it ("coherence rules are hard requirements").

Run from the project root or from code/:
    python code/build_interactive_data.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths (relative to this script -- never hand-typed absolute paths)
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
ANALYSIS_DIR = DATA_DIR / "analysis"
ANSWER_KEY_DIR = DATA_DIR / "answer_key"
INTERACTIVE_DIR = PROJECT_ROOT / "interactive"
OUTPUT_PATH = INTERACTIVE_DIR / "_data.json"

# Output must never land inside an input directory.
assert INTERACTIVE_DIR.resolve() != DATA_DIR.resolve(), "output dir must differ from data dir"
assert DATA_DIR.resolve() not in INTERACTIVE_DIR.resolve().parents, "output dir must not be nested under data/"

# ---------------------------------------------------------------------------
# Config block
# ---------------------------------------------------------------------------

BUS = ["Nordics", "Central Europe", "Baltics & Poland"]
LINES = ["Hair Care", "Skin & Body", "Home Care", "Professional"]
MONTHS = [str(p) for p in pd.period_range("2024-01", "2025-12", freq="M")]
assert len(MONTHS) == 24, "observation window must be exactly 24 months"
MONTHS_2024 = [m for m in MONTHS if m.startswith("2024")]
MONTHS_2025 = [m for m in MONTHS if m.startswith("2025")]

CE = "Central Europe"
BP = "Baltics & Poland"
NORDICS = "Nordics"

# Cross-check tolerances (STOP and report if these are not met)
CASH_CONVERSION_TOLERANCE_PP = 0.5
VOLUME_RESPONSE_TOLERANCE = 0.05
ANCHOR_TOLERANCE_EUR_OR_PP = 0.01

CASH_CONVERSION_TARGETS_PCT = {
    "h1_2024_reported": 105.6,
    "h1_2025_reported": 71.9,
    "h1_2025_underlying": 63.3,
}
VOLUME_RESPONSE_TARGETS = {"h1": 1.069, "h2": 0.664}

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def r2(value) -> float | None:
    """Round to 2dp; NaN/None becomes JSON null rather than a crash."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return round(float(value), 2)


def series_to_list(series: pd.Series) -> list:
    return [r2(v) for v in series.tolist()]


def parse_worksheet_figures(text: str) -> dict:
    """Extract figure_id -> numeric value from evaluation_worksheet.md's
    '## Section E' table. That table states it is 'recomputed fresh ...
    on every run of this script -- never hardcoded'; parsing it here (rather
    than hardcoding the numbers we saw once) keeps this script's anchors
    honestly cross-checked against a second, independent computation."""
    marker = "## Section E"
    start = text.index(marker)
    end = text.index("\n## ", start + len(marker))
    section = text[start:end]
    values = {}
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 3:
            continue
        figure_id, _label, value_str = cells
        if figure_id in ("figure_id",) or set(figure_id) <= {"-"}:
            continue
        cleaned = value_str.replace("EUR", "").replace("%", "").replace(",", "").strip()
        try:
            values[figure_id] = float(cleaned)
        except ValueError:
            continue
    return values


# ---------------------------------------------------------------------------
# Load public CSVs
# ---------------------------------------------------------------------------

print("Loading public CSVs...", flush=True)
kpi = pd.read_csv(ANALYSIS_DIR / "kpi_monthly.csv", encoding="utf-8")
var = pd.read_csv(ANALYSIS_DIR / "variances_monthly.csv", encoding="utf-8")
pnl = pd.read_csv(DATA_DIR / "pnl_monthly.csv", encoding="utf-8")
pnl_budget = pd.read_csv(DATA_DIR / "budget_pnl_monthly.csv", encoding="utf-8")
opex = pd.read_csv(DATA_DIR / "opex_monthly.csv", encoding="utf-8")
customer_revenue = pd.read_csv(DATA_DIR / "customer_revenue_monthly.csv", encoding="utf-8")
receivables = pd.read_csv(DATA_DIR / "receivables_by_customer_monthly.csv", encoding="utf-8")
working_capital = pd.read_csv(DATA_DIR / "working_capital_monthly.csv", encoding="utf-8")
cash = pd.read_csv(DATA_DIR / "cash_monthly.csv", encoding="utf-8")

# flag is read as native bool by pandas here, but cast defensively in case a
# future regeneration writes it as text.
var["flag"] = var["flag"].astype(str).str.strip().eq("True") if var["flag"].dtype == object else var["flag"].astype(bool)

for name, df in [("kpi_monthly", kpi), ("variances_monthly", var), ("pnl_monthly", pnl)]:
    assert df["month"].isin(MONTHS).all(), f"{name}.csv contains a month outside the 24-month window"
print(f"  {len(kpi):,} kpi rows, {len(var):,} variance rows, {len(pnl):,} pnl rows", flush=True)

# ---------------------------------------------------------------------------
# Company-grain and BU-grain KPI/variance lookups
# ---------------------------------------------------------------------------

print("Building company and BU series...", flush=True)

kpi_company = (
    kpi[kpi["grain"] == "Company"]
    .pivot_table(index="month", columns="metric", values="value", aggfunc="first")
    .reindex(MONTHS)
)
kpi_by_bu = {
    bu: kpi[kpi["grain"] == bu]
    .pivot_table(index="month", columns="metric", values="value", aggfunc="first")
    .reindex(MONTHS)
    for bu in BUS
}


def var_series(grain: str, measure: str, basis: str, field: str) -> pd.Series:
    sub = var[(var["grain"] == grain) & (var["measure"] == measure) & (var["basis"] == basis)]
    return sub.set_index("month")[field].reindex(MONTHS)


ebitda_reported_co = var_series("Company", "EBITDA", "vs_budget", "current_eur")
ebitda_underlying_co = ebitda_reported_co - kpi_company["other_income_eur"]
cash_closing_co = cash.set_index("month")["cash_closing"].reindex(MONTHS)
cash_ocf_co = cash.set_index("month")["operating_cash_flow"].reindex(MONTHS)

company = {
    "net_revenue": series_to_list(kpi_company["net_revenue_eur"]),
    "net_revenue_budget": series_to_list(var_series("Company", "net_revenue", "vs_budget", "reference_eur")),
    "gm_pct": series_to_list(kpi_company["gross_margin_pct"]),
    "ebitda_reported": series_to_list(ebitda_reported_co),
    "ebitda_underlying": series_to_list(ebitda_underlying_co),
    "dso": series_to_list(kpi_company["dso_days"]),
    "cash_closing": series_to_list(cash_closing_co),
}

bu_out = {}
for bu in BUS:
    bu_out[bu] = {
        "net_revenue": series_to_list(var_series(bu, "net_revenue", "vs_budget", "current_eur")),
        "net_revenue_budget": series_to_list(var_series(bu, "net_revenue", "vs_budget", "reference_eur")),
        "material_cost": series_to_list(var_series(bu, "material_cost", "vs_budget", "current_eur")),
        "material_cost_budget": series_to_list(var_series(bu, "material_cost", "vs_budget", "reference_eur")),
        "gm_pct": series_to_list(kpi_by_bu[bu]["gross_margin_pct"]),
    }

# ---------------------------------------------------------------------------
# kpis_2025 -- one dict of headline figures per 2025 month
# ---------------------------------------------------------------------------

print("Building kpis_2025...", flush=True)

vsbud_pct_co = var_series("Company", "net_revenue", "vs_budget", "pct")

kpis_2025 = {}
for month in MONTHS_2025:
    prior_year_month = "2024-" + month[5:7]
    gm_now = kpi_company.loc[month, "gross_margin_pct"]
    gm_prior = kpi_company.loc[prior_year_month, "gross_margin_pct"]
    dso_now = kpi_company.loc[month, "dso_days"]
    dso_prior = kpi_company.loc[prior_year_month, "dso_days"]
    flags_count = int(((var["month"] == month) & var["flag"]).sum())

    kpis_2025[month] = {
        "net_revenue": r2(kpi_company.loc[month, "net_revenue_eur"]),
        "mom_pct": r2(kpi_company.loc[month, "revenue_growth_mom_pct"]),
        "yoy_pct": r2(kpi_company.loc[month, "revenue_growth_yoy_pct"]),
        "vsbud_pct": r2(vsbud_pct_co.loc[month]),
        "gm_pct": r2(gm_now),
        "gm_yoy_pp": r2(gm_now - gm_prior) if pd.notna(gm_now) and pd.notna(gm_prior) else None,
        "ebitda_reported": r2(ebitda_reported_co.loc[month]),
        "ebitda_underlying": r2(ebitda_underlying_co.loc[month]),
        "other_income": r2(kpi_company.loc[month, "other_income_eur"]),
        "dso": r2(dso_now),
        "dso_yoy_delta": r2(dso_now - dso_prior) if pd.notna(dso_now) and pd.notna(dso_prior) else None,
        "cash_closing": r2(cash_closing_co.loc[month]),
        "flags_count": flags_count,
    }

flags_report = {m: kpis_2025[m]["flags_count"] for m in MONTHS_2025}

# ---------------------------------------------------------------------------
# variances_2025 -- every variance row for each 2025 month, verbatim
# ---------------------------------------------------------------------------

print("Building variances_2025...", flush=True)

variances_2025 = {}
for month in MONTHS_2025:
    sub = var[var["month"] == month]
    rows = []
    for _, row in sub.iterrows():
        rows.append({
            "grain": row["grain"],
            "measure": row["measure"],
            "basis": row["basis"],
            "pct": r2(row["pct"]),
            "eur": r2(row["value_eur"]),
            "flag": bool(row["flag"]),
        })
    variances_2025[month] = rows

# ---------------------------------------------------------------------------
# S1 -- Nordics mix shift: material/volume/unit-cost indices, line shares
# ---------------------------------------------------------------------------

print("Building S1 (Nordics mix shift)...", flush=True)

nordics_pnl = pnl[pnl["bu"] == NORDICS]
material_by_month = nordics_pnl.groupby("month")["material_cost"].sum().reindex(MONTHS)
volume_by_month = nordics_pnl.groupby("month")["volume_units"].sum().reindex(MONTHS)
unit_cost_by_month = material_by_month / volume_by_month

material_base = material_by_month.loc[MONTHS_2024].mean()
volume_base = volume_by_month.loc[MONTHS_2024].mean()
unit_cost_base = unit_cost_by_month.loc[MONTHS_2024].mean()

line_vol_2024 = nordics_pnl[nordics_pnl["month"].isin(MONTHS_2024)].groupby("line")["volume_units"].sum()
line_vol_2025 = nordics_pnl[nordics_pnl["month"].isin(MONTHS_2025)].groupby("line")["volume_units"].sum()

s1 = {
    "material_index": series_to_list(material_by_month / material_base * 100),
    "volume_index": series_to_list(volume_by_month / volume_base * 100),
    "unit_cost_index": series_to_list(unit_cost_by_month / unit_cost_base * 100),
    "lines": LINES,
    "share_2024": [r2(line_vol_2024[l] / line_vol_2024.sum() * 100) for l in LINES],
    "share_2025": [r2(line_vol_2025[l] / line_vol_2025.sum() * 100) for l in LINES],
}

# ---------------------------------------------------------------------------
# S2 -- Central Europe DSO creep behind the warehouse one-off
# ---------------------------------------------------------------------------

print("Building S2 (Central Europe DSO / cash conversion)...", flush=True)

rheinkauf_ar = (
    receivables[(receivables["bu"] == CE) & (receivables["customer"] == "Rheinkauf Gruppe")]
    .set_index("month")["receivables_closing"].reindex(MONTHS)
)
rheinkauf_rev = (
    customer_revenue[(customer_revenue["bu"] == CE) & (customer_revenue["customer"] == "Rheinkauf Gruppe")]
    .set_index("month")["net_revenue"].reindex(MONTHS)
)
ce_total_ar = working_capital[working_capital["bu"] == CE].set_index("month")["receivables_closing"].reindex(MONTHS)
rest_ce_ar = ce_total_ar - rheinkauf_ar

h1_2024 = [m for m in MONTHS if "2024-01" <= m <= "2024-06"]
h1_2025 = [m for m in MONTHS if "2025-01" <= m <= "2025-06"]

# The read-only import of the generator: needed only for S2's warehouse-gain
# parameter (so it is never hand-retyped) and S3's counterfactual below.
# generate_financials.py guards its file-writing main() behind
# `if __name__ == "__main__"`, so importing it here reads config only.
sys.path.insert(0, str(SCRIPT_DIR))
import generate_financials as gf  # noqa: E402  (must follow sys.path insert)

warehouse_gain_eur = gf.config.S2_PARAMS["warehouse_gain_eur"]

ebitda_h1_24 = ebitda_reported_co.loc[h1_2024].sum()
ocf_h1_24 = cash_ocf_co.loc[h1_2024].sum()
conv_h1_24_reported = ocf_h1_24 / ebitda_h1_24 * 100

ebitda_h1_25 = ebitda_reported_co.loc[h1_2025].sum()
ocf_h1_25 = cash_ocf_co.loc[h1_2025].sum()
conv_h1_25_reported = ocf_h1_25 / ebitda_h1_25 * 100
conv_h1_25_underlying = (ocf_h1_25 - warehouse_gain_eur) / (ebitda_h1_25 - warehouse_gain_eur) * 100

cash_conversion_computed = {
    "h1_2024_reported": conv_h1_24_reported,
    "h1_2025_reported": conv_h1_25_reported,
    "h1_2025_underlying": conv_h1_25_underlying,
}
for key, target in CASH_CONVERSION_TARGETS_PCT.items():
    diff = abs(cash_conversion_computed[key] - target)
    assert diff <= CASH_CONVERSION_TOLERANCE_PP, (
        f"S2 cash-conversion cross-check FAILED for {key}: computed {cash_conversion_computed[key]:.2f}% "
        f"vs target ~{target}% (diff {diff:.2f}pp, tolerance {CASH_CONVERSION_TOLERANCE_PP}pp) -- STOP"
    )

s2 = {
    "rheinkauf_ar": series_to_list(rheinkauf_ar),
    "rheinkauf_rev": series_to_list(rheinkauf_rev),
    "rest_ce_ar": series_to_list(rest_ce_ar),
    "conversion": {k: r2(v) for k, v in cash_conversion_computed.items()},
}

# ---------------------------------------------------------------------------
# S3 -- Baltics & Poland growth bought with discount
# ---------------------------------------------------------------------------

print("Building S3 (Baltics & Poland discount / elasticity)...", flush=True)

baltics_actual = pnl[pnl["bu"] == BP].groupby("month")[["gross_revenue", "promo_discounts"]].sum().reindex(MONTHS)
baltics_budget = pnl_budget[pnl_budget["bu"] == BP].groupby("month")[["gross_revenue", "promo_discounts"]].sum().reindex(MONTHS)
discount_pct = baltics_actual["promo_discounts"] / baltics_actual["gross_revenue"] * 100
discount_budget_pct = baltics_budget["promo_discounts"] / baltics_budget["gross_revenue"] * 100

dec_cust = customer_revenue[
    (customer_revenue["bu"] == BP) & (customer_revenue["month"] == "2025-12") & (customer_revenue["customer"] != "Other")
].copy()
dec_cust["rate_pct"] = dec_cust["promo_discounts"] / dec_cust["gross_revenue"] * 100
dec_cust = dec_cust.sort_values("rate_pct", ascending=False)
customers_dec25 = [{"name": str(row.customer), "rate_pct": r2(row.rate_pct)} for row in dec_cust.itertuples()]
assert len(customers_dec25) == 10, f"expected 10 named Baltics & Poland accounts in Dec-2025, got {len(customers_dec25)}"

# Volume response per promotional euro, H1 vs H2 2025 -- generator-side
# counterfactual, same computation as validate_financials.py's
# check_rule_8c_s3 and notebooks/board_reporting.ipynb Section 6(b).
s3_bu = gf.config.S3_PARAMS["bu"]
assert s3_bu == BP, "config.S3_PARAMS bu no longer matches Baltics & Poland -- check config.py"


def half_response(months_half: list) -> float:
    delta_vol, delta_disc_eur = 0.0, 0.0
    for month in months_half:
        t = gf.MONTH_INDEX[month]
        for line in gf.config.LINES:
            normal = gf.normal_driver(s3_bu, line, t)
            story = gf.apply_s3(s3_bu, line, month, dict(normal))
            normal_gross = normal["volume"] * normal["price_cents"] / 100.0
            story_gross = story["volume"] * story["price_cents"] / 100.0
            delta_vol += story["volume"] - normal["volume"]
            delta_disc_eur += story_gross * story["discount_rate"] - normal_gross * normal["discount_rate"]
    return delta_vol / delta_disc_eur if delta_disc_eur else float("nan")


h1_months_gf = [m for m in gf.ACTUAL_MONTHS if "2025-01" <= m <= "2025-06"]
h2_months_gf = [m for m in gf.ACTUAL_MONTHS if "2025-07" <= m <= "2025-12"]
h1_response = half_response(h1_months_gf)
h2_response = half_response(h2_months_gf)

response_computed = {"h1": h1_response, "h2": h2_response}
for key, target in VOLUME_RESPONSE_TARGETS.items():
    diff = abs(response_computed[key] - target)
    assert diff <= VOLUME_RESPONSE_TOLERANCE, (
        f"S3 volume-response cross-check FAILED for {key}: computed {response_computed[key]:.3f} "
        f"vs target ~{target} (diff {diff:.3f}, tolerance {VOLUME_RESPONSE_TOLERANCE}) -- STOP"
    )

s3 = {
    "discount_pct": series_to_list(discount_pct),
    "discount_budget_pct": series_to_list(discount_budget_pct),
    "customers_dec25": customers_dec25,
    "response": {"h1": round(h1_response, 3), "h2": round(h2_response, 3)},
}

# ---------------------------------------------------------------------------
# Anchors -- fixed FY headline figures, cross-checked against
# evaluation_worksheet.md's independently-recomputed Section E
# ---------------------------------------------------------------------------

print("Building anchors and cross-checking against evaluation_worksheet.md Section E...", flush=True)

net_revenue_fy24 = pnl[pnl["month"].isin(MONTHS_2024)]["net_revenue"].sum()
net_revenue_fy25 = pnl[pnl["month"].isin(MONTHS_2025)]["net_revenue"].sum()
growth_pct = (net_revenue_fy25 / net_revenue_fy24 - 1) * 100

gp_fy24 = pnl[pnl["month"].isin(MONTHS_2024)]["gross_profit"].sum()
gp_fy25 = pnl[pnl["month"].isin(MONTHS_2025)]["gross_profit"].sum()
gm_fy24 = gp_fy24 / net_revenue_fy24 * 100
gm_fy25 = gp_fy25 / net_revenue_fy25 * 100

opex_fy24 = opex[opex["month"].isin(MONTHS_2024)][["sales_marketing", "admin_general", "other_income"]].sum()
opex_fy25 = opex[opex["month"].isin(MONTHS_2025)][["sales_marketing", "admin_general", "other_income"]].sum()

ebitda_rep_fy24 = gp_fy24 - opex_fy24["sales_marketing"] - opex_fy24["admin_general"] + opex_fy24["other_income"]
ebitda_rep_fy25 = gp_fy25 - opex_fy25["sales_marketing"] - opex_fy25["admin_general"] + opex_fy25["other_income"]
ebitda_und_fy25 = ebitda_rep_fy25 - opex_fy25["other_income"]

rheinkauf_ar_dec24 = receivables[
    (receivables["bu"] == CE) & (receivables["customer"] == "Rheinkauf Gruppe") & (receivables["month"] == "2024-12")
]["receivables_closing"].iloc[0]
rheinkauf_ar_dec25 = receivables[
    (receivables["bu"] == CE) & (receivables["customer"] == "Rheinkauf Gruppe") & (receivables["month"] == "2025-12")
]["receivables_closing"].iloc[0]

worksheet_text = (ANALYSIS_DIR / "evaluation_worksheet.md").read_text(encoding="utf-8")
worksheet_figures = parse_worksheet_figures(worksheet_text)

anchor_checks = [
    ("fy24_net_revenue", net_revenue_fy24, "company_net_revenue_fy24"),
    ("fy25_net_revenue", net_revenue_fy25, "company_net_revenue_fy25"),
    ("growth_pct", growth_pct, "company_revenue_growth_pct"),
    ("gm_fy24", gm_fy24, "gm_pct_fy24"),
    ("gm_fy25", gm_fy25, "gm_pct_fy25"),
    ("ebitda_rep_fy24", ebitda_rep_fy24, "ebitda_reported_fy24"),
    ("ebitda_rep_fy25", ebitda_rep_fy25, "ebitda_reported_fy25"),
    ("ebitda_und_fy25", ebitda_und_fy25, "ebitda_underlying_fy25"),
    ("rheinkauf_ar_dec24", rheinkauf_ar_dec24, "rheinkauf_ar_dec24"),
    ("rheinkauf_ar_dec25", rheinkauf_ar_dec25, "rheinkauf_ar_dec25"),
]

for name, computed_value, worksheet_key in anchor_checks:
    if worksheet_key not in worksheet_figures:
        raise ValueError(
            f"evaluation_worksheet.md Section E is missing figure '{worksheet_key}' "
            f"needed to cross-check anchor '{name}'"
        )
    expected = worksheet_figures[worksheet_key]
    diff = abs(round(float(computed_value), 2) - expected)
    assert diff <= ANCHOR_TOLERANCE_EUR_OR_PP, (
        f"Anchor cross-check FAILED for '{name}': computed {computed_value:.2f} vs "
        f"evaluation_worksheet.md Section E value {expected:.2f} (diff {diff:.2f}, "
        f"tolerance {ANCHOR_TOLERANCE_EUR_OR_PP}) -- STOP"
    )
print(f"  all {len(anchor_checks)} anchors agree with evaluation_worksheet.md Section E within "
      f"{ANCHOR_TOLERANCE_EUR_OR_PP}", flush=True)

anchors = {
    "fy24_net_revenue": r2(net_revenue_fy24),
    "fy25_net_revenue": r2(net_revenue_fy25),
    "growth_pct": r2(growth_pct),
    "gm_fy24": r2(gm_fy24),
    "gm_fy25": r2(gm_fy25),
    "ebitda_rep_fy24": r2(ebitda_rep_fy24),
    "ebitda_rep_fy25": r2(ebitda_rep_fy25),
    "ebitda_und_fy25": r2(ebitda_und_fy25),
    "rheinkauf_ar_dec24": r2(rheinkauf_ar_dec24),
    "rheinkauf_ar_dec25": r2(rheinkauf_ar_dec25),
}

# ---------------------------------------------------------------------------
# Assemble and write
# ---------------------------------------------------------------------------

print("Assembling final payload and writing JSON...", flush=True)

data_out = {
    "months": MONTHS,
    "company": company,
    "bu": bu_out,
    "kpis_2025": kpis_2025,
    "variances_2025": variances_2025,
    "s1": s1,
    "s2": s2,
    "s3": s3,
    "anchors": anchors,
}

INTERACTIVE_DIR.mkdir(parents=True, exist_ok=True)
with OUTPUT_PATH.open("w", encoding="utf-8") as f:
    json.dump(data_out, f, ensure_ascii=False, separators=(",", ":"))

size_bytes = OUTPUT_PATH.stat().st_size
print("=" * 70)
print(f"Wrote {OUTPUT_PATH.relative_to(PROJECT_ROOT)} -- {size_bytes:,} bytes ({size_bytes / 1024:.1f} KB)")
print("=" * 70)
print(f"S2 cash conversion (OCF/EBITDA, H1-on-H1): "
      f"H1-2024 reported {conv_h1_24_reported:.2f}%, "
      f"H1-2025 reported {conv_h1_25_reported:.2f}%, "
      f"H1-2025 underlying {conv_h1_25_underlying:.2f}% "
      f"(targets ~105.6 / ~71.9 / ~63.3)")
print(f"S3 volume response per promo EUR: H1 {h1_response:.3f}, H2 {h2_response:.3f} "
      f"(targets ~1.069 / ~0.664)")
print("Flagged-row counts per 2025 month:")
for month, count in flags_report.items():
    print(f"  {month}: {count}")
print("Done.")
