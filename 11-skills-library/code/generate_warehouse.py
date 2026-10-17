"""Generate the Tuomimetsa Oy warehouse (Project 11, Phase 2).

Run from anywhere:  python code/generate_warehouse.py
Options:            --out PATH      write the DuckDB file elsewhere (used by the determinism check)
                    --no-internal   do not write the held-out clean tables (determinism check)

What it does, in order (every number comes from config.py, seeded by RANDOM_SEED):
  1. calendar        dim_date, ref_fiscal_calendar
  2. stores          dim_store (SCD2), ref_store_closure, trading matrix
  3. products        dim_product (SCD2), SKU master
  4. members         dim_member (SCD2), member behaviour
  5. campaigns       dim_campaign, campaign_holdout, fact_campaign_exposure
  6. sales           store receipts and web orders -> fact_sales_line, fact_web_order
  7. returns         fact_return_line
  8. stock           fact_stock_week
  9. control totals  rpt_daily_store_sales (from the CLEAN data)
 10. incidents       the four undocumented incidents are applied to the published tables
 11. clutter         staging, backup, temporary and legacy objects, views
 12. write           DuckDB file, schema comments, content hash, manifest

The clean (pre-incident) tables are written to data/internal/ for the answer
key's independent recomputation. data/internal/ is held out: no arm sees it.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

import config as cfg
import schema_comments
from wh_common import (compute_content_hash, day_offset, file_sha256, helsinki_local_to_utc, log,
                       make_version_index, resolve_version, utc_to_helsinki_local)

# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------


def to_day(value) -> pd.Timestamp:
    return pd.Timestamp(value)


def easter_sunday(year: int) -> date:
    """Western Easter Sunday (anonymous Gregorian algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def finnish_holidays(year: int) -> dict:
    """Finnish public holidays for one year as {date: name}."""
    easter = easter_sunday(year)
    holidays = {
        date(year, 1, 1): "New Year's Day", date(year, 1, 6): "Epiphany",
        easter - timedelta(days=2): "Good Friday", easter: "Easter Sunday",
        easter + timedelta(days=1): "Easter Monday", date(year, 5, 1): "May Day",
        easter + timedelta(days=39): "Ascension Day", easter + timedelta(days=49): "Whit Sunday",
        date(year, 12, 6): "Independence Day", date(year, 12, 24): "Christmas Eve",
        date(year, 12, 25): "Christmas Day", date(year, 12, 26): "Boxing Day",
    }
    for day_of_month in range(19, 26):          # Midsummer Eve: the Friday between 19 and 25 June
        if date(year, 6, day_of_month).weekday() == 4:
            holidays[date(year, 6, day_of_month)] = "Midsummer Eve"
            holidays[date(year, 6, day_of_month + 1)] = "Midsummer Day"
    for offset in range(0, 7):                  # All Saints' Day: the Saturday from 31 Oct to 6 Nov
        candidate = date(year, 10, 31) + timedelta(days=offset)
        if candidate.weekday() == 5:
            holidays[candidate] = "All Saints' Day"
    return holidays


# ---------------------------------------------------------------------------
# 1. Calendar
# ---------------------------------------------------------------------------

def build_calendar():
    """Build dim_date, ref_fiscal_calendar and day-level arrays for the generators."""
    log("Building the fiscal calendar")
    days = pd.date_range(cfg.WINDOW_START, cfg.WINDOW_END, freq="D")
    holidays = {}
    for year in range(cfg.WINDOW_START.year, cfg.WINDOW_END.year + 1):
        holidays.update(finnish_holidays(year))
    year_starts = sorted(cfg.FISCAL_YEAR_STARTS.items(), key=lambda item: item[1])
    cumulative_weeks = np.cumsum(cfg.PERIOD_WEEKS_445)

    rows = []
    for day in days:
        current = day.date()
        start_year, year_start = [(y, s) for y, s in year_starts if s <= current][-1]
        fiscal_week = (current - year_start).days // 7 + 1
        period = min(int(np.searchsorted(cumulative_weeks, fiscal_week)) + 1, 12)
        quarter = (period - 1) // 3 + 1
        week_start = current - timedelta(days=current.weekday())
        holiday_name = holidays.get(current)
        rows.append({
            "calendar_date": current,
            "day_of_week": current.isoweekday(),
            "day_name": day.day_name(),
            "calendar_year": current.year,
            "calendar_month": current.month,
            "fiscal_year": f"FY{start_year}/{str(start_year + 1)[2:]}",
            "fiscal_year_start_date": year_start,
            "fiscal_quarter": quarter,
            "fiscal_period": period,
            "fiscal_period_label": f"FY{start_year}/{str(start_year + 1)[2:]} P{period:02d}",
            "fiscal_week": fiscal_week,
            "fiscal_week_start_date": week_start,
            "fiscal_week_end_date": week_start + timedelta(days=6),
            "weeks_in_fiscal_year": cfg.FISCAL_YEAR_WEEKS[start_year],
            "is_53_week_year": cfg.FISCAL_YEAR_WEEKS[start_year] == 53,
            "is_public_holiday": holiday_name is not None,
            "holiday_name": holiday_name,
            "is_trading_day": holiday_name not in cfg.STORE_CLOSED_HOLIDAYS,
        })
    dim_date = pd.DataFrame(rows)

    # One row per fiscal period that starts inside the window (the last one is part-loaded).
    period_rows = []
    for start_year, year_start in year_starts:
        week_count = cfg.FISCAL_YEAR_WEEKS[start_year]
        week_cursor = 0
        for period_index, weeks in enumerate(cfg.PERIOD_WEEKS_445, start=1):
            if period_index == 12 and week_count == 53:
                weeks += 1
            period_start = year_start + timedelta(days=7 * week_cursor)
            if period_start > cfg.WINDOW_END:
                break
            period_end = period_start + timedelta(days=7 * weeks - 1)
            period_rows.append({
                "fiscal_year": f"FY{start_year}/{str(start_year + 1)[2:]}",
                "fiscal_period": period_index,
                "fiscal_quarter": (period_index - 1) // 3 + 1,
                "fiscal_period_label": f"FY{start_year}/{str(start_year + 1)[2:]} P{period_index:02d}",
                "period_start_date": period_start,
                "period_end_date": period_end,
                "weeks_in_period": weeks,
                "first_fiscal_week": week_cursor + 1,
                "last_fiscal_week": week_cursor + weeks,
                "fully_loaded": period_end <= cfg.WINDOW_END,
            })
            week_cursor += weeks
    ref_fiscal = pd.DataFrame(period_rows)

    calendar = {
        "days": days,
        "n_days": len(days),
        "weekday": days.weekday.to_numpy(),
        "month": days.month.to_numpy(),
        "month_id": ((days.year - 2024) * 12 + (days.month - 1)).to_numpy(),
        "is_trading_day": dim_date["is_trading_day"].to_numpy(),
        "holiday_name": dim_date["holiday_name"].to_numpy(),
        "fiscal_year_index": np.array([[y for y, s in year_starts if s <= d.date()][-1] for d in days]),
        "n_weeks": len(days) // 7,
    }
    assert len(days) % 7 == 0, "The window must be a whole number of Monday-Sunday weeks."
    return dim_date, ref_fiscal, calendar


# ---------------------------------------------------------------------------
# 2. Locations (stores, web shop, training store)
# ---------------------------------------------------------------------------

def build_locations(rng, calendar):
    """dim_store versions, closures, trading matrix and per-location parameters."""
    log("Building stores and the trading matrix")
    n_days = calendar["n_days"]
    locations = []
    for loc_idx, (store_id, name, city, region_old, region_new, fmt, open_date, close_date) in enumerate(cfg.STORES):
        low, high = cfg.STORE_SQM_BY_FORMAT[fmt]
        locations.append({
            "loc_idx": loc_idx, "store_id": store_id, "store_name": name, "city": city, "region_old": region_old,
            "region_new": region_new, "format": fmt, "open_date": open_date, "close_date": close_date,
            "sqm": int(rng.integers(low, high + 1)),
            "size_factor": float(np.exp(rng.normal(0, cfg.STORE_FACTOR_SIGMA))),
            "annual_growth": float(rng.normal(cfg.STORE_ANNUAL_GROWTH_MEAN, cfg.STORE_ANNUAL_GROWTH_SIGMA)),
            "kind": "store",
        })
    n_physical = len(locations)
    web_idx, training_idx = n_physical, n_physical + 1
    locations.append({"loc_idx": web_idx, "store_id": cfg.WEB_STORE_ID, "store_name": "Tuomimetsä web shop", "city": "Tampere",
                      "region_old": "Online", "region_new": "Online", "format": "Web", "open_date": None, "close_date": None,
                      "sqm": None, "size_factor": 1.0, "annual_growth": 0.0, "kind": "web"})
    locations.append({"loc_idx": training_idx, "store_id": cfg.TRAINING_STORE_ID, "store_name": "Training store", "city": "Tampere",
                      "region_old": "Head office", "region_new": "Head office", "format": "Training", "open_date": None,
                      "close_date": None, "sqm": None, "size_factor": 1.0, "annual_growth": 0.0, "kind": "training"})

    # dim_store versions: one version per store, two where the region changed on 28 Apr 2025.
    version_rows = []
    for loc in locations:
        first_from = loc["open_date"] or cfg.FIRST_VERSION_VALID_FROM
        if loc["region_old"] != loc["region_new"]:
            splits = [(first_from, cfg.REGION_REORG_DATE - timedelta(days=1), loc["region_old"]),
                      (cfg.REGION_REORG_DATE, cfg.OPEN_ENDED_DATE, loc["region_new"])]
        else:
            splits = [(first_from, cfg.OPEN_ENDED_DATE, loc["region_new"])]
        for valid_from, valid_to, region in splits:
            version_rows.append({
                "store_id": loc["store_id"], "store_name": loc["store_name"], "city": loc["city"], "region": region,
                "format": loc["format"], "sqm": loc["sqm"], "open_date": loc["open_date"], "close_date": loc["close_date"],
                "valid_from": valid_from, "valid_to": valid_to, "is_current": valid_to == cfg.OPEN_ENDED_DATE,
                "loc_idx": loc["loc_idx"],
            })
    dim_store = pd.DataFrame(version_rows).sort_values(["store_id", "valid_from"]).reset_index(drop=True)
    dim_store.insert(0, "store_key", np.arange(1, len(dim_store) + 1))

    store_index = make_version_index(
        dim_store["loc_idx"].to_numpy(),
        np.array([day_offset(v) for v in dim_store["valid_from"]]),
        dim_store["store_key"].to_numpy())

    # Refit closures (whole fiscal weeks) become ref_store_closure.
    closure_rows = []
    for closure_id, (store_id, start, end) in enumerate(cfg.REFITS, start=1):
        closure_rows.append({"closure_id": closure_id, "store_id": store_id, "closure_type": "refit",
                             "closure_start_date": start, "closure_end_date": end,
                             "weeks_closed": ((end - start).days + 1) // 7})
    ref_store_closure = pd.DataFrame(closure_rows)

    # Trading matrix: can the location transact on this day? (stores, training store)
    open_matrix = np.zeros((len(locations), n_days), dtype=bool)
    days_dates = [d.date() for d in calendar["days"]]
    for loc in locations:
        if loc["kind"] == "web":
            open_matrix[loc["loc_idx"], :] = True
            continue
        for day_index, current in enumerate(days_dates):
            if not calendar["is_trading_day"][day_index]:
                continue
            if loc["kind"] == "training":
                open_matrix[loc["loc_idx"], day_index] = calendar["weekday"][day_index] < 5
                continue
            if loc["open_date"] and current < loc["open_date"]:
                continue
            if loc["close_date"] and current > loc["close_date"]:
                continue
            open_matrix[loc["loc_idx"], day_index] = True
    for store_id, start, end in cfg.REFITS:
        loc_idx = [l["loc_idx"] for l in locations if l["store_id"] == store_id][0]
        open_matrix[loc_idx, day_offset(start):day_offset(end) + 1] = False

    return {
        "locations": locations, "dim_store": dim_store, "store_index": store_index, "ref_store_closure": ref_store_closure,
        "open_matrix": open_matrix, "n_physical": n_physical, "web_idx": web_idx, "training_idx": training_idx,
        "store_ids": np.array([l["store_id"] for l in locations]),
    }


# ---------------------------------------------------------------------------
# 3. Products
# ---------------------------------------------------------------------------

def build_products(rng, calendar):
    """SKU master and dim_product versions."""
    log("Building the product master")
    blueprint = cfg.SUBCATEGORIES
    n_regular = cfg.N_SKUS_TOTAL - cfg.N_TEST_SKUS
    blueprint_total = sum(item[2] for item in blueprint)
    counts = [int(round(item[2] * n_regular / blueprint_total)) for item in blueprint]
    counts[int(np.argmax(counts))] += n_regular - sum(counts)

    season_names = list(cfg.SEASON_PROFILES.keys())
    subcat_rows = []
    sku_rows = []
    sku_number = cfg.SKU_FIRST_NUMBER
    month_starts = [date(2024, 6, 1) + timedelta(days=0)]
    first_of_month_choices = pd.date_range("2024-06-01", "2026-06-01", freq="MS").date
    delist_choices = pd.date_range("2024-12-01", "2026-08-01", freq="MS").date
    for subcat_index, (item, count) in enumerate(zip(blueprint, counts)):
        category, subcategory, _, median_price, margin_mean, qty_mean, popularity, season, return_rate, vat_class, bulky = item
        subcat_rows.append({"category": category, "subcategory": subcategory, "season": season, "return_rate": return_rate,
                            "qty_mean": qty_mean, "bulky": bulky})
        prices = median_price * np.exp(rng.normal(0, cfg.SKU_PRICE_SIGMA, count))
        margins = np.clip(margin_mean + rng.normal(0, cfg.SKU_MARGIN_NOISE, count), 0.12, 0.75)
        pops = popularity * np.exp(rng.normal(0, cfg.SKU_POPULARITY_SIGMA, count))
        own_label = rng.random(count) < cfg.OWN_LABEL_SHARE
        brand_draw = rng.integers(0, len(cfg.BRANDS), count)
        own_draw = rng.integers(0, len(cfg.OWN_LABEL_BRANDS), count)
        lifecycle = rng.random(count)
        for k in range(count):
            unit_net = max(int(round(prices[k] * 100)), 50)
            unit_cost = max(int(round(unit_net * (1 - margins[k]))), 20)
            brand = cfg.OWN_LABEL_BRANDS[own_draw[k]] if own_label[k] else cfg.BRANDS[brand_draw[k]]
            listed_from = date(2019, 1, 1)
            delisted_on = None
            if lifecycle[k] < cfg.SKU_INTRODUCED_DURING_WINDOW_SHARE:
                listed_from = first_of_month_choices[int(rng.integers(0, len(first_of_month_choices)))]
            elif lifecycle[k] > 1 - cfg.SKU_DELISTED_DURING_WINDOW_SHARE:
                delisted_on = delist_choices[int(rng.integers(0, len(delist_choices)))]
            sku_rows.append({
                "sku": sku_number, "subcat_idx": subcat_index, "category": category, "subcategory": subcategory,
                "brand": brand, "own_label_flag": bool(own_label[k]), "vat_class": vat_class,
                "unit_net_cents": unit_net, "unit_cost_cents": unit_cost, "popularity": float(pops[k]),
                "listed_from": listed_from, "delisted_on": delisted_on, "is_test": False,
            })
            sku_number += 1
    # Test articles: category "ZZ Test", listed throughout.
    test_subcat_index = len(blueprint)
    subcat_rows.append({"category": cfg.TEST_CATEGORY, "subcategory": "Test Articles", "season": "flat", "return_rate": 0.0,
                        "qty_mean": 1.0, "bulky": False})
    for k in range(cfg.N_TEST_SKUS):
        sku_rows.append({
            "sku": sku_number, "subcat_idx": test_subcat_index, "category": cfg.TEST_CATEGORY, "subcategory": "Test Articles",
            "brand": "TEST", "own_label_flag": False, "vat_class": "standard", "unit_net_cents": 100 + 50 * k,
            "unit_cost_cents": 50, "popularity": 0.0, "listed_from": date(2019, 1, 1), "delisted_on": None, "is_test": True,
        })
        sku_number += 1
    skus = pd.DataFrame(sku_rows)
    skus["sku_idx"] = np.arange(len(skus))
    skus["product_name"] = [
        f"TEST ARTICLE {i + 1:02d}" if t else f"{s} {b} {200 + (i * 37) % 800}"
        for i, (t, s, b) in enumerate(zip(skus["is_test"], skus["subcategory"], skus["brand"]))]

    # dim_product versions: outdoor lighting changes category; some SKUs get a brand rename.
    rename_candidates = skus[(~skus["is_test"]) & (~skus["own_label_flag"]) &
                             (skus["subcategory"] != cfg.OUTDOOR_LIGHTING_SUBCATEGORY) &
                             (skus["listed_from"] == date(2019, 1, 1)) & (skus["delisted_on"].isna())]
    rename_skus = rng.choice(rename_candidates["sku"].to_numpy(), size=cfg.BRAND_RENAME_SKU_COUNT, replace=False)
    rename_dates = pd.date_range("2024-09-02", "2026-03-02", freq="W-MON").date
    rename_map = {int(s): rename_dates[int(rng.integers(0, len(rename_dates)))] for s in rename_skus}

    version_rows = []
    for row in skus.itertuples():
        base_from = row.listed_from if row.listed_from > cfg.WINDOW_START else cfg.FIRST_VERSION_VALID_FROM
        splits = []
        category = row.category
        if row.subcategory == cfg.OUTDOOR_LIGHTING_SUBCATEGORY:
            moves_inside = (base_from < cfg.CATEGORY_MOVE_DATE) and (row.delisted_on is None or row.delisted_on > cfg.CATEGORY_MOVE_DATE)
            if moves_inside:
                splits = [(base_from, cfg.CATEGORY_MOVE_DATE - timedelta(days=1), "Garden", row.brand),
                          (cfg.CATEGORY_MOVE_DATE, cfg.OPEN_ENDED_DATE, "Electrical", row.brand)]
            elif base_from >= cfg.CATEGORY_MOVE_DATE:
                splits = [(base_from, cfg.OPEN_ENDED_DATE, "Electrical", row.brand)]
            else:
                splits = [(base_from, cfg.OPEN_ENDED_DATE, "Garden", row.brand)]
        elif int(row.sku) in rename_map:
            changed = rename_map[int(row.sku)]
            splits = [(base_from, changed - timedelta(days=1), category, row.brand),
                      (changed, cfg.OPEN_ENDED_DATE, category, f"{row.brand} Nordic")]
        else:
            splits = [(base_from, cfg.OPEN_ENDED_DATE, category, row.brand)]
        for valid_from, valid_to, version_category, version_brand in splits:
            version_rows.append({
                "sku": int(row.sku), "product_name": row.product_name, "category": version_category,
                "subcategory": row.subcategory, "brand": version_brand, "own_label_flag": row.own_label_flag,
                "vat_class": row.vat_class, "standard_unit_cost_cents": row.unit_cost_cents,
                "listed_from": row.listed_from, "delisted_on": row.delisted_on,
                "valid_from": valid_from, "valid_to": valid_to, "is_current": valid_to == cfg.OPEN_ENDED_DATE,
                "sku_idx": int(row.sku_idx),
            })
    dim_product = pd.DataFrame(version_rows).sort_values(["sku", "valid_from"]).reset_index(drop=True)
    dim_product.insert(0, "product_key", np.arange(1, len(dim_product) + 1))
    product_index = make_version_index(
        dim_product["sku_idx"].to_numpy(),
        np.array([day_offset(v) for v in dim_product["valid_from"]]),
        dim_product["product_key"].to_numpy())

    # Per-month listing masks and seasonal weights (month_id 0 = Jan 2024).
    month_ids = sorted(set(calendar["month_id"]))
    listed_by_month = {}
    for month_id in month_ids:
        month_start = date(2024 + month_id // 12, month_id % 12 + 1, 1)
        listed = (skus["listed_from"] <= month_start).to_numpy()
        not_delisted = np.array([(d is None) or (d > month_start) for d in skus["delisted_on"]])
        listed_by_month[month_id] = listed & not_delisted
    subcat_frame = pd.DataFrame(subcat_rows)
    season_matrix = np.array([cfg.SEASON_PROFILES[s] for s in subcat_frame["season"]])
    return {
        "skus": skus, "dim_product": dim_product, "product_index": product_index, "subcats": subcat_frame,
        "season_matrix": season_matrix, "listed_by_month": listed_by_month,
        "popularity": skus["popularity"].to_numpy(), "subcat_idx": skus["subcat_idx"].to_numpy(),
        "bulky": subcat_frame["bulky"].to_numpy()[skus["subcat_idx"].to_numpy()],
        "return_rate": subcat_frame["return_rate"].to_numpy()[skus["subcat_idx"].to_numpy()],
        "qty_mean": subcat_frame["qty_mean"].to_numpy()[skus["subcat_idx"].to_numpy()],
        "test_sku_idx": skus.index[skus["is_test"]].to_numpy(),
    }


# ---------------------------------------------------------------------------
# 4. Members
# ---------------------------------------------------------------------------

TIER_NAMES = ["Basic", "Silver", "Gold"]


def build_members(rng, calendar, world):
    """Members: behaviour parameters and the SCD2 dimension."""
    log("Building loyalty members")
    n = cfg.N_MEMBERS
    n_days = calendar["n_days"]
    physical = world["n_physical"]
    web_idx = world["web_idx"]
    locations = world["locations"]
    open_matrix = world["open_matrix"]

    # Join dates: 40% before the window, the rest across it (slightly seasonal).
    pre_window = rng.random(n) < cfg.MEMBER_PRE_WINDOW_SHARE
    first_offset = day_offset(cfg.MEMBER_PRE_WINDOW_FIRST_DATE)
    join_offset = np.where(pre_window, rng.integers(first_offset, 0, n), 0)
    month_weights = np.array([cfg.MONTH_VOLUME_INDEX[m - 1] for m in calendar["month"]])
    in_window_draw = rng.choice(n_days, size=n, p=month_weights / month_weights.sum())
    join_offset = np.where(pre_window, join_offset, in_window_draw)

    # Activity, web trait, churn.
    activity = rng.gamma(cfg.MEMBER_ACTIVITY_GAMMA_SHAPE, 1.0 / cfg.MEMBER_ACTIVITY_GAMMA_SHAPE, n)
    web_trait = np.exp(rng.normal(0, cfg.MEMBER_WEB_TRAIT_SIGMA, n))
    churns = rng.random(n) < cfg.MEMBER_CHURN_SHARE
    churn_offset = np.where(churns, np.maximum(join_offset, 0) + rng.integers(60, n_days, n), 10**6)

    # Initial tier follows activity (heavier shoppers sit higher), with noise.
    score = activity * np.exp(rng.normal(0, 0.6, n))
    gold_cut = np.quantile(score, 1 - cfg.MEMBER_TIER_SHARES["Gold"])
    silver_cut = np.quantile(score, 1 - cfg.MEMBER_TIER_SHARES["Gold"] - cfg.MEMBER_TIER_SHARES["Silver"])
    tier0 = np.where(score >= gold_cut, 2, np.where(score >= silver_cut, 1, 0))

    # Home store at enrolment: online (web shop) or a store open on the join date, weighted by store size.
    store_weights = np.array([l["size_factor"] * cfg.RECEIPTS_PER_DAY_BY_FORMAT[l["format"]] for l in locations[:physical]])
    store_weights /= store_weights.sum()
    home0 = rng.choice(physical, size=n, p=store_weights)
    for _ in range(30):                                     # redraw stores that were not yet open / already closed
        join_day = np.clip(join_offset, 0, n_days - 1)
        invalid = ~open_matrix[home0, join_day]
        # a store that is merely closed on a holiday is fine; only redraw if it is outside its life span
        life_invalid = np.array([_outside_life(locations[h], int(j)) for h, j in zip(home0[invalid], join_day[invalid])]) \
            if invalid.any() else np.array([], dtype=bool)
        if not invalid.any() or not life_invalid.any():
            break
        redraw_positions = np.flatnonzero(invalid)[life_invalid]
        home0[redraw_positions] = rng.choice(physical, size=len(redraw_positions), p=store_weights)
    online = rng.random(n) < cfg.MEMBER_ONLINE_ENROL_SHARE
    home0 = np.where(online, web_idx, home0)

    consent0 = rng.random(n) < cfg.MEMBER_CONSENT_INITIAL_SHARE
    end_offset = n_days - 1

    def after_join(low_gap: int, size: int, members: np.ndarray) -> np.ndarray:
        """Random event dates between (join + low_gap) and the window end."""
        low = np.maximum(join_offset[members], 0) + low_gap
        high = np.full(len(members), end_offset)
        valid = low < high
        draws = np.where(valid, rng.integers(0, 10**6, size) % np.maximum(high - low, 1) + low, -1)
        return draws

    events = []   # (member, offset, tier, home, consent)

    # Tier changes
    tier_members = np.flatnonzero(rng.random(n) < cfg.MEMBER_TIER_CHANGE_SHARE)
    tier_dates = after_join(30, len(tier_members), tier_members)
    for member, event_day in zip(tier_members, tier_dates):
        if event_day < 0:
            continue
        current = tier0[member]
        new_tier = 1 if current == 0 else (2 if current == 1 and rng.random() < 0.6 else (0 if current == 1 else 1))
        events.append((member, int(event_day), new_tier, np.nan, np.nan))

    # Consent withdrawals and opt-ins
    withdraw = consent0 & (rng.random(n) < cfg.MEMBER_CONSENT_WITHDRAW_SHARE)
    optin = (~consent0) & (rng.random(n) < cfg.MEMBER_CONSENT_OPTIN_SHARE)
    for mask, new_value in ((withdraw, 0.0), (optin, 1.0)):
        members = np.flatnonzero(mask)
        dates = after_join(30, len(members), members)
        for member, event_day in zip(members, dates):
            if event_day >= 0:
                events.append((member, int(event_day), np.nan, np.nan, new_value))

    # Home store: closure transfer, new-store catchment transfers, random moves
    closed_idx = [l["loc_idx"] for l in locations if l["close_date"]][0]
    closed_date = [l["close_date"] for l in locations if l["close_date"]][0]
    transfer_idx = [l["loc_idx"] for l in locations if l["store_id"] == cfg.CLOSED_STORE_MEMBER_TRANSFER_TO][0]
    has_home_event = np.zeros(n, dtype=bool)
    closure_members = np.flatnonzero(home0 == closed_idx)
    for member in closure_members:
        events.append((member, day_offset(closed_date) + 1, np.nan, float(transfer_idx), np.nan))
        has_home_event[member] = True
    for new_store_id, catchment_ids in cfg.NEW_STORE_CATCHMENT.items():
        new_loc = [l for l in locations if l["store_id"] == new_store_id][0]
        catchment_idx = [l["loc_idx"] for l in locations if l["store_id"] in catchment_ids]
        candidates = np.flatnonzero(np.isin(home0, catchment_idx) & ~has_home_event &
                                    (join_offset <= day_offset(new_loc["open_date"])))
        chosen = candidates[rng.random(len(candidates)) < cfg.NEW_STORE_TRANSFER_SHARE]
        for member in chosen:
            events.append((member, day_offset(new_loc["open_date"]) + int(rng.integers(0, 60)), np.nan,
                           float(new_loc["loc_idx"]), np.nan))
            has_home_event[member] = True
    movers = np.flatnonzero((rng.random(n) < cfg.MEMBER_HOME_MOVE_SHARE) & ~has_home_event & (home0 != web_idx))
    move_dates = after_join(30, len(movers), movers)
    for member, event_day in zip(movers, move_dates):
        if event_day < 0:
            continue
        for _ in range(20):
            target = int(rng.choice(physical, p=store_weights))
            if target != home0[member] and target != closed_idx and not _outside_life(locations[target], int(event_day)):
                events.append((member, int(event_day), np.nan, float(target), np.nan))
                break

    # Assemble versions: a base row at the join date plus one row per event, forward-filled.
    base = pd.DataFrame({"member": np.arange(n), "offset": join_offset, "tier": tier0.astype(float),
                         "home": home0.astype(float), "consent": consent0.astype(float), "order": 0})
    event_frame = pd.DataFrame(events, columns=["member", "offset", "tier", "home", "consent"])
    event_frame["order"] = 1
    stacked = pd.concat([base, event_frame], ignore_index=True)
    stacked = stacked.sort_values(["member", "offset", "order"], kind="stable").reset_index(drop=True)
    stacked[["tier", "home", "consent"]] = stacked.groupby("member")[["tier", "home", "consent"]].ffill()
    stacked = stacked.drop_duplicates(["member", "offset"], keep="last").reset_index(drop=True)

    versions = stacked[["member", "offset", "tier", "home", "consent"]].copy()
    versions["next_offset"] = versions.groupby("member")["offset"].shift(-1)
    versions["valid_from"] = [cfg.WINDOW_START + timedelta(days=int(o)) for o in versions["offset"]]
    versions["valid_to"] = [cfg.OPEN_ENDED_DATE if pd.isna(o) else cfg.WINDOW_START + timedelta(days=int(o) - 1)
                            for o in versions["next_offset"]]
    versions["is_current"] = versions["next_offset"].isna()
    versions["member_id"] = 70_000_001 + versions["member"].astype(np.int64)
    versions["tier_name"] = [TIER_NAMES[int(t)] for t in versions["tier"]]
    versions["home_store_id"] = world["store_ids"][versions["home"].astype(int).to_numpy()]
    versions["marketing_consent"] = versions["consent"].astype(bool)
    versions["join_date"] = [cfg.WINDOW_START + timedelta(days=int(j)) for j in join_offset[versions["member"].to_numpy()]]
    versions = versions.sort_values(["member", "offset"]).reset_index(drop=True)
    versions.insert(0, "member_key", np.arange(1, len(versions) + 1))
    member_index = make_version_index(versions["member"].to_numpy(), versions["offset"].to_numpy(), versions["member_key"].to_numpy())

    # Weekly home-store matrix for receipt generation.
    n_weeks = calendar["n_weeks"]
    home_by_week = np.empty((n_weeks, n), dtype=np.int8)
    current_home = home0.astype(np.int8).copy()
    home_events = event_frame[event_frame["home"].notna()].copy()
    home_events["week"] = np.clip(home_events["offset"] // 7, 0, n_weeks - 1)
    home_events = home_events.sort_values("week")
    cursor = 0
    event_weeks = home_events["week"].to_numpy()
    event_members = home_events["member"].to_numpy()
    event_homes = home_events["home"].to_numpy().astype(np.int8)
    event_offsets = home_events["offset"].to_numpy()
    # events apply from their week; apply in date order so later moves win
    order = np.argsort(event_offsets, kind="stable")
    event_weeks, event_members, event_homes = event_weeks[order], event_members[order], event_homes[order]
    for week in range(n_weeks):
        while cursor < len(event_weeks) and event_weeks[cursor] <= week:
            current_home[event_members[cursor]] = event_homes[cursor]
            cursor += 1
        home_by_week[week] = current_home

    return {
        "n": n, "join_offset": join_offset, "churn_offset": churn_offset, "activity": activity, "web_trait": web_trait,
        "versions": versions, "member_index": member_index, "home_by_week": home_by_week, "tier0": tier0,
        "member_ids": 70_000_001 + np.arange(n, dtype=np.int64),
    }


def _outside_life(location: dict, day_index: int) -> bool:
    """True when a store did not exist (not yet open or already closed) on the given day index."""
    current = cfg.WINDOW_START + timedelta(days=int(day_index))
    if location["open_date"] and current < location["open_date"]:
        return True
    if location["close_date"] and current > location["close_date"]:
        return True
    return False


def member_state_at(members, member_idx: np.ndarray, day_offsets) -> dict:
    """Tier, home store index and marketing consent for members on given day offsets."""
    keys = resolve_version(members["member_index"], member_idx, day_offsets)
    rows = members["versions"].iloc[keys - 1]
    return {"member_key": keys, "tier": rows["tier"].to_numpy().astype(int), "home": rows["home"].to_numpy().astype(int),
            "consent": rows["marketing_consent"].to_numpy()}


# ---------------------------------------------------------------------------
# 5. Campaigns
# ---------------------------------------------------------------------------

def build_campaigns(rng, calendar, world, members):
    """dim_campaign, campaign_holdout, fact_campaign_exposure and per-member first-exposure offsets."""
    log("Building campaigns, holdouts and exposures")
    n = members["n"]
    region_by_key = world["dim_store"].set_index("store_key")["region"]
    store_index = world["store_index"]
    campaign_rows, holdout_rows, exposure_chunks = [], [], []
    first_exposure = {}
    contacts_options = np.array(list(cfg.CAMPAIGN_CONTACTS_PER_MEMBER.keys()))
    contacts_probs = np.array(list(cfg.CAMPAIGN_CONTACTS_PER_MEMBER.values()))
    all_members = np.arange(n)
    for campaign_id, name, start, end, channels, segment, uplift, target_fraction in cfg.CAMPAIGNS:
        start_off, end_off = day_offset(start), day_offset(end)
        state = member_state_at(members, all_members, np.full(n, start_off))
        eligible = (members["join_offset"] <= start_off) & state["consent"]
        if segment == "silver_gold":
            eligible &= state["tier"] >= 1
        elif segment == "new_members_12m":
            eligible &= members["join_offset"] >= start_off - 365
        elif segment in ("region_north_east", "region_capital_south"):
            home_store_keys = resolve_version(store_index, state["home"], np.full(n, start_off))
            regions = region_by_key.loc[home_store_keys].to_numpy()
            wanted = {"North", "East"} if segment == "region_north_east" else {"Capital Region", "South"}
            eligible &= np.isin(regions, list(wanted))
        eligible_members = np.flatnonzero(eligible)
        fraction = target_fraction if target_fraction else cfg.CAMPAIGN_DEFAULT_TARGET_FRACTION
        mailing_list = eligible_members[rng.random(len(eligible_members)) < fraction]
        is_holdout = rng.random(len(mailing_list)) < cfg.CAMPAIGN_HOLDOUT_SHARE
        held_out, contacted = mailing_list[is_holdout], mailing_list[~is_holdout]
        for member in held_out:
            holdout_rows.append((campaign_id, int(members["member_ids"][member])))

        # Contacts: 1-4 per contacted member, spread across the campaign window, consent checked on the date.
        contact_counts = rng.choice(contacts_options, size=len(contacted), p=contacts_probs)
        contact_members = np.repeat(contacted, contact_counts)
        window_days = end_off - start_off + 1
        contact_offsets = start_off + rng.integers(0, window_days, len(contact_members))
        contact_state = member_state_at(members, contact_members, contact_offsets)
        keep = contact_state["consent"]
        contact_members, contact_offsets = contact_members[keep], contact_offsets[keep]
        contact_keys = contact_state["member_key"][keep]
        local_seconds = rng.integers(8 * 3600, 20 * 3600, len(contact_members))
        local_ts = pd.to_datetime(cfg.WINDOW_START) + pd.to_timedelta(contact_offsets, unit="D") + pd.to_timedelta(local_seconds, unit="s")
        contact_ts_utc = helsinki_local_to_utc(pd.Series(local_ts))
        channel_choice = np.array(channels)[rng.integers(0, len(channels), len(contact_members))]
        delivered = rng.random(len(contact_members)) < 0.96
        open_rate = np.where(channel_choice == "email", 0.32, np.where(channel_choice == "sms", 0.70, 0.20))
        opened = delivered & (rng.random(len(contact_members)) < open_rate)
        exposure_chunks.append(pd.DataFrame({
            "campaign_id": campaign_id, "member_key": contact_keys, "contact_ts_utc": contact_ts_utc.to_numpy(),
            "contact_channel": channel_choice, "delivered": delivered, "opened": opened, "member_idx": contact_members,
            "contact_offset": contact_offsets}))

        first = np.full(n, 10**7, dtype=np.int64)
        if len(contact_members):
            np.minimum.at(first, contact_members, contact_offsets)
        first_exposure[campaign_id] = first
        campaign_rows.append({
            "campaign_id": campaign_id, "campaign_name": name, "start_date": start, "end_date": end,
            "channels": "+".join(channels), "target_group": cfg.CAMPAIGN_SEGMENT_DESCRIPTIONS[segment],
            "holdout_pct": cfg.CAMPAIGN_HOLDOUT_SHARE, "mailing_list_size": int(len(mailing_list)),
            "holdout_size": int(len(held_out)), "true_uplift": uplift, "segment": segment,
        })
    exposures = pd.concat(exposure_chunks, ignore_index=True).sort_values(["contact_ts_utc", "campaign_id", "member_key"]).reset_index(drop=True)
    exposures.insert(0, "exposure_id", np.arange(1, len(exposures) + 1))
    return {
        "dim_campaign": pd.DataFrame(campaign_rows),
        "campaign_holdout": pd.DataFrame(holdout_rows, columns=["campaign_id", "member_id"]),
        "exposures": exposures, "first_exposure": first_exposure,
    }


# ---------------------------------------------------------------------------
# 6. Sales: store receipts and web orders
# ---------------------------------------------------------------------------

def expected_store_receipts(calendar, world):
    """Expected receipts per physical store per day, before Poisson noise."""
    n_days = calendar["n_days"]
    physical = world["n_physical"]
    locations = world["locations"]
    open_matrix = world["open_matrix"]
    days = calendar["days"]
    years_elapsed = np.arange(n_days) / 365.25
    month_index = np.array([cfg.MONTH_VOLUME_INDEX[m - 1] for m in calendar["month"]])
    weekday_index = np.array([cfg.WEEKDAY_VOLUME_INDEX[w] for w in calendar["weekday"]])
    event = np.ones(n_days)
    for i, d in enumerate(days.date):
        if d in cfg.BLACK_FRIDAYS:
            event[i] = cfg.EVENT_VOLUME_MULTIPLIER["black_friday"]
        elif d.month == 12 and d.day == 22:
            event[i] = cfg.EVENT_VOLUME_MULTIPLIER["dec_22"]
        elif d.month == 12 and d.day == 23:
            event[i] = cfg.EVENT_VOLUME_MULTIPLIER["dec_23"]
    expected = np.zeros((physical, n_days))
    for loc in locations[:physical]:
        base = cfg.RECEIPTS_PER_DAY_BY_FORMAT[loc["format"]] * loc["size_factor"]
        series = base * (1 + loc["annual_growth"]) ** years_elapsed * month_index * weekday_index * event
        if loc["open_date"]:                                   # ramp-up of a new store over 52 weeks
            weeks_open = np.maximum((np.arange(n_days) - day_offset(loc["open_date"])) / 7.0, 0)
            series = series * np.minimum(cfg.NEW_STORE_RAMP_START + (1 - cfg.NEW_STORE_RAMP_START) * weeks_open / 52.0, 1.0)
        if loc["close_date"]:                                  # wind-down in the last six weeks
            weeks_to_close = (day_offset(loc["close_date"]) - np.arange(n_days)) / 7.0
            series = np.where((weeks_to_close >= 0) & (weeks_to_close < 6), series * cfg.CLOSING_STORE_FACTOR, series)
        for store_id, start, end in cfg.REFITS:                # post-refit uplift for 26 weeks
            if store_id == loc["store_id"]:
                weeks_after = (np.arange(n_days) - day_offset(end)) / 7.0
                series = np.where((weeks_after > 0) & (weeks_after <= 26), series * (1 + cfg.POST_REFIT_UPLIFT), series)
        expected[loc["loc_idx"]] = series * open_matrix[loc["loc_idx"]]
    return expected


def web_expected_orders(calendar):
    """Expected web orders per day."""
    n_days = calendar["n_days"]
    years = np.arange(n_days) / 365.25
    series = cfg.WEB_ORDERS_PER_DAY_START * (1 + cfg.WEB_ANNUAL_GROWTH) ** years
    series = series * np.array([cfg.MONTH_VOLUME_INDEX[m - 1] for m in calendar["month"]])
    series = series * np.array([cfg.WEB_WEEKDAY_INDEX[w] for w in calendar["weekday"]])
    for i, d in enumerate(calendar["days"].date):
        if d in cfg.BLACK_FRIDAYS:
            series[i] *= cfg.WEB_BLACK_FRIDAY_MULTIPLIER
        elif any(d == bf + timedelta(days=3) for bf in cfg.BLACK_FRIDAYS):
            series[i] *= cfg.WEB_CYBER_MONDAY_MULTIPLIER
        series[i] *= cfg.WEB_EVENT_MULTIPLIER.get(d, 1.0)
    return series


def simulate_receipt_slots(rng, calendar, world, members, campaigns):
    """Decide which receipts and orders exist and which member (if any) is on each."""
    log("Simulating receipt and order slots with member allocation (day loop)")
    n_days, physical = calendar["n_days"], world["n_physical"]
    expected = expected_store_receipts(calendar, world)
    base_counts = rng.poisson(expected)
    member_share = np.linspace(cfg.MEMBER_RECEIPT_SHARE_START, cfg.MEMBER_RECEIPT_SHARE_END, n_days)
    member_base = rng.binomial(base_counts, member_share[None, :])
    web_base = rng.poisson(web_expected_orders(calendar))
    web_logged = rng.binomial(web_base, cfg.WEB_LOGGED_IN_SHARE)

    n = members["n"]
    activity, web_trait = members["activity"], members["web_trait"]
    campaign_defs = {c[0]: c for c in cfg.CAMPAIGNS}
    campaign_windows = [(cid, day_offset(c[2]), day_offset(c[3]) + cfg.CAMPAIGN_UPLIFT_WINDOW_EXTRA_DAYS, c[6])
                        for cid, c in campaign_defs.items()]

    store_picks_day, store_picks_store, store_picks_member = [], [], []
    web_picks_day, web_picks_member = [], []
    extra_store = np.zeros((physical, n_days), dtype=np.int64)
    extra_web = np.zeros(n_days, dtype=np.int64)
    current_week = -1
    order_by_home = starts = ends = None
    for day in range(n_days):
        active = (members["join_offset"] <= day) & (day <= members["churn_offset"])
        boost = np.ones(n)
        for cid, window_start, window_end, uplift in campaign_windows:
            if window_start <= day <= window_end:
                boost = boost + uplift * (campaigns["first_exposure"][cid] <= day)
        base_weight = activity * active
        weight_store = base_weight * boost
        weight_web = base_weight * web_trait * boost
        total_base_store, total_base_web = base_weight.sum(), (base_weight * web_trait).sum()
        factor_store = weight_store.sum() / total_base_store if total_base_store > 0 else 1.0
        factor_web = weight_web.sum() / total_base_web if total_base_web > 0 else 1.0

        week = day // 7
        if week != current_week:                              # candidate lists by home store for this week
            current_week = week
            home_now = members["home_by_week"][week]
            order_by_home = np.argsort(home_now, kind="stable")
            sorted_homes = home_now[order_by_home]
            starts = np.searchsorted(sorted_homes, np.arange(physical), side="left")
            ends = np.searchsorted(sorted_homes, np.arange(physical), side="right")
        cumulative_all = np.cumsum(weight_store)
        total_all = cumulative_all[-1]

        if factor_store > 1.0 + 1e-9:
            extra_store[:, day] = rng.poisson(member_base[:, day] * (factor_store - 1.0))
        k_store = member_base[:, day] + extra_store[:, day]
        for store in np.flatnonzero(k_store > 0):
            k = int(k_store[store])
            candidates = order_by_home[starts[store]:ends[store]]
            n_local = int(rng.binomial(k, cfg.MEMBER_HOME_STORE_PICK_SHARE)) if len(candidates) else 0
            picks = []
            if n_local:
                cumulative_local = np.cumsum(weight_store[candidates])
                if cumulative_local[-1] > 0:
                    picks.append(candidates[np.minimum(np.searchsorted(cumulative_local, rng.random(n_local) * cumulative_local[-1],
                                                                       side="right"), len(candidates) - 1)])
                else:
                    n_local = 0
            n_global = k - (len(picks[0]) if picks else 0)
            if n_global:
                picks.append(np.minimum(np.searchsorted(cumulative_all, rng.random(n_global) * total_all, side="right"), n - 1))
            chosen = np.concatenate(picks)
            store_picks_day.append(np.full(len(chosen), day, dtype=np.int32))
            store_picks_store.append(np.full(len(chosen), store, dtype=np.int16))
            store_picks_member.append(chosen.astype(np.int32))

        if factor_web > 1.0 + 1e-9:
            extra_web[day] = rng.poisson(web_logged[day] * (factor_web - 1.0))
        k_web = int(web_logged[day] + extra_web[day])
        if k_web:
            cumulative_web = np.cumsum(weight_web)
            chosen = np.minimum(np.searchsorted(cumulative_web, rng.random(k_web) * cumulative_web[-1], side="right"), n - 1)
            web_picks_day.append(np.full(k_web, day, dtype=np.int32))
            web_picks_member.append(chosen.astype(np.int32))
        if day % 200 == 0:
            log(f"  day loop {day}/{n_days}")

    return {
        "base_counts": base_counts, "member_base": member_base, "extra_store": extra_store,
        "web_base": web_base, "web_logged": web_logged, "extra_web": extra_web,
        "store_picks": (np.concatenate(store_picks_day), np.concatenate(store_picks_store), np.concatenate(store_picks_member)),
        "web_picks": (np.concatenate(web_picks_day), np.concatenate(web_picks_member)),
    }


def local_to_utc_from_parts(day_offsets: np.ndarray, local_seconds: np.ndarray) -> pd.Series:
    """Helsinki local (day offset, seconds into the day) -> naive UTC timestamps."""
    local = pd.to_datetime(cfg.WINDOW_START) + pd.to_timedelta(day_offsets, unit="D") + pd.to_timedelta(local_seconds, unit="s")
    return helsinki_local_to_utc(pd.Series(local))


def sample_store_seconds(rng, day_offsets: np.ndarray, weekdays: np.ndarray) -> np.ndarray:
    """Local seconds into the day for store receipts, shaped by opening hours (weekday, Saturday, Sunday)."""
    hour_weights = {9: 1.0, 10: 1.6, 11: 2.0, 12: 2.2, 13: 2.0, 14: 1.8, 15: 2.0, 16: 2.4, 17: 2.4, 18: 1.8, 19: 1.2, 20: 0.6}
    seconds = np.zeros(len(day_offsets), dtype=np.int64)
    for key, mask in (("weekday", weekdays < 5), ("saturday", weekdays == 5), ("sunday", weekdays == 6)):
        count = int(mask.sum())
        if not count:
            continue
        start_hour, end_hour = cfg.STORE_OPEN_HOURS_LOCAL[key]
        hours = np.arange(start_hour, end_hour)
        weights = np.array([hour_weights[h] for h in hours])
        chosen = rng.choice(hours, size=count, p=weights / weights.sum())
        seconds[mask] = chosen * 3600 + rng.integers(0, 3600, count)
    return seconds


def build_store_receipts(rng, calendar, world, members, slots):
    """Store receipt headers (including the training store)."""
    log("Building store receipt headers")
    physical = world["n_physical"]
    n_days = calendar["n_days"]
    base_counts, member_base = slots["base_counts"], slots["member_base"]
    non_member = base_counts - member_base
    store_grid, day_grid = np.meshgrid(np.arange(physical), np.arange(n_days), indexing="ij")
    non_member_rows = np.repeat(np.stack([day_grid.ravel(), store_grid.ravel()], axis=1), non_member.ravel(), axis=0)
    picks_day, picks_store, picks_member = slots["store_picks"]
    receipts = pd.DataFrame({
        "day": np.concatenate([non_member_rows[:, 0], picks_day]).astype(np.int32),
        "loc_idx": np.concatenate([non_member_rows[:, 1], picks_store]).astype(np.int16),
        "member_idx": np.concatenate([np.full(len(non_member_rows), -1, dtype=np.int32), picks_member]),
    })
    receipts["staff"] = rng.random(len(receipts)) < cfg.STAFF_RECEIPT_SHARE
    receipts["test_receipt"] = False

    # Training store: weekday receipts, a mix of test-article receipts and staff-flagged ones.
    training_idx = world["training_idx"]
    training_counts = rng.poisson(cfg.TRAINING_STORE_RECEIPTS_PER_DAY * world["open_matrix"][training_idx])
    training_days = np.repeat(np.arange(n_days), training_counts)
    training = pd.DataFrame({"day": training_days.astype(np.int32), "loc_idx": np.int16(training_idx),
                             "member_idx": np.int32(-1)})
    training["test_receipt"] = rng.random(len(training)) < cfg.TRAINING_STORE_TEST_SKU_SHARE
    training["staff"] = ~training["test_receipt"]
    receipts = pd.concat([receipts, training], ignore_index=True)

    receipts["n_lines"] = 1 + rng.poisson(cfg.LINES_PER_RECEIPT_EXTRA_MEAN, len(receipts))
    weekdays = calendar["weekday"][receipts["day"].to_numpy()]
    seconds = sample_store_seconds(rng, receipts["day"].to_numpy(), weekdays)
    receipts["ts_utc"] = local_to_utc_from_parts(receipts["day"].to_numpy(), seconds).to_numpy()
    receipts = receipts.sort_values(["ts_utc", "loc_idx", "member_idx"], kind="stable").reset_index(drop=True)
    receipts["receipt_id"] = 10_000_000 + np.arange(len(receipts), dtype=np.int64)
    return receipts


def web_hour_probabilities(is_midnight_deal: bool) -> np.ndarray:
    weights = np.array(cfg.WEB_ORDER_HOUR_WEIGHTS, dtype=float)
    weights = weights / weights.sum()
    if is_midnight_deal:
        weights = weights * (1 - cfg.WEB_MIDNIGHT_DEAL_SHARE)
        weights[0] += cfg.WEB_MIDNIGHT_DEAL_SHARE
    return weights


def build_web_orders(rng, calendar, world, members, slots):
    """Web order headers with timestamps, status, dispatch and fulfilment."""
    log("Building web order headers")
    n_days = calendar["n_days"]
    web_base, web_logged, extra_web = slots["web_base"], slots["web_logged"], slots["extra_web"]
    picks_day, picks_member = slots["web_picks"]
    guest_counts = web_base - web_logged
    guest_days = np.repeat(np.arange(n_days), guest_counts)
    orders = pd.DataFrame({
        "day": np.concatenate([guest_days, picks_day]).astype(np.int32),
        "member_idx": np.concatenate([np.full(len(guest_days), -1, dtype=np.int32), picks_member]),
    })
    # A handful of test orders per year (test articles, no member).
    n_test = int(round(cfg.WEB_TEST_ORDERS_PER_YEAR * n_days / 365.25))
    test_days = rng.choice(n_days, size=n_test, replace=False)
    test_orders = pd.DataFrame({"day": test_days.astype(np.int32), "member_idx": np.int32(-1)})
    orders["test_order"] = False
    test_orders["test_order"] = True
    orders = pd.concat([orders, test_orders], ignore_index=True)
    orders["login_state"] = np.where(orders["member_idx"] >= 0, "logged_in", "guest")

    # Local order time of day: late-evening profile, midnight spike on Black Friday.
    seconds = np.zeros(len(orders), dtype=np.int64)
    deal_offsets = {day_offset(d) for d in cfg.WEB_MIDNIGHT_DEAL_DAYS}
    for deal, mask in ((True, orders["day"].isin(deal_offsets).to_numpy()), (False, ~orders["day"].isin(deal_offsets).to_numpy())):
        count = int(mask.sum())
        if count:
            hours = rng.choice(24, size=count, p=web_hour_probabilities(deal))
            seconds[mask] = hours * 3600 + rng.integers(0, 3600, count)
    orders["order_ts_utc"] = local_to_utc_from_parts(orders["day"].to_numpy(), seconds).to_numpy()
    orders = orders.sort_values(["order_ts_utc", "member_idx"], kind="stable").reset_index(drop=True)
    orders["web_order_id"] = 90_000_000 + np.arange(len(orders), dtype=np.int64)
    orders["n_lines"] = np.where(orders["test_order"], 1, 1 + rng.poisson(cfg.WEB_LINES_PER_ORDER_EXTRA_MEAN, len(orders)))

    # Fulfilment type grows towards click-and-collect over the window.
    progress = orders["day"].to_numpy() / (n_days - 1)
    collect_share = cfg.WEB_CLICK_COLLECT_SHARE_START + (cfg.WEB_CLICK_COLLECT_SHARE_END - cfg.WEB_CLICK_COLLECT_SHARE_START) * progress
    orders["fulfilment_type"] = np.where(rng.random(len(orders)) < collect_share, "click_and_collect", "home_delivery")
    orders.loc[orders["test_order"], "fulfilment_type"] = "home_delivery"

    # Cancellations (higher on the peak days).
    peak_offsets = {day_offset(d) for d in cfg.BLACK_FRIDAYS} | {day_offset(d + timedelta(days=3)) for d in cfg.BLACK_FRIDAYS}
    cancel_share = np.where(orders["day"].isin(peak_offsets), cfg.WEB_CANCELLATION_SHARE_PEAK, cfg.WEB_CANCELLATION_SHARE)
    orders["cancelled"] = (rng.random(len(orders)) < cancel_share) & ~orders["test_order"]

    # Dispatch: lag in days, no dispatch on Sundays or closed holidays, scans at night for a share.
    order_local_date = pd.Series(utc_to_helsinki_local(pd.Series(orders["order_ts_utc"])).dt.normalize())
    lag_home = rng.choice(list(cfg.WEB_DISPATCH_LAG_DAYS_HOME.keys()), size=len(orders), p=list(cfg.WEB_DISPATCH_LAG_DAYS_HOME.values()))
    lag_collect = rng.choice(list(cfg.WEB_DISPATCH_LAG_DAYS_CLICK_COLLECT.keys()), size=len(orders),
                             p=list(cfg.WEB_DISPATCH_LAG_DAYS_CLICK_COLLECT.values()))
    lag = np.where(orders["fulfilment_type"] == "click_and_collect", lag_collect, lag_home)
    night = rng.random(len(orders)) < cfg.WEB_DISPATCH_NIGHT_SCAN_SHARE
    day_hours = rng.integers(cfg.WEB_DISPATCH_DAY_HOURS_UTC[0], cfg.WEB_DISPATCH_DAY_HOURS_UTC[1], len(orders))
    night_hours = rng.integers(21, 24, len(orders))
    seconds_in_hour = rng.integers(0, 3600, len(orders))
    hours = np.where(night, night_hours, day_hours)
    candidate_days = (order_local_date - pd.to_datetime(cfg.WINDOW_START)).dt.days.to_numpy() + lag
    order_ts = pd.Series(orders["order_ts_utc"])
    closed_days = ~calendar["is_trading_day"]
    sundays = calendar["weekday"] == 6
    pad = 20
    blocked = np.concatenate([(closed_days | sundays), np.ones(pad, dtype=bool)])
    for _ in range(12):                                      # push forward past Sundays/closed days and impossible times
        clipped = np.minimum(candidate_days, len(blocked) - 1)
        dispatch_ts = pd.to_datetime(cfg.WINDOW_START) + pd.to_timedelta(clipped, unit="D") + pd.to_timedelta(hours * 3600 + seconds_in_hour, unit="s")
        too_early = dispatch_ts.to_numpy() <= order_ts.to_numpy()
        needs_move = blocked[clipped] | too_early
        if not needs_move.any():
            break
        candidate_days = np.where(needs_move, candidate_days + 1, candidate_days)
    orders["dispatch_ts_utc"] = dispatch_ts.to_numpy()

    data_cut = helsinki_local_to_utc(pd.Series([pd.Timestamp(cfg.WINDOW_END) + pd.Timedelta(days=1)])).iloc[0]
    unshipped = orders["dispatch_ts_utc"] >= data_cut
    orders["status"] = np.where(orders["cancelled"], "cancelled",
                                np.where(unshipped, "processing",
                                         np.where(orders["fulfilment_type"] == "click_and_collect", "collected", "delivered")))
    orders.loc[orders["status"].isin(["cancelled", "processing"]), "dispatch_ts_utc"] = pd.NaT
    # Click-and-collect pickup store: any store trading at the dispatch date, weighted by size.
    physical = world["n_physical"]
    weights = np.array([l["size_factor"] * cfg.RECEIPTS_PER_DAY_BY_FORMAT[l["format"]] for l in world["locations"][:physical]])
    weights = weights / weights.sum()
    pickup = np.full(len(orders), -1, dtype=np.int16)
    collect_rows = np.flatnonzero(orders["fulfilment_type"] == "click_and_collect")
    # The pickup store must exist (and preferably be open) on the day the order is ready: the Helsinki dispatch date,
    # or the order date for orders that were never dispatched.
    ready_local = utc_to_helsinki_local(pd.Series(orders["dispatch_ts_utc"])).dt.normalize()
    ready_local = ready_local.fillna(pd.Series(order_local_date))
    pickup_day = (ready_local.to_numpy()[collect_rows] - np.datetime64(cfg.WINDOW_START)).astype("timedelta64[D]").astype(int)
    pickup_day = np.clip(pickup_day, 0, n_days - 1)
    chosen = rng.choice(physical, size=len(collect_rows), p=weights)
    for _ in range(30):
        bad = ~world["open_matrix"][chosen, pickup_day]
        if not bad.any():
            break
        chosen[bad] = rng.choice(physical, size=int(bad.sum()), p=weights)
    # Days when every store is shut (statutory holidays): any store that exists on the day will do.
    for _ in range(60):
        not_existing = np.array([_outside_life(world["locations"][c], int(d)) for c, d in zip(chosen, pickup_day)])
        if not not_existing.any():
            break
        chosen[not_existing] = rng.choice(physical, size=int(not_existing.sum()), p=weights)
    pickup[collect_rows] = chosen
    orders["pickup_loc_idx"] = pickup
    orders["order_local_date"] = order_local_date.to_numpy()
    return orders


def sku_weight_matrix(products, month_id: int, calendar_month: int, tilt_bulky: float = 1.0) -> np.ndarray:
    """Sampling weight of every SKU in a given month (popularity x season x listed), test SKUs excluded."""
    season = products["season_matrix"][products["subcat_idx"], calendar_month - 1]
    weights = products["popularity"] * season * products["listed_by_month"][month_id]
    weights = np.where(products["bulky"], weights * tilt_bulky, weights)
    return weights


def build_ranging(rng, world, products):
    """Which SKUs each physical store carries (static for the window)."""
    log("Deciding store ranges")
    physical = world["n_physical"]
    n_sku = len(products["skus"])
    ranged = np.zeros((physical, n_sku), dtype=bool)
    for loc in world["locations"][:physical]:
        probability = np.full(n_sku, cfg.RANGING_PROBABILITY_BY_FORMAT[loc["format"]])
        if loc["format"] == "Small":
            probability = np.where(products["bulky"], probability * cfg.RANGING_BULKY_FACTOR_SMALL_STORE, probability)
        probability = np.where(products["skus"]["is_test"].to_numpy(), 0.0, probability)
        # a bestseller is more likely to be ranged: scale by popularity rank
        popularity_rank = np.argsort(np.argsort(-products["popularity"])) / n_sku
        probability = probability * (1.6 - 1.2 * popularity_rank)
        ranged[loc["loc_idx"]] = rng.random(n_sku) < np.clip(probability, 0, 0.95)
    return ranged


def expand_lines(rng, calendar, world, products, headers, ranged, kind: str):
    """Turn receipt/order headers into sales-line rows (SKU, qty, price, VAT, cost)."""
    log(f"Expanding {kind} headers into lines")
    n_headers = len(headers)
    n_lines = headers["n_lines"].to_numpy()
    header_row = np.repeat(np.arange(n_headers), n_lines)
    line_no = np.concatenate([np.arange(1, k + 1) for k in n_lines]) if n_headers else np.array([], dtype=int)
    day = headers["day"].to_numpy()[header_row]
    if kind == "store":
        loc = headers["loc_idx"].to_numpy()[header_row]
    else:
        loc = np.full(len(header_row), world["web_idx"])
    month_id = calendar["month_id"][day]
    calendar_month = calendar["month"][day]
    sku_idx = np.zeros(len(header_row), dtype=np.int32)

    test_flag = headers["test_receipt" if kind == "store" else "test_order"].to_numpy()[header_row]
    # Group by (location, month) for sampling.
    group_key = loc.astype(np.int64) * 1000 + month_id
    order = np.argsort(group_key, kind="stable")
    sorted_keys = group_key[order]
    boundaries = np.flatnonzero(np.diff(sorted_keys)) + 1
    for block in np.split(order, boundaries):
        if not len(block):
            continue
        loc_value, month_value = int(loc[block[0]]), int(month_id[block[0]])
        month_number = int(calendar_month[block[0]])
        if kind == "store" and loc_value == world["training_idx"]:
            weights = sku_weight_matrix(products, month_value, month_number)
        elif kind == "store":
            weights = sku_weight_matrix(products, month_value, month_number) * ranged[loc_value]
        else:
            weights = sku_weight_matrix(products, month_value, month_number, cfg.WEB_BULKY_TILT)
        weights = weights.astype(float)
        weights[products["test_sku_idx"]] = 0.0
        cumulative = np.cumsum(weights)
        picks = np.minimum(np.searchsorted(cumulative, rng.random(len(block)) * cumulative[-1], side="right"), len(weights) - 1)
        # test-article receipts/orders sell test SKUs instead
        is_test = test_flag[block]
        if is_test.any():
            picks = np.where(is_test, rng.choice(products["test_sku_idx"], size=len(block)), picks)
        sku_idx[block] = picks

    # Quantity, price, promotion, VAT, cost.
    qty_mean = products["qty_mean"][sku_idx]
    quantity = np.minimum(1 + rng.poisson(np.maximum(qty_mean - 1, 0)), 12)
    unit_net = products["skus"]["unit_net_cents"].to_numpy()[sku_idx].astype(float)
    unit_cost = products["skus"]["unit_cost_cents"].to_numpy()[sku_idx]
    fiscal_year = calendar["fiscal_year_index"][day]
    price_index = np.array([cfg.PRICE_INDEX_BY_FISCAL_YEAR[y] for y in fiscal_year])
    dates = calendar["days"][day]
    black_week = np.zeros(len(day), dtype=bool)
    for bf in cfg.BLACK_FRIDAYS:
        black_week |= (dates >= pd.Timestamp(bf) - pd.Timedelta(days=4)) & (dates <= pd.Timestamp(bf) + pd.Timedelta(days=3))
    promo_share = np.where(black_week, cfg.PROMO_LINE_SHARE_BLACK_WEEK,
                           np.where(dates.month == 1, cfg.PROMO_LINE_SHARE_JANUARY, cfg.PROMO_LINE_SHARE_BASE))
    promo = rng.random(len(day)) < promo_share
    discount = np.where(promo, rng.choice(cfg.PROMO_DISCOUNTS, size=len(day)), 0.0)
    staff = headers["staff"].to_numpy()[header_row] if kind == "store" else np.zeros(len(day), dtype=bool)
    keep_fraction = (1 - discount) * np.where(staff, 1 - cfg.STAFF_DISCOUNT, 1.0)
    net_cents = np.maximum(np.rint(unit_net * price_index * quantity * keep_fraction).astype(np.int64), 1)

    vat_class = products["skus"]["vat_class"].to_numpy()[sku_idx]
    after_change = day >= day_offset(cfg.VAT_CHANGE_DATE)
    vat_bp = np.where(vat_class == "standard", np.where(after_change, cfg.VAT_RATES_BP["standard_after"], cfg.VAT_RATES_BP["standard_before"]),
                      np.where(vat_class == "reduced14", cfg.VAT_RATES_BP["reduced14"], cfg.VAT_RATES_BP["reduced10"]))
    gross_cents = (net_cents * (10000 + vat_bp) + 5000) // 10000
    lines = pd.DataFrame({
        "header_row": header_row, "line_no": line_no.astype(np.int16), "day": day.astype(np.int32), "loc_idx": loc.astype(np.int16),
        "sku_idx": sku_idx, "quantity": quantity.astype(np.int16), "net_cents": net_cents, "vat_bp": vat_bp.astype(np.int32),
        "gross_cents": gross_cents, "std_cost_cents": (unit_cost * quantity).astype(np.int64),
        "staff": staff,
    })
    return lines


def attach_headers_to_lines(lines, headers, kind: str, members, world, products, calendar):
    """Copy header fields onto lines and resolve dimension keys."""
    rows = lines["header_row"].to_numpy()
    if kind == "store":
        lines["receipt_id"] = headers["receipt_id"].to_numpy()[rows]
        lines["sale_ts_utc"] = headers["ts_utc"].to_numpy()[rows]
        lines["member_idx"] = headers["member_idx"].to_numpy()[rows]
        lines["is_web"] = False
    else:
        lines["receipt_id"] = headers["web_order_id"].to_numpy()[rows]
        lines["sale_ts_utc"] = headers["order_ts_utc"].to_numpy()[rows]
        lines["member_idx"] = headers["member_idx"].to_numpy()[rows]
        lines["is_web"] = True
    lines["store_key"] = resolve_version(world["store_index"], lines["loc_idx"].to_numpy(), lines["day"].to_numpy())
    lines["product_key"] = resolve_version(products["product_index"], lines["sku_idx"].to_numpy(), lines["day"].to_numpy())
    has_member = lines["member_idx"].to_numpy() >= 0
    member_key = np.zeros(len(lines), dtype=np.int64)
    if has_member.any():
        member_key[has_member] = resolve_version(members["member_index"], lines["member_idx"].to_numpy()[has_member],
                                                 lines["day"].to_numpy()[has_member])
    lines["member_key"] = pd.array(np.where(has_member, member_key, 0), dtype="Int64")
    lines.loc[~has_member, "member_key"] = pd.NA
    return lines


def assemble_sales(rng, calendar, world, products, members, store_receipts, web_orders, ranged):
    """Both channels' lines, channel columns, load timestamps and final line ids."""
    store_lines = expand_lines(rng, calendar, world, products, store_receipts, ranged, "store")
    store_lines = attach_headers_to_lines(store_lines, store_receipts, "store", members, world, products, calendar)
    web_lines_all = expand_lines(rng, calendar, world, products, web_orders, ranged, "web")
    web_lines_all = attach_headers_to_lines(web_lines_all, web_orders, "web", members, world, products, calendar)

    # Web order values (all orders, incl. cancelled/processing) from their lines, then drop lines of orders without a dispatch.
    order_totals = web_lines_all.groupby("header_row")["gross_cents"].sum()
    web_orders["order_total_gross_cents"] = order_totals.reindex(range(len(web_orders))).fillna(0).astype(np.int64).to_numpy()
    shipped = web_orders["status"].isin(["delivered", "collected"]).to_numpy()
    web_lines = web_lines_all[shipped[web_lines_all["header_row"].to_numpy()]].copy()
    web_lines["fulfilment_type"] = web_orders["fulfilment_type"].to_numpy()[web_lines["header_row"].to_numpy()]

    # Channel columns: legacy code before the migration, channel_id from it (1 store, 2 web delivery, 3 click-and-collect).
    migration_offset = day_offset(cfg.MIGRATION_DATE)
    store_lines["fulfilment_type"] = None
    for frame in (store_lines, web_lines):
        post = frame["day"].to_numpy() >= migration_offset
        is_web = frame["is_web"].to_numpy()
        collect = (frame["fulfilment_type"] == "click_and_collect").to_numpy()
        code = np.where(is_web, "WB", "ST").astype(object)
        channel_id = np.where(~is_web, 1, np.where(collect, 3, 2))
        frame["channel_code"] = np.where(post, None, code)
        frame["channel_id"] = pd.array(np.where(post, channel_id, 0), dtype="Int64")
        frame.loc[~post, "channel_id"] = pd.NA

    lines = pd.concat([store_lines, web_lines], ignore_index=True)
    lines["staff_purchase_flag"] = lines["staff"].astype(bool)
    lines["etl_loaded_at"] = pd.to_datetime(cfg.WINDOW_START) + pd.to_timedelta(lines["day"] + 1, unit="D") + pd.Timedelta(hours=cfg.NIGHTLY_LOAD_HOUR_UTC)
    lines = lines.sort_values(["sale_ts_utc", "receipt_id", "line_no"], kind="stable").reset_index(drop=True)
    lines.insert(0, "sales_line_id", np.arange(1, len(lines) + 1, dtype=np.int64))
    lines["sale_date"] = (pd.to_datetime(cfg.WINDOW_START) + pd.to_timedelta(lines["day"], unit="D"))
    return lines, web_orders


# ---------------------------------------------------------------------------
# 7. Returns
# ---------------------------------------------------------------------------

def stock_life(calendar, world, products) -> dict:
    """First and last week in which each SKU and each store takes part in the weekly stock."""
    n_weeks, physical = calendar["n_weeks"], world["n_physical"]
    skus = products["skus"]
    return {
        "sku_first": np.array([max(day_offset(d) // 7, 0) if d > cfg.WINDOW_START else 0 for d in skus["listed_from"]]),
        "sku_last": np.array([n_weeks - 1 if d is None else min(max((day_offset(d) - 1) // 7, 0), n_weeks - 1)
                              for d in skus["delisted_on"]]),
        "store_first": np.array([max(day_offset(l["open_date"]) // 7, 0) if l["open_date"] else 0
                                 for l in world["locations"][:physical]]),
        "store_last": np.array([min(day_offset(l["close_date"]) // 7, n_weeks - 1) if l["close_date"] else n_weeks - 1
                                for l in world["locations"][:physical]]),
    }


def stock_active(life: dict, ranged: np.ndarray, loc_idx, sku_idx, week) -> np.ndarray:
    """True where a store x SKU has a stock row in the given week."""
    return (ranged[loc_idx, sku_idx] & (week >= life["sku_first"][sku_idx]) & (week <= life["sku_last"][sku_idx]) &
            (week >= life["store_first"][loc_idx]) & (week <= life["store_last"][loc_idx]))


def build_returns(rng, calendar, world, products, members, lines, web_orders, ranged):
    """Return lines: booked on the return date, at the location that processed them."""
    log("Building returns")
    n_days = calendar["n_days"]
    physical = world["n_physical"]
    open_matrix = world["open_matrix"]
    eligible = (~lines["loc_idx"].isin([world["training_idx"]])) & (~products["skus"]["is_test"].to_numpy()[lines["sku_idx"].to_numpy()])
    candidate_rows = np.flatnonzero(eligible.to_numpy())
    rate = products["return_rate"][lines["sku_idx"].to_numpy()[candidate_rows]]
    rate = rate * np.where(lines["is_web"].to_numpy()[candidate_rows], cfg.RETURN_WEB_MULTIPLIER, 1.0)
    chosen = candidate_rows[rng.random(len(candidate_rows)) < rate]
    sub = lines.iloc[chosen]
    is_web = sub["is_web"].to_numpy()

    # Base date: sale date for stores, Helsinki dispatch date for web orders.
    dispatch_local = pd.Series(web_orders["dispatch_ts_utc"])
    dispatch_local = utc_to_helsinki_local(dispatch_local).dt.normalize()
    receipt_to_dispatch = pd.Series(dispatch_local.to_numpy(), index=web_orders["web_order_id"].to_numpy())
    base_day = sub["day"].to_numpy().copy()
    if is_web.any():
        web_dispatch = receipt_to_dispatch.loc[sub["receipt_id"].to_numpy()[is_web]]
        base_day[is_web] = (web_dispatch.to_numpy() - np.datetime64(cfg.WINDOW_START)).astype("timedelta64[D]").astype(int)
    lag = np.where(is_web, 2 + rng.geometric(cfg.RETURN_WEB_LAG_GEOMETRIC_P, len(sub)) - 1, 1 + rng.geometric(cfg.RETURN_STORE_LAG_GEOMETRIC_P, len(sub)) - 1)
    lag = np.minimum(lag, cfg.RETURN_WINDOW_DAYS)
    return_day = base_day + lag

    # Processing location: stores take returns at the selling store; web returns mostly go back by post.
    location = np.where(is_web, world["web_idx"], sub["loc_idx"].to_numpy()).astype(int)
    weights = np.array([l["size_factor"] * cfg.RECEIPTS_PER_DAY_BY_FORMAT[l["format"]] for l in world["locations"][:physical]])
    weights = weights / weights.sum()
    sku_of_return = sub["sku_idx"].to_numpy()
    raw_day = np.minimum(return_day, n_days - 1)
    # Some web returns are handed in at a store: one that is open that day and ranges the article, else they go by post.
    in_store = is_web & (rng.random(len(sub)) < cfg.RETURN_WEB_IN_STORE_SHARE)
    location[in_store] = -1
    for _ in range(25):
        pending = np.flatnonzero(location == -1)
        if not len(pending):
            break
        trial = rng.choice(physical, size=len(pending), p=weights)
        acceptable = open_matrix[trial, raw_day[pending]] & ranged[trial, sku_of_return[pending]]
        location[pending[acceptable]] = trial[acceptable]
    location[location == -1] = world["web_idx"]

    # Stores take returns only when open: move to the next trading day (web processing runs every day).
    next_open = np.full((len(world["locations"]), n_days + 1), n_days, dtype=np.int32)
    for loc_idx in range(len(world["locations"])):
        for d in range(n_days - 1, -1, -1):
            next_open[loc_idx, d] = d if open_matrix[loc_idx, d] else next_open[loc_idx, d + 1]
    return_day = next_open[location, np.minimum(return_day, n_days)]
    keep = return_day < n_days                                         # drop returns that fall after the data cut
    # An in-store return needs a live stock row for that store, SKU and week (the article is still ranged there).
    return_week = np.minimum(return_day, n_days - 1) // 7
    in_store_return = location < physical
    live = stock_active(stock_life(calendar, world, products), ranged, np.minimum(location, physical - 1), sku_of_return, return_week)
    keep &= ~in_store_return | live
    # The 30-day window is extended to the next trading day when the store is shut on the last day (rule 5).
    sub, return_day, location = sub[keep], return_day[keep], location[keep]
    base_day = base_day[keep]
    quantity_sold = sub["quantity"].to_numpy()
    quantity_returned = np.where(quantity_sold > 1, rng.integers(1, quantity_sold + 1), 1)
    refund_net = np.where(quantity_returned == quantity_sold, sub["net_cents"].to_numpy(),
                          np.rint(sub["net_cents"].to_numpy() * quantity_returned / quantity_sold).astype(np.int64))
    vat_bp = sub["vat_bp"].to_numpy()
    refund_gross = (refund_net * (10000 + vat_bp) + 5000) // 10000
    cost_returned = np.rint(sub["std_cost_cents"].to_numpy() * quantity_returned / quantity_sold).astype(np.int64)

    is_web_location = location == world["web_idx"]
    hour_start = np.where(is_web_location, 8, 12)
    hour_span = np.where(is_web_location, 14, 5)
    seconds = (hour_start + (rng.random(len(sub)) * hour_span).astype(int)) * 3600 + rng.integers(0, 3600, len(sub))
    reasons = rng.choice(list(cfg.RETURN_REASONS.keys()), size=len(sub), p=list(cfg.RETURN_REASONS.values()))
    returns = pd.DataFrame({
        "sales_line_id": sub["sales_line_id"].to_numpy(), "day": return_day.astype(np.int32), "loc_idx": location.astype(np.int16),
        "sku_idx": sub["sku_idx"].to_numpy(), "member_idx": sub["member_idx"].to_numpy(),
        "quantity_returned": quantity_returned.astype(np.int16), "refund_net_cents": refund_net, "vat_bp": vat_bp,
        "refund_gross_cents": refund_gross, "std_cost_returned_cents": cost_returned, "reason_code": reasons,
        "seconds": seconds, "sale_day": sub["day"].to_numpy(), "is_web_sale": sub["is_web"].to_numpy(),
    })
    returns["return_ts_utc"] = local_to_utc_from_parts(returns["day"].to_numpy(), returns["seconds"].to_numpy()).to_numpy()
    returns = returns.sort_values(["return_ts_utc", "sales_line_id"], kind="stable").reset_index(drop=True)
    returns.insert(0, "return_line_id", np.arange(1, len(returns) + 1, dtype=np.int64))
    returns["store_key"] = resolve_version(world["store_index"], returns["loc_idx"].to_numpy(), returns["day"].to_numpy())
    returns["product_key"] = resolve_version(products["product_index"], returns["sku_idx"].to_numpy(), returns["day"].to_numpy())
    has_member = returns["member_idx"].to_numpy() >= 0
    keys = np.zeros(len(returns), dtype=np.int64)
    if has_member.any():
        keys[has_member] = resolve_version(members["member_index"], returns["member_idx"].to_numpy()[has_member],
                                           returns["day"].to_numpy()[has_member])
    returns["member_key"] = pd.array(keys, dtype="Int64")
    returns.loc[~has_member, "member_key"] = pd.NA
    returns["return_date"] = pd.to_datetime(cfg.WINDOW_START) + pd.to_timedelta(returns["day"], unit="D")
    return returns


# ---------------------------------------------------------------------------
# 8. Stock
# ---------------------------------------------------------------------------

def build_stock(rng, calendar, world, products, lines, returns, ranged):
    """Weekly closing stock per store x SKU, replenished by a deterministic policy."""
    log("Building weekly stock")
    n_weeks, physical = calendar["n_weeks"], world["n_physical"]
    n_sku = len(products["skus"])
    locations = world["locations"]

    store_lines = lines[(~lines["is_web"]) & (lines["loc_idx"] < physical)]
    flat = (store_lines["loc_idx"].to_numpy().astype(np.int64) * n_sku + store_lines["sku_idx"].to_numpy()) * n_weeks + store_lines["day"].to_numpy() // 7
    sold = np.bincount(flat, weights=store_lines["quantity"].to_numpy(), minlength=physical * n_sku * n_weeks).astype(np.int32)
    sold = sold.reshape(physical, n_sku, n_weeks)
    store_returns = returns[returns["loc_idx"] < physical]
    flat_r = (store_returns["loc_idx"].to_numpy().astype(np.int64) * n_sku + store_returns["sku_idx"].to_numpy()) * n_weeks + store_returns["day"].to_numpy() // 7
    returned = np.bincount(flat_r, weights=store_returns["quantity_returned"].to_numpy(), minlength=physical * n_sku * n_weeks).astype(np.int32)
    returned = returned.reshape(physical, n_sku, n_weeks)

    # Active window of each store x SKU in weeks.
    skus = products["skus"]
    life = stock_life(calendar, world, products)
    sku_first_week, sku_last_week = life["sku_first"], life["sku_last"]
    store_first_week, store_last_week = life["store_first"], life["store_last"]
    pack = rng.choice(cfg.STOCK_PACK_SIZE_CHOICES, size=(physical, n_sku))
    shrink = rng.random((n_weeks, physical, n_sku)) < cfg.STOCK_SHRINK_PROBABILITY

    closing = np.zeros((physical, n_sku), dtype=np.int32)
    chunks = []
    week_index = np.arange(n_weeks)
    for week in range(n_weeks):
        active = (ranged & (week >= sku_first_week)[None, :] & (week <= sku_last_week)[None, :] &
                  (week >= store_first_week)[:, None] & (week <= store_last_week)[:, None])
        history = sold[:, :, max(0, week - cfg.STOCK_TRAILING_WEEKS):week]
        average = history.mean(axis=2) if week > 0 else sold[:, :, 0].astype(float)
        reorder_point = np.ceil(cfg.STOCK_REORDER_WEEKS * average).astype(np.int32) + cfg.STOCK_MIN_FACING_UNITS
        order_up_to = reorder_point + np.ceil(cfg.STOCK_ORDER_UP_TO_EXTRA_WEEKS * average).astype(np.int32) + pack
        opening = np.where(active, closing, 0)
        available = opening + returned[:, :, week] - sold[:, :, week]
        # A write-off week only for SKUs delisted and stores closed inside the window. (Until 15 Oct 2026 this also fired for
        # every live SKU and store in the very last week of the window, which zeroed all stock at the data cut. Fixed in Phase 3.)
        ends_in_window = ((week == sku_last_week) & (sku_last_week < n_weeks - 1))[None, :] | \
                         ((week == store_last_week) & (store_last_week < n_weeks - 1))[:, None]
        final_week = active & ends_in_window
        receipts = np.where(active & (available < reorder_point), order_up_to - available, 0)
        receipts = np.where(final_week, np.maximum(-available, 0), receipts)
        adjustment = np.where(active & shrink[week] & ((available + receipts) > cfg.STOCK_MIN_FACING_UNITS), -1, 0)
        adjustment = np.where(final_week, -(available + receipts), adjustment)
        new_closing = np.where(active, available + receipts + adjustment, 0).astype(np.int32)
        if (new_closing < 0).any():
            raise RuntimeError("Stock went negative; check the replenishment policy.")
        store_idx, sku_idx = np.nonzero(active)
        chunks.append(pd.DataFrame({
            "week": np.int32(week), "loc_idx": store_idx.astype(np.int16), "sku_idx": sku_idx.astype(np.int32),
            "closing_units": new_closing[store_idx, sku_idx], "receipts_units": receipts[store_idx, sku_idx].astype(np.int32),
            "adjustment_units": adjustment[store_idx, sku_idx].astype(np.int32)}))
        closing = new_closing
    stock = pd.concat(chunks, ignore_index=True)
    week_ending_offset = stock["week"].to_numpy() * 7 + 6
    stock["week_ending_date"] = pd.to_datetime(cfg.WINDOW_START) + pd.to_timedelta(week_ending_offset, unit="D")
    stock["closing_value_cents"] = stock["closing_units"].to_numpy().astype(np.int64) * skus["unit_cost_cents"].to_numpy()[stock["sku_idx"].to_numpy()]
    stock["store_key"] = resolve_version(world["store_index"], stock["loc_idx"].to_numpy(), week_ending_offset)
    stock["product_key"] = resolve_version(products["product_index"], stock["sku_idx"].to_numpy(), week_ending_offset)
    stock["etl_loaded_at"] = stock["week_ending_date"] + pd.Timedelta(days=1, hours=cfg.NIGHTLY_LOAD_HOUR_UTC)
    return stock


# ---------------------------------------------------------------------------
# 9. Control totals (from the clean data)
# ---------------------------------------------------------------------------

def build_daily_report(calendar, world, products, lines, returns, web_orders):
    """rpt_daily_store_sales: the team's maintained net-sales aggregate (company definition)."""
    log("Building the control-total aggregate")
    test_sku = products["skus"]["is_test"].to_numpy()
    usable = (lines["loc_idx"] != world["training_idx"]) & (~test_sku[lines["sku_idx"].to_numpy()])
    sales = lines[usable].copy()
    # Web lines are recognised on the Helsinki dispatch date.
    dispatch_local = utc_to_helsinki_local(pd.Series(web_orders["dispatch_ts_utc"])).dt.normalize()
    dispatch_day = pd.Series(((dispatch_local - pd.Timestamp(cfg.WINDOW_START)).dt.days).to_numpy(), index=web_orders["web_order_id"].to_numpy())
    recognised_day = sales["day"].to_numpy().copy()
    web_mask = sales["is_web"].to_numpy()
    recognised_day[web_mask] = dispatch_day.loc[sales["receipt_id"].to_numpy()[web_mask]].to_numpy()
    sales["recognised_day"] = recognised_day
    sold = sales.groupby(["recognised_day", "loc_idx"]).agg(
        receipts=("receipt_id", "nunique"), units_sold=("quantity", "sum"), net_sales_before_returns=("net_cents", "sum")).reset_index()
    usable_returns = returns[(~test_sku[returns["sku_idx"].to_numpy()])]
    ret = usable_returns.groupby(["day", "loc_idx"]).agg(returns_net=("refund_net_cents", "sum")).reset_index().rename(columns={"day": "recognised_day"})
    report = sold.merge(ret, on=["recognised_day", "loc_idx"], how="outer").fillna(0)
    for column in ("receipts", "units_sold", "net_sales_before_returns", "returns_net"):
        report[column] = report[column].astype(np.int64)
    report["net_sales"] = report["net_sales_before_returns"] - report["returns_net"]
    report["store_id"] = world["store_ids"][report["loc_idx"].astype(int).to_numpy()]
    report["business_date"] = pd.to_datetime(cfg.WINDOW_START) + pd.to_timedelta(report["recognised_day"], unit="D")
    report = report.sort_values(["business_date", "store_id"]).reset_index(drop=True)
    return report[["business_date", "store_id", "receipts", "units_sold", "net_sales_before_returns", "returns_net", "net_sales"]]


# ---------------------------------------------------------------------------
# 10. Incidents (applied to the published tables only)
# ---------------------------------------------------------------------------

def apply_incidents(rng, calendar, world, lines, web_orders, stock):
    """Plant the four undocumented incidents; return modified copies and a manifest of what changed."""
    log("Planting the four undocumented incidents")
    manifest = {}
    published_lines, published_stock = lines.copy(), stock.copy()

    # INC-1: one store-week of receipts posted twice by a till re-sync.
    inc1 = cfg.INCIDENT_DOUBLE_POST
    store_loc = [l["loc_idx"] for l in world["locations"] if l["store_id"] == inc1["store_id"]][0]
    start_day, end_day = day_offset(inc1["week_start"]), day_offset(inc1["week_end"])
    mask = (~lines["is_web"]) & (lines["loc_idx"] == store_loc) & (lines["day"] >= start_day) & (lines["day"] <= end_day)
    duplicates = lines[mask].copy()
    duplicates["sales_line_id"] = np.arange(lines["sales_line_id"].max() + 1, lines["sales_line_id"].max() + 1 + len(duplicates))
    duplicates["etl_loaded_at"] = pd.Timestamp(inc1["reload_ts"])
    published_lines = pd.concat([published_lines, duplicates], ignore_index=True)
    manifest[inc1["id"]] = {"kind": "double_post", "store_id": inc1["store_id"], "week_start": str(inc1["week_start"]),
                            "week_end": str(inc1["week_end"]), "duplicated_lines": int(len(duplicates)),
                            "duplicated_net_eur": float(duplicates["net_cents"].sum() / 100)}

    # INC-2: logged-in web orders in a window lose their member key on the sales lines.
    inc2 = cfg.INCIDENT_LOGIN_ORPHANS
    window = (web_orders["order_local_date"] >= pd.Timestamp(inc2["start"])) & (web_orders["order_local_date"] <= pd.Timestamp(inc2["end"])) & \
             (web_orders["member_idx"] >= 0) & web_orders["status"].isin(["delivered", "collected"])
    affected_orders = web_orders.loc[window & (rng.random(len(web_orders)) < inc2["share_of_logged_in_orders"]), "web_order_id"]
    orphan_mask = published_lines["receipt_id"].isin(affected_orders) & published_lines["is_web"]
    published_lines.loc[orphan_mask, "member_key"] = pd.NA
    manifest[inc2["id"]] = {"kind": "login_orphans", "start": str(inc2["start"]), "end": str(inc2["end"]),
                            "orders_affected": int(len(affected_orders)), "lines_affected": int(orphan_mask.sum())}

    # INC-3: the West region's stock snapshot for one week was loaded twice.
    inc3 = cfg.INCIDENT_STOCK_RELOAD
    region_by_key = world["dim_store"].set_index("store_key")["region"]
    stock_regions = region_by_key.loc[stock["store_key"].to_numpy()].to_numpy()
    reload_mask = (stock["week_ending_date"] == pd.Timestamp(inc3["week_ending"])).to_numpy() & (stock_regions == inc3["region_new"])
    reloaded = stock[reload_mask].copy()
    reloaded["etl_loaded_at"] = pd.Timestamp(inc3["reload_ts"])
    published_stock = pd.concat([published_stock, reloaded], ignore_index=True)
    manifest[inc3["id"]] = {"kind": "stock_reload", "week_ending": str(inc3["week_ending"]), "region": inc3["region_new"],
                            "duplicated_rows": int(len(reloaded))}

    # INC-4: click-and-collect orders carried the home-delivery channel key for four weeks.
    inc4 = cfg.INCIDENT_CNC_MISLABEL
    cnc_orders = web_orders.loc[(web_orders["fulfilment_type"] == "click_and_collect") &
                                (web_orders["order_local_date"] >= pd.Timestamp(inc4["start"])) &
                                (web_orders["order_local_date"] <= pd.Timestamp(inc4["end"])), "web_order_id"]
    cnc_mask = published_lines["receipt_id"].isin(cnc_orders) & published_lines["is_web"]
    published_lines.loc[cnc_mask, "channel_id"] = 2
    manifest[inc4["id"]] = {"kind": "cnc_mislabel", "start": str(inc4["start"]), "end": str(inc4["end"]),
                            "orders_affected": int(published_lines.loc[cnc_mask, "receipt_id"].nunique()),
                            "lines_affected": int(cnc_mask.sum())}
    published_lines = published_lines.reset_index(drop=True)
    published_stock = published_stock.reset_index(drop=True)
    return published_lines, published_stock, manifest


# ---------------------------------------------------------------------------
# 11-12. Write to DuckDB
# ---------------------------------------------------------------------------

def money(column: str) -> str:
    """SQL expression turning an integer-cents column into DECIMAL(12,2)."""
    return f"CAST({column} * 0.01 AS DECIMAL(14,2))"


def create_and_load(connection, name: str, ddl_columns: str, frame: pd.DataFrame, select_expressions: str) -> None:
    """Create a table with explicit types and load it from a DataFrame."""
    connection.execute(f"CREATE TABLE {name} ({ddl_columns})")
    connection.register("_load_frame", frame)
    connection.execute(f"INSERT INTO {name} SELECT {select_expressions} FROM _load_frame")
    connection.unregister("_load_frame")
    count = connection.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
    log(f"  wrote {name}: {count:,} rows")


def write_canonical_tables(connection, tables: dict) -> None:
    """Create the canonical tables in dependency order."""
    t = tables
    dim_date = t["dim_date"]
    create_and_load(connection, "dim_date",
        "calendar_date DATE, day_of_week INTEGER, day_name VARCHAR, calendar_year INTEGER, calendar_month INTEGER, "
        "fiscal_year VARCHAR, fiscal_year_start_date DATE, fiscal_quarter INTEGER, fiscal_period INTEGER, "
        "fiscal_period_label VARCHAR, fiscal_week INTEGER, fiscal_week_start_date DATE, fiscal_week_end_date DATE, "
        "weeks_in_fiscal_year INTEGER, is_53_week_year BOOLEAN, is_public_holiday BOOLEAN, holiday_name VARCHAR, "
        "is_trading_day BOOLEAN",
        dim_date, "CAST(calendar_date AS DATE), day_of_week, day_name, calendar_year, calendar_month, fiscal_year, "
        "CAST(fiscal_year_start_date AS DATE), fiscal_quarter, fiscal_period, fiscal_period_label, fiscal_week, "
        "CAST(fiscal_week_start_date AS DATE), CAST(fiscal_week_end_date AS DATE), weeks_in_fiscal_year, is_53_week_year, "
        "is_public_holiday, holiday_name, is_trading_day")
    create_and_load(connection, "ref_fiscal_calendar",
        "fiscal_year VARCHAR, fiscal_period INTEGER, fiscal_quarter INTEGER, fiscal_period_label VARCHAR, "
        "period_start_date DATE, period_end_date DATE, weeks_in_period INTEGER, first_fiscal_week INTEGER, "
        "last_fiscal_week INTEGER, fully_loaded BOOLEAN",
        t["ref_fiscal"], "fiscal_year, fiscal_period, fiscal_quarter, fiscal_period_label, CAST(period_start_date AS DATE), "
        "CAST(period_end_date AS DATE), weeks_in_period, first_fiscal_week, last_fiscal_week, fully_loaded")
    create_and_load(connection, "dim_store",
        "store_key INTEGER, store_id INTEGER, store_name VARCHAR, city VARCHAR, region VARCHAR, format VARCHAR, sqm INTEGER, "
        "open_date DATE, close_date DATE, valid_from DATE, valid_to DATE, is_current BOOLEAN",
        t["dim_store"], "store_key, store_id, store_name, city, region, format, sqm, CAST(open_date AS DATE), "
        "CAST(close_date AS DATE), CAST(valid_from AS DATE), CAST(valid_to AS DATE), is_current")
    create_and_load(connection, "ref_store_closure",
        "closure_id INTEGER, store_id INTEGER, closure_type VARCHAR, closure_start_date DATE, closure_end_date DATE, weeks_closed INTEGER",
        t["ref_store_closure"], "closure_id, store_id, closure_type, CAST(closure_start_date AS DATE), CAST(closure_end_date AS DATE), weeks_closed")
    create_and_load(connection, "dim_product",
        "product_key INTEGER, sku INTEGER, product_name VARCHAR, category VARCHAR, subcategory VARCHAR, brand VARCHAR, "
        "own_label_flag BOOLEAN, vat_class VARCHAR, standard_unit_cost DECIMAL(10,2), listed_from DATE, delisted_on DATE, "
        "valid_from DATE, valid_to DATE, is_current BOOLEAN",
        t["dim_product"], f"product_key, sku, product_name, category, subcategory, brand, own_label_flag, vat_class, "
        f"{money('standard_unit_cost_cents')}, CAST(listed_from AS DATE), CAST(delisted_on AS DATE), CAST(valid_from AS DATE), "
        "CAST(valid_to AS DATE), is_current")
    members = t["members"]["versions"]
    create_and_load(connection, "dim_member",
        "member_key INTEGER, member_id BIGINT, join_date DATE, tier VARCHAR, home_store_id INTEGER, marketing_consent BOOLEAN, "
        "valid_from DATE, valid_to DATE, is_current BOOLEAN",
        members, "member_key, member_id, CAST(join_date AS DATE), tier_name, home_store_id, marketing_consent, "
        "CAST(valid_from AS DATE), CAST(valid_to AS DATE), is_current")
    channels = pd.DataFrame({"channel_id": [1, 2, 3], "channel_name": ["Store", "Web home delivery", "Click and collect"],
                             "channel_group": ["store", "web", "web"], "legacy_channel_code": ["ST", "WB", None]})
    create_and_load(connection, "dim_channel",
        "channel_id INTEGER, channel_name VARCHAR, channel_group VARCHAR, legacy_channel_code VARCHAR",
        channels, "channel_id, channel_name, channel_group, legacy_channel_code")
    campaigns = t["campaigns"]
    create_and_load(connection, "dim_campaign",
        "campaign_id INTEGER, campaign_name VARCHAR, start_date DATE, end_date DATE, channels VARCHAR, target_group VARCHAR, "
        "holdout_pct DECIMAL(4,3), mailing_list_size INTEGER, holdout_size INTEGER",
        campaigns["dim_campaign"], "campaign_id, campaign_name, CAST(start_date AS DATE), CAST(end_date AS DATE), channels, "
        "target_group, CAST(holdout_pct AS DECIMAL(4,3)), mailing_list_size, holdout_size")
    create_and_load(connection, "campaign_holdout", "campaign_id INTEGER, member_id BIGINT",
        campaigns["campaign_holdout"], "campaign_id, member_id")
    create_and_load(connection, "fact_campaign_exposure",
        "exposure_id BIGINT, campaign_id INTEGER, member_key INTEGER, contact_ts_utc TIMESTAMP, contact_channel VARCHAR, "
        "delivered BOOLEAN, opened BOOLEAN",
        campaigns["exposures"], "exposure_id, campaign_id, member_key, contact_ts_utc, contact_channel, delivered, opened")
    sales_expr = ("sales_line_id, receipt_id, line_no, CAST(sale_date AS DATE), sale_ts_utc, store_key, product_key, member_key, "
                  f"channel_code, channel_id, quantity, {money('net_cents')}, CAST(vat_bp * 0.0001 AS DECIMAL(5,4)), "
                  f"{money('gross_cents')}, {money('std_cost_cents')}, staff_purchase_flag, etl_loaded_at")
    create_and_load(connection, "fact_sales_line",
        "sales_line_id BIGINT, receipt_id BIGINT, line_no INTEGER, sale_date DATE, sale_ts_utc TIMESTAMP, store_key INTEGER, "
        "product_key INTEGER, member_key INTEGER, channel_code VARCHAR, channel_id INTEGER, quantity INTEGER, "
        "net_amount DECIMAL(14,2), vat_rate DECIMAL(5,4), gross_amount DECIMAL(14,2), standard_cost DECIMAL(14,2), "
        "staff_purchase_flag BOOLEAN, etl_loaded_at TIMESTAMP",
        t["lines"], sales_expr)
    create_and_load(connection, "fact_return_line",
        "return_line_id BIGINT, sales_line_id BIGINT, return_date DATE, return_ts_utc TIMESTAMP, store_key INTEGER, "
        "product_key INTEGER, member_key INTEGER, quantity_returned INTEGER, refund_net DECIMAL(14,2), vat_rate DECIMAL(5,4), "
        "refund_gross DECIMAL(14,2), standard_cost_returned DECIMAL(14,2), reason_code VARCHAR",
        t["returns"], f"return_line_id, sales_line_id, CAST(return_date AS DATE), return_ts_utc, store_key, product_key, member_key, "
        f"quantity_returned, {money('refund_net_cents')}, CAST(vat_bp * 0.0001 AS DECIMAL(5,4)), {money('refund_gross_cents')}, "
        f"{money('std_cost_returned_cents')}, reason_code")
    create_and_load(connection, "fact_web_order",
        "web_order_id BIGINT, member_key INTEGER, login_state VARCHAR, order_ts_utc TIMESTAMP, dispatch_ts_utc TIMESTAMP, "
        "status VARCHAR, fulfilment_type VARCHAR, pickup_store_key INTEGER, order_total_gross DECIMAL(14,2), line_count INTEGER",
        t["web_orders_db"], f"web_order_id, member_key, login_state, order_ts_utc, dispatch_ts_utc, status, fulfilment_type, "
        f"pickup_store_key, {money('order_total_gross_cents')}, n_lines")
    create_and_load(connection, "fact_stock_week",
        "store_key INTEGER, product_key INTEGER, week_ending_date DATE, closing_units INTEGER, closing_value DECIMAL(14,2), "
        "receipts_units INTEGER, adjustment_units INTEGER, etl_loaded_at TIMESTAMP",
        t["stock"], f"store_key, product_key, CAST(week_ending_date AS DATE), closing_units, {money('closing_value_cents')}, "
        "receipts_units, adjustment_units, etl_loaded_at")
    create_and_load(connection, "rpt_daily_store_sales",
        "business_date DATE, store_id INTEGER, receipts INTEGER, units_sold BIGINT, net_sales_before_returns DECIMAL(14,2), "
        "returns_net DECIMAL(14,2), net_sales DECIMAL(14,2)",
        t["report"], f"CAST(business_date AS DATE), store_id, receipts, units_sold, {money('net_sales_before_returns')}, "
        f"{money('returns_net')}, {money('net_sales')}")


def write_clutter(connection, tables: dict, world: dict) -> None:
    """Staging, backup, temporary and legacy objects, and the legacy views."""
    log("Writing clutter objects and views")
    end = cfg.WINDOW_END
    staging_from = end - timedelta(days=cfg.STAGING_RETENTION_DAYS - 1)
    connection.execute(f"CREATE TABLE stg_sales_line_load AS SELECT * FROM fact_sales_line WHERE sale_date >= DATE '{staging_from}'")
    connection.execute(f"CREATE TABLE stg_web_order_load AS SELECT * FROM fact_web_order WHERE CAST(order_ts_utc AS DATE) >= DATE '{staging_from}'")
    connection.execute(f"CREATE TABLE stg_return_line_load AS SELECT * FROM fact_return_line WHERE return_date >= DATE '{staging_from}'")
    connection.execute(f"CREATE TABLE stg_member_updates AS SELECT * FROM dim_member WHERE valid_from >= DATE '{end - timedelta(days=30)}'")
    connection.execute(f"CREATE TABLE stg_stock_snapshot AS SELECT * FROM fact_stock_week WHERE week_ending_date = DATE '{end}'")
    connection.execute(f"CREATE TABLE stg_campaign_contact_load AS SELECT * FROM fact_campaign_exposure WHERE CAST(contact_ts_utc AS DATE) >= DATE '{staging_from}'")
    connection.execute(
        "CREATE TABLE stg_product_feed AS SELECT sku, product_name, standard_unit_cost AS supplier_price, "
        f"DATE '{end - timedelta(days=3)}' AS feed_date FROM dim_product WHERE is_current AND delisted_on IS NULL AND sku % 7 = 0")
    connection.execute(
        f"CREATE TABLE bak_dim_store_2025 AS SELECT * FROM dim_store WHERE DATE '{cfg.BAK_STORE_SNAPSHOT_DATE}' BETWEEN valid_from AND valid_to")
    connection.execute(
        f"CREATE TABLE bak_dim_product_20251026 AS SELECT * FROM dim_product WHERE DATE '{cfg.BAK_PRODUCT_SNAPSHOT_DATE}' BETWEEN valid_from AND valid_to")
    connection.execute(
        f"CREATE TABLE bak_dim_campaign_2025 AS SELECT * FROM dim_campaign WHERE start_date < DATE '2025-05-01'")
    # Superseded flat dimensions (before the SCD design): old four-region hierarchy and original categories.
    connection.execute(
        f"CREATE TABLE dim_store_old AS SELECT store_id, store_name, region, format, open_date FROM dim_store "
        f"WHERE DATE '{cfg.BAK_STORE_SNAPSHOT_DATE}' BETWEEN valid_from AND valid_to AND store_id NOT IN (900, 999)")
    connection.execute(
        f"CREATE TABLE dim_product_old AS SELECT sku, product_name, category, subcategory, brand FROM dim_product "
        f"WHERE DATE '{cfg.BAK_PRODUCT_SNAPSHOT_DATE}' BETWEEN valid_from AND valid_to")
    # Scratch tables that analysts left behind.
    connection.execute(
        "CREATE TABLE tmp_lfl_store_list_2024 AS SELECT store_id, store_name FROM dim_store WHERE is_current "
        "AND store_id < 900 AND (open_date IS NULL OR open_date < DATE '2024-04-29')")
    connection.execute(
        "CREATE TABLE tmp_lfl_store_list_2025 AS SELECT store_id, store_name FROM dim_store WHERE is_current "
        "AND store_id < 900 AND (open_date IS NULL OR open_date < DATE '2024-09-01')")
    connection.execute("CREATE TABLE tmp_region_map AS SELECT store_id, region FROM dim_store WHERE is_current AND store_id < 900")
    connection.execute(
        f"CREATE TABLE tmp_outdoor_lighting_skus AS SELECT DISTINCT sku FROM dim_product WHERE subcategory = '{cfg.OUTDOOR_LIGHTING_SUBCATEGORY}'")
    # The weekly regional report that stopped refreshing before the region reorganisation (calendar weeks, old regions).
    connection.execute(
        "CREATE TABLE rpt_weekly_sales_by_region AS "
        "SELECT CAST(date_trunc('week', business_date) AS DATE) AS week_start_date, s.region, SUM(r.net_sales) AS net_sales "
        "FROM rpt_daily_store_sales r JOIN dim_store s ON s.store_id = r.store_id "
        "AND r.business_date BETWEEN s.valid_from AND s.valid_to "
        f"WHERE r.business_date <= DATE '{cfg.LEGACY_WEEKLY_REPORT_LAST_DATE}' AND r.store_id < 900 GROUP BY 1, 2")
    # Legacy views: built on channel_code, so web sales vanish after the migration.
    connection.execute("CREATE SCHEMA IF NOT EXISTS rpt")
    connection.execute(
        "CREATE VIEW rpt.v_daily_sales AS "
        "SELECT sale_date, channel, SUM(net_amount) AS net_sales, COUNT(DISTINCT receipt_id) AS receipts FROM ("
        "  SELECT f.sale_date, 'ST' AS channel, f.net_amount, f.receipt_id FROM fact_sales_line f "
        "  JOIN dim_store s ON s.store_key = f.store_key WHERE s.store_id < 900 "
        "  UNION ALL "
        "  SELECT f.sale_date, 'WB' AS channel, f.net_amount, f.receipt_id FROM fact_sales_line f WHERE f.channel_code = 'WB'"
        ") u GROUP BY sale_date, channel")
    connection.execute(
        "CREATE VIEW rpt.v_weekly_store_sales AS "
        "SELECT d.fiscal_year, d.fiscal_week, v.channel, SUM(v.net_sales) AS net_sales FROM rpt.v_daily_sales v "
        "JOIN dim_date d ON d.calendar_date = v.sale_date GROUP BY 1, 2, 3")


def apply_comments(connection) -> None:
    """Attach table and column comments (terse; a few are stale on purpose, see schema_comments.py)."""
    existing = {(r[0], r[1]) for r in connection.execute(
        "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'main'").fetchall()}
    tables = {r[0] for r in connection.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'").fetchall()}
    for table, comment in schema_comments.TABLE_COMMENTS.items():
        if table in tables:
            connection.execute(f"COMMENT ON TABLE {table} IS '{comment.replace(chr(39), chr(39) * 2)}'")
    for (table, column), (comment, _stale) in schema_comments.COLUMN_COMMENTS.items():
        if (table, column) in existing:
            connection.execute(f"COMMENT ON COLUMN {table}.{column} IS '{comment.replace(chr(39), chr(39) * 2)}'")
        else:
            raise KeyError(f"Comment given for a column that does not exist: {table}.{column}")


def save_internal(clean: dict, manifest: dict, internal_dir: Path) -> None:
    """Write the clean (pre-incident) tables and the incident manifest to the held-out folder."""
    internal_dir.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect()
    for name, frame in clean.items():
        connection.register("_frame", frame)
        target = internal_dir / f"{name}.parquet"
        connection.execute(f"COPY (SELECT * FROM _frame) TO '{target.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        connection.unregister("_frame")
        log(f"  wrote internal {target.name}")
    (internal_dir / "incident_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    connection.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the Tuomimetsa warehouse.")
    parser.add_argument("--out", type=Path, default=cfg.WAREHOUSE_PATH, help="DuckDB output path")
    parser.add_argument("--no-internal", action="store_true", help="skip the held-out clean tables")
    parser.add_argument("--no-manifest", action="store_true", help="skip writing the manifest (determinism rebuild)")
    args = parser.parse_args()

    output_path = args.out.resolve()
    # Safety: never write over anything but a .duckdb file, and never over a source file.
    protected = {Path(cfg.__file__).resolve(), Path(__file__).resolve()}
    if output_path.suffix != ".duckdb" or output_path in protected or cfg.WORLD_DIR.resolve() in output_path.parents:
        print(f"ERROR: refusing to write to {output_path}; the output must be a .duckdb file outside code/ and world/.")
        return 2
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    wal = output_path.with_suffix(".duckdb.wal")
    if wal.exists():
        wal.unlink()

    started = datetime.now()
    rng = lambda salt: np.random.default_rng([cfg.RANDOM_SEED, salt])
    try:
        dim_date, ref_fiscal, calendar = build_calendar()
        world = build_locations(rng(1), calendar)
        products = build_products(rng(2), calendar)
        members = build_members(rng(3), calendar, world)
        campaigns = build_campaigns(rng(4), calendar, world, members)
        ranged = build_ranging(rng(5), world, products)
        slots = simulate_receipt_slots(rng(6), calendar, world, members, campaigns)
        store_receipts = build_store_receipts(rng(7), calendar, world, members, slots)
        web_orders = build_web_orders(rng(8), calendar, world, members, slots)
        lines, web_orders = assemble_sales(rng(9), calendar, world, products, members, store_receipts, web_orders, ranged)
        log(f"Sales lines: {len(lines):,} (store {int((~lines['is_web']).sum()):,}, web {int(lines['is_web'].sum()):,}); "
            f"web orders: {len(web_orders):,}")
        returns = build_returns(rng(10), calendar, world, products, members, lines, web_orders, ranged)
        log(f"Return lines: {len(returns):,}")
        stock = build_stock(rng(11), calendar, world, products, lines, returns, ranged)
        log(f"Stock rows: {len(stock):,}")
        report = build_daily_report(calendar, world, products, lines, returns, web_orders)
        published_lines, published_stock, incident_manifest = apply_incidents(rng(12), calendar, world, lines, web_orders, stock)

        # Web order table for the database (member and pickup store resolved to keys).
        web_db = web_orders.copy()
        order_day = web_db["day"].to_numpy()
        has_member = web_db["member_idx"].to_numpy() >= 0
        member_keys = np.zeros(len(web_db), dtype=np.int64)
        member_keys[has_member] = resolve_version(members["member_index"], web_db["member_idx"].to_numpy()[has_member], order_day[has_member])
        web_db["member_key"] = pd.array(np.where(has_member, member_keys, 0), dtype="Int64")
        web_db.loc[~has_member, "member_key"] = pd.NA
        pickup_mask = web_db["pickup_loc_idx"].to_numpy() >= 0
        dispatch_local = utc_to_helsinki_local(pd.Series(web_db["dispatch_ts_utc"]))
        pickup_day = np.where(dispatch_local.notna(), (dispatch_local.dt.normalize() - pd.Timestamp(cfg.WINDOW_START)).dt.days.fillna(0).astype(int), order_day)
        pickup_keys = np.zeros(len(web_db), dtype=np.int64)
        pickup_keys[pickup_mask] = resolve_version(world["store_index"], web_db["pickup_loc_idx"].to_numpy()[pickup_mask], pickup_day[pickup_mask])
        web_db["pickup_store_key"] = pd.array(np.where(pickup_mask, pickup_keys, 0), dtype="Int64")
        web_db.loc[~pickup_mask, "pickup_store_key"] = pd.NA

        # Dimension frames ready for loading.
        dim_product = products["dim_product"]
        tables = {
            "dim_date": dim_date, "ref_fiscal": ref_fiscal, "dim_store": world["dim_store"],
            "ref_store_closure": world["ref_store_closure"], "dim_product": dim_product, "members": members,
            "campaigns": campaigns, "lines": published_lines, "returns": returns, "web_orders_db": web_db,
            "stock": published_stock, "report": report,
        }

        log(f"Writing the DuckDB file: {output_path}")
        connection = duckdb.connect(str(output_path))
        write_canonical_tables(connection, tables)
        write_clutter(connection, tables, world)
        apply_comments(connection)
        content_hash, per_table = compute_content_hash(connection)
        table_counts = {name: info["rows"] for name, info in per_table.items()}
        connection.execute("CHECKPOINT")
        connection.close()
        file_hash = file_sha256(output_path)
        log(f"Content hash {content_hash[:16]}...  file hash {file_hash[:16]}...")

        if not args.no_internal:
            log("Writing the held-out clean tables")
            clean_web = web_db.copy()
            save_internal({"sales_line_clean": lines.drop(columns=["header_row"], errors="ignore"),
                           "web_order_clean": clean_web, "stock_week_clean": stock,
                           "return_line_truth": returns,
                           "campaign_true_uplift": campaigns["dim_campaign"][["campaign_id", "segment", "true_uplift"]]},
                          incident_manifest, cfg.INTERNAL_DIR)
        if not args.no_manifest:
            manifest = {
                "built_at": started.isoformat(timespec="seconds"), "seed": cfg.RANDOM_SEED, "duckdb_version": duckdb.__version__,
                "pandas_version": pd.__version__, "numpy_version": np.__version__, "python_version": platform.python_version(),
                "content_hash": content_hash, "file_sha256": file_hash, "table_rows": table_counts,
                "run_seconds": round((datetime.now() - started).total_seconds(), 1), "incidents_planted": incident_manifest,
            }
            cfg.MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
            cfg.MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            log(f"Manifest written: {cfg.MANIFEST_PATH}")
    except Exception as error:                     # report clearly rather than crash with a bare traceback
        import traceback
        traceback.print_exc()
        print(f"\nERROR: warehouse generation failed: {error}")
        return 1
    log("Done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
