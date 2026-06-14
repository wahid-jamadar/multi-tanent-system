@echo off
setlocal
cd /d "%~dp0"
if exist "FileBridgeAgent.exe" (
  "FileBridgeAgent.exe" install-service
  "FileBridgeAgent.exe" start-service
) else (
  python agent.py install-service
  python agent.py start-service
)
endlocal
