# Data coherence validation report

Date: 11 September 2026
Dataset: v4 frozen dataset (the shipped, published dataset; the A4 v1→v4
iteration trail that produced it is in `data/model/ml_report.md`)
Command: `python code/validate_data.py`

This is the data-quality report, run against
the frozen v4 dataset before packaging. Note on reproduction: the command above
was run with `PYTHONIOENCODING=utf-8` set in the environment — the script's own
print statements emit an em-dash and a `≤` character that a plain Windows
console (cp1252 code page) cannot encode, which otherwise crashes the process
with a `UnicodeEncodeError` after the Rule 7 line. This is a console-encoding
artefact, not a data or logic defect: every rule check below completed and
passed. The script itself was not modified.

All eight coherence rules pass. Full stdout follows verbatim.

```
======================================================================
Kataja Analytics — Data Coherence Validation Report
======================================================================

Loading data files...
  accounts:       500 rows
  usage_monthly:  8,244 rows
  answer_key:     500 rows
  ticket_briefs:  3,777 rows

--- Rule 6: Referential integrity ---
  PASS

--- Rule 7: Date constraints ---
  PASS — Pre-signup violations: 0; Post-churn violations: 0; Weekday tickets: 87.4%

--- Rule 4: A7 resolution ≤2 days, no competitor mentions ---
  PASS — A7 tickets: 937; Slow resolutions (>2 days): 0; Competitor mentions: 0

--- Rule 3: A5 — no text signal ---
  PASS — A5 tickets: 84; Angry/frustrated stages: 0; Competitor mentions: 0

--- Rule 1: Module–usage coherence (A3) ---
  PASS — A3 collapse-module ticket rate: 43.32%; Non-A3 baseline rate: 42.66%; Lift: 1.02×

--- Rule 5: Competitor mentions in context + noise coverage ---
  PASS — Total competitor mentions: 145; In healthy accounts (noise): 54; In churning accounts: 91; In A7 (must be 0): 0

--- Rule 2: A4 usage indistinguishable from A1 until ≤1 month pre-churn ---
  PASS — A4 (n=46) vs A1 (n=176): all metric slopes within 2σ of A1 baseline (yes)

  Per-metric comparison (slopes in units/month, z-score vs A1):
  Metric                   A4 slope   A1 slope   A1 std  z-score
  --------------------------------------------------------------
  dashboard_views            0.1018     4.2444   4.1208   -1.005
  reports_created            0.0899     0.9995   1.0763   -0.845
  connector_syncs           -0.3010     3.1111   4.0369   -0.845
  alerts_configured          0.0807     0.4596   0.5266   -0.719
  api_calls                  0.6935    10.8859  15.0617   -0.677
  exports_run                0.1430     1.1379   1.2199   -0.816
  logins                     0.8327     5.6335   7.3131   -0.656

--- Rule 8: Non-churn ticket dates spread across account life ---
  PASS — A1 median=0.338 IQR=0.331 [OK]
  A2 median=0.460 IQR=0.459 [OK]
  A6 median=0.670 IQR=0.434 [OK]
  A7 median=0.384 IQR=0.478 [OK]
  A8 median=0.358 IQR=0.357 [OK]
  A6 escalation-in-dip-window (+/-1mo): 126/126 OK

======================================================================
SUMMARY
======================================================================
  Rule 6: PASS
  Rule 7: PASS
  Rule 4: PASS
  Rule 3: PASS
  Rule 1: PASS
  Rule 5: PASS
  Rule 2: PASS
  Rule 8: PASS

ALL RULES PASSED — dataset is coherent and ready for analysis.
======================================================================
```
