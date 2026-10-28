# PE6203 harness hyperparameter optimization research proposal

Prepared 2026-10-25. **Proposal for decision, not an approved implementation or an experimental result.**

The provisional recommendation is **one fixed Pi runtime, one fixed model, SkillsBench 1.1, and a small interaction-guided coordinate search**, compared with untuned Default, Random Search and standard Bayesian Optimization. Pi with Terminal-Bench 4.0 is a credible alternative with an existing current Harbor adapter. The final choice should depend on a bounded integration and cost pilot, authorized separately. A five-day project should implement one developed method, preserve a sealed test set, and prioritize trustworthy costs and outcomes over a large search or multiple benchmarks.

## Evidence categories and scope

This proposal distinguishes four kinds of statement:

- **Assignment facts:** requirements extracted from the supplied Word document, with paragraph references in the [32-item checklist](assignment_requirements_checklist.md).
- **Paper facts:** findings from the six supplied, accessible PDFs, with versions, pages, limitations and code-access status in the [literature review](literature_review.md).
- **Documentation facts:** interfaces verified in pinned source or current official documentation. Exact versions and source locations accompany the claims below and in the [Pi parameter inventory](pi_parameter_research_inventory.md).
- **Recommendations and assumptions:** our proposed algorithms, search values, budgets, comparisons and schedule. These have not been tested and are not prescribed by the instructor or upstream projects.

The requested `docs/assignment.docx` and `docs/papers/` paths do not exist. Their supplied counterparts are the root-level assignment（本地或历史材料，未打包：`../PE6203 Group Project 3 - Harness Hyperparameter Optimization.docx`） and the six PDFs in `参考论文/`. Originals remain unchanged; local_materials.json（本地或历史材料，未打包：`sources/research/local_materials.json`） records hashes and exact paths. All six papers were accessible. Research code availability is described individually in the literature review; no inaccessible guessed URL is treated as evidence that a project does not exist.

## A Assignment requirements and implications

**Assignment facts.** Choose one harness and optimize only its supported configuration surface while holding its implementation fixed. Compare at least one student-developed method with Default, Random Search and standard surrogate-based BO on the same space and evaluation budget, with comparable information. Use validation feedback for search and evaluate each selected configuration once on held-out tasks. Specify domains, budget, stopping and failure policies before final evaluation. Assignment P017–P023（本地或历史材料，未打包：`sources/research/assignment_extracted.txt#L17`）, P044–P047（本地或历史材料，未打包：`sources/research/assignment_extracted.txt#L44`）, P052（本地或历史材料，未打包：`sources/research/assignment_extracted.txt#L52`）.

Required outputs include final test pass@1, separate validation scores, search and runtime USD costs, cost-indexed incumbent curves, generalization gaps, parameter sensitivity, and both directions of tuned-versus-default failure cases. Deliver code and report through GitHub and give a 10-minute presentation plus 5-minute Q&A. P028–P030（本地或历史材料，未打包：`sources/research/assignment_extracted.txt#L28`）, P038–P064（本地或历史材料，未打包：`sources/research/assignment_extracted.txt#L38`）.

The [complete checklist](assignment_requirements_checklist.md) maps every requirement to proposed acceptance evidence. Its planned statuses do not assert that the HPO pipeline, report results or presentation already exist.

### Changes from Step 0

Step 0's three reports were reviewed before this proposal, and all four checkouts still match [source_lock.json](sources/source_lock.json). Their source analyses remain useful, but the assignment requires these design changes:

| Step 0 proposal | Revised recommendation | Reason |
|---|---|---|
| Cache warming disabled in an experimental baseline | Preserve native performance defaults in the primary Default baseline | Untuned Default is explicitly required; cache-off is a separate variant |
| Default plus one final winner | Default plus a winner from **each** search method | Required method-by-method held-out comparison |
| Three test repeats and two skill conditions | One primary attempt per task, one fixed skill condition | Matches the required single-configuration pass@1 and reduces optional scope |
| Mean reward as primary selection target | Validation pass fraction as primary; partial reward secondary | Aligns search with course pass@1 |
| 28/59 split already generated | Retain as a proposal, audit related-task groups, then freeze | Grouping and feasibility remain unverified |

The assignment does not forbid a preregistered stochastic robustness study, but such repeats must be separately budgeted, never used for test-guided selection, and never reported as best-of-k pass@1. No such study is included in the minimal plan.

## B Literature synthesis

**Paper evidence**, summarized from the [six-paper review](literature_review.md):

