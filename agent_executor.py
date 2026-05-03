import os
import re
import unicodedata


def execute_task(task, repo_path):
    relative_path = target_file(task)
    write_file(repo_path, relative_path, render_stub(task, relative_path))
    return [relative_path]


def target_file(task):
    slug = slugify(task.get("title", "task"))
    category = task_category(task)
    text = f"{category} {task.get('title', '')}".lower()

    if "backend" in text or "api" in text:
        return os.path.join("backend", f"{slug}.py")
    if "frontend" in text:
        return os.path.join("frontend", f"{slug}.tsx")
    if "database" in text:
        return os.path.join("database", f"{slug}.sql")
    if "testing" in text or "test" in text or "qa" in text:
        return os.path.join("tests", f"test_{slug.replace('-', '_')}.py")
    if "security" in text:
        return os.path.join("security", f"{slug}.py")
    return os.path.join("generated", f"{slug}.txt")


def render_stub(task, relative_path):
    if relative_path.endswith(".tsx"):
        return frontend_stub(task)
    if relative_path.endswith(".sql"):
        return database_stub(task)
    if relative_path.startswith("tests/"):
        return test_stub(task)
    if relative_path.endswith(".py"):
        return python_stub(task)
    return text_stub(task)


def python_stub(task):
    name = slugify(task.get("title", "task")).replace("-", "_")
    return (
        f'"""{task["title"]}.\n\n'
        f'{task["description"]}\n'
        f'"""\n\n'
        f"def {name}():\n"
        f"    return {{\n"
        f"        \"task_id\": {task.get('id')!r},\n"
        f"        \"title\": {task.get('title')!r},\n"
        f"        \"status\": \"stubbed\",\n"
        f"    }}\n"
    )


def frontend_stub(task):
    name = "".join(part.capitalize() for part in slugify(task.get("title", "task")).split("-"))
    return (
        f"export function {name}() {{\n"
        f"  return <section data-task-id=\"{task.get('id')}\">{task.get('title')}</section>;\n"
        f"}}\n"
    )


def database_stub(task):
    slug = slugify(task.get("title", "task")).replace("-", "_")
    return (
        f"-- {task['title']}\n"
        f"-- {task['description']}\n\n"
        f"CREATE TABLE IF NOT EXISTS {slug} (\n"
        f"  id INTEGER PRIMARY KEY,\n"
        f"  created_at TEXT NOT NULL\n"
        f");\n"
    )


def test_stub(task):
    name = slugify(task.get("title", "task")).replace("-", "_")
    return (
        f'"""Tests for {task["title"]}."""\n\n'
        f"def test_{name}_stub():\n"
        f"    assert {task.get('id')!r} is not None\n"
    )


def text_stub(task):
    return f"{task['title']}\n\n{task['description']}\n"


def write_file(repo_path, relative_path, content):
    normalized = os.path.normpath(relative_path)
    if normalized.startswith("..") or os.path.isabs(normalized):
        raise ValueError(f"Unsafe output path: {relative_path}")

    path = os.path.join(repo_path, normalized)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        file.write(content)


def task_category(task):
    return task.get("category") or task.get("department") or ""


def slugify(value):
    normalized = unicodedata.normalize("NFKD", str(value))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value).strip("-").lower()
    return slug or "task"
