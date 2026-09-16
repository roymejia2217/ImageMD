# Contributing to ImageMD

This document describes the contributor process. When this prose and the
executable policy disagree, the executable workflows, tests, and rules are
authoritative.

## Steady-state change path

Every change follows the same path:

```text
change branch
  ->
XP test-first change
  ->
focused gate
  ->
full local gate
  ->
local commit
  ->
push branch
  ->
pull request
  ->
Required PR Governance
  +
Required CI
  ->
merge
```

Start from `main` on a change branch. Write the failing behavioral test
first, then the minimum implementation that satisfies it. Run the focused
tests for the touched area, then the full local gate:

```text
uv lock --check
uv run ruff check .
uv run ruff format --check .
uv audit --locked --python-version 3.12 --python-platform x86_64-unknown-linux-gnu
uv run python -m unittest discover -v
uv build --wheel
git diff --check
```

Commit locally, push the branch, and open a pull request. The pull request
must satisfy the executable PR contract enforced by the `Required PR
Governance` check (conventional title plus the `Summary`, `Verification`,
and `Release impact` sections) and the `Required CI` aggregate on top of the
quality job. Every commit in a pull request must use the repository
Conventional Commit subject contract; the quality job validates each commit
subject in the pull-request range before installing dependencies. The
trusted `Required PR Governance` gate additionally validates every commit
subject and every changed-file path from the base revision.

Ordinary pull requests may not modify governance-root paths
(`.github/workflows/`, `.github/actions/`, `ci/`, and the executable
governance contract tests). Governance-root maintenance is a separately
authorized repository-maintenance operation. The executable
workflow and ruleset remain authoritative when this prose disagrees.

## Branch and release rules

- Direct `main` pushes will be disabled by repository rules after bootstrap.
  Land changes through pull requests only.
- Release tags are separate from development commits. A release is published
  from an immutable tag through the existing package and promotion contracts.
- Existing published tags must not be moved to retrofit later changes. Cut a
  new tag instead.
- Release publication requires the existing package and promotion contracts
  (`package.yml`, `release-guard.yml`, `promote-release.yml`); this process
  document does not replace them.
