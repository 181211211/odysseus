import json
import os
import re
from typing import Any, Dict, List

from src.constants import DATA_DIR


_TODO_DIR = os.path.join(DATA_DIR, "agent_todos")
_CODING_TASK_DIR = os.path.join(DATA_DIR, "coding_tasks")


def _safe_session_id(value: str) -> str:
    value = value or "current"
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)[:120] or "current"


class TodoWriteTool:
    async def execute(self, content: str, ctx: dict) -> dict:
        try:
            args = json.loads(content) if (content or "").strip().startswith("{") else {"todos": []}
        except (json.JSONDecodeError, TypeError):
            return {"error": "todowrite: JSON object required", "exit_code": 1}
        todos = args.get("todos")
        if not isinstance(todos, list):
            return {"error": "todowrite: todos must be a list", "exit_code": 1}

        normalized: List[Dict[str, Any]] = []
        allowed_statuses = {"pending", "in_progress", "completed"}
        allowed_priorities = {"low", "medium", "high"}
        active_count = 0
        for item in todos:
            if not isinstance(item, dict):
                return {"error": "todowrite: each todo must be an object", "exit_code": 1}
            content_text = str(item.get("content") or item.get("text") or "").strip()
            if not content_text:
                return {"error": "todowrite: todo content required", "exit_code": 1}
            status = str(item.get("status") or "pending").strip()
            if status not in allowed_statuses:
                return {"error": f"todowrite: invalid status {status!r}", "exit_code": 1}
            if status == "in_progress":
                active_count += 1
            priority = str(item.get("priority") or "medium").strip()
            if priority not in allowed_priorities:
                priority = "medium"
            normalized.append({"content": content_text, "status": status, "priority": priority})
        if active_count > 1:
            return {"error": "todowrite: only one todo can be in_progress", "exit_code": 1}

        session_id = _safe_session_id(str(ctx.get("session_id") or args.get("session_id") or "current"))
        os.makedirs(_TODO_DIR, exist_ok=True)
        path = os.path.join(_TODO_DIR, f"{session_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"todos": normalized}, f, ensure_ascii=False, indent=2)

        lines = []
        for item in normalized:
            marker = {"pending": " ", "in_progress": ">", "completed": "x"}[item["status"]]
            lines.append(f"[{marker}] {item['content']} ({item['priority']})")
        return {"output": "Updated todo list:\n" + ("\n".join(lines) if lines else "(empty)"), "exit_code": 0, "todos": normalized}


class CodingTaskTool:
    """Create/update bounded coding-task state without duplicating the agent loop."""

    async def execute(self, content: str, ctx: dict) -> dict:
        from src.coding_agent import CodingAgentOrchestrator, CodingPolicy, CodingTaskState, TaskLimits, TaskStatus

        try:
            args = json.loads(content or "{}")
        except (json.JSONDecodeError, TypeError):
            return {"error": "coding_task: JSON object required", "exit_code": 1}
        if not isinstance(args, dict):
            return {"error": "coding_task: object required", "exit_code": 1}

        session_id = _safe_session_id(str(ctx.get("session_id") or args.get("session_id") or "current"))
        task_id = _safe_session_id(str(args.get("task_id") or session_id))
        os.makedirs(_CODING_TASK_DIR, exist_ok=True)
        path = os.path.join(_CODING_TASK_DIR, f"{task_id}.json")

        if args.get("action") == "load" and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                state_data = json.load(f)
            return {"output": "Loaded coding task state", "exit_code": 0, "state": state_data}

        workspace = str(args.get("workspace") or ctx.get("workspace") or "").strip()
        if not workspace:
            return {"error": "coding_task: an active workspace is required", "exit_code": 1}
        request = str(args.get("request") or "").strip()
        if not request:
            return {"error": "coding_task: request is required", "exit_code": 1}

        level = str(args.get("autonomy") or "balanced").lower()
        try:
            from src.coding_agent import AutonomyLevel
            autonomy = AutonomyLevel(level)
        except ValueError:
            return {"error": f"coding_task: invalid autonomy level {level!r}", "exit_code": 1}

        limits = TaskLimits(
            max_iterations=max(1, min(int(args.get("max_iterations", 20)), 100)),
            max_tool_calls=max(1, min(int(args.get("max_tool_calls", 100)), 500)),
            max_shell_commands=max(1, min(int(args.get("max_shell_commands", 40)), 200)),
            max_execution_seconds=max(30, min(int(args.get("max_execution_seconds", 1800)), 7200)),
            max_test_retries=max(1, min(int(args.get("max_test_retries", 5)), 20)),
        )
        state = CodingTaskState(task_id=task_id, request=request, workspace=workspace, limits=limits)
        orchestrator = CodingAgentOrchestrator(state, CodingPolicy(autonomy))
        action = orchestrator.begin()
        state.status = TaskStatus.PLANNING
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)
        return {
            "output": f"Coding task initialized: {task_id}. Status: {state.status.value}. Next: inspect the repository and create a plan.",
            "exit_code": 0,
            "task_id": task_id,
            "state": state.to_dict(),
            "action": {"name": action.name, "status": action.status.value, "description": action.description},
        }
