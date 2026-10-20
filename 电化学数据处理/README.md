# 电化学数据处理

处理电化学工作站导出的 LSV / Tafel 数据，输出参数汇总与论文级图片。目前支持：

- BioLogic EC-Lab：`Ewe/V  <I>/mA`（制表符分隔）。
- CHI760E / CHI 系列：`Potential/V, Current/A`（逗号分隔，前面可能有一大段测试信息）。

读取时会自动跳过前导测试信息、识别逗号/制表符/空格分隔、识别电流单位（A / mA / µA）；“只画图”入口还会自动判断升扫或降扫，不需要手工改文件。

## 三个入口

- `一键LSV画图.bat`（最快）：只读取并画图，每个 txt 一张，不选线、不做对比。适合“一个文件夹里一堆 txt”的情况。
- `选线+LSV画图.bat`：原来的完整流程：选线 → 样品图 → 对比图。
- `选线+LSV画图+Tafel.bat`：在完整流程后再生成 Tafel 图。

> 说明：原来的 `一键LSV.bat` 已改名为 `选线+LSV画图.bat`，原来的 `一键LSV+Tafel.bat` 已改名为 `选线+LSV画图+Tafel.bat`。

## 模块说明

过电位检测、画图和 Tafel 已整合到主目录：

- `lsv_pipeline.py`：完整流程入口，按顺序跑 分析 → 样品图 → 对比图。
- `lsv_analysis.py`：解析 LSV 文本（BioLogic / CHI 等），自动识别 η10/η100，输出中文 CSV（UTF-8 BOM）。
- `lsv_plot.py`：画图。`--each-file` 模式每个文件一张；默认模式按样品分组，每个样品一张直接测图、一张 iR 补偿图。
- `lsv_compare.py`：自动生成总对比图与按条件词分组的对比图，自动剔除极差样品。
- `tafel_plot.py`：用 iR 后 LSV 数据出 `log10(j)-η` 的 Tafel 图，并自动滑动约 1 个数量级窗口拟合 Tafel 斜率，支持 `--files` 与 `--best-csv` 两种入口。
- `config.yaml`：绘图、对比、电极面积等规则配置。



## 数据怎么放

### 方式 A：只画图（`一键LSV画图.bat`）

不要求子文件夹，把要画的 txt 直接放在一个文件夹里即可：

```text
123/
├── Pt-HER.txt
├── Ni-HER_2.txt
├── Pt-OER.txt
└── Ni-OER_2.txt
```

也可以带子文件夹，程序会递归扫描，并在输出目录里镜像保存：

```text
123/
├── HER/
│   ├── Pt-HER.txt
│   └── Ni-HER_2.txt
└── OER/
    ├── Pt-OER.txt
    └── Ni-OER_2.txt
```

规则：

- 每个 txt 单独出一张图，文件名就是图名。
- 坐标轴按数据自动取范围，不读 `config.yaml` 的 `x_min`。
- 横轴是文件里记录的电位（不做 RHE 换算）；y 轴默认是原始电流（mA）并取绝对值。需要电流密度时用 `--y-unit density`，并先在 `config.yaml` 设好 `area`。
- 不挑线、不做对比，目录里所有 txt 都会被画出来。
- 非 LSV 文件（例如交流阻抗 `A.C. Impedance`）会被识别并跳过。

### 方式 B：选线流程（`选线+LSV画图.bat`）

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

> 如果整个文件夹里只有一层 txt、没有“每个样品一个子文件夹”，用方式 A 直接出图即可；方式 B 的选线、η10/η100 和对比图需要按样品分文件夹。

## 第一次使用 / 安装依赖

