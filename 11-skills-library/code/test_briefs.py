"""The 60 test-request briefs, deterministic from config.py (Project 11, Phase 3).

A brief holds the pattern, department, what the requester wants (`ask`, plain English), words the wording must contain
(`include`: every group needs one of its words) and words it must not contain (`avoid`), plus the question it maps to
in the key (`qid`). Ten questions are asked twice by two departments in different words (paraphrase twins).

The wording agent sees `ask` and `avoid` only. It never sees the traps, the key or the world. After wording,
build_requests.py checks every text against `include` and `avoid` (so a trap cannot be added or removed in the
wording) and against the dev history (so no test request repeats one).
"""
from __future__ import annotations

import random

import config as cfg

FIN, COM, MKT, OPS, ECO, SUP = ("Finance (FP&A)", "Commercial (category management)", "Marketing and CRM", "Store operations",
                                "E-commerce", "Supply chain")

# Words that would resolve a trap if the wording used them. A brief may allow some of them through `allow`.
GLOBAL_AVOID = ["999", "training store", "zz test", "test article", "staff purchase", "cancel", "dispatch", "helsinki time", "finnish time",
                "utc", "as-is", "as is", "as-was", "as was", "restate", "week-aligned", "exclud", "legacy", "channel_code", "rpt."]

LFL = ["lfl", "like-for-like", "like for like"]


def P(n):
    """Ways to write the start of a period range."""
    return [f"p{n}", f"period {n}", f"periods {n}"]


def END(n):
    """Ways to write the end of a period range."""
    return [f"p{n}", f"period {n}", f"to {n}", f"-{n}", f"–{n}", f"and {n}", f"– {n}", f"- {n}"]


FY2425 = ["fy24/25", "fy2024/25", "2024/25", "24/25"]
LAST_YEAR = ["last year"]
BEFORE = ["year before", "prior year", "previous year", "year earlier", "the year before", "year prior"]


def b(qid, pattern, dept, ask, include, avoid=(), allow=(), twin=None):
    return dict(qid=qid, pattern=pattern, department=dept, ask=ask, include=[list(g) for g in include], avoid=list(avoid), allow=list(allow), twin=twin)


