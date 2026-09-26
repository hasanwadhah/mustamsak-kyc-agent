# One-time setup on Windows: Python environment, packages and the public OCR models.
# Usage:  powershell -ExecutionPolicy Bypass -File setup.ps1
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Find-Python312 {
    # The Python launcher (py) is installed with python.org Python; fall back to python on PATH.
    foreach ($candidate in @(@('py', '-3.12'), @('python'))) {
        $exe = $candidate[0]
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        $version = & $exe @($candidate[1..9] | Where-Object { $_ }) -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($version -eq '3.12') { return ,$candidate }
    }
    return $null
}

if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    $python = Find-Python312
    if (-not $python) {
        throw 'Python 3.12 is required. Install it from https://www.python.org/downloads/ (tick "Add python.exe to PATH"), then run setup again.'
    }
    Write-Host 'Creating the Python environment (.venv)...'
    & $python[0] @($python[1..9] | Where-Object { $_ }) -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
}
$py = '.\.venv\Scripts\python.exe'

Write-Host 'Installing packages (CPU only; about 1.5 GB, 5-15 minutes)...'
& $py -m pip install --upgrade pip --quiet
& $py -m pip install -r requirements-lock.txt --extra-index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE -ne 0) { throw 'Package installation failed.' }

Write-Host 'Downloading the public OCR models...'
& $py scripts/setup_models.py
if ($LASTEXITCODE -ne 0) { throw 'OCR model setup failed.' }
& $py scripts/setup_english.py
if ($LASTEXITCODE -ne 0) { throw 'English model setup failed.' }
& $py scripts/setup_arabic_v5.py
if ($LASTEXITCODE -ne 0) { throw 'Arabic PP-OCRv5 model setup failed.' }

# The handwriting models trained in this project ship in models/. They are rebuilt only if missing.
if (-not (Test-Path -LiteralPath 'models\eastern_digits.npz')) {
    & $py scripts/train_eastern_digits.py
    if ($LASTEXITCODE -ne 0) { throw 'Digit model training failed.' }
}
if (-not (Test-Path -LiteralPath 'models\eastern_digits_cnn.npz')) {
    Write-Host 'Training the handwritten-digit CNN on MADBase (about 20 minutes)...'
    & $py -m pip install pyarrow --quiet
    & $py scripts/fetch_madbase.py
    if ($LASTEXITCODE -eq 0) { & $py scripts/train_digit_cnn.py }
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Digit CNN not built; the smaller synthetic digit model is used instead.' }
}

Write-Host ''
Write-Host 'Setup complete. Start the app with "Start KYC Agent.cmd" (or: powershell -ExecutionPolicy Bypass -File start.ps1).'
