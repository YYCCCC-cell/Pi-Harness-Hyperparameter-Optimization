# Phase 3 baseline implementation and validation

**Status, 2026-10-25: baseline software implemented and verified against a deterministic mock; real Pi/SkillsBench evaluation remains blocked.** All **54 automated tests passed**. The final saved verification completed **700 synthetic task attempts**: 28 for Default, 336 for Random Search, and 336 for Bayesian Optimization. There were **zero model API calls and $0 model API spend**. These are software-verification results, not measurements of harness success or generalization. Evidence: test log（本地或历史材料，未打包：`../runs/phase3-verification-20261025/unit-tests.log`）, final summary（本地或历史材料，未打包：`../runs/phase3-baselines-20261025-reproducible/summary.json`）, independent log audit（本地或历史材料，未打包：`../runs/phase3-verification-20261025/audit.json`）.

## Decision provenance and scope

This phase carries forward the saved Pi + SkillsBench 1.1 route, three-parameter grid and equal task-attempt protocol from [Phase 1, sections D/F](initial_research_feasibility_proposal.md), and the source/interface verification from [Phase 2](phase2_feasibility_verification.md). Those documents still mark model/provider, spending ceiling, runtime image and split review as unresolved. The current instruction authorizes baseline implementation and low-cost verification; it does not supply those missing real-experiment choices. No approval record, successful real pilot or measured LLM cost is inferred.

The existing validation proposal provides **28 opaque task IDs** for the mock. A validation-only projection is stored in [hpo_validation_tasks.json](../configs/hpo_validation_tasks.json), with the original split hash and status `proposed_mock_only`. The controller verifies the projection's SHA-256, `2555ffc426f9c6f03b06f614ad07119c4021d4b52c46118b9f4358e0dd210f88`, before every campaign. It never loads the combined split, task prompts, skills, verifiers, oracle code or held-out results. This is a frozen mock fixture, **not a newly approved scientific split**. [Project v0.1.0 `hpo/config.py`:46–53](../hpo/config.py), [isolation tests](../tests/test_hpo.py).

All four pre-existing upstream checkouts remain clean at their previous hashes. Pi's manifest version 1.4.0 is a source identity, not an installed runtime attestation. Verified checkout status（本地或历史材料，未打包：`../runs/phase3-verification-20261025/third-party-status.json`）.

| Component | Frozen source commit |
|---|---|
| Pi, manifest 1.4.0 | `f321e5bdd26b3624bfb2ab182a334d0a5edb698a` |
| SkillsBench v1.1 | `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af` |
| BenchFlow v0.6.3 | `99baefb602674bbd31139fd2f1a22c3ed45752f9` |
| pi-acp 0.0.34 | `b0581c9c1d675e634234674484247008b03d69b4` |

## Shared configuration contract

| Exact Pi setting | Official type/default | Shared search values | Runtime qualification |
|---|---|---|---|
| `defaultThinkingLevel` | Enum string; `medium` | `low`, `medium`, `high` | Model support can clamp levels; real activation remains unverified |
| `compaction.reserveTokens` | Nonnegative JavaScript safe integer; `16384` | `8192`, `16384`, `32768` | Changes compaction threshold; a short task may never trigger it |
| `compaction.keepRecentTokens` | Nonnegative JavaScript safe integer; `20000` | `10000`, `20000`, `40000` | Changes unsummarized recent context when compaction occurs |

