import os
import re
import unicodedata


def execute_task(task, repo_path):
    path = target_file(task)
    content = render_stub(task, path)
    write_file(repo_path, path, content)
    return [path]


def target_file(task):
    slug = slugify(task.get("title", "task"))
    text = f"{task.get('category', '')} {task.get('department', '')} {task.get('title', '')}".lower()
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


def render_stub(task, path):
    if path.endswith(".tsx"):
        name = "".join(part.capitalize() for part in slugify(task.get("title", "task")).split("-"))
        return f"export function {name}() {{\n  return null;\n}}\n"
    if path.endswith(".sql"):
        table = slugify(task.get("title", "task")).replace("-", "_")
        return f"-- {task['title']}\nCREATE TABLE IF NOT EXISTS {table} (id INTEGER PRIMARY KEY);\n"
    if path.startswith("tests/"):
        name = slugify(task.get("title", "task")).replace("-", "_")
        return f"def test_{name}_stub():\n    assert True\n"
    if path.endswith(".py"):
        name = slugify(task.get("title", "task")).replace("-", "_")
        return (
            f'"""{task["title"]}: {task["description"]}"""\n\n'
            f"def {name}():\n"
            f"    return {{'task_id': {task.get('id')!r}, 'status': 'stubbed'}}\n"
        )
    return f"{task['title']}\n{task['description']}\n"


def write_file(repo_path, relative_path, content):
    normalized = os.path.normpath(relative_path)
    if normalized.startswith("..") or os.path.isabs(normalized):
        raise ValueError(f"Unsafe path: {relative_path}")
    path = os.path.join(repo_path, normalized)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        file.write(content)


def slugify(value):
    normalized = unicodedata.normalize("NFKD", str(value))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value).strip("-").lower() or "task"
