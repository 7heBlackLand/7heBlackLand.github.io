#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified GitHub Manager + Local Sync
 - Loads .env for GITHUB_TOKEN
 - GitHub API operations (create/rename/delete/transfer repos, branches, files)
 - Local Git sync manager (clone, pull, push, sync) with logging
 - Rich interactive CLI
"""

from __future__ import annotations
import os
import sys
import subprocess
import shutil
import tempfile
from typing import Optional, List
from datetime import datetime

# Auto-install missing deps (best-effort)
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

# Safe imports after (attempted) install
try:
    import git
    from dotenv import load_dotenv
    from github import Github, Auth, GithubException, Repository
    from rich.console import Console
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    from rich.panel import Panel
except Exception as e:
    print(f"[bold red]Missing required libraries after install attempt: {e}[/bold red]")
    print("Please install required packages and re-run: pip install PyGithub GitPython python-dotenv rich requests")
    sys.exit(1)

# === CONFIG ===
ENV_PATH = "/home/gost/account/.env"
REPO_PATH = "/home/gost/all-project/git-all/7heBlackLand.github.io"
DEFAULT_COMMIT_MSG = "Welcome to Blackland"
LOG_FILE = os.path.join("/home/gost/all-project/git-all", "git_actions.log")

# === Load .env and authenticate GitHub ===
load_dotenv(dotenv_path=ENV_PATH)
TOKEN = os.getenv("GITHUB_TOKEN")

console = Console()

if not TOKEN:
    console.print("[bold red]❌ GITHUB_TOKEN not found in /home/gost/account/.env — please add and re-run.[/bold red]")
    sys.exit(1)

try:
    auth = Auth.Token(TOKEN)
    gh = Github(auth=auth)
    user = gh.get_user()
    console.print(f"✅ Authenticated as: [green]{user.login}[/green]\n")
except Exception as e:
    console.print(f"[bold red]❌ GitHub authentication failed: {e}[/bold red]")
    sys.exit(1)


# ---------------------------
# Logging helper
# ---------------------------
def log_action(action_text: str) -> None:
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a") as log:
            log.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {action_text}\n")
    except Exception:
        # non-fatal if logging fails
        pass


# ===============================================================
#  API MANAGER FUNCTIONS (PyGithub)
# ===============================================================
def list_repos(user_obj, limit: int = 50) -> List[Repository.Repository]:
    """Lists repositories of the authenticated user (first `limit`)."""
    try:
        return list(user_obj.get_repos())[:limit]
    except Exception as e:
        console.print(f"[red]Failed to load repositories: {e}[/red]")
        return []


def create_repo(user_obj, console_obj, prompt, confirm):
    """Creates a new GitHub repository interactively."""
    name = prompt.ask("Repository name")
    description = prompt.ask("Description", default=f"Repository {name}")
    is_private = confirm.ask("Make repository PRIVATE?", default=False)
    auto_init = confirm.ask("Initialize repo with README on GitHub (auto-init)?", default=False)
    try:
        repo = user_obj.create_repo(name=name, description=description, private=is_private, auto_init=auto_init)
        console_obj.print(f"✅ Created repository: [green]{repo.full_name}[/green]")
        log_action(f"Created repository {repo.full_name}")
        return repo
    except GithubException as e:
        console_obj.print(f"[red]GitHub API error: {e.data}[/red]")
        return None
    except Exception as e:
        console_obj.print(f"[red]Error creating repository: {e}[/red]")
        return None


def rename_repo(repo, console_obj, prompt):
    new_name = prompt.ask("New repository name", default=repo.name)
    try:
        repo.edit(name=new_name)
        console_obj.print(f"✏️ Renamed to [yellow]{new_name}[/yellow]")
        log_action(f"Renamed repo {repo.full_name} to {new_name}")
    except Exception as e:
        console_obj.print(f"[red]Rename failed: {e}[/red]")


def delete_repo_confirm(repo, console_obj, confirm):
    confirm_delete = confirm.ask(f"Are you sure you want to DELETE repository '{repo.full_name}'? This is irreversible!", default=False)
    if not confirm_delete:
        console_obj.print("[cyan]Delete cancelled.[/cyan]")
        return False
    try:
        repo.delete()
        console_obj.print(f"🗑️ Deleted repository: [red]{repo.full_name}[/red]")
        log_action(f"Deleted repo {repo.full_name}")
        return True
    except Exception as e:
        console_obj.print(f"[red]Delete failed: {e}[/red]")
        return False


def edit_repo_description(repo, console_obj, prompt):
    new_desc = prompt.ask("New description", default=repo.description or "")
    try:
        repo.edit(description=new_desc)
        console_obj.print("✅ Description updated.")
        log_action(f"Updated description of {repo.full_name}")
    except Exception as e:
        console_obj.print(f"[red]Update failed: {e}[/red]")


def change_repo_visibility(repo, console_obj, confirm):
    current = "Private" if repo.private else "Public"
    console_obj.print(f"Current visibility: {current}")
    make_private = confirm.ask("Make repository PRIVATE? (Choose No to make it PUBLIC)")
    try:
        repo.edit(private=make_private)
        console_obj.print(f"✅ Visibility changed to: {'Private' if make_private else 'Public'}")
        log_action(f"Changed visibility of {repo.full_name} to {'Private' if make_private else 'Public'}")
    except Exception as e:
        console_obj.print(f"[red]Visibility change failed: {e}[/red]")


def transfer_repository(repo, console_obj, prompt, confirm):
    console_obj.print("[yellow]Repository transfer is a sensitive operation and requires admin rights on target.[/yellow]")
    new_owner = prompt.ask("Enter new owner username or organization name")
    confirm_transfer = confirm.ask(f"Are you sure you want to transfer '{repo.full_name}' to '{new_owner}'?", default=False)
    if not confirm_transfer:
        console_obj.print("[cyan]Transfer cancelled.[/cyan]")
        return
    try:
        owner = repo.owner.login
        repo_name = repo.name
        transfer_body = {"new_owner": new_owner}
        repo._requester.requestJsonAndCheck("POST", f"/repos/{owner}/{repo_name}/transfer", input=transfer_body)
        console_obj.print(f"✅ Transfer requested to {new_owner}.")
        log_action(f"Transfer requested for {repo.full_name} to {new_owner}")
    except Exception as e:
        console_obj.print(f"[red]Transfer failed: {e}[/red]")


# ---------------------------
# Branch operations
# ---------------------------
def list_branches(repo, console_obj) -> List:
    try:
        branches = repo.get_branches()
        table = Table(title=f"Branches in {repo.full_name}")
        table.add_column("Branch Name", style="green")
        branch_list = []
        for b in branches:
            table.add_row(b.name)
            branch_list.append(b.name)
        console_obj.print(table)
        return branch_list
    except Exception as e:
        console_obj.print(f"[red]Failed to list branches: {e}[/red]")
        return []


def create_branch(repo, console_obj, prompt, base_branch: str):
    new_branch = prompt.ask("New branch name")
    try:
        base = repo.get_branch(base_branch)
        repo.create_git_ref(ref=f"refs/heads/{new_branch}", sha=base.commit.sha)
        console_obj.print(f"✅ Created branch {new_branch} from {base_branch}")
        log_action(f"Created branch {new_branch} from {base_branch} in {repo.full_name}")
        return new_branch
    except Exception as e:
        console_obj.print(f"[red]Error creating branch: {e}[/red]")
        return None


def delete_branch(repo, console_obj, prompt):
    branch_name = prompt.ask("Branch name to delete")
    if branch_name == repo.default_branch:
        console_obj.print("[yellow]Cannot delete the default branch via this tool. Change default first.[/yellow]")
        return
    try:
        ref = repo.get_git_ref(f"heads/{branch_name}")
        ref.delete()
        console_obj.print(f"🗑️ Deleted branch: {branch_name}")
        log_action(f"Deleted branch {branch_name} in {repo.full_name}")
    except Exception as e:
        console_obj.print(f"[red]Delete branch failed: {e}[/red]")


def switch_default_branch(repo, console_obj, prompt):
    current = repo.default_branch
    new = prompt.ask(f"Enter branch name to set as default (current: {current})")
    try:
        repo.edit(default_branch=new)
        console_obj.print(f"🔀 Default branch set to {new}")
        log_action(f"Set default branch to {new} for {repo.full_name}")
    except Exception as e:
        console_obj.print(f"[red]Failed to switch default branch: {e}[/red]")


# ---------------------------
# File/Folder operations (API)
# ---------------------------
def create_or_edit_file_via_api(repo, console_obj, prompt):
    path = prompt.ask("Repository file path (e.g., README.md or src/app.py)")
    content = prompt.ask("Enter content (leave blank to create empty file)", default="")
    branch = prompt.ask("Branch to use", default=repo.default_branch)
    try:
        try:
            existing = repo.get_contents(path, ref=branch)
            repo.update_file(existing.path, f"Update {path}", content, existing.sha, branch=branch)
            console_obj.print(f"📝 Updated {path} on {branch}")
            log_action(f"Updated file {path} on {repo.full_name}@{branch}")
        except GithubException:
            repo.create_file(path, f"Create {path}", content, branch=branch)
            console_obj.print(f"🆕 Created {path} on {branch}")
            log_action(f"Created file {path} on {repo.full_name}@{branch}")
    except Exception as e:
        console_obj.print(f"[red]API file operation failed: {e}[/red]")


def create_folder_placeholder(repo, console_obj, prompt):
    folder_path = prompt.ask("Folder path (e.g., src/utils)")
    branch = prompt.ask("Branch name", default=repo.default_branch)
    try:
        placeholder = f"{folder_path.rstrip('/')}/.gitkeep"
        repo.create_file(placeholder, f"Create folder {folder_path}", "", branch=branch)
        console_obj.print(f"📁 Created folder: {folder_path} in {branch}")
        log_action(f"Created folder placeholder {placeholder} on {repo.full_name}@{branch}")
    except Exception as e:
        console_obj.print(f"[red]Failed to create folder: {e}[/red]")


def delete_file_via_api(repo, console_obj, prompt):
    file_path = prompt.ask("File path to delete (e.g., src/app.py)")
    branch = prompt.ask("Branch name", default=repo.default_branch)
    try:
        contents = repo.get_contents(file_path, ref=branch)
        repo.delete_file(contents.path, f"Delete {file_path}", contents.sha, branch=branch)
        console_obj.print(f"🗑️ Deleted {file_path} on {branch}")
        log_action(f"Deleted file {file_path} on {repo.full_name}@{branch}")
    except Exception as e:
        console_obj.print(f"[red]Error: {e}[/red]")


def list_files_via_api(repo, console_obj, prompt):
    path = prompt.ask("Folder path in repo (blank for root)", default="")
    branch = prompt.ask("Branch name", default=repo.default_branch)
    try:
        contents = repo.get_contents(path or "", ref=branch)
        table = Table(title=f"Files in {repo.full_name}/{path or '.'} [{branch}]")
        table.add_column("Type")
        table.add_column("Path", style="yellow")
        table.add_column("Size", justify="right")
        for c in contents:
            ctype = "Folder" if c.type == "dir" else "File"
            table.add_row(ctype, c.path, str(c.size or "-"))
        console_obj.print(table)
    except Exception as e:
        console_obj.print(f"[red]Failed to list files: {e}[/red]")


def view_file_via_api(repo, console_obj, prompt):
    file_path = prompt.ask("File path to view")
    branch = prompt.ask("Branch name", default=repo.default_branch)
    try:
        contents = repo.get_contents(file_path, ref=branch)
        console_obj.rule(f"{file_path} [{branch}]")
        console_obj.print(contents.decoded_content.decode(errors="replace"))
        console_obj.rule()
    except Exception as e:
        console_obj.print(f"[red]Failed to view file: {e}[/red]")


# ===============================================================
#  GIT PUSH HANDLER (local git push using GitPython)
# ===============================================================
def upload_file_to_github(
    repo: Repository.Repository,
    file_path: str,
    branch_name: str,
    commit_message: str,
    token: str,
    user_obj,
    console_obj: Console
) -> bool:
    """Uploads a local file or folder to GitHub repo using git push (clone to temp, copy, commit, push)."""
    temp_dir = tempfile.mkdtemp(prefix="gh_clone_")
    try:
        console_obj.print(f"[yellow]Cloning repo {repo.name} into {temp_dir}[/yellow]")
        # construct HTTPS url with token (do not print token)
        repo_url = f"https://{token}@github.com/{repo.owner.login}/{repo.name}.git"
        git.Repo.clone_from(repo_url, temp_dir, branch=branch_name)
        git_repo = git.Repo(temp_dir)

        if os.path.isdir(file_path):
            dest = os.path.join(temp_dir, os.path.basename(file_path.rstrip(os.sep)))
            shutil.copytree(file_path, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(file_path, os.path.join(temp_dir, os.path.basename(file_path)))

        # remove common ignored items if they exist in the temp
        ignore_list = ['.env', '__pycache__', '.gitignore']
        for ignore_item in ignore_list:
            path = os.path.join(temp_dir, ignore_item)
            if os.path.exists(path):
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)

        git_repo.git.add(A=True)
        git_repo.index.commit(commit_message)
        origin = git_repo.remote(name="origin")
        origin.push()

        console_obj.print(f"[green]✅ Successfully pushed to {repo.name}:{branch_name}[/green]")
        log_action(f"Pushed to {repo.full_name}@{branch_name} with message: {commit_message}")
        return True
    except Exception as e:
        console_obj.print(f"[red]Error uploading to GitHub: {e}[/red]")
        log_action(f"Error uploading to GitHub: {e}")
        return False
    finally:
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass


# ===============================================================
#  Local Git Sync Manager (file-based local repo management)
# ===============================================================
def run_shell(cmd: List[str], silent: bool = False):
    """Run shell command safely and raise on failure."""
    if not silent:
        console.print(f"🚀 Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def ensure_local_repo(repo_path: str, default_clone_url: Optional[str] = None, token: Optional[str] = None) -> bool:
    """
    Ensure the local repo exists at repo_path. If not, prompt to clone.
    Returns True if repo_path exists (after clone or previously), otherwise False.
    """
    if os.path.isdir(repo_path) and os.path.isdir(os.path.join(repo_path, ".git")):
        return True

    console.print(f"⚠️ Repository not found at: [yellow]{repo_path}[/yellow]\n")
    console.print("1) Clone a new repository")
    console.print("2) Cancel / Exit")
    choice = Prompt.ask("\n👉 Enter your choice (1-2)", default="2").strip()

    if choice != "1":
        console.print("👋 Cancelled by user. Exiting local sync.")
        return False

    repo_url = Prompt.ask("\n🌐 Enter GitHub repository URL to clone (HTTPS preferred)")
    if not repo_url:
        console.print("❌ No URL provided. Exiting...")
        return False

    # If token provided, inject into URL if it's a plain https URL
    try:
        if repo_url.startswith("https://") and "@" not in repo_url and token:
            safe_url = repo_url.replace("https://", f"https://{token}@")
        else:
            safe_url = repo_url

        os.makedirs(os.path.dirname(repo_path), exist_ok=True)
        run_shell(["git", "clone", safe_url, repo_path])
        console.print(f"✅ Repository cloned successfully into: [green]{repo_path}[/green]\n")
        log_action(f"Cloned repository from {repo_url} to {repo_path}")
        return True
    except subprocess.CalledProcessError as e:
        console.print(f"❌ Failed to clone repository: {e}")
        log_action(f"Failed to clone repository: {e}")
        return False


def fix_local_remote_with_token(repo_path: str, token: str):
    """Attempt to fix origin remote to include token (for push/pull non-interactive)."""
    try:
        origin_url = subprocess.check_output(["git", "-C", repo_path, "remote", "get-url", "origin"], text=True).strip()
        if origin_url.startswith("https://") and "@" not in origin_url:
            new_url = origin_url.replace("https://", f"https://{token}@")
            subprocess.run(["git", "-C", repo_path, "remote", "set-url", "origin", new_url], check=True)
            log_action(f"Updated origin remote for {repo_path}")
    except Exception:
        # Non-fatal
        pass


def local_git_menu():
    """Interactive local git menu to pull, push, sync a chosen local repo."""
    base_repo_path = Prompt.ask("Local repository path (default)", default=REPO_PATH)
    repo_path = os.path.abspath(os.path.expanduser(base_repo_path))

    ok = ensure_local_repo(repo_path, token=TOKEN)
    if not ok:
        return

    # Configure identity if needed
    try:
        subprocess.run(["git", "-C", repo_path, "config", "user.name", "Auto Commit Bot"], check=True)
        subprocess.run(["git", "-C", repo_path, "config", "user.email", "autocommit@example.com"], check=True)
    except Exception:
        console.print("⚠️ Warning: Could not set git identity (non-fatal).")

    fix_local_remote_with_token(repo_path, TOKEN)

    def show_menu_local():
        console.print(Panel(f"📂 GIT ACTIONS — Local Repo: [bold]{repo_path}[/bold]"))
        console.print("1) Pull (update from GitHub)")
        console.print("2) Push (upload local changes)")
        console.print("3) Sync (pull + push)")
        console.print("4) Exit")
        return Prompt.ask("\n👉 Enter your choice (1-4): ").strip()

    while True:
        choice = show_menu_local()
        try:
            if choice == "1":
                console.print("\n🔄 Pulling latest changes...")
                run_shell(["git", "-C", repo_path, "pull"])
                console.print("✅ Repository updated successfully!\n")
                log_action(f"Pulled latest changes in {repo_path}")

            elif choice == "2":
                console.print("\n⬆️ Pushing local changes...")
                commit_msg = Prompt.ask("Commit message (default)", default=DEFAULT_COMMIT_MSG)
                run_shell(["git", "-C", repo_path, "add", "."])
                commit = subprocess.run(["git", "-C", repo_path, "commit", "-m", commit_msg])
                if commit.returncode == 0:
                    run_shell(["git", "-C", repo_path, "push"])
                    console.print("✅ Successfully pushed to GitHub!\n")
                    log_action(f"Pushed changes in {repo_path} with message: {commit_msg}")
                else:
                    console.print("ℹ️ Nothing to commit (working tree clean).\n")
                    log_action(f"Nothing to commit in {repo_path}")

            elif choice == "3":
                console.print("\n🔁 Syncing repository (pull then push)...")
                run_shell(["git", "-C", repo_path, "pull"])
                commit_msg = Prompt.ask("Commit message (default)", default="Auto sync via Unified Manager")
                run_shell(["git", "-C", repo_path, "add", "."])
                commit = subprocess.run(["git", "-C", repo_path, "commit", "-m", commit_msg])
                if commit.returncode == 0:
                    run_shell(["git", "-C", repo_path, "push"])
                    console.print("✅ Repository synced successfully!\n")
                    log_action(f"Synced repository {repo_path} with message: {commit_msg}")
                else:
                    console.print("ℹ️ Nothing to sync (working tree clean).\n")
                    log_action(f"Nothing to sync in {repo_path}")

            elif choice == "4":
                console.print("\n👋 Exiting local git menu.\n")
                log_action(f"Exited local git menu for {repo_path}")
                break
            else:
                console.print("⚠️ Invalid choice. Try again.\n")
        except subprocess.CalledProcessError as e:
            console.print(f"❌ Git command failed: {e}\n")
            log_action(f"Git command failed for {repo_path}: {e}")
            # continue loop


# ===============================================================
#  UI: Repo selection and menus
# ===============================================================
def select_repo() -> Optional[Repository.Repository]:
    repos = list_repos(user, limit=200)
    if not repos:
        console.print("[yellow]No repositories found.[/yellow]")
        if Confirm.ask("Create one now?"):
            return create_repo(user, console, Prompt, Confirm)
        return None

    table = Table(title=f"Your Repositories (Top {len(repos)})")
    table.add_column("No", justify="center", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Visibility", justify="center")
    for i, r in enumerate(repos, 1):
        vis = "Private 🔒" if r.private else "Public 🌍"
        table.add_row(str(i), r.name, vis)
    console.print(table)
    console.print("[blue]0[/blue] → Create new repository")

    choice = Prompt.ask("Enter repo number", default="1")
    try:
        idx = int(choice)
    except ValueError:
        console.print("[red]Invalid input[/red]")
        return None

    if idx == 0:
        return create_repo(user, console, Prompt, Confirm)
    if 1 <= idx <= len(repos):
        return repos[idx - 1]
    console.print("[red]Choice out of range[/red]")
    return None


def repo_manage_menu():
    repo = select_repo()
    if not repo:
        return

    while True:
        console.rule(f"[bold]Repository:[/bold] {repo.full_name}  (default: {repo.default_branch})")
        console.print("""
