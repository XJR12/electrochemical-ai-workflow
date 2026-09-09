#!/usr/bin/env python3
"""Generate Tafel figures from iR-corrected BioLogic EC-Lab txt files.

Two entry modes:
- --best-csv <lsv_best.csv> --input-dir <data folder>: reuse the iR curves
  already selected by the LSV pipeline.
- --files <txt ...>: draw one Tafel figure per explicitly listed iR txt file.

Tafel axes:
    x = log10(j), j = I / area (mA cm^-2)
    y = eta = (E - rhe) * 1000 (mV)

Each curve is drawn twice: all positive-current points, and a cropped view
(default j >= 1 mA cm^-2) so the linear-looking region can be inspected.
The Tafel slope is then found automatically by sliding a ~1 decade-wide
window along log10(j) and choosing the window with the highest R^2.
"""

import argparse
import csv
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FormatStrFormatter, MultipleLocator
import numpy as np
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
    "tafel": {
        "xlabel": "log(j / mA cm$^{-2}$)",
        "ylabel": "Overpotential $\\eta$ (mV)",
        "x_major_step": 1.0,
        "x_minor_step": 0.5,
        "y_major_step": 50.0,
        "y_minor_step": 10.0,
        "j_min": 1.0,
        "j_max": None,
        "eta_min": None,
        "eta_max": None,
        "fit_eta_min_mv": 50.0,
        "fit_window_decades": 1.0,
        "fit_r2_min": 0.99,
        "fit_slope_min_mv_dec": 30.0,
        "fit_slope_max_mv_dec": 200.0,
        "fontweight": "bold",
    },
    "legend": {
        "loc": "upper left",
        "fontsize": 10,
    },
    "area": 1.0,
}


def load_config(path):
    cfg = {}
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
    merged = {}
    for section, default in DEFAULTS.items():
        if not isinstance(default, dict):
            merged[section] = default
            continue
        merged[section] = {**default, **(cfg.get(section) or {})}
    merged["compare"] = cfg.get("compare") or {}
    merged["area"] = cfg.get("area", DEFAULTS.get("area", 1.0))
    return merged


def prepare_curve(path, area, rhe):
    """Parse one file and convert to (log10(j), eta_mV) pairs."""
    E, I, is_density = read_lsv(path)
    E2, I2 = clean_forward_sweep(E, I)
    if len(E2) < 3:
        return None
    j_raw = I2 if is_density else [v / area for v in I2]

    points = []
    for e, jv in zip(E2, j_raw):
        eta = (e - rhe) * 1000.0
        if jv > 0.0 and eta > 0.0:
            points.append((e, eta, jv, math.log10(jv)))
    if len(points) < 2:
        return None

    stem = os.path.splitext(os.path.basename(path))[0].replace(" ", "-")
    return {
        "path": path,
        "folder": os.path.basename(os.path.dirname(path)),
        "kind": group_kind(path),
        "stem": stem,
        "label": stem,
        "E": [p[0] for p in points],
        "eta": [p[1] for p in points],
        "j": [p[2] for p in points],
        "logj": [p[3] for p in points],
    }


def filter_curve(curve, tafel_cfg):
    j_min = tafel_cfg.get("j_min")
    j_max = tafel_cfg.get("j_max")
    eta_min = tafel_cfg.get("eta_min")
    eta_max = tafel_cfg.get("eta_max")
    out = dict(curve)
    out["E"], out["eta"], out["j"], out["logj"] = [], [], [], []
    for e, eta, jv, lj in zip(curve["E"], curve["eta"], curve["j"], curve["logj"]):
        if j_min is not None and jv < j_min:
            continue
        if j_max is not None and jv > j_max:
            continue
        if eta_min is not None and eta < eta_min:
            continue
        if eta_max is not None and eta > eta_max:
            continue
        out["E"].append(e)
        out["eta"].append(eta)
        out["j"].append(jv)
        out["logj"].append(lj)
    return out


