import argparse
import os
import subprocess
import sys

from agent_executor import execute_task as execute_code_task
from task_queue import (
    DEFAULT_PROJECT,
    list_task_files,
    load_task_file,
    mark_task_completed_real,
    mark_task_failed,
    mark_task_running,
    next_queued_task,
)


class WorkerError(Exception):
    pass


def run(command, cwd, check=True):
    result = subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True)
    if check and result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip()
        raise WorkerError(f"Command failed: {' '.join(command)}\n{output}")
    return result


def slugify(value):
    import re
    import unicodedata

    normalized = unicodedata.normalize("NFKD", str(value))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value).strip("-").lower() or "task"


def safe_branch_name(task):
    return f"ai-company/task-{slugify(task.get('id', 'manual'))}-{slugify(task.get('title', 'task'))[:48]}"


def current_branch(repo_path):
    return run(["git", "branch", "--show-current"], repo_path).stdout.strip()


def git_status(repo_path):
    return run(["git", "status", "--porcelain"], repo_path).stdout.strip()


def ensure_ready(repo_path):
    branch = current_branch(repo_path)
    if branch != "main":
        raise WorkerError(f"Refusing to work: current branch must be main, got {branch}")
    if git_status(repo_path):
        raise WorkerError("Refusing to work: git status is not clean")
    run(["gh", "auth", "status"], repo_path)
    origin = run(["git", "remote", "get-url", "origin"], repo_path).stdout.strip()
    if not origin:
        raise WorkerError("Refusing to work: no remote origin configured")


def branch_exists(repo_path, branch):
    local = run(["git", "show-ref", "--verify", f"refs/heads/{branch}"], repo_path, check=False)
    if local.returncode == 0:
        return True
    remote = run(["git", "ls-remote", "--exit-code", "--heads", "origin", branch], repo_path, check=False)
    return remote.returncode == 0


def unique_branch_name(repo_path, base):
    branch = base
    version = 2
    while branch_exists(repo_path, branch):
        branch = f"{base}-v{version}"
        version += 1
    return branch


def cleanup_uncommitted(repo_path):
    status = git_status(repo_path)
    if not status:
        return
    run(["git", "restore", "--staged", "."], repo_path, check=False)
    tracked = []
    untracked = []
    for line in status.splitlines():
        path = line[3:]
        if line.startswith("?? "):
            untracked.append(path)
        else:
            tracked.append(path)
    if tracked:
        run(["git", "restore", "--worktree", *tracked], repo_path, check=False)
    for path in untracked:
        full = os.path.join(repo_path, path)
        if os.path.isfile(full):
            os.remove(full)


def commit_all(repo_path, message):
    run(["git", "add", "."], repo_path)
    run(["git", "commit", "-m", message], repo_path)


def run_one(project_path, repo_path):
    task_file, task = next_queued_task(project_path)
    if not task:
        print("No queued task found.")
        return False

    print(f"Selected task {task['id']}: {task['title']}")
    print(f"Repo path: {repo_path}")
    print("Running preflight checks...")

    branch = None
    running = False
    try:
        ensure_ready(repo_path)
        branch = unique_branch_name(repo_path, safe_branch_name(task))
        print(f"Creating branch: {branch}")
        run(["git", "checkout", "-b", branch], repo_path)
        task = mark_task_running(task_file, branch)
        running = True
        print(f"Task {task['id']} marked running.")

        files = execute_code_task(task, repo_path)
        print(f"Files changed: {', '.join(files)}")
        commit_all(repo_path, f"AI task: {task['title']}")
        run(["git", "push", "-u", "origin", branch], repo_path)
        pr_url = run([
            "gh", "pr", "create", "--draft", "--base", "main",
            "--title", task["title"], "--body", task["description"],
        ], repo_path).stdout.strip()

        task = mark_task_completed_real(task_file, pr_url)
        commit_all(repo_path, f"AI task status: {task['title']}")
        run(["git", "push", "-u", "origin", branch], repo_path)

    except Exception as exc:
        if running:
            cleanup_uncommitted(repo_path)
            mark_task_failed(task_file, exc)
            try:
                commit_all(repo_path, f"AI task failed: {task['title']}")
                if branch:
                    run(["git", "push", "-u", "origin", branch], repo_path, check=False)
            except Exception:
                pass
        try:
            run(["git", "checkout", "main"], repo_path, check=False)
        except Exception:
            pass
        print(f"Worker failed for task {task['id']}: {exc}", file=sys.stderr)
        return False

    print(f"Task {task['id']} marked completed_real.")
    print(f"Branch pushed: {branch}")
    print(f"Draft PR created: {pr_url}")
    return True


def doctor(project_path, repo_path):
    def maybe(command):
        return run(command, repo_path, check=False)

    branch = maybe(["git", "branch", "--show-current"])
    status = maybe(["git", "status", "--porcelain"])
    auth = maybe(["gh", "auth", "status"])
    queued = 0
    for path in list_task_files(project_path):
        try:
            if load_task_file(path).get("status") == "queued":
                queued += 1
        except Exception:
            pass
    print(f"branche actuelle: {branch.stdout.strip() if branch.returncode == 0 else 'unknown'}")
    print(f"git clean: {'oui' if status.returncode == 0 and not status.stdout.strip() else 'non'}")
    print(f"gh auth: {'ok' if auth.returncode == 0 else 'non'}")
    print(f"tasks queued: {queued}")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run exactly one queued task.")
    parser.add_argument("--limit", type=int, help="Run up to this many queued tasks.")
    parser.add_argument("--doctor", action="store_true", help="Print worker diagnostics.")
    parser.add_argument("--project-path", default=DEFAULT_PROJECT, help="AI Company project path.")
    parser.add_argument("--repo-path", default=os.getcwd(), help="Git repo where the worker commits.")
    args = parser.parse_args()

    limit = 1
    if args.limit is not None:
        if args.limit < 1:
            print("--limit must be >= 1", file=sys.stderr)
            return 2
        limit = args.limit
    if args.once:
        limit = 1

    project_path = os.path.abspath(os.path.expanduser(args.project_path))
    repo_path = os.path.abspath(os.path.expanduser(args.repo_path))

    if args.doctor:
        return doctor(project_path, repo_path)

    completed = 0
    for _ in range(limit):
        if run_one(project_path, repo_path):
            completed += 1
        else:
            break

    print(f"Worker stopped. Completed tasks this run: {completed}")
    return 0 if completed or limit else 1


if __name__ == "__main__":
    raise SystemExit(main())
