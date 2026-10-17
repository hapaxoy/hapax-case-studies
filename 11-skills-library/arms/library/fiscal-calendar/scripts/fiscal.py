"""
fiscal.py - turn a fiscal-calendar phrase into dates, read from dim_date.

Usage:
    conda run -n <env> python fiscal.py PATH_TO_DUCKDB "last period"
    conda run -n <env> python fiscal.py PATH_TO_DUCKDB "Q2" --as-of 2026-03-24
    conda run -n <env> python fiscal.py PATH_TO_DUCKDB "P4 FY2025/26" --compare
    conda run -n <env> python fiscal.py PATH_TO_DUCKDB "same week last year"
    conda run -n <env> python fiscal.py PATH_TO_DUCKDB "YTD" --json

Phrases understood (case does not matter):
    last period                  last completed fiscal period (CAL-RELATIVE)
    YTD                          fiscal year to date through the last completed fiscal week (CAL-RELATIVE)
    YTD as of the end of P4      week 1 to the last week of P4 (CAL-RELATIVE, CAL-PERIODS; REQ-D09 = weeks 1-17)
    this year                    the current fiscal year, as far as it is loaded (CAL-RELATIVE)
    last completed week          the last completed fiscal week (the end point YTD uses)
    current period / current week   the period or week holding the as-of date (may be partial)
    same week last year          last completed week, with the same fiscal week last year
    same period last year        last completed period, with the same period number last year
    last N weeks                 the N most recent completed fiscal weeks
    FY2025/26 (or FY25/26)       a whole fiscal year
    P5 / P05 [FY..]              a fiscal period
    P1-P3 / P1 to P4 [FY..]      a run of periods
    Q2 [FY..]                    a fiscal quarter (CAL-PERIODS)
    H1 / H2 / first half / second half / back half [FY..]   P1-P6 or P7-P12 (as read in the request history)
    week 22 / W22 [FY..]         a fiscal week
A period, quarter, half or week given without a year is read as the most recent completed one,
which is how the accepted requests in the history read them (e.g. REQ-D03, REQ-D06, REQ-D12).

"last year" on its own is not defined in the metric dictionary. The script refuses it and asks
for the fiscal year to be named; see fiscal-calendar/SKILL.md for how past requests read it.

--as-of DATE   the date the request was received (default: the last date loaded in dim_date).
--compare      also print the comparator: the same fiscal week numbers in the prior fiscal year
               (CAL-COMPARE). Week 53 has no comparator and is listed separately (CAL-WEEK53).
--json         machine-readable output.

Only the standard library and duckdb are used. The database is opened read-only.
"""

import argparse
import datetime as dt
import json
import re
import sys

try:
    import duckdb
except ImportError:
    sys.exit("fiscal.py needs the duckdb package (conda run -n <env> ...).")


# ---------------------------------------------------------------------------
# Loading the calendar
# ---------------------------------------------------------------------------

def load_weeks(con):
    """One record per fiscal week present in dim_date, in date order."""
    rows = con.execute(
        """
        SELECT fiscal_year, fiscal_week, fiscal_period, fiscal_quarter,
               MIN(fiscal_week_start_date) AS week_start,
               MAX(fiscal_week_end_date)   AS week_end,
               MIN(calendar_date)          AS first_loaded,
               MAX(calendar_date)          AS last_loaded,
               MAX(weeks_in_fiscal_year)   AS weeks_in_year
        FROM dim_date
        GROUP BY fiscal_year, fiscal_week, fiscal_period, fiscal_quarter
        ORDER BY week_start
        """
    ).fetchall()
    keys = ["fiscal_year", "fiscal_week", "fiscal_period", "fiscal_quarter",
            "week_start", "week_end", "first_loaded", "last_loaded", "weeks_in_year"]
    return [dict(zip(keys, row)) for row in rows]


def last_loaded_date(con):
    """Last calendar date present in dim_date (the warehouse load point)."""
    return con.execute("SELECT MAX(calendar_date) FROM dim_date").fetchone()[0]


