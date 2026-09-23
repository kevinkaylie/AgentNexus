# RFC-002 Review: What May a Receiver Request—and What Does the Evidence Prove?

**RFC-002 评审：接收方可以请求什么，证据又能证明什么？**

This is the canonical community review thread for
[RFC-002 — Metadata Requirements and Evidence Exchange, Draft v0.1](https://github.com/kevinkaylie/AgentNexus/blob/main/specs/rfcs/002-metadata-requirements-and-evidence-exchange.md).

RFC-002 defines receiver-driven Metadata Requirements and structured Evidence
exchange. The current Draft lists RFC-000 and RFC-001 Part B as normative
dependencies. RFC-001 Part B supplies identity control and issuer resolution
for most security-sensitive proof profiles. Whether every RFC-002 exchange
must depend on it—or whether equivalent issuer-resolution profiles and
explicitly unresolved or self-asserted exchanges may conform—is an explicit
review question below.

The governing boundary is:

> The receiver determines what it needs. The sender determines what it is
> willing and able to disclose. The protocol standardizes the negotiation and
> its Evidence; it does not force agreement or make the receiver's trust
> decision.

RFC-002 standardizes how Requirements, Claims, Evidence, Decision Packages,
bindings, response statuses, and Verification Results are expressed. It does
not define which Evidence is sufficient, which issuers are trusted, whether a
Claim is true in the relevant domain, or whether Permission should be granted.

## Why this RFC exists

After an Agent establishes control of an identifier, a receiver may still
need context-specific information before continuing:

- Which Principal does the Agent represent for this action?
- Is a claimed capability self-asserted or independently assessed?
- Is the Agent authorized to act on a resource or artifact?
- Which issuer made each Claim, and is the Evidence current and correctly
  bound?
- What information is the sender willing to disclose for the stated purpose?
- Which checks succeeded, failed, or could not be completed?

A single fixed credential set cannot answer every receiver, action, resource,
and risk context. A universal Trust Score cannot safely replace those
questions either.

RFC-002 therefore defines a negotiation:

```text
Initiator
  → Collaboration Intent

Receiver
  → Metadata Requirements

Evidence Presenter
  → Requirement Responses + Decision Package

Receiver
  → Parse → Verify → Local Policy Evaluation
  → requirements accepted
     | additional requirements
     | conditionally accepted
     | rejected
```

The result applies only to the referenced Intent and Requirements exchange.

## The objects under review

### Collaboration Intent

The Intent identifies the proposed Agent, Principal where relevant, receiver,
objective or action, resource or artifact, purpose, constraints, validity,
correlation references, and proof of origin when required.

Natural language may explain the request, but it must not be the only
representation of a security-critical action, subject, resource, purpose, or
validity period.

### Metadata Requirements

The receiver publishes a versioned, attributable, time-bounded projection of
what it needs for this Intent. It does not have to reveal its private Policy,
weights, fraud rules, blocklists, model internals, or human-review logic.

Each Requirement Item can define:

- target subject and requested Claim or Evidence schema;
- `required`, `optional`, or `advisory` criticality;
- accepted formats, issuer classes, or proof properties;
- freshness, expiry, and revocation behavior;
- subject, audience, action, resource, artifact, Intent, and Session bindings;
- cardinality and `all_of`, `any_of`, or alternative satisfaction paths;
- selective disclosure and derived-proof support;
- purpose, retention, and onward-disclosure constraints.

The receiver should reveal enough for an honest presenter to construct an
interoperable response.

### Requirement Responses

The presenter answers every required Requirement Item using a defined status:

```text
satisfied
partially_satisfied
unavailable
declined
unsupported
not_applicable
```

In the current Draft, `satisfied` is a presenter-declared response status. It
means that the presenter claims to have supplied material intended to satisfy
the Requirement Item. It is not a Verification Result and does not mean that
the receiver has accepted the Evidence or Requirement. The review should
consider whether the term needs stronger role scoping or a less ambiguous name
such as `claimed_satisfied`.

These meanings must remain distinct. A presenter that cannot obtain Evidence,
chooses not to disclose it, or cannot process the Requirement is not the same
as a presenter that supplied Evidence which later failed verification.

### Evidence Items

An Evidence Item identifies the Claims covered by its proof, along with the
issuer, subject, source, provenance, presenter, proof method, validity,
revocation, context bindings, payload or immutable reference, and disclosure
limitations.

RFC-002 permits first-party, third-party, locally observed, and derived
Evidence. These classes must not be silently collapsed:

- a valid self-assertion proves authorship and integrity, not independent
  corroboration;
- third-party Evidence preserves the original issuer and proof;
- an exported local observation becomes Evidence issued by the observer;
- a derived assessment identifies its evaluator, method, inputs, context,
  limitations, and validity.

### Decision Package

Despite its name, a **Decision Package is not a Decision**. It is the
presenter's input package for a decision the receiver may make later. Whether
the name should change—for example, to make its response role more
obvious—is part of this review.

The package is the presenter's complete response to one exact Requirements
version. For a security-sensitive exchange, its proof should bind the
Requirement Responses and Evidence set to the presenter, receiver, Intent,
Requirements identifier and hash, nonce, payload or artifact, and validity
period.

This prevents a valid package from being transplanted into another receiver,
Intent, artifact, or Requirements set.

Package completeness and Evidence validity remain separate. A package can
answer every required item while containing Evidence that later fails
verification.

### Verification Result

A Verifier produces structured results for syntax, proof, issuer control,
subject, audience, Intent, artifact, freshness, expiry, revocation, replay,
unsupported critical fields, warnings, and unavailable checks.

A single `valid: true` is insufficient. Verification must preserve which
checks passed, failed, or remained indeterminate so that the receiver can
apply local Policy.

## Eight separations RFC-002 must preserve

```text
Requirement             ≠ Policy
Claim                   ≠ Evidence
Presenter `satisfied`   ≠ Evidence verified or receiver accepted
Decision Package        ≠ Receiver Decision
Evidence validity       ≠ domain truth
Package complete        ≠ Evidence valid
`requirements_accepted` ≠ globally trusted
`requirements_accepted` ≠ Permission granted or Session established
```

### Requirement is not private Policy

A Requirement is the disclosed condition for this exchange. Policy is the
receiver-local logic that generated Requirements and evaluates the result.
Interoperability requires usable Requirements, not disclosure of the
receiver's entire decision system.

### Claim is not Evidence

A Claim is an assertion. Evidence carries information, provenance, proof, and
context that may support one or more Claims. A valid proof establishes defined
protocol facts; it does not guarantee the Claim's factual truth or sufficiency
for the receiver.

### Decision Package is input, not a Decision

The presenter assembles the Package; the receiver consumes it. Package fields
and presenter response statuses must not impersonate the receiver's Policy
output. Receiver-facing protocol signals are produced only after verification
and local evaluation.

### Verification is not evaluation

The Verifier checks protocol-verifiable properties. The receiver's Policy
decides whether the result is sufficient, should be constrained, needs human
review, or should be rejected.

### Acceptance is not authorization

`requirements_accepted` means only that the receiver considers this package
sufficient to continue to the next protocol step. It does not grant
Permission, establish a Collaboration Session, accept a business result, or
create global trust.

## Receiver-driven does not mean unlimited disclosure

A receiver may ask, but the presenter must be able to decline, minimize,
selectively disclose, use an accepted alternative, or propose a constraint.

Sensitive Requirements should state their purpose and retention behavior.
Profiles should support field-level disclosure, derived predicates, redacted
credentials, immutable references, alternative Evidence, and authorized
manual review.

The protocol must not be used to demand chain-of-thought, hidden model
reasoning, secrets, unrelated collaboration history, or excessive personal,
organizational, or behavioral data.

Negotiation should also be bounded by rounds, package size, Evidence count,
reference depth, verification work, and expiry. Neither party is required to
continue an unbounded negotiation.

## How should existing credential and attestation formats map to Evidence?

Agent ecosystems already use verifiable credentials, JWT attestations,
certificates, signed profiles, platform observations, risk assessments,
reputation values, audit records, and outcome Receipts.

This review should clarify whether each external format is:

- a native Evidence Item profile;
- an immutable payload carried by an Evidence Item envelope;
- an external reference with a content hash and authorization rules;
- or input to a distinct derived Evidence assessment.

A mapping must preserve the original issuer, subject, presenter, source,
proof, schema and method version, context, time, revocation or status,
limitations, and transformation steps. An intermediary must not replace the
original issuer unless it is issuing a separate derived assessment.

Existing `trust_score`, `trust_delta`, certification level, ranking, or grade
fields remain Claims issued by a named evaluator. They must not be converted
automatically into universal trust, Permission, or spending limits.

Contributors using formats such as Giskard certifications, OATR JWT
attestations, external credential profiles, or platform-specific reputation
records are invited to identify lossless mappings and semantic mismatches.

## Roles and conformance boundaries

RFC-002 defines the following protocol roles:

- **Initiator**
- **Requirements Issuer**
- **Evidence Presenter**
- **Evidence Issuer**
- **Evidence Subject**
- **Verifier**
- **Receiver Policy Decision Point**

The Receiver Policy Decision Point's internal Policy, thresholds, and
decision algorithm remain outside the normative evidence-exchange logic.
RFC-002 does standardize the protocol-visible signals emitted after local
evaluation—`requirements_accepted`, `additional_requirements`,
`conditionally_accepted`, `rejected`, `expired`, and `cancelled`—and scopes
them to the related Intent and Requirements exchange. The protocol defines how
the result is communicated, not the private reasoning that selected it.

The current Draft defines conformance requirements for:

1. **Requirements Issuer**
2. **Evidence Presenter**
3. **Verifier**
4. **Decision Package Profile**

The review should test whether these conformance boundaries are sufficient.
In particular, should Evidence Issuers or schema and registry operators have
separate obligations for issuer identity, Claim coverage, status,
revocation, correction, privacy, and test vectors?

## Is RFC-001 Part B a universal dependency?

The dependency is straightforward when a Verifier must establish control of
the presenter, package issuer, or Evidence issuer identity. RFC-001 Part B
provides Identity Resolution, authorized Verification Methods, purpose
binding, status, rotation, and Proof of Control.

The boundary is less obvious for:

- closed systems using pre-established local identities;
- transport-authenticated exchanges such as mutually authenticated channels;
- anonymous or pseudonymous disclosure;
- explicitly self-asserted or unsigned material;
- proof profiles with their own issuer-resolution method.

RFC-002 itself allows issuer identifiers and Verification Methods to be
resolved under RFC-001 Part B **or an explicitly defined issuer-resolution
profile**. The review should therefore decide whether RFC-001 Part B is:

1. mandatory for every base RFC-002 conformance claim;
2. mandatory only for security-sensitive or signed proof profiles;
3. replaceable by an equivalent, explicitly defined issuer-resolution
   profile.

Whichever model is chosen, an implementation must not report proof or issuer
control as verified when it was not established. Unresolved, self-asserted,
transport-authenticated, and cryptographically verified states must remain
distinguishable.

## How to participate

You may review one object, one role, one Evidence format, or the full
negotiation. Concrete Requirement sets, credential mappings, Decision
Packages, Verification Results, traces, fixtures, and negative tests are
especially useful.

### Three core questions

1. **Scenario and Requirement:** What action is proposed, and what minimum
   Requirement should the receiver disclose for that specific context?
2. **Evidence boundary:** Which Claims may the presented Evidence support, and
   what must the receiver not infer from the Evidence, a presenter-declared
   `satisfied` status, or the Decision Package?
3. **Interoperability test:** What minimum cross-implementation exchange or
   negative test would demonstrate that Requirements, responses, a Decision
   Package, and structured Verification Results interoperate without
   standardizing local Policy?

### Go deeper

4. Do purpose, retention, alternatives, decline, selective disclosure, and
   bounded negotiation provide enough protection against metadata fishing and
   Policy probing?
5. How should an existing credential or attestation format map to an Evidence
   Item, and should Evidence Issuer or registry conformance be defined
   separately?
6. Should RFC-001 Part B be a universal dependency, a proof-profile
   dependency, or replaceable by an equivalent issuer-resolution profile?
   Which identity, audience, Intent, artifact, freshness, and revocation
   bindings remain mandatory in each case?

You can reply using this short format:

```markdown
### Core

- **Scenario, action, and disclosed Requirement:**
- **Supported Claim and prohibited inference:**
- **Required interoperability exchange or negative test:**

### Optional

- **Disclosure, purpose, retention, or negotiation feedback:**
- **External Evidence mapping or issuer-role feedback:**
- **Identity dependency, binding, lifecycle, or multi-party feedback:**

### References

- **Requirement set, schema, credential, package, trace, fixture, or test:**
```

Focused objections and incomplete answers are welcome. Please cite a section
number when commenting on specific normative text.

Use this thread for RFC-002 semantics that must remain consistent across
Requirement, Evidence, package, and verification implementations. Exact JSON
field names, canonical serialization, proof suite selection, registry APIs,
transport endpoints, and product-specific trust algorithms should be
developed in the relevant profile, binding, implementation Issue, or focused
sub-discussion unless they expose a flaw in RFC-002's shared semantics.

## Questions delegated to profiles and more specific RFC work

RFC-002 identifies open decisions including:

### Evidence and package profiles

- baseline canonical serialization and proof suites;
- Evidence-schema and Requirement-type registries;
- baseline selective-disclosure formats;
- authorization and retrieval of confidential Evidence references.

### Privacy, signaling, and operational limits

- machine-readable retention enforcement versus declared obligations;
- which Verification Result fields can be shared without Policy probing;
- participant-specific Requirements in multi-party collaboration;
- recommended package size, reference depth, and negotiation-round limits.

These questions belong in this review when they affect RFC-002's shared
semantics or conformance boundaries. Concrete encodings, registries,
cryptographic profiles, transport mappings, and implementation defaults
should be resolved by the workstream that owns them.

## Relationship to the ACF RFC family

[RFC-000](https://github.com/kevinkaylie/AgentNexus/blob/main/specs/rfcs/000-agent-collaboration-framework.md)
defines the constitutional boundary between Evidence and receiver-local trust
decisions. Its
[canonical review discussion](https://github.com/kevinkaylie/AgentNexus/discussions/4)
is the right place to challenge that framework-level separation.

[RFC-001](https://github.com/kevinkaylie/AgentNexus/blob/main/specs/rfcs/001-agent-discovery-and-identity.md)
establishes Agent identity control and issuer resolution. Its
[canonical review discussion](https://github.com/kevinkaylie/AgentNexus/discussions/5)
is the right place to review Discovery, Identity Methods, and Proof of
Control.

RFC-003 will define Capability, Permission, Authority, Delegation, and
constraints. RFC-004 will establish Collaboration Sessions after local
evaluation and negotiation.

The broader use-case discussion
[What Must a Stranger Agent Prove Before You Let It Act?](https://github.com/kevinkaylie/AgentNexus/discussions/2)
is collecting scenarios that may challenge several RFCs at once. This thread
is specifically for reviewing receiver-driven Requirements and Evidence
exchange.

## How this review will be resolved

Maintainers will summarize:

- supported object, role, binding, privacy, and conformance decisions;
- objections, counterexamples, and security or privacy risks;
- proposed RFC changes or tracked Issues;
- credential mappings, schemas, fixtures, test vectors, and implementations;
- unresolved dissent.

Votes indicate interest, not protocol truth. Material conclusions will be
linked to the relevant RFC change, Issue, Pull Request, profile, or experiment.

Comments in English or Chinese are welcome.

_This discussion prompt was prepared with Agent assistance and is published
under maintainer responsibility._

---

<details>
<summary><strong>中文版</strong></summary>

这是
[RFC-002：Metadata Requirements and Evidence Exchange，Draft v0.1](https://github.com/kevinkaylie/AgentNexus/blob/main/specs/rfcs/002-metadata-requirements-and-evidence-exchange.md)
的正式社区评审主帖。

RFC-002 定义由接收方驱动的 Metadata Requirements 与结构化 Evidence 交换。
当前草案将 RFC-000 和 RFC-001 Part B 列为规范性依赖。RFC-001 Part B 为多数
安全敏感的 Proof Profile 提供 Identity Control 与 Issuer Resolution。每一次
RFC-002 交换是否都必须依赖它，或者等价的 Issuer-resolution Profile 以及明确
标记为未解析或自我声明的交换也可以合规，是本次评审需要明确回答的问题。

治理边界是：

> 接收方决定自己需要什么；发送方决定愿意且能够披露什么。协议标准化协商及其
> Evidence，但不强迫双方达成一致，也不替接收方作出信任决定。

RFC-002 标准化 Requirements、Claims、Evidence、Decision Packages、上下文绑定、
响应状态和 Verification Results 的表达方式。它不规定哪些 Evidence 足够、哪些
Issuer 可信、Claim 在相关领域中是否为真，或是否应该授予 Permission。

## 为什么需要 RFC-002

Agent 建立对一个标识符的控制后，接收方在继续协作前仍可能需要与上下文相关的
信息：

- Agent 在本次行动中代表哪个 Principal？
- 声明的 Capability 是自我声明还是经过独立评估？
- Agent 是否被授权操作某项资源或产物？
- 每项 Claim 由哪个 Issuer 提出，Evidence 是否仍然有效并正确绑定？
- 发送方愿意为声明的 Purpose 披露哪些信息？
- 哪些检查成功、失败或无法完成？

固定的一组 Credential 无法回答所有接收方、行动、资源和风险上下文的问题。
通用 Trust Score 也不能安全地替代这些问题。

因此 RFC-002 定义了以下协商：

```text
Initiator
  → Collaboration Intent

Receiver
  → Metadata Requirements

Evidence Presenter
  → Requirement Responses + Decision Package

Receiver
  → Parse → Verify → Local Policy Evaluation
  → requirements accepted
     | additional requirements
     | conditionally accepted
     | rejected
```

结果只适用于被引用的 Intent 与 Requirements 交换。

## 本次评审的协议对象

### Collaboration Intent

Intent 标识提议参与的 Agent、相关 Principal、接收方、目标或行动、资源或产物、
Purpose、Constraints、有效期、关联引用，以及在需要时提供来源 Proof。

自然语言可以解释请求，但不能成为安全关键行动、Subject、Resource、Purpose 或
有效期的唯一表达。

### Metadata Requirements

接收方发布一个有版本、可归因、有时限的对象，作为它针对本次 Intent 所需信息的
公开投影。它不必公开私有 Policy、权重、反欺诈规则、Blocklist、模型内部信息或
人工评审逻辑。

每个 Requirement Item 可以定义：

- 目标 Subject 与请求的 Claim 或 Evidence Schema；
- `required`、`optional` 或 `advisory` Criticality；
- 接受的格式、Issuer 类别或 Proof 属性；
- 新鲜度、过期和撤销行为；
- Subject、Audience、Action、Resource、Artifact、Intent 和 Session 绑定；
- Cardinality 以及 `all_of`、`any_of` 或替代满足路径；
- 选择性披露和 Derived Proof 支持；
- Purpose、Retention 与后续披露约束。

接收方应该披露足够信息，让诚实的 Presenter 能够构造可互操作响应。

### Requirement Responses

Presenter 必须使用定义好的状态回答每一个必答 Requirement Item：

```text
satisfied
partially_satisfied
unavailable
declined
unsupported
not_applicable
```

在当前草案中，`satisfied` 是由 Presenter 声明的响应状态。它表示 Presenter
声称自己已经提供了用于满足该 Requirement Item 的材料；它不是 Verification
Result，也不表示接收方已经接受 Evidence 或 Requirement。本次评审应考虑是否
需要更明确地标注角色，或改用 `claimed_satisfied` 等不易误解的名称。

这些含义必须保持独立。Presenter 无法获得 Evidence、选择不披露或无法处理
Requirement，与它提供了后来验证失败的 Evidence 并不是同一件事。

### Evidence Items

Evidence Item 标识 Proof 覆盖的 Claims，以及 Issuer、Subject、Source、
Provenance、Presenter、Proof Method、有效期、撤销、上下文绑定、Payload 或
不可变引用和披露限制。

RFC-002 允许第一方、第三方、本地观察和派生 Evidence，不能暗中混为一类：

- 有效的自我声明证明作者身份和完整性，不代表独立佐证；
- 第三方 Evidence 保留原始 Issuer 和 Proof；
- 本地观察被导出后，成为由 Observer 签发的 Evidence；
- 派生评估标明 Evaluator、Method、输入、Context、限制和有效期。

### Decision Package

尽管名称中包含 Decision，**Decision Package 并不是 Decision**。它是 Presenter
提供给接收方、供接收方随后作出决定的输入包。是否应该修改名称，使其响应包角色
更明显，也是本次评审的一部分。

这个 Package 是 Presenter 对一个确定 Requirements 版本的完整响应。在安全敏感
的交换中，其 Proof 应将 Requirement Responses 与 Evidence Set 绑定到
Presenter、Receiver、Intent、Requirements Identifier 与 Hash、Nonce、Payload
或 Artifact 以及有效期。

这可以防止有效 Package 被移植到另一个 Receiver、Intent、Artifact 或
Requirements Set。

Package 完整性与 Evidence 有效性保持独立。Package 可以回答全部必答项，但其中
包含的 Evidence 仍可能验证失败。

### Verification Result

Verifier 为语法、Proof、Issuer Control、Subject、Audience、Intent、Artifact、
新鲜度、过期、撤销、重放、不支持的关键字段、Warning 和无法完成的检查产生
结构化结果。

单个 `valid: true` 不足以支持本地 Policy。验证必须保留哪些检查通过、失败或
无法确定，让接收方据此应用本地 Policy。

## RFC-002 必须保持的八项区分

```text
Requirement             ≠ Policy
Claim                   ≠ Evidence
Presenter 的 `satisfied` ≠ Evidence 已验证或接收方已接受
Decision Package        ≠ Receiver Decision
Evidence 有效           ≠ 领域事实
Package 完整            ≠ Evidence 有效
`requirements_accepted` ≠ 全局可信
`requirements_accepted` ≠ 已授予 Permission 或已建立 Session
```

### Requirement 不等于私有 Policy

Requirement 是本次交换中被披露的条件。Policy 是接收方用于生成 Requirements
并评估结果的本地逻辑。互操作需要可使用的 Requirements，而不是公开接收方的
完整决策系统。

### Claim 不等于 Evidence

Claim 是一项声明。Evidence 携带可支持一项或多项 Claims 的信息、Provenance、
Proof 与 Context。有效 Proof 证明定义好的协议事实，但不保证 Claim 符合领域
事实或足以满足接收方。

### Decision Package 是输入，不是 Decision

Package 由 Presenter 组装，Receiver 负责使用。Package 字段和 Presenter 的响应
状态不得冒充 Receiver 的 Policy 输出。只有在验证和本地评估之后，才会产生面向
协议对端的接收方信号。

### Verification 不等于 Evaluation

Verifier 检查可由协议验证的属性。接收方 Policy 决定结果是否足够、是否需要
限制、人工评审或拒绝。

### Acceptance 不等于 Authorization

`requirements_accepted` 只表示接收方认为这个 Package 足以继续下一协议步骤。
它不授予 Permission、不建立 Collaboration Session、不接受业务结果，也不创建
全局信任。

## Receiver-driven 不等于无限披露

接收方可以提出请求，但 Presenter 必须能够拒绝、最小化披露、选择性披露、使用
可接受的替代路径或提出约束。

敏感 Requirements 应说明 Purpose 和 Retention。Profile 应支持字段级披露、
派生谓词、脱敏 Credential、不可变引用、替代 Evidence 和经过授权的人工评审。

协议不得被用于索取思维链、隐藏模型推理、秘密、无关协作历史，或过量的个人、
组织及行为数据。

协商还应该限制轮次、Package 大小、Evidence 数量、引用深度、验证工作量和有效期。
任何一方都不必继续无界协商。

## 现有 Credential 与 Attestation 格式应如何映射到 Evidence？

Agent 生态已经使用 Verifiable Credential、JWT Attestation、Certificate、
Signed Profile、平台观察、风险评估、Reputation Value、Audit Record 和 Outcome
Receipt。

本次评审应明确每种外部格式属于哪种关系：

- 原生 Evidence Item Profile；
- 由 Evidence Item Envelope 携带的不可变 Payload；
- 带 Content Hash 和授权规则的外部引用；
- 或用于产生独立 Derived Evidence Assessment 的输入。

映射必须保留原始 Issuer、Subject、Presenter、Source、Proof、Schema 与 Method
Version、Context、Time、Revocation 或 Status、限制以及转换步骤。Intermediary
不得替换原始 Issuer，除非它正在签发一项独立的派生评估。

现有 `trust_score`、`trust_delta`、Certification Level、Ranking 或 Grade 字段
仍然是由具体 Evaluator 签发的 Claims。它们不能被自动转换为通用信任、
Permission 或 Spending Limit。

使用 Giskard Certification、OATR JWT Attestation、外部 Credential Profile 或
平台特定 Reputation Record 的贡献者，可以帮助识别无损映射和语义差异。

## 角色与合规边界

RFC-002 定义以下协议角色：

- **Initiator**
- **Requirements Issuer**
- **Evidence Presenter**
- **Evidence Issuer**
- **Evidence Subject**
- **Verifier**
- **Receiver Policy Decision Point**

Receiver Policy Decision Point 的内部 Policy、Threshold 和 Decision Algorithm
保持在规范性 Evidence Exchange 逻辑之外。RFC-002 会标准化本地评估后向协议
对端输出的信号，包括 `requirements_accepted`、`additional_requirements`、
`conditionally_accepted`、`rejected`、`expired` 和 `cancelled`，并将它们限定
在相关 Intent 与 Requirements Exchange。协议规定结果如何传达，但不规定选择
该结果的私有决策逻辑。

当前草案为以下角色或 Profile 定义了合规要求：

1. **Requirements Issuer**
2. **Evidence Presenter**
3. **Verifier**
4. **Decision Package Profile**

本次评审需要检验这些合规边界是否足够。尤其需要讨论：Evidence Issuer 或 Schema
与 Registry Operator 是否应该拥有独立的合规义务，包括 Issuer Identity、Claim
Coverage、Status、Revocation、Correction、Privacy 和测试向量？

## RFC-001 Part B 是否是通用依赖？

当 Verifier 必须建立 Presenter、Package Issuer 或 Evidence Issuer 的身份控制权
时，这项依赖很直接。RFC-001 Part B 提供 Identity Resolution、获得授权的
Verification Method、Purpose Binding、Status、Rotation 和 Proof of Control。

但以下场景的边界并不明显：

- 使用预先建立的本地身份的封闭系统；
- 通过双向认证信道完成传输身份验证的交换；
- 匿名或假名披露；
- 明确标记为自我声明或未签名的材料；
- 自带 Issuer-resolution Method 的 Proof Profile。

RFC-002 本身允许通过 RFC-001 Part B **或明确规定的 Issuer-resolution Profile**
解析 Issuer Identifier 和 Verification Method。因此，本次评审需要判断
RFC-001 Part B 属于：

1. 所有 RFC-002 基础合规声明的强制依赖；
2. 仅安全敏感或已签名 Proof Profile 的强制依赖；
3. 可以由等价且明确规定的 Issuer-resolution Profile 替代的依赖。

无论选择哪种模型，实现都不得在没有建立相应事实时报告 Proof 或 Issuer Control
已验证。未解析、自我声明、传输已认证和密码学已验证等状态必须保持可区分。

## 如何参与

你可以只评审一个对象、一个角色、一种 Evidence 格式或完整协商。具体 Requirement
Set、Credential Mapping、Decision Package、Verification Result、Trace、Fixture
与负向测试尤其有价值。

### 三个核心问题

1. **场景与 Requirement：** 提议执行什么行动？接收方针对该上下文至少应该披露
   什么 Requirement？
2. **Evidence 边界：** 提供的 Evidence 可以支持哪些 Claims？接收方不得从
   Evidence、Presenter 声明的 `satisfied` 状态或 Decision Package 中推导出
   什么？
3. **互操作测试：** 至少需要什么跨实现交换或负向测试，才能证明 Requirements、
   Responses、Decision Package 与结构化 Verification Results 可以互操作，同时
   不标准化本地 Policy？

### 进阶问题

4. Purpose、Retention、Alternatives、Decline、Selective Disclosure 和有界协商，
   是否足以防止 Metadata Fishing 与 Policy Probing？
5. 现有 Credential 或 Attestation 格式应该如何映射到 Evidence Item？是否需要
   单独定义 Evidence Issuer 或 Registry 的合规要求？
6. RFC-001 Part B 应该是通用依赖、Proof Profile 依赖，还是可以由等价的
   Issuer-resolution Profile 替代？每种情况下哪些 Identity、Audience、Intent、
   Artifact、新鲜度和撤销绑定仍然必须存在？

可以使用下面的简短格式回复：

```markdown
### 核心

- **场景、行动及公开 Requirement：**
- **支持的 Claim 与禁止的推导：**
- **需要的互操作交换或负向测试：**

### 可选

- **披露、Purpose、Retention 或协商反馈：**
- **外部 Evidence 映射或 Issuer 角色反馈：**
- **身份依赖、绑定、生命周期或多方反馈：**

### 参考材料

- **Requirement Set、Schema、Credential、Package、Trace、Fixture 或测试：**
```

聚焦单个问题或只回答部分问题同样欢迎。对具体规范文本发表评论时，请尽量标注
章节编号。

本帖用于讨论不同 Requirement、Evidence、Package 和 Verification 实现必须保持
一致的 RFC-002 语义。具体 JSON 字段命名、规范序列化、Proof Suite 选择、
Registry API、Transport Endpoint 和产品特定 Trust Algorithm，应该进入对应
Profile、Binding、实现 Issue 或聚焦子讨论；除非它们揭示了 RFC-002 共享语义
本身的问题。

## 交由 Profile 和更具体 RFC 工作处理的问题

RFC-002 识别的开放决定包括：

### Evidence 与 Package Profile

- 基线 Canonical Serialization 与 Proof Suite；
- Evidence Schema 与 Requirement Type Registry；
- 基线 Selective Disclosure 格式；
- 机密 Evidence Reference 的授权与获取。

### 隐私、信号和运行限制

- 机器可读的 Retention Enforcement 与声明式义务之间的选择；
- 哪些 Verification Result 字段可以共享且不会导致 Policy Probing；
- 多方协作中的参与方特定 Requirements；
- 推荐的 Package 大小、Reference Depth 和 Negotiation Round 限制。

这些问题影响 RFC-002 的共享语义或合规边界时，应当进入本次评审。具体编码、
Registry、密码学 Profile、Transport Mapping 和实现默认值，应在负责它们的
工作流中收敛。

## 与 ACF RFC 家族的关系

[RFC-000](https://github.com/kevinkaylie/AgentNexus/blob/main/specs/rfcs/000-agent-collaboration-framework.md)
定义 Evidence 与接收方本地信任决定之间的宪法边界。若要挑战框架层区分，请进入
其
[正式评审主帖](https://github.com/kevinkaylie/AgentNexus/discussions/4)。

[RFC-001](https://github.com/kevinkaylie/AgentNexus/blob/main/specs/rfcs/001-agent-discovery-and-identity.md)
建立 Agent Identity Control 与 Issuer Resolution。若要评审 Discovery、
Identity Method 和 Proof of Control，请进入其
[正式评审主帖](https://github.com/kevinkaylie/AgentNexus/discussions/5)。

RFC-003 将定义 Capability、Permission、Authority、Delegation 和 Constraints。
RFC-004 将在本地评估与协商后建立 Collaboration Session。

跨 RFC 场景讨论
[在允许陌生 Agent 参与任务前，它至少需要证明什么？](https://github.com/kevinkaylie/AgentNexus/discussions/2)
正在收集可能同时影响多篇 RFC 的场景；本帖只聚焦接收方驱动的 Requirements 与
Evidence Exchange。

## 本次评审如何收口

维护者将总结：

- 获得支持的对象、角色、绑定、隐私和合规决定；
- 反对意见、反例以及安全或隐私风险；
- 建议的 RFC 修改或已追踪 Issue；
- Credential Mapping、Schema、Fixture、测试向量和实现；
- 尚未形成共识的分歧。

投票只代表关注度，不代表协议真理。重要结论会链接到相关 RFC 修改、Issue、
Pull Request、Profile 或实验。

欢迎使用中文或英文参与。

_本讨论引导内容由 Agent 协助起草，并由维护者对发布内容负责。_

</details>
