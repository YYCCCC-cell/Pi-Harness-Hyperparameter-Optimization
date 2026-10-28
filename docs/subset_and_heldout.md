# 验证子集、独立留出入口与跨任务校准

2026-10-27。现在支持带版本和固定哈希的 8 任务验证子集，以及冻结赢家后才可使用的独立留出评测入口。本轮只授权一笔 **$5 跨任务校准**，未授权正式搜索或真实留出运行。

后续授权的原预算续跑已结束：共 9 次尝试覆盖 8 个任务，7 项模型任务完整计量，1 项 agent 超时完整费用未知。已知请求费用 $1.03555110，额外冻结 $1 后可分配余额 $2.96444890。举重任务环境已恢复并通过官方判分。见 [校准收尾与最新规模方案](cross_task_calibration_completion_20261027.md)；正式搜索和真实留出仍未启动。

## 验证子集

在 live 配置中显式设置 `validation_profile: "grouped_v2"`，控制器和运行时都使用 [八任务投影](../configs/hpo_validation_panel.v2.json)。它保存原始划分、家族审计来源哈希、任务名单及 8 个家族组。加载器核验文件哈希、任务唯一性、原验证集归属和完整分组。未设置时仍使用原来的 28 任务名单；mock 不变。

`space_profile: "early_compaction_v2"` 独立控制参数空间，不隐含任务子集。两个选项分别进入 manifest。HPO 配置不接受留出名单或 evaluator access；优化器只取得选中验证任务的结果。验证投影的加载过程不读取留出名单、提示词或成绩。

## 独立留出评测

入口为 `python -m evaluation.heldout`，与 HPO 搜索入口分开。执行前必须由完整的 live 验证子集实验冻结所有声明的方法赢家，不能从中断批次或部分 panel 提名。冻结时独立核对 journal、费用、完整 panel、选择规则、模型和运行时；记录源 manifest / summary / events 的哈希及全部赢家配置。

冻结清单对应 [16 任务留出投影](../evaluation/panels/heldout.v2.json)，与验证任务及家族互斥。worker 每次执行前重新检查冻结文件、源实验、配置、运行时、任务归属和评测种子。没有冻结凭据时，留出任务在读取任务文件前被拒绝。

源实验只允许冻结一次；冻结身份对应的派发 claim 也只允许创建一次。复制清单、更换输出目录或重复执行命令都不能重置已消费的批次。中断后保留费用、attempt 和未决状态，不自动补跑。默认比较中即便两个方法选中同一配置，也各自消耗声明的留出尝试，不跨方法缓存。

下面是未来使用方法，**本轮未执行这些真实留出命令**：

```bash
.venv/bin/python -m evaluation.heldout freeze \
  --campaign runs/completed-live-validation --output runs/new-frozen-selection
.venv/bin/python -m evaluation.heldout prepare \
  --freeze runs/new-frozen-selection/frozen-selection.json \
  --budget-usd 10 --output runs/new-heldout-preflight
# run 需要另行确定并授权实际预算；10 只是参数写法示例。
```

`prepare` 不构建任务镜像、不调用模型、不运行 verifier；`run` 才会消耗预算。该边界是进程和代码层的协议约束，不是针对能任意修改本地代码的攻击者的操作系统隔离。真实留出结果只保存在独立输出目录，不回传给搜索算法。

## 本轮 $5 校准

专用入口只使用原生默认 `medium / 16384 / 20000`，覆盖上述八个验证任务，不调用优化器。它以任务原生 agent 时限排序，固定种子哈希打破并列，不按历史得分或费用选顺序。最多八次，每个任务一次，原生依赖、Skills、官方 verifier 与阶段时限保持不变。

```bash
.venv/bin/python -m evaluation.calibrate prepare --output runs/new-calibration-preflight
# 本轮真实批次已使用唯一 allocation claim；不要重复发起。
```

总派发预算固定 $5，每次预留 $1，预算不足停止。未知费用、超时造成的不完整计量、有效参数未核实或清理不确定也会阻止后续派发。预算是派发门槛，无法保证已经在途的供应商请求不超支；有完整计量时报告实际请求记录和估算口径，不将失败请求假设为免费。重复命令不会追加新的 $5 额度。

