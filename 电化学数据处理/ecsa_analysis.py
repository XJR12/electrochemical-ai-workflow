#!/usr/bin/env python3
"""ECSA/Cdl selection phase: parse CV txt files, split full cycles, score them.

The ECSA workflow intentionally mirrors the LSV pipeline:
    raw txt  -> auto analysis/selection -> (manual --pick if ambiguous)
             -> ecsa_best.csv / ecsa_per_file.csv

Scan-rate is read from the filename, e.g. "2MV_C01.txt" and "2MV-2_C01.txt"
are both treated as 2 mV/s (the "-2" part is only a repeat marker).

Usage:
    python ecsa_analysis.py --input-dir <parent folder with sample subfolders>
    python ecsa_analysis.py --input-dir <folder> --output-dir result
    python ecsa_analysis.py --input-dir <folder> --pick "样品名=2MV_C01.txt#2"
"""

import argparse
import csv
import math
import os
import re
import sys

import numpy as np
import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from lsv_analysis import read_lsv

SCAN_RATE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*m\s*v", re.IGNORECASE)

SELECTION_LABEL = {"auto": "自动", "manual": "手动", "picked": "指定"}

PER_FILE_HEADER = [
    "样品",
    "文件",
    "扫速/(mV/s)",
    "圈号",
    "升支点数",
    "降支点数",
    "E范围/V",
    "闭合度",
    "支路对称度",
    "平滑度",
    "稳定性",
    "质量分",
]

BEST_HEADER = ["样品", "扫速/(mV/s)", "文件", "圈号", "质量分", "选择方式"]


def detect_scan_rate(path):
    """Return the numeric scan rate from a filename such as 2MV-2_C01.txt."""
    stem = os.path.splitext(os.path.basename(path))[0]
    m = SCAN_RATE_RE.search(stem)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _signs_of_potential(E):
    """Turning indices (local extrema) of a potential-time sequence."""
    tol = 1e-7
    dE = np.diff(E)
    prev = 0
    turns = []
    for idx, step in enumerate(dE):
        if step > tol:
            sign = 1
        elif step < -tol:
            sign = -1
        else:
            continue
        if prev != 0 and sign != prev:
            turns.append(idx)
        prev = sign
    return turns


def _smoothness(j):
    """Score 0..1 for how free of isolated spikes a branch is."""
    j = np.asarray(j, dtype=float)
    if j.size < 2:
        return 0.0
    d = np.abs(np.diff(j))
    med = float(np.median(d)) if d.size else 0.0
    if med <= 0.0:
        if float(np.max(d)) <= 0.0:
            return 1.0
        med = max(float(np.max(d)) / 15.0, 1e-12)
    threshold = med * 15.0
    spikes = int(np.sum(d > threshold))
    return max(0.0, 1.0 - spikes / float(len(d)))


def _branch_extent(E, j):
    return float(np.max(E) - np.min(E)), list(E), list(j)


def _cycle_distance(c1, c2):
    """Mean absolute current difference between two loops over shared E."""
    e1 = np.asarray(c1["E_all"], dtype=float)
    e2 = np.asarray(c2["E_all"], dtype=float)
    low = max(float(np.min(e1)), float(np.min(e2)))
    high = min(float(np.max(e1)), float(np.max(e2)))
    if high - low < 1e-9:
        return None
    grid = np.linspace(low, high, 80)
    j1 = np.interp(grid, e1, np.asarray(c1["j_all"], dtype=float))
    j2 = np.interp(grid, e2, np.asarray(c2["j_all"], dtype=float))
    scale = float(np.mean(np.abs(j1) + np.abs(j2)))
    if scale <= 0.0:
        return 0.0
    return float(np.mean(np.abs(j1 - j2))) / scale


