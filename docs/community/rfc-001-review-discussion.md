# RFC-001 Review: When Is an Agent Discovered—and When Is Its Identity Established?

**RFC-001 评审：何时只是发现 Agent，何时才算建立身份？**

This is the canonical community review thread for
[RFC-001 — Agent Discovery and Identity Establishment, Draft v0.1](https://github.com/kevinkaylie/AgentNexus/blob/main/specs/rfcs/001-agent-discovery-and-identity.md).

RFC-001 defines transport-independent semantics for finding potential Agent
collaborators and establishing current control of an Agent Identifier through
an authorized Verification Method. It requires RFC-000 and is divided into two
independently conformable parts:

- **Part A — Agent Discovery**
- **Part B — Agent Identity Establishment**

An implementation may support either part or both, but it must state its
conformance separately.

The central separation is:

```text
Discovery locates a candidate and preserves what was asserted, by whom,
through which source, and how recently.

Identity Establishment resolves the Agent Identifier and verifies that the
current participant controls a Verification Method authorized for the
requested purpose.
```

Neither step decides whether the Agent is trustworthy, competent, authorized
for a business action, currently reachable at every endpoint, or entitled to
represent a particular person or organization.

## Why Discovery and Identity must remain separate

Agent systems often collapse several different statements into one search
result or a single `verified: true` flag:

- a Directory found an Agent Descriptor;
- the Descriptor was issued or signed by a particular party;
- the Agent controls the identifier named by the Descriptor;
- the Agent represents a particular Principal;
- the Agent can perform a declared capability;
- the Agent is permitted to perform a requested action;
- the Directory recommends the Agent;
- an endpoint was recently reachable.

These statements have different issuers, verification procedures, freshness
requirements, and consequences. RFC-001 therefore declares the following
implications invalid:

```text
Discovered        ⇏ identity verified
Identity verified ⇏ Principal relationship verified
Identity verified ⇏ capability verified
Identity verified ⇏ authority granted
Identity verified ⇏ trusted
Identity verified ⇏ online
```

The goal is not to make discovery untrusted or identity weak. The goal is to
make every result precise enough that a receiver knows what was actually
established and what still requires Claims, Evidence, local evaluation, or
later protocol steps.

## Part A — Agent Discovery

Part A standardizes how implementations locate and describe potential
collaborators without requiring one global Directory.

It supports several discovery models:

- direct references;
- structured Directory queries;
- registration registries;
- broadcast or gossip;
- referrals;
- federated lookup;
- local enumeration.

Regardless of the model, a result must preserve provenance. A Directory must
not rewrite a self-asserted or third-party claim as though the Directory were
its original issuer.

### Descriptor claims are not automatically verified facts

An Agent Descriptor may declare:

- Agent and identity references;
- capabilities and actions;
- supported ACF versions and profiles;
- collaboration endpoints;
- Principal or organization references;
- Evidence or metadata-negotiation services;
- presence, availability, and expiry.

The Descriptor must distinguish self-asserted fields, third-party assertions,
local observations, and Directory-generated fields. A capability match means
that a Descriptor contains a matching claim; it does not prove competence,
Permission, or Authority.

If a Directory adds ranking, recommendation, risk, or score fields, those
fields must identify their evaluator, method, context, and time. They may
become Evidence under RFC-002, but they are not universal trust conclusions.

### How should external Agent Cards and profiles map to Agent Descriptors?

Many ecosystems already publish Agent Cards or other profile formats that
describe identities, skills or capabilities, endpoints, authentication
requirements, and metadata. A2A Agent Cards are one important example.

This review should clarify whether an external profile is:

- a native serialization or profile of an ACF Agent Descriptor;
- a source referenced by an Agent Descriptor;
- input translated into an Agent Descriptor with explicit mapping provenance;
- or a separate set of claims that remains alongside the Descriptor.

A mapping must not silently upgrade a self-asserted field into a verified
fact, replace the original issuer with the translator or Directory, or discard
version, freshness, proof, and source-type information. Contributors working
with Agent Cards or other external profile formats are invited to identify the
minimum lossless mapping and any semantic mismatch.

### Discovery is time-sensitive and security-sensitive

Discovery Records and presence claims need explicit source, retrieval time,
expiry, version, and status. Withdrawal from one Directory is not identity
deactivation, and failure to reach one endpoint does not deactivate an Agent
Identifier.

Endpoint addresses remain untrusted input. Implementations must defend
against SSRF, redirect abuse, local-network access, credential forwarding,
endpoint confusion, stale records, replay, Directory poisoning, capability
spam, search manipulation, federation loops, enumeration, and privacy leakage
from queries.

## Part B — Agent Identity Establishment

Part B defines how an implementation resolves an Agent Identifier and verifies
fresh control over an authorized Verification Method.

RFC-001 does not mandate DID or any other single identity technology. An ACF
Identity Method may be self-certifying, registry-backed, domain-backed,
ledger-backed, federated, or local, but it must define:

- identifier syntax and normalization;
- resolution and deterministic errors;
- Verification Methods and authorized purposes;
- controller and document-version semantics;
- freshness, caching, rotation, and deactivation;
- compromise, recovery, security, privacy, and test vectors.

Consumers must not assume that different Identity Methods provide identical
security properties.

### Resolution is not Proof of Control

Successful Identity Resolution means that the selected Identity Method
returned a valid Identity Document under its own rules. It does not prove that
the participant currently controls an authorized key.

Proof of Control is separate from Resolution. The current draft describes it
using a fresh verifier challenge and response. This review should determine
whether conformance is better defined by the required security properties
rather than by an explicit two-message shape.

Verifier-nonce signatures, channel-bound proofs, TLS client authentication,
DPoP-style proofs, hardware-authenticator assertions, or request-bound
non-interactive signatures may be candidate realizations if they provide the
required freshness, audience, purpose, context binding, authorized-method
binding, and replay resistance.

Regardless of the concrete realization, a verifier must:

1. resolve the current Identity Document;
2. locate the selected Verification Method;
3. confirm that it is authorized for the requested purpose;
4. validate proof freshness and replay resistance;
5. validate audience and context binding;
6. verify the proof;
7. record the document version, method identifier, and verification time.

A valid key used for an unauthorized purpose must fail. For example, a key
authorized only for key agreement must not be accepted for assertions.

### Agent identity is not Principal representation

Proof that a participant controls an Agent Identifier does not prove legal
identity, organization membership, employment, ownership, professional
status, or authority to represent another Principal.

Those relationships belong in explicit Claims and Evidence under RFC-002. An
Agent may represent different Principals in different contexts, so the
relevant Principal and representation material must be bound to the
Collaboration Intent or Session when they affect authority or risk.

### Identity changes have different meanings

RFC-001 keeps these events separate:

- key rotation;
- identity or Verification Method deactivation;
- temporary unreachability;
- Discovery Record withdrawal;
- expired presence;
- operator or Principal change;
- recovery after compromise;
- Session suspension.

Historical proofs and Receipts may remain verifiable after deactivation,
depending on their issuance-time context. Active collaboration should be
re-evaluated after compromise, recovery, or operator change.

## Four defined conformance roles—and a possible missing role

RFC-001 currently requires an implementation to state which of four defined
roles it implements:

1. **Discovery Client** — preserves provenance and freshness, treats endpoints
   as untrusted input, and exposes structured validation results.
2. **Discovery Provider** — returns attributable, versioned records; bounds
   queries and federation; and documents ranking, recommendation, and
   retention behavior.
3. **Identity Resolver** — implements a documented Identity Method, never
   falls back to an unverified key, enforces verification purposes, and
   handles rotation, deactivation, and recovery.
4. **Proof-of-Control Verifier** — as currently drafted, uses fresh single-use
   challenges; verifies the currently authorized method and context bindings;
   rejects replay; and records the identity version and verification time.
   This review asks whether equivalent security-property-based realizations
   should also conform.

A possible gap is a separate **Descriptor Publisher / Registrant** role. The
party that creates, signs, versions, updates, and withdraws the original Agent
Descriptor may be the Agent, its operator, a Principal, a runtime, an
enterprise administrator, or a third-party profile issuer. That party is not
necessarily the Discovery Provider that stores, indexes, queries, and returns
the record.

The review should decide whether Publisher responsibilities need separate
conformance requirements for claim-source labeling, issuer identity,
versioning, proof, freshness, update authorization, and withdrawal. The four
defined roles and this proposed role are all open to challenge.

## How to participate

You may review Part A, Part B, or both. A response based on an existing
Directory, Descriptor publisher, DID method, A2A Agent Card, MCP registry,
private Agent catalog, resolver, key-management system, or other
implementation is especially valuable.

### Three core questions

1. **Scenario and boundary:** In your system, where does Discovery end and
   Identity Establishment begin, and which defined or proposed RFC-001 role do
   you implement?
2. **Invalid inference:** Which claim is most likely to be incorrectly inferred
   from a Discovery Record or a successful Proof of Control?
3. **Interoperability test:** What minimum cross-implementation demonstration
   or negative test should be required separately for Part A and Part B?

### Go deeper

4. Should RFC-001 define a separate Descriptor Publisher / Registrant role,
   and how should Agent Cards or other external profiles map to Agent
   Descriptors without losing provenance or changing claim meaning?
5. Are the Identity Method requirements, verification-purpose rules, Proof of
   Control, rotation, deactivation, and recovery semantics implementable
   across materially different identity technologies?
6. Are privacy-sensitive discovery, pairwise identifiers, presence, liveness,
   and Session continuity assigned to the right RFC boundaries?

You can reply using this short format:

```markdown
### Core

- **Part, role, and scenario boundary:**
- **Dangerous invalid inference:**
- **Required interoperability demonstration or negative test:**

### Optional

- **External profile, Descriptor provenance, or Publisher feedback:**
- **Identity lifecycle or Proof-of-Control feedback:**
- **Privacy, presence, or RFC-boundary feedback:**

### References

- **Implementation, specification, trace, fixture, or test vector:**
```

Focused objections and incomplete answers are welcome. Please cite a section
number when commenting on specific normative text.

Use this thread for RFC-001 semantics that must remain consistent across
Discovery and Identity implementations. Exact DID-method selection, JSON field
names, nonce encoding, Relay endpoints, and transport-specific APIs should be
developed in the relevant profile, binding, implementation Issue, or focused
sub-discussion unless they expose a flaw in RFC-001's shared semantics.

## Questions delegated to profiles and more specific RFC work

RFC-001 identifies open decisions including:

### Discovery

- whether Discovery Records require a canonical signed form;
- which capability vocabulary supports interoperable search;
- how private and authenticated discovery is negotiated;
- how Directory recommendation methods are registered and audited;
- which presence and liveness semantics belong here versus RFC-004.

### Identity

- whether the baseline profile requires any particular Identity Methods;
- whether pairwise Agent Identifiers belong in the baseline privacy profile;
- what continuity proof successor identifiers require.

These questions belong in this review when they affect RFC-001's common
semantics or conformance boundaries. Concrete profiles, encodings, registries,
and transport mechanisms should be resolved in the document or workstream
that owns them.

## Relationship to the ACF RFC family

[RFC-000](https://github.com/kevinkaylie/AgentNexus/blob/main/specs/rfcs/000-agent-collaboration-framework.md)
defines the constitutional separation among identity, Evidence, trust,
decision, and enforcement. Its
[canonical review discussion](https://github.com/kevinkaylie/AgentNexus/discussions/4)
is the right place to challenge that framework-level boundary.

[RFC-002](https://github.com/kevinkaylie/AgentNexus/blob/main/specs/rfcs/002-metadata-requirements-and-evidence-exchange.md)
handles the representation, organization, capability, behavior, and other
Evidence that a receiver may require after discovery or identity
establishment.

The broader use-case discussion
[What Must a Stranger Agent Prove Before You Let It Act?](https://github.com/kevinkaylie/AgentNexus/discussions/2)
is collecting scenarios that may challenge several RFCs at once. This thread
is specifically for reviewing RFC-001's Discovery and Identity semantics.

## How this review will be resolved

Maintainers will summarize Part A and Part B separately:

- supported semantic and conformance decisions;
- objections, counterexamples, and security or privacy risks;
- proposed RFC changes or tracked Issues;
- interoperability fixtures, test vectors, and implementations;
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
[RFC-001：Agent Discovery and Identity Establishment，Draft v0.1](https://github.com/kevinkaylie/AgentNexus/blob/main/specs/rfcs/001-agent-discovery-and-identity.md)
的正式社区评审主帖。

RFC-001 定义寻找潜在 Agent 协作者以及建立 Agent 身份控制权时，与传输无关的
语义。它依赖 RFC-000，并分成两个可独立声明合规的部分：

- **Part A — Agent Discovery**
- **Part B — Agent Identity Establishment**

一个实现可以只支持其中一部分，也可以同时支持两部分，但必须分别说明合规范围。

核心区分是：

```text
Discovery 找到候选对象，并保留“谁通过什么来源、在什么时间作出了什么声明”。

Identity Establishment 解析 Agent Identifier，并验证当前参与者控制着一个
对本次用途有效的 Verification Method。
```

两者都不决定这个 Agent 是否可信、是否胜任、是否被授权执行具体业务行动、所有
端点是否在线，或它是否有资格代表某个特定个人或组织。

## 为什么必须区分 Discovery 和 Identity

Agent 系统经常把多种不同含义压缩进一个搜索结果或 `verified: true`：

- Directory 找到了一个 Agent Descriptor；
- Descriptor 由某个主体签发或签名；
- Agent 控制 Descriptor 中的标识符；
- Agent 代表某个 Principal；
- Agent 能够执行它声明的能力；
- Agent 被允许执行所请求的行动；
- Directory 推荐这个 Agent；
- 某个端点最近可以访问。

这些陈述具有不同的 Issuer、验证方法、新鲜度要求和后果。因此 RFC-001 明确以下
推导无效：

```text
已被发现      ⇏ 身份已验证
身份已验证    ⇏ Principal 关系已验证
身份已验证    ⇏ 能力已验证
身份已验证    ⇏ 已获得 Authority
身份已验证    ⇏ 可信
身份已验证    ⇏ 在线
```

目标不是让 Discovery 变得“不可信”或让身份变得“弱”，而是精确表达每个结果：
接收方应该清楚知道什么已经成立，什么仍需要 Claims、Evidence、本地评估或后续
协议步骤。

## Part A — Agent Discovery

Part A 规范如何寻找和描述潜在协作者，但不要求存在一个全局 Directory。

它支持多种发现模型：

- 直接引用；
- 结构化 Directory 查询；
- 注册型 Registry；
- 广播或 Gossip；
- Referral；
- 联邦查询；
- 本地枚举。

无论使用哪种模型，结果都必须保留来源。Directory 不得把一个自我声明或第三方
声明重写成仿佛由 Directory 原始签发。

### Descriptor 声明不会自动成为已验证事实

Agent Descriptor 可以声明：

- Agent 与身份引用；
- Capability 和 Action；
- 支持的 ACF 版本和 Profile；
- 协作端点；
- Principal 或组织引用；
- Evidence 或元数据协商服务；
- Presence、可用性和有效期。

Descriptor 必须区分自我声明、第三方声明、本地观察和 Directory 生成的字段。
Capability 匹配只代表 Descriptor 中存在相应声明，并不证明胜任能力、Permission
或 Authority。

如果 Directory 增加排序、推荐、风险或评分字段，这些字段必须说明 Evaluator、
方法、上下文和时间。它们可以成为 RFC-002 中的 Evidence，但不是通用信任结论。

### 外部 Agent Card 和 Profile 应如何映射到 Agent Descriptor？

许多生态已经发布 Agent Card 或其他 Profile 格式，用于描述身份、Skill 或
Capability、端点、认证要求和元数据。A2A Agent Card 是其中一个重要例子。

本次评审应明确外部 Profile 属于哪种关系：

- ACF Agent Descriptor 的原生序列化或 Profile；
- Agent Descriptor 引用的来源；
- 在保留明确映射来源的前提下，转换成 Agent Descriptor 的输入；
- 或与 Descriptor 并存的一组独立声明。

映射不得暗中把自我声明升级成已验证事实，不得用 Translator 或 Directory 替换
原始 Issuer，也不得丢失版本、新鲜度、Proof 和来源类型。使用 Agent Card 或其他
外部 Profile 的贡献者，可以帮助确定最小无损映射以及无法直接映射的语义差异。

### Discovery 具有时效、安全和隐私边界

Discovery Record 与 Presence 声明需要明确来源、检索时间、有效期、版本和状态。
从一个 Directory 撤回记录不等于身份停用，无法访问一个端点也不等于 Agent
Identifier 已停用。

端点地址仍然是不可信输入。实现必须应对 SSRF、重定向滥用、内网访问、凭证转发、
端点混淆、陈旧记录、重放、Directory 投毒、Capability Spam、搜索操纵、联邦
循环、枚举以及查询产生的隐私泄露。

## Part B — Agent Identity Establishment

Part B 规定如何解析 Agent Identifier，并通过新鲜证明验证当前参与者是否控制
一个获得授权的 Verification Method。

RFC-001 不强制 DID 或其他单一身份技术。ACF Identity Method 可以是自证明型、
注册表型、域名型、账本型、联邦型或本地型，但必须定义：

- 标识符语法与规范化；
- 解析流程和确定性错误；
- Verification Method 及授权用途；
- Controller 与文档版本语义；
- 新鲜度、缓存、轮换和停用；
- 泄露、恢复、安全、隐私和测试向量。

使用方不得假设不同 Identity Method 具有相同的安全属性。

### Resolution 不等于 Proof of Control

Identity Resolution 成功，只表示所选 Identity Method 按照自身规则返回了有效的
Identity Document；它不能证明当前参与者控制着一个获得授权的密钥。

Proof of Control 独立于 Resolution。当前草案使用新鲜的 Verifier Challenge 与
Response 描述这个过程。本次评审需要判断，合规要求是否应该由必要的安全属性
定义，而不是限定为显式的两轮消息形态。

Verifier Nonce 签名、Channel-bound Proof、TLS Client Authentication、
DPoP 类证明、硬件认证器 Assertion 或与一次性请求绑定的非交互签名，都可能成为
候选实现；前提是它们满足新鲜度、Audience、Purpose、上下文绑定、授权方法绑定
以及抗重放要求。

无论采用哪种具体实现，Verifier 都必须：

1. 解析当前 Identity Document；
2. 找到选定的 Verification Method；
3. 确认该方法被授权用于请求的用途；
4. 验证 Proof 的新鲜度和抗重放性；
5. 验证 Audience 与上下文绑定；
6. 验证 Proof；
7. 记录文档版本、方法标识符和验证时间。

有效密钥如果被用于未经授权的用途，验证必须失败。例如，只允许用于密钥协商的
密钥不能用于 Assertion。

### Agent 身份不等于 Principal 代表关系

证明参与者控制 Agent Identifier，并不能证明法律身份、组织成员关系、雇佣关系、
所有权、职业资质或代表另一个 Principal 的权限。

这些关系需要通过 RFC-002 中明确的 Claims 与 Evidence 表达。Agent 可以在不同
上下文中代表不同 Principal；当这一差异影响 Authority 或风险时，相关 Principal
和代表关系材料必须绑定到 Collaboration Intent 或 Session。

### 不同身份变化具有不同含义

RFC-001 区分：

- 密钥轮换；
- 身份或 Verification Method 停用；
- 暂时不可达；
- Discovery Record 撤回；
- Presence 过期；
- Operator 或 Principal 变化；
- 泄露后的恢复；
- Session 暂停。

停用后，历史 Proof 和 Receipt 仍可能根据其签发时上下文继续可验证。发生泄露、
恢复或 Operator 变化后，活跃协作应重新评估。

## 四种已定义的合规角色，以及一个可能缺失的角色

RFC-001 当前要求实现说明自己支持以下四种已定义角色中的哪些角色：

1. **Discovery Client**：保留来源与新鲜度，将端点视为不可信输入，并暴露结构化
   验证结果。
2. **Discovery Provider**：返回可归因、有版本的记录；限制查询与联邦转发；说明
   排序、推荐和保留策略。
3. **Identity Resolver**：实现已文档化的 Identity Method；绝不回退到未经验证
   的密钥；强制 Verification Purpose；处理轮换、停用和恢复。
4. **Proof-of-Control Verifier**：当前草案要求使用新鲜的一次性挑战；验证当前
   已授权方法与上下文绑定；拒绝重放；记录身份版本和验证时间。本次评审将判断
   满足等价安全属性的其他实现是否也应合规。

一个可能的缺口是独立的 **Descriptor Publisher / Registrant** 角色。创建、签名、
版本化、更新和撤回原始 Agent Descriptor 的主体，可能是 Agent 自身、Operator、
Principal、Runtime、企业管理员或第三方 Profile Issuer。它不一定等于负责存储、
索引、查询和返回记录的 Discovery Provider。

本次评审需要判断 Publisher 是否应该拥有独立的合规要求，包括声明来源标记、
Issuer 身份、版本、Proof、新鲜度、更新授权和撤回。四种已定义角色和这个拟议角色
都可以被质疑和调整。

## 如何参与

你可以只评审 Part A、只评审 Part B，或同时评审两部分。来自现有 Directory、
Descriptor Publisher、DID Method、A2A Agent Card、MCP Registry、私有 Agent
Catalog、Resolver、密钥管理系统或其他实现的反馈尤其有价值。

### 三个核心问题

1. **场景与边界：** 在你的系统中，Discovery 在哪里结束，Identity
   Establishment 从哪里开始？你实现了哪种已定义或拟议的 RFC-001 角色？
2. **无效推导：** 人们最容易从 Discovery Record 或成功的 Proof of Control 中
   错误推导出哪种声明？
3. **互操作测试：** Part A 和 Part B 分别至少需要什么跨实现演示或负向测试？

### 进阶问题

4. RFC-001 是否应该定义独立的 Descriptor Publisher / Registrant 角色？Agent
   Card 或其他外部 Profile 应如何映射到 Agent Descriptor，才能保留来源且不
   改变声明含义？
5. Identity Method 要求、Verification Purpose、Proof of Control、轮换、停用和
   恢复语义，能否跨差异显著的身份技术实现？
6. 隐私敏感的 Discovery、Pairwise Identifier、Presence、Liveness 和 Session
   连续性是否被分配到了正确的 RFC 边界？

可以使用下面的简短格式回复：

```markdown
### 核心

- **Part、角色及场景边界：**
- **危险的无效推导：**
- **需要的互操作演示或负向测试：**

### 可选

- **外部 Profile、Descriptor 来源或 Publisher 反馈：**
- **身份生命周期或 Proof-of-Control 反馈：**
- **隐私、Presence 或 RFC 边界反馈：**

### 参考材料

- **实现、规范、Trace、Fixture 或测试向量：**
```

聚焦单个问题或只回答部分问题同样欢迎。对具体规范文本发表评论时，请尽量标注
章节编号。

本帖用于讨论不同 Discovery 和 Identity 实现必须保持一致的 RFC-001 语义。
具体 DID Method 选择、JSON 字段命名、nonce 编码、Relay 端点和特定传输 API，
应该进入对应的 Profile、Binding、实现 Issue 或聚焦子讨论；除非它们揭示了
RFC-001 共享语义本身的问题。

## 交由 Profile 和更具体 RFC 工作处理的问题

RFC-001 识别的开放决定包括：

### Discovery

- Discovery Record 是否需要规范化的签名形式；
- 哪种 Capability Vocabulary 支持可互操作搜索；
- 私有和认证 Discovery 如何协商；
- Directory 推荐方法如何注册和审计；
- 哪些 Presence 与 Liveness 语义属于本 RFC，哪些属于 RFC-004。

### Identity

- 基线 Profile 是否要求特定 Identity Method；
- Pairwise Agent Identifier 是否属于基线隐私 Profile；
- Successor Identifier 至少需要什么连续性证明。

这些问题影响 RFC-001 的公共语义或合规边界时，应当进入本次评审。具体 Profile、
编码、Registry 和传输机制，应在负责它们的文档或工作流中收敛。

## 与 ACF RFC 家族的关系

[RFC-000](https://github.com/kevinkaylie/AgentNexus/blob/main/specs/rfcs/000-agent-collaboration-framework.md)
规定身份、Evidence、信任、决定与执行之间的宪法性区分。若要挑战框架层边界，
请进入其
[正式评审主帖](https://github.com/kevinkaylie/AgentNexus/discussions/4)。

[RFC-002](https://github.com/kevinkaylie/AgentNexus/blob/main/specs/rfcs/002-metadata-requirements-and-evidence-exchange.md)
处理发现或身份建立后，接收方可能要求的代表关系、组织、能力、行为及其他
Evidence。

跨 RFC 场景讨论
[在允许陌生 Agent 参与任务前，它至少需要证明什么？](https://github.com/kevinkaylie/AgentNexus/discussions/2)
正在收集可能同时影响多篇 RFC 的场景；本帖只聚焦 RFC-001 的 Discovery 与
Identity 语义。

## 本次评审如何收口

维护者将分别总结 Part A 与 Part B：

- 获得支持的语义和合规决定；
- 反对意见、反例以及安全或隐私风险；
- 建议的 RFC 修改或已追踪 Issue；
- 互操作 Fixture、测试向量和实现；
- 尚未形成共识的分歧。

投票只代表关注度，不代表协议真理。重要结论会链接到相关 RFC 修改、Issue、
Pull Request、Profile 或实验。

欢迎使用中文或英文参与。

_本讨论引导内容由 Agent 协助起草，并由维护者对发布内容负责。_

</details>
