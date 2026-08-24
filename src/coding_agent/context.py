"""Deterministic context selection for coding tasks."""

from __future__ import annotations

from pathlib import Path

from .repository import RepositoryInspector


_TEXT_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".scss",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".md", ".sql",
    ".sh", ".bash", ".dockerfile", ".xml", ".txt",
}


def select_initial_context(root: str, limit: int = 80) -> list[str]:
    """Select likely context files without loading their contents.

    The LLM remains responsible for deciding what to read. This function only
    provides a cheap shortlist, avoiding repository-wide context dumps.
    """
    inspector = RepositoryInspector(root)
    priority = inspector.relevant_files(limit=limit)
    selected = []
    seen = set()
    for path in priority:
        if path in seen:
            continue
        if Path(path).suffix.lower() in _TEXT_EXTENSIONS or Path(path).name in {
            "Dockerfile", "Makefile", "README", "README.md",
        }:
            selected.append(path)
            seen.add(path)
        if len(selected) >= limit:
            break
    return selected
