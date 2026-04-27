from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from cure_errors import ReviewflowError
from paths import ReviewflowPaths


def _reviewflow():
    import cure as rf

    return rf


@dataclass(frozen=True)
class SharedWorkspaceKey:
    host: str
    owner: str
    repo: str
    sealed_head_sha: str
    selected_baseline_ref: str
    chunkhound_config_fingerprint: str
    chunkhound_version: str
    digest: str

    def to_metadata(self) -> dict[str, str]:
        return {
            "host": self.host,
            "owner": self.owner,
            "repo": self.repo,
            "sealed_head_sha": self.sealed_head_sha,
            "selected_baseline_ref": self.selected_baseline_ref,
            "chunkhound_config_fingerprint": self.chunkhound_config_fingerprint,
            "chunkhound_version": self.chunkhound_version,
            "digest": self.digest,
        }


@dataclass(frozen=True)
class SharedWorkspaceLease:
    key: SharedWorkspaceKey
    repo_dir: Path
    chunkhound_cwd: Path
    chunkhound_db: Path
    chunkhound_config: Path
    workspace_root: Path
    validation: str
    result: str

    def to_metadata(self) -> dict[str, str]:
        return {
            "mode": "shared_same_sha",
            "key": self.key.digest,
            "key_metadata": self.key.to_metadata(),
            "workspace_root": str(self.workspace_root),
            "repo_dir": str(self.repo_dir),
            "chunkhound_cwd": str(self.chunkhound_cwd),
            "chunkhound_db": str(self.chunkhound_db),
            "chunkhound_config": str(self.chunkhound_config),
            "sealed_head_sha": self.key.sealed_head_sha,
            "selected_baseline_ref": self.key.selected_baseline_ref,
            "validation": self.validation,
            "lease_result": self.result,
        }


def _normalized_key_payload(
    *,
    host: str,
    owner: str,
    repo: str,
    sealed_head_sha: str,
    selected_baseline_ref: str,
    chunkhound_config_fingerprint: str,
    chunkhound_version: str,
) -> dict[str, str]:
    return {
        "host": str(host or "").strip().lower(),
        "owner": str(owner or "").strip().lower(),
        "repo": str(repo or "").strip().lower(),
        "sealed_head_sha": str(sealed_head_sha or "").strip().lower(),
        "selected_baseline_ref": str(selected_baseline_ref or "").strip(),
        "chunkhound_config_fingerprint": str(chunkhound_config_fingerprint or "").strip(),
        "chunkhound_version": str(chunkhound_version or "").strip(),
    }


def compute_shared_workspace_key(
    *,
    host: str,
    owner: str,
    repo: str,
    sealed_head_sha: str,
    selected_baseline_ref: str,
    chunkhound_config_fingerprint: str,
    chunkhound_version: str,
) -> SharedWorkspaceKey:
    payload = _normalized_key_payload(
        host=host,
        owner=owner,
        repo=repo,
        sealed_head_sha=sealed_head_sha,
        selected_baseline_ref=selected_baseline_ref,
        chunkhound_config_fingerprint=chunkhound_config_fingerprint,
        chunkhound_version=chunkhound_version,
    )
    missing = [name for name, value in payload.items() if not value]
    if missing:
        raise ReviewflowError(f"Shared workspace key missing required field(s): {', '.join(missing)}")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return SharedWorkspaceKey(**payload, digest=digest)


def shared_workspace_root(paths: ReviewflowPaths, key: SharedWorkspaceKey) -> Path:
    return paths.cache_root / "shared-workspaces" / key.host / key.owner / key.repo / key.digest


