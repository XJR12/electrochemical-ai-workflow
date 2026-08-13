# 安装本项目 Python 依赖（可传 Python 路径；找不到 python 时会自动尝试常见位置）
param(
    [string]$Python = ""
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Continue"
$req = Join-Path $PSScriptRoot 'requirements.txt'

$candidates = @(
    @{ Command = "python"; Args = @() },
    @{ Command = "py"; Args = @("-3") },
    @{ Command = "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe"; Args = @() },
    @{ Command = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"; Args = @() },
    @{ Command = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"; Args = @() },
    @{ Command = "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"; Args = @() }
)

$selected = $null
if ($Python) {
    $selected = @{ Command = $Python; Args = @() }
} else {
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
            $selected = $candidate
            break
        }
    }
}

if (-not $selected) {
    Write-Host "没有找到 Python。请先安装 Python，并在安装时勾选 Add python.exe to PATH。"
    exit 1
}

Write-Host "使用 Python: $($selected.Command)"
& $selected.Command $selected.Args -m pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple --timeout 30 -r $req
if ($LASTEXITCODE -eq 0) {
    Write-Host "依赖安装完成。"
    exit 0
}

Write-Host ""
Write-Host "全局安装失败，正在尝试安装到本项目内的 py_deps 目录..."
$target = Join-Path $PSScriptRoot "py_deps"
& $selected.Command $selected.Args -m pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple --timeout 30 --target $target -r $req
if ($LASTEXITCODE -eq 0) {
    Write-Host "依赖已安装到 py_deps，可以直接使用。"
    exit 0
}

Write-Host "安装失败。请检查网络，或手动指定 Python 路径： .\install-deps.ps1 -Python C:\你的Python\python.exe"
exit 1
