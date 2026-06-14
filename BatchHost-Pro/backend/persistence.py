"""Persistence boundary for execution tracking.

The current app uses JSON files for zero-migration compatibility. The schema
in `db/script.sql` mirrors these records for SQL deployments.
"""

import json
import os
import tempfile
import threading


class JsonStore:
    def __init__(self):
        self.lock = threading.RLock()

    def load(self, path, default=None):
        if default is None:
            default = []
        with self.lock:
            if not os.path.exists(path):
                return default
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)

    def save(self, path, data):
        with self.lock:
            directory = os.path.dirname(path) or "."
            fd, tmp_path = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=directory)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(data, handle, indent=2, default=str)
                os.replace(tmp_path, path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

