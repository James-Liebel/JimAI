# Run once as Administrator
# Configures Windows to stay awake with lid closed

Write-Host "Configuring power settings for always-on operation..." -ForegroundColor Cyan

# Set lid close action to "Do Nothing" for both battery and plugged in
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
powercfg /setdcvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0

# Disable sleep when plugged in
powercfg /change standby-timeout-ac 0

# Disable hibernation when plugged in
powercfg /change hibernate-timeout-ac 0

# Keep display off is fine (saves power) but system stays awake
powercfg /change monitor-timeout-ac 10

# Apply changes
powercfg /setactive SCHEME_CURRENT

Write-Host "Done. Your PC will now stay awake with the lid closed." -ForegroundColor Green
Write-Host "Note: Plug in the charger -- do not rely on battery for always-on operation." -ForegroundColor Yellow
Write-Host ""
Write-Host "To revert: Settings -> System -> Power -> Sleep -> change back to your preference." -ForegroundColor Gray
