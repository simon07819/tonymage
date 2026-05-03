import os
import re
import unicodedata


def execute_task(task, repo_path):
    path = target_file(task)
    write_file(repo_path, path, render_stub(task, path))
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
    title = task.get("title", "Untitled task")
    description = task.get("description", "")
    if path.endswith(".tsx"):
        name = "".join(part.capitalize() for part in slugify(title).split("-"))
        return f"export function {name}() {{\n  return null;\n}}\n"
    if path.endswith(".sql"):
        table = slugify(title).replace("-", "_")
        return f"-- {title}\n-- {description}\nCREATE TABLE IF NOT EXISTS {table} (id INTEGER PRIMARY KEY);\n"
    if path.startswith("tests/"):
        name = slugify(title).replace("-", "_")
        return f"def test_{name}_stub():\n    assert True\n"
    if path.endswith(".py"):
        name = slugify(title).replace("-", "_")
        return f'"""{title}: {description}"""\n\n\ndef {name}():\n    return {{\"status\": \"stubbed\"}}\n'
    return f"{title}\n{description}\n"


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
