from src.agent_model_policy import AgentToolProtocol, choose_agent_tool_protocol
from src.model_capabilities import (
    ASSERTION_VERIFIED,
    CAP_TOOL_CALL,
    CONFIDENCE_HEURISTIC,
    CONFIDENCE_PROVIDER_REPORTED,
    FAMILY_CHAT,
    FAMILY_EMBEDDING,
    SOURCE_CAPABILITY_PROBE,
    SOURCE_PROVIDER_READER,
    CapabilityAssertion,
    ModelCapability,
)


def test_non_chat_model_is_chat_only_for_agent_tools():
    capability = ModelCapability.build(family=FAMILY_EMBEDDING)
    decision = choose_agent_tool_protocol(capability)
    assert decision.protocol is AgentToolProtocol.CHAT_ONLY
    assert decision.agent_capable is False


def test_explicit_supports_tools_true_enables_native_tools():
    capability = ModelCapability.build(family=FAMILY_CHAT)
    decision = choose_agent_tool_protocol(capability, explicit_supports_tools=True)
    assert decision.protocol is AgentToolProtocol.NATIVE_TOOLS
    assert decision.native_tools_verified is True


def test_explicit_supports_tools_false_forces_text_fallback():
    capability = ModelCapability.build(
        family=FAMILY_CHAT,
        capabilities=[CAP_TOOL_CALL],
        source=SOURCE_PROVIDER_READER,
        confidence=CONFIDENCE_PROVIDER_REPORTED,
    )
    decision = choose_agent_tool_protocol(capability, explicit_supports_tools=False)
    assert decision.protocol is AgentToolProtocol.TEXT_TOOLS


def test_verified_tool_assertion_enables_native_tools():
    capability = ModelCapability.build(family=FAMILY_CHAT)
    assertion = CapabilityAssertion.build(
        capability=CAP_TOOL_CALL,
        status=ASSERTION_VERIFIED,
        source=SOURCE_CAPABILITY_PROBE,
        confidence=CONFIDENCE_PROVIDER_REPORTED,
    )
    decision = choose_agent_tool_protocol(capability, assertions=[assertion])
    assert decision.protocol is AgentToolProtocol.NATIVE_TOOLS
    assert decision.native_tools_verified is True


def test_provider_reported_tool_capability_enables_native_tools():
    capability = ModelCapability.build(
        family=FAMILY_CHAT,
        capabilities=[CAP_TOOL_CALL],
        source=SOURCE_PROVIDER_READER,
        confidence=CONFIDENCE_PROVIDER_REPORTED,
    )
    decision = choose_agent_tool_protocol(capability)
    assert decision.protocol is AgentToolProtocol.NATIVE_TOOLS


def test_heuristic_tool_capability_does_not_enable_native_tools():
    capability = ModelCapability.build(
        family=FAMILY_CHAT,
        capabilities=[CAP_TOOL_CALL],
        confidence=CONFIDENCE_HEURISTIC,
    )
    decision = choose_agent_tool_protocol(capability)
    assert decision.protocol is AgentToolProtocol.TEXT_TOOLS


def test_unknown_chat_model_keeps_text_tool_fallback():
    capability = ModelCapability.build(family=FAMILY_CHAT)
    decision = choose_agent_tool_protocol(capability)
    assert decision.protocol is AgentToolProtocol.TEXT_TOOLS
    assert decision.agent_capable is True
