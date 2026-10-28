> Historical protocol notes (2026-10-26). For current real diagnostics, concrete v6 budgets, subset/heldout commands and launch conditions, use [reproduction_handoff.md](reproduction_handoff.md). Historical unresolved integration statements below do not describe the current project.

# Reproduction and experimental approval boundary

Updated 26 October 2026: the task-native live evaluator is implemented and verified with offline task-container fixtures; paid HPO evaluation is pending. See [live evaluator commands and evidence](live_evaluator.md). The historical mock evidence and proposed paid study below remain distinct.

## Verified commands

From `<project-root>` (or the root of a fresh checkout with the reviewed environment):

```bash
.venv/bin/python -m pip check
env PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/reproduce_mock.py --output runs/new-verification
```

The reproduction script runs the current test suite, then three independent search seeds under the same deterministic mock. It invokes only local Python modules; it neither installs dependencies nor calls Pi, Docker or a provider. Docker integration tests have separate explicit commands. Source: [reproduce_mock.py](../scripts/reproduce_mock.py), [backend-aware campaign schema](../schemas/hpo_campaign.schema.json).

The campaign summaries remain in `runs/final-mock-verification-20261025/`. Its tests passed in 22.179 seconds; the three recorded campaign wall times were approximately 4.857, 4.348 and 4.104 seconds. These are local software runtimes, not agent-task runtimes. The evidence package（本地或历史材料，未打包：`../artifacts/mock-verification/README.md`） preserves the original logs and complete compressed runs. On 2026-10-28, the three expanded seed directories were removed after every file matched its retained archive. Extract the archives into a fresh directory when inspecting or auditing raw runs; the evidence-package README gives the audit command. See the cleanup record（本地或历史材料，未打包：`../artifacts/cleanup-20261028/manifest.json`）.

For one campaign:

```bash
.venv/bin/python -m hpo run --config configs/hpo_final_mock.json --output runs/new-one-seed
.venv/bin/python -m hpo audit --run runs/new-one-seed
.venv/bin/python -m evaluation.report --run runs/new-one-seed --output runs/new-one-seed/report
```

Use one `--run` per distinct seed to combine reports. Duplicate seeds are rejected as independent evidence. Different configurations, task rosters, dependency versions or source fingerprints cannot be pooled by this report command. Timestamps and measured local wall times may differ; proposals, normalized synthetic outcomes, charges and selections must match. Fresh-process tests vary the parent Python hash seed and verify all five methods.

## Figures

The plot script uses the installed **ReportLab 4.4.9** chart module, with no downloaded plotting dependency. Exact prepared interpreter:

```bash
<user-home>/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  scripts/plot_mock.py --report runs/new-one-seed/report --output runs/new-one-seed/report/figures
```

For another machine, use an independently reviewed environment containing the same ReportLab version. Charts are optional; all numeric chart inputs are in `chart_data.json`. There is no hidden score smoothing. Step changes occur after complete panels. Default is a separately measured horizontal reference, not a free observation shared with search methods. Synthetic cost units and actual API USD have separate figures. Overlapping curves are retained and annotated.

## What is locked now

The three domains and native default are frozen in [hpo_space.json](../configs/hpo_space.json); 27 points pass its **mock-only** feasibility metadata. IGBS constants are versioned as `igbs-1` in [interaction_search.py](../hpo/interaction_search.py): seven screen panels, pair/single/global cycle, 2,000 bootstrap draws, .95 quantile, .05 practical threshold, eight-group minimum and .8 leave-one-group stability. There was no post-result retuning.

The validation roster SHA-256 is `2555ffc426f9c6f03b06f614ad07119c4021d4b52c46118b9f4358e0dd210f88`; the validation-group file SHA-256 is `681f031848b164ee961118fa5631b7c401ba30aca01c8ebcab7a507ba30839af`. These freeze existing proposed IDs/groups for the mock. They do not imply that the pending semantic/provenance split review has passed. The [review package](run_review/README.md) enumerates all validation and test IDs without outcomes.

Python 3.12.14, SMAC 2.4.0, ConfigSpace 1.2.1, NumPy 2.2.6, scikit-learn 1.6.1, SciPy 1.15.3 and jsonschema 4.26.0 are recorded in each manifest. [Dependency lock](../requirements-hpo.lock). Pi, SkillsBench, BenchFlow and pi-acp source commits are unchanged; the installed runtime has build attestation and successful sanity-pilot evidence. [Source lock](sources/source_lock.json), [runtime evidence](phase2_reproduction.md).

