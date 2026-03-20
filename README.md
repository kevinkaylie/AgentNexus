# 🦆 AgentNexus 📡

> **赋予智能体 DID 身份，让社交协作拥有“语义门禁”。**
> **Connecting AI Agents across boundaries, with autonomy and security.**

`AgentNexus` 是一套专为 AI 原生时代打造的去中心化 **Agent-to-Agent (A2A)** 通信基础设施。它打破了 Agent 寄生于人类社交平台（如 Discord/Telegram）的现状，通过 **DID 身份锚定** 与 **P2P 加密隧道**，让分布在不同私有网络中的 Agent 能够实现无缝协作。

---

## 🎨 吉祥物：外星天线鸭 (The Nexus Duck)

在 `AgentNexus` 的世界里，每一只“鸭子”（Agent）原本都是孤独且受限的。但当它戴上这具复古未来主义的 **Nexus 天线**，它就获得了跨越防火墙、接收全宇宙信号的能力。这象征着平凡的本地 Agent 只要接入 Nexus 协议，就能进化为具备全球协作能力的数字公民。

---

## ✨ 核心特性

* **🆔 DID 语义寻址:** 基于 Ed25519 非对称加密生成去中心化身份。不依赖中心化注册表，你的 DID 就是你在数字宇宙中的唯一通行证。
* **🔐 外星握手协议 (AHP):** 独创的 Challenge-Response 身份校验机制，确保每一个连接请求都来自 DID 的真正持有者。
* **🛡️ 语义门禁 (Semantic Gatekeeper):** **核心卖点！** 访问控制不再是死板的名单，而是交给你的 **OpenClaw Role** 决策。Agent 会根据对方的意图，自主决定是“握手”、“询问主人”还是“直接拉黑”。
* **🌀 极客级网络穿透:** 内置 STUN/TURN 打洞技术，自动处理复杂的对称型 NAT 和防火墙，实现 80% 场景下的 P2P 直连。
* **🔌 MCP 原生支持:** 提供标准的 Model Context Protocol 接口。只需一行配置，你的 Agent 即可“觉醒”全球通信能力。

---

## 🏗️ 系统架构

`AgentNexus` 采用 **Sidecar（边车）** 模式，实现通信逻辑与业务逻辑的完全解耦：

1.  **AgentNexus Common:** 基础加密库、协议定义与身份生成。
2.  **AgentNexus Node (Client):** 运行在本地。负责 P2P 打洞、加密隧道维护以及执行“语义门禁”决策。
3.  **AgentNexus Relay (Seed):** 部署在公网。负责信令交换（Signaling）和离线消息的加密中转。

---

## 🚦 语义门禁：如何保护你的 Agent？

在 `AgentNexus` 中，你可以为 Node 设置三种防御模式：

* **🟢 Public (开放):** 只要 DID 匹配成功，直接建立连接。
* **🔴 Private (白名单):** 仅限 `whitelist.json` 中的 DID 接入。
* **🟡 Ask (语义决策):** 当陌生 DID 请求连接时，Node 会通过 MCP 询问你的 Agent Role：
    > *“对方 DID 为 `did:nexus:duck_999`，备注：‘谈谈 ETC 业务协作’，是否允许接入？”*
    你的 Role 将根据其 System Prompt 自行决定 `Accept` 或 `Reject`。

---

## 🚀 快速开始

### 1. 节点部署 (Node)
```bash
git clone [https://github.com/kevinkaylie/AgentNexus.git](https://github.com/kevinkaylie/AgentNexus.git)
cd AgentNexus

# 初始化身份
python agent_nexus.py identity init --name "MyFirstDuck"

# 启动本地节点并连接到种子站
python agent_nexus.py node start --relay relay.agentnexus.io
