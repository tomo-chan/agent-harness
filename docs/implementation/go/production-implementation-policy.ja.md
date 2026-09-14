# Production Implementation Policy — Go only

## 決定

Agent Harness の production implementation は Go のみとする。

Python 実装は廃止し、今後の適合対象、回帰対象、互換対象、differential comparison 対象には含めない。

## 保証の基準

今後の収束判定は、次の関係だけを対象とする。

```text
Tool Specification / Guarantee Contract
  ↓ refinement
Go production implementation
  ↓ evidence
Deterministic Conformance Assurance
  ↓ findings
Evolution
```

Pythonとの実装差、decision一致、byte互換、test vector一致は完了条件にしない。

## Pythonから引き継ぐもの

Python実装そのものは保持しないが、過去の具体化・レビューで得られた一般化可能なfindingは知識として保持してよい。

例:

- writable stateをauthorityとして扱わない
- local remote-tracking refをGitHub authorityの代替にしない
- compound shell commandをread-only/publishableと誤分類しない
- implicit Git/GitHub configurationによるpublication target変更を考慮する
- interpreter/import/environment依存はtrusted runtimeのfailure modeになり得る
- deterministic completion stateだけでsemantic task completionを確定しない

これらはPython互換性のためではなく、Guarantee Contract、Go tests、Evidence、設計判断へ一般化された知識として残す。

## 削除対象

- Python production/reference implementation
- Python専用unit/integration tests
- Python↔Go differential regression
- Pythonを将来のreference implementationとして維持する記述
- Python実装との機能同等性を完了条件とする記述

## 維持対象

- Go production implementation
- 実装非依存のTool Specification / glossary
- Assurance Slice review documents
- Go implementation notes
- Python由来であっても一般化済みのfinding / decision history
- shell/JSON/Kubernetes等、言語実装ではないdeployment/reference資材

## Evolution

今後のfindingは、Go implementationと仕様・Guarantee Contract・Evidenceの不整合として扱う。

実装で仕様不足を発見した場合は、単純にGoを既存仕様へ合わせるのではなく、次を判定する。

1. specification deficiency
2. implementation error
3. new requirement
4. external assurance responsibility

必要ならモデルをEvolutionし、その後Go implementationとdeterministic assuranceを更新する。

## 旧Python PR

旧Python実装PRはmergeせずcloseする。履歴はGit/GitHub上のhistorical evidenceとして参照可能だが、active implementation lineには含めない。
