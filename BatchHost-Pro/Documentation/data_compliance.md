# BatchHost-Pro — Data Compliance Document

**Document Version:** 1.0  
**Last Updated:** May 2026  
**Audience:** Compliance Officers, Data Protection Officers, Auditors, Administrators  

---

## 1. Purpose and Scope

This Data Compliance Document provides a comprehensive overview of how **BatchHost-Pro** addresses data protection and regulatory compliance requirements. It is designed to assist deploying organizations in:

- Understanding the data processing activities of the system
- Assessing compliance with applicable data protection regulations
- Conducting Data Protection Impact Assessments (DPIAs)
- Responding to regulatory inquiries and audits
- Implementing appropriate organizational and technical measures

### 1.1 Regulatory Frameworks Addressed

This document maps BatchHost-Pro's data practices against the following regulatory frameworks:

| Framework | Jurisdiction | Key Requirements |
|---|---|---|
| **GDPR** | European Union / EEA | Lawful processing, data subject rights, data minimization, security, breach notification |
| **CCPA / CPRA** | California, USA | Consumer rights, data disclosure, opt-out, data deletion |
| **HIPAA** | USA (Healthcare) | PHI protection, access controls, audit trails |
| **SOX** | USA (Public Companies) | Financial data integrity, audit trails, access controls |
| **ISO 27001** | International | Information security management, risk assessment, controls |
| **NIST CSF** | USA | Cybersecurity framework — Identify, Protect, Detect, Respond, Recover |

> **Note:** BatchHost-Pro is an infrastructure monitoring tool. Compliance with any specific regulation ultimately depends on how the deploying organization configures and uses the system.

---

## 2. Data Processing Inventory

### 2.1 Categories of Data Processed

| # | Data Category | Classification | Storage Location | Contains PII |
|---|---|---|---|---|
| 1 | User Accounts | Confidential | `data/users.json` | Yes (username, email, hashed password) |
| 2 | Session Data | Confidential | Server memory + signed cookies | Yes (user ID, IP address) |
| 3 | Agent Machine Data | Internal | `data/agents.json` | No (machine metadata only) |
| 4 | Script Execution Data | Internal | `data/scripts.json`, `data/script_executions.json` | No |
| 5 | Execution Events | Internal | `data/execution_events.json` | No |
| 6 | System Alerts | Internal | `data/alerts.json` | No |
| 7 | Admin Audit Logs | Confidential | `data/admin_logs.json` | Yes (admin username, IP address) |
| 8 | Server Logs | Confidential | `logs/server.log` | Yes (IP addresses, usernames in context) |
| 9 | Agent Activity Logs | Internal | `logs/<agent_id>_<date>.log` | No |
| 10 | Organization Data | Internal | `data/organizations.json` | No |
| 11 | System Settings | Confidential | `data/settings.json` | Potentially (SMTP credentials) |
| 12 | Backup Files | Confidential | `backup/` directory | Yes (contains user data, excludes passwords) |

### 2.2 Data Flow Diagram

```
┌──────────────┐    HTTPS/REST     ┌──────────────────┐
│  Agent        │───────────────────│                  │
│  Machines     │   Token Auth      │                  │
│  (Win/Linux)  │◄──────────────────│   BatchHost-Pro  │
└──────────────┘                    │   Server         │
                                    │                  │
┌──────────────┐    HTTPS/WSS      │   ┌────────────┐ │
│  Web Browser  │───────────────────│   │ data/      │ │
│  (Dashboard)  │   Session Cookie  │   │ logs/      │ │
│              │◄──────────────────│   │ backup/    │ │
└──────────────┘                    │   └────────────┘ │
                                    │                  │
                          SMTP      │                  │
               ┌────────────────────│                  │
               ▼                    └──────────────────┘
        ┌──────────────┐
        │ Email Server  │  (Optional, admin-configured)
        │ (SMTP)        │
        └──────────────┘
```

---

## 3. GDPR Compliance Mapping

### 3.1 Article 5 — Principles of Processing

| Principle | How BatchHost-Pro Addresses It |
|---|---|
| **Lawfulness, fairness, transparency** | Processing is based on legitimate interest (IT infrastructure monitoring) and contractual necessity (user account management). This Privacy Policy and documentation provide transparency. |
| **Purpose limitation** | Data is collected solely for infrastructure monitoring, script execution tracking, alerting, and administrative auditing. No secondary uses exist. |
| **Data minimization** | Only data necessary for monitoring operations is collected. No unnecessary personal data fields exist. User accounts contain only essential fields. |
| **Accuracy** | Administrators can update user data. Agent data is refreshed via heartbeats. Script status is maintained through a validated state machine. |
| **Storage limitation** | Execution events are capped at 10,000 entries. Session data is purged automatically. Core records persist until admin deletion for audit purposes. |
| **Integrity and confidentiality** | HTTPS encryption, password hashing, atomic writes, thread-safe operations, role-based access control, and multi-tenant isolation. |

