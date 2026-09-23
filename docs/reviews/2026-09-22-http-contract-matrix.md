# HTTP 契约矩阵（2026-09-22）

对应复审建议：「**建议补实际 HTTP 契约矩阵后收口，避免再次出现"字段存在但 wire 不一致"**」。

产物：`tests/test_code_review_http_contract.py`（41 项）。提交方：开发 Agent。

> 本文件说明矩阵**测什么、抓到什么、留下什么待裁决**，不是评审结论。

## 1. 为什么单独建这一个文件

前三轮评审反复出现同一类缺陷——B3（DTO/响应漂移）、R2-2（上传绑定成为可填写标签）、
R2-3（回执先落库），加上复审遗留的 P2 列表。根因不是某一处写错，而是：

> 既有测试断言的是"实现里有哪些字段"，不是**冻结契约在 wire 上的行为**。

于是"字段存在但 wire 不一致"每次都留给评审去发现。本文件把契约本身当成被测对象。

## 2. 矩阵怎么组织

**行是数据，不是测试函数**：`MATRIX` 是一个 Python 列表，一行 = 一个端点 × 一个声明的
失败（或成功）条件；一个 parametrized 执行器负责发**真实 HTTP 请求**，再对**实际响应**
做三重校验：

| 校验 | 内容 |
|---|---|
| 状态码 | 与契约 §7 的映射一致（400/422、401/403、404/410、409/412、413、429、503…） |
| 错误码与 scope | `code_review.error.v1` 的 `code` 与 `scope` |
| **冻结 schema** | 错误响应**真正通过** `error.schema.json`（类型、const、`additionalProperties`、`allOf` 不变式）；成功响应通过其冻结 schema（如 `artifact_ref.schema.json`） |

矩阵之外另有三组横切断言：
1. **传输层头**：`Cache-Control: no-store`（对**任何**响应）、JSON 响应必须是
   `application/json; charset=utf-8`（raw 除外）；
2. **DTO 字段集合**：TransportAck 恰好三字段、MessageView 恰好四字段（契约文本规定，
   不是 Profile schema）；
3. **认证优先于资源详情**：未认证请求不得通过 404/403 的差异泄露资源是否存在。

覆盖矩阵（41 行）：`POST A/messages`、`GET A/messages/{id}`、`POST A/artifacts`、
`GET A/artifacts/{id}/raw`，含成功路径、缺头、重复键、NaN、BOM、超限、未知字段、
越权、跨 session、未分配尝试、错误 epoch、If-Match 不匹配、Range 等。

## 3. 矩阵**抓到**的真实问题（写完后第一次运行即红 27 项）

这项工作的价值不在"通过"，而在于它一次性把评审三轮陆续发现的那类问题**全部变成红灯**：

| # | 抓到的问题 | 契约依据 | 修复 |
|---|---|---|---|
| M-1 | **错误响应不是合法的 `code_review.error.v1`**：`correlation_id` 为空（`minLength: 1`），约 20 处失败路径都如此 | `error.schema.json` required + `identifier` | 异常处理器在 `correlation_id` 为空时就地生成服务端 id 并回显为响应头 |
| M-2 | **413 响应体不合法**：`limit` / `limit_value` / `observed` 放在顶层，而 schema 是 `additionalProperties: false` | `error.schema.json` | 移入 `extensions.read_limit`；并在 `error_envelope()` 增加**守卫**：出现 schema 未声明的顶层字段直接抛错，而不是静默拼进去 |
| M-3 | 同类问题还有 `violations`（schema 校验失败细节）与 `unsatisfied`/`declared`（强制能力） | 同上 | 一并移入 `extensions` |
| M-4 | **JSON 响应缺少 `charset=utf-8`** | RC2 §1 | 前缀级中间件补 `application/json; charset=utf-8`；**raw 端点除外**（必须原样返回 media_type） |
| M-5 | **缺失 `X-Correlation-Id` 未被强制**（上一版头缺失时静默用信封值） | RC2 §1 | 四个新端点统一 `_require_correlation_header` → 422 |
| M-6 | **raw 的 `If-Match` 不匹配返回 409** | RC2 §2 要求 412 | 改为 412；409 保留给"存储字节与登记摘要不一致"的真实冲突 |
| M-7 | **`Range` 未显式拒绝**（静默返回全量） | RC2 §4 只定义完整字节读取 | 显式 422 |
| M-8 | **上传用裸 `json.loads`**：重复键、NaN、BOM 全部放行 | RC2 §1/§3 | 新增 `parse_strict_json`（严格 UTF-8、拒 BOM、拒重复键、拒非有限数），上传与信封共用同一套规则 |

