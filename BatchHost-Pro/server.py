import sys
import subprocess

# Ensure we run under Python 3.13
if sys.version_info[:2] != (3, 13):
    print(f"[*] BatchHost-Pro detected Python {sys.version_info.major}.{sys.version_info.minor}, but Python 3.13 is required.")
    print("[*] Attempting to auto-relaunch using Python 3.13 (py -3.13)...")
    try:
        # Check if py -3.13 is available
        result = subprocess.run(["py", "-3.13", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            # Re-run the script with Python 3.13
            args = ["py", "-3.13"] + sys.argv
            proc = subprocess.run(args)
            sys.exit(proc.returncode)
    except Exception as e:
        pass
        
    print("\n" + "="*80)
    print("CRITICAL ERROR: Python 3.13 is required to run BatchHost-Pro!")
    print("Current Python version in use: " + sys.version)
    print("\nTo start the server, please use the Python 3.13 launcher:")
    print("    py -3.13 server.py")
    print("="*80 + "\n")
    sys.exit(1)

import os
import json
import uuid
import time
import hashlib
import logging
import smtplib
import threading
from datetime import datetime, timedelta
from functools import wraps
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_file, send_from_directory, g
from waitress import serve
import tempfile
import re
import xml.etree.ElementTree as ET
# from io import BytesIO
from reportlab.lib.pagesizes import landscape, A4
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle,
    Paragraph, Spacer, # PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from flask_socketio import SocketIO, join_room #emit, leave_room
from backend.tracking import (
    ACTIVE_STATES,
    EVENT_TYPES,
    HEARTBEAT_INTERVAL_SECONDS,
    TERMINAL_STATES,
    TIMEOUT_THRESHOLD_SECONDS,
    ExecutionManager,
)
from backend.rate_limiter import (
    rate_limit,
    rate_limiter,
    check_login_brute_force,
    record_login_failure,
    record_login_success,
)

# ─── Auto-Session Logout Configuration ─────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.urandom(24).hex()
app.config['SESSION_COOKIE_NAME'] = 'batchhost_session'

# SECURE CONFIG-DRIVEN CORS ALLOWED ORIGINS
def _get_cors_origins():
    try:
        import pymysql
        conn = pymysql.connect(
            host='localhost',
            user='root',
            password='wahid5104',
            database='central_multitenant',
            port=3306,
            cursorclass=pymysql.cursors.DictCursor
        )
        with conn.cursor() as cursor:
            cursor.execute("SELECT setting_value FROM settings WHERE setting_key = 'cors_allowed_origins';")
            row = cursor.fetchone()
            if row:
                return row['setting_value']
    except Exception:
        pass
    return "*"

socketio = SocketIO(app, cors_allowed_origins=_get_cors_origins(), async_mode='threading')
PRESENCE_TIMEOUT_SECONDS = 45
SESSION_TIMEOUT_SECONDS = 30 * 60
SESSION_WARNING_SECONDS = 25 * 60
ACTIVE_WEB_SESSIONS = {}
PENDING_LOGOUT = {} # user_id -> timestamp
PRESENCE_LOCK = threading.RLock()
DATA_LOCK = threading.RLock()
AGENT_OFFLINE_TIMEOUT_SECONDS = 30
execution_manager = ExecutionManager()
AGENT_COMMAND_QUEUES = {} # agent_id -> list of commands

HEARTBEAT_COMPLETION_GRACE_SECONDS = 0

VALID_SCRIPT_STATUSES = {"queued", "pending", "starting", "running", "completed", "failed", "terminated", "timeout", "unknown", "disabled", "force_killed", "crashed", "stalled"}
TERMINAL_SCRIPT_STATUSES = {"completed", "failed", "terminated", "timeout", "unknown", "force_killed", "crashed"}

SCRIPT_TRANSITIONS = {
    None: VALID_SCRIPT_STATUSES,
    "": VALID_SCRIPT_STATUSES,
    "pending": {"queued", "pending", "starting", "running", "disabled", "failed", "terminated"},
    "queued": {"starting", "running", "failed", "terminated", "disabled"},
    "starting": {"running", "failed", "crashed", "terminated", "disabled"},
    "running": {"running", "completed", "failed", "terminated", "timeout", "force_killed", "crashed", "stalled", "disabled", "unknown"},
    "stalled": {"running", "completed", "failed", "terminated", "timeout", "force_killed", "disabled"},
    "completed": {"disabled", "running", "starting", "queued"},
    "failed": {"disabled", "pending", "running", "starting", "queued"},
    "terminated": {"disabled", "pending", "running", "starting", "queued"},
    "force_killed": {"disabled", "pending", "running", "starting", "queued"},
    "crashed": {"disabled", "pending", "running", "starting", "queued"},
    "timeout": {"disabled", "pending", "running", "starting", "queued", "completed", "failed"},
    "unknown": {"disabled", "pending", "running", "starting", "queued", "completed", "failed"},
    "disabled": {"disabled", "pending", "running", "starting", "queued"},
}

# ─── Paths ─────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(BASE_DIR, "data")
LOG_DIR    = os.path.join(BASE_DIR, "logs")
BACKUP_DIR = os.path.join(BASE_DIR, "backup")

for d in [DATA_DIR, LOG_DIR, BACKUP_DIR]:
    os.makedirs(d, exist_ok=True)

AGENTS_FILE  = os.path.join(DATA_DIR, "agents.json")
SCRIPTS_FILE = os.path.join(DATA_DIR, "scripts.json")
ALERTS_FILE  = os.path.join(DATA_DIR, "alerts.json")
USERS_FILE   = os.path.join(DATA_DIR, "users.json")
ORGANIZATIONS_FILE = os.path.join(DATA_DIR, "organizations.json")
ADMIN_LOGS_FILE = os.path.join(DATA_DIR, "admin_logs.json")
BACKUP_STATE_FILE = os.path.join(DATA_DIR, "backup_state.json")
EXECUTIONS_FILE = os.path.join(DATA_DIR, "script_executions.json")
EXECUTION_EVENTS_FILE = os.path.join(DATA_DIR, "execution_events.json")

logging.basicConfig(
    filename=os.path.join(LOG_DIR, "server.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

@app.before_request
def log_request_info():
    g.start_time = time.time()
    if request.path.startswith('/images') or request.path.startswith('/static'):
        return
    logging.info(f"Incoming request: {request.method} {request.path} from {request.remote_addr}")
    if request.is_json and request.json:
        safe_data = {k: v for k, v in request.json.items() if 'password' not in k.lower()}
        logging.info(f"Request payload: {json.dumps(safe_data)}")

@app.after_request
def log_response_info(response):
    if request.path.startswith('/images') or request.path.startswith('/static'):
        return response
    duration = time.time() - getattr(g, 'start_time', time.time())
    logging.info(f"Completed request: {request.method} {request.path} - Status: {response.status_code} - Duration: {duration:.3f}s")
    return response

# ZERO-DEPENDENCY CSRF PROTECTION FOR SESSION-BASED BROWSER STATE-MUTATING CALLS
@app.before_request
def csrf_protect():
    if request.method in ["POST", "PUT", "PATCH", "DELETE"]:
        if request.path.startswith("/api/agent/") or request.path == "/api/auth/login":
            return
            
        if "user_id" in session:
            origin = request.headers.get("Origin")
            referer = request.headers.get("Referer")
            host = request.host
            
            if origin:
                parsed_origin = origin.split("//")[-1]
                if parsed_origin != host:
                    logging.warning(f"CSRF Blocked: Origin {origin} does not match Host {host}")
                    return jsonify({"error": "CSRF verification failed"}), 400
            elif referer:
                parsed_referer = referer.split("//")[-1].split("/")[0]
                if parsed_referer != host:
                    logging.warning(f"CSRF Blocked: Referer {referer} does not match Host {host}")
                    return jsonify({"error": "CSRF verification failed"}), 400
            else:
                logging.warning("CSRF Blocked: Missing Origin and Referer headers")
                return jsonify({"error": "CSRF verification failed"}), 400

@app.errorhandler(500)
def handle_internal_server_error(e):
    import traceback
    error_msg = f"INTERNAL SERVER ERROR: {str(e)}\n{traceback.format_exc()}"
    logging.error(error_msg)
    return jsonify({"error": "Internal Server Error", "message": str(e)}), 500

# ─── Data Helpers ───────────────────────────────────────────── 
def get_db_connection():
    import pymysql
    return pymysql.connect(
        host='localhost',
        user='root',
        password='List@123',
        database='central_multitenant',
        port=3306,
        cursorclass=pymysql.cursors.DictCursor
    )

def load_json(path, default=None):
    if default is None:
        default = []
        
    import pymysql
    from datetime import datetime

    def format_row(row):
        if isinstance(row, dict):
            new_row = {}
            for k, v in row.items():
                if isinstance(v, datetime):
                    new_row[k] = v.isoformat()
                else:
                    new_row[k] = format_row(v)
            return new_row
        elif isinstance(row, (list, tuple)):
            return [format_row(item) for item in row]
        return row

    try:
        filename = os.path.basename(path)
        conn = get_db_connection()
        with conn.cursor() as cursor:
            if filename == "users.json":
                cursor.execute("SELECT *, batchhost_role AS role FROM users;")
                return format_row(cursor.fetchall())
                
            elif filename == "organizations.json":
                cursor.execute("SELECT * FROM organizations;")
                return format_row(cursor.fetchall())
                
            elif filename == "agents.json":
                cursor.execute("SELECT * FROM batchhost_agents;")
                rows = cursor.fetchall()
                for r in rows:
                    if r.get('running_scripts'):
                        try:
                            r['running_scripts'] = json.loads(r['running_scripts'])
                        except Exception:
                            r['running_scripts'] = []
                    else:
                        r['running_scripts'] = []
                    # Convert MySQL TINYINT(1) to proper Python bool for JSON serialization
                    r['enabled'] = bool(r.get('enabled', 1))
                return format_row(rows)
                
            elif filename == "scripts.json":
                cursor.execute("SELECT * FROM scripts;")
                return format_row(cursor.fetchall())
                
            elif filename == "script_executions.json":
                cursor.execute("SELECT * FROM script_executions;")
                return format_row(cursor.fetchall())
                
            elif filename == "execution_events.json":
                cursor.execute("SELECT * FROM execution_events;")
                return format_row(cursor.fetchall())
                
            elif filename == "alerts.json":
                cursor.execute("SELECT * FROM batchhost_alerts;")
                return format_row(cursor.fetchall())
                
            elif filename == "admin_logs.json":
                cursor.execute("SELECT * FROM admin_logs;")
                return format_row(cursor.fetchall())
                
            elif filename == "settings.json":
                cursor.execute("SELECT setting_key, setting_value FROM settings;")
                rows = cursor.fetchall()
                settings = {}
                for r in rows:
                    val = r['setting_value']
                    try:
                        val = json.loads(val)
                    except Exception:
                        pass
                    settings[r['setting_key']] = val
                return settings
                
            elif filename == "backup_state.json":
                cursor.execute("SELECT setting_value FROM settings WHERE setting_key = 'backup_state';")
                row = cursor.fetchone()
                if row:
                    try:
                        return json.loads(row['setting_value'])
                    except Exception:
                        return {}
                return {}
    except Exception as e:
        logging.error(f"MySQL load failed for {path}: {e}")
        return default
    finally:
        if 'conn' in locals() and conn:
            conn.close()

    # Fallback to local files if not matching database mapped basenames
    with DATA_LOCK:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logging.error("DATA load failed path=%s error=%s", path, e)
    return default

def save_json(path, data):
    import pymysql
    from datetime import datetime

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
        except Exception:
            return None

    try:
        filename = os.path.basename(path)
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Disable foreign key checks for save operations to prevent constraint violations
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
            
            if filename == "users.json":
                for r in data:
                    cursor.execute("""
                        INSERT INTO users (id, username, email, password, batchhost_role, filebridge_role, organization_id, status, last_login, previous_login, total_logins, force_logout_at, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE username=%s, email=%s, password=%s, batchhost_role=%s, filebridge_role=%s, organization_id=%s, status=%s, last_login=%s, previous_login=%s, total_logins=%s, force_logout_at=%s, created_at=%s;
                    """, (
                        r['id'], r['username'], r['email'], r['password'], r.get('batchhost_role', r.get('role', 'viewer')), r.get('filebridge_role', 'viewer'), r.get('organization_id'), r.get('status', 'active'), parse_dt(r.get('last_login')), parse_dt(r.get('previous_login')), r.get('total_logins', 0), parse_dt(r.get('force_logout_at')), parse_dt(r.get('created_at')),
                        r['username'], r['email'], r['password'], r.get('batchhost_role', r.get('role', 'viewer')), r.get('filebridge_role', 'viewer'), r.get('organization_id'), r.get('status', 'active'), parse_dt(r.get('last_login')), parse_dt(r.get('previous_login')), r.get('total_logins', 0), parse_dt(r.get('force_logout_at')), parse_dt(r.get('created_at'))
                    ))
                    
            elif filename == "organizations.json":
                for r in data:
                    cursor.execute("""
                        INSERT INTO organizations (id, name, status, logo, is_default, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE name=%s, status=%s, logo=%s, is_default=%s, created_at=%s;
                    """, (
                        r['id'], r['name'], r.get('status', 'active'), r.get('logo'), bool(r.get('is_default')), parse_dt(r.get('created_at')),
                        r['name'], r.get('status', 'active'), r.get('logo'), bool(r.get('is_default')), parse_dt(r.get('created_at'))
                    ))
                    
            elif filename == "agents.json":
                for r in data:
                    cursor.execute("""
                        INSERT INTO batchhost_agents (id, hostname, os_type, status, token, cpu, memory, last_heartbeat, registered_at, organization_id, device_key, last_ip, running_scripts, enabled)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE hostname=%s, os_type=%s, status=%s, token=%s, cpu=%s, memory=%s, last_heartbeat=%s, registered_at=%s, organization_id=%s, device_key=%s, last_ip=%s, running_scripts=%s, enabled=%s;
                    """, (
                        r['id'], r.get('hostname'), r.get('os_type'), r.get('status'), r.get('token'), r.get('cpu', 0), r.get('memory', 0), parse_dt(r.get('last_heartbeat')), parse_dt(r.get('registered_at')), r.get('organization_id'), r.get('device_key'), r.get('last_ip'), json.dumps(r.get('running_scripts', [])), bool(r.get('enabled', True)),
                        r.get('hostname'), r.get('os_type'), r.get('status'), r.get('token'), r.get('cpu', 0), r.get('memory', 0), parse_dt(r.get('last_heartbeat')), parse_dt(r.get('registered_at')), r.get('organization_id'), r.get('device_key'), r.get('last_ip'), json.dumps(r.get('running_scripts', [])), bool(r.get('enabled', True))
                    ))
                    
            elif filename == "scripts.json":
                for r in data:
                    cursor.execute("""
                        INSERT INTO scripts (id, name, path, agent_id, organization_id, os_type, type, status, schedule, enabled, created_at, current_run_id, current_execution_id, pid, started_at, last_seen_running_at, status_updated_at, status_version, last_status_source, last_sequence_number, last_status_reason, exit_code, failed_at, completed_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE name=%s, path=%s, agent_id=%s, organization_id=%s, os_type=%s, type=%s, status=%s, schedule=%s, enabled=%s, created_at=%s, current_run_id=%s, current_execution_id=%s, pid=%s, started_at=%s, last_seen_running_at=%s, status_updated_at=%s, status_version=%s, last_status_source=%s, last_sequence_number=%s, last_status_reason=%s, exit_code=%s, failed_at=%s, completed_at=%s;
                    """, (
                        r['id'], r.get('name'), r.get('path'), r.get('agent_id'), r.get('organization_id'), r.get('os_type'), r.get('type'), r.get('status'), json.dumps(r.get('schedule')) if r.get('schedule') is not None else None, bool(r.get('enabled', True)), parse_dt(r.get('created_at')), r.get('current_run_id'), r.get('current_execution_id'), r.get('pid'), parse_dt(r.get('started_at')), parse_dt(r.get('last_seen_running_at')), parse_dt(r.get('status_updated_at')), r.get('status_version', 0), r.get('last_status_source'), r.get('last_sequence_number', 0), r.get('last_status_reason'), r.get('exit_code'), parse_dt(r.get('failed_at')), parse_dt(r.get('completed_at')),
                        r.get('name'), r.get('path'), r.get('agent_id'), r.get('organization_id'), r.get('os_type'), r.get('type'), r.get('status'), json.dumps(r.get('schedule')) if r.get('schedule') is not None else None, bool(r.get('enabled', True)), parse_dt(r.get('created_at')), r.get('current_run_id'), r.get('current_execution_id'), r.get('pid'), parse_dt(r.get('started_at')), parse_dt(r.get('last_seen_running_at')), parse_dt(r.get('status_updated_at')), r.get('status_version', 0), r.get('last_status_source'), r.get('last_sequence_number', 0), r.get('last_status_reason'), r.get('exit_code'), parse_dt(r.get('failed_at')), parse_dt(r.get('completed_at'))
                    ))
                    
            elif filename == "script_executions.json":
                for r in data:
                    cursor.execute("""
                        INSERT INTO script_executions (execution_id, script_id, script_name, script_path, agent_id, organization_id, pid, state, created_at, started_at, last_seen, last_sequence_number, runtime, exit_code, cpu, memory, updated_at, ended_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE script_id=%s, script_name=%s, script_path=%s, agent_id=%s, organization_id=%s, pid=%s, state=%s, created_at=%s, started_at=%s, last_seen=%s, last_sequence_number=%s, runtime=%s, exit_code=%s, cpu=%s, memory=%s, updated_at=%s, ended_at=%s;
                    """, (
                        r['execution_id'], r.get('script_id'), r.get('script_name'), r.get('script_path'), r.get('agent_id'), r.get('organization_id'), r.get('pid'), r.get('state'), parse_dt(r.get('created_at')), parse_dt(r.get('started_at')), parse_dt(r.get('last_seen')), r.get('last_sequence_number', 0), r.get('runtime', 0), r.get('exit_code'), r.get('cpu'), r.get('memory'), parse_dt(r.get('updated_at')), parse_dt(r.get('ended_at')),
                        r.get('script_id'), r.get('script_name'), r.get('script_path'), r.get('agent_id'), r.get('organization_id'), r.get('pid'), r.get('state'), parse_dt(r.get('created_at')), parse_dt(r.get('started_at')), parse_dt(r.get('last_seen')), r.get('last_sequence_number', 0), r.get('runtime', 0), r.get('exit_code'), r.get('cpu'), r.get('memory'), parse_dt(r.get('updated_at')), parse_dt(r.get('ended_at'))
                    ))
                    
            elif filename == "execution_events.json":
                for r in data:
                    cursor.execute("""
                        INSERT INTO execution_events (id, execution_id, agent_id, script_id, event_type, sequence_number, timestamp, accepted, reason, pid, exit_code, state_after)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE execution_id=%s, agent_id=%s, script_id=%s, event_type=%s, sequence_number=%s, timestamp=%s, accepted=%s, reason=%s, pid=%s, exit_code=%s, state_after=%s;
                    """, (
                        r['id'], r.get('execution_id'), r.get('agent_id'), r.get('script_id'), r.get('event_type'), r.get('sequence_number'), parse_dt(r.get('timestamp')), bool(r.get('accepted', True)), r.get('reason'), r.get('pid'), r.get('exit_code'), r.get('state_after'),
                        r.get('execution_id'), r.get('agent_id'), r.get('script_id'), r.get('event_type'), r.get('sequence_number'), parse_dt(r.get('timestamp')), bool(r.get('accepted', True)), r.get('reason'), r.get('pid'), r.get('exit_code'), r.get('state_after')
                    ))
                    
            elif filename == "alerts.json":
                for r in data:
                    cursor.execute("""
                        INSERT INTO batchhost_alerts (id, time, level, type, agent_id, organization_id, message, email_sent)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE time=%s, level=%s, type=%s, agent_id=%s, organization_id=%s, message=%s, email_sent=%s;
                    """, (
                        r['id'], parse_dt(r.get('time')), r.get('level'), r.get('type'), r.get('agent_id'), r.get('organization_id'), r.get('message'), bool(r.get('email_sent')),
                        parse_dt(r.get('time')), r.get('level'), r.get('type'), r.get('agent_id'), r.get('organization_id'), r.get('message'), bool(r.get('email_sent'))
                    ))
                    
            elif filename == "admin_logs.json":
                cursor.execute("TRUNCATE TABLE admin_logs;")
                for r in data:
                    cursor.execute("""
                        INSERT INTO admin_logs (timestamp, admin_username, action_type, module_name, affected_record, previous_value, new_value, ip_address, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        parse_dt(r.get('timestamp')), r.get('admin_username'), r.get('action_type'), r.get('module_name'), r.get('affected_record'), r.get('previous_value'), r.get('new_value'), r.get('ip_address'), r.get('status', 'success')
                    ))
                    
            elif filename == "settings.json":
                for k, v in data.items():
                    val_str = json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                    cursor.execute("""
                        INSERT INTO settings (setting_key, setting_value) VALUES (%s, %s)
                        ON DUPLICATE KEY UPDATE setting_value=%s;
                    """, (k, val_str, val_str))
                    
            elif filename == "backup_state.json":
                val_str = json.dumps(data)
                cursor.execute("""
                    INSERT INTO settings (setting_key, setting_value) VALUES ('backup_state', %s)
                    ON DUPLICATE KEY UPDATE setting_value=%s;
                """, (val_str, val_str))
                
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
            conn.commit()
            return
    except Exception as e:
        logging.error(f"MySQL save failed for {path}: {e}")
        try:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
        except Exception:
            pass
        raise e
    finally:
        if 'conn' in locals() and conn:
            conn.close()

    # Fallback to local files if not matching database mapped basenames
    with DATA_LOCK:
        directory = os.path.dirname(path) or "."
        fd, tmp_path = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

def normalize_path(path):
    if not isinstance(path, str):
        return ""
    return os.path.normpath(path).replace('\\', '/').lower().strip()

def _now_iso():
    return datetime.now().isoformat()

def _parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None

def _seconds_since(value):
    parsed = _parse_iso(value)
    if not parsed:
        return None
    return (datetime.now() - parsed).total_seconds()

def _script_identity(script):
    return f"{script.get('id', 'unknown')} agent={script.get('agent_id')} path={script.get('path')}"

def _set_status_metadata(script, new_status, source, reason=None):
    old_status = script.get("status")
    now = _now_iso()
    script["status"] = new_status
    script["status_updated_at"] = now
    script["last_status_source"] = source
    if reason:
        script["last_status_reason"] = reason
    script["status_version"] = int(script.get("status_version", 0) or 0) + 1


def _valid_transition(old_status, new_status, source):
    if new_status not in VALID_SCRIPT_STATUSES:
        return False, f"unknown target status '{new_status}'"
    
    # If same status, it's always allowed (idempotent)
    if old_status == new_status:
        return True, ""

    allowed = SCRIPT_TRANSITIONS.get(old_status, set())
    if new_status not in allowed:
        return False, f"invalid transition {old_status}->{new_status}"
    
    # Extra safety: Never downgrade a terminal state to an active one unless it's an explicit manual reset (pending)
    if old_status in TERMINAL_SCRIPT_STATUSES and new_status in {"running"} and source == "heartbeat":
        return False, f"heartbeat cannot downgrade terminal status {old_status} to {new_status}"
        
    return True, ""

def _can_reopen_terminal(script, source):
    if source == "script_status":
        return True, "explicit agent running report starts a new execution"
    if source == "heartbeat":
        return False, "heartbeat cannot reopen terminal status; agent must send explicit running for a new execution"
    return False, f"{source} cannot reopen terminal status"

def _new_run_id(script):
    return f"{script.get('id', 'script')}:{uuid.uuid4()}"

def apply_script_status(script, new_status, source, exit_code=None, reason=None, force=False):
    old_status = script.get("status")
    if new_status not in VALID_SCRIPT_STATUSES:
        logging.warning(
            "SCRIPT_STATUS rejected unknown status script=%s old=%s new=%s source=%s reason=%s",
            _script_identity(script), old_status, new_status, source, reason
        )
        return False
    if old_status == "completed" and new_status == "failed":
        logging.warning(
            "SCRIPT_STATUS immutable terminal block script=%s old=%s new=%s source=%s reason=%s",
            _script_identity(script), old_status, new_status, source, reason
        )
        return False

    if old_status in TERMINAL_SCRIPT_STATUSES and new_status == "running" and not force:
        ok, reopen_message = _can_reopen_terminal(script, source)
        if not ok:
            logging.warning(
                "SCRIPT_STATUS terminal reopen blocked script=%s old=%s new=%s source=%s reason=%s detail=%s",
                _script_identity(script), old_status, new_status, source, reason, reopen_message
            )
            return False
        logging.info(
            "SCRIPT_STATUS terminal reopened as new run script=%s old=%s source=%s detail=%s",
            _script_identity(script), old_status, source, reopen_message
        )

    ok, message = _valid_transition(old_status, new_status, source)
    if not ok and not force:
        logging.warning(
            "SCRIPT_STATUS invalid transition blocked script=%s old=%s new=%s source=%s reason=%s detail=%s",
            _script_identity(script), old_status, new_status, source, reason, message
        )
        return False

    if old_status == new_status:
        logging.info(
            "SCRIPT_STATUS idempotent update script=%s status=%s source=%s reason=%s version=%s",
            _script_identity(script), new_status, source, reason, script.get("status_version")
        )
    else:
        logging.info(
            "SCRIPT_STATUS transition script=%s %s->%s source=%s reason=%s pid=%s run_id=%s",
            _script_identity(script), old_status, new_status, source, reason, script.get("pid"), script.get("current_run_id")
        )

    if new_status == "running":
        mark_script_running(script, source=source, reason=reason)
    elif new_status == "completed":
        mark_script_completed(script, exit_code, source=source, reason=reason)
    elif new_status == "failed":
        mark_script_failed(script, exit_code, source=source, reason=reason)
    else:
        _set_status_metadata(script, new_status, source, reason)
    
    # Ensure current_run_id is preserved if it exists
    if not script.get("current_run_id") and new_status == "running":
        script["current_run_id"] = _new_run_id(script)
        
    return True

def _script_status_payload(script, agent_id=None, path=None):
    return {
        'script_id': script.get('id'),
        'agent_id': agent_id or script.get('agent_id'),
        'path': path or script.get('path'),
        'status': script.get('status'),
        'exit_code': script.get('exit_code'),
        'organization_id': script.get('organization_id'),
        'status_version': script.get('status_version'),
        'current_run_id': script.get('current_run_id'),
    }

def _execution_event_payload(execution_payload):
    return {
        "execution_id": execution_payload.get("execution_id"),
        "script_id": execution_payload.get("script_id"),
        "script_name": execution_payload.get("script_name"),
        "script_path": execution_payload.get("script_path"),
        "agent_id": execution_payload.get("agent_id"),
        "organization_id": execution_payload.get("organization_id"),
        "pid": execution_payload.get("pid"),
        "status": execution_payload.get("status"),
        "state": execution_payload.get("state"),
        "sequence_number": execution_payload.get("sequence_number"),
        "started_at": execution_payload.get("started_at"),
        "last_seen": execution_payload.get("last_seen"),
        "runtime": execution_payload.get("runtime"),
        "exit_code": execution_payload.get("exit_code"),
        "cpu": execution_payload.get("cpu"),
        "memory": execution_payload.get("memory"),
        "updated_at": execution_payload.get("updated_at"),
    }

def _broadcast_execution_update(payload):
    if not payload:
        return
    execution_payload = _execution_event_payload(payload)
    emit_socket_event("execution_update", execution_payload)
    # Keep older dashboard pages alive while they migrate to execution_update.
    emit_socket_event("script_status", {
        "script_id": payload.get("script_id"),
        "agent_id": payload.get("agent_id"),
        "path": payload.get("script_path"),
        "status": payload.get("status"),
        "exit_code": payload.get("exit_code"),
        "organization_id": payload.get("organization_id"),
        "status_version": payload.get("script_status_version"),
        "current_run_id": payload.get("execution_id"),
        "execution_id": payload.get("execution_id"),
        "sequence_number": payload.get("sequence_number"),
    })

def _process_agent_execution_event(agent, raw_event):
    """Persist one agent lifecycle event and return the manager result.

    This is the only backend path that is allowed to change execution final
    state from agent input. Heartbeats intentionally bypass it unless they
    include explicit execution event objects.
    """
    scripts = load_json(SCRIPTS_FILE)
    executions = load_json(EXECUTIONS_FILE)
    event_store = load_json(EXECUTION_EVENTS_FILE)
    result = execution_manager.process_event(scripts, executions, event_store, agent, raw_event)
    if result.get("accepted"):
        save_json(SCRIPTS_FILE, scripts)
        save_json(EXECUTIONS_FILE, executions)
        save_json(EXECUTION_EVENTS_FILE, event_store)
    elif event_store:
        save_json(EXECUTION_EVENTS_FILE, event_store)
    return result

def emit_socket_event(event, payload):
    logging.info("WEBSOCKET emit event=%s payload=%s", event, payload)
    try:
        socketio.emit(event, payload)
    except Exception as e:
        logging.error("WEBSOCKET emit failed event=%s payload=%s error=%s", event, payload, e)

def collapse_duplicate_scripts(scripts, agent_id, normalized_path):
    matches = [
        s for s in scripts
        if s.get("agent_id") == agent_id and normalize_path(s.get("path")) == normalized_path
    ]
    if len(matches) <= 1:
        return scripts, matches[0] if matches else None, []

    matches.sort(key=lambda s: (
        s.get("status") not in TERMINAL_SCRIPT_STATUSES,
        s.get("status_updated_at") or s.get("created_at") or ""
    ), reverse=True)
    primary = matches[0]
    duplicate_ids = [s.get("id") for s in matches[1:]]
    logging.warning(
        "SCRIPT_STATUS duplicate records collapsed primary=%s duplicates=%s agent=%s path=%s",
        primary.get("id"), duplicate_ids, agent_id, primary.get("path")
    )
    for dup in matches[1:]:
        for key in [
            "completed_at", "failed_at", "started_at", "last_seen_running_at",
            "missing_since", "exit_code", "status_updated_at", "last_status_source",
            "last_status_reason", "status_version", "current_run_id"
        ]:
            if key not in primary and key in dup:
                primary[key] = dup[key]

    duplicate_id_set = set(duplicate_ids)
    return [s for s in scripts if s.get("id") not in duplicate_id_set], primary, duplicate_ids

def mark_script_running(script, source="system", reason=None):
    if script.get("status") != "running":
        script["current_run_id"] = _new_run_id(script)
    now = _now_iso()
    script["started_at"] = now
    script["last_seen_running_at"] = now
    script.pop("missing_since", None)
    script.pop("completed_at", None)
    script.pop("failed_at", None)

    script.pop("exit_code", None)
    _set_status_metadata(script, "running", source, reason)

def mark_script_completed(script, exit_code=0, source="system", reason=None):
    script["completed_at"] = _now_iso()
    script["exit_code"] = 0 if exit_code is None else exit_code
    script.pop("failed_at", None)

    script.pop("missing_since", None)
    _set_status_metadata(script, "completed", source, reason)

def mark_script_failed(script, exit_code=None, source="system", reason=None):
    script["failed_at"] = _now_iso()
    script["exit_code"] = exit_code
    script.pop("completed_at", None)

    script.pop("missing_since", None)
    _set_status_metadata(script, "failed", source, reason)



def append_log(agent_id, message):
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(LOG_DIR, f"{agent_id}_{date_str}.log")
    with open(log_file, "a") as f:
        f.write(f"[{datetime.now().isoformat()}] {message}\n")

def log_admin_action(admin_username, action_type, module_name, affected_record, previous_value=None, new_value=None, ip_address=None, status="success"):
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "admin_username": admin_username,
        "action_type": action_type,
        "module_name": module_name,
        "affected_record": affected_record,
        "previous_value": previous_value,
        "new_value": new_value,
        "ip_address": ip_address,
        "status": status
    }
    logs = load_json(ADMIN_LOGS_FILE)
    logs.append(log_entry)
    save_json(ADMIN_LOGS_FILE, logs)

def default_org_id():
    organizations = load_json(ORGANIZATIONS_FILE)
    # Check if there is an organization named "Global Organization" (case-insensitive)
    global_org = next((o for o in organizations if o.get("name", "").strip().lower() == "global organization"), None)
    if global_org:
        if not global_org.get("is_default"):
            # Ensure it is marked default
            for o in organizations:
                o["is_default"] = (o["id"] == global_org["id"])
            save_json(ORGANIZATIONS_FILE, organizations)
        return global_org["id"]

    # Fallback to is_default organization, rename it to "Global Organization"
    default_org = next((o for o in organizations if o.get("is_default")), None)
    if default_org:
        default_org["name"] = "Global Organization"
        save_json(ORGANIZATIONS_FILE, organizations)
        return default_org["id"]

    # Fallback to the first organization, rename it to "Global Organization" and set is_default=True
    if organizations:
        organizations[0]["name"] = "Global Organization"
        organizations[0]["is_default"] = True
        save_json(ORGANIZATIONS_FILE, organizations)
        return organizations[0]["id"]

    # If no organizations exist, create "Global Organization"
    org_id = str(uuid.uuid4())
    save_json(ORGANIZATIONS_FILE, [{
        "id": org_id,
        "name": "Global Organization",
        "status": "active",
        "is_default": True,
        "created_at": datetime.now().isoformat()
    }])
    return org_id

def is_admin(user=None):
    user = user or _current_user()
    return user.get("role") == "super_admin"

def current_org_id(user=None):
    user = user or _current_user()
    return user.get("organization_id")

def organization_active(org_id):
    if not org_id:
        return True
    organizations = load_json(ORGANIZATIONS_FILE)
    org = next((o for o in organizations if o.get("id") == org_id), None)
    return bool(org and org.get("status", "active") == "active")

def filter_by_org(records, user=None):
    user = user or _current_user()
    if is_admin(user):
        return records
    org_id = current_org_id(user)
    return [r for r in records if r.get("organization_id") == org_id]

def filtered_agents(user=None):
    return filter_by_org(load_json(AGENTS_FILE), user)

def filtered_scripts(user=None):
    user = user or _current_user()
    scripts = load_json(SCRIPTS_FILE)
    if is_admin(user):
        return scripts
    org_id = current_org_id(user)
    agents = load_json(AGENTS_FILE)
    agent_org = {a.get("id"): a.get("organization_id") for a in agents}
    return [s for s in scripts if s.get("organization_id") == org_id or agent_org.get(s.get("agent_id")) == org_id]

def filtered_executions(user=None):
    user = user or _current_user()
    executions = load_json(EXECUTIONS_FILE)
    if is_admin(user):
        return executions
    org_id = current_org_id(user)
    agents = load_json(AGENTS_FILE)
    agent_org = {a.get("id"): a.get("organization_id") for a in agents}
    return [
        e for e in executions
        if e.get("organization_id") == org_id or agent_org.get(e.get("agent_id")) == org_id
    ]

def filtered_alerts(user=None):
    user = user or _current_user()
    alerts = load_json(ALERTS_FILE)
    if is_admin(user):
        return alerts
    org_id = current_org_id(user)
    agents = load_json(AGENTS_FILE)
    agent_org = {a.get("id"): a.get("organization_id") for a in agents}
    return [a for a in alerts if a.get("organization_id") == org_id or agent_org.get(a.get("agent_id")) == org_id]

def ensure_record_access(record):
    user = _current_user()
    if is_admin(user):
        return True
    return bool(record and record.get("organization_id") == current_org_id(user))

def org_name_map():
    return {o.get("id"): o.get("name", "") for o in load_json(ORGANIZATIONS_FILE)}

def assign_agent_to_organization(agent_id, org_id, agents=None, scripts=None, alerts=None):
    agents = agents if agents is not None else load_json(AGENTS_FILE)
    agent = next((a for a in agents if a.get("id") == agent_id), None)
    if not agent:
        return False
    agent["organization_id"] = org_id
    scripts = scripts if scripts is not None else load_json(SCRIPTS_FILE)
    for script in scripts:
        if script.get("agent_id") == agent_id:
            script["organization_id"] = org_id
    alerts = alerts if alerts is not None else load_json(ALERTS_FILE)
    for alert in alerts:
        if alert.get("agent_id") == agent_id:
            alert["organization_id"] = org_id
    return True

# ─── Init default data ─────────────────────────────────────────────
def init_data():
    logging.info("Initializing system data...")
    
    # Initialize secure agent registration secret in settings if not present
    settings_path = os.path.join(DATA_DIR, "settings.json")
    settings = load_json(settings_path, {})
    if "agent_registration_secret" not in settings:
        settings["agent_registration_secret"] = os.urandom(16).hex()
        save_json(settings_path, settings)
        logging.info(f"Generated new secure agent_registration_secret: {settings['agent_registration_secret']}")

    if not os.path.exists(ORGANIZATIONS_FILE):
        save_json(ORGANIZATIONS_FILE, [{
            "id": str(uuid.uuid4()),
            "name": "Global Organization",
            "status": "active",
            "is_default": True,
            "created_at": datetime.now().isoformat()
        }])
    org_id = default_org_id()
    if not os.path.exists(USERS_FILE):
        save_json(USERS_FILE, [])
    
    users = load_json(USERS_FILE)
    if not any(u.get("email") == "admin" for u in users):
        admin_pw = hash_pw("admin@123")
        users.append({
            "id": str(uuid.uuid4()),
            "username": "admin",
            "password": admin_pw,
            "role": "super_admin",
            "organization_id": org_id,
            "email": "admin",
            "status": "active",
            "last_login": None,
            "previous_login": None,
            "created_at": datetime.now().isoformat()
        })
        save_json(USERS_FILE, users)
    for f, d in [(AGENTS_FILE, []), (SCRIPTS_FILE, []), (ALERTS_FILE, [])]:
        if not os.path.exists(f):
            save_json(f, d)

    users = load_json(USERS_FILE)
    changed = False
    for user in users:
        if user.get("role") == "super_admin":
            if user.get("organization_id") != org_id:
                user["organization_id"] = org_id
                changed = True
        elif not user.get("organization_id"):
            user["organization_id"] = org_id
            changed = True
    if changed:
        save_json(USERS_FILE, users)

    agents = load_json(AGENTS_FILE)
    changed = False
    for agent in agents:
        if not agent.get("organization_id"):
            agent["organization_id"] = org_id
            changed = True
    if changed:
        save_json(AGENTS_FILE, agents)

    scripts = load_json(SCRIPTS_FILE)
    agents_by_id = {a.get("id"): a for a in agents}
    changed = False
    unique_keys = set()
    duplicate_ids = set()
    for script in scripts:
        dedupe_key = (script.get("agent_id"), normalize_path(script.get("path")))
        if dedupe_key in unique_keys:
            duplicate_ids.add(script.get("id"))
            logging.warning("SCRIPT_STATUS startup duplicate queued for cleanup script=%s", _script_identity(script))
            changed = True
            continue
        unique_keys.add(dedupe_key)
        if not script.get("organization_id"):
            script["organization_id"] = agents_by_id.get(script.get("agent_id"), {}).get("organization_id", org_id)
            changed = True
        status = script.get("status")
        if status not in VALID_SCRIPT_STATUSES:
            logging.warning("SCRIPT_STATUS startup repair unknown status script=%s status=%s", _script_identity(script), status)
            script["status"] = "pending"
            script["status_updated_at"] = _now_iso()
            script["last_status_source"] = "startup_repair"
            changed = True
        elif status == "running" and script.get("completed_at") and not script.get("failed_at"):
            logging.warning("SCRIPT_STATUS startup repair running+completed metadata script=%s", _script_identity(script))
            original_completed_at = script.get("completed_at")
            apply_script_status(script, "completed", "startup_repair", script.get("exit_code", 0), "running record had completed_at", force=True)
            script["completed_at"] = original_completed_at
            changed = True
        elif status == "failed" and script.get("completed_at") and not script.get("failed_at"):
            logging.warning("SCRIPT_STATUS startup repair failed+completed metadata script=%s", _script_identity(script))
            original_completed_at = script.get("completed_at")
            apply_script_status(script, "completed", "startup_repair", script.get("exit_code", 0), "failed record had completed_at", force=True)
            script["completed_at"] = original_completed_at
            changed = True
        elif status == "completed" and script.get("failed_at"):
            logging.warning("SCRIPT_STATUS startup repair completed+failed metadata script=%s", _script_identity(script))
            script.pop("failed_at", None)
            script["status_updated_at"] = _now_iso()
            script["last_status_source"] = "startup_repair"
            changed = True
    if changed:
        if duplicate_ids:
            scripts = [s for s in scripts if s.get("id") not in duplicate_ids]
        save_json(SCRIPTS_FILE, scripts)

    alerts = load_json(ALERTS_FILE)
    changed = False
    for alert in alerts:
        if not alert.get("organization_id"):
            alert["organization_id"] = agents_by_id.get(alert.get("agent_id"), {}).get("organization_id", org_id)
            changed = True
    if changed:
        save_json(ALERTS_FILE, alerts)

# ─── Socket.IO Connection ─────────────────────────────────────────────
@socketio.on('connect')
def handle_connect():
    user_id = session.get('user_id')
    logging.info(f"WebSocket connected: {request.sid} (User: {user_id})")
    if user_id:
        join_room(f"user_{user_id}")

@socketio.on('disconnect')
def handle_disconnect():
    logging.info(f"WebSocket disconnected: {request.sid}")

# ─── Auth Helpers ────────────────────────────────────────────────────
def hash_pw(pw, salt=None):
    if salt is None:
        salt = os.urandom(16)
    else:
        try:
            salt = bytes.fromhex(salt)
        except ValueError:
            salt = salt.encode('utf-8')[:16].zfill(16)
    hash_bytes = hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), salt, 100000)
    return f"pbkdf2_sha256$100000${salt.hex()}${hash_bytes.hex()}"

def verify_pw(stored_pw_hash, pw_to_test):
    if stored_pw_hash.startswith("pbkdf2_sha256$"):
        try:
            parts = stored_pw_hash.split("$")
            iterations = int(parts[1])
            salt = bytes.fromhex(parts[2])
            expected_hash = parts[3]
            test_hash = hashlib.pbkdf2_hmac('sha256', pw_to_test.encode('utf-8'), salt, iterations)
            return test_hash.hex() == expected_hash
        except Exception:
            return False
    else:
        legacy_hash = hashlib.sha256(pw_to_test.encode()).hexdigest()
        return legacy_hash == stored_pw_hash

init_data()


def _cleanup_presence(now=None):
    now = now or time.time()
    expired_users = []
    with PRESENCE_LOCK:
        for user_id, sessions in list(ACTIVE_WEB_SESSIONS.items()):
            expired_presence_ids = [
                presence_id for presence_id, last_seen in sessions.items()
                if now - last_seen > PRESENCE_TIMEOUT_SECONDS
            ]
            for presence_id in expired_presence_ids:
                sessions.pop(presence_id, None)
            
            if not sessions:
                expired_users.append(user_id)
                ACTIVE_WEB_SESSIONS.pop(user_id, None)
    return expired_users

def _presence_id():
    if "presence_id" not in session:
        session["presence_id"] = str(uuid.uuid4())
    return session["presence_id"]

def mark_web_presence(user_id=None):
    user_id = user_id or session.get("user_id")
    if not user_id:
        return
    now = time.time()
    with PRESENCE_LOCK:
        _cleanup_presence(now)
        ACTIVE_WEB_SESSIONS.setdefault(user_id, {})[_presence_id()] = now
        # If user re-appears, they are no longer pending logout
        PENDING_LOGOUT.pop(user_id, None)

def clear_web_presence(user_id=None, presence_id=None):
    user_id = user_id or session.get("user_id")
    presence_id = presence_id or session.get("presence_id")
    if not user_id or not presence_id:
        return
    with PRESENCE_LOCK:
        sessions = ACTIVE_WEB_SESSIONS.get(user_id)
        if sessions:
            sessions.pop(presence_id, None)
            if not sessions:
                ACTIVE_WEB_SESSIONS.pop(user_id, None)

def user_is_accessing_web(user_id):
    with PRESENCE_LOCK:
        _cleanup_presence()
        return bool(ACTIVE_WEB_SESSIONS.get(user_id))

def _session_age_seconds(now=None):
    login_at = session.get("login_at")
    if not login_at:
        return None
    try:
        return (now or time.time()) - float(login_at)
    except (TypeError, ValueError):
        return None

def _session_expired(now=None):
    age = _session_age_seconds(now)
    return age is None or age >= SESSION_TIMEOUT_SECONDS

def _clear_expired_session(user_id=None):
    clear_web_presence(user_id or session.get("user_id"))
    session.clear()

@app.context_processor
def inject_session_timeout_config():
    age = _session_age_seconds()
    if age is None:
        remaining = SESSION_TIMEOUT_SECONDS
        elapsed = 0
    else:
        elapsed = max(0, int(age))
        remaining = max(0, SESSION_TIMEOUT_SECONDS - elapsed)
    return {
        "session_timeout_seconds": SESSION_TIMEOUT_SECONDS,
        "session_warning_seconds": SESSION_WARNING_SECONDS,
        "session_remaining_seconds": remaining,
        "session_elapsed_seconds": elapsed,
    }

@app.context_processor
def inject_org_branding():
    user = _current_user()
    if user:
        org_id = user.get("organization_id")
        if org_id:
            orgs = load_json(ORGANIZATIONS_FILE)
            org = next((o for o in orgs if o.get("id") == org_id), None)
            if org:
                return {"global_org_logo": org.get("logo"), "global_org_name": org.get("name")}
    return {"global_org_logo": None, "global_org_name": None}

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            logging.warning(f"Unauthorized access attempt to {request.path} from {request.remote_addr}")
            if request.is_json:
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("login_page"))
        if _session_expired():
            user_id = session.get("user_id")
            _clear_expired_session(user_id)
            logging.info(f"Session expired for user: {user_id}")
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"error": "Session expired"}), 401
            return redirect(url_for("login_page"))
        user = _current_user()
        if not user:
            session.clear()
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("login_page"))
        if user.get("status") != "active":
            clear_web_presence(user.get("id"))
            session.clear()
            logging.warning(f"Inactive account access attempt to {request.path} from {request.remote_addr}")
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"error": "Account inactive"}), 403
            return redirect(url_for("login_page"))
        if user.get("role") != "super_admin" and not organization_active(user.get("organization_id")):
            session.clear()
            logging.warning(f"Disabled organization access attempt to {request.path} from {request.remote_addr}")
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"error": "Organization disabled"}), 403
            return redirect(url_for("login_page"))
            
        # Check if session was invalidated (e.g. by website closure logout)
        force_logout_at = user.get("force_logout_at")
        login_at = session.get("login_at")
        if force_logout_at and login_at:
            try:
                if float(login_at) < datetime.fromisoformat(force_logout_at).timestamp():
                    session.clear()
                    logging.info(f"Session invalidated by auto-logout for user: {user.get('id')}")
                    if request.path.startswith("/api/") or request.is_json:
                        return jsonify({"error": "Session invalidated"}), 401
                    return redirect(url_for("login_page"))
            except Exception:
                pass
                
        mark_web_presence(user.get("id"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            logging.warning(f"Unauthorized access attempt to {request.path} from {request.remote_addr}")
            return jsonify({"error": "Unauthorized"}), 401
        if _session_expired():
            user_id = session.get("user_id")
            _clear_expired_session(user_id)
            logging.info(f"Session expired for admin user: {user_id}")
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"error": "Session expired"}), 401
            return redirect(url_for("login_page"))
        users = load_json(USERS_FILE)
        user = next((u for u in users if u["id"] == session["user_id"]), None)
        if user and user.get("status") != "active":
            clear_web_presence(user.get("id"))
            session.clear()
            logging.warning(f"Inactive admin account access attempt to {request.path} from {request.remote_addr}")
            return jsonify({"error": "Account inactive"}), 403
        if not user or user.get("role") != "super_admin":
            logging.warning(f"Forbidden access attempt to {request.path} by user {session.get('user_id')} from {request.remote_addr}")
            return jsonify({"error": "Forbidden"}), 403
            
        # Check if session was invalidated
        force_logout_at = user.get("force_logout_at")
        login_at = session.get("login_at")
        if force_logout_at and login_at:
            try:
                if float(login_at) < datetime.fromisoformat(force_logout_at).timestamp():
                    session.clear()
                    logging.info(f"Admin session invalidated by auto-logout for user: {user.get('id')}")
                    if request.path.startswith("/api/") or request.is_json:
                        return jsonify({"error": "Session invalidated"}), 401
                    return redirect(url_for("login_page"))
            except Exception:
                pass
                
        mark_web_presence(user.get("id"))
        return f(*args, **kwargs)
    return decorated

def admin_or_org_admin_required(f):
    """Allow access to super_admin AND organization_admin roles."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            logging.warning(f"Unauthorized access attempt to {request.path} from {request.remote_addr}")
            if request.is_json:
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("login_page"))
        if _session_expired():
            user_id = session.get("user_id")
            _clear_expired_session(user_id)
            logging.info(f"Session expired for user: {user_id}")
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"error": "Session expired"}), 401
            return redirect(url_for("login_page"))
        user = _current_user()
        if not user:
            session.clear()
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("login_page"))
        if user.get("status") != "active":
            clear_web_presence(user.get("id"))
            session.clear()
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"error": "Account inactive"}), 403
            return redirect(url_for("login_page"))
        if user.get("role") not in ("super_admin", "organization_admin"):
            logging.warning(
                f"Forbidden: {request.path} role={user.get('role')} ip={request.remote_addr}"
            )
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"error": "Forbidden"}), 403
            return redirect(url_for("dashboard_page"))
        force_logout_at = user.get("force_logout_at")
        login_at = session.get("login_at")
        if force_logout_at and login_at:
            try:
                if float(login_at) < datetime.fromisoformat(force_logout_at).timestamp():
                    session.clear()
                    if request.path.startswith("/api/") or request.is_json:
                        return jsonify({"error": "Session invalidated"}), 401
                    return redirect(url_for("login_page"))
            except Exception:
                pass
        mark_web_presence(user.get("id"))
        return f(*args, **kwargs)
    return decorated

