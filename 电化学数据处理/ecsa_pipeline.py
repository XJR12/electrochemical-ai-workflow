#!/usr/bin/env python3
"""One-command ECSA/Cdl workflow: select -> build selected_cv -> fit/plot.

Phase 1: ecsa_analysis.py parses every CV txt, scores full cycles and writes
         ecsa_per_file.csv + ecsa_best.csv. If any sample still needs manual
         selection the pipeline stops and asks for --pick.
Phase 2: after selection is complete, selected_cv/<样品>.csv is generated.
Phase 3: ecsa_plot.py computes Cdl (and optional ECSA) and writes figures
         without re-reading raw data.

Usage:
    python ecsa_pipeline.py --input-dir <parent folder>
    python ecsa_pipeline.py --input-dir <parent folder> --pick "样品名=2MV_C01.txt#2"
"""

import argparse
import csv
import os
import re
import sys

import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import ecsa_analysis
import ecsa_plot


def load_area(config_path):
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
        return float(cfg.get("area", 1.0))
    except Exception:
        return 1.0


def read_best_rows(best_path):
    """Return [{sample, rate, file, cycle}] and reject unfinished manual rows."""
    rows = []
    with open(best_path, "r", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            selection = row.get("选择方式", "自动")
            if selection == "手动":
                raise ValueError("%s 仍有手动候选，请先用 --pick 指定。" % os.path.basename(best_path))
            try:
                sample = row["样品"]
                rate = float(row["扫速/(mV/s)"])
                cycle = int(row["圈号"])
            except (KeyError, ValueError) as exc:
                raise ValueError("%s 格式不正确：%s" % (os.path.basename(best_path), exc))
            rows.append({
                "sample": sample,
                "rate": rate,
                "file": row["文件"],
                "cycle": cycle,
            })
    seen = {}
    for row in rows:
        key = (row["sample"], row["rate"])
        if key in seen:
            raise ValueError("ecsa_best.csv 中 %s / %.0f mV/s 出现多个选择行" % key)
        seen[key] = row
    return rows


def resolve_file(input_dir, sample, filename):
    direct = os.path.join(input_dir, sample, filename)
    if os.path.exists(direct):
        return direct
    for root, _, names in os.walk(input_dir):
        if os.path.basename(root) == sample and filename in names:
            return os.path.join(root, filename)
    return None


def write_selected_csv(path, sample, rate_rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(ecsa_plot.SELECTED_HEADER)
        seq = 0
        for rate, filename, cycle_no, cycle in rate_rows:
            # Reconstruct chronological branch order from the stored arrays.
            first_up = False
            if cycle["up_e"] and cycle["E_all"]:
                first_up = abs(cycle["up_e"][0] - cycle["E_all"][0]) < 1e-9
            if first_up:
                branches = [("升支", cycle["up_e"], cycle["up_j"]),
                            ("降支", cycle["down_e"], cycle["down_j"])]
            else:
                branches = [("降支", cycle["down_e"], cycle["down_j"]),
                            ("升支", cycle["up_e"], cycle["up_j"])]
            for branch, E_list, j_list in branches:
                for e, j in zip(E_list, j_list):
                    writer.writerow([
                        sample,
                        "%.6g" % rate,
                        filename,
                        cycle_no,
                        branch,
                        seq,
                        "%.8g" % e,
                        "%.8g" % j,
                    ])
                    seq += 1


def build_selected_csv(input_dir, ecsa_out, area):
    best_path = os.path.join(ecsa_out, "ecsa_best.csv")
    if not os.path.exists(best_path):
        raise ValueError("找不到 %s，先运行选择阶段" % best_path)
    rows = read_best_rows(best_path)
    if not rows:
        raise ValueError("%s 中没有已选择数据" % best_path)

    by_sample = {}
    for row in rows:
        by_sample.setdefault(row["sample"], []).append(row)

    selected_dir = os.path.join(ecsa_out, "selected_cv")
    os.makedirs(selected_dir, exist_ok=True)
    for sample in sorted(by_sample):
        rate_rows = []
        for row in sorted(by_sample[sample], key=lambda r: r["rate"]):
            path = resolve_file(input_dir, sample, row["file"])
            if path is None:
                raise ValueError("找不到已选文件：%s / %s" % (sample, row["file"]))
            cycle = ecsa_analysis.find_cycle(path, area, row["cycle"])
            if cycle is None:
                raise ValueError("%s / %s 中找不到第 %d 圈" % (
                    sample, row["file"], row["cycle"]))
            rate_rows.append((row["rate"], row["file"], row["cycle"], cycle))
        out_path = os.path.join(selected_dir, sample + ".csv")
        write_selected_csv(out_path, sample, rate_rows)
        print("已生成中间数据：%s" % out_path)
    return selected_dir


def run_stages(args, ecsa_out):
    input_dir = os.path.abspath(args.input_dir)
    config = os.path.abspath(args.config)

    analysis_args = [
        "--input-dir", input_dir,
        "--output-dir", ecsa_out,
        "--config", config,
        "--area", str(args.area),
    ]
    if args.score_gap is not None:
        analysis_args += ["--score-gap", str(args.score_gap)]
    for pick in args.pick:
        analysis_args += ["--pick", pick]

    print("\n=== 1/3 解析 CV 并自动选圈 ===")
    rc = ecsa_analysis.main(analysis_args)
    if rc != 0:
        print("\n停止：还有手动候选未选择。请用 --pick \"样品名=文件名#圈号\" 重跑。")
        return False

    print("\n=== 2/3 生成 selected_cv 中间数据 ===")
    try:
        selected_dir = build_selected_csv(input_dir, ecsa_out, args.area)
    except ValueError as exc:
        print("\n停止：%s" % exc)
        return False

    print("\n=== 3/3 Cdl 拟合与绘图 ===")
    plot_args = [
        "--selected-dir", selected_dir,
        "--output-dir", ecsa_out,
        "--config", config,
    ]
    for center in args.center_potential:
        plot_args += ["--center-potential", center]
    if args.cs is not None:
        plot_args += ["--cs", str(args.cs)]
    rc = ecsa_plot.main(plot_args)
    return rc == 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="ECSA/Cdl 一键：选择 → selected_cv → Cdl 拟合与图")
    parser.add_argument("--input-dir", required=True, help="父目录，每个子文件夹为一个样品")
    parser.add_argument("--output-dir", default=None, help="输出根目录（默认 output/<输入目录名>_0）")
    parser.add_argument("--config", default=os.path.join(SCRIPT_DIR, "config.yaml"))
    parser.add_argument("--area", type=float, default=None, help="电极面积 cm2，默认读 config.yaml")
    parser.add_argument("--pick", action="append", default=[], help='样品名=文件名#圈号，可重复')
    parser.add_argument("--score-gap", type=float, default=None, help="自动选择质量分阈值")
    parser.add_argument("--center-potential", action="append", default=[],
                        help="全局数值或 样品名=数值，可重复")
    parser.add_argument("--cs", type=float, default=None, help="比电容 µF/cm2；给定时额外输出 ECSA")
    args = parser.parse_args(argv)

    if args.area is None:
        args.area = load_area(args.config)
    if args.output_dir:
        output_root = os.path.abspath(args.output_dir)
    else:
        base = os.path.basename(args.input_dir.rstrip("\\/"))
        output_root = os.path.join(SCRIPT_DIR, "output", "%s_0" % base)

    ecsa_out = os.path.join(output_root, "ecsa")
    try:
        ok = run_stages(args, ecsa_out)
        return 0 if ok else 1
    except PermissionError:
        m = re.search(r"_(\d+)$", output_root)
        if m:
            base_root = output_root[:m.start()]
            n = int(m.group(1)) + 1
        else:
            base_root = output_root
            n = 0
        while True:
            fallback = "%s_%d" % (base_root, n)
            print("\n输出目录被占用（可能是 CSV 正被打开），自动改用：%s" % fallback)
            ecsa_fallback = os.path.join(fallback, "ecsa")
            try:
                ok = run_stages(args, ecsa_fallback)
                return 0 if ok else 1
            except PermissionError:
                n += 1


if __name__ == "__main__":
    sys.exit(main())
