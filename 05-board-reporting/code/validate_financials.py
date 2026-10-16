"""
validate_financials.py — Coherence rule validation for the Paju Consumer
Products Oy synthetic board-reporting dataset.

Implements the 12 coherence rules of the design as check_rule_N_<slug>
functions, each returning (passed: bool, message: str). Prints a per-rule
report and exits 1 if any rule fails, matching the churn precedent
(validate_data.py).

Measurement choices for rule 8 (story signatures), documented here because
the design gives magnitudes but not always an exact "compared to what"
window; each choice was fixed during calibration and is now load-bearing:

  S1 (Nordics): BU material spend YoY, BU net revenue YoY and BU gross
      margin delta are all FY2024-actual vs FY2025-actual (full-year sums).
      Unit material cost is checked per affected line (Home Care, Skin &
      Body), also FY24 vs FY25, since that is the answer key's decisive
      fact (flat *per line*, not blended across the BU's changed mix).

  S3 (Baltics & Poland): margin erosion is measured as Q4-2025 average
      gross margin (Oct-Dec, the period furthest into the discount ramp)
      versus FY2024 average gross margin — a "before/after" state
      comparison, which is how the design's own narrative frames it
      ("erodes from ~38% to ~33%"), rather than a FY24-vs-FY25 full-year
      average, which is diluted by the ramp's early, low-discount months.
      The fading-elasticity check recomputes a counterfactual (no-story)
      volume and discount-euro path from the deterministic driver model
      (normal_driver in generate_financials.py — explicitly sanctioned as
      generation-side validation) and compares H1 vs H2 2025
      delta-volume / delta-discount-euro.

  S2 (Central Europe): AR balances are terms-based (the most recent
      `terms` days of billing — see generate_financials.ar_terms_based),
      so they are genuinely seasonal: December balloons, Q1 unwinds, as
      a real balance sheet does. DSO (receivables_closing divided by
      trailing-12-month average daily net revenue) therefore swings with
      the calendar, and the S2 comparison must be like-for-like
      year-on-year: Nov-Dec 2025 average vs Nov-Dec 2024 average, where
      the seasonal numerator cancels and what remains is the terms
      drift. Cash conversion (OCF / EBITDA) compares H1-2024 *reported*
      (no material one-off sits in that half) to H1-2025 *underlying*
      (reported EBITDA and OCF with the April warehouse gain backed out)
      — the same seasonal collections pattern sits in both halves, so
      the comparison isolates the drift; reported-vs-reported shows a
      materially smaller fall by construction, which is the mask.

  Rule 9 (noise ceiling): "the smallest story's smallest monthly impact"
      is read as each story's *median* absolute monthly gross-profit
      impact across its active months, not the literal minimum. S3 is a
      slow ramp whose first month or two is, by design, a near-zero
      signal (discount barely above the 8% baseline) — a literal minimum
      would be dominated by that single transition month and would not
      represent "the story," which is exactly the failure mode this rule
      exists to catch in the other direction. The median is the
      representative monthly scale of each story.

Run from the project root:
    python code/validate_financials.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"

sys.path.insert(0, str(SCRIPT_DIR))
import config
import generate_financials as gf

# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_data() -> dict:
    paths = {
        "pnl": DATA_DIR / "pnl_monthly.csv",
        "budget_pnl": DATA_DIR / "budget_pnl_monthly.csv",
        "opex": DATA_DIR / "opex_monthly.csv",
        "budget_opex": DATA_DIR / "budget_opex_monthly.csv",
        "customer_master": DATA_DIR / "customer_master.csv",
        "customer_revenue": DATA_DIR / "customer_revenue_monthly.csv",
        "working_capital": DATA_DIR / "working_capital_monthly.csv",
        "receivables": DATA_DIR / "receivables_by_customer_monthly.csv",
        "cash": DATA_DIR / "cash_monthly.csv",
        "answer_key": DATA_DIR / "answer_key" / "stories.csv",
    }
    missing = [k for k, p in paths.items() if not p.exists()]
    if missing:
        print(f"FATAL: Missing data files: {missing}")
        print("Run generate_financials.py first.")
        sys.exit(1)
    return {k: pd.read_csv(p) for k, p in paths.items()}


def to_cents(df: pd.DataFrame, eur_cols: list) -> pd.DataFrame:
    """Reconstruct exact integer cents from a 2-decimal EUR column, avoiding
    binary-float comparison errors in identity checks."""
    out = df.copy()
    for col in eur_cols:
        out[col + "_cents"] = (out[col] * 100).round().astype(np.int64)
    return out

# ---------------------------------------------------------------------------
# Rule 1 — row identities to the cent
# ---------------------------------------------------------------------------

def check_rule_1_row_identities(pnl: pd.DataFrame, budget_pnl: pd.DataFrame) -> tuple:
    bad_rows = 0
    details = []
    for label, df in (("actual", pnl), ("budget", budget_pnl)):
        c = to_cents(df, ["list_price_eur", "gross_revenue", "promo_discounts", "net_revenue",
                           "material_cost", "direct_labour", "logistics_cost", "gross_profit"])
        gross_check = c["volume_units"] * c["list_price_eur_cents"] == c["gross_revenue_cents"]
        net_check = c["gross_revenue_cents"] - c["promo_discounts_cents"] == c["net_revenue_cents"]
        gp_check = (
            c["net_revenue_cents"] - c["material_cost_cents"] - c["direct_labour_cents"] - c["logistics_cost_cents"]
            == c["gross_profit_cents"]
        )
        n_bad = (~gross_check).sum() + (~net_check).sum() + (~gp_check).sum()
        bad_rows += n_bad
        details.append(f"{label}: {n_bad} identity violations across {len(df)} rows")
    passed = bad_rows == 0
    return passed, ("PASS — " if passed else "FAIL — ") + "; ".join(details)

# ---------------------------------------------------------------------------
# Rule 2 — aggregation identities (lines -> BU -> company, months -> quarters)
# ---------------------------------------------------------------------------

def check_rule_2_aggregation(pnl: pd.DataFrame) -> tuple:
    c = to_cents(pnl, ["net_revenue", "gross_profit"])
    line_sum = c["net_revenue_cents"].sum()
    bu_sum = c.groupby("bu")["net_revenue_cents"].sum().sum()
    company_sum = c.groupby("month")["net_revenue_cents"].sum().sum()

    c["quarter"] = pd.PeriodIndex(c["month"], freq="M").asfreq("Q").astype(str)
    q_sum = c.groupby("quarter")["net_revenue_cents"].sum().sum()

    passed = line_sum == bu_sum == company_sum == q_sum
    msg = (
        f"line-sum={line_sum} bu-sum={bu_sum} company-sum={company_sum} quarter-sum={q_sum}"
    )
    return passed, ("PASS — " if passed else "FAIL — ") + msg

# ---------------------------------------------------------------------------
# Rule 3 — budget completeness
# ---------------------------------------------------------------------------

def check_rule_3_budget_completeness(pnl: pd.DataFrame, budget_pnl: pd.DataFrame) -> tuple:
    actual_cells = set(zip(pnl["month"], pnl["bu"], pnl["line"]))
    budget_cells = set(zip(budget_pnl["month"], budget_pnl["bu"], budget_pnl["line"]))
    missing = actual_cells - budget_cells
    extra = budget_cells - actual_cells
    passed = len(missing) == 0 and len(extra) == 0
    msg = f"missing={len(missing)} extra={len(extra)} (of {len(actual_cells)} actual cells)"
    return passed, ("PASS — " if passed else "FAIL — ") + msg

# ---------------------------------------------------------------------------
# Rule 4 — EBITDA reconciliation
# ---------------------------------------------------------------------------

def ebitda_by_month(pnl: pd.DataFrame, opex: pd.DataFrame) -> pd.Series:
    gp = to_cents(pnl, ["gross_profit"]).groupby("month")["gross_profit_cents"].sum()
    o = to_cents(opex, ["sales_marketing", "admin_general", "other_income"])
    o = o.groupby("month")[["sales_marketing_cents", "admin_general_cents", "other_income_cents"]].sum()
    return gp - o["sales_marketing_cents"] - o["admin_general_cents"] + o["other_income_cents"]


def check_rule_4_ebitda_reconciliation(pnl: pd.DataFrame, opex: pd.DataFrame) -> tuple:
    reported = ebitda_by_month(pnl, opex)

    one_offs_cents = {m: 0 for m in reported.index}
    n1, n2 = config.NOISE_EVENTS["N1"], config.NOISE_EVENTS["N2"]
    s2 = config.S2_PARAMS
    one_offs_cents[n1["month"]] = one_offs_cents.get(n1["month"], 0) - round(n1["amount_eur"] * 100)
    one_offs_cents[n2["month"]] = one_offs_cents.get(n2["month"], 0) - round(n2["amount_eur"] * 100)
    one_offs_cents[s2["warehouse_month"]] = (
        one_offs_cents.get(s2["warehouse_month"], 0) + round(s2["warehouse_gain_eur"] * 100)
    )
    underlying = reported - pd.Series(one_offs_cents)

    # The reported-minus-one-offs identity is definitional (EBITDA is never
    # stored), so the substantive check is that the DATA contains exactly the
    # designed one-offs and nothing else: other_income must be zero in every
    # (bu, month) cell except the warehouse gain, at its designed size.
    oi = to_cents(opex, ["other_income"])
    designed = (oi["bu"] == s2["warehouse_bu"]) & (oi["month"] == s2["warehouse_month"])
    stray_cents = int(oi.loc[~designed, "other_income_cents"].abs().sum())
    gain_cents = int(oi.loc[designed, "other_income_cents"].sum())
    gain_ok = gain_cents == round(s2["warehouse_gain_eur"] * 100)

    underlying_sane = (underlying - reported).abs().max() <= abs(max(one_offs_cents.values(), key=abs))
    passed = stray_cents == 0 and gain_ok and underlying_sane
    msg = (
        f"other_income zero outside the designed one-off: {'yes' if stray_cents == 0 else f'NO ({stray_cents} stray cents)'}; "
        f"warehouse gain at designed size: {gain_ok}; "
        f"one-off months: {[m for m, v in one_offs_cents.items() if v]}"
    )
    return passed, ("PASS — " if passed else "FAIL — ") + msg

# ---------------------------------------------------------------------------
# Rule 5 — customer sums
# ---------------------------------------------------------------------------

def check_rule_5_customer_sums(pnl: pd.DataFrame, customer_revenue: pd.DataFrame) -> tuple:
    bu_from_pnl = to_cents(pnl, ["gross_revenue", "promo_discounts", "net_revenue"]).groupby(
        ["month", "bu"])[["gross_revenue_cents", "promo_discounts_cents", "net_revenue_cents"]].sum()
    bu_from_cust = to_cents(customer_revenue, ["gross_revenue", "promo_discounts", "net_revenue"]).groupby(
        ["month", "bu"])[["gross_revenue_cents", "promo_discounts_cents", "net_revenue_cents"]].sum()

    diff = (bu_from_pnl - bu_from_cust).abs().sum().sum()
    passed = diff == 0
    return passed, ("PASS — " if passed else "FAIL — ") + f"total abs cent diff = {diff}"

# ---------------------------------------------------------------------------
# Rule 6 — receivables roll-forward
# ---------------------------------------------------------------------------

def check_rule_6_receivables_rollforward(receivables: pd.DataFrame, working_capital: pd.DataFrame) -> tuple:
    r = to_cents(receivables, ["receivables_closing", "collections"])
    r = r.sort_values(["bu", "customer", "month"])
    r["opening_cents"] = r.groupby(["bu", "customer"])["receivables_closing_cents"].shift(1)

    # First month per (bu, customer) has no stored opening in this table (it lives
    # only in working_capital_monthly for the BU aggregate); check months 2..24.
    r_check = r.dropna(subset=["opening_cents"]).copy()
    r_check["opening_cents"] = r_check["opening_cents"].astype(np.int64)

    cust_rev = pd.read_csv(DATA_DIR / "customer_revenue_monthly.csv")
    cust_rev = to_cents(cust_rev, ["net_revenue"])[["month", "bu", "customer", "net_revenue_cents"]]
    r_check = r_check.merge(cust_rev, on=["month", "bu", "customer"])

    identity = (
        r_check["opening_cents"] + r_check["net_revenue_cents"] - r_check["collections_cents"]
        == r_check["receivables_closing_cents"]
    )
    n_bad_cust = (~identity).sum()

    wc = to_cents(working_capital, ["receivables_opening", "collections", "receivables_closing"])
    # BU-level identity: opening + net_revenue - collections = closing, using BU net revenue from pnl
    pnl = pd.read_csv(DATA_DIR / "pnl_monthly.csv")
    bu_net_rev = to_cents(pnl, ["net_revenue"]).groupby(["month", "bu"])["net_revenue_cents"].sum().reset_index()
    wc = wc.merge(bu_net_rev, on=["month", "bu"])
    bu_identity = (
        wc["receivables_opening_cents"] + wc["net_revenue_cents"] - wc["collections_cents"]
        == wc["receivables_closing_cents"]
    )
    n_bad_bu = (~bu_identity).sum()

    # customer receivables sum exactly to BU balance
    cust_closing = to_cents(receivables, ["receivables_closing"]).groupby(
        ["month", "bu"])["receivables_closing_cents"].sum().reset_index()
    bu_closing = to_cents(working_capital, ["receivables_closing"])[["month", "bu", "receivables_closing_cents"]]
    merged_closing = cust_closing.merge(bu_closing, on=["month", "bu"], suffixes=("_cust", "_bu"))
    sum_diff = (merged_closing["receivables_closing_cents_cust"] - merged_closing["receivables_closing_cents_bu"]).abs().sum()

    passed = n_bad_cust == 0 and n_bad_bu == 0 and sum_diff == 0
    msg = f"customer roll-forward violations={n_bad_cust}, BU roll-forward violations={n_bad_bu}, sum-to-BU cent diff={sum_diff}"
    return passed, ("PASS — " if passed else "FAIL — ") + msg

# ---------------------------------------------------------------------------
# Rule 7 — cash roll-forward
# ---------------------------------------------------------------------------

def check_rule_7_cash_rollforward(cash: pd.DataFrame) -> tuple:
    c = to_cents(cash, ["cash_opening", "operating_cash_flow", "investing_cash_flow", "cash_closing"])
    identity = (
        c["cash_opening_cents"] + c["operating_cash_flow_cents"] + c["investing_cash_flow_cents"]
        == c["cash_closing_cents"]
    )
    n_bad = (~identity).sum()

    chain = c.sort_values("month")
    chain_ok = (chain["cash_closing_cents"].iloc[:-1].values == chain["cash_opening_cents"].iloc[1:].values).all()

    s2 = config.S2_PARAMS
    icf_month = c[c["month"] == s2["warehouse_month"]]["investing_cash_flow_cents"].iloc[0]
    icf_ok = icf_month == round(s2["warehouse_proceeds_eur"] * 100)
    other_icf = c[c["month"] != s2["warehouse_month"]]["investing_cash_flow_cents"]
    icf_once = icf_ok and (other_icf == 0).all()

    opex = pd.read_csv(DATA_DIR / "opex_monthly.csv")
    gain_cents = to_cents(
        opex[(opex["bu"] == s2["warehouse_bu"]) & (opex["month"] == s2["warehouse_month"])],
        ["other_income"],
    )["other_income_cents"].iloc[0]
    gain_ok = gain_cents == round(s2["warehouse_gain_eur"] * 100)

    passed = n_bad == 0 and chain_ok and icf_once and gain_ok
    msg = (
        f"roll-forward violations={n_bad}, chained opening=closing: {chain_ok}, "
        f"warehouse ICF present exactly once at designed size: {icf_once}, "
        f"other-income gain present at designed size: {gain_ok}"
    )
    return passed, ("PASS — " if passed else "FAIL — ") + msg

# ---------------------------------------------------------------------------
# Rule 8 — story signatures at designed magnitude
# ---------------------------------------------------------------------------

def _fy(df: pd.DataFrame, year: str) -> pd.DataFrame:
    return df[df["month"].str.startswith(year)]


def check_rule_8a_s1(pnl: pd.DataFrame) -> tuple:
    s1 = config.S1_PARAMS
    bu = s1["bu"]
    fy24 = _fy(pnl[pnl["bu"] == bu], "2024")
    fy25 = _fy(pnl[pnl["bu"] == bu], "2025")

    mat24, mat25 = fy24["material_cost"].sum(), fy25["material_cost"].sum()
    material_growth = (mat25 / mat24 - 1) * 100
    material_ok = 11.0 <= material_growth <= 13.0

    nr24, nr25 = fy24["net_revenue"].sum(), fy25["net_revenue"].sum()
    revenue_growth = (nr25 / nr24 - 1) * 100
    revenue_ok = 2.0 <= revenue_growth <= 4.0

    gp24, gp25 = fy24["gross_profit"].sum(), fy25["gross_profit"].sum()
    gm24, gm25 = gp24 / nr24, gp25 / nr25
    gm_delta_pp = (gm25 - gm24) * 100
    gm_ok = -3.5 <= gm_delta_pp <= -2.5

    unit_ok = True
    unit_details = []
    for line in ["Home Care", "Skin & Body"]:
        l24 = _fy(pnl[(pnl["bu"] == bu) & (pnl["line"] == line)], "2024")
        l25 = _fy(pnl[(pnl["bu"] == bu) & (pnl["line"] == line)], "2025")
        u24 = l24["material_cost"].sum() / l24["volume_units"].sum()
        u25 = l25["material_cost"].sum() / l25["volume_units"].sum()
        change_pct = (u25 / u24 - 1) * 100
        ok = abs(change_pct) <= 0.5
        unit_ok = unit_ok and ok
        unit_details.append(f"{line} unit material cost change={change_pct:+.2f}% [{'OK' if ok else 'FAIL'}]")

    passed = material_ok and revenue_ok and gm_ok and unit_ok
    msg = (
        f"material YoY={material_growth:+.2f}% (band 11-13) [{'OK' if material_ok else 'FAIL'}], "
        f"net revenue YoY={revenue_growth:+.2f}% (band 2-4) [{'OK' if revenue_ok else 'FAIL'}], "
        f"GM delta={gm_delta_pp:+.2f}pp (band -3.5..-2.5) [{'OK' if gm_ok else 'FAIL'}]; "
        + "; ".join(unit_details)
    )
    return passed, ("PASS — " if passed else "FAIL — ") + msg


def trailing12_dso_by_bu(pnl: pd.DataFrame, working_capital: pd.DataFrame) -> pd.DataFrame:
    """DSO per BU per month = closing AR / (trailing-12-month average BU net revenue
    / 30), matching the generator's AR basis (see build_receivables docstring)."""
    months = gf.ACTUAL_MONTHS
    net_rev = pnl.groupby(["month", "bu"])["net_revenue"].sum()
    closing = working_capital.set_index(["month", "bu"])["receivables_closing"]
    rows = []
    for i, month in enumerate(months):
        window = months[max(0, i - 11):i + 1]
        for bu in config.BUS:
            trailing = np.mean([net_rev.get((m, bu), 0.0) for m in window])
            dso = closing.get((month, bu), np.nan) / (trailing / config.DAYS_IN_MONTH_APPROX) if trailing else np.nan
            rows.append({"month": month, "bu": bu, "dso": dso})
    return pd.DataFrame(rows)


