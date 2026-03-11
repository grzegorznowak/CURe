from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

LEGACY_SANDBOX_ROOT = Path("/workspaces/academy+/.tmp/review-sandboxes")
DEFAULT_SANDBOX_ROOT = Path("/workspaces/.reviewflow-sandboxes")
DEFAULT_CACHE_ROOT = Path("/workspaces/.reviewflow-cache")
DEFAULT_REVIEW_CHUNKHOUND_CONFIG = Path("/workspaces/.chunkhound.review.json")
LEGACY_MAIN_CHUNKHOUND_CONFIG = Path("/workspaces/.chunkhound.json")
DEFAULT_MAIN_CHUNKHOUND_CONFIG = Path("/workspaces/academy+/.chunkhound.json")


@dataclass(frozen=True)
class ReviewflowPaths:
    sandbox_root: Path
    cache_root: Path
    review_chunkhound_config: Path
    main_chunkhound_config: Path

    @property
    def seeds_root(self) -> Path:
        return self.cache_root / "seeds"

    @property
    def bases_root(self) -> Path:
        return self.cache_root / "bases"


DEFAULT_PATHS = ReviewflowPaths(
    sandbox_root=DEFAULT_SANDBOX_ROOT,
    cache_root=DEFAULT_CACHE_ROOT,
    review_chunkhound_config=DEFAULT_REVIEW_CHUNKHOUND_CONFIG,
    main_chunkhound_config=DEFAULT_MAIN_CHUNKHOUND_CONFIG,
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
