"""Coding-task orchestration primitives.

The generic Odysseus agent loop remains responsible for LLM reasoning and
actual tool execution. This module owns deterministic coding-task state and
bounded transitions around that loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

from .policy import CodingPolicy, assess_command
from .repository import RepositoryInspector
from .state import CodingTaskState, TaskStatus
from .test_detection import TestCommand, detect_test_commands


@dataclass(frozen=True)
class CodingAction:
    name: str
    status: TaskStatus
    description: str


class CodingAgentOrchestrator:
    def __init__(self, state: CodingTaskState, policy: CodingPolicy | None = None):
        self.state = state
        self.policy = policy or CodingPolicy()
        self.started_at = monotonic()

    @property
    def inspector(self) -> RepositoryInspector:
        return RepositoryInspector(self.state.workspace)

    def begin(self) -> CodingAction:
        self.state.status = TaskStatus.INSPECTING
        return CodingAction("inspect", self.state.status, "Inspect repository structure and project conventions")

    def plan(self, steps: list[str]) -> CodingAction:
        self.state.plan = [str(step).strip() for step in steps if str(step).strip()]
        self.state.current_step = 0
        self.state.status = TaskStatus.INSPECTING
        return CodingAction("plan", self.state.status, "Create a bounded implementation plan")

    def mark_editing(self) -> CodingAction:
        self.state.status = TaskStatus.EDITING
        return CodingAction("edit", self.state.status, "Modify the smallest relevant set of files")

    def record_tool(self, tool_name: str, *, shell: bool = False) -> bool:
        if not self.can_continue():
            self.state.status = TaskStatus.PAUSED
            return False
        self.state.record_tool_call(shell=shell)
        return self.can_continue()

    def record_file_inspected(self, path: str) -> None:
        self.state.add_inspected(path)

    def record_file_modified(self, path: str) -> None:
        self.state.add_modified(path)

    def mark_testing(self) -> CodingAction:
        self.state.status = TaskStatus.TESTING
        self.state.iterations += 1
        return CodingAction("test", self.state.status, "Run the most relevant project tests")

    def record_test_result(self, command: str, exit_code: int, output: str = "") -> CodingAction:
        self.state.tests.append({
            "command": command,
            "exit_code": int(exit_code),
            "passed": int(exit_code) == 0,
            "output": str(output)[-12000:],
        })
        if int(exit_code) == 0:
            self.state.status = TaskStatus.REVIEWING
            return CodingAction("review", self.state.status, "Review the resulting changes")
        return self.mark_failure(output or f"{command} exited with code {exit_code}")

    def mark_failure(self, message: str, category: str = "test_failure") -> CodingAction:
        self.state.errors.append({"message": str(message), "category": category})
        self.state.test_retries += 1
        if self.state.test_retries >= self.state.limits.max_test_retries:
            self.state.status = TaskStatus.FAILED
            return CodingAction("blocked", self.state.status, "Test retry limit reached; user intervention may be required")
        self.state.status = TaskStatus.FIXING
        return CodingAction("fix", self.state.status, "Analyze the failure and make a targeted correction")

    def mark_completed(self) -> CodingAction:
        self.state.status = TaskStatus.COMPLETED
        return CodingAction("complete", self.state.status, "Review the diff and report verified results")

    def mark_failed(self, reason: str) -> CodingAction:
        self.state.errors.append({"message": str(reason), "category": "blocked"})
        self.state.status = TaskStatus.FAILED
        return CodingAction("blocked", self.state.status, str(reason))

    def test_commands(self) -> list[TestCommand]:
        return detect_test_commands(self.state.workspace)

    def command_assessment(self, command: str):
        return assess_command(command, self.policy)

    def can_continue(self) -> bool:
        if not self.state.can_continue():
            return False
        return monotonic() - self.started_at < self.state.limits.max_execution_seconds

    def next_step(self) -> str | None:
        if self.state.current_step >= len(self.state.plan):
            return None
        return self.state.plan[self.state.current_step]

    def complete_step(self) -> None:
        if self.state.current_step < len(self.state.plan):
            self.state.current_step += 1
