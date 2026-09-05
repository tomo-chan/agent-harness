# DL-013 — Canonical SCM Publication Command

- 日付: 2026-09-05
- Status: Accepted / Vendor Update 時に再評価
- 対象: Shell Policy / Git Publish / GitHub PR Creation

## 判断

Autonomous な Publish Path では、任意の Shell / Git Syntax を広い Regex Allowlist で許可せず、狭い Canonical Command だけを許可します。

Autonomous に許可する Push 形式は次の2つです。

```bash
git push
git push --set-upstream origin HEAD
```

さらに Semantic Validator で次を確認した場合だけ実行を許可します。

- Repository Posture が `READY`
- Current Branch が GitHub から取得した Default Branch ではない
- `origin` が SessionStart で確認した Repository と一致する
- 単純な `git push` の Upstream が `origin/<current-branch>`
- Arbitrary Remote / Refspec / Tag / Delete / Force / `-c` Config Override / Destination Branch を指定していない

`gh pr create` では Repository / Head Branch / Base Branch の Override を禁止します。これらは Agent が自由に指定するのではなく、確認済み Repository と Current Git State から決定します。

`&&`, `||`, `;`, Pipe, Redirection, Newline, Command Substitution などの Compound Shell Syntax は Autonomous Allowlist の対象外とし、Approval / Deny 側へフォールバックします。

## 理由

`^git status` のような Prefix Regex では、例えば次の Command を Read-only と誤判定できます。

```bash
git status && git push origin feature/x
```

これは `RESTRICTED` Session が Remote SCM Authority Boundary を越えてはならないという Invariant に違反します。Arbitrary Shell を安全に Parse することは Harness の目的に対して過剰な複雑さを持つため、Autonomous Publish Path 自体を狭くします。

## 責務分離

- Policy Engine: Narrow Command Shape だけを Autonomous と分類
- SCM Semantic Validator: Repository / Branch / Upstream / Override を検証
- Repository Posture: Trusted Repository / Default Branch Context を供給し、Publish 時は `READY` 必須
- GitHub IAM / App Permission: Credential Compromise の Blast Radius を制限
- GitHub Ruleset / Branch Protection: Server-side の最終 Enforcement Boundary

## Trusted Repository Identity

`AGENT_HARNESS_EXPECTED_REPOSITORY` は Trusted Launcher / Orchestrator が設定し、Authoritative とします。Repository-local `.agent-harness/security.json` は追加要件を定義できますが、Trusted Task Identity 自体を確立・上書きする役割は持ちません。

また `AGENT_HARNESS_MINIMUM_POSTURE_MODE` も Launcher 側が所有します。Default は `restricted` とし、Repository-local の `mode: warn` だけで unattended execution を弱められないようにします。Interactive 用に弱める場合だけ Trusted Launcher が明示的に変更します。

## 再評価条件

Vendor が Structured argv / Tool Semantics を公開し Shell String Parsing が不要になった場合、または Repository / Ref Constraint を直接表現できる First-class SCM Publish Tool を提供した場合に再評価します。Shell Parser を複雑化するより、より強い Structured Primitive へ置き換えることを優先します。
