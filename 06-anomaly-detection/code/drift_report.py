"""
drift_report.py -- the standing vendor-drift review (06b's "fix" for 06a's
missed drift story).

This implements EXACTLY the pre-registered method, deterministic, no ML:

  1. Per vendor, per month: a volume-weighted mean unit price. Where a ledger
     carries item-level 'quantity' and 'unit_price_eur' columns, the weight
     is quantity and the price is unit_price_eur. Where it does not (06a's
     frozen 2025 ledger has no item granularity at all), this falls back to
     invoice-level totals: quantity = 1, price = amount_eur -- i.e. every
     invoice is its own "item" and the volume-weighted mean collapses to the
     ordinary invoice-count-weighted mean amount. A month scores only with a
     MINIMUM OF 3 INVOICES.
  2. Baseline: the expanding mean and standard deviation of all prior scored
     months, requiring a MINIMUM OF 3 MONTHS of history before scoring
     begins -- months 1-3 of any vendor's history are baseline-only.
  3. Signal: standardised deviation of the current month's price vs the
     trailing baseline; drift statistic = a one-sided CUSUM of those
     deviations, k = 0.5.
  4. Flag: a vendor is REPORTED when its CUSUM exceeds h = 4.0. The report
     ranks every scoreable vendor by peak CUSUM and prints a trajectory
     (month, price, deviation, cumulative CUSUM) for every FLAGGED vendor.

These four numbers -- min 3 invoices/month, min 3 baseline months, k = 0.5,
h = 4.0 -- are FIXED, pre-registered before any 06b data
existed, and are never adjusted to fit what this script finds when run. The
only free choice this script makes is which date field defines "month":
invoice_date (when the price was actually set), not posting_date (an AP
administrative artefact) -- a fixed, declared implementation choice, applied
identically to every ledger this script ever reads.

This script never imports, opens, or references any answer key, by design
(06b_mark.py is the only file with that permission) -- asserted below.

Usage:
    python code/drift_report.py <ledger_csv> <output_md> [--label "Some label"]

Runs read-only: it never writes anything except the one output markdown file
named on the command line.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Fixed, pre-registered method parameters. Do not tune.
# ---------------------------------------------------------------------------

MIN_INVOICES_PER_MONTH = 3
MIN_BASELINE_MONTHS = 3
CUSUM_K = 0.5
CUSUM_H = 4.0

# How many top-ranked vendors (by peak CUSUM) to print in the ranked table,
# regardless of flag status -- a reporting/display choice, not a method
# parameter; it does not affect who is flagged.
RANKED_TABLE_TOP_N = 25


def load_ledger(path: Path) -> pd.DataFrame:
    """Load a GL ledger and normalise it to the columns this method needs:
    vendor_id, vendor_name, invoice_date (as a pandas Timestamp), quantity,
    unit_price_eur. Falls back to invoice-level totals (quantity=1,
    unit_price_eur=amount_eur) when item-level columns are absent -- this is
    what lets the same script run unmodified against 06a's 2025 ledger
    (amount_eur only) and 06b's 2026 ledger (quantity + unit_price_eur)."""
    df = pd.read_csv(path)
    required = {"vendor_id", "vendor_name", "invoice_date", "amount_eur"}
    missing = required - set(df.columns)
    assert not missing, f"Ledger {path} is missing required columns: {missing}"

    df = df.copy()
    df["invoice_date"] = pd.to_datetime(df["invoice_date"])
    df["month"] = df["invoice_date"].dt.month

    if "quantity" in df.columns and "unit_price_eur" in df.columns:
        df["_quantity"] = df["quantity"].astype(float)
        df["_unit_price"] = df["unit_price_eur"].astype(float)
    else:
        df["_quantity"] = 1.0
        df["_unit_price"] = df["amount_eur"].astype(float)

    return df


