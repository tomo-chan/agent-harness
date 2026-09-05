[← 設計原則](02-design-principles.md) | [English](../03-security-model.md) | [次: 導入ガイド →](04-adoption-guide.md)

# セキュリティモデル

## Threat Model

Agent が Source / Issue / Web / Tool Output の悪意ある指示、Hallucinated / Destructive Command、Compromised Dependency、Credential 誤露出、Over-privileged MCP、誤った Repository / Worktree、Runaway Retry、Compromised Local Policy、Cloud Metadata / Internal Endpoint へのアクセス試行に遭遇する前提で設計します。

さらに **Credential Compromise は起こり得る**ものとします。GitHub Credential が Agent から見えてしまっても、被害範囲を限定できる構造が必要です。

## Defense in Depth と責務分離

```mermaid
flowchart TD
    M[Model Behavior] --> SS[SessionStart Posture Check<br/>Unsafe Repository Config を検出]
    SS --> H[Semantic Policy / Hooks<br/>Contextual Risk を分類]
    H --> P[Permissions / Rules<br/>Routine Tool Authority を制限]
    P --> S[OS Sandbox<br/>Filesystem / Process / Network Capability を低減]
    S --> C[Single Hardened Container / Pod<br/>Host / Resource を保護]
    C --> I[IAM / SCM Authorization<br/>Credential Compromise を封じ込め]
    I --> R[GitHub Rulesets / Server-side Policy<br/>Authoritative Resource Protection]
```

単一レイヤーに全 Failure Mode を背負わせません。特に Sandbox の責務を「Credential が絶対に漏れないこと」にまで拡張し、Repository Safety をその前提へ依存させないようにします。

## Trusted Computing Base

TCB は小さく保ちます。Baseline には Orchestrator、Policy Engine、Posture Checker、Sandbox Implementation、Workload Isolation、Credential Issuance / Authorization、External Server-side Policy が含まれます。Agent-generated Code と Model Reasoning は Untrusted です。

Credential を隠すだけのための Broker / Sidecar は Default TCB から除外します。Trusted Component と Operational State を増やすためです。

## Repository Posture

SessionStart で Local Policy が前提にする外部条件を確認します。Repository Identity、Default Branch、Required Pull Request、Force-push Prevention、Required Status Checks 等を GitHub から取得可能な範囲で検証します。

Check は3値です。

- `pass`: Control を確認済み
- `fail`: Control が未達であることを確認
- `unknown`: API / Plan / Integration / Permission 等により現在確認不能

`unknown` を勝手に `pass` または `fail` に変換しません。対応は Posture Mode が決定します。詳細は [DL-012](decisions/DL-012-sessionstart-repository-posture.md) を参照してください。

## Credential

Short-lived / Repository-scoped / Least-privilege Credential を優先します。Sandbox の deny path、Environment Hygiene、`gh auth token` や Credential File Read を拒否する Semantic Policy で露出を低減します。

ただし Security Invariant は「Agent が Credential を絶対に観測できない」ではありません。

> Credential Compromise が unrestricted Repository / Organization Authority を意味してはいけない。

Narrow GitHub App / IAM Permission、短い Lifetime、Server-side Ruleset / Branch Protection、Audit / Revoke で Compromise を封じ込めます。Coding に不要な Production Credential は Agent Pod に置きません。

## Sandbox

Sandbox は通常の Filesystem / Process / Network Capability と Secret Exposure を狭めます。Defense Layer ではありますが、唯一の Authority Boundary ではありません。Vendor-native Credential Masking が安定して利用できる場合は追加 Hardening として使いますが、対応しない Vendor に同等機能を再現するためだけに Privileged Broker Infrastructure は追加しません。

## Network

Network Control は Deployment Threat Model に合わせます。Internal Service や Cloud Metadata への露出がある環境では Default-deny Egress が有効です。一方で native `git` / `gh` から GitHub への通信は意図的に許可する場合があります。Network を広く許す場合は Least-privilege Credential と Strong Server-side SCM Policy で補完します。

## Git / SCM

Feature Branch の Routine Work は自律化しやすくします。Force Push、Protected Branch Mutation、Tag / Release、Workflow Modification、Merge は Policy に応じて deny / approval とします。

Remote Mutation 前には Repository Posture `READY` を要求します。`RESTRICTED` では Local Development を許可しながら `git push` / `gh pr create` 等を deny、`BLOCKED` では mutation を deny します。

最終 Authority は SCM Server-side Rule です。Agent Credential が Protected Branch Invariant を bypass できてはいけません。

## Hook Failure Semantics

Hook は Semantic Policy に有効ですが Failure Behavior は Vendor / Version で異なります。Hook Timeout / Crash / Malformed Output が起きても IAM Scope / GitHub-side Protection を破れないようにします。SessionStart Posture Check は Fail-fast / Context Injection、PreToolUse は Semantic Enforcement、GitHub-side Rule は Authoritative Enforcement という分担です。

## Audit

Task / Session / Turn ID、Runtime / Version、Policy Version、Repository Posture と各 Check、Tool / Action、allow / deny / ask、Approval、Execution Result、Commit / PR / CI、Sandbox / Network Denial を Structured Event として記録します。Raw Secret は記録しません。

---

[← 設計原則](02-design-principles.md) | [English](../03-security-model.md) | [次: 導入ガイド →](04-adoption-guide.md)
