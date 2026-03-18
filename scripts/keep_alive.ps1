# Keeps services from going idle — pings backend every 20 minutes
while ($true) {
    try {
        Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 5 | Out-Null
        Write-Host "$(Get-Date -Format 'HH:mm') - Services alive" -ForegroundColor DarkGray
    } catch {
        Write-Host "$(Get-Date -Format 'HH:mm') - Backend not responding" -ForegroundColor Yellow
    }
    Start-Sleep 1200
}
