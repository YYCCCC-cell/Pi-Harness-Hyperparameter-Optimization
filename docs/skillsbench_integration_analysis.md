# SkillsBench 1.1 integration analysis

Prepared 2026-10-25 (Asia/Singapore). **Source-level feasibility is established; end-to-end execution is not yet validated.** No dependencies were installed and no benchmark, oracle, Docker build, Modal job, or paid API request was run.

## Frozen source identities

| Component | Local checkout | Inspected version | Exact commit |
|---|---|---|---|
| SkillsBench | `third_party/skillsbench` | `v1.1` | `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af` |
| BenchFlow | `third_party/benchflow` | `v0.6.3` | `99baefb602674bbd31139fd2f1a22c3ed45752f9` |
| Pi | `third_party/pi-mono` | main snapshot; manifest version 1.4.0 | `f321e5bdd26b3624bfb2ab182a334d0a5edb698a` |
| pi-acp, supporting adapter upstream | `third_party/pi-acp` | npm version 0.0.34 / matching npm gitHead | `b0581c9c1d675e634234674484247008b03d69b4` |

These are detached, shallow source checkouts. The fourth checkout was collected because BenchFlow's Pi integration launches this separate upstream adapter; it is **not Pi core or a BenchFlow-owned repository**. Exact origins, tree IDs, commit dates, and clean-tree results are in [source_lock.json](sources/source_lock.json). The package identities and adapter invocation are directly visible in source. [P1] [B1] [B2] [A1]

