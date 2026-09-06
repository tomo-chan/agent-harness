[← 製品マッピング](05-product-mapping.md) | [English](../06-vendor-harnesses.md) | [README →](../../README.ja.md)

# ベンダー別ハーネス実装

このリポジトリには Claude Code、OpenAI Codex、Devin CLI 向けの参照用フック接続を実装している。3製品とも、共通の拒否優先方針エンジン、リポジトリ保護状態検査器、SCM意味論検証器、公開時の制御機構差分審査、セッション状態を考慮した決定的な完了保証を利用する。

本番環境では、保証・方針を実行するコードと信頼済み最低基準を、エージェントが変更可能なワークスペースの外にある信頼済みルートから解決する。

## 信頼済みハーネス境界

本番ハーネスの実装は、評価対象であるリポジトリやワークツリーから実行してはならない。信頼済み起動処理は次のようなルートを設定する。

```bash
export AGENT_HARNESS_TRUSTED_ROOT=/opt/agent-harness
```

承認済みのハーネス一式は信頼済み配備処理によってこのルートへ配置する。Kubernetesの参照構成では `/opt/agent-harness` をコンテナの読み取り専用ルートファイルシステム上に置き、`/workspace` を可変な作業用ワークスペースとする。

プロジェクト内フックファイルは次を呼び出す。

```text
$AGENT_HARNESS_TRUSTED_ROOT/reference/launcher/trusted_hook.py
```

ラッパーは、自身が設定済みの信頼済みルートから実行されていることを確認し、同じルートからベンダーアダプターと意味論的方針を解決する。リポジトリ保護状態の信頼済み最低基準は `AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY` で検査器へ渡すが、リポジトリ内の `.agent-harness/security.json` 自体は置き換えない。後者は未信頼の強化入力として扱う。詳細はDL-015とDL-018を参照する。

リポジトリ内の `.claude` / `.codex` / `.devin` ファイルは参照・開発用の接続であり、それ自体を独立した本番権威境界とはみなさない。ベンダーが管理型登録を提供する場合、フック登録自体も信頼済み起動処理または管理設定から配置する。

## 信頼済み最低基準とリポジトリ固有方針

信頼済み権威を先に確定する。

```bash
export AGENT_HARNESS_EXPECTED_REPOSITORY=owner/repository
export AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY=/opt/agent-harness/reference/policies/repository-security.example.json
# 対話用途などで信頼済み起動処理が必要に応じて指定する
export AGENT_HARNESS_MINIMUM_POSTURE_MODE=restricted
```

信頼済み最低基準ファイルは必須制御とキャッシュ時間を定める。`AGENT_HARNESS_MINIMUM_POSTURE_MODE` が明示されている場合は、信頼済み起動処理が最低基準モードを選択する。これにより、対話用途で意図的に `warn` を選ぶ既存運用を維持できる。

その後、リポジトリ内の `.agent-harness/security.json` を次の規則で単調に合成する。

```text
信頼済みモード     = 起動処理の明示指定があればその値、なければ最低基準ファイルの値
有効モード         = より厳しい(信頼済みモード, リポジトリモード)
有効必須要件       = 信頼済み要件 OR リポジトリ要件
有効キャッシュ時間 = min(信頼済み時間, リポジトリ時間)
```

したがって、リポジトリ側は必須要件を追加したり、より厳しいモードを選んだりできるが、信頼済み要件を解除したりキャッシュ時間を延長したりできない。リポジトリ側の `expected_repository` は追加の整合性主張にすぎず、信頼済み作業対象識別は `AGENT_HARNESS_EXPECTED_REPOSITORY` が担う。不正な信頼済み方針またはリポジトリ方針は `BLOCKED` とする。

SessionStartでは、`origin` と信頼済み期待リポジトリを比較し、GitHubのリポジトリ情報と既定ブランチに適用される有効な規則を取得する。根拠を `pass` / `fail` / `unknown` に正規化し、`READY` / `RESTRICTED` / `BLOCKED` を導出する。キャッシュが古い場合やリポジトリルートが変わった場合は再評価する。

## 正規形の自律公開

フック境界で観測できるエージェント直接操作として、自律的なGit公開は次の2形式だけとする。

```bash
git push
git push --set-upstream origin HEAD
```

PreToolUseで、保護状態が `READY` であること、現在ブランチが名前付きかつ既定ブランチではないこと、`origin` が検査済みリポジトリと一致すること、上流ブランチが期待どおりであることを確認する。

強制pushは `--force-with-lease=<参照>` を含む形式も拒否する。任意の遠隔リポジトリ、参照指定、タグ、削除、設定上書きは自律公開対象外とする。

