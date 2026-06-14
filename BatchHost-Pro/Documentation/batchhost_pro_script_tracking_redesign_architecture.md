# BatchHost-Pro — Industry Grade Script Tracking Redesign

## Current Problem Analysis

After reviewing the BatchHost-Pro architecture and current `server.py` implementation, the core issue is caused by the current heartbeat logic.

Current logic:

```python
if normalize_path(path) in normalized_running:
    mark_script_running(s)
else:
    if s.get("status") == "running":
        mark_script_failed(s, exit_code=1)
```

This design assumes:

> "If a script disappears from heartbeat, it failed."

That assumption is technically incorrect for production systems.

---

# Why Your Current Design Fails

## 1. Completed Scripts Become Failed

Current flow:

1. Script starts
2. Agent sends `running`
3. Script completes naturally
4. Script disappears from `running_scripts`
5. Server instantly marks it `failed`

This is the main bug.

---

## 2. Heartbeat Is Being Misused

Your heartbeat currently acts as:

- Agent online check
- Script process validation
- Script lifecycle validator

This overload creates race conditions.

---

## 3. No Script Session Identity

Currently scripts are identified only by:

- path
- agent_id

This is dangerous because:

- Same script can run multiple times
- Old status overwrites new status
- Late packets corrupt states
- Duplicate runs cannot be tracked separately

---

## 4. No Event Ordering

Current system has no:

- sequence number
- execution ID
- timestamps validation
- state machine

So delayed packets overwrite newer states.

---

## 5. No Lifecycle Ownership

Currently:

- heartbeat controls status
nstead of:

- execution engine controls status

This is the architectural mistake.

---

# Industry Standard Design

You need to redesign the system using:

# EXECUTION SESSION ARCHITECTURE

Instead of tracking:

```text
Script -> Status
```

Track:

```text
Script Execution Session -> Lifecycle
```

---

# Recommended Architecture

## Core Components

| Component | Responsibility |
|---|---|
| Agent Runtime | Detect process state locally |
| Execution Tracker | Tracks script lifecycle |
| Heartbeat Service | Agent online/offline only |
| Event Queue | Orders updates |
| Status Engine | Valid state transitions |
| Dashboard Cache | Fast UI updates |
| WebSocket Broadcaster | Real-time sync |
| Persistence Layer | Stores execution history |

---

# New Tracking Model

## OLD MODEL

```text
script -> running/completed/failed
```

---

## NEW MODEL

```text
execution_id -> lifecycle state
```

Each execution MUST have:

```json
{
  "execution_id": "uuid",
  "script_id": "script_uuid",
  "agent_id": "agent_uuid",
  "pid": 1234,
  "status": "running",
  "started_at": "timestamp",
  "ended_at": null,
  "exit_code": null,
  "last_seen": "timestamp",
  "heartbeat_timeout": 30,
  "termination_reason": null
}
```

---

# Correct Industry Status Lifecycle

## Valid States

```text
PENDING
STARTING
RUNNING
COMPLETED
FAILED
TERMINATED
KILLED
TIMEOUT
UNKNOWN
```

---

# IMPORTANT:

"Completed" and "Failed" are NOT determined from heartbeat disappearance.

They are determined from:

- process exit code
- OS process termination
- timeout engine
- manual kill event

This is critical.

---

# Correct Script Tracking Flow

# STEP 1 — Script Launch

Agent starts script.

Agent generates:

```text
execution_id = UUID()
```

Agent captures:

- PID
- start_time
- command
- execution_id

Agent sends:

```json
{
  "event": "SCRIPT_STARTED",
  "execution_id": "abc123",
  "pid": 4567,
  "script_path": "D:/jobs/test.bat",
  "started_at": "timestamp"
}
```

Server stores execution session.

Status:

```text
RUNNING
```

---

# STEP 2 — Runtime Heartbeat

Every 5–10 seconds:

Agent checks locally:

```text
Is PID still alive?
```

If YES:

