from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree

import pytest

import tap05_live_proof_runner as runner


class _Completed:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode


def _write_junit(path: Path, outcomes: dict[str, str]) -> None:
    suite = ElementTree.Element(
        "testsuite",
        tests=str(len(outcomes)),
        failures="0",
        errors="0",
        skipped=str(sum(outcome == "skipped" for outcome in outcomes.values())),
    )
    for node_id, outcome in outcomes.items():
        module, name = node_id.split("::", 1)
        case = ElementTree.SubElement(
            suite,
            "testcase",
            classname=module.removesuffix(".py").replace("/", "."),
            name=name,
        )
        if outcome == "skipped":
            ElementTree.SubElement(case, "skipped")
        elif outcome == "failed":
            ElementTree.SubElement(case, "failure")
    ElementTree.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


def _fake_pytest(
    *,
    returncode: int,
    outcomes: dict[str, str] | None,
    materialize_cases: bool = False,
):
    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        stdout: object,
        stderr: object,
        check: bool,
    ) -> _Completed:
        assert check is False
        assert command == [
            "python",
            "-m",
            "pytest",
            "-vv",
            "--junitxml",
            str(Path(env["CURE_TAP05_PROOF_ROOT"]) / "pytest-junit.xml"),
            *runner.TAP05_NODE_IDS,
        ]
        if outcomes is not None:
            _write_junit(Path(command[5]), outcomes)
        for node_id, outcome in (outcomes or {}).items():
            stdout.write(f"{node_id} {outcome.upper()}\n")
        stderr.write("fake live stderr\n")
        if materialize_cases:
            artifact_root = Path(env["CURE_TAP05_ARTIFACT_ROOT"])
            for case_name in runner.LIVE_CASE_ROOT_NAMES:
                case = artifact_root / case_name
                case.mkdir(parents=True)
                (case / "preserved.txt").write_text(case_name, encoding="utf-8")
        return _Completed(returncode)

    return fake_run


def test_tap05_runner_rejects_zero_exit_when_junit_report_is_absent(
    tmp_path: Path,
) -> None:
    proof_root = tmp_path / "absent-report"

    exit_code = runner.run_proof(
        proof_root,
        subprocess_runner=_fake_pytest(returncode=0, outcomes=None),
    )

    assert exit_code == runner.PROOF_VALIDATION_EXIT
    assert (proof_root / "pytest-exit-code.txt").read_text() == "0\n"
    assert (proof_root / "proof-exit-code.txt").read_text() == (
        f"{runner.PROOF_VALIDATION_EXIT}\n"
    )
    validation = json.loads((proof_root / "proof-validation.json").read_text())
    assert validation["accepted"] is False
    assert "absent" in validation["reason"]


def test_tap05_runner_rejects_all_skipped_junit_report(tmp_path: Path) -> None:
    proof_root = tmp_path / "all-skipped"

    exit_code = runner.run_proof(
        proof_root,
        subprocess_runner=_fake_pytest(
            returncode=0,
            outcomes={node_id: "skipped" for node_id in runner.TAP05_NODE_IDS},
        ),
    )

    assert exit_code == runner.PROOF_VALIDATION_EXIT
    validation = json.loads((proof_root / "proof-validation.json").read_text())
    assert validation["accepted"] is False
    assert validation["passed_node_ids"] == []
    assert sorted(validation["skipped_node_ids"]) == sorted(runner.TAP05_NODE_IDS)