另外 **M-9**：矩阵写行时发现我自己把"消息不存在"写成了 404 + `input_mismatch`，
但 §7 只允许 `input_mismatch` 落在 400/422，404/410 只对应 `evidence_unavailable`/
`artifact_expired`。已按 §7 改为 422，并在矩阵行里写下理由。

## 4. 幂等键措辞冲突：已裁决并落地（2026-09-22）

此前 RC2 §1 与 §4 对"幂等键"的表述落点不同（§1 说"变更接口带 `Idempotency-Key`"，
§4 表写 `message_id`）。**评审已裁决**：

> **POST A/messages 必须携带 `Idempotency-Key`，且值必须等于信封的 `message_id`。**
> 两者分别规定**传输位置**与**取值**，不是两套独立幂等键：§1 规定变更请求通过 HTTP 头
> 传递幂等键；§4 规定该接口的幂等键取 `message_id`。二者表示同一个逻辑幂等键，
> **不分别建立幂等记录**。§1 保留；§4 表同步修订以消除歧义。

执行规则（已写入契约 §4，并在矩阵中逐条有行/用例）：

| 情况 | 结果 | 覆盖 |
|---|---|---|
| 缺少或空头 | **422 `input_mismatch`**，不写入 | 矩阵行 `messages.idempotency_missing`；`test_idempotency_rule_1_missing_or_empty_header`（`None`/`""`/`"   "` 三种，并断言消息总数不变） |
| 头与 `message_id` 不一致 | **409 `idempotency_conflict`**，不写入 | 矩阵行 `messages.idempotency_key_mismatch`；`test_idempotency_rule_2_header_must_equal_message_id`（断言无写入） |
| 一致，同键同业务投影 | 返回原处理结果 | `test_idempotency_rule_3_same_key_same_projection_replays`（两次 202、响应相同、仅一条记录） |
| 一致，同键不同业务投影 | **409 `idempotency_conflict`**，**无副作用** | `test_idempotency_rule_4_...`（断言已存信封未被改写、消息总数不变） |

**`POST H/messages` 同理，但 delivery 例外**：delivery 的取值是 `delivery_id` 而非
`message_id`，不得机械地一律要求等于 `message_id`。契约 §4 表已按此修订
（`= envelope.message_id`；delivery 例外 `= delivery_id`），由 HCZJ 侧实现与验证。

`POST A/artifacts` 的 `Idempotency-Key` 是**上传自有键**，取值不由 `message_id` 规定；
矩阵行 `test_artifacts_idempotency_key_is_independent_of_message_id` 固定这一点，避免
把消息规则误套到上传接口。

契约本轮修订 → 规范包 `1.0-draft.2+semantic.13`。

## 5. 仍未覆盖（明确边界）

- **并发**：矩阵是串行请求，未做同 key 并发竞争（R2-1 复审要求里的"并发同 key"仍只是
  单线程重放）。并发竞态需要真实并发夹具，建议由测试 Agent 用专门的环境做。
- **时序**：租约过期、deadline 边界、`retry_after_seconds` 退避窗口只覆盖了静态分支。
- **外部端点**：Nexus/HCZJ 侧不在本矩阵范围。
- 矩阵通过**不代表**生产符合性，也不关闭 T1–T6 或 BINDING-GATE-1。

## 6. 运行
```bash
python -m pytest tests/test_code_review_http_contract.py -q -p no:cacheprovider
```

新增一条契约行为 = 在 `MATRIX` 里加一行；**不要**再加散落的 `assert resp.json()["field"]`。