The official [SkillsBench v1.1 release, “What this release pins” and “Reproducing results”](https://github.com/benchflow-ai/skillsbench/releases/tag/v1.1) specifies **87 active tasks, 14 excluded packages, and BenchFlow >=0.6.3,<0.7**. The release JSON and task manifest were saved in `docs/sources/`. The manifest asset SHA-256 is `0aa87c4d4f64c33db74b20e770f4b4a77dc21911e81a8ffd50cbb84ac7a4cc6f`; all 101 local package digests match. The digest algorithm hashes sorted relative paths plus each file's SHA-256, excluding symlinks and file modes. This was a mechanical integrity check, not execution or semantic inspection of the tasks. [B3] [Saved evidence](sources/source_lock.json)

## Documentation drift that affects reproduction

| Evidence | Finding | Rule for this project |
|---|---|---|
| SkillsBench README quick start vs pyproject | README still says >=0.6.2; dependency metadata says >=0.6.3,<0.7 | Follow v1.1 release + dependency metadata and pin exactly 0.6.3. [S1] [S2] |
| BenchFlow README vs pyproject at v0.6.3 | README still calls 0.6.2 current; package version is 0.6.3 | Use immutable tag/commit + package metadata. [B4] [B5] |
| Current website vs v1.1 website source | Live getting-started guide recommends Modal; v1.1 source lists Docker and older 0.6.2 text | Document both; explicitly choose one backend for comparison. [S3] [Live guide, “Prerequisites” / “Run One Task”, accessed 2026-10-25](https://www.skillsbench.ai/docs/getting-started) |
| Registry dataset resolution | Default registry URL points at moving `skillsbench/main/registry.json`; a resolved entry pins commit and task digests | Prefer the local pinned checkout for this project, or save and hash a registry snapshot. Do not assume the live registry is frozen. [B6] [B7] |

## What a task is and how it executes

The native v1.1 package contains `task.md`, `environment/`, `environment/skills/`, `oracle/`, and `verifier/`. YAML frontmatter describes metadata and resource/time requirements; the Markdown body is the agent-facing task. Native `task.md`/`oracle`/`verifier` take precedence over legacy `task.toml` + `instruction.md`/`solution`/`tests`. No conversion to an older Harbor-style layout is needed. [S4] [S5] [B8] [B9]

| Phase | Source-backed behavior | Project implication |
|---|---|---|
| Resolve | Load task, resolve provider environment, skill policy, prompt, and agent launch configuration | Preserve original task bytes and model/provider identity. [B10] |
| Stage | When needed, copy the package to a temporary tree, remove bundled skills for no-skill, or inject skill files into its build context | The framework can modify a disposable staging copy while the checked-in third-party source remains unchanged. Audit effective build inputs. [B11] |
| Start | Start sandbox, upload task files, run optional `pre_agent_hooks` | Hooks are a supported external setup seam; they run **before** agent installation. [B12] |
| Install / isolate | Install agent, establish sandbox user and credentials, snapshot verifier workspace, deploy skills and lock sensitive paths | Keep `sandbox_user="agent"`; don't opt out of lockdown. [B13] [B14] |
| Connect / solve | ACP runtime initializes a session and sets model options; rollout sends task prompts | Pi tools execute inside the task sandbox, and ACP is the control/trace interface. [B15] [B16] [A2] |
| Verify | Harden the workspace, invoke the task verifier under its timeout, collect canonical reward | Keep verifier and scoring policy unchanged. [B17] [B18] [B19] |
| Persist / cleanup | Result records include reward, errors, usage, and trajectory; rollout has explicit verify and cleanup phases | Preserve raw artifacts and ensure teardown also occurs on cancellation/failure. [B20] [B21] |

Oracle mode invokes the task's `oracle/solve.sh` reference solution through the same evaluation infrastructure. It does not invoke the coding agent's LLM, but shell scripts, dependency downloads, and cloud compute can still consume resources. Oracle success is an environment/verifier preflight, not a Pi result. The supplied `hello-world` sanity package is outside the 87-task benchmark roster and can be used for integration debugging. Its verifier writes 1 or 0 based on pytest outcomes and even installs tooling when run; **it has only been read here**. [B22] [S6] [S7]

## Scoring and reporting

BenchFlow's script verifier reads `reward.json` or `reward.txt`; text must be a finite permitted numeric value. A nonzero verifier exit with a freshly produced valid reward can still be accepted as a scored failure. Missing, empty, or invalid reward output is a verifier/infrastructure issue, not evidence of successful completion. Do not substitute assistant self-report or process exit code for task reward. [B23] [B24]

Canonical score classification gives `reward == 1.0` a pass, another explicit reward a fail, and otherwise classifies agent/verifier errors. BenchFlow separately supports an audit-oriented classification with different precedence; retain both diagnostic evidence and the canonical score. Overall pass rate is `passed/total`; the error-excluded variant is `passed/(passed+failed)`. Report the all-task denominator as primary so failing infrastructure cannot improve the headline score by disappearing. [B25] [B26]

**Proposed project metrics:** task-weighted mean reward, fraction of trials with reward exactly 1, wall time, API cost, input/output/cache tokens, tool calls, compaction count, timeout rate, agent error rate, and verifier error rate. Use the same repeats per task and paired task/condition comparisons. For binary tasks, mean reward and pass fraction coincide; do not assume every possible verifier is binary. Skill-use traces are secondary analysis; the outcome verifier remains authoritative. The existing result writer and usage contract support reward/error/usage recording, while Pi event logs are needed for Pi-specific counters. [B20] [B27] [P2]

For comparisons, keep task timeout/resource limits fixed and retain a terminal row for every scheduled trial. Predeclare infrastructure-retry policy independently of model score. Any reruns must keep their original failed attempt and cost in the audit trail. Do not use `verify-retry` or reveal verifier feedback during solving: that changes the evaluation protocol and can expose hidden tests. These are project policies; BenchFlow exposes such loop strategies but they are not required for native SkillsBench execution. [B28] [B29]

## Skill conditions and leakage boundaries

- `no-skill` is the default; it rejects a supplied `skills_dir`. `with-skill` can use each task's bundled skills or an explicitly supplied directory. `self-gen` is a different treatment and should be excluded from the initial Pi hyperparameter study. [B30]
- For no-skill, BenchFlow strips `environment/skills` from a temporary task copy and removes supported skill COPY lines. For with-skill, the Pi registry deploys skills to `$HOME/.pi/agent/skills` and `$HOME/.agents/skills`. A prebuilt image or an unrelated mounted home can still contain extra knowledge, so a no-skill flag alone is not sufficient evidence of isolation. This residual-risk statement is an inference from the staging and discovery boundaries. [B31] [B32] [B33] [P3]
- Pi initially advertises skill name/description/path and lets the model read full instructions as needed. `enableSkillCommands=false` affects command discovery, not all skill access. BenchFlow can prepend a skill-discovery nudge; explicitly set it to `off` for the initial native-Pi comparison, then hold it fixed. The `off` choice is this project's recommendation, not a benchmark requirement. [P4] [B34] [B35]
- Leave `oracle_access=false`; retain default protected directories (`/oracle`, `/solution`, `/verifier`, `/tests`, `/testbed_verify`) and a non-root agent. Do not mount this project directory, the whole benchmark checkout, prior jobs, or hidden-test output into the solver workspace. Defaults are implementation evidence; these mounting restrictions are the project design needed to preserve that boundary. [B36] [B14]

## Existing adapter: decisive finding

**A supported adapter already exists in BenchFlow v0.6.3: `--agent pi-acp`, alias `--agent pi`. A new custom external protocol adapter is not presently required.** BenchFlow's registry launches `pi-acp-launcher`, which maps provider configuration and executes pi-acp. The separate upstream pi-acp translates ACP JSON-RPC into native Pi JSONL RPC, launching one Pi subprocess with `--mode rpc --no-themes`. Native Pi RPC is not itself an ACP endpoint. [B2] [B37] [B38] [A3] [A2] [P5]

The adapter README calls it an MVP centered on Zed, specifies Pi >=0.81.0, and warns of compatibility variation. The inspected 0.0.34 code already waits for `agent_settled`, correctly distinguishing that from low-level `agent_end`; it also maps an internal Pi error to ACP `end_turn` in some cases. Therefore transport completion is not proof of successful solving, and error traces must be retained. These are source observations, not results of a compatibility test. [A4] [A5] [A6] [A7] [P6]

### Adapter contracts

| Interface | Contract / implication |
|---|---|
| BenchFlow registry | `AgentConfig` includes install/launch commands, protocol, required environment, skill paths, credential files, home directories, model format, and optional model/effort option IDs. Pi uses `registered-provider/model` model IDs. [B39] [B2] |
| ACP initialization | BenchFlow prefers an advertised model config option, else `session/set_model`; effort requires a declared registry option. [B15] |
| pi-acp controls | Supports model changes and thinking through `thought_level` config or session mode, forwarded to native Pi RPC. [A8] [A9] |
| Native Pi RPC | Command/response IDs, streamed events, cancellation and state/stats commands; read the stream until settled, not merely prompt acknowledgment. [P7] |
| Alternative external integration | BenchFlow's `Agent` factory exposes `connect`/`capabilities`; `Session` exposes `prompt`, `cancel`, `on_ask_user`, `steps`, and `on_change`. A session-factory route exists in `AgentConfig`, but adding a custom agent is not just passing an arbitrary executable string. [B40] [B41] |

### Compatibility problems to resolve before a paid run

1. **Unpinned npm bootstrap and renamed Pi package.** Registry helpers append `@latest` to unversioned packages; the Pi entry installs `@mariozechner/pi-coding-agent` and `pi-acp`, while the inspected Pi package is now `@earendil-works/pi-coding-agent`. An ordinary `bench eval run --agent pi` does not guarantee the inspected source is executed. Pin the actual runtime artifacts, not just these source directories. [B42] [B43] [P8]
2. **Thinking CLI gap.** Pi's BenchFlow entry has no `acp_effort_config_id`; `--reasoning-effort` raises in BenchFlow 0.6.3 even though pi-acp exposes `thought_level`. Use Pi settings or an explicit external control path, and inspect effective state. Do not silently patch the registry. [B2] [B44] [A8] [A10]
3. **Provider translation is incomplete as a universal abstraction.** The launcher has an explicit OpenAI-completions branch; its other branch sets Anthropic environment values. It writes `~/.pi/agent/models.json`, ignoring `PI_CODING_AGENT_DIR`. Its fallback custom-model metadata is context=128000, output=16384, reasoning=false, input=text unless metadata is supplied. Do not assume arbitrary providers, Responses endpoints, vision, or reasoning work by name alone. Start with one verified provider route, and validate endpoint/model metadata. [B45] [B46]
4. **Settings and trust drift.** The pi-acp settings helper merges user/project files directly, whereas current Pi gates project configuration on trust. Configure global settings in a fresh sandbox home, and avoid project config for the first experiment. A custom agent directory also needs corresponding provider and skill paths. [A11] [P9] [B33]
5. **Runtime versions.** BenchFlow requires Python >=3.12; Pi requires Node >=22.19.0. BenchFlow's private Node bootstrap pins 22.20.0 and supports Linux x64/arm64. The pi-acp package engine says >=20 while its README asks for Node 22+; honor the stricter Pi requirement. Native task dependencies and architecture still need validation. [B1] [P10] [B47] [A12] [A5]
6. **Official sweep script scope.** The SkillsBench integration runner accepts oracle/gemini/both/list and maps solver runs to Gemini. It is not a general Pi HPO driver. Use BenchFlow's supported CLI/SDK directly, with an external project runner. [S8] [S9]
7. **Telemetry must be checked.** `usage_tracking=auto` may leave cost unavailable; `required` fails when trusted usage cannot be captured. A zero token placeholder with `usage_source="unavailable"` is not a free trial. Pi compaction/cache calls and adapter error translation need explicit audit coverage. [B48] [P11] [P12] [A7]

## Recommended external integration plan

This plan is **not implemented or executed**. Keep all project code/configuration outside `third_party/`; do not edit Pi, pi-acp, BenchFlow, or SkillsBench source.

1. **Freeze runtime artifacts.** In a later authorized setup phase, build/package the exact Pi commit with its committed lockfile, or deliberately choose a released Pi artifact and revise this analysis to that exact release. Do not equate a manifest version string with an identical source artifact. Pin pi-acp 0.0.34, BenchFlow 0.6.3, Node, Python dependency locks, and image digests. The main-source/published-artifact distinction follows from the recorded checkout and package metadata; the lockfile policy is the project design.
2. **Reuse the registered adapter.** Use a project-owned setup hook or derived image to preinstall exact Pi/pi-acp artifacts in BenchFlow's expected private prefix, so its executable guards do not install `@latest`. Keep the registry's normal install/setup phase for credentials, skill-path metadata, ownership, and wrapper deployment. `skip_agent_install=True` sets `_agent_cfg=None`, so bypassing it blindly can lose useful setup metadata. This is a proposed use of existing seams and needs testing. [B49] [B50] [B51]
3. **Inject candidates without core changes.** Have a project-owned Pi executable wrapper, selected by `PI_ACP_PI_COMMAND`, copy the immutable candidate `settings.json` into the actual sandbox user's `~/.pi/agent/` before exec. Keep provider configuration and skill mounts intact. The wrapper can append approved Pi CLI resource-discovery flags; it must keep stdout protocol-clean. Record its own hash. pi-acp reads the executable override and inherits environment; these are real integration seams. [A13] [A2] [P13] [P14]
4. **Use explicit skill conditions.** With-skill: expose only that task's resolved skill root and preserve its bytes. No-skill: use BenchFlow stripping plus Pi discovery suppression and inspect the filesystem/trace for stray skill access. Do not copy the entire benchmark into the sandbox. Keep the prompt, nudge policy, and skill contents fixed while tuning Pi settings. [B52] [P15]
5. **Verify provenance and effective settings.** Capture Pi version/build SHA, adapter version, model/provider IDs, capability metadata, candidate hash, actual tool list and thinking level, task digest, image digest, skill mode, timeout/resource budgets, and raw RPC/ACP logs. Native RPC state/stat commands and BenchFlow result/provenance fields are the evidence channels, not a printed run label. [P16] [P17] [B53]
6. **Run staged checks only after setup is authorized.** Schema/structural checks; adapter handshake/model selection and a credential-free fake-provider test; Docker hello-world oracle; one bounded solver smoke call after cost approval; then validation-only search. Check cancellation, timeouts, missing telemetry, no-skill isolation, and unchanged task reward behavior before scaling. See the feasibility document for the split and test lock.

Illustrative upstream CLI forms, **not run here and not sufficient by themselves to pin the Pi bootstrap**:

```sh
cd '<project-root>'
bench tasks check third_party/skillsbench/experiments/sanity-tasks/hello-world
bench eval run --tasks-dir third_party/skillsbench/experiments/sanity-tasks/hello-world \
  --agent oracle --sandbox docker

# After exact-runtime bootstrap and candidate injection have been implemented:
bench eval run --tasks-dir third_party/skillsbench/tasks \
  --include '<validation-task-id>' --agent pi-acp --model '<exact-provider/model-id>' \
  --sandbox docker --skill-mode with-skill --agent-env BENCHFLOW_SKILL_NUDGE=off \
  --usage-tracking required --concurrency 1 --jobs-dir '<unique-run-output-dir>'
```

Use separate runs and output directories for repeats and conditions. For no-skill, change the explicit skill mode and do not supply a skills directory. The commands use supported task filters, modes, and telemetry controls, but the proposed project bootstrap/wrapper remains future work. [B54]

### When a custom adapter would become justified

Only if offline/low-cost conformance tests show a blocking mismatch that cannot be resolved through pinning, configuration, or the external wrapper should the project implement a new external integration. Preserve the BenchFlow Session contract and native Pi RPC lifecycle, cancellation, usage, and event semantics; retain the official task/verifier runner. Do not replace the benchmark with a home-written score loop. This is a contingency plan, not a finding that a custom adapter is currently required. [B40] [P7]

## Source index

All repository citations below are immutable links to the exact inspected commit. Line numbers refer to that checkout, not moving `main`. `P` = Pi, `S` = SkillsBench, `B` = BenchFlow, `A` = the upstream pi-acp adapter.

- **P1**: `third_party/pi-mono/packages/coding-agent/package.json:1–21`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P1]

[P1]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/package.json#L1-L21

- **B1**: `third_party/benchflow/pyproject.toml:1–19`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B1]

