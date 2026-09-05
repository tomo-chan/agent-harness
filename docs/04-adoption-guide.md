[← Security Model](03-security-model.md) | [日本語](ja/04-adoption-guide.md) | [Next: Product Mapping →](05-product-mapping.md)

# Adoption Guide

Adopt autonomy progressively. Each stage should have explicit exit criteria and observable evidence before expanding authority. Review the [Security Model](03-security-model.md) before expanding privileges.

## Stage 0 — Observe

Run the agent read-only. Enable detailed telemetry and collect the commands/tools it wants to use.

Exit criteria:
- common workflows identified;
- required domains and tools inventoried;
- sensitive paths/resources classified;
- baseline cost and failure rates known.

## Stage 1 — Workspace mutation

Permit writes only inside a disposable task worktree. Keep network restricted. Require human approval for shell actions not explicitly classified safe.

Exit criteria:
- reliable worktree selection;
- deterministic tests/lint/type checks;
- no writes outside intended workspace;
- rollback is trivial.

## Stage 2 — PR automation

Allow commit, feature-branch push and PR creation using a repository-scoped short-lived credential. Protect the default branch server-side.

Exit criteria:
- direct protected-branch mutation impossible;
- completion gate validates Git/PR state;
- CI is authoritative;
- audit events correlate task -> commit -> PR.

The reference completion check is [`completion_gate.sh`](../reference/scripts/completion_gate.sh).

## Stage 3 — Unattended operation

Move routine actions to allow rules. Add an external approval gateway for exceptional operations. Introduce turn/time/tool/cost budgets and failure circuit breakers. See [`policy.example.json`](../reference/policies/policy.example.json) for a minimal classification example.

Recommended approval candidates:
- expanding filesystem/network scope;
- accessing sensitive data;
- modifying CI/security policy;
- force operations;
- production-impacting cloud actions.

## Stage 4 — Production-adjacent workflows

Only after strong isolation and IAM controls are proven should agents interact with staging or production-adjacent systems. Prefer read-only diagnostics and deployment through existing CI/CD systems rather than direct agent deployment.

## Suggested implementation order

1. Define normalized action and policy schemas.
2. Implement central [`policy_engine.py`](../reference/hooks/policy_engine.py) and unit tests.
3. Add vendor hook adapters; the repository contains [`pre_tool_use_adapter.py`](../reference/hooks/pre_tool_use_adapter.py) as a minimal example.
4. Configure static permissions/rules.
5. Enable fail-closed OS sandbox where supported.
6. Harden container/Pod using [`agent-pod.yaml`](../reference/kubernetes/agent-pod.yaml) as a starting point.
7. Add default-deny network controls and egress path; see [`network-policy.yaml`](../reference/kubernetes/network-policy.yaml).
8. Replace static credentials with workload identity/short-lived tokens.
9. Add worktree lifecycle management.
10. Implement deterministic completion gate.
11. Integrate PR/CI state.
12. Add external approval workflow.
13. Export structured telemetry.
14. Introduce subagents only after the parent lifecycle is reliable.

## Policy development workflow

Treat policy as code:

- version it;
- unit-test allow/deny/ask cases;
- add regression tests for incidents;
- review policy changes like security-sensitive code;
- deploy policy independently from prompts where possible;
- record policy version with every decision.

Start restrictive and use telemetry to identify safe operations worth auto-allowing. Do not start permissive and attempt to enumerate every dangerous command.

## Operational metrics

Useful metrics include:

- autonomous completion rate;
- human approvals per task;
- denied operations per task;
- policy false-positive rate;
- retries after verification failure;
- median task wall-clock time;
- token/compute cost per completed task;
- PR CI success on first attempt;
- escaped defects/reverts;
- sandbox/network denial counts;
- tasks terminated by budget/circuit breaker.

The target is not maximum autonomy. The target is the highest autonomy that remains bounded, observable and recoverable.

---

[← Security Model](03-security-model.md) | [日本語](ja/04-adoption-guide.md) | [Next: Product Mapping →](05-product-mapping.md)
