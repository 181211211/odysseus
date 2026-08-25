"""End-to-end Coding Agent workflow using a real temporary repository.

The model is scripted, but the repository, file edits, test execution and git
review are real. This verifies the autonomous controller as a complete coding
workflow without making a network LLM call in CI.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from src.coding_agent.loop import AutonomousCodingLoop
from src.coding_agent.state import CodingTaskState, TaskLimits, TaskStatus


class ScriptedModel:
    def __init__(self, responses):
        self.responses = list(responses)

    async def complete(self, messages):
        if not self.responses:
            return {"content": "No more scripted actions", "tool_calls": [], "done": True}
        return self.responses.pop(0)


async def local_executor(root: Path, name: str, args: dict):
    if name == "coding_inspect":
        files = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and ".git" not in p.parts)
        return {"exit_code": 0, "output": json.dumps({"files": files})}
    if name == "write_file":
        path = root / args["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args.get("content", ""), encoding="utf-8")
        return {"exit_code": 0, "output": f"wrote {args['path']}"}
    if name == "edit_file":
        path = root / args["path"]
        text = path.read_text(encoding="utf-8")
        old, new = args["old_string"], args["new_string"]
        assert old in text
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        return {"exit_code": 0, "output": f"edited {args['path']}"}
    if name == "bash":
        proc = await asyncio.to_thread(
            subprocess.run,
            args["command"],
            cwd=root,
            shell=True,
            text=True,
            capture_output=True,
            timeout=30,
        )
        result = {"exit_code": proc.returncode, "output": proc.stdout, "stderr": proc.stderr}
        if proc.returncode != 0:
            result["error"] = proc.stderr or proc.stdout or f"command exited with {proc.returncode}"
        return result
    if name == "coding_git":
        action = args.get("action", "status")
        cmd = ["git", "status", "--short"] if action == "status" else ["git", "diff", "--", "."]
        proc = await asyncio.to_thread(subprocess.run, cmd, cwd=root, text=True, capture_output=True)
        return {"exit_code": proc.returncode, "output": proc.stdout, "stderr": proc.stderr}
    raise AssertionError(f"unexpected tool: {name}")


@pytest.mark.asyncio
async def test_calculator_task_inspect_code_test_fix_retest_review(tmp_path: Path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True)

    # Use a tiny real Python assertion as the project test command. This keeps
    # the E2E test hermetic: it verifies shell execution and failure recovery
    # without nesting pytest inside the already-running Odysseus pytest process.
    verify = "python -c \"from calculator import add; assert add(2, 3) == 5\" # pytest verification"
    responses = [
        {"content": "Inspecting project", "tool_calls": [{"name": "coding_inspect", "arguments": {}}]},
        {"content": "Creating calculator", "tool_calls": [
            {"name": "write_file", "arguments": {"path": "calculator.py", "content": "def add(a, b):\n    return a - b\n"}},
            {"name": "write_file", "arguments": {"path": "test_calculator.py", "content": "from calculator import add\n\ndef test_add():\n    assert add(2, 3) == 5\n"}},
        ]},
        {"content": "Running tests", "tool_calls": [{"name": "bash", "arguments": {"command": verify}}]},
        {"content": "Fixing failed implementation", "tool_calls": [{"name": "edit_file", "arguments": {"path": "calculator.py", "old_string": "return a - b", "new_string": "return a + b"}}]},
        {"content": "Retesting", "tool_calls": [{"name": "bash", "arguments": {"command": verify}}]},
        {"content": "Reviewing diff", "tool_calls": [{"name": "coding_git", "arguments": {"action": "diff"}}]},
        {"content": "Calculator module and tests are complete.", "tool_calls": [], "done": True},
    ]

    state = CodingTaskState(
        task_id="e2e-calculator",
        request="Create a small Python calculator module with tests.",
        workspace=str(tmp_path),
        limits=TaskLimits(max_iterations=12, max_tool_calls=30, max_shell_commands=8, max_test_retries=4),
    )

    async def execute(name, args):
        return await local_executor(tmp_path, name, args)

    loop = AutonomousCodingLoop(state, ScriptedModel(responses), execute)
    result = await loop.run()

    assert result.status is TaskStatus.COMPLETED
    assert result.tests_passed is True
    assert result.reviewed is True
    assert state.test_retries == 1
    assert len(state.tests) == 2
    assert state.tests[0]["passed"] is False
    assert state.tests[1]["passed"] is True
    assert (tmp_path / "calculator.py").read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n"
    assert "calculator.py" in state.modified_files
    assert "test_calculator.py" in state.modified_files