[B1]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/pyproject.toml#L1-L19

- **B2**: `third_party/benchflow/src/benchflow/agents/registry.py:366–389`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B2]

[B2]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/agents/registry.py#L366-L389

- **A1**: `third_party/pi-acp/package.json:1–18`; 0.0.34 npm gitHead; supporting adapter upstream; commit `b0581c9c1d675e634234674484247008b03d69b4`. [A1]

[A1]: https://github.com/svkozak/pi-acp/blob/b0581c9c1d675e634234674484247008b03d69b4/package.json#L1-L18

- **B3**: `third_party/benchflow/src/benchflow/_utils/task_authoring/__init__.py:114–141`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B3]

[B3]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/_utils/task_authoring/__init__.py#L114-L141

- **S1**: `third_party/skillsbench/README.md:21–48`; v1.1; commit `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af`. [S1]

[S1]: https://github.com/benchflow-ai/skillsbench/blob/b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af/README.md#L21-L48

- **S2**: `third_party/skillsbench/pyproject.toml:1–9`; v1.1; commit `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af`. [S2]

[S2]: https://github.com/benchflow-ai/skillsbench/blob/b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af/pyproject.toml#L1-L9

- **B4**: `third_party/benchflow/README.md:26–55`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B4]

[B4]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/README.md#L26-L55