### 3.2 Article 6 — Lawful Basis for Processing

| Processing Activity | Lawful Basis |
|---|---|
| User authentication and session management | Contractual necessity |
| Infrastructure monitoring (agents, scripts) | Legitimate interest |
| Administrative audit logging | Legal obligation / Legitimate interest |
| Email alert notifications | Consent (admin opt-in configuration) |

### 3.3 Articles 15–22 — Data Subject Rights

| Right | System Capability | Implementation |
|---|---|---|
| **Art. 15 — Access** | Admin can view and export all user data | Backup export includes all user data (except passwords) |
| **Art. 16 — Rectification** | Admin can edit user accounts | User management interface allows updating all fields |
| **Art. 17 — Erasure** | Admin can delete user accounts | Account deletion removes record from `users.json` |
| **Art. 18 — Restriction** | Admin can deactivate accounts | Setting account status to "inactive" halts all access |
| **Art. 20 — Portability** | Data stored in open JSON format | JSON/XML/PDF export capabilities |
| **Art. 21 — Object** | Admin can deactivate accounts | Contact administrator to exercise |

### 3.4 Article 25 — Data Protection by Design and Default

| Measure | Implementation |
|---|---|
| **Privacy by Design** | Self-hosted architecture — no cloud dependencies, no external data transmission |
| **Privacy by Default** | Minimal data collection, organization-based isolation, no self-registration |
| **Access by Default** | New users have no access until explicitly created by admin with specific role |
| **Encryption by Default** | HTTPS enforced for all communications |

### 3.5 Article 32 — Security of Processing

See **Section 6 (Security Controls)** below for the complete security measures mapping.

### 3.6 Article 33/34 — Breach Notification

| Requirement | System Support |
|---|---|
| **Breach Detection** | Server logs capture all access attempts, failed logins, and unauthorized access |
| **Forensic Data** | Admin audit logs provide complete trail of administrative actions |
| **Timeline Reconstruction** | Chronological logs with timestamps enable incident timeline assembly |
| **Scope Assessment** | Organization-based data isolation helps determine affected scope |

---

## 4. CCPA / CPRA Compliance Mapping

| CCPA Right | System Support |
|---|---|
| **Right to Know** | Admin can export all data associated with a user via backup |
| **Right to Delete** | Admin can delete user accounts; associated data can be purged |
| **Right to Opt-Out of Sale** | No data sale occurs — BatchHost-Pro does not sell, share, or monetize any data |
| **Right to Non-Discrimination** | System does not differentiate service based on privacy choices |
| **Right to Correct** | Admin can update user account information |

> **Important:** BatchHost-Pro does not sell personal information. No personal data is shared with third parties for commercial purposes.

---

## 5. Data Protection Impact Assessment (DPIA) Summary

### 5.1 Processing Description

| Element | Detail |
|---|---|
| **Nature** | Collection, storage, and processing of user account data and IT infrastructure monitoring data |
| **Scope** | Limited to the deploying organization's infrastructure and personnel |
| **Context** | Enterprise IT operations monitoring — batch script management and system health tracking |
| **Purpose** | Operational visibility, alerting, compliance auditing, and reporting |

### 5.2 Necessity and Proportionality

| Assessment Area | Finding |
|---|---|
| **Necessity** | Processing is necessary for the core purpose of infrastructure monitoring. No excessive data collection. |
| **Proportionality** | Data collected is proportionate to operational needs. Personal data is limited to authentication essentials (username, email, hashed password). |
| **Alternatives Considered** | File-based storage chosen for zero-dependency deployment. SHA-256 hashing chosen for password protection. Token-based auth chosen for agent security. |
| **Data Minimization** | No unnecessary personal data fields. Machine metrics are operational (CPU, memory) not personal. |

### 5.3 Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Unauthorized access to user accounts | Medium | High | Session timeout, role-based access, password hashing, HTTPS |
| Data file compromise on server | Low | High | OS-level file permissions, atomic writes, backup capability |
| Agent token theft | Low | Medium | Token required in headers, HTTPS encryption, token rotation capability |
| Session hijacking | Low | High | Signed cookies, session timeout, auto-logout, HTTPS |
| Insider threat (admin misuse) | Low | High | Admin audit logs record all actions with before/after values |
| Data loss from server failure | Medium | High | Backup system with full/incremental exports, manual recovery |

