# Agent Harness

Vendor-neutral reference architecture and implementation for secure, autonomous software-engineering agents.

This repository turns the operational lessons from Claude Code, OpenAI Codex, and Devin CLI into a reusable agent harness. The core premise is that an LLM is not a security boundary: autonomous execution must be constrained by independent policy, OS isolation, workload isolation, external authorization, and machine-verifiable completion gates.

## Architecture

```text
Instructions / AGENTS.md / Skills
              |
              v
        Agent Runtime
              |
        lifecycle hooks
              v
       Policy Engine
       /     |      \
    allow   ask     deny
      |      |        |
      |   Approval    +--> stop
      |   Gateway
      v
 Permissions / Rules
              |
              v
          OS Sandbox
              |
              v
       Container / Pod
              |
              v
    IAM / SCM / Cloud Policy
              |
              v
       External Systems
```

The layers have deliberately different responsibilities:

| Layer | Responsibility |
|---|---|
| Instructions / Skills | Desired behavior, workflow and architecture guidance |
| Hooks / Policy Engine | Semantic and lifecycle policy |
| Permissions / Rules | Static command, tool and path classification |
| Sandbox | Filesystem and network capability boundary |
| Container / Pod | Process, host and resource isolation |
| IAM / SCM policy | External authority and blast-radius containment |
| Completion Gate | Machine-verifiable definition of done |
| Telemetry | Audit, incident analysis and policy tuning |

## Standard autonomous flow

```text
Task
 -> inspect repository (read-only)
 -> create feature worktree/branch if mutation is required
 -> plan
 -> edit
 -> test/lint/type-check
 -> policy/completion gate
 -> commit
 -> push feature branch
 -> create PR
 -> CI / review
 -> merge by protected server-side workflow
```

The agent should normally be able to perform routine work without human interaction. Human approval is reserved for operations whose risk cannot be bounded safely by static policy or sandboxing.

## Repository layout

- `docs/01-architecture.md` — logical and deployment architecture
- `docs/02-design-principles.md` — design principles and responsibility boundaries
- `docs/03-security-model.md` — threat model and defense-in-depth controls
- `docs/04-adoption-guide.md` — staged adoption guide
- `docs/05-product-mapping.md` — Claude Code / Codex / Devin CLI mapping
- `reference/hooks/policy_engine.py` — vendor-neutral policy engine
- `reference/hooks/pre_tool_use_adapter.py` — hook adapter example
- `reference/policies/policy.example.json` — example policy
- `reference/scripts/completion_gate.sh` — deterministic completion check
- `reference/kubernetes/agent-pod.yaml` — hardened Pod example
- `reference/kubernetes/network-policy.yaml` — default-deny network example

## Non-goals

This project does not attempt to make prompts, AGENTS.md, CLAUDE.md, Skills, or model reasoning into a security mechanism. Those are useful behavioral controls but are not trusted enforcement boundaries.

## Guiding rule

> Make safe actions easy and autonomous; make dangerous actions technically impossible or explicitly approved.
