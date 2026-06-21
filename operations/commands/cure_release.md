# `cure_release`

This is the canonical repo-owned release command for CURe. It is an agent-assisted checklist for the release policy in [RELEASING.md](../../RELEASING.md); a maintainer remains responsible for every publish decision and explicit checkpoint.

If this file and [RELEASING.md](../../RELEASING.md) disagree, `RELEASING.md` wins. This file is not authorization to release unattended.

## Command Name

`cure_release`

## Arguments

- `VERSION="<patch|minor|major|X.Y.Z>"` with default `patch`
- `MODE="<normal|rerun>"` with default `normal`

## Non-Negotiable Contract

- Release only from `origin/main`.
- Use the latest `vX.Y.Z` tag as the previous release boundary.
- Refuse a normal patch release when `origin/main` has no unreleased commits since the previous release tag.
- Update `CHANGELOG.md` before the release commit.
- Build changelog notes from merged PRs in the unreleased range. Use story or epic metadata only as internal drafting help, not as published labels by default.
- `MODE="rerun"` is only for rerunning an existing matching tag. It must never be used to publish changed code under an old version.
- Run the local prove-out gate before any tag push.
- After tag push, watch `Publish Package`, report the workflow URL and result, confirm whether the GitHub release is visible, then run the documented public-package smoke.

## Required Inputs

- Network access for GitHub and package verification
- GitHub authentication that can inspect workflow runs and releases
- A clean working tree before starting, except for the intentional release edits in this flow
- Maintainer confirmation at each explicit checkpoint

## Workflow

### 1. Resolve The Repo And Release Boundary

1. Work from the repo root: `projects/CURe`.
2. Fetch the latest remote state and tags:
   - `git fetch --tags origin`
3. Confirm the release source is exactly `origin/main`:
   - local branch is `main`
   - `HEAD` matches `origin/main`
   - the working tree is clean before release edits begin
4. Resolve the latest release tag:
   - `PREV_TAG=$(git tag --list 'v*' --sort=-version:refname | head -n 1)`
5. Resolve the unreleased range:
   - normal mode: `${PREV_TAG}..origin/main`
   - rerun mode: the existing target tag only

### 2. Resolve The Target Version

1. Read `project.version` from `pyproject.toml`.
2. In `MODE="normal"`:
   - if `VERSION` is `patch`, `minor`, or `major`, derive the next semver from `PREV_TAG`
   - if `VERSION` is an explicit `X.Y.Z`, use it as the target version
   - if the target is a patch release and the unreleased range is empty, stop instead of cutting a no-op patch release
3. In `MODE="rerun"`:
   - require `VERSION` to resolve to an existing tag `vX.Y.Z`
   - require `project.version == X.Y.Z`
   - require the checked-out commit to match the existing release tag
   - stop if the repo contains any code or packaging changes that would alter the published artifact

### 3. Draft The Changelog Before The Release Commit

1. Gather merged PRs that landed in the unreleased range since `PREV_TAG`.
2. Cross-check the PR list against `git log ${PREV_TAG}..origin/main --oneline` so the changelog covers the real release delta.
3. Curate user-facing notes in `CHANGELOG.md`:
   - group by impact, not raw commit order
   - use concise public language
   - do not publish story or epic IDs by default
4. Keep older release sections intact.

### 4. Explicit Checkpoint Before Version Bump

Pause for maintainer confirmation after reporting:

- previous tag
- unreleased commit range
- resolved target version
- draft changelog sections that will ship
- whether this is `normal` or `rerun`

Do not edit `pyproject.toml` or `CHANGELOG.md` until this checkpoint is approved.

### 5. Update Release Metadata

1. In `MODE="normal"`:
   - update `project.version` in `pyproject.toml` to the target version
2. Update `CHANGELOG.md` with the curated release entry before the release commit.
3. If a small release-blocking fix is required on `main`, keep the scope targeted and record it in the changelog trail for the same release.

### 6. Run The Local Prove-Out Gate

Run these commands before any tag push:

- `python -m unittest discover -s tests -p 'test_release_workflow_unittest.py'`
- `python -m unittest discover -s tests -p 'test_*.py'`
- `ruff check tests/test_release_workflow_unittest.py`
- touched-file lint only if the release itself required a code or test fix
- `mypy`
- `uv build --out-dir dist-public-proveout --clear`
- `uvx twine check dist-public-proveout/*`

Then run the isolated wheel smoke:

1. Install the built wheel into a temp virtual environment.
2. Verify `cure --help`.
3. Verify there is no installed `reviewflow` executable.
4. Verify `python -c 'import reviewflow'` fails.
5. Run `cure setup`.
6. Run `cure doctor --pr-url https://github.com/chunkhound/chunkhound/pull/220 --json`.

### 7. Explicit Checkpoint Before Commit, Tag, And Push

Pause for maintainer confirmation after reporting:

- exact files changed for the release
- local prove-out commands and results
- the final commit message and tag that will be created

Do not commit, tag, or push until this checkpoint is approved.

### 8. Commit, Tag, And Push

1. Commit the release changes, including:
   - `pyproject.toml`
   - `CHANGELOG.md`
   - any approved release-blocking fix
2. Create the matching final tag `vX.Y.Z`.
3. Push `main` and the tag to `origin`.

### 9. Watch `Publish Package` And Verify Remote Release State

After pushing:

1. Watch the `Publish Package` workflow run for the new tag.
2. Report the workflow URL and final status.
3. Confirm whether the matching GitHub release is visible with the expected standalone assets.
4. Update the GitHub Release body with the matching `CHANGELOG.md` entry for this version. The GitHub Release description must always mirror the curated changelog, not the auto-generated PR list. Preserve the `**Full Changelog**` compare link at the bottom.

### 10. Run Post-Publish Public-Package Smoke

Run the documented public smoke from [RELEASING.md](../../RELEASING.md):

- `uvx --from cureview cure --help`
- `uvx --from cureview cure setup`
- `uv tool install cureview`
- `cure doctor --pr-url <public github PR> --json`

If the standalone release channel was produced for this tag, also verify the GitHub Release assets and `install-cure.sh` flow as described in [RELEASING.md](../../RELEASING.md).

### 11. Explicit Checkpoint For Non-Happy-Path Recovery

Pause before any recovery action that changes code, tags, or published state.

- If local prove-out fails before publish, fix `main`, bump to a new final version, rerun the prove-out, and do not reuse the failed tag.
- If the workflow or package index needs a rerun and the existing tag still matches the intended release, use `MODE="rerun"` with that exact tag only.
- If a final release already reached PyPI but is broken, treat it as immutable and cut a new hotfix version instead of replacing artifacts.

If the issue is not a narrow release-blocking fix, stop and hand off with the exact blocker.
