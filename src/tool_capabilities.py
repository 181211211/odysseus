"""Deterministic capability metadata for agent tools.

Model output requests an action; it never supplies the authority for that
action. This module classifies the effects of each built-in tool and applies
run-local integrity gates before dispatch.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from src.tool_approval_scopes import CHAT_SESSION_APPROVAL_CONTEXT_MARKER
from src.tool_security import BUILTIN_EMAIL_TOOLS


class ToolEffect(str, Enum):
    READ_PUBLIC = "read_public"
    READ_WORKSPACE = "read_workspace"
    READ_PRIVATE = "read_private"
    WRITE_WORKSPACE = "write_workspace"
    WRITE_PRIVATE = "write_private"
    EXECUTE_CODE = "execute_code"
    BROKERED_NETWORK_READ = "brokered_network_read"
    NETWORK_EGRESS = "network_egress"
    EXTERNAL_SIDE_EFFECT = "external_side_effect"
    UI_SIDE_EFFECT = "ui_side_effect"
    ADMIN_CHANGE = "admin_change"
    DESTRUCTIVE = "destructive"
    USER_INTERACTION = "user_interaction"


class ResultIntegrity(str, Enum):
    SYSTEM = "system"
    WORKSPACE_UNTRUSTED = "workspace_untrusted"
    EXTERNAL_UNTRUSTED = "external_untrusted"


@dataclass(frozen=True)
class ToolCapabilities:
    effects: frozenset[ToolEffect]
    result_integrity: ResultIntegrity = ResultIntegrity.SYSTEM
    known: bool = True


def _capabilities(*effects: ToolEffect, result_integrity: ResultIntegrity = ResultIntegrity.SYSTEM) -> ToolCapabilities:
    return ToolCapabilities(frozenset(effects), result_integrity)


_REGISTRY: dict[str, ToolCapabilities] = {}


def _register(names: Iterable[str], *effects: ToolEffect, result_integrity: ResultIntegrity = ResultIntegrity.SYSTEM) -> None:
    capabilities = _capabilities(*effects, result_integrity=result_integrity)
    for name in names:
        if name in _REGISTRY:
            raise RuntimeError(f"Duplicate tool capability classification: {name}")
        _REGISTRY[name] = capabilities


_register({"ask_user", "update_plan"}, ToolEffect.USER_INTERACTION)
_register({"list_cached_models", "list_cookbook_servers", "list_downloads", "list_models", "list_serve_presets", "list_served_models"}, ToolEffect.READ_PRIVATE, result_integrity=ResultIntegrity.EXTERNAL_UNTRUSTED)
_register({"search_hf_models", "web_search"}, ToolEffect.BROKERED_NETWORK_READ, result_integrity=ResultIntegrity.EXTERNAL_UNTRUSTED)
_register({"web_fetch"}, ToolEffect.BROKERED_NETWORK_READ, ToolEffect.NETWORK_EGRESS, result_integrity=ResultIntegrity.EXTERNAL_UNTRUSTED)
_register({"get_workspace", "glob", "grep", "ls", "read_file", "coding_inspect", "coding_git"}, ToolEffect.READ_WORKSPACE, result_integrity=ResultIntegrity.WORKSPACE_UNTRUSTED)
_register({"bash", "manage_bg_jobs", "python"}, ToolEffect.EXECUTE_CODE, result_integrity=ResultIntegrity.WORKSPACE_UNTRUSTED)
_register({"apply_patch", "edit_file", "write_file"}, ToolEffect.WRITE_WORKSPACE, result_integrity=ResultIntegrity.WORKSPACE_UNTRUSTED)
_register({"coding_task"}, ToolEffect.WRITE_PRIVATE, result_integrity=ResultIntegrity.SYSTEM)
_register({"create_document", "manage_calendar", "manage_contact", "manage_documents", "manage_memory", "manage_notes", "manage_research", "manage_session", "manage_skills", "manage_tasks", "suggest_document", "todowrite"}, ToolEffect.WRITE_PRIVATE)
_register({"ai_draft_email_reply", "create_session", "draft_email", "draft_email_reply"}, ToolEffect.WRITE_PRIVATE, result_integrity=ResultIntegrity.EXTERNAL_UNTRUSTED)
_register({"edit_document", "update_document"}, ToolEffect.WRITE_PRIVATE, result_integrity=ResultIntegrity.EXTERNAL_UNTRUSTED)
_register({"pipeline", "send_to_session", "chat_with_model", "ask_teacher"}, ToolEffect.NETWORK_EGRESS, result_integrity=ResultIntegrity.EXTERNAL_UNTRUSTED)
_register({"download_attachment"}, ToolEffect.READ_PRIVATE, ToolEffect.WRITE_WORKSPACE, result_integrity=ResultIntegrity.EXTERNAL_UNTRUSTED)
_register({"edit_image", "generate_image", "trigger_research"}, ToolEffect.NETWORK_EGRESS, ToolEffect.WRITE_PRIVATE, result_integrity=ResultIntegrity.EXTERNAL_UNTRUSTED)
_register({"archive_email", "bulk_email", "mark_email_read", "reply_to_email", "send_email", "unsubscribe_email"}, ToolEffect.EXTERNAL_SIDE_EFFECT, result_integrity=ResultIntegrity.EXTERNAL_UNTRUSTED)
_register({"delete_email"}, ToolEffect.EXTERNAL_SIDE_EFFECT, ToolEffect.DESTRUCTIVE, result_integrity=ResultIntegrity.EXTERNAL_UNTRUSTED)
_register({"ui_control"}, ToolEffect.UI_SIDE_EFFECT, result_integrity=ResultIntegrity.EXTERNAL_UNTRUSTED)
_register({"adopt_served_model", "cancel_download", "download_model", "serve_model", "serve_preset", "stop_served_model", "vault_unlock"}, ToolEffect.ADMIN_CHANGE, result_integrity=ResultIntegrity.EXTERNAL_UNTRUSTED)
_register({"api_call", "app_api", "manage_endpoints", "manage_mcp", "manage_settings", "manage_tokens", "manage_webhooks"}, ToolEffect.ADMIN_CHANGE, result_integrity=ResultIntegrity.EXTERNAL_UNTRUSTED)

TOOL_CAPABILITIES: Mapping[str, ToolCapabilities] = MappingProxyType(dict(_REGISTRY))
KNOWN_CAPABILITY_TOOLS = frozenset(TOOL_CAPABILITIES)

_UNKNOWN_CAPABILITIES = ToolCapabilities(
    frozenset({ToolEffect.READ_PRIVATE, ToolEffect.WRITE_WORKSPACE, ToolEffect.WRITE_PRIVATE, ToolEffect.EXECUTE_CODE, ToolEffect.NETWORK_EGRESS, ToolEffect.EXTERNAL_SIDE_EFFECT, ToolEffect.ADMIN_CHANGE, ToolEffect.DESTRUCTIVE}),
    ResultIntegrity.EXTERNAL_UNTRUSTED,
    known=False,
)
_BROWSER_MCP_READ_CAPABILITIES = _capabilities(ToolEffect.BROKERED_NETWORK_READ, result_integrity=ResultIntegrity.EXTERNAL_UNTRUSTED)
_BROWSER_MCP_READ_TOOLS = frozenset({"mcp__builtin_browser__browser_console_messages", "mcp__builtin_browser__browser_network_requests", "mcp__builtin_browser__browser_snapshot", "mcp__builtin_browser__browser_take_screenshot"})


def capabilities_for_tool(tool_name: Any) -> ToolCapabilities:
    if not isinstance(tool_name, str) or not tool_name:
        return _UNKNOWN_CAPABILITIES
    capabilities = TOOL_CAPABILITIES.get(tool_name)
    if capabilities is not None:
        return capabilities
    if tool_name.startswith("mcp__email__"):
        bare_name = tool_name[len("mcp__email__"):]
        capabilities = TOOL_CAPABILITIES.get(bare_name)
        if bare_name in BUILTIN_EMAIL_TOOLS and capabilities is not None:
            return capabilities
    if tool_name in _BROWSER_MCP_READ_TOOLS:
        return _BROWSER_MCP_READ_CAPABILITIES
    return _UNKNOWN_CAPABILITIES


_PRIVATE_ACTION_READS: Mapping[str, frozenset[str]] = MappingProxyType({
    "manage_calendar": frozenset({"list_calendars", "list_events"}),
    "manage_contact": frozenset({"list"}),
    "manage_documents": frozenset({"list", "read", "view", "open", "get"}),
    "manage_memory": frozenset({"list", "search"}),
    "manage_notes": frozenset({"list", "search", "find", "view"}),
    "manage_research": frozenset({"list", "read", "open", "view", "get"}),
    "manage_session": frozenset({"list", "switch", "open", "select", "view"}),
    "manage_skills": frozenset({"list", "index", "view", "view_ref", "search"}),
    "manage_tasks": frozenset({"list"}),
})

_PRIVATE_ACTION_WRITES: Mapping[str, frozenset[str]] = MappingProxyType({
    "manage_calendar": frozenset({"create_event", "update_event", "delete_event"}),
    "manage_contact": frozenset({"add", "update", "edit", "delete"}),
    "manage_documents": frozenset({"delete", "tidy"}),
    "manage_memory": frozenset({"add", "edit", "delete"}),
    "manage_notes": frozenset({"add", "update", "delete", "toggle_item"}),
    "manage_research": frozenset({"delete"}),
    "manage_session": frozenset({"rename", "archive", "unarchive", "delete", "important", "unimportant", "truncate", "fork"}),
    "manage_skills": frozenset({"add", "edit", "patch", "publish", "delete"}),
    "manage_tasks": frozenset({"create", "edit", "delete", "pause", "resume", "run"}),
})

_ACTION_DESTRUCTIVE: Mapping[str, frozenset[str]] = MappingProxyType({
    "manage_calendar": frozenset({"delete_event"}),
    "manage_contact": frozenset({"delete"}),
    "manage_documents": frozenset({"delete", "tidy"}),
    "manage_memory": frozenset({"delete"}),
    "manage_notes": frozenset({"delete"}),
    "manage_research": frozenset({"delete"}),
    "manage_session": frozenset({"delete", "truncate"}),
    "manage_skills": frozenset({"delete"}),
    "manage_tasks": frozenset({"delete"}),
})


def capabilities_for_action(tool_name: Any, content: Any) -> ToolCapabilities:
    base = capabilities_for_tool(tool_name)
    if not isinstance(tool_name, str) or not isinstance(content, str):
        return base
    try:
        args = json.loads(content) if content.strip().startswith("{") else {}
    except (json.JSONDecodeError, TypeError):
        return base
    if not isinstance(args, dict):
        return base
    action = str(args.get("action") or "").lower()
    reads = _PRIVATE_ACTION_READS.get(tool_name, frozenset())
    writes = _PRIVATE_ACTION_WRITES.get(tool_name, frozenset())
    destructive = _ACTION_DESTRUCTIVE.get(tool_name, frozenset())
    if action in reads:
        return _capabilities(ToolEffect.READ_PRIVATE, result_integrity=base.result_integrity)
    if action in writes:
        effects = {ToolEffect.WRITE_PRIVATE}
        if action in destructive:
            effects.add(ToolEffect.DESTRUCTIVE)
        return _capabilities(*effects, result_integrity=base.result_integrity)
    return base


@dataclass
class ToolRunSecurityContext:
    """Run-local integrity state shared by the agent loop and dispatcher."""
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    external_untrusted_context_seen: bool = False
    workspace_untrusted_context_seen: bool = False
    observed_tools: list[str] = field(default_factory=list)

    def observe_tool_result(self, tool_name: Any, result: Any, content: Any = None) -> None:
        name = str(tool_name or "")
        self.observed_tools.append(name)
        capabilities = capabilities_for_action(name, content)
        if capabilities.result_integrity is ResultIntegrity.EXTERNAL_UNTRUSTED:
            self.external_untrusted_context_seen = True
        elif capabilities.result_integrity is ResultIntegrity.WORKSPACE_UNTRUSTED:
            self.workspace_untrusted_context_seen = True

    def decision_for(self, tool_name: Any, content: Any) -> Any:
        from dataclasses import dataclass

        @dataclass(frozen=True)
        class Decision:
            allowed: bool
            reason: str = ""

        capabilities = capabilities_for_action(tool_name, content)
        if capabilities.effects & {ToolEffect.EXTERNAL_SIDE_EFFECT, ToolEffect.ADMIN_CHANGE, ToolEffect.DESTRUCTIVE}:
            if self.external_untrusted_context_seen:
                return Decision(False, "High-impact action requires explicit approval after untrusted external context.")
        return Decision(True)


def blocked_tool_result(tool_name: Any, reason: str) -> tuple[str, dict[str, Any]]:
    return f"{tool_name}: BLOCKED", {"error": reason, "exit_code": 1, "blocked": True}


def tool_result_is_successful(result: Any) -> bool:
    return isinstance(result, dict) and result.get("exit_code", 1) == 0 and not result.get("blocked")


def tool_result_should_arm_gate(result: Any) -> bool:
    return isinstance(result, dict) and result.get("external_untrusted") is True


def messages_contain_external_untrusted_context(messages: Any) -> bool:
    if not isinstance(messages, list):
        return False
    return any(isinstance(m, dict) and m.get("_external_untrusted") for m in messages)


CHAT_SESSION_APPROVAL_CONTEXT_MARKER = CHAT_SESSION_APPROVAL_CONTEXT_MARKER
