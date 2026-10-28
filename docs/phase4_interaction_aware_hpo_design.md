# Phase 4: interaction-aware HPO research and design

**Decision document · 25 October 2026 · design only, awaiting approval**

**Recommendation:** treat interaction awareness as a hypothesis to test. If the integration and parameter-activation checks pass, implement a small **interaction-guided block search**, with a matched version that chooses parameter pairs uniformly. Do not claim a new general HPO algorithm or that Pi interactions have already been demonstrated. If reliable contrasts are unavailable, use ordinary coordinate search with scheduled random exploration.

The saved evidence contains **no real Pi/SkillsBench configuration evaluations**. Phase 2 stopped before dispatch; Phase 3 verified software with synthetic outcomes. Consequently, neither an individual performance effect nor an interaction among the selected Pi settings is currently measured. Source-level effects establish that a setting can change behavior; they do not establish that it improves benchmark success. Phase 2 result（本地或历史材料，未打包：`../runs/archive/pi-setup-20261026/phase2-preflight-20261025/result.json`）, Phase 2 function probes（本地或历史材料，未打包：`../runs/archive/pi-setup-20261026/phase2-preflight-20261025/pi-function-probes.json`）, authoritative Phase 3 summary（本地或历史材料，未打包：`../runs/phase3-baselines-20261025-reproducible/summary.json`）.

This report supplies the formulation, estimator, candidate policy, pseudocode, prior-art comparison, ablation, budget analysis and implementation boundary. **No optimizer code, benchmark evaluation, dependency installation or change to the frozen harness is part of this phase.** Numerical power and cost calculations below are planning calculations, not experimental results; their inputs and outputs are recorded in [research and budget evidence](sources/phase4/research_and_budget_evidence.json).

## 1. Evidence boundary and inherited constraints

### Assignment facts

The assignment requires a fixed harness implementation, supported configuration controls, validation-only selection, a protected test set, comparable information and budgets, and Default, Random Search, standard surrogate-based BO and at least one student-developed method. It also requires sensitivity analysis and discussion of harmful interactions; it **does not require interaction awareness to succeed**, nor prescribe this algorithm, number of seeds or budget. Assignment extraction, P017–P023, P044–P046 and P051–P056（本地或历史材料，未打包：`sources/research/assignment_extracted.txt`）, [requirement checklist R01–R10, R17–R26](assignment_requirements_checklist.md).

### Verified project state

| Item | Current evidence and implication |
|---|---|
| Harness and benchmark route | Carry forward Pi + SkillsBench 1.1 via the saved external BenchFlow/pi-acp plan. A working live evaluator is still unverified; algorithm design cannot remove that blocker. |
| Source versions | Pi manifest 1.4.0 at `f321e5bdd26b3624bfb2ab182a334d0a5edb698a`; SkillsBench v1.1 at `b63b7b2850226b6aa4fb5929a8c1ac7bc4d9a6af`; BenchFlow v0.6.3 at `99baefb602674bbd31139fd2f1a22c3ed45752f9`; pi-acp 0.0.34 at `b0581c9c1d675e634234674484247008b03d69b4`. The Pi snapshot is not an installed runtime attestation. |
| Real observations | The recorded pilot has `benchmark_attempted=false`, `pilot_gate_passed=false`, zero dispatched model calls and null success. |
| Baselines | Project v0.1.0 implements Default, seeded Random Search and pinned SMAC 2.4.0 BO. The saved final verification has 700 synthetic attempts and zero model calls. It is not an HPO effectiveness experiment. |
| Space | Three settings, three levels each: 27 configurations, including the default. Context-window feasibility metadata are explicitly synthetic. |
| Split | Proposed 28 validation / 59 test tasks; metadata/provenance grouping review is still outstanding. The validation-only mock roster is frozen, not an approval of a scientific split. Its 28 tasks belong to 17 provisional groups, with sizes 1–4. |
| Unresolved deployment choices | Model/provider, credential-variable name, reviewed runtime image, live cost enforcement and spending approval remain absent from the saved pilot configuration. This phase does not invent them. |