def trailing12_dso_company(pnl: pd.DataFrame, working_capital: pd.DataFrame) -> pd.DataFrame:
    """Company-level analogue of trailing12_dso_by_bu."""
    months = gf.ACTUAL_MONTHS
    net_rev = pnl.groupby("month")["net_revenue"].sum()
    closing = working_capital.groupby("month")["receivables_closing"].sum()
    rows = []
    for i, month in enumerate(months):
        window = months[max(0, i - 11):i + 1]
        trailing = np.mean([net_rev.get(m, 0.0) for m in window])
        dso = closing.get(month, np.nan) / (trailing / config.DAYS_IN_MONTH_APPROX) if trailing else np.nan
        rows.append({"month": month, "dso": dso})
    return pd.DataFrame(rows)


def check_rule_8b_s2(pnl: pd.DataFrame, opex: pd.DataFrame, working_capital: pd.DataFrame,
                      cash: pd.DataFrame) -> tuple:
    s2 = config.S2_PARAMS

    # Like-for-like YoY windows: terms-based AR is seasonal, so Nov-Dec is
    # compared to Nov-Dec — the seasonal numerator cancels, the drift remains.
    ce_dso = trailing12_dso_by_bu(pnl, working_capital)
    ce_dso = ce_dso[ce_dso["bu"] == s2["bu"]]
    ce_before = ce_dso[ce_dso["month"].isin(["2024-11", "2024-12"])]["dso"].mean()
    ce_after = ce_dso[ce_dso["month"].isin(["2025-11", "2025-12"])]["dso"].mean()
    ce_delta = ce_after - ce_before
    ce_ok = ce_delta >= 15.0

    company_dso = trailing12_dso_company(pnl, working_capital)
    comp_before = company_dso[company_dso["month"].isin(["2024-11", "2024-12"])]["dso"].mean()
    comp_after = company_dso[company_dso["month"].isin(["2025-11", "2025-12"])]["dso"].mean()
    comp_delta = comp_after - comp_before
    comp_ok = comp_delta >= 4.0

    ebitda = ebitda_by_month(pnl, opex) / 100.0   # back to EUR
    one_off_month = s2["warehouse_month"]
    ebitda_underlying = ebitda.copy()
    ebitda_underlying.loc[one_off_month] -= s2["warehouse_gain_eur"]

    ocf = cash.set_index("month")["operating_cash_flow"]
    ocf_underlying = ocf.copy()
    ocf_underlying.loc[one_off_month] -= s2["warehouse_gain_eur"]

    h1_24 = [m for m in gf.ACTUAL_MONTHS if m.startswith("2024") and m <= "2024-06"]
    h1_25 = [m for m in gf.ACTUAL_MONTHS if m.startswith("2025") and m <= "2025-06"]
    conv_24_reported = ocf.loc[h1_24].sum() / ebitda.loc[h1_24].sum()
    conv_25_underlying = ocf_underlying.loc[h1_25].sum() / ebitda_underlying.loc[h1_25].sum()
    conversion_fall_pp = (conv_24_reported - conv_25_underlying) * 100
    conversion_ok = conversion_fall_pp >= 15.0

    cash_stable = (cash["cash_closing"] >= cash["cash_opening"].iloc[0] * 0.95).all()

    passed = ce_ok and comp_ok and conversion_ok and cash_stable
    msg = (
        f"BU DSO change={ce_delta:+.1f}d (need >=15) [{'OK' if ce_ok else 'FAIL'}], "
        f"company DSO change={comp_delta:+.1f}d (need >=4) [{'OK' if comp_ok else 'FAIL'}], "
        f"H1 cash conversion {conv_24_reported*100:.1f}% (2024 reported) -> "
        f"{conv_25_underlying*100:.1f}% (2025 underlying), fall={conversion_fall_pp:.1f}pp "
        f"(need >=15) [{'OK' if conversion_ok else 'FAIL'}], "
        f"cash stable throughout: {cash_stable}"
    )
    return passed, ("PASS — " if passed else "FAIL — ") + msg


