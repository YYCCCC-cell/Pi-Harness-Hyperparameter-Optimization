# Pi Harness HPO

**固定 Pi Agent Harness 的配置优化研究｜EP6203｜工程验证版本，正式实验未完成**

本项目保持 Pi 源码不变，通过公开配置接口调节推理档位和上下文压缩参数，在 SkillsBench 上比较 Default、Random Search、SMAC Bayesian Optimization、自研 Interaction-Guided Block Search（IGBS）和匹配的 pair-blind 消融。

截至 **2026-10-28**，算法、真实任务执行器、请求计量及报告工具已有实现和验证，真实参数诊断与跨任务校准已经执行。**正式四方法搜索（当前缩减方案）和独立留出测试尚未执行；目前没有证明 IGBS 优于其他方法。**

**完成状态**

| 部分 | 已完成 | 尚未完成 |
|---|---|---|
| 固定系统与空间 | 四个上游来源锁定、三参数 allowlist、27 点空间、原生默认配置 | 正式派发前刷新模型和运行环境 |
| 优化方法 | Default、Random、固定版本 SMAC BO、IGBS、pair-blind；共同预算、选择与审计接口 | 真实预算下的完整方法比较 |
| 软件验证 | 三个种子、4,116 次 deterministic mock 尝试；控制器、冻结、留出和报告的离线验证 | 真实 benchmark 结果 |
| 真实运行 | hello-world 链路通过；参数机制诊断；8 个任务的默认校准 | 正式验证搜索及最终配置选择 |
| 请求计量 | 请求账本、封存、费用回执、清理；一次受控超时的侧车对账通过 | 自动等待延迟回执的完整真实流程；部分历史费用仍未知 |
| 协议与交付 | 发布审阅快照、可上传目录、复现说明、报告和展示草稿 | 正式预算批准、独立留出、最终图表／报告／幻灯片 |

详细边界见 [项目当前状态](docs/project_status.md)，本次检查结果见 [发布验证](artifacts/release-verification/README.md)。历史文件中的测试数量、费用与状态只代表其记录时点。

**代码与可上传范围**

| 文件夹 | 用途 | 上传标记 |
|---|---|---|
| `hpo/` | 搜索方法、交互估计、预算与控制器 | ✅ 上传 |
| `evaluation/` | 真实任务执行、计量、冻结、留出和报告 | ✅ 上传，属于开发中实现 |
| `pilot/`、`runtime/` | Pi／BenchFlow 集成、固定运行时和诊断入口 | ✅ 上传 |
| `configs/`、`schemas/` | 空间、任务元数据、配置及结果约束 | ✅ 上传；proposal／example 不等于授权 |
| `tests/`、`scripts/` | 测试、恢复来源、复现、导出工具 | ✅ 上传；历史对账脚本另需本地运行证据 |
| `docs/` | 设计、来源锁、协议、复现和研究材料 | 🟨 只上传整理后的副本 |
| `artifacts/` | 公开验证摘要和图 | 🟨 只上传 `release-verification/` |
| `runs/`、`logs/`、`third_party/`、`.venv*` | 原始运行、请求记录、下载源码和本机环境 | ⛔ 保留本地 |
| 课程原件、论文、团队工作记录 | 本地研究资料 | ⛔ 保留本地 |

本地生成的 **`github-upload/` 是独立上传副本**。将其中内容作为 GitHub 仓库根目录，保留代码目录名称；不要上传整个桌面工作目录。[中文上传说明与完整目录标注](GITHUB_UPLOAD.md)。

**运行无费用的 Mock 流程**

在项目根目录执行。已准备好的环境是 **macOS arm64／Python 3.12**；新机器先按 [复现说明](docs/reproduction.md) 创建环境并安装哈希锁定依赖。

```bash
.venv/bin/python -m pip check
env PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m hpo run --config configs/hpo_final_mock.json --output runs/my-mock-run
.venv/bin/python -m hpo audit --run runs/my-mock-run
```

