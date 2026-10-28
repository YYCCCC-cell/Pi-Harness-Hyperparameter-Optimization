# Task-native Pi / SkillsBench evaluator

Implemented on 2026-10-26. This adds the real execution interface; it does not report a completed paid experiment or a performance improvement.

`hpo.runner` selects the backend from the validated campaign configuration. `evaluation.live.SkillsBenchBenchmark` implements the existing `evaluate(settings, task_id, seed, timeout_seconds, workdir)` contract and launches `.venv-runtime/bin/python -m evaluation.live_worker` once per charged attempt. Default, Random Search, SMAC BO, IGBS and pair-blind all use this interface. Mock configurations continue to require a zero USD budget and cannot dispatch live work.

## Execution and task adaptation

1. Preflight checks pinned clean upstream sources, the reviewed local runtime image and dependencies, actual fixed-model context metadata against all 27 configurations, and all 28 frozen validation task plans. Unknown task IDs and held-out IDs are rejected. The preflight command does not require a key; actual execution does.
2. The worker stages only task instructions, native environment/data/Skills and official verifier files. It omits `oracle/` and never mounts the project root, another task, or the host HOME into the agent. Task source hashes are rechecked before staging.
3. The original Dockerfile and dependency/data layers remain intact. An additive final layer copies the immutable Pi/Node/pi-acp runtime and installs its OS prerequisites. Multi-service Compose definitions retain their services. The existing visual-stability task's unrelated GCloud host mount and credential environment entries are removed; unreviewed host mounts/capabilities fail closed. Third-party source files are not edited.
4. BenchFlow deploys bundled Skills using its native policy and Pi skill paths. Both `with-skill` and `no-skill` are supported; the mode is fixed per campaign. The no-skill path uses BenchFlow's stripped build copy, avoiding bundled skills leaking through `COPY .`.
5. Pi gets the three selected native settings via its isolated `settings.json`. The live RPC observer checks thinking level and configured proxy model/context, and records the pinned `compaction_start` / `compaction_end` events and token usage. Provider callbacks retain reasoning effort for request-level verification. Written settings alone are not proof that a task triggered compaction. See the [small diagnostic and current evidence](pi_diagnostic.md).
6. The task's official verifier determines `raw_reward`. Only exactly `1.0` counts as a pass. Partial rewards, errors and timeouts consume their slots. No replacement attempts or outer retries are added. Native Docker dependency/build retries inside pinned BenchFlow do not create new model attempts.

For `bike-rebalance` (no-network), provisioning can download dependencies, then an owner-based IPv4/IPv6 firewall blocks agent traffic except the local metered provider proxy. Its unprivileged tools inherit the restriction. The root verifier keeps its own access. Other tasks preserve their public network policy. GPU/TPU, alternate OS, custom secret environments, allowlist networking and unreviewed host-dependent Compose capabilities are explicitly rejected rather than silently degraded. None is required by the current 28-task roster. The additive runtime currently expects apt-based Linux images; incompatible images fail before model execution.

Docker enforces declared CPU/RAM limits. `storage_mb` is recorded but is not a portable Docker disk quota. Initial environment-image IDs and CPU/RAM limits are saved. Original task dependencies may use mutable upstream tags/downloads; source hashes alone are not a claim of bit-for-bit image reproduction.

## Timing, accounting and failure cleanup

Task-native environment layers can be provisioned before timed runs with
`.venv-runtime/bin/python -m evaluation.warm_environment --task <validation-id> --output <new-directory>`.
This runs the unchanged native Dockerfile plus the fixed additive runtime, records
preparation time and image identity, and checks a cached build against the original
build limit. It does not run a model or verifier. The separate preparation allowance
does not change task build/agent/verifier timeouts. Formal comparisons must use the
same preparation policy for every method and report provisioning time separately.
The 2026-10-27 powerlifting recovery used 49.74 seconds for preparation, followed by
a 0.39-second cached build and an offline Pi/Skills/official-verifier integration
check. The previous timeout's buffered build output was not retained, so these
records establish recovery through cache preparation, not a proven diagnosis of
the exact earlier network/package step.

Build, agent and verifier limits come from each task; live configs must set `task_timeout_seconds` to `null`. The controller passes remaining method wall time as the outer process deadline. Bounded teardown can extend beyond the work deadline. Process groups include host provider/Compose descendants; each attempt uses a random, persisted Compose project identity. A second host-side reaper removes and verifies only that identity's containers, networks and volumes after every exit, including timeout and interrupt. Cached task/runtime images are retained. Cleanup uncertainty stops the whole campaign.

All Pi calls, including internal compaction calls, use the BenchFlow provider proxy. Per-call usage and estimated cost are captured before the proxy deletes its temporary log. Every recorded call must have complete usage and cost; a partially metered trace is not accepted merely because one call reported usage. Native ACP totals alone are insufficient. Unknown or interrupted totals stay null and stop the comparison. A proven failure before provider setup has zero usage/cost. Available partial evidence remains in the attempt directory.

The real diagnostic exposed a further boundary: success-only completion callbacks cannot exclude a request cancelled before its callback. Native agent timeouts and missing or aborted normal-settled audit events therefore invalidate the full attempt total even if all surviving callbacks succeeded. Known calls remain available as partial evidence. Process-group signal errors are also recorded and must not bypass the exact-label Docker reaper; unresolved process cleanup stops dispatch. See the [corrected diagnostic accounting](pi_diagnostic_real_20261027.md).

