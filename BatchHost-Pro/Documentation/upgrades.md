# BatchHost-Pro — Upgrade Roadmap

> Analyzed against the live codebase (server.py, all templates, data model).  
> Items are grouped by **perspective** and then by **priority tier**.

---

## 🧑‍💼 USER Perspective (Admins & Viewers)

### 🟢 Tier 1 — Quick Wins
---

#### U2. Script Manual Run / Force Trigger
**Gap:** Scripts can only be enabled/disabled or scheduled. There is no "Run Now" button.  
**What to add:**
- `[Run Now]` button in `script_management.html` that sends an immediate trigger to the agent
- Show a running spinner while the agent picks it up

**Files:** `script_management.html`, `server.py` (new `POST /api/scripts/<id>/run`)

---

#### U4. Alert Count Badge on Sidebar Nav
**Gap:** The sidebar shows no visual cue when alerts exist.  
**What to add:**
- A small red badge/dot next to "Alerts" in `base.html` sidebar that shows unread alert count
- Fetched via `/api/alerts` and updated every 30s

**Files:** `base.html`

---

#### U5. Date & Time Filter on Alerts Table
**Gap:** `alerts.html` has only level filters (All / Critical / Error / Warning). No date range filter.  
**What to add:**
- Date range pickers: "From" and "To" inputs
- Filter applied client-side on the already-loaded `allAlerts` array

**Files:** `alerts.html`

---

#### U6. Script Execution History / Last Run Timestamp
**Gap:** The scripts table in `script_management.html` shows Status but NOT when it last ran.  
**What to add:**
- "Last Run" column showing `completed_at` or `failed_at`
- Tooltip with full ISO timestamp on hover

**Files:** `script_management.html`

---

#### U7. Agent Search / Filter in Agents Page
**Gap:** `agents.html` has filter tabs (All/Online/Offline) but no text search.  
**What to add:**
- A search input above the agents grid to filter by hostname in real-time

**Files:** `agents.html`

---

#### U8. Dashboard "Health Score" Bar
**Gap:** Dashboard shows raw counts but gives no holistic health indicator.  
**What to add:**
- A percentage health score bar: computed as `(online_agents / total_agents) * 70 + (completed / (completed + failed)) * 30`
- Color: green (>80%), yellow (50–80%), red (<50%)

**Files:** `dashboard.html`, `server.py` (`/api/dashboard/stats`)

---

### 🟡 Tier 2 — Medium Effort

#### U9. Bulk Script Actions
**Gap:** Scripts must be enabled/disabled/deleted one at a time.  
**What to add:**
- Checkbox column in the scripts table
- "Select All" checkbox in the header
- Toolbar appears when items selected: `[Enable Selected]` `[Disable Selected]` `[Delete Selected]`

**Files:** `script_management.html`, `server.py` (new `POST /api/scripts/bulk`)

---

#### U10. Admin Logs — Export to CSV/PDF
**Gap:** `admin_logs.html` shows logs in a table but has no export option. (`server.py` already has PDF/XML export for agent logs — same pattern needed here.)  
**What to add:**
- `[Export CSV]` and `[Export PDF]` buttons in admin logs toolbar
- Backend: `GET /api/admin-logs/export?format=csv`

**Files:** `admin_logs.html`, `server.py`

---

#### U11. Organization Announcement Banner
**Gap:** There is no way for an admin to broadcast a message to viewers of a specific org.  
**What to add:**
- "Announcement" text field in the Organization Edit modal
- `viewer_announcement` field stored in `organizations.json`
- Viewers see a dismissible banner on their dashboard if a message is set

**Files:** `organizations.html`, `dashboard.html`, `server.py`

---

#### U12. Viewer Dashboard — Activity Feed
**Gap:** Viewers see the same 8-stat grid as admins but have no historical context.  
**What to add:**
- "Recent Activity" card showing last 10 events (agent online/offline, script start/complete/fail)
- Built from existing alerts + script timestamps — no new data collection needed

**Files:** `dashboard.html`, `server.py` (new `GET /api/dashboard/activity`)

---

#### U13. Script Log Viewer (In-Browser)
**Gap:** Logs exist in `logs/` as `.log` files but there is no in-UI log viewer per script.  
**What to add:**
- "View Logs" button on each script row that opens a modal
- Modal fetches and displays last 100 lines of the agent's log file for that script
- Auto-refreshes every 5s while script is running

**Files:** `script_management.html`, `server.py` (new `GET /api/scripts/<id>/logs`)

---

#### U14. User Last Active / Online Status
**Gap:** `users.html` shows `web_status` (active/inactive) but it just reflects the last login status from JSON, not real-time presence.  
**What to add:**
- Use the existing `ACTIVE_WEB_SESSIONS` dict (already in `server.py`) to power a real-time "● Online" indicator
- New API endpoint: `GET /api/users/online` returning list of currently-active user IDs

