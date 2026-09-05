# 実装 Decision Log

[English](../decision-log.md) | [Vendor Harness 実装](06-vendor-harnesses.md) | [README](../../README.ja.md)

このログは Harness の設計・実装に影響する判断、特に**現時点の Vendor 制約に起因する暫定判断**を記録します。**Vendor Update 時に再評価**とした項目は、Claude Code / Codex / Devin CLI などの機能追加・仕様変更時に必ず見直します。

詳細な判断は [`docs/ja/decisions/`](decisions/) 配下に分離して記録できます。現在の詳細レコード: [DL-011 — Sandbox-first Credential Isolation](decisions/DL-011-sandbox-first-credential-isolation.md)。

## Status

- **Accepted** — 現在採用している設計判断
- **Temporary** — 現在の制約に対する暫定回避
- **Superseded** — 後続判断に置き換え済み。履歴として残す
- **Vendor Update 時に再評価** — upstream の機能・挙動変更時に再検証する

## DL-001 — 中央に Vendor-neutral Policy Engine を置く

- 日付: 2026-09-05
- Status: Accepted
- 対象: Claude Code / Codex / Devin CLI
- 判断: 各 Vendor の Hook Input を共通 Action Model に正規化し、1つの deny-first Policy Engine で評価する。Vendor 固有コードは入出力 Schema の変換に限定する。
- 理由: Security Policy は Vendor Hook Format ではなく組織側が所有するべきである。Adapter を薄くすることで semantic drift を抑え、共通 regression test を持てる。
- 影響: Vendor 固有機能のうち、組織共通の Security Semantic でないものは無理に抽象化しない。
- 再評価条件: Vendor が中央 Policy と直接統合できる、より強い汎用 Policy Abstraction を提供した場合。

## DL-002 — Policy precedence は deny > ask > allow

- 日付: 2026-09-05
- Status: Accepted
- 対象: Shared Policy Engine
- 判断: JSON 内の記述順に依存せず、deny → ask → allow の順で評価する。
- 理由: 広い allow rule が Security Invariant を誤って上書きすることを防ぐ。
- 影響: 例外は rule order ではなく狭い条件として表現する。
- 再評価条件: 同等以上の安全性を持つ明示的 Conflict Resolution Model に Policy Language を置き換える場合。

## DL-003 — Policy 評価エラーは fail-closed

- 日付: 2026-09-05
- Status: Accepted
- 対象: Shared Policy Engine / Vendor Adapter
- 判断: Invalid Policy、Malformed Input、Adapter 側 Policy Evaluation Error は Adapter Boundary で deny / block に変換する。
- 理由: Policy Infrastructure の障害によって権限が暗黙に拡大してはいけない。
- 制約: Vendor Runtime 自体が Hook Process Failure を fail-open と扱う場合、有効な deny response を返す前の障害までは防げない。そのため OS Sandbox、Pod Isolation、IAM、SCM Rules、Server-side Protection を最終境界とする。
- 再評価条件: Vendor が Hook Failure に対する enforceable な fail-closed mode を追加した場合。それを有効化し、本ログに記録する。

## DL-004 — Codex の `ask` は native support まで deny に変換

- 日付: 2026-09-05
- Status: Temporary / Vendor Update 時に再評価
- 対象: Codex PreToolUse Adapter
- 判断: 中央 Policy の `ask` は、Trusted Launcher が `AGENT_HARNESS_APPROVED_RULES` で対象 rule を allow に昇格していない限り、Codex の `permissionDecision: deny` に変換する。
- 理由: 現行 Codex は Schema 上 `permissionDecision: "ask"` を parse するが、PreToolUse の実行制御としては未サポートで、Unsupported Output により Hook Failure となり Tool Call が継続する可能性がある。したがって fail-closed を優先する。
- Upgrade Path: Codex が PreToolUse `ask` を native enforcement するようになったら、Adapter を native `ask` に変更し、Conformance Test を追加して暫定 mapping を削除する。
- 再検証: Codex Hook Schema、Runtime Behavior、upstream issue を変更時に再確認する。

## DL-005 — Claude Code は native PreToolUse `ask` を利用

- 日付: 2026-09-05
- Status: Accepted / Vendor Update 時に再評価
- 対象: Claude Code Adapter
- 判断: Claude Code の PreToolUse には native `permissionDecision` の `allow` / `ask` / `deny` を返す。
- 理由: 現行 Claude Code はこの Policy Model に適した semantic pre-tool permission decision を提供している。
- 影響: 中央 Policy の `ask` を hard denial に変換せず interactive approval にできる。
- 再評価条件: Hook Response Schema または Permission Semantics が変更された場合。

## DL-006 — Devin の中央 `ask` は block、native Permissions は分離

