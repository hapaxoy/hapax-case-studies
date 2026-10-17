"""Run a Question's queries and checks (Project 11, Phase 3).

`evaluate()` is used by build_key.py (to build the key) and by validate_data.py (to re-prove rules 12-15 from scratch).
It runs each reference SQL on the published warehouse and on the repaired copy, recomputes it in pandas from the
generator's own tables, runs every naive variant, and reports what happened. It writes nothing.
"""
from __future__ import annotations

import time
import traceback

import pandas as pd

import config as cfg
from key_lib import compare_tables, frame_to_rows
from key_types import Question


def run_sql(connection, sql: str) -> pd.DataFrame:
    return connection.execute(sql).df()


def _norm(frame: pd.DataFrame, columns: list) -> pd.DataFrame:
    """Round-trip a frame so SQL and pandas results compare on equal terms (column order from the spec)."""
    names = [c["name"] for c in columns]
    return frame[names].reset_index(drop=True)


def _same_order(left: pd.DataFrame, right: pd.DataFrame, columns: list) -> bool:
    dims = [c["name"] for c in columns if c["role"] == "dimension"]
    if not dims:
        return True
    left_keys = [tuple(str(v) for v in row) for row in left[dims].itertuples(index=False, name=None)]
    right_keys = [tuple(str(v) for v in row) for row in right[dims].itertuples(index=False, name=None)]
    return left_keys == right_keys


def check_pair(label: str, sql: str, pandas_fn, columns: list, pub, clean, world_clean, ordered: bool, expect_clean_equal: bool,
               outcomes: list) -> dict:
    """Reference-style check for one SQL/pandas pair. Returns {frame, ok}."""
    started = time.time()
    frame_pub = _norm(run_sql(pub, sql), columns)
    frame_pd = _norm(pandas_fn(world_clean), columns)
    ok, why = compare_tables(frame_pub, frame_pd, columns)
    outcomes.append({"check": f"{label}: SQL on warehouse equals pandas recomputation", "ok": ok, "detail": why})
    if ordered:
        outcomes.append({"check": f"{label}: row order agrees between SQL and pandas", "ok": _same_order(frame_pub, frame_pd, columns), "detail": ""})
    outcomes.append({"check": f"{label}: non-empty", "ok": len(frame_pub) > 0, "detail": f"{len(frame_pub)} rows"})
    if expect_clean_equal:
        frame_clean = _norm(run_sql(clean, sql), columns)
        ok2, why2 = compare_tables(frame_pub, frame_clean, columns)
        outcomes.append({"check": f"{label}: same on the repaired (incident-free) warehouse", "ok": ok2, "detail": why2})
    outcomes[-1]["seconds"] = round(time.time() - started, 1)
    return {"frame": frame_pub, "ok": ok}


