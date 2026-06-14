# 4. Database Schema

The database is the source of truth for users, servers, agents, jobs, sync rules, credentials, alerts, and logs.

## Entity Relationships

```text
users 1..n audit_logs
users 1..n transfer_jobs
roles n..n users through user_roles
servers 1..n agents
servers 1..n server_credentials
servers 1..n file_index
sync_rules 1..n sync_runs
transfer_jobs 1..n job_events
transfer_jobs 1..n file_versions
agents 1..n heartbeats
agents 1..n job_events
```

## Core Tables

```sql
CREATE TABLE roles (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(50) NOT NULL UNIQUE,
  description VARCHAR(255),
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE users (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  username VARCHAR(100) NOT NULL UNIQUE,
  email VARCHAR(255) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  last_login_at DATETIME NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE user_roles (
  user_id BIGINT NOT NULL,
  role_id BIGINT NOT NULL,
  PRIMARY KEY (user_id, role_id),
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (role_id) REFERENCES roles(id)
);

CREATE TABLE servers (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(150) NOT NULL,
  hostname VARCHAR(255) NOT NULL,
  ip_address VARCHAR(45),
  os_type ENUM('linux','ubuntu','windows') NOT NULL,
  protocol ENUM('ssh','winrm','smb','local') NOT NULL,
  port INT NOT NULL,
  base_path VARCHAR(1000) NOT NULL,
  status ENUM('online','offline','disabled','unknown') NOT NULL DEFAULT 'unknown',
  is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_by BIGINT,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (created_by) REFERENCES users(id),
  UNIQUE KEY uq_server_name (name),
  INDEX idx_servers_status (status, is_enabled),
  INDEX idx_servers_host (hostname, ip_address)
);

CREATE TABLE agents (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  server_id BIGINT NOT NULL,
  agent_uuid CHAR(36) NOT NULL UNIQUE,
  agent_name VARCHAR(150) NOT NULL,
  version VARCHAR(50),
  public_key TEXT,
  auth_token_hash CHAR(64) NOT NULL,
  last_heartbeat_at DATETIME NULL,
  status ENUM('online','offline','disabled') NOT NULL DEFAULT 'offline',
  capabilities JSON,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (server_id) REFERENCES servers(id),
  INDEX idx_agents_server_status (server_id, status),
  INDEX idx_agents_heartbeat (last_heartbeat_at)
);

CREATE TABLE server_credentials (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  server_id BIGINT NOT NULL,
  credential_type ENUM('ssh_key','password','winrm','smb') NOT NULL,
  username VARCHAR(255) NOT NULL,
  encrypted_secret VARBINARY(4096) NOT NULL,
  key_version INT NOT NULL DEFAULT 1,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (server_id) REFERENCES servers(id),
  INDEX idx_credentials_server (server_id, credential_type)
);

CREATE TABLE transfer_jobs (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  job_uuid CHAR(36) NOT NULL UNIQUE,
  job_type ENUM('copy','move','sync','delete','mkdir','bulk') NOT NULL,
  source_server_id BIGINT NULL,
  destination_server_id BIGINT NULL,
  source_path VARCHAR(2000) NOT NULL,
  destination_path VARCHAR(2000),
  status ENUM('queued','assigned','running','success','failed','cancelled','retrying','conflict') NOT NULL DEFAULT 'queued',
  priority INT NOT NULL DEFAULT 5,
  checksum_sha256 CHAR(64) NULL,
  total_bytes BIGINT NOT NULL DEFAULT 0,
  transferred_bytes BIGINT NOT NULL DEFAULT 0,
  retry_count INT NOT NULL DEFAULT 0,
  max_retries INT NOT NULL DEFAULT 3,
  scheduled_at DATETIME NULL,
  started_at DATETIME NULL,
  completed_at DATETIME NULL,
  created_by BIGINT NULL,
  assigned_agent_id BIGINT NULL,
  signed_payload TEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (source_server_id) REFERENCES servers(id),
  FOREIGN KEY (destination_server_id) REFERENCES servers(id),
  FOREIGN KEY (created_by) REFERENCES users(id),
  FOREIGN KEY (assigned_agent_id) REFERENCES agents(id),
  INDEX idx_jobs_status_priority (status, priority, scheduled_at),
  INDEX idx_jobs_source_dest (source_server_id, destination_server_id),
  INDEX idx_jobs_agent_status (assigned_agent_id, status),
  INDEX idx_jobs_created_at (created_at)
);

CREATE TABLE sync_rules (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(150) NOT NULL,
  left_server_id BIGINT NOT NULL,
  right_server_id BIGINT NOT NULL,
  left_path VARCHAR(2000) NOT NULL,
  right_path VARCHAR(2000) NOT NULL,
  direction ENUM('left_to_right','right_to_left','bidirectional') NOT NULL,
  conflict_policy ENUM('last_write_wins','versioning','manual') NOT NULL DEFAULT 'versioning',
  schedule_cron VARCHAR(120),
  timezone VARCHAR(80) NOT NULL DEFAULT 'UTC',
  is_realtime BOOLEAN NOT NULL DEFAULT FALSE,
  is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_by BIGINT,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (left_server_id) REFERENCES servers(id),
  FOREIGN KEY (right_server_id) REFERENCES servers(id),
  FOREIGN KEY (created_by) REFERENCES users(id),
  INDEX idx_sync_enabled_schedule (is_enabled, schedule_cron),
  INDEX idx_sync_servers (left_server_id, right_server_id)
);

CREATE TABLE sync_runs (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  sync_rule_id BIGINT NOT NULL,
  status ENUM('running','success','failed','partial','conflict') NOT NULL,
  files_scanned INT NOT NULL DEFAULT 0,
  files_copied INT NOT NULL DEFAULT 0,
  files_updated INT NOT NULL DEFAULT 0,
  files_deleted INT NOT NULL DEFAULT 0,
  conflicts INT NOT NULL DEFAULT 0,
  started_at DATETIME NOT NULL,
  completed_at DATETIME NULL,
  error_message TEXT,
  FOREIGN KEY (sync_rule_id) REFERENCES sync_rules(id),
  INDEX idx_sync_runs_rule_time (sync_rule_id, started_at),
  INDEX idx_sync_runs_status (status)
);

CREATE TABLE file_index (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  server_id BIGINT NOT NULL,
  relative_path VARCHAR(2000) NOT NULL,
  absolute_path VARCHAR(3000) NOT NULL,
  file_size BIGINT NOT NULL,
  checksum_sha256 CHAR(64) NULL,
  modified_at DATETIME NOT NULL,
  inode_or_file_id VARCHAR(255) NULL,
  version_no INT NOT NULL DEFAULT 1,
  is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
  indexed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (server_id) REFERENCES servers(id),
  UNIQUE KEY uq_file_server_path (server_id, relative_path),
  INDEX idx_file_modified (server_id, modified_at),
  INDEX idx_file_checksum (checksum_sha256)
);

CREATE TABLE file_versions (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  file_index_id BIGINT NULL,
  job_id BIGINT NULL,
  server_id BIGINT NOT NULL,
  relative_path VARCHAR(2000) NOT NULL,
  version_no INT NOT NULL,
  checksum_sha256 CHAR(64),
  file_size BIGINT NOT NULL,
  backup_path VARCHAR(3000) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (file_index_id) REFERENCES file_index(id),
  FOREIGN KEY (job_id) REFERENCES transfer_jobs(id),
  FOREIGN KEY (server_id) REFERENCES servers(id),
  INDEX idx_versions_file (server_id, relative_path, version_no)
);

CREATE TABLE job_events (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  job_id BIGINT NOT NULL,
  agent_id BIGINT NULL,
  event_type ENUM('assigned','started','progress','success','failure','retry','conflict','cancelled') NOT NULL,
  message TEXT,
  progress_percent DECIMAL(5,2) NOT NULL DEFAULT 0,
  bytes_done BIGINT NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (job_id) REFERENCES transfer_jobs(id),
  FOREIGN KEY (agent_id) REFERENCES agents(id),
  INDEX idx_job_events_job_time (job_id, created_at),
  INDEX idx_job_events_type_time (event_type, created_at)
);

CREATE TABLE audit_logs (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NULL,
  action VARCHAR(120) NOT NULL,
  entity_type VARCHAR(80),
  entity_id BIGINT,
  ip_address VARCHAR(45),
  user_agent VARCHAR(500),
  details JSON,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id),
  INDEX idx_audit_user_time (user_id, created_at),
  INDEX idx_audit_action_time (action, created_at)
);

CREATE TABLE system_logs (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  level ENUM('DEBUG','INFO','WARNING','ERROR','CRITICAL') NOT NULL,
  component VARCHAR(100) NOT NULL,
  message TEXT NOT NULL,
  context JSON,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_system_level_time (level, created_at),
  INDEX idx_system_component_time (component, created_at)
);

CREATE TABLE alerts (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  severity ENUM('info','warning','critical') NOT NULL,
  title VARCHAR(255) NOT NULL,
  message TEXT NOT NULL,
  status ENUM('open','acknowledged','resolved') NOT NULL DEFAULT 'open',
  source_type VARCHAR(80),
  source_id BIGINT,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  acknowledged_by BIGINT NULL,
  resolved_at DATETIME NULL,
  FOREIGN KEY (acknowledged_by) REFERENCES users(id),
  INDEX idx_alert_status_severity (status, severity, created_at)
);

CREATE TABLE app_settings (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  setting_key VARCHAR(120) NOT NULL UNIQUE,
  setting_value JSON NOT NULL,
  encrypted BOOLEAN NOT NULL DEFAULT FALSE,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE db_backups (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  backup_name VARCHAR(255) NOT NULL,
  backup_path VARCHAR(3000) NOT NULL,
  status ENUM('running','success','failed') NOT NULL,
  size_bytes BIGINT DEFAULT 0,
  started_at DATETIME NOT NULL,
  completed_at DATETIME NULL,
  error_message TEXT,
  INDEX idx_db_backups_time_status (started_at, status)
);
```

