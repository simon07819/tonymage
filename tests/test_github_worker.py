import unittest

from workers.github_worker import safe_branch_name


class GitHubWorkerTests(unittest.TestCase):
    def test_safe_branch_name_slugifies_id_and_title(self):
        branch = safe_branch_name({"id": "TASK 42", "title": "Créer l'API + Tests!"})
        self.assertEqual(branch, "ai-company/task-task-42-creer-l-api-tests")


if __name__ == "__main__":
    unittest.main()