def shared_workspace_metadata_path(workspace_root: Path) -> Path:
    return workspace_root / "workspace.json"


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    if path.is_dir():
        for child in sorted(p for p in path.rglob("*") if p.is_file()):
            rel = child.relative_to(path).as_posix()
            hasher.update(rel.encode("utf-8"))
            hasher.update(b"\0")
            with child.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    hasher.update(chunk)
            hasher.update(b"\0")
        return hasher.hexdigest()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_shared_workspace_metadata(
    *,
    workspace_root: Path,
    key: SharedWorkspaceKey,
    repo_dir: Path,
    chunkhound_db: Path,
    chunkhound_config: Path,
) -> None:
    workspace_root.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "mode": "shared_same_sha",
        "key": key.to_metadata(),
        "paths": {
            "repo_dir": str(repo_dir.resolve(strict=False)),
            "chunkhound_cwd": str(chunkhound_db.parent.resolve(strict=False)),
            "chunkhound_db": str(chunkhound_db.resolve(strict=False)),
            "chunkhound_config": str(chunkhound_config.resolve(strict=False)),
        },
        "validation": {
            "chunkhound_config_fingerprint": key.chunkhound_config_fingerprint,
            "chunkhound_version": key.chunkhound_version,
            "chunkhound_config_file_sha256": (
                _file_sha256(chunkhound_config) if chunkhound_config.is_file() else ""
            ),
            "chunkhound_db_file_sha256": (
                _file_sha256(chunkhound_db) if chunkhound_db.exists() else ""
            ),
        },
    }
    shared_workspace_metadata_path(workspace_root).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def resolve_git_head_sha(repo_dir: Path) -> str:
    result = _reviewflow().run_cmd(["git", "-C", str(repo_dir), "rev-parse", "HEAD"])
    return str(result.stdout or "").strip().lower()


def _load_shared_workspace_metadata(workspace_root: Path) -> dict[str, Any]:
    meta_path = shared_workspace_metadata_path(workspace_root)
    if not meta_path.is_file():
        raise ReviewflowError(f"Shared workspace metadata missing: {meta_path}")
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ReviewflowError(f"Shared workspace metadata is unreadable: {meta_path}") from exc
    if not isinstance(data, dict):
        raise ReviewflowError(f"Shared workspace metadata is invalid: {meta_path}")
    return data


def _shared_workspace_key_from_metadata(raw_key: dict[str, Any]) -> SharedWorkspaceKey:
    return compute_shared_workspace_key(
        host=str(raw_key.get("host") or ""),
        owner=str(raw_key.get("owner") or ""),
        repo=str(raw_key.get("repo") or ""),
        sealed_head_sha=str(raw_key.get("sealed_head_sha") or ""),
        selected_baseline_ref=str(raw_key.get("selected_baseline_ref") or ""),
        chunkhound_config_fingerprint=str(raw_key.get("chunkhound_config_fingerprint") or ""),
        chunkhound_version=str(raw_key.get("chunkhound_version") or ""),
    )


