# Stop FinAlly (Windows PowerShell). Safe to run repeatedly. The 'finally-data' volume is kept.
$Container = 'finally'

$ErrorActionPreference = 'Continue'
docker container inspect $Container *> $null
if ($LASTEXITCODE -eq 0) {
    docker rm -f $Container | Out-Null
    Write-Host "FinAlly stopped. Data is kept in the 'finally-data' volume."
} else {
    Write-Host 'FinAlly is not running.'
}
