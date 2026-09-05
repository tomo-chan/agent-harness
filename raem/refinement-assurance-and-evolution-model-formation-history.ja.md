# RAEM形成過程
## Agent Harnessの設計から Refinement, Assurance and Evolution Model に至るまで

## 1. この記録の目的

本書は、Refinement, Assurance and Evolution Model（RAEM）の仕様そのものを説明する文書ではない。

RAEMが、

- どのような実務上の問題から生まれたのか
- 当初どのような設計として考えられていたのか
- 何がうまく説明できなかったのか
- アーキテクチャレビューによって何が発見されたのか
- どの概念が追加・分離・再定義されたのか
- なぜ最終的に Refinement / Assurance / Evolution の三つが必要になったのか

を記録するための文書である。

RAEMの最終形だけを見ると、抽象モデル、具体化、適合保証、モデルレビュー、決定的プロセスと非決定的プロセスといった概念が、最初から一つの体系として設計されていたように見える。

実際にはそうではない。

RAEMは、AIエージェントを安全に長時間自律実行させるための具体的なAgent Harnessを設計し、その実装をレビューし、そこで見つかった問題を一般化する過程から形成された。

したがって、この形成過程そのものがRAEMの重要な実例でもある。

---

## 2. 出発点 ― 自律型AIエージェントを安全に動かしたい

議論の出発点は理論モデルではなく、非常に具体的な要求だった。

目的は、Codex、Claude Code、Devin CLIなどのAIコーディングエージェントを、可能な限り人間の承認なしで長時間動作させることである。

想定する運用には、

- リポジトリの調査
- コード変更
- テスト
- Git操作
- worktreeの作成
- feature branchへのcommit
- push
- Pull Request作成

までが含まれる。

一方で、エージェントに単純に広い権限を与えることはできない。

特に問題になるのは、

- credentialの漏洩
- default branchへの直接変更
- force push
- 誤ったrepositoryへのpush
- policy bypass
- sandbox外へのアクセス
- GitHub側の保護設定が存在しない状態での自律実行

などである。

ここで最初に現れた問題は、

> **自律性を高めるほど安全性が下がり、安全性を高めるため人間承認を増やすほど自律性が失われる**

という構図だった。

当初の設計課題は、このトレードオフをどう解くかであった。

---

## 3. 最初の設計 ― Agent Harnessによる中央Policy Engine

最初に考えた基本構造は、各AIエージェント製品の機能を直接信頼するのではなく、共通のHarnessを置くことであった。

構造としては、

```text
Claude Code
Codex
Devin CLI
    ↓
Vendor Adapter
    ↓
Central Policy Engine
    ↓
allow / ask / deny
```

という形である。

基本原則は、

```text
deny > ask > allow
```

とした。

policy評価そのものに失敗した場合はfail closedとし、エージェント側の判断で継続させない。

また、

- SessionStart
- PreToolUse
- Stop

などのLifecycle Hookを使い、エージェントの操作をHarnessへ接続する構造を検討した。

この時点では議論の中心はまだ、

> 「安全なAgent Harnessをどう実装するか」

であり、RAEMのような一般モデルは存在していなかった。

---

## 4. credentialをどう守るか ― SCM Broker案

初期設計では、GitHub credentialをAIエージェントから直接見えなくするために、SCM Brokerを設ける案を検討した。

構造は概ね、

```text
Agent
  ↓
git / gh shim
  ↓
SCM Broker
  ↓
GitHub credential
  ↓
GitHub
```

である。

この設計では、AIエージェント自身はcredentialを保持せず、BrokerだけがGitHubへアクセスする。

credential confidentialityという観点では強い設計である。

しかし、この方式には別の問題があった。

Brokerを導入すると、

- 別process
- 別container
- sidecar
- shim
- 独自protocol
- IPC
- Broker自体のauthorization
- Broker自体の脆弱性
- deployment complexity
- failure mode

が増える。

そこで、

> 「credentialを絶対に見せないためにシステム構成を複雑化すること自体が、新しいリスクを作っていないか」

という問いが出た。

---

## 5. 大きな方針転換 ― credential漏洩を完全防止しない

ここで重要な設計判断が行われた。

credential confidentialityを唯一のsecurity invariantにしない。

つまり、

> **credential compromiseは起こり得るfailure modeとして扱い、その影響を封じ込める**

