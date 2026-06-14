# 6. Security Implementation

## TLS Everywhere

- Dashboard, REST APIs, and WebSockets must use HTTPS/WSS.
- Disable TLS 1.0 and 1.1.
- Use modern ciphers and automatic certificate rotation.
- In production, put Flask behind Nginx or HAProxy.

## Authentication

Users:

- Passwords hashed using Argon2id or bcrypt.
- Session cookies marked `Secure`, `HttpOnly`, and `SameSite=Lax`.
- Auto logout after 30 minutes of inactivity.
- Show stay-in-session alert after 25 minutes.

Agents:

- Bootstrap token used only for first registration.
- Backend issues long random agent token.
- Store only token hash in MySQL.
- Rotate tokens from dashboard.

## RBAC

Roles:

- Admin: full access to users, servers, jobs, credentials, settings, logs.
- Operator: create transfers and sync rules, view logs.
- Read-only: view servers, job status, logs, and alerts only.

Enforce RBAC in backend decorators, not only in frontend buttons.

## Signed Jobs

Every job payload should be signed before sending to an agent:

```text
canonical_payload = stable JSON with job_uuid, operation, paths, timestamps, nonce
signature = HMAC-SHA256(canonical_payload, agent_secret)
```

Agent verifies:

- Signature is valid.
- `job_uuid` matches payload.
- `expires_at` has not passed.
- Nonce has not been replayed.
- Source and destination paths are inside allowed base paths.

## Encrypted Credentials

- Store SSH keys, WinRM passwords, and SMB secrets encrypted with envelope encryption.
- Use a master key from environment variable or secret manager.
- Store `key_version` for rotation.
- Never log credentials or full command strings containing secrets.

## Path Safety

Backend and agents must reject:

- Path traversal such as `../`.
- Absolute paths outside configured base path.
- Dangerous shell metacharacters when command execution is needed.
- Symlink traversal unless explicitly allowed.

