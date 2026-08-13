# 电化学数据处理

处理 BioLogic EC-Lab 导出的 LSV / Tafel 数据，输出参数汇总与论文级图片。

## 两种使用方式

- 一键版（日常推荐）：双击 `一键LSV.bat`（只要 LSV）或 `一键LSV+Tafel.bat`（LSV 后再出 Tafel），不需要记命令。
- 命令行版：使用 `lsv_pipeline.py`、`lsv_analysis.py`、`lsv_plot.py`、`lsv_compare.py`、`tafel_plot.py`。

## 模块说明

过电位检测、画图和 Tafel 已整合到主目录：

- `lsv_pipeline.py`：一键入口，按顺序跑 分析 → 样品图 → 对比图。
- `lsv_analysis.py`：解析 BioLogic EC-Lab 格式 LSV，自动识别 η10/η100，输出中文 CSV（UTF-8 BOM）。
- `lsv_plot.py`：每个样品组一张直接测图、一张 iR 补偿图。
- `lsv_compare.py`：自动生成总对比图与按条件词分组的对比图，自动剔除极差样品。
- `tafel_plot.py`：用 iR 后 LSV 数据直接出 `log10(j)-η` 的 Tafel 图，支持 `--files` 与 `--best-csv` 两种入口。
- `config.yaml`：绘图、对比、电极面积等规则配置。



## 数据要这样放

把同一天、同一批测试放在一个父文件夹里，父文件夹下面每个样品一个子文件夹：

```text
260812/
├── Ru-1mg-0807/
│   ├── 1-LSV_C01.txt           直接测数据
│   ├── 2-LSV_C01.txt           同一样品的重复曲线
│   ├── IR-1_02_LSV_C01.txt     iR 补偿数据，文件名以 IR 开头
│   └── IR-2_02_LSV_C01.txt
├── 4.5%-1mg-0807/
│   ├── 1-LSV_C01.txt
│   └── IR-1_02_LSV_C01.txt
└── 3%-1g-0802/
    └── ...
```

规则：

- 父文件夹名字可以随便起，输出目录会用它命名，例如 `260812_0`。
- 子文件夹名就是样品名，也会作为图例名。
- 文件名以 `IR` 开头，或包含 `-ir`、`_ir`，会被识别为 iR 后数据；其他文件按直接测处理。
- 每个样品可以放多条重复曲线，程序会自动挑最优；只有互有优劣时才会请你人工选择。
- 程序会递归扫描子文件夹，不要求所有 txt 都放在同一层。

## 第一次使用 / 安装依赖