という考え方へ変えた。

その結果、基本構成は、

```text
1 Pod
  ↓
1 Agent Container
  ↓
native git / gh
```

という単純な構成へ戻した。

credentialについては、

- short-lived
- repository-scoped
- least privilege
- GitHub App / workload identity等
- server-side Rulesets

によって影響範囲を限定する。

ここで重要になった考え方が、

> **すべての安全性を一つの仕組みへ背負わせない**

という責務分離である。

Sandboxはcredential exposureを減らす。

Policy Engineは危険な操作を防ぐ。

IAMはcredential compromise時の権限範囲を限定する。

GitHub Rulesetsはrepository側で最終的な強制を行う。

この時点で、後のRAEMにつながる一つ目の重要な考え方が生まれている。

それは、

> **Soft controlとAuthorityを分離する**

ことである。

Agent Harnessは安全性の全責任を持つauthorityではない。

---

## 6. SessionStart Repository Postureという考え方

次に問題になったのは、

> 「Agent Harness自身が正しくても、GitHub repository側の保護設定が弱ければ安全ではない」

という点だった。

例えば、

- Pull Request必須でない
- force pushを禁止していない
- required status checkがない

状態でAIエージェントを自律実行するのは危険である。

そこでSessionStart時にrepository security postureを確認する案が生まれた。

評価結果は単純なBooleanではなく、

```text
PASS
FAIL
UNKNOWN
```

とした。

UNKNOWNを導入したのは、

- API権限不足
- GitHub planによる機能差
- transient API failure
- trusted identity不明

など、

> 「保護されていない」のではなく「確認できない」

ケースを区別するためである。

その評価結果からsession状態を、

```text
READY
RESTRICTED
BLOCKED
```

へ正規化する。

この設計は後のRAEMにおける、

- Evidence
- Assurance Result
- UNKNOWN semantics

へつながっている。

---

## 7. 最初の重大なアーキテクチャレビュー

Agent Harnessの実装が進んだ段階で、

> 「ここまでの実装がアーキテクチャや設計原則に違反していないか」

というレビューを行った。

ここで非常に重要な問題が発見された。

当時のpolicyには、

```text
git status
```

のようなread-only git commandを許可する正規表現が存在した。

しかしprefix-basedな判定だったため、

```bash
git status && git push origin feature/x
```

というcommandがread-onlyとして誤分類される可能性があった。

つまり、

```text
Policyではread-only
    ↓
実際にはshell control operatorでmutationを追加可能
    ↓
RESTRICTED状態でもremote mutation可能
```

というbypassである。

これは単なる実装バグとして修正することもできた。

しかし議論では、

> 「なぜこのバグが成立したのか」

を考えた。

原因は、

> **Git commandを文字列prefixとして評価していた**

ことであり、本質的には、

> **公開操作を広いsyntactic allowlistで表現すること自体が危険**

だった。

そこで単なるregex修正ではなく、設計を変更した。

---

## 8. Canonical SCM Publicationという一般化

`git push`について、自律実行可能な形を極端に限定した。

許可するcommand shapeを、

```bash
git push
```

または、

```bash
git push --set-upstream origin HEAD
```

だけにした。

さらに文字列判定だけではなく、

- current branch
- default branch
- origin repository
- upstream
- detached HEAD

などを実際のGit stateから確認するsemantic validationを導入した。

これによって、

```text
Command syntax
+
Repository state
+
Posture state
```

を組み合わせてpublicationを評価するようになった。

このレビューで重要なのは、

```text
Concrete bug
↓
原因分析
↓
一般化
↓
新しい設計原則
↓
実装変更
↓
回帰テスト
```

という流れが自然に起こったことである。

後にこれはRAEMの中心的なEvolution loopそのものとして認識されることになる。

---

## 9. Trusted Repository Identity問題

次にレビューで見つかった問題は、repository identityである。

当初はrepository-local configurationに、

```text
expected_repository
```

を指定できる設計だった。

しかしこれは、そのrepository自身が編集可能なconfigurationである。

すると、

> 「どのrepositoryであるべきか」

というtrust anchorを、そのrepository自身が決める構造になる。

これはauthority boundaryとして弱い。

そこで、

```text
AGENT_HARNESS_EXPECTED_REPOSITORY
```

