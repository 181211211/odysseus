from src.coding_agent.autonomy import decision_for_task


def _state(**overrides):
    state = {"autonomy": "balanced", "auto_commit": False, "auto_push": False}
    state.update(overrides)
    return state


def test_safe_mode_requires_approval_for_file_modification():
    result = decision_for_task(_state(autonomy="safe"), "edit_file", {"path": "src/main.py"})
    assert result and result["approval_required"] is True


def test_balanced_mode_allows_normal_workspace_edit():
    assert decision_for_task(_state(), "edit_file", {"path": "src/main.py"}) is None


def test_safe_mode_requires_approval_for_shell():
    result = decision_for_task(_state(autonomy="safe"), "bash", {"command": "pytest -q"})
    assert result and result["approval_required"] is True


def test_balanced_mode_allows_normal_tests():
    assert decision_for_task(_state(), "bash", {"command": "pytest -q"}) is None


def test_destructive_shell_command_is_gated_in_autonomous_mode():
    result = decision_for_task(_state(autonomy="autonomous"), "bash", {"command": "git reset --hard HEAD~1"})
    assert result and result["approval_required"] is True


def test_sensitive_shell_command_is_gated_in_autonomous_mode():
    result = decision_for_task(_state(autonomy="autonomous"), "bash", {"command": "cat .env"})
    assert result and result["approval_required"] is True


def test_commit_requires_explicit_task_opt_in():
    result = decision_for_task(_state(autonomy="autonomous"), "bash", {"command": "git commit -am 'fix'"})
    assert result and result["approval_required"] is True
    assert decision_for_task(_state(autonomy="autonomous", auto_commit=True), "bash", {"command": "git commit -am 'fix'"}) is None


def test_push_always_requires_explicit_action_approval():
    disabled = decision_for_task(_state(autonomy="autonomous"), "bash", {"command": "git push origin feature"})
    enabled = decision_for_task(_state(autonomy="autonomous", auto_push=True), "bash", {"command": "git push origin feature"})
    assert disabled and disabled["approval_required"] is True
    assert enabled and enabled["approval_required"] is True


def test_plain_file_deletion_is_gated():
    result = decision_for_task(_state(autonomy="autonomous"), "bash", {"command": "rm obsolete.py"})
    assert result and result["approval_required"] is True