a) Create folder
b) Create/Edit file
c) Delete file
d) List files
e) View file
f) Branch operations
g) Repo settings (rename/visibility/delete/transfer)
h) Upload local folder via git push (temp clone)
i) Return to main menu
""")
        sub = Prompt.ask("Choose option").strip().lower()

        if sub == "a":
            create_folder_placeholder(repo, console, Prompt)
        elif sub == "b":
            create_or_edit_file_via_api(repo, console, Prompt)
        elif sub == "c":
            delete_file_via_api(repo, console, Prompt)
        elif sub == "d":
            list_files_via_api(repo, console, Prompt)
        elif sub == "e":
            view_file_via_api(repo, console, Prompt)
        elif sub == "f":
            branches = list_branches(repo, console)
            console.print("Options: [1] Create  [2] Delete  [3] Switch Default")
            action = Prompt.ask("Choose", default="1")
            if action == "1":
                create_branch(repo, console, Prompt, repo.default_branch)
            elif action == "2":
                delete_branch(repo, console, Prompt)
            elif action == "3":
                switch_default_branch(repo, console, Prompt)
        elif sub == "g":
            console.print("Options: [1] Rename  [2] Visibility  [3] Delete Repo  [4] Transfer")
            choice = Prompt.ask("Choose", default="1")
            if choice == "1":
                rename_repo(repo, console, Prompt)
            elif choice == "2":
                change_repo_visibility(repo, console, Confirm)
            elif choice == "3":
                if delete_repo_confirm(repo, console, Confirm):
                    return
            elif choice == "4":
                transfer_repository(repo, console, Prompt, Confirm)
        elif sub == "h":
            # Upload via temp clone method
            branch_name = Prompt.ask("Branch to push to", default=repo.default_branch)
            file_path = Prompt.ask("Local path to upload (absolute or relative)", default=".")
            commit_message = Prompt.ask("Commit message", default="Upload via GitHub Manager")
            upload_file_to_github(repo, file_path, branch_name, commit_message, TOKEN, user, console)
        elif sub == "i":
            break
        else:
            console.print("[red]Invalid option[/red]")


def main_menu():
    console.print("[bold magenta]GitHub Manager — Unified Edition[/bold magenta]")
    while True:
        console.rule("[bold blue]Main Menu[/bold blue]")
        console.print("""
