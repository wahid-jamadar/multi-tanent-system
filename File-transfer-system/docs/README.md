# Server-to-Server File Communication & Synchronization System

Production-ready architecture documentation for a Flask + MySQL + Bootstrap based server-to-server file transfer and synchronization platform.

## Documentation Map

1. [High-Level Architecture](01-high-level-architecture.md)
2. [Component Breakdown and Data Flow](02-components-and-data-flow.md)
3. [Database Schema and Queries](03-database-schema.md)
4. [Agent Workflow](04-agent-workflow.md)
5. [Security Implementation](05-security.md)
6. [Scheduler, Sync Algorithm, Failure Handling](06-scheduler-sync-failure.md)
7. [Logging, Monitoring, Scalability, UI/UX](07-operations-ui-scalability.md)

## Recommended Tech Stack

- Backend: Python Flask monolith, Flask-SocketIO, SQLAlchemy, PyMySQL, APScheduler, Celery/RQ optional for heavy jobs
- Frontend: HTML, CSS, JavaScript, Bootstrap 5, native WebSocket or Socket.IO client
- Database: MySQL 8.x
- Transport: HTTPS/TLS REST APIs, WebSockets, SSH/SFTP for Linux, WinRM/SMB for Windows
- Agents: `.sh` for Linux/Ubuntu, `.bat` or PowerShell-launched `.bat` for Windows
- Monitoring: Prometheus metrics endpoint, Grafana dashboards, structured JSON logs
- Alerts: SMTP email, Slack webhook

## Monolithic Backend Rule

The first production version can keep one Python backend file, for example `app.py`, but it should still be internally organized into clear sections:

- Configuration and logger setup
- Database models
- Authentication and RBAC decorators
- REST APIs
- WebSocket events
- Scheduler
- Agent job dispatcher
- File operation services
- Sync engine
- Alert manager
- Prometheus metrics