をtrusted launcher/orchestrator側から与える設計へ変更した。

repository-local configurationは補助的なconsistency checkに格下げされた。

同様に、

```text
AGENT_HARNESS_MINIMUM_POSTURE_MODE
```

もlauncher側で所有させ、repository側からsecurity postureを`warn`へ弱められないようにした。

ここでも、

> **誰がそのpolicyを定義するauthorityなのか**

という問題が、単なるconfig設計以上に重要であることが明確になった。

---

## 10. ここまでの設計を「二つのレイヤー」で整理した

Agent Harnessの設計がある程度成熟した後、repository全体の構造を整理するため、

- Harness Layer
- Application Layer

という二層構造を導入した。

Harness Layerは、

- Hooks
- Policy
- Sandbox
- Repository Posture
- SCM publication safety

などを扱う。

Application Layerは、

- Application Architecture
- Architecture Rules
- deterministic gates

を扱う。

この時点では、この分類は自然に見えた。

Agent Harnessそのものの安全性と、その上でエージェントが変更するapplication architectureの安全性を分けたかったからである。

そのため、

```text
Harness Layer
Application Layer
```

という名前になった。

---

## 11. Application Architecture Gate

Application Layerでは、

> 「LLMレビューだけをarchitectureの最終判定にしてよいのか」

という問題を考えた。

結論はNoだった。

AIエージェントは、

- architecture violationを発見する
- 新しい問題を疑う
- design smellを指摘する

ことには向いている。

しかし、

> merge可能かどうか

をAIエージェント自身の非決定的判断へ委ねるべきではない。

そこで、

```text
Architecture Contract
        ↓
Deterministic Evidence
        ↓
Architecture Gate
        ↓
PASS / FAIL
```

という構造を導入した。

例えば、

- path exists
- path absent
- file contains regex
- file does not contain regex

のような決定的checkを実装した。

また、

- explicit waiver
- waiver expiration
- fail-closed config
- CI authority
- no llm_review check type

という原則も導入した。

この段階で、

> **LLMは問題を発見してもよいが、既知のarchitecture ruleの最終判定は決定的にする**

という重要な考えが明確になっていた。

ただし、まだこれを「Application Layer」と呼んでいた。

---

## 12. 二層モデルへの違和感

その後、議論を続ける中で、

> 「Harness LayerとApplication Layerという分類は、本当に同じ軸の二つのレイヤーなのか」

という疑問が生まれた。

詳しく見ると、Harness Layerには、

- 抽象的な原則
- security invariant
- concrete implementation
- vendor integration
- deployment
- external authority

が混在している。

一方Application Layerには、

- architecture principle
- deterministic evidence
- gate mechanism
- review

が混在している。

つまり、

```text
Harness
vs
Application
```

は技術的な対象領域の違いを表しているだけであり、

> **設計知識がどのように抽象から具体へ落ち、どう保証されるか**

という本質的な構造を説明できていなかった。

ここがRAEM形成の大きな転換点である。

---

## 13. Abstract Model / Concrete Modelという再解釈

まず現れたのは、

- Abstract Model
- Concrete Model

という区別である。

Agent Harnessの設計原則には、例えば、

> protected default branchをAIエージェントが直接変更してはならない

という性質がある。

これはGitHubや`git push`そのものについての要求ではない。

より抽象的には、

> **重要なSCM authorityはAIエージェントから独立していなければならない**

という性質である。

一方、その実現方法として、

```text
GitHub Rulesets
branch protection
canonical git push
repository-scoped credential
```

などがある。

ここで、

```text
Abstract Model
    ↓
Concrete Model
```

という構造が見えてきた。

---

## 14. しかしAbstract → Concreteだけでは不足した

当初は、

```text
Abstract Model
    ↓
Transformation
    ↓
Concrete Model
```

という考え方をした。

形式的には、

```text
C = T(A)
```

である。

しかし、ここで重大な論理的問題に気づいた。

Transformationを行ったからといって、

```text
C ⊨ A
```

とは限らない。

なぜなら、

- transformation ruleそのものが間違っている
- implementationにbugがある
- configurationが違う
- external policyが存在しない
- runtime assumptionが成立しない

可能性がある。

したがって、

> **具体化されたことは、適合していることを意味しない**

という区別が必要になった。

これによって、

