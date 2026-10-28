# Phase 2：Pi 运行环境与单任务 pilot

当前状态（2026-10-26）：**一次真实 OpenRouter hello-world pilot 已通过，`success=true`、`pilot_gate_passed=true`，官方 verifier 的两个测试均通过。** 最终结果（本地或历史材料，未打包：`../runs/pi-pilot-20261026-200805-21899/result.json`）：总耗时约 97 秒，输入 2262 / 输出 52 tokens，本地估算费用 0.0012393 USD，低于配置的 1 USD 预算。服务商账单尚未独立核对。本次为 sanity task，不属于正式 87 题成绩或 HPO 实验。历史预检保存在 `runs/archive/pi-setup-20261026/phase2-preflight-20261025/`。

2026-10-26 的首次派发在 BenchFlow setup 阶段因 `hello-world` 没有 bundled skills 而退出，尚未启动容器或调用模型。项目已将该 sanity task 改为 `no-skill`，兼容 Docker 返回 `stderr=None`，并在清理容器时保留共用的预构建镜像。恢复决定保存在当前构建目录的 `repair-record.json` 中；未修改第三方任务或 verifier。按用户要求，失败调试目录已移至废纸篓，具体清单见 整理记录（本地或历史材料，未打包：`../artifacts/pi-runtime/cleanup-20261026.json`）。

恢复后的构建证据在 `runs/runtime-ready-20261026-repair/`。不发送模型 prompt 的生命周期检查在 `runs/runtime-startup-check-20261026-194903/probe-result.json`：官方 verifier 对空工作区返回 reward=0，证明判分器能够运行，**不代表模型完成了任务**。清理后镜像保留，容器已移除。

## 已经准备好的环境

| 项目 | 当前状态 |
|---|---|
| Mac 宿主机 | Docker 服务可用；`.venv-runtime` 中 BenchFlow 0.6.3，依赖检查通过 |
| 容器 | Ubuntu 24.04 / Linux arm64，基础镜像按 digest 固定 |
| Pi | 从 `pilot.config.PINS` 的固定源码构建，版本 1.4.0 |
| pi-acp | 从固定源码构建，版本 0.0.34 |
| Node | 本次镜像实际版本 24.22.1 |
| 模型 | OpenRouter ID：`openai/gpt-5.4-mini`；BenchFlow 路由 ID：`openrouter/openai/gpt-5.4-mini` |
| 凭证 | 仅通过 `OPENROUTER_API_KEY` 环境变量提供 |
| 默认设置 | medium / reserveTokens=16384 / keepRecentTokens=20000 |
| 真实模型调用 | 已完成一次真实 hello-world pilot；未进行 HPO 搜索或 held-out 评测 |

实际选中的不可变镜像 ID 和记录路径在 [pilot.json](../configs/pilot.json)。本地 `sha256:<64 hex>` 是 Docker 镜像的不可变标识，允许使用它，无需为了获得 registry digest 而发布镜像。可变 tag 不能作为运行配置。

本次证据：

- 当前构建日志（本地或历史材料，未打包：`../runs/runtime-ready-20261026-repair/build.log`）
- 当前构建记录、依赖摘要和支出控制（本地或历史材料，未打包：`../runs/runtime-ready-20261026-repair/runtime-review.json`）
- 当前镜像的离线 RPC / ACP 测试结果（本地或历史材料，未打包：`../runs/runtime-ready-20261026-repair/offline-smoke/result.json`）
- Docker 启动、ACP 连接与判分器检查（本地或历史材料，未打包：`../runs/runtime-startup-check-20261026-194903/probe-result.json`）
- 运行目录索引（本地或历史材料，未打包：`../runs/README.md`）
- 真实 pilot 结果（本地或历史材料，未打包：`../runs/pi-pilot-20261026-200805-21899/result.json`）与官方判分器日志（本地或历史材料，未打包：`../runs/pi-pilot-20261026-200805-21899/benchflow/phase2/hello-world-once/verifier/test-stdout.txt`）

