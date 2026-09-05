[English](README.md) | [日本語](README.ja.md)

# Agent Harness

Vendor-neutral reference architecture and implementation for secure autonomous software-engineering agents.

The core premise is that an LLM is not a security boundary. Autonomous execution must be constrained by independent lifecycle policy, repository posture checks, OS sandboxing, workload isolation, external IAM/SCM authority, server-side repository rules, and machine-verifiable completion gates.

## Architecture

```mermaid
flowchart TD
    A[Instructions / AGENTS.md / Skills] --> B[Agent Runtime]
    B --> SS[SessionStart posture check]
    SS --> C[Policy Engine]
    B -->|PreToolUse| C
    C -->|allow| D[Permissions / Rules]
    C -->|ask| E[Approval Gateway]
    C -->|deny| X[Deny / restrict]
    E --> D
    D --> F[OS Sandbox]
    F --> G[Single agent container / Pod]
    G --> H[IAM / SCM credential scope]
    H --> I[GitHub / Cloud]
    I --> R[Rulesets / server-side policy]
```

The layers have deliberately different responsibilities:

| Layer | Responsibility |
|---|---|
| Instructions / Skills | Desired behavior, workflow and architecture guidance |
| Trusted launcher state | Authoritative task identity and minimum posture (`AGENT_HARNESS_EXPECTED_REPOSITORY`, minimum mode) |
| SessionStart posture check | Detect repository/security configuration drift before work begins |
| Hooks / Policy Engine | Semantic and lifecycle policy |
| Permissions / Rules | Static command, tool and path classification |
| Sandbox | Reduce filesystem/process/network capability and credential exposure |
| Container / Pod | Host and resource isolation; default baseline is one Pod / one container |
| IAM / SCM policy | Contain credential compromise with least privilege and short-lived scope |
| GitHub rulesets | Authoritative branch/PR/CI enforcement |
| Completion Gate | Machine-verifiable definition of done |
| Telemetry | Audit, incident analysis and policy tuning |

## Repository posture states

At `SessionStart`, the harness checks the actual repository against trusted launcher state and inspects GitHub-side controls such as required PRs, force-push prevention, and required status checks. Each check is `pass`, `fail`, or `unknown`; the session becomes:

- `READY` — normal policy applies;
- `RESTRICTED` — local development is allowed, but remote SCM mutation is denied;
- `BLOCKED` — mutating actions are denied.

The trusted launcher should set `AGENT_HARNESS_EXPECTED_REPOSITORY=owner/repository`. If it is absent, repository identity is `UNKNOWN`, so the default `restricted` minimum prevents remote publication. Repository-local `mode: warn` cannot weaken the default minimum; only a trusted launcher can explicitly lower `AGENT_HARNESS_MINIMUM_POSTURE_MODE` for an interactive use case.

If `.agent-harness/security.json` is missing, built-in `restricted` defaults are used. Invalid explicit configuration is `BLOCKED`. Stale posture is rechecked before remote trust-boundary operations.

## Canonical autonomous publication

The autonomous path deliberately avoids arbitrary shell/refspec parsing. Git publication is limited to:

```bash
git push
git push --set-upstream origin HEAD
```

A semantic validator then confirms `READY` posture, the checked repository, current non-default branch, `origin`, and the expected upstream. Arbitrary remotes, destination refspecs, tags, delete/force forms and configuration overrides are outside the autonomous allowlist. `gh pr create` may not override repository, head branch or base branch. Compound shell syntax such as `&&`, pipes, redirection, newlines and command substitution is also outside the autonomous allowlist.

## Standard autonomous flow

```mermaid
flowchart LR
    T[Task] --> S[SessionStart posture check]
    S --> I[Inspect repository read-only]
    I --> W{Mutation required?}
    W -->|yes| B[Create feature worktree / branch]
    W -->|no| V[Verify result]
    B --> P[Plan]
    P --> E[Edit]
    E --> Q[Test / lint / type-check]
    Q --> G[Policy / completion gate]
    G --> C[Commit]
    C --> U{Posture READY?}
    U -->|yes| PU[Canonical push]
    U -->|no| RS[Remain local / request remediation]
    PU --> PR[Create PR without repo/head/base override]
    PR --> CI[CI / review]
    CI --> M[Protected server-side merge]
```

## Repository layout

- [Architecture](docs/01-architecture.md) ([日本語](docs/ja/01-architecture.md))
- [Design Principles](docs/02-design-principles.md) ([日本語](docs/ja/02-design-principles.md))
- [Security Model](docs/03-security-model.md) ([日本語](docs/ja/03-security-model.md))
- [Adoption Guide](docs/04-adoption-guide.md) ([日本語](docs/ja/04-adoption-guide.md))
- [Product Mapping](docs/05-product-mapping.md) ([日本語](docs/ja/05-product-mapping.md))
- [Vendor Harnesses](docs/06-vendor-harnesses.md) ([日本語](docs/ja/06-vendor-harnesses.md))
- [Implementation Decision Log](docs/decision-log.md) ([日本語](docs/ja/decision-log.md))
- [DL-011: Sandbox-first credential exposure reduction](docs/decisions/DL-011-sandbox-first-credential-isolation.md)
- [DL-012: SessionStart repository posture](docs/decisions/DL-012-sessionstart-repository-posture.md)
- [DL-013: Canonical SCM publication](docs/decisions/DL-013-canonical-scm-publication.md)
- [`reference/harness/`](reference/harness/) — vendor adapters and semantic publication validation
- [`reference/posture/`](reference/posture/) — repository posture checker and cache
- [`policy.example.json`](reference/policies/policy.example.json) — semantic policy
- [`repository-security.example.json`](reference/policies/repository-security.example.json) — repository posture profile
- [`preflight.py`](reference/launcher/preflight.py) — optional launcher/CI preflight
- [`agent-pod.yaml`](reference/kubernetes/agent-pod.yaml) — single-container hardened Pod baseline

## Credential responsibility split

The baseline intentionally does not add an SCM broker or sidecar merely to hide credentials. Sandbox and local policy reduce exposure; short-lived repository-scoped credentials and least-privilege GitHub App/IAM permissions contain compromise; GitHub rulesets preserve protected-branch invariants even if a credential is exposed.

## Guiding rule

> Make safe actions easy and autonomous; detect unsafe environments early; make critical authority boundaries independent of the model and its credentials.
