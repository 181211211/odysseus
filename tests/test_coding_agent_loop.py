from pathlib import Path

import pytest

from src.coding_agent import AutonomousCodingLoop, CodingTaskState, TaskLimits, TaskStatus


class FakeModel:
    def __init__(self, responses):
        self.responses = list(responses)

    async def complete(self, messages):
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_autonomous_loop_retries_failed_test_then_completes(tmp_path: Path):
    calls = []

    async def execute_tool(name, arguments):
        calls.append((name, arguments))
        if name == "bash" and "pytest" in arguments.get("command", ""):
            attempt = sum(1 for n, _ in calls if n == "bash")
            if attempt == 1:
                return {"exit_code": 1, "stderr": "AssertionError: expected 2, got 3"}
            return {"exit_code": 0, "stdout": "1 passed"}
        if name == "coding_git":
            return {"exit_code": 0, "stdout": " M calculator.py"}
        return {"exit_code": 0, "output": "ok"}

    model = FakeModel([
        {"content": "Inspect and implement the calculator.", "tool_calls": [{"name": "coding_inspect", "arguments": {}}]},
        {"tool_calls": [{"name": "write_file", "arguments": {"path": "calculator.py", "content": "def add(a, b): return a + b\n"}}]},
        {"tool_calls": [{"name": "bash", "arguments": {"command": "pytest -q"}}]},
        {"content": "The test failed; fix the implementation.", "tool_calls": [{"name": "edit_file", "arguments": {"path": "calculator.py", "content": "def add(a, b): return a + b\n"}}]},
        {"tool_calls": [{"name": "bash", "arguments": {"command": "pytest -q"}}]},
        {"tool_calls": [{"name": "coding_git", "arguments": {"action": "diff"}}]},
        {"content": "Completed.", "done": True},
    ])
    state = CodingTaskState(
        task_id="loop-test",
        request="Create a calculator",
        workspace=str(tmp_path),
        limits=TaskLimits(max_iterations=10, max_tool_calls=20, max_shell_commands=5, max_test_retries=3),
    )

    result = await AutonomousCodingLoop(state, model, execute_tool).run()

    assert result.status is TaskStatus.COMPLETED
    assert result.tests_passed
    assert result.reviewed
    assert state.test_retries == 1
    assert [name for name, _ in calls].count("bash") == 2


@pytest.mark.asyncio
async def test_autonomous_loop_stops_on_approval(tmp_path: Path):
    async def execute_tool(name, arguments):
        return {"approval_required": True, "error": "approval required"}

    model = FakeModel([
        {"tool_calls": [{"name": "bash", "arguments": {"command": "rm -rf ./build"}}]},
    ])
    state = CodingTaskState(
        task_id="approval-test",
        request="clean build artifacts",
        workspace=str(tmp_path),
        limits=TaskLimits(max_iterations=3, max_tool_calls=3, max_shell_commands=2),
    )

    result = await AutonomousCodingLoop(state, model, execute_tool).run()

    assert result.status is TaskStatus.WAITING_APPROVAL


@pytest.mark.asyncio
async def test_autonomous_loop_does_not_repeat_identical_failed_call(tmp_path: Path):
    calls = []

    async def execute_tool(name, arguments):
        calls.append((name, arguments))
        return {"exit_code": 1, "stderr": "still broken"}

    model = FakeModel([
        {"tool_calls": [{"name": "bash", "arguments": {"command": "pytest -q"}}]},
        {"tool_calls": [{"name": "bash", "arguments": {"command": "pytest -q"}}]},
        {"done": True, "content": "blocked"},
    ])
    state = CodingTaskState(
        task_id="repeat-test",
        request="fix tests",
        workspace=str(tmp_path),
        limits=TaskLimits(max_iterations=5, max_tool_calls=5, max_shell_commands=5, max_test_retries=3),
    )

    result = await AutonomousCodingLoop(state, model, execute_tool).run()

    assert result.status in {TaskStatus.COMPLETED, TaskStatus.PAUSED}
    assert len(calls) == 1
    assert any(error["category"] == "test_failure" for error in state.errors)
