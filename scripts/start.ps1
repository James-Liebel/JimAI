$root = Split-Path $PSScriptRoot -Parent

Write-Host "Starting Private AI System..." -ForegroundColor Cyan

# Check Ollama
try {
    Invoke-RestMethod -Uri "http://localhost:11434/api/tags" | Out-Null
    Write-Host "Ollama: Running" -ForegroundColor Green
} catch {
    Write-Host "Ollama not running. Starting..." -ForegroundColor Yellow
    Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep 3
}

# ── Model verification ─────────────────────────────────────────────
$requiredModels = @(
    "deepseek-r1:14b",
    "qwen2.5-coder:14b",
    "qwen3:8b",
    "qwen2.5vl:7b",
    "qwen2-math:7b-instruct",
    "qwen2.5-coder:7b",
    "nomic-embed-text"
)

$optionalModels = @("qwen2.5:32b")

try {
    $installedModels = (ollama list 2>$null) -join " "
} catch {
    $installedModels = ""
}

Write-Host ""
Write-Host "Model status:" -ForegroundColor Cyan
foreach ($model in $requiredModels) {
    $shortName = ($model -split ":")[0]
    if ($installedModels -match [regex]::Escape($shortName)) {
        Write-Host "  + $model" -ForegroundColor Green
    } else {
        Write-Host "  x $model  <- run: ollama pull $model" -ForegroundColor Red
    }
}

Write-Host "Optional (Deep mode):" -ForegroundColor Gray
foreach ($model in $optionalModels) {
    $shortName = ($model -split ":")[0]
    if ($installedModels -match [regex]::Escape($shortName)) {
        Write-Host "  + $model" -ForegroundColor Green
    } else {
        Write-Host "  - $model not installed (run: ollama pull $model to enable Deep mode)" -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host "Checking system agent dependencies..." -ForegroundColor Cyan
$backendPath = Join-Path $PSScriptRoot "..\backend"
$backendPython = Join-Path $backendPath ".venv\Scripts\python.exe"
$packages = @("psutil", "mss", "PIL")
foreach ($pkg in $packages) {
    & $backendPython -c "import $pkg" 2>$null
    if ($LASTEXITCODE -ne 0) {
        $installName = if ($pkg -eq "PIL") { "pillow" } else { $pkg.ToLower() }
        Write-Host "  Installing $installName..." -ForegroundColor Yellow
        & $backendPython -m pip install $installName --quiet
    } else {
        Write-Host "  [OK] $pkg" -ForegroundColor Green
    }
}

# Playwright Chromium (Chat browser capture, Agent Space)
if (Test-Path $backendPython) {
    Write-Host "Checking Playwright Chromium..." -ForegroundColor Cyan
    $checkPw = Join-Path $PSScriptRoot "check_playwright_chromium.py"
    & $backendPython $checkPw 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Installing Playwright + Chromium..." -ForegroundColor Yellow
        $setupPw = Join-Path $PSScriptRoot "setup_playwright.py"
        & $backendPython $setupPw
    } else {
        Write-Host "  [OK] Playwright Chromium" -ForegroundColor Green
    }
}

# Start backend (bind to 0.0.0.0 for Tailscale access)
# Use the backend's virtualenv Python explicitly so dependencies and versions are correct.
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$backendPath'; & '$backendPython' -m uvicorn main:app --reload --host 0.0.0.0 --port 8000"

Start-Sleep 2

# Start frontend
$frontendPath = Join-Path $PSScriptRoot "..\frontend"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$frontendPath'; npm run dev"

Write-Host ""
Write-Host "Services starting:" -ForegroundColor Cyan
Write-Host "  Backend:  http://localhost:8000" -ForegroundColor White
Write-Host "  Frontend: http://localhost:5173" -ForegroundColor White
Write-Host "  Ollama:   http://localhost:11434" -ForegroundColor White

# Show Tailscale mobile URL if available
Start-Sleep 2
try {
    $tailscaleIP = (& tailscale ip --4 2>$null).Trim()
    if ($tailscaleIP) {
        Write-Host ""
        Write-Host "Mobile (Tailscale): http://$tailscaleIP`:5173" -ForegroundColor Magenta
    }
} catch {}

# Start keep-alive background process
Start-Process powershell -ArgumentList "-WindowStyle Hidden -Command `"& '$root\scripts\keep_alive.ps1'`""

Write-Host ""
Write-Host "Speed modes: Fast (7-8B) | Balanced (14B) | Deep (32B)" -ForegroundColor Gray
Write-Host "Run 'python scripts/test_models.py' to verify all models." -ForegroundColor Gray