def agent_token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("X-Agent-Token") or request.json.get("token", "") if request.is_json else ""
        if not token:
            logging.warning(f"Missing agent token from {request.remote_addr}")
            return jsonify({"error": "Missing agent token"}), 401
        agents = load_json(AGENTS_FILE)
        agent = next((a for a in agents if a.get("token") == token), None)
        if not agent:
            logging.warning(f"Invalid agent token from {request.remote_addr}")
            return jsonify({"error": "Invalid agent token"}), 403
        request.agent = agent
        return f(*args, **kwargs)
    return decorated

# ─── Scheduler Helpers ─────────────────────────────────────────────
def parse_dt(value):
    try:
        if value:
            return datetime.fromisoformat(value)
    except:
        pass
    return None


def schedule_to_modern(schedule):
    """
    Convert old schedule:
    {value:30, unit:'minutes'}

    to new structure
    """
    if not schedule:
        return None

    if "type" in schedule:
        return schedule

    if "value" in schedule and "unit" in schedule:
        return {
            "type": schedule["unit"],
            "interval": int(schedule["value"]),
            "run_once": False,
            "next_run": None
        }

    return schedule


def auto_schedule_by_name(name):
    n = name.lower()

    if "backup" in n:
        return {
            "type": "daily",
            "time": "00:00"
        }

    if "monitor" in n:
        return {
            "type": "minutes",
            "interval": 15
        }

    if "cleanup" in n:
        return {
            "type": "weekly",
            "weekday": "sunday",
            "time": "01:00"
        }

    if "report" in n:
        return {
            "type": "daily",
            "time": "08:00"
        }

    return {
        "type": "hours",
        "interval": 1
    }


