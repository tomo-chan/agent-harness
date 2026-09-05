[← 導入ガイド](04-adoption-guide.md) | [English](../05-product-mapping.md) | [README →](../../README.ja.md)

# 製品マッピング

このプロジェクトでは、ベンダー非依存の内部モデルを採用します。各製品の機能をそのままアーキテクチャに持ち込むのではなく、共通の責務レイヤーへマッピングします。共通モデルは[リファレンスアーキテクチャ](01-architecture.md)と[設計原則](02-design-principles.md)を参照してください。

| 関心事 | Claude Code | OpenAI Codex | Devin CLI |
|---|---|---|---|
| 行動ガイダンス | CLAUDE.md / rules / skills | AGENTS.md / skills | AGENTS.md / rules / skills |
| ライフサイクルポリシー | Hooks | Hooks | Hooks |
| 実行前セマンティックゲート | PreToolUse | PreToolUse | PreToolUse |
| 実行後検証 | PostToolUse | PostToolUse | PostToolUse |
| 承認介入 | PermissionRequest | PermissionRequest / approval architecture | PermissionRequest |
| 完了ゲート | Stop | Stop | Stop |
| 静的 command/tool policy | Permissions | Rules / approval policy | Permissions |
| OS Sandbox | Seatbelt / bubblewrap 系 sandbox | Codex sandbox | OS sandbox |
| Network Policy | sandbox domain controls | sandbox/network controls | sandbox domain controls。実運用前に current stability を再確認 |
| Central / Enterprise Policy | managed settings | managed configuration / requirements | Team Settings |
| Observability | hooks / telemetry integrations | OTel / agent-native events | hooks / enterprise analytics |
| Local-to-cloud transition | 別 workflow として扱う | Codex cloud architecture | `/handoff` |

## Claude Code

公式ドキュメント: [Claude Code Hooks](https://code.claude.com/docs/en/hooks) / [Sandboxing](https://code.claude.com/docs/en/sandboxing)

Claude Code は lifecycle hook の種類が多く、semantic orchestration を細かく組み込みやすい製品です。一方で、Hook Command 自体を通常の Agent Shell Command と同じ Sandbox に守られていると仮定してはいけません。Hook Code は trusted code として小さく、defensive に保ちます。

## Codex

公式ドキュメント: [OpenAI Codex documentation](https://developers.openai.com/codex/) / [Codex GitHub repository](https://github.com/openai/codex)

Codex は Sandbox、Approval Policy、Rules、Managed Configuration、Telemetry の責務分離が明確で、外部 Harness を設計する際の参考になります。App Server を使う構成では Tool Approval を structured control-plane event として扱いやすくなります。ただし Hook の failure semantics は version ごとに確認し、Hard Invariant は独立した boundary で保護します。

## Devin CLI

公式ドキュメント: [Devin CLI Hooks](https://docs.devin.ai/cli/extensibility/hooks/overview) / [Permissions](https://docs.devin.ai/cli/reference/permissions)

Devin CLI は Permissions と Sandbox Scope の結びつきが強く、Autonomous Sandbox Mode により unattended workload を構成しやすい設計です。Direct edit/write tool の境界や network filtering の成熟度は周辺アーキテクチャで補完します。また Local から Cloud への Handoff は別 trust domain への遷移として扱います。

## Portability Strategy

内部では以下の flow に統一します。

```text
Vendor event
   -> Adapter
   -> Normalized Action
   -> Policy Engine
   -> allow / ask / deny (+ reason/context)
   -> Adapter
   -> Vendor response
```

リファレンス実装は [`policy_engine.py`](../../reference/hooks/policy_engine.py) と [`pre_tool_use_adapter.py`](../../reference/hooks/pre_tool_use_adapter.py) です。

すべての Vendor Feature を完全に抽象化する必要はありません。組織側が所有すべき Security / Orchestration Semantics だけを正規化し、各製品固有の有用な機能は Adapter の背後に残します。

## 実装時の注意

各製品の Hook Schema、Decision Field、Failure Behavior、Sandbox Capability は変化し得ます。Adapter は version-aware にし、CI で schema conformance test を実行できる構成を推奨します。特に Production 導入前には、各製品の最新公式仕様と実動作を再検証してください。

---

[← 導入ガイド](04-adoption-guide.md) | [English](../05-product-mapping.md) | [README →](../../README.ja.md)
