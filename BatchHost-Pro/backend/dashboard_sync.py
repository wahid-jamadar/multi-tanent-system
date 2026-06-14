"""Dashboard read-model helpers for execution sessions."""

from .tracking import ACTIVE_STATES


def active_execution_count(executions):
    return sum(1 for execution in executions if execution.get("state") in ACTIVE_STATES)


def latest_execution(executions):
    return max(
        executions,
        key=lambda row: row.get("updated_at") or row.get("started_at") or "",
        default=None,
    )

