# S4 — 制御機構変更の公開審査

## 状態

実装移植とレビューを完了。S3が成立させた自律SCM公開経路の後段に、制御機構変更だけを明示審査へ引き上げる独立した保証境界を追加した。

## 主張

1. 制御機構変更を編集手段ではなく、実際に公開されるGit差分から検出する。
2. 比較基準は確認済みGitHubリポジトリから直接取得した既定ブランチ先頭SHAとする。
3. 制御機構を含む公開には明示的な審査を要求する。

## 権威と責任境界

- 前提: S1、S2、S3が成立していること。
- 権威:
  - S2で確認済みrepository identityとdefault branch。
  - 確認済みGitHub repositoryから直接取得したdefault branch head SHA。
- 観測:
  - ローカルに存在するGit commit object。
  - GitHub default branch headと現在HEADの三点差分。
- 非権威:
  - `origin/main` 等のローカルremote-tracking ref。
  - どの編集toolでファイルが変更されたかという履歴。
- 対象外:
  - GitHub側の最終認可規則そのもの。
  - 公開されないローカル編集の禁止。
  - 制御機構以外の変更に必要なアプリケーション固有レビュー。

## 保証契約

### 公開差分

- S3が `allow` としたSCM公開だけをS4の評価対象とする。
- `git push` では現在HEADが公開対象であることをS3が保証する。
- `gh pr create` ではローカルHEADがGitHub上の公開branch headと一致することをS3が保証する。
- S4は編集操作を監視せず、公開時点のGit差分だけを評価する。

### 比較基準

- default branch head SHAは `gh api repos/{repository}/git/ref/heads/{branch}` で確認済みrepositoryから直接取得する。
- ローカル `origin/<default>` を権威として使用しない。
- GitHubから得たSHAのcommit objectがローカルに存在しない場合はfail-closedで拒否する。
- Git差分を確立できない場合もfail-closedで拒否する。

### 制御機構範囲

制御機構として、Agent Harnessの実行・方針・権威・ベンダー接続・配備・CIに関わる既知のpathを明示的に分類する。

主な対象:

- `.agent-harness/`
- `.claude/`, `.codex/`, `.devin/`
- `.github/workflows/`
- `reference/harness/`, `reference/hooks/`, `reference/posture/`
- `reference/policies/`, `reference/launcher/`, `reference/scripts/`
- `reference/claude/`, `reference/codex/`, `reference/kubernetes/`
- `AGENTS.md`
- `.github/pull_request_template.md`

制御機構pathが公開差分に1件でも含まれる場合、S3の `allow` を `ask` へ引き上げる。

## 具体化

### `reference/harness/control_plane_publication.py`

- GitHub default branch head SHAの直接取得。
- authoritative commit objectの存在確認。
- `<github-default-head>...HEAD` の公開差分取得。
- 制御機構path分類。
- 制御機構変更の `ask` への引上げ。
- 権威・差分取得不能時のfail-closed。

### `reference/hooks/pre_tool_use_adapter.py`

実際のtrusted hook経路をS4まで接続する。

```text
S1 policy
  ↓
S2 repository authority
  ↓
S3 SCM publication semantics
  ↓
S4 control-plane publication review
```

S4を未使用helperとして残さず、S3で自律許可可能となった公開を実行直前に必ず通す。

## 決定的な根拠

### `reference/harness/tests/test_control_plane_publication.py`

- 制御機構path分類。
- GitHub default branch head SHAを比較基準に使用すること。
- `origin/main` を比較基準にしないこと。
- 通常アプリケーション差分は自律許可を維持すること。
- GitHub head取得不能時のdeny。
- authoritative commit objectがローカルに存在しない場合のdeny。
- S3が `allow` しない操作へS4が介入しないこと。
- S3 `allow` を制御機構差分で `ask` へ引き上げること。

### `reference/hooks/tests/test_policy_engine.py`

- 実際の `pre_tool_use_adapter.evaluate()` がS4の合成公開経路を呼ぶこと。
- policy上 `allow` のcanonical publicationをS4が `ask` へ変更できること。

## レビュー結果

- [x] 権威レビュー
  - default branch状態の権威をGitHub直接取得SHAへ限定した。
- [x] 信頼境界レビュー
  - ローカルremote-tracking refを権威から除外した。
- [x] 根拠完全性レビュー
  - GitHub SHA、commit object、現在HEADとの差分、path分類を一連の根拠として要求する。
- [x] 失敗形態レビュー
  - GitHub取得不能、SHA不正、commit object欠落、diff失敗をfail-closedにした。
- [x] 迂回レビュー
  - 編集手段ではなく公開差分で判定するため、別toolでの編集による迂回を作らない。
  - `origin/main` の書換えによる比較基準迂回を排除した。
- [x] 責任分担レビュー
  - SCM公開形態=S3、制御機構差分審査=S4、GitHub最終認可=外部責任へ分離した。
- [x] 保証欠落レビュー
  - 未公開ローカル編集やアプリ固有設計レビューは対象外として明示した。
- [x] 実装適合レビュー
  - PR #1 `common.py` のcontrol-plane責務を独立モジュールへ分離し、実際のhook経路へ接続した。

## 残存リスクと対象外

- 制御機構path集合は現在のAgent Harness実装構造に対する具体化であり、新しい制御機構pathを追加する場合はこの分類自身も更新対象となる。
- GitHub APIが返すrepository状態の真正性はGitHub側の責任とする。
- GitHub default branch head commitがローカルにない場合、自動fetchで権威を補完せず安全側に拒否する。これは可用性より保証を優先する意図的な判断である。
- GitHub側のbranch protection / Rulesetsによる最終認可はS4自身の保証ではない。

## 収束判定

S4は、公開対象の制御機構変更を編集経路から独立して検出し、比較基準をローカルremote-tracking refからGitHub直接取得SHAへ移した。実行経路への結線とfail-closed条件も決定的テストへ固定した。

現時点でS4内部に新たなマージ阻害指摘は残っていない。GitHub server-side authorizationとS6の配備責任を外部依存として、S4は収束状態とする。