def acquire_recorded_shared_workspace_lease(
    *,
    meta: dict[str, Any],
    paths: ReviewflowPaths,
    quiet: bool = False,
) -> SharedWorkspaceLease | None:
    workspace_meta = meta.get("workspace")
    if not isinstance(workspace_meta, dict):
        return None
    if str(workspace_meta.get("mode") or "").strip() != "shared_same_sha":
        return None

    recorded_key_digest = str(workspace_meta.get("key") or "").strip()
    if not recorded_key_digest:
        raise ReviewflowError("Shared workspace session metadata is missing key.")
    recorded_repo = Path(str(workspace_meta.get("repo_dir") or "")).resolve(strict=False)
    recorded_root_raw = str(workspace_meta.get("workspace_root") or "").strip()
    recorded_root = (
        Path(recorded_root_raw).resolve(strict=False)
        if recorded_root_raw
        else recorded_repo.parent.resolve(strict=False)
    )
    lock_path = recorded_root / ".workspace.lock"
    with _reviewflow().file_lock(lock_path, quiet=quiet):
        metadata = _load_shared_workspace_metadata(recorded_root)
        stored_key_raw = metadata.get("key")
        if not isinstance(stored_key_raw, dict):
            raise ReviewflowError("Shared workspace metadata is missing key.")
        key = _shared_workspace_key_from_metadata(stored_key_raw)
        if key.digest != recorded_key_digest:
            raise ReviewflowError("Shared workspace session key does not match workspace metadata.")
        expected_root = shared_workspace_root(paths, key).resolve(strict=False)
        if expected_root != recorded_root:
            raise ReviewflowError(
                f"Shared workspace root mismatch: expected {expected_root}, got {recorded_root}"
            )

        for field in ("host", "owner", "repo"):
            recorded_value = str(meta.get(field) or "").strip().lower()
            key_value = str(getattr(key, field)).strip().lower()
            if recorded_value and recorded_value != key_value:
                raise ReviewflowError(
                    f"Shared workspace {field} mismatch: expected {recorded_value}, got {key_value}"
                )
        recorded_sha = str(workspace_meta.get("sealed_head_sha") or "").strip().lower()
        if recorded_sha and recorded_sha != key.sealed_head_sha:
            raise ReviewflowError(
                "Shared workspace sealed SHA mismatch: "
                f"expected {recorded_sha}, got {key.sealed_head_sha}"
            )
        recorded_baseline = str(workspace_meta.get("selected_baseline_ref") or "").strip()
        if recorded_baseline and recorded_baseline != key.selected_baseline_ref:
            raise ReviewflowError(
                "Shared workspace selected baseline mismatch: "
                f"expected {recorded_baseline}, got {key.selected_baseline_ref}"
            )

        lease = _validate_shared_workspace_without_lock(paths=paths, key=key)
        recorded_paths = {
            "repo_dir": workspace_meta.get("repo_dir"),
            "chunkhound_cwd": workspace_meta.get("chunkhound_cwd"),
            "chunkhound_db": workspace_meta.get("chunkhound_db"),
            "chunkhound_config": workspace_meta.get("chunkhound_config"),
        }
        resolved_paths = {
            "repo_dir": lease.repo_dir,
            "chunkhound_cwd": lease.chunkhound_cwd,
            "chunkhound_db": lease.chunkhound_db,
            "chunkhound_config": lease.chunkhound_config,
        }
        for field, recorded in recorded_paths.items():
            recorded_text = str(recorded or "").strip()
            if not recorded_text:
                continue
            recorded_path = Path(recorded_text).resolve(strict=False)
            if recorded_path != resolved_paths[field]:
                raise ReviewflowError(
                    f"Shared workspace recorded {field} mismatch: "
                    f"expected {recorded_path}, got {resolved_paths[field]}"
                )
        return SharedWorkspaceLease(
            key=lease.key,
            repo_dir=lease.repo_dir,
            chunkhound_cwd=lease.chunkhound_cwd,
            chunkhound_db=lease.chunkhound_db,
            chunkhound_config=lease.chunkhound_config,
            workspace_root=lease.workspace_root,
            validation=lease.validation,
            result="reused",
        )


def acquire_shared_workspace_lease(
    *,
    paths: ReviewflowPaths,
    key: SharedWorkspaceKey,
    quiet: bool = False,
) -> SharedWorkspaceLease:
    workspace_root = shared_workspace_root(paths, key)
    lock_path = workspace_root / ".workspace.lock"
    with _reviewflow().file_lock(lock_path, quiet=quiet):
        return _validate_shared_workspace_without_lock(paths=paths, key=key)


