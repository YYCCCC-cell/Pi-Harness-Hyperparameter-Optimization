"""Export audited mock curves with ReportLab 4.4.9; never access benchmark tasks."""

import argparse
import json
from pathlib import Path

from reportlab.graphics.shapes import Drawing, String
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics import renderSVG
from reportlab.lib.colors import HexColor

COLORS = {"default": "#737373", "random": "#E69F00", "bo": "#0072B2", "igbs": "#009E73", "pair_blind": "#CC79A7"}


def plot(rows, seed, metric, title, label, output):
    order = ["default", "random", "bo", "pair_blind", "igbs"]
    rows = sorted((r for r in rows if r["seed"] == seed), key=lambda r: order.index(r["method"]))
    drawing = Drawing(750, 450)
    drawing.add(String(62, 424, title, fontName="Helvetica-Bold", fontSize=15))
    drawing.add(String(62, 403, f"DETERMINISTIC MOCK ONLY  |  Search seed {seed}  |  No Pi/model execution", fontSize=10))
    chart = LinePlot()
    chart.x, chart.y, chart.width, chart.height = 70, 90, 625, 285
    chart.yValueAxis.valueMin, chart.yValueAxis.valueMax = 0, 1
    chart.yValueAxis.valueSteps = [0, .2, .4, .6, .8, 1]
    chart.xValueAxis.valueMin = 0
    maximum = max((p[metric] for r in rows for p in r["curve"] if p[metric] is not None), default=0)
    chart.xValueAxis.valueMax = maximum * 1.05 if maximum else .01
    chart.data, legend = [], []
    for row in rows:
        points = [(p[metric], p["incumbent_pass_rate"]) for p in row["curve"]
                  if p[metric] is not None and p["incumbent_pass_rate"] is not None]
        if not points:
            continue
        if row["method"] == "default":
            points = [(0, row["default_reference"]), (chart.xValueAxis.valueMax, row["default_reference"])]
        else:
            step = [points[0]]
            for previous, current in zip(points, points[1:]):
                step.extend([(current[0], previous[1]), current])
            points = step
        index = len(chart.data)
        chart.data.append(points)
        color = HexColor(COLORS[row["method"]])
        chart.lines[index].strokeColor = color
        chart.lines[index].strokeWidth = 2
        chart.lines[index].strokeDashArray = {"default": [6, 3], "random": [1, 2],
                                              "bo": None, "pair_blind": [9, 3], "igbs": [2, 2]}[row["method"]]
        legend.append((color, "Default reference" if row["method"] == "default" else row["method"]))
    drawing.add(chart)
    drawing.add(String(320, 48, label, fontSize=11, textAnchor="middle"))
    drawing.add(String(70, 383, "Best-so-far validation pass fraction (synthetic)", fontSize=10))
    key = Legend()
    key.x, key.y, key.fontSize = 100, 28, 9
    key.colorNamePairs, key.columnMaximum, key.dx = legend, 1, 8
    key.deltax, key.alignment = 130, "right"
    drawing.add(key)
    by_method = {r["method"]: r["curve"] for r in rows}
    note = ("IGBS and pair-blind coincide in this recorded mock run; overlapping curves are retained."
            if "igbs" in by_method and by_method["igbs"] == by_method.get("pair_blind") else
            "Step curves update only after complete validation panels; overlapping curves are retained.")
    drawing.add(String(100, 9, note, fontSize=8))
    if maximum == 0:
        drawing.add(String(205, 230, "All observations cost $0 API USD.", fontName="Helvetica-Bold", fontSize=14))
        drawing.add(String(205, 210, "No dollar-efficiency comparison can be inferred.", fontSize=11))
    renderSVG.drawToFile(drawing, str(output.with_suffix(".svg")))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    rows = json.loads((Path(args.report) / "chart_data.json").read_text())
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    for seed in sorted({r["seed"] for r in rows}):
        for metric, title, label in (
            ("simulated_cost_units", "Search progress versus simulated cost", "Cumulative simulated cost units (not USD)"),
            ("attempts", "Search progress versus charged attempts", "Cumulative charged validation attempts"),
            ("accounted_usd", "Recorded API cost: zero throughout mock verification", "Cumulative accounted API USD")):
            plot(rows, seed, metric, title, label, output / f"{seed}-{metric}")
    print(f"Mock-only SVG plots written to {output}")
