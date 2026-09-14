# S6 保証スライス — Vendor Integration / Deployment

## 主張

Vendor adapterはvendor lifecycle eventを共通Agent Harness contractへ写像し、S1〜S5のdecision / completion semanticsを弱化しない。

## 保証規則

1. vendor payloadから共通`PreToolUse` / `Stop` / `SessionStart`へ正規化する。
2. `PreToolUse`は共通policy actionへ接続する。
3. `Stop`はS5 Completion Assuranceへ接続する。
4. vendorがnative `ask`を表現できない場合、deny/blockへ狭めてもallowへ広げない。
5. S5の`review_required`をStop成功へ変換しない。
6. vendor hostが供給するfollow-up markerをS5へ保持して渡す。
7. malformed / unknown / evaluator failureはfail-closed。
8. repository入力からtrusted evaluator実装を差替えない。

## Vendor契約の確認状態

2026-09-14時点の公開公式仕様で、Claude CodeとCodexは`Stop`入力の`stop_hook_active`を明示的に定義し、「Stop hookによって既に継続されたturnか」を表す。したがってこの2製品については、host supplied lifecycle stateをS5のfollow-up markerへ写像するcontractを根拠付きで評価できる。

Devinについては、現時点で公開公式ドキュメントから同等のhook input/output schemaを確認できていない。Go adapterにはPython referenceとの比較用mappingを保持するが、Devinのproduction vendor conformanceは本スライスの収束主張に含めない。実Devin CLI/versionでの契約確認とE2Eを追加適合条件とする。schema差がある場合はfail-closedを維持してadapterをEvolutionする。

## 具体化

- `internal/vendor/adapter.go`
- `internal/vendor/runtime.go`
- `internal/vendor/adapter_test.go`
- `internal/vendor/runtime_test.go`
- `internal/trustedexec/api.go`
- `internal/repository/completion.go`
- `internal/buildinfo/`
- `docs/implementation/go/vendor-integration-deployment.ja.md`

## Deployment assurance

Go production implementationではsource→toolchain→artifact→distribution→installed binaryのtrust chainを新たに明示する。

S6 reviewではコード内のpath checkだけをdeployment guaranteeとして過剰主張しない。build provenance、artifact integrity、signing、version、update、rollback、revocation、OS/architecture、credential containmentは外部強制機構との分担として記録する。

CIはLinux/macOSを独立に評価し、unit/race/vet/buildに加えてdistribution candidate、build identity、SHA-256 manifestをartifactとして保存する。片方のOSが失敗しても他方のEvidenceを失わないようmatrixのfail-fastを無効化する。

## Review finding

macOSではtemporary directoryの`/var/...`がcanonical pathとして`/private/var/...`へ解決される。trusted path実装は正規化済みpathを返していたが、初期testが非正規化pathとの文字列一致を要求して失敗した。実装の信頼境界を弱めず、test側をcanonical path比較へ修正した。このfindingをcross-platform trusted-path regressionとして保持する。

## 収束条件

- Claude/Codexの公開vendor contractとmappingが対応している。
- Claude/Codex/Devin compatibility mappingがunit testで固定されている。
- ask/denyがallowへ弱化されない。
- Stopのreview_required/blockedがcompletionへ変換されない。
- follow-up markerがcommon completion requestへ保持される。
- unknown/errorがfail-closed。
- Linux/macOSの独立したCI Evidenceが得られる。
- deployment trust-chainの未解決責務が明示されている。

以上をGo S6 coreの初回収束条件とする。Devin実製品契約、artifact signing/provenance、rollout/rollback/revocation、installed artifact verificationは実配備側の追加適合条件であり、本PRだけで保証済みとは主張しない。
