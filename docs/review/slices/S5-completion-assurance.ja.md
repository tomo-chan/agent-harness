# S5 保証スライス — 完了保証

## 主張

決定的なリポジトリ / 配送条件を満たしたことと、タスク要求が意味的に完了したことを混同しない。S5 は前者を根拠としてエージェントへ返し、後者の非決定的評価をエージェントに残す。

## 前提

- 信頼された実行環境がリポジトリ変更権限を都度取得できる。
- Git / GitHub の観測機構が信頼された実行境界から供給される。
- リポジトリ固有の決定的ゲートが別途、信頼された形で構成される。

## 保証規則

1. SessionStart のスナップショットを完了判定の権威ある情報にしない。
2. 停止時に都度取得したリポジトリ報告と現在のブランチ / HEAD を再照合する。
3. 配送差分なしの短絡判定は、清浄な READY 状態の既定ブランチで、GitHub の権威ある HEAD と一致する場合だけ成立する。
4. それ以外は決定的ゲートを実行する。
5. 決定的検査の失敗は停止とする。
6. 決定的検査が成功した最初の停止ではレビュー要求を返す。
7. 後続の停止でも決定的保証を再実行し、成功時だけ完了とする。
8. 意味上の完了を決定的条件へ還元しない。

## 具体化

- `internal/completion/completion.go`
- `internal/completion/completion_test.go`
- `docs/implementation/go/completion-assurance.ja.md`

## 根拠

repository、branch、local HEAD、default branch、GitHub default HEAD、no-delivery-delta、各checkのpass/fail/unknownを保持する。

## 収束条件

- no-delivery-deltaがsemantic completionとして扱われない。
- initial / follow-up Stopの意味論が分離されている。
- follow-upでもdeterministic recheckを省略しない。
- authority/head/gate failureはfail closed。
- vendor-specific mappingはS6へ分離されている。

上記をunit testで固定した状態をGo S5 coreの初回収束点とする。
