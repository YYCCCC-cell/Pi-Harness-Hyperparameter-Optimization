// Executes reviewed, verbatim pure-function bodies from the pinned source.
// This is a source-function probe, NOT a full Pi session or provider experiment.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import { execFileSync } from "node:child_process";

const root = fileURLToPath(new URL("../", import.meta.url));
const base = root + "third_party/pi-mono/";
assert.equal(execFileSync("git", ["-C", base, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
  "f321e5bdd26b3624bfb2ab182a334d0a5edb698a");
assert.equal(execFileSync("git", ["-C", base, "status", "--porcelain"], { encoding: "utf8" }).trim(), "");
const sources = {
  compaction: "packages/coding-agent/src/core/compaction/compaction.ts",
  models: "packages/ai/src/models.ts",
  sessions: "packages/coding-agent/src/core/session-manager.ts",
};
const code = {};
const identities = {};
for (const [name, path] of Object.entries(sources)) {
  const original = readFileSync(base + path, "utf8");
  identities[name] = { path, sha256: createHash("sha256").update(original).digest("hex") };
  code[name] = stripTypeScriptTypes(original);
}
const snippets = [];
const functions = [];
function take(source, name) {
  const pattern = new RegExp(`^(?:export )?function ${name}\\s*\\([\\s\\S]*?^\\}`, "m");
  const found = code[source].match(pattern);
  assert.ok(found, `Expected top-level function ${name}`);
  snippets.push(found[0].replace(/^export /, ""));
  functions.push({ source: sources[source], function: name,
    stripped_body_sha256: createHash("sha256").update(found[0]).digest("hex") });
}
for (const name of ["shouldCompact", "estimateTextAndImageContentChars", "estimateTokens",
  "isCutPointMessage", "isTurnStartMessage", "isProjectedTurnStart", "findProjectedTurnStartIndex",
  "findProjectedCutPoint"]) take("compaction", name);
take("sessions", "sessionEntryToContextMessages");
for (const name of ["getSupportedThinkingLevels", "clampThinkingLevel"]) take("models", name);
for (const [source, name] of [["compaction", "ESTIMATED_IMAGE_CHARS"], ["models", "EXTENDED_THINKING_LEVELS"]]) {
  const match = code[source].match(new RegExp(`^const ${name}[^;]*;`, "m"));
  assert.ok(match, `Expected constant ${name}`);
  snippets.push(match[0]);
}
const context = vm.createContext({}, { codeGeneration: { strings: false, wasm: false } });
vm.runInContext(snippets.join("\n"), context, { timeout: 1000 });
const reasoning = { reasoning: true };
const thinking = ["low", "medium", "high"].map(requested => ({ requested,
  effective: context.clampThinkingLevel(reasoning, requested),
  non_reasoning_effective: context.clampThinkingLevel({ reasoning: false }, requested) }));
assert.deepEqual(thinking.map(x => x.effective), ["low", "medium", "high"]);
assert.ok(thinking.every(x => x.non_reasoning_effective === "off"));
const reserve = [8192, 16384, 32768].map(reserveTokens => ({ reserveTokens,
  should_compact: context.shouldCompact(100000, 128000, { enabled: true, reserveTokens }) }));
assert.deepEqual(reserve.map(x => x.should_compact), [false, false, true]);
assert.equal(context.shouldCompact(111616, 128000, { enabled: true, reserveTokens: 16384 }), false);
assert.equal(context.shouldCompact(111617, 128000, { enabled: true, reserveTokens: 16384 }), true);
const entries = Array.from({ length: 6 }, (_, i) => {
  const message = { role: "user", content: "x".repeat(40000) };
  return { sourceEntry: { type: "message", id: `synthetic-${i}`, message }, messages: [message] };
});
const retained = [10000, 20000, 40000].map(keepRecentTokens => ({ keepRecentTokens,
  first_kept_index: context.findProjectedCutPoint(entries, 0, entries.length, keepRecentTokens).firstKeptEntryIndex }));
assert.deepEqual(retained.map(x => x.first_kept_index), [5, 4, 2]);
console.log(JSON.stringify({
  kind: "source_function_probe", node: process.version,
  pi_commit: "f321e5bdd26b3624bfb2ab182a334d0a5edb698a", sources: identities, functions,
  synthetic_inputs: { context_tokens: 100000, context_window: 128000, message_count: 6,
    characters_per_user_message: 40000, model_metadata: reasoning },
  thinking, reserve, retained, checks_passed: true, model_calls: 0, cost_usd: 0,
  limits: ["Functions are evaluated outside the full module/session; unused message-constructor branches are not exercised.",
    "No actual model capability, settings loader, ACP propagation, provider request or compaction summary was tested.",
    "Synthetic examples are not benchmark tasks or performance measurements."]
}, null, 2));
