#!/usr/bin/env python3
"""Plot LSV raw/iR curves from BioLogic txt files.

Usage:
    python lsv_plot.py --input-dir <data folder> --output-dir <output folder>
    python lsv_plot.py --input-dir <data folder> --config config.yaml

Behavior:
- groups files by parent folder and by raw / iR (filename starts with IR)
- one figure per group per kind; all repeats of that group are plotted
- x axis starts at config x_min (default 1.4 V), ends at the smallest
  maximum potential among the curves, rounded to 2 decimals
- figure filename: raw -> "<folder with spaces as hyphens>.png",
  iR -> "<folder with spaces as hyphens>-iR.png"
- legend labels: raw -> "<base>-1/-2/-3...", iR -> "<base>-iR-1/-2/-3..."
"""

import argparse
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator, FormatStrFormatter
import yaml

from lsv_analysis import clean_forward_sweep, group_kind, read_lsv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULTS = {
    "figure": {
        "dpi": 600,
        "font": "Arial",
        "figsize": [8.0, 6.0],
    },
    "curve": {
        "linewidth": 2.0,
        "marker": "none",
    },
    "axis": {
        "xlabel": "Potential (V vs. RHE)",
        "ylabel": "Current density (mA cm$^{-2}$)",
        "x_min": 1.4,
        "x_major_step": 0.1,
        "x_minor_step": 0.05,
    },
    "legend": {
        "loc": "upper left",
        "fontsize": 10,
    },
}


def load_config(path):
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
    else:
        cfg = {}
    merged = DEFAULTS
    for section, values in cfg.items():
        if isinstance(values, dict):
            merged[section] = {**DEFAULTS.get(section, {}), **values}
    return merged


def base_name(folder):
    return folder.replace(" ", "-")


def plot_group(group, kind, out_dir, cfg, area, x_min_override):
    base = base_name(group)
    if kind == "raw":
        out_name = base + ".png"
        label_prefix = base
    else:
        out_name = base + "-iR.png"
        label_prefix = base + "-iR"

    curves = []
    for path in sorted(group_paths[group][kind]):
        E, I, is_density = read_lsv(path)
        E2, I2 = clean_forward_sweep(E, I)
        if len(E2) < 3:
            print("警告：跳过非数据文件：%s" % path)
            continue
        j = I2 if is_density else [v / area for v in I2]
        curves.append((path, E2, j))

    if not curves:
        return None

    x_min = cfg["axis"]["x_min"]
    if x_min_override is not None:
        x_min = x_min_override

    max_each = [max(E) for _, E, _ in curves]
    x_max = min(max_each)
    if x_max <= x_min:
        print("警告：%s / %s 的最大电位 %s 不高于 x 起点 %s，跳过" % (group, kind, x_max, x_min))
        return None
    x_max = math.floor(x_max * 100.0 + 0.5) / 100.0

    y_max = 0.0
    for _, E, j in curves:
        for e, jv in zip(E, j):
            if x_min <= e <= x_max:
                y_max = max(y_max, jv)
    if y_max <= 0:
        print("警告：%s / %s 在 x 范围内无正电流，跳过" % (group, kind))
        return None

    fig, ax = plt.subplots(figsize=cfg["figure"]["figsize"], dpi=cfg["figure"]["dpi"])
    for idx, (path, E, j) in enumerate(curves, start=1):
        ax.plot(E, j, linewidth=cfg["curve"]["linewidth"], marker=cfg["curve"]["marker"],
                label="%s-%d" % (label_prefix, idx))

    ax.set_xlim(x_min, x_max)
    ax.set_ylim(0, y_max * 1.05)
    ax.set_xlabel(cfg["axis"]["xlabel"], fontsize=12, fontweight=cfg["axis"].get("fontweight", "normal"))
    ax.set_ylabel(cfg["axis"]["ylabel"], fontsize=12, fontweight=cfg["axis"].get("fontweight", "normal"))
    ax.xaxis.set_major_locator(MultipleLocator(cfg["axis"]["x_major_step"]))
    ax.xaxis.set_minor_locator(MultipleLocator(cfg["axis"]["x_minor_step"]))
    ax.xaxis.set_major_formatter(FormatStrFormatter("%.2f"))
    ax.legend(loc=cfg["legend"]["loc"], fontsize=cfg["legend"]["fontsize"],
              frameon=True, edgecolor="black")

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, out_name)
    fig.savefig(out_path, dpi=cfg["figure"]["dpi"], bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    return out_path


def main(argv=None):
    parser = argparse.ArgumentParser(description="LSV 自动绘图")
    parser.add_argument("files", nargs="*", help="LSV txt 文件（可选）")
    parser.add_argument("--input-dir", help="递归扫描目录下的 *.txt")
    parser.add_argument("--output-dir", default=os.path.join(SCRIPT_DIR, "output", "样品"), help="图片输出目录")
    parser.add_argument("--config", default=os.path.join(SCRIPT_DIR, "config.yaml"), help="配置文件路径")
    parser.add_argument("--area", type=float, default=1.0, help="电极面积 cm2（默认 1.0）")
    parser.add_argument("--x-min", type=float, default=None, help="x 轴起点（默认读 config）")
    args = parser.parse_args(argv)

    if args.input_dir:
        args.input_dir = os.path.abspath(args.input_dir)
    if args.output_dir:
        args.output_dir = os.path.abspath(args.output_dir)
    if args.config:
        args.config = os.path.abspath(args.config)

    paths = [os.path.abspath(p) for p in args.files]
    if args.input_dir:
        for root, _, names in os.walk(args.input_dir):
            for name in sorted(names):
                if name.lower().endswith(".txt"):
                    paths.append(os.path.join(root, name))
    if not paths:
        parser.error("没有输入文件")

    cfg = load_config(args.config)
    if "font" in cfg["figure"]:
        plt.rcParams["font.family"] = cfg["figure"]["font"]

    global group_paths
    group_paths = {}
    for p in paths:
        folder = os.path.basename(os.path.dirname(p))
        kind = group_kind(p)
        group_paths.setdefault(folder, {}).setdefault(kind, []).append(p)

    for group in sorted(group_paths):
        for kind in ("raw", "ir"):
            if kind not in group_paths[group]:
                continue
            out = plot_group(group, kind, args.output_dir, cfg, args.area, args.x_min)
            if out:
                print("已生成：%s" % out)


if __name__ == "__main__":
    main()