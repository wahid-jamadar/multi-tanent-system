CREATE DATABASE IF NOT EXISTS central_multitenant CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE central_multitenant;

CREATE TABLE IF NOT EXISTS organizations (
    id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(150) NOT NULL UNIQUE,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    is_active BOOLEAN DEFAULT TRUE,
    logo VARCHAR(255) NULL,
    is_default BOOLEAN DEFAULT FALSE,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(100) PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NULL,
    is_active BOOLEAN DEFAULT TRUE,
    batchhost_role VARCHAR(50) NOT NULL DEFAULT 'viewer',
    filebridge_role VARCHAR(50) NOT NULL DEFAULT 'viewer',
    organization_id VARCHAR(100) NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    last_login DATETIME NULL,
    last_login_at DATETIME NULL,
    previous_login DATETIME NULL,
    total_logins INT DEFAULT 0,
    force_logout_at DATETIME NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NULL,
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS batchhost_agents (
    id VARCHAR(36) PRIMARY KEY,
    hostname VARCHAR(255),
    os_type VARCHAR(50),
    status VARCHAR(50),
    token VARCHAR(36),
    cpu INT DEFAULT 0,
    memory INT DEFAULT 0,
    last_heartbeat DATETIME NULL,
    registered_at DATETIME NULL,
    organization_id VARCHAR(100) NULL,
    device_key VARCHAR(255) NULL,
    last_ip VARCHAR(45) NULL,
    running_scripts TEXT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS scripts (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255),
    path TEXT,
    agent_id VARCHAR(36) NULL,
    organization_id VARCHAR(100) NULL,
    os_type VARCHAR(50),
    type VARCHAR(50),
    status VARCHAR(50),
    schedule VARCHAR(255) NULL,
    enabled BOOLEAN DEFAULT TRUE,
    created_at DATETIME NULL,
    current_run_id VARCHAR(100) NULL,
    current_execution_id VARCHAR(100) NULL,
    pid INT NULL,
    started_at DATETIME NULL,
    last_seen_running_at DATETIME NULL,
    status_updated_at DATETIME NULL,
    status_version INT DEFAULT 0,
    last_status_source VARCHAR(255) NULL,
    last_sequence_number INT DEFAULT 0,
    last_status_reason TEXT NULL,
    exit_code INT NULL,
    failed_at DATETIME NULL,
    completed_at DATETIME NULL,
    FOREIGN KEY (agent_id) REFERENCES batchhost_agents(id) ON DELETE CASCADE,
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS script_executions (
    execution_id VARCHAR(100) PRIMARY KEY,
    script_id VARCHAR(36) NULL,
    script_name VARCHAR(255),
    script_path TEXT,
    agent_id VARCHAR(36) NULL,
    organization_id VARCHAR(100) NULL,
    pid INT NULL,
    state VARCHAR(32) NOT NULL,
    started_at DATETIME NULL,
    last_seen DATETIME NULL,
    ended_at DATETIME NULL,
    runtime INT DEFAULT 0,
    exit_code INT NULL,
    cpu INT NULL,
    memory INT NULL,
    last_sequence_number INT DEFAULT 0,
    created_at DATETIME NULL,
    updated_at DATETIME NULL,
    FOREIGN KEY (script_id) REFERENCES scripts(id) ON DELETE SET NULL,
    FOREIGN KEY (agent_id) REFERENCES batchhost_agents(id) ON DELETE SET NULL,
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE SET NULL,
    INDEX idx_execution_agent_state (agent_id, state),
    INDEX idx_execution_script_started (script_id, started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS execution_events (
    id VARCHAR(36) PRIMARY KEY,
    execution_id VARCHAR(100) NULL,
    agent_id VARCHAR(36) NULL,
    script_id VARCHAR(36) NULL,
    event_type VARCHAR(64) NOT NULL,
    sequence_number INT NOT NULL,
    timestamp DATETIME NOT NULL,
    accepted BOOLEAN DEFAULT TRUE,
    reason TEXT NULL,
    pid INT NULL,
    exit_code INT NULL,
    state_after VARCHAR(32) NULL,
    FOREIGN KEY (execution_id) REFERENCES script_executions(execution_id) ON DELETE CASCADE,
    FOREIGN KEY (agent_id) REFERENCES batchhost_agents(id) ON DELETE SET NULL,
    FOREIGN KEY (script_id) REFERENCES scripts(id) ON DELETE SET NULL,
    INDEX idx_event_execution_seq (execution_id, sequence_number),
    INDEX idx_event_agent_time (agent_id, timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS batchhost_alerts (
    id VARCHAR(36) PRIMARY KEY,
    time DATETIME NULL,
    level VARCHAR(50) NULL,
    type VARCHAR(50) NULL,
    agent_id VARCHAR(36) NULL,
    organization_id VARCHAR(100) NULL,
    message TEXT NULL,
    email_sent BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (agent_id) REFERENCES batchhost_agents(id) ON DELETE CASCADE,
    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    setting_key VARCHAR(255) UNIQUE NOT NULL,
    setting_value TEXT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS admin_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timestamp DATETIME NULL,
    admin_username VARCHAR(255) NULL,
    action_type VARCHAR(255) NULL,
    module_name VARCHAR(255) NULL,
    affected_record VARCHAR(255) NULL,
    previous_value TEXT NULL,
    new_value TEXT NULL,
    ip_address VARCHAR(45) NULL,
    status VARCHAR(50) DEFAULT 'success'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agent_logs (
    id VARCHAR(36) PRIMARY KEY,
    agent_id VARCHAR(36) NULL,
    level VARCHAR(50) NULL,
    message TEXT NULL,
    timestamp DATETIME NULL,
    FOREIGN KEY (agent_id) REFERENCES batchhost_agents(id) ON DELETE CASCADE,
    INDEX idx_agent_logs_agent_time (agent_id, timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;