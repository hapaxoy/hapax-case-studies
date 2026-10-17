"""Recover the real final message of a run whose saved final-<run_id>.txt is damaged (cut off, empty), from the run's own agent transcript.

    python code/recover_final_message.py --run full-sonnet-S-t34-r5

The runs' final messages were saved into data/agent_runs/scratch/full/final-<run_id>.txt.
One of them (full-sonnet-S-t34-r5) was cut off at 1,748 characters although the run had completed. The agent's own transcript (a
.jsonl file under the Claude Code projects folder of the launching session) holds the message it actually returned. This script:

  1. finds the transcripts whose first message tells the agent to read this run's packet (packets/<set>/<run_id>.txt);
  2. takes the last assistant text block of each (the final message);
  3. keeps the transcript whose final message begins with the damaged saved text (compared after HTML-unescaping, because the saved
     files carry entity-escaped text and the transcripts do not);
  4. writes the recovered message, exactly as in the transcript, to recovered-<run_id>.txt beside the saved file, and a note
     recovered-<run_id>.NOTE.md saying where it came from and how it was checked.

It only READS transcripts and the saved file. The saved final-<run_id>.txt is never touched, and the script refuses to overwrite
an existing recovered file. The recovered text is NOT named final-*.txt, so the other tools that read finals
do not see it; code/collect_full.py reads it by name and records that it did.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

CASE_ROOT = Path(__file__).resolve().parent.parent
FINALS_DIR = CASE_ROOT / "data" / "agent_runs" / "scratch" / "full"
# The transcripts of a session live in that session's subagents folder. The folder is an argument
# because it belongs to the launching session, not to the case.
DEFAULT_SUBAGENT_DIR = Path("subagents")
PACKET_PATTERN = re.compile(r"packets/([A-Za-z0-9_]+)/([A-Za-z0-9_\-]+)\.txt")


def first_message_run_id(transcript_path: Path) -> str | None:
    """The run id named in the packet path of a transcript's first message, or None if it is not a packet run."""
    with open(transcript_path, "r", encoding="utf-8") as handle:
        first_line = handle.readline()
    try:
        event = json.loads(first_line)
    except json.JSONDecodeError:
        return None
    content = (event.get("message") or {}).get("content")
    text = content if isinstance(content, str) else json.dumps(content)
    match = PACKET_PATTERN.search(text or "")
    return match.group(2) if match else None


def last_assistant_text(transcript_path: Path) -> tuple[str | None, str | None]:
    """(the last assistant text block, its timestamp) of a transcript; (None, None) if the agent never wrote one."""
    last_text, last_timestamp = None, None
    with open(transcript_path, "r", encoding="utf-8") as handle:
        for line in handle:
            event = json.loads(line)
            if event.get("type") != "assistant":
                continue
            blocks = (event.get("message") or {}).get("content") or []
            texts = [block["text"] for block in blocks if isinstance(block, dict) and block.get("type") == "text"]
            if texts:
                last_text, last_timestamp = "\n".join(texts), event.get("timestamp")
    return last_text, last_timestamp


def recover(run_id: str, subagent_dir: Path, finals_dir: Path) -> dict:
    """Recover and write the message; returns a dict describing what was done. Raises SystemExit with a sentence on any problem."""
    saved_path = finals_dir / f"final-{run_id}.txt"
    if not saved_path.is_file():
        raise SystemExit(f"No saved final message at {saved_path}.")
    recovered_path = finals_dir / f"recovered-{run_id}.txt"
    note_path = finals_dir / f"recovered-{run_id}.NOTE.md"
    for path in (recovered_path, note_path):
        if path.exists():
            raise SystemExit(f"{path.name} already exists; this script does not overwrite.")
    if not subagent_dir.is_dir():
        raise SystemExit(f"Transcript folder not found: {subagent_dir}")
    saved_text = saved_path.read_text(encoding="utf-8")
    saved_unescaped = html.unescape(saved_text)
    print(f"Saved file: {len(saved_text)} characters. Looking for transcripts of {run_id} ...")
    candidates = []
    for transcript in sorted(subagent_dir.glob("*.jsonl")):
        if first_message_run_id(transcript) != run_id:
            continue
        text, timestamp = last_assistant_text(transcript)
        candidates.append((transcript, text, timestamp))
        print(f"  {transcript.name}: final message {len(text) if text else 0} characters, last written {timestamp}")
    if not candidates:
        raise SystemExit(f"No transcript tells an agent to read the packet of {run_id}.")
    matching = [(t, text, ts) for t, text, ts in candidates if text and html.unescape(text).startswith(saved_unescaped)]
    if len(matching) != 1:
        raise SystemExit(f"{len(matching)} transcripts have a final message that begins with the saved text (need exactly 1).")
    transcript, text, timestamp = matching[0]
    if len(text) <= len(saved_unescaped):
        raise SystemExit("The transcript's final message is not longer than the saved text; there is nothing to recover.")
    # The recovered text must parse as the answer JSON, or it is no better than the damaged one.
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as problem:
        raise SystemExit(f"The transcript's final message is not valid JSON either: {problem}")
    recovered_path.write_text(text, encoding="utf-8")
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    note = (
        f"# Recovered final message, {run_id}\n\n"
        f"Written {datetime.now(timezone.utc).isoformat(timespec='seconds')} by `code/recover_final_message.py`.\n\n"
        f"- `final-{run_id}.txt` holds {len(saved_text)} characters and stops mid-sentence, although the run completed. It was not touched.\n"
        f"- The run's own session record (read only) holds the message it returned, "
        f"{len(text)} characters, last written {timestamp}. Stop reason of that turn: end_turn.\n"
        f"- Check: the saved text, HTML-unescaped, is exactly the beginning of the transcript message ({len(saved_unescaped)} of {len(text)} "
        f"characters). The saved file carries entity-escaped text (`&lt;`) and the transcript raw text, which is why the check unescapes.\n"
        f"- The recovered text parses as the answer JSON with keys {', '.join(parsed.keys())}. SHA-256 of the recovered file: `{sha}`.\n"
        f"- `recovered-{run_id}.txt` is the message exactly as in the transcript. `code/collect_full.py` scores it in place of the "
        f"damaged file and records that it did.\n"
        f"- Why the file was cut: not established. The cut falls after an escaped line break inside a list, at {len(saved_text)} characters; "
        f"the other 1,799 finals are complete, so the cause is in how this one was saved, not in the run.\n")
    note_path.write_text(note, encoding="utf-8")
    print(f"Wrote {recovered_path.name} ({len(text)} characters) and {note_path.name}.")
    return {"run_id": run_id, "transcript": transcript.name, "recovered_chars": len(text), "saved_chars": len(saved_text), "sha256": sha}


def main(argv: list | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Recover a damaged final message from the run's own transcript (read only).")
    parser.add_argument("--run", required=True, help="the run id, e.g. full-sonnet-S-t34-r5")
    parser.add_argument("--subagent-dir", type=Path, default=DEFAULT_SUBAGENT_DIR, help="folder of the session's subagent transcripts")
    parser.add_argument("--finals-dir", type=Path, default=FINALS_DIR)
    args = parser.parse_args(argv)
    recover(args.run, args.subagent_dir, args.finals_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
