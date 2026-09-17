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

- Direct `main` pushes are blocked by active repository rules. Land changes
  through pull requests only.
- Version selection follows the executable policy documented in
  [VERSIONING.md](VERSIONING.md). `src.__version__` is the canonical source,
  and Required CI verifies the next SemVer target from reachable release tags
  and Conventional Commit history.
- Release tags are separate from development commits. A release is published
  from a tag whose version exactly matches the tagged source revision.
- Existing published tags must not be moved or reused to retrofit later
  changes. Cut a new version instead.
- Release publication requires the existing package and promotion contracts
  (`package.yml`, `release-guard.yml`, `promote-release.yml`); this process
  document does not replace them.

## Repository-governed contribution protocol

The repository applies the same change protocol regardless of whether the
executor is a human developer, an IDE, a coding agent, a CLI automation, or
another implementation tool. Executor identity does not change acceptance
criteria.

An ordinary change follows this path:

```text
change branch
-> XP test-first implementation
-> local focused gate
-> complete local gate
-> Conventional Commit
-> push branch
-> pull request
-> Required PR Governance
-> Required CI
-> repository rules
-> native GitHub merge
-> main
```

The pull request `Verification` section describes the verification strategy
and references `Required PR Governance` and `Required CI`. Volatile execution
results such as test counts, skipped counts, vulnerability counts, workflow
run numbers, commit SHAs, and artifact hashes belong to the current GitHub
checks and are not copied into durable pull-request prose.

Governance-root maintenance is isolated from ordinary product work. A
governance-maintenance pull request must originate from the same repository,
use a governance/ branch, use a governance-scoped Conventional Commit title,
contain a `## Governance maintenance` section beginning with
`Mode: governance-maintenance`, and modify governance-root paths only.

Once repository native auto-merge is enabled, a contributor with write
permission may arm a pull request for rebase auto-merge. Arming auto-merge is
not approval: GitHub merges only after the repository's required rules and
checks are satisfied. A failing or incomplete pull request remains open.
