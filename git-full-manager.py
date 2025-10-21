#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified GitHub Manager + Local Sync — Ultimate Edition
All features active:
 - Auto dependency install
 - Auto GitHub auth via .env
 - Full repo CRUD (create, rename, delete, list)
 - Tokenized HTTPS remotes for private repos
 - Local + workspace clone/sync/pull/push
 - Auto branch alignment (main/master fix)
 - Smart file/folder upload
 - Rich CLI interface with logging
"""

from __future__ import annotations
import os
import sys
import subprocess
from datetime import datetime
from typing import Optional, List

# ---------------------------
# Auto-install missing deps
# ---------------------------
REQS = {
    "git": "GitPython",
    "github": "PyGithub",
    "dotenv": "python-dotenv",
    "rich": "rich",
    "requests": "requests",
}
for mod, pkg in REQS.items():
    try:
        __import__(mod)
    except Exception:
        print(f"[info] Installing missing package: {pkg} ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

# ---------------------------
# Imports after install
# ---------------------------
from github import Github, Auth, GithubException
from dotenv import load_dotenv
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.panel import Panel
import requests

# === CONFIG ===
ENV_PATH = "/home/gost/account/.env"
REPO_PATH = "/home/gost/7heBlackLand"
DEFAULT_COMMIT_MSG = "Welcome to Blackland"
LOG_FILE = "/home/gost/all-project/git-all/git_actions.log"

# === Load .env and authenticate ===
load_dotenv(dotenv_path=ENV_PATH)
TOKEN = os.getenv("GITHUB_TOKEN")
console = Console()

if not TOKEN:
    console.print("[bold red]❌ Missing GITHUB_TOKEN in .env file[/bold red]")
    sys.exit(1)

try:
    auth = Auth.Token(TOKEN)
    gh = Github(auth=auth)
    user = gh.get_user()
    console.print(f"✅ Authenticated as [green]{user.login}[/green]\n")
except Exception as e:
    console.print(f"[bold red]GitHub authentication failed: {e}[/bold red]")
    sys.exit(1)


# ---------------------------
# Logging
# ---------------------------
def log_action(action: str):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {action}\n")


# ---------------------------
# Shell helper
# ---------------------------
def run_shell(cmd: List[str], cwd: Optional[str] = None, silent=False):
    if not silent:
        console.print(f"🚀 {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


# ---------------------------
# Ensure git identity
# ---------------------------
def ensure_git_identity():
    try:
        name = subprocess.check_output(["git", "config", "--global", "user.name"], text=True).strip()
        email = subprocess.check_output(["git", "config", "--global", "user.email"], text=True).strip()
        if name and email:
            return
    except subprocess.CalledProcessError:
        pass
    console.print("⚙️ Setting default git identity...")
    subprocess.run(["git", "config", "--global", "user.name", "Auto Commit Bot"])
    subprocess.run(["git", "config", "--global", "user.email", "autocommit@example.com"])
    log_action("Set default git identity.")


ensure_git_identity()

# ---------------------------
# Utility helpers
# ---------------------------
def get_default_branch(repo_name: str) -> str:
    """Fetch default branch name from GitHub API"""
    url = f"https://api.github.com/repos/{user.login}/{repo_name}"
    headers = {"Authorization": f"token {TOKEN}"}
    try:
        r = requests.get(url, headers=headers)
        if r.ok:
            return r.json().get("default_branch", "main")
    except Exception:
        pass
    return "main"


def fix_remote_with_token(repo_path: str):
    """Ensure HTTPS remote has token for private repos."""
    try:
        url = subprocess.check_output(["git", "-C", repo_path, "remote", "get-url", "origin"], text=True).strip()
        if "@" not in url and url.startswith("https://"):
            new_url = url.replace("https://", f"https://{TOKEN}@")
            subprocess.run(["git", "-C", repo_path, "remote", "set-url", "origin", new_url])
    except Exception:
        pass


def ensure_branch_alignment(repo_path: str, repo_name: str):
    """Auto-fix local branch mismatch (main/master)."""
    try:
        default_branch = get_default_branch(repo_name)
        local_branch = subprocess.check_output(
            ["git", "-C", repo_path, "rev-parse", "--abbrev-ref", "HEAD"], text=True
        ).strip()
        if local_branch != default_branch:
            console.print(f"🔁 Aligning branch from {local_branch} → {default_branch}")
            subprocess.run(["git", "-C", repo_path, "fetch", "origin", default_branch], check=False)
            subprocess.run(["git", "-C", repo_path, "checkout", default_branch], check=False)
            subprocess.run(["git", "-C", repo_path, "branch", "--set-upstream-to", f"origin/{default_branch}"], check=False)
            log_action(f"Aligned {repo_name} branch {local_branch} → {default_branch}")
    except Exception:
        pass


# ---------------------------
# Core GitHub functions
# ---------------------------
def list_repos():
    repos = list(user.get_repos())
    table = Table(title="Your Repositories")
    table.add_column("No", justify="center")
    table.add_column("Name", style="cyan")
    table.add_column("Private", justify="center")
    for i, r in enumerate(repos, 1):
        table.add_row(str(i), r.name, "🔒" if r.private else "🌍")
    console.print(table)
    return repos


def create_repo():
    name = Prompt.ask("Enter new repository name")
    private = Confirm.ask("Make it private?", default=True)
    try:
        repo = user.create_repo(name, private=private)
        console.print(f"✅ Created: [green]{repo.full_name}[/green]")
        log_action(f"Created repo {repo.full_name}")
    except GithubException as e:
        console.print(f"[red]Failed to create repo: {e}[/red]")


def rename_repo():
    repos = list_repos()
    idx = int(Prompt.ask("Enter repo number to rename"))
    new_name = Prompt.ask("New name")
    repo = repos[idx - 1]
    repo.edit(name=new_name)
    console.print(f"✅ Renamed to {new_name}")
    log_action(f"Renamed {repo.name} → {new_name}")


def delete_repo():
    repos = list_repos()
    idx = int(Prompt.ask("Enter repo number to delete"))
    repo = repos[idx - 1]
    if Confirm.ask(f"Are you sure you want to delete {repo.name}?", default=False):
        repo.delete()
        console.print(f"🗑️ Deleted {repo.name}")
        log_action(f"Deleted repo {repo.name}")


# ---------------------------
# Local Operations
# ---------------------------
def clone_repositories_to_workspace():
    os.makedirs(REPO_PATH, exist_ok=True)
    repos = list(user.get_repos())
    console.print("[bold cyan]Clone Options:[/bold cyan]\n1) All\n2) Choose Specific\n3) Cancel")
    ch = Prompt.ask("Choice", default="3")
    if ch == "3": return

    to_clone = repos if ch == "1" else []
    if ch == "2":
        table = Table(title="Select Repositories")
        table.add_column("No")
        table.add_column("Name", style="cyan")
        for i, r in enumerate(repos, 1): table.add_row(str(i), r.name)
        console.print(table)
        raw = Prompt.ask("Enter numbers (comma-separated)")
        idxs = [int(x.strip()) for x in raw.split(",")]
        to_clone = [repos[i - 1] for i in idxs]

    for r in to_clone:
        local_path = os.path.join(REPO_PATH, r.name)
        if os.path.exists(local_path):
            console.print(f"⚠️ Skipping {r.name} (already exists)")
            continue
        url = r.clone_url.replace("https://", f"https://{TOKEN}@")
        console.print(f"🔽 Cloning {r.name} ...")
        run_shell(["git", "clone", url, local_path], silent=True)
        log_action(f"Cloned {r.name}")


def batch_git_manager():
    if not os.path.isdir(REPO_PATH):
        console.print("[red]Workspace missing![/red]")
        return
    repos = [d for d in os.listdir(REPO_PATH) if os.path.isdir(os.path.join(REPO_PATH, d, ".git"))]
    if not repos:
        console.print("[red]No local repos found.[/red]")
        return

    console.print("""
