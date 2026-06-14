import os
import json
import uuid
import time
import hashlib
import pymysql
from datetime import datetime
from flask import Flask, request, jsonify, render_template, session, redirect, url_for

app = Flask(__name__)
app.secret_key = "central-portal-secure-session-secret-key-2026"
app.config['SESSION_COOKIE_NAME'] = 'central_auth_session'

# Central memory storage for short-lived, one-use launch tokens (30s TTL)
ACTIVE_LAUNCH_TOKENS = {}

PORTAL_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(PORTAL_DIR)
SYSTEMS_FILE = os.path.join(PORTAL_DIR, "data", "systems.json")

def get_db_connection():
    return pymysql.connect(
        host='localhost',
        user='root',
        password='List@123',
        database='central_multitenant',
        port=3306,
        cursorclass=pymysql.cursors.DictCursor
    )

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

def get_systems_config():
    if os.path.exists(SYSTEMS_FILE):
        with open(SYSTEMS_FILE, 'r') as f:
            return json.load(f)
    return {}

def ensure_system_running(system_key):
    import sys
    if sys.platform != 'win32':
        return  # Let systemd handle service lifecycles on Linux!
        
    import socket
    import subprocess
    
    ports = {
        'batchhost': 5000,
        'filebridge': 5001
    }
    
    cwd = os.path.join(BASE_DIR, "BatchHost-Pro") if system_key == 'batchhost' else os.path.join(BASE_DIR, "File-transfer-system")
    port = ports.get(system_key)
    if not port:
        return
        
    # Low-overhead check to see if port is already active
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        is_running = s.connect_ex(('127.0.0.1', port)) == 0
        
    if not is_running:
        app.logger.info(f"[Auto-Launch] System '{system_key}' is not running on port {port}. Spawning in background...")
        try:
            is_win = sys.platform == "win32"
            popen_kwargs = {"cwd": cwd}
            if is_win:
                popen_kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
                
            if system_key == 'batchhost':
                subprocess.Popen(
                    [sys.executable, "server.py"],
                    **popen_kwargs
                )
            elif system_key == 'filebridge':
                python_bin = ["py", "-3.13"] if is_win else [sys.executable]
                if not is_win:
                    venv_py = os.path.join(cwd, ".venv", "bin", "python")
                    if os.path.exists(venv_py):
                        python_bin = [venv_py]
                    else:
                        venv_py_2 = os.path.join(cwd, "venv", "bin", "python")
                        if os.path.exists(venv_py_2):
                            python_bin = [venv_py_2]
                        else:
                            python_bin = ["python3.13"]
                subprocess.Popen(
                    python_bin + ["run.py"],
                    **popen_kwargs
                )
            app.logger.info(f"[Auto-Launch] Background process for '{system_key}' spawned successfully.")
        except Exception as e:
            app.logger.error(f"[Auto-Launch] Failed to spawn background process for '{system_key}': {e}")

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

# ─── HTTP ROUTES ─────────────────────────────────────────────────────────────

@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route("/")
@app.route("/login")
def login_page():
    if 'user_id' in session:
        session.clear()
    return render_template("portal.html")

@app.route("/select")
@login_required
def select_page():
    systems = get_systems_config()
    
    # Filter systems based on user role and org access (if desired)
    # Right now, all users have access to both systems as configured.
    # We will pass the user data into the template
    user_payload = {
        "name": session.get('username'),
        "batchhost_role": session.get('batchhost_role'),
        "batchhost_role_name": "Super Admin" if session.get('batchhost_role') in ('super_admin', 'Super Admin') else ("Org Admin" if session.get('batchhost_role') in ('organization_admin', 'Organization Admin') else "Viewer"),
        "filebridge_role": session.get('filebridge_role'),
        "filebridge_role_name": "Super Admin" if session.get('filebridge_role') in ('super_admin', 'Super Admin') else ("Org Admin" if session.get('filebridge_role') in ('organization_admin', 'Organization Admin') else "Viewer"),
        "organization": session.get('organization_name', 'Global')
    }
    
    return render_template("select.html", systems=systems, user=user_payload, systems_js=json.dumps(systems))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login_page'))

