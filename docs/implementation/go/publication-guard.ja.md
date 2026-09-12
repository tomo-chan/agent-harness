[ツール仕様書](../../spec/agent-harness-spec.ja.md) | [Repository Authority / Posture](repository-authority-posture.ja.md) | [Issue #21](https://github.com/tomo-chan/agent-harness/issues/21)

# Go 実装ノート — Publication Guard

## 1. 位置づけと範囲

本書は、Agent Harness 全体仕様の Publication Guard を Go で具体化し、S3
保証スライスで評価するための実装記録である。Publication Guard はツール
アーキテクチャ上の責務名であり、S3 は横断的な保証レビュー軸である。
`internal/publication` を「S3 package」とは扱わない。

比較基線は次のとおりである。

- 全体仕様: PR #16 HEAD `936e41e46f3e0017569507fa7488340b14c4a912`
- Go Trusted Runtime / Policy Enforcement: PR #15 HEAD `139dede4d0d0b32956309cbd82b59d83a481f4e6`
- Go Repository Authority / Posture: PR #20 HEAD `cde34e350a2fb762e335693b52c259f60d523ac1`
- Python S3 reference: PR #8 HEAD `adf939ec9960c6a67043176f217cc050ad239b98`

本実装は PR #20 に stack し、同PRの trusted task binding、固定GitHub endpoint、
current/default branch authority、GitHub rules / branch metadata source、fresh
`READY` / `BLOCKED` 判定を再利用する。Python PR #8 は保証契約と既知failure modeを
比較するreferenceであり、module構造、`shlex`、`gh` subprocess、S2の3状態を逐語移植しない。

対象は、generic hookで直接観測できる `git push` と `gh pr create` の分類、狭い
自律許可正規形、publication targetの検証、判断Evidenceへの結合である。merge、tag、
release、deploymentは通常のfeature branch publicationと同じ自律経路へ入れない。
control-plane差分審査はS4、completionはS5、実executor・credential・deployment適合は
S6の責務であり、本実装で先回りしない。

## 2. 実行経路と責任分担

```text
generic hook JSON
        ↓ strict parse / normalized action
trusted policy.json
        ↓ deny > ask > allow
publication候補を通常mutationと分離して分類
        ├─ no  → 既存Repository Authority / direct mutation経路
        └─ yes
             ↓ Repository Authority / Postureをpublication handoffとしてfresh評価
             ├─ BLOCKED / unknown → deny（unknownはexit 2）
             └─ READY
                  ↓ Publication Guard
                  ├─ canonical + 全check pass →元のallow / askを維持
                  ├─ known dangerous target → deny
                  ├─ compound / ambiguous / noncanonical → ask
                  └─ Git / GitHub取得不能 → deny + exit 2
```

`repository.AssessPublication` はdirect-file target検査だけをPublication Guardへ委譲し、
repository root、trusted worktree / Git directories / branch、local HEAD / origin、GitHub
immutable repository ID、default/current branch protectionを既存S2ロジックで評価する。
Publication Guard自身はrepository identityやGitHub rulesを再実装しない。逆にS2の
`READY`だけでpublicationを許可せず、同じactionとreportに対して公開意味論を必ず評価する。

policyの`deny`は外部取得前に確定し、Publication Guardが反転しない。policyの`ask`も
canonical check成功によって`allow`へ昇格しない。overbroadなpolicy `allow`はPublication
Guardが`ask` / `deny`へ縮退できる。

## 3. 公開候補の分類と正規形

### 広い候補分類

固定shell toolで観測したcommand中の `git ... push` と `gh ... pr ... create` を、
正規形より広くpublication候補として検出する。wrapper、追加option、複合shell中の文字列も
候補になり得る。false positiveは権限を増やさない。quote、escape、substitution、複数の
publication意味、`;` / `&&` / pipe / redirect / 改行はambiguousまたはcompoundとし、
自律許可しない。

汎用shell parserは実装しない。literal tokenへ安全に縮約できる次の正規形だけを自律許可候補にする。

### Canonical push

```text
git push origin HEAD:refs/heads/<current-branch>
git push --set-upstream origin HEAD:refs/heads/<current-branch>
```

さらに次をfreshに要求する。

- S2 reportのcurrent branch / local HEADと再観測値が一致する。
- current branchはGitHubのdefault branchではなく、S2でprotectedではない。
- refspecはlocal `HEAD`から同名のcurrent branchへの完全形だけである。
- origin fetch URLと、唯一のeffective origin push URLがS2のcanonical repositoryと一致する。
- `remote.origin.mirror`がtrueではない。重複・不正なmirror値も許可しない。
- 通常形はupstreamが `origin/<current-branch>` と一致する。
- `--set-upstream`形はbranchのremote / merge configがまだ存在しない初回形だけである。
- force / force-with-lease / force-if-includes、mirror、bulk、tag一括、delete、`+` refspecを
  autonomous pathでdenyする。
- current branch以外、default branch、tag等を明示するrefspecをdenyする。省略形やその他の
  noncanonical refspecは`ask`へ送る。

`github_branch_metadata` authority sourceは、未公開branchのmetadataを取得できないため、
初回pushがS2で`READY`にならない。このsourceでbranchを誰がpre-createするか、または初回公開を
どの承認経路へ送るかはQ-04/Q-05の接続事項として残す。Publication Guard側で404を成功へ
読み替えてS2を弱化しない。

### Canonical PR create

```text
gh pr create --fill
```

次をfreshに要求する。

- current branch / local HEAD / originがS2 reportと一致する。
- upstreamが `origin/<current-branch>` である。
- `--repo` / `-R`、`--head` / `-H`、`--base` / `-B` は、独立token、equals、短縮連結、
  subcommand前のpersistent flag形式を含めdenyする。
- repository local / worktree configに `branch.<current>.gh-merge-base` が存在しない。
- baseはfresh S2 GitHub metadataのdefault branchとしてEvidenceへ結合する。
- fixed GitHub APIから取得した `refs/heads/<current-branch>` のcommit SHAがlocal HEADと一致する。

title/body/head/base等を自由に組み立てるshell grammarは本最小実装に含めない。`--fill`以外は
通常approvalへ送り、将来広げる場合も構造化adapter入力または追加の狭い正規形として具体化する。

## 4. `gh-merge-base` findingの再評価

Python PR #8のreviewでは、`--base`を拒否した後のimplicit baseをGitHub default branchへ
委ねるとして旧指摘を解決していた。しかし`gh pr create`は、明示`--base`がない場合でも
`branch.<current>.gh-merge-base`を参照し得る。そのためoverride optionの拒否だけでは、
repository-controlled configが意図しないbaseを選ぶ経路が残る。

Go具体化では次を決定的な規則にした。

1. S2からfreshなcanonical repository / GitHub default branchを受け取る。
2. common local configとper-worktree configのkey名を、global/system configとinclude展開を
   無効化した固定`/usr/bin/git`で列挙する。
3. `branch.<current>.gh-merge-base`が存在すれば、値がdefault branchと同じであってもdenyする。
4. `include.path` / `includeIf.*.path`も、repository内外の追加configがpublication意味論へ
   混入するためdenyする。
5. selectorがない場合だけ、fresh GitHub default branchをimplicit baseとしてEvidenceへ残す。

値の同値比較を採らないのは、trusted targetをrepository-controlled selectorから導出したと
誤認しないためである。これはGitHub側のPR作成認可や、作成後のbase確認を実装したという
意味ではない。

## 5. Repository-controlled config / environment

Publication Guardはlocal common configとper-worktree configを同時に観測する。origin、push URL、
mirror、upstreamは入力として信用せず、S2 repository / current branchとの一致条件へ変換する。
origin fetch URLの重複、effective push URLの複数値、include directiveはambiguousとして拒否する。

publication processに、target、Git discovery/config、transport/executableを差し替え得る次の
非空environment selectorがあればdenyする。

- `GH_REPO`、`GH_HOST`、`GH_CONFIG_DIR`
- `GIT_DIR`、`GIT_WORK_TREE`、`GIT_COMMON_DIR`
- `GIT_CONFIG*`、`GIT_EXEC_PATH`
- object/index/namespace/replacement/shallow/discovery selector
- `GIT_SSH*`、`GIT_PROXY_COMMAND`、protocol selector

credentialだけを供給する`GH_TOKEN` / `GITHUB_TOKEN`や、promptを止める
`GIT_TERMINAL_PROMPT`はtarget selectorとして拒否しない。credential scope、secret injection、
rotation、Git/gh processの最終environment sanitizationはS6/deployment責務である。

固定`/usr/bin/git`とclean observation environmentは「実際のvendor executorも同じbinaryと
environmentでcommandを起動する」ことを証明しない。PATH resolution、Git hooks / helpers、
検証と実行のTOCTOUをhard boundaryにするにはexecutorとの構造化handoffが必要であり、
本PRではその配備契約を先取りしない。

## 6. Evidence

既存のpolicy/action EvidenceとRepository Evidenceに、`publication` Evidenceを追加する。

- publication kind
- canonical repository、current branch、local HEAD、GitHub default branch
- raw origin、唯一のeffective push URL、canonical refspec、upstream
- PR implicit base
- GitHub branch head SHAとresponse SHA-256
- publication check取得時刻
- repository authority、default branch、environment、command form、branch / HEAD、origin、
  local config、refspec / push URL / mirror / upstream / implicit base / GitHub headの
  pass / fail / unknown

GitHub branch response digestは取得byteを識別するが、GitHub署名や永続audit recordではない。
unknownはEvidenceに残した上でdeny + exit 2とし、空fieldを成功と解釈してはならない。
push前のGitHub branch headはpublication後の値と一致する必要がないため、push判断の必須checkには
しない。PR作成では「現在のlocal HEADが既に同repository / branchへ公開済み」を証明するため
必須とする。

## 7. 仕様 → Go具体化 → S3 Evidence

| 全体仕様 | Goでの具体化 | 決定的Evidence | 評価 |
|---|---|---|---|
| PU-01 | publication候補を通常mutationから分離し、canonical feature push / PR createだけをfresh repository / branch / commit / targetへ束縛 | `TestCanonicalPushBindsTargetAndEvidence`、`TestCanonicalPRCreateBindsImplicitBaseAndPublishedHead`、runtime integration | direct observable publication範囲で部分適合 |
| RE-01/02 | `AssessPublication`でS2 identity/worktree/branch/protectionを再利用し、publicationでbranch/HEAD/originを再照合 | `TestAssessPublicationReusesRepositoryAuthorityWithoutDirectFileTarget`、actual linked worktree tests | S2前提付き適合 |
| PO-01 | denyを反転せず、askをallowへ昇格せず、overbroad allowをask/denyへ縮退 | policy candidate tests、`TestPublicationKeepsLowerAskAndRejectsStaleRepositoryReport` | 実行経路で確認 |
| PO-02 | policy/action、Repository、Publication Evidenceを同一decisionへ結合 | canonical push / PR Evidence tests、runtime route test | audit永続化を除き部分適合 |
| FA-01 | Git/GitHub/config取得不能、head不一致、対象変化をallowへ変換しない | provider error、mismatch、environment、config include tests | caller前提付き適合 |
| CP-01 | Pythonの構造ではなく保証・既知finding・adversarial vectorを比較 | 第8章、Go/Python test結果 | Publication Guard範囲で部分適合 |
| PU-02 | control-plane差分を判定しない | S4へ明示委譲 | 未適合 / 本PR対象外 |

この表はS3全体、実executor、GitHub側最終認可、実配備の適合済み宣言ではない。

## 8. Python S3とのdifferential comparison

| 観点 | Python PR #8 | Go具体化 | 評価 |
|---|---|---|---|
| module / runtime | `scm_publication.py`、`shlex`、`git` / `gh` subprocess | single Go binary内の`internal/publication`、固定Git、標準library GitHub client | GoはPython import/`gh`探索を除去。binary provenance責務は残る |
| authority handoff | S2のREADY/RESTRICTED/BLOCKED reportを再取得 | PR #20のfresh READY/BLOCKED reportを専用handoffで再利用 | Goは単一strict mode。branch metadata sourceの初回公開制約あり |
| classification | regexと`shlex`で広い候補・compoundを検出 | 広いword分類後、quote/substitution/control operatorを正規形外へ倒す | 両者ともfalse positiveを権限増加に使わない |
| push | current branch、origin、push URL、mirror、upstream | 同保証にHEAD再照合、config/env selector、duplicate/include拒否を追加 | GoはS2 Evidenceとpublication Evidenceを同一decisionへ結合 |
| PR target | override forms拒否、upstream、GitHub head | option位置を含むoverride拒否、upstream、固定API branch head、implicit base | Goは`gh-merge-base` findingを未解決として再評価し修正 |
| protected branch | Python S2 default branch中心、任意protected ref集合はEV-S3-001 | PR #20 S2がexact current branchのrulesまたはprotected metadataを評価し、canonical refspecをcurrent branchだけへ限定 | 任意ref集合を列挙せず、実際のcurrent publication targetをS2で拒否 |
| Evidence | DecisionとS2 report、local/GitHub観測 | policy/action + repository + publication structured Evidence | 永続auditは双方の対象外 |

Pythonで発見したcompound shell、override表記差、local upstreamの権威化はGoの否定testへ移した。
さらにimplicit base selector、environment config injection、include、duplicate target、local HEAD変化を
Goの回帰testへ追加した。

## 9. 検証

- `go test ./...` — 成功
- `go test -race ./...` — 成功
- `go vet ./...` — 成功
- `go build ./...` — 成功
- canonical push、first-push lifecycle、force/bulk、invalid/default/tag refspec、multiple/mismatched push URL、mirror、upstream mismatch tests
- compound/quoted/ambiguous publication、PR override全形式、`gh-merge-base`、environment/config include tests
- local HEAD / branch変化、GitHub branch head mismatch / unavailable tests
- 実Git linked worktreeを使うRepository Authority handoff + Publication Guard dry decision integration
- Python PR #8 S3 differential regression — `test_scm_publication.py` / `test_policy_engine.py` の30件成功
- 実repository publication前段E2E — PR #20 worktree、repository ID `1357803614`、
  branch `feature/go-repository-authority`、HEAD `cde34e3`、GitHub branch metadata / refを
  fresh取得し、canonical pushと`gh pr create --fill`がともに`READY / allow`。実際のpush / PR createは未実行

GitHub Actions状態はPR本文へ記録する。

## 10. Open Questions / implementation notes

- Q-01/Q-10: binary version、source/toolchain/build provenance、artifact署名・更新・rollback・失効は未実装。
- Q-02: `gh pr create --fill`と2つのpush形は実験上の正規形であり、安定CLI契約ではない。
- Q-04/Q-05: branch metadata sourceでの初回publication順序、branch pre-create主体、再評価と実行のTOCTOU、push成功後の外部照合は未確定。
- Q-05: title/body/draft、fork、enterprise host、複数remote、tag/release、mergeの認可経路は未確定。暗黙に対応済みとしない。
- Q-09: publicationが外部成功した後にresponseを失うpartial-success / retry契約と、audit書込失敗時の停止を実装していない。
- Q-11: language-independent shared vector schema、必須CI、部分適合表示は未確定。
- GitHub server-side rules / authorizationが最終権威である。local `allow`はcredential scopeやrules bypass不能性を証明しない。
- current branch以外の任意protected ref集合を列挙するモデルは持たない。canonical refspecをcurrent branchへ固定し、そのexact branchのS2 authorityを要求することで現保証を成立させる。
- arbitrary child process、alias / wrapper、別API経路、credential compromiseを完全仲介しない。unknown shell mutationは既存S2 direct-target経路でfail closedになるが、完全なcapability containmentはS6のsandbox/IAM/SCM責務である。
- S4 control-plane review、S5 completion、S6 vendor/deploymentを先回りして実装しない。

したがって本実装は、Publication Guardのproduction implementation候補とS3評価Evidenceを
提供するが、S3全体の最終適合やAgent Harness全体のproduction readinessを主張しない。
