# Recovered final message, full-sonnet-S-t34-r5

Written 2026-10-15T20:07:13+00:00 by `code/recover_final_message.py`.

- `final-full-sonnet-S-t34-r5.txt` holds 1748 characters and stops mid-sentence, although the run completed. It was not touched.
- The run's own session record (read only) holds the message it returned, 5718 characters, last written 2026-10-15T19:52:59.176Z. Stop reason of that turn: end_turn.
- Check: the saved text, HTML-unescaped, is exactly the beginning of the transcript message (1736 of 5718 characters). The saved file carries entity-escaped text (`&lt;`) and the transcript raw text, which is why the check unescapes.
- The recovered text parses as the answer JSON with keys sql, result, definitions_applied, assumptions, caveats. SHA-256 of the recovered file: `eec3ebe30d85e718b43848732fffa46c6ca099eb869b0ec414011a1f6dde894a`.
- `recovered-full-sonnet-S-t34-r5.txt` is the message exactly as in the transcript. `code/collect_full.py` scores it in place of the damaged file and records that it did.
- Why the file was cut: not established. The cut falls after an escaped line break inside a list, at 1748 characters; the other 1,799 finals are complete, so the cause is in how this one was saved, not in the run.
