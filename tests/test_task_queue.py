import os
import tempfile
import unittest

from task_queue import (
    next_queued_task,
    write_task_file,
)


class TaskQueueTests(unittest.TestCase):
    def test_selects_next_numeric_queued_task_without_dry_run_history(self):
        with tempfile.TemporaryDirectory() as project_path:
            tasks = os.path.join(project_path, "tasks")
            os.makedirs(tasks)
            write_task_file(os.path.join(tasks, "TASK-001.json"), {
                "id": "TASK-001",
                "status": "completed_dry_run",
                "title": "Historical",
            })
            write_task_file(os.path.join(tasks, "2.json"), {
                "id": 2,
                "status": "queued",
                "title": "Second",
            })
            write_task_file(os.path.join(tasks, "1.json"), {
                "id": 1,
                "status": "queued",
                "title": "First",
            })

            task_file, task = next_queued_task(project_path)

        self.assertTrue(task_file.endswith("1.json"))
        self.assertEqual(task["id"], 1)


if __name__ == "__main__":
    unittest.main()
