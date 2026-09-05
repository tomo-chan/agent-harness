# Implementation Decision Log

[日本語](ja/decision-log.md) | [Vendor Harnesses](06-vendor-harnesses.md) | [README](../README.md)

This log records implementation decisions that materially shape the harness, especially decisions caused by current vendor limitations. Entries marked **Revisit on vendor change** must be re-evaluated when the corresponding tool adds or changes relevant capabilities.

Detailed decision records may live under [`docs/decisions/`](decisions/). Current detailed record: [DL-011 — Sandbox-first credential isolation](decisions/DL-011-sandbox-first-credential-isolation.md).

## Status vocabulary

- **Accepted** — current design decision.
- **Temporary** — workaround for a known current limitation.
- **Superseded** — no longer active; retained for history.
- **Revisit on vendor change** — periodically verify against current upstream behavior.

## DL-001 — Central vendor-neutral policy engine

- Date: 2026-09-05
- Status: Accepted
- Scope: Claude Code / Codex / Devin CLI
- Decision: Normalize vendor hook inputs into a common action model and evaluate them with one deny-first Policy Engine. Vendor-specific code only translates input/output schemas.
- Rationale: Security policy belongs to the organization, not to a vendor-specific hook format. Thin adapters reduce semantic drift and allow common regression tests.
- Consequence: Vendor-only capabilities may remain outside the normalized model when they do not represent an organization-owned security semantic.
- Revisit trigger: A vendor introduces a materially stronger policy abstraction that can be consumed directly without coupling the core policy to that vendor.

## DL-002 — Policy precedence is deny > ask > allow

- Date: 2026-09-05
- Status: Accepted
- Scope: Shared Policy Engine
- Decision: Evaluate deny rules before ask rules and ask rules before allow rules, independent of JSON ordering.
- Rationale: A broad allow rule must not override a security invariant accidentally.
- Consequence: Exceptions should be represented narrowly rather than by relying on rule order.
- Revisit trigger: Only if the policy language is replaced with an explicit conflict-resolution model of equal or stronger safety.

## DL-003 — Policy evaluation errors fail closed

- Date: 2026-09-05
- Status: Accepted
- Scope: Shared Policy Engine / adapters
- Decision: Invalid policy, malformed input, or adapter-side evaluation failure produces a deny/block decision at the adapter boundary.
- Rationale: Policy infrastructure failure must not silently expand authority.
- Limitation: A vendor runtime may itself treat hook process failure as fail-open before a valid deny response can be produced. OS sandbox, Pod isolation, IAM, SCM rules, and server-side protections remain authoritative.
- Revisit trigger: A vendor adds an enforceable fail-closed hook failure mode; enable it and record the change here.

## DL-004 — Codex `ask` is mapped to deny until supported

- Date: 2026-09-05
- Status: Temporary; Revisit on vendor change
- Scope: Codex PreToolUse adapter
- Decision: A central-policy `ask` result is converted to Codex `permissionDecision: deny` unless a trusted external launcher promotes that specific rule to allow through `AGENT_HARNESS_APPROVED_RULES`.
- Rationale: Current Codex schemas parse `permissionDecision: "ask"`, but current runtime behavior does not support it as an enforcing PreToolUse outcome; unsupported output can cause the hook to fail while the tool call continues. Failing closed is safer.
- Upgrade path: When Codex natively enforces PreToolUse `ask`, change the adapter to emit native `ask`, add a conformance test, and remove the temporary mapping.
- Verification source: Current OpenAI Codex hook schema/runtime behavior and upstream issue tracking must be rechecked before each change.

## DL-005 — Claude Code uses native PreToolUse `ask`

- Date: 2026-09-05
- Status: Accepted; Revisit on vendor change
- Scope: Claude Code adapter
- Decision: Emit Claude Code's native `permissionDecision` values `allow`, `ask`, and `deny` for PreToolUse.
- Rationale: Claude Code currently supports semantic pre-tool permission decisions suitable for this policy model.
- Consequence: Interactive approval is available without converting central `ask` to a hard denial.
- Revisit trigger: Hook response schema or permission semantics change.

## DL-006 — Devin central `ask` is blocked; native permissions remain separate