def check_rule_8c_s3(pnl: pd.DataFrame, customer_revenue: pd.DataFrame) -> tuple:
    s3 = config.S3_PARAMS
    bu = s3["bu"]

    jan_rate = gf.s3_discount_rate("2025-01")
    dec_rate = gf.s3_discount_rate("2025-12")
    path_ok = 0.06 <= jan_rate <= 0.10 and 0.13 <= dec_rate <= 0.20

    dec_customers = customer_revenue[(customer_revenue["bu"] == bu) & (customer_revenue["month"] == "2025-12")].copy()
    dec_customers["own_rate"] = dec_customers["promo_discounts"] / dec_customers["gross_revenue"]
    named = dec_customers[dec_customers["customer"] != "Other"]
    n_above_18 = (named["own_rate"] > 0.18).sum()
    accounts_ok = n_above_18 >= 3

    fy24_gm = _fy(pnl[pnl["bu"] == bu], "2024")
    fy24_gm_pct = fy24_gm["gross_profit"].sum() / fy24_gm["net_revenue"].sum()
    q4 = pnl[(pnl["bu"] == bu) & (pnl["month"].isin(["2025-10", "2025-11", "2025-12"]))]
    q4_gm_pct = q4["gross_profit"].sum() / q4["net_revenue"].sum()
    erosion_pp = (fy24_gm_pct - q4_gm_pct) * 100
    erosion_ok = erosion_pp >= 4.0

    company24 = _fy(pnl, "2024")["net_revenue"].sum()
    company25 = _fy(pnl, "2025")["net_revenue"].sum()
    company_growth = (company25 / company24 - 1) * 100
    company_ok = 7.0 <= company_growth <= 9.0

    def half_response(months: list) -> float:
        delta_vol, delta_disc_eur = 0.0, 0.0
        for month in months:
            t = gf.MONTH_INDEX[month]
            for line in config.LINES:
                normal = gf.normal_driver(bu, line, t)
                story = gf.apply_s3(bu, line, month, dict(normal))
                normal_gross = normal["volume"] * normal["price_cents"] / 100.0
                story_gross = story["volume"] * story["price_cents"] / 100.0
                delta_vol += story["volume"] - normal["volume"]
                delta_disc_eur += story_gross * story["discount_rate"] - normal_gross * normal["discount_rate"]
        return delta_vol / delta_disc_eur if delta_disc_eur else np.nan

    h1_months = [m for m in gf.ACTUAL_MONTHS if "2025-01" <= m <= "2025-06"]
    h2_months = [m for m in gf.ACTUAL_MONTHS if "2025-07" <= m <= "2025-12"]
    h1_response = half_response(h1_months)
    h2_response = half_response(h2_months)
    fade_pct = (1 - h2_response / h1_response) * 100 if h1_response else np.nan
    fade_ok = fade_pct >= 30.0

    passed = path_ok and accounts_ok and erosion_ok and company_ok and fade_ok
    msg = (
        f"discount path Jan={jan_rate*100:.1f}% Dec={dec_rate*100:.1f}% [{'OK' if path_ok else 'FAIL'}], "
        f"accounts >18% discount in Dec-2025={n_above_18} (need >=3) [{'OK' if accounts_ok else 'FAIL'}], "
        f"GM erosion (FY24 avg vs Q4-25 avg)={erosion_pp:.2f}pp (need >=4) [{'OK' if erosion_ok else 'FAIL'}], "
        f"company FY2025 revenue growth={company_growth:+.2f}% (band 7-9) [{'OK' if company_ok else 'FAIL'}], "
        f"H1 response={h1_response:.3f} units/EUR, H2 response={h2_response:.3f} units/EUR, "
        f"H2 weaker by {fade_pct:.1f}% (need >=30) [{'OK' if fade_ok else 'FAIL'}]"
    )
    return passed, ("PASS — " if passed else "FAIL — ") + msg


