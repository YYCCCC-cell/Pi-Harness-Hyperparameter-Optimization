# Literature review for configuration only harness optimization

Prepared 2026-10-25. Six supplied PDFs were accessible and read. They are under `参考论文/`, not the requested `docs/papers/`. The material inventory（本地或历史材料，未打包：`sources/research/local_materials.json`） records original paths, hashes, page counts and text-extraction limitations. PDF page locators below are one-based pages in those local files. Claims under **Paper evidence** are reported findings; **Project use** and **Limits for this project** are our interpretation.

## Harness Bench

**Source:** Yao et al., *Harness-Bench: Evaluating Agent Harnesses across Models and Realistic Workflows*, arXiv:2605.27922 **v2**, 15 October 2026, supplied PDF（本地或历史材料，未打包：`../参考论文/2605.27922v2.pdf`）, [official versioned PDF](https://arxiv.org/pdf/2605.27922v2). Relevant passages: §3.2–3.3, PDF p.4; §4.1, p.5; §5.1, p.6; §5.3–5.4, p.8.

**Paper evidence.** The v2 study uses 300 tasks: 274 general and 26 multimodal. It compares seven harnesses, with ten model backends on general tasks and seven on multimodal tasks. Tasks receive weighted module credit subject to safety gates; full credit and mean reward are different metrics. The evaluation preserves native harness behavior under common external conditions and records API costs, including auxiliary calls. Harness rankings vary by model and completion criterion, and higher spending need not yield higher completion. The paper analyzes an additive model–harness interaction residual and trace-level failures such as losing usable tool evidence during compaction.

**Project use.** Fix the model, environment and scoring while varying documented Pi controls; distinguish complete success from partial progress; include all model calls in costs; inspect failures where context handling or tool feedback plausibly matters. Its interaction residual is a useful analogy for a four-cell parameter contrast, not evidence that a particular pair of Pi settings interacts.

**Limits for this project.** Pi is not among this v2 paper's seven evaluated harnesses. Cross-harness comparisons do not isolate individual hyperparameters. The study runs each task–model–harness combination once (§4.1); do not transfer its ranking or costs to our task set, model, or later Pi revision. Its source modifications and benchmark are not the proposed course experiment.

**Version conflict:** the accessed [arXiv abstract page](https://arxiv.org/abs/2605.27922) describes 106 tasks and 5,194 trajectories, while both the supplied v2 PDF and the official versioned PDF describe 300 tasks. This review uses v2 and does not combine those counts. The PDF title page was visually checked. [Author repository README](https://github.com/Qihoo360/harness-bench/blob/b8d89634c6f445fcc68ceb6744a59bef6cdf4863/README.md#L35-L47) also lists 300 tasks; source snapshot `b8d89634c6f445fcc68ceb6744a59bef6cdf4863` was accessible.

## Finding the Right Fit

**Source:** Li et al., *Finding the Right Fit: Model–Harness Interactions across Agent Tasks*, arXiv:2610.00917 **v1**, 1 October 2026, supplied PDF（本地或历史材料，未打包：`../参考论文/2610.00917v1.pdf`）, [official paper](https://arxiv.org/abs/2610.00917v1). Relevant passages: §3, PDF pp.3–4; §4.3–5.2, pp.8–9; §7, p.12; Appendix A–B, pp.14–15.

**Paper evidence.** It evaluates 66 configurations over TUA-Bench, ALE-CLI and a 63-task non-H100 subset of Terminal-Bench 4. Four configurable harnesses are crossed with five models, with Codex/GPT and Claude Code/Claude native references. All request high reasoning effort, although the authors explicitly caution that an identical label need not imply an identical reasoning budget. Model rankings and preferred harnesses change across tasks; some pairings persist. Matched cases link outcomes to returned failure feedback, continuation and completion checks. Appendix A pins Pi 0.84.4 and Terminal-Bench v4.0.0; this is not our Pi 1.4.0 main snapshot.

**Project use.** Evaluate the chosen configuration in its actual target setting; verify effective reasoning rather than a requested label; record native recovery and output-limit failures. Existing Pi/Harbor integration makes Terminal-Bench a credible alternative. The [authors' code](https://github.com/liyix/finding-the-right-fit/blob/0cd55e1fb3b50fc9e722cb37c8fec234dec073ad/README.md#L90-L123) is accessible and identifies the concrete versions used.

**Limits for this project.** §7 states that settings, tools and budgets are not uniformly matched, one run is counted per task, and run-to-run variance is not measured. Its trajectory-based mechanism suggestions are not tested improvements. The reported 63-task subset is not the entire 66-task TB4 release. The study counts the last rerun's reward and cost (§3.1); our cost ledger should retain every billed attempt. Do not import its task solutions or trajectories into our search, nor infer a universally best model from its leaderboard.

## HarnessOpt Bench

**Source:** Ursekar et al., *HarnessOpt-Bench: Evaluating LLMs at Harness Optimization*, arXiv:2608.06301 **v1**, 6 August 2026, supplied PDF（本地或历史材料，未打包：`../参考论文/2608.06301v1.pdf`）, [official paper](https://arxiv.org/abs/2608.06301v1). Relevant passages: §3.1–3.2, PDF pp.5–6; §4, p.7; §5.3 and Limitations, pp.10–11.

**Paper evidence.** An optimizer edits a seed harness within a metered target-evaluation budget, nominates a candidate, and is scored on a hidden test partition using normalized gain over the seed. The suite fixes target models, environments and verifiers, separates development/validation/test disclosure, preserves candidates, and runs target evaluations in fresh sandboxes. It studies five optimizer models across four downstream tasks, reporting 111 scored runs. Test scores use three attempts per case, while optimizer inference is metered but uncapped in the reported setup. Small observed differences are treated cautiously using descriptive resolution bands.

**Project use.** Borrow the immutable candidate ledger, evaluator-owned holdout, cost accounting and separation of optimizer from solver. Track validation optimism and avoid fine rankings unsupported by noise estimates. The [official implementation directory](https://github.com/scaleapi/vero/blob/d1400011917ff66b7c122e7a787d547372f43e97/harness-opt-bench/README.md#L7-L38) is accessible inside `scaleapi/vero`; it documents disclosure levels and pinned per-benchmark configurations.

**Limits for this project.** Editing harness code is central to this paper and prohibited by our assignment. Its normalized-gain objective and three-attempt scoring cannot replace the required pass@1. Python-only candidates, task-specific seed quality, one target model per task and possible adaptation to stable evaluators limit generalization. GAIA's non-functional seed is a construction task rather than tuning a mature harness. Use the protocol lessons, not its code-editing intervention or an expensive optimizer LLM. The accessed repository snapshot is not claimed to be the exact release used for every v1 result.

## SMAC3

**Source:** Lindauer et al., *SMAC3: A Versatile Bayesian Optimization Package for Hyperparameter Optimization*, JMLR **23(54):1–9, 2022**, supplied PDF（本地或历史材料，未打包：`../参考论文/21-0888.pdf`）, [publisher page](https://www.jmlr.org/papers/v23/21-0888.html). Relevant passages: §2.1–2.4, PDF pp.2–4; §3 and §5, pp.4–5.

**Paper evidence.** SMAC3 provides modular surrogate-based optimization with different presets: Gaussian-process BO for low-dimensional continuous spaces; random-forest models for structured and conditional spaces; multi-fidelity optimization; and algorithm configuration across problem instances with racing. Its framework separates configuration space, initial design, surrogate, acquisition, intensification and target evaluation. The empirical illustration uses conventional HPO surrogate/tabular benchmarks rather than LLM-agent runs.

**Project use.** It is a defensible standard BO baseline for a finite mixed Pi space. Treat `1 - validation pass fraction` as loss. Freeze the library version, surrogate, acquisition, initial design and evaluator contract. If the main comparison uses full-panel evaluations, avoid silently giving the BO baseline extra racing or a different fidelity schedule. The [official repository](https://github.com/automl/SMAC3) and [documentation](https://automl.github.io/SMAC3/) were accessible; nothing was installed.

**Limits for this project.** The paper does not establish sample efficiency on noisy Pi/SkillsBench evaluations. With very few configurations, surrogate uncertainty can be poorly calibrated. Modern SMAC APIs and dependencies may differ from the 2022 facade names, so the paper's names are not installation instructions. SMAC itself is the required baseline, not a student-developed algorithm merely because we wrap it or use its random forest for analysis.

## Functional ANOVA for hyperparameter importance

**Source:** Hutter, Hoos and Leyton-Brown, *An Efficient Approach for Assessing Hyperparameter Importance*, ICML **2014**, PMLR **32(1):754–762**, supplied PDF（本地或历史材料，未打包：`../参考论文/hutter14.pdf`）, [publisher page](https://proceedings.mlr.press/v32/hutter14.html). Relevant passages: §2, PDF pp.3–4; §3.1–3.3 and Algorithm 2, pp.4–5; experiments and conclusion, pp.6–9.

**Paper evidence.** Random-forest predictions provide efficient marginal estimates across a configuration domain. Functional ANOVA decomposes predicted performance variation into main effects and interactions; component importance is its variance contribution divided by total variance. This is an analysis of a fitted response model and a specified input distribution. It can reuse logged optimization data and handle categorical and numerical hyperparameters. The authors' experiments show concentration of variation in relatively few parameters for the studied systems.

**Project use.** Define explicit parameter domains and keep success and cost importance separate. Use fANOVA as optional exploratory analysis if the data support a useful surrogate. The directly observed contrast `f(a,b)-f(a,b0)-f(a0,b)+f(a0,b0)` is a simpler five-day interaction diagnostic; it is not equivalent to a global fANOVA importance score. Algorithm 2 and its variance definition on PDF p.5 were visually checked.

**Limits for this project.** A small, adaptively sampled configuration log can produce an unreliable forest outside visited regions. Importance depends on domains and sampling measure; it is not an intrinsic causal property of Pi. Correlated constraints and inactive settings complicate a product-space interpretation. Validate any surrogate on held-out **configurations using validation-task data**, never test-task outcomes. Prefer direct paired ablations for the required sensitivity result. The [authors' implementation README](https://github.com/automl/fanova/blob/master/README.rst) is accessible but warns about SWIG/pyrfr compatibility; installation is not necessary for the minimal plan.

## Hyperband

**Source:** Li, Jamieson, DeSalvo, Rostamizadeh and Talwalkar, *Hyperband: A Novel Bandit-Based Approach to Hyperparameter Optimization*, JMLR **18(185):1–52**, published April **2018** in the supplied PDF, supplied PDF（本地或历史材料，未打包：`../参考论文/16-558.pdf`）, [publisher page](https://www.jmlr.org/papers/v18/16-558.html). Relevant passages: §3.1–3.4, PDF pp.6–10; Algorithm 1, p.8; theoretical setup, §5.

**Paper evidence.** Hyperband allocates increasing resources to surviving configurations through successive halving, and uses brackets to hedge the tradeoff between many cheaply assessed configurations and fewer deeply assessed ones. Inputs include maximum resource `R` and reduction factor `eta`; `eta=3` is the pseudocode default. It concerns resource allocation, and is not itself Bayesian Optimization. Demonstrated speedups are on the authors' learning problems, not agent benchmarks.

**Project use.** If evaluation cost prevents full-panel search, a fidelity can be the number of completed validation tasks, with whole tasks retaining their native budgets. Use common stratified task prefixes, count every task attempt, and promote a survivor to the full panel before it can become the reported incumbent. The [author explanation](https://homes.cs.washington.edu/~jamieson/hyperband.html) and [experimental repository](https://github.com/liamcli/hyperband_benchmarks) are accessible.

**Limits for this project.** Rankings on a few heterogeneous tasks may not predict full-panel rankings. Stopping Pi halfway through a task changes the target problem and is not analogous to training fewer epochs. Noisy binary outcomes and rare categories can cause premature elimination. Reproducing vanilla Hyperband alone is not a student-developed contribution; a justified allocation or retention change is needed, with an ablation. The old experiment repository requires legacy ML dependencies and should not be installed for this project.

## Synthesis and access status

The literature motivates three separate propositions: harness choices can change outcomes; fixed-budget search needs a protected holdout and complete accounting; and interactions may deserve explicit measurement. It does **not** prove that interactions among our proposed Pi settings are large, that compaction occurs on our tasks, or that a custom optimizer will beat Random Search or BO. Those are empirical questions.

All six papers and relevant author implementation resources were accessible. Two initially guessed README paths and an initially guessed standalone HarnessOpt repository returned 404; the actual fANOVA README is `.rst` and HarnessOpt is a directory in `scaleapi/vero`. Those path errors do not mean the projects are unavailable. The AutoML landing page could not be read through the web tool, but the publisher paper and author repository were available. No external setup script was executed. Exact reproduction of upstream experiments, their archived dependency environments and all benchmark data has not been validated.

The proposed contribution is a small, explicitly specified adaptation of known search ideas to **documented configuration-only** Pi tuning. It is a student engineering/research contribution, not a claim of a new globally novel HPO family.
