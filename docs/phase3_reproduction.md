# Phase 3 reproduction

This phase runs **deterministic mock evaluations only**. It does not execute Pi, BenchFlow, Docker, Modal, any task verifier, or any model API. The real pilot remains gated by [Phase 2](phase2_feasibility_verification.md#exact-blockers-and-smallest-compliant-alternative). The CLI's only accepted backend is `deterministic_mock_v1`; see [campaign schema](../schemas/hpo_campaign.schema.json), and project `hpo` v0.1.0 [runner.py, `run_campaign`](../hpo/runner.py).

## Use the prepared environment

Run from this exact project directory:

```bash
cd '<project-root>'
.venv/bin/python -m pip check
PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m hpo run --output runs/phase3-my-reproduction
.venv/bin/python -m hpo audit --run runs/phase3-my-reproduction
```

Choose a **new** output directory for each verification. Existing directories are rejected; there is no resume, overwrite, cross-method result cache, or automatic retry of a charged task. The CLI re-executes Python with the four pinned process variables before loading the evaluator. For imports/notebooks, start the kernel with those variables; setting `PYTHONHASHSEED` inside Python is insufficient. This requirement was added after detecting cross-process BO differences. [Project v0.1.0: `hpo/__main__.py`, startup block](../hpo/__main__.py), [`hpo/reproducibility.py`](../hpo/reproducibility.py), [`hpo/runner.py`, directory creation and attempt loop](../hpo/runner.py).

The default mock verification uses 12 configurations × 28 validation labels for each search method and one 28-label Default panel. `configs/hpo_mock.json` contains three explicit seeds, a zero real-USD ceiling, 10 synthetic cost units per method, a 120-second **active controller wall-time** ceiling per method, and a 120-second simulated task timeout. The wall-time counter includes that method's controller/evaluation work, excluding time spent running other methods; it is checked before dispatch. It is not a process-killing watchdog. Synthetic timeout rows return immediately. [Configuration](../configs/hpo_mock.json), [controller](../hpo/runner.py), [mock evaluator](../hpo/evaluation.py).

## Inspect the artifacts

| File in the run directory | Contents |
|---|---|
| `manifest.json` | Campaign, space, validation-only roster, task order, source hashes, intended upstream pins, installed distributions, Python/platform/process settings |
| `configurations/*.json` | Exact nested Pi settings for every proposed configuration |
| `events.jsonl` | Ordered, flushed dispatch/result records, configuration hashes, task IDs, seeds, status, errors, budget snapshots and full-panel curves |
| `attempts/<id>/settings.json` | Separate settings file for each synthetic attempt |
| `attempts/<id>/raw-result.json` | Synthetic evaluator output before parsing |
| `summary.json` | Every panel, selected complete-panel incumbent, budget usage, stop reasons and comparison-completion flags |
| `bo-components.json`, `smac/` | Upstream SMAC component metadata and its own scenario/runhistory files |

Implementation: project v0.1.0 [`hpo/runner.py`](../hpo/runner.py), [`hpo/evaluation.py`](../hpo/evaluation.py). The result contract is [`schemas/hpo_result.schema.json`](../schemas/hpo_result.schema.json). `actual_cost_usd`, `estimated_cost_usd` and `simulated_cost_units` are separate fields. Mock `actual_cost_usd=0` means no model call was dispatched, **not** an invoice for an LLM run. Input/output/cache token counts and simulated durations are synthetic; `execution_time_seconds` and controller duration are measured local wall time. If a real evaluator is added later, invoice reconciliation and all-call usage coverage remain its responsibility.

Reproduction means matching proposals, normalized synthetic results, budgets and selected configurations with the locked environment. Timestamps, actual local wall times, output paths and arbitrary SMAC bookkeeping times need not match byte-for-byte. The cross-process unit test compares complete panels from independently launched interpreters. [Tests: `HPOCampaignTests`](../tests/test_hpo.py).

## Dependency provenance and recreation

The prepared `.venv` uses Python **3.12.14** on macOS arm64. Main pins are SMAC **2.4.0**, ConfigSpace **1.2.1**, scikit-learn **1.6.1**, NumPy **2.2.6**, SciPy **1.15.3**, and jsonschema **4.26.0**. All 37 resolved dependency artifacts are listed with hashes in [requirements-hpo.lock](../requirements-hpo.lock) and [source_lock.json](sources/hpo/source_lock.json). This is a platform-specific artifact lock, not a claim of verification on Linux, Windows, Intel macOS, or Python 3.14.

Before installation, SMAC's package entry point, facade and dependency metadata were read. All downloaded wheels were checked for `.pth` and `.data/scripts/` install hooks; none were present. `pynisher` 1.0.10 had no wheel, so its `setup.py`, `setup.cfg`, `pyproject.toml` and package entry points were read before a local wheel build. Its setuptools build reads the README and packages Python files without custom install commands. Build tools were setuptools 80.9.0 and wheel 0.45.1. The build/install logs and downloaded artifacts remain in `runs/phase3-dependency-review/`（本地或历史材料，未打包：`../runs/phase3-dependency-review/`）. These are limited source/packaging checks, **not an exhaustive security audit of dependencies or binary wheels**. Imports execute third-party Python and native numerical code locally.

To recreate on the same architecture using the already downloaded wheelhouse, choose a fresh environment path:

```bash
cd '<project-root>'
<user-home>/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m venv .venv-reproduction
.venv-reproduction/bin/python -m pip install \
  --no-index --only-binary=:all: \
  --find-links runs/phase3-dependency-review/wheels \
  --require-hashes -r requirements-hpo.lock
.venv-reproduction/bin/python -m pip check
```

For a clean machine without that wheelhouse, use Python 3.12 on macOS arm64, review the preserved provenance, install the two pinned build tools in an isolated environment, then:

```bash
python -m pip install --only-binary=:all: --index-url https://pypi.org/simple \
  'setuptools==80.9.0' 'wheel==0.45.1'
python -m pip install --index-url https://pypi.org/simple \
  --only-binary=:all: --no-binary=pynisher --no-build-isolation \
  --require-hashes -r requirements-hpo.lock
```

The lock accepts the reviewed pynisher source archive hash as well as the locally built wheel hash. Its build can produce a different wheel hash due to archive timestamps; the source archive identity stays pinned. The offline wheelhouse path is the path used for the verified installation. The clean-machine recreation command is provided for reproduction but was not executed here. Review new artifacts and create a separate lock before changing platform or dependencies; never discard hashes simply to force an install.

## Before real evaluation

The baseline controller currently has **no live evaluation backend**. Do not point mock outputs at a real campaign or interpret their scores as benchmark results. The smallest next step is still the single gated Phase 2 pilot: select the exact model/provider and dollar ceiling, provision the reviewed digest-pinned runtime and Docker-capable host, validate settings and usage, and review/freeze the validation split. Then connect an external evaluator to this common controller with task-wide cost controls and real timeout isolation, preserving the same parameter grid and task-attempt accounting. Any changes must be applied to every baseline before scored runs. No held-out evaluation or student-developed optimizer is included in Phase 3. [Phase 2 blockers](phase2_feasibility_verification.md#exact-blockers-and-smallest-compliant-alternative), [Phase 1 protocol](initial_research_feasibility_proposal.md#f-recommended-experimental-protocol).
