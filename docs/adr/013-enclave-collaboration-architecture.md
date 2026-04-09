# ADR-013: Enclave 协作架构（项目组 + VaultBackend + Playbook 引擎）

## 状态

已采纳（2026-04-09）

## 日期

2026-04-09

## 背景

### 问题

AgentNexus 已具备完整的通信基础设施（L0-L8 协议栈）和协作原语（propose_task / claim_task / notify_state / discussion），但缺少**项目级协作编排**能力。

当前的协作模式是"临时拼凑"：

```
秘书收到"开发登录功能"
→ search_agents(keyword="Design") → 临时找一个
→ propose_task → 发一条消息
→ 等人类切换到另一个 AI 工具 → fetch_inbox → 手动认领
```

问题：
1. **无共享上下文**：每个 Agent 独立工作，不知道项目背景、不知道彼此的产出物
2. **无角色绑定**：每次临时搜索，Agent 不知道自己在项目中的职责
3. **无流程编排**：秘书需要手动逐步分发任务，无法定义"设计完成后自动触发开发"
4. **无产出物管理**：设计文档、代码、评审记录散落在各 Agent 的消息中

### 真实参照

本项目（AgentNexus）的多 Agent 协作模式就是目标形态：

| 现有实践 | 对应概念 |
|---------|---------|
| `AGENTS.md` 定义角色和阅读顺序 | Enclave 成员 + 角色 |
| `docs/` 目录共享文档 | Vault（Git 仓库） |
| `docs/processes/design-review.md` 定义评审流程 | Playbook |
| `docs/wip.md` 追踪任务状态 | Enclave 运行时状态 |

### 需求来源

- R-0851: Relay Vault（共享内存桶）
- R-0852: Enclave 群组
- R-0853: 基于 DID 的 RBAC

## 决策

引入三个核心概念：**Enclave**（项目组）、**VaultBackend**（可插拔文档存储）、**Playbook**（流程编排引擎）。

### §1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                      Enclave（项目组）                        │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Members + Roles                                     │    │
│  │ architect: did_a  developer: did_b  reviewer: did_c │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌──────────────────────┐  ┌────────────────────────────┐   │
│  │ VaultBackend         │  │ Playbook Engine            │   │
│  │ (文档/产出物)         │  │ (流程编排)                  │   │
│  │                      │  │                            │   │
│  │ ┌──────────────────┐ │  │ design → review → impl    │   │
│  │ │ GitVaultBackend  │ │  │    ↑ reject    ↓           │   │
│  │ │ (默认)           │ │  │    └──────────┘            │   │
│  │ └──────────────────┘ │  └────────────────────────────┘   │
│  └──────────────────────┘                                   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Runtime State（运行时状态，Daemon SQLite）            │    │
│  │ 任务进度 / Playbook 当前阶段 / 成员在线状态          │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
         │                              │
         │ Vault 操作                    │ 任务消息
         ▼                              ▼
  Git / Notion / S3 / ...        L7 协作层（propose_task 等）
