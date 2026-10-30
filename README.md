# Pi Harness Hyperparameter Optimization

**Evaluating how reasoning and context-compaction settings affect an agent's task success and cost.**

This EP6203 project compares **Default, Random Search, SMAC Bayesian Optimization (BO), and Interaction-Guided Block Search (IGBS)** on SkillsBench 1.1. The model and Pi Agent runtime are fixed; the search changes three harness settings. The repository includes the search algorithms, task-native evaluation, accounting checks, public result aggregates, and reproducible figures.

[Paper PDF](reports/EP6203_Paper.pdf) · [Editable paper](reports/EP6203_Paper.docx) · [Presentation](reports/EP6203_Presentation.pptx) · [Result data](results/final-20261030-1203/) · [Reproduction](docs/reproduction.md)

> **Evidence snapshot — 30 October 2026, 12:03 UTC+8.** The recorded campaign contains **139 ended validation attempts** and **12 ended held-out attempts**. Held-out evaluation is incomplete, and IGBS did not reach its adaptive search stage. The figures below describe this partial campaign; final eight-task held-out pass@1 is unavailable.

## Experiment at a glance

| Component | Recorded setup |
|---|---|
| Agent and model | Fixed Pi Agent runtime; OpenAI `gpt-5.4-mini` |
| Benchmark | SkillsBench 1.1 with native Skills, task environments, timeouts, and official verifiers |
| Task split | 8 validation tasks for search; 8 separate held-out tasks for evaluation |
| Search space | 3 parameters × 3 levels = 27 configurations |
| Methods | Default, Random Search, SMAC BO, IGBS |
| Budget allocation | Default: USD 3; each search method: USD 16; held-out: USD 9; total cap: USD 60 |
| Selection | All four configurations frozen before held-out execution |

The three parameters are `defaultThinkingLevel` (`low`, `medium`, `high`), `compaction.reserveTokens` (16,384; 360,000; 375,000), and `compaction.keepRecentTokens` (4,000; 10,000; 20,000). These are configured settings; actual runtime effects require execution evidence. See the [recorded experiment configuration](results/final-20261030-1203/experiment-config.json) and [live search space](configs/hpo_space.live-v2.json).

## Results

### 1. Validation outcomes of the selected configurations

Each column below represents the configuration selected by one method, evaluated on the eight validation tasks. It is a selected-panel result; the full search includes 139 attempts across multiple configurations.

![Validation outcome matrix for Default, Random, BO and IGBS across eight tasks; PASS, FAIL and measurement exception are shown separately.](results/final-20261030-1203/figures/frozen-validation-outcomes.png)

**Figure 1.** `PASS` and `FAIL` are measurement-valid native verifier outcomes. `EXC` preserves a measurement exception, which receives an explicit zero penalty under the recorded operational policy. The Default bike-rebalance exception remains visible as a separate category. [Figure data](results/final-20261030-1203/figure-input.json) · [PDF](results/final-20261030-1203/figures/frozen-validation-outcomes.pdf)

| Selected by | Reasoning | Reserve tokens | Keep-recent tokens | Operational validation score |
|---|---|---:|---:|---:|
| Default | medium | 16,384 | 20,000 | 3/8 · 37.5%¹ |
| Random | low | 16,384 | 10,000 | 2/8 · 25.0% |
| BO | medium | 16,384 | 4,000 | 3/8 · 37.5% |
| IGBS | medium | 16,384 | 4,000 | 5/8 · 62.5% |

¹ Default includes one measurement exception in the fixed eight-task denominator. Sources: [frozen configurations and scores](results/final-20261030-1203/aggregate-tables/frozen-winners.json), [metric definitions](docs/result_interpretation.md).

**Interpretation:** BO and IGBS selected **exactly the same configuration**. Their 3/8 and 5/8 scores came from separate executions with uncontrolled provider randomness. These observations do not establish that IGBS found better parameters or outperformed BO. All six recorded IGBS proposals were initialization screening; its interaction-guided adaptive phase was not exercised.

### 2. Search progress within a shared budget interval

Equal budget caps do not imply equal realized spending or accounting completeness. This comparison uses only the cumulative-budget interval supported by all three search methods, and does not extend their curves beyond observed support. An **incumbent** is the best operational validation score observed by that point.

![Validation incumbent curves on two cost axes: known token-cost estimates, and estimates plus unknown-request reserves. All three search methods are at 25% over their common estimate-plus-reserve interval.](results/final-20261030-1203/figures/common-support-curves.png)

**Figure 2.** The **right panel** includes unknown-request reserves: over the common interval **USD 7.1515–7.5359**, Random, BO, and IGBS all retain a **25%** incumbent score. The **left panel** uses known estimates only and omits unknown exposure; it is a sensitivity view. The dashed Default line is a fixed reference, with the exception penalty described above; Default does not define the three-method common interval. [Curve data](results/final-20261030-1203/aggregate-tables/common-budget-curves.json) · [PDF](results/final-20261030-1203/figures/common-support-curves.pdf)

The accounting record contains **USD 20.4248 in usage-based estimates plus USD 17 in unknown-request reserves**. Reserves retain uncertainty; they are neither confirmed spend nor confidence intervals. Provider invoice reconciliation is unavailable. [Accounting and coverage audit](results/final-20261030-1203/audit.json)

### 3. Held-out coverage and remaining uncertainty

