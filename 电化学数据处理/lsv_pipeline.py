#!/usr/bin/env python3
"""One-command LSV workflow: analysis -> single-sample figures -> comparison figures.

Usage:
    python lsv_pipeline.py --input-dir <data folder>
    python lsv_pipeline.py --input-dir <data folder> --skip-compare
    python lsv_pipeline.py --input-dir <data folder> --pick "3% low 1mg=2-LSV_C01.txt"
"""

import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import lsv_analysis
import lsv_compare
import lsv_plot


def main(argv=None):
    parser = argparse.ArgumentParser(description="LSV 一键：分析 + 画图 + 对比图")
    parser.add_argument("--input-dir", required=True, help="数据目录（递归扫描 *.txt）")
    parser.add_argument("--output-dir", default=os.path.join(SCRIPT_DIR, "output"), help="输出根目录")
    parser.add_argument("--config", default=os.path.join(SCRIPT_DIR, "config.yaml"), help="配置文件")
    parser.add_argument("--area", type=float, default=1.0, help="电极面积 cm2")
    parser.add_argument("--rhe", type=float, default=1.23, help="RHE 基准电位")
    parser.add_argument("--targets", nargs="+", type=float, default=[10.0, 100.0], help="目标电流密度")
    parser.add_argument("--x-min", type=float, default=None, help="样品图 x 轴起点（默认读 config）")
    parser.add_argument("--gap-mv", type=float, default=None, help="η10 并列阈值")
    parser.add_argument("--exclude-mv", type=float, default=None, help="极差样品剔除阈值")
    parser.add_argument("--majority-ratio", type=float, default=None, help="多数曲线达到 100 的比例阈值")
    parser.add_argument("--pick", nargs="+", default=[], help="目录=文件名，指定最优曲线")
    parser.add_argument("--skip-plot", action="store_true", help="跳过样品图")
    parser.add_argument("--skip-compare", action="store_true", help="跳过对比图")
    args = parser.parse_args(argv)

    input_dir = os.path.abspath(args.input_dir)
    output_dir = os.path.abspath(args.output_dir)
    config = os.path.abspath(args.config)
    figures_dir = os.path.join(output_dir, "figures")
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
        analysis_args += ["--pick"] + args.pick

    plot_args = [
        "--input-dir", input_dir,
        "--output-dir", figures_dir,
        "--config", config,
        "--area", str(args.area),
    ]
    if args.x_min is not None:
        plot_args += ["--x-min", str(args.x_min)]

    compare_args = [
        "--input-dir", input_dir,
        "--output-dir", compare_dir,
        "--config", config,
        "--area", str(args.area),
        "--rhe", str(args.rhe),
        "--targets"] + [str(t) for t in args.targets]
    if args.gap_mv is not None:
        compare_args += ["--gap-mv", str(args.gap_mv)]
    if args.exclude_mv is not None:
        compare_args += ["--exclude-mv", str(args.exclude_mv)]
    if args.majority_ratio is not None:
        compare_args += ["--majority-ratio", str(args.majority_ratio)]
    if args.pick:
        compare_args += ["--pick"] + args.pick

    print("=== 1/3 过电位分析 ===")
    lsv_analysis.main(analysis_args)

    if not args.skip_plot:
        print("\n=== 2/3 样品图 ===")
        lsv_plot.main(plot_args)

    if not args.skip_compare:
        print("\n=== 3/3 对比图 ===")
        lsv_compare.main(compare_args)

    print("\n全部完成，输出目录：%s" % output_dir)


if __name__ == "__main__":
    main()