def monthly_volume_weighted_price(df: pd.DataFrame) -> pd.DataFrame:
    """Per vendor, per month: volume-weighted mean unit price and invoice
    (row) count. Returns one row per (vendor_id, month) that clears the
    MIN_INVOICES_PER_MONTH floor -- months below it are dropped, not
    imputed, exactly as the design specifies ("minimum 3 invoices/month
    to score a month")."""
    counts = df.groupby(["vendor_id", "month"]).size().rename("n_invoices")
    weighted_sum = df.assign(_wp=df["_quantity"] * df["_unit_price"]).groupby(["vendor_id", "month"])["_wp"].sum()
    weight_total = df.groupby(["vendor_id", "month"])["_quantity"].sum()
    price = (weighted_sum / weight_total).rename("price")

    monthly = pd.concat([counts, price], axis=1).reset_index()
    monthly = monthly[monthly["n_invoices"] >= MIN_INVOICES_PER_MONTH].copy()
    return monthly


def compute_vendor_trajectory(vendor_months: pd.DataFrame) -> dict:
    """
    vendor_months: rows for ONE vendor, columns [month, price], sorted by
    month ascending, already filtered to months clearing the invoice floor.
    Runs the expanding-baseline CUSUM exactly as specified:
      - months are processed in calendar order;
      - a month is BASELINE-ONLY until at least MIN_BASELINE_MONTHS of prior
        scored months exist;
      - once eligible, z = (price - baseline_mean) / baseline_std using the
        mean/std of every prior scored month (population std; a baseline of
        exactly 3 identical months has std 0, in which case z is defined as
        0 -- a flat baseline gives no signal, which is the correct behaviour
        of a standardised-deviation statistic);
      - CUSUM: S_t = max(0, S_{t-1} + z_t - k), S_0 = 0.
    Returns a dict with the full month-by-month trajectory and summary
    fields (peak_cusum, peak_month, first_crossing_month, flagged).
    """
    months = vendor_months["month"].tolist()
    prices = vendor_months["price"].tolist()

    trajectory = []
    baseline_history = []  # prior SCORED months' prices, in order
    cusum = 0.0
    peak_cusum = 0.0
    peak_month = None
    first_crossing_month = None

    for month, price in zip(months, prices):
        if len(baseline_history) < MIN_BASELINE_MONTHS:
            trajectory.append({
                "month": month, "price": price, "role": "baseline_only",
                "baseline_mean": None, "baseline_std": None, "z": None, "cusum": None,
            })
            baseline_history.append(price)
            continue

        baseline_mean = float(np.mean(baseline_history))
        baseline_std = float(np.std(baseline_history, ddof=0))
        z = 0.0 if baseline_std == 0.0 else (price - baseline_mean) / baseline_std
        cusum = max(0.0, cusum + z - CUSUM_K)

        if cusum > peak_cusum:
            peak_cusum = cusum
            peak_month = month
        if cusum > CUSUM_H and first_crossing_month is None:
            first_crossing_month = month

        trajectory.append({
            "month": month, "price": price, "role": "scored",
            "baseline_mean": baseline_mean, "baseline_std": baseline_std,
            "z": z, "cusum": cusum,
        })
        baseline_history.append(price)

    return {
        "trajectory": trajectory,
        "peak_cusum": peak_cusum,
        "peak_month": peak_month,
        "first_crossing_month": first_crossing_month,
        "flagged": first_crossing_month is not None,
        "n_scored_months": sum(1 for t in trajectory if t["role"] == "scored"),
    }


