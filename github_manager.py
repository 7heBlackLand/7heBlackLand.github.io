#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Manager — All-In-One Script
Includes:
 - Auto dependency installer
 - .env-based GitHub authentication
 - Repository management (create, rename, delete, transfer)
 - Branch management
 - File/folder management via API
 - Local file/folder upload via Git push
"""

from __future__ import annotations
import os
import sys
import subprocess
import shutil
import tempfile
import git
from typing import Optional
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
# Load .env and authenticate
# ---------------------------
load_dotenv(dotenv_path="/home/gost/account/.env")

TOKEN = os.getenv("GITHUB_TOKEN")
console = Console()

if not TOKEN:
    console.print("[bold red]❌ GITHUB_TOKEN not found in /home/gost/account/.env — please add and re-run.[/bold red]")
    sys.exit(1)

try:
    auth = Auth.Token(TOKEN)
    g = Github(auth=auth)
    user = g.get_user()
    console.print(f"✅ Authenticated as: [green]{user.login}[/green]\n")
except Exception as e:
    console.print(f"[bold red]❌ GitHub authentication failed: {e}[/bold red]")
    sys.exit(1)

# ===============================================================
#  API MANAGER FUNCTIONS
# ===============================================================

def list_repos(user, console, limit: int = 50) -> list:
    """Lists repositories of the authenticated user."""
    try:
        return list(user.get_repos())[:limit]
    except Exception as e:
        console.print(f"[red]Failed to load repositories: {e}[/red]")
        return []


def create_repo(user, console, Prompt, Confirm):
    """Creates a new GitHub repository."""
    name = Prompt.ask("Repository name")
    description = Prompt.ask("Description", default=f"Repository {name}")
    is_private = Confirm.ask("Make repository PRIVATE?", default=False)
    auto_init = Confirm.ask("Initialize repo with README on GitHub (auto-init)?", default=False)
    try:
        repo = user.create_repo(name=name, description=description, private=is_private, auto_init=auto_init)
        console.print(f"✅ Created repository: [green]{repo.full_name}[/green]")
        return repo
    except GithubException as e:
        console.print(f"[red]GitHub API error: {e.data}[/red]")
        return None
    except Exception as e:
        console.print(f"[red]Error creating repository: {e}[/red]")
        return None


def rename_repo(repo, console, Prompt):
    new_name = Prompt.ask("New repository name", default=repo.name)
    try:
        repo.edit(name=new_name)
        console.print(f"✏️ Renamed to [yellow]{new_name}[/yellow]")
    except Exception as e:
        console.print(f"[red]Rename failed: {e}[/red]")


def delete_repo_confirm(repo, console, Confirm):
    confirm = Confirm.ask(f"Are you sure you want to DELETE repository '{repo.full_name}'? This is irreversible!", default=False)
    if not confirm:
        console.print("[cyan]Delete cancelled.[/cyan]")
        return False
    try:
        repo.delete()
        console.print(f"🗑️ Deleted repository: [red]{repo.full_name}[/red]")
        return True
    except Exception as e:
        console.print(f"[red]Delete failed: {e}[/red]")
        return False


def edit_repo_description(repo, console, Prompt):
    new_desc = Prompt.ask("New description", default=repo.description or "")
    try:
        repo.edit(description=new_desc)
        console.print("✅ Description updated.")
    except Exception as e:
        console.print(f"[red]Update failed: {e}[/red]")


def change_repo_visibility(repo, console, Confirm):
    current = "Private" if repo.private else "Public"
    console.print(f"Current visibility: {current}")
    make_private = Confirm.ask("Make repository PRIVATE? (Choose No to make it PUBLIC)")
    try:
        repo.edit(private=make_private)
        console.print(f"✅ Visibility changed to: {'Private' if make_private else 'Public'}")
    except Exception as e:
        console.print(f"[red]Visibility change failed: {e}[/red]")


def transfer_repository(repo, console, Prompt, Confirm):
    console.print("[yellow]Repository transfer is a sensitive operation and requires admin rights on target.[/yellow]")
    new_owner = Prompt.ask("Enter new owner username or organization name")
    confirm = Confirm.ask(f"Are you sure you want to transfer '{repo.full_name}' to '{new_owner}'?", default=False)
    if not confirm:
        console.print("[cyan]Transfer cancelled.[/cyan]")
        return
    try:
        owner = repo.owner.login
        repo_name = repo.name
        transfer_body = {"new_owner": new_owner}
        repo._requester.requestJsonAndCheck("POST", f"/repos/{owner}/{repo_name}/transfer", input=transfer_body)
        console.print(f"✅ Transfer requested to {new_owner}.")
    except Exception as e:
        console.print(f"[red]Transfer failed: {e}[/red]")


# ---------------------------
# Branch operations
# ---------------------------
def list_branches(repo, console, Table):
    try:
        branches = repo.get_branches()
        table = Table(title=f"Branches in {repo.full_name}")
        table.add_column("Branch Name", style="green")
        for b in branches:
            table.add_row(b.name)
        console.print(table)
        return list(branches)
    except Exception as e:
        console.print(f"[red]Failed to list branches: {e}[/red]")
        return []


def create_branch(repo, console, Prompt, branches: list, base_branch: str):
    new_branch = Prompt.ask("New branch name")
    try:
        base = repo.get_branch(base_branch)
        repo.create_git_ref(ref=f"refs/heads/{new_branch}", sha=base.commit.sha)
        console.print(f"✅ Created branch {new_branch} from {base_branch}")
        return new_branch
    except Exception as e:
        console.print(f"[red]Error creating branch: {e}[/red]")
        return None


def delete_branch(repo, console, Prompt):
    branch_name = Prompt.ask("Branch name to delete")
    if branch_name == repo.default_branch:
        console.print("[yellow]Cannot delete the default branch via this tool. Change default first.[/yellow]")
        return
    try:
        ref = repo.get_git_ref(f"heads/{branch_name}")
        ref.delete()
        console.print(f"🗑️ Deleted branch: {branch_name}")
    except Exception as e:
        console.print(f"[red]Delete branch failed: {e}[/red]")


def switch_default_branch(repo, console, Prompt):
    current = repo.default_branch
    new = Prompt.ask(f"Enter branch name to set as default (current: {current})")
    try:
        repo.edit(default_branch=new)
        console.print(f"🔀 Default branch set to {new}")
    except Exception as e:
        console.print(f"[red]Failed to switch default branch: {e}[/red]")


# ---------------------------
# File/Folder operations
# ---------------------------
def create_or_edit_file_via_api(repo, console, Prompt):
    path = Prompt.ask("Repository file path (e.g., README.md or src/app.py)")
    content = Prompt.ask("Enter content (leave blank to create empty file)", default="")
    branch = Prompt.ask("Branch to use", default=repo.default_branch)
    try:
        try:
            existing = repo.get_contents(path, ref=branch)
            repo.update_file(existing.path, f"Update {path}", content, existing.sha, branch=branch)
            console.print(f"📝 Updated {path} on {branch}")
        except GithubException:
            repo.create_file(path, f"Create {path}", content, branch=branch)
            console.print(f"🆕 Created {path} on {branch}")
    except Exception as e:
        console.print(f"[red]API file operation failed: {e}[/red]")


def create_folder_placeholder(repo, console, Prompt):
    folder_path = Prompt.ask("Folder path (e.g., src/utils)")
    branch = Prompt.ask("Branch name", default=repo.default_branch)
    try:
        placeholder = f"{folder_path.rstrip('/')}/.gitkeep"
        repo.create_file(placeholder, f"Create folder {folder_path}", "", branch=branch)
        console.print(f"📁 Created folder: {folder_path} in {branch}")
    except Exception as e:
        console.print(f"[red]Failed to create folder: {e}[/red]")


def delete_file_via_api(repo, console, Prompt):
    file_path = Prompt.ask("File path to delete (e.g., src/app.py)")
    branch = Prompt.ask("Branch name", default=repo.default_branch)
    try:
        contents = repo.get_contents(file_path, ref=branch)
        repo.delete_file(contents.path, f"Delete {file_path}", contents.sha, branch=branch)
        console.print(f"🗑️ Deleted {file_path} on {branch}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


def list_files_via_api(repo, console, Prompt, Table):
    path = Prompt.ask("Folder path in repo (blank for root)", default="")
    branch = Prompt.ask("Branch name", default=repo.default_branch)
    try:
        contents = repo.get_contents(path or "", ref=branch)
        table = Table(title=f"Files in {repo.full_name}/{path or '.'} [{branch}]")
        table.add_column("Type")
        table.add_column("Path", style="yellow")
        table.add_column("Size", justify="right")
        for c in contents:
            ctype = "Folder" if c.type == "dir" else "File"
            table.add_row(ctype, c.path, str(c.size or "-"))
        console.print(table)
    except Exception as e:
        console.print(f"[red]Failed to list files: {e}[/red]")


def view_file_via_api(repo, console, Prompt):
    file_path = Prompt.ask("File path to view")
    branch = Prompt.ask("Branch name", default=repo.default_branch)
    try:
        contents = repo.get_contents(file_path, ref=branch)
        console.rule(f"{file_path} [{branch}]")
        console.print(contents.decoded_content.decode(errors="replace"))
        console.rule()
    except Exception as e:
        console.print(f"[red]Failed to view file: {e}[/red]")


# ===============================================================
#  GIT PUSH HANDLER
# ===============================================================
def upload_file_to_github(
    repo: Repository,
    file_path: str,
    branch_name: str,
    commit_message: str,
    token: str,
    user,
    console: Console
) -> bool:
    """Uploads a local file or folder to GitHub repo using git push."""
    temp_dir = tempfile.mkdtemp(prefix="gh_clone_")
    try:
        console.print(f"[yellow]Cloning repo {repo.name} into {temp_dir}[/yellow]")
        repo_url = f"https://{token}@github.com/{repo.owner.login}/{repo.name}.git"
        git.Repo.clone_from(repo_url, temp_dir, branch=branch_name)
        git_repo = git.Repo(temp_dir)

        if os.path.isdir(file_path):
            shutil.copytree(file_path, os.path.join(temp_dir, os.path.basename(file_path)), dirs_exist_ok=True)
        else:
            shutil.copy2(file_path, os.path.join(temp_dir, os.path.basename(file_path)))

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

        console.print(f"[green]✅ Successfully pushed to {repo.name}:{branch_name}[/green]")
        return True
    except Exception as e:
        console.print(f"[red]Error uploading to GitHub: {e}[/red]")
        return False
    finally:
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass


# ===============================================================
#  MENU SYSTEM
# ===============================================================
def select_repo() -> Optional:
    repos = list_repos(user, console)
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
g) Repo settings (rename/visibility/delete)
h) Upload local folder via git push
z) Back
""")
        sub = Prompt.ask("Choose option").strip().lower()

        if sub == "a":
            create_folder_placeholder(repo, console, Prompt)
        elif sub == "b":
            create_or_edit_file_via_api(repo, console, Prompt)
        elif sub == "c":
            delete_file_via_api(repo, console, Prompt)
        elif sub == "d":
            list_files_via_api(repo, console, Prompt, Table)
        elif sub == "e":
            view_file_via_api(repo, console, Prompt)
        elif sub == "f":
            branches = list_branches(repo, console, Table)
            console.print("Options: [1] Create  [2] Delete  [3] Switch Default")
            action = Prompt.ask("Choose", default="1")
            if action == "1":
                create_branch(repo, console, Prompt, branches, repo.default_branch)
            elif action == "2":
                delete_branch(repo, console, Prompt)
            elif action == "3":
                switch_default_branch(repo, console, Prompt)
        elif sub == "g":
            console.print("Options: [1] Rename  [2] Visibility  [3] Delete Repo")
            choice = Prompt.ask("Choose", default="1")
            if choice == "1":
                rename_repo(repo, console, Prompt)
            elif choice == "2":
                change_repo_visibility(repo, console, Confirm)
            elif choice == "3":
                delete_repo_confirm(repo, console, Confirm)
                return
        elif sub == "h":
            branch_name = Prompt.ask("Branch to push to", default=repo.default_branch)
            file_path = Prompt.ask("Local path", default=".")
            commit_message = Prompt.ask("Commit message", default="Upload via GitHub Manager")
            upload_file_to_github(repo, file_path, branch_name, commit_message, TOKEN, user, console)
        elif sub == "z":
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
5) Upload local folder/file (git push)
6) List repositories
7) Exit
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
                file_path = Prompt.ask("Local path", default=".")
                commit_message = Prompt.ask("Commit message", default="Upload via GitHub Manager")
                upload_file_to_github(repo, file_path, branch_name, commit_message, TOKEN, user, console)
        elif choice == "6":
            list_repos(user, console)
        elif choice == "7":
            console.print("[bold magenta]Exiting...[/bold magenta]")
            sys.exit(0)
        else:
            console.print("[red]Invalid input[/red]")


# ===============================================================
#  MAIN ENTRY POINT
# ===============================================================
if __name__ == "__main__":
    main_menu()