1. 安装 Python（[python.org](https://www.python.org/downloads/)），安装时勾选 **Add python.exe to PATH**。
2. 双击 `安装依赖.bat`，等窗口显示“依赖安装完成”或“依赖已安装到 py_deps”。这一步只需要做一次。
3. 如果窗口提示找不到 `python`，说明第 1 步没勾选 PATH，重新安装一次 Python 即可。

也可以手动运行 `.\install-deps.ps1 -Python <python路径>`。依赖清单在 `requirements.txt`；如果全局安装因为权限失败，安装脚本会自动把依赖装到本项目内的 `py_deps` 文件夹，不影响使用。如果 Codex 运行时更新导致 matplotlib 等消失，重跑安装脚本即可。

## 日常使用（一键版）

### 只要 LSV 结果和 LSV 图

双击 `一键LSV.bat`，然后：

1. 把数据父文件夹拖到黑色窗口里，按回车；也可以直接粘贴完整路径。
2. 电极面积不用输入，默认读 `config.yaml` 的 `area`（默认 `1.0 cm²`）。
3. 等待程序自动完成。正常结束时窗口会显示输出目录。

### 要 LSV 结果，还要 Tafel 图

双击 `一键LSV+Tafel.bat`，操作和上面一样。程序会先完成 LSV，再自动用选好的 iR 曲线生成 Tafel 图。

### 如果程序停下来问“人工选择”

这种情况只说明某个样品有几条重复曲线互有优劣，程序不能自动判断。窗口会一次只列一组候选（一个样品 + 直接测/iR 其中一类），你只需要回答两样之一：

- 编号，例如 `1`、`2`、`3`
- 纯文件名，例如 `4-LSV_C01.txt`

如果多个样品都需要人工选择，窗口会一组一组继续问，每组回答一次即可，不用一次输入所有选择。

```text
样品：3%-1g-0802（直接测）
  [1] 4-LSV_C01.txt（η10=259.0 mV，η100=497.1 mV）
  [2] 3-LSV_C01.txt（η10=260.7 mV，η100=495.7 mV）
  [3] 2-LSV_C01.txt（η10=262.6 mV，η100=493.9 mV）
请输入要保留的文件名或编号：4-LSV_C01.txt
```



## 命令行用法

### LSV 一键流程

```powershell
python lsv_pipeline.py --input-dir "数据目录"
python lsv_pipeline.py --input-dir "数据目录" --pick "Ru-2mg=1-LSV_C01.txt"
```

多个手动候选可重复使用 `--pick`；需要区分直接测/iR 时用 `目录#类别=文件名`，例如：

```powershell
python lsv_pipeline.py --input-dir "数据目录" --pick "3%-1g-0802#直接测=4-LSV_C01.txt" --pick "4.5%-1mg-0807#iR补偿=IR-2_02_LSV_C01.txt"
```

流程：先做选择 → 有手动候选就停下等你指定（聊天里告诉 AI 即可，AI 内部用 `--pick` 重跑）→ 选择完成后再生成 `数据对比.md`、样品图和对比图。

如果只想先得到 `lsv_best.csv`、暂不生成 LSV 样品图和对比图，加 `--skip-plot --skip-compare` 即可；也可以直接跑 `lsv_analysis.py`，它同样会写出 `lsv_best.csv`。

### Tafel 模块

用 LSV 已测好的 iR 后数据直接出 Tafel 图：

- 横轴：`log10(j)`，`j = I / 面积`（默认面积 1.0 cm²，数据列本身是 mA）；
- 纵轴：过电位 `η = (E − 1.23) × 1000`（mV，`--rhe` 可调）；
- 只使用文件名以 `IR` 开头（或含 `-ir`/`_ir`）的 iR 曲线；
- 每个曲线出两版：全数据版（`j > 0`）和截取版（默认 `j ≥ 1 mA·cm⁻²`，可用 `--j-min`/`--j-max`/`--eta-min`/`--eta-max` 调整）；
- v1 不做斜率拟合。

前置步骤：`--best-csv` 用的 `lsv_best.csv` 由 LSV 流程生成，不是 Tafel 模块生成的。没有该文件时先跑 LSV 一键流程：

```powershell
python lsv_pipeline.py --input-dir "数据目录" --output-dir "输出目录"
```

如果 LSV 流程出现手动候选并停止，先用 `--pick "目录=文件名"` 指定后再重跑；确认 `lsv_best.csv` 已生成、没有“手动”候选后，再执行下面的 Tafel 命令。直接指定 `--files` 时不需要 `lsv_best.csv`。

```powershell
# 直接指定 iR txt
python tafel_plot.py --files "数据目录\IR-1_02_LSV_C01.txt" --output-dir "输出目录"

# 读取 LSV 已选好的 lsv_best.csv
python tafel_plot.py --input-dir "数据目录" --best-csv "输出目录\lsv_best.csv" --output-dir "输出目录\tafel"
```

## 输出目录

默认输出在 `output\<数据父文件夹名>_0`，例如：

```text
output/260812_0/
├── lsv_per_file.csv     每条曲线结果
├── lsv_best.csv         选择结果（手动候选会并列列出）
├── 数据对比.md           样品 | LSV（η10/η100） | iR后（η10/η100）
├── 样品/                每个样品的直接测 / iR 图（所有重复曲线同图）
├── 对比图/              总图与分组对比图 + 选择说明.txt
└── tafel/               使用“LSV+Tafel”入口时生成
```

Tafel 单独输出的文件：

```text
tafel/
├── tafel_per_file.csv      每条 iR 曲线的 η/j/log10(j) 范围
├── tafel_points.csv        转换后的逐点数据
├── Tafel数据对比.md
├── 样品/                   Tafel-<样品>.png 和 Tafel-<样品>-截取.png
└── 对比图/                 总图与分组对比图（best-csv 模式）
```

如果 `output` 里的文件正被 Excel/WPS 打开导致写入失败，程序会自动改用 `_1`、`_2` 继续，不会中断。平时先关闭占用的文件即可。

## 进阶设置

电极面积写在 `config.yaml` 的 `area` 字段，默认 `1.0 cm²`，一键入口不再询问；如果不是 `1.0`，改这里即可。

其余默认规则也都写在 `config.yaml` 里：RHE 基准按 `1.23 V` 算，目标电流密度是 `10` 和 `100 mA·cm⁻²`，Tafel 截取版默认从 `j ≥ 1 mA·cm⁻²` 开始。需要调整时可以打开 `config.yaml` 修改对应数值。

## 规则摘要

- 扫描起点：舍弃 1.3 V 及之前的数据（初始化段）；η10 取电流密度首次从低于 10 上升到高于 10 的相邻两点插值，开头瞬态高电流不再误判为“无 η10”。
- 选线：优先支配判定，一条曲线 η10、η100 都更优则直接胜出；仅真正互有优劣的曲线列为“手动”候选。
- 画图：x 轴 1.4 V 起，终点自动收；大分度 0.05、小分度 0.025 不标数字；坐标标题加粗；600 dpi。
- 对比：自动按目录名中的 `-` 和空格拆词分组；η10 比组内中位数高 100 mV 以上自动剔除；多数达到 100 时 y 轴 0-100，否则 0-10。
- 输出目录被占用（如 CSV 正被 Excel/WPS 打开）时，`lsv_pipeline.py` 会自动改用 `<原目录>_新` 重跑，不会中断；平时请先关闭占用的文件。

## 常见问题

### 输出图是空白的？

先确认 txt 文件第一行是否包含电位和电流两列（例如 `Ewe/V` 和 `<I>/mA`）。如果数据文件是其他电化学工作站格式，需要先转换成这个格式。

### 结果目录名带 `_1`、`_2`？

说明 `_0` 目录里有文件正被打开或被占用。关掉相关 Excel/WPS/图片查看器后重新运行即可，也可以直接使用自动生成的 `_1` 目录。
