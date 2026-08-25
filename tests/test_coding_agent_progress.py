import json

import pytest

from src.coding_agent import progress, runtime


def test_status_mapping_for_workspace_tools():
    assert progress.status_for_tool("read_file", {"path": "app.py"}) == "inspecting"
    assert progress.status_for_tool("edit_file", {"path": "app.py"}) == "editing"
    assert progress.status_for_tool("edit_file", {"path": "app.py"}, "fixing") == "fixing"
    assert progress.status_for_tool("bash", {"command": "pytest -q"}) == "testing"
    assert progress.status_for_tool("coding_git", {"action": "diff"}) == "reviewing"


def test_implicit_task_requires_real_workspace_action(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "RUNTIME_DIR", str(tmp_path / "tasks"))
    monkeypatch.setattr(runtime, "ACTIVE_TASKS_FILE", str(tmp_path / "tasks" / "active.json"))

    assert progress.ensure_implicit_task("s1", str(tmp_path), "get_workspace") is None
    path = progress.ensure_implicit_task("s1", str(tmp_path), "read_file", request="Inspect the project")
    assert path is not None
    with open(path, "r", encoding="utf-8") as fh:
        state = json.load(fh)
    assert state["request"] == "Inspect the project"
    assert state["workspace"] == str(tmp_path)
    assert state["status"] == "planning"


@pytest.mark.asyncio
async def test_emit_status_uses_existing_progress_callback(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "RUNTIME_DIR", str(tmp_path / "tasks"))
    monkeypatch.setattr(runtime, "ACTIVE_TASKS_FILE", str(tmp_path / "tasks" / "active.json"))
    progress.ensure_implicit_task("s2", str(tmp_path), "read_file", request="Inspect the project")
    events = []

    async def callback(event):
        events.append(event)

    await progress.emit_status(
        {"progress_cb": callback},
        "s2",
        "inspecting",
        "read_file",
        {"path": "src/app.py"},
    )
    assert events[0]["type"] == "ui_control"
    lifecycle = events[0]["data"]
    assert lifecycle["ui_event"] == "coding_agent_status"
    assert lifecycle["status"] == "inspecting"
    assert lifecycle["task"] == "Inspect the project"
    assert lifecycle["path"] == "src/app.py"


def test_final_git_review_marks_verified_task_complete(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "RUNTIME_DIR", str(tmp_path / "tasks"))
    monkeypatch.setattr(runtime, "ACTIVE_TASKS_FILE", str(tmp_path / "tasks" / "active.json"))
    path = progress.ensure_implicit_task("s3", str(tmp_path), "read_file", request="Fix the bug")
    state = runtime._load_state(path)
    state["tests"] = [{"command": "pytest -q", "exit_code": 0, "passed": True, "output": "ok"}]
    state["reviewed"] = True
    state["status"] = "reviewing"
    runtime._save_state(path, state)

    progress._mark_complete_if_verified("s3", "coding_git", {"action": "diff"}, {"output": "diff", "exit_code": 0})

    assert runtime._load_state(path)["status"] == "completed"


def test_failed_latest_test_prevents_completion(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "RUNTIME_DIR", str(tmp_path / "tasks"))
    monkeypatch.setattr(runtime, "ACTIVE_TASKS_FILE", str(tmp_path / "tasks" / "active.json"))
    path = progress.ensure_implicit_task("s4", str(tmp_path), "read_file", request="Fix the bug")
    state = runtime._load_state(path)
    state["tests"] = [
        {"command": "pytest -q", "exit_code": 0, "passed": True, "output": "ok"},
        {"command": "pytest -q", "exit_code": 1, "passed": False, "output": "failed"},
    ]
    state["reviewed"] = True
    state["status"] = "reviewing"
    runtime._save_state(path, state)

    progress._mark_complete_if_verified("s4", "coding_git", {"action": "diff"}, {"output": "diff", "exit_code": 0})

    assert runtime._load_state(path)["status"] == "reviewing"