Official sources, **Pi commit `f321e5…`**: [`packages/coding-agent/docs/settings.md`:11–18](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L11-L18), [same file:69–82](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L69-L82), [`src/core/settings-manager.ts`:833–879](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/settings-manager.ts#L833-L879), [`src/core/sdk.ts`:253–278](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/sdk.ts#L253-L278). Phase 2's synthetic source-function probes verified changing thresholds/retained messages, not a full ACP/model execution; see its [verification report](phase2_feasibility_verification.md).

The Cartesian product contains 27 configurations, including native defaults. All methods share one `Space`, serializer and validator. Only these nested settings are serialized; model identity, tools, retries, skills and prompts are not optimization dimensions. The mock applies the same proposed feasibility rule to all methods using **synthetic** `C=128000`, `O=16384`, `M=4096`: `reserve < C` and `recent + O + M < C - reserve`. These numbers are test-fixture metadata, not a claim about a real model. Every grid point passes this fixture. [Space](../configs/hpo_space.json), [space schema](../schemas/hpo_space.schema.json), [settings schema](../schemas/pi_search_settings.schema.json), [project v0.1.0 `hpo/config.py`:74–98](../hpo/config.py).

## Baseline implementations

| Method | Proposal rule | Charged validation work |
|---|---|---|
| Default | Exact native values: `medium`, `16384`, `20000` | One full panel; reference measurement only |
| Random Search | Seeded uniform permutation of the same 27 distinct points | First 12 full panels; no replacement or reuse of another method's results |
| Bayesian Optimization | **SMAC3 2.4.0** `HyperparameterOptimizationFacade`, public ask/tell interface | 3 Sobol initial panels + 9 subsequent panels, all inside the same 12-panel budget |

Project source **v0.1.0**: [`hpo/methods.py`:10–30](../hpo/methods.py) for Default/Random and [lines 33–78](../hpo/methods.py) for BO. Full component settings are captured in bo-components.json（本地或历史材料，未打包：`../runs/phase3-baselines-20261025-reproducible/bo-components.json`）. The installed library and its transitive artifacts are pinned in [requirements-hpo.lock](../requirements-hpo.lock), with source snapshots/hashes in [sources/hpo/source_lock.json](sources/hpo/source_lock.json).

BO uses three ordinal ConfigSpace dimensions; its upstream surrogate is a 10-tree random forest, with log expected improvement, local/sorted-random acquisition search and 0.2 random-design probability. These are library components, not a student-created BO algorithm. [SMAC **v2.4.0**, `smac/facade/hyperparameter_optimization_facade.py`:24–108](https://github.com/automl/SMAC3/blob/v2.4.0/smac/facade/hyperparameter_optimization_facade.py#L24-L108), [lines 169–181](https://github.com/automl/SMAC3/blob/v2.4.0/smac/facade/hyperparameter_optimization_facade.py#L169-L181).

The project explicitly sets `deterministic=True`, `n_workers=1`, `max_config_calls=1`, `use_default_config=False`, and `retrain_after=1`. One SMAC observation is **one completed validation panel**, with loss `1 - pass_fraction`; task IDs are not passed as SMAC instances. Thus SMAC cannot create hidden task repeats, racing evaluations, multi-fidelity trials or free confirmation panels. `TrialValue.cost` denotes optimization loss, not USD. All initial-design work is charged. [Project `hpo/methods.py`:40–77](../hpo/methods.py); official [ask/tell API, SMAC v2.4.0 `abstract_facade.py`:288–304](https://github.com/automl/SMAC3/blob/v2.4.0/smac/facade/abstract_facade.py#L288-L304), [selector options:424–431](https://github.com/automl/SMAC3/blob/v2.4.0/smac/facade/abstract_facade.py#L424-L431), [intensifier option:111–132](https://github.com/automl/SMAC3/blob/v2.4.0/smac/facade/hyperparameter_optimization_facade.py#L111-L132).

SMAC retains its own random exploration and fallback when acquisition search cannot produce enough unseen points. In the final recorded campaign, the 12 BO proposals comprise 3 Sobol, 4 local-acquisition, 3 random-search and 2 upstream retry-exhaustion fallback proposals. This behavior is logged, not hidden or replaced with a custom optimizer. An actual repeated configuration returned to the controller is an error and stops the campaign; it is never silently replaced. Final panel origins（本地或历史材料，未打包：`../runs/phase3-baselines-20261025-reproducible/summary.json`）, [SMAC v2.4.0 `smac/main/config_selector.py`:216–268](https://github.com/automl/SMAC3/blob/v2.4.0/smac/main/config_selector.py#L216-L268), [project duplicate guard](../hpo/methods.py).

## Common scoring, logging and budgets

The common controller shuffles the validation order once using the evaluation seed, derives one stable seed per task, and uses that same order/seed for every configuration and method. A separate schedule seed interleaves methods by configuration block. The search seed is `20261025`, evaluation seed `6203`, and schedule seed `42`. No method receives another method's observations. Each attempt has a new directory; this is mock filesystem separation, not evidence of real container isolation. [Campaign configuration](../configs/hpo_mock.json), [project v0.1.0 `hpo/runner.py`:47–115](../hpo/runner.py), [mock contract](../hpo/evaluation.py).

Each search method has exactly `12 × 28 = 336` dispatch slots. Default has 28. The ledger charges a slot **before** evaluator dispatch, including timeout, infrastructure, parsing and verifier failures. There are no outer replacement attempts. Before dispatch it reserves the evaluator's declared worst-case charge against the common cap; the mock's real-USD bound is zero and its synthetic bound is 0.01 units. Decimal accounting avoids boundary errors such as `0.1 + 0.1 + 0.1`. [Project v0.1.0 `hpo/budget.py`:6–65](../hpo/budget.py), [`runner.py`, attempt loop](../hpo/runner.py).

Known actual USD takes precedence over an estimate; both original fields and provenance are retained. The summary separates known-actual sums, estimates used, and unknown-cost counts. Missing cost remains null and stops **all** methods; it never becomes a free evaluation. Missing input/output usage also stops all methods. A charge exceeding its reservation is retained and triggers a stop; the ledger cannot undo an external bill. Hard monetary guarantees for a future live evaluator require a credible upper bound or provider-side enforcement. [Budget accounting](../hpo/budget.py), [normalization](../hpo/evaluation.py), [measurement gates](../hpo/runner.py), [accounting unit tests](../tests/test_hpo.py).

Primary success is `raw_reward == 1.0`; partial reward, missing reward and operational errors are nonpasses on the scheduled denominator. Explicit successful reward still takes precedence over a separate diagnostic, matching pinned BenchFlow semantics. Original reward and error are retained. Only full, measurement-valid panels can update the incumbent or be sent to BO. Synthetic ties use lower simulated cost, then simulated runtime, then configuration hash. The future real protocol must use complete-panel USD and measured runtime in those positions. [Project `hpo/evaluation.py`:9–28](../hpo/evaluation.py), [`hpo/runner.py`, panel selection](../hpo/runner.py), [BenchFlow v0.6.3 `_utils/scoring.py`:194–227](https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/_utils/scoring.py#L194-L227).

Proposals, durable dispatch intents, raw results, normalized outcomes and cumulative budgets are preserved. Partial panels consume budget but cannot supply a new incumbent. A common safety ceiling can end methods at different actual attempt counts; the summary distinguishes equal **entitlements**, equal **completed attempts**, and a fully completed comparison. It does not label an interrupted comparison equal-budget evidence. Abrupt process loss can leave an unmatched dispatch in the journal; resume is intentionally unsupported, and that attempt must be reconciled before any future real rerun. [Project `hpo/runner.py`, `Journal`, attempt loop, summary and `audit_run`](../hpo/runner.py).

## Observed mock verification

The authoritative saved run is `runs/phase3-baselines-20261025-reproducible/`（本地或历史材料，未打包：`../runs/phase3-baselines-20261025-reproducible/`）. It completed in **5.024 seconds of local wall time**. The table describes synthetic accounting coverage, not benchmark accuracy:

| Method | Complete configurations | Task attempts | Simulated timeouts | Other simulated errors | Simulated cost units | Actual model API USD |
|---|---:|---:|---:|---:|---:|---:|
| Default | 1 | 28 | 1 | 0 | 0.059354 | 0 |
| Random Search | 12 | 336 | 5 | 11 | 0.705862 | 0 |
| SMAC BO | 12 | 336 | 10 | 10 | 0.756280 | 0 |

Every search configuration was distinct within its method. The audit reconciles **700 dispatches and 700 results**, no unmatched dispatches, all complete panels containing each allowed validation label exactly once, score counts, and cumulative cost totals. Raw synthetic pass/fail results remain available, but are not used to claim that BO improves Pi. Summary（本地或历史材料，未打包：`../runs/phase3-baselines-20261025-reproducible/summary.json`）, audit（本地或历史材料，未打包：`../runs/phase3-verification-20261025/audit.json`）, event log（本地或历史材料，未打包：`../runs/phase3-baselines-20261025-reproducible/events.jsonl`）.

**54 tests passed**: 22 retained Phase 2 tests and 32 Phase 3 tests. They cover serialization, the finite grid/native default, strict schemas, seeds, actual-versus-estimated cost precedence, decimal boundaries, all failure charging, missing measurements, cap breaches, partial panels, time gates, no output reuse, roster tamper rejection, log/cost reconciliation, and same-process/fresh-process reproducibility. Tests instrument the genuine SMAC RF training method: the six-panel fixture retrains on **2, 3, 4, 5** observed panels after its two-panel initial design. No fake BO is substituted. [Tests](../tests/test_hpo.py), complete test log（本地或历史材料，未打包：`../runs/phase3-verification-20261025/unit-tests.log`）.

A fresh-process check initially exposed divergent BO proposals with identical search seeds. ConfigSpace 1.2.1 hashes a string representation, and SMAC's local search uses a set of configurations; this makes Python hash randomization relevant. The CLI now restarts with `PYTHONHASHSEED=0`, and pins numerical thread environment variables to 1. Regression tests launch two fresh interpreters with different parent hash seeds and confirm identical complete panel histories after this startup normalization. ConfigSpace **1.2.1** `ConfigSpace/configuration.py`:247–248（本地或历史材料，未打包：`sources/hpo/ConfigSpace/configuration.py`）, SMAC **2.4.0** `smac/acquisition/maximizer/local_search.py`:301–305（本地或历史材料，未打包：`sources/hpo/smac/acquisition/maximizer/local_search.py`）, [startup code](../hpo/__main__.py), [regression tests](../tests/test_hpo.py). Earlier diagnostic directories `phase3-baselines-20261025` and `phase3-baselines-20261025-final` are retained but superseded for reproducibility claims.

## Deliverables and remaining gates

| Requested deliverable | Location/status |
|---|---|
| Three baselines | [`hpo/methods.py`](../hpo/methods.py), executed with the mock |
| Automated tests | [`tests/test_hpo.py`](../tests/test_hpo.py), 32 new tests; 54 total passing |
| Configuration schemas | [`schemas/`](../schemas/), campaign, space, Pi settings and evaluator result contracts |
| Trial logging | [`hpo/runner.py`](../hpo/runner.py), final manifest/settings/events/raw results/summary |
| Budget enforcement | [`hpo/budget.py`](../hpo/budget.py), attempt/monetary reservation and post-charge gates; common dispatch-time wall gate |
| Reproduction instructions | [phase3_reproduction.md](phase3_reproduction.md), pinned interpreter/dependencies/process settings |

Remaining limitations are explicit:

1. **No live HPO evaluator is connected.** Phase 2 permits only its separate hello-world pilot. Model/provider, credentials, spending ceiling, reviewed runtime image and Docker-capable execution remain unresolved in the saved configuration. The prior preflight found missing dependencies/infrastructure; this phase installed only the optimization/test environment, not the harness stack. [Phase 2 blockers](phase2_feasibility_verification.md#exact-blockers-and-smallest-compliant-alternative), [pilot configuration](../configs/pilot.json).
2. **Real parameter activity is unproven.** Reasoning levels may collapse and compaction may remain inactive; the source-function probes do not prove runtime integration. [Phase 2 parameter verification](phase2_feasibility_verification.md), [Pi source references above](#shared-configuration-contract).
3. **Formal split approval is outstanding.** Review metadata/provenance grouping before sealing the roster. Test tasks must remain inaccessible to the optimizer, then be unlocked only after configuration selection freezes. [Phase 1 split protocol](initial_research_feasibility_proposal.md#split-and-isolation).
4. **USD and timeout enforcement are mock-tested.** The ledger is ready to consume normalized measurements, but live cost reconciliation must include auxiliary/retry/compaction/cache calls, task-side APIs and separate compute charges; external enforcement must cover in-flight overshoot. The mock cannot validate Docker cleanup or true wall-time killing. [Phase 1 cost accounting](initial_research_feasibility_proposal.md#cost-accounting), [Phase 2 accounting limits](phase2_feasibility_verification.md#parsing-and-accounting-decisions).
5. **Reproducibility is bounded by the locked platform/library environment.** The lock was verified on macOS arm64/Python 3.12.14. Runtime timestamps are expected to differ, and finite-space SMAC fallback behavior is part of this exact library baseline. Review new platforms or dependency revisions separately. [Dependency record](sources/hpo/source_lock.json), [reproduction guide](phase3_reproduction.md).

No third-party source was modified, no real benchmark evaluation was run, no held-out task was evaluated, no student-developed optimizer was added, and no Git commit or push was made. Stop here. The next proposed action is the still-pending single low-cost integration pilot after the missing setup decisions are supplied, followed by a separately approved real-validation budget.
