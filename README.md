# Daily GitHub Agent (Version 1)

> **A deterministic, secure, and beginner-friendly local automation agent for daily GitHub maintenance on Windows 10/11.**

---

## Table of Contents

1. [What is Daily GitHub Agent?](#1-what-is-daily-github-agent)
2. [Why Does It Exist?](#2-why-does-it-exist)
3. [System Architecture](#3-system-architecture)
4. [Folder Structure](#4-folder-structure)
5. [How the System Works Step-by-Step](#5-how-the-system-works-step-by-step)
6. [How to Install Python (Windows 10/11)](#6-how-to-install-python-windows-1011)
7. [How to Verify Git Installation](#7-how-to-verify-git-installation)
8. [How to Configure the Project](#8-how-to-configure-the-project)
9. [How to Configure `config/task.json`](#9-how-to-configure-configtaskjson)
10. [How to Configure `config/settings.json`](#10-how-to-configure-configsettingsjson)
11. [How to Run Dry-Run Mode (Safe Mode)](#11-how-to-run-dry-run-mode-safe-mode)
12. [How to Enable Real Commit & Push (Live Mode)](#12-how-to-enable-real-commit--push-live-mode)
13. [How to Modify Tasks](#13-how-to-modify-tasks)
14. [Supported V1 Actions](#14-supported-v1-actions)
15. [How to Add a New Action Later](#15-how-to-add-a-new-action-later)
16. [Git Safety Rules & Guardrails](#16-git-safety-rules--guardrails)
17. [Security Limitations & Boundary Defenses](#17-security-limitations--boundary-defenses)
18. [Troubleshooting Common Issues](#18-troubleshooting-common-issues)
19. [Example Daily Workflow](#19-example-daily-workflow)
20. [Roadmap for Version 2 (Local AI Model)](#20-roadmap-for-version-2-local-ai-model)
21. [Testing with Your Own GitHub Repository](#21-testing-with-your-own-github-repository)
22. [Tamil GUI Confirmation](#22-tamil-gui-confirmation)

---

## 1. What is Daily GitHub Agent?

**Daily GitHub Agent** is a lightweight, local automation tool designed to execute small, predefined maintenance tasks on your local Git repositories and push changes to GitHub.

It runs with a single double-click on `run.bat` or via a quick terminal command, making routine repository maintenance completely effortless for any user without requiring Git commands or Python programming knowledge.

---

## 2. Why Does It Exist?

Maintaining active GitHub repositories often involves simple recurring tasks:
- Adding daily notes, release tags, or status updates to documentation.
- Updating changelogs or README files.
- Ensuring consistent commits without dealing with terminal commands every day.

Non-technical users, students, or team members often find standard command-line Git workflows intimidating or prone to mistakes (like staging unwanted files or running destructive commands). Daily GitHub Agent eliminates complexity while applying enterprise-grade safety checks to ensure nothing unexpected happens.

---

## 3. System Architecture

The following diagram illustrates the flow of control:

```
 User / Double-Click "run.bat"
             │
             ▼
        [agent.py] (Orchestrator)
             │
             ├──► Loads config/settings.json & config/task.json
             │
             ├──► [validator.py]
             │     ├── Path Traversal Checks (fail closed)
             │     ├── Forbidden Files Blacklist (.env, .git, keys)
             │     └── Extension Whitelist (.md, .py, .txt, etc.)
             │
             ├──► [git_manager.py]
             │     ├── Verify Git is installed
             │     ├── Verify target is a Git repo
             │     └── Clean Workspace Check (aborts if dirty)
             │
             ├──► [validator.py]
             │     └── Creates temporary backup (*.agent_bak)
             │
             ├──► [task_manager.py]
             │     ├── Idempotency Check (skips duplicate runs)
             │     └── Executes deterministic action (append/comment/replace)
             │
             ├──► [validator.py]
             │     └── Validates that ONLY the expected file was modified
             │
             ├──► Displays Git Diff to User
             │
             ├──► IF dry_run == true:
             │     └── Reverts change from backup & exits cleanly
             │
             └──► IF dry_run == false:
                   ├── git_manager: git add <specific_file>
                   ├── git_manager: git commit -m "<task message>"
                   ├── git_manager: git push origin <branch>
                   └── Cleans up backup & logs success
```

---

## 4. Folder Structure

```
daily-github-agent/
│
├── README.md               # Complete guide and documentation
├── agent.py                # Main CLI entrypoint and orchestrator
├── task_manager.py         # Task parsing, execution, and idempotency logic
├── git_manager.py          # Safe subprocess-based Git interface
├── validator.py            # Security sandbox, backup/rollback, path validation
├── run.bat                 # 1-click Windows batch launcher
├── requirements.txt        # Python dependencies (Standard Library only)
├── .gitignore              # Git ignore rules for logs, cache, and workspace
│
├── config/
│   ├── settings.json       # Agent global configuration
│   └── task.json           # Active daily task definition
│
├── workspace/              # Folder where you place/clone target Git repos
│   └── .gitkeep
│
├── logs/                   # Automatic daily audit logs (e.g. 2026-08-14.log)
│   └── .gitkeep
│
└── tests/
    └── test_agent.py       # Automated unit & integration tests
```

---

## 5. How the System Works Step-by-Step

1. **Startup**: The user double-clicks `run.bat`. The script detects the Python environment and invokes `agent.py`.
2. **Configuration**: The agent loads `config/settings.json` and `config/task.json`.
3. **Safety Inspection**:
   - Validates that the target project is strictly inside `workspace/`.
   - Validates that the target file is inside the target project.
   - Rejects path traversal (`../`, `..\`) and sensitive files (`.env`, `.git`, SSH keys).
   - Verifies the target repository is clean (no uncommitted user work).
4. **Backup**: A temporary `.agent_bak` file is created.
5. **Deterministic Execution**: The task is executed on the file.
6. **Idempotency Check**: If the target content already exists, the agent reports that the task is already completed and exits without creating duplicate commits.
7. **Change Validation**: Confirms that only the single expected file was modified.
8. **Diff Display**: Shows the exact Git diff in the terminal.
9. **Commit & Push (or Revert)**:
   - If `dry_run: true`: The file is restored to its original state so your workspace remains clean.
   - If `dry_run: false`: The file is staged, committed with the configured message, and pushed to your remote GitHub repository.
10. **Audit Log**: The entire execution is recorded in `logs/YYYY-MM-DD.log`.

---

## 6. How to Install Python (Windows 10/11)

If Python is not installed on your computer:

1. Download the official installer from [Python.org](https://www.python.org/downloads/).
2. Run the installer.
3. **CRITICAL STEP**: On the very first screen, check the box:
   `☑ Add python.exe to PATH`
4. Click **Install Now**.
5. Once installation finishes, open Command Prompt or PowerShell and verify:
   ```cmd
   py --version
   ```
   *(Should display Python 3.10 or higher).*

---

## 7. How to Verify Git Installation

1. Open Command Prompt or PowerShell.
2. Run:
   ```cmd
   git --version
   ```
3. If Git is not installed, download and install [Git for Windows](https://git-scm.com/download/win). Keep the default installation options.

---

## 8. How to Configure the Project

Place or clone the Git repository you want to manage into the `workspace/` folder:

```
daily-github-agent/
└── workspace/
    └── my-notes-repo/      <-- Your Git repository
        ├── README.md
        └── ...
```

---

## 9. How to Configure `config/task.json` (Task Queue)

The file `config/task.json` allows you to assign a queue of multiple tasks (e.g. 10 tasks). The agent will execute them in batches (e.g. 2 tasks per double-click of `run.bat`), automatically tracking which tasks are completed.

### Example: 10-Task Queue with Status Tracking

```json
{
  "tasks": [
    {
      "id": 1,
      "project": "YOUR_REPO_NAME",
      "file": "README.md",
      "action": "append_text",
      "text": "\n<!-- Task 1: Initial daily note -->\n",
      "commit_message": "docs: task 1 initial daily note",
      "status": "pending"
    },
    {
      "id": 2,
      "project": "YOUR_REPO_NAME",
      "file": "README.md",
      "action": "append_text",
      "text": "\n<!-- Task 2: Second daily note -->\n",
      "commit_message": "docs: task 2 update notes",
      "status": "pending"
    },
    {
      "id": 3,
      "project": "YOUR_REPO_NAME",
      "file": "main.py",
      "action": "add_comment",
      "comment": "Task 3 maintenance verification",
      "position": "bottom",
      "commit_message": "chore: add task 3 comment",
      "status": "pending"
    },
    {
      "id": 4,
      "project": "YOUR_REPO_NAME",
      "file": "status.txt",
      "action": "replace_text",
      "target_text": "STATUS=PENDING",
      "replacement_text": "STATUS=VERIFIED",
      "commit_message": "chore: update status",
      "status": "pending"
    }
  ]
}
```

When a task completes in live mode, the agent automatically updates `config/task.json` with:
- `"status": "completed"`
- `"completed_at": "2026-08-14 08:35:00"`
- `"commit_hash": "a1b2c3d"`

---

## 10. How to Configure `config/settings.json`

Global settings are stored in `config/settings.json`:

```json
{
  "workspace_directory": "workspace",
  "dry_run": false,
  "tasks_per_run": 2,
  "loop_tasks": true,
  "require_clean_git_before_start": true,
  "allowed_extensions": [
    ".md",
    ".txt",
    ".py",
    ".js",
    ".html",
    ".css"
  ],
  "max_changed_files": 1
}
```

| Setting | Type | Description |
|---|---|---|
| `workspace_directory` | string | Subfolder containing target repositories (default: `"workspace"`). |
| `dry_run` | boolean | When `true`, shows proposed changes without committing or pushing. |
| `tasks_per_run` | integer | Number of pending tasks to execute per run (default: `2`). |
| `loop_tasks` | boolean | When `true`, automatically resets completed tasks to `pending` in an infinite loop so clicking `run.bat` 10, 20, or 100+ times always continues executing and committing. |
| `require_clean_git_before_start` | boolean | When `true`, stops immediately if uncommitted changes exist in the repo. |
| `allowed_extensions` | list | Whitelist of file extensions the agent is allowed to touch. |
| `max_changed_files` | integer | Maximum number of files permitted to change in a single task (default: `1`). |

---

## 11. How to Run Dry-Run Mode (Safe Mode)

By default, `dry_run` is set to `true`.

To run dry-run mode:
1. Double-click `run.bat` (or run `py agent.py` in your terminal).
2. The agent will:
   - Validate paths and security rules.
   - Apply the modification temporarily in memory/disk.
   - Display the unified Git diff in your terminal.
   - Automatically revert the modification.
   - Leave your repository completely untouched.

---

## 12. How to Enable Real Commit & Push (Live Mode)

Once you have verified the diff in Dry-Run mode:

1. Open `config/settings.json` in any text editor (Notepad, VS Code, etc.).
2. Change `"dry_run": true` to `"dry_run": false`:
   ```json
   "dry_run": false
   ```
3. Save the file.
4. Run `run.bat` or `py agent.py`.
5. The agent will execute the modification, stage the exact file (`git add <file>`), commit with your commit message, and push to GitHub!

---

## 13. How to Modify Tasks

To change the action or target file:
1. Open `config/task.json`.
2. Update the `project`, `file`, `action`, or `text` fields.
3. Save and execute `run.bat`.

---

## 14. Supported V1 Actions

Version 1 is fully deterministic and supports three core actions:

1. `append_text`: Appends the provided string to the end of the file.
2. `add_comment`: Adds a formatted comment (at `top` or `bottom` of file). Automatically uses `#` for Python/TXT, `<!-- -->` for Markdown/HTML, or `/* */` for JavaScript/CSS.
3. `replace_text`: Replaces the specified `target_text` string with `replacement_text`.

---

## 15. How to Add a New Action Later

To add a new deterministic action in the future:
1. Add the new action name to `SUPPORTED_ACTIONS` in `task_manager.py`.
2. Implement the action logic inside `execute_task()` in `task_manager.py`.
3. Include an idempotency check to avoid redundant modifications.
4. Add corresponding unit tests in `tests/test_agent.py`.

---

## 16. Git Safety Rules & Guardrails

The agent enforces strict safety rules:

- **No Destructive Commands**: Never runs `git reset --hard`, `git clean`, `git checkout -f`, or `git stash drop`.
- **No Global Staging**: Staging is strictly limited to `git add <exact_file>`. It **NEVER** runs `git add .` or `git add -A`.
- **No Force Pushing**: Never uses `git push --force` or `git push -f`.
- **Clean Workspace Requirement**: If uncommitted edits already exist in the repository, the agent refuses to modify the repository to prevent overwriting existing work.
- **Fail-Closed Rollback**: If an error occurs during execution, the target file is immediately restored from `.agent_bak`.

---

## 17. Security Limitations & Boundary Defenses

- **Strict Path Sandboxing**: Project must reside inside `workspace_directory`. Traversal sequences like `../` or `..\` are strictly rejected.
- **Blacklisted Files**: The agent will never modify `.env`, `.git/*`, SSH keys (`id_rsa`, `id_ed25519`), private keys (`.pem`, `.key`), or password files.
- **Extension Whitelist**: Only files with extensions specified in `allowed_extensions` can be modified.
- **No Code Execution**: `task.json` does not execute shell scripts, eval Python code, or invoke CMD commands.

---

## 18. Troubleshooting Common Issues

### "Python was not found"
- Reinstall Python from [python.org](https://www.python.org/downloads/) and ensure `Add python.exe to PATH` is checked.
- Alternatively, launch via `py agent.py`.

### "Repository contains existing uncommitted changes"
- Open your target repository in `workspace/<project>` and either commit or discard your manual edits before running the agent.

### "Target project directory not found"
- Verify that your cloned Git repository folder name matches the `"project"` name in `config/task.json`.

### "Git push failed: origin does not appear to be a git repository"
- Make sure your local repository in `workspace/` has a remote configured:
  ```cmd
  cd workspace/your-repo
  git remote -v
  ```
  If no remote is set, add one using `git remote add origin <github-repo-url>`.

---

## 19. Example Daily Workflow

1. Turn on computer.
2. Double-click `run.bat` on Desktop or folder.
3. The console opens, shows the progress banner, executes the daily maintenance task, stages, commits, and pushes.
4. Terminal outputs:
   ```
   ============================================================
    [OK] SUCCESS: Changes successfully committed!
    - Project:       my-notes-repo
    - File:          README.md
    - Commit Hash:   a1b2c3d
    - Message:       docs: update readme with daily notes
    - Remote Status: Success: Pushed successfully to origin/main
   ============================================================
   ```
5. Press any key to close the window. Done!

---

## 20. Roadmap for Version 2 (Local AI Model)

In Version 2, the agent will support local, offline AI model integration (e.g. via Ollama or llama.cpp) to interpret dynamic natural-language requests into deterministic patches:

```
 User Request in task.json ("Summarize today's progress log")
                       │
                       ▼
            Local AI Model (Ollama / GGUF)
                       │
                       ▼
          AI Generates Proposed Code Patch
                       │
                       ▼
          Strict V1 Validator & Sandbox Checks
                       │
                       ▼
              Diff Display & Approval
                       │
                       ▼
               Git Commit & Push
```

*Note: Version 1 contains NO AI models or external API calls, ensuring 100% predictable and audited operation.*

---

## 21. Testing with Your Own GitHub Repository

Follow these step-by-step instructions to test Daily GitHub Agent with a test GitHub repository:

### Step 1: Create a Test Repository on GitHub
1. Go to [github.com/new](https://github.com/new).
2. Name the repository: `daily-agent-test`.
3. Select **Public** or **Private**.
4. Check **Add a README file**.
5. Click **Create repository**.

### Step 2: Clone the Repository into `workspace/`
Open Command Prompt or PowerShell in the `daily-github-agent` folder:
```cmd
cd workspace
git clone https://github.com/<your-username>/daily-agent-test.git
cd ..
```

### Step 3: Configure `config/task.json`
Edit `config/task.json`:
```json
{
  "project": "daily-agent-test",
  "file": "README.md",
  "action": "append_text",
  "text": "\n<!-- Daily GitHub Agent V1 test -->\n",
  "commit_message": "docs: test daily github agent automation"
}
```

### Step 4: Run Dry-Run Mode
Double-click `run.bat` or run:
```cmd
py agent.py
```
Verify the diff preview in the terminal.

### Step 5: Enable Live Mode
In `config/settings.json`, set:
```json
"dry_run": false
```

### Step 6: Execute Live Commit & Push
Run `run.bat` again. The agent will commit and push the change to your GitHub repository!

### Step 7: Verify on GitHub
Open `https://github.com/<your-username>/daily-agent-test` in your browser and verify the new commit and updated `README.md`.

---

## 22. Tamil GUI Confirmation

### 1. Why the GUI Was Added
Daily GitHub Agent was enhanced with a native Windows Tamil GUI confirmation flow to make daily repository maintenance comfortable, intuitive, and accessible for non-technical users (such as Dad or team members). Users do not need to read terminal logs or understand Git commands.

### 2. Workflow Diagram
```
run.bat
   ↓
Tamil Confirmation Popup
   ↓
[ இயக்கவும் ] or [ ரத்து ]
   ↓
Existing V1 Agent (Deterministic Safety Pipeline)
   ↓
Task → Path Validation → Safe Modification → Git Add → Commit → Push
   ↓
Tamil Result Notification Popup
   ↓
[ சரி ] → Exit
```

### 3. What Happens When `run.bat` is Double-Clicked
1. `run.bat` launches Python in windowed mode (`pyw` / `pythonw`), preventing a lingering CMD terminal window from remaining open.
2. The initial **Tamil Confirmation Popup** appears immediately, centered on the primary screen.

### 4. Confirmation Popup
- **Title**: `Daily GitHub Agent`
- **Message**: `இன்று GitHub task-ஐ இயக்கவா?` (Should today's GitHub task be run?)
- **Buttons**:
  - `[ இயக்கவும் ]` (Confirm & Run)
  - `[ ரத்து ]` (Cancel)

### 5. What Happens When "இயக்கவும்" is Clicked
- The confirmation window closes.
- The **EXISTING V1 Agent** engine runs all deterministic safety steps:
  1. Validates repository boundaries and path traversal restrictions.
  2. Ensures the repository is clean (no dirty uncommitted changes).
  3. Creates a safety backup of the target file (`.agent_bak`).
  4. Deterministically modifies the target file.
  5. Validates that only the single expected file was modified.
  6. Stages the file (`git add <file>`), commits (`git commit -m "..."`), and pushes to GitHub (`git push`).
  7. Displays the appropriate result popup upon completion.

### 6. What Happens When "ரத்து" is Clicked
- The confirmation window closes immediately.
- **NO files are modified**.
- **NO Git commands are executed**.
- **NO commits or pushes occur**.
- The application cleanly exits with return code `0`.

### 7. Success Popup
Displayed **ONLY** if the entire live workflow completed successfully, including `git push`:
- **Title**: `Daily GitHub Agent`
- **Message**:
  ```text
  ✅ பணி முடிந்தது!

  இன்றைய GitHub task வெற்றிகரமாக
  முடிக்கப்பட்டது.
  ```
- **Button**: `[ சரி ]` (Clicking closes the app and exits cleanly).

### 8. Failure Popup
Displayed if **ANY** critical step fails (e.g. invalid target file, dirty workspace, git commit failure, network push error):
- **Title**: `Daily GitHub Agent`
- **Message**:
  ```text
  ❌ பணி முடியவில்லை!

  இன்றைய GitHub task-ஐ முடிக்க
  முடியவில்லை.

  மேலும் தகவலுக்கு log-ஐ பார்க்கவும்.
  ```
- **Button**: `[ சரி ]`
- Technical diagnostic details are safely written to `logs/YYYY-MM-DD.log` without exposing raw stack traces to the user.

### 9. Dry-Run Popup
If `dry_run: true` is enabled in `config/settings.json`, the agent verifies the modification, displays the diff, rolls back the file from backup, and shows:
- **Title**: `Daily GitHub Agent`
- **Message**:
  ```text
  🧪 சோதனை முடிந்தது!

  Dry-run வெற்றிகரமாக முடிந்தது.
  GitHub-க்கு எந்த மாற்றமும் அனுப்பப்படவில்லை.
  ```
- **Button**: `[ சரி ]`

### 10. How to Change the Tamil Text
All UI strings are stored as clean constants at the top of `confirmation_gui.py`:
- `CONFIRMATION_MESSAGE`
- `CONFIRM_BUTTON_TEXT`
- `CANCEL_BUTTON_TEXT`
- `SUCCESS_MESSAGE`
- `FAILURE_MESSAGE`
- `DRY_RUN_MESSAGE`
- `OK_BUTTON_TEXT`

To customize any message, simply edit `confirmation_gui.py` directly.

### 11. How the GUI Communicates with `agent.py`
The GUI logic is completely decoupled in `confirmation_gui.py`. `agent.py` orchestrates the flow:
1. `confirmation_gui.show_confirmation()` is invoked before running tasks.
2. If confirmed, `agent.py` executes the existing V1 validation and Git pipeline.
3. Upon completion, `agent.py` invokes `confirmation_gui.show_success()`, `show_dry_run_result()`, or `show_failure()` based on structured execution status.
4. When running automated headless test suites, the flag `--no-gui` (or `use_gui=False`) allows the CLI to execute without opening interactive windows.