**Files:** `users.html`, `server.py`

---

### 🔵 Tier 3 — Advanced Features

#### U15. Dark / Light Mode Toggle
**Gap:** The UI is dark-mode only. No toggle exists.  
**What to add:**
- Sun/moon icon button in topbar
- CSS variables in `base.html` already use `--bg`, `--text`, etc. — just define a light theme override class on `<body>`
- Preference saved in `localStorage`

**Files:** `base.html`

---

#### U16. Script Dependency Chains
**Gap:** Scripts are independent. There is no way to say "run script B only after script A completes".  
**What to add:**
- `depends_on` field in script JSON (list of script IDs)
- Scheduler checks if dependencies are in `completed` state before triggering next script
- Visual dependency arrows in the script table

**Files:** `server.py`, `script_management.html`

---

#### U17. Dashboard Widgets — Customizable Layout
**Gap:** Dashboard stat cards are hardcoded in a fixed 4-column grid.  
**What to add:**
- Let users drag-and-drop stat cards to reorder them
- Show/hide individual cards via a settings icon
- Preferences saved per-user in `users.json` under `dashboard_layout`

**Files:** `dashboard.html`, `server.py`, `users.json`

---

#### U18. Two-Factor Authentication (2FA)
**Gap:** Login is username + password only (`login.html`). No MFA support.  
**What to add:**
- TOTP-based 2FA (Google Authenticator compatible)
- Admin can enforce 2FA per user or org-wide
- `totp_secret` and `totp_enabled` fields in `users.json`

**Files:** `login.html`, `server.py`, `users.html`, `profile.html`

---

## 🧑‍💻 DEVELOPER Perspective

### 🟢 Tier 1 — Critical Reliability

#### D1. Replace `secret_key = os.urandom(24).hex()` with a Persistent Key
**Gap (Critical):** `server.py` line 29: `app.secret_key = os.urandom(24).hex()`. This generates a **new random key every server restart**, invalidating ALL active user sessions instantly.  
**Fix:**
```python
# Load from env or a saved file, generate once
SECRET_KEY_FILE = os.path.join(BASE_DIR, "data", ".secret_key")
if os.path.exists(SECRET_KEY_FILE):
    with open(SECRET_KEY_FILE, "r") as f:
        app.secret_key = f.read().strip()
else:
    key = os.urandom(24).hex()
    with open(SECRET_KEY_FILE, "w") as f:
        f.write(key)
    app.secret_key = key
```

---

#### D2. Replace JSON File Storage with SQLite
**Gap:** All data (`users.json`, `agents.json`, `scripts.json`, etc.) is stored as flat JSON files. This causes:
- Race conditions under concurrent writes (multiple threads write simultaneously)
- No atomic transactions
- Full file read/write for every change (poor performance at scale)

**Fix:**
- Migrate to SQLite using Python's built-in `sqlite3` module (zero new dependencies)
- A `db/batchhost.db` file replaces the JSON files
- The schema is already designed in `db/script.sql` — just needs the `organization_id`, `previous_login`, `total_logins` columns added

---

#### D3. Add Rate Limiting to `/api/login`
**Gap:** The login endpoint (`POST /login`) has no brute-force protection.  
**Fix:**
- Track failed attempts per IP in memory or a simple JSON counter
- Lock out IP after 10 failures within 5 minutes
- Return `HTTP 429 Too Many Requests`

**Files:** `server.py`

---

#### D4. SMTP Password Stored in Plaintext
**Gap:** `settings.json` stores `smtp_pass` as plaintext.  
**Fix:**
- Encrypt using `cryptography` library (Fernet symmetric encryption)
- Store the encryption key in an env variable or `.secret_key`-style file
- Decrypt only at send time

**Files:** `server.py`

---

### 🟡 Tier 2 — Code Quality

#### D5. Centralized API Error Handling
**Gap:** Each route has its own `try/except` with inconsistent error formats (`{"error": "..."}` vs `{"success": false, "message": "..."}`).  
**Fix:**
- Add a Flask `@app.errorhandler` for common HTTP errors
- Standardize all API responses to `{"success": bool, "data": ..., "error": str|null}`

---

#### D6. Environment-Based Configuration
**Gap:** Constants like `PRESENCE_TIMEOUT_SECONDS = 45`, `SESSION_TIMEOUT_SECONDS = 30 * 60`, and file paths are hardcoded in `server.py`.  
**Fix:**
- Load from `.env` file using `python-dotenv`
- Example `.env`:
```
SESSION_TIMEOUT_SECONDS=1800
PRESENCE_TIMEOUT_SECONDS=45
LOG_LEVEL=INFO
SECRET_KEY=...
```

---

#### D7. API Versioning
**Gap:** All API routes are `/api/...` with no versioning. Breaking changes will break all agent clients immediately.  
**Fix:**
- Prefix all routes with `/api/v1/...`
- Keep old `/api/...` routes as aliases for now with a deprecation log warning

