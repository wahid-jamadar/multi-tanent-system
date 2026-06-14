# BatchHost-Pro — Terms of Use / Terms of Service

**Document Version:** 1.0  
**Last Updated:** May 2026  
**Audience:** All Users, Administrators, Deploying Organizations  

---

## 1. Acceptance of Terms

By accessing, installing, deploying, or using **BatchHost-Pro** ("the System", "the Software", "the Service"), you & your organization agree to be bound by these Terms of Use. If you do not agree to these terms, you must not access or use the Software.

These Terms of Use govern:
- The deployment and operation of the BatchHost-Pro server software
- Access to and use of the web-based centralized monitoring dashboard and BatchHost-Pro Agent
- The deployment and operation of BatchHost-Pro agents on target machines
- The use of all associated APIs, documentation, and supporting tools

---

## 3. Service Description

BatchHost-Pro is a **self-hosted, centralized batch script monitoring and management platform** that provides:

- Real-time monitoring of distributed `.bat` (Windows) and `.sh` (Linux) script executions
- Multi-tenant organization-based data isolation
- Role-based access control (Super Admin, Organization Admin, Organization Viewer)
- Intelligent alerting for script failures, agent disconnects, and resource utilization
- Comprehensive reporting in PDF and XML formats
- Agent management with token-based authentication
- Administrative audit logging
- Automated backup and data export capabilities
- Real-time dashboard updates via WebSocket connections

---

## 4. User Accounts and Roles

### 4.1 Account Creation
- User accounts are created **exclusively by administrators** — there is no self-registration
- Administrators are responsible for assigning appropriate roles and organization memberships
- Default administrator credentials must be changed immediately upon first deployment

### 4.2 User Roles and Permissions

| Role | Scope | Capabilities |
|---|---|---|
| **Super Admin** | Global (all organizations) | Full system access — manage users, agents, scripts, organizations, settings, backups, and audit logs |
| **Organization Admin** | Single organization | Manage agents, scripts, and alerts within their assigned organization |
| **Organization Viewer** | Single organization | Read-only access to dashboard, agents, scripts, and alerts within their organization |

### 4.3 Account Responsibilities
- Users are responsible for maintaining the confidentiality of their login credentials
- Users must not share account credentials with other individuals
- Users must immediately report any suspected unauthorized access to their administrator
- Users must log out or lock their session when leaving their workstation unattended

### 4.4 Session Management
- Sessions expire after **30 minutes** of inactivity
- A session warning is issued at **25 minutes**
- Sessions can be extended by user interaction without re-login
- Auto-logout is triggered when browser tab presence is lost for more than 45 seconds (plus a 20-second grace period)
- Administrators may force-invalidate user sessions at any time

---

## 5. Acceptable Use Policy

### 5.1 Permitted Uses
You may use BatchHost-Pro to:
- Monitor and manage batch script executions across your infrastructure
- Track system health metrics (CPU, memory) of registered agent machines
- Generate reports and exports for operational and compliance purposes
- Configure automated alerting and email notifications
- Maintain audit trails of administrative actions
- Create and manage organizational data boundaries

### 5.2 Prohibited Uses
You must NOT:
- Attempt to bypass authentication, authorization, or session management controls
- Use the system to monitor machines or scripts without proper authorization from the machine owners
- Tamper with, modify, or delete JSON data files directly on the file system to circumvent application-level controls
- Use the API endpoints to automate brute-force attacks or denial-of-service actions
- Share agent authentication tokens with unauthorized parties
- Use the system to store, process, or transmit illegal content
- Reverse-engineer security mechanisms for malicious purposes
- Exceed reasonable usage limits that could degrade system performance for other users
- Use the system in violation of any applicable local, national, or international law

### 5.3 Administrator Responsibilities
Administrators are additionally responsible for:
- Changing default credentials immediately upon deployment
- Configuring SSL/TLS certificates for secure communication
- Restricting file system access to the `data/`, `logs/`, and `backup/` directories
- Regularly reviewing admin audit logs for suspicious activity
- Managing user accounts and deactivating accounts that are no longer needed
- Configuring appropriate backup schedules
- Rotating agent tokens when machines are decommissioned
- Keeping the software updated with security patches

---

## 6. Agent Deployment and Communication

### 6.1 Agent Registration
- Agents must be deployed by authorized personnel on authorized machines only
- Each agent receives a unique authentication token upon registration
- Agents communicate with the server via HTTPS REST API endpoints

### 6.2 Agent API Usage
- Agents must include their authentication token in the `X-Agent-Token` HTTP header on every request
- Agents must send heartbeats at regular intervals (every 5 seconds) to maintain online status
- Invalid or missing tokens result in HTTP 401/403 rejection

