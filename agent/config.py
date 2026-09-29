"""Load project-local Agent Warden configuration into environment defaults."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any


CONFIG_RELATIVE_PATH = Path(".agent-warden/config.toml")


def find_config(project: str | os.PathLike[str] | None = None) -> Path | None:
    """Find the nearest project config, starting at *project* or the cwd."""
    start = Path(project).expanduser() if project is not None else Path.cwd()
    start = start.resolve()
    if start.is_file():
        start = start.parent
    for directory in (start, *start.parents):
        candidate = directory / CONFIG_RELATIVE_PATH
        if candidate.is_file():
            return candidate
    return None


def load_project_config(
    project: str | os.PathLike[str] | None = None,
) -> tuple[Path | None, dict[str, Any]]:
    """Parse the nearest config and set Warden environment variables if absent."""
    config_path = find_config(project)
    if config_path is None:
        return None, {}
    with config_path.open("rb") as handle:
        config = tomllib.load(handle)
    project_dir = config_path.parent.parent

    packs = config.get("packs")
    if isinstance(packs, list) and all(isinstance(value, str) for value in packs):
        os.environ.setdefault("WARDEN_RULEPACKS", ",".join(packs))

    pack_dir = config.get("pack_dir")
    if isinstance(pack_dir, str):
        path = Path(pack_dir).expanduser()
        if not path.is_absolute():
            path = project_dir / path
        os.environ.setdefault("WARDEN_RULEPACKS_DIR", str(path.resolve()))

    state_dir = config.get("state_dir")
    if isinstance(state_dir, str):
        path = Path(state_dir).expanduser()
        if not path.is_absolute():
            path = project_dir / path
        os.environ.setdefault("WARDEN_STATE_DIR", str(path.resolve()))

    fail_closed = config.get("fail_closed")
    if isinstance(fail_closed, bool):
        os.environ.setdefault("AGENT_WARDEN_FAIL_CLOSED", "1" if fail_closed else "0")
    return config_path, config
