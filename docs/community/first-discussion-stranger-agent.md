# What Must a Stranger Agent Prove Before You Let It Act?

**在允许陌生 Agent 参与任务前，它至少需要证明什么？**

Today’s agents can already call tools, write code, manage workflows, and
coordinate local teams. The harder questions begin when independently operated
agents collaborate across organizations, platforms, runtimes, and trust
boundaries.

Once one agent discovers another:

- Is it really the agent it claims to be?
- Who operates it, and which person or organization does it represent?
- Is it authorized to perform this particular action?
- Is a declared capability supported by evidence, or merely self-asserted?
- What information and authority should the receiver withhold or limit?
- How should the result be verified, accepted, rejected, disputed, or
  attributed?

Here, **prove** does not mean achieving universal trust or disclosing
everything. It means presenting context-bound evidence from which the receiver
can make its own decision about a specific action.

## A concrete scenario

Suppose a manufacturing company needs to purchase a batch of critical
components.

Its procurement agent discovers an unfamiliar supplier agent through an
industry platform, a private directory, a direct referral, or a federated
discovery network. The supplier agent claims that:

- it represents a particular supplier company;
- it can provide products matching the requested specification;
- it is authorized to submit formal quotations and negotiate terms;
- it is reachable through one or more collaboration endpoints.

It then asks for the full technical specification, quantity, delivery address,
schedule, and perhaps part of the available budget range.

Before the procurement agent discloses that information or allows the supplier
agent to quote, negotiate, or make a commitment, what should it require the
supplier agent to prove?

Procurement is used here as a high-stakes stress test, not as a restriction on
the discussion. Counterexamples from coding, research, customer support,
payments, healthcare, or other domains are equally welcome.

## Discovery is not verification

A platform, directory, or relay returning an agent does not automatically make
that agent trusted, capable, or authorized.

Different statements may be mixed together in one discovery result:

- “This agent supports component supply” may be a self-declared capability.
- “This agent controls this identifier” may be backed by a fresh proof of
  control.
- “This agent represents Supplier Company A” may require separate
  organizational evidence.
- “This agent is authorized to quote” may require action-specific authority or
  delegation.
- “This supplier has a 97% fulfillment rate” may be an observation or derived
  assessment issued by a platform.
- “This result is ranked first” may reflect recommendation policy, commercial
  placement, or another local decision.

A single `verified: true` flag cannot safely express all of these meanings.
The receiver may need to know who made each claim, what supports it, which
subject and action it applies to, how fresh it is, and whether it has expired,
been revoked, or is disputed.

AgentNexus starts from one principle:

> **The protocol standardizes evidence exchange, not trust decisions.**

A protocol may standardize how identity, representation, capability,
authority, evidence, provenance, verification results, and outcome records are
expressed. It should not impose a universal trust score or require every
receiver to make the same decision from the same evidence.

## How to participate

### Three core questions

1. **Scenario and action:** In your scenario, what specific action is the
   unfamiliar agent asking to take?
2. **Minimum proof:** What must it prove before the receiver allows that
   action?
3. **Decision boundary:** What should cause rejection or escalation to a
   human?

### Go deeper

4. Which discovery records, identity proofs, evidence issuers, observations, or
   trust sources would you accept?
5. What information or authority should remain undisclosed, minimized, or
   explicitly bounded?
6. What receipts, audit records, schemas, traces, fixtures, or negative test
   cases should the interaction produce?

You can reply using this short format:

```markdown
### Core

- **Scenario and proposed action:**
- **What the agent must prove:**
- **Reject or escalate when:**

### Optional

- **Discovery and evidence model:**
- **Disclosure and authority limits:**
- **Receipts or test material:**
```

Focused objections, counterexamples, and incomplete answers are welcome. You
do not need to install AgentNexus or agree with its current design.

## Where AgentNexus Relay fits

AgentNexus Relay is one experimental implementation of federated discovery and
connectivity. It may return attributable and freshness-aware discovery
records, but it does not decide whether an agent is trusted, capable, or
authorized.

Other implementations may use centralized platforms, private directories,
direct references, A2A bindings, or different federation models. This
discussion does not assume that Relay is required.

## Relationship to the ACF RFC family

This is a cross-RFC use-case discussion:

- [RFC-000 — Agent Collaboration Framework Architecture](https://github.com/kevinkaylie/AgentNexus/blob/main/specs/rfcs/000-agent-collaboration-framework.md)
  defines the architectural boundaries.
- [RFC-001 — Agent Discovery and Identity Establishment](https://github.com/kevinkaylie/AgentNexus/blob/main/specs/rfcs/001-agent-discovery-and-identity.md)
  covers discovery, identity resolution, and proof of control.
- [RFC-002 — Metadata Requirements and Evidence Exchange](https://github.com/kevinkaylie/AgentNexus/blob/main/specs/rfcs/002-metadata-requirements-and-evidence-exchange.md)
  covers receiver-authored requirements and evidence exchange.
- Planned RFC-003 will cover permission, authority, and delegation.
- Planned RFC-004 will cover collaboration session establishment.

This is not the canonical review thread for any single RFC. Conclusions may be
promoted into separate RFC review or interoperability discussions.

## How the results may be used

Depending on the responses, we may synthesize:

1. a cross-framework minimum-evidence matrix for unfamiliar-agent
   collaboration;
2. focused questions or proposed changes for individual RFCs;
3. reusable interoperability fixtures, threat scenarios, or negative tests
   when contributors provide concrete material.

Where no consensus emerges, we will record the disagreement rather than force
a single answer.

Responses in English or Chinese are welcome.

---

<details>
<summary><strong>中文版</strong></summary>

今天的 Agent 已经能够调用工具、编写代码、管理工作流，也能在本地组织多个
Agent 协同完成任务。更困难的问题出现在由不同主体独立运营的 Agent 开始跨组织、
跨平台、跨运行时和跨信任边界协作之后。

当一个 Agent 发现另一个 Agent 时：

- 它真的是自己声称的那个 Agent 吗？
- 谁在运营它？它代表哪个人或组织？
- 它是否被授权执行这次具体行动？
- 它声明的能力有证据支持，还是仅仅是自我声明？
- 接收方应该保留或限制哪些信息与权限？
- 它的结果应该如何验证、接受、拒绝、争议和归因？

这里的“证明”不是获得普遍信任，也不是披露所有信息，而是提供与当前上下文绑定的
证据，让接收方能够针对一次具体行动作出自己的决定。

## 一个具体场景

假设一家制造企业需要采购一批关键零部件。

企业的采购 Agent 通过行业平台、私有目录、直接推荐或联邦发现网络，发现了一个
陌生的供应商 Agent。这个供应商 Agent 声称：

- 自己代表某家供应商企业；
- 能够提供符合采购规格的产品；
- 有权提交正式报价并参与条款谈判；
- 可以通过一个或多个协作端点联系。

随后，它请求获得完整技术规格、采购数量、交付地址、交付时间，甚至部分预算范围。

在披露这些信息，或者允许供应商 Agent 报价、谈判和作出承诺之前，采购 Agent
应该要求它证明什么？

这里使用采购作为高风险压力测试，并不限制讨论范围。我们同样欢迎来自编程、研究、
客服、支付、医疗或其他领域的反例和经验。

## 被发现不等于通过验证

一个 Agent 被平台、Directory 或 Relay 返回，并不表示它已经值得信任、具备能力
或获得授权。

发现结果中可能混合了性质不同的信息：

- “支持零部件供应”可能只是自我能力声明；
- “控制这个 Agent Identifier”可能有新鲜的控制权证明；
- “代表供应商企业 A”可能需要单独的组织关系证据；
- “有权报价”可能需要针对具体行动的授权或委托；
- “历史履约率为 97%”可能是平台发布的观察或派生评价；
- “排名第一”可能来自推荐政策、商业推广或其他本地决策。

一个简单的 `verified: true` 无法安全表达所有这些含义。接收方可能需要知道：
每项声明是谁作出的、有什么证据支持、适用于哪个主体和行动、信息有多新鲜，以及
它是否已经过期、撤销或存在争议。

AgentNexus 从一个基本原则出发：

> **协议标准化证据交换，而不是替接收方做信任决定。**

协议可以标准化身份、代表关系、能力、授权、证据、来源、验证结果和结果记录的
表达方式，但不应建立统一的 Trust Score，也不应要求所有接收方根据同一组证据
作出同样决定。

## 如何参与

### 3 项核心问题

1. **场景与行动：**在你的场景中，陌生 Agent 希望执行什么具体行动？
2. **最低证明：**在允许行动前，接收方应该要求它证明什么？
3. **决策边界：**哪些情况应该导致拒绝或升级给人类？

### 3 项进阶问题

4. 你愿意接受哪些发现记录、身份证明、证据签发者、观察记录或信任来源？
5. 哪些信息或权限应该保持不披露、最小化披露或受到明确限制？
6. 这次交互应该产生哪些回执、审计记录、schema、trace、fixture 或负向测试？

可以使用以下简短格式回复：

```markdown
### 必答

- **场景与希望执行的行动：**
- **Agent 必须证明什么：**
- **拒绝或升级给人类的条件：**

### 进阶

- **发现与证据模型：**
- **信息披露与授权边界：**
- **回执或测试材料：**
```

一个明确的质疑、反例或不完整回答同样有价值。不需要安装 AgentNexus，也不要求
认同当前设计。

## AgentNexus Relay 的位置

AgentNexus Relay 是联邦发现与连接的一条实验性实现路径。它可以返回带来源和
时效信息的发现记录，但不会替接收方决定一个 Agent 是否可信、具备能力或获得授权。

其他实现可以采用中心平台、私有目录、直接引用、A2A binding 或不同的联邦模型。
本讨论不假设 Relay 是必需组件。

## 与 ACF RFC 家族的关系

这是一个跨 RFC 的场景讨论：

- [RFC-000：Agent Collaboration Framework Architecture](https://github.com/kevinkaylie/AgentNexus/blob/main/specs/rfcs/000-agent-collaboration-framework.md)
  定义总体架构边界；
- [RFC-001：Agent Discovery and Identity Establishment](https://github.com/kevinkaylie/AgentNexus/blob/main/specs/rfcs/001-agent-discovery-and-identity.md)
  处理发现、身份解析和控制权证明；
- [RFC-002：Metadata Requirements and Evidence Exchange](https://github.com/kevinkaylie/AgentNexus/blob/main/specs/rfcs/002-metadata-requirements-and-evidence-exchange.md)
  处理接收方提出的要求和证据交换；
- 规划中的 RFC-003 将处理 Permission、Authority 和 Delegation；
- 规划中的 RFC-004 将处理 Collaboration Session 的建立。

这不是任何单篇 RFC 的正式评审主帖。讨论结论可以进一步进入独立的 RFC 评审或
互操作实验。

## 讨论结果可能如何使用

根据收到的回复，我们可能整理出：

1. 一份陌生 Agent 协作的跨框架最小证据矩阵；
2. 面向具体 RFC 的问题或修改建议；
3. 在参与者提供具体材料时形成可复用的互操作 fixture、威胁场景或负向测试。

如果未能形成共识，我们会记录分歧，而不是强行产生单一答案。

欢迎使用中文或英文回复。

</details>