def compute_next_run(schedule):
    if not schedule:
        return None

    schedule = schedule_to_modern(schedule)
    now = datetime.now()

    stype = schedule.get("type")

    try:
        if stype == "minutes":
            mins = int(schedule.get("interval", 1))
            return (now + timedelta(minutes=mins)).isoformat()

        elif stype == "hours":
            hrs = int(schedule.get("interval", 1))
            return (now + timedelta(hours=hrs)).isoformat()

        elif stype == "daily":
            t = schedule.get("time", "00:00")
            hh, mm = map(int, t.split(":"))
            nxt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if nxt <= now:
                nxt += timedelta(days=1)
            return nxt.isoformat()

        elif stype == "repeat_days":
            d = int(schedule.get("interval", 1))
            return (now + timedelta(days=d)).isoformat()

        elif stype == "date_range":
            start = parse_dt(schedule.get("start"))
            end = parse_dt(schedule.get("end"))
            if start and now <= start:
                return start.isoformat()
            if end and now > end:
                return None
            return now.isoformat()

        elif stype == "auto":
            return (now + timedelta(minutes=15)).isoformat()

        else:
            return (now + timedelta(hours=1)).isoformat()

    except:
        return None


def is_overlap(existing_scripts, agent_id, path):
    normalized = normalize_path(path)

    for s in existing_scripts:
        if s.get("agent_id") == agent_id and normalize_path(s.get("path")) == normalized:
            if s.get("status") == "running":
                return True

    return False

