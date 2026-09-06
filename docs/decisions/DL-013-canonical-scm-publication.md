# DL-013 — Canonical SCM publication commands

- Date: 2026-09-05
- Status: Accepted; Revisit on vendor change
- Scope: Shell policy / Git publication / GitHub PR creation

## Decision

The autonomous publication path uses narrow canonical commands rather than a broad regex allowlist for arbitrary shell/Git syntax.

Allowed autonomous push forms are:

```bash
git push
git push --set-upstream origin HEAD
```

They are accepted only after semantic validation confirms all of the following:

- repository posture is `READY`;
- the current branch is not the GitHub-reported default branch;
- `origin` still resolves to the repository checked by SessionStart;
- plain `git push` has upstream `origin/<current-branch>`;
- `git push --set-upstream origin HEAD` is used only when no upstream exists yet;
- no arbitrary remote, refspec, tag, delete, force, `-c` configuration override, or destination branch is supplied.

`gh pr create` may not override repository, head branch, or base branch. Autonomous PR creation is bound to the current checked Git state and is accepted only when:

- repository posture is `READY`;
- the current branch is not detached and is not the GitHub-reported default branch;
- `origin` still resolves to the checked repository;
- the current branch is already published with upstream `origin/<current-branch>`.

This intentionally requires canonical branch publication before autonomous PR creation. Repository/head/base are derived from the checked repository and current Git state rather than supplied by the agent.

Compound shell syntax (`&&`, `||`, `;`, pipes, redirection, newlines, command substitution) is outside the autonomous allowlist. It falls back to approval/deny semantics rather than being classified from the first command prefix.

## Rationale

A prefix regex such as `^git status` can misclassify a command like:

```bash
git status && git push origin feature/x
```

as read-only. This violates the invariant that `RESTRICTED` sessions cannot cross the remote SCM authority boundary. Parsing arbitrary shell safely is substantially more complex than the harness needs. Restricting the autonomous publication path reduces parser ambiguity and policy surface area.

The same principle applies to PR creation: denying explicit `--repo`, `--head`, and `--base` overrides is not sufficient if the ambient Git state can point somewhere different from the state previously checked by the harness. Therefore autonomous PR creation is semantically tied to the same current branch, checked `origin`, and expected upstream used by canonical publication.

## Responsibility split

- Policy Engine: classifies only narrow command shapes as autonomous.
- SCM semantic validator: verifies repository, branch, upstream, publication state, and prohibited overrides.
- Repository posture: supplies trusted repository/default-branch context and must be `READY` for publication.
- GitHub IAM/App permissions: limit credential blast radius.
- GitHub rulesets/branch protection: remain the authoritative server-side enforcement boundary.

## Trusted repository identity

`AGENT_HARNESS_EXPECTED_REPOSITORY` is supplied by a trusted launcher/orchestrator and is authoritative. Repository-local `.agent-harness/security.json` may add requirements but cannot establish or override trusted task identity by itself.

The launcher also owns `AGENT_HARNESS_MINIMUM_POSTURE_MODE`. Its default is `restricted`, so repository-local `mode: warn` cannot weaken unattended execution unless a trusted launcher explicitly lowers the minimum for an interactive use case.

## Revisit triggers

Re-evaluate when a vendor exposes structured argv/tool semantics that eliminate shell-string parsing, or provides a first-class SCM publication/PR tool whose repository/ref constraints can be expressed directly. Prefer replacing this validator with the stronger structured primitive rather than expanding shell parsing complexity.
