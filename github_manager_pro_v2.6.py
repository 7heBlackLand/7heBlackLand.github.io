#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Manager Pro v2.6 — Stable Fixed Version
Features:
 - Full integration: .env token load, logging, local repo init/pull, list & clone, local info, quick push.
 - Power Upload PRO+: multi-file/folder upload, branch auto-create, empty repo init, retry push.
 - Fixed working directory / context bugs (ensures git commands run inside cloned repo).
"""

from __future__ import annotations
import os
import sys
import subprocess
import shutil
import tempfile
import time
from datetime import datetime
from typing import List

# Auto-install missing dependencies (best-effort)
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
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
        except Exception as e:
            print(f"[warn] Auto-install failed for {pkg}: {e}. Please install manually.")

import git
import requests
from github import Github, Auth, GithubException, Repository
from dotenv import load_dotenv
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn

# ---------------------------
# Configuration (adjust paths as needed)
# ---------------------------
ENV_PATH = "/home/gost/account/.env"
BASE_PATH = "/home/gost/all-project/git-all"
LOG_FILE = os.path.join(BASE_PATH, "git_actions.log")

console = Console()

# ---------------------------
# Helper Functions
# ---------------------------
def log_action(text: str) -> None:
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {text}\n")
    except Exception:
        pass  # Logging failure shouldn’t stop script

def run_shell(cmd: List[str], cwd: str | None = None, silent: bool = False) -> subprocess.CompletedProcess:
    if not silent:
        console.print(f"[cyan]🚀 Running:[/cyan] {' '.join(cmd)} (cwd={cwd or os.getcwd()})")
    return subprocess.run(cmd, check=True, cwd=cwd, text=True)

# ---------------------------
# Load .env & authenticate GitHub
# ---------------------------
load_dotenv(dotenv_path=ENV_PATH)
TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USER = os.getenv("GITHUB_USER") or None

if not TOKEN:
    console.print("[bold red]❌ GITHUB_TOKEN not found in .env — set it and re‐run.[/bold red]")
    sys.exit(1)

try:
    gh = Github(auth=Auth.Token(TOKEN))
    gh_user = gh.get_user()
    if not GITHUB_USER:
        GITHUB_USER = gh_user.login
    console.print(f"[green]✅ Authenticated to GitHub as {gh_user.login}[/green]")
    log_action(f"Authenticated to GitHub as {gh_user.login}")
except Exception as e:
    console.print(f"[red]❌ GitHub authentication failed: {e}[/red]")
    sys.exit(1)

os.makedirs(BASE_PATH, exist_ok=True)

# ---------------------------
# Local repo initializer / ensure function
# ---------------------------
def ensure_local_repo(repo_path: str) -> None:
    """Ensure local repo exists; clone if missing; pull if present."""
    if not os.path.isdir(repo_path):
        console.print(f"[yellow]Local repository not found at: {repo_path}[/yellow]")
        if Confirm.ask("Clone a repository into this path now?", default=True):
            repo_url = Prompt.ask("Enter GitHub HTTPS URL (e.g., https://github.com/user/repo.git)")
            if not repo_url:
                console.print("[red]No URL provided – aborting clone.[/red]")
                return
            clone_url = repo_url
            if repo_url.startswith("https://") and "@" not in repo_url:
                clone_url = repo_url.replace("https://", f"https://x-access-token:{TOKEN}@")
            os.makedirs(os.path.dirname(repo_path), exist_ok=True)
            try:
                run_shell(["git", "clone", clone_url, repo_path])
                console.print(f"[green]✅ Cloned repo to {repo_path}[/green]")
                log_action(f"Cloned {repo_url} -> {repo_path}")
            except subprocess.CalledProcessError as e:
                console.print(f"[red]❌ Clone failed: {e}[/red]")
                log_action(f"Clone failed: {e}")
                return
        else:
            console.print("[cyan]Skipping clone – continuing.[/cyan]")
            return

    try:
        run_shell(["git", "config", "user.name", "Auto Commit Bot"], cwd=repo_path, silent=True)
        run_shell(["git", "config", "user.email", "autocommit@example.com"], cwd=repo_path, silent=True)
    except subprocess.CalledProcessError:
        console.print("[yellow]⚠️ Could not set git identity (continuing)...[/yellow]")

    try:
        origin_url = subprocess.check_output(["git", "remote", "get-url", "origin"], cwd=repo_path, text=True).strip()
        if origin_url.startswith("https://") and "@" not in origin_url:
            token_url = origin_url.replace("https://", f"https://x-access-token:{TOKEN}@")
            try:
                run_shell(["git", "remote", "set-url", "origin", token_url], cwd=repo_path, silent=True)
                log_action("Updated origin URL with token.")
            except subprocess.CalledProcessError:
                console.print("[yellow]⚠️ Could not update origin URL with token (continuing)...[/yellow]")
    except subprocess.CalledProcessError:
        console.print("[yellow]⚠️ No origin remote found or unable to read (continuing)...[/yellow]")

    try:
        console.print("\n🔄 Pulling latest changes from origin...")
        run_shell(["git", "pull"], cwd=repo_path, silent=True)
        console.print("[green]✅ Local repository updated.[/green]")
        log_action(f"Pulled changes at {repo_path}")
    except subprocess.CalledProcessError as e:
        console.print(f"[yellow]⚠️ Pull failed: {e} (continuing)...[/yellow]")
        log_action(f"Pull failed at {repo_path}: {e}")

# ---------------------------
# List & clone GitHub repos function
# ---------------------------
def list_and_clone_repos():
    console.rule("[bold blue]📦 GitHub Repository Browser[/bold blue]")
    url = "https://api.github.com/user/repos?per_page=200"
    headers = {"Authorization": f"token {TOKEN}", "Accept": "application/vnd.github+json"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        console.print(f"[red]❌ Failed to fetch repos: {e}[/red]")
        return
    repos = resp.json()
    if not repos:
        console.print("[yellow]⚠️ No repositories found.[/yellow]")
        return

    table = Table(title=f"{GITHUB_USER or gh_user.login}'s Repositories")
    table.add_column("No", justify="center")
    table.add_column("Name", style="cyan")
    table.add_column("Visibility", justify="center")
    for i, r in enumerate(repos, 1):
        vis = "Public 🌍" if not r.get("private", False) else "Private 🔒"
        table.add_row(str(i), r["name"], vis)
    console.print(table)

    choice = Prompt.ask("Select repo number to clone (0=Cancel)", default="0")
    if choice == "0":
        return
    try:
        idx = int(choice) - 1
        sel = repos[idx]
    except Exception:
        console.print("[red]Invalid selection[/red]")
        return

    repo_name = sel["name"]
    clone_url = sel.get("clone_url") or sel.get("ssh_url")
    if clone_url.startswith("https://") and "@" not in clone_url:
        clone_url = clone_url.replace("https://", f"https://x-access-token:{TOKEN}@")

    target_default = os.path.join(BASE_PATH, repo_name)
    target = Prompt.ask("Enter local target path", default=target_default)
    os.makedirs(os.path.dirname(target), exist_ok=True)

    console.print(f"[cyan]Cloning {repo_name} → {target}...[/cyan]")
    try:
        run_shell(["git", "clone", clone_url, target])
        console.print(f"[green]✅ Clone successful: {target}[/green]")
        log_action(f"Cloned {repo_name} -> {target}")
    except Exception as e:
        console.print(f"[red]❌ Clone failed: {e}[/red]")
        log_action(f"Clone failed for {repo_name}: {e}")

# ---------------------------
# Show Local Repo Info
# ---------------------------
def show_local_repo_info():
    repo_path = Prompt.ask("Enter local repository path", default=os.path.join(BASE_PATH, ""))
    if not os.path.isdir(repo_path):
        console.print(f"[red]❌ Path not found: {repo_path}[/red]")
        return
    try:
        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path, text=True).strip()
    except subprocess.CalledProcessError:
        branch = "<unknown>"
    try:
        remote = subprocess.check_output(["git", "remote", "get-url", "origin"], cwd=repo_path, text=True).strip()
    except subprocess.CalledProcessError:
        remote = "<no origin>"
    total = sum(len(files) for _, _, files in os.walk(repo_path))

    console.rule("[bold cyan]📂 Local Repository Information[/bold cyan]")
    console.print(f"[yellow]Repository Path:[/yellow] {repo_path}")
    console.print(f"[green]Current Branch:[/green] {branch}")
    console.print(f"[blue]Remote Origin:[/blue] {remote}")
    console.print(f"[magenta]Total Files (approx):[/magenta] {total}")
    console.print("\n[bold]📊 Git Status (short):[/bold]")
    try:
        run_shell(["git", "status", "-s"], cwd=repo_path)
    except Exception:
        pass

# ---------------------------
# Local quick push
# ---------------------------
def local_repo_push(repo_dir: str, commit_message: str = "Auto commit"):
    if not os.path.isdir(repo_dir):
        console.print(f"[red]❌ Repo path not found: {repo_dir}[/red]")
        return
    try:
        run_shell(["git", "add", "."], cwd=repo_dir, silent=True)
        try:
            run_shell(["git", "commit", "-m", commit_message], cwd=repo_dir, silent=True)
        except subprocess.CalledProcessError:
            console.print("[yellow]No changes to commit.[/yellow]")
        run_shell(["git", "push"], cwd=repo_dir, silent=True)
        console.print("[green]✅ Local push completed.[/green]")
        log_action(f"Local push from {repo_dir} (msg='{commit_message}')")
    except Exception as e:
        console.print(f"[red]Local push failed: {e}[/red]")
        log_action(f"Local push failure for {repo_dir}: {e}")

# ---------------------------
# Power Upload PRO+
# ---------------------------
def _collect_files(paths: List[str]) -> List[str]:
    files = []
    for p in paths:
        p = os.path.abspath(p)
        if not os.path.exists(p):
            continue
        if os.path.isdir(p):
            for root, _, fnames in os.walk(p):
                for fn in fnames:
                    files.append(os.path.join(root, fn))
        else:
            files.append(p)
    return files

def power_upload(repo: Repository, token: str):
    console.rule(f"[bold blue]Power Upload → {repo.full_name}[/bold blue]")
    file_input = Prompt.ask("Enter local files/folders (comma-separated)", default=".")
    paths = [s.strip() for s in file_input.split(",") if s.strip()]
    if not paths:
        console.print("[red]No paths provided.[/red]")
        return
    commit_msg = Prompt.ask("Commit message", default="Power Upload")
    branch_name = Prompt.ask("Target branch", default=repo.default_branch or "main")

    temp_dir = tempfile.mkdtemp(prefix="ghpush_")
    try:
        clone_url = f"https://x-access-token:{token}@github.com/{repo.owner.login}/{repo.name}.git"
        console.print(f"[cyan]Cloning repo (branch={branch_name}) into temp dir...[/cyan]")
        try:
            git_repo = git.Repo.clone_from(clone_url, temp_dir, branch=branch_name)
        except git.exc.GitCommandError as e:
            console.print(f"[yellow]Clone warning: {e}[/yellow]")
            git_repo = git.Repo.clone_from(clone_url, temp_dir)
            if not git_repo.heads:
                console.print("[yellow]Empty remote — creating initial commit...[/yellow]")
                dummy = os.path.join(temp_dir, ".init")
                with open(dummy, "w") as fh:
                    fh.write("initial")
                os.chdir(temp_dir)
                git_repo.index.add([dummy])
                git_repo.index.commit("Initial commit (auto)")
                git_repo.git.branch("-M", branch_name)
                git_repo.remote("origin").push(refspec=f"{branch_name}:{branch_name}")
                console.print("[green]Initial commit pushed.[/green]")
            else:
                try:
                    new_head = git_repo.create_head(branch_name)
                    new_head.checkout()
                    console.print(f"[yellow]Created and switched to branch '{branch_name}'.[/yellow]")
                except Exception as ex:
                    console.print(f"[red]Branch creation failed: {ex}[/red]")
                    raise

        # Collect files
        all_files = _collect_files(paths)
        if not all_files:
            console.print("[red]No valid files found to upload.[/red]")
            return
        console.print(f"[cyan]Copying {len(all_files)} files...[/cyan]")
        base_src = os.path.commonpath([os.path.abspath(p) for p in paths]) if len(paths) > 1 else os.path.abspath(paths[0])
        with Progress(SpinnerColumn(), BarColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as prog:
            task = prog.add_task("Copying files...", total=len(all_files))
            for src in all_files:
                try:
                    rel = os.path.relpath(src, start=base_src)
                except Exception:
                    rel = os.path.basename(src)
                dest = os.path.join(temp_dir, rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(src, dest)
                prog.advance(task)

        # Cleanup
        for ig in ['.env', '__pycache__', '.git', '.gitignore']:
            p = os.path.join(temp_dir, ig)
            if os.path.exists(p):
                try:
                    if os.path.isdir(p):
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        os.remove(p)
                except Exception:
                    pass

        # Commit & push with correct working dir
        os.chdir(temp_dir)
        try:
            git_repo.git.add(all=True)
            try:
                git_repo.index.commit(commit_msg)
            except Exception:
                console.print("[yellow]No changes to commit.[/yellow]")

            max_r = 3
            for attempt in range(1, max_r + 1):
                try:
                    console.print(f"[blue]Pushing (attempt {attempt}/{max_r})...[/blue]")
                    git_repo.remote("origin").push(refspec=f"{branch_name}:{branch_name}")
                    console.print(f"[green]✅ Upload succeeded: {repo.full_name}:{branch_name}[/green]")
                    log_action(f"Power upload succeeded: {repo.full_name}:{branch_name} (files={len(all_files)})")
                    break
                except Exception as p_err:
                    console.print(f"[red]Push failed (attempt {attempt}): {p_err}[/red]")
                    log_action(f"Push attempt {attempt} failed for {repo.full_name}:{branch_name} - {p_err}")
                    if attempt < max_r:
                        time.sleep(2)
                    else:
                        raise

        except Exception as e:
            console.print(f"[red]Commit/push stage failed: {e}[/red]")
            log_action(f"Commit/push stage failed for {repo.full_name}:{branch_name} - {e}")
            raise

    except Exception as exc:
        console.print(f"[red]Upload aborted: {exc}[/red]")
        log_action(f"Power upload aborted: {repo.full_name} - {exc}")

    finally:
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass

# ---------------------------
# Repos listing + selection helpers
# ---------------------------
def list_repos(limit: int = 200):
    try:
        repos = list(gh.get_user().get_repos())[:limit]
        table = Table(title="Your GitHub Repositories")
        table.add_column("No", justify="center")
        table.add_column("Name", style="cyan")
        table.add_column("Visibility", justify="center")
        for i, r in enumerate(repos, 1):
            vis = "Public 🌍" if not r.private else "Private 🔒"
            table.add_row(str(i), r.full_name, vis)
        console.print(table)
        return repos
    except Exception as e:
        console.print(f"[red]Failed to list repos: {e}[/red]")
        return []

def select_repo_interactive():
    repos = list_repos()
    if not repos:
        return None
    choice = Prompt.ask("Select repo number (0=cancel)", default="0")
    try:
        idx = int(choice)
        if idx == 0:
            return None
        return repos[idx - 1]
    except Exception:
        console.print("[red]Invalid selection[/red]")
        return None

# ---------------------------
# Main Menu
# ---------------------------
def main_menu():
    while True:
        console.rule("[bold magenta]GitHub Manager Pro v2.6[/bold magenta]")
        console.print("""
