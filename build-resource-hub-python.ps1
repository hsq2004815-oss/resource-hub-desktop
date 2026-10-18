$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$appName = "ResourceHubPython"
$distRoot = Join-Path $root "dist"
$buildRoot = Join-Path $root "build\resourcehub-python"
$outputDir = Join-Path $distRoot $appName
$pythonExe = $null
$mainPngIcon = Join-Path $root "DesktopShortcut.png"
$mainIcoIcon = Join-Path $root "DesktopShortcut.ico"

foreach ($candidate in @(
    "D:\miniconda3\python.exe",
    "C:\Python314\python.exe",
    "E:\python.exe"
)) {
    if (Test-Path $candidate) {
        $pythonExe = $candidate
        break
    }
}

if (-not $pythonExe) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $pythonExe = $pythonCommand.Source
    }
}

if (-not $pythonExe) {
    throw "No suitable Python executable was found for building Resource Hub."
}

if (Test-Path $mainPngIcon) {
    $iconScript = @"
from pathlib import Path
from PIL import Image, ImageFilter

source = Path(r"$mainPngIcon")
target = Path(r"$mainIcoIcon")
image = Image.open(source).convert("RGBA")
side = max(image.size)
canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
canvas.alpha_composite(image, ((side - image.width) // 2, (side - image.height) // 2))
icon_image = canvas.resize((256, 256), Image.Resampling.LANCZOS)
icon_image = icon_image.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=2))
icon_image.save(target, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)])
"@
    $tempScript = Join-Path $env:TEMP "resource_hub_make_icon.py"
    Set-Content -LiteralPath $tempScript -Value $iconScript -Encoding UTF8
    & $pythonExe $tempScript
    Remove-Item -LiteralPath $tempScript -Force
}

if (Test-Path $buildRoot) {
    Remove-Item -Path $buildRoot -Recurse -Force
}

if (Test-Path $outputDir) {
    Remove-Item -Path $outputDir -Recurse -Force
}

& $pythonExe -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name $appName `
    --distpath $distRoot `
    --workpath $buildRoot `
    --icon $mainIcoIcon `
    --collect-data tkinterdnd2 `
    --collect-submodules pystray `
    --hidden-import pystray._win32 `
    --add-data ((Join-Path $root "DesktopShortcut.png") + ";.") `
    --add-data ((Join-Path $root "DesktopShortcut.ico") + ";.") `
    --add-data ((Join-Path $root "LinkHub.ico") + ";.") `
    (Join-Path $root "resource_hub.pyw")

if (Test-Path (Join-Path $root "sites.sample.json")) {
    Copy-Item -Path (Join-Path $root "sites.sample.json") -Destination (Join-Path $outputDir "sites.json") -Force
}

if (Test-Path (Join-Path $root "folders.sample.json")) {
    Copy-Item -Path (Join-Path $root "folders.sample.json") -Destination (Join-Path $outputDir "folders.json") -Force
}

Copy-Item -Path (Join-Path $root "DesktopShortcut.png") -Destination $outputDir -Force
Copy-Item -Path (Join-Path $root "DesktopShortcut.ico") -Destination $outputDir -Force
Copy-Item -Path (Join-Path $root "LinkHub.ico") -Destination $outputDir -Force
Copy-Item -Path (Join-Path $root "README.md") -Destination $outputDir -Force
Copy-Item -Path (Join-Path $root "Install-ResourceHub-Exe-Shortcut.vbs") -Destination $outputDir -Force

Write-Host "Build completed:" $outputDir