def extract_cycles(E, I, j, min_range_ratio=0.85):
    """Split one parsed CV file into complete cycles.

    A "complete cycle" is two consecutive potential half sweeps in opposite
    directions between turning points. Returns a list of cycle dicts with
    up/down branches, ordered point arrays and a 0..1 raw quality score.
    """
    E = np.asarray(E, dtype=float)
    j = np.asarray(j, dtype=float)
    if E.size < 4 or j.size != E.size:
        return []

    full_low = float(np.min(E))
    full_high = float(np.max(E))
    full_span = full_high - full_low
    if full_span <= 0.0:
        return []

    raw_turns = _signs_of_potential(E)
    seq = [0]
    for t in raw_turns:
        if t > seq[-1]:
            seq.append(t)
    if E.size - 1 > seq[-1]:
        seq.append(int(E.size - 1))

    cycles = []
    for k in range(0, len(seq) - 2, 2):
        i0, i1, i2 = seq[k], seq[k + 1], seq[k + 2]
        seg_e = E[i0 : i2 + 1]
        seg_j = j[i0 : i2 + 1]
        span = float(np.max(seg_e) - np.min(seg_e))
        if span / full_span < min_range_ratio:
            continue

        b1_e = E[i0 : i1 + 1]
        b2_e = E[i1 : i2 + 1]
        if len(b1_e) < 3 or len(b2_e) < 3:
            continue

        b1_j = j[i0 : i1 + 1]
        b2_j = j[i1 : i2 + 1]
        first_up = float(b1_e[-1] - b1_e[0]) > 0.0

        if first_up:
            up = (list(b1_e), list(b1_j))
            down = (list(b2_e[1:]), list(b2_j[1:]))
            up_e, down_e = list(b1_e), list(b2_e[1:])
            up_j, down_j = list(b1_j), list(b2_j[1:])
        else:
            up = (list(b2_e[1:]), list(b2_j[1:]))
            down = (list(b1_e), list(b1_j))
            up_e, up_j = list(b2_e[1:]), list(b2_j[1:])
            down_e, down_j = list(b1_e), list(b1_j)

        up_span, _, _ = _branch_extent(*up) if up[0] else (0.0, [], [])
        down_span, _, _ = _branch_extent(*down) if down[0] else (0.0, [], [])
        extent_ratio = 1.0 - min(1.0, abs(up_span - down_span) / max(span, 1e-9))
        closure = 1.0 - min(1.0, abs(float(seg_e[0] - seg_e[-1])) / max(span, 1e-9))
        smooth = min(
            _smoothness(up_j) if up_j else 0.0,
            _smoothness(down_j) if down_j else 0.0,
        )

        cycles.append({
            "cycle_no": len(cycles) + 1,
            "span": span,
            "closure": closure,
            "extent_ratio": extent_ratio,
            "smoothness": smooth,
            "stability": 1.0,
            "score": None,
            "up_e": up_e,
            "up_j": up_j,
            "down_e": down_e,
            "down_j": down_j,
            "E_all": [float(x) for x in seg_e],
            "j_all": [float(x) for x in seg_j],
        })

    for idx, cycle in enumerate(cycles):
        neighbor = None
        if idx + 1 < len(cycles):
            neighbor = cycles[idx + 1]
        elif idx > 0:
            neighbor = cycles[idx - 1]
        if neighbor is not None:
            dist = _cycle_distance(cycle, neighbor)
            if dist is not None:
                cycle["stability"] = max(0.0, 1.0 - dist)

    for cycle in cycles:
        cycle["score"] = (
            0.30 * cycle["closure"]
            + 0.20 * cycle["extent_ratio"]
            + 0.25 * cycle["smoothness"]
            + 0.25 * cycle["stability"]
        )
        # Slight preference for the stable tail of a file when all else is equal.
        cycle["score"] = min(1.0, cycle["score"] + 0.001 * max(0, cycle["cycle_no"] - 1))
    return cycles


def parse_cv_file(path, area):
    """Parse one file and convert current to j (mA/cm2)."""
    E, I, is_density = read_lsv(path)
    if len(E) < 4:
        return None, None
    j = I if is_density else [v / area for v in I]
    cycles = extract_cycles(E, I, j)
    return (E, j), cycles


