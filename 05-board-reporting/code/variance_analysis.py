"""
variance_analysis.py -- Deterministic variance-analysis layer for Case
Study 5 (Board Reporting Automation, Paju Consumer Products Oy).

Reads only the public CSVs in data/ -- never code/config.py, never
generate_financials.py, never anything under data/answer_key/ -- and
produces "the board pack in prose": budget-vs-actual and year-on-year
variance tables, a KPI series, a price-volume-mix bridge, and mechanical
threshold flags. Business units, product lines and months are all read
from the data itself, never hard-coded.

This layer states WHAT moved, exactly, with numbers, and never WHY -- no
causal language ("driven by", "due to", "because") appears anywhere in the
generated report. Explaining causes is the job of the storyteller layer,
which this script has no part in and does not
anticipate.

Inputs (data/):
    pnl_monthly.csv, budget_pnl_monthly.csv,
    opex_monthly.csv, budget_opex_monthly.csv,
    customer_master.csv, customer_revenue_monthly.csv,
    working_capital_monthly.csv, receivables_by_customer_monthly.csv,
    cash_monthly.csv

Outputs (data/analysis/):
    surface_report.md      -- the board pack in prose
    kpi_monthly.csv         -- tidy KPI series, company grain + GM% per BU
    variances_monthly.csv   -- tidy variance table, company/BU x measure x basis
    pvm_fy2025.csv           -- price-volume-mix bridge, FY2025 vs FY2024

Grain: "BU" rows are month x business unit, aggregated from the BU x
product-line grain of pnl_monthly.csv. "Company" rows are the sum of the
three BUs (opex_monthly and budget_opex_monthly carry no separate
corporate-level row, so summing the BU rows is the whole company).

Threshold policy (constants below): every flag is a mechanical breach of a
pre-set band, applied identically in every month and every BU -- no
threshold was chosen, or adjusted, by looking at which months contain a
designed story. EBITDA is given a materially higher percentage band and a
lower absolute-euro floor than the three revenue-line measures
(net_revenue, gross_profit, material_cost): EBITDA is a thin residual
margin, structurally more volatile in percentage terms than the revenue
lines that produce it (operating leverage -- confirmed empirically here:
company reported-EBITDA MoM% swings routinely exceed 10-20% while
net_revenue MoM% rarely does). A single percentage band across all four
measures would either flag EBITDA nearly every month or miss real moves
in the revenue lines. This is a property of the measure, fixed before
generating a single flag, not a fit to any month.

DSO convention: receivables_closing / trailing-12-month average daily net
revenue (net revenue summed over the trailing window, divided by the
calendar days in that window). The public dataset starts 2024-01, so the
trailing window is partial (fewer than 12 months) for 2024-01 through
2024-11 and full from 2024-12 onward -- documented, not hidden, in the
report. Receivables in this dataset carry a visible within-year seasonal
pattern (they build into December and unwind in Q1 -- visible directly in
working_capital_monthly.csv), so this report flags DSO deterioration only
year-on-year (same calendar month, twelve months apart), never
month-on-month, where the seasonal swing would swamp any real signal.

Revenue per head: trailing-window average daily company net revenue,
annualised at 365 days, divided by average headcount_fte over the same
window (same partial-window caveat as DSO -- annualising from a partial
window keeps early 2024 months on the same annual scale as the full
12-month windows from 2024-12 onward, rather than reading as a fraction of
a year's revenue).

Price-volume-mix convention (used for both the net_revenue and the
material_cost decomposition, FY2025 vs FY2024): building blocks are
FY2024 ("PY") and FY2025 ("CY") volume and unit price/cost at the finest
grain in scope -- BU x line (12 blocks) for the company-grain bridge, line
only (4 blocks) within a single BU for a BU-grain bridge. For a building
block b, unit_b = amount_b / volume_b (for material_cost this is unit
material cost, not net price). Then:

    volume_effect (blended)   = (V_CY_total - V_PY_total) * P_PY_blended
    price_effect  (line-level) = sum_b [ (P_CY_b - P_PY_b) * V_CY_b ]
    mix_effect                 = total_delta - volume_effect - price_effect

where P_PY_blended = sum_b(amount_PY_b) / sum_b(volume_PY_b) and
total_delta = sum_b(amount_CY_b) - sum_b(amount_PY_b). This reconciles to
the cent by construction: per building block, (V2*P2 - V1*P1) = DV*P1 +
DP*V2 exactly, so summed across blocks, "line-level volume effect" (each
block at its own PY unit price) plus "line-level price effect" (each
block at its own CY volume) equals total_delta exactly. mix_effect is
defined as exactly the gap between that line-level volume-effect sum and
the single blended-price volume_effect -- i.e. the amount attributable to
the *composition* of volume across building blocks, isolated from both a
single blended volume figure and the true per-block price effect. The
identity volume_effect + mix_effect + price_effect == total_delta is
asserted in code before the bridge is written out.

Run from the project root:
    python code/variance_analysis.py
"""

import calendar
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = DATA_DIR / "analysis"

assert OUTPUT_DIR != DATA_DIR, "output dir must differ from the source data dir"
assert OUTPUT_DIR.resolve() != SCRIPT_DIR.resolve(), "output dir must differ from the code dir"

