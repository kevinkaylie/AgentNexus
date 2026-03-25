# CLI Commands | 命令速查

**[中文](#-中文) | [English](#-english)**

---

## 🇨🇳 中文

### 服务启动

```bash
python main.py relay start                     # 启动信令/中转服务器 :9000
python main.py node start                      # 启动本地节点 Daemon :8765
python main.py node mcp                        # 启动 MCP Server（stdio）
python main.py node mcp --name "CoderAgent"   # 启动 MCP 并绑定 Agent 身份
python main.py node mcp --did did:agent:xxx   # 启动 MCP 并绑定已有 DID
python main.py node mcp --name "R" --caps "CodeReview" --public  # 带能力和公开标志
python main.py node demo                       # 本地功能演示
python main.py test                            # 运行全部测试用例（68个）
```

### Agent 管理

```bash
python main.py agent add "MyBot" --type TaskAgent --caps "Chat,Search" \
  --public --desc "通用助手" --tags "chat,task"     # 新建（公开）
python main.py agent list                            # 列出所有
python main.py agent update <did> --caps "Chat,Code,Review"  # 更新
python main.py agent delete <did>                    # 删除
python main.py agent search "Chat"                   # 按能力搜索
python main.py agent profile <did>                   # 查看签名名片
```

### 访问控制

```bash
python main.py node mode set public|ask|private      # 设置访问模式
python main.py node whitelist add <did>              # 加白名单
python main.py node whitelist remove <did>           # 移除白名单
python main.py node whitelist list                   # 查看白名单
python main.py node blacklist add <did>              # 加黑名单
python main.py node blacklist remove <did>           # 移除黑名单
python main.py node blacklist list                   # 查看黑名单
python main.py node status --pending                 # 查看待审批请求
python main.py node resolve <did> allow|deny         # 审批请求
```

### Relay 配置

```bash
python main.py node relay list                       # 列出当前 Relay 配置
python main.py node relay set-local <url>            # 设置本地 relay 地址
python main.py node relay add <url>                  # 加入种子站
python main.py node relay remove <url>               # 移除种子站
```

### 多机联邦部署

```bash
# 机器 A（192.168.1.100）作为局域网 Relay
python main.py relay start

# 机器 B 指向 A 的 Relay
python main.py node relay set-local http://192.168.1.100:9000
python main.py node start

# 可选：加入公网种子站
python main.py node relay add https://relay.example.com
```

---

## 🇬🇧 English

### Service Startup

```bash
python main.py relay start                     # Start Relay server :9000
python main.py node start                      # Start Node Daemon :8765
python main.py node mcp                        # Start MCP Server (stdio)
python main.py node mcp --name "CoderAgent"   # Start MCP with Agent binding
python main.py node mcp --did did:agent:xxx   # Start MCP with existing DID
python main.py node mcp --name "R" --caps "CodeReview" --public
python main.py node demo                       # Local feature demo
python main.py test                            # Run all tests (68)
```

### Agent Management

```bash
python main.py agent add "MyBot" --type TaskAgent --caps "Chat,Search" \
  --public --desc "General assistant" --tags "chat,task"
python main.py agent list
python main.py agent update <did> --caps "Chat,Code,Review"
python main.py agent delete <did>
python main.py agent search "Chat"
python main.py agent profile <did>
```

### Access Control

```bash
python main.py node mode set public|ask|private
python main.py node whitelist add|remove|list <did>
python main.py node blacklist add|remove|list <did>
python main.py node status [--pending]
python main.py node resolve <did> allow|deny
```

### Relay Configuration

```bash
python main.py node relay list
python main.py node relay set-local <url>
python main.py node relay add <url>
python main.py node relay remove <url>
```

### Multi-Machine Federation

```bash
# Machine A (192.168.1.100) as LAN Relay
python main.py relay start

# Machine B points to A's Relay
python main.py node relay set-local http://192.168.1.100:9000
python main.py node start

# Optional: join public seed relay
python main.py node relay add https://relay.example.com
```
