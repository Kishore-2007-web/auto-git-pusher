"""
task_manager.py - Task loading, validation, batch queueing, and deterministic execution for Daily GitHub Agent.

Supports actions:
  - "append_text": Append specified text to the end of target file.
  - "add_comment": Add a comment (at top or bottom) with auto comment syntax formatting.
  - "replace_text": Replace exact target text with replacement text.

Supports task queues (e.g. 10 tasks) with batch execution and status tracking.
"""

from __future__ import annotations

import datetime
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("daily_github_agent")


class TaskError(Exception):
    """Raised when task configuration is invalid or execution fails."""
    pass


@dataclass
class TaskConfig:
    project: str
    file: str
    action: str
    commit_message: str
    id: Optional[Union[int, str]] = None
    status: str = "pending"  # "pending", "completed", "failed"
    completed_at: Optional[str] = None
    commit_hash: Optional[str] = None
    text: Optional[str] = None
    target_text: Optional[str] = None
    replacement_text: Optional[str] = None
    position: Optional[str] = "bottom"  # For add_comment: "top" or "bottom"


@dataclass
class TaskExecutionResult:
    already_completed: bool
    action: str
    file_path: Path
    message: str


SUPPORTED_ACTIONS = {"append_text", "add_comment", "replace_text"}


def parse_single_task_dict(data: Dict[str, Any], index: int = 1) -> TaskConfig:
    """
    Validate and parse a single dictionary into a TaskConfig object.
    """
    if not isinstance(data, dict):
        raise TaskError(f"Task #{index} must be a JSON object.")

    # Validate required base fields
    for field in ["project", "file", "action", "commit_message"]:
        if field not in data or not isinstance(data[field], str) or not data[field].strip():
            raise TaskError(
                f"Task #{index} missing or invalid required field: '{field}' (must be non-empty string)"
            )

    action = data["action"].strip().lower()
    if action not in SUPPORTED_ACTIONS:
        raise TaskError(
            f"Task #{index}: Unsupported action '{action}'. Supported actions in V1 are: {', '.join(sorted(SUPPORTED_ACTIONS))}"
        )

    # Validate action-specific parameters
    text = data.get("text")
    if text is not None and not isinstance(text, str):
        raise TaskError(f"Task #{index}: 'text' must be a string if provided.")

    target_text = data.get("target_text")
    replacement_text = data.get("replacement_text")
    position = data.get("position", "bottom")
    task_id = data.get("id", index)
    status = data.get("status", "pending").lower()
    completed_at = data.get("completed_at")
    commit_hash = data.get("commit_hash")

    if action == "append_text":
        if not text:
            raise TaskError(f"Task #{index} ('{action}') requires a non-empty 'text' property.")

    elif action == "add_comment":
        comment_val = data.get("comment", text)
        if not comment_val or not isinstance(comment_val, str):
            raise TaskError(f"Task #{index} ('{action}') requires a non-empty 'comment' or 'text' property.")
        text = comment_val
        if position not in ("top", "bottom"):
            raise TaskError(f"Task #{index} ('{action}') 'position' must be 'top' or 'bottom'.")

    elif action == "replace_text":
        if not target_text or not isinstance(target_text, str):
            raise TaskError(f"Task #{index} ('{action}') requires 'target_text' string property.")
        if replacement_text is None or not isinstance(replacement_text, str):
            raise TaskError(f"Task #{index} ('{action}') requires 'replacement_text' string property.")

    return TaskConfig(
        id=task_id,
        project=data["project"].strip(),
        file=data["file"].strip(),
        action=action,
        commit_message=data["commit_message"].strip(),
        status=status,
        completed_at=completed_at,
        commit_hash=commit_hash,
        text=text,
        target_text=target_text,
        replacement_text=replacement_text,
        position=position,
    )


