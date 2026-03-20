#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "cure.py"
PROMPTS_DIR = ROOT / "prompts"
LICENSE_FILE = ROOT / "LICENSE"
SUPPORTED_TARGETS = {
    "linux-x86_64": ("Linux", {"x86_64", "amd64"}),
    "macos-x86_64": ("Darwin", {"x86_64"}),
    "macos-arm64": ("Darwin", {"arm64", "aarch64"}),
}


def load_version() -> str:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(pyproject["project"]["version"]).strip()


def current_platform() -> tuple[str, str]:
    import platform

    return platform.system(), platform.machine().lower()


def infer_target_id() -> str:
    system, machine = current_platform()
    for target_id, (expected_system, machines) in SUPPORTED_TARGETS.items():
        if system == expected_system and machine in machines:
            return target_id
    supported = ", ".join(sorted(SUPPORTED_TARGETS))
    raise SystemExit(f"Unsupported build host {system}/{machine}. Supported targets: {supported}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a standalone CURe release archive for the current platform.")
    parser.add_argument("--output-dir", required=True, help="Directory to write the tarball and checksum file into.")
    parser.add_argument(
        "--target-id",
        help="Expected target id for this runner (linux-x86_64, macos-x86_64, macos-arm64). Defaults to the current host.",
    )
    parser.add_argument(
        "--work-dir",
        help="Scratch directory for PyInstaller build outputs. Defaults to .tmp_standalone_release/<target> in the repo root.",
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_binary(*, target_id: str, work_dir: Path) -> Path:
    dist_dir = work_dir / "dist"
    build_dir = work_dir / "build"
    spec_dir = work_dir / "spec"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    dist_dir.mkdir(parents=True, exist_ok=True)
    build_dir.mkdir(parents=True, exist_ok=True)
    spec_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        "cure",
        "--paths",
        str(ROOT),
        "--hidden-import",
        "prompts",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(build_dir),
        "--specpath",
        str(spec_dir),
    ]
    for prompt_file in sorted(PROMPTS_DIR.glob("*.md")):
        cmd.extend(["--add-data", f"{prompt_file}:prompts"])
    cmd.append(str(ENTRYPOINT))
    subprocess.run(cmd, cwd=ROOT, check=True)
    binary_path = dist_dir / "cure"
    if not binary_path.is_file():
        raise SystemExit(f"Expected standalone binary at {binary_path}, but it was not created.")
    return binary_path


def stage_archive(*, binary_path: Path, output_dir: Path, version: str, target_id: str) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    asset_name = f"cureview-v{version}-{target_id}.tar.gz"
    archive_path = output_dir / asset_name
    checksum_path = output_dir / f"{asset_name}.sha256"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(binary_path, arcname="cure")
        tar.add(LICENSE_FILE, arcname="LICENSE")
    checksum_path.write_text(f"{sha256(archive_path)}  {asset_name}\n", encoding="utf-8")
    return archive_path, checksum_path


def main() -> int:
    args = parse_args()
    inferred_target_id = infer_target_id()
    target_id = str(args.target_id or inferred_target_id).strip()
    if target_id not in SUPPORTED_TARGETS:
        supported = ", ".join(sorted(SUPPORTED_TARGETS))
        raise SystemExit(f"Unknown target id {target_id!r}. Supported targets: {supported}")
    if target_id != inferred_target_id:
        system, machine = current_platform()
        raise SystemExit(
            f"Target id {target_id!r} does not match the current host {system}/{machine}; expected {inferred_target_id!r}."
        )

    work_dir = (
        Path(args.work_dir).expanduser().resolve(strict=False)
        if args.work_dir
        else (ROOT / ".tmp_standalone_release" / target_id).resolve(strict=False)
    )
    output_dir = Path(args.output_dir).expanduser().resolve(strict=False)
    version = load_version()
    binary_path = build_binary(target_id=target_id, work_dir=work_dir)
    archive_path, checksum_path = stage_archive(
        binary_path=binary_path,
        output_dir=output_dir,
        version=version,
        target_id=target_id,
    )
    print(archive_path)
    print(checksum_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
