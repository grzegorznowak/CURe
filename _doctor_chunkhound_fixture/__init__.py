from __future__ import annotations

import contextlib
import importlib.resources
import json
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

_FIXTURE_FILES = ("main.py", "utils.py", "README.md")


@contextlib.contextmanager
def index_fixture_for_health_check(
    chunkhound_binary: str,
    user_config: dict[str, Any],
    timeout: float = 120.0,
) -> Iterator[tuple[str, str, tempfile.TemporaryDirectory[str]]]:
    """Create, index, and clean up a temporary ChunkHound health-check fixture."""
    temp_dir = tempfile.TemporaryDirectory(prefix="cure-chunkhound-health-")
    try:
        temp_root = Path(temp_dir.name)
        repo_path = temp_root / "fixture"
        repo_path.mkdir(parents=True, exist_ok=True)
        resources = importlib.resources.files(__package__ or __name__)
        for name in _FIXTURE_FILES:
            with importlib.resources.as_file(resources / name) as source:
                shutil.copy2(source, repo_path / name)

        config_path = temp_root / "chunkhound.json"
        merged_config = dict(user_config)
        merged_config["database"] = {"provider": "duckdb", "path": str(temp_root / ".chunkhound.db")}
        merged_config["indexing"] = {"include": ["*.py", "*.md"]}
        config_path.write_text(json.dumps(merged_config, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        subprocess.run(
            [str(chunkhound_binary), "index", str(repo_path), "--config", str(config_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=float(timeout),
        )
        yield str(config_path), str(repo_path), temp_dir
    finally:
        temp_dir.cleanup()
