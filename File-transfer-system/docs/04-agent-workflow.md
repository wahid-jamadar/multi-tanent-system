# 5. Agent Workflow

## Registration

```text
agent starts
  -> reads config: backend URL, server name, OS type, token
  -> POST /api/agents/register
  -> backend validates bootstrap token
  -> backend stores agent UUID and capability list
  -> backend returns agent token and public signing key
```

Registration payload:

```json
{
  "agent_uuid": "generated-on-install",
  "hostname": "fileserver-01",
  "os_type": "windows",
  "version": "1.0.0",
  "capabilities": ["smb", "winrm", "checksum", "filesystem_watcher"]
}
```

## Heartbeat Every 10 Seconds

```text
POST /api/agents/heartbeat
Authorization: Bearer agent-token

{
  "agent_uuid": "...",
  "free_disk_bytes": 123456789,
  "running_jobs": 2,
  "cpu_percent": 18.5,
  "memory_percent": 41.2
}
```

Backend marks agent offline if no heartbeat is received for 30 seconds.

## Job Polling

```text
agent loop every 3-5 seconds:
  POST /api/agents/jobs/poll
  receive signed job payload
  verify signature
  execute job
  POST progress every 1-5 seconds
  POST final result
```

Polling is simpler and more firewall-friendly. WebSockets can be added for lower latency, but agents should still support polling as fallback.

## Linux Agent Operations

- Copy: `rsync -a --partial --checksum` or `scp` fallback.
- Move: copy to temp path, verify checksum, rename, delete source.
- Hash: `sha256sum`.
- Metadata: `stat`.
- Change detection: `inotifywait` or periodic `find`.

## Windows Agent Operations

Use `.bat` as the entrypoint, but call PowerShell for reliable operations:

- Copy: `Copy-Item` or SMB copy to UNC path.
- Move: `Copy-Item`, `Get-FileHash`, `Remove-Item` after verification.
- Remote command: WinRM `Invoke-Command`.
- Hash: `Get-FileHash -Algorithm SHA256`.
- Change detection: `.NET FileSystemWatcher`.

## Execution Result

```json
{
  "job_uuid": "6df6d7d2-2a5a-4dd3-a63e-3313a53731b7",
  "status": "success",
  "bytes_transferred": 104857600,
  "checksum_sha256": "abc...",
  "started_at": "2026-05-04T10:30:00Z",
  "completed_at": "2026-05-04T10:31:12Z",
  "logs": [
    {"level": "INFO", "message": "Copied to temp path"},
    {"level": "INFO", "message": "Checksum verified"}
  ]
}
```

