import unittest
from types import SimpleNamespace

from workers.github_worker import unique_branch_name


def result(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class GitHubWorkerTests(unittest.TestCase):
    def test_existing_branch_gets_v2_suffix(self):
        def runner(command, cwd):
            if command == ["git", "show-ref", "--verify", "refs/heads/ai-company/task-1-build"]:
                return result()
            return result(returncode=1)

        branch = unique_branch_name("/tmp/repo", "ai-company/task-1-build", runner=runner)
        self.assertEqual(branch, "ai-company/task-1-build-v2")


if __name__ == "__main__":
    unittest.main()