[bold cyan]Batch Operations[/bold cyan]
1) Pull all
2) Push all
3) Sync all
4) Cancel
""")
    ch = Prompt.ask("Choice", default="4")
    if ch == "4": return
    msg = DEFAULT_COMMIT_MSG if ch in ("2", "3") else None

    for r in repos:
        path = os.path.join(REPO_PATH, r)
        console.print(f"\n📂 [green]{r}[/green]")
        fix_remote_with_token(path)
        ensure_branch_alignment(path, r)
        try:
            if ch in ("1", "3"):
                console.print("🔄 Pulling...")
                run_shell(["git", "-C", path, "pull"], silent=True)
            if ch in ("2", "3"):
                run_shell(["git", "-C", path, "add", "."], silent=True)
                commit = subprocess.run(["git", "-C", path, "commit", "-m", msg])
                if commit.returncode == 0:
                    run_shell(["git", "-C", path, "push"], silent=True)
                    console.print("✅ Pushed!")
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Error in {r}: {e}[/red]")


# ---------------------------
# Main menu
# ---------------------------
def main_menu():
    while True:
        console.rule("[bold magenta]Unified GitHub Manager[/bold magenta]")
        console.print(f"Workspace: [green]{REPO_PATH}[/green]\n")
        console.print("""
1) Create repository
2) Rename repository
3) Delete repository
4) List repositories
5) Clone repositories to workspace
6) Batch pull/push/sync
7) Exit
""")
        ch = Prompt.ask("Enter choice", default="7")
        if ch == "1": create_repo()
        elif ch == "2": rename_repo()
        elif ch == "3": delete_repo()
        elif ch == "4": list_repos()
        elif ch == "5": clone_repositories_to_workspace()
        elif ch == "6": batch_git_manager()
        elif ch == "7":
            console.print("[bold yellow]Goodbye![/bold yellow]")
            break
        else:
            console.print("[red]Invalid choice[/red]")


if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Interrupted by user.[/bold yellow]")