| Work | Relevant contribution | Boundary for this project |
|---|---|---|
| Harness-Bench v2 | Paired model–harness evaluation, artifact verification, full success versus partial credit, complete API accounting | Cross-harness variation does not prove individual Pi parameter effects; Pi is absent from its seven-harness grid |
| Finding the Right Fit v1 | Pi/Harbor evaluation and model–task-dependent harness effects | Uses Pi 0.84.4 and a 63-task TB4 subset; settings are not uniformly matched and one run is counted per task |
| HarnessOpt-Bench v1 | Protected holdout, immutable candidates, metered evaluation and validation optimism | Optimizes harness **code**, which our course forbids; normalized gain is not the required pass@1 |
| SMAC3, JMLR 2022 | Established surrogate-based baseline for structured configuration spaces | Its agent-benchmark performance and modern dependency compatibility are not established by the paper |
| Hutter et al., ICML 2014 | fANOVA separates modeled main effects and interactions | Sparse adaptive logs and poor surrogates can make importance unreliable; it is not causal proof |
| Hyperband, JMLR 2018 | Successive halving and bracketed resource allocation | Partial task panels can misrank settings; shortening an agent trajectory changes the task budget |

The proposed research question is: **Can explicit local parameter-interaction measurements improve configuration selection under the same evaluation budget as Random Search and BO, while retaining performance on held-out tasks?** This is a hypothesis. A null result is acceptable if the comparison and failure analysis are sound.

The Harness-Bench abstract landing page and its versioned v2 PDF disagree on task counts. The review uses the supplied and official **v2 PDF**, which both state 300 tasks; it does not combine that version with the landing page's 106-task description. [Versioned PDF §3.2–4.1, pp.4–5](https://arxiv.org/pdf/2605.27922v2).

## C Harness and benchmark combinations

### What is verified

The reused repositories remain pinned as follows. These are source identities, not installed runtime identities.

| Component | Exact revision | Local status |
|---|---|---|
| Pi | `f321e5bdd26b3624bfb2ab182a334d0a5edb698a` | Main snapshot; package manifest 1.4.0; not asserted to equal the published 1.4.0 package |
| SkillsBench | v1.1, `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af` | 87 active tasks, 14 excluded; Step 0 verified all 101 package hashes |
| BenchFlow | v0.6.3, `99baefb602674bbd31139fd2f1a22c3ed45752f9` | Source includes `pi-acp`, `claude-agent-acp` and `codex-acp` |
| pi-acp | 0.0.34 npm gitHead, `b0581c9c1d675e634234674484247008b03d69b4` | Supporting adapter source only; no runtime test |