def company_seasonal_index(pnl: pd.DataFrame, year: str) -> pd.Series:
    by_month = _fy(pnl, year).groupby("month")["net_revenue"].sum()
    return by_month / by_month.mean()


def check_rule_8d_s4(pnl: pd.DataFrame, budget_pnl: pd.DataFrame) -> tuple:
    idx24 = company_seasonal_index(pnl, "2024")
    idx25 = company_seasonal_index(pnl, "2025")
    idx25_budget = company_seasonal_index(budget_pnl, "2025")

    def band_ok(idx: pd.Series) -> bool:
        dec = idx[idx.index.str.endswith("-12")].iloc[0]
        jan = idx[idx.index.str.endswith("-01")].iloc[0]
        return (1.10 <= dec <= 1.30) and (0.75 <= jan <= 0.95)

    bands_ok = band_ok(idx24) and band_ok(idx25) and band_ok(idx25_budget)

    actual_jan = pnl[pnl["month"] == "2025-01"]["net_revenue"].sum()
    budget_jan = budget_pnl[budget_pnl["month"] == "2025-01"]["net_revenue"].sum()
    variance_pct = (actual_jan / budget_jan - 1) * 100
    variance_ok = abs(variance_pct) <= 2.0

    passed = bands_ok and variance_ok
    msg = (
        f"Dec/Jan index 2024=({idx24[idx24.index.str.endswith('-12')].iloc[0]:.3f}/"
        f"{idx24[idx24.index.str.endswith('-01')].iloc[0]:.3f}) "
        f"2025=({idx25[idx25.index.str.endswith('-12')].iloc[0]:.3f}/"
        f"{idx25[idx25.index.str.endswith('-01')].iloc[0]:.3f}) "
        f"budget=({idx25_budget[idx25_budget.index.str.endswith('-12')].iloc[0]:.3f}/"
        f"{idx25_budget[idx25_budget.index.str.endswith('-01')].iloc[0]:.3f}) "
        f"[{'OK' if bands_ok else 'FAIL'}]; "
        f"Jan-2025 vs budget variance={variance_pct:+.2f}% (band +/-2) [{'OK' if variance_ok else 'FAIL'}]"
    )
    return passed, ("PASS — " if passed else "FAIL — ") + msg


