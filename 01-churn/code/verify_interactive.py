"""QA gate for interactive/churn_explorer.html. Exits 1 on failure.

Checks (the honest subset for this page, matching the 03 Invoices convention
in spirit): self-containment (single external request = Google Fonts, no
other http(s) references anywhere in the file, no fetch/XHR), hpx- class
prefix discipline, balanced structural tags, and the page's displayed
headline numbers re-checked verbatim against data/fusion/results_summary.json
(the page embeds a JSON payload built by interactive/build_data.py from that
same source -- this script re-derives the comparison independently rather
than trusting the build step). A handful of embeddability checks (lang,
viewport, iframe height reporting, no large fixed pixel heights) are included
too, since they are cheap and mechanical.

Not implemented (would need a headless browser, out of scope for a static
QA gate): rendered-layout / visual review.

Run with:
    python code/verify_interactive.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths -- resolved relative to this script, never hardcoded absolute
# ---------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
# Optional first argument: a different page to check (e.g. interactive/staging/churn_explorer.staging.html).
PAGE_PATH = (Path(sys.argv[1]).resolve() if len(sys.argv) > 1
             else PROJECT_ROOT / "interactive" / "churn_explorer.html")
RESULTS_SUMMARY_PATH = PROJECT_ROOT / "data" / "fusion" / "results_summary.json"
ACCOUNTS_PATH = PROJECT_ROOT / "data" / "accounts.csv"
TICKETS_PATH = PROJECT_ROOT / "data" / "tickets.csv"

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    """Print a PASS/FAIL line and record the name of any failure."""
    status = "PASS" if ok else "FAIL"
    suffix = f" -- {detail}" if detail and not ok else ""
    print(f"[{status}] {name}{suffix}")
    if not ok:
        failures.append(name)


def main() -> None:
    print("=" * 70)
    print("Churn explorer interactive page -- QA gate")
    print("=" * 70)

    # -----------------------------------------------------------------
    # Load inputs, with informative errors rather than bare crashes
    # -----------------------------------------------------------------
    if not PAGE_PATH.exists():
        print(f"ERROR: page not found at {PAGE_PATH}", file=sys.stderr)
        sys.exit(1)
    if not RESULTS_SUMMARY_PATH.exists():
        print(f"ERROR: results summary not found at {RESULTS_SUMMARY_PATH}", file=sys.stderr)
        sys.exit(1)

    html = PAGE_PATH.read_text(encoding="utf-8")
    try:
        results_summary = json.loads(RESULTS_SUMMARY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: results_summary.json is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Page size: {PAGE_PATH.stat().st_size / 1024:.1f} KB")
    print()

    # -----------------------------------------------------------------
    # 1. Self-containment: exactly one external request (Google Fonts),
    #    no other http(s) references anywhere, no fetch/XHR.
    # -----------------------------------------------------------------
    tag_externals = re.findall(r'(?:href|src)="(https?://[^"]+)"', html)
    check(
        "exactly one external request via href/src (Google Fonts only)",
        len(tag_externals) == 1 and "fonts.googleapis.com" in tag_externals[0],
        str(tag_externals),
    )

    # Every http(s):// occurrence anywhere in the file, minus the one allowed
    # Google Fonts href and the SVG XML namespace string (not a network
    # request -- it is a literal namespace identifier used by
    # document.createElementNS, never dereferenced over the network).
    all_http_refs = re.findall(r"https?://[^\s\"'<>)]+", html)
    unexpected = [
        ref for ref in all_http_refs
        if "fonts.googleapis.com" not in ref and ref != "http://www.w3.org/2000/svg"
    ]
    check("no other http(s) references anywhere in the file", not unexpected, str(unexpected[:10]))

    check("no fetch(...) call", "fetch(" not in html)
    check("no XMLHttpRequest", "XMLHttpRequest" not in html)

    # -----------------------------------------------------------------
    # 2. hpx- class-prefix discipline
    # -----------------------------------------------------------------
    classes: set[str] = set()
    for class_attr in re.findall(r'class="([^"]+)"', html):
        classes.update(class_attr.split())
    non_prefixed = sorted(c for c in classes if not c.startswith("hpx-"))
    check("hpx- prefix on every CSS class", not non_prefixed, str(non_prefixed[:10]))

    # -----------------------------------------------------------------
    # 3. Balanced structural tags (a cheap self-containment / well-formed
    #    -HTML sanity check; svg elements here are built dynamically via JS,
    #    so 0-vs-0 is the expected pass, not a skipped check).
    # -----------------------------------------------------------------
    for tag in ("div", "section", "table", "svg", "script", "style"):
        n_open = len(re.findall(rf"<{tag}[\s>]", html))
        n_close = html.count(f"</{tag}>")
        check(f"balanced <{tag}>...</{tag}>", n_open == n_close, f"{n_open} open vs {n_close} close")

    # -----------------------------------------------------------------
    # 4. Embedded JSON payload parses, and headline numbers re-checked
    #    verbatim against data/fusion/results_summary.json.
    # -----------------------------------------------------------------
    match = re.search(
        r'<script type="application/json" id="hpx-data">(\{.*?\})</script>',
        html,
        re.S,
    )
    check("embedded hpx-data JSON block found", match is not None)

    if match is not None:
        try:
            embedded = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            check("embedded hpx-data JSON parses", False, str(exc))
            embedded = None
        else:
            check("embedded hpx-data JSON parses", True)

        if embedded is not None:
            # meta block: dataset-level counts, checked against the raw CSVs
            # directly (not just against results_summary.json) so a stale
            # meta block cannot hide behind a stale summary file too.
            if ACCOUNTS_PATH.exists() and TICKETS_PATH.exists():
                import csv

                with ACCOUNTS_PATH.open(encoding="utf-8") as f:
                    accounts_rows = list(csv.DictReader(f))
                with TICKETS_PATH.open(encoding="utf-8") as f:
                    tickets_rows = list(csv.DictReader(f))
                n_accounts = len(accounts_rows)
                n_tickets = len(tickets_rows)
                n_churned = sum(1 for r in accounts_rows if r.get("churned") in ("True", "true", "1"))

                meta = embedded.get("meta", {})
                check("meta.n_accounts matches accounts.csv", meta.get("n_accounts") == n_accounts,
                      f"embedded={meta.get('n_accounts')} actual={n_accounts}")
                check("meta.n_tickets matches tickets.csv", meta.get("n_tickets") == n_tickets,
                      f"embedded={meta.get('n_tickets')} actual={n_tickets}")
                check("meta.n_churned matches accounts.csv", meta.get("n_churned") == n_churned,
                      f"embedded={meta.get('n_churned')} actual={n_churned}")
            else:
                check("meta counts checked against raw CSVs", False, "accounts.csv or tickets.csv missing")

            # head_to_head: AUC / average precision / recall@50 / recall@100
            # for ml_only, text_only, combined -- the page's central claim.
            embedded_h2h = embedded.get("head_to_head", {})
            summary_h2h = results_summary.get("head_to_head", {})
            check(
                "head_to_head block matches results_summary.json exactly",
                embedded_h2h == summary_h2h,
                f"embedded={embedded_h2h} summary={summary_h2h}",
            )

            # The headline result itself: combined AUC 0.8666 -> 0.8902-ish,
            # recall@100 lifting from ml_only to combined (~59% -> ~66%).
            ml_auc = summary_h2h.get("ml_only", {}).get("auc")
            combined_auc = summary_h2h.get("combined", {}).get("auc")
            ml_recall100 = summary_h2h.get("ml_only", {}).get("recall_at_100")
            combined_recall100 = summary_h2h.get("combined", {}).get("recall_at_100")
            check(
                "AUC lifts from ml_only to combined (0.867 -> 0.890 headline)",
                ml_auc is not None and combined_auc is not None and combined_auc > ml_auc
                and round(ml_auc, 3) == 0.867 and round(combined_auc, 3) == 0.890,
                f"ml_auc={ml_auc} combined_auc={combined_auc}",
            )
            check(
                "recall@100 lifts from ~59% to ~66% (headline)",
                ml_recall100 is not None and combined_recall100 is not None
                and round(ml_recall100 * 100) == 59 and round(combined_recall100 * 100) == 66,
                f"ml_recall100={ml_recall100} combined_recall100={combined_recall100}",
            )

            # a4_table: the money-segment table
            check(
                "a4_table matches results_summary.json exactly",
                embedded.get("a4_table") == results_summary.get("a4_table"),
                f"embedded={embedded.get('a4_table')} summary={results_summary.get('a4_table')}",
            )

            # a7_verdict and a5_honesty_check: the credibility and honesty checks
            check(
                "a7_verdict matches results_summary.json exactly",
                embedded.get("a7_verdict") == results_summary.get("a7_verdict"),
            )
            check(
                "a5_honesty_check matches results_summary.json exactly",
                embedded.get("a5_honesty_check") == results_summary.get("a5_honesty_check"),
            )

            # fusion_coefficients: the sliders' underlying model
            check(
                "fusion_coefficients match results_summary.json exactly",
                embedded.get("fusion_coefficients") == results_summary.get("fusion_coefficients"),
            )

            # arr_business_translation: the euros-at-risk headline
            check(
                "arr_business_translation matches results_summary.json exactly",
                embedded.get("arr_business_translation") == results_summary.get("arr_business_translation"),
            )

    # -----------------------------------------------------------------
    # 5. Embeddability checks (cheap, mechanical).
    # -----------------------------------------------------------------
    check("lang=en-GB on <html>", '<html lang="en-GB">' in html)
    check("viewport meta present", 'name="viewport"' in html)
    check("prefers-reduced-motion respected", "prefers-reduced-motion" in html)
    check(
        "iframe height reporting via postMessage",
        "postMessage" in html and "hpx-height" in html,
    )

    fixed_heights = [
        int(h) for h in re.findall(r"[^-]height\s*:\s*(\d+)px", html) if int(h) > 60
    ]
    check("no large fixed pixel heights (>60px)", not fixed_heights, str(fixed_heights[:10]))

    # -----------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------
    print()
    print("=" * 70)
    if failures:
        print(f"FAILED: {len(failures)} check(s): {failures}")
        sys.exit(1)
    print(f"ALL CHECKS PASS ({PAGE_PATH.stat().st_size / 1024:.1f} KB, self-contained)")


if __name__ == "__main__":
    main()
