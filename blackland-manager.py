#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Manager — All-In-One Script (All Update)
 - Auto deps
 - .env-based GitHub auth
 - Repo CRUD + transfer + visibility
 - Branch management
 - File/folder operations via API
 - Local uploads via temp clone + git push
 - Workspace clone / batch pull / push / sync
 - Auto-branch alignment (default branch detection)
 - Smart push recovery and enhanced logging
"""

from __future__ import annotations
import os
import sys
import subprocess
import shutil
import tempfile
import time
from typing import Optional, List
import git
import requests

from github import Github, Auth, GithubException, Repository
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.panel import Panel
from dotenv import load_dotenv

# ---------------------------
# Auto-install missing deps (best-effort)
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
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
        except Exception as e:
            print(f"[warn] Auto-install failed for {pkg}: {e}. Please install manually and re-run.")

# ---------------------------
# Config
# ---------------------------
ENV_PATH = "/home/gost/account/.env"
REPO_PATH = "/home/gost/7heBlackLand"
DEFAULT_COMMIT_MSG = "Welcome to Blackland"
LOG_FILE = os.path.join("/home/gost/all-project/git-all", "git_actions.log")

# ---------------------------
# Load .env and authenticate
# ---------------------------
load_dotenv(dotenv_path=ENV_PATH)
TOKEN = os.getenv("GITHUB_TOKEN")
console = Console()

if not TOKEN:
    console.print("[bold red]❌ GITHUB_TOKEN not found in .env — please add and re-run.[/bold red]")
    sys.exit(1)

try:
    # Auth via PyGithub (Auth.Token may vary with versions)
    try:
        auth = Auth.Token(TOKEN)
        gh = Github(auth=auth)
    except Exception:
        gh = Github(TOKEN)
    user = gh.get_user()
    console.print(f"✅ Authenticated as: [green]{user.login}[/green]\n")
except Exception as e:
    console.print(f"[bold red]❌ GitHub authentication failed: {e}[/bold red]")
    sys.exit(1)


# ---------------------------
# Logging helper
# ---------------------------
def log_action(msg: str) -> None:
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        # non-fatal
        pass


# ---------------------------
# Shell helpers (robust)
# ---------------------------
def run_cmd(cmd: List[str], cwd: Optional[str] = None, capture: bool = False) -> subprocess.CompletedProcess:
    """Run a shell command. Raises CalledProcessError on failure."""
    if cwd:
        display = f"(cwd={cwd}) {' '.join(cmd)}"
    else:
        display = " ".join(cmd)
    console.print(f"🚀 {display}")
    if capture:
        return subprocess.run(cmd, cwd=cwd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    else:
        return subprocess.run(cmd, cwd=cwd, check=True)


# ---------------------------
# Ensure git identity (global)
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
    subprocess.run(["git", "config", "--global", "user.name", "Auto Commit Bot"], check=False)
    subprocess.run(["git", "config", "--global", "user.email", "autocommit@example.com"], check=False)
    log_action("Set default git identity to Auto Commit Bot")


ensure_git_identity()


# ---------------------------
# GitHub API helpers
# ---------------------------
def list_repos(limit: int = 200) -> List[Repository.Repository]:
    try:
        repos = list(user.get_repos())
        return repos[:limit]
    except Exception as e:
        console.print(f"[red]Failed to load repos: {e}[/red]")
        return []


def get_github_default_branch(owner: str, repo_name: str) -> str:
    """Use GitHub API to fetch default branch name."""
    url = f"https://api.github.com/repos/{owner}/{repo_name}"
    headers = {"Authorization": f"token {TOKEN}", "Accept": "application/vnd.github.v3+json"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.ok:
            return r.json().get("default_branch", "main")
    except Exception:
        pass
    return "main"


# ---------------------------
# Remote / local helpers
# ---------------------------
def ensure_remote_tokenized(repo_path: str) -> None:
    """Append token to https origin if necessary (non-destructive)."""
    try:
        origin = subprocess.check_output(["git", "-C", repo_path, "remote", "get-url", "origin"], text=True).strip()
        if origin.startswith("https://") and "@" not in origin:
            new = origin.replace("https://", f"https://{TOKEN}@")
            subprocess.run(["git", "-C", repo_path, "remote", "set-url", "origin", new], check=True)
            log_action(f"Tokenized origin for {repo_path}")
    except Exception:
        pass


def ensure_branch_alignment_local(repo_path: str, repo_name: Optional[str] = None) -> None:
    """
    Align local branch to GitHub default branch (auto-detect).
    If repo_name provided, uses that to query GitHub; otherwise tries `origin/HEAD`.
    """
    try:
        # fetch remote refs first
        subprocess.run(["git", "-C", repo_path, "fetch", "--all"], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # determine remote default branch
        default_branch = "main"
        if repo_name:
            default_branch = get_github_default_branch(user.login, repo_name)
        else:
            # try to read origin/HEAD
            try:
                out = subprocess.check_output(["git", "-C", repo_path, "symbolic-ref", "refs/remotes/origin/HEAD"], text=True).strip()
                # out looks like 'refs/remotes/origin/main'
                if out and out.startswith("refs/remotes/origin/"):
                    default_branch = out.split("/")[-1]
            except Exception:
                pass

        # current local branch
        try:
            local_branch = subprocess.check_output(["git", "-C", repo_path, "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
        except Exception:
            local_branch = default_branch

        if local_branch != default_branch:
            console.print(f"🔁 Aligning branch: local '{local_branch}' → remote default '{default_branch}' in {repo_path}")
            # try checkout or create local tracking branch
            subprocess.run(["git", "-C", repo_path, "checkout", default_branch], check=False)
            subprocess.run(["git", "-C", repo_path, "branch", "--set-upstream-to", f"origin/{default_branch}", default_branch], check=False)
            log_action(f"Aligned {repo_path} branch {local_branch} -> {default_branch}")
    except Exception:
        pass


def safe_push(repo_path: str, commit_msg: str) -> bool:
    """
    Try to push; if it fails due to non-fast-forward, fetch and retry with --force-with-lease.
    Returns True if push succeeded.
    """
    try:
        run_cmd(["git", "-C", repo_path, "push"])
        log_action(f"Pushed {repo_path}")
        return True
    except subprocess.CalledProcessError as e:
        console.print(f"[yellow]Push failed (trying recovery): {e}[/yellow]")
        try:
            run_cmd(["git", "-C", repo_path, "fetch", "origin"], )
            # try to pull --rebase to integrate remote commits
            try:
                run_cmd(["git", "-C", repo_path, "pull", "--rebase"])
            except subprocess.CalledProcessError:
                # fallback: force-with-lease push
                run_cmd(["git", "-C", repo_path, "push", "--force-with-lease"])
            log_action(f"Recovered push for {repo_path}")
            return True
        except Exception as ex:
            console.print(f"[red]Push recovery failed: {ex}[/red]")
            log_action(f"Push recovery failed for {repo_path}: {ex}")
            return False


# ---------------------------
# Upload via temp clone (safe)
# ---------------------------
def upload_file_to_github(
    repo: Repository.Repository,
    file_path: str,
    branch_name: str,
    commit_message: str,
) -> bool:
    """Clone repo to temp, copy files, commit & push. Returns True on success."""
    temp_dir = tempfile.mkdtemp(prefix="gh_upload_")
    try:
        console.print(f"[blue]Cloning {repo.full_name} into temp dir...[/blue]")
        repo_url = f"https://{TOKEN}@github.com/{repo.owner.login}/{repo.name}.git"
        # If branch doesn't exist locally in remote clone, clone default branch then create new branch locally
        git.Repo.clone_from(repo_url, temp_dir, branch=branch_name, depth=1)
    except Exception:
        # fallback: clone default branch then checkout/create branch
        try:
            default = repo.default_branch or get_github_default_branch(repo.owner.login, repo.name)
            git.Repo.clone_from(f"https://{TOKEN}@github.com/{repo.owner.login}/{repo.name}.git", temp_dir, branch=default, depth=1)
            gr = git.Repo(temp_dir)
            # create new branch if requested branch != default
            if branch_name != default:
                gr.git.checkout("-b", branch_name)
        except Exception as e:
            console.print(f"[red]Clone failed: {e}[/red]")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False

    try:
        # copy file or folder
        if os.path.isdir(file_path):
            dest = os.path.join(temp_dir, os.path.basename(os.path.normpath(file_path)))
            shutil.copytree(file_path, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(file_path, os.path.join(temp_dir, os.path.basename(file_path)))

        # remove unwanted items
        for p in (".env", "__pycache__"):
            target = os.path.join(temp_dir, p)
            if os.path.exists(target):
                if os.path.isdir(target):
                    shutil.rmtree(target, ignore_errors=True)
                else:
                    try:
                        os.remove(target)
                    except Exception:
                        pass

        gr = git.Repo(temp_dir)
        gr.git.add(A=True)
        # If no changes, skip commit
        if gr.is_dirty(untracked_files=True):
            gr.index.commit(commit_message or DEFAULT_COMMIT_MSG)
            # safe push
            origin = gr.remote(name="origin")
            try:
                origin.push(refspec=f"{branch_name}:{branch_name}")
            except Exception:
                # recovery: fetch and push --force-with-lease
                try:
                    gr.git.fetch("origin")
                    origin.push(refspec=f"{branch_name}:{branch_name}", force=True)
                except Exception as e:
                    console.print(f"[red]Push failed after recovery: {e}[/red]")
                    log_action(f"Upload push failed for {repo.full_name}: {e}")
                    return False
        else:
            console.print("[yellow]No changes to commit.[/yellow]")
        console.print(f"[green]✅ Uploaded to {repo.full_name}@{branch_name}[/green]")
        log_action(f"Uploaded {file_path} -> {repo.full_name}@{branch_name}")
        return True
    except Exception as e:
        console.print(f"[red]Upload failed: {e}[/red]")
        log_action(f"Upload failed for {repo.full_name}: {e}")
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ---------------------------
# API functions (repo CRUD, branches, files)
# ---------------------------
def create_repo_interactive():
    name = Prompt.ask("Repository name")
    description = Prompt.ask("Description", default=f"Repository {name}")
    is_private = Confirm.ask("Make repository PRIVATE?", default=False)
    auto_init = Confirm.ask("Initialize with README?", default=False)
    try:
        repo = user.create_repo(name=name, description=description, private=is_private, auto_init=auto_init)
        console.print(f"[green]Created {repo.full_name}[/green]")
        log_action(f"Created repo {repo.full_name}")
        return repo
    except GithubException as e:
        console.print(f"[red]GitHub API error: {e}[/red]")
    except Exception as e:
        console.print(f"[red]Error creating repo: {e}[/red]")


def rename_repo_interactive(repo: Repository.Repository):
    new_name = Prompt.ask("New repository name", default=repo.name)
    try:
        old = repo.full_name
        repo.edit(name=new_name)
        console.print(f"[green]Renamed {old} -> {repo.full_name}[/green]")
        log_action(f"Renamed {old} -> {repo.full_name}")
    except Exception as e:
        console.print(f"[red]Rename failed: {e}[/red]")


def delete_repo_interactive(repo: Repository.Repository):
    if not Confirm.ask(f"Delete {repo.full_name}? This is irreversible.", default=False):
        console.print("[cyan]Cancelled[/cyan]")
        return
    try:
        repo.delete()
        console.print(f"[green]Deleted {repo.full_name}[/green]")
        log_action(f"Deleted {repo.full_name}")
    except Exception as e:
        console.print(f"[red]Delete failed: {e}[/red]")


def list_branches_api(repo: Repository.Repository) -> List[str]:
    try:
        branches = [b.name for b in repo.get_branches()]
        table = Table(title=f"Branches in {repo.full_name}")
        table.add_column("Branch")
        for b in branches:
            table.add_row(b)
        console.print(table)
        return branches
    except Exception as e:
        console.print(f"[red]Failed to list branches: {e}[/red]")
        return []


def create_branch_api(repo: Repository.Repository, base_branch: str):
    new_branch = Prompt.ask("New branch name")
    try:
        base = repo.get_branch(base_branch)
        repo.create_git_ref(ref=f"refs/heads/{new_branch}", sha=base.commit.sha)
        console.print(f"[green]Created branch {new_branch} from {base_branch}[/green]")
        log_action(f"Created branch {new_branch} in {repo.full_name}")
    except Exception as e:
        console.print(f"[red]Create branch failed: {e}[/red]")


def delete_branch_api(repo: Repository.Repository):
    name = Prompt.ask("Branch name to delete")
    if name == repo.default_branch:
        console.print("[yellow]Cannot delete default branch.[/yellow]")
        return
    try:
        ref = repo.get_git_ref(f"heads/{name}")
        ref.delete()
        console.print(f"[green]Deleted branch {name}[/green]")
        log_action(f"Deleted branch {name} in {repo.full_name}")
    except Exception as e:
        console.print(f"[red]Delete branch failed: {e}[/red]")


def switch_default_branch_api(repo: Repository.Repository):
    new = Prompt.ask(f"Set default branch (current {repo.default_branch})")
    try:
        repo.edit(default_branch=new)
        console.print(f"[green]Default branch set to {new}[/green]")
        log_action(f"Set default branch to {new} for {repo.full_name}")
    except Exception as e:
        console.print(f"[red]Failed to set default branch: {e}[/red]")


def create_or_edit_file_via_api(repo: Repository.Repository):
    path = Prompt.ask("File path (e.g., README.md)")
    content = Prompt.ask("Content (leave blank for empty)", default="")
    branch = Prompt.ask("Branch", default=repo.default_branch)
    try:
        try:
            existing = repo.get_contents(path, ref=branch)
            repo.update_file(existing.path, f"Update {path}", content, existing.sha, branch=branch)
            console.print(f"[green]Updated {path} on {branch}[/green]")
            log_action(f"Updated file {path} on {repo.full_name}@{branch}")
        except GithubException:
            repo.create_file(path, f"Create {path}", content, branch=branch)
            console.print(f"[green]Created {path} on {branch}[/green]")
            log_action(f"Created file {path} on {repo.full_name}@{branch}")
    except Exception as e:
        console.print(f"[red]File API operation failed: {e}[/red]")


def create_folder_placeholder_api(repo: Repository.Repository):
    folder = Prompt.ask("Folder path (e.g., src/utils)")
    branch = Prompt.ask("Branch", default=repo.default_branch)
    placeholder = f"{folder.rstrip('/')}/.gitkeep"
    try:
        repo.create_file(placeholder, f"Create folder {folder}", "", branch=branch)
        console.print(f"[green]Created folder placeholder {folder} on {branch}[/green]")
        log_action(f"Created folder placeholder {placeholder} on {repo.full_name}@{branch}")
    except Exception as e:
        console.print(f"[red]Failed to create folder: {e}[/red]")


def delete_file_api(repo: Repository.Repository):
    file_path = Prompt.ask("File path to delete")
    branch = Prompt.ask("Branch", default=repo.default_branch)
    try:
        cont = repo.get_contents(file_path, ref=branch)
        repo.delete_file(cont.path, f"Delete {file_path}", cont.sha, branch=branch)
        console.print(f"[green]Deleted {file_path} on {branch}[/green]")
        log_action(f"Deleted file {file_path} on {repo.full_name}@{branch}")
    except Exception as e:
        console.print(f"[red]Delete file failed: {e}[/red]")


def list_files_api(repo: Repository.Repository):
    path = Prompt.ask("Folder path (blank for root)", default="")
    branch = Prompt.ask("Branch", default=repo.default_branch)
    try:
        contents = repo.get_contents(path or "", ref=branch)
        table = Table(title=f"Files: {repo.full_name}/{path or '.'} [{branch}]")
        table.add_column("Type")
        table.add_column("Path")
        table.add_column("Size", justify="right")
        for c in contents:
            ctype = "Folder" if c.type == "dir" else "File"
            table.add_row(ctype, c.path, str(c.size or "-"))
        console.print(table)
    except Exception as e:
        console.print(f"[red]List files failed: {e}[/red]")


def view_file_api(repo: Repository.Repository):
    file_path = Prompt.ask("File path to view")
    branch = Prompt.ask("Branch", default=repo.default_branch)
    try:
        contents = repo.get_contents(file_path, ref=branch)
        console.rule(f"{file_path} [{branch}]")
        console.print(contents.decoded_content.decode(errors="replace"))
        console.rule()
    except Exception as e:
        console.print(f"[red]View file failed: {e}[/red]")


# ---------------------------
# Workspace batch manager (local)
# ---------------------------
def clone_repo_to_workspace(repo: Repository.Repository):
    os.makedirs(REPO_PATH, exist_ok=True)
    local_path = os.path.join(REPO_PATH, repo.name)
    if os.path.exists(local_path):
        console.print(f"[yellow]Already exists: {repo.name} → skipping[/yellow]")
        return
    clone_url = repo.clone_url
    if clone_url.startswith("https://") and "@" not in clone_url:
        clone_url = clone_url.replace("https://", f"https://{TOKEN}@")
    try:
        run_cmd(["git", "clone", clone_url, local_path], )
        ensure_remote_tokenized(local_path)
        ensure_branch_alignment_local(local_path, repo.name)
        console.print(f"[green]Cloned {repo.full_name} -> {local_path}[/green]")
        log_action(f"Cloned {repo.full_name} to {local_path}")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Clone failed for {repo.full_name}: {e}[/red]")
        log_action(f"Clone failed for {repo.full_name}: {e}")


def batch_workspace_manager():
    """
    Walk REPO_PATH and run pull/push/sync on each git repo found.
    """
    if not os.path.isdir(REPO_PATH):
        console.print(f"[red]Workspace not found: {REPO_PATH}[/red]")
        return

    dirs = sorted([d for d in os.listdir(REPO_PATH) if os.path.isdir(os.path.join(REPO_PATH, d))])
    repo_dirs = [d for d in dirs if os.path.isdir(os.path.join(REPO_PATH, d, ".git"))]
    if not repo_dirs:
        console.print("[red]No local git repositories found in workspace.[/red]")
        return

    console.print(Panel("[bold cyan]Batch Workspace Manager[/bold cyan]"))
    console.print("1) Pull all\n2) Push all\n3) Sync all (pull then push)\n4) Clone missing (from remote)\n5) Back")
    choice = Prompt.ask("Enter choice", default="5").strip()
    if choice == "5":
        return

    commit_msg = DEFAULT_COMMIT_MSG
    if choice in ("2", "3"):
        commit_msg = Prompt.ask("Commit message", default=commit_msg)

    if choice == "4":
        # clone any missing repos from remote to workspace
        repos = list_repos(limit=1000)
        for r in repos:
            local = os.path.join(REPO_PATH, r.name)
            if not os.path.exists(local):
                clone_repo_to_workspace(r)
        return

    for d in repo_dirs:
        path = os.path.join(REPO_PATH, d)
        console.print(f"\n📂 [bold cyan]{d}[/bold cyan]")
        ensure_remote_tokenized(path)
        ensure_branch_alignment_local(path, d)
        try:
            if choice in ("1", "3"):
                console.print("🔄 Pulling...")
                run_cmd(["git", "-C", path, "pull"], )
                console.print("[green]Pulled.[/green]")
                log_action(f"Pulled {d}")
            if choice in ("2", "3"):
                console.print("⬆️ Adding & committing...")
                run_cmd(["git", "-C", path, "add", "."], )
                commit = subprocess.run(["git", "-C", path, "commit", "-m", commit_msg])
                if commit.returncode == 0:
                    pushed = safe_push(path, commit_msg)
                    if pushed:
                        console.print("[green]Pushed.[/green]")
                else:
                    console.print("[yellow]Nothing to commit.[/yellow]")
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Git operation failed for {d}: {e}[/red]")
            log_action(f"Git error {d}: {e}")

    console.print("\n✨ Batch operations completed.\n")


# ---------------------------
# Selection menus
# ---------------------------
def select_repo_interactive() -> Optional[Repository.Repository]:
    repos = list_repos(limit=200)
    if not repos:
        console.print("[yellow]No repositories found.[/yellow]")
        if Confirm.ask("Create one now?"):
            return create_repo_interactive()
        return None

    table = Table(title=f"Your repositories (top {len(repos)})")
    table.add_column("No", justify="center", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Private", justify="center")
    for i, r in enumerate(repos, 1):
        table.add_row(str(i), r.name, "🔒" if r.private else "🌍")
    console.print(table)
    console.print("[blue]0[/blue] → Create new repository")

    choice = Prompt.ask("Enter number", default="1")
    try:
        idx = int(choice)
    except ValueError:
        console.print("[red]Invalid input[/red]")
        return None

    if idx == 0:
        return create_repo_interactive()
    if 1 <= idx <= len(repos):
        return repos[idx - 1]
    console.print("[red]Choice out of range[/red]")
    return None


def repo_manage_menu():
    repo = select_repo_interactive()
    if not repo:
        return
    while True:
        console.rule(f"[bold]Repository:[/bold] {repo.full_name} (default: {repo.default_branch})")
        console.print("""