```text
Abstract Model
    ↓
Refinement
    ↓
Concrete Model
    ↓
Evidence
    ↓
Conformance Assurance
```

という構造になった。

---

## 15. Verificationという言葉への違和感

この段階で、Concrete ModelがAbstract Modelを満たしていることを確認する処理を何と呼ぶかが問題になった。

候補には、

- Verification
- Validation
- Proof
- Compliance
- Certification
- Assurance

があった。

Verificationは広すぎる。

Validationは、

> 「要求そのものが正しいか」

という意味が強く、今回とは異なる。

Proofは数学的・形式的証明を連想させ、一般的なCI evidenceまで含めるには強すぎる。

Complianceは規制準拠の印象が強い。

Certificationは第三者認証の意味が強い。

そこで、

> **EvidenceとReasoningに基づいて、定義された範囲内で適合性への信頼を確立する**

という意味を持つAssuranceを採用した。

より正確には、

> **Conformance Assurance**

とした。

ここで、

```text
Claim
+
Evidence
+
Reasoning
↓
Assurance Result
```

という概念が成立した。

また、

> GateはAssuranceではない

という区別も生まれた。

GateはAssurance Resultを強制するmechanismにすぎない。

---

## 16. それでも残った問題 ― 定義されていない問い

Conformance Assuranceが導入されると、

> 「すべてのAssuranceがPASSならarchitectureは正しいか」

という問いが生まれた。

答えはNoである。

Assuranceは、

> **すでに定義されたClaim**

しか評価できない。

例えば、

```text
default branchへのdirect push禁止
```

というClaimが定義されていれば、それは保証できる。

しかし、

```text
git status && git push
```

のような未知のbypassが存在すること自体を、Claimが存在しない状態からAssurance Engineが発見することはできない。

つまり、

```text
Assurance
=
known questionへの回答
```

であり、

```text
unknown questionの発見
```

は別のprocessが必要である。

ここでModel Reviewの役割が明確になった。

---

## 17. Model Reviewの再定義

Model Reviewは、

- Abstract Modelに欠けているinvariant
- Refinement ruleの誤り
- Concrete realizationの抜け
- Evidenceの弱さ
- Assurance bypass
- trust boundaryの誤認
- 暗黙のassumption

を探索する。

つまり、

> **Assuranceは既知の問いに答え、Model Reviewは未知の問いを発見する。**

という役割分担である。

重要なのは、Model Reviewそのものをmerge authorityにしなかったことである。

AIエージェントによるレビューは非決定的である。

そのため、

```text
Agent Review
↓
PASS
```

をmerge gateにするのではなく、

```text
Agent Review
↓
Finding
↓
Generalization
↓
Invariant / Constraint / Principle
↓
Refinement Rule
↓
Evidence
↓
Deterministic Assurance
```

へ知識を移す。

この時点で、後のRAEMのEvolutionがほぼ形成されていた。

---

## 18. 最も重要な発見 ― AIエージェントの役割が逆転した

ここまでの設計を整理すると、非常に重要なことが見えてきた。

最初は、

```text
AIエージェントに仕事をさせる
```

ことが目的だった。

しかし成熟した設計では、

```text
既知の判断
↓
決定的な仕組み
```

へどんどん移している。

つまり、

> AIエージェントに任せる仕事を増やしているのではなく、  
> **決定的にできる仕事ほどAIエージェントから取り除いている。**

一見すると、これはAIエージェントの役割を減らしているように見える。

しかし実際には逆である。

既知の判断を外へ出すことで、AIエージェントの推論能力を、

- 未知の問題
- 新しいattack path
- architecture gap
- model deficiency
- abstraction leak
- better refinement
- missing evidence

へ集中できる。

ここでRAEMの中心的な思想が生まれた。

> **エージェントの自律性を制限するために決定的な仕組みを作るのではない。  
> エージェントをより高次の非決定的な仕事へ解放するために、決定的な仕組みを作る。**

---

## 19. 決定的領域と非決定的領域

この考え方から、システム全体を、

### 決定的領域

既知の知識を扱う。

- policy
- test
- schema
- static analysis
- permission
- invariant
- assurance
- gate
- enforcement

### 非決定的領域

未知を扱う。

- exploration
- hypothesis
- review
- architecture reasoning
- unknown attack discovery
- model gap discovery
- abstraction redesign

