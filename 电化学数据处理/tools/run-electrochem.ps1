param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("LSV", "LSV+Tafel", "Plot", "Compare")]
    [string]$Task,
    [string]$InputDir = "",
    [string[]]$Pick = @()
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

$root = Split-Path -Parent $PSScriptRoot
$outputRoot = Join-Path $root "output"
$lsvPipeline = Join-Path $root "lsv_pipeline.py"
$lsvPlot = Join-Path $root "lsv_plot.py"
$lsvCompare = Join-Path $root "lsv_compare_direct.py"
$tafelPlot = Join-Path $root "tafel_plot.py"

$localDeps = Join-Path $root "py_deps"
if (Test-Path -LiteralPath $localDeps) {
    if ($env:PYTHONPATH) {
        $env:PYTHONPATH = $localDeps + [IO.Path]::PathSeparator + $env:PYTHONPATH
    } else {
        $env:PYTHONPATH = $localDeps
    }
}

if (-not $env:MPLCONFIGDIR) {
    $env:MPLCONFIGDIR = Join-Path $root ".mplcache"
    New-Item -ItemType Directory -Force -Path $env:MPLCONFIGDIR | Out-Null
}

function Write-Step {
    param([string]$Text)
    Write-Host ""
    Write-Host ("===== " + $Text + " =====") -ForegroundColor Cyan
}

function Write-Problem {
    param([string]$Text)
    Write-Host $Text -ForegroundColor Yellow
}