# ---------------------------------------------------------------------------
# Helpers for labels and selection
# ---------------------------------------------------------------------------

def normalise_year(text):
    """Accept FY2025/26, FY25/26, fy 2025/26; return 'FY2025/26' or None."""
    match = re.search(r"fy\s*(\d{2,4})\s*/\s*(\d{2})", text, re.IGNORECASE)
    if not match:
        return None
    start = match.group(1)
    if len(start) == 2:
        start = "20" + start
    return f"FY{start}/{match.group(2)}"


def strip_year(text):
    return re.sub(r"fy\s*\d{2,4}\s*/\s*\d{2}", " ", text, flags=re.IGNORECASE).strip()


def fiscal_years_in_order(weeks):
    seen = []
    for week in weeks:
        if week["fiscal_year"] not in seen:
            seen.append(week["fiscal_year"])
    return seen


def prior_year_label(year_label, weeks):
    years = fiscal_years_in_order(weeks)
    index = years.index(year_label)
    return years[index - 1] if index > 0 else None


def week_record(weeks, year_label, week_number):
    for week in weeks:
        if week["fiscal_year"] == year_label and week["fiscal_week"] == week_number:
            return week
    return None


def completed_weeks(weeks, as_of):
    """Weeks whose Sunday is on or before the as-of date and fully loaded."""
    return [w for w in weeks if w["week_end"] <= as_of and w["last_loaded"] == w["week_end"]]


def current_year(weeks, as_of):
    for week in weeks:
        if week["week_start"] <= as_of <= week["week_end"]:
            return week["fiscal_year"]
    # as-of beyond the loaded calendar: use the last loaded year
    return weeks[-1]["fiscal_year"]


def select_weeks(weeks, year_label, predicate):
    return [w for w in weeks if w["fiscal_year"] == year_label and predicate(w)]


def most_recent_completed(weeks, as_of, year_label, predicate, expected_weeks_fn):
    """
    Find the most recent fiscal year (on or before the as-of year) in which the unit selected by
    `predicate` is complete as of the as-of date. If year_label is given, use that year only.
    """
    completed = {(w["fiscal_year"], w["fiscal_week"]) for w in completed_weeks(weeks, as_of)}
    years = fiscal_years_in_order(weeks)
    if year_label:
        candidates = [year_label]
    else:
        this_year = current_year(weeks, as_of)
        candidates = list(reversed(years[: years.index(this_year) + 1]))
    for label in candidates:
        chosen = select_weeks(weeks, label, predicate)
        if not chosen:
            continue
        if year_label:
            return label, chosen
        expected = expected_weeks_fn(label, chosen)
        if len(chosen) == expected and all((label, w["fiscal_week"]) in completed for w in chosen):
            return label, chosen
    return None, []


# ---------------------------------------------------------------------------
# Building the answer
# ---------------------------------------------------------------------------

def describe(label, chosen, as_of, loaded_to, notes, expected=None):
    """
    Summarise a set of fiscal weeks as a date range with completeness flags.
    `expected` is the number of weeks the unit should have; when dim_date holds fewer (the unit runs
    past the load point), the end date is extended to the unit's real end and the range is incomplete.
    """
    notes = list(notes)
    start = min(w["week_start"] for w in chosen)
    end = max(w["week_end"] for w in chosen)
    if expected and len(chosen) < expected:
        end = start + dt.timedelta(days=7 * expected - 1)
        notes.append(f"Only {len(chosen)} of the {expected} fiscal weeks are in dim_date.")
    years = sorted({w["fiscal_year"] for w in chosen})
    week_numbers = sorted(w["fiscal_week"] for w in chosen)
    periods = sorted({(w["fiscal_year"], w["fiscal_period"]) for w in chosen})
    complete = end <= as_of and end <= loaded_to
    loaded_end = min(end, loaded_to)
    result = {
        "phrase": label,
        "fiscal_years": years,
        "fiscal_periods": [f"{y} P{p:02d}" for y, p in periods],
        "fiscal_weeks": f"{week_numbers[0]}-{week_numbers[-1]}" if len(week_numbers) > 1 else str(week_numbers[0]),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "weeks": len(chosen),
        "days": (end - start).days + 1,
        "includes_week_53": any(w["fiscal_week"] == 53 for w in chosen),
        "complete_as_of": complete,
        "loaded_through": loaded_end.isoformat(),
        "sql_filter": sql_filter(chosen),
        "notes": notes,
    }
    if result["includes_week_53"]:
        result["notes"].append(
            "Includes week 53 (27 Apr - 3 May 2026), which has no prior-year comparator (CAL-WEEK53). "
            "Drop it from both years when comparing (REQ-D04); keep it when no comparison is asked (REQ-D12)."
        )
    if end > loaded_to:
        result["notes"].append(
            f"The range runs past the last loaded date ({loaded_to}); only data through {loaded_to} exists (CAL-DATA-THROUGH)."
        )
    elif end > as_of:
        result["notes"].append(f"The range is not complete as of {as_of}.")
    return result