```json
{
  "event": "SCRIPT_HEARTBEAT",
  "execution_id": "abc123",
  "pid": 4567,
  "cpu": 2.3,
  "memory": 120,
  "timestamp": "..."
}
```

Server updates:

```text
last_seen
```

ONLY.

NOT STATUS.

This is VERY IMPORTANT.

---

# STEP 3 — Process Completion

When process exits naturally:

Agent captures:

- exit code
- completion timestamp

Agent sends:

```json
{
  "event": "SCRIPT_COMPLETED",
  "execution_id": "abc123",
  "exit_code": 0,
  "ended_at": "timestamp"
}
```

Server updates:

```text
status = COMPLETED
```

---

# STEP 4 — Failure Handling

If process crashes:

```json
{
  "event": "SCRIPT_FAILED",
  "execution_id": "abc123",
  "exit_code": 1,
  "reason": "process_crashed"
}
```

Server:

```text
status = FAILED
```

---

# STEP 5 — Manual Closure

If user kills terminal/process manually:

Agent detects:

```text
PID vanished unexpectedly
```

Agent sends:

```json
{
  "event": "SCRIPT_TERMINATED",
  "execution_id": "abc123",
  "reason": "manual_termination"
}
```

Server:

```text
status = TERMINATED
```

NOT FAILED.

This is the major improvement.

---

# Correct Status Meaning

| Status | Meaning |
|---|---|
| RUNNING | Process alive |
| COMPLETED | Process exited with code 0 |
| FAILED | Process exited with non-zero code |
| TERMINATED | User/system manually killed process |
| TIMEOUT | No heartbeat for configured duration |
| UNKNOWN | Agent disconnected before confirmation |

---

# Heartbeat Redesign

## Current Wrong Logic

```text
No heartbeat = FAILED
```

---

## Correct Logic

```text
No heartbeat = POSSIBLY LOST
```

Then:

| Condition | Action |
|---|---|
| Agent alive + PID alive | RUNNING |
| Agent alive + PID missing + no completion event | TERMINATED |
| Agent offline temporarily | UNKNOWN |
| Agent offline long duration | TIMEOUT |

---

# Recommended Database Design

# scripts

Static script definition.

```sql
scripts
- id
- name
- path
- agent_id
- created_at
```

---

# script_executions

Tracks every execution.

```sql
script_executions
- execution_id
- script_id
- agent_id
- pid
- status
- started_at
- ended_at
- exit_code
- last_heartbeat
- termination_reason
- runtime_seconds
```

---

# execution_events

Audit/event sourcing.

```sql
execution_events
- id
- execution_id
- event_type
- payload
- timestamp
```

---

# Best Industry Practice

## NEVER derive final status from heartbeat disappearance.

This is the central rule.

Final states must come from:

- process exit
- exit code
- manual termination
- timeout engine

---

# Agent Side Redesign

# Windows (.bat)

Batch files are weak for process tracking.

Industry recommendation:

## Replace `.bat` agent with Python service

Use:

- Python
- psutil
- asyncio
- websockets/socketio

Why:

| Feature | Batch | Python |
|---|---|---|
| PID tracking | Weak | Excellent |
| Exit code handling | Weak | Strong |
| Async heartbeat | No | Yes |
| Process monitoring | Limited | Full |
| Restart recovery | Poor | Strong |
| Queue system | Hard | Easy |
| Logging | Weak | Strong |

---

# Recommended Agent Runtime

## Agent Services

### 1. Process Manager

Tracks:

- PID
- execution IDs
- runtime
- exit codes

---

### 2. Event Dispatcher

Queues events:

```text
STARTED
HEARTBEAT
COMPLETED
FAILED
TERMINATED
```

---

### 3. WebSocket Client

Persistent low latency connection.

---

### 4. Recovery Engine

After reboot:

- reconnects
- resyncs active executions
- repairs stale sessions

---

# Server Side Redesign

# Recommended Stack

