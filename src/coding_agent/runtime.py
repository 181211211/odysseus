"""Runtime bridge between the normal Odysseus tool dispatcher and coding tasks."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Mapping

from src.constants import DATA_DIR

RUNTIME_DIR = os.path.join(DATA_DIR, "coding_tasks")
ACTIVE_TASKS_FILE = os.path.join(RUNTIME_DIR, "active_tasks.json")

_INSPECTION_TOOLS = {"coding_inspect", "ls", "glob", "grep", "read_file", "coding_git", "get_workspace"}
_MODIFICATION_TOOLS = {"write_file", "edit_file", "apply_patch"}
_SHELL_TOOLS = {"bash", "python"}
_CODING_JSON_TOOLS = {"coding_task", "coding_inspect", "coding_git"}
_TEST_MARKERS = ("pytest", "unittest", "npm test", "npm run test", "pnpm test", "yarn test", "vitest", "jest", "cargo test", "go test", "mvn test", "gradle test", "dotnet test", "ruff", "mypy", "eslint", "tsc", "build")


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


def current_workspace(ctx: Mapping[str, Any] | None = None) -> str | None:
    """Resolve the dispatcher-bound workspace without widening authority."""
    if isinstance(ctx, Mapping) and ctx.get("workspace"):
        return str(ctx.get("workspace"))
    try:
        from src.tool_execution import get_active_workspace
        value = get_active_workspace()
        return str(value) if value else None
    except Exception:
        return None


def prepare_tool_content(tool_name: str, content: str | None, workspace: str | None) -> str:
    """Inject the already-authorized active workspace into coding JSON tools.

    This is convenience plumbing only: tool_execution has already bound and
    vetted the workspace for the call, and the normal path-security layer still
    enforces confinement. Explicit model-supplied workspaces are never replaced.
    """
    raw = str(content or "")
    if tool_name not in _CODING_JSON_TOOLS or not workspace:
        return raw
    stripped = raw.strip()
    try:
        payload = json.loads(stripped) if stripped else {}
    except (json.JSONDecodeError, TypeError):
        return raw
    if not isinstance(payload, dict) or payload.get("workspace"):
        return raw
    payload["workspace"] = workspace
    return json.dumps(payload, ensure_ascii=False)


def parse_tool_arguments(tool_name: str, content: str | None, *, workspace: str | None = None) -> dict[str, Any]:
    """Parse tool payloads for telemetry only; never use this for authorization."""
    raw = str(content or "")
    stripped = raw.strip()
    if stripped.startswith("{"):
        try:
            value = json.loads(stripped)
            if isinstance(value, dict):
                if workspace and not value.get("workspace"):
                    value = dict(value)
                    value["workspace"] = workspace
                return dict(value)
        except (json.JSONDecodeError, TypeError):
            pass
    lines = raw.splitlines()
    if tool_name in _SHELL_TOOLS:
        return {"command": raw}
    if tool_name in _MODIFICATION_TOOLS or tool_name in _INSPECTION_TOOLS:
        args: dict[str, Any] = {"path": lines[0].strip() if lines else ""}
        if tool_name == "apply_patch":
            match = re.search(r"\*\*\* (?:Update|Add|Delete) File:\s*(.+)", raw)
            if match:
                args["path"] = match.group(1).strip()
        if workspace:
            args["workspace"] = workspace
        return args
    return {"raw": raw, "workspace": workspace} if workspace else {"raw": raw}


def _test_command(arguments: Mapping[str, Any]) -> str:
    return str(arguments.get("command") or arguments.get("code") or "").strip()


def _looks_like_test(arguments: Mapping[str, Any]) -> bool:
    command = _test_command(arguments).lower()
    return any(marker in command for marker in _TEST_MARKERS)


def _append_unique(items: list[Any], value: Any) -> None:
    if value not in items:
        items.append(value)


def _limit_state(state: dict[str, Any], message: str, key: str) -> dict[str, Any]:
    state["status"] = "paused"
    _append_unique(state.setdefault("errors", []), {"message": message, "category": "limit"})
    return {"error": f"Coding task paused: {message}", "exit_code": 1, "blocked": True, "limit": key}


def before_tool(session_id: str | None, tool_name: str, arguments: Mapping[str, Any]) -> dict[str, Any] | None:
    path = active_task_path(session_id)
    if not path or tool_name == "coding_task":
        return None
    state = _load_state(path)
    if not state:
        return None
    limits = state.get("limits") or {}
    if int(state.get("tool_calls", 0)) >= int(limits.get("max_tool_calls", 100)):
        result = _limit_state(state, "maximum tool-call limit reached", "max_tool_calls")
        _save_state(path, state)
        return result
    if tool_name in _SHELL_TOOLS and int(state.get("shell_commands", 0)) >= int(limits.get("max_shell_commands", 40)):
        result = _limit_state(state, "maximum shell-command limit reached", "max_shell_commands")
        _save_state(path, state)
        return result
    if int(state.get("iterations", 0)) >= int(limits.get("max_iterations", 20)):
        result = _limit_state(state, "maximum iteration limit reached", "max_iterations")
        _save_state(path, state)
        return result
    return None


def after_tool(session_id: str | None, tool_name: str, arguments: Mapping[str, Any], result: Mapping[str, Any]) -> None:
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
        state["errors"] = [e for e in state.get("errors", []) if e.get("category") != "duplicate_failure"]

    exit_code = result.get("exit_code")
    failed = bool(result.get("error")) or (isinstance(exit_code, int) and exit_code != 0)
    if tool_name in _SHELL_TOOLS and _looks_like_test(arguments):
        command = _test_command(arguments) or tool_name
        state.setdefault("tests", []).append({"command": command, "exit_code": int(exit_code or 0), "passed": not failed, "output": str(result.get("output") or result.get("stdout") or result.get("stderr") or result.get("error") or "")[-12000:]})
        if failed:
            state["test_retries"] = int(state.get("test_retries", 0)) + 1
            state["status"] = "fixing"
            state.setdefault("errors", []).append({"message": str(result.get("error") or result.get("stderr") or "test failed")[-12000:], "category": "test_failure"})
        else:
            state["status"] = "reviewing"
    elif failed:
        state.setdefault("errors", []).append({"message": str(result.get("error") or result.get("stderr") or "tool failed")[-12000:], "category": "tool_failure"})

    if tool_name == "coding_git" and str(arguments.get("action") or "").lower() in {"status", "diff"} and not failed:
        state["reviewed"] = True
        state["status"] = "reviewing"
    _save_state(path, state)


def install_runtime_hooks(tool_handlers: dict[str, Any]) -> None:
    """Wrap the existing handler registry without replacing the dispatcher."""
    if getattr(install_runtime_hooks, "_installed", False):
        return
    for name, handler in list(tool_handlers.items()):
        if getattr(handler, "_coding_runtime_wrapped", False):
            continue

        async def wrapped(content, ctx, _handler=handler, _name=name):
            ctx = ctx if isinstance(ctx, dict) else {}
            session_id = ctx.get("session_id")
            workspace = current_workspace(ctx)
            prepared_content = prepare_tool_content(_name, content, workspace)
            arguments = parse_tool_arguments(_name, prepared_content, workspace=workspace)
            blocked = before_tool(session_id, _name, arguments)
            if blocked is not None:
                return blocked
            try:
                result = await _handler(prepared_content, ctx)
            except Exception as exc:
                result = {"error": str(exc), "exit_code": 1}
            if isinstance(result, Mapping):
                after_tool(session_id, _name, arguments, result)
            return result

        wrapped._coding_runtime_wrapped = True
        tool_handlers[name] = wrapped
    install_runtime_hooks._installed = True
