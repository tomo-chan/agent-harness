# S5 — 完了保証

## 状態

**再レビュー中。** 実装移植後のCodex Reviewにより、現在のrepository stateだけでは「読み取り専用タスクが完了した」のか「変更が必要なタスクを何もせず終了した」のかを識別できないモデル指摘が発見された。この指摘が解消するまでS5を収束状態とはしない。

## 主張

1. 書込み可能なSessionStartスナップショットを完了判定の権威にしない。
2. Stop時に現在のリポジトリ保護状態とGit状態を再評価する。
3. repository stateがGitHub default branchと一致することだけでは、タスクが読み取り専用であったことを証明しない。
4. 成果物向け完了検査を省略するには、repository stateの一致に加えて、独立した信頼済み根拠から「このタスクはrepository変更を要求しない」と確立できなければならない。
5. タスク意図を信頼済み根拠から確立できない場合、またはrepository stateを確認できない場合は決定的完了検査を実行する。

## 権威と責任境界

- モデル上の前提: S1、S2。
- repository-state権威:
  - S2の現在のrepository posture。
  - 確認済みGitHub repositoryから直接取得したdefault branch head SHA。
- task-intent権威:
  - **未具体化。** 評価対象repositoryと同じ権限で書換え可能なSessionStart cacheやagent自己申告は権威にできない。
  - trusted control plane、trusted launcher input、または同等の独立したタスク分類根拠を候補として具体化する必要がある。
- 観測:
  - 現在branch、worktree cleanliness、local HEAD。
- 非権威:
  - 書込み可能なSessionStart completion snapshot。
  - `origin/<default>` 等のlocal remote-tracking ref。
  - agentによる「変更不要だった」という自己申告。
- 決定的な代替保証:
  - `reference/scripts/completion_gate.sh`。
- 対象外:
  - セッション中の外部副作用不存在の証明。
  - 外部サービス変更の完全追跡。
  - vendor固有Stop wiring: S6。

## 保証契約

### SessionStart

- repositoryと同じ権限で書換え可能なbaseline fileを完了権威として保存しない。
- task intentを利用する場合、それは評価対象から独立した信頼境界で確立されなければならない。

### repository-state一致

次をすべて満たすと「現在のrepository成果物がGitHub default branchと一致する」ことだけを確立できる。

1. Stop時のrepository postureが `READY`。
2. repository identityとdefault branchが現在の根拠から確定している。
3. 現在branchが確認済みdefault branch。
4. `git status --porcelain=v1 --untracked-files=all` が空。
5. local `HEAD` が取得できる。
6. 確認済みGitHub repositoryからdefault branch head SHAを直接取得できる。
7. local `HEAD == GitHub default branch head SHA`。

この条件だけから「タスクが読み取り専用だった」と推論してはならない。

### 完了検査省略条件

通常の成果物向け完了検査を省略できるのは、次の両方を独立に確立できる場合だけとする。

- repository-state一致。
- 信頼済みtask intentがrepository変更を要求しないこと。

task intentの権威が未確立・取得不能・曖昧な場合は通常完了検査へ送る。

## モデル指摘

### MF-S5-001 — repository stateからtask intentを推論できない

変更実装を要求されたタスクでagentが何も変更しない、または変更を破棄してStopした場合でも、clean default branchかつ `local HEAD == GitHub HEAD` は成立する。この状態は成功したread-only taskと区別できない。

したがって旧主張「cleanな確認済みdefault branchならread-only repository-state例外」は根拠不足であり、実装適合の局所修正では解決できない。

必要な進化は次のとおり。

```text
タスク意図
  ↓ 独立した信頼済み権威
変更要求あり / 変更要求なし
  ↓
Stop時repository state
  ↓
完了検査省略可否
```

書込み可能なSessionStart snapshotを導入するだけではS5主張1と信頼境界に反するため採用しない。

## 既に固定済みの根拠

`reference/harness/tests/test_completion.py` はrepository-state側について、READY/default branch/clean/local HEAD/GitHub HEAD、RESTRICTED/BLOCKED、取得不能、HEAD不一致等を固定している。ただしMF-S5-001に対応するtask-intent保証は未実装であり、追加の決定的テストが必要である。

## レビュー結果

- [x] 権威レビュー — repository-state権威は明確。
- [x] 信頼境界レビュー — writable snapshot/local remote refを非権威化。
- [ ] 根拠完全性レビュー — **task intentの独立根拠が不足。**
- [x] 失敗形態レビュー — repository-state取得不能は通常gateへfallback。
- [x] 迂回レビュー — writable snapshot/local remote refによる迂回は排除。
- [ ] 責任分担レビュー — **task-intent権威をどの層が供給するか未確定。**
- [ ] 保証欠落レビュー — **MF-S5-001を解消する必要がある。**
- [ ] 実装適合レビュー — モデル更新後に再実施する。

## 収束判定

S5は現在**未収束**。MF-S5-001「repository stateからtask intentを推論できない」がマージ阻害のモデル指摘として残っている。task-intent権威と保証契約を具体化し、実装・決定的テストへ固定した後に再レビューする。
