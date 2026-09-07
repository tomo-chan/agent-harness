# S6 — ベンダー接続と配備具体化

## 状態

実装・配備具体化と再レビュー中。Codex Reviewで、認証情報侵害・worker compromise時の外部責任境界にworkload isolationとnetwork enforcementが明示されていない保証欠落を発見したため、責任分担を拡張した。

## 主張

1. Claude Code、Codex、Devin CLIのライフサイクルイベントを共通ハーネスへ接続する。
2. ベンダー固有入力を共通モデルへ正規化し、同じ保証ロジックを利用する。
3. 本番参照配備で作業領域と信頼済みハーネス領域を分離し、workloadを非特権・最小権限で隔離する。
4. 認証情報侵害やworker compromiseを起こり得る障害として扱い、単一機構に完全性を要求せず、Sandbox、workload/container isolation、外部network enforcement、短寿命・リポジトリ限定・最小権限IAM、GitHub側規則へ責任を分担する。

## 境界

- 前提: 接続対象となるS1〜S5の保証機構。
- S6内部責任:
  - vendor lifecycle eventをtrusted launcher経由で共通保証へ接続する。
  - `/workspace` と `/opt/agent-harness` を分離する参照配備を示す。
  - containerをnon-root、no privilege escalation、drop ALL capabilities、read-only root filesystemで実行する参照条件を示す。
- 外部責任:
  - **Sandbox**: agent processからのfilesystem/process/credential exposure縮小。
  - **workload/container isolation**: host、peer workload、container runtime等への越境を防ぐ配備基盤責任。
  - **network enforcement**: metadata service、内部control plane、不要な外部宛先への通信をPod外の独立したNetworkPolicy/egress firewall/proxy等で制約する責任。
  - **IAM/credential issuance**: short-lived、repository-scoped、least-privilege credentialとworkload identity。
  - **SCM server-side rules**: GitHub Rulesets/branch protection等の最終認可。
- 対象外:
  - 各vendor製品、Sandbox、container runtime、network enforcement、IAM、GitHub Rulesetsの内部実装完全性。
  - S6のrepository内hookだけで、credential compromise後の全経路を完全仲介すること。

## 保証契約

### Vendor接続

- vendor名はtrusted launcherが固定されたtrusted adapter pathへ写像する。
- repository入力から任意adapter pathを選択させない。
- PreToolUseはS1〜S4、StopはS5の保証経路へ接続する。
- vendor固有のapproval表現差はadapter出力変換に閉じ込め、権威状態を弱化しない。

### 配備

- workspaceはmutable、trusted harness rootはworkspaceとは別のread-only領域に置く。
- containerはnon-root、privilege escalation禁止、capabilities drop、read-only root filesystemを基準とする。
- hostPathやcontainer-runtime socketを参照構成へ持ち込まない。
- ServiceAccount tokenは不要ならautomountしない。
- network containmentはapplication hookのallow/denyだけに依存せず、Pod/host外で独立して強制する。
- productionではimageをdigest pinし、trusted harness snapshotをimage/trusted artifactとして配備する。

### Credential compromise containment

認証情報秘匿を唯一のsecurity invariantにしない。credentialが漏洩した場合でも、次の独立層でblast radiusを限定する。

```text
Sandbox / credential exposure reduction
        ↓
workload・container isolation
        ↓
external network enforcement
        ↓
short-lived / repo-scoped / least-privilege IAM
        ↓
GitHub server-side rules
```

## レビュー指摘

### workload/network責任の欠落

初期S6は外部責任をSandbox、IAM、SCM rulesだけで記述していた。しかしworkerまたはcredentialが侵害された場合、host/peer workloadやmetadata/internal control planeへの到達性は別の独立した失敗形態である。

これは単なるKubernetes YAMLの設定追加ではなく、S6が主張するdefense-in-depthの**責任境界の欠落**だったため、保証指摘として外部責任モデルへ追加した。

## レビュー網羅性

- [x] 権威レビュー — vendor adapterは保証権威ではなく接続層。SCM最終権威はserver-side rules。
- [x] 信頼境界レビュー — workspace/trusted root、repository/vendor adapter pathを分離。
- [x] 根拠完全性レビュー — hook、launcher、Pod security context、Sandbox/IAM/network/SCM責任を区別。
- [x] 失敗形態レビュー — credential leak、worker compromise、host/peer/metadata到達を明示。
- [x] 迂回レビュー — 任意adapter差替えやproject-local hookを独立権威としない。
- [x] 責任分担レビュー — Sandbox/workload/network/IAM/SCMの各責任を明示。
- [x] 保証欠落レビュー — workload/network containment欠落を補完。
- [ ] 実装適合レビュー — S5の未収束モデル指摘とstack再同期後に最終確認する。

## 収束判定

S6単体の外部責任境界は再定義したが、前提S5がMF-S5-001により未収束のため、S6も最終収束とはしない。S5のtask-intent保証が確定し、vendor Stop接続がその更新後契約へ適合することを再確認してから収束判定する。
