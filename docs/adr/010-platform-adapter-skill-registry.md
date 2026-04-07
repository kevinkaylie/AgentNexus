# ADR-010: 平台适配器与 Skill 注册架构

## 状态

已采纳

## 日期

2026-04-04

## 背景

v0.8 需要实现两个平台适配器（0.8-07 OpenClaw Skill、0.8-08 Webhook 通用桥接），让外部平台的 Agent 能接入 AgentNexus 网络。

当前问题：

1. **没有统一的适配器抽象** — 每接入一个平台就要从零写集成代码
2. **Skill 描述是手写的** — `agentnexus-sdk/skill.yaml` 是手工维护的静态文件，无法动态注册
3. **双向 Skill 需求** — Agent 既要对外暴露能力（"我能翻译"），也要从外部获取能力（"我能调用 OpenClaw 上的搜索 Skill"）。未来每个 Agent 都可能有自己的 Skill 描述，需要统一的注册和发现机制

### 现有架构

```
外部平台 Agent ──(平台私有协议)──> ???  ──(HTTP)──> AgentNexus Daemon
```

中间缺少适配层。

## 决策

### §1 PlatformAdapter 抽象基类

```python
# agent_net/adapters/base.py
from abc import ABC, abstractmethod

class PlatformAdapter(ABC):
    """平台适配器基类，将外部平台协议转换为 AgentNexus SDK 调用"""

    platform: str  # "openclaw" / "webhook" / "dify" / "coze"

    @abstractmethod
    async def inbound(self, request: dict) -> dict:
        """外部平台 → AgentNexus：将平台请求转换为 SDK 操作"""
        ...

    @abstractmethod
    async def outbound(self, message: dict) -> dict:
        """AgentNexus → 外部平台：将 SDK 事件推送到平台"""
        ...

    @abstractmethod
    def skill_manifest(self) -> dict:
        """返回此适配器暴露的 Skill 描述（标准格式）"""
        ...
```

### §2 Skill 描述标准格式

统一 Skill 描述格式，不再手写 yaml，由适配器和 Agent 动态生成：

```python
@dataclass
class SkillManifest:
    """标准化 Skill 描述，供发现和安装"""
    name: str                    # "translate" / "search" / "agentnexus-comm"
    version: str                 # "0.1.0"
    platform: str                # "openclaw" / "webhook" / "native"
    description: str
    capabilities: list[str]      # 高层能力标签，用于发现（如 ["Translation", "Chat"]）
    actions: list[str]           # 具体可调用操作，用于执行（如 ["translate_text", "detect_language"]）
    install: InstallSpec         # 安装方式
    auth: AuthSpec | None        # 认证要求
```

`capabilities` vs `actions` 的区别：
- `capabilities` 是发现层面的标签（"这个 Agent 能做翻译"），对应 NexusProfile 的 caps 字段，用于 `search(capability="Translation")`
- `actions` 是执行层面的操作名（"调用 translate_text 这个具体接口"），对应 Skill 调用时的 action 参数

### §3 SkillRegistry — Daemon 侧 Skill 注册表

Skill 是 Agent 级别的。一个 Daemon 上可以有多个 Agent，每个 Agent 有自己的 Skill 列表。

```python
class SkillRegistry:
    """Daemon 本地 Skill 注册表（Agent 级别）"""

    async def register(self, agent_did: str, manifest: SkillManifest) -> str:
        """注册 Skill，关联到具体 Agent，返回 skill_id"""

    async def unregister(self, skill_id: str) -> None:
        """注销 Skill"""

    async def list_skills(self, agent_did: str = None, capability: str = None) -> list[SkillManifest]:
        """列出已注册 Skill，可按 Agent 或能力过滤"""

    async def get_skill(self, skill_id: str) -> SkillManifest | None:
        """获取 Skill 详情"""
```

SQLite 表结构：
```sql
CREATE TABLE skills (
    skill_id   TEXT PRIMARY KEY,
    agent_did  TEXT NOT NULL REFERENCES agents(did),
    name       TEXT NOT NULL,
    actions    TEXT NOT NULL,  -- JSON array
    platform   TEXT DEFAULT 'native',
    created_at REAL NOT NULL
);
```

