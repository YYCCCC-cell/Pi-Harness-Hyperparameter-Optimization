# Interaction-guided configuration search for a fixed agent harness

**PE6203 Group Project 3 · research report draft · 25 October 2026**

**Evaluation status: incomplete.** The student optimizer and baselines are implemented and verified with a deterministic mock. No real Pi/SkillsBench evaluation or held-out run has occurred. This draft reports software evidence and clearly labeled synthetic observations; it does not claim a successful agent optimization experiment.

Implementation claims refer to project 0.2.0; exact file hashes, function/class names and line ranges are collected in the [implementation source index](implementation_source_index.md). Executed-run and exported-artifact hashes provide the corresponding evidence identities.

## Abstract

We study configuration-only optimization of a fixed agent harness, with validation feedback, metered search and a protected test set. The selected project space contains three documented Pi controls with three values each. We implement interaction-guided block search (IGBS), which uses observed matched contrasts to choose parameter blocks, and compare its software behavior with Default, Random Search, SMAC Bayesian Optimization and a matched pair-blind ablation. Eighty automated tests passed. Three mock search seeds completed 4,116 synthetic task attempts with no model calls or API spend. IGBS and its ablation selected identical configurations in every recorded mock seed; none of the six adaptive pair decisions used a positive interaction weight. This verifies the intended fallback but provides no evidence of a real interaction advantage. Live integration, spending approval and held-out evaluation remain pending.

## 1. Problem and scope

An agent harness controls model interaction, tools and context management. Our intervention is restricted to officially supported configuration; the harness implementation, model and external execution protocol must remain fixed within an experiment. The course requires Default, Random Search, a standard surrogate-based BO method and a student-developed optimizer, with sensitivity analysis, cost accounting and final held-out evaluation. It does not require an interaction-aware method or a positive result. [Assignment requirement checklist R01–R10, R17–R26](assignment_requirements_checklist.md).

The research questions are distinct:

1. Do the exposed settings change effective runtime behavior in the chosen model/task setting?
2. Can we distinguish individual effects or pairwise interactions from task/solver noise?
3. Does using those estimates improve configuration selection at the same budget?

Only source-function evidence and mock behavior currently address part of the first question. A threshold or retained-context change does not imply a benchmark success change. [Phase 2 verification](phase2_feasibility_verification.md), recorded blocked pilot（本地或历史材料，未打包：`../runs/archive/pi-setup-20261026/phase2-preflight-20261025/result.json`）.

## 2. Related work and contribution

