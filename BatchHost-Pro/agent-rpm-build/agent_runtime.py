#!/usr/bin/env python3
"""BatchHost-Pro event-driven agent runtime (v2 - Execution Orchestration Engine).

Use this runtime to execute scripts under PID/session tracking:

    python agent_runtime.py daemon
    python agent_runtime.py run C:\\BatchScripts\\job.bat
"""

from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path
import platform
import uuid
import time
import json
import ssl
import urllib.request
import urllib.error
import logging
import socket
import threading
import psutil
import subprocess
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime


# ==========================================
# models.py
# ==========================================
@dataclass
class ExecutionEvent:
    event_type: str
    timestamp: str
    details: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ManagedExecution:
    execution_id: str
    script_id: str
    agent_id: str
    script_path: str
    script_args: List[str] = field(default_factory=list)
    root_pid: Optional[int] = None
    child_pids: List[int] = field(default_factory=list)
    execution_state: str = 'QUEUED'
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    last_heartbeat: Optional[str] = None
    last_stdout_activity: Optional[str] = None
    last_stderr_activity: Optional[str] = None
    timeout_seconds: int = 90
    exit_code: Optional[int] = None
    failure_reason: Optional[str] = None
    termination_reason: Optional[str] = None
    resource_usage: Dict[str, float] = field(default_factory=lambda: {'cpu': 0.0, 'memory': 0.0})
    retry_count: int = 0
    watchdog_status: str = 'HEALTHY'
    execution_events: List[ExecutionEvent] = field(default_factory=list)
    
    def to_dict(self):
        return {
            'execution_id': self.execution_id,
            'script_id': self.script_id,
            'agent_id': self.agent_id,
            'script_path': self.script_path,
            'script_args': self.script_args,
            'root_pid': self.root_pid,
            'child_pids': self.child_pids,
            'execution_state': self.execution_state,
            'started_at': self.started_at,
            'ended_at': self.ended_at,
            'last_heartbeat': self.last_heartbeat,
            'timeout_seconds': self.timeout_seconds,
            'exit_code': self.exit_code,
            'failure_reason': self.failure_reason,
            'termination_reason': self.termination_reason,
            'resource_usage': self.resource_usage,
            'watchdog_status': self.watchdog_status
        }

# ==========================================
# state.py (States of scripts added)
# ==========================================
class StateResolver:
    VALID_TRANSITIONS = {
        'QUEUED': ['STARTING', 'FAILED', 'TERMINATED'],
        'STARTING': ['RUNNING', 'FAILED', 'CRASHED', 'TERMINATED'],
        'RUNNING': ['COMPLETED', 'FAILED', 'TERMINATED', 'FORCE_KILLED', 'TIMEOUT', 'CRASHED', 'STALLED', 'UNKNOWN'],
        'STALLED': ['RUNNING', 'FAILED', 'TERMINATED', 'FORCE_KILLED', 'TIMEOUT'],
        'UNKNOWN': ['RUNNING', 'COMPLETED', 'FAILED', 'TERMINATED', 'FORCE_KILLED', 'TIMEOUT'],
    }
    
    @staticmethod
    def can_transition(current: str, target: str) -> bool:
        if current == target:
            return True
        allowed = StateResolver.VALID_TRANSITIONS.get(current, [])
        return target in allowed

    @staticmethod
    def resolve_exit_status(exit_code: int) -> str:
        if exit_code == 0:
            return 'COMPLETED'
        if exit_code is None:
            return 'UNKNOWN'
        if exit_code < 0:
            return 'FORCE_KILLED'
        return 'FAILED'

