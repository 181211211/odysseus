from src.coding_agent.activation import classify_coding_request, coding_mode_directive


def test_substantial_workspace_request_activates_full_coding_tools():
    result = classify_coding_request("Fix the authentication bug in this project", "/repo")
    assert result.active is True
    assert result.substantial is True
    assert result.read_only is False
    assert {"coding_task", "coding_inspect", "coding_git", "apply_patch", "bash"} <= result.forced_tools


def test_read_only_workspace_request_does_not_surface_mutating_tools():
    result = classify_coding_request("Inspect this project and find the failing tests", "/repo")
    assert result.active is True
    assert result.read_only is True
    assert "coding_inspect" in result.forced_tools
    assert "coding_task" not in result.forced_tools
    assert "apply_patch" not in result.forced_tools
    assert "bash" not in result.forced_tools


def test_no_workspace_never_auto_activates_privileged_coding_mode():
    result = classify_coding_request("Build a FastAPI application with tests", None)
    assert result.active is False
    assert not result.forced_tools


def test_non_coding_request_in_workspace_does_not_activate():
    result = classify_coding_request("Tell me a joke about APIs", "/repo")
    assert result.active is False


def test_directive_contains_security_and_lifecycle_requirements():
    directive = coding_mode_directive("/repo", substantial=True)
    assert "coding_task" in directive
    assert "status/diff" in directive
    assert "untrusted data" in directive
    assert "Do not expose secrets" in directive