Agent 注册时声明 Skill：
```python
# skills 参数为 action 名称列表
nexus = await agentnexus.connect("Translator", caps=["Translation"], skills=["translate_text", "detect_language"])
# Daemon 自动写入 skills 表，关联 agent_did
```

其他 Agent 通过发现机制搜索 Skill：
```python
results = await nexus.search(capability="Translation")
# 返回的 Agent 列表中包含 skills 字段
```

### §4 OpenClaw 适配器

```python
# agent_net/adapters/openclaw.py
class OpenClawAdapter(PlatformAdapter):
    platform = "openclaw"

    def __init__(self, agent_did: str, router, storage):
        """
        适配器运行在 Daemon 进程内，通过内部服务操作。

        Args:
            agent_did: 绑定的 Agent DID
            router: Daemon 内部路由模块（agent_net.router）
            storage: Daemon 内部存储模块（agent_net.storage）
        """
        self.agent_did = agent_did
        self.router = router
        self.storage = storage

    async def inbound(self, request: dict) -> dict:
        """OpenClaw Skill 调用 → AgentNexus 内部操作"""
        action = request.get("action")
        handler = self._action_handlers.get(action)
        if not handler:
            raise ValueError(f"Unknown action: {action}")
        return await handler(self, request)

    # Action 路由表
    _action_handlers = {}

    @staticmethod
    def _register_action(name):
        def decorator(fn):
            OpenClawAdapter._action_handlers[name] = fn
            return fn
        return decorator

    @_register_action("invoke_skill")
    async def _handle_invoke(self, request: dict) -> dict:
        return await self.router.send_message(
            from_did=self.agent_did,
            to_did=request["target_did"],
            content=request["payload"],
            message_type="skill_invoke",
        )

    @_register_action("query_status")
    async def _handle_query(self, request: dict) -> dict:
        return await self.storage.get_agent_info(request["target_did"])

    async def outbound(self, message: dict) -> dict:
        """AgentNexus 消息 → OpenClaw Skill 回调"""
        return {
            "skill_id": message.get("skill_id"),
            "result": message.get("content"),
            "status": "completed",
        }

    def skill_manifest(self) -> dict:
        return {
            "name": f"agentnexus-openclaw",
            "platform": "openclaw",
            "agent_did": self.agent_did,
            "endpoint": "/adapters/openclaw/invoke",
        }
```

### §5 Webhook 通用适配器

```python
# agent_net/adapters/webhook.py
class WebhookAdapter(PlatformAdapter):
    platform = "webhook"

    def __init__(self, agent_did: str, router, storage, webhook_secret: str):
        self.agent_did = agent_did
        self.router = router
        self.storage = storage
        self.webhook_secret = webhook_secret
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """复用 HTTP session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def inbound(self, request: dict) -> dict:
        """Webhook POST → AgentNexus 消息"""
        self._verify_signature(request)
        return await self.router.send_message(
            from_did=self.agent_did,
            to_did=request["to_did"],
            content=request["body"],
        )

    async def outbound(self, message: dict) -> dict:
        """AgentNexus 消息 → Webhook 回调 POST"""
        session = await self._get_session()
        await session.post(
            message["callback_url"],
            json={"from_did": message["from_did"], "content": message["content"]},
            headers=self._sign_headers(message),
        )

    def _verify_signature(self, request: dict) -> None:
        """HMAC-SHA256 签名验证"""
        ...
```

### §6 Daemon 端点

```
POST /adapters/{platform}/invoke    — 外部平台调用入口（需 Bearer Token）
POST /adapters/{platform}/register  — 注册适配器（需 Bearer Token）
GET  /skills                        — 列出本地已注册 Skill（公开，无需鉴权）
GET  /skills/{skill_id}             — 获取 Skill 详情（公开，无需鉴权）
```

鉴权规则与现有 Daemon 端点一致：写操作需要 Bearer Token，读操作公开。

### §7 目录结构

