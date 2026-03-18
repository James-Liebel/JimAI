try {
    $tailscaleIP = (& tailscale ip --4 2>$null).Trim()
    if ($tailscaleIP) {
        Write-Host ""
        Write-Host "Mobile Access URLs:" -ForegroundColor Cyan
        Write-Host "  Web App:  http://$tailscaleIP`:5173" -ForegroundColor Green
        Write-Host "  Backend:  http://$tailscaleIP`:8000" -ForegroundColor Green
        Write-Host ""
        Write-Host "Add to iPhone: Safari -> http://$tailscaleIP`:5173 -> Share -> Add to Home Screen" -ForegroundColor Gray
        Write-Host ""
    } else {
        Write-Host "Tailscale not running. Start it from the system tray." -ForegroundColor Yellow
    }
} catch {
    Write-Host "Tailscale not installed. Download from tailscale.com/download" -ForegroundColor Red
}