def check_rule_8_story_signatures(pnl, budget_pnl, opex, working_capital, cash, customer_revenue) -> tuple:
    r1 = check_rule_8a_s1(pnl)
    r2 = check_rule_8b_s2(pnl, opex, working_capital, cash)
    r3 = check_rule_8c_s3(pnl, customer_revenue)
    r4 = check_rule_8d_s4(pnl, budget_pnl)
    passed = r1[0] and r2[0] and r3[0] and r4[0]
    msg = f"S1: {r1[1]} || S2: {r2[1]} || S3: {r3[1]} || S4: {r4[1]}"
    return passed, ("PASS" if passed else "FAIL") + " — see per-story detail above", (r1, r2, r3, r4)

# ---------------------------------------------------------------------------
# Rule 9 — noise ceiling
# ---------------------------------------------------------------------------

def _story_monthly_gp_impacts(pnl: pd.DataFrame, bu: str, lines: list, months: list) -> list:
    impacts = []
    for month in months:
        t = gf.MONTH_INDEX[month]
        impact_cents = 0
        for line in lines:
            d = gf.normal_driver(bu, line, t)
            volume = round(d["volume"])
            price = round(d["price_cents"])
            gross = volume * price
            disc = round(gross * d["discount_rate"])
            net = gross - disc
            mat = volume * round(d["material_cents"])
            lab = volume * round(d["labour_cents"])
            log = volume * round(d["logistics_cents"])
            cf_gp_cents = net - mat - lab - log
            actual_gp_cents = round(
                pnl[(pnl["month"] == month) & (pnl["bu"] == bu) & (pnl["line"] == line)]["gross_profit"].iloc[0] * 100
            )
            impact_cents += actual_gp_cents - cf_gp_cents
        impacts.append(impact_cents / 100.0)
    return impacts


