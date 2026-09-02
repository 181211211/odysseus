"""Runtime bridge from the existing workspace chat flow into Coding Agent state.

The normal Odysseus agent loop already routes substantial workspace work through
its Terminus toolset and instructs the model to maintain a todo list. This bridge
uses that existing boundary: the first successful ``todowrite`` in an active
workspace lazily creates Coding Agent task state when no task is active.
No route, security, approval, or filesystem policy is bypassed.
"""

from __future__ import annotations

import json
import os
from typing import Any, Awaitable, Callable

from src.constants import DATA_DIR

_CODING_TASK_DIR = os.path.join(DATA_DIR, "coding_tasks")


def _safe_id(value: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "current")[:120] or "current"


def _request_from_todos(content: str) -> str:
    try:
        payload = json.loads(content or "{}")
    except (json.JSONDecodeError, TypeError):
        return ""
    todos = payload.get("todos") if isinstance(payload, dict) else None
    if not isinstance(todos, list):
        return ""
    parts = []
    for item in todos:
        if not isinstance(item, dict):
            continue
        text = str(item.get("content") or item.get("text") or "").strip()
        if text:
            parts.append(text)
    return "; ".join(parts)[:4000]


def _bootstrap_task(content: str, ctx: dict) -> None:
    """Create task state once, using the already-authorized workspace context."""
    workspace = str(ctx.get("workspace") or "").strip()
    session_id = _safe_id(str(ctx.get("session_id") or "current"))
    if not workspace:
        return

    from src.coding_agent import (
        AutonomyLevel,
        CodingAgentOrchestrator,
        CodingPolicy,
        CodingTaskState,
        TaskLimits,
        TaskStatus,
        active_task_path,
        register_active_task,
    )

    if active_task_path(session_id):
        return

    request = _request_from_todos(content)
    if not request:
        return

    task_id = session_id
    path = os.path.join(_CODING_TASK_DIR, f"{task_id}.json")
    state = CodingTaskState(
        task_id=task_id,
        request=request,
        workspace=workspace,
        autonomy=AutonomyLevel.BALANCED.value,
        auto_commit=False,
        auto_push=False,
        limits=TaskLimits(),
    )
    orchestrator = CodingAgentOrchestrator(
        state,
        CodingPolicy(AutonomyLevel.BALANCED, allow_auto_commit=False, allow_auto_push=False),
    )
    orchestrator.begin()
    state.status = TaskStatus.PLANNING
    os.makedirs(_CODING_TASK_DIR, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(state.to_dict(), handle, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    register_active_task(session_id, task_id, path)


def install_chat_bridge(tool_handlers: dict[str, Callable[..., Awaitable[dict]]]) -> None:
    """Wrap the existing todo handler exactly once."""
    original = tool_handlers.get("todowrite")
    if original is None or getattr(original, "_coding_chat_bridge", False):
        return

    async def bridged(content: str, ctx: dict) -> dict[str, Any]:
        result = await original(content, ctx)
        if isinstance(result, dict) and result.get("exit_code") == 0:
            try:
                _bootstrap_task(content, ctx)
            except Exception:
                # Task lifecycle is additive. Never turn a successful existing
                # todo operation into a failed chat turn if bookkeeping fails.
                pass
        return result

    bridged._coding_chat_bridge = True  # type: ignore[attr-defined]
    tool_handlers["todowrite"] = bridged
