import hashlib
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReleaseWorkflowTests(unittest.TestCase):
    def _installer_target_id(self) -> str | None:
        system = platform.system()
        machine = platform.machine().lower()
        if system == "Linux" and machine in {"x86_64", "amd64"}:
            return "linux-x86_64"
        if system == "Darwin" and machine == "x86_64":
            return "macos-x86_64"
        if system == "Darwin" and machine in {"arm64", "aarch64"}:
            return "macos-arm64"
        return None

    def test_publish_workflow_exists_with_trusted_publishing_targets(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "publish-package.yml").read_text(encoding="utf-8")

        self.assertIn('name: Publish Package', workflow)
        self.assertIn('tags:\n      - "v*"', workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("uses: pypa/gh-action-pypi-publish@release/v1", workflow)
        self.assertIn("repository-url: https://test.pypi.org/legacy/", workflow)
        self.assertIn("name: testpypi", workflow)
        self.assertIn("name: pypi", workflow)

    def test_publish_workflow_gates_release_tag_shape_and_package_version(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "publish-package.yml").read_text(encoding="utf-8")

        self.assertIn("Validate tag and package metadata", workflow)
        self.assertIn('PACKAGE_NAME: "cureview"', workflow)
        self.assertIn('if ref_name != f"v{version}":', workflow)
        self.assertIn("publish_target = manual_target or (\"testpypi\" if is_prerelease else \"pypi\")", workflow)
        self.assertIn("fh.write(f\"publish_target={publish_target}", workflow)
        self.assertIn("fh.write(f\"is_prerelease={'true' if is_prerelease else 'false'}", workflow)
        self.assertIn("needs.build.outputs.publish_target == 'testpypi'", workflow)
        self.assertIn("needs.build.outputs.publish_target == 'pypi'", workflow)

    def test_release_runbook_documents_version_and_environment_policy(self) -> None:
        release_doc = (ROOT / "RELEASING.md").read_text(encoding="utf-8")

        self.assertIn("`project.version` in `pyproject.toml`", release_doc)
        self.assertIn("`v<version>`", release_doc)
        self.assertIn("`v0.1.0rc1`", release_doc)
        self.assertIn("`v0.1.0`", release_doc)
        self.assertIn("`publish-package.yml`", release_doc)
        self.assertIn("Trusted Publishing", release_doc)
        self.assertIn("`testpypi` environment", release_doc)
        self.assertIn("`pypi` environment", release_doc)

    def test_release_runbook_matches_public_package_name(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        release_doc = (ROOT / "RELEASING.md").read_text(encoding="utf-8")

        self.assertEqual(pyproject["project"]["name"], "cureview")
        self.assertIn("https://pypi.org/p/cureview", release_doc)
        self.assertIn("https://test.pypi.org/p/cureview", release_doc)

    def test_release_runbook_documents_proveout_evidence_and_rollback(self) -> None:
        release_doc = (ROOT / "RELEASING.md").read_text(encoding="utf-8")

        self.assertIn("## First Public Release Prove-Out", release_doc)
        self.assertIn("uv build --out-dir dist-public-proveout --clear", release_doc)
        self.assertIn("verify there is no installed `reviewflow` executable", release_doc)
        self.assertIn('verify `python -c "import reviewflow"` fails', release_doc)
        self.assertIn("uvx --from cureview cure init", release_doc)
        self.assertIn("cure doctor --pr-url <public github PR> --json", release_doc)
        self.assertIn("## Evidence Capture", release_doc)
        self.assertIn("public_release_evidence/", release_doc)
        self.assertIn("## Rollback And Hotfix Guidance", release_doc)
        self.assertIn("Do not overwrite or reuse the broken tag.", release_doc)
        self.assertIn("v0.1.1", release_doc)
        self.assertIn("## Standalone Release Assets", release_doc)
        self.assertIn("## Standalone Asset Verification", release_doc)
        self.assertIn("SHA256SUMS", release_doc)
        self.assertIn("install-cure.sh", release_doc)
        self.assertIn("curl -fsSL https://raw.githubusercontent.com/grzegorznowak/CURe/main/install-cure.sh | sh", release_doc)

    def test_publish_workflow_builds_and_releases_standalone_assets(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "publish-package.yml").read_text(encoding="utf-8")

        self.assertIn("build-standalone-assets:", workflow)
        self.assertIn("target_id: linux-x86_64", workflow)
        self.assertIn("target_id: macos-x86_64", workflow)
        self.assertIn("target_id: macos-arm64", workflow)
        self.assertIn("python scripts/build_standalone_release.py --target-id ${{ matrix.target_id }} --output-dir standalone-dist", workflow)
        self.assertIn("standalone-assets-${{ matrix.target_id }}", workflow)
        self.assertIn("pattern: standalone-assets-*", workflow)
        self.assertIn("merge-multiple: true", workflow)
        self.assertIn("cat standalone/*.sha256 > standalone/SHA256SUMS", workflow)
        self.assertIn("actions/github-script@v7", workflow)
        self.assertIn("Publish GitHub Release assets", workflow)

    def test_installer_script_matches_standalone_contract(self) -> None:
        installer = (ROOT / "install-cure.sh").read_text(encoding="utf-8")

        self.assertIn("CURE_INSTALL_BASE_URL", installer)
        self.assertIn("Install the standalone CURe binary from GitHub Releases.", installer)
        self.assertIn("https://api.github.com/repos/grzegorznowak/CURe/releases/latest", installer)
        self.assertIn("cureview-$VERSION-$TARGET_ID.tar.gz", installer)
        self.assertIn("linux-x86_64", installer)
        self.assertIn("macos-arm64", installer)
        self.assertIn("uv tool install cureview", installer)
        self.assertIn('awk -v asset="$asset_name"', installer)
        self.assertIn('sha256sum -c "$selected_sums_path"', installer)

    def test_installer_verifies_only_selected_asset_from_multi_asset_manifest(self) -> None:
        target_id = self._installer_target_id()
        if target_id is None:
            self.skipTest("installer smoke only covers supported Linux/macOS targets")
        if shutil.which("curl") is None or shutil.which("tar") is None:
            self.skipTest("curl and tar are required for installer smoke")

        version_tag = f"v{tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']}"
        asset_name = f"cureview-{version_tag}-{target_id}.tar.gz"
        other_targets = [candidate for candidate in ("linux-x86_64", "macos-arm64", "macos-x86_64") if candidate != target_id]
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            release_dir = tmp / "release" / version_tag
            release_dir.mkdir(parents=True)
            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            staged_binary = tmp / "cure"
            staged_binary.write_text("#!/usr/bin/env sh\nprintf 'cure smoke\\n'\n", encoding="utf-8")
            staged_binary.chmod(0o755)

            archive_path = release_dir / asset_name
            with tarfile.open(archive_path, "w:gz") as tar:
                tar.add(staged_binary, arcname="cure")

            digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
            manifest = "\n".join(
                [
                    f"{'0' * 64}  cureview-{version_tag}-{other_targets[0]}.tar.gz",
                    f"{digest}  {asset_name}",
                    f"{'1' * 64}  cureview-{version_tag}-{other_targets[1]}.tar.gz",
                ]
            )
            (release_dir / "SHA256SUMS").write_text(f"{manifest}\n", encoding="utf-8")

            env = dict(os.environ)
            env["CURE_INSTALL_BASE_URL"] = f"file://{release_dir}"
            subprocess.run(
                [str(ROOT / "install-cure.sh"), "--version", version_tag, "--bin-dir", str(bin_dir)],
                cwd=ROOT,
                env=env,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            result = subprocess.run(
                [str(bin_dir / "cure")],
                cwd=ROOT,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(result.stdout.strip(), "cure smoke")

    def test_public_release_evidence_location_exists_with_contract(self) -> None:
        evidence_readme = (ROOT / "public_release_evidence" / "README.md").read_text(encoding="utf-8")

        self.assertIn("Store Story 05 prove-out logs here.", evidence_readme)
        self.assertIn("Status", evidence_readme)
        self.assertIn("Version / tag", evidence_readme)
        self.assertIn("Commands run", evidence_readme)
        self.assertIn("Verified public command surface", evidence_readme)
        self.assertIn("Rollback / hotfix decision", evidence_readme)
        self.assertIn("Exact next operator action", evidence_readme)

    def test_public_release_evidence_includes_a_real_proveout_log(self) -> None:
        evidence_log = (ROOT / "public_release_evidence" / "2026-03-19-v0.1.0-local-artifact-smoke.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("- Status: partial", evidence_log)
        self.assertIn("- Target: local artifact smoke before the first tag-driven publish", evidence_log)
        self.assertIn("uv build --out-dir /tmp/cure-public-proveout-tm2DEn/dist --clear", evidence_log)
        self.assertIn("installed executable: `cure`", evidence_log)
        self.assertIn("verified absent: `/tmp/cure-public-proveout-tm2DEn/venv/bin/reviewflow`", evidence_log)
        self.assertIn("cure doctor --pr-url https://github.com/chunkhound/chunkhound/pull/220 --json", evidence_log)
        self.assertIn("public GitHub PR access worked without `gh auth login`", evidence_log)
        self.assertIn("there is still no TestPyPI or PyPI publication evidence", evidence_log)

    def test_public_release_evidence_records_publish_blocker_when_github_access_is_missing(self) -> None:
        blocker_log = (ROOT / "public_release_evidence" / "2026-03-19-v0.1.0-publish-blocker.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("- Status: blocked", blocker_log)
        self.assertIn("gh auth status", blocker_log)
        self.assertIn("gh workflow list", blocker_log)
        self.assertIn("git -C /workspaces/cure_workspace/projects/CURe ls-remote --heads origin", blocker_log)
        self.assertIn("You are not logged into any GitHub hosts", blocker_log)
        self.assertIn("Permission denied (publickey).", blocker_log)
        self.assertIn("publish-package.yml", blocker_log)


if __name__ == "__main__":
    unittest.main()
