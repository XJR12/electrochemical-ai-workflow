#!/usr/bin/env python3
"""Parse BioLogic EC-Lab LSV files and report overpotential at target currents.

Reads LSV text files (potential in V, current in mA), takes the forward
(monotonically increasing potential) sweep, and finds the potential where
the current density crosses each target value using linear interpolation.

Repeated measurements of the same sample/condition are grouped by parent
folder and by whether the filename starts with IR. The best curve is
auto-selected by the lowest eta at the first target, unless the gap to the
second-best curve is larger than --eta10-gap (then all candidates are listed
and the user should choose with --pick).

Usage:
    python lsv_analysis.py file1.txt file2.txt ...
    python lsv_analysis.py --input-dir <folder>
    python lsv_analysis.py <files> --area 1.0 --output-dir result
    python lsv_analysis.py <files> --pick 4-LSV_C01.txt
"""

import argparse
import csv
import math
import os
import sys


def parse_number(text):
    text = text.strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def read_lsv(path):
    """Read an EC-Lab style LSV file.

    Returns (E list, I list in mA, current_is_density).
    """
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()

    e_col = 0
    i_col = 1
    current_in_mA = True
    current_is_density = False
    data_start = 0

    for idx, line in enumerate(lines[:20]):
        parts = line.split()
        if len(parts) < 2:
            continue
        joined = line.lower()
        if "ewe" not in joined and "potential" not in joined and "current" not in joined and "<i>" not in joined and "i/" not in joined:
            continue
        for ci, part in enumerate(parts):
            pl = part.lower()
            if "ewe" in pl or "potenti" in pl or pl.startswith("e/"):
                e_col = ci
            if "<i>" in pl or "current" in pl or pl.startswith("i/") or pl.startswith("i("):
                i_col = ci
                if "ma" in pl:
                    current_in_mA = True
                    current_is_density = ("/cm" in pl or "cm-2" in pl or "cm2" in pl)
                elif "/a" in pl or pl == "<i>":
                    current_in_mA = False
        data_start = idx + 1
        break

    E = []
    I = []
    for line in lines[data_start:]:
        parts = line.split()
        if len(parts) <= max(e_col, i_col):
            continue
        e = parse_number(parts[e_col])
        i = parse_number(parts[i_col])
        if e is None or i is None:
            continue
        E.append(e)
        I.append(i)

    if not current_in_mA:
        I = [v * 1000.0 for v in I]
    return E, I, current_is_density


def clean_forward_sweep(E, I, e_min=1.3):
    """Keep only the forward sweep: drop pre-scan idle points below e_min,
    then start at the minimum remaining potential and keep strictly increasing E."""
    if not E:
        return [], []
    E0 = []
    I0 = []
    for e, i in zip(E, I):
        if e >= e_min:
            E0.append(e)
            I0.append(i)
    if not E0:
        return [], []
    start = min(range(len(E0)), key=lambda k: E0[k])
    E2 = []
    I2 = []
    last = -math.inf
    for e, i in zip(E0[start:], I0[start:]):
        if e > last:
            E2.append(e)
            I2.append(i)
            last = e
    return E2, I2


def potential_at_current(E, j, target):
    """Linear interpolation of E where current density j first rises across target.

    Only a rising pair (previous below/equal, current at/above) is accepted,
    so a pre-scan transient that starts above the target is skipped.
    """
    if len(E) < 2:
        return None
    for k in range(1, len(E)):
        if j[k - 1] <= target <= j[k]:
            j0 = j[k - 1]
            j1 = j[k]
            if j0 == target:
                return E[k - 1]
            if j1 == j0:
                return E[k]
            ratio = (target - j0) / (j1 - j0)
            return E[k - 1] + ratio * (E[k] - E[k - 1])
    return None


def group_kind(path):
    stem = os.path.splitext(os.path.basename(path))[0].lower()
    if stem.startswith("ir") or "-ir" in stem or "_ir" in stem:
        return "ir"
    return "raw"


def best_score(res, targets):
    for t in targets:
        e = res["targets"].get(t)
        if e is not None:
            return e
    return None


def format_float(value):
    return "%.4f" % value if value is not None else "无"


def eta_mv(e, rhe):
    return None if e is None else (e - rhe) * 1000.0


KIND_LABEL = {"raw": "直接测", "ir": "iR补偿"}
SELECTION_LABEL = {"auto": "自动", "manual": "手动", "picked": "指定"}


