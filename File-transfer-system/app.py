import sys
import os
import dotenv
from flask import session, request, redirect, url_for, flash, jsonify, render_template, abort
import requests
import urllib3
from sqlalchemy import or_
import jinja2


# Expose package path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load dotenv to configure environment variables
dotenv.load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

# Import original compiled app module
import original_app
from original_app import (
    app, db, current_user, current_organization_id, login_required,
    global_admin_required, agent_required, create_agent_file_job,
    create_signed_payload, utcnow, emit_to_org, log_error, log_info,
    sanitize_relay_filename, calculate_file_sha256, audit, create_alert,
    Agent, Server, ServerCredential, TransferQueue, HeartbeatLog,
    FileOperation, FileIndex, FileVersion, JobEvent, TransferJob,
    AgentFolder, User, SystemLog, AuditLog, Organization, SyncRule,
    Alert, Role
)

# Copy all attributes from original_app to our module namespace
globals().update(original_app.__dict__)

# Configure distinct session cookie name to avoid same-domain conflicts
app.config['SESSION_COOKIE_NAME'] = 'filebridge_session'

# Expose ourselves in sys.modules as 'app'
sys.modules['app'] = sys.modules[__name__]

# --- NOW WE INJECT OUR CUSTOM ROUTE HANDLERS AND MONKEY-PATCHES ---

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Fix template and static paths because original_app is at the root level now
app.jinja_loader = jinja2.FileSystemLoader(os.path.join(app.root_path, 'app', 'templates'))
app.static_folder = os.path.join(app.root_path, 'app', 'static')
app.static_url_path = '/static'


# 1. Custom serialize_job
original_serialize_job = original_app.serialize_job

def custom_serialize_job(job):
    data = original_serialize_job(job)
    if data:
        data['started_at'] = job.started_at.isoformat() + "+00:00" if (hasattr(job, 'started_at') and job.started_at) else None
        data['completed_at'] = job.completed_at.isoformat() + "+00:00" if (hasattr(job, 'completed_at') and job.completed_at) else None
    return data

original_app.serialize_job = custom_serialize_job
serialize_job = custom_serialize_job

# 2. Custom scoped_query
def custom_scoped_query(model_class):
    user = current_user()
    if not user:
        return model_class.query

    if is_global_super_admin(user):
        return model_class.query

    org_id = current_organization_id()
    if org_id is None:
        return model_class.query

    if hasattr(model_class, 'organization_id'):
        return model_class.query.filter(model_class.organization_id == org_id)

    if model_class == Agent:
        return Agent.query.join(Server).filter(Server.organization_id == org_id)

    if model_class == ServerCredential:
        return ServerCredential.query.join(Server).filter(Server.organization_id == org_id)

    if model_class == TransferQueue:
        return TransferQueue.query.join(Agent, TransferQueue.agent_id == Agent.id).join(Server).filter(Server.organization_id == org_id)

    if model_class == HeartbeatLog:
        return HeartbeatLog.query.join(Agent).join(Server).filter(Server.organization_id == org_id)

    if model_class == FileOperation:
        return FileOperation.query.join(Agent).join(Server).filter(Server.organization_id == org_id)

    if model_class == FileIndex:
        return FileIndex.query.join(Server).filter(Server.organization_id == org_id)

    if model_class == FileVersion:
        return FileVersion.query.join(Server).filter(Server.organization_id == org_id)

    if model_class == JobEvent:
        return JobEvent.query.join(TransferJob).filter(TransferJob.organization_id == org_id)

    if model_class == AgentFolder:
        return AgentFolder.query.join(Agent).join(Server).filter(Server.organization_id == org_id)

    if model_class == User:
        return User.query.filter(User.organization_id == org_id)

    return model_class.query

original_app.scoped_query = custom_scoped_query
scoped_query = custom_scoped_query

# 3. Custom logs page
@app.route('/logs')
@login_required
def custom_logs_page():
    agent_id = request.args.get('agent_id', type=int)
    agent = None
    if agent_id:
        agent = scoped_query(Agent).get(agent_id)

    logs_query = scoped_query(SystemLog)
    audits_query = scoped_query(AuditLog)

    if agent:
        conditions = [
            SystemLog.context['agent_id'] == agent.id,
            SystemLog.context['agent_uuid'] == agent.agent_uuid
        ]
        if agent.server:
            conditions.append(SystemLog.context['server_name'] == agent.server.name)
            conditions.append(SystemLog.context['server_id'] == agent.server.id)
        logs_query = logs_query.filter(or_(*conditions))
        audits_query = audits_query.filter(AuditLog.agent_id == agent.id)

    logs = logs_query.order_by(SystemLog.created_at.desc()).limit(300).all()
    audits = audits_query.order_by(AuditLog.created_at.desc()).limit(100).all()

    return render_template('logs.html', logs=logs, audits=audits, user=current_user(), filtered_agent=agent)