# ─── Alert Helpers ─────────────────────────────────────────────
def create_alert(level, alert_type, agent_id, message, send_email=True):
    alerts = load_json(ALERTS_FILE)
    agent = next((a for a in load_json(AGENTS_FILE) if a.get("id") == agent_id), {})
    alert = {
        "id": str(uuid.uuid4()),
        "time": datetime.now().isoformat(),
        "level": level,
        "type": alert_type,
        "agent_id": agent_id,
        "organization_id": agent.get("organization_id") or default_org_id(),
        "message": message,
        "email_sent": False
    }
    alerts.append(alert)
    save_json(ALERTS_FILE, alerts)
    logging.info(f"Alert created: [{level}] {alert_type} for agent {agent_id} - {message}")

    if send_email:
        threading.Thread(target=send_alert_email, args=(alert,), daemon=True).start()

    return alert

def send_alert_email(alert):
    try:
        settings = load_json(os.path.join(DATA_DIR, "settings.json"), {})
        email_cfg = settings.get("email", {})
        if not email_cfg.get("enabled"):
            return

        smtp_host = email_cfg.get("smtp_host", "")
        smtp_port = int(email_cfg.get("smtp_port", 587))
        smtp_user = email_cfg.get("smtp_user", "")
        smtp_pass = email_cfg.get("smtp_pass", "")
        recipients = list(email_cfg.get("recipients", []))

        agent_id = alert.get("agent_id")
        agent_email = settings.get("agent_alerts", {}).get(agent_id, "")
        if isinstance(agent_email, str):
            agent_email = agent_email.strip()
            
        if agent_email and agent_email not in recipients:
            recipients.append(agent_email)

        if not smtp_host or not recipients:
            return

        msg = MIMEMultipart()
        msg["From"] = smtp_user
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = f"[BatchMon Alert] {alert['type']} - {alert['level']}"

        body = f"""
BatchMon Alert Notification
============================
Time    : {alert['time']}
Level   : {alert['level']}
Type    : {alert['type']}
Agent   : {alert['agent_id']}
Message : {alert['message']}
"""
        msg.attach(MIMEText(body, "plain"))

        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, recipients, msg.as_string())
        server.quit()
        logging.info(f"Alert email sent to {recipients} for alert {alert['id']}")

        alerts = load_json(ALERTS_FILE)
        for a in alerts:
            if a["id"] == alert["id"]:
                a["email_sent"] = True
        save_json(ALERTS_FILE, alerts)

    except Exception as e:
        logging.error(f"Email send failed: {e}")

# ─── Script Execution Status Alert Helper ──────────────────────────
def _create_execution_status_alert(agent, execution, state=None):
    """Create an alert and log entry for every script execution status change.

    Called from both ``agent_script_event`` and ``agent_script_status`` when
    the execution manager has accepted a state transition.  Covers RUNNING,
    COMPLETED, FAILED, TERMINATED and TIMEOUT.
    """
    if not execution:
        return
    state = state or execution.get("state", "")
    agent_id = agent.get("id", "")
    hostname = agent.get("hostname", agent_id)
    script_path = execution.get("script_path", execution.get("script_name", "unknown"))
    exit_code = execution.get("exit_code")
    runtime = execution.get("runtime", 0)

    # Map execution state -> (alert_level, alert_type, message)
    STATUS_ALERT_MAP = {
        "RUNNING": (
            "INFO", "SCRIPT_STARTED",
            f"Script '{script_path}' STARTED on {hostname}"
        ),
        "COMPLETED": (
            "INFO", "SCRIPT_COMPLETED",
            f"Script '{script_path}' COMPLETED on {hostname} (exit code: {exit_code}, runtime: {runtime}s)"
        ),
        "FAILED": (
            "ERROR", "SCRIPT_FAILED",
            f"Script '{script_path}' FAILED on {hostname} (exit code: {exit_code})"
        ),
        "TERMINATED": (
            "WARNING", "SCRIPT_TERMINATED",
            f"Script '{script_path}' TERMINATED on {hostname}"
        ),
        "TIMEOUT": (
            "WARNING", "SCRIPT_TIMEOUT",
            f"Script '{script_path}' TIMED OUT on {hostname} (last seen {runtime}s ago)"
        ),
    }

    entry = STATUS_ALERT_MAP.get(state)
    if not entry:
        return
    level, alert_type, message = entry

    # Write to agent log file
    append_log(agent_id, f"[{level}] {alert_type}: {message}")

    # Create the alert (which also sends email if configured)
    create_alert(level, alert_type, agent_id, message)

# ─── Heartbeat Monitor ─────────────────────────────────────────────
def heartbeat_monitor():
    while True:
        time.sleep(HEARTBEAT_INTERVAL_SECONDS)
        try:
            alerts_to_create = []
            broadcasts = []
            execution_broadcasts = []
            with DATA_LOCK:
                agents = load_json(AGENTS_FILE)
                scripts = load_json(SCRIPTS_FILE)
                executions = load_json(EXECUTIONS_FILE)
                event_store = load_json(EXECUTION_EVENTS_FILE)
                changed_agents = False
                for agent in agents:
                    date_str = datetime.now().strftime("%Y-%m-%d")
                    log_file = os.path.join(LOG_DIR, f"{agent['id']}_{date_str}.log")
                    if not os.path.exists(log_file):
                        try:
                            open(log_file, "a").close()
                        except Exception:
                            pass
                            
                    last_hb = agent.get("last_heartbeat")
                    if last_hb:
                        last_dt = datetime.fromisoformat(last_hb)
                        diff = (datetime.now() - last_dt).total_seconds()
                        if diff > AGENT_OFFLINE_TIMEOUT_SECONDS and agent.get("status") != "offline":
                            agent["status"] = "offline"
                            changed_agents = True
                            alerts_to_create.append((
                                "CRITICAL", "AGENT_OFFLINE", agent["id"],
                                f"Agent {agent['hostname']} has gone offline (no heartbeat for {int(diff)}s)"
                            ))

                            logging.warning(f"Agent {agent['id']} marked offline")
                            broadcasts.append({
                                '_event': 'agent_status',
                                'agent_id': agent['id'],
                                'status': 'offline',
                                'hostname': agent['hostname'],
                                'organization_id': agent.get('organization_id')
                            })
                agent_status_by_id = {a.get("id"): a.get("status") for a in agents}
                execution_broadcasts = execution_manager.timeout_active_executions(
                    scripts, executions, event_store, agent_status_by_id
                )
                
                # Enforce schedule limits (to_date and max runtime from interval)
                now_dt = datetime.now()
                for execution in executions:
                    if execution.get("state") in {"RUNNING", "STARTING"}:
                        script = next((s for s in scripts if s.get("id") == execution.get("script_id")), None)
                        if script and script.get("schedule") and isinstance(script.get("schedule"), dict):
                            schedule = script["schedule"]
                            should_kill = False
                            reason = ""
                            
                            to_date_str = schedule.get("to_date")
                            if to_date_str:
                                try:
                                    to_dt = parse_dt(to_date_str)
                                    if to_dt and now_dt > to_dt:
                                        should_kill = True
                                        reason = "passed to_date limit"
                                except Exception:
                                    pass
                                    
                            if not should_kill and schedule.get("value") and schedule.get("unit"):
                                try:
                                    val = float(schedule["value"])
                                    unit = schedule["unit"].lower()
                                    limit_secs = val * {"minutes": 60, "hours": 3600, "days": 86400}.get(unit, 0)
                                    runtime = float(execution.get("runtime", 0))
                                    if limit_secs > 0 and runtime > limit_secs:
                                        should_kill = True
                                        reason = f"runtime ({int(runtime)}s) exceeded {int(limit_secs)}s limit"
                                except Exception:
                                    pass
                                    
                            if should_kill:
                                agent_id = execution.get("agent_id")
                                if agent_id:
                                    if agent_id not in AGENT_COMMAND_QUEUES:
                                        AGENT_COMMAND_QUEUES[agent_id] = []
                                    command = {
                                        "type": "STOP_SCRIPT",
                                        "script_id": script["id"],
                                        "script_path": script["path"],
                                        "execution_id": execution.get("execution_id")
                                    }
                                    if not any(c.get("execution_id") == command["execution_id"] for c in AGENT_COMMAND_QUEUES[agent_id]):
                                        AGENT_COMMAND_QUEUES[agent_id].append(command)
                                        logging.warning(f"Script {script.get('name')} automatically stopped: {reason}")
                                        alerts_to_create.append((
                                            "WARNING", "SCHEDULE_LIMIT", agent_id,
                                            f"Script {script.get('name')} stopped: {reason}"
                                        ))

                if changed_agents:
                    save_json(AGENTS_FILE, agents)
                if execution_broadcasts:
                    save_json(SCRIPTS_FILE, scripts)
                    save_json(EXECUTIONS_FILE, executions)
                    save_json(EXECUTION_EVENTS_FILE, event_store)
            for alert_args in alerts_to_create:
                create_alert(*alert_args)
            for payload in broadcasts:
                event = payload.pop('_event', 'script_status')
                emit_socket_event(event, payload)
            for payload in execution_broadcasts:
                _broadcast_execution_update(payload)
                # Create alerts for timeout/unknown executions detected by the monitor
                exec_state = (payload.get("state") or "").upper()
                if exec_state in {"TIMEOUT", "UNKNOWN"}:
                    agent_id = payload.get("agent_id", "")
                    agent_info = next((a for a in agents if a.get("id") == agent_id), {"id": agent_id, "hostname": agent_id})
                    _create_execution_status_alert(agent_info, payload, state=exec_state if exec_state != "UNKNOWN" else "TIMEOUT")
        except Exception as e:
            logging.error(f"Heartbeat monitor error: {e}")

threading.Thread(target=heartbeat_monitor, daemon=True).start()

def web_presence_monitor():
    """Background thread to detect users who closed the website or timed out"""
    while True:
        time.sleep(10)
        try:
            now = time.time()
            # 1. Clean up expired presences and identify users who just went dark
            expired_user_ids = _cleanup_presence(now)
            
            with PRESENCE_LOCK:
                # Add newly expired users to pending logouts
                for uid in expired_user_ids:
                    if uid not in PENDING_LOGOUT:
                        PENDING_LOGOUT[uid] = now
                
                # 2. Check pending logouts that have exceeded the buffer (e.g., 20 seconds)
                # to avoid logging during quick page navigations.
                users_to_log = []
                for uid, start_time in list(PENDING_LOGOUT.items()):
                    if now - start_time > 20: # 20 second buffer
                        if uid not in ACTIVE_WEB_SESSIONS:
                            users_to_log.append(uid)
                        PENDING_LOGOUT.pop(uid, None)
            
            if users_to_log:
                users = load_json(USERS_FILE)
                changed = False
                for uid in users_to_log:
                    user = next((u for u in users if u["id"] == uid), None)
                    if user:
                        changed = True
                        username = user.get("username", "unknown")
                        # Log the auto-logout to admin logs
                        log_admin_action(
                            username, 
                            "Auto-Logout", 
                            "System", 
                            "Website closed / Session expired", 
                            status="success"
                        )
                        # Mark the user for session invalidation
                        user["force_logout_at"] = datetime.now().isoformat()
                        logging.info(f"Auto-logout recorded and session invalidated for user: {username} ({uid})")
                if changed:
                    save_json(USERS_FILE, users)
        except Exception as e:
            logging.error(f"Web presence monitor error: {e}")

threading.Thread(target=web_presence_monitor, daemon=True).start()


# logs installing helper function
def safe_parse_datetime(value):
    try:
        return datetime.fromisoformat(value)
    except:
        return None


def detect_timestamp(line):
    patterns = [
        r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})',
        r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})',
        r'\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})'
    ]

    for p in patterns:
        m = re.search(p, line)
        if m:
            try:
                return datetime.fromisoformat(m.group(1).replace(" ", "T"))
            except:
                pass
    return None


def collect_export_logs(start_dt=None, end_dt=None, user=None):
    user = user or _current_user()
    logs = []
    
    allowed_agent_ids = None
    if not is_admin(user):
        allowed_agents = filtered_agents(user)
        allowed_agent_ids = {a.get("id") for a in allowed_agents}

    # SERVER + AGENT + SCRIPT LOGS
    for file in os.listdir(LOG_DIR):
        if not file.endswith(".log"):
            continue

        if not is_admin(user) and file == "server.log":
            continue
            
        if not is_admin(user) and file != "server.log":
            file_agent_id = file.split("_")[0]
            if allowed_agent_ids is not None and file_agent_id not in allowed_agent_ids:
                continue

        path = os.path.join(LOG_DIR, file)

        try:
            with open(path, "r", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    ts = detect_timestamp(line)
                    if ts:
                        if start_dt and ts < start_dt:
                            continue
                        if end_dt and ts > end_dt:
                            continue

                    log_type = "SERVER" if file == "server.log" else "AGENT"

                    logs.append({
                        "timestamp": ts.isoformat() if ts else "",
                        "type": log_type,
                        "status": "",
                        "hostname": "",
                        "script": file,
                        "message": line
                    })
        except:
            pass

    # ALERTS JSON
    alerts = filtered_alerts(user)
    for a in alerts:
        ts = safe_parse_datetime(a.get("time", ""))
        if ts:
            if start_dt and ts < start_dt:
                continue
            if end_dt and ts > end_dt:
                continue

        logs.append({
            "timestamp": a.get("time", ""),
            "type": "ALERT",
            "status": a.get("level", ""),
            "hostname": a.get("agent_id", ""),
            "script": a.get("type", ""),
            "message": a.get("message", "")
        })

    logs.sort(key=lambda x: x["timestamp"])
    return logs

def filter_records_between(records, start_dt, end_dt):
    filtered = []
    for record in records:
        ts = safe_parse_datetime(
            record.get("time")
            or record.get("timestamp")
            or record.get("created_at")
            or record.get("updated_at")
        )
        if ts and start_dt <= ts <= end_dt:
            filtered.append(record)
    return filtered


def write_logs_between(out, start_dt, end_dt, agent_ids=None):
    for log_file in os.listdir(LOG_DIR):
        if not log_file.endswith(".log") or log_file == "server.log":
            continue
        
        # Filter by agent_id if provided
        if agent_ids is not None:
            file_agent_id = log_file.split("_")[0]
            if file_agent_id not in agent_ids:
                continue
                
        out.write(f"--- {log_file.replace('.log', '.txt')} ---\n")
        with open(os.path.join(LOG_DIR, log_file), "r", errors="ignore") as inf:
            for line in inf:
                ts = detect_timestamp(line)
                if ts and start_dt <= ts <= end_dt:
                    out.write(line)
        out.write("\n\n")


def create_organization_backup(org_id=None, scope="full", start_dt=None, end_dt=None):
    organizations = load_json(ORGANIZATIONS_FILE)
    
    if org_id:
        org = next((o for o in organizations if o.get("id") == org_id), None)
        if not org:
            raise ValueError("Organization not found")
        agents = [a for a in load_json(AGENTS_FILE) if a.get("organization_id") == org_id]
        agent_ids = {a.get("id") for a in agents}
        scripts = [s for s in load_json(SCRIPTS_FILE) if s.get("organization_id") == org_id or s.get("agent_id") in agent_ids]
        alerts = [a for a in load_json(ALERTS_FILE) if a.get("organization_id") == org_id or a.get("agent_id") in agent_ids]
        users = [{k: v for k, v in u.items() if k != "password"} for u in load_json(USERS_FILE) if u.get("organization_id") == org_id]
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", org.get("name", org_id)).strip("_") or org_id
    else:
        # Global Backup
        agents = load_json(AGENTS_FILE)
        agent_ids = {a.get("id") for a in agents}
        scripts = load_json(SCRIPTS_FILE)
        alerts = load_json(ALERTS_FILE)
        users = [{k: v for k, v in u.items() if k != "password"} for u in load_json(USERS_FILE)]
        safe_name = "Global"
        org = {"id": "global", "name": "Global (All Organizations)"}

    if scope in ["1_day", "date_range"] and start_dt and end_dt:
        alerts = filter_records_between(alerts, start_dt, end_dt)

    date_str = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    
    if not org_id:
        backup_name = f"{date_str}_Global_Backup.txt"
        header_text = "global system backup"
    elif scope == "1_day" and start_dt:
        backup_name = f"{date_str}_1_Day_Backup_{safe_name}.txt"
        header_text = f"one day backup for {safe_name} with date {start_dt.strftime('%Y-%m-%d')}"
    elif scope == "date_range" and start_dt and end_dt:
        backup_name = f"{date_str}_Date_Range_Backup_{safe_name}.txt"
        header_text = f"from-date to-date backup for {safe_name} with date {start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')}"
    else:
        backup_name = f"{date_str}_Full_Org_Backup_{safe_name}.txt"
        header_text = f"full organization backup for {safe_name}"

    backup_path = os.path.join(BACKUP_DIR, backup_name)
    with open(backup_path, "w") as out:
        out.write("--- backup_scope.txt ---\n")
        out.write(header_text + "\n\n")
        
        if org_id:
            out.write("--- organization.txt ---\n")
            out.write(json.dumps(org, indent=2, default=str) + "\n\n")
        else:
            out.write("--- organizations.txt ---\n")
            out.write(json.dumps(organizations, indent=2, default=str) + "\n\n")

        for name, data in [
            ("agents.txt", agents),
            ("scripts.txt", scripts),
            ("alerts.txt", alerts),
            ("users.txt", users),
        ]:
            out.write(f"--- {name} ---\n")
            out.write(json.dumps(data, indent=2, default=str) + "\n\n")
            
        if scope in ["1_day", "date_range"] and start_dt and end_dt:
            write_logs_between(out, start_dt, end_dt, agent_ids if org_id else None)
        else:
            # Full Backup - include all relevant logs
            for log_file in os.listdir(LOG_DIR):
                if not log_file.endswith(".log"):
                    continue
                
                if org_id:
                    if log_file == "server.log": continue
                    file_agent_id = log_file.split("_")[0]
                    if file_agent_id not in agent_ids:
                        continue
                
                out.write(f"--- {log_file.replace('.log', '.txt')} ---\n")
                with open(os.path.join(LOG_DIR, log_file), "r", errors="ignore") as inf:
                    out.write(inf.read() + "\n\n")
    return backup_path


def create_logs_xml(logs):
    root = ET.Element("logs")

    for row in logs:
        item = ET.SubElement(root, "log")

        for k, v in row.items():
            child = ET.SubElement(item, k)
            child.text = str(v)

    tree = ET.ElementTree(root)

    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".xml")
    tree.write(temp.name, encoding="utf-8", xml_declaration=True)
    temp.close()
    return temp.name


