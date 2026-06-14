$ErrorActionPreference = "Stop"

$AgentDir = "C:\BatchHost-Pro\agents"
$WinSWUrl = "https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe"
$WinSWExe = "$AgentDir\batchhost-agent-service.exe"
$WinSWXml = "$AgentDir\batchhost-agent-service.xml"

Write-Host "Preparing to install BatchHost-Pro Agent as a Windows Service..." -ForegroundColor Cyan

# Find Python executable
$PythonExe = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
if (-not $PythonExe) {
    $PythonExe = (Get-Command py.exe -ErrorAction SilentlyContinue).Source
}
if (-not $PythonExe) {
    Write-Host "Python not found in PATH. Please ensure Python is installed and added to PATH." -ForegroundColor Red
    exit 1
}

Write-Host "Found Python at: $PythonExe"

$VenvDir = "$AgentDir\venv"
$VenvPython = "$VenvDir\Scripts\python.exe"

# Create a virtual environment specifically for the service
if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating Python virtual environment for the service..."
    & $PythonExe -m venv $VenvDir
}

Write-Host "Installing dependencies in virtual environment..."
& $VenvPython -m pip install --upgrade pip > $null
& $VenvPython -m pip install psutil requests > $null

# Download WinSW if not present
if (-not (Test-Path $WinSWExe)) {
    Write-Host "Downloading WinSW service wrapper..."
    Invoke-WebRequest -Uri $WinSWUrl -OutFile $WinSWExe
}

# Create XML config
$XmlContent = @"
<service>
  <id>BatchHost-Pro_Agent</id>
  <name>BatchHost-Pro Agent</name>
  <description>Event-driven agent runtime for BatchHost-Pro. Runs continuously in the background to execute scripts without UI.</description>
  
  <executable>$VenvPython</executable>
  <arguments>"$AgentDir\agent_runtime.py" daemon</arguments>
  <workingdirectory>$AgentDir</workingdirectory>
  
  <!-- Log configuration -->
  <logpath>$AgentDir\logs</logpath>
  <log mode="roll-by-size">
    <sizeThreshold>10240</sizeThreshold> <!-- 10 MB per file -->
    <keepFiles>8</keepFiles>
  </log>

  <!-- Restart policy on crash/failure -->
  <onfailure action="restart" delay="10 sec"/>
  <onfailure action="restart" delay="30 sec"/>
  <resetfailure>1 hour</resetfailure>
  
  <startmode>Automatic</startmode>
</service>
"@

Set-Content -Path $WinSWXml -Value $XmlContent -Encoding UTF8
Write-Host "Service configuration created at $WinSWXml"

# Install and Start the service
Write-Host "Installing Windows Service..."
& $WinSWExe install

if ($LASTEXITCODE -eq 0) {
    Write-Host "Starting Windows Service..."
    & $WinSWExe start
    Write-Host "Service installed and started successfully!" -ForegroundColor Green
    Write-Host "The agent will now start automatically on system boot."
} else {
    Write-Host "Failed to install service. Make sure you are running this as Administrator." -ForegroundColor Red
}