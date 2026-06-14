# PowerShell Automation Script - Rebuild, Package and Deploy FileBridge Agent
$ErrorActionPreference = "Stop"

# Helper for formatted console outputs
function Write-Success ($Text) {
    Write-Host "[SUCCESS] $Text" -ForegroundColor Green
}

Write-Host "=== FileBridge Agent Compilation & Packaging Pipeline ===" -ForegroundColor Cyan

# 1. Resolve all paths dynamically relative to this script directory
$AgentDir = $PSScriptRoot
$ProjectDir = Resolve-Path (Join-Path $AgentDir "..")
$VenvPyinstaller = Join-Path $ProjectDir ".venv\Scripts\pyinstaller.exe"
$SpecFile = Join-Path $AgentDir "FileBridgeAgent.spec"
$DistExe = Join-Path $AgentDir "dist\FileBridgeAgent.exe"
$DeployZip = Join-Path $AgentDir "FileBridgeAgent_DEPLOY.zip"
$LocalDeployDir = "C:\FileBridgeAgent"

Write-Host "[INFO] Agent Directory:      $AgentDir"
Write-Host "[INFO] Project Directory:    $ProjectDir"

# Validate PyInstaller presence
if (-not (Test-Path $VenvPyinstaller)) {
    Write-Host "[WARNING] Local venv PyInstaller not found at: $VenvPyinstaller" -ForegroundColor Yellow
    Write-Host "[INFO] Searching for pyinstaller in system environment..."
    $VenvPyinstaller = (Get-Command pyinstaller.exe -ErrorAction SilentlyContinue).Source
}

if (-not $VenvPyinstaller) {
    Write-Error "PyInstaller executable could not be resolved! Please ensure virtual environment or global PyInstaller is installed."
    exit 1
}
Write-Host "[INFO] Using PyInstaller:    $VenvPyinstaller"

# 2. Build the updated FileBridgeAgent using PyInstaller
Write-Host "`n1. Building updated FileBridgeAgent using PyInstaller..." -ForegroundColor Cyan
Set-Location -Path $AgentDir
& $VenvPyinstaller FileBridgeAgent.spec

# Check compilation outcome
if (-not (Test-Path $DistExe)) {
    Write-Error "PyInstaller compilation failed! The expected binary was not found at $DistExe"
    exit 1
}
Write-Host "[SUCCESS] Agent successfully compiled at: $DistExe" -ForegroundColor Green

# 3. Stop existing local service or process before overwriting
Write-Host "`n2. Checking and stopping any running local FileBridge Agent..." -ForegroundColor Cyan
try {
    $Service = Get-Service -Name "FileBridgeAgent" -ErrorAction SilentlyContinue
    if ($Service -and $Service.Status -eq "Running") {
        Write-Host "[INFO] Stopping local FileBridgeAgent service..."
        Stop-Service -Name "FileBridgeAgent" -Force -ErrorAction Stop
        Start-Sleep -Seconds 2
    } else {
        Write-Host "[INFO] Stopping any loose FileBridgeAgent background processes..."
        Get-Process -Name FileBridgeAgent -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction Stop
        Start-Sleep -Seconds 1
    }
} catch {
    Write-Warning "Could not stop local service/process (permissions or not running). Proceeding..."
}

# 4. Deploy updated service package to local directory for developer testing (C:\FileBridgeAgent)
Write-Host "`n3. Deploying self-contained package locally to $LocalDeployDir for testing..." -ForegroundColor Cyan
if (-not (Test-Path $LocalDeployDir)) {
    try {
        New-Item -ItemType Directory -Path $LocalDeployDir -Force | Out-Null
    } catch {
        Write-Warning "Could not create local testing directory $LocalDeployDir. Error: $_"
    }
}

$FilesToDeploy = @(
    @{ Src = $DistExe; DstName = "FileBridgeAgent.exe" },
    @{ Src = Join-Path $AgentDir "FileBridgeAgentService.exe"; DstName = "FileBridgeAgentService.exe" },
    @{ Src = Join-Path $AgentDir "FileBridgeAgentService.xml"; DstName = "FileBridgeAgentService.xml" },
    @{ Src = Join-Path $AgentDir "config.yaml"; DstName = "config.yaml" },
    @{ Src = Join-Path $AgentDir "manage_service.ps1"; DstName = "manage_service.ps1" },
    @{ Src = Join-Path $AgentDir "README_SERVICE.md"; DstName = "README_SERVICE.md" }
)

$DeploySuccess = $true
foreach ($File in $FilesToDeploy) {
    if (Test-Path $File.Src) {
        $DestPath = Join-Path $LocalDeployDir $File.DstName
        try {
            Copy-Item -Path $File.Src -Destination $DestPath -Force -ErrorAction Stop
            Write-Host "   [DEPLOYED] $($File.DstName) -> $DestPath"
        } catch {
            Write-Warning "Could not overwrite local test file $($File.DstName) (likely locked by service): $_"
            $DeploySuccess = $false
        }
    } else {
        Write-Warning "Source file not found for deployment: $($File.Src)"
    }
}
if ($DeploySuccess) {
    Write-Success "Local package successfully deployed at $LocalDeployDir"
} else {
    Write-Warning "Local package deployment partially completed. Some active testing files are locked."
}

# Restart local service if it was running previously
if ($Service) {
    Write-Host "[INFO] Restarting local service..."
    Start-Service -Name "FileBridgeAgent" -ErrorAction SilentlyContinue
}

# 5. Package the complete, self-contained deployment ZIP
Write-Host "`n4. Packaging the self-contained deployment ZIP..." -ForegroundColor Cyan
if (Test-Path $DeployZip) {
    Remove-Item $DeployZip -Force
}

# Create a temporary packaging directory to build clean zip archive structure
$TempPackDir = Join-Path $AgentDir "FileBridgeAgent_Pack"
if (Test-Path $TempPackDir) {
    Remove-Item $TempPackDir -Recurse -Force
}
New-Item -ItemType Directory -Path $TempPackDir -Force | Out-Null

# Copy clean files to temp pack dir
foreach ($File in $FilesToDeploy) {
    if (Test-Path $File.Src) {
        Copy-Item -Path $File.Src -Destination (Join-Path $TempPackDir $File.DstName) -Force
    }
}
# Create an empty logs directory inside the deployment package
New-Item -ItemType Directory -Path (Join-Path $TempPackDir "logs") -Force | Out-Null

# Compress to self-contained ZIP archive
Compress-Archive -Path "$TempPackDir\*" -DestinationPath $DeployZip -Force
Write-Success "Packaging complete!"

# Cleanup temporary folder
Remove-Item $TempPackDir -Recurse -Force
Write-Host "[SUCCESS] Self-contained package is ready at: $DeployZip" -ForegroundColor Green

Write-Host "`n========================================================" -ForegroundColor Cyan
Write-Host "Pipeline completed successfully!" -ForegroundColor Green
Write-Host "1. Updated agent is active in $LocalDeployDir"
Write-Host "2. Release distribution is packaged in $DeployZip"
Write-Host "========================================================" -ForegroundColor Cyan
