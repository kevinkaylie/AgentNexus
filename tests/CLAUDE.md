# tests - CLAUDE.md

## 测试用例说明
对应规格书中的5个验收测试用例，使用 pytest + asyncio。

## 运行方式
```bash
# 推荐：通过主入口运行
python main.py test

# 直接pytest
python -m pytest tests/ -v

# 不依赖pytest的简单runner
python tests/test_cases.py
```

## test_cases.py — 网络与路由用例

| 用例 | 测试点 | 关键断言 |
|------|--------|----------|
| tc01 | 本地自动注册 | `list_local_agents` 返回正确DID和name |
| tc02 | 内网点对点通信 | method=local，延迟<5ms |
| tc03 | NAT穿透降级 | P2P/Relay不可达时 method=offline |
| tc04 | 离线消息投递 | B离线时消息入库，上线后fetch_inbox取到且不重复 |
| tc05 | 语义寻址 | search_agents('Bank') 精确匹配能力标签 |

## test_handshake.py — 加密握手用例

| 用例 | 测试点 | 关键断言 |
|------|--------|----------|
| tc-h01 | 完整握手 | 双方 session key 相等且为 32 字节 |
| tc-h02 | 身份伪造 | verify_key 与签名不匹配时抛 `PermissionError` |
| tc-h03 | 会话加解密 | A 加密，B 用相同 session key 解密还原明文 |
| tc-h04 | 密钥唯一性 | 每次握手 X25519 临时密钥不同，session key 不重复 |
| tc-h05 | 过期 Challenge | timestamp 超过 TTL(30s) 时抛 `ValueError: expired` |
| tc-h06 | 状态机保护 | 无 pending challenge 时 `verify_response` 抛 `RuntimeError` |
| tc-h07 | 状态机保护 | 握手未完成时 `get_session_key` 抛 `RuntimeError` |

## test_gatekeeper.py — 访问控制用例

| 用例 | 测试点 | 关键断言 |
|------|--------|----------|
| tg01 | public 模式全部放行 | `GateDecision.ALLOW` |
| tg02 | private 模式拦截未知DID | `GateDecision.DENY` |
| tg03 | private 模式白名单放行 | `GateDecision.ALLOW` |
| tg04 | 黑名单优先（public模式下也拒绝）| `GateDecision.DENY` |
| tg05 | ask 模式未知DID写入pending队列 | `GateDecision.PENDING`，DB有记录 |
| tg06 | resolve allow 唤醒握手协程 | Future返回 `"allow"`，DB status=allow |
| tg07 | resolve deny 中断握手 | Future返回 `"deny"`，DB status=deny |
| tg08 | 重复 resolve 返回 False | 第二次 `resolve()` 返回 `False` |
| tg09 | list_pending 仅返回未处理记录 | 已 resolve 的不出现在列表 |
| tg10 | 白/黑名单文件持久化 | 新实例可读到前一实例写入的条目 |

## 测试隔离
- `use_test_db` fixture 通过 `monkeypatch` 替换 `storage.DB_PATH` 为临时目录
- `isolated` fixture 同时重定向 gatekeeper 的 `CONFIG_DIR`、`WHITELIST_PATH`、`BLACKLIST_PATH`、`MODE_PATH`
- 每个用例使用独立SQLite文件，互不干扰
- tc03 使用不可达地址模拟NAT穿透失败，无需真实网络
- 握手测试和 Gatekeeper 测试均为纯内存/纯本地，无网络依赖

## 新增测试规范
- 文件名以 `test_` 开头
- 每个用例对应一个 `test_t<prefix><nn>_<描述>()` 函数
- 异步逻辑统一用 `asyncio.run()` 包裹（Python 3.14 不再支持 `get_event_loop()`）
- fixture `isolated` 同时 monkeypatch DB路径和 gatekeeper 配置目录，保证测试隔离
