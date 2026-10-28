# 复现与交接

2026-10-28。当前真实证据包括参数机制、跨任务默认校准和受控超时对账；正式 HPO 和留出结果尚未生成。代码与报告准备不等于最终作业已完成。

## 本机无模型费用检查

从项目根目录执行，每个输出路径必须未存在：

```bash
cd "<project-root>"
.venv/bin/python -m pip check
PYTHONHASHSEED=0 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -m unittest discover -s tests
PYTHONHASHSEED=0 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python scripts/verify_formal_protocol.py \
  --protocol docs/formal_protocol_20261028_v8/run_manifest.v8.approved.json \
  --output runs/new-protocol-fixtures
.venv/bin/python -m hpo preflight \
  --config docs/formal_protocol_20261028_v8/validation-config.approved.json \
  --output runs/new-live-preflight
```

前两项为软件检查；协议核验使用被替换的 evaluator、禁止网络/子进程，不执行 280 个真实任务。preflight 检查真实运行环境和任务计划，不构建任务、不调用模型。回归不需要 API 密钥；本地代理测试需单独显式开启 RUN_LOCAL_PROXY_TESTS。

## 新机器边界

1. Python 3.12；创建控制器虚拟环境，以 `pip install --require-hashes -r requirements-hpo.lock` 安装固定依赖。该锁针对已验证平台；其他平台需单独审阅，不能声称同一锁已跨平台验证。
2. `python scripts/restore_sources.py` 只下载锁定上游提交，拒绝覆盖不同版本/脏工作树；不执行下载的源码。mock 不需要付费模型。
3. 真实运行按 [Pi runtime 构建](phase2_reproduction.md) 和 [真实评测器说明](live_evaluator.md) 建立独立 runtime 环境、Docker 镜像及本机 review。当前配置的本地镜像 ID 和 runs 路径不能直接移植到他人机器。
4. 新运行时/依赖/模型元数据需生成新协议来源快照，不能修改文件后仍声称匹配旧协议哈希。公开的 source lock 是源码身份，不是可移植运行镜像。
5. API Key 仅放本机进程环境或隐藏输入，不写配置或提交。第三方源码、虚拟环境、原始轨迹、课程文档与论文不进入公开包。

## 正式运行顺序（$60 已获授权）

协议 v8 的 $60 额度已获授权；当前 key 可用额度不足，调整后重新核对凭据、用量和 preflight 再执行，不再请求同一预算批准。先一致地准备验证任务环境，记录 provisioning 开销；留出环境准备在赢家冻结后进行。每阶段都要求新目录、完整计量与清理，禁止删除 claim 重新跑分。

```bash
.venv/bin/python -m hpo run \
  --config docs/formal_protocol_20261028_v8/validation-config.approved.json \
  --output runs/formal-validation
.venv/bin/python -m hpo audit --run runs/formal-validation
.venv/bin/python -m evaluation.heldout freeze \
  --campaign runs/formal-validation --output runs/formal-freeze
.venv/bin/python -m evaluation.heldout prepare \
  --freeze runs/formal-freeze/frozen-selection.json \
  --output runs/formal-heldout-preflight --budget-usd 9
.venv/bin/python -m evaluation.heldout run \
  --freeze runs/formal-freeze/frozen-selection.json \
  --output runs/formal-heldout --budget-usd 9
.venv/bin/python -m evaluation.live_report \
  --campaign runs/formal-validation \
  --freeze runs/formal-freeze/frozen-selection.json \
  --heldout runs/formal-heldout --output artifacts/formal-report
```

上面是顺序说明，不是忽略上一阶段失败的批处理脚本。只有完整、计量有效的验证能冻结；未知费用或不完整比较停止，不擅自补题/换题/续费。真实报告使用固定留出分母；将来的曲线命令为 `scripts/plot_live.py --report artifacts/formal-report --output artifacts/formal-figures`，需文档列出的 ReportLab 环境。

## GitHub 交付

当前根目录尚未初始化 Git、提交或发布。用户自行负责 GitHub 上传；项目许可证尚未选择。使用已验证的 `github-upload/` 副本，提交源码、配置、schema、测试、脚本、当前报告/协议和明确标记的合成结果；原始真实轨迹只保留本地，公开诊断证据另按字段白名单审阅。

[报告](research_report_draft.md)、[作业映射](assignment_requirements_checklist.md)、[10 分钟展示提纲](presentation_outline.md)、[Q&A](qa.md) 已衔接当前证据。正式六类结果与最终结论必须由未来真实搜索/留出产生。

工程收尾与当前上传快照见 [检查记录](nonformal_closeout_20261028.md)。源码包无 raw runs 的协议核验应使用 [发布快照](formal_protocol_release_v8_20261028/README.md)，不要直接执行历史原件依赖检查。
