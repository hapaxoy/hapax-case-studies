"""Data shapes and small SQL/pandas builders shared by the question definitions (Project 11, Phase 3)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from key_lib import NET_EVENTS, WEB_DISPATCH


def col(name: str, role: str, unit: str = "") -> dict:
    """A result column. role: dimension (part of the row key) or measure. unit: eur | pct | count | ratio | text | date."""
    return {"name": name, "role": role, "unit": unit}


@dataclass
class Naive:
    """The plausible wrong query that falls into one planted trap."""
    trap: str                  # trap class (config.TRAP_CLASS_COUNTS key)
    label: str                 # short machine-friendly label for error attribution, e.g. "as_was_region"
    sql: str
    plain: str                 # one plain-English sentence for the review sheet: what it does wrong


@dataclass
class Interpretation:
    """One accepted reading of an ambiguous request."""
    ident: str
    label: str                 # plain English
    sql: str
    pandas_fn: Callable
    columns: list              # this reading's own result columns
    keywords: list             # list of groups; the assumptions must contain at least one word from every group
    example_pass: str          # a sentence the keyword rule must accept
    example_fail: str          # a sentence the keyword rule must reject
    # A reading that reaches the double-posted store-week (INC-1) in the published data has two accepted outcomes, as for
    # the undocumented-issue requests: the incident-free result (`sql`, de-duplicated) and the published result with a
    # caveat. Both stay None for readings the incident cannot reach.
    published_sql: str | None = None
    published_pandas_fn: Callable | None = None
    caveat_keywords: list | None = None
    caveat_pass: str | None = None
    caveat_fail: str | None = None
    tie_check_sql: str | None = None   # top-N readings: the same query with one extra row


@dataclass
class Question:
    qid: str
    pattern: int
    columns: list
    reference_sql: str
    pandas_fn: Callable
    plain: dict                # counts / leaves_out / docs / what_it_means (for the review sheet)
    naive: list = field(default_factory=list)
    ordered: bool = False      # row order matters (top-N, league table)
    interpretations: list = field(default_factory=list)   # ambiguous requests: all accepted readings (the first is primary)
    alternatives: list = field(default_factory=list)      # equally acceptable results of an unambiguous request: dicts label/sql/pandas_fn
    undocumented: dict | None = None   # {incident, published_sql, published_pandas_fn, keywords, example_pass, example_fail, what}
    invariance_sql: list = field(default_factory=list)   # clean requests: sloppy variants that must still equal the reference
    reference_world: str = "clean"   # which pandas world checks the reference ("clean" always; the reference SQL is incident-proof)
    top_n: int | None = None
    tie_check_sql: str | None = None   # top-N requests: the reference with one extra row, to prove there is no tie at the cut
    alternatives_ordered_by: dict = field(default_factory=dict)   # alternative label -> "column desc" when its row order differs


REGISTRY: dict[str, Callable[[], Question]] = {}


def question(qid: str):
    """Register a function that builds a Question."""
    def wrap(fn):
        REGISTRY[qid] = fn
        return fn
    return wrap


# ---------------------------------------------------------------------------
# SQL builder shared by the year-on-year comparisons
# ---------------------------------------------------------------------------

def yoy_sql(group_expr: str, group_out: str, ty_cond: str, ly_cond: str, joins: str = "", names=("net_sales_ty", "net_sales_ly"),
            growth: str | None = "growth_pct", events: str = NET_EVENTS, with_dispatch: bool = True, order_by: str = "1",
            where_extra: str = "", measure: str = "n.net_sales", group_extra: str = "") -> str:
    """Compare a measure between two sets of days (ty_cond / ly_cond are SQL conditions on d.* and n.business_date).

    The two sides are matched on the grouping expression with a full outer join, so a group that exists on only one
    side shows up with an empty other side.
    """
    prefix = f"WITH {WEB_DISPATCH},\n" if with_dispatch else "WITH "
    growth_sql = f",\n       ROUND(100.0 * (t.v / l.v - 1), 2) AS {growth}" if growth else ""
    return f"""{prefix}{events},
tagged AS (
    SELECT CASE WHEN {ty_cond} THEN 'ty' WHEN {ly_cond} THEN 'ly' END AS yr, {group_expr} AS grp, {measure} AS v
    FROM net_events n
    JOIN dim_date d ON d.calendar_date = n.business_date
    {joins}
    WHERE (({ty_cond}) OR ({ly_cond})) {where_extra}
),
agg AS (SELECT yr, grp, SUM(v) AS v FROM tagged GROUP BY 1, 2)
SELECT COALESCE(t.grp, l.grp) AS {group_out}, ROUND(t.v, 2) AS {names[0]}, ROUND(l.v, 2) AS {names[1]}{growth_sql}
FROM (SELECT * FROM agg WHERE yr = 'ty') t
FULL OUTER JOIN (SELECT * FROM agg WHERE yr = 'ly') l ON t.grp = l.grp
ORDER BY {order_by};"""


def yoy_frame(ty: pd.Series, ly: pd.Series, group_out: str, names=("net_sales_ty", "net_sales_ly"),
              growth: str | None = "growth_pct", divisor: float = 100.0) -> pd.DataFrame:
    """pandas twin of yoy_sql: two series (indexed by group) in cents -> comparison frame."""
    frame = pd.DataFrame({names[0]: ty / divisor, names[1]: ly / divisor})
    frame.index.name = group_out
    if growth:
        frame[growth] = 100.0 * (frame[names[0]] / frame[names[1]] - 1)
    return frame.reset_index()