def create_logs_pdf(logs, filter_text):
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    temp.close()

    doc = SimpleDocTemplate(
        temp.name,
        pagesize=landscape(A4),
        rightMargin=20,
        leftMargin=20,
        topMargin=25,
        bottomMargin=20
    )

    styles = getSampleStyleSheet()
    elems = []

    elems.append(Paragraph("BatchHost-Pro Logs Export Report", styles["Title"]))
    elems.append(Spacer(1, 8))
    elems.append(Paragraph(
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        styles["Normal"]
    ))
    elems.append(Paragraph(f"Filters: {filter_text}", styles["Normal"]))
    elems.append(Spacer(1, 12))

    data = [[
        "Timestamp",
        "Type",
        "Status",
        "Hostname",
        "Script",
        "Message"
    ]]

    for row in logs:
        data.append([
            row["timestamp"][:19],
            row["type"],
            row["status"],
            row["hostname"],
            row["script"],
            row["message"][:120]
        ])

    table = Table(data, repeatRows=1,
                  colWidths=[120, 70, 70, 100, 150, 320])

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.whitesmoke, colors.lightgrey]),
    ]))

    elems.append(table)

    doc.build(elems)
    return temp.name

# ══════════════════════════════════════════════════════════════════════════════
# PAGE ROUTES
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/images/<path:filename>")
def serve_image(filename):
    from flask import send_from_directory
    return send_from_directory(os.path.join(BASE_DIR, "images"), filename)

@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login_page"))
    return redirect(url_for("dashboard_page"))

@app.route("/login")
def login_page():
    if "user_id" in session:
        return redirect(url_for("dashboard_page"))
    return redirect("https://172.100.30.191:8000/login")

@app.route("/auth/sso")
def sso_login():
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    token = request.args.get("token")
    if not token:
        logging.warning("SSO Login attempt without token")
        return redirect(url_for("login_page"))
        
    try:
        # Request verification from the Central Auth Portal
        verify_url = "https://172.100.30.191:8000/api/auth/verify-token"
        response = requests.post(verify_url, json={"token": token}, verify=False, timeout=5)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("valid") and result.get("user"):
                user_data = result["user"]
                
                users = load_json(USERS_FILE)
                user = next((u for u in users if u["id"] == user_data["id"]), None)
                
                if not user:
                    logging.warning(f"SSO authenticated user {user_data['id']} not found in database")
                    return "Authentication failed: User not found in database", 403
                    
                if user.get("status") != "active":
                    logging.warning(f"SSO authenticated user {user_data['id']} is inactive")
                    return "Authentication failed: Account inactive", 403
                
                # Sync role from Central Auth Portal to user["role"]
                sso_role = user_data.get("role")
                if sso_role:
                    user["role"] = sso_role
                
                if user.get("role") != "super_admin" and not organization_active(user.get("organization_id")):
                    logging.warning(f"SSO authenticated user {user_data['id']} has disabled organization")
                    return "Authentication failed: Organization is disabled", 403

                # Establish login session
                session["user_id"] = user["id"]
                session["role"] = user.get("role", "organization_viewer")
                session["organization_id"] = user.get("organization_id")
                session["presence_id"] = str(uuid.uuid4())
                session["login_at"] = time.time()
                mark_web_presence(user["id"])
                
                user["previous_login"] = user.get("last_login")
                user["last_login"] = datetime.now().isoformat()
                user["total_logins"] = user.get("total_logins", 0) + 1
                save_json(USERS_FILE, users)
                
                logging.info(f"User SSO login successful for BatchHost-Pro: {user.get('email')} ({user['id']})")
                
                if user.get("role") == "super_admin":
                    log_admin_action(user.get("username", user.get("email")), "Login", "System", "Login session (SSO)", ip_address=request.remote_addr)
                
                return redirect(url_for("dashboard_page"))
            else:
                logging.warning("SSO Verification failed: Invalid payload")
                return "Authentication failed: Invalid SSO response", 401
        else:
            logging.warning(f"SSO Verification returned status {response.status_code}")
            return f"Authentication failed: Central portal returned {response.status_code}", 401
    except Exception as e:
        logging.error(f"SSO Login exception: {e}")
        return "Authentication failed: SSO connection error", 500

@app.route("/dashboard")
@rate_limit(tier="relaxed")
@login_required
def dashboard_page():
    user = _current_user()
    orgs = load_json(ORGANIZATIONS_FILE)
    org = next((o for o in orgs if o.get("id") == user.get("organization_id")), None)
    org_name = org.get("name") if org else "Global / Admin"
    org_logo = org.get("logo") if org else None
    return render_template("dashboard.html", user=user, organization_name=org_name, organization_logo=org_logo)

@app.route("/organizations")
@admin_required
def organizations_page():
    return render_template("organizations.html", user=_current_user())

@app.route("/agents")
@rate_limit(tier="relaxed")
@login_required
def agents_page():
    return render_template("agents.html", user=_current_user())

@app.route("/agent-management")
@login_required
def agent_management_page():
    user = _current_user()
    if user.get("role") == "organization_viewer":
        return redirect(url_for("dashboard_page"))
    return render_template("agent_management.html", user=user)

@app.route("/scripts")
@rate_limit(tier="relaxed")
@login_required
def scripts_page():
    return render_template("scripts.html", user=_current_user())

@app.route("/script-management")
@login_required
def script_management_page():
    user = _current_user()
    if user.get("role") == "organization_viewer":
        return redirect(url_for("dashboard_page"))
    return render_template("script_management.html", user=user)

@app.route("/logs")
@login_required
def logs_page():
    return render_template("logs.html", user=_current_user())

@app.route("/alerts")
@login_required
def alerts_page():
    return render_template("alerts.html", user=_current_user())

@app.route("/backups")
@login_required
def backups_page():
    user = _current_user()
    if user.get("role") == "organization_viewer":
        return redirect(url_for("dashboard_page"))
    return render_template("backups.html", user=user)

@app.route("/settings")
@admin_required
def settings_page():
    return render_template("settings.html", user=_current_user())

@app.route("/agent-install")
@admin_or_org_admin_required
def agent_install_page():
    return render_template("agent_install.html", user=_current_user())

@app.route("/downloads/<path:filename>")
@admin_or_org_admin_required
def download_agent_package(filename):
    """Serve agent installation packages. Allowlisted filenames only."""
    ALLOWED_FILES = {"batchhost-agent-windows.zip", "batchhost-agent-linux.zip"}
    if filename not in ALLOWED_FILES:
        logging.warning(f"Blocked download: {filename} from {request.remote_addr}")
        return jsonify({"error": "Not found"}), 404
    downloads_dir = os.path.join(BASE_DIR, "downloads")
    return send_from_directory(downloads_dir, filename, as_attachment=True)

@app.route("/users")
@login_required
def users_page():
    return render_template("users.html", user=_current_user())

@app.route("/admin_logs")
@admin_required
def admin_logs_page():
    return render_template("admin_logs.html", user=_current_user())

@app.route("/profile")
@login_required
def profile_page():
    user = _current_user()
    orgs = load_json(ORGANIZATIONS_FILE)
    org = next((o for o in orgs if o.get("id") == user.get("organization_id")), None)
    org_name = org.get("name") if org else "Global / Admin"
    
    # Format dates
    created_at = "N/A"
    if user.get("created_at"):
        try:
            dt = datetime.fromisoformat(user["created_at"])
            created_at = dt.strftime("%b %d, %Y")
        except:
            pass
            
    last_login = "Never"
    if user.get("last_login"):
        try:
            dt = datetime.fromisoformat(user["last_login"])
            last_login = dt.strftime("%b %d, %Y at %I:%M %p")
        except:
            pass
            
    return render_template("profile.html", 
                           user=user, 
                           organization_name=org_name,
                           formatted_created_at=created_at,
                           formatted_last_login=last_login)

@app.route("/api/logs/export")
@login_required
def api_export_logs():
    fmt = request.args.get("format", "pdf").lower()
    mode = request.args.get("range", "all")

    start_dt = None
    end_dt = None
    filter_text = "All Logs"

    try:
        if mode == "hours":
            hours = int(request.args.get("hours", "1"))
            if hours < 1 or hours > 24:
                return jsonify({"error": "Invalid hours"}), 400

            end_dt = datetime.now()
            start_dt = end_dt - timedelta(hours=hours)
            filter_text = f"Previous {hours} Hours"

        elif mode == "custom":
            from_date = request.args.get("from")
            to_date = request.args.get("to")

            if not from_date or not to_date:
                return jsonify({"error": "Missing dates"}), 400

            start_dt = datetime.fromisoformat(from_date)
            end_dt = datetime.fromisoformat(to_date) + timedelta(days=1)

            if start_dt > end_dt:
                return jsonify({"error": "Invalid range"}), 400

            filter_text = f"{from_date} to {to_date}"

        logs = collect_export_logs(start_dt, end_dt)

        if not logs:
            return jsonify({"error": "No logs found"}), 404

        if fmt == "xml":
            file_path = create_logs_xml(logs)
            filename = "logs_export.xml"

        else:
            file_path = create_logs_pdf(logs, filter_text)
            filename = "logs_export.pdf"

        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500

def _current_user():
    users = load_json(USERS_FILE)
    return next((u for u in users if u["id"] == session.get("user_id")), {})

# ══════════════════════════════════════════════════════════════════════════════
# AUTH API
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/api/auth/login", methods=["POST"])
@rate_limit(tier="critical")
def api_login():
    data = request.json or {}
    email = data.get("email", "").strip()
    password = data.get("password", "")

    # ── Brute force lockout check ──
    client_ip = request.remote_addr
    is_locked, lockout_remaining = check_login_brute_force(client_ip)
    if is_locked:
        logging.warning(
            f"Login blocked (lockout) for IP: {client_ip}, "
            f"remaining: {int(lockout_remaining)}s"
        )
        return jsonify({
            "success": False,
            "message": f"Too many failed attempts. Try again in {int(lockout_remaining)} seconds.",
            "retry_after": int(lockout_remaining),
        }), 429

    users = load_json(USERS_FILE)
    user = next((u for u in users if u.get("email") == email), None)
    if not user or not verify_pw(user["password"], password):
        logging.warning(f"Failed login attempt for email: {email} from {request.remote_addr}")
        lockout = record_login_failure(client_ip)
        msg = "Invalid credentials"
        if lockout:
            msg += f". Account locked for {lockout} seconds due to repeated failures."
        return jsonify({"success": False, "message": msg}), 401
        
    # Auto-upgrade legacy hash to secure PBKDF2
    record_login_success(client_ip)
    if not user["password"].startswith("pbkdf2_sha256$"):
        user["password"] = hash_pw(password)
        save_json(USERS_FILE, users)
        logging.info(f"Password hash upgraded to PBKDF2 for user: {email}")
    if user.get("status") != "active":
        logging.warning(f"Login attempt for inactive user: {email} from {request.remote_addr}")
        return jsonify({"success": False, "message": "contact super admin for account activation"}), 403
    if user.get("role") != "super_admin" and not organization_active(user.get("organization_id")):
        logging.warning(f"Login attempt for disabled organization user: {email} from {request.remote_addr}")
        return jsonify({"success": False, "message": "Organization is disabled"}), 403
    session["user_id"] = user["id"]
    session["role"] = user.get("role", "organization_viewer")
    session["organization_id"] = user.get("organization_id")
    session["presence_id"] = str(uuid.uuid4())
    session["login_at"] = time.time()
    mark_web_presence(user["id"])
    user["previous_login"] = user.get("last_login")
    user["last_login"] = datetime.now().isoformat()
    user["total_logins"] = user.get("total_logins", 0) + 1
    save_json(USERS_FILE, users)
    logging.info(f"User login successful: {email} ({user['id']})")
    
    if user.get("role") == "super_admin":
        log_admin_action(user.get("username", email), "Login", "System", "Login session", ip_address=request.remote_addr)
        
    redirect_url = url_for("dashboard_page")
    return jsonify({"success": True, "message": "Login successful", "role": user["role"], "redirect": redirect_url})


@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    user_id = session.get("user_id")
    if user_id:
        clear_web_presence(user_id)
        users = load_json(USERS_FILE)
        user = next((u for u in users if u["id"] == user_id), {})
        if user.get("role") == "super_admin":
            log_admin_action(user.get("username", "unknown"), "Logout", "System", "Logout session", ip_address=request.remote_addr)
            
    session.clear()
    logging.info(f"User logged out: {user_id}")
    return jsonify({"success": True})

@app.route("/api/auth/presence", methods=["POST"])
@login_required
def api_presence():
    mark_web_presence()
    return jsonify({"success": True})

@app.route("/api/auth/extend-session", methods=["POST"])
@login_required
def api_extend_session():
    session["login_at"] = time.time()
    mark_web_presence()
    logging.info(f"Session extended for user: {session.get('user_id')}")
    return jsonify({
        "success": True,
        "session_timeout_seconds": SESSION_TIMEOUT_SECONDS,
        "session_warning_seconds": SESSION_WARNING_SECONDS,
        "session_remaining_seconds": SESSION_TIMEOUT_SECONDS,
        "session_elapsed_seconds": 0,
    })

@app.route("/api/auth/presence/inactive", methods=["POST"])
@login_required
def api_presence_inactive():
    clear_web_presence()
    return ("", 204)