Evidence: [source lock](sources/source_lock.json), [SkillsBench v1.1 release](https://github.com/benchflow-ai/skillsbench/releases/tag/v1.1), [BenchFlow registry](https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/agents/registry.py#L324-L437).

Additional remote source was inspected and saved under `docs/sources/research/`, without cloning replacements or changing `third_party/`:

- Harbor snapshot `6099b8cf2bfbbb3e7ff1eb2163bfc4524dbd9ba5` declares package version 0.24.0 and Python ≥3.12. Its Pi adapter exposes `reasoning_effort` with `thinking` as an alias and emits Pi's `--thinking` option. It selects the renamed Pi npm package and supports an explicit install version; omission still falls back to `@latest`. [Harbor pyproject:1–9](https://github.com/harbor-framework/harbor/blob/6099b8cf2bfbbb3e7ff1eb2163bfc4524dbd9ba5/pyproject.toml#L1-L9), [Pi options:74–119](https://github.com/harbor-framework/harbor/blob/6099b8cf2bfbbb3e7ff1eb2163bfc4524dbd9ba5/src/harbor/agents/installed/pi.py#L74-L119), [install:178–244](https://github.com/harbor-framework/harbor/blob/6099b8cf2bfbbb3e7ff1eb2163bfc4524dbd9ba5/src/harbor/agents/installed/pi.py#L178-L244).
- Terminal-Bench **v4.0.0** resolves to `452bf305c6daa62fc59061d22133a7cbc7c1572e`. Its pinned `tasks/` directory contains **66 task directories**; this count was obtained from repository metadata without opening task solutions. The official release uses Harbor, and the official resource policy gives tasks an eight-hour agent timeout. [Tag](https://api.github.com/repos/harbor-framework/terminal-bench/git/ref/tags/v4.0.0), [pinned roster](https://github.com/harbor-framework/terminal-bench/tree/452bf305c6daa62fc59061d22133a7cbc7c1572e/tasks), [release resource policy](https://www.tbench.ai/news/terminal-bench-4-0).
- The older `badlogic/pi-terminal-bench` adapter exists, but its README targets TB2.0 and asks for a Harbor patch. It should not be treated as the current TB4 integration path. [README at `0074c915dc7d8ceeba5f61b19e7b9aa078564fa3`, Required Apply Harbor Fix](https://github.com/badlogic/pi-terminal-bench/blob/0074c915dc7d8ceeba5f61b19e7b9aa078564fa3/README.md#L18-L61), [TB2.0 commands:119–150](https://github.com/badlogic/pi-terminal-bench/blob/0074c915dc7d8ceeba5f61b19e7b9aa078564fa3/README.md#L119-L150). Do not apply that old patch.

### Comparison matrix

**Documentation facts and our complexity assessment.** “Existing adapter” means code is present in the inspected version, not that our selected model/runtime has passed an end-to-end trial. Complexity labels are engineering estimates for this five-day project.

| Harness | SkillsBench 1.1 | Terminal-Bench 4.0 | AppWorld |
|---|---|---|---|
| Pi | Existing BenchFlow `pi-acp`; moderate bootstrap/provider/settings work, with Step 0 already completed | Current Harbor Pi adapter; moderate settings-path and version validation, potentially long tasks | Official AppWorld MCP/API interface offers a possible route, but this exact combination was not verified; higher integration uncertainty |
| Claude Code | Existing BenchFlow `claude-agent-acp`; separate exposed-space and billing audit still needed | Current Harbor `ClaudeCode` adapter exists; separate configuration audit needed | No end-to-end combination verified in this review |
| Codex | Existing BenchFlow `codex-acp`; separate exposed-space and billing audit still needed | Current Harbor `Codex` adapter exists; separate configuration audit needed | No end-to-end combination verified in this review |
| Deer-Flow 2.0 | No DeerFlow entry found in the complete pinned BenchFlow v0.6.3 registry; additional integration investigation required | Current Harbor `DeerFlow` adapter exists, with a bundled client runner and sandbox bridge; broader integration boundary | No end-to-end combination verified in this review |

Evidence: [BenchFlow registry and aliases](https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/agents/registry.py#L324-L437), [Harbor Codex:119](https://github.com/harbor-framework/harbor/blob/6099b8cf2bfbbb3e7ff1eb2163bfc4524dbd9ba5/src/harbor/agents/installed/codex.py#L119), [Harbor ClaudeCode:118](https://github.com/harbor-framework/harbor/blob/6099b8cf2bfbbb3e7ff1eb2163bfc4524dbd9ba5/src/harbor/agents/installed/claude_code.py#L118), [Harbor DeerFlow:102–121](https://github.com/harbor-framework/harbor/blob/6099b8cf2bfbbb3e7ff1eb2163bfc4524dbd9ba5/src/harbor/agents/installed/deerflow.py#L102-L121), [AppWorld MCP section](https://github.com/StonyBrookNLP/appworld/blob/42b5bcf3cd334fee33f0c37c02070a9f5807add5/README.md#L1117-L1125). Presence of a current DeerFlow adapter does not establish which exact Deer-Flow 2.0 release should be selected.

| Benchmark | Strength for the course | Main drawback or boundary |
|---|---|---|
| SkillsBench 1.1 | Released task manifest, outcome verifiers, native BenchFlow task format, existing Pi adapter; prior integrity work is reusable | Many task-specific dependencies; skill mode must be fixed; custom grouped split required for this project |
| Terminal-Bench 4.0 | Current maintained Pi/Harbor path and existing research precedent | Native eight-hour allowance, substantial resource variability; a shorter timeout or CPU-only subset is a modified protocol and must be labelled |
| AppWorld | Official train/dev/test-normal/test-challenge roles and controllable API environment | Additional tool/environment integration; official test rules prohibit task-wise test error analysis, so required failure-case analysis must use train/dev |

Sources: [SkillsBench v1.1 README:21–77](https://github.com/benchflow-ai/skillsbench/blob/b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af/README.md#L21-L77), [TB4 official release](https://www.tbench.ai/news/terminal-bench-4-0), [AppWorld benchmark-use rules:939–950](https://github.com/StonyBrookNLP/appworld/blob/42b5bcf3cd334fee33f0c37c02070a9f5807add5/README.md#L939-L950).

### Recommended integration choice

**Recommendation:** retain Pi + SkillsBench 1.1 provisionally, with a one-day integration gate and Pi + TB4/Harbor as the fallback. This is a practical choice based on reusable evidence and bounded scope, not evidence that SkillsBench is easier, cheaper, or statistically better. No measured cost or runtime comparison between these routes exists here.

For SkillsBench, reuse `pi-acp` and an external bootstrap/configuration wrapper; no new protocol adapter is presently justified. Resolve floating npm versions, the Pi package rename, provider routing, effective thinking and telemetry before search. BenchFlow v0.6.3's Pi registry omits an ACP effort option, so its `--reasoning-effort` route cannot be assumed to set Pi thinking. [Registry:366–389](https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/agents/registry.py#L366-L389), [ACP effort handling:399–413](https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/acp/runtime.py#L399-L413), [provider translation:48–117](https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/agents/pi_acp_launcher.py#L48-L117).

For Harbor, explicit thinking support is helpful, but compaction candidates still need delivery to the actual Pi settings directory. Custom endpoints or MCP activate `PI_CODING_AGENT_DIR=/tmp/harbor-pi-agent`; a file written only to `~/.pi/agent` can then be ignored. Its MCP adapter currently enforces Pi `>=0.84.1,<0.86.0`, which excludes the Step 0 snapshot's manifest 1.4.0; avoid MCP in the minimal TB4 route. Leave `max_turns` unset: Harbor implements it by generating a prompt-changing abort extension, not a native Pi configuration parameter. [Harbor Pi:44–59](https://github.com/harbor-framework/harbor/blob/6099b8cf2bfbbb3e7ff1eb2163bfc4524dbd9ba5/src/harbor/agents/installed/pi.py#L44-L59), [version guard:190–205](https://github.com/harbor-framework/harbor/blob/6099b8cf2bfbbb3e7ff1eb2163bfc4524dbd9ba5/src/harbor/agents/installed/pi.py#L190-L205), [extension:369–403](https://github.com/harbor-framework/harbor/blob/6099b8cf2bfbbb3e7ff1eb2163bfc4524dbd9ba5/src/harbor/agents/installed/pi.py#L369-L403), [launch:450–486](https://github.com/harbor-framework/harbor/blob/6099b8cf2bfbbb3e7ff1eb2163bfc4524dbd9ba5/src/harbor/agents/installed/pi.py#L450-L486).

Docker and Modal are alternative SkillsBench backends. The current official guide recommends Modal for cloud execution and allows Docker locally. BenchFlow requires Python ≥3.12; pinned Pi requires Node ≥22.19.0. Local Docker avoids Modal compute billing but not model API costs or machine resource constraints. No machine readiness or authentication check has been performed. [Current guide, Prerequisites and Run One Task](https://www.skillsbench.ai/docs/getting-started), [Pi package:88–97](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/package.json#L88-L97).

## D Exposed Pi parameters and proposed space

**Documentation facts:** the [complete inventory](pi_parameter_research_inventory.md) gives all 72 documented setting rows with exact names, types, defaults, domains, source lines, and assessed performance relevance. It also distinguishes CLI, environment and `models.json` controls. The current official [Pi documentation](https://pi.dev/docs/latest) was checked; experiments must still use the frozen source/runtime interface, not an unversioned “latest” page.

**Recommended primary grid, subject to effective-setting validation:**

| Exact setting | Official default and domain | Proposed values | Hypothesized effect |
|---|---|---|---|
| `defaultThinkingLevel` | `medium`; `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, clamped to model support | `low`, `medium`, `high` if all remain distinct | Reasoning effort, latency and billed output |
| `compaction.reserveTokens` | `16384`; nonnegative safe integer | `8192`, `16384`, `32768` | Earlier/later compaction and additional summary calls |
| `compaction.keepRecentTokens` | `20000`; nonnegative safe integer | `10000`, `20000`, `40000` | Evidence retention versus repeated input and compression |

Evidence: [settings:7–18,69–82](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L7-L82), [runtime compaction validation:833–879](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/settings-manager.ts#L833-L879), [thinking resolution:253–278](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/sdk.ts#L253-L278).

This gives at most **27 grid points**, including native defaults. Apply one predeclared feasibility filter to every method. For verified context window `C`, fixed output allowance `O` and a recorded safety margin `M`, a conservative project filter is `reserve < C` and `keepRecent + O + M < C - reserve`. This is our design rule, not Pi's own validator. Do not falsify model metadata to make points pass. Fixed model/provider, tools, prompts, skills, recovery, image handling and resources are protocol constants. Omit model-specific overrides that could mask the three candidate values.

`thinkingBudgets.{minimal,low,medium,high}` exists, but provider-specific adaptive reasoning may ignore numeric budgets. `defaultTools` can change affordances; `retry.*` changes recovery and costs; `images.*` changes vision inputs; `codemode.*` is conditional on tool activation. These are documented possibilities, not part of the initial grid. UI options such as `theme` do not provide a justified headless success dimension. [Inventory](pi_parameter_research_inventory.md).

**Activation gate:** use validation-only pilot traces to confirm distinct effective thinking levels and nontrivial compaction activity. If compaction never occurs, do not claim a compaction HPO study succeeded. Before formal search, either retain the space and accept a null result, or propose a documented alternative such as a two-level `defaultTools` factor. Any revised space applies to every method, is versioned, and is chosen before test exposure. No undocumented `max_steps`, global `tool_timeout` or universal `temperature` setting is introduced.

## E Three feasible student-developed methods

These are proposed adaptations, not claims of global algorithmic novelty. Implement **one**, not all three. None changes Pi or learns from held-out task results. Engineering estimates assume the evaluator is already reliable.

### Option 1 Interaction guided paired coordinate search

**Recommended.** Use direct local comparisons to decide which parameter pair to explore together, without a probabilistic surrogate or BO acquisition function.

1. Start from native default `x0`. A recorded seed chooses one nondefault level for each of the three dimensions. Evaluate `x0`, the three single changes, and the three corresponding double changes on the identical full validation panel: seven configurations if all are feasible.
2. For pair `(i,j)`, compute the per-task contrast `d_t = y_t(xij) - y_t(xi) - y_t(xj) + y_t(x0)`, and its mean `Iij`. Apply the same contrast separately to USD cost. Positive success contrast suggests synergy relative to the anchor; negative contrast suggests interference. Neither alone is proof of a stable effect under model randomness.
3. Rank fully observed pairs by `abs(Iij)`, breaking ties by fixed parameter order. Explore the remaining feasible, unseen combinations of the highest-ranked pair around the current incumbent, keeping the third coordinate fixed. Use seeded order within that block; every third later proposal is a uniformly sampled unseen feasible configuration to preserve exploration. Recompute local contrasts only when all four comparable cells exist; never impute a missing cell as zero.
4. Every candidate receives the same full panel. Select by validation pass fraction, then lower measured cost, then runtime, then configuration ID. Stop at the shared budget; the incumbent must be a fully evaluated candidate.

The developed element is the explicit pair-diagnostic allocation rule plus exploration, rather than merely performing a grid search. It is distinct from BO because it has no posterior, uncertainty acquisition or model-based global optimum search. An approximate one-day optimizer implementation is plausible; integration will dominate schedule risk.

**Weaknesses:** anchor dependence, noise in four-cell contrasts, inability to identify higher-order interactions reliably, and substantial warm-up cost. A minimum useful budget must exceed the seven-point probe; 12 configurations is an illustration, not an approved budget. Direct single changes and double changes provide an interpretable sensitivity analysis even if optimization gains are absent. A coordinate-only version is the natural method ablation if additional validation budget is approved; it must receive its own disclosed budget, never free observations.

### Option 2 Diversity preserving elite mutation search

Start with Default and three seeded random feasible points, all charged to the method. Maintain three elites ranked by validation success with cost tie-breaking, retaining at least one configuration maximally different in Hamming distance from the incumbent when feasible. Propose unseen children from seeded parent selection; alternate one-coordinate mutations with two-coordinate mutations every third proposal, and inject a random feasible point when the chosen neighborhood is exhausted. Evaluate all candidates on the same full panel and stop at the common budget.

This is an evolutionary/local-search method with a specified diversity and mutation policy, not BO. The student contribution is the small mixed-domain policy and its evaluation; standard evolutionary search is established prior art, as discussed in SMAC3 §4. It is likely the simplest fallback implementation, roughly half a day to a day after the evaluator exists. Risks are lucky early elites, duplicate points and overly rapid convergence. Sensitivity still needs the planned direct ablations; mutation frequency is not a parameter-importance estimate.

### Option 3 Stratified paired task racing

Sample configurations uniformly without replacement. Evaluate each on common nested validation panels containing at least one task per category before elimination. Reserve enough budget to complete Default and a final challenger on the full panel. For binary pass outcomes, after `m` of `V` tasks and `s` passes, the possible completed-panel pass fraction lies in `[s/V, (s+V-m)/V]`. Eliminate a candidate only when its upper bound is below a fully evaluated incumbent's score; use declared category coverage and paired ordering, not an arbitrary “worst half” rule. Charge every task attempt, and never let a partial-panel score update the primary incumbent curve.

This is a conservative, stratified racing adaptation inspired by resource allocation, distinct from surrogate BO and from unmodified Hyperband. The bounds concern the scheduled finite panel, not confidence about unseen tasks. It may save little when candidates are close, and its controller/accounting are more complex, roughly one to two days. If chosen, all methods need the same task-attempt budget and access to the same per-task information; their scheduling policies may differ. Full-panel nomination costs must be reserved inside that budget. Do not implement racing simply to add a feature under the five-day deadline.

### Decision rule among the three

Choose Option 1 if the three parameters are active and a budget supports the probe plus further search. Choose Option 2 if optimizer implementation time is the binding constraint. Choose Option 3 only if the pilot demonstrates that evaluator cost dominates and conservative early elimination can materially save work. Do not decide which algorithm to report after inspecting final test results.

## F Recommended experimental protocol

Everything in this section is a proposed preregistration unless explicitly cited as an upstream fact.

### Split and isolation

Reuse Step 0's [proposed split](sources/proposed_split.json): **28 validation, 59 test**, covering the 87 active v1.1 tasks, with all 14 extras excluded and the separate hello-world package used only for smoke tests. The deterministic algorithm and seed are documented in [Step 0 feasibility](harness_benchmark_feasibility.md#deterministic-assignment-rule). It groups identical subcategories and selected obvious task-name families within categories, orders groups by a seeded SHA-256 and selects a prefix near 30% validation. Current proposal hash: `0cca4204d3c377bea2932cdaded58070dab5596d3def76024de27d0d169c1c4b`.

Before freezing, review **metadata and provenance only** for related datasets, variants and task families that should stay together. No claim is made that the existing grouping eliminates every semantic near-duplicate. Group integrity is prioritized over perfect balance; the current validation set has only one easy task. Freeze the roster, exclusions, groups, seed and hash before formal search. If time or cost requires a smaller suite, select it by a documented metadata rule before performance inspection and clearly label the resulting subset study; do not retain only tasks where Pi performs well.

Each trial gets a fresh sandbox, session, home and writable workspace. The solver sees its task prompt and permitted inputs, plus that task's released skills in the fixed **with-skill** primary condition. It does not see benchmark checkouts, oracle/verifier sources, previous task sessions or earlier solution traces. The optimizer sees validation outcomes/costs only, never test rewards or transcripts. Preserve BenchFlow's protected paths, non-root agent and `oracle_access=false`; no verifier-driven solver retry loop. [BenchFlow lockdown:36–87](https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/sandbox/lockdown.py#L36-L87), [rollout configuration:128–137](https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/rollout/_config.py#L128-L137).

Public benchmark contamination in pretraining cannot be ruled out by our split. Do not retrieve published test solutions or paper trajectories for optimizer design. If AppWorld is chosen, use official `dev` for tuning and official tests for aggregate evaluation; perform failure-case analysis on train/dev to respect its rules.

### Baselines and comparable information

| Method | Configuration proposal | Evaluation contract |
|---|---|---|
| Default | No tuning; native defaults for the fixed model and benchmark integration | Same validation and test panels, skill condition and task resources |
| Random Search | Uniform distinct feasible grid points using a recorded seed | Same charged budget and full-panel evaluator as BO and Option 1/2 |
| Bayesian Optimization | Established SMAC3-style random-forest BO; one frozen implementation/version | Same finite grid, objective, information and evaluation budget; no hidden extra intensification |
| Developed method | One selected algorithm above | Same evaluator and budget; its warm-up/probes/confirmation runs count |

No optimizer receives another method's private search results. A shared initial design is allowed only if declared before search, given to every method and charged to each method's logical budget. The minimal accounting recommendation is separate method runs with no cross-method result cache. Record physical and attributed costs separately if sharing is later introduced. Candidate-structure checks cost no model calls; a dispatched failed rollout still consumes an evaluation slot.

Fix one exact model/provider endpoint and capability catalog. Do not tune model identity at the same time as harness settings. Any common infrastructure restrictions are declared separately from native Pi defaults. If cost controls require disabling `cacheWarming`, do not label that variant untouched Default: either keep native Default as required or obtain agreement on a transparently labelled constrained baseline protocol. There is no basis yet for selecting a provider or stating its price.

### Equal budget and stopping

For Option 1 or 2, use a primary budget of `Q` complete configuration evaluations, each comprising exactly `V` validation task attempts: `B_eval = Q × V` for each of Random Search, BO and the developed method. Keep per-task resources and timeouts identical across candidates. All candidate-generation probes and dispatched failures, including infrastructure failures, are charged. A complete panel means every scheduled task has a recorded outcome or error, not that every solver execution succeeded. Use no outer replacement attempts in the primary campaign; Pi's fixed native request retries remain within a task attempt and their costs are recorded. Default has no search loop; report its one validation measurement and a horizontal reference line rather than pretending it spends a search budget.

Specify a common model-spend safety ceiling and wall-clock ceiling before runs. Equal task-attempt entitlements do **not** imply equal realized USD spend. Plot all costs honestly and compare incumbent curves at common observed dollar thresholds as a secondary cost-matched view. Do not extend curves beyond observed spend or fund one method's extra evaluations. If a safety ceiling prevents the planned equal-attempt comparison, report the campaign as budget-limited and use a predeclared matched-budget analysis; do not call unequal completed search histories equal-budget evidence. A method can nominate only a completed candidate.

For Option 3, replace configuration count with the identical total task-attempt budget for every method, include every partial panel and full-panel promotion, and ensure the reported incumbent always has the full validation panel. This more complex protocol is a reason to prefer Option 1 initially.

Illustrative scale, **not permission to run**: with `Q=12`, `V=28`, three search methods use `3 × 12 × 28 = 1008` solver trials. Add 28 for the standalone Default validation and `4 × 59 = 236` final test trials: **1272 trials**, excluding setup/pilot and any separately budgeted robustness or method ablation. This replaces Step 0's different 1056-trial example. At a hypothetical measured mean solver cost `c`, solver spend is approximately `1272c`; no value of `c` has been measured. If one trial hypothetically averages ten minutes, sequential solver time alone would be 212 hours, exceeding five days. Thus full scale is conditional on an approved pilot and supported concurrency; those numbers are arithmetic scenarios, not forecasts.

### Scoring and incumbent selection

Use `success_t = 1` only for an official successful task outcome, with the BenchFlow canonical `reward == 1.0` rule for this suite. Primary validation and test metrics are the fraction of scheduled tasks passed. Preserve raw partial reward and errors as secondary fields. BenchFlow also exposes an error-excluded pass rate; do not use it as the primary headline. [Canonical scoring:194–227](https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/_utils/scoring.py#L194-L227), [denominators:286–315](https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/_utils/scoring.py#L286-L315).

Update an incumbent only after its full validation panel completes. Order candidates by higher pass fraction, lower complete-panel USD cost, lower runtime, then stable configuration ID. The reported curve is `I(C) = max{validation pass fraction of fully evaluated candidates completed by cumulative search spend C}`. Costs of failed and unfinished candidates still move the x-axis; they do not fabricate a new full-panel y-value. The validation maximum is selection-biased; test performance and the gap reveal whether it transfers.

### Failure handling

| Event | Predeclared primary treatment | Accounting and audit |
|---|---|---|
| Invalid candidate before dispatch | Reject by the common deterministic schema/feasibility rule | Log rejection; no task slot or fictitious API cost |
| Valid verifier failure or partial reward | Not a pass; retain official reward | Full cost and task slot charged |
| Agent timeout, refusal, context overflow, invalid tool use or exhausted native retries | Not a pass; no second solver attempt to improve score | Retain trace, failure class, tokens and all billed calls |
| Infrastructure failure before any model request | Operational pass indicator zero; no outer replacement in the primary campaign | Charge the dispatched task slot; retain missing raw reward, compute costs and original failure; model cost is zero only if no model call is verified |
| Provider failure after a billed request | Retain as failed operational attempt; native fixed retry policy may act | All retry/partial costs charged; no score-directed rerun |
| Verifier crash or missing/invalid reward | Preserve missing reward and error; operational pass indicator zero | Do not rewrite raw reward to zero or silently exclude the task; diagnostic error rate separate |
| Missing trusted usage/cost | Measurement-gate failure | Do not interpret zero placeholders as zero spend; pause scaling and reconcile logs |
| Global outage or systemic runner defect | Pause all methods under the same rule | Repair infrastructure before further experiments; preserve affected attempts and protocol-version history |

The no-replacement rule makes the attempt budget explicit and is distinct from Pi's native model-request retries. Pause dispatch during a known outage to prevent further avoidable failures; retain attempts already dispatched. Tests do not get repeated until they pass. A systemic invalid test execution can require a documented campaign invalidation, not selective favorable reruns. Any future decision to permit outcome-independent infrastructure replacements must define a common extra allowance and revise the protocol before scored runs.

### Cost accounting

Track separate totals for setup/pilot, each method's search, any sensitivity/method ablation, and each selected configuration's test runtime. Sum **all** solver, compaction, cache-refresh, provider-retry and agent-retry calls. For provider-defined nonoverlapping token categories, record input, output, cache read and cache write quantities and their dated rates; include reasoning charges according to the provider's billing definition. Store billed amount when available and an estimate/provenance flag otherwise. Do not double-count cached input or replace actual rates with optimistic metadata. [Pi cost fields](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/models-configuration.md#L40-L50), [BenchFlow unavailable usage semantics](https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/usage_tracking.py#L45-L78).

Report cloud compute, storage, egress and task-side external API charges separately from model costs; include them in a total project-cost table. Local compute is not an API charge, but record resource-hours. No fixed subscription fee is assumed to make marginal evaluation free. Provider quotas and prices, Modal credentials, Docker capacity and concurrency remain decisions to verify. A per-response output cap or timeout is not a guaranteed task-wide dollar limit; the external runner must meter cumulative usage and account for in-flight calls.

For deployment horizon `N`, compare `search_cost + N × selected_runtime_cost` with `N × default_runtime_cost`, alongside their pass fractions. A financial break-even count exists from cost savings only when the selected configuration is cheaper per task; it does not establish equal quality. Do not invent a monetary value per solved task.

### Final test, uncertainty and required analysis

Freeze the selected configuration from **each method**, all configuration hashes, scoring and analysis code, failure rules, and prices before unlocking test execution. Run one attempt per test task and configuration under the same condition. Do not choose among test results or change settings afterward. If two methods select the identical configuration, either execute separately or preregister shared physical evaluation with equal attributed cost and clearly shared outcomes; do not make that choice after scores arrive.

Report pass counts and denominators, validation and test pass fractions, their difference, raw error counts, USD per attempted task and runtime distributions. Use paired task comparisons and group-aware bootstrap intervals for score differences, with a fixed bootstrap seed. One search seed and one solver attempt do not measure optimizer-seed or solver-repeat variance; confidence intervals over tasks must not be described as doing so. With 59 test tasks, one changed outcome moves pass@1 by about 1.69 percentage points, so small differences merit cautious interpretation.

Use the developed method's directly observed single changes and four-cell contrasts for sensitivity, separately for success and cost. Optional surrogate/fANOVA analysis is exploratory and needs validation on configuration-held-out prediction; it must not use test outcomes to fit the surrogate. After the selection freeze, use permitted cases in both directions—tuned fails/Default succeeds and tuned succeeds/Default fails—to analyze context loss, truncation, malformed tools, untriggered parameters, or infrastructure failures. If a category has no observed cases, state that. Avoid attributing causality from one trajectory. For AppWorld, perform these case analyses on train/dev only.

## G Risks and assumptions requiring verification

| Risk or unresolved assumption | Consequence | Evidence or next verification |
|---|---|---|
| Source checkout differs from installed artifact | Experiment does not match documented knobs | Pin package/build digest; record actual runtime version and source identity |
| Adapter silently overrides or ignores candidate settings | Search optimizes labels rather than behavior | Capture effective thinking, tool list, config directory and compaction events after model selection |
| Compaction never triggers | Two proposed dimensions are inert | Validation-only activation pilot; preregister any space revision |
| Provider clamps reasoning or lacks required modalities | Nominal grid collapses; some tasks unsupported | Exact model/API route and capability verification |
| Skill discovery leaks extra resources | Conditions no longer comparable | Fresh home; only released task skills; inspect mounted paths |
| Related tasks cross the holdout boundary | Inflated generalization | Metadata/provenance grouping audit before freeze |
| Warm cache or system load favors run order | Cost or latency comparison confounded | Interleave methods in fixed randomized blocks; record time/cache/concurrency; disclose residual cache effects |
| Sparse stochastic observations | Unstable winner and importance estimates | Small claims, paired analysis, optional approved repeats; no fabricated significance |
| Missing auxiliary-call usage | USD requirement cannot be met | Reconcile raw calls and provider billing; unavailable is not zero |
| Task build/resource failure | Five-day schedule or valid denominator lost | Reviewed Docker/image setup and metadata-based feasibility checks before scored runs |
| Incomplete native-default reconstruction | Required baseline mislabelled | No performance overrides; list only unavoidable benchmark/environment choices |
| TB4 resource protocol shortened | Scores not directly comparable to official TB4 | Label custom timeout/subset; freeze changes uniformly before outcomes |
| Dependency/supply-chain execution | Unreviewed installer runs on host or sandbox | Review scripts, lockfile and build steps first; explain downloads and lifecycle execution before installing |
| Default/Random/BO comparison omitted or underfunded | Course requirements unmet | Reserve final evaluation and baseline budgets before search starts |
| Negative or inconclusive custom-method result | Overstatement temptation | Report it accurately; reproducible comparison and diagnostics remain the deliverable |

All current compatibility conclusions are static source findings. No provider call, benchmark trial, Docker image build, package installation, or runtime handshake was performed in this phase. Official repository code was read as evidence, not executed. No Git commit or push was created.

## Five day delivery plan

**Recommendation, conditional on user approval of scope and spend:**

| Day | Minimal deliverable | Gate |
|---|---|---|
| 1 | Final choices, reviewed dependency plan, pinned runtime, synthetic adapter checks, separate hello-world oracle and bounded paid pilot | Confirm settings propagation, costs, isolation and workable throughput; otherwise decide fallback before search |
| 2 | Minimal evaluator/ledger, Default/Random/BO, one developed method, frozen split/space/budgets | Reproducible configuration hashes and end-to-end dry run; no test feedback |
| 3 | Equal-budget validation searches and required validation ablations | Complete ledgers, comparable incumbent measurements; seal per-method winners |
| 4 | One locked test campaign for all nominated configurations | Preserve all outcomes; no tuning; analyze paired differences and allowed cases |
| 5 | Required report, reproducibility instructions and 10-minute presentation | Requirement checklist audit; submit/commit/push only when authorized |

If Day 1 shows that full-roster search cannot fit the remaining time or approved dollars, reduce the metadata-selected study scope before formal search and test exposure. Do not spend the deadline on a dashboard, multiple harnesses, automatic code rewriting, a multi-agent optimizer, or extra skill ablations. A credible small study is preferable to an incomplete expensive sweep.

## Decisions needed before implementation

1. **Harness and benchmark:** approve provisional Pi + SkillsBench 1.1, or select Pi + Terminal-Bench 4.0. Other course candidates remain possible but need their own configuration audit.
2. **Runtime:** use the exact Step 0 Pi source snapshot as a reproducible build, or select a released Pi package and re-audit its configuration schema. The current snapshot must not be silently replaced.
3. **Model and resources:** choose an exact provider/model with verified effort and modalities, and Docker or an approved cloud backend.
4. **Spending and scale:** approve separate pilot, search, final-test and compute ceilings; then freeze `Q`, task counts, concurrency and the no-replacement failure policy from pilot evidence. No concrete dollar total is justified yet.
5. **Developed method:** approve Option 1, or choose simpler Option 2; reserve Option 3 for an explicit cost-driven rationale.
6. **Protocol:** approve native Default, one fixed with-skill condition, primary single-attempt pass@1, and the metadata-audited split. Confirm any departure such as a reduced suite or cache policy before experiments.

These are implementation decisions for the user, not a request to approve this already completed documentation work. The task stops here.
