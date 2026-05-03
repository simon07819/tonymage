import os
import re
import subprocess
import unicodedata
from datetime import datetime


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
    current = _current_branch(project_path, runner)
    if current != "main":
        raise WorkerPreflightError(f"Refusing to work: current branch must be main, got {current}")

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


def current_branch(project_path, runner=default_runner):
    return _current_branch(project_path, runner)


def branch_exists(project_path, branch, runner=default_runner):
    local = runner(["git", "show-ref", "--verify", f"refs/heads/{branch}"], project_path)
    if local.returncode == 0:
        return True

    remote = runner(["git", "ls-remote", "--exit-code", "--heads", "origin", branch], project_path)
    return remote.returncode == 0


def unique_branch_name(project_path, base_branch, runner=default_runner):
    branch = base_branch
    version = 2
    while branch_exists(project_path, branch, runner):
        branch = f"{base_branch}-v{version}"
        version += 1
    return branch


def create_branch(project_path, branch, runner=default_runner):
    _run(["git", "checkout", "-b", branch], project_path, runner)


def has_uncommitted_changes(project_path, runner=default_runner):
    return bool(_run(["git", "status", "--porcelain"], project_path, runner))


def cleanup_uncommitted_changes(project_path, runner=default_runner):
    status = _run(["git", "status", "--porcelain"], project_path, runner)
    if not status:
        return

    _run(["git", "restore", "--staged", "."], project_path, runner)
    tracked_dirty = []
    untracked = []
    for line in status.splitlines():
        path = line[3:]
        if line.startswith("?? "):
            untracked.append(path)
        else:
            tracked_dirty.append(path)

    if tracked_dirty:
        _run(["git", "restore", "--worktree", *tracked_dirty], project_path, runner)
    for path in untracked:
        full_path = os.path.join(project_path, path)
        if os.path.isfile(full_path):
            os.remove(full_path)


def checkout_main(project_path, runner=default_runner):
    _run(["git", "checkout", "main"], project_path, runner)


def write_task_run_summary(project_path, task):
    task_id = _slugify(task.get("id", "task"))
    output_path = os.path.join("generated", "task_runs", f"{task_id}.md")
    _write_project_file(project_path, output_path, _task_summary_content(task))
    return output_path


def _write_project_file(project_path, relative_path, content):
    normalized = os.path.normpath(relative_path)
    if normalized.startswith("..") or os.path.isabs(normalized):
        raise TaskValidationError(f"Unsafe output path: {relative_path}")

    path = os.path.join(project_path, normalized)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        file.write(content)


def _task_summary_content(task):
    return (
        f"# {task['title']}\n\n"
        f"- Task ID: {task.get('id', 'manual')}\n"
        f"- Department: {task.get('department', 'unknown')}\n"
        f"- Status at run: {task.get('status', 'unknown')}\n"
        f"- Generated at: {datetime.utcnow().isoformat()}Z\n"
        f"\n## Description\n\n{task['description']}\n"
        f"\n## Acceptance Criteria\n\n{task.get('acceptance_criteria', 'Not provided.')}\n"
    )


def execute_task(task, project_path, runner=default_runner, preflight=True):
    task = validate_task(task)
    project_path = os.path.abspath(os.path.expanduser(project_path))
    if not os.path.isdir(project_path):
        raise TaskValidationError(f"project_path does not exist: {project_path}")

    branch = task.get("branch") or safe_branch_name(task)

    if branch.split("/")[-1] in PROTECTED_BRANCHES:
        raise WorkerPreflightError(f"Refusing to use protected branch: {branch}")

    if preflight:
        ensure_ready(project_path, runner)

    if _current_branch(project_path, runner) != branch:
        print(f"Creating branch: {branch}")
        create_branch(project_path, branch, runner)
    output_path = write_task_run_summary(project_path, task)
    print(f"Wrote task run summary: {output_path}")

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
        "output_path": output_path,
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
    _run(["git", "push", "-u", "origin", branch], project_path, runner)
    return True
