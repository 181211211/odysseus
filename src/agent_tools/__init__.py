"""
agent_tools.py — Facade module.

Re-exports tool parsing, schemas, execution, and implementations
for backward compatibility. All importers continue to work unchanged.
"""

import logging
from collections import namedtuple

from src.tool_security import BUILTIN_EMAIL_TOOLS
from src.tool_utils import _truncate, get_mcp_manager, set_mcp_manager

logger = logging.getLogger(__name__)

from .subprocess_tools import BashTool, PythonTool
from .web_tools import WebSearchTool, WebFetchTool
from .filesystem_tools import ReadFileTool, WriteFileTool, EditFileTool, ApplyPatchTool, LsTool, GlobTool, GrepTool, GetWorkspaceTool
from .coding_tools import TodoWriteTool, CodingTaskTool, CodingInspectTool, CodingGitTool
from .document_tools import CreateDocumentTool, UpdateDocumentTool, EditDocumentTool, SuggestDocumentTool, ManageDocumentTool
from .interaction_tools import AskUserTool, UpdatePlanTool
from .model_interaction_tools import ChatWithModelTool, AskTeacherTool, ListModelsTool
from .bg_job_tools import ManageBgJobsTool
from .session_tools import CreateSessionTool, ListSessionsTool, SendToSessionTool, ManageSessionTool
from .admin_tools import (
    ADMIN_TOOL_HANDLERS,
    do_manage_endpoints, do_manage_mcp, do_manage_webhooks,
    do_manage_tokens, do_manage_settings,
)

TOOL_HANDLERS = {
    "bash": BashTool().execute,
    "python": PythonTool().execute,
    "web_search": WebSearchTool().execute,
    "web_fetch": WebFetchTool().execute,
    "read_file": ReadFileTool().execute,
    "write_file": WriteFileTool().execute,
    "edit_file": EditFileTool().execute,
    "apply_patch": ApplyPatchTool().execute,
    "todowrite": TodoWriteTool().execute,
    "coding_task": CodingTaskTool().execute,
    "coding_inspect": CodingInspectTool().execute,
    "coding_git": CodingGitTool().execute,
    "ls": LsTool().execute,
    "glob": GlobTool().execute,
    "grep": GrepTool().execute,
    "create_document": CreateDocumentTool().execute,
    "update_document": UpdateDocumentTool().execute,
    "edit_document": EditDocumentTool().execute,
    "suggest_document": SuggestDocumentTool().execute,
    "manage_documents": ManageDocumentTool().execute,
    "get_workspace": GetWorkspaceTool().execute,
    "ask_user": AskUserTool().execute,
    "update_plan": UpdatePlanTool().execute,
    "chat_with_model": ChatWithModelTool().execute,
    "ask_teacher": AskTeacherTool().execute,
    "list_models": ListModelsTool().execute,
    "manage_bg_jobs": ManageBgJobsTool().execute,
    "create_session": CreateSessionTool().execute,
    "list_sessions": ListSessionsTool().execute,
    "send_to_session": SendToSessionTool().execute,
    "manage_session": ManageSessionTool().execute,
}
TOOL_HANDLERS.update(ADMIN_TOOL_HANDLERS)

MAX_AGENT_ROUNDS = 50
SHELL_TIMEOUT = 60
PYTHON_TIMEOUT = 30

TOOL_TAGS = {"bash", "python", "web_search", "web_fetch", "read_file", "write_file", "edit_file",
             "apply_patch", "todowrite", "coding_task", "coding_inspect", "coding_git",
             "grep", "glob", "ls", "get_workspace", "manage_bg_jobs",
             "create_document", "update_document", "edit_document", "search_chats",
             "chat_with_model", "create_session", "list_sessions", "send_to_session",
             "pipeline", "manage_session", "manage_memory", "list_models", "ui_control",
             "generate_image", "ask_user", "update_plan", "manage_tasks", "api_call",
             "ask_teacher", "manage_skills", "suggest_document", "manage_endpoints",
             "manage_mcp", "manage_webhooks", "manage_tokens", "manage_documents",
             "manage_settings", "manage_notes", "manage_calendar", "resolve_contact",
             "manage_contact", "download_model", "serve_model", "list_served_models",
             "stop_served_model", "list_downloads", "cancel_download", "search_hf_models",
             "list_cached_models", "list_serve_presets", "serve_preset", "adopt_served_model",
             "list_cookbook_servers", "edit_image", "trigger_research", "manage_research",
             "app_api"} | BUILTIN_EMAIL_TOOLS

ToolBlock = namedtuple("ToolBlock", ["tool_type", "content"])

from src.tool_parsing import (
    parse_tool_blocks, strip_tool_blocks, _TOOL_NAME_MAP, _TOOL_BLOCK_RE,
    _TOOL_CALL_RE, _XML_TOOL_CALL_RE, _XML_INVOKE_RE, _XML_PARAM_RE,
)
from src.tool_schemas import FUNCTION_TOOL_SCHEMAS, function_call_to_tool_block
from src.tool_execution import execute_tool_block, format_tool_result
from .document_tools import set_active_document, set_active_model
from src.tool_implementations import do_search_chats, do_manage_skills, do_manage_tasks, do_api_call

FUNCTION_TOOL_SCHEMAS.extend([
    {"type": "function", "function": {"name": "coding_task", "description": "Initialize or load a bounded autonomous coding task in the active workspace. Use this at the start of a substantial repository coding request.", "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["start", "load", "status"]}, "task_id": {"type": "string"}, "request": {"type": "string"}, "workspace": {"type": "string"}, "autonomy": {"type": "string", "enum": ["safe", "balanced", "autonomous"]}, "auto_commit": {"type": "boolean"}, "auto_push": {"type": "boolean"}, "max_iterations": {"type": "integer"}, "max_tool_calls": {"type": "integer"}, "max_shell_commands": {"type": "integer"}, "max_execution_seconds": {"type": "integer"}, "max_test_retries": {"type": "integer"}}, "required": ["action"]}}},
    {"type": "function", "function": {"name": "coding_inspect", "description": "Inspect the active repository without dumping source contents. Returns bounded repository metadata, likely relevant files, and detected test commands.", "parameters": {"type": "object", "properties": {"workspace": {"type": "string"}, "limit": {"type": "integer"}}, "required": []}}},
    {"type": "function", "function": {"name": "coding_git", "description": "Read-only Git inspection for a coding task. Supports status, diff, log, and branches. Never modifies or pushes the repository.", "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["status", "diff", "log", "branches"]}, "workspace": {"type": "string"}, "staged": {"type": "boolean"}, "limit": {"type": "integer"}}, "required": ["action"]}}},
])

# Layer the Coding Agent around the normal dispatcher. Runtime accounting stays
# innermost; autonomy can reject an action before it executes; progress remains
# outermost so waiting-approval events are surfaced through the existing UI.
from src.coding_agent.runtime import install_runtime_hooks  # noqa: E402
install_runtime_hooks(TOOL_HANDLERS)
from src.coding_agent.autonomy import install_autonomy_hooks  # noqa: E402
install_autonomy_hooks(TOOL_HANDLERS)
from src.coding_agent.progress import install_progress_hooks  # noqa: E402
install_progress_hooks(TOOL_HANDLERS)

# The existing workspace chat flow already starts multi-step coding work with
# todowrite. Bridge that boundary into persistent Coding Agent state without
# introducing a parallel route or bypassing any existing tool/security layer.
from src.coding_agent.chat_bridge import install_chat_bridge  # noqa: E402
install_chat_bridge(TOOL_HANDLERS)
