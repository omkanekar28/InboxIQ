# ==============================================================================
# InboxIQ — Complete Windows Build & Installer Script
# ==============================================================================
# Usage:
#   powershell -ExecutionPolicy Bypass -File packaging/build.ps1
# ==============================================================================

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $ScriptDir

Set-Location $ProjectRoot
Write-Host "=== InboxIQ Build & Packaging ===" -ForegroundColor Cyan
Write-Host "Project Root: $ProjectRoot"

# 1. Resolve Python executable
$PythonExe = "python"
if (Test-Path "C:\Users\Om\virtual_environments\ai_venv\Scripts\python.exe") {
    $PythonExe = "C:\Users\Om\virtual_environments\ai_venv\Scripts\python.exe"
}
Write-Host "Using Python: $PythonExe"

# 2. Check credentials.json
$CredsSource = Join-Path $ScriptDir "credentials.json"
if (-not (Test-Path $CredsSource)) {
    $BackendCreds = Join-Path $ProjectRoot "backend\src\credentials.json"
    if (Test-Path $BackendCreds) {
        Copy-Item $BackendCreds $CredsSource -Force
        Write-Host "Copied credentials.json to packaging/credentials.json" -ForegroundColor Green
    } else {
        Write-Warning "credentials.json not found in packaging or backend/src! Please provide one."
    }
}

# 3. Check icon files
$IconIco = Join-Path $ScriptDir "icon.ico"
if (-not (Test-Path $IconIco)) {
    Write-Host "Generating application icons..." -ForegroundColor Yellow
    & $PythonExe (Join-Path $ProjectRoot "backend\scripts\generate_icon.py")
}

# 4. Check pywebview
& $PythonExe -c "import webview" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing pywebview in build environment..." -ForegroundColor Yellow
    & $PythonExe -m pip install pywebview
}

# 5. Build PyInstaller bundle
Write-Host "`n[1/2] Building PyInstaller executable bundle (with native desktop window)..." -ForegroundColor Cyan
$SpecFile = Join-Path $ScriptDir "inboxiq.spec"
$DistPath = Join-Path $ScriptDir "dist"
$WorkPath = Join-Path $ScriptDir "build"

& $PythonExe -m PyInstaller $SpecFile --distpath $DistPath --workpath $WorkPath --clean -y

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed with exit code $LASTEXITCODE"
}

Write-Host "PyInstaller build completed successfully: $DistPath\InboxIQ\InboxIQ.exe" -ForegroundColor Green

# 5. Build Inno Setup Installer
Write-Host "`n[2/2] Compiling Windows Setup Installer..." -ForegroundColor Cyan

$IsccCandidates = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)

$IsccExe = $null
foreach ($cand in $IsccCandidates) {
    if (Test-Path $cand) {
        $IsccExe = $cand
        break
    }
}

if (-not $IsccExe) {
    $cmd = Get-Command "iscc.exe" -ErrorAction SilentlyContinue
    if ($cmd) {
        $IsccExe = $cmd.Source
    }
}

if ($IsccExe) {
    Write-Host "Found Inno Setup Compiler: $IsccExe"
    Push-Location $ScriptDir
    try {
        & $IsccExe "installer.iss"
        if ($LASTEXITCODE -eq 0) {
            $InstallerExe = Join-Path $ScriptDir "dist-installer\InboxIQ-Setup.exe"
            Write-Host "`n========================================================" -ForegroundColor Green
            Write-Host "SUCCESS! Installer created at:" -ForegroundColor Green
            Write-Host "  $InstallerExe" -ForegroundColor Cyan
            Write-Host "========================================================`n" -ForegroundColor Green
        } else {
            Write-Warning "Inno Setup compilation exited with code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Warning "ISCC.exe not found. You can manually compile packaging/installer.iss using Inno Setup."
}
