[README](../../README.ja.md) | [ツール仕様書](agent-harness-spec.ja.md) | [RAEM](../../raem/refinement-assurance-and-evolution-model.ja.md)

# Agent Harness 用語集（Agent Harness Glossary）

## 1. 文書の位置づけ（Document Scope）

本書は、Agent Harness の仕様、具体実装、保証スライスで共有する用語を定義する。製品固有の名称と同じ語がある場合も、本書の定義を共通契約上の基準とする。

用語の定義は概念の意味を固定するものであり、特定の Go / Python の型、パッケージ、CLI field や、特定ベンダーの schema を指定しない。振る舞いの規範的な要求は[ツール仕様書](agent-harness-spec.ja.md)、保証主張と Evidence は各保証スライスで定義する。

## 2. 用語（Terms）

| 日本語 | 英語・表記 | 本書での意味 |
|---|---|---|
| Agent Harness | Agent Harness / Harness | 自律型ソフトウェア開発エージェントの操作を、policy、信頼境界、能力制限、外部認可、完了条件の中で制御する仕組み全体。単一の実行ファイルだけを指さない |
| エージェント | Agent | 調査、推論、計画、操作提案、成果物作成、未知の問題の探索を行う主体。セキュリティ境界や保証の最終権威ではない |
| サブエージェント | Subagent | Agent から限定した作業を委譲される主体。独立したセキュリティ境界とはみなさない |
| 制御プレーン | Control Plane | task state、policy decision、approval、budget、completion state をモデルコンテキスト外で管理する領域 |
| 実行プレーン | Execution Plane | 許可された操作を、sandbox や workload isolation などで能力を制限した環境内で実行する領域 |
| 信頼境界 | Trust Boundary | trusted と untrusted の主体・入力・状態・処理を分ける境界 |
| 信頼された実行環境 | Trusted Runtime | 信頼された実行物、設定、起動経路を確立し、それらを repository や Agent による差し替えから保護する実行基盤 |
| 信頼された設定 | Trusted Configuration | 運用者が管理し、repository-controlled input やモデル出力から独立して完全性を保つ設定 |
| 信頼基点 | Trusted Root | 実行物や設定を trusted と判断する起点。選択主体、所有権、完全性、更新方法を別途定義する |
| 信頼されたコンピューティング基盤 | Trusted Computing Base / TCB | 対象の保証が正しく成立するために信頼する必要があるコンポーネントと運用境界の集合 |
| ベンダーイベント | Vendor Event | Claude Code、Codex、Devin などの製品が発行する製品固有の lifecycle / tool event |
| ベンダーアダプター | Vendor Adapter | vendor event と vendor-neutral な共通契約、および共通判断と製品固有応答を相互変換する境界コンポーネント |
| 正規化された操作 | Normalized Action | 操作、対象、文脈を vendor-neutral な形で表した policy 評価入力。自己申告値と検証済み事実を区別する |
| ポリシー | Policy | Normalized Action と検証済み文脈から許可、承認要求、拒否を決定する規則と評価条件 |
| 判断 | Decision | policy 評価結果である `allow`、`ask`、`deny` のいずれか。操作の実行結果とは区別する |
| 許可 | `allow` | 評価した対象と範囲内で操作を進められるという判断。sandbox や外部認可を解除しない |
| 承認要求 | `ask` | 有効な外部承認を得て再評価するまで操作を実行しないという判断 |
| 拒否 | `deny` | 対象操作を実行しないという判断。通常の承認によって反転しない |
| 承認 | Approval | 特定の主体、操作、対象、scope、有効期限に対する外部からの限定的な権限委譲 |
| リポジトリ識別情報 | Repository Identity | 対象 repository を一意に照合するための、検証済みの repository、remote、worktree などの情報 |
| リポジトリ状態 | Repository Posture | branch、保護状態、worktree、dirty state、remote など、操作権限の判断に必要な検証済み状態 |
| 変更権限 | Mutation Authority | 特定 repository / worktree / branch に対して変更を行える、検証済みかつ限定された権限 |
| 公開 | Publication | commit、branch、PR、tag、release、設定などをローカル境界の外へ反映する操作 |
| 制御プレーン変更 | Control-plane Change | policy、hook、CI workflow、権限、配備設定など、Harness や外部強制境界の振る舞いを変更し得る変更 |
| 根拠 | Evidence | 判断や適合主張を支える、出所、対象、取得時点、評価条件を特定できる情報 |
| 完了条件 | Completion Predicate | task の完了に必要な、機械検証可能な条件 |
| 完了ゲート | Completion Gate | Completion Predicate の評価結果を使い、処理の完了や次段階への移行を許可・拒否する強制機構 |
| 完了保証 | Completion Assurance | Evidence と定義済みの評価規則から、Completion Predicate が成立するという主張を確認すること |
| 具体実装 | Concrete Implementation / Realization | ツール仕様を Go、Python、設定、配備、外部制御などで実現したもの。仕様そのものではない |
| 適合保証 | Conformance Assurance | 具体実装が仕様上の要求を満たすという主張を、Evidence と定義済みの推論で成立させること |
| 保証スライス | Assurance Slice | S1〜S6 のように、複数の機能・実装・配備境界を横断して特定の保証主張を確認するレビュー軸 |
| モデルレビュー | Model Review | 現在の要求、具体化、Evidence、保証規則にまだ表現されていない問題を探索する非決定的プロセス |
| 閉じて失敗する | Fail Closed | エラーや検証不能のときに、保護対象の操作を許可・完了として扱わない失敗特性 |
| 開いて失敗する | Fail Open | エラーや検証不能でも、呼出し元が保護対象の操作を継続し得る失敗特性 |
