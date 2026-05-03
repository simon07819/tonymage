import os
import tempfile
import unittest

from workers.agent_executor import execute_minimal_task, target_file_for_task


class AgentExecutorTests(unittest.TestCase):
    def test_executes_task_into_category_artifact(self):
        task = {
            "id": 11,
            "title": "Implement Security Measures",
            "department": "Security",
            "description": "Develop security measures for project data storage and API endpoints.",
            "acceptance_criteria": "Security measures are fully functional and secure.",
        }

        with tempfile.TemporaryDirectory() as project_path:
            result = execute_minimal_task(project_path, task)
            expected = os.path.join("docs", "security", "implement-security-measures.md")
            path = os.path.join(project_path, expected)

            self.assertEqual(target_file_for_task(task), expected)
            self.assertEqual(result["files_changed"], [expected])
            self.assertTrue(os.path.exists(path))
            self.assertFalse(os.path.exists(os.path.join(project_path, "generated", "task_runs", "11.md")))


if __name__ == "__main__":
    unittest.main()
