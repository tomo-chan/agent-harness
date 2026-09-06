# DL-015 — Keep the harness control plane outside the agent-mutable workspace

- Status: Accepted
- Date: 2026-09-06

## Context

The initial reference wiring executed hook adapters directly from the active repository/worktree with commands such as:

```bash
python3 "$(git rev-parse --show-toplevel)/reference/harness/claude.py"
```

That made worktree movement convenient, but an architecture review using RAEM exposed a trust-boundary problem: the subject being evaluated could also mutate the implementation that performed policy, posture, SCM semantic validation, and completion checks. The policy classified ordinary Write/Edit changes to control-plane paths as approval-class, but Git operations such as checkout/restore/switch could replace repository files without passing through those path-aware tool rules.

This is not only a missing deny rule. It is a verifier self-modification problem. An assurance or policy mechanism cannot claim independence from the subject it evaluates while its executable implementation and normative policy are sourced from the same agent-mutable workspace.

## Decision

Production deployments MUST establish a trusted harness root outside the agent-mutable workspace.

The trusted launcher supplies:

```text
AGENT_HARNESS_TRUSTED_ROOT=/opt/agent-harness
```

The approved harness snapshot is baked or otherwise provisioned into that path by the trusted deployment process. The reference Kubernetes baseline places it on the container read-only root filesystem, while `/workspace` remains the mutable task workspace.

Vendor hook commands invoke `reference/launcher/trusted_hook.py` from `AGENT_HARNESS_TRUSTED_ROOT`. The wrapper verifies that its actual installation root matches the launcher-provided trusted root, selects the vendor adapter from the same trusted root, and pins semantic and repository-posture policy inputs to files inside that trusted root.

The repository-local `.claude`, `.codex`, and `.devin` hook files remain useful reference/development wiring, but they are not an independent authority boundary. For production, hook registration itself SHOULD be provisioned from trusted launcher/managed configuration outside the agent-writable workspace where the vendor provides such a mechanism. If a vendor only exposes mutable project-local registration, the hook layer remains defense in depth and critical invariants must still be enforced independently by sandbox/capability boundaries, IAM/SCM authorization, and server-side rules.

## RAEM interpretation

### Abstract invariant

An assurance or policy mechanism must not depend on mutable implementation controlled by the subject it evaluates when that mechanism is used as an independent authority boundary.

### Refinement

Separate trusted control-plane artifacts from the mutable repository workspace while preserving the one-Pod / one-agent-container baseline.

### Concrete realization

```text
/opt/agent-harness       trusted, image-provisioned, read-only
/workspace               agent-mutable repository/worktree
```

`AGENT_HARNESS_TRUSTED_ROOT` identifies the trusted installation. `trusted_hook.py` resolves adapters and normative policy from that root.

### Evidence

Regression tests assert that project hook commands reference the trusted root, do not resolve adapters from the active worktree, reject a missing/mismatched trusted root, and that the Kubernetes reference keeps the trusted root on a read-only filesystem distinct from `/workspace`.

## Consequences

- `git checkout`, `git restore`, `git switch`, or source edits in `/workspace` cannot replace the production harness implementation selected by the trusted wrapper.
- Repository-local posture policy cannot silently become the production normative policy when the trusted wrapper is used.
- The deployment remains one Pod / one agent container; no broker or privileged sidecar is introduced.
- Project-local hook files are no longer described as the trust anchor for production execution.
- A deployment that executes the harness directly from an agent-writable checkout is development/reference mode, not the production trust model.

## Non-goals

This decision does not make hooks a complete mediation boundary for arbitrary child-process behavior. IAM/SCM scope and server-side controls remain authoritative for external resources. That separate issue is reviewed independently.

## Revisit triggers

Revisit this decision if vendors provide a first-class immutable/managed hook package mechanism with clear trust semantics, or if the runtime can attest and execute signed policy/harness bundles without a separately provisioned trusted filesystem root.
