# AgentNexus 代码架构审查报告

> 日期：2026-05-09 | 范围：全项目 | 原则：功能不变前提下的代码审查

## 一、废弃 / 遮蔽文件

### 1.1 确认无引用的旧入口文件（可直接删除）

| 文件 | 说明 |
|------|------|
| `agent_net/daemon.py` | v0.1.0 旧版 Daemon，已被 `agent_net/node/daemon.py` 完全替代。**全项目无任何 import 引用** |
| `agent_net/mcp_server.py` | 旧版 MCP Server（7 个工具），已被 `agent_net/node/mcp_server.py`（37 个工具）完全替代。**全项目无任何 import 引用** |

仓库内运行路径无任何 import 引用，删除风险低。注意：若 `pyproject.toml` 打包 `agent_net*`，外部用户理论上可能直接 import 这些旧模块。保守策略是保留一版只有 `raise ImportError("moved to agent_net.node.xxx")` 的 deprecated stub，或在 CHANGELOG 中显式标注删除。

### 1.2 被 package 目录遮蔽的死文件

| 文件 | 说明 |
|------|------|
| `agent_net/identity.py` | 与 `agent_net/identity/` package 目录同名。Python 导入时优先匹配 package 目录，因此 `from agent_net.identity import ...` 实际命中 `agent_net/identity/__init__.py`，**不会**命中 `agent_net/identity.py`。该文件内定义的 `generate_did()` 和 `AgentProfile` 实际上无法被任何代码 import |

验证方式：
```python
# agent_net/identity/__init__.py（生效的导入路径）
from agent_net.common.did import DIDGenerator, AgentDID, AgentProfile
def generate_did(name): return DIDGenerator.create_new(name).did

# agent_net/identity.py（被遮蔽，永不被导入）
def generate_did(name): ...  # 旧实现，不可达
class AgentProfile: ...       # 旧实现，不可达
```

### 1.3 向后兼容重导出文件

| 文件 | 内容 | 当前引用方 |
|------|------|-----------|
| `agent_net/auth/handshake.py` | 从 `common/handshake.py` 重导出 `HandshakeManager`, `SessionKey` | 无内部引用 |
| `agent_net/identity/did_generator.py` | 从 `common/did.py` 重导出 `AgentDID`, `DIDGenerator` | `tests/test_handshake.py:9` |

**建议**: 保留兼容层，在 docstring 加 `@deprecated` 标记，引导调用方迁移到 `common` 模块。等引用方迁移完毕后再删除。

---

## 二、硬编码过期 URL

| 文件:行号 | 值 | 问题 |
|-----------|-----|------|
| `agent_net/router.py:20` | `RELAY_URL = "https://relay.agent-net.io"` | 旧域名 `agent-net.io`。更关键的是：`Router.__init__` 将其存入 `self.relay_url`，但 `route_message()` 中**任何路径都不读取 `self.relay_url`**（P2P 用 `contact["endpoint"]`，relay 转发用 `contact["relay"]`）。所以这是一个**死字段 + 旧域名误导** |
| `agent_net/common/did.py:86` | `context: str = "https://agent-net.io/v1"` | AgentProfile JSON-LD `@context` 指向旧域名。注意 JSON-LD context 是语义契约而非纯品牌标识，不应简单做域名替换。应确定新的稳定 context URI（例如 `https://agentnexus.top/contexts/agent-profile/v1`），并补 Profile 序列化/反序列化测试确保 context 变更不破坏互操作 |
| `agent_net/identity.py:27` | 同上 | 被遮蔽的死文件，无需单独修复（随文件删除一并清理） |

---

## 三、死代码

### 3.1 无效的 global 声明

**`agent_net/node/routers/agents.py:37`**:
```python
import agent_net.node.routers.agents as _self
global _heartbeat_task_ref
```
`_heartbeat_task_ref` 声明为 global 但从未被赋值、从未被读取。模块的实际 heartbeat 管理走的是 `_cfg._heartbeat_task`。这是重构遗留。

### 3.2 重复的 `AgentProfile` 定义

存在**两个** `AgentProfile` dataclass：

