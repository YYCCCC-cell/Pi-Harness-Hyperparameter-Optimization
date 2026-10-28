# 自行车超时计量、历史日志导出及预算复核

后续已按同一 $5 预算完成一次真实任务；最新费用、余额及未覆盖的超时边界见 [单次真实计量复核](timeout_metering_real_review_20261028.md)。下面保留的是这次真实验证前的历史记录。

2026-10-28，香港时间。**本轮未启动正式搜索、独立留出或付费任务重跑。历史自行车完整费用仍为 null；本地计量修复不能补造过去未记录的请求。**

## 已恢复的历史数据

按香港时间 `[2026-10-27 23:00:00, 23:20:00)` 和模型 `openai/gpt-5.4-mini` 导出项目已有请求元数据。扫描范围为项目 `runs/`、`runtime/`、`artifacts/` 中的 JSON、JSONL 和日志，排除复制的第三方源码和任务输入；未读取用户全局缓存或密钥配置。扫描时共 13,886 个项目日志文件。无额外 generation ID 候选，解析错误为 0。

| 任务 | 已观测成功请求 | 已知 API 费用 USD |
|---|---:|---:|
| powerlifting-coef-calc | 11 | 0.06498255 |
| bike-rebalance | 20 | 0.47662005 |
| 本时段合计 | **31** | **0.54160260** |

这些“成功”表示模型请求完成，不代表任务官方判分通过。31 条已观测请求合计 Prompt Tokens **183,548**、Completion Tokens **112,824**、Total Tokens **296,372**。它们不包括无法枚举的取消/失败请求，不能作为完整账单。

- 请求元数据 JSONL（本地或历史材料，未打包：`../logs/openrouter_usage_20261027_2300_2320.jsonl`）：generation ID、模型、任务、请求时间、回调状态、token 数、provider `usage.cost`、独立保存的代理估价及来源索引。
- 机器可读汇总（本地或历史材料，未打包：`../logs/openrouter_usage_20261027_2300_2320.summary.json`）：逐任务费用、缺失字段数、来源 SHA256、导出 SHA256、搜索范围与完整性限制。
- [导出脚本](../scripts/export_openrouter_usage.py)：只读本地文件，网络请求数为 0；允许列表控制输出字段，去重时检查费用/token 冲突。

**缺失字段：**31 条记录的独立 Request ID、实际 HTTP 状态码、重试次数、取消标志均为 null。错误类型也没有记录，保持 null，不解释为“从未发生错误”。已有 `llm_trajectory.jsonl` 中的 HTTP 200 是 BenchFlow 根据成功回调合成的，不是原始传输状态，因此没有冒充真实 HTTP 状态导出。旧 RPC audit 只记录 assistant 完成，ACP 的 `terminal_trajectory_complete` 只说明工具轨迹，不证明上游请求已全部记账。

导出不包含 API Key、Authorization Header、Prompt、Completion、工具内容或个人信息。未把任何可能的第 21 次自行车请求编造为一条零费用记录。

## 403 与只读核对

