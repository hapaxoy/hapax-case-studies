/* quickplay_agreement_check.js -- Node runner used only by
 * verify_interactive_07.py's JS-vs-Python marking agreement check.
 *
 * Loads interactive/quickplay_score.src.js (the exact source inlined into
 * the built page) and runs its hpxScoreQuickplay() function over a set of
 * fixtures derived from data/analysis/marks.json's own recorded per-
 * requirement "addressed" flags for the real Arm A attempts on T04/T08/T11.
 * Prints the JSON results to stdout for the Python QA script to compare
 * against mark.py's own recorded coverage_pct / trap "caught" values.
 *
 * Usage: node quickplay_agreement_check.js <fixtures.json> <quickplay_score.src.js>
 */
const fs = require("fs");

const [, , fixturesPath, scoreJsPath] = process.argv;
if (!fixturesPath || !scoreJsPath) {
  console.error("usage: node quickplay_agreement_check.js <fixtures.json> <quickplay_score.src.js>");
  process.exit(2);
}

const { hpxScoreQuickplay } = require(scoreJsPath);
const fixtures = JSON.parse(fs.readFileSync(fixturesPath, "utf-8"));

const results = fixtures.map((fx) => {
  const r = hpxScoreQuickplay({
    keyReqIds: fx.key_req_ids,
    tickedReqIds: fx.ticked_req_ids,
    bidCall: fx.bid_call,
    flagConflict: fx.flag_conflict,
    trapMeta: fx.trap_meta,
  });
  return { attempt_id: fx.attempt_id, result: r };
});

process.stdout.write(JSON.stringify(results));
