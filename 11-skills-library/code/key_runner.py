"""Shared by build_key.py and validate_key.py: load the question registry and evaluate every distinct question once."""
from __future__ import annotations

import json
import shutil
from contextlib import contextmanager
from pathlib import Path

import duckdb

import config as cfg
import key_eval
import key_types
import validate_world
from key_lib import World
from wh_common import log


def load_registry() -> dict:
    """Import the question modules and return {qid: builder}."""
    import key_questions_a, key_questions_b, key_questions_c   # noqa: F401  (importing registers the questions)
    return dict(key_types.REGISTRY)


def load_briefs() -> list[dict]:
    path = cfg.REQUESTS_DIR / "briefs.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; run build_requests.py briefs first.")
    return json.loads(path.read_text(encoding="utf-8"))


@contextmanager
def repaired_copy():
    """The warehouse with the four incidents undone, in a scratch folder under data/, removed afterwards."""
    scratch = cfg.DATA_DIR / "_clean_check_key" / "clean.duckdb"
    validate_world.make_clean_copy(scratch)
    connection = duckdb.connect(str(scratch), read_only=True)
    try:
        yield connection
    finally:
        connection.close()
        scratch.unlink(missing_ok=True)
        scratch.with_suffix(".duckdb.wal").unlink(missing_ok=True)
        try:
            scratch.parent.rmdir()
        except OSError:
            pass


def evaluate_all(qids: list[str] | None = None, published=None) -> tuple[dict, dict]:
    """Evaluate each distinct question once. Returns ({qid: Question}, {qid: evaluation result})."""
    registry = load_registry()
    wanted = qids or sorted(registry)
    questions = {qid: registry[qid]() for qid in wanted}
    log(f"Evaluating {len(questions)} questions (reference SQL, pandas recomputation, naive variants)")
    own_connection = published is None
    pub = published if published is not None else duckdb.connect(str(cfg.WAREHOUSE_PATH), read_only=True)
    results = {}
    try:
        with repaired_copy() as clean:
            world_clean = World("clean")
            needs_published = any(q.undocumented or any(i.published_sql for i in q.interpretations) for q in questions.values())
            world_pub = World("published") if needs_published else None
            for number, (qid, question) in enumerate(questions.items(), start=1):
                results[qid] = key_eval.evaluate(question, pub, clean, world_clean, world_pub)
                state = "ok" if results[qid]["ok"] else "FAILED"
                log(f"  [{number:2d}/{len(questions)}] {qid}: {state}")
    finally:
        if own_connection:
            pub.close()
    return questions, results
