"""Shared helpers for the Tuomimetsa warehouse generator and its validator.

Kept separate so that generate_warehouse.py and validate_data.py use exactly
the same version-resolution, time-zone and content-hash logic.
"""
from __future__ import annotations

import hashlib
import time
from datetime import date

import numpy as np
import pandas as pd

import config as cfg

_START_TIME = time.time()


def log(message: str) -> None:
    """Print a timestamped progress line (seconds since the script started)."""
    print(f"[{time.time() - _START_TIME:7.1f}s] {message}", flush=True)


def day_offset(value: date) -> int:
    """Days from the window start to the given date (negative before the window)."""
    return (value - cfg.WINDOW_START).days


# ---------------------------------------------------------------------------
# Slowly changing dimension lookups: map (natural entity index, day) -> surrogate key
# ---------------------------------------------------------------------------

_SHIFT = 20_000        # makes day offsets positive (the earliest valid_from is year 2000)
_STRIDE = 100_000      # room for ~270 years of day offsets per entity


def make_version_index(natural_index: np.ndarray, valid_from_offset: np.ndarray, surrogate_key: np.ndarray):
    """Build a sorted composite index over dimension versions for fast lookups."""
    composite = natural_index.astype(np.int64) * _STRIDE + (valid_from_offset.astype(np.int64) + _SHIFT)
    order = np.argsort(composite, kind="stable")
    return composite[order], np.asarray(surrogate_key)[order]


def resolve_version(index, natural_index: np.ndarray, day_offsets: np.ndarray) -> np.ndarray:
    """Return, for every (entity, day) pair, the surrogate key of the version valid on that day."""
    composite_sorted, keys_sorted = index
    query = np.asarray(natural_index).astype(np.int64) * _STRIDE + (np.asarray(day_offsets).astype(np.int64) + _SHIFT)
    position = np.searchsorted(composite_sorted, query, side="right") - 1
    if (position < 0).any():
        raise ValueError("A lookup date falls before the first version of an entity; check valid_from values.")
    return keys_sorted[position]


# ---------------------------------------------------------------------------
# Time zones: the warehouse stores UTC; business dates are Helsinki time
# ---------------------------------------------------------------------------

def helsinki_local_to_utc(local_naive: pd.Series) -> pd.Series:
    """Convert naive Helsinki local timestamps to naive UTC (ambiguous autumn hour read as winter time)."""
    localised = local_naive.dt.tz_localize(
        "Europe/Helsinki", ambiguous=np.zeros(len(local_naive), dtype=bool), nonexistent="shift_forward"
    )
    return localised.dt.tz_convert("UTC").dt.tz_localize(None)


def utc_to_helsinki_local(utc_naive: pd.Series) -> pd.Series:
    """Convert naive UTC timestamps to naive Helsinki local timestamps."""
    return utc_naive.dt.tz_localize("UTC").dt.tz_convert("Europe/Helsinki").dt.tz_localize(None)


# ---------------------------------------------------------------------------
# Content hash (validator rule 11)
# ---------------------------------------------------------------------------

def compute_content_hash(connection) -> tuple[str, dict]:
    """Hash every table's contents, independent of row order, plus view definitions.

    Per table: row count and the sum of DuckDB's row hashes (an order-independent
    fingerprint), together with the column names and types. The overall digest
    is SHA-256 over those fingerprints in table-name order.
    """
    table_rows = connection.execute(
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_type = 'BASE TABLE' ORDER BY table_schema, table_name"
    ).fetchall()
    digest = hashlib.sha256()
    per_table = {}
    for schema_name, table_name in table_rows:
        qualified = f'"{schema_name}"."{table_name}"'
        columns = connection.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = ? AND table_name = ? ORDER BY ordinal_position", [schema_name, table_name]
        ).fetchall()
        column_list = ", ".join(f'"{name}"' for name, _ in columns)
        row_count, hash_sum = connection.execute(
            f"SELECT count(*), coalesce(sum(hash({column_list})::HUGEINT), 0) FROM {qualified}"
        ).fetchone()
        fingerprint = f"{schema_name}.{table_name}|{columns}|{row_count}|{hash_sum}"
        digest.update(fingerprint.encode("utf-8"))
        per_table[f"{schema_name}.{table_name}"] = {"rows": int(row_count), "hash_sum": str(hash_sum)}
    view_rows = connection.execute(
        "SELECT schema_name, view_name, sql FROM duckdb_views() WHERE NOT internal ORDER BY schema_name, view_name"
    ).fetchall()
    for schema_name, view_name, sql_text in view_rows:
        digest.update(f"{schema_name}.{view_name}|{sql_text}".encode("utf-8"))
    return digest.hexdigest(), per_table


def file_sha256(path) -> str:
    """SHA-256 of a file's bytes (reported alongside the content hash; not the determinism criterion)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()