- 日付: 2026-09-05
- Status: Temporary / Vendor Update 時に再評価
- 対象: Devin CLI Adapter
- 判断: 中央 Policy の `ask` は External Approval 済みでない限り block として返す。Devin 自身の Static Permissions による native prompt は別レイヤーとして利用する。
- 理由: Vendor 間で Hook-level `ask` が同じ semantic を持つと仮定せず、中央 Policy を deterministic に保つため。
- Upgrade Path: Devin が Harness が必要とする semantic を持つ stable な Hook Approval Response を提供した場合、中央 `ask` をそれへ mapping し Conformance Test を追加する。

## DL-007 — Active Worktree を動的に解決する

- 日付: 2026-09-05
- Status: Accepted
- 対象: `.claude/settings.json` / `.codex/hooks.json` / `.devin/hooks.v1.json`
- 判断: Hook Command は absolute checkout path を埋め込まず、`git rev-parse --show-toplevel` で現在の repository root を解決する。
- 理由: 1つの Agent Session が control checkout から task-specific Git worktree へ移動する運用を前提としているため。
- 影響: Checkout location に依存せず、active worktree に commit された Harness Version を利用できる。
- 再評価条件: Vendor Runtime が保証された repository-root variable や first-class project hook executable path を提供し、Git 呼び出しより安全・確実になった場合。

## DL-008 — Harness / Config 自体を Security-sensitive と扱う

- 日付: 2026-09-05
- Status: Accepted
- 対象: Shared Policy
- 判断: Agent Config、CI Workflow、Harness Control File の変更を通常 source edit ではなく approval-class operation にする。
- 理由: Project-local Hook や Agent Instruction は effective control plane を変更でき、Supply-chain / Security Boundary の一部であるため。
- 影響: 通常 source edit の自律性を維持しながら、Policy / Control Plane 変更は強い review を要求できる。
- 再評価条件: 原則維持。Protected Path Set は将来拡張可能。

## DL-009 — Stop Hook は deterministic Completion Gate を利用

- 日付: 2026-09-05
- Status: Accepted
- 対象: 全 Vendor Adapter
- 判断: Stop Hook で `reference/scripts/completion_gate.sh` を実行し、Gate Failure は Completion を block する。
- 理由: Model が「完了」と発言することを authoritative evidence にしないため。
- 影響: Self-repair Loop の無限化を防ぐ retry / time / tool / cost circuit breaker は External Orchestrator にも必要。
- 再評価条件: Vendor Runtime が durable task-state / completion API を提供した場合。それを統合しても deterministic verification は残す。

## DL-010 — Hook は Defense in Depth であり最終 Security Boundary ではない

- 日付: 2026-09-05
- Status: Accepted
- 対象: 全体 Architecture
- 判断: Protected Branch、Production System、Credential、Host Resource、Network Boundary の防御を Hook Success のみに依存させない。
- 理由: Hook Failure Semantics と Coverage は Vendor / Version により異なる。Model / Hook Layer が失敗しても External Capability Boundary が有効である必要がある。
- 影響: Production Deployment では Sandbox、Container / Pod Hardening、Egress Control、Short-lived IAM / SCM Credential、Server-side Ruleset が引き続き必要。
- 再評価条件: Vendor Feature だけでこの原則を置き換える場合は、明示的 Threat Model Review を必須とする。

## DL-011 — Sandbox-first Credential Isolation

詳細レコード: [DL-011 — Sandbox-first Credential Isolation](decisions/DL-011-sandbox-first-credential-isolation.md)

- 日付: 2026-09-05
- Status: Accepted / Vendor Update 時に再評価
- 対象: Claude Code / Codex / Devin CLI / SCM 認証
- 判断: Native Sandbox Credential Masking / Mediation を第一選択とし、Vendor Sandbox が Credential Confidentiality と必要な `git` / `gh` capability を同時に満たせない場合だけ narrow SCM Broker を利用する。
- Security Invariant: Agent は GitHub capability を持ってよいが、再利用可能な GitHub credential を readable data として持ってはいけない。
- Upgrade Path: 十分に強い native credential masking または first-class authenticated SCM capability を追加した Vendor では Broker を削除する。

## Maintenance Rule

以下に該当する変更では Decision Log Entry を追加します。

1. 複数の Architecture Alternative から1つを選択した場合
2. 現在の Vendor Limitation / Bug を補う Workaround を導入した場合
3. Trust Boundary、Failure Mode、Approval Path、Security Invariant を変更した場合
4. Claude Code、Codex、Devin CLI、Kubernetes、SCM 等の将来 Upgrade で改善・廃止できる可能性がある実装判断を行った場合

Temporary Decision には必ず **Upgrade Path** または **再評価条件** を記録します。過去の判断は黙って削除せず、`Superseded` に変更して後続 Decision を参照させます。
