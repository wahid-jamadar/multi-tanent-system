# BatchHost-Pro — Privacy Policy

**Document Version:** 1.0  
**Effective Date:** May 2026  
**Last Updated:** May 2026  
**Audience:** End Users, Administrators, Compliance Officers  

---

## 1. Introduction

This Privacy Policy describes how **BatchHost-Pro** ("the System", "the Software", "we", "us") collects, uses, stores, protects, and manages personal and operational data when you use the BatchHost-Pro centralized batch script monitoring platform.

BatchHost-Pro is a self-hosted, on-premises software solution. **All data is stored locally on organization's infrastructure** — no data is transmitted to external cloud services or third-party servers unless explicitly configured by the system administrator (e.g., SMTP email notifications).

By accessing or using BatchHost-Pro, you acknowledge that you have read, understood, and agree to the practices described in this Privacy Policy.

---

## 2. Data Controller

The **data controller** is the organization or individual that deploys and operates the BatchHost-Pro instance. The deploying organization is responsible for:

- Determining the purposes and means of processing personal data
- Ensuring compliance with applicable data protection laws and regulations
- Informing end users about data processing activities
- Responding to data subject requests (access, correction, deletion)
- Implementing appropriate technical and organizational security measures

---

## 3. Data We Collect

### 3.1 User Account Data

When a user account is created by an administrator, the following personal data is collected and stored in `data/users.json`:

| Data Field | Purpose |
|---|---|
| **Username** | Account identification and login |
| **Email Address** | Account identification, login credential, alert notifications |
| **Password** (hashed) | Authentication — stored as SHA-256 one-way hash; original password is never stored or recoverable |
| **Role** | Access control (Super Admin, Organization Admin, Organization Viewer) |
| **Organization Assignment** | Multi-tenant data isolation and access scoping |
| **Account Status** | Active/Inactive account state management |
| **Login Timestamps** | Current and previous login times for audit purposes |
| **Total Login Count** | Usage analytics and security monitoring |
| **Account Creation Date** | Record-keeping and audit trail |

### 3.2 Session and Authentication Data

- **Session Identifiers** — Cryptographically signed session cookies for authenticated state
- **Presence Identifiers** — Unique per-browser-tab identifiers for real-time web presence tracking
- **Login Timestamps** — Used to enforce session timeout policies (30-minute timeout)
- **IP Address** — Captured during login and administrative actions for audit logging

> **Note:** Session data is stored in server memory and signed cookies. Sessions are automatically invalidated after 30 minutes of inactivity or on browser tab closure.

### 3.3 Agent Machine Data

When a remote agent registers with the system, the following is collected and stored in `data/agents.json`:

- Agent ID, Hostname, Operating System Type
- Device Fingerprint Key (hardware-level identifier)
- Authentication Token
- CPU and Memory Usage (real-time metrics)
- Last Heartbeat Timestamp, Organization Assignment

### 3.4 Script Execution Data

Stored in `data/scripts.json`, `data/script_executions.json`, and `data/execution_events.json`:

- Script file paths and names
- Execution status lifecycle (pending → running → completed/failed/terminated/timeout)
- Execution timestamps, exit codes, process IDs (PIDs)
- Runtime duration, CPU and memory readings per execution
- Sequence-numbered lifecycle events for every execution

### 3.5 Alert and Audit Data

- **Alerts** (`data/alerts.json`) — Type, severity, agent/org association, message, email notification status, timestamps
- **Admin Audit Logs** (`data/admin_logs.json`) — Admin username, action type, affected module/record, previous/new values, IP address, status, timestamps

### 3.6 Server and Agent Logs

- **Server logs** (`logs/server.log`) — HTTP requests (method, path, IP), response codes, errors, script transitions, WebSocket events
- **Agent logs** (`logs/<agent_id>_<date>.log`) — Per-agent, per-day heartbeat and status logs

> **Important:** Password fields are explicitly stripped from all request logging.

---

## 4. How We User's Your Data

Data collected is used exclusively for:

