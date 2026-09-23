# RFC-000 Review: What Should an Agent Collaboration Framework Standardize?

**RFC-000 评审：Agent 协作框架应该标准化什么？**

This is the canonical community review thread for
[RFC-000 — Agent Collaboration Framework Architecture, Draft v0.3](https://github.com/kevinkaylie/AgentNexus/blob/main/specs/rfcs/000-agent-collaboration-framework.md).

RFC-000 is the constitution of the Agent Collaboration Framework (ACF)
family. It defines the boundaries that later RFCs must preserve; it does not
yet define a complete wire protocol.

The central trust-boundary proposition is:

> **The framework standardizes evidence exchange, not trust decisions.**

We are asking agent builders, protocol designers, identity and governance
providers, security researchers, and users of agent systems to challenge that
boundary before more of the protocol family is built on top of it.

## Why this RFC exists

Delivering a message from Agent A to Agent B is not the same as establishing a
collaboration relationship.

Independent agents also need to determine:

- who is participating and which Principal an Agent represents;
- which claims are supported by verifiable, current, and context-bound
  Evidence;
- what the Agent can do, what it is permitted to do, and where its Authority
  comes from;
- what the receiver requires before accepting a proposed action;
- when a Collaboration Session begins, changes, or ends;
- how tasks, artifacts, outcomes, and disputes remain attributable and
  auditable.

RFC-000 proposes that these are shared collaboration semantics. They should
work across runtimes and transports without requiring every participant to
use the same agent framework, identity system, trust provider, or policy.

## The boundary under review

ACF proposes to standardize:

- transport-independent collaboration objects and state transitions;
- discovery, identity-establishment, and proof-of-control semantics;
- receiver-authored Metadata Requirements and Evidence exchange;
- distinct semantics for Capability, Permission, Authority, and Delegation;
- bounded Collaboration Sessions;
- task, event, artifact, outcome, Receipt, correction, revocation, and
  dispute-signaling semantics;
- the context bindings and validation results needed for interoperable
  verification.

ACF explicitly does **not** propose to standardize:

- an Agent's model, reasoning, memory, planning, tools, or orchestration
  internals;
- a universal runtime, transport, Relay, Directory, registry, or identity
  authority;
- a universal trust or reputation score;
- domain policy for healthcare, finance, law, procurement, or other
  industries;
- the receiver's final decision about whether an action should be permitted;
- chain-of-thought, hidden reasoning, private memory, or model weights;
- legal liability or the domain truth of a signed claim.

Implementations and domain profiles may provide these functions, but RFC-000
says they must not be presented as universal ACF protocol truth.

## The proposed architecture in one view

RFC-000 organizes collaboration into seven semantic domains:

```text
D0  Discovery
  → D1  Identity
  → D2  Requirements and Evidence
  → D3  Capability and Authority
  → D4  Collaboration Session
  → D5  Coordination and Artifacts
  → D6  Outcome Records and Audit

Verified protocol objects
  → Receiver-local evaluation
  → Receiver-local enforcement
```

These are not mandatory network layers. A participant may reuse valid
Evidence or an existing Session, provided that doing so does not weaken
freshness, binding, authorization, or audit requirements.

The same collaboration may also use several transports. For example,
requirements may be exchanged over HTTP, tasks delivered through a queue,
tools exposed through MCP, and artifacts stored by content hash. Changing the
transport must not silently change identity, Authority, Session scope, or
audit continuity.

## Five separations RFC-000 treats as constitutional

### 1. Protocol facts are not domain decisions

A protocol can determine whether an object is well formed, a signature is
valid, an issuer controls a key, Evidence is correctly bound, or a state
transition is allowed.

It cannot determine whether a valid credential is sufficient for this
receiver, whether an Agent is competent for a task, whether an output is
factually correct, or whether an event creates legal liability.

### 2. Identity is not trust or authorization

Proof that an Agent controls an identifier does not prove uniqueness,
organizational representation, competence, permission, or trustworthiness.

### 3. Capability, Permission, and Authority are different

Capability describes what an Agent can do. Permission describes an allowed
action. Authority is the legitimate basis from which that Permission derives.
Capability alone must never imply authorization.

### 4. Verification is not evaluation or enforcement

RFC-000 separates:

```text
Parse → Verify → Evaluate → Enforce
```

A valid signature is a verification result. Whether to disclose information,
grant access, reduce scope, request more Evidence, involve a human, or reject
the action is a receiver-local decision.

### 5. Attributable records are not universal truth

A Receipt can prove who asserted what about an event or artifact. Its
signature does not by itself prove that the assertion is factually correct,
fair, or legally binding.

## How to participate

You do not need to review every section or agree with the current direction.
A concrete counterexample, conflicting protocol, implementation trace, threat
model, or missing distinction is especially useful.

### Three core questions

1. **Framework boundary:** What collaboration semantic must independent Agent
   implementations share, and what should remain outside ACF?
2. **Counterexample:** Which real scenario breaks, complicates, or contradicts
   the proposed separation between protocol Evidence and receiver-local trust
   decisions?
3. **Adoption test:** What minimum implementation results or
   cross-implementation demonstrations would make RFC-000 credible enough to
   serve as the constitution for more specific RFCs?

### Go deeper

4. Are any of the core distinctions—Agent/Principal, Claim/Evidence,
   Capability/Permission/Authority, Session/transport, Receipt/truth—wrong,
   incomplete, or impractical?
5. Do the seven domains and the proposed RFC-001 through RFC-008 split create
   clean implementation boundaries, or should responsibilities move?
6. Are the governance and Ratification criteria strong enough, especially the
   requirement for independent implementations, negative tests, and security
   review?

You can reply using this short format:

```markdown
### Core

- **Boundary I support or challenge:**
- **Scenario or counterexample:**
- **Adoption criteria and validation material:**

### Optional

- **Missing or problematic distinction:**
- **RFC/domain split feedback:**
- **Governance or Ratification feedback:**

### References

- **Implementation, specification, trace, test, or threat model:**
```

Focused objections and incomplete answers are welcome. Please cite a section
number when commenting on specific normative text.

Use this thread for constitutional boundaries, semantic distinctions, and the
division of responsibilities across the RFC family. Concrete mechanism
debates—such as which DID method to use, JSON field names, nonce encoding, or
Relay query APIs—belong in the relevant specific RFC or implementation Issue
unless they reveal a problem in RFC-000's architecture.

## Questions delegated to more specific RFCs

RFC-000 identifies several important questions without prescribing all of
their concrete mechanisms, including:

- baseline identity methods, canonical serialization, and proof suites;
- registries for Evidence and Receipt types;
- selective disclosure and zero-knowledge proof integration;
- multi-party requirements and participant-specific policy;
- Session resumption, liveness, revocation, and key rotation;
- privacy-preserving rejection reasons;
- the Evidence needed for independently auditable outcome Receipts.

Some of these questions are already partially addressed by RFC-001 or RFC-002.
They should inform the review of RFC-000's boundaries, while their detailed
semantics and mechanisms belong in the relevant specific RFCs.

## Relationship to current work

RFC-000 treats existing AgentNexus ADRs and code as implementation experience,
not as normative protocol sources. While RFC-000 remains a Draft, it does not
supersede those ADRs.

The currently published follow-on drafts are:

- [RFC-001 — Agent Discovery and Identity Establishment](https://github.com/kevinkaylie/AgentNexus/blob/main/specs/rfcs/001-agent-discovery-and-identity.md)
- [RFC-002 — Metadata Requirements and Evidence Exchange](https://github.com/kevinkaylie/AgentNexus/blob/main/specs/rfcs/002-metadata-requirements-and-evidence-exchange.md)

The broader use-case discussion
[What Must a Stranger Agent Prove Before You Let It Act?](https://github.com/kevinkaylie/AgentNexus/discussions/2)
is collecting scenarios that may challenge several RFCs at once. This thread
is specifically for deciding whether RFC-000 establishes the right
architecture and specification boundaries.

## How this review will be resolved

Maintainers will summarize:

- supported architectural boundaries;
- objections and counterexamples;
- proposed RFC changes or new tracked issues;
- interoperability experiments and evidence still needed;
- unresolved dissent.

Votes indicate interest, not protocol truth. Material conclusions will be
linked to the relevant RFC change, Issue, Pull Request, or experiment rather
than disappearing into comments.

Comments in English or Chinese are welcome.

_This discussion prompt was prepared with Agent assistance and is published
under maintainer responsibility._

---

<details>
<summary><strong>中文版</strong></summary>

这是
[RFC-000：Agent Collaboration Framework Architecture，Draft v0.3](https://github.com/kevinkaylie/AgentNexus/blob/main/specs/rfcs/000-agent-collaboration-framework.md)
的正式社区评审主帖。

RFC-000 是 Agent Collaboration Framework（ACF）RFC 家族的“宪法”。它规定
后续 RFC 必须保持的边界，但目前并不定义一套完整的线上协议。

核心信任边界主张是：

> **框架标准化证据交换，而不是替接收方做信任决定。**

在更多协议建立于这一原则之上以前，我们希望 Agent 开发者、协议设计者、身份与
治理服务方、安全研究者以及 Agent 系统用户共同挑战这条边界。

## 为什么需要 RFC-000

让 Agent A 把消息发送给 Agent B，并不等于双方已经建立了协作关系。

独立运营的 Agent 还需要回答：

- 谁在参与，Agent 在当前上下文中代表哪个 Principal；
- 哪些声明拥有可验证、有效且与上下文绑定的 Evidence；
- Agent 能做什么、被允许做什么，以及 Authority 来自哪里；
- 接收方在接受一次行动前要求什么；
- Collaboration Session 何时开始、变化和结束；
- 任务、产物、结果与争议如何保持可归因和可审计。

RFC-000 认为这些属于共享的协作语义。它们应该跨运行时和传输方式工作，而不要求
所有参与者使用同一种 Agent 框架、身份系统、信任服务或策略。

## 本次评审的边界

ACF 计划标准化：

- 与传输无关的协作对象和状态转换；
- 发现、身份建立和控制权证明语义；
- 由接收方声明的 Metadata Requirements 与 Evidence 交换；
- Capability、Permission、Authority 和 Delegation 的独立语义；
- 有明确边界的 Collaboration Session；
- 任务、事件、产物、结果、Receipt、更正、撤销和争议信号语义；
- 实现互操作验证所需的上下文绑定和验证结果。

ACF 明确不标准化：

- Agent 的模型、推理、记忆、规划、工具或编排内部实现；
- 通用运行时、传输协议、Relay、Directory、注册表或唯一身份权威；
- 全局通用的信任分或信誉分；
- 医疗、金融、法律、采购等领域策略；
- 接收方最终是否允许某次行动；
- 思维链、隐藏推理、私有记忆或模型权重；
- 法律责任，或“一个已签名声明在领域中必然为真”。

实现和领域 Profile 可以提供上述功能，但 RFC-000 要求不得将它们表述为 ACF
通用协议事实。

## 架构概览

RFC-000 将协作划分为七个语义域：

```text
D0  Discovery
  → D1  Identity
  → D2  Requirements and Evidence
  → D3  Capability and Authority
  → D4  Collaboration Session
  → D5  Coordination and Artifacts
  → D6  Outcome Records and Audit

已验证的协议对象
  → 接收方本地评估
  → 接收方本地执行
```

它们不是强制的网络分层。参与者可以复用仍然有效的 Evidence 或已有 Session，
前提是不会削弱新鲜度、上下文绑定、授权或审计要求。

同一次协作也可以使用多种传输方式。例如，通过 HTTP 交换要求、通过消息队列发送
任务、通过 MCP 暴露工具、通过内容哈希存储产物。传输方式改变时，不得暗中改变
身份、Authority、Session 范围或审计连续性。

## RFC-000 视为宪法的五项区分

### 1. 协议事实不等于领域决定

协议可以判断对象结构是否正确、签名是否有效、Issuer 是否控制对应密钥、
Evidence 是否正确绑定，以及状态转换是否合法。

协议不能决定某项有效资质是否足以满足接收方要求、Agent 是否胜任任务、输出是否
符合事实，或一个事件是否产生法律责任。

### 2. 身份不等于信任或授权

证明 Agent 控制某个标识符，并不能证明其唯一性、组织代表关系、胜任能力、权限
或可信程度。

### 3. Capability、Permission 和 Authority 不相同

Capability 描述 Agent 能做什么；Permission 描述被允许的行动；Authority 是
Permission 合法产生的依据。不能仅凭 Capability 推断 Agent 已获授权。

### 4. 验证不等于评估或执行

RFC-000 将处理过程区分为：

```text
Parse → Verify → Evaluate → Enforce
```

签名有效属于验证结果。是否披露信息、开放访问、缩小范围、要求更多 Evidence、
转交人工或拒绝行动，都属于接收方的本地决定。

### 5. 可归因记录不等于通用事实

Receipt 可以证明谁对某个事件或产物作出了什么声明。签名本身不能证明该声明符合
事实、公平或具有法律约束力。

## 如何参与

你不需要评审全部章节，也不需要认同当前方向。具体反例、冲突协议、实现 Trace、
威胁模型或遗漏的概念区分都很有价值。

### 三个核心问题

1. **框架边界：** 独立 Agent 实现之间必须共享哪些协作语义？哪些内容应该留在
   ACF 之外？
2. **反例：** 哪个真实场景会打破、复杂化或反驳“协议 Evidence 与接收方本地
   信任决定相分离”这一设计？
3. **采纳标准：** 至少需要什么实现结果或跨实现演示，RFC-000 才足以成为更具体
   RFC 的宪法？

### 进阶问题

4. Agent/Principal、Claim/Evidence、Capability/Permission/Authority、
   Session/传输、Receipt/事实等区分，是否存在错误、缺失或难以实现之处？
5. 七个语义域以及 RFC-001 至 RFC-008 的拆分是否形成了清晰的实现边界？是否有
   职责应该移动？
6. 治理和 Ratification 标准是否足够严格，尤其是独立实现、负向测试和安全评审
   要求？

可以使用下面的简短格式回复：

```markdown
### 核心

- **我支持或质疑的边界：**
- **场景或反例：**
- **采纳标准与验证材料：**

### 可选

- **缺失或有问题的概念区分：**
- **RFC/语义域拆分建议：**
- **治理或 Ratification 建议：**

### 参考材料

- **实现、规范、Trace、测试或威胁模型：**
```

聚焦单个问题或只回答部分问题同样欢迎。对具体规范文本发表评论时，请尽量标注
章节编号。

本帖用于讨论宪法层边界、语义区分以及 RFC 家族的职责拆分。具体机制争论——例如
选择哪种 DID 方法、JSON 字段如何命名、nonce 如何编码或 Relay 查询 API 如何
设计——应该进入对应的具体 RFC 或实现 Issue；除非它揭示了 RFC-000 本身的架构
问题。

## 交由更具体 RFC 处理的问题

RFC-000 识别了一些重要问题，但不直接规定其全部具体机制，包括：

- 基线身份方法、规范序列化方式和证明套件；
- Evidence 与 Receipt 类型注册表；
- 选择性披露与零知识证明的集成方式；
- 多方参与时的要求和参与方特定策略；
- Session 恢复、在线性、撤销和密钥轮换；
- 兼顾隐私的拒绝原因；
- 让结果 Receipt 可被独立审计所需的 Evidence。

其中一部分已经由 RFC-001 或 RFC-002 部分处理。它们仍会影响 RFC-000 的边界
评审，但详细语义和机制应由对应的具体 RFC 处理。

## 与当前工作的关系

RFC-000 将现有 AgentNexus ADR 和代码视为实现经验，而不是规范性协议来源。
RFC-000 仍处于 Draft 状态时，不取代现有 ADR。

目前已经发布的后续草案是：

- [RFC-001：Agent Discovery and Identity Establishment](https://github.com/kevinkaylie/AgentNexus/blob/main/specs/rfcs/001-agent-discovery-and-identity.md)
- [RFC-002：Metadata Requirements and Evidence Exchange](https://github.com/kevinkaylie/AgentNexus/blob/main/specs/rfcs/002-metadata-requirements-and-evidence-exchange.md)

跨 RFC 场景讨论
[在允许陌生 Agent 参与任务前，它至少需要证明什么？](https://github.com/kevinkaylie/AgentNexus/discussions/2)
正在收集可能同时影响多篇 RFC 的真实场景；本帖只聚焦 RFC-000 的架构和规范边界
是否正确。

## 本次评审如何收口

维护者将总结：

- 获得支持的架构边界；
- 反对意见与反例；
- 建议的 RFC 修改或新增 Issue；
- 仍需进行的互操作实验和补充证据；
- 尚未形成共识的分歧。

投票只代表关注度，不代表协议真理。重要结论会链接到对应 RFC 修改、Issue、
Pull Request 或实验，不会散落并消失在评论中。

欢迎使用中文或英文参与。

_本讨论引导内容由 Agent 协助起草，并由维护者对发布内容负责。_

</details>
