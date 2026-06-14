<#
.SYNOPSIS
    FileBridge Agent Windows Service Management Script.
.DESCRIPTION
    A dynamic, path-independent script to install, uninstall, start, stop, restart,
    and monitor the FileBridge Agent Windows Service wrapped by WinSW.
#>
param(
    [Parameter(Position=0)]
    [ValidateSet("install", "uninstall", "start", "stop", "restart", "status")]
    [string]$Action
)

$ServiceName = "FileBridgeAgent"
$ServiceExe = Join-Path $PSScriptRoot "FileBridgeAgentService.exe"
$ServiceXml = Join-Path $PSScriptRoot "FileBridgeAgentService.xml"
$AgentExe = Join-Path $PSScriptRoot "FileBridgeAgent.exe"
$ConfigYaml = Join-Path $PSScriptRoot "config.yaml"

# Helper for formatted console outputs
function Write-Header ($Text) {
    Write-Host ""
    Write-Host "=== $Text ===" -ForegroundColor Cyan
}

function Write-Success ($Text) {
    Write-Host "[SUCCESS] $Text" -ForegroundColor Green
}

function Write-Info ($Text) {
    Write-Host "[INFO] $Text" -ForegroundColor White
}

function Write-Err ($Text) {
    Write-Host "[ERROR] $Text" -ForegroundColor Red -ErrorAction Continue
}

# 1. Require Administrative privileges for modifying actions
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin -and ($Action -in @("install", "uninstall", "start", "stop", "restart"))) {
    Write-Header "ELEVATION REQUIRED"
    Write-Err "This action '$Action' requires administrative privileges."
    Write-Info "Please relaunch PowerShell as Administrator and run the script again."
    Write-Host ""
    exit 1
}

# 2. Default to showing status/help if no action is provided
if (-not $Action) {
    Write-Header "FileBridge Agent Service Manager"
    Write-Host "Usage:"
    Write-Host "  .\manage_service.ps1 install     - Install and start the FileBridge Windows Service"
    Write-Host "  .\manage_service.ps1 uninstall   - Stop and cleanly remove the service"
    Write-Host "  .\manage_service.ps1 start       - Start the service if stopped"
    Write-Host "  .\manage_service.ps1 stop        - Stop the running service"
    Write-Host "  .\manage_service.ps1 restart     - Restart the service"
    Write-Host "  .\manage_service.ps1 status      - Check service installation and running state"
    Write-Host ""
    
    # Prompt the user for an action in interactive sessions
    if ([Environment]::UserInteractive) {
        $Choice = Read-Host "Select action (install/uninstall/start/stop/restart/status)"
        if ($Choice -in @("install", "uninstall", "start", "stop", "restart", "status")) {
            $Action = $Choice
        } else {
            Write-Info "Invalid action selected. Showing status."
            $Action = "status"
        }
    } else {
        $Action = "status"
    }
}

# 3. Validation Check: Ensure all bundle files exist
function Verify-Dependencies {
    $Files = @(
        @{ Name = "WinSW Service Wrapper"; Path = $ServiceExe },
        @{ Name = "WinSW Configuration"; Path = $ServiceXml },
        @{ Name = "FileBridge Agent Executable"; Path = $AgentExe },
        @{ Name = "Agent YAML Configuration"; Path = $ConfigYaml }
    )
    
    $AllOk = $true
    foreach ($File in $Files) {
        if (-not (Test-Path $File.Path)) {
            Write-Err "Required component missing: $($File.Name) ($($File.Path))"
            $AllOk = $false
        }
    }
    
    if (-not $AllOk) {
        Write-Err "Self-contained folder structure is incomplete. Cannot proceed."
        exit 1
    }
}

