$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$buildPackages = Join-Path $PSScriptRoot ".build-packages"
New-Item -ItemType Directory -Path $buildPackages -Force | Out-Null

$requiredBuildPaths = @(
    (Join-Path $buildPackages "PyInstaller"),
    (Join-Path $buildPackages "pypdfium2"),
    (Join-Path $buildPackages "PIL")
)
$dependenciesReady = ($requiredBuildPaths | Where-Object { -not (Test-Path -LiteralPath $_) }).Count -eq 0
if (-not $dependenciesReady) {
    python -m pip install --disable-pip-version-check --upgrade --target $buildPackages -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) {
        throw "安装构建依赖失败，退出码：$LASTEXITCODE"
    }
}

$previousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = "$buildPackages;$PSScriptRoot\src"
try {
    python -m PyInstaller --noconfirm --clean "PDF逐页图片工具.spec"
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller 构建失败，退出码：$LASTEXITCODE"
    }
} finally {
    $env:PYTHONPATH = $previousPythonPath
}

$portableDir = Join-Path $PSScriptRoot "dist\PDF逐页图片工具"
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "使用说明.txt") -Destination $portableDir -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "THIRD_PARTY_NOTICES.txt") -Destination $portableDir -Force

$licenseDir = Join-Path $portableDir "licenses"
New-Item -ItemType Directory -Path $licenseDir -Force | Out-Null

$env:PYTHONPATH = $buildPackages
try {
python -c @'
import importlib.metadata as metadata
import pathlib
import shutil
import sys

destination = pathlib.Path(sys.argv[1])
for distribution_name in ("pypdfium2", "Pillow"):
    distribution = metadata.distribution(distribution_name)
    source = pathlib.Path(distribution._path) / "licenses"
    if source.exists():
        shutil.copytree(source, destination / distribution_name, dirs_exist_ok=True)

python_license = pathlib.Path(sys.base_prefix) / "LICENSE.txt"
if python_license.exists():
    shutil.copy2(python_license, destination / "PYTHON_LICENSE.txt")

for relative_path, output_name in (
    ("tcl/tcl8.6/license.terms", "TCL_LICENSE.txt"),
    ("tcl/tk8.6/license.terms", "TK_LICENSE.txt"),
):
    source = pathlib.Path(sys.base_prefix) / relative_path
    if source.exists():
        shutil.copy2(source, destination / output_name)
'@ $licenseDir
if ($LASTEXITCODE -ne 0) {
    throw "复制许可证失败，退出码：$LASTEXITCODE"
}
} finally {
    $env:PYTHONPATH = $previousPythonPath
}

Write-Host ""
Write-Host "构建完成：$portableDir" -ForegroundColor Green
