"""
agent.py - Main entry point and orchestrator for Daily GitHub Agent V1.

Workflow-
1. Loads configuration & task specifications (supports single task or task queues)
2. Selects the next batch of pending tasks (e.g. 2 per run based on settings.json)
3. For each task in batch:
   - Validates paths and security constraints (fail closed)
   - Verifies Git repository status
   - Modifies target file deterministically
   - Validates diff and change limits
   - Commits and pushes (if dry_run is false) or reverts diff preview (if dry_run is true)
   - Updates task status in task.json
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import confirmation_gui
import git_manager
import task_manager
import validator

logger = logging.getLogger("daily_github_agent")


def print_banner() -> None:
    banner = """
============================================================
                 DAILY GITHUB AGENT V1
        Deterministic & Safe Repository Automation
============================================================
"""
    print(banner)


def setup_logger(logs_dir: Path, debug: bool = False) -> Path:
    """
    Configure file and console logging with daily rotation.
    """
    logs_dir.mkdir(parents=True, exist_ok=True)
    today_str = datetime.date.today().isoformat()
    log_file = logs_dir / f"{today_str}.log"

    log_level = logging.DEBUG if debug else logging.INFO
    logger.setLevel(log_level)

    # Avoid duplicate handlers if re-initialized
    if not logger.handlers:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(log_level)
        logger.addHandler(file_handler)

    return log_file


def load_settings(settings_path: Path) -> Dict[str, Any]:
    """
    Load settings.json file safely.
    """
    if not settings_path.exists():
        raise validator.ValidationError(f"Configuration file not found: '{settings_path}'")

    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise validator.ValidationError(f"Failed to parse settings.json: {e}")
    except Exception as e:
        raise validator.ValidationError(f"Error reading settings.json: {e}")

    validator.validate_settings(data)
    return data


def run_agent(
    base_dir: Path,
    config_dir: Path,
    debug: bool = False,
    use_gui: bool = False,
) -> int:
    """
    Main execution workflow for Daily GitHub Agent.
    Returns integer exit code (0 for success, non-zero for error).
    """
    print_banner()

    logs_dir = base_dir / "logs"
    log_file = setup_logger(logs_dir, debug)
    logger.info("=== Daily GitHub Agent V1 Started ===")

    # GUI Step 1: Confirmation Popup
    if use_gui:
        confirmed = confirmation_gui.show_confirmation()
        if not confirmed:
            print("\n[i] Execution cancelled by user.")
            logger.info("Execution cancelled by user at confirmation dialog.")
            return 0

    try:
        # 1. Load Settings
        settings_path = config_dir / "settings.json"
        print(f"[*] Loading settings from: {settings_path.name}")
        settings = load_settings(settings_path)

        dry_run = settings["dry_run"]
        tasks_per_run = settings.get("tasks_per_run", 1)
        loop_tasks = settings.get("loop_tasks", False)
        workspace_name = settings["workspace_directory"]
        require_clean = settings["require_clean_git_before_start"]
        allowed_extensions = settings["allowed_extensions"]
        max_changed_files = settings["max_changed_files"]

        # Display Mode
        if dry_run:
            print("\n" + "=" * 60)
            print(" [MODE] DRY RUN MODE ENABLED")
            print(" No Git commit or push will be performed.")
            print("=" * 60 + "\n")
        else:
            print("\n" + "=" * 60)
            print(" [MODE] LIVE EXECUTION MODE (Commit & Push Enabled)")
            if loop_tasks:
                print(" [LOOP MODE] Continuous loop enabled ('loop_tasks': true)")
            print("=" * 60 + "\n")

        # 2. Check Git installation
        git_ok, git_ver = git_manager.check_git_installed()
        if not git_ok:
            raise git_manager.GitError(f"Git verification failed: {git_ver}")
        logger.info(f"Git environment: {git_ver}")

        # 3. Load Task Queue
        task_path = config_dir / "task.json"
        print(f"[*] Loading task queue from: {task_path.name}")
        all_tasks = task_manager.load_task_configs(task_path)
        pending_tasks = [t for t in all_tasks if t.status != "completed"]
        completed_tasks = [t for t in all_tasks if t.status == "completed"]

        print(f"[*] Task Queue Status: {len(all_tasks)} total | {len(completed_tasks)} completed | {len(pending_tasks)} pending")

        if not pending_tasks:
            if loop_tasks:
                print("\n" + "=" * 60)
                print(" [LOOP MODE] All tasks in queue were previously completed.")
                print(" Automatically resetting task queue to 'pending' for a new loop cycle!")
                print("=" * 60 + "\n")
                logger.info("Loop mode active: Resetting all tasks in queue to pending.")
                all_tasks = task_manager.reset_all_tasks_to_pending(task_path)
                pending_tasks = [t for t in all_tasks if t.status != "completed"]
            else:
                print("\n" + "=" * 60)
                print(" [i] ALL TASKS COMPLETED!")
                print(f" All {len(all_tasks)} task(s) in the queue have been successfully finished.")
                print(" To repeat tasks in a continuous loop, set 'loop_tasks': true in config/settings.json")
                print("=" * 60 + "\n")
                logger.info("All tasks in queue are completed.")
                if use_gui:
                    confirmation_gui.show_success()
                return 0

        # Select batch for this run
        batch = pending_tasks[:tasks_per_run]
        print(f"[*] Executing next batch of {len(batch)} task(s) (configured tasks_per_run={tasks_per_run}):\n")
        for t in batch:
            print(f"    - Task #{t.id}: [{t.action}] on {t.project}/{t.file} -> '{t.commit_message}'")
        print()

        executed_count = 0

        # Execute each task in batch
        for idx, task in enumerate(batch, start=1):
            task_header = f"--- [Task #{task.id} ({idx}/{len(batch)} in this batch)] ---"
            print("-" * 60)
            print(task_header)
            print("-" * 60)

            backup_file: Optional[Path] = None
            target_file: Optional[Path] = None

            try:
                # Path and Security Validation
                print(f"[*] Validating paths for project '{task.project}'...")
                project_dir, target_file = validator.validate_paths(
                    base_dir=base_dir,
                    workspace_name=workspace_name,
                    project_name=task.project,
                    file_rel_path=task.file,
                    allowed_extensions=allowed_extensions,
                )

                # Check Git Repository
                is_git, git_msg = git_manager.check_git_repository(project_dir)
                if not is_git:
                    raise git_manager.GitError(f"Directory is not a valid Git repository: {git_msg}")

                # Check Clean Git Status
                if require_clean:
                    is_clean, dirty_files = git_manager.is_git_clean(project_dir)
                    if not is_clean:
                        print("\n[!] SAFETY ERROR:")
                        print("Repository contains existing uncommitted changes:")
                        for df in dirty_files:
                            print(f"    - {df}")
                        print("The agent will not modify this repository to prevent data loss.")
                        logger.warning(f"Repository dirty for task {task.id}. Files: {dirty_files}")
                        if use_gui:
                            confirmation_gui.show_failure()
                        return 1

                # Create Backup Before Modification
                backup_file = validator.create_backup(target_file)

                # Execute Task Action
                print(f"[*] Executing action '{task.action}' on '{target_file.name}'...")
                result = task_manager.execute_task(task, target_file, allow_duplicate=loop_tasks)

                # Handle Idempotency
                if result.already_completed:
                    print(f" [i] Task #{task.id} already completed: {result.message}")
                    logger.info(f"Task #{task.id} already completed: {result.message}")
                    validator.cleanup_backup(backup_file)
                    if not dry_run:
                        task_manager.mark_task_completed(task_path, task.id, commit_hash="ALREADY_APPLIED")
                    executed_count += 1
                    continue

                # Validate Git Changes
                print("[*] Validating modifications...")
                changed_files = git_manager.get_changed_files(project_dir)
                validator.validate_git_changes(
                    changed_files=changed_files,
                    expected_rel_file=task.file,
                    max_changed_files=max_changed_files,
                )

                # Inspect Git Diff
                diff_text = git_manager.get_diff(project_dir, task.file)
                print("\nGIT DIFF PREVIEW:")
                print("~" * 40)
                print(diff_text if diff_text else "(No textual diff)")
                print("~" * 40 + "\n")
                logger.info(f"Task #{task.id} diff:\n{diff_text}")

                if dry_run:
                    # Rollback changes in dry-run
                    validator.restore_backup(target_file, backup_file)
                    validator.cleanup_backup(backup_file)
                    print(f" [OK] Dry run passed for Task #{task.id} (reverted to keep workspace clean)")
                    executed_count += 1
                else:
                    # Live commit and push
                    print(f"[*] Staging '{task.file}'...")
                    git_manager.git_add(project_dir, task.file)

                    print(f"[*] Committing: '{task.commit_message}'...")
                    commit_hash = git_manager.git_commit(project_dir, task.commit_message)
                    logger.info(f"Task #{task.id} committed: {commit_hash}")

                    print("[*] Pushing to remote repository...")
                    push_out = git_manager.git_push(project_dir)
                    push_status = f"Success: {push_out}"
                    logger.info(f"Task #{task.id} push result: {push_status}")

                    validator.cleanup_backup(backup_file)

                    # Update status in task.json
                    task_manager.mark_task_completed(task_path, task.id, commit_hash=commit_hash)

                    print(f" [OK] SUCCESS for Task #{task.id}: Commit {commit_hash} | Remote: {push_status}")
                    executed_count += 1

            except (validator.ValidationError, task_manager.TaskError, git_manager.GitError) as e:
                print(f"\n[ERROR on Task #{task.id}] {e}")
                logger.error(f"Task #{task.id} failed: {e}")
                if target_file and backup_file:
                    validator.restore_backup(target_file, backup_file)
                    validator.cleanup_backup(backup_file)
                if use_gui:
                    confirmation_gui.show_failure()
                return 1

        # Summary of the run
        remaining_count = len(pending_tasks) - executed_count
        print("\n" + "=" * 60)
        if dry_run:
            print(" [OK] BATCH DRY RUN COMPLETED SUCCESSFULLY")
            print(f" - Tested {executed_count} task(s)")
            print(f" - {remaining_count} task(s) remaining in queue")
            print(" - Set 'dry_run': false in config/settings.json to apply live")
            print("=" * 60 + "\n")
            if use_gui:
                confirmation_gui.show_dry_run_result()
            return 0
        else:
            print(" [OK] BATCH EXECUTION FINISHED SUCCESSFULLY")
            print(f" - Completed and committed {executed_count} task(s)")
            print(f" - {remaining_count} task(s) remaining in queue")
            if remaining_count > 0:
                print(" - Double-click run.bat again to execute the next batch!")
            else:
                print(" - All tasks in queue have now been executed!")
            print("=" * 60 + "\n")
            if use_gui:
                confirmation_gui.show_success()
            return 0

    except (validator.ValidationError, task_manager.TaskError, git_manager.GitError) as e:
        print(f"\n[ERROR] {e}")
        logger.error(f"Execution failed: {e}")
        if use_gui:
            confirmation_gui.show_failure()
        return 1

    except Exception as e:
        print(f"\n[UNEXPECTED ERROR] An error occurred: {e}")
        logger.error(f"Unexpected exception: {e}")
        if debug:
            import traceback
            traceback.print_exc()
        else:
            print("Run with --debug for detailed traceback.")
        if use_gui:
            confirmation_gui.show_failure()
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily GitHub Agent V1")
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help="Path to configuration directory (default: ./config)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose debug logging and stack traces",
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="Run in CLI headless mode without GUI confirmation or result popups",
    )

    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    config_directory = (args.config_dir or (script_dir / "config")).resolve()

    exit_code = run_agent(
        base_dir=script_dir,
        config_dir=config_directory,
        debug=args.debug,
        use_gui=not args.no_gui,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
