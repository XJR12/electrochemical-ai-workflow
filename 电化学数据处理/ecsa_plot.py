#!/usr/bin/env python3
"""Plot and analyse ECSA/Cdl data from selected CV files only.

This module intentionally reads only the intermediate `selected_cv` files so
the plotting / fitting stage never re-reads raw instrument data. It mirrors
the matplotlib style used by lsv_plot.py / tafel_plot.py (600 dpi, Arial,
axis labels, black-framed legend).

Usage:
    python ecsa_plot.py --selected-dir <out>/ecsa/selected_cv \
        --output-dir <out>/ecsa --config config.yaml
"""

import argparse
import csv
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator, FormatStrFormatter, MultipleLocator
import numpy as np
import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

ECSA_DEFAULTS = {
    "center_potential": None,
    "cs_uf_cm2": None,
    "cv": {
        "xlabel": "Potential (V vs. RHE)",
        "ylabel": "Current density (mA cm$^{-2}$)",
        "x_major_step": 0.05,
        "x_minor_step": 0.025,
        "fontweight": "bold",
        "x_format": "%.3f",
    },
    "fit": {
        "xlabel": "$v$ / (mV s$^{-1}$)",
        "ylabel": "$\\Delta j$ (mA cm$^{-2}$)",
        "fontweight": "bold",
        "x_format": "%.0f",
        "y_format": "%.3f",
    },
}

SELECTED_HEADER = [
    "样品",
    "扫速/(mV/s)",
    "文件",
    "圈号",
    "支路",
    "序号",
    "E/V",
    "j/(mA cm-2)",
]

DELTA_HEADER = [
    "样品",
    "中心电位/(V vs. RHE)",
    "扫速/(mV/s)",
    "j升支/(mA cm-2)",
    "j降支/(mA cm-2)",
    "Δj/(mA cm-2)",
]

RESULT_HEADER = [
    "样品",
    "中心电位/(V vs. RHE)",
    "扫速数",
    "斜率",
    "截距/(mA cm-2)",
    "R²",
    "Cdl/(mF cm-2)",
    "Cdl/(µF cm-2)",
]


def deep_merge(base, override):
    merged = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path):
    cfg = {}
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
    ecsa = deep_merge(ECSA_DEFAULTS, cfg.get("ecsa") or {})
    return cfg, ecsa


def sanitize_name(name):
    return name.replace(" ", "-")


