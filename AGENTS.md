# AGENTS.md

## Purpose

This repository defines a vendor-neutral reference architecture and implementation for secure autonomous software-engineering agents. Preserve the central security model: the LLM is not a security boundary. Trusted task identity, repository posture checks, policy, sandboxing, workload isolation, IAM/SCM authorization, server-side rules and deterministic completion checks remain independent layers.

## Read first

Before making non-trivial changes, read:

1. [README.md](README.md) or [README.ja.md](README.ja.md)
2. [Architecture](docs/01-architecture.md) ([日本語](docs/ja/01-architecture.md))
3. [Design Principles](docs/02-design-principles.md) ([日本語](docs/ja/02-design-principles.md))
4. [Security Model](docs/03-security-model.md) ([日本語](docs/ja/03-security-model.md))
5. [Adoption Guide](docs/04-adoption-guide.md) ([日本語](docs/ja/04-adoption-guide.md))
6. [Product Mapping](docs/05-product-mapping.md) ([日本語](docs/ja/05-product-mapping.md))
7. [Vendor Harnesses](docs/06-vendor-harnesses.md) ([日本語](docs/ja/06-vendor-harnesses.md))
8. [Implementation Decision Log](docs/decision-log.md) ([日本語](docs/ja/decision-log.md))
9. [DL-011: Sandbox-first credential exposure reduction](docs/decisions/DL-011-sandbox-first-credential-isolation.md)
10. [DL-012: SessionStart repository posture](docs/decisions/DL-012-sessionstart-repository-posture.md)
11. [DL-013: Canonical SCM publication](docs/decisions/DL-013-canonical-scm-publication.md)
12. [DL-015: Trusted harness boundary](docs/decisions/DL-015-trusted-harness-boundary.md)
13. [DL-016: Semantic policy is not complete mediation](docs/decisions/DL-016-semantic-policy-is-not-complete-mediation.md)

## Core invariants

Do not weaken these invariants without an explicit architectural decision:

- Prompt instructions, `AGENTS.md`, `CLAUDE.md`, Skills, or model reasoning are behavioral controls, not security boundaries.
- Hooks provide semantic/lifecycle policy but are not the sole enforcement mechanism for critical security invariants.
- Production policy/assurance implementation must execute from a trusted root outside the agent-mutable workspace; repository copies are reference/development artifacts, not the production trust anchor.
- Semantic hooks govern agent-issued actions visible at the hook boundary; they do not claim complete mediation of arbitrary nested processes or side effects launched by an allowed command.
- Trusted launcher/orchestrator state establishes expected repository identity; repository-local config cannot authoritatively redefine task identity.
- Missing trusted repository identity is `UNKNOWN`; repository mismatch is `BLOCKED`.
- Repository-local posture mode cannot weaken the trusted minimum posture mode; the default minimum is `restricted`.
- Repository security posture is checked at SessionStart and revalidated before stale remote trust-boundary operations or after repository-root changes.
- `pass`, `fail`, and `unknown` are distinct posture results; unavailable metadata must not silently become `pass`.
- Missing posture configuration uses built-in `restricted` defaults; invalid explicit policy fails closed to `BLOCKED`.
- `RESTRICTED` preserves local development but denies remote SCM mutation; `BLOCKED` denies mutation.
- Direct autonomous remote publication visible to the harness uses canonical command shapes and semantic validation, not arbitrary shell/refspec parsing.
- Critical external-system invariants remain enforced by least-privilege IAM/SCM authority and server-side policy even if local semantic policy is bypassed by nested code.
- Compound shell syntax is outside the autonomous allowlist even when its first command is read-only.
- The OS sandbox reduces filesystem/process/network capability and credential exposure independently of model behavior.
- Container/Pod isolation protects the host and resources independently of the agent sandbox.
- Default deployment is one Pod / one agent container; do not add broker/sidecar/shim infrastructure without a concrete threat model and Decision Log entry.
- IAM, SCM rulesets, branch protection, and server-side authorization are authoritative for external systems.
- Autonomous agents use least-privilege, preferably short-lived and repository-scoped credentials.
- Credential compromise is considered possible; compromise must not imply unrestricted repository or organization authority.
- Direct mutation of protected/default branches must not be part of the normal autonomous path.
- Production-impacting operations require an explicitly designed authorization path.
- MCP and other external tools are part of the security boundary and require server-side authorization.
- Completion is determined by machine-verifiable predicates, not by model claims.
- Autonomous loops must have bounded retries, time, tool calls, and/or cost.

## Architecture conventions

Keep vendor-specific behavior behind adapters. The preferred flow is:

```mermaid
flowchart LR
    TL[Trusted launcher state] --> RP[Repository Posture]
    SS[SessionStart] --> RP
    V[Vendor PreToolUse] --> A1[Vendor Adapter]
    A1 --> N[Normalized Action]
    N --> P[Policy Engine]
    RP --> P
    P --> D{Decision}
    D -->|allow publish| SV[SCM Semantic Validator]
    D -->|allow local| A2[Vendor Adapter]
    D -->|ask| A2
    D -->|deny| A2
    SV --> A2
    A2 --> R[Vendor-specific response]
```

Do not put vendor-specific semantics into the central policy engine unless they represent a genuinely vendor-neutral concept. Keep authoritative task state outside model context.