1. 安装 Python（[python.org](https://www.python.org/downloads/)），安装时勾选 **Add python.exe to PATH**。
2. 双击 `安装依赖.bat`，等窗口显示“依赖安装完成”或“依赖已安装到 py_deps”。这一步只需要做一次。
3. 如果窗口提示找不到 `python`，说明第 1 步没勾选 PATH，重新安装一次 Python 即可。

也可以手动运行 `.\install-deps.ps1 -Python <python路径>`。依赖清单在 `requirements.txt`；如果全局安装因为权限失败，安装脚本会自动把依赖装到本项目内的 `py_deps` 文件夹，不影响使用。如果 Codex 运行时更新导致 matplotlib 等消失，重跑安装脚本即可。

## 日常使用（一键版）

### 只要快速看图

双击 `一键LSV画图.bat`，把数据文件夹拖进黑色窗口按回车。程序会递归扫描所有 txt，每个文件生成一张 `<文件名>.png`，输出到 `output\<文件夹名>_<编号>\图\`；有子文件夹时按原结构镜像保存。

- 不选线、不做对比，适合刚测完想快速看曲线。
- 默认横轴是文件里记录的电位，纵轴是电流（mA），电流取绝对值。
- 想改成电流密度：命令行加 `--y-unit density`（面积读 `config.yaml` 的 `area`）。

### 要选线、η10/η100、样品图和对比图

双击 `选线+LSV画图.bat`，然后：

1. 把数据父文件夹拖到黑色窗口里，按回车；也可以直接粘贴完整路径。
2. 电极面积不用输入，默认读 `config.yaml` 的 `area`（默认 `1.0 cm²`）。
3. 等待程序自动完成。正常结束时窗口会显示输出目录。

### 要 LSV 结果，还要 Tafel 图

双击 `选线+LSV画图+Tafel.bat`，操作和上面一样。程序会先完成 LSV，再自动用选好的 iR 曲线生成 Tafel 图。

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

### 只画图（不选线）

```powershell
# 每个 txt 一张，纵轴电流 (mA)，电流取绝对值
# 不写 --output-dir 时自动新建 output\<数据文件夹名>_<编号>\图，不会覆盖
python lsv_plot.py --input-dir "数据目录" --each-file

# 改成电流密度（面积默认读 config.yaml 的 area）
python lsv_plot.py --input-dir "数据目录" --each-file --y-unit density

# 想保留原始电流符号
python lsv_plot.py --input-dir "数据目录" --each-file --no-abs-current
```

只给几个文件也可以：把 `--input-dir` 换成这些 txt 的路径列表即可。

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
- 自动拟合：在满足 `η ≥ 50 mV`（`fit_eta_min_mv`）和截取条件的正电流段内，从低电流向高电流滑动约 1 个数量级窗口，选 `R²` 最高的窗口，输出 `Tafel斜率/(mV/dec)`、`R²`、拟合起止与警告；
- 物理过滤：若最高 `R²` 候选斜率不在 `fit_slope_min_mv_dec` 到 `fit_slope_max_mv_dec` 范围内（默认 30–200 mV/dec），会自动顺延到范围内有效候选；所有参数都写在 `config.yaml` 的 `tafel:` 里，不在代码中写死；
- 不加平滑：`R²` 低于 `fit_r2_min`（默认 0.99）时只输出人工复核警告，不中断流程，也不引入 scipy 依赖；
- 额外生成独立拟合图：`-斜率拟合.png` 只显示拟合得到的直线，不叠画原始曲线，坐标范围按拟合线自动收窄；每个样品一张，每组对比一张，原全图版和截取版仍保留原始曲线。

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

规则：**每次运行都新建一个带编号的目录，从 `_0` 开始；`_0` 已存在就用 `_1`，再 `_2`……不会覆盖上一次的结果。**

```text
output/
├── 123_0/         第一次运行
├── 123_1/         第二次运行
└── 123_2/         第三次运行
```

“只画图”入口输出在 `output\<数据文件夹名>_<编号>\图\`，有子文件夹时按原结构镜像：

```text
output/123_0/图/
├── HER/
│   ├── Pt-HER.png
│   └── Ni-HER_2.png
└── OER/
    ├── Pt-OER.png
    └── Ni-OER_2.png
```

“选线”入口输出在 `output\<数据父文件夹名>_<编号>`，例如：

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
├── tafel_per_file.csv      每条 iR 曲线的 η/j/log10(j) 范围、Tafel斜率/R²/拟合区间/警告
├── tafel_points.csv        转换后的逐点数据
├── Tafel数据对比.md        自动拟合后的斜率与 R² 汇总
├── 样品/                   Tafel-<样品>.png、Tafel-<样品>-截取.png、Tafel-<样品>-斜率拟合.png
└── 对比图/                 总图与分组对比图，含对应的 -斜率拟合.png（best-csv 模式）
```

如果某个编号目录里的文件正被 Excel/WPS 打开导致写入失败，程序会自动换下一个编号，不会中断，也不会覆盖旧结果。

> 命令行里显式写了 `--output-dir "某个目录"` 时，就以你写的目录为准，不再自动编号；平时用一键入口或省略 `--output-dir` 即可。

## config.yaml 怎么改

`config.yaml` 里每一段都写了中文注释。大多数人只需要改下面几项：

| 字段 | 默认 | 作用 |
| --- | --- | --- |
| `area` | `1.0` | 电极面积（cm²），只有除以面积算电流密度时才用到 |
| `rhe` | `1.23` | 过电位基准（V）；数据已经是 vs RHE 时保持 1.23 |
| `targets` | `[10.0, 100.0]` | 目标电流密度（mA·cm⁻²），第一个算 η10，第二个算 η100 |
| `axis.x_min` | `1.4` | “选线”流程样品图的横轴起点（V）；只画图入口自动取范围，不受影响 |
| `compare.exclude_mv` | `100.0` | 对比图里剔除极差样品的阈值（mV） |

其余 `figure`、`curve`、`legend`、`tafel`、`ecsa` 都是画图和拟合的高级参数，不改也能用。Tafel 截取版默认从 `j ≥ 1 mA·cm⁻²` 开始，自动拟合参数也在 `tafel` 段里。

只画图入口的纵轴默认是原始电流 mA；想改成电流密度，用 `--y-unit density`，并在 `area` 里填实际面积。

## 规则摘要

- 读取：自动跳过前导测试信息，按表头文字定位电位/电流列，自动识别逗号、制表符、空格分隔和 `A` / `mA` / `µA` 单位；没有表头时按“第 1 列电位、第 2 列电流(mA)”处理并给出警告。
- 扫描段：只画图入口自动取最长的一段单调电位（升扫、降扫都支持），并跳过电位大幅跳变前的前导段；选线流程沿用 OER 习惯从 1.3 V 起算，HER 或低电位数据请用只画图入口。
- η10 取电流密度首次从低于 10 上升到高于 10 的相邻两点插值，开头瞬态高电流不再误判为“无 η10”。
- 选线：优先支配判定，一条曲线 η10、η100 都更优则直接胜出；仅真正互有优劣的曲线列为“手动”候选。
- 画图（选线流程）：x 轴 1.4 V 起，终点自动收；大分度 0.05、小分度 0.025 不标数字；坐标标题加粗；600 dpi。
- 画图（只画图入口）：每个 txt 一张，x 轴按数据自动范围，y 轴默认原始电流 mA 并取绝对值。
- 对比：自动按目录名中的 `-` 和空格拆词分组；η10 比组内中位数高 100 mV 以上自动剔除；多数达到 100 时 y 轴 0-100，否则 0-10。
- 输出目录被占用（如 CSV 正被 Excel/WPS 打开）时，`lsv_pipeline.py` 会自动改用 `<原目录>_新` 重跑，不会中断；平时请先关闭占用的文件。

## 常见问题

### 输出图是空白的？

先看窗口里的警告。程序会自动识别表头和数据行；如果提示“未找到表头”，说明这个 txt 的列名里没有 `Potential` / `Ewe` / `Current` / `<I>` 等关键词，需要确认它是不是 LSV 数据。交流阻抗（`A.C. Impedance`）会被自动跳过。

### 同一批数据既有 HER 又有 OER，怎么放？

用“只画图”入口最省事：父文件夹下按测试类型分子文件夹（例如 `HER/`、`OER/`），每个 txt 一个样品，程序会递归扫描并每个文件出一张图。需要算 η10/η100 或做样品间对比时，再按方式 B 每个样品一个子文件夹整理。

### 为什么输出目录名带 `_1`、`_2`？

这是正常的编号规则：每次运行都会新建一个目录，不会覆盖上一次结果。想重新从 `_0` 开始，把 `output` 里对应的旧目录删掉即可。


## ECSA/Cdl 模块（命令行）

新增 `ecsa_analysis.py`、`ecsa_pipeline.py`、`ecsa_plot.py`，实现双电层电容法（Cdl 法）的 ECSA 数据处理，不引入 PySimpleCV：

```text
原始 CV txt（每个 txt 可含多圈）
    ↓
自动解析完整回线并打分
    ↓
有歧义才 --pick 人工指定
    ↓
selected_cv.csv（中间数据）
    ↓
自动建议中心电位 → 提取 ja/jc → Δj=(ja-jc)/2
    ↓
Δj 对扫速 v 线性拟合 → Cdl（带截距的普通最小二乘）
```

数据目录约定与 LSV 相同：父文件夹下每个子文件夹是一个样品；同一扫速的多个重复文件（如 `2MV_C01.txt`、`2MV-2_C01.txt`）归为同一个扫速。文件名中的 `MV` 按 mV/s 处理。

```powershell
python ecsa_pipeline.py --input-dir "数据父目录"
# 有手动候选时指定，可重复
python ecsa_pipeline.py --input-dir "数据父目录" --pick "样品名=2MV_C01.txt#2"
# 固定中心电位 / 可选输出 ECSA（Cs 单位 µF/cm²）
python ecsa_pipeline.py --input-dir "数据父目录" --center-potential "样品名=1.10" --cs 40
```

输出位于 `output\<父目录名>_<编号>\ecsa\`：`ecsa_per_file.csv`（每圈审计）、`ecsa_best.csv`（最终选择）、`selected_cv\<样品>.csv`、`Δj表.csv`、`Cdl结果.csv`、`Cdl汇总.md`、`选择说明.txt`、`ECSA图\<样品>\`（CV 总图 + Cdl 拟合图）。

单位说明：拟合采用 v 的单位为 mV/s、Δj 单位为 mA/cm²，斜率再换算为 mF/cm² 与 µF/cm² 双单位输出；具体换算口径待补充文献依据后再更新本段说明。
