# DL-020 — Derive read-only completion from current authoritative repository state

- Date: 2026-09-06
- Status: Accepted; Revisit on trusted task-state support
- Scope: SessionStart / Stop / deterministic completion assurance

## Decision

Completion assurance does not persist an authoritative SessionStart snapshot in a writable local state directory and does not treat local remote-tracking refs as remote authority.

At Stop, the harness re-evaluates repository posture and current Git state, then obtains the checked default branch head directly from GitHub. It skips the delivery completion gate only when all of the following are established:

- the authoritative repository posture check identifies the checked repository and default branch;
- the current branch is that checked default branch;
- the worktree, including untracked files, is clean;
- local `HEAD` exactly equals the default-branch head SHA returned directly by GitHub.

Every other state, including unverifiable state, executes the normal deterministic delivery completion gate.

SessionStart may emit explanatory completion context, but it does not create an authority-bearing completion baseline.

## Rationale

The original unconditional Stop gate incorrectly rejected read-only review and inspection sessions on the default branch because it required a feature branch and upstream for every session.

A first refinement compared SessionStart and Stop Git snapshots. Model review found that the persisted snapshot lived in writable local state accessible to repository code executing under the same operating-system identity. Such state cannot serve as independent assurance evidence.

A second refinement removed that snapshot but compared local `HEAD` with `origin/<default-branch>`. Model review then found the same trust problem one layer lower: the local remote-tracking ref is also writable by repository code running under the same identity and therefore cannot represent independent remote authority.

The corrected refinement asks the narrow completion question using freshly established evidence from two authority domains:

> Is the repository currently on the checked default branch with a clean worktree, and does local `HEAD` equal the default-branch head returned directly by the checked GitHub repository?

If yes, no local repository delivery is pending and the delivery-specific gate is unnecessary. Otherwise the full gate runs.

## RAEM interpretation

This decision demonstrates iterative refinement under Model Review. Each version narrowed the claim and improved the authority of the evidence used to support it.

```text
mutable SessionStart snapshot                -> not authority
local origin/<default> remote-tracking ref   -> not remote authority
fresh posture + GitHub branch-head SHA       -> authoritative remote evidence
current local HEAD/worktree                  -> local repository evidence
all other / unknown states                   -> full delivery completion gate
```

The claim is intentionally limited to repository delivery state. It does not prove that the session caused no external-system side effects.

## Failure semantics

Failure to establish repository posture, checked repository/default branch, branch identity, worktree cleanliness, local HEAD, or the GitHub branch-head SHA never creates a read-only exemption. The normal completion gate remains in force.

## Assurance

Regression tests establish that:

- SessionStart persists no authoritative completion snapshot;
- a clean checked default branch whose local HEAD equals the GitHub branch-head SHA skips the delivery gate;
- feature branches run the delivery gate;
- dirty default-branch state runs the delivery gate;
- a local HEAD diverged from GitHub runs the delivery gate;
- a forged local `origin/<default>` ref is not consulted as authority;
- unavailable GitHub branch-head evidence never creates the read-only exemption;
- unavailable or `BLOCKED` posture never creates the read-only exemption.

## Revisit triggers

Re-evaluate when vendors or the trusted launcher expose trusted task type, mutation outcome, or transaction state that can distinguish review/read-only work from delivery work directly without introducing mutable evidence controlled by repository code.