def sql_filter(chosen):
    """A dim_date filter (alias d) that selects exactly these fiscal weeks."""
    by_year = {}
    for week in chosen:
        by_year.setdefault(week["fiscal_year"], []).append(week["fiscal_week"])
    parts = []
    for year_label, numbers in sorted(by_year.items()):
        numbers.sort()
        if numbers == list(range(numbers[0], numbers[-1] + 1)):
            parts.append(f"(d.fiscal_year = '{year_label}' AND d.fiscal_week BETWEEN {numbers[0]} AND {numbers[-1]})")
        else:
            parts.append(f"(d.fiscal_year = '{year_label}' AND d.fiscal_week IN ({', '.join(map(str, numbers))}))")
    return " OR ".join(parts)


def comparator(weeks, chosen, loaded_to):
    """Same fiscal week numbers in the prior fiscal year (CAL-COMPARE); week 53 has none (CAL-WEEK53)."""
    matched, unmatched = [], []
    for week in chosen:
        prior = prior_year_label(week["fiscal_year"], weeks)
        record = week_record(weeks, prior, week["fiscal_week"]) if prior else None
        if record is None:
            unmatched.append(f"{week['fiscal_year']} week {week['fiscal_week']}")
        else:
            matched.append(record)
    if not matched:
        return {"comparator": None, "weeks_without_comparator": unmatched,
                "note": "No prior-year weeks in the warehouse for this range (dim_date starts 29 April 2024)."}
    info = describe("comparator", matched, loaded_to, loaded_to, [])
    info["weeks_without_comparator"] = unmatched
    this_year_numbers = sorted(w["fiscal_week"] for w in chosen if w["fiscal_week"] != 53)
    info["aligned_on"] = "fiscal week number (CAL-COMPARE)"
    info["this_year_filter_without_week_53"] = sql_filter([w for w in chosen if w["fiscal_week"] != 53]) if this_year_numbers else None
    return info


# ---------------------------------------------------------------------------
# Phrase parsing
# ---------------------------------------------------------------------------

LAST_YEAR_MESSAGE = (
    "'last year' is not defined in the metric dictionary (CAL-RELATIVE defines 'last period', 'YTD' and "
    "'this year' only). Name the fiscal year, e.g. \"FY2025/26\" or \"H2 FY2025/26\", and say in the answer "
    "which year you took. The readings used in past requests are listed in fiscal-calendar/SKILL.md."
)


