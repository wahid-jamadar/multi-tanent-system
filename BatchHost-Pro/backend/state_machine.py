"""State-machine facade for execution lifecycle validation."""

from .tracking import ALLOWED_TRANSITIONS, EXECUTION_STATES, StateMachineValidator

__all__ = ["ALLOWED_TRANSITIONS", "EXECUTION_STATES", "StateMachineValidator"]