に分ける考え方が生まれた。

ここで重要なのは、

> 非決定的領域を減らすこと

が目的ではないことである。

成熟とは、

```text
以前は未知だった問題
↓
発見
↓
理解
↓
一般化
↓
決定的領域へ移動
```

することである。

するとAIエージェントはさらに新しい未知へ進める。

したがって、

```text
Known area grows
+
Unknown frontier also moves outward
```

という形でシステムが進化する。

---

## 20. RCAMという中間案

この段階ではモデルを、

**Refinement and Conformance Assurance Model**

と呼ぶ案が生まれた。

略称はRCAMである。

この名前は、

```text
Abstract Model
↓
Refinement
↓
Concrete Model
↓
Conformance Assurance
```

という構造を非常によく表していた。

しかし議論を進めると、RCAMには重要な要素が欠けていることが分かった。

それが、

> **新しい知識をどう発見し、モデルそのものをどう改善するか**

である。

RefinementとAssuranceだけでは、

```text
既知のAbstract Model
```

を正しく具体化し、保証することはできる。

しかし、

```text
Abstract Modelそのものに不足がある
```

場合を扱えない。

そこでEvolutionを独立した柱として加えた。

---

## 21. RAEMへの到達

最終的にモデル名を、

# Refinement, Assurance and Evolution Model

略して、

# RAEM

とした。

三つの柱は、

```text
Refinement
Assurance
Evolution
```

である。

### Refinement

既知の抽象的要求を具体的なsystem realizationへ落とす。

### Assurance

Concrete ModelがAbstract Modelへ適合していることをEvidenceとdeterministic reasoningで確立する。

### Evolution

現在のAbstract Model、Refinement、Concrete Model、Evidence、Assuranceでは表現できていない問題を探索し、新しい知識として体系へ取り込む。

これによって、

```text
Refine.
Assure.
Evolve.
```

という循環が成立した。

---

## 22. RAEMの本当の新規性をどこに置くか

議論の中で、RAEMを構成する個々の概念自体は新しいものではないという認識も明確になった。

- refinement
- formal methods
- assurance
- policy-as-code
- deterministic verification
- architecture review
- continuous improvement

などには既存研究や実務との共通点が多い。

したがってRAEMの価値を、

> 「RefinementやAssuranceという概念を発明した」

とは捉えない。

重要なのは、

> **AIエージェントの役割を、決定的システムとの責務分離として再設計したこと**

である。

特に、

```text
AIが発見する
↓
知識を一般化する
↓
決定的システムへ移す
↓
AIはさらに未知へ進む
```

という知識移送の循環である。

この意味でRAEMは、

> AIエージェントの能力を「作業量」ではなく「未知を探索する能力」として最大化するモデル

として整理された。

---

## 23. Core RAEMが必要になった理由

さらに議論すると、別の問題が現れた。

AIエージェントが人間には理解困難な問題を発見する可能性がある。

そのとき、

> 「AIが正しいと言っているから採用する」

という形を許すべきか。

これを無条件に許すと、

- 人間が学習しなくなる
- system理解が失われる
- AI reasoningがblack box化する
- organization knowledgeが蓄積しない
- governance能力が育たない

という問題が起こる。

そこでRAEMの基本形では、

```text
Agent Finding
↓
Human Understanding
↓
Generalization
↓
RAEM Application Evolution
↓
Deterministic Assurance
```

を要求する。

これをCore RAEMとした。

ここで人間理解はapprovalのためではない。

> **AIエージェントが発見した知識を、人間と組織にも移すため**

に存在する。

---

## 24. 「理解できない」をどう扱うか

しかし将来的には、

- 巨大なdependency graph
- combinatorial exploration
- 非常に長いformal derivation
- 多数system間のinteraction

など、人間が実用的にすべて追跡できない問題が現れる可能性がある。

ここで、

> 「理解できないならExtendedへ移行」

という単純なルールにすると危険である。

理解できない原因は、

- 単なる知識不足
- 説明不足
- visualization不足
- expert不足
- unnecessary complexity

かもしれない。

したがって、

> **人間の知識不足と、人間の実用的認知限界を区別する**

必要がある。

この区別が、CoreとExtendedの境界を決める重要な原則になった。

---

## 25. Extended RAEM

十分に成熟した領域では、