# Each entry: one request. Twins share a qid and a twin label and differ in department and wording.
BRIEF_TABLE = [
    # ---- pattern 1
    b("Q01", 1, FIN, "Net sales by region for Q3 of last year compared with Q3 the year before, with the web shop shown as its own line. Wants last year's figure, the earlier year's figure and the growth percentage for each region.",
      [["q3"], ["region"], LAST_YEAR, BEFORE, ["web", "online"]]),
    b("Q03", 1, FIN, "Total company net sales for each week of period 2 this year, with the same weeks last year next to them and the growth percentage.",
      [["p2", "period 2"], ["week"], LAST_YEAR], twin="TW01"),
    b("Q03", 1, OPS, "How the whole company's sales did in each of the four weeks of period 2 this year compared with last year, with growth.",
      [["p2", "period 2"], ["week"], LAST_YEAR], twin="TW01"),
    b("Q06", 1, FIN, "Rank the five store regions by how they are doing this year so far. Stores only, no web shop. Do not say which measure to rank by, leave 'how they are doing' open.",
      [["region"], ["rank", "order", "league", "best", "top"], ["this year", "so far", "ytd", "year to date"]], avoid=["sales", "margin", "growth", "revenue", "profit", "net", "euro", "turnover"]),
    b("A3", 1, OPS, "What the whole company's net sales were last month. Say 'last month' and nothing more precise about which dates.",
      [["sales"], ["last month"], ["company", "total", "everything", "whole", "overall"]], avoid=["p5", "period", "fiscal", "september", "calendar", "28 days", "four weeks"]),
    b("O1", 1, FIN, "For the VAT filing: gross sales including VAT, before returns, by region for August and September 2024 (one column for each month). The regions must be as they were at the time, as in the old reports.",
      [["vat"], ["gross", "incl"], ["region"], ["august"], ["september"], ["2024"], ["at the time", "as they were", "then", "old", "back then", "originally"]], allow=["as-was", "as was"]),
    # ---- pattern 2
    b("L1", 2, FIN, "Like-for-like growth for period 1 this year.",
      [LFL, ["p1", "period 1"], ["this year"]], avoid=["refit", "closed", "savonlinna", "open", "52", "weeks"]),
    b("L3", 2, FIN, "Like-for-like growth by region for Q3 last year.",
      [LFL, ["region"], ["q3"], LAST_YEAR], avoid=["refit", "closed", "open", "52", "weeks", "web"]),
    b("L5", 2, FIN, "Like-for-like growth for period 4 this year.",
      [LFL, ["p4", "period 4"], ["this year"]], avoid=["refit", "closed", "open", "52", "weeks", "web"], twin="TW02"),
    b("L5", 2, OPS, "How the stores did like for like in period 4 this year against last year.",
      [LFL, ["p4", "period 4"], ["this year"]], avoid=["refit", "closed", "open", "52", "weeks", "web"], twin="TW02"),
    # ---- pattern 3
    b("C1", 3, COM, "Net sales and gross margin percentage for the Garden and Electrical categories for period 6 last year.",
      [["garden"], ["electrical"], ["margin"], ["p6", "period 6"], LAST_YEAR], avoid=["outdoor", "lighting", "category change", "moved"]),
    b("C2", 3, COM, "Net sales for Garden and Electrical in period 8 last year compared with period 8 the year before, with growth.",
      [["garden"], ["electrical"], ["p8", "period 8"], LAST_YEAR, BEFORE], avoid=["outdoor", "lighting", "moved"]),
    b("C4", 3, COM, "Garden net sales for each period of the second half (P7 to P12) of FY24/25, with Garden as it was reported at the time (the old category set-up). Say that you want it the old way.",
      [["garden"], ["p7", "period 7"], ["p12", "period 12"], FY2425, ["at the time", "as it was", "back then", "old", "then", "originally"]], avoid=["lighting"], allow=["as-was", "as was"]),
    b("C1X", 3, COM, "How many units of Interior Paint the Lahti store sold in period 3 this year.",
      [["interior paint"], ["lahti"], ["p3", "period 3"], ["unit"]], twin="TW03"),
    b("C1X", 3, SUP, "Units of Interior Paint sold in the Lahti store in period 3 of FY26/27.",
      [["interior paint"], ["lahti"], ["p3", "period 3"], ["unit"]], twin="TW03"),
    b("C3", 3, OPS, "How many units of SKU 101624 Oulu Kaakkuri sold last week.",
      [["101624"], ["kaakkuri"], ["last week"], ["unit"]]),
    b("C13", 3, OPS, "Units sold of Cleaning Products at Hyvinkää in period 5 this year.",
      [["cleaning"], ["hyvink"], ["p5", "period 5"], ["unit"]]),
    # ---- pattern 4
    b("R4b", 4, COM, "Return rate by Garden subcategory for the goods sold in Q1 of last year.",
      [["return rate"], ["garden"], ["subcategor", "sub-categor"], ["q1"], LAST_YEAR], avoid=["cohort", "sale week", "sale-week", "refund date", "outdoor", "lighting"]),
    b("R4c", 4, COM, "Return rate by store format for goods sold in period 2 last year.",
      [["format"], ["p2", "period 2"], LAST_YEAR], avoid=["cohort", "sale week", "sale-week", "refund date"], twin="TW04"),
    b("R4c", 4, OPS, "What share of what was sold in period 2 last year came back, split by store format.",
      [["format"], ["p2", "period 2"], LAST_YEAR], avoid=["cohort", "sale week", "sale-week", "refund date"], twin="TW04"),
    b("C12", 4, COM, "How many units of Garden Furniture were returned (handed back and booked as returned) during period 4 this year.",
      [["garden furniture"], ["return"], ["p4", "period 4"], ["unit"]]),
    # ---- pattern 5
    b("W1", 5, ECO, "How many web orders were placed on Cyber Monday 2025 (1 December 2025).",
      [["cyber monday"], ["order"], ["2025"]], avoid=["midnight", "time zone", "timezone"], twin="TW05"),
    b("W1", 5, FIN, "Number of web shop orders on Cyber Monday, 1 December 2025.",
      [["cyber monday"], ["order"], ["2025"]], avoid=["midnight", "time zone", "timezone"], twin="TW05"),
    b("W2", 5, ECO, "Daily web sales (net) for each day from 15 to 23 December 2025.",
      [["web"], ["15"], ["23"], ["december"], ["daily", "each day", "per day", "day by day", "by day"]], avoid=["midnight", "time zone", "timezone", "order date"]),
    b("O2", 5, ECO, "How many web orders were placed on Black Friday 2025 (28 November), counted by the UTC calendar day, because the carrier's report is in UTC. Ask for UTC explicitly.",
      [["black friday"], ["order"], ["utc"]], allow=["utc"]),
    b("W4", 5, ECO, "Web net sales by period for periods 5 to 8 of last year.",
      [["web"], P(5), END(8), LAST_YEAR], avoid=["migration", "platform", "channel", "fulfil"], twin="TW06"),
    b("W4", 5, FIN, "What the web shop sold in each of periods 5 to 8 last year, net.",
      [["web"], P(5), END(8), LAST_YEAR], avoid=["migration", "platform", "channel", "fulfil"], twin="TW06"),
    # ---- pattern 6
    b("K1", 6, ECO, "How big click-and-collect was as a share of the web shop's sales in each of periods 6 to 8 last year.",
      [["click"], ["share"], P(6), END(8), LAST_YEAR], avoid=["migration", "platform", "channel", "fulfil"]),
    b("K2", 6, ECO, "The click-and-collect share of web sales for each of periods 9 and 10 last year, as a percentage.",
      [["click"], ["share"], P(9), END(10), LAST_YEAR], avoid=["migration", "platform", "channel", "fulfil", "wrong", "error", "glitch", "incorrect"]),
    # ---- pattern 7
    b("AT", 7, OPS, "Average transaction value (ATV) by store format for period 4 this year.",
      [["format"], ["p4", "period 4"], ["this year"], ["atv", "average transaction", "transaction value"]], avoid=["web", "online"], twin="TW07"),
    b("AT", 7, FIN, "Average basket value (the average transaction value) by store format for period 4 of FY26/27.",
      [["format"], ["p4", "period 4"], ["basket", "atv", "average transaction", "transaction value", "average receipt", "average sale"]], avoid=["web", "online"], twin="TW07"),
    b("A2", 7, OPS, "ATV for the whole company for periods 1 to 3 this year, with the web orders included in it.",
      [["atv", "average transaction", "transaction value"], ["web"], P(1), END(3), ["included", "include", "including", "with", "in it", "in the"]]),
    # ---- pattern 8
    b("M1", 8, MKT, "Active members by tier as of the end of period 8 last year.",
      [["active"], ["tier"], ["p8", "period 8"], LAST_YEAR]),
    b("M2", 8, MKT, "How many customers do we have in Tampere. Say 'customers' and leave the meaning open.",
      [["customer"], ["tampere"]], avoid=["member", "loyalty", "active", "home store", "bought", "shopped", "year"]),
    b("U2", 8, MKT, "The share of web sales that came from loyalty members, by period, for periods 9 to 11 last year.",
      [["web"], ["member"], ["share", "%", "percent"], P(9), END(11), LAST_YEAR], avoid=["missing", "incident", "null", "problem"]),
    b("G4", 8, MKT, "How many members are on the Gold tier right now.",
      [["gold"], ["member"], ["now", "today", "current", "at the moment", "right now"]], avoid=["active"], twin="TW08"),
    b("G4", 8, OPS, "Number of Gold-tier loyalty members at the moment.",
      [["gold"], ["member"], ["now", "today", "current", "at the moment", "right now"]], avoid=["active"], twin="TW08"),
    # ---- pattern 9
    b("U9a", 9, MKT, "The uplift of the Black Week 2025 campaign against its holdout group: average spend per targeted member, average spend per held-out member, and the uplift in euros.",
      [["uplift"], ["black week"], ["2025"], ["holdout", "hold-out", "held out", "held-out", "control"]]),
    b("U9b", 9, MKT, "How many members were contacted for the Spring Garden Launch 2026 mailing, and how much those members spent between 4 and 24 May 2026.",
      [["spring garden launch"], ["2026"], ["24 may", "may 24"], ["spend", "spent", "sales"]], avoid=["holdout", "uplift", "fan", "duplicate"]),
    b("C6", 9, MKT, "How many members were held out of the Black Week 2025 mailing.",
      [["black week"], ["held out", "hold", "holdout", "hold-out", "control", "held back"], ["member"]]),
    # ---- pattern 10
    b("S1", 10, SUP, "Average stock of Paint & Decorating in period 3 this year, as a value at cost in euros, for the whole chain.",
      [["stock"], ["paint"], ["p3", "period 3"], ["average"], ["this year"]], avoid=["snapshot", "never add", "sum of"]),
    b("S2", 10, SUP, "Weeks of cover by category at the end of last period.",
      [["cover"], ["category"], ["last period", "p5", "period 5"]], avoid=["four weeks", "4 weeks", "snapshot"]),
    b("U3", 10, SUP, "Average stock value in the West region for period 11 last year, by category.",
      [["stock"], ["west"], ["p11", "period 11"], ["category"], LAST_YEAR, ["average"]], avoid=["duplicate", "double", "twice", "problem"]),
    b("C7", 10, SUP, "How many units of SKU 100011 Jyväskylä Palokka had in stock at the end of last week.",
      [["100011"], ["palokka"], ["stock"], ["last week"]]),
    # ---- pattern 11
    b("T1", 11, COM, "The top 10 products by gross margin in the South region in Q4 of FY24/25.",
      [["top 10", "ten"], ["margin"], ["south"], ["q4"], FY2425], avoid=["kouvola", "capital"]),
    b("T2", 11, COM, "What our best-selling products were last period. Ask for the top 10. Do not say what 'best-selling' is measured by.",
      [["best-selling", "best selling", "best sellers", "bestsellers", "top sellers", "best-sellers", "bestselling"], ["last period", "p5", "period 5"], ["10", "ten"]],
      avoid=["units", "net sales", "revenue", "margin", "value", "euro", "sold the most"]),
    b("T5", 11, ECO, "The top 10 products by web sales since the platform migration on 3 November 2025.",
      [["top 10", "ten"], ["web"], ["migration"], ["since"]], avoid=["legacy", "channel"]),
    b("C8", 11, OPS, "The top 3 products by units sold at Helsinki Pitäjänmäki in period 5 this year.",
      [["pitäjänmäki", "pitajanmaki"], ["p5", "period 5"], ["unit", "sold"], ["3", "three"]], twin="TW09"),
    b("C8", 11, COM, "Which three products sold the most units at the Pitäjänmäki store in period 5 of FY26/27.",
      [["pitäjänmäki", "pitajanmaki"], ["p5", "period 5"], ["unit", "sold"], ["3", "three"]], twin="TW09"),
    b("C14", 11, OPS, "The top 3 subcategories by units sold at Nokia in period 5 this year.",
      [["nokia"], ["subcategor"], ["p5", "period 5"], ["unit"]]),
    # ---- pattern 12
    b("G1", 12, OPS, "The store league table for period 5 last year.",
      [["league", "rank"], ["p5", "period 5"], LAST_YEAR]),
    b("G3", 12, OPS, "The store league table for period 2 this year.",
      [["league", "rank"], ["p2", "period 2"], ["this year"]], avoid=["per day", "trading", "open"], twin="TW10"),
    b("G3", 12, FIN, "The store ranking for period 2 this year.",
      [["rank", "league"], ["p2", "period 2"], ["this year"]], avoid=["per day", "trading", "open"], twin="TW10"),
    b("G2", 12, OPS, "Which are our 10 biggest stores. Do not say what 'biggest' is measured by or the period.",
      [["biggest", "largest"], ["store"], ["10", "ten"]], avoid=["sales", "sqm", "square", "area", "size", "revenue", "year", "metric", "m2"]),
    # ---- pattern 13
    b("N1", 13, MKT, "How many new members each store signed up last year, with online sign-ups too.",
      [["new member", "signed up", "sign-up", "sign up", "sign-ups", "joined"], ["each store", "by store", "per store", "every store"], LAST_YEAR]),
    b("C10", 13, MKT, "How many members joined on 3 October 2026.",
      [["3 october", "october 3", "3 oct"], ["member"]]),
    b("C11", 13, MKT, "How many new members signed up on 25 September 2026.",
      [["25 september", "september 25", "25 sep"], ["member"]]),
    # ---- pattern 14
    b("V1", 14, FIN, "Store sales including VAT for August and September 2024, before returns, as one figure for each month.",
      [["vat"], ["august"], ["september"], ["2024"], ["store"]], avoid=["rate", "24%", "25.5", "flat"]),
    b("V2", 14, FIN, "How much VAT we charged in the stores in period 5 of FY24/25, split by VAT rate.",
      [["vat"], ["rate"], ["p5", "period 5"], FY2425, ["store"]], avoid=["25.5", "24%", "change", "september", "august"]),
    b("V3", 14, FIN, "Web sales including VAT by period for Q2 of FY24/25 (periods 4 to 6), before returns.",
      [["web"], ["vat"], P(4), END(6), FY2425], avoid=["rate", "25.5", "24%", "change"]),
]


