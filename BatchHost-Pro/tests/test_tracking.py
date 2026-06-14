import unittest

from backend.tracking import ExecutionManager


class ExecutionTrackingTests(unittest.TestCase):
    def setUp(self):
        self.manager = ExecutionManager()
        self.scripts = []
        self.executions = []
        self.events = []
        self.agent = {"id": "agent-1", "hostname": "host-1", "organization_id": "org-1", "os_type": "linux"}

    def event(self, event_type, sequence_number, **extra):
        payload = {
            "event_type": event_type,
            "execution_id": "exec-1",
            "sequence_number": sequence_number,
            "timestamp": f"2026-05-12T10:00:{sequence_number:02d}",
            "script_path": "/tmp/job.sh",
            "script_name": "job.sh",
            "pid": 1234,
        }
        payload.update(extra)
        return self.manager.process_event(self.scripts, self.executions, self.events, self.agent, payload)

    def test_exit_zero_completes(self):
        self.assertTrue(self.event("SCRIPT_STARTED", 1)["accepted"])
        result = self.event("SCRIPT_COMPLETED", 2, exit_code=0)
        self.assertTrue(result["accepted"])
        self.assertEqual(self.executions[0]["state"], "COMPLETED")

    def test_exit_nonzero_fails(self):
        self.assertTrue(self.event("SCRIPT_STARTED", 1)["accepted"])
        result = self.event("SCRIPT_COMPLETED", 2, exit_code=7)
        self.assertTrue(result["accepted"])
        self.assertEqual(self.executions[0]["state"], "FAILED")

    def test_stale_event_rejected(self):
        self.assertTrue(self.event("SCRIPT_STARTED", 1)["accepted"])
        self.assertFalse(self.event("SCRIPT_HEARTBEAT", 1)["accepted"])
        self.assertEqual(self.executions[0]["state"], "RUNNING")

    def test_terminal_cannot_reopen(self):
        self.assertTrue(self.event("SCRIPT_STARTED", 1)["accepted"])
        self.assertTrue(self.event("SCRIPT_COMPLETED", 2, exit_code=0)["accepted"])
        self.assertFalse(self.event("SCRIPT_STARTED", 3)["accepted"])
        self.assertEqual(self.executions[0]["state"], "COMPLETED")

    def test_same_script_can_run_twice_with_distinct_execution_ids(self):
        self.assertTrue(self.event("SCRIPT_STARTED", 1)["accepted"])
        result = self.manager.process_event(self.scripts, self.executions, self.events, self.agent, {
            "event_type": "SCRIPT_STARTED",
            "execution_id": "exec-2",
            "sequence_number": 1,
            "timestamp": "2026-05-12T10:01:00",
            "script_path": "/tmp/job.sh",
            "script_name": "job.sh",
            "pid": 5678,
        })
        self.assertTrue(result["accepted"])
        self.assertEqual(len(self.executions), 2)

    def test_start_with_starting_event(self):
        result = self.event("SCRIPT_STARTING", 1)
        self.assertTrue(result["accepted"])
        self.assertEqual(self.executions[0]["state"], "STARTING")
        result = self.event("SCRIPT_RUNNING", 2)
        self.assertTrue(result["accepted"])
        self.assertEqual(self.executions[0]["state"], "RUNNING")


if __name__ == "__main__":
    unittest.main()
