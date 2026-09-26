<#
.SYNOPSIS
    Builds the 2dverse Windows release with PyInstaller and zips it for itch.io.

.DESCRIPTION
    Run from the project folder (the one containing main.py):

        powershell -ExecutionPolicy Bypass -File .\build.ps1

    Steps:
      1. creates .venv-build (a clean venv, so the build never inherits
         Anaconda's numpy/MKL/scipy DLLs) and installs requirements-build.txt
      2. runs PyInstaller with 2dverse.spec  ->  dist\2dverse\
      3. zips dist\2dverse into release\2dverse-win64-<version>.zip

    Pass -Version to change the zip name (default: alpha-0.0.1).
    Pass -Python to pick the interpreter used to create the venv (default: py -3.13).
#>
param(
    [string]$Version = "alpha-0.0.1",
    [string]$Python = "py -3.13"
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$venv = ".venv-build"
if (-not (Test-Path "$venv\Scripts\python.exe")) {
    Write-Host "== Creating build venv ($Python) =="
    Invoke-Expression "$Python -m venv $venv"
}
$py = "$venv\Scripts\python.exe"

Write-Host "== Installing build requirements =="
& $py -m pip install --upgrade pip --quiet
& $py -m pip install -r requirements-build.txt --quiet
& $py -m pip list | Select-String -Pattern "^(pygame|pymunk|pyinstaller)"

Write-Host "== Running PyInstaller =="
& $py -m PyInstaller 2dverse.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$dist = "dist\2dverse"
if (-not (Test-Path "$dist\2dverse.exe")) { throw "Build did not produce $dist\2dverse.exe" }
if (-not (Test-Path "$dist\_internal\assets\audio\music\background.ogg")) {
    throw "Assets were not bundled (missing _internal\assets\...)"
}

Write-Host "== Zipping for itch.io =="
New-Item -ItemType Directory -Force -Path "release" | Out-Null
$zip = "release\2dverse-win64-$Version.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path "$dist\*" -DestinationPath $zip
$size = [math]::Round((Get-Item $zip).Length / 1MB, 1)

Write-Host ""
Write-Host "Done."
Write-Host "  exe : $dist\2dverse.exe"
Write-Host "  zip : $zip  ($size MB)"
Write-Host ""
Write-Host "Test it from a DIFFERENT folder before uploading, e.g.:"
Write-Host "  cd C:\ ; & '$PSScriptRoot\$dist\2dverse.exe'"
Write-Host "then on a PC without Python. Problems are logged to 2dverse.log beside the exe."
