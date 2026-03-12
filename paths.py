from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import pwd


def real_user_home_dir() -> Path:
    return Path(pwd.getpwuid(os.getuid()).pw_dir).resolve(strict=False)


def _home_relative(path: str) -> Path:
    return (real_user_home_dir() / path).resolve(strict=False)


def _xdg_root(env_var: str, *, fallback: str) -> Path:
    raw = str(os.environ.get(env_var) or "").strip()
    if not raw:
        return _home_relative(fallback)
    path = Path(raw).expanduser()
    if not path.is_absolute():
        return _home_relative(fallback)
    return path.resolve(strict=False)


def default_reviewflow_config_path() -> Path:
    return (_xdg_root("XDG_CONFIG_HOME", fallback=".config") / "reviewflow" / "reviewflow.toml").resolve(
        strict=False
    )


def default_sandbox_root() -> Path:
    return (_xdg_root("XDG_STATE_HOME", fallback=".local/state") / "reviewflow" / "sandboxes").resolve(
        strict=False
    )


def default_cache_root() -> Path:
    return (_xdg_root("XDG_CACHE_HOME", fallback=".cache") / "reviewflow").resolve(strict=False)


def default_codex_base_config_path() -> Path:
    return _home_relative(".codex/config.toml")


@dataclass(frozen=True)
class ReviewflowPaths:
    sandbox_root: Path
    cache_root: Path
    review_chunkhound_config: Path | None = None
    main_chunkhound_config: Path | None = None

    @property
    def seeds_root(self) -> Path:
        return self.cache_root / "seeds"

    @property
    def bases_root(self) -> Path:
        return self.cache_root / "bases"


DEFAULT_PATHS = ReviewflowPaths(
    sandbox_root=_home_relative(".local/state/reviewflow/sandboxes"),
    cache_root=_home_relative(".cache/reviewflow"),
)


def default_paths() -> ReviewflowPaths:
    return ReviewflowPaths(
        sandbox_root=default_sandbox_root(),
        cache_root=default_cache_root(),
    )


def safe_ref_slug(ref_name: str) -> str:
    # Keep mostly-readable folder names while avoiding unintended nesting.
    return ref_name.replace("/", "__")


def repo_id_for_gh(host: str, owner: str, repo: str) -> str:
    if host == "github.com":
        return f"{owner}/{repo}"
    return f"{host}/{owner}/{repo}"


def seed_dir(paths: ReviewflowPaths, host: str, owner: str, repo: str) -> Path:
    return paths.seeds_root / host / owner / repo


def base_dir(paths: ReviewflowPaths, host: str, owner: str, repo: str, base_ref: str) -> Path:
    return paths.bases_root / host / owner / repo / safe_ref_slug(base_ref)
