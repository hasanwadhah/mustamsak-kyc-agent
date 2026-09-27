param([switch]$NoBrowser, [switch]$LocalAI, [switch]$Stop, [switch]$Force, [switch]$NoUpdate, [int]$Port = 8766)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Update-FromGitHub {
    # Brings this folder up to date with GitHub before the app starts, only when that is safe:
    # fast-forward only, never over edited files or unpushed commits, and skipped quietly when offline.
    # The launcher then restarts a running server by itself, because the program files changed.
    $ErrorActionPreference = 'Continue'   # git writes progress to stderr; that is not an error
    if (-not (Get-Command git -ErrorAction SilentlyContinue) -or -not (Test-Path -LiteralPath '.git')) { return }
    $env:GIT_TERMINAL_PROMPT = '0'        # never wait for a password prompt
    $before = git rev-parse --short HEAD 2>$null
    git -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=15 fetch --quiet origin main 2>$null
    if ($LASTEXITCODE -ne 0) { Write-Host "GitHub not reachable: starting the version on this computer ($before)."; return }
    $counts = "$(git rev-list --left-right --count HEAD...origin/main 2>$null)".Trim() -split '\s+'
    $ahead = [int]$counts[0]; $behind = [int]$counts[1]
    if ($behind -eq 0) { Write-Host "Up to date with GitHub (version $before)."; return }
    if (git status --porcelain --untracked-files=no 2>$null) {
        Write-Warning "$behind update(s) on GitHub, but files in this folder were edited. Not updating; commit or undo the edits first."
        return
    }
    if ($ahead -gt 0) {
        Write-Warning "$behind update(s) on GitHub and $ahead commit(s) here that are not on GitHub. Not updating automatically."
        return
    }
    $changed = git diff --name-only HEAD origin/main 2>$null
    git merge --ff-only --quiet origin/main 2>$null
    if ($LASTEXITCODE -ne 0) { Write-Warning "Could not update from GitHub: starting the version on this computer ($before)."; return }
    Write-Host "Updated from GitHub: $before -> $(git rev-parse --short HEAD 2>$null) ($behind new commit(s))."
    if ($changed -match '^(requirements|setup\.ps1)') {
        Write-Warning 'The package list changed. Run setup.ps1 once to install the new packages.'
    }
}
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
if (-not $NoUpdate) { Update-FromGitHub }
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
