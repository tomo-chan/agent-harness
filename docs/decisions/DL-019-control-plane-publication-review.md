# DL-019 — Review control-plane changes at publication time

- Date: 2026-09-06
- Status: Accepted; Revisit on structured mutation support
- Scope: Harness control plane / SCM publication / approval

## Decision

Control-plane changes require explicit approval at the publication boundary, based on the committed branch diff against the remote default branch.

Protected paths currently include:

- `.agent-harness/`
- `.claude/`
- `.codex/`
- `.devin/`
- `.github/workflows/`
- `reference/harness/`
- `reference/hooks/`
- `reference/posture/`
- `reference/policies/`
- `reference/launcher/`
- `AGENTS.md`

Before canonical `git push` or autonomous `gh pr create`, the harness evaluates the changed file set relative to `origin/<default-branch>...HEAD`. If any protected path is present, the semantic validator returns `ask` with rule `control-plane-publication`.

Trusted external approval may authorize that final `ask`. Repository authority state is evaluated first, so `BLOCKED` or `RESTRICTED` cannot be weakened by such approval.

## Rationale

Edit-time path checks are useful but incomplete. A protected file can be changed through multiple mechanisms, including:

- Write/Edit tools;
- `apply_patch`;
- `git checkout` / `git restore`;
- repository scripts;
- arbitrary allowed code execution.

Trying to make every mutation primitive path-aware creates a large and vendor-specific mediation surface. Publication-time diff evaluation instead asks the security-relevant question directly:

> Does the branch being published contain a change to the control plane?

This is independent of how the change was produced.

## RAEM interpretation

The model review identified that the previous refinement mapped the abstract claim “control-plane changes require approval” to edit-time tool classification. That refinement was incomplete because some mutation paths did not expose target paths.

The evolved refinement maps the claim to publication evidence: the Git diff itself. The deterministic assurance rule checks protected paths in that evidence before crossing the remote SCM boundary.

## Failure semantics

If the remote default branch cannot be identified, or the publication diff cannot be established, control-plane publication validation fails closed with `deny`.

## Non-goals

This mechanism does not claim that local control-plane files cannot be modified. Production authority continues to come from the trusted read-only harness root. This decision governs publication/review of repository control-plane changes.

## Revisit triggers

Re-evaluate when vendors expose complete structured mutation targets for all file-changing operations, or when SCM publication moves to a first-class structured API that can carry reviewed path evidence directly.
