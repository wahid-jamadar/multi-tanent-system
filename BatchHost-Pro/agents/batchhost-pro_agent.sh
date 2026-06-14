#!/bin/bash
AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$AGENT_DIR/agent_runtime.py" ] && command -v python3 >/dev/null 2>&1; then
    exec python3 "$AGENT_DIR/agent_runtime.py" daemon
fi
# =============================================================
# BatchHost-Pro Linux/macOS Agent                              |
# Sends heartbeats, system stats, and script status to server  |
# =============================================================


# ── CONFIG ──────────────────────────────────────────────────
SERVER_URL="https://172.100.31.40:5000"
HEARTBEAT_INTERVAL=10
AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_ROOT="${XDG_STATE_HOME:-$HOME/.local/state}"
AGENT_STATE_DIR="$STATE_ROOT/batchhost-pro/agent"
mkdir -p "$AGENT_STATE_DIR" 2>/dev/null || AGENT_STATE_DIR="$AGENT_DIR/.state"
AGENT_ID_FILE="$AGENT_STATE_DIR/agent_id.dat"
TOKEN_FILE="$AGENT_STATE_DIR/agent_token.dat"
LOG_DIR="$AGENT_STATE_DIR/logs"
LOG_FILE="$LOG_DIR/agent_$(date +%Y-%m-%d).log"
LOCK_FILE="/tmp/batchhost-pro_agent.lock"
# ────────────────────────────────────────────────────────────

mkdir -p "$LOG_DIR"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"; }

if ! command -v curl >/dev/null 2>&1; then
    log "Error: curl is required but not installed."
    exit 1
fi

# ── Find Python ──────────────────────────────────────────────
PYTHON_CMD=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
fi


