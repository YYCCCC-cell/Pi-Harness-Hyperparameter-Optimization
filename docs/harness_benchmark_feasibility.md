# Harness–benchmark feasibility and recommended plan

Prepared 2026-10-25 (Asia/Singapore).

## Decision

**Proceed to a later, bounded integration-validation phase using BenchFlow's existing `pi-acp` adapter. Do not start hyperparameter experiments yet.** The source exposes both a supported Pi adapter and useful configuration-only knobs, but the exact Pi/adapter/runner combination has not been executed. The main blockers are unpinned npm bootstrap, the Pi package rename, provider translation, thinking-setting propagation, and complete telemetry. These are compatibility tasks for an external project runner; they do not yet justify modifying Pi or writing a new protocol adapter. [B1] [B2] [P1] [B3] [B4]

The study should ask: **with a fixed model and benchmark protocol, how do Pi's thinking and context-management settings affect task success, cost, and runtime?** Treat model changes, skill content changes, verifier feedback loops, and custom tools as separate studies. This framing is a proposed experimental design; it is not an upstream benchmark result.

## Collected evidence and status

| Item | Recorded result |
|---|---|
| Pi | `third_party/pi-mono`, commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`; manifest version 1.4.0, main snapshot rather than release-artifact identity |
| SkillsBench | `third_party/skillsbench`, tag `v1.1`, commit `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af` |
| BenchFlow | `third_party/benchflow`, tag `v0.6.3`, commit `99baefb602674bbd31139fd2f1a22c3ed45752f9` |
| Supporting pi-acp source | `third_party/pi-acp`, version 0.0.34, commit `b0581c9c1d675e634234674484247008b03d69b4` |
| Integrity | Detached shallow checkouts, clean source trees; 101/101 task-package digests match the downloaded official release manifest |
| Not done | Dependency installation, image builds, oracle runs, provider authentication tests, paid calls, solver trials, performance measurements |

The first five rows are local collection observations, recorded in [source_lock.json](sources/source_lock.json). The manifest's version/roster is backed by the [official v1.1 release, “What this release pins”](https://github.com/benchflow-ai/skillsbench/releases/tag/v1.1); the digest calculation follows the exact upstream function. [B5]

Read [Pi configuration analysis](pi_configuration_analysis.md) for the 72 documented setting rows plus model/CLI controls; read [SkillsBench integration analysis](skillsbench_integration_analysis.md) for execution, scoring, adapter contracts, and precise compatibility findings. Source references below use the same frozen revisions.

## Reproducible validation/test split

### Status and population

This is a **proposed project-specific holdout**, not an official SkillsBench train/test split. Its source population is exactly the 87 active entries in the v1.1 release manifest; all 14 `tasks-extra` entries remain excluded. Only framework/adapter code and `experiments/sanity-tasks/hello-world` were semantically inspected for this analysis. Active task bytes were mechanically hashed without displaying their prompts, oracle implementations, or verifier assertions. The source population and exclusions are saved with the manifest and lock evidence. [Official release, “What this release pins” / “Task list”](https://github.com/benchflow-ai/skillsbench/releases/tag/v1.1), [task manifest](sources/skillsbench-v1.1-task-manifest.json), [inspection record](sources/source_lock.json).

The generated proposal contains **28 validation tasks and 59 test tasks**. Smoke testing uses the separate hello-world package, which is not in either scored partition. Complete task IDs and group assignments are in [proposed_split.json](sources/proposed_split.json). Counts below are computed from that file and the official release metadata, not performance results.

| Category | Active | Validation | Test |
|---|---:|---:|---:|
| cybersecurity | 7 | 2 | 5 |
| finance-economics | 9 | 3 | 6 |
| industrial-physical-systems | 14 | 5 | 9 |
| mathematics-or-formal-reasoning | 8 | 2 | 6 |
| media-content-production | 5 | 3 | 2 |
| natural-science | 14 | 4 | 10 |
| office-white-collar | 14 | 4 | 10 |
| software-engineering | 16 | 5 | 11 |
| **Total** | **87** | **28** | **59** |

Difficulty composition is validation **1 easy / 17 medium / 10 hard**, test **5 easy / 36 medium / 18 hard**. Group integrity is favored over exact proportional difficulty balance; the small easy stratum is a limitation. These counts come from the saved manifest and proposed assignment. Do not rebalance using model scores.

### Deterministic assignment rule

The seed is the literal UTF-8 string:

```text
PE6203-SkillsBench-v1.1-split-2026-10-25-v1
```

1. Start only from `manifest.tasks` at the recorded manifest SHA-256. Sort/report task IDs lexically.
2. Group within category by identical `subcategory`, except task names beginning with `energy-`, `earthquake-`, `manufacturing-`, `pddl-`, or `fix-build-`, which share their explicit family key within that category. A task and all its repeats/skill conditions always stay in one group.
3. Within each category, order group IDs by `SHA256(seed + "\n" + group_id)`, with group ID as a collision tie-breaker. Group ID is `category + "/family:" + prefix` or `category + "/subcategory:" + subcategory`.
4. Among nonempty proper prefixes of that order, choose the prefix minimizing `abs(10 * validation_count - 3 * category_count)`. Break equal-distance ties by the smaller validation count. Assign that prefix to validation and the rest to test.
5. Freeze the resulting JSON and its SHA-256 before any solver run. Benchmark commit, manifest digest, grouping algorithm, and seed are included in the file. No runtime outcome contributes to the assignment.

This is the project-defined algorithm that generated the saved proposal. It uses only roster/taxonomy information. Before freezing it, perform a **metadata/provenance-only related-task review** for shared source datasets, repository variants, or task families missed by the name/subcategory rules. Merge such groups and regenerate using the same rule; record a new split version before any outcomes are observed. Do not inspect test answers to make this judgment. If the group audit remains incomplete, report that limitation instead of claiming all semantic near-duplicates have been ruled out.

Reproduction code (standard library only; shown for review, not a benchmark command):

```python
import hashlib, json
from collections import defaultdict
from pathlib import Path