def _fit_domain(curve, tafel_cfg):
    """Return sorted (log10(j), eta) pairs allowed for slope fitting."""
    base = filter_curve(curve, tafel_cfg)
    fit_eta_min = tafel_cfg.get("fit_eta_min_mv")
    pairs = [
        (lj, eta)
        for lj, eta in zip(base["logj"], base["eta"])
        if fit_eta_min is None or eta >= fit_eta_min
    ]
    pairs.sort()
    return [p[0] for p in pairs], [p[1] for p in pairs]


def _fit_candidates(xs, ys, target_decades):
    """Return one candidate per start, with the span closest to one decade."""
    candidates = []
    n = len(xs)
    for start in range(n - 2):
        end = start + 1
        while end < n and xs[end] - xs[start] < target_decades:
            end += 1
        if end >= n:
            break
        if end - start + 1 < 3:
            continue
        xw = np.asarray(xs[start : end + 1], dtype=float)
        yw = np.asarray(ys[start : end + 1], dtype=float)
        slope, intercept = np.polyfit(xw, yw, 1)
        predicted = slope * xw + intercept
        ss_res = float(np.sum((yw - predicted) ** 2))
        ss_tot = float(np.sum((yw - np.mean(yw)) ** 2))
        if ss_tot > 1e-15:
            r2 = 1.0 - ss_res / ss_tot
        else:
            r2 = 1.0 if ss_res < 1e-15 else 0.0
        candidates.append({
            "slope": float(slope),
            "intercept": float(intercept),
            "r2": float(r2),
            "x0": float(xw[0]),
            "x1": float(xw[-1]),
            "eta0": float(yw[0]),
            "eta1": float(yw[-1]),
            "n": int(xw.size),
        })
    return candidates


def _no_fit_result(warning):
    return {
        "ok": False,
        "slope": None,
        "intercept": None,
        "r2": None,
        "x0": None,
        "x1": None,
        "eta0": None,
        "eta1": None,
        "n": 0,
        "warning": warning,
    }


def find_tafel_fit(curve, tafel_cfg):
    """Fit the most linear ~1 decade window and return a result dict."""
    xs, ys = _fit_domain(curve, tafel_cfg)
    target = float(tafel_cfg.get("fit_window_decades", 1.0))
    slope_min = tafel_cfg.get("fit_slope_min_mv_dec")
    slope_max = tafel_cfg.get("fit_slope_max_mv_dec")
    r2_min = tafel_cfg.get("fit_r2_min", 0.99)

    if len(xs) < 3:
        return _no_fit_result(
            "无足够拟合数据点（可用点 %d），未自动拟合" % len(xs)
        )

    candidates = _fit_candidates(xs, ys, target)
    if not candidates:
        return _no_fit_result(
            "未找到跨度至少 %.1f 个数量级的连续窗口（可用点 %d），未自动拟合"
            % (target, len(xs))
        )

    ranked = sorted(candidates, key=lambda c: c["r2"], reverse=True)
    valid = [
        c for c in ranked
        if (slope_min is None or c["slope"] >= slope_min)
        and (slope_max is None or c["slope"] <= slope_max)
    ]
    if not valid:
        top = ranked[0]
        return _no_fit_result(
            "所有候选斜率均不在 %.0f-%.0f mV/dec 范围（最高R²=%.4f），未自动拟合"
            % (slope_min, slope_max, top["r2"])
        )

    chosen = valid[0]
    warning = ""
    if chosen["r2"] < r2_min:
        warning = (
            "R²=%.4f 低于 %.4f，线性不佳，建议人工复核或先降噪"
            % (chosen["r2"], r2_min)
        )
    if chosen is not ranked[0]:
        prefix = "最高R²候选斜率 %.1f mV/dec 不在范围内，已顺延至范围内有效候选" % (
            ranked[0]["slope"]
        )
        warning = prefix if not warning else prefix + "；" + warning

    result = {
        "ok": True,
        "slope": chosen["slope"],
        "intercept": chosen["intercept"],
        "r2": chosen["r2"],
        "x0": chosen["x0"],
        "x1": chosen["x1"],
        "eta0": chosen["eta0"],
        "eta1": chosen["eta1"],
        "n": chosen["n"],
        "warning": warning,
    }
    return result