| 位置 | 状态 |
|------|------|
| `agent_net/common/did.py:78` | **生效版本**，含 `created_at`，字段完整 |
| `agent_net/identity.py:20` | **被遮蔽**（见 1.2 节），字段较旧（缺少 `created_at` 等） |

两个定义字段不一致，但由于 `identity.py` 已被 package 遮蔽，不影响运行时行为。随文件删除即可。

### 3.3 `router.py` 中 `self.relay_url` 未被任何路径使用

`Router.__init__` 接收 `relay_url` 并存入 `self.relay_url`，但 `route_message()` 在 P2P 路径用 `contact["endpoint"]`，在 relay 转发路径用 `contact["relay"]`，均不读 `self.relay_url`。字段本身是历史遗留，属于**无效配置/死字段**。

---

## 四、架构问题

### 4.1 God Module — `agent_net/storage.py`

**3,341 行**，包含13个领域的 CRUD 操作：Agent、消息、通讯录、握手 Pending、Skills、Push、Enclave/Vault/Playbook、Secretary Intake/Dispatch、Trust/Reputation/Governance、Coordination、Capability Tokens、Owner/Worker 管理、交互记录。

每个 async 函数都即时 `aiosqlite.connect(DB_PATH)` 创建新连接，没有连接复用。

**建议**: 渐进式拆分。注意：当前已有 `agent_net/storage.py` 文件，同目录下同时存在 `storage.py` 和 `storage/` package 会让 `import agent_net.storage` 的解析变得脆弱。正确的渐进路径是：

**阶段 1** — 新建独立命名空间承接领域模块，原 `storage.py` 保持不变只做 facade：
```
agent_net/persistence/          # 或 agent_net/storage_modules/
├── __init__.py                 # 空或仅导出公共类型
├── agents.py                   # Agent/Owner/Worker CRUD
├── messages.py                 # 消息 + 会话
├── contacts.py                 # 通讯录
├── enclave.py                  # Enclave/Vault/Playbook
├── trust.py                    # Trust/Reputation/Governance
├── coordination.py             # Coding Coordination
└── tokens.py                   # Capability Tokens
```
每次拆一个领域：实现移到 `persistence/xxx.py`，原 `storage.py` 中对应函数改为 `from agent_net.persistence.xxx import ...` 再 re-export。

**阶段 2** — 全部领域迁移完成后，做一次原子转换：`storage.py` → `storage/__init__.py`，同时删除 `persistence/` 或将其合并到 `storage/` 内。

这样每一小步都是安全的，不会出现 `storage.py` 和 `storage/` 并存的脆弱状态。

### 4.2 存储层反向依赖 Node 层

`agent_net/storage.py` 的 `register_owner()` (L214) 和 `register_secretary()` (L247) 直接 import `agent_net.node._config`（获取 relay URL 和 endpoint），违反分层原则。已在 `docs/design/design-v1.0.md:500` 记录但未修复。

**建议**: 将 relay URL / endpoint 作为参数传入，由调用方（router 层）负责提供，存储层只做纯数据持久化。

### 4.3 模块级全局可变状态（12+ 处）

| 文件 | 全局变量 | 测试影响 |
|------|---------|---------|
| `router.py:300` | `router = Router()` | 需 monkeypatch |
| `node/gatekeeper.py:143` | `gatekeeper = Gatekeeper()` | 同上 |
| `node/_config.py` | `_node_cfg`, `RELAY_URL`, `_public_endpoint`, `_heartbeat_task`, `_cleanup_push_task` | 跨模块共享，测试需 `importlib.reload` |
| `node/_auth.py` | `_daemon_token`, `_TOKEN_DID_BINDINGS` | 同上 |
| `node/routers/governance.py` | `_governance_registry` | 同上 |
| `node/daemon.py` | `_decay_task` | 同上 |
| `node/mcp_server.py` | `_push_registration`, `_push_refresh_task` | 同上 |

**建议**: 长期引入应用级 context 对象或依赖注入，短期维持现状（功能正确，只是测试隔离成本高）。

### 4.4 `router.py` 职责混杂

`Router` 类同时处理：本地投递 → 意图路由 → P2P → Relay → 离线存储 → Push 通知 → Playbook 拦截。7 个关注点在一个 `route_message()` 方法中线性串联。

---

## 五、代码质量问题

