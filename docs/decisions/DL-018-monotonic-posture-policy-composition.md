# DL-018 — Compose trusted and repository posture policy monotonically

- Date: 2026-09-06
- Status: Accepted; Revisit on policy-model change
- Scope: Repository posture / trusted launcher / repository-local security profile

## Decision

Repository security posture is derived from trusted authority plus an untrusted repository-local overlay.

Trusted authority consists of:

1. the baseline file selected by `AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY` (or built-in restricted defaults); and
2. an optional trusted-launcher mode override, `AGENT_HARNESS_MINIMUM_POSTURE_MODE`, preserving the existing interactive `warn` use case.

The launcher mode override changes only the trusted baseline mode. Requirements and TTL continue to come from the trusted baseline file. After trusted authority has established that baseline, `.agent-harness/security.json` is read as an untrusted repository overlay.

The repository overlay may strengthen the trusted baseline but must not weaken it. For the current policy vocabulary:

```text
trusted_mode          = launcher_mode if explicitly supplied else baseline_file_mode
mode_effective        = max(trusted_mode, mode_repository)
requirement_effective = trusted_requirement OR repository_requirement
ttl_effective         = min(trusted_ttl, repository_ttl)
```

`expected_repository` in the repository overlay remains an additional consistency claim. Trusted task identity continues to come from `AGENT_HARNESS_EXPECTED_REPOSITORY` and cannot be replaced by repository-local configuration.

## RAEM rationale

Trusted-root hardening initially replaced the repository profile entirely. That strengthened one trust boundary but broke the refinement contract in DL-012. The corrected refinement distinguishes authority from extensibility:

> Trusted policy establishes the lower bound. Repository-owned policy may add constraints but cannot remove trusted constraints.

The launcher-mode override is itself trusted authority, not repository input. It therefore may deliberately select `warn` for an interactive session before the repository overlay is applied. The repository still cannot weaken that chosen trusted mode.

## Failure semantics

Malformed trusted baseline, invalid trusted launcher mode, or malformed repository overlay is a control-plane evaluation failure and produces `BLOCKED`.

A missing repository overlay is valid and leaves the trusted baseline unchanged.

## Assurance

Regression tests establish that:

- a trusted launcher may explicitly select `warn` for an interactive use case;
- repository policy cannot weaken a trusted launcher-selected mode;
- repository `warn` cannot weaken trusted `restricted` when no launcher override lowers it;
- repository `false` cannot disable a trusted required control;
- repository policy can strengthen mode and add requirements;
- repository policy can shorten but not lengthen the trusted cache TTL;
- repository-declared identity remains an additional consistency check;
- invalid launcher modes and malformed overlays fail closed.

## Revisit triggers

Re-evaluate when the policy vocabulary gains non-Boolean requirements, ordered constraints, exceptions, scoped capabilities, or another value type for which `OR`/`max`/`min` is not a valid monotonic composition operator.