# ─── API ENDPOINTS ────────────────────────────────────────────────────────────

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    data = request.json or {}
    email = data.get('email', '').strip()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'success': False, 'message': 'Please enter email and password'}), 400

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Query user from central MySQL database
            cursor.execute("SELECT * FROM users WHERE email = %s AND status = 'active';", (email,))
            user = cursor.fetchone()
            
            if not user or not verify_pw(user['password'], password):
                return jsonify({'success': False, 'message': 'Invalid credentials'}), 401
                
            # Load organization name
            cursor.execute("SELECT name FROM organizations WHERE id = %s;", (user['organization_id'],))
            org = cursor.fetchone()
            org_name = org['name'] if org else 'Global Organization'
            
            # Establish session variables
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['email'] = user['email']
            session['batchhost_role'] = user['batchhost_role']
            session['filebridge_role'] = user['filebridge_role']
            session['organization_id'] = user['organization_id']
            session['organization_name'] = org_name
            
            # Update total logins
            cursor.execute("UPDATE users SET total_logins = total_logins + 1, last_login = %s, previous_login = %s WHERE id = %s;", 
                           (datetime.now(), user.get('last_login'), user['id']))
            conn.commit()
            
        return jsonify({
            'success': True,
            'redirect': '/select'
        })
    except Exception as e:
        app.logger.error(f"Login failed: {e}")
        return jsonify({'success': False, 'message': 'System error occurred during login'}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/auth/launch', methods=['POST'])
@login_required
def auth_launch():
    data = request.json or {}
    system_key = data.get('system')
    
    # Ensure the target system is actually running
    if system_key:
        ensure_system_running(system_key)
        
    systems = get_systems_config()
    
    if not system_key or system_key not in systems:
        return jsonify({'success': False, 'message': 'Invalid target system'}), 400

    system_config = systems[system_key]
    
    # Generate a short-lived, one-use token
    token = str(uuid.uuid4())
    expires_at = time.time() + 30.0  # 30 seconds TTL
    
    system_role = session['batchhost_role'] if system_key == 'batchhost' else session['filebridge_role']
    
    # Map roles to Filebridge's expected format if needed
    if system_key == 'filebridge':
        if system_role in ('super_admin', 'Super Admin'):
            system_role = 'Super Admin'
        elif system_role in ('organization_admin', 'Organization Admin'):
            system_role = 'Organization Admin'
        elif system_role in ('organization_viewer', 'viewer', 'Viewer', 'Organization Viewer'):
            system_role = 'Organization Viewer'

    ACTIVE_LAUNCH_TOKENS[token] = {
        "user": {
            "id": session['user_id'],
            "username": session['username'],
            "email": session['email'],
            "role": system_role,
            "organization_id": session['organization_id'],
            "organization_name": session['organization_name']
        },
        "system": system_key,
        "expires_at": expires_at
    }
    
    # Return launch URL
    launch_url = f"{system_config['base_url']}/auth/sso?token={token}"
    return jsonify({
        'success': True,
        'launch_url': launch_url
    })

@app.route('/api/auth/verify-token', methods=['POST'])
def verify_token():
    data = request.json or {}
    token = data.get('token')
    
    if not token or token not in ACTIVE_LAUNCH_TOKENS:
        return jsonify({'valid': False, 'message': 'Invalid or expired launch token'}), 401
        
    token_payload = ACTIVE_LAUNCH_TOKENS.pop(token) # One-use (consumed immediately)
    
    if time.time() > token_payload['expires_at']:
        return jsonify({'valid': False, 'message': 'Token has expired'}), 401
        
    return jsonify({
        'valid': True,
        'user': token_payload['user']
    })

# Serve images directly from central auth
@app.route("/images/<path:filename>")
def serve_image(filename):
    from flask import send_from_directory
    # Read from BatchHost-Pro's images directory
    images_dir = os.path.join(BASE_DIR, "BatchHost-Pro", "images")
    return send_from_directory(images_dir, filename)

if __name__ == "__main__":
    ensure_system_running('batchhost')
    ensure_system_running('filebridge')
    
    cert_path = os.path.join(BASE_DIR, "BatchHost-Pro", "cert.pem")
    key_path = os.path.join(BASE_DIR, "BatchHost-Pro", "key.pem")
    
    ssl_context = None
    if os.path.exists(cert_path) and os.path.exists(key_path):
        ssl_context = (cert_path, key_path)
    else:
        ssl_context = 'adhoc'
        
    print("Starting Central Auth Portal on https://172.100.30.191:8000")
    if ssl_context and isinstance(ssl_context, tuple):
        app.run(host="172.100.30.191", port=8000, ssl_context=ssl_context, debug=True)
    else:
        app.run(host="172.100.30.191", port=8000, debug=True)
