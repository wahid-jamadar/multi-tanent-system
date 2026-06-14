# 2. Component Breakdown

## Flask Backend

Responsibilities:

- User login, RBAC, session timeout.
- Server registration and inventory.
- Agent registration, heartbeat, job polling, result ingestion.
- File browser APIs.
- Transfer and sync job creation.
- Job signing and verification.
- Scheduler execution.
- Conflict detection.
- Audit, system, and admin logs.
- Alert routing to email or Slack.

Production detail:

- Keep all logs structured with `request_id`, `user_id`, `agent_id`, `job_id`, `source_path`, `destination_path`, and `status`.
- Use HTTPS only. Reject plain HTTP in production.
- Store sensitive credentials encrypted, never as plain database text.

## Agents

Agent types:

- Linux/Ubuntu: `agent.sh` using `curl`, `ssh`, `scp` or `sftp`, `sha256sum`, `stat`, `find`, `rsync` when available.
- Windows: `agent.bat` launching PowerShell for robust WinRM/SMB/file hashing operations.

Agent responsibilities:

- Register itself with backend.
- Send heartbeat every 10 seconds.
- Poll for jobs or maintain WebSocket connection.
- Verify job signature.
- Execute file operation.
- Stream progress updates.
- Return result and logs.

## Communication Protocols

- Dashboard to backend: HTTPS REST + WebSockets.
- Agent to backend: HTTPS REST polling by default; WebSockets optional for lower latency.
- Linux file operations: SSH/SFTP/rsync.
- Windows file operations: WinRM for remote command execution, SMB for file share operations.
- Mixed OS transfer: agent-mediated copy using SFTP/SMB bridge or backend staging storage if direct protocol access is unavailable.

# 3. Data Flow Explanation

## One-Time Copy

```text
Admin creates copy job
  -> Backend validates RBAC and paths
  -> Backend inserts transfer_jobs row
  -> Backend creates signed job payload
  -> Source or destination agent polls job
  -> Agent verifies signature
  -> Agent copies file while calculating checksum
  -> Agent reports progress over HTTPS/WebSocket
  -> Backend records operation logs and final status
  -> Dashboard receives live progress
```

Copy retains the source file.

## Cut and Paste

```text
Admin creates move job
  -> Agent copies file to destination temp path
  -> Agent verifies size and checksum
  -> Agent atomically renames temp file to final path
  -> Agent deletes source only after verification succeeds
  -> Backend logs both copy and delete stages
```

The source must not be deleted until the destination checksum matches.

## Bi-Directional Sync

```text
Schedule or file event triggers sync
  -> Sync engine asks agents for file manifests
  -> Backend compares relative path, size, mtime, checksum
  -> Backend creates missing/update/delete jobs
  -> Agents execute jobs
  -> Conflicts are resolved by policy
  -> Sync run summary is saved
```

## Real-Time Sync

Agents can use:

- Linux: `inotifywait` if installed, fallback to periodic scan.
- Windows: PowerShell `FileSystemWatcher`, fallback to scheduled scan.

Real-time events should be debounced for 1-3 seconds to avoid syncing incomplete writes.