def check_rule_9_noise_ceiling(pnl: pd.DataFrame) -> tuple:
    s1, s3 = config.S1_PARAMS, config.S3_PARAMS
    s1_months = [m for m in gf.ACTUAL_MONTHS if s1["start_month"] <= m <= s1["end_month"]]
    s3_months = [m for m in gf.ACTUAL_MONTHS if s3["start_month"] <= m <= s3["end_month"]]

    s1_impacts = np.abs(_story_monthly_gp_impacts(pnl, s1["bu"], ["Home Care", "Skin & Body"], s1_months))
    s3_impacts = np.abs(_story_monthly_gp_impacts(pnl, s3["bu"], config.LINES, s3_months))

    smallest_story_median = min(np.median(s1_impacts), np.median(s3_impacts))
    ceiling = 0.6 * smallest_story_median

    n1 = config.NOISE_EVENTS["N1"]
    n1_ok = n1["amount_eur"] <= ceiling

    # N1's realised size: compare actual Nordics total logistics_cost that month to
    # the noiseless counterfactual (normal_driver, no N1). Using logistics_cost alone
    # (rather than full gross profit) avoids compounding unrelated volume/price/other-
    # cost noise into the check. A single BU-month cell still carries background
    # volume and unit-cost noise on top of the N1 addition (see config
    # NOISE_SIGMA_VOLUME / NOISE_SIGMA_UNIT_COST) — roughly a few thousand euros of
    # standard deviation here — so the tolerance is set well above that and well
    # below N1's own size, wide enough to absorb noise but tight enough to still be
    # a real check that N1 landed at roughly its designed size.
    n1_month_rows = pnl[(pnl["bu"] == n1["bu"]) & (pnl["month"] == n1["month"])]
    actual_logistics = n1_month_rows["logistics_cost"].sum()
    t_n1 = gf.MONTH_INDEX[n1["month"]]
    counterfactual_logistics = sum(
        round(gf.normal_driver(n1["bu"], line, t_n1)["volume"])
        * round(gf.normal_driver(n1["bu"], line, t_n1)["logistics_cents"])
        for line in config.LINES
    ) / 100.0
    n1_gp_impact = actual_logistics - counterfactual_logistics
    n1_tolerance = max(25_000.0, 0.35 * n1["amount_eur"])
    n1_size_ok = abs(n1_gp_impact - n1["amount_eur"]) <= n1_tolerance

    n2 = config.NOISE_EVENTS["N2"]
    opex = pd.read_csv(DATA_DIR / "opex_monthly.csv")
    n2_row = opex[(opex["bu"] == n2["bu"]) & (opex["month"] == n2["month"])]
    baseline_admin_rate = config.ADMIN_PCT_OF_NET_REVENUE
    pnl_n2 = pnl[(pnl["bu"] == n2["bu"]) & (pnl["month"] == n2["month"])]
    baseline_admin = pnl_n2["net_revenue"].sum() * baseline_admin_rate
    # Tolerance must sit above the admin-rate noise (sigma 1.5% of ~EUR 0.9M
    # baseline => ~EUR 13.5k std) but comfortably below N2's own EUR 90k size,
    # so the check FAILS if N2 is absent — a percentage-of-baseline tolerance
    # (~EUR 135k) was wider than the event itself and could never fail.
    n2_size_ok = abs((n2_row["admin_general"].iloc[0] - baseline_admin) - n2["amount_eur"]) <= 45_000

    # N3 (list-price step): each month's list_price carries its own independent
    # NOISE_SIGMA_PRICE draw, so a single line's June-vs-July ratio is two noisy
    # observations. Averaging the ratio across all four lines cuts the noise to
    # ~0.3%, which lets the tolerance (0.008) sit below the 2% step itself — a
    # single-line tolerance of 0.02 equalled the step and could pass with N3
    # absent.
    n3 = config.NOISE_EVENTS["N3"]
    ratios = []
    for line in config.LINES:
        before = pnl[(pnl["bu"] == n3["bu"]) & (pnl["month"] == "2025-06") & (pnl["line"] == line)]["list_price_eur"].iloc[0]
        after = pnl[(pnl["bu"] == n3["bu"]) & (pnl["month"] == "2025-07") & (pnl["line"] == line)]["list_price_eur"].iloc[0]
        ratios.append(after / before)
    trend_m = config.annual_to_monthly(config.LINE_PRICE_TREND_ANNUAL["Hair Care"])
    n3_ok = abs(np.mean(ratios) / (1 + trend_m) - n3["list_price_multiplier"]) <= 0.008

    passed = n1_ok and n1_size_ok and n2_size_ok and n3_ok
    msg = (
        f"smallest story median monthly GP impact=EUR {smallest_story_median:,.0f} "
        f"(S1 median={np.median(s1_impacts):,.0f}, S3 median={np.median(s3_impacts):,.0f}), "
        f"60% ceiling=EUR {ceiling:,.0f}; N1=EUR {n1['amount_eur']:,.0f} [{'OK' if n1_ok else 'FAIL'}]; "
        f"N1 realised GP impact matches designed size: {n1_size_ok}; "
        f"N2 realised admin one-off matches designed size (within tolerance): {n2_size_ok}; "
        f"N3 CE list-price step matches designed x{n3['list_price_multiplier']}: {n3_ok}"
    )
    return passed, ("PASS — " if passed else "FAIL — ") + msg

