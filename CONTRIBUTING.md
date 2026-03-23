# Contributing to AgentNexus

**[中文](#中文) | [English](#english)**

---

## 中文

感谢你有意为 AgentNexus 贡献代码！在开始之前，请花几分钟读完本文档。

### 行为准则

本项目采用简单直接的准则：**尊重、建设性、专注技术**。不欢迎人身攻击、骚扰和歧视性言论。违反者将被移除讨论。

### 如何贡献

#### 报告 Bug

请通过 [GitHub Issues](https://github.com/kevinkaylie/AgentNexus/issues) 提交，包含以下信息：

- Python 版本 + 操作系统
- 复现步骤（最小可复现代码或命令）
- 期望行为 vs 实际行为
- 相关错误日志（贴完整 traceback）

#### 提交功能建议

在 Issue 中描述：

- **场景**：什么情况下需要这个功能？
- **方案**：你设想的实现方式（可选）
- **影响面**：是否涉及协议变更、API 变更、数据库迁移？

#### 提交 Pull Request

1. Fork 仓库，从 `main` 创建功能分支：
   ```bash
   git checkout -b feat/your-feature-name
   # 或
   git checkout -b fix/your-bug-description
   ```

2. 写代码，**同时写测试**（见下方测试规范）

3. 确保测试全部通过：
   ```bash
   python main.py test   # 必须 passed, 0 failed
   ```

4. 提交 PR，描述清楚：**做了什么、为什么这么做、如何测试**

### 开发环境搭建

```bash
git clone https://github.com/kevinkaylie/AgentNexus.git
cd AgentNexus
pip install -r requirements.txt

# 验证环境
python -c "import fastapi, aiosqlite, mcp, pynacl, cryptography, aiohttp; print('OK')"

# 运行测试
python main.py test
```

### 代码规范

#### Python 风格

- 遵循 [PEP 8](https://pep8.org/)，行宽 ≤ 100 字符
- 使用 f-string，不用 `%` 或 `.format()`
- 函数返回类型明确时，建议加类型注解
- **禁止阻塞调用**：所有 I/O 必须用 `await`，不得在 async 上下文中调用 `time.sleep()`、`requests.get()` 等阻塞函数

#### 架构约定（必须遵守）

| 规则 | 原因 |
|------|------|
| `common/` 不得导入 `node/` 或 `relay/` | 单向依赖，防止循环 import |
| 全局常量放 `common/constants.py` | 避免各模块硬编码 |
| 新 MCP 工具必须先在 `daemon.py` 加 HTTP 端点，再在 `mcp_server.py` 注册 | Daemon 是唯一真相来源 |
| 所有写端点加 `Depends(_require_token)` | 防未授权修改 |
| **私钥签名只能在 `daemon.py` 内完成** | 私钥不出户原则 |
| 数据库变更用 `ALTER TABLE` + `IF NOT EXISTS`，写在 `init_db()` 中 | 向后兼容，用户升级不丢数据 |

#### DID 与协议兼容性

- **不得修改 DID 格式** `did:agent:<16位hex>`，这是跨节点身份的基础
- **不得修改四步握手（AHP）协议的消息结构**，除非发起 RFC 讨论并升级主版本号
- **不得修改 NexusProfile 的 canonical 签名方式**（`json.dumps(sort_keys=True, separators=(',',':'))`），否则所有历史签名失效

### 测试规范

#### 必须写测试的场景

- 新增任何公开函数/方法
- 修改路由逻辑、门禁逻辑、签名逻辑
- 数据库 schema 变更

#### 测试风格

```python
# ✅ 正确：asyncio.run() 包裹，不用 pytest-asyncio
def test_xxx():
    async def _run():
        ...
    asyncio.run(_run())

# ✅ 正确：隔离存储，用 monkeypatch 替换 DB 路径
def test_yyy(tmp_path, monkeypatch):
    import agent_net.storage as s
    monkeypatch.setattr(s, "DB_PATH", tmp_path / "test.db")

# ✅ 正确：daemon 测试先 reload 再 monkeypatch，再用 with TestClient
def test_daemon(tmp_path, monkeypatch):
    import importlib, agent_net.storage as s, agent_net.node.daemon as d
    monkeypatch.setattr(s, "DB_PATH", tmp_path / "test.db")
    importlib.reload(d)
    monkeypatch.setattr(d, "DAEMON_TOKEN_FILE", str(tmp_path / "token.txt"))
    from fastapi.testclient import TestClient
    with TestClient(d.app) as client:
        ...

# ❌ 不要用 @pytest.mark.asyncio
# ❌ 不要使用真实 DB 路径（data/agent_net.db）
```

#### 测试命名

- 文件：`tests/test_<模块>.py`
- 函数：`test_<编号>_<描述>`，如 `test_tf13_new_feature`
- 编号延续现有序列（当前最高：`tf12`、`tg10`、`tc05`、`tm07`）

### Commit 信息规范

使用 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/)：

```
<类型>(<范围>): <简短描述>

[可选：详细说明]

[可选：BREAKING CHANGE: 说明破坏性变更]
```

| 类型 | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `test` | 新增/修改测试 |
| `docs` | 文档变更 |
| `refactor` | 重构（不影响功能） |
| `perf` | 性能优化 |
| `chore` | 构建/依赖/配置变更 |

示例：

```
feat(relay): add /federation/health endpoint with peer stats

fix(gatekeeper): blacklist check not applied in public mode

test(tf): add tf13 for federation announce deduplication

BREAKING CHANGE: NexusProfile content schema bumped to 2.0
```

### PR 审查清单

提交 PR 前请自查：

- [ ] `python main.py test` 全部通过
- [ ] 新功能有对应测试
- [ ] 没有硬编码路径/端口/URL（放 `constants.py`）
- [ ] 没有在 async 函数中调用阻塞 I/O
- [ ] 写接口加了 `Depends(_require_token)`（如适用）
- [ ] `common/` 没有导入 `node/` 或 `relay/`
- [ ] 数据库变更向后兼容
- [ ] PR 描述清楚说明了**做了什么、为什么、怎么测试**

### 安全漏洞披露

**请勿通过公开 Issue 报告安全漏洞。**

涉及密码学实现、私钥安全、握手协议缺陷的漏洞，请通过 GitHub 的 [Private Security Advisory](https://github.com/kevinkaylie/AgentNexus/security/advisories/new) 私密报告。我们承诺在 72 小时内确认收到，并在修复后公开披露致谢。

### 需要帮助？

- 阅读 [README](README.md) 和 [CLAUDE.md](CLAUDE.md) 了解架构设计
- 在 Issue 中提问，标注 `question` 标签
- 新手 PR 同样欢迎，我们会耐心 review

---

## English

Thank you for your interest in contributing to AgentNexus! Please take a few minutes to read this document before you start.

### Code of Conduct

This project follows a simple principle: **be respectful, constructive, and focused on technical merit**. Personal attacks, harassment, and discriminatory language are not tolerated. Violators will be removed from discussions.

### How to Contribute

#### Reporting Bugs

Open a [GitHub Issue](https://github.com/kevinkaylie/AgentNexus/issues) with:

- Python version + operating system
- Steps to reproduce (minimal reproducible code or commands)
- Expected behavior vs actual behavior
- Full error logs / traceback

#### Suggesting Features

Describe in an Issue:

- **Context**: What situation requires this feature?
- **Proposal**: Your idea for implementation (optional)
- **Scope**: Does it involve protocol changes, API changes, or DB migrations?

#### Submitting a Pull Request

1. Fork the repo and create a branch from `main`:
   ```bash
   git checkout -b feat/your-feature-name
   # or
   git checkout -b fix/your-bug-description
   ```

2. Write code and **write tests** (see testing guidelines below)

3. Ensure all tests pass:
   ```bash
   python main.py test   # must be passed, 0 failed
   ```

4. Open a PR explaining: **what you did, why, and how you tested it**

### Development Setup

```bash
git clone https://github.com/kevinkaylie/AgentNexus.git
cd AgentNexus
pip install -r requirements.txt

# Verify environment
python -c "import fastapi, aiosqlite, mcp, pynacl, cryptography, aiohttp; print('OK')"

# Run tests
python main.py test
```

### Code Standards

#### Python Style

- Follow [PEP 8](https://pep8.org/), max line width 100 characters
- Use f-strings, not `%` formatting or `.format()`
- Add type annotations when return types are clear
- **No blocking calls**: all I/O must use `await`; never call `time.sleep()`, `requests.get()`, or other blocking functions inside an async context

#### Architecture Rules (mandatory)

| Rule | Reason |
|------|--------|
| `common/` must not import from `node/` or `relay/` | One-way dependency, prevents circular imports |
| Global constants go in `common/constants.py` | Avoid hardcoding across modules |
| New MCP tools require a Daemon HTTP endpoint first, then an MCP registration | Daemon is the single source of truth |
| All write endpoints must use `Depends(_require_token)` | Prevent unauthorized modification |
| **Private key signing must only happen inside `daemon.py`** | Key isolation principle |
| DB schema changes use `ALTER TABLE` + `IF NOT EXISTS` inside `init_db()` | Backward-compatible upgrades |

#### DID & Protocol Compatibility

- **Do not modify the DID format** `did:agent:<16-hex>` — it is the foundation of cross-node identity
- **Do not modify the 4-Step Handshake (AHP) message structure** without an RFC discussion and a major version bump
- **Do not modify the NexusProfile canonical signing method** (`json.dumps(sort_keys=True, separators=(',',':'))`) — changing this invalidates all existing signatures

### Testing Guidelines

#### When tests are required

- Any new public function or method
- Changes to routing logic, gatekeeper logic, or signing logic
- Database schema changes

#### Testing style

```python
# ✅ Correct: wrap async tests with asyncio.run(), do NOT use pytest-asyncio
def test_xxx():
    async def _run():
        ...
    asyncio.run(_run())

# ✅ Correct: isolate storage via monkeypatch
def test_yyy(tmp_path, monkeypatch):
    import agent_net.storage as s
    monkeypatch.setattr(s, "DB_PATH", tmp_path / "test.db")

# ✅ Correct: for daemon tests — reload FIRST, then monkeypatch, then TestClient as context manager
def test_daemon(tmp_path, monkeypatch):
    import importlib, agent_net.storage as s, agent_net.node.daemon as d
    monkeypatch.setattr(s, "DB_PATH", tmp_path / "test.db")
    importlib.reload(d)
    monkeypatch.setattr(d, "DAEMON_TOKEN_FILE", str(tmp_path / "token.txt"))
    from fastapi.testclient import TestClient
    with TestClient(d.app) as client:
        ...

# ❌ Do not use @pytest.mark.asyncio
# ❌ Do not use the real DB path (data/agent_net.db)
```

#### Test naming

- File: `tests/test_<module>.py`
- Function: `test_<id>_<description>`, e.g. `test_tf13_new_feature`
- Continue from existing sequence (current highest: `tf12`, `tg10`, `tc05`, `tm07`)

### Commit Message Convention

Follow [Conventional Commits](https://www.conventionalcommits.org/en/):

```
<type>(<scope>): <short description>

[optional body]

[optional: BREAKING CHANGE: description]
```

| Type | Purpose |
|------|---------|
| `feat` | New feature |
| `fix` | Bug fix |
| `test` | Add or update tests |
| `docs` | Documentation changes |
| `refactor` | Refactoring (no behavior change) |
| `perf` | Performance improvement |
| `chore` | Build / dependency / config changes |

Examples:

```
feat(relay): add /federation/health endpoint with peer stats

fix(gatekeeper): blacklist check not applied in public mode

test(tf): add tf13 for federation announce deduplication

BREAKING CHANGE: NexusProfile content schema bumped to 2.0
```

### PR Checklist

Before submitting, verify:

- [ ] `python main.py test` passes with 0 failures
- [ ] New functionality has corresponding tests
- [ ] No hardcoded paths, ports, or URLs (use `constants.py`)
- [ ] No blocking I/O inside async functions
- [ ] Write endpoints use `Depends(_require_token)` where applicable
- [ ] `common/` does not import from `node/` or `relay/`
- [ ] Database changes are backward-compatible
- [ ] PR description clearly explains **what, why, and how it was tested**

### Security Vulnerability Disclosure

**Do not report security vulnerabilities through public Issues.**

For vulnerabilities related to cryptographic implementation, private key security, or handshake protocol flaws, please use GitHub's [Private Security Advisory](https://github.com/kevinkaylie/AgentNexus/security/advisories/new). We commit to acknowledging your report within 72 hours and crediting you publicly after the fix is released.

### Need Help?

- Read [README](README.md) and [CLAUDE.md](CLAUDE.md) to understand the architecture
- Ask questions in Issues with the `question` label
- First-time contributors are welcome — we'll review your PR patiently

---

*Thank you to everyone who makes AgentNexus better.*
