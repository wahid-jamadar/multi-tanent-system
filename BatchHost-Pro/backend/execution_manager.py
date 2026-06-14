"""Execution manager facade.

The implementation lives in `backend.tracking` to preserve existing imports
while exposing a cleaner module boundary for new code.
"""

from .tracking import ExecutionManager

__all__ = ["ExecutionManager"]

