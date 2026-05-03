import json
import os
from datetime import datetime


BASE = os.path.expanduser("~/AI-Company")
DEFAULT_PROJECT = os.path.join(BASE, "projects", "Tonymage")


def utc_now():
    return datetime.utcnow().isoformat()


def tasks_dir(project_path=DEFAULT_PROJECT):
    return os.path.join(project_path, "tasks")


def load_task_file(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def write_task_file(path, task):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(task, file, indent=2)
        file.write("\n")


def list_task_files(project_path=DEFAULT_PROJECT):
    path = tasks_dir(project_path)
    if not os.path.isdir(path):
        return []
    return [
        os.path.join(path, filename)
        for filename in os.listdir(path)
        if filename.endswith(".json")
    ]


def _task_sort_key(task_file):
    task = load_task_file(task_file)
    task_id = task.get("id")
    priority_order = {
        "urgent": 0,
        "high": 1,
        "normal": 2,
        "low": 3,
    }
    priority = priority_order.get(task.get("priority", "normal"), 2)
    if isinstance(task_id, int):
        return (priority, 0, task_id)
    if isinstance(task_id, str) and task_id.isdigit():
        return (priority, 0, int(task_id))
    return (priority, 1, str(task_id))


def next_queued_task(project_path=DEFAULT_PROJECT):
    for task_file in sorted(list_task_files(project_path), key=_task_sort_key):
        task = load_task_file(task_file)
        if task.get("status") == "queued":
            return task_file, task
    return None, None


def mark_task_running(task_file, branch):
    task = load_task_file(task_file)
    task["status"] = "running"
    task["mode"] = "REAL"
    task["branch"] = branch
    task["started_at"] = utc_now()
    write_task_file(task_file, task)
    return task


def mark_task_completed_real(task_file, pr_url):
    task = load_task_file(task_file)
    task["status"] = "completed_real"
    task["mode"] = "REAL"
    task["pr_url"] = pr_url
    task["completed_at"] = utc_now()
    task.pop("error", None)
    write_task_file(task_file, task)
    return task


def mark_task_failed(task_file, error):
    task = load_task_file(task_file)
    task["status"] = "failed"
    task["mode"] = "REAL"
    task["error"] = str(error)
    task["failed_at"] = utc_now()
    write_task_file(task_file, task)
    return task
