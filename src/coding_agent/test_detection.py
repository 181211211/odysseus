"""Lightweight project test-command detection."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TestCommand:
    command: str
    reason: str
    priority: int = 50


def detect_test_commands(root: str | Path) -> list[TestCommand]:
    root = Path(root)
    found: list[TestCommand] = []

    if (root / "pyproject.toml").exists() or (root / "pytest.ini").exists() or (root / "tox.ini").exists():
        found.append(TestCommand("pytest", "Python project with pytest configuration", 10))
    elif (root / "tests").is_dir() and list(root.glob("**/test_*.py"))[:1]:
        found.append(TestCommand("pytest", "Python tests detected", 20))

    package = root / "package.json"
    if package.exists():
        try:
            data = json.loads(package.read_text(encoding="utf-8"))
            scripts = data.get("scripts", {})
            if isinstance(scripts, dict) and scripts.get("test"):
                found.append(TestCommand("npm test", "package.json test script", 10))
            if (root / "vitest.config.ts").exists() or (root / "vitest.config.js").exists():
                found.append(TestCommand("npx vitest run", "Vitest configuration detected", 15))
            elif (root / "jest.config.js").exists() or (root / "jest.config.ts").exists():
                found.append(TestCommand("npx jest", "Jest configuration detected", 15))
        except (OSError, json.JSONDecodeError):
            pass

    if (root / "Cargo.toml").exists():
        found.append(TestCommand("cargo test", "Rust project", 20))
    if (root / "go.mod").exists():
        found.append(TestCommand("go test ./...", "Go project", 20))

    return sorted(found, key=lambda item: item.priority)
