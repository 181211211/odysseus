"""Adapter from the autonomous coding loop to Odysseus' secured tool dispatcher.

This module is intentionally thin: it converts normalized loop tool calls into
normal Odysseus ToolBlocks and delegates to ``execute_tool_block``. It does not
call tool implementations directly and therefore keeps workspace confinement,
capability policy, exact approvals, disabled-tool policy, and other dispatcher
checks authoritative.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Mapping


_SHELL_TOOLS = {"bash", "python"}


def arguments_to_content(tool_name: str, arguments: Mapping[str, Any]) -> str:
    """Encode normalized tool arguments in the format existing handlers accept."""
    args = dict(arguments or {})
    if tool_name in _SHELL_TOOLS:
        return str(args.get("command") or args.get("code") or args.get("raw") or "")
    if tool_name == "apply_patch":
        patch = args.get("patch") or args.get("content") or args.get("raw")
        if isinstance(patch, str) and patch.strip():
            return patch
    return json.dumps(args, ensure_ascii=False)


@dataclass
class DispatcherToolExecutor:
    """Execute coding-loop tools through the normal Odysseus dispatcher."""

    workspace: str
    session_id: str | None
    owner: str | None
    security_context: Any
    disabled_tools: set[str] | None = None
    tool_policy: Any = None
    progress_cb: Any = None
    exact_approval: Any = None

    async def __call__(self, tool_name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        from src.tool_execution import execute_tool_block

        block = SimpleNamespace(
            tool_type=str(tool_name),
            content=arguments_to_content(str(tool_name), arguments),
        )
        _description, result = await execute_tool_block(
            block,
            session_id=self.session_id,
            disabled_tools=self.disabled_tools,
            owner=self.owner,
            progress_cb=self.progress_cb,
            workspace=self.workspace,
            tool_policy=self.tool_policy,
            security_context=self.security_context,
            exact_approval=self.exact_approval,
        )
        return result
