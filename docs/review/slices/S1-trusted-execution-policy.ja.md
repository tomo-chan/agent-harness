# S1 — 信頼済み実行境界と方針基盤

## 状態

実装移植と再レビューを完了。S2具体化からのフィードバックを受け、S2が権威として利用する入力の生成元までS1の信頼境界へ閉じた。

## 主張

1. 保証機構として利用するハーネス実装と信頼済み方針入力は、評価対象リポジトリから変更できない信頼済み領域に置かれる。
2. 方針評価は `deny > ask > allow` を明示的な優先順位とし、方針読込み・検証・評価不能時は許可へ倒れない。
3. 後続スライスが権威として扱う入力は、信頼済み起動処理が生成・正規化し、評価対象側の入力へ暗黙にフォールバックしない。

## 権威と責任境界

- 権威: 読み取り専用として配備される信頼済みハーネス領域、信頼済み起動処理、配備基盤。
- S1が確立して後続へ渡す権威入力:
  - ツール方針: `AGENT_HARNESS_POLICY`
  - リポジトリ最低基準: `AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY`
  - 期待リポジトリ: `AGENT_HARNESS_EXPECTED_REPOSITORY`
- 観測: 実行時環境、正規化されたツール入力。
- 外部責任:
  - 配備基盤が信頼済みハーネス領域を評価対象リポジトリから書込み不能にすること。
  - 配備基盤が `AGENT_HARNESS_TRUSTED_EXPECTED_REPOSITORY` などの trusted 入力を評価対象リポジトリから変更できない形で与えること。
  - 実際のフック接続が `trusted_policy_hook.py` を権威ある入口として使用すること。
- 後続スライスへ委譲:
  - リポジトリ同一性・GitHub保護状態・最低基準の単調合成: S2
  - SCM公開意味論: S3
  - 制御機構変更の公開審査: S4
  - 完了判定: S5
  - Claude Code / Codex / Devin 固有の接続と配備具体化: S6

## 保証契約

- `AGENT_HARNESS_TRUSTED_ROOT` が未指定、または実際のハーネス配置と一致しない場合は拒否する。
- 信頼済みツール方針と信頼済みリポジトリ最低基準が信頼済みルート外へ解決される場合は拒否する。
- S1では汎用方針アダプタを固定し、ベンダー選択を持ち込まない。
- `AGENT_HARNESS_TRUSTED_EXPECTED_REPOSITORY` は `owner/repository` 形式へ検証してから `AGENT_HARNESS_EXPECTED_REPOSITORY` へ渡す。trusted 入力がない場合は既存の `AGENT_HARNESS_EXPECTED_REPOSITORY` を除去する。
- `AGENT_POLICY`、`AGENT_HARNESS_REPOSITORY_SECURITY_POLICY`、`AGENT_HARNESS_MINIMUM_POSTURE_MODE` など、評価対象側から権威を差し替えたり弱化したりできる入力は信頼済み入口で除去する。
- 方針評価の優先順位は JSON の記述順ではなく `deny > ask > allow` で固定する。
- 方針読込み・検証・入力解釈・評価に失敗した場合、境界では `deny` を返す。

## 具体化

### 実装

- `reference/launcher/trusted_policy_hook.py`
  - 信頼済みルートと実配置の一致を検証する。
  - ツール方針とリポジトリ最低基準を信頼済みルート内へ束縛する。
  - trusted expected repository を検証し、S2互換入力へ再束縛する。
  - 汎用方針アダプタを固定する。
  - 弱化・差替えにつながる旧環境変数を除去する。
- `reference/hooks/policy_engine.py`
  - 方針スキーマ検証。
  - `deny > ask > allow` の決定的評価。
  - CLI境界での fail-closed。
- `reference/hooks/pre_tool_use_adapter.py`
  - `AGENT_HARNESS_POLICY` のみを方針権威として使用。
  - 方針未指定・読込み失敗・評価失敗を `deny` へ変換。

### 決定的な根拠

- `reference/hooks/tests/test_policy_engine.py`
  - deny優先順位、不正方針拒否、信頼済み方針未指定時の deny。
- `reference/launcher/tests/test_trusted_policy_hook.py`
  - trusted root 必須、実配置不一致拒否。
  - trusted root 外のツール方針・リポジトリ最低基準の拒否。
  - trusted expected repository の形式検証。
  - アダプタ固定。
  - 旧方針・弱化用環境変数の除去。
  - trusted expected repository だけがS2の期待リポジトリ入力へ再束縛されること。

## 具体化で判明した境界修正

### `reference/launcher/preflight.py`

初期スライス案ではS1へ割り当てていたが、リポジトリ保護状態を評価するためS2へ移した。

### `reference/launcher/trusted_hook.py`

PR #1ではベンダー選択と信頼境界が混在していた。S1では `trusted_policy_hook.py` へ信頼境界だけを抽出し、ベンダー接続はS6へ移した。

### 方針環境変数の不一致

PR #1では trusted launcher が `AGENT_HARNESS_POLICY` を設定する一方、汎用アダプタが `AGENT_POLICY` を読んでいた。S1で `AGENT_HARNESS_POLICY` に統一した。

### アダプタ差替え可能性

初回移植では trusted root 内の別アダプタを環境変数から選択できた。S1の保証理由と無関係な可変点であるため固定した。

### S2から発見された最低基準の権威欠落

S2は `AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY` を権威として扱うため、そのファイルの信頼性をS2自身が仮定すると責務循環になる。S1が trusted root 内へ束縛して渡す契約へ変更した。

### S2から発見された期待リポジトリの権威欠落

S2は `AGENT_HARNESS_EXPECTED_REPOSITORY` を信頼済み同一性として利用するが、従来はその生成元が明示されていなかった。S1で deployment-supplied な `AGENT_HARNESS_TRUSTED_EXPECTED_REPOSITORY` を検証し、互換入力へ再束縛する契約へ変更した。trusted 入力がない場合は既存値を破棄する。

## レビュー結果

- [x] 権威レビュー — 後続が権威として使う入力の生成元をS1へ閉じた。
- [x] 信頼境界レビュー — root一致、trusted file包含、trusted repository入力、固定アダプタを確認した。
- [x] 根拠完全性レビュー — ローカルで検証できる契約は決定的テストへ落とした。物理的読み取り専用性はS6依存。
- [x] 失敗形態レビュー — trusted root/方針/最低基準/期待リポジトリの不正を拒否する。
- [x] 迂回レビュー — repository-local fallback、アダプタ差替え、最低基準弱化、未認証 expected repository を除去した。
- [x] 責任分担レビュー — S1が権威入力を確立し、S2以降が意味論を評価する。
- [x] 保証欠落レビュー — リポジトリ保護、SCM公開、完了、配備は後続へ委譲した。
- [x] 実装適合レビュー — S2からの逆向きフィードバックを反映し、責務循環を解消した。

## 残存リスクと対象外

- trusted root の読み取り専用性と trusted 環境変数の供給元は配備基盤が強制し、S6で具体化する。
- `trusted_policy_hook.py` が権威ある入口として強制されることもS6の配備契約に依存する。
- 個々のSCMルールの意味論的妥当性はS3以降の保証対象である。

## 収束判定

S2具体化からの2件の権威欠落をS1へフィードバックして修正した。現時点でS1内部に新たなマージ阻害指摘は残っていない。

S1の実運用保証は、読み取り専用配備、trusted 環境入力、権威あるフック接続をS6が成立させることを前提とする。
