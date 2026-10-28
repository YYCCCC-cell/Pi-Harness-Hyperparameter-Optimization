# Implementation source locators

Project version **0.2.0**, 25 October 2026. File SHA-256 identities and one-based line ranges below locate the implemented behavior. Upstream dependencies retain their separately pinned versions. These are source locators, not evidence that the live benchmark was executed.

| Source | SHA-256 | Relevant definition and lines |
|---|---|---|
| [hpo/interaction_search.py](../hpo/interaction_search.py) | `41f8102dd570395c79d7fa02817679ff871ff1ae394cc032355b314370c1ca63` | `stream_seed` 24–25; `InteractionSearch` 28–120 |
| [hpo/contrasts.py](../hpo/contrasts.py) | `d2a9ab6e10b337942d08eeb3e08c3feb42314ab7bbb862db612d15e400a12e9a` | `ContrastAnalyzer` 12–111 |
| [hpo/runner.py](../hpo/runner.py) | `76e692f02217dffb81ad3bf4dddabb97e1145682df52693802737816d0b3144c` | `write_json` 26–30; `Journal` 33–47; `task_seed` 50–51; `run_campaign` 54–248; `audit_run` 251–314 |
| [hpo/methods.py](../hpo/methods.py) | `f7f9a8e5377d6eaaa4176749f8eb1f03b9b4a14d124d5d1fdafe9f8f8907f098` | `PanelObserver` 10–12; `Default` 15–23; `RandomSearch` 26–35; `BayesianOptimization` 38–83 |
| [hpo/budget.py](../hpo/budget.py) | `a4781ac7ab6a5e4dbf3a51860e4ea505dc8f889c849f9dd519556fc4a9e1c8b1` | `money` 6–10; `Ledger` 13–79 |
| [hpo/config.py](../hpo/config.py) | `a3d6c442112d25a34b8d3a7df8d21393678f91d37d5b5e0e82947f3940df0578` | `read_json` 16–29; `schema_validate` 32–36; `load_campaign` 39–51; `load_validation_roster` 54–61; `load_validation_groups` 64–75; `flatten` 78–83; `unflatten` 86–93; `Space` 96–120 |
| [hpo/selection.py](../hpo/selection.py) | `6d4f305c4f932154d13d7089d935e11176ded3d7a4c17072709ba4a21c5f4452` | `selection_key` 4–6 |
| [hpo/evaluation.py](../hpo/evaluation.py) | `8f5aa70d9b7accfe4166362a37550bf9170b2d1aff3fa1e7ed26a4e4a78881c2` | `parse_result` 9–28; `unavailable_result` 31–39; `MockBenchmark` 42–84 |
| [evaluation/report.py](../evaluation/report.py) | `7acbeafe053c0e71c0ca474832c652bdb682fc228efcce6cc0379b164d52b266` | `compile_report` 15–124; `main` 127–134 |
| [evaluation/review.py](../evaluation/review.py) | `82659ab06371e2781dabe3b41a596d8a4ba658b939545608e13982cec727f424` | `task_limits` 18–42; `prepare_review` 45–141 |
| [tests/test_interaction.py](../tests/test_interaction.py) | `4acb1475d5550160011bfe0b702997092ca40f0b63a857e1f11ef01a72c8e805` | `observation` 22–28; `panel` 31–37; `ContrastTests` 40–121; `PolicyTests` 124–179; `FinalCampaignTests` 182–274 |
| [tests/test_review.py](../tests/test_review.py) | `009b587dada70eb30b52305218578c9d83a576fb4d47a13ef58947a1fadb97fd` | `ReviewTests` 9–29 |
| [scripts/reproduce_mock.py](../scripts/reproduce_mock.py) | `3b5711f358c3d5e3eb6761a99e3cf8e0656cafdfaba75739fc5791e2083a9d58` | `main` 15–42 |
| [scripts/plot_mock.py](../scripts/plot_mock.py) | `6b90d4b91ba48f4ed6ec4ffd8028590ba95f41034c97acbf9bd2202d1d0bfe08` | `plot` 16–66 |

The executed mock manifests also hash configuration/schema files and all HPO modules. The [draft run manifest](run_review/run_manifest.draft.json) hashes 37 application/schema/test/script inputs for review. The artifact manifest（本地或历史材料，未打包：`../artifacts/mock-verification/artifact_manifest.json`） hashes exported results, plots, logs and raw archives.
