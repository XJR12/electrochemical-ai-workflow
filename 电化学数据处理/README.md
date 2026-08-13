# 电化学数据处理

处理 LSV / CV 等数据，输出参数汇总与论文级图片。

## 已合并（2026-08-04）

过电位检测与画图两大部分已整合，主目录即最终版本：

- lsv_pipeline.py：一键入口，按顺序跑 分析 → 样品图 → 对比图。
- lsv_analysis.py：解析 BioLogic EC-Lab 格式 LSV，自动识别 η10/η100，输出中文 CSV（UTF-8 BOM）。
- lsv_plot.py：每个样品组一张直接测图、一张 iR 补偿图。
- lsv_compare.py：自动生成总对比图与按条件词分组的对比图，自动剔除极差样品。
- tafel_plot.py（2026-08-12）：用 iR 后 LSV 数据直接出 log10(j)-η 的 Tafel 图，支持 --files 与 --best-csv 两种入口。
- config.yaml：绘图与对比规则配置。

LSV/ 子目录是合并前的暂存版，保留作备份，确认新入口没问题后可删除。

## 一键用法

```powershell
python lsv_pipeline.py --input-dir "数据目录"
python lsv_pipeline.py --input-dir "数据目录" --pick "Ru-2mg=1-LSV_C01.txt"
```

流程：先做选择 → 有手动候选就停下等你指定（聊天里告诉 AI 即可，AI 内部用 --pick 重跑）→ 选择完成后再生成数据对比.md、样品图和对比图。

默认输出目录为 电化学数据处理\output\<输入目录名>_0；同一天重跑直接覆盖，被占用才自动用 _1、_2……

输出：

```text
output/260807_0/
├── lsv_per_file.csv     每条曲线结果
├── lsv_best.csv         选择结果（手动候选会并列列出）
├── 数据对比.md           样品 | LSV（η10/η100） | iR后（η10/η100）
├── 样品/                每个样品的直接测 / iR 图（所有重复曲线同图）
└── 对比图/              总图与分组对比图 + 选择说明.txt
```

## Tafel 模块（2026-08-12）

新增 `tafel_plot.py`，用 LSV 已测好的 iR 后数据直接出 Tafel 图：

- 横轴：`log10(j)`，`j = I / 面积`（默认面积 1.0 cm²，数据列本身是 mA）；
- 纵轴：过电位 `η = (E − 1.23) × 1000`（mV，`--rhe` 可调）；
- 只使用文件名以 `IR` 开头（或含 `-ir`/`_ir`）的 iR 曲线；
- 每个曲线出两版：全数据版（`j > 0`）和截取版（默认 `j ≥ 1 mA·cm⁻²`，可用 `--j-min`/`--j-max`/`--eta-min`/`--eta-max` 调整）；
- v1 不做斜率拟合。

前置步骤：`--best-csv` 用的 `lsv_best.csv` 由 LSV 流程生成，不是 Tafel 模块生成的。没有该文件时先跑 LSV 一键流程（内部由 `lsv_analysis.py` 写出 `lsv_best.csv`）：

```powershell
python lsv_pipeline.py --input-dir "数据目录" --output-dir "输出目录"
```

如果只想先得到 `lsv_best.csv`、暂不生成 LSV 样品图和对比图，加 `--skip-plot --skip-compare` 即可；也可以直接跑 `lsv_analysis.py`，它同样会写出 `lsv_best.csv`。

如果 LSV 流程出现手动候选并停止，先用 `--pick "目录=文件名"` 指定后再重跑；确认 `lsv_best.csv` 已生成、没有“手动”候选后，再执行下面的 Tafel 命令。直接指定 `--files` 时不需要 `lsv_best.csv`。

用法：

```powershell
# 直接指定 iR txt
python tafel_plot.py --files "数据目录\IR-1_02_LSV_C01.txt" --output-dir "输出目录"

# 读取 LSV 已选好的 lsv_best.csv
python tafel_plot.py --input-dir "数据目录" --best-csv "输出目录\lsv_best.csv" --output-dir "输出目录\tafel"
```

输出：

```text
tafel/
├── tafel_per_file.csv      每条 iR 曲线的 η/j/log10(j) 范围
├── tafel_points.csv        转换后的逐点数据
├── Tafel数据对比.md
├── 样品/                   Tafel-<样品>.png 和 Tafel-<样品>-截取.png
└── 对比图/                 总图与分组对比图（best-csv 模式）
```

## 规则摘要

- 扫描起点：舍弃 1.3 V 及之前的数据（初始化段）；η10 取电流密度首次从低于 10 上升到高于 10 的相邻两点插值，开头瞬态高电流不再误判为“无 η10”。
- 选线：优先支配判定，一条曲线 η10、η100 都更优则直接胜出；仅真正互有优劣的曲线列为“手动”候选。
- 画图：x 轴 1.4 V 起，终点自动收；大分度 0.05、小分度 0.025 不标数字；坐标标题加粗；600 dpi。
- 对比：自动按目录名中的 - 和空格拆词分组；η10 比组内中位数高 100 mV 以上自动剔除；多数达到 100 时 y 轴 0-100，否则 0-10。
- 输出目录被占用（如 CSV 正被 Excel/WPS 打开）时，lsv_pipeline.py 会自动改用 `<原目录>_新` 重跑，不会中断；平时请先关闭占用的文件。

## 依赖

- 依赖见 电化学数据处理/requirements.txt；在 电化学数据处理 目录运行 `.\安装依赖.ps1`（可传 `-Python` 指定解释器）安装。
- 如果 Codex 运行时更新导致 matplotlib 等消失，重跑安装脚本即可。
