# T1–T6 证据采集包

本目录是 L0 binding **T1–T6 关闭**的唯一收口入口。它把「谁、交什么、怎么算通过」写成机器可校验的表单，
以免再把「源码已确认」当成「生产样例已取得」或「实现已验证」。

| 文件 | 作用 |
|---|---|
| `closure-checklist.json` | **唯一收口追踪器**：逐项登记证据要求、责任人、验收检查与声明状态 |
| `templates/T1..T6.json` | 待填写的证据记录；`__TODO__` 为占位符 |
| `received/` | 各方回填后的记录落点（`received/T1.json` … `received/T6.json`） |
| `../../tools/check_evidence.py` | 机械校验：重算摘要、拒绝虚假关闭、拒绝提前放行 |

## 当前状态

T1–T6 **全部开放**。`compatibility.json` 保持 `default_decision=reject`、`operative_allowlist=false`、
`artifact_access_scope=[]`。**BINDING-GATE-1 维持关闭**，不得启动符合本 Profile 的集成运行（Profile §15.1）。

## 采集约定

1. **先复制再回填**：`received/<T>.json` 由 `templates/<T>.json` 复制而来，不得改动 `templates/`。
2. **记录级状态**：每条 record 有 `status`（`open`/`closed`）；T 项的 `item_status` 只有在全部 blocking 记录
   均为 `closed` 时才可为 `closed`。校验脚本会比较「声明」与「实际」并拒绝不一致。
3. **原始字节是唯一口径**：所有响应/报告样例以 `raw_bytes_b64` 承载，同时声明 `sha256` 与 `byte_length`。
   校验脚本会重算；不接受「与生产一致」这类自述。

   ```
   sha256 = "sha256:" + sha256(base64.b64decode(raw_bytes_b64)).hexdigest()
   byte_length = len(base64.b64decode(raw_bytes_b64))
   ```

4. **脱敏不得改字节**：需要遮蔽字段时，用**等长**占位符就地替换后再计算摘要，并在 `redaction_note` 说明
   改动范围；不得重新序列化、压缩、改换行或去尾换行。若遮蔽会使字节口径失真，请改为在
   `redaction_note` 中说明并提供一个未遮蔽的等价小样本。
5. **部署不是工作树**：`deployment_version.source_revision` / `artifact_identifier` 必须能定位**已部署制品**。
   `bindings/source-evidence.json` 只是核对对象定位，不能作为部署版本证据。
6. **每项除正例还要有拒绝例**：冲突、越权、未知值必须各给一份实测拒绝样例；只有正例不算关闭。
7. **不提交凭据**：请求头只保留认证方案名与 correlation id；GitLab `PRIVATE-TOKEN`、Bearer 值一律不得写入。

## 校验

```bash
# 单跑证据校验（0=清单自洽且无虚假关闭，1=不一致/虚假关闭/提前放行）
python specs/profiles/code-review/v1/tools/check_evidence.py

# 包自检已内置该步
python specs/profiles/code-review/v1/tools/validate.py
```

未提供任何 `received/*.json` 时校验**通过**并报告「全部开放」——开放是合法状态；
它拒绝的是**声称关闭却拿不出证据**，以及在 T1–T6 未关闭时把 `compatibility.json` 放行。

## 关闭流程

1. Nexus / HCZJ 各自回填 `received/T{n}.json`，把该次 change 提交到本包（含原始字节，不含凭据）。
2. 维护者把 `closure-checklist.json` 中对应 `items[].status` 与 `status_reason` 改为本次实际结论。
3. 跑 `tools/check_evidence.py`：不一致即退回补充，不得直接改声明迁就实际。
4. T1–T6 全部关闭后，按 T6 的三方签署记录冻结 `compatibility.json`，再进入 CP-01～26 执行与定版评审。

## 与其他记录的关系

- `../external-confirmations-2026-09-20.md` — 源码层面的跨项目确认（**不替代**本目录的生产证据）。
- `../source-evidence.json` — 核对对象的文件摘要（**不证明**已部署版本）。
- `../l0-service-contract.md` §2–§6 — 各字段与端点的规范来源；本目录的表单不新增契约要求。
- `../../fixtures/binding/q3-outcome-coverage.md` — 语义行为用例；与本目录的 `T6.mapping_fixtures` 互补。