def evaluate(question: Question, pub, clean, world_clean, world_pub=None) -> dict:
    """All checks for one question. Never raises: an exception becomes a failed outcome."""
    outcomes: list[dict] = []
    result: dict = {"qid": question.qid, "outcomes": outcomes}
    try:
        undocumented = question.undocumented is not None
        reference = check_pair("reference", question.reference_sql, question.pandas_fn, question.columns, pub, clean, world_clean,
                               question.ordered, expect_clean_equal=True, outcomes=outcomes)
        result["reference_frame"] = reference["frame"]

        # The cut must be clean: the last row of the list differs in value from the first row left out. Equal values inside the
        # list are allowed (their order is arbitrary); they are reported so the marker can treat those rows as interchangeable.
        tie_checks = [("", "top-N has no tie at the cut", question.tie_check_sql, question.columns)]
        tie_checks += [(i.ident, f"top-N reading {i.ident} has no tie at the cut", i.tie_check_sql, i.columns) for i in question.interpretations]
        result["ties_inside_list"] = {}
        for tie_ident, tie_label, tie_sql, tie_columns in tie_checks:
            if tie_sql:
                tie_frame = run_sql(pub, tie_sql)
                measure = [c["name"] for c in tie_columns if c["role"] == "measure"][-1]
                values = list(tie_frame[measure])
                result["ties_inside_list"][tie_ident] = len(values[:-1]) != len(set(values[:-1]))
                outcomes.append({"check": tie_label, "ok": len(values) >= 2 and values[-2] != values[-1],
                                 "detail": f"values {values[:4]}...{values[-3:]}" + ("; equal values inside the list" if result["ties_inside_list"][tie_ident] else "")})
        result["interpretations"] = []
        for interp in question.interpretations:
            checked = check_pair(f"interpretation {interp.ident}", interp.sql, interp.pandas_fn, interp.columns, pub, clean, world_clean,
                                 question.ordered, expect_clean_equal=True, outcomes=outcomes)
            found = {"ident": interp.ident, "frame": checked["frame"], "published_frame": None}
            if interp.published_sql:
                # The reading reaches the double-posted week: the published result is a second accepted outcome (with a caveat).
                published = check_pair(f"interpretation {interp.ident} published number", interp.published_sql, interp.published_pandas_fn,
                                       interp.columns, pub, clean, world_pub, question.ordered, expect_clean_equal=False, outcomes=outcomes)
                found["published_frame"] = published["frame"]
                same, _ = compare_tables(published["frame"], checked["frame"], interp.columns, factor=cfg.TRAP_BITE_FACTOR)
                found["published_differs"] = not same
            result["interpretations"].append(found)
        if question.interpretations:
            frames = [i["frame"] for i in result["interpretations"]]
            distinct = []
            for index, frame in enumerate(frames):
                differs_from_all = True
                for other_index in range(index):
                    same, _ = compare_tables(frame, frames[other_index], question.interpretations[index].columns) \
                        if [c["name"] for c in question.interpretations[index].columns] == [c["name"] for c in question.interpretations[other_index].columns] \
                        else (False, "different columns")
                    if same:
                        differs_from_all = False
                distinct.append(differs_from_all)
            outcomes.append({"check": "ambiguous: every accepted reading gives a different result", "ok": all(distinct), "detail": str(distinct)})

        result["alternatives"] = []
        for alt in question.alternatives:
            checked = check_pair(f"alternative '{alt['label']}'", alt["sql"], alt["pandas_fn"], question.columns, pub, clean, world_clean,
                                 question.ordered, expect_clean_equal=True, outcomes=outcomes)
            result["alternatives"].append({"label": alt["label"], "frame": checked["frame"]})

        if undocumented:
            spec = question.undocumented
            checked = check_pair("published number", spec["published_sql"], spec["published_pandas_fn"], question.columns, pub, clean,
                                 world_pub, question.ordered, expect_clean_equal=False, outcomes=outcomes)
            result["published_frame"] = checked["frame"]
            same, why = compare_tables(checked["frame"], reference["frame"], question.columns, factor=cfg.TRAP_BITE_FACTOR)
            outcomes.append({"check": "published number differs from the incident-free number beyond 10x tolerance", "ok": not same, "detail": why})

        result["naive"] = []
        accepted = [reference["frame"]] + [i["frame"] for i in result["interpretations"]] + [a["frame"] for a in result["alternatives"]]
        accepted_columns = [question.columns] + [i.columns for i in question.interpretations] + [question.columns] * len(result["alternatives"])
        for interp, found in zip(question.interpretations, result["interpretations"]):
            if found["published_frame"] is not None:
                accepted.append(found["published_frame"])
                accepted_columns.append(interp.columns)
        for naive in question.naive:
            try:
                frame = run_sql(pub, naive.sql)
                if list(frame.columns) != [c["name"] for c in question.columns]:
                    raise ValueError(f"naive columns {list(frame.columns)} differ from the key's {[c['name'] for c in question.columns]}")
                frame = _norm(frame, question.columns)
                bites = True
                why = []
                for cand, cols in zip(accepted, accepted_columns):
                    if [c["name"] for c in cols] != [c["name"] for c in question.columns]:
                        continue
                    same, reason = compare_tables(frame, cand, cols, factor=cfg.TRAP_BITE_FACTOR)
                    if same:
                        bites = False
                    why.append(reason)
                if bites and question.ordered:
                    pass
                outcomes.append({"check": f"naive '{naive.label}' ({naive.trap}) differs from every accepted result beyond 10x tolerance",
                                 "ok": bites, "detail": "; ".join(why)[:200]})
                result["naive"].append({"label": naive.label, "trap": naive.trap, "frame": frame, "bites": bites})
            except Exception as error:   # a broken naive query is a bug in the key
                outcomes.append({"check": f"naive '{naive.label}' runs", "ok": False, "detail": str(error)[:300]})
                result["naive"].append({"label": naive.label, "trap": naive.trap, "frame": None, "bites": False})

        # Clean requests carry no naive variants; their sloppy variants must give the reference result.
        for index, sql in enumerate(question.invariance_sql, start=1):
            frame = _norm(run_sql(pub, sql), question.columns)
            same, why = compare_tables(frame, reference["frame"], question.columns)
            outcomes.append({"check": f"clean: sloppy variant {index} gives the reference result", "ok": same, "detail": why})
    except Exception as error:
        outcomes.append({"check": "question evaluates without error", "ok": False, "detail": f"{type(error).__name__}: {error}\n{traceback.format_exc()[-600:]}"})
    result["ok"] = all(o["ok"] for o in outcomes)
    return result
