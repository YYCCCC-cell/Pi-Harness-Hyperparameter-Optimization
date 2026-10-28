# Real-run review: blocked, not approved

Draft manifest SHA-256: `d2877a013f2ec95c6142eec453852766ef6e3c282aa8f440a4da1f2cf227953d`. This hash identifies the proposal; it is not authorization.

Proposed work: 4827 task attempts, including Default, four search arms × three seeds, and all frozen test winners.
All live USD ceilings, model and runtime are unset. Do not run paid evaluations from this package.

## Hyperparameters

| Setting | Values | Default |
|---|---|---|
| `defaultThinkingLevel` | ['low', 'medium', 'high'] | medium |
| `compaction.reserveTokens` | [8192, 16384, 32768] | 16384 |
| `compaction.keepRecentTokens` | [10000, 20000, 40000] | 20000 |

## Budget confirmation

| Item | USD ceiling |
|---|---|
| random, each search seed | **UNSET — approval required** |
| bo, each search seed | **UNSET — approval required** |
| igbs, each search seed | **UNSET — approval required** |
| pair_blind, each search seed | **UNSET — approval required** |
| Default validation | UNSET |
| Held-out, pilot and compute | Separately UNSET |

Mock verification uses a strict $0 API ceiling and cannot dispatch model calls.

## Task ID confirmation

Validation (28):

```text
3d-scan-calc
adaptive-cruise-control
bike-rebalance
civ6-adjacency-optimizer
crystallographic-wyckoff-position-analysis
dapt-intrusion-detection
debug-trl-grpo
dynamic-object-aware-egomotion
exoplanet-detection-period
financial-modeling-qa
fix-visual-stability
gravitational-wave-detection
hvac-control
invoice-fraud-detection
latex-formula-extraction
llm-prefix-cache-replay
mario-coin-counting
mars-clouds-clustering
multilingual-video-dubbing
parallel-tfidf-search
pdf-excel-diff
powerlifting-coef-calc
r2r-mpc-control
react-performance-debugging
sales-pivot-analysis
suricata-custom-exfil
video-silence-remover
xlsx-recover-data
```

Held-out (59; evaluator only, no feedback available):

```text
ada-bathroom-plan-repair
azure-bgp-oscillation-route-leak
citation-check
court-form-filling
data-to-d3
dialogue-parser
drone-planning-control
earthquake-phase-association
earthquake-plate-calculation
econ-detrending-correlation
edit-pdf
energy-ac-optimal-power-flow
energy-market-pricing
energy-unit-commitment
enterprise-information-search
exam-block-sequencing
exceltable-in-ppt
fix-build-agentops
fix-build-google-auto
fix-druid-loophole-cve
fix-erlang-ssh-cve
flink-query
flood-risk-analysis
glm-lake-mendota
grid-dispatch-operator
jax-computing-basics
jpg-ocr-stat
lab-unit-harmonization
lake-warming-attribution
lean4-proof
manufacturing-codebook-normalization
manufacturing-equipment-maintenance
manufacturing-fjsp-optimization
offer-letter-generator
organize-messy-files
paper-anonymizer
paratransit-routing
pddl-airport-planning
pddl-tpp-planning
pptx-reference-formatting
protein-expression-analysis
python-scala-translation
quantum-numerical-simulation
radar-vital-signs
reserves-at-risk-calc
sec-financial-report
seismic-phase-picking
setup-fuzzing-py
shock-analysis-demand
shock-analysis-supply
simpo-code-reproduction
software-dependency-audit
spring-boot-jakarta-migration
syzkaller-ppdev-syzlang
threejs-structure-parser
threejs-to-obj
tictoc-unnecessary-abort-detection
travel-planning
weighted-gdp-calc
```

## Execution and failures

Use the exact task-native agent/verifier/build timeouts enumerated in the JSON manifest. The mock's 120-second simulated timeout is not the real benchmark policy.
Every attempted task, including failure/timeout, consumes its slot and incurred cost; no outer replacement. Missing usage or cost stops all methods. In-flight cost enforcement and container cancellation remain unverified.

## Seeds and versions

Search seeds: [20261025, 20261026, 20261027]; evaluation seed 6203; schedule seed 42. These do not guarantee provider RNG control.

```json
{
  "python": "3.12.14",
  "smac": "2.4.0",
  "ConfigSpace": "1.2.1",
  "numpy": "2.2.6",
  "scikit-learn": "1.6.1",
  "scipy": "1.15.3",
  "jsonschema": "4.26.0"
}
```

Source commits, task timeouts and source hashes are listed in the manifest. The proposed concurrency is 1; feasibility at this throughput is unverified.

## Blockers

- `benchflow_0.6.3_dependencies_not_installed_in_this_interpreter`
- `docker_executable_missing`
- `not_selected:model`
- `not_selected:api_key_env`
- `not_selected:budget_usd`
- `not_selected:runtime_image`
- `not_selected:runtime_review`
- `budget_and_manifest_not_approved`
- `live_hpo_evaluator_not_connected`
- `real_model_feasibility_and_parameter_activation_unverified`
- `split_metadata_provenance_review_pending`
- `hard_timeout_cleanup_and_inflight_usd_bounds_unverified`

No test outcomes are supplied to the optimizer. The mock read-guard test checks this; live process/filesystem isolation still requires verification.
