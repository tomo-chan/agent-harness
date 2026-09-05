# Product Mapping

This project uses a vendor-neutral model. Product features should be mapped into the common layers rather than copied directly into architecture.

| Concern | Claude Code | OpenAI Codex | Devin CLI |
|---|---|---|---|
| Behavioral guidance | CLAUDE.md / rules / skills | AGENTS.md / skills | AGENTS.md / rules / skills |
| Lifecycle policy | Hooks | Hooks | Hooks |
| Pre-tool semantic gate | PreToolUse | PreToolUse | PreToolUse |
| Post-tool validation | PostToolUse | PostToolUse | PostToolUse |
| Approval interception | PermissionRequest | PermissionRequest / approval architecture | PermissionRequest |
| Completion gate | Stop | Stop | Stop |
| Static command/tool policy | Permissions | Rules / approval policy | Permissions |
| OS sandbox | Seatbelt / bubblewrap-based sandbox | Codex sandbox | OS sandbox |
| Network policy | sandbox domain controls | sandbox/network controls | sandbox domain controls; verify current stability before relying on it |
| Central/enterprise policy | managed settings | managed configuration/requirements | Team Settings |
| Observability | hooks / telemetry integrations | OTel / agent-native events | hooks / enterprise analytics |
| Local-to-cloud transition | separate workflows | Codex cloud architecture | explicit `/handoff` capability |

## Claude Code

Claude Code has a broad lifecycle-hook surface and is well suited to rich semantic orchestration. A critical design point is that hook commands themselves must not be assumed to inherit the same sandbox boundary as ordinary agent shell commands. Keep hook code trusted, small and defensive.

## Codex

Codex provides a strong platform-oriented decomposition around sandboxing, approval policy, Rules, managed configuration and telemetry. Its App Server architecture is useful when building an external harness because tool approvals can be surfaced as structured control-plane events. Hook failures must still be evaluated according to the current version's failure semantics; hard invariants belong in independent boundaries.

## Devin CLI

Devin CLI tightly connects Permissions with sandbox scope and provides an explicit autonomous sandbox mode. Its fail-closed sandbox startup behavior is attractive for unattended workloads. Direct edit/write tool behavior and network-filter maturity must be accounted for in the surrounding architecture. Local-to-cloud handoff should be treated as a separate trust-domain transition.

## Portability strategy

Use a normalized internal event model:

```text
Vendor event
   -> Adapter
   -> Normalized Action
   -> Policy Engine
   -> allow / ask / deny (+ reason/context)
   -> Adapter
   -> Vendor response
```

Do not attempt to normalize every vendor feature. Normalize the security and orchestration semantics that the organization owns; retain product-specific capabilities behind adapters when they provide value.
