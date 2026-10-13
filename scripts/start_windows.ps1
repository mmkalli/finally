# Start FinAlly in Docker (Windows PowerShell). Safe to run repeatedly.
#
# Usage: .\scripts\start_windows.ps1 [-Build] [-NoOpen]
#   -Build   rebuild the image even if it already exists
#   -NoOpen  don't open the browser
param(
    [switch]$Build,
    [switch]$NoOpen
)

$ErrorActionPreference = 'Stop'

$Image = 'finally'
$Container = 'finally'
$Volume = 'finally-data'
$Port = if ($env:FINALLY_PORT) { $env:FINALLY_PORT } else { '8000' }
$Url = "http://localhost:$Port"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Test-DockerOk {
    # Run a docker command quietly and report whether it succeeded
    param([string[]]$DockerArgs)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & docker @DockerArgs *> $null
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $prev
    return $ok
}

if (-not (Test-DockerOk @('info'))) {
    Write-Error 'Docker is not running. Start Docker Desktop and try again.'
    exit 1
}

if ($Build -or -not (Test-DockerOk @('image', 'inspect', $Image))) {
    Write-Host "Building image '$Image'..."
    docker build -t $Image .
    if ($LASTEXITCODE -ne 0) { Write-Error 'docker build failed.'; exit 1 }
}

# Replace any existing container (running or stopped); the volume is kept
if (Test-DockerOk @('container', 'inspect', $Container)) {
    Write-Host "Removing existing container '$Container'..."
    docker rm -f $Container | Out-Null
}

$runArgs = @('run', '-d', '--name', $Container, '-p', "${Port}:8000", '-v', "${Volume}:/app/db")
if (Test-Path (Join-Path $Root '.env')) {
    $runArgs += @('--env-file', '.env')
} else {
    Write-Host 'Note: no .env file found, starting without one (simulator data, AI chat disabled).'
    Write-Host '      To configure: Copy-Item .env.example .env  and set OPENROUTER_API_KEY, then rerun.'
}
$runArgs += $Image

docker @runArgs | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Error 'docker run failed.'; exit 1 }

Write-Host -NoNewline 'Waiting for FinAlly to start'
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri "$Url/api/health" -UseBasicParsing -TimeoutSec 2
        if ($resp.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
    $running = docker inspect -f '{{.State.Running}}' $Container 2>$null
    if ($running -ne 'true') {
        Write-Host ''
        Write-Host 'Container exited. Logs:'
        docker logs $Container
        exit 1
    }
    Write-Host -NoNewline '.'
    Start-Sleep -Seconds 1
}
Write-Host $(if ($ready) { ' ready.' } else { ' (still starting, check: docker logs finally)' })

Write-Host "FinAlly is running at $Url"
Write-Host "Stop it with .\scripts\stop_windows.ps1 (your data is kept in the '$Volume' volume)."

if (-not $NoOpen) {
    Start-Process $Url
}
