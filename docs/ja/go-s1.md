[English](../go-s1.md)

# Go S1 — 信頼済み実行と方針

Issue #14のS1保証契約をGoで独立に具体化した。調査対象はPR #6の
`97bb264`にあるlauncher・policy engine・adapter・テスト・
`docs/review/slices/S1-trusted-execution-policy.ja.md`。
そのブランチのマージには依存せず、既存Python版は変更しない。

## 起動と信頼境界

```sh
go test ./...
go build
# 信頼済み配備主体が同じディレクトリへバイナリとpolicy.jsonを配置する。
# 初期方針にはreference/policies/policy.example.jsonをコピーできる。
AGENT_HARNESS_TRUSTED_ROOT=/opt/agent-harness /opt/agent-harness/agent-harness <<'JSON'
{"tool_name":"exec","tool_input":{"command":"git status"}}
JSON
```

引数・subcommand・外部依存モジュールはない。ルートにmainを置くことで
`go build`だけで単一実行ファイルを生成する。

信頼済み配備主体は、バイナリ・方針・配置ディレクトリ・全祖先・hookの
起動設定と環境変数を、エージェントや評価対象リポジトリから変更できないよう
権限やread-only mount等で保護しなければならない。
書込み可能なcheckoutにバイナリを置くだけでは信頼境界は成立しない。
別のバイナリとrootを選べる主体、起動環境や信頼済み配置を変更できる主体は
この保証の対象外である。

必須の絶対パス`AGENT_HARNESS_TRUSTED_ROOT`を正規化し、実際の実行ファイルの
正規化済み親ディレクトリと一致することを確認する。方針はその直下の
`policy.json`だけであり、symlink解決後もroot内の通常ファイルでなければ拒否する。
root内のsymlinkは許容する。欠落、ディレクトリ、境界外symlinkは拒否する。
検査からopenまでの置換競合を防ぐのは配置の不変性であり、このパス検査自体は
OS sandboxでも所有者・mountの証明機構でもない。

adapterはコンパイル時に固定する。非空の`AGENT_HARNESS_TRUSTED_ADAPTER`と
`AGENT_HARNESS_TRUSTED_POLICY`は拒否する。`AGENT_HARNESS_POLICY`、`AGENT_POLICY`、
Python関連変数、cwd、リポジトリ内方針からのフォールバックは利用しない。

## 入出力・方針・失敗時の契約

- 入力はUTF-8の単一JSON object。`tool`/`input`または`tool_name`/`tool_input`を
  受け付ける。別名の混在は許容するが同一項目の両方指定は拒否する。
  toolは空白だけではない文字列、inputはobject。commandは文字列または文字列配列
  （Pythonと同様に空白で連結）。exec/Bashにはcommandが必須。他のtoolは省略可能。
  context/session/turn/prompt/cwd/event情報は受理するが方針権威に使わない。
  未知の最上位キーは拒否し、tool固有inputの追加フィールドは解釈しない。
- 方針は`default`（省略時ask）と`deny`/`ask`/`allow`配列。判断はこの3種類だけ。
  ルールは文字列の`id`/`reason`/`tool_regex`/`command_regex`/`action_regex`のみ。
  全正規表現を事前検証する。省略した条件は無条件、空の正規表現は常に一致。
  条件はANDで、action_regexの対象はtool・改行・commandの連結。
- 配列の記述順にかかわらずdeny > ask > allow。同一判断内は最初の一致を採用。
- 出力は`decision`/`reason`/`rule`（ID省略時null）のJSON。正常な判断はdeny/askも
  exit 0。パス・設定・方針・入力エラーはdenyと安定したエラー分類を返しexit 2。
  生の入力・パス・正規表現をエラー出力に含めない。出力失敗もexit 2。
  コマンドを実行する機能はない。
- 呼出側は非ゼロ終了、出力欠落・不正、クラッシュ、timeoutを拒否として扱い、
  askは外部承認へ送る必要がある。ベンダーの動作を本実装だけでは強制できない。
  stdinのEOF待ちの期限、プロセス全体の資源上限は呼出側の責任。
- 入力と方針は各1 MiBまでで、JSON深さも制限する。重複キー・後続JSON・不正JSON・
  不正UTF-8・型不整合を拒否する。正規表現はGoのRE2構文を使い、Python `re`専用の
  構文はfail closed。正規表現による分類はshell/SCM安全性の証明ではない。

## 根拠と比較

| S1主張 / Python根拠 | Goの根拠 |
|---|---|
| root必須・配置一致・境界外方針拒否 / launcher tests | TestTrustedPaths、TestSingleBinary |
| 方針必須・repository fallback禁止 / adapter test | 方針欠落、異なるcwd、旧環境変数のsubprocess tests |
| deny優先 / test_deny_precedes_ask_and_allow | TestPriorityAndPredicates（ask > allowも検証） |
| 不正default拒否 / test_invalid_policy_fails_validation | TestInvalidPolicies（型・正規表現・JSONも検証） |
| Git読取り・force push・main push・merge・未知command | TestPythonS1Vectors、同じcommandと変更していないsample policy |
| 入力解釈失敗はdeny | TestHookParsing、不正・過大入力のsubprocess tests |
| 任意adapter/policyへの差替え防止 | パス・override tests、adapterの静的リンク |
| cwd/import依存の除去 | 実バイナリを無関係なcwd、存在しないPATH、不正Python変数で起動 |

対応する保証vectorの比較であり、Pythonとの逐語的・byte単位互換ではない。
Goは型、重複キー、別名の曖昧性、未知キー、パス指定をより厳格に扱う。
既存mainのPython testsは`python3 -m pytest reference/hooks/tests -q`で検証できる。

| 観点 | Python S1 (`97bb264`) | Go S1 |
|---|---|---|
| 保証範囲 | root/adapter/policy包含、deny優先 | 同じS1主張、adapterと方針位置を固定 |
| 実装量 | runtimeの3ファイル、約270行 | mainとinternal 2 package、厳格JSON処理を追加。行数削減ではない |
| runtime依存 | Python、import、複数ソース、exec引継ぎ | 単一native executableと方針データ |
| deployment | interpreterと信頼済みソースツリー | OS/architecture別build、信頼済み配備によるbinary/policy更新 |
| failure modes | interpreter/import/path/引継ぎの失敗 | architecture違い、古いbinary、toolchain/build由来、RE2非互換。配置改変リスクは共通 |
| testability | unit testsとlauncher subprocess tests | go test、実バイナリsubprocess、Linux/macOS CI |
| debugging/operability | source編集とinterpreter診断 | rebuildが必要、安定したJSONエラー分類、信頼済み方針で再現。binaryの更新管理が必要 |

実行時の信頼境界は、interpreter選択、PYTHONPATH、import、adapter差替えを除いた分
単純になった。ただし厳格なdecodeと攻撃的入力のテストを追加したため、実装行数が
減ったとはいえない。信頼済み配布・host侵害・呼出側の失敗処理は別途必要である。
Goはproduction候補として次の評価へ進める価値があるが、production readinessや
S2〜S6全面移植の根拠にはならない。次のsliceも独立に評価すべきであり、Pythonは
実行可能な参照・比較基準として残す価値がある。

S2のrepository権威と単調合成、S3のSCM公開、S4の制御機構審査、S5の完了判定、
S6のベンダー接続・配備は実装しない。既存sampleの正規表現は比較用の具体例であり、
任意shellがread-onlyであることやGit pushの安全性を保証しない。