root = Path('<project-root>')
manifest = json.loads((root / 'docs/sources/skillsbench-v1.1-task-manifest.json').read_text())
seed = 'PE6203-SkillsBench-v1.1-split-2026-10-25-v1'
prefixes = ('energy-', 'earthquake-', 'manufacturing-', 'pddl-', 'fix-build-')
groups = defaultdict(list)
for t in manifest['tasks']:
    prefix = next((p for p in prefixes if t['name'].startswith(p)), None)
    key = t['category'] + '/' + (
        'family:' + prefix if prefix else 'subcategory:' + t['subcategory'])
    groups[key].append(t['name'])
validation, test = [], []
for category in sorted({t['category'] for t in manifest['tasks']}):
    keys = sorted((k for k in groups if k.startswith(category + '/')),
                  key=lambda k: (hashlib.sha256((seed + '\n' + k).encode()).hexdigest(), k))
    n = sum(len(groups[k]) for k in keys)
    choices = []
    for i in range(1, len(keys)):
        v = sum(len(groups[k]) for k in keys[:i])
        choices.append((abs(10 * v - 3 * n), v, i))
    _, _, cut = min(choices)
    for i, k in enumerate(keys):
        (validation if i < cut else test).extend(groups[k])
assert not set(validation) & set(test)
assert len(validation) + len(test) == 87
assert sorted(validation) == json.loads((root / 'docs/sources/proposed_split.json').read_text())['validation']
```

### Leakage prevention protocol

These are proposed study rules, not claims that a public benchmark can become a private dataset.

- **Optimization boundary:** choose candidates, prompts, retry policy, model, skill condition, timeout budgets, exclusion policy, and metric on validation only. Freeze the selected configuration and analysis plan before revealing any test reward or trajectory.
- **No target feedback in solving:** preserve original prompts and verifiers; no test-oracle output, verifier source, test feedback, prior solution traces, or score-directed retry is supplied to Pi. Disable oracle access and extra verifier-driven loops. BenchFlow offers these features, which is why their settings must be explicit. [B6] [B7]
- **Separate state:** new sandbox, Pi session, writable home, scratch space, and candidate copy per trial. Never resume a validation session on a test task. No learned memory, cross-task scratch files, retrieval over prior jobs, or optimizer access to test trajectories. Pi supports persistent/resumed sessions and ancestor context discovery, so isolation must be deliberate. [P2] [P3]
- **Files and skills:** mount only a task's permitted environment and its own released skills for the with-skill treatment. Leave default oracle/verifier locks enabled and the solver non-root. No-skill trials must have no discoverable or readable skill copies, including those accidentally baked into images. [B8] [B9] [P4]
- **Holdout stewardship:** a separate evaluation script/operator may mechanically check test package integrity and environment health, but must not feed test solutions, output details, per-task scores, or rank changes back into tuning. Detailed test analysis happens after the final freeze; subsequent tuning requires a new holdout or explicit exploratory labeling.
- **Infrastructure decisions:** preregister how missing reward, timeout, OOM, dependency failure, and provider outage are handled. Apply the same criteria to all configurations. Do not drop hard tasks after seeing Pi fail. If a test environment is incompatible, record it in the denominator and report the limitation; changing the suite afterward is a new protocol.
- **Public-data limitation:** these rules prevent leakage from this project's optimization loop. They cannot prove the underlying model never saw public SkillsBench tasks during pretraining. Report that separate contamination uncertainty.

### Test protocol and statistics

Proposed primary optimization target: mean validation reward in the **with-skill** condition, with fixed per-task wall-clock limits and a predeclared API-spend ceiling. Select on reward, break ties by lower measured cost, then runtime, then deterministic configuration ID. Include the baseline in every finalist comparison. Do not optimize the scalar cost estimate by changing price metadata.

Once selection is frozen, evaluate **baseline and the selected configuration** on all 59 test tasks, in both with-skill and no-skill conditions, with the same three independently initialized repeats per cell if the budget permits. Report each condition separately, plus paired improvement and skill benefit. The two skill conditions must not straddle partitions. Three repeats and the selection rule are project choices; they are not an asserted official v1.1 replication count. Official documentation establishes explicit comparable with/no-skill runs on the same package. [S1]

Use per-task means so tasks have equal weight. Report reward and `reward==1` pass fraction, all scheduled trial counts, raw error categories, and cost/time distributions. For uncertainty, bootstrap paired differences over **task groups**, keeping repeats and paired conditions together; report the bootstrap seed and number of resamples. Do not treat repeated samples from one task as independent new tasks. Do not report best-of-three as pass@1. These are proposed analysis procedures; upstream canonical score classification and denominators are documented in source. [B10] [B11]

## Cost exposure and budget design

No numeric model-cost forecast is defensible yet: no model, provider, per-trial token distribution, or final trial budget has been chosen. Record the selected provider's official pricing/version at execution time. Pi's model metadata distinguishes input, output, cache-read, and cache-write prices per million tokens; those are estimates, not an invoice guarantee. [P5]

For one trial, use the accounting identity:

```text
LLM cost = sum over all calls of
  (uncached_input * input_rate
   + output * output_rate
   + cache_read * cache_read_rate
   + cache_write * cache_write_rate) / 1,000,000
