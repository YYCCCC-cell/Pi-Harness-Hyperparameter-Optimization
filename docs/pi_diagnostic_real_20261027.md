# 2026-10-27 真实诊断：6 次尝试，三档 thinking 已验证，压缩行为未激活

> 历史阶段快照，保留当时的预算和异常纠正。后续原计划 8 项已执行完，并以新版空间完成真实自动压缩校准；当前结论见 [诊断闭环](pi_diagnostic_completion_20261027.md)。下文“未完成”“未启动”均指本快照时刻。

保留原模型 `openrouter/openai/gpt-5.4-mini` 后，真实多轮调用恢复。本轮共执行 **6 次验证任务尝试和 1 次极小可用性探测**；原计划最多 8 次中的最后两个 keepRecent 对照因预算预留检查没有启动。任务 2 的完整对照尚未完成，也没有启动正式 HPO 或旧草案的 4,827 次尝试。

主要结论是：low / medium / high 都确实进入了供应商请求；reserve 的三个值也正确载入 Pi，但当前任务未提供真实压缩效果证据。不能将这批结果包装成三个参数都在有效参与优化。

权威汇总：diagnostic-review.json（本地或历史材料，未打包：`../runs/pi-diagnostic-real-20261027-remaining/diagnostic-review.json`）。原始段记录保留不变，事后纠正和恢复记录单独保存。

## 费用、耗时与官方判分

以下“已知费用”是成功请求的供应商 `usage.cost` 合计。完整计量列为否时，它不是完整任务成本。

| 尝试 | 任务 / 改动 | 已知费用 USD | 完整墙钟秒数 | 官方 reward | 完整任务计量 |
|---|---|---:|---:|---:|---|
| baseline-primary | llm-prefix-cache-replay，默认设置 | 0.06675405 | 445.435 | 0 | 否：8 成功、6 地区错误请求 |
| baseline-secondary | bike-rebalance，默认设置 | 0.50211585 | 1028.421 | 0 | 否：原生 agent 在 900 秒超时 |
| thinking-low | 主任务，low | 0.03044580 | 未完整恢复 | 0 | 否：agent / verifier 记录已恢复，worker 终结记录缺失 |
| thinking-high | 主任务，high | 0.33043905 | 418.094 | 0 | 是：19 次成功调用 |
| reserve-low | 主任务，medium / reserve=8192 | 0.20937285 | 303.899 | 0 | 是：13 次成功调用 |
| reserve-high | 主任务，medium / reserve=32768 | 0.46291185 | 368.336 | 0 | 是：17 次成功调用 |

没有重复补跑上述任务。low 在核查前一任务的超时计量问题、停止批次时已完成 agent 与官方 verifier；从残存 callback、Pi audit 和 verifier 文件恢复了 7 次 low 请求和官方 0 分，但没有编造完整墙钟时间或缺失的 worker result。该记录不进入配置质量比较。

low、high、reserve-low 的官方检查均为 6 项中通过 2 项；reserve-high 为 6 项中通过 1 项。完成的主任务存在实际答案数值断言失败，例如命中 token 总数、命中率和最终缓存内容。它们不是依赖缺失或 verifier 未运行造成的成功假象，也没有获得完整通过的任务。本小样本不能估计配置优劣或整个验证集的通过率。

三次完整计量的主任务费用范围是 **$0.20937–$0.46291**，墙钟范围 **303.9–418.1 秒**，样本均值分别为 $0.33424 和 363.4 秒。这里只描述这三个失败任务的观测，不能作为所有真实任务的平均成本，也不能直接据此制定正式实验预算。

## 总费用与为什么停止

- 6 次任务的已知成功请求费用：**$1.60203945**。
- 独立可用性探测：**$0.000075**，约 2.15 秒，不算任务成绩。
- 合计已知费用：**$1.60211445**。
- 延后读取的整个密钥用量增量也是 **$1.60211445**；后 3 次任务最后一次请求的供应商 generation 记录也与对应 usage.cost 一致。见 延后用量核对（本地或历史材料，未打包：`../runs/pi-diagnostic-availability-20261027/final-key-review.json`）。

密钥级增量存在结算延迟，也可能包含其他客户端；它不是每条失败或取消请求的账单。因此旧未知费用仍保持未知，没有将失败请求假设为免费。原始预算 ledger 没有被“补成”完整已知。

为了继续时不重置 $5 预算，为前 3 次不完整记录各保留原 $1 reservation。后段三次完整计量合计 $1.00272375，加探测后，可用预算为：

```text
5 - 3 - 1.00272375 - 0.000075 = 0.99720125 USD
```

这不足下一次 $1 派发预留，所以 `recent-low` / `recent-high` 未启动。**停止原因是本地实验预算策略，不是供应商返回余额不足。** reservation 是发起前检查，并非供应商硬扣费上限；执行中的一次任务仍可能超过预留。没有为凑齐对照而扩大预算。

