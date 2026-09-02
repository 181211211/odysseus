"""Live service for starting/resuming an autonomous Coding Agent task.

The service composes existing pieces only: persisted task state, Odysseus model
resolution, the bounded autonomous loop, and the secured dispatcher bridge.
It does not create a second tool/security path.
"""

from __future__ import annotations

import inspect
import os
from typing import Any, Awaitable, Callable

from .dispatcher import DispatcherToolExecutor
from .loop import AutonomousCodingLoop, CodingLoopResult
from .model import CodingModelAdapter
from .runtime import RUNTIME_DIR, _safe, _save_state, register_active_task
from .state import CodingTaskState, TaskLimits

EventCallback = Callable[[dict[str, Any]], Awaitable[None] | None]


async def _call_optional(callback: EventCallback | None, event: dict[str, Any]) -> None:
    if callback is None:
        return
    result = callback(event)
    if inspect.isawaitable(result):
        await result


async def run_coding_task(
    *,
    request: str,
    workspace: str,
    model_spec: str,
    session_id: str,
    owner: str | None,
    security_context: Any,
    autonomy: str = "balanced",
    auto_commit: bool = False,
    auto_push: bool = False,
    limits: TaskLimits | None = None,
    disabled_tools: set[str] | None = None,
    tool_policy: Any = None,
    progress_cb: EventCallback | None = None,
    exact_approval: Any = None,
) -> CodingLoopResult:
    """Run a live coding request through the bounded autonomous loop.

    Callers must supply the same security context used by the normal agent turn.
    Tool execution is delegated to ``execute_tool_block`` by
    ``DispatcherToolExecutor``; this function never invokes handlers directly.
    """
    from .policy import AutonomyLevel

    if not request.strip():
        raise ValueError("Coding task request is required")
    if not workspace.strip():
        raise ValueError("Coding task workspace is required")
    try:
        level = AutonomyLevel(str(autonomy or "balanced").lower())
    except ValueError as exc:
        raise ValueError(f"Invalid Coding Agent autonomy level: {autonomy!r}") from exc

    task_id = f"auto-{_safe(str(session_id))}"
    state = CodingTaskState(
        task_id=task_id,
        request=request.strip(),
        workspace=workspace.strip(),
        autonomy=level.value,
        auto_commit=bool(auto_commit or auto_push),
        auto_push=bool(auto_push),
        limits=limits or TaskLimits(),
    )
    path = os.path.join(RUNTIME_DIR, f"{_safe(task_id)}.json")
    _save_state(path, state.to_dict())
    register_active_task(session_id, task_id, path)

    executor = DispatcherToolExecutor(
        workspace=state.workspace,
        session_id=session_id,
        owner=owner,
        security_context=security_context,
        disabled_tools=disabled_tools,
        tool_policy=tool_policy,
        progress_cb=progress_cb,
        exact_approval=exact_approval,
    )
    model = CodingModelAdapter(model_spec, owner=owner)

    async def persist(updated: CodingTaskState) -> None:
        _save_state(path, updated.to_dict())

    async def emit(event: dict[str, Any]) -> None:
        # Reuse the UI-control stream consumed by the Coding Agent status UI.
        await _call_optional(progress_cb, {"type": "ui_control", "data": event})

    loop = AutonomousCodingLoop(state, model, executor, persist=persist, emit=emit)
    return await loop.run()