def run_drift_review(ledger_path: Path) -> dict:
    """Runs the full method on one ledger. Returns a dict:
    {vendor_id: {vendor_name, n_invoices_total, result-of-compute_vendor_trajectory}}."""
    df = load_ledger(ledger_path)
    monthly = monthly_volume_weighted_price(df)

    vendor_names = df.drop_duplicates("vendor_id").set_index("vendor_id")["vendor_name"].to_dict()
    total_invoices = df.groupby("vendor_id").size().to_dict()

    results = {}
    for vendor_id, group in monthly.groupby("vendor_id"):
        group = group.sort_values("month")
        traj = compute_vendor_trajectory(group[["month", "price"]])
        results[vendor_id] = {
            "vendor_name": vendor_names.get(vendor_id, vendor_id),
            "n_invoices_total": int(total_invoices.get(vendor_id, 0)),
            **traj,
        }

    # Vendors that never cleared MIN_INVOICES_PER_MONTH in enough months to
    # be scoreable at all (e.g. a vendor that never reaches 3 invoices in
    # any calendar month) are recorded separately -- they cannot be ranked,
    # and the report says so explicitly rather than silently omitting them.
    scoreable_vendor_ids = set(results.keys())
    all_vendor_ids = set(df["vendor_id"].unique())
    unscoreable = sorted(all_vendor_ids - scoreable_vendor_ids)
    unscoreable_detail = {
        vid: {
            "vendor_name": vendor_names.get(vid, vid),
            "n_invoices_total": int(total_invoices.get(vid, 0)),
            "months_with_ge_3_invoices": int((df[df["vendor_id"] == vid].groupby("month").size() >= MIN_INVOICES_PER_MONTH).sum()),
        }
        for vid in unscoreable
    }

    return {"results": results, "unscoreable": unscoreable_detail, "n_vendors_total": len(all_vendor_ids)}


MONTH_NAMES = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def display_path(path: Path) -> str:
    """Path as shown in the report: relative to the case folder when the
    file sits inside it (so the report carries no machine-specific path),
    otherwise just the file name."""
    case_folder = Path(__file__).resolve().parent.parent
    try:
        return path.resolve().relative_to(case_folder).as_posix()
    except ValueError:
        return path.name


def format_report(review: dict, ledger_path: Path, label: str) -> str:
    results = review["results"]
    unscoreable = review["unscoreable"]
    n_vendors_total = review["n_vendors_total"]

    ranked = sorted(results.items(), key=lambda kv: kv[1]["peak_cusum"], reverse=True)
    flagged = [(vid, r) for vid, r in ranked if r["flagged"]]

    lines = []
    lines.append(f"# Vendor drift review -- {label}")
    lines.append("")
    lines.append(f"Source ledger: `{display_path(ledger_path)}`")
    lines.append("")
    lines.append(
        "Method: per-vendor, per-month volume-weighted unit price (falling back to "
        "invoice-level totals where no item granularity exists); expanding prior-months "
        f"baseline (minimum {MIN_BASELINE_MONTHS} months of history, minimum "
        f"{MIN_INVOICES_PER_MONTH} invoices to score a month); one-sided CUSUM of "
        f"standardised monthly deviations (k = {CUSUM_K}); flagged at CUSUM > h = {CUSUM_H}. "
        "Deterministic, no machine learning. Parameters fixed before any 06b data existed "
        "and never tuned against this ledger's output."
    )
    lines.append("")
    lines.append(f"**{n_vendors_total} vendors in the ledger; {len(results)} scoreable "
                  f"(cleared the {MIN_INVOICES_PER_MONTH}-invoices/month floor in at least "
                  f"{MIN_BASELINE_MONTHS + 1} months); {len(unscoreable)} not scoreable at all.**")
    lines.append("")

    lines.append("## Ranked table (top {} of {} scoreable vendors, by peak CUSUM)".format(
        min(RANKED_TABLE_TOP_N, len(ranked)), len(ranked)
    ))
    lines.append("")
    lines.append("| Rank | Vendor ID | Vendor name | Peak CUSUM | Peak month | Flagged | First crossing month |")
    lines.append("|---|---|---|---|---|---|---|")
    for rank, (vid, r) in enumerate(ranked[:RANKED_TABLE_TOP_N], start=1):
        peak_month_name = MONTH_NAMES[r["peak_month"]] if r["peak_month"] else "-"
        crossing_name = MONTH_NAMES[r["first_crossing_month"]] if r["first_crossing_month"] else "-"
        flagged_mark = "**YES**" if r["flagged"] else "no"
        lines.append(
            f"| {rank} | {vid} | {r['vendor_name']} | {r['peak_cusum']:.2f} | "
            f"{peak_month_name} | {flagged_mark} | {crossing_name} |"
        )
    lines.append("")

    lines.append(f"## Flagged vendors ({len(flagged)}) -- trajectory detail")
    lines.append("")
    if not flagged:
        lines.append("No vendor's CUSUM crossed h = {:.1f}.".format(CUSUM_H))
    for vid, r in flagged:
        lines.append(f"### {r['vendor_name']} ({vid})")
        lines.append("")
        lines.append(f"Peak CUSUM {r['peak_cusum']:.2f} in {MONTH_NAMES[r['peak_month']]}; "
                      f"first crossed h = {CUSUM_H:.1f} in {MONTH_NAMES[r['first_crossing_month']]}.")
        lines.append("")
        lines.append("| Month | Role | Price (EUR) | Baseline mean | Baseline std | z | CUSUM |")
        lines.append("|---|---|---|---|---|---|---|")
        for row in r["trajectory"]:
            month_name = MONTH_NAMES[row["month"]]
            if row["role"] == "baseline_only":
                lines.append(f"| {month_name} | baseline-only | {row['price']:.2f} | - | - | - | - |")
            else:
                lines.append(
                    f"| {month_name} | scored | {row['price']:.2f} | {row['baseline_mean']:.2f} | "
                    f"{row['baseline_std']:.3f} | {row['z']:.2f} | {row['cusum']:.2f} |"
                )
        lines.append("")

    if unscoreable:
        lines.append(f"## Not scoreable ({len(unscoreable)} vendors)")
        lines.append("")
        lines.append(
            f"These vendors never reached {MIN_INVOICES_PER_MONTH} invoices in enough "
            f"calendar months to build a baseline and score at least one month -- out of "
            "scope for this method, not a negative finding."
        )
        lines.append("")
        lines.append("| Vendor ID | Vendor name | Total invoices | Months with >= 3 invoices |")
        lines.append("|---|---|---|---|")
        for vid, d in sorted(unscoreable.items(), key=lambda kv: -kv[1]["n_invoices_total"])[:20]:
            lines.append(f"| {vid} | {d['vendor_name']} | {d['n_invoices_total']} | {d['months_with_ge_3_invoices']} |")
        if len(unscoreable) > 20:
            lines.append(f"| ... | ({len(unscoreable) - 20} more) | | |")
        lines.append("")

    return "\n".join(lines) + "\n"


