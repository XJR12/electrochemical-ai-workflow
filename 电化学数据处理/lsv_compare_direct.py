#!/usr/bin/env python3
"""Direct LSV comparison figures: plot every txt, grouped by top-level folder.

This is the "no selection" comparison entry.  It is useful when the data do
not follow the OER/RHE assumptions of the selection workflow (for example
HER data, Hg/HgO potentials, or a folder of Pt/Ni curves).

Layout rules (relative to --input-dir):

    1213/HER/Ni/Ni.txt      -> group HER, sample Ni
    1213/OER/Pt/Pt.txt      -> group OER, sample Pt
    260812/Ru-1mg/1-LSV.txt -> group 260812, sample Ru-1mg
    flat/Pt.txt             -> group <input folder name>, sample Pt

One figure is written per group, named after the group (OER.png, HER.png).
Colors are fixed per sample: Pt blue, Ni red; other samples use a fallback
palette or the optional ``series`` section in config.yaml.
"""

import argparse
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FormatStrFormatter, MaxNLocator

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from lsv_analysis import clean_forward_sweep, read_lsv
from lsv_plot import load_config
from output_utils import next_output_dir

BUILTIN_ORDER = ["Pt", "Ni"]
BUILTIN_COLORS = {"Pt": "#1f77b4", "Ni": "#d62728"}
FALLBACK_COLORS = [
    "#1f77b4", "#d62728", "#2ca02c", "#ff7f0e",
    "#9467bd", "#8c564b", "#e377c2", "#7f7f7f",
]


def classify(path, root):
    """Return (group, sample) for one file inside root."""
    rel = os.path.relpath(path, root)
    parts = rel.split(os.sep)
    if len(parts) >= 3:
        return parts[0], parts[1]
    if len(parts) == 2:
        return os.path.basename(root), parts[0]
    return os.path.basename(root), os.path.splitext(parts[0])[0]


def load_curve(path, shift, area, y_unit, abs_current):
    E, I, is_density = read_lsv(path)
    E2, I2 = clean_forward_sweep(E, I, e_min=None)
    if len(E2) < 3:
        return None

    E2 = [e + shift for e in E2]
    if y_unit == "density":
        j = list(I2) if is_density else [v / area for v in I2]
    else:
        j = list(I2)
        if is_density:
            print("警告：该文件本身是电流密度，无法还原成 mA：%s" % path)
    if abs_current:
        j = [abs(v) for v in j]

    return {
        "path": path,
        "E": E2,
        "j": j,
        "sample": None,
        "label": None,
    }


def resolve_color(sample, index, cfg):
    series = (cfg or {}).get("series") or {}
    order = [str(x) for x in (series.get("order") or [])]
    colors = {str(k): str(v) for k, v in (series.get("colors") or {}).items()}
    if sample in colors:
        return colors[sample]
    for key in order:
        if key and key in sample and key in colors:
            return colors[key]
    if sample in BUILTIN_COLORS:
        return BUILTIN_COLORS[sample]
    return FALLBACK_COLORS[index % len(FALLBACK_COLORS)]


def sort_curves(curves, cfg):
    series = (cfg or {}).get("series") or {}
    order = [str(x) for x in (series.get("order") or [])] or BUILTIN_ORDER

    def key(c):
        sample = c["sample"]
        if sample in order:
            return (0, order.index(sample), sample)
        return (1, 0, sample)

    return sorted(curves, key=key)


def safe_name(text):
    return text.replace(" ", "-").replace("/", "-").replace("\\", "-")


def plot_group(group, curves, out_dir, cfg, y_unit, abs_current, notes):
    fig, ax = plt.subplots(figsize=cfg["figure"]["figsize"],
                           dpi=cfg["figure"]["dpi"])
    for idx, c in enumerate(curves):
        ax.plot(
            c["E"], c["j"],
            linewidth=cfg["curve"]["linewidth"],
            marker=cfg["curve"]["marker"],
            label=c["label"],
            color=resolve_color(c["sample"], idx, cfg),
        )

    xs = [x for c in curves for x in c["E"]]
    ys = [y for c in curves for y in c["j"]]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    x_pad = max((xmax - xmin) * 0.02, 0.01)
    ax.set_xlim(xmin - x_pad, xmax + x_pad)
    if ymax > 0:
        ax.set_ylim(min(0.0, ymin * 1.05), ymax * 1.05)
    else:
        ax.set_ylim(ymin * 1.05, 0.0)

    xlabel = cfg.get("axis", {}).get("xlabel", "Potential (V vs. RHE)")
    if y_unit == "density":
        ylabel = cfg.get("axis", {}).get("ylabel",
                                         "Current density (mA cm$^{-2}$)")
    else:
        ylabel = "Current (mA)"
    ax.set_xlabel(xlabel, fontsize=12,
                  fontweight=cfg.get("axis", {}).get("fontweight", "normal"))
    ax.set_ylabel(ylabel, fontsize=12,
                  fontweight=cfg.get("axis", {}).get("fontweight", "normal"))
    ax.xaxis.set_major_locator(MaxNLocator(nbins=6))
    ax.xaxis.set_major_formatter(FormatStrFormatter("%.2f"))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6))
    ax.yaxis.set_major_formatter(FormatStrFormatter("%.0f"))
    ax.legend(loc="best", fontsize=cfg.get("legend", {}).get("fontsize", 10),
              frameon=False)

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, safe_name(group) + ".png")
    fig.savefig(out_path, dpi=cfg["figure"]["dpi"], bbox_inches="tight",
                pad_inches=0.02)
    plt.close(fig)
    notes.append("生成：%s（%d 条曲线）" % (out_path, len(curves)))
    return out_path


