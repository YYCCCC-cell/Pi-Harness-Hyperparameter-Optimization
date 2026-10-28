# Pi 真实诊断与三个参数的生效核对

> 历史阶段快照。原计划尾部和新版范围校准现已完成，当前完整证据见 [诊断闭环](pi_diagnostic_completion_20261027.md)。以下结论保留在原核查时刻，不代表最终状态。

核查时间：2026-10-27T16:06:10+08:00。当前诊断已停止，原因 usd_budget。以下为该时刻的结果快照。

**已确认推理档位 low、medium、high 都传入 Pi 状态和真实供应商请求；尚未确认两个压缩参数在这些真实任务中改变了执行行为。** 压缩参数已写入运行环境，原生机制探针也能区分其取值，但真实任务日志没有形成压缩行为对照。

**执行状态**

原计划共 8 项。当前各类状态：已返回结果，未通过 4 项；超时，费用不完整 1 项；中断，已恢复部分证据 1 项；尚未启动 2 项。最新批次正在执行的项目：无。结束、成功、证据完整分别判断，不能把它们混为一个完成率。

最新批次预算上限为 1.99992500 USD，已计量 1.00272375 USD，剩余 0.99720125 USD。每次派发需预留 1 USD；先前三项费用不完整的尝试合计保留 3 USD。触发 usd_budget 表示不能再满足一次预留，不表示原始 5 USD 全部花完。

| 诊断项 | 参数变化 | 执行结果 | 最大上下文快照 | 压缩事件证据 | 已记录成功请求金额 USD |
|---|---|---|---:|---|---:|
| baseline-primary | medium / 16384 / 20000 | 已返回结果，未通过 | 30643 | 审计完整，未观察到 | 0.06675405 |
| baseline-secondary | medium / 16384 / 20000 | 超时，费用不完整 | 27289 | 审计未闭合，不能下结论 | 0.50211585 |
| thinking-low | low / 16384 / 20000 | 中断，已恢复部分证据 | 9439 | 审计完整，未观察到 | 0.03044580 |
| thinking-high | high / 16384 / 20000 | 已返回结果，未通过 | 70277 | 审计完整，未观察到 | 0.33043905 |
| reserve-low | medium / 8192 / 20000 | 已返回结果，未通过 | 39856 | 审计完整，未观察到 | 0.20937285 |
| reserve-high | medium / 32768 / 20000 | 已返回结果，未通过 | 63947 | 审计完整，未观察到 | 0.46291185 |
| recent-low | medium / 16384 / 10000 | 尚未启动 | — | 待运行 | 未知或待完成 |
| recent-high | medium / 16384 / 40000 | 尚未启动 | — | 待运行 | 未知或待完成 |

参数列顺序为 thinking / reserveTokens / keepRecentTokens；除 baseline-secondary 使用 bike-rebalance 外，其余计划项使用 llm-prefix-cache-replay。成功请求金额不是完整尝试费用。所有已取得的官方 reward 均为 0；本次不能得出某档位提高成功率的结论。

**三个参数分别确认到了哪一层**

| 参数 | 已确认 | 尚未确认 |
|---|---|---|
| defaultThinkingLevel | low、medium、high 的运行设置、Pi RPC 状态与实际请求 reasoning_effort 一致；响应中也有 reasoning_tokens 记录 | 不能从单次、长度不同且含中断的轨迹推断档位对质量或成本的因果收益，也不能证明供应商内部计算预算的具体变化 |
| compaction.reserveTokens | 已执行档位的设置文件与计划一致；原生机制探针确认值越大，触发阈值越低 | 真实诊断尚无可比较的压缩事件，不能把不同运行的分数或费用差归因于这个参数 |
| compaction.keepRecentTokens | 默认 20000 已写入环境；原生机制探针确认 10000、20000、40000 会改变保留边界 | 两档真实对照尚未启动；即使运行，也需要实际发生压缩，才能检验真实保留行为 |

这里的“设置已写入”来自容器导出的 pi-settings-written.json；RPC get_state 暴露了 thinking level 和模型信息，但没有直接回读两个 compaction 字段。execution-evidence.json 中的 settings_and_model_verified=true 不能扩大解释成“压缩发生过”。

**为什么尚未看见压缩作用**

锁定 Pi 源码的阈值条件为 contextTokens > contextWindow - reserveTokens。模型记录的上下文窗口为 400000，因此：

| reserveTokens | 严格超过该上下文量才达到阈值 |
|---:|---:|
| 8192 | 391808 |
| 16384 | 383616 |
| 32768 | 367232 |

本次读到的最大有效 assistant usage 上下文快照为 70,277 tokens。该值不包括之后追加的 tool/user 估算，不能当成每一时刻的完整峰值；但已闭合的事件审计同样没有 compaction_start / compaction_end。累计输入 tokens 会反复计算多轮上下文，不能拿它与上述单次上下文阈值比较。

原生探针使用合成长历史、没有模型调用：keepRecentTokens 为 10000、20000、40000 时，分别保留 5、10、20 条合成消息。它证明代码机制存在，不能替代真实任务上的行为证据。

**费用与异常的处理**

- baseline-primary 遭遇供应商地区限制，6 条失败请求没有完整费用；0.06675405 USD 只是已知成功请求费用。
- baseline-secondary 的旧 result 和 summary 曾记录 0.50211585 USD；后续 corrected-result.json 将完整尝试费用改判为未知，因为超时不能排除未计量的在途请求。本汇总采用该更正，保留已知请求金额。
- thinking-low 恢复到 7 条 low 请求和官方 reward=0，也有清理证明，但缺少完整 worker 结果及全程耗时；不把恢复记录合成为正常完成记录。
- 当前已知成功请求记录金额合计 1.60203945 USD，未包括未知费用及独立可用性探测。完整诊断总费用仍为未知，不能把这个合计写成账单总额。

**对 IGBS 的结论**

当前可以确认一项参数的真实请求控制链路，以及两项条件触发参数的原生机制。尚不能宣称已经验证三个有效搜索维度，更不能宣称存在有益交互。当前批次已经停止；下一步应先审视压缩参数范围、模型与任务的匹配，再决定剩余两项诊断是否能提供有意义的行为证据。仅补跑 keepRecentTokens 而仍不触发压缩，无法解决参数作用不可识别的问题。

**可追溯证据**

- 机器可读核对结果及源文件哈希（本地或历史材料，未打包：`../artifacts/pi-diagnostic-parameter-audit-20261027/snapshot.json`）
- 最新批次结果（本地或历史材料，未打包：`../runs/pi-diagnostic-real-20261027-remaining/summary.json`）
- low 档位恢复证据（本地或历史材料，未打包：`../runs/pi-diagnostic-real-20261027-continuation/attempts/thinking-low/recovered-execution-evidence.json`）
- 超时费用更正（本地或历史材料，未打包：`../runs/pi-diagnostic-real-20261027-continuation/attempts/baseline-secondary/corrected-result.json`）
- 原生压缩机制探针（本地或历史材料，未打包：`../runs/compaction-native-probe-20261027.json`）
- [事件及请求证据汇总逻辑](../evaluation/telemetry.py)
- 锁定 Pi 压缩实现（本地或历史材料，未打包：`../third_party/pi-mono/packages/coding-agent/src/core/compaction/compaction.ts`）
