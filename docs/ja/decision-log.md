# 実装 Decision Log

[English](../decision-log.md) | [Vendor Harness 実装](06-vendor-harnesses.md) | [README](../../README.ja.md)

Harness の設計・実装に影響する判断を記録します。詳細レコードは [`docs/ja/decisions/`](decisions/) 配下に置きます。

## Status

- **Accepted** — 現在採用中
- **Temporary** — 現在の Vendor / Runtime 制約への暫定対応
- **Superseded** — 履歴として残すが現在は不採用
- **Vendor Update 時に再評価** — upstream 変更時に再検証

## DL-001 — Central Vendor-neutral Policy Engine

- Status: Accepted
- 判断: Vendor Hook Input を共通 Action Model に正規化し、1つの deny-first Policy Engine で評価する。

## DL-002 — Policy precedence は deny > ask > allow

- Status: Accepted
- 判断: 記述順に依存せず deny を最優先する。

## DL-003 — Policy 評価エラーは fail-closed

- Status: Accepted
- 判断: Invalid Policy / Malformed Input / Adapter Evaluation Error は Adapter Boundary で deny / block とする。Vendor Runtime 自体の Hook Failure は下位 Security Layer でも補完する。

## DL-004 — Codex `ask` は native enforcement まで deny

- Status: Temporary / Vendor Update 時に再評価
- 判断: Trusted External Approval がない中央 `ask` は Codex deny に変換する。
- Upgrade Path: Codex が必要な PreToolUse `ask` contract を安定して提供したら native `ask` へ切り替える。

## DL-005 — Claude Code は native PreToolUse `ask`

- Status: Accepted / Vendor Update 時に再評価
- 判断: 中央 allow / ask / deny を Claude Code の PreToolUse Decision へ対応付ける。

## DL-006 — Devin の中央 `ask` は fail-closed

- Status: Temporary / Vendor Update 時に再評価
- 判断: External Approval がない中央 `ask` は block。Devin Native Permissions は別 Layer とする。

## DL-007 — Active Worktree を動的解決

- Status: Superseded by DL-015
- 過去の判断: Absolute Checkout Path を埋め込まず `git rev-parse --show-toplevel` で Repository Root を解決する。
- Superseded 理由: Agent-mutable Worktree から Policy / Assurance Code を実行すると Trusted Harness Boundary に違反する。Production Hook Execution は `AGENT_HARNESS_TRUSTED_ROOT` から解決し、Repository / Worktree Discovery は Posture / SCM Validation の Runtime Input としてのみ扱う。

## DL-008 — Harness / Config は Security-sensitive

- Status: Accepted
- 判断: `.agent-harness/`、Vendor Hook Config、CI Workflow、Harness、Posture、Policy の変更は Approval-class とする。

## DL-009 — Stop Hook は Deterministic Completion Gate を利用

- Status: Accepted
- 判断: Stop Hook で deterministic check を実行し、Retry / Time / Tool / Cost Circuit Breaker は External Orchestrator にも持たせる。

## DL-010 — Hook は Defense in Depth、最終 Authority ではない

- Status: Accepted
- 判断: Protected Branch、Credential、Production、Host / Network Boundary は Sandbox、Workload Isolation、IAM / SCM、Server-side Rule でも独立して保護する。

## DL-011 — Sandbox-first Credential Exposure Reduction

詳細: [DL-011](decisions/DL-011-sandbox-first-credential-isolation.md)

- Status: Accepted / Vendor Update 時に再評価
- 判断: Sandbox / Local Policy で Credential Exposure を低減するが、Credential Compromise 自体は起こり得る Failure Mode とする。Default は **1 Pod / 1 Agent Container**。Credential を隠すだけのために SCM Broker / Sidecar は追加しない。
- Security Invariant: Credential Compromise が unrestricted Repository / Organization Authority を意味してはいけない。
- Containment: Short-lived / Repository-scoped Credential、Least-privilege GitHub App / IAM、Server-side Ruleset、Audit / Revoke。

## DL-012 — SessionStart で Repository Security Posture を検証

詳細: [DL-012](decisions/DL-012-sessionstart-repository-posture.md)

- Status: Accepted / Vendor Update 時に再評価
- 判断: SessionStart で Posture を検証して `READY` / `RESTRICTED` / `BLOCKED` を cache し、Remote SCM Mutation 前に stale なら再検証する。
- Trusted Identity: `AGENT_HARNESS_EXPECTED_REPOSITORY` は Trusted Launcher が設定する。未設定は `UNKNOWN`、不一致は `BLOCKED`。
- Minimum Posture: Repository-local `mode` は `AGENT_HARNESS_MINIMUM_POSTURE_MODE` を弱められない。Default minimum は `restricted`。
- Missing Config: built-in `restricted` default。
- Invalid Explicit Config: `BLOCKED`。
- External State Unknown: `UNKNOWN` を保持し、Effective Mode により block / restrict / warn を決定する。
- Enforcement: SessionStart は検出 / fail-fast、PreToolUse は実行制御、GitHub Ruleset / IAM は authoritative enforcement。

## DL-013 — Canonical SCM Publication Command

詳細: [DL-013](decisions/DL-013-canonical-scm-publication.md)

- Status: Accepted / Vendor Update 時に再評価
- 判断: Autonomous Git Publish は `git push` と `git push --set-upstream origin HEAD` の2形式だけを許可し、その後に Repository / Branch / Upstream を Semantic Validation する。
- Compound Shell: 先頭が read-only command でも `&&` / Pipe / Redirection 等を含む Command は Autonomous Allowlist 外。
- PR Creation: `gh pr create` で Repository / Head / Base の override を禁止する。
- 理由: Arbitrary Shell / Refspec を安全に解釈する複雑さを持ち込まず、必要な Publish Path だけを狭く定義する。

## DL-015 — Trusted Harness Boundary

詳細: [DL-015](decisions/DL-015-trusted-harness-boundary.md)

- Status: Accepted / Vendor・Runtime Update 時に再評価
- 判断: Production の Policy / Posture / SCM Semantic Validation / Completion Code は Agent-mutable Workspace の外に Provision された `AGENT_HARNESS_TRUSTED_ROOT` から実行する。
- Baseline: 承認済み Harness Snapshot を `/opt/agent-harness` に Bake し、Container の Read-only Root Filesystem 上に置く。`/workspace` は Mutable のまま維持する。
- Policy Source: Trusted Wrapper は Semantic Policy と Repository Posture Policy を Trusted Root 側へ固定し、Repository-controlled File を Production Normative Policy にしない。
- Hook Registration: Project-local Hook File は Reference / Development Wiring。Vendor が対応する場合、Production Registration は Trusted Launcher / Managed Configuration から Provision する。
- RAEM Invariant: 独立した Authority Boundary として使う Assurance / Policy Mechanism は、評価対象自身が変更できる Implementation に依存してはならない。

## Maintenance Rule

Architecture Alternative の選択、Vendor Limitation の Workaround、Trust Boundary / Failure Mode / Approval Path / Security Invariant の変更、将来 Upgrade で簡略化できる判断を行った場合は Decision Log を更新します。Temporary Decision には Upgrade Path / 再評価条件を残し、過去判断を黙って削除しません。
