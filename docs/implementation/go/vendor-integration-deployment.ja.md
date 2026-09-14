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
- `internal/trustedexec/api.go`
  - S1〜S4共通evaluatorへのproduction接続
  - Stop時のfresh Repository Authority + S5実行
  - trusted completion gate binding
- `internal/repository/completion.go`
  - mutation targetを要求しないStop-time authority handoff
- `main.go`
  - `agent-harness vendor <claude|codex|devin>`
  - `agent-harness version`
- tests
  - ask mapping
  - Stop review loop
  - follow-up completion
  - malformed/unknown input
  - evaluator failure
  - trusted completion gate path

## Production wiring boundary

`internal/vendor` は vendor-specific schema translationを担い、trusted evaluator自体の選択権を持たない。Productionでは固定binaryが `internal/trustedexec` のevaluatorを注入する。

`agent-harness vendor <name>` はこの固定wiringを使用し、repository側の設定やvendor payloadから任意adapter / evaluatorを差し替えない。

Completion gateもrepository内scriptを直接実行せず、trusted binaryと同じtrusted rootの固定名 `completion-gate` executableへ束縛する。これにより、repository mutationがcompletion判定そのものを書き換える経路を持たせない。

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

### Binary self-identification

`internal/buildinfo` と `agent-harness version` は、Go toolchainが埋め込んだ次の情報をJSONで出力する。

- Go version
- GOOS
- GOARCH
- module path
- VCS revision
- VCS modified flag
- VCS time

これによりinstalled binaryをsource commit / platformへ照合するための観測点を提供する。ただしbinary自身のself-reportは独立した署名・provenance証明ではない。artifact digest / signature / attestationとの照合が別途必要である。

### CI assurance

GitHub Actions `Agent Harness Go` はLinux/macOS双方で次を実行する。

- `go test ./...`
- `go test -race ./...`
- `go vet ./...`
- `go build ./...`

これらはsource-level / runtime test assuranceであり、artifact distributionの完全性を保証しない。

GitHub artifact attestationを採用する場合、private repositoryでの利用可否はGitHub planとorganization設定に依存するため、利用可能性を確認してからproduction requirementへ昇格する。attestationが利用できない場合でも、SHA-256、署名、配布経路、installed artifact verificationを別の決定的mechanismで確立する必要がある。

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
- artifact signing / attestation service自体の完全性

## 収束判定

Vendor mapping coreについて、S1〜S5結果を弱化しないこと、Stop loopを維持すること、unknown/errorをfail-openしないことをunit testへ固定した状態を初回収束点とする。

Production deployment trust-chainについては、binary self-identificationとCI検証をGo側の観測可能な具体化として追加した。artifact provenance / signing / rollout / rollback / revocation / installed artifact verificationは外部強制境界との接続が必要であり、実配備時の追加適合条件として残す。