`actual_cost_usd` remains null for provider estimates; `estimated_cost_usd` is explicit. `model_api_spend_usd` is not invented from estimates. The summary reports accounted cost separately. Real panels rank by full-panel pass rate, accounted USD, measured wall time, then configuration hash. The audit reconciles real panel cost/time as well as rewards, attempts and ledgers. Simulated cost/time stay null in live results.

`attempt_spend_reservation_usd` reserves budget before dispatch. `spend_policy=reservation_with_inflight_overrun` explicitly acknowledges that it is not a hard in-flight billing cap. A completed attempt exceeding its reservation stops every method. Use provider-side spend controls for a hard financial bound. No new key is loaded from disk or credential stores; execution reads only `OPENROUTER_API_KEY` from the launching environment. Seeds control search/order; provider RNG is not claimed to be controlled.

## Commands

### Calibrated live search profile

The original live grid remains the default. Explicit `live.space_profile=early_compaction_v2` selects [the calibrated grid](../configs/hpo_space.live-v2.json), with reserve=[16384,360000,375000] and keepRecent=[4000,10000,20000]. Thinking levels and the native default remain unchanged. Mock execution rejects this profile. The controller, preflight and worker all use the same profile-specific schemas and feasibility rules.

With the recorded 400k context window, the early reserve values trigger above 40k / 25k. This profile separately requires `keepRecent + safety < contextWindow - reserve` and `keepRecent + modelMaxOutput + safety < contextWindow`; reserve sets the trigger and is not the summary output size. Pi still applies its native dynamic output clamp. Two real tasks completed threshold compaction with this profile; the original grid did not activate on the sampled tasks. [Evidence and limitations](pi_diagnostic_completion_20261027.md). The subsequent [subset and heldout integration](subset_and_heldout.md) adds explicit `live.validation_profile=grouped_v2` and a freeze-gated independent heldout CLI; the original defaults remain unchanged.

Run from `<project-root>`:

```bash
# Read-only inventory: no credentials required, no build/model dispatch.
.venv/bin/python -m hpo preflight \
  --config configs/hpo_live.example.json --output runs/new-live-preflight

# Offline integration: real task environment, Pi and verifier; local model fixture.
.venv-runtime/bin/python -m evaluation.smoke_live \
  --task llm-prefix-cache-replay --output runs/new-prefix-smoke
.venv-runtime/bin/python -m evaluation.smoke_live \
  --task bike-rebalance --output runs/new-bike-smoke
.venv/bin/python -m evaluation.cleanup_smoke --output runs/new-cleanup-smoke

# Runtime-only adapter tests, in addition to the normal test suite.
.venv-runtime/bin/python -m unittest discover -s tests -p test_live_runtime.py -v
```

`configs/hpo_live.example.json` is a concrete example with illustrative budgets: three baselines, two configurations per search arm and all 28 validation tasks (140 planned attempts). Copy it, choose the actual method cap/reservation/wall time and confirm the study scope before running. The existing paid-study draft is not automatically approved by this example.

```bash
# Paid command: only after supplying the intended config and environment credential.
.venv/bin/python -m hpo run --config configs/my-live-campaign.json --output runs/new-live-campaign
.venv/bin/python -m hpo audit --run runs/new-live-campaign
```

Each output directory must be new. No resume or silent mock fallback exists. Live raw directories contain task/model trajectories and should remain private. The existing `evaluation.report` and mock plotting commands still target synthetic experiments; do not use them to label real results.

## Verification evidence

- All 28 task plans passed final read-only preflight: `runs/live-adapter-final-preflight-20261026/preflight.json`.
- Native `llm-prefix-cache-replay` container: Pi discovered its two Skills; low/medium/high and three compaction setting combinations completed real tool writes against a local fixture. Official verifier returned 0 for the unsolved task, as expected. `runs/live-task-smoke-prefix-20261026-v2/smoke-result.json`.
- Native `bike-rebalance` container: four Skills, the same RPC checks, plus ACP tool execution; direct agent egress blocked while fixture access worked. Official verifier returned 0 for the unsolved task. `runs/live-task-smoke-bike-20261026-v2/smoke-result.json`.
- Forced worker termination removed and verified an intentionally left container, network and named volume: `runs/live-cleanup-smoke-20261026/result.json`.
- Controller fixtures exercise real-result accounting across all five methods (including IGBS/pair-blind) without model calls; they are software tests, not benchmark scores.
- Final controller-environment suite: 116 tests discovered, 100 passed, 16 runtime-dependent tests skipped (`runs/live-adapter-tests-final-20261026.log`). The skipped tests were covered separately in `.venv-runtime`: the 8 new adapter tests and the existing 12 runtime tests passed (4 of the latter also run in the controller environment). Logs: `runs/live-adapter-runtime-tests-20261026.log`, `runs/live-adapter-existing-runtime-tests-20261026.log`.
- A live run with the credential explicitly absent stopped in preflight with no dispatch or mock fallback: `runs/live-no-credential-gate-20261026/live-preflight/preflight.json`.

The adapter's original implementation checks above were offline. Subsequent [paid diagnostics](pi_diagnostic_completion_20261027.md) verified provider-backed task metering, budget stops and real automatic compaction, with failures and incomplete historical totals recorded explicitly. The latest controller suite discovered 147 tests (131 passed, 16 runtime skips), and 8 runtime adapter tests passed separately. Full builds/execution of all 28 tasks, formal HPO comparison and heldout performance remain unverified. The hello-world pilot is separate evidence.
