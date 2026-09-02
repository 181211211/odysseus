import json

from src.coding_agent import runtime


def test_prepare_coding_inspect_injects_bound_workspace():
    content = runtime.prepare_tool_content("coding_inspect", "{}", "/tmp/project")
    assert json.loads(content) == {"workspace": "/tmp/project"}


def test_prepare_coding_git_preserves_explicit_workspace():
    content = runtime.prepare_tool_content(
        "coding_git",
        json.dumps({"action": "status", "workspace": "/explicit"}),
        "/bound",
    )
    assert json.loads(content)["workspace"] == "/explicit"


def test_prepare_non_coding_tool_is_unchanged():
    raw = "pytest -q"
    assert runtime.prepare_tool_content("bash", raw, "/tmp/project") == raw


def test_parse_json_telemetry_inherits_workspace():
    args = runtime.parse_tool_arguments("coding_git", '{"action":"diff"}', workspace="/tmp/project")
    assert args["action"] == "diff"
    assert args["workspace"] == "/tmp/project"
