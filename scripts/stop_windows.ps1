# Stop and remove the FinAlly container (Windows PowerShell). Safe to run repeatedly.
# The finally-data volume is kept, so your portfolio survives the next start.

$Container = 'finally'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host 'Docker is not installed; nothing to stop.'
    exit 0
}

docker container inspect $Container *> $null
if ($LASTEXITCODE -eq 0) {
    docker stop $Container *> $null
    docker rm $Container *> $null
    Write-Host "FinAlly stopped. Data is kept in the 'finally-data' volume."
} else {
    Write-Host 'FinAlly is not running.'
}
