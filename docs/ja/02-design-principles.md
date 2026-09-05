[← アーキテクチャ](01-architecture.md) | [English](../02-design-principles.md) | [次: セキュリティモデル →](03-security-model.md)

# 設計原則

## 1. モデルはいつか誤判断する前提で設計する

Instruction following が常に完全であることを前提にしてはいけません。Prompt injection、曖昧な意図、hallucination、通常の実装ミスはすべて想定内の failure mode です。安全性は、モデルとは独立した強制レイヤーによって実現します。

## 2. Policy と Capability を分離する

Hook が `rm -rf /` を禁止すると判断するのは Policy です。一方、Sandbox が `/` を書き込み不可にするのは Capability Control です。両方を使います。Policy は意味的な精度を提供し、Capability Control は Policy / Hook / Model の失敗を封じ込めます。

## 3. Soft Control をセキュリティ境界にしない

[AGENTS.md](../../AGENTS.md)、CLAUDE.md、Prompt、Skills、Playbook、Model-generated Plan はすべて行動制御として有効ですが、Secrets、Production、Protected Branch を守る唯一の機構にしてはいけません。

## 4. Fail-closed を優先する

セキュリティ上重要な enforcement は fail-closed を基本とします。Hook timeout / crash / malformed output 後も処理を継続する製品では、その Hook を hard boundary とみなしてはいけません。Sandbox、IAM、Server-side Policy で不変条件を守ります。

## 5. すべてのレイヤーで Least Privilege

必要最小限の権限だけを付与します。

- Organization 全体ではなく対象 repository 単位
- Default branch ではなく feature branch
- 不要なら Cloud API は read-only
- 長期 Personal Token ではなく task-scoped short-lived credential
- unrestricted Internet ではなく明示的 egress destination
- Home directory 全体ではなく workspace write

## 6. 安全な自律経路を最適化する

成熟した Harness は、すべての shell command について人間に質問するべきではありません。頻出する安全な操作は Permissions / Rules と Sandbox に組み込み、Approval は境界越えや意味的リスクの高い操作に限定します。

## 7. Server-side Policy を最終権威とする

Agent が `main` に push しないよう依頼するだけでは不十分です。GitHub Ruleset / Branch Protection / Credential Scope により、直接 push 自体を不可能にします。Cloud IAM、Deployment Environment、Production DB でも同様です。

## 8. Completion は Predicate として定義する

「完了」は会話上の自信ではなく、機械検証可能な Predicate とします。Tests、Git State、CI State、PR State、Deployment Evidence は model memory の外に置きます。実装例は [`completion_gate.sh`](../../reference/scripts/completion_gate.sh) を参照してください。

## 9. Vendor Adapter は薄く保つ

各製品固有 Hook を、次のような小さな内部契約に正規化します。

```json
{
  "event": "pre_tool_use",
  "tool": "exec",
  "input": {"command": "git push origin feature/x"},
  "context": {
    "session_id": "...",
    "cwd": "...",
    "repository": "...",
    "branch": "feature/x"
  }
}
```

中央 Policy Engine は vendor-neutral decision を返し、Claude Code / Codex / Devin CLI の Adapter が native schema に変換します。リファレンス実装は [`policy_engine.py`](../../reference/hooks/policy_engine.py) と [`pre_tool_use_adapter.py`](../../reference/hooks/pre_tool_use_adapter.py) です。

## 10. Policy Decision を観測可能にする

Policy version、Normalized Action、Decision、Reason、Approval Identity、Execution Result を記録します。Secret はログに残さず、task/session/turn ID で相関できる structured event とします。

## 11. 自律ループには上限を設ける

Turn 数、Wall-clock、Tool call、Token / Compute Cost、Repeated Failure に budget を設定します。Stop Hook や Self-repair Loop には Circuit Breaker が必要です。

## 12. Cloud Handoff は Trust Boundary Transition として扱う

Local から Cloud への Handoff は、Execution Environment、Credential、Network Control、Data Residency が変化する境界です。Local Policy がそのまま Cloud に適用されると仮定せず、再認可します。

---

[← アーキテクチャ](01-architecture.md) | [English](../02-design-principles.md) | [次: セキュリティモデル →](03-security-model.md)