- Date: 2026-09-05
- Status: Temporary; Revisit on vendor change
- Scope: Devin CLI adapter
- Decision: Central-policy `ask` is emitted as a blocking decision unless externally approved. Devin's own static Permissions may still provide native prompts independently.
- Rationale: Keep one deterministic central-policy contract and avoid assuming that every hook-level `ask` maps identically across vendors.
- Upgrade path: If Devin exposes a stable hook response that can request approval with the semantics needed by this harness, map central `ask` to it and add conformance tests.

## DL-007 — Project-local hooks locate the active worktree dynamically

- Date: 2026-09-05
- Status: Accepted
- Scope: `.claude/settings.json`, `.codex/hooks.json`, `.devin/hooks.v1.json`
- Decision: Hook commands resolve the repository root with `git rev-parse --show-toplevel` instead of embedding an absolute checkout path.
- Rationale: The intended workflow moves a single agent session between a control checkout and task-specific Git worktrees.
- Consequence: Hooks remain portable across checkout locations while still using the harness version committed in the active worktree.
- Revisit trigger: Vendor runtimes provide a guaranteed repository-root variable or first-class project hook executable path that is safer than invoking Git.

## DL-008 — Harness/config files are treated as security-sensitive

- Date: 2026-09-05
- Status: Accepted
- Scope: Shared policy
- Decision: Changes to agent configuration, CI workflows, and harness control files are approval-class operations rather than ordinary source edits.
- Rationale: Project-local hooks and agent instructions can modify the effective control plane and are a supply-chain/security boundary.
- Consequence: Autonomous source edits remain easy while policy/control-plane edits receive stronger review.
- Revisit trigger: None expected; exact protected path set may evolve.

## DL-009 — Stop hooks use a deterministic completion gate

- Date: 2026-09-05
- Status: Accepted
- Scope: All vendor adapters
- Decision: Stop hooks invoke `reference/scripts/completion_gate.sh`; failed completion checks block completion.
- Rationale: Model-generated claims of completion are not authoritative.
- Consequence: External orchestrators must additionally enforce retry/time/tool/cost circuit breakers to avoid unbounded self-repair loops.
- Revisit trigger: Vendor runtimes gain richer durable task-state/completion APIs; integrate them without removing deterministic verification.

## DL-010 — Hooks are defense-in-depth, not the final security boundary

- Date: 2026-09-05
- Status: Accepted
- Scope: Entire architecture
- Decision: Never rely on hook success alone to protect protected branches, production systems, credentials, host resources, or network boundaries.
- Rationale: Hook failure semantics and coverage vary by vendor/version. External capability boundaries remain effective even when the model or hook layer fails.
- Consequence: Production deployment still requires sandboxing, container/Pod hardening, egress controls, short-lived IAM/SCM credentials, and server-side rulesets.
- Revisit trigger: No vendor feature should supersede this without an explicit threat-model review.

## DL-011 — Sandbox-first credential isolation

Detailed record: [DL-011 — Sandbox-first credential isolation](decisions/DL-011-sandbox-first-credential-isolation.md).

- Date: 2026-09-05
- Status: Accepted; Revisit on vendor change
- Scope: Claude Code / Codex / Devin CLI / SCM authentication
- Decision: Prefer native sandbox credential masking/mediation. Only use a narrow SCM broker when the current vendor sandbox cannot preserve credential confidentiality while retaining required `git` / `gh` capability.
- Security invariant: The agent may possess GitHub capability but must not possess reusable GitHub credentials as readable data.
- Upgrade path: Remove the broker for any vendor that gains a sufficiently strong native credential-masking or first-class authenticated SCM capability.

## Maintenance rule

When implementing or changing behavior, add an entry when the change:

1. selects one architectural alternative over another;
2. compensates for a current vendor limitation or bug;
3. changes a trust boundary, failure mode, approval path, or security invariant; or
4. should be reconsidered when Claude Code, Codex, Devin CLI, Kubernetes, SCM, or another dependency gains new capabilities.

For temporary decisions, always record the **upgrade path** or **revisit trigger**. Do not silently remove historical entries; mark them Superseded and link to the replacement decision.
