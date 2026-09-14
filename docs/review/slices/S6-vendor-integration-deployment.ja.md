# S6 保証スライス — Vendor Integration / Deployment

## 主張

Vendor adapterはClaude Code / Codex / Devinのlifecycle eventを共通Agent Harness contractへ写像し、S1〜S5のdecision / completion semanticsを弱化しない。

## 保証規則

1. vendor payloadから共通`PreToolUse` / `Stop` / `SessionStart`へ正規化する。
2. `PreToolUse`は共通policy actionへ接続する。
3. `Stop`はS5 Completion Assuranceへ接続する。
4. vendorがnative `ask`を表現できない場合、deny/blockへ狭めてもallowへ広げない。
5. S5の`review_required`をStop成功へ変換しない。
6. follow-up markerをS5へ保持して渡す。
7. malformed / unknown / evaluator failureはfail-closed。
8. repository入力からtrusted evaluator実装を差替えない。

## 具体化

- `internal/vendor/adapter.go`
- `internal/vendor/runtime.go`
- `internal/vendor/adapter_test.go`
- `internal/vendor/runtime_test.go`
- `docs/implementation/go/vendor-integration-deployment.ja.md`

## Deployment assurance

Go production implementationではsource→toolchain→artifact→distribution→installed binaryのtrust chainを新たに明示する。

S6 reviewではコード内のpath checkだけをdeployment guaranteeとして過剰主張しない。build provenance、artifact integrity、signing、version、update、rollback、revocation、OS/architecture、credential containmentは外部強制機構との分担として記録する。

## 収束条件

- Claude/Codex/Devinのdecision mappingがunit testで固定されている。
- ask/denyがallowへ弱化されない。
- Stopのreview_required/blockedがcompletionへ変換されない。
- follow-up markerがcommon completion requestへ保持される。
- unknown/errorがfail-closed。
- deployment trust-chainの未解決責務が明示されている。

以上をGo S6 mapping coreの初回収束点とする。実配備環境でartifact signing/provenance/rollout/revocationを確立することはdeployment側の追加適合条件である。