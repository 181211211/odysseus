"""Capability-aware execution policy for tool-using agent modes.

This is a policy adapter over the existing ``src.model_capabilities`` metadata.
It does not discover models, call providers, or grant tool authority.  It only
chooses the safest *protocol* an agent controller should request from a model:
native structured tools, Odysseus' text/fenced fallback, or chat-only mode.

The normal dispatcher, tool policy, approvals, workspace confinement, and
security context remain authoritative for every actual tool execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from src.model_capabilities import (
    ASSERTION_VERIFIED,
    CAP_TOOL_CALL,
    CONFIDENCE_EXPLICIT,
    CONFIDENCE_PROVIDER_REPORTED,
    FAMILY_CHAT,
    CapabilityAssertion,
    ModelCapability,
)


class AgentToolProtocol(str, Enum):
    """How an agent controller should ask the selected model to use tools."""

    NATIVE_TOOLS = "native_tools"
    TEXT_TOOLS = "text_tools"
    CHAT_ONLY = "chat_only"


@dataclass(frozen=True)
class AgentModelDecision:
    protocol: AgentToolProtocol
    reason: str
    native_tools_verified: bool = False

    @property
    def agent_capable(self) -> bool:
        return self.protocol is not AgentToolProtocol.CHAT_ONLY


def choose_agent_tool_protocol(
    capability: ModelCapability,
    *,
    assertions: Iterable[CapabilityAssertion] = (),
    explicit_supports_tools: bool | None = None,
) -> AgentModelDecision:
    """Choose a conservative agent-tool protocol from canonical metadata.

    Precedence:

    1. Non-chat model families are never used for autonomous text-agent tools.
    2. An explicit endpoint ``supports_tools=False`` forces the text fallback.
    3. An explicit endpoint ``supports_tools=True`` enables native tools.
    4. A verified tool-call assertion enables native tools.
    5. Provider-reported/explicit canonical tool capability enables native tools.
    6. Otherwise chat models use the existing text/fenced fallback.

    The fallback is deliberately permissive enough for local Ollama/llama.cpp
    models that can follow Odysseus' textual tool protocol even when they do not
    expose reliable native structured tool schemas.
    """

    if capability.family != FAMILY_CHAT:
        return AgentModelDecision(
            AgentToolProtocol.CHAT_ONLY,
            f"model family {capability.family!r} is not a chat-agent family",
        )

    if explicit_supports_tools is False:
        return AgentModelDecision(
            AgentToolProtocol.TEXT_TOOLS,
            "endpoint explicitly disables native tools; use text/fenced tool fallback",
        )

    if explicit_supports_tools is True:
        return AgentModelDecision(
            AgentToolProtocol.NATIVE_TOOLS,
            "endpoint explicitly enables native tool calling",
            native_tools_verified=True,
        )

    for assertion in assertions:
        if (
            assertion.capability == CAP_TOOL_CALL
            and assertion.status == ASSERTION_VERIFIED
        ):
            return AgentModelDecision(
                AgentToolProtocol.NATIVE_TOOLS,
                "tool calling has a verified capability assertion",
                native_tools_verified=True,
            )

    if CAP_TOOL_CALL in capability.capabilities and capability.confidence in {
        CONFIDENCE_EXPLICIT,
        CONFIDENCE_PROVIDER_REPORTED,
    }:
        return AgentModelDecision(
            AgentToolProtocol.NATIVE_TOOLS,
            "canonical capability metadata reports native tool calling",
            native_tools_verified=capability.confidence == CONFIDENCE_EXPLICIT,
        )

    return AgentModelDecision(
        AgentToolProtocol.TEXT_TOOLS,
        "native tool support is unknown or insufficiently trusted; use text/fenced fallback",
    )
