from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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
    sandbox_root=Path("/workspaces/academy+/.tmp/review-sandboxes"),
    cache_root=Path("/workspaces/.reviewflow-cache"),
    review_chunkhound_config=Path("/workspaces/.chunkhound.review.json"),
    main_chunkhound_config=Path("/workspaces/.chunkhound.json"),
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

