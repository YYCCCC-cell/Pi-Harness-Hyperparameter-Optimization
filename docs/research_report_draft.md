# Interaction-guided configuration search for a fixed agent harness

PE6203 Group Project 3 · 2026-10-28 · working research report

**真实评测、参数机制诊断和跨任务校准已落地；正式搜索与独立留出尚未执行。** 本文报告已有证据，不预写 IGBS 提升结论。旧的 mock-only 报告保存在 [2026-10-25 历史版](research_report_20261025_historical.md)。

## 1. 问题与贡献

研究问题：固定 Harness 源码、模型和任务条件，只改变公开参数，在相同搜索预算下能否找到成功率更高或运行成本更低、并能泛化到独立任务的配置？交互引导相对匹配 pair-blind 的独立贡献是可选扩展问题，当前缩减协议不检验这一归因。

实现包括 Default、Random、标准 SMAC BO、自研 IGBS 与 pair-blind。贡献是面向固定 Harness 小型离散空间的外部配置搜索策略及完整计量流程，不是首次提出交互估计或新的通用 HPO 家族。SMAC 的随机森林也能表达交互。相关工作和定位保留在 [文献综述](literature_review.md) 与 [算法设计](phase4_interaction_aware_hpo_design.md)。课程要求见 [32 项映射](assignment_requirements_checklist.md)。

## 2. 固定系统与搜索空间

Pi 1.4.0、SkillsBench v1.1、BenchFlow v0.6.3、pi-acp 0.0.34 的精确提交见 [来源锁](sources/source_lock.json)。项目不修改这些上游源码。项目自有封装负责环境、代理路由、计量与清理。真实模型为 OpenRouter `openai/gpt-5.4-mini`；运行目录元数据记录 400,000 上下文、128,000 最大输出。全部方法固定 with-skill。

| 参数 | live-v2 候选值 | 原生默认 | 作用 |
|---|---|---|---|
| defaultThinkingLevel | low / medium / high | medium | 请求推理等级 |
| compaction.reserveTokens | 16384 / 360000 / 375000 | 16384 | 从上下文窗口减去该值，确定压缩阈值 |
| compaction.keepRecentTokens | 4000 / 10000 / 20000 | 20000 | 压缩时保留的近期对话量 |

共 27 点，保留原生默认。reserve 不是摘要长度；较大值用于在任务可达到的上下文规模触发压缩。[live-v2 配置](../configs/hpo_space.live-v2.json) 与真实模型元数据已核对；旧 `hpo_space.json` 仍作为 mock 空间，不用于正式 live 实验。

## 3. 真实执行与计量

[运行器](../hpo/runner.py) 通过显式 backend 工厂选择真实评测器。每次尝试保留原任务依赖、Docker 服务、资源要求、Skills、官方 verifier，以及原生构建、代理和判分时限；在任务环境中添加固定 Pi 安装。它不是把 hello-world 换名。

请求账本记录开始、供应商交接、generation ID 和结束回调，代理退出后封存哈希。隐式 SDK/router 重试固定为零。完整 usage 或供应商 generation 回执提供费用；缺身份、缺终态或缺 token/费用时保持未知，并停止整个比较。失败、超时和判分不通过仍占次数与费用；预留不是实际消费。

代理断开后的计量清理最多等待 45 秒，让已经开始的请求写出终态；不重试、不延长作答时限。任务总 wall time 包含判分、清理和对账；阶段时间单列。20 秒自行车超时诊断只用于故障验收，不纳入优化器历史或正式成绩。最新真实验收、未知账单和测试见 [验收记录](completion_acceptance_20261028.md)。

## 4. 已有真实证据

### 参数机制

真实请求核对了 low/medium/high reasoning 字段。llm-prefix-cache-replay 的两次自动压缩记录如下：

| reserve / recent | 触发阈值 | 压缩前 → 后上下文 |
|---|---:|---:|
| 375000 / 4000 | 25000 | 27673 → 1869 |
| 360000 / 4000 | 40000 | 42533 → 2883 |

另有相同人工历史、真实摘要调用的 10000/40000 保留边界对照。它不是 SkillsBench 成绩，也没有证明 live 三档保留值的质量排序。短任务可能不压缩。机制生效、交互可估计、成绩提高是三个不同结论。依据：[诊断闭环](pi_diagnostic_completion_20261027.md)、[三参数核验](step2_three_parameter_readiness_20261027.md)。

### 跨任务成本校准

powerlifting 首次环境构建超时且没有模型调用，修复环境后完成任务；原始失败保留。原自行车在 900 秒超时，完整账单仍未知。后续原生时限自行车诊断的 21 次请求已逐一对账，用于未来成本规划，不能替旧账补造数据。

| 任务 | 官方 reward | 规划所用记录 USD |
|---|---:|---:|
| 3d-scan-calc | 1 | 0.01570395 |
| bike-rebalance，后续原生时限诊断 | 0 | 0.45084345 |
| crystallographic-wyckoff-position-analysis | 0.45 | 0.02090745 |
| dapt-intrusion-detection | 0 | 0.11428530 |
| financial-modeling-qa | 0 | 0.09554805 |
| llm-prefix-cache-replay | 0 | 0.20753460 |
| mario-coin-counting | 0 | 0.03996915 |
| powerlifting-coef-calc，环境修复后 | 1 | 0.06498255 |