## 三个参数究竟是否生效

| 参数 | 实测证据 | 结论与限制 |
|---|---|---|
| defaultThinkingLevel | 真实 callback 分别记录 low、medium、high；Pi 状态与请求设置匹配 | 三档已在请求层生效；不能由单次费用/得分波动断言因果收益 |
| compaction.reserveTokens | 8192、16384、32768 均在真实任务中载入并核验 | 未观测到压缩，因此未验证真实压缩行为差异 |
| compaction.keepRecentTokens | 实际任务仅核验默认 20000 | 10000 / 40000 因预算未运行；没有真实保留窗口效果对照 |

当前真实模型 context window 为 **400,000**，max completion 为 **128,000**，不是旧 mock 的 128k / 16k 假设。所有 real worker、诊断与 live HPO 使用 `Space(live=True)` 并保存有效空间。当前搜索值下，Pi 必须严格超过以下上下文才触发阈值压缩：

| reserveTokens | 触发阈值 |
|---:|---:|
| 8192 | >391808 |
| 16384 | >383616 |
| 32768 | >367232 |

这 6 次任务记录到的最大 assistant 上下文仅 **70,277 tokens，约为窗口的 17.57%**。这是响应 usage 快照，不包含之后工具/用户内容估算，不是全程瞬时峰值。5 次有正常结束审计且未出现压缩事件；bike-rebalance 超时且没有正常结束事件，其压缩观测标为不完整，不能写成确定的“全程零压缩”。

原生合成历史探针（本地或历史材料，未打包：`../runs/compaction-native-probe-20261027.json`） 仍可证明锁定 Pi 的阈值和保留切点随参数改变；它没有调用真实模型，不是本轮真实任务中的压缩效果证据。

## 原模型可用性排查

原失败轨迹中的结构化错误是 403：`This model is not available in your region.`，路由失败阶段为 `Gate Endpoints with Geo Restrictions`。LiteLLM 外层将它包装成了 500。没有把该错误改写成余额不足。

只读检查确认密钥有效、模型仍在账户目录中；旧 8 次成功请求的 generation 记录可查询。随后在相同模型和默认路由下，一次 64-token 上限、medium、无 SDK 重试的极小请求成功，真实多轮任务也恢复。没有修改地区、代理设置或供应商路由。已核对的成功 generation 来自 OpenAI；这不证明未来每次路由都永久可用，也不能确定最初地区拒绝的后台根因。

证据：只读检查（本地或历史材料，未打包：`../runs/pi-diagnostic-availability-20261027/read-only-review.json`）、可用性探测（本地或历史材料，未打包：`../runs/pi-diagnostic-availability-20261027/generation-probe.json`）。账户总余额接口要求管理密钥；当前普通密钥可读取自身额度，但不能据此冒充账户总余额。

## 本轮发现并修复的计量与清理问题

原生 agent 超时可能终止一个尚未写出 callback 的请求。仅检查“现有 callback 都成功”不能证明没有漏计。现在，原生超时、缺少正常 agent settled 或 aborted settled 都不能被认证为完整任务费用；保留已知请求记录，将完整金额置为未知并停止后续派发。

另外，进程组终止的权限错误不再跳过 Docker 清理。它会记录 `process_cleanup_unverified`，仍按该尝试唯一的 Compose 标签清理并核查容器、网络和卷。low 的残留资源已用同一精确标签补充清理，6 次任务的资源清理均已验证。没有操作其他项目资源。

bike-rebalance 原始 `result.json` 曾错误地把 $0.50211585 当作完整估算；现在保留原件，并单独给出 corrected-result.json（本地或历史材料，未打包：`../runs/pi-diagnostic-real-20261027-continuation/attempts/baseline-secondary/corrected-result.json`）。后续分析必须使用该纠正，不使用旧 summary 的已知总额覆盖不确定性。low 的恢复见 post-interruption-review.json（本地或历史材料，未打包：`../runs/pi-diagnostic-real-20261027-continuation/attempts/thinking-low/post-interruption-review.json`）。

最终核验：134 项测试中 118 通过、16 因运行时依赖跳过；另 8 项运行时适配器测试通过。见 `runs/pi-diagnostic-final-tests-20261027.log` 和 `runs/pi-diagnostic-final-runtime-tests-20261027.log`。锁定第三方源码未修改。

## 下一步边界

尚不能宣称三个参数都在真实任务中产生了行为差异。剩余 keepRecent 对照本身也需要任务实际触发压缩，才有能力检验保留窗口效果。下一步应先设计并预选长上下文诊断，或明确将当前短任务实验限制为 thinking 参数研究；不要把未激活的压缩维度继续当作有效搜索维度。

本轮保留全部失败、超时、取消和预算停止记录。正式任务数量、搜索次数、随机种子与总预算尚未确定；应在计量完整、参数确实被激活、数据划分和相关任务分组核查完成后再定。
