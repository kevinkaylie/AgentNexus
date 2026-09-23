# q3 行为用例执行记录（自动生成）

生成方式：`python scripts/run_q3_harness.py > <本文件>`（脚本不写文件，可重复生成）。

## 1. 适配器版本与实现位置

- 规范包版本：`1.0-draft.2+semantic.8`
- 实现模块：`agent_net/code_review/provider_adapter.py`（厂商无关管线与 provider 注册表）、`agent_net/code_review/hczj_adapter.py`（HCZJ 词表）、`agent_net/code_review/presentation.py`（呈现规则）、`agent_net/code_review/validation.py`（结构校验）
- 用例定义：`specs/profiles/code-review/v1/fixtures/binding/q3-outcome-coverage.md`

## 2. 可复现命令

```bash
python -m pytest tests/test_code_review_q3_harness.py -q -p no:cacheprovider
python scripts/run_q3_harness.py > specs/profiles/code-review/v1/fixtures/binding/q3-execution-record-<date>.md
```

## 3. 真实摘要（§15.3 口径）

| 对象 | 摘要 | 字节长度 |
|---|---|---|
| 目标 Profile 报告（q3-found-partial，序列化字节） | `sha256:f3fffc926a7eb9122a1927e4b04c655d5f7331e23f1f69e3245b928c1f8336f2` | 3546 |
| 冻结 fixture `valid/09` | `sha256:21cc14d91983c724bce736bb377542a5076b4a43b63afd7fc1a090f8e19226d3` | 3816 |

## 4. 转换结果（q3-found-partial，两种原 outcome）

| 原 HCZJ outcome | 目标 outcome | 目标 coverage | finding severity | 溯源 source_outcome |
|---|---|---|---|---|
| findings_present | `issues_found` | `partial` | `medium` | `findings_present` |
| inconclusive | `issues_found` | `partial` | `medium` | `inconclusive` |

两种输入的目标语义一致（`issues_found` + `partial`），各自保留源产物溯源，符合 q3 期望。

## 5. UI / 评论正文（实际渲染文本）

### q3-found-partial

```text
发现问题；覆盖：部分
缺口警示：本次评审未覆盖全部计划范围，结论不构成通过依据。
遗漏范围：src/main/java/com/example/OrderRepository.java（inherited_gap_impact_graph_truncated）
缺口原因：继承输入证据缺口：依赖图谱在 200 节点处截断
继承缺口：art_impact_R1（依赖图谱在 200 节点处截断（truncated=true））
[medium] 库存校验失败路径未释放预留额度
  触发：库存校验返回 false 后未回滚预留记录
  影响：失败订单长期占用库存额度
  证据：1 条（src/main/java/com/example/OrderService.java 等）
```

### q3-empty-partial（findings=[]、coverage=partial）

```text
结论不充分；覆盖：部分
缺口警示：本次评审未覆盖全部计划范围，结论不构成通过依据。
遗漏范围：src/main/java/com/example/OrderRepository.java（inherited_gap_impact_graph_truncated）
缺口原因：继承输入证据缺口：依赖图谱在 200 节点处截断
继承缺口：art_impact_R1（依赖图谱在 200 节点处截断（truncated=true））
```

## 6. 重复投递前后计数（真实执行）

| 指标 | 首次交付后 | 重放后 |
|---|---|---|
| deliveries | 1 | 1 |
| receipts | 1 | 1 |

- 重放标记 `replayed=True`，复用同一 artifact（`same_artifact=True`，id=`art_4d09cbf4e50f478a`）
- 回执 kind：['received']（**不含 `accepted`**，本入口只签发 `received`）

## 7. 拒绝阶段

| 用例 | 注入内容 | 拒绝阶段 | 错误码 |
|---|---|---|---|
| A | 非空 findings + outcome=inconclusive | 结构校验 | `invalid_output` |
| B | inherited_gaps 非空 + coverage=complete | 结构校验 | `invalid_output` |
| C | 模板只呈现 outcome | 呈现校验 | `invalid_output` |
| D | 呈现缺遗漏范围 | 呈现校验 | `invalid_output` |

C/D 的拒绝发生在**写入外部系统之前**，即使目标报告已通过 JSON Schema（`validate_review_report` 返回空）。

## 8. 未在本仓库验证的部分

- **发布重放半场**（“同 operation_id 发布重放不得新增 GitLab 评论”）属 HCZJ 应用边界（RC2 §5），本仓库没有 GitLab 写入路径，无法验证；测试中显式 `skip`，不视为通过。
- Nexus/HCZJ 侧的真实响应样例、`contract_revision` 取值仍待外部提供（T1–T6）。

## 9. 与冻结 fixture 的交叉校验

目标报告的关键不变式与冻结 `valid/09` 一致（outcome/coverage.status/severity）；`valid/09` 仅锁结构，不能代替本记录的行为验收。

