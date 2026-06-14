import logging
import os
import threading
import uuid
from datetime import datetime


HEARTBEAT_INTERVAL_SECONDS = 5
TIMEOUT_THRESHOLD_SECONDS = 90

EXECUTION_STATES = {
    "PENDING",
    "QUEUED",
    "STARTING",
    "RUNNING",
    "COMPLETED",
    "FAILED",
    "TERMINATED",
    "FORCE_KILLED",
    "TIMEOUT",
    "CRASHED",
    "STALLED",
    "UNKNOWN",
}

ACTIVE_STATES = {"PENDING", "QUEUED", "STARTING", "RUNNING", "STALLED"}
TERMINAL_STATES = {"COMPLETED", "FAILED", "TERMINATED", "FORCE_KILLED", "TIMEOUT", "CRASHED", "UNKNOWN"}

ALLOWED_TRANSITIONS = {
    None: {"PENDING", "QUEUED", "STARTING"},
    "": {"PENDING", "QUEUED", "STARTING"},
    "PENDING": {"QUEUED", "STARTING", "RUNNING"},
    "QUEUED": {"STARTING", "RUNNING", "FAILED", "TERMINATED"},
    "STARTING": {"RUNNING", "FAILED", "CRASHED", "TERMINATED"},
    "RUNNING": {"COMPLETED", "FAILED", "TERMINATED", "FORCE_KILLED", "TIMEOUT", "CRASHED", "STALLED", "UNKNOWN"},
    "STALLED": {"RUNNING", "FAILED", "TERMINATED", "FORCE_KILLED", "TIMEOUT"},
    "UNKNOWN": {"RUNNING", "COMPLETED", "FAILED", "TERMINATED", "FORCE_KILLED", "TIMEOUT"},
    "COMPLETED": set(),
    "FAILED": set(),
    "TERMINATED": set(),
    "FORCE_KILLED": set(),
    "TIMEOUT": {"COMPLETED", "FAILED", "TERMINATED", "RUNNING"},
    "CRASHED": set(),
}

EVENT_TYPES = {
    "SCRIPT_QUEUED",
    "SCRIPT_STARTING",
    "SCRIPT_RUNNING",
    "SCRIPT_COMPLETED",
    "SCRIPT_FAILED",
    "SCRIPT_TERMINATED",
    "SCRIPT_FORCE_KILLED",
    "SCRIPT_TIMEOUT",
    "SCRIPT_CRASHED",
    "SCRIPT_STALLED",
    "SCRIPT_UNKNOWN",
    "SCRIPT_STARTED",
    "SCRIPT_HEARTBEAT",
    "AGENT_CONNECTED",
    "AGENT_DISCONNECTED",
}

EVENT_TARGET_STATE = {
    "SCRIPT_QUEUED": "QUEUED",
    "SCRIPT_STARTING": "STARTING",
    "SCRIPT_RUNNING": "RUNNING",
    "SCRIPT_COMPLETED": "COMPLETED",
    "SCRIPT_FAILED": "FAILED",
    "SCRIPT_TERMINATED": "TERMINATED",
    "SCRIPT_FORCE_KILLED": "FORCE_KILLED",
    "SCRIPT_TIMEOUT": "TIMEOUT",
    "SCRIPT_CRASHED": "CRASHED",
    "SCRIPT_STALLED": "STALLED",
    "SCRIPT_UNKNOWN": "UNKNOWN",
    "SCRIPT_STARTED": "RUNNING",
}

LEGACY_STATUS_TO_EVENT = {
    "running": "SCRIPT_STARTED",
    "completed": "SCRIPT_COMPLETED",
    "failed": "SCRIPT_FAILED",
    "terminated": "SCRIPT_TERMINATED",
    "timeout": "SCRIPT_TIMEOUT",
}


class StateMachineValidator:
    @staticmethod
    def can_transition(current_state, next_state):
        if next_state not in EXECUTION_STATES:
            return False, f"unknown state {next_state}"
        if current_state == next_state and current_state in ACTIVE_STATES:
            return True, "idempotent active update"
        allowed = ALLOWED_TRANSITIONS.get(current_state, set())
        if next_state in allowed:
            return True, ""
        return False, f"invalid transition {current_state}->{next_state}"


