"""Replot the recorded synthetic values without a central watermark. No evaluations."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports/figures'

def main():
    result=json.loads((ROOT/'results/igbs-synthetic-20261030/run-output/results.json').read_text())
    assert result['evidence_kind']=='controlled_synthetic_not_benchmark'
    names=['Strong designed interaction', 'No interaction (flat)', 'Weak / uncertain interaction']
    values=[]
    for scenario in ['strong_interaction','flat_no_interaction','weak_uncertain_interaction']:
        guided=next(r for r in result['runs'] if r['scenario']==scenario and r['method']=='igbs')
        c=max(guided['rows'][7]['target_pair_contrasts'],key=lambda c:abs(c['delta']))
        values.append([abs(c['delta']),c['bootstrap_radius'],c['routing_weight'],0])
    OUT.mkdir(exist_ok=True)
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
    fig.subplots_adjust(left=.08, right=.98, bottom=.28, top=.81)
    fig.savefig(OUT / "mechanism-check-no-watermark.png", dpi=180)
    fig.savefig(OUT / "mechanism-check-no-watermark.pdf")
    plt.close(fig)

if __name__ == "__main__":
    main()