| Method | Ended / planned | Measurement-valid | Exceptions | Unresolved | Not started |
|---|---:|---:|---:|---:|---:|
| Default | 3 / 8 | 2 | 1 | 1 | 4 |
| Random | 3 / 8 | 3 | 0 | 0 | 5 |
| BO | 3 / 8 | 3 | 0 | 0 | 5 |
| IGBS | 3 / 8 | 3 | 0 | 0 | 5 |

The campaign stopped with `controller_error_FileNotFoundError`. One further Default attempt remains unresolved in this snapshot. Unexecuted and unresolved tasks remain missing observations; they are not assigned a pass or fail. Complete held-out pass@1 and the final generalization gap are unavailable for every method. Later recovery outcomes are outside this README's cutoff. [Coverage data](results/final-20261030-1203/aggregate-tables/method-coverage.json) · [Snapshot status](CURRENT_STATUS.json)

### 4. Separate controlled synthetic mechanism check

The revised paper also includes a **controlled synthetic check**, stored separately from the real SkillsBench campaign. Three designed scenarios × two methods × ten configurations × eight artificial task groups produced **60 panels and 480 synthetic evaluations**, with zero model calls. These known-answer checks exercised the pair, single-parameter and global proposal routes, the pair-blind ablation, and conservative fallback.

This is software mechanism evidence; it does not establish real-task adaptive efficacy or optimizer superiority. The real-campaign tables and cutoff above are unchanged. See the [synthetic results and limitations](results/igbs-synthetic-20261030/RESULTS.md), [recorded output](results/igbs-synthetic-20261030/run-output/results.json), and Appendix B of the [paper](reports/EP6203_Paper.pdf).

## Method and implementation

The pipeline proposes a configuration, executes the native validation tasks, retains verifier and accounting evidence, and updates the search state. Selected configurations are frozen before independent held-out evaluation.

IGBS uses matched local contrasts to estimate which parameter changes are worth exploring. After initialization, its implemented policy routes proposals through pair, single-parameter, and global exploration, with stability gates and uniform fallback. The recorded real campaign only exercised initialization. The separate synthetic check exercises routing logic; real-task adaptive efficacy remains an empirical research question.

| Component | Entry point |
|---|---|
| Default, Random, and SMAC BO | [hpo/methods.py](hpo/methods.py) |
| IGBS policy and contrast estimation | [interaction_search.py](hpo/interaction_search.py), [contrasts.py](hpo/contrasts.py) |
| Native evaluation and request accounting | [live.py](evaluation/live.py), [openai_accounting.py](evaluation/openai_accounting.py) |
| Recorded campaign controller and selection freeze | [deadline_run.py](scripts/restart_20261029/deadline_run.py), [deadline_frozen.py](evaluation/deadline_frozen.py) |
| Pinned runtime and configuration | [runtime/](runtime/), [configs/](configs/), [source records](docs/sources/) |
| Tests and package integrity checks | [tests/](tests/), [verify_release_package.py](scripts/verify_release_package.py) |

The [IGBS supplement](experiments/igbs-validation-20261030/README.md) adds implementation for repeated search seeds, pair-blind ablation, optimizer traces, and a separate evaluation protocol. It has offline verification only; no supplementary paid benchmark experiment was executed. The [held-out recovery script](scripts/restart_20261029/continue_frozen_heldout.py) is also included as source, with its outcomes excluded from this snapshot.

## Reproduce and inspect

**Check the public package** using Python's standard library:

```bash
python3 -B scripts/verify_release_package.py
```

**Run offline tests** after creating the locked Python 3.12 environment in the [reproduction guide](docs/reproduction.md):

```bash
env PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -B -m unittest tests.test_hpo tests.test_interaction \
  tests.test_deadline_run tests.test_deadline_frozen tests.test_continue_frozen_heldout -q

env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -B -m unittest discover \
  -s experiments/igbs-validation-20261030/tests -v
```

The reselected package has **155 passing tests and 1 skip** in the existing environment. These are software checks; a fresh dependency installation was not performed. The release combines verified source files with the latest reviewed deliverables and public evidence. [Verification record](PACKAGING_VERIFICATION.json)

**Reproduce Figures 1–2** with the dependencies in [requirements-report.txt](requirements-report.txt), using a separate reporting environment:

```bash
python results/final-20261030-1203/reproduce_figures.py
```

The figure script reads public aggregates and makes no model calls. Regeneration writes the PNG/PDF files; PDF metadata can change their hashes. Run it in a working copy if preserving the published manifest is required.

## Deliverables and scope

- **Report and presentation:** [reviewed English deliverables](reports/), using the same real-campaign cutoff as this README; the revised paper additionally includes the separate synthetic check.
- **Inspectable evidence:** [aggregate tables, figures, source hashes, and audit](results/final-20261030-1203/README.md).
- **Requirements and limitations:** [submission checklist](docs/submission_requirements.md) and [result interpretation](docs/result_interpretation.md).
- **Upload package:** [scope guide](GITHUB_UPLOAD.md), [file manifest](UPLOAD_MANIFEST.json), and [third-party notices](THIRD_PARTY_NOTICES.md).

Credentials, raw task trajectories, request logs, private run directories, local environments, third-party source checkouts, and instructor documents are excluded. Historical material under `docs/presentation/` and `artifacts/release-verification/` retains its engineering or synthetic status. Real execution requires the pinned native environments, local credentials, a declared protocol, and a separately authorized budget; the dated controller must not be relaunched against the recorded campaign.