---

#### D8. Agent Token Rotation
**Gap:** Agent tokens (in `agents.json`) are assigned once at registration and never rotated. A leaked token gives permanent access.  
**Fix:**
- Add `POST /api/agents/<id>/rotate-token` (admin only)
- Store `token_issued_at` in agent record
- Optionally auto-expire tokens older than 90 days

**Files:** `server.py`, `agents.html`

---

#### D9. Structured Logging with Log Levels
**Gap:** `server.py` uses basic `logging.basicConfig` with a single `server.log` file. All levels go to one file.  
**Fix:**
- Separate log files: `server.log` (INFO+), `error.log` (ERROR+)
- Add request logging middleware (method, path, status code, duration)
- Include `user_id` in log context for audit trail

---

#### D10. Heartbeat Monitor — Configurable Timeout
**Gap:** `heartbeat_monitor()` hardcodes `diff > 30` (seconds) before marking an agent offline.  
**Fix:**
- Make this configurable per-agent or globally via `settings.json`
- Add `heartbeat_timeout_seconds` field to agent or to global settings

---

### 🔵 Tier 3 — Infrastructure & Scalability

#### D11. Docker `healthcheck` in Dockerfile
**Gap:** No `HEALTHCHECK` instruction in the Dockerfile. Container orchestrators can't detect if the app is hung.  
**Fix:**
```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD curl -f https://172.100.31.40:443/ || exit 1
```

---

#### D12. SSL Certificate Auto-Renewal
**Gap:** `cert.pem` / `key.pem` are static files. When they expire, the server goes down.  
**Fix:**
- Add a background thread that checks cert expiry every 24h
- Log a CRITICAL warning when < 30 days remain
- Support Let's Encrypt via `certbot` or `acme.py` integration

---

#### D13. Backup — Automated Verification
**Gap:** `backup/` directory exists but there is no verification that backups are readable/uncorrupted.  
**Fix:**
- After each backup, run a checksum and store it alongside the backup file
- A `GET /api/backups/<id>/verify` endpoint to manually trigger verification
- Alert if checksum mismatch detected

---

#### D14. Agent Communication — Webhook Support
**Gap:** Agents only push data via heartbeat. There is no way for the server to push notifications to agents (e.g., "script was disabled remotely").  
**Fix:**
- Add a `pending_commands` queue per agent in `agents.json`
- Agent polls `GET /api/agent/commands` on each heartbeat and executes queued commands

---

## 📋 Priority Summary Table

| ID  | Feature | Perspective | Priority | Effort |
|-----|---------|-------------|----------|--------|
| D1  | Persistent secret key | Dev | 🔴 Critical | Low |
| D3  | Login rate limiting | Dev | 🔴 Critical | Low |
| U3  | Change password from profile | User | 🟠 High | Low |
| U1  | Alert acknowledge/snooze | User | 🟠 High | Low |
| U2  | Script "Run Now" button | User | 🟠 High | Low |
| U4  | Alert badge on sidebar | User | 🟠 High | Low |
| U6  | Last run / next run columns | User | 🟠 High | Low |
| D2  | SQLite migration | Dev | 🟡 Medium | High |
| D4  | Encrypt SMTP password | Dev | 🟡 Medium | Low |
| D5  | Centralized error handling | Dev | 🟡 Medium | Medium |
| U9  | Bulk script actions | User | 🟡 Medium | Medium |
| U10 | Admin logs CSV/PDF export | User | 🟡 Medium | Low |
| U13 | In-browser log viewer | User | 🟡 Medium | Medium |
| U15 | Dark/Light mode toggle | User | 🟡 Medium | Low |
| D6  | Env-based configuration | Dev | 🟡 Medium | Low |
| D8  | Agent token rotation | Dev | 🟡 Medium | Low |
| U18 | Two-Factor Authentication | User | 🔵 Advanced | High |
| U16 | Script dependency chains | User | 🔵 Advanced | High |
| D12 | SSL auto-renewal | Dev | 🔵 Advanced | Medium |
| D14 | Agent webhook/command queue | Dev | 🔵 Advanced | High |

---

## 🗂️ Files Impact Map

| File | Affected Upgrades |
|------|------------------|
| `server.py` | D1, D2, D3, D4, D5, D6, D7, D8, D9, D10, D14, U2, U3, U9, U10, U13, U14 |
| `base.html` | U4, U15 |
| `dashboard.html` | U8, U11, U12, U17 |
| `alerts.html` | U1, U5, U10 |
| `script_management.html` | U2, U6, U7, U9, U13 |
| `agents.html` | U7, D8 |
| `profile.html` | U3, U18 |
| `users.html` | U14, U18 |
| `organizations.html` | U11 |
| `settings.html` | D4, D10 |
| `Dockerfile` | D11, D12 |

---

*Last updated: May 2026 · Based on BatchHost-Pro codebase review*