## Indexing Strategy

- Use composite indexes for dashboard filters: status plus timestamp.
- Use unique server/path index in `file_index` to prevent duplicate file records.
- Use `checksum_sha256` index for duplicate detection.
- Partition large log tables by month once volume grows.
- Archive old `job_events`, `system_logs`, and `audit_logs` to cold storage after retention period.

## Sample Queries

Queued jobs for an agent:

```sql
SELECT *
FROM transfer_jobs
WHERE status = 'queued'
  AND scheduled_at <= UTC_TIMESTAMP()
ORDER BY priority ASC, created_at ASC
LIMIT 10;
```

Server health dashboard:

```sql
SELECT s.id, s.name, s.os_type, s.status, a.agent_uuid, a.last_heartbeat_at,
       TIMESTAMPDIFF(SECOND, a.last_heartbeat_at, UTC_TIMESTAMP()) AS heartbeat_age_seconds
FROM servers s
LEFT JOIN agents a ON a.server_id = s.id
WHERE s.is_enabled = TRUE
ORDER BY s.name;
```

Find duplicates across servers:

```sql
SELECT checksum_sha256, COUNT(*) AS copies, SUM(file_size) AS total_bytes
FROM file_index
WHERE checksum_sha256 IS NOT NULL
  AND is_deleted = FALSE
GROUP BY checksum_sha256
HAVING COUNT(*) > 1;
```

Recent failed operations:

```sql
SELECT tj.job_uuid, tj.job_type, tj.source_path, tj.destination_path,
       je.message, je.created_at
FROM transfer_jobs tj
JOIN job_events je ON je.job_id = tj.id
WHERE tj.status = 'failed'
ORDER BY je.created_at DESC
LIMIT 50;
```