### 5.1 `content: str | dict` 类型的不一致处理

- `_models.py:22`: `SendMessageRequest.content: str | dict`
- `messages.py:112`: 发送时判断 `isinstance(req.content, str)` 再 `json.dumps`
- `router.py:56`: 接收时再次判断 `isinstance(content, str)` 再 `json.dumps`

多处重复同一模式。**建议**: 在边界（Pydantic validator 或 router 入口）统一序列化，内部路径只传 `str`。

### 5.2 重复的 DID 注册代码模式

`register_owner()` (storage.py:214)、`register_secretary()` (storage.py:247)、`api_register_agent()` (agents.py:34) 三处共享相同流程：创建 DID → 获取 endpoint → 构建 AgentProfile → 持久化 → 存私钥。重复度约 70%。

**建议**: 提取公共函数 `_create_agent_identity(name, agent_type, capabilities, worker_type)`。

### 5.3 异常处理过于宽泛

多处裸 `except Exception: pass`，例如：
- `router.py:80` 意图路由错误静默吞掉
- `router.py:135` P2P 投递失败静默吞掉
- `_config.py:100` announce 失败静默吞掉

**建议**: 至少添加 `logger.warning()`，便于排查消息投递失败、relay 通信异常等问题。

### 5.4 SQLite 连接无复用

每个 storage 函数独立 `aiosqlite.connect()` → 执行 → `commit()` → 关闭。一个 HTTP 请求可能触发 5-10 次 connect/close。

**建议**: 长期评估 WAL 模式 + 连接复用；短期维持现状（SQLite 本地文件 I/O 开销较小）。

---

## 六、SDK 目录 (`agentnexus-sdk/`)

- 结构完整，22 个 Python 文件
- `discussion.py:985` 有一处 `# TODO: Implement escalation` 未完成
- 与主项目 `agent_net/` 有部分定义共享，版本演进需注意同步

---

## 七、修改优先级

> P0 = 影响运行时正确性/安全性/消息可达性。P1 = 可维护性改进。P2 = 长期架构治理。

### P0 — 应修复

*（本次审查未发现 P0 级问题——当前代码在功能层面完整可用。以下 P1/P2 为技术债清理。）*

### P1 — 近期修整（低风险，小改动）

| # | 问题 | 文件 | 工时 |
|---|------|------|------|
| 1 | 删除无引用的旧入口文件 | `agent_net/daemon.py`, `agent_net/mcp_server.py` | 5min |
| 2 | 删除被 package 遮蔽的死文件 | `agent_net/identity.py` | 1min |
| 3 | 移除 `global _heartbeat_task_ref` 死代码 | `agents.py:37` | 1min |
| 4 | 移除 `router.py` 死字段 `RELAY_URL`；确定新的稳定 `@context` URI 替换 `agent-net.io/v1` | `router.py:20`, `did.py:86` | 30min |
| 5 | 给 P2P/Relay 异常加上 `logger.warning` | `router.py`, `_config.py` | 15min |
| 6 | 给向后兼容重导出文件加 `@deprecated` 标记 | `auth/handshake.py`, `identity/did_generator.py` | 5min |

### P2 — 中期重构（需设计 + 测试回归）

| # | 问题 | 工时 |
|---|------|------|
| 7 | 消除 `storage.py` → `node/_config.py` 反向依赖（relay URL/endpoint 参数化传入） | 2h |
| 8 | 提取公共 DID/Profile 创建函数，消除 `register_owner` / `register_secretary` / `api_register_agent` 三处重复 | 2h |
| 9 | 渐进拆分 `storage.py`：先建 `agent_net/persistence/` 承接新领域模块，原 `storage.py` 做 facade 转发；全部迁移后再做 `storage.py → storage/__init__.py` 原子转换 | 每次 2-4h |

### P3 — 长期治理（视野内但不急于动手）

| # | 问题 | 工时 |
|---|------|------|
| 10 | 拆分 `Router` 职责（路由/推送/拦截器分离） | 1d |
| 11 | 引入 app context / DI 替代 12 个全局可变状态 | 2d |
| 12 | 统一 `content: str\|dict` 序列化边界 | 1d |
| 13 | 评估 SQLite WAL 模式 + 连接复用 | 1d |