def attach_fit_results(curves, tafel_cfg, notes):
    """Add one Tafel slope result to each curve, computing only once."""
    for c in curves:
        if c.get("tafel_fit") is not None:
            continue
        fit = find_tafel_fit(c, tafel_cfg)
        c["tafel_fit"] = fit
        name = os.path.basename(c["path"])
        if fit["ok"]:
            print("Tafel 拟合：%s -> %.1f mV/dec (R²=%.4f)" % (
                name, fit["slope"], fit["r2"]
            ))
        if fit["warning"]:
            print("警告：%s（%s）" % (fit["warning"], name))
            notes.append("Tafel 拟合警告：%s（%s）" % (fit["warning"], name))


def save_tafel_figure(curves, out_path, cfg, notes, fit_mode=False):
    fig, ax = plt.subplots(figsize=cfg["figure"]["figsize"], dpi=cfg["figure"]["dpi"])
    fitted_lines = []
    if fit_mode:
        no_fit = []
        for c in curves:
            fit = c.get("tafel_fit") or {}
            if fit.get("ok"):
                label = c["label"]
                if len(curves) > 1:
                    label = "%s (%.1f mV/dec, R²=%.4f)" % (
                        label, fit["slope"], fit["r2"]
                    )
                y0 = fit["slope"] * fit["x0"] + fit["intercept"]
                y1 = fit["slope"] * fit["x1"] + fit["intercept"]
                ax.plot(
                    [fit["x0"], fit["x1"]], [y0, y1],
                    linewidth=cfg["curve"]["linewidth"], label=label,
                )
                fitted_lines.append((fit["x0"], fit["x1"], y0, y1))
            elif len(curves) > 1:
                no_fit.append(c["label"] + " (no fit)")
        for label in no_fit:
            ax.plot([], [], color="none", label=label)
    else:
        for c in curves:
            ax.plot(
                c["logj"], c["eta"], linewidth=cfg["curve"]["linewidth"],
                marker=cfg["curve"]["marker"], label=c["label"],
            )

    if fit_mode and fitted_lines:
        xmin = min(item[0] for item in fitted_lines)
        xmax = max(item[1] for item in fitted_lines)
        ymin = min(item[2] for item in fitted_lines)
        ymax = max(item[3] for item in fitted_lines)
    elif fit_mode:
        xmin, xmax, ymin, ymax = 0.0, 1.0, 0.0, 100.0
    else:
        xmin = min(min(c["logj"]) for c in curves)
        xmax = max(max(c["logj"]) for c in curves)
        ymin = min(min(c["eta"]) for c in curves)
        ymax = max(max(c["eta"]) for c in curves)
    pad_x = max((xmax - xmin) * 0.05, 0.1)
    pad_y = max((ymax - ymin) * 0.05, 5.0)
    ax.set_xlim(xmin - pad_x, xmax + pad_x)
    ax.set_ylim(ymin - pad_y, ymax + pad_y)

    ax.set_xlabel(cfg["tafel"]["xlabel"], fontsize=12,
                  fontweight=cfg["tafel"].get("fontweight", "normal"))
    ax.set_ylabel(cfg["tafel"]["ylabel"], fontsize=12,
                  fontweight=cfg["tafel"].get("fontweight", "normal"))
    ax.xaxis.set_major_locator(MultipleLocator(cfg["tafel"]["x_major_step"]))
    ax.xaxis.set_minor_locator(MultipleLocator(cfg["tafel"]["x_minor_step"]))
    ax.xaxis.set_major_formatter(FormatStrFormatter("%.0f"))
    ax.yaxis.set_major_locator(MultipleLocator(cfg["tafel"]["y_major_step"]))
    ax.yaxis.set_minor_locator(MultipleLocator(cfg["tafel"]["y_minor_step"]))
    ax.yaxis.set_major_formatter(FormatStrFormatter("%.0f"))
    ax.legend(loc=cfg["legend"]["loc"], fontsize=cfg["legend"]["fontsize"],
              frameon=True, edgecolor="black")

    if fit_mode and len(curves) == 1:
        fit = curves[0].get("tafel_fit") or {}
        if fit.get("ok"):
            text = "Tafel slope = %.1f mV/dec\nR² = %.4f" % (
                fit["slope"], fit["r2"]
            )
        else:
            text = "No valid 1-decade fit window"
        ax.text(0.97, 0.04, text, transform=ax.transAxes, ha="right",
                va="bottom", fontsize=11,
                bbox=dict(boxstyle="round,pad=0.35",
                          facecolor="white", edgecolor="black"))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=cfg["figure"]["dpi"], bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    notes.append("生成：%s" % out_path)
    return out_path


