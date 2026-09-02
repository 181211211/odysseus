import json

import pytest

from src.coding_agent.dispatcher import DispatcherToolExecutor, arguments_to_content


def test_arguments_to_content_uses_plain_shell_command():
    assert arguments_to_content("bash", {"command": "pytest -q"}) == "pytest -q"
    assert arguments_to_content("python", {"code": "print(1)"}) == "print(1)"


def test_arguments_to_content_uses_raw_patch():
    patch = "*** Begin Patch\n*** Update File: a.py\n@@\n-x\n+y\n*** End Patch"
    assert arguments_to_content("apply_patch", {"patch": patch}) == patch


def test_arguments_to_content_json_encodes_structured_tools():
    encoded = arguments_to_content("edit_file", {"path": "a.py", "old_string": "x", "new_string": "y"})
    assert json.loads(encoded) == {"path": "a.py", "old_string": "x", "new_string": "y"}


@pytest.mark.asyncio
async def test_executor_routes_through_normal_dispatcher(monkeypatch):
    seen = {}

    async def fake_execute(block, **kwargs):
        seen["tool"] = block.tool_type
        seen["content"] = block.content
        seen.update(kwargs)
        return "read_file: OK", {"output": "hello", "exit_code": 0}

    import src.tool_execution as tool_execution
    monkeypatch.setattr(tool_execution, "execute_tool_block", fake_execute)

    security_context = object()
    executor = DispatcherToolExecutor(
        workspace="/repo",
        session_id="session-1",
        owner="owner-1",
        security_context=security_context,
        disabled_tools={"web_search"},
    )
    result = await executor("read_file", {"path": "src/main.py"})

    assert result == {"output": "hello", "exit_code": 0}
    assert seen["tool"] == "read_file"
    assert json.loads(seen["content"]) == {"path": "src/main.py"}
    assert seen["workspace"] == "/repo"
    assert seen["session_id"] == "session-1"
    assert seen["owner"] == "owner-1"
    assert seen["security_context"] is security_context
    assert seen["disabled_tools"] == {"web_search"}
