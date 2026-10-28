# 自动延迟回执：最后一个真实工程验收

当前生产路径已通过离线回归与本地 HTTP 集成测试。真实受控超时有完整侧车补账，但**完整自动等待流程尚未真实验收**。本次进程没有 `OPENROUTER_API_KEY`，没有派发真实诊断或正式实验。

新增 `automatic-receipts` 诊断入口复用原生执行器，只将自行车 agent 时限设为 20 秒。它不向 HPO 提供观测、不执行留出，也不延长任务答题时间。最多一次尝试，保留原 $5 额度中已知 $1.53209730、历史未知预留 $1、首轮未知余量 $0.986443，剩余可派发 $1.48145970。新尝试预留 $1，不能删除 claim 重跑，也不能释放未知费用。预留是本地请求派发门槛，不是供应商硬扣费上限。

## 本机执行

在保有历史 receipts、固定运行时与 Docker 的原工作区执行，每次使用新目录。纯上传包缺历史原件，不能直接运行此诊断。

```bash
.venv/bin/python -m evaluation.controlled_timeout prepare \
  --revision automatic-receipts --output runs/automatic-receipts-preflight
```

prepare 会读公开模型元数据并检查本机运行时，**不调用模型**。若模型价格/身份、依赖、证据哈希或预算账本变化，先审阅差异。账户用量变化时实际运行会拒绝派发，需要只读对账，不能更新基线来绕过检查。

本机凭据可通过 `OPENROUTER_API_KEY` 环境变量或下列入口的隐藏提示输入；不要发到聊天、写进配置、录入源码或截图：

```bash
.venv/bin/python -m evaluation.controlled_timeout run \
  --revision automatic-receipts --output runs/automatic-receipts-real
```

这条命令会产生真实诊断费用，属于独立工程验收，不能与正式实验批量串行运行。进程失败、费用未知或验收无定论时停止，不自动再试。历史诊断原件保持不变。

## 通过条件

1. 自动原始 `summary.json` 的 `timeout_metering_verified=true`，任务仍为 timeout。
2. `request-accounting.json` 的请求清单完整，回执自动补齐，费用已知，清理与实际参数核验通过。
3. 若观察到 404 且自动恢复，`automatic_delayed_receipt_polling_verified=true` 才能证明真实延迟路径。若直接取得回执，这一项仍为 false，记录“普通自动计量通过，延迟场景未观察到”。不要为了得到 404 自动重复扣费。
4. 保留原始摘要、请求账本和哈希，再以只读方式核对账户增量。不要用事后侧车结果改写原始自动结果。

本地 HTTP 测试调用真实 HTTP 解析、对账和评估汇总路径，覆盖 404→200、403 停止、错误模型和缺 generation ID。服务是本地 fixture，**不能替代真实供应商结算验收**。