Sources: [frozen source lock](sources/source_lock.json); [Phase 2 blockers](phase2_feasibility_verification.md#exact-blockers-and-smallest-compliant-alternative); [Phase 3 report](phase3_baseline_validation_report.md); [project `hpo/methods.py`, lines 10–78](../hpo/methods.py); [space](../configs/hpo_space.json); [validation projection](../configs/hpo_validation_tasks.json); [split metadata](sources/proposed_split.json). Local source hashes and current checkout status are captured in the Phase 4 evidence file.

### What can actually be said about the three parameters?

| Exact official setting | Shared levels; native default in bold | Verified behavior | Performance/interaction evidence still needed |
|---|---|---|---|
| `defaultThinkingLevel` | `low`, **`medium`**, `high` | Pi resolves the requested level against model support. Unsupported levels can collapse to the same effective setting, including `off` for a non-reasoning model. | Confirm distinct effective levels for the fixed provider/model. Measure success, tokens, USD and time on the same validation tasks. A reasoning label is not a guaranteed amount of useful computation. |
| `compaction.reserveTokens` | `8192`, **`16384`**, `32768` | With compaction enabled, the source threshold is `contextTokens > contextWindow - reserveTokens`; raising the reserve lowers this threshold. | Establish whether any relevant runs reach the threshold. A short successful task may not exercise this setting. |
| `compaction.keepRecentTokens` | `10000`, **`20000`**, `40000` | The cut-point calculation retains approximately this much recent context, subject to valid message boundaries. | Establish actual compaction and changed retained context. A different cut point need not change the final task outcome. |

Official Pi **commit `f321e5…`** sources: [`packages/coding-agent/docs/settings.md`, lines 11–18](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L11-L18) and [lines 69–82](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/docs/settings.md#L69-L82); [`packages/coding-agent/src/core/settings-manager.ts`, lines 833–879](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/settings-manager.ts#L833-L879); [`packages/coding-agent/src/core/sdk.ts`, lines 253–278](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/sdk.ts#L253-L278); [`packages/ai/src/models.ts`, lines 1261–1290](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/ai/src/models.ts#L1261-L1290); [`compaction.ts`, lines 267–270](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/compaction/compaction.ts#L267-L270) and [lines 431–475](https://github.com/earendil-works/pi/blob/f321e5bdd26b3624bfb2ab182a334d0a5edb698a/packages/coding-agent/src/core/compaction/compaction.ts#L431-L475).

**Source-function evidence only:** the saved probes changed a synthetic compaction decision from false to true and changed retained-message counts; they also showed low/medium/high collapsing to `off` for a synthetic non-reasoning model. They did not execute a real provider call, the complete settings/ACP path or actual summarization. Exact probe results（本地或历史材料，未打包：`../runs/archive/pi-setup-20261026/phase2-preflight-20261025/pi-function-probes.json`）.

**Hypotheses, not findings:** reserve × recent-context length is plausible because the controls determine when compaction happens and what remains afterward. Thinking × either compaction control could matter if reasoning changes context growth or task duration. These hypotheses justify measuring **all three pairs**, including pairs whose marginal effects appear small. They do not justify assigning an informative interaction prior or excluding an apparently unimportant parameter.

The Phase 3 mock is also unsuitable as empirical evidence. Its latent quality expression is additive, but thresholded task outcomes and configuration-dependent injected faults can create nonadditivity in a finite binary panel. Its tokens and costs are synthetic. Do not fit a claimed Pi interaction model to those logs. [Project v0.1.0 `hpo/evaluation.py`, lines 53–83](../hpo/evaluation.py).

**Activation gate before an effectiveness claim:** verify requested versus effective settings, context usage, whether compaction occurred and available compaction records through existing external logs/interfaces. Do not modify Pi to add instrumentation. The hello-world smoke task can establish integration but cannot establish sensitivity on long benchmark tasks. Keep every scheduled validation task in the primary outcome; selecting only tasks that compacted under a candidate would select on a consequence of the intervention. If a dimension is inactive, report it; any revised space requires a new common protocol for every method before formal search/test evaluation.

Keep three questions separate: **RQ1**, do the settings change effective runtime behavior; **RQ2**, are individual or pairwise outcome/cost contrasts distinguishable from uncertainty on the chosen validation panel; and **RQ3**, does using those contrasts improve configuration selection under the same budget? Passing RQ1 does not establish RQ2, and finding an interaction in RQ2 does not establish an optimizer advantage in RQ3. The present evidence answers only part of RQ1 at source-function level.

## 2. Mathematical formulation

Everything in this section is our proposed formalization of the inherited protocol, not a claim from a paper.

Hold fixed harness revision \(h\), model/provider revision \(m\), adapter/environment, skill policy, prompts, tools, retry policy, verifier and timeouts, collectively \(P\). Let

\[
\Theta=\{\text{low,medium,high}\}\times\{8192,16384,32768\}
\times\{10000,20000,40000\}\cap\mathcal F_P,
\qquad \theta_0=(\text{medium},16384,20000).
\]

\(\mathcal F_P\) is a **predeclared** feasibility filter using actual fixed-model metadata. All 27 points pass the current synthetic filter; that does not establish real feasibility. If the real filter removes an initial-screen corner, revise the design for all methods before execution, rather than silently replacing a missing contrast with zero. [Current grid and feasibility provenance](../configs/hpo_space.json), [project `hpo/config.py`, lines 74–98](../hpo/config.py).

For validation task \(t\in V\), define \(Y_t(\theta,\omega)\in\{0,1\}\) as official full success, \(C_t\) as accounted USD and \(\tau_t\) as elapsed time; \(\omega\) includes solver and environmental randomness. The target and one-panel observation are

\[
F_V(\theta)=\frac1{|V|}\sum_{t\in V}\mathbb E_\omega[Y_t(\theta,\omega)],
\qquad
\widehat F_V(\theta)=\frac1{|V|}\sum_{t\in V}Y_t(\theta,\omega_t).
\]

The search policy selects \(\theta_{n+1}\) from its own history
\(H_n=\{\theta_r,(Y_{rt},C_{rt},\tau_{rt},\text{failure}_{rt})_{t\in V}\}_{r=1}^n\).
The objective is a high expected quality of the configuration selected within the common search budget. Operationally, select the **best observed eligible complete panel**, with lower panel USD, lower runtime and a stable configuration hash as successive tie-breakers:

\[
\hat\theta=\arg\min_{\theta\in H_{\mathrm{eligible}}}
\left(-\widehat F_V(\theta),\sum_t C_t,\sum_t\tau_t,\operatorname{hash}(\theta)\right).
\]

This does not pretend that the maximum observed score is an unbiased estimate of the best expected score. A single panel can overestimate its winner; the held-out evaluation measures that generalization risk.

**Budget:** each search method has \(Q|V|\) charged task-attempt slots, plus the same declared USD and wall-time ceilings. Every dispatched failure/timeout consumes a slot and its incurred cost. A full panel is required for an incumbent update; partial panels remain logged and charged. The current controller enforces this with mock measurements. [Project `hpo/runner.py`, lines 138–205](../hpo/runner.py), [`hpo/budget.py`, lines 6–65](../hpo/budget.py).

Equal attempt budgets and equal USD ceilings do **not** mean identical realized dollar spending. Preserve the inherited attempt-budget comparison and also plot incumbent performance against cumulative accounted USD. For comparisons at a common dollar amount, use the most recently completed panel at or below that amount, without interpolation using a later result. A safety stop or missing accounting makes the comparison incomplete; do not claim equal completed budgets. Replacing the primary budget with a dollar-only stopping rule would require a protocol decision before experiments.

**Scoring and isolation:** retain the saved rule `raw_reward == 1.0`. Partial/missing reward and operational failures are nonpasses unless an explicit successful reward exists; retain raw reward and diagnostics. Unknown cost/usage triggers the common measurement stop. Search sees only the validation roster and normalized observations. Freeze all method/seed winners before unlocking any held-out outcome. [Project `hpo/evaluation.py`, lines 9–28](../hpo/evaluation.py), [`hpo/runner.py`, lines 165–197](../hpo/runner.py), [pinned BenchFlow scoring, lines 194–227](https://github.com/benchflow-ai/benchflow/blob/99baefb602674bbd31139fd2f1a22c3ed45752f9/src/benchflow/_utils/scoring.py#L194-L227).

Search seeds control initialization, proposal sampling and scheduling. A Pi/provider RNG seed is **not** added to the configuration space or claimed to be supported. Identical task IDs allow paired analysis; they do not ensure identical random model draws.

## 3. What “importance” and “interaction” mean

### Global target: useful definition, inappropriate primary estimator at this sample size

On a product grid with a stated uniform reference distribution, a functional decomposition is

\[
F(\theta)=f_0+\sum_i f_i(\theta_i)+\sum_{i<j}f_{ij}(\theta_i,\theta_j)+f_{123}(\theta),
\]

where \(f_i=\mathbb E_{-i}F-f_0\), \(f_{ij}=\mathbb E_{-(i,j)}F-f_0-f_i-f_j\), and a component's importance is its variance contribution divided by \(\operatorname{Var}(F)\). If total variance is zero, normalized importance is undefined. Changing the domain/reference distribution changes the result; a constrained non-product domain needs a different, explicitly specified decomposition.

fANOVA estimates such quantities from a fitted response model, commonly a random forest. That is a useful optional descriptive analysis, but it is not direct evidence of a causal mechanism or automatically a candidate-selection algorithm. [Hutter, Hoos and Leyton-Brown, ICML 2014, §3.1–3.2, Eqs. 4–6 and Algorithm 2, PDF pp.4–5](https://proceedings.mlr.press/v32/hutter14.pdf).

For three three-level factors, an unrestricted main-plus-pair model has

\[
1+3(3-1)+\binom32(3-1)^2=19
\]

coefficients. Twelve distinct configurations give a design rank at most 12. Twenty-eight task outcomes at each point do not create new configuration design rows. Regularization can produce predictions but cannot supply the missing information. We therefore **do not propose fitting 19 coefficients, a new Bayesian surrogate, or a forest solely to manufacture interaction rankings** from the initial small history. A later exploratory fANOVA must disclose configuration coverage and predictive checks using validation-task data only.

### Proposed primary estimator: matched observed contrasts

Use only this method's completed, measurement-valid panels under the same protocol. Preserve per-task observations, including operational nonpasses; do not discard difficult tasks or inconvenient failures. Historical runs from a different model, skill mode, timeout or settings-resolution path are not interchangeable. Old mock histories are never warm starts. Real warm-start data would need an explicit common-information policy and budget charge for every method.

For an observed edge changing only coordinate \(i\), with the other coordinates fixed at \(z\), define

\[
D_{i,t}(a,b;z)=Y_t(b,z)-Y_t(a,z),\qquad
\hat\Delta_i=|V|^{-1}\sum_t D_{i,t}.
\]

For a completed rectangle changing coordinates \(i,j\) and fixing every other coordinate at the **same** \(z\), define

\[
D_{ij,t}=Y_t(a_1,b_1,z)-Y_t(a_1,b_0,z)
-Y_t(a_0,b_1,z)+Y_t(a_0,b_0,z),
\qquad \hat\Delta_{ij}=|V|^{-1}\sum_t D_{ij,t}.
\]

This is a difference of differences on the **pass-probability scale**. It asks whether the effect of one setting depends on the other setting at these levels/backgrounds. Orient levels by the frozen domain order when storing contrasts; preserve signed estimates and raw cells. An incomplete rectangle is **unidentified**, not a zero interaction. Unmatched averages of all trials using “high” versus “low” are unsuitable because the other settings were selected adaptively.

An interaction is also not a guaranteed improvement. For example, hypothetical cell means \((F_{00},F_{10},F_{01},F_{11})=(.50,.40,.40,.45)\) give a positive interaction of .15, while the joint change still loses .05 relative to the baseline. Signs and actual panel scores must both be reported. Interactions on the probability scale may differ from interactions on a logit scale; neither alone proves an internal causal coupling.

Repeat the same contrasts separately for USD and runtime when their measurements are valid. Report actual and estimated USD provenance separately. Cost sensitivity is an explanatory result and the incumbent's secondary criterion; do not silently introduce a tunable `success − lambda × cost` objective.

### Conservative stability weights: a search heuristic, not a significance test

**Proposed constants to freeze before implementation experiments:** 2,000 bootstrap resamples; practical threshold \(\epsilon=.05\), meaning five percentage points on the contrast scale; at least eight validation groups; leave-one-group-out sign/size stability at least .8. These are design choices, not literature-derived optimal settings. Do not tune them on the test set or run another hidden HPO campaign over them.

For each completed edge or rectangle \(h\):

1. Resample the frozen validation **groups** with replacement, using the same group draw across all cells/configurations. Compute a task-weighted contrast: sum the sampled group numerators and divide by the sampled number of tasks. Do not replace the primary task-weighted objective with an unweighted average of group means.
2. Let \(u_h\) be the 95th percentile of \(|\hat\Delta_h^*-\hat\Delta_h|\). Let \(s_h\) be the fraction of leave-one-group-out estimates with the same sign as \(\hat\Delta_h\) and magnitude greater than \(\epsilon/2\).
3. Define a conservative routing weight

\[
w_h=\mathbf1\{G\ge8,\ s_h\ge.8\}
\max(0,|\hat\Delta_h|-u_h-\epsilon).
\]

At the current incumbent \(x\), use only edges whose background equals \(x_{-i}\), and rectangles whose background equals \(x_{-(i,j)}\). Define \(I_i(x)\) and \(J_{ij}(x)\) as the root mean square of their \(w_h\) values, respectively. Empty evidence sets are marked unknown, with a zero routing weight. Record the number of observed edges/rectangles and levels covered alongside every score. Never compare an \(I\) numerically with a \(J\); they have different contrast scales and different action slots.

This rule avoids transporting an interaction across an unobserved background. Applying a block's weight to its unseen third level is still a **search heuristic**, not an estimated gain at that third level. Strongly heterogeneous task effects can cancel; sparse coverage and only 17 provisional groups can make these weights mostly zero.

The bootstrap quantifies variation across the observed task groups conditional on the recorded solver draws. It does not estimate unobserved repeat-run variance, and these adaptively reused weights are **not calibrated p-values or confidence sequences**. A positive routing weight is not permission to write “statistically proven interaction.” For a scientific claim, predeclare the initial three contrasts, account for their multiplicity and obtain independent validation confirmation if approved; otherwise report them as exploratory estimates with uncertainty.

## 4. Candidate-selection policy and pseudocode

Working name: **interaction-guided block search (IGBS)**. This is our application-specific design, adapted from factorial contrasts, local search and interaction grouping. It is not yet implemented.

### Charged initial design

Choose one of the two nondefault values for each coordinate using a recorded initialization seed. Evaluate the native default, the three single-coordinate changes, and the three two-coordinate changes: **seven configurations**, each on the entire validation panel. All points are distinct and all costs count against this method's budget, including its own default evaluation. The separate Default reference is not a free observation.

This gives one contrast for every pair at the default background, regardless of marginal-effect size. It covers only two levels of each parameter and omits the triple-change corner. Seven observations saturate an intercept + three main + three pair model on this restricted design; they cannot test a three-way effect or provide residual degrees of freedom for that model. No additive-model fit is needed to compute the observed contrasts.

If \(Q<7\), this design is infeasible; use the separately approved fallback. If the screen is interrupted, keep its charges and report incomplete work. At the current illustrative \(Q=12\), the screen uses 58.3% of the search and leaves five adaptive proposals.

### Subsequent proposal rule

Repeat the fixed action sequence **pair → single → global**, starting with a pair action. Thus the five remaining proposals at \(Q=12\) are pair, single, global, pair, single.

- **Pair action:** among pairs having at least one unseen feasible configuration differing from the incumbent in exactly those two coordinates, choose the pair with the highest positive \(J_{ij}(x)\). Break ties with a dedicated seeded RNG. If all eligible weights are zero/unknown, choose an eligible pair uniformly. Sample uniformly among that pair's unseen feasible two-coordinate changes.
- **Single action:** apply the analogous rule using \(I_i(x)\) and unseen configurations differing in exactly one coordinate.
- **Global action:** sample uniformly from all unseen feasible configurations.

If a local action has no eligible block, use a global action. If the grid is exhausted, stop. Do not create free probes, reuse a previous evaluation as a new attempt, change fidelity, or repeat a configuration to repair an unfavorable outcome. Recompute estimates after each completed panel. Maintain independent deterministic RNG streams for initialization, block ties, candidate sampling and bootstrap draws so that a diagnostic change does not accidentally alter unrelated sampling.

```text
INPUT: frozen space Θ, default θ0, validation roster/groups V,
       protocol P, budget ledger, seeds, Q, mode ∈ {IGBS, pair_blind}
H ← empty private history; seen ← empty set
screen ← [θ0, three seeded single changes, three corresponding double changes]

FOR θ in screen:
    if common budget cannot permit next dispatch: stop via common controller
    mark θ seen; evaluate on the full V using the common controller
    retain all attempts, outcomes, measurements and charges
    if panel is complete and measurement-valid: append panel to H
    otherwise: stop or follow the common safety-stop rule; do not nominate partial panel

FOR action in repeating [PAIR, SINGLE, GLOBAL] until Q panels or budget stop:
    x ← common score / cost / runtime / hash incumbent from H
    compute matched-edge I and matched-rectangle J from H at background x
    if mode is pair_blind: replace J routing weights by zero
    enumerate eligible unseen blocks for action at x
    if action is GLOBAL or no block is eligible:
        θ ← seeded uniform unseen feasible point
    else:
        block ← highest positive eligible weight, or seeded uniform eligible block
        θ ← seeded uniform unseen point changing exactly that block at x
    mark θ seen
    log candidate, action, evidence coverage, weights and fallback reason
    evaluate θ through the same full-panel controller; charge every attempt
    append only complete measurement-valid panel to H; retain all other records

RETURN common incumbent and complete audit history
```

The method uses an effect map to decide **which coordinates to explore**, not a global prediction of which candidate has the largest expected improvement. The signed contrasts are explanatory; the routing weight uses magnitude because both beneficial and harmful dependencies can make joint exploration useful. Whether this routing is better than uniform pair selection is exactly the primary ablation question.

## 5. Difference from the actual BO baseline

The comparator is the existing **SMAC 2.4.0** implementation, not a deliberately weak additive BO. Its random forest can represent interactions through successive splits. It would be incorrect to claim that standard BO ignores interactions. [Project `hpo/methods.py`, lines 33–78](../hpo/methods.py), recorded BO components（本地或历史材料，未打包：`../runs/phase3-baselines-20261025-reproducible/bo-components.json`）, [SMAC v2.4.0 HPO facade, lines 24–108](https://github.com/automl/SMAC3/blob/v2.4.0/smac/facade/hyperparameter_optimization_facade.py#L24-L108).

| Aspect | Existing SMAC BO | Proposed IGBS |
|---|---|---|
| Model of outcomes | Ten-tree random-forest surrogate over configuration coordinates | Observed matched contrasts; no global response surrogate |
| Next-candidate mechanism | Log expected improvement with upstream local/sorted-random maximization and random exploration | Fixed pair/single/global cadence; contrast weights select a block; sample an unseen point in it |
| Interaction treatment | Implicit in the surrogate; no requirement for complete four-cell rectangles | Explicit local rectangles with task-paired outcomes; missing rectangles remain unknown |
| Initialization at Q=12 | Three charged Sobol configurations, then nine proposals | Seven charged structured configurations, then five proposals |
| Observation interface | One panel loss, `1 − pass_fraction`, per tell | Same underlying observations, additionally uses within-task contrasts from its own panels |
| Handling noise | Frozen one-observation-per-panel baseline; `deterministic=True` suppresses repeat scheduling, not real solver randomness | Descriptive group uncertainty and stability shrinkage; no calibrated sequential inference |
| Exploration | Upstream random-design probability .2 and recorded library fallback | One global slot per three adaptive proposals, uniform block fallback when evidence is weak |
| Cost treatment | Common ledger and common incumbent tie-break; no claim of a cost-aware acquisition | Same ledger/tie-break; separate cost sensitivity diagnostics, no paid optimizer model |
| Expected limitation | Surrogate extrapolation from few configurations may be unreliable | Expensive screen and sparse local rectangle coverage may leave little useful guidance |

Sources for frozen BO details: [Phase 3 baseline report](phase3_baseline_validation_report.md#baseline-implementations), [SMAC v2.4.0 random design, lines 169–181](https://github.com/automl/SMAC3/blob/v2.4.0/smac/facade/hyperparameter_optimization_facade.py#L169-L181), recorded `bo-components.json`（本地或历史材料，未打包：`../runs/phase3-baselines-20261025-reproducible/bo-components.json`）. IGBS entries are proposed design choices.

Comparable information means the same validation outcomes and cost records are available under the evaluation contract, not that all algorithms must use identical statistics. BO remains the documented aggregate-loss baseline; it does not receive test information or fewer evaluation resources. Initialization differences belong in the end-to-end method comparison; they are controlled separately in the pair-blind ablation. Do not replace BO's acquisition with an interaction score and still call it the standard baseline.

## 6. Prior work and defensible novelty

The following are accessible primary sources. Page locators refer to the specified PDFs, not an inferred latest version. The six supplied course papers also have local file hashes in the existing material inventory（本地或历史材料，未打包：`sources/research/local_materials.json`）.

| Work and exact locator | Relevant established idea | Difference and limitation for this project |
|---|---|---|
| **Hutter, Hoos & Leyton-Brown, ICML 2014**, [fANOVA paper](https://proceedings.mlr.press/v32/hutter14.pdf), §3.1–3.2, PDF pp.4–5, Eqs.4–6/Alg.2 | Model-based marginal effects and variance contributions of parameter interactions. | Our direct local contrasts are not global fANOVA importance. Reusing HPO history for importance is established, not novel. |
| **Omidvar et al., IEEE TEVC 18(3), 2014**, DOI `10.1109/TEVC.2013.2281543`, [accepted manuscript](https://eprints.whiterose.ac.uk/id/eprint/156228/1/PID2794611.pdf), §III Theorem 1/Eqs.3–4, PDF p.5; §III.A/Alg.1, p.6 | Differential grouping detects nonseparability by comparing finite differences and groups interacting variables for optimization. | The central interaction-test-to-search-group idea already exists. Its large-scale continuous optimization setting does not validate our noisy binary-outcome estimator. Local inspected copy（本地或历史材料，未打包：`sources/phase4/differential_grouping_accepted.pdf`）. |
| **Hutter et al., JAIR 36, 2009**, [ParamILS](https://www.cs.ubc.ca/labs/algorithms/Projects/ParamILS/papers/09-JAIR-ParamILS.pdf), §3.1–3.2, PDF p.7; Framework 1, p.8 | Algorithm configuration with one-exchange local neighborhoods, perturbations and random restarts. | Local configuration search and escape moves are established. We adapt a small block-routing policy; we do not reproduce or rename ParamILS. Local inspected copy（本地或历史材料，未打包：`sources/phase4/paramils_jair2009.pdf`）. |
| **Baptista & Poloczek, ICML 2018**, [BOCS](https://proceedings.mlr.press/v80/baptista18a/baptista18a.pdf), §3.1–3.3, PDF pp.2–4, Eq.1/Alg.1 | A sparse Bayesian model explicitly includes pairwise binary interactions and uses sampled model coefficients for acquisition optimization. | “BO with pairwise interactions” is already prior art. IGBS has no Bayesian response posterior or acquisition optimizer; our three-level space also differs from its binary formulation. |
| **Fawcett & Hoos, MIC 2013 conference version**, [ablation analysis](https://www.cs.ubc.ca/~hoos/Publ/FawHoo13.pdf), §3/Alg.1, PDF pp.3–4 | Greedy source-to-target parameter changes identify a useful configuration path. | Importance is path-dependent. A tuned-versus-default ablation alone cannot establish all pairwise interactions or their role during search. The conference PDF was accessed; no claim is made to have read a different journal version. |
| **Lindauer et al., JMLR 2022**, [SMAC3](https://www.jmlr.org/papers/v23/21-0888.html), §2.1–2.4, PDF pp.2–4 | Modular surrogate, acquisition, initialization and intensification for BO/configuration. | Supplies the baseline rationale. The installed 2.4.0 implementation is pinned separately; the paper is not evidence of superiority on this agent benchmark. |
| **Bergstra & Bengio, JMLR 2012**, [Random Search](https://www.jmlr.org/papers/v13/bergstra12a.html), abstract | Random Search is a meaningful baseline where the relevance of parameters is uneven. | It does not prove that our three controls have unequal importance or that a custom search improves on random sampling. |
| **Li et al., JMLR 2018**, [Hyperband](https://www.jmlr.org/papers/v18/16-558.html), §3.1–3.4, PDF pp.6–10, Alg.1 | Resource allocation through successive halving and brackets. | Not an interaction estimator. Introducing task-prefix racing now would change the full-panel protocol and confound the interaction ablation. |
| **Harness-Bench, arXiv:2605.27922v2**, [versioned paper](https://arxiv.org/pdf/2605.27922v2), §3.2–3.3 p.4; §4.1 p.5; §5.3–5.4 p.8 | Model–harness interaction residuals and context-handling failure analysis motivate checking dependencies. | This is a different intervention: changing harnesses/models, not the three Pi controls. Pi is absent from its seven-harness study. One run per combination does not establish repeat variance. |
| **Finding the Right Fit, arXiv:2610.00917v1**, [versioned paper](https://arxiv.org/pdf/2610.00917v1), §3 pp.3–4; §7 p.12; App.A–B pp.14–15 | Model–harness rankings depend on task setting; requested reasoning labels need careful interpretation. | Its Pi is 0.84.4, not our snapshot. It does not isolate these parameter pairs and does not measure run-to-run variance. |
| **HarnessOpt-Bench, arXiv:2608.06301v1**, [versioned paper](https://arxiv.org/pdf/2608.06301v1), §3 pp.5–6; §4 p.7; limitations pp.10–11 | Protected test evaluation, metered feedback and immutable candidate records. | Its optimizer edits harness code, which is prohibited here. We borrow evaluation discipline, not its intervention. |

**What is adapted:** finite-difference interaction contrasts, task pairing, resampling, local neighborhoods, random exploration, interaction-based grouping, cost accounting and held-out selection discipline. None is claimed as a new mathematical discovery.

**What could be a student contribution in this application:** the explicit combination of local contrast stability, a fixed pair/single/global policy, a no-evidence fallback and complete cost accounting for three officially exposed Pi settings under an immutable harness; plus an empirical answer to whether interaction guidance helps this fixed model/benchmark setting. The matched pair-blind ablation makes that answer falsifiable. This is an application-specific design and evaluation contribution, **not a claim of first-ever interaction-aware HPO**. A negative result is legitimate; it should not be rewritten as demonstrated interaction benefit.

All papers used above were accessible through the supplied PDFs, publisher or author/institutional copies. Author repositories or software releases were not installed or reproduced in Phase 4. This is a focused prior-art review, not proof that no earlier method implements an identical combination. [Earlier six-paper review and access/version caveats](literature_review.md).

## 7. Noise, identifiability and small-sample risks

### How weak is a 28-task panel?

These are analytic illustrations, **not estimates of SkillsBench variance**. If independent Bernoulli task outcomes have probability .5, a 28-task pass fraction has standard error \(.5/\sqrt{28}=.0945\), giving a normal-approximation 95% half-width about .185. For a four-cell interaction with independent Bernoulli cells at .5, each task contrast has variance 1, so its panel mean has standard error \(1/\sqrt{28}=.1890\), half-width about .370. That is very coarse relative to five- or ten-percentage-point interactions.

Actual paired variance depends on covariances among the four cells. For a single-coordinate difference, \(\operatorname{Var}(D)=q-\Delta^2\), where \(q\) is the probability that the paired outcomes disagree. Pairing can help but is not guaranteed to reduce variance. A pair contrast lies in \([-2,2]\), so its variance is at most 4; using independence to plan can be optimistic. Related tasks reduce the effective amount of information further.

For an illustrative two-sided test with 80% power,

\[
N\approx\frac{(z_{1-\alpha/2}+z_{.8})^2\sigma_D^2}{\delta^2}.
\]

With \(\sigma_D^2=1\), the approximate numbers of **independent task-level four-cell contrasts** are:

| Interaction magnitude \(\delta\) | One prespecified pair, α=.05 | Three prespecified pairs, Bonferroni α=.05/3 |
|---|---:|---:|
| .20 | 197 | 262 |
| .10 | 785 | 1,047 |
| .05 | 3,140 | 4,188 |

Each contrast requires four configuration outcomes on the same task; shared cells can reduce execution counts when estimating several contrasts. These normal approximations are planning illustrations, not exact binary-test guarantees. Repeating the same 28 tasks may reduce conditional solver noise, but does not create hundreds of independent task families. The proposed validation set cannot support a strong claim about modest interactions simply by calling its 336 attempts “336 independent samples.”

### Required interpretation rules

- **No effect versus no evidence:** a zero/unstable estimate is not evidence that an interaction is absent. A defensible “practically negligible” statement would require an uncertainty interval lying inside a prespecified equivalence band; that is unlikely with this budget.
- **Adaptive reuse and multiple comparisons:** exploring many rectangles, thresholds and subgroups then reporting only the strongest effect overfits validation data. Preserve all diagnostics; keep three initial pair contrasts as the prespecified descriptive family. Do not turn repeated bootstrap checks into repeated significance claims.
- **Task diversity versus solver randomness:** group resampling covers variation across observed families, not repeat-call variance. A bootstrap can have zero spread when all recorded outcomes coincide even though another solver run could differ.
- **Binary floors/ceilings and scale:** all-pass/all-fail panels can hide internal differences. Thresholded binary success can be nonadditive despite an additive latent score. Inspect cost/context diagnostics without changing the primary outcome after seeing results.
- **Sparse coverage:** a pair may matter only at the third level or another background. A pure three-way effect is not identified by the seven-point screen. The global exploration slot mitigates trapping but does not solve identifiability.
- **Drift and infrastructure:** rate limiting, environment errors and provider changes may look like setting effects. Interleave method blocks, keep task order/protocol consistent, log failure categories and stop systemic measurement failures. Infrastructure failures remain in the primary scheduled denominator; an exclusion analysis, if shown, is secondary and cannot choose the winner.
- **Winner's curse:** selection favors noisy high validation scores. Test once after all choices freeze; report all seed winners, not the best seed selected using test data. Three search seeds still give an imprecise estimate of optimizer variability.

At this scale, a credible report can demonstrate a reproducible comparison and transparently report uncertainty. It is unlikely to establish a universal interaction law or a small statistically decisive advantage over BO.

## 8. Ablation and evaluation design

### Primary causal question about the algorithm

**Does using the measured interaction map to choose a pair improve search, beyond merely permitting two-coordinate moves?**

| Arm | Initial points | Adaptive action cadence | Single-coordinate rule | Pair rule |
|---|---|---|---|---|
| IGBS | Same seven seeded points | Pair, single, global | Stable main-effect weights | Stable interaction weights; uniform if unreliable |
| **Pair-blind matched ablation** | Same seven seeded points | Identical | Identical | Always choose an eligible pair uniformly |

Hold the space, task panel, attempt/monetary limits, scoring, fault handling, candidate sampling within a block and seed schedule fixed. Both arms pay for their own screen and all attempts; no cross-arm free cache. Matched configurations can have different live outcomes, so do not promise identical histories. Pair experiments by search seed and task roster, and interleave method blocks. Different subsequent configurations are the legitimate effect of the policy.

If all eligible interaction weights are zero, the two policies reduce to the same pair-selection rule **given identical histories and RNG state**. If IGBS never actually uses a positive weight, the study has not demonstrated an interaction-awareness contribution even if one stochastic run scores higher. Log the fraction of guided pair actions, contrast coverage, selected pairs, fallback counts and candidate disagreements.

**Optional secondary ablation, only if budgeted:** replace every pair slot with a single-coordinate slot. This tests the value of two-coordinate moves and is not a clean test of interaction awareness. An ungated raw-contrast variant could separately test the stability safeguard, but adding it is lower priority than funding repeated primary comparisons. Do not add arms opportunistically after seeing outcomes.

### End-to-end comparison and reporting

Compare Default, Random Search, unchanged SMAC BO, IGBS and the pair-blind arm under the common protocol. Default is a separately charged reference, not a search method with Q panels. All search methods get the same Q and validation panel. Initial designs and all failures consume the method's budget.

Prespecify the primary algorithmic contrast as **IGBS minus pair-blind**. Report BO and Random Search comparisons required by the assignment separately, including negative or zero gains. Suggested outputs are final validation pass counts, incumbent curves by attempts and USD, final test pass@1, validation–test gap, actual/estimated search USD, per-task deployment cost/runtime, failure categories and all paired method differences. Do not compress these into an invented single “efficiency” score.

Use group-paired uncertainty summaries for task differences, preserving correlations across methods. Report per-search-seed results and their dispersion; do not pool all seed × task rows as independent tasks. With only three search seeds, uncertainty about optimizer variation remains large. Test-task failure cases may explain the frozen outcome but must not be fed back into algorithm changes or winner selection.

Before any paid experiment, future automated checks should cover a known null landscape, additive expected success, positive and negative pair interactions, a pure three-way effect, inactive controls and correlated task-family noise. Include known deterministic cells for exact contrast tests, plus seeded Bernoulli simulations to expose false alarms and low power. The current accounting mock alone is insufficient. Test reproducibility, budget invariants and pair-blind equivalence when weights are zero; do not assert that IGBS must beat another optimizer on every seed.

## 9. Budget needed and five-day feasibility

Let \(v=28\), \(t=59\), \(Q\) be panels per search method, \(R\) search seeds, and \(A=1\) when the pair-blind ablation is included. There are \(3+A\) search methods: Random Search, BO, IGBS and optionally the ablation. With Default evaluated once on validation, and **every seed's frozen winner** evaluated once per held-out task,

\[
N_{\mathrm{search}}=(3+A)QvR,\qquad
N_{\mathrm{test}}=[1+(3+A)R]t,\qquad
N_{\mathrm{total}}=N_{\mathrm{search}}+v+N_{\mathrm{test}}.
\]

The test formula does not choose the best search seed. It counts separate frozen method/seed selections, even if some settings coincide; no free reuse is assumed. Model-internal retries and auxiliary calls affect dollars/tokens but do not create a free replacement task attempt.

| Scenario | Search attempts | Default validation | Held-out attempts | Total | Interpretation |
|---|---:|---:|---:|---:|---|
| Q=12, R=1, no ablation | 1,008 | 28 | 236 | **1,272** | Course comparison, but cannot isolate interaction guidance |
| Q=12, R=1, with ablation | 1,344 | 28 | 295 | **1,667** | Exploratory mechanism comparison; no optimizer-seed variance estimate |
| Q=12, R=3, no ablation | 3,024 | 28 | 590 | **3,642** | Repeated search comparison; interaction attribution still missing |
| Q=12, R=3, with ablation | 4,032 | 28 | 767 | **4,827** | Provisional minimum for a repeated, explicitly qualified interaction-guidance comparison |
| Q=18, R=3, with ablation | 6,048 | 28 | 767 | **6,843** | More adaptive search after the screen; likely difficult within five days |

The **4,827-attempt** recommendation is an engineering minimum for a modest repeated comparison, not a power guarantee. It still has only 28 validation tasks, 17 provisional groups and three search seeds; it cannot substantiate small interactions by itself. At Q=12, seven screening panels consume 196 of each IGBS seed's 336 attempts. A full 27-point single-panel grid would cost 756 validation attempts before any repetition; exhaustive ground truth is not free or necessary for this project.

**Illustrative costs, not provider prices or measured estimates:** if the eventual mean all-in metered API cost per attempt were $0.02 or $0.10, the totals would be:

| Total attempts | At hypothetical $0.02/attempt | At hypothetical $0.10/attempt |
|---:|---:|---:|
| 1,272 | $25.44 | $127.20 |
| 1,667 | $33.34 | $166.70 |
| 3,642 | $72.84 | $364.20 |
| 4,827 | $96.54 | $482.70 |
| 6,843 | $136.86 | $684.30 |

These omit the integration pilot, any separately approved sensitivity confirmations, container/Modal compute, storage/egress and price drift. Replace the hypothetical rate with pilot measurements and a conservative reservation bound before requesting a campaign ceiling. Record measured billing where available and clearly tagged estimates otherwise, including retries, cache usage and compaction calls. A mean cost is not a safe upper bound for in-flight enforcement.

For time, \(T\approx N_{\mathrm{total}}\bar\tau/p\) is only an optimistic throughput calculation. At 4,827 attempts, three minutes per attempt and four genuinely available concurrent task slots imply about **60.3 hours**; ten minutes imply **201.1 hours**, already beyond five days. At 6,843 attempts those figures are **85.5 / 285.1 hours**. Startup, verification, stragglers, rate limits, search dependencies and engineering time add overhead. Neither these runtimes nor four-way live concurrency have been verified. A single cheap hello-world pilot is insufficient to estimate the tail of heterogeneous benchmark cost.

**Recommendation:** do not approve a dollar amount from these illustrations. First resolve the live integration and activation gates, then choose between (a) an explicitly exploratory Q=12, R=1 study with the primary ablation, and (b) a repeated R=3 study if measured throughput and cost allow. If only the small study fits, narrow the claim rather than dropping the ablation while claiming an interaction benefit. Any smaller benchmark roster must be chosen by a documented metadata rule before outcome inspection and used equally by every method.

## 10. Complexity, expected benefits and failure modes

Let \(d\) be dimensions, \(k\) levels per dimension, \(K=k^d\) grid points, \(N\) evaluated configurations, \(v\) tasks, \(G\) groups and \(L\) bootstrap draws. With constant-time configuration lookup, the complete grid contains at most

\[
E=d\binom{k}{2}k^{d-1}\quad\text{edges},\qquad
P_2=\binom d2\binom k2^2 k^{d-2}\quad\text{rectangles}.
\]

For d=k=3, K=27 and E=P₂=81. Only observed complete contrasts are computed.

| Operation | Bound for a straightforward finite-grid implementation |
|---|---|
| Store per-task outcomes | O(Nv), plus measurement metadata |
| Enumerate grid/neighborhoods | O(Kd) per proposal |
| Build all available contrast vectors/group sums | O((E+P₂)v) time; O((E+P₂)G) group-sum storage |
| Group bootstrap | O(LG(E+P₂)) per full refresh using group sums |
| Initial charged screen | 1+d+binomial(d,2) full panels; O(d²v) task attempts for one alternative per dimension |
| Whole search | At most Qv task attempts; multiply analysis overhead by Q if recomputed after every panel |

At L=2,000 and G=17, the full-grid bootstrap bound involves roughly 5.5 million group/contrast contributions per refresh. This is an arithmetic operation count, **not a measured runtime**. It can be reduced by caching unchanged contrast statistics. No new dependency or optimizer LLM is required by the design. In larger spaces, grid enumeration and coverage become prohibitive; this proposal deliberately targets the current three-parameter problem.

**Expected advantages, conditional on evidence:** interpretable observed contrasts; joint moves even when marginal effects are weak; avoidance of a poorly identified global interaction regression; an explicit uncertainty fallback; and a compact ablation. These are design motivations, not demonstrated gains.

**Expected limitations:** seven expensive startup panels; weak binary-outcome resolution; no calibrated uncertainty about unseen configurations; greedy routing can over-focus on a noisy pair; local evidence may not transfer to the third level; pure three-way effects can be missed; a tiny grid may favor simpler Random Search; and BO already has an interaction-capable surrogate. Absolute interaction magnitude describes dependence, not whether a new point will improve. There is no convergence, regret or sample-efficiency guarantee in this proposal.

## 11. Simpler fallback and implementation boundary

There are two distinct fallbacks:

1. **Inside IGBS:** if pair estimates are unreliable, use uniform eligible pair selection. This preserves the matched ablation's move opportunities and honestly records that interaction awareness did not guide that decision. If all estimates remain weak, do not credit the method with an interaction contribution.
2. **Simpler student algorithm chosen before formal comparison:** seeded coordinate search with periodic global exploration. Start at the native default; propose unseen one-coordinate neighbors of the current incumbent in a seeded order; every third adaptive proposal sample globally from unseen feasible points; retain the common incumbent rule. Rebuild the neighborhood when the incumbent changes, fall back globally if it is exhausted, and charge every full panel. This is a modest local-search adaptation, not a new optimization family. It avoids the seven-point interaction screen and bootstrap machinery.

If the fallback is selected after an already charged screen, that screen remains in the history and budget. No refund, reset or selective reporting. If controls are operationally identical, even the simpler algorithm cannot create information; report the null/inactive setting result or obtain approval for a revised shared space.

### Minimal implementation plan, only after approval

1. **Freeze the design record:** method name, seven-point screen, action cadence, stability constants, seeds, primary pair-blind ablation and claim level. Resolve the outstanding real-model/roster/pilot gates independently; approval of optimizer code is not approval of paid experiments.
2. **Add a small external contrast module** (proposed `hpo/contrasts.py`): matched-corner lookup, per-task/group contrasts, signed diagnostics, stability weights and coverage. It consumes normalized validation results and a validation-only group map; it receives no test paths, task solutions or oracle content.
3. **Add the external policy** (proposed `hpo/interaction_search.py`): initialization queue, three-action scheduler, unseen-candidate selection and the pair-blind mode. Keep Pi and all third-party sources unchanged.
4. **Expose complete panel observations in the controller:** current methods receive only scalar loss and duration in `hpo/runner.py` lines 191–197. Add an observation hook available to all methods while leaving standard BO's scalar tell and components unchanged. Reuse `Space`, serialization, budget ledger, journal, process seeding and isolation. Real USD/runtime normalization remains a prerequisite for live use, not a shortcut inside this optimizer.
5. **Record the decision evidence:** candidate/config hash; requested/effective settings when available; action; matched edge/rectangle IDs; signed estimates; uncertainty/stability and coverage; weights; selected block; fallback reason; all attempts/costs/failures; protocol/library/source hashes. Preserve null versus zero measurements.
6. **Verify offline first:** exact contrast examples and null behavior, missing corners, conditional contexts, same-seed reproducibility, pair-blind equivalence, task-group weighting, failure accounting, no duplicate proposals, incomplete-panel rejection and held-out isolation. Reuse the existing budget tests. Only subsequently request a separately priced real-validation campaign.

After a stable evaluator exists, the policy and focused tests should be a small implementation, approximately one to one-and-a-half working days as a planning estimate. That estimate excludes Docker/model integration and paid runtime. Adding fANOVA software, a second surrogate, multi-fidelity racing, several alternative acquisitions or optimizer-LLM calls is outside the minimal plan.

## 12. Decisions for approval

The concrete choices are now reviewable:

1. **Algorithm direction:** approve IGBS plus the pair-blind primary ablation, or choose the simpler coordinate-search fallback as the student method.
2. **Research claim:** accept an exploratory application study unless sufficient repeated evaluations can be afforded; no prior claim that interactions exist or that IGBS beats BO.
3. **Design constants and scope:** accept the seven-panel screen, pair/single/global cadence and stated conservative stability rule as frozen project choices, without a separate tuning campaign for the optimizer itself.
4. **Later experiment scope:** select R/Q and a real USD/time ceiling only after the outstanding model, integration, activation and split checks. The tables are estimates of required work, not authorization to spend.

**Stop point:** research/design documentation only. Optimizer implementation and all new benchmark runs await the user's approval.
