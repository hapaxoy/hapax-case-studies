"""Shared machinery for the Phase 3 answer key (Project 11).

Three things live here:
  1. SQL fragments that the reference queries and the naive variants share (the company definitions as an analyst
     would write them).
  2. The pandas side of the two-way check: a calendar rebuilt from config.py (not from dim_date), and `World`, which
     loads the generator's own clean (pre-incident) fact tables from data/internal/ - or, for the "published number"
     of an undocumented-issue request, the published fact tables from the warehouse - into one normalised shape.
  3. The result comparer used by the key builder and by the validator (rule 12) and the bite test (rule 13).

Nothing in here writes anywhere.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import Decimal

import duckdb
import numpy as np
import pandas as pd

import config as cfg

# ---------------------------------------------------------------------------
# 1. SQL fragments
# ---------------------------------------------------------------------------

HELSINKI_DATE = "CAST(timezone('Europe/Helsinki', {col} AT TIME ZONE 'UTC') AS DATE)"


def hel(column: str) -> str:
    """SQL for the Helsinki calendar date of a UTC timestamp column."""
    return HELSINKI_DATE.format(col=column)


# Web dispatch date in Helsinki time, shipped orders only (delivered or collected).
WEB_DISPATCH = f"""web_dispatch AS (
    SELECT web_order_id, {hel('dispatch_ts_utc')} AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
)"""

# Net-sales events: sales on the sale date (web on its Helsinki dispatch date) and returns on their own return date,
# store 999 and category ZZ Test left out. Carries natural keys so any hierarchy can be joined as-is or as-was.
NET_EVENTS = """net_events AS (
    SELECT COALESCE(w.dispatch_date, f.sale_date) AS business_date, f.store_key, f.product_key, s.store_id, p.sku,
           f.net_amount AS net_sales, f.standard_cost AS cost
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
    UNION ALL
    SELECT r.return_date, r.store_key, r.product_key, s.store_id, p.sku, -r.refund_net, -r.standard_cost_returned
    FROM fact_return_line r
    JOIN dim_store s   ON s.store_key = r.store_key
    JOIN dim_product p ON p.product_key = r.product_key
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
)"""

NET_EVENTS_WITH_DISPATCH = f"WITH {WEB_DISPATCH},\n{NET_EVENTS}"

# The same lines with the double-posted rows of a re-sync removed (used only by the undocumented-issue references).
DEDUPED_LINES = ("(SELECT * FROM fact_sales_line QUALIFY row_number() OVER "
                 "(PARTITION BY receipt_id, line_no ORDER BY sales_line_id) = 1)")


# net_events built on the de-duplicated lines (a requested reading that touches the double-posted store-week uses this).
NET_EVENTS_DEDUP = NET_EVENTS.replace("FROM fact_sales_line f", f"FROM {DEDUPED_LINES} f")
assert NET_EVENTS_DEDUP != NET_EVENTS


def fiscal_year_label(start_year: int) -> str:
    return f"FY{start_year}/{str(start_year + 1)[2:]}"


# ---------------------------------------------------------------------------
# 2a. Calendar rebuilt from config.py (independent of dim_date)
# ---------------------------------------------------------------------------

def build_calendar() -> pd.DataFrame:
    """One row per day in the window: fiscal year label, week, period, quarter and week bounds, from config alone."""
    rows = []
    for start_year, start in sorted(cfg.FISCAL_YEAR_STARTS.items()):
        weeks = cfg.FISCAL_YEAR_WEEKS[start_year]
        pattern = list(cfg.PERIOD_WEEKS_445)
        if weeks == 53:
            pattern[-1] += 1
        week_to_period = []
        for period_number, length in enumerate(pattern, start=1):
            week_to_period += [period_number] * length
        for week_number in range(1, weeks + 1):
            for offset in range(7):
                day = start + timedelta(days=7 * (week_number - 1) + offset)
                if day > cfg.WINDOW_END:
                    continue
                period = week_to_period[week_number - 1]
                rows.append((day, fiscal_year_label(start_year), start_year, week_number, period, (period - 1) // 3 + 1,
                             start + timedelta(days=7 * (week_number - 1)),
                             start + timedelta(days=7 * (week_number - 1) + 6)))
    frame = pd.DataFrame(rows, columns=["date", "fy", "fy_start_year", "week", "period", "quarter", "week_start", "week_end"])
    for column in ("date", "week_start", "week_end"):
        frame[column] = pd.to_datetime(frame[column])
    return frame


def period_bounds(calendar: pd.DataFrame, fy: str, period_from: int, period_to: int | None = None):
    """First and last date of a run of periods in a fiscal year."""
    period_to = period_to or period_from
    subset = calendar[(calendar.fy == fy) & calendar.period.between(period_from, period_to)]
    return subset.date.min(), subset.date.max()


# ---------------------------------------------------------------------------
# 2b. The pandas world
# ---------------------------------------------------------------------------

def to_helsinki_date(utc_series: pd.Series) -> pd.Series:
    """Helsinki calendar date (naive, midnight) of naive UTC timestamps."""
    return utc_series.dt.tz_localize("UTC").dt.tz_convert("Europe/Helsinki").dt.tz_localize(None).dt.normalize()


class World:
    """Normalised fact tables in integer cents, from the clean internal parquet files or from the published warehouse.

    source = "clean"      the generator's own pre-incident tables (data/internal/*.parquet)
    source = "published"  the warehouse's fact tables as an analyst sees them (incidents included)
    Dimensions always come from the warehouse (no incident touches them).
    """

    def __init__(self, source: str = "clean"):
        assert source in ("clean", "published")
        self.source = source
        connection = duckdb.connect(str(cfg.WAREHOUSE_PATH), read_only=True)
        self.calendar = build_calendar()
        self.dim_store = connection.execute("SELECT * FROM dim_store").df()
        self.dim_product = connection.execute("SELECT * FROM dim_product").df()
        self.dim_member = connection.execute("SELECT * FROM dim_member").df()
        self.dim_date = connection.execute("SELECT calendar_date, is_trading_day FROM dim_date").df()
        self.dim_date["calendar_date"] = pd.to_datetime(self.dim_date["calendar_date"])
        self.dim_campaign = connection.execute("SELECT * FROM dim_campaign").df()
        self.holdout = connection.execute("SELECT * FROM campaign_holdout").df()
        self.exposure = connection.execute("SELECT * FROM fact_campaign_exposure").df()
        self.closures = connection.execute("SELECT * FROM ref_store_closure").df()
        for frame in (self.dim_store, self.dim_product, self.dim_member):
            for column in ("valid_from", "valid_to"):
                frame[column] = pd.to_datetime(frame[column].astype(str).str[:10], format="%Y-%m-%d", errors="coerce")
        # valid_to 9999-12-31 overflows pandas ns timestamps; keep a far-future stand-in.
        for frame in (self.dim_store, self.dim_product, self.dim_member):
            frame["valid_to"] = frame["valid_to"].fillna(pd.Timestamp("2262-01-01"))
        for column in ("open_date", "close_date"):
            self.dim_store[column] = pd.to_datetime(self.dim_store[column])
        self.dim_member["join_date"] = pd.to_datetime(self.dim_member["join_date"])
        for column in ("start_date", "end_date"):
            self.dim_campaign[column] = pd.to_datetime(self.dim_campaign[column])
        for column in ("closure_start_date", "closure_end_date"):
            self.closures[column] = pd.to_datetime(self.closures[column])
        self.exposure["contact_ts_utc"] = pd.to_datetime(self.exposure["contact_ts_utc"])
        # store_key -> natural key and attributes
        self.store_by_key = self.dim_store.set_index("store_key")
        self.product_by_key = self.dim_product.set_index("product_key")
        # current attributes by natural key
        self.store_current = self.dim_store[self.dim_store.is_current].set_index("store_id")
        self.product_current = self.dim_product[self.dim_product.is_current].set_index("sku")
        if source == "clean":
            self._load_clean()
        else:
            self._load_published(connection)
        connection.close()
        self._derive()

    # -- loading -----------------------------------------------------------------------------------------
    def _load_clean(self) -> None:
        d = cfg.INTERNAL_DIR
        sales = pd.read_parquet(d / "sales_line_clean.parquet")
        self.sales = pd.DataFrame({
            "sales_line_id": sales.sales_line_id, "receipt_id": sales.receipt_id, "line_no": sales.line_no.astype("int32"),
            "sale_date": pd.to_datetime(sales.sale_date), "store_key": sales.store_key, "product_key": sales.product_key,
            "member_key": sales.member_key, "channel_id": sales.channel_id, "quantity": sales.quantity.astype("int32"),
            "net_c": sales.net_cents, "gross_c": sales.gross_cents, "cost_c": sales.std_cost_cents,
            "vat_bp": sales.vat_bp, "staff": sales.staff_purchase_flag, "is_web": sales.is_web})
        returns = pd.read_parquet(d / "return_line_truth.parquet")
        self.returns = pd.DataFrame({
            "return_line_id": returns.return_line_id, "sales_line_id": returns.sales_line_id,
            "return_date": pd.to_datetime(returns.return_date), "store_key": returns.store_key,
            "product_key": returns.product_key, "member_key": returns.member_key, "qty": returns.quantity_returned.astype("int32"),
            "refund_net_c": returns.refund_net_cents, "refund_gross_c": returns.refund_gross_cents,
            "cost_c": returns.std_cost_returned_cents})
        web = pd.read_parquet(d / "web_order_clean.parquet")
        self.web = pd.DataFrame({
            "web_order_id": web.web_order_id, "member_key": web.member_key, "login_state": web.login_state,
            "order_ts_utc": pd.to_datetime(web.order_ts_utc), "dispatch_ts_utc": pd.to_datetime(web.dispatch_ts_utc),
            "status": web.status, "fulfilment_type": web.fulfilment_type, "pickup_store_key": web.pickup_store_key,
            "test_order": web.test_order})
        stock = pd.read_parquet(d / "stock_week_clean.parquet")
        self.stock = pd.DataFrame({
            "store_key": stock.store_key, "product_key": stock.product_key,
            "week_ending_date": pd.to_datetime(stock.week_ending_date), "closing_units": stock.closing_units,
            "closing_value_c": stock.closing_value_cents})

    def _load_published(self, connection) -> None:
        sales = connection.execute(
            "SELECT sales_line_id, receipt_id, line_no, sale_date, store_key, product_key, member_key, channel_id, quantity, "
            "CAST(round(net_amount * 100) AS BIGINT) AS net_c, CAST(round(gross_amount * 100) AS BIGINT) AS gross_c, "
            "CAST(round(standard_cost * 100) AS BIGINT) AS cost_c, CAST(round(vat_rate * 10000) AS INTEGER) AS vat_bp, "
            "staff_purchase_flag AS staff FROM fact_sales_line").df()
        sales["sale_date"] = pd.to_datetime(sales["sale_date"])
        store_ids = self.store_by_key["store_id"]
        sales["is_web"] = sales["store_key"].map(store_ids) == cfg.WEB_STORE_ID
        self.sales = sales
        returns = connection.execute(
            "SELECT return_line_id, sales_line_id, return_date, store_key, product_key, member_key, quantity_returned AS qty, "
            "CAST(round(refund_net * 100) AS BIGINT) AS refund_net_c, CAST(round(refund_gross * 100) AS BIGINT) AS refund_gross_c, "
            "CAST(round(standard_cost_returned * 100) AS BIGINT) AS cost_c FROM fact_return_line").df()
        returns["return_date"] = pd.to_datetime(returns["return_date"])
        self.returns = returns
        web = connection.execute(
            "SELECT web_order_id, member_key, login_state, order_ts_utc, dispatch_ts_utc, status, fulfilment_type, pickup_store_key "
            "FROM fact_web_order").df()
        zz_orders = connection.execute(
            "SELECT DISTINCT f.receipt_id FROM fact_sales_line f JOIN dim_product p USING (product_key) "
            f"WHERE p.category = '{cfg.TEST_CATEGORY}' AND f.store_key IN (SELECT store_key FROM dim_store WHERE store_id = {cfg.WEB_STORE_ID})").df()
        web["test_order"] = web["web_order_id"].isin(set(zz_orders["receipt_id"]))
        self.web = web
        stock = connection.execute(
            "SELECT store_key, product_key, week_ending_date, closing_units, CAST(round(closing_value * 100) AS BIGINT) AS closing_value_c "
            "FROM fact_stock_week").df()
        stock["week_ending_date"] = pd.to_datetime(stock["week_ending_date"])
        self.stock = stock

    # -- derived columns ---------------------------------------------------------------------------------
    def _derive(self) -> None:
        store_id = self.store_by_key["store_id"]
        sku = self.product_by_key["sku"]
        category_was = self.product_by_key["category"]
        self.sales["store_id"] = self.sales["store_key"].map(store_id)
        self.sales["sku"] = self.sales["product_key"].map(sku)
        self.sales["category_was"] = self.sales["product_key"].map(category_was)
        self.returns["store_id"] = self.returns["store_key"].map(store_id)
        self.returns["sku"] = self.returns["product_key"].map(sku)
        self.returns["category_was"] = self.returns["product_key"].map(category_was)
        self.stock["store_id"] = self.stock["store_key"].map(store_id)
        self.stock["sku"] = self.stock["product_key"].map(sku)
        self.stock["category_was"] = self.stock["product_key"].map(category_was)
        # Web dispatch date (Helsinki) for shipped orders; the business date of a web sales line.
        shipped = self.web[self.web.status.isin(["delivered", "collected"])]
        dispatch = pd.Series(to_helsinki_date(shipped["dispatch_ts_utc"]).values, index=shipped["web_order_id"].values)
        self.web["order_date"] = to_helsinki_date(self.web["order_ts_utc"])
        self.web["dispatch_date"] = self.web["web_order_id"].map(dispatch)
        self.sales["business_date"] = self.sales["sale_date"]
        web_lines = self.sales["is_web"]
        self.sales.loc[web_lines, "business_date"] = self.sales.loc[web_lines, "receipt_id"].map(dispatch)
        self.sales["current_category"] = self.sales["sku"].map(self.product_current["category"])
        self.sales["current_subcategory"] = self.sales["sku"].map(self.product_current["subcategory"])
        self.sales["current_region"] = self.sales["store_id"].map(self.store_current["region"])
        self.sales["current_format"] = self.sales["store_id"].map(self.store_current["format"])
        self.returns["current_category"] = self.returns["sku"].map(self.product_current["category"])
        self.returns["current_subcategory"] = self.returns["sku"].map(self.product_current["subcategory"])
        self.returns["current_region"] = self.returns["store_id"].map(self.store_current["region"])
        self.returns["current_format"] = self.returns["store_id"].map(self.store_current["format"])
        self.returns["region_was"] = self.returns["store_key"].map(self.store_by_key["region"])
        self.sales["region_was"] = self.sales["store_key"].map(self.store_by_key["region"])
        self.returns["business_date"] = self.returns["return_date"]

    # -- helpers used by the recomputations --------------------------------------------------------------
    def fiscal(self, frame: pd.DataFrame, date_column: str, prefix: str = "") -> pd.DataFrame:
        """Attach fiscal year / week / period / quarter for a date column."""
        lookup = self.calendar.set_index("date")
        out = frame.copy()
        for column in ("fy", "week", "period", "quarter"):
            out[prefix + column] = out[date_column].map(lookup[column])
        return out

    def in_scope_sales(self) -> pd.DataFrame:
        """Sales lines in net-sales scope: store 999 and category ZZ Test out."""
        mask = (self.sales.store_id != cfg.TRAINING_STORE_ID) & (self.sales.category_was != cfg.TEST_CATEGORY)
        return self.sales[mask]

    def in_scope_returns(self) -> pd.DataFrame:
        mask = (self.returns.store_id != cfg.TRAINING_STORE_ID) & (self.returns.category_was != cfg.TEST_CATEGORY)
        return self.returns[mask]

    def events(self) -> pd.DataFrame:
        """net_events() with fiscal year / week / period / quarter attached to the business date; computed once."""
        if getattr(self, "_events", None) is None:
            self._events = self.fiscal(self.net_events(), "date")
        return self._events

    def net_events(self) -> pd.DataFrame:
        """Net-sales events (sales at business date, returns negative at return date) with every attribute a recomputation needs."""
        s = self.in_scope_sales()
        r = self.in_scope_returns()
        sales = pd.DataFrame({
            "date": s.business_date, "store_id": s.store_id, "store_key": s.store_key, "sku": s.sku, "product_key": s.product_key,
            "net_c": s.net_c, "cost_c": s.cost_c, "is_return": False, "is_web": s.is_web, "region_was": s.region_was,
            "region": s.current_region, "format": s.current_format, "category": s.current_category,
            "subcategory": s.current_subcategory, "category_was": s.category_was, "gross_c": s.gross_c})
        returns = pd.DataFrame({
            "date": r.business_date, "store_id": r.store_id, "store_key": r.store_key, "sku": r.sku, "product_key": r.product_key,
            "net_c": -r.refund_net_c, "cost_c": -r.cost_c, "is_return": True, "is_web": r.store_id == cfg.WEB_STORE_ID,
            "region_was": r.region_was, "region": r.current_region, "format": r.current_format, "category": r.current_category,
            "subcategory": r.current_subcategory, "category_was": r.category_was, "gross_c": -r.refund_gross_c})
        return pd.concat([sales, returns], ignore_index=True)


# ---------------------------------------------------------------------------
# 3. Comparing results
# ---------------------------------------------------------------------------

def clean_value(value):
    """JSON-friendly scalar."""
    if value is None:
        return None
    if isinstance(value, (Decimal,)):
        return float(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if (isinstance(value, float) and math.isnan(value)) else float(value)
    if isinstance(value, (pd.Timestamp, date)):
        return value.date().isoformat() if isinstance(value, pd.Timestamp) else value.isoformat()
    if isinstance(value, np.bool_):
        return bool(value)
    if value is pd.NaT:
        return None
    return value


def frame_to_rows(frame: pd.DataFrame) -> list[list]:
    return [[clean_value(v) for v in row] for row in frame.itertuples(index=False, name=None)]


def values_close(a, b, unit: str) -> bool:
    """Marking tolerance: 0.1% relative, 0.1 percentage points for percentages."""
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, str) or isinstance(b, str):
        return str(a) == str(b)
    try:
        fa, fb = float(a), float(b)
    except (TypeError, ValueError):
        return str(a) == str(b)
    if unit == "pct":
        return abs(fa - fb) <= cfg.MARKING_PCT_TOLERANCE
    return abs(fa - fb) <= max(cfg.MARKING_REL_TOLERANCE * max(abs(fa), abs(fb)), 0.0051 if unit == "eur" else 1e-9)


def tolerance_scaled(a, b, unit: str, factor: float) -> bool:
    """True when a and b are within `factor` x the marking tolerance (used by the bite test with factor = 10)."""
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, str) or isinstance(b, str):
        return str(a) == str(b)
    fa, fb = float(a), float(b)
    if unit == "pct":
        return abs(fa - fb) <= cfg.MARKING_PCT_TOLERANCE * factor
    return abs(fa - fb) <= factor * cfg.MARKING_REL_TOLERANCE * max(abs(fa), abs(fb), 1e-9)


def compare_tables(left: pd.DataFrame, right: pd.DataFrame, columns: list[dict], factor: float | None = None) -> tuple[bool, str]:
    """Compare two result tables the way the marker will: dimensions as the row key, measures within tolerance.

    `columns` is the key's column spec [{"name", "role": "dimension"|"measure", "unit"}]. Rows are matched on the
    dimension columns, order-insensitive. With `factor` set, measures only count as equal inside factor x tolerance
    (the bite test asks whether a naive variant is further away than that). Returns (equal, why_not).
    """
    names = [c["name"] for c in columns]
    if list(left.columns) != names or list(right.columns) != names:
        return False, f"column mismatch {list(left.columns)} vs {list(right.columns)} vs spec {names}"
    if len(left) != len(right):
        return False, f"row count {len(left)} vs {len(right)}"
    dims = [c["name"] for c in columns if c["role"] == "dimension"]
    measures = [c for c in columns if c["role"] == "measure"]

    def keyed(frame: pd.DataFrame):
        out = {}
        for row in frame.to_dict("records"):
            key = tuple(str(clean_value(row[d])) for d in dims)
            if key in out:
                raise ValueError(f"duplicate dimension key {key}")
            out[key] = row
        return out

    if not dims:
        left_rows = {("",): left.to_dict("records")[0]}
        right_rows = {("",): right.to_dict("records")[0]}
    else:
        left_rows, right_rows = keyed(left), keyed(right)
    if set(left_rows) != set(right_rows):
        only_left = sorted(set(left_rows) - set(right_rows))[:3]
        only_right = sorted(set(right_rows) - set(left_rows))[:3]
        return False, f"row keys differ: only left {only_left}, only right {only_right}"
    for key, lrow in left_rows.items():
        rrow = right_rows[key]
        for column in measures:
            a, b = clean_value(lrow[column["name"]]), clean_value(rrow[column["name"]])
            ok = values_close(a, b, column["unit"]) if factor is None else tolerance_scaled(a, b, column["unit"], factor)
            if not ok:
                return False, f"{key} {column['name']}: {a} vs {b}"
    return True, ""


# ---------------------------------------------------------------------------
# 4. Keyword rules and plain-English formatting (used by the key, the review sheet and the validator)
# ---------------------------------------------------------------------------

def keyword_rule_match(groups: list, text: str) -> bool:
    """A pre-written keyword rule: every group must have at least one of its words in the text (case-insensitive)."""
    lowered = text.lower()
    return all(any(word.lower() in lowered for word in group) for group in groups)


def format_value(value, unit: str) -> str:
    """Human-readable number for the review sheet."""
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    if unit == "eur":
        return f"{value:,.2f}"
    if unit == "pct":
        return f"{value:,.2f} %"
    if unit == "ratio":
        return f"{value:,.2f}"
    if unit == "count":
        return f"{value:,.0f}" if float(value) == int(value) else f"{value:,.2f}"
    return str(value)


def describe_difference(reference: pd.DataFrame, other: pd.DataFrame, columns: list) -> str:
    """One short sentence: how a naive result differs from the reference (the biggest gap, or the rows that differ)."""
    dims = [c["name"] for c in columns if c["role"] == "dimension"]
    measures = [c for c in columns if c["role"] == "measure"]
    if len(other) == 0:
        return "returns no rows"
    ref_rows = {tuple(str(clean_value(r[d])) for d in dims): r for r in reference.to_dict("records")} if dims else {(): reference.to_dict("records")[0]}
    other_rows = {tuple(str(clean_value(r[d])) for d in dims): r for r in other.to_dict("records")} if dims else {(): other.to_dict("records")[0]}
    extra, missing = set(other_rows) - set(ref_rows), set(ref_rows) - set(other_rows)
    parts = []
    if extra:
        parts.append("has " + ", ".join(sorted(" ".join(k) for k in extra)[:3]) + " that should not be there")
    if missing:
        parts.append("is missing " + ", ".join(sorted(" ".join(k) for k in missing)[:3]))
    best = None
    for key in sorted(set(ref_rows) & set(other_rows)):   # sorted so ties between equal gaps resolve the same way on every run
        for column in measures:
            a, b = clean_value(ref_rows[key][column["name"]]), clean_value(other_rows[key][column["name"]])
            if a is None or b is None or isinstance(a, str):
                continue
            gap = abs(float(a) - float(b)) / max(abs(float(a)), 1e-9) if column["unit"] != "pct" else abs(float(a) - float(b)) / 100
            if best is None or gap > best[0]:
                best = (gap, key, column, a, b)
    if best and best[0] > 0:   # only mention a value gap when there is one (an extra or missing row is reported above)
        _, key, column, a, b = best
        where = (" ".join(key) + ", ") if key and key != ("",) else ""
        label = column["name"].replace("_ty", " (year asked about)").replace("_ly", " (year before)").replace("_", " ")
        parts.append(f"{where}{label} comes out as {format_value(b, column['unit'])} instead of {format_value(a, column['unit'])}")
    return "; ".join(parts) if parts else "differs"