a) Create folder
b) Create / Edit file
c) Delete file
d) List files
e) View file
f) Branch operations
g) Repo settings (rename / visibility / delete / transfer)
h) Upload local folder/file (temp clone & git push)
i) Back
""")
        sub = Prompt.ask("Choose").strip().lower()
        if sub == "a":
            create_folder_placeholder_api(repo)
        elif sub == "b":
            create_or_edit_file_via_api(repo)
        elif sub == "c":
            delete_file_api(repo)
        elif sub == "d":
            list_files_api(repo)
        elif sub == "e":
            view_file_api(repo)
        elif sub == "f":
            branches = list_branches_api(repo)
            console.print("Options: [1] Create  [2] Delete  [3] Switch default")
            action = Prompt.ask("Choose", default="1")
            if action == "1":
                create_branch_api(repo, repo.default_branch)
            elif action == "2":
                delete_branch_api(repo)
            elif action == "3":
                switch_default_branch_api(repo)
        elif sub == "g":
            console.print("Options: [1] Rename  [2] Visibility  [3] Delete  [4] Transfer")
            choice = Prompt.ask("Choose", default="1")
            if choice == "1":
                rename_repo_interactive(repo)
            elif choice == "2":
                make_private = Confirm.ask("Make PRIVATE? (No => public)", default=repo.private)
                try:
                    repo.edit(private=make_private)
                    console.print(f"[green]Visibility updated[/green]")
                    log_action(f"Visibility changed for {repo.full_name} -> {'private' if make_private else 'public'}")
                except Exception as e:
                    console.print(f"[red]Visibility change failed: {e}[/red]")
            elif choice == "3":
                delete_repo_interactive(repo)
                return
            elif choice == "4":
                transfer_repository(repo, console, Prompt, Confirm)
        elif sub == "h":
            branch = Prompt.ask("Branch", default=repo.default_branch)
            path = Prompt.ask("Local path (absolute or relative)", default=".")
            msg = Prompt.ask("Commit message", default=f"Upload via GitHub Manager @ {time.strftime('%Y-%m-%d %H:%M:%S')}")
            upload_file_to_github(repo, path, branch, msg)
        elif sub == "i":
            break
        else:
            console.print("[red]Invalid option[/red]")


# ---------------------------
# Main menu
# ---------------------------
def main_menu():
    console.print("[bold magenta]GitHub Manager — Unified Edition (All Update)[/bold magenta]")
    while True:
        console.rule("[bold blue]Main Menu[/bold blue]")
        console.print(f"Workspace: [green]{REPO_PATH}[/green]\n")
        console.print("""
