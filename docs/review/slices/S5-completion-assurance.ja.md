# S5 — 完了保証

## 状態

**再レビュー中。** MF-S5-001の検討により、完了条件には決定的に保証できるものと、Agentが探索結果を踏まえて非決定的に評価すべきものが共存することを明確化した。S5は決定的保証だけでタスク完了を確定せず、そのEvidenceをAgentへ返し、Agent自身が非決定的な完了評価を行う最小ループを実装する。

## 主張

1. 書込み可能なSessionStartスナップショットを完了判定の権威にしない。
2. Stop時に現在のリポジトリ保護状態とGit状態を再評価する。
3. 決定的に表現可能な既知の完了条件は仕組みで保証し、その結果をEvidenceとしてAgentへ返す。
4. 決定的保証の成立だけをもって、タスク要求が意味的に満たされたとは判断しない。
5. AgentはEvidenceに加え、タスク要求、Plan、実行結果、未解決事項、新しい発見・洞察を踏まえて非決定的な完了評価を行う。
6. Agentが追加作業を必要と判断すれば自律的に継続し、要求元の判断が本当に必要な場合だけ確認する。
7. 非決定的な完了条件を事前に網羅的な決定的分類へ還元することを目的としない。

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
- 決定的な保証:
  - clean READY default branchとGitHub head一致によるno-change Evidence。
  - `reference/scripts/completion_gate.sh` によるdelivery Evidence。
- Agentの非決定的責任:
  - タスク要求とPlanの再評価。
  - 実行結果が要求を満たしているかの評価。
  - 未解決事項や新しい発見・洞察の評価。
  - 追加作業、要求元への確認、完了の選択。
- 対象外:
  - 非決定的評価そのものを決定的に証明すること。
  - セッション中の外部副作用不存在の証明。
  - 外部サービス変更の完全追跡。
  - vendor固有Stop wiring: S6。

## 保証契約

### SessionStart

repositoryと同じ権限で書換え可能なbaseline fileを完了権威として保存しない。

### 決定的Evidence

cleanなno-change経路では次をすべて満たすことを確認する。

1. Stop時のrepository postureが `READY`。
2. repository identityとdefault branchが現在の根拠から確定している。
3. 現在branchが確認済みdefault branch。
4. `git status --porcelain=v1 --untracked-files=all` が空。
5. local `HEAD` が取得できる。
6. 確認済みGitHub repositoryからdefault branch head SHAを直接取得できる。
7. local `HEAD == GitHub default branch head SHA`。

この条件は「repositoryにdelivery差分がない」というEvidenceであり、タスク要求上変更不要だったことや、タスクそのものの完了を意味しない。

no-change経路が成立しない場合は `reference/scripts/completion_gate.sh` により通常の決定的delivery保証を行う。

### Agent完了評価ループ

決定的保証が失敗した場合は完了をblockする。

決定的保証が成立した最初のStopでは、完了を即時許可せず、保証Evidenceと次の評価要求をAgentへ返す。

```text
決定的保証
   ↓
 Evidence
   ↓
Agentの非決定的完了評価
   ├─ 追加作業が必要 → 自律継続
   ├─ 要求元判断が必要 → 確認
   └─ 完了可能 → 再Stop
```

Agentは少なくとも次を再評価する。

- タスク要求。
- Planと実行結果。
- 未解決事項。
- 作業中に得られた新しい発見・洞察。
- 発見によって当初の前提や要求の理解が変化していないか。

vendorの `stop_hook_active` を、Stop hookによる継続後の再Stop識別に利用する。これによりrepository内へ合意状態や完了状態を永続化せず、一度の非決定的評価ループを形成する。

再Stopでも決定的保証を再実行し、途中の追加作業によって保証が崩れていれば完了を拒否する。保証が引き続き成立していれば完了を許可する。

## モデル指摘

### MF-S5-001 — 決定的な成果物状態だけではタスク完了を保証できない

変更実装を要求されたタスクでAgentが何も変更しない場合でも、clean default branchかつ `local HEAD == GitHub HEAD` は成立し得る。また、変更とテストが正常に完了していても、探索中により重要な問題や要求の不足を発見している可能性がある。

したがって、repository stateやdelivery gateの成功だけからタスク完了を導出してはならない。

一方、非決定的な完了条件をすべて事前に分類・契約化することも採用しない。それでは未知の発見を既知の分類へ押し込め、RAEMがAgentへ期待する探索能力を弱める。

採用する境界は次のとおり。

```text
既知で決定的に表現可能な完了条件
          ↓
      仕組みで保証
          ↓
        Evidence
          ↓
        Agent
  ├─ タスク要求
  ├─ Plan / 実行結果
  ├─ 未解決事項
  └─ 新しい発見・洞察
          ↓
   非決定的完了評価
          ↓
  継続 / 確認 / 完了
```

この構造はRAEMの次の原則に従う。

> 決定的に表現可能な既知の知識は仕組みに固定し、AIエージェントの非決定的能力は、未知の問題の探索と対象領域の進化に集中させる。

## Evolutionへの接続

完了時の非決定的評価で得られた発見は、単なるStop可否の材料ではなくEvolutionの入力である。

```text
非決定的探索・完了評価
        ↓
    新しい発見
        ↓
     一般化可能か
        ↓
      Evolution
        ↓
モデル / 規則 / Evidenceを改善
```

繰り返し現れる既知のパターンが一般化できた場合は、その部分を次のサイクルで決定的な保証へ移せる。未知の可能性そのものを事前に列挙して塞ぐことはしない。

## 実装根拠

- `reference/harness/completion.py`
  - 決定的completion Evidenceを生成する。
  - 最初のpassing Stopを一度blockし、Evidenceと非決定的完了評価の指示をAgentへ返す。
  - `stop_hook_active` のfollow-up Stopでは決定的保証を再実行したうえで完了を許可する。
- `reference/harness/tests/test_completion.py`
  - no-change / delivery gate双方で最初のStopがAgent reviewへ移ることを固定する。
  - follow-up Stopが循環せず完了できることを固定する。
  - follow-up時でも決定的保証失敗を迂回できないことを固定する。

Codexの一次実装ではStop payloadに `stop_hook_active` が含まれ、Stop hookがblockした後の継続を識別するために利用されている。S6では各vendor adapterがこの入力を共通S5処理へ透過的に渡す責任を持つ。

## レビュー結果

- [x] 権威レビュー — repository-state権威は明確。
- [x] 信頼境界レビュー — writable snapshot/local remote refを非権威化。
- [x] 根拠完全性レビュー — 決定的保証と非決定的完了評価の双方を完了経路に含めた。
- [x] 失敗形態レビュー — 決定的Evidence取得不能・gate失敗は完了拒否。
- [x] 迂回レビュー — `stop_hook_active` でも決定的保証を再実行する。
- [x] 責任分担レビュー — 既知の決定的保証は仕組み、未知を含む意味評価はAgent。
- [x] 保証欠落レビュー — MF-S5-001をAssuranceから非決定的評価への接続として処理。
- [ ] 実装適合レビュー — CIとS6 vendor wiringで最終確認する。

## 収束判定

S5は**実装適合の再確認待ち**。MF-S5-001のモデル上の解決は、決定的完了条件を仕組みで保証し、そのEvidenceをAgentへ返したうえで非決定的完了評価を必須の一ターンとして残すことで具体化した。