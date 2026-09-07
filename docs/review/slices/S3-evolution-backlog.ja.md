# S3 — Evolutionバックログ

## EV-S3-001 — 任意protected refの権威モデル

### 分類

- 種別: モデル指摘
- 現サイクル阻害: **なし**
- 状態: 次サイクルのEvolution候補

### 指摘

現在のS2/S3は、確認済みGitHub repositoryのdefault branchとその保護状態を権威として扱い、S3はdefault branchへの自律pushを明示的に拒否する。

一方、GitHub上でdefault branch以外に設定される任意のprotected ref集合を取得し、自律push可否へ反映する一般的な権威モデルは持っていない。

### 停止判定

この指摘は現サイクルを停止させない。

理由は、現在のS3主張が「GitHub上のすべてのprotected refへのpushを禁止する」ことを保証範囲としておらず、現在のcanonical publication保証はdefault branch拒否、確認済みrepository/current branch/push destination/upstreamの整合、force push拒否によって成立するためである。

したがってこれは現在保証の不成立ではなく、保証範囲を拡張するモデル進化候補として扱う。

### 現在の対象外・残存リスク

- default branch以外の任意protected ref集合をS2の権威状態として取得・保持すること。
- 任意protected refへの自律pushをS3が包括的に拒否すること。

GitHub server-side Rulesets/branch protectionによる最終認可は引き続き外部責任である。

### 次サイクルで検討する進化

```text
GitHub repository rules
  ↓
権威的なprotected ref集合
  ↓
S2 repository authority
  ↓
S3 publication semantics
  ↓
自律push対象branchとの照合
```

この進化を採用する場合、S2の権威モデルとS3の保証契約を同時に再評価する。
