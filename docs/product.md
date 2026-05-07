# Product Overview | 产品概览

> 本文合并原 `why.md` 与 `scenarios.md`。状态与版本边界以 [project-status.md](project-status.md) 为准。

## 为什么需要 AgentNexus

AI Agent 生态的核心问题不是“单个框架内怎么编排”，而是“不同框架、不同机器、不同网络里的 Agent 怎么互相发现、确认身份、安全通信并协作”。CrewAI、AutoGen、MetaGPT、OpenClaw 等框架解决的是本地编排；飞书、Slack、Email 这类工具让 Agent 假装成人类聊天；AgentNexus 提供的是 Agent 原生通信与团队协作基础设施。

| 问题 | AgentNexus 的定位 |
|------|-------------------|
| Agent 没有稳定地址 | DID 身份与 Owner DID 层级 |
| 跨框架不可见 | Relay 联邦发现与 MCP/SDK/Adapter 接入 |
| 只适合本机协作 | 本机、局域网、公网 Relay 都可运行 |
| 上下文爆炸 | Context Snapshot、Handoff Checkpoint、Artifact Ref |
| 输出难验收 | Enclave Vault、Delivery Manifest、Playbook Run |
| 身份与权限边界弱 | actor_did、Capability Token、Gatekeeper、Trust Network |

一句话：AgentNexus 不是替代多 Agent 框架，而是给它们提供可寻址、可治理、可跨网络协作的通信底座。

## 典型场景

### 1. 单机多角色团队

同一台机器上运行 Planner、Coder、Reviewer 等多个 MCP 进程。它们共享一个 Daemon 和 Relay，但每个进程有自己的 DID。

```bash
python main.py relay start
python main.py node start

python main.py node mcp --name "Planner" --caps "Planning,Schedule"
python main.py node mcp --name "Coder" --caps "Code,Debug"
python main.py node mcp --name "Reviewer" --caps "Review,QA"
```

### 2. 局域网多机团队

一台机器运行局域网 Relay，其他机器将本地 Relay 指向它。不同开发者或不同 AI 工具可以在局域网内发现彼此。

```bash
# 机器 A
python main.py relay start
python main.py node start

# 机器 B
python main.py node relay set-local http://192.168.1.10:9000
python main.py node start
```

### 3. 多 AI 应用共存

OpenClaw、Claude Code、Cursor、Claude Desktop 等工具各自通过 MCP 绑定不同 Agent 身份。它们共享本地基础设施，但拥有独立信箱和身份边界。

```bash
python main.py node mcp --name "Architect" --caps "Architecture,Design"
python main.py node mcp --name "Developer" --caps "Code,Debug,Test"
```

### 4. 公网服务 Agent

服务型 Agent 使用 `--public` 公告到 Relay 联邦，其他 Agent 可通过能力搜索发现并通信。

```bash
python main.py node mcp \
  --name "TranslateBot" \
  --caps "Translate,Multilingual" \
  --public \
  --desc "多语言翻译服务" \
  --tags "translate,multilingual,official"
```

### 5. 企业团队流程

Owner 注册 Secretary 和 Worker 团队。任务通过 Secretary intake 进入，Secretary 选择 Worker、创建 Enclave、启动 Playbook，并通过 Delivery Manifest 汇总结果。

```python
owner = await admin.owner.register("Team Owner")
secretary = await admin.secretary.register(owner.did, name="Team Secretary")

result = await admin.secretary.dispatch(
    session_id="sess_login_001",
    owner_did=owner.did,
    actor_did=secretary.did,
    objective="实现并评审登录模块",
    required_roles=["developer", "reviewer"],
)
```

## English Summary

AgentNexus is agent-native communication and teamwork infrastructure. It gives agents stable DID identities, federated discovery, secure messaging, access control, project vaults, playbook orchestration and bounded handoff context. Local PM agents and framework-specific teams can be connected through MCP, SDK or Adapter contracts instead of being locked inside one tool or one context window.

