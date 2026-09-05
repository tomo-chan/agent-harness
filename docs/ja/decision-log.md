# 実装 Decision Log

[English](../decision-log.md) | [Vendor Harness 実装](06-vendor-harnesses.md) | [Application Architecture](07-application-architecture.md) | [README](../../README.ja.md)

Harness と、その上で動く Application Layer の設計・実装判断を記録します。詳細レコードは [`docs/ja/decisions/`](decisions/) 配下に置きます。

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
- 判断: Invalid Policy / Malformed Input / Adapter Evaluation Error は Adapter Boundary で deny / block とする。

## DL-004 — Codex `ask` は native enforcement まで deny
- Status: Temporary / Vendor Update 時に再評価
- 判断: Trusted External Approval がない中央 `ask` は Codex deny に変換する。

## DL-005 — Claude Code は native PreToolUse `ask`
- Status: Accepted / Vendor Update 時に再評価
- 判断: 中央 allow / ask / deny を Claude Code の PreToolUse Decision へ対応付ける。

## DL-006 — Devin の中央 `ask` は fail-closed
- Status: Temporary / Vendor Update 時に再評価
- 判断: External Approval がない中央 `ask` は block。Devin Native Permissions は別 Layer とする。

## DL-007 — Active Worktree を動的解決
- Status: Accepted
- 判断: Absolute Checkout Path を埋め込まず `git rev-parse --show-toplevel` で Repository Root を解決する。

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
- 判断: Credential Compromise を想定し、1 Pod / 1 Agent Container、Least-privilege IAM / SCM、Server-side Ruleset で封じ込める。

## DL-012 — SessionStart で Repository Security Posture を検証
詳細: [DL-012](decisions/DL-012-sessionstart-repository-posture.md)
- Status: Accepted / Vendor Update 時に再評価
- 判断: SessionStart で `READY` / `RESTRICTED` / `BLOCKED` を cache し、Remote SCM Mutation 前に stale なら再検証する。
- Trusted Identity: `AGENT_HARNESS_EXPECTED_REPOSITORY` は Trusted Launcher が設定する。
- Minimum Posture: Repository-local `mode` は Trusted Minimum を弱められない。

## DL-013 — Canonical SCM Publication Command
詳細: [DL-013](decisions/DL-013-canonical-scm-publication.md)
- Status: Accepted / Vendor Update 時に再評価
- 判断: Autonomous Git Publish は `git push` と `git push --set-upstream origin HEAD` の2形式だけを許可し、Repository / Branch / Upstream を Semantic Validation する。

## DL-014 — Deterministic Application Architecture Contract / Gate
詳細: [DL-014](decisions/DL-014-application-architecture-contracts.md)
- Status: Accepted
- 判断: Harness Layer と Application Layer を分離し、Application Principle は Reproducible Evidence 上の Deterministic Predicate に落とせたものだけ Gate として Enforce する。
- Authority: LLM / Human Architecture Review は Policy 改善に利用するが、Authoritative な Gate pass / fail は返さない。
- Control Plane: Architecture Contract、Gate Implementation、Evidence Collector、CI Wiring、Waiver は保護対象。
- Waiver: Explicit / Scoped / Owned / Reasoned / Expiring とする。

## Maintenance Rule

Architecture Alternative の選択、Vendor Limitation の Workaround、Trust Boundary / Failure Mode / Approval Path / Security Invariant の変更、または Application Architecture を Enforced Policy に変換する方式を変更した場合は Decision Log を更新します。Temporary Decision には Upgrade Path / 再評価条件を残します。
