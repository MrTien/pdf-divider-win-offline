param(
    [ValidateSet("run", "test", "build")]
    [string]$Action = "run"
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if ($Action -eq "build") {
    & (Join-Path $PSScriptRoot "build.ps1")
    exit $LASTEXITCODE
}

$dependencyDir = Join-Path $PSScriptRoot ".dev-packages"
$requiredPaths = @(
    (Join-Path $dependencyDir "pypdfium2"),
    (Join-Path $dependencyDir "PIL")
)
$dependenciesReady = ($requiredPaths | Where-Object { -not (Test-Path -LiteralPath $_) }).Count -eq 0

if (-not $dependenciesReady) {
    New-Item -ItemType Directory -Path $dependencyDir -Force | Out-Null
    python -m pip install --disable-pip-version-check --target $dependencyDir -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        throw "安装开发依赖失败，退出码：$LASTEXITCODE"
    }
}

$previousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = "$dependencyDir;$PSScriptRoot\src"
try {
    if ($Action -eq "test") {
        python -m unittest discover -s tests -v
    } else {
        python src\app.py
    }
    if ($LASTEXITCODE -ne 0) {
        throw "命令执行失败，退出码：$LASTEXITCODE"
    }
} finally {
    $env:PYTHONPATH = $previousPythonPath
}
