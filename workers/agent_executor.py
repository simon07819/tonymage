import os
import re
import unicodedata
from datetime import datetime

def slugify(value):
    normalized = unicodedata.normalize("NFKD", str(value))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value).strip("-").lower()
    return slug or "task"


def task_category(task):
    return task.get("category") or task.get("department") or "general"


def plan_task(task):
    category = task_category(task)
    return [
        f"Clarify the smallest useful {category} deliverable.",
        "Record the implementation scope and first acceptance checks.",
        "Keep the change isolated to the task artifact for review.",
    ]


def target_file_for_task(task):
    category = slugify(task_category(task))
    title = slugify(task.get("title", "task"))
    return os.path.join("docs", category, f"{title}.md")


def execute_minimal_task(project_path, task):
    relative_path = target_file_for_task(task)
    content = render_task_artifact(task)
    write_project_file(project_path, relative_path, content)
    return {
        "plan": plan_task(task),
        "files_changed": [relative_path],
    }


def render_task_artifact(task):
    plan = plan_task(task)
    return (
        f"# {task['title']}\n\n"
        f"Category: {task_category(task)}\n"
        f"Task ID: {task.get('id')}\n"
        f"Generated at: {datetime.utcnow().isoformat()}Z\n\n"
        f"## Scope\n\n{task['description']}\n\n"
        "## Minimal Execution Plan\n\n"
        + "\n".join(f"{index}. {step}" for index, step in enumerate(plan, start=1))
        + "\n\n## Acceptance Criteria\n\n"
        + f"{task.get('acceptance_criteria', 'Define acceptance criteria during implementation.')}\n"
    )


def write_project_file(project_path, relative_path, content):
    normalized = os.path.normpath(relative_path)
    if normalized.startswith("..") or os.path.isabs(normalized):
        raise ValueError(f"Unsafe output path: {relative_path}")

    path = os.path.join(project_path, normalized)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        file.write(content)
