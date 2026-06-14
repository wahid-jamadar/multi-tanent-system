"""Process tracking contract.

PID tracking is performed on the agent, close to the operating system process
table. The server trusts explicit agent lifecycle events after sequence and
state-machine validation.
"""


class ProcessTracker:
    def is_alive(self, pid):
        raise NotImplementedError