def save_tafel_versions(curves, out_dir, stem, cfg, notes):
    attach_fit_results(curves, cfg["tafel"], notes)
    full = [c for c in curves if len(c["eta"]) >= 2]
    if full:
        save_tafel_figure(full, os.path.join(out_dir, stem + ".png"), cfg, notes)
        save_tafel_figure(
            full, os.path.join(out_dir, stem + "-斜率拟合.png"), cfg, notes,
            fit_mode=True,
        )

    crops = [filter_curve(c, cfg["tafel"]) for c in curves]
    crops = [c for c in crops if len(c["eta"]) >= 2]
    if crops:
        save_tafel_figure(crops, os.path.join(out_dir, stem + "-截取.png"), cfg, notes)
    else:
        notes.append("跳过截取版：%s（筛选后无足够数据点）" % stem)


def read_selected(best_csv):
    """Return {(folder, kind): basename} from lsv_best.csv; iR rows only."""
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
                raise ValueError(
                    "lsv_best.csv 仍有手动候选（%s / %s），请先完成人工选择"
                    % (folder, row["类别"])
                )
            if kind == "ir":
                selected[(folder, kind)] = row["文件"]
    return selected


def scan_txt(input_dir):
    paths = []
    for root, _, names in os.walk(input_dir):
        for name in sorted(names):
            if name.lower().endswith(".txt"):
                paths.append(os.path.join(root, name))
    return paths


def write_per_file_csv(output_dir, curves):
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "tafel_per_file.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "目录", "文件", "点数", "η最小/mV", "η最大/mV",
            "j最小/mA_cm-2", "j最大/mA_cm-2", "log10(j)最小", "log10(j)最大",
            "Tafel斜率/(mV/dec)", "截距", "R²",
            "拟合log10(j)起", "拟合log10(j)止", "拟合点数",
            "拟合η起/mV", "拟合η止/mV", "警告",
        ])
        for c in curves:
            fit = c.get("tafel_fit") or {}
            if fit.get("ok"):
                slope_text = "%.1f" % fit["slope"]
                intercept_text = "%.1f" % fit["intercept"]
                r2_text = "%.4f" % fit["r2"]
                x0_text = "%.4f" % fit["x0"]
                x1_text = "%.4f" % fit["x1"]
                n_text = str(fit["n"])
                eta0_text = "%.1f" % fit["eta0"]
                eta1_text = "%.1f" % fit["eta1"]
            else:
                slope_text = intercept_text = r2_text = ""
                x0_text = x1_text = n_text = ""
                eta0_text = eta1_text = ""
            writer.writerow([
                c["folder"],
                os.path.basename(c["path"]),
                len(c["eta"]),
                "%.1f" % min(c["eta"]),
                "%.1f" % max(c["eta"]),
                "%.6g" % min(c["j"]),
                "%.6g" % max(c["j"]),
                "%.4f" % min(c["logj"]),
                "%.4f" % max(c["logj"]),
                slope_text,
                intercept_text,
                r2_text,
                x0_text,
                x1_text,
                n_text,
                eta0_text,
                eta1_text,
                fit.get("warning", ""),
            ])
    return path


