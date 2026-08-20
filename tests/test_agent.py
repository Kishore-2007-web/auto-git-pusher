"""
test_agent.py - Comprehensive unit and integration tests for Daily GitHub Agent V1.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import agent
import confirmation_gui
import git_manager
import task_manager
import validator


class TestValidator(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agent_test_val_"))
        self.workspace_dir = self.temp_dir / "workspace"
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.project_dir = self.workspace_dir / "my_project"
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.readme_file = self.project_dir / "README.md"
        self.readme_file.write_text("# Test Project\n", encoding="utf-8")

        self.allowed_exts = [".md", ".txt", ".py", ".js", ".html", ".css"]

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_settings_validation_valid(self) -> None:
        valid_settings = {
            "workspace_directory": "workspace",
            "dry_run": True,
            "require_clean_git_before_start": True,
            "allowed_extensions": [".md", ".py"],
            "max_changed_files": 1,
        }
        # Should not raise
        validator.validate_settings(valid_settings)

    def test_settings_validation_invalid_missing_key(self) -> None:
        invalid_settings = {
            "workspace_directory": "workspace",
            "dry_run": True,
        }
        with self.assertRaises(validator.ValidationError):
            validator.validate_settings(invalid_settings)

    def test_path_validation_success(self) -> None:
        proj, target = validator.validate_paths(
            base_dir=self.temp_dir,
            workspace_name="workspace",
            project_name="my_project",
            file_rel_path="README.md",
            allowed_extensions=self.allowed_exts,
        )
        self.assertEqual(proj, self.project_dir)
        self.assertEqual(target, self.readme_file)

    def test_path_traversal_rejection(self) -> None:
        with self.assertRaises(validator.ValidationError):
            validator.validate_paths(
                base_dir=self.temp_dir,
                workspace_name="workspace",
                project_name="../other_folder",
                file_rel_path="README.md",
                allowed_extensions=self.allowed_exts,
            )

        with self.assertRaises(validator.ValidationError):
            validator.validate_paths(
                base_dir=self.temp_dir,
                workspace_name="workspace",
                project_name="my_project",
                file_rel_path="../../windows/system32/cmd.exe",
                allowed_extensions=self.allowed_exts,
            )

    def test_forbidden_files_rejection(self) -> None:
        env_file = self.project_dir / ".env"
        env_file.write_text("SECRET=12345", encoding="utf-8")
        with self.assertRaises(validator.ValidationError):
            validator.validate_paths(
                base_dir=self.temp_dir,
                workspace_name="workspace",
                project_name="my_project",
                file_rel_path=".env",
                allowed_extensions=self.allowed_exts + [".env"],
            )

        key_file = self.project_dir / "id_rsa"
        key_file.write_text("KEY", encoding="utf-8")
        with self.assertRaises(validator.ValidationError):
            validator.validate_paths(
                base_dir=self.temp_dir,
                workspace_name="workspace",
                project_name="my_project",
                file_rel_path="id_rsa",
                allowed_extensions=self.allowed_exts + [""],
            )

    def test_disallowed_extension_rejection(self) -> None:
        sh_file = self.project_dir / "script.sh"
        sh_file.write_text("echo hi", encoding="utf-8")
        with self.assertRaises(validator.ValidationError):
            validator.validate_paths(
                base_dir=self.temp_dir,
                workspace_name="workspace",
                project_name="my_project",
                file_rel_path="script.sh",
                allowed_extensions=[".md", ".py"],
            )

    def test_backup_and_restore(self) -> None:
        original_content = "Original Content"
        self.readme_file.write_text(original_content, encoding="utf-8")

        bak = validator.create_backup(self.readme_file)
        self.assertTrue(bak.exists())

        # Modify original
        self.readme_file.write_text("Modified Content", encoding="utf-8")

        # Restore
        validator.restore_backup(self.readme_file, bak)
        self.assertEqual(self.readme_file.read_text(encoding="utf-8"), original_content)

        # Cleanup
        validator.cleanup_backup(bak)
        self.assertFalse(bak.exists())


class TestTaskManager(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agent_test_tm_"))
        self.test_file = self.temp_dir / "test.py"
        self.test_file.write_text("print('hello world')\n", encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_append_text_and_idempotency(self) -> None:
        task = task_manager.TaskConfig(
            project="test_proj",
            file="test.py",
            action="append_text",
            text="# appended line\n",
            commit_message="test append",
        )
        res1 = task_manager.execute_task(task, self.test_file)
        self.assertFalse(res1.already_completed)
        self.assertIn("# appended line", self.test_file.read_text(encoding="utf-8"))

        # Duplicate execution
        res2 = task_manager.execute_task(task, self.test_file)
        self.assertTrue(res2.already_completed)

    def test_add_comment_and_idempotency(self) -> None:
        task = task_manager.TaskConfig(
            project="test_proj",
            file="test.py",
            action="add_comment",
            text="Daily Maintenance Comment",
            position="top",
            commit_message="test comment",
        )
        res1 = task_manager.execute_task(task, self.test_file)
        self.assertFalse(res1.already_completed)
        content = self.test_file.read_text(encoding="utf-8")
        self.assertIn("# Daily Maintenance Comment", content)

        # Duplicate execution
        res2 = task_manager.execute_task(task, self.test_file)
        self.assertTrue(res2.already_completed)

    def test_replace_text_and_idempotency(self) -> None:
        task = task_manager.TaskConfig(
            project="test_proj",
            file="test.py",
            action="replace_text",
            target_text="print('hello world')",
            replacement_text="print('hello daily agent')",
            commit_message="test replace",
        )
        res1 = task_manager.execute_task(task, self.test_file)
        self.assertFalse(res1.already_completed)
        content = self.test_file.read_text(encoding="utf-8")
        self.assertIn("print('hello daily agent')", content)

        # Duplicate execution
        res2 = task_manager.execute_task(task, self.test_file)
        self.assertTrue(res2.already_completed)


class TestGitManagerAndAgentIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agent_test_git_"))
        self.workspace_dir = self.temp_dir / "workspace"
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir = self.temp_dir / "config"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir = self.temp_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        self.repo_dir = self.workspace_dir / "TEST_REPO"
        self.repo_dir.mkdir(parents=True, exist_ok=True)

        # Initialize real git repository
        subprocess.run(["git", "init"], cwd=str(self.repo_dir), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Agent Tester"], cwd=str(self.repo_dir), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "agent@test.local"], cwd=str(self.repo_dir), capture_output=True, check=True)

        self.readme = self.repo_dir / "README.md"
        self.readme.write_text("# Initial Repo\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=str(self.repo_dir), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(self.repo_dir), capture_output=True, check=True)

        # Initialize bare remote repo to serve as local origin
        self.remote_dir = self.temp_dir / "REMOTE_ORIGIN.git"
        subprocess.run(["git", "init", "--bare", str(self.remote_dir)], capture_output=True, check=True)
        subprocess.run(["git", "remote", "add", "origin", str(self.remote_dir)], cwd=str(self.repo_dir), capture_output=True, check=True)
        branch_proc = subprocess.run(["git", "branch", "--show-current"], cwd=str(self.repo_dir), capture_output=True, text=True, check=True)
        branch = branch_proc.stdout.strip() or "master"
        subprocess.run(["git", "push", "-u", "origin", branch], cwd=str(self.repo_dir), capture_output=True, check=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_git_manager_functions(self) -> None:
        is_git, _ = git_manager.check_git_repository(self.repo_dir)
        self.assertTrue(is_git)

        is_clean, dirty_files = git_manager.is_git_clean(self.repo_dir)
        self.assertTrue(is_clean)
        self.assertEqual(len(dirty_files), 0)

        # Modify file
        self.readme.write_text("# Initial Repo\nNew line\n", encoding="utf-8")
        is_clean2, dirty_files2 = git_manager.is_git_clean(self.repo_dir)
        self.assertFalse(is_clean2)
        self.assertIn("README.md", dirty_files2)

        diff = git_manager.get_diff(self.repo_dir, "README.md")
        self.assertIn("+New line", diff)

        # Stage and commit
        git_manager.git_add(self.repo_dir, "README.md")
        commit_hash = git_manager.git_commit(self.repo_dir, "test commit via manager")
        self.assertTrue(len(commit_hash) >= 4)

    def test_agent_dry_run_execution(self) -> None:
        # Create settings.json with dry_run = True
        settings = {
            "workspace_directory": "workspace",
            "dry_run": True,
            "require_clean_git_before_start": True,
            "allowed_extensions": [".md"],
            "max_changed_files": 1,
        }
        (self.config_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

        # Create task.json
        task = {
            "project": "TEST_REPO",
            "file": "README.md",
            "action": "append_text",
            "text": "<!-- Daily GitHub Agent Test -->\n",
            "commit_message": "docs: dry run test",
        }
        (self.config_dir / "task.json").write_text(json.dumps(task), encoding="utf-8")

        # Run agent
        exit_code = agent.run_agent(base_dir=self.temp_dir, config_dir=self.config_dir, debug=True)
        self.assertEqual(exit_code, 0)

        # Verify no commit was made and file was restored
        is_clean, _ = git_manager.is_git_clean(self.repo_dir)
        self.assertTrue(is_clean)
        self.assertEqual(self.readme.read_text(encoding="utf-8"), "# Initial Repo\n")

    def test_agent_dirty_repo_protection(self) -> None:
        # Make repo dirty
        (self.repo_dir / "uncommitted.txt").write_text("dirty content", encoding="utf-8")

        settings = {
            "workspace_directory": "workspace",
            "dry_run": True,
            "require_clean_git_before_start": True,
            "allowed_extensions": [".md", ".txt"],
            "max_changed_files": 1,
        }
        (self.config_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

        task = {
            "project": "TEST_REPO",
            "file": "README.md",
            "action": "append_text",
            "text": "<!-- Test -->\n",
            "commit_message": "docs: test",
        }
        (self.config_dir / "task.json").write_text(json.dumps(task), encoding="utf-8")

        exit_code = agent.run_agent(base_dir=self.temp_dir, config_dir=self.config_dir, debug=True)
        self.assertEqual(exit_code, 1)

    def test_agent_live_commit_execution(self) -> None:
        # Create settings.json with dry_run = False
        settings = {
            "workspace_directory": "workspace",
            "dry_run": False,
            "require_clean_git_before_start": True,
            "allowed_extensions": [".md"],
            "max_changed_files": 1,
        }
        (self.config_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

        task = {
            "project": "TEST_REPO",
            "file": "README.md",
            "action": "append_text",
            "text": "<!-- Live Commit Test -->\n",
            "commit_message": "docs: live agent test commit",
        }
        (self.config_dir / "task.json").write_text(json.dumps(task), encoding="utf-8")

        # Run agent in live mode
        exit_code = agent.run_agent(base_dir=self.temp_dir, config_dir=self.config_dir, debug=True)
        self.assertEqual(exit_code, 0)

        # Verify commit exists in git log
        log_res = subprocess.run(["git", "log", "-n", "1", "--oneline"], cwd=str(self.repo_dir), capture_output=True, text=True, check=True)
        self.assertIn("docs: live agent test commit", log_res.stdout)
        self.assertIn("<!-- Live Commit Test -->", self.readme.read_text(encoding="utf-8"))

    def test_agent_missing_project(self) -> None:
        settings = {
            "workspace_directory": "workspace",
            "dry_run": True,
            "require_clean_git_before_start": True,
            "allowed_extensions": [".md"],
            "max_changed_files": 1,
        }
        (self.config_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

        task = {
            "project": "NON_EXISTENT_PROJECT",
            "file": "README.md",
            "action": "append_text",
            "text": "test",
            "commit_message": "test",
        }
        (self.config_dir / "task.json").write_text(json.dumps(task), encoding="utf-8")

        exit_code = agent.run_agent(base_dir=self.temp_dir, config_dir=self.config_dir, debug=False)
        self.assertEqual(exit_code, 1)

    def test_agent_project_not_git_repo(self) -> None:
        non_git_project = self.workspace_dir / "NON_GIT_PROJ"
        non_git_project.mkdir(parents=True, exist_ok=True)
        (non_git_project / "README.md").write_text("Hello", encoding="utf-8")

        settings = {
            "workspace_directory": "workspace",
            "dry_run": True,
            "require_clean_git_before_start": True,
            "allowed_extensions": [".md"],
            "max_changed_files": 1,
        }
        (self.config_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

        task = {
            "project": "NON_GIT_PROJ",
            "file": "README.md",
            "action": "append_text",
            "text": "test",
            "commit_message": "test",
        }
        (self.config_dir / "task.json").write_text(json.dumps(task), encoding="utf-8")

        exit_code = agent.run_agent(base_dir=self.temp_dir, config_dir=self.config_dir, debug=False)
        self.assertEqual(exit_code, 1)

    def test_agent_invalid_json(self) -> None:
        (self.config_dir / "settings.json").write_text("INVALID JSON {{{", encoding="utf-8")
        exit_code = agent.run_agent(base_dir=self.temp_dir, config_dir=self.config_dir, debug=False)
        self.assertEqual(exit_code, 1)

    def test_comment_formatting_syntaxes(self) -> None:
        self.assertEqual(task_manager.format_comment("hello", ".py").strip(), "# hello")
        self.assertEqual(task_manager.format_comment("hello", ".js").strip(), "/* hello */")
        self.assertEqual(task_manager.format_comment("hello", ".css").strip(), "/* hello */")
        self.assertEqual(task_manager.format_comment("hello", ".md").strip(), "<!-- hello -->")
        self.assertEqual(task_manager.format_comment("hello", ".html").strip(), "<!-- hello -->")

    def test_replace_text_missing_target(self) -> None:
        test_file = self.temp_dir / "sample.txt"
        test_file.write_text("Some text here", encoding="utf-8")
        task = task_manager.TaskConfig(
            project="test",
            file="sample.txt",
            action="replace_text",
            target_text="NonExistentPattern",
            replacement_text="NewPattern",
            commit_message="test",
        )
        with self.assertRaises(task_manager.TaskError):
            task_manager.execute_task(task, test_file)

    def test_validate_git_changes_violations(self) -> None:
        # Multiple files changed
        with self.assertRaises(validator.ValidationError):
            validator.validate_git_changes(["README.md", "other.py"], "README.md", max_changed_files=1)

        # Unrelated file changed
        with self.assertRaises(validator.ValidationError):
            validator.validate_git_changes(["unrelated.py"], "README.md", max_changed_files=1)

    def test_multi_task_batch_execution(self) -> None:
        # 4 tasks in queue, tasks_per_run = 2
        settings = {
            "workspace_directory": "workspace",
            "dry_run": False,
            "tasks_per_run": 2,
            "require_clean_git_before_start": True,
            "allowed_extensions": [".md"],
            "max_changed_files": 1,
        }
        (self.config_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

        task_data = {
            "tasks": [
                {
                    "id": 1,
                    "project": "TEST_REPO",
                    "file": "README.md",
                    "action": "append_text",
                    "text": "\nLine 1\n",
                    "commit_message": "docs: commit 1",
                    "status": "pending",
                },
                {
                    "id": 2,
                    "project": "TEST_REPO",
                    "file": "README.md",
                    "action": "append_text",
                    "text": "\nLine 2\n",
                    "commit_message": "docs: commit 2",
                    "status": "pending",
                },
                {
                    "id": 3,
                    "project": "TEST_REPO",
                    "file": "README.md",
                    "action": "append_text",
                    "text": "\nLine 3\n",
                    "commit_message": "docs: commit 3",
                    "status": "pending",
                },
                {
                    "id": 4,
                    "project": "TEST_REPO",
                    "file": "README.md",
                    "action": "append_text",
                    "text": "\nLine 4\n",
                    "commit_message": "docs: commit 4",
                    "status": "pending",
                },
            ]
        }
        (self.config_dir / "task.json").write_text(json.dumps(task_data), encoding="utf-8")

        # First run: should execute Task 1 and Task 2
        exit1 = agent.run_agent(base_dir=self.temp_dir, config_dir=self.config_dir, debug=True)
        self.assertEqual(exit1, 0)

        tasks_after_run1 = task_manager.load_task_configs(self.config_dir / "task.json")
        self.assertEqual(tasks_after_run1[0].status, "completed")
        self.assertEqual(tasks_after_run1[1].status, "completed")
        self.assertEqual(tasks_after_run1[2].status, "pending")
        self.assertEqual(tasks_after_run1[3].status, "pending")

        # Second run: should execute Task 3 and Task 4
        exit2 = agent.run_agent(base_dir=self.temp_dir, config_dir=self.config_dir, debug=True)
        self.assertEqual(exit2, 0)

        tasks_after_run2 = task_manager.load_task_configs(self.config_dir / "task.json")
        self.assertTrue(all(t.status == "completed" for t in tasks_after_run2))

        # Third run: all completed
        exit3 = agent.run_agent(base_dir=self.temp_dir, config_dir=self.config_dir, debug=True)
        self.assertEqual(exit3, 0)

        # Check git log has 4 new commits + initial commit = 5 commits
        log_res = subprocess.run(["git", "log", "--oneline"], cwd=str(self.repo_dir), capture_output=True, text=True, check=True)
        self.assertIn("docs: commit 1", log_res.stdout)
        self.assertIn("docs: commit 2", log_res.stdout)
        self.assertIn("docs: commit 3", log_res.stdout)
        self.assertIn("docs: commit 4", log_res.stdout)

    def test_agent_loop_tasks_execution(self) -> None:
        # 2 tasks in queue, tasks_per_run = 1, loop_tasks = True
        settings = {
            "workspace_directory": "workspace",
            "dry_run": False,
            "tasks_per_run": 1,
            "loop_tasks": True,
            "require_clean_git_before_start": True,
            "allowed_extensions": [".md"],
            "max_changed_files": 1,
        }
        (self.config_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

        task_data = {
            "tasks": [
                {
                    "id": 1,
                    "project": "TEST_REPO",
                    "file": "README.md",
                    "action": "add_comment",
                    "comment": "Daily Check 1",
                    "commit_message": "chore: loop check 1",
                    "status": "pending",
                },
                {
                    "id": 2,
                    "project": "TEST_REPO",
                    "file": "README.md",
                    "action": "add_comment",
                    "comment": "Daily Check 2",
                    "commit_message": "chore: loop check 2",
                    "status": "pending",
                },
            ]
        }
        (self.config_dir / "task.json").write_text(json.dumps(task_data), encoding="utf-8")

        # Run 1: Executes Task 1
        exit1 = agent.run_agent(base_dir=self.temp_dir, config_dir=self.config_dir, debug=True)
        self.assertEqual(exit1, 0)
        tasks1 = task_manager.load_task_configs(self.config_dir / "task.json")
        self.assertEqual(tasks1[0].status, "completed")
        self.assertEqual(tasks1[1].status, "pending")

        # Run 2: Executes Task 2 (Queue now completely finished)
        exit2 = agent.run_agent(base_dir=self.temp_dir, config_dir=self.config_dir, debug=True)
        self.assertEqual(exit2, 0)
        tasks2 = task_manager.load_task_configs(self.config_dir / "task.json")
        self.assertEqual(tasks2[0].status, "completed")
        self.assertEqual(tasks2[1].status, "completed")

        # Run 3: Loop mode should auto-reset queue and execute Task 1 again
        exit3 = agent.run_agent(base_dir=self.temp_dir, config_dir=self.config_dir, debug=True)
        self.assertEqual(exit3, 0)
        tasks3 = task_manager.load_task_configs(self.config_dir / "task.json")
        self.assertEqual(tasks3[0].status, "completed")
        self.assertEqual(tasks3[1].status, "pending")

        # Check git log has 3 new commits (1 + 2 + 1 loop)
        log_res = subprocess.run(["git", "log", "--oneline"], cwd=str(self.repo_dir), capture_output=True, text=True, check=True)
        self.assertIn("chore: loop check 1", log_res.stdout)
        self.assertIn("chore: loop check 2", log_res.stdout)


class TestConfirmationGui(unittest.TestCase):
    def test_tamil_string_constants(self) -> None:
        self.assertEqual(confirmation_gui.CONFIRMATION_MESSAGE, "இன்று GitHub task-ஐ இயக்கவா?")
        self.assertEqual(confirmation_gui.CONFIRM_BUTTON_TEXT, "இயக்கவும்")
        self.assertEqual(confirmation_gui.CANCEL_BUTTON_TEXT, "ரத்து")
        self.assertIn("பணி முடிந்தது!", confirmation_gui.SUCCESS_MESSAGE)
        self.assertIn("பணி முடியவில்லை!", confirmation_gui.FAILURE_MESSAGE)
        self.assertIn("சோதனை முடிந்தது!", confirmation_gui.DRY_RUN_MESSAGE)
        self.assertEqual(confirmation_gui.OK_BUTTON_TEXT, "சரி")

    def test_get_tamil_font_returns_tuple(self) -> None:
        font_tuple = confirmation_gui.get_tamil_font(12, "bold")
        self.assertIsInstance(font_tuple, tuple)
        self.assertEqual(font_tuple[1], 12)
        self.assertEqual(font_tuple[2], "bold")


class TestAgentGuiFlow(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agent_test_gui_"))
        self.workspace_dir = self.temp_dir / "workspace"
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir = self.temp_dir / "config"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir = self.temp_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        self.repo_dir = self.workspace_dir / "GUI_TEST_REPO"
        self.repo_dir.mkdir(parents=True, exist_ok=True)

        subprocess.run(["git", "init"], cwd=str(self.repo_dir), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "GUI Tester"], cwd=str(self.repo_dir), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "gui@test.local"], cwd=str(self.repo_dir), capture_output=True, check=True)

        self.readme = self.repo_dir / "README.md"
        self.readme.write_text("# GUI Test Repo\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=str(self.repo_dir), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(self.repo_dir), capture_output=True, check=True)

        # Initialize bare remote origin
        self.remote_dir = self.temp_dir / "REMOTE_GUI.git"
        subprocess.run(["git", "init", "--bare", str(self.remote_dir)], capture_output=True, check=True)
        subprocess.run(["git", "remote", "add", "origin", str(self.remote_dir)], cwd=str(self.repo_dir), capture_output=True, check=True)
        branch_proc = subprocess.run(["git", "branch", "--show-current"], cwd=str(self.repo_dir), capture_output=True, text=True, check=True)
        branch = branch_proc.stdout.strip() or "master"
        subprocess.run(["git", "push", "-u", "origin", branch], cwd=str(self.repo_dir), capture_output=True, check=True)

        self.settings = {
            "workspace_directory": "workspace",
            "dry_run": False,
            "tasks_per_run": 1,
            "loop_tasks": False,
            "require_clean_git_before_start": True,
            "allowed_extensions": [".md"],
            "max_changed_files": 1,
        }
        (self.config_dir / "settings.json").write_text(json.dumps(self.settings), encoding="utf-8")

        self.task_data = {
            "tasks": [
                {
                    "id": 1,
                    "project": "GUI_TEST_REPO",
                    "file": "README.md",
                    "action": "append_text",
                    "text": "<!-- GUI Task 1 -->\n",
                    "commit_message": "docs: gui task commit",
                    "status": "pending",
                }
            ]
        }
        (self.config_dir / "task.json").write_text(json.dumps(self.task_data), encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("confirmation_gui.show_confirmation", return_value=False)
    def test_gui_cancel_flow(self, mock_confirm: MagicMock) -> None:
        # User clicks 'ரத்து' -> should exit cleanly without doing any work
        exit_code = agent.run_agent(base_dir=self.temp_dir, config_dir=self.config_dir, use_gui=True)
        self.assertEqual(exit_code, 0)
        mock_confirm.assert_called_once()

        # Verify no file modification and no commits
        self.assertEqual(self.readme.read_text(encoding="utf-8"), "# GUI Test Repo\n")
        tasks = task_manager.load_task_configs(self.config_dir / "task.json")
        self.assertEqual(tasks[0].status, "pending")

    @patch("confirmation_gui.show_dry_run_result")
    @patch("confirmation_gui.show_confirmation", return_value=True)
    def test_gui_dry_run_flow(self, mock_confirm: MagicMock, mock_dry_run: MagicMock) -> None:
        # Set dry_run = True
        self.settings["dry_run"] = True
        (self.config_dir / "settings.json").write_text(json.dumps(self.settings), encoding="utf-8")

        exit_code = agent.run_agent(base_dir=self.temp_dir, config_dir=self.config_dir, use_gui=True)
        self.assertEqual(exit_code, 0)
        mock_confirm.assert_called_once()
        mock_dry_run.assert_called_once()

        # In dry run, file is restored
        self.assertEqual(self.readme.read_text(encoding="utf-8"), "# GUI Test Repo\n")

    @patch("confirmation_gui.show_success")
    @patch("confirmation_gui.show_confirmation", return_value=True)
    def test_gui_live_success_flow(self, mock_confirm: MagicMock, mock_success: MagicMock) -> None:
        exit_code = agent.run_agent(base_dir=self.temp_dir, config_dir=self.config_dir, use_gui=True)
        self.assertEqual(exit_code, 0)
        mock_confirm.assert_called_once()
        mock_success.assert_called_once()

        # Verify commit in local repo and push to remote
        self.assertIn("<!-- GUI Task 1 -->", self.readme.read_text(encoding="utf-8"))
        log_res = subprocess.run(["git", "log", "-n", "1", "--oneline"], cwd=str(self.repo_dir), capture_output=True, text=True, check=True)
        self.assertIn("docs: gui task commit", log_res.stdout)

    @patch("confirmation_gui.show_failure")
    @patch("confirmation_gui.show_confirmation", return_value=True)
    def test_gui_failure_flow_on_invalid_file(self, mock_confirm: MagicMock, mock_failure: MagicMock) -> None:
        # Set task pointing to non-existent file
        invalid_task = {
            "tasks": [
                {
                    "id": 1,
                    "project": "GUI_TEST_REPO",
                    "file": "DOES_NOT_EXIST.md",
                    "action": "append_text",
                    "text": "test",
                    "commit_message": "test fail",
                    "status": "pending",
                }
            ]
        }
        (self.config_dir / "task.json").write_text(json.dumps(invalid_task), encoding="utf-8")

        exit_code = agent.run_agent(base_dir=self.temp_dir, config_dir=self.config_dir, use_gui=True)
        self.assertEqual(exit_code, 1)
        mock_confirm.assert_called_once()
        mock_failure.assert_called_once()


if __name__ == "__main__":
    unittest.main()
