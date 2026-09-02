"""Bridge normal Odysseus chat turns into Coding Agent mode.

Kept separate from ``agent_loop`` so activation is deterministic and easy to
unit-test. It only enriches the normal turn with trusted coding tools/directive;
execution continues through the existing agent dispatcher and security gates.
"""

from __future__ import annotations

from dataclasses import dataclass

from .activation import CodingActivation, classify_coding_request, coding_mode_directive


@dataclass(frozen=True)
class CodingChatActivation:
    activation: CodingActivation
    forced_tools: frozenset[str]
    directive: str | None


def activate_coding_chat_turn(
    text: str,
    workspace: str | None,
    forced_tools: set[str] | frozenset[str] | None = None,
) -> CodingChatActivation:
    """Return coding-mode additions for a normal chat turn.

    Existing caller-forced tools are preserved. Read-only coding requests stay
    read-only because ``classify_coding_request`` removes mutating tools before
    they are unioned here.
    """
    activation = classify_coding_request(text, workspace)
    tools = set(forced_tools or set())
    directive = None
    if activation.active:
        tools.update(activation.forced_tools)
        directive = coding_mode_directive(str(workspace), substantial=activation.substantial)
    return CodingChatActivation(activation, frozenset(tools), directive)