| Layer | Recommended |
|---|---|
| API | FastAPI |
| WebSocket | Socket.IO / native websockets |
| Queue | Redis Streams / RabbitMQ |
| DB | PostgreSQL |
| Cache | Redis |
| Monitoring | Prometheus + Grafana |
| Process Tracking | Event-driven |

---

# Real-Time Flow

```text
Agent
  ↓
Event Queue
  ↓
Execution Engine
  ↓
Database
  ↓
WebSocket Broadcaster
  ↓
Dashboard
```

---

# Dashboard Improvements

## Current Issue

Dashboard reads inconsistent state.

---

## New Dashboard Model

Dashboard should:

- subscribe to WebSocket events
- never infer status
- render execution sessions
- separate active and historical runs

---

# Dashboard Sections

## Active Executions

Shows:

- PID
- runtime
- CPU
- memory
- live logs
- host

---

## Historical Executions

Shows:

- completion status
- runtime
- exit code
- failure reason

---

# Recommended State Machine

```text
PENDING
  ↓
STARTING
  ↓
RUNNING
  ├──> COMPLETED
  ├──> FAILED
  ├──> TERMINATED
  ├──> TIMEOUT
  └──> UNKNOWN
```

Invalid transitions should be rejected.

Example:

```text
COMPLETED -> RUNNING
```

MUST NEVER HAPPEN.

---

# Anti-Race-Condition Design

Every event must include:

```json
{
  "execution_id": "uuid",
  "sequence": 12,
  "timestamp": "..."
}
```

Server accepts only newer sequence numbers.

This prevents:

- stale packets
- delayed updates
- duplicate messages

---

# Recommended Timing

| Component | Interval |
|---|---|
| Agent heartbeat | 5 sec |
| Script heartbeat | 10 sec |
| Timeout threshold | 30 sec |
| Dashboard refresh | WebSocket realtime |

---

# What You Should Remove Immediately

## REMOVE THIS ENTIRE IDEA

```python
if running_script_disappeared:
    mark_failed()
```

This is the root architectural issue.

---

# What You Should Implement Immediately

## Add Execution IDs

Mandatory.

---

## Separate Agent Heartbeat From Script Lifecycle

Mandatory.

---

## Add PID-Based Process Tracking

Mandatory.

---

## Add Explicit Completion Events

Mandatory.

---

## Add TERMINATED State

Mandatory.

---

## Add Event Queue

Strongly recommended.

---

# Final Industry Grade Architecture

```text
+----------------------+
| Central Dashboard |
+----------+-----------+
           |
           v
+----------------------+
| WebSocket Gateway |
+----------+-----------+
           |
           v
+----------------------+
| Execution Engine |
+----------+-----------+
           |
     +-----+-----+
     |           |
     v           v
+---------+   +---------+
| Redis |   | Postgres |
+---------+   +---------+
           ^
           |
+----------------------+
| Agent Runtime |
| - PID tracker |
| - Event queue |
| - Recovery |
+----------------------+
```

---

# Recommended Migration Plan

## Phase 1

Immediate fixes:

- remove heartbeat-failed logic
- add terminated state
- add explicit completion event

---

## Phase 2

Structural redesign:

- execution IDs
- PID tracking
- event ordering
- execution sessions

---

## Phase 3

Enterprise scaling:

- Redis queue
- PostgreSQL
- WebSocket scaling
- monitoring stack

---

# Final Recommendation

Your current architecture is very close to a monitoring system, but the script tracking layer needs to evolve from:

```text
Status Snapshot Architecture
```

to:

```text
Event-Driven Execution Lifecycle Architecture
```

That is the exact architectural transition used in:

- Jenkins
- Airflow
- Rundeck
- Azure DevOps Agents
- Kubernetes Job Controllers
- Enterprise RMM tools
- Datacenter orchestration systems

Once you implement this redesign:

- false failures disappear
- dashboard sync becomes accurate
- long-running scripts behave correctly
- concurrent executions become reliable
- manual termination becomes distinguishable
- scaling becomes much easier
- monitoring becomes enterprise-grade

