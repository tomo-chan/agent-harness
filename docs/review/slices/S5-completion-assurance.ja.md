# S5 — 完了保証

## 状態

実装移植とレビューを完了。完了判定をSessionStart時点の書込み可能な状態から切り離し、Stop時の現在状態だけで読み取り専用例外または通常の決定的完了検査を選択する保証境界として具体化した。

## 主張

1. 書込み可能なSessionStartスナップショットを完了判定の権威にしない。
2. Stop時に現在のリポジトリ保護状態とGit状態を再評価する。
3. `READY` で、クリーンな確認済み既定ブランチの `HEAD` がGitHubから直接取得した先頭SHAと一致する場合だけ、リポジトリ成果物について読み取り専用と判断する。
4. それ以外または確認不能時は決定的完了検査を実行する。

## 権威と責任境界

- モデル上の前提: S1、S2。物理的な積層順序上はS4の後に配置するが、S3/S4を意味論上の前提とはしない。
- 権威:
  - S2の現在のrepository posture。
  - 確認済みGitHub repositoryから直接取得したdefault branch head SHA。
- 観測:
  - 現在branch。
  - worktreeのcleanliness（untrackedを含む）。
  - ローカルHEAD。
- 非権威:
  - SessionStart時点のcompletion snapshot。
  - `origin/<default>` 等のローカルremote-tracking ref。
- 決定的な代替保証:
  - `reference/scripts/completion_gate.sh`。
- 対象外:
  - セッション中に外部副作用が一切なかったことの証明。
  - 外部サービスへ行った変更の完全な追跡。
  - vendor固有Stopイベントへの接続: S6。

## 保証契約

### SessionStart

- 完了判定用の権威あるbaseline fileを保存しない。
- SessionStartは「Stop時に再評価する」というcontextだけを返す。
- 評価対象リポジトリと同じOS identityから書換え可能なローカル状態を独立した完了権威とはみなさない。

### 読み取り専用repository-state例外

通常の成果物向け完了検査を省略できるのは、次をすべて満たす場合だけとする。

1. Stop時のrepository postureが `READY`。
2. repository identityとdefault branchが現在の根拠から確定している。
3. 現在branchが確認済みdefault branch。
4. `git status --porcelain=v1 --untracked-files=all` が空。
5. local `HEAD` が取得できる。
6. 確認済みGitHub repositoryからdefault branch head SHAを直接取得できる。
7. local `HEAD == GitHub default branch head SHA`。

上記のどれかが成立しない場合は読み取り専用とは判定しない。

### 通常完了検査へのフォールバック

- feature branch、dirty worktree、`RESTRICTED`、`BLOCKED`、posture取得不能、GitHub取得不能、HEAD不一致は、通常の決定的完了検査へ送る。
- 「確認できない」ことを読み取り専用成功へ変換しない。
- 完了検査自体の実行エラー・timeoutはfail-closedとする。

## 具体化

### `reference/harness/completion.py`

- SessionStartで権威baselineを保存しない。
- Stop時にrepository postureを再評価する。
- default branch / clean worktree / local HEADを現在観測する。
- GitHub default branch headを直接取得する。
- 読み取り専用repository-state例外または通常completion gateを選択する。

### `reference/scripts/completion_gate.sh`

読み取り専用例外が成立しない場合の決定的なdelivery gate。現在branch、dirty state、verification command、commit存在、upstream等のrepository delivery条件を検査する。

S5の読み取り専用例外とこのgateは役割が異なる。前者は「成果物向けgateを省略できるほど現在repositoryが権威状態と一致しているか」を判定し、後者は通常の変更セッションに対するdelivery completionを判定する。

## 決定的な根拠

### `reference/harness/tests/test_completion.py`

- SessionStartが権威baselineを保存しないこと。
- cleanな `READY` default branch + GitHub head一致だけがgateを省略すること。
- `RESTRICTED` default branchはgateを省略しないこと。
- feature branchはgateを実行すること。
- dirty default branchはgateを実行すること。
- local/GitHub HEAD不一致はgateを実行すること。
- ローカル `origin/main` を完了権威にしないこと。
- GitHub head取得不能時はgateを実行すること。
- posture評価不能・`BLOCKED` はgateを実行すること。

## 具体化で判明した指摘

### `RESTRICTED` を読み取り専用例外に含めていた

PR #1の元実装は次の条件だった。

```text
BLOCKED ではない
+ repository/default branchが取得できる
+ clean default branch
+ local HEAD == GitHub HEAD
```

このため、repository identityやGitHub保護根拠が不足して `RESTRICTED` になっていても、他の条件が揃えば通常completion gateを省略できた。

S5の主張は「確認済み既定ブランチ」であり、S2では完全に確認できた権威状態を `READY` と定義している。このため読み取り専用例外を `report.state == READY` に限定した。

これは権威状態を「拒否対象かどうか」だけで解釈せず、その状態がどの保証に十分な根拠を持つかで判断すべきことを示す。

## レビュー結果

- [x] 権威レビュー
  - repository postureとGitHub default branch headを現在の権威とした。
- [x] 信頼境界レビュー
  - SessionStart snapshotとlocal remote-tracking refを権威から除外した。
- [x] 根拠完全性レビュー
  - READY、default branch、cleanliness、local HEAD、GitHub HEADの全条件を要求した。
- [x] 失敗形態レビュー
  - posture/Git/GitHub取得不能、dirty、branch不一致、HEAD不一致を通常gateへフォールバックする。
- [x] 迂回レビュー
  - writable snapshotや `origin/main` の書換えで読み取り専用例外を成立させられない。
- [x] 責任分担レビュー
  - repository authority=S2、completion=S5、vendor Stop wiring=S6へ分離した。
- [x] 保証欠落レビュー
  - 外部副作用の不存在は保証しないことを明示した。
- [x] 実装適合レビュー
  - PR #1のcompletion実装を移植し、RESTRICTED例外の保証不一致を修正した。

## 残存リスクと対象外

- 読み取り専用例外が証明するのはrepository成果物について現在のローカル状態がGitHub default branchと一致していることであり、セッション中に外部副作用がなかったことではない。
- completion gateのrepository固有verification内容は配備・対象repository側の設定責任を含む。
- Stopイベントが必ずこのcompletion保証を呼ぶことはvendor接続の責任であり、S6で具体化する。

## 収束判定

S5のレビューで、元実装が `RESTRICTED` を読み取り専用例外へ含め得ることを発見し、`READY` のみへ保証条件を強化した。SessionStart snapshotやlocal remote-tracking refを権威にせず、確認不能な状態は通常の決定的completion gateへ戻す経路をテストへ固定した。

現時点でS5内部に新たなマージ阻害指摘は残っていない。S6によるStopイベント接続を外部依存として、S5は収束状態とする。
