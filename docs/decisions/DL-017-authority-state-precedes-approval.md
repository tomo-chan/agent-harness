# DL-017 — Authority state precedes approval

- Status: Accepted
- Date: 2026-09-06

## Context

Repository posture produces `READY`, `RESTRICTED`, or `BLOCKED`. The original enforcement path only applied posture after the central policy had returned `allow`. As a result, a mutating operation classified as `ask` could reach a vendor approval path even when repository posture was `BLOCKED`.

That behavior contradicted the documented invariant that `BLOCKED` denies mutation. It also made an authority state weaker than an approval-class policy result.

## Decision

Repository posture is an authority state and is evaluated before ordinary `allow` / `ask` handling for mutating operations.

The precedence is:

```text
non-mutating action
    -> ordinary policy result

mutating action
    -> repository authority state
        BLOCKED    -> deny
        RESTRICTED -> deny remote SCM mutation
        READY      -> continue
    -> ordinary allow / ask / deny semantics
    -> canonical SCM semantic validation where applicable
```

`BLOCKED` therefore cannot be weakened by a native vendor prompt, an `ask` result, or trusted external approval of an ordinary policy rule. Remediation must change the repository posture itself before mutation can proceed.

`RESTRICTED` remains intentionally narrower: it permits local development but denies remote SCM mutation. Approval of an ordinary policy rule does not convert a restricted remote publication into an allowed operation.

## RAEM interpretation

### Abstract invariant

An authority state that declares mutation prohibited must not be weakened by a lower-level approval mechanism.

### Refinement

Separate two kinds of decisions:

1. **Authority-state decisions** — whether the current environment is eligible to perform a class of operation.
2. **Approval decisions** — whether an otherwise eligible operation requires human or external authorization.

Authority eligibility is evaluated first.

### Concrete realization

`reference/harness/common.py` evaluates repository posture for every mutating PreToolUse action before returning an `ask` or consuming an ordinary `allow` result.

### Evidence

Regression tests establish that:

- `BLOCKED` denies an ordinary allowed mutation;
- `BLOCKED` overrides an `ask` mutation;
- `BLOCKED` overrides a mutation already promoted to `allow` by external approval;
- read-only actions remain available while `BLOCKED`;
- `RESTRICTED` continues to allow local mutation while denying remote SCM mutation.

## Consequences

- Vendor-native approval prompts cannot bypass `BLOCKED`.
- External approval is not a posture-remediation mechanism.
- Operators must remediate the failing or unknown posture evidence and re-evaluate it before mutation resumes.
- The distinction between authority and approval becomes explicit and reviewable.

## Revisit triggers

Revisit if repository posture is replaced by a richer capability/authority model, or if future runtimes provide a first-class structured authorization lattice that can represent authority-state precedence without harness-side composition.
