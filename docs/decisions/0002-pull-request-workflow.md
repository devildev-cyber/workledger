# 0002. Change `main` only through squash-merged pull requests

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

We want a readable history on `main`, a review step for every change, and automated checks before code lands. The repository is private on a GitHub plan that cannot enforce branch protection.

## Decision

- Every change starts from an issue and is made on a short-lived branch, such as `feat/…`, `chore/…`, `ci/…`, or `docs/…`.
- Branches contain small, focused commits.
- Changes reach `main` only through a pull request that links its issue and passes CI.
- Pull requests are squash-merged, and merged branches are deleted.

## Consequences

- `main` has one commit per pull request, titled after the pull request.
- Detailed commit history stays available on each pull request.
- Because branch protection is unavailable, waiting for green checks before merging is a team rule rather than an enforced setting. Revisit if the plan changes.
