# AGENTS.md

## Purpose

This repository defines a vendor-neutral reference architecture and implementation for secure autonomous software-engineering agents. Changes should preserve the central security model: the LLM is not a security boundary. Policy, sandboxing, workload isolation, network controls, IAM and source code management authorization, and deterministic completion checks must remain independent enforcement layers.

## Read first

Before making non-trivial changes, read:

1. [README.md](README.md) or [README.ja.md](README.ja.md)
2. [Architecture](docs/01-architecture.md) ([日本語](docs/ja/01-architecture.md))
3. [Design Principles](docs/02-design-principles.md) ([日本語](docs/ja/02-design-principles.md))
4. [Security Model](docs/03-security-model.md) ([日本語](docs/ja/03-security-model.md))
5. [Adoption Guide](docs/04-adoption-guide.md) ([日本語](docs/ja/04-adoption-guide.md))
6. [Product Mapping](docs/05-product-mapping.md) ([日本語](docs/ja/05-product-mapping.md))

## Core invariants

Do not weaken these invariants without an explicit architectural decision:

- Prompt instructions, `AGENTS.md`, `CLAUDE.md`, Skills, or model reasoning are behavioral controls, not security boundaries.
- Hooks provide semantic/lifecycle policy but are not the sole enforcement mechanism for critical security invariants.
- The OS sandbox constrains filesystem/network capability independently of model behavior.
- Container/Pod isolation protects the host and other workloads independently of the agent sandbox.
- IAM, source code management rulesets, branch protection, and server-side authorization are authoritative for external systems.
- Autonomous agents must use least-privilege, preferably short-lived credentials.
- Direct mutation of protected/default branches must not be part of the normal autonomous path.
- Production-impacting operations require an explicitly designed authorization path; do not add broad production credentials to coding-agent workers.
- MCP and other external tools are part of the security boundary and require server-side authorization.
- Completion is determined by machine-verifiable predicates, not by the model saying that work is complete.
- Autonomous loops must have bounded retries, time, tool calls, and/or cost.

## Architecture conventions

Keep vendor-specific behavior behind adapters. The preferred flow is:

```mermaid
flowchart LR
    V[Vendor Event] --> A1[Vendor Adapter]
    A1 --> N[Normalized Action]
    N --> P[Policy Engine]
    P --> D{Decision}
    D -->|allow| A2[Vendor Adapter]
    D -->|ask| A2
    D -->|deny| A2
    A2 --> R[Vendor-specific response]
```

Do not put Claude Code, Codex, or Devin-specific semantics into the central policy engine unless they represent a genuinely vendor-neutral concept.

Separate the control plane from the execution plane. Durable task state, policy decisions, approvals, budgets, and completion state belong outside model context.

## Repository structure

- [`docs/`](docs/) — English architecture/design/security/adoption documentation
- [`docs/ja/`](docs/ja/) — Japanese documentation corresponding to `docs/`
- [`reference/hooks/`](reference/hooks/) — policy engine and vendor adapter examples
- [`reference/policies/`](reference/policies/) — policy examples
- [`reference/scripts/`](reference/scripts/) — deterministic lifecycle/completion utilities
- [`reference/kubernetes/`](reference/kubernetes/) — workload and network-isolation examples

When changing an English architecture document, update the corresponding Japanese document in the same change where practical. Keep terminology and architectural meaning aligned; the Japanese version does not need to be a literal translation.

## Development rules

- Prefer Python standard library for the small reference policy implementation unless an external dependency provides clear architectural value.
- Keep policy decisions deterministic and testable.
- Prefer structured data over parsing free-form model prose.
- Deny rules must take precedence over approval/allow rules when multiple rules can match.
- Security-critical errors should fail closed wherever the surrounding product/runtime permits it.
- Never embed real secrets, tokens, account identifiers, private endpoints, or production credentials in examples or tests.
- Kubernetes examples must remain non-privileged and must not introduce `hostPath`, host networking, runtime sockets, or broad default egress without explicit security documentation.
- Avoid introducing a generic privileged shell/MCP path as a shortcut around policy.

## Testing

For changes to [`reference/hooks/`](reference/hooks/), run:

```bash
python -m pytest reference/hooks/tests -q
```

Add or update tests for policy behavior. At minimum, preserve coverage for:

- safe read-only Git operations;
- force-push denial;
- protected/default-branch push denial;
- approval-required operations;
- unknown-operation default behavior.

If a change modifies a security invariant, add a regression test when the invariant is machine-testable.

## Documentation expectations

Architecture documentation should distinguish clearly between:

- behavioral guidance;
- semantic policy;
- static permissions;
- OS capability isolation;
- workload isolation;
- external authorization;
- observability/audit.

Do not describe a prompt, hook, deny-list, or model instruction as a complete security control when a lower-level enforcement boundary is required.

Product-specific statements about Claude Code, Codex, or Devin CLI can change over time. Verify current upstream documentation before making claims about hook schemas, sandbox behavior, permission semantics, network filtering, or enterprise enforcement. Keep vendor adapters versionable and avoid assuming identical semantics across products.

## Git workflow

For non-trivial implementation work, prefer:

```mermaid
flowchart LR
    I[Inspect] --> W[Feature branch / worktree]
    W --> M[Implement]
    M --> T[Test]
    T --> V[Verify]
    V --> C[Commit]
    C --> P[Push]
    P --> R[Pull Request]
```

Do not force-push or directly push implementation changes to a protected default branch as part of autonomous operation. Do not merge a PR unless the task explicitly authorizes merge and repository policy permits it.

## Definition of done

A change is complete only when all applicable conditions are true:

- implementation/documentation matches the requested scope;
- relevant tests pass;
- security invariants remain intact;
- English/Japanese documentation is synchronized when applicable;
- Git state contains only intended changes;
- no credentials or sensitive artifacts were introduced;
- any vendor-specific behavior added or changed is documented with its assumptions.
