# DL-014 — Application Architecture を Deterministic Contract / Gate で Enforce する

- 日付: 2026-09-05
- Status: Accepted
- 対象: Agent Harness 上で動く Application

## Context

Harness は Execution / Security Architecture と再利用可能な Enforcement Primitive を定義します。その上で動く Application には、個別 Application 固有の Architecture / Product Invariant という別の Policy Domain があります。

Human / Agent Review は Principle 違反の発見には有効ですが、Machine-verifiable にできる Invariant の Merge / Release Authority を Non-deterministic Review に依存させるべきではありません。

## 判断

Application Layer を次の構成として明示します。

1. Application Design Principles
2. Versioned Architecture Contract
3. Deterministic Evidence Collectors
4. Deterministic Architecture Gate
5. Gate Result を使う CI / Release Wiring

同じ Repository State と Contract なら、Model、Prompt、Conversation History、Reviewer Confidence に依存せず同じ Gate Result を返す必要があります。

## Principle から Gate への昇格条件

文章としての Principle は、Deterministic Predicate と Reproducible Evidence が定義できた場合だけ Enforced Gate へ昇格します。まだ満たせない Principle は Advisory のまま扱います。

LLM / Human Review は Missing Principle 発見、Invariant 提案、Failure 説明、Waiver 提案には利用できますが、Authoritative な pass / fail を直接返しません。

## Control-plane Protection

Architecture Contract、Gate Implementation、Evidence Collector、CI Wiring、Waiver は Control-plane Artifact とします。Routine Source Edit と同じ Autonomous Path から無審査で弱体化できないよう、Harness Control と同じ Review / Approval Policy で保護します。

## Failure Semantics

Malformed Contract、Unsupported Check Type、Path Escape、Required Evidence Missing、Evaluator Failure、Expired Waiver は fail-closed とします。

Waiver は Check ID、Owner、Reason、Expiry を持つ Explicit Data とし、Architecture Gate 全体を恒久的に無効化する Broad Switch は設けません。

## 初期実装範囲

最初の Reference Gate は小さな Deterministic Vocabulary に限定します。

- Path Exists
- Path Absent
- File Contains Regex
- File Does Not Contain Regex

Universal Architecture Language を最初から作ることが目的ではありません。Concrete Invariant が必要になった時点で Evidence Type を追加し、可能なら Text Heuristic より Structured Evidence を優先します。

## Consequences

- Application Architecture を Executable / Regression-testable にできる
- Non-deterministic Reasoning の価値を維持しながら Authority Boundary から外せる
- Architecture Policy Change が明示的な Code Review Event になる
- CI Required Check として Merge 前に Enforce できる
- Control-plane Mechanism を共有しても Harness Layer と Application Layer の責務を分離できる

## 再評価条件

より汎用的な Policy Engine、Dependency Graph Framework、Schema Compatibility System、Signed Attestation Platform、Organization-level Architecture Service が、より少ない Custom Implementation で同じ Deterministic Contract を提供できる場合に再評価します。