Functional ANOVA decomposes variation in a fitted response model into main effects and interactions; importance depends on the chosen domain and reference measure. Differential grouping already uses differences of finite differences to detect interacting variables and construct search groups. ParamILS establishes local configuration neighborhoods and perturbation/restart mechanisms. BOCS explicitly includes pairwise interactions in a Bayesian combinatorial model. Consequently, neither interaction estimation, interaction-guided grouping, nor pairwise-interaction BO is new. [Hutter et al., ICML 2014, §3.1–3.2/Alg.2](https://proceedings.mlr.press/v32/hutter14.pdf); [Omidvar et al., TEVC 2014 accepted version, §III/Alg.1](https://eprints.whiterose.ac.uk/id/eprint/156228/1/PID2794611.pdf); [Hutter et al., JAIR 2009, §3.1–3.2/Framework 1](https://www.cs.ubc.ca/labs/algorithms/Projects/ParamILS/papers/09-JAIR-ParamILS.pdf); [Baptista and Poloczek, ICML 2018, §3.1–3.3](https://proceedings.mlr.press/v80/baptista18a/baptista18a.pdf).

Our contribution is an application-specific external policy combining local contrast stability, a fixed pair/single/global schedule, explicit no-evidence behavior and complete attempted-run accounting for a small immutable-harness configuration space. Its contribution must be evaluated against a matched pair-blind arm. It is not a new general HPO family, and the current evidence does not show that it improves Pi.

The model–harness interactions in Harness-Bench and Finding the Right Fit motivate cautious testing but do not establish interactions among these Pi settings. HarnessOpt-Bench contributes evaluation-boundary ideas, although its harness-code editing intervention is prohibited here. The six supplied papers and version-specific limitations are documented in the [literature review](literature_review.md); the fuller prior-art comparison is in [Phase 4 §6](phase4_interaction_aware_hpo_design.md#6-prior-work-and-defensible-novelty).

## 3. System and protocol

### Fixed identities and configuration space

| Component | Identity |
|---|---|
| Project | 0.2.0; exact executed source hashes in each run manifest |
| Pi | Manifest 1.4.0; source `f321e5bdd26b3624bfb2ab182a334d0a5edb698a` |
| SkillsBench | v1.1; source `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af` |
| BenchFlow | v0.6.3; source `99baefb602674bbd31139fd2f1a22c3ed45752f9` |
| pi-acp | 0.0.34; source `b0581c9c1d675e634234674484247008b03d69b4` |
| BO | SMAC 2.4.0; ConfigSpace 1.2.1; recorded upstream component settings |
| Actual evaluated harness/model | None: deterministic mock only |

All upstream checkouts were reused and remain unchanged. A source version does not attest an installed live runtime. [Source lock](sources/source_lock.json), [current review/preflight](run_review/run_manifest.draft.json).

| Setting | Domain | Native default | Source-level effect |
|---|---|---|---|
| `defaultThinkingLevel` | low / medium / high | medium | Requested reasoning level is resolved against model support |
| `compaction.reserveTokens` | 8192 / 16384 / 32768 | 16384 | Changes the automatic compaction threshold |
| `compaction.keepRecentTokens` | 10000 / 20000 / 40000 | 20000 | Changes recent-context retention when compaction occurs |

Sources at Pi commit `f321e5…`: [`settings.md`, lines 11–18](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L11-L18), [lines 69–82](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L69-L82), [`models.ts`, lines 1261–1290](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/ai/src/models.ts#L1261-L1290), [`compaction.ts`, lines 267–270](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/compaction/compaction.ts#L267-L270) and [431–475](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/compaction/compaction.ts#L431-L475).

The Cartesian product has 27 configurations. All pass the fixture's synthetic context/output-margin filter; real-model feasibility remains unverified. There is no added temperature, maximum-step control or presumed provider RNG seed. [Frozen grid](../configs/hpo_space.json).

### Formulation and fair comparison

For a fixed harness/model/protocol, let \(Y_t(\theta)\in\{0,1\}\) be a task's full-success outcome, with accounted cost \(C_t\). Search targets expected validation success, observed through a complete task panel:

\[
F_V(\theta)=|V|^{-1}\sum_{t\in V}\mathbb E[Y_t(\theta)],\qquad
\widehat F_V(\theta)=|V|^{-1}\sum_{t\in V}Y_t(\theta).
\]

Each search arm receives Q=12 full panels of 28 validation labels per seed: 336 charged attempts including initialization and failures. Default is measured once per standalone mock campaign. Only complete, measurement-valid panels can nominate a winner. The common rank is success, then lower cost, lower duration and configuration hash; the mock uses explicitly synthetic cost/time in the latter positions. A future live adapter must use accounted USD and measured runtime. [Controller and audit](../hpo/runner.py), [shared selection rule](../hpo/selection.py).

Search seeds are 20261025/26/27, evaluation seed 6203 and schedule seed 42. Solver randomness is absent in this deterministic fixture. Search panels are interleaved across methods, with private histories and no cross-method result reuse. The source hashes, installed versions and process environment are recorded. [Final mock configuration](../configs/hpo_final_mock.json).

The proposed split has 28 validation and 59 test IDs across 87 active tasks; the 17 validation groups require semantic/provenance review before real evaluation. Optimizers load only hashed validation projections. No test outcome exists in the mock inputs or outputs. The live filesystem boundary has not been verified. [Exact rosters and confirmation status](run_review/README.md), [read-guard tests](../tests/test_interaction.py).

### Baselines and student algorithm

Random Search samples uniformly without replacement. Standard BO uses the unmodified SMAC HPO facade, ten-tree random forest, log expected improvement, three Sobol initial panels and the existing public ask/tell contract. A random forest can represent interactions; “BO ignores interactions” is not our rationale. [Baseline implementation](../hpo/methods.py), [SMAC 2.4.0 facade, lines 24–108](https://github.com/automl/SMAC3/blob/v2.4.0/smac/facade/hyperparameter_optimization_facade.py#L24-L108).

IGBS evaluates default + three single changes + three double changes, then cycles through pair, single and global proposals. A matched pair contrast on the same tasks is

\[
\hat\Delta_{ij}=|V|^{-1}\sum_t(Y_{11,t}-Y_{10,t}-Y_{01,t}+Y_{00,t}).
\]

Incomplete rectangles are unidentified, not zero. Local background values must match the current incumbent. Task-weighted group resampling and leave-one-group-out stability shrink the routing weight. The fixed constants are 2,000 resamples, .95 absolute-deviation quantile, .05 practical threshold, at least eight groups and .8 sign/size stability. A positive weight chooses a block; a candidate within that block is sampled uniformly. No reliable weight means uniform eligible block selection. The pair-blind ablation changes only pair selection to uniform, retaining the screen, single rule, cadence, costs and candidate sampling. [Estimator](../hpo/contrasts.py), [IGBS implementation](../hpo/interaction_search.py), [complete mathematics/pseudocode](phase4_interaction_aware_hpo_design.md).

These weights are heuristics, not calibrated sequential significance tests. Seven initial panels consume 58.3% of Q=12. The method covers only two initial levels and can miss a third-level or three-way dependency. No theorem of improved sample efficiency is claimed.

## 4. Verification evidence and synthetic observations

### Software verification

**80 tests passed.** Coverage includes exact synergy/antagonism contrasts, no-interaction behavior, missing corners, background matching, task-weighted group resampling, unstable/noisy contrasts, a pure three-way effect the screen misses, seeded proposals, all-five-method fresh-process reproducibility, equal charged budgets, fault/missing-measurement handling, audit reconciliation, reporting nulls and held-out read guards. Tests verify that a deliberately constructed strong pair effect activates guided selection; they do not assert that IGBS must win on every seed. Preserved test log（本地或历史材料，未打包：`../artifacts/mock-verification/unit-tests.log`）, [tests](../tests/test_interaction.py).

The three complete saved campaigns contain **4,116 synthetic attempts**: Default 84 and 1,008 for each of Random Search, BO, IGBS and pair-blind. Every dispatch has a recorded result. All failures/timeouts remain charged, with zero model calls and zero API USD. The three campaign wall times sum to approximately 13.31 seconds of local mock execution, excluding the unit suite. They are not agent-runtime measurements. Results and audits（本地或历史材料，未打包：`../artifacts/mock-verification/results.json`）.

### Selected configurations and validation scores — mock only

Aliases below are exact settings, not model names:

- **D:** `defaultThinkingLevel=medium`, `reserveTokens=16384`, `keepRecentTokens=20000`.
- **H:** `defaultThinkingLevel=high`, `reserveTokens=16384`, `keepRecentTokens=20000`.
- **S:** `defaultThinkingLevel=high`, `reserveTokens=16384`, `keepRecentTokens=10000`.

| Search seed | Default | Random Search | SMAC BO | IGBS | Pair-blind |
|---|---|---|---|---|---|
| 20261025 | D, 16/28 | D, 16/28 | H, 17/28 | D, 16/28 | D, 16/28 |
| 20261026 | D, 16/28 | S, 16/28 | H, 17/28 | H, 17/28 | H, 17/28 |
| 20261027 | D, 16/28 | D, 16/28 | S, 16/28 | H, 17/28 | H, 17/28 |

The values 16/28 and 17/28 correspond to 0.5714 and 0.6071 in a deliberately synthetic landscape. They are not estimates of Pi success. All exact settings and scores are available in results.json（本地或历史材料，未打包：`../artifacts/mock-verification/results.json`）; unsuccessful attempted configurations are retained in the raw archives.

### Search-cost curves

Synthetic search-cost curve, first seed（历史合成图原件保留本地；本包公开图见 `artifacts/release-verification/figures/`）

Every figure is labeled **deterministic mock only**. Curves use only completed-panel incumbents and retain overlapping arms. Actual USD is zero at every observation; the USD figure（本地或历史材料，未打包：`../artifacts/mock-verification/figures/20261025-accounted_usd.svg`） explicitly states that no dollar-efficiency inference is possible. Attempt and synthetic-cost curves for all three seeds, plus their JSON inputs, are in the artifact package（本地或历史材料，未打包：`../artifacts/mock-verification/README.md`）.

| Seed | Random simulated search cost | BO | IGBS | Pair-blind |
|---|---:|---:|---:|---:|
| 20261025 | 0.705862 | 0.756280 | 0.671745 | 0.671745 |
| 20261026 | 0.672730 | 0.696210 | 0.807320 | 0.807320 |
| 20261027 | 0.655791 | 0.722323 | 0.788873 | 0.788873 |

These are fixture units, neither dollars nor provider-price estimates. Equal attempt entitlements do not imply equal synthetic or real costs. Default's separate synthetic panel cost is 0.059354 per standalone verification run. Budget records（本地或历史材料，未打包：`../artifacts/mock-verification/results.json`）.

### Interaction-awareness ablation

| Seed | Guided pair actions / pair slots | IGBS minus pair-blind validation score | Candidate disagreements |
|---|---:|---:|---:|
| 20261025 | 0/2 | 0 | 0 |
| 20261026 | 0/2 | 0 | 0 |
| 20261027 | 0/2 | 0 | 0 |

All seven initial settings match within each pair of arms; the subsequent candidates also match. The uncertainty fallback works as specified. **There is no observed contribution from interaction guidance in this mock campaign.** No threshold, seed or result was changed to obtain a positive difference. This does not show that Pi interactions are absent; Pi was not run. Ablation records（本地或历史材料，未打包：`../artifacts/mock-verification/ablation.json`）.

### Parameter sensitivity — descriptive mock analysis

Posthoc matched contrasts were computed separately from each method's own completed history, without feeding other methods' data into search. For IGBS:

| Seed | Observed edges | Completed rectangles | Range of signed pair contrasts |
|---|---:|---:|---|
| 20261025 | 18 | 4 | −0.07143 to +0.03571 |
| 20261026 | 20 | 6 | −0.07143 to +0.03571 |
| 20261027 | 20 | 6 | −0.14286 to +0.03571 |

These sparse, adaptively sampled contrasts do not identify global fANOVA importance over 27 points. The mock's thresholded outcomes and configuration-dependent injected faults can create nonadditivity even though its latent quality expression is additive. Thus the contrasts are useful parser/estimator coverage, not evidence about Pi mechanisms. Signed estimates, coverage, stability weights and separate synthetic cost/time contrasts are preserved in sensitivity.json（本地或历史材料，未打包：`../artifacts/mock-verification/sensitivity.json`）. [Fixture source](../hpo/evaluation.py), [estimator source](../hpo/contrasts.py).

### Representative failure cases in both directions — mock only

For IGBS seed 20261026, the selected H configuration and Default differ on these opaque labels:

| Direction | Label | Recorded outcome | Valid interpretation |
|---|---|---|---|
| Tuned passes, Default fails | `multilingual-video-dubbing` | Selected success; Default `verifier_failure` | Deterministic fixture generated different outcomes; no video task was executed |
| Default passes, tuned fails | `exoplanet-detection-period` | Default success; selected `infrastructure_failure` | The fixture injected a failure; it is not a diagnosed Pi or astronomy-task weakness |

The full export has 34 paired differences across all method/seed winners: 20 tuned-pass/default-fail and 14 reverse cases. They are repeated views of a deterministic synthetic fixture, not 34 independent real incidents. Each case references its exact attempt IDs and raw outcome. Real trajectories and causal failure diagnoses remain unavailable. Case records（本地或历史材料，未打包：`../artifacts/mock-verification/failure_cases.json`）.

## 5. Held-out and economic results: not yet available

| Required real result | Status | Why it is missing |
|---|---|---|
| Final held-out pass@1 for each frozen winner | **Not run / null** | No approved paid campaign or completed live integration |
| Validation–test generalization gap | **Unavailable / null** | Neither real validation nor test observations exist |
| Actual/estimated real search USD | **Unavailable** | Model/provider and approved ceilings are unset |
| Real per-task runtime/API cost | **Unavailable** | No real solver call was dispatched |
| Real parameter sensitivity/interaction effects | **Unverified** | Only source probes and synthetic outcomes exist |
| Real interaction ablation benefit | **Unverified** | Mock arms coincide; no live comparison |
| Real success/failure trajectories | **Unavailable** | Pi was never executed in the campaign |

Null is not zero success, zero cost, or assumed convergence. These rows cannot be filled from the mock tables.

For later economic analysis, distinguish one-time search cost \(C_{\mathrm{search}}\) from per-deployment-task cost \(c_\theta\). Deployment cost for M tasks is \(C_{\mathrm{search}}+Mc_\theta\). A monetary break-even count exists only if the tuned setting is cheaper: \(M>C_{\mathrm{search}}/(c_0-c_\theta)\), with consistent workload and measured/estimated provenance. If tuning increases task cost, quality gains do not create a monetary saving without an explicitly supplied value model. No such value or real break-even estimate is invented here.

In the fixture, H costs approximately 0.002713 synthetic units per task versus D's 0.002120. The synthetic winner may therefore be more costly to deploy even when it passes one additional label. These values test accounting, not a recommendation to spend on high reasoning. Actual API costs for both are zero because no API is involved. Selected-panel measurements（本地或历史材料，未打包：`../artifacts/mock-verification/results.json`）.

## 6. Budget, noise and limitations

The [draft real-run manifest](run_review/run_manifest.draft.json) enumerates the fixed IDs and native timeouts, but has **no approved USD budget**. With 28 validation tasks, 59 test tasks, Q=12, three search seeds and the pair-blind arm, the proposed workload is 4,032 search attempts + 28 Default validation + 767 final-test attempts = **4,827**, excluding pilot/compute. Exact model, runtime, per-attempt reservations, wall-time ceilings and split review must be resolved before approval.

Agent timeouts in the pinned active-task metadata range from 300 to 7,200 seconds, rather than the mock's uniform simulated 120 seconds. This reinforces the five-day feasibility risk. Read-only metadata inventory does not validate the environments, assets, cancellation or provider usage. [Per-task metadata and current preflight](run_review/run_manifest.draft.json).

Binary outcomes on 28 heterogeneous tasks provide weak interaction resolution. Under an illustrative independent Bernoulli .5 model, a four-cell mean contrast has standard error about .189. Three search seeds do not resolve solver-repeat variance or provide strong significance claims. The existing 17 metadata groups are not proven independent; adaptive candidate selection, sparse rectangles, covariance, floors/ceilings, inactive compaction and model-level clamping can all obscure or imitate effects. [Phase 4 noise and budget calculations](phase4_interaction_aware_hpo_design.md#7-noise-identifiability-and-small-sample-risks).

The standard BO surrogate can model interactions, and Random Search already explores a substantial fraction of this 27-point grid. A seven-point screen leaves only five adaptive proposals. Even a perfectly implemented interaction estimator may not improve finite-budget performance. These are reasons to preserve the matched ablation and report negative findings, rather than reasons to weaken the baseline or select favorable seeds.

## 7. Completion plan and conclusion boundary

The current deliverable is a reproducible, mock-verified external search system and an auditable experimental proposal. The real experiment is incomplete. Before claiming optimization gains: obtain the missing model/runtime and itemized budget decisions, review and approve the final manifest, validate the integration/measurement boundary, run validation comparisons fairly, freeze all winners and then evaluate held-out tasks once under the approved protocol. [Experiment instructions](experiment_instructions.md).

The evidence supports “the policy, fallback, budget accounting and reporting path function under the deterministic fixture.” It does not support “interaction-aware tuning improves Pi,” “the selected configuration generalizes,” or “the method reduces real cost.” Those remain unanswered research questions.
