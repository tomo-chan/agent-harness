# S5 保証スライス — Completion Assurance

## 主張

決定的なrepository/delivery条件を満たしたことと、タスク要求が意味的に完了したことを混同しない。S5は前者をEvidenceとしてAgentへ返し、後者の非決定的評価をAgentに残す。

## 前提

- trusted runtimeがfresh Repository Authorityを取得できる。
- Git/GitHub observation providerがtrusted execution boundaryから供給される。
- repository-specific deterministic gateは別途trustedに構成される。

## 保証規則

1. SessionStart snapshotをcompletion authorityにしない。
2. Stop時のfresh repository reportとcurrent branch/HEADを再照合する。
3. no-delivery-delta shortcutはclean READY default branchかつGitHub authoritative HEAD一致時のみ成立する。
4. それ以外はdeterministic gateを実行する。
5. deterministic failureはblocked。
6. deterministic successの初回Stopはreview_required。
7. follow-up Stopでもdeterministic assuranceを再実行し、成功時だけcomplete。
8. semantic completionをdeterministic条件へ還元しない。

## 具体化

- `internal/completion/completion.go`
- `internal/completion/completion_test.go`
- `docs/implementation/go/completion-assurance.ja.md`

## Evidence

repository、branch、local HEAD、default branch、GitHub default HEAD、no-delivery-delta、各checkのpass/fail/unknownを保持する。

## 収束条件

- no-delivery-deltaがsemantic completionとして扱われない。
- initial / follow-up Stopの意味論が分離されている。
- follow-upでもdeterministic recheckを省略しない。
- authority/head/gate failureはfail closed。
- vendor-specific mappingはS6へ分離されている。

上記をunit testで固定した状態をGo S5 coreの初回収束点とする。