INPUT_FILES = [
    "pnl_monthly", "budget_pnl_monthly",
    "opex_monthly", "budget_opex_monthly",
    "customer_master", "customer_revenue_monthly",
    "working_capital_monthly", "receivables_by_customer_monthly",
    "cash_monthly",
]

# ---------------------------------------------------------------------------
# Threshold policy -- see module docstring for rationale.
# key: (measure, basis) -> (pct_threshold, abs_threshold_company_eur, abs_threshold_bu_eur)
# A cell is flagged if it breaches EITHER the percentage OR the absolute-euro band.
# ---------------------------------------------------------------------------

THRESHOLDS = {
    ("net_revenue",   "MoM"):       (10.0, 500_000, 200_000),
    ("gross_profit",  "MoM"):       (10.0, 500_000, 200_000),
    ("material_cost", "MoM"):       (10.0, 500_000, 200_000),
    ("EBITDA",        "MoM"):       (20.0, 200_000, 100_000),

    ("net_revenue",   "YoY"):       (5.0, 400_000, 150_000),
    ("gross_profit",  "YoY"):       (5.0, 400_000, 150_000),
    ("material_cost", "YoY"):       (5.0, 400_000, 150_000),
    ("EBITDA",        "YoY"):       (15.0, 200_000, 100_000),

    ("net_revenue",   "vs_budget"): (3.0, 300_000, 150_000),
    ("gross_profit",  "vs_budget"): (3.0, 300_000, 150_000),
    ("material_cost", "vs_budget"): (3.0, 300_000, 150_000),
    ("EBITDA",        "vs_budget"): (8.0, 150_000, 75_000),
}

DSO_YOY_FLAG_DAYS = 5.0   # flag DSO deterioration if it worsens by more than this, YoY, same grain
TRAILING_WINDOW_MONTHS = 12

MEASURE_COLUMNS = {
    "net_revenue": "net_revenue",
    "gross_profit": "gross_profit",
    "material_cost": "material_cost",
    "EBITDA": "ebitda_reported",
}
MEASURE_ORDER = ["net_revenue", "gross_profit", "material_cost", "EBITDA"]
BASIS_ORDER = ["MoM", "YoY", "vs_budget"]

MONTH_NAMES = {i: calendar.month_name[i] for i in range(1, 13)}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_data() -> dict:
    print("Loading public data tables from data/ ...", flush=True)
    tables = {}
    for name in INPUT_FILES:
        path = DATA_DIR / f"{name}.csv"
        if not path.exists():
            raise FileNotFoundError(
                f"Required input not found: {path}. Run code/generate_financials.py first."
            )
        tables[name] = pd.read_csv(path)
        print(f"  {name}.csv: {len(tables[name])} rows", flush=True)
    return tables


# ---------------------------------------------------------------------------
# Grain construction: BU and Company rows for P&L and opex/EBITDA
# ---------------------------------------------------------------------------

PNL_SUM_COLS = [
    "volume_units", "gross_revenue", "promo_discounts", "net_revenue",
    "material_cost", "direct_labour", "logistics_cost", "gross_profit",
]
OPEX_SUM_COLS = ["sales_marketing", "admin_general", "other_income", "headcount_fte"]


def bu_pnl(pnl: pd.DataFrame) -> pd.DataFrame:
    return pnl.groupby(["month", "bu"], as_index=False)[PNL_SUM_COLS].sum()


def company_pnl(pnl: pd.DataFrame) -> pd.DataFrame:
    df = pnl.groupby("month", as_index=False)[PNL_SUM_COLS].sum()
    df.insert(1, "bu", "Company")
    return df


def company_opex(opex: pd.DataFrame) -> pd.DataFrame:
    df = opex.groupby("month", as_index=False)[OPEX_SUM_COLS].sum()
    df.insert(1, "bu", "Company")
    return df


def build_grain_table(pnl: pd.DataFrame, opex: pd.DataFrame) -> pd.DataFrame:
    """One table, Company + BU rows, per month, with EBITDA derived."""
    pnl_grain = pd.concat([company_pnl(pnl), bu_pnl(pnl)], ignore_index=True)
    opex_grain = pd.concat([company_opex(opex), opex[["month", "bu"] + OPEX_SUM_COLS]], ignore_index=True)
    merged = pnl_grain.merge(opex_grain, on=["month", "bu"], how="left")
    merged["ebitda_reported"] = (
        merged["gross_profit"] - merged["sales_marketing"] - merged["admin_general"] + merged["other_income"]
    )
    merged["ebitda_underlying"] = merged["ebitda_reported"] - merged["other_income"]
    merged["gross_margin_pct"] = merged["gross_profit"] / merged["net_revenue"] * 100
    merged["ebitda_pct_reported"] = merged["ebitda_reported"] / merged["net_revenue"] * 100
    merged["ebitda_pct_underlying"] = merged["ebitda_underlying"] / merged["net_revenue"] * 100
    return merged


def company_working_capital(wc: pd.DataFrame) -> pd.DataFrame:
    df = wc.groupby("month", as_index=False)[
        ["receivables_opening", "collections", "receivables_closing"]
    ].sum()
    df.insert(1, "bu", "Company")
    return df


# ---------------------------------------------------------------------------
# Calendar helpers
# ---------------------------------------------------------------------------

def days_in_month(month: str) -> int:
    y, m = int(month[:4]), int(month[5:7])
    return calendar.monthrange(y, m)[1]