1) Create new repository
2) Manage repository (files / branches / settings)
3) Clone repositories to workspace
4) Batch workspace manager (pull / push / sync / clone missing)
5) Upload local folder/file to a repository (temp clone & push)
6) List repositories (remote)
7) Exit
""")
        choice = Prompt.ask("Enter choice", default="7").strip()
        if choice == "1":
            create_repo_interactive()
        elif choice == "2":
            repo_manage_menu()
        elif choice == "3":
            repos = list_repos(limit=500)
            console.print("[cyan]Select: [1] Clone all  [2] Choose specific  [3] Cancel[/cyan]")
            sub = Prompt.ask("Choice", default="3")
            if sub == "1":
                for r in repos:
                    clone_repo_to_workspace(r)
            elif sub == "2":
                table = Table(title="Select repositories")
                table.add_column("No", justify="center")
                table.add_column("Name", style="cyan")
                for i, r in enumerate(repos, 1):
                    table.add_row(str(i), r.name)
                console.print(table)
                raw = Prompt.ask("Enter numbers comma-separated")
                try:
                    indices = [int(x.strip()) for x in raw.split(",") if x.strip()]
                    for i in indices:
                        if 1 <= i <= len(repos):
                            clone_repo_to_workspace(repos[i - 1])
                except Exception:
                    console.print("[red]Invalid selection[/red]")
        elif choice == "4":
            batch_workspace_manager()
        elif choice == "5":
            repo = select_repo_interactive()
            if repo:
                branch = Prompt.ask("Branch", default=repo.default_branch)
                path = Prompt.ask("Local path", default=".")
                msg = Prompt.ask("Commit message", default=f"Upload via GitHub Manager @ {time.strftime('%Y-%m-%d %H:%M:%S')}")
                upload_file_to_github(repo, path, branch, msg)
        elif choice == "6":
            repos = list_repos(limit=500)
            table = Table(title=f"Your Repositories (top {len(repos)})")
            table.add_column("No", justify="center")
            table.add_column("Name", style="cyan")
            table.add_column("Private", justify="center")
            for i, r in enumerate(repos, 1):
                table.add_row(str(i), r.name, "🔒" if r.private else "🌍")
            console.print(table)
        elif choice == "7":
            console.print("[bold yellow]Goodbye![/bold yellow]")
            log_action("Exited GitHub Manager")
            break
        else:
            console.print("[red]Invalid choice[/red]")


# ---------------------------
# Entry
# ---------------------------
if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Interrupted. Exiting...[/bold yellow]")
        log_action("Interrupted by user - exit")
        sys.exit(0)
