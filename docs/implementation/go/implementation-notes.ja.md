[ツール仕様書](../../spec/agent-harness-spec.ja.md) | [用語集](../../spec/agent-harness-glossary.ja.md) | [Issue #14](https://github.com/tomo-chan/agent-harness/issues/14)

# Go 実装ノート — Trusted Runtime / Policy Enforcement spike

## 1. 位置づけ

本書は、Agent Harness の[ツール仕様書](../../spec/agent-harness-spec.ja.md)にある
信頼された実行環境とポリシー強制を、Issue #14 の範囲で Go により具体化した記録である。
規範仕様、Go 専用仕様、S1 保証スライスの仕様ではない。

現行の比較対象は、2026-09-11 に確認した PR #6 の最新 HEAD
`b9e9471a5817a1e1f6cadad297154cf9b71ae381` にある Python の launcher、policy engine、
固定 adapter、信頼済みリポジトリ入力、テスト、S1 レビュー文書である。`97bb264` は
Go spike 着手時の歴史的 baseline としてだけ扱い、現行 Python S1 の代表とはしない。
Python の構造や出力を仕様の正本とはせず、対応する保証、実装、テストデータ、実行結果を
比較する。既存 Python 実装は変更しない。

全体仕様の Q-01〜Q-03、Q-10、Q-11 は未解決である。本 spike の CLI、schema、
数値制限、パス構成は、以下の実験上の仮定であり、共通契約の確定や安定版互換性の
宣言ではない。

## 2. 対象契約と適合状態

| 全体仕様 | Go での具体化 | 根拠 | 状態 |
|---|---|---|---|
| TR-01 | 実行ファイルの正規化済み親を trusted root と照合し、同じ root の固定名 `policy.json` だけを読む。adapter は静的リンクする | `TestTrustedPaths`、`TestSingleBinary` | 配備前提付き適合 |
| IO-01 | stdin から単一 JSON を読み、stdout には判断 JSON だけを出す。正常判断と処理失敗を終了コードで区別する | `TestSingleBinary`、`TestOutputFailure` | 実験 schema で適合 |
| PO-01 | JSON の記述順によらず `deny > ask > allow`。分類不能時は既定 `ask`、検証不能時は `deny` | `TestPriorityAndPredicates`、`TestInvalidPolicies` | 対象範囲で適合 |
| PO-02 | 方針の全 byte と正規化した tool/input の SHA-256、実験的評価器 ID を判断 Evidence に含める。外部状態は参照しない | `TestDecisionEvidenceIdentifiesPolicyAndNormalizedAction` | build provenance 未確立のため部分適合 |
| FA-01 | パス・設定・方針・入力の失敗時は allow を返さず、deny JSON と exit 2 を返す。出力不能時も非ゼロ終了する | 異常系 policy/hook/subprocess tests | 呼出側前提付き適合 |
| CP-01 | 現行 Python S1 と tool-policy の command vectors、信頼境界、配備前提を比較し、byte 単位互換や S1 全体の機能同等性を主張しない | `TestPythonS1Vectors`、`TestSingleBinary`、第5・6章 | tool-policy core の比較範囲で部分適合 |
| 第16章の配備前提 | バイナリ、方針、配置、祖先、起動設定をエージェントから変更不能にする責任を配備主体へ置く | 第4章の前提・否定ケース | コード単体では未立証 |

S1 のレビュー軸では TR-01、IO-01、PO-01/02、FA-01 と配備前提を対象とする。
本表は実装と根拠の対応であり、外部配備を含む最終的な保証済み宣言ではない。

現行 Python S1 は tool policy の信頼境界だけでなく、S2 が権威として利用する
repository-security policy と expected repository の生成元・再束縛も S1 の主張に含める。
Go spike はその下流権威入力を実装していないため、現行 Python S1 全体と同じ保証範囲にはない。
これは S2 の意味論を Go で実装すべきという意味ではなく、S2 へ渡す trusted input の確立を
どの trusted component が担うかが未解決という意味である。

## 3. 実験上の具体化

### Q-01 — 信頼解決

- `AGENT_HARNESS_TRUSTED_ROOT` は必須の絶対パスとする。
- symlink 解決後の実行ファイルの親が、symlink 解決後の root と一致しなければ拒否する。
- 方針は root 直下の固定名 `policy.json` とし、解決後も root 内にある通常ファイルだけを読む。
- root 内を指す symlink は許容し、境界外 symlink、欠落、ディレクトリは拒否する。
- adapter はバイナリへ静的リンクする。任意 adapter を実行時に読み込まない。
- `AGENT_HARNESS_TRUSTED_ADAPTER` と `AGENT_HARNESS_TRUSTED_POLICY` が非空なら拒否する。
  `AGENT_HARNESS_POLICY`、`AGENT_POLICY`、Python 関連変数、cwd、リポジトリ内方針は
  選択に使わない。

現行 Python S1 も generic adapter を固定し、tool policy は trusted root 内に限定する。
さらに `AGENT_HARNESS_TRUSTED_REPOSITORY_SECURITY_POLICY` を trusted root 内へ束縛し、
`AGENT_HARNESS_TRUSTED_EXPECTED_REPOSITORY` を検証して
`AGENT_HARNESS_EXPECTED_REPOSITORY` へ再束縛する。repository 側から弱化できる
`AGENT_POLICY`、`AGENT_HARNESS_REPOSITORY_SECURITY_POLICY`、
`AGENT_HARNESS_MINIMUM_POSTURE_MODE` も除去する。Go はこれらを判断に利用せず S2 を
起動もしないため、現在の単体判断を弱化する経路にはならないが、下流へ権威ある値を渡す
Python S1 の契約を代替してはいない。

これは所有権、mount、署名、更新、失効を検証しない。検査後の置換競合を防ぐのは
信頼された配置の不変性であり、パス検査自体は OS sandbox ではない。

### Q-02 — CLI と通信

- 引数と subcommand を持たない単発プロセスとする。
- 入力は UTF-8 の単一 JSON object、上限 1 MiB、深さ上限 64 とする。
- `tool`/`input` または `tool_name`/`tool_input` を受け付ける。同一項目の別名を
  両方指定した場合、重複キー、未知の最上位キー、後続 JSON、不正 UTF-8、型不正を拒否する。
- tool は空白だけではない文字列、input は object。command は文字列だけを許可する。
  exec/Bash では command を必須とし、他の tool では省略できる。argv 配列はadapterごとに
  実行意味が異なり、空白連結すると引数境界を失うため、共通schemaが確定するまで拒否する。
- context/session/turn/prompt/cwd/event は受理するが、S1 の判断権威には使わない。
  tool 固有 input の追加フィールドは評価器にとってopaqueだが、正規化操作とEvidenceには保持する。
- 出力は `decision`、`reason`、`rule` と、正常判断時の `evidence.policy_sha256`、
  `evidence.action_sha256`、`evidence.evaluator` を持つ JSON object とする。
- 正常な allow/ask/deny は exit 0。入力・方針・信頼境界の処理失敗は、安定した分類を
  reason/rule に持つ deny と exit 2。出力不能も exit 2 とする。

呼出側は、非ゼロ終了、出力欠落・不正、panic、signal、timeout を拒否として扱い、
ask を外部承認へ送る必要がある。stdin の期限とプロセス資源上限は呼出側の責任である。
本 spike はベンダー実行環境の停止挙動を保証しない。

### Q-03 — 方針評価

- top-level は任意の `default` と `deny`/`ask`/`allow` 配列だけを許可する。
- default の省略値は ask。判断値は deny/ask/allow だけとする。
- rule は文字列の `id`、`reason`、`tool_regex`、`command_regex`、`action_regex` だけを許可する。
- 全正規表現を判断前にコンパイルする。条件は AND、条件省略は無条件、空 pattern は一致とする。
- action_regex の対象はtoolとinput全体を持つ正規化JSON。同一判断内では最初の一致を採用する。
- Go の RE2 構文を使い、Python `re` 専用構文は不正方針として拒否する。

正規表現による command 分類は shell やソースコード管理操作の安全性を証明しない。
既存 sample policy の規則は対応テスト用であり、S2 以降の保証を与えない。

## 4. ビルドと配備

main package をモジュール root に置き、次の最小コマンドで単一実行ファイルを生成する。
第三者 Go module、runtime plugin、Python runtime は使わない。

```sh
go test ./...
go build
```

信頼された配備主体が OS/architecture ごとにビルドした `agent-harness` と
`policy.json` を同じ保護ディレクトリへ配置する。たとえば `/opt/agent-harness` へ
配置した場合の実験的な起動形は次のとおりである。

```sh
AGENT_HARNESS_TRUSTED_ROOT=/opt/agent-harness \
  /opt/agent-harness/agent-harness <<'JSON'
{"tool_name":"exec","tool_input":{"command":"git status"}}
JSON
```

バイナリ、方針、配置ディレクトリ、全祖先、hook の起動設定と環境を、エージェントや
評価対象リポジトリから変更できないよう権限や read-only mount 等で保護しなければならない。
書込み可能な checkout にこのバイナリを置くだけでは trusted runtime は成立しない。

single executable は runtime の可変点を減らす一方、source commit、Go toolchain、build flags、
生成 artifact の対応が新しい信頼対象になる。本 spike の判断 Evidence は policy、正規化した
tool/input、実験的評価器IDを識別するが、実行中 binary の source commit とbuild provenanceは
識別しない。
CI は `ubuntu-latest` と `macos-latest` で test/build を行うだけで、配布 artifact の
OS/architecture matrix、再現可能 build、署名、SBOM、保管、段階更新、rollback、失効、
stale binary 検出を確立しない。これらがない状態では、正しい `policy.json` と古い binary の
組合せや、未承認 toolchain で作られた binary を Evidence から区別できない。

## 5. S1 Evidence

| 主張 / 現行 Python (`b9e9471`) の根拠 | Go の根拠 | 評価 |
|---|---|---|
| root 必須・配置一致・境界外 tool policy 拒否 / launcher subprocess tests | `TestTrustedPaths`、`TestSingleBinary` | 対応する否定ケースあり |
| generic adapter 固定、repository fallback 禁止 / launcher・adapter tests | adapter の静的リンク、override・異なる cwd・方針欠落の subprocess cases | Go は runtime file / exec を不要にする |
| Python startup env 除去、adapter の `python -I` 起動 / launcher の source assertion | Python runtime を使わず、存在しない PATH と不正 Python 環境で実 binary を起動する `TestSingleBinary` | Go は同じ緩和策ではなく依存自体を除去する |
| repository-security policy と expected repository の trusted binding / launcher tests | 対応実装・テストなし | 現行 Python S1 との保証差分 |
| deny 優先 / `test_deny_precedes_ask_and_allow` | `TestPriorityAndPredicates`（ask > allow も検証） | 対応 vector あり |
| 不正 default・非文字列 / 不正 regex 拒否 / policy engine tests | `TestInvalidPolicies`（型・regex・JSON も検証） | Go は JSON 境界をさらに厳格化 |
| Git 読取り、force push、main push、merge、未知 command / policy engine tests | `TestPythonS1Vectors`、同じ command と sample policy | 意味上の判断が対応 |
| read-only allow と後続 shell 操作の分離 | `TestAllowRulesRejectCompoundShellCommands` | allow規則をcommand全体と安全な引数文字へ限定 |
| 入力解釈失敗は deny / adapter boundary | `TestHookParsing`、不正・過大入力の subprocess cases | Go の方が入力 schema の否定ケースが多い |
| 判断と再現根拠の結合 | `TestDecisionEvidenceIdentifiesPolicyAndNormalizedAction`、`TestActionPredicateCanDistinguishToolInputTargets` | policy、tool/input、評価意味論IDを識別し、tool targetを方針で区別。build provenanceは未対応 |

PR #6 の最新 HEAD では Python の対象テスト 22 件が成功する。ただしその test suite は、
isolated startup を source 文字列で検査するだけで、trusted root が正しい正常系 launcher を
end-to-end で実行しない。Python 3.9.6 と 3.12.14 で実際に起動すると、`python -I` が adapter
ディレクトリを module search path から外し、`from policy_engine import ...` が
`ModuleNotFoundError` となって exit 1 になることを確認した。したがって 22 件の PASS は個別の
境界対策を支えるが、現行 Python S1 が実行可能な正常系を成立させる根拠にはなっていない。

Go は型、重複キー、別名の曖昧性、未知キー、パス指定を Python 参照実装より厳格に扱い、
実際に build した binary の正常系・異常系を subprocess で確認する。どちらの test suite も、
配備先の read-only 性、trusted 環境変数の供給元、呼出側の fail-closed、artifact provenance を
証明しない。これは対応する保証 vector の比較であり、逐語的・byte 単位互換や完全な適合保証ではない。

## 6. Python との比較と判断

`97bb264` は歴史的 baseline であり、現在の選択判断は PR #6 の
`b9e9471a5817a1e1f6cadad297154cf9b71ae381` と行う。両 SHA の間で Python は adapter 固定、
repository-security policy / expected repository の trusted binding、弱化用環境変数の除去、
Python startup env の除去、`python -I`、regex 検証を追加した。

| 観点 | 現行 Python S1 (`b9e9471`) | Go spike | 比較評価 |
|---|---|---|---|
| 保証範囲 | tool policy に加え、S2 が使う repository-security policy と expected repository の権威を確立 | tool-policy runtime core、厳格な入出力、policy/action digest | Python の方が S1 の主張範囲は広い。Go は完全代替ではない |
| Trusted Computing Base / runtime | interpreter、launcher、固定 adapter、policy engine、複数 source、2回の interpreter startup | 実行 binary、policy data、OS loader/runtime | Go は runtime の可変要素を減らすが、build artifact を新しい TCB とする |
| policy / adapter binding | adapter 固定。tool policy の可変 path は trusted root 内へ限定 | adapter を静的リンクし、固定名 `policy.json` だけを許可 | Go の runtime 解決は単純。両者とも配備基盤の不変性が必要 |
| startup 環境 | Python startup env を exec 前に除去し、child を `-I` で起動 | PATH / PYTHONPATH / PYTHONHOME を使わない | Python の対策を評価に反映する。ただし初回 interpreter は残り、現行 `-I` handoff は正常系を壊す |
| ポリシー意味論 | deny 優先、非文字列・不正 regex を拒否。Python `re` | deny > ask > allow、全 regex を事前検証。Go RE2 | 主要 vector は対応するが regex dialect は非互換 |
| 入出力 / Evidence | permissive な JSON 正規化、decision/reason/rule | サイズ・深さ・重複・別名・型を厳格検証、argv配列を拒否、policy/tool-input digestと評価器ID | Go の方が protocol ambiguity と再現対象の識別を強く扱う |
| 実装量 | launcher / adapter / engine と trusted input 用 data | main と internal 2 package。厳格 decoder と否定テストを含む | single binary でも source / test の単純な行数削減にはならない |
| 配備 | Python version と trusted source tree を揃える。source と trace を直接確認しやすい | OS/architecture 別に binary を build・配布する | Go は runtime 配備を単純化する一方、artifact lifecycle を増やす |
| 除去できる failure mode | `-I` と env sanitize で child の user site / Python env 影響を抑制 | interpreter の欠落・version 差、module import、複数 source の欠落、adapter への exec handoff を不要にする | 現行 Python で既に除去した runtime adapter 差替えまで Go 固有の利点として数えない |
| 残存・追加 failure mode | interpreter 選択、初回 startup、isolated import、source 組合せ、exec 失敗 | source-binary 対応、toolchain/build provenance、stale binary、OS/architecture 不一致、署名・更新・rollback・失効、RE2 差 | 配置改変、host compromise、TOCTOU、caller fail-open は共通 |
| testability / Evidence | unit/launcher tests 22件は成功。ただし isolated handoff の正常系 E2E がなく、実起動は import error | `go test ./...`、実 binary subprocess、Linux/macOS CI | 現時点の E2E 根拠は Go が強い。配備根拠は双方に不足 |
| debugging / operability | source と Python traceback を直接調査できるが、interpreter・import・exec の状態を追う必要がある | 単一 process と安定した failure category / digest。修正には rebuild が必要 | Go は runtime 切分けが容易。正確な再現には build metadata と symbol / toolchain 管理が必要 |

single executable により、現行 Python が緩和している Python startup 状態をさらに縮小し、
interpreter、module import、複数 source、adapter exec handoff に起因する failure mode を除去できる。
一方で「source と実行物が同じ」という確認は binary artifact の provenance 問題へ移り、
stale binary、OS/architecture ごとの配布、署名・更新・rollback・失効を運用契約に追加する。
policy/action digest だけではこの問題を解決しない。

再評価の結論は次のとおりである。

- Go は **tool-policy runtime core の production implementation 候補**として続行する価値がある。
  これは現行 Python S1 全体を置換できるという判断ではない。
- 現行 Python は追加された trust binding により保証範囲を広げたが、isolated exec の正常系が
  壊れており、そのまま production baseline とする根拠も不足する。
- Go を production 実装として選ぶ前に、下流権威入力の担当、共有された言語非依存の
  end-to-end vectors、binary version/provenance、OS/architecture 配布、署名・更新・失効、
  実配備と caller fail-closed の Evidence を確立する必要がある。
- Python は仕様の偶然な言語依存と実装差を発見する reference / differential comparison として
  残す価値がある。実行可能な参照として扱うには、別途 `-I` handoff と正常系 E2E test を修正する。
- S2〜S6 を Go で再具体化するかは本比較から決めず、各契約の TCB、外部連携、Evidence に
  基づいて個別に判断する。

## 7. 未対応範囲

- Q-01 の所有権、署名、配布、更新、失効、利用時の再検証。
- Q-02/Q-10 の安定 schema、argv表現、version negotiation、signal/timeout の実装、互換性期間。
- Q-03 の承認 scope / expiry と policy 更新時の承認失効。
- Q-09 の監査、秘匿化、部分成功。digest は監査基盤の代替ではない。
- Q-11 の共有 test vector 形式、必須 CI、部分適合の表示規則。
- 現行 Python S1 が確立する repository-security policy / expected repository の権威を、
  Go または別の trusted component から S2 へ渡す契約と Evidence。
- binary version、source commit、toolchain/build provenance、OS/architecture artifact、署名、
  更新、rollback、失効、stale binary 検出。
- S2 のリポジトリ権限、S3 の公開、S4 の制御プレーン公開、S5 の完了保証、
  S6 のベンダー統合と実配備適合。

これらを先回りして実装せず、全体仕様で契約を確定してから各具体化を評価する。
