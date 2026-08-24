"""Repository inspection helpers used by the coding-agent orchestrator."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


_DEFAULT_IGNORES = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "dist", "build", ".next", ".cache",
}


@dataclass(frozen=True)
class RepositorySummary:
    root: str
    files: int
    directories: int
    top_level: tuple[str, ...]


class RepositoryInspector:
    """Small, bounded filesystem inspection API; never reads file contents."""

    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise ValueError(f"Workspace is not a directory: {self.root}")

    def summary(self) -> RepositorySummary:
        files = directories = 0
        top_level = tuple(sorted(p.name for p in self.root.iterdir()))
        for current, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in _DEFAULT_IGNORES]
            directories += len(dirnames)
            files += len(filenames)
        return RepositorySummary(str(self.root), files, directories, top_level)

    def iter_files(self, suffixes: set[str] | None = None, limit: int = 5000):
        """Yield repository-relative file paths without loading their contents."""
        count = 0
        for current, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in _DEFAULT_IGNORES]
            for filename in sorted(filenames):
                if suffixes and Path(filename).suffix.lower() not in suffixes:
                    continue
                path = Path(current) / filename
                yield path.relative_to(self.root).as_posix()
                count += 1
                if count >= limit:
                    return

    def relevant_files(self, limit: int = 100) -> list[str]:
        """Return likely entry/config/test files before broad repository scans."""
        priority_names = {
            "pyproject.toml", "package.json", "tsconfig.json", "vite.config.ts",
            "vite.config.js", "Cargo.toml", "go.mod", "Dockerfile", "docker-compose.yml",
            "docker-compose.yaml", "README.md", "Makefile", "manage.py", "main.py",
            "app.py", "src/main.py", "src/index.ts", "src/index.js",
        }
        candidates = []
        for path in self.iter_files(limit=limit * 4):
            score = 0
            if Path(path).name in priority_names:
                score -= 10
            if "test" in Path(path).name.lower():
                score += 5
            candidates.append((score, path))
        return [path for _, path in sorted(candidates)[:limit]]
