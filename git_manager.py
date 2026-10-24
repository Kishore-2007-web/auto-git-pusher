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
import os
import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger("daily_github_agent")

DEFAULT_GIT_TIMEOUT: int = 120

# Regex patterns for redacting sensitive credentials and tokens in logs
_REDACTION_PATTERNS = [
    (re.compile(r"https?://(?:[^:@/]+(?::[^@/]*)?@)"), "https://[REDACTED_CREDENTIAL]@"),
    (re.compile(r"ghp_[A-Za-z0-9]{36}"), "[REDACTED_GH_TOKEN]"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{82}"), "[REDACTED_GH_PAT]"),
    (re.compile(r"ghs_[A-Za-z0-9]{36}"), "[REDACTED_GH_APP_TOKEN]"),
]


def redact_sensitive_text(text: str) -> str:
    """
    Mask any personal access tokens, app tokens, or basic auth credentials from text.
    """
    if not text:
        return text
    redacted = text
    for pattern, replacement in _REDACTION_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


class GitError(Exception):
    """Raised when a git command fails or repository is invalid."""
    pass


def _run_git_command(
    args: List[str],
    cwd: Optional[Path] = None,
    check: bool = True,
    timeout: int = DEFAULT_GIT_TIMEOUT,
) -> subprocess.CompletedProcess[str]:
    """
    Execute a Git command safely using subprocess list arguments (shell=False) with bounded timeout.
    """
    full_cmd = ["git"] + args
    cwd_str = str(cwd) if cwd else None
    sanitized_cmd = redact_sensitive_text(" ".join(full_cmd))
    logger.debug(f"Executing Git command: {sanitized_cmd} (cwd={cwd_str})")

    # Enforce non-interactive credential prompts to fail closed rather than hanging in CI
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    try:
        result = subprocess.run(
            full_cmd,
            cwd=cwd_str,
            capture_output=True,
            text=True,
            shell=False,
            check=False,
            timeout=timeout,
            env=env,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        raise GitError("Git executable was not found on your system. Please install Git and add it to PATH.")
    except subprocess.TimeoutExpired:
        raise GitError(f"Git command timed out after {timeout} seconds: {sanitized_cmd}")
    except Exception as e:
        raise GitError(f"Unexpected error executing Git command: {redact_sensitive_text(str(e))}")

    if check and result.returncode != 0:
        raw_err = result.stderr.strip() or result.stdout.strip()
        err_msg = redact_sensitive_text(raw_err)
        raise GitError(f"Git command '{sanitized_cmd}' failed (exit code {result.returncode}): {err_msg}")

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
    Uses --message= flag to prevent option injection if message starts with '-'.
    """
    if not commit_message.strip():
        raise GitError("Commit message cannot be empty.")

    logger.info(f"Committing with message: '{commit_message}'")
    _run_git_command(["commit", f"--message={commit_message}"], cwd=repo_path, check=True)

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
    raw_out = proc.stdout.strip() or proc.stderr.strip() or f"Pushed successfully to {remote}/{target_branch}"
    return redact_sensitive_text(raw_out)


def git_pull(repo_path: Path, remote: str = "origin", branch: Optional[str] = None) -> Tuple[bool, str]:
    """
    Pull latest changes from remote repository safely before execution.
    """
    target_branch = branch or get_current_branch(repo_path)
    logger.info(f"Pulling latest from remote '{remote}' branch '{target_branch}'...")

    proc = _run_git_command(["pull", remote, target_branch], cwd=repo_path, check=False)
    if proc.returncode == 0:
        out = proc.stdout.strip() or f"Pulled successfully from {remote}/{target_branch}"
        return True, redact_sensitive_text(out)
    else:
        err = proc.stderr.strip() or proc.stdout.strip() or "git pull failed"
        sanitized_err = redact_sensitive_text(err)
        logger.warning(f"Git pull warning: {sanitized_err}")
        return False, sanitized_err


def git_fetch(repo_path: Path, remote: str = "origin", branch: Optional[str] = None) -> Tuple[bool, str]:
    """
    Fetch latest commits from remote without merging.
    """
    target_branch = branch or get_current_branch(repo_path)
    logger.info(f"Fetching from remote '{remote}' branch '{target_branch}'...")

    proc = _run_git_command(["fetch", remote, target_branch], cwd=repo_path, check=False)
    if proc.returncode == 0:
        out = proc.stdout.strip() or "Fetch successful"
        return True, redact_sensitive_text(out)
    else:
        err = proc.stderr.strip() or proc.stdout.strip() or "git fetch failed"
        return False, redact_sensitive_text(err)


def is_commit_on_remote(
    repo_path: Path,
    commit_hash: str,
    remote: str = "origin",
    branch: Optional[str] = None,
) -> bool:
    """
    Check if a specific commit hash has been published to the remote branch.
    """
    target_branch = branch or get_current_branch(repo_path)
    proc = _run_git_command(
        ["branch", "-r", "--contains", commit_hash],
        cwd=repo_path,
        check=False,
    )
    if proc.returncode == 0:
        expected = f"{remote}/{target_branch}"
        for line in proc.stdout.splitlines():
            if expected in line.strip():
                return True
    return False


def undo_last_commit(repo_path: Path) -> None:
    """
    Undo the last local commit (reset HEAD~1) safely if subsequent steps (like push) fail.
    """
    logger.info("Undoing last local commit to maintain clean repository state...")
    _run_git_command(["reset", "HEAD~1"], cwd=repo_path, check=False)