def _validate_shared_workspace_without_lock(
    *,
    paths: ReviewflowPaths,
    key: SharedWorkspaceKey,
) -> SharedWorkspaceLease:
    workspace_root = shared_workspace_root(paths, key)
    metadata = _load_shared_workspace_metadata(workspace_root)
    stored_key = metadata.get("key")
    if not isinstance(stored_key, dict) or stored_key.get("digest") != key.digest:
        raise ReviewflowError("Shared workspace metadata key does not match requested lease key.")
    paths_meta = metadata.get("paths")
    if not isinstance(paths_meta, dict):
        raise ReviewflowError("Shared workspace metadata is missing paths.")
    repo_dir = Path(str(paths_meta.get("repo_dir") or "")).resolve(strict=False)
    chunkhound_db = Path(str(paths_meta.get("chunkhound_db") or "")).resolve(strict=False)
    chunkhound_cwd = Path(str(paths_meta.get("chunkhound_cwd") or "")).resolve(strict=False)
    if not str(paths_meta.get("chunkhound_cwd") or "").strip():
        chunkhound_cwd = chunkhound_db.parent
    chunkhound_config = Path(str(paths_meta.get("chunkhound_config") or "")).resolve(strict=False)
    if not repo_dir.is_dir():
        raise ReviewflowError(f"Shared workspace repo is missing: {repo_dir}")
    if not chunkhound_cwd.is_dir():
        raise ReviewflowError(f"Shared workspace ChunkHound cwd is missing: {chunkhound_cwd}")
    if not chunkhound_db.exists():
        raise ReviewflowError(f"Shared workspace ChunkHound DB is missing: {chunkhound_db}")
    if not chunkhound_config.is_file():
        raise ReviewflowError(f"Shared workspace ChunkHound config is missing: {chunkhound_config}")
    validation_meta = metadata.get("validation")
    if not isinstance(validation_meta, dict):
        raise ReviewflowError("Shared workspace metadata is missing validation fingerprints.")
    stored_config_fingerprint = str(
        validation_meta.get("chunkhound_config_fingerprint") or ""
    ).strip()
    if stored_config_fingerprint != key.chunkhound_config_fingerprint:
        raise ReviewflowError(
            "Shared workspace ChunkHound config fingerprint mismatch: "
            f"expected {key.chunkhound_config_fingerprint}, got {stored_config_fingerprint or '<empty>'}"
        )
    stored_version = str(validation_meta.get("chunkhound_version") or "").strip()
    if stored_version != key.chunkhound_version:
        raise ReviewflowError(
            "Shared workspace ChunkHound version mismatch: "
            f"expected {key.chunkhound_version}, got {stored_version or '<empty>'}"
        )
    stored_config_hash = str(validation_meta.get("chunkhound_config_file_sha256") or "").strip()
    actual_config_hash = _file_sha256(chunkhound_config)
    if not stored_config_hash or stored_config_hash != actual_config_hash:
        raise ReviewflowError(
            "Shared workspace ChunkHound config fingerprint changed: "
            f"expected {stored_config_hash or '<empty>'}, got {actual_config_hash}"
        )
    stored_db_hash = str(validation_meta.get("chunkhound_db_file_sha256") or "").strip()
    actual_db_hash = _file_sha256(chunkhound_db)
    if not stored_db_hash or stored_db_hash != actual_db_hash:
        raise ReviewflowError(
            "Shared workspace ChunkHound DB fingerprint changed: "
            f"expected {stored_db_hash or '<empty>'}, got {actual_db_hash}"
        )
    actual_sha = _reviewflow().resolve_git_head_sha(repo_dir)
    if actual_sha != key.sealed_head_sha:
        raise ReviewflowError(
            "Shared workspace sealed SHA validation failed: "
            f"expected {key.sealed_head_sha}, got {actual_sha or '<empty>'}"
        )
    return SharedWorkspaceLease(
        key=key,
        repo_dir=repo_dir,
        chunkhound_cwd=chunkhound_cwd,
        chunkhound_db=chunkhound_db,
        chunkhound_config=chunkhound_config,
        workspace_root=workspace_root,
        validation="passed",
        result="reused",
    )


def _quarantine_invalid_shared_workspace_state(*, workspace_root: Path) -> Path:
    invalid_root = workspace_root / "invalid"
    invalid_root.mkdir(parents=True, exist_ok=True)
    for index in range(1000):
        target = invalid_root / f"rebuild-{index:03d}"
        if not target.exists():
            target.mkdir(parents=True)
            break
    else:
        raise ReviewflowError(f"Shared workspace has too many invalid rebuilds: {invalid_root}")

    for child in list(workspace_root.iterdir()):
        if child.name in {".workspace.lock", "invalid"}:
            continue
        shutil.move(str(child), str(target / child.name))
    return target