def analyze_file(path, area):
    """Return (meta, cycle list) for one txt file."""
    meta = {
        "path": path,
        "folder": os.path.basename(os.path.dirname(path)),
        "file": os.path.basename(path),
        "scan_rate": detect_scan_rate(path),
    }
    if meta["scan_rate"] is None:
        return meta, []
    _, cycles = parse_cv_file(path, area)
    return meta, cycles


def find_cycle(path, area, cycle_no):
    """Return the cycle dict matching cycle_no, or None."""
    meta, cycles = analyze_file(path, area)
    for cycle in cycles:
        if cycle["cycle_no"] == cycle_no:
            return cycle
    return None


def scan_txt(input_dir):
    paths = []
    for root, _, names in os.walk(input_dir):
        for name in sorted(names):
            if name.lower().endswith(".txt"):
                paths.append(os.path.join(root, name))
    return sorted(paths)


def format_float(value, width="%.4f"):
    return width % value if value is not None else ""


def write_per_file_csv(output_dir, rows):
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "ecsa_per_file.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(PER_FILE_HEADER)
        for row in rows:
            writer.writerow([
                row["folder"],
                row["file"],
                "%.0f" % row["scan_rate"],
                row["cycle_no"],
                len(row["up_e"]),
                len(row["down_e"]),
                "%.6g" % row["span"],
                "%.4f" % row["closure"],
                "%.4f" % row["extent_ratio"],
                "%.4f" % row["smoothness"],
                "%.4f" % row["stability"],
                "%.4f" % row["score"],
            ])
    return path


def parse_picks(pick_args):
    """List of (sample_lower, filename_lower, cycle_no|None) picks."""
    out = []
    for item in pick_args or []:
        if "=" not in item:
            continue
        sample, ref = item.split("=", 1)
        ref = ref.strip()
        cycle_no = None
        if "#" in ref:
            ref, cycle_part = ref.rsplit("#", 1)
            try:
                cycle_no = int(cycle_part)
            except ValueError:
                cycle_no = None
        out.append((sample.strip().lower(), ref.strip().lower(), cycle_no))
    return out


def pick_candidate(candidates, sample_lower, picks):
    """Try to resolve a group from --pick; returns (cycle, picked_bool)."""
    for sample, filename, cycle_no in picks:
        if sample != sample_lower:
            continue
        matches = [c for c in candidates if c["file"].lower() == filename]
        if not matches:
            continue
        if cycle_no is None:
            best = sorted(matches, key=lambda c: c["score"], reverse=True)[0]
            return best, True
        for c in matches:
            if c["cycle_no"] == cycle_no:
                return c, True
    return None, False