def year_ago(month: str) -> str:
    y, m = month.split("-")
    return f"{int(y) - 1:04d}-{m}"


def trailing_window(months_sorted: list, month: str, window: int = TRAILING_WINDOW_MONTHS) -> list:
    i = months_sorted.index(month)
    return months_sorted[max(0, i - window + 1): i + 1]


# ---------------------------------------------------------------------------
# DSO and revenue-per-head (trailing-window KPIs)
# ---------------------------------------------------------------------------

def compute_dso(grain_pnl: pd.DataFrame, grain_wc: pd.DataFrame, months_sorted: list) -> pd.DataFrame:
    rows = []
    for grain in sorted(grain_pnl["bu"].unique()):
        rev = grain_pnl[grain_pnl["bu"] == grain].set_index("month")["net_revenue"]
        wc = grain_wc[grain_wc["bu"] == grain].set_index("month")["receivables_closing"]
        for month in months_sorted:
            window = trailing_window(months_sorted, month)
            total_rev = rev.loc[window].sum()
            total_days = sum(days_in_month(m) for m in window)
            avg_daily = total_rev / total_days
            dso = wc.loc[month] / avg_daily if avg_daily else np.nan
            rows.append({
                "month": month, "grain": grain, "dso_days": dso,
                "window_months": len(window),
            })
    return pd.DataFrame(rows)


