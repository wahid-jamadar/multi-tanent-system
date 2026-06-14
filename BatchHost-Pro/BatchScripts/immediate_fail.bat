@echo off
echo [%date% %time%] Immediate failure test script started.
echo [%date% %time%] Waiting 10 seconds to allow the dashboard to catch the state...
timeout /t 10 > nul
echo [%date% %time%] Simulating a critical error...
echo [%date% %time%] ERROR: Task failed successfully (Testing failure status).
exit /b 1