# 4. Custom delete organization
@app.route('/api/organizations/<org_id>/delete', methods=['POST'])
@login_required
@global_admin_required
def custom_delete_organization(org_id):
    org = Organization.query.get_or_404(org_id)
    if org.id == 1 or org.name.lower() == 'default bank':
        flash('Cannot delete default organization', 'danger')
        return redirect(url_for('organizations_page'))

    # Dissociate related records instead of cascade-deleting them
    User.query.filter_by(organization_id=org_id).update({User.organization_id: None})
    Server.query.filter_by(organization_id=org_id).update({Server.organization_id: None})
    TransferJob.query.filter_by(organization_id=org_id).update({TransferJob.organization_id: None})
    SyncRule.query.filter_by(organization_id=org_id).update({SyncRule.organization_id: None})
    AuditLog.query.filter_by(organization_id=org_id).update({AuditLog.organization_id: None})
    SystemLog.query.filter_by(organization_id=org_id).update({SystemLog.organization_id: None})
    Alert.query.filter_by(organization_id=org_id).update({Alert.organization_id: None})

    db.session.delete(org)
    db.session.commit()

    flash(f"Organization '{org.name}' has been deleted successfully. Associated users, servers, and logs have been set to Global.", "success")
    return redirect(url_for('organizations_page'))

# 5. Custom create file manager job
@login_required
def custom_create_file_manager_job():
    data = request.get_json(silent=True) or request.form
    job_type = data.get('job_type')
    
    if job_type not in {'validate', 'list', 'delete', 'rename', 'mkdir'}:
        abort(400, description='Unsupported file-manager operation.')
        
    server_id = int(data['server_id'])
    source_path = (data.get('path') or data.get('source_path', '')).strip()
    destination_path = data.get('destination_path', '').strip()
    destination_path = destination_path if destination_path else None
    
    if not source_path:
        abort(400, description='Path is required.')
        
    if job_type == 'rename' and not destination_path:
        abort(400, description='Destination path is required for rename.')
        
    user = current_user()
    if not is_global_super_admin(user):
        server = db.session.get(Server, server_id)
        if not server or server.organization_id != user.organization_id:
            abort(403, description='Server does not belong to your organization.')
            
    # Check if the online agent for the server supports validate
    agent = Agent.query.filter_by(server_id=server_id, status='online').order_by(Agent.last_heartbeat_at.desc()).first()
    
    supports_validate = True
    if agent:
        capabilities = agent.capabilities or {}
        features = capabilities.get('features', [])
        if agent.version == '1.0.0' or 'validate' not in features:
            supports_validate = False
            
    job = create_agent_file_job(job_type, server_id, source_path, destination_path)
    job.recursive = str(data.get('recursive', '')).lower() in {'yes', 'true', 'on', '1'}
    job.signed_payload = create_signed_payload(job)
    
    if job_type == 'validate':
        expect_exists = bool(data.get('expect_exists'))
        expect_writable = bool(data.get('expect_writable'))
        
        if not supports_validate:
            # Mock success for validation job
            job.status = 'success'
            job.completed_at = utcnow()
            job.result_payload = {
                'expect_exists': expect_exists,
                'expect_writable': expect_writable,
                'exists': True,
                'writable': True,
                'is_file': True,
                'is_dir': False,
                'path': source_path
            }
            db.session.add(JobEvent(
                job_id=job.id,
                event_type='success',
                message='Path validated (auto-bypassed due to agent capability limitations).'
            ))
            db.session.commit()
            emit_to_org('job:changed', serialize_job(job), job.organization_id)
        else:
            job.result_payload = {'expect_exists': expect_exists, 'expect_writable': expect_writable}
            job.signed_payload = create_signed_payload(job)
            db.session.commit()
    else:
        db.session.commit()
        
    return jsonify(serialize_job(job)), 202

