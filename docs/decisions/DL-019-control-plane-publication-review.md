# DL-019 — Review control-plane changes at publication time

- Date: 2026-09-06
- Status: Accepted; Revisit on structured mutation support
- Scope: Harness control plane / SCM publication / approval

## Decision

Control-plane changes require explicit approval at the publication boundary. The changed-path evidence is computed against the exact default-branch head SHA obtained directly from the checked GitHub repository, not against a locally mutable remote-tracking ref.

Protected paths currently include:

- `.agent-harness/`
- `.claude/`
- `.codex/`
- `.devin/`
- `.github/workflows/`
- `.github/pull_request_template.md`
- `reference/claude/`
- `reference/codex/`
- `reference/harness/`
- `reference/hooks/`
- `reference/posture/`
- `reference/policies/`
- `reference/launcher/`
- `reference/scripts/`
- `reference/kubernetes/`
- `AGENTS.md`

Before canonical `git push` or autonomous `gh pr create`, the harness:

1. obtains the checked default branch from freshly evaluated repository posture;
2. queries that checked GitHub repository directly for the default-branch head SHA;
3. verifies that exact commit object is available locally;
4. evaluates `git diff --name-only <github-default-head-sha>...HEAD`;
5. returns `ask` with rule `control-plane-publication` if a protected path changed.

Trusted external approval may authorize that final `ask`. Repository authority state is evaluated first, so `BLOCKED` or `RESTRICTED` cannot be weakened by such approval.

## Rationale

Edit-time path checks are useful but incomplete. A protected file can be changed through Write/Edit tools, `apply_patch`, Git restore/checkout, repository scripts, or arbitrary allowed code execution. Trying to make every mutation primitive path-aware creates a large and vendor-specific mediation surface.

Publication-time diff evaluation instead asks the security-relevant question directly:

> Does the branch being published contain a change to the control plane relative to the authoritative current default-branch head?

This is independent of how the change was produced.

The diff base is itself part of the assurance evidence. A local `origin/<default>` ref is unsuitable as independent remote evidence because repository code running under the same operating-system identity can rewrite `refs/remotes/origin/*`. Therefore the base SHA is obtained directly from GitHub and the local ref is ignored for this authority decision.

## RAEM interpretation

Model Review first identified that the refinement mapped the abstract claim “control-plane changes require approval” to edit-time tool classification. That refinement was incomplete because some mutation paths did not expose target paths. The evolved refinement mapped the claim to publication evidence: the Git diff itself.

A later Model Review applied the same trust-boundary principle to the evidence source and found that `origin/<default>` was still mutable by the evaluated subject. The refinement therefore evolved again:

```text
edit primitive paths                 -> insufficient evidence coverage
local origin/<default> diff base     -> mutable, not remote authority
GitHub default-branch head SHA       -> authoritative remote base evidence
Git diff from that SHA to HEAD       -> local changed-path evidence
```

The first publication-diff implementation also contained a path-normalization defect: using `lstrip("./")` removed the significant leading dot from `.github/...`, causing the protected-path regression test to fail. CI detected the mismatch before merge. The implementation was corrected to remove only literal leading `./` segments.

Together these changes demonstrate the RAEM Evolution loop: Model Review improves both the claim and its evidence model; deterministic assurance then detects concrete deviations from that refined model.

## Failure semantics

If the checked repository/default branch cannot be identified, GitHub cannot provide the current default-branch head SHA, that exact commit object is unavailable locally, or the publication diff cannot be established, control-plane publication validation fails closed with `deny`. It does not fall back to a local remote-tracking ref.

## Non-goals

This mechanism does not claim that local control-plane files cannot be modified. Production authority continues to come from the trusted read-only harness root. This decision governs publication/review of repository control-plane changes.

## Revisit triggers

Re-evaluate when vendors expose complete structured mutation targets for all file-changing operations, or when SCM publication moves to a first-class structured API that can carry reviewed path evidence directly.
