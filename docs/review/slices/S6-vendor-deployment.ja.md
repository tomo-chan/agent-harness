# S6 — ベンダー接続と配備具体化

## 状態

**実装適合の再確認中。** S5で、決定的完了保証の成功をEvidenceとしてAgentへ返し、非決定的な完了評価を一度挟むStopループを導入した。S6ではClaude Code、Codex、Devin CLIの各adapterがこの契約を弱化せず接続できることを確認する。

## 主張

1. Claude Code、Codex、Devin CLIのライフサイクルイベントを共通ハーネスへ接続する。
2. ベンダー固有入力を共通モデルへ正規化し、同じ保証ロジックを利用する。
3. S5が返す決定的Evidenceと非決定的完了評価のループを、vendor adapterが独自判断で省略・弱化しない。
4. 本番参照配備で作業領域と信頼済みハーネス領域を分離し、workloadを非特権・最小権限で隔離する。
5. 認証情報侵害やworker compromiseを起こり得る障害として扱い、Sandbox、workload/container isolation、外部network enforcement、短寿命・リポジトリ限定・最小権限IAM、GitHub側規則へ責任を分担する。

## 境界

- 前提: 接続対象となるS1〜S5の保証機構。
- S6内部責任:
  - vendor lifecycle eventをtrusted launcher経由で共通保証へ接続する。
  - Stop payloadを共通S5へ渡し、`stop_hook_active` 等のS5が必要とする継続情報を失わない。
  - S5が `False` とEvidence/理由を返した場合はStopをblockし、その内容をAgentへ戻す。
  - S5がfollow-up Stopで `True` を返した場合だけ完了を許可する。
  - `/workspace` と `/opt/agent-harness` を分離する参照配備を示す。
  - containerをnon-root、no privilege escalation、drop ALL capabilities、read-only root filesystemで実行する参照条件を示す。
- 外部責任:
  - **Agent実行系**: S5から返されたEvidenceを踏まえ、タスク要求、Plan、実行結果、未解決事項、新しい発見・洞察を非決定的に評価する。
  - **Sandbox**: agent processからのfilesystem/process/credential exposure縮小。
  - **workload/container isolation**: host、peer workload、container runtime等への越境を防ぐ配備基盤責任。
  - **network enforcement**: metadata service、内部control plane、不要な外部宛先への通信をPod外の独立したNetworkPolicy/egress firewall/proxy等で制約する責任。
  - **IAM/credential issuance**: short-lived、repository-scoped、least-privilege credentialとworkload identity。
  - **SCM server-side rules**: GitHub Rulesets/branch protection等の最終認可。
- 対象外:
  - 各vendor製品、Sandbox、container runtime、network enforcement、IAM、GitHub Rulesetsの内部実装完全性。
  - S6のrepository内hookだけで、credential compromise後の全経路を完全仲介すること。
  - 非決定的な完了評価の内容をS6で決定的な分類へ還元すること。

## 保証契約

### Vendor接続

- vendor名はtrusted launcherが固定されたtrusted adapter pathへ写像する。
- repository入力から任意adapter pathを選択させない。
- PreToolUseはS1〜S4、StopはS5の保証経路へ接続する。
- vendor固有のapproval表現差はadapter出力変換に閉じ込め、権威状態を弱化しない。
- Stop payloadは共通runtimeへそのまま渡し、S5のfollow-up識別情報を欠落させない。
- 最初の決定的保証成功でS5がAgent reviewを要求した場合、adapterは成功扱いに変換せずblockとしてAgentへ返す。
- follow-up StopではS5が決定的保証を再確認する。adapterはS5の結果だけをvendor固有Stop responseへ写像する。

### S5 Stopループ

```text
vendor Stop
   ↓
共通S5
   ↓
決定的保証
   ├─ 失敗 → block
   └─ 成功
        ↓
   初回Stop？
   ├─ Yes → Evidenceを返してblock
   │          ↓
   │       Agentの非決定的完了評価
   │          ↓
   │       継続 / 確認 / 再Stop
   │
   └─ No (`stop_hook_active`)
          ↓
      決定的保証を再確認
          ↓
        完了可
```

S6はAgentの非決定的判断内容を評価しない。S6の責任は、S5が作る決定的EvidenceとvendorのAgent継続ループを失わず接続することである。

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

### S5 follow-up Stop情報の保持

S5の最新契約では、最初の決定的保証成功後にAgentへEvidenceを返し、非決定的な完了評価を一度要求する。follow-up Stopの識別にはvendor payloadの `stop_hook_active` を用いる。S6 adapterがこのfieldを削除・再構築すると、S5は初回とfollow-upを区別できずループする。

そのため3 vendorすべてについて、Stop payloadを共通S5へそのまま渡し、`stop_hook_active` を保持することをテストで固定した。

## レビュー網羅性

- [x] 権威レビュー — vendor adapterは保証権威ではなく接続層。SCM最終権威はserver-side rules。
- [x] 信頼境界レビュー — workspace/trusted root、repository/vendor adapter pathを分離。
- [x] 根拠完全性レビュー — hook、launcher、S5 Evidence loop、Pod security context、Sandbox/IAM/network/SCM責任を区別。
- [x] 失敗形態レビュー — Stop continuation情報欠落、credential leak、worker compromise、host/peer/metadata到達を明示。
- [x] 迂回レビュー — 任意adapter差替えやproject-local hookを独立権威としない。
- [x] 責任分担レビュー — 非決定的完了評価はAgent、決定的保証はS5、vendor接続はS6、外部防御はSandbox/workload/network/IAM/SCM。
- [x] 保証欠落レビュー — workload/network containmentとS5 follow-up接続を補完。
- [ ] 実装適合レビュー — CIおよびvendor hook実装の最終確認待ち。

## 収束判定

S6は**実装適合の再確認待ち**。S5のMF-S5-001はtask-intent分類を追加する方向ではなく、決定的EvidenceとAgentの非決定的完了評価を接続する形へ進化した。S6は最新S5実装を同期し、Claude Code、Codex、Devin CLIの各adapterでfollow-up Stop情報を保持するテストを追加した。CIとreview結果を確認後に最終収束を判定する。