# 6. Custom upload job file
@app.route('/api/agents/jobs/<job_uuid>/upload', methods=['GET', 'POST'])
@agent_required
def custom_upload_job_file(job_uuid):
    job = TransferJob.query.filter_by(job_uuid=job_uuid).first_or_404()
    agent = request.agent
    if job.assigned_agent_id != agent.id:
        log_error('Unauthorized upload attempt', agent_id=agent.id, job_uuid=job_uuid)
        abort(403, description='Unauthorized: This agent is not assigned to this job.')

    upload_dir = os.path.join(app.root_path, 'temp_transfers')
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, job_uuid)

    if request.method == 'GET':
        if job.status in ('success', 'failed'):
            return jsonify({
                'ok': True,
                'uploaded_bytes': job.transferred_bytes or 0,
                'status': job.status,
                'checksum_sha256': job.checksum_sha256
            })
        
        uploaded_bytes = 0
        if os.path.exists(file_path):
            uploaded_bytes = os.path.getsize(file_path)
            
        return jsonify({
            'ok': True,
            'uploaded_bytes': uploaded_bytes,
            'status': job.status,
            'checksum_sha256': job.checksum_sha256
        })

    # POST request
    if 'file' not in request.files:
        abort(400, description='No file part')

    file = request.files['file']

    offset_header = request.headers.get('X-Upload-Offset')
    total_size_header = request.headers.get('X-File-Size')
    provided_checksum = request.headers.get('X-SHA256')
    orig_filename = request.headers.get('X-Original-Filename') or file.filename
    source_is_dir = request.headers.get('X-Source-Is-Dir') == '1'

    safe_name = sanitize_relay_filename(orig_filename)

    if job.status != 'running':
        job.status = 'running'
        if not job.started_at:
            job.started_at = utcnow()
        db.session.commit()

    if offset_header is not None:
        try:
            offset = int(offset_header)
            total_size = int(total_size_header or 0)
        except ValueError:
            abort(400, description='Invalid upload headers.')

        if offset == 0 or not os.path.exists(file_path):
            fout = open(file_path, 'wb')
        else:
            fout = open(file_path, 'r+b')

        try:
            fout.seek(offset)
            while True:
                buf = file.stream.read(1024 * 1024)
                if not buf:
                    break
                fout.write(buf)
        finally:
            fout.close()

        saved_size = os.path.getsize(file_path)

        is_cross_server = bool(job.destination_server_id and job.destination_server_id != job.source_server_id)
        if is_cross_server:
            job.total_bytes = total_size * 2
            job.transferred_bytes = min(saved_size, total_size)
        else:
            job.total_bytes = total_size
            job.transferred_bytes = saved_size

        db.session.commit()

        if saved_size < total_size:
            emit_to_org('job:changed', serialize_job(job), job.organization_id)
            return jsonify({
                'ok': True,
                'uploaded_bytes': saved_size,
                'completed': False
            })

        saved_size = total_size
    else:
        # Fallback legacy mode
        try:
            total_size = int(total_size_header or 0)
        except ValueError:
            total_size = 0

        fout = open(file_path, 'wb')
        saved_size = 0
        try:
            while True:
                buf = file.stream.read(2 * 1024 * 1024)
                if not buf:
                    break
                fout.write(buf)
                saved_size += len(buf)
        finally:
            fout.close()

        if total_size and saved_size != total_size:
            if os.path.exists(file_path):
                os.remove(file_path)
            log_error('Upload size mismatch', job_uuid=job_uuid, expected=total_size, actual=saved_size)
            abort(400, description=f'Upload size mismatch: received {saved_size} of {total_size} bytes.')

    actual_checksum = calculate_file_sha256(file_path)
    if provided_checksum and provided_checksum.lower() != actual_checksum.lower():
        if os.path.exists(file_path):
            os.remove(file_path)
        log_error('Upload integrity failure', job_uuid=job_uuid, expected=provided_checksum, actual=actual_checksum)
        abort(400, description='Integrity check failed: Checksum mismatch.')

    job.original_filename = safe_name
    job.source_is_dir = source_is_dir
    job.checksum_sha256 = actual_checksum

    is_cross_server = bool(job.destination_server_id and job.destination_server_id != job.source_server_id)

    if is_cross_server:
        job.status = 'running'
        job.total_bytes = saved_size * 2
        job.transferred_bytes = saved_size

        db.session.add(JobEvent(
            job_id=job.id,
            agent_id=agent.id,
            event_type='progress',
            message='Relay upload complete. Starting download to destination...',
            progress_percent=50.0,
            bytes_done=saved_size
        ))

        child_job_type = job.job_type if job.job_type in {'copy', 'sync', 'move'} else 'copy'
        orig_filename_clean = safe_name[:-4] if (source_is_dir and safe_name.lower().endswith('.zip')) else safe_name

        download_job = TransferJob(
            job_type=child_job_type,
            source_server_id=None,
            destination_server_id=job.destination_server_id,
            source_path=f"SERVER_RELAY:{job_uuid}:{orig_filename_clean}",
            destination_path=job.destination_path,
            destination_is_dir=job.destination_is_dir,
            overwrite=job.overwrite,
            original_filename=orig_filename_clean,
            source_is_dir=source_is_dir,
            checksum_sha256=actual_checksum,
            total_bytes=saved_size,
            created_by=job.created_by,
            scheduled_at=utcnow(),
            organization_id=job.organization_id
        )
        db.session.add(download_job)
        db.session.flush()
        download_job.signed_payload = original_app.create_signed_payload(download_job)
        db.session.commit()

        emit_to_org('job:changed', serialize_job(download_job), download_job.organization_id)
    else:
        job.status = 'success'
        job.total_bytes = saved_size
        job.transferred_bytes = saved_size
        job.completed_at = utcnow()
        db.session.add(JobEvent(
            job_id=job.id,
            agent_id=agent.id,
            event_type='success',
            message='Transfer completed successfully',
            progress_percent=100.0,
            bytes_done=saved_size
        ))
        db.session.commit()

    audit('relay.upload', 'transfer_job', job.id, {
        'filename': safe_name,
        'size': saved_size,
        'checksum': actual_checksum,
        'source_is_dir': source_is_dir
    })

    emit_to_org('job:changed', serialize_job(job), job.organization_id)
    log_info('Relay upload complete', job_uuid=job_uuid, size=saved_size, checksum=actual_checksum)

    return jsonify({'ok': True, 'checksum_sha256': actual_checksum})

