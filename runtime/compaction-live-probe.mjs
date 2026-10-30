// Controlled synthetic history; real native Pi summaries only with --run.
// This is not a SkillsBench attempt and never produces a benchmark reward.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { shouldCompact, prepareCompaction, estimateTokens, estimateContextTokens, compact }
  from "/opt/benchflow/pi/node_modules/@earendil-works/pi-coding-agent/dist/core/compaction/compaction.js";
import { streamSimple } from "/opt/benchflow/pi/node_modules/@earendil-works/pi-ai/dist/compat.js";

const run = process.argv.includes("--run");
const followup = process.argv.includes("--reviewed-followup");
const bounded = process.argv.includes("--bounded-context");
const networkFollowup = process.argv.includes("--network-followup");
const catalog = JSON.parse(readFileSync("/model.json")).model;
assert.equal(catalog.id, "openai/gpt-5.4-mini");
assert.equal(catalog.context_length, 400000);
const model = { id: catalog.id, name: catalog.name, provider: "openrouter", api: "openai-completions",
  baseUrl: "https://openrouter.ai/api/v1", reasoning: true, input: ["text"],
  contextWindow: bounded ? 128000 : catalog.context_length, maxTokens: catalog.top_provider.max_completion_tokens,
  cost: { input: Number(catalog.pricing.prompt)*1e6, output: Number(catalog.pricing.completion)*1e6,
    cacheRead: Number(catalog.pricing.input_cache_read)*1e6, cacheWrite: 0 },
  compat: { thinkingFormat: "openai", supportsReasoningEffort: true, maxTokensField: "max_completion_tokens" } };
const hash = value => createHash("sha256").update(value).digest("hex");
const fixture = JSON.parse(readFileSync("/history.json"));
assert.equal(fixture.kind, "synthetic_integer_inventory_not_task_data");
const entries = [];
// Dense numeric fixture: provider tokens, not char/4 estimates, prime the
// threshold decision. The summary's separate char/3.5 limiter remains intact.
let offset = 0;
while (offset < fixture.text.length) {
  const size = offset === 0 ? fixture.text.length % 20000 || 20000 : 20000;
  const index = entries.length;
  const message = { role: "user", content: [{ type: "text", text: fixture.text.slice(offset, offset+size) }], timestamp: index };
  entries.push({ type: "message", id: `fixture-${index}`, parentId: entries.at(-1)?.id ?? null,
    timestamp: new Date(index).toISOString(), message });
  offset += size;
}
let estimate = estimateContextTokens(entries.map(e => e.message));
assert.equal(estimate.lastUsageIndex, null);
const rows = [];
const calls = [];
let spent = 0;
const output = { kind: "controlled_synthetic_history_real_native_compaction_not_benchmark",
  mode: run ? "live" : "prepare_no_dispatch", status: "running", model: catalog.id,
  contextWindow: model.contextWindow, catalogContextWindow: catalog.context_length, modelMaxTokens: model.maxTokens,
  diagnostic_output_cap: 8192, native_context_window_unchanged: !bounded,
  context_budget_override_is_diagnostic_only: bounded,
  route: "native_pi_openai_compatible_transport_direct_openrouter_no_provider_override",
  history_sha256: hash(JSON.stringify(entries)), context_estimate: estimate,
  local_tokenizer_text_tokens: fixture.target_text_tokens, planned_context_band: bounded ? [95233,111616] : [367233, 383616],
  provider_usage_fabricated: false, task_attempts: 0, official_reward: null,
  cap_usd: 1.25, prior_unknown_cost_holdback_usd: networkFollowup ? 0.82 : bounded ? 0.68 : followup ? 0.34 : 0,
  separate_availability_cost_usd: followup ? 0.0000795 : 0,
  per_call_reservation_usd: bounded ? 0.14 : 0.34, max_requests: followup ? 3 : 4, retries: 0,
  source_pins: JSON.parse(readFileSync("/opt/pe6203/runtime.json")).source_commits, rows, calls };
