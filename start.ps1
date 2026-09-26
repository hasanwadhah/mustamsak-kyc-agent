param([switch]$NoBrowser, [switch]$LocalAI, [switch]$Stop, [switch]$Force, [int]$Port = 8766)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$runtime = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $runtime)) {
    Write-Host 'First run setup.ps1 (one time):  powershell -ExecutionPolicy Bypass -File setup.ps1'
    exit 1
}
$env:PYTHONUTF8 = '1'
$launchArgs = @('-m', 'app.launcher', '--port', "$Port")
# -Stop ends the app (it runs in the background without a window); -Force also while it is busy.
if ($Stop) {
    $stopArgs = $launchArgs + @('--stop')
    if ($Force) { $stopArgs += '--force' }
    & $runtime @stopArgs
    exit $LASTEXITCODE
}
if ($NoBrowser) { $launchArgs += '--no-browser' }
& $runtime @launchArgs
$code = $LASTEXITCODE
# -LocalAI switches the optional local AI reader on (same as the toggle in reading settings).
if ($LocalAI -and $code -eq 0) {
    try {
        $state = Invoke-RestMethod -Method Put -Uri "http://127.0.0.1:$Port/api/local-ai" -ContentType 'application/json' -Body '{"enabled": true}' -TimeoutSec 60
        if (-not $state.ready) { Write-Warning 'Local AI reader switched on, but Ollama or its model is not ready.' }
    } catch { Write-Warning 'Could not switch on the local AI reader.' }
}
exit $code