# ==========================================
# api.py (API tracking & working)
# ==========================================
class ApiSyncLayer:
    def __init__(self, server_url, token=None, registration_secret=None):
        self.server_url = server_url.rstrip('/')
        self.token = token
        self.registration_secret = registration_secret
        self.logger = logging.getLogger('ApiSyncLayer')

    def set_token(self, token):
        self.token = token

    def register(self, agent_id):
        payload = {
            'agent_id': agent_id,
            'hostname': socket.gethostname(),
            'os_type': platform.system().lower(),
            'device_key': platform.node() or agent_id,
            'registration_secret': self.registration_secret or ''
        }
        res = self._post('/api/agent/register', payload)
        if res and res.get('token'):
            self.token = res.get('token')
        return res

    def sync_event(self, event_payload):
        return self._post('/api/agent/script-event', event_payload)

    def heartbeat(self, payload):
        return self._post('/api/agent/heartbeat', payload)

    def _post(self, path, payload, timeout=10):
        body = json.dumps(payload).encode('utf-8')
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['X-Agent-Token'] = self.token
        if self.registration_secret:
            headers['X-Registration-Secret'] = self.registration_secret
            
        req = urllib.request.Request(
            self.server_url + path,
            data=body,
            headers=headers,
            method='POST',
        )
        context = ssl._create_unverified_context()
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
                raw = response.read().decode('utf-8')
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            self.logger.error(f'API Sync failed for {path}: {e}')
            if e.code in (401, 403):
                return {"error": "unauthorized", "status_code": e.code}
            return None
        except Exception as e:
            self.logger.error(f'API Sync failed for {path}: {e}')
            return None

# ==========================================
# process.py
# ==========================================
class ProcessTreeManager:
    def __init__(self):
        self.logger = logging.getLogger('ProcessTreeManager')

    def get_process_tree(self, root_pid: int) -> list:
        if not root_pid:
            return []
        try:
            parent = psutil.Process(root_pid)
            children = parent.children(recursive=True)
            return [p.pid for p in children]
        except psutil.NoSuchProcess:
            return []
        except Exception as e:
            self.logger.error(f'Error getting process tree for {root_pid}: {e}')
            return []

    def is_running(self, pid: int) -> bool:
        if not pid:
            return False
        try:
            return psutil.pid_exists(pid)
        except Exception:
            return False

    def terminate_tree(self, root_pid: int, force: bool = False):
        try:
            parent = psutil.Process(root_pid)
            children = parent.children(recursive=True)
            for child in children:
                try:
                    if force:
                        child.kill()
                    else:
                        child.terminate()
                except psutil.NoSuchProcess:
                    pass
            if force:
                parent.kill()
            else:
                parent.terminate()
        except psutil.NoSuchProcess:
            pass
        except Exception as e:
            self.logger.error(f'Failed to terminate tree for {root_pid}: {e}')

# ==========================================
# output.py
# ==========================================
class OutputStreamingEngine:
    def __init__(self):
        self.logger = logging.getLogger('OutputStreamingEngine')

    def stream_output(self, process, execution, journal):
        def read_stream(stream, stream_name):
            if not stream:
                return
            for line in iter(stream.readline, ''):
                if not line:
                    break
                now = datetime.now().isoformat()
                if stream_name == 'stdout':
                    execution.last_stdout_activity = now
                else:
                    execution.last_stderr_activity = now
                
                journal.append_event(execution, f'{stream_name.upper()}_ACTIVITY', {'output': line.strip()})

        if process.stdout:
            threading.Thread(target=read_stream, args=(process.stdout, 'stdout'), daemon=True).start()
        if process.stderr:
            threading.Thread(target=read_stream, args=(process.stderr, 'stderr'), daemon=True).start()

# ==========================================
# journal.py
# ==========================================
class EventJournal:
    def __init__(self):
        self.logger = logging.getLogger('EventJournal')

    def append_event(self, execution: ManagedExecution, event_type: str, details: dict = None):
        if details is None:
            details = {}
        event = ExecutionEvent(
            event_type=event_type,
            timestamp=datetime.now().isoformat(),
            details=details
        )
        execution.execution_events.append(event)
        self.logger.info(f'[{execution.execution_id}] {event_type} - {details}')