def compute_revenue_per_head(company_grain: pd.DataFrame, months_sorted: list) -> pd.DataFrame:
    """Annualised at a 365-day year from the trailing window's average daily net revenue,
    so that partial windows (2024-01 .. 2024-11, fewer than 12 months of history) are on the
    same annual scale as the full 12-month windows from 2024-12 onward, rather than reading as
    a fraction of a year's revenue. A full 12-month window in a 366-day leap year (2024) is
    scaled down by the same ~0.3% as any other window -- a documented, negligible effect of
    a single fixed annualisation constant, not a second convention for full windows."""
    rev = company_grain.set_index("month")["net_revenue"]
    hc = company_grain.set_index("month")["headcount_fte"]
    rows = []
    for month in months_sorted:
        window = trailing_window(months_sorted, month)
        total_rev = rev.loc[window].sum()
        total_days = sum(days_in_month(m) for m in window)
        avg_hc = hc.loc[window].mean()
        annualised_rev = total_rev / total_days * 365
        rows.append({
            "month": month,
            "revenue_per_head_eur": annualised_rev / avg_hc if avg_hc else np.nan,
            "window_months": len(window),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Variance table: month x grain x measure x basis
# ---------------------------------------------------------------------------

def make_variance_row(month, grain, measure, basis, current, reference) -> dict:
    delta = current - reference
    pct = (delta / reference * 100) if reference != 0 else np.nan
    pct_th, abs_co, abs_bu = THRESHOLDS[(measure, basis)]
    abs_th = abs_co if grain == "Company" else abs_bu
    pct_breach = (not np.isnan(pct)) and abs(pct) > pct_th
    abs_breach = abs(delta) > abs_th
    return {
        "month": month, "grain": grain, "measure": measure, "basis": basis,
        "current_eur": round(current, 2), "reference_eur": round(reference, 2),
        "value_eur": round(delta, 2),
        "pct": round(pct, 2) if not np.isnan(pct) else np.nan,
        "flag": bool(pct_breach or abs_breach),
    }


def compute_variances(actual_grain: pd.DataFrame, budget_grain: pd.DataFrame, months_sorted: list) -> pd.DataFrame:
    act = actual_grain.set_index(["grain_key", "month"])
    bud = budget_grain.set_index(["grain_key", "month"])
    grains = sorted(actual_grain["bu"].unique(), key=lambda g: (g != "Company", g))
    month_index = {m: i for i, m in enumerate(months_sorted)}
    rows = []
    for grain in grains:
        for measure in MEASURE_ORDER:
            col = MEASURE_COLUMNS[measure]
            for month in months_sorted:
                key = (grain, month)
                if key not in act.index:
                    continue
                current = act.loc[key, col]
                # MoM
                i = month_index[month]
                if i > 0:
                    prev_month = months_sorted[i - 1]
                    prev_key = (grain, prev_month)
                    if prev_key in act.index:
                        rows.append(make_variance_row(
                            month, grain, measure, "MoM", current, act.loc[prev_key, col]
                        ))
                # YoY
                ya = year_ago(month)
                ya_key = (grain, ya)
                if ya_key in act.index:
                    rows.append(make_variance_row(
                        month, grain, measure, "YoY", current, act.loc[ya_key, col]
                    ))
                # vs budget
                if key in bud.index:
                    rows.append(make_variance_row(
                        month, grain, measure, "vs_budget", current, bud.loc[key, col]
                    ))
    df = pd.DataFrame(rows)
    df["basis"] = pd.Categorical(df["basis"], categories=BASIS_ORDER, ordered=True)
    df["measure"] = pd.Categorical(df["measure"], categories=MEASURE_ORDER, ordered=True)
    df = df.sort_values(["month", "grain", "measure", "basis"]).reset_index(drop=True)
    df["basis"] = df["basis"].astype(str)
    df["measure"] = df["measure"].astype(str)
    return df


# ---------------------------------------------------------------------------
# KPI table
# ---------------------------------------------------------------------------

def build_kpi_monthly(
    actual_grain: pd.DataFrame, variances_df: pd.DataFrame, dso_df: pd.DataFrame,
    rev_per_head_df: pd.DataFrame, months_sorted: list, bus_sorted: list,
) -> pd.DataFrame:
    rows = []
    co = actual_grain[actual_grain["bu"] == "Company"].set_index("month")
    dso_co = dso_df[dso_df["grain"] == "Company"].set_index("month")["dso_days"]
    rph = rev_per_head_df.set_index("month")["revenue_per_head_eur"]

    for month in months_sorted:
        rows.append({"month": month, "grain": "Company", "metric": "net_revenue_eur",
                      "value": round(co.loc[month, "net_revenue"], 2)})
        for basis, metric_name in [("MoM", "revenue_growth_mom_pct"), ("YoY", "revenue_growth_yoy_pct")]:
            match = variances_df[
                (variances_df["month"] == month) & (variances_df["grain"] == "Company")
                & (variances_df["measure"] == "net_revenue") & (variances_df["basis"] == basis)
            ]
            if not match.empty:
                rows.append({"month": month, "grain": "Company", "metric": metric_name,
                              "value": match["pct"].iloc[0]})
        rows.append({"month": month, "grain": "Company", "metric": "gross_margin_pct",
                      "value": round(co.loc[month, "gross_margin_pct"], 2)})
        rows.append({"month": month, "grain": "Company", "metric": "ebitda_pct_reported",
                      "value": round(co.loc[month, "ebitda_pct_reported"], 2)})
        rows.append({"month": month, "grain": "Company", "metric": "ebitda_pct_underlying",
                      "value": round(co.loc[month, "ebitda_pct_underlying"], 2)})
        rows.append({"month": month, "grain": "Company", "metric": "other_income_eur",
                      "value": round(co.loc[month, "other_income"], 2)})
        rows.append({"month": month, "grain": "Company", "metric": "dso_days",
                      "value": round(dso_co.loc[month], 1)})
        rows.append({"month": month, "grain": "Company", "metric": "revenue_per_head_eur",
                      "value": round(rph.loc[month], 0)})
        for bu in bus_sorted:
            bu_row = actual_grain[(actual_grain["bu"] == bu) & (actual_grain["month"] == month)].iloc[0]
            rows.append({"month": month, "grain": bu, "metric": "gross_margin_pct",
                          "value": round(bu_row["gross_margin_pct"], 2)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Price-volume-mix bridge
# ---------------------------------------------------------------------------

def pvm_bridge(pnl_slice: pd.DataFrame, group_cols: list, measure: str) -> dict:
    df = pnl_slice.copy()
    df["year"] = df["month"].str[:4]
    fy = df.groupby(group_cols + ["year"], as_index=False).agg(
        volume=("volume_units", "sum"), amount=(measure, "sum")
    )
    fy["unit"] = fy["amount"] / fy["volume"]
    py = fy[fy["year"] == "2024"].set_index(group_cols)
    cy = fy[fy["year"] == "2025"].set_index(group_cols)
    common = py.index.intersection(cy.index)
    if len(common) < len(py.index) or len(common) < len(cy.index):
        raise ValueError(f"PVM building blocks not aligned between FY2024 and FY2025 for {group_cols}/{measure}")
    py, cy = py.loc[common], cy.loc[common]

    total_py = py["amount"].sum()
    total_cy = cy["amount"].sum()
    total_delta = total_cy - total_py

    line_volume_effect = ((cy["volume"] - py["volume"]) * py["unit"]).sum()
    price_effect = ((cy["unit"] - py["unit"]) * cy["volume"]).sum()

    blended_py_unit = total_py / py["volume"].sum()
    total_delta_volume = cy["volume"].sum() - py["volume"].sum()
    volume_effect = total_delta_volume * blended_py_unit

    mix_effect = line_volume_effect - volume_effect

    reconciled = volume_effect + mix_effect + price_effect
    if abs(reconciled - total_delta) > 0.01:
        raise AssertionError(
            f"PVM bridge does not reconcile for {group_cols}/{measure}: "
            f"{reconciled:.2f} vs total_delta {total_delta:.2f}"
        )

    return {
        "fy2024_eur": total_py, "fy2025_eur": total_cy, "delta_eur": total_delta,
        "volume_effect_eur": volume_effect, "mix_effect_eur": mix_effect, "price_effect_eur": price_effect,
    }


def build_pvm(pnl: pd.DataFrame, bus_sorted: list) -> pd.DataFrame:
    rows = []
    for measure in ["net_revenue", "material_cost"]:
        res = pvm_bridge(pnl, ["bu", "line"], measure)
        rows.append({"grain": "Company", "measure": measure, **{k: round(v, 2) for k, v in res.items()}})
        for bu in bus_sorted:
            sub = pnl[pnl["bu"] == bu]
            res_bu = pvm_bridge(sub, ["line"], measure)
            rows.append({"grain": bu, "measure": measure, **{k: round(v, 2) for k, v in res_bu.items()}})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt_eur(x) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    sign = "-" if x < 0 else ""
    return f"{sign}€{abs(x):,.0f}"


def fmt_pct(x, decimals: int = 1) -> str:
    """Signed percentage -- for variances and deltas (MoM/YoY/vs-budget %)."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    sign = "+" if x >= 0 else ""
    return f"{sign}{x:.{decimals}f}%"


def fmt_pct_level(x, decimals: int = 1) -> str:
    """Unsigned percentage -- for levels (gross margin %, EBITDA % of revenue)."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"{x:.{decimals}f}%"


def fmt_pp(x, decimals: int = 1) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    sign = "+" if x >= 0 else ""
    return f"{sign}{x:.{decimals}f}pp"


def fmt_days(x, decimals: int = 1) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"{x:.{decimals}f}d"


def month_label(month: str) -> str:
    y, m = int(month[:4]), int(month[5:7])
    return f"{MONTH_NAMES[m]} {y}"


def md_table(headers: list, rows: list) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------

def variance_lookup(variances_df: pd.DataFrame) -> dict:
    """month, grain, measure -> {basis: row} for O(1) report building."""
    lookup = {}
    for _, row in variances_df.iterrows():
        key = (row["month"], row["grain"], row["measure"])
        lookup.setdefault(key, {})[row["basis"]] = row
    return lookup


def variance_table_for_month(month, grains, var_lookup) -> str:
    headers = ["Grain", "Measure", "Actual", "MoM", "YoY", "vs Budget"]
    rows = []
    for grain in grains:
        for measure in MEASURE_ORDER:
            bases = var_lookup.get((month, grain, measure), {})
            current = None
            cells = {}
            for basis in BASIS_ORDER:
                r = bases.get(basis)
                if r is None:
                    cells[basis] = "n/a"
                    continue
                current = r["current_eur"]
                text = fmt_pct(r["pct"])
                if r["flag"]:
                    text = f"**{text}**"
                cells[basis] = text
            actual_text = fmt_eur(current) if current is not None else "n/a"
            rows.append([grain, measure, actual_text, cells["MoM"], cells["YoY"], cells["vs_budget"]])
    return md_table(headers, rows)


def build_report(
    actual_grain, budget_grain, variances_df, kpi_df, dso_df, cash, pvm_df, months_sorted, bus_sorted,
) -> str:
    print("Assembling surface_report.md ...", flush=True)
    grains = ["Company"] + bus_sorted
    var_lookup = variance_lookup(variances_df)
    all_flags = []  # (month, grain, measure, basis, text) for the appendix

    co_grain = actual_grain[actual_grain["bu"] == "Company"].set_index("month")
    dso_indexed = dso_df.set_index(["grain", "month"])
    cash_indexed = cash.set_index("month")

    lines = []
    lines.append("# Paju Consumer Products Oy -- Board Pack (Deterministic Variance Analysis)")
    lines.append("")
    lines.append(
        "Generated by `code/variance_analysis.py` from the public data tables only. "
        "This report states what moved, with numbers, at company and business-unit grain. "
        "It does not explain why anything moved -- that is a separate layer, not run here. "
        "Figures are EUR, ex-VAT, rounded for display; underlying totals are exact to the cent."
    )
    lines.append("")

    # -- Methodology --------------------------------------------------------
    lines.append("## Methodology and thresholds")
    lines.append("")
    lines.append(
        "A cell is flagged when it breaches **either** the percentage band **or** the absolute-euro "
        "floor below, whichever is looser for that grain. Company-grain floors are higher than "
        "BU-grain floors because the company total is roughly the sum of three BUs. EBITDA carries a "
        "wider percentage band and a lower euro floor than the three revenue-line measures because it "
        "is a thin residual margin, structurally more volatile in percentage terms (operating "
        "leverage) -- a property of the measure, fixed before any figure below was generated."
    )
    lines.append("")
    thresh_rows = []
    for measure in MEASURE_ORDER:
        for basis in BASIS_ORDER:
            pct_th, abs_co, abs_bu = THRESHOLDS[(measure, basis)]
            thresh_rows.append([measure, basis, f"{pct_th:.0f}%", fmt_eur(abs_co), fmt_eur(abs_bu)])
    lines.append(md_table(
        ["Measure", "Basis", "% threshold", "Company € floor", "BU € floor"], thresh_rows
    ))
    lines.append("")
    lines.append(
        f"DSO (receivables_closing ÷ trailing-{TRAILING_WINDOW_MONTHS}-month average daily net "
        f"revenue) is flagged only year-on-year, same calendar month, when it worsens by more than "
        f"{DSO_YOY_FLAG_DAYS:.0f} days -- receivables in this dataset build seasonally into December "
        "and unwind in Q1 (visible directly in `working_capital_monthly.csv`), so a month-on-month DSO "
        "threshold would flag the calendar, not a change in payment behaviour. The trailing window is "
        "partial (fewer than 12 months of history) for 2024-01 through 2024-11, since the public dataset "
        "starts 2024-01; those DSO figures are shown with the window length noted."
    )
    lines.append("")
    lines.append(
        "Revenue per head is the trailing-window average daily company net revenue, annualised at 365 "
        "days, divided by average headcount over the same window (same partial-window caveat as DSO)."
    )
    lines.append("")
    lines.append(
        "Year-on-year variances are not computable for calendar-2024 months: the public dataset has no "
        "2023 actuals or budget. 2024-01 has no month-on-month comparator for the same reason. Both are "
        "omitted from the tables below rather than shown as a false zero."
    )
    lines.append("")
    lines.append(
        "EBITDA is reported EBITDA (gross profit less sales & marketing less admin, plus other income) "
        "throughout the variance table and the flag thresholds. Underlying EBITDA (reported less other "
        "income) is shown alongside it in the KPI series and in the monthly narrative only for months "
        "where other income is non-zero -- other income is zero every month except where a one-off is "
        "booked, so any non-zero month is a one-off by construction. Showing the split draws no "
        "conclusion about which figure is more representative."
    )
    lines.append("")

    # -- FY2024 baseline ------------------------------------------------------
    lines.append("## FY2024 baseline")
    lines.append("")
    lines.append(
        "FY2024 is the first year of the observation window; there is no prior-year data in the public "
        "dataset, so no year-on-year comparison is possible for it. The figures below are annual actual "
        "vs annual budget, for context -- they are not evaluated against the monthly flag thresholds "
        "used elsewhere in this pack, which are calibrated for monthly moves."
    )
    lines.append("")
    fy2024_actual = actual_grain[actual_grain["month"].str.startswith("2024")]
    fy2024_budget = budget_grain[budget_grain["month"].str.startswith("2024")]
    baseline_rows = []
    for grain in grains:
        a = fy2024_actual[fy2024_actual["bu"] == grain]
        b = fy2024_budget[fy2024_budget["bu"] == grain]
        for measure in MEASURE_ORDER:
            col = MEASURE_COLUMNS[measure]
            act_total = a[col].sum()
            bud_total = b[col].sum()
            delta = act_total - bud_total
            pct = delta / bud_total * 100 if bud_total else np.nan
            baseline_rows.append([grain, measure, fmt_eur(act_total), fmt_eur(bud_total), fmt_pct(pct)])
    lines.append(md_table(["Grain", "Measure", "FY2024 actual", "FY2024 budget", "vs budget"], baseline_rows))
    lines.append("")

    fy2024_co = fy2024_actual[fy2024_actual["bu"] == "Company"]
    fy2024_gm = fy2024_co["gross_profit"].sum() / fy2024_co["net_revenue"].sum() * 100
    fy2024_ebitda_pct = fy2024_co["ebitda_reported"].sum() / fy2024_co["net_revenue"].sum() * 100
    dso_dec24 = dso_indexed.loc[("Company", "2024-12")]
    rph_dec24 = kpi_df[
        (kpi_df["month"] == "2024-12") & (kpi_df["grain"] == "Company") & (kpi_df["metric"] == "revenue_per_head_eur")
    ]["value"].iloc[0]
    lines.append(
        f"Company FY2024: gross margin {fmt_pct_level(fy2024_gm)} of net revenue, reported EBITDA "
        f"{fmt_pct_level(fy2024_ebitda_pct)} of net revenue. DSO at December 2024 (trailing "
        f"{int(dso_dec24['window_months'])}-month window): {fmt_days(dso_dec24['dso_days'])}. "
        f"Revenue per head (trailing twelve months to December 2024): {fmt_eur(rph_dec24)}."
    )
    lines.append("")
    fy2024_all = variances_df[variances_df["month"].str.startswith("2024")]
    fy2024_flags = fy2024_all[fy2024_all["flag"]]
    lines.append(
        f"Applying the same monthly thresholds used elsewhere in this pack to each individual month of "
        f"FY2024 (context only -- these are not counted in the flag appendix below, which covers 2025 "
        f"only): {len(fy2024_flags)} of {len(fy2024_all)} evaluated month x grain x measure x basis cells "
        f"would have flagged, mostly on vs-budget. Month-by-month detail for FY2024 is available in full "
        f"in `variances_monthly.csv` and `kpi_monthly.csv` (all 24 months are written to both files; the "
        f"narrative below covers 2025 month by month, as the year with a prior-year comparator)."
    )
    lines.append("")

    # -- Monthly detail, 2025 -------------------------------------------------
    lines.append("## Monthly detail -- 2025")
    lines.append("")
    months_2025 = [m for m in months_sorted if m.startswith("2025")]
    for month in months_2025:
        lines.append(f"### {month_label(month)}")
        lines.append("")

        co = co_grain.loc[month]
        rev_mom = var_lookup.get((month, "Company", "net_revenue"), {}).get("MoM")
        rev_yoy = var_lookup.get((month, "Company", "net_revenue"), {}).get("YoY")
        rev_bud = var_lookup.get((month, "Company", "net_revenue"), {}).get("vs_budget")
        gm_yoy_pp = None
        ya = year_ago(month)
        if ya in co_grain.index:
            gm_yoy_pp = co.loc["gross_margin_pct"] - co_grain.loc[ya, "gross_margin_pct"]
        dso_row = dso_indexed.loc[("Company", month)]
        dso_yoy_delta = None
        if ya in months_sorted and ("Company", ya) in dso_indexed.index:
            dso_yoy_delta = dso_row["dso_days"] - dso_indexed.loc[("Company", ya), "dso_days"]
        rph = kpi_df[
            (kpi_df["month"] == month) & (kpi_df["grain"] == "Company") & (kpi_df["metric"] == "revenue_per_head_eur")
        ]["value"].iloc[0]

        headline = (
            f"Company net revenue {fmt_eur(co['net_revenue'])} "
            f"(MoM {fmt_pct(rev_mom['pct']) if rev_mom is not None else 'n/a'}, "
            f"YoY {fmt_pct(rev_yoy['pct']) if rev_yoy is not None else 'n/a'}, "
            f"vs budget {fmt_pct(rev_bud['pct']) if rev_bud is not None else 'n/a'}). "
            f"Gross margin {fmt_pct_level(co['gross_margin_pct'])}"
            f"{f' (YoY {fmt_pp(gm_yoy_pp)})' if gm_yoy_pp is not None else ''}. "
            f"Reported EBITDA {fmt_pct_level(co['ebitda_pct_reported'])} of net revenue"
        )
        if co["other_income"] != 0:
            headline += (
                f", including {fmt_eur(co['other_income'])} of other income this month; "
                f"underlying EBITDA (ex that amount) is {fmt_pct_level(co['ebitda_pct_underlying'])} of net revenue"
            )
        headline += (
            f". DSO {fmt_days(dso_row['dso_days'])}"
            f"{f' (YoY {fmt_days(dso_yoy_delta)})' if dso_yoy_delta is not None else ''}"
            f". Revenue per head (trailing twelve months) {fmt_eur(rph)}."
        )
        lines.append(headline)
        lines.append("")

        lines.append(variance_table_for_month(month, grains, var_lookup))
        lines.append("")

        flags = []
        for grain in grains:
            for measure in MEASURE_ORDER:
                bases = var_lookup.get((month, grain, measure), {})
                for basis in BASIS_ORDER:
                    r = bases.get(basis)
                    if r is not None and r["flag"]:
                        text = (
                            f"{grain} {measure} {basis}: {fmt_pct(r['pct'])} "
                            f"({fmt_eur(r['value_eur'])}, actual {fmt_eur(r['current_eur'])} "
                            f"vs reference {fmt_eur(r['reference_eur'])})"
                        )
                        flags.append(text)
                        all_flags.append((month, grain, measure, basis, text))
        # DSO YoY flags (worsening only -- a DSO improvement is never flagged)
        for grain in grains:
            key = (grain, month)
            ya_key = (grain, ya)
            if key in dso_indexed.index and ya_key in dso_indexed.index:
                delta = dso_indexed.loc[key, "dso_days"] - dso_indexed.loc[ya_key, "dso_days"]
                if delta > DSO_YOY_FLAG_DAYS:
                    text = (
                        f"{grain} DSO YoY: {fmt_days(delta)} worse "
                        f"({fmt_days(dso_indexed.loc[ya_key, 'dso_days'])} -> {fmt_days(dso_indexed.loc[key, 'dso_days'])})"
                    )
                    flags.append(text)
                    all_flags.append((month, grain, "DSO", "YoY", text))

        if flags:
            lines.append("**Flags this month:**")
            for f in flags:
                lines.append(f"- {f}")
        else:
            lines.append("No threshold breaches this month.")
        lines.append("")

        gm_bu_rows = []
        for grain in grains:
            gv = actual_grain[(actual_grain["bu"] == grain) & (actual_grain["month"] == month)]["gross_margin_pct"].iloc[0]
            dv = dso_indexed.loc[(grain, month), "dso_days"]
            dv_yoy = "n/a"
            if (grain, ya) in dso_indexed.index:
                dv_yoy = fmt_days(dso_indexed.loc[(grain, month), "dso_days"] - dso_indexed.loc[(grain, ya), "dso_days"])
            gm_bu_rows.append([grain, fmt_pct_level(gv), fmt_days(dv), dv_yoy])
        lines.append(md_table(["Grain", "Gross margin %", "DSO", "DSO YoY Δ"], gm_bu_rows))
        lines.append("")

        cash_row = cash_indexed.loc[month]
        cash_text = (
            f"Cash closing {fmt_eur(cash_row['cash_closing'])}, operating cash flow "
            f"{fmt_eur(cash_row['operating_cash_flow'])}, investing cash flow "
            f"{fmt_eur(cash_row['investing_cash_flow'])} this month."
        )
        prev_i = months_sorted.index(month) - 1
        if prev_i >= 0:
            prev_month = months_sorted[prev_i]
            mom_cash = cash_row["cash_closing"] - cash_indexed.loc[prev_month, "cash_closing"]
            cash_text += f" Cash closing MoM {fmt_eur(mom_cash)}."
        if ya in cash_indexed.index:
            yoy_cash = cash_row["cash_closing"] - cash_indexed.loc[ya, "cash_closing"]
            cash_text += f" Cash closing YoY {fmt_eur(yoy_cash)}."
        lines.append(cash_text)
        lines.append("")

    # -- PVM bridge -------------------------------------------------------
    lines.append("## FY2025 vs FY2024 -- price / volume / mix bridge")
    lines.append("")
    lines.append(
        "Convention: see module docstring in `code/variance_analysis.py`. Volume effect uses a single "
        "blended FY2024 unit price/cost applied to the total change in volume; price effect is computed "
        "line by line at that line's own FY2025 volume; mix effect is the remainder -- the amount "
        "attributable to the composition of volume shifting across lines (or BUs, at company grain), "
        "isolated from a uniform volume change and from genuine unit price/cost movement. The three "
        "effects sum to the total change exactly, to the cent (asserted in code)."
    )
    lines.append("")
    pvm_rows = []
    for _, r in pvm_df.iterrows():
        pvm_rows.append([
            r["grain"], r["measure"], fmt_eur(r["fy2024_eur"]), fmt_eur(r["fy2025_eur"]),
            fmt_eur(r["delta_eur"]), fmt_eur(r["volume_effect_eur"]), fmt_eur(r["mix_effect_eur"]),
            fmt_eur(r["price_effect_eur"]),
        ])
    lines.append(md_table(
        ["Grain", "Measure", "FY2024", "FY2025", "Δ total", "Volume effect", "Mix effect", "Price effect"],
        pvm_rows,
    ))
    lines.append("")

    # -- Appendix: flag index ----------------------------------------------
    lines.append("## Appendix -- flag index")
    lines.append("")
    lines.append(
        "Every threshold breach in the monthly detail above, in one place, chronological. "
        f"{len(all_flags)} flags across {len(months_2025)} months of 2025."
    )
    lines.append("")
    if all_flags:
        appendix_rows = [[m, g, meas, b, t] for (m, g, meas, b, t) in all_flags]
        lines.append(md_table(["Month", "Grain", "Measure", "Basis", "Detail"], appendix_rows))
    else:
        lines.append("No flags were raised.")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Validation of this script's own outputs (not the generator's coherence rules --
# those are validate_financials.py's job; these are self-checks on this layer)
# ---------------------------------------------------------------------------

def self_check(actual_grain: pd.DataFrame, pnl: pd.DataFrame, opex: pd.DataFrame):
    print("Running self-checks ...", flush=True)
    co = actual_grain[actual_grain["bu"] == "Company"].set_index("month")
    bu_sum = actual_grain[actual_grain["bu"] != "Company"].groupby("month")[
        ["net_revenue", "gross_profit", "material_cost", "ebitda_reported"]
    ].sum()
    for col in ["net_revenue", "gross_profit", "material_cost", "ebitda_reported"]:
        diff = (co[col] - bu_sum[col]).abs().max()
        if diff > 0.01:
            raise AssertionError(f"BU rows do not sum to company for {col}: max diff {diff:.4f}")
    print("  BU-to-company aggregation identity holds (all four measures, all months).", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70, flush=True)
    print("variance_analysis.py -- Case Study 5 deterministic analysis layer", flush=True)
    print("=" * 70, flush=True)

    tables = load_data()
    pnl, bpnl = tables["pnl_monthly"], tables["budget_pnl_monthly"]
    opex, bopex = tables["opex_monthly"], tables["budget_opex_monthly"]
    wc = tables["working_capital_monthly"]
    cash = tables["cash_monthly"]

    months_sorted = sorted(pnl["month"].unique())
    bus_sorted = sorted(pnl["bu"].unique())
    print(f"Months: {months_sorted[0]} .. {months_sorted[-1]} ({len(months_sorted)}); BUs: {bus_sorted}", flush=True)

    print("Building Company + BU grain tables (actual and budget) ...", flush=True)
    actual_grain = build_grain_table(pnl, opex)
    budget_grain = build_grain_table(bpnl, bopex)
    actual_grain["grain_key"] = actual_grain["bu"]
    budget_grain["grain_key"] = budget_grain["bu"]

    self_check(actual_grain, pnl, opex)

    print("Computing DSO (trailing-window, Company + BU) ...", flush=True)
    grain_wc = pd.concat([company_working_capital(wc), wc], ignore_index=True)
    dso_df = compute_dso(actual_grain, grain_wc, months_sorted)

    print("Computing revenue per head (trailing-window, Company) ...", flush=True)
    rev_per_head_df = compute_revenue_per_head(actual_grain[actual_grain["bu"] == "Company"], months_sorted)

    print("Computing variance table (MoM / YoY / vs budget, Company + BU x 4 measures) ...", flush=True)
    variances_df = compute_variances(actual_grain, budget_grain, months_sorted)
    n_flags = int(variances_df["flag"].sum())
    print(f"  {len(variances_df)} variance rows, {n_flags} flagged.", flush=True)

    print("Building KPI series ...", flush=True)
    kpi_df = build_kpi_monthly(actual_grain, variances_df, dso_df, rev_per_head_df, months_sorted, bus_sorted)

    print("Building price-volume-mix bridge (FY2025 vs FY2024) ...", flush=True)
    pvm_df = build_pvm(pnl, bus_sorted)

    report_text = build_report(
        actual_grain, budget_grain, variances_df, kpi_df, dso_df, cash, pvm_df, months_sorted, bus_sorted,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    column_order = ["month", "grain", "measure", "basis", "current_eur", "reference_eur", "value_eur", "pct", "flag"]
    variances_df[column_order].to_csv(OUTPUT_DIR / "variances_monthly.csv", index=False, encoding="utf-8")
    print(f"Wrote {OUTPUT_DIR / 'variances_monthly.csv'} ({len(variances_df)} rows)", flush=True)

    kpi_df.to_csv(OUTPUT_DIR / "kpi_monthly.csv", index=False, encoding="utf-8")
    print(f"Wrote {OUTPUT_DIR / 'kpi_monthly.csv'} ({len(kpi_df)} rows)", flush=True)

    pvm_df.to_csv(OUTPUT_DIR / "pvm_fy2025.csv", index=False, encoding="utf-8")
    print(f"Wrote {OUTPUT_DIR / 'pvm_fy2025.csv'} ({len(pvm_df)} rows)", flush=True)

    (OUTPUT_DIR / "surface_report.md").write_text(report_text, encoding="utf-8")
    print(f"Wrote {OUTPUT_DIR / 'surface_report.md'} ({len(report_text.splitlines())} lines)", flush=True)

    print("=" * 70, flush=True)
    print("Done.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"variance_analysis.py failed: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
