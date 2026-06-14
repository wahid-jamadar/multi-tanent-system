import os
import json
import pymysql
from datetime import datetime

print("=== STARTING BATCHHOST-PRO TO MYSQL MIGRATION ===")

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'List@123',
    'port': 3306
}

# 1. Connect and initialize schema
conn = pymysql.connect(**DB_CONFIG)
try:
    cursor = conn.cursor()
    cursor.execute("USE central_multitenant;")
    
    # Drop BatchHost-Pro specific tables to ensure clean recreate with correct column types
    tables_to_drop = [
        "execution_events",
        "script_executions",
        "agent_logs",
        "scripts",
        "batchhost_alerts",
        "batchhost_agents",
        "admin_logs",
        "settings"
    ]
    print("Dropping existing BatchHost-Pro tables for clean schema application...")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
    for t in tables_to_drop:
        cursor.execute(f"DROP TABLE IF EXISTS `{t}`;")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
    
    # Read script.sql
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "script.sql")
    print(f"Reading schema from: {script_path}")
    with open(script_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()
        
    # Split by semicolon and run statements
    statements = schema_sql.split(";")
    for stmt in statements:
        stmt = stmt.strip()
        if stmt:
            cursor.execute(stmt)
            
    # Ensure specific columns on shared tables exist
    cursor.execute("USE central_multitenant;")
    try:
        cursor.execute("ALTER TABLE organizations ADD COLUMN is_default BOOLEAN DEFAULT FALSE;")
        print("Added/verified is_default column in organizations.")
    except Exception as e:
        if "Duplicate column name" not in str(e):
            print(f"Note/Warning on organizations column: {e}")

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN force_logout_at DATETIME NULL;")
        print("Added/verified force_logout_at column in users.")
    except Exception as e:
        if "Duplicate column name" not in str(e):
            print(f"Note/Warning on users column: {e}")
            
    conn.commit()
    print("MySQL schema applied successfully.")
finally:
    conn.close()

# 2. Reconnect to target database
conn = pymysql.connect(database="central_multitenant", **DB_CONFIG)
cursor = conn.cursor()

def parse_dt(val):
    if not val:
        return None
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(val)
    try:
        if isinstance(val, str):
            val = val.replace('Z', '+00:00')
            return datetime.fromisoformat(val)
        return val
    except Exception as e:
        print(f"Warning: Failed to parse datetime '{val}': {e}")
        return None

def migrate_table(json_file_name, query, row_mapper):
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    json_path = os.path.join(data_dir, json_file_name)
    if not os.path.exists(json_path):
        print(f"File {json_file_name} does not exist, skipping.")
        return
        
    print(f"Migrating {json_file_name}...")
    with open(json_path, "r", encoding="utf-8") as f:
        records = json.load(f)
        
    if isinstance(records, dict):
        # Handle dict format (e.g. settings or backup_state)
        records = [records]
        
    count = 0
    for r in records:
        params = row_mapper(r)
        if params is not None:
            cursor.execute(query, params)
            count += 1
            
    conn.commit()
    print(f"Migrated {count} records from {json_file_name}.")

try:
    # Disable foreign key checks for migration
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
    
    # 1. Organizations
    migrate_table(
        "organizations.json",
        """INSERT INTO organizations (id, name, status, logo, is_default, created_at)
           VALUES (%s, %s, %s, %s, %s, %s)
           ON DUPLICATE KEY UPDATE name=%s, status=%s, logo=%s, is_default=%s, created_at=%s""",
        lambda r: (
            r['id'], r['name'], r.get('status', 'active'), r.get('logo'), bool(r.get('is_default')), parse_dt(r.get('created_at')),
            r['name'], r.get('status', 'active'), r.get('logo'), bool(r.get('is_default')), parse_dt(r.get('created_at'))
        )
    )

    # 2. Users
    migrate_table(
        "users.json",
        """INSERT INTO users (id, username, email, password, batchhost_role, filebridge_role, organization_id, status, last_login, previous_login, total_logins, force_logout_at, created_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON DUPLICATE KEY UPDATE username=%s, email=%s, password=%s, batchhost_role=%s, filebridge_role=%s, organization_id=%s, status=%s, last_login=%s, previous_login=%s, total_logins=%s, force_logout_at=%s, created_at=%s""",
        lambda r: (
            r['id'], r['username'], r['email'], r['password'], r.get('batchhost_role', 'viewer'), r.get('filebridge_role', 'viewer'), r.get('organization_id'), r.get('status', 'active'), parse_dt(r.get('last_login')), parse_dt(r.get('previous_login')), r.get('total_logins', 0), parse_dt(r.get('force_logout_at')), parse_dt(r.get('created_at')),
            r['username'], r['email'], r['password'], r.get('batchhost_role', 'viewer'), r.get('filebridge_role', 'viewer'), r.get('organization_id'), r.get('status', 'active'), parse_dt(r.get('last_login')), parse_dt(r.get('previous_login')), r.get('total_logins', 0), parse_dt(r.get('force_logout_at')), parse_dt(r.get('created_at'))
        )
    )

    # 3. Agents (stored in batchhost_agents)
    migrate_table(
        "agents.json",
        """INSERT INTO batchhost_agents (id, hostname, os_type, status, token, cpu, memory, last_heartbeat, registered_at, organization_id, device_key, last_ip, running_scripts)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON DUPLICATE KEY UPDATE hostname=%s, os_type=%s, status=%s, token=%s, cpu=%s, memory=%s, last_heartbeat=%s, registered_at=%s, organization_id=%s, device_key=%s, last_ip=%s, running_scripts=%s""",
        lambda r: (
            r['id'], r.get('hostname'), r.get('os_type'), r.get('status'), r.get('token'), r.get('cpu', 0), r.get('memory', 0), parse_dt(r.get('last_heartbeat')), parse_dt(r.get('registered_at')), r.get('organization_id'), r.get('device_key'), r.get('last_ip'), json.dumps(r.get('running_scripts', [])),
            r.get('hostname'), r.get('os_type'), r.get('status'), r.get('token'), r.get('cpu', 0), r.get('memory', 0), parse_dt(r.get('last_heartbeat')), parse_dt(r.get('registered_at')), r.get('organization_id'), r.get('device_key'), r.get('last_ip'), json.dumps(r.get('running_scripts', []))
        )
    )

    # 4. Scripts
    migrate_table(
        "scripts.json",
        """INSERT INTO scripts (id, name, path, agent_id, organization_id, os_type, type, status, schedule, enabled, created_at, current_run_id, current_execution_id, pid, started_at, last_seen_running_at, status_updated_at, status_version, last_status_source, last_sequence_number, last_status_reason, exit_code, failed_at, completed_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON DUPLICATE KEY UPDATE name=%s, path=%s, agent_id=%s, organization_id=%s, os_type=%s, type=%s, status=%s, schedule=%s, enabled=%s, created_at=%s, current_run_id=%s, current_execution_id=%s, pid=%s, started_at=%s, last_seen_running_at=%s, status_updated_at=%s, status_version=%s, last_status_source=%s, last_sequence_number=%s, last_status_reason=%s, exit_code=%s, failed_at=%s, completed_at=%s""",
        lambda r: (
            r['id'], r.get('name'), r.get('path'), r.get('agent_id'), r.get('organization_id'), r.get('os_type'), r.get('type'), r.get('status'), r.get('schedule'), bool(r.get('enabled', True)), parse_dt(r.get('created_at')), r.get('current_run_id'), r.get('current_execution_id'), r.get('pid'), parse_dt(r.get('started_at')), parse_dt(r.get('last_seen_running_at')), parse_dt(r.get('status_updated_at')), r.get('status_version', 0), r.get('last_status_source'), r.get('last_sequence_number', 0), r.get('last_status_reason'), r.get('exit_code'), parse_dt(r.get('failed_at')), parse_dt(r.get('completed_at')),
            r.get('name'), r.get('path'), r.get('agent_id'), r.get('organization_id'), r.get('os_type'), r.get('type'), r.get('status'), r.get('schedule'), bool(r.get('enabled', True)), parse_dt(r.get('created_at')), r.get('current_run_id'), r.get('current_execution_id'), r.get('pid'), parse_dt(r.get('started_at')), parse_dt(r.get('last_seen_running_at')), parse_dt(r.get('status_updated_at')), r.get('status_version', 0), r.get('last_status_source'), r.get('last_sequence_number', 0), r.get('last_status_reason'), r.get('exit_code'), parse_dt(r.get('failed_at')), parse_dt(r.get('completed_at'))
        )
    )

    # 5. Script Executions
    migrate_table(
        "script_executions.json",
        """INSERT INTO script_executions (execution_id, script_id, script_name, script_path, agent_id, organization_id, pid, state, created_at, started_at, last_seen, last_sequence_number, runtime, exit_code, cpu, memory, updated_at, ended_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON DUPLICATE KEY UPDATE script_id=%s, script_name=%s, script_path=%s, agent_id=%s, organization_id=%s, pid=%s, state=%s, created_at=%s, started_at=%s, last_seen=%s, last_sequence_number=%s, runtime=%s, exit_code=%s, cpu=%s, memory=%s, updated_at=%s, ended_at=%s""",
        lambda r: (
            r['execution_id'], r.get('script_id'), r.get('script_name'), r.get('script_path'), r.get('agent_id'), r.get('organization_id'), r.get('pid'), r.get('state'), parse_dt(r.get('created_at')), parse_dt(r.get('started_at')), parse_dt(r.get('last_seen')), r.get('last_sequence_number', 0), r.get('runtime', 0), r.get('exit_code'), r.get('cpu'), r.get('memory'), parse_dt(r.get('updated_at')), parse_dt(r.get('ended_at')),
            r.get('script_id'), r.get('script_name'), r.get('script_path'), r.get('agent_id'), r.get('organization_id'), r.get('pid'), r.get('state'), parse_dt(r.get('created_at')), parse_dt(r.get('started_at')), parse_dt(r.get('last_seen')), r.get('last_sequence_number', 0), r.get('runtime', 0), r.get('exit_code'), r.get('cpu'), r.get('memory'), parse_dt(r.get('updated_at')), parse_dt(r.get('ended_at'))
        )
    )

    # 6. Execution Events
    migrate_table(
        "execution_events.json",
        """INSERT INTO execution_events (id, execution_id, agent_id, script_id, event_type, sequence_number, timestamp, accepted, reason, pid, exit_code, state_after)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON DUPLICATE KEY UPDATE execution_id=%s, agent_id=%s, script_id=%s, event_type=%s, sequence_number=%s, timestamp=%s, accepted=%s, reason=%s, pid=%s, exit_code=%s, state_after=%s""",
        lambda r: (
            r['id'], r.get('execution_id'), r.get('agent_id'), r.get('script_id'), r.get('event_type'), r.get('sequence_number'), parse_dt(r.get('timestamp')), bool(r.get('accepted', True)), r.get('reason'), r.get('pid'), r.get('exit_code'), r.get('state_after'),
            r.get('execution_id'), r.get('agent_id'), r.get('script_id'), r.get('event_type'), r.get('sequence_number'), parse_dt(r.get('timestamp')), bool(r.get('accepted', True)), r.get('reason'), r.get('pid'), r.get('exit_code'), r.get('state_after')
        )
    )

    # 7. Alerts (stored in batchhost_alerts)
    migrate_table(
        "alerts.json",
        """INSERT INTO batchhost_alerts (id, time, level, type, agent_id, organization_id, message, email_sent)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
           ON DUPLICATE KEY UPDATE time=%s, level=%s, type=%s, agent_id=%s, organization_id=%s, message=%s, email_sent=%s""",
        lambda r: (
            r['id'], parse_dt(r.get('time')), r.get('level'), r.get('type'), r.get('agent_id'), r.get('organization_id'), r.get('message'), bool(r.get('email_sent')),
            parse_dt(r.get('time')), r.get('level'), r.get('type'), r.get('agent_id'), r.get('organization_id'), r.get('message'), bool(r.get('email_sent'))
        )
    )

    # 8. Admin Logs
    print("Clearing admin_logs table...")
    cursor.execute("TRUNCATE TABLE admin_logs;")
    migrate_table(
        "admin_logs.json",
        """INSERT INTO admin_logs (timestamp, admin_username, action_type, module_name, affected_record, previous_value, new_value, ip_address, status)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        lambda r: (
            parse_dt(r.get('timestamp')), r.get('admin_username'), r.get('action_type'), r.get('module_name'), r.get('affected_record'), r.get('previous_value'), r.get('new_value'), r.get('ip_address'), r.get('status', 'success')
        )
    )

    # 9. Settings
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    settings_path = os.path.join(data_dir, "settings.json")
    if os.path.exists(settings_path):
        print("Migrating settings.json...")
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
        for k, v in settings.items():
            val_str = json.dumps(v) if isinstance(v, (dict, list)) else str(v)
            cursor.execute(
                """INSERT INTO settings (setting_key, setting_value) VALUES (%s, %s)
                   ON DUPLICATE KEY UPDATE setting_value=%s""",
                (k, val_str, val_str)
            )
        print("Migrated settings.")

    # 10. Backup State
    backup_state_path = os.path.join(data_dir, "backup_state.json")
    if os.path.exists(backup_state_path):
        print("Migrating backup_state.json...")
        with open(backup_state_path, "r", encoding="utf-8") as f:
            backup_state = json.load(f)
        val_str = json.dumps(backup_state)
        cursor.execute(
            """INSERT INTO settings (setting_key, setting_value) VALUES (%s, %s)
               ON DUPLICATE KEY UPDATE setting_value=%s""",
            ("backup_state", val_str, val_str)
        )
        print("Migrated backup state.")

    # Re-enable foreign key checks
    cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
    
    conn.commit()
    print("=== DATA MIGRATION COMPLETE ===")
except Exception as e:
    cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
    conn.rollback()
    print(f"ERROR: Migration failed: {e}")
    raise
finally:
    conn.close()