def dominates(a, b):
    """True if curve a is strictly better than b in eta10/eta100 (lower is better)."""
    def cmp(x, y):
        if x is None and y is None:
            return 0
        if x is None:
            return 1
        if y is None:
            return -1
        if x < y:
            return -1
        if x > y:
            return 1
        return 0
    r10 = cmp(a["eta10"], b["eta10"])
    r100 = cmp(a["eta100"], b["eta100"])
    return (r10 <= 0 and r100 <= 0) and (r10 < 0 or r100 < 0)


def write_summary_md(output_dir, best_rows, targets, rhe):
    by_folder = {}
    for r in best_rows:
        if r.get("selection") in ("auto", "picked"):
            by_folder.setdefault(r["folder"], {})[r["kind"]] = r
    lines = [
        "| 样品 | LSV（η10/η100） | iR后（η10/η100） |",
        "| --- | --- | --- |",
    ]
    for folder in sorted(by_folder):
        def cell(kind):
            r = by_folder[folder].get(kind)
            if r is None:
                return "-"
            e10 = eta_mv(r["targets"].get(targets[0]), rhe)
            e100 = eta_mv(r["targets"].get(targets[1]), rhe)
            return "%s / %s" % (
                "-" if e10 is None else ("%.1f" % e10),
                "-" if e100 is None else ("%.1f" % e100),
            )
        lines.append("| %s | %s | %s |" % (folder, cell("raw"), cell("ir")))
    md_path = os.path.join(output_dir, "数据对比.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("已生成：%s" % md_path)


def main(argv=None):
    parser = argparse.ArgumentParser(description="LSV 过电位自动识别")
    parser.add_argument("files", nargs="*", help="LSV txt 文件")
    parser.add_argument("--input-dir", help="递归扫描该目录下的 *.txt")
    parser.add_argument("--area", type=float, default=1.0, help="电极面积 cm2（默认 1.0）")
    parser.add_argument("--rhe", type=float, default=1.23, help="RHE 基准电位（默认 1.23）")
    parser.add_argument("--targets", nargs="+", type=float, default=[10.0, 100.0], help="目标电流密度 mA/cm2")
    parser.add_argument("--output-dir", help="输出 CSV 的目录")
    parser.add_argument("--no-best", action="store_true", help="跳过最优曲线选择")
    parser.add_argument("--pick", nargs="+", default=[], help="目录=文件名，可指定多个")
    parser.add_argument("--eta10-gap", type=float, default=5.0, help="eta10 与次优差距超过该值（mV）时不自动选")
    parser.add_argument("--sanity-mv", type=float, default=0.0, help="过电位低于该值（mV）视为异常曲线")
    args = parser.parse_args(argv)

    if args.input_dir:
        args.input_dir = os.path.abspath(args.input_dir)
    if args.output_dir:
        args.output_dir = os.path.abspath(args.output_dir)

    paths = [os.path.abspath(p) for p in args.files]
    if args.input_dir:
        for root, _, names in os.walk(args.input_dir):
            for name in sorted(names):
                if name.lower().endswith(".txt"):
                    paths.append(os.path.join(root, name))

    if not paths:
        parser.error("没有输入文件")

    results = []
    for p in paths:
        E, I, is_density = read_lsv(p)
        E2, I2 = clean_forward_sweep(E, I)
        if len(E2) < 3:
            print("警告：跳过非数据文件：%s" % p)
            continue
        if is_density:
            j = I2
        else:
            j = [v / args.area for v in I2]

        targets = {}
        for t in args.targets:
            targets[t] = potential_at_current(E2, j, t)

        invalid = any(e is not None and (e - args.rhe) * 1000.0 < args.sanity_mv for e in targets.values())
        if invalid:
            print("警告：异常曲线（过电位低于 %s mV）：%s" % (format_float(args.sanity_mv), p))

        folder = os.path.basename(os.path.dirname(p))
        results.append({
            "path": p,
            "folder": folder,
            "kind": group_kind(p),
            "targets": targets,
            "max_j": max(j) if j else 0.0,
            "invalid": invalid,
            "eta10": None if targets[args.targets[0]] is None else (targets[args.targets[0]] - args.rhe) * 1000.0,
            "eta100": None if targets[args.targets[1]] is None else (targets[args.targets[1]] - args.rhe) * 1000.0,
        })

    results.sort(key=lambda r: (r["folder"], 0 if r["kind"] == "raw" else 1, os.path.basename(r["path"])))

    print("=== 逐文件结果 ===")
    header = ["目录", "文件", "类别", "备注"]
    for t in args.targets:
        header += ["电位%d/V" % t, "过电位%d/mV" % t]
    print("\t".join(header))
    for r in results:
        row = [r["folder"], os.path.basename(r["path"]), KIND_LABEL[r["kind"]], "异常" if r.get("invalid") else ""]
        for t in args.targets:
            e = r["targets"][t]
            row.append(format_float(e))
            row.append(format_float(eta_mv(e, args.rhe)))
        print("\t".join(row))

    if not args.no_best:
        print("\n=== 每组最优曲线 ===")
        groups = {}
        for r in results:
            groups.setdefault((r["folder"], r["kind"]), []).append(r)

        pick_map = {}
        for item in args.pick:
            if "=" in item:
                folder, filename = item.split("=", 1)
                pick_map[folder] = filename
        best_rows = []
        for key, group in groups.items():
            pool = [r for r in group if not r.get("invalid")]
            if not pool:
                pool = group
            scored = sorted(pool, key=lambda r: best_score(r, args.targets) if best_score(r, args.targets) is not None else 1e9)
            surviving = [c for c in scored if not any(dominates(o, c) for o in scored)]

            selected = None
            chosen_by_pick = False
            pick_name = pick_map.get(key[0])
            if pick_name:
                matches = [r for r in group if os.path.basename(r["path"]).lower() == pick_name.lower()]
                if matches:
                    selected = matches[0]
                    chosen_by_pick = True


            if selected is None and len(surviving) >= 2:
                print("%s / %s：存在 %d 条互有优劣的曲线，需人工确认" % (key[0], key[1], len(surviving)))
                for cand in surviving:
                    print("  候选：%s | η10=%s mV | η100=%s mV" % (
                        os.path.basename(cand["path"]),
                        format_float(eta_mv(cand["targets"].get(args.targets[0]), args.rhe)),
                        format_float(eta_mv(cand["targets"].get(args.targets[1]), args.rhe))))
                if key[0] not in pick_map:
                    print("  已在 CSV 中列出候选，请用 --pick <目录=文件名> 指定")
                for cand in surviving:
                    cand["selection"] = "manual"
                    best_rows.append(cand)
                continue

            if selected is None:
                selected = surviving[0] if surviving else scored[0]
            selected["selection"] = "picked" if chosen_by_pick else "auto"
            best_rows.append(selected)

            line = "%s / %s → %s" % (key[0], key[1], os.path.basename(selected["path"]))
            for t in args.targets:
                e = selected["targets"][t]
                line += " | 电位%d=%s V, 过电位%d=%s mV" % (t, format_float(e), t, format_float(eta_mv(e, args.rhe)))
            print(line)

        if args.output_dir:
            os.makedirs(args.output_dir, exist_ok=True)
            per_file_path = os.path.join(args.output_dir, "lsv_per_file.csv")
            with open(per_file_path, "w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.writer(fh)
                writer.writerow(header)
                for r in results:
                    row = [r["folder"], os.path.basename(r["path"]), KIND_LABEL[r["kind"]], "异常" if r.get("invalid") else ""]
                    for t in args.targets:
                        e = r["targets"][t]
                        row.append("" if e is None else ("%.4f" % e))
                        row.append("" if e is None else ("%.1f" % eta_mv(e, args.rhe)))
                    writer.writerow(row)

            best_path = os.path.join(args.output_dir, "lsv_best.csv")
            best_header = ["目录", "类别", "η10/mV", "η100/mV", "选择方式", "文件"]
            with open(best_path, "w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.writer(fh)
                writer.writerow(best_header)
                for r in best_rows:
                    e10 = eta_mv(r["targets"].get(args.targets[0]), args.rhe)
                    e100 = eta_mv(r["targets"].get(args.targets[1]), args.rhe)
                    row = [
                        r["folder"],
                        KIND_LABEL[r["kind"]],
                        "" if e10 is None else ("%.1f" % e10),
                        "" if e100 is None else ("%.1f" % e100),
                        SELECTION_LABEL.get(r.get("selection", "auto"), "自动"),
                        os.path.basename(r["path"]),
                    ]
                    writer.writerow(row)
            print("\nCSV 已写入 %s" % args.output_dir)

            has_manual = any(r.get("selection") == "manual" for r in best_rows)
            if has_manual:
                print("存在手动候选，请先指定后再重跑。")
                return 1
            write_summary_md(args.output_dir, best_rows, args.targets, args.rhe)

    print("\n说明：电流列按总电流处理，已除以面积=%.2f cm2。" % args.area)
    return 0


if __name__ == "__main__":
    sys.exit(main())
