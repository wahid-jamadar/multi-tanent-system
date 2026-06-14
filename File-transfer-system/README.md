# FileBridge - Server-to-Server File Communication & Synchronization

FileBridge is a Flask + MySQL + Bootstrap starter project for secure automated file transfer and synchronization across Windows, Linux, and Ubuntu servers.

## Features

- Login with RBAC-ready users
- Server management
- WinSCP-style file transfer screen
- Agent registration, heartbeat, polling, job result APIs
- Copy, move, sync, delete, mkdir job records
- WebSocket progress events
- MySQL schema and SQLAlchemy models
- System logs, audit logs, alerts, settings
- Email/Slack alert hooks
- Session warning after 25 minutes and auto logout after 30 minutes
- Dark/light theme toggle
- Windows `.bat` agent and Linux `.sh` agent templates

## Setup

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Create a MySQL database:

```sql
CREATE DATABASE filebridge CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'filebridge_user'@'172.100.31.40' IDENTIFIED BY 'filebridge_pass';
GRANT ALL PRIVILEGES ON filebridge.* TO 'filebridge_user'@'172.100.31.40';
FLUSH PRIVILEGES;
```

Initialize tables and seed the admin user:

```powershell
python app.py init-db
```

Run:

```powershell
python run.py
```

Open:

```text
https://172.100.31.40:5001
```

Default login:

```text
admin / Admin@12345
```

Change the default password immediately in production.

## Install an Agent on Another Windows Machine

Copy the `agents` folder to the remote Windows machine, then run PowerShell as that user:

```powershell
cd C:\path\to\agents
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\install-agent.ps1 -BackendUrl "https://YOUR_FILEBRIDGE_SERVER_IP:5001" -BootstrapToken "replace-bootstrap-token" -ServerName "BRANCH-PC-01" -BasePath "C:\" -StartNow
```

Each install writes its own `agent.env` with a unique `AGENT_UUID`. Keep `SERVER_NAME` unique per machine.

Open `File Manager` in the web app to browse the machine, create folders, rename items, and delete items through its online agent.

## Production Notes

- Run behind Nginx or HAProxy with HTTPS.
- Use a real `FLASK_SECRET_KEY`, `ENCRYPTION_KEY`, `JOB_SIGNING_SECRET`, and `AGENT_BOOTSTRAP_TOKEN`.
- Store secrets in a vault or environment manager.
- Use Gunicorn/eventlet on Linux or Waitress on Windows.
- Schedule MySQL backups and verify restore.
- Do not expose agents publicly unless they are behind VPN/private network.