def main(argv=None):
    parser = argparse.ArgumentParser(description="LSV 直接对比图（不选线）")
    parser.add_argument("--input-dir", required=True, help="数据目录（递归扫描 *.txt）")
    parser.add_argument("--output-dir", default=None,
                        help="输出目录；不填时新建 output/<输入目录名>_<序号>/对比图")
    parser.add_argument("--config", default=os.path.join(SCRIPT_DIR, "config.yaml"))
    parser.add_argument("--area", type=float, default=None, help="电极面积 cm2")
    parser.add_argument("--erhe-shift", type=float, default=0.0,
                        help="E_RHE = E + shift；Hg/HgO + 1 M KOH 时用 0.924 V")
    parser.add_argument("--y-unit", choices=["density", "mA"], default="density",
                        help="纵轴：density=电流密度；mA=原始电流（默认 density）")
    parser.add_argument("--abs-current", action=argparse.BooleanOptionalAction,
                        default=True, help="电流取绝对值（默认取）")
    args = parser.parse_args(argv)

    input_dir = os.path.abspath(args.input_dir)
    config_path = os.path.abspath(args.config)
    cfg = load_config(config_path)
    if args.area is None:
        args.area = float(cfg.get("area", 1.0))
    if not args.output_dir:
        base = os.path.join(SCRIPT_DIR, "output",
                            os.path.basename(input_dir.rstrip("\\/")))
        args.output_dir = os.path.join(next_output_dir(base), "对比图")
    args.output_dir = os.path.abspath(args.output_dir)
    plt.rcParams["font.family"] = [
        cfg["figure"].get("font", "Arial"),
        "Microsoft YaHei",
        "DejaVu Sans",
    ]

    paths = []
    for root, _, names in os.walk(input_dir):
        for name in sorted(names):
            if name.lower().endswith(".txt"):
                paths.append(os.path.join(root, name))
    if not paths:
        print("没有找到 txt 文件：%s" % input_dir)
        return 1

    groups = {}
    for path in paths:
        group, sample = classify(path, input_dir)
        c = load_curve(path, args.erhe_shift, args.area, args.y_unit,
                       args.abs_current)
        if c is None:
            print("警告：没有解析到 LSV 数据点，跳过：%s" % path)
            continue
        c["sample"] = sample
        groups.setdefault(group, []).append(c)

    if not groups:
        print("没有可用的 LSV 曲线。")
        return 1

    notes = []
    made = 0
    for group in sorted(groups):
        curves = sort_curves(groups[group], cfg)
        counts = {}
        for c in curves:
            counts[c["sample"]] = counts.get(c["sample"], 0) + 1
        for c in curves:
            if counts[c["sample"]] > 1:
                c["label"] = "%s-%s" % (
                    c["sample"],
                    os.path.splitext(os.path.basename(c["path"]))[0],
                )
            else:
                c["label"] = c["sample"]
        out = plot_group(group, curves, args.output_dir, cfg, args.y_unit,
                         args.abs_current, notes)
        print("已生成：%s" % out)
        made += 1

    note_path = os.path.join(args.output_dir, "选择说明.txt")
    with open(note_path, "w", encoding="utf-8") as fh:
        fh.write("数据目录：%s\n" % input_dir)
        fh.write("电位换算：E_RHE = E + %.3f V\n" % args.erhe_shift)
        fh.write("电极面积：%.3f cm2\n" % args.area)
        fh.write("纵轴：%s；电流取绝对值：%s\n"
                 % ("电流密度" if args.y_unit == "density" else "原始电流",
                    "是" if args.abs_current else "否"))
        fh.write("分组：每个顶层子文件夹一张图；样品名为其下一级文件夹。\n")
        fh.write("\n".join(notes) + "\n")
    print("说明已写入：%s" % note_path)
    return 0 if made else 1


if __name__ == "__main__":
    sys.exit(main())