```

### §2 Enclave 数据模型

#### 核心表（Daemon SQLite）

```sql
-- Enclave 项目组
CREATE TABLE enclaves (
    enclave_id TEXT PRIMARY KEY,         -- enc_{uuid}
    name TEXT NOT NULL,
    owner_did TEXT NOT NULL,
    status TEXT DEFAULT 'active',        -- active / paused / archived
    vault_backend TEXT DEFAULT 'git',    -- git / local / notion / s3
    vault_config TEXT DEFAULT '{}',      -- JSON: backend 配置
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

-- 成员 + 角色
CREATE TABLE enclave_members (
    enclave_id TEXT NOT NULL,
    did TEXT NOT NULL,
    role TEXT NOT NULL,                  -- 自定义角色名
    permissions TEXT DEFAULT 'rw',       -- r / rw / admin
    handbook TEXT,                       -- 角色职责说明
    joined_at REAL NOT NULL,
    PRIMARY KEY (enclave_id, did),
    FOREIGN KEY (enclave_id) REFERENCES enclaves(enclave_id)
);

-- Playbook 定义（可复用）
CREATE TABLE playbooks (
    playbook_id TEXT PRIMARY KEY,        -- pb_{uuid}
    name TEXT NOT NULL,
    stages TEXT NOT NULL,                -- JSON: 阶段定义数组
    created_by TEXT NOT NULL,
    created_at REAL NOT NULL
);

-- Playbook 执行实例
CREATE TABLE playbook_runs (
    run_id TEXT PRIMARY KEY,             -- run_{uuid}
    enclave_id TEXT NOT NULL,
    playbook_id TEXT NOT NULL,
    current_stage TEXT,                  -- 当前阶段名
    status TEXT DEFAULT 'running',       -- running / paused / completed / failed
    context TEXT DEFAULT '{}',           -- JSON: 运行时上下文
    started_at REAL NOT NULL,
    completed_at REAL,
    FOREIGN KEY (enclave_id) REFERENCES enclaves(enclave_id),
    FOREIGN KEY (playbook_id) REFERENCES playbooks(playbook_id)
);

-- 阶段执行记录
CREATE TABLE stage_executions (
    run_id TEXT NOT NULL,
    stage_name TEXT NOT NULL,
    assigned_did TEXT,                   -- 执行者 DID
    status TEXT DEFAULT 'pending',       -- pending / active / completed / rejected / skipped
    task_id TEXT,                        -- 关联的 task_id
    output_ref TEXT,                     -- 产出物引用（vault key 或 git commit）
    started_at REAL,
    completed_at REAL,
    PRIMARY KEY (run_id, stage_name),
    FOREIGN KEY (run_id) REFERENCES playbook_runs(run_id)
);

-- 索引
CREATE INDEX idx_enclaves_owner ON enclaves(owner_did);
CREATE INDEX idx_enclaves_status ON enclaves(status);
CREATE INDEX idx_enclave_members_did ON enclave_members(did);
CREATE INDEX idx_playbook_runs_enclave ON playbook_runs(enclave_id);
CREATE INDEX idx_playbook_runs_status ON playbook_runs(status);
CREATE INDEX idx_stage_executions_task ON stage_executions(task_id);
```

> `idx_enclave_members_did`：按 DID 查"我参与的所有 Enclave"。
> `idx_stage_executions_task`：Daemon 拦截 `notify_state` 时按 `task_id` 反查关联的 Playbook 阶段。

#### Enclave 生命周期

```
create → active → (paused) → archived
                      ↑
                      └── resume
```

### §3 VaultBackend 抽象接口

#### 错误类型

```python
class VaultError(Exception):
    """Vault 操作基础异常"""

class VaultKeyNotFoundError(VaultError):
    """文档不存在"""

class VaultPermissionError(VaultError):
    """权限不足"""

class VaultBackendError(VaultError):
    """后端操作失败（Git 命令失败、文件 I/O 错误等）"""
```

#### 接口定义

```python
from dataclasses import dataclass, field
from typing import Optional
from abc import ABC, abstractmethod


@dataclass
class VaultEntry:
    key: str
    value: str                    # 文本内容或 JSON（list 时为空串）
    version: str                  # Git: commit hash / Local: 自增整数字符串
    updated_by: str               # DID
    updated_at: float             # Unix timestamp
    message: str = ""             # 变更说明


class VaultBackend(ABC):
    """Enclave 文档存储抽象接口"""

    @abstractmethod
    async def get(self, key: str, version: Optional[str] = None) -> VaultEntry:
        """
        读取文档。

        Args:
            key: 文档键名
            version: 指定版本（None=最新）

        Returns:
            VaultEntry（含 value）

        Raises:
            VaultKeyNotFoundError: key 不存在
            VaultBackendError: 后端操作失败
        """

    @abstractmethod
    async def put(self, key: str, value: str, author_did: str,
                  message: str = "") -> VaultEntry:
        """
        写入文档（创建或更新）。

        Args:
            key: 文档键名（允许 / 分隔的路径，如 "design/api-spec"）
            value: 文档内容
            author_did: 作者 DID
            message: 变更说明（Git backend 用作 commit message）

        Returns:
            新版本的 VaultEntry（value 为空串，节省带宽）

        Raises:
            VaultBackendError: 后端操作失败
        """

    @abstractmethod
    async def list(self, prefix: str = "") -> list[VaultEntry]:
        """
        列出文档（仅元数据，value 为空串）。

        Args:
            prefix: 键名前缀过滤

        Returns:
            VaultEntry 列表（按 key 字母序）
        """

    @abstractmethod
    async def history(self, key: str, limit: int = 10) -> list[VaultEntry]:
        """
        查看文档变更历史（按时间倒序）。

        Args:
            key: 文档键名
            limit: 最大返回条数

        Returns:
            VaultEntry 列表（含 value 为空串，仅元数据）

        Raises:
            VaultKeyNotFoundError: key 不存在
        """

    @abstractmethod
    async def delete(self, key: str, author_did: str) -> bool:
        """
        删除文档。

        Returns:
            True=已删除，False=key 不存在
        """
```

#### 内置实现

##### GitVaultBackend

```python
class GitVaultBackend(VaultBackend):
    """
    基于 Git 仓库的 Vault 实现。

    文件布局：{repo_path}/{vault_dir}/{key}
    key 中的 / 映射为目录层级。

    配置：
        repo_path: 本地仓库路径（必填）
        remote: 远程仓库 URL（可选，用于跨机器同步）
        branch: 分支名（默认 main）
        vault_dir: Vault 文件存放子目录（默认 .vault/）
    """

    def __init__(self, repo_path: str, remote: str = None,
                 branch: str = "main", vault_dir: str = ".vault"):
        self.repo_path = repo_path
        self.remote = remote
        self.branch = branch
        self.vault_dir = vault_dir

    async def put(self, key: str, value: str, author_did: str,
                  message: str = "") -> VaultEntry:
        # 1. 写文件到 {repo_path}/{vault_dir}/{key}
        # 2. git add + git commit -m "{message}" --author="{author_did}"
        # 3. 如果有 remote: git push
        # 4. 返回 VaultEntry(version=commit_hash)
        ...

    async def get(self, key: str, version: str = None) -> Optional[VaultEntry]:
        # version=None: 读当前文件
        # version=commit_hash: git show {hash}:{vault_dir}/{key}
        ...

    async def history(self, key: str, limit: int = 10) -> list[VaultEntry]:
        # git log --follow -n {limit} -- {vault_dir}/{key}
        ...
```

映射关系：

| VaultBackend 操作 | Git 操作 |
|------------------|---------|
| `put(key, value)` | write file → `git add` → `git commit` |
| `get(key)` | read file |
| `get(key, version)` | `git show {version}:{path}` |
| `list(prefix)` | `ls {vault_dir}/{prefix}` |
| `history(key)` | `git log -- {path}` |
| `delete(key)` | `rm` → `git add` → `git commit` |

##### LocalVaultBackend（零配置）

```python
class LocalVaultBackend(VaultBackend):
    """
    基于 Daemon SQLite 的 Vault 实现。
    零配置，适合单机简单场景。

    数据存储在 enclave_vault 表中。
    """
```

```sql
CREATE TABLE enclave_vault (
    enclave_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    version INTEGER DEFAULT 1,       -- 自增版本号
    updated_by TEXT NOT NULL,
    updated_at REAL NOT NULL,
    message TEXT DEFAULT '',
    PRIMARY KEY (enclave_id, key)
);

-- 历史版本（append-only）
CREATE TABLE enclave_vault_history (
    enclave_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    version INTEGER NOT NULL,
    updated_by TEXT NOT NULL,
    updated_at REAL NOT NULL,
    message TEXT DEFAULT ''
);
```

#### Backend 注册

```python
_VAULT_BACKENDS: dict[str, type[VaultBackend]] = {}

def register_vault_backend(name: str, cls: type[VaultBackend]):
    _VAULT_BACKENDS[name] = cls

def create_vault_backend(name: str, config: dict) -> VaultBackend:
    cls = _VAULT_BACKENDS.get(name)
    if not cls:
        raise ValueError(f"Unknown vault backend: {name}")
    return cls(**config)

# 内置注册
register_vault_backend("git", GitVaultBackend)
register_vault_backend("local", LocalVaultBackend)
```

### §4 Playbook 引擎

#### 阶段定义

```python
@dataclass
class Stage:
    name: str                          # 阶段名（唯一）
    role: str                          # 执行角色
    description: str = ""              # 任务描述
    input_keys: list[str] = None       # 依赖的 Vault key（前置阶段产出物）
    output_key: str = None             # 本阶段产出物的 Vault key
    next: str = None                   # 成功后的下一阶段
    on_reject: str = None              # 被拒绝后回退到的阶段
    timeout_seconds: int = 0           # 超时时间（0=不限）

@dataclass
class Playbook:
    name: str
    stages: list[Stage]
    description: str = ""
```

#### 执行引擎

```python
class PlaybookEngine:
    """
    Playbook 执行引擎。

    职责：
    1. 根据阶段定义，向对应角色的 Agent 发送 task_propose
    2. 监听 notify_state(completed/rejected)，推进到下一阶段
    3. 处理超时、回退、跳过
    """

    async def start(self, enclave_id: str, playbook_id: str) -> str:
        """启动 Playbook，返回 run_id"""

    async def on_stage_completed(self, run_id: str, stage_name: str,
                                  output_ref: str = None):
        """阶段完成回调 → 推进到下一阶段"""

    async def on_stage_rejected(self, run_id: str, stage_name: str,
                                 reason: str = ""):
        """阶段被拒绝 → 回退到 on_reject 阶段"""

    async def get_status(self, run_id: str) -> dict:
        """查询 Playbook 执行状态"""
```

#### 执行流程

```
PlaybookEngine.start()
  │
  ├── 1. 创建 playbook_runs 记录
  ├── 2. 找到第一个 stage
  ├── 3. 查 enclave_members 找到该 role 的 DID
  ├── 4. propose_task(to_did, title=stage.description)
  ├── 5. 创建 stage_executions 记录（status=active）
  │
  │   ... Agent 执行任务 ...
  │
  ├── Agent 调用 notify_state(status="completed")
  │   └── PlaybookEngine.on_stage_completed()
  │       ├── 更新 stage_executions（status=completed）
  │       ├── 如果有 output_key → 记录 output_ref
  │       └── 推进到 stage.next → 回到步骤 3
  │
  ├── Agent 调用 notify_state(status="rejected")
  │   └── PlaybookEngine.on_stage_rejected()
  │       ├── 更新 stage_executions（status=rejected）
  │       └── 回退到 stage.on_reject → 回到步骤 3
  │
  └── 最后一个 stage 完成 → playbook_runs.status = completed
```

#### 与 L7 协作层的集成

Playbook 引擎复用现有 `propose_task` / `notify_state`，通过 content 中的扩展字段关联 Enclave 上下文。

##### 引擎发出的 task_propose content 结构

```json
{
  "task_id": "task_abc123",
  "title": "根据需求文档输出技术设计方案",
  "enclave_id": "enc_xyz789",
  "run_id": "run_def456",
  "stage_name": "design",
  "input_keys": ["requirements"],
  "output_key": "design_doc",
  "message_type": "task_propose",
  "protocol": "nexus_v1"
}
```

新增字段（`enclave_id` / `run_id` / `stage_name` / `input_keys` / `output_key`）是可选的——没有这些字段的 `task_propose` 仍然是普通任务，有这些字段的是 Playbook 驱动的任务。

##### Agent 回复的 notify_state content 结构

```json
// 完成
{
  "status": "completed",
  "task_id": "task_abc123",
  "output_ref": "design_doc",
  "message_type": "state_notify",
  "protocol": "nexus_v1"
}

// 拒绝（评审不通过）
{
  "status": "rejected",
  "task_id": "task_abc123",
  "reason": "设计方案缺少错误处理流程",
  "message_type": "state_notify",
  "protocol": "nexus_v1"
}
```

##### Daemon 侧的消息拦截

```python
# daemon.py send_message 端点中
async def _intercept_playbook_state(msg):
    """拦截 state_notify，检查是否关联 Playbook 并推进"""
    if msg.message_type != "state_notify":
        return
    task_id = msg.content.get("task_id")
    if not task_id:
        return

    # 查找关联的 stage_execution
    execution = await get_stage_execution_by_task_id(task_id)
    if not execution:
        return  # 普通任务，不是 Playbook 驱动的

    status = msg.content.get("status")
    if status == "completed":
        await playbook_engine.on_stage_completed(
            execution["run_id"], execution["stage_name"],
            output_ref=msg.content.get("output_ref"))
    elif status == "rejected":
        await playbook_engine.on_stage_rejected(
            execution["run_id"], execution["stage_name"],
            reason=msg.content.get("reason", ""))
```

这样 Playbook 引擎对 Agent 侧完全透明——Agent 只需要正常使用 `notify_state(status="completed")` 或 `notify_state(status="rejected")`，Daemon 自动检测并推进流程。

#### 示例：标准开发流程

```python
standard_dev = Playbook(
    name="标准开发流程",
    stages=[
        Stage(
            name="design",
            role="architect",
            description="根据需求文档输出技术设计方案",
            input_keys=["requirements"],
            output_key="design_doc",
            next="review_design",
        ),
        Stage(
            name="review_design",
            role="reviewer",
            description="评审设计方案",
            input_keys=["design_doc"],
            next="implement",
            on_reject="design",
        ),
        Stage(
            name="implement",
            role="developer",
            description="根据设计方案实现代码",
            input_keys=["design_doc"],
            output_key="code_diff",
            next="review_code",
        ),
        Stage(
            name="review_code",
            role="reviewer",
            description="代码评审",
            input_keys=["code_diff"],
            next="done",
            on_reject="implement",
        ),
        Stage(name="done", role="architect", description="确认完成"),
    ],
)
```

### §5 Daemon 端点

所有写端点需 Bearer Token。Vault 操作额外检查成员权限（`permissions` 字段）。

#### 端点总览

```
# Enclave 管理
POST   /enclaves                    创建 Enclave
GET    /enclaves                    列出我参与的 Enclave
GET    /enclaves/{id}               获取 Enclave 详情
PATCH  /enclaves/{id}               更新 Enclave（名称、状态）
DELETE /enclaves/{id}               归档 Enclave

# 成员管理
POST   /enclaves/{id}/members       添加成员
DELETE /enclaves/{id}/members/{did}  移除成员
PATCH  /enclaves/{id}/members/{did}  更新角色/权限

# Vault 操作
GET    /enclaves/{id}/vault              列出文档
GET    /enclaves/{id}/vault/{key:path}   读取文档
PUT    /enclaves/{id}/vault/{key:path}   写入文档
DELETE /enclaves/{id}/vault/{key:path}   删除文档
GET    /enclaves/{id}/vault/{key:path}/history  文档历史

# Playbook 执行
POST   /enclaves/{id}/runs           启动 Playbook
GET    /enclaves/{id}/runs/{run_id}  查询执行状态
```

> `{key:path}` 表示 FastAPI path converter，支持 `design/api-spec` 这样的多级 key。

#### 关键端点请求/响应

##### POST /enclaves

```json
// 请求
{
  "name": "登录功能开发",
  "owner_did": "did:agentnexus:z6Mk...secretary",
  "vault_backend": "git",
  "vault_config": {"repo_path": "/path/to/project", "vault_dir": ".vault"},
  "members": {
    "architect": {"did": "did:agentnexus:z6Mk...a", "handbook": "输出设计方案", "permissions": "rw"},
    "developer": {"did": "did:agentnexus:z6Mk...b", "permissions": "rw"},
    "reviewer":  {"did": "did:agentnexus:z6Mk...c", "permissions": "r"}
  }
}

// 响应 200
{
  "status": "ok",
  "enclave_id": "enc_a1b2c3d4e5f6"
}
```

##### PUT /enclaves/{id}/vault/{key:path}

```json
// 请求
{
  "value": "# 需求文档\n\n用户需要邮箱+密码登录...",
  "author_did": "did:agentnexus:z6Mk...secretary",
  "message": "初始需求文档"
}

// 响应 200
{
  "status": "ok",
  "key": "requirements",
  "version": "abc123",
  "updated_at": 1712649600.0
}

// 响应 403（权限不足）
{"detail": "Read-only access"}
```

##### GET /enclaves/{id}/vault/{key:path}

```json
// 响应 200
{
  "status": "ok",
  "key": "requirements",
  "value": "# 需求文档\n\n用户需要邮箱+密码登录...",
  "version": "abc123",
  "updated_by": "did:agentnexus:z6Mk...secretary",
  "updated_at": 1712649600.0,
  "message": "初始需求文档"
}

// 响应 404
{"detail": "Key not found: requirements"}
```

##### POST /enclaves/{id}/runs

```json
// 请求（内联 Playbook）
{
  "playbook": {
    "name": "标准开发流程",
    "stages": [
      {"name": "design", "role": "architect", "description": "输出设计方案",
       "input_keys": ["requirements"], "output_key": "design_doc", "next": "review_design"},
      {"name": "review_design", "role": "reviewer", "description": "评审设计方案",
       "input_keys": ["design_doc"], "next": "implement", "on_reject": "design"},
      {"name": "implement", "role": "developer", "description": "实现代码",
       "input_keys": ["design_doc"], "output_key": "code_diff", "next": "review_code"},
      {"name": "review_code", "role": "reviewer", "description": "代码评审",
       "input_keys": ["code_diff"], "next": "done", "on_reject": "implement"},
      {"name": "done", "role": "architect", "description": "确认完成"}
    ]
  }
}

// 响应 200
{
  "status": "ok",
  "run_id": "run_x1y2z3",
  "current_stage": "design",
  "assigned_did": "did:agentnexus:z6Mk...a"
}
```

##### GET /enclaves/{id}/runs/{run_id}

```json
// 响应 200
{
  "status": "ok",
  "run_id": "run_x1y2z3",
  "playbook_name": "标准开发流程",
  "current_stage": "implement",
  "run_status": "running",
  "stages": {
    "design":        {"status": "completed", "assigned_did": "did:...a", "output_ref": "design_doc"},
    "review_design": {"status": "completed", "assigned_did": "did:...c"},
    "implement":     {"status": "active",    "assigned_did": "did:...b", "task_id": "task_abc"},
    "review_code":   {"status": "pending"},
    "done":          {"status": "pending"}
  },
  "started_at": 1712649600.0
}
```

### §6 MCP 工具（6 个新增）

工具总数：27（现有）+ 6 = 33。

#### 实现方式

与 ADR-012 §6 一致：所有工具通过 HTTP 调用 Daemon 端点，MCP 层不直接操作存储。

```python
# mcp_server.py 中的实现模式
case "create_enclave":
    if not _MY_DID:
        result = {"error": "No DID bound — start with --name"}
    else:
        result = await _call("post", "/enclaves", json={
            "owner_did": _MY_DID,
            **arguments,
        })
```

#### 返回值格式

| 工具 | 成功返回 | 错误返回 |
|------|---------|---------|
| `create_enclave` | `{status, enclave_id}` | `{error: "..."}` |
| `vault_get` | `{status, key, value, version, updated_by}` | `{error: "not_found"}` |
| `vault_put` | `{status, key, version}` | `{error: "permission_denied"}` |
| `vault_list` | `{status, entries: [{key, version, updated_at}]}` | `{error: "..."}` |
| `run_playbook` | `{status, run_id, current_stage}` | `{error: "..."}` |
| `get_run_status` | `{status, run_id, current_stage, stages: {...}}` | `{error: "not_found"}` |

#### 工具定义

##### create_enclave

```python
Tool(name="create_enclave",
     description="Create an Enclave (project team) with members, roles, and shared Vault.",
     inputSchema={"type": "object",
                  "properties": {
                      "name": {"type": "string", "description": "Enclave name (e.g. 'Login Feature Dev')"},
                      "members": {
                          "type": "object",
                          "description": "Role-to-DID mapping. Key=role name, value=object with did and optional handbook",
                          "additionalProperties": {
                              "type": "object",
                              "properties": {
                                  "did": {"type": "string", "description": "Agent DID for this role"},
                                  "handbook": {"type": "string", "description": "Role responsibilities"},
                                  "permissions": {"type": "string", "enum": ["r", "rw", "admin"], "description": "Default: rw"},
                              },
                              "required": ["did"],
                          },
                      },
                      "vault_backend": {"type": "string", "enum": ["git", "local"],
                                        "description": "Vault storage backend (default: local)"},
                      "vault_config": {
                          "type": "object",
                          "description": "Backend-specific config. git: {repo_path, branch}. local: {}",
                      },
                  }, "required": ["name", "members"]})
```

##### vault_get

```python
Tool(name="vault_get",
     description="Read a document from Enclave Vault. Returns content and version.",
     inputSchema={"type": "object",
                  "properties": {
                      "enclave_id": {"type": "string", "description": "Enclave ID"},
                      "key": {"type": "string", "description": "Document key (e.g. 'requirements', 'design_doc')"},
                      "version": {"type": "string", "description": "Specific version (omit for latest)"},
                  }, "required": ["enclave_id", "key"]})
```

##### vault_put

```python
Tool(name="vault_put",
     description="Write a document to Enclave Vault. Creates new or updates existing.",
     inputSchema={"type": "object",
                  "properties": {
                      "enclave_id": {"type": "string", "description": "Enclave ID"},
                      "key": {"type": "string", "description": "Document key"},
                      "value": {"type": "string", "description": "Document content (text or JSON string)"},
                      "message": {"type": "string", "description": "Change description (used as commit message for git backend)"},
                  }, "required": ["enclave_id", "key", "value"]})
```

##### vault_list

```python
Tool(name="vault_list",
     description="List documents in Enclave Vault.",
     inputSchema={"type": "object",
                  "properties": {
                      "enclave_id": {"type": "string", "description": "Enclave ID"},
                      "prefix": {"type": "string", "description": "Filter by key prefix (e.g. 'design_')"},
                  }, "required": ["enclave_id"]})
```

##### run_playbook

```python
Tool(name="run_playbook",
     description="Start a Playbook in an Enclave. Automatically assigns tasks to role-bound Agents.",
     inputSchema={"type": "object",
                  "properties": {
                      "enclave_id": {"type": "string", "description": "Enclave ID"},
                      "playbook": {
                          "type": "object",
                          "description": "Playbook definition (inline) or playbook_id reference",
                          "properties": {
                              "playbook_id": {"type": "string", "description": "Existing playbook ID (mutually exclusive with stages)"},
                              "name": {"type": "string", "description": "Playbook name (for inline definition)"},
                              "stages": {
                                  "type": "array",
                                  "description": "Stage definitions (for inline definition)",
                                  "items": {
                                      "type": "object",
                                      "properties": {
                                          "name": {"type": "string"},
                                          "role": {"type": "string"},
                                          "description": {"type": "string"},
                                          "input_keys": {"type": "array", "items": {"type": "string"}},
                                          "output_key": {"type": "string"},
                                          "next": {"type": "string"},
                                          "on_reject": {"type": "string"},
                                          "timeout_seconds": {"type": "integer"},
                                      },
                                      "required": ["name", "role"],
                                  },
                              },
                          },
                      },
                  }, "required": ["enclave_id", "playbook"]})
```

##### get_run_status

```python
Tool(name="get_run_status",
     description="Get Playbook execution status for an Enclave.",
     inputSchema={"type": "object",
                  "properties": {
                      "enclave_id": {"type": "string", "description": "Enclave ID"},
                      "run_id": {"type": "string", "description": "Run ID (omit to get latest run)"},
                  }, "required": ["enclave_id"]})

### §7 SDK API

```python
# 创建 Enclave
enclave = await nexus.create_enclave(
    name="登录功能开发",
    vault={"backend": "git", "repo": "/path/to/project"},
    members={
        "architect": {"did": did_a, "handbook": "输出设计方案"},
        "developer": {"did": did_b, "handbook": "实现代码"},
        "reviewer":  {"did": did_c, "handbook": "质量把关"},
    },
)

# Vault 操作
await enclave.vault.put("requirements", "用户需要邮箱+密码登录...", message="初始需求")
doc = await enclave.vault.get("requirements")
history = await enclave.vault.history("requirements")

# 启动 Playbook
run = await enclave.run_playbook(standard_dev)
status = await run.get_status()
# → {"current_stage": "design", "stages": {"design": "active", ...}}

# Agent 侧（SDK 事件驱动模式）
@nexus.on_task_propose
async def handle_task(action):
    enclave_id = action.content.get("enclave_id")
    stage = action.content.get("stage_name")

    if stage == "design":
        # 读取需求
        req = await nexus.vault_get(enclave_id, "requirements")
        # 写设计文档
        await nexus.vault_put(enclave_id, "design_doc", design_output)
        # 汇报完成
        await nexus.notify_state(to_did=action.from_did, status="completed",
                                  task_id=action.content["task_id"])
```

### §8 完整场景示例

```
人类在 OpenClaw: "安排开发登录功能"
  │
  ▼
秘书 Agent（SDK 模式，常驻运行）
  │
  ├── 1. create_enclave("登录功能开发", members={...})
  ├── 2. vault.put("requirements", 需求文档)
  ├── 3. run_playbook(standard_dev)
  │
  │   PlaybookEngine 自动推进：
  │
  ├── 4. propose_task → Architect（stage: design）
  │      Architect 收到推送 → vault.get("requirements")
  │      → 输出设计方案 → vault.put("design_doc", ...)
  │      → notify_state(completed)
  │
  ├── 5. propose_task → Reviewer（stage: review_design）
  │      Reviewer 收到推送 → vault.get("design_doc")
  │      → 评审通过 → notify_state(completed)
  │      （或评审不通过 → notify_state(rejected) → 回退到 design）
  │
  ├── 6. propose_task → Developer（stage: implement）
  │      Developer 收到推送 → vault.get("design_doc")
  │      → 写代码 → vault.put("code_diff", ...)
  │      → notify_state(completed)
  │
  ├── 7. propose_task → Reviewer（stage: review_code）
  │      → 评审通过 → notify_state(completed)
  │
  └── 8. Playbook 完成 → 通知秘书 → 秘书汇报给人类
```

### §9 权限模型

```
permissions 字段：
  "r"     — 只读 Vault（Reviewer 默认）
  "rw"    — 读写 Vault（Developer / Architect 默认）
  "admin" — 读写 + 管理成员 + 启动 Playbook（Owner 默认）
```

权限检查在 Daemon 端点层执行：

```python
async def _check_vault_permission(enclave_id: str, did: str, required: str):
    member = await get_enclave_member(enclave_id, did)
    if not member:
        raise HTTPException(403, "Not a member of this enclave")
    if required == "rw" and member["permissions"] == "r":
        raise HTTPException(403, "Read-only access")
    if required == "admin" and member["permissions"] != "admin":
        raise HTTPException(403, "Admin access required")
```

### §10 演进路线

| 阶段 | 内容 | 依赖 |
|------|------|------|
| v0.9.5-alpha | Enclave CRUD + LocalVaultBackend + 6 个 MCP 工具 | 无 |
| v0.9.5-beta | GitVaultBackend + Playbook 引擎 + SDK API | v0.9.5-alpha |
| v0.9.5 | 权限模型 + 完整测试 + 文档 | v0.9.5-beta |
| v1.0+ | 跨机器 Enclave（Relay 同步元数据）+ 更多 Backend | v0.9.5 |

## 理由

### 为什么是 Enclave 而不是纯 Skill 匹配

Skill 匹配适合一次性任务（"帮我翻译这段话"），但项目级协作需要：
- 固定团队（不是每次临时搜索）
- 共享上下文（不是每条消息都带完整背景）
- 流程定义（不是手动逐步分发）

### 为什么 VaultBackend 要抽象

1. **Git 是最佳默认选择**：与 AI 编程工具（Claude Code / Kiro / Cursor）的工作方式一致，天然有版本历史和分布式同步
2. **企业场景需要灵活性**：有些团队用 Notion 管文档、用 Confluence 做 Wiki，不应该强制迁移
3. **简单场景零配置**：LocalVaultBackend 用 SQLite，不需要 Git

### 为什么 Playbook 是独立概念

Playbook 可复用——同一个"标准开发流程"可以用于不同的 Enclave。类比 CI/CD pipeline 模板。

### 考虑的替代方案

1. **纯消息编排（无 Enclave）** — 秘书 Agent 用代码逻辑串行发 propose_task，等 notify_state 再发下一个。问题：编排逻辑散落在秘书代码中，不可复用，无共享上下文。
2. **Relay 中心化存储** — Vault 数据全放 Relay Redis。问题：Relay 变重，违背"轻量邮局"定位；单点故障；隐私问题（文档经过第三方服务器）。
3. **每个 Agent 独立存储 + 消息同步** — 用 sync_resource 广播所有文档。问题：全量同步浪费带宽，版本冲突难处理。

## 影响范围

### v0.8.5 新增文件

| 文件 | 说明 |
|------|------|
| `agent_net/enclave/` | Enclave 模块目录 |
| `agent_net/enclave/models.py` | Enclave / Member / Playbook 数据模型 |
| `agent_net/enclave/vault.py` | VaultBackend 抽象接口 + 注册表 |
| `agent_net/enclave/vault_git.py` | GitVaultBackend 实现 |
| `agent_net/enclave/vault_local.py` | LocalVaultBackend 实现 |
| `agent_net/enclave/playbook.py` | Playbook 引擎 |
| `tests/test_enclave.py` | Enclave CRUD 测试 |
| `tests/test_vault.py` | VaultBackend 测试 |
| `tests/test_playbook.py` | Playbook 引擎测试 |

### 修改文件

| 文件 | 变更 |
|------|------|
| `agent_net/storage.py` | 新增 Enclave 相关表和 CRUD |
| `agent_net/node/daemon.py` | 新增 Enclave / Vault / Playbook 端点 |
| `agent_net/node/mcp_server.py` | 新增 6 个 MCP 工具（27→33） |
| `docs/mcp-setup.md` | 更新工具列表 |
| `docs/architecture.md` | 新增 Enclave 架构说明 |
| `docs/api-reference.md` | 新增 Enclave 端点 |
| `docs/requirements.md` | 更新 R-0851/R-0852/R-0853 状态 |

## 相关 ADR

- ADR-007: Action Layer 协作协议 — Playbook 引擎调用 propose_task / notify_state
- ADR-010: 平台适配器与 Skill 注册 — Enclave 成员可通过 Skill 匹配发现
- ADR-011: Discussion Protocol — Enclave 内可发起讨论
- ADR-012: ACP 协议栈 — Enclave 位于 L7 协作层之上

## 评审记录

| 日期 | 评审者 | 结果 | 备注 |
|------|--------|------|------|
| 2026-04-09 | Claude Code | 通过 | 基础实现完成：models/vault/storage/daemon/mcp，290 个测试通过 |
| 2026-04-09 | Claude Code | **通过（第二轮）** | 代码评审问题修复：B1 action 字段区分删除记录、B2 aiosqlite 异步 I/O、B3 移除 DDL 重复定义 |
| 2026-04-09 | 设计 Agent（代码评审） | **有条件通过** | 与 ADR-013 设计高度一致。✅ 12 项通过（34 tests passed）。⚠️ 3 个未实现项（GitVaultBackend / Playbook 消息拦截 / get_run_status 省略 run_id），详见 §设计评审 |
| 2026-04-09 | 设计 Agent（复审） | **全部通过** | N1 GitVaultBackend ✅（vault_git.py，8 tests passed）N2 Playbook 消息拦截 ✅（router._intercept_playbook_state）N3 get_run_status 省略 run_id ✅。全量测试 299 passed，场景链路全部打通 |

### v0.8.5 代码评审详情（2026-04-09）

#### 🔴 阻塞性问题

| # | 文件 | 问题 | 状态 |
|---|------|------|------|
| B1 | vault_local.py / storage.py | delete() 写入的 history 记录无法与普通历史记录区分（value='', message='[deleted]' 但调用方无法可靠识别） | ✅ 已修复 — 新增 `action` 字段（create/update/delete） |

#### 🟡 建议性问题

| # | 文件 | 问题 | 状态 |
|---|------|------|------|
| B2 | vault_local.py | 用同步 sqlite3，违反项目"禁止阻塞I/O"规范 | ✅ 已修复 — 改用 aiosqlite 异步 I/O |
| B3 | vault_local.py / storage.py | enclave_vault 表 DDL 重复定义，存在初始化顺序隐患 | ✅ 已修复 — vault_local.py 不再执行 DDL，由 storage.py 统一管理 |

### 设计评审（2026-04-09 设计 Agent）

评审对象：v0.8.5 Enclave 协作架构全部代码，对照 ADR-013。

#### ✅ 通过项

| # | 检查项 | 文件 |
|---|--------|------|
| 1 | 7 张表结构与 ADR-013 §2 完全一致（enclaves / members / playbooks / runs / stage_executions / vault / vault_history） | storage.py |
| 2 | 6 个索引全部创建（含 `idx_stage_executions_task`） | storage.py |
| 3 | VaultBackend 抽象接口与 §3 一致（get/put/list/history/delete + 3 个异常类型） | vault.py |
| 4 | LocalVaultBackend 完整实现（aiosqlite 异步、版本自增、历史 append-only、action 字段） | vault_local.py |
| 5 | Backend 注册表（register_vault_backend / create_vault_backend） | vault.py |
| 6 | 数据模型完整（Enclave / Member / Stage / Playbook / PlaybookRun / StageExecution + to_dict/from_dict） | models.py |
| 7 | Daemon 15 个端点全部实现（Enclave CRUD 5 + Member 3 + Vault 5 + Playbook Run 2） | daemon.py |
| 8 | Vault 端点使用 `{key:path}` 支持多级 key | daemon.py |
| 9 | 权限检查（`_check_vault_permission`：r/rw/admin 三级） | daemon.py |
| 10 | MCP 6 个工具实现（create_enclave / vault_get / vault_put / vault_list / run_playbook / get_run_status） | mcp_server.py |
| 11 | Owner 自动设为 admin | daemon.py |
| 12 | 34 个测试全部通过（Enclave CRUD + Member + Vault + Playbook + LocalVaultBackend + Models） | tests/ |

#### ✅ 未实现项已全部修复（2026-04-09）

| # | 内容 | 严重性 | 状态 | 说明 |
|---|------|--------|------|------|
| N1 | GitVaultBackend | 🟡 beta 阶段 | ✅ 已实现 | `vault_git.py`：git add/commit/push/pull + 版本历史，8 个测试通过 |
| N2 | Playbook 消息拦截 | 🟡 beta 阶段 | ✅ 已实现 | `playbook.py` + router `_intercept_playbook_state`，自动推进流程 |
| N3 | `get_run_status` 省略 run_id | 🟢 小功能 | ✅ 已修复 | 新增 `GET /enclaves/{id}/runs` 端点 |

#### 评分

| 维度 | 评分 |
|------|------|
| 设计一致性 | ⭐⭐⭐⭐⭐ |
| 功能完整性 | ⭐⭐⭐⭐⭐（alpha + beta 全部完成） |
| 代码质量 | ⭐⭐⭐⭐（异步 I/O、权限检查、错误处理完善） |
| 测试覆盖 | ⭐⭐⭐⭐⭐（28 tests，含 GitVaultBackend 8 个测试） |

## 答疑记录

| 日期 | 提问者 | 问题 | 回复 | 是否触发设计变更 |
|------|--------|------|------|----------------|
| | | | | |