def load_task_configs(task_path: Path) -> List[TaskConfig]:
    """
    Load task.json which can contain either:
    1. An object with a "tasks" array (e.g. {"tasks": [...]})
    2. A direct array of task objects ([{...}, {...}])
    3. A single task object ({...})
    """
    if not task_path.exists():
        raise TaskError(f"Task configuration file not found: '{task_path}'")

    try:
        with open(task_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise TaskError(f"Failed to parse task.json: {e}")
    except Exception as e:
        raise TaskError(f"Error reading task.json: {e}")

    task_configs: List[TaskConfig] = []

    if isinstance(data, dict):
        if "tasks" in data and isinstance(data["tasks"], list):
            if not data["tasks"]:
                raise TaskError("task.json 'tasks' list is empty.")
            for i, item in enumerate(data["tasks"], start=1):
                task_configs.append(parse_single_task_dict(item, index=i))
        else:
            # Single task object format
            task_configs.append(parse_single_task_dict(data, index=1))

    elif isinstance(data, list):
        if not data:
            raise TaskError("task.json list is empty.")
        for i, item in enumerate(data, start=1):
            task_configs.append(parse_single_task_dict(item, index=i))
    else:
        raise TaskError("task.json must contain a JSON object or array of tasks.")

    return task_configs


# Backward compatible helper
def load_task_config(task_path: Path) -> TaskConfig:
    tasks = load_task_configs(task_path)
    return tasks[0]


def get_pending_tasks(tasks: List[TaskConfig], limit: int = 1) -> List[TaskConfig]:
    """
    Return the next `limit` pending tasks from the list.
    """
    pending = [t for t in tasks if t.status != "completed"]
    return pending[:limit]


def mark_task_completed(task_path: Path, task_id: Optional[Union[int, str]], commit_hash: str) -> None:
    """
    Update status, completion timestamp, and commit hash of a task inside task.json.
    """
    if not task_path.exists():
        return

    try:
        with open(task_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        def update_item(item: Dict[str, Any]) -> bool:
            if item.get("id") == task_id or task_id is None:
                item["status"] = "completed"
                item["completed_at"] = now_iso
                item["commit_hash"] = commit_hash
                return True
            return False

        if isinstance(data, dict):
            if "tasks" in data and isinstance(data["tasks"], list):
                for item in data["tasks"]:
                    if isinstance(item, dict) and update_item(item):
                        break
            else:
                update_item(data)
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and update_item(item):
                    break

        with open(task_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Marked task {task_id} as completed in {task_path.name}")
    except Exception as e:
        logger.warning(f"Could not update task status in {task_path.name}: {e}")


def reset_all_tasks_to_pending(task_path: Path) -> List[TaskConfig]:
    """
    Reset all tasks in task.json back to 'pending' status for loop execution.
    """
    if not task_path.exists():
        return []

    try:
        with open(task_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        def reset_item(item: Dict[str, Any]) -> None:
            item["status"] = "pending"
            item.pop("completed_at", None)
            item.pop("commit_hash", None)

        if isinstance(data, dict):
            if "tasks" in data and isinstance(data["tasks"], list):
                for item in data["tasks"]:
                    if isinstance(item, dict):
                        reset_item(item)
            else:
                reset_item(data)
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    reset_item(item)

        with open(task_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Reset all tasks in {task_path.name} to pending for loop mode.")
        return load_task_configs(task_path)
    except Exception as e:
        logger.error(f"Failed to reset task queue in {task_path.name}: {e}")
        return load_task_configs(task_path)


def format_comment(text: str, file_suffix: str) -> str:
    """
    Format raw comment text according to file extension syntax if not already formatted.
    """
    raw = text.strip()
    ext = file_suffix.lower()

    if ext in [".md", ".html"]:
        if raw.startswith("<!--") and raw.endswith("-->"):
            return text
        return f"\n<!-- {raw} -->\n"
    elif ext in [".py", ".sh", ".txt"]:
        if raw.startswith("#"):
            return text
        return f"\n# {raw}\n"
    elif ext in [".js", ".css"]:
        if (raw.startswith("/*") and raw.endswith("*/")) or raw.startswith("//"):
            return text
        return f"\n/* {raw} */\n"
    else:
        return text


def read_file_content(file_path: Path) -> str:
    """
    Read target file text handling UTF-8, UTF-8-BOM, UTF-16, or fallback encodings.
    """
    encodings = ["utf-8-sig", "utf-8", "utf-16", "cp1252", "latin-1"]
    for enc in encodings:
        try:
            return file_path.read_text(encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise TaskError(f"Failed to decode text file '{file_path.name}' with supported text encodings.")


def execute_task(task: TaskConfig, target_file: Path, allow_duplicate: bool = False) -> TaskExecutionResult:
    """
    Deterministically execute the task action on the target file with idempotency checking.
    """
    try:
        content = read_file_content(target_file)
    except Exception as e:
        raise TaskError(f"Failed to read target file '{target_file.name}': {e}")

    # =========================================================================
    # Action: append_text
    # =========================================================================
    if task.action == "append_text":
        append_str = task.text or ""
        # Idempotency check: check if the trimmed append text already exists in file
        if not allow_duplicate and append_str.strip() in content:
            logger.info(f"Idempotency match on task {task.id}: Content to append already present.")
            return TaskExecutionResult(
                already_completed=True,
                action=task.action,
                file_path=target_file,
                message="Target text already present in file.",
            )

        if allow_duplicate and append_str.strip() in content:
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            append_str = f"{append_str.rstrip()} (run: {now_str})\n"

        # Ensure newline separator if target file doesn't end with newline
        prefix = "" if content.endswith("\n") or not content else "\n"
        new_content = content + prefix + append_str
        target_file.write_text(new_content, encoding="utf-8")
        return TaskExecutionResult(
            already_completed=False,
            action=task.action,
            file_path=target_file,
            message=f"Appended text to '{target_file.name}'",
        )

    # =========================================================================
    # Action: add_comment
    # =========================================================================
    elif task.action == "add_comment":
        raw_comment_text = (task.text or "").strip()
        comment_formatted = format_comment(task.text or "", target_file.suffix)

        # Idempotency check: if raw text or formatted comment already exists
        if not allow_duplicate and (raw_comment_text in content or comment_formatted.strip() in content):
            logger.info(f"Idempotency match on task {task.id}: Comment already present.")
            return TaskExecutionResult(
                already_completed=True,
                action=task.action,
                file_path=target_file,
                message="Comment already present in file.",
            )

        if allow_duplicate and (raw_comment_text in content or comment_formatted.strip() in content):
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            comment_formatted = format_comment(f"{raw_comment_text} ({now_str})", target_file.suffix)

        if task.position == "top":
            new_content = comment_formatted + content
        else:
            prefix = "" if content.endswith("\n") or not content else "\n"
            new_content = content + prefix + comment_formatted

        target_file.write_text(new_content, encoding="utf-8")
        return TaskExecutionResult(
            already_completed=False,
            action=task.action,
            file_path=target_file,
            message=f"Added comment to '{target_file.name}' at {task.position}",
        )

    # =========================================================================
    # Action: replace_text
    # =========================================================================
    elif task.action == "replace_text":
        target = task.target_text or ""
        replacement = task.replacement_text or ""

        # Idempotency check: if replacement is already in file and target is NOT in file
        if replacement in content and target not in content:
            logger.info(f"Idempotency match on task {task.id}: Replacement text already present.")
            return TaskExecutionResult(
                already_completed=True,
                action=task.action,
                file_path=target_file,
                message="Text replacement already applied.",
            )

        if target not in content:
            raise TaskError(
                f"Target text '{target[:50]}...' not found in '{target_file.name}' to replace."
            )

        new_content = content.replace(target, replacement, 1)
        target_file.write_text(new_content, encoding="utf-8")
        return TaskExecutionResult(
            already_completed=False,
            action=task.action,
            file_path=target_file,
            message=f"Replaced target text in '{target_file.name}'",
        )

    else:
        raise TaskError(f"Unhandled action: {task.action}")