# ---------------------------------------------------------------------------
# Rule 10 — seasonality consistency (budget vs generator index)
# ---------------------------------------------------------------------------

def check_rule_10_seasonality_consistency(pnl: pd.DataFrame, budget_pnl: pd.DataFrame) -> tuple:
    idx_actual = company_seasonal_index(pnl, "2024")
    idx_budget = company_seasonal_index(budget_pnl, "2024")
    diff = (idx_actual - idx_budget).abs().max()
    passed = diff <= 0.03
    return passed, ("PASS — " if passed else "FAIL — ") + f"max |actual-budget| seasonal index diff (FY2024) = {diff:.4f} (band <=0.03)"

# ---------------------------------------------------------------------------
# Rule 11 — headcount and labour coherence
# ---------------------------------------------------------------------------

def check_rule_11_headcount_labour(pnl: pd.DataFrame, opex: pd.DataFrame) -> tuple:
    bu_month = pnl.groupby(["month", "bu"]).agg(
        volume=("volume_units", "sum"), labour=("direct_labour", "sum"), net_revenue=("net_revenue", "sum")
    ).reset_index()
    corr_ok = True
    corr_details = []
    for bu in config.BUS:
        sub = bu_month[bu_month["bu"] == bu]
        corr = np.corrcoef(sub["volume"], sub["labour"])[0, 1]
        ok = corr >= 0.75
        corr_ok = corr_ok and ok
        corr_details.append(f"{bu} volume/labour corr={corr:.3f} [{'OK' if ok else 'FAIL'}]")

    hc = opex.sort_values(["bu", "month"]).copy()
    hc["delta_pct"] = hc.groupby("bu")["headcount_fte"].pct_change().abs()
    smooth_ok = (hc["delta_pct"].dropna() <= 0.03).all()

    total_net_rev_fy24 = pnl[pnl["month"].str.startswith("2024")]["net_revenue"].sum()
    total_fte_fy24 = opex[opex["month"].str.startswith("2024")].groupby("month")["headcount_fte"].sum().mean()
    revenue_per_head = total_net_rev_fy24 / total_fte_fy24
    band_ok = 150_000 <= revenue_per_head <= 500_000

    passed = corr_ok and smooth_ok and band_ok
    msg = (
        "; ".join(corr_details)
        + f"; headcount smooth (all |MoM % change| <= 3%): {smooth_ok}"
        + f"; FY2024 revenue/head=EUR {revenue_per_head:,.0f} (band 150k-500k) [{'OK' if band_ok else 'FAIL'}]"
    )
    return passed, ("PASS — " if passed else "FAIL — ") + msg

