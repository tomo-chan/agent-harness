# DL-020 — Apply delivery completion assurance only to changed repository state

- Date: 2026-09-06
- Status: Accepted; Revisit on task-state support
- Scope: SessionStart / Stop / deterministic completion assurance

## Decision

SessionStart records a deterministic Git snapshot consisting of:

- repository root;
- `HEAD`;
- exact porcelain worktree state, including untracked files.

At Stop, the current snapshot is compared with the SessionStart snapshot.

- If the snapshots are identical, the session is treated as read-only and the delivery completion gate is skipped.
- If repository state changed, the normal deterministic completion gate runs.
- If the baseline is missing, invalid, or cannot be compared reliably, the harness does not assume read-only; it runs the full completion gate.

## Rationale

The previous unconditional Stop gate required a feature branch and upstream for every session. That incorrectly rejected read-only review and inspection sessions on the default branch.

Tool-call history is not sufficient evidence for whether a session changed repository state: an allowed mutation may fail, a process may mutate state indirectly, or a vendor may expose different tool semantics. Comparing actual Git state before and after the session answers the relevant question directly.

## RAEM interpretation

The abstract completion claim applies to delivery work, not to every possible agent session. The previous refinement conflated “session ended” with “repository delivery changed.”

The evolved refinement introduces deterministic evidence for whether delivery state changed. Completion assurance is then selected from that evidence:

```text
unchanged repository state -> read-only completion
changed / unverifiable state -> full delivery completion gate
```

## Failure semantics

Failure to capture or load a valid SessionStart snapshot never bypasses the completion gate. Unknown comparison state selects the stricter full gate.

## Assurance

Regression tests establish that:

- unchanged HEAD and worktree skip the delivery gate;
- changed HEAD runs the full gate;
- changed worktree runs the full gate;
- missing or invalid baseline never implies read-only.

## Revisit triggers

Re-evaluate when vendors expose trusted task type, mutation outcome, or transaction state that can distinguish review/read-only work from delivery work more directly than Git-state comparison.