> 人間が詳細な推論過程を完全に追跡できること

を必須条件から外せる。

その代わり、

```text
Finding
↓
Formalization
↓
Independent Assurance
↓
Governance
↓
Adoption
```

を要求する。

これをExtended RAEMとした。

ただし人間が理解しなくてよいのは、

- 全探索経路
- 全dependency expansion
- 長大なproof derivation
- combinatorial reasoning

などのdetailである。

人間は依然として、

- 何を意味するのか
- 何に適用するのか
- 何を前提とするのか
- どのEvidenceを使うのか
- Assuranceをなぜ信頼できるのか
- 失敗したらどうなるのか
- どう停止・撤回・rollbackするのか

を理解しなければならない。

したがってExtended RAEMは、

> **理解を放棄するモデルではなく、人間が理解する抽象度を上げるモデル**

である。

---

## 26. Concrete Modelの範囲をrepository内に限定しなかった理由

RAEMをAgent Harnessへ適用すると、Concrete Modelを単なるsource codeと考えることができない。

例えば、

```text
GitHub Rulesets
```

はrepository内のcodeではない。

IAM permissionもrepository外である。

Kubernetesのruntime security設定も場合によってはdeployment側で管理される。

したがってConcrete Modelを、

```text
Code
+ Configuration
+ Deployment
+ External Policy
+ Permissions
+ Runtime State
+ Operational Assumptions
```

と定義した。

これはAssuranceにとっても重要である。

repository static analysisだけでは、system全体のconformanceを保証できないからである。

---

## 27. Evidenceという概念が必要になった理由

Application Architecture Gateでは、当初、

```text
file contains regex
```

のようなcheckをarchitecture ruleとして扱っていた。

しかしこれは危険である。

architecture principleそのものと、その代理となるlint ruleを混同すると、

> gateがPASSすること

が目的化する。

そこで、

```text
Claim
↓
Evidence
↓
Reasoning
```

という構造を明示した。

例えば、

```text
Claim:
protected default branch cannot be directly mutated

Evidence:
effective GitHub branch rules

Reasoning:
required PR + non-fast-forward restriction + status requirements
```

のようにする。

これによって、

> EvidenceがClaimに対して直接的か

を議論できる。

これは、RAEMがarchitecture-as-codeを単なるlint集へ縮退させないための重要な考え方になった。

---

## 28. 原則・不変条件・制約を分ける

さらに、すべてのarchitecture knowledgeをBoolean gateにすることにも違和感が生じた。

例えば、

> minimize complexity

は重要な原則だが、

```text
PASS / FAIL
```

へ直接変換するのは難しい。

一方、

> default branchへ直接pushしてはならない

はdeterministic invariantとして表現できる。

そこで少なくとも、

```text
Principle
Invariant
Constraint
```

を区別する考え方が生まれた。

これはRAEMにおける重要な節度である。

> **決定的にできるものだけを決定的にする。**

決定的に表現できない原則を無理にlintへ落とすと、抽象モデルが歪む。

---

## 29. Governanceを第四の柱にしなかった理由

RAEMではGovernanceも重要である。

しかし、

```text
Refinement
Assurance
Evolution
Governance
```

という四本柱にはしなかった。

Governanceは、

- Refinementで何を採用するか
- Assuranceで何を信頼するか
- EvolutionでどのFindingを規範へ昇格するか
- Extended RAEMをどこへ適用するか

のすべてに横断的に関与する。

したがってGovernanceは、

> **RAEM三本柱を横断するcontrol plane**

として扱う方が自然であると整理した。

---

## 30. RAEM文書の構成自体も進化した

RAEM文書の作成過程でも同じ問題が起きた。

最初の文書では、

- 「モデル進化」
- 「既存モデル」
- 「現在のモデル」

といった抽象的な「モデル」という言葉が頻繁に使われ、何を指しているか分かりにくかった。

また、

- Core / Extendedの説明が突然現れる
- 「なぜ」が不足している
- 章同士の接続が弱い
- 読者が議論の背景を知らないと価値を理解しにくい

という問題があった。

これを改善しようとして一度、文書全体を大きく再構成した。

しかし、その結果、

> **それまでの議論にあった熱量が失われた**

という問題が発生した。

そこで方針を変更した。

構成そのものは大きく変えず、

