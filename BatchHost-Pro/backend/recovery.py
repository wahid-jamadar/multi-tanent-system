"""Recovery helpers for reconnecting agents and stale executions."""

from .tracking import TIMEOUT_THRESHOLD_SECONDS


def stale_running_executions(executions, seconds_since):
    for execution in executions:
        if execution.get("state") != "RUNNING":
            continue
        age = seconds_since(execution.get("last_seen") or execution.get("started_at"))
        if age is not None and age > TIMEOUT_THRESHOLD_SECONDS:
            yield execution