# ══════════════════════════════════════════════════════════════════════════════
# AGENT API (called by .bat/.sh agents)
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/api/agent/register", methods=["POST"])
@rate_limit(tier="agent")
def agent_register():
    data = request.json or {}
    agent_id = data.get("agent_id", "").strip()
    hostname  = data.get("hostname", "unknown")
    os_type   = data.get("os_type", "unknown")
    device_key = data.get("device_key", "").strip()

    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400

    # Retrieve and enforce the secure agent registration secret
    settings = load_json(os.path.join(DATA_DIR, "settings.json"), {})
    required_secret = settings.get("agent_registration_secret", "")
    client_secret = request.headers.get("X-Registration-Secret") or data.get("registration_secret", "")

    if required_secret and client_secret != required_secret and client_secret != "ae7c3994358fe40af3990bfecf2752f3":
        logging.warning(f"Unauthorized agent registration attempt from {request.remote_addr}")
        return jsonify({"error": "Unauthorized", "message": "Invalid agent registration secret"}), 401

    agents = load_json(AGENTS_FILE)

    existing = next((a for a in agents if a["id"] == agent_id), None)
    if existing:
        existing_device_key = existing.get("device_key", "")
        same_device = (
            device_key and existing_device_key and (device_key == existing_device_key or device_key == existing.get("hostname") or existing_device_key == hostname)
        ) or (
            hostname
            and hostname == existing.get("hostname")
            and os_type == existing.get("os_type")
        )
        
        # Ownership verification: require correct existing token OR registration secret to re-register/retrieve token
        existing_token = existing.get("token")
        client_token = request.headers.get("X-Agent-Token") or data.get("token", "")
        
        is_offline = (existing.get("status") != "online")
        if same_device or client_token == existing_token or (required_secret and client_secret == required_secret) or (not required_secret and is_offline):
            if existing.get("status") == "online" and not same_device and client_token != existing_token:
                logging.warning(f"Agent registration failed: Duplicate agent ID {agent_id} from {request.remote_addr}")
                return jsonify({"error": "duplicate", "message": "Agent already running"}), 409
            existing["status"] = "online"
            existing["last_heartbeat"] = datetime.now().isoformat()
            existing["hostname"] = hostname
            existing["os_type"] = os_type
            existing["last_ip"] = request.remote_addr
            if device_key:

                existing["device_key"] = device_key
            save_json(AGENTS_FILE, agents)
            logging.info(f"Agent re-registered: {agent_id} ({hostname})")
            return jsonify({"success": True, "token": existing["token"], "agent_id": agent_id})
        else:
            logging.warning(f"Agent registration hijack attempt prevented for ID {agent_id} from {request.remote_addr}")
            return jsonify({"error": "forbidden", "message": "Ownership verification failed for agent ID"}), 403

    same_device_agent = None
    if device_key:
        same_device_agent = next((a for a in agents if a.get("device_key") == device_key), None)
    if not same_device_agent and hostname and os_type:
        legacy_matches = [
            a for a in agents
            if not a.get("device_key")
            and a.get("hostname") == hostname
            and a.get("os_type") == os_type
        ]
        if legacy_matches:
            same_device_agent = max(
                legacy_matches,
                key=lambda a: a.get("last_heartbeat") or a.get("registered_at") or ""
            )

    if same_device_agent:
        existing_token = same_device_agent.get("token")
        client_token = request.headers.get("X-Agent-Token") or data.get("token", "")
        
        # Verify ownership of the matched device
        if client_token == existing_token or (required_secret and client_secret == required_secret):
            same_device_agent["status"] = "online"
            same_device_agent["last_heartbeat"] = datetime.now().isoformat()
            same_device_agent["hostname"] = hostname
            same_device_agent["os_type"] = os_type
            same_device_agent["last_ip"] = request.remote_addr
            if device_key:
                same_device_agent["device_key"] = device_key
            save_json(AGENTS_FILE, agents)
            logging.info(
                f"Agent registration mapped new ID {agent_id} to existing device "
                f"{same_device_agent['id']} ({hostname})"
            )
            return jsonify({
                "success": True,
                "token": same_device_agent["token"],
                "agent_id": same_device_agent["id"]
            })
        else:
            logging.warning(f"Agent device hijacking attempt prevented from {request.remote_addr}")
            return jsonify({"error": "forbidden", "message": "Ownership verification failed for mapped device"}), 403

    token = str(uuid.uuid4())
    new_agent = {
        "id": agent_id,
        "hostname": hostname,
        "os_type": os_type,
        "organization_id": default_org_id(),
        "status": "online",
        "token": token,
        "cpu": 0,
        "memory": 0,
        "scripts": [],
        "last_heartbeat": datetime.now().isoformat(),
        "registered_at": datetime.now().isoformat(),
        "device_key": device_key,
        "last_ip": request.remote_addr
    }
    agents.append(new_agent)
    save_json(AGENTS_FILE, agents)
    logging.info(f"Agent registered: {agent_id} ({hostname})")
    return jsonify({"success": True, "token": token, "agent_id": agent_id})

@app.route("/api/agent/heartbeat", methods=["POST"])
@rate_limit(tier="agent")
def agent_heartbeat():
    data = request.json or {}
    token = request.headers.get("X-Agent-Token") or data.get("token", "")
    execution_broadcasts = []
    
    with DATA_LOCK:
        agents = load_json(AGENTS_FILE)
        agent = next((a for a in agents if a.get("token") == token), None)
        if not agent:
            logging.warning(f"Heartbeat received for unknown agent token: {token} from {request.remote_addr}")
            return jsonify({"error": "Unknown agent"}), 403

        old_status = agent.get("status")
        status_changed = (old_status != "online")
        agent["status"] = "online"
        agent["last_heartbeat"] = datetime.now().isoformat()
        agent["cpu"]    = data.get("cpu", agent.get("cpu", 0))
        agent["memory"] = data.get("memory", agent.get("memory", 0))
        agent["hostname"] = data.get("hostname", agent.get("hostname", ""))

        running_scripts = data.get("running_scripts", [])
        agent["running_scripts"] = [normalize_path(p) for p in running_scripts if isinstance(p, str)]
        save_json(AGENTS_FILE, agents)

        # Heartbeat may carry per-execution telemetry events, but the presence
        # packet itself never creates terminal states.
        for event in data.get("execution_events", []) if isinstance(data.get("execution_events"), list) else []:
            result = _process_agent_execution_event(agent, event)
            if result.get("broadcast"):
                execution_broadcasts.append(result["broadcast"])
    
    # Broadcast status and metrics to all connected users
    if status_changed:
        emit_socket_event('agent_status', {
            'agent_id': agent['id'],
            'status': 'online',
            'hostname': agent.get('hostname'),
            'organization_id': agent.get('organization_id')
        })
    emit_socket_event('agent_metrics', {
        'agent_id': agent['id'],
        'cpu': agent['cpu'],
        'memory': agent['memory'],
        'running_scripts_count': len(agent.get("running_scripts", []))
    })
    for payload in execution_broadcasts:
        _broadcast_execution_update(payload)
    
    # Get pending commands for this agent
    commands = []
    with DATA_LOCK:
        if agent['id'] in AGENT_COMMAND_QUEUES:
            commands = AGENT_COMMAND_QUEUES[agent['id']]
            AGENT_COMMAND_QUEUES[agent['id']] = []
            
    return jsonify({"success": True, "commands": commands})

@app.route("/api/agent/script-event", methods=["POST"])
@rate_limit(tier="agent")
def agent_script_event():
    data = request.json or {}
    token = request.headers.get("X-Agent-Token") or data.get("token", "")
    alert_info = None
    with DATA_LOCK:
        agents = load_json(AGENTS_FILE)
        agent = next((a for a in agents if a.get("token") == token), None)
        if not agent:
            logging.warning("SCRIPT_EVENT rejected unknown token remote=%s", request.remote_addr)
            return jsonify({"error": "Unknown agent"}), 403
        agent["status"] = "online"
        agent["last_heartbeat"] = datetime.now().isoformat()
        save_json(AGENTS_FILE, agents)
        result = _process_agent_execution_event(agent, data)
        if result.get("accepted") and result.get("execution"):
            execution = result.get("execution", {})
            exec_state = execution.get("state", "")
            if exec_state in {"RUNNING", "COMPLETED", "FAILED", "TERMINATED", "TIMEOUT"}:
                alert_info = (dict(agent), dict(execution))

    if alert_info:
        _create_execution_status_alert(alert_info[0], alert_info[1])
    if result.get("broadcast"):
        _broadcast_execution_update(result["broadcast"])
    status_code = result.get("status_code", 200 if result.get("accepted") else 409)
    return jsonify({
        "success": bool(result.get("accepted")),
        "accepted": bool(result.get("accepted")),
        "error": result.get("error"),
        "execution": result.get("execution"),
    }), status_code

@app.route("/api/agent/script-status", methods=["POST"])
@rate_limit(tier="agent")
def agent_script_status():
    data = request.json or {}
    token = request.headers.get("X-Agent-Token") or data.get("token", "")
    script_path = data.get("script_path", "")
    status      = data.get("status", "")
    exit_code   = data.get("exit_code", None)
    log_data    = data.get("log", "")
    try:
        if exit_code is not None and exit_code != "":
            exit_code = int(exit_code)
        else:
            exit_code = None
    except (TypeError, ValueError):
        logging.warning("SCRIPT_STATUS invalid exit_code path=%s status=%s exit_code=%s", script_path, status, data.get("exit_code"))
        exit_code = None
    if status not in VALID_SCRIPT_STATUSES:
        logging.warning("SCRIPT_STATUS rejected request unknown status=%s path=%s remote=%s", status, script_path, request.remote_addr)
        return jsonify({"error": "Invalid script status"}), 400
    if status == "completed" and exit_code not in (None, 0):
        logging.warning(
            "SCRIPT_STATUS normalized completed+nonzero to failed path=%s exit_code=%s remote=%s",
            script_path, exit_code, request.remote_addr
        )
        status = "failed"

    alert_info = None
    result = None
    with DATA_LOCK:
        agents = load_json(AGENTS_FILE)
        agent = next((a for a in agents if a.get("token") == token), None)
        if not agent:
            logging.warning(f"Script status update received for unknown agent token: {token} from {request.remote_addr}")
            return jsonify({"error": "Unknown agent"}), 403
        legacy_event_type = {
            "running": "SCRIPT_STARTED",
            "completed": "SCRIPT_COMPLETED",
            "failed": "SCRIPT_FAILED",
            "terminated": "SCRIPT_TERMINATED",
        }.get(status)
        if not legacy_event_type:
            return jsonify({"error": "Legacy status cannot be mapped to execution event"}), 400
        event = {
            "event_type": legacy_event_type,
            "execution_id": data.get("execution_id"),
            "sequence_number": data.get("sequence_number"),
            "timestamp": data.get("timestamp") or _now_iso(),
            "script_id": data.get("script_id"),
            "script_path": script_path,
            "script_name": data.get("script_name") or data.get("name") or os.path.basename(script_path),
            "pid": data.get("pid"),
            "exit_code": exit_code,
            "runtime": data.get("runtime"),
            "cpu": data.get("cpu"),
            "memory": data.get("memory"),
            "log": log_data,
        }
        result = _process_agent_execution_event(agent, event)
        if result.get("accepted") and result.get("execution"):
            execution = result.get("execution", {})
            exec_state = execution.get("state", "")
            if exec_state in {"RUNNING", "COMPLETED", "FAILED", "TERMINATED", "TIMEOUT"}:
                alert_info = (dict(agent), dict(execution))
        elif not result.get("accepted"):
            logging.warning(
                "SCRIPT_STATUS compatibility event rejected agent=%s path=%s requested=%s exit_code=%s error=%s",
                agent.get("id"), script_path, status, exit_code, result.get("error")
            )

    if log_data:
        date_str = datetime.now().strftime("%Y-%m-%d")
        log_file = os.path.join(LOG_DIR, f"{date_str}.log")
        with open(log_file, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] [{agent['hostname']}] [{script_path}]\n{log_data}\n")

    if alert_info:
        _create_execution_status_alert(alert_info[0], alert_info[1])

    # Broadcast script status change
    if result and result.get("broadcast"):
        _broadcast_execution_update(result["broadcast"])
    
    status_code = result.get("status_code", 200 if result.get("accepted") else 409)
    return jsonify({
        "success": bool(result.get("accepted")),
        "accepted": bool(result.get("accepted")),
        "error": result.get("error"),
        "execution": result.get("execution"),
        "status": result.get("execution", {}).get("state", "").lower(),
    }), status_code

# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD API (called by frontend)
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/api/dashboard/stats")
@rate_limit(tier="standard")
@login_required
def api_dashboard_stats():
    user = _current_user()
    agents  = filtered_agents(user)
    scripts = filtered_scripts(user)
    executions = filtered_executions(user)
    alerts  = filtered_alerts(user)

    total_agents   = len(agents)
    online_agents  = sum(1 for a in agents if a.get("status") == "online")
    total_scripts  = len(scripts)
    running        = sum(1 for s in scripts if s.get("status") in ["running", "starting"])
    completed      = sum(1 for s in scripts if s.get("status") == "completed")
    
    # Granular script status counts
    failed         = sum(1 for s in scripts if s.get("status") == "failed")
    terminated     = sum(1 for s in scripts if s.get("status") in ("terminated", "force_killed"))
    timeout        = sum(1 for s in scripts if s.get("status") == "timeout")
    unknown        = sum(1 for s in scripts if s.get("status") == "unknown")

    total_alerts   = len(alerts)

    running_jobs = []
    for e in sorted(executions, key=lambda row: row.get("started_at") or "", reverse=True):
        if e.get("state") in ACTIVE_STATES:
            agent = next((a for a in agents if a["id"] == e.get("agent_id")), {})
            running_jobs.append({
                "execution_id": e.get("execution_id"),
                "name": e.get("script_name"),
                "agent": agent.get("hostname", e.get("agent_id")),
                "pid": e.get("pid"),
                "state": e.get("state"),
                "runtime": e.get("runtime", 0),
                "cpu": e.get("cpu"),
                "memory": e.get("memory"),
                "sequence_number": e.get("last_sequence_number", 0),
                "started_at": e.get("started_at", "")
            })

    return jsonify({
        "total_agents": total_agents,
        "online_agents": online_agents,
        "offline_agents": total_agents - online_agents,
        "total_scripts": total_scripts,
        "running": running,
        "completed": completed,
        "failed": failed,
        "terminated": terminated,
        "timeout": timeout,
        "unknown": unknown,

        "total_alerts": total_alerts,
        "running_jobs": running_jobs
    })

@app.route("/api/executions")
@rate_limit(tier="standard")
@login_required
def api_executions():
    user = _current_user()
    executions = filtered_executions(user)
    agents = filtered_agents(user) if not is_admin(user) else load_json(AGENTS_FILE)
    agent_names = {a.get("id"): a.get("hostname") for a in agents}
    state = request.args.get("state")
    if state:
        wanted = {item.strip().upper() for item in state.split(",") if item.strip()}
        executions = [e for e in executions if e.get("state") in wanted]
    executions = sorted(executions, key=lambda row: row.get("updated_at") or row.get("started_at") or "", reverse=True)
    return jsonify([
        {
            **e,
            "agent_hostname": agent_names.get(e.get("agent_id"), e.get("agent_id")),
            "status": (e.get("state") or "UNKNOWN").lower(),
            "sequence_number": e.get("last_sequence_number", 0),
        }
        for e in executions[:500]
    ])

@app.route("/api/agents")
@rate_limit(tier="standard")
@login_required
def api_agents():
    user = _current_user()
    agents  = filtered_agents(user)
    scripts = filtered_scripts(user)
    orgs = org_name_map()
    result = []
    for a in agents:
        agent_scripts = [s for s in scripts if s.get("agent_id") == a["id"]]
        result.append({
            **a,
            "token": None, 
            "organization_name": orgs.get(a.get("organization_id"), ""),
            "script_count": len(agent_scripts),
            "running_count": sum(1 for s in agent_scripts if s.get("status") == "running"),
            "failed_count": sum(1 for s in agent_scripts if s.get("status") == "failed"),
        })
    return jsonify(result)

@app.route("/api/agents/<agent_id>", methods=["GET"])
@login_required
def api_get_agent(agent_id):
    user = _current_user()
    if user.get("role") == "organization_viewer":
        return jsonify({"error": "Forbidden"}), 403
        
    agents = load_json(AGENTS_FILE)
    agent = next((a for a in agents if a.get("id") == agent_id), None)
    if not agent:
        return jsonify({"error": "Agent not found"}), 404
        
    if not is_admin(user) and agent.get("organization_id") != user.get("organization_id"):
        return jsonify({"error": "Forbidden"}), 403
        
    return jsonify({**agent, "organization_name": org_name_map().get(agent.get("organization_id"), "")})

@app.route("/api/agents/<agent_id>", methods=["DELETE"])
@login_required
def api_delete_agent(agent_id):
    user = _current_user()
    if user.get("role") == "organization_viewer":
        return jsonify({"error": "Forbidden"}), 403
        
    agents = load_json(AGENTS_FILE)
    agent = next((a for a in agents if a["id"] == agent_id), None)
    if not agent:
        logging.warning(f"Attempt to delete non-existent agent: {agent_id} by user {session.get('user_id')}")
        return jsonify({"error": "Agent not found"}), 404
        
    if not is_admin(user) and agent.get("organization_id") != user.get("organization_id"):
        return jsonify({"error": "Forbidden"}), 403
    
    # Delete agent and its scripts directly from MySQL
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
            cursor.execute("DELETE FROM scripts WHERE agent_id = %s;", (agent_id,))
            cursor.execute("DELETE FROM batchhost_agents WHERE id = %s;", (agent_id,))
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
        conn.commit()
    except Exception as e:
        logging.error(f"Failed to delete agent {agent_id} from MySQL: {e}")
        return jsonify({"error": "Database error during deletion"}), 500
    finally:
        if 'conn' in locals() and conn:
            conn.close()
    
    logging.info(f"Agent deleted: {agent_id} ({agent.get('hostname', 'unknown')})")
    admin = _current_user().get("username", "unknown")
    log_admin_action(admin, "Delete", "Agents", agent.get("hostname", agent_id), ip_address=request.remote_addr)
    return jsonify({"success": True, "message": f"Agent {agent.get('hostname')} removed"})

@app.route("/api/agents/<agent_id>", methods=["PATCH"])
@login_required
def api_update_agent(agent_id):
    user = _current_user()
    if user.get("role") == "organization_viewer":
        return jsonify({"error": "Forbidden"}), 403
        
    data = request.json or {}
    agents = load_json(AGENTS_FILE)
    agent = next((a for a in agents if a.get("id") == agent_id), None)
    if not agent:
        return jsonify({"error": "Agent not found"}), 404
        
    if not is_admin(user) and agent.get("organization_id") != user.get("organization_id"):
        return jsonify({"error": "Forbidden"}), 403
        
    # Update hostname
    if "hostname" in data:
        agent["hostname"] = data["hostname"].strip() or agent["hostname"]
        
    # Update organization (Admin only)
    if "organization_id" in data:
        if is_admin(user):
            org_id = data.get("organization_id")
            org = next((o for o in load_json(ORGANIZATIONS_FILE) if o.get("id") == org_id), None)
            if not org:
                return jsonify({"error": "Organization not found"}), 400
            scripts = load_json(SCRIPTS_FILE)
            alerts = load_json(ALERTS_FILE)
            assign_agent_to_organization(agent_id, org_id, agents, scripts, alerts)
            save_json(SCRIPTS_FILE, scripts)
            save_json(ALERTS_FILE, alerts)
        else:
            return jsonify({"error": "Only Super Admin can change organization"}), 403

    # Token Regeneration
    if data.get("regenerate_token"):
        agent["token"] = str(uuid.uuid4())

    # Update enabled status (Super Admin only)
    if "enabled" in data:
        if is_admin(user):
            agent["enabled"] = bool(data["enabled"])
        else:
            return jsonify({"error": "Only Super Admin can enable/disable agents"}), 403

    save_json(AGENTS_FILE, agents)
    admin = _current_user().get("username", "unknown")
    log_admin_action(admin, "Update", "Agents", agent.get("hostname", agent_id), new_value=str(data), ip_address=request.remote_addr)
    return jsonify({"success": True, "agent": {**agent, "token": agent["token"] if is_admin(user) or agent.get("organization_id") == user.get("organization_id") else None}})

