import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import run_worker
from task_queue import load_task_file, write_task_file
from workers.github_worker import WorkerPreflightError


def result(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class RunWorkerTests(unittest.TestCase):
    def test_does_not_mark_running_when_branch_creation_fails(self):
        with tempfile.TemporaryDirectory() as project_path:
            tasks = os.path.join(project_path, "tasks")
            os.makedirs(tasks)
            task_file = os.path.join(tasks, "1.json")
            write_task_file(task_file, {
                "id": 1,
                "title": "Build API",
                "description": "Build a minimal API.",
                "status": "queued",
            })

            with patch("run_worker.ensure_ready"), \
                patch("run_worker.unique_branch_name", return_value="ai-company/task-1-build-api"), \
                patch("run_worker.create_branch", side_effect=WorkerPreflightError("branch failed")):
                ok = run_worker.run_one(project_path, "/tmp/repo")

            self.assertFalse(ok)
            self.assertEqual(load_task_file(task_file)["status"], "queued")

    def test_doctor_does_not_crash(self):
        with tempfile.TemporaryDirectory() as project_path:
            os.makedirs(os.path.join(project_path, "tasks"))

            def runner(command, cwd):
                if command == ["git", "branch", "--show-current"]:
                    return result(stdout="main\n")
                if command == ["git", "remote", "get-url", "origin"]:
                    return result(stdout="https://github.com/example/repo.git\n")
                return result()

            self.assertEqual(run_worker.doctor(project_path, "/tmp/repo", runner=runner), 0)


if __name__ == "__main__":
    unittest.main()