def write_points_csv(output_dir, curves):
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "tafel_points.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["目录", "文件", "E/V", "η/mV", "j/mA_cm-2", "log10(j)"])
        for c in curves:
            for e, eta, jv, lj in zip(c["E"], c["eta"], c["j"], c["logj"]):
                writer.writerow([
                    c["folder"],
                    os.path.basename(c["path"]),
                    "%.4f" % e,
                    "%.1f" % eta,
                    "%.6g" % jv,
                    "%.4f" % lj,
                ])
    return path


def write_summary_md(output_dir, curves):
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "Tafel数据对比.md")
    lines = [
        "| 样品 | 文件 | η范围/mV | j范围/mA·cm⁻² | log10(j)范围 | Tafel斜率/(mV/dec) | R² |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for c in curves:
        fit = c.get("tafel_fit") or {}
        if fit.get("ok"):
            slope_text = "%.1f" % fit["slope"]
            r2_text = "%.4f" % fit["r2"]
        else:
            slope_text = r2_text = "-"
        lines.append("| %s | %s | %.1f-%.1f | %.4g-%.4g | %.2f-%.2f | %s | %s |" % (
            c["folder"],
            os.path.basename(c["path"]),
            min(c["eta"]),
            max(c["eta"]),
            min(c["j"]),
            max(c["j"]),
            min(c["logj"]),
            max(c["logj"]),
            slope_text,
            r2_text,
        ))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def write_notes(output_dir, notes):
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "选择说明.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(notes) + "\n")
    return path


def build_comparison_figures(curves, out_dir, cfg, notes):
    if len(curves) < 2:
        notes.append("跳过对比图：已选 iR 曲线不足 2 条")
        return
    save_tafel_versions(curves, out_dir, "Tafel", cfg, notes)

    tokens = {}
    for c in curves:
        for tok in c["folder"].replace("-", " ").split():
            tokens.setdefault(tok, set()).add(c["folder"])
    for tok in sorted(tokens):
        members = [c for c in curves if c["folder"] in tokens[tok]]
        if len(members) < 2 or len(members) == len(curves):
            continue
        save_tafel_versions(members, out_dir, "对比-%s-Tafel" % tok, cfg, notes)

    for group in cfg.get("compare", {}).get("manual_groups") or []:
        gname = group.get("name", "manual")
        folders = group.get("folders", [])
        members = [c for c in curves if c["folder"] in folders]
        if len(members) < 2:
            continue
        save_tafel_versions(members, out_dir, "对比-%s-Tafel" % gname, cfg, notes)


def run_direct(files, output_dir, cfg, area, rhe, notes):
    curves = []
    skipped_raw = []
    for p in files:
        p = os.path.abspath(p)
        if not os.path.exists(p):
            print("警告：文件不存在：%s" % p)
            continue
        if group_kind(p) != "ir":
            skipped_raw.append(p)
            print("警告：跳过非 iR 文件（Tafel 只画 iR 后数据）：%s" % p)
            continue
        c = prepare_curve(p, area, rhe)
        if c is None:
            print("警告：无法解析或无正电流：%s" % p)
            continue
        curves.append(c)

    if not curves:
        print("没有可用的 iR Tafel 数据。")
        if skipped_raw:
            print("跳过 raw 文件数：%d" % len(skipped_raw))
        return False

    sample_dir = os.path.join(output_dir, "样品")
    for c in curves:
        folder_stem = c["folder"].replace(" ", "-")
        c["stem"] = "%s-%s" % (folder_stem, c["stem"])
        c["label"] = c["stem"]
        save_tafel_versions([c], sample_dir, "Tafel-%s" % c["stem"], cfg, notes)
        print("已生成 Tafel 图：%s" % c["stem"])

    write_per_file_csv(output_dir, curves)
    write_points_csv(output_dir, curves)
    write_summary_md(output_dir, curves)
    write_notes(output_dir, notes)
    print("CSV 与说明已写入：%s" % output_dir)
    return True


def run_best_csv(input_dir, best_csv, output_dir, cfg, area, rhe, notes):
    parsed = {}
    for p in scan_txt(input_dir):
        c = prepare_curve(p, area, rhe)
        if c is None:
            continue
        parsed[(c["folder"], c["kind"], os.path.basename(p))] = c

    selected = read_selected(best_csv)
    curves = []
    for key, basename in selected.items():
        lookup = (key[0], key[1], basename)
        if lookup not in parsed:
            print("警告：找不到已选数据 %s / %s / %s" % (key[0], key[1], basename))
            continue
        c = parsed[lookup]
        c["stem"] = c["folder"].replace(" ", "-")
        c["label"] = c["stem"]
        curves.append(c)

    if not curves:
        print("lsv_best.csv 中没有可用的 iR Tafel 数据。")
        return False

    curves.sort(key=lambda c: c["folder"])
    sample_dir = os.path.join(output_dir, "样品")
    for c in curves:
        save_tafel_versions([c], sample_dir, "Tafel-%s" % c["stem"], cfg, notes)
    build_comparison_figures(curves, os.path.join(output_dir, "对比图"), cfg, notes)

    write_per_file_csv(output_dir, curves)
    write_points_csv(output_dir, curves)
    write_summary_md(output_dir, curves)
    write_notes(output_dir, notes)
    print("CSV 与说明已写入：%s" % output_dir)
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tafel 图：log10(j) - η，只使用 iR 后数据")
    parser.add_argument("--files", nargs="+", default=[], help="直接指定的 iR txt 文件")
    parser.add_argument("--input-dir", help="best-csv 模式下扫描的数据目录")
    parser.add_argument("--best-csv", help="LSV 已选好的 lsv_best.csv")
    parser.add_argument("--output-dir", default=os.path.join(SCRIPT_DIR, "output", "tafel"))
    parser.add_argument("--config", default=os.path.join(SCRIPT_DIR, "config.yaml"))
    parser.add_argument("--area", type=float, default=None, help="电极面积 cm2，默认读 config.yaml 的 area")
    parser.add_argument("--rhe", type=float, default=1.23, help="RHE 基准电位（默认 1.23）")
    parser.add_argument("--j-min", type=float, default=None, help="截取版电流下界")
    parser.add_argument("--j-max", type=float, default=None, help="截取版电流上界")
    parser.add_argument("--eta-min", type=float, default=None, help="截取版过电位下界 mV")
    parser.add_argument("--eta-max", type=float, default=None, help="截取版过电位上界 mV")
    args = parser.parse_args(argv)

    if args.output_dir:
        args.output_dir = os.path.abspath(args.output_dir)
    if args.config:
        args.config = os.path.abspath(args.config)
    if args.input_dir:
        args.input_dir = os.path.abspath(args.input_dir)
    if args.best_csv:
        args.best_csv = os.path.abspath(args.best_csv)

    cfg = load_config(args.config)
    if args.area is None:
        args.area = cfg.get("area", 1.0)
    for key in ("j_min", "j_max", "eta_min", "eta_max"):
        value = getattr(args, key)
        if value is not None:
            cfg["tafel"][key] = value
    if "font" in cfg["figure"]:
        plt.rcParams["font.family"] = cfg["figure"]["font"]

    notes = []
    if args.best_csv:
        if not args.input_dir:
            parser.error("使用 --best-csv 时必须提供 --input-dir")
        ok = run_best_csv(args.input_dir, args.best_csv, args.output_dir, cfg,
                          args.area, args.rhe, notes)
    elif args.files:
        ok = run_direct(args.files, args.output_dir, cfg, args.area, args.rhe, notes)
    else:
        parser.error("需要 --files 或 --best-csv")

    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
