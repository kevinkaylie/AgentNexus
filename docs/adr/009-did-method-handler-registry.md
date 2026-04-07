# ADR-009: DID Method Handler 注册表架构

## 状态

已采纳

## 日期

2026-04-04

## 背景

v0.7.x 的 `DIDResolver` 使用硬编码 `if/elif` 链处理不同 DID 方法（agentnexus、agent、key、web）。v0.8.0 引入 did:meeet 后，Relay 侧出现了第二处独立的 if 分支（`relay/server.py` 的 `resolve_did`），meeet 解析逻辑完全绕过了 `DIDResolver`。

随着 did:aps 及未来更多外部 DID 方法的接入，当前架构存在以下问题：

1. **两处分散的 if/elif 链**：`DIDResolver.resolve()` 和 `relay/server.py:resolve_did()` 各自维护一套方法分支，新增方法需改两处
2. **meeet 逻辑孤立**：`_resolve_meeet_via_solana` 是 Relay 私有函数，Daemon 侧若需解析 meeet DID 需重复实现
3. **扩展成本线性增长**：每新增一个 DID 方法，需要修改核心文件，违反开闭原则

## 决策

### 1. 引入 DIDMethodHandler 抽象基类

```python
# agent_net/common/did_methods/base.py
from abc import ABC, abstractmethod
from agent_net.common.did import DIDResolutionResult

class DIDMethodHandler(ABC):
    method: str  # 子类必须声明，如 "agentnexus" / "meeet" / "aps"

    @abstractmethod
    async def resolve(self, did: str, method_specific_id: str) -> DIDResolutionResult:
        """解析 DID，返回 DIDResolutionResult，失败时抛出 DIDError 子类"""
        ...
```

**依赖注入**：需要外部依赖（db_path、redis_client）的 handler 通过 `__init__()` 接收，不污染 `resolve()` 接口契约。

### 2. DIDResolver 改为注册表路由

```python
# agent_net/common/did.py — DIDResolver 核心逻辑
class DIDResolver:
    _handlers: dict[str, DIDMethodHandler] = {}

    def __init__(self):
        pass  # 无需 db_path，依赖通过 handler 构造函数注入

    @classmethod
    def register(cls, handler: DIDMethodHandler) -> None:
        cls._handlers[handler.method] = handler

    @classmethod
    def reset_handlers(cls) -> None:
        """仅用于测试：清空所有已注册 handler，防止测试间状态污染"""
        cls._handlers.clear()

    async def resolve(self, did: str) -> DIDResolutionResult:
        parts = did.split(":", 2)
        if len(parts) < 3 or parts[0] != "did":
            raise DIDMethodUnsupportedError(f"Invalid DID format: '{did}'")
        method = parts[1]
        handler = self._handlers.get(method)
        if not handler:
            raise DIDMethodUnsupportedError(f"Unsupported DID method: '{method}'")
        return await handler.resolve(did, parts[2])
```

**依赖注入**：`AgentLegacyHandler` 通过 `__init__(db_path=...)` 接收数据库路径，`MeeetHandler` 通过 `__init__(redis_client=...)` 接收 Redis 连接。注册时传入依赖，`resolve()` 签名保持简洁。

### 3. 现有方法迁移为独立 Handler

```
agent_net/common/did_methods/
├── base.py              # DIDMethodHandler 抽象基类（含 resolve 抽象方法）
├── utils.py             # 共用工具方法：_build_did_document、_extract_ed25519_key_from_doc
├── agentnexus.py        # AgentNexusHandler（从 DIDResolver._resolve_agentnexus 迁移）
├── agent_legacy.py      # AgentLegacyHandler（从 DIDResolver._resolve_agent 迁移，需 db_path）
├── key.py               # KeyHandler（从 DIDResolver._resolve_key 迁移）
├── web.py               # WebHandler（从 DIDResolver._resolve_web 迁移）
└── meeet.py             # MeeetHandler（从 relay/server.py 迁移）
```

`_build_did_document` 和 `_extract_ed25519_key_from_doc` 放入 `utils.py`，各 handler 按需 import，不放入基类（基类只定义接口契约，不承载实现）。

### 4. Handler 注册在模块初始化时完成