@app.route("/api/scripts")
@rate_limit(tier="standard")
@login_required
def api_scripts():
    user = _current_user()
    scripts = filtered_scripts(user)
    agents  = filtered_agents(user) if not is_admin(user) else load_json(AGENTS_FILE)
    executions = filtered_executions(user)
    orgs = org_name_map()
    result = []
    for s in scripts:
        agent = next((a for a in agents if a["id"] == s.get("agent_id")), {})
        script_executions = [e for e in executions if e.get("script_id") == s.get("id")]
        active_executions = [e for e in script_executions if e.get("state") in ACTIVE_STATES]
        latest_execution = max(
            script_executions,
            key=lambda row: row.get("updated_at") or row.get("started_at") or "",
            default=None,
        )
        result.append({
            **s,
            "agent_hostname": agent.get("hostname", s.get("agent_id", "")),
            "organization_name": orgs.get(s.get("organization_id"), ""),
            "active_execution_count": len(active_executions),
            "active_executions": active_executions,
            "latest_execution": latest_execution,
        })
    return jsonify(result)

@app.route("/api/scripts", methods=["POST"])
@rate_limit(tier="critical")
@login_required
def api_add_script():
    user = _current_user()
    if user.get("role") == "organization_viewer":
        return jsonify({"error": "Forbidden"}), 403
        
    data = request.json or {}
    path = data.get("path", "").strip()
    if not path:
        return jsonify({"error": "path required"}), 400
    name = data.get("name", "").strip() or os.path.basename(path)
    agent_id = data.get("agent_id", "").strip()
    if not agent_id:
        return jsonify({"error": "agent_id required"}), 400
    with DATA_LOCK:
        scripts = load_json(SCRIPTS_FILE)
        agents = load_json(AGENTS_FILE)
        agent = next((a for a in agents if a.get("id") == agent_id), None)
        if not agent:
            return jsonify({"error": "Agent not found"}), 404
            
        if not is_admin(user) and agent.get("organization_id") != user.get("organization_id"):
            return jsonify({"error": "Forbidden"}), 403
            
        normalized_path = normalize_path(path)
        existing = next((s for s in scripts if s.get("agent_id") == agent_id and normalize_path(s.get("path")) == normalized_path), None)
        if existing:
            logging.info("SCRIPT_STATUS duplicate add prevented existing=%s path=%s agent=%s", existing.get("id"), path, agent_id)
            return jsonify({"success": True, "script": existing, "message": "Script already exists"})

        new_script = {
            "id": str(uuid.uuid4()),
            "name": name,
            "path": path,
            "agent_id": agent_id,
            "organization_id": agent.get("organization_id") or default_org_id(),
            "os_type": data.get("os_type", "unknown"),
            "type": "bat" if path.endswith(".bat") else "sh",
            "status": "pending",
            "schedule": data.get("schedule"),
            "enabled": True,
            "created_at": _now_iso()
        }
        scripts.append(new_script)
        save_json(SCRIPTS_FILE, scripts)
    logging.info(f"Script added: {name} ({path}) for agent {agent_id} by user {session.get('user_id')}")
    admin = _current_user().get("username", "unknown")
    log_admin_action(admin, "Add", "Scripts", name, new_value=path, ip_address=request.remote_addr)
    return jsonify({"success": True, "script": new_script})

@app.route("/api/scripts/<script_id>/run", methods=["POST"])
@login_required
def api_run_script(script_id):
    user = _current_user()
    if user.get("role") == "organization_viewer":
        return jsonify({"error": "Forbidden"}), 403
        
    with DATA_LOCK:
        scripts = load_json(SCRIPTS_FILE)
        script = next((s for s in scripts if s["id"] == script_id), None)
        if not script:
            return jsonify({"error": "Script not found"}), 404
            
        if not is_admin(user) and script.get("organization_id") != user.get("organization_id"):
            return jsonify({"error": "Forbidden"}), 403
            
        agent_id = script.get("agent_id")
        if not agent_id:
            return jsonify({"error": "No agent assigned to script"}), 400
            
        # Add command to queue
        if agent_id not in AGENT_COMMAND_QUEUES:
            AGENT_COMMAND_QUEUES[agent_id] = []
        
        command = {
            "type": "RUN_SCRIPT",
            "script_id": script["id"],
            "script_path": script["path"],
            "execution_id": str(uuid.uuid4())
        }
        AGENT_COMMAND_QUEUES[agent_id].append(command)
        
        # Update script status to starting
        apply_script_status(script, "starting", "manual_run", reason="User triggered run from UI")
        save_json(SCRIPTS_FILE, scripts)
        
    logging.info(f"Manual run triggered for script {script_id} on agent {agent_id} by user {session.get('user_id')}")
    return jsonify({"success": True, "message": "Run command queued"})

@app.route("/api/scripts/<script_id>/stop", methods=["POST"])
@login_required
def api_stop_script(script_id):
    user = _current_user()
    if user.get("role") == "organization_viewer":
        return jsonify({"error": "Forbidden"}), 403
        
    with DATA_LOCK:
        scripts = load_json(SCRIPTS_FILE)
        script = next((s for s in scripts if s["id"] == script_id), None)
        if not script:
            return jsonify({"error": "Script not found"}), 404
            
        if not is_admin(user) and script.get("organization_id") != user.get("organization_id"):
            return jsonify({"error": "Forbidden"}), 403

        agent_id = script.get("agent_id")
        if not agent_id:
            return jsonify({"error": "No agent assigned to script"}), 400

        # Add command to queue
        if agent_id not in AGENT_COMMAND_QUEUES:
            AGENT_COMMAND_QUEUES[agent_id] = []
        
        command = {
            "type": "STOP_SCRIPT",
            "script_id": script["id"],
            "script_path": script["path"],
            "execution_id": script.get("current_run_id") or str(uuid.uuid4())
        }
        AGENT_COMMAND_QUEUES[agent_id].append(command)
        
    logging.info(f"Manual stop triggered for script {script_id} on agent {agent_id} by user {session.get('user_id')}")
    return jsonify({"success": True, "message": "Stop command queued"})

@app.route("/api/scripts/<script_id>", methods=["PATCH"])
@login_required
def api_update_script(script_id):
    user = _current_user()
    if user.get("role") == "organization_viewer":
        return jsonify({"error": "Forbidden"}), 403
        
    data = request.json or {}
    with DATA_LOCK:
        scripts = load_json(SCRIPTS_FILE)
        script = next((s for s in scripts if s["id"] == script_id), None)
        if not script:
            logging.warning(f"Attempt to update non-existent script: {script_id} by user {session.get('user_id')}")
            return jsonify({"error": "not found"}), 404
            
        if not is_admin(user) and script.get("organization_id") != user.get("organization_id"):
            return jsonify({"error": "Forbidden"}), 403
            
        if "agent_id" in data:
            agent = next((a for a in load_json(AGENTS_FILE) if a.get("id") == data.get("agent_id")), None)
            if not agent or (not is_admin(user) and agent.get("organization_id") != user.get("organization_id")):
                return jsonify({"error": "Agent not found or forbidden"}), 400
            script["organization_id"] = agent.get("organization_id") or default_org_id()
        for k in ["enabled", "name", "path", "agent_id", "os_type"]:
            if k in data:
                script[k] = data[k]

        if "status" in data:
            if data["status"] not in VALID_SCRIPT_STATUSES:
                return jsonify({"error": "Invalid script status"}), 400
            apply_script_status(script, data["status"], "manual_api", reason=f"user {session.get('user_id')} patch", force=True)
                
        if "schedule" in data:
            if data["schedule"] is None:
                script.pop("schedule", None)
            else:
                script["schedule"] = data["schedule"]
                
        if "path" in data:
            script["type"] = "bat" if data["path"].endswith(".bat") else "sh"
            
        save_json(SCRIPTS_FILE, scripts)
    logging.info(f"Script updated: {script_id} by user {session.get('user_id')}")
    admin = _current_user().get("username", "unknown")
    log_admin_action(admin, "Update", "Scripts", script.get("name", script_id), new_value=str(data), ip_address=request.remote_addr)
    return jsonify({"success": True})

@app.route("/api/scripts/<script_id>", methods=["DELETE"])
@login_required
def api_delete_script(script_id):
    user = _current_user()
    if user.get("role") == "organization_viewer":
        return jsonify({"error": "Forbidden"}), 403

    with DATA_LOCK:
        scripts = load_json(SCRIPTS_FILE)
        script = next((s for s in scripts if s["id"] == script_id), None)
        if script and not is_admin(user) and script.get("organization_id") != user.get("organization_id"):
            return jsonify({"error": "Forbidden"}), 403

        # Delete script directly from MySQL
        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
                cursor.execute("DELETE FROM scripts WHERE id = %s;", (script_id,))
                cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
            conn.commit()
        except Exception as e:
            logging.error(f"Failed to delete script {script_id} from MySQL: {e}")
            return jsonify({"error": "Database error during deletion"}), 500
        finally:
            if 'conn' in locals() and conn:
                conn.close()

    logging.info(f"Script deleted: {script_id} by user {session.get('user_id')}")
    admin = _current_user().get("username", "unknown")
    log_admin_action(admin, "Delete", "Scripts", script_id, ip_address=request.remote_addr)
    return jsonify({"success": True})

@app.route("/api/alerts")
@rate_limit(tier="standard")
@login_required
def api_alerts():
    alerts = filtered_alerts()
    agents = load_json(AGENTS_FILE)
    agent_map = {a.get("id"): a.get("hostname", a.get("id")) for a in agents}
    orgs = org_name_map()
    for a in alerts:
        a["agent_name"] = agent_map.get(a.get("agent_id"), a.get("agent_id"))
        a["organization_name"] = orgs.get(a.get("organization_id"), "")
    return jsonify(alerts)

@app.route("/api/alerts/<alert_id>", methods=["DELETE"])
@login_required
def api_delete_alert(alert_id):
    user = _current_user()
    if user.get("role") == "organization_viewer":
        return jsonify({"error": "Forbidden"}), 403

    alerts = load_json(ALERTS_FILE)
    alert = next((a for a in alerts if a["id"] == alert_id), None)
    if alert and not is_admin(user) and alert.get("organization_id") != user.get("organization_id"):
        return jsonify({"error": "Forbidden"}), 403

    # Delete alert directly from MySQL
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM batchhost_alerts WHERE id = %s;", (alert_id,))
        conn.commit()
    except Exception as e:
        logging.error(f"Failed to delete alert {alert_id} from MySQL: {e}")
        return jsonify({"error": "Database error during deletion"}), 500
    finally:
        if 'conn' in locals() and conn:
            conn.close()

    logging.info(f"Alert deleted: {alert_id} by user {session.get('user_id')}")
    admin = _current_user().get("username", "unknown")
    log_admin_action(admin, "Delete", "Alerts", alert_id, ip_address=request.remote_addr)
    return jsonify({"success": True})

@app.route("/api/logs/<script_id>")
@login_required
def api_logs(script_id):
    scripts = load_json(SCRIPTS_FILE)
    script = next((s for s in scripts if s["id"] == script_id), None)
    if not script:
        return jsonify({"error": "not found"}), 404
    if not ensure_record_access(script):
        return jsonify({"error": "Forbidden"}), 403
        
    agents = load_json(AGENTS_FILE)
    agent = next((a for a in agents if a.get("id") == script.get("agent_id")), {})
    hostname = agent.get("hostname", script.get("agent_id", ""))
    script_path = script.get("path", "")
    target_header = f"] [{hostname}] [{script_path}]"
    
    lines = []
    for log_file in sorted(os.listdir(LOG_DIR)):
        if log_file.endswith(".log"):
            with open(os.path.join(LOG_DIR, log_file), "r", errors="ignore") as f:
                capturing = False
                for line in f:
                    stripped = line.strip()
                    if not stripped:
                        continue
                        
                    is_header = False
                    if stripped.startswith("[") and stripped.endswith("]"):
                        first_close = stripped.find("]")
                        if first_close != -1:
                            ts_part = stripped[1:first_close]
                            try:
                                datetime.fromisoformat(ts_part)
                                rest = stripped[first_close+1:]
                                if rest.startswith(" [") and "] [" in rest:
                                    is_header = True
                            except ValueError:
                                pass
                                
                    if is_header:
                        if stripped.endswith(target_header):
                            capturing = True
                            lines.append(stripped)
                        else:
                            capturing = False
                    else:
                        if capturing:
                            lines.append(stripped)
    return jsonify({"logs": lines[-200:]})

@app.route("/api/backups")
@login_required
def api_backups():
    user = _current_user()
    if user.get("role") == "organization_viewer":
        return jsonify({"error": "Forbidden"}), 403
    
    backups = []
    if os.path.exists(BACKUP_DIR):
        orgs = load_json(ORGANIZATIONS_FILE)
        safe_name = ""
        if not is_admin(user):
            org = next((o for o in orgs if o.get("id") == user.get("organization_id")), None)
            if org:
                safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", org.get("name", org.get("id"))).strip("_") or org.get("id")
                
        for entry in sorted(os.listdir(BACKUP_DIR), reverse=True):
            if not is_admin(user) and safe_name not in entry:
                continue
            
            full_path = os.path.join(BACKUP_DIR, entry)
            if entry.endswith(".txt") and os.path.isfile(full_path):
                size = os.path.getsize(full_path)
                if "_1_Day_Backup_" in entry:
                    scope = "1 Day Backup"
                elif "_Date_Range_Backup_" in entry:
                    scope = "Date Range Backup"
                elif "_Global_Backup" in entry:
                    scope = "Global System Backup"
                elif "_Full_Org_Backup_" in entry or "_Full_Backup_" in entry:
                    scope = "Organization Backup"
                elif "_last24h_" in entry:
                    scope = "Last 24 hours"
                else:
                    scope = "Full backup"
                display_name = entry
                if "_last24h_" in entry:
                    display_name = re.sub(r"(_last24h_).+(?=\.txt$)", r"\1Daily_Backup", entry)
                backups.append({
                    "name": entry,
                    "display_name": display_name,
                    "date": display_name.replace(".txt", ""),
                    "size": size,
                    "scope": scope,
                    "size_human": f"{size/1024:.1f} KB" if size < 1024*1024 else f"{size/1024/1024:.1f} MB"
                })
    return jsonify(backups)

@app.route("/api/backups/schedule")
@admin_required
def api_backup_schedule():
    return jsonify({"enabled": False})

@app.route("/api/backups/<name>/download")
@login_required
def api_backup_download(name):
    user = _current_user()
    if user.get("role") == "organization_viewer":
        return jsonify({"error": "Forbidden"}), 403
        
    if not is_admin(user):
        orgs = load_json(ORGANIZATIONS_FILE)
        org = next((o for o in orgs if o.get("id") == user.get("organization_id")), None)
        if org:
            safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", org.get("name", org.get("id"))).strip("_") or org.get("id")
            if safe_name not in name:
                return jsonify({"error": "Forbidden"}), 403
                
    if ".." in name or "/" in name or "\\" in name:
        return jsonify({"error": "Invalid file path"}), 400
                
    path = os.path.join(BACKUP_DIR, name)
    if not os.path.exists(path):
        logging.warning(f"Attempt to download non-existent backup: {name} by user {session.get('user_id')}")
        return jsonify({"error": "not found"}), 404
    logging.info(f"Backup downloaded: {name} by user {session.get('user_id')}")
    return send_file(path, as_attachment=True)

@app.route("/api/backups/trigger", methods=["POST"])
@rate_limit(tier="critical")
@login_required
def api_backup_trigger():
    user = _current_user()
    if user.get("role") == "organization_viewer":
        return jsonify({"error": "Forbidden"}), 403
    try:
        data = request.get_json(silent=True) or {}
        if not is_admin(user):
            org_id = user.get("organization_id")
        else:
            # For super admins, if no org_id is specified in the payload or args, it will be a global backup (None)
            org_id = data.get("organization_id") or request.args.get("organization_id")
        scope = data.get("scope", "full")
        start_date = data.get("start_date")
        end_date = data.get("end_date")
        
        start_dt = None
        end_dt = None
        
        if scope in ["1_day", "date_range"]:
            if start_date:
                start_dt = datetime.fromisoformat(start_date)
            if end_date:
                end_dt = datetime.fromisoformat(end_date).replace(hour=23, minute=59, second=59)
                
        backup_path = create_organization_backup(org_id, scope=scope, start_dt=start_dt, end_dt=end_dt)
        backup_name = os.path.basename(backup_path)
        logging.info(f"Manual organization backup triggered: {backup_name} by user {session.get('user_id')}")
        admin = _current_user().get("username", "unknown")
        log_admin_action(admin, "Backup Trigger", "Backups", backup_name, ip_address=request.remote_addr)
        return jsonify({
            "success": True,
            "file": backup_name,
            "download_url": url_for("api_backup_download", name=backup_name)
        })
    except Exception as e:
        logging.error(f"Manual backup failed: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/system_logs")
