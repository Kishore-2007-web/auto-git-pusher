"""
test_cloud_hardening.py - Unit and regression tests for cloud automation, security, and validation.
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
import git_manager
import notifier
import task_manager
import validator


class TestCloudHardeningAndSecurity(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="agent_test_cloud_"))
        self.workspace_dir = self.temp_dir / "workspace"
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir = self.temp_dir / "config"
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.repo_dir = self.workspace_dir / "TEST_PROJ"
        self.repo_dir.mkdir(parents=True, exist_ok=True)

        # Real git repo
        subprocess.run(["git", "init"], cwd=str(self.repo_dir), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Cloud Tester"], cwd=str(self.repo_dir), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "cloud@test.local"], cwd=str(self.repo_dir), capture_output=True, check=True)

        self.readme = self.repo_dir / "README.md"
        self.readme.write_text("# Test Project\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=str(self.repo_dir), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(self.repo_dir), capture_output=True, check=True)

        self.settings = {
            "workspace_directory": "workspace",
            "dry_run": True,
            "tasks_per_run": 1,
            "loop_tasks": False,
            "require_clean_git_before_start": True,
            "allowed_repositories": ["TEST_PROJ"],
            "allowed_branches": ["main", "master"],
            "emergency_pause": False,
            "allowed_extensions": [".md", ".txt"],
            "max_changed_files": 1,
        }
        (self.config_dir / "settings.json").write_text(json.dumps(self.settings), encoding="utf-8")

        default_tasks = {
            "tasks": [
                {
                    "id": 1,
                    "project": "TEST_PROJ",
                    "file": "README.md",
                    "action": "append_text",
                    "text": "# default",
                    "commit_message": "default",
                    "status": "completed",
                }
            ]
        }
        (self.config_dir / "task.json").write_text(json.dumps(default_tasks), encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_secret_redaction(self) -> None:
        token_str = "ghp_123456789012345678901234567890123456"
        redacted_token = git_manager.redact_sensitive_text(f"Token: {token_str}")
        self.assertIn("[REDACTED_GH_TOKEN]", redacted_token)
        self.assertNotIn(token_str, redacted_token)

        url_with_auth = f"https://x-access-token:{token_str}@github.com/org/repo.git"
        redacted_url = git_manager.redact_sensitive_text(url_with_auth)
        self.assertNotIn(token_str, redacted_url)
        self.assertIn("https://[REDACTED_CREDENTIAL]@", redacted_url)

    def test_git_commit_flag_sanitization(self) -> None:
        # Commit message starting with flag syntax --amend
        test_file = self.repo_dir / "test_flag.txt"
        test_file.write_text("content", encoding="utf-8")
        git_manager.git_add(self.repo_dir, "test_flag.txt")
        commit_hash = git_manager.git_commit(self.repo_dir, "--amend -s test message")
        self.assertTrue(len(commit_hash) >= 4)

        # Verify commit message was stored verbatim rather than altering git flags
        proc = subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=str(self.repo_dir), capture_output=True, text=True, check=True)
        self.assertIn("--amend -s test message", proc.stdout)

    def test_git_command_timeout(self) -> None:
        # Mock subprocess.run to raise TimeoutExpired
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["git", "push"], timeout=5)):
            with self.assertRaises(git_manager.GitError) as ctx:
                git_manager._run_git_command(["push"], cwd=self.repo_dir, timeout=5)
            self.assertIn("timed out after 5 seconds", str(ctx.exception))

    def test_repository_allowlist_enforcement(self) -> None:
        # Project not in allowed_repositories
        with self.assertRaises(validator.ValidationError):
            validator.validate_repository_and_branch(
                project_name="UNAUTHORIZED_REPO",
                branch_name="main",
                allowed_repositories=["weather", "TEST_PROJ"],
                allowed_branches=["main"],
            )

    def test_branch_allowlist_enforcement(self) -> None:
        # Branch not in allowed_branches
        with self.assertRaises(validator.ValidationError):
            validator.validate_repository_and_branch(
                project_name="TEST_PROJ",
                branch_name="release-v2",
                allowed_repositories=["TEST_PROJ"],
                allowed_branches=["main", "master"],
            )

    def test_emergency_pause_setting(self) -> None:
        self.settings["emergency_pause"] = True
        (self.config_dir / "settings.json").write_text(json.dumps(self.settings), encoding="utf-8")

        task = {
            "tasks": [
                {
                    "id": 1,
                    "project": "TEST_PROJ",
                    "file": "README.md",
                    "action": "append_text",
                    "text": "new text",
                    "commit_message": "test",
                    "status": "pending",
                }
            ]
        }
        (self.config_dir / "task.json").write_text(json.dumps(task), encoding="utf-8")

        # Run agent: should exit with EXIT_SUCCESS (0) without running tasks
        exit_code = agent.run_agent(base_dir=self.temp_dir, config_dir=self.config_dir, use_gui=False)
        self.assertEqual(exit_code, agent.EXIT_SUCCESS)

        # File should remain unmodified
        self.assertEqual(self.readme.read_text(encoding="utf-8"), "# Test Project\n")

    def test_emergency_pause_env(self) -> None:
        with patch.dict(os.environ, {"AUTOMATION_PAUSED": "true"}):
            self.assertTrue(validator.check_emergency_pause({}))

    def test_forbidden_workflow_modification(self) -> None:
        workflow_file = self.repo_dir / ".github" / "workflows" / "test.yml"
        workflow_file.parent.mkdir(parents=True, exist_ok=True)
        workflow_file.write_text("name: Test", encoding="utf-8")

        is_forbidden, reason = validator.is_forbidden_target(workflow_file)
        self.assertTrue(is_forbidden)
        self.assertIn("workflow", reason.lower())

    @patch("confirmation_gui.show_confirmation")
    def test_headless_ci_auto_detection(self, mock_show_confirm: MagicMock) -> None:
        # In CI environment, use_gui=True should be automatically ignored
        with patch.dict(os.environ, {"CI": "true"}):
            exit_code = agent.run_agent(
                base_dir=self.temp_dir,
                config_dir=self.config_dir,
                use_gui=True,
            )
            # GUI popup should NEVER have been called
            mock_show_confirm.assert_not_called()
            self.assertEqual(exit_code, agent.EXIT_SUCCESS)

    def test_dry_run_override(self) -> None:
        # Settings has dry_run=False
        self.settings["dry_run"] = False
        (self.config_dir / "settings.json").write_text(json.dumps(self.settings), encoding="utf-8")

        task = {
            "tasks": [
                {
                    "id": 1,
                    "project": "TEST_PROJ",
                    "file": "README.md",
                    "action": "append_text",
                    "text": "\n<!-- Dry Run Test Override -->\n",
                    "commit_message": "docs: test dry run override",
                    "status": "pending",
                }
            ]
        }
        (self.config_dir / "task.json").write_text(json.dumps(task), encoding="utf-8")

        # Execute with dry_run_override=True
        exit_code = agent.run_agent(
            base_dir=self.temp_dir,
            config_dir=self.config_dir,
            use_gui=False,
            dry_run_override=True,
        )
        self.assertEqual(exit_code, agent.EXIT_SUCCESS)

        # File must remain untouched
        self.assertEqual(self.readme.read_text(encoding="utf-8"), "# Test Project\n")

    @patch("urllib.request.urlopen")
    def test_notifier_github_issue_alert(self, mock_urlopen: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status = 201
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        result = notifier.send_github_issue_alert(
            title="Test Failure",
            body="Sensitive token ghp_123456789012345678901234567890123456 leaked",
            repo="Kishore-2007-web/auto-git-pusher",
            token="dummy_token",
        )
        self.assertTrue(result)
        mock_urlopen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
