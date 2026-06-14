@echo off
setlocal EnableDelayedExpansion
set BATCHHOST_REGISTRATION_SECRET=ae7c3994358fe40af3990bfecf2752f3

set AGENT_DIR=%~dp0
set AGENT_EXE_NAME=batchHost-Pro_Agent.exe
set AGENT_EXE_PATH=%AGENT_DIR%%AGENT_EXE_NAME%

if exist "%AGENT_DIR%agent_runtime.py" (
    :: Find Python (prefer local venv for dependencies like psutil)
    set PYTHON_EXE=
    if exist "%AGENT_DIR%venv\Scripts\python.exe" (
        set "PYTHON_EXE=%AGENT_DIR%venv\Scripts\python.exe"
    ) else (
        where python >nul 2>nul
        if not errorlevel 1 (
            for /f "tokens=*" %%i in ('where python') do (
                set "POTENTIAL=%%i"
                if "!POTENTIAL:~-10!"=="python.exe" set "PYTHON_EXE=%%i"
            )
        )
        
        if "!PYTHON_EXE!"=="" (
            where py >nul 2>nul
            if not errorlevel 1 (
                for /f "tokens=*" %%i in ('where py') do set PYTHON_EXE=%%i
            )
        )
    )

    if not "!PYTHON_EXE!"=="" (
        :: Determine directory of the chosen python
        for %%F in ("!PYTHON_EXE!") do set "PYTHON_DIR=%%~dpF"
        
        :: Create custom-named executable inside the same directory (crucial for venv)
        set "CUSTOM_AGENT_EXE=!PYTHON_DIR!!AGENT_EXE_NAME!"
        
        if not exist "!CUSTOM_AGENT_EXE!" (
            echo Creating custom agent process: !AGENT_EXE_NAME! in !PYTHON_DIR!
            copy "!PYTHON_EXE!" "!CUSTOM_AGENT_EXE!" >nul
        )
        
        echo [%DATE% %TIME%] Starting Agent as !AGENT_EXE_NAME!... >> "%AGENT_DIR%logs\agent.log"
        echo Starting Agent as !AGENT_EXE_NAME!...
        
        :AGENT_LOOP
        "!CUSTOM_AGENT_EXE!" "%AGENT_DIR%agent_runtime.py" daemon
        set AGENT_EXIT_CODE=!ERRORLEVEL!
        
        if !AGENT_EXIT_CODE! NEQ 0 (
            echo [%DATE% %TIME%] Agent exited with code !AGENT_EXIT_CODE!. Restarting in 5s... >> "%AGENT_DIR%logs\agent.log"
            echo Agent exited with code !AGENT_EXIT_CODE!. Restarting in 5s...
            timeout /t 5 >nul
            goto AGENT_LOOP
        )
        echo [%DATE% %TIME%] Agent exited normally. >> "%AGENT_DIR%logs\agent.log"
        exit /b 0
    )
    echo Python 3 not found. Falling back to legacy heartbeat agent.
)

set SERVER_URL=https://172.100.30.191:5000
set HEARTBEAT_INTERVAL=10
set AGENT_STATE_DIR=%ProgramData%\BatchHost-Pro\Agent
if "%ProgramData%"=="" set AGENT_STATE_DIR=%LOCALAPPDATA%\BatchHost-Pro\Agent
if not exist "%AGENT_STATE_DIR%" mkdir "%AGENT_STATE_DIR%" 2>nul
if not exist "%AGENT_STATE_DIR%" set AGENT_STATE_DIR=%LOCALAPPDATA%\BatchHost-Pro\Agent
if not exist "%AGENT_STATE_DIR%" mkdir "%AGENT_STATE_DIR%" 2>nul
set AGENT_ID_FILE=%AGENT_STATE_DIR%\agent_id.dat
set TOKEN_FILE=%AGENT_STATE_DIR%\agent_token.dat
set LOG_DIR=%AGENT_STATE_DIR%\logs
set LOG_FILE=%LOG_DIR%\agent.log
set RETRY_COUNT=0
set MAX_RETRIES=5
set BACKOFF=5

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" 2>nul

