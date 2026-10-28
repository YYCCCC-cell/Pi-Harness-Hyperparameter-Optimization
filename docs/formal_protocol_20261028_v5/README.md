# 正式协议 v5：请求计量与真实报告接入

2026-10-28。沿用 [v4 的研究协议](../formal_protocol_20261028/README.md)：3 参数、27 点空间，8 个验证任务、16 个留出任务，四搜索方法各 13 配置，总计 424 次验证 + 80 次留出。仍只有一个搜索种子，不承诺 IGBS 优于 BO。v4 的 504 次 / $155 是本版保留的**待复核规模与派发额度**，不是新增授权、费用报价或供应商硬限额。

本版冻结新的固定运行条件 `live.accounting_policy=request_journal_v1`；算法、题目、参数值、次数与选优规则不变。旧协议与历史结果不覆盖。

## 请求计量规则

1. 代理在转发前持久化 request_started；供应商请求前记录 provider_attempt，流式响应出现 ID 时即保存 generation ID，完成或失败后记录终态。文件仅保存调用标识及计量元数据，不保存提示词、正文或密钥。
2. 代理退出后，将请求记录和计量回调做哈希封存。账本必须逐条匹配；没有开始记录、重复结束、重复 ID、缺失 handoff 或未知请求都不能被已有成功回调掩盖。
3. 固定关闭 LiteLLM Router / OpenAI SDK 的隐式重试，避免同一 handoff 下有不可观测的多次 HTTP 请求。Pi 本身的行为保持不变；它重新发起的请求都有独立账本记录。这项传输设置对所有方法相同，不属于搜索超参数。
4. 完整成功请求优先用供应商 usage.cost，缺失时保留 LiteLLM 估算及其来源。已知 generation ID 但终态费用缺失时，只读查询供应商 generation 元数据；必须匹配 ID、模型目录中确切的公开 ID 或 canonical_slug、终态、token 数与费用。查询失败、没有 ID 或未结算继续记未知，不把预留当实际费用。
5. 原生 agent 超时仍记失败。只有整个请求清单完整落账、参数/模型已核实、worker 正常收尾且清理通过时，才可作为“已计量失败”进入统计；不完整费用仍停止整个比较。外层中断、清理失败和模型身份异常不会因为查询到部分回执而解除。

对账查询单次最多 15 秒，整个阶段设置 30 秒派发期限；剩余时间不足时缩短单次超时，401/403 后不继续尝试其他 ID。对账耗时单列在 execution.json，并计入任务总 wall time；这些是任务结束后的计量开销，不延长原生 agent 时限。

旧 bike-rebalance 只有 20 个完成回调，没有新账本，因此其完整费用不能由这次代码修复倒推出来。原始 null、历史已知费用与原 $1 风险预留保持原意。独立日志导出和金额复核由项目另一聊天维护，本版不覆盖这些文件。

本次本地代理使用真实 LiteLLM 进程与本机模拟上游，覆盖 Chat Completions / Responses 完整流、中途取消、500 和连接中断。六次代理请求对应六次上游 HTTP 请求，只有两次完整成功记录可直接结算；取消和失败保持未知。这证明软件路径的边界，不是一次真实 Pi 超时或供应商账单验证。

## 真实报告入口

新增 `evaluation.live_report`：从运行日志核对任务、配置、费用、冻结来源与固定测试分母；从已审计记录重建美元搜索曲线，使用共同已观察区间的阶梯值比较；生成验证/测试成绩、泛化差距、搜索/运行成本、局部参数对照、IGBS/pair-blind 路由与双向失败案例。

未执行或残缺的留出实验保持 null，不用更小分母制造 pass@1；模拟数据默认拒绝，只有显式 `--allow-fixtures` 才能生成带醒目标识的测试报告。报告不调用模型、不修改优化器历史。费用称为 accounted USD，不冒充已核对发票。

未来真实验证结束后的命令（本次未执行付费验证）：

```bash
.venv/bin/python -m evaluation.live_report \
  --campaign runs/completed-validation \
  --output artifacts/new-validation-report

# 完成冻结及独立留出后才提供下面两个参数：
.venv/bin/python -m evaluation.live_report \
  --campaign runs/completed-validation \
  --freeze runs/frozen-selection/frozen-selection.json \
  --heldout runs/completed-heldout \
  --output artifacts/new-final-report
```

`scripts/plot_live.py --report <report-directory> --output <new-figure-directory>` 可导出 SVG 搜索曲线，使用 ReportLab。模拟报告的图也保留 fixture 标识，不能放进正式结果区。

## 当前状态与启动条件

- [配置](validation-config.proposal.json) 和 [机器协议](run_manifest.v5.proposal.json) 保存新政策、代码/数据来源哈希及待处理事项。
- 软件验证（本地或历史材料，未打包：`../../artifacts/step4-readiness-20261028/README.md`） 记录回归、本地故障测试和五方法流程检查。本次真实模型调用为 0。
- 在真实模型入口验证新计量路径、完成金额复核并确定具体派发额度后，才能进入正式实验。现有校准中的未知费用不能用测试通过来消除。
- 真实执行环境需要通过隐藏终端输入或环境变量提供 API 凭据；当前聊天的执行环境未取得该变量。不要将密钥写入配置、文档或聊天。

协议字段 `execution_enabled=false` 是审阅状态，控制器不会将它当作授权锁。后续修改计量实现、算法、模型元数据或预算后，应创建新的审阅快照；不要直接用旧 v4 的来源哈希声称核验了新代码。

供应商依据：[generation 查询文档](https://openrouter.ai/docs/api/api-reference/generations/get-generation) 描述按 generation ID 查询费用和 token 元数据；[官方流式文档](https://github.com/OpenRouterTeam/docs/blob/main/api_reference/streaming.mdx) 说明取消行为受提供商支持情况影响。因此本项目使用逐请求可核对证据，不从“连接已断开”推断零费用。
