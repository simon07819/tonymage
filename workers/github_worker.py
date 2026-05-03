import os
import re
import subprocess
import unicodedata

from agent_executor import execute_task as execute_code_task


PROTECTED_BRANCHES = {"main", "master"}


class GitHubWorkerError(Exception):
    pass


class TaskValidationError(GitHubWorkerError):
    pass


class WorkerPreflightError(GitHubWorkerError):
    pass


def _slugify(value):
    normalized = unicodedata.normalize("NFKD", str(value))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value).strip("-").lower()
    return slug or "task"


def safe_branch_name(task):
    task_id = _slugify(task.get("id", "manual"))[:32]
    title_slug = _slugify(task.get("title", "task"))[:48]
    return f"ai-company/task-{task_id}-{title_slug}"


def validate_task(task):
    required = ("id", "title", "description")
    missing = [key for key in required if not task.get(key)]
    if missing:
        raise TaskValidationError(f"Task missing required fields: {', '.join(missing)}")

    return task


def default_runner(command, cwd):
    return subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def _run(command, cwd, runner=default_runner):
    result = runner(command, cwd)
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip()
        raise WorkerPreflightError(f"Command failed: {' '.join(command)}\n{output}")
    return result.stdout.strip()


def ensure_ready(project_path, runner=default_runner):
    status = _run(["git", "status", "--porcelain"], project_path, runner)
    if status:
        raise WorkerPreflightError("Refusing to work: git status is not clean")

    try:
        _run(["gh", "auth", "status"], project_path, runner)
    except WorkerPreflightError as exc:
        raise WorkerPreflightError(
            "GitHub CLI authentication failed. Run: gh auth login"
        ) from exc

    try:
        origin = _run(["git", "remote", "get-url", "origin"], project_path, runner)
    except WorkerPreflightError as exc:
        raise WorkerPreflightError(
            "Refusing to work: no remote origin configured"
        ) from exc
    if not origin:
        raise WorkerPreflightError("Refusing to work: no remote origin configured")


def _current_branch(project_path, runner=default_runner):
    return _run(["git", "branch", "--show-current"], project_path, runner)


def execute_task(task, project_path, runner=default_runner, preflight=True):
    task = validate_task(task)
    project_path = os.path.abspath(os.path.expanduser(project_path))
    if not os.path.isdir(project_path):
        raise TaskValidationError(f"project_path does not exist: {project_path}")

    branch = safe_branch_name(task)

    if branch.split("/")[-1] in PROTECTED_BRANCHES:
        raise WorkerPreflightError(f"Refusing to use protected branch: {branch}")

    if preflight:
        ensure_ready(project_path, runner)

    print(f"Creating branch: {branch}")
    _run(["git", "checkout", "-b", branch], project_path, runner)
    files_changed = execute_code_task(task, project_path)
    print(f"Files changed: {', '.join(files_changed)}")

    status_after = _run(["git", "status", "--porcelain"], project_path, runner)
    if not status_after:
        raise WorkerPreflightError("No file changes were produced for this task")

    current = _current_branch(project_path, runner)
    if current in PROTECTED_BRANCHES:
        raise WorkerPreflightError(f"Refusing to push protected branch: {current}")

    _run(["git", "add", "."], project_path, runner)
    _run(["git", "commit", "-m", f"AI task: {task['title']}"], project_path, runner)
    _run(["git", "push", "-u", "origin", branch], project_path, runner)
    pr_url = _run(
        [
            "gh",
            "pr",
            "create",
            "--draft",
            "--base",
            "main",
            "--title",
            task["title"],
            "--body",
            task["description"],
        ],
        project_path,
        runner,
    )

    return {
        "task_id": task.get("id"),
        "branch": branch,
        "pr_url": pr_url,
        "files_changed": files_changed,
    }


def commit_and_push_status_update(project_path, task, branch, runner=default_runner):
    status = _run(["git", "status", "--porcelain"], project_path, runner)
    if not status:
        return False

    current = _current_branch(project_path, runner)
    if current in PROTECTED_BRANCHES:
        raise WorkerPreflightError(f"Refusing to push protected branch: {current}")
    if current != branch:
        raise WorkerPreflightError(f"Refusing to push status update from unexpected branch: {current}")

    _run(["git", "add", "."], project_path, runner)
    _run(
        ["git", "commit", "-m", f"AI task status: {task['title']}"],
        project_path,
        runner,
    )
    _run(["git", "push"], project_path, runner)
    return True