```
agent_net/adapters/
├── __init__.py          # register_adapter(), AdapterRegistry
├── base.py              # PlatformAdapter ABC, SkillManifest
├── openclaw.py          # OpenClawAdapter
└── webhook.py           # WebhookAdapter

agent_net/node/
├── skill.py             # SkillRegistry（Daemon 本地功能，与 storage 同级）
```

## 理由

1. **统一抽象降低接入成本** — 新平台只需实现 `inbound/outbound/skill_manifest` 三个方法
2. **Skill 注册表支持动态发现** — 不再依赖手写 yaml，Agent 注册时自动声明能力，其他 Agent 可搜索
3. **双向适配** — inbound 处理外部→内部，outbound 处理内部→外部，覆盖两个方向
4. **与 ADR-009 模式一致** — Handler 注册表模式已在 DID 解析中验证，适配器复用同一模式

### 考虑的替代方案

1. **每个平台独立实现，无抽象层** — 开发快但重复代码多，第三个平台接入时成本线性增长。与 ADR-009 重构前的 if/elif 问题相同
2. **只做 Webhook，不做 Skill 注册** — 能解决 0.8-08 但无法支持 Agent 间的能力发现，未来 OpenClaw/Dify/Coze 每个都要单独处理
3. **Skill 描述放在 Relay 侧** — Relay 是无状态转发层，不应承担 Skill 管理职责。Skill 是 Agent 本地能力，归 Daemon 管理

## 影响范围

- **新增模块**：`agent_net/adapters/`（适配器目录）、`agent_net/node/skill.py`（Skill 注册表）
- **修改模块**：`agent_net/node/daemon.py`（新增 `/adapters/*` 和 `/skills` 端点）、`agent_net/storage.py`（新增 `skills` 表）
- **SDK 变更**：`connect()` 新增可选 `skills` 参数；`search()` 返回结果包含 skills 字段
- **数据库变更**：SQLite 新增 `skills` 表
- **现有 skill.yaml**：保留作为静态描述文件，但运行时以 SkillRegistry 为准

## 相关 ADR

- ADR-006: SDK 架构与 Daemon 通信协议 — SDK 是适配器的调用基础
- ADR-007: Action Layer 协作协议 — Skill 调用可映射为 `task_propose`
- ADR-009: DID Method Handler 注册表 — 注册表路由模式的先例

## 评审记录

| 日期 | 评审者 | 结果 | 备注 |
|------|--------|------|------|
| 2026-04-04 | 评审 Agent | 条件批准 | 阻塞性问题：B1 适配器实例化位置、B2 Skill 与 Agent 关系、B3 端点鉴权；建议性问题：S1-S4 |
| 2026-04-05 | 评审 Agent | 批准 | B1-B3 已修复，S1-S4 已修复 |
| 2026-04-05 | 开发 Agent | 批准 | 实现建议：skills 表增加 capabilities 列、Webhook secret 从环境变量读取 |

### 阻塞性问题详情

| # | 章节 | 问题描述 |
|---|------|---------|
| B1 | §4/§5 | 适配器实例化位置不明确：代码示例中适配器持有 `AgentNexusClient`，但 Daemon 端点是 HTTP 入口。适配器是在 Daemon 进程内还是独立进程？ |
| B2 | §3 | Skill 与 Agent 的关系不明确：`connect(skills=[...])` 中 skills 是什么格式？Skill 是 Agent 级别还是 Daemon 级别？ |
| B3 | §6 | 端点鉴权缺失：`/adapters/{platform}/invoke` 和 `/adapters/{platform}/register` 是否需要 Token？ |

### 建议性问题详情

| # | 章节 | 问题描述 |
|---|------|---------|
| S1 | §2 | `SkillManifest.actions` 与 `capabilities` 区别不够清晰 |
| S2 | §4 | OpenClaw `inbound` 只处理一种 action，其他 action 如何处理？ |
| S3 | §5 | Webhook `outbound` 每次新建 session，建议复用 |
| S4 | §7 | `skill.py` 放在 `common/` 还是 `node/`？建议明确 |

## 答疑记录

| 日期 | 提问者 | 问题 | 回复 | 是否触发设计变更 |
|------|--------|------|------|----------------|
| | | | | |
