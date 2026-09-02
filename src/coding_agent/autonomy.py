"""Runtime autonomy gate for active Coding Agent tasks.

This is an additional policy layer around existing Odysseus tool handlers. It
never grants authority: the normal dispatcher, path confinement, capability
checks, and exact-approval system still run independently.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from . import runtime
from .policy import AutonomyLevel, CodingPolicy, assess_command


def _policy_from_state(state: Mapping[str, Any]) -> CodingPolicy:
    raw = str(state.get("autonomy") or "balanced").lower()
    try:
        level = AutonomyLevel(raw)
    except ValueError:
        level = AutonomyLevel.BALANCED
    return CodingPolicy(
        level=level,
        allow_auto_commit=bool(state.get("auto_commit", False)),
        allow_auto_push=bool(state.get("auto_push", False)),
    )


def _approval(reason: str, *, policy: str = "coding_autonomy") -> dict[str, Any]:
    return {
        "error": reason,
        "exit_code": 1,
        "blocked": True,
        "approval_required": True,
        "policy": policy,
    }


def _command_decision(command: str, policy: CodingPolicy) -> dict[str, Any] | None:
    assessment = assess_command(command, policy)
    if not assessment.allowed or assessment.requires_approval:
        return _approval(assessment.reason or "This command requires explicit approval")

    # Commits are a local Git side effect and must be explicitly enabled even in
    # autonomous mode. Push is an external side effect and always stops for
    # approval, even when auto_push is enabled for the task.
    if re.search(r"\bgit\s+commit\b", command, re.IGNORECASE) and not policy.allow_auto_commit:
        return _approval("Git commit is disabled for this Coding Agent task. Enable auto_commit or approve the action explicitly.")
    if re.search(r"\bgit\s+push\b", command, re.IGNORECASE):
        if not policy.allow_auto_push:
            return _approval("Git push is disabled for this Coding Agent task.")
        return _approval("Git push is an external side effect and requires explicit approval even when enabled.")

    # Plain removals are less catastrophic than rm -rf, but still destructive.
    # Keep them human-gated at every autonomy level.
    if re.search(r"(^|[;&|]\s*)rm\s+", command, re.IGNORECASE):
        return _approval("File deletion requires explicit approval")
    return None


def decision_for_task(state: Mapping[str, Any], tool_name: str, arguments: Mapping[str, Any]) -> dict[str, Any] | None:
    policy = _policy_from_state(state)

    if tool_name in runtime._MODIFICATION_TOOLS and policy.modification_requires_approval():
        return _approval("Safe mode requires approval before modifying workspace files")

    if tool_name in runtime._SHELL_TOOLS:
        command = str(arguments.get("command") or arguments.get("code") or "").strip()
        return _command_decision(command, policy)
    return None


def install_autonomy_hooks(tool_handlers: dict[str, Any]) -> None:
    """Wrap active-task handlers with autonomy checks.

    Install this after runtime accounting and before progress hooks so rejected
    actions still produce the normal waiting-approval lifecycle event.
    """
    if getattr(install_autonomy_hooks, "_installed", False):
        return
    for name, handler in list(tool_handlers.items()):
        if getattr(handler, "_coding_autonomy_wrapped", False):
            continue

        async def wrapped(content, ctx, _handler=handler, _name=name):
            ctx = ctx if isinstance(ctx, dict) else {}
            session_id = ctx.get("session_id")
            path = runtime.active_task_path(session_id)
            if path and _name != "coding_task":
                state = runtime._load_state(path) or {}
                workspace = runtime.current_workspace(ctx)
                prepared = runtime.prepare_tool_content(_name, content, workspace)
                arguments = runtime.parse_tool_arguments(_name, prepared, workspace=workspace)
                blocked = decision_for_task(state, _name, arguments)
                if blocked is not None:
                    return blocked
            return await _handler(content, ctx)

        wrapped._coding_autonomy_wrapped = True
        tool_handlers[name] = wrapped
    install_autonomy_hooks._installed = True
