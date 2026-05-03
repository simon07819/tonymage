import os
import tempfile
import unittest
from unittest.mock import patch

from task_queue import (
    mark_task_completed_real,
    mark_task_running,
    write_task_file,
)


class TaskQueueTests(unittest.TestCase):
    def test_transition_queued_running_completed_real(self):
        with tempfile.TemporaryDirectory() as project_path:
            task_file = self._task_file(project_path)
            write_task_file(task_file, {
                "id": 1,
                "status": "queued",
                "title": "Implement Feature",
                "description": "Do the smallest safe real run.",
            })

            with patch("task_queue.utc_now", return_value="2026-05-03T00:00:00"):
                running = mark_task_running(task_file, "ai-company/task-1-implement-feature")
                completed = mark_task_completed_real(task_file, "https://github.com/acme/repo/pull/1")

        self.assertEqual(running["status"], "running")
        self.assertEqual(completed["status"], "completed_real")
        self.assertEqual(completed["mode"], "REAL")
        self.assertEqual(completed["pr_url"], "https://github.com/acme/repo/pull/1")

    def _task_file(self, project_path):
        tasks = os.path.join(project_path, "tasks")
        os.makedirs(tasks)
        return os.path.join(tasks, "1.json")


if __name__ == "__main__":
    unittest.main()
