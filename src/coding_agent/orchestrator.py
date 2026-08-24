"""Coding-task orchestration primitives.

This module deliberately does not duplicate Odysseus' LLM/tool loop.  It
owns the coding-specific state machine and supplies deterministic decisions
that the existing agent loop can use when selecting tools and deciding when a
task may continue.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

from .policy import AutonomyLevel, CodingPolicy, assess_command
from .repository import RepositoryInspector
from .state import CodingTaskState, TaskStatus
from .test_detection import TestCommand, detect_test_commands


@dataclass(frozen=True)
class CodingAction:
    name: str
    status: TaskStatus
    description: str


class CodingAgentOrchestrator:
    """Bounded controller for a coding task.

    Tool execution remains in the existing Odysseus dispatcher.  Callers use
    this class to track progress, budgets, workspace inspection and safety
    decisions without putting coding-specific state into the generic loop.
    """

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

    def mark_testing(self) -> CodingAction:
        self.state.status = TaskStatus.TESTING
        self.state.iterations += 1
        return CodingAction("test", self.state.status, "Run the most relevant project tests")

    def mark_failure(self, message: str, category: str = "test_failure") -> CodingAction:
        self.state.errors.append({"message": str(message), "category": category})
        self.state.test_retries += 1
        self.state.status = TaskStatus.FIXING
        return CodingAction("fix", self.state.status, "Analyze the failure and make a targeted correction")

    def mark_completed(self) -> CodingAction:
        self.state.status = TaskStatus.COMPLETED
        return CodingAction("complete", self.state.status, "Review the diff and report verified results")

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
