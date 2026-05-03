import unittest
from types import SimpleNamespace

from workers.github_worker import WorkerPreflightError, ensure_ready, unique_branch_name


def result(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class GitHubWorkerTests(unittest.TestCase):
    def test_refuses_dirty_git_before_work(self):
        def runner(command, cwd):
            if command == ["git", "branch", "--show-current"]:
                return result(stdout="main\n")
            if command == ["git", "status", "--porcelain"]:
                return result(stdout=" M changed.py\n")
            return result()

        with self.assertRaisesRegex(WorkerPreflightError, "not clean"):
            ensure_ready("/tmp/repo", runner=runner)

    def test_existing_remote_branch_gets_v2_suffix(self):
        def runner(command, cwd):
            if command == ["git", "ls-remote", "--exit-code", "--heads", "origin", "ai-company/task-3-build"]:
                return result()
            return result(returncode=1)

        branch = unique_branch_name("/tmp/repo", "ai-company/task-3-build", runner=runner)
        self.assertEqual(branch, "ai-company/task-3-build-v2")


if __name__ == "__main__":
    unittest.main()
