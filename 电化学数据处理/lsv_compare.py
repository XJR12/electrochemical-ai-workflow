#!/usr/bin/env python3
"""Comparison figures from the finalized selection (lsv_best.csv).

This script does NOT re-select curves. It reads the selected file per
group from lsv_best.csv (produced by lsv_analysis.py), then draws the
total and token-group comparison figures.

Usage:
    python lsv_compare.py --input-dir <data folder> --best-csv <output>/lsv_best.csv \
        --output-dir <output>/对比图 --config config.yaml
"""

import argparse
import csv
import math
import os
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import yaml

from lsv_analysis import clean_forward_sweep, group_kind, potential_at_current, read_lsv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

COMPARE_DEFAULTS = {
    "exclude_mv": 100.0,
    "majority_ratio": 0.5,
    "x_end_pad": 0.01,
    "manual_groups": [],
}


def load_config(path):
    cfg = {}
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
    compare = {**COMPARE_DEFAULTS, **(cfg.get("compare") or {})}
    return cfg, compare


def parse_all(paths, area, rhe, targets):
    parsed = {}
    for p in paths:
        E, I, is_density = read_lsv(p)
        E2, I2 = clean_forward_sweep(E, I)
        if len(E2) < 3:
            continue
        j = I2 if is_density else [v / area for v in I2]
        t = {x: potential_at_current(E2, j, x) for x in targets}
        parsed[(os.path.basename(os.path.dirname(p)), group_kind(p), os.path.basename(p))] = {
            "path": p,
            "folder": os.path.basename(os.path.dirname(p)),
            "kind": group_kind(p),
            "targets": t,
            "eta10": None if t[targets[0]] is None else (t[targets[0]] - rhe) * 1000.0,
            "eta100": None if t[targets[1]] is None else (t[targets[1]] - rhe) * 1000.0,
            "maxE": max(E2),
            "E": E2,
            "j": j,
        }
    return parsed


