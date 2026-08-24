import json
from pathlib import Path

import pytest

from src.agent_tools import FUNCTION_TOOL_SCHEMAS, TOOL_HANDLERS
from src.coding_agent import AutonomyLevel, CodingPolicy, CodingTaskState, RepositoryInspector, TaskLimits, TaskStatus, assess_command, detect_test_commands


def test_task_state_enforces_budgets():
    state = CodingTaskState(task_id="t1", request="test", workspace="/tmp", limits=TaskLimits(max_iterations=1, max_tool_calls=1, max_shell_commands=1))
    assert state.can_continue()
    state.record_tool_call(shell=True)
    assert not state.can_continue()
    assert state.to_dict()["status"] == TaskStatus.PLANNING.value


def test_dangerous_commands_require_approval():
    result = assess_command("git reset --hard HEAD", CodingPolicy(AutonomyLevel.AUTONOMOUS))
    assert not result.allowed and result.requires_approval


def test_push_is_not_allowed_by_default():
    result = assess_command("git push origin main", CodingPolicy())
    assert not result.allowed and result.requires_approval


def test_safe_mode_requires_shell_approval():
    result = assess_command("pytest", CodingPolicy(AutonomyLevel.SAFE))
    assert result.allowed and result.requires_approval


def test_test_detection(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    commands = detect_test_commands(tmp_path)
    assert commands and commands[0].command == "pytest"


def test_repository_inspector_ignores_heavy_directories(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.js").write_text("x", encoding="utf-8")
    inspector = RepositoryInspector(tmp_path)
    assert "src/main.py" in list(inspector.iter_files())
    assert "node_modules/junk.js" not in list(inspector.iter_files())


def test_coding_tools_are_registered_for_native_calls():
    assert {"coding_task", "coding_inspect", "coding_git"}.issubset(TOOL_HANDLERS)
    names = {item["function"]["name"] for item in FUNCTION_TOOL_SCHEMAS}
    assert {"coding_task", "coding_inspect", "coding_git"}.issubset(names)


@pytest.mark.asyncio
async def test_coding_task_persists_state(tmp_path: Path, monkeypatch):
    import src.agent_tools.coding_tools as coding_tools
    monkeypatch.setattr(coding_tools, "_CODING_TASK_DIR", str(tmp_path / "tasks"))
    result = await coding_tools.CodingTaskTool().execute(json.dumps({"action": "start", "task_id": "calculator", "request": "create calculator tests", "workspace": str(tmp_path), "autonomy": "balanced"}), {"session_id": "test"})
    assert result["exit_code"] == 0
    assert result["state"]["status"] == "planning"
    assert (tmp_path / "tasks" / "calculator.json").exists()


@pytest.mark.asyncio
async def test_coding_inspect_is_bounded(tmp_path: Path):
    import src.agent_tools.coding_tools as coding_tools
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    result = await coding_tools.CodingInspectTool().execute(json.dumps({"workspace": str(tmp_path), "limit": 10}), {})
    assert result["exit_code"] == 0
    assert result["test_commands"][0]["command"] == "pytest"
    assert "src/main.py" in result["candidate_files"]


def test_coding_prompt_rejects_repository_as_instruction():
    from src.coding_agent import CODING_AGENT_PROMPT
    assert "untrusted DATA" in CODING_AGENT_PROMPT
    assert "Never claim success" in CODING_AGENT_PROMPT
