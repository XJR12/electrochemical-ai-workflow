# 电化学数据处理

处理 LSV / CV 等数据，输出参数汇总与论文级图片。

## 已合并（2026-08-04）

过电位检测与画图两大部分已整合，主目录即最终版本：

- lsv_pipeline.py：一键入口，按顺序跑 分析 → 样品图 → 对比图。
- lsv_analysis.py：解析 BioLogic EC-Lab 格式 LSV，自动识别 η10/η100，输出中文 CSV（UTF-8 BOM）。
- lsv_plot.py：每个样品组一张直接测图、一张 iR 补偿图。
- lsv_compare.py：自动生成总对比图与按条件词分组的对比图，自动剔除极差样品。
- config.yaml：绘图与对比规则配置。

LSV/ 子目录是合并前的暂存版，保留作备份，确认新入口没问题后可删除。

## 一键用法

```powershell
python lsv_pipeline.py --input-dir "数据目录"
python lsv_pipeline.py --input-dir "数据目录" --pick "3% low 1mg=2-LSV_C01.txt" --skip-compare
```

输出：

```text
output/
├── lsv_per_file.csv     每条曲线结果
├── lsv_best.csv         每组最优曲线
├── figures/             样品图（直接测 / iR）
└── 对比图/              总图与分组对比图 + 选择说明.txt
```

## 规则摘要

- 选线：η10 差距 ≤5 mV 的候选里优先选 η100 最低；差距大则标记“手动”并用 --pick 指定。
- 画图：x 轴 1.4 V 起，终点自动收；大分度 0.05、小分度 0.025 不标数字；坐标标题加粗；600 dpi。
- 对比：自动按目录名空格拆词分组；η10 比组内中位数高 100 mV 以上自动剔除；多数达到 100 时 y 轴 0-100，否则 0-10。

## 依赖

matplotlib、PyYAML（已装入本机 bundled Python）。