### 6.3 Agent Data Collection
- Agents report: hostname, OS type, CPU usage, memory usage, running script status, and script exit codes
- The deploying organization is responsible for ensuring that script monitoring complies with any applicable employee privacy or workplace monitoring regulations

---

## 7. Data and Intellectual Property

### 7.1 Data Ownership
- All data generated, stored, and processed by the BatchHost-Pro instance is **owned by the deploying organization**
- The software developers have no access to, claim on, or right to any data stored in any BatchHost-Pro deployment

### 7.2 Data Portability
- Data can be exported in PDF, XML, and plaintext backup formats
- JSON data files can be directly accessed and migrated by the deploying organization
- There is no vendor lock-in — all data is stored in open, human-readable formats

### 7.3 Software Intellectual Property
- BatchHost-Pro software, including its source code, templates, agent scripts, and documentation, is the intellectual property of LIST Software 

---

## 8. Availability and Performance

### 8.1 No Uptime Guarantee
- BatchHost-Pro is self-hosted software; availability depends entirely on the deploying organization's infrastructure
- There is no Service Level Agreement (SLA) provided with the software
- The software developers are not responsible for downtime, data loss, or service interruptions

### 8.2 Performance Considerations
- System performance depends on the number of agents, scripts, and concurrent users
- The file-based JSON storage model is designed for small-to-medium deployments
- Large-scale deployments should consider the documented upgrade path to SQLite
- Server log files grow continuously and require manual rotation for long-running deployments

---

## 9. Security

### 9.1 Security Measures Built In
- HTTPS/SSL/TLS encryption for all communications
- SHA-256 password hashing
- Token-based agent authentication
- Role-based access control with multi-tenant isolation
- Session timeout and auto-logout enforcement
- Atomic file writes to prevent data corruption
- Request payload logging with password redaction
- Administrative audit trail

### 9.2 Security Responsibilities of the Deploying Organization
- Securing the server operating system and network
- Managing SSL/TLS certificates (generation, renewal)
- Restricting file system permissions on data directories
- Configuring firewalls and network access controls
- Monitoring server logs for security events
- Implementing backup and disaster recovery procedures
- Ensuring physical security of the server hardware

### 9.3 Reporting Security Vulnerabilities
If you discover a security vulnerability in the BatchHost-Pro software, please report it responsibly to the software author. Do not publicly disclose vulnerabilities before they have been addressed.

---

## 10. Disclaimer of Warranties

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NONINFRINGEMENT.

IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT, OR OTHERWISE, ARISING FROM, OUT OF, OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

Specifically, the software developers do not warrant that:
- The software will be uninterrupted, error-free, or free of security vulnerabilities
- The software will meet all specific requirements of the deploying organization
- Data stored by the software will be preserved against all failure scenarios
- The software will comply with all regulations in every jurisdiction

---

## 11. Limitation of Liability

To the maximum extent permitted by applicable law:

- The software developers shall not be liable for any indirect, incidental, special, consequential, or punitive damages
- The software developers shall not be liable for any loss of data, revenue, profits, or business opportunities
- The software developers shall not be liable for damages arising from third-party actions, system failures, or data breaches
- Total liability shall not exceed the amount paid for the software (which, under the MIT License, may be zero)

---

## 12. Indemnification

The deploying organization agrees to indemnify, defend, and hold harmless the software developers from and against any claims, liabilities, damages, losses, and expenses arising from:

- The organization's use or misuse of the software
- Violation of these Terms of Use
- Violation of any applicable law or regulation
- Failure to properly secure the deployment
- Claims by third parties related to data processed by the software

---

## 13. Termination

### 13.1 User Account Termination
- Administrators may deactivate or delete user accounts at any time
- Deactivated users are immediately denied access to the system
- Account deletion removes the user record from `data/users.json`

### 13.2 Software Termination
- The deploying organization may stop using the software at any time
- Upon termination, the organization retains full ownership of all generated data
- Data files can be archived, migrated, or deleted at the organization's discretion

---

## 14. Governing Law

These Terms of Use shall be governed by and construed in accordance with the laws of the jurisdiction in which the deploying organization operates, without regard to conflict of law principles.

Any disputes arising from these terms shall be resolved through negotiation, and if necessary, through the courts of competent jurisdiction.

---

## 15. Modifications to Terms

These Terms of Use may be updated from time to time. Changes will be documented with:
- An updated version number and effective date
- Change log describing modifications
- Notification to administrators for distribution to users

Continued use of the software after modifications constitutes acceptance of the updated terms.

---

## 16. Severability

If any provision of these Terms is held to be invalid or unenforceable, the remaining provisions shall continue in full force and effect.

---

## 17. Contact Information

- **Software Author:** Wahid Jamadar
- **System Administrator:** Vaibhav Deshpande
- **Legal Inquiries:** 
---

**End of Terms of Use / Terms of Service**

*Built by **Wahid Jamadar** — BatchHost-Pro Team*
