import argparse
import os
import subprocess
import sys

from task_queue import (
    DEFAULT_PROJECT,
    list_task_files,
    load_task_file,
    mark_task_completed_real,
    mark_task_failed,
    mark_task_running,
    next_queued_task,
)
from workers.github_worker import GitHubWorkerError, safe_branch_name


def run_cmd(command, repo_path, check=True):
    result = subprocess.run(command, cwd=repo_path, check=False, capture_output=True, text=True)
    if check and result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip()
        raise GitHubWorkerError(f"Command failed: {' '.join(command)}\n{output}")
    return result


def current_branch(repo_path):
    return run_cmd(["git", "branch", "--show-current"], repo_path).stdout.strip()


def git_clean(repo_path):
    return run_cmd(["git", "status", "--porcelain"], repo_path).stdout.strip() == ""


def gh_auth_ok(repo_path):
    return run_cmd(["gh", "auth", "status"], repo_path, check=False).returncode == 0


def preflight(repo_path):
    branch = current_branch(repo_path)
    if branch != "main":
        raise GitHubWorkerError(f"Refusing to work: current branch must be main, got {branch}")
    if not git_clean(repo_path):
        raise GitHubWorkerError("Refusing to work: git status is not clean")
    if not gh_auth_ok(repo_path):
        raise GitHubWorkerError("GitHub CLI authentication failed. Run: gh auth login")
    origin = run_cmd(["git", "remote", "get-url", "origin"], repo_path).stdout.strip()
    if not origin:
        raise GitHubWorkerError("Refusing to work: no remote origin configured")


def branch_exists(repo_path, branch):
    local = run_cmd(["git", "show-ref", "--verify", f"refs/heads/{branch}"], repo_path, check=False)
    if local.returncode == 0:
        return True
    remote = run_cmd(["git", "ls-remote", "--exit-code", "--heads", "origin", branch], repo_path, check=False)
    return remote.returncode == 0


def remote_branch_exists(repo_path, branch):
    remote = run_cmd(["git", "ls-remote", "--exit-code", "--heads", "origin", branch], repo_path, check=False)
    return remote.returncode == 0


def unique_branch(repo_path, base_branch):
    branch = base_branch
    version = 2
    while branch_exists(repo_path, branch):
        branch = f"{base_branch}-v{version}"
        version += 1
    return branch


def checkout_new_branch(repo_path, branch):
    run_cmd(["git", "checkout", "-b", branch], repo_path)


def checkout_main(repo_path):
    run_cmd(["git", "checkout", "main"], repo_path, check=False)


def cleanup_dirty(repo_path):
    status = run_cmd(["git", "status", "--porcelain"], repo_path, check=False).stdout
    if not status.strip():
        return
    run_cmd(["git", "restore", "--staged", "."], repo_path, check=False)
    tracked = []
    untracked = []
    for line in status.splitlines():
        path = line[3:]
        if line.startswith("?? "):
            untracked.append(path)
        else:
            tracked.append(path)
    if tracked:
        run_cmd(["git", "restore", "--worktree", *tracked], repo_path, check=False)
    for path in untracked:
        full_path = os.path.join(repo_path, path)
        if os.path.isfile(full_path):
            os.remove(full_path)


def commit_all(repo_path, message):
    run_cmd(["git", "add", "."], repo_path)
    run_cmd(["git", "commit", "-m", message], repo_path)


def write_task_code(repo_path, task):
    slug = safe_branch_name(task).split("/")[-1]
    path = os.path.join("backend", f"{slug}.py")
    full_path = os.path.join(repo_path, path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as file:
        file.write(f'"""{task["title"]}: {task["description"]}"""\n\n')
        file.write("def run():\n    return {'status': 'stubbed'}\n")
    return [path]


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
        preflight(repo_path)
        branch = unique_branch(repo_path, safe_branch_name(task))
        print(f"Creating branch: {branch}")
        checkout_new_branch(repo_path, branch)
        task = mark_task_running(task_file, branch)
        running = True
        print(f"Task {task['id']} marked running.")

        files_changed = write_task_code(repo_path, task)
        print(f"Files changed: {', '.join(files_changed)}")
        if remote_branch_exists(repo_path, branch):
            branch = unique_branch(repo_path, safe_branch_name(task))
            print(f"Branch appeared on origin before push; using {branch}")
            run_cmd(["git", "branch", "-m", branch], repo_path)
            task = mark_task_running(task_file, branch)

        commit_all(repo_path, f"AI task: {task['title']}")
        if remote_branch_exists(repo_path, branch):
            branch = unique_branch(repo_path, safe_branch_name(task))
            print(f"Remote branch exists before push; renaming to {branch}")
            run_cmd(["git", "branch", "-m", branch], repo_path)
            task = mark_task_running(task_file, branch)
            commit_all(repo_path, f"AI task branch: {task['title']}")
        run_cmd(["git", "push", "-u", "origin", branch], repo_path)
        pr_url = run_cmd([
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
        ], repo_path).stdout.strip()

        task = mark_task_completed_real(task_file, pr_url)
        commit_all(repo_path, f"AI task status: {task['title']}")
        run_cmd(["git", "push", "-u", "origin", branch], repo_path)

    except GitHubWorkerError as exc:
        if running:
            cleanup_dirty(repo_path)
            mark_task_failed(task_file, exc)
            try:
                commit_all(repo_path, f"AI task failed: {task['title']}")
                if branch and not branch_exists(repo_path, branch):
                    run_cmd(["git", "push", "-u", "origin", branch], repo_path, check=False)
            except Exception:
                cleanup_dirty(repo_path)
        checkout_main(repo_path)
        print(f"Worker failed for task {task['id']}: {exc}", file=sys.stderr)
        return False

    print(f"Task {task['id']} marked completed_real.")
    print(f"Branch pushed: {branch}")
    print(f"Draft PR created: {pr_url}")
    return True


def doctor(project_path, repo_path):
    queued = 0
    for task_file in list_task_files(project_path):
        try:
            if load_task_file(task_file).get("status") == "queued":
                queued += 1
        except Exception:
            pass
    print(f"current branch: {current_branch(repo_path)}")
    print(f"git clean: {str(git_clean(repo_path)).lower()}")
    print(f"gh auth ok: {str(gh_auth_ok(repo_path)).lower()}")
    print(f"queued tasks count: {queued}")
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