def test_tap05_runner_accepts_exact_five_passes_and_audits_bundle(
    tmp_path: Path,
) -> None:
    proof_root = tmp_path / "exact-success"
    calls = _fake_pytest(
        returncode=0,
        outcomes={node_id: "passed" for node_id in runner.TAP05_NODE_IDS},
        materialize_cases=True,
    )

    exit_code = runner.run_proof(proof_root, subprocess_runner=calls)

    assert exit_code == 0
    assert len(runner.TAP05_NODE_IDS) == 5
    assert len(set(runner.TAP05_NODE_IDS)) == 5
    assert set(runner.LIVE_CASE_ROOT_NAMES) == {
        "ordinary-nonempty-absent",
        "ordinary-nonempty-existing",
        "ordinary-zero-absent",
        "ordinary-zero-existing",
        "watchman-fresh-instance",
    }
    validation = json.loads((proof_root / "proof-validation.json").read_text())
    assert validation == {
        "accepted": True,
        "expected_node_ids": list(runner.TAP05_NODE_IDS),
        "passed_node_ids": list(runner.TAP05_NODE_IDS),
        "reason": "exactly five expected TAP-05 nodes passed",
        "skipped_node_ids": [],
        "unexpected_node_ids": [],
    }
    completion = json.loads((proof_root / "bundle-complete.json").read_text())
    assert completion["pytest_exit_code"] == 0
    assert completion["proof_exit_code"] == 0
    assert completion["proof_validation_accepted"] is True
    invocation = json.loads((proof_root / "invocation.json").read_text())
    assert invocation["environment"]["CURE_RUN_LIVE_CHUNKHOUND"] == "1"
    assert invocation["environment"]["CURE_RUN_LIVE_CHUNKHOUND_WATCHMAN"] == "1"
    assert invocation["environment"]["PYTHONPATH"] == str(runner.REPO_ROOT)
    assert invocation["command"][-5:] == list(runner.TAP05_NODE_IDS)
    assert 'PYTHONPATH="$PWD"' in invocation["rendered_command"]
    assert (proof_root / "pytest-junit.xml").is_file()
    artifact_manifest = json.loads(
        (proof_root / "live-artifacts-manifest.json").read_text()
    )
    assert all(name in artifact_manifest for name in runner.LIVE_CASE_ROOT_NAMES)
    for phase in ("before", "after"):
        manifest = json.loads(
            (proof_root / f"worktree-manifest-{phase}.json").read_text()
        )
        assert "tests/tap05_live_proof_runner.py" in manifest
        assert "tests/daemon_aware_research_calls_smoke.py" in manifest
        assert all(
            row["kind"] in {"file", "symlink", "missing"}
            and (row["sha256"] is None or len(row["sha256"]) == 64)
            for row in manifest.values()
        )
    runtime = json.loads((proof_root / "installed-runtime-identity.json").read_text())
    assert set(runtime) == {"chunkhound", "watchman"}
    assert set(runtime["chunkhound"]) >= {
        "requested_command",
        "resolved_path",
        "sha256",
        "version_output",
    }


def test_tap05_runner_preserves_pytest_failure_as_proof_exit(tmp_path: Path) -> None:
    proof_root = tmp_path / "pytest-failure"

    exit_code = runner.run_proof(
        proof_root,
        subprocess_runner=_fake_pytest(returncode=7, outcomes=None),
    )

    assert exit_code == 7
    assert (proof_root / "pytest-exit-code.txt").read_text() == "7\n"
    assert (proof_root / "proof-exit-code.txt").read_text() == "7\n"
    validation = json.loads((proof_root / "proof-validation.json").read_text())
    assert validation["accepted"] is False
    assert "pytest exited 7" in validation["reason"]


def test_tap05_runner_refuses_proof_root_inside_checkout() -> None:
    forbidden = runner.REPO_ROOT / "would-be-proof-root"
    assert not forbidden.exists()

    with pytest.raises(ValueError, match="outside the source checkout"):
        runner.run_proof(forbidden)

    assert not forbidden.exists()


def test_tap05_runner_refuses_to_reuse_existing_proof_root(tmp_path: Path) -> None:
    proof_root = tmp_path / "existing"
    proof_root.mkdir()
    sentinel = proof_root / "sentinel"
    sentinel.write_text("immutable\n")

    with pytest.raises(FileExistsError):
        runner.run_proof(proof_root)

    assert sentinel.read_text() == "immutable\n"
    assert list(proof_root.iterdir()) == [sentinel]