## Repository structure

- [`docs/`](docs/) — English architecture/design/security/adoption documentation
- [`docs/ja/`](docs/ja/) — Japanese counterparts
- [`docs/decisions/`](docs/decisions/) — detailed implementation decisions
- [`reference/hooks/`](reference/hooks/) — policy engine
- [`reference/harness/`](reference/harness/) — runnable vendor adapters and SCM semantic validation
- [`reference/posture/`](reference/posture/) — repository security posture checker and state cache
- [`reference/policies/`](reference/policies/) — semantic and repository-security policy examples
- [`reference/launcher/`](reference/launcher/) — trusted hook wrapper and optional preflight utilities
- [`reference/scripts/`](reference/scripts/) — deterministic lifecycle/completion utilities
- [`reference/kubernetes/`](reference/kubernetes/) — simple workload/network isolation examples

When changing an English architecture document, update the corresponding Japanese document in the same change where practical.

## Development rules

- Prefer Python standard library for the small reference implementation unless an external dependency has clear architectural value.
- Keep policy and posture decisions deterministic and testable.
- Prefer structured data over parsing free-form model prose.
- If a required operation can be expressed as a narrow canonical command/argv contract, prefer that over increasingly complex shell regex parsing.
- Treat `&&`, `||`, `;`, pipes, redirection, newlines and command substitution as outside autonomous command allowlists unless a dedicated parser/validator explicitly owns the semantics.
- Direct autonomous Git publication visible at the hook boundary is limited to `git push` and `git push --set-upstream origin HEAD`; validate repository, current branch, default branch, `origin` and upstream before allowing it.
- Autonomous `gh pr create` must not override repository, head branch or base branch.
- Do not interpret an allowed test/build/tool invocation as proof that every nested subprocess or network side effect was mediated by hooks.
- For invariants that must survive nested code execution, refine enforcement to sandbox/workload capability controls, IAM/SCM scope, network policy where required, and authoritative server-side rules.
- Deny rules take precedence over ask/allow rules.
- Security-critical errors fail closed wherever the runtime permits it.
- Never embed real secrets, tokens, account identifiers, private endpoints, or production credentials in examples/tests.
- Deny obvious credential extraction (`gh auth token`, direct reads of known credential stores) as defense in depth, but rely on IAM/SCM scope and server-side rules for compromise containment.
- Keep Kubernetes examples non-privileged and avoid `hostPath`, host networking, runtime sockets, and unnecessary extra containers.
- Do not introduce a generic privileged shell/MCP/SCM proxy as a shortcut around policy or solely to emulate complete mediation.
- Protect `.agent-harness/`, vendor hook config, harness, posture, policy and CI files as control-plane artifacts; production trust must still come from the trusted harness root rather than mutable repository copies.

## Testing

For harness changes, run:

```bash
python -m pytest reference/hooks/tests reference/harness/tests reference/posture/tests -q
```

Preserve regression coverage for safe read-only Git, force-push denial, approval-required actions, credential extraction denial, control-plane file protection, trusted harness root resolution, repository posture state derivation, missing/mismatched trusted repository identity, repository-local mode not weakening trusted minimum, `RESTRICTED` remote-mutation denial, `BLOCKED` mutation denial, compound-shell bypass attempts, non-canonical direct push/refspec rejection, default-branch direct push rejection, origin/upstream mismatch and direct PR repository/head/base override rejection.

## Decision log requirement

Record decisions in [Implementation Decision Log](docs/decision-log.md) or a focused record under [`docs/decisions/`](docs/decisions/). Add/update a decision whenever a change selects an architectural alternative, works around a vendor limitation, changes a trust boundary/failure mode/approval path/security invariant, or may be simplified after a future tool upgrade.

For temporary/vendor-dependent choices, record the limitation, workaround, and revisit trigger. Do not silently erase history; mark superseded decisions or explain the replaced default.

## Documentation expectations

Distinguish trusted task identity, repository posture detection, behavioral guidance, semantic policy, static permissions, SCM semantic validation, OS capability isolation, workload isolation, IAM/SCM containment, server-side enforcement, and observability. Do not describe a prompt, hook, deny-list, sandbox, credential secrecy assumption, or direct-command validator as a complete security control when nested execution or a lower-level authority boundary exists.

Product-specific claims change over time. Verify upstream documentation before changing hook schemas, SessionStart behavior, sandbox/network behavior, permission semantics, or credential-masking guidance.

## Git workflow

```mermaid
flowchart LR
    I[Inspect] --> W[Feature branch / worktree]
    W --> M[Implement]
    M --> T[Test]
    T --> V[Verify]
    V --> C[Commit]
    C --> P[Posture READY?]
    P -->|yes| U[Canonical direct push]
    U --> R[Pull Request]
    P -->|no| L[Remain local / remediate]
```

Do not force-push or directly push to a protected default branch. Do not merge a PR unless the task explicitly authorizes merge and repository policy permits it.

## Definition of done

A change is complete only when implementation/documentation matches scope, relevant tests pass, security invariants remain intact, English/Japanese docs are synchronized where applicable, Git state contains only intended changes, no credentials/sensitive artifacts were introduced, and vendor-sensitive decisions have assumptions/revisit triggers documented.