Total study cost = solver calls + compaction/refresh/retry calls
                 + any task/verifier API calls + cloud compute/storage/egress
```

Count reasoning tokens according to the selected provider's billing definition and avoid double-counting cached tokens inside uncached input. Summary calls and cache warming are real additional work in Pi; agent retries and provider retries are distinct layers. Model pricing tiers can be request-wide. Use complete provider billing/usage logs when local estimates disagree. [P6] [P7] [P8] [P9] [P5]

| Potential charge | Trigger / evidence | Recommended control |
|---|---|---|
| Solver API | Agent runs require provider credentials | Choose one exact model/provider; create an explicit run budget before smoke testing. [S2] |
| Summaries and retries | Long contexts, transient failures, nested retry layers | Hold recovery policy fixed; log retry/compaction counts and cumulative usage. [P10] [P11] |
| Cache refresh | Pi defaults to streaming cache warming where eligible | Start with `cacheWarming=off` and report the deliberate baseline change. [P8] |
| Task / verifier APIs | Credential-dependent extras, or any package-specific script that invokes a service | Keep all 14 excluded tasks out; check declared external services before execution. An oracle has no coding-agent LLM call but can still run a resource-consuming script. [S3] [S4] [B12] |
| Modal | CPU, memory, GPU and other metered cloud resources | Use sandbox-specific pricing, not ordinary function CPU/RAM rates; kill jobs on failure and record lifetimes. [Modal pricing, “Modal Sandbox pricing” / “Resource costs”, accessed 2026-10-25](https://modal.com/pricing) |
| Missing cost telemetry | Auto mode cannot capture trusted usage | Fail validation of the measurement setup; never treat unavailable usage as zero cost. [B13] |

Modal's current pricing page states that sandbox CPU/memory use non-preemptible rates at 3× base list pricing; it also lists storage and network egress charges. These are current website terms, not a quote for this study or a claim about the user's credits. [Modal pricing, “Modal Sandbox pricing”, “Resource costs”, and FAQ](https://modal.com/pricing)

Illustrative staged allocation, **not authorization to spend**:

| Stage | Proposed allocation | Solver trials |
|---|---|---:|
| Screening | 12 candidate configurations × 8 validation tasks × 1 with-skill repeat | 96 |
| Finalist validation | Baseline + best 2 screened candidates × all 28 validation tasks × 3 with-skill repeats | 252 |
| Locked test | Baseline + selected winner × 59 test tasks × 2 skill conditions × 3 repeats | 708 |
| **Total** | Excludes integration smoke, oracle checks, infrastructure reruns | **1056** |

Select the screening task from each category by a fixed hash order **within validation only**; use the first eligible task, and record that eight-task list before screening. Finalist repeats above are fresh, so the arithmetic does not pretend screening calls are reused. If the winner equals baseline, the duplicate winner cell is unnecessary. Reduce candidate/repeat counts **before test exposure** if an initial approved pilot indicates this is unaffordable. The table is arithmetic based on proposed counts, not a recommended immediate full run.

A per-response `maxTokens` value is not a task-wide API cost cap: the agent can call the model repeatedly, summarize, and retry. Start at concurrency 1, set a study-level spending stop in the external runner/provider budget, include in-flight calls in the bound, and checkpoint outputs. A wall-clock timeout alone is not a dollar guarantee. This is an inference from per-call output caps and the multi-turn/recovery lifecycle. [P12] [P10] [B14]

## Docker, Modal, and compatibility requirements

| Area | Confirmed requirement or concern | Status / recommendation |
|---|---|---|
| Local Docker | BenchFlow checks the `docker` executable and daemon; Docker backend uses Compose | Installation/daemon/resources were not probed. Prefer a small Docker-first smoke test in a later authorized phase. [B15] [B16] |
| Modal | Backend checks `.modal.toml` or both `MODAL_TOKEN_ID`/`MODAL_TOKEN_SECRET`; optional extra includes modal>=0.73 and tenacity | A cloud account, credentials, and the appropriate installed extra are required later. No auth files or secret values were inspected. [B17] [B18] |
| Sandbox resources | Modal passes task CPU, memory, GPU and network settings to `Sandbox.create`; tasks carry their own resource/time configuration | Fix resource policy across candidates; do not treat a larger machine as a Pi hyperparameter. [B19] [S5] |
| Python | Both repositories require >=3.12; BenchFlow has optional backend extras | Existing Python being able to read files does not prove a supported installed BenchFlow environment. [S6] [B20] |
| Node | Pi >=22.19.0; BenchFlow's private Node bootstrap pins 22.20.0 | Pin runtime artifacts and verify the actual executable inside the sandbox. [P13] [B21] |
| Apple Silicon | Official guide notes slower builds and possible numerical differences in native libraries | Host architecture was not assumed. If using ARM locally, record platform and avoid silently mixing it with cloud x86 results. [S7] |
| Build reproducibility | Some task builds compile large ML dependencies and can exceed ten minutes; source pins do not by themselves pin external image tags/downloads | Record base-image digests, actual resolved dependencies, network artifacts, and build logs. Use the same built artifact for paired comparisons where skill isolation allows. [S8] |
| Security / verification | Default hardening depends on a non-root solver and trusted task images/verifiers; known gaps remain | Preserve hardening, inspect only authorized inputs in solver context, and audit final traces. Do not claim perfect reward-hack prevention. [B22] [B23] |
| Model/provider | BenchFlow's Pi launcher has limited protocol branches and fallback capability metadata | Verify one route before exploring providers; don't change provider alongside Pi settings. [B4] |
| Tool / skill discovery | Pi loads user/project/ancestor resources; empty configured arrays are not a complete isolation policy | Fresh HOME and explicit launch/discovery policy per trial. [P3] [P14] |

Docker and Modal are alternative execution backends, not two mandatory accounts/services for every run. The live SkillsBench guide recommends Modal as its cloud default; the frozen v1.1 website source and release examples use Docker. Pin the backend used for the experiment and report any backend exclusions rather than presenting cross-backend runs as identical. [Live getting-started guide, “Prerequisites” / “Run One Task”](https://www.skillsbench.ai/docs/getting-started), [S9]

## Integration validation gates and next deliverables

These gates are a recommended plan only. Nothing in this document schedules or starts them.

1. **Artifact and protocol gate:** freeze exact runtime versions and candidate schema; implement the external bootstrap/wrapper described in the integration document. Confirm no registry `@latest` install occurs. No third-party source patch.
2. **Credential-free gate:** validate candidate files and task structure; exercise ACP/RPC initialization, model/thinking option propagation, prompt completion, cancellation, and error recording using synthetic fixtures/fake provider responses. Verify that `agent_settled` terminates a trial and errors are not mislabelled as success. The relevant protocol and adapter behavior are explicit in source. [P15] [A1] [A2]
3. **Container gate:** after dependency/image setup authorization, run the separate hello-world oracle and a no-skill isolation check; confirm verifier reward parsing, protected paths, task source hashes, and cleanup. This can consume compute even without an LLM. [S10] [S11]
4. **Bounded paid smoke gate:** only after a model and cost limit are agreed, run one short solver task. Verify actual model, thinking, tool selection, usage/cost, cancellation, and with/no-skill separation. No broad sweep until this evidence is complete.
5. **Validation-only gate:** freeze the split after metadata grouping review, candidate set, schedule, selection rule, and operational error policy. Run screening and finalist validation. No test scores enter selection.
6. **Final test gate:** seal configuration and analysis hashes, run the locked test matrix once, preserve all outcomes and costs, and report uncertainty and compatibility limitations. Any subsequent tuning is exploratory and cannot reuse this holdout as if untouched.

Recommended future project artifacts: `configs/` for immutable candidates and runtime locks; `integration/` for the external bootstrap/Pi wrapper; `splits/` for the approved split; `runs/` for manifests and raw results; and an analysis script that aggregates paired task-level outcomes. These are proposed locations, not files created or code implemented in this phase.

## Scope completed and stopping point

Completed: official source collection; exact source pins; release-manifest integrity checks; Pi parameter/schema analysis; benchmark execution/scoring/interface inspection; adapter feasibility assessment; a deterministic split proposal; and this integration/cost plan. No third-party source was changed. No dependency installer or benchmark runner was executed. No paid experiment or measurement is claimed.

## Source index

All repository citations below are immutable links to the exact inspected commit. Line numbers refer to that checkout, not moving `main`. `P` = Pi, `S` = SkillsBench, `B` = BenchFlow, `A` = the upstream pi-acp adapter.

- **B1**: `third_party/benchflow/src/benchflow/agents/registry.py:163–187`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B1]

[B1]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/agents/registry.py#L163-L187

- **B2**: `third_party/benchflow/src/benchflow/agents/registry.py:366–389`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B2]

[B2]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/agents/registry.py#L366-L389

- **P1**: `third_party/pi-mono/packages/coding-agent/package.json:1–11`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P1]

[P1]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/package.json#L1-L11

- **B3**: `third_party/benchflow/src/benchflow/acp/runtime.py:399–413`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B3]

[B3]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/acp/runtime.py#L399-L413

- **B4**: `third_party/benchflow/src/benchflow/agents/pi_acp_launcher.py:48–117`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B4]

[B4]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/agents/pi_acp_launcher.py#L48-L117

- **B5**: `third_party/benchflow/src/benchflow/_utils/task_authoring/__init__.py:114–141`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B5]

[B5]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/_utils/task_authoring/__init__.py#L114-L141

- **B6**: `third_party/benchflow/src/benchflow/rollout/_config.py:128–137`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B6]

[B6]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/rollout/_config.py#L128-L137

- **B7**: `third_party/benchflow/docs/reference/cli.md:247–247`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B7]

[B7]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/docs/reference/cli.md#L247

- **P2**: `third_party/pi-mono/packages/coding-agent/docs/cli.md:78–107`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P2]

[P2]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/cli.md#L78-L107

- **P3**: `third_party/pi-mono/packages/coding-agent/docs/configuration.md:41–47`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P3]

[P3]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/configuration.md#L41-L47

- **B8**: `third_party/benchflow/src/benchflow/skill_policy.py:111–184`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B8]

[B8]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/skill_policy.py#L111-L184

- **B9**: `third_party/benchflow/src/benchflow/sandbox/lockdown.py:36–87`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B9]

[B9]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/sandbox/lockdown.py#L36-L87

- **P4**: `third_party/pi-mono/packages/coding-agent/docs/skills.md:57–65`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P4]

[P4]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/skills.md#L57-L65

- **S1**: `third_party/skillsbench/website/src/content/docs/getting-started.mdx:29–50`; v1.1; commit `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af`. [S1]

[S1]: https://github.com/benchflow-ai/skillsbench/blob/b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af/website/src/content/docs/getting-started.mdx#L29-L50

- **B10**: `third_party/benchflow/src/benchflow/_utils/scoring.py:194–227`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B10]

[B10]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/_utils/scoring.py#L194-L227

- **B11**: `third_party/benchflow/src/benchflow/_utils/scoring.py:307–315`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B11]

[B11]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/_utils/scoring.py#L307-L315

- **P5**: `third_party/pi-mono/packages/coding-agent/docs/models-configuration.md:40–50`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P5]

[P5]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/models-configuration.md#L40-L50

- **P6**: `third_party/pi-mono/packages/coding-agent/docs/compaction.md:43–49`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P6]

[P6]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/compaction.md#L43-L49

- **P7**: `third_party/pi-mono/packages/coding-agent/docs/compaction.md:153–165`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P7]

[P7]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/compaction.md#L153-L165

- **P8**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:21–23`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P8]