def read_selected_csv(path):
    """Read one selected_cv csv into an ordered data structure."""
    sample = os.path.splitext(os.path.basename(path))[0]
    rates = {}
    with open(path, "r", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                rate = float(row["扫速/(mV/s)"])
                e = float(row["E/V"])
                j = float(row["j/(mA cm-2)"])
                order = int(float(row["序号"]))
                branch = row["支路"]
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("%s 列格式不正确：%s" % (os.path.basename(path), exc))
            entry = rates.setdefault(rate, {
                "file": row.get("文件", ""),
                "cycle": row.get("圈号", ""),
                "order": [],
                "E_all": [],
                "j_all": [],
                "up_E": [],
                "up_j": [],
                "down_E": [],
                "down_j": [],
            })
            entry["order"].append(order)
            entry["E_all"].append(e)
            entry["j_all"].append(j)
            if branch == "升支":
                entry["up_E"].append(e)
                entry["up_j"].append(j)
            elif branch == "降支":
                entry["down_E"].append(e)
                entry["down_j"].append(j)
    return sample, rates


def collect_selected(selected_dir):
    if not os.path.isdir(selected_dir):
        raise ValueError("selected 目录不存在：%s" % selected_dir)
    paths = sorted(
        os.path.join(selected_dir, name)
        for name in os.listdir(selected_dir)
        if name.lower().endswith(".csv")
    )
    if not paths:
        raise ValueError("selected 目录里没有 CSV：%s" % selected_dir)
    data = {}
    for path in paths:
        sample, rates = read_selected_csv(path)
        if not rates:
            continue
        data[sample] = rates
    return data


def _sort_branch(e_list, j_list):
    if not e_list:
        return None
    e = np.asarray(e_list, dtype=float)
    j = np.asarray(j_list, dtype=float)
    order = np.argsort(e)
    return e[order], j[order]


def interp_at(e_list, j_list, x):
    pair = _sort_branch(e_list, j_list)
    if pair is None:
        return None
    e, j = pair
    if x < float(np.min(e)) - 1e-9 or x > float(np.max(e)) + 1e-9:
        return None
    return float(np.interp(x, e, j))


def parse_center_overrides(values, ecsa_cfg):
    overrides = {}
    global_value = ecsa_cfg.get("center_potential")
    if global_value is not None:
        global_value = float(global_value)
    for item in values or []:
        item = item.strip()
        if "=" in item:
            sample, value = item.split("=", 1)
            overrides[sample.strip()] = float(value.strip())
        else:
            global_value = float(item)
    return global_value, overrides


def find_auto_center(rates):
    """Choose the potential with the smallest average mid-branch current."""
    rate_list = sorted(rates)
    lows = []
    highs = []
    for rate in rate_list:
        entry = rates[rate]
        lows.append(min(min(entry["up_E"]), min(entry["down_E"])))
        highs.append(max(max(entry["up_E"]), max(entry["down_E"])))
    low = max(lows)
    high = min(highs)
    if high - low <= 0.0:
        raise ValueError("五条已选回线没有共同电位区间")

    grid = np.linspace(low, high, 501)
    scores = []
    valid = []
    for x in grid:
        mids = []
        ok = True
        for rate in rate_list:
            entry = rates[rate]
            ju = interp_at(entry["up_E"], entry["up_j"], x)
            jd = interp_at(entry["down_E"], entry["down_j"], x)
            if ju is None or jd is None:
                ok = False
                break
            mids.append((ju + jd) / 2.0)
        if ok:
            scores.append(float(np.mean(np.abs(mids))))
            valid.append(True)
        else:
            scores.append(float("inf"))
            valid.append(False)

    if sum(valid) < 2:
        raise ValueError("共同电位区间内没有足够多的有效取点位置")
    valid_idx = [i for i, ok in enumerate(valid) if ok]
    finite_scores = np.asarray([scores[i] for i in valid_idx])
    best = float(np.min(finite_scores))
    amp = float(np.max(finite_scores) - best)
    tol = max(1e-12, amp * 0.02)

    chosen_idx = [i for i in valid_idx if scores[i] <= best + tol]
    # Choose the contiguous run around the global minimum instead of averaging
    # two separated valleys.
    best_pos = valid_idx[int(np.argmin(finite_scores))]
    runs = []
    run = []
    prev = None
    for i in chosen_idx:
        if prev is not None and i != prev + 1:
            runs.append(run)
            run = []
        run.append(i)
        prev = i
    if run:
        runs.append(run)
    run = next((r for r in runs if best_pos in r), runs[0])
    return float(grid[int(np.mean(run))])


def compute_sample(sample_data, center_value):
    rates = sorted(sample_data)
    if len(rates) < 2:
        raise ValueError("已选扫速少于 2 个，无法线性拟合")
    delta_rows = []
    for rate in rates:
        entry = sample_data[rate]
        ju = interp_at(entry["up_E"], entry["up_j"], center_value)
        jd = interp_at(entry["down_E"], entry["down_j"], center_value)
        if ju is None or jd is None:
            raise ValueError(
                "扫速 %.0f mV/s 在中心电位 %.4f V 缺少升/降支数据"
                % (rate, center_value)
            )
        delta_rows.append((rate, ju, jd, (ju - jd) / 2.0))

    delta_rows.sort(key=lambda row: row[0])
    x = np.asarray([row[0] for row in delta_rows], dtype=float)
    y = np.asarray([row[3] for row in delta_rows], dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    predicted = slope * x + intercept
    ss_res = float(np.sum((y - predicted) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-15 else 1.0

    return {
        "center": center_value,
        "delta_rows": delta_rows,
        "slope": float(slope),
        "intercept": float(intercept),
        "r2": float(r2),
        "rates": x,
        "deltas": y,
        "mF_cm2": float(slope * 1000.0),
        "uF_cm2": float(slope * 1.0e6),
    }


def save_cv_figure(sample, sample_data, center, out_dir, cfg, ecsa):
    fig, ax = plt.subplots(
        figsize=cfg.get("figure", {}).get("figsize", [8.0, 6.0]),
        dpi=cfg.get("figure", {}).get("dpi", 600),
    )
    curve_cfg = cfg.get("curve", {})
    cv_cfg = ecsa["cv"]
    rates = sorted(sample_data)
    min_e = float("inf")
    max_e = float("-inf")
    max_abs_j = 0.0
    for rate in rates:
        entry = sample_data[rate]
        order = np.argsort(entry["order"])
        E = np.asarray(entry["E_all"], dtype=float)[order]
        j = np.asarray(entry["j_all"], dtype=float)[order]
        min_e = min(min_e, float(np.min(E)))
        max_e = max(max_e, float(np.max(E)))
        max_abs_j = max(max_abs_j, float(np.max(np.abs(j))))
        rate_int = int(round(rate))
        label = ("%d mV/s" % rate_int) if abs(rate - rate_int) < 1e-9 else ("%.2f mV/s" % rate)
        ax.plot(E, j, linewidth=curve_cfg.get("linewidth", 2.0),
                marker=curve_cfg.get("marker", "none"), label=label)

    span = max(max_e - min_e, 1e-6)
    pad_x = span * 0.03
    pad_y = max(max_abs_j * 0.1, 1e-6)
    ax.set_xlim(min_e - pad_x, max_e + pad_x)
    ax.set_ylim(-max_abs_j - pad_y, max_abs_j + pad_y)
    ax.set_xlabel(cv_cfg.get("xlabel", "Potential (V)"), fontsize=12,
                  fontweight=cv_cfg.get("fontweight", "normal"))
    ax.set_ylabel(cv_cfg.get("ylabel", "Current density (mA cm$^{-2}$)"), fontsize=12,
                  fontweight=cv_cfg.get("fontweight", "normal"))
    x_major = cv_cfg.get("x_major_step")
    x_minor = cv_cfg.get("x_minor_step")
    if x_major:
        ax.xaxis.set_major_locator(MultipleLocator(x_major))
    if x_minor:
        ax.xaxis.set_minor_locator(MultipleLocator(x_minor))
    if cv_cfg.get("x_format"):
        ax.xaxis.set_major_formatter(FormatStrFormatter(cv_cfg["x_format"]))

    ax.axvline(center, color="black", linestyle="--", linewidth=1.2, alpha=0.8)
    y_top = max_abs_j + pad_y
    ax.text(center, y_top, "E = %.3f V" % center, ha="center", va="top",
            fontsize=10, color="black")
    legend_cfg = cfg.get("legend", {})
    ax.legend(loc=legend_cfg.get("loc", "upper left"),
              fontsize=legend_cfg.get("fontsize", 10),
              frameon=True, edgecolor="black")

    tag = sanitize_name(sample)
    out_path = os.path.join(out_dir, "%s-CV总图.png" % tag)
    os.makedirs(out_dir, exist_ok=True)
    fig.savefig(out_path, dpi=cfg.get("figure", {}).get("dpi", 600),
                bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    return out_path


def save_fit_figure(sample, result, out_dir, cfg, ecsa):
    fig, ax = plt.subplots(
        figsize=cfg.get("figure", {}).get("figsize", [8.0, 6.0]),
        dpi=cfg.get("figure", {}).get("dpi", 600),
    )
    fit_cfg = ecsa["fit"]
    x = result["rates"]
    y = result["deltas"]
    ax.scatter(x, y, s=48, color="black", zorder=3, label="Data")
    x_line = np.linspace(0.0, float(np.max(x)) * 1.1, 100)
    ax.plot(x_line, result["slope"] * x_line + result["intercept"],
            color="black", linewidth=2.0, label="Fit")
    ax.set_xlim(0.0, float(np.max(x)) * 1.12)
    y_vals = list(y) + [result["intercept"]]
    y_min = min(y_vals)
    y_max = max(y_vals)
    pad = max((y_max - y_min) * 0.15, abs(y_max) * 0.05, 1e-6)
    ax.set_ylim(y_min - pad, y_max + pad)
    ax.set_xlabel(fit_cfg.get("xlabel", "Scan rate (mV s$^{-1}$)"), fontsize=12,
                  fontweight=fit_cfg.get("fontweight", "normal"))
    ax.set_ylabel(fit_cfg.get("ylabel", "$\\Delta j$ (mA cm$^{-2}$)"), fontsize=12,
                  fontweight=fit_cfg.get("fontweight", "normal"))
    if fit_cfg.get("x_format"):
        ax.xaxis.set_major_formatter(FormatStrFormatter(fit_cfg["x_format"]))
    if fit_cfg.get("y_format"):
        ax.yaxis.set_major_formatter(FormatStrFormatter(fit_cfg["y_format"]))
    ax.xaxis.set_minor_locator(AutoMinorLocator())
    ax.yaxis.set_minor_locator(AutoMinorLocator())

    text = (
        "$\\Delta j = %.4g + %.4g \\cdot v$\n"
        "$C_{dl}$ = %.4g mF cm$^{-2}$  (= %.4g $\\mu$F cm$^{-2}$)\n"
        "$R^2$ = %.4f"
    ) % (
        result["intercept"],
        result["slope"],
        result["mF_cm2"],
        result["uF_cm2"],
        result["r2"],
    )
    ax.text(0.03, 0.97, text, transform=ax.transAxes, va="top",
            fontsize=11, bbox=dict(boxstyle="round,pad=0.35",
                                   facecolor="white", edgecolor="black"))

    tag = sanitize_name(sample)
    out_path = os.path.join(out_dir, "%s-Cdl拟合.png" % tag)
    os.makedirs(out_dir, exist_ok=True)
    fig.savefig(out_path, dpi=cfg.get("figure", {}).get("dpi", 600),
                bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    return out_path


def write_delta_csv(output_dir, result_rows):
    path = os.path.join(output_dir, "Δj表.csv")
    os.makedirs(output_dir, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(DELTA_HEADER)
        for sample, center, rows, _res in result_rows:
            for rate, ju, jd, delta in rows:
                writer.writerow([
                    sample, "%.6g" % center, "%.6g" % rate,
                    "%.8g" % ju, "%.8g" % jd, "%.8g" % delta,
                ])
    return path


def write_result_csv(output_dir, result_rows, cs_uf):
    header = list(RESULT_HEADER)
    if cs_uf is not None:
        header.append("ECSA(Cdl/Cs)")
    path = os.path.join(output_dir, "Cdl结果.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for sample, center, rows, res in result_rows:
            row = [
                sample,
                "%.6g" % center,
                len(rows),
                "%.8g" % res["slope"],
                "%.8g" % res["intercept"],
                "%.6f" % res["r2"],
                "%.6g" % res["mF_cm2"],
                "%.6g" % res["uF_cm2"],
            ]
            if cs_uf is not None:
                ecsa_value = res["uF_cm2"] / cs_uf
                row.append("%.6g" % ecsa_value)
            writer.writerow(row)
    return path


def write_summary_md(output_dir, result_rows, cs_uf):
    path = os.path.join(output_dir, "Cdl汇总.md")
    header = ["样品", "中心电位/(V vs. RHE)", "Cdl/(mF cm-2)", "Cdl/(µF cm-2)", "R²"]
    if cs_uf is not None:
        header.append("ECSA(Cdl/Cs)")
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * len(header)) + " |"]
    for sample, center, rows, res in result_rows:
        row = [
            sample,
            "%.4f" % center,
            "%.4g" % res["mF_cm2"],
            "%.4g" % res["uF_cm2"],
            "%.4f" % res["r2"],
        ]
        if cs_uf is not None:
            row.append("%.4g" % (res["uF_cm2"] / cs_uf))
        lines.append("| " + " | ".join(row) + " |")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description="ECSA/Cdl 拟合与绘图（只读 selected_cv）")
    parser.add_argument("--selected-dir", required=True, help="selected_cv 中间数据目录")
    parser.add_argument("--output-dir", required=True, help="Cdl结果/图表输出目录")
    parser.add_argument("--config", default=os.path.join(SCRIPT_DIR, "config.yaml"))
    parser.add_argument("--center-potential", action="append", default=[],
                        help="全局数值或 样品名=数值，可重复")
    parser.add_argument("--cs", type=float, default=None, help="比电容 µF/cm2；给定时额外输出 ECSA")
    args = parser.parse_args(argv)

    cfg, ecsa = load_config(args.config)
    if args.cs is None and ecsa.get("cs_uf_cm2") is not None:
        args.cs = float(ecsa["cs_uf_cm2"])
    if "font" in cfg.get("figure", {}):
        plt.rcParams["font.family"] = cfg["figure"]["font"]

    global_center, center_overrides = parse_center_overrides(args.center_potential, ecsa)
    try:
        data = collect_selected(args.selected_dir)
    except ValueError as exc:
        print("错误：%s" % exc)
        return 1

    out_dir = os.path.abspath(args.output_dir)
    os.makedirs(out_dir, exist_ok=True)
    notes = []
    result_rows = []
    for sample in sorted(data):
        sample_data = data[sample]
        center = center_overrides.get(sample, global_center)
        try:
            if center is None:
                center = find_auto_center(sample_data)
            res = compute_sample(sample_data, center)
        except Exception as exc:
            msg = "%s 跳过：%s" % (sample, exc)
            print("警告：%s" % msg)
            notes.append(msg)
            continue

        result_rows.append((sample, center, res["delta_rows"], res))
        figure_dir = os.path.join(out_dir, "ECSA图", sanitize_name(sample))
        cv_path = save_cv_figure(sample, sample_data, center, figure_dir, cfg, ecsa)
        fit_path = save_fit_figure(sample, res, figure_dir, cfg, ecsa)
        notes.append("已生成：%s" % cv_path)
        notes.append("已生成：%s" % fit_path)
        if res["slope"] < 0.0:
            notes.append("警告：%s 的 Cdl 斜率为负，请检查中心电位或电流正负号。" % sample)
        print("%s 完成：Cdl=%.4g mF/cm2，R2=%.4f" % (
            sample, res["mF_cm2"], res["r2"]))

    if not result_rows:
        print("没有样品完成 Cdl 计算。")
        with open(os.path.join(out_dir, "选择说明.txt"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(notes) + "\n")
        return 1

    delta_path = write_delta_csv(out_dir, result_rows)
    result_path = write_result_csv(out_dir, result_rows, args.cs)
    md_path = write_summary_md(out_dir, result_rows, args.cs)
    notes.append("已生成：%s" % delta_path)
    notes.append("已生成：%s" % result_path)
    notes.append("已生成：%s" % md_path)
    note_path = os.path.join(out_dir, "选择说明.txt")
    with open(note_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(notes) + "\n")
    print("结果已写入：%s" % out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
