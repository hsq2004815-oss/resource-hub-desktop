# Build the installable Resource Hub Desktop package.
#
# Produces release\ResourceHub-Desktop-<stamp>\ with:
#   resource_hub.exe          Flutter client (built from app\)
#   backend\                  frozen Python backend (PyInstaller onedir)
#   README.txt                first-run / data-location notes
#
# Usage (PowerShell 7):
#   .\build-flutter-release.ps1                 # rebuild both
#   .\build-flutter-release.ps1 -SkipFlutter    # reuse the current Flutter build
#   .\build-flutter-release.ps1 -SkipBackend    # reuse build\backend-exe\dist
#
# The JSON data files (sites.json / folders.json / settings.json) are *not*
# shipped: the backend writes the legacy sample data on first run, next to the
# executable. Keep the installed folder writable.

param(
    [switch]$SkipFlutter,
    [switch]$SkipBackend,
    [string]$Tag = ""
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = "D:\miniconda3\python.exe"
$flutterRoot = "F:\flutter"
$backendSource = Join-Path $root "backend"
$backendDistRoot = Join-Path $root "build\backend-exe\dist"
$backendDist = Join-Path $backendDistRoot "resource_hub_backend"
$flutterRelease = Join-Path $root "app\build\windows\x64\runner\Release"

if (-not (Test-Path $python)) {
    throw "Python not found at $python (see MEMORY.md: the miniconda interpreter is required for packaging)."
}

# -- 1. frozen backend ------------------------------------------------------
if (-not $SkipBackend) {
    Write-Host "==> Building frozen backend (PyInstaller onedir)"
    # conda's _ctypes needs Library\bin\ffi.dll on PATH during analysis; the spec
    # additionally pins it with --add-binary. See build\backend-exe\REPORT.md.
    $env:PATH = "D:\miniconda3\Library\bin;$env:PATH"
    & $python -m PyInstaller `
        --noconfirm --clean `
        --onedir --console --hide-console hide-early `
        --add-binary "D:\miniconda3\Library\bin\ffi.dll;." `
        --paths $backendSource `
        --name resource_hub_backend `
        --distpath $backendDistRoot `
        --workpath (Join-Path $root "build\backend-exe\work") `
        (Join-Path $backendSource "main.py")
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
}

if (-not (Test-Path (Join-Path $backendDist "resource_hub_backend.exe"))) {
    throw "Frozen backend missing: $backendDist\resource_hub_backend.exe (run without -SkipBackend)"
}

# -- 2. Flutter client ------------------------------------------------------
if (-not $SkipFlutter) {
    Write-Host "==> Building Flutter client (windows/release)"
    $env:PATH = "$flutterRoot\bin;$env:PATH"
    $env:HTTP_PROXY = ""
    $env:HTTPS_PROXY = ""
    $env:NO_PROXY = "localhost,127.0.0.1"
    Push-Location (Join-Path $root "app")
    try {
        # --no-tree-shake-icons: the icon tree shaker only keeps IconData that
        # appears in const contexts. Icons passed through widget parameters
        # (ToolbarButton, ButtonSegment) are non-const, so several glyphs were
        # missing from the subset font (export/import/list/grid). Shipping the
        # full Material icon font costs ~1.6 MB out of 46 MB — acceptable.
        flutter build windows --release --no-tree-shake-icons
        if ($LASTEXITCODE -ne 0) {
            throw "flutter build failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

if (-not (Test-Path (Join-Path $flutterRelease "resource_hub.exe"))) {
    throw "Flutter release build missing: $flutterRelease\resource_hub.exe"
}

# -- 3. assemble ------------------------------------------------------------
$stamp = if ($Tag) { $Tag } else { Get-Date -Format "yyyyMMdd-HHmm" }
$out = Join-Path $root "release\ResourceHub-Desktop-$stamp"
if (Test-Path $out) {
    Remove-Item -Path $out -Recurse -Force
}
New-Item -ItemType Directory -Path $out -Force | Out-Null

Write-Host "==> Assembling $out"
Copy-Item -Path (Join-Path $flutterRelease "*") -Destination $out -Recurse -Force
New-Item -ItemType Directory -Path (Join-Path $out "backend") -Force | Out-Null
Copy-Item -Path (Join-Path $backendDist "*") -Destination (Join-Path $out "backend") -Recurse -Force

$readme = @"
Resource Hub Desktop
====================

启动：双击 resource_hub.exe

目录说明
--------
resource_hub.exe     Flutter 前端
backend\             打包后的 Python 后端（必须与 exe 一起分发，勿删）
sites.json           网站收藏（首次启动自动生成示例数据）
folders.json         本地文件/文件夹收藏（首次启动自动生成示例数据）
settings.json        语言、主题、全局快捷键、开机启动

说明
----
* 数据文件保存在 exe 同目录，请把整个文件夹放在可写位置（不要放 Program Files）。
* 关闭窗口 = 隐藏到托盘；托盘菜单可显示/隐藏或退出。
* 全局快捷键默认 Ctrl + Alt + Space，可在设置里录制修改。
* 快速面板（只弹出树状图、不打开完整窗口）：Ctrl + Alt + Shift + L 网站树、
  Ctrl + Alt + Shift + F 文件夹树；同样可在设置里录制修改。
* 开机启动由设置里的开关创建/删除“启动”文件夹快捷方式（静默进托盘）。
* 导入/导出使用 JSON 备份文件，格式与原 Python 版完全兼容。
"@
Set-Content -Path (Join-Path $out "README.txt") -Value $readme -Encoding UTF8

# -- 4. sanity checks -------------------------------------------------------
$exe = Join-Path $out "resource_hub.exe"
$backendExe = Join-Path $out "backend\resource_hub_backend.exe"
foreach ($required in @($exe, $backendExe)) {
    if (-not (Test-Path $required)) {
        throw "Assembled package is incomplete: $required"
    }
}

$size = (Get-ChildItem $out -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Host ("==> Done: {0} ({1:N1} MB)" -f $out, ($size / 1MB))
Write-Host "    Launch it from its own folder; data files are written next to the exe."
