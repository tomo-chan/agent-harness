[← セキュリティモデル](03-security-model.md) | [English](../04-adoption-guide.md) | [次: 製品マッピング →](05-product-mapping.md)

# 導入ガイド

自律化は段階的に導入します。各段階で exit criteria と観測可能な evidence を定義し、それを満たしてから権限を拡大します。権限拡大前に[セキュリティモデル](03-security-model.md)を確認してください。

## Stage 0 — Observe

Agent を read-only で動かし、詳細 telemetry を有効にして、利用しようとする command / tool を収集します。

Exit criteria:
- 頻出 workflow を特定できている
- 必要 domain / tool の inventory がある
- sensitive path / resource の分類ができている
- baseline cost / failure rate が把握できている

## Stage 1 — Workspace Mutation

Disposable な task worktree 内だけ write を許可します。Network は制限したままにし、明示的に safe と分類されていない shell action は approval 対象とします。

Exit criteria:
- worktree 選択が安定している
- test / lint / type-check が deterministic に実行できる
- workspace 外への write が発生しない
- rollback が容易

## Stage 2 — PR Automation

Repository-scoped short-lived credential を使い、commit、feature branch push、PR creation を許可します。Default branch は server-side で保護します。

Exit criteria:
- protected branch への直接 mutation が技術的に不可能
- completion gate が Git / PR state を検証する
- CI が authoritative
- task -> commit -> PR を audit 上で相関できる

リファレンス実装は [`completion_gate.sh`](../../reference/scripts/completion_gate.sh) です。

## Stage 3 — Unattended Operation

Routine action を allow rule に移し、例外操作には external approval gateway を導入します。Turn / time / tool / cost budget と failure circuit breaker を設定します。最小構成の分類例は [`policy.example.json`](../../reference/policies/policy.example.json) を参照してください。

Approval 候補:
- filesystem/network scope の拡張
- sensitive data へのアクセス
- CI / security policy の変更
- force operation
- production-impacting cloud action

## Stage 4 — Production-adjacent Workflow

Isolation と IAM Control が十分に検証されてから、staging / production-adjacent system へのアクセスを許可します。直接 deployment より、既存 CI/CD を経由する方式を優先します。Production diagnostics は read-only を基本とします。

## 推奨実装順序

1. Normalized Action / Policy Schema を定義する
2. Central Policy Engine と test を実装する。現行例は [`internal/policy/policy.go`](../../internal/policy/policy.go) と [`internal/policy/policy_test.go`](../../internal/policy/policy_test.go)
3. Vendor Hook Adapter を追加する。Go 実装の Vendor Mapping は [`internal/vendor/adapter.go`](../../internal/vendor/adapter.go)、test は [`internal/vendor/adapter_test.go`](../../internal/vendor/adapter_test.go)
4. Static Permissions / Rules を設定する
5. 利用可能なら fail-closed OS Sandbox を有効化する
6. [`agent-pod.yaml`](../../reference/kubernetes/agent-pod.yaml) を起点に Container / Pod を harden する
7. [`network-policy.yaml`](../../reference/kubernetes/network-policy.yaml) を参考に Default-deny Network Control と egress path を追加する
8. Static Credential を Workload Identity / short-lived token に置き換える
9. Worktree Lifecycle Manager を実装する
10. Deterministic Completion Gate を実装する
11. PR / CI State を統合する
12. External Approval Workflow を追加する
13. Structured Telemetry を export する
14. Parent lifecycle が安定してから Subagent を導入する

## Policy Development Workflow

Policy は code として扱います。

- version control する
- allow / deny / ask の unit test を持つ
- incident ごとに regression test を追加する
- security-sensitive code として review する
- 可能なら Prompt とは独立して deploy する
- 全 decision に policy version を記録する

最初は restrictive に始め、Telemetry から安全な操作を特定して auto-allow を拡大します。Permissive に始めて危険コマンドを deny-list で列挙する方式は避けます。

## 運用メトリクス

有用な指標:

- autonomous completion rate
- task あたり human approval 回数
- task あたり deny 回数
- policy false-positive rate
- verification failure 後の retry 数
- median task wall-clock time
- completed task あたり token / compute cost
- PR の first-attempt CI success rate
- escaped defect / revert 数
- sandbox/network denial 数
- budget / circuit breaker による terminate 数

目標は「最大の自律性」ではありません。**境界づけ可能・観測可能・復旧可能な範囲で最大の自律性**を目指します。

---

[← セキュリティモデル](03-security-model.md) | [English](../04-adoption-guide.md) | [次: 製品マッピング →](05-product-mapping.md)