1) Ensure local repo (clone/pull)
2) List GitHub repositories
3) List & Clone repositories
4) Show local repo info
5) Local quick push
6) Power Upload PRO+
7) Exit
""")
        choice = Prompt.ask("Enter choice").strip()
        if choice == "1":
            path = Prompt.ask("Enter local repo path", default=os.path.join(BASE_PATH, ""))
            ensure_local_repo(path)
        elif choice == "2":
            list_repos()
        elif choice == "3":
            list_and_clone_repos()
        elif choice == "4":
            show_local_repo_info()
        elif choice == "5":
            path = Prompt.ask("Local repo path", default=os.path.join(BASE_PATH, ""))
            if Confirm.ask("Perform quick add/commit/push in this path?", default=False):
                local_repo_push(path, commit_message=Prompt.ask("Commit message", default="Auto commit"))
        elif choice == "6":
            repo = select_repo_interactive()
            if repo:
                power_upload(repo, TOKEN)
        elif choice == "7":
            console.print("[magenta]👋 Goodbye![/magenta]")
            log_action("Exited GitHub Manager Pro v2.6")
            sys.exit(0)
        else:
            console.print("[red]Invalid option[/red]")

if __name__ == "__main__":
    console.rule("[bold green]🚀 Starting GitHub Manager Pro v2.6[/bold green]")
    log_action("Launched GitHub Manager Pro v2.6")
    try:
        main_menu()
    except KeyboardInterrupt:
        console.print("\n[cyan]Interrupted by user. Exiting...[/cyan]")
        log_action("Interrupted by user")
        sys.exit(0)
