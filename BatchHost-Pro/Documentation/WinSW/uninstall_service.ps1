$ErrorActionPreference = "Stop"

$AgentDir = "C:\BatchHost-Pro\agents"
$WinSWExe = "$AgentDir\batchhost-agent-service.exe"

Write-Host "Preparing to uninstall BatchHost-Pro Agent Windows Service..." -ForegroundColor Cyan

if (Test-Path $WinSWExe) {
    Write-Host "Stopping Windows Service..."
    & $WinSWExe stop
    
    Write-Host "Uninstalling Windows Service..."
    & $WinSWExe uninstall
    
    Write-Host "Service uninstalled successfully!" -ForegroundColor Green
} else {
    Write-Host "Service wrapper ($WinSWExe) not found. Is it installed?" -ForegroundColor Yellow
}
