# ImageMD versioning contract

ImageMD uses Semantic Versioning 2.0.0 for stable releases and
Conventional Commits for machine-readable change intent.

## Authority

`src.__version__` is the canonical application version.
`pyproject.toml` obtains the package version dynamically from that
attribute.

The executable version contract is
`tests/test_version_contract.py`. Existing release workflows remain
authoritative for package construction and publication.

If prose and executable policy disagree, execution must stop and the
discrepancy must be reconciled before release.

## Public compatibility surface

For ImageMD, the public compatibility surface includes documented CLI
entry points and invocation behavior, user-visible metadata analysis
and repair behavior, externally observable file-processing semantics,
application/package identity, and supported distribution formats.

Internal implementation or architecture is not a public API merely
because it changed.

## Stable version syntax

Stable ImageMD releases use:

`MAJOR.MINOR.PATCH`

Pre-release identifiers and build metadata are not part of the normal
ImageMD release path unless a separate release contract explicitly
authorizes them.

## Source of truth

The version is defined once:

`src.__version__`

Setuptools consumes that value through:

`version = { attr = "src.__version__" }`

Package builders and release metadata must ultimately derive their
version from the same source.

## Required development version

The repository version is derived from the highest reachable stable
release tag matching `vMAJOR.MINOR.PATCH` and the Conventional Commit
subjects after that tag.

The required bump is selected by the highest-impact unreleased change:

- any commit containing the Conventional Commit `!` breaking marker:
  `MAJOR`;
- otherwise, any `feat` commit: `MINOR`;
- otherwise, any unreleased commit: `PATCH`;
- no unreleased commits: keep the published version represented by the
  latest reachable release tag.

Conventional Commits assigns explicit SemVer meaning to `fix`, `feat`,
and breaking changes. The default-to-`PATCH` behavior for other valid
ImageMD commit types is an ImageMD-specific policy. It prevents a
changed post-release repository state from retaining the exact identity
of an already-published release.

During a GitHub `pull_request` verification run, the checked-out
worktree is the synthetic merge result used to test integration with
the target branch. That synthetic merge commit is CI infrastructure,
not authored change intent, and therefore does not participate in
Conventional Commit version classification.

Pull-request version derivation uses the immutable `base.sha` and
`head.sha` values from the GitHub event payload as the semantic history
tips. The merged worktree is still tested normally. This preserves both
integration testing and authored-history SemVer classification without
weakening Conventional Commit grammar.

## Published release identity

A release tag must have the form `vMAJOR.MINOR.PATCH` and its version
must exactly match `src.__version__` at the tagged revision.

Once a version is published, that published version must not be
retroactively changed. A later modification requires a new version.

Published release tags must not be moved or reused to represent
different repository contents.

## Development flow

Required CI evaluates the executable version contract on pull requests
and on `main`.

The first change after a release advances the development version to
the next required target. Additional changes keep that target when they
have equal or lower SemVer impact, or advance it when a higher-impact
change appears.

A release is not created by changing the version alone. Tag creation,
package construction, provenance validation, promotion, and publication
remain separate release-governance operations.
