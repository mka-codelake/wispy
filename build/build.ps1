# build.ps1
# ---------------------------------------------------------------------------
# Reproducible build script for the portable wispy Windows bundle.
# Uses uv (https://github.com/astral-sh/uv) as the Python + package manager.
#
# Prerequisites (once on your build machine):
#     choco install uv -y
#
# That's it. uv itself downloads and manages Python 3.12, so you do NOT
# need a separate Python installation on this host.
#
# Run (from any directory inside the repo):
#     powershell -ExecutionPolicy Bypass -File build\build.ps1
# ---------------------------------------------------------------------------

[CmdletBinding()]
param(
    [switch]$CreateZip,  # When set, also package dist/wispy/ into wispy-vX.Y.Z.zip
    [switch]$Gpu         # When set, install NVIDIA CUDA libs and build a GPU-capable bundle (~2 GB).
                         # Without this flag the build is CPU-only (~350-600 MB).
)

$ErrorActionPreference = "Stop"

# --- 1. Resolve paths --------------------------------------------------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path -Parent $ScriptDir
$VenvDir   = Join-Path $RepoRoot ".venv-build"
$DistDir   = Join-Path $RepoRoot "dist"
$BuildDir  = Join-Path $RepoRoot "build"
$SpecFile  = Join-Path $BuildDir "wispy.spec"
$BundleDir = Join-Path $DistDir "wispy"
$PythonVer = "3.12"

$BuildVariant = if ($Gpu) { "GPU (CUDA)" } else { "CPU-only" }

Write-Host ""
Write-Host "=== wispy portable build (uv) ===" -ForegroundColor Cyan
Write-Host "Repo root : $RepoRoot"
Write-Host "Venv      : $VenvDir"
Write-Host "Python    : $PythonVer (managed by uv)"
Write-Host "Output    : $BundleDir"
Write-Host "Variant   : $BuildVariant"
Write-Host ""

# --- 2. Preflight: uv must be installed -------------------------------------
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is not installed or not in PATH. Install it once with:`n    choco install uv -y`nThen open a new PowerShell and retry."
}

$uvVersion = (& uv --version) -join ""
Write-Host "[build] Using $uvVersion" -ForegroundColor DarkGray

# --- 3. Ensure Python 3.12 is available via uv ------------------------------
Write-Host "[build] Ensuring Python $PythonVer is available ..." -ForegroundColor Yellow
& uv python install $PythonVer

# --- 4. Create / reuse build venv -------------------------------------------
if (-not (Test-Path $VenvDir)) {
    Write-Host "[build] Creating build venv ..." -ForegroundColor Yellow
    & uv venv $VenvDir --python $PythonVer
} else {
    Write-Host "[build] Reusing existing build venv" -ForegroundColor DarkGray
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    throw "Venv Python not found at $VenvPython"
}

# --- 5. Install dependencies into the venv ----------------------------------
Write-Host "[build] Installing wispy (editable) and runtime dependencies ..." -ForegroundColor Yellow
& uv pip install --python $VenvPython -e $RepoRoot

if ($Gpu) {
    Write-Host "[build] Installing CUDA runtime libs and PyInstaller ..." -ForegroundColor Yellow
    & uv pip install --python $VenvPython `
        nvidia-cublas-cu12 `
        nvidia-cudnn-cu12 `
        nvidia-cuda-runtime-cu12 `
        pyinstaller
} else {
    Write-Host "[build] Installing PyInstaller (CPU-only build, skipping CUDA libs) ..." -ForegroundColor Yellow
    & uv pip install --python $VenvPython pyinstaller
}

# --- 6. Clean previous build ------------------------------------------------
if (Test-Path $BundleDir) {
    Write-Host "[build] Removing previous bundle at $BundleDir" -ForegroundColor DarkGray
    Remove-Item -Recurse -Force $BundleDir
}

# --- 7. Run PyInstaller -----------------------------------------------------
Write-Host "[build] Running PyInstaller ($BuildVariant) ..." -ForegroundColor Yellow
$env:WISPY_GPU_BUILD = if ($Gpu) { "1" } else { "0" }
Push-Location $RepoRoot
try {
    & $VenvPython -m PyInstaller $SpecFile --clean --noconfirm
} finally {
    Pop-Location
    Remove-Item Env:WISPY_GPU_BUILD -ErrorAction SilentlyContinue
}

if (-not (Test-Path $BundleDir)) {
    throw "Bundle was not created at $BundleDir"
}

# --- 8. Post-build: copy config + readme, create models dir -----------------
Write-Host "[build] Post-build copy ..." -ForegroundColor Yellow

Copy-Item (Join-Path $RepoRoot "config.yaml") `
          -Destination (Join-Path $BundleDir "config.yaml") -Force

Copy-Item (Join-Path $BuildDir "README.txt") `
          -Destination (Join-Path $BundleDir "README.txt") -Force

$ModelsDir = Join-Path $BundleDir "models"
New-Item -ItemType Directory -Force -Path $ModelsDir | Out-Null

# --- 9. Summary -------------------------------------------------------------
$BundleBytes = (Get-ChildItem -Recurse $BundleDir | Measure-Object -Property Length -Sum).Sum
$BundleSize  = "{0:N0} MB" -f ($BundleBytes / 1MB)

Write-Host ""
Write-Host "[build] Bundle ready." -ForegroundColor Green
Write-Host "[build] Location : $BundleDir"
Write-Host "[build] Size     : $BundleSize"
Write-Host ""

# --- 10. Optional: create release ZIP ---------------------------------------
if ($CreateZip) {
    $TomlPath = Join-Path $RepoRoot "pyproject.toml"
    $VersionLine = (Get-Content $TomlPath) | Where-Object { $_ -match '^version\s*=\s*"(.+)"' } | Select-Object -First 1
    if ($VersionLine -match '^version\s*=\s*"(.+)"') {
        $PkgVersion = $Matches[1]
    } else {
        throw "Could not read version from pyproject.toml"
    }

    $ZipSuffix = if ($Gpu) { "-gpu" } else { "" }
    $ZipName = "wispy-v$PkgVersion$ZipSuffix.zip"
    $ZipPath = Join-Path $DistDir $ZipName

    if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }

    Write-Host "[build] Creating $ZipName ..." -ForegroundColor Yellow
    Compress-Archive -Path $BundleDir -DestinationPath $ZipPath
    $ZipBytes = (Get-Item $ZipPath).Length
    $ZipSize  = "{0:N0} MB" -f ($ZipBytes / 1MB)

    Write-Host "[build] ZIP ready : $ZipPath ($ZipSize)" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next step (GitHub Release):" -ForegroundColor Cyan
    Write-Host "  gh release create v$PkgVersion $ZipPath --title `"wispy v$PkgVersion`" --notes `"<release notes>`""
    if (-not $Gpu) {
        Write-Host ""
        Write-Host "  (Optional GPU build: .\build\build.ps1 -CreateZip -Gpu)" -ForegroundColor DarkGray
    }
    Write-Host ""
} else {
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "  1. Smoke test : $BundleDir\wispy.exe"
    Write-Host "  2. Release    : .\build\build.ps1 -CreateZip  (then gh release create ...)"
    Write-Host "     GPU build  : .\build\build.ps1 -CreateZip -Gpu"
    Write-Host ""
}