# ---------------------------------------------------------------------------
# Rule 12 — format
# ---------------------------------------------------------------------------

def check_rule_12_format(pnl: pd.DataFrame) -> tuple:
    months = sorted(pnl["month"].unique())
    expected = gf.ACTUAL_MONTHS
    months_ok = months == expected and len(months) == 24

    nulls = {}
    for name, path in [
        ("pnl_monthly", "pnl_monthly.csv"), ("opex_monthly", "opex_monthly.csv"),
        ("customer_master", "customer_master.csv"), ("customer_revenue_monthly", "customer_revenue_monthly.csv"),
        ("working_capital_monthly", "working_capital_monthly.csv"),
        ("receivables_by_customer_monthly", "receivables_by_customer_monthly.csv"),
        ("cash_monthly", "cash_monthly.csv"), ("budget_pnl_monthly", "budget_pnl_monthly.csv"),
        ("budget_opex_monthly", "budget_opex_monthly.csv"), ("stories", "answer_key/stories.csv"),
    ]:
        df = pd.read_csv(DATA_DIR / path)
        n_null = df.isna().sum().sum()
        if n_null:
            nulls[name] = int(n_null)

    passed = months_ok and not nulls
    msg = f"24 ISO months present and exact: {months_ok}; unexpected nulls: {nulls if nulls else 'none'}"
    return passed, ("PASS — " if passed else "FAIL — ") + msg

# ---------------------------------------------------------------------------
# Main report
# ---------------------------------------------------------------------------

def main():
    print("=" * 78)
    print(f"{config.COMPANY_NAME} — Financial Data Coherence Validation Report")
    print("=" * 78)

    print("\nLoading data...")
    d = load_data()
    for name, df in d.items():
        print(f"  {name}: {len(df):,} rows")

    results = []

    print("\n--- Rule 1: Row identities to the cent ---")
    passed, msg = check_rule_1_row_identities(d["pnl"], d["budget_pnl"])
    print(f"  {msg}")
    results.append(("Rule 1 (row identities)", passed))

    print("\n--- Rule 2: Aggregation identities ---")
    passed, msg = check_rule_2_aggregation(d["pnl"])
    print(f"  {msg}")
    results.append(("Rule 2 (aggregation)", passed))

    print("\n--- Rule 3: Budget completeness ---")
    passed, msg = check_rule_3_budget_completeness(d["pnl"], d["budget_pnl"])
    print(f"  {msg}")
    results.append(("Rule 3 (budget completeness)", passed))

    print("\n--- Rule 4: EBITDA reconciliation ---")
    passed, msg = check_rule_4_ebitda_reconciliation(d["pnl"], d["opex"])
    print(f"  {msg}")
    results.append(("Rule 4 (EBITDA reconciliation)", passed))

    print("\n--- Rule 5: Customer sums ---")
    passed, msg = check_rule_5_customer_sums(d["pnl"], d["customer_revenue"])
    print(f"  {msg}")
    results.append(("Rule 5 (customer sums)", passed))

    print("\n--- Rule 6: Receivables roll-forward ---")
    passed, msg = check_rule_6_receivables_rollforward(d["receivables"], d["working_capital"])
    print(f"  {msg}")
    results.append(("Rule 6 (receivables roll-forward)", passed))

    print("\n--- Rule 7: Cash roll-forward ---")
    passed, msg = check_rule_7_cash_rollforward(d["cash"])
    print(f"  {msg}")
    results.append(("Rule 7 (cash roll-forward)", passed))

    print("\n--- Rule 8: Story signatures at designed magnitude ---")
    passed, msg, detail = check_rule_8_story_signatures(
        d["pnl"], d["budget_pnl"], d["opex"], d["working_capital"], d["cash"], d["customer_revenue"]
    )
    for label, (p, m) in zip(["S1", "S2", "S3", "S4"], detail):
        print(f"  [{label}] {'PASS' if p else 'FAIL'} — {m}")
    results.append(("Rule 8 (story signatures)", passed))

    print("\n--- Rule 9: Noise ceiling ---")
    passed, msg = check_rule_9_noise_ceiling(d["pnl"])
    print(f"  {msg}")
    results.append(("Rule 9 (noise ceiling)", passed))

    print("\n--- Rule 10: Seasonality consistency (budget vs actual index) ---")
    passed, msg = check_rule_10_seasonality_consistency(d["pnl"], d["budget_pnl"])
    print(f"  {msg}")
    results.append(("Rule 10 (seasonality consistency)", passed))

    print("\n--- Rule 11: Headcount and labour coherence ---")
    passed, msg = check_rule_11_headcount_labour(d["pnl"], d["opex"])
    print(f"  {msg}")
    results.append(("Rule 11 (headcount/labour)", passed))

    print("\n--- Rule 12: Format ---")
    passed, msg = check_rule_12_format(d["pnl"])
    print(f"  {msg}")
    results.append(("Rule 12 (format)", passed))

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    all_passed = True
    for rule_name, rule_passed in results:
        status = "PASS" if rule_passed else "FAIL"
        print(f"  {rule_name}: {status}")
        all_passed = all_passed and rule_passed

    print()
    if all_passed:
        print("ALL RULES PASSED — dataset is coherent and ready for analysis.")
        print("=" * 78)
        sys.exit(0)
    else:
        failed = [r for r, p in results if not p]
        print(f"FAILED RULES: {failed}")
        print("=" * 78)
        sys.exit(1)


if __name__ == "__main__":
    main()
