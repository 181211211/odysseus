"""Additive capability registration for Coding Agent tools.

The upstream capability module remains the security source of truth. Coding
Agent tools are registered here at import time so the feature can extend that
registry without replacing upstream security classifications.
"""

from __future__ import annotations

from types import MappingProxyType

from src import tool_capabilities as _cap


def install_coding_capabilities() -> None:
    registrations = {
        "coding_task": _cap.ToolCapabilities(frozenset({_cap.ToolEffect.WRITE_PRIVATE}), _cap.ResultIntegrity.SYSTEM),
        "coding_inspect": _cap.ToolCapabilities(frozenset({_cap.ToolEffect.READ_WORKSPACE}), _cap.ResultIntegrity.WORKSPACE_UNTRUSTED),
        "coding_git": _cap.ToolCapabilities(frozenset({_cap.ToolEffect.READ_WORKSPACE}), _cap.ResultIntegrity.WORKSPACE_UNTRUSTED),
    }
    for name, capabilities in registrations.items():
        _cap._REGISTRY[name] = capabilities
    _cap.TOOL_CAPABILITIES = MappingProxyType(dict(_cap._REGISTRY))
    _cap.KNOWN_CAPABILITY_TOOLS = frozenset(_cap.TOOL_CAPABILITIES)
