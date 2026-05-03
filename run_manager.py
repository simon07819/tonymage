import argparse
import os
import subprocess

from task_queue import DEFAULT_PROJECT, list_task_files, load_task_file


def run_cmd(command, repo_path):
    return subprocess.run(command, cwd=repo_path, check=False, capture_output=True, text=True)


def current_branch(repo_path):
    result = run_cmd(["git", "branch", "--show-current"], repo_path)
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def git_clean(repo_path):
    result = run_cmd(["git", "status", "--porcelain"], repo_path)
    return result.returncode == 0 and result.stdout.strip() == ""


def queued_tasks(project_path):
    tasks = []
    for task_file in sorted(list_task_files(project_path), key=task_sort_key):
        task = load_task_file(task_file)
        if task.get("status") == "queued":
            tasks.append((task_file, task))
    return tasks


def task_sort_key(task_file):
    task = load_task_file(task_file)
    task_id = task.get("id")
    if isinstance(task_id, int):
        return (0, task_id)
    if isinstance(task_id, str) and task_id.isdigit():
        return (0, int(task_id))
    return (1, str(task_id))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--project-path", default=DEFAULT_PROJECT)
    parser.add_argument("--repo-path", default=os.getcwd())
    args = parser.parse_args()

    if args.workers < 1:
        print("--workers must be >= 1")
        return 2

    project_path = os.path.abspath(os.path.expanduser(args.project_path))
    repo_path = os.path.abspath(os.path.expanduser(args.repo_path))
    branch = current_branch(repo_path)
    clean = git_clean(repo_path)

    print("AI Company OS run manager simulation")
    print(f"repo path: {repo_path}")
    print(f"current branch: {branch}")
    print(f"git clean: {str(clean).lower()}")
    print(f"workers planned: {args.workers}")

    if branch != "main":
        print("ready: false")
        print("reason: current branch must be main")
        return 1
    if not clean:
        print("ready: false")
        print("reason: git status is not clean")
        return 1

    tasks = queued_tasks(project_path)
    print(f"queued tasks: {len(tasks)}")
    print("virtual assignments:")
    for index in range(args.workers):
        worker = f"worker-{index + 1}"
        if index < len(tasks):
            task_file, task = tasks[index]
            print(f"- {worker}: task {task.get('id')} | {task.get('title')} | {task_file}")
        else:
            print(f"- {worker}: idle")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
