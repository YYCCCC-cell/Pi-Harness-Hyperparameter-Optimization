# Ten-minute presentation outline

**Current version: implementation and mock verification; real evaluation pending.** Keep this qualification on the title slide and every result slide. Total speaking time: exactly 10 minutes, followed by the assignment's five-minute Q&A. [Report draft](research_report_draft.md), [Q&A](qa.md).

| Time | Slide | Main point and evidence | Suggested visual |
|---|---|---|---|
| 0:00–0:45 (45 s) | 1. Research problem and current status | Can configuration-only tuning improve a fixed harness under a limited budget? We built the system; paid evaluation is not complete. | Fixed harness → external settings → evaluator → search history, with test feedback kept separate |
| 0:45–1:45 (60 s) | 2. What can change? | Three documented Pi settings; 27 combinations. Harness source unchanged. Actual model and parameter activation remain unverified. | Three-row domain/default table from the report; source commit footer |
| 1:45–2:55 (70 s) | 3. Why measure interactions first? | Separate runtime activation, outcome nonadditivity and optimizer benefit. A strong interaction need not mean an improved configuration. Differential grouping/fANOVA/ParamILS/BOCS are prior art. | Four-cell difference-of-differences diagram and the hypothetical .50/.40/.40/.45 counterexample |
| 2:55–4:25 (90 s) | 4. Student-developed policy | Seven charged-within-budget screen configurations; then pair/single/global actions. Matched contrasts + stability weights choose a block. Weak evidence falls back to uniform. | Seven-point screen and three-action loop; label “application-specific adaptation” |
| 4:25–5:45 (80 s) | 5. Fair comparison and audit | Default, Random, standard SMAC BO, IGBS, pair-blind. Each search arm receives 336 task-attempt slots per seed, including failures and initialization. Same validation tasks; no free warm starts. | Accounting diagram: proposal → reserve → dispatch → raw result → settle → complete-panel selection |
| 5:45–7:05 (80 s) | 6. What was actually verified? | 80 tests; 4,116 synthetic attempts; three seeds; zero API calls. Show selected mock scores and a synthetic cost curve. Held-out results are null. | Seed 20261025 curve（本地或历史材料，未打包：`../artifacts/mock-verification/figures/20261025-simulated_cost_units.svg`）, conspicuously labeled mock |
| 7:05–8:00 (55 s) | 7. Ablation result | Zero guided pair actions out of six slots; IGBS and pair-blind coincide. No interaction-awareness benefit demonstrated. Strong-synergy unit fixture verifies the guided code branch separately. | Three-row ablation table; do not imply the unit fixture is an empirical benchmark |
| 8:00–9:10 (70 s) | 8. Risks and missing evidence | 28 binary task outcomes have low resolution; 17 provisional groups, sparse rectangles, possible inactive compaction, solver variance unknown. Real integration and USD budget remain blocked. | Evidence ladder: source check → mock → integration pilot → validation → held-out, marking only the first two complete |
| 9:10–10:00 (50 s) | 9. Reproducibility and next approved step | Source/library/seed locks and raw logs are saved. Proposed repeated study needs 4,827 attempts; no dollar budget is approved. Finalize model/runtime and budget manifest before any paid run. | Links to repository README, report, exact manifest and required decisions |

## Speaker emphasis

- Say “16 or 17 of 28 **synthetic labels**” when showing the mock table. Never say “Pi solves 61% of SkillsBench.”
- Say “SMAC's random forest can already model interactions.” The difference is explicit observed-contrast block routing, not an additive-versus-interacting strawman baseline.
- Say “All failures cost a slot, and missing cost stays unknown.” Do not describe failed attempts as free or replace their outcomes.
- Say “No observed contribution from interaction guidance in this mock.” This is the correct ablation interpretation, not a failed result to conceal.
- Finish with the exact missing experiment stage, not a claim that the full course evaluation is complete.

If paid results are subsequently authorized and completed, replace slides 6–8 with the audited real curves, held-out pass@1/gaps, actual versus estimated USD, primary ablation and trace-supported failure cases. Preserve the frozen protocol and report unsuccessful/interrupted runs. Do not select the presentation's optimizer or seed by test performance.

## Timing check

45 + 60 + 70 + 90 + 80 + 80 + 55 + 70 + 50 = 600 seconds. Keep additional technical detail in backup material: estimator formula and uncertainty limitations, native task timeouts, the source lock, all selected configurations, per-attempt accounting fields and both-direction case records.