本次只读访问记录（本地或历史材料，未打包：`../logs/openrouter_api_access_check_20261028.json`） 保存了 `GET /api/v1/analytics/meta` 的一次 **HTTP 403 / HTTPError**。错误响应正文没有保留，标为 null；未重复请求。根据 [OpenRouter 官方 Analytics 文档说明](https://openrouter.ai/blog/announcements/activity-dashboard/)，完整分析查询要求 management key，普通推理 key 返回 403。此次错误不能解释为余额不足，也不同于此前模型地区限制的 403。

同次查询的 key 累计用量为 **$4.1949079**，与上次校准恢复记录相同；这是 key 用量，非钱包余额，也不能单凭它解除历史超时费用的不确定性。浏览器 Activity 页面跳转登录，没有进行登录或权限变更。

## 计量代码修复与独立核验

共享工作区采用项目自有 `request_journal_v1`，不修改锁定的第三方源码：派发前持久化请求开始记录，记录 provider handoff 和流式 generation ID；代理退出后对请求清单与回调做哈希封存，再逐项核对完成用量或供应商 generation 回执。

只有请求清单完整且每项均有合法费用/token，原生 agent 超时才可以落账；任务仍保留 timeout / 未通过状态。缺 ID、未结算回执、重复/遗漏请求、封存不匹配或清理失败均不能被改成成功或零成本。正常结束与超时走同一计量审计。真实回执允许目录中审核过的 canonical model slug。

本聊天完成导出和预算回归测试，并独立审查共享修复；同项目另一聊天负责核心计量文件和真实 LiteLLM 对本地模拟上游的故障测试。实测供应商取消结算仍需之后的受限真实诊断，不能把本地 fixture 当成真实费用证据。最终验证结果另附于 核验记录（本地或历史材料，未打包：`../logs/timeout_metering_verification_20261028.json`）。

最终独立核验：完整回归 **196 项，177 通过、19 跳过**；另外显式启用的本地 LiteLLM 代理集成 **1 项通过**，运行时 adapter **10 项通过**。补充的 **3 项边界测试**验证了 403 后停止后续账单查询、总查询派发期限保留未知、对账耗时计入总 wall time 且原生 timeout 不变成成功。导出 **4 项**及预算 **2 项**测试也通过（这些包含在完整回归内，不重复累加）。31 条导出唯一 ID 和 token 算术全部一致，敏感模式扫描 0 命中；四个第三方仓库仍与锁定提交一致且干净。

本地代理覆盖六次 HTTP 请求：两个完整流、一个中途取消、两个 500 和一个连接断开；上游请求数与代理请求数一致。新协议固定禁用 SDK/Router 隐式重试；只读账单查询的派发期限为 30 秒，单次 socket 超时最多 15 秒，401/403 后不再查询其他 ID。对账开销单列并计入总耗时，不修改任务原生 agent 时限。

## 第三步规模与预算复核

保留 v4 确定并由 [v5 协议](formal_protocol_20261028_v5/README.md) 沿用的 **8 个验证任务、16 个独立留出任务**，Default 1 组配置，Random / BO / IGBS / pair-blind 各 13 组；搜索种子 20261027。IGBS 的 7 组初始化后保留 6 组适应性动作。正式验证 **424 次**，冻结后留出 **80 次**，合计 **504 次**。v5 明确启用新请求账本并固定禁止隐式重试；本轮没有新的完整费用证据支持改变任务集合或方法次数。

原 $5 校准：已知消费 **$1.03555110**；完整消费 **null**；未知费用预留 **$1**；预算占用 **$2.03555110**；可分配余额 **$2.96444890**。本轮模型消费新增 **$0**，没有释放预留。

| 计算情景 | 费用 USD | 性质 |
|---|---:|---|
| 以已知默认均值机械外推 504 次 | 65.24 | 基数含不完整超时费用 |
| 搜索 2 倍、留出 2.5 倍默认均值 | 134.62 | 规划假设，非测量上界 |
| 分阶段向上取整并留派发余量 | **155** | **仍为未批准草案** |
| 每个八任务 panel 另增加 $1 的同规则敏感性 | 285 | 压力情景，非建议增额、非实际消费 |

$155 的分配保持 Default $5、四个搜索方法各 $30、独立留出 $30。串行耗时按现有冷/热混合环境均值机械外推约 **56.2 小时**，两倍情景 **112.3 小时**；不是工期承诺，也不含单独的环境准备。

计算见 [可复算预算 JSON](timeout_metering_budget_review_20261028.json) 和 [脚本](../scripts/review_timeout_budget.py)。**第三步目前完成了算术复核，尚未达到“基于完整费用核定正式预算”。**代码修复不能追溯证明旧请求完整；若最终无法恢复旧账单，应在之后明确新的成本依据，并用原 $5 剩余额度完成受限真实计量验证，再确认正式额度。正式搜索和留出继续保持未启动。

## 本轮复现

在项目根目录执行：

```sh
.venv/bin/python scripts/export_openrouter_usage.py
.venv/bin/python scripts/review_timeout_budget.py
.venv/bin/python -m unittest discover -s tests -p test_usage_export.py -v
.venv/bin/python -m unittest discover -s tests -p test_timeout_budget_review.py -v
```

这些命令不发起模型请求。导出窗口是本次固定历史区间，不是滚动监控。历史 raw result、原预算账本和旧 proposal 保留，不因本轮复核而覆盖。
