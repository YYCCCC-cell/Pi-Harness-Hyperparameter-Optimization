// Run only in the pinned runtime with --network none. Synthetic history, no model.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  shouldCompact, prepareCompaction, estimateTokens,
} from "/opt/benchflow/pi/node_modules/@earendil-works/pi-coding-agent/dist/core/compaction/compaction.js";

const contextWindow = 400000;
const reserveValues = [8192, 16384, 32768];
const thresholds = reserveValues.map(reserveTokens => {
  const settings = { enabled: true, reserveTokens, keepRecentTokens: 20000 };
  const threshold = contextWindow - reserveTokens;
  assert.equal(shouldCompact(threshold, contextWindow, settings), false);
  assert.equal(shouldCompact(threshold + 1, contextWindow, settings), true);
  return { reserveTokens, threshold, at_boundary: false, above_boundary: true,
    at_380000: shouldCompact(380000, contextWindow, settings),
    at_390000: shouldCompact(390000, contextWindow, settings) };
});
assert.deepEqual(thresholds.map(r => r.at_380000), [false, false, true]);
assert.deepEqual(thresholds.map(r => r.at_390000), [false, true, true]);

const entries = [];
for (let turn = 0; turn < 100; turn++) {
  for (const role of ["user", "assistant"]) {
    const message = { role, content: [{ type: "text", text: "x".repeat(8000) }], timestamp: turn };
    if (role === "assistant") Object.assign(message, { api: "openai-completions", provider: "fixture",
      model: "synthetic-history", stopReason: "stop",
      usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0 } });
    entries.push({ type: "message", id: `e${entries.length}`, parentId: entries.at(-1)?.id ?? null,
      timestamp: new Date(turn).toISOString(), message });
  }
}
const retention = [10000, 20000, 40000].map(keepRecentTokens => {
  const prep = prepareCompaction(entries, { enabled: true, reserveTokens: 16384, keepRecentTokens });
  assert.ok(prep);
  const index = entries.findIndex(e => e.id === prep.firstKeptEntryId);
  const retainedEstimatedTokens = entries.slice(index).reduce((sum, e) => sum + estimateTokens(e.message), 0);
  assert.ok(retainedEstimatedTokens >= keepRecentTokens);
  return { keepRecentTokens, firstKeptEntryId: prep.firstKeptEntryId,
    retainedMessages: entries.length - index, retainedEstimatedTokens,
    messagesToSummarize: prep.messagesToSummarize.length, tokensBefore: prep.tokensBefore };
});
assert.equal(new Set(retention.map(r => r.firstKeptEntryId)).size, 3);
assert.ok(retention[0].retainedMessages < retention[1].retainedMessages);
assert.ok(retention[1].retainedMessages < retention[2].retainedMessages);
console.log(JSON.stringify({ status: "passed_native_mechanism_probe", kind: "synthetic_history_not_benchmark",
  real_model_calls: 0, source_pins: JSON.parse(readFileSync("/opt/pe6203/runtime.json")).source_commits,
  contextWindow, thresholds, retention }, null, 2));
