[ツール仕様書](../../spec/agent-harness-spec.ja.md) | [用語集](../../spec/agent-harness-glossary.ja.md) | [Issue #14](https://github.com/tomo-chan/agent-harness/issues/14)

# Go 実装ノート — Trusted Runtime / Policy Enforcement spike

## 1. 位置づけ

本書は、Agent Harness の[ツール仕様書](../../spec/agent-harness-spec.ja.md)にある
信頼された実行環境とポリシー強制を、Issue #14 の範囲で Go により具体化した記録である。
規範仕様、Go 専用仕様、S1 保証スライスの仕様ではない。

比較対象は、PR #6 のコミット `97bb264` にある Python の launcher、policy engine、
adapter、テスト、S1 レビュー文書である。Python の構造や出力を仕様の正本とはせず、
対応する保証とテストデータを比較する。既存 Python 実装は変更しない。

全体仕様の Q-01〜Q-03、Q-10、Q-11 は未解決である。本 spike の CLI、schema、
数値制限、パス構成は、以下の実験上の仮定であり、共通契約の確定や安定版互換性の
宣言ではない。

## 2. 対象契約と適合状態

| 全体仕様 | Go での具体化 | 根拠 | 状態 |
|---|---|---|---|
| TR-01 | 実行ファイルの正規化済み親を trusted root と照合し、同じ root の固定名 `policy.json` だけを読む。adapter は静的リンクする | `TestTrustedPaths`、`TestSingleBinary` | 配備前提付き適合 |
| IO-01 | stdin から単一 JSON を読み、stdout には判断 JSON だけを出す。正常判断と処理失敗を終了コードで区別する | `TestSingleBinary`、`TestOutputFailure` | 実験 schema で適合 |
| PO-01 | JSON の記述順によらず `deny > ask > allow`。分類不能時は既定 `ask`、検証不能時は `deny` | `TestPriorityAndPredicates`、`TestInvalidPolicies` | 対象範囲で適合 |
| PO-02 | 方針の全 byte と正規化した tool/command の SHA-256 を判断 Evidence に含める。外部状態は参照しない | `TestDecisionEvidenceIdentifiesPolicyAndNormalizedAction` | S1 入力範囲で適合 |
| FA-01 | パス・設定・方針・入力の失敗時は allow を返さず、deny JSON と exit 2 を返す。出力不能時も非ゼロ終了する | 異常系 policy/hook/subprocess tests | 呼出側前提付き適合 |
| CP-01 | Python と同じ command vectorsを意味上の判断で比較し、byte 単位互換を主張しない | `TestPythonS1Vectors`、第6章 | spike の比較範囲で適合 |
| 第16章の配備前提 | バイナリ、方針、配置、祖先、起動設定をエージェントから変更不能にする責任を配備主体へ置く | 第4章の前提・否定ケース | コード単体では未立証 |

S1 のレビュー軸では TR-01、IO-01、PO-01/02、FA-01 と配備前提を対象とする。
本表は実装と根拠の対応であり、外部配備を含む最終的な保証済み宣言ではない。

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

これは所有権、mount、署名、更新、失効を検証しない。検査後の置換競合を防ぐのは
信頼された配置の不変性であり、パス検査自体は OS sandbox ではない。

### Q-02 — CLI と通信

- 引数と subcommand を持たない単発プロセスとする。
- 入力は UTF-8 の単一 JSON object、上限 1 MiB、深さ上限 64 とする。
- `tool`/`input` または `tool_name`/`tool_input` を受け付ける。同一項目の別名を
  両方指定した場合、重複キー、未知の最上位キー、後続 JSON、不正 UTF-8、型不正を拒否する。
- tool は空白だけではない文字列、input は object。command は文字列または文字列配列。
  exec/Bash では command を必須とし、他の tool では省略できる。
- context/session/turn/prompt/cwd/event は受理するが、S1 の判断権威には使わない。
  tool 固有 input の追加フィールドは opaque とする。
- 出力は `decision`、`reason`、`rule` と、正常判断時の `evidence.policy_sha256`、
  `evidence.action_sha256` を持つ JSON object とする。
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
- action_regex の対象は tool、改行、command の連結。同一判断内では最初の一致を採用する。
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

## 5. S1 Evidence

| 主張 / Python の対応根拠 | Go の根拠 |
|---|---|
| root 必須・配置一致・境界外方針拒否 / launcher tests | `TestTrustedPaths`、`TestSingleBinary` |
| trusted policy 必須・repository fallback 禁止 / adapter test | 方針欠落、異なる cwd、旧環境変数の subprocess cases |
| deny 優先 / `test_deny_precedes_ask_and_allow` | `TestPriorityAndPredicates`（ask > allow も検証） |
| 不正 default 拒否 / `test_invalid_policy_fails_validation` | `TestInvalidPolicies`（型・regex・JSON も検証） |
| Git 読取り、force push、main push、merge、未知 command | `TestPythonS1Vectors`、同じ command と sample policy |
| 入力解釈失敗は deny | `TestHookParsing`、不正・過大入力の subprocess cases |
| 任意 adapter / policy への差替え防止 | path / override tests、adapter の静的リンク |
| cwd / import 依存の除去 | 無関係な cwd、存在しない PATH、不正 Python 変数で実バイナリを起動 |
| 判断と再現根拠の結合 | policy/action digest tests |

Go は型、重複キー、別名の曖昧性、未知キー、パス指定を Python 参照実装より厳格に扱う。
これは対応する保証 vector の比較であり、Python との逐語的または byte 単位互換ではない。

## 6. Python との比較と判断

| 観点 | Python S1 (`97bb264`) | Go spike |
|---|---|---|
| 保証範囲 | root / adapter / policy の包含、deny 優先 | 同じ S1 主張に加え、adapter の静的固定と policy/action Evidence |
| 実装量 | runtime の3ファイル、約270行 | main と internal 2 package。厳格 JSON と否定テストにより行数削減ではない |
| runtime 依存 | Python、import、複数 source、exec 引継ぎ | 単一 native executable と policy data |
| 配備 | interpreter と信頼済み source tree | OS/architecture 別 build、binary/policy の信頼済み配布 |
| failure modes | interpreter/import/path/引継ぎ | architecture 不一致、古い binary、toolchain/build provenance、RE2 非互換。配置改変リスクは共通 |
| testability | unit tests と launcher subprocess tests | `go test ./...`、実バイナリ subprocess、Linux/macOS CI |
| debugging / operability | source 編集と interpreter 診断 | rebuild が必要。安定した failure category と digest で再現対象を識別 |

single binary により interpreter 選択、PYTHONPATH、module import、adapter exec handoff、
runtime adapter 差替えを除去でき、S1 の runtime boundary は単純になった。一方、厳格な
decode と攻撃的入力のテストにより実装自体は小さくならず、trusted distribution、host compromise、
caller の fail-open、build provenance は残る。

Go は production implementation 候補として次の独立評価へ進める価値がある。
この結果だけで S2〜S6 を Go 化する判断はできない。Python は実行可能な参照、異なる
runtime による比較基準、仕様の偶然な言語依存を発見する材料として残す価値がある。

## 7. 未対応範囲

- Q-01 の所有権、署名、配布、更新、失効、利用時の再検証。
- Q-02/Q-10 の安定 schema、version negotiation、signal/timeout の実装、互換性期間。
- Q-03 の承認 scope / expiry と policy 更新時の承認失効。
- Q-09 の監査、秘匿化、部分成功。digest は監査基盤の代替ではない。
- Q-11 の共有 test vector 形式、必須 CI、部分適合の表示規則。
- S2 のリポジトリ権限、S3 の公開、S4 の制御プレーン公開、S5 の完了保証、
  S6 のベンダー統合と実配備適合。

これらを先回りして実装せず、全体仕様で契約を確定してから各具体化を評価する。
