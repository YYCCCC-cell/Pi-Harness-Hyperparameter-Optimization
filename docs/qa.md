# Likely questions and evidence-based answers

Updated 2026-10-28 for real diagnostics and formal-experiment preparation. Final comparison results remain unavailable; see [acceptance](completion_acceptance_20261028.md).

**1. Did your algorithm improve Pi on SkillsBench?**

We do not know whether IGBS improves Pi. Real task evaluations, parameter diagnostics and cross-task calibration now exist, but no formal four-method search in the reduced protocol or independent heldout evaluation has run. The preserved 4,116 mock attempts cannot answer the performance question. [Current report](research_report_draft.md).

**2. What is student-developed here? Is interaction-aware HPO new?**

We implemented an external policy combining a seven-point local screen, task-paired contrast stability, a fixed pair/single/global schedule and an uncertainty fallback for this three-setting harness problem. Finite-difference grouping, importance estimation and local configuration search already exist. BOCS already models pairwise interactions inside BO. Our novelty claim is an application-specific adaptation and its controlled evaluation, not a new general algorithm family. [Prior-art review with exact paper sections](phase4_interaction_aware_hpo_design.md#6-prior-work-and-defensible-novelty).

**3. Why not just use BO?**

We retain genuine SMAC 2.4.0 as the required baseline. Its random forest can represent interactions. IGBS asks whether explicit local observed contrasts help choose coordinate blocks when little configuration data is available. It may lose because the screen is expensive and the interaction estimates are noisy. The mock provides no evidence of a real advantage. [Baseline code](../hpo/methods.py), [policy code](../hpo/interaction_search.py).

**4. How do you define an interaction?**

For two parameter changes with all other settings fixed, compute the task-paired mean of `Y11 − Y10 − Y01 + Y00`. This measures nonadditivity on the success-probability scale at the observed levels/background. It is not a universal causal property or a promise that the joint change is better than default. Missing a corner means the contrast is unidentified. [Estimator](../hpo/contrasts.py), [mathematical design](phase4_interaction_aware_hpo_design.md#3-what-importance-and-interaction-mean).

**5. What did the interaction ablation show?**

In all three recorded mock seeds, IGBS and pair-blind proposed identical configurations and had zero final-score difference. None of six adaptive pair slots used a positive interaction weight. That is evidence that fallback behavior works, not that interaction guidance improves optimization or that real Pi interactions are absent. A separate exact-synergy unit test exercises the positive-guidance branch. Ablation records（本地或历史材料，未打包：`../artifacts/mock-verification/ablation.json`）, [tests](../tests/test_interaction.py).

**6. Does the ablation isolate interaction awareness?**

The primary ablation retains the same seven initial settings, pair/single/global cadence, single-parameter weighting, candidate sampling, tasks and budgets. Only pair selection changes from estimated interaction weights to uniform selection. Removing all pair moves would confound interaction awareness with move size; that is not our primary comparison. Each arm pays for its own observations. [Phase 4 ablation design](phase4_interaction_aware_hpo_design.md#8-ablation-and-evaluation-design).

**7. Is the seven-point initialization fair against BO's three initial points?**

In the historical mock, all initialization consumes the same total Q=12 panel budget. IGBS therefore has only five adaptive proposals while BO has nine. That cost is part of the end-to-end algorithm comparison. The pair-blind arm controls the initialization when isolating the contribution of pair routing. There are no free sensitivity probes or borrowed Default results. The current real protocol has Q=10, seven IGBS screening configurations and three adaptive choices; optional pair-blind is not run. [Campaign configuration](../configs/hpo_final_mock.json), [controller](../hpo/runner.py).

**8. Are 28 validation tasks sufficient?**

They are sufficient to exercise the pipeline, but small for detecting modest binary-outcome interactions. Under an illustrative independent Bernoulli .5 model, a four-cell panel contrast has standard error about .189 at n=28. Task-family dependence and unknown solver-repeat variance can make inference weaker. Three search seeds do not remove that limitation. Report uncertainty and avoid a superiority claim without supporting data. [Noise/power analysis](phase4_interaction_aware_hpo_design.md#7-noise-identifiability-and-small-sample-risks).

**9. Why are your bootstrap weights not p-values?**

They are an adaptive routing heuristic: observed group resampling plus leave-one-group sign stability and a practical threshold. The same validation data are repeatedly reused; no sequential significance calibration is implemented. They describe observed task-group variation conditional on recorded solver draws, not unseen repeated model calls. [Contrast implementation](../hpo/contrasts.py).

**10. How do you know the parameters actually work?**

Real provider requests verified reasoning levels. Two real task runs triggered automatic compaction at 27,673 and 42,533 context tokens; a separate same-history diagnostic checked retention boundaries. Short tasks can still avoid compaction, and activation does not establish better scores. [Evidence](pi_diagnostic_completion_20261027.md).

**11. How do failures and timeouts affect your scores and budget?**

Every dispatch is charged before execution. A full reward of 1 counts as success; partial/missing reward and operational failures are nonpasses unless an explicit successful reward is present. No outer replacement is allowed. Partial panels cannot nominate an incumbent. Missing cost or tokens stops all methods and remains null. Implicit SDK/router retries are fixed to zero; any Pi-level new request is separately inventoried and charged. [Ledger](../hpo/budget.py), [parser](../hpo/evaluation.py), [controller](../hpo/runner.py).

**12. Are the monetary budgets equal? What did the experiments cost?**

The mock enforces a $0 API ceiling and dispatched no model calls. Synthetic cost units are a separate fixture quantity, not dollars. The user-authorized v8 allocation is $16 per search method (Random, BO, IGBS), $3 for Default and $9 for heldout ($60 total). Planned attempts remain 280, but tighter caps may stop the study before completion. Optional pair-blind is deferred; its isolated contribution cannot be measured by this study. Search caps and attempt entitlements are equal, while actual spending may differ. Dollar curves must use accounted real costs and disclose estimated versus measured components. [Current budget](formal_protocol_20261028_v8/README.md).

**13. What prevents test-set leakage?**

The optimizer receives only a hashed validation roster/group map and its own normalized observations. Automated read guards reject access to the combined split, benchmark files and held-out roster during mock search. The evaluator-owned review manifest contains IDs, not outcomes, and is never passed to the optimizers. The real evaluator stages only authorized tasks and requires all winners frozen before heldout access. These process/software guards are not an adversarial OS security boundary against a malicious controller. [Isolation test](../tests/test_interaction.py), [configuration boundary](../hpo/config.py).

**14. Can you report held-out pass@1 and the generalization gap now?**

No. Those fields are null because formal search and independent heldout have not executed; real diagnostics are separate evidence. After validation selection freezes, each method/seed winner and Default must receive the approved held-out evaluation. Test scores cannot be used to choose the best seed or revise optimizer settings. Current result schema in exported results（本地或历史材料，未打包：`../artifacts/mock-verification/results.json`）, [completion sequence](experiment_instructions.md#sequence-after-the-missing-decisions-are-supplied).

**15. Can the five-day project afford the proposed experiment?**

The original 4,827-attempt plan is historical. The current four-method study plans 280 attempts with a user-authorized $60 allocation. Eight-task mixed-version calibration gives a simple $35.34 cost and 29.62-hour serial extrapolation; higher-cost scenarios may exceed $60, so completion is not guaranteed. Docker/runtime checks and all eight validation environment builds have passed; the remaining start gate is the provider key's available capacity. Formal search and heldout have not run. [Current protocol and limits](formal_protocol_20261028_v8/README.md).

**16. Does a tuned configuration necessarily save deployment cost?**

No. Search is a one-time expense, while the chosen setting changes per-task runtime/API cost. A cheaper setting can amortize search cost; a more expensive one needs a separate justified quality/value argument. The mock's H setting costs more synthetic units than default, but these quantities say nothing about real provider billing. [Economic analysis](research_report_draft.md#5-held-out-and-economic-results-not-yet-available).

**17. What do the representative failure cases prove?**

Only that the reporting path preserves both outcome directions and references exact raw attempts. The mock case tagged `infrastructure_failure` is an injected fixture outcome; no actual astronomy or video-processing task ran. We cannot diagnose Pi reasoning, skill use or compaction without real trajectories. Case export（本地或历史材料，未打包：`../artifacts/mock-verification/failure_cases.json`）.

**18. What remains before you can call the project complete?**

A reviewed live runtime/evaluator, an approved model/split/budget/manifest, a successful bounded integration pilot, fair real validation searches, frozen selections, held-out pass@1 and complete cost/trajectory reconciliation. The optimizer software is ready for that next integration stage; the empirical course deliverables are still incomplete. [Research report status](research_report_draft.md), [approval boundary](experiment_instructions.md).
