[← Design Principles](02-design-principles.md) | [日本語](ja/03-security-model.md) | [Adoption Guide →](04-adoption-guide.md)

# Security Model

This security model assumes the agent, repository code, and repository-local configuration may be wrong or adversarial. The LLM is not a security boundary. Critical invariants are distributed across trusted launcher state, a trusted harness implementation, semantic hooks, sandbox/workload capability boundaries, least-privilege IAM/SCM authority, and server-side repository policy.

## Threat model

Assume that an autonomous agent may make an incorrect decision, follow malicious repository instructions, execute repository code with unexpected side effects, attempt direct or indirect credential extraction, mutate control-plane files, or try to publish to an unintended repository/ref. Also assume allowed commands such as tests can launch arbitrary child processes outside hook visibility.

The design therefore does not depend on perfect model behavior, perfect prompt following, or complete hook mediation.

## Trusted authority and repository input

Trusted task identity comes from `AGENT_HARNESS_EXPECTED_REPOSITORY`. The production policy/posture evaluator and semantic validator execute from `AGENT_HARNESS_TRUSTED_ROOT`, outside the agent-mutable workspace.

Repository posture policy has two authority levels. A trusted baseline is supplied by `AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY` or built-in restricted defaults. A trusted launcher may explicitly choose the baseline mode through `AGENT_HARNESS_MINIMUM_POSTURE_MODE`; this preserves an intentional interactive `warn` mode. Repository-local `.agent-harness/security.json` is then treated as untrusted strengthening input.

For the current policy vocabulary:

```text
trusted_mode          = launcher override if supplied, else trusted baseline mode
mode_effective        = stricter(trusted_mode, repository_mode)
requirement_effective = trusted OR repository
ttl_effective         = min(trusted, repository)
```

Repository policy may therefore add controls or select a stricter mode, but it cannot remove trusted requirements or extend the trusted cache lifetime. Repository-local `expected_repository` is only an additional consistency claim; it cannot replace trusted task identity. Invalid trusted or repository posture policy produces `BLOCKED`.

## Repository authority state

SessionStart evaluates repository identity, GitHub metadata, and effective rules applying to the default branch. Each required observation is normalized to `pass`, `fail`, or `unknown`. The effective policy derives one of three authority states:

- `READY`: required evidence satisfies the effective policy, or trusted `warn` mode accepts non-passing evidence as warnings;
- `RESTRICTED`: local development may continue, but remote SCM mutation is denied;
- `BLOCKED`: mutation is denied.

Authority state precedes approval. `BLOCKED` cannot be weakened by native prompts or trusted external approval. `RESTRICTED` cannot be used to authorize remote SCM mutation through an approval path. Cached posture is refreshed after TTL expiry or repository-root change.

## Direct-action semantic policy

Hooks govern agent-issued actions visible at the hook boundary. They do not claim complete mediation of arbitrary nested subprocess effects.

Direct autonomous Git publication is intentionally narrow:

```bash
git push
git push --set-upstream origin HEAD
```

The validator confirms `READY` posture, a named non-default current branch, the checked `origin`, and expected upstream semantics. Force push is denied, including valued `--force-with-lease=<ref>` forms. Autonomous `gh pr create` cannot override repository/head/base and requires the current branch to be published with upstream `origin/<current-branch>`.

Compound shell syntax is outside the autonomous allowlist. For repository-authority enforcement, remote SCM mutation is conservatively detected anywhere in the observed command so `RESTRICTED` cannot be bypassed with a chain such as `git status && git push`.

## Control-plane publication review

Local control-plane files are not the production trust anchor, but changes to them still require explicit review before publication. Edit-time path rules are defense in depth; the path-independent assurance point is the committed publication diff.

Before canonical push or autonomous PR creation, the harness evaluates changed paths relative to `origin/<default-branch>...HEAD`. Protected paths include vendor hook configuration, `.agent-harness/`, CI workflows, harness/posture/policy/launcher implementation, and `AGENTS.md`. If protected paths changed, the result is approval-class `control-plane-publication`. Failure to establish the comparison fails closed.

This protects the review invariant regardless of whether a change was introduced by Write/Edit, `apply_patch`, Git restore/checkout, a repository script, or another local execution path. Production execution authority remains the read-only trusted harness root.

## Credential compromise containment

Credential confidentiality is desirable but not the only security invariant. Allowed repository code may be able to observe or misuse runtime authority even when direct extraction is denied.

The architecture therefore treats credential compromise as a possible failure mode and contains it with short-lived, repository-scoped, least-privilege credentials plus authoritative GitHub-side rules. The default deployment remains one Pod / one agent container; an SCM broker/sidecar is not added solely to hide credentials.

## Completion assurance

Completion is evidence-based, not model-asserted. SessionStart records repository root, `HEAD`, and exact porcelain worktree state including untracked files. Stop compares current state with that baseline.

- unchanged state is deterministic evidence for a read-only session and does not require delivery-specific feature-branch/upstream predicates;
- changed state runs the full deterministic delivery completion gate;
- missing, invalid, or unverifiable baseline never implies read-only and also runs the full gate.

This keeps review/inspection sessions usable while preserving fail-closed delivery assurance for changed repository state.

## Responsibility split

The intended authority split is:

- trusted launcher: task identity and trusted posture-mode intent;
- trusted harness root: policy/evaluator implementation and trusted baseline files;
- repository overlay: application-specific strengthening requirements only;
- semantic hooks: direct observed action classification and lifecycle integration;
- sandbox/container: local capability reduction and workload isolation;
- IAM/SCM credentials: compromise blast-radius containment;
- GitHub Rulesets/branch protection: authoritative remote repository enforcement;
- deterministic tests/gates: conformance evidence for defined claims;
- human/agent Model Review: discovery of unknown gaps not represented by existing assurance rules.

No single layer is described as complete security enforcement.

## Failure semantics

Security-critical evaluation errors fail closed where the runtime permits it. `unknown` remains distinct from `fail`: unavailable external evidence is never silently promoted to `pass`. A missing optional repository overlay is valid because the trusted baseline remains effective; malformed explicit policy is a control-plane failure.

## RAEM interpretation

This implementation separates claims from mechanisms and evidence. Model Review has already discovered several gaps: worktree-resident verifier self-modification, hook overclaiming of complete mediation, approval bypass of `BLOCKED`, incomplete SCM state binding, repository-policy masking, edit-path-only control-plane review, and read-only Stop failures. Stable findings were generalized into decisions and deterministic regression tests.

A notable example occurred after DL-019: the first publication-diff implementation incorrectly normalized `.github/...` and the new deterministic regression test failed in CI. The defect was corrected before merge. Reviews improved the model; assurance then exposed a concrete refinement defect.

---

[← Design Principles](02-design-principles.md) | [日本語](ja/03-security-model.md) | [Adoption Guide →](04-adoption-guide.md)
