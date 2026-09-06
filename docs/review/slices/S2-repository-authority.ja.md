# S2 — リポジトリ同一性・保護状態・権威状態

## 状態

実装移植とレビューを完了。PR #1 の `common.py` に混在していたリポジトリ権威とSCM公開意味論を分離し、S2は権威状態の導出と適用順序だけを担当する形へ具体化した。

## 主張

1. 作業対象リポジトリの同一性を、S1が確立した信頼済み期待リポジトリと現在のGit/GitHub状態から評価する。
2. S1が確立した最低基準、リポジトリ固有の強化設定、GitHubの現在の保護状態から `READY` / `RESTRICTED` / `BLOCKED` を導出する。
3. 書込み可能なセッションキャッシュやpreflight結果を権威として利用しない。
4. 権威を必要とする変更操作では状態を再評価し、`BLOCKED` / `RESTRICTED` の権威判断を通常の承認判断より先に適用する。
5. `RESTRICTED` で禁止する操作の意味論はS2に埋め込まず、後続スライスが分類してS2の権威ゲートへ渡す。

## 権威と責任境界

- S1から受け取る権威入力:
  - `AGENT_HARNESS_EXPECTED_REPOSITORY`
  - `AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY`
- 外部権威:
  - GitHubリポジトリ情報。
  - 対象ブランチへ現在適用されているGitHub Rules。
- 観測:
  - ローカルGit repository root。
  - `origin` fetch URL。
  - リポジトリ固有 `.agent-harness/security.json`。
- 非権威:
  - SessionStart時に保存したposture cache。
  - `preflight.py` の過去の出力。
- 前提: S1が成立し、上記 trusted 入力が評価対象リポジトリから改変できないこと。
- 対象外:
  - SCMコマンドがどの操作分類に属するかという意味論: S3。
  - 制御機構変更の公開審査: S4。
  - 完了判定: S5。
  - GitHub/IAM内部実装そのものの完全性。
  - 任意子プロセスの完全仲介。

## 保証契約

### リポジトリ同一性

- ローカルGitの `origin` からGitHub repositoryを正規化する。
- S1から渡された期待リポジトリと実際のrepositoryが一致しない場合は `BLOCKED` とする。
- trusted expected repository がない場合、その欠落を `unknown` として保持し、既定の `restricted` 基準では `RESTRICTED` とする。
- リポジトリ固有 `expected_repository` は追加の整合性主張としてのみ扱い、trusted expected repository と競合する場合は `BLOCKED` とする。

### 最低基準の単調合成

- trusted baseline の mode をrepository overlayが弱くできない。
- trusted baseline が要求する保護条件をrepository overlayの `false` で解除できない。
- repository overlayは要求を追加できる。
- cache TTLは短くできるが長くできない。
- 不正なtrusted baselineまたはrepository overlayは fail-closed で `BLOCKED` とする。

### GitHub保護状態

- repository metadataから現在のdefault branchを取得する。
- 現在適用されるGitHub Rulesを直接取得する。
- 必要な根拠が取得不能な場合は `unknown` として保持し、成功扱いへ変換しない。
- `strict` / `restricted` / `warn` のmodeに従い三値の根拠から権威状態を導出する。

### 権威適用

- 権威を必要とする変更操作では `current_repository_posture(..., refresh_for_authority=True)` により毎回再評価する。
- 書込み可能なcacheは再評価の代替にしない。
- `BLOCKED` は変更操作を `deny` へ上書きし、通常の `ask` / approval で弱化できない。
- `RESTRICTED` は、後続スライスが `restricted_operation=True` と分類した操作を `deny` する。
- S2自身はGit pushやPR作成等のコマンド意味論を判定しない。
- 実際の `pre_tool_use_adapter.py` は、方針評価後にS2の権威ゲートを必ず通る。権威ゲートを単なる未使用ヘルパーとして残さない。

## 具体化

### `reference/posture/checker.py`

リポジトリ同一性、最低基準の単調合成、GitHub metadata / effective rulesの収集、三値根拠、権威状態導出を担当する。

### `reference/harness/authority.py`

権威の利用境界を担当する。

- 権威利用時はpostureを新しく取得する。
- cacheはread-only context用途に限る。
- `BLOCKED` / `RESTRICTED` を通常承認より先に適用する。
- SCM意味論を持たず、後続スライスから `mutation` / `restricted_operation` を受け取る。

### `reference/hooks/pre_tool_use_adapter.py`

S1の方針評価とS2の権威適用を実際のhook実行経路で接続する。

- 方針評価結果をS2権威ゲートへ渡す。
- S2の一般的な変更操作分類を使い、`BLOCKED` を方針の `allow` / `ask` より優先する。
- S3導入前は `restricted_operation=False` とし、RESTRICTED操作の意味論は持ち込まない。

### `reference/launcher/preflight.py`

セッション開始前の診断用入口。現在状態を表示・検査するが、その結果を後続の変更操作に対する権威として保存しない。変更時の権威は `authority.py` が再評価する。

### `reference/policies/repository-security.example.json`

S1がtrusted root内へ束縛する最低基準の参照実体。ファイルの信頼性はS1、内容の単調合成と意味解釈はS2の責務とする。

## 決定的な根拠