class ExecutionManager:
    """Thread-safe event-driven execution lifecycle manager.

    Storage is intentionally JSON-backed to preserve the current deployment model.
    The public methods accept already-loaded JSON rows so server.py can keep its
    existing file helpers, auth filters, and organization model.
    """

    def __init__(self):
        self.lock = threading.RLock()

    @staticmethod
    def now_iso():
        return datetime.now().isoformat()

    @staticmethod
    def parse_iso(value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def seconds_since(value):
        parsed = ExecutionManager.parse_iso(value)
        if not parsed:
            return None
        return (datetime.now() - parsed).total_seconds()

    @staticmethod
    def normalize_path(path):
        if not isinstance(path, str):
            return ""
        return os.path.normpath(path).replace("\\", "/").lower().strip()

    @staticmethod
    def script_type(path):
        low = (path or "").lower()
        if low.endswith(".bat") or low.endswith(".cmd"):
            return "bat"
        if low.endswith(".ps1"):
            return "ps1"
        return "sh"

    def ensure_script(self, scripts, agent, script_path, script_id=None, script_name=None):
        normalized = self.normalize_path(script_path)
        script = None
        if script_id:
            script = next((s for s in scripts if s.get("id") == script_id), None)
        if not script and normalized:
            script = next(
                (
                    s for s in scripts
                    if s.get("agent_id") == agent.get("id")
                    and self.normalize_path(s.get("path")) == normalized
                ),
                None,
            )
        if script:
            return script

        script = {
            "id": script_id or str(uuid.uuid4()),
            "name": script_name or os.path.basename(script_path or "script"),
            "path": script_path,
            "agent_id": agent.get("id"),
            "organization_id": agent.get("organization_id"),
            "os_type": agent.get("os_type", "unknown"),
            "type": self.script_type(script_path),
            "status": "pending",
            "enabled": True,
            "created_at": self.now_iso(),
        }
        scripts.append(script)
        logging.info(
            "TRACKING script created script_id=%s agent=%s path=%s",
            script["id"], agent.get("id"), script_path,
        )
        return script

    def find_execution(self, executions, execution_id):
        if not execution_id:
            return None
        return next((e for e in executions if e.get("execution_id") == execution_id), None)

    def latest_active_execution(self, executions, agent_id, script_path=None, script_id=None, pid=None, process_start_time=None):
        normalized = self.normalize_path(script_path)
        matches = []
        for execution in executions:
            if execution.get("agent_id") != agent_id:
                continue
            if execution.get("state") not in ACTIVE_STATES:
                continue
            if script_id and execution.get("script_id") != script_id:
                continue
            if pid is not None and str(execution.get("pid")) != str(pid):
                continue
            if normalized and self.normalize_path(execution.get("script_path")) != normalized:
                continue
            # Recycled PID Prevention: If process_start_time is stored and also provided, verify they match
            stored_start = execution.get("process_start_time")
            if process_start_time and stored_start and stored_start != process_start_time:
                continue
            matches.append(execution)
        matches.sort(key=lambda e: e.get("started_at") or e.get("created_at") or "", reverse=True)
        return matches[0] if matches else None

    def _next_sequence(self, execution):
        return int(execution.get("last_sequence_number", 0) or 0) + 1

    def normalize_event(self, data, agent=None, default_type=None):
        event_type = data.get("event_type") or data.get("type") or default_type
        if event_type in LEGACY_STATUS_TO_EVENT:
            event_type = LEGACY_STATUS_TO_EVENT[event_type]
        sequence = data.get("sequence_number")
        try:
            sequence = int(sequence) if sequence not in (None, "") else None
        except (TypeError, ValueError):
            sequence = None
        exit_code = data.get("exit_code")
        try:
            exit_code = int(exit_code) if exit_code not in (None, "") else None
        except (TypeError, ValueError):
            exit_code = None
        return {
            "event_id": data.get("event_id") or str(uuid.uuid4()),
            "event_type": event_type,
            "execution_id": data.get("execution_id"),
            "sequence_number": sequence,
            "timestamp": data.get("timestamp") or self.now_iso(),
            "agent_id": data.get("agent_id") or (agent or {}).get("id"),
            "script_id": data.get("script_id"),
            "script_name": data.get("script_name") or data.get("name"),
            "script_path": data.get("script_path") or data.get("path"),
            "pid": data.get("pid"),
            "exit_code": exit_code,
            "cpu": data.get("cpu"),
            "memory": data.get("memory"),
            "runtime": data.get("runtime"),
            "reason": data.get("reason"),
            "log": data.get("log", ""),
            "process_start_time": data.get("process_start_time"),
        }

    def validate_sequence(self, execution, event):
        sequence = event.get("sequence_number")
        if sequence is None:
            event["sequence_number"] = self._next_sequence(execution)
            return True, ""
        last_sequence = int(execution.get("last_sequence_number", 0) or 0)
        if sequence <= last_sequence:
            return False, f"stale or duplicate sequence {sequence} <= {last_sequence}"
        return True, ""

    def append_event(self, event_store, execution, event, accepted, reason=None):
        stored = {
            "id": event.get("event_id") or str(uuid.uuid4()),
            "execution_id": event.get("execution_id"),
            "agent_id": event.get("agent_id"),
            "script_id": event.get("script_id") or execution.get("script_id"),
            "event_type": event.get("event_type"),
            "sequence_number": event.get("sequence_number"),
            "timestamp": event.get("timestamp") or self.now_iso(),
            "accepted": bool(accepted),
            "reason": reason,
            "pid": event.get("pid"),
            "exit_code": event.get("exit_code"),
            "state_after": execution.get("state"),
        }
        event_store.append(stored)
        if len(event_store) > 10000:
            del event_store[:-10000]

    def _sync_script_summary(self, script, execution):
        state = execution.get("state", "UNKNOWN")
        if state in {"STARTING", "RUNNING"}:
            script["status"] = "running"
        elif state == "PENDING":
            script["status"] = "pending"
        elif state in {"TERMINATED", "TIMEOUT", "UNKNOWN"}:
            script["status"] = state.lower()
        else:
            script["status"] = state.lower()
        
        script["current_run_id"] = execution.get("execution_id")
        script["current_execution_id"] = execution.get("execution_id")
        script["pid"] = execution.get("pid")
        script["started_at"] = execution.get("started_at")
        script["last_seen_running_at"] = execution.get("last_seen")
        script["status_updated_at"] = execution.get("updated_at")
        script["status_version"] = int(script.get("status_version", 0) or 0) + 1
        script["last_status_source"] = "execution_manager"
        script["last_sequence_number"] = execution.get("last_sequence_number")
        if execution.get("exit_code") is not None:
            script["exit_code"] = execution.get("exit_code")
        if state == "COMPLETED":
            script["completed_at"] = execution.get("ended_at")
            script.pop("failed_at", None)
        elif state in {"FAILED", "TERMINATED", "TIMEOUT", "UNKNOWN"}:
            script["failed_at"] = execution.get("ended_at")
            script.pop("completed_at", None)
        elif state in {"PENDING", "STARTING", "RUNNING"}:
            script.pop("completed_at", None)
            script.pop("failed_at", None)

    def _broadcast_payload(self, execution, script=None):
        return {
            "execution_id": execution.get("execution_id"),
            "script_id": execution.get("script_id"),
            "script_name": execution.get("script_name"),
            "script_path": execution.get("script_path"),
            "agent_id": execution.get("agent_id"),
            "organization_id": execution.get("organization_id"),
            "pid": execution.get("pid"),
            "status": execution.get("state", "").lower(),
            "state": execution.get("state"),
            "sequence_number": execution.get("last_sequence_number", 0),
            "started_at": execution.get("started_at"),
            "last_seen": execution.get("last_seen"),
            "runtime": execution.get("runtime", 0),
            "exit_code": execution.get("exit_code"),
            "cpu": execution.get("cpu"),
            "memory": execution.get("memory"),
            "updated_at": execution.get("updated_at"),
            "script_status_version": (script or {}).get("status_version"),
            "process_start_time": execution.get("process_start_time"),
        }

    def process_event(self, scripts, executions, event_store, agent, raw_event):
        with self.lock:
            event = self.normalize_event(raw_event, agent=agent)
            event_type = event.get("event_type")
            if event_type not in EVENT_TYPES:
                return {
                    "accepted": False,
                    "status_code": 400,
                    "error": f"unknown event_type {event_type}",
                    "broadcast": None,
                }

            if event_type in {"AGENT_CONNECTED", "AGENT_DISCONNECTED"}:
                pseudo = {
                    "execution_id": event.get("execution_id"),
                    "script_id": None,
                    "state": event_type,
                    "last_sequence_number": event.get("sequence_number") or 0,
                }
                self.append_event(event_store, pseudo, event, True)
                return {"accepted": True, "execution": None, "broadcast": None}

            script = self.ensure_script(
                scripts,
                agent,
                event.get("script_path"),
                script_id=event.get("script_id"),
                script_name=event.get("script_name"),
            )
            event["script_id"] = script.get("id")

            execution = self.find_execution(executions, event.get("execution_id"))
            if not execution:
                execution = self.latest_active_execution(
                    executions,
                    agent.get("id"),
                    script_path=event.get("script_path"),
                    script_id=script.get("id"),
                    pid=event.get("pid"),
                    process_start_time=event.get("process_start_time"),
                )

            if not execution:
                if event_type not in {"SCRIPT_STARTED", "SCRIPT_STARTING", "SCRIPT_QUEUED", "SCRIPT_RUNNING"}:
                    return {
                        "accepted": False,
                        "status_code": 409,
                        "error": "terminal/heartbeat event has no active execution",
                        "broadcast": None,
                    }
                execution = {
                    "execution_id": event.get("execution_id") or str(uuid.uuid4()),
                    "script_id": script.get("id"),
                    "script_name": script.get("name"),
                    "script_path": script.get("path"),
                    "agent_id": agent.get("id"),
                    "organization_id": agent.get("organization_id"),
                    "pid": event.get("pid"),
                    "state": "PENDING",
                    "created_at": event.get("timestamp"),
                    "started_at": event.get("timestamp"),
                    "last_seen": event.get("timestamp"),
                    "last_sequence_number": 0,
                    "runtime": 0,
                    "exit_code": None,
                    "cpu": None,
                    "memory": None,
                    "updated_at": event.get("timestamp"),
                    "process_start_time": event.get("process_start_time"),
                }
                executions.append(execution)
                event["execution_id"] = execution["execution_id"]
            else:
                event["execution_id"] = execution.get("execution_id")
                # Backfill process_start_time if present in event but missing from execution
                if not execution.get("process_start_time") and event.get("process_start_time"):
                    execution["process_start_time"] = event.get("process_start_time")

            sequence_ok, sequence_reason = self.validate_sequence(execution, event)
            if not sequence_ok:
                self.append_event(event_store, execution, event, False, sequence_reason)
                logging.warning(
                    "TRACKING stale event rejected execution=%s type=%s reason=%s",
                    execution.get("execution_id"), event_type, sequence_reason,
                )
                return {
                    "accepted": False,
                    "status_code": 409,
                    "error": sequence_reason,
                    "execution": execution,
                    "broadcast": None,
                }

            now = event.get("timestamp") or self.now_iso()
            if event_type == "SCRIPT_HEARTBEAT":
                if execution.get("state") not in ACTIVE_STATES:
                    # If the execution is in TIMEOUT or UNKNOWN state, a live heartbeat
                    # from the agent proves the process is still running — resurrect it.
                    # This handles cases where the 90s timeout fired before the agent
                    # reconnected or the network was temporarily slow.
                    recoverable = {"TIMEOUT", "UNKNOWN"}
                    if execution.get("state") in recoverable:
                        ok, _ = StateMachineValidator.can_transition(execution.get("state"), "RUNNING")
                        if ok:
                            logging.info(
                                "TRACKING resurrecting %s execution=%s from %s back to RUNNING via heartbeat",
                                execution.get("state"), execution.get("execution_id"), execution.get("state"),
                            )
                            execution["state"] = "RUNNING"
                            execution.pop("ended_at", None)
                            # Fall through to the normal heartbeat update below
                        else:
                            reason = f"heartbeat ignored for terminal state {execution.get('state')}"
                            self.append_event(event_store, execution, event, False, reason)
                            return {
                                "accepted": False,
                                "status_code": 409,
                                "error": reason,
                                "execution": execution,
                                "broadcast": None,
                            }
                    else:
                        reason = f"heartbeat ignored for terminal state {execution.get('state')}"
                        self.append_event(event_store, execution, event, False, reason)
                        return {
                            "accepted": False,
                            "status_code": 409,
                            "error": reason,
                            "execution": execution,
                            "broadcast": None,
                        }
                execution["last_seen"] = now
                execution["cpu"] = event.get("cpu", execution.get("cpu"))
                execution["memory"] = event.get("memory", execution.get("memory"))
                execution["runtime"] = event.get("runtime", execution.get("runtime", 0))
                execution["updated_at"] = now
                execution["last_sequence_number"] = event["sequence_number"]
                self._sync_script_summary(script, execution)
                self.append_event(event_store, execution, event, True)
                return {
                    "accepted": True,
                    "execution": execution,
                    "script": script,
                    "broadcast": self._broadcast_payload(execution, script),
                }

            target_state = EVENT_TARGET_STATE[event_type]
            if event_type == "SCRIPT_STARTED":
                if execution.get("state") == "PENDING":
                    ok, reason = StateMachineValidator.can_transition("PENDING", "STARTING")
                    if not ok:
                        self.append_event(event_store, execution, event, False, reason)
                        return {"accepted": False, "status_code": 409, "error": reason}
                    execution["state"] = "STARTING"
                ok, reason = StateMachineValidator.can_transition(execution.get("state"), "RUNNING")
                target_state = "RUNNING"
            else:
                if target_state == "FAILED" and event.get("exit_code") == 0:
                    target_state = "COMPLETED"
                if target_state == "COMPLETED" and event.get("exit_code") not in (None, 0):
                    target_state = "FAILED"
                ok, reason = StateMachineValidator.can_transition(execution.get("state"), target_state)

            if not ok:
                # SPECIAL CASE: If we get a final event for a TIMEOUT/UNKNOWN state, we allow it if it's a real terminal state
                if execution.get("state") in {"TIMEOUT", "UNKNOWN"} and target_state in {"COMPLETED", "FAILED", "TERMINATED"}:
                    ok = True
                    reason = f"Recovering real status from {execution.get('state')} to {target_state}"
                else:
                    self.append_event(event_store, execution, event, False, reason)
                    logging.warning(
                        "TRACKING transition rejected execution=%s event=%s state=%s target=%s reason=%s",
                        execution.get("execution_id"), event_type, execution.get("state"), target_state, reason,
                    )
                    return {
                        "accepted": False,
                        "status_code": 409,
                        "error": reason,
                        "execution": execution,
                        "broadcast": None,
                    }

            old_state = execution.get("state")
            execution["state"] = target_state
            execution["pid"] = event.get("pid", execution.get("pid"))
            execution["last_seen"] = now
            execution["runtime"] = event.get("runtime", execution.get("runtime", 0))
            execution["cpu"] = event.get("cpu", execution.get("cpu"))
            execution["memory"] = event.get("memory", execution.get("memory"))
            execution["exit_code"] = event.get("exit_code", execution.get("exit_code"))
            execution["last_sequence_number"] = event["sequence_number"]
            execution["updated_at"] = now
            if target_state in TERMINAL_STATES:
                execution["ended_at"] = now

            self._sync_script_summary(script, execution)
            self.append_event(event_store, execution, event, True)
            logging.info(
                "TRACKING event accepted execution=%s script=%s agent=%s event=%s state=%s seq=%s",
                execution.get("execution_id"), script.get("id"), agent.get("id"),
                event_type, execution.get("state"), event.get("sequence_number"),
            )
            return {
                "accepted": True,
                "execution": execution,
                "script": script,
                "broadcast": self._broadcast_payload(execution, script),
            }

    def timeout_active_executions(self, scripts, executions, event_store, agent_status_by_id):
        broadcasts = []
        with self.lock:
            scripts_by_id = {s.get("id"): s for s in scripts}
            for execution in executions:
                if execution.get("state") != "RUNNING":
                    continue
                age = self.seconds_since(execution.get("last_seen") or execution.get("started_at"))
                if age is None or age <= TIMEOUT_THRESHOLD_SECONDS:
                    continue
                agent_status = agent_status_by_id.get(execution.get("agent_id"))
                target = "UNKNOWN" if agent_status == "offline" else "TIMEOUT"
                ok, reason = StateMachineValidator.can_transition("RUNNING", target)
                if not ok:
                    logging.warning(
                        "TRACKING timeout transition rejected execution=%s reason=%s",
                        execution.get("execution_id"), reason,
                    )
                    continue
                sequence_number = self._next_sequence(execution)
                now = self.now_iso()
                event = {
                    "event_id": str(uuid.uuid4()),
                    "event_type": "AGENT_DISCONNECTED" if target == "UNKNOWN" else "SCRIPT_TIMEOUT",
                    "execution_id": execution.get("execution_id"),
                    "agent_id": execution.get("agent_id"),
                    "script_id": execution.get("script_id"),
                    "sequence_number": sequence_number,
                    "timestamp": now,
                    "reason": f"last_seen exceeded {TIMEOUT_THRESHOLD_SECONDS}s threshold",
                }
                execution["state"] = target
                execution["last_sequence_number"] = sequence_number
                execution["updated_at"] = now
                execution["ended_at"] = now
                execution["exit_code"] = execution.get("exit_code")
                script = scripts_by_id.get(execution.get("script_id"))
                if script:
                    self._sync_script_summary(script, execution)
                self.append_event(event_store, execution, event, True, event["reason"])
                broadcasts.append(self._broadcast_payload(execution, script))
                logging.warning(
                    "TRACKING execution %s moved to %s after %.1fs without heartbeat",
                    execution.get("execution_id"), target, age,
                )
        return broadcasts