- 曖昧な「モデル」を具体的名称へ置き換える
- 必要な箇所へ「なぜ」を追加する
- 章間の接続を補強する
- Core / Extendedの前に成熟概念を説明する

という局所的な修正に戻した。

これはRAEMの文書設計においても重要な判断だった。

> 理論を整理することと、理論を生んだ問題意識の熱量を残すことは両立させる必要がある。

---

## 31. Agent HarnessからRAEMを分離した理由

当初RAEM文書はAgent Harness repositoryの番号付きdocument hierarchyの上位文書として置く案があった。

しかし議論を進めると、

> RAEMはAgent Harnessそのものではない

ことが明確になった。

Agent Harnessは、

```text
RAEM
↓
自律AI開発への適用
↓
Concrete realization
```

の一例である。

したがってRAEMをAgent Harness implementationと同じPRに含めると、

- 理論
- その具体的適用
- reference implementation

の境界が曖昧になる。

そこでRAEMを独立PRへ分離した。

ファイル名もREADMEではなく、

```text
raem/refinement-assurance-and-evolution-model.ja.md
```

とした。

これは、

> repository説明文書ではなく、一つの独立した理論文書として扱う

という意図による。

---

## 32. PR #3

RAEM文書は、

```text
feature/raem
```

branchへ独立させ、

```text
PR #3
docs: define Refinement, Assurance and Evolution Model (RAEM)
```

として`main`へ直接向けた。

一方、

- PR #1 = Agent Harness reference implementation
- PR #2 = Application Architecture Gate

という既存の変更からは分離した。

RAEMは一度PR #2上に存在したが、そのcommitを取り除き、`main`をparentとする独立commitとして作り直した。

これによって、

```text
Theory
≠
Reference Implementation
```

という境界をGit history上でも明確にした。

PR #3は最終的に`main`へsquash mergeされた。

---

## 33. RAEMから既存Agent Harnessを見直した結果

RAEM形成後、逆にRAEMを使ってAgent Harness repositoryをレビューした。

すると、それまで自然に見えていた、

```text
Harness Layer
Application Layer
```

という二層構造が、RAEMの観点では不適切であることが明確になった。

特に、

```text
Application Layer
```

という名前の中に、

- Assurance
- Model Review
- architecture invariant
- deterministic gate

が混在していた。

そこで、

```text
Abstract Model
Refinement
Concrete Model
Conformance Assurance
Evolution
```

という役割で既存artifactを再分類する方向が見えてきた。

これは非常に重要な出来事である。

RAEMはAgent Harnessから生まれたが、

> **完成したRAEMをAgent Harnessへ適用すると、Agent Harness自身の設計上の分類誤りが発見された。**

つまりRAEMは、自身を生み出したsystemへfeedbackを返した。

---

## 34. この議論そのものがRAEMの実例である

全体を振り返ると、RAEMの形成過程そのものがRAEMとして説明できる。

最初にConcreteなAgent Harnessがあった。

```text
Concrete implementation
```

そこへarchitecture reviewを行った。

```text
Model Review
```

レビューによって、

```text
git status && git push
```

という未知のbypassや、trusted repository identity問題が発見された。

```text
Finding
```

それを単なるbug fixで終わらせず、

- canonical publication
- trusted authority
- external enforcement
- deterministic known boundary

という一般的知識へ変換した。

```text
Generalization
```

その知識から、

- Abstract Model
- Refinement
- Assurance
- Evolution

というより抽象的な構造が形成された。

```text
Model Evolution
```

さらに形成されたRAEMを既存Agent Harnessへ適用すると、

```text
Harness Layer / Application Layer
```

という既存architecture classificationの問題が発見された。

つまり、

```text
Concrete system
↓
Nondeterministic review
↓
Finding
↓
Generalization
↓
RAEM
↓
RAEMによるConcrete systemの再レビュー
↓
新しいFinding
↓
さらにEvolution
```

という循環が実際に発生している。

これはRAEMのconceptual exampleではなく、RAEMが生まれた実際の過程である。

---

## 35. 最終的に得られた中心命題

この一連の議論から得られた最も重要な命題は、次のものである。

> **決定的に扱える既知の知識は仕組みに固定し、AIエージェントの非決定的能力は、未知の問題の探索とRAEM適用体系の進化に集中させる。**

これを別の角度から言えば、

