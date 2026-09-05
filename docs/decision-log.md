# Implementation Decision Log

[日本語](ja/decision-log.md) | [Vendor Harnesses](06-vendor-harnesses.md) | [README](../README.md)

This log records implementation choices that shape the harness. Detailed records live under [`docs/decisions/`](decisions/).

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
- Upgrade path: Emit native `ask` once Codex reliably enforces it.

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
- Decision: Use Sandbox and local policy to reduce credential exposure, but treat credential compromise as a possible failure mode. The default remains one Pod / one agent container; do not add an SCM broker/sidecar solely to hide credentials.
- Security invariant: Credential compromise must not imply unrestricted repository or organization authority.
- Containment: short-lived repository-scoped credentials, least-privilege GitHub App/IAM, server-side rulesets, audit and revocation.

## DL-012 — Validate repository security posture at SessionStart

Detailed record: [DL-012](decisions/DL-012-sessionstart-repository-posture.md).

- Status: Accepted; Revisit on vendor change
- Decision: Run a repository posture check at SessionStart, cache `READY` / `RESTRICTED` / `BLOCKED`, and refresh stale posture before remote SCM mutation.
- Trusted identity: `AGENT_HARNESS_EXPECTED_REPOSITORY` is supplied by the trusted launcher; absence is `UNKNOWN`, mismatch is `BLOCKED`.
- Minimum posture: repository-local `mode` cannot weaken `AGENT_HARNESS_MINIMUM_POSTURE_MODE`, whose default is `restricted`.
- Missing config: use built-in `restricted` defaults.
- Invalid explicit config: `BLOCKED`.
- Unknown external state: preserve `UNKNOWN`; effective policy mode decides whether it blocks, restricts or warns.
- Enforcement: SessionStart detects/fails fast; PreToolUse enforces; GitHub Rulesets/IAM remain authoritative.

## DL-013 — Canonical SCM publication commands

Detailed record: [DL-013](decisions/DL-013-canonical-scm-publication.md).

- Status: Accepted; Revisit on vendor change
- Decision: Autonomous Git publication uses only `git push` and `git push --set-upstream origin HEAD`, followed by semantic repository/branch/upstream validation.
- Compound shell: compound syntax is not autonomous even when the first command is read-only.
- PR creation: `gh pr create` cannot override repository/head/base in the autonomous path.
- Rationale: avoid attempting to safely interpret arbitrary shell/refspec syntax when a narrow structured publication path is sufficient.

## Maintenance rule

Add or update a decision when a change selects an architecture alternative, compensates for a vendor limitation, changes a trust boundary/failure/approval/security invariant, or is likely to be simplified by future vendor/platform improvements. Preserve history and record upgrade/revisit triggers for temporary decisions.
