import argparse
import os
import sys

from task_queue import (
    DEFAULT_PROJECT,
    load_task_file,
    mark_task_completed_real,
    mark_task_failed,
    mark_task_running,
    next_queued_task,
)
from workers.github_worker import (
    GitHubWorkerError,
    cleanup_uncommitted_changes,
    commit_and_push_status_update,
    ensure_ready,
    execute_task,
    has_uncommitted_changes,
    safe_branch_name,
    unique_branch_name,
)


def run_one(project_path, repo_path):
    task_file, task = next_queued_task(project_path)
    if not task:
        print("No queued task found.")
        return False

    print(f"Selected task {task['id']}: {task['title']}")
    print(f"Repo path: {repo_path}")
    print("Running preflight checks...")

    started = False
    try:
        ensure_ready(repo_path)
        branch = unique_branch_name(repo_path, safe_branch_name(task))
        task = mark_task_running(task_file, branch)
        started = True
        print(f"Task {task['id']} marked running.")

        result = execute_task(task, repo_path, preflight=False)
        task = mark_task_completed_real(task_file, result["pr_url"])
        commit_and_push_status_update(repo_path, task, result["branch"])

    except GitHubWorkerError as exc:
        if started and has_uncommitted_changes(repo_path):
            cleanup_uncommitted_changes(repo_path)
            print(f"Task {task['id']} restored after pre-commit failure.")
        elif started:
            mark_task_failed(task_file, exc)
            commit_and_push_status_update(repo_path, load_task_file(task_file), task["branch"])
        print(f"Worker failed for task {task['id']}: {exc}", file=sys.stderr)
        return False

    print(f"Task {task['id']} marked completed_real.")
    print(f"Branch pushed: {result['branch']}")
    print(f"Draft PR created: {result['pr_url']}")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run exactly one queued task.")
    parser.add_argument("--limit", type=int, help="Run up to this many queued tasks.")
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
