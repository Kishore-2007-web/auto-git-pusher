"""
notifier.py - Headless failure alerting module for Auto Git Pusher.

Dispatches structured failure alerts only when automation encounters unrecoverable errors.
Requires zero external pip packages (uses Python standard library urllib).
Supports:
1. Automated GitHub Issue creation in the controller repository (via GITHUB_TOKEN).
2. Optional Webhook dispatch (Discord / Telegram / Slack / generic webhook).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

import git_manager

logger = logging.getLogger("daily_github_agent")


def send_github_issue_alert(
    title: str,
    body: str,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> bool:
    """
    Open an issue in the controller repository reporting automation failure.
    Uses GITHUB_TOKEN provided natively by GitHub Actions runner.
    """
    target_repo = repo or os.getenv("GITHUB_REPOSITORY")
    auth_token = token or os.getenv("GITHUB_TOKEN")

    if not target_repo or not auth_token:
        logger.debug("GitHub Issue alert skipped: GITHUB_REPOSITORY or GITHUB_TOKEN not set.")
        return False

    api_url = f"https://api.github.com/repos/{target_repo}/issues"
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "Auto-Git-Pusher-Agent",
        "Content-Type": "application/json",
    }
    payload = {
        "title": title,
        "body": git_manager.redact_sensitive_text(body),
        "labels": ["automation-failure", "alert"],
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(api_url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as response:
            if response.status in (200, 201):
                logger.info(f"Successfully opened failure issue in {target_repo}")
                return True
            else:
                logger.warning(f"GitHub API returned unexpected status {response.status}")
                return False
    except urllib.error.HTTPError as e:
        logger.warning(f"HTTPError creating failure issue: {e.code} - {e.reason}")
        return False
    except Exception as e:
        logger.warning(f"Failed to create GitHub issue alert: {e}")
        return False


def send_webhook_alert(webhook_url: Optional[str], message: str) -> bool:
    """
    Send failure alert to an external webhook (e.g. Discord, Slack, Telegram bridge).
    """
    target_url = webhook_url or os.getenv("FAILURE_WEBHOOK_URL")
    if not target_url:
        return False

    sanitized_message = git_manager.redact_sensitive_text(message)
    headers = {
        "User-Agent": "Auto-Git-Pusher-Agent",
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {"text": sanitized_message, "content": sanitized_message}

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(target_url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status in (200, 204)
    except Exception as e:
        logger.warning(f"Failed to dispatch webhook alert: {e}")
        return False


def notify_failure(
    error_summary: str,
    details: Optional[str] = None,
    task_id: Optional[str] = None,
    project: Optional[str] = None,
) -> None:
    """
    Primary entry point to send alerts on unhandled errors.
    Only called when an actionable error occurs; completely silent on success.
    """
    run_id = os.getenv("GITHUB_RUN_ID", "local-run")
    repo = os.getenv("GITHUB_REPOSITORY", "Kishore-2007-web/auto-git-pusher")
    workflow = os.getenv("GITHUB_WORKFLOW", "Scheduled Agent")

    title = f"🚨 [Auto Git Pusher] Task Failure Alert: Run #{run_id}"

    body_lines = [
        "## Auto Git Pusher Automation Failure",
        "",
        f"- **Workflow**: `{workflow}`",
        f"- **Run ID**: `{run_id}`",
        f"- **Controller Repo**: `{repo}`",
        f"- **Target Project**: `{project or 'N/A'}`",
        f"- **Task ID**: `{task_id or 'N/A'}`",
        "",
        "### Error Summary",
        f"```text\n{git_manager.redact_sensitive_text(error_summary)}\n```",
    ]

    if details:
        body_lines.extend([
            "",
            "### Diagnostic Details",
            f"```text\n{git_manager.redact_sensitive_text(details)[:2000]}\n```",
        ])

    if run_id != "local-run":
        body_lines.extend([
            "",
            f"👉 [View Full Actions Run Logs](https://github.com/{repo}/actions/runs/{run_id})",
        ])

    full_body = "\n".join(body_lines)

    # 1. Dispatch GitHub Issue alert if running in GitHub Actions
    send_github_issue_alert(title, full_body)

    # 2. Dispatch Webhook alert if configured
    send_webhook_alert(None, f"{title}\n\n{error_summary}")
