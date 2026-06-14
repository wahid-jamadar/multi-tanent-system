# FileBridge Agent Windows Service — Deployment & Operations Guide

This guide describes how to deploy, install, run, and manage the **FileBridge Agent** as a high-availability background Windows Service.

---

## 1. Directory Architecture

The deployment package is fully self-contained and path-independent. You can copy the entire folder to any path (e.g. `C:\FileBridgeAgent`, `D:\Services\FileBridgeAgent`, etc.) on a target machine without modifying any configuration.

```
FileBridgeAgent/
├── FileBridgeAgent.exe         # Compiled Python Agent binary
├── FileBridgeAgentService.exe  # WinSW Windows Service Wrapper binary
├── FileBridgeAgentService.xml  # WinSW configuration (dynamic paths)
├── config.yaml                 # Agent registration, token, and backend URL config
├── manage_service.ps1          # Robust PowerShell installer and service manager
└── logs/                       # (Automatically created) Service & agent run logs
    ├── agent.log               # Dynamic Python agent logs (midnight rotation)
    ├── FileBridgeAgentService.wrapper.log  # WinSW wrapper events
    ├── FileBridgeAgentService.out.log      # Stdout capture
    └── FileBridgeAgentService.err.log      # Stderr capture
```

---

## 2. Dynamic Configurations (`FileBridgeAgentService.xml`)

The service uses **WinSW** (Windows Service Wrapper) to handle the background hosting.
To achieve absolute path-independence, all file targets are resolved dynamically relative to the installation directory using the `%BASE%` environment variable:

```xml
<service>
  <id>FileBridgeAgent</id>
  <name>FileBridge Agent</name>
  <description>FileBridge distributed file synchronization and monitoring agent.</description>
  
  <executable>%BASE%\FileBridgeAgent.exe</executable>
  <arguments></arguments>
  <workingdirectory>%BASE%</workingdirectory>
  
  <env name="FILEBRIDGE_SERVICE" value="1"/>

  <logpath>%BASE%\logs</logpath>
  <log mode="roll-by-size">
    <sizeThreshold>10240</sizeThreshold> <!-- 10 MB limit per wrapper log -->
    <keepFiles>8</keepFiles>
  </log>

  <!-- Service Recovery Policies -->
  <onfailure action="restart" delay="10 sec"/>
  <onfailure action="restart" delay="30 sec"/>
  <onfailure action="restart" delay="60 sec"/>
  <resetfailure>1 hour</resetfailure>
  
  <startmode>Automatic</startmode>
</service>
```

### Key Operations Features:
*   `FILEBRIDGE_SERVICE`: Set to `1`. Tells the agent executable it is running as a service, disabling console outputs and routing logging exclusively to the timed rolling file log.
*   **Automatic Failure Recovery**: If the agent process crashes unexpectedly, Windows Service Controller will restart the process with progressive delays (10 seconds, 30 seconds, then 60 seconds) to prevent CPU thrashing in case of network outages.

---

## 3. Using the Service Manager (`manage_service.ps1`)

The PowerShell script `manage_service.ps1` provides an easy, interactive, or CLI-driven interface to manage the service lifecycle.

> [!IMPORTANT]
> Running `install`, `uninstall`, `start`, `stop`, or `restart` commands requires **Administrative Privileges**. Relaunch PowerShell as Administrator before executing these commands.

### Commands

#### A. Install and Start the Service
```powershell
.\manage_service.ps1 install
```
*Action*: Performs validation checks (checks if all files exist, extracts backend URL from `config.yaml`, verifies connectivity), stops/uninstalls any previous instance, registers the service, and starts it.

#### B. Check Service Status
```powershell
.\manage_service.ps1 status
```
*Action*: Displays detailed information about installation directories, status of binaries/wrappers, service running state (Running/Stopped/Not Installed), the backend URL, and the last 10 lines of the agent execution log (`logs/agent.log`).

#### C. Stop the Service
```powershell
.\manage_service.ps1 stop
```
*Action*: Stops the service cleanly. The Python agent catches the interruption signal (Ctrl+C) sent by WinSW and triggers a graceful shutdown (stopping and joining the folder observers).

#### D. Start the Service
```powershell
.\manage_service.ps1 start
```

#### E. Restart the Service
```powershell
.\manage_service.ps1 restart
```

#### F. Uninstall the Service
```powershell
.\manage_service.ps1 uninstall
```
*Action*: Stops the running service and removes it cleanly from the Windows Service Controller database. All binaries are left intact, allowing the folder to be moved or deleted.

---

## 4. Graceful Shutdown & Recovery Details

When a service stop command is issued:
1. WinSW sends a `Ctrl+C` interrupt signal to `FileBridgeAgent.exe`.
2. The agent catches `KeyboardInterrupt` inside the main process loop.
3. The custom `try...finally` block inside the agent's main loop executes, stopping filesystem watcher threads (`observer.stop()`) and joining them (`observer.join()`).
4. Any active job telemetry thread is allowed to terminate cleanly before the process exits.
5. WinSW records the graceful exit code (`0`) and logs service termination events.
