@echo off
setlocal
cd /d "%~dp0"
if exist "FileBridgeAgent.exe" (
  "FileBridgeAgent.exe" stop-service
  "FileBridgeAgent.exe" uninstall-service
) else (
  python agent.py stop-service
  python agent.py uninstall-service
)
endlocal
