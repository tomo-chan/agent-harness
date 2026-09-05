# Agent Harness 日本語版

Claude Code / OpenAI Codex / Devin CLI などの自律型ソフトウェア開発エージェントを、安全かつ再利用可能な形で運用するための、ベンダー非依存のリファレンスアーキテクチャと実装例です。

このリポジトリの中心的な考え方は、**LLM 自体をセキュリティ境界として扱わない**ことです。自律実行は、独立したポリシー、OS サンドボックス、Pod/コンテナ分離、外部 IAM、ネットワーク制御、機械検証可能な完了条件によって制約されるべきです。

## 基本アーキテクチャ

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

各レイヤーの責務は明確に分離します。

| レイヤー | 主な責務 |
|---|---|
| Instructions / Skills | 望ましい振る舞い、作業手順、設計方針 |
| Hooks / Policy Engine | 文脈依存・ライフサイクル依存のポリシー判断 |
| Permissions / Rules | コマンド、ツール、パスの静的分類 |
| Sandbox | ファイルシステム・ネットワークの能力境界 |
| Container / Pod | プロセス、ホスト、リソースの隔離 |
| IAM / SCM Policy | 外部システムに対する権限と被害範囲の制御 |
| Completion Gate | 機械検証可能な「完了」の定義 |
| Telemetry | 監査、障害解析、ポリシーチューニング |

## 標準的な自律実行フロー

```text
Task
 -> リポジトリ調査（read-only）
 -> 変更が必要なら feature worktree / branch を作成
 -> 計画
 -> 編集
 -> test / lint / type-check
 -> policy / completion gate
 -> commit
 -> feature branch を push
 -> PR 作成
 -> CI / review
 -> 保護されたサーバー側フローで merge
```

通常業務は可能な限り人間の確認なしで完結させます。人間の承認は、静的ポリシーやサンドボックスだけでは安全に境界づけられない操作に限定します。

## リポジトリ構成

- `docs/01-architecture.md` — 英語版アーキテクチャ
- `docs/02-design-principles.md` — 英語版設計原則
- `docs/03-security-model.md` — 英語版セキュリティモデル
- `docs/04-adoption-guide.md` — 英語版導入ガイド
- `docs/05-product-mapping.md` — 英語版製品マッピング
- `docs/ja/` — 上記ドキュメントの日本語版
- `reference/hooks/policy_engine.py` — ベンダー非依存 Policy Engine
- `reference/hooks/pre_tool_use_adapter.py` — Hook Adapter 例
- `reference/policies/policy.example.json` — ポリシー例
- `reference/scripts/completion_gate.sh` — 完了条件検証
- `reference/kubernetes/agent-pod.yaml` — Hardening 済み Pod 例
- `reference/kubernetes/network-policy.yaml` — default-deny NetworkPolicy 例

## 非目標

このプロジェクトは、Prompt、AGENTS.md、CLAUDE.md、Skills、モデルの推論そのものをセキュリティ機構にすることを目的としていません。これらは有効な行動制御ですが、秘密情報、production 環境、protected branch を守るための最終的な強制境界ではありません。

## 基本原則

> 安全な操作は自律実行しやすくし、危険な操作は技術的に不可能にするか、明示的な承認を必要とする。
