# 1. High-Level Architecture Diagram

```text
                             Admin Browser
                       HTML + CSS + JS + Bootstrap
                           HTTPS + WebSockets
                                   |
                                   v
                    +-------------------------------+
                    | Flask Monolithic Backend       |
                    | - REST API                     |
                    | - WebSocket Gateway            |
                    | - Scheduler                    |
                    | - Job Signer                   |
                    | - Sync Engine                  |
                    | - Logging / Alert Manager      |
                    +---------------+---------------+
                                    |
                   +----------------+----------------+
                   |                                 |
                   v                                 v
          +----------------+                 +----------------+
          | MySQL Database |                 | Object/Staging |
          | Source of      |                 | Storage        |
          | Truth          |                 | Optional       |
          +----------------+                 +----------------+
                   |
                   v
        +----------------------+         +----------------------+
        | Linux/Ubuntu Agent   |         | Windows Agent        |
        | agent.sh             |         | agent.bat            |
        | HTTPS polling / WS   |         | HTTPS polling / WS   |
        | SSH/SFTP operations  |         | WinRM/SMB operations |
        +----------+-----------+         +----------+-----------+
                   |                                |
                   v                                v
        Linux/Ubuntu File Servers        Windows File Servers
```

## Architecture Style

The platform uses a control-plane/data-plane split.

- Control plane: Flask backend, database, dashboard, scheduler, job signing, audit logs.
- Data plane: agents execute file operations close to the file systems using SSH/SFTP, WinRM, SMB, or local file operations.

This avoids routing every large file through the Flask server. For very large transfers, the backend should only create signed jobs and collect progress, while agents stream files directly server-to-server where possible.

## Deployment Topology

```text
Internet / VPN
    |
Load Balancer / Reverse Proxy
Nginx or HAProxy with TLS termination
    |
Flask App Workers
Gunicorn or Waitress depending on OS
    |
MySQL Primary + Replica
    |
Backup Storage
```

Recommended production services:

- `nginx`: TLS termination, request size limits, WebSocket proxy.
- `flask app`: monolithic backend, multiple workers.
- `mysql`: persistent relational state.
- `redis`: optional queue/session/rate-limit store.
- `prometheus`: scrape metrics.
- `grafana`: dashboards.

