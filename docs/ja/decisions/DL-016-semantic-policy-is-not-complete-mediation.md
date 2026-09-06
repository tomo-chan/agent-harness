# DL-016 — Semantic Policy は Complete Mediation ではない

- Status: Accepted / Vendor・Runtime Update 時に再評価

## Context

Harness は `PreToolUse` などの Vendor Lifecycle / Tool Event を観測し、その境界で見える Action に対して Deterministic Semantic Policy を適用する。これは Agent が直接発行する `git push`、`gh pr create`、File Edit、明示的な Credential Extraction などには有効である。

一方、許可された Executable は Repository-controlled Code を内部で実行できる。例えば `pytest`、`npm test`、Compiler Build Script、Plugin、その他の許可済み Program が内部で `git`、`gh`、HTTP Client、別 Process を起動する可能性がある。Vendor Hook が通常観測するのは外側の Invocation であり、全 Secondary Process / Side Effect ではない。

したがって Semantic Hook を Complete Mediation とみなすと、その Mechanism が実際に確立できる保証範囲を超えてしまう。

## Decision

Semantic Policy Engine と SCM Semantic Validator が統治するのは、**Hook Boundary で観測可能な Agent-issued Action** とする。許可後に実行される Arbitrary Code の全 Secondary Effect に対する Authoritative Complete-mediation Boundary とはしない。

Critical External-system Invariant は、許可済み Process が Hook から見えない Secondary Action を行っても成立しなければならない。そのため、次の Lower-level Authority へ Refinement する。

- Least-privilege / Short-lived / Repository-scoped IAM・SCM Credential
- GitHub Rulesets / Branch Protection / Required Pull Request / Required Status Check
- Threat Model 上必要な場合の Network Destination Control
- Host / Local Resource Protection のための Workload / Sandbox Capability Boundary

Harness は引き続き明示的な Direct Misuse を deny し、通常の Autonomous Publication を Canonical Direct Command Shape に限定する。ただしそれは Accidental / Model-generated Misuse を減らす Control であり、Sandbox 内の Process が異なる SCM / Network Operation を一切試行できないことの Proof ではない。

## RAEM Interpretation

Abstract Claim を次のように分離する。

1. **Direct Semantic-action Claim** — Harness が許可する Agent-issued Direct SCM Publication は Canonical Publication Contract に従う。
2. **External Authority Invariant** — Local Semantic Policy が Bypass / Compromise されても、Unrestricted Repository / Organization Authority を得られず、Authoritative Server-side Policy が禁止する Mutation は成立しない。
3. **Principle** — Local Semantic Policy は明示的な Unsafe Behavior を減らすが、Complete Security Boundary と記述しない。

これにより、Assurance Mechanism が実際に観測する Evidence より強い Claim を主張しない。Local Hook は1番目の Claim の Evidence、IAM / GitHub-side Policy は2番目の Invariant の Independent Evidence / Enforcement を担う。

## Consequences

- `pytest` / `npm test` 等の Verification Command は Policy が許可する限り Autonomous に実行可能だが、その実行は Nested Side Effect がすべて Semantic Mediation されたことの証明にはならない。
- Documentation は Direct Agent-issued Publication と Arbitrary Nested Process Effect を区別する。
- Security Review では Repository-controlled Code が Allowed Process 内で実行される前提でも、Lower-level IAM / Server-side Control が十分か評価する。
- Concrete Threat Model が必要としない限り、Complete Mediation を疑似実現するためだけに Generic Process Interception、SCM Broker、Command Shim を導入しない。

## Revisit Trigger

Vendor / Runtime が、TCB を不必要に拡大せず Nested Process / Network Effect を Trusted / Structured に観測・強制できる Complete Mediation Boundary を提供した場合、または Deployment Threat Model が IAM / Server-side Policy より強い Containment を要求した場合に再評価する。
