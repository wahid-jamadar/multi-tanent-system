# FileBridge Production Agent Platform

## Architecture

Dashboard UI <-> Flask API + Socket.IO <-> scheduler/sync engine <-> distributed Python agents.

The existing Flask, SQLAlchemy, Socket.IO, Bootstrap, and Python agent stack is preserved. The upgrade adds production-grade agent identity, heartbeat telemetry, folder monitoring, and persistent operation queues around the current transfer job pipeline.

## Agent Registration

1. Agent starts from its installed directory on any drive.
2. It creates a UUID agent id and SHA256 machine fingerprint.
3. It detects hostname, OS details, IP address, drives, install directory, and configured sync folders.
4. It registers through `/api/agents/register` with the bootstrap token.
5. The backend stores the agent, server mapping, token hash, capabilities, version, folders, and status.
6. The backend returns a JWT-wrapped agent token.
7. The agent saves config locally, starts heartbeat reporting, starts watchdog monitoring, and polls for jobs.

## Database Additions

- `agents`: hostname, IP, OS info, machine fingerprint, uptime, last sync time, live metrics.
- `agent_folders`: user/config-managed monitored folders per agent.
- `transfer_queue`: durable backend queue for observed operations.
- `heartbeat_logs`: searchable performance history.
- `file_operations`: filesystem create/modify/delete/rename audit stream.
- `sync_rules`: optional `target_agent_ids` for group synchronization.

## Agent Runtime

- Dynamic path resolution via `pathlib`, `abspath`, configured folders, and drive detection.
- Watchdog detects created, modified, deleted, renamed files and folders.
- Local JSONL queue preserves events while the backend is offline.
- `psutil` heartbeat reports CPU, RAM, disk, network counters, queue depth, transfers, uptime, and drives every 30 seconds.
- Chunked transfer, resumable range download, retry logic, and SHA256 validation remain in the transfer engine.

## Windows Service

Run as Administrator:

```bat
agent\install_service.bat
```

Other commands:

```bat
agent\FileBridgeAgent.exe restart-service
agent\uninstall_service.bat
```

The service is configured for auto-start and runs without a terminal window. For packaged installs, build with PyInstaller, then compile `agent\FileBridgeAgentInstaller.iss` using Inno Setup.

## Security

- Agent bootstrap token is used only for first registration.
- Backend stores only SHA256 token hashes.
- Agent API accepts JWT-wrapped tokens and legacy raw bearer tokens for compatibility.
- Path sandboxing remains enforced by configured allowed roots.
- Relay uploads/downloads validate job ownership and SHA256 checksums.

## Operations

- Dashboard machine cards show online/offline status, CPU, RAM, disk, queue depth, active transfers, and recent watchdog activity.
- Sync rules continue to support manual, interval, and event-driven workflows.
- Offline agents retain local event queues and retry automatically when online.
