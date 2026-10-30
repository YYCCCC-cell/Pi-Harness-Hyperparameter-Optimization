"""Render only the already executed controlled synthetic experiment."""
import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "run-output"


def main():
    result = json.loads((OUT / "results.json").read_text())
    assert result["status"] == "passed" and result["evidence_kind"] == "controlled_synthetic_not_benchmark"
    assert result["model_calls"] == 0
    scenarios = ["strong_interaction", "flat_no_interaction", "weak_uncertain_interaction"]
    names = ["Strong designed interaction", "No interaction (flat)", "Weak / uncertain interaction"]
    values, table = [], []
    for scenario in scenarios:
        guided = next(r for r in result["runs"] if r["scenario"] == scenario and r["method"] == "igbs")
        blind = next(r for r in result["runs"] if r["scenario"] == scenario and r["method"] == "igbs_pair_blind")
        g, b = guided["rows"][7], blind["rows"][7]
        candidates = g["target_pair_contrasts"]
        c = max(candidates, key=lambda c: abs(c["delta"]))
        values.append([abs(c["delta"]), c["bootstrap_radius"], c["routing_weight"], 0])
        table.append({"scenario": scenario, "absolute_contrast": abs(c["delta"]),
            "bootstrap_radius": c["bootstrap_radius"], "leave_one_group_stability": c["leave_one_group_stability"],
            "igbs_routing_weight": c["routing_weight"], "pair_blind_applied_weight": 0,
            "igbs_reason": g["routing_reason"], "pair_blind_reason": b["routing_reason"],
            "igbs_selected_block": g["selected_block"], "pair_blind_selected_block": b["selected_block"],
            "evidence_kind": "controlled_synthetic_not_benchmark"})
    (OUT / "first-adaptive-decision.json").write_text(json.dumps(table, ensure_ascii=False, indent=2) + "\n")
    with (OUT / "first-adaptive-decision.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    fig, ax = plt.subplots(figsize=(10.8, 6.5))
    colors = ["#364152", "#9aa4b2", "#c85b24", "#00856a"]
    labels = ["Absolute known contrast", "Bootstrap deviation radius", "IGBS pair weight", "Pair-blind applied pair weight"]
    xs = np.arange(3)
    width = .18
    for j in range(4):
        x = xs + (j - 1.5) * width
        heights = [v[j] for v in values]
        bars = ax.bar(x, heights, width, color=colors[j], label=labels[j])
        for bar, value in zip(bars, heights):
            ax.text(bar.get_x()+bar.get_width()/2, value + .015, f"{value:g}", ha="center", va="bottom", fontsize=10)
    ax.set_xticks(xs, names)
    ax.set_ylim(0, 1.16)
    ax.set_ylabel("Synthetic contrast / routing weight (unitless)")
    ax.grid(axis="y", alpha=.18)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="upper center", bbox_to_anchor=(.5, -.13), ncol=2, frameon=False, fontsize=10)
    fig.suptitle("SYNTHETIC MECHANISM CHECK — NOT BENCHMARK RESULTS", fontsize=15,
                 fontweight="bold", x=.07, ha="left", y=.97)
    ax.set_title("First adaptive proposal (step 8), after seven complete screening panels", loc="left", fontsize=12, pad=17)
    fig.text(.07, .055,
        "Eight artificial task groups; seed 31; original algorithm thresholds unchanged.\n"
        "Strong signal: guided routing. Flat / weak signals: uniform fallback. Pair-blind removes pair weighting.\n"
        "Designed known-answer checks only; these bars do not measure real-task success or optimizer superiority.", fontsize=9, color="#454545")
    fig.text(.5, .47, "SYNTHETIC DATA", ha="center", fontsize=47, rotation=17, color="#a51d2d", alpha=.10)
    fig.subplots_adjust(left=.08, right=.98, bottom=.28, top=.81)
    fig.savefig(OUT / "mechanism-check.png", dpi=180)
    fig.savefig(OUT / "mechanism-check.pdf")
    plt.close(fig)

    rows = []
    for label, row in zip(["强交互", "无交互", "弱不确定交互"], table):
        rows.append(f"| {label} | {row['absolute_contrast']:.2f} | {row['bootstrap_radius']:.2f} | {row['igbs_routing_weight']:.2f} | {row['pair_blind_applied_weight']:.2f} | `{row['igbs_reason']}` |")
    target = result["runs"][0]["target_pair"]
    report = f'''# IGBS 十分钟简版：受控合成机制验证

**状态：已执行并通过。数据类型：合成。真实模型调用：0；付费 API 费用：$0。**

本记录验证实际 IGBS 代码的自适应决策行为，不属于 SkillsBench 真实效果实验，也不证明 IGBS 优于 BO、Random 或 pair-blind。原真实实验和已经交付的补充 ZIP 均保持原样。

## 实验规模与方法

运行 3 个预声明场景 × IGBS / pair-blind 两个方法 × 每方法 10 个配置 × 8 个人工任务组，共 **60 个完整配置面板、480 次合成任务评估**。种子固定为 31，使用当前三参数 27 配置空间（low/medium/high；reserve 16384/360000/375000；recent 4000/10000/20000）。

所有六条运行路径均完成 **7 次 screen → 第 8 次 pair → 第 9 次 single → 第 10 次 global**，每条路径配置不重复，ask/tell 日志哈希链与完成状态均通过核验。两方法的前七个初始化配置相同，分别保留自己的观测。

算法运行实测耗时 **{result['offline_wall_time_seconds']:.3f} 秒**，包括导入、合成计算、日志和源码核查；单独的绘图与打包耗时未计入。运行器禁止网络连接和子进程调用，未构造真实 evaluator。运行前后核对的 **{result['protected_source_files_unchanged']} 个受保护源文件均未变化**。

## 合成目标如何构造

目标参数对是 `defaultThinkingLevel × compaction.reserveTokens`。根据固定种子的初始化设计，目标替代取值为 `{json.dumps(target, ensure_ascii=False)}`。

- 强交互：只有该参数对同时达到目标替代取值，八个人工组才都返回成功。
- 无交互：所有配置、所有人工组均返回失败，形成平坦目标。
- 弱不确定交互：同一参数对达到目标时，只有第 0、1 两个人工组返回成功。

信号位置被**有意对齐初始化设计**，用于构造答案已知的机制检查。八个人工组不能视为八份独立真实实验证据；bootstrap 与稳定性数值只是算法对该合成输入的计算结果，不能解释为真实效果的统计置信度。所有 cost/time 破平分输入固定为零，实际离线耗时另记。

## 第一次自适应决策的实测输出

| 场景 | 绝对交互 contrast | Bootstrap 半径 | IGBS 交互权重 | pair-blind 生效权重 | IGBS 路由 |
|---|---:|---:|---:|---:|---|
{chr(10).join(rows)}

强交互场景中，IGBS 选中了注入信号的参数对，使用 `positive_stable_weight`；pair-blind 将参数对权重屏蔽后使用 `pair_blind_uniform`。无交互和弱不确定交互场景中，IGBS 的参数对权重均为零，两方法的十配置轨迹一致，符合均匀回退规则。门槛保持原值：8 组、实用阈值 0.05、稳定性阈值 0.8、bootstrap 2000 次。

![Synthetic mechanism check](run-output/mechanism-check.png)

## 可以写入报告的结论

> 我们在三个受控合成场景上验证了 IGBS 的实现：算法完成七点初始化后进入 pair/single/global 自适应决策；对强而稳定的已知交互使用加权参数对选择；在无交互或不确定信号下回退到均匀选择。配对消融验证了 pair-blind 能移除交互权重。该实验提供机制实现正确性的证据，不提供真实任务上的性能优势证据。

英文版本：

> We executed a controlled synthetic validation of the unchanged IGBS implementation using three designed objectives, eight artificial task groups, and a matched pair-blind ablation. All six runs completed seven screening panels followed by pair, single, and global proposals (60 configuration panels and 480 synthetic evaluations in total). In the strong-interaction case, IGBS selected the injected parameter pair with a routing weight of 0.95, whereas the ablation used uniform pair selection. Flat and weak-signal cases produced zero pair weights and the expected uniform fallback. These known-answer checks validate routing behavior and the ablation implementation; they do not establish performance gains on real SkillsBench tasks or superiority over another optimizer.

## 复核文件与复现

- `run-output/protocol.json`：在评估前写入的场景规则、种子、参数空间与源码哈希。
- `run-output/results.json`：完整结果与断言核验。
- `run-output/rounds.csv`：全部 60 轮配置、合成分数和路由。
- `run-output/<scenario>/<method>/optimizer-trace.jsonl`：完整 contrast、稳定性、权重、ask/tell 与哈希链。
- `run-output/first-adaptive-decision.csv`：上表的机器可读数据。
- `run-output/mechanism-check.png` / `.pdf`：已标注合成数据的图表。

在原项目中，用 `.venv/bin/python experiments/igbs-synthetic-demo-20261030/run_demo.py` 可运行。已有 `run-output` 时脚本拒绝覆盖；复现请仅复制 `run_demo.py` 和 `render_report.py` 到新的同级目录（不复制 `run-output`），再运行新副本。它依赖同项目的 `hpo/` 和 `experiments/igbs-validation-20261030/optimizers.py`，不是独立安装的 benchmark runtime。绘图使用已有的 Python 3.14 / matplotlib 运行 `render_report.py`，无需安装或付费模型。
'''
    (HERE / "RESULTS.md").write_text(report)
    (OUT / "render-manifest.json").write_text(json.dumps({
        "evidence_kind": "controlled_synthetic_not_benchmark",
        "results_sha256": hashlib.sha256((OUT / "results.json").read_bytes()).hexdigest(),
        "renderer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "figure": "mechanism-check.png", "visual_inspection": "pending"}, indent=2) + "\n")
    print(json.dumps(table, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