function Resolve-Python {
    $candidates = @(
        @{ Command = "python"; Args = @() },
        @{ Command = "py"; Args = @("-3") },
        @{ Command = "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe"; Args = @() },
        @{ Command = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"; Args = @() },
        @{ Command = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"; Args = @() },
        @{ Command = "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"; Args = @() }
    )
    foreach ($candidate in $candidates) {
        $found = [bool](Get-Command $candidate.Command -ErrorAction SilentlyContinue)
        if (-not $found -and (Test-Path -LiteralPath $candidate.Command -ErrorAction SilentlyContinue)) {
            $found = $true
        }
        if (-not $found) { continue }
        $previousPreference = $ErrorActionPreference
        $ErrorActionPreference = "Stop"
        try {
            & $candidate.Command $candidate.Args --version *> $null
            $ok = ($LASTEXITCODE -eq 0)
        } catch {
            $ok = $false
        } finally {
            $ErrorActionPreference = $previousPreference
        }
        if ($ok) {
            return $candidate
        }
    }
    return $null
}

function Invoke-Python {
    param([string[]]$Arguments)
    if ($pythonArgs -and $pythonArgs.Count -gt 0) {
        & $python $pythonArgs $Arguments 2>&1 | Out-Host
    } else {
        & $python $Arguments 2>&1 | Out-Host
    }
    return $LASTEXITCODE
}

function Get-DataFolder {
    Write-Step "选择数据文件夹"
    Write-Host "请把数据文件夹拖到本窗口后按回车；也可以直接粘贴完整路径。"
    Write-Host "示例：D:\文档\科研\RuO2\测性能\260812"
    while ($true) {
        $raw = Read-Host "数据文件夹"
        if ($null -eq $raw) {
            Write-Problem "无法读取输入，请重新运行。"
            exit 1
        }
        $folder = $raw.Trim().Trim('"')
        if ($folder.EndsWith('\')) { $folder = $folder.Substring(0, $folder.Length - 1) }
        if ([string]::IsNullOrWhiteSpace($folder)) {
            Write-Problem "路径不能为空，请重新输入。"
            continue
        }
        if (-not (Test-Path -LiteralPath $folder)) {
            Write-Problem "找不到这个路径，请重新输入。"
            continue
        }
        $hasTxt = Get-ChildItem -LiteralPath $folder -Recurse -File -Filter "*.txt" -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $hasTxt) {
            Write-Problem "这个文件夹里没有 .txt 文件，请重新输入。"
            continue
        }
        return (Resolve-Path -LiteralPath $folder).Path
    }
}

function Get-NewOutputDir {
    param([string]$BaseName)
    for ($n = 0; $n -lt 1000; $n++) {
        $candidate = Join-Path $outputRoot ("{0}_{1}" -f $BaseName, $n)
        if (-not (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }
    Write-Problem "输出目录编号已经到 _999，请先清理 output 目录。"
    exit 1
}

function Get-NewestLsvBest {
    param([string]$RootDir, [datetime]$After)
    if (-not (Test-Path -LiteralPath $RootDir)) { return $null }
    return Get-ChildItem -LiteralPath $RootDir -Recurse -File -Filter "lsv_best.csv" -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -ge $After } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1 -ExpandProperty FullName
}

function Invoke-LsvPipeline {
    param([string]$InputDir, [string]$OutputDir, [string[]]$Picks)
    $scriptArgs = @(
        $lsvPipeline,
        "--input-dir", $InputDir,
        "--output-dir", $OutputDir
    )
    foreach ($pick in $Picks) {
        $scriptArgs += @("--pick", $pick)
    }
    return Invoke-Python -Arguments $scriptArgs
}

function Resolve-ManualPicks {
    param([string]$BestCsv, [System.Collections.Generic.List[string]]$Picks)
    $rows = @(Import-Csv -LiteralPath $BestCsv -Encoding UTF8)
    $manual = @($rows | Where-Object { $_.选择方式 -eq "手动" })
    if ($manual.Count -eq 0) { return $false }

    Write-Step "人工选择最优曲线"
    Write-Host "以下样品的多条曲线互有优劣，程序不能自动判断。"
    Write-Host "请保留你认为最好的那条（一般选过电位最低、曲线最合理的）。"
    $keys = @($manual | ForEach-Object { "$($_.目录)|$($_.类别)" } | Select-Object -Unique)
    if ($keys.Count -gt 1) {
        Write-Host ("共 {0} 组需要人工选择，会一组一组问，每组回答一次即可。" -f $keys.Count)
    }
    Write-Host "输入规则：只填编号（如 1）或纯文件名（如 4-LSV_C01.txt），不要带目录，也不要写 目录=文件。"

    foreach ($key in $keys) {
        $parts = $key.Split('|', 2)
        $folder = $parts[0]
        $category = $parts[1]
        $cands = @($manual | Where-Object { $_.目录 -eq $folder -and $_.类别 -eq $category })
        Write-Host ""
        Write-Host "样品：$folder（$category）"
        $index = 0
        foreach ($cand in $cands) {
            $index++
            Write-Host ("  [{0}] {1}（η10={2} mV，η100={3} mV）" -f $index, $cand.文件, $cand.'η10/mV', $cand.'η100/mV')
        }
        while ($true) {
            $answer = Read-Host "输入要保留的文件名或编号"
            if ($null -eq $answer) {
                Write-Problem "无法读取输入，请重新运行。"
                exit 1
            }
            $answer = $answer.Trim().Trim('"')
            $chosen = $null
            if ($answer -match '^\d+$') {
                $number = [int]$answer
                if ($number -ge 1 -and $number -le $index) { $chosen = $cands[$number - 1].文件 }
            } else {
                $match = @($cands | Where-Object { $_.文件 -eq $answer })
                if ($match.Count -gt 0) { $chosen = $match[0].文件 }
            }
            if ($chosen) {
                $Picks.Add("$folder#$category=$chosen")
                Write-Host "已选择：$chosen"
                break
            }
            Write-Problem "输入不正确，请重新输入。"
        }
    }
    return $true
}

function Show-ResultPath {
    param([string]$Path)
    Write-Step "完成"
    Write-Host "输出目录：$Path"
    Write-Host "结果文件都在这个目录里，可以打开检查。"
}

$pythonInfo = Resolve-Python
if (-not $pythonInfo) {
    Write-Problem "没有找到可用的 Python。请先安装 Python，并在安装时勾选 Add python.exe to PATH。"
    exit 1
}
$python = $pythonInfo.Command
$pythonArgs = $pythonInfo.Args

if ($InputDir) {
    if (-not (Test-Path -LiteralPath $InputDir)) {
        Write-Problem "找不到路径：$InputDir"
        exit 1
    }
    $inputDir = (Resolve-Path -LiteralPath $InputDir).Path
} else {
    $inputDir = Get-DataFolder
}

$baseName = Split-Path -Leaf $inputDir
$outDir = Get-NewOutputDir -BaseName $baseName

if ($Task -eq "Plot") {
    $plotDir = Join-Path $outDir "图"
    Write-Step "LSV：读取并出图（每个 txt 一张，不选线、不做对比）"
    $plotArgs = @(
        $lsvPlot,
        "--input-dir", $inputDir,
        "--output-dir", $plotDir,
        "--each-file",
        "--y-unit", "mA"
    )
    $plotRc = Invoke-Python -Arguments $plotArgs
    if ($plotRc -ne 0) {
        Write-Problem "出图失败，请检查窗口里的报错。"
        exit 1
    }
    Show-ResultPath -Path $plotDir
    exit 0
}

if ($Task -eq "Compare") {
    $compareDir = Join-Path $outDir "对比图"
    Write-Step "LSV：直接生成对比图（不选线，每个顶层文件夹一张）"
    Write-Host "电位基准："
    Write-Host "  [1] 数据已经是 vs RHE（默认）"
    Write-Host "  [2] Hg/HgO，1 M KOH（E_RHE = E + 0.924 V）"
    $refChoice = Read-Host "选择 1 或 2（直接回车=1）"
    if ($null -eq $refChoice) { $refChoice = "1" }
    $refChoice = $refChoice.Trim()
    if ($refChoice -eq "2") {
        $shift = "0.924"
    } else {
        $shift = "0.0"
    }
    $compareArgs = @(
        $lsvCompare,
        "--input-dir", $inputDir,
        "--output-dir", $compareDir,
        "--erhe-shift", $shift
    )
    $compareRc = Invoke-Python -Arguments $compareArgs
    if ($compareRc -ne 0) {
        Write-Problem "对比图生成失败，请检查窗口里的报错。"
        exit 1
    }
    Show-ResultPath -Path $compareDir
    exit 0
}

$startTime = Get-Date
$picks = New-Object System.Collections.Generic.List[string]
foreach ($pickItem in $Pick) {
    $picks.Add($pickItem)
}

Write-Step "LSV：分析、选线、样品图、对比图"
$rc = $null
for ($attempt = 1; $attempt -le 3; $attempt++) {
    $rc = Invoke-LsvPipeline -InputDir $inputDir -OutputDir $outDir -Picks $picks
    if ($rc -eq 0) { break }

    if ($attempt -ge 3) {
        Write-Problem "LSV 连续多次未完成，请检查窗口里的报错。"
        exit 1
    }
    $bestCsv = Get-NewestLsvBest -RootDir $outputRoot -After $startTime.AddSeconds(-2)
    if (-not $bestCsv) {
        Write-Problem "没有生成 lsv_best.csv，请检查窗口里的报错。"
        exit 1
    }
    $hasManual = Resolve-ManualPicks -BestCsv $bestCsv -Picks $picks
    if (-not $hasManual) {
        Write-Problem "LSV 失败，但没有发现需要人工选择的候选，请检查窗口里的报错。"
        exit 1
    }
}

if ($rc -ne 0) { exit 1 }

$bestCsv = Get-NewestLsvBest -RootDir $outputRoot -After $startTime.AddSeconds(-2)
if (-not $bestCsv) {
    Write-Problem "找不到 lsv_best.csv。"
    exit 1
}
$actualOutput = Split-Path -Parent $bestCsv

if ($Task -eq "LSV+Tafel") {
    $tafelOut = Join-Path $actualOutput "tafel"
    Write-Step "Tafel：log10(j) - η 图"
    $tafelArgs = @(
        $tafelPlot,
        "--input-dir", $inputDir,
        "--best-csv", $bestCsv,
        "--output-dir", $tafelOut
    )
    $tafelRc = Invoke-Python -Arguments $tafelArgs
    if ($tafelRc -ne 0) {
        Write-Problem "Tafel 生成失败，请检查窗口里的报错。"
        exit 1
    }
}

Show-ResultPath -Path $actualOutput
