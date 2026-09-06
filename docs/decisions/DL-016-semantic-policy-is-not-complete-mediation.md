# DL-016 — Semantic policy is not complete mediation

- Status: Accepted; Revisit on vendor/runtime change

## Context

The harness observes vendor lifecycle/tool events such as `PreToolUse` and applies deterministic semantic policy to the action visible at that boundary. This is useful for direct agent-issued operations such as `git push`, `gh pr create`, file edits, or obvious credential extraction.

However, an allowed executable can run arbitrary repository-controlled code internally. For example, `pytest`, `npm test`, a compiler build script, a plugin, or another allowed program may itself spawn `git`, `gh`, an HTTP client, or another process. The vendor hook normally observes the outer invocation, not every secondary process and side effect.

Treating semantic hooks as complete mediation would therefore overstate what the mechanism can establish.

## Decision

The semantic Policy Engine and SCM Semantic Validator govern **agent-issued actions observable at the hook boundary**. They are not the authoritative complete-mediation boundary for arbitrary code executed after an action is allowed.

Critical external-system invariants must remain valid even if an allowed process performs an unobserved secondary action. Those invariants are refined to lower-level authorities such as:

- least-privilege, short-lived, repository-scoped IAM / SCM credentials;
- GitHub Rulesets / branch protection and required pull-request/status-check policy;
- network controls where the threat model requires destination restrictions;
- workload/sandbox capability boundaries for host and local resource protection.

The harness may still deny obvious direct misuse and narrow routine autonomous publication to canonical direct command shapes. Those controls reduce accidental or model-generated misuse but do not prove that no process inside the sandbox can ever attempt a different SCM/network operation.

## RAEM interpretation

The abstract claims are deliberately separated:

1. **Direct semantic-action claim** — agent-issued direct SCM publication accepted by the harness must follow the canonical publication contract.
2. **External authority invariant** — compromise or bypass of local semantic policy must not grant unrestricted repository/organization authority or permit mutation that authoritative server-side policy forbids.
3. **Principle** — local semantic policy should reduce obvious unsafe behavior without being described as a complete security boundary.

This prevents an assurance mechanism from claiming evidence stronger than it actually observes. The local hook provides evidence for the first claim; IAM and GitHub-side policy provide independent evidence/enforcement for the second.

## Consequences

- Verification commands such as `pytest` or `npm test` may remain autonomously runnable when allowed by policy; their execution does not become proof that all nested side effects were semantically mediated.
- Documentation must distinguish direct agent-issued publication from arbitrary nested process effects.
- Security review should evaluate whether lower-level IAM/server-side controls remain sufficient under the assumption that repository-controlled code can execute inside an allowed process.
- Do not introduce generic process interception, SCM brokers, or command shims merely to simulate complete mediation unless a concrete threat model requires it and the added TCB/complexity is justified.

## Revisit triggers

Revisit this decision when a vendor/runtime provides a trustworthy, structured, complete process/network mediation boundary that can observe and enforce nested effects without materially expanding the TCB, or when a deployment threat model requires stronger containment than IAM/server-side policy provides.
