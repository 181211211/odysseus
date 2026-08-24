from pathlib import Path

from src.coding_agent import CodingAgentOrchestrator, CodingTaskState, TaskLimits, TaskStatus


def make_state(tmp_path: Path) -> CodingTaskState:
    return CodingTaskState(
        task_id="test-task",
        request="Create a calculator",
        workspace=str(tmp_path),
        limits=TaskLimits(max_iterations=3, max_tool_calls=3, max_shell_commands=2, max_test_retries=2),
    )


def test_tool_budget_stops_orchestrator(tmp_path: Path):
    agent = CodingAgentOrchestrator(make_state(tmp_path))
    assert agent.record_tool("read_file")
    assert agent.record_tool("edit_file")
    assert not agent.record_tool("bash", shell=True)
    assert agent.state.tool_calls == 3


def test_failed_test_transitions_to_fixing(tmp_path: Path):
    agent = CodingAgentOrchestrator(make_state(tmp_path))
    agent.mark_testing()
    action = agent.record_test_result("pytest", 1, "AssertionError")
    assert action.status is TaskStatus.FIXING
    assert agent.state.test_retries == 1


def test_retry_limit_marks_task_failed(tmp_path: Path):
    agent = CodingAgentOrchestrator(make_state(tmp_path))
    agent.mark_failure("first")
    action = agent.mark_failure("second")
    assert action.status is TaskStatus.FAILED
