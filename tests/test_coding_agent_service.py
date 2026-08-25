import pytest

from src.coding_agent.state import TaskLimits, TaskStatus


@pytest.mark.asyncio
async def test_run_coding_task_composes_model_loop_and_secured_executor(monkeypatch, tmp_path):
    import src.coding_agent.service as service

    captured = {}

    class FakeModel:
        def __init__(self, model_spec, *, owner=None):
            captured["model_spec"] = model_spec
            captured["model_owner"] = owner

    class FakeExecutor:
        def __init__(self, **kwargs):
            captured["executor"] = kwargs

    class FakeLoop:
        def __init__(self, state, model, executor, *, persist=None, emit=None):
            captured["state"] = state
            captured["persist"] = persist
            captured["emit"] = emit

        async def run(self):
            captured["state"].status = TaskStatus.COMPLETED
            await captured["persist"](captured["state"])
            await captured["emit"]({"type": "coding_agent_status", "status": "completed"})
            from src.coding_agent.loop import CodingLoopResult
            return CodingLoopResult(TaskStatus.COMPLETED, "done", 1, 2, True, True)

    monkeypatch.setattr(service, "RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(service, "CodingModelAdapter", FakeModel)
    monkeypatch.setattr(service, "DispatcherToolExecutor", FakeExecutor)
    monkeypatch.setattr(service, "AutonomousCodingLoop", FakeLoop)
    monkeypatch.setattr(service, "register_active_task", lambda session_id, task_id, path: captured.update(active=(session_id, task_id, path)))

    events = []

    async def progress(event):
        events.append(event)

    security_context = object()
    result = await service.run_coding_task(
        request="Fix the failing tests",
        workspace="/repo",
        model_spec="openrouter/model",
        session_id="s1",
        owner="u1",
        security_context=security_context,
        autonomy="autonomous",
        auto_commit=True,
        limits=TaskLimits(max_iterations=7),
        disabled_tools={"web_search"},
        progress_cb=progress,
    )

    assert result.status is TaskStatus.COMPLETED
    assert captured["model_spec"] == "openrouter/model"
    assert captured["model_owner"] == "u1"
    assert captured["state"].request == "Fix the failing tests"
    assert captured["state"].workspace == "/repo"
    assert captured["state"].autonomy == "autonomous"
    assert captured["state"].auto_commit is True
    assert captured["state"].limits.max_iterations == 7
    assert captured["executor"]["workspace"] == "/repo"
    assert captured["executor"]["security_context"] is security_context
    assert captured["executor"]["disabled_tools"] == {"web_search"}
    assert events == [{"type": "ui_control", "data": {"type": "coding_agent_status", "status": "completed"}}]


@pytest.mark.asyncio
async def test_run_coding_task_rejects_invalid_autonomy():
    from src.coding_agent.service import run_coding_task

    with pytest.raises(ValueError, match="Invalid Coding Agent autonomy"):
        await run_coding_task(
            request="Fix it",
            workspace="/repo",
            model_spec="model",
            session_id="s1",
            owner=None,
            security_context=object(),
            autonomy="root-mode",
        )
