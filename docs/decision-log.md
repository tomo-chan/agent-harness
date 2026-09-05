# Implementation Decision Log

[日本語](ja/decision-log.md) | [Vendor Harnesses](06-vendor-harnesses.md) | [Application Architecture](07-application-architecture.md) | [README](../README.md)

This log records implementation choices that shape the harness and the application layer built on top of it. Detailed records live under [`docs/decisions/`](decisions/).

## Status vocabulary

- **Accepted** — current design decision.
- **Temporary** — workaround for a current limitation.
- **Superseded** — retained for history but no longer active.
- **Revisit on vendor change** — verify when upstream behavior changes.

## DL-001 — Central vendor-neutral policy engine
- Status: Accepted
- Decision: Normalize vendor hook inputs into a common action model and evaluate them with one deny-first Policy Engine.

## DL-002 — Policy precedence is deny > ask > allow
- Status: Accepted
- Decision: Broad allow rules never override an invariant deny rule through ordering.

## DL-003 — Policy evaluation errors fail closed
- Status: Accepted
- Decision: Invalid policy, malformed input, or adapter evaluation failure yields deny/block at the adapter boundary. Vendor runtime hook failures may still require lower-level controls.

## DL-004 — Codex `ask` is mapped to deny until supported
- Status: Temporary; Revisit on vendor change
- Decision: Central `ask` becomes Codex deny unless a trusted external approval promotes the specific rule.

## DL-005 — Claude Code uses native PreToolUse `ask`
- Status: Accepted; Revisit on vendor change
- Decision: Map central allow/ask/deny directly to Claude Code PreToolUse decisions.

## DL-006 — Devin central `ask` remains fail-closed
- Status: Temporary; Revisit on vendor change
- Decision: Central `ask` remains blocking unless externally approved; native Devin permissions remain a separate layer.

## DL-007 — Project-local hooks locate the active worktree dynamically
- Status: Accepted
- Decision: Resolve the repository root with `git rev-parse --show-toplevel` instead of embedding checkout paths.

## DL-008 — Harness/config files are security-sensitive
- Status: Accepted
- Decision: Changes to `.agent-harness/`, vendor hook config, CI workflows, harness, posture and policy code are approval-class operations.

## DL-009 — Stop hooks use deterministic completion gates
- Status: Accepted
- Decision: Stop hooks invoke a deterministic completion check; retry/time/tool/cost circuit breakers remain external.

## DL-010 — Hooks are defense in depth, not final authority
- Status: Accepted
- Decision: Protected branches, credentials, production systems and network/resource boundaries remain protected by Sandbox, workload isolation, IAM/SCM policy and server-side controls even if hooks fail.

## DL-011 — Sandbox-first credential exposure reduction
Detailed record: [DL-011](decisions/DL-011-sandbox-first-credential-isolation.md).
- Status: Accepted; Revisit on vendor change
- Decision: Use Sandbox and local policy to reduce credential exposure, but treat credential compromise as a possible failure mode. The default remains one Pod / one agent container.

## DL-012 — Validate repository security posture at SessionStart
Detailed record: [DL-012](decisions/DL-012-sessionstart-repository-posture.md).
- Status: Accepted; Revisit on vendor change
- Decision: Run a repository posture check at SessionStart, cache `READY` / `RESTRICTED` / `BLOCKED`, and refresh stale posture before remote SCM mutation.
- Trusted identity: `AGENT_HARNESS_EXPECTED_REPOSITORY` is supplied by the trusted launcher; absence is `UNKNOWN`, mismatch is `BLOCKED`.
- Minimum posture: repository-local `mode` cannot weaken `AGENT_HARNESS_MINIMUM_POSTURE_MODE`, whose default is `restricted`.

## DL-013 — Canonical SCM publication commands
Detailed record: [DL-013](decisions/DL-013-canonical-scm-publication.md).
- Status: Accepted; Revisit on vendor change
- Decision: Autonomous Git publication uses only `git push` and `git push --set-upstream origin HEAD`, followed by semantic repository/branch/upstream validation.
- Compound shell syntax is not autonomous; `gh pr create` cannot override repository/head/base.

## DL-014 — Deterministic application architecture contracts and gates
Detailed record: [DL-014](decisions/DL-014-application-architecture-contracts.md).
- Status: Accepted
- Decision: Separate the Application Layer from the Harness Layer. Application principles become enforced only when represented by deterministic predicates over reproducible evidence.
- Authority: LLM/human architecture review may improve policy but does not emit authoritative gate pass/fail.
- Control plane: architecture contracts, gate implementation, evidence collectors, CI wiring, and waivers are protected artifacts.
- Waivers: explicit, scoped, owned, reasoned, and expiring.

## Maintenance rule

Add or update a decision when a change selects an architecture alternative, compensates for a vendor limitation, changes a trust boundary/failure/approval/security invariant, or changes how application architecture is converted into enforced policy. Preserve history and record upgrade/revisit triggers for temporary decisions.