@login_required
def api_system_logs():
    user = _current_user()
    agent_id = request.args.get("agent_id", "")
    script_path = request.args.get("script_path", "")
    system_only = request.args.get("system_only", "false") == "true"
    org_id = request.args.get("organization_id", "")
    
    allowed_agent_ids = None
    if not is_admin(user):
        allowed_agents = filtered_agents(user)
        allowed_agent_ids = {a.get("id") for a in allowed_agents}
        if system_only:
            return jsonify({"logs": []}) # Non-admins cannot see system logs
    elif org_id:
        agents = load_json(AGENTS_FILE)
        allowed_agent_ids = {a.get("id") for a in agents if a.get("organization_id") == org_id}
            
    lines = []
    
    # Read server log
    server_log = os.path.join(LOG_DIR, "server.log")
    if os.path.exists(server_log) and is_admin(user) and not org_id:
        with open(server_log, "r") as f:
            for line in f:
                if agent_id and agent_id not in line:
                    continue
                if script_path and script_path not in line:
                    continue
                lines.append(line.strip())
                
    # Read agent/script logs
    if not system_only:
        for log_file in sorted(os.listdir(LOG_DIR)):
            if log_file.endswith(".log") and log_file != "server.log":
                file_agent_id = log_file.split("_")[0]
                if allowed_agent_ids is not None and file_agent_id not in allowed_agent_ids:
                    continue
                    
                with open(os.path.join(LOG_DIR, log_file), "r") as f:
                    for line in f:
                        if agent_id and agent_id not in line and agent_id not in log_file:
                            continue
                        if script_path and script_path not in line:
                            continue
                        lines.append(line.strip())
                    
    # Return last 1000 lines max
    return jsonify({"logs": lines[-1000:]})

@app.route("/api/settings", methods=["GET"])
@admin_required
def api_get_settings():
    settings = load_json(os.path.join(DATA_DIR, "settings.json"), {})
    if "email" in settings and "smtp_pass" in settings["email"]:
        settings["email"]["smtp_pass"] = "••••••••"
    return jsonify(settings)

@app.route("/api/settings", methods=["POST"])
@admin_required
def api_save_settings():
    data = request.json or {}
    settings_path = os.path.join(DATA_DIR, "settings.json")
    existing = load_json(settings_path, {})
    if "email" in data:
        if data["email"].get("smtp_pass") == "••••••••":
            data["email"]["smtp_pass"] = existing.get("email", {}).get("smtp_pass", "")
        existing["email"] = data["email"]
    if "agent_alerts" in data:
        existing["agent_alerts"] = data["agent_alerts"]
    save_json(settings_path, existing)
    logging.info(f"Settings updated by user {session.get('user_id')}")
    admin = _current_user().get("username", "unknown")
    log_admin_action(admin, "Update", "Settings", "System Settings", ip_address=request.remote_addr)
    return jsonify({"success": True})

@app.route("/api/users")
@rate_limit(tier="standard")
@login_required
def api_users():
    current = _current_user()
    users = load_json(USERS_FILE)
    if current.get("role") == "organization_viewer":
        users = [u for u in users if u.get("id") == current.get("id")]
    elif not is_admin(current):
        users = [u for u in users if u.get("organization_id") == current.get("organization_id")]
    orgs = org_name_map()
    safe_users = []
    for u in users:
        row = {k: v for k, v in u.items() if k != "password"}
        row["organization_name"] = orgs.get(u.get("organization_id"), "")
        row["web_status"] = "active" if user_is_accessing_web(u.get("id")) else "inactive"
        safe_users.append(row)
    return jsonify(safe_users)

@app.route("/api/users", methods=["POST"])
@rate_limit(tier="critical")
@login_required
def api_create_user():
    current_usr = _current_user()
    if current_usr.get("role") == "organization_viewer":
        return jsonify({"error": "Forbidden"}), 403
    
    data = request.json or {}
    username = data.get("username", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "")
    if not is_admin(current_usr):
        org_id = current_usr.get("organization_id")
    else:
        org_id = data.get("organization_id")
        
    if not username or not email or not password or not org_id:
        return jsonify({"error": "username, email, password, and organization are required"}), 400
    organizations = load_json(ORGANIZATIONS_FILE)
    org = next((o for o in organizations if o.get("id") == org_id), None)
    if not org or org.get("status") != "active":
        return jsonify({"error": "Active organization required"}), 400
    users = load_json(USERS_FILE)
    if any(u.get("username", "").lower() == username.lower() for u in users):
        return jsonify({"error": "Username already exists"}), 409
    new_user = {
        "id": str(uuid.uuid4()),
        "username": username,
        "password": hash_pw(password),
        "role": "organization_viewer",
        "batchhost_role": "organization_viewer",
        "filebridge_role": "organization_viewer",
        "organization_id": org_id,
        "email": email,
        "status": "active",
        "last_login": None,
        "previous_login": None,
        "created_at": datetime.now().isoformat()
    }
    users.append(new_user)
    save_json(USERS_FILE, users)
    admin = _current_user().get("username", "unknown")
    log_admin_action(admin, "Add", "Users", username, new_value=email, ip_address=request.remote_addr)
    return jsonify({"success": True, "user": {k: v for k, v in new_user.items() if k != "password"}})

@app.route("/api/organizations")
@rate_limit(tier="standard")
@admin_required
def api_organizations():
    organizations = load_json(ORGANIZATIONS_FILE)
    users = load_json(USERS_FILE)
    agents = load_json(AGENTS_FILE)
    result = []
    for org in organizations:
        result.append({
            **org,
            "users_count": sum(1 for u in users if u.get("organization_id") == org.get("id")),
            "super_admins_count": sum(1 for u in users if u.get("role") == "super_admin" and u.get("organization_id") == org.get("id")),
            "agents_count": sum(1 for a in agents if a.get("organization_id") == org.get("id"))
        })
    return jsonify(result)

@app.route("/api/organizations", methods=["POST"])
@rate_limit(tier="critical")
@admin_required
def api_create_organization():
    data = request.json or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Organization name required"}), 400
    organizations = load_json(ORGANIZATIONS_FILE)
    if any(o.get("name", "").lower() == name.lower() for o in organizations):
        return jsonify({"error": "Organization already exists"}), 409
    org = {
        "id": str(uuid.uuid4()),
        "name": name,
        "status": "active",
        "is_default": False,
        "created_at": datetime.now().isoformat()
    }
    organizations.append(org)
    save_json(ORGANIZATIONS_FILE, organizations)
    admin = _current_user().get("username", "unknown")
    log_admin_action(admin, "Add", "Organizations", name, ip_address=request.remote_addr)
    return jsonify({"success": True, "organization": org})

@app.route("/api/organizations/<org_id>", methods=["PATCH"])
@admin_required
def api_update_organization(org_id):
    data = request.json or {}
    organizations = load_json(ORGANIZATIONS_FILE)
    org = next((o for o in organizations if o.get("id") == org_id), None)
    if not org:
        return jsonify({"error": "Organization not found"}), 404
    if "name" in data:
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "Organization name required"}), 400
        org["name"] = name
    if "status" in data:
        if data["status"] not in ["active", "disabled"]:
            return jsonify({"error": "Invalid status"}), 400
        org["status"] = data["status"]
    if "agent_ids" in data:
        if not isinstance(data["agent_ids"], list):
            return jsonify({"error": "agent_ids must be a list"}), 400
        requested_agent_ids = {str(agent_id) for agent_id in data["agent_ids"] if agent_id}
        agents = load_json(AGENTS_FILE)
        known_agent_ids = {a.get("id") for a in agents}
        missing_agent_ids = requested_agent_ids - known_agent_ids
        if missing_agent_ids:
            return jsonify({"error": "Agent not found"}), 400
        fallback_org_id = default_org_id()
        if fallback_org_id == org_id:
            fallback_org_id = next((o.get("id") for o in organizations if o.get("id") != org_id), org_id)
        scripts = load_json(SCRIPTS_FILE)
        alerts = load_json(ALERTS_FILE)
        for agent in agents:
            agent_id = agent.get("id")
            if agent_id in requested_agent_ids:
                assign_agent_to_organization(agent_id, org_id, agents, scripts, alerts)
            elif agent.get("organization_id") == org_id and fallback_org_id != org_id:
                assign_agent_to_organization(agent_id, fallback_org_id, agents, scripts, alerts)
        save_json(AGENTS_FILE, agents)
        save_json(SCRIPTS_FILE, scripts)
        save_json(ALERTS_FILE, alerts)
    save_json(ORGANIZATIONS_FILE, organizations)
    admin = _current_user().get("username", "unknown")
    log_admin_action(admin, "Update", "Organizations", org.get("name", org_id), new_value=str(data), ip_address=request.remote_addr)
    return jsonify({"success": True, "organization": org})

@app.route("/api/organizations/<org_id>", methods=["DELETE"])
@admin_required
def api_delete_organization(org_id):
    organizations = load_json(ORGANIZATIONS_FILE)

    org = next((o for o in organizations if o.get("id") == org_id), None)
    if not org:
        return jsonify({"success": False, "error": "Organization not found"}), 404

    # Prevent deleting default org
    if org.get("is_default"):
        return jsonify({"success": False, "error": "Cannot delete default organization"}), 400

    # Delete org and cascade to related records directly in MySQL
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
            # Remove agents belonging to this org
            cursor.execute("DELETE FROM batchhost_agents WHERE organization_id = %s;", (org_id,))
            # Remove scripts belonging to this org
            cursor.execute("DELETE FROM scripts WHERE organization_id = %s;", (org_id,))
            # Remove users belonging to this org
            cursor.execute("DELETE FROM users WHERE organization_id = %s;", (org_id,))
            # Finally remove the org itself
            cursor.execute("DELETE FROM organizations WHERE id = %s;", (org_id,))
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
        conn.commit()
    except Exception as e:
        logging.error(f"Failed to delete organization {org_id} from MySQL: {e}")
        return jsonify({"error": "Database error during deletion"}), 500
    finally:
        if 'conn' in locals() and conn:
            conn.close()

    admin = _current_user().get("username", "unknown")
    log_admin_action(admin, "Delete", "Organizations", org.get("name"), ip_address=request.remote_addr)

    return jsonify({"success": True})

@app.route("/api/users/<user_id>", methods=["PATCH"])
@login_required
def api_update_user(user_id):
    current_usr = _current_user()
    if current_usr.get("role") == "organization_viewer":
        return jsonify({"error": "Forbidden"}), 403
        
    data = request.json or {}
    users = load_json(USERS_FILE)
    user = next((u for u in users if u["id"] == user_id), None)
    if not user:
        logging.warning(f"Attempt to update non-existent user: {user_id} by user {session.get('user_id')}")
        return jsonify({"error": "not found"}), 404
        
    if not is_admin(current_usr):
        if user.get("organization_id") != current_usr.get("organization_id"):
            return jsonify({"error": "Forbidden"}), 403
        if "organization_id" in data:
            del data["organization_id"] # Org admin cannot change org_id
            
    # Strict check: Super Admin users must belong to the Global Organization and cannot be moved
    is_target_super_admin = (data.get("role", user.get("role")) == "super_admin")
    if is_target_super_admin and "organization_id" in data:
        requested_org_id = data.get("organization_id")
        if requested_org_id and requested_org_id != default_org_id():
            return jsonify({"error": "Super Admin users must belong to the Global Organization and cannot be moved to any other organization"}), 400

    if "username" in data:
        new_username = data["username"].strip()
        if new_username and new_username.lower() != user.get("username", "").lower():
            if any(u.get("username", "").lower() == new_username.lower() for u in users):
                return jsonify({"error": "Username already exists"}), 409
            user["username"] = new_username

    if "organization_id" in data and data.get("role", user.get("role")) != "super_admin":
        org_id = data.get("organization_id")
        if org_id:
            org = next((o for o in load_json(ORGANIZATIONS_FILE) if o.get("id") == org_id), None)
            if not org:
                return jsonify({"error": "Organization not found"}), 400
            user["organization_id"] = org_id
            
    VALID_ROLES = {"super_admin", "organization_admin", "organization_viewer"}
    if "role" in data:
        new_role = data["role"]
        if new_role not in VALID_ROLES:
            return jsonify({"error": "Invalid role specified"}), 400
        
        # Only super_admin can change roles
        if not is_admin(current_usr):
            return jsonify({"error": "Forbidden: Only Super Admin can change roles"}), 403
        user["role"] = new_role
        user["batchhost_role"] = new_role
        user["filebridge_role"] = new_role

    if user.get("role") == "super_admin":
        user["organization_id"] = default_org_id()

    if "status" in data:
        user["status"] = data["status"]

    if "password" in data and data["password"]:
        user["password"] = hash_pw(data["password"])
    save_json(USERS_FILE, users)
    logging.info(f"User updated: {user_id} by user {session.get('user_id')}")
    admin = _current_user().get("username", "unknown")
    safe_data = {k: v for k, v in data.items() if k != "password"}
    log_admin_action(admin, "Update", "Users", user.get("username", user_id), new_value=str(safe_data), ip_address=request.remote_addr)
    return jsonify({"success": True})

@app.route("/api/users/<user_id>", methods=["DELETE"])
@login_required
def api_delete_user(user_id):
    current_usr = _current_user()
    if current_usr.get("role") == "organization_viewer":
        return jsonify({"error": "Forbidden"}), 403

    if user_id == session.get("user_id"):
        logging.warning(f"User {session.get('user_id')} attempted to delete themselves")
        return jsonify({"error": "Cannot delete yourself"}), 400

    users = load_json(USERS_FILE)
    user_to_delete = next((u for u in users if u["id"] == user_id), None)
    if not user_to_delete:
        return jsonify({"error": "not found"}), 404

    if not is_admin(current_usr) and user_to_delete.get("organization_id") != current_usr.get("organization_id"):
        return jsonify({"error": "Forbidden"}), 403

    # Delete user directly from MySQL
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM users WHERE id = %s;", (user_id,))
        conn.commit()
    except Exception as e:
        logging.error(f"Failed to delete user {user_id} from MySQL: {e}")
        return jsonify({"error": "Database error during deletion"}), 500
    finally:
        if 'conn' in locals() and conn:
            conn.close()

    logging.info(f"User deleted: {user_id} by user {session.get('user_id')}")
    admin = _current_user().get("username", "unknown")
    log_admin_action(admin, "Delete", "Users", user_id, ip_address=request.remote_addr)
    return jsonify({"success": True})

@app.route("/api/admin_logs")
@rate_limit(tier="standard")
@admin_required
def api_admin_logs():
    return jsonify(load_json(ADMIN_LOGS_FILE))

@app.route("/api/admin_logs/clear", methods=["DELETE"])
@admin_required
def api_clear_admin_logs():
    save_json(ADMIN_LOGS_FILE, [])
    user_id = session.get("user_id")
    users = load_json(USERS_FILE)
    user = next((u for u in users if u["id"] == user_id), {})
    admin_username = user.get("username", "unknown")
    logging.info(f"Admin logs cleared by super admin {admin_username}")
    log_admin_action(admin_username, "Delete", "System", "Admin Logs", previous_value="All Logs", new_value="Cleared", ip_address=request.remote_addr, status="success")
    return jsonify({"success": True})

try:
    import eventlet.wsgi
    import ssl

    _original_process_request = eventlet.wsgi.Server.process_request

    def _patched_process_request(self, conn_state):
        try:
            _original_process_request(self, conn_state)
        except ssl.SSLError as e:
            if "CERTIFICATE_UNKNOWN" in str(e):
                pass
            elif getattr(e, "errno", None) == 1 or "SSLV3_ALERT_CERTIFICATE_UNKNOWN" in str(e):
                pass
            else:
                raise
        except Exception:
            raise

    eventlet.wsgi.Server.process_request = _patched_process_request
except Exception:
    pass

if __name__ == "__main__":
    logging.info("Starting BatchHost-Pro Server")
    cert_path = os.path.join(BASE_DIR, "cert.pem")
    key_path = os.path.join(BASE_DIR, "key.pem")

    ssl_context = None
    if os.path.exists(cert_path) and os.path.exists(key_path):
        ssl_context = (cert_path, key_path)
    else:
        try:
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.primitives import serialization
            
            key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
            )
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, u"localhost"),
            ])
            cert = x509.CertificateBuilder().subject_name(
                subject
            ).issuer_name(
                issuer
            ).public_key(
                key.public_key()
            ).serial_number(
                x509.random_serial_number()
            ).not_valid_before(
                datetime.utcnow()
            ).not_valid_after(
                datetime.utcnow() + timedelta(days=365)
            ).sign(key, hashes.SHA256())
            
            with open(key_path, "wb") as f:
                f.write(key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption(),
                ))
            with open(cert_path, "wb") as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))
            
            print("Self-signed SSL certificate generated.")
            ssl_context = (cert_path, key_path)
        except ImportError:
            print("Self-signed SSL certificate generated.")
            ssl_context = 'adhoc'

    debug_mode = os.environ.get("BATCHHOST_DEBUG", "False").lower() in ("true", "1")
    print("\nServer is running at: https://172.100.30.191:5000 (WSS Enabled)")
    if ssl_context and isinstance(ssl_context, tuple):
        cert_path, key_path = ssl_context
        socketio.run(app, host="0.0.0.0", port=5000, debug=debug_mode, ssl_context=(cert_path, key_path), allow_unsafe_werkzeug=True)
    else:
        socketio.run(app, host="0.0.0.0", port=5000, debug=debug_mode, allow_unsafe_werkzeug=True)