def read_selected(best_csv):
    """Return {(folder, kind): basename} from lsv_best.csv; reject manual rows."""
    selected = {}
    with open(best_csv, "r", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            folder = row["目录"]
            kind = {"直接测": "raw", "iR补偿": "ir"}.get(row["类别"])
            selection = row["选择方式"]
            if kind is None:
                continue
            if selection == "手动":
                raise ValueError("lsv_best.csv 仍有手动候选（%s / %s），请先完成人工选择" % (folder, row["类别"]))
            selected[(folder, kind)] = row["文件"]
    return selected


def exclude_bad(curves, exclude_mv):
    etas = sorted(c["eta10"] for c in curves if c["eta10"] is not None)
    if len(curves) <= 1 or not etas:
        return list(curves), []
    median = statistics.median(etas)
    keep = []
    excluded = []
    for c in curves:
        if c["eta10"] is not None and (c["eta10"] - median) > exclude_mv:
            excluded.append(c)
        else:
            keep.append(c)
    return keep, excluded


def decide_axis(curves, majority_ratio):
    if not curves:
        return "10", 1.4
    reached = sum(1 for c in curves if c["eta100"] is not None)
    mode = "100" if reached / len(curves) >= majority_ratio else "10"
    if mode == "100":
        pool = [c for c in curves if c["eta100"] is not None] or curves
        x_end = max(c["targets"][100.0] for c in pool) + 0.01
    else:
        x_end = min(c["maxE"] for c in curves)
    x_end = math.ceil(x_end * 100.0 - 1e-9) / 100.0
    return mode, x_end


def label_of(folder):
    return folder.replace(" ", "-")


def save_figure(curves, kind, out_name, out_dir, cfg, mode, x_end, notes):
    x_min = cfg.get("axis", {}).get("x_min", 1.4)
    y_max = 100.0 if mode == "100" else 10.0
    fig, ax = plt.subplots(figsize=cfg.get("figure", {}).get("figsize", [8.0, 6.0]),
                           dpi=cfg.get("figure", {}).get("dpi", 600))
    for c in curves:
        label = label_of(c["folder"]) + ("-iR" if kind == "ir" else "")
        ax.plot(c["E"], c["j"], linewidth=cfg.get("curve", {}).get("linewidth", 2.0),
                marker=cfg.get("curve", {}).get("marker", "none"), label=label)
    ax.set_xlim(x_min, x_end)
    ax.set_ylim(0, y_max)
    ax.set_xlabel(cfg.get("axis", {}).get("xlabel", "Potential (V vs. RHE)"), fontsize=12,
                  fontweight=cfg.get("axis", {}).get("fontweight", "normal"))
    ax.set_ylabel(cfg.get("axis", {}).get("ylabel", "Current density (mA·cm$^{-2}$)"), fontsize=12,
                  fontweight=cfg.get("axis", {}).get("fontweight", "normal"))
    ax.xaxis.set_major_locator(plt.MultipleLocator(0.05))
    ax.xaxis.set_minor_locator(plt.MultipleLocator(0.025))
    ax.xaxis.set_major_formatter(plt.FormatStrFormatter("%.2f"))
    ax.legend(loc=cfg.get("legend", {}).get("loc", "upper left"),
              fontsize=cfg.get("legend", {}).get("fontsize", 10),
              frameon=True, edgecolor="black")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, out_name)
    fig.savefig(out_path, dpi=cfg.get("figure", {}).get("dpi", 600),
                bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    notes.append("生成：%s（y轴0-%.0f，x轴%.2f-%.2f）" % (out_name, y_max, x_min, x_end))
    return out_path


def build_figure(entries, kind, out_name, out_dir, cfg, compare, notes):
    curves = [e for (_, k), e in entries.items() if k == kind]
    curves.sort(key=lambda c: c["folder"])
    if not curves:
        return None
    curves, excluded = exclude_bad(curves, compare["exclude_mv"])
    if excluded:
        notes.append("剔除（%s）：%s" % (kind, ", ".join(label_of(c["folder"]) for c in excluded)))
    if len(curves) < 2:
        notes.append("跳过：%s（剩余曲线不足 2 条）" % out_name)
        return None
    mode, x_end = decide_axis(curves, compare["majority_ratio"])
    return save_figure(curves, kind, out_name, out_dir, cfg, mode, x_end, notes)


def main(argv=None):
    parser = argparse.ArgumentParser(description="LSV 对比图（基于选择后数据）")
    parser.add_argument("--input-dir", required=True, help="数据目录（递归扫描 *.txt）")
    parser.add_argument("--best-csv", required=True, help="lsv_best.csv（选择后数据）")
    parser.add_argument("--output-dir", default=os.path.join(SCRIPT_DIR, "output", "对比图"))
    parser.add_argument("--config", default=os.path.join(SCRIPT_DIR, "config.yaml"))
    parser.add_argument("--area", type=float, default=None, help="电极面积 cm2，默认读 config.yaml 的 area")
    parser.add_argument("--rhe", type=float, default=1.23)
    parser.add_argument("--targets", nargs="+", type=float, default=[10.0, 100.0])
    parser.add_argument("--exclude-mv", type=float, default=None)
    parser.add_argument("--majority-ratio", type=float, default=None)
    args = parser.parse_args(argv)

    args.input_dir = os.path.abspath(args.input_dir)
    args.output_dir = os.path.abspath(args.output_dir)
    args.config = os.path.abspath(args.config)
    args.best_csv = os.path.abspath(args.best_csv)

    cfg, compare = load_config(args.config)
    if args.area is None:
        args.area = float(cfg.get("area", 1.0))
    if args.exclude_mv is not None:
        compare["exclude_mv"] = args.exclude_mv
    if args.majority_ratio is not None:
        compare["majority_ratio"] = args.majority_ratio
    if "font" in cfg.get("figure", {}):
        plt.rcParams["font.family"] = cfg["figure"]["font"]

    paths = []
    for root, _, names in os.walk(args.input_dir):
        for name in sorted(names):
            if name.lower().endswith(".txt"):
                paths.append(os.path.join(root, name))
    parsed = parse_all(paths, args.area, args.rhe, args.targets)
    selected = read_selected(args.best_csv)

    entries = {}
    for key, basename in selected.items():
        lookup = (key[0], key[1], basename)
        if lookup not in parsed:
            print("警告：找不到选择的数据 %s / %s / %s" % (key[0], key[1], basename))
            continue
        entries[key] = parsed[lookup]

    notes = []
    out_dir = args.output_dir
    build_figure(entries, "raw", "LSV.png", out_dir, cfg, compare, notes)
    build_figure(entries, "ir", "IR.png", out_dir, cfg, compare, notes)

    all_folders = sorted(set(f for f, _ in entries))
    tokens = {}
    for f in all_folders:
        for tok in f.replace("-", " ").split():
            tokens.setdefault(tok, set()).add(f)
    for kind in ("raw", "ir"):
        kind_folders = sorted(set(f for (f, k) in entries if k == kind))
        for tok in sorted(tokens):
            members = [f for f in tokens[tok] if f in kind_folders]
            if len(members) < 2 or len(members) == len(kind_folders):
                continue
            subset = {key: e for key, e in entries.items() if key[0] in members and key[1] == kind}
            name = "对比-%s.png" % tok if kind == "raw" else "对比-%s-iR.png" % tok
            build_figure(subset, kind, name, out_dir, cfg, compare, notes)

    for g in compare.get("manual_groups") or []:
        gname = g.get("name", "manual")
        folders = g.get("folders", [])
        for kind, suffix in (("raw", ".png"), ("ir", "-iR.png")):
            members = [f for f in folders if (f, kind) in entries]
            if len(members) < 2:
                continue
            subset = {key: e for key, e in entries.items() if key[0] in members and key[1] == kind}
            name = "对比-%s%s" % (gname, suffix)
            build_figure(subset, kind, name, out_dir, cfg, compare, notes)

    note_path = os.path.join(out_dir, "选择说明.txt")
    os.makedirs(out_dir, exist_ok=True)
    with open(note_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(notes) + "\n")
    for line in notes:
        print(line)
    print("说明已写入：%s" % note_path)


if __name__ == "__main__":
    main()
