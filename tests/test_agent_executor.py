import os
import tempfile
import unittest

from agent_executor import execute_task, target_file


class AgentExecutorTests(unittest.TestCase):
    def test_executes_backend_task_into_source_file(self):
        task = {
            "id": 11,
            "title": "Implement API Endpoints",
            "department": "Backend",
            "description": "Develop security measures for project data storage and API endpoints.",
            "acceptance_criteria": "Security measures are fully functional and secure.",
        }

        with tempfile.TemporaryDirectory() as project_path:
            result = execute_task(task, project_path)
            expected = os.path.join("backend", "implement-api-endpoints.py")
            path = os.path.join(project_path, expected)

            self.assertEqual(target_file(task), expected)
            self.assertEqual(result, [expected])
            self.assertTrue(os.path.exists(path))
            self.assertFalse(os.path.exists(os.path.join(project_path, "docs", "backend")))


if __name__ == "__main__":
    unittest.main()