1) Create new repository
2) Rename repository
3) Delete repository
4) Manage repository (files/branches)
5) Upload local folder/file to a repo (git push via temp clone)
6) Local Git Pull/Push Manager (clone/pull/push/sync)
7) List repositories
8) Exit
""")
        choice = Prompt.ask("Enter your choice").strip()
        if choice == "1":
            create_repo(user, console, Prompt, Confirm)
        elif choice == "2":
            repo = select_repo()
            if repo:
                rename_repo(repo, console, Prompt)
        elif choice == "3":
            repo = select_repo()
            if repo:
                delete_repo_confirm(repo, console, Confirm)
        elif choice == "4":
            repo_manage_menu()
        elif choice == "5":
            repo = select_repo()
            if repo:
                branch_name = Prompt.ask("Branch", default=repo.default_branch)
                file_path = Prompt.ask("Local path to upload (absolute or relative)", default=".")
                commit_message = Prompt.ask("Commit message", default=DEFAULT_COMMIT_MSG)
                upload_file_to_github(repo, file_path, branch_name, commit_message, TOKEN, user, console)
        elif choice == "6":
            local_git_menu()
        elif choice == "7":
            repos = list_repos(user, limit=200)
            table = Table(title=f"Your Repositories (Top {len(repos)})")
            table.add_column("No", justify="center", style="cyan")
            table.add_column("Name", style="bold")
            table.add_column("Visibility", justify="center")
            for i, r in enumerate(repos, 1):
                vis = "Private 🔒" if r.private else "Public 🌍"
                table.add_row(str(i), r.name, vis)
            console.print(table)
        elif choice == "8":
            console.print("[bold magenta]Exiting...[/bold magenta]")
            log_action("Exited Unified GitHub Manager")
            sys.exit(0)
        else:
            console.print("[red]Invalid input[/red]")


# ===============================================================
#  MAIN ENTRY POINT
# ===============================================================
if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Interrupted by user. Exiting...[/bold yellow]")
        log_action("Interrupted by user - exited")
        sys.exit(0)