- **B5**: `third_party/benchflow/pyproject.toml:1–6`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B5]

[B5]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/pyproject.toml#L1-L6

- **S3**: `third_party/skillsbench/website/src/content/docs/getting-started.mdx:10–45`; v1.1; commit `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af`. [S3]

[S3]: https://github.com/benchflow-ai/skillsbench/blob/b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af/website/src/content/docs/getting-started.mdx#L10-L45

- **B6**: `third_party/benchflow/src/benchflow/_utils/dataset_registry.py:1–23`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B6]

[B6]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/_utils/dataset_registry.py#L1-L23

- **B7**: `third_party/benchflow/src/benchflow/_utils/dataset_registry.py:142–150`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B7]

[B7]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/_utils/dataset_registry.py#L142-L150

- **S4**: `third_party/skillsbench/README.md:59–77`; v1.1; commit `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af`. [S4]

[S4]: https://github.com/benchflow-ai/skillsbench/blob/b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af/README.md#L59-L77

- **S5**: `third_party/skillsbench/website/src/content/docs/getting-started.mdx:69–86`; v1.1; commit `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af`. [S5]

[S5]: https://github.com/benchflow-ai/skillsbench/blob/b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af/website/src/content/docs/getting-started.mdx#L69-L86

- **B8**: `third_party/benchflow/docs/task-standard.md:50–91`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B8]