def main():
    if len(sys.argv) < 3:
        print("Usage: python code/drift_report.py <ledger_csv> <output_md> [--label \"Some label\"]")
        sys.exit(2)

    ledger_path = Path(sys.argv[1]).resolve()
    output_path = Path(sys.argv[2]).resolve()
    label = None
    if "--label" in sys.argv:
        idx = sys.argv.index("--label")
        label = sys.argv[idx + 1]
    if label is None:
        label = ledger_path.stem

    print("=" * 70)
    print("Vendor drift review")
    print("=" * 70)
    print(f"Ledger: {ledger_path}")
    print(f"Output: {output_path}")

    assert ledger_path.exists(), f"Ledger not found: {ledger_path}"
    assert output_path.suffix == ".md", "Output path must be a .md file"

    print("\n[1/3] Loading ledger and computing per-vendor monthly volume-weighted prices...")
    review = run_drift_review(ledger_path)
    print(f"  {review['n_vendors_total']} vendors total; {len(review['results'])} scoreable; "
          f"{len(review['unscoreable'])} not scoreable")

    print("\n[2/3] Running the expanding-baseline CUSUM (k={}, h={})...".format(CUSUM_K, CUSUM_H))
    n_flagged = sum(1 for r in review["results"].values() if r["flagged"])
    print(f"  {n_flagged} vendor(s) flagged (CUSUM > {CUSUM_H})")

    print("\n[3/3] Writing report...")
    report_text = format_report(review, ledger_path, label)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(report_text)
    print(f"  wrote {output_path}")

    print("\n" + "=" * 70)
    print("Done.")
    print("=" * 70)


if __name__ == "__main__":
    main()
