"""Persistent, bounded state for a single coding task."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    PLANNING = "planning"
    INSPECTING = "inspecting"
    EDITING = "editing"
    TESTING = "testing"
    FIXING = "fixing"
    REVIEWING = "reviewing"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


@dataclass
class TaskLimits:
    """Hard ceilings preventing an autonomous task from running forever."""

    max_iterations: int = 20
    max_tool_calls: int = 100
    max_shell_commands: int = 40
    max_execution_seconds: int = 30 * 60
    max_test_retries: int = 5


@dataclass
class CodingTaskState:
    task_id: str
    request: str
    workspace: str
    status: TaskStatus = TaskStatus.PLANNING
    plan: list[str] = field(default_factory=list)
    current_step: int = 0
    inspected_files: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    tests: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    iterations: int = 0
    tool_calls: int = 0
    shell_commands: int = 0
    test_retries: int = 0
    limits: TaskLimits = field(default_factory=TaskLimits)

    def can_continue(self) -> bool:
        return (
            self.iterations < self.limits.max_iterations
            and self.tool_calls < self.limits.max_tool_calls
            and self.shell_commands < self.limits.max_shell_commands
        )

    def record_tool_call(self, *, shell: bool = False) -> None:
        self.tool_calls += 1
        if shell:
            self.shell_commands += 1

    def add_inspected(self, path: str) -> None:
        if path not in self.inspected_files:
            self.inspected_files.append(path)

    def add_modified(self, path: str) -> None:
        if path not in self.modified_files:
            self.modified_files.append(path)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodingTaskState":
        values = dict(data)
        values["status"] = TaskStatus(values.get("status", TaskStatus.PLANNING))
        limits = values.get("limits") or {}
        values["limits"] = TaskLimits(**limits)
        return cls(**values)
