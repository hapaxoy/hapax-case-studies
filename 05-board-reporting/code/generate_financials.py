"""
generate_financials.py — Driver-based synthetic financial dataset for
Paju Consumer Products Oy (Case Study 5, Board Reporting Automation).

Inputs:  code/config.py (every tunable — grid, trends, seasonality, story
         and noise-ledger parameters, budget assumptions, customer rosters).
Outputs: data/pnl_monthly.csv, data/opex_monthly.csv,
         data/customer_master.csv, data/customer_revenue_monthly.csv,
         data/working_capital_monthly.csv,
         data/receivables_by_customer_monthly.csv, data/cash_monthly.csv,
         data/budget_pnl_monthly.csv, data/budget_opex_monthly.csv,
         data/answer_key/stories.csv.

Rationale: the model generates *drivers* (volume, list
price, discount rate, unit material/labour/logistics cost, opex ratios,
headcount, customer revenue shares, payment terms), never a total
independently of its parts. Every monetary value is computed and held in
integer cents at leaf grain (a pnl_monthly row = one month x BU x line);
every aggregate is a sum of those cents. CSVs are written with money in EUR
at exactly 2 decimals; volumes and headcount are integer units.

The internal driver model spans 36 months (2023-01 .. 2025-12): FY2023 is
never emitted as a table but is the "prior year" every FY2024 budget cell is
grown from, exactly as FY2024 is the prior year FY2025's budget is grown
from. Budgets are the same trend-and-seasonality model plus a small,
deliberate optimism bias — no noise, no story overlay, no one-off events —
which is what gives budget-vs-actual variance a genuine cause (noise, a
story, or nothing) rather than being definitionally hollow.

Run from the project root:
    python code/generate_financials.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
ANSWER_KEY_DIR = DATA_DIR / "answer_key"

sys.path.insert(0, str(SCRIPT_DIR))
import config

assert DATA_DIR.resolve() != SCRIPT_DIR.resolve(), "output dir must differ from code dir"

# ---------------------------------------------------------------------------
# Calendar / time-index helpers
# ---------------------------------------------------------------------------

def month_range(start: str, end: str) -> list:
    return [str(p) for p in pd.period_range(start=start, end=end, freq="M")]

ALL_MONTHS = month_range(config.DRIVER_MODEL_START, config.DRIVER_MODEL_END)   # 36 months
MONTH_INDEX = {m: t for t, m in enumerate(ALL_MONTHS)}
ACTUAL_MONTHS = month_range(config.OBS_START, config.OBS_END)                  # 24 months

assert len(ACTUAL_MONTHS) == 24, "actual window must be exactly 24 months (rule 12)"


def calendar_month(month: str) -> int:
    return int(month[5:7])


def calendar_year(month: str) -> int:
    return int(month[0:4])

# ---------------------------------------------------------------------------
# Trend rates (annual -> monthly, compounded)
# ---------------------------------------------------------------------------

LINE_VOLUME_TREND_M = {ln: config.annual_to_monthly(r) for ln, r in config.LINE_VOLUME_TREND_ANNUAL.items()}
LINE_PRICE_TREND_M  = {ln: config.annual_to_monthly(r) for ln, r in config.LINE_PRICE_TREND_ANNUAL.items()}
MATERIAL_TREND_M    = config.annual_to_monthly(config.MATERIAL_COST_TREND_ANNUAL)
LABOUR_TREND_M       = config.annual_to_monthly(config.LABOUR_COST_TREND_ANNUAL)
LOGISTICS_TREND_M    = config.annual_to_monthly(config.LOGISTICS_COST_TREND_ANNUAL)
HEADCOUNT_TREND_M    = config.annual_to_monthly(config.HEADCOUNT_GROWTH_ANNUAL)

# ---------------------------------------------------------------------------
# Normal (no-story, no-noise) driver model — shared by actuals and budget
# ---------------------------------------------------------------------------

def bu_price_multiplier(bu: str, month: str) -> float:
    """N3: Central Europe list prices step +2% from July 2025, permanently."""
    n3 = config.NOISE_EVENTS["N3"]
    if bu == n3["bu"] and month >= n3["month"]:
        return n3["list_price_multiplier"]
    return 1.0


def normal_driver(bu: str, line: str, t: int) -> dict:
    """Trend + seasonality only — no story overlay, no random noise."""
    month = ALL_MONTHS[t]
    seasonal = config.SEASONAL_INDEX_BY_LINE[line][calendar_month(month)]

    volume = config.BASE_VOLUME_FY2023[bu][line] * (1 + LINE_VOLUME_TREND_M[line]) ** t * seasonal
    price_cents = (
        config.LINE_BASE_LIST_PRICE_CENTS_FY2023[line]
        * (1 + LINE_PRICE_TREND_M[line]) ** t
        * bu_price_multiplier(bu, month)
    )
    discount_rate = config.BASELINE_DISCOUNT_RATE_BY_BU[bu]
    material_cents  = config.UNIT_MATERIAL_COST_CENTS_FY2023[line]  * (1 + MATERIAL_TREND_M) ** t
    labour_cents    = config.UNIT_LABOUR_COST_CENTS_FY2023[line]    * (1 + LABOUR_TREND_M) ** t
    logistics_cents = config.UNIT_LOGISTICS_COST_CENTS_FY2023[line] * (1 + LOGISTICS_TREND_M) ** t

    return {
        "volume": volume,
        "price_cents": price_cents,
        "discount_rate": discount_rate,
        "material_cents": material_cents,
        "labour_cents": labour_cents,
        "logistics_cents": logistics_cents,
    }


def ramp_value(month: str, start_month: str, end_month: str, start_val: float, end_val: float) -> float:
    """Linear interpolation of a value between two months, held flat outside the window."""
    if month <= start_month:
        return start_val
    if month >= end_month:
        return end_val
    t0, t1, t = MONTH_INDEX[start_month], MONTH_INDEX[end_month], MONTH_INDEX[month]
    frac = (t - t0) / (t1 - t0)
    return start_val + frac * (end_val - start_val)


def apply_s1(bu: str, line: str, month: str, driver: dict) -> dict:
    """S1 — mix shift + promotional pricing, Nordics Home Care / Skin & Body, Feb 2025 on."""
    p = config.S1_PARAMS
    if bu != p["bu"] or not (p["start_month"] <= month <= p["end_month"]):
        return driver
    d = dict(driver)
    if line == "Home Care":
        d["volume"] *= p["home_care_volume_multiplier"]
        d["discount_rate"] = p["home_care_promo_discount_rate"]
    elif line == "Skin & Body":
        d["volume"] *= p["skin_body_volume_multiplier"]
    return d


def s3_discount_rate(month: str) -> float:
    """Plain linear ramp from discount_start_rate (Jan 2025) to discount_end_rate
    (Dec 2025; 17% as calibrated). Early
    months sit barely above the 8% baseline by design, which is why rule 9 reads
    story impact as a median across active months rather than a minimum."""
    p = config.S3_PARAMS
    return ramp_value(month, p["start_month"], p["discount_ramp_end_month"],
                       p["discount_start_rate"], p["discount_end_rate"])


def apply_s3(bu: str, line: str, month: str, driver: dict) -> dict:
    """S3 — escalating discount + fading volume elasticity, Baltics & Poland, all lines, 2025."""
    p = config.S3_PARAMS
    if bu != p["bu"] or not (p["start_month"] <= month <= p["end_month"]):
        return driver
    d = dict(driver)
    discount_rate = s3_discount_rate(month)
    incremental = discount_rate - p["discount_start_rate"]
    elasticity = p["elasticity_h1"] if calendar_month(month) <= 6 else p["elasticity_h1"] * p["elasticity_h2_ratio"]
    d["discount_rate"] = discount_rate
    d["volume"] *= (1 + elasticity * incremental)
    return d


def budget_driver(bu: str, line: str, t: int) -> dict:
    """Budget = normal driver for the same calendar month (already the 'prior-year
    driver grown by trend' by construction of the exponential trend model) plus a
    small optimism bias. No noise, no story, no one-off events."""
    d = dict(normal_driver(bu, line, t))
    d["volume"] *= (1 + config.BUDGET_OPTIMISM_VOLUME)
    d["price_cents"] *= (1 + config.BUDGET_OPTIMISM_PRICE)
    d["discount_rate"] *= (1 + config.BUDGET_OPTIMISM_DISCOUNT)
    d["material_cents"] *= (1 + config.BUDGET_OPTIMISM_UNIT_COST)
    d["labour_cents"] *= (1 + config.BUDGET_OPTIMISM_UNIT_COST)
    d["logistics_cents"] *= (1 + config.BUDGET_OPTIMISM_UNIT_COST)
    return d

# ---------------------------------------------------------------------------
# Cents-exact helpers
# ---------------------------------------------------------------------------

def allocate_largest_remainder(total_cents: int, weights: list) -> list:
    """Split total_cents across len(weights) buckets proportional to weights,
    summing back to exactly total_cents (largest-remainder method)."""
    n = len(weights)
    weight_sum = sum(weights)
    if total_cents == 0 or weight_sum <= 0:
        return [0] * n
    raw = [total_cents * w / weight_sum for w in weights]
    floors = [int(np.floor(x)) for x in raw]
    remainder = total_cents - sum(floors)
    order = sorted(range(n), key=lambda i: (raw[i] - floors[i]), reverse=True)
    result = list(floors)
    for i in range(remainder):
        result[order[i % n]] += 1
    return result


def pnl_identity_row(volume_units: int, list_price_cents: int, discount_rate: float,
                      unit_material_cents: int, unit_labour_cents: int, unit_logistics_cents: int) -> dict:
    """Compute a full pnl leaf row from realised (already-rounded) integer drivers."""
    gross_revenue_cents = volume_units * list_price_cents
    promo_discounts_cents = round(gross_revenue_cents * discount_rate)
    net_revenue_cents = gross_revenue_cents - promo_discounts_cents
    material_cost_cents = volume_units * unit_material_cents
    direct_labour_cents = volume_units * unit_labour_cents
    logistics_cost_cents = volume_units * unit_logistics_cents
    gross_profit_cents = net_revenue_cents - material_cost_cents - direct_labour_cents - logistics_cost_cents
    return {
        "volume_units": volume_units,
        "list_price_cents": list_price_cents,
        "gross_revenue_cents": gross_revenue_cents,
        "promo_discounts_cents": promo_discounts_cents,
        "net_revenue_cents": net_revenue_cents,
        "material_cost_cents": material_cost_cents,
        "direct_labour_cents": direct_labour_cents,
        "logistics_cost_cents": logistics_cost_cents,
        "gross_profit_cents": gross_profit_cents,
    }

# ---------------------------------------------------------------------------
# pnl_monthly (actual) and budget_pnl_monthly
# ---------------------------------------------------------------------------

def build_pnl_actual(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for month in ACTUAL_MONTHS:
        t = MONTH_INDEX[month]
        for bu in config.BUS:
            for line in config.LINES:
                d = normal_driver(bu, line, t)
                d = apply_s1(bu, line, month, d)
                d = apply_s3(bu, line, month, d)

                volume_noisy = d["volume"] * (1 + rng.normal(0, config.NOISE_SIGMA_VOLUME))
                price_noisy = d["price_cents"] * (1 + rng.normal(0, config.NOISE_SIGMA_PRICE))
                discount_noisy = d["discount_rate"] + rng.normal(0, config.NOISE_SIGMA_DISCOUNT_ABS)
                discount_noisy = min(max(discount_noisy, 0.0), 0.90)
                material_noisy = d["material_cents"] * (1 + rng.normal(0, config.NOISE_SIGMA_UNIT_COST))
                labour_noisy = d["labour_cents"] * (1 + rng.normal(0, config.NOISE_SIGMA_UNIT_COST))
                logistics_noisy = d["logistics_cents"] * (1 + rng.normal(0, config.NOISE_SIGMA_UNIT_COST))

                row = pnl_identity_row(
                    volume_units=max(0, round(volume_noisy)),
                    list_price_cents=max(1, round(price_noisy)),
                    discount_rate=discount_noisy,
                    unit_material_cents=max(0, round(material_noisy)),
                    unit_labour_cents=max(0, round(labour_noisy)),
                    unit_logistics_cents=max(0, round(logistics_noisy)),
                )
                row.update({"month": month, "bu": bu, "line": line})
                rows.append(row)

    df = pd.DataFrame(rows)

    # N1 — logistics cost spike, Nordics, Feb 2024: allocated across the 4 Nordics
    # lines proportional to that month's logistics cost (a general disruption, not
    # line-specific), then gross_profit is recomputed for the affected rows.
    n1 = config.NOISE_EVENTS["N1"]
    mask = (df["bu"] == n1["bu"]) & (df["month"] == n1["month"])
    weights = df.loc[mask].sort_values("line", key=lambda s: s.map({l: i for i, l in enumerate(config.LINES)}))
    weights = weights.set_index("line").loc[config.LINES, "logistics_cost_cents"].tolist()
    add_cents = allocate_largest_remainder(round(n1["amount_eur"] * 100), weights)
    for line, add in zip(config.LINES, add_cents):
        row_mask = mask & (df["line"] == line)
        df.loc[row_mask, "logistics_cost_cents"] += add
        df.loc[row_mask, "gross_profit_cents"] -= add

    # Row order is already month -> bu -> line (construction order above); the N1
    # adjustment only mutates values in place via boolean masks, so no re-sort needed.
    return df


def build_pnl_budget() -> pd.DataFrame:
    rows = []
    for month in ACTUAL_MONTHS:
        t = MONTH_INDEX[month]
        for bu in config.BUS:
            for line in config.LINES:
                d = budget_driver(bu, line, t)
                row = pnl_identity_row(
                    volume_units=max(0, round(d["volume"])),
                    list_price_cents=max(1, round(d["price_cents"])),
                    discount_rate=min(max(d["discount_rate"], 0.0), 0.90),
                    unit_material_cents=max(0, round(d["material_cents"])),
                    unit_labour_cents=max(0, round(d["labour_cents"])),
                    unit_logistics_cents=max(0, round(d["logistics_cents"])),
                )
                row.update({"month": month, "bu": bu, "line": line})
                rows.append(row)
    return pd.DataFrame(rows)

# ---------------------------------------------------------------------------
# opex_monthly (actual) and budget_opex_monthly
# ---------------------------------------------------------------------------

def bu_base_fte(bu: str) -> float:
    return config.TOTAL_FTE_FY2023 * config.BU_SHARE[bu]


def build_opex_actual(pnl_actual: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    bu_net_revenue = pnl_actual.groupby(["month", "bu"])["net_revenue_cents"].sum()
    n2 = config.NOISE_EVENTS["N2"]
    s2 = config.S2_PARAMS

    rows = []
    for month in ACTUAL_MONTHS:
        t = MONTH_INDEX[month]
        for bu in config.BUS:
            net_rev_cents = int(bu_net_revenue.loc[(month, bu)])
            sm_rate = config.SM_PCT_OF_NET_REVENUE * (1 + rng.normal(0, config.NOISE_SIGMA_OPEX))
            admin_rate = config.ADMIN_PCT_OF_NET_REVENUE * (1 + rng.normal(0, config.NOISE_SIGMA_OPEX))
            sales_marketing_cents = round(net_rev_cents * sm_rate)
            admin_general_cents = round(net_rev_cents * admin_rate)
            other_income_cents = 0

            if bu == n2["bu"] and month == n2["month"]:
                admin_general_cents += round(n2["amount_eur"] * 100)
            if bu == s2["warehouse_bu"] and month == s2["warehouse_month"]:
                other_income_cents += round(s2["warehouse_gain_eur"] * 100)

            headcount_fte = round(bu_base_fte(bu) * (1 + HEADCOUNT_TREND_M) ** t)

            rows.append({
                "month": month, "bu": bu,
                "sales_marketing_cents": sales_marketing_cents,
                "admin_general_cents": admin_general_cents,
                "other_income_cents": other_income_cents,
                "headcount_fte": headcount_fte,
            })
    return pd.DataFrame(rows)


def build_opex_budget(pnl_budget: pd.DataFrame) -> pd.DataFrame:
    bu_net_revenue = pnl_budget.groupby(["month", "bu"])["net_revenue_cents"].sum()
    rows = []
    for month in ACTUAL_MONTHS:
        t = MONTH_INDEX[month]
        for bu in config.BUS:
            net_rev_cents = int(bu_net_revenue.loc[(month, bu)])
            sm_rate = config.SM_PCT_OF_NET_REVENUE * (1 + config.BUDGET_OPTIMISM_OPEX)
            admin_rate = config.ADMIN_PCT_OF_NET_REVENUE * (1 + config.BUDGET_OPTIMISM_OPEX)
            headcount_fte = round(bu_base_fte(bu) * (1 + HEADCOUNT_TREND_M) ** t)
            rows.append({
                "month": month, "bu": bu,
                "sales_marketing_cents": round(net_rev_cents * sm_rate),
                "admin_general_cents": round(net_rev_cents * admin_rate),
                "other_income_cents": 0,
                "headcount_fte": headcount_fte,
            })
    return pd.DataFrame(rows)

# ---------------------------------------------------------------------------
# customer_master and customer_revenue_monthly
# ---------------------------------------------------------------------------

def customer_roster_with_other(bu: str) -> list:
    """Named top-10 + 'Other', in config-declared order, Other always last."""
    roster = list(config.CUSTOMER_ROSTER[bu])
    other = dict(config.OTHER_BUCKET[bu])
    other["name"] = "Other"
    other["share"] = config.other_share(bu)
    return roster + [other]


def build_customer_master() -> pd.DataFrame:
    rows = []
    for bu in config.BUS:
        for cust in customer_roster_with_other(bu):
            rows.append({
                "customer": cust["name"],
                "bu": bu,
                "channel": cust["channel"],
                "contractual_terms_days": cust["contractual_terms_days"],
            })
    return pd.DataFrame(rows)


def build_customer_revenue_monthly(pnl_actual: pd.DataFrame) -> pd.DataFrame:
    bu_totals = pnl_actual.groupby(["month", "bu"])[["gross_revenue_cents", "promo_discounts_cents"]].sum()
    s3 = config.S3_PARAMS

    rows = []
    for month in ACTUAL_MONTHS:
        for bu in config.BUS:
            gross_total = int(bu_totals.loc[(month, bu), "gross_revenue_cents"])
            discount_total = int(bu_totals.loc[(month, bu), "promo_discounts_cents"])
            roster = customer_roster_with_other(bu)

            gross_shares = [c["share"] for c in roster]
            gross_alloc = allocate_largest_remainder(gross_total, gross_shares)

            is_concentrated_window = (bu == s3["bu"]) and (s3["start_month"] <= month <= s3["end_month"])
            discount_weights = []
            for c in roster:
                mult = s3["concentrated_discount_multiplier"] if (
                    is_concentrated_window and c["name"] in s3["concentrated_accounts"]
                ) else 1.0
                discount_weights.append(c["share"] * mult)
            discount_alloc = allocate_largest_remainder(discount_total, discount_weights)

            for cust, gross_cents, discount_cents in zip(roster, gross_alloc, discount_alloc):
                rows.append({
                    "month": month, "bu": bu, "customer": cust["name"],
                    "gross_revenue_cents": gross_cents,
                    "promo_discounts_cents": discount_cents,
                    "net_revenue_cents": gross_cents - discount_cents,
                })
    return pd.DataFrame(rows)

# ---------------------------------------------------------------------------
# working_capital_monthly and receivables_by_customer_monthly
# ---------------------------------------------------------------------------

def build_receivables(customer_revenue: pd.DataFrame, rng: np.random.Generator) -> tuple:
    s2 = config.S2_PARAMS
    contractual = {}
    for bu in config.BUS:
        for cust in customer_roster_with_other(bu):
            contractual[(bu, cust["name"])] = cust["contractual_terms_days"]

    # Deterministic per-(bu,customer,month) noise draw, in stable iteration order.
    keys = [(bu, cust["name"]) for bu in config.BUS for cust in customer_roster_with_other(bu)]
    noise_lookup = {}
    for key in keys:
        for month in ACTUAL_MONTHS:
            noise_lookup[(key[0], key[1], month)] = rng.normal(0, config.NOISE_SIGMA_TERMS_DAYS)

    def effective_terms_days(bu: str, customer: str, month: str) -> float:
        base_days = contractual[(bu, customer)]
        noise = noise_lookup[(bu, customer, month)]
        if bu == s2["bu"] and customer == s2["primary_account"]:
            base_days = ramp_value(month, s2["primary_drift_start_month"], s2["primary_drift_end_month"],
                                    s2["primary_terms_start_days"], s2["primary_terms_end_days"])
        elif bu == s2["bu"] and customer in s2["secondary_accounts"]:
            base_days = ramp_value(month, s2["secondary_drift_start_month"], s2["secondary_drift_end_month"],
                                    s2["secondary_terms_start_days"], s2["secondary_terms_end_days"])
        return max(5.0, base_days + noise)

    net_rev_lookup = customer_revenue.set_index(["month", "bu", "customer"])["net_revenue_cents"]

    # FY2023 backfill (noiseless, consumes no RNG): terms-based AR reads the most
    # recent ~4 months of billing, so opening balances and early-2024 closings need
    # pre-window revenue. Computed from the deterministic driver model (no noise,
    # no stories — none is active in 2023) and allocated to customers by share.
    backfill_months = month_range("2023-01", "2023-12")
    backfill = {}
    for month in backfill_months:
        t = MONTH_INDEX[month]
        for bu in config.BUS:
            bu_net_cents = 0
            for line in config.LINES:
                d = normal_driver(bu, line, t)
                row = pnl_identity_row(
                    volume_units=max(0, round(d["volume"])),
                    list_price_cents=max(1, round(d["price_cents"])),
                    discount_rate=min(max(d["discount_rate"], 0.0), 0.90),
                    unit_material_cents=max(0, round(d["material_cents"])),
                    unit_labour_cents=max(0, round(d["labour_cents"])),
                    unit_logistics_cents=max(0, round(d["logistics_cents"])),
                )
                bu_net_cents += row["net_revenue_cents"]
            roster = customer_roster_with_other(bu)
            alloc = allocate_largest_remainder(bu_net_cents, [c["share"] for c in roster])
            for cust, cents in zip(roster, alloc):
                backfill[(month, bu, cust["name"])] = cents

    def rev_at(bu: str, customer: str, idx: int) -> int:
        """Net revenue cents at ACTUAL_MONTHS index idx; negative idx reads the
        noiseless FY2023 backfill (idx=-1 -> 2023-12)."""
        if idx >= 0:
            return int(net_rev_lookup.loc[(ACTUAL_MONTHS[idx], bu, customer)])
        return backfill[(backfill_months[12 + idx], bu, customer)]

    def ar_terms_based(bu: str, customer: str, idx: int, days: float) -> int:
        """Closing AR = the most recent `days` of billing: the newest full months
        plus a fraction of the oldest month in the window (30-day months, declared
        simplification). This is the realistic model — balances balloon after the
        December billing peak and unwind through Q1, as a real balance sheet does —
        so DSO comparisons downstream must be like-for-like year-on-year (see
        validate_financials.py rule 8b), where the seasonal numerator cancels."""
        full = int(days // config.DAYS_IN_MONTH_APPROX)
        frac = (days - config.DAYS_IN_MONTH_APPROX * full) / config.DAYS_IN_MONTH_APPROX
        total = 0.0
        for k in range(full):
            total += rev_at(bu, customer, idx - k)
        total += frac * rev_at(bu, customer, idx - full)
        return round(total)

    receivable_rows = []
    opening_cents = {}
    for key in keys:
        bu, customer = key
        opening_cents[key] = ar_terms_based(bu, customer, -1, float(contractual[key]))

    for month_idx, month in enumerate(ACTUAL_MONTHS):
        for bu in config.BUS:
            for cust in customer_roster_with_other(bu):
                key = (bu, cust["name"])
                net_rev_cents = rev_at(bu, cust["name"], month_idx)
                days = effective_terms_days(bu, cust["name"], month)
                closing_cents = ar_terms_based(bu, cust["name"], month_idx, days)
                collections_cents = opening_cents[key] + net_rev_cents - closing_cents
                receivable_rows.append({
                    "month": month, "bu": bu, "customer": cust["name"],
                    "receivables_opening_cents": opening_cents[key],
                    "collections_cents": collections_cents,
                    "receivables_closing_cents": closing_cents,
                })
                opening_cents[key] = closing_cents

    receivables_df = pd.DataFrame(receivable_rows)
    working_capital_df = (
        receivables_df.groupby(["month", "bu"], sort=False)[
            ["receivables_opening_cents", "collections_cents", "receivables_closing_cents"]
        ].sum().reset_index()
    )
    month_order = {m: i for i, m in enumerate(ACTUAL_MONTHS)}
    bu_order = {b: i for i, b in enumerate(config.BUS)}
    working_capital_df = working_capital_df.sort_values(
        by=["month", "bu"], key=lambda s: s.map(month_order if s.name == "month" else bu_order)
    ).reset_index(drop=True)
    return working_capital_df, receivables_df

# ---------------------------------------------------------------------------
# cash_monthly (company level)
# ---------------------------------------------------------------------------

def build_cash_monthly(pnl_actual: pd.DataFrame, opex_actual: pd.DataFrame,
                        working_capital: pd.DataFrame) -> pd.DataFrame:
    gp_by_month = pnl_actual.groupby("month")["gross_profit_cents"].sum()
    opex_by_month = opex_actual.groupby("month")[
        ["sales_marketing_cents", "admin_general_cents", "other_income_cents"]
    ].sum()
    ar_by_month = working_capital.groupby("month")["receivables_closing_cents"].sum()
    ar_opening_by_month = working_capital.groupby("month")["receivables_opening_cents"].sum()

    s2 = config.S2_PARAMS
    rows = []
    opening_cash_cents = round(config.CASH_OPENING_EUR * 100)
    prior_ar_cents = None

    for month in ACTUAL_MONTHS:
        ebitda_cents = (
            int(gp_by_month.loc[month])
            - int(opex_by_month.loc[month, "sales_marketing_cents"])
            - int(opex_by_month.loc[month, "admin_general_cents"])
            + int(opex_by_month.loc[month, "other_income_cents"])
        )
        ar_cents = int(ar_by_month.loc[month])
        if prior_ar_cents is None:
            # First month's delta runs against the terms-based Dec-2023 opening
            # balance, so January's post-peak collections are a real cash event
            # (they are, every January).
            delta_ar_cents = ar_cents - int(ar_opening_by_month.loc[month])
        else:
            delta_ar_cents = ar_cents - prior_ar_cents
        prior_ar_cents = ar_cents

        tax_cents = round(config.SIMPLIFIED_TAX_RATE * max(ebitda_cents, 0))
        ocf_cents = ebitda_cents - delta_ar_cents - tax_cents

        icf_cents = 0
        if month == s2["warehouse_month"]:
            icf_cents += round(s2["warehouse_proceeds_eur"] * 100)

        closing_cash_cents = opening_cash_cents + ocf_cents + icf_cents
        rows.append({
            "month": month,
            "cash_opening_cents": opening_cash_cents,
            "operating_cash_flow_cents": ocf_cents,
            "investing_cash_flow_cents": icf_cents,
            "cash_closing_cents": closing_cash_cents,
        })
        opening_cash_cents = closing_cash_cents

    return pd.DataFrame(rows)

# ---------------------------------------------------------------------------
# answer_key/stories.csv
# ---------------------------------------------------------------------------

def build_answer_key() -> pd.DataFrame:
    s1, s2, s3, s4 = (config.STORY_PARAMS[k] for k in ("S1", "S2", "S3", "S4"))
    rows = [
        {
            "story_id": "S1", "type": "story", "name": "The mix shift that reads as input inflation",
            "mechanism": "Listing win + deep in-store promo (Home Care net price/unit ~-13%) lifts Home Care "
                         "volume ~+42% FY-on-FY and cannibalises Skin & Body ~-13%; Home Care carries ~48% "
                         "material cost vs a ~30% line average, so BU material spend rises while unit "
                         "material costs (per line) stay flat.",
            "affected_bus": s1["bu"], "affected_lines": "Home Care; Skin & Body", "affected_customers": "(none)",
            "months": f"{s1['start_month']}..{s1['end_month']}",
            "designed_magnitude": "BU material spend +12%±1 YoY, unit material cost flat ±0.5%, "
                                   "BU net revenue +2-4%, BU gross margin -3pp±0.5",
            "expected_finding": "Unit costs are flat; the margin went to mix and promotional pricing, not "
                                 "commodity inflation.",
            "failure_mode_tested": "Right variance, wrong cause.",
        },
        {
            "story_id": "S2", "type": "story", "name": "The DSO creep behind a one-off",
            "mechanism": f"{s2['primary_account']} (~35% of the BU) stretches effective payment terms from "
                         f"~{s2['primary_terms_start_days']} to ~{s2['primary_terms_end_days']} days over "
                         f"{s2['primary_drift_start_month']}..{s2['primary_drift_end_month']}, then holds; two "
                         "smaller CE accounts follow partway over the same window. The April-2025 warehouse "
                         "sale-and-leaseback masks the cash effect with a one-off gain and cash inflow.",
            "affected_bus": s2["bu"], "affected_lines": "(none — receivables/cash only)",
            "affected_customers": "; ".join([s2["primary_account"]] + s2["secondary_accounts"]),
            "months": f"{s2['primary_drift_start_month']}..{s2['primary_drift_end_month']}",
            "designed_magnitude": "BU DSO +15 days or more, company DSO +4 days or more, reported EBITDA "
                                   "on plan and cash balance stable throughout, H1-2025 cash conversion "
                                   "(OCF/EBITDA) falls 15pp or more",
            "expected_finding": "The one-off is doing the work; strip it out and cash conversion has "
                                 "deteriorated materially, driven by one named customer's payment behaviour.",
            "failure_mode_tested": "Missing a story entirely because every headline looks fine.",
        },
        {
            "story_id": "S3", "type": "story", "name": "Growth bought with discount",
            "mechanism": "Promotional discounting escalates from ~8% to ~17% of gross revenue across 2025; "
                         "three of the BU's top-10 accounts are discounted above 18%; the volume response "
                         "per promotional euro fades in H2 versus H1.",
            "affected_bus": s3["bu"], "affected_lines": "(all four)",
            "affected_customers": "; ".join(s3["concentrated_accounts"]),
            "months": f"{s3['start_month']}..{s3['end_month']}",
            "designed_magnitude": "Discount rate 8%->17% of gross, 3+ accounts >18%, BU gross margin "
                                   "erosion 4pp or more (FY2024 avg vs Q4-2025 avg), company FY2025 revenue "
                                   "+8%±1, H2 volume-per-promo-euro 30% or more weaker than H1",
            "expected_finding": "The growth is bought and fading — named accounts and the H1/H2 elasticity "
                                 "comparison are the evidence.",
            "failure_mode_tested": "Celebrating a positive headline without reading what funds it.",
        },
        {
            "story_id": "S4", "type": "story", "name": "The January cliff that isn't (the trap)",
            "mechanism": "Hair Care and Skin & Body carry a Q4 gifting peak and Q1 trough, identical in both "
                         "years and in the budget. January is always a steep MoM drop against December.",
            "affected_bus": "(all three)", "affected_lines": "Hair Care; Skin & Body", "affected_customers": "(none)",
            "months": s4["test_month"],
            "designed_magnitude": "Company seasonal index (per-year basis): December ~1.24, January ~0.81; "
                                   "January-2025 ~-29% MoM, ~+3% YoY, ~-2% vs budget",
            "expected_finding": "Stand down — seasonal, in line with budget and prior year, no action.",
            "failure_mode_tested": "Narrating a crisis where none exists (the A7 analogue).",
        },
    ]
    for nid, n in config.NOISE_EVENTS.items():
        amount = n.get("amount_eur")
        magnitude = f"EUR {amount:,.0f}" if amount is not None else f"list price x{n.get('list_price_multiplier')}"
        rows.append({
            "story_id": nid, "type": "noise", "name": n["description"],
            "mechanism": n["description"], "affected_bus": n["bu"], "affected_lines": "(none)",
            "affected_customers": "(none)", "months": n["month"],
            "designed_magnitude": magnitude,
            "expected_finding": "Mundane, self-explaining; may be noted but not dramatised.",
            "failure_mode_tested": "Treating routine noise as a story.",
        })
    # N4 — structural budget optimism. Not an event: a property of how the
    # budget is set (config BUDGET_OPTIMISM_*), compounding to roughly -1%
    # revenue / -2.6% gross profit / -8% EBITDA vs budget in the story-free
    # year. Declared here so a storyteller who correctly observes "budgets
    # run optimistic; the below-plan EBITDA hum is planning bias, not
    # deterioration" is scored as right, not as a false positive.
    rows.append({
        "story_id": "N4", "type": "noise", "name": "Structural budget optimism",
        "mechanism": "Budgets are computed from prior-year drivers with a small optimism bias on volume, "
                     "price, discounts, unit costs and opex; the biases compound through operating leverage "
                     "to a persistent below-plan EBITDA gap in every month, both years, all BUs.",
        "affected_bus": "(all three)", "affected_lines": "(all four)", "affected_customers": "(none)",
        "months": "2024-01..2025-12",
        "designed_magnitude": "FY2024 (story-free year): net revenue ~-1%, gross profit ~-2.6%, "
                               "EBITDA ~-8% vs budget",
        "expected_finding": "Budgets are set optimistically; the persistent below-plan EBITDA hum is a "
                             "planning property, not a performance deterioration. Note it once; do not "
                             "dramatise it, and do not attribute 2025 story variances to it.",
        "failure_mode_tested": "Narrating the budget hum as a crisis, or missing that it predates the stories.",
    })
    return pd.DataFrame(rows)

# ---------------------------------------------------------------------------
# CSV writers — cents internally, EUR at exactly 2 decimals on disk
# ---------------------------------------------------------------------------

def cents_to_eur(df: pd.DataFrame, cent_cols: list) -> pd.DataFrame:
    out = df.copy()
    for col in cent_cols:
        eur_col = col.replace("_cents", "")
        out[eur_col] = (out[col] / 100.0).round(2)
        out = out.drop(columns=[col])
    return out


def write_csv(df: pd.DataFrame, path: Path, columns: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df[columns].to_csv(path, index=False, float_format="%.2f", encoding="utf-8")
    print(f"  wrote {path.relative_to(PROJECT_ROOT)}  ({len(df):,} rows)")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print(f"Generating financial dataset — {config.COMPANY_NAME}")
    print(f"Actual window: {ACTUAL_MONTHS[0]} .. {ACTUAL_MONTHS[-1]} ({len(ACTUAL_MONTHS)} months)")
    print("=" * 70)

    rng = np.random.default_rng(config.RANDOM_SEED)

    print("\nBuilding pnl_monthly (actual)...")
    pnl_actual = build_pnl_actual(rng)

    print("Building budget_pnl_monthly...")
    pnl_budget = build_pnl_budget()

    print("Building opex_monthly (actual)...")
    opex_actual = build_opex_actual(pnl_actual, rng)

    print("Building budget_opex_monthly...")
    opex_budget = build_opex_budget(pnl_budget)

    print("Building customer_master...")
    customer_master = build_customer_master()

    print("Building customer_revenue_monthly...")
    customer_revenue = build_customer_revenue_monthly(pnl_actual)

    print("Building working_capital_monthly and receivables_by_customer_monthly...")
    working_capital, receivables = build_receivables(customer_revenue, rng)

    print("Building cash_monthly...")
    cash = build_cash_monthly(pnl_actual, opex_actual, working_capital)

    print("Building answer_key/stories.csv...")
    answer_key = build_answer_key()

    print("\nWriting CSVs...")
    # The stored unit price column is named list_price_eur (so rule 1's
    # volume x price = gross identity is checkable directly from the CSV).
    pnl_cols = ["month", "bu", "line", "volume_units", "list_price_eur", "gross_revenue",
                "promo_discounts", "net_revenue", "material_cost", "direct_labour",
                "logistics_cost", "gross_profit"]
    money_cent_cols = [
        "list_price_cents", "gross_revenue_cents", "promo_discounts_cents", "net_revenue_cents",
        "material_cost_cents", "direct_labour_cents", "logistics_cost_cents", "gross_profit_cents",
    ]
    pnl_actual_out = cents_to_eur(pnl_actual, money_cent_cols).rename(columns={"list_price": "list_price_eur"})
    write_csv(pnl_actual_out, DATA_DIR / "pnl_monthly.csv", pnl_cols)

    pnl_budget_out = cents_to_eur(pnl_budget, money_cent_cols).rename(columns={"list_price": "list_price_eur"})
    write_csv(pnl_budget_out, DATA_DIR / "budget_pnl_monthly.csv", pnl_cols)

    opex_cols = ["month", "bu", "sales_marketing", "admin_general", "other_income", "headcount_fte"]
    opex_actual_out = cents_to_eur(opex_actual, ["sales_marketing_cents", "admin_general_cents", "other_income_cents"])
    write_csv(opex_actual_out, DATA_DIR / "opex_monthly.csv", opex_cols)

    opex_budget_out = cents_to_eur(opex_budget, ["sales_marketing_cents", "admin_general_cents", "other_income_cents"])
    write_csv(opex_budget_out, DATA_DIR / "budget_opex_monthly.csv", opex_cols)

    write_csv(customer_master, DATA_DIR / "customer_master.csv",
              ["customer", "bu", "channel", "contractual_terms_days"])

    customer_revenue_out = cents_to_eur(customer_revenue,
        ["gross_revenue_cents", "promo_discounts_cents", "net_revenue_cents"])
    write_csv(customer_revenue_out, DATA_DIR / "customer_revenue_monthly.csv",
              ["month", "bu", "customer", "gross_revenue", "promo_discounts", "net_revenue"])

    working_capital_out = cents_to_eur(working_capital,
        ["receivables_opening_cents", "collections_cents", "receivables_closing_cents"])
    write_csv(working_capital_out, DATA_DIR / "working_capital_monthly.csv",
              ["month", "bu", "receivables_opening", "collections", "receivables_closing"])

    receivables_out = cents_to_eur(receivables, ["collections_cents", "receivables_closing_cents"])
    write_csv(receivables_out, DATA_DIR / "receivables_by_customer_monthly.csv",
              ["month", "bu", "customer", "receivables_closing", "collections"])

    cash_out = cents_to_eur(cash,
        ["cash_opening_cents", "operating_cash_flow_cents", "investing_cash_flow_cents", "cash_closing_cents"])
    write_csv(cash_out, DATA_DIR / "cash_monthly.csv",
              ["month", "cash_opening", "operating_cash_flow", "investing_cash_flow", "cash_closing"])

    write_csv(answer_key, ANSWER_KEY_DIR / "stories.csv",
              ["story_id", "type", "name", "mechanism", "affected_bus", "affected_lines",
               "affected_customers", "months", "designed_magnitude", "expected_finding",
               "failure_mode_tested"])

    print("\nDone.")


if __name__ == "__main__":
    main()