def acquire_or_create_shared_workspace_lease(
    *,
    paths: ReviewflowPaths,
    key: SharedWorkspaceKey,
    source_repo_dir: Path,
    seed_source_db_path: Path | None,
    chunkhound_cfg: Any,
    resolved_chunkhound_config: dict[str, Any],
    progress: Any,
    quiet: bool = False,
    stream: bool = False,
    local_refs: list[str] | tuple[str, ...] | None = None,
    prepare_repo: Callable[[Path], None] | None = None,
) -> SharedWorkspaceLease:
    workspace_root = shared_workspace_root(paths, key)
    repo_dir = workspace_root / "repo"
    chunkhound_cwd = workspace_root / "chunkhound"
    chunkhound_db = chunkhound_cwd / ".chunkhound.db"
    chunkhound_config = chunkhound_cwd / "chunkhound.json"
    lock_path = workspace_root / ".workspace.lock"
    with _reviewflow().file_lock(lock_path, quiet=quiet):
        rebuilt = False
        if shared_workspace_metadata_path(workspace_root).is_file():
            try:
                return _validate_shared_workspace_without_lock(paths=paths, key=key)
            except ReviewflowError as exc:
                _quarantine_invalid_shared_workspace_state(workspace_root=workspace_root)
                rebuilt = True
                progress_meta = getattr(progress, "meta", None)
                if isinstance(progress_meta, dict):
                    workspace_meta = progress_meta.setdefault("workspace", {})
                    if isinstance(workspace_meta, dict):
                        workspace_meta["rebuild_reason"] = str(exc)

        if repo_dir.exists() or chunkhound_cwd.exists():
            raise ReviewflowError(
                f"Shared workspace has partial state without metadata: {workspace_root}"
            )
        workspace_root.mkdir(parents=True, exist_ok=True)
        clone_cmd = ["git", "clone"]
        if _reviewflow().same_device(source_repo_dir, workspace_root):
            clone_cmd.append("--local")
        else:
            clone_cmd.append("--no-hardlinks")
        clone_cmd.extend([str(source_repo_dir), str(repo_dir)])
        recorder = getattr(progress, "record_cmd", None)
        if callable(recorder):
            recorder(clone_cmd)
        _reviewflow().run_cmd(clone_cmd)
        for ref in local_refs or ():
            ref_name = str(ref or "").strip()
            if not ref_name:
                continue
            fetch_ref_cmd = ["git", "-C", str(repo_dir), "fetch", "origin", f"{ref_name}:{ref_name}"]
            if callable(recorder):
                recorder(fetch_ref_cmd)
            _reviewflow().run_cmd(fetch_ref_cmd)
        if prepare_repo is not None:
            prepare_repo(repo_dir)
        checkout_cmd = ["git", "-C", str(repo_dir), "checkout", "--detach", key.sealed_head_sha]
        if callable(recorder):
            recorder(checkout_cmd)
        _reviewflow().run_cmd(checkout_cmd)
        actual_sha = _reviewflow().resolve_git_head_sha(repo_dir)
        if actual_sha != key.sealed_head_sha:
            _quarantine_invalid_shared_workspace_state(workspace_root=workspace_root)
            raise ReviewflowError(
                "Shared workspace sealed SHA validation failed after checkout: "
                f"expected {key.sealed_head_sha}, got {actual_sha or '<empty>'}"
            )

        _reviewflow().materialize_chunkhound_env_config(
            resolved_config=resolved_chunkhound_config,
            output_config_path=chunkhound_config,
            database_provider="duckdb",
            database_path=chunkhound_db,
        )
        _reviewflow()._run_session_chunkhound_index_with_rebuild_fallback(
            progress=progress,
            scope="shared_workspace",
            quiet=quiet,
            stream=stream,
            chunkhound_cfg=chunkhound_cfg,
            chunkhound_cfg_path=chunkhound_config,
            chunkhound_db_path=chunkhound_db,
            chunkhound_work_dir=chunkhound_cwd,
            repo_dir=repo_dir,
            reuse_source_kind="shared_workspace_seed",
            seed_source_db_path=seed_source_db_path,
        )
        write_shared_workspace_metadata(
            workspace_root=workspace_root,
            key=key,
            repo_dir=repo_dir,
            chunkhound_db=chunkhound_db,
            chunkhound_config=chunkhound_config,
        )
        lease = _validate_shared_workspace_without_lock(paths=paths, key=key)
        return SharedWorkspaceLease(
            key=lease.key,
            repo_dir=lease.repo_dir,
            chunkhound_cwd=lease.chunkhound_cwd,
            chunkhound_db=lease.chunkhound_db,
            chunkhound_config=lease.chunkhound_config,
            workspace_root=lease.workspace_root,
            validation=lease.validation,
            result=("rebuilt" if rebuilt else "created"),
        )
