# Releasing CURe Public Packages

This repo publishes the public CURe package as `cureview`, while the installed console command stays `cure`.

## Release Contract

- `project.version` in `pyproject.toml` is the source of truth for the package version.
- The release tag must be `v<version>` and must match `project.version` exactly.
- Pre-release tags such as `v0.1.0rc1`, `v0.1.0b1`, or `v0.1.0.dev1` publish to TestPyPI.
- Final tags such as `v0.1.0` publish to PyPI.
- The publish workflow is [`.github/workflows/publish-package.yml`](.github/workflows/publish-package.yml).
- The public package pages are:
  - TestPyPI: https://test.pypi.org/p/cureview
  - PyPI: https://pypi.org/p/cureview

## Trusted Publishing Setup

Configure Trusted Publishing on both indices before the first release:

1. Create the `cureview` project on TestPyPI and PyPI if it does not already exist.
2. Add a Trusted Publisher on each index that points at this repository and workflow file:
   - owner/repo: this GitHub repository
   - workflow: `.github/workflows/publish-package.yml`
   - environment: `testpypi` on TestPyPI, `pypi` on PyPI
3. In GitHub, create the matching `testpypi` environment and `pypi` environment.
4. Apply any required reviewers or branch/tag protections to the `pypi` environment before the first production publish.

The workflow uses GitHub OIDC with `pypa/gh-action-pypi-publish@release/v1`, so no long-lived PyPI API token should be stored in repo secrets. The action produces publish attestations unless explicitly disabled; this workflow does not disable them.

## Normal Release Flow

1. Update `project.version` in `pyproject.toml`.
2. Commit the version bump.
3. Create and push the matching tag.
   - TestPyPI prove-out example: `git tag v0.1.0rc1 && git push origin v0.1.0rc1`
   - Production example: `git tag v0.1.0 && git push origin v0.1.0`
4. Wait for `Publish Package` to finish.
5. Verify the package page and install smoke:
   - `uvx --from cureview cure --help`
   - `uv tool install cureview`

## First Public Release Prove-Out

Run the first public prove-out as an explicit evidence-gathering exercise, not as an implicit one-off:

1. Build the exact release artifacts from the tagged tree before publishing:
   - `uv build --out-dir dist-public-proveout --clear`
2. Run a clean-environment local artifact smoke against the built wheel:
   - create a temp root for config/state/cache
   - install the wheel into an isolated environment
   - verify `cure --help`
   - verify there is no installed `reviewflow` executable
   - run `cure init`
   - run `cure install`
   - run `cure doctor --pr-url <public github PR> --json`
3. Push the matching tag and let `publish-package.yml` publish to the appropriate index.
4. Run the published-package smoke with the public commands:
   - `uvx --from cureview cure --help`
   - `uvx --from cureview cure init`
   - `uv tool install cureview`
   - `cure doctor --pr-url <public github PR> --json`
5. Record what actually happened in `public_release_evidence/` before closing the release.

The local artifact smoke is the pre-publish gate. The published-package smoke is the release proof that the public index matches the built artifact.

## Evidence Capture

Store every prove-out log in `public_release_evidence/` with a dated filename such as:

- `public_release_evidence/2026-03-19-v0.1.0rc1-testpypi.md`
- `public_release_evidence/2026-03-19-v0.1.0-pypi.md`

Each evidence log should capture:

- the exact version and tag
- whether the run targeted local artifact smoke, TestPyPI, or PyPI
- the exact commands run
- the observed package/install result
- whether the verified public executable was `cure`
- any blocker with the literal error text
- the rollback or hotfix decision taken
- the exact next operator action

Treat the evidence file, not memory, as the handoff artifact for future sessions.

## Manual Rerun / Recovery

Use the `workflow_dispatch` entry on `publish-package.yml` only for rerunning an existing tag that already matches `project.version`.

- `release_tag` must be an existing `v<version>` tag.
- `target=testpypi` is the safe default for prove-outs and reruns.
- `target=pypi` is reserved for an approved rerun of a final release tag after the TestPyPI path is already understood.

The workflow itself enforces the tag/version match and refuses to publish if `pyproject.toml` is still on the old package name or the wrong version.

## Rollback And Hotfix Guidance

If the prove-out fails before PyPI publication:

1. Do not force a PyPI rerun.
2. Fix the issue on `main`.
3. Bump to a new version or prerelease version.
4. Push a new matching tag and rerun the TestPyPI prove-out first.

If a final release already reached PyPI but the package is not usable:

1. Treat the published files as immutable.
2. Do not overwrite or reuse the broken tag.
3. Document the failure and affected commands in `public_release_evidence/`.
4. Cut a new hotfix version, for example `v0.1.1`.
5. Re-run local artifact smoke, then the publish flow, then the public install smoke.

If the failure is only in the GitHub workflow or index-side configuration:

1. Keep the version/tag decision explicit in the evidence log.
2. Prefer `workflow_dispatch` reruns only when the existing tag is still the correct release candidate.
3. Record whether the failure was GitHub environment protection, Trusted Publisher setup, or index acceptance.
