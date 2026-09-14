# Go Vendor Integration / Deployment 実装ノート

## 位置づけ

本書は Agent Harness 全体仕様の Vendor Integration / Deployment を Go production implementation でどのように具体化するかを記録する。

S6 は保証スライスであり、Claude Code / Codex / Devin という製品名を core assurance の内部モデルへ持ち込むためのものではない。Vendor adapter は lifecycle event / response schema を共通契約へ写像し、S1〜S5 の保証結果を弱化しないことを責務とする。

## 共通 lifecycle contract

Go 実装は vendor input を次の共通イベントへ正規化する。

- `SessionStart`
- `PreToolUse`
- `Stop`

`PreToolUse` は `policy.Action` へ、`Stop` は `completion.Request` へ変換する。

`stop_hook_active` は repository stateへ永続化せず、vendor payloadから follow-up Stop marker として `completion.Request.FollowUp` へ渡す。

## Vendor別 decision mapping

### Claude Code

- `allow` → allow
- `ask` → ask
- `deny` → deny

### Codex

現行参照adapter contractでは native `ask` を直接表現しないため、

- `allow` → allow
- `ask` → deny（reasonにapproval requiredを保持）
- `deny` → deny

とする。`ask` を `allow` へ弱化しない。

### Devin

- `allow` → empty success response
- `ask` / `deny` → block

とする。`ask` は approval required の理由を保持する。

## Stop mapping

S5 Completion Assurance の結果に対して、`complete` だけを vendor Stop 成功へ写像する。

- `blocked` → block
- `review_required` → blockし、Agentへsemantic completion reviewを要求
- `complete` → Stop許可

したがって deterministic assurance が一度成功しただけでvendor adapterがタスク終了を許可する経路はない。

## SessionStart

SessionStartは診断・文脈供給だけを行い、completion authority snapshotを保存しない。権威あるcompletion判断はStop時にfresh stateを再評価するS5へ委譲する。

## Fail-closed

次はfail-closedとする。

- malformed JSON
- unsupported lifecycle event
- missing/invalid `tool_name` / `tool_input` / `cwd`
- unsupported vendor
- trusted evaluator未接続
- S1〜S5 evaluator error
- unknown decision value

unknown vendor decisionはallowに変換しない。

## 実装

- `internal/vendor/adapter.go`
  - vendor/event normalization
  - common Action / Completion Request変換
  - vendor decision mapping
- `internal/vendor/runtime.go`
  - lifecycle dispatch
  - trusted evaluator dependency injection
  - vendor response rendering
- tests
  - ask mapping
  - Stop review loop
  - follow-up completion
  - malformed/unknown input
  - evaluator failure

## Production wiring boundary

`internal/vendor` は vendor-specific schema translationを担い、trusted evaluator自体の選択権を持たない。Productionでは固定binaryがtrusted dependenciesを注入する必要がある。

この分離により、repository側の設定やvendor payloadから任意adapter / evaluatorを差し替える設計を避ける。

## Deployment trust chain

Go単一binary化でPython interpreter/import pathの可変性は減るが、代わりに次のtrust chainがproduction responsibilityになる。

```text
source commit
  ↓
Go toolchain + build flags
  ↓
build artifact
  ↓
provenance / digest / signature
  ↓
distribution channel
  ↓
installed binary
  ↓
trusted configuration
  ↓
vendor hook invocation
```

最低限、次を識別・検証可能にする必要がある。

- source commit ↔ artifact対応
- Go version / target OS / architecture
- reproducible or attestable build provenance
- artifact SHA-256
- signing / verification policy
- versioning
- staged update
- rollback
- revocation
- stale binary検出
- installed binaryとtrusted configのbinding

これらはGo codeだけでは保証できず、CI/CD・artifact registry・OS/package deployment・workload identity等の外部強制境界と組み合わせる。

## Credential containment

Hookによるdenyはcredential compromise後の外部権限境界の代替ではない。

production deploymentでは、可能な範囲で次を外部強制する。

- short-lived credentials
- repository scoped permissions
- least privilege
- network egress controls
- sandbox / workload isolation
- GitHub server-side rules
- secretをrepository writable領域へ置かない

## 対象外

- vendor製品自身の完全性
- undocumented vendor behaviorの保証
- hookを経由しない任意子プロセスの完全仲介
- credential compromise後の完全封じ込め
- build system / registry / OS updater自体の完全性

## 収束判定

Vendor mapping coreについて、S1〜S5結果を弱化しないこと、Stop loopを維持すること、unknown/errorをfail-openしないことをunit testへ固定した状態を初回収束点とする。

Production deployment trust-chainは外部責任として明示し、artifact provenance / signing / rollout / revocationを実配備時の必須保証として残す。