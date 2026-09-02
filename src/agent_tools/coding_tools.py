import json
import os
import re
from typing import Any, Dict, List

from src.constants import DATA_DIR
from src.coding_agent.capabilities import install_coding_capabilities

# Register additive Coding Agent capabilities when this tool module loads.
install_coding_capabilities()

_TODO_DIR = os.path.join(DATA_DIR, "agent_todos")
_CODING_TASK_DIR = os.path.join(DATA_DIR, "coding_tasks")


def _safe_session_id(value: str) -> str:
    value = value or "current"
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)[:120] or "current"


def _task_path(task_id: str) -> str:
    return os.path.join(_CODING_TASK_DIR, f"{_safe_session_id(task_id)}.json")


def _save_state(path: str, state: dict) -> None:
    os.makedirs(_CODING_TASK_DIR, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


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
            active_count += status == "in_progress"
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
    async def execute(self, content: str, ctx: dict) -> dict:
        from src.coding_agent import CodingAgentOrchestrator, CodingPolicy, CodingTaskState, TaskLimits, TaskStatus, AutonomyLevel, register_active_task
        try:
            args = json.loads(content or "{}")
        except (json.JSONDecodeError, TypeError):
            return {"error": "coding_task: JSON object required", "exit_code": 1}
        if not isinstance(args, dict):
            return {"error": "coding_task: object required", "exit_code": 1}
        session_id = _safe_session_id(str(ctx.get("session_id") or args.get("session_id") or "current"))
        task_id = _safe_session_id(str(args.get("task_id") or session_id))
        path = _task_path(task_id)
        action_name = str(args.get("action") or "start").lower()
        if action_name in {"load", "status"}:
            if not os.path.exists(path):
                return {"error": f"coding_task: task {task_id!r} does not exist", "exit_code": 1}
            with open(path, "r", encoding="utf-8") as f:
                state_data = json.load(f)
            register_active_task(session_id, task_id, path)
            return {"output": "Loaded coding task state", "exit_code": 0, "state": state_data, "task_id": task_id}
        workspace = str(args.get("workspace") or ctx.get("workspace") or "").strip()
        if not workspace:
            return {"error": "coding_task: an active workspace is required", "exit_code": 1}
        request = str(args.get("request") or "").strip()
        if not request:
            return {"error": "coding_task: request is required", "exit_code": 1}
        level = str(args.get("autonomy") or "balanced").lower()
        try:
            autonomy = AutonomyLevel(level)
        except ValueError:
            return {"error": f"coding_task: invalid autonomy level {level!r}", "exit_code": 1}
        auto_commit = bool(args.get("auto_commit", False))
        auto_push = bool(args.get("auto_push", False))
        # Push is intentionally opt-in independently of the autonomy level.
        # Enabling it also implies commit permission, but neither flag bypasses
        # the existing tool-security/exact-approval layer.
        if auto_push:
            auto_commit = True
        try:
            limits = TaskLimits(
                max_iterations=max(1, min(int(args.get("max_iterations", 20)), 100)),
                max_tool_calls=max(1, min(int(args.get("max_tool_calls", 100)), 500)),
                max_shell_commands=max(1, min(int(args.get("max_shell_commands", 40)), 200)),
                max_execution_seconds=max(30, min(int(args.get("max_execution_seconds", 1800)), 7200)),
                max_test_retries=max(1, min(int(args.get("max_test_retries", 5)), 20)),
            )
        except (TypeError, ValueError):
            return {"error": "coding_task: numeric limits must be valid integers", "exit_code": 1}
        state = CodingTaskState(
            task_id=task_id,
            request=request,
            workspace=workspace,
            autonomy=autonomy.value,
            auto_commit=auto_commit,
            auto_push=auto_push,
            limits=limits,
        )
        orchestrator = CodingAgentOrchestrator(
            state,
            CodingPolicy(autonomy, allow_auto_commit=auto_commit, allow_auto_push=auto_push),
        )
        action = orchestrator.begin()
        state.status = TaskStatus.PLANNING
        _save_state(path, state.to_dict())
        register_active_task(session_id, task_id, path)
        return {"output": f"Coding task initialized: {task_id}. Status: {state.status.value}. Autonomy: {state.autonomy}. Next: inspect the repository and create a plan.", "exit_code": 0, "task_id": task_id, "state": state.to_dict(), "action": {"name": action.name, "status": action.status.value, "description": action.description}}


class CodingInspectTool:
    """Return bounded repository metadata without dumping source into context."""
    async def execute(self, content: str, ctx: dict) -> dict:
        from src.coding_agent import RepositoryInspector, detect_test_commands, select_initial_context
        try:
            args = json.loads(content or "{}")
        except (json.JSONDecodeError, TypeError):
            return {"error": "coding_inspect: JSON object required", "exit_code": 1}
        if not isinstance(args, dict):
            return {"error": "coding_inspect: object required", "exit_code": 1}
        workspace = str(args.get("workspace") or ctx.get("workspace") or "").strip()
        if not workspace:
            return {"error": "coding_inspect: workspace is required", "exit_code": 1}
        try:
            inspector = RepositoryInspector(workspace)
            summary = inspector.summary()
            limit = max(1, min(int(args.get("limit", 40)), 100))
            tests = detect_test_commands(workspace)
            candidates = select_initial_context(workspace, limit=limit)
        except (OSError, ValueError, TypeError) as exc:
            return {"error": f"coding_inspect: {exc}", "exit_code": 1}
        return {
            "output": "Repository inspected without loading source contents.",
            "exit_code": 0,
            "summary": {"root": summary.root, "files": summary.files, "directories": summary.directories, "top_level": list(summary.top_level)},
            "test_commands": [{"command": t.command, "reason": t.reason} for t in tests],
            "candidate_files": candidates,
        }


class CodingGitTool:
    """Read-only Git inspection for coding tasks."""
    async def execute(self, content: str, ctx: dict) -> dict:
        from src.coding_agent import GitInspector
        try:
            args = json.loads(content or "{}")
        except (json.JSONDecodeError, TypeError):
            return {"error": "coding_git: JSON object required", "exit_code": 1}
        if not isinstance(args, dict):
            return {"error": "coding_git: object required", "exit_code": 1}
        workspace = str(args.get("workspace") or ctx.get("workspace") or "").strip()
        if not workspace:
            return {"error": "coding_git: workspace is required", "exit_code": 1}
        action = str(args.get("action") or "status").lower()
        try:
            git = GitInspector(workspace)
            if action == "status":
                result = git.status()
            elif action == "diff":
                result = git.diff(bool(args.get("staged")))
            elif action == "log":
                result = git.log(int(args.get("limit", 10)))
            elif action == "branches":
                result = git.branches()
            else:
                return {"error": f"coding_git: unsupported read-only action {action!r}", "exit_code": 1}
        except (OSError, ValueError, TypeError) as exc:
            return {"error": f"coding_git: {exc}", "exit_code": 1}
        return {"output": result.stdout, "stderr": result.stderr, "exit_code": result.returncode, "action": action}