### `reference/posture/tests/test_checker.py`

- GitHub remote正規化。
- trusted expected repository一致 / 欠落 / 不一致。
- GitHub Rules取得不能時の `unknown`。
- `READY` / `RESTRICTED` / `BLOCKED` 導出。
- repository overlayがtrusted mode、requirements、TTLを弱化できないこと。
- repository overlayによる強化。
- expected repository競合。
- 不正policyのfail-closed。

### `reference/harness/tests/test_authority.py`

- cache上の `READY` より新しい再評価結果を優先する。
- 期限切れcacheをcontextとしても使用しない。
- `BLOCKED` が通常の `ask` より先に変更を拒否する。
- read-only操作には不要な権威制約を適用しない。
- `RESTRICTED` の操作分類を後続スライスから受け取れる。
- 権威取得不能時、restricted operationをfail-closedで拒否する。

### `reference/hooks/tests/test_policy_engine.py`

- 実際の `pre_tool_use_adapter.evaluate()` が方針評価の後にS2権威ゲートを呼ぶ。
- 方針が `ask` でも権威ゲートが `deny` へ上書きできる。
- S2時点では `restricted_operation=False` でS3境界を維持する。

## 具体化で判明した境界修正

### S2 → S1: trusted minimum baselineの生成元

S2が `AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY` を権威として扱うだけでは、その入力自身の信頼性をS2が仮定する責務循環になる。S1へフィードバックし、trusted root内のファイルへ束縛して渡す契約とした。

### S2 → S1: expected repositoryの生成元

同様に `AGENT_HARNESS_EXPECTED_REPOSITORY` の権威元が未定義だったため、S1がdeployment-supplied trusted inputを検証・再束縛する契約へ変更した。

### PR #1 `common.py` の責務分離

PR #1では権威状態、SCMコマンド意味論、control-plane diffが同じ `common.py` に存在した。これではS2/S3/S4が独立して失敗できるという保証スライス境界を表現できない。

S2では `authority.py` を独立させ、次の境界とした。

```text
S3等が操作を分類
        ↓
mutation / restricted_operation
        ↓
S2 authority gate
        ↓
現在の権威状態を再評価
        ↓
権威判断を通常承認より先に適用
```

これにより「どの操作がremote SCM mutationか」というS3の知識をS2から除去した。

### 権威ゲートの未接続

最初のS2レビューでは `authority.py` 単体の適合だけを確認し、実際の `pre_tool_use_adapter.py` が権威ゲートを呼んでいないことを見落としていた。この状態では「権威判断が通常承認より先に適用される」という主張は実行経路上では成立しない。

`pre_tool_use_adapter.evaluate()` をS2権威ゲートへ接続し、統合テストで方針の `ask` が権威の `deny` に上書きされることを固定した。これは「実装が存在する」ことと「保証経路に組み込まれている」ことを分けてレビューする必要性を示す指摘でもある。

## レビュー結果

- [x] 権威レビュー
  - trusted identity / minimum baselineの生成元をS1まで追跡した。
  - GitHub current stateを外部権威として明示した。
- [x] 信頼境界レビュー
  - S1とS2の境界で渡すtrusted inputsを明示した。
  - repository overlayとcacheを権威から除外した。
- [x] 根拠完全性レビュー
  - identity、metadata、rulesを個別のpass/fail/unknown根拠として保持する。
- [x] 失敗形態レビュー
  - policy不正、identity不一致、GitHub根拠取得不能、cache陳腐化を分類した。
- [x] 迂回レビュー
  - writable cacheから権威を復元しない。
  - approvalはBLOCKEDを上書きできない。
  - 権威ゲートが実際のhook経路から迂回されていないことを統合テストで確認する。
- [x] 責任分担レビュー
  - trusted入力の確立=S1、権威導出/適用=S2、操作意味論=S3へ分離した。
- [x] 保証欠落レビュー
  - SCM publication、control-plane publication、completion、deploymentを後続へ委譲した。
- [x] 実装適合レビュー
  - PR #1の混在実装を保証責務に沿って `authority.py` へ分離し、実際のadapter実行経路へ接続した。

## 残存リスクと対象外

- GitHub API / Rulesが示す状態の真正性はGitHub側の責任であり、その内部実装はS2では保証しない。
- `warn` modeは根拠が不完全でも `READY` を許容し得る。これはtrusted deploymentが明示的に選ぶ運用modeであり、repository overlayからは既定 `restricted` を弱化できない。S1の権威ある入口では旧 `AGENT_HARNESS_MINIMUM_POSTURE_MODE` を除去する。
- `preflight.py` やcheckerをtrusted S1経路外から単独実行した結果は権威ではない。
- 任意子プロセスによる操作を完全に観測・仲介する責務は持たない。

## 収束判定

S2の具体化からS1へ2件の権威境界フィードバックを返し、S1側で修正済み。PR #1の `common.py` からS2の責務も分離した。さらに再レビューで権威ゲートの実行経路未接続を発見し、adapter統合と決定的な回帰テストへ移した。

現時点でS2内部に新たなマージ阻害指摘は残っていない。S3が `restricted_operation` を正しく分類すること、およびS6がS1のtrusted入力供給を成立させることを外部依存として、S2は収束状態とする。