校准数据用于确定环境可执行性、跨任务成本和耗时，不创建免费优化器观测，不得据此宣称某个搜索方法更优。是否能作为后续正式实验的 Default 记录，需要在正式协议中明确纳入并核对模型、任务、预算和来源，不能静默复用。

## 验证与记录

- 控制器回归（本地或历史材料，未打包：`../runs/subset-heldout-final-full-tests-20261027.log`）：161 项中 143 通过、18 项依赖跳过。
- 运行时测试（本地或历史材料，未打包：`../runs/subset-heldout-runtime-tests-20261027.log`）：10 项通过，包括留出任务无凭据拒绝、带测试凭据的 16 任务原生环境元数据规划；没有留出模型或 verifier 执行。
- 新入口定向测试（本地或历史材料，未打包：`../runs/subset-heldout-final-status-tests-20261027.log`）：12 项通过，包括全部五种方法在子集上的控制器测试、冻结身份校验、独立留出入口的假后端运行和重复消费防护。这些是假后端软件测试，不是 benchmark 分数。
- 真实校准预检（本地或历史材料，未打包：`../runs/cross-task-calibration-preflight-20261027/summary.json`）、真实运行目录（本地或历史材料，未打包：`../runs/cross-task-calibration-real-20261027/manifest.json`）。

原 $255 / 408 次草案保留为历史规划，不能据此自动发起实验。待本轮费用和耗时结算后再决定规模。

## 原预算续跑（2026-10-27 后续授权）

用户随后明确授权处理举重任务构建超时，并使用原 $5 的余额补齐校准。新增 `--continue-from` 只接受已结算、主动停止的原始批次，核对原始全局 claim、固定计划、每次原始结果、清理和费用；从 $5 中扣除原费用后才建立新的派发 ledger。复制旧目录、更换输出位置或重复执行不能重置额度。

本次续跑固定为：powerlifting-coef-calc、bike-rebalance、llm-prefix-cache-replay、3d-scan-calc、crystallographic-wyckoff-position-analysis。第一项是用户明确要求恢复的构建失败，只有确认 provider 从未启动、模型调用和费用为零时才允许恢复。原失败记录和耗时保留；已经执行过模型的三个任务不重跑。这不是正式实验中的自动重试规则。

```bash
.venv/bin/python -m evaluation.calibrate prepare \
  --continue-from runs/cross-task-calibration-real-20261027 \
  --output runs/new-continuation-preflight
```

原支出 $0.24980250，续跑派发额度 $4.75019750；两段合计仍属于同一笔 $5。续跑也保留原生任务时限、费用未知即停止和按精确标签清理的规则。`run` 消费唯一续跑 claim，不得通过删除 claim 重复派发。准备模式不调用模型。

续跑中的 bike-rebalance 再次触发原生 900 秒 agent 超时。该批次按规则停止；其完整费用继续为 null，20 个已完成回调的费用仅作已知部分。只读核对确认这段 key 增量与已知请求合计 $0.54160260 一致，但未将超时记录改成完整计量。

在本轮明确的“补齐校准、仍限原 $5”范围内，提供一次独立恢复：`--timeout-reconciliation <readonly-audit-directory>`。它仅适用于首个续跑中的一次原生 agent 超时，验证原始 claim/计划、结果、清理、回调和只读核对来源；出现重试、压缩或其他供应商错误时拒绝此恢复。额外冻结 $1，保持未知费用状态，并在派发前重新确认 key 用量未增长。按记录模型价格，完整 400k 输入加 128k 输出的单请求价格包络为 $0.876；$1 是额外风险预留，不是对该超时任务最终费用的证明或供应商硬限额。

因此，恢复前已知费用 $0.79140510、额外预留 $1，可派发余额 $3.20859490。只运行尚未执行的后三项；不重跑自行车任务。恢复也有唯一全局 claim，不可再次复制或递归恢复。正式 HPO 和留出入口仍禁止从不完整计量的验证实验冻结赢家；这项校准恢复没有放宽正式比较规则。
