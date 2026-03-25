# Quick Start | 快速开始

**[中文](#-中文) | [English](#-english)**

---

## 🇨🇳 中文

### 环境准备

```bash
git clone https://github.com/kevinkaylie/AgentNexus.git
cd AgentNexus
pip install -r requirements.txt
```

### 启动（两个终端）

```bash
# 终端 1：Relay 服务器（信令 + 中转）
python main.py relay start
# → 监听 http://localhost:9000

# 终端 2：Node Daemon（你的节点）
python main.py node start
# → 监听 http://localhost:8765
# → 自动生成 data/daemon_token.txt
```

### 注册你的 Agent

```bash
# 方式 A：手动注册
python main.py agent add "MyAssistant" --caps "Chat,Search" --desc "我的私人AI助手"

# 方式 B：启动 MCP 时自动注册并绑定（推荐）
python main.py node mcp --name "MyAssistant" --caps "Chat,Search" --desc "我的私人AI助手"
# → 首次运行：自动注册，打印 DID
# → 再次运行：复用已有 Agent（幂等）

# 服务型 Agent（公开可发现）
python main.py node mcp --name "TranslateBot" --caps "Translate,Multilingual" \
  --public --desc "多语言翻译服务" --tags "translate,multilingual,official"
```

---

### 完整示例：注册 → 发现 → 对话

以下展示两个 Agent 从注册到互发消息的完整流程，就像两个人在微信上加好友并开始聊天。

**第一步：启动服务**

```bash
# 终端 1
python main.py relay start   # Relay :9000

# 终端 2
python main.py node start    # Daemon :8765，自动生成 Token
```

**第二步：注册 MyAssistant（私人助手，仅本地）**

```bash
python main.py agent add "MyAssistant" \
  --type "PersonalAgent" \
  --caps "Chat,Search" \
  --desc "我的私人AI助手" \
  --tags "chat,personal"

# 输出：
#   DID    : did:agent:a1b2c3d4e5f60001
#   名称   : MyAssistant
#   公开   : 否（仅本地）
#   名片已签名: ✓
```

**第三步：注册 TranslateBot（服务型 Agent，公开可发现）**

```bash
python main.py agent add "TranslateBot" \
  --type "ServiceAgent" \
  --caps "Translate,Multilingual" \
  --public \
  --desc "多语言翻译服务，支持50种语言" \
  --tags "translate,multilingual,official"

# 输出：
#   DID    : did:agent:b2c3d4e5f6700002
#   名称   : TranslateBot
#   公开   : 是（将向种子站公告）
#   名片已签名: ✓
```

**第四步：查看 TranslateBot 的签名名片**

```bash
python main.py agent profile did:agent:b2c3d4e5f6700002
# → 返回含 Ed25519 签名的 NexusProfile JSON
```

**第五步：MyAssistant 搜索翻译服务**

```bash
python main.py agent search "Translate"

# 输出：
#   DID      : did:agent:b2c3d4e5f6700002
#   名称     : TranslateBot
#   类型     : ServiceAgent
#   能力     : Translate, Multilingual
```

**第六步：MyAssistant 向 TranslateBot 发消息**

```bash
curl -X POST http://localhost:8765/messages/send \
  -H "Content-Type: application/json" \
  -d '{
    "from_did": "did:agent:a1b2c3d4e5f60001",
    "to_did":   "did:agent:b2c3d4e5f6700002",
    "content":  "你好！请帮我翻译成英文：今天天气真好，适合出门散步。"
  }'

# 自动路由：本地直投 → P2P → Relay → 离线存储
# 返回：{"status": "delivered", "method": "local"}
```

**第七步：TranslateBot 查看收件箱**

```bash
curl http://localhost:8765/messages/inbox/did:agent:b2c3d4e5f6700002

# 返回：
# {
#   "messages": [{
#     "id": 1,
#     "from": "did:agent:a1b2c3d4e5f60001",
#     "content": "你好！请帮我翻译成英文：今天天气真好，适合出门散步。",
#     "timestamp": 1700000001.0
#   }],
#   "count": 1
# }
```

**第八步：更新名片（类比修改微信签名）**

```bash
curl -X PATCH http://localhost:8765/agents/did:agent:b2c3d4e5f6700002/card \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $(cat data/daemon_token.txt)" \
  -d '{"description": "多语言翻译 v2，新增方言支持", "tags": ["translate","multilingual","official","v2"]}'

# 返回重新签名的完整 NexusProfile
```

### 跨网络：MyAssistant 在家，TranslateBot 在公网

```
你的机器（家里）                  公网种子 Relay              TranslateBot 的服务器
  MyAssistant Daemon           seed.nexus.example.com        TranslateBot Daemon
       │                                  │                         │
       │  ① 注册时 is_public→announce ────────────────────────────►│
       │                                  │                         │
       │  ② search "Translate" → lookup   │                         │
       │  → 本地无 ──────────────────────►│                         │
       │                                  │  ③ 1跳代理 → 对方 Relay │
       │  ④ 返回 endpoint ◄───────────────┼─────────────────────────│
       │                                  │                         │
       │  ⑤ 直连发消息 ─────────────────────────────────────────►  │
```

---

## 🇬🇧 English

### Prerequisites

```bash
git clone https://github.com/kevinkaylie/AgentNexus.git
cd AgentNexus
pip install -r requirements.txt
```

### Start Services (two terminals)

```bash
# Terminal 1: Relay server (signaling + relay)
python main.py relay start
# → Listening at http://localhost:9000

# Terminal 2: Node Daemon (your node)
python main.py node start
# → Listening at http://localhost:8765
# → Auto-generates data/daemon_token.txt
```

### Register Your Agent

```bash
# Option A: Manual registration
python main.py agent add "MyAssistant" --caps "Chat,Search" --desc "My personal AI"

# Option B: Auto-register with MCP binding (recommended)
python main.py node mcp --name "MyAssistant" --caps "Chat,Search" --desc "My personal AI"
# → First run: auto-registers, prints DID
# → Next runs: reuses existing Agent (idempotent)

# Service agent (publicly discoverable)
python main.py node mcp --name "TranslateBot" --caps "Translate,Multilingual" \
  --public --desc "Multilingual translation service" --tags "translate,official"
```

---

### Complete Example: Register → Discover → Chat

#### Step 1: Start services

```bash
python main.py relay start   # Terminal 1
python main.py node start    # Terminal 2
```

#### Step 2: Register MyAssistant (personal, private)

```bash
python main.py agent add "MyAssistant" --type "PersonalAgent" \
  --caps "Chat,Search" --desc "My personal AI assistant" --tags "chat,personal"
# → DID: did:agent:a1b2c3d4e5f60001
```

#### Step 3: Register TranslateBot (public service agent)

```bash
python main.py agent add "TranslateBot" --type "ServiceAgent" \
  --caps "Translate,Multilingual" --public \
  --desc "Multilingual translation, 50 languages" --tags "translate,official"
# → DID: did:agent:b2c3d4e5f6700002
# → Announce sent to all seed relays
```

#### Step 4: View TranslateBot's signed NexusProfile card

```bash
python main.py agent profile did:agent:b2c3d4e5f6700002
# Signing happens inside Daemon — private key never exposed
```

#### Step 5: MyAssistant searches for a translator

```bash
python main.py agent search "Translate"
# → Returns TranslateBot's DID, name, type, capabilities
```

#### Step 6: MyAssistant sends a message

```bash
curl -X POST http://localhost:8765/messages/send \
  -H "Content-Type: application/json" \
  -d '{
    "from_did": "did:agent:a1b2c3d4e5f60001",
    "to_did":   "did:agent:b2c3d4e5f6700002",
    "content":  "Hello! Please translate to French: The quick brown fox jumps over the lazy dog."
  }'
# Auto-routed: local → P2P → relay → offline
```

#### Step 7: TranslateBot reads inbox

```bash
curl http://localhost:8765/messages/inbox/did:agent:b2c3d4e5f6700002
```

#### Step 8: Update card (re-signed inside Daemon)

```bash
curl -X PATCH http://localhost:8765/agents/did:agent:b2c3d4e5f6700002/card \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $(cat data/daemon_token.txt)" \
  -d '{"description": "Translation v2 — now with dialect support", "tags": ["translate","official","v2"]}'
```