[B8]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/docs/task-standard.md#L50-L91

- **B9**: `third_party/benchflow/docs/task-standard.md:143–172`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B9]

[B9]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/docs/task-standard.md#L143-L172

- **B10**: `third_party/benchflow/src/benchflow/rollout/__init__.py:451–506`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B10]

[B10]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/rollout/__init__.py#L451-L506

- **B11**: `third_party/benchflow/src/benchflow/rollout/__init__.py:508–540`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B11]

[B11]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/rollout/__init__.py#L508-L540

- **B12**: `third_party/benchflow/src/benchflow/rollout/__init__.py:599–620`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B12]

[B12]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/rollout/__init__.py#L599-L620

- **B13**: `third_party/benchflow/src/benchflow/rollout/__init__.py:647–744`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B13]

[B13]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/rollout/__init__.py#L647-L744

- **B14**: `third_party/benchflow/src/benchflow/sandbox/lockdown.py:36–87`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B14]

[B14]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/sandbox/lockdown.py#L36-L87

- **B15**: `third_party/benchflow/src/benchflow/acp/runtime.py:360–413`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B15]

[B15]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/acp/runtime.py#L360-L413

- **B16**: `third_party/benchflow/src/benchflow/rollout/__init__.py:952–985`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B16]

[B16]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/rollout/__init__.py#L952-L985

- **A2**: `third_party/pi-acp/src/pi-rpc/process.ts:154–171`; 0.0.34 npm gitHead; supporting adapter upstream; commit `b0581c9c1d675e634234674484247008b03d69b4`. [A2]

[A2]: https://github.com/svkozak/pi-acp/blob/b0581c9c1d675e634234674484247008b03d69b4/src/pi-rpc/process.ts#L154-L171

