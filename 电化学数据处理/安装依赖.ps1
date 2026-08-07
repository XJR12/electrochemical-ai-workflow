# 安装本项目 Python 依赖（可传 Python 路径，默认用 PATH 里的 python）
param(
    [string]$Python = "python"
)
$req = Join-Path $PSScriptRoot 'requirements.txt'
& $Python -m pip install -r $req
if ($LASTEXITCODE -ne 0) {
    Write-Host "安装失败，请确认 python 可用，或指定路径： .\安装依赖.ps1 -Python C:\你的Python\python.exe"
}