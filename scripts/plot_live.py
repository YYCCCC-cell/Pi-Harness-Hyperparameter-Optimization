"""Plot audited live-report data using ReportLab; preserve fixture labels."""
import argparse
import json
from pathlib import Path

from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String, Rect
from reportlab.graphics import renderSVG
from reportlab.lib.colors import HexColor

COLORS = {"default": "#737373", "random": "#E69F00", "bo": "#0072B2", "igbs": "#009E73", "pair_blind": "#CC79A7"}


def plot(report_path, output):
    report = json.loads((Path(report_path) / "results.json").read_text())
    if "cost_curves" not in report:
        raise ValueError("Expected audited live_report data")
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    fixture = report["verification_only"]
    curves = report["cost_curves"]["raw"]
    drawing = Drawing(800, 480)
    drawing.add(Rect(0, 0, 800, 480, fillColor=HexColor("#ffffff"), strokeColor=None))
    drawing.add(String(70, 451, "Incumbent validation performance versus accounted cost", fontName="Helvetica-Bold", fontSize=16))
    subtitle = "OFFLINE FIXTURES ONLY - NOT PI / SKILLSBENCH RESULTS" if fixture else "Recorded validation only; heldout outcomes never guide search"
    drawing.add(String(70, 429, subtitle, fontSize=11))
    chart = LinePlot(); chart.x, chart.y, chart.width, chart.height = 70, 115, 660, 275
    maximum = max((p["accounted_usd"] for rows in curves.values() for p in rows if p["accounted_usd"] is not None), default=1)
    chart.xValueAxis.valueMin = 0; chart.xValueAxis.valueMax = max(maximum * 1.02, 0.01)
    chart.yValueAxis.valueMin = 0; chart.yValueAxis.valueMax = 1
    chart.yValueAxis.valueSteps = [0, .2, .4, .6, .8, 1]
    chart.data, legends = [], []
    for method, rows in curves.items():
        points = [(p["accounted_usd"], p["incumbent_pass_rate"]) for p in rows
                  if p["accounted_usd"] is not None and p["incumbent_pass_rate"] is not None]
        if not points: continue
        if method == "default":
            points = [points[0], (maximum, points[0][1])]
        else:
            steps = [points[0]]
            for previous, current in zip(points, points[1:]): steps.extend([(current[0], previous[1]), current])
            points = steps
        index = len(chart.data); chart.data.append(points)
        color = HexColor(COLORS[method]); chart.lines[index].strokeColor = color
        chart.lines[index].strokeWidth = 2
        chart.lines[index].strokeDashArray = {"default": [6, 3], "random": [1, 2], "bo": None,
                                            "igbs": [2, 2], "pair_blind": [9, 3]}[method]
        legends.append((color, "Default reference" if method == "default" else method))
    if not chart.data:
        raise ValueError("No complete measured panels to plot")
    drawing.add(chart)
    drawing.add(String(70, 402, "Best-so-far validation pass fraction", fontSize=10))
    drawing.add(String(400, 76, "Fixture USD (not spent)" if fixture else "Cumulative accounted request USD (not an invoice)", textAnchor="middle", fontSize=11))
    legend = Legend(); legend.x, legend.y, legend.fontSize = 85, 51, 10
    legend.colorNamePairs, legend.columnMaximum, legend.deltax = legends, 1, 133
    drawing.add(legend)
    drawing.add(String(70, 24, "Steps update after complete panels; overlaps are retained. Default has no tuning budget.", fontSize=9))
    renderSVG.drawToFile(drawing, str(output / "incumbent-cost.svg"))
    return drawing


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True); parser.add_argument("--output", required=True)
    args = parser.parse_args(); plot(args.report, args.output)