def resolve(weeks, phrase, as_of, loaded_to):
    text = phrase.strip().lower()
    year_label = normalise_year(text)
    rest = strip_year(text)
    done = completed_weeks(weeks, as_of)
    notes = []

    if year_label and year_label not in fiscal_years_in_order(weeks):
        raise ValueError(f"{year_label} is not in dim_date. Years loaded: {', '.join(fiscal_years_in_order(weeks))}.")

    # --- relative phrases defined in CAL-RELATIVE -------------------------------------------
    if re.fullmatch(r"(same\s+)?(time\s+)?last\s+year|ly|previous\s+year|prior\s+year", rest) and not year_label:
        raise ValueError(LAST_YEAR_MESSAGE)

    if rest in ("last period", "last completed period", "same period last year"):
        if not done:
            raise ValueError("No completed period before the as-of date.")
        # a period is complete when its last week is complete and every week of it is loaded
        for week in reversed(done):
            members = select_weeks(weeks, week["fiscal_year"], lambda w, p=week["fiscal_period"]: w["fiscal_period"] == p)
            if members[-1]["fiscal_week"] == week["fiscal_week"] and ref_weeks_in_period(week, weeks, members):
                notes.append("'Last period' = the last completed fiscal period (CAL-RELATIVE).")
                result = describe(phrase, members, as_of, loaded_to, notes)
                return result, members, rest == "same period last year"
        raise ValueError("No completed period found.")

    # "YTD as of the end of P4": week 1 to the last week of the most recent completed P4 (or of the named year)
    match = re.fullmatch(r"(?:ytd|year to date)\s+(?:as\s+of|to|through|at)\s+(?:the\s+)?end\s+of\s+(?:p|period)\s*0?(\d{1,2})", rest)
    if match:
        number = int(match.group(1))
        if not 1 <= number <= 12:
            raise ValueError("Periods run from P1 to P12 (CAL-PERIODS).")
        result, period_weeks, _ = named_unit(weeks, phrase, as_of, loaded_to, year_label,
                                             lambda w: w["fiscal_period"] == number, [], {number})
        label = period_weeks[0]["fiscal_year"]
        last_week = max(w["fiscal_week"] for w in period_weeks)
        members = select_weeks(weeks, label, lambda w: w["fiscal_week"] <= last_week)
        notes.append(f"YTD as of the end of P{number} = weeks 1 to {last_week} of {label} "
                     "(CAL-RELATIVE, CAL-PERIODS; REQ-D09 used weeks 1-17 for the end of P4).")
        if not year_label:
            notes.append(f"No year given: P{number} read as the most recent completed one, {label}. Say which year you used.")
        return describe(phrase, members, as_of, loaded_to, notes), members, False

    if rest in ("ytd", "year to date", "fiscal ytd"):
        if not done:
            raise ValueError("No completed fiscal week before the as-of date.")
        last = done[-1]
        members = select_weeks(weeks, last["fiscal_year"], lambda w: w["fiscal_week"] <= last["fiscal_week"])
        notes.append("YTD = fiscal year to date through the last completed fiscal week (CAL-RELATIVE).")
        return describe(phrase, members, as_of, loaded_to, notes), members, False

    if rest in ("this year", "current year", "this fiscal year", "current fiscal year") or (rest == "" and year_label):
        label = year_label or current_year(weeks, as_of)
        members = select_weeks(weeks, label, lambda w: True)
        if not year_label:
            notes.append("'This year' = the current fiscal year (CAL-RELATIVE).")
        weeks_in_year = max(w["weeks_in_year"] for w in members)
        return describe(phrase, members, as_of, loaded_to, notes, weeks_in_year), members, False

    if rest in ("last completed week", "last week completed", "same week last year"):
        if not done:
            raise ValueError("No completed fiscal week before the as-of date.")
        members = [done[-1]]
        if rest == "same week last year":
            notes.append("Same week last year = the same fiscal week number in the prior fiscal year (CAL-COMPARE).")
        return describe(phrase, members, as_of, loaded_to, notes), members, rest == "same week last year"

    if rest in ("current period", "this period"):
        label = current_year(weeks, as_of)
        anchor = [w for w in weeks if w["week_start"] <= as_of <= w["week_end"]] or [weeks[-1]]
        period = anchor[0]["fiscal_period"]
        members = select_weeks(weeks, anchor[0]["fiscal_year"], lambda w: w["fiscal_period"] == period)
        expected = weeks_for_periods(anchor[0]["fiscal_year"], {period}, weeks)
        return describe(phrase, members, as_of, loaded_to, notes, expected), members, False

    if rest in ("current week", "this week"):
        anchor = [w for w in weeks if w["week_start"] <= as_of <= w["week_end"]] or [weeks[-1]]
        return describe(phrase, anchor, as_of, loaded_to, notes), anchor, False

    match = re.fullmatch(r"last\s+(\d+)\s+weeks?", rest)
    if match:
        count = int(match.group(1))
        members = done[-count:]
        notes.append("The most recent completed fiscal weeks. REQ-D02 read 'last four weeks' as the last "
                      "completed period (FY2026/27 P4, which was those same four weeks).")
        return describe(phrase, members, as_of, loaded_to, notes), members, False

    # --- named units, with or without a year -------------------------------------------------
    match = re.fullmatch(r"p\s*0?(\d{1,2})\s*(?:-|to|–)\s*p?\s*0?(\d{1,2})", rest)
    if match:
        first, last = int(match.group(1)), int(match.group(2))
        if not (1 <= first <= last <= 12):
            raise ValueError("Periods run from P1 to P12 (CAL-PERIODS).")
        predicate = lambda w: first <= w["fiscal_period"] <= last
        return named_unit(weeks, phrase, as_of, loaded_to, year_label, predicate, notes, set(range(first, last + 1)))

    match = re.fullmatch(r"(?:p|period)\s*0?(\d{1,2})", rest)
    if match:
        number = int(match.group(1))
        if not 1 <= number <= 12:
            raise ValueError("Periods run from P1 to P12 (CAL-PERIODS).")
        predicate = lambda w: w["fiscal_period"] == number
        return named_unit(weeks, phrase, as_of, loaded_to, year_label, predicate, notes, {number})

    match = re.fullmatch(r"(?:q|quarter)\s*([1-4])", rest)
    if match:
        number = int(match.group(1))
        predicate = lambda w: w["fiscal_quarter"] == number
        notes.append("Q1 = P1-P3 (weeks 1-13), Q2 = P4-P6, Q3 = P7-P9, Q4 = P10-P12 (CAL-PERIODS).")
        return named_unit(weeks, phrase, as_of, loaded_to, year_label, predicate, notes,
                          set(range(3 * number - 2, 3 * number + 1)))

    if rest in ("h1", "first half"):
        notes.append("First half = P1-P6 (REQ-D13, REQ-D33).")
        return named_unit(weeks, phrase, as_of, loaded_to, year_label, lambda w: w["fiscal_period"] <= 6, notes,
                          set(range(1, 7)))

    if rest in ("h2", "second half", "back half"):
        notes.append("Second half = P7-P12 (REQ-D04, REQ-D35); REQ-D08 took weeks 27-52 for an LFL request, "
                     "since week 53 is never LFL.")
        return named_unit(weeks, phrase, as_of, loaded_to, year_label, lambda w: w["fiscal_period"] >= 7, notes,
                          set(range(7, 13)))

    match = re.fullmatch(r"(?:w|wk|week|fiscal week)\s*(\d{1,2})", rest)
    if match:
        number = int(match.group(1))
        return named_unit(weeks, phrase, as_of, loaded_to, year_label, lambda w: w["fiscal_week"] == number, notes)

    raise ValueError(
        f"Could not read '{phrase}'. Try: last period, YTD, this year, same week last year, P5, P5 FY2025/26, "
        "Q2, H2 FY2025/26, P1-P3, week 22, FY2024/25, last 4 weeks."
    )