if "!SERVER_URL!"=="" (
    echo ERROR: SERVER_URL not configured
    echo [%DATE% %TIME%] ERROR: SERVER_URL not configured.>>"!LOG_FILE!"
    pause
    exit /b 1
)

if exist "%AGENT_ID_FILE%" (
    set /p AGENT_ID=<"%AGENT_ID_FILE%"
) else (
    call :NEW_AGENT_ID
)

for /f "tokens=*" %%i in ('hostname') do set HOSTNAME=%%i
for /f "delims=" %%i in ('powershell -ExecutionPolicy Bypass -NoProfile -Command "try { (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Cryptography').MachineGuid } catch { $env:COMPUTERNAME }"') do set DEVICE_KEY=%%i

echo [%DATE% %TIME%] Agent starting on !HOSTNAME! (ID: !AGENT_ID!)>>"!LOG_FILE!"
echo Starting agent on !HOSTNAME!...

:REGISTER
if "!RETRY_COUNT!" GEQ "!MAX_RETRIES!" (
    echo [%DATE% %TIME%] ERROR: Max retries reached. Exiting...>>"!LOG_FILE!"
    exit /b 1
)

set /a RETRY_COUNT+=1
set /a BACKOFF=!BACKOFF!*2

echo Registering with server (Attempt !RETRY_COUNT!)...
set TEMP_PS=%TEMP%\batchhost_register_!RANDOM!.ps1
(
    echo $ErrorActionPreference = 'Stop'
    echo [System.Net.ServicePointManager]::ServerCertificateValidationCallback = {$true}
    echo $body = @{ agent_id='!AGENT_ID!'; hostname='!HOSTNAME!'; os_type='windows'; device_key='!DEVICE_KEY!' } ^| ConvertTo-Json
    echo $uri = '!SERVER_URL!/api/agent/register'
    echo try {
    echo     $response = Invoke-RestMethod -Uri $uri -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 10
    echo     Write-Output "$($response.token)|$($response.agent_id)"
    echo } catch {
    echo     if ^($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 409^) {
    echo         Write-Output 'DUPLICATE'
    echo     } else {
    echo         Write-Output 'FAILED'
    echo     }
    echo }
) > "!TEMP_PS!"

for /f "delims=" %%i in ('powershell -ExecutionPolicy Bypass -NoProfile -File "!TEMP_PS!"') do set REGISTER_RESPONSE=%%i
if exist "!TEMP_PS!" del /q "!TEMP_PS!"

set TOKEN=!REGISTER_RESPONSE!
set REGISTERED_AGENT_ID=
for /f "tokens=1,2 delims=|" %%a in ("!REGISTER_RESPONSE!") do (
    set TOKEN=%%a
    set REGISTERED_AGENT_ID=%%b
)

if "!TOKEN!"=="FAILED" (
    echo [%DATE% %TIME%] Registration failed. Retrying in !BACKOFF! seconds...>>"!LOG_FILE!"
    timeout /t !BACKOFF! >nul
    goto REGISTER
)

if "!TOKEN!"=="DUPLICATE" (
    echo [%DATE% %TIME%] Duplicate agent ID !AGENT_ID! rejected by server. Creating a new per-device ID...>>"!LOG_FILE!"
    call :NEW_AGENT_ID
    set RETRY_COUNT=0
    set BACKOFF=5
    goto REGISTER
)

if "!TOKEN!"=="" (
    echo [%DATE% %TIME%] Registration failed: empty response.>>"!LOG_FILE!"
    goto :RETRY_REG
)

if "!TOKEN!"=="FAILED" (
    echo [%DATE% %TIME%] Registration failed: server connection error.>>"!LOG_FILE!"
    goto :RETRY_REG
)