# ==========================================
# execution.py
# ==========================================
class ExecutionManager:
    def __init__(self, process_manager, output_engine, journal, api_layer):
        self.process_manager = process_manager
        self.output_engine = output_engine
        self.journal = journal
        self.api_layer = api_layer
        self.executions = {}
        self.lock = threading.RLock()
        self.logger = logging.getLogger('ExecutionManager')

    def queue_script(self, script_path, execution_id=None):
        if not execution_id:
            execution_id = str(uuid.uuid4())
            
        execution = ManagedExecution(
            execution_id=execution_id,
            script_id='unknown',
            agent_id='unknown',
            script_path=script_path,
            script_args=[]
        )
        with self.lock:
            self.executions[execution_id] = execution
            
        self.journal.append_event(execution, 'EXECUTION_CREATED')
        self.transition_state(execution, 'STARTING', 'Queued for execution')

        threading.Thread(target=self._execution_watcher, args=(execution,), daemon=True).start()
        return execution

    def get_active_executions(self):
        with self.lock:
            return [e for e in self.executions.values() if e.execution_state in ['QUEUED', 'STARTING', 'RUNNING', 'STALLED']]

    def transition_state(self, execution: ManagedExecution, new_state: str, reason: str = None):
        with self.lock:
            if not StateResolver.can_transition(execution.execution_state, new_state):
                self.logger.warning(f'Invalid transition {execution.execution_state} -> {new_state} for {execution.execution_id}')
                return False
                
            execution.execution_state = new_state
            if new_state in ['COMPLETED', 'FAILED', 'TERMINATED', 'FORCE_KILLED', 'TIMEOUT', 'CRASHED']:
                execution.ended_at = datetime.now().isoformat()
                if new_state == 'TIMEOUT':
                    execution.termination_reason = reason
                elif new_state in ['FAILED', 'CRASHED']:
                    execution.failure_reason = reason
                    
            self.journal.append_event(execution, f'TRANSITION_{new_state}', {'reason': reason})
            
            event_payload = {
                'event_type': f'SCRIPT_{new_state}',
                'execution_id': execution.execution_id,
                'script_path': execution.script_path,
                'pid': execution.root_pid,
                'exit_code': execution.exit_code,
                'reason': reason,
                'sequence_number': len(execution.execution_events)
            }
            self.api_layer.sync_event(event_payload)
            return True

    def _execution_watcher(self, execution: ManagedExecution):
        try:
            cmd = [execution.script_path] + execution.script_args
            if os.name == 'nt' and execution.script_path.lower().endswith(('.bat', '.cmd')):
                cmd = ['cmd.exe', '/c'] + cmd
                
            self.journal.append_event(execution, 'PROCESS_STARTING', {'cmd': cmd})
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            execution.root_pid = process.pid
            execution.started_at = datetime.now().isoformat()
            self.transition_state(execution, 'RUNNING')
            
            self.output_engine.stream_output(process, execution, self.journal)
            
            while process.poll() is None:
                execution.child_pids = self.process_manager.get_process_tree(process.pid)
                if execution.execution_state in ['TIMEOUT', 'TERMINATED', 'FORCE_KILLED']:
                    self.process_manager.terminate_tree(process.pid, force=(execution.execution_state=='FORCE_KILLED'))
                    break
                time.sleep(1)
                
            exit_code = process.returncode
            execution.exit_code = exit_code
            self.journal.append_event(execution, 'PROCESS_EXITED', {'exit_code': exit_code})
            
            if execution.execution_state in ['RUNNING', 'STALLED']:
                final_state = StateResolver.resolve_exit_status(exit_code)
                self.transition_state(execution, final_state, f'Process exited with {exit_code}')
                
        except Exception as e:
            self.logger.error(f'Execution failed to start: {e}')
            execution.exit_code = -1
            self.transition_state(execution, 'CRASHED', str(e))