```python
# agent_net/common/did_methods/__init__.py
from agent_net.common.did import DIDResolver
from .agentnexus import AgentNexusHandler
from .agent_legacy import AgentLegacyHandler
from .key import KeyHandler
from .web import WebHandler
from .meeet import MeeetHandler

def register_daemon_handlers(db_path: str):
    """Daemon 启动时调用，注册所有 Daemon 侧需要的 handler"""
    DIDResolver.register(AgentNexusHandler())
    DIDResolver.register(AgentLegacyHandler(db_path=db_path))
    DIDResolver.register(KeyHandler())
    DIDResolver.register(WebHandler())

def register_relay_handlers(redis_client):
    """Relay 启动时调用，注册所有 Relay 侧需要的 handler（含 MeeetHandler）"""
    DIDResolver.register(AgentNexusHandler())
    DIDResolver.register(KeyHandler())
    DIDResolver.register(WebHandler())
    DIDResolver.register(MeeetHandler(redis_client=redis_client))
```

- `AgentLegacyHandler` 仅在 Daemon 侧注册，通过构造函数接收 `db_path`
- `MeeetHandler` 仅在 Relay 侧注册，通过构造函数接收 `redis_client`
- 两侧不会出现 `db_path=None` 或 `redis_client=None` 的问题

### 5. Relay 侧 resolve_did 简化

`relay/server.py` 的 `resolve_did` 移除 meeet 专用分支，统一走 `DIDResolver`：

```python
async def resolve_did(did: str):
    resolver = DIDResolver()
    # 优先级 1: 本地注册表
    # 优先级 2: PeerDirectory
    # 优先级 3: DIDResolver（含所有已注册方法，包括 meeet、aps 等）
    try:
        result = await resolver.resolve(did)
        return {"didDocument": result.did_document, "source": "resolver"}
    except DIDError:
        raise HTTPException(status_code=404, ...)
```

### 6. 新增 DID 方法的标准流程

未来接入 did:aps 或其他方法：

1. 新建 `agent_net/common/did_methods/aps.py`，实现 `APSHandler(DIDMethodHandler)`
2. 在 `__init__.py` 的 `register_default_handlers()` 中添加一行
3. 不修改 `DIDResolver`、不修改 `relay/server.py`

## 理由

### 为什么选择注册表模式而不是其他方案

| 维度 | 注册表模式（本方案） | 继续扩展 if/elif | 插件系统（动态加载） |
|------|-------------------|----------------|-------------------|
| 新增方法改动范围 | 仅新文件 + 1 行注册 | 修改核心文件 | 新文件 + 配置文件 |
| 现有代码破坏风险 | 零（平移逻辑） | 低（但累积风险） | 中（动态加载复杂） |
| 测试隔离性 | 每个 handler 独立测试 | 共享测试文件膨胀 | 好，但过度设计 |
| 实现复杂度 | 低 | 最低 | 高 |
| 适合当前规模 | ✅ | 勉强 | ❌ 过度设计 |

### 向后兼容保证

- `DIDResolver.resolve(did)` 签名不变
- `DIDResolutionResult` 结构不变
- 所有调用方（Daemon、Relay、Gatekeeper、RuntimeVerifier、SDK）零改动
- 现有测试全部继续有效

## 影响范围

- `agent_net/common/did.py`：`DIDResolver` 改为注册表路由，移除 `_resolve_*` 私有方法
- `agent_net/common/did_methods/`：新增目录，包含 5 个 handler 文件 + `__init__.py`
- `agent_net/relay/server.py`：移除 meeet 专用 if 分支，`_resolve_meeet_via_solana` 迁移到 `MeeetHandler`
- `agent_net/node/daemon.py`：启动时调用 `register_daemon_handlers(db_path)`
- `agent_net/relay/server.py`：启动时调用 `register_relay_handlers(redis_client)`，移除 meeet 专用 if 分支
- 现有调用方（Gatekeeper、RuntimeVerifier、SDK）：**零改动**

## 测试要求

| 测试场景 | 类型 | 说明 |
|---------|------|------|
| 现有 `TestDIDResolver` 全部通过 | 回归 | 重构后行为不变 |
| 未注册方法抛出 `DIDMethodUnsupportedError` | 单元 | 注册表路由正确 |
| 注册自定义 handler 后可解析新方法 | 单元 | 扩展点验证 |
| `reset_handlers()` 后注册表为空 | 单元 | 测试隔离机制验证 |
| 测试 fixture 使用 `reset_handlers()` 清理状态 | 单元 | 防止测试间污染 |
| MeeetHandler 迁移后 meeet 解析行为不变 | 回归 | relay 侧 meeet 测试重跑 |
| `AgentLegacyHandler` 正确接收并使用 `db_path` | 单元 | db_path 透传验证 |
| 其他 handler 忽略 `db_path` 不报错 | 单元 | 默认参数兼容性 |
| Daemon 启动后所有默认方法可解析 | 集成 | `register_daemon_handlers()` 验证 |
| Relay 启动后 meeet 可解析，did:agent 不可解析 | 集成 | `register_relay_handlers()` 验证 |