function save() { output.known_provider_cost_usd = spent; writeFileSync("/out/result.json", JSON.stringify(output, null, 2)+"\n"); }
async function measuredStream(m, context, options, contrast, maxTokens) {
  if (calls.length >= output.max_requests) throw new Error("request_limit");
  if (spent+output.prior_unknown_cost_holdback_usd+output.separate_availability_cost_usd+output.per_call_reservation_usd > output.cap_usd) throw new Error("dispatch_budget");
  const call = { id: calls.length+1, contrast, status: "inflight", transport_requests: 0 };
  calls.push(call); save();
  const result = await streamSimple(m, context, { ...options, maxTokens, maxRetries: 0,
    fetch: async (...args) => {
      call.transport_requests++; save();
      try { const response = await fetch(...args); call.http_status = response.status; save(); return response; }
      catch(error) { call.transport_error = {name:error.name, message:error.message, cause:error.cause?.code}; save(); throw error; }
    },
    onPayload: payload => {
      call.request = { model: payload.model, reasoning_effort: payload.reasoning_effort,
        max_completion_tokens: payload.max_completion_tokens, stream: payload.stream,
        messages_count: payload.messages.length,
        content_characters: payload.messages.reduce((n,m)=>n+(typeof m.content === 'string' ? m.content.length :
          (m.content||[]).reduce((s,b)=>s+(b.text?.length||0),0)),0) };
      save();
      assert.equal(payload.reasoning_effort, "medium");
      assert.equal(payload.max_completion_tokens, maxTokens);
    } }).result();
  Object.assign(call, { status: result.stopReason, response_id: result.responseId,
    response_model: result.model, usage: result.usage });
  if (result.errorMessage) call.error_message = String(result.errorMessage)
    .replaceAll(process.env.OPENROUTER_API_KEY || "__no_secret__", "[REDACTED]").slice(0, 1500);
  if (result.usage?.cost?.totalFromProvider === true) spent += result.usage.cost.total;
  save();
  if (result.stopReason !== "stop" || result.usage?.cost?.totalFromProvider !== true)
    throw new Error("incomplete_summary_or_provider_cost");
  if (result.usage.cost.total > output.per_call_reservation_usd ||
      spent+output.prior_unknown_cost_holdback_usd+output.separate_availability_cost_usd > output.cap_usd)
    throw new Error("usd_bound_breach");
  return { result: async () => result };
}
save();
try {
  if (run) {
    if (!process.env.OPENROUTER_API_KEY) throw new Error("credential_missing");
    const context = { messages: [...entries.map(e => e.message),
      { role: "user", content: "This is a long-context token-metering diagnostic. Do not process the integer records. Reply only OK.", timestamp: 100 }] };
    const prime = await (await measuredStream(model, context, { apiKey: process.env.OPENROUTER_API_KEY,
      reasoning: "medium", signal: AbortSignal.timeout(240000) }, "provider_context_priming", 64)).result();
    // Keep the exact priming prompt in history so the real usage applies.
    entries.push({ type: "message", id: "prime-prompt", parentId: entries.at(-1).id,
      timestamp: new Date(100).toISOString(), message: context.messages.at(-1) });
    entries.push({ type: "message", id: "prime-response", parentId: "prime-prompt",
      timestamp: new Date(prime.timestamp).toISOString(), message: prime });
    estimate = estimateContextTokens(entries.map(e => e.message));
    output.context_estimate = estimate;
    assert.ok(estimate.tokens >= output.planned_context_band[0] && estimate.tokens <= output.planned_context_band[1]);
    assert.ok(estimate.lastUsageIndex !== null);
    save();
  }
  const plan = followup ? [
    ["reserve-low", 8192, 10000], ["reserve-default", 16384, 10000],
    ["recent-low", 32768, 10000], ["recent-high", 32768, 40000],
  ] : [
    ["reserve-low", 8192, 20000], ["reserve-default", 16384, 20000],
    ["reserve-high", 32768, 20000], ["recent-low", 32768, 10000], ["recent-high", 32768, 40000],
  ];
  for (const [id, reserveTokens, keepRecentTokens] of plan) {
    const settings = { enabled: true, reserveTokens, keepRecentTokens };
    const trigger = shouldCompact(run ? estimate.tokens : bounded ? 105000 : 380000, model.contextWindow, settings);
    const row = { id, settings, threshold: model.contextWindow-reserveTokens, trigger,
      status: trigger ? "prepared" : "threshold_not_reached", model_calls: 0 };
    rows.push(row);
    if (!trigger) { save(); continue; }
    const prep = prepareCompaction(entries, settings);
    assert.ok(prep);
    assert.equal(prep.isSplitTurn, false); // Exactly one native summary per contrast.
    const index = entries.findIndex(e => e.id === prep.firstKeptEntryId);
    Object.assign(row, { firstKeptEntryId: prep.firstKeptEntryId, retained_messages: entries.length-index,
      retained_estimated_tokens: entries.slice(index).reduce((sum, e) => sum+estimateTokens(e.message), 0),
      messages_to_summarize: prep.messagesToSummarize.length, tokens_before: prep.tokensBefore });
    if (!run) { save(); continue; }
    if (!process.env.OPENROUTER_API_KEY) throw new Error("credential_missing");
    const started = performance.now();
    const stream = (m, context, options) => measuredStream(m, context, options, id, 8192);
    const result = await compact(prep, model, process.env.OPENROUTER_API_KEY, undefined,
      "This is a synthetic diagnostic. Produce a concise checkpoint under 250 words; preserve RELEASE_DELAY_MS=37.",
      AbortSignal.timeout(240000), "medium", stream, undefined,
      { enabled: false, maxRetries: 0, baseDelayMs: 0 });
    assert.equal(result.firstKeptEntryId, prep.firstKeptEntryId);
    assert.ok(result.summary.includes("RELEASE_DELAY_MS=37"));
    Object.assign(row, { status: "completed_native_compaction", model_calls: 1,
      wall_seconds: (performance.now()-started)/1000, summary_sha256: hash(result.summary),
      summary_characters: result.summary.length, release_marker_preserved: true, usage: result.usage });
    save();
    console.log(JSON.stringify({ contrast: id, status: row.status, known_provider_cost_usd: spent }));
  }
  assert.deepEqual(rows.map(r => r.trigger), followup ? [false, false, true, true] : [false, false, true, true, true]);
  if (followup) assert.ok(rows[2].retained_estimated_tokens < rows[3].retained_estimated_tokens);
  else {
    assert.ok(rows[3].retained_estimated_tokens < rows[2].retained_estimated_tokens);
    assert.ok(rows[2].retained_estimated_tokens < rows[4].retained_estimated_tokens);
  }
  output.status = run ? "completed_live_mechanism_diagnostic" : "prepared_no_dispatch";
} catch (error) {
  output.status = "stopped";
  // Exception bodies may contain upstream details; persist only our safe category.
  output.stop_reason = ["credential_missing", "dispatch_budget", "request_limit", "usd_bound_breach", "incomplete_summary_or_provider_cost"].includes(error.message)
    ? error.message : error.name;
  process.exitCode = 1;
} finally { save(); }
