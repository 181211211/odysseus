"""Read-only Git inspection primitives for coding tasks."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GitResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class GitInspector:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()

    def run(self, *args: str) -> GitResult:
        proc = subprocess.run(
            ["git", *args], cwd=self.root, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
        )
        return GitResult(("git", *args), proc.returncode, proc.stdout, proc.stderr)

    def status(self) -> GitResult:
        return self.run("status", "--short", "--branch")

    def diff(self, staged: bool = False) -> GitResult:
        return self.run("diff", "--cached" if staged else "--",)

    def log(self, limit: int = 10) -> GitResult:
        limit = max(1, min(limit, 50))
        return self.run("log", f"-{limit}", "--oneline", "--decorate")

    def branches(self) -> GitResult:
        return self.run("branch", "--list", "--all")