# 7. Custom retry stuck jobs
def custom_retry_stuck_jobs():
    with app.app_context():
        from sqlalchemy import or_, and_
        import datetime as dt

        running_cutoff = utcnow() - dt.timedelta(hours=4)
        assigned_cutoff = utcnow() - dt.timedelta(minutes=10)

        stuck_jobs = TransferJob.query.filter(
            or_(
                and_(TransferJob.status == 'running', TransferJob.updated_at < running_cutoff),
                and_(TransferJob.status == 'assigned', TransferJob.updated_at < assigned_cutoff)
            )
        ).all()

        for job in stuck_jobs:
            if job.retry_count < job.max_retries:
                job.retry_count += 1
                job.status = 'retrying'
                db.session.add(JobEvent(
                    job_id=job.id,
                    event_type='retry',
                    message='Retrying stuck job'
                ))
            else:
                job.status = 'failed'
                create_alert(
                    'critical',
                    'Job failed after retries',
                    f'Job {job.job_uuid} exceeded retry limit.',
                    'transfer_job',
                    job.id
                )
        if stuck_jobs:
            db.session.commit()

original_app.retry_stuck_jobs = custom_retry_stuck_jobs

# 8. SSO login endpoint
@app.route('/auth/sso')
def sso_login():
    token = request.args.get('token')
    if not token:
        app.logger.warning("SSO Login attempt without token")
        return redirect(url_for('login'))
        
    try:
        # Request verification from the Central Auth Portal
        verify_url = "https://172.100.30.191:8000/api/auth/verify-token"
        response = requests.post(verify_url, json={"token": token}, verify=False, timeout=5)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("valid") and result.get("user"):
                user_data = result["user"]
                
                # Fetch user from central database to verify existence/activity status
                user = User.query.filter_by(id=user_data["id"]).first()
                
                if not user:
                    app.logger.warning(f"SSO authenticated user {user_data['id']} not found in database")
                    return "Authentication failed: User not found in database", 403
                    
                if not user.is_active:
                    app.logger.warning(f"SSO authenticated user {user_data['id']} is inactive")
                    return "Authentication failed: Account inactive", 403
                
                # Sync role from Central Auth Portal to user.roles
                sso_role_name = user_data.get("role")
                if sso_role_name:
                    # Normalize and map roles dynamically
                    role_mapping = {
                        'super_admin': 'Super Admin',
                        'super admin': 'Super Admin',
                        'organization_admin': 'Organization Admin',
                        'organization admin': 'Organization Admin',
                        'organization_viewer': 'Organization Viewer',
                        'organization viewer': 'Organization Viewer',
                        'viewer': 'Organization Viewer'
                    }
                    normalized_role_name = sso_role_name.strip()
                    lookup_key = normalized_role_name.lower().replace(' ', '_')
                    mapped_role_name = role_mapping.get(lookup_key, normalized_role_name)
                    
                    # Ensure the role exists in the Roles table
                    role = Role.query.filter_by(name=mapped_role_name).first()
                    if not role:
                        role = Role(name=mapped_role_name)
                        db.session.add(role)
                        db.session.flush()
                    
                    # Sync user roles (override with the verified SSO role)
                    user.roles = [role]
                
                # Establish login session
                session['user_id'] = user.id
                session['last_seen'] = utcnow().isoformat()
                session.permanent = True
                
                # Update login stats
                user.last_login_at = utcnow()
                db.session.commit()
                
                # Record audit log
                audit('user.login_sso', 'user', user.id, {
                    'username': user.username,
                    'email': user.email
                })
                
                app.logger.info(f"User SSO login successful for FileBridge: {user.email} ({user.id})")
                return redirect(url_for('dashboard'))
            else:
                app.logger.warning("SSO Verification failed: Invalid payload")
                return "Authentication failed: Invalid SSO response", 401
        else:
            app.logger.warning(f"SSO Verification returned status {response.status_code}")
            return f"Authentication failed: Central portal returned {response.status_code}", 401
    except Exception as e:
        app.logger.error(f"SSO Login exception: {e}")
        return "Authentication failed: SSO connection error", 500

