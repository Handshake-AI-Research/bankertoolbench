"""Shared "is the install complete?" checks for the MCP tool data layout.

Single source of truth for the adapter validator, the prerequisites bootstrap,
and the downloader — so they cannot drift on what counts as complete.
"""

from __future__ import annotations

from pathlib import Path

from .config import REQUIRED_TOOL_FILES, REQUIRED_TOOLS


def missing_tool_paths(tools_dir: Path) -> list[str]:
    """Return missing tool dirs and required files under *tools_dir*."""
    missing: list[str] = []
    for tool in REQUIRED_TOOLS:
        if not (tools_dir / tool).is_dir():
            missing.append(tool)
            continue
        for rel in REQUIRED_TOOL_FILES.get(tool, ()):
            if not (tools_dir / tool / rel).is_file():
                missing.append(f"{tool}/{rel}")
    return missing


def tool_needs_refresh(tools_dir: Path, tool: str) -> bool:
    """Return True if *tool* is missing its directory or any required file."""
    if not (tools_dir / tool).is_dir():
        return True
    return any(
        not (tools_dir / tool / rel).is_file()
        for rel in REQUIRED_TOOL_FILES.get(tool, ())
    )
