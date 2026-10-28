# Phase 2 feasibility verification

Historical report: the blockers below describe the initial preflight. Docker, BenchFlow dependencies, the fixed-source Pi image and offline RPC/ACP verification have since been prepared. See [current runtime instructions](phase2_reproduction.md) for the 2026-10-25 update. The real provider-backed pilot remains unexecuted.

Status on 2026-10-25: **partial — external runner and offline checks completed; real pilot blocked before dispatch.** No end-to-end Pi/SkillsBench success is claimed. No optimizer was implemented, no scored task was evaluated, and no dependency installer was executed.

## Decision provenance

The Phase 1 document explicitly labels its choices provisional and lists model, runtime artifact, infrastructure and budget as undecided. The new instruction authorizes Phase 2 and one low-cost pilot. It does not supply a particular model or dollar amount. This phase therefore carries forward **Pi + SkillsBench 1.1**, the existing `pi-acp` route, and the three proposed settings, without inventing a prior approval record. An asynchronous question requested the missing exact provider/model, credential variable name and spending ceiling.

The pilot is restricted to `experiments/sanity-tasks/hello-world`, a separate sanity package outside the proposed 28/59 validation/test split. This is the smallest proposed pilot, not a measured member of the 87-task scored suite. Its prompt asks for `hello.txt`; its native agent and verifier timeouts are each 120 seconds. [SkillsBench v1.1 task.md:1–23](https://github.com/benchflow-ai/skillsbench/blob/b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af/experiments/sanity-tasks/hello-world/task.md#L1-L23). It contains no task skill pack, so selecting the with-skill policy does not test skill discovery.

## Delivered files and evidence

| Deliverable | Location | Verified status |
|---|---|---|
| Minimal external CLI | [pilot package](../pilot/__main__.py), [BenchFlow worker](../pilot/worker.py) | Preflight executed; real Docker/ACP branch not executed |
| Exact configuration serializer | [config.py](../pilot/config.py), [pilot.json](../configs/pilot.json) | Offline tests pass; missing choices remain JSON null |
| Result parser | [results.py](../pilot/results.py) | Tested against explicitly synthetic BenchFlow-format fixtures |
| Configuration and result unit tests | [test_pilot.py](../tests/test_pilot.py), test log（本地或历史材料，未打包：`../runs/archive/pi-setup-20261026/phase2-preflight-20261025/unit-tests.log`） | 22 passed, including one-dispatch guard |
| Source-function behavior probe | [probe script](../scripts/probe_pi_functions.mjs), observed JSON（本地或历史材料，未打包：`../runs/archive/pi-setup-20261026/phase2-preflight-20261025/pi-function-probes.json`） | Passed; zero model calls; not a full Pi runtime test |
| Pilot readiness log | preflight.json（本地或历史材料，未打包：`../runs/archive/pi-setup-20261026/phase2-preflight-20261025/preflight.json`） | Blocked before execution |
| Pilot status record | result.json（本地或历史材料，未打包：`../runs/archive/pi-setup-20261026/phase2-preflight-20261025/result.json`） | `benchmark_attempted=false`, success null, zero dispatched model calls |
| Frozen intended settings and source identities | manifest.json（本地或历史材料，未打包：`../runs/archive/pi-setup-20261026/phase2-preflight-20261025/manifest.json`）, settings（本地或历史材料，未打包：`../runs/archive/pi-setup-20261026/phase2-preflight-20261025/pi-settings.json`） | All four existing checkout SHAs match; clean trees |
| Reproduction and remaining setup | [reproduction instructions](phase2_reproduction.md) | Offline commands work; paid path prerequisites explicitly unresolved |

The preflight record is **not a failed benchmark trial** and does not consume the one-pilot dispatch allowance. Tokens and task execution time are null because no solver ran. Its USD field is zero with provenance `no_model_calls_dispatched`, not a token-based estimate or a claim that a completed trial was free. The recorded preflight duration measures readiness checking only.

## Selected source and supported interface

| Component | Frozen source commit | Runtime status |
|---|---|---|
| Pi, manifest version 1.4.0 | `f321e5bdd26b3624bfb2ab182a334d0a5edb698a` | No built artifact installed; do not substitute npm 1.4.0 without re-auditing source identity |
| SkillsBench v1.1 | `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af` | Source reused; no task execution |
| BenchFlow v0.6.3 | `99baefb602674bbd31139fd2f1a22c3ed45752f9` | Package/dependencies absent in the execution interpreter |
| pi-acp 0.0.34 gitHead | `b0581c9c1d675e634234674484247008b03d69b4` | Source reused; adapter not installed or handshaken |

The live checkout observations are in the preflight log. Pi supports agent-directory `settings.json`, with `PI_CODING_AGENT_DIR` selecting that directory; project settings can take precedence after trust. [Pi configuration:1–35](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/configuration.md#L1-L35). The wrapper writes only the three candidate values plus fixed startup provider/model identity into a fresh sandbox home. It preserves native tools, retry policy, compaction enablement and cache-warming defaults. `PI_OFFLINE=1` is a fixed operational setting; it is not a network sandbox. [Pi CLI Offline mode](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/cli.md#L194-L242).

## Verified parameter table

The columns distinguish **documented support**, **executed source-function behavior**, and **full-session verification**. The source probe strips TypeScript annotations using the existing Node 24.19.0 runtime and evaluates the reviewed, unchanged function bodies in an isolated JavaScript context. It does not import Pi's complete dependency graph, exercise its settings loader, simulate a provider, or submit benchmark prompts. Source and extracted-function hashes are recorded in its JSON output. Unused branches requiring message constructors are not exercised.

| Exact supported setting | Official default/domain; proposed values | Observed source-function result | Real Pi/adapter verification |
|---|---|---|---|
| `defaultThinkingLevel` | Default `medium`; `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, subject to model support. Proposed: low/medium/high. | Official clamping functions preserve the three values for synthetic `reasoning=true` metadata; all become `off` for `reasoning=false`. This verifies clamping, not different provider reasoning or success. | **Pending:** exact selected model, effective state after ACP model selection, and provider request parameters |
| `compaction.reserveTokens` | Default 16384; nonnegative safe integer. Proposed: 8192/16384/32768. | With synthetic context usage 100000 and context window 128000, official `shouldCompact` returns false/false/true. Boundary check confirms strict `>` rather than `>=`. | **Pending:** settings propagation, actual context threshold and a compaction event in a full session |
| `compaction.keepRecentTokens` | Default 20000; nonnegative safe integer. Proposed: 10000/20000/40000. | For six synthetic user entries of 40000 characters each, the official projected cut-point routine selects first-kept indexes 5/4/2, retaining 1/2/4 entries. | **Pending:** full-session projection, actual summarization and evidence retention on a task |

Exact source evidence:

- Names and defaults: [Pi settings:13–17](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L13-L17), [compaction:69–82](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L69-L82).
- Runtime numeric constraints and per-model override precedence: [settings-manager.ts:833–879](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/settings-manager.ts#L833-L879).
- Startup precedence and clamping: [sdk.ts:253–278](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/sdk.ts#L253-L278), [models.ts:1257–1294](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/ai/src/models.ts#L1257-L1294).
- Trigger and retained-context logic: [compaction.ts:267–270](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/compaction/compaction.ts#L267-L270), [projected cut point:789–856](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/compaction/compaction.ts#L789-L856), [production caller:859–885](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/compaction/compaction.ts#L859-L885).

**Task 2 is only partially satisfied.** These controls have documented and executable logic effects. Their propagation and activation in the selected benchmark runtime are unverified. A cheap hello-world task may never trigger compaction; successful completion must not be represented as verification of all three dimensions.

## Integration boundary and runner behavior

BenchFlow v0.6.3 already registers `pi-acp`; its provider launcher bridges BenchFlow provider information and then execs pi-acp. Pi-acp starts native Pi RPC with `--mode rpc --no-themes`. Thus this benchmark has an existing supported **external adapter**; Pi does not directly speak ACP. No new protocol adapter is implemented here. [Registry:366–389](https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/agents/registry.py#L366-L389), [provider launcher:48–117](https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/agents/pi_acp_launcher.py#L48-L117), [pi-acp process.ts:154–171](https://github.com/svkozak/pi-acp/blob/b0581c9c1d675e634234674484247008b03d69b4/src/pi-rpc/process.ts#L154-L171).

The worker uses public `register_agent` to preserve the existing Pi adapter's metadata and replace only its install/launch commands: installation becomes executable-presence checks against a reviewed prebuilt image; launch writes official settings and starts the upstream launcher. This avoids the pinned registry's floating npm install and old package scope. It is external integration configuration, not a Pi patch. [Registration API:1009–1075](https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/agents/registry.py#L1009-L1075), [floating installer:170–188](https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/agents/registry.py#L170-L188).

The image override uses the public environment manifest instead of editing the task Dockerfile. [Image seam:660–679](https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/sandbox/setup.py#L660-L679). The setup hook uploads the project wrappers and the exact upstream provider launcher. `Rollout.run()` retains official execution, verification and cleanup. [Hook:619–620](https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/rollout/__init__.py#L619-L620), [lifecycle:1450–1573](https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/rollout/__init__.py#L1450-L1573).

The RPC audit wrapper forwards traffic and records selected state, model and compaction event metadata. It does not inject prompts, change tool definitions, or add turns. The supported adapter override is `PI_ACP_PI_COMMAND`. [pi-acp agent.ts:280–290](https://github.com/svkozak/pi-acp/blob/b0581c9c1d675e634234674484247008b03d69b4/src/acp/agent.ts#L280-L290). This instrumentation's full transport behavior still needs a real handshake; unit tests only verify its metadata filtering.

The CLI allows only hello-world and rejects batch/task substitutions. It writes fresh manifests and logs, checks source pins/cleanliness, requires an immutable local image, and consumes an atomic project-wide dispatch guard only after preflight passes. A second run cannot silently start another pilot. There is no outer solver retry, HPO loop or held-out evaluation. The worker imposes a 600-second lifecycle deadline in addition to the 120-second agent budget; the parent has a 720-second emergency timeout. Emergency termination can leave a container requiring cleanup, so inspect the recorded sandbox identity after such a failure.

## Parsing and accounting decisions

The parser reads the actual pinned `result.json` layout, including nested `agent_result`, raw rewards, errors, timing and model identity. It does not invent a flat token schema. [Writer:369–414](https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/rollout/_results.py#L369-L414).

Explicit reward takes precedence in the official outcome classification, even if a separate error exists. Therefore the parser preserves both `success` and diagnostic/measurement-gate status. Partial reward is not a pass. [Scoring:194–227](https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/_utils/scoring.py#L194-L227). This corrects the potential mistake of treating any error string as sufficient to override official reward.

BenchFlow's `cost_usd` is labelled **estimated**, not an actual provider invoice; `price_source` is retained. Zero token placeholders with `usage_source=unavailable` become null in the normalized record. [Result contract:79–93](https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/models.py#L79-L93), [unavailable usage:60–73](https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/usage_tracking.py#L60-L73).

`budget_usd` is a post-run check, **not an enforced task-wide spend ceiling**. A runtime review must describe provider-side spending control, or record explicit acceptance of a bounded pilot with possible in-flight overshoot. This runner does not implement an unreviewed billing proxy. Cached-token accounting, provider retries, summaries and cache warming still require reconciliation against captured provider calls. A trusted usage label alone cannot prove every auxiliary call was captured.

## Exact blockers and smallest compliant alternative

The recorded preflight found:

1. No Docker executable in the execution environment. Additional read-only checks found no Docker Desktop/OrbStack application or standard Docker socket at the checked locations. This does not establish that no remote Docker host exists.
2. No BenchFlow 0.6.3 distribution/dependencies in the selected Python interpreter; no installed Pi or pi-acp runtime was found. Bundled Node 24.19.0 was available for the isolated source-function probes.
3. No exact model, credential environment variable, or USD ceiling in the saved decisions. The common provider key variables checked were unset; no credential value was displayed or written to artifacts.
4. No reviewed digest-pinned runtime image built from the selected Pi source snapshot, and no dependency/build review record. The image source identity remains a required build attestation, not a verified reproducible build.
5. The official sanity verifier invokes `apt-get` and downloads/runs the uv 0.9.7 installer, then pytest 8.4.1. Its local script was read, but the downloaded installer and dependency execution have not yet been reviewed/executed. [Verifier:1–18](https://github.com/benchflow-ai/skillsbench/blob/b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af/experiments/sanity-tasks/hello-world/verifier/test.sh#L1-L18). Exact patch-level labels do not by themselves freeze downloaded bytes.

**Smallest compliant continuation:** use an existing Docker-capable machine, keep these source pins and this runner, prepare one reviewed runtime image and isolated Python environment, supply the exact model/key-variable/budget, and run this one sanity task. This does not require changing benchmark, rewriting the adapter, reading held-out solutions, or running the solver on the host. Installing Docker locally is an alternative setup task; choosing Modal adds account/compute decisions and is not silently substituted here.

Remaining risks after setup are adapter/Pi version compatibility, provider metadata that clamps thinking to off, model alias changes, untriggered compaction, incomplete auxiliary-call costs, stale cache effects, image architecture and native dependencies, incomplete container cleanup, and the fact that a trivial sanity task is not evidence of SkillsBench accuracy or skill use. No search algorithm development should begin on the basis of these offline checks alone.