离线检查证明：真实 Pi 进程能够加载模型能力、分别发送 low/medium/high、通过原生 write 工具创建文件；pi-acp 能初始化、创建会话、选择模型并执行工具。检查在 `--network none` 的非 root 容器中进行，只有容器内 loopback 模拟接口回答请求。**这是运行时验证，不是模型能力或 SkillsBench 成绩。**

## 在当前机器重新检查

以下命令都从项目根目录执行，每次输出目录必须是新的：

```zsh
cd "<project-root>"

.venv-runtime/bin/python -m pip check

.venv-runtime/bin/python -m pilot.smoke_runtime \
  --config configs/pilot.json \
  --output "runs/pi-offline-check-$(date +%Y%m%d-%H%M%S)"

.venv-runtime/bin/python -m pilot preflight \
  --config configs/pilot.json \
  --output "runs/pi-preflight-$(date +%Y%m%d-%H%M%S)"
```

离线检查不需要 API Key，也不消耗一次性 pilot 机会。预检不会调用模型。当前项目预算为 1 USD，并保留用户填写的服务商限额说明；执行进程仍需拥有 `OPENROUTER_API_KEY`。在设置过密钥的同一个终端执行命令。预检退出码 2 表示未准备好，不代表一次模型任务失败。

成功的预检输出 `ready_not_dispatched`，只保存 `preflight.json` 和配置快照，不生成 `result.json`。阻塞时的 `result.json` 是错误报告；真实 `pilot run` 完成后生成的 `result.json` 才记录任务与费用结果。

## 从固定源码重新构建

本机已有 `.venv-runtime`。在新机器上先按固定 commit 准备 BenchFlow 0.6.3 依赖，并恢复 `pilot.config.PINS` 所列第三方源码。然后执行：

```zsh
cd "<project-root>"

.venv-runtime/bin/python -m pilot.prepare_runtime \
  --platform linux/arm64 \
  --output "runs/pi-build-$(date +%Y%m%d-%H%M%S)" \
  --configure
```

`--configure` 会在镜像构建、依赖记录和离线检查通过后，将镜像 ID 与记录路径写入 `configs/pilot.json`，并保存修改前的配置。它不设置预算、不批准费用，也不发起真实 pilot。x86 Linux 可选择 `--platform linux/amd64`，但本次验证仅覆盖 arm64。

构建流程由 [prepare_runtime.py](../pilot/prepare_runtime.py) 和 [Dockerfile](../runtime/Dockerfile) 实现：

1. 验证固定源码，使用 `git archive` 导出独立副本；不在 `third_party/` 内安装或构建。
2. 使用 [固定基础镜像](../runtime/base-images.json)，以 `npm ci --ignore-scripts` 安装锁定依赖。
3. 在构建阶段获取公开模型目录，执行 Pi 官方构建与本地包打包逻辑，以及 pi-acp 构建。构建过程不传入模型密钥。
4. 最终镜像仅安装所需运行产物、Node、Python 和系统工具；不包含项目实验数据、测试答案或宿主机凭证。
5. 保存 npm locks、OS 软件包版本、实际模型目录和 SHA-256 清单；宿主机依赖另存为版本快照。
6. 运行断网 smoke，检查真实 Pi 的 RPC、ACP 和工具执行。

源码与基础镜像已固定，但模型目录和 Ubuntu 仓库仍有网络输入；实际构建结果会保存哈希。**当前不是独立重建后逐字节一致的可复现构建证明。** 如需迁移完全相同的运行环境，应保留当前不可变镜像及其构建记录，而非只依赖可变 tag。

## OpenRouter 接入方式

[openrouter.py](../pilot/openrouter.py) 在进程内扩展固定 BenchFlow 的 provider registry，第三方源码保持不变。完整调用路径为：

```text
BenchFlow → Docker 内 pi-acp → Pi
                              ↓
                       本机 LiteLLM 用量代理
                              ↓
                         OpenRouter API
```