def build_briefs() -> list[dict]:
    """Assign request IDs, requesters and received dates deterministically. Twins end up far apart in the queue."""
    rng = random.Random(cfg.RANDOM_SEED + 3)
    entries = [dict(entry) for entry in BRIEF_TABLE]
    for _ in range(200):                       # shuffle until twins are at least 12 places apart (deterministic)
        rng.shuffle(entries)
        positions = {}
        for index, entry in enumerate(entries):
            if entry["twin"]:
                positions.setdefault(entry["twin"], []).append(index)
        if all(abs(a - b_) >= 12 for a, b_ in positions.values()):
            break
    else:
        raise RuntimeError("could not space the twin pairs")
    briefs = []
    for index, entry in enumerate(entries, start=1):
        pool = cfg.DEPARTMENT_REQUESTERS[entry["department"]]
        received = cfg.TEST_RECEIVED_DATES[min((index - 1) * len(cfg.TEST_RECEIVED_DATES) // len(entries), len(cfg.TEST_RECEIVED_DATES) - 1)]
        brief = dict(entry)
        brief.update({"id": f"REQ-T{index:02d}", "requester": pool[rng.randrange(len(pool))], "received": received.isoformat()})
        brief["avoid_words"] = [w for w in GLOBAL_AVOID if w not in entry["allow"]] + entry["avoid"]
        briefs.append(brief)
    return briefs


if __name__ == "__main__":
    for item in build_briefs()[:6]:
        print(item["id"], item["qid"], item["department"], item["requester"], item["received"])