该混合版本面板合计 **$1.00977450、3046.69 秒**。其中 7 项是历史完整 usage，后续自行车为完整 generation 回执且与 key usage 增量一致。2/8 完整通过只是校准描述，不是正式 Default 成绩。新自行车总时长 774.50 秒、代理执行 555.1 秒，没有触发其 900 秒原生时限。旧自行车已知 $0.47662005 仅为下界，完整费用仍为 null。见 [原生自行车计量报告](timeout_metering_real_review_20261028.md)。

额外受控超时诊断仍使用原 $5 预算，单独记录费用、未知值和预留，不加入以上原生任务成本面板。见 [当前预算账本](completion_acceptance_20261028.json)。

## 5. 已准备的降预算正式协议

用户要求降低原 $155 方案的规模。本版保留 8 个验证任务及 8 个独立组，留出从 16 项缩为 8 个单任务家族；按固定 SHA256 种子纯元数据选择，没有读取留出成绩。新 compact_v3 面板、冻结身份和报告分母均已接入。它是项目子集，不是官方划分或完整语义去重认证。

Default 测一个配置；Random、BO、IGBS 各测 10 配置。共 **248 次验证 + 32 次留出 = 280 次**，较原 504 次少 44.4%。IGBS 保留七点初始化与一轮完整 pair/single/global。预算不再包含可选 pair-blind，因此不能孤立归因交互引导的收益；仍能完成作业要求的四方法比较和已观察的参数敏感性分析。

用户批准 $82 后进一步要求压缩至 $60。当前分阶段额度为 Default **$3**、Random/BO/IGBS **各 $16**、四个冻结配置的留出 **$9**，共 **$60，已授权**，较原 $155 少 61.3%。默认均价外推 $35.34，1.5× 情景为 $53.01；验证 2×、留出 2.5× 假设仍为 $72.70，高于当前额度，可能提前停止而未完成。串行时间外推 29.62–59.24 小时，不是保证，不含本地计算成本。派发额度及单次 $1 预留不是供应商硬限额。环境准备已完成，等待 key 可用额度调整，尚无正式结果。

同一个搜索种子 20261027、evaluation seed 6203、schedule seed 42，不控制供应商随机性。固定原生时限与任务/Skills/模型条件，同空间、同搜索次数/美元额度，初始化、失败、超时全部收费。方法历史独立，校准不作免费观测。完整验证后按成功率、费用、耗时、配置哈希选优，四赢家一起冻结再留出；部分面板不选优，未知成本停止，测试不反馈。测试分母固定 8，成绩只能以 12.5 个百分点变化，属于小样本探索。

详细清单和来源快照见 [协议 v8](formal_protocol_20261028_v8/README.md)。低于八验证组会让当前 IGBS 引导失效，不能继续用该方式减预算却宣称相同方法被有效检验。正式六类结果仍待实际运行。

## 6. IGBS 与分析方法

IGBS 先测默认、3 个单参数变化、3 个双参数变化，然后执行一轮 pair/single/global（当前十配置方案）。局部双参数对照为同任务上的平均 `Y11 − Y10 − Y01 + Y00`。缺角或背景不匹配时视为不可识别，不填零。固定采用 2000 次按组重采样、0.95 偏差分位数、0.05 实用阈值、至少 8 组和 0.8 稳定性阈值。没有可靠正权重时均匀选择可用块；pair-blind 只移除 pair 权重。

这些权重是启发式，并非校准的顺序显著性检验。初始化占 7/10 = 70%；局部稀疏对照可能遗漏第三水平或三阶效应。不能从一个种子推出稳健优势。

| 作业要求的最终结果 | 当前真实 formal 值 | 生成方式 |
|---|---|---|
| 累计搜索 USD—incumbent 曲线 | unavailable | 完整面板，比较共同观察预算区间 |
| 各方法赢家、验证/留出 pass@1 | unavailable | 冻结配置、固定测试分母 |
| 验证到测试差距 | unavailable | 相同选定配置、分列两种成绩 |
| 搜索与后续运行费用权衡 | unavailable | 两类账本与每任务成本 |
| 敏感性与实际路由 | unavailable | 方法自身历史的匹配对照；本版不做 pair-blind 消融 |
| Default/调优双向失败案例 | unavailable | 留出配对结果，按任务 ID 固定选例 |

[真实报告工具](../evaluation/live_report.py) 已实现并通过 fixture 验证；无额外付费敏感性网格，不存在的对照保留未知。某方向没有失败案例应如实报告，不能杜撰。

## 7. 验证、交付和限制

历史 mock 包含 3 种搜索种子、4116 次合成尝试、零模型调用和零 API 消费，证明软件流程而非代理能力。IGBS 与 pair-blind 的 mock 选点一致，没有触发正交互引导。合成图留在明确标记的 mock 包（本地或历史材料，未打包：`../artifacts/mock-verification/README.md`），不放入正式结果表。

当前回归、真实超时验收和 search→freeze→heldout→report 检查在[验收记录](completion_acceptance_20261028.md)中汇总。[复现交接](reproduction_handoff.md)、[作业映射](assignment_requirements_checklist.md)、[10 分钟汇报提纲](presentation_outline.md)已更新。工程版本可由用户自行上传；最终研究报告需要真实正式数据。

已补齐 [结果填入说明](results_completion.md) 和 [可编辑 10 页展示草稿](presentation/EP6203-progress-draft.pptx)。草稿含中文讲稿和来源，正式实验结果保持待填。

目前能确认系统与参数机制已实现；仍不能回答 IGBS 是否改善独立任务表现。负面或不确定结果都可接受，mock 或校准不能替代正式比较。
