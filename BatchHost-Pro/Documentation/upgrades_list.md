# BatchHost-Pro — Documentation & Feature Upgrades

This document outlines the necessary upgrades to align the **BatchHost-Pro Documentation** with the actual codebase, and identifies missing features described in the documentation that are not yet fully implemented in the application.

---

## 🛠️ 1. Alignment Upgrades (App vs. Doc)
*Changes needed to make the application match the existing documentation.*

### A3. Organization-Specific Backups
- **Doc says:** Organization Admins can trigger and download backups of their organization only.
- **Current State:** Backups are global and restricted to `super_admin`.
- **Upgrade Needed:** Update the backup logic to filter JSON data by `organization_id` when triggered by an Org-Admin.

---

## 📝 2. Documentation Upgrades
*Improvements needed to the documentation to reflect technical realities.*

### D1. WebSocket Technical Overview
- **Gap:** The doc emphasizes 10-second polling for the dashboard.
- **Upgrade:** Add a section in **Section 20 (Infrastructure)** explaining the use of `Flask-SocketIO`. Describe how `execution_update` events provide sub-second latency for status changes, reducing reliance on the 10-second refresh.

### D2. "Auto Start If Crashed" Logic
- **Gap:** The doc mentions this toggle in Script Management but doesn't explain how it works.
- **Upgrade:** Add a technical note explaining that the **Agent Runtime** (the .bat/.sh on the machine) is responsible for reading this flag and performing the loop-restart logic, not the server.

### D3. Smart Default "Auto Schedule"
- **Gap:** The doc mentions "System picks a smart default."
- **Upgrade:** Define the logic. (e.g., "If name contains 'backup' -> 00:00 Daily; If name contains 'sync' -> Every 1 Hour").

---

## 🚀 3. Proposed Feature Upgrades
*Enhancements inspired by the documentation's focus on professional management.*

### F1. Remote Execution Control (Stop/Restart)
- **Concept:** Since the doc defines "Terminated" as a state, the UI should provide a "Stop" button that sends a signal to the agent to kill the process PID.
- **Benefit:** Allows admins to stop runaway scripts without RDP-ing into the machine.

### F2. Organization Branding
- **Concept:** Allow each organization to upload its own logo.
- **Benefit:** Enhances the "Multi-Tenant" feel described in the doc. The Welcome Banner would show the Org's custom logo instead of the generic system logo.

### F3. Enhanced Audit Log Diffing
- **Concept:** The Admin Audit Log mentions "Previous Value" and "New Value". 
- **Benefit:** Implement a "diff" view in `admin_logs.html` that highlights exactly which fields changed in a script or user profile.

---
*Generated: May 14, 2026 · Based on Documentation Gap Analysis*
