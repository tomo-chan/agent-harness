# S4 保証スライス — Control-plane Change Guard

## 主張

Agent Harness が自律公開を許可する場合でも、制御プレーンを変更する公開は通常の feature change と同一に扱わず、実際の publication diff に基づいて明示審査へ引き上げる。

## 前提

- S1: trusted runtime / policy enforcement が成立している。
- S2: repository identity / posture が fresh authority から `READY` と評価される。
- S3: publication target / branch / refspec / PR target が canonical autonomous publication として `allow` されている。

S4 は S3 を置き換えない。S3 が `ask` / `deny` の操作に S4 が追加権限を与えない。

## Authority

- repository identity: fresh S2 report
- default branch name: fresh S2 report
- default branch head SHA: checked GitHub repositoryからS4評価時に直接取得
- publication head: S2/S3 に束縛された current local HEAD
- publication diff: authoritative default branch head と publication head の Git diff

ローカル `origin/main` 等の remote-tracking ref は authority ではない。

## 保証規則

1. S3 結果が `allow` でなければ S4 は評価しない。
2. GitHub default branch head が取得できなければ deny。
3. authoritative base commit object がローカルで検証できなければ deny。
4. `base...HEAD` の changed path を確立できなければ deny。
5. protected control-plane path が1つ以上含まれれば ask。
6. protected path がなければ S3 allow を維持する。
7. unknown は allow に変換しない。

## 具体化

- `internal/controlplane/guard.go`
- `internal/trustedexec/run.go`
- `internal/controlplane/guard_test.go`
- `internal/trustedexec/run_test.go`
- `docs/implementation/go/control-plane-change-guard.ja.md`

## Evidence

S4 は Publication Evidence に、authority取得・base object・diff・protected path 判定の pass / fail / unknown を追加する。

重要なのは「protected path が見つからなかった」という結果ではなく、どの authoritative base とどの publication head の差分に対して判定したかを追跡可能にすることである。

## Failure modes

- GitHub response unavailable / malformed
- default branch head unknown
- local base commit unavailable
- diff execution failure
- protected path contract miss
- S3/S4間でHEADが変化するTOCTOU
- hook外のpublication path

前4件は現実装でfail-closed。protected path contractの完全性、TOCTOU完全排除、hook外経路は外部責任またはEvolution対象として明示する。

## 検証観点

- S4はS3より前に実行されない。
- S3 ask/denyをS4がallowへ変えない。
- local remote-tracking refに依存しない。
- GitHub authoritative base取得失敗をfail-openしない。
- actual diffからprotected pathを検出する。
- path表記差を正規化する。
- unknown Evidenceを保持する。
- runtime failureはnonzero exitとなる。

## 収束条件

次を満たしたため初回収束とする。

- 保証規則が実装とunit/runtime testへ追跡可能。
- Linux/macOS CIでGo test/buildが成功。
- S3→S4順序がruntime testで固定されている。
- Evidence取得不能はdeny + nonzero exit。
- 既知の対象外と外部責任が文書化されている。

本収束はAgent Harness全体、S5/S6、deployment、GitHub server-side authorizationの適合を意味しない。
