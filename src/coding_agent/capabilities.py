"""Additive registration for Coding Agent capabilities and tool retrieval.

The upstream capability and tool-index modules remain the sources of truth.
Coding Agent extends their mutable registries at import time instead of
replacing upstream security or retrieval behavior.
"""

from __future__ import annotations

from types import MappingProxyType

from src import tool_capabilities as _cap


_CODING_TOOL_DESCRIPTIONS = {
    "coding_task": (
        "Control an autonomous repository coding task. Start substantial code work, "
        "record a plan, inspect status, and mark completion only after tests and git "
        "review. Use for requests to implement, fix, debug, refactor, build, test, or "
        "review code in the active project/workspace."
    ),
    "coding_inspect": (
        "Inspect the active code repository efficiently without dumping all source. "
        "Returns project structure, likely relevant files, and detected test commands. "
        "Use near the start of substantial coding/debugging tasks."
    ),
    "coding_git": (
        "Read-only Git inspection for repository coding tasks: status, diff, branches, "
        "and recent commits. Use before edits when useful and always review status/diff "
        "before declaring a coding task complete."
    ),
}


def install_coding_capabilities() -> None:
    registrations = {
        "coding_task": _cap.ToolCapabilities(
            frozenset({_cap.ToolEffect.WRITE_PRIVATE}),
            _cap.ResultIntegrity.SYSTEM,
        ),
        "coding_inspect": _cap.ToolCapabilities(
            frozenset({_cap.ToolEffect.READ_WORKSPACE}),
            _cap.ResultIntegrity.WORKSPACE_UNTRUSTED,
        ),
        "coding_git": _cap.ToolCapabilities(
            frozenset({_cap.ToolEffect.READ_WORKSPACE}),
            _cap.ResultIntegrity.WORKSPACE_UNTRUSTED,
        ),
    }
    for name, capabilities in registrations.items():
        _cap._REGISTRY[name] = capabilities
    _cap.TOOL_CAPABILITIES = MappingProxyType(dict(_cap._REGISTRY))
    _cap.KNOWN_CAPABILITY_TOOLS = frozenset(_cap.TOOL_CAPABILITIES)

    # Tool retrieval is keyword/embedding based. Register the coding tools in
    # the existing index so ordinary workspace requests such as "fix the auth
    # bug" can surface Coding Agent automatically without a separate router.
    try:
        from src import tool_index as _index

        _index.BUILTIN_TOOL_DESCRIPTIONS.update(_CODING_TOOL_DESCRIPTIONS)
    except Exception:
        # Retrieval is a soft enhancement. Native schemas still exist and the
        # normal fallback prompt continues to work if the index is unavailable.
        pass
