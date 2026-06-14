@echo off
title Infinite Long Running Script
color 0A

echo ==========================================
echo   Long Running Batch Script Started
echo   Press CTRL + C or close the window
echo   to stop the script manually.
echo ==========================================
echo.

:loop
echo [%date% %time%] Script is still running...

:: Wait for 5 seconds
timeout /t 5 /nobreak > nul

goto loop