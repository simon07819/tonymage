import unittest
from types import SimpleNamespace

from workers.github_worker import WorkerPreflightError, ensure_ready, unique_branch_name


def result(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class GitHubWorkerTests(unittest.TestCase):
    def test_refuses_when_current_branch_is_not_main(self):
        def runner(command, cwd):
            if command == ["git", "branch", "--show-current"]:
                return result(stdout="feature/work\n")
            if command == ["git", "status", "--porcelain"]:
                return result(stdout="")
            return result()

        with self.assertRaisesRegex(WorkerPreflightError, "must be main"):
            ensure_ready("/tmp/repo", runner=runner)

    def test_unique_branch_name_adds_version_suffix(self):
        existing = {
            ("git", "show-ref", "--verify", "refs/heads/ai-company/task-1-build"),
            ("git", "ls-remote", "--exit-code", "--heads", "origin", "ai-company/task-1-build-v2"),
        }

        def runner(command, cwd):
            if tuple(command) in existing:
                return result()
            return result(returncode=1)

        branch = unique_branch_name("/tmp/repo", "ai-company/task-1-build", runner=runner)
        self.assertEqual(branch, "ai-company/task-1-build-v3")


if __name__ == "__main__":
    unittest.main()