# 4. Extract and check backend URL from config.yaml
function Test-BackendConnection {
    if (Test-Path $ConfigYaml) {
        $ConfigContent = Get-Content $ConfigYaml -Raw
        $BackendUrl = $null
        if ($ConfigContent -match "backend_url:\s*`"?(https?://[^\s#`"]+)`"?") {
            $BackendUrl = $Matches[1]
        } elseif ($ConfigContent -match "url:\s*`"?(https?://[^\s#`"]+)`"?") {
            $BackendUrl = $Matches[1]
        }
        
        if ($BackendUrl) {
            Write-Info "Extracted Backend URL from config.yaml: $BackendUrl"
            Write-Info "Verifying network reachability (bypassing SSL errors)..."
            
            # Save original callback and set to trust all certificates
            $OriginalCallback = [System.Net.ServicePointManager]::ServerCertificateValidationCallback
            try {
                [System.Net.ServicePointManager]::ServerCertificateValidationCallback = {$true}
                
                # Check backend status endpoint or base register URL
                $Timer = [System.Diagnostics.Stopwatch]::StartNew()
                $Response = Invoke-WebRequest -Uri "$BackendUrl/api/agents/register" -Method Post -Body "{}" -ContentType "application/json" -TimeoutSec 5 -ErrorAction SilentlyContinue
                $Timer.Stop()
                
                # If we get here, connection succeeded (even if 400 Bad Request/401/409, it means the server responded)
                Write-Success "Backend is active and responsive! Roundtrip latency: $($Timer.ElapsedMilliseconds)ms"
            } catch {
                Write-Host "[WARNING] Could not establish connection to FileBridge backend at $BackendUrl" -ForegroundColor Yellow
                Write-Host "          Error: $($_.Exception.Message)" -ForegroundColor Yellow
                Write-Host "          The service will still be installed, but it may fail to connect until backend is active." -ForegroundColor Yellow
            } finally {
                [System.Net.ServicePointManager]::ServerCertificateValidationCallback = $OriginalCallback
            }
        } else {
            Write-Host "[WARNING] Could not find backend_url in config.yaml. Skipping reachability check." -ForegroundColor Yellow
        }
    }
}

# 5. Service Status Checking helper
function Get-ServiceStatus {
    $Service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($Service) {
        return @{
            Installed = $true
            Status = $Service.Status
            Running = ($Service.Status -eq "Running")
        }
    } else {
        return @{
            Installed = $false
            Status = "Not Installed"
            Running = $false
        }
    }
}

# Handle actions
switch ($Action) {
    "install" {
        Write-Header "Installing FileBridge Agent Service"
        Verify-Dependencies
        Test-BackendConnection
        
        $ServiceState = Get-ServiceStatus
        if ($ServiceState.Installed) {
            Write-Info "Existing service instance '$ServiceName' detected. Stopping and removing it first..."
            & $ServiceExe stop | Out-Null
            Start-Sleep -Seconds 1
            & $ServiceExe uninstall | Out-Null
            Start-Sleep -Seconds 1
            Write-Success "Previous service instance uninstalled successfully."
        }
        
        # Ensure logs directory exists
        $LogsDir = Join-Path $PSScriptRoot "logs"
        if (-not (Test-Path $LogsDir)) {
            New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
        }
        
        Write-Info "Registering Windows Service via WinSW..."
        & $ServiceExe install
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Service registered successfully!"
            Write-Info "Starting service..."
            & $ServiceExe start
            
            # Wait for service status verification
            Start-Sleep -Seconds 2
            $ServiceState = Get-ServiceStatus
            if ($ServiceState.Running) {
                Write-Success "FileBridge Agent service is now active and running!"
                Write-Info "The agent is configured to automatically launch on system boot."
            } else {
                Write-Err "Service installed but failed to start cleanly. Check logs/agent.log or logs/FileBridgeAgent.wrapper.log for errors."
            }
        } else {
            Write-Err "Failed to register Windows Service. Check WinSW logs."
        }
    }
    
    "uninstall" {
        Write-Header "Uninstalling FileBridge Agent Service"
        $ServiceState = Get-ServiceStatus
        if (-not $ServiceState.Installed) {
            Write-Info "The FileBridge Agent service is not installed on this machine."
            exit 0
        }
        
        if ($ServiceState.Running) {
            Write-Info "Stopping active service..."
            & $ServiceExe stop
            Start-Sleep -Seconds 1
        }
        
        Write-Info "Deregistering service..."
        & $ServiceExe uninstall
        if ($LASTEXITCODE -eq 0) {
            Write-Success "FileBridge Agent service uninstalled successfully!"
        } else {
            Write-Err "Failed to uninstall service."
        }
    }
    
    "start" {
        Write-Header "Starting FileBridge Agent Service"
        $ServiceState = Get-ServiceStatus
        if (-not $ServiceState.Installed) {
            Write-Err "Service is not installed. Run '.\manage_service.ps1 install' first."
            exit 1
        }
        if ($ServiceState.Running) {
            Write-Info "Service is already running."
            exit 0
        }
        
        & $ServiceExe start
        Start-Sleep -Seconds 1
        $ServiceState = Get-ServiceStatus
        if ($ServiceState.Running) {
            Write-Success "Service started successfully!"
        } else {
            Write-Err "Failed to start service."
        }
    }
    
    "stop" {
        Write-Header "Stopping FileBridge Agent Service"
        $ServiceState = Get-ServiceStatus
        if (-not $ServiceState.Installed) {
            Write-Info "Service is not installed."
            exit 0
        }
        if (-not $ServiceState.Running) {
            Write-Info "Service is already stopped."
            exit 0
        }
        
        & $ServiceExe stop
        Start-Sleep -Seconds 1
        $ServiceState = Get-ServiceStatus
        if (-not $ServiceState.Running) {
            Write-Success "Service stopped successfully!"
        } else {
            Write-Err "Failed to stop service."
        }
    }
    
    "restart" {
        Write-Header "Restarting FileBridge Agent Service"
        $ServiceState = Get-ServiceStatus
        if (-not $ServiceState.Installed) {
            Write-Err "Service is not installed. Run '.\manage_service.ps1 install' first."
            exit 1
        }
        
        Write-Info "Restarting service..."
        & $ServiceExe restart
        Start-Sleep -Seconds 2
        $ServiceState = Get-ServiceStatus
        if ($ServiceState.Running) {
            Write-Success "Service restarted successfully!"
        } else {
            Write-Err "Failed to restart service."
        }
    }
    
    "status" {
        Write-Header "FileBridge Agent Service Status"
        $ServiceState = Get-ServiceStatus
        
        Write-Host "Service Name:      " -NoNewline
        Write-Host $ServiceName -ForegroundColor Cyan
        
        Write-Host "Installation Dir:  " -NoNewline
        Write-Host $PSScriptRoot -ForegroundColor Gray
        
        Write-Host "Service Wrapper:   " -NoNewline
        if (Test-Path $ServiceExe) {
            Write-Host "Detected ($ServiceExe)" -ForegroundColor Green
        } else {
            Write-Host "NOT FOUND" -ForegroundColor Red
        }
        
        Write-Host "Service Config:    " -NoNewline
        if (Test-Path $ServiceXml) {
            Write-Host "Detected ($ServiceXml)" -ForegroundColor Green
        } else {
            Write-Host "NOT FOUND" -ForegroundColor Red
        }
        
        Write-Host "Agent Binary:      " -NoNewline
        if (Test-Path $AgentExe) {
            Write-Host "Detected ($AgentExe)" -ForegroundColor Green
        } else {
            Write-Host "NOT FOUND" -ForegroundColor Red
        }
        
        Write-Host "Status:            " -NoNewline
        if ($ServiceState.Installed) {
            if ($ServiceState.Running) {
                Write-Host "Running" -ForegroundColor Green
            } else {
                Write-Host "Stopped" -ForegroundColor Yellow
            }
        } else {
            Write-Host "Not Installed" -ForegroundColor Red
        }
        
        # Display backend URL if exists
        if (Test-Path $ConfigYaml) {
            $ConfigContent = Get-Content $ConfigYaml -Raw
            if ($ConfigContent -match "backend_url:\s*`"?(https?://[^\s#`"]+)`"?") {
                Write-Host "Backend URL:       " -NoNewline
                Write-Host $Matches[1] -ForegroundColor White
            }
        }
        
        # Show recent logs if log file exists
        $LogFile = Join-Path $PSScriptRoot "logs\agent.log"
        if (Test-Path $LogFile) {
            Write-Header "Recent Log Entries (logs\agent.log)"
            Get-Content $LogFile -Tail 10 | ForEach-Object {
                if ($_ -match "\[ERROR\]" -or $_ -match "Failed" -or $_ -match "error") {
                    Write-Host $_ -ForegroundColor Red
                } elseif ($_ -match "\[WARNING\]" -or $_ -match "warn") {
                    Write-Host $_ -ForegroundColor Yellow
                } else {
                    Write-Host $_ -ForegroundColor Gray
                }
            }
        } else {
            Write-Header "Log File"
            Write-Info "No logs detected at: logs\agent.log"
        }
        Write-Host ""
    }
}
