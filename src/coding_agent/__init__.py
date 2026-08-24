"""Autonomous coding-agent primitives for Odysseus.

The package intentionally stays independent of the existing agent loop. It
provides task state, safety policy, repository inspection helpers, test
strategy detection, git inspection primitives, and a bounded coding-task
orchestrator that the existing agent loop can compose.
"""

from .state import CodingTaskState, TaskLimits, TaskStatus
from .policy import AutonomyLevel, CodingPolicy, assess_command
from .repository import RepositoryInspector
from .test_detection import TestCommand, detect_test_commands
from .git import GitInspector
from .orchestrator import CodingAction, CodingAgentOrchestrator

__all__ = [
    "AutonomyLevel",
    "CodingAction",
    "CodingAgentOrchestrator",
    "CodingPolicy",
    "CodingTaskState",
    "GitInspector",
    "RepositoryInspector",
    "TaskLimits",
    "TaskStatus",
    "TestCommand",
    "assess_command",
    "detect_test_commands",
]