代理使用 `OPENROUTER_API_KEY`；传给 Agent 的是代理凭证。启动器通过 Pi 官方 `models.json` / `settings.json` 接口写入模型别名、上下文、输入类型和推理能力，避免代理别名使推理档位被折叠为 off。`models.json` 仅引用凭证变量名，不写入真实 key。

OpenRouter 的模型目录包含 `file` 输入类型，但 Pi 当前模型配置只接受 text/image；适配层明确筛选这两项，不宣称直接支持原始文件输入。文件处理仍依靠任务工具。

Pi 到代理使用 `reasoning_effort`。本地 HTTP 集成测试验证 LiteLLM 保留 OpenRouter 的完整模型 slug 与 low/medium/high。真实 pilot 已验证本次凭证、路由及模型调用可用，RPC 记录观察到 medium 档位。low/high 的真实服务调用尚未测试。协议依据：[OpenRouter reasoning 文档](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens)。

代理别名是路由证据，不能当作上游模型身份的独立证明。结果分别记录 `proxy_route_matches`、`actual_model_id_matches` 和 `provider_identity_verified`。费用仍是估计值；缓存、重试及账单需要真实运行后核对。

## 单任务 pilot 的运行条件

本次 pilot 已完成，一次性派发标记已保留。下面说明运行条件与入口；再次执行会被标记阻止，不要删除标记来重复付费调用。

1. 在启动实验的同一个终端导出 `OPENROUTER_API_KEY`，不要写入 JSON、镜像或聊天。
2. 确定单任务美元预算，填写 `budget_usd`。
3. 在生成的 runtime review 中记录实际服务商侧支出控制，或用户明确接受的在途超支边界；不能凭空填写“已审核”。
4. 查看预检和一次性运行清单。只有预检返回 `ready_not_dispatched`，且费用输入已经明确后才运行。

**`budget_usd` 当前是结束后的超支检查，不是实时硬上限。** 凭证配置不会自动授权费用。

已准备好后使用同一解释器执行以下一次性命令：

```zsh
.venv-runtime/bin/python -m pilot run \
  --config configs/pilot.json \
  --output "runs/pi-pilot-$(date +%Y%m%d-%H%M%S)"
```

也可以在项目根目录执行 `./运行Pi测试.command`。脚本会显示结果目录；若当前终端没有密钥，会以隐藏输入方式提示输入。出现 `status: running` 表示预检已通过，正在执行；最终结果以新目录中的 `result.json` 为准。

runner 只允许独立的 hello-world sanity task，不属于 87 个正式计分任务。一次派发会创建 `runs/.phase2-dispatched.json`；不要删除它重试。真实任务失败时保留日志和费用记录，重新决定下一次尝试。

官方 verifier 会在容器中使用 apt，并下载执行 uv 0.9.7 安装器及 pytest 8.4.1。2026-10-26 的独立生命周期检查已执行该 verifier，空工作区得到预期的 reward=0；断网 smoke 本身仍不包含 verifier。后续执行仍依赖这些下载服务可用。不得将 verifier 改到宿主机执行。

## 测试与结果边界

```zsh
.venv-runtime/bin/python -m unittest discover -s tests -p test_runtime.py -v
.venv-runtime/bin/python -m unittest discover -s tests -p test_pilot.py -v
```

HPO 回归使用原 `.venv` 与固定进程环境：

```zsh
env PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -m unittest discover -s tests -v
```

`test_runtime` 中需要 BenchFlow 的测试在 HPO 环境中会跳过，因此必须同时运行上面的 `.venv-runtime` 测试。两个环境分别保留，避免依赖互相覆盖。

本次真实 API、工具执行和官方判分已通过，但短任务不代表两个 compaction 参数触发过。代理模型别名不构成上游模型身份的独立证明，估算费用也不等于账单核对。`runtime_observed` 中复制自镜像构建清单的 `model_calls_dispatched=0` 描述构建阶段，不能用于统计这次 pilot 调用；真实调用证据在 `trajectory/llm_trajectory.jsonl`，汇总用量在 `result.json`。真实 HPO evaluator 仍未接入；本次完成的是单任务 Pi 环境与真实调用链路验证。
