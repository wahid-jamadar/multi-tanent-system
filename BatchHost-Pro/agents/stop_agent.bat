@echo off
echo Stopping BatchHost-Pro Agent...
wmic process where "name='cmd.exe' and commandline like '%%batchhost-pro_agent.bat%%'" call terminate
echo Agent stopped.
pause
