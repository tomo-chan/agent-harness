# Go Completion Assurance 実装ノート

## 位置づけ

Completion Assurance は「既知で決定的に表現可能な完了条件」と、Agentが担う非決定的なsemantic completion evaluationを分離する。

S5 は保証スライスであり、vendor hook形式ではない。Go coreは `internal/completion` に実装し、Claude Code / Codex / Devin のStopイベント変換はS6で接続する。

## 中核契約

決定的保証が成功しても、それだけでタスクが意味的に完了したとは主張しない。

```text
fresh deterministic assurance
  ↓
Evidence
  ↓
Agent semantic completion review
  ├─ 追加作業 → 継続
  ├─ 要求元判断が必要 → ask
  └─ 完了可能 → follow-up Stop
                     ↓
              deterministic recheck
                     ↓
                  complete
```

## Authority

Stop時に取得したfresh Repository Authority reportを入力とする。SessionStart snapshot、過去のpreflight、local `origin/main` 等をcompletion authorityとして受け入れない。

S5 coreは次を再照合する。

- current branch
- local HEAD
- fresh reportに束縛されたrepository/default branch
- no-delivery-delta判定時のGitHub default branch head
- worktree cleanliness（untrackedを含む）

## No-delivery-delta

次のすべてが成立する場合だけ「repository delivery deltaなし」を決定的Evidenceとして成立させる。

- fresh reportが`READY`
- current branch = authoritative default branch
- worktreeがtracked/untrackedともclean
- local HEAD = fresh report HEAD
- GitHubから直接取得したdefault branch head = local HEAD

これはsemantic completionではなく、repository delivery差分がないという機械的事実だけを意味する。

## 通常のdeterministic gate

no-delivery-deltaを証明できない場合はrepository-specific `Gate`へ委譲する。

Gate失敗は`blocked`。Gate成功はdeterministic assurance成功に過ぎず、初回Stopでは`review_required`を返す。

## Follow-up

初回のdeterministic assurance成功:

- `review_required`
- EvidenceをAgentへ返す
- task requirements / plan / execution results / unresolved concerns / new findingsを非決定的に評価させる

follow-up Stop:

- deterministic assuranceを再実行
- 依然成功している場合だけ`complete`

書込み可能なrepository stateに「Agent review済み」flagを保存しない。follow-up markerのvendor-specific取得と信頼境界はS6で扱う。

## Evidence

- repository
- branch
- local head
- default branch
- GitHub default head（適用時）
- no-delivery-delta
- checks
  - repository_authority
  - current_branch
  - local_head
  - clean_worktree
  - github_default_head
  - deterministic_gate

unknownは成功に変換しない。

## 検証

`internal/completion/completion_test.go`で次を固定する。

- clean default branchでも初回はsemantic review必須
- follow-upでdeterministic recheck後にcomplete可能
- feature branchはdeterministic gateを使用
- gate failureはblocked
- dirty default branchはno-delta shortcut不可
- GitHub head mismatchはno-delta shortcut不可
- branch/HEAD変化はblocked
- provider欠落はfail closed

## 対象外

- vendor-specific Stop schema / response mapping
- follow-up markerのvendorごとの意味論
- repository-specific gate commandの配備方法
- CI / artifact / deployment evidenceの全体系
- semantic completionの決定化
- task requirementsの完全な機械表現

これらをS5 coreの適合主張へ含めない。