# ── Prevent duplicate agents ─────────────────────────────────
if [ -f "$LOCK_FILE" ]; then
    OLD_PID=$(cat "$LOCK_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        log "Agent already running (PID: $OLD_PID). Exiting."
        exit 1
    else
        log "Stale lock file found. Removing."
        rm -f "$LOCK_FILE"
    fi
fi

echo $$ > "$LOCK_FILE"

cleanup() {
    rm -f "$LOCK_FILE"
    log "Agent stopped."
    exit 0
}

trap cleanup EXIT INT TERM
# Extra safety: prevent multiple instances via process scan
# CURRENT_PID=$$

# RUNNING_PIDS=$(pgrep -f "batchhost-pro_agent.sh")

# for PID in $RUNNING_PIDS; do
    # if [ "$PID" != "$CURRENT_PID" ]; then
        # log "Another instance detected (PID: $PID). Exiting."
        # exit 1
    # fi
# done


# ── Load or generate agent ID ────────────────────────────────
new_agent_id() {
    AGENT_ID=$(cat /proc/sys/kernel/random/uuid 2>/dev/null || \
               uuidgen 2>/dev/null || \
               ([ -n "$PYTHON_CMD" ] && $PYTHON_CMD -c "import uuid; print(uuid.uuid4())" 2>/dev/null) || \
               echo "agent-$(hostname)-$(date +%s)-${RANDOM}")
    
    # Ensure AGENT_ID is not empty
    if [ -z "$AGENT_ID" ]; then
        AGENT_ID="agent-$(hostname)-$(date +%s)"
    fi
    echo "$AGENT_ID" > "$AGENT_ID_FILE"
}

if [ -f "$AGENT_ID_FILE" ]; then
    AGENT_ID=$(cat "$AGENT_ID_FILE" | tr -d '[:space:]')
fi

if [ -z "$AGENT_ID" ]; then
    new_agent_id
fi

HOSTNAME=$(hostname)
OS_TYPE="linux"
if [ "$(uname)" = "Darwin" ]; then OS_TYPE="macos"; fi
DEVICE_KEY=$(cat /etc/machine-id 2>/dev/null || ioreg -rd1 -c IOPlatformExpertDevice 2>/dev/null | awk -F\" '/IOPlatformUUID/ {print $4}' || hostname)

log "BatchHost-Pro Agent starting on $HOSTNAME (ID: $AGENT_ID)"


# Helper to extract JSON values
extract_json_val() {
    local json="$1"
    local key="$2"
    if [ -n "$PYTHON_CMD" ]; then
        echo "$json" | $PYTHON_CMD -c "import sys,json; d=json.load(sys.stdin); print(d.get('$key',''))" 2>/dev/null
    else
        # Fallback for simple string/bool values
        echo "$json" | sed -n 's/.*"'"$key"'"\s*:\s*"\?\([^",}]*\)"\?.*/\1/p' | tr -d ' ' | sed 's/[,}]$//'
    fi
}

# ── Register with server ─────────────────────────────────────
register() {
    local PAYLOAD="{\"agent_id\":\"$AGENT_ID\",\"hostname\":\"$HOSTNAME\",\"os_type\":\"$OS_TYPE\",\"device_key\":\"$DEVICE_KEY\"}"
    local RESPONSE
    RESPONSE=$(curl -k -s -w "\n%{http_code}" -X POST "$SERVER_URL/api/agent/register" \
        -H "Content-Type: application/json" \
        -d "$PAYLOAD" \
        --connect-timeout 10 \
        --max-time 15 2>/dev/null)
    
    if [ $? -ne 0 ]; then return 1; fi

    local HTTP_STATUS=$(printf "%s" "$RESPONSE" | tail -n 1)
    RESPONSE=$(printf "%s" "$RESPONSE" | sed '$d')
    
    local SUCCESS=$(extract_json_val "$RESPONSE" "success")
    if [ "$SUCCESS" = "True" ] || [ "$SUCCESS" = "true" ]; then
        TOKEN=$(extract_json_val "$RESPONSE" "token")
        REGISTERED_AGENT_ID=$(extract_json_val "$RESPONSE" "agent_id")
        if [ -n "$REGISTERED_AGENT_ID" ] && [ "$REGISTERED_AGENT_ID" != "$AGENT_ID" ]; then
            log "Server mapped this device to existing agent ID $REGISTERED_AGENT_ID."
            AGENT_ID="$REGISTERED_AGENT_ID"
            echo "$AGENT_ID" > "$AGENT_ID_FILE"
        fi
        echo "$TOKEN" > "$TOKEN_FILE"
        log "Registered successfully."
        return 0
    else
        local ERR=$(extract_json_val "$RESPONSE" "error")
        if [ "$ERR" = "duplicate" ] || [ "$HTTP_STATUS" = "409" ]; then
            log "Duplicate agent ID $AGENT_ID rejected by server. Creating a new per-device ID."
            new_agent_id
        fi
        return 1
    fi
}

# Retry registration
until register; do
    log "Registration failed. Retrying in 15s..."
    sleep 15
done

TOKEN=$(cat "$TOKEN_FILE")


# ── Get system metrics ────────────────────────────────────────
get_cpu() {
    if command -v top &>/dev/null; then
        top -bn1 | grep "Cpu(s)" | awk '{print int($2)}' 2>/dev/null || echo 0
    else
        echo 0
    fi
}

get_memory() {
    if [ -f /proc/meminfo ]; then
        local TOTAL=$(grep MemTotal /proc/meminfo | awk '{print $2}')
        local FREE=$(grep MemAvailable /proc/meminfo | awk '{print $2}')
        echo $(( 100 - (FREE * 100 / TOTAL) ))
    elif command -v vm_stat &>/dev/null; then
        # macOS
        local PAGES_FREE=$(vm_stat | grep "Pages free" | awk '{print $3}' | tr -d '.')
        local PAGES_TOTAL=$(sysctl -n hw.memsize 2>/dev/null || echo 8589934592)
        echo 50  # Simplified for macOS
    else
        echo 0
    fi
}

get_running_scripts() {
    # List all running .sh processes tracked by this agent
    ps aux | grep '\.sh' | grep -v grep | awk '{print $11}' | tr '\n' ',' | sed 's/,$//' 2>/dev/null || echo ""
}


# ── Heartbeat Loop ────────────────────────────────────────────
log "Starting heartbeat loop (interval: ${HEARTBEAT_INTERVAL}s)"

send_script_status() {
    local SCRIPT_PATH="$1"
    local STATUS="$2"
    local EXIT_CODE="${3:-0}"
    local LOG_DATA="${4:-}"
    
    local PAYLOAD="{\"token\":\"$TOKEN\",\"script_path\":\"$SCRIPT_PATH\",\"status\":\"$STATUS\",\"exit_code\":$EXIT_CODE,\"log\":\"$LOG_DATA\"}"
    curl -k -s -X POST "$SERVER_URL/api/agent/script-status" \
        -H "Content-Type: application/json" \
        -d "$PAYLOAD" \
        --connect-timeout 5 \
        --max-time 10 &>/dev/null
}

# Export function so subshells can use it
export -f send_script_status
export SERVER_URL TOKEN

while true; do
    CPU=$(get_cpu)
    MEM=$(get_memory)
    
    # Build running scripts JSON array
    RUNNING_JSON="[]"
    RUNNING_PROCS=$(ps aux | grep '\.sh\|\.bat' | grep -v grep | grep -v "$0" | awk '{print $11}' | head -10)
    if [ -n "$RUNNING_PROCS" ]; then
        RUNNING_JSON="[$(echo "$RUNNING_PROCS" | awk '{printf "\"%s\",", $0}' | sed 's/,$//')]"
    fi
    
    PAYLOAD="{\"token\":\"$TOKEN\",\"hostname\":\"$HOSTNAME\",\"cpu\":$CPU,\"memory\":$MEM,\"running_scripts\":$RUNNING_JSON}"
    
    RESP=$(curl -k -s -X POST "$SERVER_URL/api/agent/heartbeat" \
        -H "Content-Type: application/json" \
        -H "X-Agent-Token: $TOKEN" \
        -d "$PAYLOAD" \
        --connect-timeout 5 \
        --max-time 8 2>/dev/null)
    
    if [ $? -eq 0 ]; then
        log "Heartbeat OK — CPU: ${CPU}% | MEM: ${MEM}%"
    else
        log "Heartbeat FAILED — server unreachable"
    fi
    
    sleep "$HEARTBEAT_INTERVAL"
done
