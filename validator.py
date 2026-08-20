"""
validator.py - Security and validation module for Daily GitHub Agent.

Enforces strict path safety, forbidden file blacklists, extension whitelists,
backup/rollback mechanisms, and change scope limits.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("daily_github_agent")


class ValidationError(Exception):
    """Raised when any security or configuration validation check fails."""
    pass


# Blacklist patterns for sensitive files and folders that must NEVER be modified
FORBIDDEN_PATTERNS = [
    ".env",
    ".git",
    "credential",
    "id_rsa",
    "id_ed25519",
    "id_dsa",
    "id_ecdsa",
    ".pem",
    ".key",
    "secret",
    "token",
    "password",
    ".htpasswd",
    "auth",
]


def is_path_traversal(path_str: str) -> bool:
    """
    Check if a path string contains traversal sequences or suspicious characters.
    """
    normalized = path_str.replace("\\", "/")
    parts = normalized.split("/")
    return ".." in parts or "." in parts and len(parts) == 1


def is_forbidden_target(target_path: Path) -> Tuple[bool, str]:
    """
    Check if the target path matches any blacklisted sensitive patterns.
    """
    path_parts_lower = [part.lower() for part in target_path.parts]
    filename_lower = target_path.name.lower()

    # Check parts and filename
    for part in path_parts_lower:
        if part == ".git" or part.startswith(".git"):
            return True, f"Modifying .git directory or files is strictly forbidden: '{part}'"

    for pattern in FORBIDDEN_PATTERNS:
        if pattern in filename_lower:
            return True, f"Target file matches forbidden sensitive pattern '{pattern}': '{target_path.name}'"

    return False, ""


def validate_settings(settings: Dict[str, Any]) -> None:
    """
    Validate the structure and types of the settings dictionary.
    """
    required_keys = ["workspace_directory", "dry_run", "require_clean_git_before_start", "allowed_extensions", "max_changed_files"]
    for key in required_keys:
        if key not in settings:
            raise ValidationError(f"Missing required key in settings.json: '{key}'")

    if not isinstance(settings["workspace_directory"], str) or not settings["workspace_directory"].strip():
        raise ValidationError("settings.json 'workspace_directory' must be a non-empty string.")

    if not isinstance(settings["dry_run"], bool):
        raise ValidationError("settings.json 'dry_run' must be a boolean (true or false).")

    if "tasks_per_run" in settings:
        if not isinstance(settings["tasks_per_run"], int) or settings["tasks_per_run"] < 1:
            raise ValidationError("settings.json 'tasks_per_run' must be an integer >= 1.")

    if not isinstance(settings["require_clean_git_before_start"], bool):
        raise ValidationError("settings.json 'require_clean_git_before_start' must be a boolean (true or false).")

    if not isinstance(settings["allowed_extensions"], list) or not settings["allowed_extensions"]:
        raise ValidationError("settings.json 'allowed_extensions' must be a non-empty list of file extensions.")

    if not isinstance(settings["max_changed_files"], int) or settings["max_changed_files"] < 1:
        raise ValidationError("settings.json 'max_changed_files' must be an integer >= 1.")

    if "loop_tasks" in settings:
        if not isinstance(settings["loop_tasks"], bool):
            raise ValidationError("settings.json 'loop_tasks' must be a boolean (true or false).")


def validate_paths(
    base_dir: Path,
    workspace_name: str,
    project_name: str,
    file_rel_path: str,
    allowed_extensions: List[str],
) -> Tuple[Path, Path]:
    """
    Strictly validate project and file paths against directory traversal and boundaries.

    Returns:
        Tuple[Path, Path]: (resolved_project_dir, resolved_target_file)
    """
    # Reject explicit traversal tokens
    if is_path_traversal(workspace_name):
        raise ValidationError(f"Invalid workspace path traversal detected: '{workspace_name}'")

    if is_path_traversal(project_name):
        raise ValidationError(f"Path traversal sequence detected in project name: '{project_name}'")

    if is_path_traversal(file_rel_path):
        raise ValidationError(f"Path traversal sequence detected in file path: '{file_rel_path}'")

    # Reject absolute paths in project or file relative parameters
    if os.path.isabs(project_name):
        raise ValidationError(f"Absolute path in project name is not allowed: '{project_name}'")

    if os.path.isabs(file_rel_path):
        raise ValidationError(f"Absolute path in file parameter is not allowed: '{file_rel_path}'")

    workspace_dir = (base_dir / workspace_name).resolve()
    if not workspace_dir.exists() or not workspace_dir.is_dir():
        raise ValidationError(f"Workspace directory does not exist: '{workspace_dir}'")

    project_dir = (workspace_dir / project_name).resolve()

    # Ensure project_dir is strictly inside workspace_dir
    try:
        project_dir.relative_to(workspace_dir)
    except ValueError:
        raise ValidationError(f"Project directory '{project_dir}' is outside workspace '{workspace_dir}'.")

    if project_dir == workspace_dir:
        raise ValidationError("Target project cannot be the workspace directory itself.")

    if not project_dir.exists() or not project_dir.is_dir():
        raise ValidationError(f"Target project directory not found: '{project_dir}'")

    target_file = (project_dir / file_rel_path).resolve()

    # Ensure target_file is strictly inside project_dir
    try:
        target_file.relative_to(project_dir)
    except ValueError:
        raise ValidationError(f"Target file '{target_file}' is outside project directory '{project_dir}'.")

    if not target_file.exists() or not target_file.is_file():
        raise ValidationError(f"Target file does not exist or is not a regular file: '{target_file}'")

    # Forbidden file checks
    forbidden, reason = is_forbidden_target(target_file)
    if forbidden:
        raise ValidationError(f"Security check failed: {reason}")

    # Extension check
    suffix = target_file.suffix.lower()
    normalized_allowed = [ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in allowed_extensions]
    if suffix not in normalized_allowed:
        raise ValidationError(
            f"File extension '{suffix}' for '{target_file.name}' is not in allowed_extensions: {allowed_extensions}"
        )

    return project_dir, target_file


def create_backup(target_file: Path) -> Path:
    """
    Create a backup of the target file prior to any modifications.
    """
    backup_file = target_file.with_name(f"{target_file.name}.agent_bak")
    try:
        shutil.copy2(target_file, backup_file)
        logger.info(f"Created temporary backup: {backup_file}")
        return backup_file
    except Exception as e:
        raise ValidationError(f"Failed to create backup of '{target_file}': {e}")


def restore_backup(target_file: Path, backup_file: Optional[Path]) -> bool:
    """
    Restore the target file from its backup copy.
    """
    if backup_file and backup_file.exists():
        try:
            shutil.copy2(backup_file, target_file)
            logger.info(f"Restored original file from backup: {target_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to restore backup '{backup_file}' to '{target_file}': {e}")
            return False
    return False


def cleanup_backup(backup_file: Optional[Path]) -> None:
    """
    Remove temporary backup file after successful completion.
    """
    if backup_file and backup_file.exists():
        try:
            backup_file.unlink()
            logger.debug(f"Removed temporary backup: {backup_file}")
        except Exception as e:
            logger.warning(f"Could not remove temporary backup '{backup_file}': {e}")


def validate_git_changes(
    changed_files: List[str],
    expected_rel_file: str,
    max_changed_files: int = 1,
) -> None:
    """
    Ensure only the single expected target file was modified.
    """
    # Normalize paths for comparison (forward slashes)
    norm_expected = expected_rel_file.replace("\\", "/").lstrip("./")
    norm_changed = [f.replace("\\", "/").lstrip("./") for f in changed_files]

    # Filter out backup files if any showed up in untracked
    norm_changed = [f for f in norm_changed if not f.endswith(".agent_bak")]

    if len(norm_changed) == 0:
        raise ValidationError("No changes were detected in the repository.")

    if len(norm_changed) > max_changed_files:
        raise ValidationError(
            f"Too many changed files ({len(norm_changed)} > max {max_changed_files}): {norm_changed}"
        )

    for changed in norm_changed:
        if changed != norm_expected:
            raise ValidationError(
                f"Unexpected file changed: '{changed}'. Only '{norm_expected}' was permitted."
            )
