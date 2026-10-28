# 任务 2：小规模真实任务诊断

2026-10-27 最终更新：原计划 **8/8 项已执行**，另完成 3 项真实范围校准；新版空间在原模型 400k 任务窗口中产生了 **2 次正常自动压缩**，三档 thinking 的请求控制和同历史 keepRecent 保留边界均有证据。第 2 步工程诊断已完成，历史异常费用仍未知，官方任务 reward 均为 0。详见 [诊断闭环](pi_diagnostic_completion_20261027.md) 和 [第 3 步实验规划](run_review_20261027/README.md)。下面描述原八项诊断的准备与运行接口；原空间未触发压缩，后续显式选择的 `early_compaction_v2` 使用独立记录，不改写原始运行。

## 真实模型与搜索空间

重新读取了 [OpenRouter 公共模型目录](https://openrouter.ai/api/v1/models)，结果与已审核运行时元数据一致：`openai/gpt-5.4-mini` 的 context=400,000、max completion=128,000，支持 reasoning effort。快照和比对结果位于 `runs/pi-diagnostic-prepare-20261027/model-catalog.json`、`metadata-check.json`。该目录列出的标准输入/输出价格为 $0.75/$4.50 每百万 tokens；实际路由、缓存和账单可能不同，不据此编造单任务实测费用。

`Space(live=True)` 现在用于真实 HPO、worker 校验与本诊断。它从 `runtime/openrouter-model.json` 生成真实 feasibility；有效空间写入运行 manifest。原 `configs/hpo_space.json` 中 128k/16k 假设仅保留给既有 mock 复现。27 个候选均通过真实模型的保守可行性检查，**可行不等于会触发压缩**。诊断在每次新运行前刷新公共目录；相关元数据改变时阻止调用，要求重新核对，不静默覆盖已审核运行时。

锁定 Pi 的触发条件是 `contextTokens > contextWindow - reserveTokens`，等于阈值时不触发：

| reserveTokens | 严格超过此上下文 token 数才触发 | 占 400k 比例 |
|---:|---:|---:|
| 8192 | 391808 | 97.952% |
| 16384 | 383616 | 95.904% |
| 32768 | 367232 | 91.808% |

`keepRecentTokens` 决定已触发压缩时的保留切点。短任务可以把三个参数都正确装载，却只实际用到 thinking level。Pi 的原生输出上限还会根据剩余上下文和 4096 安全余量动态缩小；128k 是模型上限，不是每次固定生成长度。代码依据：`third_party/pi-mono/packages/coding-agent/src/core/compaction/compaction.ts`、`packages/ai/src/api/simple-options.ts`。

## 固定诊断范围

配置：`configs/pi_diagnostic.json`。在查看真实成绩之前，选定两个冻结验证任务：

- `llm-prefix-cache-replay`：代码/性能任务，作为单参数对照的主任务。
- `bike-rebalance`：运筹优化任务，包含额外 solver 依赖和 no-network 策略，作为默认设置的第二环境对照。

两者先前已通过原生容器、Skills 和官方 verifier 的离线连通性检查。按此事前选择的顺序运行：两个默认设置，主任务 thinking=low/high、reserve=8192/32768、keepRecent=10000/40000。每次只改一个参数，其余使用 medium/16384/20000。共最多 8 次尝试，无重复补跑、无外层重试、无优化器。该样本不能评估统计显著性或确定最优参数。

总 USD 门槛 5、单次预留 1、执行墙钟上限 3 小时，原生 build/agent/verifier 超时不变，清理允许额外耗时。已有 reservation ledger 在费用不明、计量失败、超出预留或清理不确定时停止后续尝试。它是发起前预算检查，不是供应商硬账单限额；正在执行的一次任务可能超支。没有启动旧草案的 4,827 次尝试，也没有扩大到 140 次全验证集 HPO 示例。

## 新增观测与判定

`evaluation/live_rpc_audit.py` 透明转发 RPC，不插入提示词、命令或测试历史。原有已审核的 pilot 包装器保持不变；live worker 上传新的独立审计器。

- 修正旧审计器的事件名：本版本发出 `compaction_start` / `compaction_end`，而非 `auto_compaction_*`。
- 记录启动版本、Pi 模型/contextWindow、thinking state、assistant token usage、agent settled，以及压缩原因、完成/中断、tokensBefore、estimatedTokensAfter、firstKeptEntryId。不会把 prompt、tool 内容或压缩摘要复制进审计日志。
- 在 provider callback 删除临时文件前保存每次请求的 reasoning effort、响应 ID、usage、估算费用及时间。锁定 Pi 的普通请求和默认压缩请求都使用当前 thinking level；诊断要求所有记录的请求匹配。
- `execution-evidence.json` 区分参数写入、请求级生效、压缩完成、尝试但未完成、完整观测中未出现、日志不足而未知。旧日志和不完整日志不会被解释为“0 次压缩”。
- 上下文最大值来自 assistant usage 快照，并非完整逐时刻峰值；不包含随后 tool/user 内容的估算。不能用其低于阈值单独断言没有压缩。
- 保存官方 reward、输入/输出 tokens、模型调用数、整个任务墙钟耗时，以及 BenchFlow 提供的阶段计时。LiteLLM `response_cost` 为估算；若所有调用均提供 `usage.cost`，另记 provider-reported 总额。两者都不冒充已核对账单。

所有尝试都没有压缩事件时，报告要求不要把 reserve/keepRecent 下的分数波动归因于压缩。后续应先选择具有实际上下文增长的验证任务，或另行设计明确标注的压力实验；不能偷偷缩小正式模型窗口、注入填充历史后仍称为原任务成绩。

## 使用

在项目目录运行；每次输出目录必须是新的。`prepare` 不读取供应商密钥，不构建容器，不调用模型：

```bash
cd '<project-root>'
.venv/bin/python -m evaluation.diagnostic prepare --output runs/my-diagnostic-preflight

# OPENROUTER_API_KEY 已在启动环境中设置时，执行固定的少量真实任务。
.venv/bin/python -m evaluation.diagnostic run --output runs/my-real-diagnostic
```

在另一个终端中 `export` 不会自动更新正在运行的 Codex 进程环境。可从已配置的终端执行上述命令，或向 Codex 提供已有本地密钥文件路径以便在指定进程中读取；不要把密钥粘贴到聊天。程序默认不搜索磁盘、Keychain 或其他任务中的凭据。

主要产物为 `manifest.json`、公共目录快照、`live-preflight/`、逐次 `attempts/*/result.json` / `execution-evidence.json` / provider metering / 官方 verifier 输出，以及 `summary.json`、`report.md`。中断时保留 `inflight.json`，不会自动重跑。

### 地区错误后的显式续跑

用户明确选择保留原模型并在排查后继续时，可使用 `run --continue-from <原运行目录> --availability <可用性探测.json> --output <新目录>`。续跑要求原配置、固定计划、运行时与源码锁一致，先前结果和清理均有记录，且没有未解决的 `inflight.json`。还要求一小时内同模型、原路由的成功可用性探测。它只执行尚未启动的计划尾部；第一次失败尝试仍消耗原 8 次名额，不补跑。

原有未知费用仍保持未知，每条未知费用记录完整保留原 $1 reservation 作为不可使用的预算，另外扣除探测费用和先前已知成本，再计算新段上限。前次任务墙钟时间也会扣除。该政策继承原来的“执行中可能超出预留”限制，不把预留伪装成实际账单。新段一旦再次出现计量缺失仍立即停止；不会循环续跑。排他 `continuation-claim.json` 阻止对同一个原运行重复派发，原 manifest、summary 和结果文件不修改。续跑及可用性探测分别留证，不计作新的独立 8 次实验。

## 已执行的核验及界限

- `runs/compaction-native-probe-20261027.json`：在锁定容器、`--network none` 下，直接调用 Pi 原生函数。38 万 tokens 时三个 reserve 的触发值是 false/false/true；39 万时为 false/true/true。合成 40 万 token 历史的三个 keepRecent 分别保留估算 10k/20k/40k，切点不同。0 次真实模型调用；这是机制探针，不是任务成绩。
- `runs/pi-diagnostic-audit-smoke-20261027/smoke-result.json`：真实 `llm-prefix-cache-replay` 容器、Skills、Pi RPC/ACP 和官方判分链通过本地 fixture 验证；审计记录实际 400k 模型元数据、usage 和 settled。未解题的官方 reward=0，清理已验证。0 次付费调用。
- `runs/pi-diagnostic-full-tests-20261027.log`：126 个测试，110 通过、16 个运行时依赖测试跳过；`runs/pi-diagnostic-runtime-tests-20261027.log` 的 8 个适配器测试通过。后续预算中止用例与诊断测试共 11 个，见 `runs/pi-diagnostic-unit-tests-20261027.log`。
- `runs/pi-diagnostic-credential-gate-20261027-final/live-preflight/preflight.json`：唯一阻塞项是 `credential_environment_variable_missing:OPENROUTER_API_KEY`，未派发任务；`summary.json` 同时记录该原因和 0 次 dispatch。

上述离线证据不能提供真实成绩。后续真实执行与费用纠正在文首链接中，不能用历史 prepare / fixture 状态替代真实结果。三档 thinking 的请求参数已核验，但真实压缩参数行为差异、完整 keepRecent 对照和代表性成本分布仍待验证。正式实验规模与预算属于下一步，不能用 hello-world 或这几个失败任务的成本直接外推。
