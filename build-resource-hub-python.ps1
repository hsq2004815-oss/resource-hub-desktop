$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$appName = "ResourceHubPython"
$distRoot = Join-Path $root "dist"
$buildRoot = Join-Path $root "build\resourcehub-python"
$outputDir = Join-Path $distRoot $appName

if (Test-Path $buildRoot) {
    Remove-Item -Path $buildRoot -Recurse -Force
}

if (Test-Path $outputDir) {
    Remove-Item -Path $outputDir -Recurse -Force
}

python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name $appName `
    --distpath $distRoot `
    --workpath $buildRoot `
    --icon (Join-Path $root "LinkHub.ico") `
    --collect-data tkinterdnd2 `
    --add-data ((Join-Path $root "DesktopShortcut.ico") + ";.") `
    --add-data ((Join-Path $root "LinkHub.ico") + ";.") `
    (Join-Path $root "resource_hub.pyw")

if (Test-Path (Join-Path $root "sites.sample.json")) {
    Copy-Item -Path (Join-Path $root "sites.sample.json") -Destination (Join-Path $outputDir "sites.json") -Force
}

if (Test-Path (Join-Path $root "folders.sample.json")) {
    Copy-Item -Path (Join-Path $root "folders.sample.json") -Destination (Join-Path $outputDir "folders.json") -Force
}

Copy-Item -Path (Join-Path $root "DesktopShortcut.ico") -Destination $outputDir -Force
Copy-Item -Path (Join-Path $root "LinkHub.ico") -Destination $outputDir -Force
Copy-Item -Path (Join-Path $root "README.md") -Destination $outputDir -Force
Copy-Item -Path (Join-Path $root "Install-ResourceHub-Exe-Shortcut.vbs") -Destination $outputDir -Force

Write-Host "Build completed:" $outputDir
