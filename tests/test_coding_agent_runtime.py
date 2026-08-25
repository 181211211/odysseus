import json
from pathlib import Path

import pytest

from src.coding_agent import runtime


@pytest.fixture
def runtime_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(runtime, "RUNTIME_DIR", str(tmp_path / "coding_tasks"))
    monkeypatch.setattr(runtime, "ACTIVE_TASKS_FILE", str(tmp_path / "coding_tasks" / "active_tasks.json"))
    return tmp_path / "coding_tasks"


def test_register_and_resolve_active_task(runtime_dir: Path, tmp_path: Path):
    state_path = tmp_path / "task.json"
    state_path.write_text(json.dumps({"status": "planning"}), encoding="utf-8")

    runtime.register_active_task("session/one", "task-1", str(state_path))

    assert runtime.active_task_path("session/one") == str(state_path.resolve())
    runtime.clear_active_task("session/one")
    assert runtime.active_task_path("session/one") is None


def test_before_tool_enforces_tool_budget(runtime_dir: Path, tmp_path: Path):
    state_path = runtime_dir / "task.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({
        "status": "editing",
        "tool_calls": 2,
        "shell_commands": 0,
        "iterations": 0,
        "limits": {"max_tool_calls": 2, "max_shell_commands": 2, "max_iterations": 5},
        "errors": [],
    }), encoding="utf-8")
    runtime.register_active_task("s1", "t1", str(state_path))

    result = runtime.before_tool("s1", "read_file", {"path": "src/main.py"})

    assert result and result["blocked"] is True
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["status"] == "paused"


def test_after_tool_records_test_and_edit(runtime_dir: Path, tmp_path: Path):
    state_path = runtime_dir / "task.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({
        "status": "editing",
        "tool_calls": 0,
        "shell_commands": 0,
        "iterations": 1,
        "limits": {"max_tool_calls": 10, "max_shell_commands": 5, "max_iterations": 5},
        "tests": [], "errors": [], "inspected_files": [], "modified_files": [], "commands": [],
    }), encoding="utf-8")
    runtime.register_active_task("s2", "t2", str(state_path))

    runtime.after_tool("s2", "edit_file", {"path": "src/main.py"}, {"exit_code": 0, "output": "updated"})
    runtime.after_tool("s2", "bash", {"command": "pytest -q"}, {"exit_code": 1, "output": "FAILED test_x"})

    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["tool_calls"] == 2
    assert saved["shell_commands"] == 1
    assert saved["modified_files"] == ["src/main.py"]
    assert saved["status"] == "fixing"
    assert saved["tests"][0]["passed"] is False
    assert saved["test_retries"] == 1
