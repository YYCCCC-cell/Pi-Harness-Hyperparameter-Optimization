# 干净目录复现与验证

在下载后的仓库根目录执行。Mock 不需要 Docker、API key 或 `third_party/`。当前没有可复现的正式 HPO／留出结果，以下命令验证软件和合成流程。

**1．依赖环境**

当前锁经过验证的平台是 macOS arm64、Python 3.12。已有 `.venv` 时先运行 `.venv/bin/python -m pip check`。在相同平台的新机器上：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: \
  'setuptools==80.9.0' 'wheel==0.45.1'
.venv/bin/python -m pip install --index-url https://pypi.org/simple \
  --only-binary=:all: --no-binary=pynisher --no-build-isolation \
  --require-hashes -r requirements-hpo.lock
.venv/bin/python -m pip check
```

命令从 PyPI 下载依赖并构建锁定的 pynisher 源码包，不调用模型。来源和哈希见 [依赖来源锁](sources/hpo/source_lock.json)。本次在同一 macOS arm64 主机建立了全新虚拟环境，从历史已审阅且再次逐包核对哈希的 37 个 wheel 离线安装，未继承旧 site-packages。包含此前已审阅构建的 pynisher wheel；本次未重新下载或重新构建该源码包，不等同于另一台机器或跨平台验收。Linux、Windows、Intel macOS 或其他 Python 版本需单独验证，不能删除哈希强行安装。

**2．源码测试与合成流程**

```bash
env PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m hpo run --config configs/hpo_final_mock.json --output runs/my-mock-run
.venv/bin/python -m hpo audit --run runs/my-mock-run
```

测试自行创建 `runs/` 临时父目录。Pi 官方 schema 对照在未恢复上游源码时明确跳过，三个 thinking 档位与本地约束仍测试；BenchFlow 和代理测试也按依赖／开关跳过。每个运行使用新目录，不覆盖历史结果。

完整三种子复现：

```bash
.venv/bin/python scripts/reproduce_mock.py --output runs/my-three-seed-verification
```

该流程应生成 4,116 次合成尝试。Mock API 费用为零，synthetic score 不代表真实 SkillsBench 成绩。`scripts/plot_mock.py` 可生成 SVG；绘图另需 ReportLab 4.4.9，它不属于优化器或测试的必要依赖。

**3．可选的上游和运行时检查**

```bash
.venv/bin/python scripts/restore_sources.py
env PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -m unittest discover -s tests -v
```

恢复脚本只下载四个固定提交，不执行上游源码，不重置不同版本或有修改的仓库。真实运行另需 BenchFlow、Docker、固定 image 和凭据；见 [执行器说明](live_evaluator.md) 与 [运行时记录](phase2_reproduction.md)。旧运行路径是原工作区的历史证据，不会随上传包分发。

已有安装 BenchFlow 的独立 `.venv-runtime` 时，可运行本地模拟上游测试：

```bash
.venv-runtime/bin/python -m unittest discover -s tests -p test_live_runtime.py -v
RUN_LOCAL_PROXY_TESTS=1 .venv-runtime/bin/python -m unittest discover -s tests -p test_request_proxy_runtime.py -v
```

它们不产生供应商调用，也不能替代真实费用验收。

**4．发布审阅快照的纯离线检查**

以下命令使用本次 v8 工程发布快照（计划 280 次，继承 $60 分阶段额度）。不读取上传包之外的 raw runs，也不授予运行权限。旧 v5/v7/v8 运行协议保留历史身份；后续多人执行适配或代码变化须新建快照。

```bash
env PYTHONHASHSEED=0 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python scripts/verify_formal_protocol.py \
  --protocol docs/formal_protocol_release_v8_20261028/run_manifest.release.proposal.json \
  --output runs/my-release-protocol-check
```

检查器使用替换评估器，并禁止网络和子进程；验证预算／次数、冻结、留出和未知费用停止。源码哈希不一致时拒绝继续。运行它不授予正式实验额度。

**5．原工作区的历史工具**

`reconcile_*`、`export_openrouter_usage.py`、`build_completion_acceptance.py`、`review_*_budget.py` 等需要对应的本地 raw runs／receipts／logs。上传包不带这些原件；它们不是新目录 quick start 的必经步骤。公开摘要给出来源哈希和限制，不伪造缺失原件。