## 相关 ADR

- ADR-001: DID 格式选择（did:agentnexus 是主方法，本 ADR 不改变其格式）
- ADR-008: did:meeet 跨平台桥接（MeeetHandler 是 ADR-008 的实现载体）

## 评审记录

| 日期 | 评审者 | 结果 | 备注 |
|------|--------|------|------|
| 2026-04-04 | 评审 Agent #1 | 条件批准 | 阻塞：需补充 `_handlers` 测试隔离方案（`reset_handlers()` 或等效机制）；建议：明确 `db_path` 传递路径、共用工具方法归属 |
| 2026-04-04 | 设计 Agent | 已修复 | 新增 `reset_handlers()`；`db_path` 通过 `resolve()` 透传给 handler；共用方法移入 `utils.py` |
| 2026-04-04 | 评审 Agent #2 | 批准 | 建议：`reset_handlers()` 改用 `cls._handlers.clear()` 而非重新赋值；§1 的 `resolve` 签名需同步更新为含 `db_path` 参数版本 |

## 答疑记录

| 日期 | 提问者 | 问题 | 回复 | 是否触发设计变更 |
|------|--------|------|------|----------------|
| 2026-04-04 | 开发 Agent | Q1: `MeeetHandler` 需要访问 Redis，但 `resolve()` 签名只接受 `did`、`method_specific_id`、`db_path`。Redis 连接如何传递？是否需要在签名中增加 `redis_client` 参数，还是通过 `__init__()` 注入？ | 通过 `__init__()` 注入：`MeeetHandler(redis_client=_redis)`。不在 `resolve()` 签名加 `redis_client`——那会污染所有 handler 的接口契约，而只有 meeet 需要 Redis。`register_default_handlers()` 在 Relay 启动后调用，此时 `_redis` 已初始化，直接传入即可。Daemon 侧不注册 `MeeetHandler`，无需关心。 | 否 |
| 2026-04-04 | 开发 Agent | Q2: Relay `resolve_did` 的优先级逻辑（本地注册表 → PeerDirectory → DIDResolver）与 `did:meeet` 当前行为的关系？`MeeetHandler` 是否需要先查 `meeet:mapping:` 再查 Solana？ | 是的，`MeeetHandler` 内部保留现有的两步逻辑：先查 Redis `meeet:mapping:{did}` 缓存，命中直接返回；未命中再调 Solana API，写缓存后返回。这是 `_resolve_meeet_via_solana` 的原有行为，平移进 handler 即可，不改变逻辑。Relay 的优先级链（本地注册表 → PeerDirectory → DIDResolver）对 meeet 不适用——meeet DID 不会出现在本地注册表或 PeerDirectory 里，所以实际上会直接落到 DIDResolver 分支，由 `MeeetHandler` 处理。 | 否 |
| 2026-04-04 | 开发 Agent | Q3: `reset_handlers()` 是否确认改用 `cls._handlers.clear()` 而非重新赋值？ | 确认，改用 `cls._handlers.clear()`。评审 Agent #2 的建议正确，语义更清晰且不破坏引用。 | 是（实现细节，不影响接口） |
| 2026-04-04 | 开发 Agent | Q4: `AgentLegacyHandler` 需要 `db_path`，但 Relay 侧没有本地 SQLite。Relay 调用时 `db_path` 传什么？是否传 `None` 并抛出 `DIDError`？ | Relay 不注册 `AgentLegacyHandler`。`did:agent` 是向后兼容的旧格式，只在 Daemon 本地有意义，Relay 从不需要解析它。`register_default_handlers()` 拆分为两个函数：`register_daemon_handlers(db_path)` 含 AgentLegacyHandler；`register_relay_handlers(redis_client)` 不含。这样各自只注册自己需要的方法，不存在 `db_path=None` 的问题。 | 是 — `register_default_handlers()` 拆分为 daemon/relay 两个版本 |