Mock 不调用 Pi、Docker 或模型 API。每次输出使用新目录。测试自行准备临时目录；依赖上游源码、BenchFlow 或显式代理开关的测试会明确跳过，不把缺少环境判成已验证。配置合法性等本地测试仍正常执行。

需要检查官方 Pi schema 或准备真实运行时，先恢复锁定源码：

```bash
.venv/bin/python scripts/restore_sources.py
```

该脚本下载并核对固定提交，不安装或执行上游代码，也不覆盖已修改的副本。完整三种子 mock 复现入口：

```bash
.venv/bin/python scripts/reproduce_mock.py --output runs/my-three-seed-verification
```

**搜索空间与方法**

真实候选空间使用显式 `early_compaction_v2` profile：

| Pi 公开参数 | live-v2 候选值 | 原生默认 |
|---|---|---|
| `defaultThinkingLevel` | low、medium、high | medium |
| `compaction.reserveTokens` | 16384、360000、375000 | 16384 |
| `compaction.keepRecentTokens` | 4000、10000、20000 | 20000 |

共 27 点。reserve 决定自动压缩触发阈值；keepRecent 控制保留的近期原始上下文。运行记录中的模型窗口为 400k，正式运行前会重新核对。旧 [mock 空间](configs/hpo_space.json) 用于合成复现，取值与 [live-v2](configs/hpo_space.live-v2.json) 不同。

IGBS 用七个已计费的初始配置估计局部交互，再进行 pair／single／global 搜索。信息不足时回退到均匀选择；pair-blind 保留相同流程，只移除交互引导。SMAC 的随机森林也能表达交互。在已有 mock 中 IGBS 与 pair-blind 结果一致，不能解释成真实参数没有交互或 IGBS 已有优势。[算法设计及限制](docs/phase4_interaction_aware_hpo_design.md)。

**真实执行与实验边界**

`skillsbench_pi_v1` 保留任务原生依赖、Skills、资源、时限和官方 verifier，使用项目自有封装完成计量、进程取消与资源清理。模型固定为 OpenRouter `openai/gpt-5.4-mini`，上游提交见 [来源锁](docs/sources/source_lock.json)。

八任务校准有两项官方全通过；这些是工程校准观察，不是调优结果。后续 20 秒受控超时改变了原生作答时限，仅用于故障验收，不能加入正式成绩。原始自动结果与事后侧车对账各自保留，不把侧车通过称为完整自动流程已通过。

当前候选已按用户要求缩减为 **8 个验证任务、8 个独立留出任务，Random/BO/IGBS 各 10 配置，Default 单独测量，共 248 + 32 = 280 次尝试，暂拟 $82**。保留一轮完整 IGBS 自适应，暂不执行可选 pair-blind 消融。额度尚未批准，也不是供应商硬扣费上限。见 [当前协议 v7](docs/formal_protocol_20261028_v7/README.md)；原 504 次/$155 发布审阅快照保留为历史方案。

正式顺序是：确认协议与费用条件 → 验证集搜索 → 统一冻结赢家 → 独立留出 → 报告。缺失费用保持未知并停止比较。当前没有真实 held-out pass@1、泛化差距或完整 HPO 搜索成本。

**结果与研究材料**

- [公开证据摘要与 Mock 图](artifacts/release-verification/README.md)：区分合成结果、校准和受控诊断；原始运行记录保留本地。
- [研究报告草稿](docs/research_report_draft.md)、[展示提纲](docs/presentation_outline.md)、[Q&A](docs/qa.md)：正式结果仍待补齐。
- [复现说明](docs/reproduction.md)：干净目录测试、依赖来源、可选运行时验证与历史工具限制。
- [第三方来源及许可说明](THIRD_PARTY_NOTICES.md)：上游和论文不属于项目原创；项目自身开源许可尚未选择。

本次整理未执行 Git 初始化、commit、push 或发布。上传包带 `UPLOAD_MANIFEST.json`，记录文件清单、来源及导出哈希；未打包的本地证据链接会明确标注，保留真实实验尚未完成的状态。
