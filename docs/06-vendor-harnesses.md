[← Product Mapping](05-product-mapping.md) | [日本語](ja/06-vendor-harnesses.md) | [README →](../README.md)

# Vendor Harness Implementations

The repository contains reference hook wiring for Claude Code, OpenAI Codex, and Devin CLI. All three use the same deny-first Policy Engine, repository posture checker, SCM semantic validator, publication-time control-plane review, and deterministic completion assurance. In production, executable assurance/policy code and trusted baseline policy are resolved from a trusted root outside the agent-mutable workspace.

## Trusted harness boundary

Production harness implementation must not be sourced from the repository/worktree being evaluated. The trusted launcher supplies a root such as:

```bash
export AGENT_HARNESS_TRUSTED_ROOT=/opt/agent-harness
```

The approved harness snapshot is baked or otherwise provisioned into that root by the trusted deployment process. The Kubernetes reference keeps `/opt/agent-harness` on the container read-only root filesystem and `/workspace` as the mutable task workspace.

Project-local hook files invoke:

```text
$AGENT_HARNESS_TRUSTED_ROOT/reference/launcher/trusted_hook.py
```

The wrapper verifies that it is itself executing from the configured trusted root and resolves vendor adapters and semantic policy from that same root. It exports the trusted posture baseline through `AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY`; it does **not** replace the repository-local `.agent-harness/security.json`. The posture checker treats that repository file as untrusted strengthening input. See DL-015 and DL-018.

Project-local `.claude`, `.codex`, and `.devin` files remain reference/development wiring rather than an independent production authority boundary. Where supported, provision hook registration from trusted launcher or managed configuration outside the agent-writable workspace.

## Trusted and repository posture policy

Trusted authority is established first:

```bash
export AGENT_HARNESS_EXPECTED_REPOSITORY=owner/repository
export AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY=/opt/agent-harness/reference/policies/repository-security.example.json
# Optional trusted interactive override:
export AGENT_HARNESS_MINIMUM_POSTURE_MODE=restricted
```

The trusted baseline file provides required controls and cache TTL. A trusted launcher may explicitly select the baseline mode with `AGENT_HARNESS_MINIMUM_POSTURE_MODE`, preserving the interactive `warn` use case. Repository-local `.agent-harness/security.json` is then composed monotonically:

```text
trusted_mode          = launcher override if supplied, else trusted baseline mode
mode_effective        = stricter(trusted_mode, repository_mode)
requirement_effective = trusted OR repository
ttl_effective         = min(trusted, repository)
```

The repository can therefore add requirements or choose a stricter mode, but cannot remove trusted requirements or lengthen the trusted TTL. Repository-local `expected_repository` is only an additional consistency claim; trusted task identity remains `AGENT_HARNESS_EXPECTED_REPOSITORY`. Malformed trusted or repository policy fails closed to `BLOCKED`.

At SessionStart, the checker compares `origin` with trusted expected repository, reads repository metadata, queries effective active GitHub rules on the default branch, normalizes evidence to `pass`, `fail`, or `unknown`, and derives `READY`, `RESTRICTED`, or `BLOCKED`. The resulting session cache is context/performance state only. Mutation enforcement re-evaluates posture from current Git and GitHub evidence rather than trusting that writable cache as authority.

## Canonical autonomous publication

The autonomous direct push path consists only of:

```bash
git push
git push --set-upstream origin HEAD
```

PreToolUse verifies `READY` posture, named non-default current branch, checked `origin`, and expected upstream semantics. Force push is denied, including `--force-with-lease=<ref>` forms. Arbitrary remote/refspec/tag/delete/config-override forms are not autonomous.

Autonomous `gh pr create` may not override repository/head/base and requires the current branch to be published as `origin/<current-branch>`. Compound shell syntax is outside the autonomous allowlist. Repository-authority enforcement conservatively detects remote SCM mutation even when it appears later in a compound command, so `RESTRICTED` cannot be bypassed by an approval on `git status && git push` or equivalent.

## Control-plane publication review

Edit-time path classification is defense in depth, not the complete review boundary. Before canonical push or autonomous PR creation, the harness evaluates:

```text
git diff --name-only origin/<default-branch>...HEAD
```

If the committed branch changes protected control-plane paths such as `.agent-harness/`, vendor hook configuration, CI workflows, harness/posture/policy/launcher code, assurance scripts, deployment references, or `AGENTS.md`, the semantic validator returns `ask` with rule `control-plane-publication`. Trusted external approval may authorize that final review result only after repository authority has been satisfied. If the diff cannot be established, validation fails closed.

This makes the publication decision independent of whether the change was produced by Write/Edit, `apply_patch`, `git restore`, a repository script, or another local mechanism. Production authority still resides in the trusted read-only harness root. See DL-019.

## Authoritative-state completion assurance

SessionStart does not persist an authority-bearing completion snapshot. At Stop, the harness freshly evaluates repository posture and current Git state.

The delivery completion gate is skipped only when the current branch is the checked default branch, the worktree including untracked files is clean, and local `HEAD` exactly equals `origin/<checked-default-branch>`. This is evidence that no local repository delivery is pending. Every feature-branch, dirty, diverged, `BLOCKED`, or otherwise unverifiable state runs the full deterministic delivery gate.

This avoids rejecting clean review/inspection sessions on the default branch without trusting mutable local session evidence. The claim is limited to repository delivery state and does not assert that the session produced no external side effects. See DL-020.

## Vendor notes

### Claude Code

Use SessionStart, PreToolUse, and Stop hooks plus the sandbox. Native PreToolUse `ask` represents central approval-class decisions. Credential-file deny rules and native credential masking are defense in depth; SCM/IAM and server-side rules remain external authority.

### Codex

Use hooks plus Codex sandbox/workspace controls. Central `ask` remains deny unless a trusted external approval promotes the specific rule. Repository posture and server-side controls remain independent of hook approval limitations.

### Devin CLI

Use lifecycle hooks, static permissions, and the Devin sandbox. Keep native `git` and `gh`; do not add an SCM broker solely for credential hiding. Central approval-class decisions remain fail-closed unless explicitly approved through the trusted external path.

## Keep deployment simple

The default remains one Pod / one agent container. Do not introduce a broker, sidecar, `git` shim, or `gh` shim without a concrete threat model. Sandbox and policy reduce exposure; short-lived repository-scoped credentials and least-privilege IAM/SCM constrain compromise; GitHub Rulesets/branch protection remain authoritative server-side controls.

## Validation

```bash
python -m pip install pytest
python -m pytest reference/hooks/tests reference/harness/tests reference/posture/tests -q
AGENT_HARNESS_EXPECTED_REPOSITORY=owner/repository \
  python reference/launcher/preflight.py --json
```

Regression coverage includes trusted-root isolation, monotonic trusted/repository posture composition, trusted launcher mode override, mutation-time posture re-evaluation, compound-shell remote mutation detection, canonical publication, all force-push variants, control-plane publication review, PR Git-state binding, authority-over-approval precedence, authoritative-state read-only completion, and required production-code docstrings.

---

[← Product Mapping](05-product-mapping.md) | [日本語](ja/06-vendor-harnesses.md) | [README →](../README.md)
