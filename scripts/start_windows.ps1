# Start FinAlly in Docker (Windows PowerShell). Safe to run repeatedly.
#
#   .\scripts\start_windows.ps1           # build the image if missing, then (re)start the container
#   .\scripts\start_windows.ps1 -Build    # rebuild the image first
#   .\scripts\start_windows.ps1 -NoOpen   # don't open a browser
[CmdletBinding()]
param(
    [switch]$Build,
    [switch]$NoOpen
)

# Not 'Stop': Windows PowerShell 5.1 turns a native command's redirected stderr into a
# terminating error under 'Stop'. Exit codes are checked through $LASTEXITCODE instead.

$Image = 'finally'
$Container = 'finally'
$Volume = 'finally-data'
$Port = if ($env:FINALLY_PORT) { $env:FINALLY_PORT } else { '8000' }
$Url = "http://localhost:$Port"

$Root = Split-Path -Parent $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error 'Docker is not installed. Get it from https://docs.docker.com/get-docker/'
    exit 1
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Error 'Docker is not running. Start Docker Desktop and try again.'
    exit 1
}

docker image inspect $Image *> $null
if ($Build -or $LASTEXITCODE -ne 0) {
    Write-Host "Building the $Image image (the first build takes a few minutes)..."
    docker build -t $Image $Root
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

# Replace any existing container so a new image or .env takes effect. The data lives in the volume.
docker container inspect $Container *> $null
if ($LASTEXITCODE -eq 0) {
    docker stop $Container *> $null
    docker rm $Container *> $null
}

$EnvFile = Join-Path $Root '.env'
$RunArgs = @('run', '-d', '--name', $Container, '-p', "${Port}:8000", '-v', "${Volume}:/app/db")
if (Test-Path $EnvFile) {
    $RunArgs += @('--env-file', $EnvFile)
} else {
    Write-Host 'No .env found: running with the market simulator and AI chat off.'
    Write-Host 'To enable chat: copy .env.example to .env, then add your OPENROUTER_API_KEY.'
}
$RunArgs += $Image

docker @RunArgs > $null
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host -NoNewline 'Waiting for FinAlly to start'
$Ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        Invoke-WebRequest -Uri "$Url/api/health" -UseBasicParsing -TimeoutSec 2 *> $null
        $Ready = $true
        break
    } catch {
        $Running = docker container inspect -f '{{.State.Running}}' $Container 2> $null
        if ($Running -ne 'true') { break }
        Write-Host -NoNewline '.'
        Start-Sleep -Seconds 1
    }
}
Write-Host ''

if (-not $Ready) {
    Write-Host 'FinAlly did not become healthy. Recent logs:'
    docker logs --tail 40 $Container
    exit 1
}

Write-Host "FinAlly is running at $Url"
Write-Host "Stop it with .\scripts\stop_windows.ps1 (your data is kept in the '$Volume' volume)."

if (-not $NoOpen) {
    Start-Process $Url
}
