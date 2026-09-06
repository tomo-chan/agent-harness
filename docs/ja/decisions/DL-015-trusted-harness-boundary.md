# DL-015 — Harness Control Plane を Agent 可変 Workspace から分離する

- Status: Accepted
- Date: 2026-09-06

## Context

初期の Reference Wiring では、次のように Active Repository / Worktree 内の Adapter を直接実行していました。

```bash
python3 "$(git rev-parse --show-toplevel)/reference/harness/claude.py"
```

Worktree 移動には便利でしたが、RAEM を用いた Architecture Review により Trust Boundary 上の問題が明確になりました。Policy / Posture / SCM Semantic Validation / Completion Check を実行する実装そのものを、その評価対象である Agent が変更できる構造だったためです。

Policy では Control-plane Path に対する通常の Write / Edit を Approval-class にしていましたが、`git checkout` / `git restore` / `git switch` などの Git 操作では、その Path-aware Tool Rule を経由せず Repository File を置き換えられます。

これは単なる deny rule の不足ではありません。Verifier Self-modification の問題です。独立した Authority Boundary として使う Assurance / Policy Mechanism が、評価対象と同じ Agent-mutable Workspace から実行されるなら、その独立性を保証できません。

## Decision

Production Deployment では、Agent-mutable Workspace の外に Trusted Harness Root を確立しなければなりません。

Trusted Launcher は次を設定します。

```text
AGENT_HARNESS_TRUSTED_ROOT=/opt/agent-harness
```

承認済み Harness Snapshot は Trusted Deployment Process によってこの Path へ Bake / Provision します。Reference Kubernetes Baseline では `/opt/agent-harness` を Container の Read-only Root Filesystem 上に置き、`/workspace` のみを Task 用 Mutable Workspace とします。

各 Vendor Hook Command は `AGENT_HARNESS_TRUSTED_ROOT` 配下の `reference/launcher/trusted_hook.py` を呼び出します。Wrapper は、実際の Install Root が Launcher 指定の Trusted Root と一致することを確認し、同じ Trusted Root から Vendor Adapter、Semantic Policy、Repository Posture Policy を選択します。

Repository-local の `.claude` / `.codex` / `.devin` Hook File は Reference / Development Wiring としては有用ですが、それ自体を独立した Authority Boundary とはみなしません。Production では Vendor が対応している場合、Hook Registration 自体も Agent-writable Workspace の外にある Trusted Launcher / Managed Configuration から Provision すべきです。Vendor が Mutable Project-local Registration しか提供しない場合、その Hook Layer は Defense in Depth に留め、Critical Invariant は Sandbox / Capability Boundary、IAM / SCM Authorization、Server-side Rule で独立して Enforcement します。

## RAEM Interpretation

### Abstract Invariant

独立した Authority Boundary として使用する Assurance / Policy Mechanism は、評価対象自身が変更できる Mutable Implementation に依存してはならない。

### Refinement

1 Pod / 1 Agent Container の Baseline を維持したまま、Trusted Control-plane Artifact と Mutable Repository Workspace を分離する。

### Concrete Realization

```text
/opt/agent-harness       trusted / image-provisioned / read-only
/workspace               agent-mutable repository / worktree
```

`AGENT_HARNESS_TRUSTED_ROOT` が Trusted Installation を識別し、`trusted_hook.py` がその Root から Adapter と Normative Policy を解決します。

### Evidence

Regression Test で、Project Hook Command が Trusted Root を参照すること、Active Worktree から Adapter を解決しないこと、Trusted Root 未設定 / 不一致を拒否すること、Kubernetes Reference で Trusted Root が `/workspace` と分離された Read-only Filesystem 上にあることを確認します。

## Consequences

- `/workspace` 内で `git checkout` / `git restore` / `git switch` や Source Edit を行っても、Production Harness Implementation は置き換わりません。
- Trusted Wrapper 使用時、Repository-local Posture Policy が Production の Normative Policy に暗黙昇格することを防ぎます。
- 1 Pod / 1 Agent Container を維持し、Broker / Privileged Sidecar は追加しません。
- Project-local Hook File を Production Execution の Trust Anchor として説明しません。
- Agent-writable Checkout から Harness を直接実行する構成は Development / Reference Mode であり、Production Trust Model ではありません。

## Non-goals

この Decision は、Hook を Arbitrary Child-process Behavior に対する Complete Mediation Boundary にするものではありません。External Resource については IAM / SCM Scope と Server-side Control が引き続き Authoritative です。この問題は別の Review Finding として扱います。

## Revisit Triggers

Vendor が明確な Trust Semantics を持つ First-class Immutable / Managed Hook Package Mechanism を提供した場合、または Runtime が別途 Provision した Trusted Filesystem Root なしで Signed Policy / Harness Bundle を Attest / Execute できるようになった場合に再評価します。