---

## 6. Security Controls

### 6.1 Access Controls

| Control | Implementation |
|---|---|
| **Authentication** | Username/email + SHA-256 hashed password |
| **Authorization** | Three-tier RBAC: Super Admin, Org Admin, Org Viewer |
| **Session Management** | 30-min timeout, auto-logout on inactivity, force-logout capability |
| **Agent Authentication** | Unique token per agent, validated on every API request |
| **Multi-Tenancy** | Organization-based data isolation at application level |
| **Account Lifecycle** | Active/Inactive status, no self-registration |

### 6.2 Data Protection Controls

| Control | Implementation |
|---|---|
| **Encryption in Transit** | HTTPS/TLS for HTTP, WSS for WebSocket, SMTP/TLS for email |
| **Password Protection** | SHA-256 one-way hashing — no plaintext storage |
| **Data Integrity** | Atomic writes via temp file + `os.replace()` |
| **Concurrency Safety** | Reentrant locks (`threading.RLock`) on all data operations |
| **Backup Security** | Passwords excluded from backup exports |
| **Log Redaction** | Password fields stripped from all request logging |

### 6.3 Audit and Monitoring Controls

| Control | Implementation |
|---|---|
| **Admin Audit Trail** | Every admin action logged with who, what, when, where, before/after |
| **Request Logging** | All HTTP requests logged with method, path, IP, duration |
| **Execution Event Logging** | Complete lifecycle event log for all script executions |
| **Agent Activity Logging** | Per-agent, per-day log files |
| **WebSocket Event Logging** | Real-time event broadcasts logged |
| **Error Logging** | Internal errors logged with full stack traces |

### 6.4 ISO 27001 Control Mapping

| ISO 27001 Control | BatchHost-Pro Feature |
|---|---|
| **A.9 Access Control** | RBAC, session management, agent token auth |
| **A.10 Cryptography** | HTTPS/TLS, SHA-256 hashing, signed session cookies |
| **A.12 Operations Security** | Server logging, admin audit logs, change tracking |
| **A.13 Communications Security** | HTTPS, WSS, SMTP/TLS |
| **A.14 System Acquisition** | Atomic writes, data integrity checks, startup self-repair |
| **A.16 Incident Management** | Alert system, logging infrastructure, audit trail |
| **A.18 Compliance** | Data export, retention controls, audit logs |

---

## 7. Data Retention and Disposal

### 7.1 Retention Schedule

| Data Type | Retention Period | Justification | Disposal Method |
|---|---|---|---|
| User Accounts | Until admin deletion | Operational necessity | JSON record removal |
| Agent Records | Until admin deletion | Operational necessity | JSON record removal |
| Script Records | Until admin deletion | Historical tracking | JSON record removal |
| Alerts | Until admin deletion | Incident history | JSON record removal |
| Execution Events | Auto-capped at 10,000 | Performance management | Oldest entries auto-pruned |
| Admin Audit Logs | Until admin clear | Compliance requirement | Bulk clear (logged action) |
| Server Logs | Continuous | Debugging and forensics | Manual rotation/deletion |
| Agent Logs | Per-day files | Operational tracking | Manual deletion |
| Session Data | 30-minute timeout | Session management | Auto-purged from memory |
| Backups | Until manual deletion | Disaster recovery | File system deletion |

### 7.2 Secure Disposal Recommendations

When disposing of data, the deploying organization should:
- Use secure file deletion tools (not just standard delete) for sensitive data files
- Ensure backup media is securely destroyed when no longer needed
- Clear all data directories before decommissioning a BatchHost-Pro server
- Document the disposal of sensitive data for compliance records

---

## 8. Third-Party Data Processing

### 8.1 Sub-Processors

BatchHost-Pro itself does not engage any third-party sub-processors. However, the following optional integrations may involve external services:

| Integration | Purpose | Data Shared | Responsibility |
|---|---|---|---|
| **SMTP Email Server** | Alert notifications | Alert details (type, severity, message, agent info) | Deploying organization's chosen SMTP provider |
| **SSL Certificate Authority** | HTTPS certificates | Server identity information only | Deploying organization's chosen CA |

### 8.2 No Data Sale or Sharing

- No personal data is sold to third parties
- No data is shared with advertising or analytics providers
- No telemetry, usage data, or crash reports are transmitted externally
- The software operates entirely within the deploying organization's network

