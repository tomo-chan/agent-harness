# DL-020 — Derive read-only completion from current authoritative repository state

- Date: 2026-09-06
- Status: Accepted; Revisit on trusted task-state support
- Scope: SessionStart / Stop / deterministic completion assurance

## Decision

Completion assurance does not persist an authoritative SessionStart snapshot in a writable local state directory.

At Stop, the harness re-evaluates repository posture and current Git state. It skips the delivery completion gate only when all of the following are established:

- the authoritative repository posture check succeeds sufficiently to identify the checked default branch;
- the current branch is that checked default branch;
- the worktree, including untracked files, is clean;
- local `HEAD` exactly equals `origin/<checked-default-branch>`.

Every other state, including unverifiable state, executes the normal deterministic delivery completion gate.

SessionStart may emit explanatory completion context, but it does not create an authority-bearing completion baseline.

## Rationale

The original unconditional Stop gate incorrectly rejected read-only review and inspection sessions on the default branch because it required a feature branch and upstream for every session.

A first refinement compared SessionStart and Stop Git snapshots. Model review then found that the persisted snapshot lived in writable local state accessible to repository code executing under the same operating-system identity. Such state cannot serve as independent assurance evidence: the evaluated subject could rewrite the evidence used to decide whether the completion gate runs.

The corrected refinement asks a narrower question at Stop using freshly established evidence:

> Is the repository currently a clean checked default branch exactly equal to its checked remote default branch?

If yes, no local repository delivery is pending and the delivery-specific gate is unnecessary. Otherwise the full gate runs.

## RAEM interpretation

The first refinement solved the read-only-session usability problem but violated the trust requirement for assurance evidence. Model review discovered that mismatch and evolved the refinement again.

```text
mutable session baseline                         -> not authority
fresh posture + current Git/remote equality      -> read-only repository evidence
all other / unknown states                       -> full delivery completion gate
```

The claim is intentionally limited to repository delivery state. It does not prove that the session caused no external-system side effects.

## Failure semantics

Failure to establish repository posture, default branch, branch identity, worktree cleanliness, local HEAD, or the remote default-branch commit never creates a read-only exemption. The normal completion gate remains in force.

## Assurance

Regression tests establish that:

- SessionStart persists no authoritative completion snapshot;
- a clean checked default branch equal to `origin/<default>` skips the delivery gate;
- feature branches run the delivery gate;
- dirty default-branch state runs the delivery gate;
- a diverged default branch runs the delivery gate;
- unavailable or `BLOCKED` posture never creates the read-only exemption.

## Revisit triggers

Re-evaluate when vendors or the trusted launcher expose trusted task type, mutation outcome, or transaction state that can distinguish review/read-only work from delivery work directly without introducing mutable evidence controlled by repository code.
