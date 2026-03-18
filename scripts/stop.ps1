# Stop Private AI — Ollama + GPU runner (for night shutdown)

Write-Host "Shutting down Private AI..." -ForegroundColor Cyan

# Ollama on Windows spawns a separate GPU process that often keeps VRAM in use after
# the main app quits. Kill every process whose name contains "ollama".
$ollamaProcesses = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -like "*ollama*" }
if ($ollamaProcesses) {
    $ollamaProcesses | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "  Ollama (and GPU runner): stopped" -ForegroundColor Green
} else {
    Write-Host "  Ollama: not running" -ForegroundColor Gray
}

# If GPU is still in use, another process may be holding it (e.g. Ollama's helper).
# Run: Get-Process | Where-Object { $_.ProcessName -match "ollama|llama|nvidia" }
# Or check Task Manager > Performance > GPU > "See which apps use your GPU"
Write-Host ""
Write-Host "If GPU is still in use: Task Manager > Performance > GPU, or run: nvidia-smi" -ForegroundColor Gray
Write-Host "To start again: .\scripts\start.ps1" -ForegroundColor Gray