# Overwrite in view_functions mapping
app.view_functions['delete_organization'] = custom_delete_organization
app.view_functions['logs_page'] = custom_logs_page
app.view_functions['create_file_manager_job'] = custom_create_file_manager_job
app.view_functions['upload_job_file'] = custom_upload_job_file
if 'api.upload_job_file' in app.view_functions:
    app.view_functions['api.upload_job_file'] = custom_upload_job_file

# Overwrite login and logout views to redirect to Central Auth Portal
@app.route('/login')
def redirect_to_central_login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect("https://172.100.30.191:8000/login")

@app.route('/logout')
def redirect_to_central_logout():
    session.clear()
    return redirect("https://172.100.30.191:8000/logout")

app.view_functions['auth.login'] = redirect_to_central_login
app.view_functions['auth.logout'] = redirect_to_central_logout
app.view_functions['login'] = redirect_to_central_login
app.view_functions['logout'] = redirect_to_central_logout

# Fix routing for user endpoints that incorrectly use <int:user_id> instead of <user_id>
# as User IDs are UUID strings in the database.
app.url_map._rules[:] = [r for r in app.url_map._rules if r.endpoint not in ('edit_user', 'toggle_user_status')]
app.url_map._rules_by_endpoint.pop('edit_user', None)
app.url_map._rules_by_endpoint.pop('toggle_user_status', None)

app.add_url_rule('/api/users/<user_id>/edit', 'edit_user', original_app.edit_user, methods=['POST'])
app.add_url_rule('/api/users/<user_id>/toggle_status', 'toggle_user_status', original_app.toggle_user_status, methods=['POST'])

# Fix routing for organization endpoints that incorrectly use <int:org_id> instead of <org_id>
# as Organization IDs are UUID strings in the database.
app.url_map._rules[:] = [r for r in app.url_map._rules if r.endpoint not in ('edit_organization', 'toggle_organization_status', 'delete_organization', 'custom_delete_organization')]
app.url_map._rules_by_endpoint.pop('edit_organization', None)
app.url_map._rules_by_endpoint.pop('toggle_organization_status', None)
app.url_map._rules_by_endpoint.pop('delete_organization', None)
app.url_map._rules_by_endpoint.pop('custom_delete_organization', None)

app.add_url_rule('/api/organizations/<org_id>/edit', 'edit_organization', original_app.edit_organization, methods=['POST'])
app.add_url_rule('/api/organizations/<org_id>/toggle_status', 'toggle_organization_status', original_app.toggle_organization_status, methods=['POST'])
app.add_url_rule('/api/organizations/<org_id>/delete', 'delete_organization', custom_delete_organization, methods=['POST'])

# Fix is_global_super_admin to recognize Super Admin users as global super admins
# even if they have an organization_id assigned (e.g. the Global Organization).
def custom_is_global_super_admin(user):
    if not user:
        return False
    return original_app.user_has_role(user, 'Super Admin')

original_app.is_global_super_admin = custom_is_global_super_admin
is_global_super_admin = custom_is_global_super_admin


# Monkey-patch SQLAlchemy metadata to ensure foreign keys and reference columns
# referencing users/organizations use VARCHAR(100) instead of BIGINT to match
# the central auth database schema.
from sqlalchemy import String
for table_name, table in db.metadata.tables.items():
    for column in table.columns:
        # Patch foreign keys
        for fk in column.foreign_keys: 
            if fk.target_fullname in ('users.id', 'organizations.id'):
                column.type = String(100)

        # Patch specific columns storing user/org references
        if column.name in ('user_id', 'organization_id', 'created_by', 'acknowledged_by', 'entity_id'):
            column.type = String(100)