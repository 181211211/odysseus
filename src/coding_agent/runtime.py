"""Runtime bridge between the normal Odysseus tool dispatcher and coding tasks.

The autonomous coding controller is intentionally provider-agnostic. This module
connects it to the existing agent loop without creating a second tool executor:
active tasks are associated with a session, tool budgets are enforced before
execution, and useful tool/test metadata is persisted after execution.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

from src.constants import DATA_DIR

RUNTIME_DIR = os.path.join(DATA_DIR, "coding_tasks")
ACTIVE_TASKS_FILE = os.path.join(RUNTIME_DIR, "active_tasks.json")

_INSPECTION_TOOLS = {"coding_inspect", "ls", "glob", "grep", "read_file", "coding_git", "get_workspace"}
_MODIFICATION_TOOLS = {"write_file", "edit_file", "apply_patch"}
_SHELL_TOOLS = {"bash", "python"}
_TEST_MARKERS = (
    "pytest", "unittest", "npm test", "npm run test", "pnpm test", "yarn test",
    "vitest", "jest", "cargo test", "go test", "mvn test", "gradle test",
    "dotnet test", "ruff", "mypy", "eslint", "tsc", "build",
)


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "current")[:120] or "current"


def _load_active() -> dict[str, str]:
    try:
        with open(ACTIVE_TASKS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def _save_active(data: dict[str, str]) -> None:
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    tmp = f"{ACTIVE_TASKS_FILE}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, ACTIVE_TASKS_FILE)


def register_active_task(session_id: str, task_id: str, state_path: str) -> None:
    """Associate a chat session with its active coding task."""
    data = _load_active()
    data[_safe(str(session_id))] = os.path.realpath(state_path)
    _save_active(data)


def clear_active_task(session_id: str) -> None:
    data = _load_active()
    data.pop(_safe(str(session_id)), None)
    _save_active(data)


def active_task_path(session_id: str | None) -> str | None:
    if not session_id:
        return None
    path = _load_active().get(_safe(str(session_id)))
    if not path or not os.path.isfile(path):
        return None
    return path


def _load_state(path: str) -> dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            value = json.load(fh)
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def _save_state(path: str, state: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _test_command(arguments: Mapping[str, Any]) -> str:
    return str(arguments.get("command") or arguments.get("code") or "").strip()


def _looks_like_test(arguments: Mapping[str, Any]) -> bool:
    command = _test_command(arguments).lower()
    return any(marker in command for marker in _TEST_MARKERS)


def _append_unique(items: list[Any], value: Any) -> None:
    if value not in items:
        items.append(value)


def before_tool(session_id: str | None, tool_name: str, arguments: Mapping[str, Any]) -> dict[str, Any] | None:
    """Enforce active coding-task budgets before a tool is executed.

    Returns a result dict when execution must be blocked, otherwise ``None``.
    ``coding_task`` itself is deliberately exempt so a task can be started or
    loaded even when another task has exhausted its budget.
    """
    path = active_task_path(session_id)
    if not path or tool_name == "coding_task":
        return None
    state = _load_state(path)
    if not state:
        return None

    limits = state.get("limits") or {}
    tool_calls = int(state.get("tool_calls", 0))
    shell_commands = int(state.get("shell_commands", 0))
    iterations = int(state.get("iterations", 0))
    max_tools = int(limits.get("max_tool_calls", 100))
    max_shell = int(limits.get("max_shell_commands", 40))
    max_iterations = int(limits.get("max_iterations", 20))

    if tool_calls >= max_tools:
        state["status"] = "paused"
        _append_unique(state.setdefault("errors", []), {"message": "Maximum tool-call limit reached.", "category": "limit"})
        _save_state(path, state)
        return {"error": "Coding task paused: maximum tool-call limit reached.", "exit_code": 1, "blocked": True, "limit": "max_tool_calls"}
    if tool_name in _SHELL_TOOLS and shell_commands >= max_shell:
        state["status"] = "paused"
        _append_unique(state.setdefault("errors", []), {"message": "Maximum shell-command limit reached.", "category": "limit"})
        _save_state(path, state)
        return {"error": "Coding task paused: maximum shell-command limit reached.", "exit_code": 1, "blocked": True, "limit": "max_shell_commands"}
    if iterations >= max_iterations:
        state["status"] = "paused"
        _append_unique(state.setdefault("errors", []), {"message": "Maximum iteration limit reached.", "category": "limit"})
        _save_state(path, state)
        return {"error": "Coding task paused: maximum iteration limit reached.", "exit_code": 1, "blocked": True, "limit": "max_iterations"}
    return None


def after_tool(session_id: str | None, tool_name: str, arguments: Mapping[str, Any], result: Mapping[str, Any]) -> None:
    """Record tool activity in the persisted coding-task state."""
    path = active_task_path(session_id)
    if not path or tool_name == "coding_task":
        return
    state = _load_state(path)
    if not state:
        return

    state["tool_calls"] = int(state.get("tool_calls", 0)) + 1
    if tool_name in _SHELL_TOOLS:
        state["shell_commands"] = int(state.get("shell_commands", 0)) + 1
    _append_unique(state.setdefault("commands", []), tool_name)

    raw_path = arguments.get("path") or arguments.get("file")
    if isinstance(raw_path, str) and tool_name in _INSPECTION_TOOLS:
        _append_unique(state.setdefault("inspected_files", []), raw_path)
    if isinstance(raw_path, str) and tool_name in _MODIFICATION_TOOLS:
        _append_unique(state.setdefault("modified_files", []), raw_path)
        if state.get("status") == "fixing":
            # A real edit is new evidence; the next test is expected to be a
            # retest rather than a blind duplicate call.
            state["errors"] = [e for e in state.get("errors", []) if e.get("category") not in {"duplicate_failure"}]

    exit_code = result.get("exit_code")
    failed = bool(result.get("error")) or (isinstance(exit_code, int) and exit_code != 0)
    if tool_name in _SHELL_TOOLS and _looks_like_test(arguments):
        command = _test_command(arguments) or tool_name
        state.setdefault("tests", []).append({
            "command": command,
            "exit_code": int(exit_code or 0),
            "passed": not failed,
            "output": str(result.get("output") or result.get("stderr") or result.get("error") or "")[-12000:],
        })
        if failed:
            state["test_retries"] = int(state.get("test_retries", 0)) + 1
            state["status"] = "fixing"
            state.setdefault("errors", []).append({"message": str(result.get("error") or result.get("output") or "test failed")[-12000:], "category": "test_failure"})
        else:
            state["status"] = "reviewing"
    elif failed:
        state.setdefault("errors", []).append({"message": str(result.get("error") or result.get("stderr") or "tool failed")[-12000:], "category": "tool_failure"})

    if tool_name in {"coding_git"} and str(arguments.get("action") or "").lower() in {"status", "diff"} and not failed:
        state["reviewed"] = True
        state["status"] = "reviewing"

    _save_state(path, state)