# ==========================================
# recovery.py
# ==========================================
class RecoveryManager:
    def __init__(self, state_file):
        self.state_file = state_file
        self.logger = logging.getLogger('RecoveryManager')

    def save_state(self, executions):
        try:
            data = {k: v.to_dict() for k, v in executions.items()}
            with open(self.state_file, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            self.logger.error(f'Failed to save state: {e}')

    def load_state(self):
        executions = {}
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    for k, v in data.items():
                        executions[k] = ManagedExecution(**v)
            except Exception as e:
                self.logger.error(f'Failed to load state: {e}')
        return executions

    def recover(self, execution_manager, process_manager):
        self.logger.info('Starting crash recovery...')
        executions = self.load_state()
        for exec_id, execution in executions.items():
            if execution.execution_state in ['QUEUED', 'STARTING', 'RUNNING', 'STALLED']:
                if execution.root_pid and process_manager.is_running(execution.root_pid):
                    self.logger.info(f'Recovered active execution {exec_id}')
                    execution_manager.executions[exec_id] = execution
                else:
                    self.logger.info(f'Execution {exec_id} orphaned during restart. Marking UNKNOWN.')
                    execution_manager.executions[exec_id] = execution
                    execution_manager.transition_state(execution, 'UNKNOWN', 'Agent restarted and process lost')


# ==========================================
# heartbeat.py
# ==========================================
class HeartbeatService:
    def __init__(self, api_layer, execution_manager, interval=5, agent_id=None, token_file=None):
        self.api_layer = api_layer
        self.execution_manager = execution_manager
        self.interval = interval
        self.agent_id = agent_id
        self.token_file = token_file
        self.running = False
        self.logger = logging.getLogger('HeartbeatService')

    def start(self):
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while self.running:
            try:
                executions = self.execution_manager.get_active_executions()
                running_paths = [e.script_path for e in executions]

                execution_events = []
                now = datetime.now()
                for e in executions:
                    runtime = 0
                    if e.started_at:
                        runtime = (now - datetime.fromisoformat(e.started_at)).total_seconds()
                    execution_events.append({
                        'event_type': 'SCRIPT_HEARTBEAT',
                        'execution_id': e.execution_id,
                        'script_path': e.script_path,
                        'pid': e.root_pid,
                        'cpu': e.resource_usage.get('cpu', 0),
                        'memory': e.resource_usage.get('memory', 0),
                        'runtime': runtime
                    })


                try:
                    sys_cpu = psutil.cpu_percent(interval=None)
                    sys_mem = psutil.virtual_memory().percent
                except Exception:
                    sys_cpu = 0
                    sys_mem = 0

                payload = {
                    'token': self.api_layer.token,
                    'cpu': sys_cpu,
                    'memory': sys_mem,
                    'running_scripts': running_paths,
                    'execution_events': execution_events
                }
                resp = self.api_layer.heartbeat(payload)
                if resp and isinstance(resp, dict) and resp.get("status_code") in (401, 403):
                    self.logger.warning("Agent token rejected by server (403 Forbidden). Clearing token and re-registering...")
                    self.api_layer.token = None
                    if self.token_file and os.path.exists(self.token_file):
                        try:
                            os.remove(self.token_file)
                        except Exception as ex:
                            self.logger.error(f"Failed to remove token file: {ex}")
                    if self.agent_id:
                        res = self.api_layer.register(self.agent_id)
                        if res and res.get('token'):
                            self.logger.info("Re-registration successful. Saving new token.")
                            if self.token_file:
                                try:
                                    with open(self.token_file, 'w') as f:
                                        f.write(res.get('token'))
                                except Exception as ex:
                                    self.logger.error(f"Failed to write token file: {ex}")
                elif resp and 'commands' in resp:
                    for cmd in resp['commands']:
                        if cmd.get('type') == 'RUN_SCRIPT':
                            self.execution_manager.queue_script(
                                script_path=cmd.get('script_path'),
                                execution_id=cmd.get('execution_id')
                            )
                        elif cmd.get('type') == 'STOP_SCRIPT':
                            script_path = cmd.get('script_path')
                            if not script_path:
                                continue
                            target_norm = os.path.normpath(script_path).lower()
                            
                            # 1. Kill managed executions
                            for execution in self.execution_manager.get_active_executions():
                                exec_norm = os.path.normpath(execution.script_path).lower() if execution.script_path else ""
                                if exec_norm == target_norm or execution.script_id == cmd.get('script_id'):
                                    self.execution_manager.transition_state(execution, 'FORCE_KILLED', 'Stopped by user')
                                    if execution.root_pid:
                                        self.process_manager.terminate_tree(execution.root_pid, force=True)
                                        

            except Exception as e:
                self.logger.error(f'Heartbeat error: {e}')
            time.sleep(self.interval)


# ==========================================
# watchdog.py
# ==========================================
class WatchdogEngine:
    def __init__(self, execution_manager, process_manager: ProcessTreeManager, journal):
        self.execution_manager = execution_manager
        self.process_manager = process_manager
        self.journal = journal
        self.logger = logging.getLogger('WatchdogEngine')
        self.running = False
        self.thread = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

    def _monitor_loop(self):
        while self.running:
            self._check_executions()
            time.sleep(5)

    def _check_executions(self):
        executions = self.execution_manager.get_active_executions()
        now = datetime.now()
        for execution in executions:
            if not execution.started_at:
                continue
            
            started = datetime.fromisoformat(execution.started_at)
            runtime = (now - started).total_seconds()
            
            last_activity = execution.last_stdout_activity or execution.started_at
            if last_activity:
                idle_time = (now - datetime.fromisoformat(last_activity)).total_seconds()
                if idle_time > 300 and execution.execution_state == 'RUNNING':
                    self.execution_manager.transition_state(execution, 'STALLED', 'No output activity for 300s')
            
            if execution.root_pid and self.process_manager.is_running(execution.root_pid):
                try:
                    p = psutil.Process(execution.root_pid)
                    execution.resource_usage['cpu'] = p.cpu_percent()
                    execution.resource_usage['memory'] = p.memory_percent()
                except Exception:
                    pass

    def _trigger_timeout(self, execution: ManagedExecution):
        self.logger.warning(f'Execution {execution.execution_id} timed out.')
        self.execution_manager.transition_state(execution, 'TIMEOUT', 'Exceeded configured timeout')
        if execution.root_pid:
            self.process_manager.terminate_tree(execution.root_pid, force=True)

# ==========================================
# core.py
# ==========================================
class AgentCore:
    def __init__(self, server_url, agent_id, state_dir):
        logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
        self.logger = logging.getLogger('AgentCore')
        
        self.process_manager = ProcessTreeManager()
        self.output_engine = OutputStreamingEngine()
        self.journal = EventJournal()
        self.token_file = os.path.join(state_dir, 'agent_token.dat')
        token = None
        if os.path.exists(self.token_file):
            with open(self.token_file, 'r') as f:
                token = f.read().strip()
                
        registration_secret = os.environ.get('BATCHHOST_REGISTRATION_SECRET')
        self.api_layer = ApiSyncLayer(server_url, token, registration_secret)
        self.execution_manager = ExecutionManager(
            self.process_manager, 
            self.output_engine, 
            self.journal, 
            self.api_layer
        )
        self.watchdog = WatchdogEngine(
            self.execution_manager,
            self.process_manager,
            self.journal
        )
        self.agent_id = agent_id
        self.heartbeat = HeartbeatService(
            self.api_layer,
            self.execution_manager,
            agent_id=self.agent_id,
            token_file=self.token_file
        )
        self.recovery = RecoveryManager(os.path.join(state_dir, 'executions_v2.json'))

    def start(self):
        self.logger.info('Starting AgentCore...')
        if not self.api_layer.token:
            res = self.api_layer.register(self.agent_id)
            if res and res.get('token'):
                with open(self.token_file, 'w') as f:
                    f.write(res.get('token'))
        else:
            self.logger.info('Using existing token from disk.')
            
        self.recovery.recover(self.execution_manager, self.process_manager)
        self.watchdog.start()
        self.heartbeat.start()
        self.logger.info('AgentCore started successfully.')
        while True:
            time.sleep(1)
            self.recovery.save_state(self.execution_manager.executions)

# ==========================================
# Runtime Logic
# ==========================================

SERVER_URL = os.environ.get("BATCHHOST_SERVER_URL", "https://172.100.30.191:5000").rstrip("/")
SCRIPT_DIR = Path(__file__).parent.absolute()
LOCAL_STATE_FILE = SCRIPT_DIR / "agent_id.dat"

if LOCAL_STATE_FILE.exists():
    STATE_DIR = SCRIPT_DIR
else:
    default_state = Path(os.environ.get("ProgramData", "C:\\ProgramData")) / "BatchHost-Pro" / "Agent"
    STATE_DIR = Path(os.environ.get("BATCHHOST_AGENT_STATE_DIR", os.environ.get("AGENT_STATE_DIR", default_state)))

# Fallback: if running locally next to the server, extract secret
if not os.environ.get("BATCHHOST_REGISTRATION_SECRET"):
    local_settings_path = SCRIPT_DIR.parent / "data" / "settings.json"
    if local_settings_path.exists():
        try:
            with open(local_settings_path, "r", encoding="utf-8") as f:
                settings_data = json.load(f)
                secret = settings_data.get("agent_registration_secret")
                if secret:
                    os.environ["BATCHHOST_REGISTRATION_SECRET"] = secret
        except Exception:
            pass

STATE_DIR.mkdir(parents=True, exist_ok=True)
AGENT_ID_FILE = STATE_DIR / "agent_id.dat"
LOCK_FILE = STATE_DIR / "agent.lock"

def agent_id() -> str:
    if AGENT_ID_FILE.exists():
        return AGENT_ID_FILE.read_text(encoding="utf-8").strip()
    value = str(uuid.uuid4())
    AGENT_ID_FILE.write_text(value, encoding="utf-8")
    return value

def ensure_single_instance() -> None:
    # psutil is already imported at the top now
    if LOCK_FILE.exists():
        try:
            pid = int(LOCK_FILE.read_text(encoding="utf-8").strip())
            if psutil.pid_exists(pid):
                print(f"CRITICAL: Another agent instance is already running with PID {pid}")
                sys.exit(1)
        except (ValueError, OSError):
            pass
    
    LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
    import atexit
    def cleanup():
        try:
            if LOCK_FILE.exists():
                pid = int(LOCK_FILE.read_text(encoding="utf-8").strip())
                if pid == os.getpid():
                    LOCK_FILE.unlink()
        except:
            pass
    atexit.register(cleanup)

def daemon() -> None:
    ensure_single_instance()
    aid = agent_id()
    core = AgentCore(SERVER_URL, aid, str(STATE_DIR))
    core.start()

def run_script(script_path: str, script_args: list[str]) -> int:
    aid = agent_id()
    core = AgentCore(SERVER_URL, aid, str(STATE_DIR))
    core.api_layer.register(aid)
    
    core.watchdog.start()
    core.heartbeat.start()
    
    execution = core.execution_manager.queue_script(script_path)
    
    while execution.execution_state not in ["COMPLETED", "FAILED", "TERMINATED", "FORCE_KILLED", "TIMEOUT", "CRASHED"]:
        time.sleep(1)
        
    return execution.exit_code if execution.exit_code is not None else 1

def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("daemon")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("script")
    run_parser.add_argument("script_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command == "daemon":
        daemon()
        return 0
    return run_script(args.script, args.script_args)

if __name__ == "__main__":
    raise SystemExit(main())