- **B17**: `third_party/benchflow/src/benchflow/rollout/_setup.py:412–441`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B17]

[B17]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/rollout/_setup.py#L412-L441

- **B18**: `third_party/benchflow/src/benchflow/task/verifier_core.py:350–399`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B18]

[B18]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/task/verifier_core.py#L350-L399

- **B19**: `third_party/benchflow/src/benchflow/task/verifier_core.py:464–529`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B19]

[B19]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/task/verifier_core.py#L464-L529

- **B20**: `third_party/benchflow/src/benchflow/_utils/evaluation_results.py:59–100`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B20]

[B20]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/_utils/evaluation_results.py#L59-L100

- **B21**: `third_party/benchflow/src/benchflow/rollout/__init__.py:1315–1345`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B21]

[B21]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/rollout/__init__.py#L1315-L1345

- **B22**: `third_party/benchflow/src/benchflow/rollout/_setup.py:330–367`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B22]

[B22]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/rollout/_setup.py#L330-L367

- **S6**: `third_party/skillsbench/experiments/README.md:14–28`; v1.1; commit `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af`. [S6]

[S6]: https://github.com/benchflow-ai/skillsbench/blob/b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af/experiments/README.md#L14-L28

- **S7**: `third_party/skillsbench/experiments/sanity-tasks/hello-world/verifier/test.sh:1–19`; v1.1; commit `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af`. [S7]

[S7]: https://github.com/benchflow-ai/skillsbench/blob/b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af/experiments/sanity-tasks/hello-world/verifier/test.sh#L1-L19

- **B23**: `third_party/benchflow/src/benchflow/task/verifier_core.py:118–169`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B23]

[B23]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/task/verifier_core.py#L118-L169

- **B24**: `third_party/benchflow/src/benchflow/task/verifier_core.py:496–529`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B24]

[B24]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/task/verifier_core.py#L496-L529

- **B25**: `third_party/benchflow/src/benchflow/_utils/scoring.py:194–227`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B25]

[B25]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/_utils/scoring.py#L194-L227

- **B26**: `third_party/benchflow/src/benchflow/_utils/scoring.py:286–315`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B26]

[B26]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/_utils/scoring.py#L286-L315

- **B27**: `third_party/benchflow/src/benchflow/usage_tracking.py:9–17`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B27]

[B27]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/usage_tracking.py#L9-L17

- **P2**: `third_party/pi-mono/packages/coding-agent/docs/rpc.md:24–33`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P2]

[P2]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/rpc.md#L24-L33

- **B28**: `third_party/benchflow/docs/reference/cli.md:224–247`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B28]

[B28]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/docs/reference/cli.md#L224-L247

- **B29**: `third_party/benchflow/src/benchflow/rollout/_config.py:119–137`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B29]

[B29]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/rollout/_config.py#L119-L137

- **B30**: `third_party/benchflow/src/benchflow/skill_policy.py:111–177`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B30]

[B30]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/skill_policy.py#L111-L177

- **B31**: `third_party/benchflow/src/benchflow/skill_policy.py:180–214`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B31]

[B31]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/skill_policy.py#L180-L214

- **B32**: `third_party/benchflow/src/benchflow/rollout/__init__.py:508–538`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B32]

[B32]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/rollout/__init__.py#L508-L538

- **B33**: `third_party/benchflow/src/benchflow/agents/registry.py:366–369`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B33]

[B33]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/agents/registry.py#L366-L369

- **P3**: `third_party/pi-mono/packages/coding-agent/docs/skills.md:57–65`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P3]

[P3]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/skills.md#L57-L65

- **P4**: `third_party/pi-mono/packages/coding-agent/docs/skills.md:41–61`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P4]

[P4]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/skills.md#L41-L61

- **B34**: `third_party/benchflow/src/benchflow/rollout/_setup.py:161–165`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B34]

[B34]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/rollout/_setup.py#L161-L165

- **B35**: `third_party/benchflow/docs/reference/cli.md:250–253`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B35]

[B35]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/docs/reference/cli.md#L250-L253

- **B36**: `third_party/benchflow/src/benchflow/rollout/_config.py:128–137`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B36]

[B36]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/rollout/_config.py#L128-L137

- **B37**: `third_party/benchflow/src/benchflow/agents/registry.py:808–818`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B37]

[B37]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/agents/registry.py#L808-L818

- **B38**: `third_party/benchflow/src/benchflow/agents/pi_acp_launcher.py:48–144`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B38]

[B38]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/agents/pi_acp_launcher.py#L48-L144

