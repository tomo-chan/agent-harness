# DL-018 — Compose trusted and repository posture policy monotonically

- Date: 2026-09-06
- Status: Accepted; Revisit on policy-model change
- Scope: Repository posture / trusted launcher / repository-local security profile

## Decision

Repository security posture is derived from two policy inputs with different authority:

1. a trusted minimum baseline supplied by the launcher or trusted harness installation;
2. an untrusted repository-local overlay at `.agent-harness/security.json`.

The effective policy is a monotonic composition. Repository-local configuration may strengthen the trusted baseline but must not weaken it.

For the current policy vocabulary:

```text
mode_effective        = max(mode_trusted, mode_repository)
requirement_effective = trusted OR repository
ttl_effective         = min(ttl_trusted, ttl_repository)
```

`expected_repository` in the repository overlay remains an additional consistency claim. Trusted task identity continues to come from `AGENT_HARNESS_EXPECTED_REPOSITORY` and cannot be replaced by repository-local configuration.

The trusted baseline path is exposed as:

```text
AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY
```

Production wiring points this variable into the read-only trusted harness root. The repository overlay is deliberately read from the active repository and treated as untrusted input to the composition rule.

## RAEM rationale

The previous trusted-root hardening accidentally replaced the repository profile entirely. That made the concrete model stronger in one dimension but no longer conformed to the refinement contract documented in DL-012.

The refined requirement is therefore not “trust the repository policy” and not “ignore the repository policy.” It is:

> Trusted policy establishes the lower bound. Repository-owned policy may add constraints but cannot remove trusted constraints.

This separates authority from application-specific strengthening while preserving repository-level adaptability.

## Failure semantics

Malformed trusted baseline or malformed repository overlay is a control-plane evaluation failure and produces `BLOCKED`.

A missing repository overlay is valid and leaves the trusted baseline unchanged.

## Assurance

Regression tests establish that:

- repository `warn` cannot weaken trusted `restricted`;
- repository `false` cannot disable a trusted required control;
- repository policy can strengthen mode and add requirements;
- repository policy can shorten but not lengthen the trusted cache TTL;
- repository-declared identity remains an additional consistency check;
- malformed overlays fail closed.

## Revisit triggers

Re-evaluate when the policy vocabulary gains non-Boolean requirements, ordered constraints, exceptions, scoped capabilities, or another value type for which `OR`/`max`/`min` is not a valid monotonic composition operator.