> **決定的にできる仕事ほど、AIエージェントの判断から外していく。**

その目的はAIエージェントを制限することではない。

> **AIエージェントを、決定的な仕組みではまだ扱えない、より価値の高い問題へ解放することである。**

そしてAIエージェントが発見した知識が安定したなら、

```text
Nondeterministic Discovery
↓
Understanding / Formalization
↓
Generalization
↓
Abstract Knowledge
↓
Refinement
↓
Evidence
↓
Deterministic Assurance
```

へ移す。

この循環によって、

- AIエージェント
- 人間
- 組織
- 対象システム
- RAEM適用体系
- Assurance

が共に成熟する。

---

## 36. RAEM形成過程から得られた設計上の教訓

RAEMが形成される過程から、いくつかの一般的な教訓も得られた。

第一に、Concreteな問題をすぐ局所修正せず、

> **なぜその問題が成立したのか**

まで一般化することが重要である。

第二に、すべての問題をAIエージェントへ判断させない。

既知の判断はdeterministic mechanismへ移す。

第三に、deterministic mechanismですべての安全性を保証できると考えない。

定義されていない問題はModel Reviewで探索する必要がある。

第四に、reviewとassuranceを混同しない。

> Reviews improve the model; assurance establishes conformance.

第五に、具体化と適合を混同しない。

> C = T(A) does not imply C ⊨ A.

第六に、security controlそのものだけでなく、

> **誰がそのcontrolを変更できるのか**

というauthorityを設計する。

第七に、複雑なsecurity mechanismは、それ自身がattack surfaceやoperational riskになる。

必要以上に構成要素を増やさず、IAM、Sandbox、Policy、external enforcementの責務を分離する。

第八に、AIエージェントによる発見を一回限りの知見で終わらせない。

安定した知識は、可能な限り決定的な仕組みへ昇格させる。

---

## 37. 現時点で未解決・今後深化すべき点

RAEMは完成された閉じた理論ではない。

形成過程で、今後さらに検討すべき問題も残っている。

例えば、

- Refinement ModelとRefinement Processをどこまで分けるか
- Assumption / Evaluation Contextを形式モデルへどう含めるか
- Abstract ModelからEvidenceまでのbidirectional traceability
- Findingをdeterministic ruleへ昇格させる基準
- Assurance Engine自身のtrustworthiness
- verifier regressをどこで止めるか
- CoreからExtendedへのmaturity判定主体
- ExtendedからCoreへ戻すdowngrade条件
- Assuranceのscopeとconfidenceをどう表現するか
- Principleをどこまでdeterministic claimへ変換すべきか
- AIエージェント自身によるRAEM改善提案のgovernance
- RAEMと既存のassurance case、formal refinement、CEGAR、runtime assurance等との関係

などである。

これらはRAEMの欠陥というより、

> **現在のRAEM適用体系ではまだ完全に決定的に扱えない領域**

である。

したがって、これら自身が今後のModel ReviewとEvolutionの対象になる。

---

## 38. 結論

RAEMは、最初から理論として設計されたものではない。

自律型AIエージェントを安全に実運用するために、

- Hooks
- Sandbox
- Policy
- IAM
- SCM protection
- Repository Posture
- Architecture Gate

を設計し、その具体的実装を厳しくレビューした結果、

> **既知の問題と未知の問題では、AIエージェントへ与える役割を変える必要がある**

という問題へ到達した。

そこから、

```text
Known knowledge
→ Deterministic system

Unknown problem
→ Human / AI exploration
```

という責務分離が生まれた。

そして、

```text
探索
↓
発見
↓
一般化
↓
具体化
↓
根拠
↓
適合保証
↓
さらに探索
```

という循環が、

**Refinement, Assurance and Evolution Model**

として整理された。

RAEMの形成過程で最も重要だったのは、AIエージェントをどう制限するかを考え続けた結果、

> **AIエージェントをどこで自由にすべきか**

という問いへ反転したことである。

決定的な仕組みの役割は、AIエージェントの能力を閉じ込めることではない。

既知の危険、既知の判断、既知の制約を引き受けることで、

> **AIエージェントを、未知を発見し、現在の体系そのものを進化させる仕事へ解放すること**

にある。

この反転が、Agent Harnessの設計からRAEMへ至った議論の中核である。
