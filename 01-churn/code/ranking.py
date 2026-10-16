"""
ranking.py -- the one place the case decides how a ranked list is ordered and cut.

Why this file exists (method clarification recorded 6 Oct 2026): the ticket-text agent's account score has only 33 distinct
values, so the top-100 cut fell inside a tie (23 accounts at 0.55 occupy ranks
95-117). The old code broke ties by row order (a stable sort on accounts.csv
order), which is arbitrary: it depends on nothing but how the data happens to be
laid out. Every top-N in the case is now cut by an explicit rule instead.

THE RULE (applied wherever a list is cut: top-50, top-100, ranks, 2x2 regions):

    Text arm      : score descending, then most recent ticket date descending
                    (a more recent concern outranks an older one at equal
                    score), then account_id ascending.
    Combined arm  : the same rule. The combined arm already reads ticket data,
                    so recency is a legitimate tie-break there.
    Usage arm     : score descending, then account_id ascending. Recency is
                    deliberately NOT used here, so the usage arm never sees a
                    ticket field and the arms stay independent. (Usage and
                    combined scores are continuous, so this clause never fires
                    at either published cut; it is stated so the rule holds if
                    the data ever changes.)

The recency tie-break stays inside the text layer: it uses only ticket dates, no
usage or answer-key information, so the text arm remains independent of the
usage arm. account_id ascending makes the order fully deterministic.

Accounts with no tickets would have no recency; they sort after dated accounts
at equal score (NaT last). All 500 accounts currently have tickets.
"""

import numpy as np
import pandas as pd

# The three arms, so call sites name the arm rather than re-stating the rule.
ARM_USAGE = "usage"
ARM_TEXT = "text"
ARM_COMBINED = "combined"

RULE_TEXT = (
    "score descending; ties broken by most recent ticket date descending "
    "(usage arm: omitted, to keep it free of ticket data), then account_id ascending"
)


def ranked_order(account_ids, scores, last_ticket_dates=None, arm=ARM_TEXT):
    """
    Return the positional indices (into the inputs) in rank order, best first.

    account_ids       : array of account ids (ascending id is the final tie-break).
    scores            : array of scores, higher = riskier.
    last_ticket_dates : array of most recent ticket date per account (anything
                        sortable; ISO strings or datetimes). Required for the
                        text and combined arms, ignored for the usage arm.
    arm               : ARM_USAGE, ARM_TEXT or ARM_COMBINED.
    """
    frame = pd.DataFrame({
        "position": np.arange(len(account_ids)),
        "account_id": np.asarray(account_ids),
        "score": np.asarray(scores, dtype=float),
    })
    sort_columns = ["score"]
    sort_ascending = [False]

    if arm in (ARM_TEXT, ARM_COMBINED):
        if last_ticket_dates is None:
            raise ValueError(f"The {arm} arm's tie-break needs last_ticket_dates.")
        frame["recency"] = pd.to_datetime(pd.Series(np.asarray(last_ticket_dates)))
        sort_columns.append("recency")
        sort_ascending.append(False)
    elif arm != ARM_USAGE:
        raise ValueError(f"Unknown arm {arm!r}.")

    sort_columns.append("account_id")
    sort_ascending.append(True)

    # na_position="last" keeps undated accounts below dated ones at equal score.
    ordered = frame.sort_values(sort_columns, ascending=sort_ascending, na_position="last", kind="mergesort")
    return ordered["position"].to_numpy()


def top_k_flags_ranked(account_ids, scores, k, last_ticket_dates=None, arm=ARM_TEXT):
    """Boolean array (aligned to the inputs) flagging the top-k accounts under the rule."""
    order = ranked_order(account_ids, scores, last_ticket_dates, arm)
    flags = np.zeros(len(order), dtype=bool)
    flags[order[:k]] = True
    return flags


def rank_numbers(account_ids, scores, last_ticket_dates=None, arm=ARM_TEXT):
    """1-based rank per account (aligned to the inputs) under the rule. No ties by construction."""
    order = ranked_order(account_ids, scores, last_ticket_dates, arm)
    ranks = np.empty(len(order), dtype=int)
    ranks[order] = np.arange(1, len(order) + 1)
    return ranks


def last_ticket_date_by_account(tickets_frame):
    """Most recent ticket created_at per account_id, as a Series indexed by account_id."""
    dates = pd.to_datetime(tickets_frame["created_at"])
    return dates.groupby(tickets_frame["account_id"]).max()