## Review manifest before paid execution

The evaluator-side command below reads only task **front matter** to inventory native timeouts, plus frozen split metadata. It does not read task instructions, skills, solutions or verifier files and cannot dispatch an experiment:

```bash
.venv/bin/python -m evaluation.review --output docs/new-run-review
```

The current [draft manifest](run_review/run_manifest.draft.json) proposes Q=12, search seeds 20261025/26/27, evaluation seed 6203, schedule seed 42, all four search arms and one Default reference. It accounts for 4,827 real task attempts including final test, but that scope has not been priced or approved. Default validation is counted once in that proposal; the mock repeats its deterministic reference once per seed to verify each standalone run, hence the mock total of 4,116 is not the planned real total.

| Required confirmation | Current status |
|---|---|
| Parameter domains | Frozen; live preflight also checks all 27 points against the selected model metadata |
| Validation/test IDs | Enumerated 28/59; disjoint and match 87 active tasks; grouping review pending |
| USD per Random Search/BO/IGBS/pair-blind seed | **Unset, not approved**; must share the same cap |
| Default, held-out, pilot, compute/project ceilings | **Separately unset, not approved** |
| Task timeouts | Exact native agent/verifier/build limits recorded; agent range 300–7,200 seconds across the 87 tasks |
| Failure accounting | Every dispatched error/timeout charged; no outer replacement; missing cost/usage stops all methods |
| Seeds/software | Explicitly listed in the draft and mock manifests; provider RNG control not guaranteed |
| Held-out feedback isolation | Verified in mock via allowlist/read-guard tests; live mount/process isolation unverified |

Do not interpret mock `task_timeout_seconds=120` as a real SkillsBench override. Live configs require `null` and use native task timeouts consistently across methods. The mock wall-time guard is checked before dispatch; the live evaluator additionally enforces an outer worker deadline and verifies resource cleanup. Its per-attempt USD reservation is an explicit soft accounting limit, not a hard provider billing bound. A mean price per task is not such a bound either.

The real hello-world provider pilot passed. The live adapter now uses task-native environments, Skills and verifiers; two scored-task environments passed offline Pi/Skills/verifier integration, and forced cleanup was tested. Remaining experimental prerequisites include a supplied provider credential, study budgets/provider spend control, split/group review, and provider-backed scored-task validation. Actual compaction activation and hard in-flight USD enforcement are not established. See [runtime evidence](phase2_reproduction.md) and [live evaluator evidence](live_evaluator.md). The earlier [run manifest](run_review/run_manifest.draft.json) is a historical draft. A live campaign requires the explicit live configuration block, positive USD reservation/cap and native timeout policy; changing the backend string alone is insufficient.

## Sequence after the missing decisions are supplied

1. Review a digest-pinned runtime/dependency build and provider spend control; keep third-party sources unchanged. Review external installation code before any new installation. Populate model identity and actual context/output metadata; do not silently alter the shared search grid.
2. Regenerate a manifest with concrete equal search caps, Default/pilot/test/compute ceilings, concurrency, wall-time limits, protocol/source hashes and reviewed split metadata. Obtain explicit human approval of that exact manifest and budget. The present all-null-budget draft is **not ready to authorize spending**.
3. Run the separately authorized integration pilot, verify all-call usage and effective settings, and resolve hard timeout/cleanup issues. A hello-world success is insufficient evidence that compaction parameters affect benchmark tasks. Connect and verify the external live evaluator for every method before expanding the campaign.
4. Execute validation search only. Keep private method histories, charge initialization and all attempts, and record every raw outcome, trajectory and setting. Failures remain in the denominator; retain actual costs and separately tagged estimates, with unknown values null. Interrupted comparisons stay incomplete.
5. Freeze all method/seed winners, source hashes and full validation audit **before** exposing any held-out outcomes. Run one primary attempt per held-out task for each frozen winner and Default. Never use test scores to choose a seed, parameter, failure exclusion, optimizer constant or alternate algorithm.
6. Reconcile provider billing and raw logs. Generate real USD curves, pass@1/gaps, deployment-cost analysis, prespecified sensitivity/ablation and both-direction failure cases. Real trajectories belong in the private raw archive; create a separately reviewed, redacted shareable export.

No implementation result guarantees that this full sequence fits five days. At concurrency one, even a modest average task duration makes the 4,827-attempt proposal difficult; the native timeouts include two-hour agent tasks. A smaller study must be selected by metadata before outcomes and explicitly reported as a subset/exploratory study.
