# S3 — 自律SCM公開制御

## 状態

実装移植とレビューを完了。PR #1 の `common.py` に混在していたSCM公開意味論を `reference/harness/scm_publication.py` へ分離し、S2の権威状態とS4の制御機構公開審査の間に独立した保証境界を形成した。

## 主張

1. 観測可能な直接的SCM公開を狭い正規形に限定する。
2. `git push` は確認済みリポジトリ、現在ブランチ、実効push先、上流状態と整合する場合だけ自律許可する。
3. 強制pushを自律許可しない。
4. `gh pr create` を確認済みリポジトリと、GitHub上で現在のローカルHEADまで公開済みの現在ブランチへ結び付ける。
5. 複合シェルや対象上書き等の正規形外操作を自律許可対象から外す。

## 権威と責任境界

- 前提: S1、S2が成立していること。
- S2から受け取る権威:
  - 確認済みrepository identity。
  - default branch。
  - `READY` / `RESTRICTED` / `BLOCKED`。
- 観測:
  - 現在のローカルbranch。
  - `origin` fetch URL。
  - Gitが解決した実効push URL。
  - upstream設定。
  - ローカルHEAD。
- 外部権威:
  - `gh api` で確認済みrepositoryから直接取得する公開branch head SHA。
- 対象外:
  - 制御機構変更の公開差分審査: S4。
  - フックから観測できない任意子プロセスの完全仲介。
  - 認証情報侵害後の封じ込め全体: S6および外部IAM/SCM責任。

## 保証契約

### 公開操作の分類

- `git push` と `gh pr create` は、正規形に一致するかどうかより広く「SCM公開候補」として検出する。
- `git status && git push ...` のような複合シェル内の公開も検出し、S2へ `restricted_operation=True` として渡す。
- `RESTRICTED` または権威取得不能時は、SCM公開を通常承認より先に拒否する。
- `READY` であっても複合シェルは自律許可しない。

### `git push`

自律許可候補は次の2形式だけとする。

```text
git push origin HEAD:refs/heads/<current-branch>
git push --set-upstream origin HEAD:refs/heads/<current-branch>
```

さらに以下を要求する。

- 現在branchが名前付きbranchである。
- default branchではない。
- refspecのbranchが現在branchと一致する。
- `origin` fetch URLがS2で確認済みrepositoryと一致する。
- `git remote get-url --push --all origin` がちょうど1件で、確認済みrepositoryと一致する。
- `remote.origin.mirror=true` ではない。
- 通常pushではupstreamが `origin/<current-branch>` である。
- `--set-upstream` はupstreamが存在しない初回公開だけに使用する。
- 強制pushやその他のオプション・refspecは自律許可しない。

### `gh pr create`

- 現在branchはdefault branch以外の名前付きbranchである。
- `origin` は確認済みrepositoryと一致する。
- upstreamは `origin/<current-branch>` である。
- `--repo` / `-R`、`--head` / `-H`、`--base` / `-B` による対象上書きを許可しない。
- `--repo=value`、`-Rvalue` 等の表記差でも上書きを拒否する。
- ローカル `HEAD` と、確認済みrepositoryから直接取得した同branchのGitHub head SHAが一致する。
- ローカルupstream設定だけを「公開済み」の権威として扱わない。

## 具体化

### `reference/harness/scm_publication.py`

S3の公開意味論を担当する。

- SCM公開候補の広い検出。
- 複合シェルの自律許可除外。
- S2権威ゲートへの `restricted_operation` 供給。
- canonical pushのbranch / origin / pushurl / mirror / upstream検証。
- PR作成のrepository / branch / upstream / GitHub公開head検証。

### `reference/hooks/pre_tool_use_adapter.py`

S1のpolicy評価結果をS3へ渡し、S3がS2権威ゲートを含む公開保証経路を適用する。

```text
S1 policy
  ↓
S3 publication classification
  ↓
S2 authority gate
  ↓
S3 canonical semantics
  ↓
S4 publication review（後続）
```

### `reference/policies/policy.example.json`

