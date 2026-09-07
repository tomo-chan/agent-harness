# S5 — 完了保証

## 状態

**再レビュー中。** MF-S5-001の検討により、S5の保証対象を「タスクの意味的完了」ではなく「repository delivery stateの完了保証」に限定する責任境界を明確化した。実装を試行した結果、Stopで要求元確認を強制すると、確認後も同じStop判定に戻る循環が発生し、S5へ要求解釈・合意管理を持ち込む設計は過剰と判断した。

## 主張

1. 書込み可能なSessionStartスナップショットを完了判定の権威にしない。
2. Stop時に現在のリポジトリ保護状態とGit状態を再評価する。
3. cleanな確認済みdefault branchで `local HEAD == GitHub default branch head` が成立する場合、repository delivery上は追加成果物が存在しない状態として扱える。
4. S5は、そのタスクでrepository変更が必要だったか、ユーザー要求を意味的に満たしたかまでは保証しない。
5. タスク要求の解釈、Plan、Auto、必要な確認と合意形成はAgent実行系の責任とし、S5へ独自のタスク分類・合意状態管理を追加しない。

## 権威と責任境界

- モデル上の前提: S1、S2。
- repository-state権威:
  - S2の現在のrepository posture。
  - 確認済みGitHub repositoryから直接取得したdefault branch head SHA。
- 観測:
  - 現在branch、worktree cleanliness、local HEAD。
- 非権威:
  - 書込み可能なSessionStart completion snapshot。
  - `origin/<default>` 等のlocal remote-tracking ref。
- 決定的な代替保証:
  - `reference/scripts/completion_gate.sh`。
- Agent実行系の責任:
  - タスク要求の解釈。
  - Plan/Auto等による自律実行範囲の管理。
  - 要求が曖昧な場合の確認。
  - repository変更不要という判断を要求元へ確認すべきかの判断。
- 対象外:
  - タスクの意味的完了そのものの証明。
  - セッション中の外部副作用不存在の証明。
  - 外部サービス変更の完全追跡。
  - vendor固有Stop wiring: S6。

## 保証契約

### SessionStart

repositoryと同じ権限で書換え可能なbaseline fileを完了権威として保存しない。

### repository-state一致

次をすべて満たすと「現在のrepository成果物がGitHub default branchと一致する」ことを確立できる。

1. Stop時のrepository postureが `READY`。
2. repository identityとdefault branchが現在の根拠から確定している。
3. 現在branchが確認済みdefault branch。
4. `git status --porcelain=v1 --untracked-files=all` が空。
5. local `HEAD` が取得できる。
6. 確認済みGitHub repositoryからdefault branch head SHAを直接取得できる。
7. local `HEAD == GitHub default branch head SHA`。

この条件はrepository delivery stateの保証であり、「タスクが読み取り専用だった」「変更不要というタスク要求だった」という意味的主張には拡張しない。

### 通常完了検査

上記repository-state一致が成立しない場合は `reference/scripts/completion_gate.sh` による通常の決定的完了検査へ送る。

## モデル指摘

### MF-S5-001 — repository stateだけでは、変更なしでタスクを完了してよいか判断できない

変更実装を要求されたタスクでAgentが何も変更しない場合でも、clean default branchかつ `local HEAD == GitHub HEAD` は成立し得る。このためrepository stateだけからタスク要求を推論してはならない。

当初は、変更なし完了時に要求元との合意をS5で必須化する案を試行した。しかしStopをblockするだけでは、要求元確認後にも同じ判定へ戻り続ける。これを解消するために独自の合意状態やタスク分類をS5へ導入すると、S5の責任を不必要に拡大する。

そこでMF-S5-001は、S5の保証範囲を次のように限定することで扱う。

```text
タスク要求
  ↓
Agent実行系
  ├─ Plan / Auto
  ├─ 探索・判断
  └─ 必要時のみ要求元へ確認
  ↓
repository state
  ↓
S5
  └─ repository delivery stateだけを決定的に保証
```

S5は「タスク要求が満たされた」という主張を行わない。したがってrepository stateからタスク要求を推論する必要もない。

## 実装試行から得た根拠

一時的に、clean default branchをStop時にblockし、要求元との合意を要求する実装を試行した。その結果、合意をS5へ安全かつ単純に戻す経路がなければStopが循環することを確認した。この試行は撤回し、repository-state実装は元に戻した。

この結果から、要求解釈・確認・合意形成をS5へ持ち込まず、既存AgentのPlan/Auto/approval等を利用する責任分担を採用する。

## 既に固定済みの根拠

`reference/harness/tests/test_completion.py` はrepository-state側について、READY/default branch/clean/local HEAD/GitHub HEAD、RESTRICTED/BLOCKED、取得不能、HEAD不一致等を固定している。

## レビュー結果

- [x] 権威レビュー — repository-state権威は明確。
- [x] 信頼境界レビュー — writable snapshot/local remote refを非権威化。
- [x] 根拠完全性レビュー — S5の保証範囲をrepository delivery stateに限定。
- [x] 失敗形態レビュー — repository-state取得不能は通常gateへfallback。
- [x] 迂回レビュー — writable snapshot/local remote refによる迂回は排除。
- [x] 責任分担レビュー — タスク要求解釈と確認はAgent実行系、repository delivery保証はS5。
- [x] 保証欠落レビュー — MF-S5-001を保証範囲の明確化として処理。
- [ ] 実装適合レビュー — PR #10の最新状態で再確認する。

## 収束判定

S5は**実装適合の再確認待ち**。MF-S5-001は、追加のタスク要求管理機構を導入せず、S5の保証対象をrepository delivery stateへ限定することで解消した。今後、Plan/Auto等の実運用で確認過多や誤完了が具体的に観測された場合は、その実例をEvidenceとして次のEvolution対象とする。