- **A3**: `third_party/pi-acp/README.md:1–11`; 0.0.34 npm gitHead; supporting adapter upstream; commit `b0581c9c1d675e634234674484247008b03d69b4`. [A3]

[A3]: https://github.com/svkozak/pi-acp/blob/b0581c9c1d675e634234674484247008b03d69b4/README.md#L1-L11

- **P5**: `third_party/pi-mono/packages/coding-agent/docs/rpc.md:22–56`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P5]

[P5]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/rpc.md#L22-L56

- **A4**: `third_party/pi-acp/README.md:7–11`; 0.0.34 npm gitHead; supporting adapter upstream; commit `b0581c9c1d675e634234674484247008b03d69b4`. [A4]

[A4]: https://github.com/svkozak/pi-acp/blob/b0581c9c1d675e634234674484247008b03d69b4/README.md#L7-L11

- **A5**: `third_party/pi-acp/README.md:36–46`; 0.0.34 npm gitHead; supporting adapter upstream; commit `b0581c9c1d675e634234674484247008b03d69b4`. [A5]

[A5]: https://github.com/svkozak/pi-acp/blob/b0581c9c1d675e634234674484247008b03d69b4/README.md#L36-L46

- **A6**: `third_party/pi-acp/src/acp/session.ts:892–907`; 0.0.34 npm gitHead; supporting adapter upstream; commit `b0581c9c1d675e634234674484247008b03d69b4`. [A6]

[A6]: https://github.com/svkozak/pi-acp/blob/b0581c9c1d675e634234674484247008b03d69b4/src/acp/session.ts#L892-L907

- **A7**: `third_party/pi-acp/src/acp/agent.ts:893–900`; 0.0.34 npm gitHead; supporting adapter upstream; commit `b0581c9c1d675e634234674484247008b03d69b4`. [A7]

[A7]: https://github.com/svkozak/pi-acp/blob/b0581c9c1d675e634234674484247008b03d69b4/src/acp/agent.ts#L893-L900

- **P6**: `third_party/pi-mono/packages/coding-agent/docs/rpc.md:58–71`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P6]

[P6]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/rpc.md#L58-L71

- **B39**: `third_party/benchflow/src/benchflow/agents/registry.py:258–319`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B39]

[B39]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/agents/registry.py#L258-L319

- **A8**: `third_party/pi-acp/src/acp/agent.ts:60–61`; 0.0.34 npm gitHead; supporting adapter upstream; commit `b0581c9c1d675e634234674484247008b03d69b4`. [A8]

[A8]: https://github.com/svkozak/pi-acp/blob/b0581c9c1d675e634234674484247008b03d69b4/src/acp/agent.ts#L60-L61

- **A9**: `third_party/pi-acp/src/acp/agent.ts:1153–1200`; 0.0.34 npm gitHead; supporting adapter upstream; commit `b0581c9c1d675e634234674484247008b03d69b4`. [A9]

[A9]: https://github.com/svkozak/pi-acp/blob/b0581c9c1d675e634234674484247008b03d69b4/src/acp/agent.ts#L1153-L1200

- **P7**: `third_party/pi-mono/packages/coding-agent/docs/rpc.md:22–71`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P7]

[P7]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/rpc.md#L22-L71

- **B40**: `third_party/benchflow/src/benchflow/agents/protocol.py:105–162`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B40]

[B40]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/agents/protocol.py#L105-L162

- **B41**: `third_party/benchflow/src/benchflow/agents/registry.py:258–268`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B41]

[B41]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/agents/registry.py#L258-L268

- **B42**: `third_party/benchflow/src/benchflow/agents/registry.py:163–187`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B42]

[B42]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/agents/registry.py#L163-L187

- **B43**: `third_party/benchflow/src/benchflow/agents/registry.py:366–378`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B43]

[B43]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/agents/registry.py#L366-L378

- **P8**: `third_party/pi-mono/packages/coding-agent/package.json:1–11`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P8]

[P8]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/package.json#L1-L11

- **B44**: `third_party/benchflow/src/benchflow/acp/runtime.py:399–413`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B44]

[B44]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/acp/runtime.py#L399-L413

- **A10**: `third_party/pi-acp/src/acp/agent.ts:1175–1200`; 0.0.34 npm gitHead; supporting adapter upstream; commit `b0581c9c1d675e634234674484247008b03d69b4`. [A10]

[A10]: https://github.com/svkozak/pi-acp/blob/b0581c9c1d675e634234674484247008b03d69b4/src/acp/agent.ts#L1175-L1200

- **B45**: `third_party/benchflow/src/benchflow/agents/pi_acp_launcher.py:18–38`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B45]

