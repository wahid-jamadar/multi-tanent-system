# ⚡ BatchHost-Pro

![Python](https://img.shields.io/badge/Python-3.13+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-2.3+-000000?style=for-the-badge&logo=flask&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-8.0+-4479A1?style=for-the-badge&logo=mysql&logoColor=white)
![Status](https://img.shields.io/badge/Status-Production--Ready-blue?style=for-the-badge)

**BatchHost-Pro** is a high-performance, centralized orchestration and monitoring system designed for distributed `.bat` (Windows) and `.sh` (Linux) scripts. It provides real-time execution tracking, process tree management, system health monitoring, and automated alerting across an entire multi-tenant infrastructure.

---

## ✨ Key Features & System Enhancements

- 🖥️ **Centralized Orchestration Dashboard**: A unified web interface powered by WebSocket (`Socket.IO` in threading mode) for real-time visibility into agent statuses, system resource utilization, and live script outputs.
- 🏢 **Multi-Tenancy (Organizations)**: Isolated data boundaries by organization. Users only see resources belonging to their assigned organization.
- 🔗 **SSO Integration**: Full single sign-on integration. Login redirects to the Central Auth Portal (`https://172.100.31.40:8000/login`). The Flask server verifies SSO tokens via `/auth/sso` contacting the central verification portal at `/api/auth/verify-token` and synchronizes roles dynamically.
- 🗺️ **Premium Navigation Widget**: A floating quick-nav widget embedded in the layout (`base.html`) for switching between **BatchHost-Pro System** (Port 5000), **FileBridge System** (Port 5001), and the **Central Selection Portal** (Port 8000).
- 🛞 **V2 Execution Orchestration Engine**: Python-based agent (`agent_runtime.py`) featuring process tree (PID) tracking, crash recovery, watchdog timeouts, and an advanced event journal.
  - **Remote Stop (`STOP_SCRIPT`)**: Remotely terminate a running script's entire child process tree (`ProcessTreeManager.terminate_tree` on the root PID) and transition the state to `FORCE_KILLED`.
  - **Heartbeat Execution Recovery (Resurrection)**: If a script execution has transitioned to `TIMEOUT` or `UNKNOWN` due to network delays, a fresh heartbeat from the agent will automatically resurrect the execution back to `RUNNING`.
  - **Resource Monitoring**: Tracks and reports actual agent machine CPU and Virtual Memory usage via the `psutil` library.
- 🔐 **Security & Auditing**:
  - Super Admin users are strictly pinned to the **Global Organization** and cannot be moved.
  - Detailed **Admin Audit Logs** tracking user creations, deletions, and script executions.
  - Zero-dependency CSRF protection, rate limiting, and brute-force protection.
  - Session presence tracking with auto-logout warnings at 25 minutes and hard logout at 30 minutes.
  - Dynamic SSO splash overlay when accessing the dashboard with the `splash=1` query parameter.
- 📊 **Advanced Reporting & Logs**: Generate and export execution logs in **PDF** or **XML** formats with custom date ranges.
- 💾 **Centralized MySQL Architecture**: Users and organizations are stored in a centralized MySQL database (InnoDB engine, `utf8mb4_unicode_ci` collation) with automatic JSON file fallback for offline standalone configurations.

---

## 📁 Project Structure

```text
BatchHost-Pro/
├── server.py               # Core Flask server (requires Python 3.13 with Waitress & Eventlet)
├── requirements.txt        # Python dependencies
├── backend/                # Server-side business logic
│   ├── rate_limiter.py     # Endpoint rate limits & brute force protection
│   └── tracking.py         # Script state validator & execution manager
├── data/                   # Persistent backup/fallback JSON storage
│   ├── agents.json         # Registered agent metadata
│   ├── scripts.json        # Script registry & schedules
│   ├── script_executions.json # Detailed execution records
│   ├── execution_events.json  # Execution event journal
│   ├── alerts.json         # System & script alerts
│   ├── admin_logs.json     # Audit trail for admin actions
│   └── settings.json       # SMTP, CORS, and registration secrets
├── templates/              # Modern HTML5 templates (Dashboard UI)
├── agents/                 # Deployment packages for target machines
│   ├── agent_runtime.py    # V2 Python Agent (Execution Engine)
│   ├── batchhost-pro_agent.bat  # Agent launcher (automatically sets up venv)
│   ├── batchhost-pro_agent.sh   # Linux Agent wrapper
│   └── batchhost-agent-service.xml # Windows Service wrapper configuration
├── db/                     # SQL schemas and migrations
│   └── script.sql          # MySQL database schema (InnoDB, agent_logs table)
├── logs/                   # Real-time execution and server logs
├── backup/                 # System and organization backup archives
├── images/                 # UI assets
└── ssl-details.txt         # SSL certificate generation instructions
```

---

## 🚀 Installation & Setup

### 1. Prerequisites
- **Python 3.13 or higher** (A launch wrapper in `server.py` enforces this version and will auto-relaunch using `py -3.13` if available).
- **MySQL Server** (for centralized Multi-Tenant user and organization storage).
- **OpenSSL** (for generating HTTPS certificates).

### 2. Database Configuration
BatchHost-Pro connects to a MySQL database named `central_multitenant` running on port `3306`.
1. Create a MySQL database named `central_multitenant` using the schema in [script.sql](file:///c:/Amulti-tanent-system/BatchHost-Pro/db/script.sql):
   ```bash
   mysql -u root -p -h localhost < db/script.sql
   ```
2. Verify credentials in `server.py` match your MySQL setup:
   - **Host**: `localhost`
   - **Port**: `3306`
   - **User**: `root`
   - **Password**: `wahid5104` (update this in the `load_json`/`save_json` MySQL connection blocks in `server.py` if needed).

### 3. Clone & Install
```bash
git clone https://github.com/your-repo/BatchHost-Pro.git
cd BatchHost-Pro
pip install -r requirements.txt
```

### 4. SSL Configuration
Secure communications are required for Socket.IO and HTTPS. Place your `cert.pem` and `key.pem` in the root directory:
```bash
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes
```

### 5. Start the Server
Run the Flask server:
```bash
py -3.13 server.py
```
The dashboard will be available at **`https://172.100.31.40:5000`**.

---

## 🔌 Agent Deployment (V2 Runtime)

The V2 Agent runtime handles process execution, tree termination, and system stats reporting.

### 1. Requirements Setup
1. Copy the `agents/` folder to the target machine.
2. It is highly recommended to deploy the agent within a virtual environment. The launcher `batchhost-pro_agent.bat` automatically looks for `venv\Scripts\python.exe` inside the agents folder.
3. To configure the virtual environment:
   ```bash
   cd agents
   python -m venv venv
   venv\Scripts\pip install psutil requests websocket-client
   ```

### 2. Environment Variables
Set the following environment variables on the agent machine:
- `BATCHHOST_SERVER_URL`: The HTTPS URL of the BatchHost-Pro server (default: `https://172.100.31.40:5000`).
- `BATCHHOST_REGISTRATION_SECRET`: Secure registration secret (found in the server's `data/settings.json`).

### 3. Run the Agent

**Daemon Mode (Listens for server commands):**
Run the batch file to execute the agent:
```bash
batchhost-pro_agent.bat
```
*(The batch file copies python.exe to a custom-named executable `batchHost-Pro_Agent.exe` inside the venv directory to facilitate process monitoring in Task Manager).*

**Run a Specific Script Manually:**
```bash
venv\Scripts\python agent_runtime.py run C:\BatchScripts\job.bat
```

### 4. Windows Service Installation
The agent can run as a background Windows Service using the provided config:
1. Open a PowerShell window as Administrator in the `agents/` folder.
2. Use the wrapper `batchhost-agent-service.exe` pointing to `batchhost-pro_agent.bat` (configured inside `batchhost-agent-service.xml`).
3. Install and start:
   ```powershell
   .\batchhost-agent-service.exe install
   .\batchhost-agent-service.exe start
   ```

---

## 🏗️ Architecture & Execution Flow

1. **Registration & Token**: Agents authenticate with the server via `BATCHHOST_REGISTRATION_SECRET` and receive a dynamic, secure token stored locally.
2. **Heartbeats**: Every 5 seconds, agents push hostname, CPU usage, memory utilization, and active running script paths to the `/api/agent/heartbeat` endpoint.
3. **Execution Request**: When a user triggers "Run Now" from the dashboard UI:
   - The server pushes a `RUN_SCRIPT` command containing script ID, path, and execution ID into the agent's pending command queue.
   - On the next heartbeat poll, the agent retrieves the command, spawns the script, and records the child PIDs.
4. **Execution Stop**: When a user triggers "Stop":
   - The server pushes a `STOP_SCRIPT` command to the queue.
   - The agent receives the command, invokes the `ProcessTreeManager` to recursively kill all child processes under the root PID, and reports the state as `FORCE_KILLED`.
5. **State Transitions**: Scripts transition through states:
   `PENDING` ➔ `QUEUED` ➔ `STARTING` ➔ `RUNNING` ➔ `COMPLETED` / `FAILED` / `TIMEOUT` / `FORCE_KILLED` / `CRASHED` / `UNKNOWN`.
6. **Execution Resurrection**: If a script is marked `TIMEOUT` or `UNKNOWN` (e.g., due to temporary agent offline status), receiving a live script heartbeat on the server resurrects the record back to `RUNNING`.

---

## 🛠️ Security & Troubleshooting

- **Super Admin Pinning**: Super admins are locked to the Global Organization for security compliance. They cannot be reassigned to other organizational IDs.
- **CSRF Blocked**: Mutating API calls are strictly checked against `Origin` and `Referer` headers. Ensure headers match the Flask host.
- **SSL Verification Warnings**: SSL warnings are disabled locally for requests between BatchHost-Pro and the Central Auth Portal to prevent handshake verification bottlenecks.
- **Offline Agents**: If an agent stops heartbeating for >30 seconds, it is marked as `OFFLINE`. Confirm host networking to `https://172.100.31.40:5000`.

---

## 📄 License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---
*Project maintained and updated for multi-tenant enterprise orchestration.*