echo Registration successful!
if not "!REGISTERED_AGENT_ID!"=="" if not "!REGISTERED_AGENT_ID!"=="!AGENT_ID!" (
    echo [%DATE% %TIME%] Server mapped this device to existing agent ID !REGISTERED_AGENT_ID!.>>"!LOG_FILE!"
    set AGENT_ID=!REGISTERED_AGENT_ID!
    (echo !AGENT_ID!)>"%AGENT_ID_FILE%"
)
echo [%DATE% %TIME%] Registered successfully. Token: !TOKEN:~0,8!...>>"!LOG_FILE!"
(echo !TOKEN!)>"%TOKEN_FILE%"
echo Agent running. Close window to stop.
goto :HEARTBEAT_LOOP

:RETRY_REG
echo [%DATE% %TIME%] Registration failed. Retrying in 15s...>>"!LOG_FILE!"
timeout /t 15 /nobreak >nul
goto :REGISTER

:HEARTBEAT_LOOP
set CPU=0
for /f "skip=1 tokens=1" %%i in ('wmic cpu get LoadPercentage 2^>nul') do (
    if not "%%i"=="" set CPU=%%i
    goto :GOT_CPU
)
:GOT_CPU

set MEM_USED_PCT=50

set HB_PS=%TEMP%\batchhost_heartbeat_!RANDOM!.ps1
(
    echo $ErrorActionPreference = 'SilentlyContinue'
    echo [System.Net.ServicePointManager]::ServerCertificateValidationCallback = {$true}
    echo $running = @()
    echo $scriptExtensions = @('.bat', '.cmd', '.ps1')
    echo $seen = @{}
    echo foreach ($proc in Get-CimInstance Win32_Process) {
    echo     $cl = $proc.CommandLine
    echo     if (-not $cl) { continue }
    echo     foreach ($ext in $scriptExtensions) {
    echo         $pattern = '([A-Za-z]:\\(?:[^\\"<>|*?\r\n]+\\)*[^\\"<>|*?\r\n]+\' + $ext + ')'
    echo         if ($cl -match $pattern) {
    echo             $path = $matches[1]
    echo             if ($path -notmatch 'batchhost-pro_agent' -and -not $seen.ContainsKey($path)) {
    echo                 $seen[$path] = $true
    echo                 $running += $path
    echo             }
    echo             break
    echo         }
    echo     }
    echo     if ($running.Count -ge 20) { break }
    echo }
    echo $body = @{ token='!TOKEN!'; hostname='!HOSTNAME!'; cpu=!CPU!; memory=!MEM_USED_PCT!; running_scripts=$running } ^| ConvertTo-Json
    echo $uri = '!SERVER_URL!/api/agent/heartbeat'
    echo try {
    echo     Invoke-RestMethod -Uri $uri -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 5 ^| Out-Null
    echo     Write-Host '.' -NoNewline
    echo } catch {
    echo     Write-Host 'E' -NoNewline -ForegroundColor Red
    echo }
) > "!HB_PS!"

powershell -ExecutionPolicy Bypass -NoProfile -File "!HB_PS!" 2>nul

if exist "!HB_PS!" del /q "!HB_PS!"

echo [%DATE% %TIME%] Heartbeat sent. CPU=!CPU!%% MEM=!MEM_USED_PCT!%%>>"!LOG_FILE!"
title BatchHost-Pro Agent - !HOSTNAME! [CPU: !CPU!%% MEM: !MEM_USED_PCT!%%]

timeout /t %HEARTBEAT_INTERVAL% /nobreak >nul
goto :HEARTBEAT_LOOP

:NEW_AGENT_ID
for /f "delims=" %%i in ('powershell -ExecutionPolicy Bypass -NoProfile -Command "[guid]::NewGuid().ToString()"') do set AGENT_ID=%%i
(echo !AGENT_ID!)>"%AGENT_ID_FILE%"
exit /b 0
