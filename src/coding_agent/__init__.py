"""Autonomous coding-agent primitives for Odysseus.

The package intentionally stays independent of the existing agent loop. It
provides task state, safety policy, repository inspection helpers, test
strategy detection, git inspection primitives, bounded context selection, and
a coding-task orchestrator that the existing agent loop can compose.
"""

from .state import CodingTaskState, TaskLimits, TaskStatus
from .policy import AutonomyLevel, CodingPolicy, assess_command
from .repository import RepositoryInspector
from .test_detection import TestCommand, detect_test_commands
from .git import GitInspector
from .orchestrator import CodingAction, CodingAgentOrchestrator
from .context import select_initial_context
from .prompt import CODING_AGENT_PROMPT, coding_agent_prompt

__all__ = [
    "AutonomyLevel",
    "CODING_AGENT_PROMPT",
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
    "coding_agent_prompt",
    "detect_test_commands",
    "select_initial_context",
]