[P8]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L21-L23

- **P9**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:120–136`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P9]

[P9]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L120-L136

- **S2**: `third_party/skillsbench/README.md:53–57`; v1.1; commit `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af`. [S2]

[S2]: https://github.com/benchflow-ai/skillsbench/blob/b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af/README.md#L53-L57

- **P10**: `third_party/pi-mono/packages/coding-agent/docs/compaction.md:27–49`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P10]

[P10]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/compaction.md#L27-L49

- **P11**: `third_party/pi-mono/packages/coding-agent/docs/settings.md:128–136`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P11]

[P11]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L128-L136

- **S3**: `third_party/skillsbench/README.md:41–44`; v1.1; commit `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af`. [S3]

[S3]: https://github.com/benchflow-ai/skillsbench/blob/b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af/README.md#L41-L44

- **S4**: `third_party/skillsbench/website/src/content/docs/getting-started.mdx:88–104`; v1.1; commit `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af`. [S4]

[S4]: https://github.com/benchflow-ai/skillsbench/blob/b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af/website/src/content/docs/getting-started.mdx#L88-L104

- **B12**: `third_party/benchflow/src/benchflow/rollout/_setup.py:330–367`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B12]

[B12]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/rollout/_setup.py#L330-L367

- **B13**: `third_party/benchflow/src/benchflow/usage_tracking.py:45–78`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B13]

[B13]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/usage_tracking.py#L45-L78

- **P12**: `third_party/pi-mono/packages/ai/src/api/simple-options.ts:36–64`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P12]

[P12]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/ai/src/api/simple-options.ts#L36-L64

- **B14**: `third_party/benchflow/src/benchflow/rollout/_config.py:119–125`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B14]

[B14]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/rollout/_config.py#L119-L125

- **B15**: `third_party/benchflow/src/benchflow/sandbox/docker.py:1–3`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B15]

[B15]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/sandbox/docker.py#L1-L3

- **B16**: `third_party/benchflow/src/benchflow/sandbox/docker.py:130–147`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B16]

[B16]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/sandbox/docker.py#L130-L147

- **B17**: `third_party/benchflow/src/benchflow/sandbox/modal_impl.py:22–34`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B17]

[B17]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/sandbox/modal_impl.py#L22-L34

- **B18**: `third_party/benchflow/pyproject.toml:58–61`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B18]

[B18]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/pyproject.toml#L58-L61

- **B19**: `third_party/benchflow/src/benchflow/sandbox/modal_impl.py:92–112`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B19]

[B19]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/sandbox/modal_impl.py#L92-L112

- **S5**: `third_party/skillsbench/website/src/content/docs/getting-started.mdx:84–86`; v1.1; commit `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af`. [S5]

[S5]: https://github.com/benchflow-ai/skillsbench/blob/b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af/website/src/content/docs/getting-started.mdx#L84-L86

- **S6**: `third_party/skillsbench/pyproject.toml:1–9`; v1.1; commit `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af`. [S6]

[S6]: https://github.com/benchflow-ai/skillsbench/blob/b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af/pyproject.toml#L1-L9

- **B20**: `third_party/benchflow/pyproject.toml:1–20`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B20]

[B20]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/pyproject.toml#L1-L20

- **P13**: `third_party/pi-mono/packages/coding-agent/package.json:95–97`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P13]

[P13]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/package.json#L95-L97

- **B21**: `third_party/benchflow/src/benchflow/agents/registry.py:103–159`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B21]

[B21]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/agents/registry.py#L103-L159

- **S7**: `third_party/skillsbench/website/src/content/docs/getting-started.mdx:122–126`; v1.1; commit `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af`. [S7]

[S7]: https://github.com/benchflow-ai/skillsbench/blob/b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af/website/src/content/docs/getting-started.mdx#L122-L126

- **S8**: `third_party/skillsbench/website/src/content/docs/getting-started.mdx:108–120`; v1.1; commit `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af`. [S8]

[S8]: https://github.com/benchflow-ai/skillsbench/blob/b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af/website/src/content/docs/getting-started.mdx#L108-L120

- **B22**: `third_party/benchflow/docs/sandbox-hardening.md:10–23`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B22]

[B22]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/docs/sandbox-hardening.md#L10-L23

- **B23**: `third_party/benchflow/docs/sandbox-hardening.md:44–53`; v0.6.3; commit `99baefb602674bbd31139fd2f1a22c3ed45752f9`. [B23]

[B23]: https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/docs/sandbox-hardening.md#L44-L53

- **P14**: `third_party/pi-mono/packages/coding-agent/docs/cli.md:194–217`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P14]

[P14]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/cli.md#L194-L217

- **S9**: `third_party/skillsbench/website/src/content/docs/getting-started.mdx:10–45`; v1.1; commit `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af`. [S9]

[S9]: https://github.com/benchflow-ai/skillsbench/blob/b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af/website/src/content/docs/getting-started.mdx#L10-L45

- **P15**: `third_party/pi-mono/packages/coding-agent/docs/rpc.md:58–71`; main snapshot; package version 1.4.0, not the v1.4.0 release commit; commit `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`. [P15]

[P15]: https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/rpc.md#L58-L71

- **A1**: `third_party/pi-acp/src/acp/session.ts:892–907`; 0.0.34 npm gitHead; supporting adapter upstream; commit `b0581c9c1d675e634234674484247008b03d69b4`. [A1]

[A1]: https://github.com/svkozak/pi-acp/blob/b0581c9c1d675e634234674484247008b03d69b4/src/acp/session.ts#L892-L907

- **A2**: `third_party/pi-acp/src/acp/agent.ts:893–900`; 0.0.34 npm gitHead; supporting adapter upstream; commit `b0581c9c1d675e634234674484247008b03d69b4`. [A2]

[A2]: https://github.com/svkozak/pi-acp/blob/b0581c9c1d675e634234674484247008b03d69b4/src/acp/agent.ts#L893-L900

- **S10**: `third_party/skillsbench/experiments/README.md:14–28`; v1.1; commit `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af`. [S10]

[S10]: https://github.com/benchflow-ai/skillsbench/blob/b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af/experiments/README.md#L14-L28

- **S11**: `third_party/skillsbench/experiments/sanity-tasks/hello-world/verifier/test.sh:1–19`; v1.1; commit `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af`. [S11]

[S11]: https://github.com/benchflow-ai/skillsbench/blob/b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af/experiments/sanity-tasks/hello-world/verifier/test.sh#L1-L19