def write_best_csv(output_dir, best_rows):
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "ecsa_best.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(BEST_HEADER)
        for row in best_rows:
            writer.writerow([
                row["folder"],
                "%.0f" % row["scan_rate"],
                row["file"],
                row["cycle_no"],
                "%.4f" % row["score"],
                SELECTION_LABEL.get(row["selection"], "自动"),
            ])
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description="ECSA/Cdl CV 回线解析与自动选择")
    parser.add_argument("--input-dir", help="父目录：每个子文件夹为一个样品")
    parser.add_argument("--output-dir", required=True, help="输出 ecsa_per_file.csv / ecsa_best.csv 的目录")
    parser.add_argument("--config", default=os.path.join(SCRIPT_DIR, "config.yaml"))
    parser.add_argument("--area", type=float, default=None, help="电极面积 cm2，默认读 config.yaml")
    parser.add_argument("--score-gap", type=float, default=None, help="自动选择的质量分差距阈值")
    parser.add_argument("--max-manual-candidates", type=int, default=None)
    parser.add_argument("--pick", action="append", default=[], help='样品名=文件名#圈号，可重复')
    args = parser.parse_args(argv)

    if not args.input_dir:
        parser.error("需要 --input-dir")
    input_dir = os.path.abspath(args.input_dir)
    output_dir = os.path.abspath(args.output_dir)

    cfg = {}
    if os.path.exists(args.config):
        with open(args.config, "r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
    if args.area is None:
        args.area = float(cfg.get("area", 1.0))
    ecsa_cfg = cfg.get("ecsa") or {}
    if args.score_gap is None:
        args.score_gap = float(ecsa_cfg.get("score_gap", 0.002))
    if args.max_manual_candidates is None:
        args.max_manual_candidates = int(ecsa_cfg.get("max_manual_candidates", 3))

    paths = scan_txt(input_dir)
    if not paths:
        parser.error("没有找到 txt 文件")

    all_rows = []
    unknown = []
    for p in paths:
        meta, cycles = analyze_file(p, args.area)
        if meta["scan_rate"] is None:
            unknown.append(p)
            continue
        for cycle in cycles:
            row = dict(meta)
            row.update(cycle)
            all_rows.append(row)

    groups = {}
    for row in all_rows:
        groups.setdefault((row["folder"], row["scan_rate"]), []).append(row)

    if not groups:
        print("\n没有识别到任何可用的完整 CV 回线。请检查 txt 是否包含完整往返扫描。")
        return 1

    pick_map = parse_picks(args.pick)
    best_rows = []
    has_manual = False

    if all_rows:
        print("=== 逐文件完整回线 ===")
        for row in sorted(all_rows, key=lambda r: (r["folder"], r["scan_rate"], r["file"], r["cycle_no"])):
            print("%s | %s | %.0f mV/s | 第%d圈 | score=%.4f" % (
                row["folder"], row["file"], row["scan_rate"], row["cycle_no"], row["score"]))

    print("\n=== 每样品×扫速选择 ===")
    for (folder, rate) in sorted(groups):
        candidates = sorted(groups[(folder, rate)], key=lambda c: c["score"], reverse=True)
        chosen, picked = pick_candidate(candidates, folder.lower(), pick_map)
        ambiguous = len(candidates) >= 2 and candidates[0]["score"] - candidates[1]["score"] < args.score_gap

        if chosen is not None:
            chosen["selection"] = "picked"
            best_rows.append(chosen)
            print("%s | %.0f mV/s -> %s#%d（指定）" % (
                folder, rate, chosen["file"], chosen["cycle_no"]))
            continue

        if ambiguous:
            top = candidates[: args.max_manual_candidates]
            print("%s | %.0f mV/s：候选圈质量接近，需人工确认" % (folder, rate))
            for c in top:
                print("  候选：%s#%d | score=%.4f | E范围=%.4g" % (
                    c["file"], c["cycle_no"], c["score"], c["span"]))
            for c in top:
                c["selection"] = "manual"
                best_rows.append(c)
            has_manual = True
            continue

        chosen = candidates[0]
        chosen["selection"] = "auto"
        best_rows.append(chosen)
        print("%s | %.0f mV/s -> %s#%d（自动，score=%.4f）" % (
            folder, rate, chosen["file"], chosen["cycle_no"], chosen["score"]))

    per_path = write_per_file_csv(output_dir, all_rows)
    best_path = write_best_csv(output_dir, best_rows)
    print("\nCSV 已写入：%s" % per_path)
    print("选择结果：%s" % best_path)

    note_lines = []
    if unknown:
        note_lines.append("无法从文件名识别扫速的文件（已跳过）：")
        note_lines.extend(unknown)
    if note_lines:
        with open(os.path.join(output_dir, "选择说明.txt"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(note_lines) + "\n")

    if has_manual:
        print("\n存在手动候选。请用 --pick \"样品名=文件名#圈号\" 指定后重跑。")
        return 1
    print("\n说明：文件中的 MV 按 mV/s 处理，电流已按面积=%.4g cm2 换算。" % args.area)
    return 0


if __name__ == "__main__":
    sys.exit(main())
