# セキュリティモデル

## 脅威モデル

エージェントが以下に遭遇する前提で設計します。

- source code、issue、Web page、documentation、tool output に埋め込まれた悪意ある指示
- hallucination や破壊的 command
- dependency install script や compromised package
- credential の誤露出
- malicious / over-privileged MCP tool
- repository / worktree / branch の誤選択
- runaway retry loop
- compromised hook / policy code
- cloud metadata や internal control-plane endpoint へのアクセス試行

## Defense in Depth

```text
Model behavior
   |
   v
Semantic policy/hooks       文脈依存の危険を検出
   |
   v
Permissions/rules           通常操作の authority を制限
   |
   v
OS sandbox                  filesystem/network capability を制限
   |
   v
Pod/container isolation     host/peer workload を保護
   |
   v
Network enforcement         destination/protocol を制限
   |
   v
IAM/SCM authorization       external authority を制限
   |
   v
Server-side protections     critical resource を最終防御
```

単一レイヤーで全 failure mode を防ぐことは想定しません。

## Trusted Computing Base

TCB は小さく保ちます。少なくとも Orchestrator、Policy Engine、Sandbox Implementation、Workload Isolation、Credential Broker、External Authorization System が含まれます。Agent-generated code と model reasoning は trusted component ではありません。

## Credential

Workload Identity と short-lived credential を優先します。広範な personal credential を agent home directory に mount しません。可能であれば、通常の filesystem read から credential を分離し、必要な process / proxy にだけ渡します。

Repository credential は対象 repository と必要操作だけに scope します。Production credential は通常、coding-agent Pod に存在させるべきではありません。

## Network

Agent Runtime の外側にある network control を hard boundary とします。

```text
Agent Pod -> NetworkPolicy -> controlled egress proxy/gateway -> allowlisted services
```

Cloud metadata endpoint、cluster administration endpoint、無関係な internal network は遮断します。Agent 内蔵の domain filtering は defense in depth として利用し、唯一の network boundary にはしません。

## MCP / External Tool

MCP は Agent の authority を拡張するため、Threat Model に含めます。次の組み合わせを推奨します。

1. MCP tool permission / rule
2. semantic PreToolUse policy
3. MCP server authentication / authorization
4. least-privilege service account / IAM
5. audit logging

Production data へのアクセスには read-only service account を優先します。Generic administrative MCP tool を autonomous session に公開することは避けます。

## Git / SCM

`status`、`diff`、`log`、feature branch の commit / push、PR creation などの通常操作は許可しやすくします。一方、force push、protected branch mutation、tag/release creation、workflow modification、merge などは deny または approval 対象にします。

最終的な権威は SCM server-side rules です。Agent credential が ruleset や branch protection を bypass できてはいけません。

## Hook Failure Semantics

Hook は semantic policy に有効ですが、failure behavior は製品や version によって異なります。Hook timeout / crash / malformed output 後に execution が継続する可能性がある場合、その Hook は fail-open として扱います。Hard invariant は Hook 不在でも有効な Sandbox、IAM、Server-side Control で守ります。

## Audit

最低限、以下を記録します。

- task/session/turn identifiers
- model/runtime/version
- policy version
- tool/action と normalized target
- allow/deny/ask decision と reason
- approval actor/scope/expiry
- execution outcome
- commit/PR/CI identifiers
- sandbox/network denial

Raw secret はログに記録しません。OTel や集中分析基盤に流せる structured event を推奨します。
