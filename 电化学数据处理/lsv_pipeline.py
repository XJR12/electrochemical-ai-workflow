#!/usr/bin/env python3
"""One-command LSV workflow: select -> (wait for manual picks) -> summary MD + figures.

Phase 1: lsv_analysis.py produces lsv_per_file.csv and lsv_best.csv.
         If any group still needs manual selection, the pipeline stops and
         asks the user to specify the picks; rerun with --pick to continue.
Phase 2: after selection is complete, 数据对比.md is written and the sample
         figures (样品/) and comparison figures (对比图/) are generated.

Usage:
    python lsv_pipeline.py --input-dir <data folder>
    python lsv_pipeline.py --input-dir <data folder> --pick "Ru-2mg=1-LSV_C01.txt"
"""

import argparse
import os
import re
import sys

import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import lsv_analysis
import lsv_compare
import lsv_plot


def load_area(config_path):
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
        return float(cfg.get("area", 1.0))
    except Exception:
        return 1.0


def run_stages(args, output_dir):
    input_dir = os.path.abspath(args.input_dir)
    config = os.path.abspath(args.config)
    sample_dir = os.path.join(output_dir, "样品")
    compare_dir = os.path.join(output_dir, "对比图")

    analysis_args = [
        "--input-dir", input_dir,
        "--output-dir", output_dir,
        "--area", str(args.area),
        "--rhe", str(args.rhe),
        "--targets"] + [str(t) for t in args.targets]
    if args.gap_mv is not None:
        analysis_args += ["--eta10-gap", str(args.gap_mv)]
    if args.pick:
        for pick in args.pick:
            analysis_args += ["--pick", pick]

    print("=== 1/3 过电位分析（选择） ===")
    rc = lsv_analysis.main(analysis_args)
    if rc != 0:
        print("\n停止：还有手动候选未选择。请告诉我各组的选定文件后重跑。")
        return False

    if not args.skip_plot:
        print("\n=== 2/3 样品图 ===")
        plot_args = [
            "--input-dir", input_dir,
            "--output-dir", sample_dir,
            "--config", config,
            "--area", str(args.area),
        ]
        if args.x_min is not None:
            plot_args += ["--x-min", str(args.x_min)]
        lsv_plot.main(plot_args)

    if not args.skip_compare:
        print("\n=== 3/3 对比图 ===")
        compare_args = [
            "--input-dir", input_dir,
            "--best-csv", os.path.join(output_dir, "lsv_best.csv"),
            "--output-dir", compare_dir,
            "--config", config,
            "--area", str(args.area),
            "--rhe", str(args.rhe),
            "--targets"] + [str(t) for t in args.targets]
        if args.exclude_mv is not None:
            compare_args += ["--exclude-mv", str(args.exclude_mv)]
        if args.majority_ratio is not None:
            compare_args += ["--majority-ratio", str(args.majority_ratio)]
        lsv_compare.main(compare_args)

    print("\n全部完成，输出目录：%s" % output_dir)
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description="LSV 一键：选择 → 数据对比.md → 样品图 + 对比图")
    parser.add_argument("--input-dir", required=True, help="数据目录（递归扫描 *.txt）")
    parser.add_argument("--output-dir", default=None, help="输出根目录（默认 output/<输入目录名>_0）")
    parser.add_argument("--config", default=os.path.join(SCRIPT_DIR, "config.yaml"), help="配置文件")
    parser.add_argument("--area", type=float, default=None, help="电极面积 cm2，默认读 config.yaml 的 area")
    parser.add_argument("--rhe", type=float, default=1.23, help="RHE 基准电位")
    parser.add_argument("--targets", nargs="+", type=float, default=[10.0, 100.0], help="目标电流密度")
    parser.add_argument("--x-min", type=float, default=None, help="样品图 x 轴起点（默认读 config）")
    parser.add_argument("--gap-mv", type=float, default=None, help="η10 并列阈值")
    parser.add_argument("--exclude-mv", type=float, default=None, help="极差样品剔除阈值")
    parser.add_argument("--majority-ratio", type=float, default=None, help="多数曲线达到 100 的比例阈值")
    parser.add_argument("--pick", action="append", default=[], help="目录=文件名，可重复指定")
    parser.add_argument("--skip-plot", action="store_true", help="跳过样品图")
    parser.add_argument("--skip-compare", action="store_true", help="跳过对比图")
    args = parser.parse_args(argv)
    if args.area is None:
        args.area = load_area(args.config)

    input_dir = os.path.abspath(args.input_dir)
    if args.output_dir:
        output_dir = os.path.abspath(args.output_dir)
    else:
        base = os.path.basename(input_dir.rstrip("\\/"))
        output_dir = os.path.join(SCRIPT_DIR, "output", "%s_0" % base)

    try:
        ok = run_stages(args, output_dir)
        return 0 if ok else 1
    except PermissionError:
        m = re.search(r"_(\d+)$", output_dir)
        if m:
            base = output_dir[:m.start()]
            n = int(m.group(1)) + 1
        else:
            base = output_dir
            n = 0
        while True:
            fallback = "%s_%d" % (base, n)
            print("\n输出目录被占用（可能是文件正被打开），自动改用：%s" % fallback)
            try:
                ok = run_stages(args, fallback)
                return 0 if ok else 1
            except PermissionError:
                n += 1


if __name__ == "__main__":
    sys.exit(main())