- **Authentication & Authorization** — Verifying identity and enforcing role-based access control
- **Session Management** — Maintaining sessions with timeout enforcement and auto-logout
- **Multi-Tenant Isolation** — Ensuring users only access data within their organization
- **Monitoring & Alerting** — Tracking agent health, script execution, and generating alerts
- **Email Notifications** — Sending alert emails via SMTP (only when configured by admin)
- **Reporting & Auditing** — Generating PDF/XML exports and maintaining admin audit trails
- **System Integrity** — Data self-repair, duplicate detection, and real-time WebSocket broadcasting

---

## 5. Data Storage and Retention

### 5.1 Storage Model

BatchHost-Pro uses a **file-based JSON storage model** on the server's local file system. No external database is used. All data remains on infrastructure controlled by the deploying organization.

### 5.2 Retention Periods

| Data Type | Retention Policy |
|---|---|
| User Accounts, Agents, Scripts, Alerts | Until explicitly deleted by an administrator |
| Execution Events | Capped at 10,000 entries (oldest pruned automatically) |
| Server Logs | Continuous growth; manual rotation recommended |
| Agent Logs | One file per agent per day; no automatic purging |
| Admin Audit Logs | Until cleared by an administrator |
| Session Data | In-memory only; purged on expiration or server restart |

---

## 6. Data Security

### 6.1 Data at Rest
- Passwords are SHA-256 hashed — never stored in plain text
- Atomic write operations prevent data corruption during saves
- File system access should be restricted via OS-level permissions

### 6.2 Data in Transit
- All browser-to-server communication uses **HTTPS** (SSL/TLS)
- Agent-to-server communication uses **HTTPS** with token-based authentication (`X-Agent-Token` headers)
- WebSocket connections run over **WSS** (encrypted WebSocket)

### 6.3 Authentication & Access Control
- Flask signed cookie sessions with cryptographic secret key
- 30-minute session timeout with auto-logout enforcement
- Role-based access control (Super Admin, Org Admin, Org Viewer)
- Agent tokens validated on every API request (HTTP 401/403 on failure)

### 6.4 Concurrency & Integrity
- Thread-safe operations via reentrant locks (`threading.RLock`)
- Atomic file writes (temp file → `os.replace`) prevent partial writes
- Startup self-repair detects and corrects data inconsistencies

---

## 7. Data Sharing and Third Parties

BatchHost-Pro **does not share or transmit** data to any third-party services, analytics platforms, or advertising networks.

External data transmission occurs only when:
1. **SMTP Email Notifications** — Alert emails sent via the admin-configured SMTP server
2. **Backup Exports** — Downloadable backup files (passwords excluded)

> **No telemetry, analytics, crash reports, or any data is sent to BatchHost-Pro developers or external services.**

---

## 8. Cookies and Browser Storage

| Cookie | Purpose | Duration |
|---|---|---|
| **Session Cookie** | Maintains authenticated session | 30 minutes or until logout |

- No third-party cookies, tracking pixels, advertising tags, or analytics scripts are used
- Browser `localStorage` may be used for UI preferences only

---

## 9. User Rights

Depending on your jurisdiction (GDPR, CCPA, etc.), you may exercise:

- **Right of Access** — Request a copy of your personal data
- **Right to Rectification** — Request correction of inaccurate data
- **Right to Erasure** — Request deletion of your account and data
- **Right to Restriction** — Request limitation of data processing
- **Right to Data Portability** — Receive data in JSON/XML format via backup export
- **Right to Object** — Object to processing of your data

> All data subject requests should be directed to the **organization operating the BatchHost-Pro instance**.

---

## 10. International Data Transfers

As a self-hosted solution, no inherent cross-border transfers occur. If the deploying organization operates across jurisdictions, they are responsible for appropriate data transfer safeguards.

---

## 11. Data Breach Notification

The deploying organization is responsible for breach detection and response. Server logs and admin audit logs provide forensic data. Organizations must notify affected parties per applicable law.

---

## 14. Contact Information

- **Primary Contact:** Vaibhav Deshpande
- **Organization Data Controller:** LIST Software Pvt. Ltd., Sangli.
- **Data Protection Officer:** Vaibhav Deshpannde
- **Email:** business@listspl.co.in
---

**End of Privacy Policy**

*Doc Created by **Wahid Jamadar** — BatchHost-Pro Team*
