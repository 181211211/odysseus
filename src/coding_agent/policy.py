"""Safety policy for autonomous coding operations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class AutonomyLevel(str, Enum):
    SAFE = "safe"
    BALANCED = "balanced"
    AUTONOMOUS = "autonomous"


@dataclass(frozen=True)
class CommandAssessment:
    allowed: bool
    requires_approval: bool
    reason: str = ""


@dataclass(frozen=True)
class CodingPolicy:
    level: AutonomyLevel = AutonomyLevel.BALANCED
    allow_auto_commit: bool = False
    allow_auto_push: bool = False

    def modification_requires_approval(self) -> bool:
        return self.level is AutonomyLevel.SAFE


# Deliberately conservative.  This is a second layer beside the existing
# tool-security/approval system, not a replacement for it.
_BLOCKED_PATTERNS = (
    r"\brm\s+-[a-z]*r[a-z]*f\b",
    r"\bsudo\b",
    r"\bmkfs(?:\.[\w-]+)?\b",
    r"\bdd\s+[^\n]*\bof=/dev/",
    r"\bchmod\s+-R\b",
    r"\bdocker\s+system\s+prune\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+clean\s+-[a-z]*f[a-z]*\b",
    r"\bgit\s+push\s+[^\n]*--force(?:-with-lease)?\b",
)

_SENSITIVE_COMMAND_PATTERNS = (
    r"\bcat\s+[^\n]*(?:\.env|id_rsa|id_ed25519|credentials)\b",
    r"\b(?:printenv|env)\b",
    r"\bssh\b",
    r"\bcurl\s+[^\n]*(?:https?://|--upload-file|-d\s)",
    r"\bwget\s+",
)


def assess_command(command: str, policy: CodingPolicy) -> CommandAssessment:
    command = (command or "").strip()
    if not command:
        return CommandAssessment(False, False, "Empty shell command")

    for pattern in _BLOCKED_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return CommandAssessment(False, True, "Potentially destructive command requires explicit approval")

    for pattern in _SENSITIVE_COMMAND_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return CommandAssessment(True, True, "Command may expose credentials or cause an external side effect")

    if re.search(r"\bgit\s+push\b", command, re.IGNORECASE):
        return CommandAssessment(False, True, "Git push is disabled by default")

    if policy.level is AutonomyLevel.SAFE:
        return CommandAssessment(True, True, "Safe mode requires approval for shell execution")

    return CommandAssessment(True, False)
