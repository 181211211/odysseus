"""Workspace Coding Agent lifecycle bridge.

This layer sits outside the existing runtime/security wrapper. It does not grant
new tools or bypass approvals. When normal Odysseus workspace tools are already
being executed, it creates a lightweight persisted coding task if needed and
publishes concise lifecycle events through the dispatcher's existing
``progress_cb`` channel.
"""

from __future__ import annotations

import inspect
import os
from typing import Any, Mapping

from . import runtime
from .state import CodingTaskState, TaskStatus

_WORKSPACE_TOOLS = frozenset(
    runtime._INSPECTION_TOOLS | runtime._MODIFICATION_TOOLS | runtime._SHELL_TOOLS
)
# get_workspace by itself is orientation, not enough evidence to create a task.
_IMPLICIT_START_TOOLS = _WORKSPACE_TOOLS - {"get_workspace"}


def ensure_implicit_task(
    session_id: str | None,
    workspace: str | None,
    tool_name: str,
    *,
    request: str | None = None,
) -> str | None:
    """Create task state when the existing agent starts real workspace work."""
    if not session_id or not workspace or tool_name not in _IMPLICIT_START_TOOLS:
        return runtime.active_task_path(session_id)
    current = runtime.active_task_path(session_id)
    if current:
        return current

    task_id = f"auto-{runtime._safe(str(session_id))}"
    path = os.path.join(runtime.RUNTIME_DIR, f"{runtime._safe(task_id)}.json")
    state = CodingTaskState(
        task_id=task_id,
        request=str(request or "Workspace coding task"),
        workspace=str(workspace),
        status=TaskStatus.PLANNING,
    )
    runtime._save_state(path, state.to_dict())
    runtime.register_active_task(str(session_id), task_id, path)
    return path


def status_for_tool(tool_name: str, arguments: Mapping[str, Any], current: str | None = None) -> str:
    if tool_name == "coding_task":
        return TaskStatus.PLANNING.value
    if tool_name == "coding_git" and str(arguments.get("action") or "").lower() in {"status", "diff"}:
        return TaskStatus.REVIEWING.value
    if tool_name in runtime._INSPECTION_TOOLS:
        return TaskStatus.INSPECTING.value
    if tool_name in runtime._MODIFICATION_TOOLS:
        return TaskStatus.FIXING.value if current == TaskStatus.FIXING.value else TaskStatus.EDITING.value
    if tool_name in runtime._SHELL_TOOLS:
        return TaskStatus.TESTING.value if runtime._looks_like_test(arguments) else TaskStatus.EDITING.value
    return current or TaskStatus.PLANNING.value


def task_snapshot(session_id: str | None) -> dict[str, Any] | None:
    path = runtime.active_task_path(session_id)
    return runtime._load_state(path) if path else None


async def emit_status(ctx: Mapping[str, Any], session_id: str | None, status: str, tool_name: str, arguments: Mapping[str, Any]) -> None:
    callback = ctx.get("progress_cb") if isinstance(ctx, Mapping) else None
    if not callable(callback):
        return
    state = task_snapshot(session_id) or {}
    payload: dict[str, Any] = {
        "type": "coding_agent_status",
        "status": status,
        "task_id": state.get("task_id"),
        "task": state.get("request"),
        "tool": tool_name,
        "tool_calls": int(state.get("tool_calls", 0)),
        "iterations": int(state.get("iterations", 0)),
    }
    path = arguments.get("path") or arguments.get("file")
    if isinstance(path, str) and path:
        payload["path"] = path
    command = str(arguments.get("command") or arguments.get("code") or "").strip()
    if command:
        payload["command"] = command[:300]
    value = callback(payload)
    if inspect.isawaitable(value):
        await value


def _set_pre_tool_status(session_id: str | None, status: str) -> None:
    path = runtime.active_task_path(session_id)
    state = runtime._load_state(path) if path else None
    if not state:
        return
    state["status"] = status
    runtime._save_state(path, state)


def _record_iteration_for_test(session_id: str | None, tool_name: str, arguments: Mapping[str, Any]) -> None:
    if tool_name not in runtime._SHELL_TOOLS or not runtime._looks_like_test(arguments):
        return
    path = runtime.active_task_path(session_id)
    state = runtime._load_state(path) if path else None
    if not state:
        return
    state["iterations"] = int(state.get("iterations", 0)) + 1
    runtime._save_state(path, state)


def _mark_complete_if_verified(session_id: str | None, tool_name: str, arguments: Mapping[str, Any], result: Any) -> None:
    """Close implicit tasks only after successful tests and final git review."""
    if tool_name != "coding_git" or str(arguments.get("action") or "").lower() not in {"status", "diff"}:
        return
    if isinstance(result, Mapping) and (result.get("error") or result.get("blocked") or result.get("approval_required")):
        return
    path = runtime.active_task_path(session_id)
    state = runtime._load_state(path) if path else None
    if not state:
        return
    tests = state.get("tests") or []
    has_passing_test = any(isinstance(test, Mapping) and test.get("passed") is True for test in tests)
    has_failed_latest = bool(tests and isinstance(tests[-1], Mapping) and tests[-1].get("passed") is False)
    if has_passing_test and not has_failed_latest and state.get("reviewed"):
        state["status"] = TaskStatus.COMPLETED.value
        runtime._save_state(path, state)


def install_progress_hooks(tool_handlers: dict[str, Any]) -> None:
    """Add lifecycle events around the already-secured runtime handlers."""
    if getattr(install_progress_hooks, "_installed", False):
        return
    for name, handler in list(tool_handlers.items()):
        if getattr(handler, "_coding_progress_wrapped", False):
            continue

        async def wrapped(content, ctx, _handler=handler, _name=name):
            ctx = ctx if isinstance(ctx, dict) else {}
            session_id = ctx.get("session_id")
            workspace = runtime.current_workspace(ctx)
            prepared = runtime.prepare_tool_content(_name, content, workspace)
            arguments = runtime.parse_tool_arguments(_name, prepared, workspace=workspace)

            ensure_implicit_task(
                session_id,
                workspace,
                _name,
                request=ctx.get("coding_request") or ctx.get("user_request"),
            )
            state = task_snapshot(session_id) or {}
            if runtime.active_task_path(session_id):
                status = status_for_tool(_name, arguments, str(state.get("status") or ""))
                _set_pre_tool_status(session_id, status)
                _record_iteration_for_test(session_id, _name, arguments)
                await emit_status(ctx, session_id, status, _name, arguments)

            result = await _handler(content, ctx)

            if runtime.active_task_path(session_id):
                _mark_complete_if_verified(session_id, _name, arguments, result)
                latest = task_snapshot(session_id) or {}
                final_status = str(latest.get("status") or status_for_tool(_name, arguments))
                if isinstance(result, Mapping) and (result.get("blocked") or result.get("approval_required")):
                    final_status = TaskStatus.WAITING_APPROVAL.value if result.get("approval_required") else TaskStatus.PAUSED.value
                await emit_status(ctx, session_id, final_status, _name, arguments)
            return result

        wrapped._coding_progress_wrapped = True
        tool_handlers[name] = wrapped
    install_progress_hooks._installed = True