---

## 9. Cross-Border Data Transfer Assessment

### 9.1 Default Posture

BatchHost-Pro is a **self-hosted, on-premises application**. By default, no data leaves the server on which it is installed. There are no inherent cross-border data transfers.

### 9.2 Scenarios Requiring Assessment

The deploying organization should assess cross-border implications if:

| Scenario | Consideration |
|---|---|
| Remote dashboard access from another country | User session data and dashboard content cross borders |
| SMTP server located in a different jurisdiction | Alert data is transmitted to the SMTP provider's infrastructure |
| Backup files stored on remote/cloud storage | All system data (minus passwords) would be transferred |
| Agents deployed in different countries | Agent machine data and script execution data cross borders |

### 9.3 Recommended Safeguards

For cross-border scenarios, consider implementing:
- Standard Contractual Clauses (SCCs) with SMTP providers
- VPN or private network connections for remote access
- Data residency documentation for audit purposes
- Adequacy decisions review for relevant jurisdictions

---

## 10. Incident Response and Breach Management

### 10.1 Detection Capabilities

| Detection Method | Data Source |
|---|---|
| Failed login monitoring | Server logs (`logs/server.log`) |
| Unauthorized API access | HTTP 401/403 response logging |
| Admin action tracking | Admin audit logs (`data/admin_logs.json`) |
| Agent authentication failures | Token validation logging |
| Unusual activity patterns | Combined log analysis |

### 10.2 Response Procedures (Recommended)

1. **Identify** — Review server logs, admin logs, and alert history for anomalous activity
2. **Contain** — Deactivate compromised accounts, revoke agent tokens, restrict access
3. **Assess** — Determine scope using organization-based data boundaries
4. **Notify** — Inform affected parties and regulators per applicable law
5. **Remediate** — Rotate credentials, patch vulnerabilities, update configurations
6. **Document** — Record incident details, response actions, and lessons learned

### 10.3 Notification Timeline

| Regulation | Notification Requirement |
|---|---|
| **GDPR** | 72 hours to supervisory authority; without undue delay to affected individuals |
| **CCPA** | Most expedient time possible and without unreasonable delay |
| **HIPAA** | 60 days to HHS and affected individuals |

---

## 11. Compliance Checklist for Deploying Organizations

### Pre-Deployment

- [ ] Identify applicable data protection regulations for your jurisdiction
- [ ] Conduct a Data Protection Impact Assessment (DPIA) if required
- [ ] Document the lawful basis for processing under applicable law
- [ ] Prepare a privacy notice for users of the system
- [ ] Designate a Data Protection Officer (DPO) if required

### Deployment

- [ ] Change default administrator credentials immediately
- [ ] Configure SSL/TLS certificates for HTTPS
- [ ] Restrict file system permissions on `data/`, `logs/`, `backup/` directories
- [ ] Configure network firewall rules to limit access
- [ ] Set up SMTP for email alerts (if needed)
- [ ] Document the deployment configuration

### Ongoing Operations

- [ ] Regularly review admin audit logs for unauthorized activity
- [ ] Implement server log rotation to manage storage
- [ ] Schedule and verify backup operations
- [ ] Review and deactivate unused user accounts
- [ ] Rotate agent tokens for decommissioned machines
- [ ] Update SSL certificates before expiry
- [ ] Conduct periodic access reviews

### Incident Response

- [ ] Establish an incident response plan with clear roles and responsibilities
- [ ] Test breach notification procedures
- [ ] Maintain contact list for regulatory authorities
- [ ] Document incident response exercises

---

## 12. Document Revision History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0 | May 2026 | Wahid Jamadar | Initial data compliance document |

---

## 13. Glossary

| Term | Definition |
|---|---|
| **PII** | Personally Identifiable Information — data that can identify an individual |
| **RBAC** | Role-Based Access Control — access permissions based on user roles |
| **DPIA** | Data Protection Impact Assessment — risk analysis for data processing |
| **DPO** | Data Protection Officer — individual responsible for data protection compliance |
| **SHA-256** | Secure Hash Algorithm — one-way cryptographic hash function |
| **TLS** | Transport Layer Security — encryption protocol for network communication |
| **WSS** | WebSocket Secure — encrypted WebSocket protocol |
| **SMTP** | Simple Mail Transfer Protocol — standard for email transmission |
| **Multi-Tenancy** | Architecture where a single instance serves multiple organizations with data isolation |

---

**End of Data Compliance Document**

*Built by **Wahid Jamadar** — BatchHost-Pro*
