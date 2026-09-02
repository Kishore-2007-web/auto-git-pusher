"""
git_manager.py - Safe subprocess wrapper for Git operations in Daily GitHub Agent.

Strictly adheres to safety rules:
- No shell=True execution
- No global `git add .` or `git add -A`
- No destructive commands (`git reset --hard`, `git clean`, `git push --force`)
- Staging limited exclusively to allowed target files
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger("daily_github_agent")


class GitError(Exception):
    """Raised when a git command fails or repository is invalid."""
    pass


def _run_git_command(
    args: List[str],
    cwd: Optional[Path] = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """
    Execute a Git command safely using subprocess list arguments (shell=False).
    """
    full_cmd = ["git"] + args
    cwd_str = str(cwd) if cwd else None
    logger.debug(f"Executing Git command: {' '.join(full_cmd)} (cwd={cwd_str})")

    try:
        result = subprocess.run(
            full_cmd,
            cwd=cwd_str,
            capture_output=True,
            text=True,
            shell=False,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        raise GitError("Git executable was not found on your system. Please install Git and add it to PATH.")
    except Exception as e:
        raise GitError(f"Unexpected error executing Git command: {e}")

    if check and result.returncode != 0:
        err_msg = result.stderr.strip() or result.stdout.strip()
        raise GitError(f"Git command '{' '.join(full_cmd)}' failed (exit code {result.returncode}): {err_msg}")

    return result


def check_git_installed() -> Tuple[bool, str]:
    """
    Check if Git is installed and return its version.
    """
    try:
        proc = _run_git_command(["--version"], check=True)
        return True, proc.stdout.strip()
    except GitError as e:
        return False, str(e)


def check_git_repository(repo_path: Path) -> Tuple[bool, str]:
    """
    Verify if the target directory is a valid Git repository work tree.
    """
    if not repo_path.exists() or not repo_path.is_dir():
        return False, f"Directory does not exist: '{repo_path}'"

    proc = _run_git_command(["rev-parse", "--is-inside-work-tree"], cwd=repo_path, check=False)
    if proc.returncode == 0 and proc.stdout.strip() == "true":
        return True, "Valid Git repository"
    else:
        err = proc.stderr.strip() or "Not a Git repository"
        return False, f"'{repo_path.name}' is not a Git repository ({err})"


def get_status(repo_path: Path) -> str:
    """
    Get short status of the Git repository.
    """
    proc = _run_git_command(["status", "--short"], cwd=repo_path, check=True)
    return proc.stdout.strip()


def get_changed_files(repo_path: Path) -> List[str]:
    """
    Retrieve list of relative paths of all modified or untracked files in the repository.
    """
    proc = _run_git_command(["status", "--porcelain"], cwd=repo_path, check=True)
    lines = proc.stdout.splitlines()
    changed: List[str] = []
    for line in lines:
        if not line.strip():
            continue
        if len(line) >= 3:
            # First 2 chars are status code (e.g. ' M', 'M ', '??', 'A ')
            entry = line[2:].lstrip()
            if " -> " in entry:
                entry = entry.split(" -> ")[-1].strip()
            # Strip quotes if git wrapped filenames
            entry = entry.strip('"\'')
            if entry:
                changed.append(entry)
    return changed


def is_git_clean(repo_path: Path) -> Tuple[bool, List[str]]:
    """
    Check if the repository has no uncommitted changes (ignoring temporary .agent_bak files).
    """
    all_changed = get_changed_files(repo_path)
    # Filter out agent backup files from dirty check
    meaningful_changes = [f for f in all_changed if not f.endswith(".agent_bak")]
    return len(meaningful_changes) == 0, meaningful_changes


def get_diff(repo_path: Path, file_rel_path: Optional[str] = None, staged: bool = False) -> str:
    """
    Get unified diff for the repository or a specific file.
    """
    args = ["diff"]
    if staged:
        args.append("--staged")
    if file_rel_path:
        args.extend(["--", file_rel_path])

    proc = _run_git_command(args, cwd=repo_path, check=True)
    return proc.stdout.strip()


def git_add(repo_path: Path, file_rel_path: str) -> None:
    """
    Stage ONLY the specific allowed file. Never use 'git add .' or 'git add -A'.
    """
    if file_rel_path in (".", "./", "*") or not file_rel_path.strip():
        raise GitError("Refusing to stage entire directory or wildcard. Only specific file paths allowed.")

    norm_path = file_rel_path.replace("\\", "/")
    logger.info(f"Staging single file: {norm_path}")
    _run_git_command(["add", "--", norm_path], cwd=repo_path, check=True)


def git_commit(repo_path: Path, commit_message: str) -> str:
    """
    Commit staged changes with the provided commit message and return the new commit hash.
    """
    if not commit_message.strip():
        raise GitError("Commit message cannot be empty.")

    logger.info(f"Committing with message: '{commit_message}'")
    _run_git_command(["commit", "-m", commit_message], cwd=repo_path, check=True)

    # Get latest commit hash
    hash_proc = _run_git_command(["rev-parse", "--short", "HEAD"], cwd=repo_path, check=True)
    return hash_proc.stdout.strip()


def get_current_branch(repo_path: Path) -> str:
    """
    Get the name of the current active Git branch.
    """
    proc = _run_git_command(["branch", "--show-current"], cwd=repo_path, check=False)
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    return "main"


def git_push(repo_path: Path, remote: str = "origin", branch: Optional[str] = None) -> str:
    """
    Push committed changes to remote repository. Never forces push.
    """
    target_branch = branch or get_current_branch(repo_path)
    logger.info(f"Pushing to remote '{remote}' branch '{target_branch}'...")

    proc = _run_git_command(["push", remote, target_branch], cwd=repo_path, check=True)
    out = proc.stdout.strip() or proc.stderr.strip() or f"Pushed successfully to {remote}/{target_branch}"
    return out


def git_pull(repo_path: Path, remote: str = "origin", branch: Optional[str] = None) -> Tuple[bool, str]:
    """
    Pull latest changes from remote repository safely before execution.
    """
    target_branch = branch or get_current_branch(repo_path)
    logger.info(f"Pulling latest from remote '{remote}' branch '{target_branch}'...")

    proc = _run_git_command(["pull", remote, target_branch], cwd=repo_path, check=False)
    if proc.returncode == 0:
        out = proc.stdout.strip() or f"Pulled successfully from {remote}/{target_branch}"
        return True, out
    else:
        err = proc.stderr.strip() or proc.stdout.strip() or "git pull failed"
        logger.warning(f"Git pull warning: {err}")
        return False, err


def undo_last_commit(repo_path: Path) -> None:
    """
    Undo the last local commit (reset HEAD~1) safely if subsequent steps (like push) fail.
    """
    logger.info("Undoing last local commit to maintain clean repository state...")
    _run_git_command(["reset", "HEAD~1"], cwd=repo_path, check=False)