[B45]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/agents/pi_acp_launcher.py#L18-L38

- **B46**: `third_party/benchflow/src/benchflow/agents/pi_acp_launcher.py:48–117`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B46]

[B46]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/agents/pi_acp_launcher.py#L48-L117

- **A11**: `third_party/pi-acp/src/acp/pi-settings.ts:30–57`; 0.0.34 npm gitHead; supporting adapter upstream; commit `b0581c9c1d675e634234674484247008b03d69b4`. [A11]

[A11]: https://github.com/svkozak/pi-acp/blob/b0581c9c1d675e634234674484247008b03d69b4/src/acp/pi-settings.ts#L30-L57

- **P9**: `third_party/pi-mono/packages/coding-agent/docs/configuration.md:1–9`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P9]

[P9]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/configuration.md#L1-L9

- **P10**: `third_party/pi-mono/packages/coding-agent/package.json:95–97`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P10]

[P10]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/package.json#L95-L97

- **B47**: `third_party/benchflow/src/benchflow/agents/registry.py:103–159`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B47]

[B47]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/agents/registry.py#L103-L159

- **A12**: `third_party/pi-acp/package.json:25–27`; 0.0.34 npm gitHead; supporting adapter upstream; commit `b0581c9c1d675e634234674484247008b03d69b4`. [A12]

[A12]: https://github.com/svkozak/pi-acp/blob/b0581c9c1d675e634234674484247008b03d69b4/package.json#L25-L27

- **S8**: `third_party/skillsbench/experiments/scripts/run_benchflow_integration.py:365–396`; v1.1; commit `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af`. [S8]

[S8]: https://github.com/benchflow-ai/skillsbench/blob/b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af/experiments/scripts/run_benchflow_integration.py#L365-L396

- **S9**: `third_party/skillsbench/experiments/scripts/run_benchflow_integration.py:656–680`; v1.1; commit `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af`. [S9]

[S9]: https://github.com/benchflow-ai/skillsbench/blob/b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af/experiments/scripts/run_benchflow_integration.py#L656-L680

- **B48**: `third_party/benchflow/src/benchflow/usage_tracking.py:45–78`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B48]

[B48]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/usage_tracking.py#L45-L78

- **P11**: `third_party/pi-mono/packages/coding-agent/docs/compaction.md:153–165`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P11]

[P11]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/compaction.md#L153-L165

- **P12**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:21–23`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P12]

[P12]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L21-L23

- **B49**: `third_party/benchflow/src/benchflow/agents/registry.py:170–187`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B49]

[B49]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/agents/registry.py#L170-L187

- **B50**: `third_party/benchflow/src/benchflow/rollout/__init__.py:619–620`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B50]

[B50]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/rollout/__init__.py#L619-L620

- **B51**: `third_party/benchflow/src/benchflow/rollout/__init__.py:690–739`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B51]

[B51]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/rollout/__init__.py#L690-L739

- **A13**: `third_party/pi-acp/src/acp/agent.ts:280–290`; 0.0.34 npm gitHead; supporting adapter upstream; commit `b0581c9c1d675e634234674484247008b03d69b4`. [A13]

[A13]: https://github.com/svkozak/pi-acp/blob/b0581c9c1d675e634234674484247008b03d69b4/src/acp/agent.ts#L280-L290

- **P13**: `third_party/pi-mono/packages/coding-agent/docs/cli.md:194–217`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P13]

[P13]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/cli.md#L194-L217

- **P14**: `third_party/pi-mono/packages/coding-agent/docs/rpc.md:50–56`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P14]

[P14]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/rpc.md#L50-L56

- **B52**: `third_party/benchflow/src/benchflow/skill_policy.py:111–184`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B52]

[B52]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/skill_policy.py#L111-L184

- **P15**: `third_party/pi-mono/packages/coding-agent/docs/cli.md:200–215`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P15]

[P15]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/cli.md#L200-L215

- **P16**: `third_party/pi-mono/packages/coding-agent/docs/rpc-commands.md:155–192`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P16]

[P16]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/rpc-commands.md#L155-L192

- **P17**: `third_party/pi-mono/packages/coding-agent/docs/rpc-commands.md:526–561`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P17]

[P17]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/rpc-commands.md#L526-L561

- **B53**: `third_party/benchflow/src/benchflow/rollout/_config.py:160–168`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B53]

[B53]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/rollout/_config.py#L160-L168

- **B54**: `third_party/benchflow/docs/reference/cli.md:207–247`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B54]

[B54]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/docs/reference/cli.md#L207-L247