自律的な `gh pr create` はリポジトリ、作業元ブランチ、基準ブランチを上書きできず、現在ブランチが `origin/<現在ブランチ>` として公開済みである必要がある。

複合シェルは自律許可対象外とする。さらに `RESTRICTED` では、`git status && git push` のように遠隔SCM変更がコマンド途中に現れる場合でも保守的に検出し、承認による権威状態の迂回を許さない。

## 制御機構の公開時審査

編集時のパス分類だけを承認境界にしない。正規形pushまたは自律的なプルリクエスト作成の直前に、次の差分を評価する。

```text
git diff --name-only origin/<既定ブランチ>...HEAD
```

`.agent-harness/`、ベンダー用フック設定、CI、ハーネス、保護状態検査、方針、起動処理、`AGENTS.md` などの保護対象が変更されている場合、規則 `control-plane-publication` の承認要求を返す。

この審査は、変更が書込み・編集ツール、`apply_patch`、`git restore`、リポジトリ内スクリプトなど、どの経路で作成されたかに依存しない。差分を確立できない場合は安全側へ倒して拒否する。本番権威そのものは引き続き読み取り専用の信頼済みハーネス領域が担う。詳細はDL-019を参照する。

## セッション状態を考慮した完了保証

SessionStartで次を基準状態として保存する。

- リポジトリルート
- `HEAD`
- 未追跡ファイルを含む正確な作業ツリー状態

Stop時に現在状態と比較する。

- 状態が同一なら読み取り専用セッションとして扱い、機能ブランチや上流ブランチを要求する成果物向け完了検査を省略する。
- 状態が変化していれば通常の決定的な成果物完了検査を実行する。
- 基準状態が欠落、不正、または比較不能なら読み取り専用と推定せず、通常の完了検査を実行する。

これにより、既定ブランチ上のレビューや調査だけのセッションを誤って失敗させず、変更を伴う成果物作業は引き続き安全側へ倒せる。詳細はDL-020を参照する。

## 意味論的方針の仲介範囲

フックが統治するのは、フック境界で観測可能なエージェント直接操作である。`pytest` や `npm test` の内部で起動するすべての子プロセスや副作用まで完全仲介したとは扱わない。

子プロセスが意味論的方針の可視範囲を迂回しても成立しなければならない重要な外部不変条件は、最小権限のIAM / SCM認証情報、GitHub側ルールセットやブランチ保護、必要に応じたネットワーク制御へ具体化する。詳細はDL-016を参照する。

## ベンダーごとの補足

### Claude Code

SessionStart / PreToolUse / Stopとサンドボックスを利用する。中央方針の承認要求はPreToolUseのネイティブな承認要求へ対応付ける。認証情報ファイルの拒否やベンダー提供の秘匿機能は多層防御であり、最終的なSCM権威にはしない。

### Codex

フックとCodexのサンドボックス / ワークスペース制御を利用する。中央方針の承認要求は、信頼済み外部承認がない限り拒否へ変換する。リポジトリ保護状態とサーバー側制御は、この承認機構の制約とは独立して維持する。

### Devin CLI

ライフサイクルフック、静的権限、Devinのサンドボックスを利用する。標準構成ではネイティブの `git` / `gh` を使い、認証情報を隠すことだけを目的にSCM仲介サービスを追加しない。

## 配備を単純に保つ

標準構成は **1 Pod / 1エージェントコンテナ** とする。具体的な脅威モデルがない限り、SCM仲介サービス、サイドカー、`git`差し替え、`gh`差し替えを追加しない。

サンドボックスと方針で露出を減らし、短寿命・リポジトリ限定の認証情報と最小権限のIAM / SCMで侵害時の影響を制限する。GitHubのルールセットとブランチ保護はサーバー側の権威的な制御として維持する。

## 検証

```bash
python -m pip install pytest
python -m pytest reference/hooks/tests reference/harness/tests reference/posture/tests -q
AGENT_HARNESS_EXPECTED_REPOSITORY=owner/repository \
  python reference/launcher/preflight.py --json
```

回帰検査では、信頼済みルートの隔離、信頼済み最低基準とリポジトリ固有方針の単調合成、信頼済み起動処理によるモード指定、複合シェル内の遠隔SCM変更検出、正規形公開、各種強制push、制御機構の公開時審査、プルリクエスト作成時のGit状態拘束、権威状態と承認の優先順位、読み取り専用セッションの完了保証、本番Pythonコードの `docstring` を確認する。

---

[← 製品マッピング](05-product-mapping.md) | [English](../06-vendor-harnesses.md) | [README →](../../README.ja.md)
