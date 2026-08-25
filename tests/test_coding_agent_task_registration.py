import json
from pathlib import Path

import pytest

from src.agent_tools import coding_tools
from src.coding_agent import runtime


@pytest.mark.asyncio
async def test_coding_task_start_registers_active_session(tmp_path: Path, monkeypatch):
    task_dir = tmp_path / "coding_tasks"
    monkeypatch.setattr(coding_tools, "_CODING_TASK_DIR", str(task_dir))
    monkeypatch.setattr(runtime, "RUNTIME_DIR", str(task_dir))
    monkeypatch.setattr(runtime, "ACTIVE_TASKS_FILE", str(task_dir / "active_tasks.json"))

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tool = coding_tools.CodingTaskTool()

    result = await tool.execute(
        json.dumps({
            "action": "start",
            "task_id": "demo-task",
            "request": "Create a calculator",
            "workspace": str(workspace),
            "autonomy": "balanced",
        }),
        {"session_id": "session-1", "workspace": str(workspace)},
    )

    assert result["exit_code"] == 0
    assert runtime.active_task_path("session-1") == str(task_dir / "demo-task.json")

    saved = json.loads((task_dir / "demo-task.json").read_text(encoding="utf-8"))
    assert saved["task_id"] == "demo-task"
    assert saved["workspace"] == str(workspace)


@pytest.mark.asyncio
async def test_coding_task_status_rebinds_existing_task(tmp_path: Path, monkeypatch):
    task_dir = tmp_path / "coding_tasks"
    task_dir.mkdir()
    monkeypatch.setattr(coding_tools, "_CODING_TASK_DIR", str(task_dir))
    monkeypatch.setattr(runtime, "RUNTIME_DIR", str(task_dir))
    monkeypatch.setattr(runtime, "ACTIVE_TASKS_FILE", str(task_dir / "active_tasks.json"))

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (task_dir / "demo-task.json").write_text(
        json.dumps({"task_id": "demo-task", "status": "planning", "workspace": str(workspace)}),
        encoding="utf-8",
    )

    result = await coding_tools.CodingTaskTool().execute(
        json.dumps({"action": "status", "task_id": "demo-task"}),
        {"session_id": "session-2", "workspace": str(workspace)},
    )

    assert result["exit_code"] == 0
    assert result["state"]["task_id"] == "demo-task"
    assert runtime.active_task_path("session-2") == str((task_dir / "demo-task.json").resolve())