- canonical pushだけを `allow` 候補にする。
- `gh pr create` をsemantic validation付きの `allow` 候補にする。
- read-only Git / PR操作をコマンド末尾までanchorし、`git status && ...` のような複合シェルをread-only allowへ誤分類しない。
- force pushはdeny規則として維持する。

## 決定的な根拠

### `reference/harness/tests/test_scm_publication.py`

- SCM公開候補分類。
- S2 `RESTRICTED` が公開意味論より先に適用されること。
- canonical / noncanonical push。
- detached HEAD / default branch拒否。
- origin mismatch。
- pushurl mismatch / 複数push URL / mirror拒否。
- upstream lifecycle。
- PR target overrideの各表記拒否。
- GitHub公開branch headとローカルHEADの一致。
- 複合シェル内pushの検出と自律許可除外。

### `reference/hooks/tests/test_policy_engine.py`

- canonical push / PR createだけがpolicy allow候補になること。
- noncanonical pushは通常承認へ残ること。
- trusted adapterがS3の合成保証経路を呼ぶこと。

## 具体化で判明した指摘

### 複合シェルによるread-only allow迂回

初期S3実装では、`is_scm_publication()` がコマンド先頭だけを見ていた。一方、従来のread-only policy規則は末尾までanchorされていなかったため、次の形式がread-only `allow` と判定され、S3の公開分類からも漏れる可能性があった。

```text
git status && git push ...
```

公開検出を正規形より広くし、複合シェル内の `git push` / `gh pr create` も検出するよう修正した。policy側のread-only規則も末尾までanchorし、複合シェル自体を自律許可対象から除外した。

### PR対象上書きの表記差

初期実装は `--repo` のような独立tokenだけを拒否し、`--repo=other/repo` や `-Rother/repo` を見落としていた。オプション意味論で判定するよう一般化し、repository / head / baseの長短・equals形式を拒否した。

### upstream設定を公開証拠とみなしていた

`@{u}=origin/<branch>` はローカルGit設定であり、GitHub上へ現在HEADが公開されていることを保証しない。PR作成時は確認済みrepositoryのGitHub branch head SHAを直接取得し、ローカルHEADとの一致を要求するよう修正した。

## レビュー結果

- [x] 権威レビュー
  - repository authorityはS2、公開branch headはGitHub直接取得とした。
- [x] 信頼境界レビュー
  - ローカルGit設定を観測に限定し、GitHub公開状態と分離した。
- [x] 根拠完全性レビュー
  - branch、origin、pushurl、upstream、GitHub headをそれぞれ検証する。
- [x] 失敗形態レビュー
  - detached HEAD、default branch、URL不一致、multiple pushurl、mirror、upstream不一致、GitHub head不一致をfail-closedとした。
- [x] 迂回レビュー
  - 複合シェル、target override表記差、ローカルupstream偽装をレビューして回帰テストへ固定した。
- [x] 責任分担レビュー
  - repository authority=S2、SCM意味論=S3、control-plane review=S4へ分離した。
- [x] 保証欠落レビュー
  - 任意子プロセス・credential compromise containment・GitHub server-side authorizationは対象外として明示した。
- [x] 実装適合レビュー
  - PR #1の `common.py` からS3責務を独立モジュールへ移した。

## 残存リスクと対象外

- hookから直接観測できないalias展開、任意子プロセス、別実行経路の完全仲介は保証しない。
- 認証情報が侵害された場合にGitHub APIを直接呼ぶ等の迂回をS3単体で封じ込めるとは主張しない。Sandbox/IAM/GitHub server-side rulesへ責任を分担する。
- `gh pr create` のGitHub branch head確認は公開状態を保証するが、GitHub側の最終認可やRulesets自体の完全性は保証しない。
- 制御機構変更を含むbranchかどうかはS4で評価する。

## 収束判定

具体化と再レビューで、複合シェル迂回、PR target overrideの表記差、ローカルupstreamを公開権威として扱う問題を発見し、一般化した規則と決定的テストへ移した。

現時点でS3内部に新たなマージ阻害指摘は残っていない。S4の制御機構公開審査とS6の外部封じ込め責任を明示的な後続依存として、S3は収束状態とする。