def ref_weeks_in_period(week, weeks, members):
    """A period counts as complete when all its weeks are present and loaded (4, 4 or 5; 6 for P12 of a 53-week year)."""
    expected = expected_weeks(week["fiscal_year"], members, weeks)
    return len(members) == expected and all(m["last_loaded"] == m["week_end"] for m in members)


PERIOD_WEEKS = {1: 4, 2: 4, 3: 5, 4: 4, 5: 4, 6: 5, 7: 4, 8: 4, 9: 5, 10: 4, 11: 4, 12: 5}   # 4-4-5 (CAL-PERIODS)


def weeks_for_periods(year_label, period_numbers, weeks):
    """Weeks the given periods should have: 4-4-5 per quarter, P12 one longer in a 53-week year (CAL-WEEK53)."""
    total = sum(PERIOD_WEEKS[p] for p in period_numbers)
    weeks_in_year = max(w["weeks_in_year"] for w in weeks if w["fiscal_year"] == year_label)
    if 12 in period_numbers and weeks_in_year == 53:
        total += 1
    return total


def expected_weeks(year_label, members, weeks):
    """Number of weeks the periods present in `members` should have."""
    return weeks_for_periods(year_label, {m["fiscal_period"] for m in members}, weeks)


def named_unit(weeks, phrase, as_of, loaded_to, year_label, predicate, notes, period_numbers=None):
    """
    A period, run of periods, quarter, half (period_numbers given) or a single week (period_numbers None).
    Without a year, take the most recent occurrence that is complete as of the as-of date.
    """
    def expected_fn(label, chosen):
        if period_numbers is None:
            return 1
        return weeks_for_periods(label, period_numbers, weeks)

    label, chosen = most_recent_completed(weeks, as_of, year_label, predicate, expected_fn)
    if not chosen:
        raise ValueError(f"'{phrase}': no completed occurrence found in dim_date on or before {as_of}.")
    if not year_label:
        notes.append(f"No year given: read as the most recent completed one, {label}, as the accepted requests "
                     "did (e.g. REQ-D03, REQ-D06, REQ-D12). Say which year you used.")
    expected = expected_fn(label, chosen)
    return describe(phrase, chosen, as_of, loaded_to, notes, expected), chosen, False


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_block(title, info):
    print(f"\n{title}")
    print("-" * len(title))
    for key in ("fiscal_years", "fiscal_periods", "fiscal_weeks", "start_date", "end_date", "weeks", "days",
                "includes_week_53", "complete_as_of", "loaded_through", "aligned_on", "sql_filter",
                "this_year_filter_without_week_53", "weeks_without_comparator"):
        if key in info and info[key] not in (None, []):
            value = info[key]
            if isinstance(value, list):
                value = ", ".join(value)
            print(f"  {key:<34} {value}")
    for note in info.get("notes", []):
        print(f"  note: {note}")
    if info.get("note"):
        print(f"  note: {info['note']}")


