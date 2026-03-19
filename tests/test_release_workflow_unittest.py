import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReleaseWorkflowTests(unittest.TestCase):
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
        self.assertIn("manual_target == 'testpypi'", workflow)
        self.assertIn(
            "manual_target == 'pypi' && !contains(needs.build.outputs.version, 'a') && !contains(needs.build.outputs.version, 'b') && !contains(needs.build.outputs.version, 'rc') && !contains(needs.build.outputs.version, 'dev')",
            workflow,
        )
        self.assertIn("contains(needs.build.outputs.version, 'a')", workflow)
        self.assertIn("contains(needs.build.outputs.version, 'rc')", workflow)

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
        self.assertIn("uvx --from cureview cure init", release_doc)
        self.assertIn("cure doctor --pr-url <public github PR> --json", release_doc)
        self.assertIn("## Evidence Capture", release_doc)
        self.assertIn("public_release_evidence/", release_doc)
        self.assertIn("## Rollback And Hotfix Guidance", release_doc)
        self.assertIn("Do not overwrite or reuse the broken tag.", release_doc)
        self.assertIn("v0.1.1", release_doc)

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
