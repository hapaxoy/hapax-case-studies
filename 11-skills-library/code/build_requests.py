"""Build the 60 test requests (Project 11, Phase 3).

  python code/build_requests.py briefs     write data/requests/briefs.json (held out: carries the question each request maps
                                           to) and three wording batches for the Sonnet wording agent
  python code/build_requests.py assemble   read the agent's wording from data/requests/wording_raw/, check every text
                                           against its brief and against the dev history, write data/requests/test_requests.json

The wording agent sees `ask` and `avoid_words` only. It never sees a trap, the key or the world. The checks in
`assemble` are what stop it adding or removing a trap: every text must contain what its brief says it must contain and
none of the words that would resolve a trap, and no text may repeat a dev-history request.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import config as cfg
import dev_requests
import test_briefs
from wh_common import log

BATCH_COUNT = 3
WORDING_INSTRUCTIONS = """You are writing the text of requests as they arrive in the request queue of the Data & Analytics team at Tuomimetsä Oy, a Finnish home-and-garden retailer. Each request comes from a named colleague in a department.

For each item you get: the requester, the department, `ask` (a plain description of what the requester wants) and `avoid_words`. Write the request as that person would type it into the queue.

Style
- Short: one to three sentences, usually under 40 words. Natural and a little informal, as typed by a busy colleague. Sometimes terse, sometimes friendly ("Hi," or "thanks" now and then, not every time).
- Let the department show: Finance is precise and number-minded, Commercial terse, Marketing friendly, Store operations practical, E-commerce brisk, Supply chain matter-of-fact.
- British spelling. No emojis, no markdown, no bullet points, no quotation marks around the whole request.

Rules (these matter more than style)
1. Keep every concrete detail in `ask`: numbers, dates, period labels, store names, product names, categories, the measure asked for, and any explicit instruction such as "as they were at the time" or "by the UTC calendar day". Period labels may be written as given (P2, Q3, FY24/25) or as "period 2", "quarter 3" and so on.
2. Add nothing that is not in `ask`. No definitions, no instructions on how to calculate, no remarks about exclusions, time zones, data problems, cancelled orders, tables or columns. Never use a word from `avoid_words` (not even inside another word).
3. Do not make the request more precise or more vague than `ask`. Where `ask` says to leave something open, leave it open.
4. Where `ask` names what the requester wants back (this year and last year side by side, growth, a split, a share), say so in your own words.
5. Different items may be the same question asked by two different people. Write every item as its own person would; do not try to match or avoid matching other items.
6. Do not read any file other than the batch file named in your task, and write nothing except the output file."""


def briefs_stage() -> int:
    cfg.REQUESTS_DIR.mkdir(parents=True, exist_ok=True)
    briefs = test_briefs.build_briefs()
    (cfg.REQUESTS_DIR / "briefs.json").write_text(json.dumps(briefs, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"wrote {len(briefs)} briefs to data/requests/briefs.json")
    batch_of: dict[str, int] = {}
    twin_batches: dict[str, int] = {}
    for index, brief in enumerate(briefs):
        candidate = index % BATCH_COUNT
        if brief["twin"] and twin_batches.get(brief["twin"]) == candidate:
            candidate = (candidate + 1) % BATCH_COUNT
        if brief["twin"]:
            twin_batches[brief["twin"]] = candidate
        batch_of[brief["id"]] = candidate
    wording_dir = cfg.REQUESTS_DIR / "wording_batches"
    wording_dir.mkdir(parents=True, exist_ok=True)
    for number in range(BATCH_COUNT):
        items = [{"id": b["id"], "requester": b["requester"], "department": b["department"], "received": b["received"],
                  "ask": b["ask"], "avoid_words": b["avoid_words"]} for b in briefs if batch_of[b["id"]] == number]
        payload = {"instructions": WORDING_INSTRUCTIONS, "output_format": 'a JSON list of {"id": ..., "request_text": ...}, one entry per item', "items": items}
        path = wording_dir / f"batch_{number + 1:02d}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        log(f"  {path.name}: {len(items)} items")
    (cfg.REQUESTS_DIR / "wording_raw").mkdir(exist_ok=True)
    return 0


def words(text: str) -> list[str]:
    return re.findall(r"[\w']+", text.lower())


def trigrams(text: str) -> set:
    tokens = words(text)
    return {tuple(tokens[i:i + 3]) for i in range(len(tokens) - 2)}


def overlap(a: str, b: str) -> float:
    ta, tb = trigrams(a), trigrams(b)
    return len(ta & tb) / max(1, min(len(ta), len(tb)))


def check_text(brief: dict, text: str) -> list[str]:
    """Problems with one wording: missing required content or a forbidden word."""
    problems = []
    lowered = text.lower()
    for group in brief["include"]:
        if not any(option.lower() in lowered for option in group):
            problems.append(f"missing one of {group}")
    for word in brief["avoid_words"]:
        if word.lower() in lowered:
            problems.append(f"contains forbidden '{word}'")
    return problems


def assemble_stage() -> int:
    briefs = json.loads((cfg.REQUESTS_DIR / "briefs.json").read_text(encoding="utf-8"))
    texts = {}
    for path in sorted((cfg.REQUESTS_DIR / "wording_raw").glob("batch_*.json")):
        for item in json.loads(path.read_text(encoding="utf-8")):
            texts[item["id"]] = item["request_text"].strip()
    missing = [b["id"] for b in briefs if b["id"] not in texts]
    if missing:
        print(f"ERROR: no wording for {missing}")
        return 1
    problems = {}
    for brief in briefs:
        found = check_text(brief, texts[brief["id"]])
        if len(words(texts[brief["id"]])) > 70:
            found.append("longer than 70 words")
        if found:
            problems[brief["id"]] = found
    dev_texts = [r["request_text"] for r in dev_requests.DEV_REQUESTS]
    for brief in briefs:
        worst = max(overlap(texts[brief["id"]], dev) for dev in dev_texts)
        if worst > cfg.DEV_NGRAM_LEAK_THRESHOLD:
            problems.setdefault(brief["id"], []).append(f"repeats a dev request ({worst:.0%} of 3-grams)")
    by_twin = {}
    for brief in briefs:
        if brief["twin"]:
            by_twin.setdefault(brief["twin"], []).append(brief["id"])
    for twin, ids in by_twin.items():
        if overlap(texts[ids[0]], texts[ids[1]]) > 0.5:
            problems.setdefault(ids[1], []).append(f"too close to its twin {ids[0]}")
    if len(set(t.lower() for t in texts.values())) != len(texts):
        problems.setdefault("ALL", []).append("duplicate texts")
    if problems:
        print("WORDING PROBLEMS:")
        for key, found in problems.items():
            print(f"  {key}: {found}   <- {texts.get(key, '')!r}")
        return 1
    output = [{"id": b["id"], "received": b["received"], "requester": b["requester"], "department": b["department"],
               "request_text": texts[b["id"]]} for b in briefs]
    (cfg.REQUESTS_DIR / "test_requests.json").write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"wrote {len(output)} requests to data/requests/test_requests.json")
    return 0


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else ""
    sys.exit({"briefs": briefs_stage, "assemble": assemble_stage}.get(stage, lambda: print(__doc__) or 1)())