def main():
    parser = argparse.ArgumentParser(description="Resolve a fiscal-calendar phrase to dates using dim_date.")
    parser.add_argument("db", help="path to tuomimetsa.duckdb")
    parser.add_argument("phrase", help='e.g. "last period", "Q2", "YTD", "same week last year", "P4 FY2025/26"')
    parser.add_argument("--as-of", help="date the request was received, YYYY-MM-DD (default: last loaded date)")
    parser.add_argument("--compare", action="store_true", help="also give the prior-year comparator weeks")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = parser.parse_args()

    try:
        con = duckdb.connect(args.db, read_only=True)
    except Exception as error:  # file missing, locked, not a database
        sys.exit(f"Could not open {args.db}: {error}")

    weeks = load_weeks(con)
    loaded_to = last_loaded_date(con)
    try:
        as_of = dt.date.fromisoformat(args.as_of) if args.as_of else loaded_to
    except ValueError:
        sys.exit(f"--as-of must be YYYY-MM-DD, got {args.as_of!r}")

    try:
        result, chosen, wants_compare = resolve(weeks, args.phrase, as_of, loaded_to)
    except ValueError as error:
        if args.json:
            print(json.dumps({"phrase": args.phrase, "error": str(error)}, indent=2))
        else:
            print(f"fiscal.py: {error}")
        sys.exit(2)

    result["as_of"] = as_of.isoformat()
    if args.compare or wants_compare:
        result["comparison"] = comparator(weeks, chosen, loaded_to)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return

    print(f"Phrase: {args.phrase}    as of: {as_of}    warehouse loaded through: {loaded_to}")
    print_block("Range", result)
    if "comparison" in result:
        print_block("Prior-year comparator (same fiscal week numbers)", result["comparison"])


if __name__ == "__main__":
    main()
