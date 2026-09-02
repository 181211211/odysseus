from src.coding_agent.chat_activation import activate_coding_chat_turn


def test_mutating_workspace_request_activates_full_coding_mode():
    result = activate_coding_chat_turn("Fix the authentication bug in this project", "/repo")

    assert result.activation.active is True
    assert result.activation.substantial is True
    assert "coding_task" in result.forced_tools
    assert "apply_patch" in result.forced_tools
    assert "bash" in result.forced_tools
    assert result.directive is not None
    assert "CODING AGENT MODE" in result.directive
    assert "/repo" in result.directive


def test_read_only_workspace_request_does_not_gain_mutating_tools():
    result = activate_coding_chat_turn("Inspect this project and find the failing tests", "/repo")

    assert result.activation.active is True
    assert result.activation.read_only is True
    assert "read_file" in result.forced_tools
    assert "grep" in result.forced_tools
    assert "write_file" not in result.forced_tools
    assert "apply_patch" not in result.forced_tools
    assert "bash" not in result.forced_tools
    assert "coding_task" not in result.forced_tools


def test_no_workspace_never_activates_privileged_coding_tools():
    result = activate_coding_chat_turn("Fix the authentication bug in this project", None, {"web_search"})

    assert result.activation.active is False
    assert result.forced_tools == frozenset({"web_search"})
    assert result.directive is None


def test_existing_forced_tools_are_preserved():
    result = activate_coding_chat_turn("Build a FastAPI application", "/repo", {"web_search"})

    assert result.activation.active is True
    assert "web_search" in result.forced_tools
    assert "coding_task" in result.forced_tools
